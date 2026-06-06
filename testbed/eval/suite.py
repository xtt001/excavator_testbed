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

from dataclasses import replace
import json
from pathlib import Path
import time
from typing import Any

import numpy as np

from testbed.eval.rollout_logs import (
    build_rollout_manifest,
    to_jsonable,
    write_json,
)
from testbed.eval.hybrid_metrics import (
    aggregate_hybrid_metrics,
)
from testbed.eval.planner_metrics import aggregate_planner_metrics
from testbed.eval.quality_metrics import aggregate_quality_metrics
from testbed.eval.metrics import EvalMetrics
from testbed.eval.multi_cycle_metrics import (
    aggregate_multicycle_metrics,
)
from testbed.eval.tasks import EVAL_SEED, EvalTaskDef, get_eval_task
from testbed.eval.video import save_eval_video
from testbed.eval.rollout_hdf5 import (
    build_rollout_v2_payload,
    enrich_rollout_hdf5_in_place,
)
from testbed.eval.rollout_artifacts import (
    build_rollout_metric_summaries,
    write_rollout_log_artifacts,
)
from testbed.eval.rollout_step_records import (
    build_planner_debug_json,
    build_policy_input,
    build_rollout_step_record,
)
from testbed.policies.base import Policy
from testbed.tasks.logic.excavator_reward import (
    build_agx_excavation_mission_overrides,
    resolve_agx_field_indices,
)
from testbed.data.v2_1 import build_goal_tokens
from testbed.planner.boundary_detector import build_boundary_detector_from_config
from testbed.planner.goal_sequence import (
    GOAL_SECTOR_NAME_TO_ID,
    normalize_goal_sequence as normalize_goal_sequence_values,
)

DEFAULT_PAUSE_EPS = 0.05
LIVE_GOAL_SECTOR_IDS = GOAL_SECTOR_NAME_TO_ID


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
    stream_rollout_logs If True, append rollout_XXX.partial.jsonl during the
                      rollout so interrupted runs still leave timestep evidence.
    record_hdf5   If True, write each policy rollout as a trainable HDF5 episode.
    record_hdf5_dir Directory for policy-rollout HDF5 episodes.
    send_planner_debug_to_backend
                  If True, forward planner debug JSON to AGX/Unity.  Disable
                  this for visual-policy eval when debug markers must not enter
                  ACT camera observations.
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
    target_cycle_gate  Optional multicycle early-stop gate; when set, the
                      rollout stops once the external boundary detector has
                      observed this many completed dump events.
    target_cycle_gate_terminal_hold_steps  Optional tail length after the
                      target-cycle gate first fires. This prevents the gate
                      from truncating dump-complete final-hold accounting.
    episode_len     Optional per-run rollout horizon override.
    camera_names    Optional per-run camera override for video/eval inputs.
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
        stream_rollout_logs: bool = False,
        rollout_log_dir: str | Path | None = None,
        record_hdf5: bool = False,
        record_hdf5_dir: str | Path | None = None,
        record_hdf5_metadata: dict[str, object] | None = None,
        record_hdf5_with_cell_entry: bool = True,
        send_planner_debug_to_backend: bool = True,
        step_log_interval: int = 50,
        agx_host: str = "127.0.0.1",
        agx_port: int = 5057,
        agx_timeout: float = 10.0,
        scenario_id: str | None = None,
        mass_thresh: float | None = None,
        hold_steps: int | None = None,
        success_signal_name: str | None = None,
        env_state_index: int | None = None,
        reward_overrides: dict[str, float] | None = None,
        agx_success_mode: str = "legacy_any",
        strict_max_failures: dict[str, int] | None = None,
        residual_bucket_mass_thresh: float = 100.0,
        target_cycle_gate: int | None = None,
        target_cycle_gate_terminal_hold_steps: int | None = None,
        live_goal_sequence: list[str] | tuple[str, ...] | list[int] | tuple[int, ...] | None = None,
        live_goal_depth_norm: float = 1.0,
        live_goal_dump_target_norm: float = 1.0,
        episode_len: int | None = None,
        camera_names: list[str] | None = None,
    ):
        self.policy       = policy
        self.task_def     = get_eval_task(task_name)
        if episode_len is not None:
            self.task_def = replace(self.task_def, episode_len=int(episode_len))
        if camera_names is not None:
            self.task_def = replace(self.task_def, camera_names=list(camera_names))
        self.num_rollouts = num_rollouts
        self.save_video   = save_video
        self.ckpt_path    = ckpt_path
        self.save_rollout_logs = bool(save_rollout_logs)
        self.stream_rollout_logs = bool(stream_rollout_logs)
        self.record_hdf5 = bool(record_hdf5)
        self.record_hdf5_dir = None if record_hdf5_dir is None else Path(record_hdf5_dir)
        self.record_hdf5_metadata = dict(record_hdf5_metadata or {})
        self.record_hdf5_with_cell_entry = bool(record_hdf5_with_cell_entry)
        self.send_planner_debug_to_backend = bool(send_planner_debug_to_backend)
        self.step_log_interval = max(0, int(step_log_interval))
        self.agx_host     = agx_host
        self.agx_port     = agx_port
        self.agx_timeout  = agx_timeout
        self._scenario_id = None if scenario_id in (None, "") else str(scenario_id)
        self._env_state_index = None if env_state_index is None else int(env_state_index)
        self._live_goal_tokens = None
        if self._scenario_id is not None:
            self._live_goal_tokens = build_goal_tokens(self._scenario_id)
        self._live_goal_sequence = self._normalize_live_goal_sequence(live_goal_sequence)
        self._live_goal_depth_norm = float(live_goal_depth_norm)
        self._live_goal_dump_target_norm = float(live_goal_dump_target_norm)

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
        self._target_cycle_gate = (
            None if target_cycle_gate is None else max(1, int(target_cycle_gate))
        )
        self._target_cycle_gate_terminal_hold_steps = (
            max(0, int(self._hold_steps))
            if target_cycle_gate_terminal_hold_steps is None
            else max(0, int(target_cycle_gate_terminal_hold_steps))
        )

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
        if self.record_hdf5 and self.record_hdf5_dir is None:
            self.record_hdf5_dir = (
                (self.results_dir if self.results_dir is not None else self.rollout_log_dir.parent)
                / "hdf5_rollouts"
            )

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
        target_cycle_gate_successes: list[bool] = []
        target_cycle_completed_counts: list[int] = []
        final_signal_values: list[float] = []
        max_signal_values: list[float] = []
        final_bucket_values: list[float] = []
        ending_success_consecutive_steps: list[int] = []
        ending_dump_complete_consecutive_steps: list[int] = []
        rollout_summaries: list[dict[str, object]] = []
        continuity_summaries: list[dict[str, float]] = []
        multicycle_summaries: list[dict[str, float | int]] = []
        hybrid_summaries: list[dict[str, float | int | str]] = []
        planner_summaries: list[dict[str, object]] = []
        quality_summaries: list[dict[str, float | int]] = []
        policy_name = type(self.policy).__name__
        hdf5_paths: list[str] = []
        if self.record_hdf5 and self.record_hdf5_dir is not None:
            self.record_hdf5_dir.mkdir(parents=True, exist_ok=True)

        try:
            for rollout_id in range(self.num_rollouts):
                np.random.seed(EVAL_SEED + rollout_id)

                # MuJoCo: set deterministic object pose per rollout
                if task.backend_type != "agx" and task.make_object_pose is not None:
                    env.set_initial_object_pose(task.make_object_pose())

                ts = env.reset(seed=EVAL_SEED + rollout_id)
                self.policy.reset()
                rollout_recorder = None
                if self.record_hdf5:
                    from testbed.data.recorder import EpisodeRecorder

                    rollout_recorder = EpisodeRecorder(
                        output_dir=self.record_hdf5_dir,
                        episode_idx=rollout_id,
                        metadata=self._build_rollout_hdf5_metadata(
                            env=env,
                            rollout_id=rollout_id,
                            task=task,
                            policy_name=policy_name,
                        ),
                        camera_names=list(task.camera_names),
                    )

                rewards:      list[float]      = []
                frames:       list[np.ndarray] = []
                env_states:   list[np.ndarray] = []
                phase_labels: list[str]        = []
                success_flags: list[bool]      = []
                step_records: list[dict[str, object]] = []
                stream_path = None
                rollout_stop_reason = "episode_len_reached"
                target_cycle_gate_reached_step: int | None = None
                boundary_detector = build_boundary_detector_from_config(
                    reward_cfg=self._reward_overrides,
                    success_cfg={
                        "residual_bucket_mass_thresh": self._residual_bucket_mass_thresh,
                    },
                    pause_action_eps=DEFAULT_PAUSE_EPS,
                )
                live_goal_cycle_id = -1

                if self.save_rollout_logs and self.stream_rollout_logs:
                    self.rollout_log_dir.mkdir(parents=True, exist_ok=True)
                    stream_path = (
                        self.rollout_log_dir
                        / f"rollout_{rollout_id:03d}.partial.jsonl"
                    )
                    stream_path.write_text("")

                for t in range(task.episode_len):
                    obs = ts.observation

                    policy_input = build_policy_input(
                        obs=obs,
                        camera_names=task.camera_names,
                        goal_tokens=self._live_goal_tokens_for_cycle(
                            live_goal_cycle_id
                        ),
                    )

                    action = self.policy.predict(policy_input)
                    policy_debug = (
                        dict(self.policy.debug_state())
                        if hasattr(self.policy, "debug_state")
                        else {}
                    )
                    planner_debug_json = None
                    if self.send_planner_debug_to_backend:
                        planner_debug_json = self._planner_debug_json(
                            policy_debug,
                            obs=obs,
                        )
                    ts = self._env_step_with_optional_planner_debug(
                        env=env,
                        task=task,
                        action=action,
                        planner_debug_json=planner_debug_json,
                    )
                    post_obs = ts.observation
                    boundary_event = boundary_detector.update(
                        env_state=post_obs.get("env_state", np.zeros(9, dtype=np.float32)),
                        action=action,
                        qpos=post_obs.get("qpos", np.zeros(4, dtype=np.float32)),
                        reward_phase=str(
                            ts.info.get("reward_phase", post_obs.get("reward_phase", ""))
                        ),
                        task_step_successes=list(
                            ts.info.get(
                                "task_step_successes",
                                post_obs.get("task_step_successes", []),
                            )
                        ),
                        task_metrics=dict(
                            ts.info.get("task_metrics", post_obs.get("task_metrics", {}))
                        ),
                    )
                    live_goal_cycle_id = int(boundary_event.cycle_id)

                    r = float(ts.reward) if ts.reward is not None else 0.0
                    rewards.append(r)
                    reward_phase = str(ts.info.get("reward_phase", post_obs.get("reward_phase", "")))
                    task_success = bool(ts.info.get("task_success", post_obs.get("task_success", False)))
                    task_step_successes = list(
                        ts.info.get("task_step_successes", post_obs.get("task_step_successes", []))
                    )
                    task_step_failures = list(
                        ts.info.get("task_step_failures", post_obs.get("task_step_failures", []))
                    )
                    task_metrics = dict(
                        ts.info.get("task_metrics", post_obs.get("task_metrics", {}))
                    )
                    warnings = list(ts.info.get("warnings", post_obs.get("warnings", [])))
                    if rollout_recorder is not None:
                        rollout_recorder.record(
                            obs=post_obs,
                            action=np.asarray(action, dtype=np.float32),
                            reward=r,
                            step_id=int(post_obs.get("step_id", t)),
                            step_ns=time.time_ns(),
                            action_src_type="policy",
                            action_src_id=self._policy_action_source_id(
                                policy_name=policy_name,
                                policy_debug=policy_debug,
                            ),
                        )
                    step_record = build_rollout_step_record(
                        rollout_id=rollout_id,
                        step_index=t,
                        post_obs=post_obs,
                        action=action,
                        policy_input=policy_input,
                        policy_debug=policy_debug,
                        boundary_event=boundary_event,
                        reward=r,
                        reward_phase=reward_phase,
                        task_success=task_success,
                        task_step_successes=task_step_successes,
                        task_step_failures=task_step_failures,
                        task_metrics=task_metrics,
                        warnings=warnings,
                        sim_time_ns=ts.info.get("sim_time_ns", 0),
                    )
                    step_records.append(step_record)
                    if stream_path is not None:
                        with open(stream_path, "a") as f:
                            f.write(
                                json.dumps(
                                    to_jsonable(step_records[-1]),
                                    separators=(",", ":"),
                                )
                            )
                            f.write("\n")

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

                    if bool(policy_debug.get("transition_timeout", False)):
                        rollout_stop_reason = "transition_timeout"
                        break
                    if bool(
                        policy_debug.get("planner_terminal_stop_requested", False)
                    ):
                        rollout_stop_reason = str(
                            policy_debug.get(
                                "planner_terminal_stop_reason",
                                "planner_terminal_stop",
                            )
                        )
                        break
                    (
                        target_cycle_gate_reached_step,
                        target_gate_stop_reason,
                    ) = self._target_cycle_gate_stop_reason(
                        completed_dump_count=boundary_detector.completed_dump_count,
                        step_index=t,
                        gate_reached_step=target_cycle_gate_reached_step,
                    )
                    if target_gate_stop_reason is not None:
                        rollout_stop_reason = target_gate_stop_reason
                        break

                # ── Success detection ─────────────────────────────────────────
                success_summary: dict[str, Any] | None = None
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
                hdf5_path = ""
                cell_entry_summary: dict[str, Any] = {}
                if rollout_recorder is not None and len(rollout_recorder) > 0:
                    v2_payload = build_rollout_v2_payload(step_records)
                    saved_hdf5 = rollout_recorder.save(success=success, v2=v2_payload)
                    hdf5_path = str(saved_hdf5)
                    hdf5_paths.append(hdf5_path)
                    if self.record_hdf5_with_cell_entry:
                        cell_entry_summary = enrich_rollout_hdf5_in_place(saved_hdf5)

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

                continuity_summary = _build_continuity_summary(
                    step_records=step_records,
                    success_summary=success_summary,
                )
                metric_summaries = build_rollout_metric_summaries(
                    step_records=step_records,
                    policy=self.policy,
                    success_summary=success_summary,
                )
                target_gate_summary: dict[str, Any] = {}
                if task.backend_type == "agx":
                    target_gate_summary = self._target_cycle_gate_summary(
                        hybrid_summary=metric_summaries.hybrid_summary,
                        multicycle_summary=metric_summaries.multicycle_summary,
                        rollout_stop_reason=rollout_stop_reason,
                    )
                    if target_gate_summary:
                        target_cycle_gate_successes.append(
                            bool(target_gate_summary["target_cycle_gate_success"])
                        )
                        target_cycle_completed_counts.append(
                            int(target_gate_summary["target_cycle_completed_dump_count"])
                        )

                if self.save_rollout_logs:
                    planner_trace = (
                        dict(self.policy.planner_trace())
                        if hasattr(self.policy, "planner_trace")
                        else {}
                    )
                    summary = write_rollout_log_artifacts(
                        rollout_log_dir=self.rollout_log_dir,
                        rollout_id=rollout_id,
                        success=success,
                        rewards=rewards,
                        step_records=step_records,
                        video_path=video_path,
                        hdf5_path=hdf5_path,
                        cell_entry_summary=cell_entry_summary,
                        success_summary=success_summary,
                        continuity_summary=continuity_summary,
                        metric_summaries=metric_summaries,
                        target_gate_summary=target_gate_summary,
                        planner_trace=planner_trace,
                        rollout_stop_reason=rollout_stop_reason,
                    )
                    rollout_summaries.append(summary)
                    planner_summaries.append(summary)
                else:
                    planner_summaries.append(metric_summaries.hybrid_summary)
                continuity_summaries.append(continuity_summary)
                multicycle_summaries.append(metric_summaries.multicycle_summary)
                hybrid_summaries.append(metric_summaries.hybrid_summary)
                quality_summaries.append(metric_summaries.quality_summary)
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
        if hdf5_paths:
            extra_metrics["hdf5_paths"] = list(hdf5_paths)
        if task.backend_type == "agx":
            extra_metrics.update(
                {
                    "scenario_id": "" if self._scenario_id is None else self._scenario_id,
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
                    "target_cycle_gate": (
                        0 if self._target_cycle_gate is None else int(self._target_cycle_gate)
                    ),
                    "target_cycle_gate_terminal_hold_steps": int(
                        self._target_cycle_gate_terminal_hold_steps
                    ),
                    "target_cycle_gate_success_count": int(
                        sum(target_cycle_gate_successes)
                    ),
                    "target_cycle_gate_success_rate": _safe_rate(
                        sum(target_cycle_gate_successes),
                        len(target_cycle_gate_successes),
                    ),
                    "target_cycle_completed_dump_mean": (
                        float(np.mean(target_cycle_completed_counts))
                        if target_cycle_completed_counts
                        else 0.0
                    ),
                }
            )
        extra_metrics.update(_aggregate_continuity_metrics(continuity_summaries))
        extra_metrics.update(aggregate_multicycle_metrics(multicycle_summaries))
        extra_metrics.update(aggregate_hybrid_metrics(hybrid_summaries))
        extra_metrics.update(aggregate_planner_metrics(planner_summaries))
        extra_metrics.update(aggregate_quality_metrics(quality_summaries))

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

    def _target_cycle_gate_summary(
        self,
        *,
        hybrid_summary: dict[str, Any],
        multicycle_summary: dict[str, Any],
        rollout_stop_reason: str,
    ) -> dict[str, int | str]:
        if self._target_cycle_gate is None:
            return {}
        gate = int(self._target_cycle_gate)
        completed_raw = hybrid_summary.get(
            "coverage_completed_dump_count",
            multicycle_summary.get("completed_dump_count", 0),
        )
        completed = int(completed_raw or 0)
        stop_reason = str(rollout_stop_reason)
        gate_stop = bool(stop_reason.startswith("target_cycle_gate"))
        if gate_stop:
            completed = max(completed, gate)
        gate_success = int(gate_stop or completed >= gate)
        return {
            "target_cycle_gate": gate,
            "target_cycle_completed_dump_count": completed,
            "target_cycle_gate_success": gate_success,
            "target_cycle_gate_stop_reason": (
                stop_reason if gate_stop else ""
            ),
        }

    def _build_rollout_hdf5_metadata(
        self,
        *,
        env,
        rollout_id: int,
        task: EvalTaskDef,
        policy_name: str,
    ) -> dict[str, object]:
        from testbed.data.schema import (
            ATTR_ACTION_ORDER,
            ATTR_ACTION_SEMANTICS,
            ATTR_CAMERA_FPS,
            ATTR_CAMERA_HEIGHT,
            ATTR_CAMERA_NAMES,
            ATTR_CAMERA_ROW_ORDER,
            ATTR_CAMERA_WIDTH,
            ATTR_CONTROL_HZ,
            ATTR_DIG_AREA_PRESET_ID,
            ATTR_DT,
            ATTR_DUMP_AREA_PRESET_ID,
            ATTR_ENV_STATE_CONTRACT_VERSION,
            ATTR_ENV_STATE_ORDER,
            ATTR_IMAGE_FORMAT,
            ATTR_OBSERVER_NOTES,
            ATTR_OPERATOR_NOTES,
            ATTR_PARAM_VERSION,
            ATTR_PROTOCOL_VERSION,
            ATTR_QPOS_ORDER,
            ATTR_QVEL_ORDER,
            ATTR_RECORDING_MODE,
            ATTR_RECORDING_PROTOCOL_VERSION,
            ATTR_SCENE_VERSION,
            ATTR_SCENARIO_ID,
            ATTR_SEED,
            ATTR_SIM_BACKEND,
            ATTR_SOIL_PRESET_ID,
            ATTR_TARGET_DEPTH_M,
            ATTR_TASK_GOAL_DESCRIPTION,
            ATTR_TASK_NAME,
            ATTR_WARMUP_OR_TRAIN,
        )

        info = env.get_info() if hasattr(env, "get_info") else None
        camera_names = list(task.camera_names)
        camera_by_name = {
            camera.name: camera
            for camera in (getattr(info, "cameras", ()) if info is not None else ())
        }
        metadata: dict[str, object] = {
            ATTR_TASK_NAME: task.name,
            ATTR_SIM_BACKEND: "agxunity" if task.backend_type == "agx" else task.backend_type,
            ATTR_SEED: int(EVAL_SEED + rollout_id),
            ATTR_PARAM_VERSION: "v2.2_policy_rollout",
            ATTR_RECORDING_MODE: "policy_rollout",
            ATTR_RECORDING_PROTOCOL_VERSION: "v2.2_policy_rollout_hdf5",
            ATTR_ENV_STATE_CONTRACT_VERSION: "agx_env_state_v2_2_64",
            ATTR_CAMERA_NAMES: ",".join(camera_names),
            ATTR_IMAGE_FORMAT: "raw_rgb",
            ATTR_SCENE_VERSION: "unknown",
            ATTR_SOIL_PRESET_ID: "unknown",
            ATTR_DIG_AREA_PRESET_ID: "default_3x2",
            ATTR_DUMP_AREA_PRESET_ID: "active_dump_area",
            ATTR_TASK_GOAL_DESCRIPTION: "Yulong fixed-station 3-cycle dig/dump policy rollout",
            ATTR_TARGET_DEPTH_M: 0.08,
            ATTR_WARMUP_OR_TRAIN: "train",
            ATTR_OPERATOR_NOTES: "",
            ATTR_OBSERVER_NOTES: "",
            "policy_name": str(policy_name),
            "checkpoint_path": str(self.ckpt_path),
        }
        if self._scenario_id is not None:
            metadata[ATTR_SCENARIO_ID] = str(self._scenario_id)
        if info is not None:
            metadata.update(
                {
                    ATTR_CONTROL_HZ: int(round(float(info.control_hz))),
                    ATTR_DT: float(info.dt),
                    ATTR_ACTION_SEMANTICS: str(info.action_semantics),
                    ATTR_PROTOCOL_VERSION: str(info.protocol_version),
                    ATTR_ACTION_ORDER: ",".join(info.action_order),
                    ATTR_QPOS_ORDER: ",".join(info.qpos_order),
                    ATTR_QVEL_ORDER: ",".join(info.qvel_order),
                    ATTR_ENV_STATE_ORDER: ",".join(info.env_state_order),
                }
            )
        if len(camera_names) == 1 and camera_names[0] in camera_by_name:
            camera = camera_by_name[camera_names[0]]
            metadata[ATTR_CAMERA_WIDTH] = int(camera.width)
            metadata[ATTR_CAMERA_HEIGHT] = int(camera.height)
            metadata[ATTR_CAMERA_FPS] = float(camera.fps)
            metadata[ATTR_CAMERA_ROW_ORDER] = str(camera.row_order)

        metadata.update(self.record_hdf5_metadata)
        return {str(key): _metadata_attr_value(value) for key, value in metadata.items()}

    def _policy_action_source_id(
        self,
        *,
        policy_name: str,
        policy_debug: dict[str, object],
    ) -> str:
        primitive_checkpoint = str(policy_debug.get("primitive_checkpoint_path", ""))
        if primitive_checkpoint:
            return f"policy:{policy_name}:{primitive_checkpoint}"
        if self.ckpt_path:
            return f"policy:{policy_name}:{self.ckpt_path}"
        return f"policy:{policy_name}"

    @staticmethod
    def _env_step_with_optional_planner_debug(
        *,
        env,
        task: EvalTaskDef,
        action: np.ndarray,
        planner_debug_json: str | None,
    ):
        if task.backend_type == "agx" and planner_debug_json is not None:
            return env.step(action, planner_debug_json=planner_debug_json)
        return env.step(action)

    @staticmethod
    def _planner_debug_json(
        policy_debug: dict[str, object],
        *,
        obs: dict[str, object] | None = None,
    ) -> str | None:
        return build_planner_debug_json(policy_debug, obs=obs)

    def _should_log_step_progress(self, step_index: int, episode_len: int) -> bool:
        if self.step_log_interval <= 0:
            return False
        return (step_index % self.step_log_interval == 0) or (step_index == episode_len)

    def _target_cycle_gate_stop_reason(
        self,
        *,
        completed_dump_count: int,
        step_index: int,
        gate_reached_step: int | None,
    ) -> tuple[int | None, str | None]:
        if self._target_cycle_gate is None:
            return gate_reached_step, None
        if int(completed_dump_count) < int(self._target_cycle_gate):
            return gate_reached_step, None

        if gate_reached_step is None:
            gate_reached_step = int(step_index)
        if self._target_cycle_gate_terminal_hold_steps <= 0:
            return gate_reached_step, "target_cycle_gate_reached"

        held_steps = int(step_index) - int(gate_reached_step) + 1
        if held_steps >= self._target_cycle_gate_terminal_hold_steps:
            return gate_reached_step, "target_cycle_gate_terminal_hold_reached"
        return gate_reached_step, None

    def _live_goal_tokens_for_cycle(self, cycle_index: int) -> np.ndarray | None:
        if self._scenario_id is None:
            return None
        if int(cycle_index) < 0:
            return None if self._live_goal_tokens is None else self._live_goal_tokens.copy()
        if not self._live_goal_sequence:
            return None if self._live_goal_tokens is None else self._live_goal_tokens.copy()
        index = max(0, min(int(cycle_index), len(self._live_goal_sequence) - 1))
        curr_sector_id = int(self._live_goal_sequence[index])
        next_index = index + 1
        next_sector_id = (
            int(self._live_goal_sequence[next_index])
            if next_index < len(self._live_goal_sequence)
            else -1
        )
        return build_goal_tokens(
            self._scenario_id,
            curr_sector_id=curr_sector_id,
            curr_cut_depth_norm=self._live_goal_depth_norm,
            next_sector_id=next_sector_id,
            next_cut_depth_norm=self._live_goal_depth_norm,
            dst_target_norm=self._live_goal_dump_target_norm,
            has_lookahead=next_sector_id >= 0,
        )

    @staticmethod
    def _normalize_live_goal_sequence(
        goal_sequence: list[str] | tuple[str, ...] | list[int] | tuple[int, ...] | None,
    ) -> tuple[int, ...]:
        return normalize_goal_sequence_values(
            goal_sequence,
            unknown_message_prefix="Unknown live goal sector",
            id_message_prefix="Live goal sector id",
        )

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
                scenario_id=self._scenario_id,
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


def _metadata_attr_value(value: object) -> object:
    if isinstance(value, (str, bytes, int, float, bool, np.integer, np.floating, np.bool_)):
        return value
    if value is None:
        return ""
    if isinstance(value, Path):
        return str(value)
    try:
        return json.dumps(to_jsonable(value), sort_keys=True)
    except TypeError:
        return str(value)


def _safe_rate(numerator: int | float, denominator: int) -> float:
    return float(numerator) / float(denominator) if denominator > 0 else 0.0


def _build_continuity_summary(
    *,
    step_records: list[dict[str, object]],
    success_summary: dict[str, object] | None,
) -> dict[str, float | int | str | None]:
    if not step_records:
        return {
            "pause_ratio": 0.0,
            "mean_action_jerk": 0.0,
            "boundary_jump_l1": 0.0,
            "boundary_jump_l2": 0.0,
            "boundary_source": "none",
            "boundary_step_count": 0,
        }

    actions = np.asarray(
        [np.asarray(record.get("action", []), dtype=np.float32).reshape(-1) for record in step_records],
        dtype=np.float32,
    )
    pause_mask = np.asarray(
        [
            bool(record.get("pause_mask", np.sum(np.abs(action)) < DEFAULT_PAUSE_EPS))
            for record, action in zip(step_records, actions, strict=False)
        ],
        dtype=bool,
    )

    boundary_mask = np.asarray(
        [bool(record.get("boundary_mask", 0)) for record in step_records],
        dtype=bool,
    )
    boundary_source = "step_record_mask" if np.any(boundary_mask) else "none"
    if not np.any(boundary_mask):
        first_dump_complete_step = (
            None
            if success_summary is None
            else success_summary.get("first_dump_complete_step")
        )
        if first_dump_complete_step is not None:
            boundary_mask[max(0, int(first_dump_complete_step) - 1) : min(len(boundary_mask), int(first_dump_complete_step) + 2)] = True
            boundary_source = "dump_complete_window"

    action_delta = np.diff(actions, axis=0) if len(actions) >= 2 else np.zeros((0, 0), dtype=np.float32)
    if len(actions) >= 3:
        action_jerk = actions[2:] - (2.0 * actions[1:-1]) + actions[:-2]
        mean_action_jerk = float(np.linalg.norm(action_jerk, ord=2, axis=1).mean())
    else:
        mean_action_jerk = 0.0

    boundary_indices = np.flatnonzero(boundary_mask)
    boundary_indices = boundary_indices[boundary_indices > 0]
    if len(boundary_indices) > 0 and len(action_delta) > 0:
        boundary_delta = action_delta[boundary_indices - 1]
        boundary_jump_l1 = float(np.linalg.norm(boundary_delta, ord=1, axis=1).mean())
        boundary_jump_l2 = float(np.linalg.norm(boundary_delta, ord=2, axis=1).mean())
    else:
        boundary_jump_l1 = 0.0
        boundary_jump_l2 = 0.0

    return {
        "pause_ratio": float(pause_mask.mean()) if len(pause_mask) > 0 else 0.0,
        "mean_action_jerk": mean_action_jerk,
        "boundary_jump_l1": boundary_jump_l1,
        "boundary_jump_l2": boundary_jump_l2,
        "boundary_source": boundary_source,
        "boundary_step_count": int(len(boundary_indices)),
    }


def _aggregate_continuity_metrics(
    continuity_summaries: list[dict[str, float | int | str | None]],
) -> dict[str, float]:
    if not continuity_summaries:
        return {
            "avg_pause_ratio": 0.0,
            "avg_mean_action_jerk": 0.0,
            "avg_boundary_jump_l1": 0.0,
            "avg_boundary_jump_l2": 0.0,
        }
    pause_ratio = [float(item.get("pause_ratio", 0.0)) for item in continuity_summaries]
    mean_action_jerk = [float(item.get("mean_action_jerk", 0.0)) for item in continuity_summaries]
    boundary_jump_l1 = [float(item.get("boundary_jump_l1", 0.0)) for item in continuity_summaries]
    boundary_jump_l2 = [float(item.get("boundary_jump_l2", 0.0)) for item in continuity_summaries]
    return {
        "avg_pause_ratio": float(np.mean(pause_ratio)),
        "avg_mean_action_jerk": float(np.mean(mean_action_jerk)),
        "avg_boundary_jump_l1": float(np.mean(boundary_jump_l1)),
        "avg_boundary_jump_l2": float(np.mean(boundary_jump_l2)),
    }
