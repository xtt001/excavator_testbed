"""Internal record helper called by Runner.record()."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


def record_episodes(config: dict[str, Any]) -> None:
    # ── resolve config (supports flat task_v0.yaml and nested act_v0.yaml) ────────
    task_cfg        = config.get("task", {})
    task_name       = task_cfg.get("task_name", config.get("task_name", ""))
    dataset_dir     = Path(task_cfg.get("dataset_dir", config.get("dataset_dir", "data")))
    num_episodes    = task_cfg.get("num_episodes", config.get("num_episodes", 50))
    episode_len     = task_cfg.get("episode_len", config.get("episode_len", 400))
    equipment_model = task_cfg.get("equipment_model", config.get("equipment_model", "excavator_simple"))
    pipeline        = task_cfg.get("excavator_pipeline", config.get("excavator_pipeline", "ee_replay"))
    only_success    = task_cfg.get("only_save_success", config.get("only_save_success", False))
    success_thresh  = task_cfg.get("success_reward_threshold", config.get("success_reward_threshold", None))
    target_success  = task_cfg.get("target_success_episodes", config.get("target_success_episodes", None))
    inject_noise    = task_cfg.get("inject_noise", config.get("inject_noise", False))
    is_bimanual     = "bimanual" in equipment_model

    from testbed.data.recorder import EpisodeRecorder
    from testbed.backends.mujoco.tasks.constants import puppet_gripper_pos_normalize

    ScriptedPolicy = _select_scripted_policy_ee(task_name, equipment_model)

    dataset_dir.mkdir(parents=True, exist_ok=True)
    success_count = 0
    saved_count   = 0
    max_attempts  = num_episodes * 5

    for attempt_idx in range(max_attempts):
        if target_success is not None and saved_count >= int(target_success):
            break
        if not only_success and saved_count >= num_episodes:
            break

        object_pose = _sample_pose(task_name, equipment_model)

        if pipeline in ("ee_replay", "ee"):
            # ── Phase 1: EE-space rollout to get joint trajectory ───────────────
            from testbed.backends.mujoco.ee_backend import MuJoCoEESimBackend
            ee_env = MuJoCoEESimBackend(task_name=task_name, equipment_model=equipment_model)
            ee_env.set_initial_object_pose(object_pose)
            np.random.seed(attempt_idx)
            ts = ee_env.reset()
            ee_episode = [ts]
            scripted = ScriptedPolicy(inject_noise=inject_noise)
            for _ in range(episode_len):
                action = scripted(ts)
                ts = ee_env.step(action)
                ee_episode.append(ts)

            # Extract joint qpos trajectory; replace gripper channel with ctrl value
            joint_traj        = [s.observation["qpos"].copy() for s in ee_episode]
            gripper_ctrl_traj = [s.observation["gripper_ctrl"].copy() for s in ee_episode]
            if is_bimanual:
                for joint, ctrl in zip(joint_traj, gripper_ctrl_traj):
                    joint[6]   = puppet_gripper_pos_normalize(ctrl[0])
                    joint[6+7] = puppet_gripper_pos_normalize(ctrl[2])
            else:
                for joint, ctrl in zip(joint_traj, gripper_ctrl_traj):
                    joint[6] = puppet_gripper_pos_normalize(ctrl[0])

            subtask_info = ee_episode[0].observation["env_state"].copy()
            del ee_env, ee_episode, scripted

            # ── Phase 2: Replay joint trajectory in joint-space sim ────────────
            from testbed.backends.mujoco.backend import MuJoCoSimBackend
            sim_env = MuJoCoSimBackend(task_name=task_name, equipment_model=equipment_model)
            sim_env.set_initial_object_pose(subtask_info)
            np.random.seed(attempt_idx)
            ts = sim_env.reset()
            episode_replay = [ts]
            for t in range(len(joint_traj)):
                ts = sim_env.step(joint_traj[t])
                episode_replay.append(ts)

            max_reward = max(float(s.reward or 0) for s in episode_replay[1:])
            env_max    = float(sim_env.max_reward)
            threshold  = float(success_thresh) if success_thresh is not None else env_max
            episode_ok = max_reward >= threshold

            # Align: action[t] commands robot at step t; obs[t] is state before step t
            # Truncate both to episode_len (drop the extra final state)
            joint_traj     = joint_traj[:episode_len]
            episode_replay = episode_replay[:episode_len]
            del sim_env

        elif pipeline == "joint_replay":
            from testbed.backends.mujoco.backend import MuJoCoSimBackend
            from testbed.backends.mujoco.scripted_policies import ExcavatorJointSpaceDigDumpPolicy
            sim_env = MuJoCoSimBackend(task_name=task_name, equipment_model=equipment_model)
            sim_env.set_initial_object_pose(object_pose)
            np.random.seed(attempt_idx)
            ts = sim_env.reset()
            episode_replay = [ts]
            joint_traj = []
            scripted = ExcavatorJointSpaceDigDumpPolicy(inject_noise=inject_noise)
            for _ in range(episode_len):
                action = scripted(ts)
                joint_traj.append(action.copy())
                ts = sim_env.step(action)
                episode_replay.append(ts)

            max_reward = max(float(s.reward or 0) for s in episode_replay[1:])
            env_max    = float(sim_env.max_reward)
            threshold  = float(success_thresh) if success_thresh is not None else env_max
            episode_ok = max_reward >= threshold

            joint_traj     = joint_traj[:episode_len]
            episode_replay = episode_replay[:episode_len]
            del sim_env
        else:
            raise ValueError(f"Unknown pipeline: {pipeline!r}")

        status     = "✓" if episode_ok else "✗"
        should_save = (not only_success) or episode_ok
        print(
            f"Attempt {attempt_idx:4d}  max_reward={max_reward:.1f}/{threshold:.1f}  {status}  "
            f"{'saving' if should_save else 'skipping'}"
        )

        if not should_save:
            continue

        recorder = EpisodeRecorder(
            output_dir=dataset_dir,
            episode_idx=saved_count,
            metadata={
                "task_name":     task_name,
                "sim_backend":   pipeline,
                "seed":          attempt_idx,
                "param_version": "v0",
            },
        )
        for t in range(len(joint_traj)):
            recorder.record(
                episode_replay[t].observation,
                joint_traj[t],
                reward=float(episode_replay[t].reward or 0.0),
            )
        path = recorder.save(success=episode_ok)
        saved_count += 1
        if episode_ok:
            success_count += 1
        print(f"  Saved → {path.name}")

    print(f"\nDone. {success_count} successful / {saved_count} saved  (out of {attempt_idx+1} attempts).")


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
