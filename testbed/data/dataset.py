"""
EpisodicDataset, get_norm_stats, load_data.

Directly migrated from legacy/utils.py with clean imports and added
docstrings. Public API is backward-compatible with legacy callers.
"""

from __future__ import annotations

import datetime
import os
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml
from torch.utils.data import DataLoader, Dataset

from testbed.data.hdf5_io import list_episodes


# ─── Normalization stats ──────────────────────────────────────────────────────

def get_norm_stats(
    dataset_dir: str | Path,
    num_episodes: int,
    episode_ids: list[int] | None = None,
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
      "qpos_mean":    (Nq,)  float32
      "qpos_std":     (Nq,)  float32
      "example_qpos": (T, Nq) float32   (last episode read)
    }
    """
    import h5py

    dataset_dir = Path(dataset_dir)
    all_qpos_data:   list[torch.Tensor] = []
    all_action_data: list[torch.Tensor] = []
    example_qpos = None

    ids = episode_ids if episode_ids is not None else list(range(num_episodes))
    for ep_idx in ids:
        p = dataset_dir / f"episode_{ep_idx}.hdf5"
        if not p.exists():
            continue
        with h5py.File(p, "r") as f:
            qpos   = f["/observations/qpos"][()]
            action = f["/action"][()]
        all_qpos_data.append(torch.from_numpy(qpos))
        all_action_data.append(torch.from_numpy(action))
        example_qpos = qpos

    if not all_qpos_data:
        raise FileNotFoundError(
            f"No episodes found under {dataset_dir}. "
            "Expected files like episode_0.hdf5."
        )

    # NOTE: Do NOT assume all episodes share the same timestep length.
    # Success-truncated AGX demos are intentionally variable-length.
    # Stats should be computed over the concatenated time axis, not by stacking
    # episodes into a rectangular (N, T, D) tensor.
    qpos_tensor   = torch.cat(all_qpos_data, dim=0)    # (sum_T, Nq)
    action_tensor = torch.cat(all_action_data, dim=0)  # (sum_T, Na)

    action_mean = action_tensor.mean(dim=0, keepdim=True)
    action_std  = action_tensor.std(dim=0,  keepdim=True).clamp(min=1e-2)
    qpos_mean   = qpos_tensor.mean(dim=0,   keepdim=True)
    qpos_std    = qpos_tensor.std(dim=0,    keepdim=True).clamp(min=1e-2)

    return {
        "action_mean":  action_mean.numpy().squeeze().astype(np.float32),
        "action_std":   action_std.numpy().squeeze().astype(np.float32),
        "qpos_mean":    qpos_mean.numpy().squeeze().astype(np.float32),
        "qpos_std":     qpos_std.numpy().squeeze().astype(np.float32),
        "example_qpos": example_qpos,
    }


# ─── Dataset ─────────────────────────────────────────────────────────────────

class EpisodicDataset(Dataset):
    """
    PyTorch Dataset over a set of HDF5 episode files.

    Each __getitem__ samples a random start timestep t0 from episode_i,
    then returns:
      image_data : (n_cams, C, H, W)   float32 [0, 1]
      qpos_data  : (Nq,)               float32 normalised
      action_data: (T - t0, Na)        float32 normalised + zero-padded to T
      is_pad     : (T,)                bool    True where zero-padded

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
    ):
        super().__init__()
        self.episode_ids  = episode_ids
        self.dataset_dir  = Path(dataset_dir)
        self.camera_names = camera_names
        self.norm_stats   = norm_stats
        self.episode_len  = int(episode_len) if episode_len is not None else None
        self.is_sim: bool | None = None
        # Warm-up to populate self.is_sim
        self.__getitem__(0)

    def __len__(self) -> int:
        return len(self.episode_ids)

    def __getitem__(self, index: int):
        import h5py

        ep_id  = self.episode_ids[index]
        path   = self.dataset_dir / f"episode_{ep_id}.hdf5"

        with h5py.File(path, "r") as f:
            is_sim: bool = bool(f.attrs.get("sim", True))
            original_action_shape = f["/action"].shape
            T = original_action_shape[0]

            # ── sample start timestep ─────────────────────────────────────
            t0 = int(np.random.choice(T))

            # ── observation at t0 ─────────────────────────────────────────
            qpos = f["/observations/qpos"][t0]
            qvel = f["/observations/qvel"][t0]
            image_dict = {
                cam: f[f"/observations/images/{cam}"][t0]
                for cam in self.camera_names
            }

            # ── action from t0 onward (legacy hack for real data) ─────────
            if is_sim:
                action     = f["/action"][t0:]
                action_len = T - t0
            else:
                start = max(0, t0 - 1)
                action     = f["/action"][start:]
                action_len = T - start

        self.is_sim = is_sim

        # ── pad action to fixed dataset length for batching ────────────────
        target_len = self.episode_len if self.episode_len is not None else T
        if T > target_len:
            raise ValueError(
                f"Episode {ep_id} has length {T}, which exceeds configured "
                f"episode_len {target_len}. Increase task.episode_len or re-record."
            )

        padded_action = np.zeros((target_len, original_action_shape[1]), dtype=np.float32)
        padded_action[:action_len] = action
        is_pad = np.ones(target_len, dtype=bool)
        is_pad[:action_len] = False

        # ── assemble camera tensor ─────────────────────────────────────────
        all_cam_images = np.stack(
            [image_dict[c] for c in self.camera_names], axis=0
        )  # (n_cams, H, W, 3)

        # ── convert to tensors ────────────────────────────────────────────
        image_data  = torch.from_numpy(all_cam_images)
        qpos_data   = torch.from_numpy(qpos).float()
        action_data = torch.from_numpy(padded_action).float()
        is_pad_t    = torch.from_numpy(is_pad)

        # channel-last → channel-first + normalize to [0, 1]
        image_data = torch.einsum("k h w c -> k c h w", image_data).float() / 255.0

        # normalise qpos and actions
        action_data = (
            action_data
            - torch.from_numpy(self.norm_stats["action_mean"])
        ) / torch.from_numpy(self.norm_stats["action_std"])
        qpos_data = (
            qpos_data
            - torch.from_numpy(self.norm_stats["qpos_mean"])
        ) / torch.from_numpy(self.norm_stats["qpos_std"])

        return image_data, qpos_data, action_data, is_pad_t


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
) -> tuple[DataLoader, DataLoader, dict, bool, dict[str, Any]]:
    """
    Build train/val DataLoaders from an HDF5 dataset directory.

    Returns
    -------
    train_loader, val_loader, norm_stats, is_sim, split_info
    """
    dataset_dir = Path(dataset_dir)
    print(f"\nData from: {dataset_dir}\n")

    # discover available episode files
    available = [
        int(p.stem.split("_", 1)[1])
        for p in list_episodes(dataset_dir)
    ]
    available = [i for i in available if i < num_episodes]

    if not available:
        raise FileNotFoundError(
            f"No episodes found under {dataset_dir}. "
            "Expected files like episode_0.hdf5."
        )
    if len(available) < num_episodes:
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
    for ep_id in available:
        p = dataset_dir / f"episode_{ep_id}.hdf5"
        with h5py.File(p, "r") as f:
            dim_info[ep_id] = (
                f["/action"].shape[1],
                f["/observations/qpos"].shape[1],
            )
            length_info[ep_id] = int(f["/action"].shape[0])
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
    target_episode_len = int(episode_len) if episode_len is not None else max_episode_len
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

    norm_stats = get_norm_stats(dataset_dir, num_episodes, episode_ids=available)

    train_ds = EpisodicDataset(
        train_ids,
        dataset_dir,
        camera_names,
        norm_stats,
        episode_len=target_episode_len,
    )
    val_ds = EpisodicDataset(
        val_ids,
        dataset_dir,
        camera_names,
        norm_stats,
        episode_len=target_episode_len,
    )

    split_info["dataset_max_episode_len"] = int(max_episode_len)
    split_info["loader_episode_len"] = int(target_episode_len)

    loader_kw: dict = {"pin_memory": pin_memory, "num_workers": num_workers}
    if num_workers > 0:
        loader_kw["prefetch_factor"] = prefetch_factor
        loader_kw["persistent_workers"] = bool(persistent_workers)

    train_loader = DataLoader(train_ds, batch_size=batch_size_train, shuffle=True,  **loader_kw)
    val_loader   = DataLoader(val_ds,   batch_size=batch_size_val,   shuffle=True,  **loader_kw)

    return train_loader, val_loader, norm_stats, train_ds.is_sim, split_info


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
        raise ValueError("Saved split file must contain non-empty train_ids and val_ids.")

    split_ids = set(train_ids) | set(val_ids)
    missing = sorted(split_ids - available)
    if missing:
        raise ValueError(
            "Saved split file references episode ids not available in the current dataset: "
            + ", ".join(str(ep_id) for ep_id in missing)
        )
