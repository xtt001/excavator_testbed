"""Primitive planner debug-state and rollout-summary schema builders."""

from __future__ import annotations

from typing import Any

import numpy as np

from testbed.contracts.primitive_tokens import (
    DIG_CUT_TOKEN_DIM,
    DIG_DEPTH_PROFILE_TOKEN_DIM,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_TARGET_TOKEN_DIM,
)
from testbed.planner.cell_entry import CELL_ENTRY_TOKEN_DIM


TRANSITION_SOURCE_PRIMITIVE_RETURN_POLICY = "v2_2_primitive_return_policy"
TRANSITION_POLICY_MODE_PRIMITIVE = "primitive_return_policy"


def build_primitive_debug_state(policy: Any) -> dict[str, Any]:
    """Build the public debug-state schema for a primitive planner policy."""
    cell_goal = policy._cell_entry_goal
    cell_audit = policy._cell_entry_audit
    return {
        "skill_name": policy._debug_state.skill_name,
        "skill_id": int(policy._debug_state.skill_id),
        "skill_switch_reason": policy._debug_state.skill_switch_reason,
        "primitive_checkpoint_path": policy._debug_state.primitive_checkpoint_path,
        "hybrid_mode": policy._debug_state.hybrid_mode,
        "transition_timeout": bool(policy._debug_state.transition_timeout),
        "transition_completed": bool(policy._debug_state.transition_completed),
        "transition_source": TRANSITION_SOURCE_PRIMITIVE_RETURN_POLICY,
        "transition_policy_mode": TRANSITION_POLICY_MODE_PRIMITIVE,
        "transition_fallback_count": 0,
        "transition_fallback_reason": "",
        "completed_transition_count": int(
            policy._debug_state.completed_transition_count
        ),
        "transition_timeout_count": int(policy._debug_state.transition_timeout_count),
        "dump_ready_hold_count": int(policy._debug_state.dump_ready_hold_count),
        "dump_done_hold_count": int(policy._debug_state.dump_done_hold_count),
        "approach_ready_hold_count": int(
            policy._debug_state.approach_ready_hold_count
        ),
        "dump_release_ready_hold_count": int(
            policy._debug_state.dump_release_ready_hold_count
        ),
        "primitive_cycle_index": int(policy._debug_state.primitive_cycle_index),
        "primitive_goal_curr_sector_id": int(
            policy._goal_sector_id(policy._cycle_index)
        ),
        "primitive_goal_next_sector_id": int(policy._next_goal_sector_id()),
        "cell_entry_enabled": bool(policy.cell_entry_enabled),
        "cell_entry_token_injected": bool(policy._cell_entry_token_injected),
        "cell_entry_token_dim": int(CELL_ENTRY_TOKEN_DIM),
        "dig_cut_token_injected": bool(policy._dig_cut_token_injected),
        "dig_cut_token_dim": int(DIG_CUT_TOKEN_DIM),
        "dig_depth_profile_token_injected": bool(
            policy._dig_depth_profile_token_injected
        ),
        "dig_depth_profile_token_dim": int(DIG_DEPTH_PROFILE_TOKEN_DIM),
        "dig_depth_profile_source": str(policy.dig_depth_profile_source),
        "dig_depth_profile_required": bool(policy.dig_depth_profile_required),
        "dig_depth_profile_token_source": str(
            policy._dig_depth_profile_token_source
        ),
        "dig_depth_profile_fallback_reason": str(
            policy._dig_depth_profile_fallback_reason
        ),
        "dig_failed_replan_next_skill": str(policy.dig_failed_replan_next_skill),
        "return_target_token_injected": bool(policy._return_target_token_injected),
        "return_target_token_dim": int(RETURN_TARGET_TOKEN_DIM),
        "return_target_token_source": str(policy._return_target_token_source),
        "return_target_tokens": policy._return_target_tokens.astype(float).tolist(),
        "return_target_fallback_reason": str(policy._return_target_fallback_reason),
        "return_relocate_token_injected": bool(
            policy._return_relocate_token_injected
        ),
        "return_relocate_token_dim": int(RETURN_TARGET_TOKEN_DIM),
        "return_relocate_token_source": str(policy._return_target_token_source),
        "return_relocate_tokens": (
            policy._return_relocate_tokens.astype(float).tolist()
        ),
        "return_start_envelope_token_injected": bool(
            policy._return_start_envelope_token_injected
        ),
        "return_start_envelope_token_dim": int(RETURN_START_ENVELOPE_TOKEN_DIM),
        "return_start_envelope_token_source": str(
            policy._return_start_envelope_token_source
        ),
        "return_start_envelope_tokens": (
            policy._return_start_envelope_tokens.astype(float).tolist()
        ),
        "return_to_dig_entry_error_m": float(policy._return_to_dig_entry_error_m),
        "return_to_dig_entry_close": bool(policy._return_to_dig_entry_close_state),
        "return_next_dig_event_seen": bool(policy._return_next_dig_event_seen),
        "return_to_dig_start_envelope_gate_enabled": bool(
            policy.return_to_dig_start_envelope_gate_enabled
        ),
        "return_to_dig_start_envelope_direct_handoff_enabled": bool(
            policy.return_to_dig_start_envelope_direct_handoff_enabled
        ),
        "return_to_dig_start_envelope_ready": bool(
            policy._return_to_dig_start_envelope_ready_state
        ),
        "return_to_dig_start_envelope_plane_depth_mode": str(
            policy.return_to_dig_start_envelope_plane_depth_mode
        ),
        "return_to_dig_start_envelope_local_depth_tolerance_m": float(
            policy.return_to_dig_start_envelope_local_depth_tolerance_m
        ),
        "return_to_dig_start_envelope_error": float(
            policy._return_to_dig_start_envelope_error
        ),
        "return_to_dig_start_envelope_checks": dict(
            policy._return_to_dig_start_envelope_checks
        ),
        "pending_dig_cut_cycle_id": int(policy._pending_dig_cut_cycle_id),
        "pending_dig_cut_corridor_id": int(policy._pending_dig_cut_corridor_id),
        "dig_cut_planner_mode": str(policy.dig_cut_planner_mode),
        "dig_cut_prior_id": str(policy.dig_cut_prior_id),
        "dig_cut_token_source": str(policy._dig_cut_token_source),
        "dig_cut_tokens": policy._dig_cut_tokens.astype(float).tolist(),
        "dig_depth_profile_tokens": (
            policy._dig_depth_profile_tokens.astype(float).tolist()
        ),
        "token_in_prior_p10_p90": bool(policy._dig_cut_token_in_prior_p10_p90),
        "dig_cut_token_in_prior_p10_p90": bool(
            policy._dig_cut_token_in_prior_p10_p90
        ),
        "fallback_reason": str(policy._dig_cut_fallback_reason),
        "dig_cut_fallback_reason": str(policy._dig_cut_fallback_reason),
        "coverage_corridor_id": int(policy._coverage_active_corridor_id),
        "coverage_selected_corridor_id": int(policy._coverage_active_corridor_id),
        "coverage_last_selected_corridor_id": int(
            policy._coverage_last_selected_corridor_id
        ),
        "coverage_last_selected_cell_id": int(
            policy._coverage_corridor_cell_id_by_id(
                policy._coverage_last_selected_corridor_id
            )
        ),
        "coverage_last_selected_row_id": int(
            policy._coverage_corridor_row_id_by_id(
                policy._coverage_last_selected_corridor_id
            )
        ),
        "coverage_entry_x_m": float(policy._coverage_active_value("entry_x_m")),
        "coverage_entry_z_m": float(policy._coverage_active_value("entry_z_m")),
        "coverage_exit_x_m": float(policy._coverage_active_value("exit_x_m")),
        "coverage_exit_z_m": float(policy._coverage_active_value("exit_z_m")),
        "coverage_entry_x_p05_m": float(
            policy._coverage_active_value("entry_x_p05_m")
        ),
        "coverage_entry_x_p50_m": float(
            policy._coverage_active_value("entry_x_p50_m")
        ),
        "coverage_entry_x_p95_m": float(
            policy._coverage_active_value("entry_x_p95_m")
        ),
        "coverage_entry_z_p05_m": float(
            policy._coverage_active_value("entry_z_p05_m")
        ),
        "coverage_entry_z_p50_m": float(
            policy._coverage_active_value("entry_z_p50_m")
        ),
        "coverage_entry_z_p95_m": float(
            policy._coverage_active_value("entry_z_p95_m")
        ),
        "coverage_entry_radial_p75_m": float(
            policy._coverage_active_value("entry_radial_p75_m")
        ),
        "coverage_entry_radial_p95_m": float(
            policy._coverage_active_value("entry_radial_p95_m")
        ),
        "coverage_exit_x_p05_m": float(
            policy._coverage_active_value("exit_x_p05_m")
        ),
        "coverage_exit_x_p50_m": float(
            policy._coverage_active_value("exit_x_p50_m")
        ),
        "coverage_exit_x_p95_m": float(
            policy._coverage_active_value("exit_x_p95_m")
        ),
        "coverage_exit_z_p05_m": float(
            policy._coverage_active_value("exit_z_p05_m")
        ),
        "coverage_exit_z_p50_m": float(
            policy._coverage_active_value("exit_z_p50_m")
        ),
        "coverage_exit_z_p95_m": float(
            policy._coverage_active_value("exit_z_p95_m")
        ),
        "coverage_exit_radial_p75_m": float(
            policy._coverage_active_value("exit_radial_p75_m")
        ),
        "coverage_exit_radial_p95_m": float(
            policy._coverage_active_value("exit_radial_p95_m")
        ),
        "coverage_cut_depth_peak_p05_m": float(
            policy._coverage_active_value("cut_depth_peak_p05_m")
        ),
        "coverage_cut_depth_peak_p50_m": float(
            policy._coverage_active_value("cut_depth_peak_p50_m")
        ),
        "coverage_cut_depth_peak_p95_m": float(
            policy._coverage_active_value("cut_depth_peak_p95_m")
        ),
        "coverage_cell_id": int(policy._coverage_active_cell_id()),
        "coverage_corridor_score": float(policy._coverage_active_corridor_score()),
        "coverage_state_exemplar_enabled": bool(
            policy.coverage_state_exemplars_enabled
        ),
        "coverage_state_exemplar_ids": list(
            policy._coverage_active_state_exemplar_ids
        ),
        "coverage_state_exemplar_distance": float(
            policy._coverage_active_state_exemplar_distance
        ),
        "coverage_depleted_count": int(policy._coverage_depleted_count()),
        "coverage_pass_index": int(policy._coverage_pass_index),
        "coverage_multi_pass_enabled": bool(policy.coverage_multi_pass_enabled),
        "coverage_multi_pass_max_passes": int(policy.coverage_multi_pass_max_passes),
        "coverage_multi_pass_min_remaining_depth_m": float(
            policy.coverage_multi_pass_min_remaining_depth_m
        ),
        "coverage_last_payload_gain_kg": float(
            policy._coverage_last_payload_gain_kg
        ),
        "coverage_last_effective_deposit_delta_kg": float(
            policy._coverage_last_effective_deposit_delta_kg
        ),
        "coverage_global_low_productivity_streak": int(
            policy._coverage_global_low_productivity_streak
        ),
        "coverage_use_env_removed_depth": bool(policy.coverage_use_env_removed_depth),
        "coverage_candidate_layout": str(policy.coverage_candidate_layout),
        "coverage_first_dig_strategy": str(policy.coverage_first_dig_strategy),
        "coverage_first_dig_preferred_corridor_id": int(
            -1
            if policy.coverage_first_dig_preferred_corridor_id is None
            else policy.coverage_first_dig_preferred_corridor_id
        ),
        "coverage_first_dig_max_entry_distance_m": float(
            np.nan
            if policy.coverage_first_dig_max_entry_distance_m is None
            else policy.coverage_first_dig_max_entry_distance_m
        ),
        "coverage_first_dig_qpos_delta_weight": float(
            policy.coverage_first_dig_qpos_delta_weight
        ),
        "coverage_first_dig_max_qpos_delta": (
            None
            if policy.coverage_first_dig_max_qpos_delta is None
            else policy.coverage_first_dig_max_qpos_delta.astype(float).tolist()
        ),
        "coverage_terminal_stop_requested": bool(
            policy._coverage_terminal_stop_requested
        ),
        "coverage_terminal_stop_reason": str(policy._coverage_terminal_stop_reason),
        "coverage_corridors": [
            policy._coverage_corridor_to_debug(corridor)
            for corridor in policy._coverage_corridors
        ],
        "planner_terminal_stop_requested": bool(
            policy._coverage_terminal_stop_requested
        ),
        "planner_terminal_stop_reason": str(policy._coverage_terminal_stop_reason),
        "coverage_candidate_scores": list(policy._coverage_candidate_scores),
        "cell_entry_selected_cell_id": int(
            -1 if cell_goal is None else cell_goal.selected_cell_id
        ),
        "cell_entry_selected_long_index": int(
            -1 if cell_goal is None else cell_goal.selected_long_index
        ),
        "cell_entry_selected_short_index": int(
            -1 if cell_goal is None else cell_goal.selected_short_index
        ),
        "cell_entry_planned_entry_x_m": float(
            np.nan if cell_goal is None else cell_goal.planned_entry_x_m
        ),
        "cell_entry_planned_entry_y_m": float(
            np.nan if cell_goal is None else cell_goal.planned_entry_y_m
        ),
        "cell_entry_planned_entry_z_m": float(
            np.nan if cell_goal is None else cell_goal.planned_entry_z_m
        ),
        "cell_entry_planner_ok": bool(
            False if cell_audit is None else cell_audit.planner_ok
        ),
        "cell_entry_audit_reason_code": int(
            -1 if cell_audit is None else cell_audit.reason_code
        ),
        "cell_entry_audit_reason": str("" if cell_audit is None else cell_audit.reason),
        "cell_entry_audit_risk_flags": int(
            0 if cell_audit is None else cell_audit.risk_flags
        ),
        "cell_entry_inside_entry_envelope": bool(
            False if cell_audit is None else cell_audit.inside_entry_envelope
        ),
        "cell_entry_distance_to_entry_envelope_m": float(
            np.nan if cell_audit is None else cell_audit.distance_to_entry_envelope_m
        ),
        "cell_entry_seen_cell_id": int(policy._cell_entry_seen_cell_id),
        "scripted_bootstrap_step_count": int(policy._scripted_bootstrap_step_count),
        "scripted_bootstrap_hold_count": int(policy._scripted_bootstrap_hold_count),
        "scripted_bootstrap_timeout_count": int(
            policy._scripted_bootstrap_timeout_count
        ),
        "dig_step_count": int(policy._dig_step_count),
        "dig_best_mass_kg": float(policy._dig_best_mass_kg),
        "dig_mass_plateau_count": int(policy._dig_mass_plateau_count),
        "dig_to_carry_reason": str(policy._dig_to_carry_reason),
        "dig_bad_replan_count": int(policy._dig_bad_replan_count),
        "dig_exit_guard_replan_count": int(policy._dig_exit_guard_replan_count),
        "pre_dig_align_enabled": bool(policy.pre_dig_align_enabled),
        "pre_dig_align_first_dig_only": bool(policy.pre_dig_align_first_dig_only),
        "pre_dig_align_replan_after_failed_dig": bool(
            policy.pre_dig_align_replan_after_failed_dig
        ),
        "pre_dig_align_entry_intent_controlled_dims": (
            None
            if policy.pre_dig_align_entry_intent_controlled_dims is None
            else [
                int(value)
                for value in policy.pre_dig_align_entry_intent_controlled_dims.tolist()
            ]
        ),
        "pre_dig_align_surface_guard_enabled": bool(
            policy.pre_dig_align_surface_guard_enabled
        ),
        "pre_dig_align_surface_depth_m": float(
            policy._pre_dig_align_surface_depth_m
        ),
        "pre_dig_align_surface_guard_triggered": bool(
            policy._pre_dig_align_surface_guard_triggered
        ),
        "pre_dig_align_surface_guard_count": int(
            policy._pre_dig_align_surface_guard_count
        ),
        "pre_dig_align_active_for_next_dig": bool(
            policy._should_pre_dig_align_before_dig()
        ),
        "pre_dig_align_step_count": int(policy._pre_dig_align_step_count),
        "pre_dig_align_hold_count": int(policy._pre_dig_align_hold_count),
        "pre_dig_align_timeout_count": int(policy._pre_dig_align_timeout_count),
        "pre_dig_align_completed_count": int(policy._pre_dig_align_completed_count),
        "pre_dig_align_replan_count": int(policy._pre_dig_align_replan_count),
        "pre_dig_align_target_qpos": (
            policy._pre_dig_align_target_qpos.astype(float).tolist()
        ),
        "pre_dig_align_error": policy._pre_dig_align_error.astype(float).tolist(),
        "pre_dig_align_entry_error_m": float(policy._pre_dig_align_entry_error_m),
        "pre_dig_align_start_envelope_ready": bool(
            policy._pre_dig_align_start_envelope_ready
        ),
        "pre_dig_align_first_dig_entry_close_handoff": bool(
            policy.pre_dig_align_first_dig_entry_close_handoff
        ),
        "pre_dig_align_entry_close_handoff_ready": bool(
            policy._pre_dig_align_entry_close_handoff_ready
        ),
        "pre_dig_align_entry_intent_handoff_enabled": bool(
            policy.pre_dig_align_entry_intent_handoff_enabled
        ),
        "pre_dig_align_entry_intent_handoff_ready": bool(
            policy._pre_dig_align_entry_intent_handoff_ready
        ),
        "pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max": float(
            np.nan
            if policy.pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max is None
            else policy.pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max
        ),
        "pre_dig_align_controlled_dims": [
            int(value) for value in policy.pre_dig_align_controlled_dims.tolist()
        ],
        "pre_dig_align_bucket_target_qpos": float(
            np.nan
            if policy.pre_dig_align_bucket_target_qpos is None
            else policy.pre_dig_align_bucket_target_qpos
        ),
    }


def build_primitive_rollout_summary(
    policy: Any,
) -> dict[str, float | int | str | list[str]]:
    """Build the public rollout-summary schema for a primitive planner policy."""
    return {
        "transition_source": TRANSITION_SOURCE_PRIMITIVE_RETURN_POLICY,
        "transition_policy_mode": TRANSITION_POLICY_MODE_PRIMITIVE,
        "transition_fallback_count": 0,
        "transition_fallback_reason": "",
        "transition_timeout_count": int(policy._transition_timeout_count),
        "completed_transition_count": int(policy._completed_transition_count),
        "dump_done_use_boundary_event": int(policy.dump_done_use_boundary_event),
        "primitive_final_skill": str(policy._skill_name),
        "primitive_cycle_index": int(policy._cycle_index),
        "cell_entry_enabled": int(policy.cell_entry_enabled),
        "cell_entry_trace_count": int(len(policy._cell_entry_trace)),
        "dig_cut_token_dim": int(DIG_CUT_TOKEN_DIM),
        "return_target_token_dim": int(RETURN_TARGET_TOKEN_DIM),
        "return_target_token_source": str(policy._return_target_token_source),
        "return_to_dig_max_entry_error_m": float(
            np.nan
            if policy.return_to_dig_max_entry_error_m is None
            else policy.return_to_dig_max_entry_error_m
        ),
        "return_to_dig_entry_error_m": float(policy._return_to_dig_entry_error_m),
        "return_to_dig_entry_close": int(policy._return_to_dig_entry_close_state),
        "return_next_dig_event_seen": int(policy._return_next_dig_event_seen),
        "return_to_dig_start_envelope_gate_enabled": int(
            policy.return_to_dig_start_envelope_gate_enabled
        ),
        "return_to_dig_start_envelope_direct_handoff_enabled": int(
            policy.return_to_dig_start_envelope_direct_handoff_enabled
        ),
        "return_to_dig_start_envelope_ready": int(
            policy._return_to_dig_start_envelope_ready_state
        ),
        "return_to_dig_start_envelope_plane_depth_mode": str(
            policy.return_to_dig_start_envelope_plane_depth_mode
        ),
        "return_to_dig_start_envelope_local_depth_tolerance_m": float(
            policy.return_to_dig_start_envelope_local_depth_tolerance_m
        ),
        "return_to_dig_start_envelope_error": float(
            policy._return_to_dig_start_envelope_error
        ),
        "pending_dig_cut_cycle_id": int(policy._pending_dig_cut_cycle_id),
        "pending_dig_cut_corridor_id": int(policy._pending_dig_cut_corridor_id),
        "dig_cut_token_injected": int(policy._dig_cut_token_injected),
        "dig_cut_planner_mode": str(policy.dig_cut_planner_mode),
        "dig_cut_prior_id": str(policy.dig_cut_prior_id),
        "dig_cut_token_source": str(policy._dig_cut_token_source),
        "dig_cut_token_in_prior_p10_p90": int(
            policy._dig_cut_token_in_prior_p10_p90
        ),
        "dig_cut_fallback_reason": str(policy._dig_cut_fallback_reason),
        "dig_failed_replan_next_skill": str(policy.dig_failed_replan_next_skill),
        "coverage_selected_corridor_id": int(policy._coverage_active_corridor_id),
        "coverage_depleted_count": int(policy._coverage_depleted_count()),
        "coverage_completed_dump_count": int(policy._coverage_completed_dump_count),
        "coverage_pass_index": int(policy._coverage_pass_index),
        "coverage_multi_pass_enabled": int(policy.coverage_multi_pass_enabled),
        "coverage_use_env_removed_depth": int(policy.coverage_use_env_removed_depth),
        "coverage_candidate_layout": str(policy.coverage_candidate_layout),
        "coverage_first_dig_strategy": str(policy.coverage_first_dig_strategy),
        "coverage_first_dig_preferred_corridor_id": int(
            -1
            if policy.coverage_first_dig_preferred_corridor_id is None
            else policy.coverage_first_dig_preferred_corridor_id
        ),
        "coverage_first_dig_max_entry_distance_m": float(
            np.nan
            if policy.coverage_first_dig_max_entry_distance_m is None
            else policy.coverage_first_dig_max_entry_distance_m
        ),
        "coverage_first_dig_qpos_delta_weight": float(
            policy.coverage_first_dig_qpos_delta_weight
        ),
        "coverage_terminal_stop_requested": int(
            policy._coverage_terminal_stop_requested
        ),
        "coverage_terminal_stop_reason": str(policy._coverage_terminal_stop_reason),
        "scripted_bootstrap_timeout_count": int(
            policy._scripted_bootstrap_timeout_count
        ),
        "pre_dig_align_enabled": int(policy.pre_dig_align_enabled),
        "pre_dig_align_first_dig_only": int(policy.pre_dig_align_first_dig_only),
        "pre_dig_align_replan_after_failed_dig": int(
            policy.pre_dig_align_replan_after_failed_dig
        ),
        "pre_dig_align_surface_guard_enabled": int(
            policy.pre_dig_align_surface_guard_enabled
        ),
        "pre_dig_align_surface_guard_count": int(
            policy._pre_dig_align_surface_guard_count
        ),
        "pre_dig_align_timeout_count": int(policy._pre_dig_align_timeout_count),
        "pre_dig_align_completed_count": int(policy._pre_dig_align_completed_count),
        "pre_dig_align_replan_count": int(policy._pre_dig_align_replan_count),
        "dig_bad_replan_count": int(policy._dig_bad_replan_count),
        "dig_exit_guard_replan_count": int(policy._dig_exit_guard_replan_count),
    }
