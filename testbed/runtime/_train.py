"""Internal train helper called by Runner.train()."""

from __future__ import annotations

import copy
import datetime
import pickle
from pathlib import Path
from typing import Any

import torch

from testbed.data.operator_first_v2_2 import (
    DIG_CUT_TOKEN_DIM,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_TARGET_TOKEN_DIM,
)
from testbed.data.v2_1 import GOAL_TOKEN_DIM
from testbed.planner.cell_entry import CELL_ENTRY_TOKEN_DIM


def train_policy(config: dict[str, Any]) -> None:
    task_cfg   = config.get("task", {})
    policy_cfg = config.get("policy", {})
    train_cfg  = config.get("train", {})

    policy_class  = str(policy_cfg.get("class", policy_cfg.get("name", "ACT"))).upper()
    task_name     = task_cfg.get("task_name", task_cfg.get("name", config.get("task_name", "")))
    dataset_dir   = Path(task_cfg.get("dataset_dir", config.get("dataset_dir", "data")))
    num_episodes_raw = task_cfg.get("num_episodes", config.get("num_episodes"))
    num_episodes  = 0 if num_episodes_raw is None else int(num_episodes_raw)
    episode_len   = int(task_cfg.get("episode_len", config.get("episode_len", 400)))
    camera_names  = task_cfg.get("camera_names", config.get("camera_names", []))
    low_dim_keys  = list(policy_cfg.get("low_dim_keys", ["qpos"]))
    supervision_keys = list(
        policy_cfg.get("supervision_keys", train_cfg.get("supervision_keys", []))
        or []
    )
    image_mask_config = copy.deepcopy(
        policy_cfg.get("image_mask", task_cfg.get("image_mask", {}))
    )
    ckpt_dir      = Path(train_cfg.get("ckpt_dir", config.get("ckpt_dir", f"ckpts/{task_name}")))
    equipment_model = task_cfg.get("equipment_model", config.get("equipment_model", "excavator_simple"))
    device        = str(train_cfg.get("device", policy_cfg.get("device", "cuda")))
    split_seed_raw = train_cfg.get("split_seed")
    split_seed = int(train_cfg.get("seed", 0) if split_seed_raw is None else split_seed_raw)
    train_split_ratio = float(train_cfg.get("train_split_ratio", 0.8))
    reuse_split = bool(train_cfg.get("reuse_split", True))
    split_path = Path(train_cfg.get("split_path", ckpt_dir / "train_val_split.yaml"))
    metadata_filters = dict(
        train_cfg.get("metadata_filters", task_cfg.get("metadata_filters", {})) or {}
    )

    if policy_class != "ACT":
        raise NotImplementedError(f"Trainer for policy class {policy_class!r} not yet implemented.")

    from testbed.data.dataset import load_data
    from testbed.policies.act.trainer import ACTTrainer
    from testbed.runtime.run_metadata import (
        build_train_run_metadata,
        write_json,
        write_resolved_config,
    )

    # build policy_config dict for ACTAdapter / detr
    act_params = policy_cfg.get("act_params", {})
    outcome_head_cfg = dict(policy_cfg.get("outcome_head") or {})
    outcome_head_enabled = bool(outcome_head_cfg.get("enabled", False))
    outcome_dim = int(
        outcome_head_cfg.get(
            "dim",
            10 if outcome_head_enabled or supervision_keys else 0,
        )
    )
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
        "low_dim_keys":  low_dim_keys,
        "supervision_keys": supervision_keys,
        "state_dim":     _resolve_low_dim_state_dim(low_dim_keys, equipment_model),
        "image_mask":    image_mask_config,
        "outcome_head": outcome_head_cfg,
        "outcome_dim": outcome_dim if outcome_head_enabled else 0,
        "outcome_action_horizon": int(
            outcome_head_cfg.get("action_horizon", act_params.get("chunk_size", 100))
        ),
        "outcome_hidden_dim": outcome_head_cfg.get("hidden_dim"),
    }

    full_config = {
        "num_epochs":     int(train_cfg.get("num_epochs", 2000)),
        "ckpt_dir":       str(ckpt_dir),
        "seed":           int(train_cfg.get("seed", 0)),
        "task_name":      task_name,
        "device":         device,
        "resume_ckpt":    train_cfg.get("resume_ckpt"),
        "resume_optimizer": bool(train_cfg.get("resume_optimizer", True)),
        "reset_best_on_resume": bool(train_cfg.get("reset_best_on_resume", False)),
        "start_epoch":    train_cfg.get("start_epoch"),
        "val_every":      int(train_cfg.get("val_every", 1)),
        "save_latest_every": int(train_cfg.get("save_latest_every", 1)),
        "checkpoint_every": int(train_cfg.get("checkpoint_every", 100)),
        "plot_every":     int(train_cfg.get("plot_every", train_cfg.get("checkpoint_every", 100))),
        "keep_only_best_ckpt": bool(train_cfg.get("keep_only_best_ckpt", False)),
        "amp":            bool(train_cfg.get("amp", False)),
        "amp_dtype":      str(train_cfg.get("amp_dtype", "auto")),
        "cudnn_benchmark": bool(train_cfg.get("cudnn_benchmark", True)),
        "allow_tf32":     bool(train_cfg.get("allow_tf32", True)),
        "matmul_precision": str(train_cfg.get("matmul_precision", "high")),
        "split_seed":     split_seed,
        "train_split_ratio": train_split_ratio,
        "reuse_split":    reuse_split,
        "split_path":     str(split_path),
        "supervision_keys": supervision_keys,
        "outcome_head": outcome_head_cfg,
        "metadata_filters": metadata_filters,
    }

    ckpt_dir.mkdir(parents=True, exist_ok=True)
    _configure_torch_performance(train_cfg=train_cfg, device=device)

    batch_size   = int(train_cfg.get("batch_size", 8))
    num_workers  = int(train_cfg.get("num_workers", 4))
    pf_raw       = train_cfg.get("prefetch_factor", 2)
    prefetch_factor = int(pf_raw) if pf_raw is not None and num_workers > 0 else None
    train_loader, val_loader, norm_stats, _, split_info = load_data(
        dataset_dir  = dataset_dir,
        num_episodes = num_episodes,
        camera_names = camera_names,
        episode_len  = episode_len,
        batch_size_train   = batch_size,
        batch_size_val     = batch_size,
        num_workers        = num_workers,
        prefetch_factor    = prefetch_factor,
        persistent_workers = bool(train_cfg.get("persistent_workers", True)) and num_workers > 0,
        pin_memory         = bool(train_cfg.get("pin_memory", True)),
        split_seed         = split_seed,
        train_split_ratio  = train_split_ratio,
        split_path         = split_path,
        reuse_split        = reuse_split,
        low_dim_keys       = low_dim_keys,
        supervision_keys   = supervision_keys,
        metadata_filters   = metadata_filters,
        image_mask_config  = image_mask_config,
        hdf5_cache_size    = int(train_cfg.get("hdf5_cache_size", 0)),
    )

    # save normalisation stats so trainer can load them
    stats_path = ckpt_dir / "dataset_stats.pkl"
    with open(stats_path, "wb") as f:
        pickle.dump(norm_stats, f)
    print(f"Saved normalisation stats to {stats_path}")

    resolved_config = _build_resolved_train_config(
        config=config,
        dataset_dir=dataset_dir,
        ckpt_dir=ckpt_dir,
        split_path=split_path,
        full_config=full_config,
    )
    resolved_config_path = write_resolved_config(ckpt_dir / "resolved_config.yaml", resolved_config)
    run_metadata = build_train_run_metadata(
        dataset_dir=dataset_dir,
        ckpt_dir=ckpt_dir,
        resolved_config_path=resolved_config_path,
        dataset_stats_path=stats_path,
        split_info=split_info,
        policy_class=policy_class,
        task_name=task_name,
        device=device,
    )
    run_metadata["status"] = "started"
    run_metadata_path = write_json(ckpt_dir / "run_metadata.json", run_metadata)
    print(f"Saved resolved config to {resolved_config_path}")
    print(f"Saved run metadata to {run_metadata_path}")

    trainer = ACTTrainer(policy_config=policy_config, config=full_config)
    try:
        best_epoch, best_val_loss, _ = trainer.fit(train_loader, val_loader, full_config)
    except Exception as exc:
        run_metadata["status"] = "failed"
        run_metadata["completed_at"] = datetime.datetime.utcnow().isoformat()
        run_metadata["error"] = f"{type(exc).__name__}: {exc}"
        write_json(run_metadata_path, run_metadata)
        raise

    run_metadata["status"] = "completed"
    run_metadata["completed_at"] = datetime.datetime.utcnow().isoformat()
    run_metadata["training_result"] = {
        "best_epoch": int(best_epoch),
        "best_val_loss": float(best_val_loss),
    }
    write_json(run_metadata_path, run_metadata)


def _build_resolved_train_config(
    *,
    config: dict[str, Any],
    dataset_dir: Path,
    ckpt_dir: Path,
    split_path: Path,
    full_config: dict[str, Any],
) -> dict[str, Any]:
    resolved = copy.deepcopy(config)
    task_cfg = resolved.setdefault("task", {})
    train_cfg = resolved.setdefault("train", {})

    task_cfg["dataset_dir"] = str(dataset_dir)
    policy_cfg = resolved.setdefault("policy", {})
    policy_cfg["supervision_keys"] = list(full_config.get("supervision_keys", []))
    if full_config.get("outcome_head"):
        policy_cfg["outcome_head"] = copy.deepcopy(full_config["outcome_head"])
    train_cfg["ckpt_dir"] = str(ckpt_dir)
    train_cfg["split_path"] = str(split_path)
    train_cfg["split_seed"] = int(full_config["split_seed"])
    train_cfg["train_split_ratio"] = float(full_config["train_split_ratio"])
    train_cfg["reuse_split"] = bool(full_config["reuse_split"])
    train_cfg["metadata_filters"] = copy.deepcopy(
        full_config.get("metadata_filters", {})
    )
    train_cfg["val_every"] = int(full_config["val_every"])
    train_cfg["save_latest_every"] = int(full_config["save_latest_every"])
    train_cfg["checkpoint_every"] = int(full_config["checkpoint_every"])
    train_cfg["plot_every"] = int(full_config["plot_every"])
    train_cfg["keep_only_best_ckpt"] = bool(full_config["keep_only_best_ckpt"])
    train_cfg["amp"] = bool(full_config["amp"])
    train_cfg["amp_dtype"] = str(full_config["amp_dtype"])
    train_cfg["cudnn_benchmark"] = bool(full_config["cudnn_benchmark"])
    train_cfg["allow_tf32"] = bool(full_config["allow_tf32"])
    train_cfg["matmul_precision"] = str(full_config["matmul_precision"])
    return resolved


def _configure_torch_performance(
    *,
    train_cfg: dict[str, Any],
    device: str,
) -> None:
    if not str(device).startswith("cuda") or not torch.cuda.is_available():
        return
    torch.backends.cudnn.benchmark = bool(train_cfg.get("cudnn_benchmark", True))
    allow_tf32 = bool(train_cfg.get("allow_tf32", True))
    torch.backends.cuda.matmul.allow_tf32 = allow_tf32
    torch.backends.cudnn.allow_tf32 = allow_tf32
    precision = str(train_cfg.get("matmul_precision", "high"))
    if precision:
        torch.set_float32_matmul_precision(precision)


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
        "return_target_tokens": _resolve_single_low_dim_dim(
            "return_target_tokens", equipment_model
        ),
        "return_start_envelope_tokens_v1": _resolve_single_low_dim_dim(
            "return_start_envelope_tokens_v1", equipment_model
        ),
    }
    return int(sum(dims[key] for key in low_dim_keys))


def _resolve_single_low_dim_dim(key: str, equipment_model: str) -> int:
    equipment_model = str(equipment_model).lower()
    if key == "goal_tokens":
        return int(GOAL_TOKEN_DIM)
    if key == "cell_entry_tokens":
        return int(CELL_ENTRY_TOKEN_DIM)
    if key == "dig_cut_tokens":
        return int(DIG_CUT_TOKEN_DIM)
    if key == "return_target_tokens":
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
