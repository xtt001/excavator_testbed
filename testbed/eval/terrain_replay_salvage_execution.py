"""Execute and exactly resume strict or corrected replay salvage phases."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from testbed.data.terrain_replay_dataset import sha256_file
from testbed.eval.terrain_replay_attempt_runner import (
    remove_retained_attempt_hdf5,
    run_one_replay_attempt,
)
from testbed.eval.terrain_replay_run_contract import HardReplayContractError
from testbed.eval.terrain_replay_salvage_candidates import (
    evaluate_attempt_local_candidate,
    remove_all_retained_candidates,
    retain_only_best_candidate,
)


def run_episode_phase(
    *,
    output_root: Path,
    attempts_root: Path,
    selected_root: Path,
    episode_id: int,
    selection_manifest: Path,
    replay_config: Path,
    calibrated_source_path: Path,
    expected_steps: int,
    source_reference: Mapping[str, Any],
    source_cycles: Sequence[Mapping[str, Any]],
    attempt_kind: str,
    max_attempts: int,
    expected_runtime_build_id: str,
    require_first_attempt_technical_smoke: bool = False,
) -> dict[str, Any]:
    """Run one fixed phase, counting interrupted attempts without replaying them."""

    episode_dir = attempts_root / f"episode_{episode_id}"
    episode_dir.mkdir(parents=True, exist_ok=True)
    result_path = episode_dir / f"{attempt_kind}_episode_result.json"
    attempts = _load_attempt_results(
        attempts_root=attempts_root,
        selected_root=selected_root,
        episode_id=episode_id,
        attempt_kind=attempt_kind,
        max_attempts=max_attempts,
    )
    if require_first_attempt_technical_smoke and attempts:
        _record_first_attempt_technical_smoke(
            output_root=output_root,
            episode_id=episode_id,
            result=attempts[0],
        )
    if result_path.is_file():
        stored = _read_json(result_path)
        if int(stored.get("attempt_count", -1)) != len(attempts):
            raise ValueError(f"Resume phase result no longer matches attempts: {result_path}")
        return stored

    for result in attempts:
        retained = result.get("retained_hdf5_path")
        local_path = Path(str(result["gate_path"])).parent / "local_candidate.json"
        if (
            bool(result.get("candidate_technical_pass", False))
            and retained
            and Path(str(retained)).is_file()
            and not local_path.is_file()
        ):
            local = evaluate_attempt_local_candidate(
                attempt_result=result,
                calibrated_source_path=calibrated_source_path,
                source_cycles=source_cycles,
                replay_config=replay_config,
            )
            retain_only_best_candidate(output_root, candidate=local)

    if attempt_kind == "strict":
        passing = next((row for row in attempts if bool(row.get("pass", False))), None)
        if passing is not None:
            result = _phase_result(
                episode_id=episode_id,
                attempt_kind=attempt_kind,
                attempts=attempts,
                selected=passing,
                max_attempts=max_attempts,
            )
            _write_json_atomic(result_path, result)
            return result

    for attempt_index in range(len(attempts), int(max_attempts)):
        result = run_one_replay_attempt(
            attempts_root=attempts_root,
            selected_root=selected_root,
            episode_id=episode_id,
            selection_manifest=selection_manifest,
            replay_config=replay_config,
            calibrated_source_path=calibrated_source_path,
            expected_steps=int(expected_steps),
            source_reference=source_reference,
            attempt_index=attempt_index,
            attempt_kind=attempt_kind,
            failure_hdf5_policy="retain",
            expected_runtime_build_id=expected_runtime_build_id,
        )
        attempts.append(result)
        if require_first_attempt_technical_smoke and len(attempts) == 1:
            _record_first_attempt_technical_smoke(
                output_root=output_root,
                episode_id=episode_id,
                result=result,
            )
        if bool(result.get("pass", False)):
            remove_all_retained_candidates(output_root, episode_id=episode_id)
            break
        if bool(result.get("candidate_technical_pass", False)) and result.get(
            "retained_hdf5_path"
        ):
            local = evaluate_attempt_local_candidate(
                attempt_result=result,
                calibrated_source_path=calibrated_source_path,
                source_cycles=source_cycles,
                replay_config=replay_config,
            )
            retain_only_best_candidate(output_root, candidate=local)

    selected = (
        next((row for row in attempts if bool(row.get("pass", False))), None)
        if attempt_kind == "strict"
        else None
    )
    result = _phase_result(
        episode_id=episode_id,
        attempt_kind=attempt_kind,
        attempts=attempts,
        selected=selected,
        max_attempts=max_attempts,
    )
    _write_json_atomic(result_path, result)
    print(
        json.dumps(
            {
                "event": "salvage_episode_phase_end",
                "source_episode_id": f"episode_{episode_id}",
                "attempt_kind": attempt_kind,
                "status": result["status"],
                "attempt_count": result["attempt_count"],
            }
        ),
        flush=True,
    )
    return result


def _record_first_attempt_technical_smoke(
    *,
    output_root: Path,
    episode_id: int,
    result: Mapping[str, Any],
) -> None:
    """Persist and enforce the one-attempt technical gate before batch replay."""

    technical_pass = bool(
        result.get("candidate_technical_pass", False) or result.get("pass", False)
    )
    smoke = {
        "schema": "terrain_replay_salvage_live_smoke_v1",
        "source_episode_id": f"episode_{episode_id}",
        "attempt_id": str(result.get("attempt_id", "")),
        "technical_contract_pass": technical_pass,
        "strict_semantic_pass": bool(result.get("pass", False)),
        "hard_contract_errors": list(result.get("hard_contract_errors", ()) or ()),
    }
    path = output_root / "episode_4_live_smoke.json"
    if path.is_file():
        if _read_json(path) != smoke:
            raise HardReplayContractError(
                f"Stored live smoke result changed before resume: {path}"
            )
    else:
        _write_json_atomic(path, smoke)
    if not technical_pass:
        raise HardReplayContractError(
            "episode_4 live smoke did not produce a technically auditable HDF5."
        )


def collect_strict_additions(output_root: Path) -> list[dict[str, Any]]:
    """Collect and checksum every new strict selected record."""

    rows = [
        _read_json(path)
        for path in (output_root / "strict_attempts").glob(
            "episode_*/attempt_*/selected_record.json"
        )
    ]
    rows.sort(key=lambda row: _episode_number(str(row["source_episode_id"])))
    for row in rows:
        path = Path(str(row["selected_hdf5_path"])).resolve(strict=True)
        if sha256_file(path) != str(row["sha256"]):
            raise HardReplayContractError(f"Strict addition checksum mismatch: {path}")
    return rows


def collect_attempt_inventory(output_root: Path) -> list[dict[str, Any]]:
    """Collect both strict and corrected attempt results in stable order."""

    rows = [
        _read_json(path)
        for root_name in ("strict_attempts", "corrected_attempts")
        for path in (output_root / root_name).glob(
            "episode_*/attempt_*/attempt_result.json"
        )
    ]
    rows.sort(
        key=lambda row: (
            _episode_number(str(row["source_episode_id"])),
            0 if str(row.get("attempt_kind")) == "strict" else 1,
            int(row.get("attempt_index", 0)),
        )
    )
    return rows


def _phase_result(
    *,
    episode_id: int,
    attempt_kind: str,
    attempts: Sequence[Mapping[str, Any]],
    selected: Mapping[str, Any] | None,
    max_attempts: int,
) -> dict[str, Any]:
    return {
        "schema": "terrain_replay_salvage_attempt_sequence_v1",
        "source_episode_id": f"episode_{episode_id}",
        "attempt_kind": str(attempt_kind),
        "selection_policy": (
            "first_passing_attempt_v1"
            if attempt_kind == "strict"
            else "local_candidate_generation_only"
        ),
        "status": (
            "selected"
            if selected is not None
            else (
                "exhausted_no_pass"
                if len(attempts) == int(max_attempts)
                else "incomplete"
            )
        ),
        "attempt_count": len(attempts),
        "max_attempts": int(max_attempts),
        "selected_attempt_id": (
            None if selected is None else str(selected.get("attempt_id", ""))
        ),
        "attempts": [dict(row) for row in attempts],
    }


def _load_attempt_results(
    *,
    attempts_root: Path,
    selected_root: Path,
    episode_id: int,
    attempt_kind: str,
    max_attempts: int,
) -> list[dict[str, Any]]:
    episode_dir = attempts_root / f"episode_{episode_id}"
    dirs = sorted(
        [path for path in episode_dir.glob("attempt_*") if path.is_dir()],
        key=lambda path: path.name,
    )
    expected_names = [f"attempt_{index:02d}" for index in range(len(dirs))]
    if [path.name for path in dirs] != expected_names:
        raise ValueError(f"Attempt directory sequence has a gap: {episode_dir}")
    if len(dirs) > int(max_attempts):
        raise ValueError(f"Attempt inventory exceeds fixed budget: {episode_dir}")
    results: list[dict[str, Any]] = []
    for index, attempt_dir in enumerate(dirs):
        result_path = attempt_dir / "attempt_result.json"
        if not result_path.is_file():
            _recover_interrupted_attempt(
                attempts_root=attempts_root,
                selected_root=selected_root,
                episode_id=episode_id,
                attempt_kind=attempt_kind,
                attempt_index=index,
                attempt_dir=attempt_dir,
            )
        result = _read_json(result_path)
        if str(result.get("source_episode_id", "")) != f"episode_{episode_id}":
            raise ValueError(f"Resumed attempt episode mismatch: {result_path}")
        if str(result.get("attempt_id", "")) != f"attempt_{index:02d}":
            raise ValueError(f"Resumed attempt index mismatch: {result_path}")
        if str(result.get("attempt_kind", "strict")) != attempt_kind:
            raise ValueError(f"Resumed attempt kind mismatch: {result_path}")
        if result.get("retained_hdf5_path"):
            path = Path(str(result["retained_hdf5_path"]))
            if path.is_file() and (
                int(path.stat().st_size) != int(result["retained_hdf5_size_bytes"])
                or sha256_file(path) != str(result["retained_hdf5_sha256"])
            ):
                raise HardReplayContractError(
                    f"Retained HDF5 changed before resume: {path}"
                )
        selected_record = result.get("selected_record")
        if selected_record:
            selected_path = Path(str(selected_record["selected_hdf5_path"]))
            if not selected_path.is_file() or sha256_file(selected_path) != str(
                selected_record["sha256"]
            ):
                raise HardReplayContractError(
                    f"Selected strict HDF5 changed before resume: {selected_path}"
                )
        results.append(result)
    return results


def _recover_interrupted_attempt(
    *,
    attempts_root: Path,
    selected_root: Path,
    episode_id: int,
    attempt_kind: str,
    attempt_index: int,
    attempt_dir: Path,
) -> None:
    attempt_id = f"attempt_{attempt_index:02d}"
    checkpoint_path = attempt_dir / "attempt_checkpoint.json"
    checkpoint = _read_json(checkpoint_path) if checkpoint_path.is_file() else {}
    intent_path = attempt_dir / "selection_intent.json"
    selected_path = selected_root / f"episode_{episode_id}.hdf5"
    selected_record: dict[str, Any] | None = None
    selected_record_path = attempt_dir / "selected_record.json"
    if intent_path.is_file() and selected_path.is_file():
        intent = _read_json(intent_path)
        if int(selected_path.stat().st_size) != int(intent["size_bytes"]):
            raise HardReplayContractError(
                f"Interrupted selected HDF5 size mismatch: {selected_path}"
            )
        if sha256_file(selected_path) != str(intent["sha256"]):
            raise HardReplayContractError(
                f"Interrupted selected HDF5 checksum mismatch: {selected_path}"
            )
        selected_record = (
            _read_json(selected_record_path)
            if selected_record_path.is_file()
            else {
                "schema": "terrain_replay_selected_episode_v1",
                "source_episode_id": f"episode_{episode_id}",
                "selected_attempt_id": attempt_id,
                "selection_policy": "first_passing_attempt_v1",
                "evidence_kind": "replay_derived_selected_pass",
                "repeatability_status": "not_assessed_single_attempt",
                "gold_status": "not_gold",
                "selected_hdf5_path": str(selected_path.resolve()),
                "sha256": str(intent["sha256"]),
                "size_bytes": int(intent["size_bytes"]),
                "selected_cycle_sample_path": str(
                    (attempt_dir / "selected_cycle_samples.jsonl").resolve()
                ),
            }
        )
        if not selected_record_path.is_file():
            _write_json_atomic(selected_record_path, selected_record)
    generated = attempt_dir / "recorded" / "episode_0.hdf5"
    deletion = None
    if generated.is_file():
        required = (
            attempt_dir / "gate.json",
            attempt_dir / "hdf5_audit.json",
            attempt_dir / "diagnostics.jsonl",
        )
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise HardReplayContractError(
                "Interrupted generated HDF5 is preserved because audit artifacts "
                f"are missing: {missing}"
            )
        deletion = remove_retained_attempt_hdf5(
            path=generated,
            attempts_root=attempts_root,
            attempt_dir=attempt_dir,
            reason="interrupted_attempt_recovery",
        )
    result = {
        "schema": "terrain_replay_attempt_result_v2",
        "source_episode_id": f"episode_{episode_id}",
        "attempt_id": attempt_id,
        "attempt_index": int(attempt_index),
        "attempt_kind": attempt_kind,
        "control_compatibility_profile": checkpoint.get(
            "control_compatibility_profile", ""
        ),
        "replay_evidence_profile": checkpoint.get("replay_evidence_profile", ""),
        "pass": selected_record is not None,
        "strict_gate_pass": bool(selected_record is not None),
        "candidate_technical_pass": False,
        "status": "selected_recovered" if selected_record else "interrupted_recovered",
        "process_returncode": checkpoint.get("process_returncode"),
        "expected_step_count": checkpoint.get("expected_step_count"),
        "gate_path": str((attempt_dir / "gate.json").resolve()),
        "diagnostic_path": str((attempt_dir / "diagnostics.jsonl").resolve()),
        "cycle_samples_path": str((attempt_dir / "cycle_samples.jsonl").resolve()),
        "retained_hdf5_path": None,
        "retained_hdf5_sha256": None,
        "retained_hdf5_size_bytes": None,
        "selected_record": selected_record,
        "selected_cycle_sample_count": 0,
        "failed_hdf5_deletion": deletion,
        "hard_contract_errors": list(checkpoint.get("hard_contract_errors", ()) or ()),
        "recovery_status": "counted_without_replay_repeat",
    }
    _write_json_atomic(attempt_dir / "attempt_result.json", result)


def _episode_number(value: str) -> int:
    return int(str(value).rsplit("_", 1)[1])


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"No-overwrite output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(
        json.dumps(dict(payload), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


__all__ = [
    "collect_attempt_inventory",
    "collect_strict_additions",
    "run_episode_phase",
]
