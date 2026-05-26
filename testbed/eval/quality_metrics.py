"""Rollout quality metrics focused on digging / transport / dump behavior."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.data.schema import (
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
    ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_DUMP_CLEARANCE_OK_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
    ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
)
from testbed.data.operator_first_v2_2 import DIG_CUT_DEPTH_SCALE_M

FLAT_BUCKET_QPOS_THRESH = 0.20
FAR_DUMP_START_DISTANCE_M = 1.25
NEAR_DUMP_START_DISTANCE_M = 0.35
LOW_CARRY_EFFICIENCY_THRESH = 0.40
HIGH_RESIDUAL_BUCKET_MASS_THRESH_KG = 250.0
SHALLOW_PEAK_BUCKET_DEPTH_THRESH_M = 0.25
DIG_AREA_ESCAPE_MASS_THRESH_KG = 300.0
DIG_AREA_ESCAPE_DISTANCE_M = 0.35
DIG_AREA_ESCAPE_MIN_STREAK = 5
LOW_CYCLE_DEPOSITED_FRACTION_THRESH = 0.90
HIGH_CYCLE_POST_DUMP_DROP_THRESH_KG = 50.0


@dataclass(frozen=True)
class _CycleWindow:
    cycle_id: int
    qds_idx: int
    dump_start_idx: int | None
    dump_end_idx: int | None
    end_idx: int


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


def _target_geometry(record: dict[str, Any]) -> dict[str, float] | None:
    task_metrics = dict(record.get("task_metrics", {}) or {})
    if float(task_metrics.get("target_geometry_available", 1.0)) <= 0.0:
        return None
    required_metric_keys = (
        "target_horizontal_distance_m",
        "bucket_height_above_target_rim_m",
        "bucket_over_target_footprint_mask",
        "dump_clearance_ok_mask",
    )
    if all(key in task_metrics for key in required_metric_keys):
        values = {key: float(task_metrics[key]) for key in required_metric_keys}
        if all(np.isfinite(value) for value in values.values()):
            return values

    env_state = record.get("env_state")
    if env_state is None:
        return None
    arr = np.asarray(env_state, dtype=np.float32).reshape(-1)
    required_indices = (
        ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
        ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
        ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
        ENV_STATE_DUMP_CLEARANCE_OK_IDX,
    )
    if any(index >= len(arr) for index in required_indices):
        return None
    values = {
        "target_horizontal_distance_m": float(arr[ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX]),
        "bucket_height_above_target_rim_m": float(
            arr[ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX]
        ),
        "bucket_over_target_footprint_mask": float(
            arr[ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX]
        ),
        "dump_clearance_ok_mask": float(arr[ENV_STATE_DUMP_CLEARANCE_OK_IDX]),
    }
    if not all(np.isfinite(value) for value in values.values()):
        return None
    if values["target_horizontal_distance_m"] < 0.0:
        return None
    return values


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


def _safe_record_scalar(record: dict[str, Any], key: str) -> float | None:
    if key not in record:
        return None
    try:
        value = float(record[key])
    except (TypeError, ValueError):
        return None
    if not np.isfinite(value):
        return None
    return value


def _safe_sequence_scalar(value: object, index: int) -> float | None:
    if value is None:
        return None
    arr = np.asarray(value, dtype=np.float32).reshape(-1)
    if index < 0 or index >= len(arr):
        return None
    scalar = float(arr[index])
    if not np.isfinite(scalar):
        return None
    return scalar


def _bucket_tip_xz(record: dict[str, Any]) -> tuple[float, float] | None:
    tip_x = _safe_env_scalar(record, ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX)
    tip_z = _safe_env_scalar(record, ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX)
    if tip_x is not None and tip_z is not None:
        return float(tip_x), float(tip_z)
    bucket_x = _safe_env_scalar(record, ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX)
    bucket_z = _safe_env_scalar(record, ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX)
    if bucket_x is not None and bucket_z is not None:
        return float(bucket_x), float(bucket_z)
    return None


def _coverage_point(
    record: dict[str, Any],
    *,
    prefix: str,
) -> tuple[float, float] | None:
    point_x = _safe_record_scalar(record, f"coverage_{prefix}_x_m")
    point_z = _safe_record_scalar(record, f"coverage_{prefix}_z_m")
    if point_x is None or point_z is None:
        return None
    return float(point_x), float(point_z)


def _coverage_point_stats(
    record: dict[str, Any],
    *,
    prefix: str,
) -> dict[str, float | None]:
    return {
        "x_p05": _safe_record_scalar(record, f"coverage_{prefix}_x_p05_m"),
        "x_p50": _safe_record_scalar(record, f"coverage_{prefix}_x_p50_m"),
        "x_p95": _safe_record_scalar(record, f"coverage_{prefix}_x_p95_m"),
        "z_p05": _safe_record_scalar(record, f"coverage_{prefix}_z_p05_m"),
        "z_p50": _safe_record_scalar(record, f"coverage_{prefix}_z_p50_m"),
        "z_p95": _safe_record_scalar(record, f"coverage_{prefix}_z_p95_m"),
        "radial_p75": _safe_record_scalar(record, f"coverage_{prefix}_radial_p75_m"),
        "radial_p95": _safe_record_scalar(record, f"coverage_{prefix}_radial_p95_m"),
    }


def _inside_expert_box(
    point: tuple[float, float] | None,
    stats: dict[str, float | None],
) -> bool | None:
    if point is None:
        return None
    required = ("x_p05", "x_p95", "z_p05", "z_p95")
    if any(stats.get(key) is None for key in required):
        return None
    x, z = point
    return bool(
        float(stats["x_p05"]) <= x <= float(stats["x_p95"])
        and float(stats["z_p05"]) <= z <= float(stats["z_p95"])
    )


def _inside_radial_tolerance(error: float | None, tolerance: float | None) -> bool | None:
    if error is None or tolerance is None:
        return None
    if tolerance < 0.0:
        return None
    return bool(error <= tolerance)


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 1.0e-6:
        return None
    return float(numerator) / float(denominator)


def _point_distance_xz(
    record: dict[str, Any],
    target: tuple[float, float] | None,
) -> float | None:
    tip = _bucket_tip_xz(record)
    if tip is None or target is None:
        return None
    return float(np.hypot(float(tip[0]) - target[0], float(tip[1]) - target[1]))


def _exit_signed_error_m(
    record: dict[str, Any],
    entry: tuple[float, float] | None,
    exit_point: tuple[float, float] | None,
) -> float | None:
    tip = _bucket_tip_xz(record)
    if tip is None or entry is None or exit_point is None:
        return None
    entry_arr = np.asarray(entry, dtype=np.float32)
    exit_arr = np.asarray(exit_point, dtype=np.float32)
    tip_arr = np.asarray(tip, dtype=np.float32)
    direction = exit_arr - entry_arr
    length = float(np.linalg.norm(direction))
    if not np.isfinite(length) or length <= 1.0e-6:
        return None
    progress = float(np.dot(tip_arr - entry_arr, direction / length))
    return float(progress - length)


def _planned_depth_m(record: dict[str, Any]) -> float | None:
    depth_norm = _safe_sequence_scalar(record.get("dig_cut_tokens"), 7)
    valid = _safe_sequence_scalar(record.get("dig_cut_tokens"), 9)
    if depth_norm is None:
        return None
    if valid is not None and valid <= 0.5:
        return None
    return float(depth_norm) * float(DIG_CUT_DEPTH_SCALE_M)


def _dig_stage_indices(
    step_records: list[dict[str, Any]],
    window: _CycleWindow,
) -> list[int]:
    search_end = (
        int(window.dump_start_idx) - 1
        if window.dump_start_idx is not None
        else int(window.end_idx)
    )
    search_end = max(int(window.qds_idx), min(search_end, len(step_records) - 1))
    indices = list(range(int(window.qds_idx), search_end + 1))
    skill_tagged = [
        idx
        for idx in indices
        if str(step_records[idx].get("skill_name", "")) == "dig"
    ]
    if skill_tagged:
        return skill_tagged
    return indices


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
                end_idx=int(indices[-1]),
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


def _build_cycle_deposit_metrics(
    step_records: list[dict[str, Any]],
    window: _CycleWindow,
) -> dict[str, float] | None:
    if window.dump_start_idx is None:
        return None

    dump_start_idx = int(window.dump_start_idx)
    end_idx = max(int(window.end_idx), dump_start_idx)
    baseline_idx = max(int(window.qds_idx), dump_start_idx - 1)

    baseline_target_mass = _safe_env_scalar(
        step_records[baseline_idx], ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX
    )
    final_target_mass = _safe_env_scalar(
        step_records[end_idx], ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX
    )
    if baseline_target_mass is None or final_target_mass is None:
        return None

    target_series = [
        target_mass
        for idx in range(dump_start_idx, end_idx + 1)
        if (
            (target_mass := _safe_env_scalar(
                step_records[idx], ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX
            ))
            is not None
        )
    ]
    bucket_series = [
        mass
        for idx in range(int(window.qds_idx), end_idx + 1)
        if (
            (mass := _safe_env_scalar(step_records[idx], ENV_STATE_MASS_IN_BUCKET_IDX))
            is not None
        )
    ]
    pre_dump_bucket_series = [
        mass
        for idx in range(int(window.qds_idx), dump_start_idx + 1)
        if (
            (mass := _safe_env_scalar(step_records[idx], ENV_STATE_MASS_IN_BUCKET_IDX))
            is not None
        )
    ]
    post_dump_bucket_series = [
        mass
        for idx in range(dump_start_idx, end_idx + 1)
        if (
            (mass := _safe_env_scalar(step_records[idx], ENV_STATE_MASS_IN_BUCKET_IDX))
            is not None
        )
    ]
    if not target_series or not bucket_series:
        return None

    peak_target_mass = float(np.max(target_series))
    peak_bucket_mass = float(
        np.max(pre_dump_bucket_series if pre_dump_bucket_series else bucket_series)
    )
    min_post_dump_bucket_mass = float(
        np.min(post_dump_bucket_series if post_dump_bucket_series else bucket_series)
    )
    bucket_mass_out = max(0.0, peak_bucket_mass - min_post_dump_bucket_mass)
    target_deposit_peak_delta = max(0.0, peak_target_mass - baseline_target_mass)
    target_deposit_final_delta = max(0.0, final_target_mass - baseline_target_mass)
    post_dump_target_mass_drop = max(
        0.0, target_deposit_peak_delta - target_deposit_final_delta
    )
    deposited_fraction = (
        float(np.clip(target_deposit_final_delta / bucket_mass_out, 0.0, 1.0))
        if bucket_mass_out > 1.0e-6
        else 0.0
    )
    peak_deposited_fraction = (
        float(np.clip(target_deposit_peak_delta / bucket_mass_out, 0.0, 1.0))
        if bucket_mass_out > 1.0e-6
        else 0.0
    )
    return {
        "bucket_mass_out_kg": float(bucket_mass_out),
        "target_deposit_final_delta_kg": float(target_deposit_final_delta),
        "target_deposit_peak_delta_kg": float(target_deposit_peak_delta),
        "deposited_fraction": float(deposited_fraction),
        "peak_deposited_fraction": float(peak_deposited_fraction),
        "post_dump_target_mass_drop_kg": float(post_dump_target_mass_drop),
    }


def build_quality_summary(step_records: list[dict[str, Any]]) -> dict[str, float | int]:
    if not step_records:
        return {
            "spill_before_target_count": 0,
            "spill_before_target_rate": 0.0,
            "unsafe_target_distance_count": 0,
            "unsafe_target_distance_rate": 0.0,
            "hard_target_collision_count": 0,
            "hard_target_collision_rate": 0.0,
            "target_geometry_available_count": 0,
            "target_geometry_available_rate": 0.0,
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
            "dig_precision_cycle_count": 0,
            "dig_entry_error_mean_m": 0.0,
            "dig_entry_error_max_m": 0.0,
            "dig_exit_error_mean_m": 0.0,
            "dig_exit_error_max_m": 0.0,
            "dig_exit_signed_error_mean_m": 0.0,
            "dig_exit_abs_overshoot_mean_m": 0.0,
            "dig_exit_abs_overshoot_max_m": 0.0,
            "dig_entry_expert_box_hit_count": 0,
            "dig_entry_expert_box_hit_rate": 0.0,
            "dig_entry_expert_radial_p95_hit_count": 0,
            "dig_entry_expert_radial_p95_hit_rate": 0.0,
            "dig_entry_error_over_expert_p95_mean": 0.0,
            "dig_exit_expert_box_hit_count": 0,
            "dig_exit_expert_box_hit_rate": 0.0,
            "dig_exit_expert_radial_p95_hit_count": 0,
            "dig_exit_expert_radial_p95_hit_rate": 0.0,
            "dig_exit_error_over_expert_p95_mean": 0.0,
            "dig_depth_target_mean_m": 0.0,
            "dig_depth_peak_mean_m": 0.0,
            "dig_depth_error_mean_m": 0.0,
            "dig_depth_abs_error_mean_m": 0.0,
            "dig_depth_abs_error_max_m": 0.0,
            "dig_depth_expert_range_hit_count": 0,
            "dig_depth_expert_range_hit_rate": 0.0,
            "dig_depth_expert_p95_overshoot_mean_m": 0.0,
            "dig_depth_expert_p95_overshoot_max_m": 0.0,
            "dump_start_distance_mean": 0.0,
            "dump_start_distance_max": 0.0,
            "dump_start_horizontal_distance_mean": 0.0,
            "dump_start_horizontal_distance_max": 0.0,
            "dump_start_geometry_missing_count": 0,
            "dump_start_geometry_missing_rate": 0.0,
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
            "cycle_deposit_metric_count": 0,
            "cycle_deposited_fraction_mean": 0.0,
            "cycle_deposited_fraction_min": 0.0,
            "cycle_post_dump_target_mass_drop_mean_kg": 0.0,
            "cycle_post_dump_target_mass_drop_max_kg": 0.0,
            "low_cycle_deposited_fraction_count": 0,
            "low_cycle_deposited_fraction_rate": 0.0,
            "high_cycle_post_dump_drop_count": 0,
            "high_cycle_post_dump_drop_rate": 0.0,
            "quality_issue_count": 0,
        }

    spill_before_target_count = _count_failure(step_records, "spill_before_target")
    unsafe_target_distance_count = _count_failure(step_records, "unsafe_target_distance")
    hard_target_collision_count = _count_failure(step_records, "hard_target_collision")
    target_geometry_available_count = int(
        sum(_target_geometry(record) is not None for record in step_records)
    )

    windows = _build_cycle_windows(step_records)
    qds_bucket_qpos_values: list[float] = []
    peak_bucket_depth_values: list[float] = []
    entry_error_values: list[float] = []
    exit_error_values: list[float] = []
    exit_signed_error_values: list[float] = []
    exit_abs_overshoot_values: list[float] = []
    entry_expert_box_values: list[bool] = []
    entry_expert_radial_p95_values: list[bool] = []
    entry_error_over_expert_p95_values: list[float] = []
    exit_expert_box_values: list[bool] = []
    exit_expert_radial_p95_values: list[bool] = []
    exit_error_over_expert_p95_values: list[float] = []
    depth_target_values: list[float] = []
    depth_peak_values: list[float] = []
    depth_error_values: list[float] = []
    depth_abs_error_values: list[float] = []
    depth_expert_range_values: list[bool] = []
    depth_expert_p95_overshoot_values: list[float] = []
    dump_start_distance_values: list[float] = []
    carry_efficiency_values: list[float] = []
    dump_end_residual_bucket_mass_values: list[float] = []

    flat_bucket_qds_count = 0
    shallow_peak_bucket_depth_count = 0
    far_dump_start_count = 0
    near_dump_start_count = 0
    dump_start_geometry_missing_count = 0
    low_carry_efficiency_count = 0
    high_residual_bucket_mass_count = 0
    dig_area_escape_cycle_count = 0
    dig_area_escape_step_count = 0
    dig_area_escape_window_steps = 0
    cycle_deposited_fraction_values: list[float] = []
    cycle_post_dump_drop_values: list[float] = []
    low_cycle_deposited_fraction_count = 0
    high_cycle_post_dump_drop_count = 0
    per_cycle_precision_metrics: dict[str, float] = {}
    per_cycle_deposit_metrics: dict[str, float] = {}

    for window in windows:
        qds_record = step_records[window.qds_idx]
        display_cycle = int(window.cycle_id) + 1
        prefix = f"cycle{display_cycle}"
        dig_indices = _dig_stage_indices(step_records, window)
        first_dig_idx = dig_indices[0] if dig_indices else int(window.qds_idx)
        last_dig_idx = dig_indices[-1] if dig_indices else int(window.qds_idx)
        first_dig_record = step_records[first_dig_idx]
        last_dig_record = step_records[last_dig_idx]

        entry_point = _coverage_point(first_dig_record, prefix="entry")
        exit_point = _coverage_point(last_dig_record, prefix="exit")
        actual_entry_point = _bucket_tip_xz(first_dig_record)
        actual_exit_point = _bucket_tip_xz(last_dig_record)
        entry_stats = _coverage_point_stats(first_dig_record, prefix="entry")
        exit_stats = _coverage_point_stats(last_dig_record, prefix="exit")
        entry_error = _point_distance_xz(first_dig_record, entry_point)
        exit_error = _point_distance_xz(last_dig_record, exit_point)
        exit_signed_error = _exit_signed_error_m(
            last_dig_record,
            _coverage_point(last_dig_record, prefix="entry"),
            exit_point,
        )
        if entry_point is not None:
            per_cycle_precision_metrics[f"{prefix}_entry_planned_x_m"] = float(
                entry_point[0]
            )
            per_cycle_precision_metrics[f"{prefix}_entry_planned_z_m"] = float(
                entry_point[1]
            )
        if actual_entry_point is not None:
            per_cycle_precision_metrics[f"{prefix}_entry_actual_x_m"] = float(
                actual_entry_point[0]
            )
            per_cycle_precision_metrics[f"{prefix}_entry_actual_z_m"] = float(
                actual_entry_point[1]
            )
        if exit_point is not None:
            per_cycle_precision_metrics[f"{prefix}_exit_planned_x_m"] = float(
                exit_point[0]
            )
            per_cycle_precision_metrics[f"{prefix}_exit_planned_z_m"] = float(
                exit_point[1]
            )
        if actual_exit_point is not None:
            per_cycle_precision_metrics[f"{prefix}_exit_actual_x_m"] = float(
                actual_exit_point[0]
            )
            per_cycle_precision_metrics[f"{prefix}_exit_actual_z_m"] = float(
                actual_exit_point[1]
            )
        for metric_name, metric_value in entry_stats.items():
            if metric_value is not None:
                per_cycle_precision_metrics[
                    f"{prefix}_entry_expert_{metric_name}_m"
                ] = float(metric_value)
        for metric_name, metric_value in exit_stats.items():
            if metric_value is not None:
                per_cycle_precision_metrics[
                    f"{prefix}_exit_expert_{metric_name}_m"
                ] = float(metric_value)
        if entry_error is not None:
            entry_error_values.append(entry_error)
            per_cycle_precision_metrics[f"{prefix}_entry_error_m"] = float(entry_error)
            radial_p95 = entry_stats.get("radial_p95")
            radial_hit = _inside_radial_tolerance(entry_error, radial_p95)
            if radial_hit is not None:
                entry_expert_radial_p95_values.append(radial_hit)
                per_cycle_precision_metrics[
                    f"{prefix}_entry_expert_radial_p95_hit"
                ] = int(radial_hit)
            ratio = _safe_ratio(entry_error, radial_p95)
            if ratio is not None:
                entry_error_over_expert_p95_values.append(ratio)
                per_cycle_precision_metrics[
                    f"{prefix}_entry_error_over_expert_p95"
                ] = float(ratio)
        if exit_error is not None:
            exit_error_values.append(exit_error)
            per_cycle_precision_metrics[f"{prefix}_exit_error_m"] = float(exit_error)
            radial_p95 = exit_stats.get("radial_p95")
            radial_hit = _inside_radial_tolerance(exit_error, radial_p95)
            if radial_hit is not None:
                exit_expert_radial_p95_values.append(radial_hit)
                per_cycle_precision_metrics[
                    f"{prefix}_exit_expert_radial_p95_hit"
                ] = int(radial_hit)
            ratio = _safe_ratio(exit_error, radial_p95)
            if ratio is not None:
                exit_error_over_expert_p95_values.append(ratio)
                per_cycle_precision_metrics[
                    f"{prefix}_exit_error_over_expert_p95"
                ] = float(ratio)
        entry_box_hit = _inside_expert_box(actual_entry_point, entry_stats)
        if entry_box_hit is not None:
            entry_expert_box_values.append(entry_box_hit)
            per_cycle_precision_metrics[f"{prefix}_entry_expert_box_hit"] = int(
                entry_box_hit
            )
        exit_box_hit = _inside_expert_box(actual_exit_point, exit_stats)
        if exit_box_hit is not None:
            exit_expert_box_values.append(exit_box_hit)
            per_cycle_precision_metrics[f"{prefix}_exit_expert_box_hit"] = int(
                exit_box_hit
            )
        if exit_signed_error is not None:
            exit_signed_error_values.append(exit_signed_error)
            exit_abs_overshoot_values.append(abs(exit_signed_error))
            per_cycle_precision_metrics[f"{prefix}_exit_signed_error_m"] = float(
                exit_signed_error
            )
            per_cycle_precision_metrics[f"{prefix}_exit_abs_overshoot_m"] = float(
                abs(exit_signed_error)
            )

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
            planned_depth = _planned_depth_m(first_dig_record)
            expert_depth_p05 = _safe_record_scalar(
                first_dig_record,
                "coverage_cut_depth_peak_p05_m",
            )
            expert_depth_p50 = _safe_record_scalar(
                first_dig_record,
                "coverage_cut_depth_peak_p50_m",
            )
            expert_depth_p95 = _safe_record_scalar(
                first_dig_record,
                "coverage_cut_depth_peak_p95_m",
            )
            for depth_name, depth_value in (
                ("p05", expert_depth_p05),
                ("p50", expert_depth_p50),
                ("p95", expert_depth_p95),
            ):
                if depth_value is not None:
                    per_cycle_precision_metrics[
                        f"{prefix}_depth_expert_{depth_name}_m"
                    ] = float(depth_value)
            if expert_depth_p05 is not None and expert_depth_p95 is not None:
                depth_hit = bool(expert_depth_p05 <= peak_depth <= expert_depth_p95)
                depth_expert_range_values.append(depth_hit)
                per_cycle_precision_metrics[
                    f"{prefix}_depth_expert_range_hit"
                ] = int(depth_hit)
                depth_p95_overshoot = max(0.0, peak_depth - expert_depth_p95)
                depth_expert_p95_overshoot_values.append(depth_p95_overshoot)
                per_cycle_precision_metrics[
                    f"{prefix}_depth_expert_p95_overshoot_m"
                ] = float(depth_p95_overshoot)
            if planned_depth is not None:
                depth_target_values.append(planned_depth)
                depth_peak_values.append(peak_depth)
                depth_error = float(peak_depth) - float(planned_depth)
                depth_error_values.append(depth_error)
                depth_abs_error_values.append(abs(depth_error))
                per_cycle_precision_metrics[f"{prefix}_depth_target_m"] = float(
                    planned_depth
                )
                per_cycle_precision_metrics[f"{prefix}_depth_peak_m"] = float(
                    peak_depth
                )
                per_cycle_precision_metrics[f"{prefix}_depth_error_m"] = float(
                    depth_error
                )
                per_cycle_precision_metrics[f"{prefix}_depth_abs_error_m"] = float(
                    abs(depth_error)
                )
            if peak_depth < SHALLOW_PEAK_BUCKET_DEPTH_THRESH_M:
                shallow_peak_bucket_depth_count += 1

        if window.dump_start_idx is not None:
            geometry = _target_geometry(step_records[window.dump_start_idx])
            dump_start_distance = (
                None
                if geometry is None
                else float(geometry["target_horizontal_distance_m"])
            )
            if dump_start_distance is None:
                dump_start_geometry_missing_count += 1
            else:
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

        cycle_deposit_metrics = _build_cycle_deposit_metrics(step_records, window)
        if cycle_deposit_metrics is not None:
            deposited_fraction = float(cycle_deposit_metrics["deposited_fraction"])
            post_drop = float(cycle_deposit_metrics["post_dump_target_mass_drop_kg"])
            cycle_deposited_fraction_values.append(deposited_fraction)
            cycle_post_dump_drop_values.append(post_drop)
            if deposited_fraction < LOW_CYCLE_DEPOSITED_FRACTION_THRESH:
                low_cycle_deposited_fraction_count += 1
            if post_drop > HIGH_CYCLE_POST_DUMP_DROP_THRESH_KG:
                high_cycle_post_dump_drop_count += 1
            for key, value in cycle_deposit_metrics.items():
                per_cycle_deposit_metrics[f"{prefix}_{key}"] = float(value)

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
        + low_cycle_deposited_fraction_count
        + high_cycle_post_dump_drop_count
    )

    n_steps = max(len(step_records), 1)
    qds_count_actual = int(len(windows))
    dump_start_count_actual = int(sum(window.dump_start_idx is not None for window in windows))
    dump_end_count_actual = int(sum(window.dump_end_idx is not None for window in windows))
    qds_count = max(qds_count_actual, 1)
    dump_start_count = max(dump_start_count_actual, 1)
    dump_end_count = max(dump_end_count_actual, 1)
    cycle_deposit_metric_count = len(cycle_deposited_fraction_values)
    cycle_deposit_metric_denominator = max(cycle_deposit_metric_count, 1)

    summary = {
        "spill_before_target_count": int(spill_before_target_count),
        "spill_before_target_rate": float(spill_before_target_count) / float(n_steps),
        "unsafe_target_distance_count": int(unsafe_target_distance_count),
        "unsafe_target_distance_rate": float(unsafe_target_distance_count) / float(n_steps),
        "hard_target_collision_count": int(hard_target_collision_count),
        "hard_target_collision_rate": float(hard_target_collision_count) / float(n_steps),
        "target_geometry_available_count": int(target_geometry_available_count),
        "target_geometry_available_rate": float(target_geometry_available_count) / float(n_steps),
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
        "dig_precision_cycle_count": int(
            max(
                len(entry_error_values),
                len(exit_error_values),
                len(depth_abs_error_values),
            )
        ),
        "dig_entry_error_mean_m": _safe_array_mean(entry_error_values),
        "dig_entry_error_max_m": _safe_array_max(entry_error_values),
        "dig_exit_error_mean_m": _safe_array_mean(exit_error_values),
        "dig_exit_error_max_m": _safe_array_max(exit_error_values),
        "dig_exit_signed_error_mean_m": _safe_array_mean(exit_signed_error_values),
        "dig_exit_abs_overshoot_mean_m": _safe_array_mean(exit_abs_overshoot_values),
        "dig_exit_abs_overshoot_max_m": _safe_array_max(exit_abs_overshoot_values),
        "dig_entry_expert_box_hit_count": int(sum(entry_expert_box_values)),
        "dig_entry_expert_box_hit_rate": (
            float(sum(entry_expert_box_values)) / float(len(entry_expert_box_values))
            if entry_expert_box_values
            else 0.0
        ),
        "dig_entry_expert_radial_p95_hit_count": int(
            sum(entry_expert_radial_p95_values)
        ),
        "dig_entry_expert_radial_p95_hit_rate": (
            float(sum(entry_expert_radial_p95_values))
            / float(len(entry_expert_radial_p95_values))
            if entry_expert_radial_p95_values
            else 0.0
        ),
        "dig_entry_error_over_expert_p95_mean": _safe_array_mean(
            entry_error_over_expert_p95_values
        ),
        "dig_exit_expert_box_hit_count": int(sum(exit_expert_box_values)),
        "dig_exit_expert_box_hit_rate": (
            float(sum(exit_expert_box_values)) / float(len(exit_expert_box_values))
            if exit_expert_box_values
            else 0.0
        ),
        "dig_exit_expert_radial_p95_hit_count": int(
            sum(exit_expert_radial_p95_values)
        ),
        "dig_exit_expert_radial_p95_hit_rate": (
            float(sum(exit_expert_radial_p95_values))
            / float(len(exit_expert_radial_p95_values))
            if exit_expert_radial_p95_values
            else 0.0
        ),
        "dig_exit_error_over_expert_p95_mean": _safe_array_mean(
            exit_error_over_expert_p95_values
        ),
        "dig_depth_target_mean_m": _safe_array_mean(depth_target_values),
        "dig_depth_peak_mean_m": _safe_array_mean(depth_peak_values),
        "dig_depth_error_mean_m": _safe_array_mean(depth_error_values),
        "dig_depth_abs_error_mean_m": _safe_array_mean(depth_abs_error_values),
        "dig_depth_abs_error_max_m": _safe_array_max(depth_abs_error_values),
        "dig_depth_expert_range_hit_count": int(sum(depth_expert_range_values)),
        "dig_depth_expert_range_hit_rate": (
            float(sum(depth_expert_range_values))
            / float(len(depth_expert_range_values))
            if depth_expert_range_values
            else 0.0
        ),
        "dig_depth_expert_p95_overshoot_mean_m": _safe_array_mean(
            depth_expert_p95_overshoot_values
        ),
        "dig_depth_expert_p95_overshoot_max_m": _safe_array_max(
            depth_expert_p95_overshoot_values
        ),
        "dump_start_distance_mean": _safe_array_mean(dump_start_distance_values),
        "dump_start_distance_max": _safe_array_max(dump_start_distance_values),
        "dump_start_horizontal_distance_mean": _safe_array_mean(dump_start_distance_values),
        "dump_start_horizontal_distance_max": _safe_array_max(dump_start_distance_values),
        "dump_start_geometry_missing_count": int(dump_start_geometry_missing_count),
        "dump_start_geometry_missing_rate": float(dump_start_geometry_missing_count)
        / float(dump_start_count),
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
        "cycle_deposit_metric_count": int(cycle_deposit_metric_count),
        "cycle_deposited_fraction_mean": _safe_array_mean(
            cycle_deposited_fraction_values
        ),
        "cycle_deposited_fraction_min": (
            float(np.min(cycle_deposited_fraction_values))
            if cycle_deposited_fraction_values
            else 0.0
        ),
        "cycle_post_dump_target_mass_drop_mean_kg": _safe_array_mean(
            cycle_post_dump_drop_values
        ),
        "cycle_post_dump_target_mass_drop_max_kg": _safe_array_max(
            cycle_post_dump_drop_values
        ),
        "low_cycle_deposited_fraction_count": int(
            low_cycle_deposited_fraction_count
        ),
        "low_cycle_deposited_fraction_rate": (
            float(low_cycle_deposited_fraction_count)
            / float(cycle_deposit_metric_denominator)
        ),
        "high_cycle_post_dump_drop_count": int(high_cycle_post_dump_drop_count),
        "high_cycle_post_dump_drop_rate": (
            float(high_cycle_post_dump_drop_count)
            / float(cycle_deposit_metric_denominator)
        ),
        "quality_issue_count": quality_issue_count,
    }
    summary.update(per_cycle_precision_metrics)
    summary.update(per_cycle_deposit_metrics)
    return summary


def aggregate_quality_metrics(
    summaries: list[dict[str, float | int]],
) -> dict[str, float]:
    if not summaries:
        return {}

    def _avg(key: str) -> float:
        return float(np.mean([float(item.get(key, 0.0)) for item in summaries]))

    metrics = {
        "avg_spill_before_target_count": _avg("spill_before_target_count"),
        "avg_spill_before_target_rate": _avg("spill_before_target_rate"),
        "avg_unsafe_target_distance_count": _avg("unsafe_target_distance_count"),
        "avg_unsafe_target_distance_rate": _avg("unsafe_target_distance_rate"),
        "avg_hard_target_collision_count": _avg("hard_target_collision_count"),
        "avg_hard_target_collision_rate": _avg("hard_target_collision_rate"),
        "avg_target_geometry_available_count": _avg("target_geometry_available_count"),
        "avg_target_geometry_available_rate": _avg("target_geometry_available_rate"),
        "avg_qds_bucket_qpos_mean": _avg("qds_bucket_qpos_mean"),
        "avg_qds_bucket_qpos_max": _avg("qds_bucket_qpos_max"),
        "avg_flat_bucket_qds_count": _avg("flat_bucket_qds_count"),
        "avg_flat_bucket_qds_rate": _avg("flat_bucket_qds_rate"),
        "avg_peak_bucket_depth_mean": _avg("peak_bucket_depth_mean"),
        "avg_shallow_peak_bucket_depth_count": _avg("shallow_peak_bucket_depth_count"),
        "avg_shallow_peak_bucket_depth_rate": _avg("shallow_peak_bucket_depth_rate"),
        "avg_dig_precision_cycle_count": _avg("dig_precision_cycle_count"),
        "avg_dig_entry_error_mean_m": _avg("dig_entry_error_mean_m"),
        "avg_dig_entry_error_max_m": _avg("dig_entry_error_max_m"),
        "avg_dig_exit_error_mean_m": _avg("dig_exit_error_mean_m"),
        "avg_dig_exit_error_max_m": _avg("dig_exit_error_max_m"),
        "avg_dig_exit_signed_error_mean_m": _avg("dig_exit_signed_error_mean_m"),
        "avg_dig_exit_abs_overshoot_mean_m": _avg(
            "dig_exit_abs_overshoot_mean_m"
        ),
        "avg_dig_exit_abs_overshoot_max_m": _avg("dig_exit_abs_overshoot_max_m"),
        "avg_dig_entry_expert_box_hit_count": _avg(
            "dig_entry_expert_box_hit_count"
        ),
        "avg_dig_entry_expert_box_hit_rate": _avg("dig_entry_expert_box_hit_rate"),
        "avg_dig_entry_expert_radial_p95_hit_count": _avg(
            "dig_entry_expert_radial_p95_hit_count"
        ),
        "avg_dig_entry_expert_radial_p95_hit_rate": _avg(
            "dig_entry_expert_radial_p95_hit_rate"
        ),
        "avg_dig_entry_error_over_expert_p95_mean": _avg(
            "dig_entry_error_over_expert_p95_mean"
        ),
        "avg_dig_exit_expert_box_hit_count": _avg(
            "dig_exit_expert_box_hit_count"
        ),
        "avg_dig_exit_expert_box_hit_rate": _avg("dig_exit_expert_box_hit_rate"),
        "avg_dig_exit_expert_radial_p95_hit_count": _avg(
            "dig_exit_expert_radial_p95_hit_count"
        ),
        "avg_dig_exit_expert_radial_p95_hit_rate": _avg(
            "dig_exit_expert_radial_p95_hit_rate"
        ),
        "avg_dig_exit_error_over_expert_p95_mean": _avg(
            "dig_exit_error_over_expert_p95_mean"
        ),
        "avg_dig_depth_target_mean_m": _avg("dig_depth_target_mean_m"),
        "avg_dig_depth_peak_mean_m": _avg("dig_depth_peak_mean_m"),
        "avg_dig_depth_error_mean_m": _avg("dig_depth_error_mean_m"),
        "avg_dig_depth_abs_error_mean_m": _avg("dig_depth_abs_error_mean_m"),
        "avg_dig_depth_abs_error_max_m": _avg("dig_depth_abs_error_max_m"),
        "avg_dig_depth_expert_range_hit_count": _avg(
            "dig_depth_expert_range_hit_count"
        ),
        "avg_dig_depth_expert_range_hit_rate": _avg(
            "dig_depth_expert_range_hit_rate"
        ),
        "avg_dig_depth_expert_p95_overshoot_mean_m": _avg(
            "dig_depth_expert_p95_overshoot_mean_m"
        ),
        "avg_dig_depth_expert_p95_overshoot_max_m": _avg(
            "dig_depth_expert_p95_overshoot_max_m"
        ),
        "avg_dump_start_distance_mean": _avg("dump_start_distance_mean"),
        "avg_dump_start_distance_max": _avg("dump_start_distance_max"),
        "avg_dump_start_horizontal_distance_mean": _avg(
            "dump_start_horizontal_distance_mean"
        ),
        "avg_dump_start_horizontal_distance_max": _avg(
            "dump_start_horizontal_distance_max"
        ),
        "avg_dump_start_geometry_missing_count": _avg(
            "dump_start_geometry_missing_count"
        ),
        "avg_dump_start_geometry_missing_rate": _avg(
            "dump_start_geometry_missing_rate"
        ),
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
        "avg_cycle_deposit_metric_count": _avg("cycle_deposit_metric_count"),
        "avg_cycle_deposited_fraction_mean": _avg("cycle_deposited_fraction_mean"),
        "avg_cycle_deposited_fraction_min": _avg("cycle_deposited_fraction_min"),
        "avg_cycle_post_dump_target_mass_drop_mean_kg": _avg(
            "cycle_post_dump_target_mass_drop_mean_kg"
        ),
        "avg_cycle_post_dump_target_mass_drop_max_kg": _avg(
            "cycle_post_dump_target_mass_drop_max_kg"
        ),
        "avg_low_cycle_deposited_fraction_count": _avg(
            "low_cycle_deposited_fraction_count"
        ),
        "avg_low_cycle_deposited_fraction_rate": _avg(
            "low_cycle_deposited_fraction_rate"
        ),
        "avg_high_cycle_post_dump_drop_count": _avg("high_cycle_post_dump_drop_count"),
        "avg_high_cycle_post_dump_drop_rate": _avg("high_cycle_post_dump_drop_rate"),
        "avg_cycle1_deposited_fraction": _avg("cycle1_deposited_fraction"),
        "avg_cycle2_deposited_fraction": _avg("cycle2_deposited_fraction"),
        "avg_cycle3_deposited_fraction": _avg("cycle3_deposited_fraction"),
        "avg_cycle1_post_dump_target_mass_drop_kg": _avg(
            "cycle1_post_dump_target_mass_drop_kg"
        ),
        "avg_cycle2_post_dump_target_mass_drop_kg": _avg(
            "cycle2_post_dump_target_mass_drop_kg"
        ),
        "avg_cycle3_post_dump_target_mass_drop_kg": _avg(
            "cycle3_post_dump_target_mass_drop_kg"
        ),
        "avg_quality_issue_count": _avg("quality_issue_count"),
    }
    for cycle_idx in range(1, 31):
        for suffix in (
            "entry_error_m",
            "entry_planned_x_m",
            "entry_planned_z_m",
            "entry_actual_x_m",
            "entry_actual_z_m",
            "entry_expert_x_p05_m",
            "entry_expert_x_p50_m",
            "entry_expert_x_p95_m",
            "entry_expert_z_p05_m",
            "entry_expert_z_p50_m",
            "entry_expert_z_p95_m",
            "entry_expert_radial_p75_m",
            "entry_expert_radial_p95_m",
            "entry_expert_box_hit",
            "entry_expert_radial_p95_hit",
            "entry_error_over_expert_p95",
            "exit_error_m",
            "exit_planned_x_m",
            "exit_planned_z_m",
            "exit_actual_x_m",
            "exit_actual_z_m",
            "exit_expert_x_p05_m",
            "exit_expert_x_p50_m",
            "exit_expert_x_p95_m",
            "exit_expert_z_p05_m",
            "exit_expert_z_p50_m",
            "exit_expert_z_p95_m",
            "exit_expert_radial_p75_m",
            "exit_expert_radial_p95_m",
            "exit_expert_box_hit",
            "exit_expert_radial_p95_hit",
            "exit_error_over_expert_p95",
            "exit_signed_error_m",
            "exit_abs_overshoot_m",
            "depth_target_m",
            "depth_peak_m",
            "depth_error_m",
            "depth_abs_error_m",
            "depth_expert_p05_m",
            "depth_expert_p50_m",
            "depth_expert_p95_m",
            "depth_expert_range_hit",
            "depth_expert_p95_overshoot_m",
        ):
            key = f"cycle{cycle_idx}_{suffix}"
            metrics[f"avg_{key}"] = _avg(key)
    return metrics
