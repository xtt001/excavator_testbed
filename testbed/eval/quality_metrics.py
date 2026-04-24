"""Rollout quality metrics focused on digging / transport / dump behavior."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.data.schema import (
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
    ENV_STATE_MIN_DISTANCE_TO_TARGET_IDX,
)

FLAT_BUCKET_QPOS_THRESH = 0.20
FAR_DUMP_START_DISTANCE_M = 1.25
NEAR_DUMP_START_DISTANCE_M = 0.35
LOW_CARRY_EFFICIENCY_THRESH = 0.40
HIGH_RESIDUAL_BUCKET_MASS_THRESH_KG = 250.0
SHALLOW_PEAK_BUCKET_DEPTH_THRESH_M = 0.25
DIG_AREA_ESCAPE_MASS_THRESH_KG = 300.0
DIG_AREA_ESCAPE_DISTANCE_M = 0.35
DIG_AREA_ESCAPE_MIN_STREAK = 5


@dataclass(frozen=True)
class _CycleWindow:
    cycle_id: int
    qds_idx: int
    dump_start_idx: int | None
    dump_end_idx: int | None


def _safe_array_mean(values: list[float]) -> float:
    return float(np.mean(values)) if values else 0.0


def _safe_array_max(values: list[float]) -> float:
    return float(np.max(values)) if values else 0.0


def _safe_env_scalar(record: dict[str, Any], index: int) -> float | None:
    env_state = record.get("env_state")
    if env_state is None:
        return None
    arr = np.asarray(env_state, dtype=np.float32).reshape(-1)
    if index < 0 or index >= len(arr):
        return None
    value = float(arr[index])
    if not np.isfinite(value):
        return None
    return value


def _safe_bucket_qpos(record: dict[str, Any]) -> float | None:
    qpos = record.get("qpos")
    if qpos is None:
        return None
    arr = np.asarray(qpos, dtype=np.float32).reshape(-1)
    if len(arr) < 4:
        return None
    value = float(arr[3])
    if not np.isfinite(value):
        return None
    return value


def _count_failure(step_records: list[dict[str, Any]], failure_name: str) -> int:
    return int(
        sum(
            failure_name in list(record.get("task_step_failures", []))
            for record in step_records
        )
    )


def _build_cycle_windows(step_records: list[dict[str, Any]]) -> list[_CycleWindow]:
    cycle_rows: dict[int, list[int]] = {}
    for idx, record in enumerate(step_records):
        cycle_id = int(record.get("cycle_id", -1))
        if cycle_id < 0:
            continue
        cycle_rows.setdefault(cycle_id, []).append(idx)

    windows: list[_CycleWindow] = []
    for cycle_id in sorted(cycle_rows):
        indices = cycle_rows[cycle_id]
        qds_idx = next(
            (idx for idx in indices if bool(step_records[idx].get("qualified_dig_start_mask", 0))),
            None,
        )
        if qds_idx is None:
            continue
        dump_start_idx = next(
            (
                idx
                for idx in indices
                if idx >= qds_idx and bool(step_records[idx].get("dump_start_mask", 0))
            ),
            None,
        )
        dump_end_idx = next(
            (
                idx
                for idx in indices
                if idx >= qds_idx and bool(step_records[idx].get("dump_end_mask", 0))
            ),
            None,
        )
        windows.append(
            _CycleWindow(
                cycle_id=int(cycle_id),
                qds_idx=int(qds_idx),
                dump_start_idx=None if dump_start_idx is None else int(dump_start_idx),
                dump_end_idx=None if dump_end_idx is None else int(dump_end_idx),
            )
        )
    return windows


def _detect_dig_area_escape(
    step_records: list[dict[str, Any]],
    *,
    start_idx: int,
    end_idx: int,
) -> tuple[bool, int]:
    streak = 0
    escaped = False
    escape_steps = 0
    for idx in range(start_idx, end_idx + 1):
        mass = _safe_env_scalar(step_records[idx], ENV_STATE_MASS_IN_BUCKET_IDX)
        dig_distance = _safe_env_scalar(step_records[idx], ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX)
        if (
            mass is not None
            and dig_distance is not None
            and mass >= DIG_AREA_ESCAPE_MASS_THRESH_KG
            and dig_distance > DIG_AREA_ESCAPE_DISTANCE_M
        ):
            streak += 1
            escape_steps += 1
            if streak >= DIG_AREA_ESCAPE_MIN_STREAK:
                escaped = True
        else:
            streak = 0
    return escaped, escape_steps


def build_quality_summary(step_records: list[dict[str, Any]]) -> dict[str, float | int]:
    if not step_records:
        return {
            "spill_before_target_count": 0,
            "spill_before_target_rate": 0.0,
            "unsafe_target_distance_count": 0,
            "unsafe_target_distance_rate": 0.0,
            "hard_target_collision_count": 0,
            "hard_target_collision_rate": 0.0,
            "qualified_dig_start_count": 0,
            "dump_start_count": 0,
            "dump_end_count": 0,
            "qds_bucket_qpos_mean": 0.0,
            "qds_bucket_qpos_max": 0.0,
            "flat_bucket_qds_count": 0,
            "flat_bucket_qds_rate": 0.0,
            "peak_bucket_depth_mean": 0.0,
            "shallow_peak_bucket_depth_count": 0,
            "shallow_peak_bucket_depth_rate": 0.0,
            "dump_start_distance_mean": 0.0,
            "dump_start_distance_max": 0.0,
            "far_dump_start_count": 0,
            "far_dump_start_rate": 0.0,
            "near_dump_start_count": 0,
            "near_dump_start_rate": 0.0,
            "carry_efficiency_proxy_mean": 0.0,
            "low_carry_efficiency_count": 0,
            "low_carry_efficiency_rate": 0.0,
            "dump_end_residual_bucket_mass_mean": 0.0,
            "dump_end_residual_bucket_mass_max": 0.0,
            "high_residual_bucket_mass_count": 0,
            "high_residual_bucket_mass_rate": 0.0,
            "dig_area_escape_cycle_count": 0,
            "dig_area_escape_cycle_rate": 0.0,
            "dig_area_escape_step_ratio": 0.0,
            "quality_issue_count": 0,
        }

    spill_before_target_count = _count_failure(step_records, "spill_before_target")
    unsafe_target_distance_count = _count_failure(step_records, "unsafe_target_distance")
    hard_target_collision_count = _count_failure(step_records, "hard_target_collision")

    windows = _build_cycle_windows(step_records)
    qds_bucket_qpos_values: list[float] = []
    peak_bucket_depth_values: list[float] = []
    dump_start_distance_values: list[float] = []
    carry_efficiency_values: list[float] = []
    dump_end_residual_bucket_mass_values: list[float] = []

    flat_bucket_qds_count = 0
    shallow_peak_bucket_depth_count = 0
    far_dump_start_count = 0
    near_dump_start_count = 0
    low_carry_efficiency_count = 0
    high_residual_bucket_mass_count = 0
    dig_area_escape_cycle_count = 0
    dig_area_escape_step_count = 0
    dig_area_escape_window_steps = 0

    for window in windows:
        qds_record = step_records[window.qds_idx]
        qds_bucket_qpos = _safe_bucket_qpos(qds_record)
        if qds_bucket_qpos is not None:
            qds_bucket_qpos_values.append(qds_bucket_qpos)
            if qds_bucket_qpos > FLAT_BUCKET_QPOS_THRESH:
                flat_bucket_qds_count += 1

        end_idx = window.dump_end_idx if window.dump_end_idx is not None else (
            window.dump_start_idx if window.dump_start_idx is not None else window.qds_idx
        )
        bucket_depths = [
            depth
            for idx in range(window.qds_idx, end_idx + 1)
            if (depth := _safe_env_scalar(step_records[idx], ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX))
            is not None
        ]
        if bucket_depths:
            peak_depth = float(np.max(bucket_depths))
            peak_bucket_depth_values.append(peak_depth)
            if peak_depth < SHALLOW_PEAK_BUCKET_DEPTH_THRESH_M:
                shallow_peak_bucket_depth_count += 1

        if window.dump_start_idx is not None:
            dump_start_distance = _safe_env_scalar(
                step_records[window.dump_start_idx], ENV_STATE_MIN_DISTANCE_TO_TARGET_IDX
            )
            if dump_start_distance is not None:
                dump_start_distance_values.append(dump_start_distance)
                if dump_start_distance > FAR_DUMP_START_DISTANCE_M:
                    far_dump_start_count += 1
                if dump_start_distance < NEAR_DUMP_START_DISTANCE_M:
                    near_dump_start_count += 1

            mass_values = [
                mass
                for idx in range(window.qds_idx, window.dump_start_idx + 1)
                if (mass := _safe_env_scalar(step_records[idx], ENV_STATE_MASS_IN_BUCKET_IDX))
                is not None
            ]
            if mass_values:
                max_pre_dump_mass = float(np.max(mass_values))
                dump_start_mass = float(mass_values[-1])
                if max_pre_dump_mass > 1.0e-6:
                    carry_eff = float(np.clip(dump_start_mass / max_pre_dump_mass, 0.0, 1.0))
                    carry_efficiency_values.append(carry_eff)
                    if carry_eff < LOW_CARRY_EFFICIENCY_THRESH:
                        low_carry_efficiency_count += 1

            escaped, escape_steps = _detect_dig_area_escape(
                step_records,
                start_idx=window.qds_idx,
                end_idx=window.dump_start_idx,
            )
            if escaped:
                dig_area_escape_cycle_count += 1
            dig_area_escape_step_count += int(escape_steps)
            dig_area_escape_window_steps += max(0, int(window.dump_start_idx - window.qds_idx + 1))

        if window.dump_end_idx is not None:
            residual_bucket_mass = _safe_env_scalar(
                step_records[window.dump_end_idx], ENV_STATE_MASS_IN_BUCKET_IDX
            )
            if residual_bucket_mass is not None:
                dump_end_residual_bucket_mass_values.append(residual_bucket_mass)
                if residual_bucket_mass > HIGH_RESIDUAL_BUCKET_MASS_THRESH_KG:
                    high_residual_bucket_mass_count += 1

    quality_issue_count = int(
        spill_before_target_count
        + unsafe_target_distance_count
        + hard_target_collision_count
        + flat_bucket_qds_count
        + far_dump_start_count
        + near_dump_start_count
        + low_carry_efficiency_count
        + high_residual_bucket_mass_count
        + dig_area_escape_cycle_count
    )

    n_steps = max(len(step_records), 1)
    qds_count_actual = int(len(windows))
    dump_start_count_actual = int(sum(window.dump_start_idx is not None for window in windows))
    dump_end_count_actual = int(sum(window.dump_end_idx is not None for window in windows))
    qds_count = max(qds_count_actual, 1)
    dump_start_count = max(dump_start_count_actual, 1)
    dump_end_count = max(dump_end_count_actual, 1)

    return {
        "spill_before_target_count": int(spill_before_target_count),
        "spill_before_target_rate": float(spill_before_target_count) / float(n_steps),
        "unsafe_target_distance_count": int(unsafe_target_distance_count),
        "unsafe_target_distance_rate": float(unsafe_target_distance_count) / float(n_steps),
        "hard_target_collision_count": int(hard_target_collision_count),
        "hard_target_collision_rate": float(hard_target_collision_count) / float(n_steps),
        "qualified_dig_start_count": qds_count_actual,
        "dump_start_count": dump_start_count_actual,
        "dump_end_count": dump_end_count_actual,
        "qds_bucket_qpos_mean": _safe_array_mean(qds_bucket_qpos_values),
        "qds_bucket_qpos_max": _safe_array_max(qds_bucket_qpos_values),
        "flat_bucket_qds_count": int(flat_bucket_qds_count),
        "flat_bucket_qds_rate": float(flat_bucket_qds_count) / float(qds_count),
        "peak_bucket_depth_mean": _safe_array_mean(peak_bucket_depth_values),
        "shallow_peak_bucket_depth_count": int(shallow_peak_bucket_depth_count),
        "shallow_peak_bucket_depth_rate": float(shallow_peak_bucket_depth_count)
        / float(qds_count),
        "dump_start_distance_mean": _safe_array_mean(dump_start_distance_values),
        "dump_start_distance_max": _safe_array_max(dump_start_distance_values),
        "far_dump_start_count": int(far_dump_start_count),
        "far_dump_start_rate": float(far_dump_start_count) / float(dump_start_count),
        "near_dump_start_count": int(near_dump_start_count),
        "near_dump_start_rate": float(near_dump_start_count) / float(dump_start_count),
        "carry_efficiency_proxy_mean": _safe_array_mean(carry_efficiency_values),
        "low_carry_efficiency_count": int(low_carry_efficiency_count),
        "low_carry_efficiency_rate": float(low_carry_efficiency_count)
        / float(dump_start_count),
        "dump_end_residual_bucket_mass_mean": _safe_array_mean(
            dump_end_residual_bucket_mass_values
        ),
        "dump_end_residual_bucket_mass_max": _safe_array_max(
            dump_end_residual_bucket_mass_values
        ),
        "high_residual_bucket_mass_count": int(high_residual_bucket_mass_count),
        "high_residual_bucket_mass_rate": float(high_residual_bucket_mass_count)
        / float(dump_end_count),
        "dig_area_escape_cycle_count": int(dig_area_escape_cycle_count),
        "dig_area_escape_cycle_rate": float(dig_area_escape_cycle_count) / float(qds_count),
        "dig_area_escape_step_ratio": (
            float(dig_area_escape_step_count) / float(dig_area_escape_window_steps)
            if dig_area_escape_window_steps > 0
            else 0.0
        ),
        "quality_issue_count": quality_issue_count,
    }


def aggregate_quality_metrics(
    summaries: list[dict[str, float | int]],
) -> dict[str, float]:
    if not summaries:
        return {}

    def _avg(key: str) -> float:
        return float(np.mean([float(item.get(key, 0.0)) for item in summaries]))

    return {
        "avg_spill_before_target_count": _avg("spill_before_target_count"),
        "avg_spill_before_target_rate": _avg("spill_before_target_rate"),
        "avg_unsafe_target_distance_count": _avg("unsafe_target_distance_count"),
        "avg_unsafe_target_distance_rate": _avg("unsafe_target_distance_rate"),
        "avg_hard_target_collision_count": _avg("hard_target_collision_count"),
        "avg_hard_target_collision_rate": _avg("hard_target_collision_rate"),
        "avg_qds_bucket_qpos_mean": _avg("qds_bucket_qpos_mean"),
        "avg_qds_bucket_qpos_max": _avg("qds_bucket_qpos_max"),
        "avg_flat_bucket_qds_count": _avg("flat_bucket_qds_count"),
        "avg_flat_bucket_qds_rate": _avg("flat_bucket_qds_rate"),
        "avg_peak_bucket_depth_mean": _avg("peak_bucket_depth_mean"),
        "avg_shallow_peak_bucket_depth_count": _avg("shallow_peak_bucket_depth_count"),
        "avg_shallow_peak_bucket_depth_rate": _avg("shallow_peak_bucket_depth_rate"),
        "avg_dump_start_distance_mean": _avg("dump_start_distance_mean"),
        "avg_dump_start_distance_max": _avg("dump_start_distance_max"),
        "avg_far_dump_start_count": _avg("far_dump_start_count"),
        "avg_far_dump_start_rate": _avg("far_dump_start_rate"),
        "avg_near_dump_start_count": _avg("near_dump_start_count"),
        "avg_near_dump_start_rate": _avg("near_dump_start_rate"),
        "avg_carry_efficiency_proxy_mean": _avg("carry_efficiency_proxy_mean"),
        "avg_low_carry_efficiency_count": _avg("low_carry_efficiency_count"),
        "avg_low_carry_efficiency_rate": _avg("low_carry_efficiency_rate"),
        "avg_dump_end_residual_bucket_mass_mean": _avg(
            "dump_end_residual_bucket_mass_mean"
        ),
        "avg_dump_end_residual_bucket_mass_max": _avg(
            "dump_end_residual_bucket_mass_max"
        ),
        "avg_high_residual_bucket_mass_count": _avg("high_residual_bucket_mass_count"),
        "avg_high_residual_bucket_mass_rate": _avg("high_residual_bucket_mass_rate"),
        "avg_dig_area_escape_cycle_count": _avg("dig_area_escape_cycle_count"),
        "avg_dig_area_escape_cycle_rate": _avg("dig_area_escape_cycle_rate"),
        "avg_dig_area_escape_step_ratio": _avg("dig_area_escape_step_ratio"),
        "avg_quality_issue_count": _avg("quality_issue_count"),
    }
