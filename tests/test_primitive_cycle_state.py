from __future__ import annotations

from types import MethodType

import numpy as np

from testbed.planner.primitive_cycle_state import PrimitiveCycleRuntimeState
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
    ports.set_dump_ready_hold_count(1)
    ports.set_dump_done_hold_count(2)
    ports.set_dig_step_count(3)
    ports.set_dig_best_mass_kg(4.5)
    ports.set_dig_mass_plateau_count(6)
    ports.set_dig_to_carry_reason("reason")

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
    policy.action_dim = 1
    policy._semantic_boundary_profile_active = MethodType(lambda self: False, policy)
    policy._coverage_terminal_stop_requested = False
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
    policy._coverage_cycle_start_deposit_kg = 0.0
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
    policy._return_next_dig_event_seen = False
    policy._return_to_dig_entry_close_state = True
    policy._return_to_dig_start_envelope_ready_state = True
    policy._return_to_dig_direct_handoff_ready = MethodType(
        lambda self, obs, *, handoff_ready: False,
        policy,
    )
    policy._return_to_dig_handoff_ready = MethodType(lambda self, obs: True, policy)
    policy._should_pre_dig_align_before_dig = MethodType(lambda self: False, policy)

    ports = policy._primitive_fsm_capability_provider_ports()

    assert ports.dig_step_count == 12
    assert ports.dig_mass_plateau_count == 3
    assert ports.dump_ready_hold_count == 4
    assert ports.dump_done_hold_count == 5
    assert ports.dump_start_deposited_mass_kg == 6.5


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
