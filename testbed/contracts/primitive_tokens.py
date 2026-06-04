"""Primitive token contract shared by data builders, loaders, and rollout."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from testbed.data.schema import (
    DS_V2_STEP_DIG_CUT_TOKENS,
    DS_V2_STEP_DIG_DEPTH_PROFILE_TOKENS_V1,
    DS_V2_STEP_RETURN_START_ENVELOPE_TOKENS_V1,
    DS_V2_STEP_RETURN_START_ENVELOPE_VALID_MASK,
    DS_V2_STEP_RETURN_TARGET_TOKENS,
)


PRIMITIVE_TOKEN_CONTRACT_VERSION = "v2_4_5_primitive_tokens_v1"

DIG_CUT_TOKEN_KEY = "dig_cut_tokens"
DIG_DEPTH_PROFILE_TOKEN_KEY = "dig_depth_profile_tokens_v1"
RETURN_TARGET_TOKEN_KEY = "return_target_tokens"
RETURN_RELOCATE_TOKEN_KEY = "return_relocate_tokens_v1"
RETURN_START_ENVELOPE_TOKEN_KEY = "return_start_envelope_tokens_v1"
RETURN_START_ENVELOPE_VALID_MASK_KEY = "return_start_envelope_valid_mask"

DIG_CUT_TOKEN_DIM = 10
RETURN_TARGET_TOKEN_DIM = DIG_CUT_TOKEN_DIM
RETURN_RELOCATE_TOKEN_DIM = DIG_CUT_TOKEN_DIM
DIG_DEPTH_PROFILE_TOKEN_DIM = 12
RETURN_START_ENVELOPE_TOKEN_DIM = 18
RETURN_START_ENVELOPE_VALID_MASK_DIM = RETURN_START_ENVELOPE_TOKEN_DIM

DIG_CUT_TOKEN_ORDER = (
    "entry_x",
    "entry_z",
    "exit_x",
    "exit_z",
    "dir_x",
    "dir_z",
    "length",
    "cut_depth_semantic",
    "payload",
    "valid",
)
RETURN_TARGET_TOKEN_ORDER = DIG_CUT_TOKEN_ORDER
RETURN_RELOCATE_TOKEN_ORDER = DIG_CUT_TOKEN_ORDER

DIG_DEPTH_PROFILE_TOKEN_ORDER = (
    "dominant_cell_id_norm",
    "removed_depth_target_norm",
    "payload_target_norm",
    "effective_deposit_target_norm",
    "cut_length_norm",
    "entry_reference_depth_norm",
    "exit_reference_depth_norm",
    "peak_reference_depth_norm",
    "peak_surface_penetration_est_norm",
    "plane_minus_surface_penetration_offset_norm",
    "contact_fraction",
    "valid",
)

RETURN_START_ENVELOPE_TOKEN_ORDER = (
    "long_norm",
    "short_norm",
    "depth_center",
    "tip_radius",
    "depth_min",
    "depth_max",
    "contact_flag",
    "qpos_center_0",
    "qpos_center_1",
    "qpos_center_2",
    "qpos_center_3",
    "qpos_half_width_0",
    "qpos_half_width_1",
    "qpos_half_width_2",
    "qpos_half_width_3",
    "qvel_abs_max",
    "qpos_valid",
    "spatial_depth_valid",
)
RETURN_START_ENVELOPE_VALID_MASK_ORDER = RETURN_START_ENVELOPE_TOKEN_ORDER

CUT_ENTRY_X_IDX = 0
CUT_ENTRY_Z_IDX = 1
CUT_EXIT_X_IDX = 2
CUT_EXIT_Z_IDX = 3
CUT_DIR_X_IDX = 4
CUT_DIR_Z_IDX = 5
CUT_LENGTH_IDX = 6
CUT_DEPTH_SEMANTIC_IDX = 7
CUT_PAYLOAD_IDX = 8
CUT_VALID_IDX = 9
CUT_RELOCATION_SLICE = slice(CUT_ENTRY_X_IDX, CUT_DEPTH_SEMANTIC_IDX)

RETURN_ENVELOPE_LONG_NORM_IDX = 0
RETURN_ENVELOPE_SHORT_NORM_IDX = 1
RETURN_ENVELOPE_DEPTH_CENTER_IDX = 2
RETURN_ENVELOPE_TIP_RADIUS_IDX = 3
RETURN_ENVELOPE_DEPTH_MIN_IDX = 4
RETURN_ENVELOPE_DEPTH_MAX_IDX = 5
RETURN_ENVELOPE_CONTACT_FLAG_IDX = 6
RETURN_ENVELOPE_QPOS_CENTER_SLICE = slice(7, 11)
RETURN_ENVELOPE_QPOS_HALF_WIDTH_SLICE = slice(11, 15)
RETURN_ENVELOPE_QVEL_ABS_MAX_IDX = 15
RETURN_ENVELOPE_QPOS_VALID_IDX = 16
RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX = 17
RETURN_ENVELOPE_SPATIAL_SLICE = slice(
    RETURN_ENVELOPE_LONG_NORM_IDX,
    RETURN_ENVELOPE_CONTACT_FLAG_IDX + 1,
)

_TOKEN_DIMS = {
    DIG_CUT_TOKEN_KEY: DIG_CUT_TOKEN_DIM,
    DIG_DEPTH_PROFILE_TOKEN_KEY: DIG_DEPTH_PROFILE_TOKEN_DIM,
    RETURN_TARGET_TOKEN_KEY: RETURN_TARGET_TOKEN_DIM,
    RETURN_RELOCATE_TOKEN_KEY: RETURN_RELOCATE_TOKEN_DIM,
    RETURN_START_ENVELOPE_TOKEN_KEY: RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_START_ENVELOPE_VALID_MASK_KEY: RETURN_START_ENVELOPE_VALID_MASK_DIM,
}

_TOKEN_ORDERS = {
    DIG_CUT_TOKEN_KEY: DIG_CUT_TOKEN_ORDER,
    DIG_DEPTH_PROFILE_TOKEN_KEY: DIG_DEPTH_PROFILE_TOKEN_ORDER,
    RETURN_TARGET_TOKEN_KEY: RETURN_TARGET_TOKEN_ORDER,
    RETURN_RELOCATE_TOKEN_KEY: RETURN_RELOCATE_TOKEN_ORDER,
    RETURN_START_ENVELOPE_TOKEN_KEY: RETURN_START_ENVELOPE_TOKEN_ORDER,
    RETURN_START_ENVELOPE_VALID_MASK_KEY: RETURN_START_ENVELOPE_VALID_MASK_ORDER,
}

_TOKEN_DATASET_PATHS = {
    DIG_CUT_TOKEN_KEY: DS_V2_STEP_DIG_CUT_TOKENS,
    DIG_DEPTH_PROFILE_TOKEN_KEY: DS_V2_STEP_DIG_DEPTH_PROFILE_TOKENS_V1,
    RETURN_TARGET_TOKEN_KEY: DS_V2_STEP_RETURN_TARGET_TOKENS,
    RETURN_RELOCATE_TOKEN_KEY: DS_V2_STEP_RETURN_TARGET_TOKENS,
    RETURN_START_ENVELOPE_TOKEN_KEY: DS_V2_STEP_RETURN_START_ENVELOPE_TOKENS_V1,
    RETURN_START_ENVELOPE_VALID_MASK_KEY: DS_V2_STEP_RETURN_START_ENVELOPE_VALID_MASK,
}

_TOKEN_METADATA_DIM_ATTRS = {
    DIG_CUT_TOKEN_KEY: ("dig_cut_tokens_dim", "dig_cut_token_dim"),
    DIG_DEPTH_PROFILE_TOKEN_KEY: (
        "dig_depth_profile_tokens_v1_dim",
        "dig_depth_profile_token_dim",
    ),
    RETURN_TARGET_TOKEN_KEY: ("return_target_tokens_dim", "return_target_token_dim"),
    RETURN_RELOCATE_TOKEN_KEY: (
        "return_relocate_tokens_v1_dim",
        "return_target_tokens_dim",
        "return_target_token_dim",
    ),
    RETURN_START_ENVELOPE_TOKEN_KEY: (
        "return_start_envelope_tokens_v1_dim",
        "return_start_envelope_token_dim",
    ),
    RETURN_START_ENVELOPE_VALID_MASK_KEY: (
        "return_start_envelope_valid_mask_dim",
        "return_start_envelope_tokens_v1_dim",
        "return_start_envelope_token_dim",
    ),
}


def primitive_token_dim(key: str) -> int:
    value = str(key)
    if value not in _TOKEN_DIMS:
        raise ValueError(f"Unsupported primitive token key {key!r}.")
    return int(_TOKEN_DIMS[value])


def primitive_token_order(key: str) -> tuple[str, ...]:
    value = str(key)
    if value not in _TOKEN_ORDERS:
        raise ValueError(f"Unsupported primitive token key {key!r}.")
    return tuple(_TOKEN_ORDERS[value])


def primitive_token_dataset_path(key: str) -> str:
    value = str(key)
    if value not in _TOKEN_DATASET_PATHS:
        raise ValueError(f"Unsupported primitive token key {key!r}.")
    return str(_TOKEN_DATASET_PATHS[value])


def primitive_token_metadata_dim_attrs(key: str) -> tuple[str, ...]:
    value = str(key)
    if value not in _TOKEN_METADATA_DIM_ATTRS:
        raise ValueError(f"Unsupported primitive token key {key!r}.")
    return tuple(_TOKEN_METADATA_DIM_ATTRS[value])


def validate_primitive_token_shape(
    key: str,
    value: Any,
    *,
    allow_sequence: bool = True,
) -> np.ndarray:
    arr = np.asarray(value)
    expected_dim = primitive_token_dim(key)
    if arr.ndim == 1 and arr.shape[0] == expected_dim:
        return arr
    if allow_sequence and arr.ndim == 2 and arr.shape[1] == expected_dim:
        return arr
    raise ValueError(
        f"{key} must have last dimension {expected_dim}, got {arr.shape}."
    )


def derive_return_relocate_token(return_target_token: Any) -> np.ndarray:
    token = validate_primitive_token_shape(
        RETURN_TARGET_TOKEN_KEY,
        return_target_token,
    ).astype(np.float32, copy=True)
    token[~np.isfinite(token)] = 0.0
    token[..., CUT_DEPTH_SEMANTIC_IDX] = 0.0
    token[..., CUT_PAYLOAD_IDX] = 0.0
    return token


def token_contract_string(key: str, *, prefix: str = "") -> str:
    fields = primitive_token_order(key)
    if prefix:
        fields = tuple(f"{prefix} {fields[0]}") + fields[1:]
    return ",".join(fields)


def metadata_dim_from_attrs(
    key: str,
    attrs: Mapping[str, Any],
) -> int | None:
    for attr in primitive_token_metadata_dim_attrs(key):
        if attr in attrs:
            return int(np.asarray(attrs[attr]).reshape(-1)[0])
    return None
