"""
EvalSuite: run fixed task × seed evaluation and produce metrics + videos.

Design goals:
  • Policy is fully hot-swappable — only needs to implement Policy.predict().
  • Evaluation conditions (seed, tasks, cameras, episode_len) are fixed in
    testbed/eval/tasks.py; do NOT add random elements here.
  • Produces per-rollout MP4 videos with overlays when save_video=True.
  • Optionally writes per-rollout JSONL logs plus summary / manifest files.
  • Returns EvalMetrics which can be serialised to JSON/CSV.

Success rules
─────────────
  MuJoCo backends:  ep_highest_reward == task.env_max_reward
  AGX backend:      configurable success mode over retained-mass history and
                    rollout failure summaries. Legacy task_success latch is
                    still recorded for comparison.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from testbed.eval.rollout_logs import (
    build_rollout_manifest,
    build_rollout_summary,
    write_json,
    write_jsonl,
)
from testbed.eval.metrics import EvalMetrics
from testbed.eval.tasks import EVAL_SEED, EvalTaskDef, get_eval_task
from testbed.eval.video import save_eval_video
from testbed.policies.base import Policy
from testbed.tasks.logic.excavator_reward import (
    build_agx_excavation_mission_overrides,
    resolve_agx_field_indices,
)


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
    results_dir  Root directory for eval result artifacts.
    agx_host     AGX machine host (only used when backend_type=="agx").
    agx_port     AGX machine port (only used when backend_type=="agx").
    agx_timeout  AGX socket timeout seconds (only used when backend_type=="agx").
    save_rollout_logs  If True, write JSONL timestep logs and summaries.
    rollout_log_dir    Directory for rollout_XXX.jsonl and summary files.
    step_log_interval  Print step progress every N steps during rollout.
    mass_thresh  Override task.mass_thresh (AGX success threshold).
    hold_steps   Override task.hold_steps for AGX success.
    success_signal_name  Override task.success_signal_name for AGX success.
    env_state_index  Legacy fallback index for AGX success signal lookup.
    reward_overrides Additional AGX reward-shaping overrides.
    agx_success_mode  Primary AGX success mode:
                      "legacy_any" | "final_hold" | "strict_final_hold" |
                      "dump_complete_final_hold" | "strict_dump_complete".
    strict_max_failures  Optional failure-count upper bounds used by the
                      strict AGX success mode, e.g.
                      {"hard_target_collision": 0, "spill_before_target": 0}.
    residual_bucket_mass_thresh  For dump-complete success, final bucket mass
                      must stay at or below this threshold for hold_steps.
    """

    def __init__(
        self,
        policy: Policy,
        task_name: str,
        num_rollouts: int = 50,
        save_video: bool = True,
        video_dir: str | Path | None = None,
        results_dir: str | Path | None = None,
        ckpt_path: str = "",
        save_rollout_logs: bool = True,
        rollout_log_dir: str | Path | None = None,
        step_log_interval: int = 50,
        agx_host: str = "127.0.0.1",
        agx_port: int = 5057,
        agx_timeout: float = 10.0,
        mass_thresh: float | None = None,
        hold_steps: int | None = None,
        success_signal_name: str | None = None,
        env_state_index: int | None = None,
        reward_overrides: dict[str, float] | None = None,
        agx_success_mode: str = "legacy_any",
        strict_max_failures: dict[str, int] | None = None,
        residual_bucket_mass_thresh: float = 100.0,
    ):
        self.policy       = policy
        self.task_def     = get_eval_task(task_name)
        self.num_rollouts = num_rollouts
        self.save_video   = save_video
        self.ckpt_path    = ckpt_path
        self.save_rollout_logs = bool(save_rollout_logs)
        self.step_log_interval = max(0, int(step_log_interval))
        self.agx_host     = agx_host
        self.agx_port     = agx_port
        self.agx_timeout  = agx_timeout
        self._env_state_index = None if env_state_index is None else int(env_state_index)

        # Allow config override for mass_thresh
        if mass_thresh is not None:
            # EvalTaskDef is frozen; shadow it on the suite instance
            self._mass_thresh = mass_thresh
        else:
            self._mass_thresh = self.task_def.mass_thresh
        self._hold_steps = self.task_def.hold_steps if hold_steps is None else int(hold_steps)
        self._success_signal_name = (
            self.task_def.success_signal_name
            if success_signal_name is None
            else str(success_signal_name)
        )
        self._reward_overrides = dict(self.task_def.reward_overrides)
        if reward_overrides:
            self._reward_overrides.update(dict(reward_overrides))
        self._agx_success_mode = str(agx_success_mode)
        self._strict_max_failures = {
            str(name): int(limit)
            for name, limit in (strict_max_failures or {}).items()
        }
        self._residual_bucket_mass_thresh = float(residual_bucket_mass_thresh)

        if video_dir is None:
            policy_name = type(policy).__name__
            video_dir = Path("runs") / "eval" / task_name / policy_name
        self.video_dir = Path(video_dir)
        self.results_dir = None if results_dir is None else Path(results_dir)
        if rollout_log_dir is None:
            default_results_dir = (
                self.results_dir
                if self.results_dir is not None
                else self.video_dir.parent / "results"
            )
            rollout_log_dir = default_results_dir / "rollouts"
        self.rollout_log_dir = Path(rollout_log_dir)

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
        legacy_successes: list[bool]  = []
        final_hold_successes: list[bool] = []
        strict_successes: list[bool]  = []
        dump_complete_successes: list[bool] = []
        strict_dump_complete_successes: list[bool] = []
        final_signal_values: list[float] = []
        max_signal_values: list[float] = []
        final_bucket_values: list[float] = []
        ending_success_consecutive_steps: list[int] = []
        ending_dump_complete_consecutive_steps: list[int] = []
        rollout_summaries: list[dict[str, object]] = []
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
                phase_labels: list[str]        = []
                success_flags: list[bool]      = []
                step_records: list[dict[str, object]] = []

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
                    reward_phase = str(ts.info.get("reward_phase", obs.get("reward_phase", "")))
                    task_success = bool(ts.info.get("task_success", obs.get("task_success", False)))
                    task_step_successes = list(
                        ts.info.get("task_step_successes", obs.get("task_step_successes", []))
                    )
                    task_step_failures = list(
                        ts.info.get("task_step_failures", obs.get("task_step_failures", []))
                    )
                    task_metrics = dict(
                        ts.info.get("task_metrics", obs.get("task_metrics", {}))
                    )
                    warnings = list(ts.info.get("warnings", obs.get("warnings", [])))
                    step_records.append(
                        {
                            "rollout_id": int(rollout_id),
                            "t": int(t),
                            "step_id": int(obs.get("step_id", t)),
                            "sim_time_ns": int(obs.get("sim_time_ns", ts.info.get("sim_time_ns", 0))),
                            "reward": r,
                            "reward_phase": reward_phase,
                            "task_success": task_success,
                            "task_step_successes": task_step_successes,
                            "task_step_failures": task_step_failures,
                            "task_metrics": task_metrics,
                            "qpos": np.array(obs.get("qpos", []), dtype=np.float32),
                            "qvel": np.array(obs.get("qvel", []), dtype=np.float32),
                            "env_state": (
                                None
                                if obs.get("env_state") is None
                                else np.array(obs.get("env_state"), dtype=np.float32)
                            ),
                            "action": np.array(action, dtype=np.float32),
                            "warnings": warnings,
                        }
                    )

                    # AGX: track env_state for mass-based success
                    if task.backend_type == "agx":
                        es = ts.observation.get("env_state")
                        if es is not None:
                            env_states.append(np.array(es, dtype=np.float32))
                        phase_labels.append(reward_phase or "idle")
                        success_flags.append(task_success)

                    # Video frames
                    if self.save_video and task.camera_names:
                        cam0 = task.camera_names[0]
                        frame = ts.observation.get("images", {}).get(cam0)
                        if frame is not None:
                            frames.append(frame)

                    if self._should_log_step_progress(t + 1, task.episode_len):
                        print(
                            f"  rollout {rollout_id:03d}  step {t + 1} / {task.episode_len}"
                        )

                # ── Success detection ─────────────────────────────────────────
                if task.backend_type == "agx":
                    success_summary = self._evaluate_agx_success(
                        env=env,
                        env_states=env_states,
                        success_flags=success_flags,
                        step_records=step_records,
                    )
                    success = bool(success_summary["success"])
                    ep_highest = float(max(rewards)) if rewards else 0.0
                    legacy_successes.append(bool(success_summary["legacy_success"]))
                    final_hold_successes.append(bool(success_summary["final_hold_success"]))
                    strict_successes.append(bool(success_summary["strict_final_hold_success"]))
                    dump_complete_successes.append(
                        bool(success_summary["dump_complete_final_hold_success"])
                    )
                    strict_dump_complete_successes.append(
                        bool(success_summary["strict_dump_complete_success"])
                    )
                    final_signal_values.append(float(success_summary["final_signal_value"]))
                    max_signal_values.append(float(success_summary["max_signal_value"]))
                    final_bucket_values.append(float(success_summary["final_bucket_mass"]))
                    ending_success_consecutive_steps.append(
                        int(success_summary["ending_success_consecutive_steps"])
                    )
                    ending_dump_complete_consecutive_steps.append(
                        int(success_summary["ending_dump_complete_consecutive_steps"])
                    )
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

                video_path = ""
                if self.save_video and frames:
                    self.video_dir.mkdir(parents=True, exist_ok=True)
                    dt = getattr(env, "dt", 0.02)
                    output_video_path = self.video_dir / f"rollout_{rollout_id:03d}.mp4"
                    save_eval_video(
                        frames=frames,
                        dt=dt,
                        video_path=output_video_path,
                        reward_curve=rewards,
                        phase_labels=phase_labels if phase_labels else None,
                        success=success,
                    )
                    video_path = str(output_video_path)

                if self.save_rollout_logs:
                    summary = build_rollout_summary(
                        rollout_id=rollout_id,
                        success=success,
                        rewards=rewards,
                        step_records=step_records,
                        video_path=video_path,
                    )
                    if task.backend_type == "agx":
                        summary.update(success_summary)
                    jsonl_path = self.rollout_log_dir / f"rollout_{rollout_id:03d}.jsonl"
                    summary_path = self.rollout_log_dir / f"rollout_{rollout_id:03d}_summary.json"
                    write_jsonl(jsonl_path, step_records)
                    write_json(summary_path, summary)
                    summary["jsonl_path"] = str(jsonl_path)
                    summary["summary_path"] = str(summary_path)
                    rollout_summaries.append(summary)
        finally:
            if hasattr(env, "close"):
                env.close()

        if self.save_rollout_logs:
            manifest_dir = self.results_dir if self.results_dir is not None else self.rollout_log_dir.parent
            manifest_path = manifest_dir / "rollout_manifest.json"
            write_json(
                manifest_path,
                build_rollout_manifest(
                    task_name=task.name,
                    policy_name=policy_name,
                    ckpt_path=self.ckpt_path,
                    rollout_log_dir=self.rollout_log_dir,
                    rollouts=rollout_summaries,
                ),
            )

        extra_metrics = {"success_list": successes}
        if task.backend_type == "agx":
            extra_metrics.update(
                {
                    "success_mode": self._agx_success_mode,
                    "legacy_success_count": int(sum(legacy_successes)),
                    "legacy_success_rate": _safe_rate(sum(legacy_successes), len(legacy_successes)),
                    "final_hold_success_count": int(sum(final_hold_successes)),
                    "final_hold_success_rate": _safe_rate(sum(final_hold_successes), len(final_hold_successes)),
                    "strict_final_hold_success_count": int(sum(strict_successes)),
                    "strict_final_hold_success_rate": _safe_rate(sum(strict_successes), len(strict_successes)),
                    "dump_complete_final_hold_success_count": int(sum(dump_complete_successes)),
                    "dump_complete_final_hold_success_rate": _safe_rate(
                        sum(dump_complete_successes), len(dump_complete_successes)
                    ),
                    "strict_dump_complete_success_count": int(sum(strict_dump_complete_successes)),
                    "strict_dump_complete_success_rate": _safe_rate(
                        sum(strict_dump_complete_successes), len(strict_dump_complete_successes)
                    ),
                    "avg_final_success_signal": float(np.mean(final_signal_values)) if final_signal_values else 0.0,
                    "avg_max_success_signal": float(np.mean(max_signal_values)) if max_signal_values else 0.0,
                    "avg_final_bucket_mass": float(np.mean(final_bucket_values)) if final_bucket_values else 0.0,
                    "avg_ending_success_consecutive_steps": (
                        float(np.mean(ending_success_consecutive_steps))
                        if ending_success_consecutive_steps else 0.0
                    ),
                    "avg_ending_dump_complete_consecutive_steps": (
                        float(np.mean(ending_dump_complete_consecutive_steps))
                        if ending_dump_complete_consecutive_steps else 0.0
                    ),
                    "strict_max_failures": dict(self._strict_max_failures),
                    "residual_bucket_mass_thresh": float(self._residual_bucket_mass_thresh),
                }
            )

        metrics = EvalMetrics.from_rollouts(
            task_name       = task.name,
            policy_name     = policy_name,
            ckpt_path       = self.ckpt_path,
            episode_returns = episode_returns,
            highest_rewards = highest_rewards,
            env_max_reward  = task.env_max_reward,
            episode_lengths = episode_lengths,
            successes       = successes,
            extra           = extra_metrics,
        )
        print("\n" + metrics.summary())
        return metrics

    def _should_log_step_progress(self, step_index: int, episode_len: int) -> bool:
        if self.step_log_interval <= 0:
            return False
        return (step_index % self.step_log_interval == 0) or (step_index == episode_len)

    # ── Environment factory ───────────────────────────────────────────────────

    def _make_env(self, task: EvalTaskDef):
        if task.backend_type == "agx":
            from testbed.backends.agx.backend import AGXSimBackend
            reward_overrides = build_agx_excavation_mission_overrides(
                success_cfg={
                    "signal_name": self._success_signal_name,
                    "mass_thresh": self._mass_thresh,
                    "hold_steps": self._hold_steps,
                },
                reward_cfg=self._reward_overrides,
            )
            return AGXSimBackend(
                host=self.agx_host,
                port=self.agx_port,
                timeout=self.agx_timeout,
                task_name=task.name,
                reward_overrides=reward_overrides,
            )
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

    def _resolve_agx_success_index(self, env) -> int | None:
        if self._env_state_index is not None:
            return self._env_state_index
        if not hasattr(env, "get_info"):
            return None
        try:
            info = env.get_info()
            indices = resolve_agx_field_indices(info.env_state_order)
        except Exception:
            return None

        signal_name = self._success_signal_name
        if signal_name == "mass_in_bucket_kg":
            return indices.mass_in_bucket_idx
        if signal_name == "excavated_mass_kg":
            return indices.excavated_mass_idx
        if signal_name == "mass_in_target_box_kg":
            return indices.mass_in_target_box_idx
        if signal_name == "deposited_mass_in_target_box_kg":
            return indices.deposited_mass_in_target_box_idx
        if signal_name == "min_distance_to_target_m":
            return indices.min_distance_to_target_idx
        return None

    def _resolve_agx_bucket_mass_index(self, env) -> int | None:
        if not hasattr(env, "get_info"):
            return None
        try:
            info = env.get_info()
            indices = resolve_agx_field_indices(info.env_state_order)
        except Exception:
            return None
        return indices.mass_in_bucket_idx

    def _evaluate_agx_success(
        self,
        *,
        env,
        env_states: list[np.ndarray],
        success_flags: list[bool],
        step_records: list[dict[str, object]],
    ) -> dict[str, object]:
        mass_idx = self._resolve_agx_success_index(env)
        bucket_mass_idx = self._resolve_agx_bucket_mass_index(env)
        signal_series = _extract_signal_series(env_states, mass_idx)
        bucket_mass_series = _extract_signal_series(env_states, bucket_mass_idx)
        mass_summary = _mass_success_summary(
            signal_series=signal_series,
            mass_thresh=self._mass_thresh,
            hold_steps=self._hold_steps,
        )
        dump_complete_summary = _dump_complete_success_summary(
            signal_series=signal_series,
            bucket_mass_series=bucket_mass_series,
            mass_thresh=self._mass_thresh,
            residual_bucket_mass_thresh=self._residual_bucket_mass_thresh,
            hold_steps=self._hold_steps,
        )
        failure_counts = _count_rollout_failures(step_records)
        strict_blocking_failures = {
            name: failure_counts.get(name, 0)
            for name, limit in self._strict_max_failures.items()
            if failure_counts.get(name, 0) > limit
        }

        legacy_success = bool(any(success_flags) or mass_summary["ever_hold_success"])
        final_hold_success = bool(mass_summary["final_hold_success"])
        strict_final_hold_success = bool(final_hold_success and not strict_blocking_failures)
        dump_complete_final_hold_success = bool(dump_complete_summary["dump_complete_final_hold_success"])
        strict_dump_complete_success = bool(
            dump_complete_final_hold_success and not strict_blocking_failures
        )

        success_mode = self._agx_success_mode
        if success_mode == "legacy_any":
            primary_success = legacy_success
        elif success_mode == "final_hold":
            primary_success = final_hold_success
        elif success_mode == "strict_final_hold":
            primary_success = strict_final_hold_success
        elif success_mode == "dump_complete_final_hold":
            primary_success = dump_complete_final_hold_success
        elif success_mode == "strict_dump_complete":
            primary_success = strict_dump_complete_success
        else:
            raise ValueError(
                f"Unsupported AGX success mode {success_mode!r}. "
                "Expected one of: legacy_any, final_hold, strict_final_hold, "
                "dump_complete_final_hold, strict_dump_complete."
            )

        return {
            "success_mode": success_mode,
            "success": bool(primary_success),
            "legacy_success": legacy_success,
            "final_hold_success": final_hold_success,
            "strict_final_hold_success": strict_final_hold_success,
            "dump_complete_final_hold_success": dump_complete_final_hold_success,
            "strict_dump_complete_success": strict_dump_complete_success,
            "first_task_success_step": _first_true_index(success_flags),
            "first_hold_success_step": mass_summary["first_hold_success_step"],
            "first_dump_complete_step": dump_complete_summary["first_dump_complete_step"],
            "success_signal_name": self._success_signal_name,
            "success_mass_thresh": float(self._mass_thresh),
            "success_hold_steps": int(self._hold_steps),
            "final_signal_value": mass_summary["final_signal_value"],
            "max_signal_value": mass_summary["max_signal_value"],
            "ending_success_consecutive_steps": mass_summary["ending_consecutive_steps"],
            "final_bucket_mass": dump_complete_summary["final_bucket_mass"],
            "max_bucket_mass": dump_complete_summary["max_bucket_mass"],
            "residual_bucket_mass_thresh": float(self._residual_bucket_mass_thresh),
            "ending_dump_complete_consecutive_steps": dump_complete_summary["ending_consecutive_steps"],
            "strict_max_failures": dict(self._strict_max_failures),
            "strict_blocking_failures": strict_blocking_failures,
        }


# ─── AGX success rule (spec §8) ───────────────────────────────────────────────

def _mass_success(
    env_states: list[np.ndarray],
    mass_thresh: float,
    hold_steps: int,
    mass_idx: int = 0,
) -> bool:
    """
    Returns True if the selected env_state signal >= mass_thresh for
    hold_steps consecutive steps at any point in the episode.
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


def _extract_signal_series(env_states: list[np.ndarray], mass_idx: int | None) -> list[float]:
    if mass_idx is None:
        return []
    series: list[float] = []
    for env_state in env_states:
        if len(env_state) > mass_idx:
            series.append(float(env_state[mass_idx]))
    return series


def _mass_success_summary(
    *,
    signal_series: list[float],
    mass_thresh: float,
    hold_steps: int,
) -> dict[str, object]:
    if not signal_series or mass_thresh <= 0.0:
        return {
            "ever_hold_success": False,
            "final_hold_success": False,
            "first_hold_success_step": None,
            "final_signal_value": 0.0,
            "max_signal_value": 0.0,
            "ending_consecutive_steps": 0,
        }

    consecutive = 0
    first_hold_success_step: int | None = None
    for step_index, value in enumerate(signal_series):
        if value >= mass_thresh:
            consecutive += 1
            if consecutive >= hold_steps and first_hold_success_step is None:
                first_hold_success_step = step_index
        else:
            consecutive = 0

    ending_consecutive_steps = 0
    for value in reversed(signal_series):
        if value >= mass_thresh:
            ending_consecutive_steps += 1
        else:
            break

    return {
        "ever_hold_success": first_hold_success_step is not None,
        "final_hold_success": ending_consecutive_steps >= hold_steps,
        "first_hold_success_step": first_hold_success_step,
        "final_signal_value": float(signal_series[-1]),
        "max_signal_value": float(max(signal_series)),
        "ending_consecutive_steps": int(ending_consecutive_steps),
    }


def _dump_complete_success_summary(
    *,
    signal_series: list[float],
    bucket_mass_series: list[float],
    mass_thresh: float,
    residual_bucket_mass_thresh: float,
    hold_steps: int,
) -> dict[str, object]:
    if (
        not signal_series
        or not bucket_mass_series
        or len(signal_series) != len(bucket_mass_series)
        or mass_thresh <= 0.0
    ):
        return {
            "dump_complete_final_hold_success": False,
            "first_dump_complete_step": None,
            "final_bucket_mass": float(bucket_mass_series[-1]) if bucket_mass_series else 0.0,
            "max_bucket_mass": float(max(bucket_mass_series)) if bucket_mass_series else 0.0,
            "ending_consecutive_steps": 0,
        }

    consecutive = 0
    first_dump_complete_step: int | None = None
    for step_index, (signal_value, bucket_value) in enumerate(zip(signal_series, bucket_mass_series)):
        if signal_value >= mass_thresh and bucket_value <= residual_bucket_mass_thresh:
            consecutive += 1
            if consecutive >= hold_steps and first_dump_complete_step is None:
                first_dump_complete_step = step_index
        else:
            consecutive = 0

    ending_consecutive_steps = 0
    for signal_value, bucket_value in reversed(list(zip(signal_series, bucket_mass_series))):
        if signal_value >= mass_thresh and bucket_value <= residual_bucket_mass_thresh:
            ending_consecutive_steps += 1
        else:
            break

    return {
        "dump_complete_final_hold_success": ending_consecutive_steps >= hold_steps,
        "first_dump_complete_step": first_dump_complete_step,
        "final_bucket_mass": float(bucket_mass_series[-1]),
        "max_bucket_mass": float(max(bucket_mass_series)),
        "ending_consecutive_steps": int(ending_consecutive_steps),
    }


def _count_rollout_failures(step_records: list[dict[str, object]]) -> dict[str, int]:
    failure_counts: dict[str, int] = {}
    for record in step_records:
        for failure_name in record.get("task_step_failures", []):
            failure_key = str(failure_name)
            failure_counts[failure_key] = failure_counts.get(failure_key, 0) + 1
    return failure_counts


def _first_true_index(flags: list[bool]) -> int | None:
    for index, flag in enumerate(flags):
        if flag:
            return index
    return None


def _safe_rate(numerator: int | float, denominator: int) -> float:
    return float(numerator) / float(denominator) if denominator > 0 else 0.0
