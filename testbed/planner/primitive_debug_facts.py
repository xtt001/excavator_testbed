"""Primitive debug-state facts assembly from service snapshots."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from testbed.planner.primitive_debug import PrimitivePlannerDebugState


@dataclass(frozen=True)
class PrimitiveDebugStateFacts:
    debug_state: PrimitivePlannerDebugState
    primitive_goal_curr_sector_id: int
    primitive_goal_next_sector_id: int
    cell_entry_enabled: bool
    cell_entry_token_injected: bool
    dig_cut_token_injected: bool
    dig_depth_profile_token_injected: bool
    dig_depth_profile_source: str
    dig_depth_profile_required: bool
    dig_depth_profile_token_source: str
    dig_depth_profile_fallback_reason: str
    dig_failed_replan_next_skill: str
    return_target_token_injected: bool
    return_target_token_source: str
    return_target_tokens: np.ndarray
    return_target_fallback_reason: str
    return_relocate_token_injected: bool
    return_relocate_tokens: np.ndarray
    return_start_envelope_token_injected: bool
    return_start_envelope_token_source: str
    return_start_envelope_tokens: np.ndarray
    return_to_dig_entry_error_m: float
    return_to_dig_entry_close: bool
    return_next_dig_event_seen: bool
    return_to_dig_start_envelope_gate_enabled: bool
    return_to_dig_start_envelope_direct_handoff_enabled: bool
    return_to_dig_start_envelope_ready: bool
    return_to_dig_start_envelope_plane_depth_mode: str
    return_to_dig_start_envelope_local_depth_tolerance_m: float
    return_to_dig_start_envelope_error: float
    return_to_dig_start_envelope_checks: Mapping[str, Any]
    pending_dig_cut_cycle_id: int
    pending_dig_cut_corridor_id: int
    dig_cut_planner_mode: str
    dig_cut_prior_id: str
    dig_cut_token_source: str
    dig_cut_tokens: np.ndarray
    dig_depth_profile_tokens: np.ndarray
    dig_cut_token_in_prior_p10_p90: bool
    dig_cut_fallback_reason: str
    coverage_active_corridor_id: int
    coverage_last_selected_corridor_id: int
    coverage_last_selected_cell_id: int
    coverage_last_selected_row_id: int
    coverage_active_values: Mapping[str, float]
    coverage_active_cell_id: int
    coverage_active_corridor_score: float
    coverage_state_exemplar_enabled: bool
    coverage_active_state_exemplar_ids: tuple[Any, ...]
    coverage_active_state_exemplar_distance: float
    coverage_depleted_count: int
    coverage_pass_index: int
    coverage_multi_pass_enabled: bool
    coverage_multi_pass_max_passes: int
    coverage_multi_pass_min_remaining_depth_m: float
    coverage_last_payload_gain_kg: float
    coverage_last_effective_deposit_delta_kg: float
    coverage_global_low_productivity_streak: int
    coverage_use_env_removed_depth: bool
    coverage_candidate_layout: str
    coverage_first_dig_strategy: str
    coverage_first_dig_preferred_corridor_id: int | None
    coverage_first_dig_max_entry_distance_m: float | None
    coverage_first_dig_qpos_delta_weight: float
    coverage_first_dig_max_qpos_delta: np.ndarray | None
    coverage_terminal_stop_requested: bool
    coverage_terminal_stop_reason: str
    coverage_corridors: tuple[Mapping[str, Any], ...]
    coverage_candidate_scores: tuple[Any, ...]
    cell_entry_selected_cell_id: int
    cell_entry_selected_long_index: int
    cell_entry_selected_short_index: int
    cell_entry_planned_entry_x_m: float
    cell_entry_planned_entry_y_m: float
    cell_entry_planned_entry_z_m: float
    cell_entry_planner_ok: bool
    cell_entry_audit_reason_code: int
    cell_entry_audit_reason: str
    cell_entry_audit_risk_flags: int
    cell_entry_inside_entry_envelope: bool
    cell_entry_distance_to_entry_envelope_m: float
    cell_entry_seen_cell_id: int
    scripted_bootstrap_step_count: int
    scripted_bootstrap_hold_count: int
    scripted_bootstrap_timeout_count: int
    dig_step_count: int
    dig_best_mass_kg: float
    dig_mass_plateau_count: int
    dig_to_carry_reason: str
    dig_bad_replan_count: int
    dig_exit_guard_replan_count: int
    pre_dig_align_enabled: bool
    pre_dig_align_first_dig_only: bool
    pre_dig_align_replan_after_failed_dig: bool
    pre_dig_align_entry_intent_controlled_dims: np.ndarray | None
    pre_dig_align_surface_guard_enabled: bool
    pre_dig_align_surface_depth_m: float
    pre_dig_align_surface_guard_triggered: bool
    pre_dig_align_surface_guard_count: int
    pre_dig_align_active_for_next_dig: bool
    pre_dig_align_step_count: int
    pre_dig_align_hold_count: int
    pre_dig_align_timeout_count: int
    pre_dig_align_completed_count: int
    pre_dig_align_replan_count: int
    pre_dig_align_target_qpos: np.ndarray
    pre_dig_align_error: np.ndarray
    pre_dig_align_entry_error_m: float
    pre_dig_align_start_envelope_ready: bool
    pre_dig_align_first_dig_entry_close_handoff: bool
    pre_dig_align_entry_close_handoff_ready: bool
    pre_dig_align_entry_intent_handoff_enabled: bool
    pre_dig_align_entry_intent_handoff_ready: bool
    pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max: float | None
    pre_dig_align_controlled_dims: np.ndarray
    pre_dig_align_bucket_target_qpos: float | None


@dataclass(frozen=True)
class PrimitivePlannerTraceFacts:
    cell_entry_trace: tuple[Mapping[str, Any], ...]
    dig_cut_planner_mode: str
    dig_cut_prior_id: str
    dig_cut_prior_path: str
    return_target_planner_enabled: bool
    coverage_use_env_removed_depth: bool
    coverage_candidate_layout: str
    coverage_first_dig_strategy: str
    coverage_pass_index: int
    coverage_multi_pass_enabled: bool
    coverage_multi_pass_max_passes: int
    coverage_multi_pass_min_remaining_depth_m: float
    coverage_first_dig_preferred_corridor_id: int | None
    coverage_corridors: tuple[Mapping[str, Any], ...]
    coverage_decision_trace: tuple[Mapping[str, Any], ...]
    coverage_terminal_stop_requested: bool
    coverage_terminal_stop_reason: str


@dataclass(frozen=True)
class PrimitiveRolloutSummaryFacts:
    transition_timeout_count: int
    completed_transition_count: int
    dump_done_use_boundary_event: bool
    primitive_final_skill: str
    primitive_cycle_index: int
    cell_entry_enabled: bool
    cell_entry_trace_count: int
    return_target_token_source: str
    return_to_dig_max_entry_error_m: float | None
    return_to_dig_entry_error_m: float
    return_to_dig_entry_close: bool
    return_next_dig_event_seen: bool
    return_to_dig_start_envelope_gate_enabled: bool
    return_to_dig_start_envelope_direct_handoff_enabled: bool
    return_to_dig_start_envelope_ready: bool
    return_to_dig_start_envelope_plane_depth_mode: str
    return_to_dig_start_envelope_local_depth_tolerance_m: float
    return_to_dig_start_envelope_error: float
    pending_dig_cut_cycle_id: int
    pending_dig_cut_corridor_id: int
    dig_cut_token_injected: bool
    dig_cut_planner_mode: str
    dig_cut_prior_id: str
    dig_cut_token_source: str
    dig_cut_token_in_prior_p10_p90: bool
    dig_cut_fallback_reason: str
    dig_failed_replan_next_skill: str
    coverage_selected_corridor_id: int
    coverage_depleted_count: int
    coverage_completed_dump_count: int
    coverage_pass_index: int
    coverage_multi_pass_enabled: bool
    coverage_use_env_removed_depth: bool
    coverage_candidate_layout: str
    coverage_first_dig_strategy: str
    coverage_first_dig_preferred_corridor_id: int | None
    coverage_first_dig_max_entry_distance_m: float | None
    coverage_first_dig_qpos_delta_weight: float
    coverage_terminal_stop_requested: bool
    coverage_terminal_stop_reason: str
    scripted_bootstrap_timeout_count: int
    pre_dig_align_enabled: bool
    pre_dig_align_first_dig_only: bool
    pre_dig_align_replan_after_failed_dig: bool
    pre_dig_align_surface_guard_enabled: bool
    pre_dig_align_surface_guard_count: int
    pre_dig_align_timeout_count: int
    pre_dig_align_completed_count: int
    pre_dig_align_replan_count: int
    dig_bad_replan_count: int
    dig_exit_guard_replan_count: int


@dataclass(frozen=True)
class PrimitiveDebugStateAssemblyInputs:
    debug_state: PrimitivePlannerDebugState
    primitive_goal_curr_sector_id: int
    primitive_goal_next_sector_id: int
    cell_entry_enabled: bool
    cell_entry_token_injected: bool
    pre_dig_align_first_dig_only: bool
    pre_dig_align_replan_after_failed_dig: bool
    pre_dig_align_active_for_next_dig: bool
    coverage_debug: Any
    return_handoff_status: Any
    dig_cut_status: Any
    dig_depth_profile_status: Any
    return_target_status: Any
    dig_lifecycle_status: Any
    bootstrap_status: Any
    cell_entry_debug: Any
    pre_dig_align_debug: Any


PRIMITIVE_DEBUG_STATE_ASSEMBLY_FIELDS: tuple[tuple[str, str], ...] = (
    ("debug_state", "_debug_state"),
    ("cell_entry_enabled", "cell_entry_enabled"),
    ("cell_entry_token_injected", "_cell_entry_token_injected"),
    ("pre_dig_align_first_dig_only", "pre_dig_align_first_dig_only"),
    (
        "pre_dig_align_replan_after_failed_dig",
        "pre_dig_align_replan_after_failed_dig",
    ),
)


def build_primitive_debug_state_assembly_inputs_from_mapping(
    values: Mapping[str, Any],
    *,
    primitive_goal_curr_sector_id: Any,
    primitive_goal_next_sector_id: Any,
    pre_dig_align_active_for_next_dig: Any,
    coverage_debug: Any,
    return_handoff_status: Any,
    dig_cut_status: Any,
    dig_depth_profile_status: Any,
    return_target_status: Any,
    dig_lifecycle_status: Any,
    bootstrap_status: Any,
    cell_entry_debug: Any,
    pre_dig_align_debug: Any,
) -> PrimitiveDebugStateAssemblyInputs:
    return PrimitiveDebugStateAssemblyInputs(
        debug_state=values["debug_state"],
        primitive_goal_curr_sector_id=int(primitive_goal_curr_sector_id),
        primitive_goal_next_sector_id=int(primitive_goal_next_sector_id),
        cell_entry_enabled=bool(values["cell_entry_enabled"]),
        cell_entry_token_injected=bool(values["cell_entry_token_injected"]),
        pre_dig_align_first_dig_only=bool(
            values["pre_dig_align_first_dig_only"]
        ),
        pre_dig_align_replan_after_failed_dig=bool(
            values["pre_dig_align_replan_after_failed_dig"]
        ),
        pre_dig_align_active_for_next_dig=bool(
            pre_dig_align_active_for_next_dig
        ),
        coverage_debug=coverage_debug,
        return_handoff_status=return_handoff_status,
        dig_cut_status=dig_cut_status,
        dig_depth_profile_status=dig_depth_profile_status,
        return_target_status=return_target_status,
        dig_lifecycle_status=dig_lifecycle_status,
        bootstrap_status=bootstrap_status,
        cell_entry_debug=cell_entry_debug,
        pre_dig_align_debug=pre_dig_align_debug,
    )


@dataclass(frozen=True)
class PrimitiveRolloutSummaryAssemblyInputs:
    transition_timeout_count: int
    completed_transition_count: int
    dump_done_use_boundary_event: bool
    primitive_final_skill: str
    primitive_cycle_index: int
    cell_entry_enabled: bool
    cell_entry_trace_count: int
    pre_dig_align_first_dig_only: bool
    pre_dig_align_replan_after_failed_dig: bool
    coverage_summary: Any
    return_handoff_status: Any
    dig_cut_status: Any
    return_target_status: Any
    dig_lifecycle_status: Any
    bootstrap_status: Any
    pre_dig_align_debug: Any


PRIMITIVE_ROLLOUT_SUMMARY_ASSEMBLY_FIELDS: tuple[tuple[str, str], ...] = (
    ("transition_timeout_count", "_transition_timeout_count"),
    ("completed_transition_count", "_completed_transition_count"),
    ("dump_done_use_boundary_event", "dump_done_use_boundary_event"),
    ("primitive_final_skill", "_skill_name"),
    ("primitive_cycle_index", "_cycle_index"),
    ("cell_entry_enabled", "cell_entry_enabled"),
    ("cell_entry_trace", "_cell_entry_trace"),
    ("pre_dig_align_first_dig_only", "pre_dig_align_first_dig_only"),
    (
        "pre_dig_align_replan_after_failed_dig",
        "pre_dig_align_replan_after_failed_dig",
    ),
)


def build_primitive_rollout_summary_assembly_inputs_from_mapping(
    values: Mapping[str, Any],
    *,
    coverage_summary: Any,
    return_handoff_status: Any,
    dig_cut_status: Any,
    return_target_status: Any,
    dig_lifecycle_status: Any,
    bootstrap_status: Any,
    pre_dig_align_debug: Any,
) -> PrimitiveRolloutSummaryAssemblyInputs:
    return PrimitiveRolloutSummaryAssemblyInputs(
        transition_timeout_count=int(values["transition_timeout_count"]),
        completed_transition_count=int(values["completed_transition_count"]),
        dump_done_use_boundary_event=bool(values["dump_done_use_boundary_event"]),
        primitive_final_skill=str(values["primitive_final_skill"]),
        primitive_cycle_index=int(values["primitive_cycle_index"]),
        cell_entry_enabled=bool(values["cell_entry_enabled"]),
        cell_entry_trace_count=int(len(values["cell_entry_trace"])),
        pre_dig_align_first_dig_only=bool(
            values["pre_dig_align_first_dig_only"]
        ),
        pre_dig_align_replan_after_failed_dig=bool(
            values["pre_dig_align_replan_after_failed_dig"]
        ),
        coverage_summary=coverage_summary,
        return_handoff_status=return_handoff_status,
        dig_cut_status=dig_cut_status,
        return_target_status=return_target_status,
        dig_lifecycle_status=dig_lifecycle_status,
        bootstrap_status=bootstrap_status,
        pre_dig_align_debug=pre_dig_align_debug,
    )


@dataclass(frozen=True)
class PrimitivePlannerTraceAssemblyInputs:
    cell_entry_trace: tuple[Any, ...]
    dig_cut_planner_mode: str
    dig_cut_prior_id: str
    dig_cut_prior_path: str
    return_target_planner_enabled: bool
    coverage_trace: Any


PRIMITIVE_PLANNER_TRACE_ASSEMBLY_FIELDS: tuple[tuple[str, str], ...] = (
    ("cell_entry_trace", "_cell_entry_trace"),
    ("dig_cut_planner_mode", "dig_cut_planner_mode"),
    ("dig_cut_prior_id", "dig_cut_prior_id"),
    ("dig_cut_prior_path", "dig_cut_prior_path"),
    ("return_target_planner_enabled", "return_target_planner_enabled"),
)


def build_primitive_planner_trace_assembly_inputs_from_mapping(
    values: Mapping[str, Any],
    *,
    coverage_trace: Any,
) -> PrimitivePlannerTraceAssemblyInputs:
    return PrimitivePlannerTraceAssemblyInputs(
        cell_entry_trace=tuple(values["cell_entry_trace"]),
        dig_cut_planner_mode=str(values["dig_cut_planner_mode"]),
        dig_cut_prior_id=str(values["dig_cut_prior_id"]),
        dig_cut_prior_path=str(values["dig_cut_prior_path"]),
        return_target_planner_enabled=bool(
            values["return_target_planner_enabled"]
        ),
        coverage_trace=coverage_trace,
    )


def build_primitive_planner_trace_facts(
    inputs: PrimitivePlannerTraceAssemblyInputs,
) -> PrimitivePlannerTraceFacts:
    """Project service snapshots into the planner-trace facts contract."""
    coverage_trace = inputs.coverage_trace
    return PrimitivePlannerTraceFacts(
        cell_entry_trace=tuple(inputs.cell_entry_trace),
        dig_cut_planner_mode=str(inputs.dig_cut_planner_mode),
        dig_cut_prior_id=str(inputs.dig_cut_prior_id),
        dig_cut_prior_path=str(inputs.dig_cut_prior_path),
        return_target_planner_enabled=bool(inputs.return_target_planner_enabled),
        coverage_use_env_removed_depth=bool(coverage_trace.use_env_removed_depth),
        coverage_candidate_layout=str(coverage_trace.candidate_layout),
        coverage_first_dig_strategy=str(coverage_trace.first_dig_strategy),
        coverage_pass_index=int(coverage_trace.pass_index),
        coverage_multi_pass_enabled=bool(coverage_trace.multi_pass_enabled),
        coverage_multi_pass_max_passes=int(coverage_trace.multi_pass_max_passes),
        coverage_multi_pass_min_remaining_depth_m=float(
            coverage_trace.multi_pass_min_remaining_depth_m
        ),
        coverage_first_dig_preferred_corridor_id=(
            coverage_trace.first_dig_preferred_corridor_id
        ),
        coverage_corridors=tuple(coverage_trace.corridors),
        coverage_decision_trace=tuple(coverage_trace.decision_trace),
        coverage_terminal_stop_requested=bool(
            coverage_trace.terminal_stop_requested
        ),
        coverage_terminal_stop_reason=str(coverage_trace.terminal_stop_reason),
    )


def build_primitive_planner_trace_facts_from_mapping(
    values: Mapping[str, Any],
    *,
    coverage_trace: Any,
) -> PrimitivePlannerTraceFacts:
    """Project planner shell trace fields and snapshots into trace facts."""
    return build_primitive_planner_trace_facts(
        build_primitive_planner_trace_assembly_inputs_from_mapping(
            values,
            coverage_trace=coverage_trace,
        )
    )


def build_primitive_rollout_summary_facts(
    inputs: PrimitiveRolloutSummaryAssemblyInputs,
) -> PrimitiveRolloutSummaryFacts:
    """Project service snapshots into the rollout-summary facts contract."""
    coverage_summary = inputs.coverage_summary
    return_handoff_status = inputs.return_handoff_status
    dig_cut_status = inputs.dig_cut_status
    return_target_status = inputs.return_target_status
    dig_lifecycle_status = inputs.dig_lifecycle_status
    bootstrap_status = inputs.bootstrap_status
    pre_dig_align_debug = inputs.pre_dig_align_debug

    return PrimitiveRolloutSummaryFacts(
        transition_timeout_count=int(inputs.transition_timeout_count),
        completed_transition_count=int(inputs.completed_transition_count),
        dump_done_use_boundary_event=bool(inputs.dump_done_use_boundary_event),
        primitive_final_skill=str(inputs.primitive_final_skill),
        primitive_cycle_index=int(inputs.primitive_cycle_index),
        cell_entry_enabled=bool(inputs.cell_entry_enabled),
        cell_entry_trace_count=int(inputs.cell_entry_trace_count),
        return_target_token_source=str(return_target_status.target_token_source),
        return_to_dig_max_entry_error_m=return_handoff_status.max_entry_error_m,
        return_to_dig_entry_error_m=float(return_handoff_status.entry_error_m),
        return_to_dig_entry_close=bool(return_handoff_status.entry_close),
        return_next_dig_event_seen=bool(return_handoff_status.next_dig_event_seen),
        return_to_dig_start_envelope_gate_enabled=bool(
            return_handoff_status.start_envelope_gate_enabled
        ),
        return_to_dig_start_envelope_direct_handoff_enabled=bool(
            return_handoff_status.start_envelope_direct_handoff_enabled
        ),
        return_to_dig_start_envelope_ready=bool(
            return_handoff_status.start_envelope_ready
        ),
        return_to_dig_start_envelope_plane_depth_mode=str(
            return_handoff_status.start_envelope_plane_depth_mode
        ),
        return_to_dig_start_envelope_local_depth_tolerance_m=float(
            return_handoff_status.start_envelope_local_depth_tolerance_m
        ),
        return_to_dig_start_envelope_error=float(
            return_handoff_status.start_envelope_error
        ),
        pending_dig_cut_cycle_id=int(dig_cut_status.pending_cycle_id),
        pending_dig_cut_corridor_id=int(dig_cut_status.pending_corridor_id),
        dig_cut_token_injected=bool(dig_cut_status.token_injected),
        dig_cut_planner_mode=str(dig_cut_status.planner_mode),
        dig_cut_prior_id=str(dig_cut_status.prior_id),
        dig_cut_token_source=str(dig_cut_status.token_source),
        dig_cut_token_in_prior_p10_p90=bool(
            dig_cut_status.token_in_prior_p10_p90
        ),
        dig_cut_fallback_reason=str(dig_cut_status.fallback_reason),
        dig_failed_replan_next_skill=str(
            dig_lifecycle_status.failed_replan_next_skill
        ),
        coverage_selected_corridor_id=int(coverage_summary.selected_corridor_id),
        coverage_depleted_count=int(coverage_summary.depleted_count),
        coverage_completed_dump_count=int(coverage_summary.completed_dump_count),
        coverage_pass_index=int(coverage_summary.pass_index),
        coverage_multi_pass_enabled=bool(coverage_summary.multi_pass_enabled),
        coverage_use_env_removed_depth=bool(coverage_summary.use_env_removed_depth),
        coverage_candidate_layout=str(coverage_summary.candidate_layout),
        coverage_first_dig_strategy=str(coverage_summary.first_dig_strategy),
        coverage_first_dig_preferred_corridor_id=(
            coverage_summary.first_dig_preferred_corridor_id
        ),
        coverage_first_dig_max_entry_distance_m=(
            coverage_summary.first_dig_max_entry_distance_m
        ),
        coverage_first_dig_qpos_delta_weight=float(
            coverage_summary.first_dig_qpos_delta_weight
        ),
        coverage_terminal_stop_requested=bool(
            coverage_summary.terminal_stop_requested
        ),
        coverage_terminal_stop_reason=str(coverage_summary.terminal_stop_reason),
        scripted_bootstrap_timeout_count=int(bootstrap_status.timeout_count),
        pre_dig_align_enabled=bool(pre_dig_align_debug.enabled),
        pre_dig_align_first_dig_only=bool(inputs.pre_dig_align_first_dig_only),
        pre_dig_align_replan_after_failed_dig=bool(
            inputs.pre_dig_align_replan_after_failed_dig
        ),
        pre_dig_align_surface_guard_enabled=bool(
            pre_dig_align_debug.surface_guard_enabled
        ),
        pre_dig_align_surface_guard_count=int(
            pre_dig_align_debug.surface_guard_count
        ),
        pre_dig_align_timeout_count=int(pre_dig_align_debug.timeout_count),
        pre_dig_align_completed_count=int(pre_dig_align_debug.completed_count),
        pre_dig_align_replan_count=int(pre_dig_align_debug.replan_count),
        dig_bad_replan_count=int(dig_lifecycle_status.bad_replan_count),
        dig_exit_guard_replan_count=int(
            dig_lifecycle_status.exit_guard_replan_count
        ),
    )


def build_primitive_rollout_summary_facts_from_mapping(
    values: Mapping[str, Any],
    *,
    coverage_summary: Any,
    return_handoff_status: Any,
    dig_cut_status: Any,
    return_target_status: Any,
    dig_lifecycle_status: Any,
    bootstrap_status: Any,
    pre_dig_align_debug: Any,
) -> PrimitiveRolloutSummaryFacts:
    """Project planner shell summary fields and snapshots into summary facts."""
    return build_primitive_rollout_summary_facts(
        build_primitive_rollout_summary_assembly_inputs_from_mapping(
            values,
            coverage_summary=coverage_summary,
            return_handoff_status=return_handoff_status,
            dig_cut_status=dig_cut_status,
            return_target_status=return_target_status,
            dig_lifecycle_status=dig_lifecycle_status,
            bootstrap_status=bootstrap_status,
            pre_dig_align_debug=pre_dig_align_debug,
        )
    )


def build_primitive_debug_state_facts(
    inputs: PrimitiveDebugStateAssemblyInputs,
) -> PrimitiveDebugStateFacts:
    """Project service snapshots into the public debug-state facts contract."""
    coverage_debug = inputs.coverage_debug
    return_handoff_status = inputs.return_handoff_status
    dig_cut_status = inputs.dig_cut_status
    dig_depth_profile_status = inputs.dig_depth_profile_status
    return_target_status = inputs.return_target_status
    dig_lifecycle_status = inputs.dig_lifecycle_status
    bootstrap_status = inputs.bootstrap_status
    cell_entry_debug = inputs.cell_entry_debug
    pre_dig_align_debug = inputs.pre_dig_align_debug

    return PrimitiveDebugStateFacts(
        debug_state=inputs.debug_state,
        primitive_goal_curr_sector_id=int(inputs.primitive_goal_curr_sector_id),
        primitive_goal_next_sector_id=int(inputs.primitive_goal_next_sector_id),
        cell_entry_enabled=bool(inputs.cell_entry_enabled),
        cell_entry_token_injected=bool(inputs.cell_entry_token_injected),
        dig_cut_token_injected=bool(dig_cut_status.token_injected),
        dig_depth_profile_token_injected=bool(
            dig_depth_profile_status.token_injected
        ),
        dig_depth_profile_source=str(dig_depth_profile_status.source),
        dig_depth_profile_required=bool(dig_depth_profile_status.required),
        dig_depth_profile_token_source=str(dig_depth_profile_status.token_source),
        dig_depth_profile_fallback_reason=str(
            dig_depth_profile_status.fallback_reason
        ),
        dig_failed_replan_next_skill=str(
            dig_lifecycle_status.failed_replan_next_skill
        ),
        return_target_token_injected=bool(
            return_target_status.target_token_injected
        ),
        return_target_token_source=str(return_target_status.target_token_source),
        return_target_tokens=return_target_status.target_tokens.copy(),
        return_target_fallback_reason=str(
            return_target_status.target_fallback_reason
        ),
        return_relocate_token_injected=bool(
            return_target_status.relocate_token_injected
        ),
        return_relocate_tokens=return_target_status.relocate_tokens.copy(),
        return_start_envelope_token_injected=bool(
            return_target_status.start_envelope_token_injected
        ),
        return_start_envelope_token_source=str(
            return_target_status.start_envelope_token_source
        ),
        return_start_envelope_tokens=(
            return_target_status.start_envelope_tokens.copy()
        ),
        return_to_dig_entry_error_m=float(return_handoff_status.entry_error_m),
        return_to_dig_entry_close=bool(return_handoff_status.entry_close),
        return_next_dig_event_seen=bool(
            return_handoff_status.next_dig_event_seen
        ),
        return_to_dig_start_envelope_ready=bool(
            return_handoff_status.start_envelope_ready
        ),
        return_to_dig_start_envelope_gate_enabled=bool(
            return_handoff_status.start_envelope_gate_enabled
        ),
        return_to_dig_start_envelope_direct_handoff_enabled=bool(
            return_handoff_status.start_envelope_direct_handoff_enabled
        ),
        return_to_dig_start_envelope_plane_depth_mode=str(
            return_handoff_status.start_envelope_plane_depth_mode
        ),
        return_to_dig_start_envelope_local_depth_tolerance_m=float(
            return_handoff_status.start_envelope_local_depth_tolerance_m
        ),
        return_to_dig_start_envelope_error=float(
            return_handoff_status.start_envelope_error
        ),
        return_to_dig_start_envelope_checks=dict(
            return_handoff_status.start_envelope_checks
        ),
        pending_dig_cut_cycle_id=int(dig_cut_status.pending_cycle_id),
        pending_dig_cut_corridor_id=int(dig_cut_status.pending_corridor_id),
        dig_cut_planner_mode=str(dig_cut_status.planner_mode),
        dig_cut_prior_id=str(dig_cut_status.prior_id),
        dig_cut_token_source=str(dig_cut_status.token_source),
        dig_cut_tokens=dig_cut_status.tokens.copy(),
        dig_depth_profile_tokens=dig_depth_profile_status.tokens.copy(),
        dig_cut_token_in_prior_p10_p90=bool(
            dig_cut_status.token_in_prior_p10_p90
        ),
        dig_cut_fallback_reason=str(dig_cut_status.fallback_reason),
        coverage_active_corridor_id=int(coverage_debug.active_corridor_id),
        coverage_last_selected_corridor_id=int(
            coverage_debug.last_selected_corridor_id
        ),
        coverage_last_selected_cell_id=int(coverage_debug.last_selected_cell_id),
        coverage_last_selected_row_id=int(coverage_debug.last_selected_row_id),
        coverage_active_values=dict(coverage_debug.active_values),
        coverage_active_cell_id=int(coverage_debug.active_cell_id),
        coverage_active_corridor_score=float(
            coverage_debug.active_corridor_score
        ),
        coverage_state_exemplar_enabled=bool(
            coverage_debug.state_exemplar_enabled
        ),
        coverage_active_state_exemplar_ids=tuple(
            coverage_debug.active_state_exemplar_ids
        ),
        coverage_active_state_exemplar_distance=float(
            coverage_debug.active_state_exemplar_distance
        ),
        coverage_depleted_count=int(coverage_debug.depleted_count),
        coverage_pass_index=int(coverage_debug.pass_index),
        coverage_multi_pass_enabled=bool(coverage_debug.multi_pass_enabled),
        coverage_multi_pass_max_passes=int(coverage_debug.multi_pass_max_passes),
        coverage_multi_pass_min_remaining_depth_m=float(
            coverage_debug.multi_pass_min_remaining_depth_m
        ),
        coverage_last_payload_gain_kg=float(coverage_debug.last_payload_gain_kg),
        coverage_last_effective_deposit_delta_kg=float(
            coverage_debug.last_effective_deposit_delta_kg
        ),
        coverage_global_low_productivity_streak=int(
            coverage_debug.global_low_productivity_streak
        ),
        coverage_use_env_removed_depth=bool(coverage_debug.use_env_removed_depth),
        coverage_candidate_layout=str(coverage_debug.candidate_layout),
        coverage_first_dig_strategy=str(coverage_debug.first_dig_strategy),
        coverage_first_dig_preferred_corridor_id=(
            None
            if coverage_debug.first_dig_preferred_corridor_id is None
            else int(coverage_debug.first_dig_preferred_corridor_id)
        ),
        coverage_first_dig_max_entry_distance_m=(
            None
            if coverage_debug.first_dig_max_entry_distance_m is None
            else float(coverage_debug.first_dig_max_entry_distance_m)
        ),
        coverage_first_dig_qpos_delta_weight=float(
            coverage_debug.first_dig_qpos_delta_weight
        ),
        coverage_first_dig_max_qpos_delta=(
            None
            if coverage_debug.first_dig_max_qpos_delta is None
            else coverage_debug.first_dig_max_qpos_delta.copy()
        ),
        coverage_terminal_stop_requested=bool(
            coverage_debug.terminal_stop_requested
        ),
        coverage_terminal_stop_reason=str(coverage_debug.terminal_stop_reason),
        coverage_corridors=tuple(coverage_debug.corridors),
        coverage_candidate_scores=tuple(coverage_debug.candidate_scores),
        cell_entry_selected_cell_id=int(cell_entry_debug.selected_cell_id),
        cell_entry_selected_long_index=int(cell_entry_debug.selected_long_index),
        cell_entry_selected_short_index=int(cell_entry_debug.selected_short_index),
        cell_entry_planned_entry_x_m=float(cell_entry_debug.planned_entry_x_m),
        cell_entry_planned_entry_y_m=float(cell_entry_debug.planned_entry_y_m),
        cell_entry_planned_entry_z_m=float(cell_entry_debug.planned_entry_z_m),
        cell_entry_planner_ok=bool(cell_entry_debug.planner_ok),
        cell_entry_audit_reason_code=int(cell_entry_debug.audit_reason_code),
        cell_entry_audit_reason=str(cell_entry_debug.audit_reason),
        cell_entry_audit_risk_flags=int(cell_entry_debug.audit_risk_flags),
        cell_entry_inside_entry_envelope=bool(
            cell_entry_debug.inside_entry_envelope
        ),
        cell_entry_distance_to_entry_envelope_m=float(
            cell_entry_debug.distance_to_entry_envelope_m
        ),
        cell_entry_seen_cell_id=int(cell_entry_debug.seen_cell_id),
        scripted_bootstrap_step_count=int(bootstrap_status.step_count),
        scripted_bootstrap_hold_count=int(bootstrap_status.hold_count),
        scripted_bootstrap_timeout_count=int(bootstrap_status.timeout_count),
        dig_step_count=int(dig_lifecycle_status.step_count),
        dig_best_mass_kg=float(dig_lifecycle_status.best_mass_kg),
        dig_mass_plateau_count=int(dig_lifecycle_status.mass_plateau_count),
        dig_to_carry_reason=str(dig_lifecycle_status.dig_to_carry_reason),
        dig_bad_replan_count=int(dig_lifecycle_status.bad_replan_count),
        dig_exit_guard_replan_count=int(
            dig_lifecycle_status.exit_guard_replan_count
        ),
        pre_dig_align_enabled=bool(pre_dig_align_debug.enabled),
        pre_dig_align_first_dig_only=bool(inputs.pre_dig_align_first_dig_only),
        pre_dig_align_replan_after_failed_dig=bool(
            inputs.pre_dig_align_replan_after_failed_dig
        ),
        pre_dig_align_entry_intent_controlled_dims=(
            pre_dig_align_debug.entry_intent_controlled_dims
        ),
        pre_dig_align_surface_guard_enabled=bool(
            pre_dig_align_debug.surface_guard_enabled
        ),
        pre_dig_align_surface_depth_m=float(pre_dig_align_debug.surface_depth_m),
        pre_dig_align_surface_guard_triggered=bool(
            pre_dig_align_debug.surface_guard_triggered
        ),
        pre_dig_align_surface_guard_count=int(
            pre_dig_align_debug.surface_guard_count
        ),
        pre_dig_align_active_for_next_dig=bool(
            inputs.pre_dig_align_active_for_next_dig
        ),
        pre_dig_align_step_count=int(pre_dig_align_debug.step_count),
        pre_dig_align_hold_count=int(pre_dig_align_debug.hold_count),
        pre_dig_align_timeout_count=int(pre_dig_align_debug.timeout_count),
        pre_dig_align_completed_count=int(pre_dig_align_debug.completed_count),
        pre_dig_align_replan_count=int(pre_dig_align_debug.replan_count),
        pre_dig_align_target_qpos=pre_dig_align_debug.target_qpos,
        pre_dig_align_error=pre_dig_align_debug.error,
        pre_dig_align_entry_error_m=float(pre_dig_align_debug.entry_error_m),
        pre_dig_align_start_envelope_ready=bool(
            pre_dig_align_debug.start_envelope_ready
        ),
        pre_dig_align_first_dig_entry_close_handoff=bool(
            pre_dig_align_debug.first_dig_entry_close_handoff
        ),
        pre_dig_align_entry_close_handoff_ready=bool(
            pre_dig_align_debug.entry_close_handoff_ready
        ),
        pre_dig_align_entry_intent_handoff_enabled=bool(
            pre_dig_align_debug.entry_intent_handoff_enabled
        ),
        pre_dig_align_entry_intent_handoff_ready=bool(
            pre_dig_align_debug.entry_intent_handoff_ready
        ),
        pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max=(
            pre_dig_align_debug.first_dig_entry_close_handoff_qvel_abs_max
        ),
        pre_dig_align_controlled_dims=pre_dig_align_debug.controlled_dims,
        pre_dig_align_bucket_target_qpos=pre_dig_align_debug.bucket_target_qpos,
    )


def build_primitive_debug_state_facts_from_mapping(
    values: Mapping[str, Any],
    *,
    primitive_goal_curr_sector_id: Any,
    primitive_goal_next_sector_id: Any,
    pre_dig_align_active_for_next_dig: Any,
    coverage_debug: Any,
    return_handoff_status: Any,
    dig_cut_status: Any,
    dig_depth_profile_status: Any,
    return_target_status: Any,
    dig_lifecycle_status: Any,
    bootstrap_status: Any,
    cell_entry_debug: Any,
    pre_dig_align_debug: Any,
) -> PrimitiveDebugStateFacts:
    """Project planner shell debug fields and snapshots into debug facts."""
    return build_primitive_debug_state_facts(
        build_primitive_debug_state_assembly_inputs_from_mapping(
            values,
            primitive_goal_curr_sector_id=primitive_goal_curr_sector_id,
            primitive_goal_next_sector_id=primitive_goal_next_sector_id,
            pre_dig_align_active_for_next_dig=(
                pre_dig_align_active_for_next_dig
            ),
            coverage_debug=coverage_debug,
            return_handoff_status=return_handoff_status,
            dig_cut_status=dig_cut_status,
            dig_depth_profile_status=dig_depth_profile_status,
            return_target_status=return_target_status,
            dig_lifecycle_status=dig_lifecycle_status,
            bootstrap_status=bootstrap_status,
            cell_entry_debug=cell_entry_debug,
            pre_dig_align_debug=pre_dig_align_debug,
        )
    )
