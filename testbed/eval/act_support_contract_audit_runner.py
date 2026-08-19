"""File orchestration for the offline Strict-18 support-contract audit."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import h5py

from testbed.data.act_support_contract import (
    load_strict_source_aware_support_rows,
)
from testbed.data.recorded_act_replay import (
    join_recorded_act_replay_frames,
    split_stable_recorded_act_segments,
)
from testbed.eval.act_support_contract_audit import (
    EVIDENCE_KIND,
    run_support_contract_audit,
)

STAGE_A_MANIFEST_SCHEMA = "act_goal_condition_sensitivity_manifest_v1"


def run_support_contract_audit_from_files(
    *,
    source_results_root: str | Path,
    stage_a_output_root: str | Path,
    dig_training_config_path: str | Path,
    return_training_config_path: str | Path,
    output_root: str | Path,
) -> dict[str, Any]:
    """Audit frozen support candidates against source-disjoint validation rows.

    This entrypoint rejects a dirty code tree, mismatched Stage-A source lineage,
    and malformed JSONL/HDF5 alignment before fitting a candidate.  It does not
    modify a runtime support gate or invoke an ACT checkpoint.
    """

    destination = Path(output_root).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"support-contract output already exists: {destination}")
    clean_code = _clean_code_record()
    if not bool(clean_code["worktree_clean"]):
        raise RuntimeError("support-contract audit requires a clean Git worktree")

    source_root = Path(source_results_root).expanduser().resolve(strict=True)
    source_paths = _source_paths(source_root)
    stage_root = Path(stage_a_output_root).expanduser().resolve(strict=True)
    stage_paths = _stage_a_paths(stage_root)
    stage_manifest = _load_json_mapping(stage_paths["manifest"])
    _validate_stage_a_manifest(stage_manifest, source_paths=source_paths)

    feature_partitions = {
        "dig": load_strict_source_aware_support_rows(
            training_config_path=dig_training_config_path,
            skill_name="dig",
        ),
        "return": load_strict_source_aware_support_rows(
            training_config_path=return_training_config_path,
            skill_name="return",
        ),
    }
    frames = join_recorded_act_replay_frames(
        rollout_hdf5_path=source_paths["rollout_hdf5"],
        rollout_jsonl_path=source_paths["rollout_jsonl"],
        skills=("dig", "return"),
    )
    target_segments = {
        primitive: [
            segment
            for segment in split_stable_recorded_act_segments(frames)
            if segment.skill_name == primitive
        ]
        for primitive in ("dig", "return")
    }
    if not target_segments["dig"] or not target_segments["return"]:
        raise ValueError("source results lack stable Dig or Return target segments")

    lineage = {
        "source_results_root": str(source_root),
        "eval_resolved_config": _source_record(source_paths["eval_config"]),
        "eval_run_metadata": _source_record(source_paths["eval_metadata"]),
        "rollout_jsonl": _source_record(source_paths["rollout_jsonl"]),
        "rollout_hdf5": _source_record(source_paths["rollout_hdf5"]),
        "stage_a_manifest": _source_record(stage_paths["manifest"]),
        "stage_a_baseline": _source_record(stage_paths["baseline"]),
        "stage_a_dig": _source_record(stage_paths["dig"]),
        "stage_a_return": _source_record(stage_paths["return"]),
        "dig_training_config": _source_record(Path(dig_training_config_path)),
        "return_training_config": _source_record(Path(return_training_config_path)),
        "strict_support_inputs": _support_input_lineage(feature_partitions),
        "code": clean_code,
        "alignment_and_field_contract": _alignment_and_field_contract(
            source_paths["rollout_hdf5"],
            target_segments=target_segments,
        ),
    }
    return run_support_contract_audit(
        source_lineage=lineage,
        feature_partitions=feature_partitions,
        target_segments=target_segments,
        output_root=destination,
    )


def _source_paths(source_root: Path) -> dict[str, Path]:
    paths = {
        "eval_config": source_root / "eval_resolved_config.yaml",
        "eval_metadata": source_root / "eval_run_metadata.json",
        "rollout_jsonl": source_root / "rollouts" / "rollout_000.jsonl",
        "rollout_hdf5": source_root / "hdf5_rollouts" / "episode_0.hdf5",
    }
    _require_files(paths, label="source results")
    return paths


def _stage_a_paths(stage_root: Path) -> dict[str, Path]:
    paths = {
        "manifest": stage_root / "manifest.json",
        "baseline": stage_root / "baseline.json",
        "dig": stage_root / "dig.json",
        "return": stage_root / "return.json",
    }
    _require_files(paths, label="Stage-A evidence")
    return paths


def _require_files(paths: Mapping[str, Path], *, label: str) -> None:
    missing = [f"{name}={path}" for name, path in paths.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"{label} missing required files: {', '.join(missing)}")


def _validate_stage_a_manifest(
    manifest: Mapping[str, Any],
    *,
    source_paths: Mapping[str, Path],
) -> None:
    if manifest.get("schema") != STAGE_A_MANIFEST_SCHEMA:
        raise ValueError("Stage-A manifest schema is not recognized")
    if manifest.get("status") != "completed":
        raise ValueError("Stage-A manifest is not a completed artifact")
    if manifest.get("evidence_kind") != EVIDENCE_KIND:
        raise ValueError("Stage-A manifest evidence kind does not match teacher-forced scope")
    if manifest.get("diagnostic_only") is not True or manifest.get("promotion_eligible") is not False:
        raise ValueError("Stage-A manifest violates diagnostic-only evidence boundary")
    stage_lineage = manifest.get("source_lineage")
    if not isinstance(stage_lineage, Mapping):
        raise ValueError("Stage-A manifest lacks source lineage")
    expected = {
        "eval_resolved_config": source_paths["eval_config"],
        "rollout_jsonl": source_paths["rollout_jsonl"],
        "rollout_hdf5": source_paths["rollout_hdf5"],
    }
    for key, path in expected.items():
        record = stage_lineage.get(key)
        if not isinstance(record, Mapping) or record.get("sha256") != _sha256(path):
            raise ValueError(f"Stage-A manifest lineage mismatch for {key}")


def _alignment_and_field_contract(
    hdf5_path: Path,
    *,
    target_segments: Mapping[str, list[Any]],
) -> dict[str, Any]:
    with h5py.File(hdf5_path, "r") as handle:
        metadata = handle.get("metadata")
        if metadata is None:
            raise ValueError("source HDF5 lacks metadata required for qpos/qvel semantics")
        qpos_order = _metadata_text(metadata.attrs.get("qpos_order"), "qpos_order")
        qvel_order = _metadata_text(metadata.attrs.get("qvel_order"), "qvel_order")
        camera_names = _metadata_text(metadata.attrs.get("camera_names"), "camera_names")
    return {
        "status": "structural_alignment_and_field_mapping_passed",
        "action_jsonl_hdf5_tolerance": 1.0e-6,
        "action_observation_relation": "action_step_id uses HDF5 pre-action row action_index-1",
        "return_token_mapping": "JSONL return_start_envelope_tokens -> return_start_envelope_tokens_v1",
        "qpos_order": qpos_order,
        "qvel_order": qvel_order,
        "camera_names": camera_names,
        "target_segment_counts": {
            primitive: len(segments)
            for primitive, segments in target_segments.items()
        },
        "semantic_limit": (
            "structural checks pass; numeric evidence alone cannot prove physical "
            "field semantics beyond recorded metadata"
        ),
    }


def _metadata_text(value: Any, label: str) -> str:
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    text = str(value).strip()
    if not text:
        raise ValueError(f"source HDF5 metadata lacks {label}")
    return text


def _source_record(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve(strict=True)
    return {
        "path": str(resolved),
        "sha256": _sha256(resolved),
        "size_bytes": int(resolved.stat().st_size),
    }


def _support_input_lineage(
    feature_partitions: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    """Record each strict support population and exact source split hash."""

    output: dict[str, dict[str, Any]] = {}
    for primitive, rows in feature_partitions.items():
        as_dict = getattr(rows, "as_dict", None)
        split_path = getattr(rows, "split_path", None)
        if not callable(as_dict) or split_path is None:
            raise ValueError(
                f"{primitive} support rows lack lineage metadata required for audit"
            )
        output[str(primitive)] = {
            **dict(as_dict()),
            "split_sha256": _sha256(Path(split_path)),
        }
    return output


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json_mapping(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"{path} must contain a JSON object")
    return dict(payload)


def _clean_code_record() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    return {
        "git_head": _git_output(root, "rev-parse", "HEAD"),
        "git_branch": _git_output(root, "branch", "--show-current"),
        "worktree_clean": not bool(_git_output(root, "status", "--short")),
    }


def _git_output(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


__all__ = ["run_support_contract_audit_from_files"]
