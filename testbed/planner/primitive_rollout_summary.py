"""Public rollout-summary report assembly for the primitive planner."""

from __future__ import annotations

from dataclasses import dataclass

from testbed.planner.primitive_coverage_reports import CoverageSummaryReportStatus


PrimitiveRolloutSummaryValue = float | int | str | list[str]


@dataclass(frozen=True)
class PrimitiveRolloutSummaryInputs:
    """Snapshot values required to assemble the public rollout summary."""

    transition_source: str
    transition_policy_mode: str
    transition_fallback_count: int
    transition_fallback_reason: str
    transition_timeout_count: int
    completed_transition_count: int
    dump_done_use_boundary_event: bool
    primitive_final_skill: str
    primitive_cycle_index: int
    cell_entry_enabled: bool
    cell_entry_trace_count: int
    dig_cut_token_dim: int
    return_target_token_dim: int
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
    coverage: CoverageSummaryReportStatus
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
class PrimitiveRolloutSummaryBuilder:
    """Build the public primitive planner rollout-summary payload."""

    def build(
        self, inputs: PrimitiveRolloutSummaryInputs
    ) -> dict[str, PrimitiveRolloutSummaryValue]:
        return {
            "transition_source": str(inputs.transition_source),
            "transition_policy_mode": str(inputs.transition_policy_mode),
            "transition_fallback_count": int(inputs.transition_fallback_count),
            "transition_fallback_reason": str(inputs.transition_fallback_reason),
            "transition_timeout_count": int(inputs.transition_timeout_count),
            "completed_transition_count": int(inputs.completed_transition_count),
            "dump_done_use_boundary_event": int(
                inputs.dump_done_use_boundary_event
            ),
            "primitive_final_skill": str(inputs.primitive_final_skill),
            "primitive_cycle_index": int(inputs.primitive_cycle_index),
            "cell_entry_enabled": int(inputs.cell_entry_enabled),
            "cell_entry_trace_count": int(inputs.cell_entry_trace_count),
            "dig_cut_token_dim": int(inputs.dig_cut_token_dim),
            "return_target_token_dim": int(inputs.return_target_token_dim),
            "return_target_token_source": str(inputs.return_target_token_source),
            "return_to_dig_max_entry_error_m": _float_or_nan(
                inputs.return_to_dig_max_entry_error_m
            ),
            "return_to_dig_entry_error_m": float(
                inputs.return_to_dig_entry_error_m
            ),
            "return_to_dig_entry_close": int(inputs.return_to_dig_entry_close),
            "return_next_dig_event_seen": int(inputs.return_next_dig_event_seen),
            "return_to_dig_start_envelope_gate_enabled": int(
                inputs.return_to_dig_start_envelope_gate_enabled
            ),
            "return_to_dig_start_envelope_direct_handoff_enabled": int(
                inputs.return_to_dig_start_envelope_direct_handoff_enabled
            ),
            "return_to_dig_start_envelope_ready": int(
                inputs.return_to_dig_start_envelope_ready
            ),
            "return_to_dig_start_envelope_plane_depth_mode": str(
                inputs.return_to_dig_start_envelope_plane_depth_mode
            ),
            "return_to_dig_start_envelope_local_depth_tolerance_m": float(
                inputs.return_to_dig_start_envelope_local_depth_tolerance_m
            ),
            "return_to_dig_start_envelope_error": float(
                inputs.return_to_dig_start_envelope_error
            ),
            "pending_dig_cut_cycle_id": int(inputs.pending_dig_cut_cycle_id),
            "pending_dig_cut_corridor_id": int(inputs.pending_dig_cut_corridor_id),
            "dig_cut_token_injected": int(inputs.dig_cut_token_injected),
            "dig_cut_planner_mode": str(inputs.dig_cut_planner_mode),
            "dig_cut_prior_id": str(inputs.dig_cut_prior_id),
            "dig_cut_token_source": str(inputs.dig_cut_token_source),
            "dig_cut_token_in_prior_p10_p90": int(
                inputs.dig_cut_token_in_prior_p10_p90
            ),
            "dig_cut_fallback_reason": str(inputs.dig_cut_fallback_reason),
            "dig_failed_replan_next_skill": str(
                inputs.dig_failed_replan_next_skill
            ),
            "coverage_selected_corridor_id": int(
                inputs.coverage.selected_corridor_id
            ),
            "coverage_depleted_count": int(inputs.coverage.depleted_count),
            "coverage_completed_dump_count": int(
                inputs.coverage.completed_dump_count
            ),
            "coverage_pass_index": int(inputs.coverage.pass_index),
            "coverage_multi_pass_enabled": int(
                inputs.coverage.multi_pass_enabled
            ),
            "coverage_use_env_removed_depth": int(
                inputs.coverage.use_env_removed_depth
            ),
            "coverage_candidate_layout": str(inputs.coverage.candidate_layout),
            "coverage_first_dig_strategy": str(
                inputs.coverage.first_dig_strategy
            ),
            "coverage_first_dig_preferred_corridor_id": int(
                -1
                if inputs.coverage.first_dig_preferred_corridor_id is None
                else inputs.coverage.first_dig_preferred_corridor_id
            ),
            "coverage_first_dig_max_entry_distance_m": _float_or_nan(
                inputs.coverage.first_dig_max_entry_distance_m
            ),
            "coverage_first_dig_qpos_delta_weight": float(
                inputs.coverage.first_dig_qpos_delta_weight
            ),
            "coverage_terminal_stop_requested": int(
                inputs.coverage.terminal_stop_requested
            ),
            "coverage_terminal_stop_reason": str(
                inputs.coverage.terminal_stop_reason
            ),
            "scripted_bootstrap_timeout_count": int(
                inputs.scripted_bootstrap_timeout_count
            ),
            "pre_dig_align_enabled": int(inputs.pre_dig_align_enabled),
            "pre_dig_align_first_dig_only": int(
                inputs.pre_dig_align_first_dig_only
            ),
            "pre_dig_align_replan_after_failed_dig": int(
                inputs.pre_dig_align_replan_after_failed_dig
            ),
            "pre_dig_align_surface_guard_enabled": int(
                inputs.pre_dig_align_surface_guard_enabled
            ),
            "pre_dig_align_surface_guard_count": int(
                inputs.pre_dig_align_surface_guard_count
            ),
            "pre_dig_align_timeout_count": int(
                inputs.pre_dig_align_timeout_count
            ),
            "pre_dig_align_completed_count": int(
                inputs.pre_dig_align_completed_count
            ),
            "pre_dig_align_replan_count": int(inputs.pre_dig_align_replan_count),
            "dig_bad_replan_count": int(inputs.dig_bad_replan_count),
            "dig_exit_guard_replan_count": int(
                inputs.dig_exit_guard_replan_count
            ),
        }


def _float_or_nan(value: float | None) -> float:
    return float("nan") if value is None else float(value)


__all__ = [
    "PrimitiveRolloutSummaryBuilder",
    "PrimitiveRolloutSummaryInputs",
    "PrimitiveRolloutSummaryValue",
]
