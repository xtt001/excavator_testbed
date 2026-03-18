"""
Fixed evaluation task × seed definitions.

IMPORTANT: The seed used here (EVAL_SEED = 1000) must NEVER be changed.
           All evaluation results must use this exact seed for fair comparison.
"""

from __future__ import annotations

from dataclasses import dataclass, field
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
    name             Unique string identifier.
    equipment_model  Asset folder name (e.g. "excavator_simple").
    episode_len      Maximum timesteps per rollout.
    camera_names     Cameras to record for video output.
    env_max_reward   Maximum achievable reward (for MuJoCo reward-based success).
    backend_type     "mujoco" | "mujoco_ee" | "agx"
    make_object_pose Optional callable that returns a pose for MuJoCo tasks.
                     Not used by AGX — terrain reset is handled by RESET_REQ.

    AGX-specific success rule (used when backend_type == "agx"):
    mass_thresh      mass_in_bucket must reach this value (AGX units).
    hold_steps       Number of consecutive steps above mass_thresh = success.
                     Default 25 = 0.5s @ 50Hz.
    """
    name:             str
    equipment_model:  str
    episode_len:      int
    camera_names:     list[str]
    backend_type:     str = "mujoco_ee"
    env_max_reward:   float = 4.0
    make_object_pose: Callable[[], np.ndarray] | None = None
    # AGX success params
    mass_thresh:      float = 0.0    # set to team-defined value when known
    hold_steps:       int   = 25     # 0.5s @ 50Hz


# ─── MuJoCo pose samplers ─────────────────────────────────────────────────────

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


# ─── Task definitions ─────────────────────────────────────────────────────────

EVAL_TASKS: dict[str, EvalTaskDef] = {
    # ── MuJoCo legacy tasks (kept for compat) ─────────────────────────────────
    "sim_transfer_cube_scripted": EvalTaskDef(
        name             = "sim_transfer_cube_scripted",
        equipment_model  = "vx300s_bimanual",
        episode_len      = 400,
        camera_names     = ["top"],
        env_max_reward   = 4.0,
        make_object_pose = _sample_transfer_cube,
        backend_type     = "mujoco",
    ),
    "sim_insertion_scripted": EvalTaskDef(
        name             = "sim_insertion_scripted",
        equipment_model  = "vx300s_bimanual",
        episode_len      = 500,
        camera_names     = ["top", "left_wrist", "right_wrist"],
        env_max_reward   = 4.0,
        make_object_pose = _sample_insertion,
        backend_type     = "mujoco_ee",
    ),
    "sim_lifting_cube_scripted": EvalTaskDef(
        name             = "sim_lifting_cube_scripted",
        equipment_model  = "excavator_simple",
        episode_len      = 400,
        camera_names     = ["front_close", "side"],
        env_max_reward   = 3.0,
        make_object_pose = _sample_excavator,
        backend_type     = "mujoco",
    ),
    # ── AGX excavation task ───────────────────────────────────────────────────
    "agx_excavation_teleop": EvalTaskDef(
        name             = "agx_excavation_teleop",
        equipment_model  = "agxunity",
        episode_len      = 500,          # 10s @ 50Hz
        camera_names     = ["fpv"],
        backend_type     = "agx",
        # Success: mass_in_bucket >= mass_thresh for hold_steps consecutive steps.
        # mass_thresh is set in eval_agx_v0.yaml and overrides this default.
        mass_thresh      = 1.0,          # placeholder — override in config
        hold_steps       = 25,           # 0.5s @ 50Hz (locked per spec)
    ),
}


def get_eval_task(name: str) -> EvalTaskDef:
    if name not in EVAL_TASKS:
        raise KeyError(
            f"Unknown eval task {name!r}. "
            f"Available: {list(EVAL_TASKS.keys())}"
        )
    return EVAL_TASKS[name]
