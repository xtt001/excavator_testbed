"""
EpisodicDataset, get_norm_stats, load_data.

Directly migrated from legacy/utils.py with clean imports and added
docstrings. Public API is backward-compatible with legacy callers.
"""

from __future__ import annotations

import datetime
from collections import OrderedDict
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml
from torch.utils.data import DataLoader, Dataset

from testbed.data.action_loss_mask import (
    ACTION_LOSS_MASK_SCOPE_LOSS_ONLY,
    ACTION_LOSS_MASK_SCOPE_LOSS_SAMPLING_STATS,
    normalize_action_loss_mask_scope,
    read_action_loss_mask,
    select_sample_start_index,
    valid_stats_rows,
)
from testbed.data.camera_images import read_camera_rgb
from testbed.data.dig_depth_profile_v2_4 import DIG_DEPTH_PROFILE_TOKEN_DIM
from testbed.data.hdf5_io import list_episodes
from testbed.data.image_masks import (
    apply_image_mask,
    mask_dataset_path,
    require_mask_dataset,
)
from testbed.data.operator_first_v2_2 import (
    DIG_CUT_LENGTH_SCALE_M,
    DIG_CUT_POSITION_SCALE_M,
    DIG_CUT_TOKEN_DIM,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_TARGET_TOKEN_DIM,
)
from testbed.data.schema import (
    DS_V2_STEP_ACTION_LOSS_MASK,
    DS_V2_STEP_CELL_ENTRY_TOKENS,
    DS_V2_STEP_DIG_CUT_TOKENS,
    DS_V2_STEP_DIG_DEPTH_PROFILE_TOKENS_V1,
    DS_V2_STEP_DIG_GOAL_VALID_MASK,
    DS_V2_STEP_DIG_OUTCOME_TARGETS,
    DS_V2_STEP_GOAL_TOKENS,
    DS_V2_STEP_RETURN_GOAL_VALID_MASK,
    DS_V2_STEP_RETURN_OUTCOME_TARGETS,
    DS_V2_STEP_RETURN_START_ENVELOPE_TOKENS_V1,
    DS_V2_STEP_RETURN_TARGET_TOKENS,
)
from testbed.data.v2_1 import GOAL_TOKEN_DIM
from testbed.planner.cell_entry import CELL_ENTRY_TOKEN_DIM

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

SUPPORTED_SUPERVISION_KEYS = (
    "dig_outcome_targets",
    "return_outcome_targets",
    "return_relocate_outcome_targets_v1",
)

_SUPERVISION_DATASET_PATHS = {
    "dig_outcome_targets": DS_V2_STEP_DIG_OUTCOME_TARGETS,
    "return_outcome_targets": DS_V2_STEP_RETURN_OUTCOME_TARGETS,
    "return_relocate_outcome_targets_v1": DS_V2_STEP_RETURN_OUTCOME_TARGETS,
}

_SUPERVISION_MASK_PATHS = {
    "dig_outcome_targets": DS_V2_STEP_DIG_GOAL_VALID_MASK,
    "return_outcome_targets": DS_V2_STEP_RETURN_GOAL_VALID_MASK,
    "return_relocate_outcome_targets_v1": DS_V2_STEP_RETURN_GOAL_VALID_MASK,
}


def _normalize_low_dim_keys(
    low_dim_keys: list[str] | tuple[str, ...] | None,
) -> list[str]:
    keys = ["qpos"] if not low_dim_keys else [str(key) for key in low_dim_keys]
    invalid = [key for key in keys if key not in SUPPORTED_LOW_DIM_KEYS]
    if invalid:
        raise ValueError(
            f"Unsupported low_dim_keys {invalid}. "
            f"Supported keys: {SUPPORTED_LOW_DIM_KEYS}."
        )
    return keys


def _normalize_supervision_keys(
    supervision_keys: list[str] | tuple[str, ...] | None,
) -> list[str]:
    keys = [] if not supervision_keys else [str(key) for key in supervision_keys]
    invalid = [key for key in keys if key not in SUPPORTED_SUPERVISION_KEYS]
    if invalid:
        raise ValueError(
            f"Unsupported supervision_keys {invalid}. "
            f"Supported keys: {SUPPORTED_SUPERVISION_KEYS}."
        )
    if len(keys) > 1:
        raise ValueError(
            "Only one supervision key is supported per ACT run for now. "
            f"Got {keys}."
        )
    return keys


def _assemble_low_dim_observation(
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
    low_dim_keys: list[str],
) -> np.ndarray:
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


# ─── Normalization stats ──────────────────────────────────────────────────────


def get_norm_stats(
    dataset_dir: str | Path,
    num_episodes: int,
    episode_ids: list[int] | None = None,
    low_dim_keys: list[str] | tuple[str, ...] | None = None,
    action_loss_mask_scope: str = ACTION_LOSS_MASK_SCOPE_LOSS_ONLY,
) -> dict[str, np.ndarray]:
    """
    Compute mean/std normalization statistics from a set of episodes.

    Parameters
    ----------
    dataset_dir   Directory containing episode_N.hdf5 files.
    num_episodes  Maximum number of episodes to consider.
    episode_ids   Explicit list of episode indices to use.  If None, uses
                  range(num_episodes) and skips missing files.

    Returns
    -------
    {
      "action_mean":  (Na,)  float32
      "action_std":   (Na,)  float32
      "proprio_mean": (Np,)  float32
      "proprio_std":  (Np,)  float32
      "example_proprio": (T, Np) float32
      "qpos_mean":    (Nq,)  float32    legacy alias when low_dim_keys=['qpos']
      "qpos_std":     (Nq,)  float32    legacy alias when low_dim_keys=['qpos']
      "example_qpos": (T, Nq) float32   legacy alias when low_dim_keys=['qpos']
    }
    """
    import h5py

    dataset_dir = Path(dataset_dir)
    selected_low_dim_keys = _normalize_low_dim_keys(low_dim_keys)
    resolved_mask_scope = normalize_action_loss_mask_scope(action_loss_mask_scope)
    all_proprio_data: list[torch.Tensor] = []
    all_qpos_data: list[torch.Tensor] = []
    all_action_data: list[torch.Tensor] = []
    example_qpos = None
    example_proprio = None

    if episode_ids is not None:
        ids = [int(ep_id) for ep_id in episode_ids]
    else:
        ids = _select_episode_ids(dataset_dir, num_episodes)
    for ep_idx in ids:
        p = dataset_dir / f"episode_{ep_idx}.hdf5"
        if not p.exists():
            continue
        with h5py.File(p, "r") as f:
            qpos = f["/observations/qpos"][()]
            qvel = f["/observations/qvel"][()]
            action = f["/action"][()]
            goal_tokens = (
                _read_goal_tokens_dataset(f)
                if "goal_tokens" in selected_low_dim_keys
                else None
            )
            cell_entry_tokens = (
                _read_cell_entry_tokens_dataset(f)
                if "cell_entry_tokens" in selected_low_dim_keys
                else None
            )
            dig_cut_tokens = (
                _read_dig_cut_tokens_dataset(f)
                if "dig_cut_tokens" in selected_low_dim_keys
                else None
            )
            dig_depth_profile_tokens = (
                _read_dig_depth_profile_tokens_dataset(f)
                if "dig_depth_profile_tokens_v1" in selected_low_dim_keys
                else None
            )
            return_target_tokens = (
                _read_return_target_tokens_dataset(f)
                if "return_target_tokens" in selected_low_dim_keys
                else None
            )
            return_relocate_tokens = (
                _read_return_relocate_tokens_dataset(f)
                if "return_relocate_tokens_v1" in selected_low_dim_keys
                else None
            )
            return_start_envelope_tokens = (
                _read_return_start_envelope_tokens_dataset(f)
                if "return_start_envelope_tokens_v1" in selected_low_dim_keys
                else None
            )
            stats_mask = (
                read_action_loss_mask(
                    f,
                    expected_length=int(action.shape[0]),
                    required=True,
                )
                if resolved_mask_scope
                == ACTION_LOSS_MASK_SCOPE_LOSS_SAMPLING_STATS
                else None
            )
        proprio = _assemble_low_dim_observation(
            qpos=qpos,
            qvel=qvel,
            goal_tokens=goal_tokens,
            cell_entry_tokens=cell_entry_tokens,
            dig_cut_tokens=dig_cut_tokens,
            dig_depth_profile_tokens_v1=dig_depth_profile_tokens,
            return_target_tokens=return_target_tokens,
            return_relocate_tokens_v1=return_relocate_tokens,
            return_start_envelope_tokens_v1=return_start_envelope_tokens,
            low_dim_keys=selected_low_dim_keys,
        )
        valid_rows = valid_stats_rows(
            episode_length=int(action.shape[0]),
            action_loss_mask=stats_mask,
            scope=resolved_mask_scope,
        )
        qpos = qpos[valid_rows]
        action = action[valid_rows]
        proprio = proprio[valid_rows]
        all_proprio_data.append(torch.from_numpy(proprio))
        all_qpos_data.append(torch.from_numpy(qpos))
        all_action_data.append(torch.from_numpy(action))
        example_qpos = qpos
        example_proprio = proprio

    if not all_proprio_data:
        raise FileNotFoundError(
            f"No episodes found under {dataset_dir}. "
            "Expected files like episode_0.hdf5."
        )

    # NOTE: Do NOT assume all episodes share the same timestep length.
    # Success-truncated AGX demos are intentionally variable-length.
    # Stats should be computed over the concatenated time axis, not by stacking
    # episodes into a rectangular (N, T, D) tensor.
    proprio_tensor = torch.cat(all_proprio_data, dim=0)  # (sum_T, Np)
    qpos_tensor = torch.cat(all_qpos_data, dim=0)  # (sum_T, Nq)
    action_tensor = torch.cat(all_action_data, dim=0)  # (sum_T, Na)

    action_mean = action_tensor.mean(dim=0, keepdim=True)
    action_std = action_tensor.std(dim=0, keepdim=True).clamp(min=1e-2)
    proprio_mean = proprio_tensor.mean(dim=0, keepdim=True)
    proprio_std = proprio_tensor.std(dim=0, keepdim=True).clamp(min=1e-2)
    qpos_mean = qpos_tensor.mean(dim=0, keepdim=True)
    qpos_std = qpos_tensor.std(dim=0, keepdim=True).clamp(min=1e-2)

    stats = {
        "action_mean": action_mean.numpy().squeeze().astype(np.float32),
        "action_std": action_std.numpy().squeeze().astype(np.float32),
        "proprio_mean": proprio_mean.numpy().squeeze().astype(np.float32),
        "proprio_std": proprio_std.numpy().squeeze().astype(np.float32),
        "example_proprio": example_proprio,
        "proprio_keys": np.asarray(selected_low_dim_keys, dtype=object),
        "proprio_dim": int(proprio_tensor.shape[1]),
        "qpos_only_dim": int(qpos_tensor.shape[1]),
    }
    if selected_low_dim_keys == ["qpos"]:
        stats.update(
            {
                "qpos_mean": qpos_mean.numpy().squeeze().astype(np.float32),
                "qpos_std": qpos_std.numpy().squeeze().astype(np.float32),
                "example_qpos": example_qpos,
            }
        )
    return stats


# ─── Dataset ─────────────────────────────────────────────────────────────────


class EpisodicDataset(Dataset):
    """
    PyTorch Dataset over a set of HDF5 episode files.

    Each __getitem__ samples a random start timestep t0 from episode_i,
    then returns:
      image_data  : (n_cams, C, H, W)   float32 [0, 1]
      proprio_data: (Np,)               float32 normalised
      action_data : (T - t0, Na)        float32 normalised + zero-padded to T
      is_pad      : (T,)                bool    True where zero-padded

    Parameters
    ----------
    episode_ids   List of integer episode indices.
    dataset_dir   Directory with episode_N.hdf5 files.
    camera_names  Cameras to include (in order).
    norm_stats    Dict returned by get_norm_stats.
    """

    def __init__(
        self,
        episode_ids: list[int],
        dataset_dir: str | Path,
        camera_names: list[str],
        norm_stats: dict[str, np.ndarray],
        episode_len: int | None = None,
        low_dim_keys: list[str] | tuple[str, ...] | None = None,
        supervision_keys: list[str] | tuple[str, ...] | None = None,
        image_mask_config: dict[str, Any] | None = None,
        hdf5_cache_size: int = 0,
        action_loss_mask_scope: str = ACTION_LOSS_MASK_SCOPE_LOSS_ONLY,
    ):
        super().__init__()
        self.episode_ids = episode_ids
        self.dataset_dir = Path(dataset_dir)
        self.camera_names = camera_names
        self.norm_stats = norm_stats
        self.episode_len = int(episode_len) if episode_len is not None else None
        self.low_dim_keys = _normalize_low_dim_keys(low_dim_keys)
        self.supervision_keys = _normalize_supervision_keys(supervision_keys)
        self.image_mask_config = dict(image_mask_config or {})
        self.hdf5_cache_size = max(0, int(hdf5_cache_size))
        self.action_loss_mask_scope = normalize_action_loss_mask_scope(
            action_loss_mask_scope
        )
        self._h5_cache: OrderedDict[int, Any] = OrderedDict()
        self.is_sim: bool | None = None
        # Warm-up to populate self.is_sim
        self.__getitem__(0)
        self.close()

    def __len__(self) -> int:
        return len(self.episode_ids)

    def __getitem__(self, index: int):
        import h5py

        ep_id = self.episode_ids[index]
        path = self.dataset_dir / f"episode_{ep_id}.hdf5"

        close_after_read = self.hdf5_cache_size <= 0
        f = h5py.File(path, "r") if close_after_read else self._cached_h5(ep_id, path)
        try:
            is_sim: bool = bool(f.attrs.get("sim", True))
            original_action_shape = f["/action"].shape
            T = original_action_shape[0]

            # ── sample start timestep ─────────────────────────────────────
            sampling_mask = (
                read_action_loss_mask(
                    f,
                    expected_length=int(T),
                    required=True,
                )
                if self.action_loss_mask_scope
                == ACTION_LOSS_MASK_SCOPE_LOSS_SAMPLING_STATS
                else None
            )
            t0 = select_sample_start_index(
                episode_length=int(T),
                action_loss_mask=sampling_mask,
                scope=self.action_loss_mask_scope,
            )

            # ── observation at t0 ─────────────────────────────────────────
            qpos = f["/observations/qpos"][t0]
            qvel = f["/observations/qvel"][t0]
            goal_tokens = (
                _read_goal_tokens_dataset(f, index=t0)
                if "goal_tokens" in self.low_dim_keys
                else None
            )
            cell_entry_tokens = (
                _read_cell_entry_tokens_dataset(f, index=t0)
                if "cell_entry_tokens" in self.low_dim_keys
                else None
            )
            dig_cut_tokens = (
                _read_dig_cut_tokens_dataset(f, index=t0)
                if "dig_cut_tokens" in self.low_dim_keys
                else None
            )
            dig_depth_profile_tokens = (
                _read_dig_depth_profile_tokens_dataset(f, index=t0)
                if "dig_depth_profile_tokens_v1" in self.low_dim_keys
                else None
            )
            return_target_tokens = (
                _read_return_target_tokens_dataset(f, index=t0)
                if "return_target_tokens" in self.low_dim_keys
                else None
            )
            return_relocate_tokens = (
                _read_return_relocate_tokens_dataset(f, index=t0)
                if "return_relocate_tokens_v1" in self.low_dim_keys
                else None
            )
            return_start_envelope_tokens = (
                _read_return_start_envelope_tokens_dataset(f, index=t0)
                if "return_start_envelope_tokens_v1" in self.low_dim_keys
                else None
            )
            supervision_target = None
            supervision_mask = None
            if self.supervision_keys:
                supervision_target, supervision_mask = _read_supervision_at_step(
                    f,
                    key=self.supervision_keys[0],
                    index=t0,
                )
            proprio = _assemble_low_dim_observation(
                qpos=qpos,
                qvel=qvel,
                goal_tokens=goal_tokens,
                cell_entry_tokens=cell_entry_tokens,
                dig_cut_tokens=dig_cut_tokens,
                dig_depth_profile_tokens_v1=dig_depth_profile_tokens,
                return_target_tokens=return_target_tokens,
                return_relocate_tokens_v1=return_relocate_tokens,
                return_start_envelope_tokens_v1=return_start_envelope_tokens,
                low_dim_keys=self.low_dim_keys,
            )
            image_dict = {}
            for cam in self.camera_names:
                image = read_camera_rgb(f, cam, t0)
                mask = None
                mask_path = mask_dataset_path(
                    camera_name=cam,
                    mask_config=self.image_mask_config,
                )
                if mask_path is not None:
                    if mask_path in f:
                        mask = f[mask_path][t0]
                    elif require_mask_dataset(
                        camera_name=cam,
                        mask_config=self.image_mask_config,
                    ):
                        raise KeyError(
                            f"Episode {ep_id} is missing required image mask dataset "
                            f"{mask_path!r} for camera {cam!r}."
                        )
                image_dict[cam] = apply_image_mask(
                    image,
                    camera_name=cam,
                    mask_config=self.image_mask_config,
                    mask=mask,
                )

            # ── action from t0 onward (legacy hack for real data) ─────────
            if is_sim:
                action = f["/action"][t0:]
                action_loss_mask = _read_action_loss_mask(f, start=t0)
                action_len = T - t0
            else:
                start = max(0, t0 - 1)
                action = f["/action"][start:]
                action_loss_mask = _read_action_loss_mask(f, start=start)
                action_len = T - start
        finally:
            if close_after_read:
                f.close()

        self.is_sim = is_sim

        # ── pad action to fixed dataset length for batching ────────────────
        target_len = self.episode_len if self.episode_len is not None else T
        if T > target_len:
            raise ValueError(
                f"Episode {ep_id} has length {T}, which exceeds configured "
                f"episode_len {target_len}. Increase task.episode_len or re-record."
            )

        padded_action = np.zeros(
            (target_len, original_action_shape[1]), dtype=np.float32
        )
        padded_action[:action_len] = action
        is_pad = np.ones(target_len, dtype=bool)
        is_pad[:action_len] = False
        if action_loss_mask is not None:
            loss_mask = np.asarray(
                action_loss_mask[:action_len], dtype=np.uint8
            ).reshape(-1)
            if loss_mask.shape[0] != action_len:
                raise ValueError(
                    f"Episode {ep_id} action_loss_mask length {loss_mask.shape[0]} "
                    f"does not match action_len {action_len}."
                )
            is_pad[:action_len] |= loss_mask == 0

        # ── assemble camera tensor ─────────────────────────────────────────
        all_cam_images = np.stack(
            [image_dict[c] for c in self.camera_names], axis=0
        )  # (n_cams, H, W, 3)

        # ── convert to tensors ────────────────────────────────────────────
        image_data = torch.from_numpy(all_cam_images)
        proprio_data = torch.from_numpy(proprio).float()
        action_data = torch.from_numpy(padded_action).float()
        is_pad_t = torch.from_numpy(is_pad)

        # channel-last → channel-first + normalize to [0, 1]
        image_data = torch.einsum("k h w c -> k c h w", image_data).float() / 255.0

        # normalise proprio and actions
        action_data = (
            action_data - torch.from_numpy(self.norm_stats["action_mean"])
        ) / torch.from_numpy(self.norm_stats["action_std"])
        proprio_data = (
            proprio_data - torch.from_numpy(self.norm_stats["proprio_mean"])
        ) / torch.from_numpy(self.norm_stats["proprio_std"])

        if self.supervision_keys:
            return {
                "image": image_data,
                "proprio": proprio_data,
                "action": action_data,
                "is_pad": is_pad_t,
                "outcome_target": torch.from_numpy(
                    np.asarray(supervision_target, dtype=np.float32)
                ).float(),
                "outcome_mask": torch.from_numpy(
                    np.asarray(supervision_mask, dtype=np.float32)
                ).float(),
                "supervision_key": self.supervision_keys[0],
            }

        return image_data, proprio_data, action_data, is_pad_t

    def close(self) -> None:
        for handle in self._h5_cache.values():
            try:
                handle.close()
            except Exception:
                pass
        self._h5_cache.clear()

    def __del__(self) -> None:
        self.close()

    def __getstate__(self) -> dict[str, Any]:
        state = dict(self.__dict__)
        state["_h5_cache"] = OrderedDict()
        return state

    def _cached_h5(self, ep_id: int, path: Path):
        import h5py

        if ep_id in self._h5_cache:
            handle = self._h5_cache.pop(ep_id)
            self._h5_cache[ep_id] = handle
            return handle
        handle = h5py.File(path, "r")
        self._h5_cache[ep_id] = handle
        while len(self._h5_cache) > self.hdf5_cache_size:
            _, old_handle = self._h5_cache.popitem(last=False)
            old_handle.close()
        return handle


# ─── load_data ────────────────────────────────────────────────────────────────


def load_data(
    dataset_dir: str | Path,
    num_episodes: int,
    camera_names: list[str],
    episode_len: int | None,
    batch_size_train: int,
    batch_size_val: int,
    num_workers: int = 1,
    prefetch_factor: int = 1,
    persistent_workers: bool = False,
    pin_memory: bool = True,
    *,
    split_seed: int = 0,
    train_split_ratio: float = 0.8,
    split_path: str | Path | None = None,
    reuse_split: bool = True,
    low_dim_keys: list[str] | tuple[str, ...] | None = None,
    supervision_keys: list[str] | tuple[str, ...] | None = None,
    metadata_filters: dict[str, Any] | None = None,
    image_mask_config: dict[str, Any] | None = None,
    hdf5_cache_size: int = 0,
    action_loss_mask_scope: str = ACTION_LOSS_MASK_SCOPE_LOSS_ONLY,
) -> tuple[DataLoader, DataLoader, dict, bool, dict[str, Any]]:
    """
    Build train/val DataLoaders from an HDF5 dataset directory.

    Returns
    -------
    train_loader, val_loader, norm_stats, is_sim, split_info
    """
    dataset_dir = Path(dataset_dir)
    print(f"\nData from: {dataset_dir}\n")

    available = _select_episode_ids(dataset_dir, num_episodes)

    if not available:
        raise FileNotFoundError(
            f"No episodes found under {dataset_dir}. "
            "Expected files like episode_0.hdf5."
        )
    if num_episodes > 0 and len(available) < num_episodes:
        print(
            f"Warning: requested {num_episodes} episodes "
            f"but found {len(available)}. Using available episodes."
        )

    # Filter to episodes where action_dim matches qpos_dim.
    # This removes legacy episodes recorded with EE-space actions (wrong format).
    # The correct pipeline saves joint-space qpos as actions, so action_dim == qpos_dim.
    import h5py

    dim_info = {}
    length_info = {}
    metadata_filters = dict(metadata_filters or {})
    metadata_filter_rejects = 0
    for ep_id in available:
        p = dataset_dir / f"episode_{ep_id}.hdf5"
        with h5py.File(p, "r") as f:
            if metadata_filters and not _episode_matches_metadata_filters(
                f,
                metadata_filters,
            ):
                metadata_filter_rejects += 1
                continue
            dim_info[ep_id] = (
                f["/action"].shape[1],
                f["/observations/qpos"].shape[1],
            )
            length_info[ep_id] = int(f["/action"].shape[0])
    available = [ep_id for ep_id in available if ep_id in dim_info]
    if metadata_filter_rejects:
        print(
            f"Metadata filters skipped {metadata_filter_rejects} episode(s): "
            f"{metadata_filters}"
        )
    filtered = [i for i in available if dim_info[i][0] == dim_info[i][1]]
    dropped = len(available) - len(filtered)
    if dropped:
        act_dims = set(d[0] for d in dim_info.values())
        qpos_dim = dim_info[available[0]][1]
        print(
            f"Warning: skipped {dropped} episode(s) where action_dim != qpos_dim ({qpos_dim}). "
            f"Found action dims: {act_dims}. Re-collect data with `tb-record` to fix."
        )
    available = filtered

    if not available:
        raise FileNotFoundError(
            f"No valid episodes found under {dataset_dir} (action_dim != qpos_dim for all). "
            "Re-collect data with `tb-record`."
        )

    max_episode_len = max(length_info[ep_id] for ep_id in available)
    target_episode_len = (
        int(episode_len) if episode_len is not None else max_episode_len
    )
    if max_episode_len > target_episode_len:
        raise ValueError(
            f"Dataset contains an episode of length {max_episode_len}, but configured "
            f"episode_len is only {target_episode_len}. Increase task.episode_len."
        )

    train_ids, val_ids, split_info = _resolve_episode_split(
        dataset_dir=dataset_dir,
        available_episode_ids=available,
        requested_num_episodes=int(num_episodes),
        split_seed=int(split_seed),
        train_split_ratio=float(train_split_ratio),
        split_path=None if split_path is None else Path(split_path),
        reuse_split=bool(reuse_split),
    )

    selected_low_dim_keys = _normalize_low_dim_keys(low_dim_keys)
    selected_supervision_keys = _normalize_supervision_keys(supervision_keys)
    resolved_mask_scope = normalize_action_loss_mask_scope(action_loss_mask_scope)
    norm_stats = get_norm_stats(
        dataset_dir,
        num_episodes,
        episode_ids=available,
        low_dim_keys=selected_low_dim_keys,
        action_loss_mask_scope=resolved_mask_scope,
    )

    train_ds = EpisodicDataset(
        train_ids,
        dataset_dir,
        camera_names,
        norm_stats,
        episode_len=target_episode_len,
        low_dim_keys=selected_low_dim_keys,
        supervision_keys=selected_supervision_keys,
        image_mask_config=image_mask_config,
        hdf5_cache_size=hdf5_cache_size,
        action_loss_mask_scope=resolved_mask_scope,
    )
    val_ds = EpisodicDataset(
        val_ids,
        dataset_dir,
        camera_names,
        norm_stats,
        episode_len=target_episode_len,
        low_dim_keys=selected_low_dim_keys,
        supervision_keys=selected_supervision_keys,
        image_mask_config=image_mask_config,
        hdf5_cache_size=hdf5_cache_size,
        action_loss_mask_scope=resolved_mask_scope,
    )

    split_info["dataset_max_episode_len"] = int(max_episode_len)
    split_info["loader_episode_len"] = int(target_episode_len)
    split_info["low_dim_keys"] = list(selected_low_dim_keys)
    split_info["supervision_keys"] = list(selected_supervision_keys)
    split_info["metadata_filters"] = metadata_filters
    split_info["low_dim_dim"] = int(norm_stats["proprio_dim"])
    split_info["image_mask_enabled"] = bool(image_mask_config)
    split_info["hdf5_cache_size"] = int(hdf5_cache_size)
    split_info["action_loss_mask_scope"] = resolved_mask_scope

    loader_kw: dict = {"pin_memory": pin_memory, "num_workers": num_workers}
    if num_workers > 0:
        loader_kw["prefetch_factor"] = prefetch_factor
        loader_kw["persistent_workers"] = bool(persistent_workers)

    train_loader = DataLoader(
        train_ds, batch_size=batch_size_train, shuffle=True, **loader_kw
    )
    val_loader = DataLoader(
        val_ds, batch_size=batch_size_val, shuffle=True, **loader_kw
    )

    return train_loader, val_loader, norm_stats, train_ds.is_sim, split_info


def _episode_matches_metadata_filters(h5_file, filters: dict[str, Any]) -> bool:
    metadata_attrs = {}
    if "metadata" in h5_file:
        metadata_attrs.update(dict(h5_file["metadata"].attrs))
    metadata_attrs.update(dict(h5_file.attrs))
    for key, expected in filters.items():
        actual = metadata_attrs.get(str(key))
        if isinstance(actual, bytes):
            actual = actual.decode()
        if isinstance(actual, np.generic):
            actual = actual.item()
        actual_str = str(actual)
        if isinstance(expected, (list, tuple, set)):
            expected_values = {str(item) for item in expected}
            if actual_str not in expected_values:
                return False
        elif actual_str != str(expected):
            return False
    return True


def _select_episode_ids(dataset_dir: str | Path, num_episodes: int) -> list[int]:
    dataset_dir = Path(dataset_dir)
    discovered = [
        int(path.stem.split("_", 1)[1]) for path in list_episodes(dataset_dir)
    ]
    discovered = sorted(discovered)
    if num_episodes <= 0:
        return discovered
    return [episode_id for episode_id in discovered if episode_id < int(num_episodes)]


def _resolve_episode_split(
    *,
    dataset_dir: Path,
    available_episode_ids: list[int],
    requested_num_episodes: int,
    split_seed: int,
    train_split_ratio: float,
    split_path: Path | None,
    reuse_split: bool,
) -> tuple[list[int], list[int], dict[str, Any]]:
    if split_path is not None and split_path.exists() and reuse_split:
        split_info = _load_split_file(split_path)
        _validate_saved_split(
            split_info=split_info,
            dataset_dir=dataset_dir,
            available_episode_ids=available_episode_ids,
        )
        train_ids = [int(ep_id) for ep_id in split_info["train_ids"]]
        val_ids = [int(ep_id) for ep_id in split_info["val_ids"]]
        split_info["reused_existing_split"] = True
        return train_ids, val_ids, split_info

    train_ids, val_ids = _generate_episode_split(
        available_episode_ids=available_episode_ids,
        split_seed=split_seed,
        train_split_ratio=train_split_ratio,
    )
    split_info = {
        "schema_version": 1,
        "generated_at": datetime.datetime.utcnow().isoformat(),
        "dataset_dir": str(dataset_dir.resolve()),
        "requested_num_episodes": int(requested_num_episodes),
        "available_episode_ids": [int(ep_id) for ep_id in available_episode_ids],
        "split_seed": int(split_seed),
        "train_split_ratio": float(train_split_ratio),
        "train_ids": [int(ep_id) for ep_id in train_ids],
        "val_ids": [int(ep_id) for ep_id in val_ids],
        "reused_existing_split": False,
    }

    if split_path is not None:
        split_path.parent.mkdir(parents=True, exist_ok=True)
        with open(split_path, "w") as f:
            yaml.safe_dump(split_info, f, sort_keys=False)
        split_info["split_path"] = str(split_path)
    else:
        split_info["split_path"] = ""

    return train_ids, val_ids, split_info


def _generate_episode_split(
    *,
    available_episode_ids: list[int],
    split_seed: int,
    train_split_ratio: float,
) -> tuple[list[int], list[int]]:
    available = [int(ep_id) for ep_id in available_episode_ids]
    if not available:
        raise ValueError("Cannot generate split from an empty episode list.")

    ratio = float(np.clip(train_split_ratio, 0.0, 1.0))
    shuffled = list(np.random.default_rng(split_seed).permutation(available))

    if len(shuffled) == 1:
        # For tiny smoke/overfit runs, share the only episode across train/val.
        single = [int(shuffled[0])]
        return single, single

    split = int(round(ratio * len(shuffled)))
    split = min(max(split, 1), len(shuffled) - 1)
    return shuffled[:split], shuffled[split:]


def _load_split_file(path: Path) -> dict[str, Any]:
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Invalid split file format at {path}. Expected a mapping.")
    data["split_path"] = str(path)
    return data


def _validate_saved_split(
    *,
    split_info: dict[str, Any],
    dataset_dir: Path,
    available_episode_ids: list[int],
) -> None:
    expected_dataset_dir = str(dataset_dir.resolve())
    saved_dataset_dir = str(split_info.get("dataset_dir", ""))
    if saved_dataset_dir and saved_dataset_dir != expected_dataset_dir:
        raise ValueError(
            "Saved split file dataset_dir does not match current dataset_dir: "
            f"{saved_dataset_dir} != {expected_dataset_dir}"
        )

    available = {int(ep_id) for ep_id in available_episode_ids}
    train_ids = [int(ep_id) for ep_id in split_info.get("train_ids", [])]
    val_ids = [int(ep_id) for ep_id in split_info.get("val_ids", [])]
    if not train_ids or not val_ids:
        raise ValueError(
            "Saved split file must contain non-empty train_ids and val_ids."
        )

    split_ids = set(train_ids) | set(val_ids)
    missing = sorted(split_ids - available)
    if missing:
        raise ValueError(
            "Saved split file references episode ids not available in the current dataset: "
            + ", ".join(str(ep_id) for ep_id in missing)
        )


def _read_goal_tokens_dataset(h5_file, index: int | None = None) -> np.ndarray:
    if DS_V2_STEP_GOAL_TOKENS not in h5_file:
        raise KeyError(
            "Requested low_dim key 'goal_tokens' but /v2/step/goal_tokens is missing."
        )
    dataset = h5_file[DS_V2_STEP_GOAL_TOKENS]
    value = dataset[()] if index is None else dataset[index]
    arr = np.asarray(value, dtype=np.float32)
    expected_dim = GOAL_TOKEN_DIM
    if arr.shape[-1] != expected_dim:
        raise ValueError(
            f"/v2/step/goal_tokens must have last dimension {expected_dim}, got {arr.shape}."
        )
    return arr


def _read_cell_entry_tokens_dataset(h5_file, index: int | None = None) -> np.ndarray:
    if DS_V2_STEP_CELL_ENTRY_TOKENS not in h5_file:
        raise KeyError(
            "Requested low_dim key 'cell_entry_tokens' but "
            "/v2/step/cell_entry_tokens is missing."
        )
    dataset = h5_file[DS_V2_STEP_CELL_ENTRY_TOKENS]
    value = dataset[()] if index is None else dataset[index]
    arr = np.asarray(value, dtype=np.float32)
    expected_dim = CELL_ENTRY_TOKEN_DIM
    if arr.shape[-1] != expected_dim:
        raise ValueError(
            "/v2/step/cell_entry_tokens must have last dimension "
            f"{expected_dim}, got {arr.shape}."
        )
    return arr


def _read_dig_cut_tokens_dataset(h5_file, index: int | None = None) -> np.ndarray:
    if DS_V2_STEP_DIG_CUT_TOKENS not in h5_file:
        raise KeyError(
            "Requested low_dim key 'dig_cut_tokens' but "
            "/v2/step/dig_cut_tokens is missing."
        )
    dataset = h5_file[DS_V2_STEP_DIG_CUT_TOKENS]
    value = dataset[()] if index is None else dataset[index]
    arr = np.asarray(value, dtype=np.float32)
    expected_dim = DIG_CUT_TOKEN_DIM
    if arr.shape[-1] != expected_dim:
        raise ValueError(
            "/v2/step/dig_cut_tokens must have last dimension "
            f"{expected_dim}, got {arr.shape}."
        )
    return arr


def _read_dig_depth_profile_tokens_dataset(
    h5_file,
    index: int | None = None,
) -> np.ndarray:
    if DS_V2_STEP_DIG_DEPTH_PROFILE_TOKENS_V1 not in h5_file:
        raise KeyError(
            "Requested low_dim key 'dig_depth_profile_tokens_v1' but "
            "/v2/step/dig_depth_profile_tokens_v1 is missing."
        )
    dataset = h5_file[DS_V2_STEP_DIG_DEPTH_PROFILE_TOKENS_V1]
    value = dataset[()] if index is None else dataset[index]
    arr = np.asarray(value, dtype=np.float32)
    expected_dim = DIG_DEPTH_PROFILE_TOKEN_DIM
    if arr.shape[-1] != expected_dim:
        raise ValueError(
            "/v2/step/dig_depth_profile_tokens_v1 must have last dimension "
            f"{expected_dim}, got {arr.shape}."
        )
    return arr


def _read_return_target_tokens_dataset(h5_file, index: int | None = None) -> np.ndarray:
    if DS_V2_STEP_RETURN_TARGET_TOKENS not in h5_file:
        raise KeyError(
            "Requested low_dim key 'return_target_tokens' but "
            "/v2/step/return_target_tokens is missing."
        )
    dataset = h5_file[DS_V2_STEP_RETURN_TARGET_TOKENS]
    value = dataset[()] if index is None else dataset[index]
    arr = np.asarray(value, dtype=np.float32)
    expected_dim = RETURN_TARGET_TOKEN_DIM
    if arr.shape[-1] != expected_dim:
        raise ValueError(
            "/v2/step/return_target_tokens must have last dimension "
            f"{expected_dim}, got {arr.shape}."
        )
    return arr


def _read_return_relocate_tokens_dataset(
    h5_file,
    index: int | None = None,
) -> np.ndarray:
    target_tokens = _read_return_target_tokens_or_zeros(h5_file, index=index)
    relocate_tokens = _mask_return_relocate_tokens(target_tokens)
    metadata_token = _return_relocate_token_from_metadata(h5_file)
    if metadata_token is None:
        return relocate_tokens
    if relocate_tokens.ndim == 1:
        if _return_token_invalid(relocate_tokens):
            return metadata_token
        return relocate_tokens
    invalid = _return_token_invalid(relocate_tokens)
    if np.any(invalid):
        relocate_tokens = relocate_tokens.copy()
        relocate_tokens[invalid] = metadata_token.reshape(1, -1)
    return relocate_tokens


def _read_return_target_tokens_or_zeros(
    h5_file,
    *,
    index: int | None,
) -> np.ndarray:
    if DS_V2_STEP_RETURN_TARGET_TOKENS in h5_file:
        return _read_return_target_tokens_dataset(h5_file, index=index)
    if "/observations/qpos" not in h5_file:
        raise KeyError(
            "Requested low_dim key 'return_relocate_tokens_v1' but "
            "/v2/step/return_target_tokens and /observations/qpos are missing."
        )
    length = int(h5_file["/observations/qpos"].shape[0])
    if index is None:
        return np.zeros((length, RETURN_TARGET_TOKEN_DIM), dtype=np.float32)
    return np.zeros((RETURN_TARGET_TOKEN_DIM,), dtype=np.float32)


def _mask_return_relocate_tokens(tokens: np.ndarray) -> np.ndarray:
    arr = np.asarray(tokens, dtype=np.float32).copy()
    if arr.shape[-1] != RETURN_TARGET_TOKEN_DIM:
        raise ValueError(
            "return_relocate_tokens_v1 must be derived from 10D "
            f"return_target_tokens, got {arr.shape}."
        )
    arr[~np.isfinite(arr)] = 0.0
    arr[..., 7] = 0.0
    arr[..., 8] = 0.0
    return arr


def _return_token_invalid(tokens: np.ndarray) -> np.ndarray | bool:
    arr = np.asarray(tokens, dtype=np.float32)
    finite = np.all(np.isfinite(arr), axis=-1)
    valid = arr[..., 9] > 0.5
    spatial_nonzero = np.linalg.norm(arr[..., :7], axis=-1) > 1e-6
    return np.logical_not(finite & valid & spatial_nonzero)


def _return_relocate_token_from_metadata(h5_file) -> np.ndarray | None:
    if "metadata" not in h5_file:
        return None
    attrs = h5_file["metadata"].attrs
    if int(_metadata_scalar(attrs, "next_operator_cut_valid", default=0)) <= 0:
        return None
    required = (
        "next_operator_entry_x_m",
        "next_operator_entry_z_m",
        "next_operator_exit_x_m",
        "next_operator_exit_z_m",
        "next_operator_cut_direction_x",
        "next_operator_cut_direction_z",
        "next_operator_cut_length_m",
    )
    values = [_metadata_scalar(attrs, key, default=np.nan) for key in required]
    if not all(np.isfinite(float(value)) for value in values):
        return None
    entry_x, entry_z, exit_x, exit_z, direction_x, direction_z, length_m = values
    token = np.asarray(
        [
            _clip_norm(float(entry_x), DIG_CUT_POSITION_SCALE_M),
            _clip_norm(float(entry_z), DIG_CUT_POSITION_SCALE_M),
            _clip_norm(float(exit_x), DIG_CUT_POSITION_SCALE_M),
            _clip_norm(float(exit_z), DIG_CUT_POSITION_SCALE_M),
            float(direction_x),
            float(direction_z),
            _clip_norm(float(length_m), DIG_CUT_LENGTH_SCALE_M),
            0.0,
            0.0,
            1.0,
        ],
        dtype=np.float32,
    )
    token[~np.isfinite(token)] = 0.0
    return token


def _metadata_scalar(attrs, key: str, *, default: float) -> float:
    if key not in attrs:
        return float(default)
    value = attrs[key]
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    arr = np.asarray(value)
    if arr.shape == ():
        return float(arr.item())
    if arr.size <= 0:
        return float(default)
    return float(arr.reshape(-1)[0])


def _clip_norm(value: float, scale: float) -> float:
    if scale <= 0.0:
        return 0.0
    return float(np.clip(float(value) / float(scale), -1.0, 1.0))


def _read_return_start_envelope_tokens_dataset(
    h5_file,
    index: int | None = None,
) -> np.ndarray:
    if DS_V2_STEP_RETURN_START_ENVELOPE_TOKENS_V1 not in h5_file:
        raise KeyError(
            "Requested low_dim key 'return_start_envelope_tokens_v1' but "
            "/v2/step/return_start_envelope_tokens_v1 is missing."
        )
    dataset = h5_file[DS_V2_STEP_RETURN_START_ENVELOPE_TOKENS_V1]
    value = dataset[()] if index is None else dataset[index]
    arr = np.asarray(value, dtype=np.float32)
    expected_dim = RETURN_START_ENVELOPE_TOKEN_DIM
    if arr.shape[-1] != expected_dim:
        raise ValueError(
            "/v2/step/return_start_envelope_tokens_v1 must have last dimension "
            f"{expected_dim}, got {arr.shape}."
        )
    return arr


def _read_supervision_at_step(
    h5_file,
    *,
    key: str,
    index: int,
) -> tuple[np.ndarray, np.ndarray]:
    dataset_path = _SUPERVISION_DATASET_PATHS[key]
    mask_path = _SUPERVISION_MASK_PATHS[key]
    if dataset_path not in h5_file:
        raise KeyError(
            f"Requested supervision key {key!r} but {dataset_path} is missing."
        )
    target = np.asarray(h5_file[dataset_path][index], dtype=np.float32).reshape(-1)
    expected_dim = (
        DIG_CUT_TOKEN_DIM
        if key == "dig_outcome_targets"
        else RETURN_TARGET_TOKEN_DIM
    )
    if target.shape[-1] != expected_dim:
        raise ValueError(
            f"{dataset_path} must have last dimension {expected_dim}, got {target.shape}."
        )
    if mask_path in h5_file:
        mask = np.asarray(h5_file[mask_path][index], dtype=np.float32).reshape(-1)
    else:
        mask = np.ones_like(target, dtype=np.float32)
    if mask.shape != target.shape:
        raise ValueError(
            f"{mask_path} shape {mask.shape} does not match target shape {target.shape}."
        )
    if key == "return_relocate_outcome_targets_v1":
        target = _mask_return_relocate_tokens(target)
        mask = mask.copy()
        mask[7] = 0.0
        mask[8] = 0.0
    return target.astype(np.float32), mask.astype(np.float32)


def _read_action_loss_mask(h5_file, *, start: int) -> np.ndarray | None:
    if DS_V2_STEP_ACTION_LOSS_MASK not in h5_file:
        return None
    dataset = h5_file[DS_V2_STEP_ACTION_LOSS_MASK]
    arr = np.asarray(dataset[start:], dtype=np.uint8)
    if arr.ndim != 1:
        raise ValueError(f"/v2/step/action_loss_mask must be rank-1, got {arr.shape}.")
    return arr
