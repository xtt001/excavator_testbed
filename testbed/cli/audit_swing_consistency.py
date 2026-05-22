"""Audit old YuLong recordings for swing consistency and filter windows."""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from testbed.data.hdf5_io import list_episodes, read_episode
from testbed.data.vds import write_lineage_json, write_vds_episode


SWING_AXIS = 0
DIG_CONTACT_IDX = 61
DUMP_CONTACT_IDX = 62
HARD_COLLISION_IDX = 63


@dataclass(frozen=True)
class AuditConfig:
    warning_qvel_action_threshold: float
    severe_qvel_action_threshold: float
    warning_qvel_jump_threshold: float
    severe_qvel_jump_threshold: float
    severe_qpos_delta_threshold: float
    reject_padding_steps: int
    min_clean_steps: int


@dataclass(frozen=True)
class EpisodeAudit:
    episode_path: Path
    episode_id: str
    steps: int
    reject_intervals: list[dict[str, Any]]
    clean_intervals: list[dict[str, int]]
    stats: dict[str, Any]


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-audit-swing-consistency",
        description=(
            "Audit YuLong raw episodes for swing qvel/action/position anomalies. "
            "Optionally filter an existing primitive VDS root by removing windows "
            "that overlap severe swing anomaly intervals."
        ),
    )
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for audit JSON/JSONL outputs.",
    )
    parser.add_argument(
        "--primitive-root",
        type=Path,
        default=None,
        help="Existing primitive VDS root with window_manifest.json to filter.",
    )
    parser.add_argument(
        "--filtered-primitive-root",
        type=Path,
        default=None,
        help="Optional output primitive VDS root containing only accepted windows.",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--warning-qvel-action-threshold", type=float, default=0.35)
    parser.add_argument("--severe-qvel-action-threshold", type=float, default=0.75)
    parser.add_argument("--warning-qvel-jump-threshold", type=float, default=0.35)
    parser.add_argument("--severe-qvel-jump-threshold", type=float, default=0.60)
    parser.add_argument("--severe-qpos-delta-threshold", type=float, default=0.02)
    parser.add_argument("--reject-padding-steps", type=int, default=120)
    parser.add_argument("--min-clean-steps", type=int, default=250)
    args = parser.parse_args()

    raw_dir = args.raw_dir.expanduser().resolve()
    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir is not None
        else (Path("runs/diagnostics") / f"{raw_dir.name}_swing_audit").resolve()
    )
    config = AuditConfig(
        warning_qvel_action_threshold=float(args.warning_qvel_action_threshold),
        severe_qvel_action_threshold=float(args.severe_qvel_action_threshold),
        warning_qvel_jump_threshold=float(args.warning_qvel_jump_threshold),
        severe_qvel_jump_threshold=float(args.severe_qvel_jump_threshold),
        severe_qpos_delta_threshold=float(args.severe_qpos_delta_threshold),
        reject_padding_steps=max(0, int(args.reject_padding_steps)),
        min_clean_steps=max(1, int(args.min_clean_steps)),
    )

    if output_dir.exists() and args.overwrite:
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    audits = [_audit_episode(path, config=config) for path in list_episodes(raw_dir)]
    _write_episode_outputs(output_dir, raw_dir=raw_dir, audits=audits, config=config)

    primitive_payload = None
    if args.primitive_root is not None:
        primitive_root = args.primitive_root.expanduser().resolve()
        filtered_root = (
            args.filtered_primitive_root.expanduser().resolve()
            if args.filtered_primitive_root is not None
            else None
        )
        if filtered_root is not None and filtered_root.exists() and args.overwrite:
            shutil.rmtree(filtered_root)
        primitive_payload = _filter_primitives(
            primitive_root=primitive_root,
            filtered_root=filtered_root,
            output_dir=output_dir,
            audits=audits,
            config=config,
        )

    summary = _summary_payload(
        raw_dir=raw_dir,
        output_dir=output_dir,
        audits=audits,
        config=config,
        primitive_payload=primitive_payload,
    )
    _write_json(output_dir / "summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))


def _audit_episode(path: Path, *, config: AuditConfig) -> EpisodeAudit:
    episode = read_episode(path, load_images=False)
    qpos = np.asarray(episode["qpos"], dtype=np.float32)
    qvel = np.asarray(episode["qvel"], dtype=np.float32)
    actions = np.asarray(episode["actions"], dtype=np.float32)
    env_state = episode.get("env_state")
    metadata = episode.get("metadata", {})
    episode_id = _episode_id(path, metadata)
    steps = int(min(len(qpos), len(qvel), len(actions)))

    if steps == 0:
        return EpisodeAudit(
            episode_path=path,
            episode_id=episode_id,
            steps=0,
            reject_intervals=[],
            clean_intervals=[],
            stats={"error": "empty_episode"},
        )

    swing_qpos = qpos[:steps, SWING_AXIS]
    swing_qvel = qvel[:steps, SWING_AXIS]
    swing_action = actions[:steps, SWING_AXIS]
    qvel_action_abs = np.abs(swing_qvel - swing_action)
    qvel_jump_abs = _prepend_zero(np.abs(np.diff(swing_qvel)))
    qpos_delta_abs = _prepend_zero(np.abs(np.diff(swing_qpos)))
    contact = _contact_mask(env_state, steps)
    hard_collision = _hard_collision(env_state, steps)

    severe_masks = {
        "severe_qvel_action_mismatch": qvel_action_abs
        >= config.severe_qvel_action_threshold,
        "severe_qvel_jump": qvel_jump_abs >= config.severe_qvel_jump_threshold,
        "severe_qpos_delta": qpos_delta_abs >= config.severe_qpos_delta_threshold,
    }
    warning_masks = {
        "warning_qvel_action_mismatch": qvel_action_abs
        >= config.warning_qvel_action_threshold,
        "warning_qvel_jump": qvel_jump_abs >= config.warning_qvel_jump_threshold,
    }

    reject_points: dict[int, set[str]] = defaultdict(set)
    for reason, mask in severe_masks.items():
        for index in np.flatnonzero(mask):
            reject_points[int(index)].add(reason)
            if contact[int(index)]:
                reject_points[int(index)].add("contact_active")
            if hard_collision[int(index)]:
                reject_points[int(index)].add("hard_collision_active")

    reject_intervals = _points_to_intervals(
        reject_points,
        steps=steps,
        padding=config.reject_padding_steps,
    )
    clean_intervals = _complement_intervals(
        reject_intervals,
        steps=steps,
        min_len=config.min_clean_steps,
    )

    stats = {
        "max_abs_swing_qvel_action_residual": _float(np.max(qvel_action_abs)),
        "p99_abs_swing_qvel_action_residual": _float(np.percentile(qvel_action_abs, 99)),
        "max_abs_swing_qvel_jump": _float(np.max(qvel_jump_abs)),
        "p99_abs_swing_qvel_jump": _float(np.percentile(qvel_jump_abs, 99)),
        "max_abs_swing_qpos_delta": _float(np.max(qpos_delta_abs)),
        "p99_abs_swing_qpos_delta": _float(np.percentile(qpos_delta_abs, 99)),
        "warning_counts": {
            reason: int(np.sum(mask)) for reason, mask in warning_masks.items()
        },
        "severe_counts": {
            reason: int(np.sum(mask)) for reason, mask in severe_masks.items()
        },
        "reject_step_count_with_padding": int(
            sum(interval["end_step_exclusive"] - interval["start_step"] for interval in reject_intervals)
        ),
        "clean_step_count": int(
            sum(interval["end_step_exclusive"] - interval["start_step"] for interval in clean_intervals)
        ),
    }
    return EpisodeAudit(
        episode_path=path,
        episode_id=episode_id,
        steps=steps,
        reject_intervals=reject_intervals,
        clean_intervals=clean_intervals,
        stats=stats,
    )


def _filter_primitives(
    *,
    primitive_root: Path,
    filtered_root: Path | None,
    output_dir: Path,
    audits: list[EpisodeAudit],
    config: AuditConfig,
) -> dict[str, Any]:
    manifest_path = primitive_root / "window_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(manifest_path)
    with manifest_path.open("r", encoding="utf-8") as f:
        manifest = json.load(f)

    intervals_by_episode = {
        audit.episode_id: audit.reject_intervals for audit in audits
    }
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    next_id_by_primitive: dict[str, int] = defaultdict(int)

    for record in manifest:
        episode_id = _normalise_episode_id(record.get("source_episode_id", ""))
        start = int(record.get("source_start_step", 0))
        end = int(record.get("source_end_step_exclusive", start))
        overlapping = _overlapping_intervals(
            intervals_by_episode.get(episode_id, []),
            start=start,
            end=end,
        )
        record = dict(record)
        record["swing_audit_overlap_count"] = len(overlapping)
        record["swing_audit_overlaps"] = overlapping
        if overlapping:
            record["swing_audit_status"] = "rejected"
            record["swing_audit_reject_reason"] = "overlaps_severe_swing_interval"
            rejected.append(record)
            continue

        primitive = str(record.get("primitive_name", "unknown"))
        new_id = next_id_by_primitive[primitive]
        next_id_by_primitive[primitive] += 1
        record["swing_audit_status"] = "accepted"
        record["swing_audit_source_primitive_episode_id"] = int(
            record.get("primitive_episode_id", new_id)
        )
        record["primitive_episode_id"] = int(new_id)
        if filtered_root is not None:
            out_path = filtered_root / primitive / f"episode_{new_id}.hdf5"
            _write_filtered_primitive_episode(
                primitive_root=primitive_root,
                record=record,
                output_path=out_path,
                config=config,
            )
            record["output_episode_path"] = str(out_path)
        accepted.append(record)

    _write_json(output_dir / "accepted_window_manifest.json", accepted)
    _write_json(output_dir / "rejected_window_manifest.json", rejected)
    if filtered_root is not None:
        _write_json(filtered_root / "window_manifest.json", accepted)
        write_lineage_json(
            filtered_root,
            builder="tb-audit-swing-consistency",
            storage_mode="vds",
            source_roots=[primitive_root],
            extra={
                "swing_audit_config": _config_payload(config),
                "accepted_window_count": len(accepted),
                "rejected_window_count": len(rejected),
                "audit_output_dir": str(output_dir),
            },
        )

    payload = {
        "primitive_root": str(primitive_root),
        "filtered_primitive_root": "" if filtered_root is None else str(filtered_root),
        "accepted_window_count": len(accepted),
        "rejected_window_count": len(rejected),
        "accepted_by_primitive": dict(Counter(r.get("primitive_name", "") for r in accepted)),
        "rejected_by_primitive": dict(Counter(r.get("primitive_name", "") for r in rejected)),
        "rejected_by_training_tier": dict(Counter(r.get("training_tier", "") for r in rejected)),
    }
    _write_json(output_dir / "primitive_filter_summary.json", payload)
    return payload


def _write_filtered_primitive_episode(
    *,
    primitive_root: Path,
    record: dict[str, Any],
    output_path: Path,
    config: AuditConfig,
) -> None:
    primitive = str(record.get("primitive_name", "unknown"))
    source_primitive_id = int(record.get("swing_audit_source_primitive_episode_id", 0))
    source_primitive_path = primitive_root / primitive / f"episode_{source_primitive_id}.hdf5"
    if not source_primitive_path.exists():
        raise FileNotFoundError(source_primitive_path)

    with h5py.File(source_primitive_path, "r") as f:
        metadata = _read_attrs(f["metadata"].attrs)

    source_path = Path(str(metadata.get("vds_source_abs_path", "")))
    if not source_path.exists():
        fallback = metadata.get("source_episode_path")
        source_path = Path(str(fallback)) if fallback else source_primitive_path
    if not source_path.exists():
        raise FileNotFoundError(
            f"Cannot resolve source for {source_primitive_path}: {source_path}"
        )

    start = int(metadata.get("vds_source_start_step", metadata.get("source_start_step", 0)))
    end = int(
        metadata.get(
            "vds_source_end_step_exclusive",
            metadata.get("source_end_step_exclusive", start),
        )
    )
    metadata.update(
        {
            "primitive_episode_id": int(record["primitive_episode_id"]),
            "swing_audit_status": "accepted",
            "swing_audit_source_primitive_episode_id": source_primitive_id,
            "swing_audit_reject_padding_steps": int(config.reject_padding_steps),
            "swing_audit_severe_qvel_action_threshold": float(
                config.severe_qvel_action_threshold
            ),
            "swing_audit_severe_qvel_jump_threshold": float(
                config.severe_qvel_jump_threshold
            ),
        }
    )
    write_vds_episode(
        output_path,
        source_path=source_path,
        crop=slice(start, end),
        metadata=metadata,
    )


def _write_episode_outputs(
    output_dir: Path,
    *,
    raw_dir: Path,
    audits: list[EpisodeAudit],
    config: AuditConfig,
) -> None:
    intervals_path = output_dir / "reject_intervals.jsonl"
    with intervals_path.open("w", encoding="utf-8") as f:
        for audit in audits:
            for interval in audit.reject_intervals:
                payload = {
                    "episode_id": audit.episode_id,
                    "episode_path": str(audit.episode_path),
                    **interval,
                }
                f.write(json.dumps(_jsonable(payload), sort_keys=True) + "\n")

    clean_path = output_dir / "clean_intervals.jsonl"
    with clean_path.open("w", encoding="utf-8") as f:
        for audit in audits:
            for interval in audit.clean_intervals:
                payload = {
                    "episode_id": audit.episode_id,
                    "episode_path": str(audit.episode_path),
                    **interval,
                }
                f.write(json.dumps(_jsonable(payload), sort_keys=True) + "\n")

    episode_summary = [
        {
            "episode_id": audit.episode_id,
            "episode_path": str(audit.episode_path),
            "steps": audit.steps,
            "reject_intervals": audit.reject_intervals,
            "clean_intervals": audit.clean_intervals,
            "stats": audit.stats,
        }
        for audit in audits
    ]
    _write_json(output_dir / "episode_summary.json", episode_summary)
    write_lineage_json(
        output_dir,
        builder="tb-audit-swing-consistency",
        storage_mode="manifest",
        source_roots=[raw_dir],
        extra={"swing_audit_config": _config_payload(config)},
    )


def _summary_payload(
    *,
    raw_dir: Path,
    output_dir: Path,
    audits: list[EpisodeAudit],
    config: AuditConfig,
    primitive_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    reject_episode_count = sum(1 for audit in audits if audit.reject_intervals)
    reject_interval_count = sum(len(audit.reject_intervals) for audit in audits)
    total_steps = sum(audit.steps for audit in audits)
    rejected_steps = sum(
        interval["end_step_exclusive"] - interval["start_step"]
        for audit in audits
        for interval in audit.reject_intervals
    )
    clean_steps = sum(
        interval["end_step_exclusive"] - interval["start_step"]
        for audit in audits
        for interval in audit.clean_intervals
    )
    payload: dict[str, Any] = {
        "raw_dir": str(raw_dir),
        "output_dir": str(output_dir),
        "episode_count": len(audits),
        "reject_episode_count": reject_episode_count,
        "reject_interval_count": reject_interval_count,
        "total_steps": int(total_steps),
        "rejected_steps_with_padding": int(rejected_steps),
        "clean_steps_after_min_len": int(clean_steps),
        "rejected_step_fraction": _float(rejected_steps / total_steps if total_steps else 0.0),
        "config": _config_payload(config),
    }
    if primitive_payload is not None:
        payload["primitive_filter"] = primitive_payload
    return payload


def _points_to_intervals(
    points: dict[int, set[str]],
    *,
    steps: int,
    padding: int,
) -> list[dict[str, Any]]:
    raw: list[dict[str, Any]] = []
    for point, reasons in sorted(points.items()):
        raw.append(
            {
                "start_step": max(0, int(point) - padding),
                "end_step_exclusive": min(steps, int(point) + padding + 1),
                "peak_step": int(point),
                "reasons": sorted(reasons),
            }
        )
    if not raw:
        return []

    merged: list[dict[str, Any]] = [raw[0]]
    for interval in raw[1:]:
        prev = merged[-1]
        if interval["start_step"] <= prev["end_step_exclusive"]:
            prev["end_step_exclusive"] = max(
                prev["end_step_exclusive"],
                interval["end_step_exclusive"],
            )
            prev["reasons"] = sorted(set(prev["reasons"]) | set(interval["reasons"]))
            if "peak_steps" not in prev:
                prev["peak_steps"] = [prev.pop("peak_step")]
            prev["peak_steps"].append(interval["peak_step"])
        else:
            merged.append(interval)

    for interval in merged:
        if "peak_steps" not in interval:
            interval["peak_steps"] = [interval.pop("peak_step")]
        interval["window_len"] = int(interval["end_step_exclusive"] - interval["start_step"])
    return merged


def _complement_intervals(
    reject_intervals: list[dict[str, Any]],
    *,
    steps: int,
    min_len: int,
) -> list[dict[str, int]]:
    clean: list[dict[str, int]] = []
    cursor = 0
    for interval in sorted(reject_intervals, key=lambda item: item["start_step"]):
        start = int(interval["start_step"])
        if start - cursor >= min_len:
            clean.append(
                {
                    "start_step": cursor,
                    "end_step_exclusive": start,
                    "window_len": start - cursor,
                }
            )
        cursor = max(cursor, int(interval["end_step_exclusive"]))
    if steps - cursor >= min_len:
        clean.append(
            {
                "start_step": cursor,
                "end_step_exclusive": steps,
                "window_len": steps - cursor,
            }
        )
    return clean


def _overlapping_intervals(
    intervals: list[dict[str, Any]],
    *,
    start: int,
    end: int,
) -> list[dict[str, Any]]:
    return [
        interval
        for interval in intervals
        if _overlaps(
            start,
            end,
            int(interval["start_step"]),
            int(interval["end_step_exclusive"]),
        )
    ]


def _overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return int(a_start) < int(b_end) and int(b_start) < int(a_end)


def _contact_mask(env_state: Any, steps: int) -> np.ndarray:
    mask = np.zeros(steps, dtype=bool)
    if env_state is None:
        return mask
    arr = np.asarray(env_state, dtype=np.float32)
    if arr.ndim != 2:
        return mask
    if arr.shape[1] > DIG_CONTACT_IDX:
        mask |= arr[:steps, DIG_CONTACT_IDX] > 0.5
    if arr.shape[1] > DUMP_CONTACT_IDX:
        mask |= arr[:steps, DUMP_CONTACT_IDX] > 0.5
    return mask


def _hard_collision(env_state: Any, steps: int) -> np.ndarray:
    if env_state is None:
        return np.zeros(steps, dtype=bool)
    arr = np.asarray(env_state, dtype=np.float32)
    if arr.ndim != 2 or arr.shape[1] <= HARD_COLLISION_IDX:
        return np.zeros(steps, dtype=bool)
    hard = arr[:steps, HARD_COLLISION_IDX]
    delta = _prepend_zero(np.maximum(0.0, np.diff(hard)))
    return delta > 0.0


def _episode_id(path: Path, metadata: dict[str, Any]) -> str:
    return _normalise_episode_id(metadata.get("episode_id") or path.stem)


def _normalise_episode_id(value: Any) -> str:
    text = str(value.decode() if isinstance(value, bytes) else value)
    if text.endswith(".hdf5"):
        text = Path(text).stem
    return text


def _prepend_zero(values: np.ndarray) -> np.ndarray:
    return np.concatenate([np.zeros(1, dtype=np.float32), values.astype(np.float32)])


def _read_attrs(attrs: h5py.AttributeManager) -> dict[str, Any]:
    return {str(key): attrs[key] for key in attrs.keys()}


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(_jsonable(payload), f, indent=2, sort_keys=True)


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return _jsonable(value.tolist())
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return str(value)


def _float(value: Any) -> float:
    return float(np.asarray(value).item())


def _config_payload(config: AuditConfig) -> dict[str, Any]:
    return {
        "warning_qvel_action_threshold": config.warning_qvel_action_threshold,
        "severe_qvel_action_threshold": config.severe_qvel_action_threshold,
        "warning_qvel_jump_threshold": config.warning_qvel_jump_threshold,
        "severe_qvel_jump_threshold": config.severe_qvel_jump_threshold,
        "severe_qpos_delta_threshold": config.severe_qpos_delta_threshold,
        "reject_padding_steps": config.reject_padding_steps,
        "min_clean_steps": config.min_clean_steps,
    }


if __name__ == "__main__":
    main()
