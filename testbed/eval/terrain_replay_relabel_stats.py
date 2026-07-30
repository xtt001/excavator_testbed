"""Variance stats for current-Unity replay relabel cycle samples."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

SCHEMA = "terrain_replay_relabel_stats_v2"
RECORD_SCHEMA = "terrain_replay_relabel_cycle_sample_v2"
SOURCE = "current_unity_replay_relabel_stats"
RECORD_SOURCE = "current_unity_replay_relabel"
GRID_CELL_COUNT = 6


def build_replay_relabel_stats(
    repeats: Sequence[Mapping[str, Any]],
    *,
    source_episode_id: str | None = None,
    target_id: str | None = None,
    min_repeat_count: int = 5,
) -> dict[str, Any]:
    """Aggregate repeat replay cycle candidates into relabel variance records."""

    validation_errors: list[str] = []
    grouped: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)

    for repeat_index, repeat in enumerate(repeats):
        repeat_map = _mapping(repeat)
        repeat_id = _optional_text(repeat_map.get("repeat_id")) or (
            f"repeat_{repeat_index:03d}"
        )
        diagnostic = _mapping(repeat_map.get("diagnostic_summary"))
        candidate_records = repeat_map.get("candidate_records")
        if not isinstance(candidate_records, Sequence) or isinstance(
            candidate_records, (str, bytes)
        ):
            validation_errors.append(
                f"repeats[{repeat_index}].candidate_records must be a list"
            )
            continue

        for record_index, record_value in enumerate(candidate_records):
            record = _mapping(record_value)
            parsed, errors = _parse_candidate_record(
                record,
                repeat_id=repeat_id,
                diagnostic=diagnostic,
                source_episode_id=source_episode_id,
                target_id=target_id,
            )
            if errors:
                validation_errors.extend(
                    f"repeats[{repeat_index}].candidate_records[{record_index}].{error}"
                    for error in errors
                )
                continue
            grouped[
                (
                    parsed["source_episode_id"],
                    parsed["target_id"],
                    parsed["source_cycle_id"],
                )
            ].append(parsed)

    records = [
        _build_group_record(group, min_repeat_count=max(1, int(min_repeat_count)))
        for group in grouped.values()
    ]
    records.sort(
        key=lambda item: (
            str(item["source_episode_id"]),
            str(item["target_id"]),
            int(item["source_cycle_id"]),
        )
    )
    usable_count = sum(1 for record in records if record["tier"] in {"A", "B"})
    status = "present" if not validation_errors else "invalid_repeat_records"
    return {
        "schema": SCHEMA,
        "source": SOURCE,
        "status": status,
        "group_count": len(records),
        "usable_group_count": usable_count if status == "present" else 0,
        "record_count": len(records) if status == "present" else 0,
        "records": records if status == "present" else [],
        "validation_errors": validation_errors,
        "tier_counts": _tier_counts(records if status == "present" else []),
        "training_source": "current_unity_replay_relabel",
        "gold_status": "not_gold",
        "calibrated_branch_status": "not_claimed",
    }


def write_replay_relabel_outputs(
    repeats: Sequence[Mapping[str, Any]],
    *,
    report_path: Any,
    samples_path: Any,
    source_episode_id: str | None = None,
    target_id: str | None = None,
    min_repeat_count: int = 5,
) -> dict[str, Any]:
    """Write stats report JSON and relabel sample JSONL with no-overwrite."""

    report = Path(report_path)
    samples = Path(samples_path)
    existing = [str(path) for path in (report, samples) if path.exists()]
    if existing:
        return {
            "schema": SCHEMA,
            "source": SOURCE,
            "status": "output_path_already_exists",
            "report_path": str(report),
            "samples_path": str(samples),
            "validation_errors": [
                f"output path must not already exist: {path}" for path in existing
            ],
            "records": [],
            "record_count": 0,
        }

    result = build_replay_relabel_stats(
        repeats,
        source_episode_id=source_episode_id,
        target_id=target_id,
        min_repeat_count=min_repeat_count,
    )
    report.parent.mkdir(parents=True, exist_ok=True)
    samples.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    sample_lines = [
        json.dumps(record, sort_keys=True, allow_nan=False)
        for record in result.get("records", [])
    ]
    samples.write_text(
        "\n".join(sample_lines) + ("\n" if sample_lines else ""),
        encoding="utf-8",
    )
    return {**result, "report_path": str(report), "samples_path": str(samples)}


def load_replay_diagnostic_summary(path: Any) -> dict[str, Any]:
    """Read qpos/exception/realign summary fields from tb-replay diagnostics."""

    source_episode = ""
    qpos_max_error = 0.0
    exception_count = 0
    pose_realign_events = 0
    pose_realign_count_from_end = 0
    qpos_pre_contact_max_error = 0.0
    qpos_pre_contact_sample_count = 0
    first_qualified_contact_step: int | None = None
    qualified_contact_seen = False
    diagnostic_every: int | None = None
    logged_step_count = 0
    source_step_count: int | None = None
    previous_record_step_index: int | None = None
    step_sequence_error = False
    realign_record_step_indices: set[int] = set()
    episode_end_seen = False
    final_removed_depth_grid: list[float] | None = None
    for row in _read_jsonl(Path(path)):
        if not isinstance(row, Mapping):
            continue
        event = row.get("event")
        if event in {"episode_start", "episode_end"}:
            source_episode = _optional_text(row.get("source_episode")) or source_episode
        if event == "episode_start":
            diagnostic_every = _finite_int(
                row.get("diagnostic_every"),
                default=None,
            )
        if event == "episode_end":
            episode_end_seen = True
            source_step_count = _finite_int(row.get("steps"), default=None)
            terminal_grid = _float_sequence(
                _mapping(row.get("final_env_state")).get(
                    "removed_depth_m_grid_3x2"
                )
            )
            if terminal_grid is not None:
                final_removed_depth_grid = terminal_grid
        if event == "step_exception":
            exception_count += 1
        if event == "pose_realign":
            pose_realign_events += 1
            realign_index = _finite_int(row.get("record_step_index"), default=None)
            if realign_index is not None:
                realign_record_step_indices.add(realign_index)
        if event == "step":
            record_step_index = _finite_int(
                row.get("record_step_index"),
                default=None,
            )
            step_id_before = _finite_int(row.get("step_id_before"), default=None)
            step_id_after = _finite_int(row.get("step_id_after"), default=None)
            if record_step_index is None:
                step_sequence_error = True
            elif previous_record_step_index is not None:
                if record_step_index <= previous_record_step_index:
                    step_sequence_error = True
                if (
                    diagnostic_every == 1
                    and record_step_index != previous_record_step_index + 1
                ):
                    step_sequence_error = True
            backend_id_is_normal = (
                step_id_before is not None
                and step_id_after is not None
                and step_id_after == step_id_before + 1
            )
            backend_id_is_realign_stutter = (
                record_step_index is not None
                and record_step_index in realign_record_step_indices
                and step_id_before is not None
                and step_id_after == step_id_before
            )
            if not (backend_id_is_normal or backend_id_is_realign_stutter):
                step_sequence_error = True
            previous_record_step_index = record_step_index
            logged_step_count += 1

            final_grid = _float_sequence(
                _mapping(row.get("env_state_after")).get(
                    "removed_depth_m_grid_3x2"
                )
            )
            if final_grid is not None:
                final_removed_depth_grid = final_grid

        if event == "step" and not qualified_contact_seen:
            before_contact = _qualified_contact_active(row.get("env_state_before"))
            after_contact = _qualified_contact_active(row.get("env_state_after"))
            before_error = _finite_float(
                row.get("qpos_max_error_before"),
                default=None,
            )
            after_error = _finite_float(
                row.get("qpos_max_error_after"),
                default=None,
            )
            if before_error is not None:
                qpos_pre_contact_max_error = max(
                    qpos_pre_contact_max_error,
                    before_error,
                )
                qpos_pre_contact_sample_count += 1
            if not before_contact and not after_contact and after_error is not None:
                qpos_pre_contact_max_error = max(
                    qpos_pre_contact_max_error,
                    after_error,
                )
                qpos_pre_contact_sample_count += 1
            if before_contact or after_contact:
                first_qualified_contact_step = record_step_index
                qualified_contact_seen = True
        pose_realign_count_from_end = max(
            pose_realign_count_from_end,
            _finite_int(row.get("pose_realign_count"), default=0),
        )
        for key in (
            "qpos_max_error_before",
            "qpos_max_error_after",
            "qpos_max_diff",
        ):
            qpos_max_error = max(
                qpos_max_error,
                _finite_float(row.get(key), default=0.0),
            )
    step_sequence_complete = bool(
        episode_end_seen
        and source_step_count is not None
        and source_step_count > 0
        and not step_sequence_error
        and (
            (
                diagnostic_every == 1
                and source_step_count == logged_step_count
                and previous_record_step_index == source_step_count - 1
            )
            or diagnostic_every == 0
        )
    )
    return {
        "source_episode": source_episode,
        "qpos_max_error_max": qpos_max_error,
        "qpos_pre_contact_max_error_max": (
            qpos_pre_contact_max_error
            if qpos_pre_contact_sample_count > 0
            else None
        ),
        "first_qualified_contact_step": first_qualified_contact_step,
        "exception_count": exception_count,
        "pose_realign_count": max(pose_realign_events, pose_realign_count_from_end),
        "step_sequence_complete": step_sequence_complete,
        "logged_step_count": logged_step_count,
        "source_step_count": source_step_count,
        "final_removed_depth_grid_m": final_removed_depth_grid,
    }


def _parse_candidate_record(
    record: Mapping[str, Any],
    *,
    repeat_id: str,
    diagnostic: Mapping[str, Any],
    source_episode_id: str | None,
    target_id: str | None,
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    resolved_source_episode_id = (
        _optional_text(source_episode_id)
        or _optional_text(record.get("source_episode_id"))
        or _optional_text(record.get("episode_id"))
    )
    resolved_target_id = _optional_text(target_id) or _optional_text(
        record.get("target_id")
    )
    cycle_index = _finite_int(record.get("cycle_index"), default=None)
    source_cycle_id = (
        cycle_index
        if record.get("source_cycle_id") is None
        else _finite_int(record.get("source_cycle_id"), default=None)
    )
    payload = _finite_float(record.get("payload_mass_kg"), default=None)
    deposit = _finite_float(record.get("effective_deposit_mass_kg"), default=None)
    removed_start = _float_sequence(record.get("removed_depth_grid_start_m"))
    removed_end = _float_sequence(record.get("removed_depth_grid_end_m"))
    valid_mask = _float_sequence(record.get("valid_mask"))

    required = {
        "source_episode_id": resolved_source_episode_id,
        "target_id": resolved_target_id,
        "cycle_index": cycle_index,
        "source_cycle_id": source_cycle_id,
        "payload_mass_kg": payload,
        "effective_deposit_mass_kg": deposit,
        "removed_depth_grid_start_m": removed_start,
        "removed_depth_grid_end_m": removed_end,
        "valid_mask": valid_mask,
    }
    for key, value in required.items():
        if value is None:
            errors.append(f"{key} is required")
    for key, value in (
        ("removed_depth_grid_start_m", removed_start),
        ("removed_depth_grid_end_m", removed_end),
        ("valid_mask", valid_mask),
    ):
        if value is not None and len(value) != GRID_CELL_COUNT:
            errors.append(f"{key} must have {GRID_CELL_COUNT} cells")
    if errors:
        return {}, errors

    start_arr = np.asarray(removed_start, dtype=float)
    end_arr = np.asarray(removed_end, dtype=float)
    return {
        "repeat_id": repeat_id,
        "source_record_schema": str(record.get("schema", "")),
        "source_episode_id": str(resolved_source_episode_id),
        "target_id": str(resolved_target_id),
        "cycle_index": int(cycle_index),
        "source_cycle_id": int(source_cycle_id),
        "payload_mass_kg": float(payload),
        "effective_deposit_mass_kg": float(deposit),
        "removed_depth_delta_grid_m": (end_arr - start_arr).tolist(),
        "valid_mask": [float(value) for value in valid_mask],
        "qpos_max_error_max": _finite_float(
            diagnostic.get("qpos_max_error_max"),
            default=0.0,
        ),
        "exception_count": _finite_int(
            diagnostic.get("exception_count"),
            default=0,
        ),
        "pose_realign_count": _finite_int(
            diagnostic.get("pose_realign_count"),
            default=0,
        ),
    }, []


def _build_group_record(
    group: Sequence[Mapping[str, Any]],
    *,
    min_repeat_count: int,
) -> dict[str, Any]:
    first = group[0]
    payload_values = np.asarray([item["payload_mass_kg"] for item in group], dtype=float)
    deposit_values = np.asarray(
        [item["effective_deposit_mass_kg"] for item in group],
        dtype=float,
    )
    removed_delta = np.asarray(
        [item["removed_depth_delta_grid_m"] for item in group],
        dtype=float,
    )
    valid_mask = np.asarray([item["valid_mask"] for item in group], dtype=float)
    cell_valid = np.max(valid_mask, axis=0) > 0.5
    removed_std = np.std(removed_delta, axis=0)
    max_cell_std = float(np.max(removed_std[cell_valid])) if np.any(cell_valid) else 0.0
    qpos_max = max(float(item["qpos_max_error_max"]) for item in group)
    exception_count = sum(int(item["exception_count"]) for item in group)
    realign_count = sum(int(item["pose_realign_count"]) for item in group)

    payload_stats = _series_stats(payload_values)
    deposit_stats = _series_stats(deposit_values)
    tier, label_usage, weight = _classify(
        repeat_count=len(group),
        min_repeat_count=min_repeat_count,
        payload_stats=payload_stats,
        deposit_stats=deposit_stats,
        removed_depth_delta_grid_max_cell_std_m=max_cell_std,
        qpos_max_error_max=qpos_max,
        exception_count=exception_count,
        pose_realign_count=realign_count,
    )
    return {
        "schema": RECORD_SCHEMA,
        "source": RECORD_SOURCE,
        "source_episode_id": str(first["source_episode_id"]),
        "target_id": str(first["target_id"]),
        "cycle_index": int(first["source_cycle_id"]),
        "source_cycle_id": int(first["source_cycle_id"]),
        "observed_cycle_indices": [int(item["cycle_index"]) for item in group],
        "repeat_count": len(group),
        "candidate_repeat_ids": [str(item["repeat_id"]) for item in group],
        "source_record_schemas": sorted(
            {str(item.get("source_record_schema", "")) for item in group}
        ),
        "payload_mass_kg_mean": payload_stats["mean"],
        "payload_mass_kg_std": payload_stats["std"],
        "payload_mass_kg_cv": payload_stats["cv"],
        "effective_deposit_mass_kg_mean": deposit_stats["mean"],
        "effective_deposit_mass_kg_std": deposit_stats["std"],
        "effective_deposit_mass_kg_cv": deposit_stats["cv"],
        "removed_depth_delta_grid_mean_m": np.mean(removed_delta, axis=0).tolist(),
        "removed_depth_delta_grid_std_m": removed_std.tolist(),
        "removed_depth_delta_grid_max_cell_std_m": max_cell_std,
        "qpos_max_error_max": qpos_max,
        "qpos_gate_role": "diagnostic_only_post_contact",
        "exception_count": exception_count,
        "pose_realign_count": realign_count,
        "tier": tier,
        "recommended_weight": weight,
        "label_usage": label_usage,
        "training_source": "current_unity_replay_relabel",
        "gold_status": "not_gold",
    }


def _classify(
    *,
    repeat_count: int,
    min_repeat_count: int,
    payload_stats: Mapping[str, float | None],
    deposit_stats: Mapping[str, float | None],
    removed_depth_delta_grid_max_cell_std_m: float,
    qpos_max_error_max: float,
    exception_count: int,
    pose_realign_count: int,
) -> tuple[str, str, float]:
    process_failed = (
        repeat_count < min_repeat_count
        or exception_count > 0
        or pose_realign_count > 0
    )
    if process_failed:
        return "C", "coarse_or_diagnostic_only", 0.0

    payload_std = float(payload_stats["std"])
    payload_cv = payload_stats["cv"]
    deposit_std = float(deposit_stats["std"])
    deposit_cv = deposit_stats["cv"]
    if (
        payload_std <= 2.0
        and _cv_lte(payload_cv, 0.08)
        and deposit_std <= 2.0
        and _cv_lte(deposit_cv, 0.10)
        and removed_depth_delta_grid_max_cell_std_m <= 0.02
    ):
        return "A", "fine_relabel", 1.0

    payload_b = payload_std <= 5.0 or _cv_lte(payload_cv, 0.20)
    deposit_b = deposit_std <= 5.0 or _cv_lte(deposit_cv, 0.20)
    grid_b = removed_depth_delta_grid_max_cell_std_m <= 0.06
    if payload_b and deposit_b and grid_b:
        return "B", "uncertainty_weighted_relabel", 0.5

    return "C", "coarse_or_diagnostic_only", 0.0


def _series_stats(values: np.ndarray) -> dict[str, float | None]:
    mean = float(np.mean(values))
    std = float(np.std(values))
    return {"mean": mean, "std": std, "cv": _coefficient_of_variation(mean, std)}


def _coefficient_of_variation(mean: float, std: float) -> float | None:
    if abs(mean) <= 1.0e-9:
        return 0.0 if std <= 1.0e-9 else None
    return abs(std / mean)


def _cv_lte(value: float | None, threshold: float) -> bool:
    return value is not None and value <= threshold


def _tier_counts(records: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = {"A": 0, "B": 0, "C": 0}
    for record in records:
        tier = str(record.get("tier", ""))
        if tier in counts:
            counts[tier] += 1
    return counts


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _qualified_contact_active(value: Any) -> bool:
    env_state = _mapping(value)
    mask = _finite_float(
        env_state.get("bucket_dig_area_penetration_contact_mask"),
        default=0.0,
    )
    return bool(mask is not None and mask > 0.5)


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _finite_float(value: Any, *, default: float | None) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _finite_int(value: Any, *, default: int | None) -> int | None:
    parsed = _finite_float(value, default=None)
    return default if parsed is None else int(parsed)


def _float_sequence(value: Any) -> list[float] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    result: list[float] = []
    for item in value:
        parsed = _finite_float(item, default=None)
        if parsed is None:
            return None
        result.append(parsed)
    return result


def _read_jsonl(path: Path) -> Iterator[Any]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            yield json.loads(text)
