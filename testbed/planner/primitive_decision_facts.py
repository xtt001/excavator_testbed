"""Backend-neutral common decision facts for primitive planner backends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from testbed.planner.primitive_capabilities import ReturnTransitionStatus
from testbed.planner.primitive_decision_context import PrimitiveDecisionContext
from testbed.planner.primitive_execution import PrimitiveTickPreparation


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


__all__ = ["PrimitiveDecisionFacts", "PrimitiveReturnTransitionFacts"]
