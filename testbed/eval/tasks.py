"""
Fixed evaluation task × seed definitions.

IMPORTANT: The seed used here (EVAL_SEED = 1000) must NEVER be changed.
           All evaluation results must use this exact seed for fair comparison.

These definitions mirror the legacy `SIM_TASK_CONFIGS` in constants.py but
are stripped to only the fields needed by the evaluator.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np


EVAL_SEED = 1000  # FIXED — never change for reproducible comparisons


@dataclass(frozen=True)
class EvalTaskDef:
    """
    Everything the EvalSuite needs to run one task.

    Attributes
    ----------
    name            Unique string identifier.
    equipment_model Asset folder name (e.g. "excavator_simple").
    episode_len     Maximum timesteps per rollout.
    camera_names    Cameras to record for video output.
    env_max_reward  Maximum achievable reward (for success detection).
    make_object_pose Callable that returns a new object pose for each rollout.
    backend_type    "mujoco" | "mujoco_ee".
    """
    name:             str
    equipment_model:  str
    episode_len:      int
    camera_names:     list[str]
    env_max_reward:   float
    make_object_pose: Callable[[], np.ndarray]
    backend_type:     str = "mujoco_ee"


# ─── Pose samplers ────────────────────────────────────────────────────────────

def _sample_transfer_cube() -> np.ndarray:
    from testbed.backends.mujoco.tasks.sampling import sample_box_pose
    return sample_box_pose()


def _sample_insertion() -> np.ndarray:
    from testbed.backends.mujoco.tasks.sampling import sample_insertion_pose
    peg, sock = sample_insertion_pose()
    return np.concatenate([peg, sock])


def _sample_lifting_cube() -> np.ndarray:
    from testbed.backends.mujoco.tasks.sampling import sample_box_pose
    return sample_box_pose()


def _sample_excavator() -> np.ndarray:
    from testbed.backends.mujoco.tasks.sampling import sample_box_pose_for_excavator
    return sample_box_pose_for_excavator()


# ─── Fixed task definitions ───────────────────────────────────────────────────

EVAL_TASKS: dict[str, EvalTaskDef] = {
    "sim_transfer_cube_scripted": EvalTaskDef(
        name            = "sim_transfer_cube_scripted",
        equipment_model = "vx300s_bimanual",
        episode_len     = 400,
        camera_names    = ["top"],   # must match training camera_names in act_v0.yaml
        env_max_reward  = 4.0,
        make_object_pose= _sample_transfer_cube,
        backend_type    = "mujoco",  # joint-space: model outputs 14-DOF joint commands
    ),
    "sim_insertion_scripted": EvalTaskDef(
        name            = "sim_insertion_scripted",
        equipment_model = "vx300s_bimanual",
        episode_len     = 500,
        camera_names    = ["top", "left_wrist", "right_wrist"],
        env_max_reward  = 4.0,
        make_object_pose= _sample_insertion,
        backend_type    = "mujoco_ee",
    ),
    "sim_lifting_cube_scripted": EvalTaskDef(
        name            = "sim_lifting_cube_scripted",
        equipment_model = "excavator_simple",
        episode_len     = 400,
        camera_names    = ["front_close", "side"],
        env_max_reward  = 3.0,
        make_object_pose= _sample_excavator,
        backend_type    = "mujoco",
    ),
}


def get_eval_task(name: str) -> EvalTaskDef:
    if name not in EVAL_TASKS:
        raise KeyError(
            f"Unknown eval task {name!r}. "
            f"Available: {list(EVAL_TASKS.keys())}"
        )
    return EVAL_TASKS[name]
