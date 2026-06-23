from __future__ import annotations

from types import MethodType
from types import SimpleNamespace
from typing import Any

import numpy as np

from testbed.data.schema import (
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX,
)
from testbed.planner.primitive_coverage import CoverageCorridorState
from testbed.planner.primitive_capabilities import (
    CarryTransitionStatus,
    DigTransitionStatus,
    DumpTransitionStatus,
    ReturnTransitionStatus,
)
from testbed.planner.primitive_decision import (
    LEGACY_FSM_DECISION_SOURCE,
    CompleteCellEntryDigCompatibilityEffect,
    CompleteCoverageDigEffect,
    CompleteReturnTransitionEffect,
    CompleteCoverageDumpEffect,
    IncrementDigBadReplanCountEffect,
    IncrementDigExitGuardReplanCountEffect,
    LegacyDecisionOutcomeEffect,
    MarkReturnNextDigEventSeenEffect,
    PrimitiveDecisionContractError,
    PrimitiveDecisionResult,
    RejectActiveCoverageCorridorEffect,
    RequestedPlannerEffect,
    RestartAfterFailedDigEffect,
    SetDumpDoneHoldCountEffect,
    SetDumpReadyHoldCountEffect,
    SetDumpStartDepositedMassFromObservationEffect,
    SetReturnOrDirectHandoffEffect,
    SwitchToNextSkillAfterReturnEffect,
    SwitchSkillEffect,
    validate_decision_effect_contract,
)
from testbed.planner.primitive_execution import PrimitiveTickPreparation
from testbed.planner.primitive_backend import RESIDUAL_PRE_DIG_ALIGN_DECISION_SOURCE
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def _default_dig_status(**overrides: Any) -> DigTransitionStatus:
    values: dict[str, Any] = {
        "dig_step_count": 0,
        "mass_in_bucket_kg": 0.0,
        "min_distance_to_dig_area_m": 0.0,
        "transition_mass_in_bucket_kg": 0.0,
        "transition_min_distance_to_dig_area_m": 0.0,
        "distance_ready": False,
        "semantic_boundary_profile_active": False,
        "coverage_terminal_stop_requested": False,
        "dig_complete_boundary": False,
        "dig_complete_boundary_low_payload": False,
        "dig_bad_replan_ready": False,
        "dig_exit_guard_ready": False,
        "dig_mass_plateau_ready": False,
        "dig_to_carry_ready": False,
        "dig_to_carry_reason": "",
    }
    values.update(overrides)
    return DigTransitionStatus(**values)


class _FakePrimitiveFSMCapabilityProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def dig_transition_status(self, obs: dict, boundary_event: Any | None) -> str:
        self.calls.append("dig")
        return "dig_status"

    def carry_transition_status(self, obs: dict, boundary_event: Any | None) -> str:
        self.calls.append("carry")
        return "carry_status"

    def dump_transition_status(self, obs: dict, boundary_event: Any | None) -> str:
        self.calls.append("dump")
        return "dump_status"

    def return_transition_status(self, obs: dict, boundary_event: Any | None) -> str:
        self.calls.append("return")
        return "return_status"

    def sync_dig_transition_reason(self, status: DigTransitionStatus) -> None:
        self.calls.append(f"sync:{status.dig_to_carry_reason}")

    def refresh_return_transition_state(self, obs: dict) -> None:
        self.calls.append("refresh_return")


class _FakeDecisionStatusProvider:
    def __init__(
        self,
        *,
        dig_status: DigTransitionStatus | None = None,
        carry_status: CarryTransitionStatus | None = None,
        dump_status: DumpTransitionStatus | None = None,
        return_status: ReturnTransitionStatus | None = None,
    ) -> None:
        self.dig_status = dig_status
        self.carry_status = carry_status
        self.dump_status = dump_status
        self.return_status = return_status

    def dig_transition_status(
        self,
        obs: dict,
        boundary_event: Any | None,
    ) -> DigTransitionStatus:
        if self.dig_status is None:
            raise AssertionError("dig status was not expected")
        return self.dig_status

    def carry_transition_status(
        self,
        obs: dict,
        boundary_event: Any | None,
    ) -> CarryTransitionStatus:
        if self.carry_status is None:
            raise AssertionError("carry status was not expected")
        return self.carry_status

    def dump_transition_status(
        self,
        obs: dict,
        boundary_event: Any | None,
    ) -> DumpTransitionStatus:
        if self.dump_status is None:
            raise AssertionError("dump status was not expected")
        return self.dump_status

    def return_transition_status(
        self,
        obs: dict,
        boundary_event: Any | None,
    ) -> ReturnTransitionStatus:
        if self.return_status is None:
            raise AssertionError("return status was not expected")
        return self.return_status

    def sync_dig_transition_reason(self, status: DigTransitionStatus) -> None:
        pass

    def refresh_return_transition_state(self, obs: dict) -> None:
        pass


def _install_fake_decision_status_provider(
    planner: PrimitivePlannerACTPolicy,
    *,
    dig_status: DigTransitionStatus | None = None,
    carry_status: CarryTransitionStatus | None = None,
    dump_status: DumpTransitionStatus | None = None,
    return_status: ReturnTransitionStatus | None = None,
) -> _FakeDecisionStatusProvider:
    provider = _FakeDecisionStatusProvider(
        dig_status=dig_status,
        carry_status=carry_status,
        dump_status=dump_status,
        return_status=return_status,
    )
    planner._primitive_fsm_capability_provider = MethodType(
        lambda self: provider,
        planner,
    )
    return provider


def _set_minimal_non_dig_capability_fields(planner: PrimitivePlannerACTPolicy) -> None:
    planner._coverage_cycle_start_deposit_kg = 0.0
    planner._dump_ready_hold_count = 0
    planner.dump_ready_hold_steps = 1
    planner.dump_ready_min_height_above_rim_m = 0.0
    planner.dump_ready_require_over_footprint = True
    planner.dump_ready_require_clearance = True
    planner.dump_ready_max_horizontal_distance_m = None
    planner.dump_ready_position_mode = "footprint_or_dump_area_relative"
    planner.dump_ready_max_dump_area_footprint_outside_distance_m = None
    planner.dump_ready_min_dump_area_relative_x_m = None
    planner.dump_ready_max_dump_area_relative_x_m = None
    planner.dump_ready_min_dump_area_relative_z_m = None
    planner.dump_ready_max_dump_area_relative_z_m = None
    planner.dump_ready_near_window_enabled = False
    planner.dump_ready_near_window_x_tolerance_m = 0.0
    planner.dump_ready_near_window_z_tolerance_m = 0.0
    planner.dump_ready_near_window_outside_tolerance_m = 0.0
    planner.dump_ready_near_window_require_over_footprint = True
    planner.dump_done_max_bucket_mass_kg = 0.0
    planner.dump_done_min_deposit_delta_kg = 0.0
    planner.dump_done_use_boundary_event = True
    planner._dump_start_deposited_mass_kg = 0.0
    planner._dump_done_hold_count = 0
    planner.dump_done_hold_steps = 1
    planner.return_to_dig_start_envelope_direct_handoff_enabled = False
    planner.return_to_dig_start_envelope_gate_enabled = False
    planner.return_to_dig_shallow_guard_enabled = False
    planner.return_to_dig_max_bucket_mass_kg = 0.0
    planner.return_to_dig_touch_tolerance_m = 0.0
    planner.return_to_dig_min_depth_m = 0.0
    planner.return_to_dig_max_depth_m = 0.0
    planner.return_to_dig_max_entry_error_m = None
    planner._return_to_dig_handoff_ready = MethodType(lambda self, obs: False, planner)
    planner._should_pre_dig_align_before_dig = MethodType(lambda self: False, planner)


def test_legacy_decision_result_records_observable_skill_switch_only() -> None:
    result = PrimitiveDecisionResult.from_legacy_fsm_outcome(
        skill_before="dig",
        skill_after="carry",
        switch_reason="dig_to_carry_boundary_confirmed",
    )

    assert result.decision_source == LEGACY_FSM_DECISION_SOURCE
    assert result.status == "skill_switch"
    assert result.skill_before == "dig"
    assert result.skill_after == "carry"
    assert result.switch_reason == "dig_to_carry_boundary_confirmed"
    assert result.side_effects_applied is True
    assert result.effects == (
        LegacyDecisionOutcomeEffect(
            effect_type="legacy_decision_outcome",
            already_applied=True,
            skill_before="dig",
            skill_after="carry",
            switch_reason="dig_to_carry_boundary_confirmed",
        ),
    )


def test_legacy_decision_result_does_not_infer_private_effects_for_no_change() -> None:
    result = PrimitiveDecisionResult.from_legacy_fsm_outcome(
        skill_before="return",
        skill_after="return",
        switch_reason="",
    )

    assert result.status == "no_change"
    assert result.effects == ()
    assert result.side_effects_applied is True


def test_requested_effect_result_records_ordered_unapplied_effects() -> None:
    effects = (
        RequestedPlannerEffect(effect_type="record_decision_trace", reason="first"),
        RequestedPlannerEffect(effect_type="record_decision_note", reason="second"),
    )

    result = PrimitiveDecisionResult.from_requested_effects(
        decision_source="test_backend",
        status="skill_switch",
        skill_before="dig",
        skill_after="carry",
        switch_reason="dig_to_carry_boundary_confirmed",
        effects=effects,
    )

    assert result.side_effects_applied is False
    assert result.effects == effects
    assert [effect.reason for effect in result.effects] == ["first", "second"]


def test_switch_skill_effect_records_semantic_target_and_reason() -> None:
    effect = SwitchSkillEffect(
        target_skill_name="carry",
        switch_reason="dig_to_carry_boundary_confirmed",
    )

    result = PrimitiveDecisionResult.from_requested_effects(
        decision_source="test_backend",
        status="skill_switch",
        skill_before="dig",
        skill_after="carry",
        switch_reason="dig_to_carry_boundary_confirmed",
        effects=(effect,),
    )

    assert result.effects == (effect,)
    assert effect.effect_type == "switch_skill"
    assert effect.target_skill_name == "carry"
    assert effect.switch_reason == "dig_to_carry_boundary_confirmed"
    assert effect.reason == "dig_to_carry_boundary_confirmed"


def test_switch_skill_effect_rejects_empty_skill_or_reason() -> None:
    invalid_results = (
        PrimitiveDecisionResult.from_requested_effects(
            decision_source="test_backend",
            status="skill_switch",
            skill_before="dig",
            skill_after="",
            switch_reason="dig_to_carry_boundary_confirmed",
            effects=(
                SwitchSkillEffect(
                    target_skill_name="",
                    switch_reason="dig_to_carry_boundary_confirmed",
                ),
            ),
            validate=False,
        ),
        PrimitiveDecisionResult.from_requested_effects(
            decision_source="test_backend",
            status="skill_switch",
            skill_before="dig",
            skill_after="carry",
            switch_reason="",
            effects=(SwitchSkillEffect(target_skill_name="carry", switch_reason=""),),
            validate=False,
        ),
        PrimitiveDecisionResult.from_requested_effects(
            decision_source="test_backend",
            status="skill_switch",
            skill_before="dig",
            skill_after="carry",
            switch_reason="dig_to_carry_boundary_confirmed",
            effects=(
                RequestedPlannerEffect(
                    effect_type="switch_skill",
                    payload={
                        "target_skill_name": "carry",
                        "switch_reason": "dig_to_carry_boundary_confirmed",
                    },
                ),
            ),
            validate=False,
        ),
    )

    for result in invalid_results:
        try:
            validate_decision_effect_contract(result)
        except PrimitiveDecisionContractError:
            pass
        else:
            raise AssertionError("invalid SwitchSkill effect was accepted")


def test_return_cycle_effects_record_semantic_requests() -> None:
    effects = (
        MarkReturnNextDigEventSeenEffect(),
        CompleteReturnTransitionEffect(),
        SwitchToNextSkillAfterReturnEffect(reason_suffix="next_dig_entry_ready"),
    )

    result = PrimitiveDecisionResult.from_requested_effects(
        decision_source="legacy_fsm_return_requested_effect",
        status="skill_switch",
        skill_before="return",
        skill_after="return",
        switch_reason="",
        effects=effects,
    )

    assert result.effects == effects
    assert [effect.effect_type for effect in result.effects] == [
        "mark_return_next_dig_event_seen",
        "complete_return_transition",
        "switch_to_next_skill_after_return",
    ]
    assert effects[2].reason == "next_dig_entry_ready"


def test_return_cycle_effect_rejects_empty_reason_suffix() -> None:
    result = PrimitiveDecisionResult.from_requested_effects(
        decision_source="legacy_fsm_return_requested_effect",
        status="skill_switch",
        skill_before="return",
        skill_after="return",
        switch_reason="",
        effects=(SwitchToNextSkillAfterReturnEffect(reason_suffix=""),),
        validate=False,
    )

    try:
        validate_decision_effect_contract(result)
    except PrimitiveDecisionContractError:
        pass
    else:
        raise AssertionError("invalid return switch effect was accepted")


def test_carry_dump_effects_record_semantic_requests() -> None:
    effects = (
        SetDumpReadyHoldCountEffect(value=2),
        SetDumpStartDepositedMassFromObservationEffect(),
        SetDumpDoneHoldCountEffect(value=3),
        CompleteCoverageDumpEffect(reason="dump_mass_low"),
        SetReturnOrDirectHandoffEffect(reason="dump_to_return_mass_low"),
    )

    result = PrimitiveDecisionResult.from_requested_effects(
        decision_source="legacy_fsm_carry_requested_effect",
        status="skill_switch",
        skill_before="carry",
        skill_after="carry",
        switch_reason="",
        effects=effects,
    )

    assert result.effects == effects
    assert [effect.effect_type for effect in effects] == [
        "set_dump_ready_hold_count",
        "set_dump_start_deposited_mass_from_observation",
        "set_dump_done_hold_count",
        "complete_coverage_dump",
        "set_return_or_direct_handoff",
    ]
    assert effects[0].value == 2
    assert effects[2].value == 3
    assert effects[3].reason == "dump_mass_low"
    assert effects[4].reason == "dump_to_return_mass_low"


def test_carry_dump_effects_reject_invalid_values_or_reasons() -> None:
    invalid_results = (
        PrimitiveDecisionResult.from_requested_effects(
            decision_source="test_backend",
            status="no_change",
            skill_before="carry",
            skill_after="carry",
            switch_reason="",
            effects=(SetDumpReadyHoldCountEffect(value=-1),),
            validate=False,
        ),
        PrimitiveDecisionResult.from_requested_effects(
            decision_source="test_backend",
            status="no_change",
            skill_before="dump",
            skill_after="dump",
            switch_reason="",
            effects=(SetDumpDoneHoldCountEffect(value=-1),),
            validate=False,
        ),
        PrimitiveDecisionResult.from_requested_effects(
            decision_source="test_backend",
            status="skill_switch",
            skill_before="carry",
            skill_after="return",
            switch_reason="",
            effects=(CompleteCoverageDumpEffect(reason=""),),
            validate=False,
        ),
        PrimitiveDecisionResult.from_requested_effects(
            decision_source="test_backend",
            status="skill_switch",
            skill_before="dump",
            skill_after="return",
            switch_reason="",
            effects=(SetReturnOrDirectHandoffEffect(reason=""),),
            validate=False,
        ),
    )

    for result in invalid_results:
        try:
            validate_decision_effect_contract(result)
        except PrimitiveDecisionContractError:
            pass
        else:
            raise AssertionError("invalid carry/dump effect was accepted")


def test_dig_effects_record_semantic_requests() -> None:
    effects = (
        IncrementDigExitGuardReplanCountEffect(),
        IncrementDigBadReplanCountEffect(),
        RejectActiveCoverageCorridorEffect(reason="bad_dig_low_payload"),
        RestartAfterFailedDigEffect(reason="bad_dig_low_payload"),
        CompleteCellEntryDigCompatibilityEffect(),
        CompleteCoverageDigEffect(),
    )

    result = PrimitiveDecisionResult.from_requested_effects(
        decision_source="legacy_fsm_dig_requested_effect",
        status="skill_switch",
        skill_before="dig",
        skill_after="carry",
        switch_reason="dig_to_carry_loaded",
        effects=effects,
    )

    assert result.effects == effects
    assert [effect.effect_type for effect in effects] == [
        "increment_dig_exit_guard_replan_count",
        "increment_dig_bad_replan_count",
        "reject_active_coverage_corridor",
        "restart_after_failed_dig",
        "complete_cell_entry_dig_compatibility",
        "complete_coverage_dig",
    ]
    assert effects[2].reason == "bad_dig_low_payload"
    assert effects[3].reason == "bad_dig_low_payload"


def test_dig_effects_reject_invalid_reasons() -> None:
    invalid_results = (
        PrimitiveDecisionResult.from_requested_effects(
            decision_source="test_backend",
            status="no_change",
            skill_before="dig",
            skill_after="dig",
            switch_reason="",
            effects=(RejectActiveCoverageCorridorEffect(reason=""),),
            validate=False,
        ),
        PrimitiveDecisionResult.from_requested_effects(
            decision_source="test_backend",
            status="no_change",
            skill_before="dig",
            skill_after="dig",
            switch_reason="",
            effects=(RestartAfterFailedDigEffect(reason=""),),
            validate=False,
        ),
    )

    for result in invalid_results:
        try:
            validate_decision_effect_contract(result)
        except PrimitiveDecisionContractError:
            pass
        else:
            raise AssertionError("invalid dig effect was accepted")


def test_decision_contract_rejects_callable_or_planner_method_effect_shapes() -> None:
    callable_effect = PrimitiveDecisionResult.from_requested_effects(
        decision_source="test_backend",
        status="no_change",
        skill_before="dig",
        skill_after="dig",
        switch_reason="",
        effects=(
            RequestedPlannerEffect(
                effect_type="record_decision_trace",
                payload={"callback": lambda: None},
            ),
        ),
        validate=False,
    )
    method_effect = PrimitiveDecisionResult.from_requested_effects(
        decision_source="test_backend",
        status="no_change",
        skill_before="dig",
        skill_after="dig",
        switch_reason="",
        effects=(
            RequestedPlannerEffect(
                effect_type="call_planner_method",
                payload={"method_name": "_set_skill"},
            ),
        ),
        validate=False,
    )

    for result in (callable_effect, method_effect):
        try:
            validate_decision_effect_contract(result)
        except PrimitiveDecisionContractError:
            pass
        else:
            raise AssertionError("invalid requested effect shape was accepted")


def test_primitive_planner_requested_effect_bridge_allows_empty_effects() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)

    planner._apply_requested_tick_effects({}, ())


def test_primitive_planner_requested_effect_bridge_delegates_to_requested_applier() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    obs: dict[str, Any] = {"tag": "current_obs"}
    effects = (
        RequestedPlannerEffect(
            effect_type="delegated_probe",
            reason="test_delegate",
        ),
    )
    calls: list[tuple[dict[str, Any], tuple[RequestedPlannerEffect, ...]]] = []

    class FakeApplier:
        def apply(
            self,
            got_obs: dict[str, Any],
            got_effects: tuple[RequestedPlannerEffect, ...],
        ) -> None:
            calls.append((got_obs, got_effects))

    planner._requested_effect_applier = MethodType(lambda self: FakeApplier(), planner)

    planner._apply_requested_tick_effects(obs, effects)

    assert calls == [(obs, effects)]


def test_primitive_planner_requested_effect_bridge_rejects_live_effects() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    effects = (
        RequestedPlannerEffect(
            effect_type="record_decision_trace",
            reason="future_backend_probe",
        ),
    )

    try:
        planner._apply_requested_tick_effects({}, effects)
    except PrimitiveDecisionContractError as exc:
        message = str(exc)
    else:
        raise AssertionError("live requested effects were silently ignored")

    assert "real planner" in message
    assert "requested-effect application" in message
    assert "only supports SwitchSkill" in message


def test_primitive_planner_requested_effect_bridge_applies_switch_skill() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    calls: list[tuple[str, str]] = []

    def fake_set_skill(
        self: PrimitivePlannerACTPolicy,
        skill_name: str,
        reason: str,
    ) -> None:
        calls.append((skill_name, reason))

    planner._set_skill = MethodType(fake_set_skill, planner)

    planner._apply_requested_tick_effects(
        {},
        (
            SwitchSkillEffect(
                target_skill_name="carry",
                switch_reason="dig_to_carry_boundary_confirmed",
            ),
        )
    )

    assert calls == [("carry", "dig_to_carry_boundary_confirmed")]


def test_primitive_planner_requested_effect_bridge_applies_return_cycle_in_order() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    events: list[str] = []
    cycle_state = planner._primitive_cycle_runtime_state()
    return_state = planner._primitive_return_runtime_state()

    def fake_next_skill(self: PrimitivePlannerACTPolicy) -> str:
        events.append(f"next_skill:{cycle_state.cycle_index}")
        return "dig" if cycle_state.cycle_index > 0 else "pre_dig_align"

    def fake_set_skill(
        self: PrimitivePlannerACTPolicy,
        skill_name: str,
        reason: str,
    ) -> None:
        events.append(f"set:{skill_name}:{reason}")

    planner._next_skill_after_return_transition = MethodType(fake_next_skill, planner)
    planner._set_skill = MethodType(fake_set_skill, planner)

    planner._apply_requested_tick_effects(
        {},
        (
            MarkReturnNextDigEventSeenEffect(),
            CompleteReturnTransitionEffect(),
            SwitchToNextSkillAfterReturnEffect(
                reason_suffix="next_dig_entry_ready",
            ),
        )
    )

    assert events == [
        "next_skill:1",
        "set:dig:return_to_dig_next_dig_entry_ready",
    ]
    assert return_state.return_next_dig_event_seen is True
    assert cycle_state.completed_transition_count == 1
    assert cycle_state.cycle_index == 1


def test_primitive_planner_requested_effect_bridge_applies_carry_dump_effects_with_obs() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    obs: dict[str, Any] = {"payload": "current_obs"}
    events: list[str] = []
    cycle_state = planner._primitive_cycle_runtime_state()

    def fake_deposited(self: PrimitivePlannerACTPolicy, got_obs: dict[str, Any]) -> float:
        assert got_obs is obs
        events.append("deposited")
        return 12.5

    def fake_complete_dump(
        self: PrimitivePlannerACTPolicy,
        got_obs: dict[str, Any],
        *,
        reason: str,
    ) -> None:
        assert got_obs is obs
        events.append(f"complete:{reason}")

    def fake_return_or_handoff(
        self: PrimitivePlannerACTPolicy,
        got_obs: dict[str, Any],
        *,
        reason: str,
    ) -> None:
        assert got_obs is obs
        events.append(f"return:{reason}")

    def fake_set_skill(
        self: PrimitivePlannerACTPolicy,
        skill_name: str,
        reason: str,
    ) -> None:
        events.append(f"skill:{skill_name}:{reason}")

    planner._deposited_mass = MethodType(fake_deposited, planner)
    planner._complete_coverage_dump = MethodType(fake_complete_dump, planner)
    planner._set_return_or_direct_handoff = MethodType(fake_return_or_handoff, planner)
    planner._set_skill = MethodType(fake_set_skill, planner)

    planner._apply_requested_tick_effects(
        obs,
        (
            SetDumpReadyHoldCountEffect(value=4),
            SetDumpStartDepositedMassFromObservationEffect(),
            SwitchSkillEffect(
                target_skill_name="dump",
                switch_reason="carry_to_dump_target_ready",
            ),
            SetDumpDoneHoldCountEffect(value=2),
            CompleteCoverageDumpEffect(reason="dump_mass_low"),
            SetReturnOrDirectHandoffEffect(reason="dump_to_return_mass_low"),
        ),
    )

    assert events == [
        "deposited",
        "skill:dump:carry_to_dump_target_ready",
        "complete:dump_mass_low",
        "return:dump_to_return_mass_low",
    ]
    assert cycle_state.dump_ready_hold_count == 4
    assert cycle_state.dump_start_deposited_mass_kg == 12.5
    assert cycle_state.dump_done_hold_count == 2


def test_primitive_planner_return_effect_bridge_uses_service_backed_wrapper() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    obs: dict[str, Any] = {"payload": "current_obs"}
    calls: list[tuple[dict[str, Any], str]] = []

    class FakeReturnDirectHandoffService:
        def apply(self, got_obs: dict[str, Any], *, reason: str) -> object:
            calls.append((got_obs, reason))
            return SimpleNamespace(direct_handoff_applied=False)

    planner._return_direct_handoff_effect_service = MethodType(
        lambda self: FakeReturnDirectHandoffService(),
        planner,
    )

    planner._apply_requested_tick_effects(
        obs,
        (SetReturnOrDirectHandoffEffect(reason="dump_to_return_mass_low"),),
    )

    assert calls == [(obs, "dump_to_return_mass_low")]


def test_primitive_planner_requested_effect_bridge_applies_dig_effects_in_order() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    obs: dict[str, Any] = {"payload": "current_obs"}
    events: list[str] = []
    cycle_state = planner._primitive_cycle_runtime_state()

    def fake_reject(
        self: PrimitivePlannerACTPolicy,
        got_obs: dict[str, Any],
        *,
        reason: str,
    ) -> None:
        assert got_obs is obs
        events.append(f"reject:{reason}")

    def fake_restart(
        self: PrimitivePlannerACTPolicy,
        reason: str,
        got_obs: dict[str, Any],
    ) -> None:
        assert got_obs is obs
        events.append(f"restart:{reason}")

    def fake_complete_cell(
        self: PrimitivePlannerACTPolicy,
        got_obs: dict[str, Any],
    ) -> None:
        assert got_obs is obs
        events.append("cell")

    def fake_complete_dig(
        self: PrimitivePlannerACTPolicy,
        got_obs: dict[str, Any],
    ) -> None:
        assert got_obs is obs
        events.append("coverage")

    def fake_set_skill(
        self: PrimitivePlannerACTPolicy,
        skill_name: str,
        reason: str,
    ) -> None:
        events.append(f"skill:{skill_name}:{reason}")

    planner._reject_active_coverage_corridor = MethodType(fake_reject, planner)
    planner._restart_after_failed_dig = MethodType(fake_restart, planner)
    planner._complete_cell_entry_dig = MethodType(fake_complete_cell, planner)
    planner._complete_coverage_dig = MethodType(fake_complete_dig, planner)
    planner._set_skill = MethodType(fake_set_skill, planner)

    planner._apply_requested_tick_effects(
        obs,
        (
            IncrementDigExitGuardReplanCountEffect(),
            IncrementDigBadReplanCountEffect(),
            RejectActiveCoverageCorridorEffect(reason="bad_dig_low_payload"),
            RestartAfterFailedDigEffect(reason="bad_dig_low_payload"),
            CompleteCellEntryDigCompatibilityEffect(),
            CompleteCoverageDigEffect(),
            SwitchSkillEffect(
                target_skill_name="carry",
                switch_reason="dig_to_carry_loaded",
            ),
        ),
    )

    assert events == [
        "reject:bad_dig_low_payload",
        "restart:bad_dig_low_payload",
        "cell",
        "coverage",
        "skill:carry:dig_to_carry_loaded",
    ]
    assert cycle_state.dig_exit_guard_replan_count == 1
    assert cycle_state.dig_bad_replan_count == 1


def test_primitive_planner_unknown_skill_fails_without_broad_legacy_fallback() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    planner._skill_name = "legacy_skill"
    planner._switch_reason = ""
    obs: dict[str, Any] = {"qpos": [1.0]}
    boundary_event = object()
    calls: list[tuple[dict[str, Any], object, str]] = []

    def fake_maybe_switch_skill(
        self: PrimitivePlannerACTPolicy,
        *,
        obs: dict[str, Any],
        boundary_event: object,
    ) -> None:
        calls.append((obs, boundary_event, str(self._skill_name)))
        self._skill_name = "carry"
        self._switch_reason = "legacy_to_carry"

    planner._maybe_switch_skill = MethodType(fake_maybe_switch_skill, planner)
    _install_fake_decision_status_provider(planner)

    try:
        planner._decide_tick_with_legacy_fsm(
            obs=obs,
            boundary_event=boundary_event,
            preparation=PrimitiveTickPreparation(
                boundary_event=boundary_event,
                skill_name_before_decision="legacy_skill",
                dig_progress_updated=False,
            ),
        )
    except PrimitiveDecisionContractError as exc:
        message = str(exc)
    else:
        raise AssertionError("unknown skill unexpectedly used broad legacy fallback")

    assert calls == []
    assert "unhandled planner skill" in message
    assert "broad legacy fallback is retired" in message


def test_primitive_planner_decision_bridge_delegates_to_decision_runtime() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    obs: dict[str, Any] = {"qpos": [1.0]}
    boundary_event = object()
    expected = PrimitiveDecisionResult.from_requested_effects(
        decision_source="test_runner",
        status="no_change",
        skill_before="dig",
        skill_after="dig",
        switch_reason="",
        effects=(),
    )
    calls: list[tuple[dict[str, Any], object, PrimitiveTickPreparation]] = []

    class FakeRuntime:
        def decide_tick(self, *, obs, boundary_event, preparation):
            calls.append((obs, boundary_event, preparation))
            return expected

    planner._decision_runtime = MethodType(
        lambda self: FakeRuntime(),
        planner,
    )
    planner._legacy_fsm_branch_ports = MethodType(
        lambda self: (_ for _ in ()).throw(
            AssertionError("policy bridge should delegate to decision runtime")
        ),
        planner,
    )

    preparation = PrimitiveTickPreparation(
        boundary_event=boundary_event,
        skill_name_before_decision="dig",
        dig_progress_updated=True,
    )
    result = planner._decide_tick_with_legacy_fsm(
        obs=obs,
        boundary_event=boundary_event,
        preparation=preparation,
    )

    assert result is expected
    assert calls == [(obs, boundary_event, preparation)]


def test_primitive_planner_mainline_miss_does_not_call_broad_legacy_fallback() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    obs: dict[str, Any] = {"qpos": [1.0]}
    calls: list[str] = []

    class FailingRuntime:
        def decide_tick(self, *, obs, boundary_event, preparation):
            calls.append("runtime")
            raise PrimitiveDecisionContractError(
                "unhandled planner skill in requested branch chain; broad legacy "
                "fallback is retired for default decisions: 'dig'"
            )

    planner._decision_runtime = MethodType(
        lambda self: FailingRuntime(),
        planner,
    )
    planner._maybe_switch_skill = MethodType(
        lambda self, *, obs, boundary_event: (_ for _ in ()).throw(
            AssertionError("broad legacy fallback should not be called")
        ),
        planner,
    )

    try:
        planner._decide_tick_with_legacy_fsm(
            obs=obs,
            boundary_event=None,
            preparation=PrimitiveTickPreparation(
                boundary_event=None,
                skill_name_before_decision="dig",
                dig_progress_updated=True,
            ),
        )
    except PrimitiveDecisionContractError as exc:
        message = str(exc)
    else:
        raise AssertionError("unhandled mainline branch miss was silently accepted")

    assert calls == ["runtime"]
    assert "unhandled planner skill" in message
    assert "broad legacy fallback" in message


def test_primitive_planner_pre_dig_align_uses_explicit_residual_path() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    obs: dict[str, Any] = {"qpos": [1.0]}
    expected = PrimitiveDecisionResult.from_legacy_fsm_outcome(
        decision_source=RESIDUAL_PRE_DIG_ALIGN_DECISION_SOURCE,
        skill_before="pre_dig_align",
        skill_after="dig",
        switch_reason="pre_dig_align_to_dig_ready",
    )
    calls: list[tuple[dict[str, Any], None, PrimitiveTickPreparation]] = []

    class FakeRuntime:
        def decide_tick(self, *, obs, boundary_event, preparation):
            calls.append((obs, boundary_event, preparation))
            return expected

    planner._decision_runtime = MethodType(
        lambda self: FakeRuntime(),
        planner,
    )
    planner._maybe_switch_skill = MethodType(
        lambda self, *, obs, boundary_event: (_ for _ in ()).throw(
            AssertionError("broad legacy fallback should not be called")
        ),
        planner,
    )

    result = planner._decide_tick_with_legacy_fsm(
        obs=obs,
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="pre_dig_align",
            dig_progress_updated=False,
        ),
    )

    assert calls == [
        (
            obs,
            None,
            PrimitiveTickPreparation(
                boundary_event=None,
                skill_name_before_decision="pre_dig_align",
                dig_progress_updated=False,
            ),
        )
    ]
    assert result is expected
    assert result.side_effects_applied is True
    assert result.skill_before == "pre_dig_align"
    assert result.skill_after == "dig"
    assert result.switch_reason == "pre_dig_align_to_dig_ready"


def test_primitive_planner_maybe_switch_skill_applies_requested_compat_result() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    obs: dict[str, Any] = {"qpos": [1.0]}
    boundary_event = object()
    effect = SwitchSkillEffect(
        target_skill_name="carry",
        switch_reason="dig_to_carry_loaded",
    )
    result = PrimitiveDecisionResult.from_requested_effects(
        decision_source="compat_dig",
        status="skill_switch",
        skill_before="dig",
        skill_after="carry",
        switch_reason="dig_to_carry_loaded",
        effects=(effect,),
    )
    calls: list[Any] = []

    class FakeRuntime:
        def decide_legacy_compatibility_tick(self, *, obs, boundary_event, preparation):
            calls.append(("decide", obs, boundary_event, preparation))
            return result

    planner._skill_name = "dig"
    planner._decision_runtime = MethodType(
        lambda self: FakeRuntime(),
        planner,
    )
    planner._apply_requested_tick_effects = MethodType(
        lambda self, got_obs, effects: calls.append(("apply", got_obs, effects)),
        planner,
    )

    planner._maybe_switch_skill(obs=obs, boundary_event=boundary_event)

    assert calls == [
        (
            "decide",
            obs,
            boundary_event,
            PrimitiveTickPreparation(
                boundary_event=boundary_event,
                skill_name_before_decision="dig",
                dig_progress_updated=True,
            ),
        ),
        ("apply", obs, (effect,)),
    ]


def test_primitive_planner_maybe_switch_skill_does_not_reapply_already_applied_residual() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    obs: dict[str, Any] = {"qpos": [1.0]}
    result = PrimitiveDecisionResult.from_legacy_fsm_outcome(
        decision_source=RESIDUAL_PRE_DIG_ALIGN_DECISION_SOURCE,
        skill_before="pre_dig_align",
        skill_after="dig",
        switch_reason="pre_dig_align_to_dig_ready",
    )
    calls: list[Any] = []

    class FakeRuntime:
        def decide_legacy_compatibility_tick(self, *, obs, boundary_event, preparation):
            calls.append(("decide", obs, boundary_event, preparation))
            return result

    planner._skill_name = "pre_dig_align"
    planner._decision_runtime = MethodType(
        lambda self: FakeRuntime(),
        planner,
    )
    planner._apply_requested_tick_effects = MethodType(
        lambda self, got_obs, effects: calls.append(("apply", got_obs, effects)),
        planner,
    )

    planner._maybe_switch_skill(obs=obs, boundary_event=None)

    assert calls == [
        (
            "decide",
            obs,
            None,
            PrimitiveTickPreparation(
                boundary_event=None,
                skill_name_before_decision="pre_dig_align",
                dig_progress_updated=False,
            ),
        )
    ]


def test_primitive_planner_maybe_switch_skill_noops_when_compatibility_misses() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    obs: dict[str, Any] = {"qpos": [1.0]}
    calls: list[Any] = []

    class FakeRuntime:
        def decide_legacy_compatibility_tick(self, *, obs, boundary_event, preparation):
            calls.append(("decide", obs, boundary_event, preparation))
            return None

    planner._skill_name = "legacy_skill"
    planner._decision_runtime = MethodType(
        lambda self: FakeRuntime(),
        planner,
    )
    planner._apply_requested_tick_effects = MethodType(
        lambda self, got_obs, effects: calls.append(("apply", got_obs, effects)),
        planner,
    )

    planner._maybe_switch_skill(obs=obs, boundary_event=None)

    assert calls == [
        (
            "decide",
            obs,
            None,
            PrimitiveTickPreparation(
                boundary_event=None,
                skill_name_before_decision="legacy_skill",
                dig_progress_updated=False,
            ),
        )
    ]


def test_primitive_planner_bootstrap_decision_bridge_returns_requested_switch() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    planner._skill_name = "bootstrap"
    planner._switch_reason = ""
    obs: dict[str, Any] = {"qpos": [1.0]}
    boundary_event = object()
    calls: list[tuple[str, str]] = []

    def fake_set_skill(
        self: PrimitivePlannerACTPolicy,
        skill_name: str,
        reason: str,
    ) -> None:
        calls.append((skill_name, reason))

    planner._set_skill = MethodType(fake_set_skill, planner)
    planner._should_end_bootstrap = MethodType(
        lambda self, *, obs, boundary_event: True,
        planner,
    )
    planner.bootstrap_end_mode = "first_qualified_dig_start"
    planner._should_pre_dig_align_before_dig = MethodType(
        lambda self: False,
        planner,
    )
    _install_fake_decision_status_provider(planner)

    result = planner._decide_tick_with_legacy_fsm(
        obs=obs,
        boundary_event=boundary_event,
        preparation=PrimitiveTickPreparation(
            boundary_event=boundary_event,
            skill_name_before_decision="bootstrap",
            dig_progress_updated=False,
        ),
    )

    assert calls == []
    assert result.side_effects_applied is False
    assert result.skill_before == "bootstrap"
    assert result.skill_after == "dig"
    assert result.switch_reason == "bootstrap_to_dig"
    assert result.effects == (
        SwitchSkillEffect(
            target_skill_name="dig",
            switch_reason="bootstrap_to_dig",
        ),
    )


def test_primitive_planner_return_decision_bridge_returns_requested_effects() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    planner._skill_name = "return"
    planner._switch_reason = ""
    obs: dict[str, Any] = {"qpos": [1.0]}
    calls: list[str] = []

    _install_fake_decision_status_provider(
        planner,
        return_status=ReturnTransitionStatus(
            mass_in_bucket_kg=0.0,
            min_distance_to_dig_area_m=0.0,
            bucket_depth_below_dig_area_plane_m=0.0,
            semantic_boundary_profile_active=True,
            next_dig_event=True,
            next_or_seen_dig_event=True,
            entry_close=True,
            start_envelope_ready=True,
            handoff_ready=True,
            direct_handoff_ready=False,
            shallow_guard_ready=False,
            shallow_guard_allowed=False,
            completed_transition=True,
            next_skill="dig",
            switch_reason="return_to_dig_next_dig_entry_ready",
        ),
    )
    planner._mark_return_next_dig_event_seen = MethodType(
        lambda self: calls.append("mark"),
        planner,
    )
    planner._complete_return_transition_for_backend = MethodType(
        lambda self: calls.append("complete"),
        planner,
    )
    planner._next_skill_after_return_transition = MethodType(
        lambda self: "dig",
        planner,
    )
    planner._set_skill = MethodType(
        lambda self, skill_name, reason: calls.append(f"{skill_name}:{reason}"),
        planner,
    )

    result = planner._decide_tick_with_legacy_fsm(
        obs=obs,
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="return",
            dig_progress_updated=False,
        ),
    )

    assert calls == []
    assert result.side_effects_applied is False
    assert result.status == "skill_switch"
    assert result.effects == (
        MarkReturnNextDigEventSeenEffect(),
        CompleteReturnTransitionEffect(),
        SwitchToNextSkillAfterReturnEffect(reason_suffix="next_dig_entry_ready"),
    )


def test_primitive_planner_carry_decision_bridge_returns_requested_effects() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    planner._skill_name = "carry"
    planner._switch_reason = ""
    obs: dict[str, Any] = {"qpos": [1.0]}
    callbacks: list[str] = []

    _install_fake_decision_status_provider(
        planner,
        carry_status=CarryTransitionStatus(
            mass_in_bucket_kg=120.0,
            deposited_mass_in_target_box_kg=8.5,
            deposit_delta_since_cycle_start_kg=8.5,
            semantic_boundary_profile_active=True,
            dump_committed_event=True,
            release_onset_event=False,
            dump_complete_event=False,
            legacy_dump_start_event=False,
            carry_release_safety_done=False,
            dump_ready=False,
            next_dump_ready_hold_count=3,
            ready_to_dump=True,
            carry_to_dump_reason="dump_committed_boundary",
            carry_to_return_reason="",
        ),
    )
    planner._complete_coverage_dump = MethodType(
        lambda self, obs, reason: callbacks.append(f"complete:{reason}"),
        planner,
    )
    planner._set_return_or_direct_handoff = MethodType(
        lambda self, obs, reason: callbacks.append(f"return:{reason}"),
        planner,
    )
    planner._set_dump_ready_hold_count = MethodType(
        lambda self, value: callbacks.append(f"hold:{value}"),
        planner,
    )
    planner._deposited_mass = MethodType(lambda self, obs: 8.5, planner)
    planner._set_dump_start_deposited_mass = MethodType(
        lambda self, value: callbacks.append(f"deposit:{value}"),
        planner,
    )
    planner._set_skill = MethodType(
        lambda self, skill, reason: callbacks.append(f"{skill}:{reason}"),
        planner,
    )

    result = planner._decide_tick_with_legacy_fsm(
        obs=obs,
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="carry",
            dig_progress_updated=False,
        ),
    )

    assert callbacks == []
    assert result.side_effects_applied is False
    assert result.effects == (
        SetDumpReadyHoldCountEffect(value=3),
        SetDumpStartDepositedMassFromObservationEffect(),
        SwitchSkillEffect(
            target_skill_name="dump",
            switch_reason="carry_to_dump_dump_committed_boundary",
        ),
    )


def test_primitive_planner_dump_decision_bridge_returns_requested_effects() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    planner._skill_name = "dump"
    planner._switch_reason = ""
    obs: dict[str, Any] = {"qpos": [1.0]}
    callbacks: list[str] = []

    _install_fake_decision_status_provider(
        planner,
        dump_status=DumpTransitionStatus(
            mass_in_bucket_kg=5.0,
            deposited_mass_in_target_box_kg=20.0,
            deposit_delta_since_dump_start_kg=10.0,
            semantic_boundary_profile_active=False,
            dump_complete_event=False,
            legacy_dump_end_event=False,
            boundary_dump_done=False,
            dump_done_mass_low=True,
            next_dump_done_hold_count=2,
            ready_to_return=True,
            coverage_completion_reason="dump_mass_low",
            dump_to_return_reason="dump_to_return_mass_low",
        ),
    )
    planner._complete_coverage_dump = MethodType(
        lambda self, obs, reason: callbacks.append(f"complete:{reason}"),
        planner,
    )
    planner._set_return_or_direct_handoff = MethodType(
        lambda self, obs, reason: callbacks.append(f"return:{reason}"),
        planner,
    )
    planner._set_dump_done_hold_count = MethodType(
        lambda self, value: callbacks.append(f"done:{value}"),
        planner,
    )

    result = planner._decide_tick_with_legacy_fsm(
        obs=obs,
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="dump",
            dig_progress_updated=False,
        ),
    )

    assert callbacks == []
    assert result.side_effects_applied is False
    assert result.effects == (
        SetDumpDoneHoldCountEffect(value=2),
        CompleteCoverageDumpEffect(reason="dump_mass_low"),
        SetReturnOrDirectHandoffEffect(reason="dump_to_return_mass_low"),
    )


def test_primitive_planner_dig_decision_bridge_returns_requested_effects() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    planner._skill_name = "dig"
    planner._switch_reason = ""
    obs: dict[str, Any] = {"qpos": [1.0]}
    callbacks: list[str] = []

    _install_fake_decision_status_provider(
        planner,
        dig_status=_default_dig_status(
            dig_to_carry_ready=True,
            dig_to_carry_reason="boundary_confirmed",
        ),
    )
    planner._increment_dig_exit_guard_replan_count = MethodType(
        lambda self: callbacks.append("exit_count"),
        planner,
    )
    planner._reject_active_coverage_corridor = MethodType(
        lambda self, obs, reason: callbacks.append(f"reject:{reason}"),
        planner,
    )
    planner._restart_after_failed_dig = MethodType(
        lambda self, reason, obs: callbacks.append(f"restart:{reason}"),
        planner,
    )
    planner._increment_dig_bad_replan_count = MethodType(
        lambda self: callbacks.append("bad_count"),
        planner,
    )
    planner._complete_cell_entry_dig = MethodType(
        lambda self, obs: callbacks.append("cell"),
        planner,
    )
    planner._complete_coverage_dig = MethodType(
        lambda self, obs: callbacks.append("coverage"),
        planner,
    )
    planner._set_skill = MethodType(
        lambda self, skill, reason: callbacks.append(f"{skill}:{reason}"),
        planner,
    )

    result = planner._decide_tick_with_legacy_fsm(
        obs=obs,
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="dig",
            dig_progress_updated=True,
        ),
    )

    assert callbacks == []
    assert result.side_effects_applied is False
    assert result.status == "skill_switch"
    assert result.effects == (
        CompleteCellEntryDigCompatibilityEffect(),
        CompleteCoverageDigEffect(),
        SwitchSkillEffect(
            target_skill_name="carry",
            switch_reason="dig_to_carry_boundary_confirmed",
        ),
    )


def test_primitive_planner_dig_transition_status_provider_maps_inputs_and_syncs_mirror_explicitly() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    planner.action_dim = 1
    planner.boundary_detector = SimpleNamespace(
        config=SimpleNamespace(boundary_profile="legacy")
    )
    planner._coverage_terminal_stop_requested = False
    planner._dig_step_count = 12
    planner._dig_mass_plateau_count = 4
    planner.dig_to_carry_min_distance_to_dig_area_m = 0.5
    planner.dig_to_carry_min_bucket_mass_kg = 20.0
    planner.dig_to_carry_target_bucket_mass_kg = 20.0
    planner.dig_to_carry_mass_plateau_enabled = True
    planner.dig_to_carry_mass_plateau_min_bucket_mass_kg = 5.0
    planner.dig_to_carry_mass_plateau_hold_steps = 3
    planner.dig_to_carry_mass_plateau_min_steps = 5
    planner.dump_ready_min_bucket_mass_kg = 10.0
    planner.dig_bad_replan_enabled = True
    planner.dig_bad_replan_max_steps = 10
    planner.dig_bad_replan_min_bucket_mass_kg = 3.0
    planner.dig_exit_guard_enabled = True
    planner.dig_exit_guard_min_steps = 10
    planner.dig_exit_guard_min_bucket_mass_kg = 3.0
    planner.dig_exit_guard_overshoot_m = 0.65
    planner._dig_to_carry_reason = "stale"
    coverage_state = planner._coverage_runtime_state()
    coverage_state.set_coverage_corridors(
        [
            CoverageCorridorState(
                corridor_id=5,
                entry_x_m=0.0,
                entry_z_m=0.0,
                exit_x_m=1.0,
                exit_z_m=0.0,
            )
        ]
    )
    coverage_state.set_active_corridor_id(5)
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX] = 1.7
    env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX] = 0.0
    env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX] = 0.0
    _set_minimal_non_dig_capability_fields(planner)

    loaded_status = planner._dig_transition_status_for_backend(
        {
            "qpos": [0.0],
            "env_state": env_state,
            "task_metrics": {
                "mass_in_bucket_kg": 25.0,
                "min_distance_to_dig_area_m": 1.0,
            },
        },
        boundary_event=None,
    )

    assert loaded_status.dig_step_count == 12
    assert loaded_status.dig_to_carry_ready is True
    assert loaded_status.dig_to_carry_reason == "loaded"
    assert loaded_status.dig_exit_guard_ready is False
    assert loaded_status.dig_bad_replan_ready is False
    assert planner._dig_to_carry_reason == "stale"
    planner._primitive_fsm_capability_provider().sync_dig_transition_reason(
        loaded_status
    )
    assert planner._dig_to_carry_reason == "loaded"

    low_payload_status = planner._dig_transition_status_for_backend(
        {
            "qpos": [0.0],
            "env_state": env_state,
            "task_metrics": {
                "mass_in_bucket_kg": 1.0,
                "min_distance_to_dig_area_m": 0.0,
            },
        },
        boundary_event=None,
    )

    assert low_payload_status.dig_exit_guard_ready is True
    assert low_payload_status.dig_bad_replan_ready is True
    assert low_payload_status.dig_to_carry_ready is False
    assert low_payload_status.dig_to_carry_reason == ""
    assert planner._dig_to_carry_reason == "loaded"
    planner._primitive_fsm_capability_provider().sync_dig_transition_reason(
        low_payload_status
    )
    assert planner._dig_to_carry_reason == ""


def test_primitive_planner_legacy_branch_ports_use_capability_provider_methods() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    planner._skill_name = "dig"
    planner._switch_reason = ""
    planner.bootstrap_end_mode = "first_qualified_dig_start"
    planner._should_end_bootstrap = MethodType(
        lambda self, *, obs, boundary_event: False,
        planner,
    )
    planner._should_pre_dig_align_before_dig = MethodType(lambda self: False, planner)
    planner._maybe_handle_pre_dig_align_skill = MethodType(lambda self, obs: False, planner)
    provider = _FakePrimitiveFSMCapabilityProvider()
    planner._primitive_fsm_capability_provider = MethodType(
        lambda self: provider,
        planner,
    )

    ports = planner._legacy_fsm_branch_ports()

    context = SimpleNamespace(obs={}, boundary_event=None)
    assert ports.facts_source.backend_facts(context).dig_transition().status == "dig_status"
    assert (
        ports.facts_source.backend_facts(context).carry_transition().status
        == "carry_status"
    )
    assert (
        ports.facts_source.backend_facts(context).dump_transition().status
        == "dump_status"
    )
    assert (
        ports.facts_source.backend_facts(context).return_transition().status
        == "return_status"
    )
    assert provider.calls == ["dig", "carry", "dump", "return"]
    for removed_name in (
        "capabilities",
        "current_skill_name",
        "should_end_bootstrap",
        "dig_transition_status",
        "carry_transition_status",
        "dump_transition_status",
        "return_transition_status",
    ):
        assert not hasattr(ports, removed_name)


def test_primitive_planner_transition_status_wrappers_delegate_to_provider() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    provider = _FakePrimitiveFSMCapabilityProvider()
    planner._primitive_fsm_capability_provider = MethodType(
        lambda self: provider,
        planner,
    )

    assert planner._dig_transition_status_for_backend({}, None) == "dig_status"
    assert planner._carry_transition_status_for_backend({}, None) == "carry_status"
    assert planner._dump_transition_status_for_backend({}, None) == "dump_status"
    assert planner._return_transition_status_for_backend({}, None) == "return_status"
    assert provider.calls == ["dig", "carry", "dump", "return"]
