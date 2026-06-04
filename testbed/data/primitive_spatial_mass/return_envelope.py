"""Return start-envelope token construction for spatial-mass slicing."""

from __future__ import annotations

from typing import Any

import numpy as np

from .common import *

def find_spatial_mass_return_entry_ready(
    *,
    episode: dict[str, Any],
    start: int,
    next_start: int,
    next_work_end: int,
) -> tuple[int, dict[str, Any]]:
    """Find the first next-dig entry/envelope frame after dump completion."""
    fallback = int(next_start)
    qc: dict[str, Any] = {
        "return_end_source": "fallback_next_material_start",
        "return_entry_ready_distance_m": float(SPATIAL_MASS_RETURN_ENTRY_READY_DISTANCE_M),
        "return_entry_ready_depth_m": float(SPATIAL_MASS_RETURN_ENTRY_READY_DEPTH_M),
        "return_entry_ready_search_start_step": int(start),
        "return_entry_ready_search_end_step": int(next_work_end),
        "return_entry_ready_selected_step": int(fallback),
    }
    env_state = env_state_or_none(episode)
    if env_state is None:
        qc["return_end_source"] = "fallback_missing_env_state"
        return fallback, qc

    search_start = max(0, int(start) + 1)
    search_end = min(
        int(env_state.shape[0]),
        max(int(next_start) + 1, int(next_work_end)),
    )
    if search_end <= search_start:
        qc["return_end_source"] = "fallback_empty_search_window"
        return fallback, qc

    geometry = optional_env_col(
        env_state,
        ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX,
        default=0.0,
    )
    distance = optional_env_col(
        env_state,
        ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
        default=float("inf"),
    )
    contact = optional_env_col(
        env_state,
        ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
        default=0.0,
    )
    depth = optional_env_col(
        env_state,
        ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
        default=0.0,
    )

    indices = np.arange(search_start, search_end, dtype=np.int32)
    finite_geometry = geometry[indices] > 0.5
    finite_distance = np.isfinite(distance[indices])
    finite_depth = np.isfinite(depth[indices])
    ready = finite_geometry & (
        (finite_distance & (distance[indices] <= SPATIAL_MASS_RETURN_ENTRY_READY_DISTANCE_M))
        | (contact[indices] > 0.5)
        | (finite_depth & (depth[indices] >= SPATIAL_MASS_RETURN_ENTRY_READY_DEPTH_M))
    )
    ready_indices = indices[ready]
    if len(ready_indices) <= 0:
        return fallback, qc

    selected = int(ready_indices[0])
    qc.update(
        {
            "return_end_source": "first_next_dig_entry_ready",
            "return_entry_ready_selected_step": int(selected),
            "return_entry_ready_offset_from_dump_end": int(selected) - int(start),
            "return_entry_ready_offset_from_next_material_start": int(selected)
            - int(next_start),
            "return_entry_ready_min_distance_m": float(distance[selected]),
            "return_entry_ready_contact_mask": int(contact[selected] > 0.5),
            "return_entry_ready_local_surface_depth_m": float(depth[selected]),
            "return_entry_ready_geometry_available": int(geometry[selected] > 0.5),
        }
    )
    return selected, qc

def build_return_start_envelope_token(
    *,
    episode: dict[str, Any],
    next_start_step: int,
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    token = np.zeros(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)
    valid_mask = np.zeros(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.uint8)
    qpos = np.asarray(episode.get("qpos", []), dtype=np.float32)
    qvel = np.asarray(episode.get("qvel", []), dtype=np.float32)
    env_state = env_state_or_none(episode)
    next_start = int(next_start_step)
    qpos_valid = (
        qpos.ndim == 2
        and qpos.shape[0] > next_start
        and qpos.shape[1] >= 4
        and np.all(np.isfinite(qpos[next_start, :4]))
    )
    window_end = min(
        qpos.shape[0] if qpos.ndim == 2 else next_start,
        next_start + int(RETURN_START_ENVELOPE_WINDOW_STEPS),
    )
    qvel_valid = False
    if qpos_valid:
        qpos_window = qpos[next_start:window_end, :4]
        qpos_center = qpos[next_start, :4]
        if qpos_window.shape[0] > 1:
            half_width = 0.5 * (
                np.percentile(qpos_window, 90, axis=0)
                - np.percentile(qpos_window, 10, axis=0)
            )
        else:
            half_width = np.zeros(4, dtype=np.float32)
        half_width = np.clip(np.maximum(half_width, 0.02), 0.02, 0.35)
        token[RETURN_ENVELOPE_QPOS_CENTER_SLICE] = qpos_center.astype(np.float32)
        token[RETURN_ENVELOPE_QPOS_HALF_WIDTH_SLICE] = half_width.astype(np.float32)
        valid_mask[RETURN_ENVELOPE_QPOS_CENTER_SLICE] = 1
        valid_mask[RETURN_ENVELOPE_QPOS_HALF_WIDTH_SLICE] = 1
        if qvel.ndim == 2 and qvel.shape[0] > next_start:
            qvel_window = qvel[
                next_start : min(
                    qvel.shape[0],
                    next_start + int(RETURN_START_ENVELOPE_WINDOW_STEPS),
                ),
                :4,
            ]
            qvel_valid = bool(qvel_window.size and np.all(np.isfinite(qvel_window)))
            token[RETURN_ENVELOPE_QVEL_ABS_MAX_IDX] = (
                float(np.max(np.abs(qvel_window))) if qvel_valid else 0.0
            )
            if qvel_valid:
                valid_mask[RETURN_ENVELOPE_QVEL_ABS_MAX_IDX] = 1
    selected_env_step: int | None = None
    selected_env_source = "missing_env_state"
    geometry_available = False
    if env_state is not None and env_state.shape[0] > next_start:
        geometry = optional_env_col(
            env_state,
            ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX,
            default=0.0,
        )
        long_norm = optional_env_col(
            env_state,
            ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX,
            default=0.0,
        )
        short_norm = optional_env_col(
            env_state,
            ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX,
            default=0.0,
        )
        depth = optional_env_col(
            env_state,
            ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
            default=0.0,
        )
        contact = optional_env_col(
            env_state,
            ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
            default=0.0,
        )
        env_window_end = min(
            env_state.shape[0],
            next_start + int(RETURN_START_ENVELOPE_WINDOW_STEPS),
        )
        candidate_indices = np.arange(next_start, env_window_end, dtype=np.int32)
        finite_spatial = (
            np.isfinite(long_norm[candidate_indices])
            & np.isfinite(short_norm[candidate_indices])
            & np.isfinite(depth[candidate_indices])
        )
        geometry_candidates = candidate_indices[
            finite_spatial & (geometry[candidate_indices] > 0.5)
        ]
        finite_candidates = candidate_indices[finite_spatial]
        if len(geometry_candidates) > 0:
            selected_env_step = int(geometry_candidates[0])
            selected_env_source = "first_geometry_available_in_window"
            geometry_available = True
        elif len(finite_candidates) > 0:
            selected_env_step = int(finite_candidates[0])
            selected_env_source = "first_finite_spatial_in_window"
            geometry_available = bool(geometry[selected_env_step] > 0.5)

    if selected_env_step is not None:
        token[RETURN_ENVELOPE_LONG_NORM_IDX] = float(long_norm[selected_env_step])
        token[RETURN_ENVELOPE_SHORT_NORM_IDX] = float(short_norm[selected_env_step])
        token[RETURN_ENVELOPE_DEPTH_CENTER_IDX] = float(
            max(0.0, depth[selected_env_step])
        )
        token[RETURN_ENVELOPE_TIP_RADIUS_IDX] = 0.20
        token[RETURN_ENVELOPE_DEPTH_MIN_IDX] = float(
            max(0.0, token[RETURN_ENVELOPE_DEPTH_CENTER_IDX] - 0.08)
        )
        token[RETURN_ENVELOPE_DEPTH_MAX_IDX] = float(
            token[RETURN_ENVELOPE_DEPTH_CENTER_IDX] + 0.08
        )
        token[RETURN_ENVELOPE_CONTACT_FLAG_IDX] = float(
            contact[selected_env_step] > 0.5
        )
        valid_mask[RETURN_ENVELOPE_SPATIAL_SLICE] = 1
        valid_mask[RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX] = 1
        token[RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX] = 1.0
    elif qpos_valid:
        token[RETURN_ENVELOPE_TIP_RADIUS_IDX] = 0.20
        token[RETURN_ENVELOPE_DEPTH_MAX_IDX] = 0.08
        valid_mask[RETURN_ENVELOPE_TIP_RADIUS_IDX] = 1
        valid_mask[RETURN_ENVELOPE_DEPTH_MAX_IDX] = 1
        valid_mask[RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX] = 1
        token[RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX] = 1.0
    token[RETURN_ENVELOPE_QPOS_VALID_IDX] = float(qpos_valid)
    if qpos_valid:
        valid_mask[RETURN_ENVELOPE_QPOS_VALID_IDX] = 1
    qc = {
        "return_start_envelope_valid": bool(
            token[RETURN_ENVELOPE_QPOS_VALID_IDX] > 0.5
        ),
        "return_start_envelope_selected_step": (
            -1 if selected_env_step is None else int(selected_env_step)
        ),
        "return_start_envelope_selected_offset": (
            -1 if selected_env_step is None else int(selected_env_step) - int(next_start)
        ),
        "return_start_envelope_selected_source": selected_env_source,
        "return_start_envelope_geometry_available": bool(geometry_available),
        "return_start_envelope_window_steps": int(RETURN_START_ENVELOPE_WINDOW_STEPS),
        "return_start_envelope_valid_dim_count": int(np.sum(valid_mask > 0)),
        "return_start_envelope_long_norm": float(token[RETURN_ENVELOPE_LONG_NORM_IDX]),
        "return_start_envelope_short_norm": float(token[RETURN_ENVELOPE_SHORT_NORM_IDX]),
        "return_start_envelope_depth_center_m": float(
            token[RETURN_ENVELOPE_DEPTH_CENTER_IDX]
        ),
        "return_start_envelope_qpos_half_width_max": float(
            np.max(token[RETURN_ENVELOPE_QPOS_HALF_WIDTH_SLICE])
        ),
        "return_start_envelope_qvel_abs_max": float(
            token[RETURN_ENVELOPE_QVEL_ABS_MAX_IDX]
        ),
    }
    return token, valid_mask, qc

__all__ = [
    "find_spatial_mass_return_entry_ready",
    "build_return_start_envelope_token",
]
