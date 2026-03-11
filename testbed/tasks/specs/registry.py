"""
Task specifications — fixed parameters for each named task.

These are the canonical definitions consumed by the testbed core.
They mirror SIM_TASK_CONFIGS from legacy/constants.py but are typed Pydantic models.
"""

from __future__ import annotations

from pydantic import BaseModel


class TaskSpec(BaseModel):
    """Immutable specification for a simulation task."""

    task_name: str
    equipment_model: str
    episode_len: int
    camera_names: list[str]
    state_dim: int
    max_reward: float
    success_reward_threshold: float


# ─── Registry ─────────────────────────────────────────────────────────────────

TASK_SPECS: dict[str, TaskSpec] = {
    "sim_transfer_cube_scripted": TaskSpec(
        task_name="sim_transfer_cube_scripted",
        equipment_model="vx300s_bimanual",
        episode_len=400,
        camera_names=["top"],
        state_dim=14,
        max_reward=4,
        success_reward_threshold=4.0,
    ),
    "sim_insertion_scripted": TaskSpec(
        task_name="sim_insertion_scripted",
        equipment_model="vx300s_bimanual",
        episode_len=400,
        camera_names=["top"],
        state_dim=14,
        max_reward=4,
        success_reward_threshold=4.0,
    ),
    "sim_lifting_cube_scripted": TaskSpec(
        task_name="sim_lifting_cube_scripted",
        equipment_model="excavator_simple",
        episode_len=400,
        camera_names=["top"],
        state_dim=4,
        max_reward=4,
        success_reward_threshold=3.0,
    ),
}


def get_task_spec(task_name: str) -> TaskSpec:
    if task_name not in TASK_SPECS:
        raise KeyError(f"Unknown task: {task_name!r}. Available: {list(TASK_SPECS)}")
    return TASK_SPECS[task_name]
