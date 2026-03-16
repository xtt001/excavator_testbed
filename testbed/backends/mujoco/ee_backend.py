"""
MuJoCo EESimBackend — wraps dm_control EE environments for scripted demo collection.

This backend is ONLY used during the EE-space rollout phase of data collection.
Policy code and the evaluator NEVER touch this backend directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from dm_control import mujoco
from dm_control.rl import control

from testbed.backends.base import EESimBackend
from testbed.backends.mujoco.tasks.bimanual import (
    BOX_POSE,
)
from testbed.backends.mujoco.tasks.constants import DT
from testbed.backends.mujoco.tasks.excavator import ExcavatorLiftingCubeEETask

# EE-space task classes for non-excavator robots (imported from ee_sim_env equivalent)
from testbed.backends.mujoco.ee_tasks import (
    InsertionEETask,
    LiftingCubeEETask,
    TransferCubeEETask,
)

_ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets"


def _xml(equipment_model: str, filename: str) -> str:
    path = _ASSETS_DIR / equipment_model / filename
    if not path.exists():
        raise FileNotFoundError(f"MJCF not found: {path}")
    return str(path)


def make_mujoco_ee_env(task_name: str, equipment_model: str):
    """Build a dm_control EE Environment."""
    if "sim_transfer_cube" in task_name:
        physics = mujoco.Physics.from_xml_path(
            _xml(equipment_model, "bimanual_viperx_ee_transfer_cube.xml")
        )
        task = TransferCubeEETask(random=False)
    elif "sim_insertion" in task_name:
        physics = mujoco.Physics.from_xml_path(
            _xml(equipment_model, "bimanual_viperx_ee_insertion.xml")
        )
        task = InsertionEETask(random=False)
    elif "sim_lifting_cube" in task_name:
        if equipment_model == "excavator_simple":
            physics = mujoco.Physics.from_xml_path(
                _xml(equipment_model, "single_viperx_ee_transfer_cube.xml")
            )
            task = ExcavatorLiftingCubeEETask(random=False)
        else:
            physics = mujoco.Physics.from_xml_path(
                _xml(equipment_model, "single_viperx_ee_transfer_cube.xml")
            )
            task = LiftingCubeEETask(random=False, equipment_model=equipment_model)
    else:
        raise NotImplementedError(f"Unknown task: {task_name!r}")

    return control.Environment(
        physics, task, time_limit=20, control_timestep=DT, flat_observation=False
    )


class MuJoCoEESimBackend(EESimBackend):
    """EE-space MuJoCo backend (scripted demo collection only)."""

    def __init__(self, task_name: str, equipment_model: str):
        self._env = make_mujoco_ee_env(task_name, equipment_model)

    def reset(self) -> Any:
        return self._env.reset()

    def step(self, action: np.ndarray) -> Any:
        return self._env.step(action)

    def set_initial_object_pose(self, object_pose: np.ndarray) -> None:
        BOX_POSE[0] = object_pose

    @property
    def max_reward(self) -> float:
        return self._env.task.max_reward
