"""Backend-neutral common decision facts for primitive planner backends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from testbed.planner.primitive.facts.capabilities import (
    CarryTransitionStatus,
    DigTransitionStatus,
    DumpTransitionStatus,
    ReturnTransitionStatus,
)
from testbed.planner.primitive.decision.context import PrimitiveDecisionContext
from testbed.planner.primitive.execution.runtime import PrimitiveTickPreparation


@dataclass(frozen=True)
class PrimitiveDecisionFacts:
    """Read-only common facts shared by primitive decision backends."""

    context: PrimitiveDecisionContext
    current_skill_name: str
    current_switch_reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "current_skill_name", str(self.current_skill_name))
        object.__setattr__(
            self,
            "current_switch_reason",
            str(self.current_switch_reason),
        )

    @classmethod
    def from_context(
        cls,
        context: PrimitiveDecisionContext,
        *,
        current_skill_name: Any,
        current_switch_reason: Any,
    ) -> "PrimitiveDecisionFacts":
        return cls(
            context=context,
            current_skill_name=str(current_skill_name),
            current_switch_reason=str(current_switch_reason),
        )

    @property
    def obs(self) -> dict[str, Any]:
        return self.context.obs

    @property
    def boundary_event(self) -> Any | None:
        return self.context.boundary_event

    @property
    def preparation(self) -> PrimitiveTickPreparation:
        return self.context.preparation

    @property
    def skill_name_before_decision(self) -> str:
        return self.context.skill_name_before_decision

    @property
    def dig_progress_updated(self) -> bool:
        return self.context.dig_progress_updated

    def is_current_skill(self, skill_name: str) -> bool:
        return self.current_skill_name == str(skill_name)


@dataclass(frozen=True)
class PrimitiveDigTransitionFacts:
    """Read-only dig transition view assembled before explicit reason sync."""

    common: PrimitiveDecisionFacts
    status: DigTransitionStatus

    @property
    def context(self) -> PrimitiveDecisionContext:
        return self.common.context

    @property
    def obs(self) -> dict[str, Any]:
        return self.common.obs

    @property
    def boundary_event(self) -> Any | None:
        return self.common.boundary_event

    @property
    def preparation(self) -> PrimitiveTickPreparation:
        return self.common.preparation

    @property
    def current_skill_name(self) -> str:
        return self.common.current_skill_name

    @property
    def skill_name_before_decision(self) -> str:
        return self.common.skill_name_before_decision

    @property
    def dig_to_carry_ready(self) -> bool:
        return bool(self.status.dig_to_carry_ready)

    @property
    def dig_to_carry_reason(self) -> str:
        return str(self.status.dig_to_carry_reason)


@dataclass(frozen=True)
class PrimitiveCarryTransitionFacts:
    """Read-only carry transition view for active-carry decisions."""

    common: PrimitiveDecisionFacts
    status: CarryTransitionStatus

    @property
    def context(self) -> PrimitiveDecisionContext:
        return self.common.context

    @property
    def obs(self) -> dict[str, Any]:
        return self.common.obs

    @property
    def boundary_event(self) -> Any | None:
        return self.common.boundary_event

    @property
    def preparation(self) -> PrimitiveTickPreparation:
        return self.common.preparation

    @property
    def current_skill_name(self) -> str:
        return self.common.current_skill_name

    @property
    def skill_name_before_decision(self) -> str:
        return self.common.skill_name_before_decision

    @property
    def ready_to_dump(self) -> bool:
        return bool(self.status.ready_to_dump)

    @property
    def carry_to_dump_reason(self) -> str:
        return str(self.status.carry_to_dump_reason)

    @property
    def carry_release_safety_done(self) -> bool:
        return bool(self.status.carry_release_safety_done)

    @property
    def dump_complete_event(self) -> bool:
        return bool(self.status.dump_complete_event)

    @property
    def next_dump_ready_hold_count(self) -> int:
        return int(self.status.next_dump_ready_hold_count)


@dataclass(frozen=True)
class PrimitiveDumpTransitionFacts:
    """Read-only dump transition view for active-dump decisions."""

    common: PrimitiveDecisionFacts
    status: DumpTransitionStatus

    @property
    def context(self) -> PrimitiveDecisionContext:
        return self.common.context

    @property
    def obs(self) -> dict[str, Any]:
        return self.common.obs

    @property
    def boundary_event(self) -> Any | None:
        return self.common.boundary_event

    @property
    def preparation(self) -> PrimitiveTickPreparation:
        return self.common.preparation

    @property
    def current_skill_name(self) -> str:
        return self.common.current_skill_name

    @property
    def skill_name_before_decision(self) -> str:
        return self.common.skill_name_before_decision

    @property
    def ready_to_return(self) -> bool:
        return bool(self.status.ready_to_return)

    @property
    def dump_to_return_reason(self) -> str:
        return str(self.status.dump_to_return_reason)

    @property
    def coverage_completion_reason(self) -> str:
        return str(self.status.coverage_completion_reason)

    @property
    def next_dump_done_hold_count(self) -> int:
        return int(self.status.next_dump_done_hold_count)


@dataclass(frozen=True)
class PrimitiveReturnTransitionFacts:
    """Read-only return transition view assembled after explicit refresh."""

    common: PrimitiveDecisionFacts
    status: ReturnTransitionStatus

    @property
    def context(self) -> PrimitiveDecisionContext:
        return self.common.context

    @property
    def obs(self) -> dict[str, Any]:
        return self.common.obs

    @property
    def boundary_event(self) -> Any | None:
        return self.common.boundary_event

    @property
    def preparation(self) -> PrimitiveTickPreparation:
        return self.common.preparation

    @property
    def current_skill_name(self) -> str:
        return self.common.current_skill_name

    @property
    def skill_name_before_decision(self) -> str:
        return self.common.skill_name_before_decision

    @property
    def completed_transition(self) -> bool:
        return bool(self.status.completed_transition)

    @property
    def switch_reason(self) -> str:
        return str(self.status.switch_reason)


__all__ = [
    "PrimitiveCarryTransitionFacts",
    "PrimitiveDecisionFacts",
    "PrimitiveDigTransitionFacts",
    "PrimitiveDumpTransitionFacts",
    "PrimitiveReturnTransitionFacts",
]
