"""Return-to-dig transition classification service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ReturnToDigTransitionConfig:
    legacy_shallow_guard_enabled: bool = True


@dataclass(frozen=True)
class ReturnDirectHandoffAttemptConfig:
    return_skill_name: str = "return"


@dataclass(frozen=True)
class ReturnToDigTransitionFacts:
    handoff_ready: bool
    next_dig_event_ready: bool
    next_dig_event_seen: bool
    direct_handoff_ready: bool
    shallow_guard_ready: bool


@dataclass(frozen=True)
class ReturnToDigTransitionRequest:
    facts: ReturnToDigTransitionFacts
    config: ReturnToDigTransitionConfig
    should_check_direct_handoff: bool

    def should_check_shallow_guard(self, direct_handoff_ready: bool) -> bool:
        return bool(
            self.should_check_direct_handoff
            and not bool(direct_handoff_ready)
            and bool(self.config.legacy_shallow_guard_enabled)
        )

    def facts_with_gate_results(
        self,
        *,
        direct_handoff_ready: bool,
        shallow_guard_ready: bool,
    ) -> ReturnToDigTransitionFacts:
        return ReturnToDigTransitionFacts(
            handoff_ready=bool(self.facts.handoff_ready),
            next_dig_event_ready=bool(self.facts.next_dig_event_ready),
            next_dig_event_seen=bool(self.facts.next_dig_event_seen),
            direct_handoff_ready=bool(direct_handoff_ready),
            shallow_guard_ready=bool(shallow_guard_ready),
        )


@dataclass(frozen=True)
class ReturnDirectHandoffAttemptFacts:
    active_skill_name: str
    return_target_planner_enabled: bool
    direct_handoff_enabled: bool
    handoff_evaluated: bool = False
    handoff_ready: bool = False
    direct_handoff_ready: bool = False


@dataclass(frozen=True)
class ReturnToDigTransitionOutcome:
    action: str
    reason_suffix: str
    next_dig_event_seen: bool

    def switch_reason(self, next_skill_name: str) -> str:
        if not self.reason_suffix:
            return ""
        return f"return_to_{next_skill_name}_{self.reason_suffix}"


@dataclass(frozen=True)
class ReturnDirectHandoffAttemptOutcome:
    action: str
    reason_suffix: str = ""
    should_prepare_return_target: bool = False
    should_evaluate_handoff: bool = False

    def switch_reason(self, next_skill_name: str) -> str:
        if not self.reason_suffix:
            return ""
        return f"return_to_{next_skill_name}_{self.reason_suffix}"


@dataclass(frozen=True)
class ReturnToDigTransitionCompletionFacts:
    pre_dig_align_before_dig: bool


@dataclass(frozen=True)
class ReturnToDigTransitionCompletionConfig:
    dig_skill_name: str = "dig"
    pre_dig_align_skill_name: str = "pre_dig_align"


@dataclass(frozen=True)
class ReturnToDigTransitionCompletionRequest:
    facts: ReturnToDigTransitionCompletionFacts
    config: ReturnToDigTransitionCompletionConfig


@dataclass(frozen=True)
class ReturnToDigTransitionCounterUpdate:
    should_transition: bool
    completed_transition_increment: int = 0
    cycle_index_increment: int = 0


@dataclass(frozen=True)
class ReturnToDigTransitionRuntimeProjection:
    next_dig_event_seen: bool
    should_transition: bool
    completed_transition_increment: int = 0
    cycle_index_increment: int = 0


@dataclass(frozen=True)
class ReturnToDigTransitionRuntime:
    outcome: ReturnToDigTransitionOutcome
    projection: ReturnToDigTransitionRuntimeProjection
    facts: ReturnToDigTransitionFacts | None = None


class ReturnTransitionHandoffReadyProvider(Protocol):
    def __call__(self, obs: dict) -> bool: ...


class ReturnTransitionDirectHandoffReadyProvider(Protocol):
    def __call__(
        self,
        obs: dict,
        *,
        handoff_ready: bool | None = None,
    ) -> bool: ...


class ReturnTransitionShallowGuardReadyProvider(Protocol):
    def __call__(
        self,
        *,
        obs: dict,
        boundary_event: Any | None,
    ) -> bool: ...


@dataclass(frozen=True)
class ReturnDirectHandoffRuntimeProjection:
    should_transition: bool
    completed_transition_increment: int = 0
    cycle_index_increment: int = 0


@dataclass(frozen=True)
class ReturnToDigTransitionCompletion:
    should_transition: bool
    next_skill: str = ""
    switch_reason: str = ""


@dataclass(frozen=True)
class ReturnDirectHandoffAttemptRequest:
    facts: ReturnDirectHandoffAttemptFacts
    config: ReturnDirectHandoffAttemptConfig
    outcome: ReturnDirectHandoffAttemptOutcome

    @property
    def should_prepare_return_target(self) -> bool:
        return bool(self.outcome.should_prepare_return_target)

    @property
    def should_evaluate_handoff(self) -> bool:
        return bool(self.outcome.should_evaluate_handoff)

    def facts_with_gate_results(
        self,
        *,
        handoff_ready: bool,
        direct_handoff_ready: bool,
    ) -> ReturnDirectHandoffAttemptFacts:
        return ReturnDirectHandoffAttemptFacts(
            active_skill_name=str(self.facts.active_skill_name),
            return_target_planner_enabled=bool(
                self.facts.return_target_planner_enabled
            ),
            direct_handoff_enabled=bool(self.facts.direct_handoff_enabled),
            handoff_evaluated=True,
            handoff_ready=bool(handoff_ready),
            direct_handoff_ready=bool(direct_handoff_ready),
        )


class ReturnToDigTransitionService:
    """Classify return-to-dig transition outcomes from precomputed gates."""

    @staticmethod
    def transition_request(
        *,
        handoff_ready: bool,
        boundary_event: Any | None,
        previous_next_dig_event_seen: bool,
        semantic_boundary_profile_active: bool,
    ) -> ReturnToDigTransitionRequest:
        next_dig_event_ready = bool(
            boundary_event is not None
            and (
                getattr(boundary_event, "next_dig_entry_ready", False)
                or getattr(boundary_event, "qualified_dig_start", False)
            )
        )
        next_dig_event_latched = bool(
            next_dig_event_ready or previous_next_dig_event_seen
        )
        should_check_direct = not (
            next_dig_event_latched and bool(handoff_ready)
        )
        legacy_shallow_guard_enabled = True
        if should_check_direct:
            legacy_shallow_guard_enabled = not bool(
                semantic_boundary_profile_active
            )
        return ReturnToDigTransitionRequest(
            facts=ReturnToDigTransitionFacts(
                handoff_ready=bool(handoff_ready),
                next_dig_event_ready=next_dig_event_ready,
                next_dig_event_seen=bool(previous_next_dig_event_seen),
                direct_handoff_ready=False,
                shallow_guard_ready=False,
            ),
            config=ReturnToDigTransitionConfig(
                legacy_shallow_guard_enabled=legacy_shallow_guard_enabled
            ),
            should_check_direct_handoff=should_check_direct,
        )

    @staticmethod
    def direct_handoff_attempt_request(
        *,
        active_skill_name: str,
        return_target_planner_enabled: bool,
        direct_handoff_enabled: bool,
        config: ReturnDirectHandoffAttemptConfig | None = None,
    ) -> ReturnDirectHandoffAttemptRequest:
        cfg = config or ReturnDirectHandoffAttemptConfig()
        facts = ReturnDirectHandoffAttemptFacts(
            active_skill_name=str(active_skill_name),
            return_target_planner_enabled=bool(return_target_planner_enabled),
            direct_handoff_enabled=bool(direct_handoff_enabled),
        )
        return ReturnDirectHandoffAttemptRequest(
            facts=facts,
            config=cfg,
            outcome=ReturnToDigTransitionService.direct_handoff_attempt(
                facts,
                cfg,
            ),
        )

    @staticmethod
    def completion_request(
        *,
        pre_dig_align_before_dig: bool,
        dig_skill_name: str = "dig",
        pre_dig_align_skill_name: str = "pre_dig_align",
    ) -> ReturnToDigTransitionCompletionRequest:
        return ReturnToDigTransitionCompletionRequest(
            facts=ReturnToDigTransitionCompletionFacts(
                pre_dig_align_before_dig=bool(pre_dig_align_before_dig),
            ),
            config=ReturnToDigTransitionCompletionConfig(
                dig_skill_name=str(dig_skill_name),
                pre_dig_align_skill_name=str(pre_dig_align_skill_name),
            ),
        )

    @staticmethod
    def direct_handoff_attempt(
        facts: ReturnDirectHandoffAttemptFacts,
        config: ReturnDirectHandoffAttemptConfig | None = None,
    ) -> ReturnDirectHandoffAttemptOutcome:
        cfg = config or ReturnDirectHandoffAttemptConfig()
        if str(facts.active_skill_name) != str(cfg.return_skill_name):
            return ReturnDirectHandoffAttemptOutcome(action="skip")
        if not facts.return_target_planner_enabled:
            return ReturnDirectHandoffAttemptOutcome(action="skip")
        if not facts.direct_handoff_enabled:
            return ReturnDirectHandoffAttemptOutcome(action="skip")
        if not facts.handoff_evaluated:
            return ReturnDirectHandoffAttemptOutcome(
                action="evaluate",
                should_prepare_return_target=True,
                should_evaluate_handoff=True,
            )
        if not (facts.handoff_ready and facts.direct_handoff_ready):
            return ReturnDirectHandoffAttemptOutcome(action="wait")
        return ReturnDirectHandoffAttemptOutcome(
            action="direct_handoff",
            reason_suffix="start_envelope_ready",
        )

    @staticmethod
    def transition_completion(
        outcome: ReturnToDigTransitionOutcome,
        facts: ReturnToDigTransitionCompletionFacts,
        config: ReturnToDigTransitionCompletionConfig | None = None,
    ) -> ReturnToDigTransitionCompletion:
        return ReturnToDigTransitionService._completion(
            transition_ready=str(outcome.action) != "wait",
            reason_suffix=str(outcome.reason_suffix),
            facts=facts,
            config=config,
        )

    @staticmethod
    def transition_counter_update(
        outcome: ReturnToDigTransitionOutcome,
    ) -> ReturnToDigTransitionCounterUpdate:
        return ReturnToDigTransitionService._counter_update(
            transition_ready=str(outcome.action) != "wait",
        )

    @staticmethod
    def transition_runtime_projection(
        outcome: ReturnToDigTransitionOutcome,
    ) -> ReturnToDigTransitionRuntimeProjection:
        counter_update = ReturnToDigTransitionService.transition_counter_update(
            outcome
        )
        return ReturnToDigTransitionRuntimeProjection(
            next_dig_event_seen=bool(outcome.next_dig_event_seen),
            should_transition=bool(counter_update.should_transition),
            completed_transition_increment=int(
                counter_update.completed_transition_increment
            ),
            cycle_index_increment=int(counter_update.cycle_index_increment),
        )

    @staticmethod
    def direct_handoff_runtime_projection(
        outcome: ReturnDirectHandoffAttemptOutcome,
    ) -> ReturnDirectHandoffRuntimeProjection:
        counter_update = ReturnToDigTransitionService.direct_handoff_counter_update(
            outcome
        )
        return ReturnDirectHandoffRuntimeProjection(
            should_transition=bool(counter_update.should_transition),
            completed_transition_increment=int(
                counter_update.completed_transition_increment
            ),
            cycle_index_increment=int(counter_update.cycle_index_increment),
        )

    @staticmethod
    def direct_handoff_completion(
        outcome: ReturnDirectHandoffAttemptOutcome,
        facts: ReturnToDigTransitionCompletionFacts,
        config: ReturnToDigTransitionCompletionConfig | None = None,
    ) -> ReturnToDigTransitionCompletion:
        return ReturnToDigTransitionService._completion(
            transition_ready=str(outcome.action) == "direct_handoff",
            reason_suffix=str(outcome.reason_suffix),
            facts=facts,
            config=config,
        )

    @staticmethod
    def direct_handoff_counter_update(
        outcome: ReturnDirectHandoffAttemptOutcome,
    ) -> ReturnToDigTransitionCounterUpdate:
        return ReturnToDigTransitionService._counter_update(
            transition_ready=str(outcome.action) == "direct_handoff",
        )

    @staticmethod
    def _completion(
        *,
        transition_ready: bool,
        reason_suffix: str,
        facts: ReturnToDigTransitionCompletionFacts,
        config: ReturnToDigTransitionCompletionConfig | None,
    ) -> ReturnToDigTransitionCompletion:
        if not transition_ready:
            return ReturnToDigTransitionCompletion(should_transition=False)
        cfg = config or ReturnToDigTransitionCompletionConfig()
        next_skill = (
            str(cfg.pre_dig_align_skill_name)
            if bool(facts.pre_dig_align_before_dig)
            else str(cfg.dig_skill_name)
        )
        switch_reason = (
            f"return_to_{next_skill}_{reason_suffix}" if reason_suffix else ""
        )
        return ReturnToDigTransitionCompletion(
            should_transition=True,
            next_skill=next_skill,
            switch_reason=switch_reason,
        )

    @staticmethod
    def _counter_update(
        *,
        transition_ready: bool,
    ) -> ReturnToDigTransitionCounterUpdate:
        if not transition_ready:
            return ReturnToDigTransitionCounterUpdate(should_transition=False)
        return ReturnToDigTransitionCounterUpdate(
            should_transition=True,
            completed_transition_increment=1,
            cycle_index_increment=1,
        )

    @staticmethod
    def classify(
        facts: ReturnToDigTransitionFacts,
        config: ReturnToDigTransitionConfig,
    ) -> ReturnToDigTransitionOutcome:
        next_dig_event_seen = bool(
            facts.next_dig_event_seen or facts.next_dig_event_ready
        )
        if next_dig_event_seen and facts.handoff_ready:
            return ReturnToDigTransitionOutcome(
                action="next_dig_event",
                reason_suffix="next_dig_entry_ready",
                next_dig_event_seen=next_dig_event_seen,
            )
        if facts.direct_handoff_ready:
            return ReturnToDigTransitionOutcome(
                action="direct_handoff",
                reason_suffix="start_envelope_ready",
                next_dig_event_seen=next_dig_event_seen,
            )
        if (
            config.legacy_shallow_guard_enabled
            and facts.shallow_guard_ready
            and facts.handoff_ready
        ):
            return ReturnToDigTransitionOutcome(
                action="shallow_guard",
                reason_suffix="shallow_entry_guard",
                next_dig_event_seen=next_dig_event_seen,
            )
        return ReturnToDigTransitionOutcome(
            action="wait",
            reason_suffix="",
            next_dig_event_seen=next_dig_event_seen,
        )


def return_transition_runtime_from_gate_providers(
    *,
    service: ReturnToDigTransitionService,
    obs: dict,
    boundary_event: Any | None,
    previous_next_dig_event_seen: bool,
    semantic_boundary_profile_active: bool,
    handoff_ready: ReturnTransitionHandoffReadyProvider,
    direct_handoff_ready: ReturnTransitionDirectHandoffReadyProvider,
    shallow_guard_ready: ReturnTransitionShallowGuardReadyProvider,
) -> ReturnToDigTransitionRuntime:
    """Build the return transition runtime while preserving legacy gate order."""

    handoff = bool(handoff_ready(obs))
    request = service.transition_request(
        handoff_ready=handoff,
        boundary_event=boundary_event,
        previous_next_dig_event_seen=previous_next_dig_event_seen,
        semantic_boundary_profile_active=semantic_boundary_profile_active,
    )
    direct = False
    shallow = False
    if request.should_check_direct_handoff:
        direct = bool(
            direct_handoff_ready(
                obs,
                handoff_ready=handoff,
            )
        )
    if request.should_check_shallow_guard(direct):
        shallow = bool(
            shallow_guard_ready(
                obs=obs,
                boundary_event=boundary_event,
            )
        )
    facts = request.facts_with_gate_results(
        direct_handoff_ready=direct,
        shallow_guard_ready=shallow,
    )
    outcome = service.classify(facts, request.config)
    projection = service.transition_runtime_projection(outcome)
    return ReturnToDigTransitionRuntime(
        outcome=outcome,
        projection=projection,
        facts=facts,
    )
