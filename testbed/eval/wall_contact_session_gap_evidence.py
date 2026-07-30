"""Evidence summaries for the diagnostic wall-contact session-gap probe."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from testbed.eval.wall_contact_artifact_io import (
    artifact_ref,
    load_json,
    locked_ref,
    mapping,
)
from testbed.eval.wall_contact_evidence_contracts import (
    CONTACT_DETAIL_WARNING_PREFIX,
    ContactEvidenceContractError,
    parse_worktool_wall_contact_detail,
    validate_reset_pair,
)

_B2_CODE_PATHS = (
    "testbed/planner/box_emptying/wall_contact_detail.py",
    "testbed/planner/box_emptying/safety_contracts.py",
    "testbed/planner/box_emptying/safety_interlock.py",
    "testbed/planner/primitive/config/adapter.py",
    "testbed/eval/suite.py",
    "testbed/eval/wall_contact_ab_collection.py",
    "testbed/eval/wall_contact_session_gap_probe.py",
    "testbed/eval/wall_contact_session_gap_evidence.py",
    "testbed/cli/wall_contact_session_gap_probe.py",
)


def lock_b2_code_lineage(repo_root: Path) -> list[dict[str, Any]]:
    """Hash every Python source that owns or records the B2 semantics."""

    return [
        {
            **artifact_ref(repo_root / relative_path),
            "relative_path": relative_path,
        }
        for relative_path in _B2_CODE_PATHS
    ]


def build_session_gap_report(
    *,
    manifest: Mapping[str, Any],
    attempt: Mapping[str, Any],
    attempt_path: Path,
    contact_evidence: Mapping[str, Any],
    expected_reset: Mapping[str, Any],
    report_schema: str,
    attempt_id: str,
    seed: int,
    clear_ticks_required: int,
    target_exemplar_id: str,
    target_raw_fields_sha256: str,
    downstream_gates: Mapping[str, bool],
) -> dict[str, Any]:
    """Build the immutable, diagnostic-only B2 causal report."""

    source_reset = mapping(
        mapping(manifest.get("reset_lineage"), "reset_lineage").get(
            "source_reset_state"
        ),
        "source_reset_state",
    )
    observed_reset = mapping(
        attempt.get("reset_state", {}),
        "observed_reset_state",
    )
    reset_fairness = summarize_reset_fairness(
        expected=expected_reset,
        source=source_reset,
        observed=observed_reset,
    )
    target_match = (
        attempt.get("selected_exemplar_id") == target_exemplar_id
        and attempt.get("selected_raw_fields_sha256")
        == target_raw_fields_sha256
    )
    bridge_observed = bool(
        contact_evidence.get("single_tick_rollover_bridge_observed", False)
    )
    contact_ended_before_carry = bool(
        attempt.get("contact_ended_before_carry", False)
    )
    blockers = list(attempt.get("blockers", []))
    if not reset_fairness["passed"]:
        blockers.append("b2_reset_fairness_invalid")
    if not target_match:
        blockers.append("b2_target_lineage_drift")
    if contact_evidence.get("status") != "passed":
        blockers.append("b2_contact_evidence_invalid")
    if attempt.get("status") != "passed":
        blockers.append("b2_attempt_extraction_failed")
    blockers = sorted(set(str(item) for item in blockers))
    status = "passed" if not blockers else "failed"
    if status != "passed" or not bridge_observed:
        outcome = "inconclusive"
    elif (
        bool(attempt.get("entered_carry", False))
        and bool(attempt.get("dump_completed", False))
        and contact_ended_before_carry
        and not bool(attempt.get("hard_violation", False))
    ):
        outcome = "single_clear_tick_split_supported"
    else:
        outcome = "single_clear_tick_split_not_supported"
    source_lock = mapping(manifest.get("source_lock"), "source_lock")
    return {
        "schema": report_schema,
        "status": status,
        "blockers": blockers,
        "outcome": outcome,
        "attempt_id": attempt_id,
        "seed": seed,
        "condition": "B",
        "diagnostic_variant": "B2",
        "executed_attempt_count": 1,
        "retry_count": 0,
        "retry_allowed": False,
        "session_end_clear_ticks": clear_ticks_required,
        "single_clear_tick_is_same_logical_session": True,
        "single_tick_rollover_bridge_observed": bridge_observed,
        "entered_carry": bool(attempt.get("entered_carry", False)),
        "dump_completed": bool(attempt.get("dump_completed", False)),
        "contact_ended_before_carry": contact_ended_before_carry,
        "terminal_reason": str(attempt.get("terminal_reason", "")),
        "hard_stop_violations": list(
            attempt.get("hard_stop_violations", [])
        ),
        "hard_violation": bool(attempt.get("hard_violation", False)),
        "reset_fairness": reset_fairness,
        "target_lineage_match": target_match,
        "physical_contact_sessions": contact_evidence[
            "physical_contact_sessions"
        ],
        "logical_contact_sessions": contact_evidence[
            "logical_contact_sessions"
        ],
        "contact_free_gaps": contact_evidence["contact_free_gaps"],
        "baseline_outcome": dict(
            mapping(manifest.get("baseline_outcome"), "baseline_outcome")
        ),
        "original_ab_conclusion_unchanged": True,
        "diagnostic_only": True,
        "non_promotable": True,
        "production_promotion_allowed": False,
        "writes_training_hdf5": False,
        "downstream_gates": dict(downstream_gates),
        "source_lock": {
            "manifest": artifact_ref(Path(str(manifest["manifest_path"]))),
            "attempt_result": artifact_ref(attempt_path),
            "baseline_config": dict(source_lock["baseline_config"]),
            "baseline_attempt": dict(source_lock["baseline_attempt"]),
            "baseline_rollout_jsonl": dict(
                source_lock["baseline_rollout_jsonl"]
            ),
            "expected_reset_state": dict(
                source_lock["expected_reset_state"]
            ),
        },
    }


def lock_original_environment(
    source_config_path: Path,
) -> dict[str, Any]:
    """Verify the original A/B Unity and target artifacts when available."""

    relative = Path("experiment_manifest.json")
    candidates = (
        source_config_path.parent / relative,
        source_config_path.parents[2] / relative,
    )
    manifest_path = next(
        (candidate for candidate in candidates if candidate.is_file()),
        candidates[-1],
    )
    if not manifest_path.is_file():
        return {
            "status": "not_available",
            "source_manifest_path": str(manifest_path),
        }
    manifest = load_json(manifest_path)
    source_lock = mapping(manifest.get("source_lock"), "source_lock")
    unity = mapping(source_lock.get("unity"), "source_lock.unity")
    contact_files = unity.get("contact_lineage_files")
    if not isinstance(contact_files, list) or not contact_files:
        raise ValueError("source_unity_contact_lineage_missing")
    scene = locked_ref(
        {
            "path": unity.get("scene_path"),
            "sha256": unity.get("scene_sha256"),
        },
        "source_unity_scene",
    )
    normalization = locked_ref(
        {
            "path": unity.get("normalization_path"),
            "sha256": unity.get("normalization_sha256"),
        },
        "source_unity_normalization",
    )
    return {
        "status": "verified",
        "experiment_manifest": artifact_ref(manifest_path),
        "frozen_target_handoff": locked_ref(
            mapping(
                source_lock.get("frozen_target_handoff"),
                "frozen_target_handoff",
            ),
            "frozen_target_handoff",
        ),
        "expected_reset_state": locked_ref(
            mapping(
                source_lock.get("expected_reset_state"),
                "expected_reset_state",
            ),
            "expected_reset_state",
        ),
        "execution_library": locked_ref(
            mapping(
                source_lock.get("execution_library"),
                "execution_library",
            ),
            "execution_library",
        ),
        "unity": {
            "scene": scene,
            "normalization": normalization,
            "contact_lineage_files": [
                locked_ref(mapping(item, "unity_contact_file"), "unity_contact_file")
                for item in contact_files
            ],
        },
    }


def summarize_session_gap_evidence(
    *,
    rollout_path: Path | None,
    target_cycle: int,
    clear_ticks_required: int,
) -> dict[str, Any]:
    """Summarize Unity physical sessions and Python logical sessions."""

    empty = {
        "status": "passed",
        "blockers": [],
        "physical_contact_sessions": {"count": 0, "sessions": []},
        "logical_contact_sessions": {"count": 0, "sessions": []},
        "contact_free_gaps": [],
        "single_tick_rollover_bridge_observed": False,
    }
    if rollout_path is None:
        return {**empty, "status": "failed", "blockers": ["rollout_missing"]}
    try:
        contacts = _contact_rows(
            rollout_path=rollout_path,
            target_cycle=target_cycle,
        )
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        ContactEvidenceContractError,
    ) as exc:
        return {
            **empty,
            "status": "failed",
            "blockers": [
                f"contact_evidence_parse_failed:{type(exc).__name__}:{exc}"
            ],
        }
    if not contacts:
        return empty

    physical = _physical_sessions(contacts)
    logical, gaps = _logical_sessions(
        contacts,
        clear_ticks_required=clear_ticks_required,
    )
    bridge = any(
        gap["contact_free_tick_count"] == 1
        and gap["physical_session_rollover"]
        and not gap["ends_logical_session"]
        for gap in gaps
    )
    return {
        "status": "passed",
        "blockers": [],
        "physical_contact_sessions": {
            "count": len(physical),
            "sessions": physical,
        },
        "logical_contact_sessions": {
            "count": len(logical),
            "sessions": logical,
        },
        "contact_free_gaps": gaps,
        "single_tick_rollover_bridge_observed": bridge,
    }


def summarize_reset_fairness(
    *,
    expected: Mapping[str, Any],
    source: Mapping[str, Any],
    observed: Mapping[str, Any],
) -> dict[str, Any]:
    """Check the new reset against both the frozen and source-run states."""

    try:
        evidence = validate_reset_pair(
            expected_reset_state=expected,
            reset_a=source,
            reset_b=observed,
        )
    except (KeyError, TypeError, ValueError) as exc:
        return {
            "passed": False,
            "blockers": [
                f"reset_state_contract_invalid:{type(exc).__name__}:{exc}"
            ],
            "thresholds": {},
            "measurements": {},
        }
    return {
        "passed": bool(evidence["valid"]),
        "blockers": list(evidence["violations"]),
        "thresholds": {
            "qpos_max_abs_delta": 0.005,
            "qvel_abs_max": 0.10,
            "qvel_paired_axis_max_abs_delta": 0.02,
            "bucket_tip_max_displacement_m": 0.02,
            "terrain_depth_max_abs_delta_m": 0.002,
            "remaining_mass_max_abs_delta_kg": 5.0,
        },
        "measurements": dict(evidence["metrics"]),
        "compared_against_frozen_expected": True,
        "compared_against_source_seed_2_b": True,
    }


def _contact_rows(
    *,
    rollout_path: Path,
    target_cycle: int,
) -> list[dict[str, Any]]:
    selected = [
        row
        for row in _load_jsonl(rollout_path)
        if _cycle(row) == target_cycle or target_cycle < 0
    ]
    contacts: list[dict[str, Any]] = []
    for index, row in enumerate(selected):
        warnings = row.get("warnings", [])
        if (
            isinstance(warnings, (str, bytes))
            or not isinstance(warnings, Sequence)
            or not any(
                (
                    isinstance(item, str)
                    and item.startswith(CONTACT_DETAIL_WARNING_PREFIX)
                )
                or (
                    isinstance(item, Mapping)
                    and item.get("schema")
                    == CONTACT_DETAIL_WARNING_PREFIX.removesuffix(":")
                )
                for item in warnings
            )
        ):
            continue
        detail = parse_worktool_wall_contact_detail(warnings)
        contacts.append(
            {
                "row_index": index,
                "step_id": int(row.get("step_id", -1)),
                "session_id": int(detail["session_id"]),
                "session_count": int(detail["session_count"]),
                "consecutive_contact_steps": int(
                    detail["consecutive_contact_steps"]
                ),
                "delta_time_s": float(detail["delta_time_s"]),
                "parts": list(detail["parts"]),
                "walls": list(detail["walls"]),
                "max_force_n": max(
                    float(pair["max_total_force_n"])
                    for pair in detail["pairs"]
                ),
            }
        )
    return contacts


def _physical_sessions(
    contacts: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    by_physical: dict[int, list[Mapping[str, Any]]] = {}
    for contact in contacts:
        by_physical.setdefault(int(contact["session_id"]), []).append(contact)
    return [
        {
            "session_id": session_id,
            "session_count_values": sorted(
                {int(item["session_count"]) for item in items}
            ),
            "first_step_id": int(items[0]["step_id"]),
            "last_step_id": int(items[-1]["step_id"]),
            "contact_tick_count": len(items),
            "parts": sorted(
                {str(part) for item in items for part in item["parts"]}
            ),
            "walls": sorted(
                {str(wall) for item in items for wall in item["walls"]}
            ),
            "peak_force_n": max(float(item["max_force_n"]) for item in items),
        }
        for session_id, items in by_physical.items()
    ]


def _logical_sessions(
    contacts: Sequence[Mapping[str, Any]],
    *,
    clear_ticks_required: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    logical_groups: list[list[Mapping[str, Any]]] = []
    gaps: list[dict[str, Any]] = []
    for contact in contacts:
        if not logical_groups:
            logical_groups.append([contact])
            continue
        previous = logical_groups[-1][-1]
        clear_ticks = int(contact["row_index"]) - int(previous["row_index"]) - 1
        ends_session = clear_ticks >= clear_ticks_required
        if clear_ticks > 0:
            nominal_dt = min(
                float(previous["delta_time_s"]),
                float(contact["delta_time_s"]),
            )
            gaps.append(
                {
                    "previous_contact_step_id": int(previous["step_id"]),
                    "next_contact_step_id": int(contact["step_id"]),
                    "contact_free_tick_count": clear_ticks,
                    "nominal_contact_free_duration_s": clear_ticks * nominal_dt,
                    "ends_logical_session": ends_session,
                    "physical_session_rollover": (
                        int(previous["session_id"])
                        != int(contact["session_id"])
                    ),
                }
            )
        if ends_session:
            logical_groups.append([contact])
        else:
            logical_groups[-1].append(contact)
    logical = [
        {
            "logical_session_id": index,
            "physical_session_ids": list(
                dict.fromkeys(int(item["session_id"]) for item in items)
            ),
            "first_step_id": int(items[0]["step_id"]),
            "last_step_id": int(items[-1]["step_id"]),
            "contact_tick_count": len(items),
        }
        for index, items in enumerate(logical_groups, start=1)
    ]
    return logical, gaps


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"rollout_row_invalid:{line_number}")
        rows.append(value)
    return rows


def _cycle(row: Mapping[str, Any]) -> int:
    return int(row.get("primitive_cycle_index", row.get("cycle_id", -1)))


__all__ = [
    "build_session_gap_report",
    "lock_b2_code_lineage",
    "lock_original_environment",
    "summarize_reset_fairness",
    "summarize_session_gap_evidence",
]
