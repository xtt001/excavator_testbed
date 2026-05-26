"""Audit accepted and rejected return windows from a primitive split."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from testbed.data.schema import (
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-audit-return-windows",
        description=(
            "Summarize motion and env-state changes in accepted/rejected return "
            "windows from a V2.4.5 primitive split summary."
        ),
    )
    parser.add_argument(
        "--primitive-root",
        type=Path,
        required=True,
        help="Primitive root containing summary.json and window_manifest.json.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Output JSON path. Defaults to <primitive-root>/return_window_audit.json.",
    )
    parser.add_argument(
        "--tail-len",
        type=int,
        default=512,
        help="Also audit the final N steps of overlong rejected return windows.",
    )
    args = parser.parse_args()

    output_json = args.output_json or (args.primitive_root / "return_window_audit.json")
    payload = audit_return_windows(
        primitive_root=args.primitive_root,
        tail_len=int(args.tail_len),
    )
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output_json": str(output_json), **payload["summary"]}, indent=2))


def audit_return_windows(*, primitive_root: Path, tail_len: int = 512) -> dict[str, Any]:
    primitive_root = Path(primitive_root)
    summary_path = primitive_root / "summary.json"
    manifest_path = primitive_root / "window_manifest.json"
    if not summary_path.exists():
        raise FileNotFoundError(summary_path)
    if not manifest_path.exists():
        raise FileNotFoundError(manifest_path)

    summary = json.loads(summary_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    if not isinstance(manifest, list):
        raise ValueError(f"{manifest_path} must contain a list")

    records: list[dict[str, Any]] = []
    for entry in manifest:
        if str(entry.get("primitive_name")) != "return":
            continue
        records.append(
            _audit_window_record(
                kind="accepted",
                reason="accepted",
                source_episode_path=Path(str(entry["source_episode_path"])),
                start=int(entry["source_start_step"]),
                end=int(entry["source_end_step_exclusive"]),
                source_cycle_id=_safe_int(entry.get("source_cycle_id"), -1),
                details={},
            )
        )

    rejects = list(summary.get("rejects", []) or [])
    for reject in rejects:
        if str(reject.get("primitive_name")) != "return":
            continue
        source_episode_path = _reject_source_path(reject)
        record = _audit_window_record(
            kind="rejected",
            reason=str(reject.get("reason", "unknown")),
            source_episode_path=source_episode_path,
            start=int(reject.get("start_step", 0)),
            end=int(reject.get("end_step_exclusive", 0)),
            source_cycle_id=_safe_int(reject.get("source_cycle_id"), -1),
            details=dict(reject.get("details", {}) or {}),
        )
        records.append(record)
        if (
            str(reject.get("reason")) == "overlong_transition_len"
            and int(tail_len) > 0
            and record.get("window_len", 0) > int(tail_len)
        ):
            end = int(reject.get("end_step_exclusive", 0))
            records.append(
                _audit_window_record(
                    kind=f"rejected_tail{int(tail_len)}",
                    reason="overlong_transition_len_tail",
                    source_episode_path=source_episode_path,
                    start=max(int(reject.get("start_step", 0)), end - int(tail_len)),
                    end=end,
                    source_cycle_id=_safe_int(reject.get("source_cycle_id"), -1),
                    details=dict(reject.get("details", {}) or {}),
                )
            )

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[str(record.get("kind", "unknown"))].append(record)

    return {
        "primitive_root": str(primitive_root),
        "boundary_profile": summary.get("boundary_profile"),
        "reject_counts": summary.get("reject_counts", {}),
        "tail_len": int(tail_len),
        "summary": {
            "accepted_count": len(grouped.get("accepted", [])),
            "rejected_count": len(grouped.get("rejected", [])),
            "rejected_tail_count": len(grouped.get(f"rejected_tail{int(tail_len)}", [])),
        },
        "groups": {
            group: _summarize_group(group_records)
            for group, group_records in sorted(grouped.items())
        },
        "records": records,
    }


def _reject_source_path(reject: dict[str, Any]) -> Path:
    explicit = reject.get("source_episode_path")
    if explicit:
        return Path(str(explicit))
    dataset_dir = Path(str(reject["source_dataset_dir"]))
    episode_id = reject.get("source_episode_id")
    if isinstance(episode_id, str) and episode_id.startswith("episode_"):
        stem = episode_id
    else:
        stem = f"episode_{int(episode_id)}"
    return dataset_dir / f"{stem}.hdf5"


def _audit_window_record(
    *,
    kind: str,
    reason: str,
    source_episode_path: Path,
    start: int,
    end: int,
    source_cycle_id: int,
    details: dict[str, Any],
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "kind": kind,
        "reason": reason,
        "source_episode_path": str(source_episode_path),
        "source_cycle_id": int(source_cycle_id),
        "start_step": int(start),
        "end_step_exclusive": int(end),
        "window_len": int(max(0, end - start)),
        "realign_steps_in_window_count": len(details.get("realign_steps_in_window", []) or []),
    }
    try:
        metrics = _window_metrics(source_episode_path, start=int(start), end=int(end))
        record.update(metrics)
    except Exception as exc:  # pragma: no cover - audit should keep partial results.
        record["error"] = f"{type(exc).__name__}: {exc}"
    return record


def _window_metrics(path: Path, *, start: int, end: int) -> dict[str, Any]:
    with h5py.File(path, "r") as handle:
        action = _read_window(handle, ("action", "actions"), start=start, end=end)
        qpos = _read_window(handle, ("observations/qpos", "qpos"), start=start, end=end)
        qvel = _read_window(handle, ("observations/qvel", "qvel"), start=start, end=end)
        env_state = _read_window(
            handle,
            ("observations/env_state", "env_state"),
            start=start,
            end=end,
            required=False,
        )
        work_stage = _read_window(
            handle,
            ("v2/step/work_stage_id",),
            start=start,
            end=end,
            required=False,
        )

    metrics: dict[str, Any] = {}
    if action.size:
        action = np.asarray(action, dtype=np.float32).reshape((action.shape[0], -1))
        action_norm = np.linalg.norm(action, axis=1)
        metrics.update(
            {
                "action_norm_mean": _finite_mean(action_norm),
                "action_norm_max": _finite_max(action_norm),
                "action_moving_frac": _finite_mean(action_norm > 0.02),
            }
        )
    if qpos.size:
        qpos = np.asarray(qpos, dtype=np.float32).reshape((qpos.shape[0], -1))
        metrics["qpos_total_delta_norm"] = _endpoint_delta_norm(qpos)
        metrics["qpos_path_delta_norm"] = _path_delta_norm(qpos)
    if qvel.size:
        qvel = np.asarray(qvel, dtype=np.float32).reshape((qvel.shape[0], -1))
        qvel_norm = np.linalg.norm(qvel, axis=1)
        metrics["qvel_norm_mean"] = _finite_mean(qvel_norm)
        metrics["qvel_norm_max"] = _finite_max(qvel_norm)
    if env_state.size:
        env_state = np.asarray(env_state, dtype=np.float32)
        metrics.update(_env_state_metrics(env_state))
    if work_stage.size:
        counts = Counter(int(value) for value in np.asarray(work_stage).reshape(-1))
        metrics["work_stage_id_counts"] = {
            str(key): int(value) for key, value in sorted(counts.items())
        }
    return metrics


def _read_window(
    handle: h5py.File,
    names: tuple[str, ...],
    *,
    start: int,
    end: int,
    required: bool = True,
) -> np.ndarray:
    dataset = None
    for name in names:
        if name in handle:
            dataset = handle[name]
            break
    if dataset is None:
        if required:
            raise KeyError(names[0])
        return np.asarray([])
    size = int(dataset.shape[0])
    lo = max(0, min(int(start), size))
    hi = max(lo, min(int(end), size))
    return np.asarray(dataset[lo:hi])


def _env_state_metrics(env_state: np.ndarray) -> dict[str, Any]:
    metrics: dict[str, Any] = {}
    if env_state.ndim != 2:
        return metrics
    columns = {
        "mass": ENV_STATE_MASS_IN_BUCKET_IDX,
        "dig_distance": ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
        "plane_depth": ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
        "local_surface_depth": ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    }
    for name, index in columns.items():
        if env_state.shape[1] <= index:
            continue
        values = np.asarray(env_state[:, index], dtype=np.float32)
        metrics[f"{name}_start"] = _finite_first(values)
        metrics[f"{name}_end"] = _finite_last(values)
        metrics[f"{name}_min"] = _finite_min(values)
        metrics[f"{name}_max"] = _finite_max(values)
        metrics[f"{name}_delta"] = _finite_last(values) - _finite_first(values)
    return metrics


def _summarize_group(records: list[dict[str, Any]]) -> dict[str, Any]:
    numeric_keys = sorted(
        {
            key
            for record in records
            for key, value in record.items()
            if isinstance(value, (int, float)) and math.isfinite(float(value))
        }
    )
    reasons = Counter(str(record.get("reason", "unknown")) for record in records)
    summary: dict[str, Any] = {
        "count": len(records),
        "reason_counts": dict(sorted(reasons.items())),
    }
    for key in numeric_keys:
        values = [float(record[key]) for record in records if _is_finite(record.get(key))]
        if values:
            summary[key] = _stats(values)
    return summary


def _stats(values: list[float]) -> dict[str, float | int]:
    arr = np.asarray(values, dtype=np.float64)
    return {
        "count": int(arr.size),
        "min": float(np.min(arr)),
        "p10": float(np.percentile(arr, 10)),
        "p50": float(np.percentile(arr, 50)),
        "p90": float(np.percentile(arr, 90)),
        "p95": float(np.percentile(arr, 95)),
        "p98": float(np.percentile(arr, 98)),
        "max": float(np.max(arr)),
        "mean": float(np.mean(arr)),
    }


def _endpoint_delta_norm(values: np.ndarray) -> float:
    if values.shape[0] <= 1:
        return 0.0
    return float(np.linalg.norm(values[-1] - values[0]))


def _path_delta_norm(values: np.ndarray) -> float:
    if values.shape[0] <= 1:
        return 0.0
    return float(np.sum(np.linalg.norm(np.diff(values, axis=0), axis=1)))


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _is_finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _finite_first(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=np.float64)
    if values.size <= 0:
        return float("nan")
    return float(values[0])


def _finite_last(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=np.float64)
    if values.size <= 0:
        return float("nan")
    return float(values[-1])


def _finite_mean(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=np.float64)
    if values.size <= 0:
        return float("nan")
    return float(np.nanmean(values))


def _finite_min(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=np.float64)
    if values.size <= 0:
        return float("nan")
    return float(np.nanmin(values))


def _finite_max(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=np.float64)
    if values.size <= 0:
        return float("nan")
    return float(np.nanmax(values))


if __name__ == "__main__":
    main()
