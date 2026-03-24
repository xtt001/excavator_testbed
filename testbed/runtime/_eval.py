"""Internal eval helper called by Runner.eval()."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def eval_policy(config: dict[str, Any]) -> None:
    agx_cfg    = config.get("agx", {})
    success_cfg = config.get("success", {})
    reward_cfg = config.get("reward", {})
    task_cfg   = config.get("task", {})
    policy_cfg = config.get("policy", {})
    eval_cfg   = config.get("eval", {})

    policy_class = str(policy_cfg.get("class", policy_cfg.get("name", "ACT"))).upper()
    task_name = task_cfg.get("name", task_cfg.get("task_name", config.get("task_name", "")))
    from testbed.eval.tasks import get_eval_task

    task_def = get_eval_task(task_name)
    equipment_model = task_cfg.get(
        "equipment_model",
        config.get("equipment_model", task_def.equipment_model),
    )
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
    ckpt_path_value = eval_cfg.get("ckpt_path") or policy_cfg.get("ckpt_path")
    explicit_ckpt_dir = eval_cfg.get("ckpt_dir", config.get("train", {}).get("ckpt_dir"))
    if ckpt_path_value:
        ckpt_path = Path(ckpt_path_value)
        ckpt_dir = Path(explicit_ckpt_dir) if explicit_ckpt_dir else ckpt_path.parent
    else:
        ckpt_dir = Path(explicit_ckpt_dir) if explicit_ckpt_dir else Path("ckpts")
        ckpt_path = ckpt_dir / "policy_best.ckpt"
    video_dir       = Path(eval_cfg.get("video_dir", ckpt_dir / "eval_videos"))
    results_dir     = Path(eval_cfg.get("results_dir", ckpt_dir / "eval_results"))
    agx_host        = str(agx_cfg.get("host", "127.0.0.1"))
    agx_port        = int(agx_cfg.get("port", 5057))
    agx_timeout     = float(agx_cfg.get("timeout", 10.0))
    mass_thresh     = success_cfg.get("mass_thresh", success_cfg.get("mass_thresh_kg"))
    hold_steps      = success_cfg.get("hold_steps")
    success_signal_name = success_cfg.get(
        "signal_name",
        success_cfg.get("success_signal_name"),
    )
    env_state_index_value = success_cfg.get(
        "env_state_idx",
        success_cfg.get("env_state_index"),
    )
    env_state_index = None if env_state_index_value is None else int(env_state_index_value)

    if policy_class == "ACT":
        act_params     = policy_cfg.get("act_params", {})
        norm_stats_path = ckpt_dir / "dataset_stats.pkl"
        policy_config  = {
            "lr":            float(config.get("train", {}).get("lr", 1e-5)),
            "num_queries":   int(act_params.get("chunk_size", 100)),
            "kl_weight":     float(act_params.get("kl_weight", 10)),
            "hidden_dim":    int(act_params.get("hidden_dim", 512)),
            "dim_feedforward": int(act_params.get("dim_feedforward", 3200)),
            "lr_backbone":   1e-5,
            "backbone":      "resnet18",
            "enc_layers":    4,
            "dec_layers":    7,
            "nheads":        8,
            "camera_names":  camera_names,
            "equipment_model": equipment_model,
            "max_episode_len": max_episode_len,
        }
        from testbed.policies.act.adapter import ACTAdapter
        policy = ACTAdapter.from_checkpoint(
            ckpt_path=ckpt_path,
            policy_config=policy_config,
            norm_stats_path=norm_stats_path,
            temporal_agg=temporal_agg,
            device=device,
        )

    elif policy_class == "DUMMY":
        action_dim = int(policy_cfg.get("action_dim", 4))
        from testbed.policies.dummy.adapter import DummyPolicy
        policy = DummyPolicy(action_dim=action_dim, mode=policy_cfg.get("mode", "zero"))

    else:
        from testbed.policies.base import PolicyRegistry
        policy_cls = PolicyRegistry.get(policy_class.lower())
        policy = policy_cls(**policy_cfg.get("init_kwargs", {}))

    from testbed.eval.suite import EvalSuite
    from testbed.eval.metrics import EvalMetrics

    suite = EvalSuite(
        policy       = policy,
        task_name    = task_name,
        num_rollouts = num_rollouts,
        save_video   = save_video,
        video_dir    = video_dir,
        ckpt_path    = str(ckpt_path),
        agx_host     = agx_host,
        agx_port     = agx_port,
        agx_timeout  = agx_timeout,
        mass_thresh  = None if mass_thresh is None else float(mass_thresh),
        hold_steps   = None if hold_steps is None else int(hold_steps),
        success_signal_name = (
            None if success_signal_name is None else str(success_signal_name)
        ),
        env_state_index = env_state_index,
        reward_overrides = dict(reward_cfg),
    )
    metrics = suite.run()

    # save results
    results_dir.mkdir(parents=True, exist_ok=True)
    metrics.to_json(results_dir / "metrics.json")
    EvalMetrics.append_to_csv([metrics], results_dir / "results.csv")
    print(f"\nResults saved to {results_dir}")
