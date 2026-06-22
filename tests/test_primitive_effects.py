from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from testbed.planner.primitive_decision import (
    CompleteCellEntryDigCompatibilityEffect,
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
from testbed.planner.primitive_effects import (
    RequestedEffectApplier,
    RequestedEffectApplierPorts,
)


def _ports(
    events: list[str],
    *,
    deposited_mass: Callable[[dict[str, Any]], float] | None = None,
    next_skill_after_return_transition: Callable[[], str] | None = None,
) -> RequestedEffectApplierPorts:
    return RequestedEffectApplierPorts(
        set_skill=lambda skill, reason: events.append(f"skill:{skill}:{reason}"),
        mark_return_next_dig_event_seen=lambda: events.append("mark_return_event"),
        complete_return_transition=lambda: events.append("complete_return"),
        next_skill_after_return_transition=(
            next_skill_after_return_transition or (lambda: "dig")
        ),
        increment_dig_exit_guard_replan_count=lambda: events.append("exit_count"),
        increment_dig_bad_replan_count=lambda: events.append("bad_count"),
        reject_active_coverage_corridor=lambda obs, reason: events.append(
            f"reject:{reason}:{obs['tag']}"
        ),
        restart_after_failed_dig=lambda reason, obs: events.append(
            f"restart:{reason}:{obs['tag']}"
        ),
        complete_cell_entry_dig=lambda obs: events.append(f"cell:{obs['tag']}"),
        complete_coverage_dig=lambda obs: events.append(f"coverage_dig:{obs['tag']}"),
        set_dump_ready_hold_count=lambda value: events.append(f"ready:{value}"),
        deposited_mass=deposited_mass or (lambda obs: 12.5),
        set_dump_start_deposited_mass=lambda value: events.append(f"start:{value}"),
        set_dump_done_hold_count=lambda value: events.append(f"done:{value}"),
        complete_coverage_dump=lambda obs, reason: events.append(
            f"coverage_dump:{reason}:{obs['tag']}"
        ),
        set_return_or_direct_handoff=lambda obs, reason: events.append(
            f"return:{reason}:{obs['tag']}"
        ),
    )


def test_requested_effect_applier_applies_mixed_effects_in_order() -> None:
    events: list[str] = []
    obs = {"tag": "current"}
    state = {"cycle": 0}

    def next_skill_after_return() -> str:
        state["cycle"] += 1
        events.append(f"next_skill:{state['cycle']}")
        return "dig"

    applier = RequestedEffectApplier(
        ports=_ports(
            events,
            deposited_mass=lambda got_obs: 17.25,
            next_skill_after_return_transition=next_skill_after_return,
        )
    )

    applier.apply(
        obs,
        (
            SwitchSkillEffect(target_skill_name="carry", switch_reason="bootstrap_to_carry"),
            MarkReturnNextDigEventSeenEffect(),
            CompleteReturnTransitionEffect(),
            SwitchToNextSkillAfterReturnEffect(reason_suffix="next_dig_entry_ready"),
            IncrementDigExitGuardReplanCountEffect(),
            IncrementDigBadReplanCountEffect(),
            RejectActiveCoverageCorridorEffect(reason="bad_dig_low_payload"),
            RestartAfterFailedDigEffect(reason="bad_dig_low_payload"),
            CompleteCellEntryDigCompatibilityEffect(),
            CompleteCoverageDigEffect(),
            SetDumpReadyHoldCountEffect(value=4),
            SetDumpStartDepositedMassFromObservationEffect(),
            SetDumpDoneHoldCountEffect(value=2),
            CompleteCoverageDumpEffect(reason="dump_mass_low"),
            SetReturnOrDirectHandoffEffect(reason="dump_to_return_mass_low"),
        ),
    )

    assert events == [
        "skill:carry:bootstrap_to_carry",
        "mark_return_event",
        "complete_return",
        "next_skill:1",
        "skill:dig:return_to_dig_next_dig_entry_ready",
        "exit_count",
        "bad_count",
        "reject:bad_dig_low_payload:current",
        "restart:bad_dig_low_payload:current",
        "cell:current",
        "coverage_dig:current",
        "ready:4",
        "start:17.25",
        "done:2",
        "coverage_dump:dump_mass_low:current",
        "return:dump_to_return_mass_low:current",
    ]


def test_requested_effect_applier_reads_deposited_mass_from_current_obs() -> None:
    events: list[str] = []
    first_obs = {"tag": "first"}
    second_obs = {"tag": "second"}

    def deposited_mass(obs: dict[str, Any]) -> float:
        events.append(f"read:{obs['tag']}")
        return 3.0 if obs is first_obs else 8.0

    applier = RequestedEffectApplier(
        ports=_ports(events, deposited_mass=deposited_mass)
    )

    applier.apply(first_obs, (SetDumpStartDepositedMassFromObservationEffect(),))
    applier.apply(second_obs, (SetDumpStartDepositedMassFromObservationEffect(),))

    assert events == ["read:first", "start:3.0", "read:second", "start:8.0"]


@pytest.mark.parametrize(
    ("effect", "message"),
    [
        (
            SwitchSkillEffect(target_skill_name="", switch_reason="reason"),
            "SwitchSkill effect requires non-empty skill and reason",
        ),
        (
            SwitchSkillEffect(target_skill_name="dig", switch_reason=""),
            "SwitchSkill effect requires non-empty skill and reason",
        ),
        (
            SwitchToNextSkillAfterReturnEffect(reason_suffix=""),
            "SwitchToNextSkillAfterReturn effect requires non-empty reason suffix",
        ),
        (
            RejectActiveCoverageCorridorEffect(reason=""),
            "RejectActiveCoverageCorridor effect requires non-empty reason",
        ),
        (
            RestartAfterFailedDigEffect(reason=""),
            "RestartAfterFailedDig effect requires non-empty reason",
        ),
        (
            CompleteCoverageDumpEffect(reason=""),
            "CompleteCoverageDump effect requires non-empty reason",
        ),
        (
            SetReturnOrDirectHandoffEffect(reason=""),
            "SetReturnOrDirectHandoff effect requires non-empty reason",
        ),
    ],
)
def test_requested_effect_applier_rejects_empty_contract_fields(
    effect: RequestedPlannerEffect,
    message: str,
) -> None:
    applier = RequestedEffectApplier(ports=_ports([]))

    with pytest.raises(PrimitiveDecisionContractError, match=message):
        applier.apply({"tag": "current"}, (effect,))


def test_requested_effect_applier_rejects_unknown_requested_effect() -> None:
    applier = RequestedEffectApplier(ports=_ports([]))

    with pytest.raises(PrimitiveDecisionContractError) as exc_info:
        applier.apply(
            {"tag": "current"},
            (
                RequestedPlannerEffect(
                    effect_type="record_decision_trace",
                    reason="future_backend_probe",
                ),
            ),
        )

    message = str(exc_info.value)
    assert "real planner" in message
    assert "requested-effect application" in message
    assert "only supports SwitchSkill" in message
