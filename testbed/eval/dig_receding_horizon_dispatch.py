"""Request-local Dig dispatch controls for the offline receding-horizon audit."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, TypeVar

import numpy as np

from testbed.eval.dig_effect_state import canonical_token_sha256
from testbed.eval.temporal_dispatch_contract import (
    TemporalDispatchStrategy,
    temporal_dispatch_contributors_for_frame,
)

GOAL_KEY = "dig_cut_tokens"
LEGACY_STRATEGY_ID = "legacy_100_oldest_first_decay_0p01"
LATEST_STRATEGY_ID = "latest_chunk_receding_horizon_diagnostic_v1"


@dataclass(frozen=True)
class DigDispatchFrame:
    """One raw chunk plus the diagnostic action selected from it."""

    raw_action_chunk: np.ndarray
    dispatched_action: np.ndarray
    contributing_chunk_ages: tuple[int, ...]
    contributing_chunk_weights: tuple[float, ...]
    cache_reset: bool
    goal_sha256: str
    frame_index_in_cache_epoch: int
    clipping_applied: bool = False

    @property
    def nonfinite(self) -> bool:
        return bool(
            not np.isfinite(self.raw_action_chunk).all()
            or not np.isfinite(self.dispatched_action).all()
        )


class _GoalBoundDispatcher:
    def __init__(self, policy: Any) -> None:
        self.policy = policy
        self._goal_sha256: str | None = None
        self._frame_index = 0

    def begin_request(self) -> None:
        """Force the next frame to start an independent request-local cache epoch."""
        self._goal_sha256 = None
        self._frame_index = 0

    def _bind_goal(
        self,
        observation: Mapping[str, Any],
        goal_token: Sequence[float] | np.ndarray,
    ) -> tuple[dict[str, Any], str, bool, int]:
        token = np.asarray(goal_token, dtype=np.float32).reshape(-1)
        goal_sha256 = canonical_token_sha256(token.tolist())
        cache_reset = goal_sha256 != self._goal_sha256
        if cache_reset:
            reset = getattr(self.policy, "reset", None)
            if not callable(reset):
                raise TypeError("Dig dispatch policy must expose reset()")
            reset()
            self._goal_sha256 = goal_sha256
            self._frame_index = 0
        frame_index = self._frame_index
        self._frame_index += 1
        bound = dict(observation)
        bound[GOAL_KEY] = token.copy()
        return bound, goal_sha256, cache_reset, frame_index

    @staticmethod
    def _raw_chunk(policy: Any, observation: Mapping[str, Any]) -> np.ndarray:
        method = getattr(policy, "predict_action_chunk", None)
        if not callable(method):
            raise TypeError("Dig dispatch policy must expose predict_action_chunk()")
        value = method(dict(observation))
        actions = getattr(value, "actions", value)
        chunk = np.asarray(actions, dtype=np.float32)
        if chunk.ndim != 2 or chunk.shape[0] < 1 or chunk.shape[1] != 4:
            raise ValueError("ACT raw action chunk must have shape [queries,4]")
        return chunk.copy()


class LatestChunkRecedingHorizonDispatcher(_GoalBoundDispatcher):
    """Dispatch only query zero from a newly inferred chunk on every frame."""

    def dispatch(
        self,
        observation: Mapping[str, Any],
        goal_token: Sequence[float] | np.ndarray,
    ) -> DigDispatchFrame:
        bound, goal_sha256, cache_reset, frame_index = self._bind_goal(
            observation, goal_token
        )
        chunk = self._raw_chunk(self.policy, bound)
        return DigDispatchFrame(
            raw_action_chunk=chunk,
            dispatched_action=chunk[0].copy(),
            contributing_chunk_ages=(0,),
            contributing_chunk_weights=(1.0,),
            cache_reset=cache_reset,
            goal_sha256=goal_sha256,
            frame_index_in_cache_epoch=frame_index,
        )


class LegacyTemporalAggregationDispatcher(_GoalBoundDispatcher):
    """Trace public ``ACTAdapter.predict`` without changing its cache semantics."""

    def __init__(self, policy: Any) -> None:
        super().__init__(policy)
        self.strategy = legacy_strategy_from_policy(policy)

    def dispatch(
        self,
        observation: Mapping[str, Any],
        goal_token: Sequence[float] | np.ndarray,
    ) -> DigDispatchFrame:
        bound, goal_sha256, cache_reset, frame_index = self._bind_goal(
            observation, goal_token
        )
        chunk = self._raw_chunk(self.policy, bound)
        predict = getattr(self.policy, "predict", None)
        if not callable(predict):
            raise TypeError("legacy Dig dispatch policy must expose predict()")
        dispatched = np.asarray(predict(dict(bound)), dtype=np.float32).reshape(-1)
        if dispatched.shape != (4,):
            raise ValueError("legacy ACT dispatched action must have shape [4]")
        contributors = temporal_dispatch_contributors_for_frame(
            current_frame=frame_index,
            strategy=self.strategy,
            epoch_start_frame=0,
        )
        return DigDispatchFrame(
            raw_action_chunk=chunk,
            dispatched_action=dispatched.copy(),
            contributing_chunk_ages=tuple(item.age for item in contributors),
            contributing_chunk_weights=tuple(item.weight for item in contributors),
            cache_reset=cache_reset,
            goal_sha256=goal_sha256,
            frame_index_in_cache_epoch=frame_index,
        )


def legacy_strategy_from_policy(policy: Any) -> TemporalDispatchStrategy:
    contract = getattr(policy, "temporal_aggregation_contract", None)
    required = ("enabled", "num_queries", "window", "weight_order", "decay")
    if contract is None or any(not hasattr(contract, name) for name in required):
        raise TypeError("legacy policy lacks a resolved temporal aggregation contract")
    if not bool(contract.enabled):
        raise ValueError("legacy diagnostic requires temporal aggregation enabled")
    if str(contract.weight_order) != "legacy_oldest_first":
        raise ValueError("legacy diagnostic requires legacy_oldest_first ordering")
    return TemporalDispatchStrategy(
        strategy_id=LEGACY_STRATEGY_ID,
        num_queries=int(contract.num_queries),
        maximum_contributor_age=int(contract.window) - 1,
        weight_order=str(contract.weight_order),
        decay=float(contract.decay),
        diagnostic_only=False,
        promotion_eligible=False,
    )


def latest_strategy(num_queries: int) -> TemporalDispatchStrategy:
    return TemporalDispatchStrategy(
        strategy_id=LATEST_STRATEGY_ID,
        num_queries=int(num_queries),
        maximum_contributor_age=0,
        weight_order="not_applicable",
        decay=0.0,
        dispatch_mode="latest_current_chunk",
        diagnostic_only=True,
        promotion_eligible=False,
    )


DispatcherT = TypeVar("DispatcherT", bound=_GoalBoundDispatcher)


def make_independent_arm_dispatchers(
    *,
    policy_factory: Callable[[], Any],
    dispatcher_type: type[DispatcherT],
) -> dict[str, DispatcherT]:
    policies = {name: policy_factory() for name in ("baseline", "alternate")}
    if policies["baseline"] is policies["alternate"]:
        raise ValueError("baseline and alternate must use independent policy instances")
    dispatchers = {name: dispatcher_type(policy) for name, policy in policies.items()}
    if dispatchers["baseline"] is dispatchers["alternate"]:
        raise ValueError("baseline and alternate dispatch caches are shared")
    return dispatchers


def summarise_contributing_chunk_ages(
    rows: Sequence[DigDispatchFrame],
) -> dict[str, Any]:
    ages = [age for row in rows for age in row.contributing_chunk_ages]
    counts = {str(age): ages.count(age) for age in sorted(set(ages))}
    return {
        "frame_count": len(rows),
        "contributor_count": len(ages),
        "contributor_count_by_frame": [
            len(row.contributing_chunk_ages) for row in rows
        ],
        "count_by_age": counts,
        "minimum_age": min(ages) if ages else None,
        "maximum_age": max(ages) if ages else None,
        "p01": float(np.quantile(ages, 0.01)) if ages else None,
        "p50": float(np.quantile(ages, 0.50)) if ages else None,
        "p99": float(np.quantile(ages, 0.99)) if ages else None,
    }


def assess_action_support(
    actions: np.ndarray,
    *,
    p01: Sequence[float] | np.ndarray,
    p99: Sequence[float] | np.ndarray,
) -> dict[str, Any]:
    values = np.asarray(actions, dtype=np.float32)
    if values.ndim < 2 or values.shape[-1] != 4:
        raise ValueError("actions must have a final width of four")
    flat = values.reshape(-1, 4)
    lower = np.asarray(p01, dtype=np.float32).reshape(-1)
    upper = np.asarray(p99, dtype=np.float32).reshape(-1)
    if (
        lower.shape != (4,)
        or upper.shape != (4,)
        or not np.isfinite(lower).all()
        or not np.isfinite(upper).all()
        or np.any(lower > upper)
    ):
        raise ValueError("action p01/p99 support bounds are invalid")
    finite_rows = np.isfinite(flat).all(axis=1)
    outside_axis = finite_rows[:, None] & (
        (flat < lower[None, :]) | (flat > upper[None, :])
    )
    violation_rows = np.any(outside_axis, axis=1)
    row_count = int(flat.shape[0])
    violation_count = int(np.count_nonzero(violation_rows))
    nonfinite_count = int(np.count_nonzero(~finite_rows))
    return {
        "row_count": row_count,
        "support_violation_count": violation_count,
        "support_violation_rate": violation_count / row_count if row_count else 0.0,
        "support_violation_by_axis": [
            int(value) for value in np.count_nonzero(outside_axis, axis=0)
        ],
        "nonfinite_count": nonfinite_count,
        "nonfinite_rate": nonfinite_count / row_count if row_count else 0.0,
        "clipping_applied": False,
        "p01": lower.astype(float).tolist(),
        "p99": upper.astype(float).tolist(),
    }


__all__ = [
    "DigDispatchFrame",
    "LATEST_STRATEGY_ID",
    "LEGACY_STRATEGY_ID",
    "LegacyTemporalAggregationDispatcher",
    "LatestChunkRecedingHorizonDispatcher",
    "assess_action_support",
    "latest_strategy",
    "legacy_strategy_from_policy",
    "make_independent_arm_dispatchers",
    "summarise_contributing_chunk_ages",
]
