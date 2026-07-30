"""Fail-closed stable-hold guard for continuous-goal return handoff."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from testbed.data.operator_first_v2_2 import (
    RETURN_START_ENVELOPE_TOKEN_DIM,
)


@dataclass
class ContinuousGoalHandoffGuardState:
    """Mutable consecutive-readiness state for one locked continuous goal."""

    goal_id: str = ""
    hold_count: int = 0
    first_ready_step: int | None = None

    def reset(self, *, goal_id: str = "") -> None:
        self.goal_id = str(goal_id)
        self.hold_count = 0
        self.first_ready_step = None


@dataclass(frozen=True)
class ContinuousGoalHandoffGuardResult:
    """Stable-hold decision with field-level fail-closed diagnostics."""

    ready: bool
    hold_count: int
    first_ready_step: int | None
    violations: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContinuousGoalHandoffGuardService:
    """Require one identity and three consecutive complete handoff frames."""

    hold_steps: int = 3

    def __post_init__(self) -> None:
        if int(self.hold_steps) <= 0:
            raise ValueError("continuous handoff hold_steps must be positive")

    def evaluate(
        self,
        state: ContinuousGoalHandoffGuardState,
        *,
        expected_goal_id: str,
        envelope_goal_id: str,
        return_step: int,
        token: Any,
        prior_independent_depth_m: float,
        prior_independent_plane_depth_m: float,
        base_ready: bool,
        base_checks: dict[str, Any],
    ) -> ContinuousGoalHandoffGuardResult:
        expected = str(expected_goal_id)
        envelope = str(envelope_goal_id)
        violations: dict[str, Any] = {}

        if not state.goal_id:
            state.goal_id = expected
        if not _valid_sha256(expected) or state.goal_id != expected:
            violations["locked_goal_identity_invalid"] = {
                "state_goal_id": state.goal_id,
                "expected_goal_id": expected,
            }
        if envelope != expected:
            violations["goal_identity_drift"] = {
                "expected_goal_id": expected,
                "envelope_goal_id": envelope,
            }

        token_array = np.asarray(token, dtype=np.float32).reshape(-1)
        if (
            token_array.shape != (RETURN_START_ENVELOPE_TOKEN_DIM,)
            or not bool(np.all(np.isfinite(token_array)))
            or float(token_array[16]) <= 0.5
            or float(token_array[17]) <= 0.5
        ):
            violations["return_envelope_token_invalid"] = {
                "shape": list(token_array.shape),
                "finite": bool(np.all(np.isfinite(token_array))),
            }
        if not (
            np.isfinite(float(prior_independent_depth_m))
            and np.isfinite(float(prior_independent_plane_depth_m))
        ):
            violations["prior_independent_depth_missing"] = {
                "local_depth_m": float(prior_independent_depth_m),
                "plane_depth_m": float(prior_independent_plane_depth_m),
            }

        for name, check in dict(base_checks).items():
            if isinstance(check, dict):
                if not bool(check.get("ok", False)):
                    violations[str(name)] = dict(check)
            elif bool(check):
                violations[str(name)] = check
        if not bool(base_ready) and not violations:
            violations["base_handoff_not_ready"] = True

        if violations:
            state.hold_count = 0
        else:
            state.hold_count += 1
            if (
                state.hold_count >= int(self.hold_steps)
                and state.first_ready_step is None
            ):
                state.first_ready_step = int(return_step)

        ready = bool(
            not violations and state.hold_count >= int(self.hold_steps)
        )
        return ContinuousGoalHandoffGuardResult(
            ready=ready,
            hold_count=int(state.hold_count),
            first_ready_step=state.first_ready_step,
            violations=violations,
        )


def _valid_sha256(value: str) -> bool:
    return bool(
        len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


__all__ = [
    "ContinuousGoalHandoffGuardResult",
    "ContinuousGoalHandoffGuardService",
    "ContinuousGoalHandoffGuardState",
]
