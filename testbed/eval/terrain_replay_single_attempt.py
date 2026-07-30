"""Acceptance semantics for selecting one complete replay realization."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from testbed.eval.terrain_replay_pilot_gate import evaluate_replay_pilot_gate

SCHEMA = "terrain_replay_single_attempt_gate_v1"


def evaluate_single_replay_attempt(
    repeat: Mapping[str, Any],
    *,
    source_reference: Mapping[str, Any],
    required_source_episode_id: str,
    hdf5_audit: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate one replay without claiming repeatability or variance evidence."""

    pilot = evaluate_replay_pilot_gate(
        [dict(repeat)],
        source_reference=source_reference,
        required_source_episode_id=str(required_source_episode_id),
        required_repeat_count=1,
        semantic_repeat_fraction_min=1.0,
    )
    semantic_results = list(pilot.get("semantic_repeat_results", []))
    semantic_pass = bool(
        len(semantic_results) == 1 and semantic_results[0].get("pass", False)
    )
    hdf5_pass = bool(hdf5_audit.get("pass", False))
    failed_checks: list[str] = []
    if not bool(pilot.get("process_integrity_pass", False)):
        failed_checks.append("process_integrity_failed")
    if not semantic_pass:
        failed_checks.append("semantic_attempt_failed")
    if not hdf5_pass:
        failed_checks.append("hdf5_audit_failed")
    validation_errors = [str(item) for item in pilot.get("validation_errors", [])]
    validation_errors.extend(str(item) for item in hdf5_audit.get("errors", []))
    status = "present" if not validation_errors else "invalid_inputs"
    passed = status == "present" and not failed_checks
    return {
        "schema": SCHEMA,
        "status": status,
        "pass": passed,
        "source_episode_id": str(required_source_episode_id),
        "attempt_id": str(repeat.get("repeat_id", "")),
        "process_integrity_pass": bool(pilot.get("process_integrity_pass", False)),
        "semantic_attempt_pass": semantic_pass,
        "hdf5_audit_pass": hdf5_pass,
        "repeatability_status": "not_assessed_single_attempt",
        "effect_label_status": "single_realization_silver",
        "evidence_kind": "replay_derived_selected_pass",
        "gold_status": "not_gold",
        "post_contact_qpos_gate": "diagnostic_only",
        "semantic_result": semantic_results[0] if semantic_results else {},
        "hdf5_audit": dict(hdf5_audit),
        "pilot_process_failed_checks": [
            str(item)
            for item in pilot.get("failed_checks", [])
            if str(item)
            not in {
                "semantic_pass_repeat_count_below_minimum",
                "target_completion_std_exceeded",
                "final_grid_max_cell_std_exceeded",
            }
        ],
        "failed_checks": failed_checks,
        "validation_errors": list(dict.fromkeys(validation_errors)),
    }


__all__ = ["SCHEMA", "evaluate_single_replay_attempt"]
