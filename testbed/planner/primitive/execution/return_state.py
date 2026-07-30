"""Mutable primitive return runtime state owner."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class PrimitiveReturnReportStatus:
    """Projected return runtime/config facts for reports and summaries."""

    return_to_dig_entry_error_m: float
    return_to_dig_entry_close: bool
    return_next_dig_event_seen: bool
    return_to_dig_start_envelope_gate_enabled: bool
    return_to_dig_start_envelope_direct_handoff_enabled: bool
    return_to_dig_start_envelope_ready: bool
    return_to_dig_start_envelope_plane_depth_mode: str
    return_to_dig_start_envelope_local_depth_tolerance_m: float
    return_to_dig_start_envelope_error: float
    return_to_dig_start_envelope_checks: dict[str, Any]

    def debug_fields(self) -> dict[str, Any]:
        """Return the public debug report field projection."""

        return {
            "return_to_dig_entry_error_m": float(
                self.return_to_dig_entry_error_m
            ),
            "return_to_dig_entry_close": bool(self.return_to_dig_entry_close),
            "return_next_dig_event_seen": bool(self.return_next_dig_event_seen),
            "return_to_dig_start_envelope_gate_enabled": bool(
                self.return_to_dig_start_envelope_gate_enabled
            ),
            "return_to_dig_start_envelope_direct_handoff_enabled": bool(
                self.return_to_dig_start_envelope_direct_handoff_enabled
            ),
            "return_to_dig_start_envelope_ready": bool(
                self.return_to_dig_start_envelope_ready
            ),
            "return_to_dig_start_envelope_plane_depth_mode": str(
                self.return_to_dig_start_envelope_plane_depth_mode
            ),
            "return_to_dig_start_envelope_local_depth_tolerance_m": float(
                self.return_to_dig_start_envelope_local_depth_tolerance_m
            ),
            "return_to_dig_start_envelope_error": float(
                self.return_to_dig_start_envelope_error
            ),
            "return_to_dig_start_envelope_checks": dict(
                self.return_to_dig_start_envelope_checks
            ),
        }


@dataclass
class PrimitiveReturnRuntimeState:
    """Own mutable return handoff/cache runtime state."""

    return_step_count: int = 0
    return_to_dig_entry_error_m: float = field(default_factory=lambda: float("nan"))
    return_to_dig_entry_close_state: bool = True
    return_to_dig_entry_evaluated_state: bool = False
    return_next_dig_event_seen: bool = False
    return_to_dig_start_envelope_ready_state: bool = True
    return_to_dig_start_envelope_error: float = field(
        default_factory=lambda: float("nan")
    )
    return_to_dig_start_envelope_checks: dict[str, Any] = field(default_factory=dict)
    continuous_goal_handoff_cycle_id: int = -1
    continuous_goal_handoff_goal_id: str = ""
    continuous_goal_handoff_hold_count: int = 0
    continuous_goal_handoff_first_ready_step: int | None = None

    @classmethod
    def fresh(cls) -> PrimitiveReturnRuntimeState:
        """Return a fresh return runtime state matching reset defaults."""

        return cls()

    def mark_next_dig_event_seen(self) -> None:
        self.return_next_dig_event_seen = True

    def clear_next_dig_event_seen(self) -> None:
        self.return_next_dig_event_seen = False

    def to_report_status(
        self,
        *,
        start_envelope_gate_enabled: bool,
        start_envelope_direct_handoff_enabled: bool,
        start_envelope_plane_depth_mode: str,
        start_envelope_local_depth_tolerance_m: float,
    ) -> PrimitiveReturnReportStatus:
        """Project live return runtime state plus config facts for reporting."""

        return PrimitiveReturnReportStatus(
            return_to_dig_entry_error_m=float(self.return_to_dig_entry_error_m),
            return_to_dig_entry_close=bool(self.return_to_dig_entry_close_state),
            return_next_dig_event_seen=bool(self.return_next_dig_event_seen),
            return_to_dig_start_envelope_gate_enabled=bool(
                start_envelope_gate_enabled
            ),
            return_to_dig_start_envelope_direct_handoff_enabled=bool(
                start_envelope_direct_handoff_enabled
            ),
            return_to_dig_start_envelope_ready=bool(
                self.return_to_dig_start_envelope_ready_state
            ),
            return_to_dig_start_envelope_plane_depth_mode=str(
                start_envelope_plane_depth_mode
            ),
            return_to_dig_start_envelope_local_depth_tolerance_m=float(
                start_envelope_local_depth_tolerance_m
            ),
            return_to_dig_start_envelope_error=float(
                self.return_to_dig_start_envelope_error
            ),
            return_to_dig_start_envelope_checks=dict(
                self.return_to_dig_start_envelope_checks
            ),
        )

    def apply_start_envelope_gate_result(
        self,
        *,
        ready: bool,
        error: float,
        checks: dict[str, Any],
    ) -> None:
        self.return_to_dig_start_envelope_ready_state = bool(ready)
        self.return_to_dig_start_envelope_error = float(error)
        self.return_to_dig_start_envelope_checks = dict(checks)

    def set_entry_close_result(
        self,
        *,
        error_m: float,
        close: bool,
    ) -> None:
        self.return_to_dig_entry_error_m = float(error_m)
        self.return_to_dig_entry_close_state = bool(close)
        self.return_to_dig_entry_evaluated_state = True

    def reset_continuous_goal_handoff(
        self,
        *,
        cycle_id: int,
        goal_id: str,
    ) -> None:
        self.continuous_goal_handoff_cycle_id = int(cycle_id)
        self.continuous_goal_handoff_goal_id = str(goal_id)
        self.continuous_goal_handoff_hold_count = 0
        self.continuous_goal_handoff_first_ready_step = None

    def apply_continuous_goal_handoff_result(
        self,
        *,
        goal_id: str,
        hold_count: int,
        first_ready_step: int | None,
    ) -> None:
        self.continuous_goal_handoff_goal_id = str(goal_id)
        self.continuous_goal_handoff_hold_count = int(hold_count)
        self.continuous_goal_handoff_first_ready_step = (
            None if first_ready_step is None else int(first_ready_step)
        )


__all__ = ["PrimitiveReturnReportStatus", "PrimitiveReturnRuntimeState"]
