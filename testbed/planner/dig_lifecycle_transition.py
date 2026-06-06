"""Dig lifecycle transition runtime service."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class DigTransitionRuntimeFacts:
    exit_guard_ready: bool
    bad_replan_ready: bool
    complete_boundary_low_payload: bool
    dig_to_carry_ready: bool
    dig_to_carry_reason: str = ""


@dataclass(frozen=True)
class DigTransitionRuntimeRequest:
    facts: DigTransitionRuntimeFacts
    should_check_bad_replan: bool

    def should_check_complete_boundary_low_payload(
        self,
        bad_replan_ready: bool,
    ) -> bool:
        return bool(self.should_check_bad_replan and not bool(bad_replan_ready))

    def should_check_dig_to_carry(
        self,
        *,
        bad_replan_ready: bool,
        complete_boundary_low_payload: bool,
    ) -> bool:
        return bool(
            self.should_check_complete_boundary_low_payload(bad_replan_ready)
            and not bool(complete_boundary_low_payload)
        )

    def facts_with_gate_results(
        self,
        *,
        bad_replan_ready: bool,
        complete_boundary_low_payload: bool,
        dig_to_carry_ready: bool,
        dig_to_carry_reason: str = "",
    ) -> DigTransitionRuntimeFacts:
        return DigTransitionRuntimeFacts(
            exit_guard_ready=bool(self.facts.exit_guard_ready),
            bad_replan_ready=bool(bad_replan_ready),
            complete_boundary_low_payload=bool(complete_boundary_low_payload),
            dig_to_carry_ready=bool(dig_to_carry_ready),
            dig_to_carry_reason=str(dig_to_carry_reason),
        )


@dataclass(frozen=True)
class DigTransitionRuntimeOutcome:
    action: str
    counter: str = ""
    failed_dig_reason: str = ""
    coverage_reject_reason: str = ""
    switch_reason: str = ""


@dataclass(frozen=True)
class DigTransitionRuntimeProjection:
    outcome: DigTransitionRuntimeOutcome
    bad_replan_count_increment: int = 0
    exit_guard_replan_count_increment: int = 0

    @property
    def should_restart_after_failed_dig(self) -> bool:
        return self.outcome.action == "failed_dig"

    @property
    def should_handoff_to_carry(self) -> bool:
        return self.outcome.action == "carry"


@dataclass(frozen=True)
class FailedDigStopFacts:
    reason: str
    coverage_current_payload_gain_kg: float
    dig_best_mass_kg: float
    current_bucket_mass_kg: float
    dig_step_count: int
    switch_reason: str | None = None
    terminal_reason: str | None = None


FAILED_DIG_STOP_FACT_FIELDS: tuple[tuple[str, str], ...] = (
    ("coverage_current_payload_gain_kg", "_coverage_current_payload_gain_kg"),
    ("dig_best_mass_kg", "_dig_best_mass_kg"),
    ("dig_step_count", "_dig_step_count"),
)


def _optional_reason(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def build_failed_dig_stop_facts_from_mapping(
    values: Mapping[str, object],
) -> FailedDigStopFacts:
    return build_failed_dig_stop_facts_from_runtime(
        reason=values["reason"],
        coverage_current_payload_gain_kg=values["coverage_current_payload_gain_kg"],
        dig_best_mass_kg=values["dig_best_mass_kg"],
        current_bucket_mass_kg=values["current_bucket_mass_kg"],
        dig_step_count=values["dig_step_count"],
        switch_reason=values.get("switch_reason"),
        terminal_reason=values.get("terminal_reason"),
    )


def build_failed_dig_stop_facts_from_runtime(
    *,
    reason: object,
    coverage_current_payload_gain_kg: object,
    dig_best_mass_kg: object,
    current_bucket_mass_kg: object,
    dig_step_count: object,
    switch_reason: object | None = None,
    terminal_reason: object | None = None,
) -> FailedDigStopFacts:
    return FailedDigStopFacts(
        reason=str(reason),
        coverage_current_payload_gain_kg=float(coverage_current_payload_gain_kg),
        dig_best_mass_kg=float(dig_best_mass_kg),
        current_bucket_mass_kg=float(current_bucket_mass_kg),
        dig_step_count=int(dig_step_count),
        switch_reason=_optional_reason(switch_reason),
        terminal_reason=_optional_reason(terminal_reason),
    )


@dataclass(frozen=True)
class FailedDigStopState:
    switch_reason: str
    terminal_reason: str
    coverage_event: str
    coverage_event_extra: dict[str, float | int | str]
    terminal_stop_replace: bool = True


class DigLifecycleTransitionService:
    """Project dig transition outcomes from precomputed gates."""

    @staticmethod
    def dig_transition_runtime_request(
        *,
        exit_guard_ready: bool,
    ) -> DigTransitionRuntimeRequest:
        return DigTransitionRuntimeRequest(
            facts=DigTransitionRuntimeFacts(
                exit_guard_ready=bool(exit_guard_ready),
                bad_replan_ready=False,
                complete_boundary_low_payload=False,
                dig_to_carry_ready=False,
                dig_to_carry_reason="",
            ),
            should_check_bad_replan=not bool(exit_guard_ready),
        )

    @staticmethod
    def dig_transition_runtime(
        facts: DigTransitionRuntimeFacts,
    ) -> DigTransitionRuntimeOutcome:
        if bool(facts.exit_guard_ready):
            return DigTransitionRuntimeOutcome(
                action="failed_dig",
                counter="exit_guard_replan",
                failed_dig_reason="exit_overshoot_low_payload",
                coverage_reject_reason="exit_overshoot_low_payload",
            )
        if bool(facts.bad_replan_ready):
            return DigTransitionRuntimeOutcome(
                action="failed_dig",
                counter="bad_replan",
                failed_dig_reason="bad_dig_low_payload",
                coverage_reject_reason="bad_dig_low_payload",
            )
        if bool(facts.complete_boundary_low_payload):
            return DigTransitionRuntimeOutcome(
                action="failed_dig",
                counter="bad_replan",
                failed_dig_reason="complete_low_payload",
                coverage_reject_reason="dig_complete_low_current_payload",
            )
        if bool(facts.dig_to_carry_ready):
            reason = str(facts.dig_to_carry_reason or "loaded")
            return DigTransitionRuntimeOutcome(
                action="carry",
                switch_reason=f"dig_to_carry_{reason}",
            )
        return DigTransitionRuntimeOutcome(action="none")

    @staticmethod
    def dig_transition_runtime_projection(
        outcome: DigTransitionRuntimeOutcome,
    ) -> DigTransitionRuntimeProjection:
        bad_replan_increment = 0
        exit_guard_increment = 0
        if str(outcome.action) == "failed_dig":
            if str(outcome.counter) == "exit_guard_replan":
                exit_guard_increment = 1
            elif str(outcome.counter) == "bad_replan":
                bad_replan_increment = 1
        return DigTransitionRuntimeProjection(
            outcome=outcome,
            bad_replan_count_increment=bad_replan_increment,
            exit_guard_replan_count_increment=exit_guard_increment,
        )

    @staticmethod
    def failed_dig_stop_state(facts: FailedDigStopFacts) -> FailedDigStopState:
        reason = str(facts.reason)
        current_bucket_mass = float(facts.current_bucket_mass_kg)
        payload_gain = max(
            float(facts.coverage_current_payload_gain_kg),
            float(facts.dig_best_mass_kg),
            current_bucket_mass,
            0.0,
        )
        return FailedDigStopState(
            switch_reason=str(facts.switch_reason or f"dig_failed_stop_{reason}"),
            terminal_reason=str(
                facts.terminal_reason or f"dig_failed_{reason}"
            ),
            coverage_event="failed_dig_stop",
            coverage_event_extra={
                "reason": reason,
                "payload_gain_kg": float(payload_gain),
                "current_bucket_mass_kg": current_bucket_mass,
                "dig_best_mass_kg": float(facts.dig_best_mass_kg),
                "dig_step_count": int(facts.dig_step_count),
            },
            terminal_stop_replace=True,
        )
