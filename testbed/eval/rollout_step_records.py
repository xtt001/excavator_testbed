"""Rollout policy-input, step-record, and planner-debug schema helpers."""

from __future__ import annotations

import json
from typing import Any

import numpy as np

from testbed.data.schema import (
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX,
)


def build_policy_input(
    *,
    obs: dict[str, Any],
    camera_names: list[str] | tuple[str, ...],
    goal_tokens: np.ndarray | None = None,
) -> dict[str, Any]:
    """Build the per-step policy input without changing observation semantics."""
    policy_input = dict(obs)
    for cam in camera_names:
        img = obs.get("images", {}).get(cam)
        if img is not None:
            from einops import rearrange

            policy_input[f"image_{cam}"] = rearrange(
                np.array(img, dtype=np.float32) / 255.0,
                "h w c -> c h w",
            )
    if "goal_tokens" not in policy_input and goal_tokens is not None:
        policy_input["goal_tokens"] = goal_tokens
    return policy_input


def build_rollout_step_record(
    *,
    rollout_id: int,
    step_index: int,
    post_obs: dict[str, Any],
    action: np.ndarray,
    policy_input: dict[str, Any],
    policy_debug: dict[str, Any],
    boundary_event: Any,
    reward: float,
    reward_phase: str,
    task_success: bool,
    task_step_successes: list[Any],
    task_step_failures: list[Any],
    task_metrics: dict[str, Any],
    warnings: list[Any],
    sim_time_ns: int | None = None,
) -> dict[str, Any]:
    """Build one JSONL-compatible rollout step record from runtime facts."""
    return {
        "rollout_id": int(rollout_id),
        "t": int(step_index),
        "step_id": int(post_obs.get("step_id", step_index)),
        "sim_time_ns": int(
            post_obs.get(
                "sim_time_ns",
                0 if sim_time_ns is None else int(sim_time_ns),
            )
        ),
        "reward": float(reward),
        "reward_phase": str(reward_phase),
        "task_success": bool(task_success),
        "task_step_successes": list(task_step_successes),
        "task_step_failures": list(task_step_failures),
        "task_metrics": dict(task_metrics),
        "qpos": np.array(post_obs.get("qpos", []), dtype=np.float32),
        "qvel": np.array(post_obs.get("qvel", []), dtype=np.float32),
        "env_state": (
            None
            if post_obs.get("env_state") is None
            else np.array(post_obs.get("env_state"), dtype=np.float32)
        ),
        "action": np.array(action, dtype=np.float32),
        "goal_tokens": (
            None
            if policy_input.get("goal_tokens") is None
            else np.array(policy_input.get("goal_tokens"), dtype=np.float32)
        ),
        "cell_entry_token_injected": bool(
            policy_debug.get("cell_entry_token_injected", False)
        ),
        "cell_entry_selected_cell_id": int(
            policy_debug.get("cell_entry_selected_cell_id", -1)
        ),
        "cell_entry_selected_long_index": int(
            policy_debug.get("cell_entry_selected_long_index", -1)
        ),
        "cell_entry_selected_short_index": int(
            policy_debug.get("cell_entry_selected_short_index", -1)
        ),
        "cell_entry_planned_entry_x_m": float(
            policy_debug.get("cell_entry_planned_entry_x_m", np.nan)
        ),
        "cell_entry_planned_entry_y_m": float(
            policy_debug.get("cell_entry_planned_entry_y_m", np.nan)
        ),
        "cell_entry_planned_entry_z_m": float(
            policy_debug.get("cell_entry_planned_entry_z_m", np.nan)
        ),
        "cell_entry_planner_ok": bool(
            policy_debug.get("cell_entry_planner_ok", False)
        ),
        "cell_entry_audit_reason_code": int(
            policy_debug.get("cell_entry_audit_reason_code", -1)
        ),
        "cell_entry_audit_reason": str(
            policy_debug.get("cell_entry_audit_reason", "")
        ),
        "cell_entry_audit_risk_flags": int(
            policy_debug.get("cell_entry_audit_risk_flags", 0)
        ),
        "cell_entry_inside_entry_envelope": bool(
            policy_debug.get("cell_entry_inside_entry_envelope", False)
        ),
        "cell_entry_distance_to_entry_envelope_m": float(
            policy_debug.get("cell_entry_distance_to_entry_envelope_m", np.nan)
        ),
        "cell_entry_seen_cell_id": int(
            policy_debug.get("cell_entry_seen_cell_id", -1)
        ),
        "dig_cut_token_injected": bool(
            policy_debug.get("dig_cut_token_injected", False)
        ),
        "dig_cut_planner_mode": str(policy_debug.get("dig_cut_planner_mode", "")),
        "dig_cut_prior_id": str(policy_debug.get("dig_cut_prior_id", "")),
        "dig_cut_token_source": str(policy_debug.get("dig_cut_token_source", "")),
        "dig_cut_tokens": _debug_array_or_none(policy_debug, "dig_cut_tokens"),
        "dig_depth_profile_token_injected": bool(
            policy_debug.get("dig_depth_profile_token_injected", False)
        ),
        "dig_depth_profile_token_source": str(
            policy_debug.get("dig_depth_profile_token_source", "")
        ),
        "dig_depth_profile_fallback_reason": str(
            policy_debug.get("dig_depth_profile_fallback_reason", "")
        ),
        "dig_depth_profile_tokens": _debug_array_or_none(
            policy_debug,
            "dig_depth_profile_tokens",
        ),
        "return_target_token_injected": bool(
            policy_debug.get("return_target_token_injected", False)
        ),
        "return_target_token_source": str(
            policy_debug.get("return_target_token_source", "")
        ),
        "return_target_tokens": _debug_array_or_none(
            policy_debug,
            "return_target_tokens",
        ),
        "return_relocate_token_injected": bool(
            policy_debug.get("return_relocate_token_injected", False)
        ),
        "return_relocate_token_source": str(
            policy_debug.get("return_relocate_token_source", "")
        ),
        "return_relocate_tokens": _debug_array_or_none(
            policy_debug,
            "return_relocate_tokens",
        ),
        "return_start_envelope_token_injected": bool(
            policy_debug.get("return_start_envelope_token_injected", False)
        ),
        "return_start_envelope_token_source": str(
            policy_debug.get("return_start_envelope_token_source", "")
        ),
        "return_start_envelope_tokens": _debug_array_or_none(
            policy_debug,
            "return_start_envelope_tokens",
        ),
        "return_to_dig_entry_error_m": float(
            policy_debug.get("return_to_dig_entry_error_m", np.nan)
        ),
        "return_to_dig_entry_close": bool(
            policy_debug.get("return_to_dig_entry_close", True)
        ),
        "return_to_dig_start_envelope_gate_enabled": bool(
            policy_debug.get("return_to_dig_start_envelope_gate_enabled", False)
        ),
        "return_to_dig_start_envelope_ready": bool(
            policy_debug.get("return_to_dig_start_envelope_ready", True)
        ),
        "return_to_dig_start_envelope_error": float(
            policy_debug.get("return_to_dig_start_envelope_error", np.nan)
        ),
        "return_to_dig_start_envelope_checks": dict(
            policy_debug.get("return_to_dig_start_envelope_checks", {}) or {}
        ),
        "coverage_corridor_id": int(policy_debug.get("coverage_corridor_id", -1)),
        "coverage_entry_x_m": float(policy_debug.get("coverage_entry_x_m", np.nan)),
        "coverage_entry_z_m": float(policy_debug.get("coverage_entry_z_m", np.nan)),
        "coverage_exit_x_m": float(policy_debug.get("coverage_exit_x_m", np.nan)),
        "coverage_exit_z_m": float(policy_debug.get("coverage_exit_z_m", np.nan)),
        "coverage_entry_x_p05_m": float(
            policy_debug.get("coverage_entry_x_p05_m", np.nan)
        ),
        "coverage_entry_x_p50_m": float(
            policy_debug.get("coverage_entry_x_p50_m", np.nan)
        ),
        "coverage_entry_x_p95_m": float(
            policy_debug.get("coverage_entry_x_p95_m", np.nan)
        ),
        "coverage_entry_z_p05_m": float(
            policy_debug.get("coverage_entry_z_p05_m", np.nan)
        ),
        "coverage_entry_z_p50_m": float(
            policy_debug.get("coverage_entry_z_p50_m", np.nan)
        ),
        "coverage_entry_z_p95_m": float(
            policy_debug.get("coverage_entry_z_p95_m", np.nan)
        ),
        "coverage_entry_radial_p75_m": float(
            policy_debug.get("coverage_entry_radial_p75_m", np.nan)
        ),
        "coverage_entry_radial_p95_m": float(
            policy_debug.get("coverage_entry_radial_p95_m", np.nan)
        ),
        "coverage_exit_x_p05_m": float(
            policy_debug.get("coverage_exit_x_p05_m", np.nan)
        ),
        "coverage_exit_x_p50_m": float(
            policy_debug.get("coverage_exit_x_p50_m", np.nan)
        ),
        "coverage_exit_x_p95_m": float(
            policy_debug.get("coverage_exit_x_p95_m", np.nan)
        ),
        "coverage_exit_z_p05_m": float(
            policy_debug.get("coverage_exit_z_p05_m", np.nan)
        ),
        "coverage_exit_z_p50_m": float(
            policy_debug.get("coverage_exit_z_p50_m", np.nan)
        ),
        "coverage_exit_z_p95_m": float(
            policy_debug.get("coverage_exit_z_p95_m", np.nan)
        ),
        "coverage_exit_radial_p75_m": float(
            policy_debug.get("coverage_exit_radial_p75_m", np.nan)
        ),
        "coverage_exit_radial_p95_m": float(
            policy_debug.get("coverage_exit_radial_p95_m", np.nan)
        ),
        "coverage_cut_depth_peak_p05_m": float(
            policy_debug.get("coverage_cut_depth_peak_p05_m", np.nan)
        ),
        "coverage_cut_depth_peak_p50_m": float(
            policy_debug.get("coverage_cut_depth_peak_p50_m", np.nan)
        ),
        "coverage_cut_depth_peak_p95_m": float(
            policy_debug.get("coverage_cut_depth_peak_p95_m", np.nan)
        ),
        "coverage_corridor_score": float(
            policy_debug.get("coverage_corridor_score", np.nan)
        ),
        "coverage_depleted_count": int(
            policy_debug.get("coverage_depleted_count", 0)
        ),
        "coverage_last_payload_gain_kg": float(
            policy_debug.get("coverage_last_payload_gain_kg", 0.0)
        ),
        "coverage_last_effective_deposit_delta_kg": float(
            policy_debug.get("coverage_last_effective_deposit_delta_kg", 0.0)
        ),
        "coverage_global_low_productivity_streak": int(
            policy_debug.get("coverage_global_low_productivity_streak", 0)
        ),
        "coverage_terminal_stop_requested": bool(
            policy_debug.get("coverage_terminal_stop_requested", False)
        ),
        "coverage_terminal_stop_reason": str(
            policy_debug.get("coverage_terminal_stop_reason", "")
        ),
        "dig_step_count": int(policy_debug.get("dig_step_count", 0)),
        "dig_best_mass_kg": float(policy_debug.get("dig_best_mass_kg", 0.0)),
        "dig_mass_plateau_count": int(
            policy_debug.get("dig_mass_plateau_count", 0)
        ),
        "dig_to_carry_reason": str(policy_debug.get("dig_to_carry_reason", "")),
        "dig_bad_replan_count": int(policy_debug.get("dig_bad_replan_count", 0)),
        "dig_exit_guard_replan_count": int(
            policy_debug.get("dig_exit_guard_replan_count", 0)
        ),
        "pre_dig_align_enabled": bool(
            policy_debug.get("pre_dig_align_enabled", False)
        ),
        "pre_dig_align_first_dig_only": bool(
            policy_debug.get("pre_dig_align_first_dig_only", False)
        ),
        "pre_dig_align_active_for_next_dig": bool(
            policy_debug.get("pre_dig_align_active_for_next_dig", False)
        ),
        "pre_dig_align_step_count": int(
            policy_debug.get("pre_dig_align_step_count", 0)
        ),
        "pre_dig_align_hold_count": int(
            policy_debug.get("pre_dig_align_hold_count", 0)
        ),
        "pre_dig_align_timeout_count": int(
            policy_debug.get("pre_dig_align_timeout_count", 0)
        ),
        "pre_dig_align_completed_count": int(
            policy_debug.get("pre_dig_align_completed_count", 0)
        ),
        "pre_dig_align_replan_count": int(
            policy_debug.get("pre_dig_align_replan_count", 0)
        ),
        "pre_dig_align_controlled_dims": list(
            policy_debug.get("pre_dig_align_controlled_dims", [])
        ),
        "pre_dig_align_bucket_target_qpos": float(
            policy_debug.get("pre_dig_align_bucket_target_qpos", np.nan)
        ),
        "pre_dig_align_entry_error_m": float(
            policy_debug.get("pre_dig_align_entry_error_m", np.nan)
        ),
        "pre_dig_align_start_envelope_ready": bool(
            policy_debug.get("pre_dig_align_start_envelope_ready", False)
        ),
        "cycle_id": int(getattr(boundary_event, "cycle_id")),
        "mode_id": int(getattr(boundary_event, "mode_id")),
        "qualified_dig_start_mask": int(
            getattr(boundary_event, "qualified_dig_start")
        ),
        "dump_start_mask": int(getattr(boundary_event, "dump_start")),
        "dump_end_mask": int(getattr(boundary_event, "dump_end")),
        "pause_mask": int(getattr(boundary_event, "pause")),
        "boundary_mask": int(getattr(boundary_event, "boundary")),
        "warnings": list(warnings),
        "hybrid_mode": str(policy_debug.get("hybrid_mode", "")),
        "transition_submode": str(policy_debug.get("transition_submode", "")),
        "planner_cycle_index": int(policy_debug.get("planner_cycle_index", -1)),
        "planner_curr_sector_id": int(
            policy_debug.get("planner_curr_sector_id", -1)
        ),
        "planner_next_sector_id": int(
            policy_debug.get("planner_next_sector_id", -1)
        ),
        "planner_current_sector_id": int(
            policy_debug.get("planner_current_sector_id", -1)
        ),
        "planner_current_depth_class": int(
            policy_debug.get("planner_current_depth_class", -1)
        ),
        "planner_next_depth_class": int(
            policy_debug.get("planner_next_depth_class", -1)
        ),
        "planner_plan_source": str(policy_debug.get("planner_plan_source", "")),
        "planner_replan_mask": int(
            bool(policy_debug.get("planner_replan_mask", False))
        ),
        "transition_timeout": bool(policy_debug.get("transition_timeout", False)),
        "transition_collision_delta": int(
            policy_debug.get("transition_collision_delta", 0)
        ),
        "corridor_align_steps": int(policy_debug.get("corridor_align_steps", 0)),
        "wait_next_dig_steps": int(policy_debug.get("wait_next_dig_steps", 0)),
        "transition_completed": bool(
            policy_debug.get("transition_completed", False)
        ),
        "transition_source": str(policy_debug.get("transition_source", "")),
        "transition_policy_mode": str(
            policy_debug.get("transition_policy_mode", "")
        ),
        "transition_fallback_count": int(
            policy_debug.get("transition_fallback_count", 0)
        ),
        "transition_fallback_reason": str(
            policy_debug.get("transition_fallback_reason", "")
        ),
        "work_target_guard_active": bool(
            policy_debug.get("work_target_guard_active", False)
        ),
        "work_target_guard_count": int(
            policy_debug.get("work_target_guard_count", 0)
        ),
        "skill_name": str(policy_debug.get("skill_name", "")),
        "skill_id": int(policy_debug.get("skill_id", -1)),
        "skill_switch_reason": str(policy_debug.get("skill_switch_reason", "")),
        "primitive_checkpoint_path": str(
            policy_debug.get("primitive_checkpoint_path", "")
        ),
        "primitive_cycle_index": int(
            policy_debug.get("primitive_cycle_index", -1)
        ),
        "primitive_goal_curr_sector_id": int(
            policy_debug.get("primitive_goal_curr_sector_id", -1)
        ),
        "primitive_goal_next_sector_id": int(
            policy_debug.get("primitive_goal_next_sector_id", -1)
        ),
        "dump_ready_hold_count": int(policy_debug.get("dump_ready_hold_count", 0)),
        "dump_done_hold_count": int(policy_debug.get("dump_done_hold_count", 0)),
        "approach_ready_hold_count": int(
            policy_debug.get("approach_ready_hold_count", 0)
        ),
        "dump_release_ready_hold_count": int(
            policy_debug.get("dump_release_ready_hold_count", 0)
        ),
    }


def build_planner_debug_payload(
    policy_debug: dict[str, Any],
    *,
    obs: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Build the AGX/Unity planner debug payload sent alongside a rollout step."""
    mode = str(policy_debug.get("dig_cut_planner_mode", ""))
    if not mode:
        return None

    env_state = np.asarray((obs or {}).get("env_state", []), dtype=np.float32).reshape(-1)

    def _env_state_float(index: int, default: float = 0.0) -> float:
        if index < 0 or index >= env_state.size:
            return float(default)
        value = float(env_state[index])
        return value if np.isfinite(value) else float(default)

    current_tip_valid = bool(
        env_state.size > ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX
        and np.all(
            np.isfinite(
                env_state[
                    [
                        ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
                        ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX,
                        ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX,
                    ]
                ]
            )
        )
    )

    candidate_scores = []
    for item in list(policy_debug.get("coverage_candidate_scores", []) or []):
        if not isinstance(item, dict):
            continue
        candidate_scores.append(
            {
                "corridor_id": int(item.get("corridor_id", -1)),
                "cell_id": int(item.get("cell_id", -1)),
                "score": _finite_payload_float(item.get("score", 0.0)),
                "attempts": int(item.get("attempts", 0)),
                "depleted": int(item.get("depleted", 0)),
                "remaining_depth_m": _finite_payload_float(
                    item.get("remaining_depth_m", 0.0)
                ),
                "first_dig_bonus": _finite_payload_float(
                    item.get("first_dig_bonus", 0.0)
                ),
                "recent_row_penalty": _finite_payload_float(
                    item.get("recent_row_penalty", 0.0)
                ),
                "first_dig_entry_distance_m": _finite_payload_float(
                    item.get("first_dig_entry_distance_m", 0.0)
                ),
                "low_productivity_streak": int(
                    item.get("low_productivity_streak", 0)
                ),
            }
        )

    corridors = []
    for item in list(policy_debug.get("coverage_corridors", []) or []):
        if not isinstance(item, dict):
            continue
        corridors.append(
            {
                "corridor_id": int(item.get("corridor_id", -1)),
                "cell_id": int(item.get("cell_id", -1)),
                "entry_x_m": _finite_payload_float(item.get("entry_x_m", 0.0)),
                "entry_z_m": _finite_payload_float(item.get("entry_z_m", 0.0)),
                "exit_x_m": _finite_payload_float(item.get("exit_x_m", 0.0)),
                "exit_z_m": _finite_payload_float(item.get("exit_z_m", 0.0)),
                "entry_radial_p95_m": _finite_payload_float(
                    item.get("entry_radial_p95_m", 0.0)
                ),
                "exit_radial_p95_m": _finite_payload_float(
                    item.get("exit_radial_p95_m", 0.0)
                ),
                "cut_depth_peak_p95_m": _finite_payload_float(
                    item.get("cut_depth_peak_p95_m", 0.0)
                ),
                "score": _finite_payload_float(item.get("score", 0.0)),
                "attempts": int(item.get("attempts", 0)),
                "depleted": int(item.get("depleted", 0)),
                "low_productivity_streak": int(
                    item.get("low_productivity_streak", 0)
                ),
                "last_payload_gain_kg": _finite_payload_float(
                    item.get("last_payload_gain_kg", 0.0)
                ),
                "last_effective_deposit_delta_kg": _finite_payload_float(
                    item.get("last_effective_deposit_delta_kg", 0.0)
                ),
                "last_remaining_depth_m": _finite_payload_float(
                    item.get("last_remaining_depth_m", 0.0)
                ),
                "last_reason": str(item.get("last_reason", "")),
            }
        )

    return {
        "valid": True,
        "mode": mode,
        "cycle": int(policy_debug.get("primitive_cycle_index", -1)),
        "skill": str(policy_debug.get("skill_name", "")),
        "selected_corridor_id": int(policy_debug.get("coverage_corridor_id", -1)),
        "entry_x_m": _finite_debug_float(policy_debug, "coverage_entry_x_m"),
        "entry_z_m": _finite_debug_float(policy_debug, "coverage_entry_z_m"),
        "exit_x_m": _finite_debug_float(policy_debug, "coverage_exit_x_m"),
        "exit_z_m": _finite_debug_float(policy_debug, "coverage_exit_z_m"),
        "entry_x_p05_m": _finite_debug_float(policy_debug, "coverage_entry_x_p05_m"),
        "entry_x_p50_m": _finite_debug_float(policy_debug, "coverage_entry_x_p50_m"),
        "entry_x_p95_m": _finite_debug_float(policy_debug, "coverage_entry_x_p95_m"),
        "entry_z_p05_m": _finite_debug_float(policy_debug, "coverage_entry_z_p05_m"),
        "entry_z_p50_m": _finite_debug_float(policy_debug, "coverage_entry_z_p50_m"),
        "entry_z_p95_m": _finite_debug_float(policy_debug, "coverage_entry_z_p95_m"),
        "entry_radial_p75_m": _finite_debug_float(
            policy_debug,
            "coverage_entry_radial_p75_m",
        ),
        "entry_radial_p95_m": _finite_debug_float(
            policy_debug,
            "coverage_entry_radial_p95_m",
        ),
        "exit_x_p05_m": _finite_debug_float(policy_debug, "coverage_exit_x_p05_m"),
        "exit_x_p50_m": _finite_debug_float(policy_debug, "coverage_exit_x_p50_m"),
        "exit_x_p95_m": _finite_debug_float(policy_debug, "coverage_exit_x_p95_m"),
        "exit_z_p05_m": _finite_debug_float(policy_debug, "coverage_exit_z_p05_m"),
        "exit_z_p50_m": _finite_debug_float(policy_debug, "coverage_exit_z_p50_m"),
        "exit_z_p95_m": _finite_debug_float(policy_debug, "coverage_exit_z_p95_m"),
        "exit_radial_p75_m": _finite_debug_float(
            policy_debug,
            "coverage_exit_radial_p75_m",
        ),
        "exit_radial_p95_m": _finite_debug_float(
            policy_debug,
            "coverage_exit_radial_p95_m",
        ),
        "cut_depth_peak_p05_m": _finite_debug_float(
            policy_debug,
            "coverage_cut_depth_peak_p05_m",
        ),
        "cut_depth_peak_p50_m": _finite_debug_float(
            policy_debug,
            "coverage_cut_depth_peak_p50_m",
        ),
        "cut_depth_peak_p95_m": _finite_debug_float(
            policy_debug,
            "coverage_cut_depth_peak_p95_m",
        ),
        "score": _finite_debug_float(policy_debug, "coverage_corridor_score"),
        "depleted_count": int(policy_debug.get("coverage_depleted_count", 0)),
        "last_payload_gain_kg": _finite_debug_float(
            policy_debug,
            "coverage_last_payload_gain_kg",
        ),
        "last_effective_deposit_delta_kg": _finite_debug_float(
            policy_debug,
            "coverage_last_effective_deposit_delta_kg",
        ),
        "global_low_productivity_streak": int(
            policy_debug.get("coverage_global_low_productivity_streak", 0)
        ),
        "stop_reason": str(policy_debug.get("coverage_terminal_stop_reason", "")),
        "terminal_stop_requested": bool(
            policy_debug.get("coverage_terminal_stop_requested", False)
        ),
        "token_source": str(policy_debug.get("dig_cut_token_source", "")),
        "prior_id": str(policy_debug.get("dig_cut_prior_id", "")),
        "dig_cut_tokens": _finite_debug_list(policy_debug, "dig_cut_tokens"),
        "current_bucket_dig_area_x_m": _env_state_float(
            ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX
        ),
        "current_bucket_dig_area_y_m": _env_state_float(
            ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX
        ),
        "current_bucket_dig_area_z_m": _env_state_float(
            ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX
        ),
        "current_bucket_tip_valid": current_tip_valid,
        "current_bucket_tip_dig_area_x_m": _env_state_float(
            ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX
        ),
        "current_bucket_tip_dig_area_y_m": _env_state_float(
            ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX
        ),
        "current_bucket_tip_dig_area_z_m": _env_state_float(
            ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX
        ),
        "pre_dig_align_enabled": bool(
            policy_debug.get("pre_dig_align_enabled", False)
        ),
        "pre_dig_align_first_dig_only": bool(
            policy_debug.get("pre_dig_align_first_dig_only", False)
        ),
        "pre_dig_align_active_for_next_dig": bool(
            policy_debug.get("pre_dig_align_active_for_next_dig", False)
        ),
        "pre_dig_align_step_count": int(
            policy_debug.get("pre_dig_align_step_count", 0)
        ),
        "pre_dig_align_hold_count": int(
            policy_debug.get("pre_dig_align_hold_count", 0)
        ),
        "pre_dig_align_replan_count": int(
            policy_debug.get("pre_dig_align_replan_count", 0)
        ),
        "pre_dig_align_entry_error_m": _finite_debug_float(
            policy_debug,
            "pre_dig_align_entry_error_m",
        ),
        "pre_dig_align_start_envelope_ready": bool(
            policy_debug.get("pre_dig_align_start_envelope_ready", False)
        ),
        "pre_dig_align_target_qpos": _finite_debug_list(
            policy_debug,
            "pre_dig_align_target_qpos",
        ),
        "pre_dig_align_controlled_dims": list(
            policy_debug.get("pre_dig_align_controlled_dims", [])
        ),
        "pre_dig_align_bucket_target_qpos": _finite_debug_float(
            policy_debug,
            "pre_dig_align_bucket_target_qpos",
        ),
        "dig_step_count": int(policy_debug.get("dig_step_count", 0)),
        "dig_best_mass_kg": _finite_debug_float(policy_debug, "dig_best_mass_kg"),
        "dig_bad_replan_count": int(policy_debug.get("dig_bad_replan_count", 0)),
        "dig_exit_guard_replan_count": int(
            policy_debug.get("dig_exit_guard_replan_count", 0)
        ),
        "candidate_scores": candidate_scores,
        "corridors": corridors,
    }


def build_planner_debug_json(
    policy_debug: dict[str, Any],
    *,
    obs: dict[str, Any] | None = None,
) -> str | None:
    payload = build_planner_debug_payload(policy_debug, obs=obs)
    if payload is None:
        return None
    return json.dumps(payload, separators=(",", ":"), allow_nan=False)


def _debug_array_or_none(policy_debug: dict[str, Any], key: str) -> np.ndarray | None:
    value = policy_debug.get(key)
    if value is None:
        return None
    return np.array(value, dtype=np.float32)


def _finite_debug_float(
    policy_debug: dict[str, Any],
    name: str,
    default: float = 0.0,
) -> float:
    try:
        value = float(policy_debug.get(name, default))
    except (TypeError, ValueError):
        return float(default)
    return value if np.isfinite(value) else float(default)


def _finite_debug_list(policy_debug: dict[str, Any], name: str) -> list[float]:
    values = policy_debug.get(name)
    if values is None:
        return []
    arr = np.asarray(values, dtype=np.float32).reshape(-1)
    return [float(value) if np.isfinite(float(value)) else 0.0 for value in arr]


def _finite_payload_float(value: object, default: float = 0.0) -> float:
    try:
        float_value = float(value)
    except (TypeError, ValueError):
        return float(default)
    return float_value if np.isfinite(float_value) else float(default)
