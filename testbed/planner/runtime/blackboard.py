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
    return_step_count: int = 0
    return_next_dig_event_seen: bool = False
    dump_ready_hold_count: int = 0
    dump_done_hold_count: int = 0

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
        object.__setattr__(
            self,
            "return_step_count",
            int(self.return_step_count),
        )
        object.__setattr__(
            self,
            "return_next_dig_event_seen",
            bool(self.return_next_dig_event_seen),
        )
        object.__setattr__(
            self,
            "dump_ready_hold_count",
            int(self.dump_ready_hold_count),
        )
        object.__setattr__(
            self,
            "dump_done_hold_count",
            int(self.dump_done_hold_count),
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

    def with_return_step_increment(self) -> PlannerBlackboard:
        """Return a snapshot after one return-policy tick."""

        return replace(self, return_step_count=self.return_step_count + 1)

    def with_return_step_count(self, count: object) -> PlannerBlackboard:
        """Return a snapshot with an updated return-policy step count."""

        return replace(self, return_step_count=int(count))

    def with_return_next_dig_event_seen(self, seen: object) -> PlannerBlackboard:
        """Return a snapshot with the return-to-dig boundary latch updated."""

        return replace(self, return_next_dig_event_seen=bool(seen))

    def with_dump_ready_hold_count(self, count: object) -> PlannerBlackboard:
        """Return a snapshot with updated carry-to-dump ready hold count."""

        return replace(self, dump_ready_hold_count=int(count))

    def with_dump_done_hold_count(self, count: object) -> PlannerBlackboard:
        """Return a snapshot with updated dump-to-return done hold count."""

        return replace(self, dump_done_hold_count=int(count))
