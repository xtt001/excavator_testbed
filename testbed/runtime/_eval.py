"""Internal eval helper called by Runner.eval()."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from testbed.data.v2_1 import GOAL_TOKEN_DIM


def eval_policy(config: dict[str, Any]) -> None:
    agx_cfg    = config.get("agx", {})
    success_cfg = config.get("success", {})
    reward_cfg = config.get("reward", {})
    task_cfg   = config.get("task", {})
    policy_cfg = config.get("policy", {})
    eval_cfg   = config.get("eval", {})
    low_dim_keys = list(policy_cfg.get("low_dim_keys", ["qpos"]))

    policy_class = str(policy_cfg.get("class", policy_cfg.get("name", "ACT"))).upper()
    task_name = task_cfg.get("name", task_cfg.get("task_name", config.get("task_name", "")))
    from testbed.eval.tasks import get_eval_task

    task_def = get_eval_task(task_name)
    equipment_model = task_cfg.get(
        "equipment_model",
        config.get("equipment_model", task_def.equipment_model),
    )
    scenario_id = task_cfg.get("scenario_id")
    camera_names    = task_cfg.get("camera_names", config.get("camera_names", task_def.camera_names))
    max_episode_len = int(
        task_cfg.get("episode_len", config.get("episode_len", task_def.episode_len))
    )
    num_rollouts    = int(
        eval_cfg.get(
            "num_rollouts",
            config.get("rollout", {}).get("num_rollouts_default", 50),
        )
    )
    save_video      = bool(eval_cfg.get("save_video", True))
    temporal_agg    = bool(eval_cfg.get("temporal_agg", policy_cfg.get("temporal_agg", False)))
    device          = str(policy_cfg.get("device", eval_cfg.get("device", "cuda")))
    if policy_class == "HYBRID_PLANNER_ACT":
        ckpt_path_value = (
            eval_cfg.get("work_ckpt_path")
            or policy_cfg.get("work_ckpt_path")
            or eval_cfg.get("ckpt_path")
            or policy_cfg.get("ckpt_path")
        )
        explicit_ckpt_dir = (
            eval_cfg.get("work_ckpt_dir")
            or policy_cfg.get("work_ckpt_dir")
            or eval_cfg.get("ckpt_dir")
            or config.get("train", {}).get("ckpt_dir")
        )
    else:
        ckpt_path_value = eval_cfg.get("ckpt_path") or policy_cfg.get("ckpt_path")
        explicit_ckpt_dir = eval_cfg.get("ckpt_dir", config.get("train", {}).get("ckpt_dir"))
    ckpt_path, ckpt_dir = _resolve_checkpoint_paths(
        ckpt_path_value=ckpt_path_value,
        explicit_ckpt_dir=explicit_ckpt_dir,
    )
    video_dir       = Path(eval_cfg.get("video_dir", ckpt_dir / "eval_videos"))
    results_dir     = Path(eval_cfg.get("results_dir", ckpt_dir / "eval_results"))
    save_rollout_logs = bool(eval_cfg.get("save_rollout_logs", True))
    rollout_log_dir = Path(eval_cfg.get("rollout_log_dir", results_dir / "rollouts"))
    step_log_interval = int(eval_cfg.get("step_log_interval", 50))
    agx_host        = str(agx_cfg.get("host", "127.0.0.1"))
    agx_port        = int(agx_cfg.get("port", 5057))
    agx_timeout     = float(agx_cfg.get("timeout", 10.0))
    mass_thresh     = success_cfg.get("mass_thresh", success_cfg.get("mass_thresh_kg"))
    hold_steps      = success_cfg.get("hold_steps")
    success_signal_name = success_cfg.get(
        "signal_name",
        success_cfg.get("success_signal_name"),
    )
    agx_success_mode = str(success_cfg.get("mode", "legacy_any"))
    strict_max_failures = dict(success_cfg.get("strict_max_failures", {}))
    residual_bucket_mass_thresh = float(
        success_cfg.get(
            "residual_bucket_mass_thresh",
            success_cfg.get("bucket_residual_mass_thresh", 100.0),
        )
    )
    env_state_index_value = success_cfg.get(
        "env_state_idx",
        success_cfg.get("env_state_index"),
    )
    env_state_index = None if env_state_index_value is None else int(env_state_index_value)

    if "goal_tokens" in low_dim_keys and not scenario_id:
        raise ValueError(
            "policy.low_dim_keys includes 'goal_tokens' for live eval, "
            "but task.scenario_id is missing."
        )

    if policy_class == "ACT":
        policy = _build_act_eval_policy(
            config=config,
            ckpt_path=ckpt_path,
            ckpt_dir=ckpt_dir,
            camera_names=camera_names,
            equipment_model=equipment_model,
            max_episode_len=max_episode_len,
            low_dim_keys=low_dim_keys,
            temporal_agg=temporal_agg,
            device=device,
            act_params=policy_cfg.get("act_params", {}),
        )

    elif policy_class == "DUMMY":
        action_dim = int(policy_cfg.get("action_dim", 4))
        from testbed.policies.dummy.adapter import DummyPolicy
        policy = DummyPolicy(action_dim=action_dim, mode=policy_cfg.get("mode", "zero"))

    elif policy_class == "HYBRID_PLANNER_ACT":
        work_low_dim_keys = list(policy_cfg.get("work_low_dim_keys", ["qpos"]))
        if "goal_tokens" in work_low_dim_keys and not scenario_id:
            raise ValueError(
                "policy.work_low_dim_keys includes 'goal_tokens' for live eval, "
                "but task.scenario_id is missing."
            )

        work_policy = _build_act_eval_policy(
            config=config,
            ckpt_path=ckpt_path,
            ckpt_dir=ckpt_dir,
            camera_names=camera_names,
            equipment_model=equipment_model,
            max_episode_len=max_episode_len,
            low_dim_keys=work_low_dim_keys,
            temporal_agg=temporal_agg,
            device=device,
            act_params=policy_cfg.get("act_params", {}),
        )

        bootstrap_ckpt_path_value = (
            eval_cfg.get("bootstrap_ckpt_path")
            or policy_cfg.get("bootstrap_ckpt_path")
        )
        bootstrap_ckpt_dir_value = (
            eval_cfg.get("bootstrap_ckpt_dir")
            or policy_cfg.get("bootstrap_ckpt_dir")
        )
        bootstrap_policy = None
        if bootstrap_ckpt_path_value or bootstrap_ckpt_dir_value:
            bootstrap_ckpt_path, bootstrap_ckpt_dir = _resolve_checkpoint_paths(
                ckpt_path_value=bootstrap_ckpt_path_value,
                explicit_ckpt_dir=bootstrap_ckpt_dir_value,
            )
            bootstrap_low_dim_keys = list(
                policy_cfg.get("bootstrap_low_dim_keys", work_low_dim_keys)
            )
            if "goal_tokens" in bootstrap_low_dim_keys and not scenario_id:
                raise ValueError(
                    "policy.bootstrap_low_dim_keys includes 'goal_tokens' for live eval, "
                    "but task.scenario_id is missing."
                )
            bootstrap_policy = _build_act_eval_policy(
                config=config,
                ckpt_path=bootstrap_ckpt_path,
                ckpt_dir=bootstrap_ckpt_dir,
                camera_names=camera_names,
                equipment_model=equipment_model,
                max_episode_len=max_episode_len,
                low_dim_keys=bootstrap_low_dim_keys,
                temporal_agg=temporal_agg,
                device=device,
                act_params=policy_cfg.get(
                    "bootstrap_act_params",
                    policy_cfg.get("act_params", {}),
                ),
            )

        transition_ckpt_path_value = (
            eval_cfg.get("transition_ckpt_path")
            or policy_cfg.get("transition_ckpt_path")
        )
        transition_ckpt_dir_value = (
            eval_cfg.get("transition_ckpt_dir")
            or policy_cfg.get("transition_ckpt_dir")
        )
        transition_policy = None
        if transition_ckpt_path_value or transition_ckpt_dir_value:
            transition_ckpt_path, transition_ckpt_dir = _resolve_checkpoint_paths(
                ckpt_path_value=transition_ckpt_path_value,
                explicit_ckpt_dir=transition_ckpt_dir_value,
            )
            transition_low_dim_keys = list(
                policy_cfg.get("transition_low_dim_keys", ["qpos", "qvel"])
            )
            if "goal_tokens" in transition_low_dim_keys and not scenario_id:
                raise ValueError(
                    "policy.transition_low_dim_keys includes 'goal_tokens' for live eval, "
                    "but task.scenario_id is missing."
                )
            transition_policy = _build_act_eval_policy(
                config=config,
                ckpt_path=transition_ckpt_path,
                ckpt_dir=transition_ckpt_dir,
                camera_names=camera_names,
                equipment_model=equipment_model,
                max_episode_len=max_episode_len,
                low_dim_keys=transition_low_dim_keys,
                temporal_agg=temporal_agg,
                device=device,
                act_params=policy_cfg.get(
                    "transition_act_params",
                    policy_cfg.get("act_params", {}),
                ),
            )

        from testbed.planner.boundary_detector import build_boundary_detector_from_config
        from testbed.planner.corridor_servo import (
            EntryCorridorBand,
            TransitionController,
            build_default_entry_corridor_bands,
            normalize_named_entry_corridor_bands,
        )
        from testbed.planner.fixed_sequence_planner import FixedSequencePlanner
        from testbed.planner.rule_planner import RuleTaskPlanner
        from testbed.planner.scenario_manifest import resolve_scenario_manifest
        from testbed.policies.hybrid.adapter import HybridPlannerACTPolicy

        planner_cfg = dict(policy_cfg.get("planner", {}))
        transition_cfg = dict(policy_cfg.get("transition", {}))
        default_bands = build_default_entry_corridor_bands()
        bands_cfg = transition_cfg.get("bands", {})
        bands: dict[str, EntryCorridorBand] = {}
        for name in ("left", "mid", "right"):
            default_band = default_bands[name]
            band_cfg = dict(bands_cfg.get(name, {}))
            bands[name] = EntryCorridorBand(
                name=name,
                sector_id=default_band.sector_id,
                qpos_lo=np.asarray(
                    band_cfg.get("qpos_lo", default_band.qpos_lo),
                    dtype=np.float32,
                ).reshape(4),
                qpos_hi=np.asarray(
                    band_cfg.get("qpos_hi", default_band.qpos_hi),
                    dtype=np.float32,
                ).reshape(4),
            )
        bands = normalize_named_entry_corridor_bands(bands)

        planner_kind = str(planner_cfg.get("kind", "fixed_sequence")).strip().lower()
        if planner_kind == "rule":
            manifest_id = str(planner_cfg.get("manifest_id", scenario_id or "s0_truck"))
            planner = RuleTaskPlanner(
                manifest=resolve_scenario_manifest(manifest_id)
            )
        elif planner_kind == "fixed_sequence":
            planner = FixedSequencePlanner(planner_cfg.get("sequence", ["mid", "mid", "mid"]))
        else:
            raise ValueError(
                f"Unsupported planner.kind {planner_kind!r}. "
                "Expected 'fixed_sequence' or 'rule'."
            )

        work_safety_cfg = dict(policy_cfg.get("work_safety", {}))
        policy = HybridPlannerACTPolicy(
            work_policy=work_policy,
            transition_policy=transition_policy,
            bootstrap_policy=bootstrap_policy,
            bootstrap_end_mode=str(
                policy_cfg.get("bootstrap_end_mode", "first_qualified_dig_start")
            ),
            bootstrap_end_min_bucket_mass_kg=float(
                policy_cfg.get("bootstrap_end_min_bucket_mass_kg", 300.0)
            ),
            bootstrap_end_min_distance_to_dig_area_m=float(
                policy_cfg.get("bootstrap_end_min_distance_to_dig_area_m", 0.25)
            ),
            transition_enable_fallback=bool(
                policy_cfg.get("transition_enable_fallback", False)
            ),
            transition_fallback_local_budget_steps=int(
                policy_cfg.get("transition_fallback_local_budget_steps", 180)
            ),
            transition_fallback_no_progress_steps=int(
                policy_cfg.get("transition_fallback_no_progress_steps", 120)
            ),
            transition_fallback_progress_mass_kg=float(
                policy_cfg.get("transition_fallback_progress_mass_kg", 40.0)
            ),
            transition_fallback_progress_distance_to_dig_area_m=float(
                policy_cfg.get(
                    "transition_fallback_progress_distance_to_dig_area_m",
                    reward_cfg.get("dig_area_touch_tolerance_m", 0.05),
                )
            ),
            transition_fallback_progress_bucket_depth_m=float(
                policy_cfg.get(
                    "transition_fallback_progress_bucket_depth_m",
                    reward_cfg.get("dig_below_plane_depth_tolerance_m", 0.02),
                )
            ),
            work_target_guard_enabled=bool(
                work_safety_cfg.get(
                    "target_guard_enabled",
                    policy_cfg.get("work_target_guard_enabled", False),
                )
            ),
            work_target_guard_distance_m=float(
                work_safety_cfg.get(
                    "target_guard_distance_m",
                    policy_cfg.get("work_target_guard_distance_m", 0.45),
                )
            ),
            work_target_guard_min_bucket_mass_kg=float(
                work_safety_cfg.get(
                    "target_guard_min_bucket_mass_kg",
                    policy_cfg.get("work_target_guard_min_bucket_mass_kg", 300.0),
                )
            ),
            work_target_guard_bucket_action_floor=float(
                work_safety_cfg.get(
                    "target_guard_bucket_action_floor",
                    policy_cfg.get("work_target_guard_bucket_action_floor", -0.15),
                )
            ),
            work_target_guard_boom_action_min=float(
                work_safety_cfg.get(
                    "target_guard_boom_action_min",
                    policy_cfg.get("work_target_guard_boom_action_min", 0.08),
                )
            ),
            work_target_guard_approach_distance_m=_optional_float(
                work_safety_cfg.get(
                    "target_guard_approach_distance_m",
                    policy_cfg.get("work_target_guard_approach_distance_m"),
                )
            ),
            work_target_guard_approach_bucket_action_floor=_optional_float(
                work_safety_cfg.get(
                    "target_guard_approach_bucket_action_floor",
                    policy_cfg.get("work_target_guard_approach_bucket_action_floor"),
                )
            ),
            work_target_guard_approach_boom_action_min=_optional_float(
                work_safety_cfg.get(
                    "target_guard_approach_boom_action_min",
                    policy_cfg.get("work_target_guard_approach_boom_action_min"),
                )
            ),
            planner=planner,
            transition_controller=TransitionController(
                bands=bands,
                kp=float(transition_cfg.get("kp", 2.0)),
                kd=float(transition_cfg.get("kd", 0.25)),
                action_clip=float(transition_cfg.get("action_clip", 0.35)),
                action_clip_by_joint=transition_cfg.get("action_clip_by_joint"),
                target_approach_distance_m=float(
                    transition_cfg.get(
                        "target_approach_distance_m",
                        reward_cfg.get("target_approach_distance_m", 1.25),
                    )
                ),
                clear_target_extra_distance_m=float(
                    transition_cfg.get("clear_target_extra_distance_m", 0.25)
                ),
                clear_target_min_steps=int(
                    transition_cfg.get("clear_target_min_steps", 0)
                ),
                clear_target_max_steps=int(
                    transition_cfg.get("clear_target_max_steps", 60)
                ),
                corridor_align_max_steps=int(
                    transition_cfg.get("corridor_align_max_steps", 100)
                ),
                corridor_align_qvel_abs_max=float(
                    transition_cfg.get("corridor_align_qvel_abs_max", 0.15)
                ),
                corridor_align_hold_steps=int(
                    transition_cfg.get("corridor_align_hold_steps", 5)
                ),
                wait_next_dig_max_steps=int(
                    transition_cfg.get("wait_next_dig_max_steps", 120)
                ),
                wait_next_dig_mode=str(
                    transition_cfg.get("wait_next_dig_mode", "work_policy_handoff")
                ),
                wait_next_dig_reentry_template_qpos=transition_cfg.get(
                    "wait_next_dig_reentry_template_qpos"
                ),
            ),
            boundary_detector=build_boundary_detector_from_config(
                reward_cfg=reward_cfg,
                success_cfg=success_cfg,
                pause_action_eps=float(
                    transition_cfg.get("pause_action_eps", 0.05)
                ),
            ),
            action_dim=int(policy_cfg.get("action_dim", 4)),
            scenario_id=scenario_id,
        )

    else:
        from testbed.policies.base import PolicyRegistry
        policy_cls = PolicyRegistry.get(policy_class.lower())
        policy = policy_cls(**policy_cfg.get("init_kwargs", {}))

    from testbed.eval.suite import EvalSuite
    from testbed.eval.metrics import EvalMetrics
    from testbed.runtime.run_metadata import (
        build_eval_run_metadata,
        write_json,
        write_resolved_config,
    )

    results_dir.mkdir(parents=True, exist_ok=True)
    resolved_eval_config_path = write_resolved_config(
        results_dir / "eval_resolved_config.yaml",
        config,
    )
    eval_run_metadata = build_eval_run_metadata(
        ckpt_dir=ckpt_dir,
        ckpt_path=ckpt_path,
        results_dir=results_dir,
        resolved_config_path=resolved_eval_config_path,
        task_name=task_name,
        policy_class=policy_class,
        device=device,
        scenario_id=None if scenario_id is None else str(scenario_id),
    )
    eval_run_metadata["status"] = "started"
    eval_run_metadata["success"] = {
        "mode": agx_success_mode,
        "signal_name": success_signal_name,
        "mass_thresh": None if mass_thresh is None else float(mass_thresh),
        "hold_steps": None if hold_steps is None else int(hold_steps),
        "env_state_index": env_state_index,
        "residual_bucket_mass_thresh": residual_bucket_mass_thresh,
        "strict_max_failures": {
            str(name): int(limit) for name, limit in strict_max_failures.items()
        },
    }
    eval_run_metadata["reward_overrides"] = dict(reward_cfg)
    eval_run_metadata["target_cycle_gate"] = (
        None
        if eval_cfg.get("target_cycle_gate") is None
        else int(eval_cfg.get("target_cycle_gate"))
    )
    eval_run_metadata["target_cycle_gate_terminal_hold_steps"] = (
        None
        if eval_cfg.get("target_cycle_gate_terminal_hold_steps") is None
        else int(eval_cfg.get("target_cycle_gate_terminal_hold_steps"))
    )
    eval_run_metadata_path = write_json(results_dir / "eval_run_metadata.json", eval_run_metadata)

    suite = EvalSuite(
        policy       = policy,
        task_name    = task_name,
        num_rollouts = num_rollouts,
        save_video   = save_video,
        video_dir    = video_dir,
        results_dir  = results_dir,
        ckpt_path    = str(ckpt_path),
        save_rollout_logs = save_rollout_logs,
        rollout_log_dir   = rollout_log_dir,
        step_log_interval = step_log_interval,
        agx_host     = agx_host,
        agx_port     = agx_port,
        agx_timeout  = agx_timeout,
        scenario_id = None if scenario_id is None else str(scenario_id),
        mass_thresh  = None if mass_thresh is None else float(mass_thresh),
        hold_steps   = None if hold_steps is None else int(hold_steps),
        success_signal_name = (
            None if success_signal_name is None else str(success_signal_name)
        ),
        agx_success_mode = agx_success_mode,
        strict_max_failures = strict_max_failures,
        residual_bucket_mass_thresh = residual_bucket_mass_thresh,
        env_state_index = env_state_index,
        reward_overrides = dict(reward_cfg),
        target_cycle_gate = (
            None
            if eval_cfg.get("target_cycle_gate") is None
            else int(eval_cfg.get("target_cycle_gate"))
        ),
        target_cycle_gate_terminal_hold_steps = (
            None
            if eval_cfg.get("target_cycle_gate_terminal_hold_steps") is None
            else int(eval_cfg.get("target_cycle_gate_terminal_hold_steps"))
        ),
        episode_len = max_episode_len,
        camera_names = list(camera_names),
    )
    try:
        metrics = suite.run()
    except Exception as exc:
        eval_run_metadata["status"] = "failed"
        eval_run_metadata["error"] = f"{type(exc).__name__}: {exc}"
        write_json(eval_run_metadata_path, eval_run_metadata)
        raise

    metrics.to_json(results_dir / "metrics.json")
    EvalMetrics.append_to_csv([metrics], results_dir / "results.csv")
    eval_run_metadata["status"] = "completed"
    if hasattr(metrics, "to_dict"):
        eval_run_metadata["metrics"] = metrics.to_dict()
    else:
        eval_run_metadata["metrics"] = {
            "repr": repr(metrics),
        }
    write_json(eval_run_metadata_path, eval_run_metadata)
    print(f"\nResults saved to {results_dir}")


def _resolve_low_dim_state_dim(low_dim_keys: list[str], equipment_model: str) -> int:
    dims = {
        "qpos": _resolve_single_low_dim_dim("qpos", equipment_model),
        "qvel": _resolve_single_low_dim_dim("qvel", equipment_model),
        "goal_tokens": _resolve_single_low_dim_dim("goal_tokens", equipment_model),
    }
    return int(sum(dims[key] for key in low_dim_keys))


def _optional_float(value: Any | None) -> float | None:
    return None if value is None else float(value)


def _resolve_single_low_dim_dim(key: str, equipment_model: str) -> int:
    equipment_model = str(equipment_model).lower()
    if key == "goal_tokens":
        return int(GOAL_TOKEN_DIM)
    if key in ("qpos", "qvel"):
        if "bimanual" in equipment_model:
            return 14
        if "excavator_simple" in equipment_model or "agxunity" in equipment_model or "agx" in equipment_model:
            return 4
        return 7
    raise ValueError(f"Unsupported low-dim key {key!r}.")


def _resolve_checkpoint_paths(
    *,
    ckpt_path_value: str | Path | None,
    explicit_ckpt_dir: str | Path | None,
) -> tuple[Path, Path]:
    if ckpt_path_value:
        ckpt_path = Path(ckpt_path_value)
        ckpt_dir = Path(explicit_ckpt_dir) if explicit_ckpt_dir else ckpt_path.parent
    else:
        ckpt_dir = Path(explicit_ckpt_dir) if explicit_ckpt_dir else Path("ckpts")
        ckpt_path = ckpt_dir / "policy_best.ckpt"
    return ckpt_path, ckpt_dir


def _build_act_eval_policy(
    *,
    config: dict[str, Any],
    ckpt_path: Path,
    ckpt_dir: Path,
    camera_names: list[str],
    equipment_model: str,
    max_episode_len: int,
    low_dim_keys: list[str],
    temporal_agg: bool,
    device: str,
    act_params: dict[str, Any] | None = None,
):
    act_params = dict(act_params or {})
    policy_config = {
        "lr": float(config.get("train", {}).get("lr", 1e-5)),
        "num_queries": int(act_params.get("chunk_size", 100)),
        "kl_weight": float(act_params.get("kl_weight", 10)),
        "hidden_dim": int(act_params.get("hidden_dim", 512)),
        "dim_feedforward": int(act_params.get("dim_feedforward", 3200)),
        "lr_backbone": 1e-5,
        "backbone": "resnet18",
        "enc_layers": 4,
        "dec_layers": 7,
        "nheads": 8,
        "camera_names": camera_names,
        "equipment_model": equipment_model,
        "max_episode_len": max_episode_len,
        "low_dim_keys": list(low_dim_keys),
        "state_dim": _resolve_low_dim_state_dim(low_dim_keys, equipment_model),
    }
    from testbed.policies.act.adapter import ACTAdapter

    return ACTAdapter.from_checkpoint(
        ckpt_path=ckpt_path,
        policy_config=policy_config,
        norm_stats_path=ckpt_dir / "dataset_stats.pkl",
        temporal_agg=temporal_agg,
        device=device,
    )
