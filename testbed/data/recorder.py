"""
EpisodeRecorder: buffers per-step data and flushes to HDF5 at episode end.

Supports schema v1.1 fields (step_id, action_source, env_state) via
optional parameters in record().

Usage
-----
    recorder = EpisodeRecorder(
        output_dir=Path("data/agx_excavation"),
        episode_idx=0,
        metadata={
            "task_name":        "agx_excavation_teleop",
            "sim_backend":      "agxunity",
            "seed":             -1,
            "control_hz":       50,
            "dt":               0.02,
            "action_semantics": "actuator_speed_cmd",
            "camera_names":     "fpv",
            "image_format":     "raw_rgb",
        },
    )
    recorder.record(obs, action, reward=0.0, step_id=0,
                    action_src_type="teleop", action_src_id="joystick")
    path = recorder.save(success=True)
"""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

import numpy as np

from testbed.data.camera_images import encoded_frame_to_uint8, validate_camera_step
from testbed.data.hdf5_io import write_episode
from testbed.data.schema import ATTR_CAMERA_NAMES, ATTR_EPISODE_ID, ATTR_IMAGE_FORMAT


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

        # ── v1.0 buffers ─────────────────────────────────────────────────────
        self._qpos:    list[np.ndarray] = []
        self._qvel:    list[np.ndarray] = []
        self._actions: list[np.ndarray] = []
        self._rewards: list[float]      = []
        self._images:  dict[str, list[np.ndarray]] = {}
        self._encoded_images: dict[str, list[np.ndarray]] = {}
        self._camera_storage_mode: str | None = None

        # ── v1.1 buffers ─────────────────────────────────────────────────────
        self._step_ids:        list[int]        = []
        self._step_ns:         list[int]        = []
        self._env_states:      list[np.ndarray] = []
        self._action_src_types: list[str]       = []
        self._action_src_ids:   list[str]       = []

    # ── Per-step recording ────────────────────────────────────────────────────

    def record(
        self,
        obs: dict,
        action: np.ndarray,
        reward: float = 0.0,
        *,
        step_id: int | None = None,
        step_ns: int | None = None,
        action_src_type: str = "teleop",
        action_src_id: str = "joystick",
    ) -> None:
        """
        Buffer one timestep.

        Parameters
        ----------
        obs              Raw observation dict from backend step.
        action           Action applied at this step (shape: (4,) for AGX V0).
        reward           Scalar reward (default 0).
        step_id          Monotonic step counter from the backend (v1.1).
        step_ns          Wall-clock nanoseconds (v1.1, optional).
        action_src_type  "teleop" | "policy" | "scripted" (v1.1).
        action_src_id    "joystick" | "keyboard" | ... (v1.1).
        """
        images: dict = obs.get("images", {})
        encoded_images: dict = obs.get("encoded_images", {})
        cams, step_mode = validate_camera_step(
            requested_names=self.camera_names,
            raw_images=images,
            encoded_images=encoded_images,
            previous_mode=self._camera_storage_mode,
        )

        self._qpos.append(np.array(obs["qpos"], dtype=np.float32))
        self._qvel.append(np.array(obs["qvel"], dtype=np.float32))
        self._actions.append(np.array(action, dtype=np.float32))
        self._rewards.append(float(reward))

        # v1.1
        self._step_ids.append(int(step_id) if step_id is not None else len(self._step_ids))
        self._step_ns.append(int(step_ns) if step_ns is not None else 0)
        self._action_src_types.append(action_src_type)
        self._action_src_ids.append(action_src_id)

        env_s = obs.get("env_state")
        if env_s is not None:
            self._env_states.append(np.array(env_s, dtype=np.float32))

        if step_mode is not None:
            self._camera_storage_mode = step_mode
        for cam in cams:
            if cam in images:
                if cam not in self._images:
                    self._images[cam] = []
                self._images[cam].append(np.array(images[cam], dtype=np.uint8))
            else:
                self._encoded_images.setdefault(cam, []).append(
                    encoded_frame_to_uint8(encoded_images[cam])
                )

    # ── Save ─────────────────────────────────────────────────────────────────

    def save(
        self,
        success: bool = False,
        *,
        v2: dict[str, dict[str, np.ndarray]] | None = None,
    ) -> Path:
        """
        Flush buffers to disk as episode_{episode_idx}.hdf5.

        Returns
        -------
        Path  Path to the written HDF5 file.
        """
        if not self._qpos:
            raise RuntimeError("EpisodeRecorder.save() called on an empty buffer.")

        path = self.output_dir / f"episode_{self.episode_idx}.hdf5"

        meta = dict(self.metadata)
        meta.setdefault(ATTR_EPISODE_ID, f"episode_{self.episode_idx}")
        meta["success"]   = int(success)
        meta["timestamp"] = datetime.datetime.utcnow().isoformat()
        meta["n_steps"]   = len(self._qpos)

        qpos    = np.stack(self._qpos)
        qvel    = np.stack(self._qvel)
        actions = np.stack(self._actions)
        rewards = np.array(self._rewards, dtype=np.float32)

        images: dict[str, np.ndarray] = {
            cam: np.stack(frames) for cam, frames in self._images.items()
        }
        encoded_images = {
            cam: list(frames) for cam, frames in self._encoded_images.items()
        }
        stored_names = list(self.camera_names or images.keys() or encoded_images.keys())
        if stored_names:
            meta[ATTR_CAMERA_NAMES] = ",".join(stored_names)
            meta[ATTR_IMAGE_FORMAT] = "jpeg" if encoded_images else "raw_rgb"

        env_state = (
            np.stack(self._env_states)
            if self._env_states else None
        )

        write_episode(
            path,
            qpos=qpos,
            qvel=qvel,
            actions=actions,
            images=images if images else None,
            encoded_images=encoded_images if encoded_images else None,
            rewards=rewards,
            metadata=meta,
            # v1.1
            env_state=env_state,
            step_ids=np.array(self._step_ids, dtype=np.int64) if self._step_ids else None,
            step_ns=np.array(self._step_ns, dtype=np.int64) if any(self._step_ns) else None,
            action_src_types=self._action_src_types if self._action_src_types else None,
            action_src_ids=self._action_src_ids if self._action_src_ids else None,
            v2=v2,
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
        self._encoded_images.clear()
        self._camera_storage_mode = None
        self._step_ids.clear()
        self._step_ns.clear()
        self._env_states.clear()
        self._action_src_types.clear()
        self._action_src_ids.clear()
