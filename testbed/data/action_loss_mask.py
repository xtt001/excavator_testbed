"""Shared semantics for optional per-step ACT action-loss masks."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np

from testbed.data.schema import DS_V2_STEP_ACTION_LOSS_MASK


ACTION_LOSS_MASK_SCOPE_LOSS_ONLY = "loss_only"
ACTION_LOSS_MASK_SCOPE_LOSS_SAMPLING_STATS = "loss_sampling_stats"
ACTION_LOSS_MASK_SCOPES = (
    ACTION_LOSS_MASK_SCOPE_LOSS_ONLY,
    ACTION_LOSS_MASK_SCOPE_LOSS_SAMPLING_STATS,
)


def normalize_action_loss_mask_scope(value: str | None) -> str:
    scope = str(value or ACTION_LOSS_MASK_SCOPE_LOSS_ONLY).strip().lower()
    if scope not in ACTION_LOSS_MASK_SCOPES:
        raise ValueError(
            f"Unsupported action_loss_mask_scope {scope!r}; expected one of "
            f"{', '.join(ACTION_LOSS_MASK_SCOPES)}."
        )
    return scope


def read_action_loss_mask(
    h5_file: Any,
    *,
    expected_length: int,
    required: bool,
) -> np.ndarray | None:
    if DS_V2_STEP_ACTION_LOSS_MASK not in h5_file:
        if required:
            raise ValueError(
                f"Clean mask scope requires /{DS_V2_STEP_ACTION_LOSS_MASK}."
            )
        return None
    mask = np.asarray(
        h5_file[DS_V2_STEP_ACTION_LOSS_MASK][()], dtype=np.uint8
    ).reshape(-1)
    if mask.shape != (int(expected_length),):
        raise ValueError(
            f"/{DS_V2_STEP_ACTION_LOSS_MASK} length {mask.shape[0]} does not "
            f"match episode length {expected_length}."
        )
    if np.any((mask != 0) & (mask != 1)):
        raise ValueError(f"/{DS_V2_STEP_ACTION_LOSS_MASK} must contain only 0 or 1.")
    return mask


def valid_stats_rows(
    *,
    episode_length: int,
    action_loss_mask: np.ndarray | None,
    scope: str,
) -> np.ndarray:
    resolved_scope = normalize_action_loss_mask_scope(scope)
    if resolved_scope == ACTION_LOSS_MASK_SCOPE_LOSS_ONLY:
        return np.ones(int(episode_length), dtype=bool)
    if action_loss_mask is None:
        raise ValueError("loss_sampling_stats requires action_loss_mask.")
    valid = np.asarray(action_loss_mask, dtype=np.uint8).reshape(-1) == 1
    if valid.shape != (int(episode_length),):
        raise ValueError("action_loss_mask length does not match episode length.")
    if not np.any(valid):
        raise ValueError("action_loss_mask has no valid rows for normalization stats.")
    return valid


def select_sample_start_index(
    *,
    episode_length: int,
    action_loss_mask: np.ndarray | None,
    scope: str,
    choice_fn: Callable[[np.ndarray], int] | None = None,
) -> int:
    resolved_scope = normalize_action_loss_mask_scope(scope)
    length = int(episode_length)
    if length <= 0:
        raise ValueError("Cannot sample from an empty episode.")
    candidates = np.arange(length, dtype=np.int64)
    if resolved_scope == ACTION_LOSS_MASK_SCOPE_LOSS_SAMPLING_STATS:
        if action_loss_mask is None:
            raise ValueError("loss_sampling_stats requires action_loss_mask.")
        mask = np.asarray(action_loss_mask, dtype=np.uint8).reshape(-1)
        if mask.shape != (length,):
            raise ValueError("action_loss_mask length does not match episode length.")
        candidates = np.flatnonzero(mask == 1).astype(np.int64)
        if candidates.size == 0:
            raise ValueError("action_loss_mask has no valid sample start.")
    chooser = choice_fn or np.random.choice
    return int(chooser(candidates))


__all__ = [
    "ACTION_LOSS_MASK_SCOPES",
    "ACTION_LOSS_MASK_SCOPE_LOSS_ONLY",
    "ACTION_LOSS_MASK_SCOPE_LOSS_SAMPLING_STATS",
    "normalize_action_loss_mask_scope",
    "read_action_loss_mask",
    "select_sample_start_index",
    "valid_stats_rows",
]
