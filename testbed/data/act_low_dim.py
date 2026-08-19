"""Canonical low-dimensional ACT observation assembly.

This module owns the ordering and flattening of the numeric inputs that are
concatenated before ACT training and frozen-policy replay.  Keeping the
assembly here prevents an offline audit from accidentally constructing a
different proprioceptive vector from the training data path.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

SUPPORTED_ACT_LOW_DIM_KEYS = (
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
"""Low-dimensional fields accepted by the ACT training data contract."""


def assemble_act_low_dim_observation(
    *,
    qpos: np.ndarray,
    qvel: np.ndarray,
    goal_tokens: np.ndarray | None = None,
    cell_entry_tokens: np.ndarray | None = None,
    dig_cut_tokens: np.ndarray | None = None,
    dig_depth_profile_tokens_v1: np.ndarray | None = None,
    return_target_tokens: np.ndarray | None = None,
    return_relocate_tokens_v1: np.ndarray | None = None,
    return_start_envelope_tokens_v1: np.ndarray | None = None,
    low_dim_keys: Sequence[str],
) -> np.ndarray:
    """Concatenate requested ACT inputs in the configured key order.

    The implementation deliberately preserves the historical training data
    semantics: vector inputs become one flat vector, while any sequence input
    selects sequence mode and produces one concatenated row per timestep.
    Callers must use the same ``low_dim_keys`` sequence as the frozen
    checkpoint and its normalisation statistics.
    """

    qpos_arr = np.asarray(qpos, dtype=np.float32)
    qvel_arr = np.asarray(qvel, dtype=np.float32)
    goal_tokens_arr = (
        None if goal_tokens is None else np.asarray(goal_tokens, dtype=np.float32)
    )
    cell_entry_tokens_arr = (
        None
        if cell_entry_tokens is None
        else np.asarray(cell_entry_tokens, dtype=np.float32)
    )
    dig_cut_tokens_arr = (
        None if dig_cut_tokens is None else np.asarray(dig_cut_tokens, dtype=np.float32)
    )
    dig_depth_profile_tokens_arr = (
        None
        if dig_depth_profile_tokens_v1 is None
        else np.asarray(dig_depth_profile_tokens_v1, dtype=np.float32)
    )
    return_target_tokens_arr = (
        None
        if return_target_tokens is None
        else np.asarray(return_target_tokens, dtype=np.float32)
    )
    return_relocate_tokens_arr = (
        None
        if return_relocate_tokens_v1 is None
        else np.asarray(return_relocate_tokens_v1, dtype=np.float32)
    )
    return_start_envelope_tokens_arr = (
        None
        if return_start_envelope_tokens_v1 is None
        else np.asarray(return_start_envelope_tokens_v1, dtype=np.float32)
    )
    sequence_mode = (
        qpos_arr.ndim > 1
        or qvel_arr.ndim > 1
        or (goal_tokens_arr is not None and goal_tokens_arr.ndim > 1)
        or (cell_entry_tokens_arr is not None and cell_entry_tokens_arr.ndim > 1)
        or (dig_cut_tokens_arr is not None and dig_cut_tokens_arr.ndim > 1)
        or (
            dig_depth_profile_tokens_arr is not None
            and dig_depth_profile_tokens_arr.ndim > 1
        )
        or (
            return_target_tokens_arr is not None
            and return_target_tokens_arr.ndim > 1
        )
        or (
            return_relocate_tokens_arr is not None
            and return_relocate_tokens_arr.ndim > 1
        )
        or (
            return_start_envelope_tokens_arr is not None
            and return_start_envelope_tokens_arr.ndim > 1
        )
    )
    parts: list[np.ndarray] = []
    for key in low_dim_keys:
        if key == "qpos":
            part = qpos_arr
        elif key == "qvel":
            part = qvel_arr
        elif key == "goal_tokens":
            if goal_tokens_arr is None:
                raise KeyError(
                    "Requested low_dim key 'goal_tokens' but /v2/step/goal_tokens is missing."
                )
            part = goal_tokens_arr
        elif key == "cell_entry_tokens":
            if cell_entry_tokens_arr is None:
                raise KeyError(
                    "Requested low_dim key 'cell_entry_tokens' but "
                    "/v2/step/cell_entry_tokens is missing."
                )
            part = cell_entry_tokens_arr
        elif key == "dig_cut_tokens":
            if dig_cut_tokens_arr is None:
                raise KeyError(
                    "Requested low_dim key 'dig_cut_tokens' but "
                    "/v2/step/dig_cut_tokens is missing."
                )
            part = dig_cut_tokens_arr
        elif key == "dig_depth_profile_tokens_v1":
            if dig_depth_profile_tokens_arr is None:
                raise KeyError(
                    "Requested low_dim key 'dig_depth_profile_tokens_v1' but "
                    "/v2/step/dig_depth_profile_tokens_v1 is missing."
                )
            part = dig_depth_profile_tokens_arr
        elif key == "return_target_tokens":
            if return_target_tokens_arr is None:
                raise KeyError(
                    "Requested low_dim key 'return_target_tokens' but "
                    "/v2/step/return_target_tokens is missing."
                )
            part = return_target_tokens_arr
        elif key == "return_relocate_tokens_v1":
            if return_relocate_tokens_arr is None:
                raise KeyError(
                    "Requested low_dim key 'return_relocate_tokens_v1' but "
                    "a relocate target could not be derived from "
                    "/v2/step/return_target_tokens or metadata next_operator fields."
                )
            part = return_relocate_tokens_arr
        elif key == "return_start_envelope_tokens_v1":
            if return_start_envelope_tokens_arr is None:
                raise KeyError(
                    "Requested low_dim key 'return_start_envelope_tokens_v1' but "
                    "/v2/step/return_start_envelope_tokens_v1 is missing."
                )
            part = return_start_envelope_tokens_arr
        else:
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


__all__ = [
    "SUPPORTED_ACT_LOW_DIM_KEYS",
    "assemble_act_low_dim_observation",
]
