"""Mutable primitive pre-dig-align compatibility runtime state owner."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass(frozen=True)
class PrimitivePreDigAlignReportConfig:
    enabled: bool
    first_dig_only: bool
    replan_after_failed_dig: bool
    entry_intent_controlled_dims: Any | None
    surface_guard_enabled: bool
    active_for_next_dig: bool
    first_dig_entry_close_handoff: bool
    entry_intent_handoff_enabled: bool
    first_dig_entry_close_handoff_qvel_abs_max: float | None
    controlled_dims: Any
    bucket_target_qpos: float | None


@dataclass(frozen=True)
class PrimitivePreDigAlignReportStatus:
    enabled: bool
    first_dig_only: bool
    replan_after_failed_dig: bool
    entry_intent_controlled_dims: list[int] | None
    surface_guard_enabled: bool
    surface_depth_m: float
    surface_guard_triggered: bool
    surface_guard_count: int
    active_for_next_dig: bool
    step_count: int
    hold_count: int
    timeout_count: int
    completed_count: int
    replan_count: int
    target_qpos: list[float]
    error: list[float]
    entry_error_m: float
    start_envelope_ready: bool
    first_dig_entry_close_handoff: bool
    entry_close_handoff_ready: bool
    entry_intent_handoff_enabled: bool
    entry_intent_handoff_ready: bool
    first_dig_entry_close_handoff_qvel_abs_max: float
    controlled_dims: list[int]
    bucket_target_qpos: float

    def debug_fields(self) -> dict[str, Any]:
        return {
            "pre_dig_align_enabled": bool(self.enabled),
            "pre_dig_align_first_dig_only": bool(self.first_dig_only),
            "pre_dig_align_replan_after_failed_dig": bool(
                self.replan_after_failed_dig
            ),
            "pre_dig_align_entry_intent_controlled_dims": (
                None
                if self.entry_intent_controlled_dims is None
                else list(self.entry_intent_controlled_dims)
            ),
            "pre_dig_align_surface_guard_enabled": bool(
                self.surface_guard_enabled
            ),
            "pre_dig_align_surface_depth_m": float(self.surface_depth_m),
            "pre_dig_align_surface_guard_triggered": bool(
                self.surface_guard_triggered
            ),
            "pre_dig_align_surface_guard_count": int(self.surface_guard_count),
            "pre_dig_align_active_for_next_dig": bool(self.active_for_next_dig),
            "pre_dig_align_step_count": int(self.step_count),
            "pre_dig_align_hold_count": int(self.hold_count),
            "pre_dig_align_timeout_count": int(self.timeout_count),
            "pre_dig_align_completed_count": int(self.completed_count),
            "pre_dig_align_replan_count": int(self.replan_count),
            "pre_dig_align_target_qpos": list(self.target_qpos),
            "pre_dig_align_error": list(self.error),
            "pre_dig_align_entry_error_m": float(self.entry_error_m),
            "pre_dig_align_start_envelope_ready": bool(
                self.start_envelope_ready
            ),
            "pre_dig_align_first_dig_entry_close_handoff": bool(
                self.first_dig_entry_close_handoff
            ),
            "pre_dig_align_entry_close_handoff_ready": bool(
                self.entry_close_handoff_ready
            ),
            "pre_dig_align_entry_intent_handoff_enabled": bool(
                self.entry_intent_handoff_enabled
            ),
            "pre_dig_align_entry_intent_handoff_ready": bool(
                self.entry_intent_handoff_ready
            ),
            "pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max": float(
                self.first_dig_entry_close_handoff_qvel_abs_max
            ),
            "pre_dig_align_controlled_dims": list(self.controlled_dims),
            "pre_dig_align_bucket_target_qpos": float(self.bucket_target_qpos),
        }


@dataclass
class PrimitivePreDigAlignCompatibilityRuntimeState:
    """Own parked pre-dig-align compatibility/report mutable storage."""

    step_count: int = 0
    hold_count: int = 0
    timeout_count: int = 0
    completed_count: int = 0
    replan_count: int = 0
    target_qpos: np.ndarray = field(
        default_factory=lambda: np.zeros(4, dtype=np.float32)
    )
    error: np.ndarray = field(default_factory=lambda: np.zeros(4, dtype=np.float32))
    entry_error_m: float = float("nan")
    start_envelope_ready: bool = False
    entry_close_handoff_ready: bool = False
    entry_intent_handoff_ready: bool = False
    timeout_handoff_reason: str = ""
    surface_depth_m: float = float("nan")
    surface_guard_triggered: bool = False
    surface_guard_count: int = 0

    @classmethod
    def fresh(
        cls,
        *,
        action_dim: int,
    ) -> "PrimitivePreDigAlignCompatibilityRuntimeState":
        """Return reset-default pre-dig-align compatibility storage."""

        return cls(
            target_qpos=np.zeros(int(action_dim), dtype=np.float32),
            error=np.zeros(int(action_dim), dtype=np.float32),
        )

    def to_report_status(
        self,
        config: PrimitivePreDigAlignReportConfig,
    ) -> PrimitivePreDigAlignReportStatus:
        return PrimitivePreDigAlignReportStatus(
            enabled=bool(config.enabled),
            first_dig_only=bool(config.first_dig_only),
            replan_after_failed_dig=bool(config.replan_after_failed_dig),
            entry_intent_controlled_dims=_optional_int_list(
                config.entry_intent_controlled_dims
            ),
            surface_guard_enabled=bool(config.surface_guard_enabled),
            surface_depth_m=float(self.surface_depth_m),
            surface_guard_triggered=bool(self.surface_guard_triggered),
            surface_guard_count=int(self.surface_guard_count),
            active_for_next_dig=bool(config.active_for_next_dig),
            step_count=int(self.step_count),
            hold_count=int(self.hold_count),
            timeout_count=int(self.timeout_count),
            completed_count=int(self.completed_count),
            replan_count=int(self.replan_count),
            target_qpos=np.asarray(self.target_qpos, dtype=float).tolist(),
            error=np.asarray(self.error, dtype=float).tolist(),
            entry_error_m=float(self.entry_error_m),
            start_envelope_ready=bool(self.start_envelope_ready),
            first_dig_entry_close_handoff=bool(
                config.first_dig_entry_close_handoff
            ),
            entry_close_handoff_ready=bool(self.entry_close_handoff_ready),
            entry_intent_handoff_enabled=bool(
                config.entry_intent_handoff_enabled
            ),
            entry_intent_handoff_ready=bool(self.entry_intent_handoff_ready),
            first_dig_entry_close_handoff_qvel_abs_max=float(
                np.nan
                if config.first_dig_entry_close_handoff_qvel_abs_max is None
                else config.first_dig_entry_close_handoff_qvel_abs_max
            ),
            controlled_dims=_int_list(config.controlled_dims),
            bucket_target_qpos=float(
                np.nan
                if config.bucket_target_qpos is None
                else config.bucket_target_qpos
            ),
        )


def _optional_int_list(values: Any | None) -> list[int] | None:
    if values is None:
        return None
    return _int_list(values)


def _int_list(values: Any) -> list[int]:
    return [int(value) for value in np.asarray(values).tolist()]


__all__ = [
    "PrimitivePreDigAlignCompatibilityRuntimeState",
    "PrimitivePreDigAlignReportConfig",
    "PrimitivePreDigAlignReportStatus",
]
