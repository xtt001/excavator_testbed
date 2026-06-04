"""Carry and dump window detection for spatial-mass primitive slicing."""

from __future__ import annotations

from typing import Any

import numpy as np

from testbed.data.v2_1 import WORK_STAGE_NAME_TO_ID

from .common import *

def find_spatial_mass_release_onset(
    *,
    episode: dict[str, Any],
    start: int,
    end: int,
) -> tuple[int | None, dict[str, Any]]:
    start = max(0, int(start))
    end = min(int(end), int(len(episode.get("actions", []))))
    env_state = env_state_or_none(episode)
    if env_state is not None and end > start + 1:
        mass = optional_env_col(env_state, ENV_STATE_MASS_IN_BUCKET_IDX, default=0.0)
        deposit = np.zeros(len(env_state), dtype=np.float32)
        for col in (
            ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
            ENV_STATE_DEPOSITED_MASS_IN_DUMP_AREA_IDX,
            ENV_STATE_OFFTARGET_DEPOSITED_MASS_IDX,
        ):
            if col < env_state.shape[1]:
                deposit = deposit + np.nan_to_num(env_state[:, col], nan=0.0)
        outside = optional_env_col(
            env_state,
            ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
            default=0.0,
        )
        over = optional_env_col(
            env_state,
            ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
            default=0.0,
        )
        for idx in range(start + 1, end):
            mass_drop = float(max(0.0, mass[idx - 1] - mass[idx]))
            deposit_gain = float(max(0.0, deposit[idx] - deposit[idx - 1]))
            near_dump_area = bool(outside[idx] <= 0.45 or over[idx] > 0.5)
            if near_dump_area and (mass_drop >= 0.5 or deposit_gain >= 0.5):
                return int(idx), {
                    "release_onset_step": int(idx),
                    "release_onset_source": "instant_mass_or_deposit_delta",
                    "release_instant_mass_drop_kg": mass_drop,
                    "release_instant_deposit_gain_kg": deposit_gain,
                    "release_dump_area_outside_distance_m": float(outside[idx]),
                }

    step = dict(dict(episode.get("v2") or {}).get("step", {}) or {})
    dump_start_mask = np.asarray(step.get("dump_start_mask", []), dtype=np.uint8)
    if dump_start_mask.size:
        candidates = np.flatnonzero(dump_start_mask.astype(bool))
        candidates = candidates[(candidates >= start) & (candidates < end)]
        if len(candidates) > 0:
            idx = int(candidates[0])
            return idx, {
                "release_onset_step": int(idx),
                "release_onset_source": "dump_start_mask_fallback",
            }
    work_stage_id = np.asarray(step.get("work_stage_id", []), dtype=np.int32)
    if work_stage_id.size:
        candidates = np.flatnonzero(work_stage_id == WORK_STAGE_NAME_TO_ID["dump"])
        candidates = candidates[(candidates >= start) & (candidates < end)]
        if len(candidates) > 0:
            idx = int(candidates[0])
            return idx, {
                "release_onset_step": int(idx),
                "release_onset_source": "dump_stage_fallback",
            }
    return None, {
        "release_onset_step": -1,
        "release_onset_source": "missing",
    }

def find_spatial_mass_dump_start(
    *,
    episode: dict[str, Any],
    cycle_start: int,
    release_onset: int,
) -> tuple[int, dict[str, Any]]:
    release_i = max(0, int(release_onset))
    lead_start = max(
        int(cycle_start),
        release_i - int(SPATIAL_MASS_DUMP_PRE_RELEASE_LEAD_MAX_STEPS),
    )
    qc: dict[str, Any] = {
        "dump_start_lead_cap_candidate_step": int(lead_start),
        "dump_start_max_outside_distance_m": float(
            SPATIAL_MASS_DUMP_START_MAX_OUTSIDE_DISTANCE_M
        ),
        "dump_start_stable_outside_distance_m": float(
            SPATIAL_MASS_DUMP_START_STABLE_OUTSIDE_DISTANCE_M
        ),
        "dump_start_stable_window_steps": int(
            SPATIAL_MASS_DUMP_START_STABLE_WINDOW_STEPS
        ),
        "dump_start_outside_range_tol_m": float(
            SPATIAL_MASS_DUMP_START_OUTSIDE_RANGE_TOL_M
        ),
        "dump_start_total_approach_tol_m": float(
            SPATIAL_MASS_DUMP_START_TOTAL_APPROACH_TOL_M
        ),
        "dump_start_relative_x_range_tol_m": float(
            SPATIAL_MASS_DUMP_START_RELATIVE_X_RANGE_TOL_M
        ),
        "dump_start_relative_z_range_tol_m": float(
            SPATIAL_MASS_DUMP_START_RELATIVE_Z_RANGE_TOL_M
        ),
        "dump_start_relative_x_min_m": float(
            SPATIAL_MASS_DUMP_START_RELATIVE_X_MIN_M
        ),
        "dump_start_relative_x_max_m": float(
            SPATIAL_MASS_DUMP_START_RELATIVE_X_MAX_M
        ),
        "dump_start_relative_z_min_m": float(
            SPATIAL_MASS_DUMP_START_RELATIVE_Z_MIN_M
        ),
        "dump_start_relative_z_max_m": float(
            SPATIAL_MASS_DUMP_START_RELATIVE_Z_MAX_M
        ),
        "dump_start_min_height_above_rim_m": float(
            SPATIAL_MASS_DUMP_START_MIN_HEIGHT_ABOVE_RIM_M
        ),
        "dump_start_source": "release_lead_cap",
    }
    env_state = env_state_or_none(episode)
    if env_state is None or env_state.shape[0] <= lead_start:
        qc["dump_start_source"] = "release_lead_cap_missing_env_state"
        return int(lead_start), qc
    end_i = min(int(release_i), int(env_state.shape[0] - 1))
    if end_i < lead_start:
        return int(lead_start), qc
    outside = optional_env_col(
        env_state,
        ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
        default=float("inf"),
    )
    over = optional_env_col(
        env_state,
        ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
        default=0.0,
    )
    relative_x = optional_env_col(
        env_state,
        ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX,
        default=float("nan"),
    )
    relative_z = optional_env_col(
        env_state,
        ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX,
        default=float("nan"),
    )
    height_above_rim = optional_env_col(
        env_state,
        ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
        default=float("nan"),
    )
    clearance = optional_env_col(
        env_state,
        ENV_STATE_DUMP_CLEARANCE_OK_IDX,
        default=0.0,
    )
    has_relative_geometry = bool(
        env_state.shape[1] > ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX
    )
    selected = int(lead_start)
    release_outside = float(outside[end_i])
    for idx in range(int(lead_start), int(end_i) + 1):
        outside_value = float(outside[idx])
        over_value = float(over[idx])
        height_value = float(height_above_rim[idx])
        near_dump_area = (
            np.isfinite(outside_value)
            and outside_value <= SPATIAL_MASS_DUMP_START_STABLE_OUTSIDE_DISTANCE_M
        ) or over_value > 0.5
        height_ok = (
            not np.isfinite(height_value)
            or height_value >= SPATIAL_MASS_DUMP_START_MIN_HEIGHT_ABOVE_RIM_M
        )
        if not near_dump_area or not height_ok:
            continue
        window_end = min(
            int(end_i) + 1,
            int(idx) + int(SPATIAL_MASS_DUMP_START_STABLE_WINDOW_STEPS),
        )
        outside_window = outside[int(idx) : window_end]
        finite_window = outside_window[np.isfinite(outside_window)]
        outside_range = (
            float(np.max(finite_window) - np.min(finite_window))
            if len(finite_window) > 0
            else float("inf")
        )
        total_approach = (
            abs(outside_value - release_outside)
            if np.isfinite(outside_value) and np.isfinite(release_outside)
            else 0.0 if over_value > 0.5 else float("inf")
        )
        relative_x_value = float(relative_x[idx])
        relative_z_value = float(relative_z[idx])
        relative_corridor_ok = (
            not has_relative_geometry
            or (
                np.isfinite(relative_x_value)
                and np.isfinite(relative_z_value)
                and SPATIAL_MASS_DUMP_START_RELATIVE_X_MIN_M
                <= relative_x_value
                <= SPATIAL_MASS_DUMP_START_RELATIVE_X_MAX_M
                and SPATIAL_MASS_DUMP_START_RELATIVE_Z_MIN_M
                <= relative_z_value
                <= SPATIAL_MASS_DUMP_START_RELATIVE_Z_MAX_M
            )
        )
        relative_x_window = relative_x[int(idx) : window_end]
        relative_z_window = relative_z[int(idx) : window_end]
        relative_x_range = finite_range(relative_x_window) if has_relative_geometry else 0.0
        relative_z_range = finite_range(relative_z_window) if has_relative_geometry else 0.0
        if (
            outside_range <= SPATIAL_MASS_DUMP_START_OUTSIDE_RANGE_TOL_M
            and total_approach <= SPATIAL_MASS_DUMP_START_TOTAL_APPROACH_TOL_M
            and relative_corridor_ok
            and relative_x_range <= SPATIAL_MASS_DUMP_START_RELATIVE_X_RANGE_TOL_M
            and relative_z_range <= SPATIAL_MASS_DUMP_START_RELATIVE_Z_RANGE_TOL_M
        ):
            selected = int(idx)
            qc["dump_start_source"] = "dump_area_committed_aiming_band"
            qc["dump_start_selected_outside_range_m"] = float(outside_range)
            qc["dump_start_selected_total_approach_m"] = float(total_approach)
            qc["dump_start_selected_relative_x_range_m"] = float(relative_x_range)
            qc["dump_start_selected_relative_z_range_m"] = float(relative_z_range)
            break
    else:
        candidates: list[int] = []
        for idx in range(int(lead_start), int(end_i) + 1):
            outside_value = float(outside[idx])
            over_value = float(over[idx])
            height_value = float(height_above_rim[idx])
            height_ok = (
                not np.isfinite(height_value)
                or height_value >= SPATIAL_MASS_DUMP_START_MIN_HEIGHT_ABOVE_RIM_M
            )
            relative_corridor_ok = (
                not has_relative_geometry
                or (
                    np.isfinite(float(relative_x[idx]))
                    and np.isfinite(float(relative_z[idx]))
                    and SPATIAL_MASS_DUMP_START_RELATIVE_X_MIN_M
                    <= float(relative_x[idx])
                    <= SPATIAL_MASS_DUMP_START_RELATIVE_X_MAX_M
                    and SPATIAL_MASS_DUMP_START_RELATIVE_Z_MIN_M
                    <= float(relative_z[idx])
                    <= SPATIAL_MASS_DUMP_START_RELATIVE_Z_MAX_M
                )
            )
            if height_ok and relative_corridor_ok and (
                np.isfinite(outside_value)
                and outside_value <= SPATIAL_MASS_DUMP_START_MAX_OUTSIDE_DISTANCE_M
                or over_value > 0.5
            ):
                candidates.append(int(idx))
        if candidates:
            fallback_floor = int(end_i) - int(
                SPATIAL_MASS_DUMP_START_FALLBACK_PRE_RELEASE_STEPS
            )
            late_candidates = [idx for idx in candidates if idx >= fallback_floor]
            selected = int(late_candidates[0] if late_candidates else candidates[-1])
            qc["dump_start_source"] = "late_pre_release_aiming_fallback"
            qc["dump_start_fallback_pre_release_steps"] = int(
                SPATIAL_MASS_DUMP_START_FALLBACK_PRE_RELEASE_STEPS
            )
        else:
            selected = int(end_i)
            qc["dump_start_source"] = "release_onset_no_aiming_candidate"
    qc["dump_start_selected_step"] = int(selected)
    qc["dump_start_selected_outside_distance_m"] = float(
        np.nan_to_num(outside[selected], nan=float("nan"), posinf=float("inf"))
    )
    qc["dump_start_release_outside_distance_m"] = float(
        np.nan_to_num(release_outside, nan=float("nan"), posinf=float("inf"))
    )
    qc["dump_start_selected_relative_x_m"] = float(
        np.nan_to_num(relative_x[selected], nan=float("nan"))
    )
    qc["dump_start_selected_relative_z_m"] = float(
        np.nan_to_num(relative_z[selected], nan=float("nan"))
    )
    qc["dump_start_release_relative_x_m"] = float(
        np.nan_to_num(relative_x[end_i], nan=float("nan"))
    )
    qc["dump_start_release_relative_z_m"] = float(
        np.nan_to_num(relative_z[end_i], nan=float("nan"))
    )
    qc["dump_start_selected_height_above_rim_m"] = float(
        np.nan_to_num(height_above_rim[selected], nan=float("nan"))
    )
    qc["dump_start_selected_over_target_footprint"] = int(over[selected] > 0.5)
    qc["dump_start_selected_clearance_ok"] = int(clearance[selected] > 0.5)
    return int(selected), qc

def find_spatial_mass_dump_end(
    *,
    episode: dict[str, Any],
    search_end: int,
    release_onset: int,
) -> tuple[int, dict[str, Any]]:
    work_end = int(search_end)
    release_i = max(0, int(release_onset))
    qc: dict[str, Any] = {
        "dump_legacy_work_end_step": int(work_end),
        "dump_end_source": "legacy_work_end",
        "dump_end_residual_bucket_mass_kg": float(
            SPATIAL_MASS_DUMP_END_RESIDUAL_BUCKET_MASS_KG
        ),
        "dump_end_plateau_steps": int(SPATIAL_MASS_DUMP_END_PLATEAU_STEPS),
    }
    env_state = env_state_or_none(episode)
    if env_state is None or work_end <= release_i + 1:
        qc["dump_end_source"] = "legacy_work_end_missing_env_state"
        return int(work_end), qc

    n_steps = int(env_state.shape[0])
    end_i = min(max(0, work_end - 1), n_steps - 1)
    release_i = min(release_i, end_i)
    mass = optional_env_col(env_state, ENV_STATE_MASS_IN_BUCKET_IDX, default=0.0)
    deposit = spatial_mass_deposit_trace(env_state)
    release_mass = max(0.0, float(mass[release_i]))
    residual_limit = max(
        5.0,
        min(
            float(SPATIAL_MASS_DUMP_END_RESIDUAL_BUCKET_MASS_KG),
            release_mass * 0.35,
        ),
    )
    hold = max(1, int(SPATIAL_MASS_DUMP_END_PLATEAU_STEPS))
    search_limit_exclusive = min(
        end_i + 1,
        release_i + int(SPATIAL_MASS_DUMP_END_MAX_POST_RELEASE_STEPS),
    )
    latest_plateau_start = max(release_i + 1, search_limit_exclusive - hold)
    low_mass_candidates: list[int] = []
    for idx in range(release_i + 1, latest_plateau_start + 1):
        if float(mass[idx]) > residual_limit:
            continue
        low_mass_candidates.append(int(idx))
        plateau_end = int(idx) + hold
        mass_window = mass[idx:plateau_end]
        deposit_window = deposit[idx:plateau_end]
        mass_range = float(np.nanmax(mass_window) - np.nanmin(mass_window))
        deposit_gain = float(max(0.0, deposit_window[-1] - deposit_window[0]))
        if (
            mass_range <= SPATIAL_MASS_DUMP_END_MASS_RANGE_TOL_KG
            and deposit_gain <= SPATIAL_MASS_DUMP_END_DEPOSIT_GAIN_TOL_KG
        ):
            qc.update(
                {
                    "dump_end_source": "residual_mass_deposit_plateau",
                    "dump_end_selected_step": int(plateau_end),
                    "dump_end_low_mass_step": int(idx),
                    "dump_end_residual_limit_kg": float(residual_limit),
                    "dump_end_plateau_mass_range_kg": mass_range,
                    "dump_end_plateau_deposit_gain_kg": deposit_gain,
                }
            )
            return int(plateau_end), qc

    if low_mass_candidates:
        selected = min(end_i + 1, int(low_mass_candidates[0]) + hold)
        qc.update(
            {
                "dump_end_source": "residual_mass_post_hold_fallback",
                "dump_end_selected_step": int(selected),
                "dump_end_low_mass_step": int(low_mass_candidates[0]),
                "dump_end_residual_limit_kg": float(residual_limit),
            }
        )
        return int(selected), qc

    capped = min(end_i + 1, release_i + int(SPATIAL_MASS_DUMP_END_MAX_POST_RELEASE_STEPS))
    if capped < work_end:
        qc.update(
            {
                "dump_end_source": "post_release_cap_fallback",
                "dump_end_selected_step": int(capped),
                "dump_end_post_release_cap_steps": int(
                    SPATIAL_MASS_DUMP_END_MAX_POST_RELEASE_STEPS
                ),
            }
        )
        return int(capped), qc
    qc["dump_end_selected_step"] = int(work_end)
    return int(work_end), qc

def spatial_mass_carry_qc(
    *,
    episode: dict[str, Any],
    start: int,
    end: int,
    release_onset: int,
) -> dict[str, Any]:
    qc = {
        "carry_start_step": int(start),
        "carry_end_step": int(end),
        "carry_window_len": int(end) - int(start),
        "carry_release_onset_step": int(release_onset),
        "carry_steps_before_release": int(release_onset) - int(end),
    }
    env_state = env_state_or_none(episode)
    if env_state is None or int(end) <= int(start):
        qc["carry_qc_missing_env_state"] = True
        return qc
    start_i = max(0, min(int(start), len(env_state) - 1))
    end_i = max(start_i, min(int(end) - 1, len(env_state) - 1))
    mass = optional_env_col(env_state, ENV_STATE_MASS_IN_BUCKET_IDX, default=0.0)
    deposit = spatial_mass_deposit_trace(env_state)
    mass_loss = float(max(0.0, mass[start_i] - mass[end_i]))
    deposit_delta = float(max(0.0, deposit[end_i] - deposit[start_i]))
    ratio = float(0.0 if mass_loss <= 1.0e-6 else deposit_delta / mass_loss)
    qc.update(
        {
            "carry_start_bucket_mass_kg": float(mass[start_i]),
            "carry_end_bucket_mass_kg": float(mass[end_i]),
            "carry_bucket_mass_loss_kg": mass_loss,
            "carry_deposit_delta_kg": deposit_delta,
            "carry_deposit_to_payload_loss_frac": ratio,
            "carry_max_deposit_delta_kg": float(SPATIAL_MASS_CARRY_MAX_DEPOSIT_DELTA_KG),
            "carry_max_deposit_to_payload_loss_frac": float(
                SPATIAL_MASS_CARRY_MAX_DEPOSIT_TO_PAYLOAD_LOSS_FRAC
            ),
        }
    )
    return qc

def spatial_mass_carry_contaminated(qc: dict[str, Any]) -> bool:
    deposit_delta = float(qc.get("carry_deposit_delta_kg", 0.0))
    ratio = float(qc.get("carry_deposit_to_payload_loss_frac", 0.0))
    return bool(
        deposit_delta > SPATIAL_MASS_CARRY_MAX_DEPOSIT_DELTA_KG
        and ratio > SPATIAL_MASS_CARRY_MAX_DEPOSIT_TO_PAYLOAD_LOSS_FRAC
    )

def spatial_mass_dump_qc(
    *,
    episode: dict[str, Any],
    start: int,
    end: int,
    release_onset: int,
    release_qc: dict[str, Any],
) -> dict[str, Any]:
    qc = dict(release_qc)
    qc.update(
        {
            "dump_start_step": int(start),
            "dump_end_step": int(end),
            "dump_window_len": int(end) - int(start),
            "dump_release_onset_step": int(release_onset),
            "dump_pre_release_lead_steps": int(release_onset) - int(start),
            "dump_pre_release_lead_cap_steps": int(
                SPATIAL_MASS_DUMP_PRE_RELEASE_LEAD_MAX_STEPS
            ),
        }
    )
    env_state = env_state_or_none(episode)
    if env_state is None or int(end) <= int(start):
        qc["dump_qc_missing_env_state"] = True
        return qc
    start_i = max(0, min(int(start), len(env_state) - 1))
    end_i = max(start_i, min(int(end) - 1, len(env_state) - 1))
    release_i = max(start_i, min(int(release_onset), end_i))
    mass = optional_env_col(env_state, ENV_STATE_MASS_IN_BUCKET_IDX, default=0.0)
    deposit = spatial_mass_deposit_trace(env_state)
    window_mass_loss = float(max(0.0, mass[start_i] - mass[end_i]))
    release_mass_loss = float(max(0.0, mass[release_i] - mass[end_i]))
    deposit_delta = float(max(0.0, deposit[end_i] - deposit[start_i]))
    outside = optional_env_col(
        env_state,
        ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
        default=float("nan"),
    )
    relative_x = optional_env_col(
        env_state,
        ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX,
        default=float("nan"),
    )
    relative_z = optional_env_col(
        env_state,
        ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX,
        default=float("nan"),
    )
    height_above_rim = optional_env_col(
        env_state,
        ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
        default=float("nan"),
    )
    over = optional_env_col(
        env_state,
        ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
        default=0.0,
    )
    clearance = optional_env_col(
        env_state,
        ENV_STATE_DUMP_CLEARANCE_OK_IDX,
        default=0.0,
    )
    qc.update(
        {
            "dump_window_mass_loss_kg": window_mass_loss,
            "dump_release_mass_loss_kg": release_mass_loss,
            "dump_deposit_delta_kg": deposit_delta,
            "dump_release_deposit_fraction": float(
                0.0 if release_mass_loss <= 1.0e-6 else deposit_delta / release_mass_loss
            ),
            "dump_start_dump_area_footprint_outside_distance_m": float(
                np.nan_to_num(outside[start_i], nan=float("nan"))
            ),
            "dump_release_dump_area_footprint_outside_distance_m": float(
                np.nan_to_num(outside[release_i], nan=float("nan"))
            ),
            "dump_start_dump_area_relative_x_m": float(
                np.nan_to_num(relative_x[start_i], nan=float("nan"))
            ),
            "dump_start_dump_area_relative_z_m": float(
                np.nan_to_num(relative_z[start_i], nan=float("nan"))
            ),
            "dump_release_dump_area_relative_x_m": float(
                np.nan_to_num(relative_x[release_i], nan=float("nan"))
            ),
            "dump_release_dump_area_relative_z_m": float(
                np.nan_to_num(relative_z[release_i], nan=float("nan"))
            ),
            "dump_start_height_above_rim_m": float(
                np.nan_to_num(height_above_rim[start_i], nan=float("nan"))
            ),
            "dump_start_over_target_footprint": int(over[start_i] > 0.5),
            "dump_start_clearance_ok": int(clearance[start_i] > 0.5),
        }
    )
    return qc

__all__ = [
    "find_spatial_mass_release_onset",
    "find_spatial_mass_dump_start",
    "find_spatial_mass_dump_end",
    "spatial_mass_carry_qc",
    "spatial_mass_carry_contaminated",
    "spatial_mass_dump_qc",
]
