"""Execute, audit, and retain or remove one terrain replay attempt.

The strict dataset builder and the layered salvage builder share this runtime
boundary.  Strict semantic selection remains owned by the existing single-attempt
gate; salvage may retain a technically complete failed realization for later local
masking without promoting it to strict evidence.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from testbed.data.terrain_replay_dataset import (
    annotate_selected_replay_episode,
    apply_source_action_overlays,
    audit_recorded_replay_episode,
    safe_remove_failed_attempt_hdf5,
    sha256_file,
)
from testbed.eval.terrain_replay_pilot_gate import build_source_semantic_reference
from testbed.eval.terrain_replay_relabel_stats import load_replay_diagnostic_summary
from testbed.eval.terrain_replay_run_contract import (
    HardReplayContractError,
    replay_control_profile_for_episode,
)
from testbed.eval.terrain_replay_selection import (
    CALIBRATED_MIXED_SELECTION_PROFILE,
    CORRECTED_PARTIAL_SALVAGE_EVIDENCE_PROFILE,
    STRICT_REPLAY_EVIDENCE_PROFILE,
)
from testbed.eval.terrain_replay_single_attempt import evaluate_single_replay_attempt

STRICT_SELECTION_POLICY = "first_passing_attempt_v1"
CORRECTED_SELECTION_POLICY = "best_local_cycle_coverage_v1"
STRICT_EVIDENCE_KIND = "replay_derived_selected_pass"
PARTIAL_EVIDENCE_KIND = "replay_partial_salvage_v1"
EXPECTED_TARGET_IDS = (
    "recording_depth_0p08_full_grid_diagnostic",
    "t1_large_shallow_rectangular_pit_default",
    "t2_long_shallow_trench_default",
)


def run_one_replay_attempt(
    *,
    attempts_root: Path,
    selected_root: Path,
    episode_id: int,
    selection_manifest: Path,
    replay_config: Path,
    calibrated_source_path: Path,
    expected_steps: int,
    source_reference: Mapping[str, Any],
    attempt_index: int,
    attempt_kind: str = "strict",
    failure_hdf5_policy: str = "delete",
    expected_runtime_build_id: str | None = None,
) -> dict[str, Any]:
    """Run one full causal replay and preserve strict versus salvage evidence."""

    if attempt_kind not in {"strict", "corrected"}:
        raise ValueError(f"Unknown attempt_kind: {attempt_kind!r}")
    if failure_hdf5_policy not in {"delete", "retain"}:
        raise ValueError(
            f"Unknown failure_hdf5_policy: {failure_hdf5_policy!r}"
        )
    attempt_id = f"attempt_{int(attempt_index):02d}"
    episode_name = f"episode_{int(episode_id)}"
    control_profile = replay_control_profile_for_episode(int(episode_id))
    evidence_profile = (
        STRICT_REPLAY_EVIDENCE_PROFILE
        if attempt_kind == "strict"
        else CORRECTED_PARTIAL_SALVAGE_EVIDENCE_PROFILE
    )
    attempt_dir = attempts_root / episode_name / attempt_id
    if attempt_dir.exists():
        raise FileExistsError(f"Attempt directory already exists: {attempt_dir}")
    recorded_dir = attempt_dir / "recorded"
    recorded_dir.mkdir(parents=True, exist_ok=False)
    selected_root.mkdir(parents=True, exist_ok=True)
    diagnostic_path = attempt_dir / "diagnostics.jsonl"
    samples_path = attempt_dir / "cycle_samples.jsonl"
    replay_log = attempt_dir / "replay.log"
    command = _build_replay_command(
        episode_name=episode_name,
        selection_manifest=selection_manifest,
        replay_config=replay_config,
        recorded_dir=recorded_dir,
        diagnostic_path=diagnostic_path,
        samples_path=samples_path,
        control_profile=control_profile,
        evidence_profile=evidence_profile,
        corrected=attempt_kind == "corrected",
    )
    _write_json_atomic(
        attempt_dir / "command.json",
        {
            "schema": "terrain_replay_attempt_command_v2",
            "attempt_id": attempt_id,
            "attempt_kind": attempt_kind,
            "source_episode_id": episode_name,
            "control_compatibility_profile": control_profile,
            "replay_evidence_profile": evidence_profile,
            "argv": command,
            "cwd": str(Path.cwd().resolve()),
        },
    )
    print(
        json.dumps(
            {
                "event": "attempt_start",
                "episode": episode_name,
                "attempt": attempt_id,
                "attempt_kind": attempt_kind,
                "expected_steps": int(expected_steps),
            }
        ),
        flush=True,
    )
    started_at = datetime.now(timezone.utc).isoformat()
    with replay_log.open("w", encoding="utf-8") as sink:
        completed = subprocess.run(
            command,
            cwd=Path(__file__).resolve().parents[2],
            stdout=sink,
            stderr=subprocess.STDOUT,
            check=False,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
    ended_at = datetime.now(timezone.utc).isoformat()
    recorded_path = recorded_dir / "episode_0.hdf5"
    hdf5_audit = _audit_attempt_hdf5(
        recorded_path=recorded_path,
        calibrated_source_path=calibrated_source_path,
        expected_steps=int(expected_steps),
        control_profile=control_profile,
        evidence_profile=evidence_profile,
        expected_runtime_build_id=expected_runtime_build_id,
    )
    diagnostic_summary = (
        load_replay_diagnostic_summary(diagnostic_path)
        if diagnostic_path.is_file()
        else {
            "exception_count": 1,
            "pose_realign_count": 0,
            "step_sequence_complete": False,
        }
    )
    candidate_records = [
        row
        for row in (_read_jsonl(samples_path) if samples_path.is_file() else [])
        if str(row.get("source_episode_id") or row.get("episode_id") or "")
        == episode_name
    ]
    gate = evaluate_single_replay_attempt(
        {
            "repeat_id": attempt_id,
            "candidate_records": candidate_records,
            "diagnostic_summary": diagnostic_summary,
        },
        source_reference=source_reference,
        required_source_episode_id=episode_name,
        hdf5_audit=hdf5_audit,
    )
    if int(completed.returncode) != 0:
        gate["pass"] = False
        gate.setdefault("failed_checks", []).append("replay_process_nonzero_exit")
    gate["replay_process_returncode"] = int(completed.returncode)
    gate["attempt_kind"] = attempt_kind
    gate["replay_evidence_profile"] = evidence_profile
    _write_json_atomic(attempt_dir / "hdf5_audit.json", hdf5_audit)
    _write_json_atomic(attempt_dir / "gate.json", gate)

    hard_errors = _hard_hdf5_errors(hdf5_audit.get("errors", []))
    if attempt_kind == "strict" and int(
        diagnostic_summary.get("pose_realign_count", 0)
    ) != 0:
        hard_errors.append("strict_replay_pose_realign_observed")
    if int(completed.returncode) != 0 and _looks_like_hard_process_failure(replay_log):
        hard_errors.append("hard_process_contract_failure")
    technical_candidate_pass = candidate_is_locally_auditable(
        process_returncode=int(completed.returncode),
        hdf5_audit=hdf5_audit,
        diagnostic_summary=diagnostic_summary,
    )
    strict_gate_pass = bool(gate.get("pass", False)) and not hard_errors
    strict_selected = attempt_kind == "strict" and strict_gate_pass
    _write_json_atomic(
        attempt_dir / "attempt_checkpoint.json",
        {
            "schema": "terrain_replay_attempt_checkpoint_v1",
            "source_episode_id": episode_name,
            "attempt_id": attempt_id,
            "attempt_index": int(attempt_index),
            "attempt_kind": attempt_kind,
            "control_compatibility_profile": control_profile,
            "replay_evidence_profile": evidence_profile,
            "process_returncode": int(completed.returncode),
            "expected_step_count": int(expected_steps),
            "candidate_technical_pass": technical_candidate_pass,
            "strict_gate_pass": strict_gate_pass,
            "strict_selected": strict_selected,
            "hard_contract_errors": hard_errors,
            "diagnostic_summary": diagnostic_summary,
        },
    )
    selected_record: dict[str, Any] | None = None
    selected_sample_count = 0
    deletion: dict[str, Any] | None = None
    retained_path: str | None = None
    retained_sha256: str | None = None
    retained_size_bytes: int | None = None
    if strict_selected:
        overlay = apply_source_action_overlays(
            replay_path=recorded_path,
            calibrated_source_path=calibrated_source_path,
            replay_qc_mask=np.ones(int(expected_steps), dtype=np.uint8),
        )
        lineage = annotate_selected_replay_episode(
            replay_path=recorded_path,
            source_episode_id=episode_name,
            calibrated_source_path=calibrated_source_path,
            attempt_id=attempt_id,
        )
        selected_samples = selected_sidecar_rows(
            candidate_records,
            source_episode_id=episode_name,
            attempt_id=attempt_id,
            selection_policy=STRICT_SELECTION_POLICY,
            evidence_kind=STRICT_EVIDENCE_KIND,
        )
        selected_sample_count = len(selected_samples)
        selected_sample_path = attempt_dir / "selected_cycle_samples.jsonl"
        _write_jsonl_atomic(selected_sample_path, selected_samples)
        selected_path = selected_root / f"{episode_name}.hdf5"
        if selected_path.exists():
            raise FileExistsError(f"Selected HDF5 already exists: {selected_path}")
        selected_sha256 = sha256_file(recorded_path)
        selected_size = int(recorded_path.stat().st_size)
        selection_intent = {
            "schema": "terrain_replay_selection_move_intent_v1",
            "source_path": str(recorded_path.resolve()),
            "selected_path": str(selected_path.resolve()),
            "sha256": selected_sha256,
            "size_bytes": selected_size,
            "source_episode_id": episode_name,
            "attempt_id": attempt_id,
        }
        _write_json_atomic(attempt_dir / "selection_intent.json", selection_intent)
        recorded_path.replace(selected_path)
        lineage["replay_path"] = str(selected_path.resolve())
        selected_record = {
            "schema": "terrain_replay_selected_episode_v1",
            "source_episode_id": episode_name,
            "selected_attempt_id": attempt_id,
            "selection_policy": STRICT_SELECTION_POLICY,
            "evidence_kind": STRICT_EVIDENCE_KIND,
            "repeatability_status": "not_assessed_single_attempt",
            "gold_status": "not_gold",
            "control_compatibility_profile": control_profile,
            "selected_hdf5_path": str(selected_path.resolve()),
            "sha256": selected_sha256,
            "size_bytes": selected_size,
            "step_count": int(expected_steps),
            "selected_cycle_sample_path": str(selected_sample_path.resolve()),
            "selected_cycle_sample_count": selected_sample_count,
            "calibrated_source_path": str(calibrated_source_path.resolve()),
            "action_overlay": overlay,
            "lineage": lineage,
            "gate_path": str((attempt_dir / "gate.json").resolve()),
            "diagnostic_path": str(diagnostic_path.resolve()),
        }
        _write_json_atomic(attempt_dir / "selected_record.json", selected_record)
    elif recorded_path.is_file() and technical_candidate_pass and (
        failure_hdf5_policy == "retain"
    ):
        retained_path = str(recorded_path.resolve())
        retained_sha256 = sha256_file(recorded_path)
        retained_size_bytes = int(recorded_path.stat().st_size)
    elif recorded_path.is_file():
        deletion = _remove_failed_hdf5(
            recorded_path=recorded_path,
            attempts_root=attempts_root,
            attempt_dir=attempt_dir,
            diagnostic_path=diagnostic_path,
            gate_path=attempt_dir / "gate.json",
            reason=(
                "attempt_not_retained_for_local_salvage"
                if failure_hdf5_policy == "retain"
                else "attempt_did_not_pass_single_attempt_gate"
            ),
        )

    result = {
        "schema": "terrain_replay_attempt_result_v2",
        "source_episode_id": episode_name,
        "attempt_id": attempt_id,
        "attempt_index": int(attempt_index),
        "attempt_kind": attempt_kind,
        "control_compatibility_profile": control_profile,
        "replay_evidence_profile": evidence_profile,
        "pass": strict_selected,
        "strict_gate_pass": strict_gate_pass,
        "candidate_technical_pass": technical_candidate_pass,
        "status": "selected" if strict_selected else "failed",
        "started_at": started_at,
        "ended_at": ended_at,
        "process_returncode": int(completed.returncode),
        "expected_step_count": int(expected_steps),
        "gate_path": str((attempt_dir / "gate.json").resolve()),
        "diagnostic_path": str(diagnostic_path.resolve()),
        "cycle_samples_path": str(samples_path.resolve()),
        "retained_hdf5_path": retained_path,
        "retained_hdf5_sha256": retained_sha256,
        "retained_hdf5_size_bytes": retained_size_bytes,
        "selected_record": selected_record,
        "selected_cycle_sample_count": selected_sample_count,
        "failed_hdf5_deletion": deletion,
        "hard_contract_errors": hard_errors,
    }
    _write_json_atomic(attempt_dir / "attempt_result.json", result)
    print(
        json.dumps(
            {
                "event": "attempt_end",
                "episode": episode_name,
                "attempt": attempt_id,
                "attempt_kind": attempt_kind,
                "pass": strict_selected,
                "candidate_technical_pass": technical_candidate_pass,
                "hard_contract_errors": hard_errors,
            }
        ),
        flush=True,
    )
    if hard_errors:
        raise HardReplayContractError(
            f"{episode_name}/{attempt_id}: {', '.join(hard_errors)}"
        )
    return result


def selected_sidecar_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    source_episode_id: str,
    attempt_id: str,
    selection_policy: str,
    evidence_kind: str,
) -> list[dict[str, Any]]:
    """Seal the complete three-target sidecar set for one retained realization."""

    grouped: dict[int, set[str]] = {}
    selected: list[dict[str, Any]] = []
    for raw in rows:
        row = dict(raw)
        cycle_index = int(row["cycle_index"])
        target_id = str(row["target_id"])
        grouped.setdefault(cycle_index, set()).add(target_id)
        selected.append(
            {
                **row,
                "upstream_schema": str(row.get("schema", "")),
                "schema": "terrain_replay_selected_cycle_sample_v1",
                "source": "terrain_replay_attempt_runner",
                "source_episode_id": str(source_episode_id),
                "episode_id": str(source_episode_id),
                "selected_attempt_id": str(attempt_id),
                "selection_policy": str(selection_policy),
                "evidence_kind": str(evidence_kind),
                "repeatability_status": "not_assessed_single_attempt",
                "gold_status": "not_gold",
                "volume_label_status": "derived_grid_integral",
                "direct_volume_status": "unavailable_no_sensor",
                "planned_cut_status": "missing_not_generated_by_replay",
                "entry_exit_status": "missing_not_generated_by_replay",
                "gate_transition_status": "missing_not_generated_by_replay",
                "planner_trace_status": "missing_not_generated_by_replay",
                "actual_response_status": "missing_not_generated_by_replay",
            }
        )
    expected = set(EXPECTED_TARGET_IDS)
    bad = {
        cycle: sorted(targets)
        for cycle, targets in grouped.items()
        if targets != expected
    }
    if not grouped or bad or len(selected) != 3 * len(grouped):
        raise HardReplayContractError(
            f"Selected sidecar target-set mismatch: {bad or 'no complete cycles'}"
        )
    selected.sort(key=lambda row: (int(row["cycle_index"]), str(row["target_id"])))
    return selected


def candidate_is_locally_auditable(
    *,
    process_returncode: int,
    hdf5_audit: Mapping[str, Any],
    diagnostic_summary: Mapping[str, Any],
) -> bool:
    """Accept only complete attempts whose defects can be isolated by timestep.

    Isolated JPEG framing failures are local-mask defects.  Missing datasets,
    protocol/metadata mismatches, non-finite state, missing steps, and runtime
    exceptions are not locally recoverable.
    """

    errors = _hard_hdf5_errors(hdf5_audit.get("errors", ()))
    expected = hdf5_audit.get("expected_step_count")
    recorded = hdf5_audit.get("recorded_step_count")
    return bool(
        int(process_returncode) == 0
        and not errors
        and expected is not None
        and recorded is not None
        and int(recorded) == int(expected)
        and int(diagnostic_summary.get("exception_count", 1)) == 0
        and bool(diagnostic_summary.get("step_sequence_complete", False))
    )


def build_replay_source_reference(
    *,
    source_path: str | Path,
    source_episode_id: str,
    cycle_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the shared source-relative semantic gate reference."""

    source = Path(source_path).expanduser().resolve(strict=True)
    with h5py.File(source, "r") as handle:
        env_state = np.asarray(handle["observations/env_state"][()], dtype=np.float32)
        control_hz = float(handle["metadata"].attrs.get("control_hz", 0.0))
    reference = build_source_semantic_reference(
        source_episode_id=str(source_episode_id),
        control_hz=control_hz,
        env_state=env_state,
        cycle_records=cycle_rows,
    )
    if reference.get("status") != "present":
        raise HardReplayContractError(
            f"Invalid source semantic reference for {source_episode_id}: "
            f"{reference.get('validation_errors', [])}"
        )
    return reference


def remove_retained_attempt_hdf5(
    *,
    path: str | Path,
    attempts_root: str | Path,
    attempt_dir: str | Path,
    reason: str,
) -> dict[str, Any]:
    """Delete only the generated HDF5 owned by one exact audited attempt."""

    root = Path(attempts_root).expanduser().resolve(strict=True)
    attempt = Path(attempt_dir).expanduser().resolve(strict=True)
    try:
        attempt.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Attempt directory is outside attempts root: {attempt}") from exc
    target = Path(path).expanduser().resolve(strict=True)
    expected = (attempt / "recorded" / "episode_0.hdf5").resolve(strict=True)
    if target != expected:
        raise ValueError(
            f"Deletion target is not the exact current attempt HDF5: {target}"
        )
    required_audit = (
        attempt / "gate.json",
        attempt / "hdf5_audit.json",
        attempt / "diagnostics.jsonl",
    )
    missing = [str(item) for item in required_audit if not item.is_file()]
    if missing:
        raise ValueError(
            f"Retained HDF5 cannot be removed before audit artifacts exist: {missing}"
        )
    digest = sha256_file(target)
    size = int(target.stat().st_size)
    intent_path = attempt / "deletion_intent.json"
    result_path = attempt / "deletion_result.json"
    if intent_path.exists() or result_path.exists():
        raise FileExistsError(
            f"Deletion audit already exists for current attempt: {attempt}"
        )
    _write_json_atomic(
        intent_path,
        {
            "schema": "terrain_replay_failed_hdf5_deletion_intent_v1",
            "path": str(target),
            "sha256": digest,
            "size_bytes": size,
            "reason": str(reason),
            "diagnostic_path": str((attempt / "diagnostics.jsonl").resolve()),
            "gate_path": str((attempt / "gate.json").resolve()),
            "hdf5_audit_path": str((attempt / "hdf5_audit.json").resolve()),
        },
    )
    result = safe_remove_failed_attempt_hdf5(
        path=target,
        attempts_root=attempt / "recorded",
        expected_sha256=digest,
        expected_size_bytes=size,
    )
    _write_json_atomic(result_path, result)
    return result


def _build_replay_command(
    *,
    episode_name: str,
    selection_manifest: Path,
    replay_config: Path,
    recorded_dir: Path,
    diagnostic_path: Path,
    samples_path: Path,
    control_profile: str,
    evidence_profile: str,
    corrected: bool,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "testbed.cli.replay",
        "--selection-manifest",
        str(selection_manifest),
        "--selection-profile",
        CALIBRATED_MIXED_SELECTION_PROFILE,
        "--selection-episode-id",
        episode_name,
        "--config",
        str(replay_config),
        "--record-output-dir",
        str(recorded_dir),
        "--post-tail-steps",
        "0",
        "--diagnostic-log",
        str(diagnostic_path),
        "--diagnostic-every",
        "0",
        "--control-compatibility-profile",
        control_profile,
        "--replay-evidence-profile",
        evidence_profile,
        "--gold-cycle-samples-jsonl",
        str(samples_path),
    ]
    if corrected:
        command.extend(
            (
                "--realign-on-qpos-error",
                "--realign-error-threshold",
                "0.04",
                "--realign-axis",
                "all",
                "--realign-hold-steps",
                "3",
                "--realign-min-steps-between",
                "200",
                "--realign-burn-in-steps",
                "15",
                "--realign-max-count",
                "20",
            )
        )
    return command


def _audit_attempt_hdf5(
    *,
    recorded_path: Path,
    calibrated_source_path: Path,
    expected_steps: int,
    control_profile: str,
    evidence_profile: str,
    expected_runtime_build_id: str | None,
) -> dict[str, Any]:
    if not recorded_path.is_file():
        return {
            "schema": "terrain_replay_hdf5_audit_v1",
            "status": "fail",
            "pass": False,
            "errors": ["recorded_hdf5_missing"],
        }
    return audit_recorded_replay_episode(
        replay_path=recorded_path,
        calibrated_source_path=calibrated_source_path,
        expected_steps=int(expected_steps),
        expected_control_compatibility_profile=control_profile,
        expected_replay_evidence_profile=evidence_profile,
        expected_runtime_build_id=expected_runtime_build_id,
    )


def _remove_failed_hdf5(
    *,
    recorded_path: Path,
    attempts_root: Path,
    attempt_dir: Path,
    diagnostic_path: Path,
    gate_path: Path,
    reason: str,
) -> dict[str, Any]:
    if not diagnostic_path.is_file():
        _write_jsonl_atomic(
            diagnostic_path,
            (
                {
                    "event": "attempt_diagnostic_missing",
                    "reason": "replay_process_did_not_write_diagnostics",
                },
            ),
        )
    del gate_path
    return remove_retained_attempt_hdf5(
        path=recorded_path,
        attempts_root=attempts_root,
        attempt_dir=attempt_dir,
        reason=reason,
    )


def _hard_hdf5_errors(values: Sequence[Any]) -> list[str]:
    non_hard_prefixes = (
        "camera_jpeg_empty:",
        "camera_jpeg_invalid:",
        "camera_jpeg_shape_invalid:",
    )
    return [
        str(value)
        for value in values
        if not str(value).startswith(non_hard_prefixes)
    ]


def _looks_like_hard_process_failure(log_path: Path) -> bool:
    text = log_path.read_text(encoding="utf-8", errors="replace").lower()
    patterns = (
        "multi-camera contract mismatch",
        "env_state contract mismatch",
        "outside fixed episode inventory",
        "outside approved source root",
        "action contract",
        "source filename does not match",
        "requires zero replay post-tail",
    )
    return any(pattern in text for pattern in patterns)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append(value)
    return rows


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    _write_text_atomic(
        path,
        json.dumps(dict(payload), indent=2, sort_keys=True, allow_nan=False) + "\n",
    )


def _write_jsonl_atomic(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    content = "\n".join(
        json.dumps(dict(row), sort_keys=True, allow_nan=False) for row in rows
    )
    _write_text_atomic(path, content + ("\n" if content else ""))


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


__all__ = [
    "CORRECTED_SELECTION_POLICY",
    "PARTIAL_EVIDENCE_KIND",
    "STRICT_EVIDENCE_KIND",
    "STRICT_SELECTION_POLICY",
    "build_replay_source_reference",
    "candidate_is_locally_auditable",
    "remove_retained_attempt_hdf5",
    "run_one_replay_attempt",
    "selected_sidecar_rows",
]
