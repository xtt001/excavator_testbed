"""V2.4.5 dig depth-profile token helpers.

``dig_cut_tokens`` keep the long-standing 10D corridor contract.  The profile
token below is an add-on for dig retraining: it exposes depth/posture/outcome
semantics that are awkward to overload into the removed-depth field.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from testbed.contracts.primitive_tokens import (
    DIG_DEPTH_PROFILE_TOKEN_DIM,
    DIG_DEPTH_PROFILE_TOKEN_KEY,
    DIG_DEPTH_PROFILE_TOKEN_ORDER,
)
from testbed.data.operator_first_v2_2 import (
    DIG_CUT_DEPTH_SCALE_M,
    DIG_CUT_LENGTH_SCALE_M,
    DIG_CUT_PAYLOAD_SCALE_KG,
)


DIG_DEPTH_REFERENCE_SCALE_M = 1.5
DIG_DEPTH_PROFILE_SURFACE_OFFSET_SCALE_M = 0.75
DIG_DEPTH_PROFILE_CONTRACT_VERSION = DIG_DEPTH_PROFILE_TOKEN_KEY


def build_dig_depth_profile_token_from_metrics(
    metrics: dict[str, Any],
) -> np.ndarray:
    """Build one normalized 12D token from audit-style episode metrics."""
    cell_id = _finite_float(metrics.get("dominant_removed_depth_cell_id"), default=0.0)
    removed_depth = _first_finite_value(
        metrics.get("actual_removed_depth_peak_m"),
        metrics.get("token_depth_target_m"),
        metrics.get("operator_cut_depth_peak_m"),
    )
    payload = _first_finite_value(
        metrics.get("dig_outcome_payload_gain_kg"),
        metrics.get("operator_cut_payload_gain_kg"),
        metrics.get("token_payload_target_kg"),
    )
    effective_deposit = _first_finite_value(
        metrics.get("dig_outcome_effective_deposit_delta_kg"),
        payload,
    )
    cut_length = _first_finite_value(
        metrics.get("operator_cut_length_m"),
        metrics.get("token_cut_length_m"),
    )
    entry_reference_depth = _first_finite_value(
        _negative_or_nan(metrics.get("operator_entry_y_m")),
        metrics.get("entry_reference_depth_m"),
    )
    exit_reference_depth = _first_finite_value(
        _negative_or_nan(metrics.get("operator_exit_y_m")),
        metrics.get("peak_reference_depth_m"),
        entry_reference_depth,
    )
    peak_reference_depth = _first_finite_value(
        metrics.get("peak_reference_depth_m"),
        max(entry_reference_depth, exit_reference_depth),
    )
    peak_surface_penetration = _first_finite_value(
        metrics.get("peak_surface_penetration_m"),
        metrics.get("local_depth_peak_m"),
    )
    plane_offset = _first_finite_value(
        metrics.get("plane_minus_surface_penetration_median_m"),
        0.0,
    )
    contact_fraction = _first_finite_value(metrics.get("contact_fraction"), 0.0)
    token = np.asarray(
        [
            _clip_norm(cell_id, 5.0),
            _clip_norm(removed_depth, DIG_CUT_DEPTH_SCALE_M),
            _clip_norm(payload, DIG_CUT_PAYLOAD_SCALE_KG),
            _clip_norm(effective_deposit, DIG_CUT_PAYLOAD_SCALE_KG),
            _clip_norm(cut_length, DIG_CUT_LENGTH_SCALE_M),
            _clip_norm(entry_reference_depth, DIG_DEPTH_REFERENCE_SCALE_M),
            _clip_norm(exit_reference_depth, DIG_DEPTH_REFERENCE_SCALE_M),
            _clip_norm(peak_reference_depth, DIG_DEPTH_REFERENCE_SCALE_M),
            _clip_norm(peak_surface_penetration, DIG_DEPTH_REFERENCE_SCALE_M),
            _clip_norm(plane_offset, DIG_DEPTH_PROFILE_SURFACE_OFFSET_SCALE_M),
            float(np.clip(contact_fraction, 0.0, 1.0)),
            1.0,
        ],
        dtype=np.float32,
    )
    token[~np.isfinite(token)] = 0.0
    return token


def build_dig_depth_profile_token_from_plan(
    *,
    raw_fields: dict[str, float | int],
    cell_id: int,
    env_state: np.ndarray | None = None,
    effective_deposit_delta_kg: float | None = None,
    contact_fraction: float = 1.0,
) -> np.ndarray:
    """Build a live/planner token from the chosen dig corridor and current state."""
    entry_y = _finite_float(raw_fields.get("operator_entry_y_m"), default=float("nan"))
    exit_y = _finite_float(raw_fields.get("operator_exit_y_m"), default=float("nan"))
    if not np.isfinite(entry_y) or abs(entry_y) <= 1.0e-6:
        entry_reference_depth = _current_reference_depth(env_state)
    else:
        entry_reference_depth = max(0.0, -entry_y)
    if not np.isfinite(exit_y) or abs(exit_y) <= 1.0e-6:
        cut_depth = _finite_float(
            raw_fields.get("operator_cut_depth_peak_m"),
            default=0.0,
        )
        exit_reference_depth = max(entry_reference_depth, entry_reference_depth + cut_depth)
    else:
        exit_reference_depth = max(0.0, -exit_y)
    surface_depth = _current_surface_depth(env_state, cell_id=cell_id)
    peak_reference_depth = max(entry_reference_depth, exit_reference_depth)
    peak_surface_penetration = max(0.0, peak_reference_depth - surface_depth)
    metrics = {
        "dominant_removed_depth_cell_id": int(cell_id),
        "actual_removed_depth_peak_m": raw_fields.get("operator_cut_depth_peak_m", 0.0),
        "dig_outcome_payload_gain_kg": raw_fields.get("operator_cut_payload_gain_kg", 0.0),
        "dig_outcome_effective_deposit_delta_kg": (
            effective_deposit_delta_kg
            if effective_deposit_delta_kg is not None
            else raw_fields.get("operator_cut_payload_gain_kg", 0.0)
        ),
        "operator_cut_length_m": raw_fields.get("operator_cut_length_m", 0.0),
        "entry_reference_depth_m": entry_reference_depth,
        "peak_reference_depth_m": peak_reference_depth,
        "peak_surface_penetration_m": peak_surface_penetration,
        "operator_entry_y_m": -entry_reference_depth,
        "operator_exit_y_m": -exit_reference_depth,
        "plane_minus_surface_penetration_median_m": surface_depth,
        "contact_fraction": contact_fraction,
    }
    return build_dig_depth_profile_token_from_metrics(metrics)


def _current_reference_depth(env_state: np.ndarray | None) -> float:
    if env_state is None:
        return 0.0
    arr = np.asarray(env_state, dtype=np.float32).reshape(-1)
    for index in (29, 21):
        if arr.size > index and np.isfinite(arr[index]):
            return max(0.0, -float(arr[index]))
    return 0.0


def _current_surface_depth(env_state: np.ndarray | None, *, cell_id: int) -> float:
    if env_state is None:
        return 0.0
    arr = np.asarray(env_state, dtype=np.float32).reshape(-1)
    index = 33 + int(max(0, min(5, cell_id)))
    if arr.size > index and np.isfinite(arr[index]):
        return max(0.0, float(arr[index]))
    return 0.0


def _negative_or_nan(value: Any) -> float:
    result = _finite_float(value, default=float("nan"))
    if not np.isfinite(result):
        return float("nan")
    return max(0.0, -result)


def _first_finite_value(*values: Any) -> float:
    for value in values:
        result = _finite_float(value, default=float("nan"))
        if np.isfinite(result):
            return result
    return 0.0


def _finite_float(value: Any, *, default: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return float(default)
    if not np.isfinite(result):
        return float(default)
    return result


def _clip_norm(value: float, scale: float) -> float:
    if scale <= 0.0:
        return 0.0
    return float(np.clip(float(value) / float(scale), -1.0, 1.0))
