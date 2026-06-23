"""Requested-effect application for primitive planner shell mutations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from testbed.planner.primitive_decision import (
    CompleteCoverageDigEffect,
    CompleteCoverageDumpEffect,
    CompleteReturnTransitionEffect,
    IncrementDigBadReplanCountEffect,
    IncrementDigExitGuardReplanCountEffect,
    MarkReturnNextDigEventSeenEffect,
    PrimitiveDecisionContractError,
    RejectActiveCoverageCorridorEffect,
    RequestedPlannerEffect,
    RestartAfterFailedDigEffect,
    SetDumpDoneHoldCountEffect,
    SetDumpReadyHoldCountEffect,
    SetDumpStartDepositedMassFromObservationEffect,
    SetReturnOrDirectHandoffEffect,
    SwitchSkillEffect,
    SwitchToNextSkillAfterReturnEffect,
)
from testbed.planner.primitive_cycle_state import PrimitiveCycleRuntimeState
from testbed.planner.primitive_capabilities import PrimitiveObservationFacts
from testbed.planner.primitive_return_state import PrimitiveReturnRuntimeState


@dataclass(frozen=True)
class RequestedEffectApplierPorts:
    """Shell-owned mutation ports used by the requested-effect applier."""

    cycle_state: PrimitiveCycleRuntimeState
    return_state: PrimitiveReturnRuntimeState
    set_skill: Callable[[str, str], None]
    next_skill_after_return_transition: Callable[[], str]
    reject_active_coverage_corridor: Callable[..., None]
    restart_after_failed_dig: Callable[[str, dict[str, Any]], None]
    complete_coverage_dig: Callable[[dict[str, Any]], None]
    observation_facts: Callable[[dict[str, Any]], PrimitiveObservationFacts]
    complete_coverage_dump: Callable[..., None]
    set_return_or_direct_handoff: Callable[..., None]


@dataclass(frozen=True)
class RequestedEffectApplier:
    """Apply ordered requested effects through explicit shell mutation ports."""

    ports: RequestedEffectApplierPorts

    @classmethod
    def from_ports(
        cls,
        ports: RequestedEffectApplierPorts,
    ) -> "RequestedEffectApplier":
        return cls(ports=ports)

    def apply(
        self,
        obs: dict[str, Any],
        effects: tuple[RequestedPlannerEffect, ...],
    ) -> None:
        if not effects:
            return
        for effect in effects:
            self._apply_one(obs, effect)

    def _apply_one(
        self,
        obs: dict[str, Any],
        effect: RequestedPlannerEffect,
    ) -> None:
        ports = self.ports
        if isinstance(effect, SwitchSkillEffect):
            target_skill = str(effect.target_skill_name)
            switch_reason = str(effect.switch_reason)
            if not target_skill.strip() or not switch_reason.strip():
                raise PrimitiveDecisionContractError(
                    "SwitchSkill effect requires non-empty skill and reason"
                )
            ports.set_skill(target_skill, switch_reason)
        elif isinstance(effect, MarkReturnNextDigEventSeenEffect):
            ports.return_state.mark_next_dig_event_seen()
        elif isinstance(effect, CompleteReturnTransitionEffect):
            ports.cycle_state.complete_return_transition()
        elif isinstance(effect, SwitchToNextSkillAfterReturnEffect):
            reason_suffix = str(effect.reason_suffix)
            if not reason_suffix.strip():
                raise PrimitiveDecisionContractError(
                    "SwitchToNextSkillAfterReturn effect requires non-empty "
                    "reason suffix"
                )
            next_skill = str(ports.next_skill_after_return_transition())
            ports.set_skill(
                next_skill,
                f"return_to_{next_skill}_{reason_suffix}",
            )
        elif isinstance(effect, IncrementDigExitGuardReplanCountEffect):
            ports.cycle_state.increment_dig_exit_guard_replan_count()
        elif isinstance(effect, IncrementDigBadReplanCountEffect):
            ports.cycle_state.increment_dig_bad_replan_count()
        elif isinstance(effect, RejectActiveCoverageCorridorEffect):
            reason = str(effect.reason)
            if not reason.strip():
                raise PrimitiveDecisionContractError(
                    "RejectActiveCoverageCorridor effect requires non-empty "
                    "reason"
                )
            ports.reject_active_coverage_corridor(obs, reason=reason)
        elif isinstance(effect, RestartAfterFailedDigEffect):
            reason = str(effect.reason)
            if not reason.strip():
                raise PrimitiveDecisionContractError(
                    "RestartAfterFailedDig effect requires non-empty reason"
                )
            ports.restart_after_failed_dig(reason, obs)
        elif isinstance(effect, CompleteCoverageDigEffect):
            ports.complete_coverage_dig(obs)
        elif isinstance(effect, SetDumpReadyHoldCountEffect):
            ports.cycle_state.set_dump_ready_hold_count(int(effect.value))
        elif isinstance(effect, SetDumpStartDepositedMassFromObservationEffect):
            ports.cycle_state.set_dump_start_deposited_mass_kg(
                float(ports.observation_facts(obs).deposited_mass_in_target_box_kg)
            )
        elif isinstance(effect, SetDumpDoneHoldCountEffect):
            ports.cycle_state.set_dump_done_hold_count(int(effect.value))
        elif isinstance(effect, CompleteCoverageDumpEffect):
            reason = str(effect.reason)
            if not reason.strip():
                raise PrimitiveDecisionContractError(
                    "CompleteCoverageDump effect requires non-empty reason"
                )
            ports.complete_coverage_dump(obs, reason=reason)
        elif isinstance(effect, SetReturnOrDirectHandoffEffect):
            reason = str(effect.reason)
            if not reason.strip():
                raise PrimitiveDecisionContractError(
                    "SetReturnOrDirectHandoff effect requires non-empty reason"
                )
            ports.set_return_or_direct_handoff(obs, reason=reason)
        else:
            effect_name = str(effect.effect_type)
            raise PrimitiveDecisionContractError(
                "real planner requested-effect application only supports "
                "SwitchSkill, dig, return-cycle, and carry/dump effects; "
                f"received: {effect_name}"
            )


__all__ = [
    "RequestedEffectApplier",
    "RequestedEffectApplierPorts",
]
