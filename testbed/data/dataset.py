"""
EpisodicDataset, get_norm_stats, load_data.

Directly migrated from legacy/utils.py with clean imports and added
docstrings. Public API is backward-compatible with legacy callers.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import torch
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

    # NOTE: Do NOT filter by action_dim == qpos_dim.
    # AGX V0 has action_dim=4 (swing/boom/stick/bucket) and qpos_dim=3 (no swing_pos).
    # That is intentional and correct per the protocol spec.
    # Stats are computed independently per-dimension so mismatched dims are fine.
    qpos_tensor   = torch.stack(all_qpos_data)    # (N, T, Nq)
    action_tensor = torch.stack(all_action_data)  # (N, T, Na)

    action_mean = action_tensor.mean(dim=[0, 1], keepdim=True)
    action_std  = action_tensor.std(dim=[0, 1],  keepdim=True).clamp(min=1e-2)
    qpos_mean   = qpos_tensor.mean(dim=[0, 1],   keepdim=True)
    qpos_std    = qpos_tensor.std(dim=[0, 1],    keepdim=True).clamp(min=1e-2)

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
    ):
        super().__init__()
        self.episode_ids  = episode_ids
        self.dataset_dir  = Path(dataset_dir)
        self.camera_names = camera_names
        self.norm_stats   = norm_stats
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

        # ── pad action to full length ──────────────────────────────────────
        padded_action = np.zeros(original_action_shape, dtype=np.float32)
        padded_action[:action_len] = action
        is_pad = np.zeros(T, dtype=bool)
        is_pad[action_len:] = True

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
    batch_size_train: int,
    batch_size_val: int,
    num_workers: int = 1,
    prefetch_factor: int = 1,
    persistent_workers: bool = False,
    pin_memory: bool = True,
) -> tuple[DataLoader, DataLoader, dict, bool]:
    """
    Build train/val DataLoaders from an HDF5 dataset directory.

    Returns
    -------
    train_loader, val_loader, norm_stats, is_sim
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
    for ep_id in available:
        p = dataset_dir / f"episode_{ep_id}.hdf5"
        with h5py.File(p, "r") as f:
            dim_info[ep_id] = (
                f["/action"].shape[1],
                f["/observations/qpos"].shape[1],
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

    # 80/20 train/val split
    shuffled = list(np.random.permutation(available))
    split    = int(0.8 * len(shuffled))
    train_ids = shuffled[:split]
    val_ids   = shuffled[split:]

    norm_stats = get_norm_stats(dataset_dir, num_episodes, episode_ids=available)

    train_ds = EpisodicDataset(train_ids, dataset_dir, camera_names, norm_stats)
    val_ds   = EpisodicDataset(val_ids,   dataset_dir, camera_names, norm_stats)

    loader_kw: dict = {"pin_memory": pin_memory, "num_workers": num_workers}
    if num_workers > 0:
        loader_kw["prefetch_factor"] = prefetch_factor
        loader_kw["persistent_workers"] = bool(persistent_workers)

    train_loader = DataLoader(train_ds, batch_size=batch_size_train, shuffle=True,  **loader_kw)
    val_loader   = DataLoader(val_ds,   batch_size=batch_size_val,   shuffle=True,  **loader_kw)

    return train_loader, val_loader, norm_stats, train_ds.is_sim
