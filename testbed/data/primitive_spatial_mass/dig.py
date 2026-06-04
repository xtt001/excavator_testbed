"""Dig-window detection for spatial-mass primitive slicing."""

from __future__ import annotations

from typing import Any

import numpy as np

from .common import *

def find_spatial_mass_dig_start(
    *,
    episode: dict[str, Any],
    start: int,
    end: int,
) -> tuple[int, dict[str, Any]]:
    env_state = env_state_or_none(episode)
    if env_state is None:
        return int(start), {
            "dig_start_step": int(start),
            "dig_start_source": "cycle_start_missing_env_state",
        }
    search_start = max(0, int(start))
    search_end = min(int(end), len(env_state))
    if search_end <= search_start:
        return int(start), {"dig_start_step": int(start), "dig_start_source": "empty_window"}
    geometry = optional_env_col(
        env_state,
        ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX,
        default=1.0,
    )
    contact = optional_env_col(
        env_state,
        ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
        default=0.0,
    )
    depth = optional_env_col(
        env_state,
        ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
        default=float("nan"),
    )
    if not np.any(np.isfinite(depth)):
        depth = optional_env_col(env_state, 8, default=0.0)
    mask = (
        (geometry > 0.5)
        & ((contact > 0.5) | (np.nan_to_num(depth, nan=0.0) > 0.005))
    )
    indices = np.flatnonzero(mask[search_start:search_end])
    if len(indices) <= 0:
        return int(start), {
            "dig_start_step": int(start),
            "dig_start_source": "cycle_start_no_contact_depth_match",
        }
    dig_start = int(search_start + indices[0])
    return dig_start, {
        "dig_start_step": int(dig_start),
        "dig_start_source": "first_dig_contact_or_depth",
        "dig_start_depth_m": float(np.nan_to_num(depth[dig_start], nan=0.0)),
        "dig_start_contact_mask": int(contact[dig_start] > 0.5),
    }

def find_spatial_mass_dig_end(
    *,
    episode: dict[str, Any],
    start: int,
    end: int,
) -> tuple[int, dict[str, Any]]:
    start = int(start)
    end = int(end)
    qc: dict[str, Any] = {
        "dig_end_search_start_step": int(start),
        "dig_end_search_end_step": int(end),
        "dig_end_source": "fallback_search_end",
        "dig_mass_gain_eps_kg": float(SPATIAL_MASS_DIG_MASS_GAIN_EPS_KG),
        "dig_peak_gain_fraction": float(SPATIAL_MASS_DIG_PEAK_GAIN_FRACTION),
        "dig_near_peak_tol_kg": float(SPATIAL_MASS_DIG_NEAR_PEAK_TOL_KG),
        "dig_future_gain_tol_kg": float(SPATIAL_MASS_DIG_FUTURE_GAIN_TOL_KG),
        "dig_mass_plateau_steps": int(SPATIAL_MASS_DIG_MASS_PLATEAU_STEPS),
        "dig_exit_hold_steps": int(SPATIAL_MASS_DIG_EXIT_HOLD_STEPS),
    }
    if end <= start + 1:
        qc["dig_end_selected_step"] = int(end)
        qc["dig_end_source"] = "empty_search_window"
        return int(end), qc

    env_state = env_state_or_none(episode)
    if env_state is None:
        selected = int(min(end, start + 120))
        qc["dig_end_selected_step"] = int(selected)
        qc["dig_end_source"] = "fallback_missing_env_state"
        return selected, qc

    n_steps = int(env_state.shape[0])
    search_start = max(0, min(start, n_steps - 1))
    search_end = max(search_start + 1, min(end, n_steps))
    mass = optional_env_col(env_state, ENV_STATE_MASS_IN_BUCKET_IDX, default=0.0)
    departed = spatial_mass_dig_area_departed_mask(env_state)

    mass_delta = np.diff(mass, prepend=mass[0])
    growth_indices = np.flatnonzero(
        mass_delta[search_start + 1 : search_end] >= SPATIAL_MASS_DIG_MASS_GAIN_EPS_KG
    )
    if len(growth_indices) > 0:
        last_growth = int(search_start + 1 + growth_indices[-1])
        first_growth = int(search_start + 1 + growth_indices[0])
    else:
        last_growth = int(search_start)
        first_growth = -1
    start_mass = float(mass[search_start])
    peak_mass = float(np.nanmax(mass[search_start:search_end]))
    total_gain = float(max(0.0, peak_mass - start_mass))
    near_peak_tolerance = max(
        float(SPATIAL_MASS_DIG_NEAR_PEAK_TOL_KG),
        total_gain * (1.0 - float(SPATIAL_MASS_DIG_PEAK_GAIN_FRACTION)),
    )
    future_gain_tolerance = max(
        float(SPATIAL_MASS_DIG_FUTURE_GAIN_TOL_KG),
        total_gain * 0.03,
    )
    qc.update(
        {
            "dig_first_mass_growth_step": int(first_growth),
            "dig_last_mass_growth_step": int(last_growth),
            "dig_start_bucket_mass_kg": start_mass,
            "dig_peak_bucket_mass_kg": peak_mass,
            "dig_total_mass_gain_kg": total_gain,
            "dig_near_peak_tolerance_kg": float(near_peak_tolerance),
            "dig_future_gain_tolerance_kg": float(future_gain_tolerance),
        }
    )

    hold = max(1, int(SPATIAL_MASS_DIG_EXIT_HOLD_STEPS))
    plateau_steps = max(0, int(SPATIAL_MASS_DIG_MASS_PLATEAU_STEPS))
    candidate_start = search_start + 1
    latest_candidate = max(candidate_start, search_end - hold)
    for idx in range(candidate_start, latest_candidate + 1):
        exit_window = departed[idx : idx + hold]
        if len(exit_window) < hold or not bool(np.all(exit_window)):
            continue
        past_peak = float(np.nanmax(mass[search_start : idx + 1]))
        if total_gain > SPATIAL_MASS_DIG_NEAR_PEAK_TOL_KG and past_peak < (
            peak_mass - near_peak_tolerance
        ):
            continue
        plateau_end = min(search_end, idx + plateau_steps + 1)
        future_peak = float(np.nanmax(mass[idx:plateau_end])) if plateau_end > idx else float(mass[idx])
        future_gain = float(max(0.0, future_peak - float(mass[idx])))
        if future_gain > future_gain_tolerance:
            continue
        qc.update(
            {
                "dig_end_source": "mass_plateau_and_dig_area_departure",
                "dig_end_selected_step": int(idx),
                "dig_end_departure_hold_end_step": int(idx + hold),
                "dig_end_past_peak_bucket_mass_kg": float(past_peak),
                "dig_end_future_gain_kg": float(future_gain),
                "dig_end_mass_at_start_kg": start_mass,
                "dig_end_mass_at_selected_kg": float(mass[idx]),
            }
        )
        return int(idx), qc

    selected = int(search_end)
    qc.update(
        {
            "dig_end_source": "search_end_no_confirmed_departure",
            "dig_end_selected_step": int(selected),
            "dig_end_departed_fraction_after_growth": float(
                np.mean(departed[candidate_start:search_end])
                if search_end > candidate_start
                else 0.0
            ),
        }
    )
    return selected, qc

def spatial_mass_dig_area_departed_mask(env_state: np.ndarray) -> np.ndarray:
    geometry = optional_env_col(
        env_state,
        ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX,
        default=1.0,
    )
    contact = optional_env_col(
        env_state,
        ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
        default=0.0,
    )
    depth = optional_env_col(
        env_state,
        ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
        default=float("nan"),
    )
    if not np.any(np.isfinite(depth)):
        depth = optional_env_col(env_state, 8, default=0.0)
    min_distance = optional_env_col(
        env_state,
        ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
        default=float("nan"),
    )
    long_norm = optional_env_col(
        env_state,
        ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX,
        default=float("nan"),
    )
    short_norm = optional_env_col(
        env_state,
        ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX,
        default=float("nan"),
    )
    finite_norm = np.isfinite(long_norm) & np.isfinite(short_norm)
    inside_norm_box = (
        (geometry > 0.5)
        & finite_norm
        & (np.abs(long_norm) <= SPATIAL_MASS_DIG_BOX_LONG_ABS_MAX)
        & (short_norm >= SPATIAL_MASS_DIG_BOX_SHORT_MIN)
        & (short_norm <= SPATIAL_MASS_DIG_BOX_SHORT_MAX)
    )
    finite_distance = np.isfinite(min_distance)
    outside_by_distance = finite_distance & (
        min_distance > SPATIAL_MASS_DIG_EXIT_MIN_DISTANCE_M
    )
    outside_by_norm = finite_norm & (~inside_norm_box)
    outside_spatial = outside_by_norm | outside_by_distance
    no_contact_depth = (
        (contact <= 0.5)
        & (np.nan_to_num(depth, nan=0.0) <= SPATIAL_MASS_DIG_EXIT_MAX_DEPTH_M)
    )
    return np.asarray(outside_spatial & no_contact_depth, dtype=bool)

__all__ = [
    "find_spatial_mass_dig_start",
    "find_spatial_mass_dig_end",
    "spatial_mass_dig_area_departed_mask",
]
