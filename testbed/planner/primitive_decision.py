"""Typed decision and effect contracts for primitive planner ticks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


LEGACY_FSM_DECISION_SOURCE = "legacy_fsm_side_effects_applied"

PrimitiveDecisionStatus = Literal["no_change", "skill_switch"]


@dataclass(frozen=True)
class PlannerEffect:
    """Minimal effect record; Phase 3 records only already-applied outcomes."""

    effect_type: str
    already_applied: bool


@dataclass(frozen=True)
class LegacyDecisionOutcomeEffect(PlannerEffect):
    """Observable outcome emitted by the legacy FSM after it already mutated state."""

    skill_before: str
    skill_after: str
    switch_reason: str


@dataclass(frozen=True)
class PrimitiveDecisionResult:
    """Decision result returned to the public tick template."""

    decision_source: str
    status: PrimitiveDecisionStatus
    skill_before: str
    skill_after: str
    switch_reason: str
    effects: tuple[PlannerEffect, ...]
    side_effects_applied: bool

    @classmethod
    def from_legacy_fsm_outcome(
        cls,
        *,
        skill_before: str,
        skill_after: str,
        switch_reason: str,
    ) -> "PrimitiveDecisionResult":
        status: PrimitiveDecisionStatus = (
            "skill_switch" if skill_after != skill_before else "no_change"
        )
        effects: tuple[PlannerEffect, ...]
        if skill_after != skill_before:
            effects = (
                LegacyDecisionOutcomeEffect(
                    effect_type="legacy_decision_outcome",
                    already_applied=True,
                    skill_before=str(skill_before),
                    skill_after=str(skill_after),
                    switch_reason=str(switch_reason),
                ),
            )
        else:
            effects = ()
        return cls(
            decision_source=LEGACY_FSM_DECISION_SOURCE,
            status=status,
            skill_before=str(skill_before),
            skill_after=str(skill_after),
            switch_reason=str(switch_reason),
            effects=effects,
            side_effects_applied=True,
        )
