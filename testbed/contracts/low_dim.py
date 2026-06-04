"""Low-dimensional observation contract shared by train, data, and eval."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from testbed.contracts.primitive_tokens import (
    DIG_CUT_TOKEN_DIM,
    DIG_DEPTH_PROFILE_TOKEN_DIM,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_TARGET_TOKEN_DIM,
)
from testbed.data.v2_1 import GOAL_TOKEN_DIM
from testbed.planner.cell_entry import CELL_ENTRY_TOKEN_DIM


LOW_DIM_CONTRACT_VERSION = "v2_4_5_low_dim_v1"

SUPPORTED_LOW_DIM_KEYS = (
    "qpos",
    "qvel",
    "goal_tokens",
    "cell_entry_tokens",
    "dig_cut_tokens",
    "dig_depth_profile_tokens_v1",
    "return_target_tokens",
    "return_relocate_tokens_v1",
    "return_start_envelope_tokens_v1",
)

TOKEN_LOW_DIM_KEYS = (
    "goal_tokens",
    "dig_cut_tokens",
    "dig_depth_profile_tokens_v1",
    "return_target_tokens",
    "return_relocate_tokens_v1",
    "return_start_envelope_tokens_v1",
)

_TOKEN_DIMS = {
    "goal_tokens": int(GOAL_TOKEN_DIM),
    "cell_entry_tokens": int(CELL_ENTRY_TOKEN_DIM),
    "dig_cut_tokens": int(DIG_CUT_TOKEN_DIM),
    "dig_depth_profile_tokens_v1": int(DIG_DEPTH_PROFILE_TOKEN_DIM),
    "return_target_tokens": int(RETURN_TARGET_TOKEN_DIM),
    "return_relocate_tokens_v1": int(RETURN_TARGET_TOKEN_DIM),
    "return_start_envelope_tokens_v1": int(RETURN_START_ENVELOPE_TOKEN_DIM),
}

_MISSING_MESSAGES = {
    "goal_tokens": (
        "Requested low_dim key 'goal_tokens' but /v2/step/goal_tokens is missing."
    ),
    "cell_entry_tokens": (
        "Requested low_dim key 'cell_entry_tokens' but "
        "/v2/step/cell_entry_tokens is missing."
    ),
    "dig_cut_tokens": (
        "Requested low_dim key 'dig_cut_tokens' but "
        "/v2/step/dig_cut_tokens is missing."
    ),
    "dig_depth_profile_tokens_v1": (
        "Requested low_dim key 'dig_depth_profile_tokens_v1' but "
        "/v2/step/dig_depth_profile_tokens_v1 is missing."
    ),
    "return_target_tokens": (
        "Requested low_dim key 'return_target_tokens' but "
        "/v2/step/return_target_tokens is missing."
    ),
    "return_relocate_tokens_v1": (
        "Requested low_dim key 'return_relocate_tokens_v1' but "
        "a relocate target could not be derived from "
        "/v2/step/return_target_tokens or metadata next_operator fields."
    ),
    "return_start_envelope_tokens_v1": (
        "Requested low_dim key 'return_start_envelope_tokens_v1' but "
        "/v2/step/return_start_envelope_tokens_v1 is missing."
    ),
}


def normalize_low_dim_keys(
    low_dim_keys: Sequence[str] | None,
) -> list[str]:
    """Normalize dataset low-dim key config and reject unsupported keys."""
    keys = ["qpos"] if not low_dim_keys else [str(key) for key in low_dim_keys]
    invalid = [key for key in keys if key not in SUPPORTED_LOW_DIM_KEYS]
    if invalid:
        raise ValueError(
            f"Unsupported low_dim_keys {invalid}. "
            f"Supported keys: {SUPPORTED_LOW_DIM_KEYS}."
        )
    return keys


def low_dim_key_dim(key: str, equipment_model: str) -> int:
    """Return one low-dim key width for the current equipment model."""
    key = str(key)
    if key in _TOKEN_DIMS:
        return int(_TOKEN_DIMS[key])
    if key in ("qpos", "qvel"):
        equipment = str(equipment_model).lower()
        if "bimanual" in equipment:
            return 14
        if (
            "excavator_simple" in equipment
            or "agxunity" in equipment
            or "agx" in equipment
            or "yulong" in equipment
        ):
            return 4
        return 7
    raise ValueError(f"Unsupported low-dim key {key!r}.")


def resolve_low_dim_state_dim(
    low_dim_keys: Sequence[str],
    equipment_model: str,
) -> int:
    """Resolve total state_dim while preserving legacy KeyError on unknown keys."""
    dims = {
        key: low_dim_key_dim(key, equipment_model) for key in SUPPORTED_LOW_DIM_KEYS
    }
    return int(sum(dims[str(key)] for key in low_dim_keys))


def resolve_token_slices(
    low_dim_keys: Sequence[str],
    equipment_model: str,
) -> tuple[slice, ...] | None:
    """Return slices that contain swappable token observations."""
    start = 0
    token_slices: list[slice] = []
    for key in low_dim_keys:
        key = str(key)
        dim = low_dim_key_dim(key, equipment_model)
        if key in TOKEN_LOW_DIM_KEYS:
            token_slices.append(slice(start, start + dim))
        start += dim
    if not token_slices:
        return None
    return tuple(token_slices)


def assemble_low_dim_observation(
    values: Mapping[str, Any],
    low_dim_keys: Sequence[str],
) -> np.ndarray:
    """Assemble configured low-dim arrays in contract order."""
    arrays = {
        key: None if value is None else np.asarray(value, dtype=np.float32)
        for key, value in values.items()
    }
    sequence_mode = any(value is not None and value.ndim > 1 for value in arrays.values())
    parts: list[np.ndarray] = []
    for key in low_dim_keys:
        key = str(key)
        part = arrays.get(key)
        if part is None:
            if key in _MISSING_MESSAGES:
                raise KeyError(_MISSING_MESSAGES[key])
            continue
        if sequence_mode:
            part = part.reshape(part.shape[0], -1)
        else:
            part = part.reshape(-1)
        parts.append(part)
    if not parts:
        raise ValueError("low_dim_keys must contain at least one supported key.")
    axis = 1 if sequence_mode else 0
    return np.concatenate(parts, axis=axis).astype(np.float32)


def validate_low_dim_stats_contract(
    policy_config: Mapping[str, Any],
    norm_stats: Mapping[str, Any],
) -> None:
    """Validate dataset stats against policy low_dim_keys and state_dim."""
    low_dim_keys = list(policy_config.get("low_dim_keys", ["qpos"]))
    expected_dim = resolve_low_dim_state_dim(
        low_dim_keys,
        str(policy_config.get("equipment_model", "")),
    )
    configured_dim = policy_config.get("state_dim")
    if configured_dim is not None and int(configured_dim) != expected_dim:
        raise ValueError(
            "ACTAdapter policy_config.state_dim does not match low_dim_keys: "
            f"state_dim={int(configured_dim)}, expected {expected_dim} from "
            f"low_dim_keys={low_dim_keys}."
        )

    stats_keys = norm_stats.get("proprio_keys")
    if stats_keys is not None:
        normalized_keys = _normalize_stats_keys(stats_keys)
        if normalized_keys != low_dim_keys:
            raise ValueError(
                "dataset_stats.pkl proprio_keys does not match policy low_dim_keys: "
                f"{normalized_keys} != {low_dim_keys}."
            )

    stats_dim = norm_stats.get("proprio_dim")
    if stats_dim is not None and int(stats_dim) != expected_dim:
        raise ValueError(
            "dataset_stats.pkl proprio_dim does not match policy low_dim_keys: "
            f"proprio_dim={int(stats_dim)}, expected {expected_dim}."
        )

    if "proprio_mean" in norm_stats or "proprio_std" in norm_stats:
        if "proprio_mean" not in norm_stats or "proprio_std" not in norm_stats:
            raise KeyError(
                "dataset_stats.pkl must contain both proprio_mean and proprio_std."
            )
        mean_dim = _flat_stat_dim(norm_stats["proprio_mean"])
        std_dim = _flat_stat_dim(norm_stats["proprio_std"])
        if mean_dim != expected_dim or std_dim != expected_dim:
            raise ValueError(
                "dataset_stats.pkl proprio_mean/proprio_std length does not "
                f"match policy low_dim_keys: mean={mean_dim}, std={std_dim}, "
                f"expected={expected_dim}."
            )
        return

    if low_dim_keys == ["qpos"]:
        if "qpos_mean" not in norm_stats or "qpos_std" not in norm_stats:
            raise KeyError(
                "dataset_stats.pkl must contain qpos_mean/qpos_std for "
                "legacy qpos-only checkpoints."
            )
        mean_dim = _flat_stat_dim(norm_stats["qpos_mean"])
        std_dim = _flat_stat_dim(norm_stats["qpos_std"])
        if mean_dim != expected_dim or std_dim != expected_dim:
            raise ValueError(
                "legacy qpos_mean/qpos_std length does not match qpos dim: "
                f"mean={mean_dim}, std={std_dim}, expected={expected_dim}."
            )
        return

    raise KeyError(
        "dataset_stats.pkl does not contain proprio_mean/proprio_std for "
        f"low_dim_keys={low_dim_keys}. Recompute stats by retraining "
        "with the updated data pipeline."
    )


def validate_checkpoint_state_dim_contract(
    raw_checkpoint: Any,
    policy_config: Mapping[str, Any],
) -> None:
    """Validate checkpoint state_dim metadata against the eval policy config."""
    if not isinstance(raw_checkpoint, dict):
        return
    raw_config = raw_checkpoint.get("policy_config")
    if raw_config is None:
        raw_config = raw_checkpoint.get("config")
    if not isinstance(raw_config, dict):
        return
    ckpt_state_dim = raw_config.get("state_dim")
    if ckpt_state_dim is None and isinstance(raw_config.get("policy_config"), dict):
        ckpt_state_dim = raw_config["policy_config"].get("state_dim")
    if ckpt_state_dim is None:
        return
    configured_state_dim = policy_config.get("state_dim")
    if configured_state_dim is None:
        return
    if int(ckpt_state_dim) != int(configured_state_dim):
        raise ValueError(
            "Checkpoint state_dim does not match eval policy_config.state_dim: "
            f"checkpoint={int(ckpt_state_dim)}, "
            f"policy_config={int(configured_state_dim)}."
        )


def _flat_stat_dim(value: Any) -> int:
    return int(np.asarray(value).reshape(-1).shape[0])


def _normalize_stats_keys(value: Any) -> list[str]:
    keys = []
    for item in np.asarray(value, dtype=object).reshape(-1):
        if isinstance(item, bytes):
            item = item.decode("utf-8")
        keys.append(str(item))
    return keys
