"""Dump lifecycle transition runtime service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DumpLifecycleOutcome:
    action: str
    switch_reason: str = ""
    coverage_reason: str = ""


@dataclass(frozen=True)
class CarryTransitionRuntimeFacts:
    release_safety_done: bool
    dump_complete_event: bool
    dump_committed_event: bool
    release_onset_event: bool
    legacy_dump_start_event: bool
    dump_ready: bool
    current_dump_ready_hold_count: int


@dataclass(frozen=True)
class CarryTransitionRuntimeState:
    dump_ready_hold_count: int
    outcome: DumpLifecycleOutcome


@dataclass(frozen=True)
class CarryTransitionRuntimeRequestFacts:
    release_safety_done: bool
    boundary_event: Any | None
    semantic_boundary_profile_active: bool
    current_dump_ready_hold_count: int


@dataclass(frozen=True)
class CarryTransitionRuntimeRequest:
    facts: CarryTransitionRuntimeFacts
    should_check_dump_ready: bool

    def facts_with_dump_ready(self, dump_ready: bool) -> CarryTransitionRuntimeFacts:
        return CarryTransitionRuntimeFacts(
            release_safety_done=bool(self.facts.release_safety_done),
            dump_complete_event=bool(self.facts.dump_complete_event),
            dump_committed_event=bool(self.facts.dump_committed_event),
            release_onset_event=bool(self.facts.release_onset_event),
            legacy_dump_start_event=bool(self.facts.legacy_dump_start_event),
            dump_ready=bool(dump_ready),
            current_dump_ready_hold_count=int(
                self.facts.current_dump_ready_hold_count
            ),
        )


@dataclass(frozen=True)
class DumpTransitionRuntimeFacts:
    dump_complete_event: bool
    legacy_dump_end_event: bool
    dump_done: bool
    current_dump_done_hold_count: int


@dataclass(frozen=True)
class DumpTransitionRuntimeState:
    dump_done_hold_count: int
    outcome: DumpLifecycleOutcome


@dataclass(frozen=True)
class DumpTransitionRuntimeRequestFacts:
    dump_done_use_boundary_event: bool
    boundary_event: Any | None
    semantic_boundary_profile_active: bool
    current_dump_done_hold_count: int


@dataclass(frozen=True)
class DumpTransitionRuntimeRequest:
    facts: DumpTransitionRuntimeFacts
    should_check_dump_done: bool

    def facts_with_dump_done(self, dump_done: bool) -> DumpTransitionRuntimeFacts:
        return DumpTransitionRuntimeFacts(
            dump_complete_event=bool(self.facts.dump_complete_event),
            legacy_dump_end_event=bool(self.facts.legacy_dump_end_event),
            dump_done=bool(dump_done),
            current_dump_done_hold_count=int(
                self.facts.current_dump_done_hold_count
            ),
        )


def build_carry_transition_runtime_request(
    *,
    release_safety_done: bool,
    boundary_event: Any | None,
    semantic_boundary_profile_active: bool,
    current_dump_ready_hold_count: int,
) -> CarryTransitionRuntimeRequest:
    return DumpLifecycleTransitionService.carry_transition_runtime_request(
        CarryTransitionRuntimeRequestFacts(
            release_safety_done=bool(release_safety_done),
            boundary_event=boundary_event,
            semantic_boundary_profile_active=bool(semantic_boundary_profile_active),
            current_dump_ready_hold_count=int(current_dump_ready_hold_count),
        )
    )


def build_dump_transition_runtime_request(
    *,
    dump_done_use_boundary_event: bool,
    boundary_event: Any | None,
    semantic_boundary_profile_active: bool,
    current_dump_done_hold_count: int,
) -> DumpTransitionRuntimeRequest:
    return DumpLifecycleTransitionService.dump_transition_runtime_request(
        DumpTransitionRuntimeRequestFacts(
            dump_done_use_boundary_event=bool(dump_done_use_boundary_event),
            boundary_event=boundary_event,
            semantic_boundary_profile_active=bool(semantic_boundary_profile_active),
            current_dump_done_hold_count=int(current_dump_done_hold_count),
        )
    )


class DumpLifecycleTransitionService:
    """Project dump lifecycle transition outcomes from precomputed gates."""

    @staticmethod
    def carry_transition_runtime_request(
        facts: CarryTransitionRuntimeRequestFacts,
    ) -> CarryTransitionRuntimeRequest:
        dump_committed_event = False
        release_onset_event = False
        dump_complete_event = False
        if not bool(facts.release_safety_done):
            dump_committed_event = bool(
                facts.boundary_event is not None
                and getattr(facts.boundary_event, "dump_committed_start", False)
            )
            release_onset_event = bool(
                facts.boundary_event is not None
                and getattr(facts.boundary_event, "release_onset", False)
            )
            dump_complete_event = bool(
                facts.boundary_event is not None
                and getattr(facts.boundary_event, "dump_complete", False)
            )
        legacy_dump_start_event = False
        if not (bool(facts.release_safety_done) or dump_complete_event):
            legacy_dump_start_event = bool(
                facts.boundary_event is not None
                and getattr(facts.boundary_event, "dump_start", False)
                and not bool(facts.semantic_boundary_profile_active)
            )
        should_check_dump_ready = bool(
            not (
                bool(facts.release_safety_done)
                or dump_complete_event
                or dump_committed_event
                or release_onset_event
                or legacy_dump_start_event
            )
            and not bool(facts.semantic_boundary_profile_active)
        )
        return CarryTransitionRuntimeRequest(
            facts=CarryTransitionRuntimeFacts(
                release_safety_done=bool(facts.release_safety_done),
                dump_complete_event=dump_complete_event,
                dump_committed_event=dump_committed_event,
                release_onset_event=release_onset_event,
                legacy_dump_start_event=legacy_dump_start_event,
                dump_ready=False,
                current_dump_ready_hold_count=int(
                    facts.current_dump_ready_hold_count
                ),
            ),
            should_check_dump_ready=should_check_dump_ready,
        )

    @staticmethod
    def carry_outcome(
        *,
        release_safety_done: bool,
        dump_complete_event: bool,
        dump_committed_event: bool,
        release_onset_event: bool,
        legacy_dump_start_event: bool,
        dump_ready_hold_ready: bool,
    ) -> DumpLifecycleOutcome:
        if bool(release_safety_done):
            return DumpLifecycleOutcome(
                action="return",
                switch_reason="carry_to_return_release_safety",
                coverage_reason="carry_release_safety",
            )
        if bool(dump_complete_event):
            return DumpLifecycleOutcome(
                action="return",
                switch_reason="carry_to_return_dump_complete_boundary",
                coverage_reason="carry_dump_complete_boundary",
            )
        if bool(dump_ready_hold_ready):
            reason = (
                "dump_committed_boundary"
                if bool(dump_committed_event)
                else "release_onset_boundary"
                if bool(release_onset_event)
                else "dump_start_boundary"
                if bool(legacy_dump_start_event)
                else "target_ready"
            )
            return DumpLifecycleOutcome(
                action="dump",
                switch_reason=f"carry_to_dump_{reason}",
            )
        return DumpLifecycleOutcome(action="none")

    def carry_transition_runtime(
        self,
        facts: CarryTransitionRuntimeFacts,
        *,
        dump_ready_hold_steps: int,
    ) -> CarryTransitionRuntimeState:
        hold_count = int(facts.current_dump_ready_hold_count)
        if not (bool(facts.release_safety_done) or bool(facts.dump_complete_event)):
            if (
                bool(facts.dump_committed_event)
                or bool(facts.release_onset_event)
                or bool(facts.legacy_dump_start_event)
            ):
                hold_count = int(dump_ready_hold_steps)
            elif bool(facts.dump_ready):
                hold_count += 1
            else:
                hold_count = 0
        outcome = self.carry_outcome(
            release_safety_done=bool(facts.release_safety_done),
            dump_complete_event=bool(facts.dump_complete_event),
            dump_committed_event=bool(facts.dump_committed_event),
            release_onset_event=bool(facts.release_onset_event),
            legacy_dump_start_event=bool(facts.legacy_dump_start_event),
            dump_ready_hold_ready=(hold_count >= int(dump_ready_hold_steps)),
        )
        return CarryTransitionRuntimeState(
            dump_ready_hold_count=int(hold_count),
            outcome=outcome,
        )

    @staticmethod
    def dump_transition_runtime_request(
        facts: DumpTransitionRuntimeRequestFacts,
    ) -> DumpTransitionRuntimeRequest:
        dump_complete_event = bool(
            bool(facts.dump_done_use_boundary_event)
            and facts.boundary_event is not None
            and bool(getattr(facts.boundary_event, "dump_complete", False))
        )
        legacy_dump_end_event = False
        if not dump_complete_event:
            legacy_dump_end_event = bool(
                bool(facts.dump_done_use_boundary_event)
                and facts.boundary_event is not None
                and bool(getattr(facts.boundary_event, "dump_end", False))
                and not bool(facts.semantic_boundary_profile_active)
            )
        should_check_dump_done = bool(
            not (dump_complete_event or legacy_dump_end_event)
            and not bool(facts.semantic_boundary_profile_active)
        )
        return DumpTransitionRuntimeRequest(
            facts=DumpTransitionRuntimeFacts(
                dump_complete_event=dump_complete_event,
                legacy_dump_end_event=legacy_dump_end_event,
                dump_done=False,
                current_dump_done_hold_count=int(facts.current_dump_done_hold_count),
            ),
            should_check_dump_done=should_check_dump_done,
        )

    @staticmethod
    def dump_outcome(
        *,
        dump_complete_event: bool,
        legacy_dump_end_event: bool,
        dump_done_hold_ready: bool,
    ) -> DumpLifecycleOutcome:
        if bool(dump_complete_event) or bool(legacy_dump_end_event):
            coverage_reason = (
                "dump_complete_boundary"
                if bool(dump_complete_event)
                else "dump_end_boundary"
            )
            switch_reason = (
                "dump_to_return_dump_complete_boundary"
                if coverage_reason == "dump_complete_boundary"
                else "dump_to_return_dump_end"
            )
            return DumpLifecycleOutcome(
                action="return",
                switch_reason=switch_reason,
                coverage_reason=coverage_reason,
            )
        if bool(dump_done_hold_ready):
            return DumpLifecycleOutcome(
                action="return",
                switch_reason="dump_to_return_mass_low",
                coverage_reason="dump_mass_low",
            )
        return DumpLifecycleOutcome(action="none")

    def dump_transition_runtime(
        self,
        facts: DumpTransitionRuntimeFacts,
        *,
        dump_done_hold_steps: int,
    ) -> DumpTransitionRuntimeState:
        hold_count = int(facts.current_dump_done_hold_count)
        if not (bool(facts.dump_complete_event) or bool(facts.legacy_dump_end_event)):
            if bool(facts.dump_done):
                hold_count += 1
            else:
                hold_count = 0
        outcome = self.dump_outcome(
            dump_complete_event=bool(facts.dump_complete_event),
            legacy_dump_end_event=bool(facts.legacy_dump_end_event),
            dump_done_hold_ready=(hold_count >= int(dump_done_hold_steps)),
        )
        return DumpTransitionRuntimeState(
            dump_done_hold_count=int(hold_count),
            outcome=outcome,
        )
