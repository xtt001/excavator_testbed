"""
MuJoCo SimBackend — wraps dm_control environments for joint-space rollout.

This is the backend used by:
  - EpisodeRecorder (data collection, joint-space replay)
  - EvalSuite (policy rollout)
  - Runner (train-eval loop)

It does NOT expose any dm_control types at the boundary — callers see only
numpy arrays and the raw_obs dict contract defined in backends/base.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from dm_control import mujoco
from dm_control.rl import control

from testbed.backends.base import SimBackend
from testbed.backends.mujoco.tasks.bimanual import (
    BOX_POSE,
    InsertionTask,
    TransferCubeTask,
)
from testbed.backends.mujoco.tasks.constants import DT
from testbed.backends.mujoco.tasks.excavator import ExcavatorLiftingCubeTask
from testbed.backends.mujoco.tasks.single_arm import LiftingCubeTask

# Default assets directory (resolved at import time)
_ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets"


def _xml(equipment_model: str, filename: str) -> str:
    path = _ASSETS_DIR / equipment_model / filename
    if not path.exists():
        raise FileNotFoundError(f"MJCF not found: {path}")
    return str(path)


def make_mujoco_env(task_name: str, equipment_model: str):
    """
    Build a dm_control Environment for the given task + equipment.

    Returns the raw dm_control Environment (not wrapped in SimBackend).
    """
    if "sim_transfer_cube" in task_name:
        physics = mujoco.Physics.from_xml_path(
            _xml(equipment_model, "bimanual_viperx_transfer_cube.xml")
        )
        task = TransferCubeTask(random=False)
    elif "sim_insertion" in task_name:
        physics = mujoco.Physics.from_xml_path(
            _xml(equipment_model, "bimanual_viperx_insertion.xml")
        )
        task = InsertionTask(random=False)
    elif "sim_lifting_cube" in task_name:
        if equipment_model == "excavator_simple":
            physics = mujoco.Physics.from_xml_path(
                _xml(equipment_model, "single_viperx_transfer_cube.xml")
            )
            task = ExcavatorLiftingCubeTask(random=False)
        else:
            physics = mujoco.Physics.from_xml_path(
                _xml(equipment_model, "single_viperx_transfer_cube.xml")
            )
            task = LiftingCubeTask(random=False, equipment_model=equipment_model)
    else:
        raise NotImplementedError(f"Unknown task: {task_name!r}")

    return control.Environment(
        physics, task, time_limit=20, control_timestep=DT, flat_observation=False
    )


class MuJoCoSimBackend(SimBackend):
    """
    Joint-space MuJoCo simulation backend.

    Parameters
    ----------
    task_name : str
    equipment_model : str
    """

    def __init__(self, task_name: str, equipment_model: str):
        self._task_name = task_name
        self._equipment_model = equipment_model
        self._env = make_mujoco_env(task_name, equipment_model)

    # ── SimBackend interface ──────────────────────────────────────────────────

    def reset(self, seed: int | None = None) -> Any:
        # dm_control does not accept a seed in reset(); seed is applied
        # externally by seeding numpy before calling reset.
        if seed is not None:
            np.random.seed(seed)
        return self._env.reset()

    def step(self, action: np.ndarray) -> Any:
        return self._env.step(action)

    def render(self, camera_id: str, height: int = 480, width: int = 640) -> np.ndarray:
        return self._env._physics.render(height=height, width=width, camera_id=camera_id)

    @property
    def dt(self) -> float:
        return DT

    @property
    def max_reward(self) -> float:
        return self._env.task.max_reward

    def set_initial_object_pose(self, pose: np.ndarray) -> None:
        BOX_POSE[0] = pose

    # ── Extras ────────────────────────────────────────────────────────────────

    @property
    def task_name(self) -> str:
        return self._task_name

    @property
    def equipment_model(self) -> str:
        return self._equipment_model
