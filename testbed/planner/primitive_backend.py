"""Decision backend protocol and legacy FSM adapter for primitive planning."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from testbed.planner.primitive_capabilities import (
    CarryTransitionStatus,
    DigTransitionStatus,
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
from testbed.planner.primitive_decision_capabilities import (
    PrimitiveDecisionCapabilities,
)
from testbed.planner.primitive_decision_context import PrimitiveDecisionContext
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
    capabilities: PrimitiveDecisionCapabilities


class PrimitiveDecisionBackend(Protocol):
    """Backend interface for choosing the next primitive skill for a tick."""

    def decide_context(
        self,
        context: PrimitiveDecisionContext,
    ) -> PrimitiveDecisionResult: ...

    def decide_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult: ...


class PrimitiveDecisionBranch(Protocol):
    """One ordered primitive decision branch, or None when not handled."""

    def decide_context(
        self,
        context: PrimitiveDecisionContext,
    ) -> PrimitiveDecisionResult | None: ...

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

    def decide_context(
        self,
        context: PrimitiveDecisionContext,
    ) -> PrimitiveDecisionResult:
        for branch in (
            self.bootstrap_branch,
            self.dig_branch,
            self.carry_branch,
            self.dump_branch,
            self.return_branch,
            self.residual_branch,
        ):
            result = branch.decide_context(context)
            if result is not None:
                return result
        unhandled_skill = str(context.skill_name_before_decision)
        raise PrimitiveDecisionContractError(
            "unhandled planner skill in requested branch chain; broad legacy "
            f"fallback is retired for default decisions: {unhandled_skill!r}"
        )

    def decide_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult:
        return self.decide_context(
            PrimitiveDecisionContext.from_tick(
                obs=obs,
                boundary_event=boundary_event,
                preparation=preparation,
            )
        )


@dataclass(frozen=True)
class LegacyFSMBackendAdapter:
    """Adapter around the existing already-mutating legacy FSM callback."""

    maybe_switch_skill: Callable[..., None]
    current_skill_name: Callable[[], str]
    current_switch_reason: Callable[[], str]

    def decide_context(
        self,
        context: PrimitiveDecisionContext,
    ) -> PrimitiveDecisionResult:
        skill_before = str(context.skill_name_before_decision)
        self.maybe_switch_skill(
            obs=context.obs,
            boundary_event=context.boundary_event,
        )
        return PrimitiveDecisionResult.from_legacy_fsm_outcome(
            skill_before=skill_before,
            skill_after=str(self.current_skill_name()),
            switch_reason=str(self.current_switch_reason()),
        )

    def decide_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult:
        return self.decide_context(
            PrimitiveDecisionContext.from_tick(
                obs=obs,
                boundary_event=boundary_event,
                preparation=preparation,
            )
        )


@dataclass(frozen=True)
class LegacyFSMResidualPreDigAlignAdapter:
    """Explicit already-applied adapter for parked pre-dig-align behavior."""

    pre_dig_align_skill_name: str
    capabilities: PrimitiveDecisionCapabilities

    def decide_context(
        self,
        context: PrimitiveDecisionContext,
    ) -> PrimitiveDecisionResult | None:
        skill_before = str(context.skill_name_before_decision)
        if str(self.capabilities.current_skill_name()) != str(
            self.pre_dig_align_skill_name
        ):
            return None
        self.capabilities.handle_residual_pre_dig_align(context)
        return PrimitiveDecisionResult.from_legacy_fsm_outcome(
            decision_source=RESIDUAL_PRE_DIG_ALIGN_DECISION_SOURCE,
            skill_before=skill_before,
            skill_after=str(self.capabilities.current_skill_name()),
            switch_reason=str(self.capabilities.current_switch_reason()),
        )

    def decide_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult | None:
        return self.decide_context(
            PrimitiveDecisionContext.from_tick(
                obs=obs,
                boundary_event=boundary_event,
                preparation=preparation,
            )
        )

    def maybe_handle(self, *, obs: dict[str, Any], boundary_event: Any | None) -> bool:
        context = PrimitiveDecisionContext.from_tick(
            obs=obs,
            boundary_event=boundary_event,
            preparation=PrimitiveTickPreparation(
                boundary_event=boundary_event,
                skill_name_before_decision=str(self.capabilities.current_skill_name()),
                dig_progress_updated=False,
            ),
        )
        if str(self.capabilities.current_skill_name()) != str(
            self.pre_dig_align_skill_name
        ):
            return False
        self.capabilities.handle_residual_pre_dig_align(context)
        return True


@dataclass(frozen=True)
class LegacyFSMBootstrapConfig:
    bootstrap_skill_name: str
    pre_dig_align_skill_name: str


@dataclass(frozen=True)
class LegacyFSMBootstrapBranch:
    """Bootstrap branch of the legacy FSM with decision capabilities."""

    config: LegacyFSMBootstrapConfig
    capabilities: PrimitiveDecisionCapabilities

    def decide_context(
        self,
        context: PrimitiveDecisionContext,
    ) -> PrimitiveDecisionResult | None:
        skill_before = str(context.skill_name_before_decision)
        if str(self.capabilities.current_skill_name()) != str(
            self.config.bootstrap_skill_name
        ):
            return None
        status = self.capabilities.bootstrap_status(
            context,
            bootstrap_skill_name=self.config.bootstrap_skill_name,
            pre_dig_align_skill_name=self.config.pre_dig_align_skill_name,
        )
        if not status.should_end_bootstrap:
            return PrimitiveDecisionResult.from_requested_effects(
                decision_source=BOOTSTRAP_REQUESTED_DECISION_SOURCE,
                status="no_change",
                skill_before=skill_before,
                skill_after=skill_before,
                switch_reason="",
                effects=(),
            )
        next_skill = status.next_skill_after_bootstrap
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

    def decide_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult | None:
        return self.decide_context(
            PrimitiveDecisionContext.from_tick(
                obs=obs,
                boundary_event=boundary_event,
                preparation=preparation,
            )
        )


@dataclass(frozen=True)
class LegacyFSMDigConfig:
    dig_skill_name: str


@dataclass(frozen=True)
class LegacyFSMDigBranch:
    """Dig branch of the legacy FSM with decision capabilities."""

    config: LegacyFSMDigConfig
    capabilities: PrimitiveDecisionCapabilities

    def decide_context(
        self,
        context: PrimitiveDecisionContext,
    ) -> PrimitiveDecisionResult | None:
        skill_before = str(context.skill_name_before_decision)
        if str(self.capabilities.current_skill_name()) != str(self.config.dig_skill_name):
            return None
        effects = self._effects_for_status(
            self.capabilities.dig_transition_status(context)
        )
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

    def decide_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult | None:
        return self.decide_context(
            PrimitiveDecisionContext.from_tick(
                obs=obs,
                boundary_event=boundary_event,
                preparation=preparation,
            )
        )

    def _effects_for_status(self, status: DigTransitionStatus) -> tuple[Any, ...]:
        if status.dig_exit_guard_ready:
            return (
                IncrementDigExitGuardReplanCountEffect(),
                RejectActiveCoverageCorridorEffect(
                    reason="exit_overshoot_low_payload",
                ),
                RestartAfterFailedDigEffect(reason="exit_overshoot_low_payload"),
            )
        if status.dig_bad_replan_ready:
            return (
                IncrementDigBadReplanCountEffect(),
                RejectActiveCoverageCorridorEffect(reason="bad_dig_low_payload"),
                RestartAfterFailedDigEffect(reason="bad_dig_low_payload"),
            )
        if status.dig_complete_boundary_low_payload:
            return (
                IncrementDigBadReplanCountEffect(),
                RejectActiveCoverageCorridorEffect(
                    reason="dig_complete_low_current_payload",
                ),
                RestartAfterFailedDigEffect(reason="complete_low_payload"),
            )
        if status.dig_to_carry_ready:
            reason = str(status.dig_to_carry_reason) or "loaded"
            return (
                CompleteCellEntryDigCompatibilityEffect(),
                CompleteCoverageDigEffect(),
                SwitchSkillEffect(
                    target_skill_name="carry",
                    switch_reason=f"dig_to_carry_{reason}",
                ),
            )
        return ()

@dataclass(frozen=True)
class LegacyFSMCarryConfig:
    carry_skill_name: str


@dataclass(frozen=True)
class LegacyFSMCarryBranch:
    """Carry branch of the legacy FSM with decision capabilities."""

    config: LegacyFSMCarryConfig
    capabilities: PrimitiveDecisionCapabilities

    def decide_context(
        self,
        context: PrimitiveDecisionContext,
    ) -> PrimitiveDecisionResult | None:
        skill_before = str(context.skill_name_before_decision)
        if str(self.capabilities.current_skill_name()) != str(
            self.config.carry_skill_name
        ):
            return None
        status = self.capabilities.carry_transition_status(context)
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

    def decide_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult | None:
        return self.decide_context(
            PrimitiveDecisionContext.from_tick(
                obs=obs,
                boundary_event=boundary_event,
                preparation=preparation,
            )
        )

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

@dataclass(frozen=True)
class LegacyFSMDumpConfig:
    dump_skill_name: str


@dataclass(frozen=True)
class LegacyFSMDumpBranch:
    """Dump branch of the legacy FSM with decision capabilities."""

    config: LegacyFSMDumpConfig
    capabilities: PrimitiveDecisionCapabilities

    def decide_context(
        self,
        context: PrimitiveDecisionContext,
    ) -> PrimitiveDecisionResult | None:
        skill_before = str(context.skill_name_before_decision)
        if str(self.capabilities.current_skill_name()) != str(self.config.dump_skill_name):
            return None
        status = self.capabilities.dump_transition_status(context)
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

    def decide_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult | None:
        return self.decide_context(
            PrimitiveDecisionContext.from_tick(
                obs=obs,
                boundary_event=boundary_event,
                preparation=preparation,
            )
        )

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

@dataclass(frozen=True)
class LegacyFSMReturnConfig:
    return_skill_name: str


@dataclass(frozen=True)
class LegacyFSMReturnBranch:
    """Return branch of the legacy FSM with decision capabilities."""

    config: LegacyFSMReturnConfig
    capabilities: PrimitiveDecisionCapabilities

    def decide_context(
        self,
        context: PrimitiveDecisionContext,
    ) -> PrimitiveDecisionResult | None:
        skill_before = str(context.skill_name_before_decision)
        if str(self.capabilities.current_skill_name()) != str(
            self.config.return_skill_name
        ):
            return None
        status = self.capabilities.return_transition_status(context)
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

    def decide_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult | None:
        return self.decide_context(
            PrimitiveDecisionContext.from_tick(
                obs=obs,
                boundary_event=boundary_event,
                preparation=preparation,
            )
        )

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
                capabilities=ports.capabilities,
            ),
            dig_branch=LegacyFSMDigBranch(
                config=LegacyFSMDigConfig(dig_skill_name=ports.dig_skill_name),
                capabilities=ports.capabilities,
            ),
            carry_branch=LegacyFSMCarryBranch(
                config=LegacyFSMCarryConfig(carry_skill_name=ports.carry_skill_name),
                capabilities=ports.capabilities,
            ),
            dump_branch=LegacyFSMDumpBranch(
                config=LegacyFSMDumpConfig(dump_skill_name=ports.dump_skill_name),
                capabilities=ports.capabilities,
            ),
            return_branch=LegacyFSMReturnBranch(
                config=LegacyFSMReturnConfig(return_skill_name=ports.return_skill_name),
                capabilities=ports.capabilities,
            ),
            residual_branch=LegacyFSMResidualPreDigAlignAdapter(
                pre_dig_align_skill_name=ports.pre_dig_align_skill_name,
                capabilities=ports.capabilities,
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

    def compatibility_decision_backend(
        self,
    ) -> "LegacyFSMCompatibilityDecisionBackend":
        return LegacyFSMCompatibilityDecisionBackend(branch_set=self)


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

    def decide_context(
        self,
        context: PrimitiveDecisionContext,
    ) -> PrimitiveDecisionResult:
        return self.branch_set.requested_runner().decide_context(context)

    def decide_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult:
        return self.decide_context(
            PrimitiveDecisionContext.from_tick(
                obs=obs,
                boundary_event=boundary_event,
                preparation=preparation,
            )
        )


@dataclass(frozen=True)
class LegacyFSMCompatibilityDecisionBackend:
    """Legacy compatibility decision order without branch-local mutation."""

    branch_set: LegacyFSMBranchSet

    @classmethod
    def from_ports(
        cls,
        ports: LegacyFSMBranchPorts,
    ) -> "LegacyFSMCompatibilityDecisionBackend":
        return cls(branch_set=LegacyFSMBranchSet.from_ports(ports))

    def decide_context(
        self,
        context: PrimitiveDecisionContext,
    ) -> PrimitiveDecisionResult | None:
        for branch in (
            self.branch_set.bootstrap_branch,
            self.branch_set.residual_branch,
            self.branch_set.dig_branch,
            self.branch_set.carry_branch,
            self.branch_set.dump_branch,
            self.branch_set.return_branch,
        ):
            result = branch.decide_context(context)
            if result is not None:
                return result
        return None

    def decide_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult | None:
        return self.decide_context(
            PrimitiveDecisionContext.from_tick(
                obs=obs,
                boundary_event=boundary_event,
                preparation=preparation,
            )
        )


__all__ = [
    "LegacyFSMBackendAdapter",
    "LegacyFSMBranchPorts",
    "LegacyFSMBranchSet",
    "LegacyFSMBootstrapBranch",
    "LegacyFSMBootstrapConfig",
    "LegacyFSMCarryBranch",
    "LegacyFSMCarryConfig",
    "LegacyFSMCompatibilityDecisionBackend",
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
