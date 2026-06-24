"""Decision backend protocol and legacy FSM adapter for primitive planning."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from testbed.planner.primitive.facts.capabilities import (
    CarryTransitionStatus,
    DigTransitionStatus,
    DumpTransitionStatus,
    ReturnTransitionStatus,
)
from testbed.planner.primitive.decision.contracts import PrimitiveDecisionContractError
from testbed.planner.primitive.decision.contracts import PrimitiveDecisionResult
from testbed.planner.primitive.decision.contracts import CompleteCoverageDigEffect
from testbed.planner.primitive.decision.contracts import CompleteCoverageDumpEffect
from testbed.planner.primitive.decision.contracts import CompleteReturnTransitionEffect
from testbed.planner.primitive.decision.contracts import IncrementDigBadReplanCountEffect
from testbed.planner.primitive.decision.contracts import (
    IncrementDigExitGuardReplanCountEffect,
)
from testbed.planner.primitive.decision.contracts import MarkReturnNextDigEventSeenEffect
from testbed.planner.primitive.decision.contracts import RejectActiveCoverageCorridorEffect
from testbed.planner.primitive.decision.contracts import RestartAfterFailedDigEffect
from testbed.planner.primitive.decision.contracts import RestartDigWithNewCutEffect
from testbed.planner.primitive.decision.contracts import ReplanOrRestartPreDigAlignEffect
from testbed.planner.primitive.decision.contracts import SetDumpDoneHoldCountEffect
from testbed.planner.primitive.decision.contracts import SetDumpReadyHoldCountEffect
from testbed.planner.primitive.decision.contracts import (
    SetDumpStartDepositedMassFromObservationEffect,
)
from testbed.planner.primitive.decision.contracts import SetReturnOrDirectHandoffEffect
from testbed.planner.primitive.decision.contracts import SwitchSkillEffect
from testbed.planner.primitive.decision.contracts import SwitchToNextSkillAfterReturnEffect
from testbed.planner.primitive.decision.capabilities import (
    PrimitiveDecisionCompatibilityActions,
    PrimitiveDecisionCapabilities,
    PrimitiveDecisionCapabilitiesPorts,
)
from testbed.planner.primitive.facts.backend import PrimitiveBackendFactsSource
from testbed.planner.primitive.decision.context import PrimitiveDecisionContext
from testbed.planner.primitive.decision.input import (
    PrimitiveBackendDecisionInput,
    PrimitiveBackendDecisionInputBuilder,
)
from testbed.planner.primitive.decision.backends.legacy_capability_provider import (
    PrimitiveFSMCapabilityProvider,
    PrimitiveFSMCapabilityProviderConfig,
    PrimitiveFSMCapabilityProviderPorts,
)
from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.execution.cycle_state import PrimitiveCycleRuntimeState
from testbed.planner.primitive.execution.runtime import PrimitiveTickPreparation
from testbed.planner.primitive.effects.return_handoff import ReturnHandoffReadinessService
from testbed.planner.primitive.execution.return_state import PrimitiveReturnRuntimeState


BOOTSTRAP_REQUESTED_DECISION_SOURCE = "legacy_fsm_bootstrap_requested_effect"
DIG_REQUESTED_DECISION_SOURCE = "legacy_fsm_dig_requested_effect"
CARRY_REQUESTED_DECISION_SOURCE = "legacy_fsm_carry_requested_effect"
DUMP_REQUESTED_DECISION_SOURCE = "legacy_fsm_dump_requested_effect"
RETURN_REQUESTED_DECISION_SOURCE = "legacy_fsm_return_requested_effect"
PRE_DIG_ALIGN_REQUESTED_DECISION_SOURCE = "legacy_fsm_pre_dig_align_requested_effect"


class PrimitivePreDigAlignDecisionService(Protocol):
    """Pre-dig-align decision surface used by the legacy FSM ready branch."""

    def ready(self, obs: dict[str, Any]) -> bool: ...

    def mark_completed(self) -> None: ...

    def surface_guard_triggered_for_state(self, obs: dict[str, Any]) -> bool: ...

    def mark_surface_guard(self) -> None: ...

    def reset_hold(self) -> None: ...

    def surface_guard_can_handoff(self, obs: dict[str, Any]) -> bool: ...

    def timed_out(self) -> bool: ...

    def mark_timeout(self) -> None: ...

    @property
    def timeout_handoff_reason(self) -> str: ...

    def timeout_can_handoff(self, obs: dict[str, Any]) -> bool: ...


@dataclass(frozen=True)
class LegacyFSMBranchPorts:
    """Typed shell ports needed to build the legacy FSM branch set."""

    bootstrap_skill_name: str
    dig_skill_name: str
    carry_skill_name: str
    dump_skill_name: str
    return_skill_name: str
    facts_source: PrimitiveBackendFactsSource
    compatibility_actions: PrimitiveDecisionCompatibilityActions
    pre_dig_align_skill_name: str = "pre_dig_align"
    pre_dig_align_service: PrimitivePreDigAlignDecisionService | None = None


@dataclass(frozen=True)
class LegacyFSMDecisionBackendFactoryPorts:
    """Typed runtime ports for composing the default legacy FSM backend factory."""

    capability_provider_config: PrimitiveFSMCapabilityProviderConfig
    semantic_boundary_profile_active: Callable[[], bool]
    cycle_state: PrimitiveCycleRuntimeState
    coverage_state: CoverageRuntimeState
    return_state: PrimitiveReturnRuntimeState
    return_handoff_readiness_service: ReturnHandoffReadinessService
    current_skill_name: Callable[[], str]
    current_switch_reason: Callable[[], str]
    should_end_bootstrap: Callable[..., bool]
    bootstrap_end_mode: Callable[[], str]
    bootstrap_skill_name: str
    dig_skill_name: str
    carry_skill_name: str
    dump_skill_name: str
    return_skill_name: str
    pre_dig_align_skill_name: str = "pre_dig_align"
    pre_dig_align_service: PrimitivePreDigAlignDecisionService | None = None


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


class PrimitiveCompatibilityDecisionBackend(Protocol):
    """Backend interface for legacy compatibility decisions that may not handle."""

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


class PrimitiveDecisionBackendFactory(Protocol):
    """Factory interface for runtime-selected primitive decision backends."""

    def requested_decision_backend(self) -> PrimitiveDecisionBackend: ...

    def compatibility_decision_backend(
        self,
    ) -> PrimitiveCompatibilityDecisionBackend: ...


class PrimitiveDecisionBranch(Protocol):
    """One ordered primitive decision branch, or None when not handled."""

    def decide_input(
        self,
        decision_input: PrimitiveBackendDecisionInput,
    ) -> PrimitiveDecisionResult | None: ...


@dataclass(frozen=True)
class PrimitiveRequestedBranchRunner:
    """Ordered primitive branch dispatch with explicit residual parking."""

    facts_source: PrimitiveBackendFactsSource
    compatibility_actions: PrimitiveDecisionCompatibilityActions
    bootstrap_branch: PrimitiveDecisionBranch
    dig_branch: PrimitiveDecisionBranch
    carry_branch: PrimitiveDecisionBranch
    dump_branch: PrimitiveDecisionBranch
    return_branch: PrimitiveDecisionBranch
    pre_dig_align_branch: PrimitiveDecisionBranch | None = None

    def decide_context(
        self,
        context: PrimitiveDecisionContext,
    ) -> PrimitiveDecisionResult:
        decision_input = PrimitiveBackendDecisionInputBuilder.from_sources(
            facts_source=self.facts_source,
            compatibility_actions=self.compatibility_actions,
        ).build(context)
        if (
            self.pre_dig_align_branch is not None
            and str(context.skill_name_before_decision) == "pre_dig_align"
        ):
            result = self.pre_dig_align_branch.decide_input(decision_input)
            if result is not None:
                return result
        for branch in (
            self.bootstrap_branch,
            self.dig_branch,
            self.carry_branch,
            self.dump_branch,
            self.return_branch,
        ):
            result = branch.decide_input(decision_input)
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
class LegacyFSMBootstrapConfig:
    bootstrap_skill_name: str


@dataclass(frozen=True)
class LegacyFSMBootstrapBranch:
    """Bootstrap branch of the legacy FSM with decision capabilities."""

    config: LegacyFSMBootstrapConfig

    def decide_input(
        self,
        decision_input: PrimitiveBackendDecisionInput,
    ) -> PrimitiveDecisionResult | None:
        backend_facts = decision_input.backend_facts
        facts = decision_input.common
        skill_before = str(facts.skill_name_before_decision)
        if not facts.is_current_skill(self.config.bootstrap_skill_name):
            return None
        bootstrap_facts = backend_facts.bootstrap_decision()
        status = bootstrap_facts.status
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


@dataclass(frozen=True)
class LegacyFSMDigConfig:
    dig_skill_name: str


@dataclass(frozen=True)
class LegacyFSMDigBranch:
    """Dig branch of the legacy FSM with decision capabilities."""

    config: LegacyFSMDigConfig

    def decide_input(
        self,
        decision_input: PrimitiveBackendDecisionInput,
    ) -> PrimitiveDecisionResult | None:
        backend_facts = decision_input.backend_facts
        facts = decision_input.common
        skill_before = str(facts.skill_name_before_decision)
        if not facts.is_current_skill(self.config.dig_skill_name):
            return None
        dig_facts = backend_facts.dig_transition()
        decision_input.compatibility_actions.sync_dig_transition_reason(dig_facts)
        effects = self._effects_for_status(dig_facts.status)
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

    def decide_input(
        self,
        decision_input: PrimitiveBackendDecisionInput,
    ) -> PrimitiveDecisionResult | None:
        backend_facts = decision_input.backend_facts
        facts = decision_input.common
        skill_before = str(facts.skill_name_before_decision)
        if not facts.is_current_skill(self.config.carry_skill_name):
            return None
        carry_facts = backend_facts.carry_transition()
        effects = self._effects_for_status(carry_facts.status)
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

    def decide_input(
        self,
        decision_input: PrimitiveBackendDecisionInput,
    ) -> PrimitiveDecisionResult | None:
        backend_facts = decision_input.backend_facts
        facts = decision_input.common
        skill_before = str(facts.skill_name_before_decision)
        if not facts.is_current_skill(self.config.dump_skill_name):
            return None
        dump_facts = backend_facts.dump_transition()
        effects = self._effects_for_status(dump_facts.status)
        decision_status = "skill_switch" if _has_transition_effect(effects) else "no_change"
        return PrimitiveDecisionResult.from_requested_effects(
            decision_source=DUMP_REQUESTED_DECISION_SOURCE,
            status=decision_status,
            skill_before=skill_before,
            skill_after=skill_before,
            switch_reason="",
            effects=effects,
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

    def decide_input(
        self,
        decision_input: PrimitiveBackendDecisionInput,
    ) -> PrimitiveDecisionResult | None:
        backend_facts = decision_input.backend_facts
        facts = decision_input.common
        skill_before = str(facts.skill_name_before_decision)
        if not facts.is_current_skill(self.config.return_skill_name):
            return None
        decision_input.compatibility_actions.refresh_return_transition_state(
            decision_input.context
        )
        return_facts = backend_facts.return_transition()
        effects = self._effects_for_status(return_facts.status)
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
class LegacyFSMPreDigAlignConfig:
    pre_dig_align_skill_name: str
    dig_skill_name: str


@dataclass(frozen=True)
class LegacyFSMPreDigAlignBranch:
    """Ready-only pre-dig-align branch of the legacy FSM."""

    config: LegacyFSMPreDigAlignConfig
    service: PrimitivePreDigAlignDecisionService

    def decide_input(
        self,
        decision_input: PrimitiveBackendDecisionInput,
    ) -> PrimitiveDecisionResult | None:
        facts = decision_input.common
        skill_before = str(facts.skill_name_before_decision)
        if not facts.is_current_skill(self.config.pre_dig_align_skill_name):
            return None
        if self.service.surface_guard_triggered_for_state(decision_input.context.obs):
            return self._surface_guard_result(
                obs=decision_input.context.obs,
                skill_before=skill_before,
            )
        if self.service.ready(decision_input.context.obs):
            self.service.mark_completed()
            switch_reason = "pre_dig_align_to_dig_ready"
            return PrimitiveDecisionResult.from_requested_effects(
                decision_source=PRE_DIG_ALIGN_REQUESTED_DECISION_SOURCE,
                status="skill_switch",
                skill_before=skill_before,
                skill_after=str(self.config.dig_skill_name),
                switch_reason=switch_reason,
                effects=(
                    SwitchSkillEffect(
                        target_skill_name=str(self.config.dig_skill_name),
                        switch_reason=switch_reason,
                    ),
                ),
            )
        if self.service.timed_out():
            return self._timeout_result(
                obs=decision_input.context.obs,
                skill_before=skill_before,
            )
        return PrimitiveDecisionResult.from_requested_effects(
            decision_source=PRE_DIG_ALIGN_REQUESTED_DECISION_SOURCE,
            status="no_change",
            skill_before=skill_before,
            skill_after=skill_before,
            switch_reason="",
            effects=(),
        )

    def _surface_guard_result(
        self,
        *,
        obs: dict[str, Any],
        skill_before: str,
    ) -> PrimitiveDecisionResult:
        self.service.mark_surface_guard()
        self.service.reset_hold()
        if self.service.surface_guard_can_handoff(obs):
            self.service.mark_completed()
            switch_reason = "pre_dig_align_to_dig_surface_guard"
            return PrimitiveDecisionResult.from_requested_effects(
                decision_source=PRE_DIG_ALIGN_REQUESTED_DECISION_SOURCE,
                status="skill_switch",
                skill_before=skill_before,
                skill_after=str(self.config.dig_skill_name),
                switch_reason=switch_reason,
                effects=(
                    SwitchSkillEffect(
                        target_skill_name=str(self.config.dig_skill_name),
                        switch_reason=switch_reason,
                    ),
                ),
            )
        switch_reason = "pre_dig_align_to_dig_surface_guard_replan"
        return PrimitiveDecisionResult.from_requested_effects(
            decision_source=PRE_DIG_ALIGN_REQUESTED_DECISION_SOURCE,
            status="skill_switch",
            skill_before=skill_before,
            skill_after=str(self.config.dig_skill_name),
            switch_reason=switch_reason,
            effects=(
                RejectActiveCoverageCorridorEffect(
                    reason="pre_align_surface_penetration_entry_gap",
                ),
                RestartDigWithNewCutEffect(reason=switch_reason),
            ),
        )

    def _timeout_result(
        self,
        *,
        obs: dict[str, Any],
        skill_before: str,
    ) -> PrimitiveDecisionResult:
        self.service.mark_timeout()
        if self.service.timeout_can_handoff(obs):
            switch_reason = (
                str(self.service.timeout_handoff_reason).strip()
                or "pre_dig_align_to_dig_timeout_close_enough"
            )
            return PrimitiveDecisionResult.from_requested_effects(
                decision_source=PRE_DIG_ALIGN_REQUESTED_DECISION_SOURCE,
                status="skill_switch",
                skill_before=skill_before,
                skill_after=str(self.config.dig_skill_name),
                switch_reason=switch_reason,
                effects=(
                    SwitchSkillEffect(
                        target_skill_name=str(self.config.dig_skill_name),
                        switch_reason=switch_reason,
                    ),
                ),
            )
        switch_reason = "pre_dig_align_retry_entry_gap"
        return PrimitiveDecisionResult.from_requested_effects(
            decision_source=PRE_DIG_ALIGN_REQUESTED_DECISION_SOURCE,
            status="skill_switch",
            skill_before=skill_before,
            skill_after=str(self.config.pre_dig_align_skill_name),
            switch_reason=switch_reason,
            effects=(
                RejectActiveCoverageCorridorEffect(
                    reason="align_entry_gap_timeout",
                ),
                ReplanOrRestartPreDigAlignEffect(
                    replan_reason="pre_dig_align_replan_to_dig_entry_close",
                    restart_reason=switch_reason,
                ),
            ),
        )


@dataclass(frozen=True)
class LegacyFSMBranchSet:
    """Constructed legacy FSM branches plus their supported dispatch orders."""

    facts_source: PrimitiveBackendFactsSource
    compatibility_actions: PrimitiveDecisionCompatibilityActions
    bootstrap_branch: PrimitiveDecisionBranch
    dig_branch: PrimitiveDecisionBranch
    carry_branch: PrimitiveDecisionBranch
    dump_branch: PrimitiveDecisionBranch
    return_branch: PrimitiveDecisionBranch
    pre_dig_align_branch: PrimitiveDecisionBranch | None = None

    @classmethod
    def from_ports(cls, ports: LegacyFSMBranchPorts) -> "LegacyFSMBranchSet":
        pre_dig_align_branch = None
        if ports.pre_dig_align_service is not None:
            pre_dig_align_branch = LegacyFSMPreDigAlignBranch(
                config=LegacyFSMPreDigAlignConfig(
                    pre_dig_align_skill_name=ports.pre_dig_align_skill_name,
                    dig_skill_name=ports.dig_skill_name,
                ),
                service=ports.pre_dig_align_service,
            )
        return cls(
            facts_source=ports.facts_source,
            compatibility_actions=ports.compatibility_actions,
            bootstrap_branch=LegacyFSMBootstrapBranch(
                config=LegacyFSMBootstrapConfig(
                    bootstrap_skill_name=ports.bootstrap_skill_name,
                ),
            ),
            dig_branch=LegacyFSMDigBranch(
                config=LegacyFSMDigConfig(dig_skill_name=ports.dig_skill_name),
            ),
            carry_branch=LegacyFSMCarryBranch(
                config=LegacyFSMCarryConfig(carry_skill_name=ports.carry_skill_name),
            ),
            dump_branch=LegacyFSMDumpBranch(
                config=LegacyFSMDumpConfig(dump_skill_name=ports.dump_skill_name),
            ),
            return_branch=LegacyFSMReturnBranch(
                config=LegacyFSMReturnConfig(return_skill_name=ports.return_skill_name),
            ),
            pre_dig_align_branch=pre_dig_align_branch,
        )

    def requested_runner(self) -> PrimitiveRequestedBranchRunner:
        return PrimitiveRequestedBranchRunner(
            facts_source=self.facts_source,
            compatibility_actions=self.compatibility_actions,
            bootstrap_branch=self.bootstrap_branch,
            dig_branch=self.dig_branch,
            carry_branch=self.carry_branch,
            dump_branch=self.dump_branch,
            return_branch=self.return_branch,
            pre_dig_align_branch=self.pre_dig_align_branch,
        )

    def requested_decision_backend(self) -> "LegacyFSMRequestedDecisionBackend":
        return LegacyFSMRequestedDecisionBackend(branch_set=self)

    def compatibility_decision_backend(self) -> PrimitiveCompatibilityDecisionBackend:
        return LegacyFSMCompatibilityDecisionBackend(branch_set=self)


def _legacy_fsm_branch_ports_from_runtime_ports(
    ports: LegacyFSMDecisionBackendFactoryPorts,
) -> LegacyFSMBranchPorts:
    capabilities = PrimitiveDecisionCapabilities.from_ports(
        PrimitiveDecisionCapabilitiesPorts(
            current_skill_name=ports.current_skill_name,
            current_switch_reason=ports.current_switch_reason,
            should_end_bootstrap=ports.should_end_bootstrap,
            bootstrap_end_mode=ports.bootstrap_end_mode,
            transition_status_provider=(
                PrimitiveFSMCapabilityProvider.from_ports(
                    PrimitiveFSMCapabilityProviderPorts(
                        config=ports.capability_provider_config,
                        semantic_boundary_profile_active=(
                            ports.semantic_boundary_profile_active
                        ),
                        cycle_state=ports.cycle_state,
                        coverage_state=ports.coverage_state,
                        return_state=ports.return_state,
                        return_handoff_readiness_service=(
                            ports.return_handoff_readiness_service
                        ),
                    )
                )
            ),
        )
    )
    return LegacyFSMBranchPorts(
        bootstrap_skill_name=ports.bootstrap_skill_name,
        dig_skill_name=ports.dig_skill_name,
        carry_skill_name=ports.carry_skill_name,
        dump_skill_name=ports.dump_skill_name,
        return_skill_name=ports.return_skill_name,
        facts_source=capabilities.facts_source(),
        compatibility_actions=capabilities.compatibility_actions(),
        pre_dig_align_skill_name=ports.pre_dig_align_skill_name,
        pre_dig_align_service=ports.pre_dig_align_service,
    )


@dataclass(frozen=True)
class LegacyFSMDecisionBackendFactory:
    """Build and reuse legacy FSM requested and compatibility backends."""

    _branch_set_builder: Callable[[], LegacyFSMBranchSet] = field(
        repr=False,
        compare=False,
    )
    _cached_branch_set: LegacyFSMBranchSet | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    @classmethod
    def from_ports(
        cls,
        ports: LegacyFSMBranchPorts,
    ) -> "LegacyFSMDecisionBackendFactory":
        return cls(lambda: LegacyFSMBranchSet.from_ports(ports))

    @classmethod
    def from_runtime_ports(
        cls,
        ports: LegacyFSMDecisionBackendFactoryPorts,
    ) -> "LegacyFSMDecisionBackendFactory":
        return cls.from_ports(_legacy_fsm_branch_ports_from_runtime_ports(ports))

    @classmethod
    def from_branch_set(
        cls,
        branch_set: LegacyFSMBranchSet,
    ) -> "LegacyFSMDecisionBackendFactory":
        return cls(lambda: branch_set)

    def branch_set(self) -> LegacyFSMBranchSet:
        cached = self._cached_branch_set
        if cached is None:
            cached = self._branch_set_builder()
            object.__setattr__(self, "_cached_branch_set", cached)
        return cached

    def requested_decision_backend(self) -> "LegacyFSMRequestedDecisionBackend":
        return self.branch_set().requested_decision_backend()

    def compatibility_decision_backend(self) -> PrimitiveCompatibilityDecisionBackend:
        return self.branch_set().compatibility_decision_backend()


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
    ) -> PrimitiveCompatibilityDecisionBackend:
        return cls(branch_set=LegacyFSMBranchSet.from_ports(ports))

    def decide_context(
        self,
        context: PrimitiveDecisionContext,
    ) -> PrimitiveDecisionResult | None:
        decision_input = PrimitiveBackendDecisionInputBuilder.from_sources(
            facts_source=self.branch_set.facts_source,
            compatibility_actions=self.branch_set.compatibility_actions,
        ).build(context)
        if (
            self.branch_set.pre_dig_align_branch is not None
            and str(context.skill_name_before_decision) == "pre_dig_align"
        ):
            result = self.branch_set.pre_dig_align_branch.decide_input(
                decision_input
            )
            if result is not None:
                return result
        for branch in (
            self.branch_set.bootstrap_branch,
            self.branch_set.dig_branch,
            self.branch_set.carry_branch,
            self.branch_set.dump_branch,
            self.branch_set.return_branch,
        ):
            result = branch.decide_input(decision_input)
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
    "LegacyFSMDecisionBackendFactory",
    "LegacyFSMDecisionBackendFactoryPorts",
    "LegacyFSMDigBranch",
    "LegacyFSMDigConfig",
    "LegacyFSMDumpBranch",
    "LegacyFSMDumpConfig",
    "LegacyFSMPreDigAlignBranch",
    "LegacyFSMPreDigAlignConfig",
    "LegacyFSMRequestedDecisionBackend",
    "LegacyFSMReturnBranch",
    "LegacyFSMReturnConfig",
    "PrimitiveCompatibilityDecisionBackend",
    "PrimitivePreDigAlignDecisionService",
    "PrimitiveDecisionBranch",
    "PrimitiveDecisionBackend",
    "PrimitiveDecisionBackendFactory",
    "PrimitiveRequestedBranchRunner",
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
