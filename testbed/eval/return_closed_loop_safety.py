"""Fail-closed safety boundary for bounded Return-only experiments."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.data.schema import (
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_STEP_MAX_FORCE_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_STEP_MAX_FORCE_IDX,
    ENV_STATE_HARD_COLLISION_COUNT_IDX,
    ENV_STATE_TARGET_CONTACT_MAX_NORMAL_FORCE_N_IDX,
    ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX,
    ENV_STATE_V2_4_DIM,
)
from testbed.planner.box_emptying.safety_contracts import (
    SafetyActionDecision,
    SafetyInterlockConfig,
)
from testbed.planner.box_emptying.safety_interlock import (
    BoxEmptyingSafetyInterlock,
)

RETURN_ACTION_DIM = 4
CONTACT_FORCE_LIMIT_N = 100_000.0


@dataclass(frozen=True)
class ReturnProbeSafetyDecision:
    """Narrow JSON-friendly projection of the production safety decision."""

    action: np.ndarray
    reason: str = ""
    terminal: bool = False
    replan: bool = False
    awaiting_neutral_ack: bool = False
    neutral_acknowledged: bool = False

    def __post_init__(self) -> None:
        action = np.asarray(self.action, dtype=np.float32).reshape(-1)
        if action.shape != (RETURN_ACTION_DIM,):
            raise ValueError("Return safety action must be 4D")
        object.__setattr__(self, "action", action)

    def as_dict(self) -> dict[str, Any]:
        return {
            "reason": self.reason,
            "terminal": bool(self.terminal),
            "replan": bool(self.replan),
            "awaiting_neutral_ack": bool(self.awaiting_neutral_ack),
            "neutral_acknowledged": bool(self.neutral_acknowledged),
        }


class ReturnClosedLoopSafetyAdapter:
    """Add strict Return-only stops around ``BoxEmptyingSafetyInterlock``."""

    def __init__(
        self,
        *,
        interlock: BoxEmptyingSafetyInterlock | None = None,
        contact_force_limit_n: float = CONTACT_FORCE_LIMIT_N,
    ) -> None:
        self._force_limit = float(contact_force_limit_n)
        if not math.isfinite(self._force_limit) or self._force_limit <= 0.0:
            raise ValueError("contact_force_limit_n must be finite and positive")
        self._interlock = interlock or BoxEmptyingSafetyInterlock(
            SafetyInterlockConfig(
                action_dim=RETURN_ACTION_DIM,
                wall_high_force_n=self._force_limit,
            )
        )

    def reset(self) -> None:
        self._interlock.reset()

    def filter_action(
        self,
        obs: dict[str, Any],
        proposed_action: Any,
        **_: Any,
    ) -> ReturnProbeSafetyDecision:
        try:
            action = np.asarray(proposed_action, dtype=np.float32).reshape(-1)
        except Exception:
            return self._terminal("invalid_policy_action")
        if action.shape != (RETURN_ACTION_DIM,):
            return self._terminal("invalid_policy_action")
        if not np.isfinite(action).all():
            return self._terminal("nonfinite_policy_action")

        try:
            qpos = np.asarray(obs.get("qpos"), dtype=np.float64).reshape(-1)
            qvel = np.asarray(obs.get("qvel"), dtype=np.float64).reshape(-1)
            env_state = np.asarray(
                obs.get("env_state"), dtype=np.float64
            ).reshape(-1)
        except Exception:
            return self._terminal("invalid_observation")
        if (
            qpos.shape != (RETURN_ACTION_DIM,)
            or qvel.shape != (RETURN_ACTION_DIM,)
            or env_state.size < ENV_STATE_V2_4_DIM
        ):
            return self._terminal("invalid_observation")
        if not (
            np.isfinite(qpos).all()
            and np.isfinite(qvel).all()
            and np.isfinite(env_state[:ENV_STATE_V2_4_DIM]).all()
        ):
            return self._terminal("nonfinite_observation")

        collision_counts = (
            env_state[ENV_STATE_TARGET_HARD_COLLISION_COUNT_IDX],
            env_state[ENV_STATE_HARD_COLLISION_COUNT_IDX],
        )
        if any(float(value) >= 0.5 for value in collision_counts):
            return self._terminal("hard_collision")
        forces = (
            env_state[ENV_STATE_TARGET_CONTACT_MAX_NORMAL_FORCE_N_IDX],
            env_state[ENV_STATE_EXCAVATOR_WALL_CONTACT_STEP_MAX_FORCE_IDX],
            env_state[
                ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_STEP_MAX_FORCE_IDX
            ],
        )
        if any(float(value) >= self._force_limit for value in forces):
            return self._terminal("contact_force_at_or_above_limit")

        try:
            decision = self._interlock.filter_action(
                dict(obs),
                action,
                active_cell_id=-1,
                active_corridor_id=-1,
                skill_name="return",
            )
        except Exception:
            return self._terminal("safety_interlock_error")
        projected = project_return_probe_safety_decision(decision)
        if projected.replan:
            return self._terminal(
                f"return_only_replan_blocked:{projected.reason or 'unspecified'}"
            )
        if projected.terminal:
            return ReturnProbeSafetyDecision(
                action=np.zeros(RETURN_ACTION_DIM, dtype=np.float32),
                reason=projected.reason or "safety_terminal",
                terminal=True,
                awaiting_neutral_ack=projected.awaiting_neutral_ack,
                neutral_acknowledged=projected.neutral_acknowledged,
            )
        if not np.isfinite(projected.action).all():
            return self._terminal("nonfinite_safety_action")
        return projected

    @staticmethod
    def _terminal(reason: str) -> ReturnProbeSafetyDecision:
        return ReturnProbeSafetyDecision(
            action=np.zeros(RETURN_ACTION_DIM, dtype=np.float32),
            reason=str(reason),
            terminal=True,
            awaiting_neutral_ack=True,
        )


def project_return_probe_safety_decision(
    value: Any,
) -> ReturnProbeSafetyDecision:
    """Project an injected or production decision onto the probe boundary."""

    if isinstance(value, ReturnProbeSafetyDecision):
        return value
    if isinstance(value, SafetyActionDecision):
        source = {
            "action": value.action,
            "reason": value.reason,
            "terminal": value.terminal,
            "replan": value.replan,
            "awaiting_neutral_ack": value.awaiting_neutral_ack,
            "neutral_acknowledged": value.neutral_acknowledged,
        }
    elif isinstance(value, dict):
        source = value
    else:
        fields = (
            "action",
            "reason",
            "terminal",
            "replan",
            "awaiting_neutral_ack",
            "neutral_acknowledged",
        )
        source = {
            field: getattr(value, field)
            for field in fields
            if hasattr(value, field)
        }
    return ReturnProbeSafetyDecision(
        action=np.asarray(source.get("action"), dtype=np.float32),
        reason=str(source.get("reason", "")),
        terminal=bool(source.get("terminal", False)),
        replan=bool(source.get("replan", False)),
        awaiting_neutral_ack=bool(source.get("awaiting_neutral_ack", False)),
        neutral_acknowledged=bool(source.get("neutral_acknowledged", False)),
    )


__all__ = [
    "CONTACT_FORCE_LIMIT_N",
    "RETURN_ACTION_DIM",
    "ReturnClosedLoopSafetyAdapter",
    "ReturnProbeSafetyDecision",
    "project_return_probe_safety_decision",
]
