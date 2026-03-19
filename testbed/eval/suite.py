"""
EvalSuite: run fixed task × seed evaluation and produce metrics + videos.

Design goals:
  • Policy is fully hot-swappable — only needs to implement Policy.predict().
  • Evaluation conditions (seed, tasks, cameras, episode_len) are fixed in
    testbed/eval/tasks.py; do NOT add random elements here.
  • Produces per-rollout MP4 videos with overlays when save_video=True.
  • Returns EvalMetrics which can be serialised to JSON/CSV.

Success rules
─────────────
  MuJoCo backends:  ep_highest_reward == task.env_max_reward
  AGX backend:      mass_in_bucket >= task.mass_thresh
                    for task.hold_steps consecutive steps  (spec §8)
"""

from __future__ import annotations

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
    task_name    Key in EVAL_TASKS (e.g. "agx_excavation_teleop").
    num_rollouts Number of rollouts to run (default 50).
    save_video   If True, write per-rollout MP4 to video_dir.
    video_dir    Directory for MP4 files.
    agx_host     AGX machine host (only used when backend_type=="agx").
    agx_port     AGX machine port (only used when backend_type=="agx").
    mass_thresh  Override task.mass_thresh (AGX success threshold).
    """

    def __init__(
        self,
        policy: Policy,
        task_name: str,
        num_rollouts: int = 50,
        save_video: bool = True,
        video_dir: str | Path | None = None,
        ckpt_path: str = "",
        agx_host: str = "127.0.0.1",
        agx_port: int = 5057,
        mass_thresh: float | None = None,
    ):
        self.policy       = policy
        self.task_def     = get_eval_task(task_name)
        self.num_rollouts = num_rollouts
        self.save_video   = save_video
        self.ckpt_path    = ckpt_path
        self.agx_host     = agx_host
        self.agx_port     = agx_port

        # Allow config override for mass_thresh
        if mass_thresh is not None:
            # EvalTaskDef is frozen; shadow it on the suite instance
            self._mass_thresh = mass_thresh
        else:
            self._mass_thresh = self.task_def.mass_thresh

        if video_dir is None:
            policy_name = type(policy).__name__
            video_dir = Path("runs") / "eval" / task_name / policy_name
        self.video_dir = Path(video_dir)

    # ── Public API ────────────────────────────────────────────────────────────

    def run(self) -> EvalMetrics:
        """Execute all rollouts and return aggregate EvalMetrics."""
        np.random.seed(EVAL_SEED)
        task = self.task_def
        env  = self._make_env(task)

        episode_returns:  list[float] = []
        highest_rewards:  list[float] = []
        episode_lengths:  list[int]   = []
        successes:        list[bool]  = []
        policy_name = type(self.policy).__name__

        try:
            for rollout_id in range(self.num_rollouts):
                np.random.seed(EVAL_SEED + rollout_id)

                # MuJoCo: set deterministic object pose per rollout
                if task.backend_type != "agx" and task.make_object_pose is not None:
                    env.set_initial_object_pose(task.make_object_pose())

                ts = env.reset(seed=EVAL_SEED + rollout_id)
                self.policy.reset()

                rewards:      list[float]      = []
                frames:       list[np.ndarray] = []
                env_states:   list[np.ndarray] = []

                for t in range(task.episode_len):
                    obs = ts.observation

                    # Assemble policy input — add image_{cam} keys (channel-first float)
                    policy_input = dict(obs)
                    for cam in task.camera_names:
                        img = obs.get("images", {}).get(cam)
                        if img is not None:
                            from einops import rearrange
                            policy_input[f"image_{cam}"] = rearrange(
                                np.array(img, dtype=np.float32) / 255.0,
                                "h w c -> c h w",
                            )

                    action = self.policy.predict(policy_input)
                    ts     = env.step(action)

                    r = float(ts.reward) if ts.reward is not None else 0.0
                    rewards.append(r)

                    # AGX: track env_state for mass-based success
                    if task.backend_type == "agx":
                        es = ts.observation.get("env_state")
                        if es is not None:
                            env_states.append(np.array(es, dtype=np.float32))

                    # Video frames
                    if self.save_video and task.camera_names:
                        cam0 = task.camera_names[0]
                        frame = ts.observation.get("images", {}).get(cam0)
                        if frame is not None:
                            frames.append(frame)

                # ── Success detection ─────────────────────────────────────────
                if task.backend_type == "agx":
                    success = _mass_success(
                        env_states,
                        mass_thresh=self._mass_thresh,
                        hold_steps=task.hold_steps,
                        mass_idx=0,   # schema: env_state[0] = mass_in_bucket
                    )
                    ep_highest = 1.0 if success else 0.0
                else:
                    ep_highest = float(max(rewards)) if rewards else 0.0
                    success    = ep_highest == task.env_max_reward

                ep_return = float(np.sum(rewards))
                episode_returns.append(ep_return)
                highest_rewards.append(ep_highest)
                episode_lengths.append(len(rewards))
                successes.append(success)

                print(
                    f"Rollout {rollout_id:3d}  "
                    f"return={ep_return:.2f}  "
                    f"success={'✓' if success else '✗'}"
                )

                if self.save_video and frames:
                    self.video_dir.mkdir(parents=True, exist_ok=True)
                    dt = getattr(env, "dt", 0.02)
                    save_eval_video(
                        frames=frames,
                        dt=dt,
                        video_path=self.video_dir / f"rollout_{rollout_id:03d}.mp4",
                        reward_curve=rewards,
                        phase_labels=None,
                        success=success,
                    )
        finally:
            if hasattr(env, "close"):
                env.close()

        metrics = EvalMetrics.from_rollouts(
            task_name       = task.name,
            policy_name     = policy_name,
            ckpt_path       = self.ckpt_path,
            episode_returns = episode_returns,
            highest_rewards = highest_rewards,
            env_max_reward  = 1.0 if task.backend_type == "agx" else task.env_max_reward,
            episode_lengths = episode_lengths,
            extra           = {"success_list": successes},
        )
        print("\n" + metrics.summary())
        return metrics

    # ── Environment factory ───────────────────────────────────────────────────

    def _make_env(self, task: EvalTaskDef):
        if task.backend_type == "agx":
            from testbed.backends.agx.backend import AGXSimBackend
            return AGXSimBackend(host=self.agx_host, port=self.agx_port)
        elif task.backend_type == "mujoco_ee":
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


# ─── AGX success rule (spec §8) ───────────────────────────────────────────────

def _mass_success(
    env_states: list[np.ndarray],
    mass_thresh: float,
    hold_steps: int,
    mass_idx: int = 0,
) -> bool:
    """
    Returns True if mass_in_bucket >= mass_thresh for hold_steps
    consecutive steps at any point in the episode.
    """
    if not env_states or mass_thresh <= 0.0:
        return False
    consecutive = 0
    for es in env_states:
        if len(es) > mass_idx and es[mass_idx] >= mass_thresh:
            consecutive += 1
            if consecutive >= hold_steps:
                return True
        else:
            consecutive = 0
    return False
