"""Rollout extraction contracts for the Strict-18 paired contact A/B."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from testbed.data.schema import (
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX,
    ENV_STATE_DIG_AREA_CURRENT_REMAINING_MASS_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_STEP_MAX_FORCE_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_TYPED_MASK_IDX,
    ENV_STATE_V2_4_DIM,
)
from testbed.eval.wall_contact_artifact_io import (
    artifact_ref,
    load_json,
    required_file,
    write_json_x,
)
from testbed.eval.wall_contact_evidence_contracts import (
    CONTACT_DETAIL_WARNING_PREFIX,
    ContactEvidenceContractError,
    parse_worktool_wall_contact_detail,
    terminal_matches_box_safety_reason,
)
from testbed.planner.box_emptying.wall_contact_detail import (
    WALL_CONTACT_HARD_MAX_FORCE_N,
    WALL_CONTACT_SESSION_END_CLEAR_TICKS_DEFAULT,
    validate_wall_contact_session_end_clear_ticks,
)

ATTEMPT_SCHEMA = "wall_contact_paired_ab_attempt_v1"
ATTEMPT_SET_SCHEMA = "wall_contact_paired_ab_attempt_set_v1"
START_MARKER_SCHEMA = "wall_contact_paired_ab_attempt_started_v1"
TARGET_EXEMPLAR_ID = "episode_168"
TARGET_RAW_FIELDS_SHA256 = (
    "c167e087f3d41f6db8fe0ad260d5f72c3440b6fab9115fdf55959feacc50991c"
)
_CONTACT_HARD_REASONS = frozenset(
    {
        "wall_contact_detail_invalid",
        "wall_contact_forbidden_component",
        "wall_contact_high_force",
        "wall_contact_repeat_session",
        "wall_contact_identity_drift",
    }
)


class WallContactABCollectionError(RuntimeError):
    """Raised when a completed attempt cannot be trusted."""


def extract_paired_ab_attempt(
    *,
    expected: Mapping[str, Any],
    rollout_jsonl_path: str | Path,
    rollout_summary_path: str | Path,
    process_returncode: int,
) -> dict[str, Any]:
    """Extract one diagnostic attempt from the canonical rollout JSONL."""

    rollout_path = required_file(rollout_jsonl_path, "paired_ab_rollout_jsonl")
    summary_path = required_file(
        rollout_summary_path,
        "paired_ab_rollout_summary",
    )
    rows = _load_jsonl(rollout_path)
    summary = load_json(summary_path)
    blockers: list[str] = []
    if int(process_returncode) != 0:
        blockers.append("eval_process_nonzero")

    expected_mode = str(expected.get("wall_first_touch_mode", ""))
    condition = str(expected.get("condition", ""))
    expected_clear_ticks = _expected_session_end_clear_ticks(expected)
    debug_valid, debug_fields, invalid_debug_step = _debug_lineage(
        rows,
        expected_mode=expected_mode,
        expected_session_end_clear_ticks=(
            expected_clear_ticks
            if "wall_contact_session_end_clear_ticks" in expected
            else None
        ),
    )
    if not debug_valid:
        blockers.append("diagnostic_debug_lineage_drift")

    target_rows = [
        row
        for row in rows
        if str(row.get("coverage_execution_exemplar_id", ""))
        == TARGET_EXEMPLAR_ID
    ]
    selected_exemplar = TARGET_EXEMPLAR_ID if target_rows else ""
    selected_raw_sha = (
        str(target_rows[0].get("coverage_execution_raw_fields_sha256", ""))
        if target_rows
        else ""
    )
    target_cycle = _target_execution_cycle(target_rows)
    if not target_rows:
        blockers.append("target_episode_168_not_selected")
    elif (
        target_cycle < 0
        or any(
            row.get("coverage_execution_raw_fields_sha256")
            != TARGET_RAW_FIELDS_SHA256
            for row in target_rows
        )
    ):
        blockers.append("target_episode_168_lineage_drift")

    reset_state = _reset_state(rows[0], blockers)
    target_execution_rows = [
        row for row in rows if _cycle(row) == target_cycle
    ]
    details, warnings_by_step, contact_indices, contact_blockers = (
        _contact_details(target_execution_rows)
    )
    blockers.extend(contact_blockers)

    carry_indices = [
        index
        for index, row in enumerate(target_execution_rows)
        if _skill(row) == "carry"
    ]
    dump_indices = [
        index
        for index, row in enumerate(target_execution_rows)
        if int(row.get("dump_end_mask", 0)) == 1
    ]
    entered_carry = bool(carry_indices)
    target_dump_completed = bool(dump_indices)
    contact_ended_before_carry = bool(
        contact_indices
        and carry_indices
        and max(contact_indices) < min(carry_indices)
    )

    diagnostic_allowed = any(
        bool(row.get("box_safety_wall_contact_diagnostic_allowed", False))
        for row in target_execution_rows
    )
    hard_violations = _hard_stop_violations(
        rows=target_execution_rows,
        details=details,
        contact_indices=contact_indices,
        session_end_clear_ticks=expected_clear_ticks,
    )
    safety_reasons = [
        str(row.get("box_safety_reason", ""))
        for row in target_execution_rows
        if str(row.get("box_safety_reason", ""))
    ]
    terminal_reason = str(summary.get("rollout_stop_reason", "")) or (
        safety_reasons[-1] if safety_reasons else ""
    )
    if target_dump_completed and not terminal_reason:
        terminal_reason = "target_dump_complete"
    if int(process_returncode) != 0 and not terminal_reason:
        terminal_reason = "eval_process_nonzero"

    neutral = _neutral_evidence(target_execution_rows, contact_indices)
    hard_violation = bool(hard_violations)
    contact_driven_reasons = {
        *_CONTACT_HARD_REASONS,
        "persistent_contact",
        "stuck",
    }
    if condition == "A" and contact_indices:
        if not terminal_matches_box_safety_reason(
            terminal_reason,
            "wall_contact_first_session",
        ):
            blockers.append("condition_a_first_touch_not_stopped")
        if (
            not neutral["zero_action_after_first_contact"]
            or not neutral["neutral_acknowledged"]
        ):
            blockers.append("condition_a_terminal_neutral_contract_invalid")
    if (
        condition == "B"
        and contact_indices
        and not hard_violation
        and not diagnostic_allowed
    ):
        blockers.append("condition_b_diagnostic_allow_lineage_missing")
    if (
        hard_violation
        and (
            not neutral["zero_action_after_first_contact"]
            or not neutral["neutral_acknowledged"]
        )
    ):
        blockers.append("hard_stop_terminal_neutral_contract_invalid")

    blockers = sorted(set(blockers))
    return {
        "schema": ATTEMPT_SCHEMA,
        "status": "passed" if not blockers else "failed",
        "blockers": blockers,
        "attempt_id": str(expected.get("attempt_id", "")),
        "pair_id": str(expected.get("pair_id", "")),
        "sequence_index": int(expected.get("sequence_index", -1)),
        "seed": int(expected.get("seed", -1)),
        "condition": condition,
        "retry_count": 0,
        "process_returncode": int(process_returncode),
        "reset_checkpoint_semantics": "first_post_reset_control_step",
        "reset_state": reset_state,
        "selected_exemplar_id": selected_exemplar,
        "selected_raw_fields_sha256": selected_raw_sha,
        "target_cycle_index": target_cycle,
        "entered_carry": entered_carry,
        "dump_completed": target_dump_completed,
        "target_dump_completed": target_dump_completed,
        "contact_ended_before_carry": contact_ended_before_carry,
        "terminal_reason": terminal_reason,
        "hard_stop_violations": hard_violations,
        "hard_violation": hard_violation,
        "contact_driven_hard_failure": bool(
            not target_dump_completed
            and contact_driven_reasons.intersection(hard_violations)
        ),
        "zero_action_after_first_contact": neutral[
            "zero_action_after_first_contact"
        ],
        "neutral_acknowledged": neutral["neutral_acknowledged"],
        "neutral_zero_action_evidence": neutral,
        "diagnostic_allowed_observed": diagnostic_allowed,
        "debug_lineage_valid_every_tick": debug_valid,
        "debug_lineage_first_invalid_step_id": invalid_debug_step,
        "debug_fields": debug_fields,
        "warnings_by_step": warnings_by_step,
        "diagnostic_only": True,
        "non_promotable": True,
        "writes_training_hdf5": False,
        "source_lock": {
            "rollout_jsonl": artifact_ref(rollout_path),
            "rollout_summary": artifact_ref(summary_path),
        },
    }


def write_paired_ab_attempt_set(
    *,
    schedule: Mapping[str, Any],
    output_path: str | Path,
) -> dict[str, Any]:
    """Collect six immutable per-attempt records into one attempt set."""

    destination = Path(output_path).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite {destination}")
    attempts: list[dict[str, Any]] = []
    result_refs: list[dict[str, Any]] = []
    frozen_handoff_shas: set[str] = set()
    for expected in schedule["attempts"]:
        run_root = Path(str(expected["run_root"]))
        marker_path = required_file(
            run_root / "attempt_started.json",
            f"{expected['attempt_id']}.attempt_started",
        )
        result_path = required_file(
            run_root / "attempt_result.json",
            f"{expected['attempt_id']}.attempt_result",
        )
        marker = load_json(marker_path)
        result = load_json(result_path)
        if (
            marker.get("schema") != START_MARKER_SCHEMA
            or marker.get("attempt_id") != expected["attempt_id"]
            or result.get("schema") != ATTEMPT_SCHEMA
            or result.get("attempt_id") != expected["attempt_id"]
            or int(result.get("retry_count", -1)) != 0
        ):
            raise WallContactABCollectionError(
                f"paired_ab_result_lineage_invalid:{expected['attempt_id']}"
            )
        frozen_handoff_shas.add(
            _frozen_handoff_sha(Path(str(expected["config_path"])))
        )
        attempts.append(result)
        result_refs.append(artifact_ref(result_path))
    if len(frozen_handoff_shas) != 1:
        raise WallContactABCollectionError("frozen_handoff_sha_drift")
    failed = [
        str(item["attempt_id"])
        for item in attempts
        if item.get("status") != "passed"
    ]
    artifact = {
        "schema": ATTEMPT_SET_SCHEMA,
        "status": "passed" if not failed else "failed",
        "blockers": (
            [] if not failed else ["paired_ab_attempt_execution_failed"]
        ),
        "failed_attempt_ids": failed,
        "attempt_count": len(attempts),
        "retry_allowed": False,
        "execution_order": [str(item["attempt_id"]) for item in attempts],
        "frozen_handoff_sha256": next(iter(frozen_handoff_shas)),
        "expert_same_region_sub_100kn": False,
        "expert_lineage_complete": False,
        "expert_cross_evidence_status": "not_owned_by_ab_runner",
        "attempts": attempts,
        "diagnostic_only": True,
        "non_promotable": True,
        "production_promotion_allowed": False,
        "writes_training_hdf5": False,
        "source_lock": {
            "schedule": artifact_ref(Path(str(schedule["schedule_path"]))),
            "attempt_results": result_refs,
        },
    }
    write_json_x(destination, artifact)
    return artifact


def failed_paired_ab_attempt(
    *,
    expected: Mapping[str, Any],
    returncode: int,
    blocker: str,
) -> dict[str, Any]:
    """Return a serializable fail-closed record when no rollout is complete."""

    return {
        "schema": ATTEMPT_SCHEMA,
        "status": "failed",
        "blockers": sorted(
            {
                blocker,
                *(("eval_process_nonzero",) if returncode != 0 else ()),
            }
        ),
        "attempt_id": str(expected.get("attempt_id", "")),
        "pair_id": str(expected.get("pair_id", "")),
        "sequence_index": int(expected.get("sequence_index", -1)),
        "seed": int(expected.get("seed", -1)),
        "condition": str(expected.get("condition", "")),
        "retry_count": 0,
        "process_returncode": int(returncode),
        "reset_checkpoint_semantics": "first_post_reset_control_step",
        "reset_state": {
            "qpos": [],
            "qvel": [],
            "bucket_tip_m": [],
            "terrain_depth_m": [],
            "remaining_mass_kg": 0.0,
        },
        "selected_exemplar_id": "",
        "selected_raw_fields_sha256": "",
        "target_cycle_index": -1,
        "entered_carry": False,
        "dump_completed": False,
        "target_dump_completed": False,
        "contact_ended_before_carry": False,
        "terminal_reason": (
            "eval_process_nonzero"
            if returncode != 0
            else "rollout_artifacts_missing"
        ),
        "hard_stop_violations": [],
        "hard_violation": False,
        "contact_driven_hard_failure": False,
        "zero_action_after_first_contact": False,
        "neutral_acknowledged": False,
        "neutral_zero_action_evidence": {},
        "diagnostic_allowed_observed": False,
        "debug_lineage_valid_every_tick": False,
        "debug_lineage_first_invalid_step_id": -1,
        "debug_fields": {
            "box_safety_wall_contact_diagnostic_ab_enabled": False,
            "box_safety_wall_first_touch_mode": "",
        },
        "warnings_by_step": [],
        "diagnostic_only": True,
        "non_promotable": True,
        "writes_training_hdf5": False,
        "source_lock": {},
    }


def _expected_session_end_clear_ticks(
    expected: Mapping[str, Any],
) -> int:
    value = expected.get(
        "wall_contact_session_end_clear_ticks",
        WALL_CONTACT_SESSION_END_CLEAR_TICKS_DEFAULT,
    )
    try:
        return validate_wall_contact_session_end_clear_ticks(value)
    except ValueError as exc:
        raise WallContactABCollectionError(
            "wall_contact_session_end_clear_ticks_invalid"
        ) from exc


def _debug_lineage(
    rows: Sequence[Mapping[str, Any]],
    *,
    expected_mode: str,
    expected_session_end_clear_ticks: int | None = None,
) -> tuple[bool, dict[str, Any], int]:
    fields = {
        "box_safety_wall_contact_diagnostic_ab_enabled": True,
        "box_safety_wall_first_touch_mode": expected_mode,
    }
    if expected_session_end_clear_ticks is not None:
        fields["box_safety_wall_contact_session_end_clear_ticks"] = (
            expected_session_end_clear_ticks
        )
    for row in rows:
        observed = {
            "box_safety_wall_contact_diagnostic_ab_enabled": row.get(
                "box_safety_wall_contact_diagnostic_ab_enabled"
            ),
            "box_safety_wall_first_touch_mode": row.get(
                "box_safety_wall_first_touch_mode"
            ),
        }
        if expected_session_end_clear_ticks is not None:
            observed["box_safety_wall_contact_session_end_clear_ticks"] = (
                row.get(
                    "box_safety_wall_contact_session_end_clear_ticks"
                )
            )
        if observed != fields:
            return False, observed, int(row.get("step_id", -1))
    return True, fields, -1


def _target_execution_cycle(
    target_rows: Sequence[Mapping[str, Any]],
) -> int:
    dig_cycles = {
        _cycle(row)
        for row in target_rows
        if _skill(row) == "dig" and _cycle(row) >= 0
    }
    if len(dig_cycles) != 1:
        return -1
    target_cycle = next(iter(dig_cycles))
    for row in target_rows:
        cycle = _cycle(row)
        if cycle == target_cycle:
            continue
        if cycle != target_cycle - 1 or _skill(row) != "return":
            return -1
    return target_cycle


def _reset_state(
    row: Mapping[str, Any],
    blockers: list[str],
) -> dict[str, Any]:
    try:
        qpos = _finite_vector(row.get("qpos"), 4, "reset.qpos")
        qvel = _finite_vector(row.get("qvel"), 4, "reset.qvel")
        env = _finite_vector(
            row.get("env_state"),
            ENV_STATE_V2_4_DIM,
            "reset.env_state",
        )
        start = ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX
        return {
            "qpos": qpos,
            "qvel": qvel,
            "bucket_tip_m": env[28:31],
            "terrain_depth_m": env[start : start + 6],
            "remaining_mass_kg": env[
                ENV_STATE_DIG_AREA_CURRENT_REMAINING_MASS_IDX
            ],
        }
    except WallContactABCollectionError:
        blockers.append("reset_state_contract_invalid")
        return {
            "qpos": [],
            "qvel": [],
            "bucket_tip_m": [],
            "terrain_depth_m": [],
            "remaining_mass_kg": 0.0,
        }


def _contact_details(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[int],
    list[str],
]:
    details: list[dict[str, Any]] = []
    warnings_by_step: list[dict[str, Any]] = []
    contact_indices: list[int] = []
    blockers: list[str] = []
    for index, row in enumerate(rows):
        warnings = row.get("warnings", [])
        if (
            isinstance(warnings, (str, bytes))
            or not isinstance(warnings, Sequence)
        ):
            blockers.append("contact_warnings_invalid")
            continue
        warnings_list = list(warnings)
        has_sidecar = any(
            (
                isinstance(item, str)
                and item.startswith(CONTACT_DETAIL_WARNING_PREFIX)
            )
            or (
                isinstance(item, Mapping)
                and item.get("schema")
                == CONTACT_DETAIL_WARNING_PREFIX.removesuffix(":")
            )
            for item in warnings_list
        )
        try:
            env = _finite_vector(
                row.get("env_state"),
                ENV_STATE_V2_4_DIM,
                "step.env_state",
            )
        except WallContactABCollectionError:
            blockers.append("env_state_107d_contract_invalid")
            continue
        wall_positive = (
            env[ENV_STATE_EXCAVATOR_WALL_CONTACT_TYPED_MASK_IDX] >= 0.5
        )
        if wall_positive or has_sidecar:
            contact_indices.append(index)
            warnings_by_step.append(
                {
                    "step_id": int(row.get("step_id", -1)),
                    "warnings": warnings_list,
                }
            )
        if wall_positive != has_sidecar:
            blockers.append("typed_contact_sidecar_lineage_missing")
            continue
        if not wall_positive:
            continue
        try:
            detail = parse_worktool_wall_contact_detail(warnings_list)
            _validate_contact_lineage(row=row, env=env, detail=detail)
            details.append(detail)
        except (
            ContactEvidenceContractError,
            WallContactABCollectionError,
        ):
            blockers.append("wall_contact_detail_invalid")
    return details, warnings_by_step, sorted(set(contact_indices)), blockers


def _validate_contact_lineage(
    *,
    row: Mapping[str, Any],
    env: Sequence[float],
    detail: Mapping[str, Any],
) -> None:
    if int(detail.get("step_id", -1)) != int(row.get("step_id", -2)):
        raise WallContactABCollectionError("contact_step_lineage_drift")
    sim_time_ns = int(row.get("sim_time_ns", -1))
    expected_time_s = sim_time_ns / 1_000_000_000.0
    dt = float(detail.get("delta_time_s", 0.0))
    if sim_time_ns < 0 or not math.isclose(
        float(detail.get("sim_time_s", math.nan)),
        expected_time_s,
        abs_tol=max(1.0e-6, abs(dt) * 1.0e-5),
        rel_tol=0.0,
    ):
        raise WallContactABCollectionError("contact_sim_time_lineage_drift")
    if int(detail.get("session_count", -1)) != int(
        round(env[ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX])
    ):
        raise WallContactABCollectionError("contact_session_lineage_drift")
    sidecar_force = max(
        float(pair["max_normal_force_n"])
        for pair in detail.get("pairs", ())
    )
    aggregate_force = env[
        ENV_STATE_EXCAVATOR_WALL_CONTACT_STEP_MAX_FORCE_IDX
    ]
    if not math.isclose(
        sidecar_force,
        aggregate_force,
        abs_tol=max(1.0e-3, abs(sidecar_force) * 1.0e-5),
        rel_tol=0.0,
    ):
        raise WallContactABCollectionError("contact_force_lineage_drift")


def _hard_stop_violations(
    *,
    rows: Sequence[Mapping[str, Any]],
    details: Sequence[Mapping[str, Any]],
    contact_indices: Sequence[int],
    session_end_clear_ticks: int,
) -> list[str]:
    result: set[str] = set()
    components = {
        str(pair["component"])
        for detail in details
        for pair in detail.get("pairs", ())
    }
    walls = {
        str(pair["wall_name"])
        for detail in details
        for pair in detail.get("pairs", ())
    }
    if any(component != "bucket" for component in components):
        result.add("wall_contact_forbidden_component")
    forces = [
        float(force)
        for detail in details
        for pair in detail.get("pairs", ())
        for force in (
            pair["max_normal_force_n"],
            pair["max_tangential_force_n"],
            pair["max_total_force_n"],
        )
    ]
    if any(
        not math.isfinite(force) or force >= WALL_CONTACT_HARD_MAX_FORCE_N
        for force in forces
    ):
        result.add("wall_contact_high_force")
    result.update(
        _session_lineage_hard_violations(
            rows=rows,
            details=details,
            contact_indices=contact_indices,
            session_end_clear_ticks=session_end_clear_ticks,
        )
    )
    if len(components) > 1 or len(walls) > 1:
        result.add("wall_contact_identity_drift")
    for row in rows:
        reason = str(row.get("box_safety_reason", ""))
        if reason in _CONTACT_HARD_REASONS:
            result.add(reason)
        if (
            bool(row.get("box_safety_hard_bottom_contact", False))
            or _env_flag(
                row,
                ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX,
            )
        ):
            result.add("hard_bottom_contact")
        if bool(row.get("transition_timeout", False)) or "timeout" in reason:
            result.add("timeout")
        if "stuck" in reason:
            result.add("stuck")
    if (
        contact_indices
        and max(contact_indices) == len(rows) - 1
        and not any(_skill(row) == "carry" for row in rows)
    ):
        result.add("persistent_contact")
    return sorted(result)


def _session_lineage_hard_violations(
    *,
    rows: Sequence[Mapping[str, Any]],
    details: Sequence[Mapping[str, Any]],
    contact_indices: Sequence[int],
    session_end_clear_ticks: int,
) -> set[str]:
    """Reconcile Unity physical sessions with the configured logical gap."""

    if session_end_clear_ticks == WALL_CONTACT_SESSION_END_CLEAR_TICKS_DEFAULT:
        session_ids = {
            int(detail.get("session_id", -1)) for detail in details
        }
        repeat_observed = len(session_ids) > 1 or any(
            int(detail.get("session_count", 0)) >= 2
            for detail in details
        )
        return (
            {"wall_contact_repeat_session"} if repeat_observed else set()
        )

    detail_by_step = {
        int(detail.get("step_id", -1)): detail for detail in details
    }
    events = [
        (index, detail_by_step[int(rows[index].get("step_id", -1))])
        for index in contact_indices
        if (
            0 <= index < len(rows)
            and int(rows[index].get("step_id", -1)) in detail_by_step
        )
    ]
    if not events:
        return set()

    _, first_detail = events[0]
    if int(first_detail.get("session_count", 0)) >= 2:
        return {"wall_contact_repeat_session"}

    previous_index, previous_detail = events[0]
    previous_session_id = int(previous_detail.get("session_id", -1))
    previous_session_count = int(previous_detail.get("session_count", -1))
    previous_consecutive_steps = int(
        previous_detail.get("consecutive_contact_steps", -1)
    )
    for index, detail in events[1:]:
        session_id = int(detail.get("session_id", -1))
        session_count = int(detail.get("session_count", -1))
        consecutive_steps = int(
            detail.get("consecutive_contact_steps", -1)
        )
        clear_ticks = index - previous_index - 1
        if clear_ticks >= session_end_clear_ticks:
            return {"wall_contact_repeat_session"}
        if clear_ticks == 0:
            if (
                session_id != previous_session_id
                or session_count != previous_session_count
            ):
                return {"wall_contact_repeat_session"}
            if consecutive_steps <= previous_consecutive_steps:
                return {"wall_contact_identity_drift"}
        elif clear_ticks == 1:
            if (
                session_id != previous_session_id + 1
                or session_count != previous_session_count + 1
            ):
                return {"wall_contact_repeat_session"}
            if consecutive_steps != 1:
                return {"wall_contact_identity_drift"}
        previous_index = index
        previous_session_id = session_id
        previous_session_count = session_count
        previous_consecutive_steps = consecutive_steps
    return set()


def _neutral_evidence(
    rows: Sequence[Mapping[str, Any]],
    contact_indices: Sequence[int],
) -> dict[str, Any]:
    first_contact_index = min(contact_indices, default=-1)
    zero_indices = [
        index
        for index, row in enumerate(rows)
        if index > first_contact_index
        and first_contact_index >= 0
        and _is_zero_action(row.get("action"))
    ]
    awaiting_indices = [
        index
        for index, row in enumerate(rows)
        if index > first_contact_index
        and bool(row.get("box_safety_awaiting_neutral_ack", False))
    ]
    ack_indices = [
        index
        for index, row in enumerate(rows)
        if index > first_contact_index
        and bool(row.get("box_safety_neutral_acknowledged", False))
    ]
    return {
        "first_contact_step_id": _step(rows, first_contact_index),
        "first_zero_action_step_id": _step(
            rows,
            min(zero_indices, default=-1),
        ),
        "awaiting_neutral_ack_step_id": _step(
            rows,
            min(awaiting_indices, default=-1),
        ),
        "neutral_ack_step_id": _step(
            rows,
            min(ack_indices, default=-1),
        ),
        "zero_action_after_first_contact": bool(zero_indices),
        "neutral_acknowledged": bool(ack_indices),
    }


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    last_step = -1
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise WallContactABCollectionError(
                f"rollout_jsonl_invalid:line={line_number}"
            ) from exc
        if not isinstance(row, dict):
            raise WallContactABCollectionError(
                f"rollout_jsonl_row_invalid:line={line_number}"
            )
        step = int(row.get("step_id", -1))
        if step <= last_step:
            raise WallContactABCollectionError(
                "rollout_step_sequence_invalid"
            )
        last_step = step
        rows.append(row)
    if not rows:
        raise WallContactABCollectionError("rollout_jsonl_empty")
    return rows


def _frozen_handoff_sha(config_path: Path) -> str:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    metadata = _mapping(
        _mapping(config.get("eval"), "eval").get("record_hdf5_metadata"),
        "record_hdf5_metadata",
    )
    return _sha256(
        metadata.get("frozen_target_handoff_sha256"),
        "frozen_handoff",
    )


def _finite_vector(value: Any, size: int, label: str) -> list[float]:
    if (
        isinstance(value, (str, bytes))
        or not isinstance(value, Sequence)
        or len(value) != size
    ):
        raise WallContactABCollectionError(f"{label}_invalid")
    result = [float(item) for item in value]
    if not all(math.isfinite(item) for item in result):
        raise WallContactABCollectionError(f"{label}_nonfinite")
    return result


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise WallContactABCollectionError(f"{label}_invalid")
    return value


def _sha256(value: Any, label: str) -> str:
    text = str(value).strip().lower()
    if len(text) != 64 or any(
        char not in "0123456789abcdef" for char in text
    ):
        raise WallContactABCollectionError(f"{label}_sha256_invalid")
    return text


def _skill(row: Mapping[str, Any]) -> str:
    return str(row.get("skill_name", row.get("hybrid_mode", ""))).lower()


def _cycle(row: Mapping[str, Any]) -> int:
    return int(
        row.get(
            "primitive_cycle_index",
            row.get("cycle_id", -1),
        )
    )


def _env_flag(row: Mapping[str, Any], index: int) -> bool:
    env = row.get("env_state")
    return bool(
        isinstance(env, Sequence)
        and not isinstance(env, (str, bytes))
        and len(env) > index
        and math.isfinite(float(env[index]))
        and float(env[index]) >= 0.5
    )


def _is_zero_action(value: Any) -> bool:
    try:
        action = _finite_vector(value, 4, "action")
    except WallContactABCollectionError:
        return False
    return all(abs(item) <= 1.0e-8 for item in action)


def _step(rows: Sequence[Mapping[str, Any]], index: int) -> int:
    if index < 0 or index >= len(rows):
        return -1
    return int(rows[index].get("step_id", -1))


__all__ = [
    "ATTEMPT_SCHEMA",
    "ATTEMPT_SET_SCHEMA",
    "START_MARKER_SCHEMA",
    "TARGET_EXEMPLAR_ID",
    "TARGET_RAW_FIELDS_SHA256",
    "WallContactABCollectionError",
    "extract_paired_ab_attempt",
    "failed_paired_ab_attempt",
    "write_paired_ab_attempt_set",
]
