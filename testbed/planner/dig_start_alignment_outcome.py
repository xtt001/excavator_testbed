"""Pre-dig alignment outcome classification and runtime projection."""

from __future__ import annotations

from dataclasses import dataclass

from testbed.planner.dig_start_alignment_runtime import (
    DigStartAlignmentRuntimeState,
    PreDigAlignOutcomeRuntimeProjection,
    project_pre_dig_align_outcome_runtime,
)


@dataclass(frozen=True)
class PreDigAlignOutcome:
    action: str
    switch_reason: str = ""
    reject_reason: str = ""


@dataclass(frozen=True)
class PreDigAlignOutcomeRuntimeFacts:
    outcome: PreDigAlignOutcome
    state: DigStartAlignmentRuntimeState


@dataclass(frozen=True)
class PreDigAlignOutcomeRequest:
    surface_guard_triggered: bool
    timed_out: bool

    @property
    def should_check_surface_guard_handoff(self) -> bool:
        return bool(self.surface_guard_triggered)

    @property
    def should_check_ready(self) -> bool:
        return not bool(self.surface_guard_triggered)

    def should_check_timeout(self, *, ready: bool) -> bool:
        return bool(
            not bool(self.surface_guard_triggered)
            and not bool(ready)
            and bool(self.timed_out)
        )

    def outcome_with_gate_results(
        self,
        *,
        surface_guard_can_handoff: bool = False,
        ready: bool = False,
        timeout_can_handoff: bool = False,
        timeout_reason: str = "",
    ) -> PreDigAlignOutcome:
        return DigStartAlignmentOutcomeService.classify_outcome(
            surface_guard_triggered=bool(self.surface_guard_triggered),
            surface_guard_can_handoff=bool(surface_guard_can_handoff),
            ready=bool(ready),
            timed_out=bool(self.timed_out),
            timeout_can_handoff=bool(timeout_can_handoff),
            timeout_reason=str(timeout_reason),
        )


class DigStartAlignmentOutcomeService:
    """Classifies pre-dig alignment outcomes without scheduler state."""

    @staticmethod
    def outcome_runtime_projection(
        facts: PreDigAlignOutcomeRuntimeFacts,
    ) -> PreDigAlignOutcomeRuntimeProjection:
        outcome = facts.outcome
        return project_pre_dig_align_outcome_runtime(
            state=facts.state,
            outcome_action=str(outcome.action),
            switch_reason=str(outcome.switch_reason),
            reject_reason=str(outcome.reject_reason),
        )

    @staticmethod
    def outcome_runtime_projection_from_state(
        *,
        outcome: PreDigAlignOutcome,
        state: DigStartAlignmentRuntimeState,
    ) -> PreDigAlignOutcomeRuntimeProjection:
        return DigStartAlignmentOutcomeService.outcome_runtime_projection(
            PreDigAlignOutcomeRuntimeFacts(
                outcome=outcome,
                state=state,
            )
        )

    @staticmethod
    def outcome_request(
        *,
        surface_guard_triggered: bool,
        step_count: int,
        max_steps: int,
    ) -> PreDigAlignOutcomeRequest:
        return PreDigAlignOutcomeRequest(
            surface_guard_triggered=bool(surface_guard_triggered),
            timed_out=bool(int(step_count) >= int(max_steps)),
        )

    @staticmethod
    def classify_outcome(
        *,
        surface_guard_triggered: bool,
        surface_guard_can_handoff: bool = False,
        ready: bool = False,
        timed_out: bool = False,
        timeout_can_handoff: bool = False,
        timeout_reason: str = "",
    ) -> PreDigAlignOutcome:
        if bool(surface_guard_triggered):
            if bool(surface_guard_can_handoff):
                return PreDigAlignOutcome(
                    action="surface_guard_handoff",
                    switch_reason="pre_dig_align_to_dig_surface_guard",
                )
            return PreDigAlignOutcome(
                action="surface_guard_replan",
                switch_reason="pre_dig_align_to_dig_surface_guard_replan",
                reject_reason="pre_align_surface_penetration_entry_gap",
            )
        if bool(ready):
            return PreDigAlignOutcome(
                action="ready",
                switch_reason="pre_dig_align_to_dig_ready",
            )
        if bool(timed_out):
            if bool(timeout_can_handoff):
                reason = str(
                    timeout_reason or "pre_dig_align_to_dig_timeout_close_enough"
                )
                return PreDigAlignOutcome(
                    action="timeout_handoff",
                    switch_reason=reason,
                )
            return PreDigAlignOutcome(
                action="timeout_replan",
                switch_reason="pre_dig_align_retry_entry_gap",
                reject_reason="align_entry_gap_timeout",
            )
        return PreDigAlignOutcome(action="none")
