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


__all__ = ["PrimitiveCellEntryCompatibilityRuntimeState"]
