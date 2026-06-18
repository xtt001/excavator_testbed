"""Typed runtime blackboard state for planner backend ticks."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PlannerBlackboard:
    """Minimal typed state snapshot shared with planner backends."""

    current_skill: str = ""
    switch_reason: str = ""
    cycle_index: int = 0
    completed_transition_count: int = 0
    transition_timeout_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "current_skill", str(self.current_skill))
        object.__setattr__(self, "switch_reason", str(self.switch_reason))
        object.__setattr__(self, "cycle_index", int(self.cycle_index))
        object.__setattr__(
            self,
            "completed_transition_count",
            int(self.completed_transition_count),
        )
        object.__setattr__(
            self,
            "transition_timeout_count",
            int(self.transition_timeout_count),
        )
