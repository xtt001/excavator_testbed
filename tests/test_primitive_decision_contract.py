from __future__ import annotations

from types import MethodType
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from testbed.data.schema import (
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX,
)
from testbed.planner.primitive.coverage.selection import CoverageCorridorState
from testbed.planner.primitive.facts.capabilities import (
    CarryTransitionStatus,
    DigTransitionStatus,
    DumpTransitionStatus,
    ReturnTransitionStatus,
)
from testbed.planner.primitive.decision.backends.legacy_capability_provider import (
    PrimitiveFSMCapabilityProvider,
    PrimitiveFSMCapabilityProviderConfig,
    PrimitiveFSMCapabilityProviderPorts,
)
from testbed.planner.primitive.decision import contracts as primitive_decision
from testbed.planner.primitive.decision.backends.legacy_fsm import (
    LegacyFSMBranchPorts,
    LegacyFSMDecisionBackendFactory,
)
from testbed.planner.primitive.decision.contracts import (
    LEGACY_FSM_DECISION_SOURCE,
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
from testbed.planner.primitive.decision.capabilities import (
    PrimitiveDecisionCapabilities,
    PrimitiveDecisionCapabilitiesPorts,
)
from testbed.planner.primitive.decision.runtime import (
    LEGACY_FSM_DECISION_BACKEND_NAME,
    PrimitiveDecisionRuntime,
    PrimitiveDecisionRuntimePorts,
)
from testbed.planner.primitive.execution.runtime import PrimitiveTickPreparation
from testbed.planner.primitive.effects.return_handoff import (
    ReturnHandoffReadinessConfig,
    ReturnStartEnvelopeGateConfig,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


_OLD_TRANSITION_STATUS_POLICY_WRAPPERS = (
    "_dig_transition_status_for_backend",
    "_carry_transition_status_for_backend",
    "_dump_transition_status_for_backend",
    "_return_transition_status_for_backend",
)

_OLD_CAPABILITY_COMPOSITION_POLICY_WRAPPERS = (
    "_decision_runtime_ports",
    "_legacy_fsm_backend_factory",
    "_legacy_fsm_branch_ports",
    "_primitive_decision_capabilities",
    "_primitive_decision_capabilities_ports",
    "_primitive_fsm_capability_provider",
    "_primitive_fsm_capability_provider_ports",
)


def _minimal_return_handoff_config(
    *,
    action_dim: int = 4,
) -> ReturnHandoffReadinessConfig:
    return ReturnHandoffReadinessConfig(
        return_target_planner_enabled=False,
        max_entry_error_m=None,
        max_bucket_mass_kg=0.0,
        start_envelope_direct_handoff_enabled=False,
        start_envelope_gate=ReturnStartEnvelopeGateConfig(
            enabled=False,
            action_dim=int(action_dim),
            spatial_tolerance=0.0,
            depth_tolerance_m=0.0,
            local_depth_tolerance_m=0.0,
            plane_depth_tolerance_m=0.0,
            plane_depth_mode="range",
            qpos_tolerance=0.0,
            require_contact=False,
        ),
    )


class _FakeCoverageEffectRuntime:
    def __init__(self, events: list[str], expected_obs: dict[str, Any]) -> None:
        self._events = events
        self._expected_obs = expected_obs

    def complete_coverage_dump(
        self,
        got_obs: dict[str, Any],
        *,
        reason: str,
    ) -> None:
        assert got_obs is self._expected_obs
        self._events.append(f"complete:{reason}")

    def reject_active_coverage_corridor(
        self,
        got_obs: dict[str, Any],
        *,
        reason: str,
    ) -> None:
        assert got_obs is self._expected_obs
        self._events.append(f"reject:{reason}")

    def complete_coverage_dig(self, got_obs: dict[str, Any]) -> None:
        assert got_obs is self._expected_obs
        self._events.append("coverage")


class _FakeDigRecoveryService:
    def __init__(self, events: list[str], expected_obs: dict[str, Any]) -> None:
        self._events = events
        self._expected_obs = expected_obs

    def restart_after_failed_dig(self, reason: str, got_obs: dict[str, Any]) -> None:
        assert got_obs is self._expected_obs
        self._events.append(f"restart:{reason}")


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
    capabilities = PrimitiveDecisionCapabilities.from_ports(
        PrimitiveDecisionCapabilitiesPorts(
            current_skill_name=lambda: str(planner._skill_name),
            current_switch_reason=lambda: str(planner._switch_reason),
            should_end_bootstrap=getattr(
                planner,
                "_should_end_bootstrap",
                lambda *, obs, boundary_event: False,
            ),
            bootstrap_end_mode=lambda: str(
                getattr(planner, "bootstrap_end_mode", "first_qualified_dig_start")
            ),
            transition_status_provider=provider,
        )
    )
    branch_ports = LegacyFSMBranchPorts(
        bootstrap_skill_name="bootstrap",
        dig_skill_name="dig",
        carry_skill_name="carry",
        dump_skill_name="dump",
        return_skill_name="return",
        facts_source=capabilities.facts_source(),
        compatibility_actions=capabilities.compatibility_actions(),
    )
    runtime = PrimitiveDecisionRuntime.from_ports(
        PrimitiveDecisionRuntimePorts(
            backend_factories={
                LEGACY_FSM_DECISION_BACKEND_NAME: (
                    lambda: LegacyFSMDecisionBackendFactory.from_ports(branch_ports)
                ),
            }
        )
    )
    planner._decision_runtime = MethodType(
        lambda self: runtime,
        planner,
    )
    return provider


def _set_minimal_non_dig_capability_fields(planner: PrimitivePlannerACTPolicy) -> None:
    planner._coverage_runtime_state().coverage_cycle_start_deposit_kg = 0.0
    cycle_state = planner._primitive_cycle_runtime_state()
    cycle_state.dump_ready_hold_count = 0
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
    cycle_state.dump_start_deposited_mass_kg = 0.0
    cycle_state.dump_done_hold_count = 0
    planner.dump_done_hold_steps = 1
    planner.return_to_dig_start_envelope_direct_handoff_enabled = False
    planner.return_to_dig_start_envelope_gate_enabled = False
    planner.return_to_dig_shallow_guard_enabled = False
    planner.return_to_dig_max_bucket_mass_kg = 0.0
    planner.return_to_dig_touch_tolerance_m = 0.0
    planner.return_to_dig_min_depth_m = 0.0
    planner.return_to_dig_max_depth_m = 0.0
    planner.return_to_dig_max_entry_error_m = None
    planner._primitive_return_handoff_config = _minimal_return_handoff_config(
        action_dim=int(getattr(planner, "action_dim", 4))
    )


def _fsm_capability_provider_from_config(
    planner: PrimitivePlannerACTPolicy,
    *,
    config: PrimitiveFSMCapabilityProviderConfig,
) -> PrimitiveFSMCapabilityProvider:
    return PrimitiveFSMCapabilityProvider.from_ports(
        PrimitiveFSMCapabilityProviderPorts(
            config=config,
            semantic_boundary_profile_active=(
                lambda: planner._semantic_boundary_profile_active()
            ),
            cycle_state=planner._primitive_cycle_runtime_state(),
            coverage_state=planner._coverage_runtime_state(),
            return_state=planner._primitive_return_runtime_state(),
            return_handoff_readiness_service=(
                planner._primitive_return_handoff_runtime().readiness_service()
            ),
        )
    )


def _apply_legacy_compatibility_decision(
    planner: PrimitivePlannerACTPolicy,
    *,
    obs: dict[str, Any],
    boundary_event: Any | None,
) -> PrimitiveDecisionResult | None:
    skill_before = str(planner._skill_name)
    result = planner._decision_runtime().decide_legacy_compatibility_tick(
        obs=obs,
        boundary_event=boundary_event,
        preparation=PrimitiveTickPreparation(
            boundary_event=boundary_event,
            skill_name_before_decision=skill_before,
            dig_progress_updated=skill_before == "dig",
        ),
    )
    if result is not None and not result.side_effects_applied:
        planner._primitive_requested_effect_runtime().apply(obs, result.effects)
    return result


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
        "complete_coverage_dig",
    ]
    assert effects[2].reason == "bad_dig_low_payload"
    assert effects[3].reason == "bad_dig_low_payload"


def test_cell_entry_compatibility_effect_is_removed_from_decision_contract() -> None:
    assert not hasattr(primitive_decision, "CompleteCellEntryDigCompatibilityEffect")


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


def test_primitive_planner_unknown_skill_fails_without_broad_legacy_fallback() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    planner._skill_name = "legacy_skill"
    planner._switch_reason = ""
    obs: dict[str, Any] = {
        "qpos": [1.0],
        "task_metrics": {"deposited_mass_in_target_box_kg": 8.5},
    }
    boundary_event = object()
    _install_fake_decision_status_provider(planner)

    try:
        planner._decision_runtime().decide_tick(
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

    preparation = PrimitiveTickPreparation(
        boundary_event=boundary_event,
        skill_name_before_decision="dig",
        dig_progress_updated=True,
    )
    result = planner._decision_runtime().decide_tick(
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

    try:
        planner._decision_runtime().decide_tick(
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


def test_primitive_planner_pre_dig_align_is_unhandled_after_cleanup() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    obs: dict[str, Any] = {"qpos": [1.0]}
    calls: list[tuple[dict[str, Any], None, PrimitiveTickPreparation]] = []

    class FakeRuntime:
        def decide_tick(self, *, obs, boundary_event, preparation):
            calls.append((obs, boundary_event, preparation))
            raise PrimitiveDecisionContractError("unhandled planner skill: pre_dig_align")

    planner._decision_runtime = MethodType(
        lambda self: FakeRuntime(),
        planner,
    )

    with pytest.raises(PrimitiveDecisionContractError, match="pre_dig_align"):
        planner._decision_runtime().decide_tick(
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


def test_primitive_planner_legacy_compatibility_applies_requested_compat_result() -> None:
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
    class FakeApplier:
        def apply(self, got_obs, effects):
            calls.append(("apply", got_obs, effects))

    planner._primitive_requested_effect_runtime = MethodType(
        lambda self: FakeApplier(),
        planner,
    )

    assert (
        _apply_legacy_compatibility_decision(
            planner,
            obs=obs,
            boundary_event=boundary_event,
        )
        is result
    )

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


def test_primitive_planner_legacy_compatibility_propagates_removed_pre_dig_error() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    obs: dict[str, Any] = {"qpos": [1.0]}
    calls: list[Any] = []

    class FakeRuntime:
        def decide_legacy_compatibility_tick(self, *, obs, boundary_event, preparation):
            calls.append(("decide", obs, boundary_event, preparation))
            raise PrimitiveDecisionContractError("unhandled planner skill: pre_dig_align")

    planner._skill_name = "pre_dig_align"
    planner._decision_runtime = MethodType(
        lambda self: FakeRuntime(),
        planner,
    )
    class FakeApplier:
        def apply(self, got_obs, effects):
            calls.append(("apply", got_obs, effects))

    planner._primitive_requested_effect_runtime = MethodType(
        lambda self: FakeApplier(),
        planner,
    )

    with pytest.raises(PrimitiveDecisionContractError, match="pre_dig_align"):
        _apply_legacy_compatibility_decision(
            planner,
            obs=obs,
            boundary_event=None,
        )

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


def test_primitive_planner_legacy_compatibility_noops_when_compatibility_misses() -> None:
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
    class FakeApplier:
        def apply(self, got_obs, effects):
            calls.append(("apply", got_obs, effects))

    planner._primitive_requested_effect_runtime = MethodType(
        lambda self: FakeApplier(),
        planner,
    )

    assert (
        _apply_legacy_compatibility_decision(
            planner,
            obs=obs,
            boundary_event=None,
        )
        is None
    )

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
    _install_fake_decision_status_provider(planner)

    result = planner._decision_runtime().decide_tick(
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
    planner._set_skill = MethodType(
        lambda self, skill_name, reason: calls.append(f"{skill_name}:{reason}"),
        planner,
    )

    result = planner._decision_runtime().decide_tick(
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
    planner._set_skill = MethodType(
        lambda self, skill, reason: callbacks.append(f"{skill}:{reason}"),
        planner,
    )

    result = planner._decision_runtime().decide_tick(
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
    result = planner._decision_runtime().decide_tick(
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
    planner._set_skill = MethodType(
        lambda self, skill, reason: callbacks.append(f"{skill}:{reason}"),
        planner,
    )

    result = planner._decision_runtime().decide_tick(
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
    planner._coverage_runtime_state().coverage_terminal_stop_requested = False
    cycle_state = planner._primitive_cycle_runtime_state()
    cycle_state.dig_step_count = 12
    cycle_state.dig_mass_plateau_count = 4
    cycle_state.dig_to_carry_reason = "stale"
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

    capability_provider = _fsm_capability_provider_from_config(
        planner,
        config=PrimitiveFSMCapabilityProviderConfig(
            action_dim=1,
            dig_to_carry_min_distance_to_dig_area_m=0.5,
            dig_to_carry_min_bucket_mass_kg=20.0,
            dig_to_carry_target_bucket_mass_kg=20.0,
            dig_to_carry_mass_plateau_enabled=True,
            dig_to_carry_mass_plateau_min_bucket_mass_kg=5.0,
            dig_to_carry_mass_plateau_hold_steps=3,
            dig_to_carry_mass_plateau_min_steps=5,
            dump_ready_min_bucket_mass_kg=10.0,
            dig_bad_replan_enabled=True,
            dig_bad_replan_max_steps=10,
            dig_bad_replan_min_bucket_mass_kg=3.0,
            dig_exit_guard_enabled=True,
            dig_exit_guard_min_steps=10,
            dig_exit_guard_min_bucket_mass_kg=3.0,
            dig_exit_guard_overshoot_m=0.65,
            dump_ready_hold_steps=1,
            dump_ready_min_height_above_rim_m=0.0,
            dump_ready_require_over_footprint=False,
            dump_ready_require_clearance=False,
            dump_ready_max_horizontal_distance_m=None,
            dump_ready_position_mode="footprint",
            dump_ready_max_dump_area_footprint_outside_distance_m=None,
            dump_ready_min_dump_area_relative_x_m=None,
            dump_ready_max_dump_area_relative_x_m=None,
            dump_ready_min_dump_area_relative_z_m=None,
            dump_ready_max_dump_area_relative_z_m=None,
            dump_ready_near_window_enabled=False,
            dump_ready_near_window_x_tolerance_m=0.0,
            dump_ready_near_window_z_tolerance_m=0.0,
            dump_ready_near_window_outside_tolerance_m=0.0,
            dump_ready_near_window_require_over_footprint=False,
            dump_done_max_bucket_mass_kg=0.0,
            dump_done_min_deposit_delta_kg=0.0,
            dump_done_use_boundary_event=False,
            dump_done_hold_steps=1,
            return_to_dig_start_envelope_direct_handoff_enabled=False,
            return_to_dig_start_envelope_gate_enabled=False,
            return_to_dig_shallow_guard_enabled=False,
            return_to_dig_max_bucket_mass_kg=0.0,
            return_to_dig_touch_tolerance_m=0.0,
            return_to_dig_min_depth_m=0.0,
            return_to_dig_max_depth_m=0.0,
            return_to_dig_max_entry_error_m=None,
        ),
    )
    loaded_status = capability_provider.dig_transition_status(
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
    assert cycle_state.dig_to_carry_reason == "stale"
    capability_provider.sync_dig_transition_reason(loaded_status)
    assert cycle_state.dig_to_carry_reason == "loaded"

    low_payload_status = capability_provider.dig_transition_status(
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
    assert cycle_state.dig_to_carry_reason == "loaded"
    capability_provider.sync_dig_transition_reason(low_payload_status)
    assert cycle_state.dig_to_carry_reason == ""


def test_legacy_fsm_branch_ports_use_capability_provider_methods() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    planner._skill_name = "dig"
    planner._switch_reason = ""
    planner.bootstrap_end_mode = "first_qualified_dig_start"
    planner._should_end_bootstrap = MethodType(
        lambda self, *, obs, boundary_event: False,
        planner,
    )
    provider = _FakePrimitiveFSMCapabilityProvider()
    capabilities = PrimitiveDecisionCapabilities.from_ports(
        PrimitiveDecisionCapabilitiesPorts(
            current_skill_name=lambda: str(planner._skill_name),
            current_switch_reason=lambda: str(planner._switch_reason),
            should_end_bootstrap=planner._should_end_bootstrap,
            bootstrap_end_mode=lambda: str(planner.bootstrap_end_mode),
            transition_status_provider=provider,
        )
    )
    ports = LegacyFSMBranchPorts(
        bootstrap_skill_name="bootstrap",
        dig_skill_name="dig",
        carry_skill_name="carry",
        dump_skill_name="dump",
        return_skill_name="return",
        facts_source=capabilities.facts_source(),
        compatibility_actions=capabilities.compatibility_actions(),
    )

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


def test_primitive_planner_no_longer_exposes_transition_status_wrappers() -> None:
    for wrapper_name in _OLD_TRANSITION_STATUS_POLICY_WRAPPERS:
        assert wrapper_name not in PrimitivePlannerACTPolicy.__dict__


def test_primitive_planner_no_longer_exposes_capability_composition_wrappers() -> None:
    for wrapper_name in _OLD_CAPABILITY_COMPOSITION_POLICY_WRAPPERS:
        assert wrapper_name not in PrimitivePlannerACTPolicy.__dict__
