"""Offline ACT checkpoint audit for conditioned dig primitives.

The audit compares a dig checkpoint against recorded dig primitive episodes in
two complementary ways:

* teacher-forced first-action inference on recorded observations;
* full ACT chunk inference from selected start steps, compared with the expert
  action suffix that the model is trained to predict.

It is intended to separate shallow live digs caused by the dig checkpoint from
planner handoff, replan, or Unity rollout effects.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import yaml

from testbed.data.dataset import _episode_matches_metadata_filters
from testbed.data.hdf5_io import episode_id_from_path, list_episodes
from testbed.policies.act.inference import (
    build_act_adapter_config,
    load_act_policy,
)

DIG_CUT_TOKEN_KEY = "dig_cut_tokens"
DIG_CUT_TOKEN_PATH = "v2/step/dig_cut_tokens"
DIG_DEPTH_PROFILE_KEY = "dig_depth_profile_tokens_v1"
DIG_DEPTH_PROFILE_PATH = "v2/step/dig_depth_profile_tokens_v1"
DIG_OUTCOME_TARGET_PATH = "v2/step/dig_outcome_targets"


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-audit-dig-ckpt",
        description=(
            "Run offline teacher-forcing and chunk-level inference for a "
            "conditioned dig ACT checkpoint."
        ),
    )
    parser.add_argument("--config", required=True, help="ACT training YAML config.")
    parser.add_argument("--ckpt", required=True, help="policy_best.ckpt to audit.")
    parser.add_argument(
        "--dataset-dir",
        default=None,
        help="Dig primitive dataset root. Defaults to task.dataset_dir in config.",
    )
    parser.add_argument("--output", required=True, help="Output JSON path.")
    parser.add_argument("--device", default=None, help="Override policy device.")
    parser.add_argument(
        "--episode-ids",
        default="",
        help="Comma-separated episode ids to audit. Empty selects filtered episodes.",
    )
    parser.add_argument(
        "--max-episodes",
        type=int,
        default=12,
        help="Maximum filtered episodes to audit when --episode-ids is empty.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=160,
        help="Maximum recorded steps per episode for first-action and scheduled audit.",
    )
    parser.add_argument(
        "--chunk-start-steps",
        default="0",
        help="Comma-separated start steps for full-chunk audit.",
    )
    parser.add_argument(
        "--metadata-filter",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Additional metadata filter. Repeats are allowed.",
    )
    parser.add_argument(
        "--ignore-config-metadata-filters",
        action="store_true",
        help="Do not inherit train.metadata_filters from the YAML config.",
    )
    parser.add_argument(
        "--temporal-agg",
        action="store_true",
        help="Use ACT temporal aggregation in the recorded-stream scheduled audit.",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    config = yaml.safe_load(config_path.read_text()) or {}
    task_cfg = dict(config.get("task", {}) or {})
    policy_cfg = dict(config.get("policy", {}) or {})
    train_cfg = dict(config.get("train", {}) or {})

    dataset_dir = Path(args.dataset_dir or task_cfg["dataset_dir"])
    ckpt_path = Path(args.ckpt)
    low_dim_keys = list(policy_cfg.get("low_dim_keys", ["qpos"]))
    if DIG_CUT_TOKEN_KEY not in low_dim_keys:
        raise ValueError(
            "Dig checkpoint audit requires policy.low_dim_keys to include "
            f"{DIG_CUT_TOKEN_KEY!r}."
        )
    camera_names = list(task_cfg.get("camera_names", ["fpv"]))
    device = str(args.device or policy_cfg.get("device") or train_cfg.get("device") or "cuda")
    metadata_filters = (
        {}
        if bool(args.ignore_config_metadata_filters)
        else dict(train_cfg.get("metadata_filters", {}) or {})
    )
    metadata_filters.update(_parse_metadata_filter_args(args.metadata_filter))

    policy = _load_policy(
        config=config,
        ckpt_path=ckpt_path,
        camera_names=camera_names,
        low_dim_keys=low_dim_keys,
        device=device,
        temporal_agg=bool(args.temporal_agg),
    )
    episode_paths = _select_episode_paths(
        dataset_dir=dataset_dir,
        episode_ids=_parse_int_list(args.episode_ids),
        max_episodes=int(args.max_episodes),
        metadata_filters=metadata_filters,
    )
    if not episode_paths:
        raise FileNotFoundError(
            f"No matching dig episodes found under {dataset_dir} with filters "
            f"{metadata_filters}."
        )

    chunk_start_steps = _parse_int_list(args.chunk_start_steps) or [0]
    episode_records: list[dict[str, Any]] = []
    first_action_records: list[dict[str, Any]] = []
    scheduled_records: list[dict[str, Any]] = []
    chunk_records: list[dict[str, Any]] = []

    for index, episode_path in enumerate(episode_paths):
        print(f"[{index + 1}/{len(episode_paths)}] {episode_path.name}", flush=True)
        payload = _audit_episode(
            episode_path=episode_path,
            policy=policy,
            camera_names=camera_names,
            low_dim_keys=low_dim_keys,
            max_steps=int(args.max_steps),
            chunk_start_steps=chunk_start_steps,
        )
        episode_records.append(payload["episode"])
        first_action_records.extend(payload["first_action_records"])
        scheduled_records.extend(payload["scheduled_records"])
        chunk_records.extend(payload["chunk_records"])

    summary = {
        "first_action": _summarize_action_records(first_action_records),
        "scheduled_recorded_stream": _summarize_action_records(scheduled_records),
        "chunks": _summarize_chunk_records(chunk_records),
        "episodes": _summarize_episode_records(episode_records),
    }
    output = {
        "schema_version": "dig_ckpt_offline_audit_v1",
        "config": str(config_path),
        "checkpoint": str(ckpt_path),
        "dataset_dir": str(dataset_dir),
        "selected_episode_ids": [episode_id_from_path(path) for path in episode_paths],
        "metadata_filters": metadata_filters,
        "low_dim_keys": low_dim_keys,
        "camera_names": camera_names,
        "temporal_agg": bool(args.temporal_agg),
        "max_steps": int(args.max_steps),
        "chunk_start_steps": chunk_start_steps,
        "summary": summary,
        "episodes": episode_records,
        "chunk_records": chunk_records,
        "interpretation_hint": (
            "If chunk-level or first-action predictions diverge on recorded "
            "gold episodes, inspect checkpoint training/data. If recorded "
            "offline predictions track expert but live digs stay shallow, "
            "inspect live observation/action scaling, camera stream, temporal "
            "aggregation, or Unity rollout state."
        ),
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(_jsonable(output), indent=2, sort_keys=True) + "\n")
    print(json.dumps(_jsonable(summary), indent=2, sort_keys=True))
    print(output_path)


def _load_policy(
    *,
    config: dict[str, Any],
    ckpt_path: Path,
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
        norm_stats_path=ckpt_path.parent / "dataset_stats.pkl",
        temporal_agg=bool(temporal_agg),
        device=device,
    )


def _audit_episode(
    *,
    episode_path: Path,
    policy: Any,
    camera_names: list[str],
    low_dim_keys: list[str],
    max_steps: int,
    chunk_start_steps: list[int],
) -> dict[str, Any]:
    episode_id = episode_id_from_path(episode_path)
    with h5py.File(episode_path, "r") as handle:
        actions = np.asarray(handle["action"], dtype=np.float32)
        n_steps = int(actions.shape[0])
        audit_steps = n_steps if max_steps <= 0 else min(n_steps, int(max_steps))
        episode_payload = _build_episode_payload(
            handle=handle,
            episode_path=episode_path,
            episode_id=episode_id,
            n_steps=n_steps,
        )

        first_action_records = []
        for step in range(audit_steps):
            obs = _read_obs_at_step(
                handle=handle,
                step=step,
                camera_names=camera_names,
                low_dim_keys=low_dim_keys,
            )
            pred, outcome = policy.predict_with_outcome(obs)
            first_action_records.append(
                _build_action_record(
                    mode="first_action",
                    episode_id=episode_id,
                    step=step,
                    episode_len=n_steps,
                    pred=np.asarray(pred, dtype=np.float32),
                    expert=actions[step],
                    outcome=outcome,
                )
            )

        scheduled_records = []
        policy.reset()
        for step in range(audit_steps):
            obs = _read_obs_at_step(
                handle=handle,
                step=step,
                camera_names=camera_names,
                low_dim_keys=low_dim_keys,
            )
            pred = np.asarray(policy.predict(obs), dtype=np.float32).reshape(-1)
            scheduled_records.append(
                _build_action_record(
                    mode="scheduled_recorded_stream",
                    episode_id=episode_id,
                    step=step,
                    episode_len=n_steps,
                    pred=pred,
                    expert=actions[step],
                    outcome=None,
                )
            )

        chunk_records = []
        for start_step in chunk_start_steps:
            if start_step < 0 or start_step >= n_steps:
                continue
            obs = _read_obs_at_step(
                handle=handle,
                step=start_step,
                camera_names=camera_names,
                low_dim_keys=low_dim_keys,
            )
            action_chunk = policy.predict_action_chunk(obs)
            pred_chunk = action_chunk.actions
            outcome = action_chunk.outcome
            expert_chunk = actions[start_step : start_step + pred_chunk.shape[0]]
            chunk_records.append(
                _build_chunk_record(
                    episode_id=episode_id,
                    step=start_step,
                    episode_len=n_steps,
                    pred_chunk=pred_chunk[: expert_chunk.shape[0]],
                    expert_chunk=expert_chunk,
                    outcome=outcome,
                    token=np.asarray(obs[DIG_CUT_TOKEN_KEY], dtype=np.float32),
                )
            )

    return {
        "episode": episode_payload,
        "first_action_records": first_action_records,
        "scheduled_records": scheduled_records,
        "chunk_records": chunk_records,
    }


def _read_obs_at_step(
    *,
    handle: h5py.File,
    step: int,
    camera_names: list[str],
    low_dim_keys: list[str],
) -> dict[str, np.ndarray]:
    obs: dict[str, np.ndarray] = {}
    for key in low_dim_keys:
        if key == "qpos":
            obs[key] = handle["observations/qpos"][step].astype(np.float32)
        elif key == "qvel":
            obs[key] = handle["observations/qvel"][step].astype(np.float32)
        elif key == DIG_CUT_TOKEN_KEY:
            if DIG_CUT_TOKEN_PATH not in handle:
                raise KeyError(f"Episode is missing {DIG_CUT_TOKEN_PATH}")
            obs[key] = handle[DIG_CUT_TOKEN_PATH][step].astype(np.float32)
        elif key == DIG_DEPTH_PROFILE_KEY:
            if DIG_DEPTH_PROFILE_PATH not in handle:
                raise KeyError(f"Episode is missing {DIG_DEPTH_PROFILE_PATH}")
            obs[key] = handle[DIG_DEPTH_PROFILE_PATH][step].astype(np.float32)
        else:
            raise ValueError(f"Unsupported low_dim key {key!r} for dig audit.")
    for camera_name in camera_names:
        image_path = f"observations/images/{camera_name}"
        if image_path not in handle:
            raise KeyError(f"Episode is missing {image_path}")
        obs[f"image_{camera_name}"] = handle[image_path][step]
    return obs


def _build_episode_payload(
    *,
    handle: h5py.File,
    episode_path: Path,
    episode_id: int,
    n_steps: int,
) -> dict[str, Any]:
    attrs = dict(handle.attrs)
    if "metadata" in handle:
        attrs.update(dict(handle["metadata"].attrs))
    token0 = (
        np.asarray(handle[DIG_CUT_TOKEN_PATH][0], dtype=np.float32)
        if DIG_CUT_TOKEN_PATH in handle
        else np.zeros(0, dtype=np.float32)
    )
    return {
        "episode_id": int(episode_id),
        "path": str(episode_path),
        "n_steps": int(n_steps),
        "training_tier": _decode_attr(attrs.get("training_tier", "")),
        "source_episode_id": _decode_attr(attrs.get("source_episode_id", "")),
        "source_cycle_id": _decode_attr(attrs.get("source_cycle_id", "")),
        "dominant_removed_depth_cell_id": _attr_float(
            attrs.get("dominant_removed_depth_cell_id", np.nan)
        ),
        "operator_cut_depth_peak_m": _attr_float(
            attrs.get("operator_cut_depth_peak_m", np.nan)
        ),
        "operator_cut_payload_gain_kg": _attr_float(
            attrs.get("operator_cut_payload_gain_kg", np.nan)
        ),
        "payload_gain_kg": _attr_float(attrs.get("payload_gain_kg", np.nan)),
        "peak_bucket_depth_m": _attr_float(attrs.get("peak_bucket_depth_m", np.nan)),
        "dig_cut_token0": _float_list(token0),
    }


def _build_action_record(
    *,
    mode: str,
    episode_id: int,
    step: int,
    episode_len: int,
    pred: np.ndarray,
    expert: np.ndarray,
    outcome: np.ndarray | None,
) -> dict[str, Any]:
    pred_arr = np.asarray(pred, dtype=np.float32).reshape(-1)
    expert_arr = np.asarray(expert, dtype=np.float32).reshape(-1)
    error = pred_arr - expert_arr
    return {
        "mode": str(mode),
        "episode_id": int(episode_id),
        "step": int(step),
        "frame_key": f"{int(episode_id)}:{int(step)}",
        "phase": 0.0 if episode_len <= 1 else float(step) / float(episode_len - 1),
        "pred": pred_arr,
        "expert": expert_arr,
        "error": error,
        "l2": float(np.linalg.norm(error)),
        "outcome": None if outcome is None else np.asarray(outcome, dtype=np.float32),
    }


def _build_chunk_record(
    *,
    episode_id: int,
    step: int,
    episode_len: int,
    pred_chunk: np.ndarray,
    expert_chunk: np.ndarray,
    outcome: np.ndarray | None,
    token: np.ndarray,
) -> dict[str, Any]:
    pred = np.asarray(pred_chunk, dtype=np.float32)
    expert = np.asarray(expert_chunk, dtype=np.float32)
    n = min(pred.shape[0], expert.shape[0])
    pred = pred[:n]
    expert = expert[:n]
    error = pred - expert
    return {
        "episode_id": int(episode_id),
        "step": int(step),
        "phase": 0.0 if episode_len <= 1 else float(step) / float(episode_len - 1),
        "chunk_len": int(n),
        "token": _float_list(token),
        "token_depth_norm": float(token[7]) if token.size > 7 else 0.0,
        "token_payload_norm": float(token[8]) if token.size > 8 else 0.0,
        "pred_action": _vector_stats(pred),
        "expert_action": _vector_stats(expert),
        "pred_minus_expert": _vector_stats(error),
        "l2_mean": float(np.mean(np.linalg.norm(error, axis=1))) if n else 0.0,
        "l2_p90": float(np.percentile(np.linalg.norm(error, axis=1), 90)) if n else 0.0,
        "first25": _summarize_chunk_slice(pred, expert, 0, min(25, n)),
        "first50": _summarize_chunk_slice(pred, expert, 0, min(50, n)),
        "full": _summarize_chunk_slice(pred, expert, 0, n),
        "outcome": None if outcome is None else _float_list(outcome),
    }


def _summarize_chunk_slice(
    pred: np.ndarray,
    expert: np.ndarray,
    start: int,
    end: int,
) -> dict[str, Any]:
    if end <= start:
        return {"count": 0}
    pred_slice = np.asarray(pred[start:end], dtype=np.float32)
    expert_slice = np.asarray(expert[start:end], dtype=np.float32)
    diff = pred_slice - expert_slice
    return {
        "count": int(end - start),
        "pred_action_mean": _float_list(np.mean(pred_slice, axis=0)),
        "expert_action_mean": _float_list(np.mean(expert_slice, axis=0)),
        "pred_minus_expert_mean": _float_list(np.mean(diff, axis=0)),
        "pred_minus_expert_abs_mean": _float_list(np.mean(np.abs(diff), axis=0)),
        "l2_mean": float(np.mean(np.linalg.norm(diff, axis=1))),
    }


def _summarize_action_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {"count": 0}
    pred = np.asarray([record["pred"] for record in records], dtype=np.float32)
    expert = np.asarray([record["expert"] for record in records], dtype=np.float32)
    error = pred - expert
    l2 = np.linalg.norm(error, axis=1)
    early = [record for record in records if float(record["phase"]) < 0.25]
    mid = [
        record
        for record in records
        if 0.25 <= float(record["phase"]) < 0.75
    ]
    late = [record for record in records if float(record["phase"]) >= 0.75]
    return {
        "count": int(len(records)),
        "episode_count": int(len({int(record["episode_id"]) for record in records})),
        "pred_action": _vector_stats(pred),
        "expert_action": _vector_stats(expert),
        "pred_minus_expert": _vector_stats(error),
        "l2_mean": float(np.mean(l2)),
        "l2_p90": float(np.percentile(l2, 90)),
        "early_p0_25": _summarize_action_records_flat(early),
        "mid_p25_75": _summarize_action_records_flat(mid),
        "late_p75_100": _summarize_action_records_flat(late),
    }


def _summarize_action_records_flat(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {"count": 0}
    pred = np.asarray([record["pred"] for record in records], dtype=np.float32)
    expert = np.asarray([record["expert"] for record in records], dtype=np.float32)
    error = pred - expert
    l2 = np.linalg.norm(error, axis=1)
    return {
        "count": int(len(records)),
        "pred_action_mean": _float_list(np.mean(pred, axis=0)),
        "expert_action_mean": _float_list(np.mean(expert, axis=0)),
        "pred_minus_expert_mean": _float_list(np.mean(error, axis=0)),
        "l2_mean": float(np.mean(l2)),
    }


def _summarize_chunk_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {"count": 0}
    return {
        "count": int(len(records)),
        "episode_count": int(len({int(record["episode_id"]) for record in records})),
        "l2_mean": float(np.mean([float(record["l2_mean"]) for record in records])),
        "l2_p90": float(np.percentile([float(record["l2_mean"]) for record in records], 90)),
        "token_depth_norm": _numeric_stats(
            [float(record["token_depth_norm"]) for record in records]
        ),
        "token_payload_norm": _numeric_stats(
            [float(record["token_payload_norm"]) for record in records]
        ),
        "first50_pred_minus_expert_mean": _vector_stats(
            np.asarray(
                [
                    record["first50"].get("pred_minus_expert_mean", [0.0, 0.0, 0.0, 0.0])
                    for record in records
                    if int(record["first50"].get("count", 0)) > 0
                ],
                dtype=np.float32,
            )
        ),
    }


def _summarize_episode_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {"count": 0}
    return {
        "count": int(len(records)),
        "operator_cut_depth_peak_m": _numeric_stats(
            [record["operator_cut_depth_peak_m"] for record in records]
        ),
        "operator_cut_payload_gain_kg": _numeric_stats(
            [record["operator_cut_payload_gain_kg"] for record in records]
        ),
        "payload_gain_kg": _numeric_stats([record["payload_gain_kg"] for record in records]),
        "dominant_removed_depth_cell_id_counts": _counts(
            int(record["dominant_removed_depth_cell_id"])
            for record in records
            if np.isfinite(record["dominant_removed_depth_cell_id"])
        ),
    }


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


def _numeric_stats(values: list[float]) -> dict[str, Any]:
    arr = np.asarray(values, dtype=np.float32)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return {"count": 0}
    return {
        "count": int(arr.size),
        "mean": float(np.mean(arr)),
        "p10": float(np.percentile(arr, 10)),
        "p50": float(np.percentile(arr, 50)),
        "p90": float(np.percentile(arr, 90)),
    }


def _counts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _select_episode_paths(
    *,
    dataset_dir: Path,
    episode_ids: list[int],
    max_episodes: int,
    metadata_filters: dict[str, Any],
) -> list[Path]:
    if episode_ids:
        candidates = [dataset_dir / f"episode_{ep_id}.hdf5" for ep_id in episode_ids]
    else:
        candidates = list_episodes(dataset_dir)
    selected: list[Path] = []
    for path in candidates:
        if not path.exists():
            raise FileNotFoundError(path)
        with h5py.File(path, "r") as handle:
            if metadata_filters and not _episode_matches_metadata_filters(
                handle,
                metadata_filters,
            ):
                continue
            if handle["action"].shape[1] != handle["observations/qpos"].shape[1]:
                continue
        selected.append(path)
        if not episode_ids and max_episodes > 0 and len(selected) >= max_episodes:
            break
    return selected


def _parse_int_list(value: str) -> list[int]:
    if not str(value).strip():
        return []
    return [int(item.strip()) for item in str(value).split(",") if item.strip()]


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


def _decode_attr(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode()
    if isinstance(value, np.generic):
        value = value.item()
    return str(value)


def _attr_float(value: Any) -> float:
    if isinstance(value, np.ndarray):
        value = value.reshape(-1)[0] if value.size else np.nan
    if isinstance(value, np.generic):
        value = value.item()
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _float_list(values: np.ndarray) -> list[float]:
    return [float(value) for value in np.asarray(values, dtype=np.float32).reshape(-1)]


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
