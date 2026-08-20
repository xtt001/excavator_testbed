"""Pure reconstruction and measurement for frozen temporal dispatch candidates.

This module deliberately has no policy, checkpoint, dataset, or runtime
dependencies.  It reconstructs the action dispatched from already-produced
ACT chunks while preserving the two cache facts that matter to an offline
audit: a contributor must be an earlier chunk whose query covers the current
frame, and no contributor may cross an explicit reset boundary.

Candidate selection belongs to a source-disjoint validation runner.  This
module only exposes pre-registered candidates and computes JSON-ready facts
from a frozen metric contract; it never tunes a window, weight, or threshold
against a target segment.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

SCHEMA = "temporal_dispatch_contract_v1"
REQUIRED_RESPONSE_ACTIVE_FRACTION = 0.80

_AGGREGATE_MODE = "temporal_aggregation"
_LATEST_MODE = "latest_current_chunk"
_LEGACY_ORDER = "legacy_oldest_first"
_NEWEST_ORDER = "newest_first"


class TemporalDispatchContractError(ValueError):
    """Raised when frozen dispatch inputs or measurements are inconsistent."""


@dataclass(frozen=True)
class TemporalDispatchStrategy:
    """One pre-registered way to dispatch actions from raw ACT chunks.

    ``maximum_contributor_age`` is inclusive.  For example, the normal
    100-query ACT window has a maximum age of 99, while the bounded candidate
    retains chunks aged 0 through 20 (21 possible contributors).  This avoids
    silently conflating an ACT ``window=20`` with a true maximum age of 20.
    """

    strategy_id: str
    num_queries: int
    maximum_contributor_age: int
    weight_order: str
    decay: float
    dispatch_mode: str = _AGGREGATE_MODE
    diagnostic_only: bool = False
    promotion_eligible: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.strategy_id, str) or not self.strategy_id.strip():
            raise TemporalDispatchContractError("strategy_id must be a non-empty string")
        if not isinstance(self.diagnostic_only, bool):
            raise TemporalDispatchContractError("diagnostic_only must be boolean")
        if not isinstance(self.promotion_eligible, bool):
            raise TemporalDispatchContractError("promotion_eligible must be boolean")
        _positive_int(self.num_queries, "num_queries")
        _nonnegative_int(self.maximum_contributor_age, "maximum_contributor_age")
        if self.maximum_contributor_age >= self.num_queries:
            raise TemporalDispatchContractError(
                "maximum_contributor_age must be smaller than num_queries"
            )
        if self.dispatch_mode not in {_AGGREGATE_MODE, _LATEST_MODE}:
            raise TemporalDispatchContractError("dispatch_mode is invalid")
        if self.weight_order not in {_LEGACY_ORDER, _NEWEST_ORDER, "not_applicable"}:
            raise TemporalDispatchContractError("weight_order is invalid")
        if not math.isfinite(float(self.decay)) or float(self.decay) < 0.0:
            raise TemporalDispatchContractError("decay must be finite and non-negative")
        if self.dispatch_mode == _AGGREGATE_MODE:
            if self.weight_order not in {_LEGACY_ORDER, _NEWEST_ORDER}:
                raise TemporalDispatchContractError(
                    "temporal aggregation requires a recognised weight_order"
                )
        else:
            if self.maximum_contributor_age != 0:
                raise TemporalDispatchContractError(
                    "latest-current dispatch cannot retain historical contributors"
                )
            if self.weight_order != "not_applicable" or float(self.decay) != 0.0:
                raise TemporalDispatchContractError(
                    "latest-current dispatch must not define temporal weights"
                )
            if not self.diagnostic_only or self.promotion_eligible:
                raise TemporalDispatchContractError(
                    "latest-current dispatch is diagnostic-only and non-promotable"
                )
        if self.diagnostic_only and self.promotion_eligible:
            raise TemporalDispatchContractError(
                "a diagnostic-only strategy cannot be promotion eligible"
            )

    @property
    def contributor_window(self) -> int:
        """Maximum count of chunks that may contribute after a reset."""

        return self.maximum_contributor_age + 1

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe declaration without turning it into runtime config."""

        return {
            "strategy_id": self.strategy_id,
            "num_queries": int(self.num_queries),
            "maximum_contributor_age": int(self.maximum_contributor_age),
            "contributor_window": int(self.contributor_window),
            "weight_order": self.weight_order,
            "decay": float(self.decay),
            "dispatch_mode": self.dispatch_mode,
            "diagnostic_only": bool(self.diagnostic_only),
            "promotion_eligible": bool(self.promotion_eligible),
            "reset_semantics": {
                "explicit_reset_required_at_first_frame": True,
                "contributors_cross_reset_boundary": False,
                "each_condition_requires_independent_temporal_state": True,
            },
        }


@dataclass(frozen=True)
class TemporalDispatchContributor:
    """A single raw chunk/query contribution to one dispatched action."""

    source_frame_index: int
    query_index: int
    age: int
    weight: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_frame_index": int(self.source_frame_index),
            "query_index": int(self.query_index),
            "age": int(self.age),
            "weight": float(self.weight),
        }


@dataclass(frozen=True)
class TemporalDispatchTrace:
    """Reconstructed dispatch stream and its cache-style contributors."""

    strategy: TemporalDispatchStrategy
    actions: np.ndarray
    contributors: tuple[tuple[TemporalDispatchContributor, ...], ...]
    reset_frame_indices: tuple[int, ...]

    def as_dict(self) -> dict[str, Any]:
        """Make the complete trace safe to write to a JSON audit artifact."""

        return {
            "schema": SCHEMA,
            "strategy": self.strategy.as_dict(),
            "reset_frame_indices": [int(value) for value in self.reset_frame_indices],
            "actions": np.asarray(self.actions, dtype=np.float64).tolist(),
            "frames": [
                {
                    "frame_index": frame_index,
                    "dispatched_action": np.asarray(
                        self.actions[frame_index], dtype=np.float64
                    ).tolist(),
                    "contributors": [
                        value.as_dict() for value in frame_contributors
                    ],
                }
                for frame_index, frame_contributors in enumerate(self.contributors)
            ],
        }


@dataclass(frozen=True)
class TemporalDispatchMetricContract:
    """Externally frozen thresholds used only to measure candidate quality.

    The constructor accepts no target data.  The caller supplies values chosen
    from strict training and held-out validation sources.  The response gate is
    intentionally fixed at 80 percent, matching the Stage-A response contract.
    """

    response_threshold: np.ndarray
    action_scale: np.ndarray
    envelope_lower: np.ndarray
    envelope_upper: np.ndarray
    jitter_mean_abs_limit: np.ndarray
    discontinuity_threshold: np.ndarray
    required_active_frame_fraction: float = REQUIRED_RESPONSE_ACTIVE_FRACTION

    def __post_init__(self) -> None:
        vectors = {
            "response_threshold": _finite_vector(
                self.response_threshold, "response_threshold"
            ),
            "action_scale": _finite_vector(self.action_scale, "action_scale"),
            "envelope_lower": _finite_vector(
                self.envelope_lower, "envelope_lower"
            ),
            "envelope_upper": _finite_vector(
                self.envelope_upper, "envelope_upper"
            ),
            "jitter_mean_abs_limit": _finite_vector(
                self.jitter_mean_abs_limit, "jitter_mean_abs_limit"
            ),
            "discontinuity_threshold": _finite_vector(
                self.discontinuity_threshold, "discontinuity_threshold"
            ),
        }
        width = vectors["response_threshold"].shape[0]
        if any(vector.shape != (width,) for vector in vectors.values()):
            raise TemporalDispatchContractError(
                "metric contract vectors must share one action width"
            )
        if np.any(vectors["response_threshold"] <= 0.0):
            raise TemporalDispatchContractError("response_threshold must be positive")
        if np.any(vectors["action_scale"] <= 0.0):
            raise TemporalDispatchContractError("action_scale must be positive")
        if np.any(vectors["jitter_mean_abs_limit"] < 0.0):
            raise TemporalDispatchContractError(
                "jitter_mean_abs_limit must be non-negative"
            )
        if np.any(vectors["discontinuity_threshold"] < 0.0):
            raise TemporalDispatchContractError(
                "discontinuity_threshold must be non-negative"
            )
        if np.any(vectors["envelope_lower"] > vectors["envelope_upper"]):
            raise TemporalDispatchContractError(
                "envelope_lower must not exceed envelope_upper"
            )
        gate = float(self.required_active_frame_fraction)
        if not math.isclose(
            gate,
            REQUIRED_RESPONSE_ACTIVE_FRACTION,
            rel_tol=0.0,
            abs_tol=0.0,
        ):
            raise TemporalDispatchContractError(
                "required_active_frame_fraction is fixed at 0.80"
            )
        for name, vector in vectors.items():
            copied = vector.astype(np.float64, copy=True)
            copied.setflags(write=False)
            object.__setattr__(self, name, copied)

    @property
    def action_dim(self) -> int:
        return int(self.response_threshold.shape[0])

    def as_dict(self) -> dict[str, Any]:
        return {
            "response_threshold": self.response_threshold.tolist(),
            "action_scale": self.action_scale.tolist(),
            "envelope_lower": self.envelope_lower.tolist(),
            "envelope_upper": self.envelope_upper.tolist(),
            "jitter_mean_abs_limit": self.jitter_mean_abs_limit.tolist(),
            "discontinuity_threshold": self.discontinuity_threshold.tolist(),
            "required_active_frame_fraction": float(
                self.required_active_frame_fraction
            ),
        }


def pre_registered_temporal_dispatch_strategies() -> dict[str, TemporalDispatchStrategy]:
    """Return the complete frozen candidate set for Return validation.

    The first entry is an identity baseline, not a replacement candidate.  The
    two aggregation candidates can be selected only by an independent Return
    validation run.  The latest-current-chunk entry is a diagnostic control and
    remains non-promotable even if it looks favourable offline.
    """

    strategies = (
        TemporalDispatchStrategy(
            strategy_id="legacy_100_oldest_first_decay_0p01",
            num_queries=100,
            maximum_contributor_age=99,
            weight_order=_LEGACY_ORDER,
            decay=0.01,
            promotion_eligible=False,
        ),
        TemporalDispatchStrategy(
            strategy_id="newest_first_100_decay_0p01",
            num_queries=100,
            maximum_contributor_age=99,
            weight_order=_NEWEST_ORDER,
            decay=0.01,
            promotion_eligible=True,
        ),
        TemporalDispatchStrategy(
            strategy_id="newest_first_max_age_20_decay_0p01",
            num_queries=100,
            maximum_contributor_age=20,
            weight_order=_NEWEST_ORDER,
            decay=0.01,
            promotion_eligible=True,
        ),
        TemporalDispatchStrategy(
            strategy_id="latest_current_chunk_diagnostic",
            num_queries=100,
            maximum_contributor_age=0,
            weight_order="not_applicable",
            decay=0.0,
            dispatch_mode=_LATEST_MODE,
            diagnostic_only=True,
            promotion_eligible=False,
        ),
    )
    return {strategy.strategy_id: strategy for strategy in strategies}


def temporal_dispatch_contributors_for_frame(
    *,
    current_frame: int,
    strategy: TemporalDispatchStrategy,
    epoch_start_frame: int = 0,
) -> tuple[TemporalDispatchContributor, ...]:
    """Describe the exact chunk/query weights used at one live dispatch frame."""

    _nonnegative_int(current_frame, "current_frame")
    _nonnegative_int(epoch_start_frame, "epoch_start_frame")
    if epoch_start_frame > current_frame:
        raise TemporalDispatchContractError(
            "epoch_start_frame must not follow current_frame"
        )
    if strategy.dispatch_mode == _LATEST_MODE:
        source_indices = np.asarray([current_frame], dtype=np.int64)
        query_indices = np.asarray([0], dtype=np.int64)
        weights = np.asarray([1.0], dtype=np.float64)
    else:
        start_frame = max(
            epoch_start_frame,
            current_frame - strategy.maximum_contributor_age,
        )
        source_indices = np.arange(start_frame, current_frame + 1, dtype=np.int64)
        query_indices = current_frame - source_indices
        weights = _temporal_weights(ages=query_indices, strategy=strategy)
    return tuple(
        TemporalDispatchContributor(
            source_frame_index=int(source_frame),
            query_index=int(query_index),
            age=int(current_frame - source_frame),
            weight=float(weight),
        )
        for source_frame, query_index, weight in zip(
            source_indices,
            query_indices,
            weights,
            strict=True,
        )
    )


def reconstruct_temporal_dispatch(
    *,
    chunks: np.ndarray,
    strategy: TemporalDispatchStrategy,
    reset_frame_indices: tuple[int, ...] | list[int] | None = None,
) -> TemporalDispatchTrace:
    """Reconstruct one action stream from a sequence of raw ACT chunks.

    ``chunks[frame, query]`` is the action proposed at ``frame + query`` by a
    policy state observed at ``frame``.  ``reset_frame_indices`` marks the
    first frame of each independent cache epoch.  A reset prevents an older
    chunk from contributing after that point, which mirrors a real
    ``policy.reset()`` without instantiating or mutating a policy.
    """

    if not isinstance(strategy, TemporalDispatchStrategy):
        raise TemporalDispatchContractError("strategy must be a TemporalDispatchStrategy")
    values = _finite_array(chunks, "chunks", ndim=3)
    frame_count, query_count, action_dim = values.shape
    if query_count != strategy.num_queries:
        raise TemporalDispatchContractError(
            "raw chunk query width disagrees with temporal dispatch strategy"
        )
    if frame_count < 1 or action_dim < 1:
        raise TemporalDispatchContractError("chunks must contain frames and actions")
    resets = _normalise_reset_frame_indices(reset_frame_indices, frame_count)
    reset_set = set(resets)
    actions = np.empty((frame_count, action_dim), dtype=np.float32)
    contributors_by_frame: list[tuple[TemporalDispatchContributor, ...]] = []
    epoch_start = 0

    for current_frame in range(frame_count):
        if current_frame in reset_set:
            epoch_start = current_frame
        contributors = temporal_dispatch_contributors_for_frame(
            current_frame=current_frame,
            strategy=strategy,
            epoch_start_frame=epoch_start,
        )
        source_indices = np.asarray(
            [item.source_frame_index for item in contributors],
            dtype=np.int64,
        )
        query_indices = np.asarray(
            [item.query_index for item in contributors],
            dtype=np.int64,
        )
        weights = np.asarray(
            [item.weight for item in contributors],
            dtype=np.float64,
        )

        values_for_frame = values[source_indices, query_indices]
        actions[current_frame] = np.sum(
            values_for_frame * weights[:, None], axis=0, dtype=np.float64
        ).astype(np.float32)
        contributors_by_frame.append(contributors)

    return TemporalDispatchTrace(
        strategy=strategy,
        actions=actions,
        contributors=tuple(contributors_by_frame),
        reset_frame_indices=resets,
    )


def evaluate_temporal_dispatch_metrics(
    *,
    baseline: TemporalDispatchTrace,
    alternate: TemporalDispatchTrace,
    metric_contract: TemporalDispatchMetricContract,
    reference_actions: np.ndarray,
) -> dict[str, Any]:
    """Measure target response and action quality under a frozen contract.

    ``reference_actions`` is an externally fixed action stream, normally the
    legacy dispatch on the same held-out sequence.  It is a comparison
    diagnostic, never a source from which this function derives thresholds.
    The output intentionally does not decide whether a candidate replaces any
    runtime strategy.
    """

    baseline_actions = _trace_actions(baseline, "baseline")
    alternate_actions = _trace_actions(alternate, "alternate")
    if baseline_actions.shape != alternate_actions.shape:
        raise TemporalDispatchContractError("baseline and alternate action shapes differ")
    if baseline.reset_frame_indices != alternate.reset_frame_indices:
        raise TemporalDispatchContractError(
            "baseline and alternate must use identical reset boundaries"
        )
    if baseline_actions.shape[1] != metric_contract.action_dim:
        raise TemporalDispatchContractError(
            "metric contract action width disagrees with dispatched actions"
        )
    reference = _finite_array(reference_actions, "reference_actions", ndim=2)
    if reference.shape != baseline_actions.shape:
        raise TemporalDispatchContractError(
            "reference_actions must match dispatched action shape"
        )

    action_delta = alternate_actions - baseline_actions
    active_frames = np.any(
        np.abs(action_delta) > metric_contract.response_threshold[None, :],
        axis=1,
    )
    response_fraction = float(np.mean(active_frames))
    return {
        "schema": SCHEMA,
        "metric_contract": metric_contract.as_dict(),
        "baseline_strategy": baseline.strategy.as_dict(),
        "alternate_strategy": alternate.strategy.as_dict(),
        "reset_frame_indices": [int(value) for value in baseline.reset_frame_indices],
        "response": {
            "active_frame_fraction": response_fraction,
            "active_frame_count": int(np.count_nonzero(active_frames)),
            "frame_count": int(active_frames.shape[0]),
            "active_frame_indices": np.flatnonzero(active_frames).astype(int).tolist(),
            "required_active_frame_fraction": REQUIRED_RESPONSE_ACTIVE_FRACTION,
            "passes_fixed_gate": bool(
                response_fraction >= REQUIRED_RESPONSE_ACTIVE_FRACTION
            ),
            "action_delta_max_abs": float(np.max(np.abs(action_delta))),
        },
        "baseline_action_quality": _action_quality_metrics(
            actions=baseline_actions,
            metric_contract=metric_contract,
            reference_actions=reference,
        ),
        "alternate_action_quality": _action_quality_metrics(
            actions=alternate_actions,
            metric_contract=metric_contract,
            reference_actions=reference,
        ),
        "promotion": {
            "baseline_strategy_promotion_eligible": bool(
                baseline.strategy.promotion_eligible
            ),
            "alternate_strategy_promotion_eligible": bool(
                alternate.strategy.promotion_eligible
            ),
            "alternate_diagnostic_only": bool(alternate.strategy.diagnostic_only),
            "runtime_replacement_decided_here": False,
        },
    }


def _temporal_weights(
    *,
    ages: np.ndarray,
    strategy: TemporalDispatchStrategy,
) -> np.ndarray:
    if strategy.weight_order == _LEGACY_ORDER:
        distance = np.arange(ages.shape[0], dtype=np.float64)
    elif strategy.weight_order == _NEWEST_ORDER:
        distance = ages.astype(np.float64)
    else:  # pragma: no cover - guarded by TemporalDispatchStrategy.
        raise TemporalDispatchContractError("weight_order is invalid for aggregation")
    weights = np.exp(-float(strategy.decay) * distance)
    total = float(np.sum(weights))
    if not math.isfinite(total) or total <= 0.0:
        raise TemporalDispatchContractError("temporal aggregation weights are invalid")
    return weights / total


def _action_quality_metrics(
    *,
    actions: np.ndarray,
    metric_contract: TemporalDispatchMetricContract,
    reference_actions: np.ndarray,
) -> dict[str, Any]:
    absolute = np.abs(actions)
    action_scale = metric_contract.action_scale
    lower = metric_contract.envelope_lower
    upper = metric_contract.envelope_upper
    envelope_violation = (actions < lower[None, :]) | (actions > upper[None, :])
    envelope_frames = np.flatnonzero(np.any(envelope_violation, axis=1))
    reference_delta = np.abs(actions - reference_actions)

    first_difference = np.diff(actions, axis=0)
    abs_first_difference = np.abs(first_difference)
    if first_difference.shape[0] == 0:
        mean_abs = np.zeros(actions.shape[1], dtype=np.float64)
        rms = np.zeros(actions.shape[1], dtype=np.float64)
        max_abs = np.zeros(actions.shape[1], dtype=np.float64)
        discontinuity_mask = np.zeros((0, actions.shape[1]), dtype=bool)
    else:
        mean_abs = np.mean(abs_first_difference, axis=0)
        rms = np.sqrt(np.mean(np.square(first_difference), axis=0))
        max_abs = np.max(abs_first_difference, axis=0)
        discontinuity_mask = (
            abs_first_difference > metric_contract.discontinuity_threshold[None, :]
        )
    discontinuity_transitions = np.flatnonzero(
        np.any(discontinuity_mask, axis=1)
    )
    transition_records = [
        {
            "from_frame_index": int(index),
            "to_frame_index": int(index + 1),
            "axis_indices": np.flatnonzero(discontinuity_mask[index])
            .astype(int)
            .tolist(),
        }
        for index in discontinuity_transitions
    ]
    return {
        "action_scale": {
            "mean_abs": _float_list(np.mean(absolute, axis=0)),
            "max_abs": _float_list(np.max(absolute, axis=0)),
            "mean_abs_over_scale": _float_list(
                np.mean(absolute, axis=0) / action_scale
            ),
            "max_abs_over_scale": _float_list(np.max(absolute, axis=0) / action_scale),
        },
        "envelope": {
            "lower": _float_list(lower),
            "upper": _float_list(upper),
            "within_frozen_envelope": bool(not np.any(envelope_violation)),
            "violation_frame_count": int(envelope_frames.shape[0]),
            "violation_frame_indices": envelope_frames.astype(int).tolist(),
            "violation_axis_count": int(np.count_nonzero(envelope_violation)),
        },
        "reference_delta": {
            "mean_abs": float(np.mean(reference_delta)),
            "max_abs": float(np.max(reference_delta)),
            "mean_abs_per_axis": _float_list(np.mean(reference_delta, axis=0)),
            "max_abs_per_axis": _float_list(np.max(reference_delta, axis=0)),
        },
        "first_difference": {
            "mean_abs": _float_list(mean_abs),
            "rms": _float_list(rms),
            "max_abs": _float_list(max_abs),
            "mean_abs_over_action_scale": _float_list(mean_abs / action_scale),
            "max_abs_over_action_scale": _float_list(max_abs / action_scale),
            "jitter_mean_abs_limit": _float_list(metric_contract.jitter_mean_abs_limit),
            "passes_jitter_limit": bool(
                np.all(mean_abs <= metric_contract.jitter_mean_abs_limit)
            ),
            "discontinuity_threshold": _float_list(
                metric_contract.discontinuity_threshold
            ),
            "discontinuity_transition_count": int(
                discontinuity_transitions.shape[0]
            ),
            "discontinuity_transitions": transition_records,
        },
    }


def _trace_actions(trace: TemporalDispatchTrace, label: str) -> np.ndarray:
    if not isinstance(trace, TemporalDispatchTrace):
        raise TemporalDispatchContractError(f"{label} must be a TemporalDispatchTrace")
    values = _finite_array(trace.actions, f"{label}.actions", ndim=2)
    if values.shape[0] != len(trace.contributors):
        raise TemporalDispatchContractError(
            f"{label} action rows and contributor rows differ"
        )
    return values


def _normalise_reset_frame_indices(
    values: tuple[int, ...] | list[int] | None,
    frame_count: int,
) -> tuple[int, ...]:
    if values is None:
        return (0,)
    if isinstance(values, (str, bytes)):
        raise TemporalDispatchContractError("reset_frame_indices must be integers")
    result: list[int] = []
    for value in values:
        _nonnegative_int(value, "reset_frame_index")
        if value >= frame_count:
            raise TemporalDispatchContractError("reset_frame_index is outside chunks")
        result.append(int(value))
    if not result or result[0] != 0:
        raise TemporalDispatchContractError("reset_frame_indices must include frame 0")
    if result != sorted(set(result)):
        raise TemporalDispatchContractError(
            "reset_frame_indices must be sorted and unique"
        )
    return tuple(result)


def _finite_array(value: Any, label: str, *, ndim: int) -> np.ndarray:
    try:
        result = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise TemporalDispatchContractError(f"{label} must be numeric") from exc
    if result.ndim != ndim or not np.all(np.isfinite(result)):
        raise TemporalDispatchContractError(f"{label} must be a finite {ndim}D array")
    return result


def _finite_vector(value: Any, label: str) -> np.ndarray:
    result = _finite_array(value, label, ndim=1)
    if result.shape[0] < 1:
        raise TemporalDispatchContractError(f"{label} must not be empty")
    return result


def _positive_int(value: Any, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise TemporalDispatchContractError(f"{label} must be a positive integer")


def _nonnegative_int(value: Any, label: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TemporalDispatchContractError(f"{label} must be a non-negative integer")


def _float_list(value: np.ndarray) -> list[float]:
    return [float(item) for item in np.asarray(value, dtype=np.float64).tolist()]


__all__ = [
    "REQUIRED_RESPONSE_ACTIVE_FRACTION",
    "SCHEMA",
    "TemporalDispatchContractError",
    "TemporalDispatchContributor",
    "TemporalDispatchMetricContract",
    "TemporalDispatchStrategy",
    "TemporalDispatchTrace",
    "evaluate_temporal_dispatch_metrics",
    "pre_registered_temporal_dispatch_strategies",
    "reconstruct_temporal_dispatch",
    "temporal_dispatch_contributors_for_frame",
]
