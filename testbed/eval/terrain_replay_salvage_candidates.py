"""Evaluate, rank, retain, and finalize local replay salvage candidates."""

from __future__ import annotations

import json
import os
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import yaml

from testbed.data.terrain_cycle_cleaning import analyze_episode_cleaning
from testbed.data.terrain_replay_dataset import (
    annotate_selected_replay_episode,
    apply_source_action_overlays,
    replay_camera_step_valid_mask,
    sha256_file,
)
from testbed.data.v2_1 import label_episode_v2_1
from testbed.eval.terrain_replay_attempt_runner import (
    CORRECTED_SELECTION_POLICY,
    PARTIAL_EVIDENCE_KIND,
    remove_retained_attempt_hdf5,
    selected_sidecar_rows,
)
from testbed.eval.terrain_replay_pilot_gate import match_monotonic_boundaries
from testbed.eval.terrain_replay_run_contract import HardReplayContractError
from testbed.eval.terrain_replay_salvage import (
    build_local_action_mask,
    evaluate_local_cycle_eligibility,
    select_best_local_candidate,
)
from testbed.eval.terrain_replay_selection import (
    CORRECTED_PARTIAL_SALVAGE_EVIDENCE_PROFILE,
)
from testbed.planner.boundary_detector import QUALIFIED_DIG_START_MODE_CONTACT_DEPTH

LOCAL_GUARD_SECONDS = 1.0


def evaluate_attempt_local_candidate(
    *,
    attempt_result: Mapping[str, Any],
    calibrated_source_path: Path,
    source_cycles: Sequence[Mapping[str, Any]],
    replay_config: Path,
) -> dict[str, Any]:
    """Compute replay-native cleaning, local eligibility, and three-way masks."""

    replay_path = Path(str(attempt_result["retained_hdf5_path"])).resolve(strict=True)
    attempt_dir = Path(str(attempt_result["gate_path"])).resolve(strict=True).parent
    local_path = attempt_dir / "local_candidate.json"
    if local_path.is_file():
        stored = _read_json(local_path)
        _verify_local_candidate_hdf5(stored)
        return stored
    with h5py.File(calibrated_source_path, "r") as source:
        source_qpos = np.asarray(source["observations/qpos"][()], dtype=np.float32)
        source_env = np.asarray(source["observations/env_state"][()], dtype=np.float32)
        source_mask = np.asarray(
            source["v2/step/action_loss_mask"][()], dtype=np.uint8
        ).reshape(-1)
        control_hz = float(source["metadata"].attrs.get("control_hz", 50.0))
    with h5py.File(replay_path, "r") as replay:
        replay_qpos = np.asarray(replay["observations/qpos"][()], dtype=np.float32)
        replay_env = np.asarray(replay["observations/env_state"][()], dtype=np.float32)
        metadata = dict(replay["metadata"].attrs)
    replay_steps = int(len(replay_qpos))
    if min(len(source_qpos), len(source_env), len(source_mask)) < replay_steps:
        raise HardReplayContractError(
            f"Calibrated source is shorter than retained replay: {replay_path}"
        )
    source_qpos = source_qpos[:replay_steps]
    source_env = source_env[:replay_steps]
    source_mask = source_mask[:replay_steps]
    realign_steps = _parse_step_list(metadata.get("replay_pose_realign_steps", ""))
    camera_mask, camera_issues = replay_camera_step_valid_mask(replay_path)
    native = _replay_native_cleaning(
        replay_path=replay_path,
        replay_config=replay_config,
        camera_mask=camera_mask,
    )
    replay_qc_mask = (
        camera_mask.astype(bool)
        & np.asarray(native["action_loss_mask"], dtype=np.uint8).astype(bool)
    ).astype(np.uint8)
    candidate_records = _read_jsonl(Path(str(attempt_result["cycle_samples_path"])))
    source_episode_id = str(attempt_result["source_episode_id"])
    candidate_records = [
        row
        for row in candidate_records
        if str(row.get("source_episode_id") or row.get("episode_id") or "")
        == source_episode_id
    ]
    eligibility = evaluate_local_cycle_eligibility(
        source_qpos=source_qpos,
        source_env_state=source_env,
        replay_qpos=replay_qpos,
        replay_env_state=replay_env,
        source_cycles=source_cycles,
        candidate_records=candidate_records,
        realign_steps=realign_steps,
        camera_step_valid_mask=camera_mask,
        replay_cycle_validity=native["observed_cycle_validity"],
        control_hz=control_hz,
    )
    cycle_windows = [
        {**row, "cycle_id": int(row["source_cycle_id"])}
        for row in eligibility["cycle_rows"]
    ]
    local_only_mask = build_local_action_mask(
        source_mask=np.ones(len(source_mask), dtype=np.uint8),
        replay_qc_mask=np.ones(len(source_mask), dtype=np.uint8),
        cycle_windows=cycle_windows,
        eligible_cycle_ids=eligibility["eligible_source_cycle_ids"],
        realign_steps=realign_steps,
        guard_steps=max(0, int(round(control_hz * LOCAL_GUARD_SECONDS))),
    )
    final_mask = (
        source_mask.astype(bool)
        & replay_qc_mask.astype(bool)
        & local_only_mask.astype(bool)
    ).astype(np.uint8)
    local_mask_path = attempt_dir / "local_cycle_mask.npy"
    replay_qc_path = attempt_dir / "replay_qc_mask.npy"
    final_mask_path = attempt_dir / "final_local_action_loss_mask.npy"
    for path, values in (
        (local_mask_path, local_only_mask),
        (replay_qc_path, replay_qc_mask),
        (final_mask_path, final_mask),
    ):
        if path.exists():
            raise FileExistsError(f"No-overwrite local mask already exists: {path}")
        np.save(path, values, allow_pickle=False)
    enriched_rows = [
        {
            **row,
            "source_episode_id": source_episode_id,
            "attempt_id": str(attempt_result["attempt_id"]),
            "attempt_kind": str(attempt_result["attempt_kind"]),
            "candidate_hdf5_path": str(replay_path),
        }
        for row in eligibility["cycle_rows"]
    ]
    cycle_rows_path = attempt_dir / "local_cycle_eligibility.jsonl"
    _write_jsonl_atomic(cycle_rows_path, enriched_rows)
    candidate = {
        "schema": "terrain_replay_local_candidate_v1",
        "source_episode_id": source_episode_id,
        "attempt_id": str(attempt_result["attempt_id"]),
        "attempt_index": int(attempt_result["attempt_index"]),
        "attempt_kind": str(attempt_result["attempt_kind"]),
        "attempt_uid": f"{attempt_result['attempt_kind']}:{attempt_result['attempt_id']}",
        "attempt_dir": str(attempt_dir),
        "candidate_hdf5_path": str(replay_path),
        "candidate_hdf5_sha256": sha256_file(replay_path),
        "candidate_hdf5_size_bytes": int(replay_path.stat().st_size),
        "eligible_cycle_count": int(eligibility["eligible_cycle_count"]),
        "eligible_source_cycle_ids": list(eligibility["eligible_source_cycle_ids"]),
        "valid_action_step_count": int(np.count_nonzero(final_mask)),
        "source_action_step_count": int(len(source_mask)),
        "realign_steps": list(realign_steps),
        "realign_count": len(realign_steps),
        "camera_issues": camera_issues,
        "native_cleaning": native["summary"],
        "local_cycle_eligibility_path": str(cycle_rows_path.resolve()),
        "local_cycle_mask_path": str(local_mask_path.resolve()),
        "replay_qc_mask_path": str(replay_qc_path.resolve()),
        "final_action_loss_mask_path": str(final_mask_path.resolve()),
        "cycle_samples_path": str(
            Path(str(attempt_result["cycle_samples_path"])).resolve()
        ),
        "gate_path": str(Path(str(attempt_result["gate_path"])).resolve()),
        "diagnostic_path": str(
            Path(str(attempt_result["diagnostic_path"])).resolve()
        ),
    }
    _write_json_atomic(local_path, candidate)
    return candidate


def retain_only_best_candidate(
    output_root: Path,
    *,
    candidate: Mapping[str, Any],
) -> None:
    """Keep at most one deterministic local HDF5 for one source identity."""

    episode_id = _episode_number(str(candidate["source_episode_id"]))
    candidates = _local_candidates(output_root, episode_id=episode_id)
    best = select_best_local_candidate(candidates)
    if best is None:
        return
    for row in candidates:
        path = Path(str(row["candidate_hdf5_path"]))
        if not path.is_file():
            continue
        keep = (
            str(row["attempt_uid"]) == str(best["attempt_uid"])
            and int(row.get("eligible_cycle_count", 0)) > 0
            and int(row.get("valid_action_step_count", 0)) > 0
        )
        if not keep:
            _remove_candidate_hdf5(row, reason="not_best_local_candidate")


def remove_all_retained_candidates(output_root: Path, *, episode_id: int) -> None:
    """Remove provisional local HDF5s once the strict source is selected."""

    for candidate in _local_candidates(output_root, episode_id=episode_id):
        if Path(str(candidate["candidate_hdf5_path"])).is_file():
            _remove_candidate_hdf5(
                candidate,
                reason="strict_attempt_selected_for_source_identity",
            )


def best_retained_candidate(
    output_root: Path,
    *,
    episode_id: int,
) -> dict[str, Any] | None:
    """Return and verify the single live deterministic best candidate."""

    candidates = _local_candidates(output_root, episode_id=episode_id)
    best = select_best_local_candidate(candidates)
    if best is None:
        return None
    if int(best.get("eligible_cycle_count", 0)) <= 0 or int(
        best.get("valid_action_step_count", 0)
    ) <= 0:
        return None
    _verify_local_candidate_hdf5(best)
    live = [row for row in candidates if Path(str(row["candidate_hdf5_path"])).is_file()]
    if len(live) != 1 or str(live[0]["attempt_uid"]) != str(best["attempt_uid"]):
        raise HardReplayContractError(
            f"Retained local candidate inventory is not deterministic for episode_{episode_id}."
        )
    return best


def finalize_partial_candidate(
    *,
    output_root: Path,
    candidate: Mapping[str, Any],
    calibrated_source_path: Path,
) -> dict[str, Any]:
    """Seal one best local candidate into the isolated partial pool."""

    episode_name = str(candidate["source_episode_id"])
    episode_id = _episode_number(episode_name)
    target = output_root / "partial_salvage_full_hdf5" / f"episode_{episode_id}.hdf5"
    sidecar_path = output_root / "partial_sidecars" / f"episode_{episode_id}.jsonl"
    attempt_dir = Path(str(candidate["attempt_dir"]))
    final_record_path = attempt_dir / "partial_record.json"
    if final_record_path.is_file():
        record = _read_json(final_record_path)
        final = Path(str(record["selected_hdf5_path"])).resolve(strict=True)
        if sha256_file(final) != str(record["sha256"]):
            raise HardReplayContractError(f"Partial HDF5 checksum mismatch: {final}")
        return record
    move_intent_path = attempt_dir / "partial_move_intent.json"
    if move_intent_path.is_file():
        return _complete_partial_move(
            output_root=output_root,
            episode_id=episode_id,
            intent_path=move_intent_path,
            retention_reason="recovered_after_partial_move",
        )
    source = Path(str(candidate["candidate_hdf5_path"])).resolve(strict=True)
    if target.exists():
        raise FileExistsError(f"Partial selected HDF5 already exists: {target}")
    replay_qc_mask = np.load(
        Path(str(candidate["replay_qc_mask_path"])), allow_pickle=False
    )
    local_cycle_mask = np.load(
        Path(str(candidate["local_cycle_mask_path"])), allow_pickle=False
    )
    overlay = apply_source_action_overlays(
        replay_path=source,
        calibrated_source_path=calibrated_source_path,
        replay_qc_mask=replay_qc_mask,
        local_cycle_mask=local_cycle_mask,
    )
    attempt_kind = str(candidate["attempt_kind"])
    evidence_kind = (
        PARTIAL_EVIDENCE_KIND
        if attempt_kind == "strict"
        else CORRECTED_PARTIAL_SALVAGE_EVIDENCE_PROFILE
    )
    lineage = annotate_selected_replay_episode(
        replay_path=source,
        source_episode_id=episode_name,
        calibrated_source_path=calibrated_source_path,
        attempt_id=str(candidate["attempt_uid"]),
        selection_policy=CORRECTED_SELECTION_POLICY,
        evidence_kind=evidence_kind,
    )
    with h5py.File(source, "a") as handle:
        metadata = handle.require_group("metadata")
        metadata.attrs["default_enabled"] = False
        metadata.attrs["salvage_status"] = "local_cycle_only"
        metadata.attrs["local_cycle_mask_policy"] = (
            "source_and_replay_qc_and_local_cycle_v1"
        )
        metadata.attrs["local_realign_guard_seconds"] = LOCAL_GUARD_SECONDS
        metadata.attrs["strict_pool_eligible"] = False
    raw_samples = _read_jsonl(Path(str(candidate["cycle_samples_path"])))
    samples = selected_sidecar_rows(
        raw_samples,
        source_episode_id=episode_name,
        attempt_id=str(candidate["attempt_uid"]),
        selection_policy=CORRECTED_SELECTION_POLICY,
        evidence_kind=evidence_kind,
    )
    eligibility_by_observed = {
        int(row["observed_cycle_index"]): row
        for row in _read_jsonl(Path(str(candidate["local_cycle_eligibility_path"])))
        if row.get("observed_cycle_index") is not None
    }
    for row in samples:
        eligibility = eligibility_by_observed.get(int(row["cycle_index"]), {})
        row["local_cycle_eligible"] = bool(eligibility.get("eligible", False))
        row["matched_source_cycle_id"] = eligibility.get("source_cycle_id")
        row["local_cycle_reason_codes"] = list(
            eligibility.get("reason_codes", ()) or ()
        )
        row["default_enabled"] = False
    _write_jsonl_atomic(sidecar_path, samples)
    digest = sha256_file(source)
    size = int(source.stat().st_size)
    lineage["replay_path"] = str(target.resolve())
    record = {
        "schema": "terrain_replay_partial_salvage_episode_v1",
        "source_episode_id": episode_name,
        "selected_attempt_id": str(candidate["attempt_uid"]),
        "attempt_kind": attempt_kind,
        "selection_policy": CORRECTED_SELECTION_POLICY,
        "evidence_kind": evidence_kind,
        "repeatability_status": "not_assessed_single_attempt",
        "gold_status": "not_gold",
        "default_enabled": False,
        "strict_pool_eligible": False,
        "selected_hdf5_path": str(target.resolve()),
        "sha256": digest,
        "size_bytes": size,
        "eligible_cycle_count": int(candidate["eligible_cycle_count"]),
        "eligible_source_cycle_ids": list(candidate["eligible_source_cycle_ids"]),
        "valid_action_step_count": int(overlay["valid_step_count"]),
        "realign_count": int(candidate["realign_count"]),
        "realign_steps": list(candidate["realign_steps"]),
        "selected_cycle_sample_path": str(sidecar_path.resolve()),
        "selected_cycle_sample_count": len(samples),
        "calibrated_source_path": str(calibrated_source_path.resolve()),
        "action_overlay": overlay,
        "lineage": lineage,
        "gate_path": str(candidate["gate_path"]),
        "diagnostic_path": str(candidate["diagnostic_path"]),
        "local_cycle_eligibility_path": str(
            candidate["local_cycle_eligibility_path"]
        ),
    }
    _write_json_atomic(
        move_intent_path,
        {
            "schema": "terrain_replay_partial_move_intent_v1",
            "source_path": str(source),
            "selected_path": str(target.resolve()),
            "sha256": digest,
            "size_bytes": size,
            "attempt_uid": str(candidate["attempt_uid"]),
            "record": record,
        },
    )
    return _complete_partial_move(
        output_root=output_root,
        episode_id=episode_id,
        intent_path=move_intent_path,
        retention_reason="moved_to_partial_salvage_pool",
    )


def existing_partial_record(
    output_root: Path,
    *,
    episode_id: int,
) -> dict[str, Any] | None:
    """Recover one already finalized partial record on exact resume."""

    paths = list(
        output_root.glob(f"*/episode_{episode_id}/attempt_*/partial_record.json")
    )
    if len(paths) > 1:
        raise HardReplayContractError(
            f"Multiple partial records exist for episode_{episode_id}."
        )
    if not paths:
        intents = list(
            output_root.glob(
                f"*/episode_{episode_id}/attempt_*/partial_move_intent.json"
            )
        )
        if len(intents) > 1:
            raise HardReplayContractError(
                f"Multiple partial move intents exist for episode_{episode_id}."
            )
        if not intents:
            return None
        return _complete_partial_move(
            output_root=output_root,
            episode_id=episode_id,
            intent_path=intents[0],
            retention_reason="recovered_after_partial_move",
        )
    record = _read_json(paths[0])
    selected = Path(str(record["selected_hdf5_path"])).resolve(strict=True)
    if sha256_file(selected) != str(record["sha256"]):
        raise HardReplayContractError(f"Partial HDF5 checksum mismatch: {selected}")
    return record


def _complete_partial_move(
    *,
    output_root: Path,
    episode_id: int,
    intent_path: Path,
    retention_reason: str,
) -> dict[str, Any]:
    """Finish or recover exactly one audited candidate move without replaying it."""

    output = output_root.resolve()
    attempt_dir = intent_path.parent.resolve(strict=True)
    allowed_attempt_dirs = {
        (output / root_name / f"episode_{episode_id}").resolve()
        for root_name in ("strict_attempts", "corrected_attempts")
    }
    if attempt_dir.parent not in allowed_attempt_dirs or not attempt_dir.name.startswith(
        "attempt_"
    ):
        raise HardReplayContractError(
            f"Partial move intent is outside the exact attempt scope: {intent_path}"
        )
    intent = _read_json(intent_path)
    expected_source = (attempt_dir / "recorded" / "episode_0.hdf5").resolve()
    expected_target = (
        output / "partial_salvage_full_hdf5" / f"episode_{episode_id}.hdf5"
    ).resolve()
    source = Path(str(intent.get("source_path", ""))).resolve()
    target = Path(str(intent.get("selected_path", ""))).resolve()
    if source != expected_source or target != expected_target:
        raise HardReplayContractError(
            f"Partial move intent escapes its fixed source or target: {intent_path}"
        )
    record_value = intent.get("record")
    if not isinstance(record_value, Mapping):
        raise HardReplayContractError(
            f"Partial move intent has no recoverable record: {intent_path}"
        )
    record = dict(record_value)
    digest = str(intent.get("sha256", ""))
    size = int(intent.get("size_bytes", -1))
    if (
        str(record.get("source_episode_id")) != f"episode_{episode_id}"
        or Path(str(record.get("selected_hdf5_path", ""))).resolve() != target
        or str(record.get("sha256", "")) != digest
        or int(record.get("size_bytes", -1)) != size
        or bool(record.get("default_enabled", True))
        or bool(record.get("strict_pool_eligible", True))
    ):
        raise HardReplayContractError(
            f"Partial move record disagrees with its intent: {intent_path}"
        )
    source_exists = source.is_file()
    target_exists = target.is_file()
    if source_exists and target_exists:
        raise HardReplayContractError(
            f"Both partial source and target exist during recovery: {intent_path}"
        )
    if source_exists:
        target.parent.mkdir(parents=True, exist_ok=True)
        source.replace(target)
    elif not target_exists:
        raise HardReplayContractError(
            f"Neither partial source nor target exists during recovery: {intent_path}"
        )
    if int(target.stat().st_size) != size or sha256_file(target) != digest:
        raise HardReplayContractError(
            f"Partial HDF5 changed across atomic move: {target}"
        )
    final_record_path = attempt_dir / "partial_record.json"
    if final_record_path.is_file():
        if _read_json(final_record_path) != record:
            raise HardReplayContractError(
                f"Partial record changed after move: {final_record_path}"
            )
    else:
        _write_json_atomic(final_record_path, record)
    retention = {
        "schema": "terrain_replay_candidate_retention_v1",
        "retained": True,
        "reason": retention_reason,
        "attempt_uid": str(intent.get("attempt_uid", "")),
        "final_path": str(target),
    }
    retention_path = attempt_dir / "partial_retention.json"
    if retention_path.is_file():
        stored = _read_json(retention_path)
        if (
            not bool(stored.get("retained", False))
            or str(stored.get("attempt_uid", "")) != retention["attempt_uid"]
            or Path(str(stored.get("final_path", ""))).resolve() != target
        ):
            raise HardReplayContractError(
                f"Partial retention record changed after move: {retention_path}"
            )
    else:
        _write_json_atomic(retention_path, retention)
    return record


def collect_local_cycle_rows(output_root: Path) -> list[dict[str, Any]]:
    """Collect every strict/corrected local-cycle decision for audit."""

    rows = [
        row
        for root_name in ("strict_attempts", "corrected_attempts")
        for path in (output_root / root_name).glob(
            "episode_*/attempt_*/local_cycle_eligibility.jsonl"
        )
        for row in _read_jsonl(path)
    ]
    rows.sort(
        key=lambda row: (
            _episode_number(str(row["source_episode_id"])),
            0 if str(row.get("attempt_kind")) == "strict" else 1,
            str(row.get("attempt_id", "")),
            int(row.get("source_cycle_id", -1)),
        )
    )
    return rows


def _replay_native_cleaning(
    *,
    replay_path: Path,
    replay_config: Path,
    camera_mask: np.ndarray,
) -> dict[str, Any]:
    config = yaml.safe_load(replay_config.read_text(encoding="utf-8")) or {}
    success_cfg = dict(config.get("success", {}) or {})
    reward_cfg = dict(config.get("reward", {}) or {})
    reward_cfg["qualified_dig_start_mode"] = QUALIFIED_DIG_START_MODE_CONTACT_DEPTH
    with h5py.File(replay_path, "r") as handle:
        qpos = np.asarray(handle["observations/qpos"][()], dtype=np.float32)
        qvel = np.asarray(handle["observations/qvel"][()], dtype=np.float32)
        actions = np.asarray(handle["action"][()], dtype=np.float32)
        env_state = np.asarray(handle["observations/env_state"][()], dtype=np.float32)
        step_ids = (
            np.asarray(handle["timestamps/step_id"][()], dtype=np.int64)
            if "timestamps/step_id" in handle
            else None
        )
        step_ns = (
            np.asarray(handle["timestamps/step_ns"][()], dtype=np.int64)
            if "timestamps/step_ns" in handle
            else None
        )
        metadata = dict(handle["metadata"].attrs)
    scenario_id = _text(metadata.get("scenario_id", "")).strip()
    if not scenario_id:
        raise HardReplayContractError(f"Replay is missing scenario_id: {replay_path}")
    v2, _ = label_episode_v2_1(
        qpos=qpos,
        actions=actions,
        env_state=env_state,
        metadata=metadata,
        scenario_id=scenario_id,
        pause_action_eps=0.05,
        reward_cfg=reward_cfg,
        success_cfg=success_cfg,
    )
    cleaning = analyze_episode_cleaning(
        episode_id=0,
        actions=actions,
        qpos=qpos,
        qvel=qvel,
        step_ids=step_ids,
        step_ns=step_ns,
        v2_step=dict(v2.get("step", {}) or {}),
        v2_cycle=dict(v2.get("cycle", {}) or {}),
        camera_step_valid_mask=camera_mask,
    )
    observed_validity = _native_cycle_validity(
        cleaning_cycles=cleaning.cycles,
        candidate_records=_read_jsonl(replay_path.parent.parent / "cycle_samples.jsonl"),
        control_hz=float(metadata.get("control_hz", 50.0)),
    )
    return {
        "action_loss_mask": np.asarray(
            cleaning.default_action_loss_mask, dtype=np.uint8
        ),
        "observed_cycle_validity": observed_validity,
        "summary": {
            "cycle_count": len(cleaning.cycles),
            "eligible_cycle_count": sum(
                bool(row.get("replay_candidate", False))
                and not bool(row.get("review_required", False))
                for row in cleaning.cycles
            ),
            "masked_step_count": int(
                np.count_nonzero(cleaning.default_action_loss_mask == 0)
            ),
            "diagnostics": cleaning.diagnostics,
        },
    }


def _native_cycle_validity(
    *,
    cleaning_cycles: Sequence[Mapping[str, Any]],
    candidate_records: Sequence[Mapping[str, Any]],
    control_hz: float,
) -> dict[int, bool]:
    source_boundaries = [
        (
            int(row["cycle_id"]),
            int(row.get("dump_end_step", int(row["end_step_exclusive"]) - 1)),
        )
        for row in cleaning_cycles
    ]
    source_boundaries.sort(key=lambda item: (item[1], item[0]))
    grouped: dict[int, list[int]] = defaultdict(list)
    for row in candidate_records:
        grouped[int(row["cycle_index"])].append(
            int(row["cycle_end_observation_index"])
        )
    observed = [
        (cycle_index, min(values)) for cycle_index, values in grouped.items()
    ]
    observed.sort(key=lambda item: (item[1], item[0]))
    matches = match_monotonic_boundaries(
        source_boundaries,
        observed,
        tolerance_steps=max(0, int(round(float(control_hz)))),
    )
    clean_by_id = {int(row["cycle_id"]): row for row in cleaning_cycles}
    result = {int(cycle_index): False for cycle_index in grouped}
    for match in matches:
        row = clean_by_id[int(match["source_cycle_id"])]
        result[int(match["observed_cycle_index"])] = bool(
            row.get("replay_candidate", False)
            and not row.get("review_required", False)
            and not row.get("diagnostic_only", False)
        )
    return result


def _remove_candidate_hdf5(
    candidate: Mapping[str, Any],
    *,
    reason: str,
) -> None:
    path = Path(str(candidate["candidate_hdf5_path"]))
    attempt_dir = Path(str(candidate["attempt_dir"]))
    retention_path = attempt_dir / "candidate_retention.json"
    if not path.exists():
        if retention_path.is_file():
            return
        _write_json_atomic(
            retention_path,
            {
                "schema": "terrain_replay_candidate_retention_v1",
                "retained": False,
                "reason": "candidate_hdf5_already_absent",
                "attempt_uid": str(candidate["attempt_uid"]),
            },
        )
        return
    deletion = remove_retained_attempt_hdf5(
        path=path,
        attempts_root=attempt_dir.parents[1],
        attempt_dir=attempt_dir,
        reason=reason,
    )
    _write_json_atomic(
        retention_path,
        {
            "schema": "terrain_replay_candidate_retention_v1",
            "retained": False,
            "reason": str(reason),
            "attempt_uid": str(candidate["attempt_uid"]),
            "deletion": deletion,
        },
    )


def _local_candidates(output_root: Path, *, episode_id: int) -> list[dict[str, Any]]:
    rows = [
        _read_json(path)
        for root_name in ("strict_attempts", "corrected_attempts")
        for path in (output_root / root_name / f"episode_{episode_id}").glob(
            "attempt_*/local_candidate.json"
        )
    ]
    rows.sort(
        key=lambda row: (
            0 if str(row.get("attempt_kind")) == "strict" else 1,
            int(row.get("attempt_index", 0)),
        )
    )
    return rows


def _verify_local_candidate_hdf5(candidate: Mapping[str, Any]) -> None:
    path = Path(str(candidate["candidate_hdf5_path"])).resolve(strict=True)
    if int(path.stat().st_size) != int(candidate["candidate_hdf5_size_bytes"]):
        raise HardReplayContractError(f"Local candidate size changed: {path}")
    if sha256_file(path) != str(candidate["candidate_hdf5_sha256"]):
        raise HardReplayContractError(f"Local candidate checksum changed: {path}")


def _parse_step_list(value: Any) -> tuple[int, ...]:
    text = _text(value).strip()
    if not text:
        return ()
    return tuple(int(item.strip()) for item in text.split(",") if item.strip())


def _episode_number(value: str) -> int:
    return int(str(value).rsplit("_", 1)[1])


def _text(value: Any) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


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
    if path.exists():
        raise FileExistsError(f"No-overwrite output already exists: {path}")
    _write_text_atomic(
        path,
        json.dumps(dict(payload), indent=2, sort_keys=True, allow_nan=False) + "\n",
    )


def _write_jsonl_atomic(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    if path.exists():
        raise FileExistsError(f"No-overwrite output already exists: {path}")
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
    "best_retained_candidate",
    "collect_local_cycle_rows",
    "evaluate_attempt_local_candidate",
    "existing_partial_record",
    "finalize_partial_candidate",
    "remove_all_retained_candidates",
    "retain_only_best_candidate",
]
