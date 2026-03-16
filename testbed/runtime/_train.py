"""Internal train helper called by Runner.train()."""

from __future__ import annotations

import pickle
from pathlib import Path
from typing import Any

import yaml


def train_policy(config: dict[str, Any]) -> None:
    task_cfg   = config.get("task", {})
    policy_cfg = config.get("policy", {})
    train_cfg  = config.get("train", {})

    policy_class  = policy_cfg.get("class", "ACT").upper()
    task_name     = task_cfg.get("task_name", task_cfg.get("name", config.get("task_name", "")))
    dataset_dir   = Path(task_cfg.get("dataset_dir", config.get("dataset_dir", "data")))
    num_episodes  = task_cfg.get("num_episodes", config.get("num_episodes", 50))
    camera_names  = task_cfg.get("camera_names", config.get("camera_names", []))
    ckpt_dir      = Path(train_cfg.get("ckpt_dir", config.get("ckpt_dir", f"ckpts/{task_name}")))
    equipment_model = task_cfg.get("equipment_model", config.get("equipment_model", "excavator_simple"))

    if policy_class != "ACT":
        raise NotImplementedError(f"Trainer for policy class {policy_class!r} not yet implemented.")

    from testbed.data.dataset import load_data, get_norm_stats
    from testbed.policies.act.trainer import ACTTrainer

    # build policy_config dict for ACTAdapter / detr
    act_params = policy_cfg.get("act_params", {})
    policy_config = {
        "lr":            float(train_cfg.get("lr", 1e-5)),
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

    full_config = {
        "num_epochs":     int(train_cfg.get("num_epochs", 2000)),
        "ckpt_dir":       str(ckpt_dir),
        "seed":           int(train_cfg.get("seed", 0)),
        "task_name":      task_name,
        "resume_ckpt":    train_cfg.get("resume_ckpt"),
        "start_epoch":    train_cfg.get("start_epoch"),
    }

    ckpt_dir.mkdir(parents=True, exist_ok=True)

    # save normalisation stats so trainer can load them
    stats = get_norm_stats(dataset_dir, num_episodes)
    stats_path = ckpt_dir / "dataset_stats.pkl"
    with open(stats_path, "wb") as f:
        pickle.dump(stats, f)
    print(f"Saved normalisation stats to {stats_path}")

    batch_size   = int(train_cfg.get("batch_size", 8))
    num_workers  = int(train_cfg.get("num_workers", 4))
    pf_raw       = train_cfg.get("prefetch_factor", 2)
    prefetch_factor = int(pf_raw) if pf_raw is not None and num_workers > 0 else None
    train_loader, val_loader, _, _ = load_data(
        dataset_dir  = dataset_dir,
        num_episodes = num_episodes,
        camera_names = camera_names,
        batch_size_train   = batch_size,
        batch_size_val     = batch_size,
        num_workers        = num_workers,
        prefetch_factor    = prefetch_factor,
        persistent_workers = bool(train_cfg.get("persistent_workers", True)) and num_workers > 0,
        pin_memory         = bool(train_cfg.get("pin_memory", True)),
    )

    trainer = ACTTrainer(policy_config=policy_config, config=full_config)
    trainer.fit(train_loader, val_loader, full_config)
