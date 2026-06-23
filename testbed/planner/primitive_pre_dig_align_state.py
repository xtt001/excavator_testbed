"""Mutable primitive pre-dig-align compatibility runtime state owner."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


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


__all__ = ["PrimitivePreDigAlignCompatibilityRuntimeState"]
