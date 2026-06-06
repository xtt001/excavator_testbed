"""Primitive planner debug-state and rollout-summary schema builders."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.contracts.primitive_tokens import (
    DIG_CUT_TOKEN_CONTRACT,
    DIG_CUT_TOKEN_DIM,
    DIG_CUT_TOKEN_KEY,
    DIG_DEPTH_PROFILE_TOKEN_DIM,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_START_ENVELOPE_TOKEN_KEY,
    RETURN_TARGET_TOKEN_DIM,
    RETURN_TARGET_TOKEN_KEY,
    token_contract_string,
)
from testbed.planner.cell_entry import CELL_ENTRY_TOKEN_DIM
from testbed.planner.primitive_debug_facts import (
    PrimitiveDebugStateFacts,
    PrimitivePlannerTraceFacts,
    PrimitiveRolloutSummaryFacts,
)

TRANSITION_SOURCE_PRIMITIVE_RETURN_POLICY = "v2_2_primitive_return_policy"
TRANSITION_POLICY_MODE_PRIMITIVE = "primitive_return_policy"


@dataclass(frozen=True)
class PrimitivePlannerDebugState:
    skill_name: str
    skill_id: int
    skill_switch_reason: str
    primitive_checkpoint_path: str
    hybrid_mode: str
    transition_timeout: bool
    transition_completed: bool
    completed_transition_count: int
    transition_timeout_count: int
    dump_ready_hold_count: int
    dump_done_hold_count: int
    primitive_cycle_index: int
    approach_ready_hold_count: int = 0
    dump_release_ready_hold_count: int = 0


@dataclass(frozen=True)
class PrimitiveDebugStateSnapshotConfig:
    skill_ids: Mapping[str, int]
    transition_skill_names: tuple[str, ...]
    transition_hybrid_mode: str
    work_hybrid_mode: str
    primitive_checkpoint_paths: Mapping[str, str]


@dataclass(frozen=True)
class PrimitiveDebugStateSnapshotFacts:
    skill_name: str
    skill_switch_reason: str
    first_dig_policy_active: bool
    transition_timeout: bool
    transition_completed: bool
    completed_transition_count: int
    transition_timeout_count: int
    dump_ready_hold_count: int
    dump_done_hold_count: int
    primitive_cycle_index: int
    approach_ready_hold_count: int = 0
    dump_release_ready_hold_count: int = 0


def build_primitive_debug_state_snapshot(
    *,
    skill_name: str,
    skill_ids: Mapping[str, int],
    transition_skill_names: tuple[str, ...],
    transition_hybrid_mode: str,
    work_hybrid_mode: str,
    skill_switch_reason: str,
    primitive_checkpoint_paths: Mapping[str, str],
    first_dig_policy_active: bool,
    transition_timeout: bool,
    transition_completed: bool,
    completed_transition_count: int,
    transition_timeout_count: int,
    dump_ready_hold_count: int,
    dump_done_hold_count: int,
    primitive_cycle_index: int,
    approach_ready_hold_count: int = 0,
    dump_release_ready_hold_count: int = 0,
) -> PrimitivePlannerDebugState:
    """Build the planner-owned debug-state snapshot without side effects."""
    normalized_skill_name = str(skill_name)
    checkpoint_key = (
        "first_dig" if bool(first_dig_policy_active) else normalized_skill_name
    )
    return PrimitivePlannerDebugState(
        skill_name=normalized_skill_name,
        skill_id=int(skill_ids.get(normalized_skill_name, -1)),
        skill_switch_reason=str(skill_switch_reason),
        primitive_checkpoint_path=str(
            primitive_checkpoint_paths.get(checkpoint_key, "")
        ),
        hybrid_mode=(
            str(transition_hybrid_mode)
            if normalized_skill_name in set(transition_skill_names)
            else str(work_hybrid_mode)
        ),
        transition_timeout=bool(transition_timeout),
        transition_completed=bool(transition_completed),
        completed_transition_count=int(completed_transition_count),
        transition_timeout_count=int(transition_timeout_count),
        dump_ready_hold_count=int(dump_ready_hold_count),
        dump_done_hold_count=int(dump_done_hold_count),
        primitive_cycle_index=int(primitive_cycle_index),
        approach_ready_hold_count=int(approach_ready_hold_count),
        dump_release_ready_hold_count=int(dump_release_ready_hold_count),
    )


def build_primitive_debug_state_snapshot_from_runtime(
    *,
    config: PrimitiveDebugStateSnapshotConfig,
    facts: PrimitiveDebugStateSnapshotFacts,
) -> PrimitivePlannerDebugState:
    """Project scheduler-owned runtime facts into the debug-state snapshot."""
    return build_primitive_debug_state_snapshot(
        skill_name=facts.skill_name,
        skill_ids=config.skill_ids,
        transition_skill_names=config.transition_skill_names,
        transition_hybrid_mode=config.transition_hybrid_mode,
        work_hybrid_mode=config.work_hybrid_mode,
        skill_switch_reason=facts.skill_switch_reason,
        primitive_checkpoint_paths=config.primitive_checkpoint_paths,
        first_dig_policy_active=facts.first_dig_policy_active,
        transition_timeout=facts.transition_timeout,
        transition_completed=facts.transition_completed,
        completed_transition_count=facts.completed_transition_count,
        transition_timeout_count=facts.transition_timeout_count,
        dump_ready_hold_count=facts.dump_ready_hold_count,
        dump_done_hold_count=facts.dump_done_hold_count,
        primitive_cycle_index=facts.primitive_cycle_index,
        approach_ready_hold_count=facts.approach_ready_hold_count,
        dump_release_ready_hold_count=facts.dump_release_ready_hold_count,
    )


def build_primitive_debug_state_from_facts(
    facts: PrimitiveDebugStateFacts,
) -> dict[str, Any]:
    """Build the public debug-state schema from explicit debug facts."""
    return {
        "skill_name": facts.debug_state.skill_name,
        "skill_id": int(facts.debug_state.skill_id),
        "skill_switch_reason": facts.debug_state.skill_switch_reason,
        "primitive_checkpoint_path": facts.debug_state.primitive_checkpoint_path,
        "hybrid_mode": facts.debug_state.hybrid_mode,
        "transition_timeout": bool(facts.debug_state.transition_timeout),
        "transition_completed": bool(facts.debug_state.transition_completed),
        "transition_source": TRANSITION_SOURCE_PRIMITIVE_RETURN_POLICY,
        "transition_policy_mode": TRANSITION_POLICY_MODE_PRIMITIVE,
        "transition_fallback_count": 0,
        "transition_fallback_reason": "",
        "completed_transition_count": int(facts.debug_state.completed_transition_count),
        "transition_timeout_count": int(facts.debug_state.transition_timeout_count),
        "dump_ready_hold_count": int(facts.debug_state.dump_ready_hold_count),
        "dump_done_hold_count": int(facts.debug_state.dump_done_hold_count),
        "approach_ready_hold_count": int(facts.debug_state.approach_ready_hold_count),
        "dump_release_ready_hold_count": int(
            facts.debug_state.dump_release_ready_hold_count
        ),
        "primitive_cycle_index": int(facts.debug_state.primitive_cycle_index),
        "primitive_goal_curr_sector_id": int(facts.primitive_goal_curr_sector_id),
        "primitive_goal_next_sector_id": int(facts.primitive_goal_next_sector_id),
        "cell_entry_enabled": bool(facts.cell_entry_enabled),
        "cell_entry_token_injected": bool(facts.cell_entry_token_injected),
        "cell_entry_token_dim": int(CELL_ENTRY_TOKEN_DIM),
        "dig_cut_token_injected": bool(facts.dig_cut_token_injected),
        "dig_cut_token_dim": int(DIG_CUT_TOKEN_DIM),
        "dig_depth_profile_token_injected": bool(
            facts.dig_depth_profile_token_injected
        ),
        "dig_depth_profile_token_dim": int(DIG_DEPTH_PROFILE_TOKEN_DIM),
        "dig_depth_profile_source": str(facts.dig_depth_profile_source),
        "dig_depth_profile_required": bool(facts.dig_depth_profile_required),
        "dig_depth_profile_token_source": str(facts.dig_depth_profile_token_source),
        "dig_depth_profile_fallback_reason": str(
            facts.dig_depth_profile_fallback_reason
        ),
        "dig_failed_replan_next_skill": str(facts.dig_failed_replan_next_skill),
        "return_target_token_injected": bool(facts.return_target_token_injected),
        "return_target_token_dim": int(RETURN_TARGET_TOKEN_DIM),
        "return_target_token_source": str(facts.return_target_token_source),
        "return_target_tokens": facts.return_target_tokens.astype(float).tolist(),
        "return_target_fallback_reason": str(facts.return_target_fallback_reason),
        "return_relocate_token_injected": bool(
            facts.return_relocate_token_injected
        ),
        "return_relocate_token_dim": int(RETURN_TARGET_TOKEN_DIM),
        "return_relocate_token_source": str(facts.return_target_token_source),
        "return_relocate_tokens": facts.return_relocate_tokens.astype(float).tolist(),
        "return_start_envelope_token_injected": bool(
            facts.return_start_envelope_token_injected
        ),
        "return_start_envelope_token_dim": int(RETURN_START_ENVELOPE_TOKEN_DIM),
        "return_start_envelope_token_source": str(
            facts.return_start_envelope_token_source
        ),
        "return_start_envelope_tokens": (
            facts.return_start_envelope_tokens.astype(float).tolist()
        ),
        "return_to_dig_entry_error_m": float(facts.return_to_dig_entry_error_m),
        "return_to_dig_entry_close": bool(facts.return_to_dig_entry_close),
        "return_next_dig_event_seen": bool(facts.return_next_dig_event_seen),
        "return_to_dig_start_envelope_gate_enabled": bool(
            facts.return_to_dig_start_envelope_gate_enabled
        ),
        "return_to_dig_start_envelope_direct_handoff_enabled": bool(
            facts.return_to_dig_start_envelope_direct_handoff_enabled
        ),
        "return_to_dig_start_envelope_ready": bool(
            facts.return_to_dig_start_envelope_ready
        ),
        "return_to_dig_start_envelope_plane_depth_mode": str(
            facts.return_to_dig_start_envelope_plane_depth_mode
        ),
        "return_to_dig_start_envelope_local_depth_tolerance_m": float(
            facts.return_to_dig_start_envelope_local_depth_tolerance_m
        ),
        "return_to_dig_start_envelope_error": float(
            facts.return_to_dig_start_envelope_error
        ),
        "return_to_dig_start_envelope_checks": dict(
            facts.return_to_dig_start_envelope_checks
        ),
        "pending_dig_cut_cycle_id": int(facts.pending_dig_cut_cycle_id),
        "pending_dig_cut_corridor_id": int(facts.pending_dig_cut_corridor_id),
        "dig_cut_planner_mode": str(facts.dig_cut_planner_mode),
        "dig_cut_prior_id": str(facts.dig_cut_prior_id),
        "dig_cut_token_source": str(facts.dig_cut_token_source),
        "dig_cut_tokens": facts.dig_cut_tokens.astype(float).tolist(),
        "dig_depth_profile_tokens": (
            facts.dig_depth_profile_tokens.astype(float).tolist()
        ),
        "token_in_prior_p10_p90": bool(facts.dig_cut_token_in_prior_p10_p90),
        "dig_cut_token_in_prior_p10_p90": bool(
            facts.dig_cut_token_in_prior_p10_p90
        ),
        "fallback_reason": str(facts.dig_cut_fallback_reason),
        "dig_cut_fallback_reason": str(facts.dig_cut_fallback_reason),
        "coverage_corridor_id": int(facts.coverage_active_corridor_id),
        "coverage_selected_corridor_id": int(facts.coverage_active_corridor_id),
        "coverage_last_selected_corridor_id": int(
            facts.coverage_last_selected_corridor_id
        ),
        "coverage_last_selected_cell_id": int(facts.coverage_last_selected_cell_id),
        "coverage_last_selected_row_id": int(facts.coverage_last_selected_row_id),
        "coverage_entry_x_m": float(facts.coverage_active_values["entry_x_m"]),
        "coverage_entry_z_m": float(facts.coverage_active_values["entry_z_m"]),
        "coverage_exit_x_m": float(facts.coverage_active_values["exit_x_m"]),
        "coverage_exit_z_m": float(facts.coverage_active_values["exit_z_m"]),
        "coverage_entry_x_p05_m": float(
            facts.coverage_active_values["entry_x_p05_m"]
        ),
        "coverage_entry_x_p50_m": float(
            facts.coverage_active_values["entry_x_p50_m"]
        ),
        "coverage_entry_x_p95_m": float(
            facts.coverage_active_values["entry_x_p95_m"]
        ),
        "coverage_entry_z_p05_m": float(
            facts.coverage_active_values["entry_z_p05_m"]
        ),
        "coverage_entry_z_p50_m": float(
            facts.coverage_active_values["entry_z_p50_m"]
        ),
        "coverage_entry_z_p95_m": float(
            facts.coverage_active_values["entry_z_p95_m"]
        ),
        "coverage_entry_radial_p75_m": float(
            facts.coverage_active_values["entry_radial_p75_m"]
        ),
        "coverage_entry_radial_p95_m": float(
            facts.coverage_active_values["entry_radial_p95_m"]
        ),
        "coverage_exit_x_p05_m": float(
            facts.coverage_active_values["exit_x_p05_m"]
        ),
        "coverage_exit_x_p50_m": float(
            facts.coverage_active_values["exit_x_p50_m"]
        ),
        "coverage_exit_x_p95_m": float(
            facts.coverage_active_values["exit_x_p95_m"]
        ),
        "coverage_exit_z_p05_m": float(
            facts.coverage_active_values["exit_z_p05_m"]
        ),
        "coverage_exit_z_p50_m": float(
            facts.coverage_active_values["exit_z_p50_m"]
        ),
        "coverage_exit_z_p95_m": float(
            facts.coverage_active_values["exit_z_p95_m"]
        ),
        "coverage_exit_radial_p75_m": float(
            facts.coverage_active_values["exit_radial_p75_m"]
        ),
        "coverage_exit_radial_p95_m": float(
            facts.coverage_active_values["exit_radial_p95_m"]
        ),
        "coverage_cut_depth_peak_p05_m": float(
            facts.coverage_active_values["cut_depth_peak_p05_m"]
        ),
        "coverage_cut_depth_peak_p50_m": float(
            facts.coverage_active_values["cut_depth_peak_p50_m"]
        ),
        "coverage_cut_depth_peak_p95_m": float(
            facts.coverage_active_values["cut_depth_peak_p95_m"]
        ),
        "coverage_cell_id": int(facts.coverage_active_cell_id),
        "coverage_corridor_score": float(facts.coverage_active_corridor_score),
        "coverage_state_exemplar_enabled": bool(
            facts.coverage_state_exemplar_enabled
        ),
        "coverage_state_exemplar_ids": list(facts.coverage_active_state_exemplar_ids),
        "coverage_state_exemplar_distance": float(
            facts.coverage_active_state_exemplar_distance
        ),
        "coverage_depleted_count": int(facts.coverage_depleted_count),
        "coverage_pass_index": int(facts.coverage_pass_index),
        "coverage_multi_pass_enabled": bool(facts.coverage_multi_pass_enabled),
        "coverage_multi_pass_max_passes": int(facts.coverage_multi_pass_max_passes),
        "coverage_multi_pass_min_remaining_depth_m": float(
            facts.coverage_multi_pass_min_remaining_depth_m
        ),
        "coverage_last_payload_gain_kg": float(facts.coverage_last_payload_gain_kg),
        "coverage_last_effective_deposit_delta_kg": float(
            facts.coverage_last_effective_deposit_delta_kg
        ),
        "coverage_global_low_productivity_streak": int(
            facts.coverage_global_low_productivity_streak
        ),
        "coverage_use_env_removed_depth": bool(facts.coverage_use_env_removed_depth),
        "coverage_candidate_layout": str(facts.coverage_candidate_layout),
        "coverage_first_dig_strategy": str(facts.coverage_first_dig_strategy),
        "coverage_first_dig_preferred_corridor_id": int(
            -1
            if facts.coverage_first_dig_preferred_corridor_id is None
            else facts.coverage_first_dig_preferred_corridor_id
        ),
        "coverage_first_dig_max_entry_distance_m": float(
            np.nan
            if facts.coverage_first_dig_max_entry_distance_m is None
            else facts.coverage_first_dig_max_entry_distance_m
        ),
        "coverage_first_dig_qpos_delta_weight": float(
            facts.coverage_first_dig_qpos_delta_weight
        ),
        "coverage_first_dig_max_qpos_delta": (
            None
            if facts.coverage_first_dig_max_qpos_delta is None
            else facts.coverage_first_dig_max_qpos_delta.astype(float).tolist()
        ),
        "coverage_terminal_stop_requested": bool(
            facts.coverage_terminal_stop_requested
        ),
        "coverage_terminal_stop_reason": str(facts.coverage_terminal_stop_reason),
        "coverage_corridors": list(facts.coverage_corridors),
        "planner_terminal_stop_requested": bool(
            facts.coverage_terminal_stop_requested
        ),
        "planner_terminal_stop_reason": str(facts.coverage_terminal_stop_reason),
        "coverage_candidate_scores": list(facts.coverage_candidate_scores),
        "cell_entry_selected_cell_id": int(facts.cell_entry_selected_cell_id),
        "cell_entry_selected_long_index": int(facts.cell_entry_selected_long_index),
        "cell_entry_selected_short_index": int(facts.cell_entry_selected_short_index),
        "cell_entry_planned_entry_x_m": float(facts.cell_entry_planned_entry_x_m),
        "cell_entry_planned_entry_y_m": float(facts.cell_entry_planned_entry_y_m),
        "cell_entry_planned_entry_z_m": float(facts.cell_entry_planned_entry_z_m),
        "cell_entry_planner_ok": bool(facts.cell_entry_planner_ok),
        "cell_entry_audit_reason_code": int(facts.cell_entry_audit_reason_code),
        "cell_entry_audit_reason": str(facts.cell_entry_audit_reason),
        "cell_entry_audit_risk_flags": int(facts.cell_entry_audit_risk_flags),
        "cell_entry_inside_entry_envelope": bool(
            facts.cell_entry_inside_entry_envelope
        ),
        "cell_entry_distance_to_entry_envelope_m": float(
            facts.cell_entry_distance_to_entry_envelope_m
        ),
        "cell_entry_seen_cell_id": int(facts.cell_entry_seen_cell_id),
        "scripted_bootstrap_step_count": int(facts.scripted_bootstrap_step_count),
        "scripted_bootstrap_hold_count": int(facts.scripted_bootstrap_hold_count),
        "scripted_bootstrap_timeout_count": int(
            facts.scripted_bootstrap_timeout_count
        ),
        "dig_step_count": int(facts.dig_step_count),
        "dig_best_mass_kg": float(facts.dig_best_mass_kg),
        "dig_mass_plateau_count": int(facts.dig_mass_plateau_count),
        "dig_to_carry_reason": str(facts.dig_to_carry_reason),
        "dig_bad_replan_count": int(facts.dig_bad_replan_count),
        "dig_exit_guard_replan_count": int(facts.dig_exit_guard_replan_count),
        "pre_dig_align_enabled": bool(facts.pre_dig_align_enabled),
        "pre_dig_align_first_dig_only": bool(facts.pre_dig_align_first_dig_only),
        "pre_dig_align_replan_after_failed_dig": bool(
            facts.pre_dig_align_replan_after_failed_dig
        ),
        "pre_dig_align_entry_intent_controlled_dims": (
            None
            if facts.pre_dig_align_entry_intent_controlled_dims is None
            else [
                int(value)
                for value in (
                    facts.pre_dig_align_entry_intent_controlled_dims.tolist()
                )
            ]
        ),
        "pre_dig_align_surface_guard_enabled": bool(
            facts.pre_dig_align_surface_guard_enabled
        ),
        "pre_dig_align_surface_depth_m": float(facts.pre_dig_align_surface_depth_m),
        "pre_dig_align_surface_guard_triggered": bool(
            facts.pre_dig_align_surface_guard_triggered
        ),
        "pre_dig_align_surface_guard_count": int(
            facts.pre_dig_align_surface_guard_count
        ),
        "pre_dig_align_active_for_next_dig": bool(
            facts.pre_dig_align_active_for_next_dig
        ),
        "pre_dig_align_step_count": int(facts.pre_dig_align_step_count),
        "pre_dig_align_hold_count": int(facts.pre_dig_align_hold_count),
        "pre_dig_align_timeout_count": int(facts.pre_dig_align_timeout_count),
        "pre_dig_align_completed_count": int(facts.pre_dig_align_completed_count),
        "pre_dig_align_replan_count": int(facts.pre_dig_align_replan_count),
        "pre_dig_align_target_qpos": (
            facts.pre_dig_align_target_qpos.astype(float).tolist()
        ),
        "pre_dig_align_error": facts.pre_dig_align_error.astype(float).tolist(),
        "pre_dig_align_entry_error_m": float(facts.pre_dig_align_entry_error_m),
        "pre_dig_align_start_envelope_ready": bool(
            facts.pre_dig_align_start_envelope_ready
        ),
        "pre_dig_align_first_dig_entry_close_handoff": bool(
            facts.pre_dig_align_first_dig_entry_close_handoff
        ),
        "pre_dig_align_entry_close_handoff_ready": bool(
            facts.pre_dig_align_entry_close_handoff_ready
        ),
        "pre_dig_align_entry_intent_handoff_enabled": bool(
            facts.pre_dig_align_entry_intent_handoff_enabled
        ),
        "pre_dig_align_entry_intent_handoff_ready": bool(
            facts.pre_dig_align_entry_intent_handoff_ready
        ),
        "pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max": float(
            np.nan
            if facts.pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max is None
            else facts.pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max
        ),
        "pre_dig_align_controlled_dims": [
            int(value) for value in facts.pre_dig_align_controlled_dims.tolist()
        ],
        "pre_dig_align_bucket_target_qpos": float(
            np.nan
            if facts.pre_dig_align_bucket_target_qpos is None
            else facts.pre_dig_align_bucket_target_qpos
        ),
    }


def build_primitive_debug_state(policy: Any) -> dict[str, Any]:
    """Build the public debug-state schema for legacy direct callers."""
    return build_primitive_debug_state_from_facts(policy._debug_state_facts())


def build_primitive_planner_trace_from_facts(
    facts: PrimitivePlannerTraceFacts,
) -> dict[str, object]:
    """Build the planner trace payload from explicit trace facts."""
    return {
        "cell_entry_trace": list(facts.cell_entry_trace),
        "dig_cut_token_contract_version": DIG_CUT_TOKEN_CONTRACT,
        "dig_cut_token_contract": token_contract_string(DIG_CUT_TOKEN_KEY),
        "dig_cut_planner_mode": str(facts.dig_cut_planner_mode),
        "dig_cut_prior_id": str(facts.dig_cut_prior_id),
        "dig_cut_prior_path": str(facts.dig_cut_prior_path),
        "return_target_token_contract_version": DIG_CUT_TOKEN_CONTRACT,
        "return_target_token_contract": token_contract_string(
            RETURN_TARGET_TOKEN_KEY,
            prefix="next",
        ),
        "return_start_envelope_token_contract_version": RETURN_START_ENVELOPE_TOKEN_KEY,
        "return_start_envelope_token_contract": token_contract_string(
            RETURN_START_ENVELOPE_TOKEN_KEY
        ),
        "return_target_planner_enabled": bool(facts.return_target_planner_enabled),
        "coverage_use_env_removed_depth": bool(facts.coverage_use_env_removed_depth),
        "coverage_candidate_layout": str(facts.coverage_candidate_layout),
        "coverage_first_dig_strategy": str(facts.coverage_first_dig_strategy),
        "coverage_pass_index": int(facts.coverage_pass_index),
        "coverage_multi_pass_enabled": bool(facts.coverage_multi_pass_enabled),
        "coverage_multi_pass_max_passes": int(facts.coverage_multi_pass_max_passes),
        "coverage_multi_pass_min_remaining_depth_m": float(
            facts.coverage_multi_pass_min_remaining_depth_m
        ),
        "coverage_first_dig_preferred_corridor_id": int(
            -1
            if facts.coverage_first_dig_preferred_corridor_id is None
            else facts.coverage_first_dig_preferred_corridor_id
        ),
        "coverage_corridors": list(facts.coverage_corridors),
        "coverage_decision_trace": list(facts.coverage_decision_trace),
        "coverage_decision_trace_count": int(len(facts.coverage_decision_trace)),
        "coverage_terminal_stop_requested": bool(
            facts.coverage_terminal_stop_requested
        ),
        "coverage_terminal_stop_reason": str(facts.coverage_terminal_stop_reason),
    }


def build_primitive_planner_trace(policy: Any) -> dict[str, object]:
    """Build the planner trace payload for legacy direct callers."""
    return build_primitive_planner_trace_from_facts(policy._planner_trace_facts())


def build_primitive_rollout_summary_from_facts(
    facts: PrimitiveRolloutSummaryFacts,
) -> dict[str, float | int | str | list[str]]:
    """Build the public rollout-summary schema from explicit summary facts."""
    return {
        "transition_source": TRANSITION_SOURCE_PRIMITIVE_RETURN_POLICY,
        "transition_policy_mode": TRANSITION_POLICY_MODE_PRIMITIVE,
        "transition_fallback_count": 0,
        "transition_fallback_reason": "",
        "transition_timeout_count": int(facts.transition_timeout_count),
        "completed_transition_count": int(facts.completed_transition_count),
        "dump_done_use_boundary_event": int(facts.dump_done_use_boundary_event),
        "primitive_final_skill": str(facts.primitive_final_skill),
        "primitive_cycle_index": int(facts.primitive_cycle_index),
        "cell_entry_enabled": int(facts.cell_entry_enabled),
        "cell_entry_trace_count": int(facts.cell_entry_trace_count),
        "dig_cut_token_dim": int(DIG_CUT_TOKEN_DIM),
        "return_target_token_dim": int(RETURN_TARGET_TOKEN_DIM),
        "return_target_token_source": str(facts.return_target_token_source),
        "return_to_dig_max_entry_error_m": float(
            np.nan
            if facts.return_to_dig_max_entry_error_m is None
            else facts.return_to_dig_max_entry_error_m
        ),
        "return_to_dig_entry_error_m": float(facts.return_to_dig_entry_error_m),
        "return_to_dig_entry_close": int(facts.return_to_dig_entry_close),
        "return_next_dig_event_seen": int(facts.return_next_dig_event_seen),
        "return_to_dig_start_envelope_gate_enabled": int(
            facts.return_to_dig_start_envelope_gate_enabled
        ),
        "return_to_dig_start_envelope_direct_handoff_enabled": int(
            facts.return_to_dig_start_envelope_direct_handoff_enabled
        ),
        "return_to_dig_start_envelope_ready": int(
            facts.return_to_dig_start_envelope_ready
        ),
        "return_to_dig_start_envelope_plane_depth_mode": str(
            facts.return_to_dig_start_envelope_plane_depth_mode
        ),
        "return_to_dig_start_envelope_local_depth_tolerance_m": float(
            facts.return_to_dig_start_envelope_local_depth_tolerance_m
        ),
        "return_to_dig_start_envelope_error": float(
            facts.return_to_dig_start_envelope_error
        ),
        "pending_dig_cut_cycle_id": int(facts.pending_dig_cut_cycle_id),
        "pending_dig_cut_corridor_id": int(facts.pending_dig_cut_corridor_id),
        "dig_cut_token_injected": int(facts.dig_cut_token_injected),
        "dig_cut_planner_mode": str(facts.dig_cut_planner_mode),
        "dig_cut_prior_id": str(facts.dig_cut_prior_id),
        "dig_cut_token_source": str(facts.dig_cut_token_source),
        "dig_cut_token_in_prior_p10_p90": int(
            facts.dig_cut_token_in_prior_p10_p90
        ),
        "dig_cut_fallback_reason": str(facts.dig_cut_fallback_reason),
        "dig_failed_replan_next_skill": str(facts.dig_failed_replan_next_skill),
        "coverage_selected_corridor_id": int(facts.coverage_selected_corridor_id),
        "coverage_depleted_count": int(facts.coverage_depleted_count),
        "coverage_completed_dump_count": int(facts.coverage_completed_dump_count),
        "coverage_pass_index": int(facts.coverage_pass_index),
        "coverage_multi_pass_enabled": int(facts.coverage_multi_pass_enabled),
        "coverage_use_env_removed_depth": int(facts.coverage_use_env_removed_depth),
        "coverage_candidate_layout": str(facts.coverage_candidate_layout),
        "coverage_first_dig_strategy": str(facts.coverage_first_dig_strategy),
        "coverage_first_dig_preferred_corridor_id": int(
            -1
            if facts.coverage_first_dig_preferred_corridor_id is None
            else facts.coverage_first_dig_preferred_corridor_id
        ),
        "coverage_first_dig_max_entry_distance_m": float(
            np.nan
            if facts.coverage_first_dig_max_entry_distance_m is None
            else facts.coverage_first_dig_max_entry_distance_m
        ),
        "coverage_first_dig_qpos_delta_weight": float(
            facts.coverage_first_dig_qpos_delta_weight
        ),
        "coverage_terminal_stop_requested": int(facts.coverage_terminal_stop_requested),
        "coverage_terminal_stop_reason": str(facts.coverage_terminal_stop_reason),
        "scripted_bootstrap_timeout_count": int(
            facts.scripted_bootstrap_timeout_count
        ),
        "pre_dig_align_enabled": int(facts.pre_dig_align_enabled),
        "pre_dig_align_first_dig_only": int(facts.pre_dig_align_first_dig_only),
        "pre_dig_align_replan_after_failed_dig": int(
            facts.pre_dig_align_replan_after_failed_dig
        ),
        "pre_dig_align_surface_guard_enabled": int(
            facts.pre_dig_align_surface_guard_enabled
        ),
        "pre_dig_align_surface_guard_count": int(
            facts.pre_dig_align_surface_guard_count
        ),
        "pre_dig_align_timeout_count": int(facts.pre_dig_align_timeout_count),
        "pre_dig_align_completed_count": int(facts.pre_dig_align_completed_count),
        "pre_dig_align_replan_count": int(facts.pre_dig_align_replan_count),
        "dig_bad_replan_count": int(facts.dig_bad_replan_count),
        "dig_exit_guard_replan_count": int(facts.dig_exit_guard_replan_count),
    }


def build_primitive_rollout_summary(
    policy: Any,
) -> dict[str, float | int | str | list[str]]:
    """Build the public rollout-summary schema for legacy direct callers."""
    return build_primitive_rollout_summary_from_facts(policy._rollout_summary_facts())
