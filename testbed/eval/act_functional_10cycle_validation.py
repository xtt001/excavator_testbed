"""Offline functional gate for ten complete four-primitive ACT cycles.

This contract is intentionally separate from the formal ACT freeze gate.  It
proves restoration of the historical ten-cycle capability, while recording
mass, payload, effectiveness, and inference latency only as diagnostics.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from testbed.data.schema import (
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX,
    ENV_STATE_DIG_AREA_CELL_AREA_IDX,
    ENV_STATE_DIG_AREA_CURRENT_REMAINING_MASS_IDX,
    ENV_STATE_DIG_AREA_INITIAL_REMAINING_MASS_IDX,
    ENV_STATE_DIG_AREA_REMAINING_MASS_VALID_MASK_IDX,
    ENV_STATE_DIG_AREA_REMAINING_SOIL_VOLUME_START_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_V2_4_DIM,
)
from testbed.eval.coverage_wall_safety_validation import (
    CoverageWallSafetyRolloutContract,
    load_optional_coverage_wall_safety_rollout_contract,
    validate_coverage_wall_safety_rollout,
)

VALIDATION_SCHEMA = "act_functional_10cycle_validation_v1"
MANIFEST_SCHEMA = "act_functional_10cycle_validation_manifest_v1"
AGGREGATE_SCHEMA = "act_functional_10cycle_aggregate_v1"
PRIMITIVES = ("dig", "carry", "dump", "return")

_ROLLOUT_RE = re.compile(r"rollout_(\d{3})\.jsonl\Z")
_REQUIRED_ROW_FIELDS = (
    "step_id",
    "primitive_cycle_index",
    "skill_name",
    "action",
    "box_safety_reason",
    "box_safety_awaiting_neutral_ack",
    "transition_timeout",
    "pre_dig_align_timeout_count",
    "env_state",
)
_CELL_ID_FIELDS = (
    "planned_cut_cell_id",
    "box_residual_active_cell_id",
    "cell_entry_selected_cell_id",
)
class ActFunctional10CycleValidationError(RuntimeError):
    """Raised when an artifact cannot prove the functional regression gate."""


def build_act_functional_10cycle_record(
    *,
    rows: Sequence[Mapping[str, Any]],
    reset_id: str,
    source_artifact_path: str | Path | None = None,
    source_artifact_sha256: str | None = None,
    coverage_wall_safety_contract: (
        CoverageWallSafetyRolloutContract | None
    ) = None,
) -> dict[str, Any]:
    """Validate and summarize one reset entirely from recorded rollout rows."""

    normalized_reset_id = str(reset_id).strip()
    if not normalized_reset_id:
        raise ActFunctional10CycleValidationError("reset_id_missing")
    normalized_rows = _validate_rows(rows)
    cycles = _validate_complete_cycles(normalized_rows)
    terminal_ready_step, terminal_ack_step = _validate_terminal_stop(
        normalized_rows,
        cycles=cycles,
    )
    wall_count, stuck_count, timeout_count = _safety_counts(normalized_rows)
    errors: list[str] = []
    if wall_count != 0:
        errors.append("wall_contact_present")
    if stuck_count != 0:
        errors.append("stuck_present")
    if timeout_count != 0:
        errors.append("timeout_present")
    if errors:
        raise ActFunctional10CycleValidationError(";".join(errors))
    hard_bottom_events = _validate_hard_bottom_events(normalized_rows)
    wall_safety_evidence = (
        None
        if coverage_wall_safety_contract is None
        else validate_coverage_wall_safety_rollout(
            rows=normalized_rows,
            contract=coverage_wall_safety_contract,
        )
    )
    diagnostics = _diagnostics(normalized_rows)
    source_path = (
        str(Path(source_artifact_path).expanduser().resolve())
        if source_artifact_path is not None
        else None
    )
    source_sha = _optional_sha256(source_artifact_sha256)
    return {
        "schema": VALIDATION_SCHEMA,
        "status": "passed",
        "reset_id": normalized_reset_id,
        "completed_cycle_count": 10,
        "cycles": cycles,
        "wall_contact_count": wall_count,
        "stuck_count": stuck_count,
        "timeout_count": timeout_count,
        "hard_bottom_event_count": len(hard_bottom_events),
        "hard_bottom_events": hard_bottom_events,
        "coverage_wall_safety": wall_safety_evidence,
        "terminal_return_ready_step": terminal_ready_step,
        "terminal_neutral_ack_step": terminal_ack_step,
        "source_artifact_path": source_path,
        "source_artifact_sha256": source_sha,
        "diagnostics": diagnostics,
        "gate": {
            "required_complete_cycles": 10,
            "first_nine_require_next_cycle_dig": True,
            "final_cycle_requires_terminal_return_ready": True,
            "final_cycle_requires_terminal_neutral_ack": True,
            "required_zero_counts": ["wall_contact", "stuck", "timeout"],
            "minimum_wall_clearance_m": (
                None
                if coverage_wall_safety_contract is None
                else coverage_wall_safety_contract.hard_clearance_m
            ),
            "diagnostic_only": [
                "remaining_mass",
                "effective_move",
                "payload",
                "inference_p95",
            ],
        },
    }


def evaluate_act_functional_10cycle_records(
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Require three independent passing ten-cycle reset records."""

    if len(records) != 3:
        raise ActFunctional10CycleValidationError(
            "exactly_three_reset_records_required"
        )
    reset_ids: set[str] = set()
    summaries: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, raw in enumerate(records):
        prefix = f"reset[{index}]"
        if not isinstance(raw, Mapping):
            errors.append(f"{prefix}:record_not_mapping")
            continue
        if raw.get("schema") != VALIDATION_SCHEMA:
            errors.append(f"{prefix}:schema_mismatch")
        if raw.get("status") != "passed":
            errors.append(f"{prefix}:record_not_passed")
        reset_id = str(raw.get("reset_id", "")).strip()
        if not reset_id or reset_id in reset_ids:
            errors.append(f"{prefix}:independent_reset_id_invalid")
        reset_ids.add(reset_id)
        if _integer(raw.get("completed_cycle_count"), default=-1) != 10:
            errors.append(f"{prefix}:completed_cycle_count_not_10")
        cycles = raw.get("cycles")
        if not _sequence(cycles) or len(cycles) != 10:
            errors.append(f"{prefix}:cycle_evidence_invalid")
        else:
            cycle_ids = [
                _integer(cycle.get("cycle_index"), default=-1)
                if isinstance(cycle, Mapping)
                else -1
                for cycle in cycles
            ]
            if cycle_ids != list(range(10)):
                errors.append(f"{prefix}:cycle_evidence_invalid")
        terminal_ready_step = _integer(
            raw.get("terminal_return_ready_step"),
            default=-1,
        )
        terminal_ack_step = _integer(
            raw.get("terminal_neutral_ack_step"),
            default=-1,
        )
        if terminal_ready_step < 0:
            errors.append(f"{prefix}:terminal_return_ready_invalid")
        if terminal_ack_step <= terminal_ready_step:
            errors.append(f"{prefix}:terminal_neutral_ack_invalid")
        for field in ("wall_contact_count", "stuck_count", "timeout_count"):
            if _integer(raw.get(field), default=-1) != 0:
                errors.append(f"{prefix}:{field}_not_zero")
        events = raw.get("hard_bottom_events")
        if not _sequence(events):
            errors.append(f"{prefix}:hard_bottom_events_invalid")
        elif _integer(raw.get("hard_bottom_event_count"), default=-1) != len(
            events
        ):
            errors.append(f"{prefix}:hard_bottom_event_count_invalid")
        diagnostics = raw.get("diagnostics")
        if not isinstance(diagnostics, Mapping):
            errors.append(f"{prefix}:diagnostics_missing")
            diagnostics = {}
        summaries.append(
            {
                "reset_id": reset_id,
                "completed_cycle_count": raw.get("completed_cycle_count"),
                "hard_bottom_event_count": raw.get("hard_bottom_event_count"),
                "remaining_mass_drop_fraction": diagnostics.get(
                    "remaining_mass_drop_fraction"
                ),
                "inference_p95_ms": diagnostics.get("inference_p95_ms"),
            }
        )
    if errors:
        raise ActFunctional10CycleValidationError(";".join(errors))
    return {
        "schema": AGGREGATE_SCHEMA,
        "status": "passed",
        "required_reset_count": 3,
        "passed_reset_count": 3,
        "cycles_per_reset": 10,
        "resets": summaries,
    }


def build_act_functional_10cycle_records(
    *,
    results_dir: str | Path,
    output_dir: str | Path,
    expected_rollout_count: int = 3,
    seed_base: int = 1000,
) -> list[dict[str, Any]]:
    """Build no-overwrite records and a manifest from rollout JSONL files."""

    source = Path(results_dir).expanduser()
    destination = Path(output_dir).expanduser()
    if destination.exists():
        raise FileExistsError(
            f"functional validation output already exists: {destination}"
        )
    if expected_rollout_count <= 0:
        raise ValueError("expected_rollout_count must be positive")
    rollout_dir = source / "rollouts"
    indexed: list[tuple[int, Path]] = []
    for path in sorted(rollout_dir.glob("rollout_*.jsonl")):
        match = _ROLLOUT_RE.fullmatch(path.name)
        if match is not None:
            indexed.append((int(match.group(1)), path))
    expected_ids = list(range(expected_rollout_count))
    actual_ids = [index for index, _ in indexed]
    if actual_ids != expected_ids:
        raise ActFunctional10CycleValidationError(
            f"rollout_inventory_mismatch:expected={expected_ids}:actual={actual_ids}"
        )

    records: list[dict[str, Any]] = []
    wall_safety_contract = (
        load_optional_coverage_wall_safety_rollout_contract(
            source / "eval_resolved_config.yaml"
        )
    )
    for rollout_id, path in indexed:
        source_sha = _sha256(path)
        records.append(
            build_act_functional_10cycle_record(
                rows=_read_jsonl(path),
                reset_id=f"seed-{seed_base + rollout_id}",
                source_artifact_path=path,
                source_artifact_sha256=source_sha,
                coverage_wall_safety_contract=wall_safety_contract,
            )
        )
    aggregate = (
        evaluate_act_functional_10cycle_records(records)
        if expected_rollout_count == 3
        else None
    )

    destination.mkdir(parents=True, exist_ok=False)
    record_paths: list[str] = []
    for rollout_id, record in zip(expected_ids, records, strict=True):
        output_path = destination / f"validation_reset_{rollout_id:03d}.json"
        output_path.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        record_paths.append(str(output_path.resolve()))
    manifest = {
        "schema": MANIFEST_SCHEMA,
        "source_results_dir": str(source.resolve()),
        "record_count": len(records),
        "records": record_paths,
        "aggregate": aggregate,
    }
    (destination / "validation_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return records


def _validate_rows(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if not rows:
        raise ActFunctional10CycleValidationError("rollout_rows_missing")
    normalized: list[dict[str, Any]] = []
    previous_step: int | None = None
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            raise ActFunctional10CycleValidationError(
                f"row_{index}:not_mapping"
            )
        missing = [field for field in _REQUIRED_ROW_FIELDS if field not in raw]
        if missing:
            raise ActFunctional10CycleValidationError(
                f"row_{index}:required_row_field_missing:{missing[0]}"
            )
        row = dict(raw)
        if not isinstance(row["skill_name"], str):
            raise ActFunctional10CycleValidationError(
                f"row_{index}:skill_name_invalid"
            )
        if not isinstance(row["box_safety_reason"], str):
            raise ActFunctional10CycleValidationError(
                f"row_{index}:box_safety_reason_invalid"
            )
        for field in (
            "box_safety_awaiting_neutral_ack",
            "transition_timeout",
        ):
            if not isinstance(row[field], bool):
                raise ActFunctional10CycleValidationError(
                    f"row_{index}:{field}_invalid"
                )
        step = _integer(row["step_id"], default=-1)
        if step < 0:
            raise ActFunctional10CycleValidationError(
                f"row_{index}:step_id_invalid"
            )
        if previous_step is not None and step <= previous_step:
            raise ActFunctional10CycleValidationError(
                "step_id_not_strictly_increasing"
            )
        previous_step = step
        action = _vector(row["action"])
        if action.size != 4 or not np.isfinite(action).all():
            raise ActFunctional10CycleValidationError(
                f"row_{index}:action_invalid"
            )
        env = _vector(row["env_state"])
        if env.size != ENV_STATE_V2_4_DIM or not np.isfinite(env).all():
            raise ActFunctional10CycleValidationError(
                f"row_{index}:env_state_invalid"
            )
        if _integer(row["pre_dig_align_timeout_count"], default=-1) < 0:
            raise ActFunctional10CycleValidationError(
                f"row_{index}:pre_dig_align_timeout_count_invalid"
            )
        normalized.append(row)
    return normalized


def _validate_complete_cycles(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    dig_cycle_ids = sorted(
        {
            _integer(row.get("primitive_cycle_index"), default=-1)
            for row in rows
            if str(row.get("skill_name", "")) == "dig"
        }
    )
    if dig_cycle_ids != list(range(10)):
        raise ActFunctional10CycleValidationError(
            f"cycle_inventory_not_0_through_9:actual={dig_cycle_ids}"
        )
    cycle_indices: dict[int, list[int]] = {cycle: [] for cycle in range(10)}
    for index, row in enumerate(rows):
        skill = str(row.get("skill_name", ""))
        cycle = _integer(row.get("primitive_cycle_index"), default=-1)
        if skill in PRIMITIVES and cycle in cycle_indices:
            cycle_indices[cycle].append(index)
        elif skill in PRIMITIVES and cycle >= 0:
            raise ActFunctional10CycleValidationError(
                f"unexpected_cycle_id:{cycle}"
            )

    result: list[dict[str, Any]] = []
    previous_last = -1
    for cycle in range(10):
        indices = cycle_indices[cycle]
        compressed: list[str] = []
        first_by_skill: dict[str, int] = {}
        for index in indices:
            skill = str(rows[index]["skill_name"])
            first_by_skill.setdefault(skill, index)
            if not compressed or compressed[-1] != skill:
                compressed.append(skill)
        if tuple(compressed) != PRIMITIVES:
            raise ActFunctional10CycleValidationError(
                f"cycle_{cycle}:primitive_sequence_invalid:{compressed}"
            )
        if indices[0] <= previous_last:
            raise ActFunctional10CycleValidationError(
                f"cycle_{cycle}:cycle_rows_overlap_or_reorder"
            )
        previous_last = indices[-1]
        if cycle < 9:
            next_dig = next(
                (
                    index
                    for index, row in enumerate(rows)
                    if _integer(
                        row.get("primitive_cycle_index"),
                        default=-1,
                    )
                    == cycle + 1
                    and str(row.get("skill_name", "")) == "dig"
                ),
                -1,
            )
            if next_dig <= first_by_skill["return"]:
                raise ActFunctional10CycleValidationError(
                    f"cycle_{cycle}:next_cycle_dig_missing"
                )
        result.append(
            {
                "cycle_index": cycle,
                "dig_step": _step(rows[first_by_skill["dig"]]),
                "carry_step": _step(rows[first_by_skill["carry"]]),
                "dump_step": _step(rows[first_by_skill["dump"]]),
                "return_step": _step(rows[first_by_skill["return"]]),
            }
        )
    return result


def _validate_terminal_stop(
    rows: Sequence[Mapping[str, Any]],
    *,
    cycles: Sequence[Mapping[str, Any]],
) -> tuple[int, int]:
    return_step = _integer(cycles[-1].get("return_step"), default=-1)
    ready_indices = [
        index
        for index, row in enumerate(rows)
        if row.get("functional_terminal_return_ready") is True
        and _integer(row.get("primitive_cycle_index"), default=-1) == 9
        and str(row.get("skill_name", "")) == "return"
        and _step(row) >= return_step
    ]
    if not ready_indices:
        raise ActFunctional10CycleValidationError(
            "terminal_return_ready_missing"
        )
    ready_index = ready_indices[0]
    ready = rows[ready_index]
    if ready.get("functional_terminal_awaiting_neutral_ack") is not True:
        raise ActFunctional10CycleValidationError(
            "terminal_neutral_pending_missing"
        )
    if not _zero_action(ready):
        raise ActFunctional10CycleValidationError(
            "terminal_ready_action_not_neutral"
        )
    ack_indices = [
        index
        for index, row in enumerate(rows)
        if index > ready_index
        and row.get("functional_terminal_neutral_acknowledged") is True
        and _integer(row.get("primitive_cycle_index"), default=-1) == 9
        and str(row.get("skill_name", "")) == "return"
    ]
    if not ack_indices:
        raise ActFunctional10CycleValidationError(
            "terminal_neutral_ack_missing"
        )
    ack_index = ack_indices[0]
    if not _zero_action(rows[ack_index]):
        raise ActFunctional10CycleValidationError(
            "terminal_ack_action_not_neutral"
        )
    for row in rows[ack_index + 1 :]:
        if not _zero_action(row):
            raise ActFunctional10CycleValidationError(
                "non_neutral_action_after_terminal_ack"
            )
    return _step(ready), _step(rows[ack_index])


def _safety_counts(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[int, int, int]:
    wall_sessions = max(
        int(
            round(
                _vector(row["env_state"])[
                    ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX
                ]
            )
        )
        for row in rows
    )
    wall_steps = {
        _step(row)
        for row in rows
        if str(row["box_safety_reason"]).startswith("wall")
    }
    stuck_steps = {
        _step(row)
        for row in rows
        if "stuck" in str(row["box_safety_reason"])
    }
    timeout_steps = {
        _step(row)
        for row in rows
        if "timeout" in str(row["box_safety_reason"])
    }
    transition_timeouts = 0
    previous = False
    for row in rows:
        current = row["transition_timeout"] is True
        if current and not previous:
            transition_timeouts += 1
        previous = current
    pre_dig_timeouts = max(
        _integer(row["pre_dig_align_timeout_count"], default=0)
        for row in rows
    )
    return (
        max(wall_sessions, len(wall_steps)),
        len(stuck_steps),
        len(timeout_steps) + transition_timeouts + pre_dig_timeouts,
    )


def _validate_hard_bottom_events(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    contact_rows = [
        (index, row)
        for index, row in enumerate(rows)
        if row.get("box_safety_hard_bottom_contact") is True
        or str(row["box_safety_reason"]) == "hard_bottom_contact"
    ]
    contact_ids = {
        str(row.get("box_safety_event_id", "")).strip()
        for _, row in contact_rows
        if str(row.get("box_safety_event_id", "")).strip()
    }
    hard_bottom_rows = [
        (index, row)
        for index, row in enumerate(rows)
        if row.get("box_safety_hard_bottom_contact") is True
        or str(row.get("box_safety_event_id", "")).strip() in contact_ids
    ]
    for index, row in hard_bottom_rows:
        if not str(row.get("box_safety_event_id", "")).strip():
            raise ActFunctional10CycleValidationError(
                f"row_{index}:hard_bottom_event_id_missing"
            )
    grouped: dict[str, list[tuple[int, Mapping[str, Any]]]] = {}
    for index, row in hard_bottom_rows:
        event_id = str(row["box_safety_event_id"]).strip()
        grouped.setdefault(event_id, []).append((index, row))
    ordered_contact_ids = [
        str(row["box_safety_event_id"]).strip() for _, row in contact_rows
    ]
    if len(ordered_contact_ids) != len(set(ordered_contact_ids)):
        raise ActFunctional10CycleValidationError(
            "hard_bottom_event_duplicate_contact"
        )
    orphan_ids = sorted(set(grouped) - set(ordered_contact_ids))
    if orphan_ids:
        raise ActFunctional10CycleValidationError(
            f"hard_bottom_event_contact_missing:{orphan_ids}"
        )

    events: list[dict[str, Any]] = []
    exhausted_cell_ids: set[int] = set()
    for contact_index, contact in contact_rows:
        event_id = str(contact["box_safety_event_id"]).strip()
        cell_id = _event_cell_id(contact)
        if cell_id in exhausted_cell_ids:
            raise ActFunctional10CycleValidationError(
                f"{event_id}:exhausted_cell_recontacted:{cell_id}"
            )
        exhausted_cell_ids.add(cell_id)
        event_rows = grouped[event_id]
        if contact.get("box_safety_awaiting_neutral_ack") is not True:
            raise ActFunctional10CycleValidationError(
                f"{event_id}:contact_neutral_pending_missing"
            )
        if not _zero_action(contact):
            raise ActFunctional10CycleValidationError(
                f"{event_id}:contact_action_not_neutral"
            )
        stages: dict[str, int] = {
            "neutral_ack": _first_stage(
                event_rows,
                "box_safety_neutral_acknowledged",
                event_id,
                "neutral_ack_missing",
            ),
            "policy_restart": _first_stage(
                event_rows,
                "box_safety_policy_restarted",
                event_id,
                "policy_restart_missing",
            ),
            "clearance_active": _first_stage(
                event_rows,
                "box_safety_clearance_active",
                event_id,
                "clearance_missing",
            ),
            "clearance_completed": _first_stage(
                event_rows,
                "box_safety_clearance_completed",
                event_id,
                "clearance_completion_missing",
            ),
            "clearance_neutral_ack": _first_stage(
                event_rows,
                "box_safety_clearance_neutral_acknowledged",
                event_id,
                "clearance_neutral_ack_missing",
            ),
        }
        stages["replan"] = _first_stage(
            event_rows,
            "box_safety_replan",
            event_id,
            "replan_missing",
            at_or_after=stages["clearance_neutral_ack"],
        )
        ordered = [
            contact_index,
            stages["neutral_ack"],
            stages["policy_restart"],
            stages["clearance_active"],
            stages["clearance_completed"],
            stages["clearance_neutral_ack"],
            stages["replan"],
        ]
        if not (
            ordered[0] < ordered[1]
            <= ordered[2]
            <= ordered[3]
            <= ordered[4]
            < ordered[5]
            <= ordered[6]
        ):
            raise ActFunctional10CycleValidationError(
                f"{event_id}:recovery_stage_order_invalid:{ordered}"
            )
        if not _zero_action(rows[stages["clearance_completed"]]):
            raise ActFunctional10CycleValidationError(
                f"{event_id}:clearance_completion_action_not_neutral"
            )
        if not _zero_action(rows[stages["clearance_neutral_ack"]]):
            raise ActFunctional10CycleValidationError(
                f"{event_id}:clearance_ack_action_not_neutral"
            )
        contact_depth = float(
            _vector(contact["env_state"])[
                ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX
            ]
        )
        event_depths = [
            float(
                _vector(row["env_state"])[
                    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX
                ]
            )
            for index, row in event_rows
            if contact_index <= index <= stages["clearance_neutral_ack"]
        ]
        if (
            event_depths
            and max(event_depths) - contact_depth > 0.002 + 1.0e-9
        ):
            raise ActFunctional10CycleValidationError(
                f"{event_id}:continued_downward_penetration"
            )
        for later in rows[stages["replan"] + 1 :]:
            if str(later.get("skill_name", "")) != "dig":
                continue
            if str(later.get("box_safety_event_id", "")).strip() == event_id:
                continue
            later_cell_id = _dig_cell_id(later, event_id=event_id)
            if later_cell_id == cell_id:
                raise ActFunctional10CycleValidationError(
                    f"{event_id}:exhausted_cell_redug:{cell_id}"
                )
        events.append(
            {
                "event_id": event_id,
                "cycle_index": _integer(
                    contact.get("primitive_cycle_index"),
                    default=-1,
                ),
                "cell_id": cell_id,
                "contact_step": _step(contact),
                "neutral_ack_step": _step(rows[stages["neutral_ack"]]),
                "policy_restart_step": _step(rows[stages["policy_restart"]]),
                "clearance_start_step": _step(rows[stages["clearance_active"]]),
                "clearance_complete_step": _step(
                    rows[stages["clearance_completed"]]
                ),
                "clearance_neutral_ack_step": _step(
                    rows[stages["clearance_neutral_ack"]]
                ),
                "replan_step": _step(rows[stages["replan"]]),
            }
        )
    return events


def validate_hard_bottom_recovery_events(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Validate hard-bottom ordering without requiring a ten-cycle rollout."""

    return _validate_hard_bottom_events(_validate_rows(rows))


def _diagnostics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    valid_envs = [
        _vector(row["env_state"])
        for row in rows
        if _vector(row["env_state"])[
            ENV_STATE_DIG_AREA_REMAINING_MASS_VALID_MASK_IDX
        ]
        >= 0.5
    ]
    initial_mass: float | None = None
    final_mass: float | None = None
    drop_fraction: float | None = None
    if valid_envs:
        candidate_initial = float(
            valid_envs[0][ENV_STATE_DIG_AREA_INITIAL_REMAINING_MASS_IDX]
        )
        candidate_final = float(
            valid_envs[-1][ENV_STATE_DIG_AREA_CURRENT_REMAINING_MASS_IDX]
        )
        if math.isfinite(candidate_initial) and candidate_initial > 0.0:
            initial_mass = candidate_initial
            if math.isfinite(candidate_final) and candidate_final >= 0.0:
                final_mass = candidate_final
                drop_fraction = 1.0 - final_mass / initial_mass
    payloads = [
        float(_vector(row["env_state"])[ENV_STATE_MASS_IN_BUCKET_IDX])
        for row in rows
    ]
    latencies = [
        _finite_float(row.get("policy_inference_latency_ms"))
        for row in rows
    ]
    finite_latencies = [
        value for value in latencies if value is not None and value >= 0.0
    ]
    cycle_outcomes = _cycle_outcome_diagnostics(rows)
    effective_cycles = [
        outcome
        for outcome in cycle_outcomes
        if outcome.get("effective_move") is True
    ]
    bottom_sessions = max(
        int(
            round(
                _vector(row["env_state"])[
                    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX
                ]
            )
        )
        for row in rows
    )
    return {
        "initial_remaining_mass_kg": initial_mass,
        "final_remaining_mass_kg": final_mass,
        "remaining_mass_drop_fraction": drop_fraction,
        "max_payload_kg": max(payloads) if payloads else None,
        "effective_move_cycle_count": len(effective_cycles),
        "effective_move_observed_cycle_count": sum(
            outcome.get("effective_move") is not None
            for outcome in cycle_outcomes
        ),
        "cycle_outcomes": cycle_outcomes,
        "inference_p95_ms": (
            float(np.percentile(finite_latencies, 95))
            if finite_latencies
            else None
        ),
        "bottom_contact_session_count": bottom_sessions,
        "blocking_gate_fields": [],
    }


def _cycle_outcome_diagnostics(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for cycle_index in range(10):
        cycle_rows = [
            row
            for row in rows
            if _integer(
                row.get("primitive_cycle_index"),
                default=-1,
            )
            == cycle_index
        ]
        explicit = [
            bool(row["cycle_effective_move"])
            for row in cycle_rows
            if isinstance(row.get("cycle_effective_move"), bool)
        ]
        envs = [_vector(row["env_state"]) for row in cycle_rows]
        payload = (
            max(float(env[ENV_STATE_MASS_IN_BUCKET_IDX]) for env in envs)
            if envs
            else None
        )
        if explicit:
            result.append(
                {
                    "cycle_index": cycle_index,
                    "effective_move": any(explicit),
                    "peak_payload_kg": payload,
                    "stable_net_removed_volume_m3": None,
                    "source": "runtime_cycle_effective_move",
                }
            )
            continue
        stable = _stable_cycle_volume_snapshots(envs)
        if stable is None:
            result.append(
                {
                    "cycle_index": cycle_index,
                    "effective_move": None,
                    "peak_payload_kg": payload,
                    "stable_net_removed_volume_m3": None,
                    "source": "stable_107d_window_unavailable",
                }
            )
            continue
        first_volume, last_volume = stable
        net_removed = max(
            0.0,
            float(np.sum(first_volume - last_volume)),
        )
        peak_payload = 0.0 if payload is None else float(payload)
        result.append(
            {
                "cycle_index": cycle_index,
                "effective_move": not (
                    peak_payload < 15.0 and net_removed < 0.005
                ),
                "peak_payload_kg": peak_payload,
                "stable_net_removed_volume_m3": net_removed,
                "source": "stable_107d_window",
            }
        )
    return result


def _stable_cycle_volume_snapshots(
    envs: Sequence[np.ndarray],
    *,
    window_steps: int = 10,
    max_depth_range_m: float = 0.002,
) -> tuple[np.ndarray, np.ndarray] | None:
    width = 6
    volume_start = ENV_STATE_DIG_AREA_REMAINING_SOIL_VOLUME_START_IDX
    snapshots: list[np.ndarray] = []
    for start in range(0, len(envs) - window_steps + 1):
        window = envs[start : start + window_steps]
        if any(env.size != ENV_STATE_V2_4_DIM for env in window):
            continue
        if any(
            env[ENV_STATE_DIG_AREA_REMAINING_MASS_VALID_MASK_IDX] < 0.5
            for env in window
        ):
            continue
        areas = np.asarray(
            [env[ENV_STATE_DIG_AREA_CELL_AREA_IDX] for env in window],
            dtype=np.float64,
        )
        volumes = np.asarray(
            [env[volume_start : volume_start + width] for env in window],
            dtype=np.float64,
        )
        if (
            not np.isfinite(areas).all()
            or not np.isfinite(volumes).all()
            or np.any(areas <= 0.0)
            or np.ptp(areas) > 1.0e-6
        ):
            continue
        depths = volumes / areas[:, None]
        if np.any(np.ptp(depths, axis=0) > max_depth_range_m):
            continue
        snapshots.append(np.median(volumes, axis=0))
    if not snapshots:
        return None
    return snapshots[0], snapshots[-1]


def _first_stage(
    event_rows: Sequence[tuple[int, Mapping[str, Any]]],
    field: str,
    event_id: str,
    reason: str,
    *,
    at_or_after: int = -1,
) -> int:
    for index, row in event_rows:
        if index >= at_or_after and row.get(field) is True:
            return index
    raise ActFunctional10CycleValidationError(f"{event_id}:{reason}")


def _event_cell_id(row: Mapping[str, Any]) -> int:
    value = _integer(
        row.get("box_safety_depth_exhausted_cell_id"),
        default=-1,
    )
    if value < 0:
        event_id = str(row.get("box_safety_event_id", "")).strip()
        raise ActFunctional10CycleValidationError(
            f"{event_id}:depth_exhausted_cell_id_missing"
        )
    return value


def _dig_cell_id(row: Mapping[str, Any], *, event_id: str) -> int:
    for field in _CELL_ID_FIELDS:
        if field in row:
            value = _integer(row[field], default=-1)
            if value >= 0:
                return value
    raise ActFunctional10CycleValidationError(
        f"{event_id}:later_dig_cell_id_missing"
    )


def _zero_action(row: Mapping[str, Any]) -> bool:
    action = _vector(row.get("action"))
    return bool(
        action.size == 4
        and np.isfinite(action).all()
        and np.all(np.abs(action) <= 1.0e-9)
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise ActFunctional10CycleValidationError(
            f"rollout_jsonl_invalid:{path}"
        ) from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _optional_sha256(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", normalized):
        raise ActFunctional10CycleValidationError(
            "source_artifact_sha256_invalid"
        )
    return normalized


def _step(row: Mapping[str, Any]) -> int:
    return _integer(row.get("step_id"), default=-1)


def _integer(value: Any, *, default: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed


def _finite_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _vector(value: Any) -> np.ndarray:
    try:
        return np.asarray(value, dtype=np.float64).reshape(-1)
    except (TypeError, ValueError):
        return np.asarray([], dtype=np.float64)


def _sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


__all__ = [
    "AGGREGATE_SCHEMA",
    "ActFunctional10CycleValidationError",
    "MANIFEST_SCHEMA",
    "VALIDATION_SCHEMA",
    "build_act_functional_10cycle_record",
    "build_act_functional_10cycle_records",
    "evaluate_act_functional_10cycle_records",
    "validate_hard_bottom_recovery_events",
]
