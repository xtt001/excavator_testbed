"""Top-level orchestration for the fixed seven-episode replay salvage run."""

from __future__ import annotations

import json
import os
import shutil
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from testbed.eval.terrain_replay_attempt_runner import build_replay_source_reference
from testbed.eval.terrain_replay_dataset_builder import build_calibrated_selection_rows
from testbed.eval.terrain_replay_run_contract import (
    DEFAULT_REPLAY_CONFIG,
    HardReplayContractError,
    all_source_snapshots,
)
from testbed.eval.terrain_replay_salvage import (
    CORRECTED_MAX_ATTEMPTS,
    PARENT_SELECTED_EPISODE_IDS,
    SALVAGE_EPISODE_IDS,
    SALVAGE_RUN_CONTRACT_SCHEMA,
    STRICT_ATTEMPT_BUDGETS,
    STRICT_REPLAY_ORDER,
    initialize_salvage_root,
)
from testbed.eval.terrain_replay_salvage_candidates import (
    best_retained_candidate,
    collect_local_cycle_rows,
    existing_partial_record,
    finalize_partial_candidate,
    remove_all_retained_candidates,
)
from testbed.eval.terrain_replay_salvage_execution import (
    collect_attempt_inventory,
    collect_strict_additions,
    run_episode_phase,
)
from testbed.eval.terrain_replay_salvage_outputs import (
    build_final_views,
    postprocess_selected_group,
    summarize_partial_coverage,
)
from testbed.eval.terrain_replay_salvage_preflight import (
    DEFAULT_PARENT_RUN_ROOT,
    DEFAULT_SALVAGE_OUTPUT_ROOT,
    build_existing_failure_diagnosis,
    build_salvage_preflight,
    build_salvage_run_contract,
    verify_parent_after,
)
from testbed.eval.terrain_replay_salvage_views import (
    COMBINED_STRICT_VIEW,
    LAYERED_SALVAGE_VIEW,
    write_salvage_training_configs,
)
from testbed.eval.terrain_replay_selection import (
    CALIBRATED_MIXED_SELECTION_PROFILE,
    load_replay_selection,
)


def build_terrain_replay_salvage_dataset(
    *,
    output_root: str | Path = DEFAULT_SALVAGE_OUTPUT_ROOT,
    replay_config: str | Path = DEFAULT_REPLAY_CONFIG,
    parent_root: str | Path = DEFAULT_PARENT_RUN_ROOT,
    resume: bool = False,
    stop_after_strict: bool = False,
) -> dict[str, Any]:
    """Run fixed strict budgets, then corrected/local salvage and layered views."""

    output = Path(output_root).expanduser().resolve()
    config = Path(replay_config).expanduser().resolve(strict=True)
    parent = Path(parent_root).expanduser().resolve(strict=True)
    preflight = build_salvage_preflight(
        replay_config=config,
        parent_root=parent,
        verify_parent_checksums=True,
    )
    if not bool(preflight["pass"]):
        raise HardReplayContractError(
            "Salvage preflight failed: " + ", ".join(preflight["errors"])
        )
    contract = build_salvage_run_contract(
        output_root=output,
        replay_config=config,
        preflight=preflight,
    )
    root_state = initialize_salvage_root(
        output_root=output,
        contract=contract,
        resume=bool(resume),
    )
    completion_path = output / "completion_report.json"
    if completion_path.is_file():
        completion = _read_json(completion_path)
        if completion.get("run_contract_schema") != SALVAGE_RUN_CONTRACT_SCHEMA:
            raise ValueError("Completed salvage report has a mismatched run contract.")
        return completion

    preflight_path = output / "preflight.json"
    if preflight_path.is_file():
        stored_preflight = _read_json(preflight_path)
        if _stable_preflight_projection(stored_preflight) != (
            _stable_preflight_projection(preflight)
        ):
            raise HardReplayContractError(
                "Stable preflight contracts changed before resume."
            )
    else:
        _write_json_atomic(preflight_path, preflight)

    source_before = all_source_snapshots()
    before_path = output / "source_immutability_before.json"
    _write_or_verify_json(before_path, source_before)
    parent_before = {
        "schema": "terrain_replay_parent_immutability_snapshot_v1",
        "parent_artifacts": dict(preflight["parent_artifacts"]),
        "selected_files": list(preflight["parent_selected_files"]),
    }
    _write_or_verify_json(output / "parent_immutability_before.json", parent_before)

    selection_manifest = output / "calibrated_replay_selection.jsonl"
    _write_or_verify_text(
        selection_manifest,
        (parent / "calibrated_replay_selection.jsonl").read_text(encoding="utf-8"),
    )
    selections = load_replay_selection(
        selection_manifest,
        selection_profile=CALIBRATED_MIXED_SELECTION_PROFILE,
    )
    selection_by_id = {
        _episode_number(item.source_episode_id): item for item in selections
    }
    current_selection_rows = build_calibrated_selection_rows()
    expected_selection_ids = {
        _episode_number(str(row["source_episode_id"]))
        for row in current_selection_rows
    }
    if set(selection_by_id) != expected_selection_ids or not set(
        SALVAGE_EPISODE_IDS
    ).issubset(selection_by_id):
        raise HardReplayContractError(
            "Salvage selection no longer resolves to the fixed calibrated 24."
        )
    selection_rows = _read_jsonl(selection_manifest)
    cycle_rows_by_id = _rows_by_episode(selection_rows)
    diagnosis = build_existing_failure_diagnosis(parent)
    if int(diagnosis["attempt_count"]) != 35:
        raise HardReplayContractError("Expected exactly 35 prior failed attempts.")
    _write_or_verify_json(output / "existing_failure_diagnosis.json", diagnosis)

    runtime_build_id = str(preflight["runtime_contract"]["runtime_build_id"])
    strict_results: list[dict[str, Any]] = []
    for episode_id in STRICT_REPLAY_ORDER:
        selection = selection_by_id[episode_id]
        source_reference = build_replay_source_reference(
            source_path=selection.source_path,
            source_episode_id=selection.source_episode_id,
            cycle_rows=cycle_rows_by_id[episode_id],
        )
        strict_result = run_episode_phase(
            output_root=output,
            attempts_root=output / "strict_attempts",
            selected_root=output / "strict_selected_full_hdf5",
            episode_id=episode_id,
            selection_manifest=selection_manifest,
            replay_config=config,
            calibrated_source_path=selection.source_path,
            expected_steps=int(selection.end_step_exclusive),
            source_reference=source_reference,
            source_cycles=cycle_rows_by_id[episode_id],
            attempt_kind="strict",
            max_attempts=STRICT_ATTEMPT_BUDGETS[episode_id],
            expected_runtime_build_id=runtime_build_id,
            require_first_attempt_technical_smoke=episode_id == 4,
        )
        strict_results.append(strict_result)

    strict_ids = sorted(
        _episode_number(str(row["source_episode_id"]))
        for row in strict_results
        if row.get("status") == "selected"
    )
    strict_phase = {
        "schema": "terrain_replay_salvage_strict_phase_v1",
        "status": "complete",
        "strict_attempt_count": sum(
            int(row.get("attempt_count", 0)) for row in strict_results
        ),
        "strict_addition_episode_ids": strict_ids,
        "strict_addition_count": len(strict_ids),
        "strict_exhausted_episode_ids": sorted(
            set(SALVAGE_EPISODE_IDS) - set(strict_ids)
        ),
        "episode_results": strict_results,
    }
    _write_or_verify_json(output / "strict_phase_report.json", strict_phase)
    if stop_after_strict:
        return {
            **strict_phase,
            "status": "strict_phase_complete",
            "output_root": str(output),
            "resumed": bool(root_state["resumed"]),
        }

    corrected_results = _run_corrected_phases(
        output=output,
        config=config,
        selection_manifest=selection_manifest,
        selection_by_id=selection_by_id,
        cycle_rows_by_id=cycle_rows_by_id,
        strict_ids=set(strict_ids),
        runtime_build_id=runtime_build_id,
    )
    partial_rows = _finalize_partial_pool(
        output=output,
        selection_by_id=selection_by_id,
        strict_ids=set(strict_ids),
    )

    strict_additions = collect_strict_additions(output)
    _write_or_verify_jsonl(
        output / "strict_additions_manifest.jsonl", strict_additions
    )
    _write_or_verify_jsonl(output / "partial_salvage_manifest.jsonl", partial_rows)
    local_rows = collect_local_cycle_rows(output)
    _write_or_verify_jsonl(output / "local_cycle_eligibility.jsonl", local_rows)
    inventory = collect_attempt_inventory(output)
    _write_or_verify_jsonl(output / "attempt_inventory.jsonl", inventory)

    strict_clean = postprocess_selected_group(
        output_root=output,
        selected_root=output / "strict_selected_full_hdf5",
        episode_ids=tuple(sorted(strict_ids)),
        replay_config=config,
        group_name="strict_additions",
        evidence_kind="replay_derived_selected_pass",
    )
    partial_ids = tuple(
        sorted(_episode_number(str(row["source_episode_id"])) for row in partial_rows)
    )
    partial_clean = postprocess_selected_group(
        output_root=output,
        selected_root=output / "partial_salvage_full_hdf5",
        episode_ids=partial_ids,
        replay_config=config,
        group_name="partial_salvage",
        evidence_kind="layered_partial_replay_salvage_v1",
    )
    view_report = build_final_views(
        output_root=output,
        parent_root=parent,
        strict_addition_ids=tuple(strict_ids),
        strict_clean_dir=strict_clean,
        partial_ids=partial_ids,
        partial_clean_dir=partial_clean,
    )

    strict_total_ids = tuple(sorted((*PARENT_SELECTED_EPISODE_IDS, *strict_ids)))
    layered_ids = tuple(sorted((*strict_total_ids, *partial_ids)))
    training_configs = write_salvage_training_configs(
        output_root=output,
        combined_strict_dir=output / COMBINED_STRICT_VIEW,
        layered_salvage_dir=output / LAYERED_SALVAGE_VIEW,
        strict_episode_ids=strict_total_ids,
        layered_episode_ids=layered_ids,
    )
    exhausted_ids = sorted(set(SALVAGE_EPISODE_IDS) - set(strict_ids))
    rerecord = {
        "schema": "terrain_replay_rerecord_recommendation_v1",
        "recommended_episode_ids": [
            value for value in (14, 20) if value in set(exhausted_ids)
        ],
        "reason": "strict_replay_exhausted_after_automatic_salvage",
        "automatic_salvage_blocks_other_results": False,
    }
    _write_or_verify_json(output / "rerecord_recommendation.json", rerecord)

    source_after = all_source_snapshots()
    source_immutable = source_after == source_before
    _write_or_verify_json(
        output / "source_immutability_after.json",
        {**source_after, "matches_before": source_immutable},
    )
    parent_after = verify_parent_after(preflight)
    _write_or_verify_json(output / "parent_immutability_after.json", parent_after)
    if not source_immutable or not bool(parent_after["matches_before"]):
        raise HardReplayContractError("Protected source or parent replay data changed.")

    strict_total = len(strict_total_ids)
    status = "complete_24_of_24" if strict_total == 24 else "partial"
    disk = shutil.disk_usage(output.parent)
    partial_coverage = summarize_partial_coverage(partial_rows)
    report = {
        "schema": "terrain_replay_salvage_completion_v1",
        "run_contract_schema": SALVAGE_RUN_CONTRACT_SCHEMA,
        "status": status,
        "default_training_enabled": strict_total == 24,
        "output_root": str(output),
        "parent_strict_count": len(PARENT_SELECTED_EPISODE_IDS),
        "strict_addition_count": len(strict_ids),
        "strict_addition_episode_ids": strict_ids,
        "strict_total_count": strict_total,
        "strict_total_episode_ids": list(strict_total_ids),
        "strict_exhausted_count": len(exhausted_ids),
        "strict_exhausted_episode_ids": exhausted_ids,
        "partial_candidate_count": len(partial_rows),
        "partial_candidate_episode_ids": list(partial_ids),
        "local_eligible_cycle_count": partial_coverage["eligible_cycle_count"],
        "local_valid_action_step_count": partial_coverage["valid_action_step_count"],
        "all_attempt_local_eligible_cycle_count": sum(
            bool(row.get("eligible", False)) for row in local_rows
        ),
        "local_cycle_audit_row_count": len(local_rows),
        "strict_attempt_count": sum(
            row.get("attempt_kind") == "strict" for row in inventory
        ),
        "corrected_attempt_count": sum(
            row.get("attempt_kind") == "corrected" for row in inventory
        ),
        "attempt_count": len(inventory),
        "corrected_episode_results": corrected_results,
        "rerecord_recommendation": rerecord,
        "views": view_report,
        "training_configs": {key: str(value) for key, value in training_configs.items()},
        "source_immutable": source_immutable,
        "parent_immutable": bool(parent_after["matches_before"]),
        "selected_hdf5_size_bytes": sum(
            int(row.get("size_bytes", 0)) for row in (*strict_additions, *partial_rows)
        ),
        "disk_free_bytes": int(disk.free),
        "gold_status": "not_gold",
        "closed_loop_status": "not_run_by_this_builder",
        "planner_fields_status": "missing_not_generated_by_replay",
    }
    _write_or_verify_json(completion_path, report)
    return report


def _run_corrected_phases(
    *,
    output: Path,
    config: Path,
    selection_manifest: Path,
    selection_by_id: Mapping[int, Any],
    cycle_rows_by_id: Mapping[int, Sequence[Mapping[str, Any]]],
    strict_ids: set[int],
    runtime_build_id: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for episode_id in STRICT_REPLAY_ORDER:
        if episode_id in strict_ids:
            continue
        selection = selection_by_id[episode_id]
        source_reference = build_replay_source_reference(
            source_path=selection.source_path,
            source_episode_id=selection.source_episode_id,
            cycle_rows=cycle_rows_by_id[episode_id],
        )
        results.append(
            run_episode_phase(
                output_root=output,
                attempts_root=output / "corrected_attempts",
                selected_root=output / "strict_selected_full_hdf5",
                episode_id=episode_id,
                selection_manifest=selection_manifest,
                replay_config=config,
                calibrated_source_path=selection.source_path,
                expected_steps=int(selection.end_step_exclusive),
                source_reference=source_reference,
                source_cycles=cycle_rows_by_id[episode_id],
                attempt_kind="corrected",
                max_attempts=CORRECTED_MAX_ATTEMPTS,
                expected_runtime_build_id=runtime_build_id,
            )
        )
    return results


def _finalize_partial_pool(
    *,
    output: Path,
    selection_by_id: Mapping[int, Any],
    strict_ids: set[int],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for episode_id in STRICT_REPLAY_ORDER:
        if episode_id in strict_ids:
            remove_all_retained_candidates(output, episode_id=episode_id)
            continue
        existing = existing_partial_record(output, episode_id=episode_id)
        if existing is not None:
            rows.append(existing)
            continue
        candidate = best_retained_candidate(output, episode_id=episode_id)
        if candidate is None:
            continue
        rows.append(
            finalize_partial_candidate(
                output_root=output,
                candidate=candidate,
                calibrated_source_path=selection_by_id[episode_id].source_path,
            )
        )
    return rows


def _stable_preflight_projection(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "parent_root": payload.get("parent_root"),
        "parent_inventory": payload.get("parent_inventory"),
        "parent_artifacts": payload.get("parent_artifacts"),
        "parent_selected_files": payload.get("parent_selected_files"),
        "runtime_contract": payload.get("runtime_contract"),
        "source_files": payload.get("source_files"),
    }


def _rows_by_episode(
    rows: Sequence[Mapping[str, Any]],
) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_episode_number(str(row["source_episode_id"]))].append(dict(row))
    return dict(grouped)


def _episode_number(value: str) -> int:
    return int(str(value).rsplit("_", 1)[1])


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


def _write_or_verify_json(path: Path, payload: Mapping[str, Any]) -> None:
    content = json.dumps(dict(payload), indent=2, sort_keys=True, allow_nan=False) + "\n"
    _write_or_verify_text(path, content)


def _write_or_verify_jsonl(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    content = "\n".join(
        json.dumps(dict(row), sort_keys=True, allow_nan=False) for row in rows
    )
    _write_or_verify_text(path, content + ("\n" if content else ""))


def _write_or_verify_text(path: Path, content: str) -> None:
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise ValueError(f"Resume artifact content mismatch: {path}")
        return
    _write_text_atomic(path, content)


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"No-overwrite output already exists: {path}")
    _write_text_atomic(
        path,
        json.dumps(dict(payload), indent=2, sort_keys=True, allow_nan=False) + "\n",
    )


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


__all__ = [
    "DEFAULT_PARENT_RUN_ROOT",
    "DEFAULT_SALVAGE_OUTPUT_ROOT",
    "build_existing_failure_diagnosis",
    "build_salvage_preflight",
    "build_salvage_run_contract",
    "build_terrain_replay_salvage_dataset",
]
