from __future__ import annotations

from types import MethodType

import numpy as np

from testbed.planner.primitive_return_handoff import ReturnStartEnvelopeGateResult
from testbed.planner.primitive_return_state import (
    PrimitiveReturnReportStatus,
    PrimitiveReturnRuntimeState,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def test_return_runtime_state_fresh_matches_legacy_reset_defaults() -> None:
    state = PrimitiveReturnRuntimeState.fresh()

    assert state.return_step_count == 0
    assert np.isnan(state.return_to_dig_entry_error_m)
    assert state.return_to_dig_entry_close_state is True
    assert state.return_next_dig_event_seen is False
    assert state.return_to_dig_start_envelope_ready_state is True
    assert np.isnan(state.return_to_dig_start_envelope_error)
    assert state.return_to_dig_start_envelope_checks == {}


def test_return_runtime_state_fresh_does_not_alias_mutable_checks() -> None:
    first = PrimitiveReturnRuntimeState.fresh()
    second = PrimitiveReturnRuntimeState.fresh()

    first.return_to_dig_start_envelope_checks["changed"] = True

    assert second.return_to_dig_start_envelope_checks == {}
    assert (
        first.return_to_dig_start_envelope_checks
        is not second.return_to_dig_start_envelope_checks
    )


def test_policy_legacy_return_fields_are_backed_by_one_state_owner() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    state = policy._primitive_return_runtime_state()

    policy._return_step_count = 11
    policy._return_to_dig_entry_error_m = 0.25
    policy._return_to_dig_entry_close_state = False
    policy._return_next_dig_event_seen = True
    policy._return_to_dig_start_envelope_ready_state = False
    policy._return_to_dig_start_envelope_error = 0.5
    policy._return_to_dig_start_envelope_checks = {"qpos_0": {"ok": False}}

    assert policy._primitive_return_runtime_state() is state
    assert state.return_step_count == 11
    assert state.return_to_dig_entry_error_m == 0.25
    assert state.return_to_dig_entry_close_state is False
    assert state.return_next_dig_event_seen is True
    assert state.return_to_dig_start_envelope_ready_state is False
    assert state.return_to_dig_start_envelope_error == 0.5
    assert (
        policy._return_to_dig_start_envelope_checks
        is state.return_to_dig_start_envelope_checks
    )


def test_policy_reset_application_replaces_return_state_owner() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    old_state = policy._primitive_return_runtime_state()
    old_state.return_step_count = 9
    old_state.return_to_dig_start_envelope_checks["old"] = True
    reset_state = PrimitiveReturnRuntimeState.fresh()

    class _ResetState:
        def as_policy_field_updates(self):
            return {"_return_state": reset_state}

    policy._apply_reset_lifecycle_state(_ResetState())

    assert policy._primitive_return_runtime_state() is reset_state
    assert policy._primitive_return_runtime_state() is not old_state
    assert policy._return_step_count == 0
    assert policy._return_to_dig_start_envelope_checks == {}
    assert (
        policy._return_to_dig_start_envelope_checks
        is not old_state.return_to_dig_start_envelope_checks
    )


def test_policy_return_state_methods_write_state_owner() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    state = policy._primitive_return_runtime_state()

    policy._mark_return_next_dig_event_seen()
    policy._apply_return_start_envelope_gate_result(
        ReturnStartEnvelopeGateResult(
            ready=False,
            error=0.75,
            checks={"qpos_0": {"ok": False}},
        )
    )

    assert state.return_next_dig_event_seen is True
    assert state.return_to_dig_start_envelope_ready_state is False
    assert state.return_to_dig_start_envelope_error == 0.75
    assert state.return_to_dig_start_envelope_checks == {"qpos_0": {"ok": False}}


def test_skill_lifecycle_return_ports_write_return_state_owner() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    state = policy._primitive_return_runtime_state()
    state.return_step_count = 9
    state.return_next_dig_event_seen = True
    policy._skill_name = "dig"
    policy._switch_reason = ""
    policy._active_policy = MethodType(
        lambda self: type("_Policy", (), {"reset": lambda self: None})(),
        policy,
    )
    policy._clear_dig_cut_plan = MethodType(lambda self: None, policy)

    ports = policy._primitive_skill_lifecycle_ports()
    ports.set_return_step_count(0)
    ports.set_return_next_dig_event_seen(False)

    assert state.return_step_count == 0
    assert state.return_next_dig_event_seen is False


def test_return_direct_handoff_effect_ports_read_return_state_owner() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    state = policy._primitive_return_runtime_state()
    state.return_next_dig_event_seen = True
    state.return_to_dig_entry_close_state = False
    state.return_to_dig_start_envelope_ready_state = True
    policy._skill_name = "return"
    policy.return_target_planner_enabled = True
    policy.return_to_dig_start_envelope_direct_handoff_enabled = True
    policy._set_skill = MethodType(lambda self, skill, reason: None, policy)
    policy._ensure_return_target_plan_for_cycle = MethodType(lambda self, obs: None, policy)
    policy._return_to_dig_handoff_ready = MethodType(lambda self, obs: False, policy)
    policy._return_to_dig_direct_handoff_ready = MethodType(
        lambda self, obs, *, handoff_ready: False,
        policy,
    )
    policy._complete_return_transition_for_backend = MethodType(lambda self: None, policy)
    policy._next_skill_after_return_transition = MethodType(lambda self: "dig", policy)

    ports = policy._return_direct_handoff_effect_ports()

    assert ports.current_skill_name() == "return"
    assert state.return_next_dig_event_seen is True
    assert state.return_to_dig_entry_close_state is False
    assert state.return_to_dig_start_envelope_ready_state is True


def test_return_runtime_state_projects_fresh_report_status_defaults() -> None:
    state = PrimitiveReturnRuntimeState.fresh()

    status = state.to_report_status(
        start_envelope_gate_enabled=False,
        start_envelope_direct_handoff_enabled=True,
        start_envelope_plane_depth_mode="range",
        start_envelope_local_depth_tolerance_m=0.005,
    )

    assert np.isnan(status.return_to_dig_entry_error_m)
    assert status.return_to_dig_entry_close is True
    assert status.return_next_dig_event_seen is False
    assert status.return_to_dig_start_envelope_gate_enabled is False
    assert status.return_to_dig_start_envelope_direct_handoff_enabled is True
    assert status.return_to_dig_start_envelope_ready is True
    assert status.return_to_dig_start_envelope_plane_depth_mode == "range"
    assert status.return_to_dig_start_envelope_local_depth_tolerance_m == 0.005
    assert np.isnan(status.return_to_dig_start_envelope_error)
    assert status.return_to_dig_start_envelope_checks == {}

    fields = status.debug_fields()
    assert fields["return_to_dig_entry_close"] is True
    assert fields["return_next_dig_event_seen"] is False
    assert fields["return_to_dig_start_envelope_checks"] == {}
    assert fields["return_to_dig_start_envelope_checks"] is not (
        status.return_to_dig_start_envelope_checks
    )


def test_return_runtime_state_projects_populated_report_status_without_aliasing() -> None:
    state = PrimitiveReturnRuntimeState.fresh()
    state.return_to_dig_entry_error_m = 0.25
    state.return_to_dig_entry_close_state = False
    state.return_next_dig_event_seen = True
    state.return_to_dig_start_envelope_ready_state = False
    state.return_to_dig_start_envelope_error = 0.75
    state.return_to_dig_start_envelope_checks = {"qpos_0": {"ok": False}}

    status = state.to_report_status(
        start_envelope_gate_enabled=True,
        start_envelope_direct_handoff_enabled=False,
        start_envelope_plane_depth_mode="p50_floor",
        start_envelope_local_depth_tolerance_m=0.03,
    )
    state.return_to_dig_start_envelope_checks["changed"] = True

    assert status.return_to_dig_entry_error_m == 0.25
    assert status.return_to_dig_entry_close is False
    assert status.return_next_dig_event_seen is True
    assert status.return_to_dig_start_envelope_gate_enabled is True
    assert status.return_to_dig_start_envelope_direct_handoff_enabled is False
    assert status.return_to_dig_start_envelope_ready is False
    assert status.return_to_dig_start_envelope_plane_depth_mode == "p50_floor"
    assert status.return_to_dig_start_envelope_local_depth_tolerance_m == 0.03
    assert status.return_to_dig_start_envelope_error == 0.75
    assert status.return_to_dig_start_envelope_checks == {
        "qpos_0": {"ok": False}
    }
    assert status.debug_fields() == {
        "return_to_dig_entry_error_m": 0.25,
        "return_to_dig_entry_close": False,
        "return_next_dig_event_seen": True,
        "return_to_dig_start_envelope_gate_enabled": True,
        "return_to_dig_start_envelope_direct_handoff_enabled": False,
        "return_to_dig_start_envelope_ready": False,
        "return_to_dig_start_envelope_plane_depth_mode": "p50_floor",
        "return_to_dig_start_envelope_local_depth_tolerance_m": 0.03,
        "return_to_dig_start_envelope_error": 0.75,
        "return_to_dig_start_envelope_checks": {"qpos_0": {"ok": False}},
    }


def test_policy_return_debug_facade_delegates_to_report_status() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    state = policy._primitive_return_runtime_state()
    state.return_to_dig_entry_error_m = 0.25
    state.return_to_dig_entry_close_state = False
    state.return_next_dig_event_seen = True
    state.return_to_dig_start_envelope_ready_state = False
    state.return_to_dig_start_envelope_error = 0.75
    state.return_to_dig_start_envelope_checks = {"qpos_0": {"ok": False}}
    policy.return_to_dig_start_envelope_gate_enabled = True
    policy.return_to_dig_start_envelope_direct_handoff_enabled = False
    policy.return_to_dig_start_envelope_plane_depth_mode = "p50_floor"
    policy.return_to_dig_start_envelope_local_depth_tolerance_m = 0.03

    status = state.to_report_status(
        start_envelope_gate_enabled=True,
        start_envelope_direct_handoff_enabled=False,
        start_envelope_plane_depth_mode="p50_floor",
        start_envelope_local_depth_tolerance_m=0.03,
    )

    assert policy._debug_report_return_fields() == status.debug_fields()


def test_policy_rollout_summary_inputs_use_return_report_status_projection() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    return_status = PrimitiveReturnReportStatus(
        return_to_dig_entry_error_m=0.42,
        return_to_dig_entry_close=False,
        return_next_dig_event_seen=True,
        return_to_dig_start_envelope_gate_enabled=True,
        return_to_dig_start_envelope_direct_handoff_enabled=True,
        return_to_dig_start_envelope_ready=False,
        return_to_dig_start_envelope_plane_depth_mode="p50_floor",
        return_to_dig_start_envelope_local_depth_tolerance_m=0.04,
        return_to_dig_start_envelope_error=0.125,
        return_to_dig_start_envelope_checks={"qpos_0": {"ok": False}},
    )
    policy._return_report_status = MethodType(lambda self: return_status, policy)
    policy.dump_done_use_boundary_event = False
    policy.cell_entry_enabled = False
    policy.return_to_dig_max_entry_error_m = 0.5
    policy.dig_cut_planner_mode = "operator_prior"
    policy.dig_cut_prior_id = "default"
    policy.dig_failed_replan_next_skill = "dig"
    policy.coverage_multi_pass_enabled = False
    policy.coverage_use_env_removed_depth = False
    policy.coverage_candidate_layout = "corridor_grid"
    policy.coverage_first_dig_strategy = "best_score"
    policy.coverage_first_dig_preferred_corridor_id = None
    policy.coverage_first_dig_max_entry_distance_m = None
    policy.coverage_first_dig_qpos_delta_weight = 1.0
    policy.pre_dig_align_enabled = False
    policy.pre_dig_align_first_dig_only = True
    policy.pre_dig_align_replan_after_failed_dig = False
    policy.pre_dig_align_surface_guard_enabled = False

    inputs = policy._rollout_summary_inputs()

    assert inputs.return_to_dig_entry_error_m == 0.42
    assert inputs.return_to_dig_entry_close is False
    assert inputs.return_next_dig_event_seen is True
    assert inputs.return_to_dig_start_envelope_gate_enabled is True
    assert inputs.return_to_dig_start_envelope_direct_handoff_enabled is True
    assert inputs.return_to_dig_start_envelope_ready is False
    assert inputs.return_to_dig_start_envelope_plane_depth_mode == "p50_floor"
    assert inputs.return_to_dig_start_envelope_local_depth_tolerance_m == 0.04
    assert inputs.return_to_dig_start_envelope_error == 0.125
