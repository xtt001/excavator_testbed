"""Dig-cut plan assembly for planner-generated ACT conditioning tokens."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.data.operator_first_v2_2 import _build_dig_cut_token

Pose3D = tuple[float, float, float]


@dataclass(frozen=True)
class DigCutPlan:
    token: np.ndarray
    raw_fields: dict[str, float | int]
    source: str
    fallback_reason: str = ""


@dataclass(frozen=True)
class OperatorPriorDigCutPlanRequest:
    dig_cut_prior: dict[str, Any]
    bucket_dig_area_pose: Pose3D | None


def build_conservative_pose_dig_cut_plan(
    pose: Pose3D | None,
    *,
    source: str = "conservative_pose",
    fallback_reason: str = "",
) -> DigCutPlan:
    raw_fields = raw_fields_from_live_pose(pose)
    return DigCutPlan(
        token=_build_dig_cut_token(raw_fields),
        raw_fields=raw_fields,
        source=str(source),
        fallback_reason=str(fallback_reason),
    )


def build_operator_prior_dig_cut_plan(
    request: OperatorPriorDigCutPlanRequest,
) -> DigCutPlan:
    if not request.dig_cut_prior:
        raise ValueError("operator_prior mode requires a dig cut prior JSON.")
    fields = dict(request.dig_cut_prior.get("fields", {}))
    pose = request.bucket_dig_area_pose
    fallback_reason = ""
    if pose is None:
        entry_x = prior_percentile(fields, "entry_x_m", "p50")
        entry_y = 0.0
        entry_z = prior_percentile(fields, "entry_z_m", "p50")
        source = "operator_prior_median_pose_fallback"
        fallback_reason = "missing_bucket_dig_area_pose"
    else:
        entry_x = clamp_to_prior(fields, "entry_x_m", float(pose[0]))
        entry_y = float(pose[1])
        entry_z = clamp_to_prior(fields, "entry_z_m", float(pose[2]))
        source = "operator_prior_pose_clamped"

    dir_x = prior_percentile(fields, "cut_direction_x", "p50")
    dir_z = prior_percentile(fields, "cut_direction_z", "p50")
    norm = float(np.hypot(dir_x, dir_z))
    if norm <= 1.0e-6:
        dir_x, dir_z = -1.0, 0.0
    else:
        dir_x, dir_z = dir_x / norm, dir_z / norm
    length = prior_percentile(fields, "cut_length_m", "p50")
    exit_x = clamp_to_prior(fields, "exit_x_m", entry_x + dir_x * length)
    exit_z = clamp_to_prior(fields, "exit_z_m", entry_z + dir_z * length)

    delta_x = exit_x - entry_x
    delta_z = exit_z - entry_z
    generated_length = float(np.hypot(delta_x, delta_z))
    if generated_length > 1.0e-6:
        dir_x = delta_x / generated_length
        dir_z = delta_z / generated_length
        length = generated_length

    raw_fields = {
        "operator_entry_x_m": float(entry_x),
        "operator_entry_y_m": float(entry_y),
        "operator_entry_z_m": float(entry_z),
        "operator_exit_x_m": float(exit_x),
        "operator_exit_y_m": float(entry_y),
        "operator_exit_z_m": float(exit_z),
        "operator_cut_direction_x": float(
            clamp_to_prior(fields, "cut_direction_x", dir_x)
        ),
        "operator_cut_direction_y": 0.0,
        "operator_cut_direction_z": float(
            clamp_to_prior(fields, "cut_direction_z", dir_z)
        ),
        "operator_cut_length_m": float(
            clamp_to_prior(fields, "cut_length_m", length)
        ),
        "operator_cut_depth_peak_m": float(
            prior_percentile(fields, "cut_depth_peak_m", "p50")
        ),
        "operator_cut_payload_gain_kg": float(
            prior_percentile(fields, "payload_gain_kg", "p50")
        ),
        "operator_effective_deposit_delta_kg": float(
            prior_percentile(fields, "effective_deposit_delta_kg", "p50")
        ),
        "operator_cut_valid": 1,
    }
    return DigCutPlan(
        token=_build_dig_cut_token(raw_fields),
        raw_fields=raw_fields,
        source=source,
        fallback_reason=fallback_reason,
    )


def raw_fields_from_live_pose(pose: Pose3D | None) -> dict[str, float | int]:
    if pose is None:
        return {
            "operator_entry_x_m": 0.0,
            "operator_entry_y_m": 0.0,
            "operator_entry_z_m": 0.0,
            "operator_exit_x_m": 0.0,
            "operator_exit_y_m": 0.0,
            "operator_exit_z_m": 0.0,
            "operator_cut_direction_x": 0.0,
            "operator_cut_direction_y": 0.0,
            "operator_cut_direction_z": 0.0,
            "operator_cut_length_m": 0.0,
            "operator_cut_depth_peak_m": 0.0,
            "operator_cut_payload_gain_kg": 0.0,
            "operator_effective_deposit_delta_kg": 0.0,
            "operator_cut_valid": 0,
        }
    entry_x, entry_y, entry_z = float(pose[0]), float(pose[1]), float(pose[2])
    exit_x = entry_x - 1.2
    exit_z = entry_z
    return {
        "operator_entry_x_m": entry_x,
        "operator_entry_y_m": entry_y,
        "operator_entry_z_m": entry_z,
        "operator_exit_x_m": exit_x,
        "operator_exit_y_m": entry_y,
        "operator_exit_z_m": exit_z,
        "operator_cut_direction_x": -1.0,
        "operator_cut_direction_y": 0.0,
        "operator_cut_direction_z": 0.0,
        "operator_cut_length_m": 1.2,
        "operator_cut_depth_peak_m": 0.08,
        "operator_cut_payload_gain_kg": 55.0,
        "operator_effective_deposit_delta_kg": 55.0,
        "operator_cut_valid": 1,
    }


def prior_percentile(
    fields: dict[str, Any],
    field_name: str,
    percentile: str,
) -> float:
    try:
        return float(fields[field_name][percentile])
    except KeyError as exc:
        raise KeyError(f"Missing prior field {field_name}.{percentile}") from exc


def clamp_to_prior(fields: dict[str, Any], field_name: str, value: float) -> float:
    lo = prior_percentile(fields, field_name, "p10")
    hi = prior_percentile(fields, field_name, "p90")
    return float(np.clip(float(value), lo, hi))
