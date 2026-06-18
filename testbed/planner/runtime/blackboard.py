"""Typed runtime blackboard state for planner backend ticks."""

from __future__ import annotations

from dataclasses import dataclass, replace


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

    def with_skill(
        self,
        skill_name: object,
        switch_reason: object,
    ) -> PlannerBlackboard:
        """Return a blackboard snapshot after switching active skill."""

        return replace(
            self,
            current_skill=str(skill_name),
            switch_reason=str(switch_reason),
        )

    def with_switch_reason(self, reason: object) -> PlannerBlackboard:
        """Return a blackboard snapshot with an updated switch reason."""

        return replace(self, switch_reason=str(reason))

    def with_transition_timeout_increment(self) -> PlannerBlackboard:
        """Return a blackboard snapshot after recording one timeout."""

        return replace(
            self,
            transition_timeout_count=self.transition_timeout_count + 1,
        )

    def with_return_transition_counts(
        self,
        *,
        completed_increment: object,
        cycle_increment: object,
    ) -> PlannerBlackboard:
        """Return a snapshot after applying return-to-dig transition counters."""

        return replace(
            self,
            completed_transition_count=(
                self.completed_transition_count + int(completed_increment)
            ),
            cycle_index=self.cycle_index + int(cycle_increment),
        )
