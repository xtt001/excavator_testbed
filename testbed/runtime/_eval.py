"""Internal eval helper called by Runner.eval()."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from testbed.data.dig_depth_profile_v2_4 import DIG_DEPTH_PROFILE_TOKEN_DIM
from testbed.data.operator_first_v2_2 import (
    DIG_CUT_TOKEN_DIM,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_TARGET_TOKEN_DIM,
)
from testbed.data.v2_1 import GOAL_TOKEN_DIM
from testbed.planner.cell_entry import CELL_ENTRY_TOKEN_DIM
from testbed.runtime.torch_performance import (
    configure_torch_performance,
    eval_torch_performance_config,
)


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
    from testbed.eval.tasks import EVAL_SEED, get_eval_task

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
    seed_base = int(eval_cfg.get("seed", EVAL_SEED))
    if seed_base < 0:
        raise ValueError("eval.seed must be non-negative")
    save_video      = bool(eval_cfg.get("save_video", True))
    if policy_class == "PRIMITIVE_PLANNER_ACT_5P":
        raise ValueError(
            "PRIMITIVE_PLANNER_ACT_5P runtime planner has been removed; "
            "use PRIMITIVE_PLANNER_ACT for the supported 4P runtime path."
        )
    temporal_agg_default = True if policy_class == "PRIMITIVE_PLANNER_ACT" else False
    temporal_agg    = bool(
        eval_cfg.get(
            "temporal_agg",
            policy_cfg.get("temporal_agg", temporal_agg_default),
        )
    )
    device          = str(policy_cfg.get("device", eval_cfg.get("device", "cuda")))
    _configure_eval_torch_performance(eval_cfg, device=device)
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
    elif policy_class == "PRIMITIVE_PLANNER_ACT":
        ckpt_path_value = (
            eval_cfg.get("dig_ckpt_path")
            or policy_cfg.get("dig_ckpt_path")
            or eval_cfg.get("ckpt_path")
            or policy_cfg.get("ckpt_path")
        )
        explicit_ckpt_dir = (
            eval_cfg.get("dig_ckpt_dir")
            or policy_cfg.get("dig_ckpt_dir")
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
    stream_rollout_logs = bool(eval_cfg.get("stream_rollout_logs", False))
    rollout_log_dir = Path(eval_cfg.get("rollout_log_dir", results_dir / "rollouts"))
    record_hdf5 = bool(eval_cfg.get("record_hdf5", False))
    record_hdf5_dir = Path(
        eval_cfg.get(
            "record_hdf5_dir",
            eval_cfg.get("hdf5_dir", results_dir / "hdf5_rollouts"),
        )
    )
    record_hdf5_with_cell_entry = bool(
        eval_cfg.get("record_hdf5_with_cell_entry", True)
    )
    from testbed.runtime.eval_output_paths import (
        assert_eval_output_paths_available,
    )

    assert_eval_output_paths_available(
        enabled=bool(eval_cfg.get("no_overwrite", False)),
        results_dir=results_dir,
        video_dir=video_dir,
        rollout_log_dir=rollout_log_dir,
        hdf5_dir=record_hdf5_dir,
        save_video=save_video,
        save_rollout_logs=save_rollout_logs,
        record_hdf5=record_hdf5,
    )
    send_planner_debug_to_backend = bool(
        eval_cfg.get("send_planner_debug_to_backend", True)
    )
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
            image_mask_config=policy_cfg.get("image_mask", {}),
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
            image_mask_config=policy_cfg.get(
                "work_image_mask",
                policy_cfg.get("image_mask", {}),
            ),
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
                image_mask_config=policy_cfg.get(
                    "bootstrap_image_mask",
                    policy_cfg.get("image_mask", {}),
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
                image_mask_config=policy_cfg.get(
                    "transition_image_mask",
                    policy_cfg.get("image_mask", {}),
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
                scripted_bucket_qpos_target=transition_cfg.get(
                    "scripted_bucket_qpos_target"
                ),
                scripted_bucket_qpos_tolerance=float(
                    transition_cfg.get("scripted_bucket_qpos_tolerance", 0.03)
                ),
            ),
            boundary_detector=build_boundary_detector_from_config(
                reward_cfg=reward_cfg,
                success_cfg=success_cfg,
                boundary_cfg=dict(config.get("boundary", {}) or {}),
                pause_action_eps=float(
                    transition_cfg.get("pause_action_eps", 0.05)
                ),
            ),
            action_dim=int(policy_cfg.get("action_dim", 4)),
            scenario_id=scenario_id,
        )

    elif policy_class == "PRIMITIVE_PLANNER_ACT":
        primitive_low_dim_keys = list(policy_cfg.get("primitive_low_dim_keys", ["qpos", "qvel"]))
        if "goal_tokens" in primitive_low_dim_keys and not scenario_id:
            raise ValueError(
                "policy.primitive_low_dim_keys includes 'goal_tokens' for live eval, "
                "but task.scenario_id is missing."
            )

        primitive_policies = {}
        primitive_ckpt_paths: dict[str, str] = {}
        primitive_ckpt_dirs: dict[str, str] = {}
        primitive_names = ("dig", "carry", "dump", "return")
        for primitive_name in primitive_names:
            primitive_ckpt_path_value = (
                eval_cfg.get(f"{primitive_name}_ckpt_path")
                or policy_cfg.get(f"{primitive_name}_ckpt_path")
            )
            primitive_ckpt_dir_value = (
                eval_cfg.get(f"{primitive_name}_ckpt_dir")
                or policy_cfg.get(f"{primitive_name}_ckpt_dir")
            )
            primitive_ckpt_path, primitive_ckpt_dir = _resolve_checkpoint_paths(
                ckpt_path_value=primitive_ckpt_path_value,
                explicit_ckpt_dir=primitive_ckpt_dir_value,
            )
            primitive_low_dim_keys_for_skill = list(
                policy_cfg.get(f"{primitive_name}_low_dim_keys", primitive_low_dim_keys)
            )
            if "goal_tokens" in primitive_low_dim_keys_for_skill and not scenario_id:
                raise ValueError(
                    f"policy.{primitive_name}_low_dim_keys includes 'goal_tokens' "
                    "for live eval, but task.scenario_id is missing."
                )
            primitive_policies[primitive_name] = _build_act_eval_policy(
                config=config,
                ckpt_path=primitive_ckpt_path,
                ckpt_dir=primitive_ckpt_dir,
                camera_names=camera_names,
                equipment_model=equipment_model,
                max_episode_len=max_episode_len,
                low_dim_keys=primitive_low_dim_keys_for_skill,
                temporal_agg=temporal_agg,
                device=device,
                act_params=policy_cfg.get(
                    f"{primitive_name}_act_params",
                    policy_cfg.get("act_params", {}),
                ),
                outcome_head_config=policy_cfg.get(
                    f"{primitive_name}_outcome_head",
                    policy_cfg.get("outcome_head", {}),
                ),
                image_mask_config=policy_cfg.get(
                    f"{primitive_name}_image_mask",
                    policy_cfg.get("image_mask", {}),
                ),
            )
            primitive_ckpt_paths[primitive_name] = str(primitive_ckpt_path)
            primitive_ckpt_dirs[primitive_name] = str(primitive_ckpt_dir)

        first_dig_ckpt_path_value = (
            eval_cfg.get("first_dig_ckpt_path")
            or policy_cfg.get("first_dig_ckpt_path")
        )
        first_dig_ckpt_dir_value = (
            eval_cfg.get("first_dig_ckpt_dir")
            or policy_cfg.get("first_dig_ckpt_dir")
        )
        first_dig_policy = None
        if first_dig_ckpt_path_value or first_dig_ckpt_dir_value:
            first_dig_ckpt_path, first_dig_ckpt_dir = _resolve_checkpoint_paths(
                ckpt_path_value=first_dig_ckpt_path_value,
                explicit_ckpt_dir=first_dig_ckpt_dir_value,
            )
            first_dig_low_dim_keys = list(
                policy_cfg.get(
                    "first_dig_low_dim_keys",
                    policy_cfg.get("dig_low_dim_keys", primitive_low_dim_keys),
                )
            )
            if "goal_tokens" in first_dig_low_dim_keys and not scenario_id:
                raise ValueError(
                    "policy.first_dig_low_dim_keys includes 'goal_tokens' "
                    "for live eval, but task.scenario_id is missing."
                )
            first_dig_policy = _build_act_eval_policy(
                config=config,
                ckpt_path=first_dig_ckpt_path,
                ckpt_dir=first_dig_ckpt_dir,
                camera_names=camera_names,
                equipment_model=equipment_model,
                max_episode_len=max_episode_len,
                low_dim_keys=first_dig_low_dim_keys,
                temporal_agg=temporal_agg,
                device=device,
                act_params=policy_cfg.get(
                    "first_dig_act_params",
                    policy_cfg.get("dig_act_params", policy_cfg.get("act_params", {})),
                ),
                outcome_head_config=policy_cfg.get(
                    "first_dig_outcome_head",
                    policy_cfg.get("dig_outcome_head", policy_cfg.get("outcome_head", {})),
                ),
                image_mask_config=policy_cfg.get(
                    "first_dig_image_mask",
                    policy_cfg.get("dig_image_mask", policy_cfg.get("image_mask", {})),
                ),
            )
            primitive_ckpt_paths["first_dig"] = str(first_dig_ckpt_path)
            primitive_ckpt_dirs["first_dig"] = str(first_dig_ckpt_dir)

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
                policy_cfg.get("bootstrap_low_dim_keys", primitive_low_dim_keys)
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
                image_mask_config=policy_cfg.get(
                    "bootstrap_image_mask",
                    policy_cfg.get("image_mask", {}),
                ),
            )
            primitive_ckpt_paths["bootstrap"] = str(bootstrap_ckpt_path)
            primitive_ckpt_dirs["bootstrap"] = str(bootstrap_ckpt_dir)

        from testbed.planner.boundary_detector import build_boundary_detector_from_config
        from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy

        switch_cfg = dict(policy_cfg.get("switch", {}))
        transition_cfg = dict(policy_cfg.get("transition", {}))
        scripted_bootstrap_cfg = dict(policy_cfg.get("scripted_bootstrap", {}))
        cell_entry_cfg = dict(policy_cfg.get("cell_entry", {}))
        dig_cut_planner_cfg = dict(policy_cfg.get("dig_cut_planner", {}))
        _validate_dig_depth_profile_eval_low_dim(
            policy_cfg=policy_cfg,
            dig_cut_planner_cfg=dig_cut_planner_cfg,
            primitive_low_dim_keys=primitive_low_dim_keys,
            first_dig_policy_enabled=first_dig_policy is not None,
        )
        return_target_planner_cfg = dict(policy_cfg.get("return_target_planner", {}))
        box_emptying_cfg = dict(policy_cfg.get("box_emptying", {}))
        pre_dig_align_cfg = dict(policy_cfg.get("pre_dig_align", {}))
        boundary_detector = build_boundary_detector_from_config(
            reward_cfg=reward_cfg,
            success_cfg=success_cfg,
            boundary_cfg=dict(config.get("boundary", {}) or {}),
            pause_action_eps=float(
                switch_cfg.get(
                    "pause_action_eps",
                    transition_cfg.get("pause_action_eps", 0.05),
                )
            ),
        )
        common_kwargs = {
            "first_dig_policy": first_dig_policy,
            "bootstrap_policy": bootstrap_policy,
            "bootstrap_end_mode": str(policy_cfg.get("bootstrap_end_mode", "disabled")),
            "bootstrap_end_min_bucket_mass_kg": float(
                policy_cfg.get("bootstrap_end_min_bucket_mass_kg", 300.0)
            ),
            "bootstrap_end_min_distance_to_dig_area_m": float(
                policy_cfg.get("bootstrap_end_min_distance_to_dig_area_m", 0.25)
            ),
            "dig_to_carry_min_bucket_mass_kg": float(
                switch_cfg.get("dig_to_carry_min_bucket_mass_kg", 300.0)
            ),
            "dig_to_carry_min_distance_to_dig_area_m": float(
                switch_cfg.get("dig_to_carry_min_distance_to_dig_area_m", 0.20)
            ),
            "dig_to_carry_target_bucket_mass_kg": _optional_float(
                switch_cfg.get("dig_to_carry_target_bucket_mass_kg")
            ),
            "dig_to_carry_mass_plateau_enabled": bool(
                switch_cfg.get("dig_to_carry_mass_plateau_enabled", False)
            ),
            "dig_to_carry_mass_plateau_min_bucket_mass_kg": float(
                switch_cfg.get("dig_to_carry_mass_plateau_min_bucket_mass_kg", 20.0)
            ),
            "dig_to_carry_mass_plateau_epsilon_kg": float(
                switch_cfg.get("dig_to_carry_mass_plateau_epsilon_kg", 1.0)
            ),
            "dig_to_carry_mass_plateau_hold_steps": int(
                switch_cfg.get("dig_to_carry_mass_plateau_hold_steps", 25)
            ),
            "dig_to_carry_mass_plateau_min_steps": int(
                switch_cfg.get("dig_to_carry_mass_plateau_min_steps", 80)
            ),
            "dig_bad_replan_enabled": bool(
                switch_cfg.get("dig_bad_replan_enabled", False)
            ),
            "dig_bad_replan_max_steps": int(
                switch_cfg.get("dig_bad_replan_max_steps", 180)
            ),
            "dig_bad_replan_min_bucket_mass_kg": float(
                switch_cfg.get("dig_bad_replan_min_bucket_mass_kg", 15.0)
            ),
            "dig_exit_guard_enabled": bool(
                switch_cfg.get("dig_exit_guard_enabled", False)
            ),
            "dig_exit_guard_min_steps": int(
                switch_cfg.get("dig_exit_guard_min_steps", 80)
            ),
            "dig_exit_guard_overshoot_m": float(
                switch_cfg.get("dig_exit_guard_overshoot_m", 0.65)
            ),
            "dig_exit_guard_min_bucket_mass_kg": float(
                switch_cfg.get("dig_exit_guard_min_bucket_mass_kg", 20.0)
            ),
            "dig_failed_replan_next_skill": str(
                switch_cfg.get("dig_failed_replan_next_skill", "dig")
            ),
            "dump_done_max_bucket_mass_kg": float(
                switch_cfg.get("dump_done_max_bucket_mass_kg", 100.0)
            ),
            "dump_done_min_deposit_delta_kg": float(
                switch_cfg.get("dump_done_min_deposit_delta_kg", 10.0)
            ),
            "dump_done_hold_steps": int(switch_cfg.get("dump_done_hold_steps", 2)),
            "dump_done_use_boundary_event": bool(
                switch_cfg.get("dump_done_use_boundary_event", True)
            ),
            "dump_ready_near_window_enabled": bool(
                switch_cfg.get("dump_ready_near_window_enabled", False)
            ),
            "dump_ready_near_window_x_tolerance_m": float(
                switch_cfg.get("dump_ready_near_window_x_tolerance_m", 0.05)
            ),
            "dump_ready_near_window_z_tolerance_m": float(
                switch_cfg.get("dump_ready_near_window_z_tolerance_m", 0.05)
            ),
            "dump_ready_near_window_outside_tolerance_m": float(
                switch_cfg.get("dump_ready_near_window_outside_tolerance_m", 0.0)
            ),
            "dump_ready_near_window_require_over_footprint": bool(
                switch_cfg.get("dump_ready_near_window_require_over_footprint", True)
            ),
            "return_to_dig_shallow_guard_enabled": bool(
                switch_cfg.get("return_to_dig_shallow_guard_enabled", False)
            ),
            "return_to_dig_max_bucket_mass_kg": float(
                switch_cfg.get("return_to_dig_max_bucket_mass_kg", 15.0)
            ),
            "return_to_dig_touch_tolerance_m": float(
                switch_cfg.get(
                    "return_to_dig_touch_tolerance_m",
                    reward_cfg.get("dig_area_touch_tolerance_m", 0.05),
                )
            ),
            "return_to_dig_min_depth_m": float(
                switch_cfg.get(
                    "return_to_dig_min_depth_m",
                    reward_cfg.get("dig_below_plane_depth_tolerance_m", 0.02),
                )
            ),
            "return_to_dig_max_depth_m": float(
                switch_cfg.get("return_to_dig_max_depth_m", 0.12)
            ),
            "return_to_dig_max_entry_error_m": (
                None
                if switch_cfg.get("return_to_dig_max_entry_error_m") is None
                else float(switch_cfg.get("return_to_dig_max_entry_error_m"))
            ),
            "return_to_dig_start_envelope_gate_enabled": bool(
                switch_cfg.get("return_to_dig_start_envelope_gate_enabled", False)
            ),
            "return_to_dig_start_envelope_spatial_tolerance": float(
                switch_cfg.get("return_to_dig_start_envelope_spatial_tolerance", 0.10)
            ),
            "return_to_dig_start_envelope_depth_tolerance_m": float(
                switch_cfg.get(
                    "return_to_dig_start_envelope_depth_tolerance_m",
                    0.08,
                )
            ),
            "return_to_dig_start_envelope_local_depth_tolerance_m": float(
                switch_cfg.get(
                    "return_to_dig_start_envelope_local_depth_tolerance_m",
                    0.005,
                )
            ),
            "return_to_dig_start_envelope_plane_depth_tolerance_m": float(
                switch_cfg.get(
                    "return_to_dig_start_envelope_plane_depth_tolerance_m",
                    0.05,
                )
            ),
            "return_to_dig_start_envelope_plane_depth_mode": str(
                switch_cfg.get(
                    "return_to_dig_start_envelope_plane_depth_mode",
                    "range",
                )
            ),
            "return_to_dig_start_envelope_qpos_tolerance": float(
                switch_cfg.get("return_to_dig_start_envelope_qpos_tolerance", 0.04)
            ),
            "return_to_dig_start_envelope_require_contact": bool(
                switch_cfg.get("return_to_dig_start_envelope_require_contact", True)
            ),
            "return_to_dig_start_envelope_direct_handoff_enabled": bool(
                switch_cfg.get(
                    "return_to_dig_start_envelope_direct_handoff_enabled",
                    False,
                )
            ),
            "return_max_steps": int(
                switch_cfg.get(
                    "return_max_steps",
                    transition_cfg.get("wait_next_dig_max_steps", 420),
                )
            ),
            "boundary_detector": boundary_detector,
            "action_dim": int(policy_cfg.get("action_dim", 4)),
            "primitive_checkpoint_paths": primitive_ckpt_paths,
            "goal_sequence": list(
                policy_cfg.get(
                    "goal_sequence",
                    policy_cfg.get("primitive_goal_sequence", []),
                )
                or []
            ),
            "goal_scenario_id": str(
                policy_cfg.get("goal_scenario_id", scenario_id or "s0_truck")
            ),
            "goal_depth_norm": float(policy_cfg.get("goal_depth_norm", 1.0)),
            "goal_dump_target_norm": float(
                policy_cfg.get("goal_dump_target_norm", 1.0)
            ),
            "cell_entry_enabled": bool(
                cell_entry_cfg.get("enabled", policy_cfg.get("cell_entry_enabled", False))
            ),
            "cell_entry_grid": dict(cell_entry_cfg.get("grid", {})),
            "cell_entry_low_productivity_payload_gain_kg": float(
                cell_entry_cfg.get("low_productivity_payload_gain_kg", 100.0)
            ),
            "dig_cut_planner": dig_cut_planner_cfg,
            "return_target_planner": return_target_planner_cfg,
            "box_emptying": box_emptying_cfg,
            "pre_dig_align": pre_dig_align_cfg,
            "scripted_bootstrap_target_qpos": scripted_bootstrap_cfg.get("target_qpos"),
            "scripted_bootstrap_kp": float(scripted_bootstrap_cfg.get("kp", 2.0)),
            "scripted_bootstrap_kd": float(scripted_bootstrap_cfg.get("kd", 0.25)),
            "scripted_bootstrap_action_clip": scripted_bootstrap_cfg.get(
                "action_clip",
                0.35,
            ),
            "scripted_bootstrap_action_signs": scripted_bootstrap_cfg.get(
                "action_signs"
            ),
            "scripted_bootstrap_qpos_tolerance": float(
                scripted_bootstrap_cfg.get("qpos_tolerance", 0.02)
            ),
            "scripted_bootstrap_qvel_abs_max": float(
                scripted_bootstrap_cfg.get("qvel_abs_max", 0.08)
            ),
            "scripted_bootstrap_hold_steps": int(
                scripted_bootstrap_cfg.get("hold_steps", 5)
            ),
            "scripted_bootstrap_max_steps": int(
                scripted_bootstrap_cfg.get("max_steps", 240)
            ),
        }
        policy = PrimitivePlannerACTPolicy(
            dig_policy=primitive_policies["dig"],
            carry_policy=primitive_policies["carry"],
            dump_policy=primitive_policies["dump"],
            return_policy=primitive_policies["return"],
            dump_ready_min_bucket_mass_kg=float(
                switch_cfg.get("dump_ready_min_bucket_mass_kg", 150.0)
            ),
            dump_ready_min_height_above_rim_m=float(
                switch_cfg.get("dump_ready_min_height_above_rim_m", 0.45)
            ),
            dump_ready_require_over_footprint=bool(
                switch_cfg.get("dump_ready_require_over_footprint", True)
            ),
            dump_ready_require_clearance=bool(
                switch_cfg.get("dump_ready_require_clearance", True)
            ),
            dump_ready_max_horizontal_distance_m=_optional_float(
                switch_cfg.get("dump_ready_max_horizontal_distance_m", 0.82)
            ),
            dump_ready_position_mode=str(
                switch_cfg.get(
                    "dump_ready_position_mode",
                    "footprint_or_dump_area_relative",
                )
            ),
            dump_ready_max_dump_area_footprint_outside_distance_m=_optional_float(
                switch_cfg.get(
                    "dump_ready_max_dump_area_footprint_outside_distance_m",
                    0.05,
                )
            ),
            dump_ready_min_dump_area_relative_x_m=_optional_float(
                switch_cfg.get("dump_ready_min_dump_area_relative_x_m")
            ),
            dump_ready_max_dump_area_relative_x_m=_optional_float(
                switch_cfg.get("dump_ready_max_dump_area_relative_x_m")
            ),
            dump_ready_min_dump_area_relative_z_m=_optional_float(
                switch_cfg.get("dump_ready_min_dump_area_relative_z_m")
            ),
            dump_ready_max_dump_area_relative_z_m=_optional_float(
                switch_cfg.get("dump_ready_max_dump_area_relative_z_m")
            ),
            dump_ready_hold_steps=int(switch_cfg.get("dump_ready_hold_steps", 3)),
            **common_kwargs,
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
    eval_run_metadata["seed_base"] = seed_base
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
    eval_run_metadata["live_goal_sequence"] = list(
        eval_cfg.get("live_goal_sequence", policy_cfg.get("goal_sequence", [])) or []
    )
    eval_run_metadata["live_goal_depth_norm"] = float(
        eval_cfg.get("live_goal_depth_norm", policy_cfg.get("goal_depth_norm", 1.0))
    )
    eval_run_metadata["live_goal_dump_target_norm"] = float(
        eval_cfg.get(
            "live_goal_dump_target_norm",
            policy_cfg.get("goal_dump_target_norm", 1.0),
        )
    )
    eval_run_metadata["record_hdf5"] = {
        "enabled": record_hdf5,
        "dir": str(record_hdf5_dir),
        "with_cell_entry": record_hdf5_with_cell_entry,
    }
    eval_run_metadata["send_planner_debug_to_backend"] = bool(
        send_planner_debug_to_backend
    )
    eval_run_metadata_path = write_json(results_dir / "eval_run_metadata.json", eval_run_metadata)
    repo_a_snapshot = dict(eval_run_metadata.get("repo_snapshots", {}).get("repo_a", {}))
    record_hdf5_metadata = dict(eval_cfg.get("record_hdf5_metadata", {}) or {})
    record_hdf5_metadata.update(
        {
            "record_config_path": str(resolved_eval_config_path.resolve()),
            "eval_results_dir": str(results_dir.resolve()),
            "eval_run_metadata_path": str(eval_run_metadata_path.resolve()),
            "git_commit": str(repo_a_snapshot.get("commit", "")),
            "git_branch": str(repo_a_snapshot.get("branch", "")),
            "git_dirty": int(bool(repo_a_snapshot.get("dirty", False))),
            "policy_class": str(policy_class),
            "device_requested": str(device),
        }
    )
    if policy_class == "PRIMITIVE_PLANNER_ACT":
        record_hdf5_metadata.update(
            {
                "dig_ckpt_path": str(policy_cfg.get("dig_ckpt_path", "")),
                "carry_ckpt_path": str(policy_cfg.get("carry_ckpt_path", "")),
                "dump_ckpt_path": str(policy_cfg.get("dump_ckpt_path", "")),
                "return_ckpt_path": str(policy_cfg.get("return_ckpt_path", "")),
            }
        )

    suite = EvalSuite(
        policy       = policy,
        task_name    = task_name,
        num_rollouts = num_rollouts,
        seed_base    = seed_base,
        save_video   = save_video,
        video_dir    = video_dir,
        results_dir  = results_dir,
        ckpt_path    = str(ckpt_path),
        save_rollout_logs = save_rollout_logs,
        stream_rollout_logs = stream_rollout_logs,
        rollout_log_dir   = rollout_log_dir,
        record_hdf5 = record_hdf5,
        record_hdf5_dir = record_hdf5_dir,
        record_hdf5_metadata = record_hdf5_metadata,
        record_hdf5_with_cell_entry = record_hdf5_with_cell_entry,
        send_planner_debug_to_backend = send_planner_debug_to_backend,
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
        live_goal_sequence = eval_cfg.get(
            "live_goal_sequence",
            policy_cfg.get("goal_sequence", []),
        ),
        live_goal_depth_norm = float(
            eval_cfg.get("live_goal_depth_norm", policy_cfg.get("goal_depth_norm", 1.0))
        ),
        live_goal_dump_target_norm = float(
            eval_cfg.get(
                "live_goal_dump_target_norm",
                policy_cfg.get("goal_dump_target_norm", 1.0),
            )
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
        "cell_entry_tokens": _resolve_single_low_dim_dim(
            "cell_entry_tokens", equipment_model
        ),
        "dig_cut_tokens": _resolve_single_low_dim_dim(
            "dig_cut_tokens", equipment_model
        ),
        "dig_depth_profile_tokens_v1": _resolve_single_low_dim_dim(
            "dig_depth_profile_tokens_v1", equipment_model
        ),
        "return_target_tokens": _resolve_single_low_dim_dim(
            "return_target_tokens", equipment_model
        ),
        "return_relocate_tokens_v1": _resolve_single_low_dim_dim(
            "return_relocate_tokens_v1", equipment_model
        ),
        "return_start_envelope_tokens_v1": _resolve_single_low_dim_dim(
            "return_start_envelope_tokens_v1", equipment_model
        ),
    }
    return int(sum(dims[key] for key in low_dim_keys))


def _configure_eval_torch_performance(
    eval_cfg: dict[str, Any],
    *,
    device: str,
):
    torch_performance_config = eval_torch_performance_config(eval_cfg)
    eval_cfg.update(torch_performance_config.as_config_dict())
    configure_torch_performance(torch_performance_config, device=device)
    return torch_performance_config


def _validate_dig_depth_profile_eval_low_dim(
    *,
    policy_cfg: dict[str, Any],
    dig_cut_planner_cfg: dict[str, Any],
    primitive_low_dim_keys: list[str],
    first_dig_policy_enabled: bool,
) -> None:
    profile_cfg = dict(dig_cut_planner_cfg.get("dig_depth_profile", {}) or {})
    if not bool(profile_cfg.get("required", False)):
        return
    required_key = "dig_depth_profile_tokens_v1"
    dig_low_dim_keys = list(policy_cfg.get("dig_low_dim_keys", primitive_low_dim_keys))
    if required_key not in dig_low_dim_keys:
        raise ValueError(
            "dig_cut_planner.dig_depth_profile.required=true, but "
            f"policy.dig_low_dim_keys does not include {required_key!r}. "
            "Without this key the ACT checkpoint would silently ignore the "
            "strict prior-driven profile token."
        )
    if first_dig_policy_enabled:
        first_dig_low_dim_keys = list(
            policy_cfg.get(
                "first_dig_low_dim_keys",
                policy_cfg.get("dig_low_dim_keys", primitive_low_dim_keys),
            )
        )
        if required_key not in first_dig_low_dim_keys:
            raise ValueError(
                "dig_cut_planner.dig_depth_profile.required=true, but "
                f"policy.first_dig_low_dim_keys does not include {required_key!r}."
            )


def _optional_float(value: Any | None) -> float | None:
    return None if value is None else float(value)


def _resolve_single_low_dim_dim(key: str, equipment_model: str) -> int:
    equipment_model = str(equipment_model).lower()
    if key == "goal_tokens":
        return int(GOAL_TOKEN_DIM)
    if key == "cell_entry_tokens":
        return int(CELL_ENTRY_TOKEN_DIM)
    if key == "dig_cut_tokens":
        return int(DIG_CUT_TOKEN_DIM)
    if key == "dig_depth_profile_tokens_v1":
        return int(DIG_DEPTH_PROFILE_TOKEN_DIM)
    if key == "return_target_tokens":
        return int(RETURN_TARGET_TOKEN_DIM)
    if key == "return_relocate_tokens_v1":
        return int(RETURN_TARGET_TOKEN_DIM)
    if key == "return_start_envelope_tokens_v1":
        return int(RETURN_START_ENVELOPE_TOKEN_DIM)
    if key in ("qpos", "qvel"):
        if "bimanual" in equipment_model:
            return 14
        if (
            "excavator_simple" in equipment_model
            or "agxunity" in equipment_model
            or "agx" in equipment_model
            or "yulong" in equipment_model
        ):
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
    outcome_head_config: dict[str, Any] | None = None,
    image_mask_config: dict[str, Any] | None = None,
):
    act_params = dict(act_params or {})
    outcome_head_config = dict(outcome_head_config or {})
    outcome_head_enabled = bool(outcome_head_config.get("enabled", False))
    outcome_dim = int(
        outcome_head_config.get("dim", 10 if outcome_head_enabled else 0)
    )
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
        "image_mask": dict(image_mask_config or {}),
        "outcome_head": outcome_head_config,
        "outcome_dim": outcome_dim if outcome_head_enabled else 0,
        "outcome_action_horizon": int(
            outcome_head_config.get("action_horizon", act_params.get("chunk_size", 100))
        ),
        "outcome_hidden_dim": outcome_head_config.get("hidden_dim"),
    }
    for temporal_key in (
        "temporal_agg_window",
        "temporal_agg_weight_order",
        "temporal_agg_decay",
    ):
        if temporal_key in act_params:
            policy_config[temporal_key] = act_params[temporal_key]
    from testbed.policies.act.adapter import ACTAdapter

    return ACTAdapter.from_checkpoint(
        ckpt_path=ckpt_path,
        policy_config=policy_config,
        norm_stats_path=ckpt_dir / "dataset_stats.pkl",
        temporal_agg=temporal_agg,
        device=device,
    )
