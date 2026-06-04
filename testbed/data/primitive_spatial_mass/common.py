"""Shared constants and array helpers for spatial-mass primitive slicing."""

from __future__ import annotations

from typing import Any, Iterable

import numpy as np

from testbed.contracts.primitive_profile import (
    PRIMITIVE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS,
)
from testbed.contracts.primitive_tokens import (
    RETURN_ENVELOPE_CONTACT_FLAG_IDX,
    RETURN_ENVELOPE_DEPTH_CENTER_IDX,
    RETURN_ENVELOPE_DEPTH_MAX_IDX,
    RETURN_ENVELOPE_DEPTH_MIN_IDX,
    RETURN_ENVELOPE_LONG_NORM_IDX,
    RETURN_ENVELOPE_QPOS_CENTER_SLICE,
    RETURN_ENVELOPE_QPOS_HALF_WIDTH_SLICE,
    RETURN_ENVELOPE_QPOS_VALID_IDX,
    RETURN_ENVELOPE_QVEL_ABS_MAX_IDX,
    RETURN_ENVELOPE_SHORT_NORM_IDX,
    RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX,
    RETURN_ENVELOPE_SPATIAL_SLICE,
    RETURN_ENVELOPE_TIP_RADIUS_IDX,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_START_ENVELOPE_TOKEN_KEY,
    RETURN_START_ENVELOPE_VALID_MASK_KEY,
    primitive_token_dataset_path,
)
from testbed.data.schema import (
    ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX,
    ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
    ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_DUMP_AREA_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_DIG_AREA_GEOMETRY_AVAILABLE_IDX,
    ENV_STATE_DUMP_CLEARANCE_OK_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
    ENV_STATE_OFFTARGET_DEPOSITED_MASS_IDX,
)

SPATIAL_MASS_DIG_WINDOW_NAME = "material_cycle_dig_contact_depth_payload_gain"
SPATIAL_MASS_CARRY_WINDOW_NAME = "loaded_transport_to_pre_release"
SPATIAL_MASS_DUMP_WINDOW_NAME = "dump_area_committed_release_deposit"
SPATIAL_MASS_RETURN_WINDOW_NAME = "dump_end_to_next_dig_start_envelope"
POSE_REALIGN_METADATA_KEY = "replay_pose_realign_steps"
POSE_REALIGN_CYCLE_REJECT_REASON = "cycle_contains_pose_realign"
POSE_REALIGN_TRANSITION_REJECT_REASON = "return_window_contains_pose_realign"

SPATIAL_MASS_DUMP_PRE_RELEASE_LEAD_MAX_STEPS = 120
SPATIAL_MASS_DUMP_START_MAX_OUTSIDE_DISTANCE_M = 0.30
SPATIAL_MASS_DUMP_START_STABLE_OUTSIDE_DISTANCE_M = 0.25
SPATIAL_MASS_DUMP_START_STABLE_WINDOW_STEPS = 20
SPATIAL_MASS_DUMP_START_OUTSIDE_RANGE_TOL_M = 0.06
SPATIAL_MASS_DUMP_START_TOTAL_APPROACH_TOL_M = 0.10
SPATIAL_MASS_DUMP_START_RELATIVE_X_MIN_M = -0.20
SPATIAL_MASS_DUMP_START_RELATIVE_X_MAX_M = 1.90
SPATIAL_MASS_DUMP_START_RELATIVE_Z_MIN_M = 0.45
SPATIAL_MASS_DUMP_START_RELATIVE_Z_MAX_M = 2.10
SPATIAL_MASS_DUMP_START_RELATIVE_X_RANGE_TOL_M = 0.16
SPATIAL_MASS_DUMP_START_RELATIVE_Z_RANGE_TOL_M = 0.10
SPATIAL_MASS_DUMP_START_MIN_HEIGHT_ABOVE_RIM_M = 0.45
SPATIAL_MASS_DUMP_START_FALLBACK_PRE_RELEASE_STEPS = 15
SPATIAL_MASS_DUMP_END_RESIDUAL_BUCKET_MASS_KG = 15.0
SPATIAL_MASS_DUMP_END_PLATEAU_STEPS = 30
SPATIAL_MASS_DUMP_END_MASS_RANGE_TOL_KG = 2.0
SPATIAL_MASS_DUMP_END_DEPOSIT_GAIN_TOL_KG = 2.0
SPATIAL_MASS_DUMP_END_MAX_POST_RELEASE_STEPS = 480
SPATIAL_MASS_DIG_MASS_GAIN_EPS_KG = 0.35
SPATIAL_MASS_DIG_PEAK_GAIN_FRACTION = 0.90
SPATIAL_MASS_DIG_NEAR_PEAK_TOL_KG = 3.0
SPATIAL_MASS_DIG_FUTURE_GAIN_TOL_KG = 2.0
SPATIAL_MASS_DIG_MASS_PLATEAU_STEPS = 8
SPATIAL_MASS_DIG_EXIT_HOLD_STEPS = 3
SPATIAL_MASS_DIG_EXIT_MIN_DISTANCE_M = 0.08
SPATIAL_MASS_DIG_EXIT_MAX_DEPTH_M = 0.02
SPATIAL_MASS_DIG_BOX_LONG_ABS_MAX = 1.05
SPATIAL_MASS_DIG_BOX_SHORT_MIN = -0.15
SPATIAL_MASS_DIG_BOX_SHORT_MAX = 1.15
SPATIAL_MASS_RETURN_ENTRY_READY_DISTANCE_M = 0.05
SPATIAL_MASS_RETURN_ENTRY_READY_DEPTH_M = 0.005
RETURN_START_ENVELOPE_WINDOW_STEPS = 40
SPATIAL_MASS_CARRY_MAX_DEPOSIT_DELTA_KG = 5.0
SPATIAL_MASS_CARRY_MAX_DEPOSIT_TO_PAYLOAD_LOSS_FRAC = 0.10

def spatial_mass_deposit_trace(env_state: np.ndarray) -> np.ndarray:
    deposit = np.zeros(len(env_state), dtype=np.float32)
    for col in (
        ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
        ENV_STATE_DEPOSITED_MASS_IN_DUMP_AREA_IDX,
        ENV_STATE_OFFTARGET_DEPOSITED_MASS_IDX,
    ):
        if col < env_state.shape[1]:
            deposit = deposit + np.nan_to_num(env_state[:, col], nan=0.0)
    return deposit

def env_state_or_none(episode: dict[str, Any]) -> np.ndarray | None:
    value = episode.get("env_state")
    if value is None:
        return None
    arr = np.asarray(value, dtype=np.float32)
    if arr.ndim != 2:
        return None
    return arr

def optional_env_col(
    env_state: np.ndarray,
    index: int,
    *,
    default: float,
) -> np.ndarray:
    if int(index) < env_state.shape[1]:
        return np.asarray(env_state[:, int(index)], dtype=np.float32)
    return np.full(env_state.shape[0], float(default), dtype=np.float32)

def finite_range(values: np.ndarray) -> float:
    arr = np.asarray(values, dtype=np.float32)
    finite = arr[np.isfinite(arr)]
    if len(finite) <= 0:
        return float("inf")
    return float(np.max(finite) - np.min(finite))

def window_pose_realign_steps(
    *,
    realign_steps: Iterable[int],
    start_step: int,
    end_step_exclusive: int,
) -> tuple[int, ...]:
    start = int(start_step)
    end = int(end_step_exclusive)
    return tuple(
        int(step)
        for step in realign_steps
        if int(step) >= start and int(step) < end
    )

__all__ = [
    name
    for name in globals()
    if name.startswith(("ENV_STATE_", "RETURN_ENVELOPE_", "SPATIAL_MASS_"))
]
__all__ += [
    "POSE_REALIGN_METADATA_KEY",
    "POSE_REALIGN_CYCLE_REJECT_REASON",
    "POSE_REALIGN_TRANSITION_REJECT_REASON",
    "PRIMITIVE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS",
    "RETURN_START_ENVELOPE_TOKEN_DIM",
    "RETURN_START_ENVELOPE_TOKEN_KEY",
    "RETURN_START_ENVELOPE_VALID_MASK_KEY",
    "RETURN_START_ENVELOPE_WINDOW_STEPS",
    "primitive_token_dataset_path",
    "env_state_or_none",
    "optional_env_col",
    "finite_range",
    "window_pose_realign_steps",
    "spatial_mass_deposit_trace",
]
