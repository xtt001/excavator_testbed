"""
StructuredState: typed container consumed by every Policy and Evaluator.

Raw obs dict from dm_control environments has the shape:
  {
    "qpos":      np.ndarray  (N,)
    "qvel":      np.ndarray  (N,)
    "images":    dict[str, np.ndarray]  cam_name → (H, W, 3) uint8
    "env_state": np.ndarray  (M,)       task-specific (box xyz/quat, ...)
  }

StateConverter wraps the raw dict into a StructuredState. FK tip positions
are populated lazily by passing an optional physics handle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class StructuredState:
    """
    Canonical observation container.  All fields are numpy arrays.

    Attributes
    ----------
    qpos        Joint positions (may include gripper).
    qvel        Joint velocities.
    images      Camera images, keyed by camera name.
    env_state   Task-specific environment state (object poses, etc.).
    tip_pos     FK-derived end-effector / bucket-tip positions.
                Keys are site names; values are (3,) xyz arrays.
    tip_mat     FK-derived orientation matrices (3, 3) for each site.
    metadata    Arbitrary scalar metadata (step, reward, phase, …).
    """

    qpos: np.ndarray
    qvel: np.ndarray
    images: dict[str, np.ndarray] = field(default_factory=dict)
    env_state: np.ndarray = field(default_factory=lambda: np.zeros(0))
    tip_pos: dict[str, np.ndarray] = field(default_factory=dict)
    tip_mat: dict[str, np.ndarray] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    # ── Convenience properties ────────────────────────────────────────────────

    @property
    def n_joints(self) -> int:
        return len(self.qpos)

    @property
    def has_images(self) -> bool:
        return bool(self.images)

    @property
    def camera_names(self) -> list[str]:
        return list(self.images.keys())

    def as_policy_input(self) -> dict[str, np.ndarray]:
        """
        Flatten state into the dict format expected by Policy.predict().

        Returns a new dict every call (safe to mutate downstream).
        """
        d: dict[str, np.ndarray] = {
            "qpos": self.qpos.copy(),
            "qvel": self.qvel.copy(),
        }
        for cam, img in self.images.items():
            d[f"image_{cam}"] = img.copy()
        if self.env_state.size > 0:
            d["env_state"] = self.env_state.copy()
        for site, pos in self.tip_pos.items():
            d[f"tip_pos_{site}"] = pos.copy()
        return d


# ─── StateConverter ───────────────────────────────────────────────────────────

class StateConverter:
    """
    Convert a raw obs dict from a dm_control TimeStep into a StructuredState.

    Parameters
    ----------
    fk_sites
        Site names for which FK positions should be populated.
        Requires a physics handle (see `convert_with_physics`).
    """

    def __init__(self, fk_sites: list[str] | None = None):
        self.fk_sites: list[str] = fk_sites or []

    # ── primary API ──────────────────────────────────────────────────────────

    def convert(self, obs: dict) -> StructuredState:
        """Convert raw obs dict (no FK enrichment)."""
        return StructuredState(
            qpos=np.array(obs.get("qpos", []), dtype=np.float32),
            qvel=np.array(obs.get("qvel", []), dtype=np.float32),
            images={k: np.array(v) for k, v in obs.get("images", {}).items()},
            env_state=np.array(obs.get("env_state", []), dtype=np.float32),
        )

    def convert_with_physics(self, obs: dict, physics) -> StructuredState:
        """
        Convert raw obs dict AND populate FK site positions.

        Parameters
        ----------
        obs      Raw observation dict.
        physics  dm_control Physics handle (e.g. env._physics).
        """
        from testbed.state.kinematics import get_site_pose

        state = self.convert(obs)
        for site in self.fk_sites:
            try:
                pos, mat = get_site_pose(physics, site)
                state.tip_pos[site] = pos
                state.tip_mat[site] = mat
            except Exception:
                pass  # site might not exist in this env variant
        return state

    # ── batch helper ─────────────────────────────────────────────────────────

    @staticmethod
    def stack(states: list[StructuredState]) -> dict[str, np.ndarray]:
        """
        Stack a list of StructuredStates into batched numpy arrays.
        Used by Dataset.__getitem__ to assemble training batches.
        """
        return {
            "qpos":      np.stack([s.qpos for s in states]),
            "qvel":      np.stack([s.qvel for s in states]),
            "env_state": np.stack([s.env_state for s in states]),
        }
