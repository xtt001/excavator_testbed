"""Mutable primitive cell-entry compatibility runtime state owner."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from testbed.planner.cell_entry import CELL_ENTRY_TOKEN_DIM


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
    def fresh(cls) -> "PrimitiveCellEntryCompatibilityRuntimeState":
        """Return reset-default cell-entry compatibility storage."""

        return cls()

    def copy_tokens(self) -> np.ndarray:
        return self.tokens.copy()

    def debug_fields(self) -> dict[str, Any]:
        """Return the public cell-entry debug field projection."""

        goal = self.goal
        audit = self.audit
        return {
            "cell_entry_selected_cell_id": int(
                -1 if goal is None else goal.selected_cell_id
            ),
            "cell_entry_selected_long_index": int(
                -1 if goal is None else goal.selected_long_index
            ),
            "cell_entry_selected_short_index": int(
                -1 if goal is None else goal.selected_short_index
            ),
            "cell_entry_planned_entry_x_m": float(
                np.nan if goal is None else goal.planned_entry_x_m
            ),
            "cell_entry_planned_entry_y_m": float(
                np.nan if goal is None else goal.planned_entry_y_m
            ),
            "cell_entry_planned_entry_z_m": float(
                np.nan if goal is None else goal.planned_entry_z_m
            ),
            "cell_entry_planner_ok": bool(
                False if audit is None else audit.planner_ok
            ),
            "cell_entry_audit_reason_code": int(
                -1 if audit is None else audit.reason_code
            ),
            "cell_entry_audit_reason": str(
                "" if audit is None else audit.reason
            ),
            "cell_entry_audit_risk_flags": int(
                0 if audit is None else audit.risk_flags
            ),
            "cell_entry_inside_entry_envelope": bool(
                False if audit is None else audit.inside_entry_envelope
            ),
            "cell_entry_distance_to_entry_envelope_m": float(
                np.nan if audit is None else audit.distance_to_entry_envelope_m
            ),
            "cell_entry_seen_cell_id": int(self.seen_cell_id),
        }


__all__ = ["PrimitiveCellEntryCompatibilityRuntimeState"]
