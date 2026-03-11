"""
Abstract simulation backend interface.

Any sim backend (MuJoCo, Isaac, AGX, …) must implement SimBackend.
The testbed core only depends on this interface — never on dm_control directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import numpy as np


class SimBackend(ABC):
    """
    Minimal simulation backend interface consumed by the testbed core.

    Terminology
    -----------
    raw_obs : dict
        Dictionary with at least::

            {
                "qpos":   np.ndarray  (state_dim,)
                "qvel":   np.ndarray  (state_dim,)
                "images": dict[str, np.ndarray]   # cam_name -> (H, W, 3) uint8
                "env_state": np.ndarray           # object poses etc.
            }

        Additional keys are allowed (e.g. "mocap_pose_right" for EE envs).

    timestep : Any
        Backend-specific timestep object returned by reset/step.
        The testbed accesses it only via `.observation` (raw_obs) and `.reward`.
    """

    @abstractmethod
    def reset(self, seed: int | None = None) -> Any:
        """Reset the environment and return the first timestep."""
        raise NotImplementedError

    @abstractmethod
    def step(self, action: np.ndarray) -> Any:
        """Apply action and return the next timestep."""
        raise NotImplementedError

    @abstractmethod
    def render(self, camera_id: str, height: int = 480, width: int = 640) -> np.ndarray:
        """Render a camera view outside the normal observation pipeline."""
        raise NotImplementedError

    @property
    @abstractmethod
    def dt(self) -> float:
        """Control timestep in seconds."""
        raise NotImplementedError

    @property
    @abstractmethod
    def max_reward(self) -> float:
        """Maximum achievable reward for success detection."""
        raise NotImplementedError

    @abstractmethod
    def set_initial_object_pose(self, pose: np.ndarray) -> None:
        """
        Set the initial pose of the primary manipulated object.

        Parameters
        ----------
        pose : np.ndarray, shape (7,)
            [x, y, z, qw, qx, qy, qz]
        """
        raise NotImplementedError


class EESimBackend(ABC):
    """
    Backend for end-effector-space simulation (scripted demo collection only).

    Used during the EE rollout phase of data collection.
    Policy/eval code should never depend on this; they use SimBackend only.
    """

    @abstractmethod
    def reset(self) -> Any:
        raise NotImplementedError

    @abstractmethod
    def step(self, action: np.ndarray) -> Any:
        raise NotImplementedError

    @property
    @abstractmethod
    def max_reward(self) -> float:
        raise NotImplementedError
