"""Observation-readiness gates used before coverage goal selection."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from testbed.planner.primitive.coverage.config import (
    CoverageFirstPlanPoseStabilityConfig,
)
from testbed.planner.primitive.coverage.state import CoverageRuntimeState


@dataclass(frozen=True)
class CoverageFirstPlanPoseStabilityResult:
    """One readiness decision with explicit timeout diagnostics."""

    ready: bool
    timed_out: bool
    hold_count: int
    wait_count: int
    spike_count: int
    step_delta_m: float


@dataclass(frozen=True)
class CoverageFirstPlanPoseStabilityService:
    """Require a continuous pose window before the first exact-tuple plan."""

    config: CoverageFirstPlanPoseStabilityConfig
    state: CoverageRuntimeState

    def observe(
        self,
        pose_m: Sequence[float] | None,
    ) -> CoverageFirstPlanPoseStabilityResult:
        if not self.config.enabled:
            return self._result(step_delta_m=0.0, ready=True)

        self.state.coverage_first_plan_pose_stability_wait_count += 1
        pose = self._validated_pose(pose_m)
        previous = (
            self.state.coverage_first_plan_pose_stability_last_pose_m
        )
        step_delta_m = float("inf")
        if pose is None:
            self.state.coverage_first_plan_pose_stability_hold_count = 0
            self.state.coverage_first_plan_pose_stability_spike_count += 1
            self.state.coverage_first_plan_pose_stability_last_pose_m = None
        elif previous is None:
            self.state.coverage_first_plan_pose_stability_hold_count = 1
            self.state.coverage_first_plan_pose_stability_last_pose_m = pose
        else:
            step_delta_m = float(
                np.linalg.norm(
                    np.asarray(pose, dtype=np.float64)
                    - np.asarray(previous, dtype=np.float64)
                )
            )
            if step_delta_m <= float(self.config.max_step_delta_m):
                self.state.coverage_first_plan_pose_stability_hold_count += 1
            else:
                self.state.coverage_first_plan_pose_stability_hold_count = 1
                self.state.coverage_first_plan_pose_stability_spike_count += 1
            self.state.coverage_first_plan_pose_stability_last_pose_m = pose

        ready = bool(
            self.state.coverage_first_plan_pose_stability_hold_count
            >= int(self.config.hold_steps)
        )
        timed_out = bool(
            not ready
            and self.state.coverage_first_plan_pose_stability_wait_count
            >= int(self.config.max_wait_steps)
        )
        self.state.coverage_first_plan_pose_stability_ready = ready
        self.state.coverage_first_plan_pose_stability_timed_out = timed_out
        return self._result(
            step_delta_m=step_delta_m,
            ready=ready,
            timed_out=timed_out,
        )

    def debug_fields(self) -> dict[str, object]:
        """Return stable names for rollout and failure diagnosis."""

        pose = self.state.coverage_first_plan_pose_stability_last_pose_m
        return {
            "coverage_first_plan_pose_stability_enabled": bool(
                self.config.enabled
            ),
            "coverage_first_plan_pose_stability_hold_steps": int(
                self.config.hold_steps
            ),
            "coverage_first_plan_pose_stability_max_step_delta_m": float(
                self.config.max_step_delta_m
            ),
            "coverage_first_plan_pose_stability_max_wait_steps": int(
                self.config.max_wait_steps
            ),
            "coverage_first_plan_pose_stability_hold_count": int(
                self.state.coverage_first_plan_pose_stability_hold_count
            ),
            "coverage_first_plan_pose_stability_wait_count": int(
                self.state.coverage_first_plan_pose_stability_wait_count
            ),
            "coverage_first_plan_pose_stability_spike_count": int(
                self.state.coverage_first_plan_pose_stability_spike_count
            ),
            "coverage_first_plan_pose_stability_ready": bool(
                self.state.coverage_first_plan_pose_stability_ready
            ),
            "coverage_first_plan_pose_stability_timed_out": bool(
                self.state.coverage_first_plan_pose_stability_timed_out
            ),
            "coverage_first_plan_pose_stability_last_pose_m": (
                None if pose is None else [float(value) for value in pose]
            ),
        }

    def _result(
        self,
        *,
        step_delta_m: float,
        ready: bool | None = None,
        timed_out: bool | None = None,
    ) -> CoverageFirstPlanPoseStabilityResult:
        return CoverageFirstPlanPoseStabilityResult(
            ready=bool(
                self.state.coverage_first_plan_pose_stability_ready
                if ready is None
                else ready
            ),
            timed_out=bool(
                self.state.coverage_first_plan_pose_stability_timed_out
                if timed_out is None
                else timed_out
            ),
            hold_count=int(
                self.state.coverage_first_plan_pose_stability_hold_count
            ),
            wait_count=int(
                self.state.coverage_first_plan_pose_stability_wait_count
            ),
            spike_count=int(
                self.state.coverage_first_plan_pose_stability_spike_count
            ),
            step_delta_m=float(step_delta_m),
        )

    @staticmethod
    def _validated_pose(
        pose_m: Sequence[float] | None,
    ) -> tuple[float, float, float] | None:
        if pose_m is None:
            return None
        values = np.asarray(pose_m, dtype=np.float64).reshape(-1)
        if values.size != 3 or not np.all(np.isfinite(values)):
            return None
        return tuple(float(value) for value in values)


__all__ = [
    "CoverageFirstPlanPoseStabilityResult",
    "CoverageFirstPlanPoseStabilityService",
]
