"""Decision backend protocol and legacy FSM adapter for primitive planning."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from testbed.planner.primitive_capabilities import (
    CarryTransitionStatus,
    DumpTransitionStatus,
    ReturnTransitionStatus,
)
from testbed.planner.primitive_decision import PrimitiveDecisionContractError
from testbed.planner.primitive_decision import PrimitiveDecisionResult
from testbed.planner.primitive_decision import CompleteCellEntryDigCompatibilityEffect
from testbed.planner.primitive_decision import CompleteCoverageDigEffect
from testbed.planner.primitive_decision import CompleteCoverageDumpEffect
from testbed.planner.primitive_decision import CompleteReturnTransitionEffect
from testbed.planner.primitive_decision import IncrementDigBadReplanCountEffect
from testbed.planner.primitive_decision import (
    IncrementDigExitGuardReplanCountEffect,
)
from testbed.planner.primitive_decision import MarkReturnNextDigEventSeenEffect
from testbed.planner.primitive_decision import RejectActiveCoverageCorridorEffect
from testbed.planner.primitive_decision import RestartAfterFailedDigEffect
from testbed.planner.primitive_decision import SetDumpDoneHoldCountEffect
from testbed.planner.primitive_decision import SetDumpReadyHoldCountEffect
from testbed.planner.primitive_decision import (
    SetDumpStartDepositedMassFromObservationEffect,
)
from testbed.planner.primitive_decision import SetReturnOrDirectHandoffEffect
from testbed.planner.primitive_decision import SwitchSkillEffect
from testbed.planner.primitive_decision import SwitchToNextSkillAfterReturnEffect
from testbed.planner.primitive_execution import PrimitiveTickPreparation


BOOTSTRAP_REQUESTED_DECISION_SOURCE = "legacy_fsm_bootstrap_requested_effect"
DIG_REQUESTED_DECISION_SOURCE = "legacy_fsm_dig_requested_effect"
CARRY_REQUESTED_DECISION_SOURCE = "legacy_fsm_carry_requested_effect"
DUMP_REQUESTED_DECISION_SOURCE = "legacy_fsm_dump_requested_effect"
RETURN_REQUESTED_DECISION_SOURCE = "legacy_fsm_return_requested_effect"
RESIDUAL_PRE_DIG_ALIGN_DECISION_SOURCE = (
    "legacy_fsm_residual_pre_dig_align_already_applied"
)


@dataclass(frozen=True)
class LegacyFSMBranchPorts:
    """Typed shell ports needed to build the legacy FSM branch set."""

    bootstrap_skill_name: str
    pre_dig_align_skill_name: str
    dig_skill_name: str
    carry_skill_name: str
    dump_skill_name: str
    return_skill_name: str
    current_skill_name: Callable[[], str]
    current_switch_reason: Callable[[], str]
    should_end_bootstrap: Callable[..., bool]
    bootstrap_end_mode: Callable[[], str]
    should_pre_dig_align_before_dig: Callable[[], bool]
    set_skill: Callable[[str, str], None]
    maybe_handle_pre_dig_align_skill: Callable[[dict[str, Any]], bool]
    dig_exit_guard_ready: Callable[[dict[str, Any]], bool]
    increment_dig_exit_guard_replan_count: Callable[[], None]
    reject_active_coverage_corridor: Callable[..., None]
    restart_after_failed_dig: Callable[[str, dict[str, Any]], None]
    dig_bad_replan_ready: Callable[[dict[str, Any]], bool]
    increment_dig_bad_replan_count: Callable[[], None]
    dig_complete_boundary_low_payload: Callable[[dict[str, Any], Any | None], bool]
    dig_to_carry_ready: Callable[..., bool]
    complete_cell_entry_dig: Callable[[dict[str, Any]], None]
    complete_coverage_dig: Callable[[dict[str, Any]], None]
    dig_to_carry_reason: Callable[[], str]
    carry_transition_status: Callable[[dict[str, Any], Any | None], CarryTransitionStatus]
    complete_coverage_dump: Callable[..., None]
    set_return_or_direct_handoff: Callable[..., None]
    set_dump_ready_hold_count: Callable[[int], None]
    deposited_mass: Callable[[dict[str, Any]], float]
    set_dump_start_deposited_mass: Callable[[float], None]
    dump_transition_status: Callable[[dict[str, Any], Any | None], DumpTransitionStatus]
    set_dump_done_hold_count: Callable[[int], None]
    return_transition_status: Callable[
        [dict[str, Any], Any | None],
        ReturnTransitionStatus,
    ]
    mark_return_next_dig_event_seen: Callable[[], None]
    complete_return_transition: Callable[[], None]
    next_skill_after_return_transition: Callable[[], str]


class PrimitiveDecisionBackend(Protocol):
    """Backend interface for choosing the next primitive skill for a tick."""

    def decide_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult: ...


class PrimitiveDecisionBranch(Protocol):
    """One ordered primitive decision branch, or None when not handled."""

    def decide_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult | None: ...


@dataclass(frozen=True)
class PrimitiveRequestedBranchRunner:
    """Ordered primitive branch dispatch with explicit residual parking."""

    bootstrap_branch: PrimitiveDecisionBranch
    dig_branch: PrimitiveDecisionBranch
    carry_branch: PrimitiveDecisionBranch
    dump_branch: PrimitiveDecisionBranch
    return_branch: PrimitiveDecisionBranch
    residual_branch: PrimitiveDecisionBranch

    def decide_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult:
        for branch in (
            self.bootstrap_branch,
            self.dig_branch,
            self.carry_branch,
            self.dump_branch,
            self.return_branch,
            self.residual_branch,
        ):
            result = branch.decide_tick(
                obs=obs,
                boundary_event=boundary_event,
                preparation=preparation,
            )
            if result is not None:
                return result
        unhandled_skill = str(preparation.skill_name_before_decision)
        raise PrimitiveDecisionContractError(
            "unhandled planner skill in requested branch chain; broad legacy "
            f"fallback is retired for default decisions: {unhandled_skill!r}"
        )


@dataclass(frozen=True)
class LegacyFSMBackendAdapter:
    """Adapter around the existing already-mutating legacy FSM callback."""

    maybe_switch_skill: Callable[..., None]
    current_skill_name: Callable[[], str]
    current_switch_reason: Callable[[], str]

    def decide_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult:
        skill_before = str(preparation.skill_name_before_decision)
        self.maybe_switch_skill(obs=obs, boundary_event=boundary_event)
        return PrimitiveDecisionResult.from_legacy_fsm_outcome(
            skill_before=skill_before,
            skill_after=str(self.current_skill_name()),
            switch_reason=str(self.current_switch_reason()),
        )


@dataclass(frozen=True)
class LegacyFSMResidualPreDigAlignAdapter:
    """Explicit already-applied adapter for parked pre-dig-align behavior."""

    pre_dig_align_skill_name: str
    current_skill_name: Callable[[], str]
    current_switch_reason: Callable[[], str]
    maybe_handle_pre_dig_align_skill: Callable[[dict[str, Any]], bool]

    def decide_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult | None:
        del boundary_event
        skill_before = str(preparation.skill_name_before_decision)
        if str(self.current_skill_name()) != str(self.pre_dig_align_skill_name):
            return None
        self.maybe_handle_pre_dig_align_skill(obs)
        return PrimitiveDecisionResult.from_legacy_fsm_outcome(
            decision_source=RESIDUAL_PRE_DIG_ALIGN_DECISION_SOURCE,
            skill_before=skill_before,
            skill_after=str(self.current_skill_name()),
            switch_reason=str(self.current_switch_reason()),
        )

    def maybe_handle(self, *, obs: dict[str, Any], boundary_event: Any | None) -> bool:
        del boundary_event
        if str(self.current_skill_name()) != str(self.pre_dig_align_skill_name):
            return False
        self.maybe_handle_pre_dig_align_skill(obs)
        return True


@dataclass(frozen=True)
class LegacyFSMBootstrapConfig:
    bootstrap_skill_name: str
    pre_dig_align_skill_name: str


@dataclass(frozen=True)
class LegacyFSMBootstrapBranch:
    """Bootstrap branch of the legacy FSM with explicit callbacks."""

    config: LegacyFSMBootstrapConfig
    current_skill_name: Callable[[], str]
    should_end_bootstrap: Callable[..., bool]
    bootstrap_end_mode: Callable[[], str]
    should_pre_dig_align_before_dig: Callable[[], bool]
    set_skill: Callable[[str, str], None]

    def decide_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult | None:
        skill_before = str(preparation.skill_name_before_decision)
        if str(self.current_skill_name()) != str(self.config.bootstrap_skill_name):
            return None
        if not self.should_end_bootstrap(obs=obs, boundary_event=boundary_event):
            return PrimitiveDecisionResult.from_requested_effects(
                decision_source=BOOTSTRAP_REQUESTED_DECISION_SOURCE,
                status="no_change",
                skill_before=skill_before,
                skill_after=skill_before,
                switch_reason="",
                effects=(),
            )
        next_skill = self._next_skill_after_bootstrap()
        switch_reason = f"bootstrap_to_{next_skill}"
        return PrimitiveDecisionResult.from_requested_effects(
            decision_source=BOOTSTRAP_REQUESTED_DECISION_SOURCE,
            status="skill_switch",
            skill_before=skill_before,
            skill_after=next_skill,
            switch_reason=switch_reason,
            effects=(
                SwitchSkillEffect(
                    target_skill_name=next_skill,
                    switch_reason=switch_reason,
                ),
            ),
        )

    def maybe_handle(self, *, obs: dict[str, Any], boundary_event: Any | None) -> bool:
        skill_before = str(self.current_skill_name())
        result = self.decide_tick(
            obs=obs,
            boundary_event=boundary_event,
            preparation=PrimitiveTickPreparation(
                boundary_event=boundary_event,
                skill_name_before_decision=skill_before,
                dig_progress_updated=False,
            ),
        )
        if result is None:
            return False
        for effect in result.effects:
            if isinstance(effect, SwitchSkillEffect):
                self.set_skill(effect.target_skill_name, effect.switch_reason)
        return True

    def _next_skill_after_bootstrap(self) -> str:
        if self.bootstrap_end_mode() in {
            "first_qualified_dig_start",
            "scripted_qpos",
        }:
            return (
                str(self.config.pre_dig_align_skill_name)
                if self.should_pre_dig_align_before_dig()
                else "dig"
            )
        return "carry"


@dataclass(frozen=True)
class LegacyFSMDigConfig:
    dig_skill_name: str


@dataclass(frozen=True)
class LegacyFSMDigBranch:
    """Dig branch of the legacy FSM with explicit callbacks."""

    config: LegacyFSMDigConfig
    current_skill_name: Callable[[], str]
    dig_exit_guard_ready: Callable[[dict[str, Any]], bool]
    increment_dig_exit_guard_replan_count: Callable[[], None]
    reject_active_coverage_corridor: Callable[..., None]
    restart_after_failed_dig: Callable[[str, dict[str, Any]], None]
    dig_bad_replan_ready: Callable[[dict[str, Any]], bool]
    increment_dig_bad_replan_count: Callable[[], None]
    dig_complete_boundary_low_payload: Callable[[dict[str, Any], Any | None], bool]
    dig_to_carry_ready: Callable[..., bool]
    complete_cell_entry_dig: Callable[[dict[str, Any]], None]
    complete_coverage_dig: Callable[[dict[str, Any]], None]
    dig_to_carry_reason: Callable[[], str]
    set_skill: Callable[[str, str], None]

    def decide_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult | None:
        skill_before = str(preparation.skill_name_before_decision)
        if str(self.current_skill_name()) != str(self.config.dig_skill_name):
            return None
        effects = self._effects_for_tick(obs=obs, boundary_event=boundary_event)
        switch_reason = _switch_reason_from_effects(effects)
        skill_after = _skill_after_from_effects(effects, default=skill_before)
        return PrimitiveDecisionResult.from_requested_effects(
            decision_source=DIG_REQUESTED_DECISION_SOURCE,
            status="skill_switch" if switch_reason else "no_change",
            skill_before=skill_before,
            skill_after=skill_after,
            switch_reason=switch_reason,
            effects=effects,
        )

    def maybe_handle(self, *, obs: dict[str, Any], boundary_event: Any | None) -> bool:
        skill_before = str(self.current_skill_name())
        result = self.decide_tick(
            obs=obs,
            boundary_event=boundary_event,
            preparation=PrimitiveTickPreparation(
                boundary_event=boundary_event,
                skill_name_before_decision=skill_before,
                dig_progress_updated=True,
            ),
        )
        if result is None:
            return False
        self._apply_effects(obs, result.effects)
        return True

    def _effects_for_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> tuple[Any, ...]:
        if self.dig_exit_guard_ready(obs):
            return (
                IncrementDigExitGuardReplanCountEffect(),
                RejectActiveCoverageCorridorEffect(
                    reason="exit_overshoot_low_payload",
                ),
                RestartAfterFailedDigEffect(reason="exit_overshoot_low_payload"),
            )
        if self.dig_bad_replan_ready(obs):
            return (
                IncrementDigBadReplanCountEffect(),
                RejectActiveCoverageCorridorEffect(reason="bad_dig_low_payload"),
                RestartAfterFailedDigEffect(reason="bad_dig_low_payload"),
            )
        if self.dig_complete_boundary_low_payload(obs, boundary_event):
            return (
                IncrementDigBadReplanCountEffect(),
                RejectActiveCoverageCorridorEffect(
                    reason="dig_complete_low_current_payload",
                ),
                RestartAfterFailedDigEffect(reason="complete_low_payload"),
            )
        if self.dig_to_carry_ready(obs=obs, boundary_event=boundary_event):
            reason = self.dig_to_carry_reason() or "loaded"
            return (
                CompleteCellEntryDigCompatibilityEffect(),
                CompleteCoverageDigEffect(),
                SwitchSkillEffect(
                    target_skill_name="carry",
                    switch_reason=f"dig_to_carry_{reason}",
                ),
            )
        return ()

    def _apply_effects(self, obs: dict[str, Any], effects: tuple[Any, ...]) -> None:
        for effect in effects:
            if isinstance(effect, IncrementDigExitGuardReplanCountEffect):
                self.increment_dig_exit_guard_replan_count()
            elif isinstance(effect, IncrementDigBadReplanCountEffect):
                self.increment_dig_bad_replan_count()
            elif isinstance(effect, RejectActiveCoverageCorridorEffect):
                self.reject_active_coverage_corridor(obs, reason=effect.reason)
            elif isinstance(effect, RestartAfterFailedDigEffect):
                self.restart_after_failed_dig(effect.reason, obs)
            elif isinstance(effect, CompleteCellEntryDigCompatibilityEffect):
                self.complete_cell_entry_dig(obs)
            elif isinstance(effect, CompleteCoverageDigEffect):
                self.complete_coverage_dig(obs)
            elif isinstance(effect, SwitchSkillEffect):
                self.set_skill(effect.target_skill_name, effect.switch_reason)


@dataclass(frozen=True)
class LegacyFSMCarryConfig:
    carry_skill_name: str


@dataclass(frozen=True)
class LegacyFSMCarryBranch:
    """Carry branch of the legacy FSM with explicit callbacks."""

    config: LegacyFSMCarryConfig
    current_skill_name: Callable[[], str]
    carry_transition_status: Callable[[dict[str, Any], Any | None], CarryTransitionStatus]
    complete_coverage_dump: Callable[..., None]
    set_return_or_direct_handoff: Callable[..., None]
    set_dump_ready_hold_count: Callable[[int], None]
    deposited_mass: Callable[[dict[str, Any]], float]
    set_dump_start_deposited_mass: Callable[[float], None]
    set_skill: Callable[[str, str], None]

    def decide_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult | None:
        skill_before = str(preparation.skill_name_before_decision)
        if str(self.current_skill_name()) != str(self.config.carry_skill_name):
            return None
        status = self.carry_transition_status(obs, boundary_event)
        effects = self._effects_for_status(status)
        decision_status = "skill_switch" if _has_transition_effect(effects) else "no_change"
        switch_reason = _switch_reason_from_effects(effects)
        skill_after = _skill_after_from_effects(effects, default=skill_before)
        return PrimitiveDecisionResult.from_requested_effects(
            decision_source=CARRY_REQUESTED_DECISION_SOURCE,
            status=decision_status,
            skill_before=skill_before,
            skill_after=skill_after,
            switch_reason=switch_reason,
            effects=effects,
        )

    def maybe_handle(self, *, obs: dict[str, Any], boundary_event: Any | None) -> bool:
        skill_before = str(self.current_skill_name())
        result = self.decide_tick(
            obs=obs,
            boundary_event=boundary_event,
            preparation=PrimitiveTickPreparation(
                boundary_event=boundary_event,
                skill_name_before_decision=skill_before,
                dig_progress_updated=False,
            ),
        )
        if result is None:
            return False
        self._apply_effects(obs, result.effects)
        return True

    def _effects_for_status(
        self,
        status: CarryTransitionStatus,
    ) -> tuple[Any, ...]:
        if status.carry_release_safety_done:
            return (
                CompleteCoverageDumpEffect(reason="carry_release_safety"),
                SetReturnOrDirectHandoffEffect(
                    reason="carry_to_return_release_safety",
                ),
            )
        if status.dump_complete_event:
            return (
                CompleteCoverageDumpEffect(reason="carry_dump_complete_boundary"),
                SetReturnOrDirectHandoffEffect(
                    reason="carry_to_return_dump_complete_boundary",
                ),
            )
        effects: list[Any] = [
            SetDumpReadyHoldCountEffect(
                value=int(status.next_dump_ready_hold_count)
            )
        ]
        if status.ready_to_dump:
            reason = status.carry_to_dump_reason or "target_ready"
            effects.extend(
                (
                    SetDumpStartDepositedMassFromObservationEffect(),
                    SwitchSkillEffect(
                        target_skill_name="dump",
                        switch_reason=f"carry_to_dump_{reason}",
                    ),
                )
            )
        return tuple(effects)

    def _apply_effects(self, obs: dict[str, Any], effects: tuple[Any, ...]) -> None:
        for effect in effects:
            if isinstance(effect, CompleteCoverageDumpEffect):
                self.complete_coverage_dump(obs, reason=effect.reason)
            elif isinstance(effect, SetReturnOrDirectHandoffEffect):
                self.set_return_or_direct_handoff(obs, reason=effect.reason)
            elif isinstance(effect, SetDumpReadyHoldCountEffect):
                self.set_dump_ready_hold_count(int(effect.value))
            elif isinstance(effect, SetDumpStartDepositedMassFromObservationEffect):
                self.set_dump_start_deposited_mass(float(self.deposited_mass(obs)))
            elif isinstance(effect, SwitchSkillEffect):
                self.set_skill(effect.target_skill_name, effect.switch_reason)


@dataclass(frozen=True)
class LegacyFSMDumpConfig:
    dump_skill_name: str


@dataclass(frozen=True)
class LegacyFSMDumpBranch:
    """Dump branch of the legacy FSM with explicit callbacks."""

    config: LegacyFSMDumpConfig
    current_skill_name: Callable[[], str]
    dump_transition_status: Callable[[dict[str, Any], Any | None], DumpTransitionStatus]
    complete_coverage_dump: Callable[..., None]
    set_return_or_direct_handoff: Callable[..., None]
    set_dump_done_hold_count: Callable[[int], None]

    def decide_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult | None:
        skill_before = str(preparation.skill_name_before_decision)
        if str(self.current_skill_name()) != str(self.config.dump_skill_name):
            return None
        status = self.dump_transition_status(obs, boundary_event)
        effects = self._effects_for_status(status)
        decision_status = "skill_switch" if _has_transition_effect(effects) else "no_change"
        return PrimitiveDecisionResult.from_requested_effects(
            decision_source=DUMP_REQUESTED_DECISION_SOURCE,
            status=decision_status,
            skill_before=skill_before,
            skill_after=skill_before,
            switch_reason="",
            effects=effects,
        )

    def maybe_handle(self, *, obs: dict[str, Any], boundary_event: Any | None) -> bool:
        skill_before = str(self.current_skill_name())
        result = self.decide_tick(
            obs=obs,
            boundary_event=boundary_event,
            preparation=PrimitiveTickPreparation(
                boundary_event=boundary_event,
                skill_name_before_decision=skill_before,
                dig_progress_updated=False,
            ),
        )
        if result is None:
            return False
        self._apply_effects(obs, result.effects)
        return True

    def _effects_for_status(
        self,
        status: DumpTransitionStatus,
    ) -> tuple[Any, ...]:
        if status.boundary_dump_done:
            return (
                CompleteCoverageDumpEffect(reason=status.coverage_completion_reason),
                SetReturnOrDirectHandoffEffect(reason=status.dump_to_return_reason),
            )
        effects: list[Any] = [
            SetDumpDoneHoldCountEffect(value=int(status.next_dump_done_hold_count))
        ]
        if status.ready_to_return:
            effects.extend(
                (
                    CompleteCoverageDumpEffect(
                        reason=status.coverage_completion_reason,
                    ),
                    SetReturnOrDirectHandoffEffect(
                        reason=status.dump_to_return_reason,
                    ),
                )
            )
        return tuple(effects)

    def _apply_effects(self, obs: dict[str, Any], effects: tuple[Any, ...]) -> None:
        for effect in effects:
            if isinstance(effect, SetDumpDoneHoldCountEffect):
                self.set_dump_done_hold_count(int(effect.value))
            elif isinstance(effect, CompleteCoverageDumpEffect):
                self.complete_coverage_dump(obs, reason=effect.reason)
            elif isinstance(effect, SetReturnOrDirectHandoffEffect):
                self.set_return_or_direct_handoff(obs, reason=effect.reason)


@dataclass(frozen=True)
class LegacyFSMReturnConfig:
    return_skill_name: str


@dataclass(frozen=True)
class LegacyFSMReturnBranch:
    """Return branch of the legacy FSM with explicit callbacks."""

    config: LegacyFSMReturnConfig
    current_skill_name: Callable[[], str]
    return_transition_status: Callable[
        [dict[str, Any], Any | None],
        ReturnTransitionStatus,
    ]
    mark_return_next_dig_event_seen: Callable[[], None]
    complete_return_transition: Callable[[], None]
    next_skill_after_return_transition: Callable[[], str]
    set_skill: Callable[[str, str], None]

    def decide_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult | None:
        skill_before = str(preparation.skill_name_before_decision)
        if str(self.current_skill_name()) != str(self.config.return_skill_name):
            return None
        status = self.return_transition_status(obs, boundary_event)
        effects = self._effects_for_status(status)
        decision_status = (
            "skill_switch" if _has_return_switch_effect(effects) else "no_change"
        )
        return PrimitiveDecisionResult.from_requested_effects(
            decision_source=RETURN_REQUESTED_DECISION_SOURCE,
            status=decision_status,
            skill_before=skill_before,
            skill_after=skill_before,
            switch_reason="",
            effects=effects,
        )

    def maybe_handle(self, *, obs: dict[str, Any], boundary_event: Any | None) -> bool:
        skill_before = str(self.current_skill_name())
        result = self.decide_tick(
            obs=obs,
            boundary_event=boundary_event,
            preparation=PrimitiveTickPreparation(
                boundary_event=boundary_event,
                skill_name_before_decision=skill_before,
                dig_progress_updated=False,
            ),
        )
        if result is None:
            return False
        self._apply_effects(result.effects)
        return True

    def _effects_for_status(
        self,
        status: ReturnTransitionStatus,
    ) -> tuple[
        MarkReturnNextDigEventSeenEffect
        | CompleteReturnTransitionEffect
        | SwitchToNextSkillAfterReturnEffect,
        ...,
    ]:
        effects: list[
            MarkReturnNextDigEventSeenEffect
            | CompleteReturnTransitionEffect
            | SwitchToNextSkillAfterReturnEffect
        ] = []
        if status.next_dig_event:
            effects.append(MarkReturnNextDigEventSeenEffect())
        if status.completed_transition:
            reason_suffix = _return_transition_reason_suffix(status)
            effects.append(CompleteReturnTransitionEffect())
            effects.append(
                SwitchToNextSkillAfterReturnEffect(reason_suffix=reason_suffix)
            )
        return tuple(effects)

    def _apply_effects(self, effects: tuple[Any, ...]) -> None:
        for effect in effects:
            if isinstance(effect, MarkReturnNextDigEventSeenEffect):
                self.mark_return_next_dig_event_seen()
            elif isinstance(effect, CompleteReturnTransitionEffect):
                self.complete_return_transition()
            elif isinstance(effect, SwitchToNextSkillAfterReturnEffect):
                next_skill = str(self.next_skill_after_return_transition())
                self.set_skill(
                    next_skill,
                    f"return_to_{next_skill}_{effect.reason_suffix}",
                )


@dataclass(frozen=True)
class LegacyFSMBranchSet:
    """Constructed legacy FSM branches plus their supported dispatch orders."""

    bootstrap_branch: PrimitiveDecisionBranch
    dig_branch: PrimitiveDecisionBranch
    carry_branch: PrimitiveDecisionBranch
    dump_branch: PrimitiveDecisionBranch
    return_branch: PrimitiveDecisionBranch
    residual_branch: PrimitiveDecisionBranch

    @classmethod
    def from_ports(cls, ports: LegacyFSMBranchPorts) -> "LegacyFSMBranchSet":
        return cls(
            bootstrap_branch=LegacyFSMBootstrapBranch(
                config=LegacyFSMBootstrapConfig(
                    bootstrap_skill_name=ports.bootstrap_skill_name,
                    pre_dig_align_skill_name=ports.pre_dig_align_skill_name,
                ),
                current_skill_name=ports.current_skill_name,
                should_end_bootstrap=ports.should_end_bootstrap,
                bootstrap_end_mode=ports.bootstrap_end_mode,
                should_pre_dig_align_before_dig=(
                    ports.should_pre_dig_align_before_dig
                ),
                set_skill=ports.set_skill,
            ),
            dig_branch=LegacyFSMDigBranch(
                config=LegacyFSMDigConfig(dig_skill_name=ports.dig_skill_name),
                current_skill_name=ports.current_skill_name,
                dig_exit_guard_ready=ports.dig_exit_guard_ready,
                increment_dig_exit_guard_replan_count=(
                    ports.increment_dig_exit_guard_replan_count
                ),
                reject_active_coverage_corridor=(
                    ports.reject_active_coverage_corridor
                ),
                restart_after_failed_dig=ports.restart_after_failed_dig,
                dig_bad_replan_ready=ports.dig_bad_replan_ready,
                increment_dig_bad_replan_count=ports.increment_dig_bad_replan_count,
                dig_complete_boundary_low_payload=(
                    ports.dig_complete_boundary_low_payload
                ),
                dig_to_carry_ready=ports.dig_to_carry_ready,
                complete_cell_entry_dig=ports.complete_cell_entry_dig,
                complete_coverage_dig=ports.complete_coverage_dig,
                dig_to_carry_reason=ports.dig_to_carry_reason,
                set_skill=ports.set_skill,
            ),
            carry_branch=LegacyFSMCarryBranch(
                config=LegacyFSMCarryConfig(carry_skill_name=ports.carry_skill_name),
                current_skill_name=ports.current_skill_name,
                carry_transition_status=ports.carry_transition_status,
                complete_coverage_dump=ports.complete_coverage_dump,
                set_return_or_direct_handoff=ports.set_return_or_direct_handoff,
                set_dump_ready_hold_count=ports.set_dump_ready_hold_count,
                deposited_mass=ports.deposited_mass,
                set_dump_start_deposited_mass=ports.set_dump_start_deposited_mass,
                set_skill=ports.set_skill,
            ),
            dump_branch=LegacyFSMDumpBranch(
                config=LegacyFSMDumpConfig(dump_skill_name=ports.dump_skill_name),
                current_skill_name=ports.current_skill_name,
                dump_transition_status=ports.dump_transition_status,
                complete_coverage_dump=ports.complete_coverage_dump,
                set_return_or_direct_handoff=ports.set_return_or_direct_handoff,
                set_dump_done_hold_count=ports.set_dump_done_hold_count,
            ),
            return_branch=LegacyFSMReturnBranch(
                config=LegacyFSMReturnConfig(return_skill_name=ports.return_skill_name),
                current_skill_name=ports.current_skill_name,
                return_transition_status=ports.return_transition_status,
                mark_return_next_dig_event_seen=(
                    ports.mark_return_next_dig_event_seen
                ),
                complete_return_transition=ports.complete_return_transition,
                next_skill_after_return_transition=(
                    ports.next_skill_after_return_transition
                ),
                set_skill=ports.set_skill,
            ),
            residual_branch=LegacyFSMResidualPreDigAlignAdapter(
                pre_dig_align_skill_name=ports.pre_dig_align_skill_name,
                current_skill_name=ports.current_skill_name,
                current_switch_reason=ports.current_switch_reason,
                maybe_handle_pre_dig_align_skill=(
                    ports.maybe_handle_pre_dig_align_skill
                ),
            ),
        )

    def requested_runner(self) -> PrimitiveRequestedBranchRunner:
        return PrimitiveRequestedBranchRunner(
            bootstrap_branch=self.bootstrap_branch,
            dig_branch=self.dig_branch,
            carry_branch=self.carry_branch,
            dump_branch=self.dump_branch,
            return_branch=self.return_branch,
            residual_branch=self.residual_branch,
        )

    def requested_decision_backend(self) -> "LegacyFSMRequestedDecisionBackend":
        return LegacyFSMRequestedDecisionBackend(branch_set=self)

    def maybe_handle_legacy_fsm(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> bool:
        for branch in (
            self.bootstrap_branch,
            self.residual_branch,
            self.dig_branch,
            self.carry_branch,
            self.dump_branch,
            self.return_branch,
        ):
            if branch.maybe_handle(obs=obs, boundary_event=boundary_event):
                return True
        return False


@dataclass(frozen=True)
class LegacyFSMRequestedDecisionBackend:
    """Requested-effect decision backend backed by a legacy FSM branch set."""

    branch_set: LegacyFSMBranchSet

    @classmethod
    def from_ports(
        cls,
        ports: LegacyFSMBranchPorts,
    ) -> "LegacyFSMRequestedDecisionBackend":
        return cls(branch_set=LegacyFSMBranchSet.from_ports(ports))

    def decide_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult:
        return self.branch_set.requested_runner().decide_tick(
            obs=obs,
            boundary_event=boundary_event,
            preparation=preparation,
        )


__all__ = [
    "LegacyFSMBackendAdapter",
    "LegacyFSMBranchPorts",
    "LegacyFSMBranchSet",
    "LegacyFSMBootstrapBranch",
    "LegacyFSMBootstrapConfig",
    "LegacyFSMCarryBranch",
    "LegacyFSMCarryConfig",
    "LegacyFSMDigBranch",
    "LegacyFSMDigConfig",
    "LegacyFSMDumpBranch",
    "LegacyFSMDumpConfig",
    "LegacyFSMResidualPreDigAlignAdapter",
    "LegacyFSMRequestedDecisionBackend",
    "LegacyFSMReturnBranch",
    "LegacyFSMReturnConfig",
    "PrimitiveDecisionBranch",
    "PrimitiveDecisionBackend",
    "PrimitiveRequestedBranchRunner",
    "RESIDUAL_PRE_DIG_ALIGN_DECISION_SOURCE",
]


def _return_transition_reason_suffix(status: ReturnTransitionStatus) -> str:
    if status.next_or_seen_dig_event and status.handoff_ready:
        return "next_dig_entry_ready"
    if status.direct_handoff_ready:
        return "start_envelope_ready"
    if status.shallow_guard_allowed:
        return "shallow_entry_guard"
    return ""


def _has_return_switch_effect(effects: tuple[Any, ...]) -> bool:
    return any(
        isinstance(effect, SwitchToNextSkillAfterReturnEffect)
        for effect in effects
    )


def _has_transition_effect(effects: tuple[Any, ...]) -> bool:
    return any(
        isinstance(
            effect,
            (
                SwitchSkillEffect,
                SetReturnOrDirectHandoffEffect,
            ),
        )
        for effect in effects
    )


def _switch_reason_from_effects(effects: tuple[Any, ...]) -> str:
    for effect in effects:
        if isinstance(effect, SwitchSkillEffect):
            return str(effect.switch_reason)
    return ""


def _skill_after_from_effects(effects: tuple[Any, ...], *, default: str) -> str:
    for effect in effects:
        if isinstance(effect, SwitchSkillEffect):
            return str(effect.target_skill_name)
    return str(default)
