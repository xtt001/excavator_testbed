"""
EvalSuite: run fixed task × seed evaluation and produce metrics + videos.

Design goals:
  • Policy is fully hot-swappable — only needs to implement Policy.predict().
  • Evaluation conditions (seed, tasks, cameras, episode_len) are fixed in
    testbed/eval/tasks.py; do NOT add random elements here.
  • Produces per-rollout MP4 videos with overlays when save_video=True.
  • Returns EvalMetrics which can be serialised to JSON/CSV.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from testbed.eval.metrics import EvalMetrics
from testbed.eval.tasks import EVAL_SEED, EvalTaskDef, get_eval_task
from testbed.eval.video import save_eval_video
from testbed.policies.base import Policy


class EvalSuite:
    """
    Orchestrate rollouts for one policy over one task.

    Parameters
    ----------
    policy       Any Policy subclass instance.
    task_name    Key in EVAL_TASKS (e.g. "sim_lifting_cube_scripted").
    num_rollouts Number of rollouts to run (default 50).
    save_video   If True, write per-rollout MP4 to video_dir.
    video_dir    Directory for MP4 files (default: "runs/eval/<task>/<policy>/").
    device       Torch device string for policy (unused by EvalSuite directly).
    """

    def __init__(
        self,
        policy: Policy,
        task_name: str,
        num_rollouts: int = 50,
        save_video: bool = True,
        video_dir: str | Path | None = None,
        ckpt_path: str = "",
    ):
        self.policy       = policy
        self.task_def     = get_eval_task(task_name)
        self.num_rollouts = num_rollouts
        self.save_video   = save_video
        self.ckpt_path    = ckpt_path

        if video_dir is None:
            policy_name = type(policy).__name__
            video_dir = Path("runs") / "eval" / task_name / policy_name
        self.video_dir = Path(video_dir)

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self) -> EvalMetrics:
        """
        Execute all rollouts and return aggregate EvalMetrics.
        """
        np.random.seed(EVAL_SEED)
        task = self.task_def
        env  = self._make_env(task)

        episode_returns: list[float]  = []
        highest_rewards: list[float]  = []
        episode_lengths: list[int]    = []
        policy_name = type(self.policy).__name__

        for rollout_id in range(self.num_rollouts):
            # fixed pose per rollout_id (deterministic re-seed each rollout)
            np.random.seed(EVAL_SEED + rollout_id)
            object_pose = task.make_object_pose()
            env.set_initial_object_pose(object_pose)

            ts = env.reset()
            self.policy.reset()

            rewards:     list[float]     = []
            frames:      list[np.ndarray]= []
            phase_labels:list[str]       = []

            for t in range(task.episode_len):
                obs = ts.observation

                # ── assemble policy input ─────────────────────────────────
                policy_input = dict(obs)
                # add image_<cam> keys for ACT-style policies
                for cam in task.camera_names:
                    if "images" in obs and cam in obs["images"]:
                        import torch
                        from einops import rearrange
                        img = rearrange(
                            np.array(obs["images"][cam], dtype=np.float32) / 255.0,
                            "h w c -> c h w",
                        )
                        policy_input[f"image_{cam}"] = img

                action = self.policy.predict(policy_input)
                ts     = env.step(action)

                rewards.append(float(ts.reward) if ts.reward is not None else 0.0)

                # ── frames for video ──────────────────────────────────────
                if self.save_video and task.camera_names:
                    cam0 = task.camera_names[0]
                    if "images" in ts.observation and cam0 in ts.observation["images"]:
                        frames.append(ts.observation["images"][cam0])

                # ── phase label (excavator only) ──────────────────────────
                phase_labels.append("")

            ep_return = float(np.sum([r for r in rewards if r is not None]))
            ep_highest = float(np.max(rewards)) if rewards else 0.0
            episode_returns.append(ep_return)
            highest_rewards.append(ep_highest)
            episode_lengths.append(task.episode_len)

            success = ep_highest == task.env_max_reward
            print(
                f"Rollout {rollout_id:3d}  "
                f"return={ep_return:.2f}  "
                f"max_reward={ep_highest:.2f}  "
                f"success={'✓' if success else '✗'}"
            )

            if self.save_video and frames:
                self.video_dir.mkdir(parents=True, exist_ok=True)
                from testbed.backends.mujoco.tasks.constants import DT
                save_eval_video(
                    frames=frames,
                    dt=DT,
                    video_path=self.video_dir / f"rollout_{rollout_id:03d}.mp4",
                    reward_curve=rewards,
                    phase_labels=phase_labels if any(phase_labels) else None,
                    success=success,
                )

        metrics = EvalMetrics.from_rollouts(
            task_name       = task.name,
            policy_name     = policy_name,
            ckpt_path       = self.ckpt_path,
            episode_returns = episode_returns,
            highest_rewards = highest_rewards,
            env_max_reward  = task.env_max_reward,
            episode_lengths = episode_lengths,
        )
        print("\n" + metrics.summary())
        return metrics

    # ── Environment factory ───────────────────────────────────────────────────

    @staticmethod
    def _make_env(task: EvalTaskDef):
        if task.backend_type == "mujoco_ee":
            from testbed.backends.mujoco.ee_backend import MuJoCoEESimBackend
            return MuJoCoEESimBackend(
                task_name=task.name,
                equipment_model=task.equipment_model,
            )
        else:
            from testbed.backends.mujoco.backend import MuJoCoSimBackend
            return MuJoCoSimBackend(
                task_name=task.name,
                equipment_model=task.equipment_model,
            )
