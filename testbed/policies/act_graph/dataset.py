"""Graph-aware ACT dataloader."""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset

from testbed.data.dataset import (
    _assemble_low_dim_observation,
    _normalize_low_dim_keys,
    _read_action_loss_mask,
    _read_cell_entry_tokens_dataset,
    _read_dig_cut_tokens_dataset,
    _read_goal_tokens_dataset,
    _resolve_episode_split,
    _select_episode_ids,
    get_norm_stats,
)
from testbed.data.image_masks import (
    apply_image_mask,
    mask_dataset_path,
    require_mask_dataset,
)

GRAPH_KEYS = (
    "node_features",
    "node_mask",
    "edge_indices",
    "edge_features",
    "edge_mask",
    "graph_globals",
)


class GraphEpisodicDataset(Dataset):
    """ACT dataset that also returns `/observations/graph` at the sampled step."""

    def __init__(
        self,
        episode_ids: list[int],
        dataset_dir: str | Path,
        camera_names: list[str],
        norm_stats: dict[str, np.ndarray],
        episode_len: int | None = None,
        low_dim_keys: list[str] | tuple[str, ...] | None = None,
        image_mask_config: dict[str, Any] | None = None,
        hdf5_cache_size: int = 0,
    ):
        super().__init__()
        self.episode_ids = episode_ids
        self.dataset_dir = Path(dataset_dir)
        self.camera_names = list(camera_names)
        self.norm_stats = norm_stats
        self.episode_len = int(episode_len) if episode_len is not None else None
        self.low_dim_keys = _normalize_low_dim_keys(low_dim_keys)
        self.image_mask_config = dict(image_mask_config or {})
        self.hdf5_cache_size = max(0, int(hdf5_cache_size))
        self._h5_cache: OrderedDict[int, Any] = OrderedDict()
        self.is_sim: bool | None = None
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
            is_sim = bool(f.attrs.get("sim", True))
            original_action_shape = f["/action"].shape
            total_steps = int(original_action_shape[0])
            t0 = int(np.random.choice(total_steps))

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
            proprio = _assemble_low_dim_observation(
                qpos=qpos,
                qvel=qvel,
                goal_tokens=goal_tokens,
                cell_entry_tokens=cell_entry_tokens,
                dig_cut_tokens=dig_cut_tokens,
                low_dim_keys=self.low_dim_keys,
            )
            graph = _read_graph_at_timestep(f, t0)
            image_dict = _read_images_at_timestep(
                f,
                camera_names=self.camera_names,
                image_mask_config=self.image_mask_config,
                t0=t0,
                ep_id=ep_id,
            )

            if is_sim:
                action = f["/action"][t0:]
                action_loss_mask = _read_action_loss_mask(f, start=t0)
                action_len = total_steps - t0
            else:
                start = max(0, t0 - 1)
                action = f["/action"][start:]
                action_loss_mask = _read_action_loss_mask(f, start=start)
                action_len = total_steps - start
        finally:
            if close_after_read:
                f.close()

        self.is_sim = is_sim
        target_len = self.episode_len if self.episode_len is not None else total_steps
        if total_steps > target_len:
            raise ValueError(
                f"Episode {ep_id} has length {total_steps}, which exceeds configured "
                f"episode_len {target_len}. Increase task.episode_len or re-record."
            )

        padded_action = np.zeros((target_len, original_action_shape[1]), dtype=np.float32)
        padded_action[:action_len] = action
        is_pad = np.ones(target_len, dtype=bool)
        is_pad[:action_len] = False
        if action_loss_mask is not None:
            loss_mask = np.asarray(action_loss_mask[:action_len], dtype=np.uint8).reshape(-1)
            if loss_mask.shape[0] != action_len:
                raise ValueError(
                    f"Episode {ep_id} action_loss_mask length {loss_mask.shape[0]} "
                    f"does not match action_len {action_len}."
                )
            is_pad[:action_len] |= loss_mask == 0

        all_cam_images = np.stack([image_dict[c] for c in self.camera_names], axis=0)
        image_data = torch.from_numpy(all_cam_images)
        image_data = torch.einsum("k h w c -> k c h w", image_data).float() / 255.0
        proprio_data = torch.from_numpy(proprio).float()
        action_data = torch.from_numpy(padded_action).float()
        is_pad_t = torch.from_numpy(is_pad)

        action_data = (
            action_data - torch.from_numpy(self.norm_stats["action_mean"])
        ) / torch.from_numpy(self.norm_stats["action_std"])
        proprio_data = (
            proprio_data - torch.from_numpy(self.norm_stats["proprio_mean"])
        ) / torch.from_numpy(self.norm_stats["proprio_std"])

        graph_data = {
            "node_features": torch.from_numpy(graph["node_features"]).float(),
            "node_mask": torch.from_numpy(graph["node_mask"]).bool(),
            "edge_indices": torch.from_numpy(graph["edge_indices"]).long(),
            "edge_features": torch.from_numpy(graph["edge_features"]).float(),
            "edge_mask": torch.from_numpy(graph["edge_mask"]).bool(),
            "graph_globals": torch.from_numpy(graph["graph_globals"]).float(),
        }
        return image_data, proprio_data, graph_data, action_data, is_pad_t

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


def load_graph_data(
    dataset_dir: str | Path,
    num_episodes: int,
    camera_names: list[str],
    episode_len: int | None,
    batch_size_train: int,
    batch_size_val: int,
    num_workers: int = 1,
    prefetch_factor: int | None = 1,
    persistent_workers: bool = False,
    pin_memory: bool = True,
    *,
    split_seed: int = 0,
    train_split_ratio: float = 0.8,
    split_path: str | Path | None = None,
    reuse_split: bool = True,
    low_dim_keys: list[str] | tuple[str, ...] | None = None,
    image_mask_config: dict[str, Any] | None = None,
    hdf5_cache_size: int = 0,
) -> tuple[DataLoader, DataLoader, dict, bool, dict[str, Any]]:
    dataset_dir = Path(dataset_dir)
    print(f"\nGraph data from: {dataset_dir}\n")
    available = _select_episode_ids(dataset_dir, int(num_episodes))
    if not available:
        raise FileNotFoundError(
            f"No episodes found under {dataset_dir}. Expected files like episode_0.hdf5."
        )

    import h5py

    length_info: dict[int, int] = {}
    valid: list[int] = []
    for ep_id in available:
        path = dataset_dir / f"episode_{ep_id}.hdf5"
        with h5py.File(path, "r") as f:
            if "/observations/graph" not in f:
                continue
            _validate_graph_group(f, ep_id=ep_id)
            if f["/action"].shape[1] != f["/observations/qpos"].shape[1]:
                continue
            length_info[ep_id] = int(f["/action"].shape[0])
            valid.append(ep_id)
    if not valid:
        raise FileNotFoundError(
            f"No graph episodes found under {dataset_dir}. "
            "Expected /observations/graph in episode_*.hdf5."
        )

    max_episode_len = max(length_info[ep_id] for ep_id in valid)
    target_episode_len = int(episode_len) if episode_len is not None else max_episode_len
    if max_episode_len > target_episode_len:
        raise ValueError(
            f"Dataset contains an episode of length {max_episode_len}, but configured "
            f"episode_len is only {target_episode_len}. Increase task.episode_len."
        )

    train_ids, val_ids, split_info = _resolve_episode_split(
        dataset_dir=dataset_dir,
        available_episode_ids=valid,
        requested_num_episodes=int(num_episodes),
        split_seed=int(split_seed),
        train_split_ratio=float(train_split_ratio),
        split_path=None if split_path is None else Path(split_path),
        reuse_split=bool(reuse_split),
    )
    selected_low_dim_keys = _normalize_low_dim_keys(low_dim_keys)
    norm_stats = get_norm_stats(
        dataset_dir,
        int(num_episodes),
        episode_ids=valid,
        low_dim_keys=selected_low_dim_keys,
    )

    train_ds = GraphEpisodicDataset(
        train_ids,
        dataset_dir,
        camera_names,
        norm_stats,
        episode_len=target_episode_len,
        low_dim_keys=selected_low_dim_keys,
        image_mask_config=image_mask_config,
        hdf5_cache_size=hdf5_cache_size,
    )
    val_ds = GraphEpisodicDataset(
        val_ids,
        dataset_dir,
        camera_names,
        norm_stats,
        episode_len=target_episode_len,
        low_dim_keys=selected_low_dim_keys,
        image_mask_config=image_mask_config,
        hdf5_cache_size=hdf5_cache_size,
    )

    split_info["dataset_max_episode_len"] = int(max_episode_len)
    split_info["loader_episode_len"] = int(target_episode_len)
    split_info["low_dim_keys"] = list(selected_low_dim_keys)
    split_info["low_dim_dim"] = int(norm_stats["proprio_dim"])
    split_info["uses_observation_graph"] = True

    loader_kw: dict[str, Any] = {"pin_memory": pin_memory, "num_workers": num_workers}
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


def _read_graph_at_timestep(h5_file, t0: int) -> dict[str, np.ndarray]:
    group = h5_file["/observations/graph"]
    graph: dict[str, np.ndarray] = {}
    for key in GRAPH_KEYS:
        value = np.asarray(group[key][t0])
        if key in {"node_features", "edge_features", "graph_globals"}:
            value = value.astype(np.float32)
        elif key in {"node_mask", "edge_mask"}:
            value = value.astype(np.uint8)
        elif key == "edge_indices":
            value = value.astype(np.int64)
        graph[key] = value
    return graph


def _read_images_at_timestep(
    h5_file,
    *,
    camera_names: list[str],
    image_mask_config: dict[str, Any],
    t0: int,
    ep_id: int,
) -> dict[str, np.ndarray]:
    image_dict: dict[str, np.ndarray] = {}
    for cam in camera_names:
        image = h5_file[f"/observations/images/{cam}"][t0]
        mask = None
        mask_path = mask_dataset_path(camera_name=cam, mask_config=image_mask_config)
        if mask_path is not None:
            if mask_path in h5_file:
                mask = h5_file[mask_path][t0]
            elif require_mask_dataset(camera_name=cam, mask_config=image_mask_config):
                raise KeyError(
                    f"Episode {ep_id} is missing required image mask dataset "
                    f"{mask_path!r} for camera {cam!r}."
                )
        image_dict[cam] = apply_image_mask(
            image,
            camera_name=cam,
            mask_config=image_mask_config,
            mask=mask,
        )
    return image_dict


def _validate_graph_group(h5_file, *, ep_id: int) -> None:
    group = h5_file["/observations/graph"]
    missing = [key for key in GRAPH_KEYS if key not in group]
    if missing:
        raise KeyError(f"Episode {ep_id} graph is missing keys: {missing}")
    total_steps = int(h5_file["/action"].shape[0])
    for key in GRAPH_KEYS:
        if int(group[key].shape[0]) != total_steps:
            raise ValueError(
                f"Episode {ep_id} graph key {key!r} length {group[key].shape[0]} "
                f"does not match action length {total_steps}."
            )
