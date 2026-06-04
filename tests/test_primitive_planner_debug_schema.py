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
from testbed.planner.cell_entry import CELL_ENTRY_TOKEN_DIM
from testbed.planner.primitive_debug import (
    build_primitive_debug_state,
    build_primitive_rollout_summary,
)
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


def test_debug_state_default_schema_is_stable() -> None:
    policy = _make_policy()

    state = policy.debug_state()

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


def test_rollout_summary_schema_is_stable() -> None:
    policy = _make_configured_policy()

    summary = policy.rollout_summary()

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
