"""Derive frozen A/B target and reset lineage from one bounded rollout."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from testbed.eval.wall_contact_artifact_io import (
    artifact_ref,
    is_sha256,
    load_json,
    mapping,
    required_file,
    validate_reset_state,
    vector,
    write_json_x,
)

_BUCKET_TIP_SLICE = slice(28, 31)
_TERRAIN_DEPTH_SLICE = slice(39, 45)
_REMAINING_MASS_INDEX = 97


class WallContactABLineageError(RuntimeError):
    """Raised when the frozen rollout cannot prove the target handoff."""


def build_ab_lineage(
    *,
    rollout_jsonl_path: str | Path,
    planner_trace_path: str | Path,
    target_episode_id: str,
    target_raw_fields_sha256: str,
    target_cycle_index: int,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Write create-new handoff and expected-reset artifacts."""

    rollout_path = required_file(rollout_jsonl_path, "bounded_rollout_jsonl")
    trace_path = required_file(planner_trace_path, "bounded_planner_trace")
    episode_id = str(target_episode_id).strip()
    raw_sha = str(target_raw_fields_sha256).strip().lower()
    cycle_index = int(target_cycle_index)
    if not episode_id or not is_sha256(raw_sha) or cycle_index <= 0:
        raise WallContactABLineageError("target_lineage_arguments_invalid")

    rows = _read_jsonl(rollout_path)
    trace = load_json(trace_path)
    corridor_id = _target_corridor(
        trace,
        episode_id=episode_id,
        raw_sha=raw_sha,
        cycle_index=cycle_index,
    )
    dig_index = _first_target_dig_index(
        rows,
        episode_id=episode_id,
        raw_sha=raw_sha,
        cycle_index=cycle_index,
    )
    if dig_index == 0:
        raise WallContactABLineageError("target_dig_has_no_pre_action_row")
    handoff_index = dig_index - 1
    handoff_row = rows[handoff_index]
    dig_row = rows[dig_index]
    _validate_adjacent_rows(handoff_row, dig_row)

    source_lock = {
        "bounded_rollout_jsonl": artifact_ref(rollout_path),
        "planner_trace": artifact_ref(trace_path),
    }
    handoff = {
        "schema": "episode_168_bounded_handoff_v1",
        "exemplar_id": episode_id,
        "raw_fields_sha256": raw_sha,
        "cycle_index": cycle_index,
        "selection_event_cycle_index": cycle_index - 1,
        "corridor_id": corridor_id,
        "handoff_row_index": handoff_index,
        "handoff_t": int(handoff_row.get("t", -1)),
        "handoff_step_id": int(handoff_row.get("step_id", -1)),
        "first_dig_row_index": dig_index,
        "first_dig_t": int(dig_row.get("t", -1)),
        "first_dig_step_id": int(dig_row.get("step_id", -1)),
        **_state_from_row(handoff_row, "target_handoff"),
        "source_lock": source_lock,
    }
    reset = {
        "schema": "wall_contact_expected_reset_state_v1",
        "checkpoint_semantics": "first_post_reset_control_step",
        "reset_row_index": 0,
        "reset_t": int(rows[0].get("t", -1)),
        "reset_step_id": int(rows[0].get("step_id", -1)),
        **_state_from_row(rows[0], "expected_reset"),
        "source_lock": source_lock,
    }
    validate_reset_state(handoff)
    validate_reset_state(reset)

    destination = Path(output_dir).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite {destination}")
    destination.mkdir(parents=True, exist_ok=False)
    handoff_path = destination / "frozen_target_handoff.json"
    reset_path = destination / "expected_reset_state.json"
    write_json_x(handoff_path, handoff)
    write_json_x(reset_path, reset)
    manifest = {
        "schema": "wall_contact_ab_lineage_v1",
        "status": "passed",
        "diagnostic_only": True,
        "frozen_target_handoff": artifact_ref(handoff_path),
        "expected_reset_state": artifact_ref(reset_path),
        "source_lock": source_lock,
    }
    write_json_x(destination / "manifest.json", manifest)
    return manifest


def _read_jsonl(path: Path) -> list[Mapping[str, Any]]:
    rows: list[Mapping[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            rows.append(mapping(json.loads(line), f"rollout_line_{line_number}"))
        except json.JSONDecodeError as exc:
            raise WallContactABLineageError(
                f"rollout_jsonl_invalid:{line_number}"
            ) from exc
    if not rows:
        raise WallContactABLineageError("bounded_rollout_empty")
    return rows


def _target_corridor(
    trace: Mapping[str, Any],
    *,
    episode_id: str,
    raw_sha: str,
    cycle_index: int,
) -> int:
    events = trace.get("coverage_decision_trace")
    if not isinstance(events, list):
        raise WallContactABLineageError("planner_decision_trace_missing")
    matches = [
        mapping(item, "coverage_decision_event")
        for item in events
        if isinstance(item, Mapping)
        and item.get("exemplar_id") == episode_id
        and str(item.get("raw_fields_sha256", "")).lower() == raw_sha
    ]
    if len(matches) != 1:
        raise WallContactABLineageError("target_planner_lineage_not_unique")
    event = matches[0]
    if int(event.get("cycle_index", -1)) != cycle_index - 1:
        raise WallContactABLineageError("target_planner_selection_cycle_drift")
    for key in ("corridor_id", "coverage_corridor_id", "selected_corridor_id"):
        if key in event:
            return int(event[key])
    raise WallContactABLineageError("target_corridor_id_missing")


def _first_target_dig_index(
    rows: list[Mapping[str, Any]],
    *,
    episode_id: str,
    raw_sha: str,
    cycle_index: int,
) -> int:
    for index, row in enumerate(rows):
        skill = str(row.get("skill_name", row.get("hybrid_mode", "")))
        cycle = int(
            row.get(
                "primitive_cycle_index",
                row.get("cycle_id", -1),
            )
        )
        if skill != "dig" or cycle != cycle_index:
            continue
        row_episode = str(row.get("coverage_execution_exemplar_id", ""))
        row_sha = str(row.get("coverage_execution_raw_fields_sha256", "")).lower()
        if row_episode and row_episode != episode_id:
            raise WallContactABLineageError("target_dig_episode_drift")
        if row_sha and row_sha != raw_sha:
            raise WallContactABLineageError("target_dig_raw_sha_drift")
        return index
    raise WallContactABLineageError("target_dig_policy_input_missing")


def _validate_adjacent_rows(
    handoff: Mapping[str, Any],
    dig: Mapping[str, Any],
) -> None:
    for key in ("t", "step_id"):
        if key in handoff and key in dig and int(dig[key]) != int(handoff[key]) + 1:
            raise WallContactABLineageError(f"target_handoff_{key}_not_adjacent")


def _state_from_row(row: Mapping[str, Any], label: str) -> dict[str, Any]:
    env = row.get("env_state")
    if not isinstance(env, list) or len(env) <= _REMAINING_MASS_INDEX:
        raise WallContactABLineageError(f"{label}_env_state_invalid")
    return {
        "qpos": vector(row.get("qpos"), 4, f"{label}.qpos"),
        "qvel": vector(row.get("qvel"), 4, f"{label}.qvel"),
        "bucket_tip_m": vector(
            env[_BUCKET_TIP_SLICE],
            3,
            f"{label}.bucket_tip_m",
        ),
        "terrain_depth_m": vector(
            env[_TERRAIN_DEPTH_SLICE],
            6,
            f"{label}.terrain_depth_m",
        ),
        "remaining_mass_kg": float(env[_REMAINING_MASS_INDEX]),
    }


__all__ = ["WallContactABLineageError", "build_ab_lineage"]
