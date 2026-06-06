from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

from testbed.contracts.primitive_tokens import (
    DIG_CUT_TOKEN_DIM,
    DIG_DEPTH_PROFILE_TOKEN_DIM,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_TARGET_TOKEN_DIM,
)
from testbed.eval.rollout_logs import to_jsonable
from testbed.eval.rollout_step_records import (
    build_planner_debug_json,
    build_rollout_step_record,
)
from testbed.planner.bootstrap import BootstrapRuntimeStatusSnapshot
from testbed.planner.cell_entry import (
    AUDIT_REASON_TO_ID,
    CELL_ENTRY_TOKEN_DIM,
    CellEntryPlanner,
    CellGridSpec,
    PlannerDecisionAuditor,
    PrimitiveCycleOutcome,
)
from testbed.planner.dig_cut_plan import DigCutRuntimeStatusSnapshot
from testbed.planner.dig_depth_profile import DigDepthProfileRuntimeStatusSnapshot
from testbed.planner.dig_lifecycle import DigLifecycleRuntimeStatusSnapshot
from testbed.planner.dig_start_alignment import DigStartAlignmentDebugSnapshot
from testbed.planner.primitive_debug import (
    PrimitiveDebugStateFacts,
    PrimitivePlannerTraceFacts,
    PrimitiveRolloutSummaryFacts,
    build_primitive_debug_state,
    build_primitive_debug_state_from_facts,
    build_primitive_planner_trace,
    build_primitive_planner_trace_from_facts,
    build_primitive_rollout_summary,
    build_primitive_rollout_summary_from_facts,
)
from testbed.planner.primitive_debug_facts import (
    PRIMITIVE_DEBUG_STATE_ASSEMBLY_FIELDS,
    PRIMITIVE_PLANNER_TRACE_ASSEMBLY_FIELDS,
    PRIMITIVE_ROLLOUT_SUMMARY_ASSEMBLY_FIELDS,
    build_primitive_debug_state_assembly_inputs_from_mapping,
    build_primitive_debug_state_facts,
    build_primitive_debug_state_facts_from_mapping,
    build_primitive_planner_trace_assembly_inputs_from_mapping,
    build_primitive_planner_trace_facts,
    build_primitive_planner_trace_facts_from_mapping,
    build_primitive_rollout_summary_assembly_inputs_from_mapping,
    build_primitive_rollout_summary_facts,
    build_primitive_rollout_summary_facts_from_mapping,
)
from testbed.planner.primitive_debug_facts import (
    PrimitiveDebugStateFacts as SourcePrimitiveDebugStateFacts,
)
from testbed.planner.primitive_debug_facts import (
    PrimitivePlannerTraceFacts as SourcePrimitivePlannerTraceFacts,
)
from testbed.planner.primitive_debug_facts import (
    PrimitiveRolloutSummaryFacts as SourcePrimitiveRolloutSummaryFacts,
)
from testbed.planner.return_handoff import ReturnToDigHandoffStatusSnapshot
from testbed.planner.return_target_plan import ReturnTargetConditioningStatusSnapshot
from testbed.policies.hybrid.primitive_planner import (
    TRANSITION_POLICY_MODE_PRIMITIVE,
    TRANSITION_SOURCE_PRIMITIVE_RETURN_POLICY,
    PrimitivePlannerACTPolicy,
)

EXPECTED_DEBUG_STATE_KEYS = (
    "skill_name",
    "skill_id",
    "skill_switch_reason",
    "primitive_checkpoint_path",
    "hybrid_mode",
    "transition_timeout",
    "transition_completed",
    "transition_source",
    "transition_policy_mode",
    "transition_fallback_count",
    "transition_fallback_reason",
    "completed_transition_count",
    "transition_timeout_count",
    "dump_ready_hold_count",
    "dump_done_hold_count",
    "approach_ready_hold_count",
    "dump_release_ready_hold_count",
    "primitive_cycle_index",
    "primitive_goal_curr_sector_id",
    "primitive_goal_next_sector_id",
    "cell_entry_enabled",
    "cell_entry_token_injected",
    "cell_entry_token_dim",
    "dig_cut_token_injected",
    "dig_cut_token_dim",
    "dig_depth_profile_token_injected",
    "dig_depth_profile_token_dim",
    "dig_depth_profile_source",
    "dig_depth_profile_required",
    "dig_depth_profile_token_source",
    "dig_depth_profile_fallback_reason",
    "dig_failed_replan_next_skill",
    "return_target_token_injected",
    "return_target_token_dim",
    "return_target_token_source",
    "return_target_tokens",
    "return_target_fallback_reason",
    "return_relocate_token_injected",
    "return_relocate_token_dim",
    "return_relocate_token_source",
    "return_relocate_tokens",
    "return_start_envelope_token_injected",
    "return_start_envelope_token_dim",
    "return_start_envelope_token_source",
    "return_start_envelope_tokens",
    "return_to_dig_entry_error_m",
    "return_to_dig_entry_close",
    "return_next_dig_event_seen",
    "return_to_dig_start_envelope_gate_enabled",
    "return_to_dig_start_envelope_direct_handoff_enabled",
    "return_to_dig_start_envelope_ready",
    "return_to_dig_start_envelope_plane_depth_mode",
    "return_to_dig_start_envelope_local_depth_tolerance_m",
    "return_to_dig_start_envelope_error",
    "return_to_dig_start_envelope_checks",
    "pending_dig_cut_cycle_id",
    "pending_dig_cut_corridor_id",
    "dig_cut_planner_mode",
    "dig_cut_prior_id",
    "dig_cut_token_source",
    "dig_cut_tokens",
    "dig_depth_profile_tokens",
    "token_in_prior_p10_p90",
    "dig_cut_token_in_prior_p10_p90",
    "fallback_reason",
    "dig_cut_fallback_reason",
    "coverage_corridor_id",
    "coverage_selected_corridor_id",
    "coverage_last_selected_corridor_id",
    "coverage_last_selected_cell_id",
    "coverage_last_selected_row_id",
    "coverage_entry_x_m",
    "coverage_entry_z_m",
    "coverage_exit_x_m",
    "coverage_exit_z_m",
    "coverage_entry_x_p05_m",
    "coverage_entry_x_p50_m",
    "coverage_entry_x_p95_m",
    "coverage_entry_z_p05_m",
    "coverage_entry_z_p50_m",
    "coverage_entry_z_p95_m",
    "coverage_entry_radial_p75_m",
    "coverage_entry_radial_p95_m",
    "coverage_exit_x_p05_m",
    "coverage_exit_x_p50_m",
    "coverage_exit_x_p95_m",
    "coverage_exit_z_p05_m",
    "coverage_exit_z_p50_m",
    "coverage_exit_z_p95_m",
    "coverage_exit_radial_p75_m",
    "coverage_exit_radial_p95_m",
    "coverage_cut_depth_peak_p05_m",
    "coverage_cut_depth_peak_p50_m",
    "coverage_cut_depth_peak_p95_m",
    "coverage_cell_id",
    "coverage_corridor_score",
    "coverage_state_exemplar_enabled",
    "coverage_state_exemplar_ids",
    "coverage_state_exemplar_distance",
    "coverage_depleted_count",
    "coverage_pass_index",
    "coverage_multi_pass_enabled",
    "coverage_multi_pass_max_passes",
    "coverage_multi_pass_min_remaining_depth_m",
    "coverage_last_payload_gain_kg",
    "coverage_last_effective_deposit_delta_kg",
    "coverage_global_low_productivity_streak",
    "coverage_use_env_removed_depth",
    "coverage_candidate_layout",
    "coverage_first_dig_strategy",
    "coverage_first_dig_preferred_corridor_id",
    "coverage_first_dig_max_entry_distance_m",
    "coverage_first_dig_qpos_delta_weight",
    "coverage_first_dig_max_qpos_delta",
    "coverage_terminal_stop_requested",
    "coverage_terminal_stop_reason",
    "coverage_corridors",
    "planner_terminal_stop_requested",
    "planner_terminal_stop_reason",
    "coverage_candidate_scores",
    "cell_entry_selected_cell_id",
    "cell_entry_selected_long_index",
    "cell_entry_selected_short_index",
    "cell_entry_planned_entry_x_m",
    "cell_entry_planned_entry_y_m",
    "cell_entry_planned_entry_z_m",
    "cell_entry_planner_ok",
    "cell_entry_audit_reason_code",
    "cell_entry_audit_reason",
    "cell_entry_audit_risk_flags",
    "cell_entry_inside_entry_envelope",
    "cell_entry_distance_to_entry_envelope_m",
    "cell_entry_seen_cell_id",
    "scripted_bootstrap_step_count",
    "scripted_bootstrap_hold_count",
    "scripted_bootstrap_timeout_count",
    "dig_step_count",
    "dig_best_mass_kg",
    "dig_mass_plateau_count",
    "dig_to_carry_reason",
    "dig_bad_replan_count",
    "dig_exit_guard_replan_count",
    "pre_dig_align_enabled",
    "pre_dig_align_first_dig_only",
    "pre_dig_align_replan_after_failed_dig",
    "pre_dig_align_entry_intent_controlled_dims",
    "pre_dig_align_surface_guard_enabled",
    "pre_dig_align_surface_depth_m",
    "pre_dig_align_surface_guard_triggered",
    "pre_dig_align_surface_guard_count",
    "pre_dig_align_active_for_next_dig",
    "pre_dig_align_step_count",
    "pre_dig_align_hold_count",
    "pre_dig_align_timeout_count",
    "pre_dig_align_completed_count",
    "pre_dig_align_replan_count",
    "pre_dig_align_target_qpos",
    "pre_dig_align_error",
    "pre_dig_align_entry_error_m",
    "pre_dig_align_start_envelope_ready",
    "pre_dig_align_first_dig_entry_close_handoff",
    "pre_dig_align_entry_close_handoff_ready",
    "pre_dig_align_entry_intent_handoff_enabled",
    "pre_dig_align_entry_intent_handoff_ready",
    "pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max",
    "pre_dig_align_controlled_dims",
    "pre_dig_align_bucket_target_qpos",
)

EXPECTED_ROLLOUT_SUMMARY_KEYS = (
    "transition_source",
    "transition_policy_mode",
    "transition_fallback_count",
    "transition_fallback_reason",
    "transition_timeout_count",
    "completed_transition_count",
    "dump_done_use_boundary_event",
    "primitive_final_skill",
    "primitive_cycle_index",
    "cell_entry_enabled",
    "cell_entry_trace_count",
    "dig_cut_token_dim",
    "return_target_token_dim",
    "return_target_token_source",
    "return_to_dig_max_entry_error_m",
    "return_to_dig_entry_error_m",
    "return_to_dig_entry_close",
    "return_next_dig_event_seen",
    "return_to_dig_start_envelope_gate_enabled",
    "return_to_dig_start_envelope_direct_handoff_enabled",
    "return_to_dig_start_envelope_ready",
    "return_to_dig_start_envelope_plane_depth_mode",
    "return_to_dig_start_envelope_local_depth_tolerance_m",
    "return_to_dig_start_envelope_error",
    "pending_dig_cut_cycle_id",
    "pending_dig_cut_corridor_id",
    "dig_cut_token_injected",
    "dig_cut_planner_mode",
    "dig_cut_prior_id",
    "dig_cut_token_source",
    "dig_cut_token_in_prior_p10_p90",
    "dig_cut_fallback_reason",
    "dig_failed_replan_next_skill",
    "coverage_selected_corridor_id",
    "coverage_depleted_count",
    "coverage_completed_dump_count",
    "coverage_pass_index",
    "coverage_multi_pass_enabled",
    "coverage_use_env_removed_depth",
    "coverage_candidate_layout",
    "coverage_first_dig_strategy",
    "coverage_first_dig_preferred_corridor_id",
    "coverage_first_dig_max_entry_distance_m",
    "coverage_first_dig_qpos_delta_weight",
    "coverage_terminal_stop_requested",
    "coverage_terminal_stop_reason",
    "scripted_bootstrap_timeout_count",
    "pre_dig_align_enabled",
    "pre_dig_align_first_dig_only",
    "pre_dig_align_replan_after_failed_dig",
    "pre_dig_align_surface_guard_enabled",
    "pre_dig_align_surface_guard_count",
    "pre_dig_align_timeout_count",
    "pre_dig_align_completed_count",
    "pre_dig_align_replan_count",
    "dig_bad_replan_count",
    "dig_exit_guard_replan_count",
)

EXPECTED_PLANNER_TRACE_KEYS = (
    "cell_entry_trace",
    "dig_cut_token_contract_version",
    "dig_cut_token_contract",
    "dig_cut_planner_mode",
    "dig_cut_prior_id",
    "dig_cut_prior_path",
    "return_target_token_contract_version",
    "return_target_token_contract",
    "return_start_envelope_token_contract_version",
    "return_start_envelope_token_contract",
    "return_target_planner_enabled",
    "coverage_use_env_removed_depth",
    "coverage_candidate_layout",
    "coverage_first_dig_strategy",
    "coverage_pass_index",
    "coverage_multi_pass_enabled",
    "coverage_multi_pass_max_passes",
    "coverage_multi_pass_min_remaining_depth_m",
    "coverage_first_dig_preferred_corridor_id",
    "coverage_corridors",
    "coverage_decision_trace",
    "coverage_decision_trace_count",
    "coverage_terminal_stop_requested",
    "coverage_terminal_stop_reason",
)

EXPECTED_COVERAGE_CORRIDOR_DEBUG_KEYS = (
    "corridor_id",
    "entry_x_m",
    "entry_z_m",
    "exit_x_m",
    "exit_z_m",
    "entry_x_p05_m",
    "entry_x_p50_m",
    "entry_x_p95_m",
    "entry_z_p05_m",
    "entry_z_p50_m",
    "entry_z_p95_m",
    "entry_radial_p75_m",
    "entry_radial_p95_m",
    "exit_x_p05_m",
    "exit_x_p50_m",
    "exit_x_p95_m",
    "exit_z_p05_m",
    "exit_z_p50_m",
    "exit_z_p95_m",
    "exit_radial_p75_m",
    "exit_radial_p95_m",
    "cut_depth_peak_p05_m",
    "cut_depth_peak_p50_m",
    "cut_depth_peak_p95_m",
    "cell_id",
    "source_count",
    "source_fraction",
    "attempt_limit",
    "cell_confidence",
    "score",
    "attempts",
    "low_productivity_streak",
    "depleted",
    "belief_coverage",
    "last_payload_gain_kg",
    "last_effective_deposit_delta_kg",
    "last_remaining_depth_m",
    "last_reason",
    "state_exemplar_id",
    "state_exemplar_distance",
)


def test_primitive_debug_facts_contract_symbols_remain_compatible_facades() -> None:
    assert PrimitiveDebugStateFacts is SourcePrimitiveDebugStateFacts
    assert PrimitivePlannerTraceFacts is SourcePrimitivePlannerTraceFacts
    assert PrimitiveRolloutSummaryFacts is SourcePrimitiveRolloutSummaryFacts


def test_debug_state_default_schema_is_stable() -> None:
    policy = _make_policy()

    state = policy.debug_state()

    _assert_nested_equal(
        state,
        build_primitive_debug_state_from_facts(policy._debug_state_facts()),
    )
    _assert_nested_equal(state, build_primitive_debug_state(policy))
    assert tuple(state) == EXPECTED_DEBUG_STATE_KEYS
    assert len(state) == 167
    assert state["skill_name"] == "dig"
    assert state["skill_id"] == 0
    assert state["skill_switch_reason"] == "reset"
    assert state["primitive_checkpoint_path"] == ""
    assert state["hybrid_mode"] == "WORK"
    assert state["transition_source"] == TRANSITION_SOURCE_PRIMITIVE_RETURN_POLICY
    assert state["transition_policy_mode"] == TRANSITION_POLICY_MODE_PRIMITIVE
    assert state["transition_timeout"] is False
    assert state["transition_completed"] is False
    assert state["completed_transition_count"] == 0
    assert state["primitive_cycle_index"] == 0

    assert state["cell_entry_enabled"] is False
    assert state["cell_entry_token_dim"] == CELL_ENTRY_TOKEN_DIM
    assert state["cell_entry_selected_cell_id"] == -1
    assert state["cell_entry_planner_ok"] is False

    assert state["dig_cut_token_injected"] is False
    assert state["dig_cut_token_dim"] == DIG_CUT_TOKEN_DIM
    assert state["dig_depth_profile_token_dim"] == DIG_DEPTH_PROFILE_TOKEN_DIM
    assert state["dig_depth_profile_source"] == "live_plan"
    assert state["dig_depth_profile_required"] is False
    assert state["dig_depth_profile_token_source"] == "none"
    assert state["dig_cut_planner_mode"] == "conservative_pose"
    assert state["dig_cut_token_source"] == "none"
    assert state["dig_cut_tokens"] == [0.0] * DIG_CUT_TOKEN_DIM
    assert len(state["dig_depth_profile_tokens"]) == DIG_DEPTH_PROFILE_TOKEN_DIM

    assert state["return_target_token_dim"] == RETURN_TARGET_TOKEN_DIM
    assert state["return_relocate_token_dim"] == RETURN_TARGET_TOKEN_DIM
    assert state["return_start_envelope_token_dim"] == RETURN_START_ENVELOPE_TOKEN_DIM
    assert state["return_target_token_source"] == "none"
    assert state["return_relocate_token_source"] == "none"
    assert state["return_start_envelope_token_source"] == "none"
    assert state["return_to_dig_entry_close"] is True
    assert state["return_to_dig_start_envelope_gate_enabled"] is False
    assert state["return_to_dig_start_envelope_direct_handoff_enabled"] is False
    assert state["return_to_dig_start_envelope_ready"] is True
    assert state["return_to_dig_start_envelope_plane_depth_mode"] == "range"
    assert state["return_to_dig_start_envelope_checks"] == {}

    assert state["coverage_corridor_id"] == -1
    assert state["coverage_last_selected_cell_id"] == -1
    assert state["coverage_candidate_layout"] == "percentile_grid"
    assert state["coverage_multi_pass_enabled"] is False
    assert state["coverage_corridors"] == []
    assert state["coverage_candidate_scores"] == []
    assert state["coverage_terminal_stop_requested"] is False
    assert state["planner_terminal_stop_requested"] is False

    assert state["pre_dig_align_enabled"] is False
    assert state["pre_dig_align_first_dig_only"] is False
    assert state["pre_dig_align_entry_intent_controlled_dims"] is None
    assert state["pre_dig_align_active_for_next_dig"] is False
    assert state["pre_dig_align_controlled_dims"] == [1, 1, 1, 0]

    _assert_exact_type(state, "transition_timeout", bool)
    _assert_exact_type(state, "completed_transition_count", int)
    _assert_exact_type(state, "dig_cut_token_source", str)
    _assert_exact_type(state, "return_to_dig_start_envelope_checks", dict)
    _assert_exact_type(state, "coverage_corridors", list)
    _assert_exact_type(state, "pre_dig_align_controlled_dims", list)


def test_debug_state_configured_schema_is_stable() -> None:
    policy = _make_configured_policy()
    policy._ensure_coverage_corridors()

    state = policy.debug_state()

    _assert_nested_equal(
        state,
        build_primitive_debug_state_from_facts(policy._debug_state_facts()),
    )
    _assert_nested_equal(state, build_primitive_debug_state(policy))
    assert tuple(state) == EXPECTED_DEBUG_STATE_KEYS
    assert state["skill_name"] == "pre_dig_align"
    assert state["skill_id"] == -1
    assert state["cell_entry_enabled"] is True
    assert state["return_to_dig_start_envelope_gate_enabled"] is True
    assert state["return_to_dig_start_envelope_direct_handoff_enabled"] is True
    assert state["return_to_dig_start_envelope_plane_depth_mode"] == "target_band"
    assert state["return_to_dig_start_envelope_local_depth_tolerance_m"] == 0.007
    assert state["return_target_token_injected"] is False
    assert state["return_start_envelope_token_source"] == "none"

    assert state["dig_cut_planner_mode"] == "operator_prior_coverage"
    assert state["dig_cut_prior_id"] == "yulong_operator_first_dig_cut_prior_v1"
    assert state["coverage_candidate_layout"] == "percentile_grid"
    assert state["coverage_use_env_removed_depth"] is True
    assert state["coverage_multi_pass_enabled"] is True
    assert len(state["coverage_corridors"]) == 9
    assert tuple(state["coverage_corridors"][0]) == EXPECTED_COVERAGE_CORRIDOR_DEBUG_KEYS
    assert state["coverage_corridors"][0]["corridor_id"] == 0
    assert state["coverage_corridors"][0]["attempt_limit"] == 3
    assert state["coverage_corridors"][0]["depleted"] == 0

    assert state["pre_dig_align_enabled"] is True
    assert state["pre_dig_align_first_dig_only"] is True
    assert state["pre_dig_align_replan_after_failed_dig"] is True
    assert state["pre_dig_align_surface_guard_enabled"] is True
    assert state["pre_dig_align_entry_intent_controlled_dims"] == [1, 0, 1, 0]
    assert state["pre_dig_align_entry_intent_handoff_enabled"] is True


def test_debug_and_summary_facts_use_return_handoff_status_snapshot() -> None:
    policy = _make_configured_policy()
    policy._return_to_dig_entry_error_m = 1.25
    policy._return_to_dig_entry_close_state = True
    policy._return_next_dig_event_seen = False
    policy._return_to_dig_start_envelope_ready_state = True
    policy._return_to_dig_start_envelope_error = 0.33
    policy._return_to_dig_start_envelope_checks = {"old": {"ok": True}}
    calls: list[Any] = []

    def fake_status_snapshot(**kwargs: Any) -> ReturnToDigHandoffStatusSnapshot:
        calls.append(kwargs)
        return ReturnToDigHandoffStatusSnapshot(
            max_entry_error_m=0.44,
            entry_error_m=0.55,
            entry_close=False,
            next_dig_event_seen=True,
            start_envelope_gate_enabled=False,
            start_envelope_direct_handoff_enabled=False,
            start_envelope_ready=False,
            start_envelope_plane_depth_mode="snapshot_mode",
            start_envelope_local_depth_tolerance_m=0.066,
            start_envelope_error=0.77,
            start_envelope_checks={"snapshot": {"ok": False}},
        )

    policy.return_handoff_gate.status_snapshot = fake_status_snapshot  # type: ignore[method-assign]

    debug_facts = policy._debug_state_facts()
    summary_facts = policy._rollout_summary_facts()

    assert len(calls) == 2
    state = calls[0]["state"]
    assert state.entry_error_m == 1.25
    assert state.entry_close is True
    assert state.next_dig_event_seen is False
    assert state.start_envelope_ready is True
    assert state.start_envelope_error == 0.33
    assert state.start_envelope_checks == {"old": {"ok": True}}
    assert debug_facts.return_to_dig_entry_error_m == 0.55
    assert debug_facts.return_to_dig_entry_close is False
    assert debug_facts.return_next_dig_event_seen is True
    assert debug_facts.return_to_dig_start_envelope_gate_enabled is False
    assert debug_facts.return_to_dig_start_envelope_direct_handoff_enabled is False
    assert debug_facts.return_to_dig_start_envelope_ready is False
    assert debug_facts.return_to_dig_start_envelope_plane_depth_mode == "snapshot_mode"
    assert debug_facts.return_to_dig_start_envelope_local_depth_tolerance_m == 0.066
    assert debug_facts.return_to_dig_start_envelope_error == 0.77
    assert debug_facts.return_to_dig_start_envelope_checks == {
        "snapshot": {"ok": False}
    }
    assert summary_facts.return_to_dig_max_entry_error_m == 0.44
    assert summary_facts.return_to_dig_entry_error_m == 0.55
    assert summary_facts.return_to_dig_entry_close is False
    assert summary_facts.return_next_dig_event_seen is True
    assert summary_facts.return_to_dig_start_envelope_gate_enabled is False
    assert summary_facts.return_to_dig_start_envelope_direct_handoff_enabled is False
    assert summary_facts.return_to_dig_start_envelope_ready is False
    assert summary_facts.return_to_dig_start_envelope_plane_depth_mode == "snapshot_mode"
    assert summary_facts.return_to_dig_start_envelope_local_depth_tolerance_m == 0.066
    assert summary_facts.return_to_dig_start_envelope_error == 0.77


def test_debug_and_summary_facts_use_return_target_conditioning_status_snapshot() -> None:
    policy = _make_configured_policy()
    policy._return_target_token_injected = False
    policy._return_target_token_source = "planner_target_source"
    policy._return_target_tokens = np.full(
        RETURN_TARGET_TOKEN_DIM,
        1.0,
        dtype=np.float32,
    )
    policy._return_target_fallback_reason = "planner_target_fallback"
    policy._return_relocate_token_injected = False
    policy._return_relocate_tokens = np.full(
        RETURN_TARGET_TOKEN_DIM,
        2.0,
        dtype=np.float32,
    )
    policy._return_start_envelope_token_injected = False
    policy._return_start_envelope_token_source = "planner_envelope_source"
    policy._return_start_envelope_tokens = np.full(
        RETURN_START_ENVELOPE_TOKEN_DIM,
        3.0,
        dtype=np.float32,
    )
    calls: list[Any] = []

    def fake_status_snapshot_from_mapping(
        values: dict[str, Any],
    ) -> ReturnTargetConditioningStatusSnapshot:
        calls.append(values)
        return ReturnTargetConditioningStatusSnapshot(
            target_token_injected=True,
            target_token_source="snapshot_target_source",
            target_tokens=np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32),
            target_fallback_reason="snapshot_target_fallback",
            relocate_token_injected=True,
            relocate_tokens=(
                np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32) + 10.0
            ),
            start_envelope_token_injected=True,
            start_envelope_token_source="snapshot_envelope_source",
            start_envelope_tokens=(
                np.arange(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)
                + 20.0
            ),
        )

    policy.return_target_plan_service.conditioning_status_snapshot_from_mapping = (  # type: ignore[method-assign]
        fake_status_snapshot_from_mapping
    )

    debug_facts = policy._debug_state_facts()
    summary_facts = policy._rollout_summary_facts()

    assert len(calls) == 2
    values = calls[0]
    assert values["target_token_injected"] is False
    assert values["target_token_source"] == "planner_target_source"
    np.testing.assert_allclose(
        values["target_tokens"],
        np.full(RETURN_TARGET_TOKEN_DIM, 1.0, dtype=np.float32),
    )
    assert values["target_fallback_reason"] == "planner_target_fallback"
    assert values["relocate_token_injected"] is False
    np.testing.assert_allclose(
        values["relocate_tokens"],
        np.full(RETURN_TARGET_TOKEN_DIM, 2.0, dtype=np.float32),
    )
    assert values["start_envelope_token_injected"] is False
    assert values["start_envelope_token_source"] == "planner_envelope_source"
    np.testing.assert_allclose(
        values["start_envelope_tokens"],
        np.full(RETURN_START_ENVELOPE_TOKEN_DIM, 3.0, dtype=np.float32),
    )
    assert debug_facts.return_target_token_injected is True
    assert debug_facts.return_target_token_source == "snapshot_target_source"
    np.testing.assert_allclose(
        debug_facts.return_target_tokens,
        np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32),
    )
    assert debug_facts.return_target_fallback_reason == "snapshot_target_fallback"
    assert debug_facts.return_relocate_token_injected is True
    np.testing.assert_allclose(
        debug_facts.return_relocate_tokens,
        np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32) + 10.0,
    )
    assert debug_facts.return_start_envelope_token_injected is True
    assert (
        debug_facts.return_start_envelope_token_source
        == "snapshot_envelope_source"
    )
    np.testing.assert_allclose(
        debug_facts.return_start_envelope_tokens,
        np.arange(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32) + 20.0,
    )
    assert summary_facts.return_target_token_source == "snapshot_target_source"


def test_debug_and_summary_facts_use_dig_cut_runtime_status_snapshot() -> None:
    policy = _make_configured_policy()
    policy._pending_dig_cut_cycle_id = 3
    policy._pending_dig_cut_corridor_id = 4
    policy._dig_cut_token_injected = False
    policy._dig_cut_token_source = "planner_source"
    policy._dig_cut_tokens = np.full(DIG_CUT_TOKEN_DIM, 1.0, dtype=np.float32)
    policy._dig_depth_profile_tokens = np.full(
        DIG_DEPTH_PROFILE_TOKEN_DIM,
        2.0,
        dtype=np.float32,
    )
    policy._dig_cut_token_in_prior_p10_p90 = False
    policy._dig_cut_fallback_reason = "planner_fallback"
    calls: list[Any] = []

    def fake_status_snapshot_from_mappings(**kwargs: Any) -> DigCutRuntimeStatusSnapshot:
        calls.append(kwargs)
        return DigCutRuntimeStatusSnapshot(
            pending_cycle_id=11,
            pending_corridor_id=12,
            token_injected=True,
            planner_mode="snapshot_mode",
            prior_id="snapshot_prior",
            token_source="snapshot_source",
            tokens=np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float32),
            token_in_prior_p10_p90=True,
            fallback_reason="snapshot_fallback",
        )

    policy.dig_cut_plan_service.runtime_status_snapshot_from_mappings = (  # type: ignore[method-assign]
        fake_status_snapshot_from_mappings
    )

    debug_facts = policy._debug_state_facts()
    summary_facts = policy._rollout_summary_facts()

    assert len(calls) == 2
    config_values = calls[0]["config_values"]
    state_values = calls[0]["state_values"]
    assert config_values["planner_mode"] == policy.dig_cut_planner_mode
    assert config_values["prior_id"] == policy.dig_cut_prior_id
    assert state_values["pending_cycle_id"] == 3
    assert state_values["pending_corridor_id"] == 4
    assert state_values["token_injected"] is False
    assert state_values["token_source"] == "planner_source"
    np.testing.assert_allclose(
        state_values["tokens"],
        np.full(DIG_CUT_TOKEN_DIM, 1.0),
    )
    assert state_values["token_in_prior_p10_p90"] is False
    assert state_values["fallback_reason"] == "planner_fallback"
    assert debug_facts.pending_dig_cut_cycle_id == 11
    assert debug_facts.pending_dig_cut_corridor_id == 12
    assert debug_facts.dig_cut_token_injected is True
    assert debug_facts.dig_cut_planner_mode == "snapshot_mode"
    assert debug_facts.dig_cut_prior_id == "snapshot_prior"
    assert debug_facts.dig_cut_token_source == "snapshot_source"
    np.testing.assert_allclose(
        debug_facts.dig_cut_tokens,
        np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float32),
    )
    np.testing.assert_allclose(
        debug_facts.dig_depth_profile_tokens,
        np.full(DIG_DEPTH_PROFILE_TOKEN_DIM, 2.0, dtype=np.float32),
    )
    assert debug_facts.dig_cut_token_in_prior_p10_p90 is True
    assert debug_facts.dig_cut_fallback_reason == "snapshot_fallback"
    assert summary_facts.pending_dig_cut_cycle_id == 11
    assert summary_facts.pending_dig_cut_corridor_id == 12
    assert summary_facts.dig_cut_token_injected is True
    assert summary_facts.dig_cut_planner_mode == "snapshot_mode"
    assert summary_facts.dig_cut_prior_id == "snapshot_prior"
    assert summary_facts.dig_cut_token_source == "snapshot_source"
    assert summary_facts.dig_cut_token_in_prior_p10_p90 is True
    assert summary_facts.dig_cut_fallback_reason == "snapshot_fallback"


def test_debug_state_facts_use_dig_depth_profile_runtime_status_snapshot() -> None:
    policy = _make_configured_policy()
    policy._dig_depth_profile_token_injected = False
    policy._dig_depth_profile_token_source = "planner_depth_source"
    policy._dig_depth_profile_fallback_reason = "planner_depth_fallback"
    policy._dig_depth_profile_tokens = np.full(
        DIG_DEPTH_PROFILE_TOKEN_DIM,
        3.0,
        dtype=np.float32,
    )
    calls: list[Any] = []

    def fake_status_snapshot_from_mappings(
        **kwargs: Any,
    ) -> DigDepthProfileRuntimeStatusSnapshot:
        calls.append(kwargs)
        return DigDepthProfileRuntimeStatusSnapshot(
            source="snapshot_depth_source",
            required=True,
            token_injected=True,
            token_source="snapshot_depth_token_source",
            fallback_reason="snapshot_depth_fallback",
            tokens=np.arange(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float32),
        )

    policy.dig_depth_profile_service.runtime_status_snapshot_from_mappings = (  # type: ignore[method-assign]
        fake_status_snapshot_from_mappings
    )

    debug_facts = policy._debug_state_facts()

    assert len(calls) == 1
    config_values = calls[0]["config_values"]
    assert config_values["source"] == "live_plan"
    assert config_values["required"] is False
    assert config_values["allow_live_fallback"] is True
    assert config_values["allow_global_fallback"] is True
    state_values = calls[0]["state_values"]
    assert state_values["token_injected"] is False
    assert state_values["token_source"] == "planner_depth_source"
    assert state_values["fallback_reason"] == "planner_depth_fallback"
    np.testing.assert_allclose(
        state_values["tokens"],
        np.full(DIG_DEPTH_PROFILE_TOKEN_DIM, 3.0, dtype=np.float32),
    )
    assert debug_facts.dig_depth_profile_source == "snapshot_depth_source"
    assert debug_facts.dig_depth_profile_required is True
    assert debug_facts.dig_depth_profile_token_injected is True
    assert debug_facts.dig_depth_profile_token_source == "snapshot_depth_token_source"
    assert (
        debug_facts.dig_depth_profile_fallback_reason
        == "snapshot_depth_fallback"
    )
    np.testing.assert_allclose(
        debug_facts.dig_depth_profile_tokens,
        np.arange(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float32),
    )


def test_debug_and_summary_facts_use_dig_lifecycle_runtime_status_snapshot() -> None:
    policy = _make_configured_policy()
    policy.dig_failed_replan_next_skill = "stop"
    policy._dig_step_count = 4
    policy._dig_best_mass_kg = 19.5
    policy._dig_mass_plateau_count = 2
    policy._dig_to_carry_reason = "planner_reason"
    policy._dig_bad_replan_count = 3
    policy._dig_exit_guard_replan_count = 1
    calls: list[Any] = []

    def fake_status_snapshot(**kwargs: Any) -> DigLifecycleRuntimeStatusSnapshot:
        calls.append(kwargs)
        return DigLifecycleRuntimeStatusSnapshot(
            failed_replan_next_skill="snapshot_next_skill",
            step_count=11,
            best_mass_kg=33.25,
            mass_plateau_count=7,
            dig_to_carry_reason="snapshot_reason",
            bad_replan_count=13,
            exit_guard_replan_count=17,
        )

    policy.dig_lifecycle_gate.runtime_status_snapshot = fake_status_snapshot  # type: ignore[method-assign]

    debug_facts = policy._debug_state_facts()
    summary_facts = policy._rollout_summary_facts()

    assert len(calls) == 2
    config = calls[0]["config"]
    assert config.dig_failed_replan_next_skill == "stop"
    state = calls[0]["state"]
    assert state.step_count == 4
    assert state.best_mass_kg == 19.5
    assert state.mass_plateau_count == 2
    assert state.dig_to_carry_reason == "planner_reason"
    assert state.bad_replan_count == 3
    assert state.exit_guard_replan_count == 1
    assert debug_facts.dig_failed_replan_next_skill == "snapshot_next_skill"
    assert debug_facts.dig_step_count == 11
    assert debug_facts.dig_best_mass_kg == 33.25
    assert debug_facts.dig_mass_plateau_count == 7
    assert debug_facts.dig_to_carry_reason == "snapshot_reason"
    assert debug_facts.dig_bad_replan_count == 13
    assert debug_facts.dig_exit_guard_replan_count == 17
    assert summary_facts.dig_failed_replan_next_skill == "snapshot_next_skill"
    assert summary_facts.dig_bad_replan_count == 13
    assert summary_facts.dig_exit_guard_replan_count == 17


def test_debug_and_summary_facts_use_bootstrap_runtime_status_snapshot() -> None:
    policy = _make_configured_policy()
    policy._scripted_bootstrap_step_count = 5
    policy._scripted_bootstrap_hold_count = 3
    policy._scripted_bootstrap_timeout_count = 2
    calls: list[Any] = []

    def fake_status_snapshot(state: Any) -> BootstrapRuntimeStatusSnapshot:
        calls.append(state)
        return BootstrapRuntimeStatusSnapshot(
            step_count=11,
            hold_count=13,
            timeout_count=17,
        )

    policy.bootstrap_service.runtime_status_snapshot = fake_status_snapshot  # type: ignore[method-assign]

    debug_facts = policy._debug_state_facts()
    summary_facts = policy._rollout_summary_facts()

    assert len(calls) == 2
    assert calls[0].step_count == 5
    assert calls[0].hold_count == 3
    assert calls[0].timeout_count == 2
    assert debug_facts.scripted_bootstrap_step_count == 11
    assert debug_facts.scripted_bootstrap_hold_count == 13
    assert debug_facts.scripted_bootstrap_timeout_count == 17
    assert summary_facts.scripted_bootstrap_timeout_count == 17


def test_debug_state_coverage_snapshot_preserves_exemplar_id_strings() -> None:
    policy = _make_configured_policy()
    policy._ensure_coverage_corridors()
    policy._coverage_active_corridor_id = 0
    policy._coverage_active_state_exemplar_ids = ["cell_0_0"]

    state = policy.debug_state()

    _assert_nested_equal(
        state,
        build_primitive_debug_state_from_facts(policy._debug_state_facts()),
    )
    _assert_nested_equal(state, build_primitive_debug_state(policy))
    assert state["coverage_state_exemplar_ids"] == ["cell_0_0"]


def test_debug_state_cell_entry_snapshot_preserves_goal_audit_and_seen_cell() -> None:
    policy = _make_policy()
    grid = CellGridSpec()
    planner = CellEntryPlanner(grid=grid)
    auditor = PlannerDecisionAuditor(grid=grid)
    goal = planner.plan(cycle_id=0)
    audit = auditor.audit(
        goal=goal,
        outcome=PrimitiveCycleOutcome(
            cycle_id=0,
            actual_start_step=1,
            actual_bite_step=2,
            actual_removal_step=2,
            actual_start_cell_id=goal.selected_cell_id,
            actual_bite_cell_id=goal.selected_cell_id,
            actual_removal_cell_id=goal.selected_cell_id,
            payload_gain_kg=150.0,
            deposit_delta_kg=0.0,
            collision_count_delta=0,
        ),
        current_bucket_pose=(
            goal.planned_entry_x_m,
            goal.planned_entry_y_m,
            goal.planned_entry_z_m,
        ),
        geometry_available=True,
    )
    policy._cell_entry_goal = goal
    policy._cell_entry_goal_cycle_id = 0
    policy._cell_entry_audit = audit
    policy._cell_entry_seen_cell_id = 5

    state = policy.debug_state()

    _assert_nested_equal(
        state,
        build_primitive_debug_state_from_facts(policy._debug_state_facts()),
    )
    _assert_nested_equal(state, build_primitive_debug_state(policy))
    assert state["cell_entry_selected_cell_id"] == goal.selected_cell_id
    assert state["cell_entry_selected_long_index"] == goal.selected_long_index
    assert state["cell_entry_selected_short_index"] == goal.selected_short_index
    assert state["cell_entry_planned_entry_x_m"] == goal.planned_entry_x_m
    assert state["cell_entry_planned_entry_y_m"] == goal.planned_entry_y_m
    assert state["cell_entry_planned_entry_z_m"] == goal.planned_entry_z_m
    assert state["cell_entry_planner_ok"] is True
    assert state["cell_entry_audit_reason_code"] == AUDIT_REASON_TO_ID["ok"]
    assert state["cell_entry_audit_reason"] == "ok"
    assert state["cell_entry_audit_risk_flags"] == 0
    assert state["cell_entry_inside_entry_envelope"] is True
    assert state["cell_entry_distance_to_entry_envelope_m"] == 0.0
    assert state["cell_entry_seen_cell_id"] == 5


def test_debug_state_pre_dig_align_snapshot_preserves_alignment_fields() -> None:
    policy = _make_configured_policy()
    policy.pre_dig_align_controlled_dims = np.asarray(
        [True, False, True, False],
        dtype=bool,
    )
    policy.pre_dig_align_bucket_target_qpos = 0.11
    policy.pre_dig_align_first_dig_entry_close_handoff = True
    policy.pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max = 0.08
    policy._pre_dig_align_surface_depth_m = 0.05
    policy._pre_dig_align_surface_guard_triggered = True
    policy._pre_dig_align_surface_guard_count = 2
    policy._pre_dig_align_step_count = 3
    policy._pre_dig_align_hold_count = 4
    policy._pre_dig_align_timeout_count = 5
    policy._pre_dig_align_completed_count = 6
    policy._pre_dig_align_replan_count = 7
    policy._pre_dig_align_target_qpos = np.asarray(
        [0.1, 0.2, 0.3, 0.4],
        dtype=np.float32,
    )
    policy._pre_dig_align_error = np.asarray(
        [0.01, -0.02, 0.03, -0.04],
        dtype=np.float32,
    )
    policy._pre_dig_align_entry_error_m = 0.09
    policy._pre_dig_align_start_envelope_ready = True
    policy._pre_dig_align_entry_close_handoff_ready = True
    policy._pre_dig_align_entry_intent_handoff_ready = True

    state = policy.debug_state()

    _assert_nested_equal(
        state,
        build_primitive_debug_state_from_facts(policy._debug_state_facts()),
    )
    _assert_nested_equal(state, build_primitive_debug_state(policy))
    assert state["pre_dig_align_enabled"] is True
    assert state["pre_dig_align_entry_intent_controlled_dims"] == [1, 0, 1, 0]
    assert state["pre_dig_align_surface_guard_enabled"] is True
    assert state["pre_dig_align_surface_depth_m"] == 0.05
    assert state["pre_dig_align_surface_guard_triggered"] is True
    assert state["pre_dig_align_surface_guard_count"] == 2
    assert state["pre_dig_align_step_count"] == 3
    assert state["pre_dig_align_hold_count"] == 4
    assert state["pre_dig_align_timeout_count"] == 5
    assert state["pre_dig_align_completed_count"] == 6
    assert state["pre_dig_align_replan_count"] == 7
    np.testing.assert_allclose(
        state["pre_dig_align_target_qpos"],
        [0.1, 0.2, 0.3, 0.4],
    )
    np.testing.assert_allclose(
        state["pre_dig_align_error"],
        [0.01, -0.02, 0.03, -0.04],
    )
    assert state["pre_dig_align_entry_error_m"] == 0.09
    assert state["pre_dig_align_start_envelope_ready"] is True
    assert state["pre_dig_align_first_dig_entry_close_handoff"] is True
    assert state["pre_dig_align_entry_close_handoff_ready"] is True
    assert state["pre_dig_align_entry_intent_handoff_enabled"] is True
    assert state["pre_dig_align_entry_intent_handoff_ready"] is True
    assert state["pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max"] == 0.08
    assert state["pre_dig_align_controlled_dims"] == [1, 0, 1, 0]
    assert state["pre_dig_align_bucket_target_qpos"] == 0.11


def test_debug_and_summary_facts_use_pre_dig_align_debug_snapshot() -> None:
    policy = _make_configured_policy()
    policy.pre_dig_align_first_dig_only = True
    policy.pre_dig_align_replan_after_failed_dig = True
    policy._pre_dig_align_surface_guard_count = 99
    policy._pre_dig_align_timeout_count = 99
    policy._pre_dig_align_completed_count = 99
    policy._pre_dig_align_replan_count = 99

    def fake_debug_snapshot(**kwargs: Any) -> DigStartAlignmentDebugSnapshot:
        return DigStartAlignmentDebugSnapshot(
            enabled=False,
            entry_intent_controlled_dims=None,
            surface_guard_enabled=False,
            surface_depth_m=0.44,
            surface_guard_triggered=True,
            surface_guard_count=2,
            step_count=3,
            hold_count=4,
            timeout_count=5,
            completed_count=6,
            replan_count=7,
            target_qpos=np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
            error=np.asarray([0.01, 0.02, 0.03, 0.04], dtype=np.float32),
            entry_error_m=0.55,
            start_envelope_ready=True,
            first_dig_entry_close_handoff=False,
            entry_close_handoff_ready=True,
            entry_intent_handoff_enabled=False,
            entry_intent_handoff_ready=True,
            first_dig_entry_close_handoff_qvel_abs_max=None,
            controlled_dims=np.asarray([True, False, True, False], dtype=bool),
            bucket_target_qpos=None,
        )

    policy.dig_start_alignment_service.debug_snapshot = fake_debug_snapshot  # type: ignore[method-assign]

    debug_facts = policy._debug_state_facts()
    summary_facts = policy._rollout_summary_facts()

    assert debug_facts.pre_dig_align_enabled is False
    assert debug_facts.pre_dig_align_surface_guard_enabled is False
    assert debug_facts.pre_dig_align_surface_guard_count == 2
    assert debug_facts.pre_dig_align_timeout_count == 5
    assert debug_facts.pre_dig_align_completed_count == 6
    assert debug_facts.pre_dig_align_replan_count == 7
    assert summary_facts.pre_dig_align_enabled is False
    assert summary_facts.pre_dig_align_first_dig_only is True
    assert summary_facts.pre_dig_align_replan_after_failed_dig is True
    assert summary_facts.pre_dig_align_surface_guard_enabled is False
    assert summary_facts.pre_dig_align_surface_guard_count == 2
    assert summary_facts.pre_dig_align_timeout_count == 5
    assert summary_facts.pre_dig_align_completed_count == 6
    assert summary_facts.pre_dig_align_replan_count == 7


def test_debug_state_assembly_input_mapping_preserves_shell_projection() -> None:
    debug_state = object()
    coverage_debug = object()
    return_handoff_status = object()
    dig_cut_status = object()
    dig_depth_profile_status = object()
    return_target_status = object()
    dig_lifecycle_status = object()
    bootstrap_status = object()
    cell_entry_debug = object()
    pre_dig_align_debug = object()
    values = {
        "debug_state": debug_state,
        "cell_entry_enabled": 1,
        "cell_entry_token_injected": 0,
        "pre_dig_align_first_dig_only": 1,
        "pre_dig_align_replan_after_failed_dig": 0,
        "ignored": object(),
    }

    inputs = build_primitive_debug_state_assembly_inputs_from_mapping(
        values,
        primitive_goal_curr_sector_id="2",
        primitive_goal_next_sector_id=np.int64(3),
        pre_dig_align_active_for_next_dig=1,
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

    assert {key for key, _ in PRIMITIVE_DEBUG_STATE_ASSEMBLY_FIELDS} == (
        set(values) - {"ignored"}
    )
    assert inputs.debug_state is debug_state
    assert inputs.primitive_goal_curr_sector_id == 2
    assert inputs.primitive_goal_next_sector_id == 3
    assert inputs.cell_entry_enabled is True
    assert inputs.cell_entry_token_injected is False
    assert inputs.pre_dig_align_first_dig_only is True
    assert inputs.pre_dig_align_replan_after_failed_dig is False
    assert inputs.pre_dig_align_active_for_next_dig is True
    assert inputs.coverage_debug is coverage_debug
    assert inputs.return_handoff_status is return_handoff_status
    assert inputs.dig_cut_status is dig_cut_status
    assert inputs.dig_depth_profile_status is dig_depth_profile_status
    assert inputs.return_target_status is return_target_status
    assert inputs.dig_lifecycle_status is dig_lifecycle_status
    assert inputs.bootstrap_status is bootstrap_status
    assert inputs.cell_entry_debug is cell_entry_debug
    assert inputs.pre_dig_align_debug is pre_dig_align_debug


def test_debug_state_facts_from_mapping_matches_legacy_assembly_chain() -> None:
    policy = _make_configured_policy()
    policy._ensure_coverage_corridors()
    values = {
        field_name: getattr(policy, attr_name)
        for field_name, attr_name in PRIMITIVE_DEBUG_STATE_ASSEMBLY_FIELDS
    }
    kwargs = {
        "primitive_goal_curr_sector_id": policy._goal_sector_id(
            policy._cycle_index
        ),
        "primitive_goal_next_sector_id": policy._next_goal_sector_id(),
        "pre_dig_align_active_for_next_dig": (
            policy._should_pre_dig_align_before_dig()
        ),
        "coverage_debug": policy._coverage_debug_snapshot(),
        "return_handoff_status": policy._return_to_dig_handoff_status_snapshot(),
        "dig_cut_status": policy._dig_cut_runtime_status_snapshot(),
        "dig_depth_profile_status": (
            policy._dig_depth_profile_runtime_status_snapshot()
        ),
        "return_target_status": policy._return_target_conditioning_status_snapshot(),
        "dig_lifecycle_status": policy._dig_lifecycle_runtime_status_snapshot(),
        "bootstrap_status": policy._bootstrap_runtime_status_snapshot(),
        "cell_entry_debug": policy._cell_entry_debug_snapshot(),
        "pre_dig_align_debug": policy._pre_dig_align_debug_snapshot(),
    }

    legacy = build_primitive_debug_state_facts(
        build_primitive_debug_state_assembly_inputs_from_mapping(values, **kwargs)
    )
    combined = build_primitive_debug_state_facts_from_mapping(values, **kwargs)

    _assert_nested_equal(
        build_primitive_debug_state_from_facts(combined),
        build_primitive_debug_state_from_facts(legacy),
    )


def test_rollout_summary_schema_is_stable() -> None:
    policy = _make_configured_policy()

    summary = policy.rollout_summary()

    _assert_nested_equal(
        summary,
        build_primitive_rollout_summary_from_facts(policy._rollout_summary_facts()),
    )
    _assert_nested_equal(summary, build_primitive_rollout_summary(policy))
    assert tuple(summary) == EXPECTED_ROLLOUT_SUMMARY_KEYS
    assert len(summary) == 57
    assert summary["transition_source"] == TRANSITION_SOURCE_PRIMITIVE_RETURN_POLICY
    assert summary["transition_policy_mode"] == TRANSITION_POLICY_MODE_PRIMITIVE
    assert summary["transition_fallback_count"] == 0
    assert summary["transition_fallback_reason"] == ""
    assert summary["primitive_final_skill"] == "pre_dig_align"
    assert summary["primitive_cycle_index"] == 0
    assert summary["cell_entry_enabled"] == 1
    assert summary["cell_entry_trace_count"] == 0
    assert summary["dig_cut_token_dim"] == DIG_CUT_TOKEN_DIM
    assert summary["return_target_token_dim"] == RETURN_TARGET_TOKEN_DIM
    assert summary["return_target_token_source"] == "none"
    assert np.isnan(summary["return_to_dig_max_entry_error_m"])
    assert summary["return_to_dig_entry_close"] == 1
    assert summary["return_to_dig_start_envelope_gate_enabled"] == 1
    assert summary["return_to_dig_start_envelope_direct_handoff_enabled"] == 1
    assert summary["return_to_dig_start_envelope_plane_depth_mode"] == "target_band"
    assert summary["return_to_dig_start_envelope_local_depth_tolerance_m"] == 0.007
    assert summary["dig_cut_token_injected"] == 0
    assert summary["dig_cut_planner_mode"] == "operator_prior_coverage"
    assert summary["dig_cut_prior_id"] == "yulong_operator_first_dig_cut_prior_v1"
    assert summary["coverage_selected_corridor_id"] == -1
    assert summary["coverage_multi_pass_enabled"] == 1
    assert summary["coverage_candidate_layout"] == "percentile_grid"
    assert summary["pre_dig_align_enabled"] == 1
    assert summary["pre_dig_align_first_dig_only"] == 1
    assert summary["pre_dig_align_replan_after_failed_dig"] == 1
    assert summary["pre_dig_align_surface_guard_enabled"] == 1

    _assert_exact_type(summary, "cell_entry_enabled", int)
    _assert_exact_type(summary, "return_to_dig_start_envelope_gate_enabled", int)
    _assert_exact_type(summary, "coverage_multi_pass_enabled", int)
    _assert_exact_type(summary, "pre_dig_align_enabled", int)
    _assert_exact_type(summary, "return_to_dig_max_entry_error_m", float)


def test_rollout_summary_facts_use_coverage_summary_snapshot() -> None:
    policy = _make_configured_policy()
    policy._ensure_coverage_corridors()
    policy._coverage_active_corridor_id = 0
    policy._coverage_completed_dump_count = 3
    policy._coverage_pass_index = 2
    policy._coverage_corridors[1].depleted = True
    policy.coverage_first_dig_preferred_corridor_id = None
    policy.coverage_first_dig_max_entry_distance_m = None
    policy._request_coverage_terminal_stop("unit_terminal", replace=True)

    snapshot = policy._coverage_rollout_summary_snapshot()
    facts = policy._rollout_summary_facts()

    assert facts.coverage_selected_corridor_id == snapshot.selected_corridor_id
    assert facts.coverage_depleted_count == snapshot.depleted_count
    assert facts.coverage_completed_dump_count == snapshot.completed_dump_count
    assert facts.coverage_pass_index == snapshot.pass_index
    assert facts.coverage_multi_pass_enabled == snapshot.multi_pass_enabled
    assert facts.coverage_use_env_removed_depth == snapshot.use_env_removed_depth
    assert facts.coverage_candidate_layout == snapshot.candidate_layout
    assert facts.coverage_first_dig_strategy == snapshot.first_dig_strategy
    assert (
        facts.coverage_first_dig_preferred_corridor_id
        == snapshot.first_dig_preferred_corridor_id
    )
    assert (
        facts.coverage_first_dig_max_entry_distance_m
        == snapshot.first_dig_max_entry_distance_m
    )
    assert (
        facts.coverage_first_dig_qpos_delta_weight
        == snapshot.first_dig_qpos_delta_weight
    )
    assert facts.coverage_terminal_stop_requested == snapshot.terminal_stop_requested
    assert facts.coverage_terminal_stop_reason == snapshot.terminal_stop_reason

    summary = build_primitive_rollout_summary_from_facts(facts)

    assert summary["coverage_first_dig_preferred_corridor_id"] == -1
    assert np.isnan(summary["coverage_first_dig_max_entry_distance_m"])
    assert summary["coverage_terminal_stop_requested"] == 1
    assert summary["coverage_terminal_stop_reason"] == "unit_terminal"


def test_rollout_summary_assembly_input_mapping_preserves_shell_projection() -> None:
    coverage_summary = object()
    return_handoff_status = object()
    dig_cut_status = object()
    return_target_status = object()
    dig_lifecycle_status = object()
    bootstrap_status = object()
    pre_dig_align_debug = object()
    values = {
        "transition_timeout_count": "2",
        "completed_transition_count": np.int64(3),
        "dump_done_use_boundary_event": 1,
        "primitive_final_skill": 123,
        "primitive_cycle_index": "4",
        "cell_entry_enabled": 0,
        "cell_entry_trace": [{"cycle_id": 1}, {"cycle_id": 2}],
        "pre_dig_align_first_dig_only": 1,
        "pre_dig_align_replan_after_failed_dig": 0,
        "ignored": object(),
    }

    inputs = build_primitive_rollout_summary_assembly_inputs_from_mapping(
        values,
        coverage_summary=coverage_summary,
        return_handoff_status=return_handoff_status,
        dig_cut_status=dig_cut_status,
        return_target_status=return_target_status,
        dig_lifecycle_status=dig_lifecycle_status,
        bootstrap_status=bootstrap_status,
        pre_dig_align_debug=pre_dig_align_debug,
    )

    assert {key for key, _ in PRIMITIVE_ROLLOUT_SUMMARY_ASSEMBLY_FIELDS} == (
        set(values) - {"ignored"}
    )
    assert inputs.transition_timeout_count == 2
    assert inputs.completed_transition_count == 3
    assert inputs.dump_done_use_boundary_event is True
    assert inputs.primitive_final_skill == "123"
    assert inputs.primitive_cycle_index == 4
    assert inputs.cell_entry_enabled is False
    assert inputs.cell_entry_trace_count == 2
    assert inputs.pre_dig_align_first_dig_only is True
    assert inputs.pre_dig_align_replan_after_failed_dig is False
    assert inputs.coverage_summary is coverage_summary
    assert inputs.return_handoff_status is return_handoff_status
    assert inputs.dig_cut_status is dig_cut_status
    assert inputs.return_target_status is return_target_status
    assert inputs.dig_lifecycle_status is dig_lifecycle_status
    assert inputs.bootstrap_status is bootstrap_status
    assert inputs.pre_dig_align_debug is pre_dig_align_debug


def test_rollout_summary_facts_from_mapping_matches_legacy_assembly_chain() -> None:
    policy = _make_configured_policy()
    policy._ensure_coverage_corridors()
    values = {
        field_name: getattr(policy, attr_name)
        for field_name, attr_name in PRIMITIVE_ROLLOUT_SUMMARY_ASSEMBLY_FIELDS
    }
    kwargs = {
        "coverage_summary": policy._coverage_rollout_summary_snapshot(),
        "return_handoff_status": policy._return_to_dig_handoff_status_snapshot(),
        "dig_cut_status": policy._dig_cut_runtime_status_snapshot(),
        "return_target_status": policy._return_target_conditioning_status_snapshot(),
        "dig_lifecycle_status": policy._dig_lifecycle_runtime_status_snapshot(),
        "bootstrap_status": policy._bootstrap_runtime_status_snapshot(),
        "pre_dig_align_debug": policy._pre_dig_align_debug_snapshot(),
    }

    legacy = build_primitive_rollout_summary_facts(
        build_primitive_rollout_summary_assembly_inputs_from_mapping(
            values,
            **kwargs,
        )
    )
    combined = build_primitive_rollout_summary_facts_from_mapping(
        values,
        **kwargs,
    )

    _assert_nested_equal(
        build_primitive_rollout_summary_from_facts(combined),
        build_primitive_rollout_summary_from_facts(legacy),
    )


def test_rollout_summary_builder_from_facts_preserves_schema_and_coercions() -> None:
    facts = PrimitiveRolloutSummaryFacts(
        transition_timeout_count=2,
        completed_transition_count=3,
        dump_done_use_boundary_event=True,
        primitive_final_skill="return",
        primitive_cycle_index=4,
        cell_entry_enabled=True,
        cell_entry_trace_count=5,
        return_target_token_source="operator_prior",
        return_to_dig_max_entry_error_m=None,
        return_to_dig_entry_error_m=0.25,
        return_to_dig_entry_close=True,
        return_next_dig_event_seen=False,
        return_to_dig_start_envelope_gate_enabled=True,
        return_to_dig_start_envelope_direct_handoff_enabled=False,
        return_to_dig_start_envelope_ready=True,
        return_to_dig_start_envelope_plane_depth_mode="target_band",
        return_to_dig_start_envelope_local_depth_tolerance_m=0.007,
        return_to_dig_start_envelope_error=0.125,
        pending_dig_cut_cycle_id=6,
        pending_dig_cut_corridor_id=7,
        dig_cut_token_injected=True,
        dig_cut_planner_mode="operator_prior_coverage",
        dig_cut_prior_id="prior_a",
        dig_cut_token_source="pending_return_target",
        dig_cut_token_in_prior_p10_p90=True,
        dig_cut_fallback_reason="",
        dig_failed_replan_next_skill="dig",
        coverage_selected_corridor_id=8,
        coverage_depleted_count=9,
        coverage_completed_dump_count=10,
        coverage_pass_index=11,
        coverage_multi_pass_enabled=True,
        coverage_use_env_removed_depth=False,
        coverage_candidate_layout="percentile_grid",
        coverage_first_dig_strategy="coverage_score",
        coverage_first_dig_preferred_corridor_id=None,
        coverage_first_dig_max_entry_distance_m=None,
        coverage_first_dig_qpos_delta_weight=0.5,
        coverage_terminal_stop_requested=True,
        coverage_terminal_stop_reason="dig_area_depleted",
        scripted_bootstrap_timeout_count=12,
        pre_dig_align_enabled=True,
        pre_dig_align_first_dig_only=False,
        pre_dig_align_replan_after_failed_dig=True,
        pre_dig_align_surface_guard_enabled=False,
        pre_dig_align_surface_guard_count=13,
        pre_dig_align_timeout_count=14,
        pre_dig_align_completed_count=15,
        pre_dig_align_replan_count=16,
        dig_bad_replan_count=17,
        dig_exit_guard_replan_count=18,
    )

    summary = build_primitive_rollout_summary_from_facts(facts)

    assert tuple(summary) == EXPECTED_ROLLOUT_SUMMARY_KEYS
    assert len(summary) == 57
    assert summary["transition_source"] == TRANSITION_SOURCE_PRIMITIVE_RETURN_POLICY
    assert summary["transition_policy_mode"] == TRANSITION_POLICY_MODE_PRIMITIVE
    assert summary["transition_fallback_count"] == 0
    assert summary["transition_fallback_reason"] == ""
    assert summary["dig_cut_token_dim"] == DIG_CUT_TOKEN_DIM
    assert summary["return_target_token_dim"] == RETURN_TARGET_TOKEN_DIM
    assert np.isnan(summary["return_to_dig_max_entry_error_m"])
    assert summary["coverage_first_dig_preferred_corridor_id"] == -1
    assert np.isnan(summary["coverage_first_dig_max_entry_distance_m"])
    assert summary["coverage_terminal_stop_reason"] == "dig_area_depleted"
    assert summary["cell_entry_enabled"] == 1
    assert summary["dump_done_use_boundary_event"] == 1
    assert summary["return_next_dig_event_seen"] == 0
    assert summary["return_to_dig_start_envelope_direct_handoff_enabled"] == 0
    assert summary["coverage_multi_pass_enabled"] == 1
    assert summary["coverage_use_env_removed_depth"] == 0
    assert summary["pre_dig_align_first_dig_only"] == 0
    assert summary["pre_dig_align_replan_after_failed_dig"] == 1
    _assert_exact_type(summary, "cell_entry_enabled", int)
    _assert_exact_type(summary, "dump_done_use_boundary_event", int)
    _assert_exact_type(summary, "coverage_use_env_removed_depth", int)
    _assert_exact_type(summary, "return_to_dig_max_entry_error_m", float)


def test_planner_trace_schema_is_stable() -> None:
    policy = _make_configured_policy()
    policy._ensure_coverage_corridors()

    trace = policy.planner_trace()

    _assert_nested_equal(
        trace,
        build_primitive_planner_trace_from_facts(policy._planner_trace_facts()),
    )
    _assert_nested_equal(trace, build_primitive_planner_trace(policy))
    assert tuple(trace) == EXPECTED_PLANNER_TRACE_KEYS
    assert trace["dig_cut_planner_mode"] == "operator_prior_coverage"
    assert trace["dig_cut_prior_id"] == "yulong_operator_first_dig_cut_prior_v1"
    assert trace["return_target_planner_enabled"] is True
    assert trace["coverage_use_env_removed_depth"] is True
    assert trace["coverage_candidate_layout"] == "percentile_grid"
    assert trace["coverage_multi_pass_enabled"] is True
    assert len(trace["coverage_corridors"]) == 9
    assert trace["coverage_decision_trace"] == []
    assert trace["coverage_decision_trace_count"] == 0


def test_planner_trace_facts_use_coverage_trace_snapshot() -> None:
    policy = _make_configured_policy()
    policy._ensure_coverage_corridors()

    snapshot = policy._coverage_trace_snapshot()
    facts = policy._planner_trace_facts()

    assert facts.coverage_use_env_removed_depth == snapshot.use_env_removed_depth
    assert facts.coverage_candidate_layout == snapshot.candidate_layout
    assert facts.coverage_first_dig_strategy == snapshot.first_dig_strategy
    assert facts.coverage_pass_index == snapshot.pass_index
    assert facts.coverage_multi_pass_enabled == snapshot.multi_pass_enabled
    assert facts.coverage_multi_pass_max_passes == snapshot.multi_pass_max_passes
    assert (
        facts.coverage_multi_pass_min_remaining_depth_m
        == snapshot.multi_pass_min_remaining_depth_m
    )
    assert (
        facts.coverage_first_dig_preferred_corridor_id
        == snapshot.first_dig_preferred_corridor_id
    )
    _assert_nested_equal(
        list(facts.coverage_corridors),
        list(snapshot.corridors),
    )
    _assert_nested_equal(
        list(facts.coverage_decision_trace),
        list(snapshot.decision_trace),
    )
    assert facts.coverage_terminal_stop_requested == snapshot.terminal_stop_requested
    assert facts.coverage_terminal_stop_reason == snapshot.terminal_stop_reason

    policy._record_coverage_decision_event(
        "after_trace_snapshot",
        corridor=policy._coverage_corridors[0],
        extra={"score_delta": float("nan")},
    )

    assert len(facts.coverage_decision_trace) == 0
    assert len(snapshot.decision_trace) == 0
    assert len(policy._planner_trace_facts().coverage_decision_trace) == 1


def test_planner_trace_assembly_input_mapping_preserves_shell_projection() -> None:
    coverage_trace = SimpleNamespace(
        use_env_removed_depth=True,
        candidate_layout="layout",
        first_dig_strategy="strategy",
        pass_index=1,
        multi_pass_enabled=False,
        multi_pass_max_passes=3,
        multi_pass_min_remaining_depth_m=0.04,
        first_dig_preferred_corridor_id=7,
        corridors=(),
        decision_trace=(),
        terminal_stop_requested=False,
        terminal_stop_reason="",
    )
    values = {
        "cell_entry_trace": [{"cycle_id": 2}],
        "dig_cut_planner_mode": 123,
        "dig_cut_prior_id": 456,
        "dig_cut_prior_path": Path("/tmp/prior.json"),
        "return_target_planner_enabled": 1,
        "ignored": object(),
    }

    inputs = build_primitive_planner_trace_assembly_inputs_from_mapping(
        values,
        coverage_trace=coverage_trace,
    )

    assert {key for key, _ in PRIMITIVE_PLANNER_TRACE_ASSEMBLY_FIELDS} == (
        set(values) - {"ignored"}
    )
    assert inputs.cell_entry_trace == ({"cycle_id": 2},)
    assert inputs.dig_cut_planner_mode == "123"
    assert inputs.dig_cut_prior_id == "456"
    assert inputs.dig_cut_prior_path == "/tmp/prior.json"
    assert inputs.return_target_planner_enabled is True
    assert inputs.coverage_trace is coverage_trace


def test_planner_trace_facts_from_mapping_matches_legacy_assembly_chain() -> None:
    policy = _make_configured_policy()
    policy._ensure_coverage_corridors()
    values = {
        field_name: getattr(policy, attr_name)
        for field_name, attr_name in PRIMITIVE_PLANNER_TRACE_ASSEMBLY_FIELDS
    }
    kwargs = {"coverage_trace": policy._coverage_trace_snapshot()}

    legacy = build_primitive_planner_trace_facts(
        build_primitive_planner_trace_assembly_inputs_from_mapping(
            values,
            **kwargs,
        )
    )
    combined = build_primitive_planner_trace_facts_from_mapping(values, **kwargs)

    _assert_nested_equal(
        build_primitive_planner_trace_from_facts(combined),
        build_primitive_planner_trace_from_facts(legacy),
    )


def test_planner_trace_builder_from_facts_preserves_schema_and_count() -> None:
    facts = PrimitivePlannerTraceFacts(
        cell_entry_trace=({"cycle_id": 2},),
        dig_cut_planner_mode="operator_prior",
        dig_cut_prior_id="prior_a",
        dig_cut_prior_path="/tmp/prior.json",
        return_target_planner_enabled=True,
        coverage_use_env_removed_depth=False,
        coverage_candidate_layout="percentile_grid",
        coverage_first_dig_strategy="coverage_score",
        coverage_pass_index=3,
        coverage_multi_pass_enabled=True,
        coverage_multi_pass_max_passes=4,
        coverage_multi_pass_min_remaining_depth_m=0.125,
        coverage_first_dig_preferred_corridor_id=None,
        coverage_corridors=(
            {
                "corridor_id": 7,
                "cell_id": 4,
            },
        ),
        coverage_decision_trace=(
            {"event": "select", "reason": "coverage_score"},
            {"event": "complete", "reason": "dump_mass_low"},
        ),
        coverage_terminal_stop_requested=True,
        coverage_terminal_stop_reason="dig_area_depleted",
    )

    trace = build_primitive_planner_trace_from_facts(facts)

    assert tuple(trace) == EXPECTED_PLANNER_TRACE_KEYS
    assert trace["cell_entry_trace"] == [{"cycle_id": 2}]
    assert trace["dig_cut_planner_mode"] == "operator_prior"
    assert trace["dig_cut_prior_id"] == "prior_a"
    assert trace["dig_cut_prior_path"] == "/tmp/prior.json"
    assert trace["return_target_planner_enabled"] is True
    assert trace["coverage_use_env_removed_depth"] is False
    assert trace["coverage_pass_index"] == 3
    assert trace["coverage_multi_pass_enabled"] is True
    assert trace["coverage_multi_pass_max_passes"] == 4
    assert trace["coverage_multi_pass_min_remaining_depth_m"] == 0.125
    assert trace["coverage_first_dig_preferred_corridor_id"] == -1
    assert trace["coverage_corridors"] == [{"corridor_id": 7, "cell_id": 4}]
    assert trace["coverage_decision_trace"] == [
        {"event": "select", "reason": "coverage_score"},
        {"event": "complete", "reason": "dump_mass_low"},
    ]
    assert trace["coverage_decision_trace_count"] == 2
    assert trace["coverage_terminal_stop_requested"] is True
    assert trace["coverage_terminal_stop_reason"] == "dig_area_depleted"


def test_debug_state_json_safe_after_sanitization_path() -> None:
    policy = _make_configured_policy()
    policy._ensure_coverage_corridors()
    state = policy.debug_state()
    obs = {
        "qpos": np.asarray([0.5, 0.6, 0.2, 0.1], dtype=np.float32),
        "qvel": np.zeros(4, dtype=np.float32),
        "env_state": np.zeros(64, dtype=np.float32),
        "step_id": 3,
        "sim_time_ns": 12_000_000,
    }

    planner_debug_json = build_planner_debug_json(state, obs=obs)
    assert planner_debug_json is not None
    payload = json.loads(planner_debug_json)
    assert payload["mode"] == "operator_prior_coverage"
    assert payload["selected_corridor_id"] == -1
    assert payload["token_source"] == "none"
    assert payload["pre_dig_align_enabled"] is True
    assert len(payload["corridors"]) == 9

    record = build_rollout_step_record(
        rollout_id=0,
        step_index=2,
        post_obs=obs,
        action=np.zeros(4, dtype=np.float32),
        policy_input={"goal_tokens": np.zeros(12, dtype=np.float32)},
        policy_debug=state,
        boundary_event=SimpleNamespace(
            cycle_id=0,
            mode_id=0,
            qualified_dig_start=0,
            dump_start=0,
            dump_end=0,
            pause=0,
            boundary=0,
        ),
        reward=0.0,
        reward_phase="dig",
        task_success=False,
        task_step_successes=[],
        task_step_failures=[],
        task_metrics={},
        warnings=[],
    )
    json.dumps(to_jsonable(record))
    assert record["skill_name"] == "pre_dig_align"
    assert record["dig_cut_token_source"] == "none"
    assert record["return_to_dig_start_envelope_gate_enabled"] is True
    assert record["pre_dig_align_enabled"] is True


def _make_policy(**kwargs: Any) -> PrimitivePlannerACTPolicy:
    return PrimitivePlannerACTPolicy(
        dig_policy=_ConstantPolicy(0.0),
        carry_policy=_ConstantPolicy(1.0),
        dump_policy=_ConstantPolicy(2.0),
        return_policy=_ConstantPolicy(3.0),
        boundary_detector=_FakeBoundaryDetector(),
        **kwargs,
    )


def _make_configured_policy() -> PrimitivePlannerACTPolicy:
    return _make_policy(
        cell_entry_enabled=True,
        return_to_dig_start_envelope_gate_enabled=True,
        return_to_dig_start_envelope_direct_handoff_enabled=True,
        return_to_dig_start_envelope_local_depth_tolerance_m=0.007,
        return_to_dig_start_envelope_plane_depth_mode="target_band",
        dig_cut_planner={
            "enabled": True,
            "mode": "operator_prior_coverage",
            "prior_path": str(_YULONG_DIG_CUT_PRIOR_PATH),
            "coverage": {
                "candidate_layout": "percentile_grid",
                "multi_pass_enabled": True,
            },
            "return_start_envelope": {"use_cell_prior": True},
        },
        return_target_planner={
            "enabled": True,
            "hold_token_until_skill_exit": True,
        },
        pre_dig_align={
            "enabled": True,
            "first_dig_only": True,
            "replan_after_failed_dig": True,
            "surface_guard_enabled": True,
            "entry_intent_controlled_dims": [1, 0, 1, 0],
        },
    )


def _assert_exact_type(payload: dict[str, Any], key: str, expected_type: type) -> None:
    assert type(payload[key]) is expected_type


def _assert_nested_equal(left: Any, right: Any) -> None:
    if isinstance(left, dict) and isinstance(right, dict):
        assert tuple(left) == tuple(right)
        for key in left:
            _assert_nested_equal(left[key], right[key])
        return
    if isinstance(left, list) and isinstance(right, list):
        assert len(left) == len(right)
        for left_item, right_item in zip(left, right):
            _assert_nested_equal(left_item, right_item)
        return
    if isinstance(left, float) and isinstance(right, float):
        if np.isnan(left) and np.isnan(right):
            return
    assert left == right


class _ConstantPolicy:
    def __init__(self, value: float) -> None:
        self.value = float(value)

    def reset(self) -> None:
        pass

    def predict(self, _obs: dict[str, Any]) -> np.ndarray:
        action = np.zeros(4, dtype=np.float32)
        action[0] = self.value
        return action


class _FakeBoundaryDetector:
    boundary_profile = "legacy"

    def reset(self) -> None:
        pass

    def update(self, _obs: dict[str, Any]) -> None:
        return None


_REPO_ROOT = Path(__file__).resolve().parents[1]
_YULONG_DIG_CUT_PRIOR_PATH = (
    _REPO_ROOT
    / "testbed/configs/planner_priors/yulong_operator_first_dig_cut_prior_v1.json"
)
