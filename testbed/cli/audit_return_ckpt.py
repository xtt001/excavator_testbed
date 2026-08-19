"""Offline ACT checkpoint audit for conditioned return primitives.

The audit runs a return checkpoint on recorded return episodes with the
recorded observation stream, then repeats inference under controlled
return-start-envelope token variants.  It is meant to separate three cases:

* the checkpoint already diverges on the recorded distribution;
* the checkpoint is sound, but a token/state variant changes behavior;
* the rollout issue is likely in online planner state or handoff logic.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import yaml

from testbed.data.dataset import (
    _episode_matches_metadata_filters,
    _read_return_relocate_tokens_dataset,
)
from testbed.data.hdf5_io import episode_id_from_path, list_episodes
from testbed.data.operator_first_v2_2 import RETURN_START_ENVELOPE_TOKEN_DIM
from testbed.policies.act.inference import (
    build_act_adapter_config,
    load_act_policy,
)

RETURN_START_TOKEN_KEY = "return_start_envelope_tokens_v1"
RETURN_START_TOKEN_PATH = "v2/step/return_start_envelope_tokens_v1"
RETURN_RELOCATE_TOKEN_KEY = "return_relocate_tokens_v1"

DEFAULT_TOKEN_VARIANTS = (
    "original",
    "depth_zero",
    "depth_mid_neutral",
    "contact_zero",
    "spatial_zero",
    "spatial_depth_contact_zero",
    "qpos_envelope_only",
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-audit-return-ckpt",
        description=(
            "Run offline teacher-forcing inference for a conditioned return ACT "
            "checkpoint and compare return_start_envelope token variants."
        ),
    )
    parser.add_argument("--config", required=True, help="ACT training YAML config.")
    parser.add_argument("--ckpt", required=True, help="policy_best.ckpt to audit.")
    parser.add_argument(
        "--dataset-dir",
        default=None,
        help="Return primitive dataset root. Defaults to task.dataset_dir in config.",
    )
    parser.add_argument("--output", required=True, help="Output JSON path.")
    parser.add_argument("--device", default=None, help="Override policy device.")
    parser.add_argument(
        "--max-episodes",
        type=int,
        default=24,
        help="Maximum filtered episodes to audit; <=0 means all filtered episodes.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=0,
        help="Maximum steps per episode; <=0 means the full episode.",
    )
    parser.add_argument(
        "--token-variants",
        default=",".join(DEFAULT_TOKEN_VARIANTS),
        help="Comma-separated token variants to evaluate.",
    )
    parser.add_argument(
        "--metadata-filter",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help=(
            "Additional metadata filter. Repeats are allowed. Defaults also "
            "include train.metadata_filters from the config."
        ),
    )
    parser.add_argument(
        "--ignore-config-metadata-filters",
        action="store_true",
        help="Do not inherit train.metadata_filters from the YAML config.",
    )
    parser.add_argument(
        "--no-temporal-agg",
        action="store_true",
        help="Disable ACT temporal aggregation during inference.",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    config = yaml.safe_load(config_path.read_text()) or {}
    task_cfg = dict(config.get("task", {}) or {})
    policy_cfg = dict(config.get("policy", {}) or {})
    train_cfg = dict(config.get("train", {}) or {})

    dataset_dir = Path(args.dataset_dir or task_cfg["dataset_dir"])
    ckpt_path = Path(args.ckpt)
    ckpt_dir = ckpt_path.parent
    low_dim_keys = list(policy_cfg.get("low_dim_keys", ["qpos"]))
    if RETURN_START_TOKEN_KEY not in low_dim_keys:
        raise ValueError(
            "Return checkpoint audit currently requires policy.low_dim_keys to "
            f"include {RETURN_START_TOKEN_KEY!r}."
        )
    camera_names = list(task_cfg.get("camera_names", ["fpv"]))
    device = str(args.device or policy_cfg.get("device") or train_cfg.get("device") or "cuda")
    token_variants = _parse_token_variants(args.token_variants)
    metadata_filters = (
        {}
        if bool(args.ignore_config_metadata_filters)
        else dict(train_cfg.get("metadata_filters", {}) or {})
    )
    metadata_filters.update(_parse_metadata_filter_args(args.metadata_filter))

    policy = _load_policy(
        config=config,
        ckpt_path=ckpt_path,
        ckpt_dir=ckpt_dir,
        camera_names=camera_names,
        low_dim_keys=low_dim_keys,
        device=device,
        temporal_agg=not bool(args.no_temporal_agg),
    )
    episode_paths = _select_episode_paths(
        dataset_dir=dataset_dir,
        max_episodes=int(args.max_episodes),
        metadata_filters=metadata_filters,
    )
    if not episode_paths:
        raise FileNotFoundError(
            f"No matching return episodes found under {dataset_dir} with filters "
            f"{metadata_filters}."
        )

    records: list[dict[str, Any]] = []
    for episode_index, episode_path in enumerate(episode_paths):
        print(
            f"[{episode_index + 1}/{len(episode_paths)}] {episode_path.name}",
            flush=True,
        )
        records.extend(
            _audit_episode(
                episode_path=episode_path,
                policy=policy,
                camera_names=camera_names,
                low_dim_keys=low_dim_keys,
                token_variants=token_variants,
                max_steps=int(args.max_steps),
            )
        )

    summary = summarize_records(records)
    output = {
        "schema_version": "return_ckpt_offline_audit_v1",
        "config": str(config_path),
        "checkpoint": str(ckpt_path),
        "dataset_dir": str(dataset_dir),
        "selected_episode_ids": [episode_id_from_path(path) for path in episode_paths],
        "metadata_filters": metadata_filters,
        "low_dim_keys": low_dim_keys,
        "camera_names": camera_names,
        "temporal_agg": not bool(args.no_temporal_agg),
        "token_variants": token_variants,
        "record_count": int(len(records)),
        "summary": summary,
        "interpretation_hint": (
            "If original tracks expert but token variants or live-style tokens "
            "diverge, inspect token/env_state/planner generation before blaming "
            "the return primitive boundary. If original diverges on recorded "
            "episodes, inspect checkpoint/data distribution."
        ),
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(_jsonable(output), indent=2, sort_keys=True) + "\n")
    print(json.dumps(_jsonable(summary.get("headline", {})), indent=2, sort_keys=True))
    print(output_path)


def _load_policy(
    *,
    config: dict[str, Any],
    ckpt_path: Path,
    ckpt_dir: Path,
    camera_names: list[str],
    low_dim_keys: list[str],
    device: str,
    temporal_agg: bool,
):
    task_cfg = dict(config.get("task", {}) or {})
    policy_cfg = dict(config.get("policy", {}) or {})
    act_params = dict(policy_cfg.get("act_params", {}) or {})
    outcome_head_cfg = dict(policy_cfg.get("outcome_head") or {})
    equipment_model = str(task_cfg.get("equipment_model", "yulong"))
    episode_len = int(task_cfg.get("episode_len", 512))
    adapter_config = build_act_adapter_config(
        config=config,
        camera_names=camera_names,
        equipment_model=equipment_model,
        max_episode_len=episode_len,
        low_dim_keys=low_dim_keys,
        act_params=act_params,
        outcome_head_config=outcome_head_cfg,
        image_mask_config=dict(policy_cfg.get("image_mask") or {}),
    )
    return load_act_policy(
        ckpt_path=ckpt_path,
        policy_config=adapter_config,
        norm_stats_path=ckpt_dir / "dataset_stats.pkl",
        temporal_agg=bool(temporal_agg),
        device=device,
    )


def _audit_episode(
    *,
    episode_path: Path,
    policy: Any,
    camera_names: list[str],
    low_dim_keys: list[str],
    token_variants: list[str],
    max_steps: int,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    episode_id = episode_id_from_path(episode_path)
    with h5py.File(episode_path, "r") as handle:
        if RETURN_START_TOKEN_PATH not in handle:
            raise KeyError(f"{episode_path} is missing {RETURN_START_TOKEN_PATH}")
        actions = np.asarray(handle["action"], dtype=np.float32)
        n_steps = int(actions.shape[0])
        if max_steps > 0:
            n_steps = min(n_steps, int(max_steps))
        original_tokens = np.asarray(
            handle[RETURN_START_TOKEN_PATH][:n_steps],
            dtype=np.float32,
        )
        for variant in token_variants:
            policy.reset()
            for step in range(n_steps):
                original_token = original_tokens[step]
                token = apply_return_envelope_variant(original_token, variant)
                obs = _read_obs_at_step(
                    handle=handle,
                    step=step,
                    camera_names=camera_names,
                    low_dim_keys=low_dim_keys,
                    return_start_token=token,
                )
                pred = np.asarray(policy.predict(obs), dtype=np.float32).reshape(-1)
                expert = np.asarray(actions[step], dtype=np.float32).reshape(-1)
                records.append(
                    _build_record(
                        variant=variant,
                        episode_id=episode_id,
                        step=step,
                        episode_len=n_steps,
                        pred=pred,
                        expert=expert,
                        original_token=original_token,
                    )
                )
    return records


def _read_obs_at_step(
    *,
    handle: h5py.File,
    step: int,
    camera_names: list[str],
    low_dim_keys: list[str],
    return_start_token: np.ndarray,
) -> dict[str, np.ndarray]:
    obs: dict[str, np.ndarray] = {}
    for key in low_dim_keys:
        if key == "qpos":
            obs[key] = handle["observations/qpos"][step].astype(np.float32)
        elif key == "qvel":
            obs[key] = handle["observations/qvel"][step].astype(np.float32)
        elif key == RETURN_START_TOKEN_KEY:
            obs[key] = np.asarray(return_start_token, dtype=np.float32)
        elif key == RETURN_RELOCATE_TOKEN_KEY:
            obs[key] = _read_return_relocate_tokens_dataset(handle, index=step)
        else:
            raise ValueError(
                f"Unsupported low_dim key {key!r} for return checkpoint audit."
            )
    for camera_name in camera_names:
        image_path = f"observations/images/{camera_name}"
        if image_path not in handle:
            raise KeyError(f"Episode is missing {image_path}")
        obs[f"image_{camera_name}"] = handle[image_path][step]
    return obs


def _build_record(
    *,
    variant: str,
    episode_id: int,
    step: int,
    episode_len: int,
    pred: np.ndarray,
    expert: np.ndarray,
    original_token: np.ndarray,
) -> dict[str, Any]:
    long_norm = float(original_token[0]) if original_token.size > 0 else 0.0
    short_norm = float(original_token[1]) if original_token.size > 1 else 0.0
    return {
        "variant": str(variant),
        "episode_id": int(episode_id),
        "step": int(step),
        "frame_key": f"{int(episode_id)}:{int(step)}",
        "phase": 1.0 if episode_len <= 1 else float(step) / float(episode_len - 1),
        "pred": np.asarray(pred, dtype=np.float32),
        "expert": np.asarray(expert, dtype=np.float32),
        "original_token_depth_m": float(original_token[2])
        if original_token.size > 2
        else 0.0,
        "original_token_entry_norm": float((long_norm**2 + short_norm**2) ** 0.5),
    }


def apply_return_envelope_variant(token: np.ndarray, variant: str) -> np.ndarray:
    """Return a controlled variant of a 18D return-start-envelope token."""
    arr = np.asarray(token, dtype=np.float32).reshape(-1).copy()
    if arr.shape[0] != RETURN_START_ENVELOPE_TOKEN_DIM:
        raise ValueError(
            f"{RETURN_START_TOKEN_KEY} must be {RETURN_START_ENVELOPE_TOKEN_DIM}D, "
            f"got {arr.shape}."
        )
    name = str(variant).strip()
    if name == "original":
        return arr
    if name == "depth_zero":
        arr[[2, 4, 5]] = 0.0
        return arr
    if name == "depth_mid_neutral":
        arr[2] = 0.0
        arr[4] = 0.0
        arr[5] = 0.08
        return arr
    if name == "contact_zero":
        arr[6] = 0.0
        return arr
    if name == "spatial_zero":
        arr[[0, 1]] = 0.0
        return arr
    if name == "spatial_depth_contact_zero":
        arr[0:7] = 0.0
        return arr
    if name == "qpos_envelope_only":
        arr[0:7] = 0.0
        arr[17] = 0.0
        return arr
    raise ValueError(f"Unknown return token variant {variant!r}.")


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    variants = sorted({str(record["variant"]) for record in records})
    baseline = {
        str(record["frame_key"]): np.asarray(record["pred"], dtype=np.float32)
        for record in records
        if record["variant"] == "original"
    }
    subset_predicates = _subset_predicates()
    by_variant: dict[str, Any] = {}
    for variant in variants:
        variant_records = [
            record for record in records if str(record["variant"]) == variant
        ]
        by_subset: dict[str, Any] = {}
        for subset_name, predicate in subset_predicates.items():
            subset_records = [record for record in variant_records if predicate(record)]
            by_subset[subset_name] = _summarize_subset(
                subset_records,
                baseline=baseline,
                include_delta=(variant != "original"),
            )
        by_variant[variant] = by_subset
    return {
        "headline": _build_headline(by_variant),
        "variants": by_variant,
    }


def _subset_predicates() -> dict[str, Callable[[dict[str, Any]], bool]]:
    return {
        "all": lambda record: True,
        "early_p0_25": lambda record: float(record["phase"]) < 0.25,
        "mid_p25_75": lambda record: 0.25 <= float(record["phase"]) < 0.75,
        "late_p75_100": lambda record: float(record["phase"]) >= 0.75,
        "late_depth_gt_0p08": lambda record: (
            float(record["phase"]) >= 0.75
            and float(record["original_token_depth_m"]) > 0.08
        ),
        "late_near_entry_le_1p2": lambda record: (
            float(record["phase"]) >= 0.75
            and float(record["original_token_entry_norm"]) <= 1.2
        ),
    }


def _summarize_subset(
    records: list[dict[str, Any]],
    *,
    baseline: dict[str, np.ndarray],
    include_delta: bool,
) -> dict[str, Any]:
    if not records:
        return {"count": 0}
    pred = np.asarray([record["pred"] for record in records], dtype=np.float32)
    expert = np.asarray([record["expert"] for record in records], dtype=np.float32)
    error = pred - expert
    result: dict[str, Any] = {
        "count": int(len(records)),
        "episode_count": int(len({int(record["episode_id"]) for record in records})),
        "pred_action": _vector_stats(pred),
        "expert_action": _vector_stats(expert),
        "pred_minus_expert": _vector_stats(error),
        "pred_l2_error_mean": float(np.mean(np.linalg.norm(error, axis=1))),
        "pred_l2_error_p90": float(np.percentile(np.linalg.norm(error, axis=1), 90)),
    }
    if pred.shape[1] > 2:
        result["pred_action_dim2_mean"] = float(np.mean(pred[:, 2]))
        result["pred_action_dim2_negative_frac_lt_-0p05"] = _fraction(
            pred[:, 2] < -0.05
        )
    if pred.shape[1] > 3:
        result["pred_action_dim3_negative_frac_lt_-0p03"] = _fraction(
            pred[:, 3] < -0.03
        )
    if include_delta:
        paired_delta = []
        for record in records:
            base_pred = baseline.get(str(record["frame_key"]))
            if base_pred is None:
                continue
            paired_delta.append(np.asarray(record["pred"], dtype=np.float32) - base_pred)
        if paired_delta:
            delta = np.asarray(paired_delta, dtype=np.float32)
            delta_norm = np.linalg.norm(delta, axis=1)
            result["delta_vs_original"] = {
                "action_delta": _vector_stats(delta),
                "l2_mean": float(np.mean(delta_norm)),
                "l2_p90": float(np.percentile(delta_norm, 90)),
                "abs_max": float(np.max(np.abs(delta))),
            }
    return result


def _build_headline(by_variant: dict[str, Any]) -> dict[str, Any]:
    headline: dict[str, Any] = {}
    for variant, payload in by_variant.items():
        late = dict(payload.get("late_p75_100") or {})
        if not late or int(late.get("count", 0)) <= 0:
            continue
        headline[variant] = {
            "late_count": int(late["count"]),
            "late_pred_l2_error_mean": late.get("pred_l2_error_mean"),
            "late_pred_action_dim2_mean": late.get("pred_action_dim2_mean"),
            "late_dim2_negative_frac_lt_-0p05": late.get(
                "pred_action_dim2_negative_frac_lt_-0p05"
            ),
            "late_delta_vs_original_l2_mean": (
                late.get("delta_vs_original", {}) or {}
            ).get("l2_mean"),
        }
    return headline


def _vector_stats(values: np.ndarray) -> dict[str, Any]:
    arr = np.asarray(values, dtype=np.float32)
    if arr.size == 0:
        return {"count": 0}
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    return {
        "count": int(arr.shape[0]),
        "mean": _float_list(np.mean(arr, axis=0)),
        "std": _float_list(np.std(arr, axis=0)),
        "p10": _float_list(np.percentile(arr, 10, axis=0)),
        "p50": _float_list(np.percentile(arr, 50, axis=0)),
        "p90": _float_list(np.percentile(arr, 90, axis=0)),
    }


def _fraction(mask: np.ndarray) -> float:
    arr = np.asarray(mask, dtype=bool).reshape(-1)
    if arr.size == 0:
        return 0.0
    return float(np.mean(arr))


def _float_list(values: np.ndarray) -> list[float]:
    return [float(value) for value in np.asarray(values).reshape(-1)]


def _parse_token_variants(value: str) -> list[str]:
    variants = [item.strip() for item in str(value).split(",") if item.strip()]
    if not variants:
        raise ValueError("At least one token variant is required.")
    for variant in variants:
        if variant not in DEFAULT_TOKEN_VARIANTS:
            raise ValueError(
                f"Unknown token variant {variant!r}. Supported: "
                f"{', '.join(DEFAULT_TOKEN_VARIANTS)}"
            )
    if "original" not in variants:
        variants.insert(0, "original")
    return variants


def _parse_metadata_filter_args(values: list[str]) -> dict[str, str]:
    filters: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"metadata filters must be KEY=VALUE, got {value!r}")
        key, expected = value.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"metadata filter has empty key: {value!r}")
        filters[key] = expected.strip()
    return filters


def _select_episode_paths(
    *,
    dataset_dir: Path,
    max_episodes: int,
    metadata_filters: dict[str, Any],
) -> list[Path]:
    selected: list[Path] = []
    for path in list_episodes(dataset_dir):
        with h5py.File(path, "r") as handle:
            if metadata_filters and not _episode_matches_metadata_filters(
                handle,
                metadata_filters,
            ):
                continue
            if handle["action"].shape[1] != handle["observations/qpos"].shape[1]:
                continue
        selected.append(path)
        if max_episodes > 0 and len(selected) >= max_episodes:
            break
    return selected


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return _jsonable(value.tolist())
    if isinstance(value, np.generic):
        return value.item()
    return value


if __name__ == "__main__":
    main()
