"""Internal eval helper called by Runner.eval()."""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any


def eval_policy(config: dict[str, Any]) -> None:
    task_cfg   = config.get("task", {})
    policy_cfg = config.get("policy", {})
    eval_cfg   = config.get("eval", {})

    policy_class    = policy_cfg.get("class", "ACT").upper()
    task_name       = task_cfg.get("name", config.get("task_name", ""))
    equipment_model = task_cfg.get("equipment_model", config.get("equipment_model", "excavator_simple"))
    camera_names    = task_cfg.get("camera_names", config.get("camera_names", []))
    num_rollouts    = int(eval_cfg.get("num_rollouts", 50))
    save_video      = bool(eval_cfg.get("save_video", True))
    temporal_agg    = bool(eval_cfg.get("temporal_agg", False))
    ckpt_dir        = Path(eval_cfg.get("ckpt_dir", config.get("train", {}).get("ckpt_dir", "ckpts")))
    ckpt_path       = Path(eval_cfg.get("ckpt_path", ckpt_dir / "policy_best.ckpt"))
    video_dir       = Path(eval_cfg.get("video_dir", ckpt_dir / "eval_videos"))
    results_dir     = Path(eval_cfg.get("results_dir", ckpt_dir / "eval_results"))

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
        }
        from testbed.policies.act.adapter import ACTAdapter
        policy = ACTAdapter.from_checkpoint(
            ckpt_path=ckpt_path,
            policy_config=policy_config,
            norm_stats_path=norm_stats_path,
            temporal_agg=temporal_agg,
        )

    elif policy_class == "DUMMY":
        action_dim = int(policy_cfg.get("action_dim", 4))
        from testbed.policies.dummy.adapter import DummyPolicy
        policy = DummyPolicy(action_dim=action_dim, mode="zero")

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
    )
    metrics = suite.run()

    # save results
    results_dir.mkdir(parents=True, exist_ok=True)
    metrics.to_json(results_dir / "metrics.json")
    EvalMetrics.append_to_csv([metrics], results_dir / "results.csv")
    print(f"\nResults saved to {results_dir}")
