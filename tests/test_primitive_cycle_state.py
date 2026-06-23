from __future__ import annotations

from types import MethodType, SimpleNamespace

import numpy as np

from testbed.planner.primitive_cycle_state import (
    PrimitiveCycleReportStatus,
    PrimitiveCycleRuntimeState,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def test_cycle_runtime_state_fresh_matches_legacy_reset_defaults() -> None:
    state = PrimitiveCycleRuntimeState.fresh()

    assert state.dump_ready_hold_count == 0
    assert state.dump_done_hold_count == 0
    assert state.dig_step_count == 0
    assert state.dig_best_mass_kg == 0.0
    assert state.dig_mass_plateau_count == 0
    assert state.dig_to_carry_reason == ""
    assert state.dig_bad_replan_count == 0
    assert state.dig_exit_guard_replan_count == 0
    assert state.completed_transition_count == 0
    assert state.transition_timeout_count == 0
    assert state.cycle_index == 0
    assert state.dump_start_deposited_mass_kg == 0.0


def test_cycle_runtime_state_methods_preserve_legacy_counter_rules() -> None:
    state = PrimitiveCycleRuntimeState.fresh()

    state.set_dump_ready_hold_count(3)
    state.set_dump_done_hold_count(4)
    state.set_dump_start_deposited_mass_kg(12.5)
    state.increment_transition_timeout_count()
    state.complete_return_transition()
    state.increment_dig_bad_replan_count()
    state.increment_dig_exit_guard_replan_count()
    state.update_dig_progress(mass_in_bucket_kg=5.0, plateau_epsilon_kg=0.1)
    state.update_dig_progress(mass_in_bucket_kg=5.05, plateau_epsilon_kg=0.1)

    assert state.dump_ready_hold_count == 3
    assert state.dump_done_hold_count == 4
    assert state.dump_start_deposited_mass_kg == 12.5
    assert state.transition_timeout_count == 1
    assert state.completed_transition_count == 1
    assert state.cycle_index == 1
    assert state.dig_bad_replan_count == 1
    assert state.dig_exit_guard_replan_count == 1
    assert state.dig_step_count == 2
    assert state.dig_best_mass_kg == 5.05
    assert state.dig_mass_plateau_count == 1

    state.dig_to_carry_reason = "loaded"
    state.reset_dig_progress()

    assert state.dig_step_count == 0
    assert state.dig_best_mass_kg == 0.0
    assert state.dig_mass_plateau_count == 0
    assert state.dig_to_carry_reason == ""


def test_policy_legacy_cycle_fields_are_backed_by_one_state_owner() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    state = policy._primitive_cycle_runtime_state()

    policy._dump_ready_hold_count = 2
    policy._dump_done_hold_count = 3
    policy._dig_step_count = 4
    policy._dig_best_mass_kg = 5.0
    policy._dig_mass_plateau_count = 6
    policy._dig_to_carry_reason = "loaded"
    policy._dig_bad_replan_count = 7
    policy._dig_exit_guard_replan_count = 8
    policy._completed_transition_count = 9
    policy._transition_timeout_count = 10
    policy._cycle_index = 11
    policy._dump_start_deposited_mass_kg = 12.5

    assert policy._primitive_cycle_runtime_state() is state
    assert state.dump_ready_hold_count == 2
    assert state.dump_done_hold_count == 3
    assert state.dig_step_count == 4
    assert state.dig_best_mass_kg == 5.0
    assert state.dig_mass_plateau_count == 6
    assert state.dig_to_carry_reason == "loaded"
    assert state.dig_bad_replan_count == 7
    assert state.dig_exit_guard_replan_count == 8
    assert state.completed_transition_count == 9
    assert state.transition_timeout_count == 10
    assert state.cycle_index == 11
    assert state.dump_start_deposited_mass_kg == 12.5


def test_policy_reset_application_replaces_cycle_state_owner() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    old_state = policy._primitive_cycle_runtime_state()
    old_state.cycle_index = 9
    reset_state = PrimitiveCycleRuntimeState.fresh()

    class _ResetState:
        def as_policy_field_updates(self):
            return {"_cycle_state": reset_state}

    policy._apply_reset_lifecycle_state(_ResetState())
    policy._cycle_index = 3

    assert policy._primitive_cycle_runtime_state() is reset_state
    assert policy._primitive_cycle_runtime_state() is not old_state
    assert reset_state.cycle_index == 3
    assert old_state.cycle_index == 9


def test_policy_cycle_methods_write_state_owner() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    state = policy._primitive_cycle_runtime_state()
    policy.dig_to_carry_mass_plateau_epsilon_kg = 0.1
    policy._mass_in_bucket = MethodType(lambda self, obs: float(obs["mass"]), policy)
    policy._coverage_current_payload_gain_kg = 0.0

    policy._set_dump_ready_hold_count(4)
    policy._set_dump_done_hold_count(5)
    policy._set_dump_start_deposited_mass(6.5)
    policy._increment_dig_bad_replan_count()
    policy._increment_dig_exit_guard_replan_count()
    policy._complete_return_transition_for_backend()
    policy._transition_timeout_count = 2
    policy._update_dig_progress({"mass": 3.0})
    policy._update_dig_progress({"mass": 3.05})

    assert state.dump_ready_hold_count == 4
    assert state.dump_done_hold_count == 5
    assert state.dump_start_deposited_mass_kg == 6.5
    assert state.dig_bad_replan_count == 1
    assert state.dig_exit_guard_replan_count == 1
    assert state.completed_transition_count == 1
    assert state.cycle_index == 1
    assert state.transition_timeout_count == 2
    assert state.dig_step_count == 2
    assert state.dig_best_mass_kg == 3.05
    assert state.dig_mass_plateau_count == 1
    assert policy._coverage_current_payload_gain_kg == 3.05


def test_requested_effect_ports_share_cycle_and_return_state_owners() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    policy.action_dim = 4
    cycle_state = policy._primitive_cycle_runtime_state()
    return_state = policy._primitive_return_runtime_state()

    ports = policy._requested_effect_applier_ports()

    assert ports.cycle_state is cycle_state
    assert ports.return_state is return_state
    assert not hasattr(ports, "deposited_mass")
    assert hasattr(ports, "observation_facts")
    assert not hasattr(ports, "complete_return_transition")
    assert not hasattr(ports, "mark_return_next_dig_event_seen")
    assert not hasattr(ports, "set_dump_ready_hold_count")
    assert not hasattr(ports, "set_dump_start_deposited_mass")
    assert not hasattr(ports, "set_dump_done_hold_count")

    ports.cycle_state.set_dump_ready_hold_count(7)
    ports.return_state.mark_next_dig_event_seen()

    assert cycle_state.dump_ready_hold_count == 7
    assert return_state.return_next_dig_event_seen is True


def test_skill_lifecycle_cycle_ports_write_state_owner() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    state = policy._primitive_cycle_runtime_state()
    policy._skill_name = "dig"
    policy._switch_reason = ""
    policy._active_policy = MethodType(
        lambda self: type("_Policy", (), {"reset": lambda self: None})(),
        policy,
    )
    policy._clear_dig_cut_plan = MethodType(lambda self: None, policy)

    ports = policy._primitive_skill_lifecycle_ports()
    assert ports.cycle_state is state
    assert not hasattr(ports, "set_dump_ready_hold_count")
    assert not hasattr(ports, "set_dump_done_hold_count")
    assert not hasattr(ports, "set_dig_step_count")
    ports.cycle_state.set_dump_ready_hold_count(1)
    ports.cycle_state.set_dump_done_hold_count(2)
    ports.cycle_state.dig_step_count = 3
    ports.cycle_state.dig_best_mass_kg = 4.5
    ports.cycle_state.dig_mass_plateau_count = 6
    ports.cycle_state.dig_to_carry_reason = "reason"

    assert state.dump_ready_hold_count == 1
    assert state.dump_done_hold_count == 2
    assert state.dig_step_count == 3
    assert state.dig_best_mass_kg == 4.5
    assert state.dig_mass_plateau_count == 6
    assert state.dig_to_carry_reason == "reason"


def test_capability_provider_ports_read_cycle_state_owner() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    state = policy._primitive_cycle_runtime_state()
    state.dig_step_count = 12
    state.dig_mass_plateau_count = 3
    state.dump_ready_hold_count = 4
    state.dump_done_hold_count = 5
    state.dump_start_deposited_mass_kg = 6.5
    coverage_state = policy._coverage_runtime_state()
    coverage_state.coverage_terminal_stop_requested = False
    coverage_state.coverage_cycle_start_deposit_kg = 7.5
    return_state = policy._primitive_return_runtime_state()
    return_state.return_next_dig_event_seen = False
    return_state.return_to_dig_entry_close_state = True
    return_state.return_to_dig_start_envelope_ready_state = True
    policy.action_dim = 1
    policy._semantic_boundary_profile_active = MethodType(lambda self: False, policy)
    policy._dig_exit_overshoot_m = MethodType(lambda self, obs: 0.0, policy)
    policy.dig_to_carry_min_distance_to_dig_area_m = 0.0
    policy.dig_to_carry_min_bucket_mass_kg = 0.0
    policy.dig_to_carry_target_bucket_mass_kg = 0.0
    policy.dig_to_carry_mass_plateau_enabled = False
    policy.dig_to_carry_mass_plateau_min_bucket_mass_kg = 0.0
    policy.dig_to_carry_mass_plateau_hold_steps = 1
    policy.dig_to_carry_mass_plateau_min_steps = 1
    policy.dump_ready_min_bucket_mass_kg = 0.0
    policy.dig_bad_replan_enabled = False
    policy.dig_bad_replan_max_steps = 1
    policy.dig_bad_replan_min_bucket_mass_kg = 0.0
    policy.dig_exit_guard_enabled = False
    policy.dig_exit_guard_min_steps = 1
    policy.dig_exit_guard_min_bucket_mass_kg = 0.0
    policy.dig_exit_guard_overshoot_m = 0.0
    policy.dump_ready_hold_steps = 1
    policy.dump_ready_min_height_above_rim_m = 0.0
    policy.dump_ready_require_over_footprint = False
    policy.dump_ready_require_clearance = False
    policy.dump_ready_max_horizontal_distance_m = None
    policy.dump_ready_position_mode = "footprint"
    policy.dump_ready_max_dump_area_footprint_outside_distance_m = None
    policy.dump_ready_min_dump_area_relative_x_m = None
    policy.dump_ready_max_dump_area_relative_x_m = None
    policy.dump_ready_min_dump_area_relative_z_m = None
    policy.dump_ready_max_dump_area_relative_z_m = None
    policy.dump_ready_near_window_enabled = False
    policy.dump_ready_near_window_x_tolerance_m = 0.0
    policy.dump_ready_near_window_z_tolerance_m = 0.0
    policy.dump_ready_near_window_outside_tolerance_m = 0.0
    policy.dump_ready_near_window_require_over_footprint = False
    policy.dump_done_max_bucket_mass_kg = 0.0
    policy.dump_done_min_deposit_delta_kg = 0.0
    policy.dump_done_use_boundary_event = False
    policy.dump_done_hold_steps = 1
    policy.return_to_dig_max_bucket_mass_kg = 0.0
    policy.return_to_dig_touch_tolerance_m = 0.0
    policy.return_to_dig_min_depth_m = 0.0
    policy.return_to_dig_max_depth_m = 0.0
    policy.return_to_dig_shallow_guard_enabled = False
    policy.return_to_dig_max_entry_error_m = None
    policy.return_to_dig_start_envelope_direct_handoff_enabled = False
    policy.return_to_dig_start_envelope_gate_enabled = False
    policy._return_to_dig_direct_handoff_ready = MethodType(
        lambda self, obs, *, handoff_ready: False,
        policy,
    )
    policy._return_to_dig_handoff_ready = MethodType(lambda self, obs: True, policy)
    policy._should_pre_dig_align_before_dig = MethodType(lambda self: False, policy)

    ports = policy._primitive_fsm_capability_provider_ports()

    assert ports.cycle_state is state
    assert ports.coverage_state is coverage_state
    assert ports.return_state is return_state
    assert not hasattr(ports, "dig_step_count")
    assert not hasattr(ports, "dig_mass_plateau_count")
    assert not hasattr(ports, "set_dig_to_carry_reason")
    assert not hasattr(ports, "coverage_terminal_stop_requested")
    assert not hasattr(ports, "coverage_cycle_start_deposit_kg")
    assert not hasattr(ports, "dump_ready_hold_count")
    assert not hasattr(ports, "dump_done_hold_count")
    assert not hasattr(ports, "dump_start_deposited_mass_kg")
    assert not hasattr(ports, "return_next_dig_event_seen")
    assert not hasattr(ports, "return_entry_close")
    assert not hasattr(ports, "return_start_envelope_ready")
    assert ports.cycle_state.dig_step_count == 12
    assert ports.cycle_state.dig_mass_plateau_count == 3
    assert ports.cycle_state.dump_ready_hold_count == 4
    assert ports.cycle_state.dump_done_hold_count == 5
    assert ports.cycle_state.dump_start_deposited_mass_kg == 6.5
    assert ports.coverage_state.coverage_cycle_start_deposit_kg == 7.5
    assert ports.return_state.return_to_dig_entry_close_state is True


def test_tick_finalization_and_report_inputs_read_cycle_state_owner() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    state = policy._primitive_cycle_runtime_state()
    state.completed_transition_count = 7
    state.transition_timeout_count = 8
    state.dump_ready_hold_count = 9
    state.dump_done_hold_count = 10
    state.cycle_index = 11
    policy._skill_name = "dump"
    policy._switch_reason = "carry_to_dump"
    policy.primitive_checkpoint_paths = {"dump": "dump.ckpt"}
    policy._first_dig_policy_active = MethodType(lambda self: False, policy)

    inputs = policy._tick_finalization_inputs(
        transition_timeout=False,
        transition_completed=True,
    )

    assert inputs.completed_transition_count == 7
    assert inputs.transition_timeout_count == 8
    assert inputs.dump_ready_hold_count == 9
    assert inputs.dump_done_hold_count == 10
    assert inputs.primitive_cycle_index == 11

    policy._debug_state = type(
        "_DebugState",
        (),
        {
            "skill_name": "dump",
            "skill_id": 2,
            "skill_switch_reason": "carry_to_dump",
            "primitive_checkpoint_path": "dump.ckpt",
            "hybrid_mode": "work",
            "transition_timeout": False,
            "transition_completed": True,
            "completed_transition_count": 7,
            "transition_timeout_count": 8,
            "dump_ready_hold_count": 9,
            "dump_done_hold_count": 10,
            "approach_ready_hold_count": 0,
            "dump_release_ready_hold_count": 0,
            "primitive_cycle_index": 11,
        },
    )()

    snapshot = policy._debug_state_snapshot_for_report()
    assert snapshot.completed_transition_count == 7
    assert snapshot.transition_timeout_count == 8
    assert snapshot.dump_ready_hold_count == 9
    assert snapshot.dump_done_hold_count == 10
    assert snapshot.primitive_cycle_index == 11


def test_cycle_runtime_state_projects_fresh_report_status_defaults() -> None:
    state = PrimitiveCycleRuntimeState.fresh()

    status = state.to_report_status()

    assert status.completed_transition_count == 0
    assert status.transition_timeout_count == 0
    assert status.dump_ready_hold_count == 0
    assert status.dump_done_hold_count == 0
    assert status.primitive_cycle_index == 0
    assert status.dig_step_count == 0
    assert status.dig_best_mass_kg == 0.0
    assert status.dig_mass_plateau_count == 0
    assert status.dig_to_carry_reason == ""
    assert status.dig_bad_replan_count == 0
    assert status.dig_exit_guard_replan_count == 0
    assert status.dig_progress_debug_fields() == {
        "dig_step_count": 0,
        "dig_best_mass_kg": 0.0,
        "dig_mass_plateau_count": 0,
        "dig_to_carry_reason": "",
        "dig_bad_replan_count": 0,
        "dig_exit_guard_replan_count": 0,
    }


def test_cycle_runtime_state_projects_populated_report_status() -> None:
    state = PrimitiveCycleRuntimeState.fresh()
    state.completed_transition_count = 1
    state.transition_timeout_count = 2
    state.dump_ready_hold_count = 3
    state.dump_done_hold_count = 4
    state.cycle_index = 5
    state.dig_step_count = 6
    state.dig_best_mass_kg = 7.5
    state.dig_mass_plateau_count = 8
    state.dig_to_carry_reason = "loaded"
    state.dig_bad_replan_count = 9
    state.dig_exit_guard_replan_count = 10

    status = state.to_report_status()

    assert status == PrimitiveCycleReportStatus(
        completed_transition_count=1,
        transition_timeout_count=2,
        dump_ready_hold_count=3,
        dump_done_hold_count=4,
        primitive_cycle_index=5,
        dig_step_count=6,
        dig_best_mass_kg=7.5,
        dig_mass_plateau_count=8,
        dig_to_carry_reason="loaded",
        dig_bad_replan_count=9,
        dig_exit_guard_replan_count=10,
    )
    assert status.dig_progress_debug_fields() == {
        "dig_step_count": 6,
        "dig_best_mass_kg": 7.5,
        "dig_mass_plateau_count": 8,
        "dig_to_carry_reason": "loaded",
        "dig_bad_replan_count": 9,
        "dig_exit_guard_replan_count": 10,
    }


def test_policy_dig_progress_debug_facade_delegates_to_cycle_report_status() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    state = policy._primitive_cycle_runtime_state()
    state.dig_step_count = 6
    state.dig_best_mass_kg = 7.5
    state.dig_mass_plateau_count = 8
    state.dig_to_carry_reason = "loaded"
    state.dig_bad_replan_count = 9
    state.dig_exit_guard_replan_count = 10

    assert (
        policy._debug_report_dig_progress_fields()
        == state.to_report_status().dig_progress_debug_fields()
    )


def test_policy_rollout_summary_inputs_use_cycle_report_status_projection() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    cycle_status = PrimitiveCycleReportStatus(
        completed_transition_count=11,
        transition_timeout_count=12,
        dump_ready_hold_count=13,
        dump_done_hold_count=14,
        primitive_cycle_index=15,
        dig_step_count=16,
        dig_best_mass_kg=17.5,
        dig_mass_plateau_count=18,
        dig_to_carry_reason="loaded",
        dig_bad_replan_count=19,
        dig_exit_guard_replan_count=20,
    )
    policy._cycle_report_status = MethodType(lambda self: cycle_status, policy)
    policy._return_report_status = MethodType(
        lambda self: SimpleNamespace(
            return_to_dig_entry_error_m=0.0,
            return_to_dig_entry_close=True,
            return_next_dig_event_seen=False,
            return_to_dig_start_envelope_gate_enabled=False,
            return_to_dig_start_envelope_direct_handoff_enabled=False,
            return_to_dig_start_envelope_ready=True,
            return_to_dig_start_envelope_plane_depth_mode="range",
            return_to_dig_start_envelope_local_depth_tolerance_m=0.0,
            return_to_dig_start_envelope_error=0.0,
        ),
        policy,
    )
    policy._scripted_bootstrap_report_status = MethodType(
        lambda self: SimpleNamespace(timeout_count=0),
        policy,
    )
    policy._token_report_status = MethodType(lambda self: SimpleNamespace(), policy)
    policy._cell_entry_report_status = MethodType(lambda self: SimpleNamespace(), policy)
    policy._pre_dig_align_report_status = MethodType(
        lambda self: SimpleNamespace(),
        policy,
    )
    policy.dump_done_use_boundary_event = False
    policy.cell_entry_enabled = False
    policy.return_to_dig_max_entry_error_m = 0.5
    policy.dig_cut_planner_mode = "operator_prior"
    policy.dig_cut_prior_id = "default"
    policy.dig_cut_prior_path = ""
    policy.dig_failed_replan_next_skill = "dig"
    policy.coverage_multi_pass_enabled = False
    policy.coverage_use_env_removed_depth = False
    policy.coverage_candidate_layout = "corridor_grid"
    policy.coverage_first_dig_strategy = "best_score"
    policy.coverage_first_dig_preferred_corridor_id = None
    policy.coverage_first_dig_max_entry_distance_m = None
    policy.coverage_first_dig_qpos_delta_weight = 1.0
    policy.coverage_state_exemplars_enabled = False
    policy.coverage_multi_pass_max_passes = 1
    policy.coverage_multi_pass_min_remaining_depth_m = 0.0
    policy.coverage_first_dig_max_qpos_delta = None
    policy.pre_dig_align_enabled = False
    policy.pre_dig_align_first_dig_only = True
    policy.pre_dig_align_replan_after_failed_dig = False
    policy.pre_dig_align_surface_guard_enabled = False

    inputs = policy._rollout_summary_inputs()

    assert inputs.transition_timeout_count == 12
    assert inputs.completed_transition_count == 11
    assert inputs.primitive_cycle_index == 15
    assert inputs.dig_bad_replan_count == 19
    assert inputs.dig_exit_guard_replan_count == 20


def test_policy_tick_finalization_inputs_use_cycle_report_status_projection() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    cycle_status = PrimitiveCycleReportStatus(
        completed_transition_count=21,
        transition_timeout_count=22,
        dump_ready_hold_count=23,
        dump_done_hold_count=24,
        primitive_cycle_index=25,
        dig_step_count=26,
        dig_best_mass_kg=27.5,
        dig_mass_plateau_count=28,
        dig_to_carry_reason="loaded",
        dig_bad_replan_count=29,
        dig_exit_guard_replan_count=30,
    )
    policy._cycle_report_status = MethodType(lambda self: cycle_status, policy)
    policy._skill_name = "dump"
    policy._switch_reason = "carry_to_dump"
    policy.primitive_checkpoint_paths = {"dump": "dump.ckpt"}
    policy._first_dig_policy_active = MethodType(lambda self: False, policy)

    inputs = policy._tick_finalization_inputs(
        transition_timeout=False,
        transition_completed=True,
    )

    assert inputs.completed_transition_count == 21
    assert inputs.transition_timeout_count == 22
    assert inputs.dump_ready_hold_count == 23
    assert inputs.dump_done_hold_count == 24
    assert inputs.primitive_cycle_index == 25
