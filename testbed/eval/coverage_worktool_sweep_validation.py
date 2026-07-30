"""Offline gate for Unity-generated worktool sweep evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from testbed.planner.primitive.coverage.worktool_sweep import (
    CALIBRATED_ACT_TRACKING_MARGIN_M,
    CALIBRATED_HARD_CLEARANCE_M,
    CALIBRATED_POSE_INTERPOLATION_BOUND_M,
    CoverageWorktoolSweepConfig,
    CoverageWorktoolSweepService,
)

SCHEMA = "coverage_worktool_sweep_episode_preflight_v1"
OUTPUT_FILENAME = f"{SCHEMA}.json"
_TARGET_EXEMPLAR = "episode_168"
_TARGET_RAW_FIELDS_SHA256 = (
    "c167e087f3d41f6db8fe0ad260d5f72c3440b6fab9115fdf55959feacc50991c"
)


class CoverageWorktoolSweepPreflightError(RuntimeError):
    """Raised when frozen evidence cannot be evaluated faithfully."""


def build_coverage_worktool_sweep_preflight(
    *,
    sweep_artifact_path: str | Path,
    sweep_artifact_sha256: str,
    execution_library_path: str | Path,
    execution_library_sha256: str,
    pose_library_path: str | Path,
    pose_library_sha256: str,
    frozen_rollout_dir: str | Path,
    output_dir: str | Path,
    target_cycle_index: int = 1,
) -> dict[str, Any]:
    """Require episode_168 rejection at all three frozen live starts."""

    destination = Path(output_dir).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite {destination}")
    sweep_path = _locked_file(
        sweep_artifact_path,
        sweep_artifact_sha256,
        "sweep_artifact",
    )
    execution_path = _locked_file(
        execution_library_path,
        execution_library_sha256,
        "execution_library",
    )
    pose_path = _locked_file(
        pose_library_path,
        pose_library_sha256,
        "pose_library",
    )
    rollout_dir = Path(frozen_rollout_dir).expanduser().resolve(strict=True)
    if not rollout_dir.is_dir():
        raise CoverageWorktoolSweepPreflightError(
            f"frozen_rollout_dir_not_directory:{rollout_dir}"
        )

    config = CoverageWorktoolSweepConfig.from_mapping(
        {
            "enabled": True,
            "profile": "unity_kinematic_convex_cover_worktool_sweep_v1",
            "hard_clearance_m": CALIBRATED_HARD_CLEARANCE_M,
            "act_tracking_margin_m": CALIBRATED_ACT_TRACKING_MARGIN_M,
            "pose_interpolation_bound_m": (
                CALIBRATED_POSE_INTERPOLATION_BOUND_M
            ),
            "artifact_path": str(sweep_path),
            "artifact_sha256": str(sweep_artifact_sha256).lower(),
            "execution_library_sha256": str(
                execution_library_sha256
            ).lower(),
            "pose_library_sha256": str(pose_library_sha256).lower(),
            "missing_contract": "fail_closed",
        }
    )
    service = CoverageWorktoolSweepService.from_config(config)
    sweep_root = _load_mapping(sweep_path)
    episode_record = _episode_record(sweep_root)
    raw_fields_sha256 = str(
        episode_record.get("raw_fields_sha256", "")
    ).lower()
    if raw_fields_sha256 != _TARGET_RAW_FIELDS_SHA256:
        raise CoverageWorktoolSweepPreflightError(
            "episode_168_raw_fields_sha256_drift"
        )
    bucket_zmin = _bucket_zmin_pair_witness(episode_record)

    evaluations: list[dict[str, Any]] = []
    for rollout_index in range(3):
        stem = f"rollout_{rollout_index:03d}"
        jsonl_path = rollout_dir / f"{stem}.jsonl"
        trace_path = rollout_dir / f"{stem}_planner_trace.json"
        for path, label in (
            (jsonl_path, "rollout_jsonl"),
            (trace_path, "planner_trace"),
        ):
            if not path.is_file():
                raise CoverageWorktoolSweepPreflightError(
                    f"{label}_missing:{path}"
                )
        _validate_selected_exemplar(
            trace_path,
            target_cycle_index=int(target_cycle_index),
            expected_raw_fields_sha256=raw_fields_sha256,
        )
        start_row = _target_cycle_start(
            jsonl_path,
            target_cycle_index=int(target_cycle_index),
        )
        evaluation = service.evaluate(
            exemplar_id=_TARGET_EXEMPLAR,
            raw_fields_sha256=raw_fields_sha256,
            live_start_qpos=start_row["qpos"],
        )
        evaluations.append(
            {
                "rollout_index": rollout_index,
                "step_id": int(start_row["step_id"]),
                "target_cycle_index": int(target_cycle_index),
                "live_start_qpos": [
                    float(value) for value in start_row["qpos"]
                ],
                "act_inference_allowed": bool(evaluation.eligible),
                **evaluation.as_trace_fields(),
                "source_lock": {
                    "rollout_jsonl": _source_record(jsonl_path),
                    "planner_trace": _source_record(trace_path),
                },
            }
        )

    rejected_count = sum(
        int(
            not item["act_inference_allowed"]
            and item["worktool_sweep_3d_rejection_reason"]
            == "worktool_3d_clearance_below_minimum"
            and float(
                item["worktool_sweep_3d_effective_clearance_m"]
            )
            < 0.30
        )
        for item in evaluations
    )
    passed = rejected_count == 3
    artifact: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "passed" if passed else "failed",
        "evidence_kind": "offline_frozen_live_start_replay",
        "teacher_forced_recorded_observation": True,
        "act_inference_executed": False,
        "target_exemplar_id": _TARGET_EXEMPLAR,
        "target_raw_fields_sha256": raw_fields_sha256,
        "hard_clearance_m": CALIBRATED_HARD_CLEARANCE_M,
        "episode_168_rejected_count": rejected_count,
        "required_rejected_count": 3,
        "bucket_zmin_pair_witness": bucket_zmin,
        "evaluations": evaluations,
        "source_lock": {
            "sweep_artifact": _source_record(sweep_path),
            "execution_library": _source_record(execution_path),
            "pose_library": _source_record(pose_path),
        },
        "production_replan_allowed": bool(passed),
    }
    destination.mkdir(parents=True, exist_ok=False)
    with (destination / OUTPUT_FILENAME).open("x", encoding="utf-8") as handle:
        json.dump(
            artifact,
            handle,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        handle.write("\n")
    return artifact


def _episode_record(root: dict[str, Any]) -> dict[str, Any]:
    records = root.get("records")
    if not isinstance(records, list):
        raise CoverageWorktoolSweepPreflightError(
            "sweep_records_missing"
        )
    matches = [
        dict(item)
        for item in records
        if isinstance(item, dict)
        and item.get("exemplar_id") == _TARGET_EXEMPLAR
    ]
    if len(matches) != 1:
        raise CoverageWorktoolSweepPreflightError(
            f"episode_168_record_count:{len(matches)}"
        )
    return matches[0]


def _bucket_zmin_pair_witness(record: dict[str, Any]) -> dict[str, Any]:
    links = record.get("link_sweeps")
    if not isinstance(links, list):
        raise CoverageWorktoolSweepPreflightError(
            "episode_168_link_sweeps_missing"
        )
    bucket = next(
        (
            item
            for item in links
            if isinstance(item, dict)
            and item.get("link_name") == "bucket"
        ),
        None,
    )
    if not isinstance(bucket, dict):
        raise CoverageWorktoolSweepPreflightError(
            "episode_168_bucket_sweep_missing"
        )
    pairs = bucket.get("wall_sweeps")
    if not isinstance(pairs, list):
        raise CoverageWorktoolSweepPreflightError(
            "episode_168_bucket_wall_sweeps_missing"
        )
    pair = next(
        (
            item
            for item in pairs
            if isinstance(item, dict)
            and item.get("wall_name") == "Dig_ZMin_Board"
        ),
        None,
    )
    if not isinstance(pair, dict):
        raise CoverageWorktoolSweepPreflightError(
            "episode_168_bucket_zmin_pair_missing"
        )
    witness = pair.get("closest")
    if (
        not isinstance(witness, dict)
        or witness.get("link_name") != "bucket"
        or witness.get("wall_name") != "Dig_ZMin_Board"
    ):
        raise CoverageWorktoolSweepPreflightError(
            "episode_168_bucket_zmin_witness_invalid"
        )
    return {
        "link_name": "bucket",
        "wall_name": "Dig_ZMin_Board",
        "sampled_convex_cover_clearance_m": float(
            pair["sampled_convex_cover_clearance_m"]
        ),
        "shape_name": str(witness.get("shape_name", "")),
        "pose_index": int(witness.get("pose_index", -1)),
        "qpos": [float(value) for value in witness.get("qpos", ())],
    }


def _validate_selected_exemplar(
    trace_path: Path,
    *,
    target_cycle_index: int,
    expected_raw_fields_sha256: str,
) -> None:
    root = _load_mapping(trace_path)
    events = root.get("coverage_decision_trace")
    if not isinstance(events, list):
        raise CoverageWorktoolSweepPreflightError(
            f"coverage_decision_trace_missing:{trace_path}"
        )
    selected = [
        item
        for item in events
        if isinstance(item, dict)
        and item.get("event")
        == "select_actual_tuple_execution_candidate"
        and item.get("exemplar_id") == _TARGET_EXEMPLAR
        and str(item.get("raw_fields_sha256", "")).lower()
        == expected_raw_fields_sha256
        and int(item.get("cycle_index", -1))
        in {target_cycle_index - 1, target_cycle_index}
    ]
    if len(selected) != 1:
        raise CoverageWorktoolSweepPreflightError(
            f"target_cycle_selection_count:{trace_path}:{len(selected)}"
        )
    event = selected[0]
    if int(event.get("active_corridor_id", 1_000_168)) != 1_000_168:
        raise CoverageWorktoolSweepPreflightError(
            f"target_cycle_selection_drift:{trace_path}"
        )


def _target_cycle_start(
    jsonl_path: Path,
    *,
    target_cycle_index: int,
) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    with jsonl_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if (
                int(row.get("primitive_cycle_index", -1))
                == target_cycle_index
                and row.get("skill_name") == "dig"
            ):
                matches.append(row)
    if not matches:
        raise CoverageWorktoolSweepPreflightError(
            f"target_cycle_start_missing:{jsonl_path}"
        )
    row = min(matches, key=lambda item: int(item["step_id"]))
    qpos = row.get("qpos")
    if not isinstance(qpos, list) or len(qpos) != 4:
        raise CoverageWorktoolSweepPreflightError(
            f"target_cycle_qpos_invalid:{jsonl_path}"
        )
    return row


def _locked_file(
    path: str | Path,
    expected_sha256: str,
    label: str,
) -> Path:
    source = Path(path).expanduser().resolve(strict=True)
    actual = _sha256(source)
    expected = str(expected_sha256).strip().lower()
    if actual != expected:
        raise CoverageWorktoolSweepPreflightError(
            f"{label}_sha256_mismatch:expected={expected}:actual={actual}"
        )
    return source


def _load_mapping(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CoverageWorktoolSweepPreflightError(
            f"json_invalid:{path}"
        ) from exc
    if not isinstance(value, dict):
        raise CoverageWorktoolSweepPreflightError(
            f"json_root_not_mapping:{path}"
        )
    return value


def _source_record(path: Path) -> dict[str, str]:
    return {
        "path": str(path),
        "sha256": _sha256(path),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "CoverageWorktoolSweepPreflightError",
    "OUTPUT_FILENAME",
    "SCHEMA",
    "build_coverage_worktool_sweep_preflight",
]
