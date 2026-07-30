"""Mutable primitive cell-entry compatibility runtime state owner."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from testbed.planner.cell_entry import CELL_ENTRY_TOKEN_DIM


@dataclass(frozen=True)
class PrimitiveCellEntryReportConfig:
    enabled: bool


@dataclass(frozen=True)
class PrimitiveCellEntryReportStatus:
    enabled: bool
    trace: list[dict[str, Any]]
    selected_cell_id: int
    selected_long_index: int
    selected_short_index: int
    planned_entry_x_m: float
    planned_entry_y_m: float
    planned_entry_z_m: float
    planner_ok: bool
    audit_reason_code: int
    audit_reason: str
    audit_risk_flags: int
    inside_entry_envelope: bool
    distance_to_entry_envelope_m: float
    seen_cell_id: int

    @property
    def trace_count(self) -> int:
        return int(len(self.trace))

    def trace_for_planner_trace(self) -> list[dict[str, Any]]:
        return list(self.trace)

    def debug_fields(self) -> dict[str, Any]:
        return {
            "cell_entry_selected_cell_id": int(self.selected_cell_id),
            "cell_entry_selected_long_index": int(self.selected_long_index),
            "cell_entry_selected_short_index": int(self.selected_short_index),
            "cell_entry_planned_entry_x_m": float(self.planned_entry_x_m),
            "cell_entry_planned_entry_y_m": float(self.planned_entry_y_m),
            "cell_entry_planned_entry_z_m": float(self.planned_entry_z_m),
            "cell_entry_planner_ok": bool(self.planner_ok),
            "cell_entry_audit_reason_code": int(self.audit_reason_code),
            "cell_entry_audit_reason": str(self.audit_reason),
            "cell_entry_audit_risk_flags": int(self.audit_risk_flags),
            "cell_entry_inside_entry_envelope": bool(
                self.inside_entry_envelope
            ),
            "cell_entry_distance_to_entry_envelope_m": float(
                self.distance_to_entry_envelope_m
            ),
            "cell_entry_seen_cell_id": int(self.seen_cell_id),
        }


@dataclass
class PrimitiveCellEntryCompatibilityRuntimeState:
    """Own parked cell-entry compatibility/report mutable storage."""

    goal: Any | None = None
    goal_cycle_id: int = -1
    audit: Any | None = None
    tokens: np.ndarray = field(
        default_factory=lambda: np.zeros(CELL_ENTRY_TOKEN_DIM, dtype=np.float32)
    )
    seen_cell_id: int = -1
    trace: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def fresh(cls) -> PrimitiveCellEntryCompatibilityRuntimeState:
        """Return reset-default cell-entry compatibility storage."""

        return cls()

    def copy_tokens(self) -> np.ndarray:
        return self.tokens.copy()

    def to_report_status(
        self,
        config: PrimitiveCellEntryReportConfig,
    ) -> PrimitiveCellEntryReportStatus:
        goal = self.goal
        audit = self.audit
        return PrimitiveCellEntryReportStatus(
            enabled=bool(config.enabled),
            trace=list(self.trace),
            selected_cell_id=int(-1 if goal is None else goal.selected_cell_id),
            selected_long_index=int(
                -1 if goal is None else goal.selected_long_index
            ),
            selected_short_index=int(
                -1 if goal is None else goal.selected_short_index
            ),
            planned_entry_x_m=float(
                np.nan if goal is None else goal.planned_entry_x_m
            ),
            planned_entry_y_m=float(
                np.nan if goal is None else goal.planned_entry_y_m
            ),
            planned_entry_z_m=float(
                np.nan if goal is None else goal.planned_entry_z_m
            ),
            planner_ok=bool(False if audit is None else audit.planner_ok),
            audit_reason_code=int(-1 if audit is None else audit.reason_code),
            audit_reason=str("" if audit is None else audit.reason),
            audit_risk_flags=int(0 if audit is None else audit.risk_flags),
            inside_entry_envelope=bool(
                False if audit is None else audit.inside_entry_envelope
            ),
            distance_to_entry_envelope_m=float(
                np.nan if audit is None else audit.distance_to_entry_envelope_m
            ),
            seen_cell_id=int(self.seen_cell_id),
        )

    def debug_fields(self) -> dict[str, Any]:
        """Return the public cell-entry debug field projection."""

        return self.to_report_status(
            PrimitiveCellEntryReportConfig(enabled=False)
        ).debug_fields()


__all__ = [
    "PrimitiveCellEntryCompatibilityRuntimeState",
    "PrimitiveCellEntryReportConfig",
    "PrimitiveCellEntryReportStatus",
]
