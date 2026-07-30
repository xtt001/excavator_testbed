"""Run-contract and attempt policy for selected terrain replay datasets."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import h5py

from testbed.data.action_contract_calibration import (
    CURRENT_EQUIVALENT_ACTION_CONTRACT,
)
from testbed.data.terrain_replay_dataset import (
    safe_remove_failed_attempt_hdf5,
    sha256_file,
)
from testbed.eval.terrain_replay_attempt_runner import (
    build_replay_source_reference,
    run_one_replay_attempt,
)
from testbed.eval.terrain_replay_run_contract import (
    CALIBRATED_SOURCE_ROOT,
    CLEAN_DATASET_ROOT,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_REPLAY_CONFIG,
    HIGH_RISK_EPISODE_IDS,
    MAX_ATTEMPTS,
    RUN_CONTRACT_SCHEMA,
    SMOKE_EPISODE_IDS,
    HardReplayContractError,
    all_source_snapshots,
    build_replay_preflight,
    build_run_contract,
    initialize_run_root,
    ordered_replay_episode_ids,
)
from testbed.eval.terrain_replay_selection import (
    CALIBRATED_MIXED_SELECTION_PROFILE,
    load_replay_selection,
)

SELECTION_POLICY = "first_passing_attempt_v1"
class RepresentativeSmokeReplayError(RuntimeError):
    """Representative replay semantics failed before formal batch execution."""


def resolve_dataset_build_status(
    *,
    batch_stop: Mapping[str, Any] | None,
    stop_after_smokes: bool,
    all_episodes_selected: bool,
) -> str:
    """Map execution outcome to an evidence-accurate dataset status."""

    if batch_stop is not None:
        if str(batch_stop.get("reason", "")) == "representative_smoke_exhausted":
            return "halted_representative_smoke_failure"
        return "halted_hard_contract_error"
    if stop_after_smokes:
        return "smokes_complete"
    return "complete_24_of_24" if all_episodes_selected else "partial"


def _smoke_failures_are_semantic_only(
    episode_results: Sequence[Mapping[str, Any]],
    failed_smoke_episode_ids: Sequence[int],
) -> bool:
    """Allow batch continuation only after fully audited semantic-only exhaustion."""

    failed_ids = {int(value) for value in failed_smoke_episode_ids}
    if not failed_ids:
        return False
    results_by_id: dict[int, Mapping[str, Any]] = {}
    for result in episode_results:
        source_episode_id = str(result.get("source_episode_id", ""))
        try:
            episode_id = int(source_episode_id.rsplit("_", 1)[1])
        except (IndexError, ValueError):
            continue
        results_by_id[episode_id] = result

    for episode_id in failed_ids:
        result = results_by_id.get(episode_id)
        if result is None or str(result.get("status", "")) != "exhausted_no_pass":
            return False
        attempts = list(result.get("attempts", []))
        if int(result.get("attempt_count", -1)) != MAX_ATTEMPTS:
            return False
        if len(attempts) != MAX_ATTEMPTS:
            return False
        for attempt in attempts:
            if int(attempt.get("process_returncode", -1)) != 0:
                return False
            if list(attempt.get("hard_contract_errors", [])):
                return False
            gate_path = Path(str(attempt.get("gate_path", ""))).expanduser()
            if not gate_path.is_file():
                return False
            try:
                gate = json.loads(gate_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                return False
            if bool(gate.get("pass", False)):
                return False
            if not bool(gate.get("process_integrity_pass", False)):
                return False
            if bool(gate.get("semantic_attempt_pass", False)):
                return False
            if not bool(gate.get("hdf5_audit_pass", False)):
                return False
            if list(gate.get("validation_errors", [])):
                return False
            if list(gate.get("failed_checks", [])) != ["semantic_attempt_failed"]:
                return False
    return True


def run_attempt_sequence(
    *,
    run_attempt: Callable[[int], Mapping[str, Any]],
    max_attempts: int = MAX_ATTEMPTS,
    existing_attempts: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Execute attempts serially and stop at the first passing realization."""

    limit = int(max_attempts)
    if limit <= 0:
        raise ValueError("max_attempts must be positive.")
    attempts = [dict(value) for value in existing_attempts]
    if len(attempts) > limit:
        raise ValueError("Existing attempt count exceeds max_attempts.")
    for attempt in attempts:
        if bool(attempt.get("pass", False)):
            return _attempt_sequence_result(attempts, selected=attempt)
    for attempt_index in range(len(attempts), limit):
        attempt = dict(run_attempt(attempt_index))
        expected_id = f"attempt_{attempt_index:02d}"
        if str(attempt.get("attempt_id", "")) != expected_id:
            raise ValueError(
                f"Attempt callback returned {attempt.get('attempt_id')!r}; "
                f"expected {expected_id!r}."
            )
        attempts.append(attempt)
        if bool(attempt.get("pass", False)):
            return _attempt_sequence_result(attempts, selected=attempt)
    return _attempt_sequence_result(attempts, selected=None)


def build_selected_terrain_replay_dataset(
    *,
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    replay_config: str | Path = DEFAULT_REPLAY_CONFIG,
    resume: bool = False,
    max_attempts: int = MAX_ATTEMPTS,
    stop_after_smokes: bool = False,
    continue_after_smoke_semantic_failure: bool = False,
    run_postprocess: bool = True,
) -> dict[str, Any]:
    """Build the fixed 24-source first-passing replay dataset."""

    if int(max_attempts) != MAX_ATTEMPTS:
        raise ValueError(
            f"The approved replay policy fixes max_attempts={MAX_ATTEMPTS}."
        )
    if continue_after_smoke_semantic_failure and not resume:
        raise ValueError(
            "--continue-after-smoke-semantic-failure requires --resume after "
            "an audited representative-smoke run."
        )
    if continue_after_smoke_semantic_failure and stop_after_smokes:
        raise ValueError(
            "--continue-after-smoke-semantic-failure cannot be combined with "
            "--stop-after-smokes."
        )
    output = Path(output_root).expanduser().resolve()
    config = Path(replay_config).expanduser().resolve(strict=True)
    preflight = build_replay_preflight(replay_config=config)
    if not bool(preflight["pass"]):
        raise HardReplayContractError(
            "Replay preflight failed: " + ", ".join(preflight["errors"])
        )
    contract = build_run_contract(
        output_root=output,
        replay_config=config,
        preflight=preflight,
        max_attempts=int(max_attempts),
        selection_policy=SELECTION_POLICY,
    )
    root_state = initialize_run_root(
        output_root=output,
        contract=contract,
        resume=bool(resume),
    )
    _write_json_atomic(output / "preflight.json", preflight)
    source_before_path = output / "source_immutability_before.json"
    current_source_snapshot = all_source_snapshots()
    if source_before_path.exists():
        stored_snapshot = json.loads(source_before_path.read_text(encoding="utf-8"))
        if stored_snapshot != current_source_snapshot:
            raise HardReplayContractError(
                "Readonly source snapshot changed since the run began."
            )
    else:
        _write_json_atomic(source_before_path, current_source_snapshot)

    selection_rows = build_calibrated_selection_rows()
    selection_manifest = output / "calibrated_replay_selection.jsonl"
    _write_or_verify_jsonl(selection_manifest, selection_rows)
    selections = load_replay_selection(
        selection_manifest,
        selection_profile=CALIBRATED_MIXED_SELECTION_PROFILE,
    )
    selection_by_id = {
        int(item.source_episode_id.rsplit("_", 1)[1]): item for item in selections
    }
    expected_ids = set(ordered_replay_episode_ids())
    if set(selection_by_id) != expected_ids:
        raise HardReplayContractError(
            "Selection manifest does not resolve to the fixed 24 episodes."
        )
    cycle_rows_by_id = _rows_by_episode(selection_rows)

    episode_results: list[dict[str, Any]] = []
    hard_stop: dict[str, Any] | None = None
    failed_smoke_episode_ids: list[int] = []
    for episode_id in ordered_replay_episode_ids():
        if episode_id not in SMOKE_EPISODE_IDS and failed_smoke_episode_ids:
            may_continue = bool(continue_after_smoke_semantic_failure) and (
                _smoke_failures_are_semantic_only(
                    episode_results,
                    failed_smoke_episode_ids,
                )
            )
            if not may_continue:
                hard_stop = {
                    "reason": "representative_smoke_exhausted",
                    "episode_ids": failed_smoke_episode_ids,
                }
                break
        if stop_after_smokes and episode_id not in SMOKE_EPISODE_IDS:
            break
        selection = selection_by_id[episode_id]
        episode_dir = output / "attempts" / f"episode_{episode_id}"
        episode_dir.mkdir(parents=True, exist_ok=True)
        episode_result_path = episode_dir / "episode_result.json"
        existing_result = _load_existing_episode_result(
            episode_result_path=episode_result_path,
            output_root=output,
            episode_id=episode_id,
        )
        if existing_result is not None:
            episode_results.append(existing_result)
            if (
                episode_id in SMOKE_EPISODE_IDS
                and existing_result.get("status") != "selected"
            ):
                failed_smoke_episode_ids.append(episode_id)
            continue

        source_reference = build_replay_source_reference(
            source_path=selection.source_path,
            source_episode_id=selection.source_episode_id,
            cycle_rows=cycle_rows_by_id[episode_id],
        )
        existing_attempts = _load_existing_attempts(episode_dir)

        def execute(attempt_index: int) -> Mapping[str, Any]:
            return _run_one_attempt(
                output_root=output,
                episode_id=episode_id,
                selection_manifest=selection_manifest,
                replay_config=config,
                calibrated_source_path=selection.source_path,
                expected_steps=selection.end_step_exclusive,
                source_reference=source_reference,
                attempt_index=attempt_index,
            )

        try:
            sequence = run_attempt_sequence(
                run_attempt=execute,
                max_attempts=int(max_attempts),
                existing_attempts=existing_attempts,
            )
        except HardReplayContractError as exc:
            hard_stop = {
                "reason": "hard_replay_contract_error",
                "episode_id": episode_id,
                "error": str(exc),
            }
            break
        episode_result = {
            **sequence,
            "source_episode_id": f"episode_{episode_id}",
            "calibrated_source_path": str(selection.source_path),
            "source_end_step_exclusive": int(selection.end_step_exclusive),
        }
        _write_json_atomic(episode_result_path, episode_result)
        episode_results.append(episode_result)
        print(
            json.dumps(
                {
                    "episode": f"episode_{episode_id}",
                    "status": episode_result["status"],
                    "attempt_count": episode_result["attempt_count"],
                }
            ),
            flush=True,
        )
        if episode_id in SMOKE_EPISODE_IDS and sequence["status"] != "selected":
            failed_smoke_episode_ids.append(episode_id)

    semantic_smoke_override_applied = bool(
        hard_stop is None
        and continue_after_smoke_semantic_failure
        and _smoke_failures_are_semantic_only(
            episode_results,
            failed_smoke_episode_ids,
        )
    )
    if (
        hard_stop is None
        and failed_smoke_episode_ids
        and not semantic_smoke_override_applied
    ):
        hard_stop = {
            "reason": "representative_smoke_exhausted",
            "episode_ids": failed_smoke_episode_ids,
        }

    inventory = _collect_attempt_inventory(output)
    selected_manifest = _collect_selected_manifest(output, episode_results)
    _write_jsonl_atomic(output / "attempt_inventory.jsonl", inventory)
    _write_jsonl_atomic(output / "selected_manifest.jsonl", selected_manifest)
    selected_samples = _collect_selected_cycle_samples(output, selected_manifest)
    _write_jsonl_atomic(output / "selected_cycle_samples.jsonl", selected_samples)

    selected_ids = {
        int(row["source_episode_id"].rsplit("_", 1)[1]) for row in selected_manifest
    }
    exhausted_ids = sorted(
        int(result["source_episode_id"].rsplit("_", 1)[1])
        for result in episode_results
        if result.get("status") == "exhausted_no_pass"
    )
    postprocess_report: dict[str, Any] | None = None
    if run_postprocess and selected_ids and hard_stop is None and not stop_after_smokes:
        postprocess_report = _run_post_replay_processing(
            output_root=output,
            replay_config=config,
            selected_episode_ids=tuple(sorted(selected_ids)),
            all_episodes_selected=selected_ids == expected_ids,
        )

    source_after = all_source_snapshots()
    source_immutable = source_after == current_source_snapshot
    _write_json_atomic(
        output / "source_immutability_after.json",
        {
            **source_after,
            "matches_before": source_immutable,
        },
    )
    if not source_immutable:
        raise HardReplayContractError("Readonly source files changed during replay.")

    status = resolve_dataset_build_status(
        batch_stop=hard_stop,
        stop_after_smokes=bool(stop_after_smokes),
        all_episodes_selected=selected_ids == expected_ids,
    )
    summary = {
        "schema": "terrain_replay_selected_dataset_summary_v1",
        "status": status,
        "selection_policy": SELECTION_POLICY,
        "evidence_kind": "replay_derived_selected_pass",
        "gold_status": "not_gold",
        "closed_loop_status": "not_run_by_this_builder",
        "output_root": str(output),
        "resumed": bool(root_state["resumed"]),
        "expected_episode_count": 24,
        "selected_episode_count": len(selected_ids),
        "selected_episode_ids": sorted(selected_ids),
        "exhausted_episode_count": len(exhausted_ids),
        "exhausted_episode_ids": exhausted_ids,
        "attempt_count": len(inventory),
        "selected_cycle_sample_count": len(selected_samples),
        "selected_detected_cycle_count": len(selected_samples) // 3,
        "selected_hdf5_size_bytes": sum(
            int(row.get("size_bytes", 0)) for row in selected_manifest
        ),
        "source_immutable": source_immutable,
        "representative_smoke_exhausted_episode_ids": sorted(
            set(failed_smoke_episode_ids)
        ),
        "continued_after_smoke_semantic_failure": (
            semantic_smoke_override_applied
        ),
        "batch_stop": hard_stop,
        "hard_stop": (
            hard_stop
            if hard_stop is not None
            and str(hard_stop.get("reason", "")) == "hard_replay_contract_error"
            else None
        ),
        "postprocess": postprocess_report,
    }
    _write_json_atomic(output / "completion_report.json", summary)
    if hard_stop is not None:
        if str(hard_stop.get("reason", "")) == "representative_smoke_exhausted":
            raise RepresentativeSmokeReplayError(json.dumps(hard_stop, sort_keys=True))
        raise HardReplayContractError(json.dumps(hard_stop, sort_keys=True))
    return summary


def build_calibrated_selection_rows() -> list[dict[str, Any]]:
    """Rewrite clean eligibility rows onto the fixed calibrated 24-source view."""

    clean_rows = _read_jsonl(CLEAN_DATASET_ROOT / "cycle_eligibility.jsonl")
    expected_ids = set(ordered_replay_episode_ids())
    output: list[dict[str, Any]] = []
    present: set[int] = set()
    for row in clean_rows:
        episode_name = str(row.get("source_episode_id", ""))
        try:
            episode_id = int(episode_name.rsplit("_", 1)[1])
        except (IndexError, ValueError):
            continue
        if episode_id not in expected_ids or not bool(
            row.get("replay_candidate", False)
        ):
            continue
        calibrated = (CALIBRATED_SOURCE_ROOT / f"episode_{episode_id}.hdf5").resolve()
        with h5py.File(calibrated, "r") as handle:
            metadata = handle["metadata"].attrs
            raw_source = _text(metadata.get("raw_source_realpath", ""))
            clean_source = _text(metadata.get("vds_source_abs_path", ""))
        output.append(
            {
                **row,
                "source_path": str(calibrated),
                "raw_source_path": raw_source,
                "clean_source_path": clean_source,
                "calibrated_source_path": str(calibrated),
                "action_contract": CURRENT_EQUIVALENT_ACTION_CONTRACT,
                "selection_profile": CALIBRATED_MIXED_SELECTION_PROFILE,
            }
        )
        present.add(episode_id)
    if present != expected_ids:
        missing = sorted(expected_ids - present)
        raise ValueError(f"Fixed calibrated selection has missing episodes: {missing}")
    output.sort(
        key=lambda row: (
            _episode_number(str(row["source_episode_id"])),
            int(row["cycle_id"]),
        )
    )
    return output


def _run_one_attempt(
    *,
    output_root: Path,
    episode_id: int,
    selection_manifest: Path,
    replay_config: Path,
    calibrated_source_path: Path,
    expected_steps: int,
    source_reference: Mapping[str, Any],
    attempt_index: int,
) -> dict[str, Any]:
    """Compatibility facade over the focused replay-attempt runner."""

    return run_one_replay_attempt(
        attempts_root=output_root / "attempts",
        selected_root=output_root / "selected_full_hdf5",
        episode_id=episode_id,
        selection_manifest=selection_manifest,
        replay_config=replay_config,
        calibrated_source_path=calibrated_source_path,
        expected_steps=expected_steps,
        source_reference=source_reference,
        attempt_index=attempt_index,
        attempt_kind="strict",
        failure_hdf5_policy="delete",
    )


def _load_existing_attempts(episode_dir: Path) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for attempt_index in range(MAX_ATTEMPTS):
        attempt_dir = episode_dir / f"attempt_{attempt_index:02d}"
        if not attempt_dir.exists():
            break
        result_path = attempt_dir / "attempt_result.json"
        if not result_path.is_file():
            result = _recover_interrupted_attempt(attempt_dir)
        else:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        if str(result.get("attempt_id", "")) != f"attempt_{attempt_index:02d}":
            raise ValueError(f"Invalid resumed attempt identity: {result_path}")
        attempts.append(result)
    return attempts


def _recover_interrupted_attempt(attempt_dir: Path) -> dict[str, Any]:
    attempt_id = attempt_dir.name
    episode_name = attempt_dir.parent.name
    generated = attempt_dir / "recorded" / "episode_0.hdf5"
    deletion = None
    if generated.is_file():
        _write_json_atomic(
            attempt_dir / "deletion_intent.json",
            {
                "schema": "terrain_replay_failed_hdf5_deletion_intent_v1",
                "path": str(generated.resolve()),
                "size_bytes": int(generated.stat().st_size),
                "reason": "interrupted_attempt_recovery",
            },
        )
        deletion = safe_remove_failed_attempt_hdf5(
            path=generated,
            attempts_root=attempt_dir.parents[1],
        )
        _write_json_atomic(attempt_dir / "deletion_result.json", deletion)
    result = {
        "schema": "terrain_replay_attempt_result_v1",
        "source_episode_id": episode_name,
        "attempt_id": attempt_id,
        "pass": False,
        "status": "interrupted_recovered",
        "process_returncode": None,
        "failed_hdf5_deletion": deletion,
        "hard_contract_errors": [],
    }
    _write_json_atomic(attempt_dir / "attempt_result.json", result)
    return result


def _load_existing_episode_result(
    *, episode_result_path: Path, output_root: Path, episode_id: int
) -> dict[str, Any] | None:
    if episode_result_path.is_file():
        result = json.loads(episode_result_path.read_text(encoding="utf-8"))
        if result.get("status") == "selected":
            selected = output_root / "selected_full_hdf5" / f"episode_{episode_id}.hdf5"
            if not selected.is_file():
                raise ValueError(f"Resume selected HDF5 is missing: {selected}")
        return result
    selected_path = output_root / "selected_full_hdf5" / f"episode_{episode_id}.hdf5"
    if not selected_path.is_file():
        return None
    with h5py.File(selected_path, "r") as handle:
        attempt_id = _text(handle["metadata"].attrs.get("selection_attempt_id", ""))
    attempt_result_path = (
        episode_result_path.parent / attempt_id / "attempt_result.json"
    )
    if not attempt_result_path.is_file():
        raise ValueError(
            f"Selected HDF5 exists without recoverable attempt result: {selected_path}"
        )
    result = {
        "schema": "terrain_replay_attempt_sequence_v1",
        "selection_policy": SELECTION_POLICY,
        "status": "selected",
        "attempt_count": int(attempt_id.rsplit("_", 1)[1]) + 1,
        "selected_attempt_id": attempt_id,
        "attempts": _load_existing_attempts(episode_result_path.parent),
        "source_episode_id": f"episode_{episode_id}",
    }
    _write_json_atomic(episode_result_path, result)
    return result


def _collect_attempt_inventory(output_root: Path) -> list[dict[str, Any]]:
    rows = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(
            (output_root / "attempts").glob("episode_*/attempt_*/attempt_result.json"),
            key=lambda path: (
                _episode_number(path.parents[1].name),
                path.parent.name,
            ),
        )
    ]
    return rows


def _collect_selected_manifest(
    output_root: Path, episode_results: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    del episode_results
    rows = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (output_root / "attempts").glob(
            "episode_*/attempt_*/selected_record.json"
        )
    ]
    rows.sort(key=lambda row: _episode_number(str(row["source_episode_id"])))
    for row in rows:
        selected = Path(str(row["selected_hdf5_path"])).resolve(strict=True)
        if sha256_file(selected) != str(row["sha256"]):
            raise HardReplayContractError(
                f"Selected HDF5 checksum mismatch: {selected}"
            )
        lineage = dict(row.get("lineage", {}) or {})
        lineage["replay_path"] = str(selected)
        row["lineage"] = lineage
    return rows


def _collect_selected_cycle_samples(
    output_root: Path, selected_manifest: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    del output_root
    rows: list[dict[str, Any]] = []
    for selected in selected_manifest:
        path = Path(str(selected["selected_cycle_sample_path"]))
        rows.extend(_read_jsonl(path))
    rows.sort(
        key=lambda row: (
            _episode_number(str(row["source_episode_id"])),
            int(row["cycle_index"]),
            str(row["target_id"]),
        )
    )
    return rows


def _run_post_replay_processing(
    *,
    output_root: Path,
    replay_config: Path,
    selected_episode_ids: tuple[int, ...],
    all_episodes_selected: bool,
) -> dict[str, Any]:
    from testbed.data.terrain_replay_postprocess import (
        build_selected_replay_postprocess,
    )

    return build_selected_replay_postprocess(
        selected_root=output_root / "selected_full_hdf5",
        output_root=output_root,
        label_config_path=replay_config,
        selected_episode_ids=selected_episode_ids,
        complete_inventory=bool(all_episodes_selected),
    )


def _rows_by_episode(
    rows: Sequence[Mapping[str, Any]],
) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        episode_id = _episode_number(str(row["source_episode_id"]))
        grouped.setdefault(episode_id, []).append(dict(row))
    return grouped


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append(value)
    return rows


def _write_or_verify_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    content = _jsonl_content(rows)
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise ValueError(f"Resume JSONL content mismatch: {path}")
        return
    path.write_text(content, encoding="utf-8")


def _write_jsonl_atomic(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    _write_text_atomic(path, _jsonl_content(rows))


def _jsonl_content(rows: Sequence[Mapping[str, Any]]) -> str:
    lines = [json.dumps(dict(row), sort_keys=True, allow_nan=False) for row in rows]
    return "\n".join(lines) + ("\n" if lines else "")


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    _write_text_atomic(
        path,
        json.dumps(dict(payload), indent=2, sort_keys=True, allow_nan=False) + "\n",
    )


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def _episode_number(value: str) -> int:
    return int(str(value).rsplit("_", 1)[1])


def _text(value: Any) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def _attempt_sequence_result(
    attempts: list[dict[str, Any]], *, selected: Mapping[str, Any] | None
) -> dict[str, Any]:
    return {
        "schema": "terrain_replay_attempt_sequence_v1",
        "selection_policy": SELECTION_POLICY,
        "status": "selected" if selected is not None else "exhausted_no_pass",
        "attempt_count": len(attempts),
        "selected_attempt_id": (
            None if selected is None else str(selected.get("attempt_id", ""))
        ),
        "attempts": attempts,
    }


__all__ = [
    "HIGH_RISK_EPISODE_IDS",
    "MAX_ATTEMPTS",
    "RUN_CONTRACT_SCHEMA",
    "RepresentativeSmokeReplayError",
    "SELECTION_POLICY",
    "SMOKE_EPISODE_IDS",
    "initialize_run_root",
    "ordered_replay_episode_ids",
    "resolve_dataset_build_status",
    "run_attempt_sequence",
]
