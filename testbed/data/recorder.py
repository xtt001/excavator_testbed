"""
EpisodeRecorder: buffers per-step data and flushes to HDF5 at episode end.

Usage
-----
    recorder = EpisodeRecorder(
        output_dir=Path("data/sim_lifting_cube"),
        episode_idx=0,
        metadata={
            "task_name": "sim_lifting_cube_scripted",
            "sim_backend": "mujoco_ee",
            "seed": 42,
            "param_version": "v0",
        },
    )
    recorder.record(ts, action)     # inside env loop
    success = recorder.save(success=True)
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

import numpy as np

from testbed.data.hdf5_io import write_episode


class EpisodeRecorder:
    """
    Buffer for one demonstration episode.

    Parameters
    ----------
    output_dir   Directory where episode_N.hdf5 will be written.
    episode_idx  Integer episode index used for the filename.
    metadata     Dict of scalar metadata written to /metadata group.
    camera_names Names of cameras to record from images dict.
                 If None, all cameras present in first obs are recorded.
    """

    def __init__(
        self,
        output_dir: Path | str,
        episode_idx: int,
        metadata: dict[str, Any] | None = None,
        camera_names: list[str] | None = None,
    ):
        self.output_dir   = Path(output_dir)
        self.episode_idx  = episode_idx
        self.metadata     = dict(metadata or {})
        self.camera_names = camera_names

        # Buffers
        self._qpos:    list[np.ndarray] = []
        self._qvel:    list[np.ndarray] = []
        self._actions: list[np.ndarray] = []
        self._rewards: list[float]      = []
        self._images:  dict[str, list[np.ndarray]] = {}

    # ── Per-step recording ────────────────────────────────────────────────────

    def record(self, obs: dict, action: np.ndarray, reward: float = 0.0) -> None:
        """
        Buffer one timestep.

        Parameters
        ----------
        obs     Raw observation dict from dm_control env step.
        action  Action applied at this step.
        reward  Scalar reward (default 0).
        """
        self._qpos.append(np.array(obs["qpos"], dtype=np.float32))
        self._qvel.append(np.array(obs["qvel"], dtype=np.float32))
        self._actions.append(np.array(action, dtype=np.float32))
        self._rewards.append(float(reward))

        images: dict = obs.get("images", {})
        cams = self.camera_names if self.camera_names else list(images.keys())
        for cam in cams:
            if cam in images:
                if cam not in self._images:
                    self._images[cam] = []
                self._images[cam].append(np.array(images[cam], dtype=np.uint8))

    # ── Save ─────────────────────────────────────────────────────────────────

    def save(self, success: bool = False) -> Path:
        """
        Flush buffers to disk as episode_{episode_idx}.hdf5.

        Parameters
        ----------
        success  Whether the episode was successful.

        Returns
        -------
        Path  Path to the written HDF5 file.
        """
        if not self._qpos:
            raise RuntimeError("EpisodeRecorder.save() called on an empty buffer.")

        path = self.output_dir / f"episode_{self.episode_idx}.hdf5"

        meta = dict(self.metadata)
        meta["success"]   = int(success)
        meta["timestamp"] = datetime.datetime.utcnow().isoformat()
        meta["n_steps"]   = len(self._qpos)

        qpos    = np.stack(self._qpos)
        qvel    = np.stack(self._qvel)
        actions = np.stack(self._actions)
        rewards = np.array(self._rewards, dtype=np.float32)

        images: dict[str, np.ndarray] = {}
        for cam, frames in self._images.items():
            images[cam] = np.stack(frames)

        write_episode(
            path,
            qpos=qpos,
            qvel=qvel,
            actions=actions,
            images=images if images else None,
            rewards=rewards,
            metadata=meta,
        )
        return path

    # ── Convenience ──────────────────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self._qpos)

    def reset(self, episode_idx: int | None = None) -> None:
        """Clear buffers and optionally update episode index (for reuse)."""
        if episode_idx is not None:
            self.episode_idx = episode_idx
        self._qpos.clear()
        self._qvel.clear()
        self._actions.clear()
        self._rewards.clear()
        self._images.clear()
