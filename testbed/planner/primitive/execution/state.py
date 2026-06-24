"""Mutable primitive execution lifecycle runtime state owner."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass
class PrimitiveExecutionRuntimeState:
    """Own active execution metadata shared by tick, reset, and reports."""

    skill_name: str = "dig"
    switch_reason: str = ""
    prev_action: np.ndarray | None = None
    debug_state: Any | None = None

    @classmethod
    def fresh(
        cls,
        *,
        initial_skill_name: str = "dig",
        switch_reason: str = "",
    ) -> "PrimitiveExecutionRuntimeState":
        """Return a fresh execution runtime state matching reset defaults."""

        return cls(
            skill_name=str(initial_skill_name),
            switch_reason=str(switch_reason),
            prev_action=None,
            debug_state=None,
        )

    def set_skill_name(self, value: str) -> None:
        self.skill_name = str(value)

    def set_switch_reason(self, value: str) -> None:
        self.switch_reason = str(value)

    def set_prev_action(self, value: np.ndarray | None) -> None:
        self.prev_action = value

    def set_debug_state(self, value: Any) -> None:
        self.debug_state = value


__all__ = ["PrimitiveExecutionRuntimeState"]
