"""Frozen source-balanced data and token controls for the minimal DP probe."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import cv2
import h5py
import numpy as np

from testbed.data.camera_images import read_camera_rgb


class SourceEpisodeBalancedSampler:
    """Sample source, then primitive episode, then window with equal probability."""

    def __init__(self, source_ids: np.ndarray, episode_ids: np.ndarray) -> None:
        sources = np.asarray(source_ids, dtype=np.int64).reshape(-1)
        episodes = np.asarray(episode_ids, dtype=np.int64).reshape(-1)
        if sources.shape != episodes.shape or sources.size == 0:
            raise ValueError(
                "source/episode sampler inputs must align and be non-empty"
            )
        allowed = ~np.isin(sources, [33, 34])
        self.source_ids = sources[allowed]
        self.episode_ids = episodes[allowed]
        self.original_indices = np.flatnonzero(allowed)
        if self.source_ids.size == 0:
            raise ValueError("source/episode sampler has no allowed rows")
        grouped: dict[int, dict[int, list[int]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for local_index, (source, episode) in enumerate(
            zip(self.source_ids, self.episode_ids, strict=True)
        ):
            grouped[int(source)][int(episode)].append(local_index)
        self._grouped = {
            source: {
                episode: np.asarray(indices, dtype=np.int64)
                for episode, indices in episodes_by_source.items()
            }
            for source, episodes_by_source in grouped.items()
        }
        self.sources = np.asarray(sorted(self._grouped), dtype=np.int64)

    def sample_indices(self, *, batch_size: int, seed: int) -> np.ndarray:
        if batch_size < 1:
            raise ValueError("source-balanced batch size must be positive")
        rng = np.random.default_rng(int(seed))
        output = np.empty(batch_size, dtype=np.int64)
        sampled_sources = rng.choice(self.sources, size=batch_size, replace=True)
        for index, source_value in enumerate(sampled_sources):
            source = int(source_value)
            episodes = np.asarray(sorted(self._grouped[source]), dtype=np.int64)
            episode = int(rng.choice(episodes))
            local = int(rng.choice(self._grouped[source][episode]))
            output[index] = int(self.original_indices[local])
        return output


def build_evaluation_token_conditions(
    variants: Sequence[Mapping[str, Any]], *, shuffle_seed: int
) -> dict[str, np.ndarray]:
    rows = list(variants)
    if len(rows) < 2:
        raise ValueError("token shuffle requires at least two variants")
    base = np.asarray([row["base_token"] for row in rows], dtype=np.float32)
    alternate = np.asarray([row["variant_token"] for row in rows], dtype=np.float32)
    if base.shape != (len(rows), 10) or alternate.shape != base.shape:
        raise ValueError("evaluation tokens must be [variants,10]")
    rng = np.random.default_rng(int(shuffle_seed))
    shifts = rng.permutation(np.arange(1, len(rows), dtype=np.int64))
    indices = None
    shift = None
    for candidate_shift in shifts:
        candidate = (np.arange(len(rows), dtype=np.int64) + int(candidate_shift)) % len(
            rows
        )
        equal = np.all(alternate[candidate] == alternate, axis=1)
        if not np.any(equal):
            indices = candidate
            shift = int(candidate_shift)
            break
    if indices is None or shift is None:
        raise ValueError("cannot construct a value-disjoint shuffled token control")
    return {
        "base_correct": base,
        "alternate_correct": alternate,
        "zero": np.zeros_like(alternate),
        "shuffled": alternate[indices].copy(),
        "shuffle_indices": indices,
        "shuffle_shift": np.asarray(shift, dtype=np.int64),
    }


def build_training_window_cache(
    *,
    rollout_windows_path: str | Path,
    dataset_dir: str | Path,
    camera_order: Sequence[str],
    output_path: str | Path,
    image_size: int = 32,
) -> dict[str, Any]:
    """Attach 10D tokens and four downsampled cameras to formal rollout windows."""
    source_path = Path(rollout_windows_path).expanduser().resolve(strict=True)
    dataset = Path(dataset_dir).expanduser().resolve(strict=True)
    destination = Path(output_path).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(destination)
    with np.load(source_path) as handle:
        initial_qpos = np.asarray(handle["initial_qpos"], dtype=np.float32)
        initial_qvel = np.asarray(handle["initial_qvel"], dtype=np.float32)
        actions = np.asarray(handle["actions"], dtype=np.float32)
        frame_index = np.asarray(handle["frame_index"], dtype=np.int32)
        episode_id = np.asarray(handle["primitive_episode_id"], dtype=np.int32)
        source_id = np.asarray(handle["source_episode_id"], dtype=np.int32)
    count = initial_qpos.shape[0]
    if (
        initial_qpos.shape != (count, 4)
        or initial_qvel.shape != (count, 4)
        or actions.shape != (count, 100, 4)
        or frame_index.shape != episode_id.shape
        or episode_id.shape != source_id.shape
        or episode_id.shape != (count,)
        or np.isin(source_id, [33, 34]).any()
    ):
        raise ValueError("formal DP training window cache contract mismatch")
    images = np.empty(
        (count, len(tuple(camera_order)), image_size, image_size), dtype=np.uint8
    )
    tokens = np.empty((count, 10), dtype=np.float32)
    by_episode: dict[int, list[int]] = defaultdict(list)
    for index, episode in enumerate(episode_id):
        by_episode[int(episode)].append(index)
    for episode in sorted(by_episode):
        with h5py.File(dataset / f"episode_{episode}.hdf5", "r") as hdf5_file:
            for index in by_episode[episode]:
                frame = int(frame_index[index])
                stored_qpos = np.asarray(
                    hdf5_file["observations/qpos"][frame], dtype=np.float32
                )
                stored_qvel = np.asarray(
                    hdf5_file["observations/qvel"][frame], dtype=np.float32
                )
                if not np.array_equal(
                    stored_qpos, initial_qpos[index]
                ) or not np.array_equal(stored_qvel, initial_qvel[index]):
                    raise ValueError("rollout cache/HDF5 observation lineage mismatch")
                tokens[index] = np.asarray(
                    hdf5_file["v2/step/dig_cut_tokens"][frame], dtype=np.float32
                )
                for camera_index, camera in enumerate(camera_order):
                    rgb = read_camera_rgb(hdf5_file, str(camera), frame)
                    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
                    images[index, camera_index] = cv2.resize(
                        gray,
                        (image_size, image_size),
                        interpolation=cv2.INTER_AREA,
                    )
    proprio = np.concatenate((initial_qpos, initial_qvel, tokens), axis=1)
    np.savez(
        destination,
        images=images,
        proprio=proprio.astype(np.float32),
        actions=actions,
        frame_index=frame_index,
        primitive_episode_id=episode_id,
        source_episode_id=source_id,
    )
    return {
        "schema": "minimal_dp_training_window_cache_v1",
        "window_count": count,
        "episode_count": int(np.unique(episode_id).size),
        "source_episode_ids": sorted(int(value) for value in np.unique(source_id)),
        "camera_order": list(camera_order),
        "image_preprocessing": f"grayscale_{image_size}x{image_size}_area",
        "low_dim_order": ["qpos", "qvel", "dig_cut_tokens"],
        "action_horizon": 100,
        "source_33_34_used": False,
        "window_random_split": False,
        "output_path": str(destination),
    }


def build_evaluation_observation_cache(
    *,
    variants: Sequence[Mapping[str, Any]],
    camera_order: Sequence[str],
    output_path: str | Path,
    image_size: int = 32,
) -> dict[str, Any]:
    rows = list(variants)
    destination = Path(output_path).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(destination)
    count = len(rows)
    images = np.empty((count, 100, 4, image_size, image_size), dtype=np.uint8)
    qpos = np.empty((count, 100, 4), dtype=np.float32)
    qvel = np.empty_like(qpos)
    source_ids = np.empty(count, dtype=np.int32)
    episode_ids = np.empty(count, dtype=np.int32)
    for variant_index, variant in enumerate(rows):
        if int(variant["source_episode_id"]) in (33, 34):
            raise ValueError("source 33/34 cannot enter DP evaluation")
        frame_indices = [int(value) for value in variant["observation_frame_indices"]]
        if frame_indices != list(range(100)):
            raise ValueError("DP evaluation requires frozen frames 0..99")
        with h5py.File(str(variant["dataset_path"]), "r") as hdf5_file:
            qpos[variant_index] = np.asarray(
                hdf5_file["observations/qpos"][:100], dtype=np.float32
            )
            qvel[variant_index] = np.asarray(
                hdf5_file["observations/qvel"][:100], dtype=np.float32
            )
            for frame in range(100):
                for camera_index, camera in enumerate(camera_order):
                    rgb = read_camera_rgb(hdf5_file, str(camera), frame)
                    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
                    images[variant_index, frame, camera_index] = cv2.resize(
                        gray,
                        (image_size, image_size),
                        interpolation=cv2.INTER_AREA,
                    )
        source_ids[variant_index] = int(variant["source_episode_id"])
        episode_ids[variant_index] = int(variant["primitive_episode_id"])
    np.savez(
        destination,
        images=images,
        qpos=qpos,
        qvel=qvel,
        source_episode_id=source_ids,
        primitive_episode_id=episode_ids,
    )
    return {
        "schema": "minimal_dp_evaluation_observation_cache_v1",
        "variant_count": count,
        "frame_count_per_variant": 100,
        "camera_order": list(camera_order),
        "image_preprocessing": f"grayscale_{image_size}x{image_size}_area",
        "source_33_34_used": False,
        "output_path": str(destination),
    }


def load_npz_arrays(path: str | Path) -> dict[str, np.ndarray]:
    with np.load(Path(path).expanduser().resolve(strict=True)) as handle:
        return {key: np.asarray(handle[key]) for key in handle.files}


def json_ready_cache_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(value, allow_nan=False))


__all__ = [
    "SourceEpisodeBalancedSampler",
    "build_evaluation_observation_cache",
    "build_evaluation_token_conditions",
    "build_training_window_cache",
    "json_ready_cache_manifest",
    "load_npz_arrays",
]
