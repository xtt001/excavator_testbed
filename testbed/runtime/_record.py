"""Internal record helper called by Runner.record()."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np


def record_episodes(config: dict[str, Any]) -> None:
    task_cfg  = config.get("task", {})
    task_name = task_cfg.get("name", config.get("task_name", ""))
    dataset_dir   = Path(task_cfg.get("dataset_dir", config.get("dataset_dir", "data")))
    num_episodes  = task_cfg.get("num_episodes", config.get("num_episodes", 50))
    episode_len   = task_cfg.get("episode_len", config.get("episode_len", 400))
    equipment_model = task_cfg.get("equipment_model", config.get("equipment_model", "excavator_simple"))
    pipeline      = task_cfg.get("pipeline", "ee_replay")

    from testbed.data.recorder import EpisodeRecorder

    if pipeline == "ee_replay":
        from testbed.backends.mujoco.ee_backend import make_mujoco_ee_env
        from testbed.backends.mujoco.scripted_policies import (
            PickAndTransferPolicy,
            InsertionPolicy,
            LiftingAndMovingPolicy,
        )
        env = make_mujoco_ee_env(task_name=task_name, equipment_model=equipment_model)
        ScriptedPolicy = _select_scripted_policy_ee(task_name, equipment_model)
    elif pipeline == "joint_replay":
        from testbed.backends.mujoco.backend import make_mujoco_env
        from testbed.backends.mujoco.scripted_policies import ExcavatorJointSpaceDigDumpPolicy
        env = make_mujoco_env(task_name=task_name, equipment_model=equipment_model)
        ScriptedPolicy = ExcavatorJointSpaceDigDumpPolicy
    else:
        raise ValueError(f"Unknown pipeline: {pipeline!r}")

    from testbed.backends.mujoco.tasks.sampling import (
        sample_box_pose,
        sample_box_pose_for_excavator,
        sample_insertion_pose,
    )

    dataset_dir.mkdir(parents=True, exist_ok=True)
    success_count = 0

    for ep_idx in range(num_episodes):
        object_pose = _sample_pose(task_name, equipment_model)
        env.set_initial_object_pose(object_pose)

        np.random.seed(ep_idx)
        ts = env.reset()
        scripted = ScriptedPolicy(inject_noise=True)

        recorder = EpisodeRecorder(
            output_dir=dataset_dir,
            episode_idx=ep_idx,
            metadata={
                "task_name":    task_name,
                "sim_backend":  pipeline,
                "seed":         ep_idx,
                "param_version": "v0",
            },
        )

        for t in range(episode_len):
            action = scripted(ts)
            recorder.record(ts.observation, action, reward=float(ts.reward or 0.0))
            ts = env.step(action)

        success = bool(ts.reward == env.max_reward) if hasattr(env, "max_reward") else False
        path = recorder.save(success=success)
        if success:
            success_count += 1
        print(f"Episode {ep_idx:4d} → {path.name}  success={'✓' if success else '✗'}")

    print(f"\nDone. {success_count}/{num_episodes} episodes succeeded.")


def _sample_pose(task_name: str, equipment_model: str) -> np.ndarray:
    from testbed.backends.mujoco.tasks.sampling import (
        sample_box_pose,
        sample_box_pose_for_excavator,
        sample_insertion_pose,
    )
    if "insertion" in task_name:
        peg, sock = sample_insertion_pose()
        return np.concatenate([peg, sock])
    if "excavator" in equipment_model:
        return sample_box_pose_for_excavator()
    return sample_box_pose()


def _select_scripted_policy_ee(task_name: str, equipment_model: str):
    from testbed.backends.mujoco.scripted_policies import (
        PickAndTransferPolicy,
        InsertionPolicy,
        LiftingAndMovingPolicy,
    )
    if "transfer_cube" in task_name:
        return PickAndTransferPolicy
    if "insertion" in task_name:
        return InsertionPolicy
    return LiftingAndMovingPolicy
