from __future__ import annotations

from collections.abc import Callable
from dataclasses import fields
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
from testbed.planner.primitive_cycle_state import PrimitiveCycleRuntimeState
from testbed.planner.primitive_return_state import PrimitiveReturnRuntimeState


def _ports(
    events: list[str],
    *,
    deposited_mass: Callable[[dict[str, Any]], float] | None = None,
    next_skill_after_return_transition: Callable[[], str] | None = None,
    cycle_state: PrimitiveCycleRuntimeState | None = None,
    return_state: PrimitiveReturnRuntimeState | None = None,
) -> RequestedEffectApplierPorts:
    return RequestedEffectApplierPorts(
        cycle_state=cycle_state or PrimitiveCycleRuntimeState.fresh(),
        return_state=return_state or PrimitiveReturnRuntimeState.fresh(),
        set_skill=lambda skill, reason: events.append(f"skill:{skill}:{reason}"),
        next_skill_after_return_transition=(
            next_skill_after_return_transition or (lambda: "dig")
        ),
        reject_active_coverage_corridor=lambda obs, reason: events.append(
            f"reject:{reason}:{obs['tag']}"
        ),
        restart_after_failed_dig=lambda reason, obs: events.append(
            f"restart:{reason}:{obs['tag']}"
        ),
        complete_cell_entry_dig=lambda obs: events.append(f"cell:{obs['tag']}"),
        complete_coverage_dig=lambda obs: events.append(f"coverage_dig:{obs['tag']}"),
        deposited_mass=deposited_mass or (lambda obs: 12.5),
        complete_coverage_dump=lambda obs, reason: events.append(
            f"coverage_dump:{reason}:{obs['tag']}"
        ),
        set_return_or_direct_handoff=lambda obs, reason: events.append(
            f"return:{reason}:{obs['tag']}"
        ),
    )


def test_requested_effect_ports_use_state_owners_not_storage_callbacks() -> None:
    field_names = {field.name for field in fields(RequestedEffectApplierPorts)}

    assert {"cycle_state", "return_state"} <= field_names
    assert not {
        "mark_return_next_dig_event_seen",
        "complete_return_transition",
        "increment_dig_exit_guard_replan_count",
        "increment_dig_bad_replan_count",
        "set_dump_ready_hold_count",
        "set_dump_start_deposited_mass",
        "set_dump_done_hold_count",
    } & field_names


def test_requested_effect_applier_applies_mixed_effects_in_order() -> None:
    events: list[str] = []
    obs = {"tag": "current"}
    cycle_state = PrimitiveCycleRuntimeState.fresh()
    return_state = PrimitiveReturnRuntimeState.fresh()

    def next_skill_after_return() -> str:
        events.append(f"next_skill:{cycle_state.cycle_index}")
        return "dig"

    ports = _ports(
        events,
        deposited_mass=lambda got_obs: 17.25,
        next_skill_after_return_transition=next_skill_after_return,
        cycle_state=cycle_state,
        return_state=return_state,
    )
    applier = RequestedEffectApplier(ports=ports)

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
        "next_skill:1",
        "skill:dig:return_to_dig_next_dig_entry_ready",
        "reject:bad_dig_low_payload:current",
        "restart:bad_dig_low_payload:current",
        "cell:current",
        "coverage_dig:current",
        "coverage_dump:dump_mass_low:current",
        "return:dump_to_return_mass_low:current",
    ]
    assert return_state.return_next_dig_event_seen is True
    assert cycle_state.completed_transition_count == 1
    assert cycle_state.cycle_index == 1
    assert cycle_state.dig_exit_guard_replan_count == 1
    assert cycle_state.dig_bad_replan_count == 1
    assert cycle_state.dump_ready_hold_count == 4
    assert cycle_state.dump_start_deposited_mass_kg == 17.25
    assert cycle_state.dump_done_hold_count == 2


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
    assert applier.ports.cycle_state.dump_start_deposited_mass_kg == 3.0
    applier.apply(second_obs, (SetDumpStartDepositedMassFromObservationEffect(),))

    assert events == ["read:first", "read:second"]
    assert applier.ports.cycle_state.dump_start_deposited_mass_kg == 8.0


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
