"""Helpers for saving per-rollout timestep logs and summaries."""

from __future__ import annotations

import collections
import datetime
import json
from pathlib import Path
from typing import Any

import numpy as np


def to_jsonable(value: Any) -> Any:
    """Convert numpy-heavy rollout data into JSON-serialisable values."""
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def write_json(path: Path | str, payload: dict[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(to_jsonable(payload), f, indent=2)
    return path


def write_jsonl(path: Path | str, rows: list[dict[str, Any]]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for row in rows:
            f.write(json.dumps(to_jsonable(row), separators=(",", ":")))
            f.write("\n")
    return path


def build_rollout_summary(
    *,
    rollout_id: int,
    success: bool,
    rewards: list[float],
    step_records: list[dict[str, Any]],
    video_path: str = "",
) -> dict[str, Any]:
    failure_counts: collections.Counter[str] = collections.Counter()
    first_success_step: int | None = None
    first_failure_step: int | None = None

    for record in step_records:
        step_index = int(record.get("t", 0))
        task_success = bool(record.get("task_success", False))
        task_step_successes = list(record.get("task_step_successes", []))
        task_step_failures = list(record.get("task_step_failures", []))

        if first_success_step is None and (task_success or task_step_successes):
            first_success_step = step_index
        if task_step_failures and first_failure_step is None:
            first_failure_step = step_index
        failure_counts.update(task_step_failures)

    return {
        "rollout_id": int(rollout_id),
        "generated_at": datetime.datetime.utcnow().isoformat(),
        "success": bool(success),
        "episode_return": float(np.sum(rewards)) if rewards else 0.0,
        "episode_len": len(rewards),
        "highest_reward": float(max(rewards)) if rewards else 0.0,
        "first_success_event_step": first_success_step,
        "first_success_step": first_success_step,
        "first_failure_step": first_failure_step,
        "failure_counts": dict(sorted(failure_counts.items())),
        "video_path": str(video_path),
    }


def build_rollout_manifest(
    *,
    task_name: str,
    policy_name: str,
    ckpt_path: str,
    rollout_log_dir: Path | str,
    rollouts: list[dict[str, Any]],
) -> dict[str, Any]:
    success_counts_by_mode: dict[str, int] = {}
    success_rates_by_mode: dict[str, float] = {}
    continuity_means: dict[str, float] = {}
    multicycle_means: dict[str, float] = {}
    hybrid_means: dict[str, float] = {}
    planner_means: dict[str, float] = {}
    quality_means: dict[str, float] = {}
    planner_sector_sequences: list[list[str]] = []
    if rollouts:
        success_keys = [
            "success",
            "legacy_success",
            "final_hold_success",
            "strict_final_hold_success",
            "dump_complete_final_hold_success",
            "strict_dump_complete_success",
        ]
        n_rollouts = len(rollouts)
        for key in success_keys:
            if key not in rollouts[0]:
                continue
            count = int(sum(bool(rollout.get(key, False)) for rollout in rollouts))
            success_counts_by_mode[key] = count
            success_rates_by_mode[key] = count / n_rollouts if n_rollouts > 0 else 0.0
        continuity_keys = [
            "pause_ratio",
            "mean_action_jerk",
            "boundary_jump_l1",
            "boundary_jump_l2",
        ]
        for key in continuity_keys:
            values = [float(rollout.get(key, 0.0)) for rollout in rollouts if key in rollout]
            if values:
                continuity_means[key] = float(np.mean(values))
        multicycle_keys = [
            "dump_to_next_dig_gap_steps",
            "completed_dump_count",
            "cycle1_success",
            "cycle2_success",
            "cycle3_success",
        ]
        for key in multicycle_keys:
            values = [float(rollout.get(key, 0.0)) for rollout in rollouts if key in rollout]
            if values:
                multicycle_means[key] = float(np.mean(values))
        hybrid_keys = [
            "transition_timeout_count",
            "transition_collision_rate",
            "avg_corridor_align_steps",
            "avg_wait_next_dig_steps",
            "completed_transition_count",
            "work_target_guard_count",
        ]
        for key in hybrid_keys:
            values = [float(rollout.get(key, 0.0)) for rollout in rollouts if key in rollout]
            if values:
                hybrid_means[key] = float(np.mean(values))
        planner_keys = [
            "planner_replan_count",
            "planner_blocked_sector_count",
            "planner_done_sector_count",
        ]
        for key in planner_keys:
            values = [float(rollout.get(key, 0.0)) for rollout in rollouts if key in rollout]
            if values:
                planner_means[key] = float(np.mean(values))
        planner_sector_sequences = [
            list(rollout.get("planner_sector_sequence", []))
            for rollout in rollouts
            if rollout.get("planner_sector_sequence")
        ]
        quality_keys = [
            "spill_before_target_count",
            "spill_before_target_rate",
            "unsafe_target_distance_count",
            "unsafe_target_distance_rate",
            "hard_target_collision_count",
            "hard_target_collision_rate",
            "qds_bucket_qpos_mean",
            "qds_bucket_qpos_max",
            "flat_bucket_qds_count",
            "flat_bucket_qds_rate",
            "peak_bucket_depth_mean",
            "shallow_peak_bucket_depth_count",
            "shallow_peak_bucket_depth_rate",
            "dig_precision_cycle_count",
            "dig_entry_error_mean_m",
            "dig_entry_error_max_m",
            "dig_exit_error_mean_m",
            "dig_exit_error_max_m",
            "dig_exit_signed_error_mean_m",
            "dig_exit_abs_overshoot_mean_m",
            "dig_exit_abs_overshoot_max_m",
            "dig_depth_target_mean_m",
            "dig_depth_peak_mean_m",
            "dig_depth_error_mean_m",
            "dig_depth_abs_error_mean_m",
            "dig_depth_abs_error_max_m",
            "dump_start_distance_mean",
            "dump_start_distance_max",
            "far_dump_start_count",
            "far_dump_start_rate",
            "near_dump_start_count",
            "near_dump_start_rate",
            "carry_efficiency_proxy_mean",
            "low_carry_efficiency_count",
            "low_carry_efficiency_rate",
            "dump_end_residual_bucket_mass_mean",
            "dump_end_residual_bucket_mass_max",
            "high_residual_bucket_mass_count",
            "high_residual_bucket_mass_rate",
            "dig_area_escape_cycle_count",
            "dig_area_escape_cycle_rate",
            "dig_area_escape_step_ratio",
            "cycle_deposit_metric_count",
            "cycle_deposited_fraction_mean",
            "cycle_deposited_fraction_min",
            "cycle_post_dump_target_mass_drop_mean_kg",
            "cycle_post_dump_target_mass_drop_max_kg",
            "low_cycle_deposited_fraction_count",
            "low_cycle_deposited_fraction_rate",
            "high_cycle_post_dump_drop_count",
            "high_cycle_post_dump_drop_rate",
            "cycle1_deposited_fraction",
            "cycle2_deposited_fraction",
            "cycle3_deposited_fraction",
            "cycle1_post_dump_target_mass_drop_kg",
            "cycle2_post_dump_target_mass_drop_kg",
            "cycle3_post_dump_target_mass_drop_kg",
            "quality_issue_count",
        ]
        for cycle_idx in range(1, 31):
            for suffix in (
                "entry_error_m",
                "exit_error_m",
                "exit_signed_error_m",
                "exit_abs_overshoot_m",
                "depth_target_m",
                "depth_peak_m",
                "depth_error_m",
                "depth_abs_error_m",
            ):
                quality_keys.append(f"cycle{cycle_idx}_{suffix}")
        for key in quality_keys:
            values = [float(rollout.get(key, 0.0)) for rollout in rollouts if key in rollout]
            if values:
                quality_means[key] = float(np.mean(values))

    return {
        "generated_at": datetime.datetime.utcnow().isoformat(),
        "task_name": task_name,
        "policy_name": policy_name,
        "ckpt_path": str(ckpt_path),
        "rollout_log_dir": str(rollout_log_dir),
        "n_rollouts": len(rollouts),
        "success_counts_by_mode": success_counts_by_mode,
        "success_rates_by_mode": success_rates_by_mode,
        "continuity_means": continuity_means,
        "multicycle_means": multicycle_means,
        "hybrid_means": hybrid_means,
        "planner_means": planner_means,
        "quality_means": quality_means,
        "planner_sector_sequences": planner_sector_sequences,
        "rollouts": [to_jsonable(rollout) for rollout in rollouts],
    }
