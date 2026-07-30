"""Residual cut-intent execution and dump-exit diagnostics."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


SCHEMA = "terrain_residual_execution_diagnostic_v1"
SOURCE = "residual_cut_intent_execution_quality_diagnostic"
FAILURE_PACKET_SCHEMA = "terrain_residual_official_v0_failure_packet_v1"
FAILURE_PACKET_SOURCE = "request_local_official_v0_failure_packet_builder"
DEPTH_OVERSHOOT_TOLERANCE_M = 0.05


def build_terrain_residual_execution_diagnostic(
    *,
    runtime_source: Mapping[str, Any],
    rollout_summary: Mapping[str, Any],
    rollout_records: Sequence[Mapping[str, Any]] | None = None,
    target_id: str,
    branch_name: str,
    depth_overshoot_tolerance_m: float = DEPTH_OVERSHOOT_TOLERANCE_M,
) -> dict[str, Any]:
    """Align residual cut intents with real execution and dump-exit evidence."""

    if not isinstance(runtime_source, Mapping) or not isinstance(
        rollout_summary,
        Mapping,
    ):
        return _result(
            status="invalid_inputs",
            target_id=target_id,
            branch_name=branch_name,
            cycles=[],
            summary={},
            validation_errors=[
                "runtime_source and rollout_summary must be mappings",
            ],
        )

    plans = runtime_source.get("plans")
    if not isinstance(plans, Sequence) or isinstance(plans, (str, bytes)):
        return _result(
            status="invalid_runtime_source",
            target_id=target_id,
            branch_name=branch_name,
            cycles=[],
            summary={},
            validation_errors=["runtime_source must include plans list"],
        )

    dump_exits = _dump_exits_by_cycle(rollout_records or [])
    cycles = [
        cycle
        for plan in plans
        if isinstance(plan, Mapping)
        and (
            cycle := _cycle_diagnostic(
                plan=plan,
                rollout_summary=rollout_summary,
                dump_exits=dump_exits,
                depth_overshoot_tolerance_m=float(depth_overshoot_tolerance_m),
            )
        )
        is not None
    ]
    summary = _summary(cycles=cycles, rollout_summary=rollout_summary)
    return _result(
        status="present" if cycles else "missing_cycles",
        target_id=target_id,
        branch_name=branch_name,
        cycles=cycles,
        summary=summary,
        validation_errors=[],
    )


def write_terrain_residual_execution_diagnostic(
    *,
    runtime_source_path: Any,
    rollout_summary_path: Any,
    rollout_jsonl_path: Any,
    output_path: Any,
    target_id: str,
    branch_name: str,
    depth_overshoot_tolerance_m: float = DEPTH_OVERSHOOT_TOLERANCE_M,
) -> dict[str, Any]:
    """Read explicit artifacts and write a no-overwrite execution diagnostic."""

    target_path = Path(output_path)
    if target_path.exists():
        return {
            "schema": SCHEMA,
            "source": SOURCE,
            "status": "output_path_already_exists",
            "output_path": str(target_path),
            "validation_errors": ["output_path must not already exist before writing"],
        }

    runtime_source, source_errors = _read_json_object(Path(runtime_source_path))
    rollout_summary, summary_errors = _read_json_object(Path(rollout_summary_path))
    rollout_records, record_errors = _read_jsonl_records(Path(rollout_jsonl_path))
    validation_errors = source_errors + summary_errors + record_errors
    if validation_errors:
        return {
            "schema": SCHEMA,
            "source": SOURCE,
            "status": "invalid_input_artifacts",
            "output_path": str(target_path),
            "validation_errors": validation_errors,
        }

    result = build_terrain_residual_execution_diagnostic(
        runtime_source=runtime_source,
        rollout_summary=rollout_summary,
        rollout_records=rollout_records,
        target_id=target_id,
        branch_name=branch_name,
        depth_overshoot_tolerance_m=depth_overshoot_tolerance_m,
    )
    result = {
        **result,
        "output_path": str(target_path),
        "input_paths": {
            "runtime_source_path": str(runtime_source_path),
            "rollout_summary_path": str(rollout_summary_path),
            "rollout_jsonl_path": str(rollout_jsonl_path),
        },
    }
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        return {
            **result,
            "status": "write_failed",
            "validation_errors": [f"execution diagnostic write failed: {exc}"],
        }
    return result


def build_official_v0_failure_packet(
    *,
    official_v0_comparison: Mapping[str, Any],
    depth_execution_diagnostic_index: Mapping[str, Any],
) -> dict[str, Any]:
    """Summarize official-v0 B failures without changing planner behavior."""

    if not isinstance(official_v0_comparison, Mapping) or not isinstance(
        depth_execution_diagnostic_index,
        Mapping,
    ):
        return {
            "schema": FAILURE_PACKET_SCHEMA,
            "source": FAILURE_PACKET_SOURCE,
            "status": "invalid_inputs",
            "target_count": 0,
            "targets": [],
            "conclusion": _failure_packet_conclusion([]),
            "non_goal_statuses": _non_goal_statuses(),
            "validation_errors": [
                "official_v0_comparison and depth_execution_diagnostic_index must be mappings",
            ],
        }

    comparison_targets = _target_map(official_v0_comparison.get("targets"))
    diagnostic_targets = _target_map(depth_execution_diagnostic_index.get("targets"))
    targets = [
        _failure_packet_target(
            target_id=target_id,
            comparison_target=comparison_target,
            depth_diagnostic=diagnostic_targets.get(target_id, {}),
        )
        for target_id, comparison_target in sorted(comparison_targets.items())
    ]
    return {
        "schema": FAILURE_PACKET_SCHEMA,
        "source": FAILURE_PACKET_SOURCE,
        "status": "present" if targets else "missing_targets",
        "official_v0_comparison_status": str(
            official_v0_comparison.get("status") or ""
        ),
        "depth_execution_diagnostic_index_status": str(
            depth_execution_diagnostic_index.get("status") or ""
        ),
        "target_count": len(targets),
        "targets": targets,
        "conclusion": _failure_packet_conclusion(targets),
        "non_goal_statuses": _non_goal_statuses(),
        "validation_errors": [],
    }


def write_official_v0_failure_packet(
    *,
    official_v0_comparison_path: Any,
    depth_execution_diagnostic_index_path: Any,
    output_path: Any,
) -> dict[str, Any]:
    """Read official-v0 artifacts and write a no-overwrite failure packet."""

    target_path = Path(output_path)
    if target_path.exists():
        return {
            "schema": FAILURE_PACKET_SCHEMA,
            "source": FAILURE_PACKET_SOURCE,
            "status": "output_path_already_exists",
            "output_path": str(target_path),
            "validation_errors": ["output_path must not already exist before writing"],
        }

    comparison, comparison_errors = _read_json_object(Path(official_v0_comparison_path))
    diagnostics, diagnostic_errors = _read_json_object(
        Path(depth_execution_diagnostic_index_path),
    )
    validation_errors = comparison_errors + diagnostic_errors
    if validation_errors:
        return {
            "schema": FAILURE_PACKET_SCHEMA,
            "source": FAILURE_PACKET_SOURCE,
            "status": "invalid_input_artifacts",
            "output_path": str(target_path),
            "validation_errors": validation_errors,
        }

    result = build_official_v0_failure_packet(
        official_v0_comparison=comparison,
        depth_execution_diagnostic_index=diagnostics,
    )
    result = {
        **result,
        "output_path": str(target_path),
        "input_paths": {
            "official_v0_comparison_path": str(official_v0_comparison_path),
            "depth_execution_diagnostic_index_path": str(
                depth_execution_diagnostic_index_path,
            ),
        },
    }
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        return {
            **result,
            "status": "write_failed",
            "validation_errors": [f"official v0 failure packet write failed: {exc}"],
        }
    return result


def _result(
    *,
    status: str,
    target_id: str,
    branch_name: str,
    cycles: list[dict[str, Any]],
    summary: Mapping[str, Any],
    validation_errors: list[str],
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "source": SOURCE,
        "status": status,
        "target_id": str(target_id),
        "branch_name": str(branch_name),
        "cycles": cycles,
        "summary": dict(summary),
        "root_cause_hypothesis": _root_cause_hypothesis(summary),
        "non_goal_statuses": _non_goal_statuses(),
        "validation_errors": list(validation_errors),
    }


def _non_goal_statuses() -> dict[str, str]:
    return {
        "planner_behavior_change_status": "not_made",
        "checked_in_default_config_change": "not_made",
        "production_readiness_status": "not_claimed",
        "calibrated_branch_status": "blocked_pending_gold_replay_samples",
    }


def _target_map(value: Any) -> dict[str, Mapping[str, Any]]:
    if isinstance(value, Mapping):
        return {
            str(target_id): target
            for target_id, target in value.items()
            if isinstance(target, Mapping)
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        result: dict[str, Mapping[str, Any]] = {}
        for target in value:
            if not isinstance(target, Mapping):
                continue
            target_id = str(target.get("target_id") or "")
            if target_id:
                result[target_id] = target
        return result
    return {}


def _failure_packet_target(
    *,
    target_id: str,
    comparison_target: Mapping[str, Any],
    depth_diagnostic: Mapping[str, Any],
) -> dict[str, Any]:
    branches = _mapping(comparison_target.get("branches"))
    a_branch = _select_branch(
        branches,
        (
            "A",
            "current",
            "current_planner_baseline",
        ),
    )
    b_branch = _select_branch(
        branches,
        (
            "B",
            "residual",
            "heuristic_residual_pipeline",
            "heuristic_residual_pipeline_target_specific_rerun",
        ),
    )
    b_pass_fail = _mapping(b_branch.get("official_pass_fail"))
    summary = _mapping(depth_diagnostic.get("summary"))
    root_cause = _mapping(depth_diagnostic.get("root_cause_hypothesis"))
    return {
        "target_id": str(comparison_target.get("target_id") or target_id),
        "official_b_pass": _bool_or_none(b_pass_fail.get("pass")),
        "official_b_failed_checks": _string_list(b_pass_fail.get("failed_checks")),
        "depth_execution_status": str(depth_diagnostic.get("status") or ""),
        "depth_overshoot_cycle_count": _int_or_none(
            summary.get("depth_overshoot_cycle_count"),
        ),
        "mean_depth_peak_minus_intent_m": _metric_float_or_none(
            summary.get("mean_depth_peak_minus_intent_m"),
        ),
        "mean_deposited_fraction": _metric_float_or_none(
            summary.get("mean_deposited_fraction"),
        ),
        "target_cycle_gate_success": _int_or_none(
            summary.get("target_cycle_gate_success"),
        ),
        "transition_timeout_count": _int_or_none(
            summary.get("transition_timeout_count"),
        ),
        "root_cause_primary_category": str(
            root_cause.get("primary_category") or "",
        ),
        "artifact_refs": _artifact_refs(a_branch=a_branch, b_branch=b_branch),
    }


def _failure_packet_conclusion(targets: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    if not targets:
        return {
            "status": "missing_targets",
            "primary_blocker": "missing_official_v0_target_evidence",
            "official_v0_b_pass_status": "not_evaluated",
        }
    b_pass_values = [target.get("official_b_pass") for target in targets]
    b_failed = any(value is False for value in b_pass_values)
    primary_blocker = next(
        (
            str(target.get("root_cause_primary_category"))
            for target in targets
            if target.get("root_cause_primary_category")
        ),
        "official_v0_b_failure",
    )
    return {
        "status": "b_not_promoted" if b_failed else "b_not_blocked_by_packet",
        "primary_blocker": primary_blocker,
        "official_v0_b_pass_status": "failed" if b_failed else "passed",
    }


def _artifact_refs(
    *,
    a_branch: Mapping[str, Any],
    b_branch: Mapping[str, Any],
) -> dict[str, str]:
    refs = {
        "a_cycle_quality_report_path": _text_or_none(
            _artifact_path(a_branch, "cycle_quality_report_path"),
        ),
        "b_cycle_quality_report_path": _text_or_none(
            _artifact_path(b_branch, "cycle_quality_report_path"),
        ),
        "b_runtime_source_path": _text_or_none(
            _artifact_path(b_branch, "runtime_source_path")
            or _artifact_path(b_branch, "source_mixed_path")
            or _artifact_path(b_branch, "residual_cut_intent_runtime_source_path"),
        ),
    }
    return {key: value for key, value in refs.items() if value}


def _select_branch(
    branches: Mapping[str, Any],
    names: Sequence[str],
) -> Mapping[str, Any]:
    for name in names:
        branch = branches.get(name)
        if isinstance(branch, Mapping):
            return branch
    return {}


def _artifact_path(branch: Mapping[str, Any], key: str) -> Any:
    if key in branch:
        return branch.get(key)
    artifact_paths = branch.get("artifact_paths")
    if isinstance(artifact_paths, Mapping):
        return artifact_paths.get(key)
    return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [str(item) for item in value]


def _text_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _cycle_diagnostic(
    *,
    plan: Mapping[str, Any],
    rollout_summary: Mapping[str, Any],
    dump_exits: Mapping[int, Mapping[str, Any]],
    depth_overshoot_tolerance_m: float,
) -> dict[str, Any] | None:
    cycle_index = _int_or_none(plan.get("cycle_index"))
    if cycle_index is None:
        return None
    plan_payload = _mapping(plan.get("plan"))
    raw_fields = _mapping(plan_payload.get("raw_fields"))
    intent = _intent_summary(
        raw_fields=raw_fields,
        dig_cut_tokens=plan_payload.get("dig_cut_tokens"),
        token_contract=_mapping(plan_payload.get("dig_cut_token_contract")),
    )
    execution = _execution_summary(
        cycle_index=cycle_index,
        rollout_summary=rollout_summary,
        intent=intent,
    )
    dump_exit = _dump_exit_summary(dump_exits.get(cycle_index))
    if not _has_execution_evidence(execution, dump_exit):
        return None
    depth_gap = _finite_float(execution.get("depth_peak_minus_intent_m"))
    return {
        "cycle_index": int(cycle_index),
        "candidate_id": str(
            plan.get("cut_intent_candidate_id")
            or plan_payload.get("candidate_id")
            or ""
        ),
        "intent_summary": intent,
        "execution_summary": execution,
        "dump_exit_summary": dump_exit,
        "diagnosis_flags": {
            "depth_peak_exceeds_intent": bool(
                depth_gap is not None and depth_gap > depth_overshoot_tolerance_m
            ),
            "return_handoff_reachable": bool(
                (_int_or_none(rollout_summary.get("target_cycle_gate_success")) or 0)
                == 1
                and (_int_or_none(rollout_summary.get("transition_timeout_count")) or 0)
                == 0
            ),
        },
    }


def _intent_summary(
    *,
    raw_fields: Mapping[str, Any],
    dig_cut_tokens: Any,
    token_contract: Mapping[str, Any],
) -> dict[str, Any]:
    depth_scale = _finite_float(token_contract.get("depth_scale_m")) or 0.8
    depth_norm = _sequence_float(dig_cut_tokens, 7)
    return {
        "entry_x_m": _metric_float_or_none(raw_fields.get("operator_entry_x_m")),
        "entry_z_m": _metric_float_or_none(raw_fields.get("operator_entry_z_m")),
        "exit_x_m": _metric_float_or_none(raw_fields.get("operator_exit_x_m")),
        "exit_z_m": _metric_float_or_none(raw_fields.get("operator_exit_z_m")),
        "cut_length_m": _metric_float_or_none(raw_fields.get("operator_cut_length_m")),
        "cut_depth_peak_m": _metric_float_or_none(
            raw_fields.get("operator_cut_depth_peak_m"),
        ),
        "token_cut_depth_peak_m": (
            _metric_float(depth_norm * depth_scale)
            if depth_norm is not None
            else None
        ),
        "cut_payload_gain_kg": _metric_float_or_none(
            raw_fields.get("operator_cut_payload_gain_kg"),
        ),
        "effective_deposit_delta_kg": _metric_float_or_none(
            raw_fields.get("operator_effective_deposit_delta_kg"),
        ),
    }


def _execution_summary(
    *,
    cycle_index: int,
    rollout_summary: Mapping[str, Any],
    intent: Mapping[str, Any],
) -> dict[str, Any]:
    prefix = f"cycle{cycle_index + 1}_"
    depth_peak = _summary_float(rollout_summary, prefix + "depth_peak_m")
    intent_depth = _finite_float(intent.get("cut_depth_peak_m"))
    depth_gap = _delta(intent_depth, depth_peak)
    entry_error = _point_error(
        intent.get("entry_x_m"),
        intent.get("entry_z_m"),
        rollout_summary.get(prefix + "entry_actual_x_m"),
        rollout_summary.get(prefix + "entry_actual_z_m"),
    )
    exit_error = _point_error(
        intent.get("exit_x_m"),
        intent.get("exit_z_m"),
        rollout_summary.get(prefix + "exit_actual_x_m"),
        rollout_summary.get(prefix + "exit_actual_z_m"),
    )
    return {
        "depth_target_m": _summary_float(rollout_summary, prefix + "depth_target_m"),
        "depth_peak_m": depth_peak,
        "depth_abs_error_m": _summary_float(
            rollout_summary,
            prefix + "depth_abs_error_m",
        ),
        "depth_peak_minus_intent_m": depth_gap,
        "depth_peak_to_intent_ratio": (
            _metric_float(depth_peak / intent_depth)
            if depth_peak is not None and intent_depth and intent_depth > 0.0
            else None
        ),
        "entry_actual_x_m": _summary_float(
            rollout_summary,
            prefix + "entry_actual_x_m",
        ),
        "entry_actual_z_m": _summary_float(
            rollout_summary,
            prefix + "entry_actual_z_m",
        ),
        "entry_actual_error_vs_intent_m": entry_error,
        "exit_actual_x_m": _summary_float(
            rollout_summary,
            prefix + "exit_actual_x_m",
        ),
        "exit_actual_z_m": _summary_float(
            rollout_summary,
            prefix + "exit_actual_z_m",
        ),
        "exit_actual_error_vs_intent_m": exit_error,
        "payload_mass_kg": _summary_float(
            rollout_summary,
            prefix + "bucket_mass_out_kg",
        ),
        "effective_deposit_mass_kg": _summary_float(
            rollout_summary,
            prefix + "target_deposit_final_delta_kg",
        ),
        "deposited_fraction": _summary_float(
            rollout_summary,
            prefix + "deposited_fraction",
        ),
        "success": _int_or_none(rollout_summary.get(prefix + "success")),
    }


def _dump_exits_by_cycle(
    rollout_records: Sequence[Mapping[str, Any]],
) -> dict[int, Mapping[str, Any]]:
    exits: dict[int, Mapping[str, Any]] = {}
    for row_index, row in enumerate(rollout_records):
        if not isinstance(row, Mapping) or not _truthy(row.get("dump_end_mask")):
            continue
        cycle_index = _int_or_none(row.get("primitive_cycle_index"))
        if cycle_index is None:
            continue
        exits[int(cycle_index)] = {**row, "_row_index": int(row_index)}
    return exits


def _dump_exit_summary(row: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(row, Mapping):
        return {
            "dump_end_row_index": None,
            "return_target_token_source": "",
            "return_start_envelope_token_source": "",
            "return_to_dig_entry_error_m": None,
            "return_to_dig_start_envelope_ready": None,
            "return_to_dig_start_envelope_error": None,
            "failed_envelope_check_names": [],
        }
    return {
        "dump_end_row_index": _int_or_none(row.get("_row_index")),
        "return_target_token_source": str(row.get("return_target_token_source") or ""),
        "return_start_envelope_token_source": str(
            row.get("return_start_envelope_token_source") or "",
        ),
        "return_to_dig_entry_error_m": _metric_float_or_none(
            row.get("return_to_dig_entry_error_m"),
        ),
        "return_to_dig_start_envelope_ready": _bool_or_none(
            row.get("return_to_dig_start_envelope_ready"),
        ),
        "return_to_dig_start_envelope_error": _metric_float_or_none(
            row.get("return_to_dig_start_envelope_error"),
        ),
        "failed_envelope_check_names": _failed_envelope_check_names(
            row.get("return_to_dig_start_envelope_checks"),
        ),
    }


def _has_execution_evidence(
    execution: Mapping[str, Any],
    dump_exit: Mapping[str, Any],
) -> bool:
    for field in (
        "depth_peak_m",
        "depth_abs_error_m",
        "payload_mass_kg",
        "effective_deposit_mass_kg",
        "deposited_fraction",
    ):
        if _finite_float(execution.get(field)) is not None:
            return True
    return _int_or_none(dump_exit.get("dump_end_row_index")) is not None


def _summary(
    *,
    cycles: list[Mapping[str, Any]],
    rollout_summary: Mapping[str, Any],
) -> dict[str, Any]:
    depth_gaps = [
        cycle["execution_summary"].get("depth_peak_minus_intent_m")
        for cycle in cycles
        if isinstance(cycle.get("execution_summary"), Mapping)
    ]
    deposited_fractions = [
        cycle["execution_summary"].get("deposited_fraction")
        for cycle in cycles
        if isinstance(cycle.get("execution_summary"), Mapping)
    ]
    return {
        "cycle_count": len(cycles),
        "depth_overshoot_cycle_count": sum(
            1
            for cycle in cycles
            if _mapping(cycle.get("diagnosis_flags")).get(
                "depth_peak_exceeds_intent",
            )
            is True
        ),
        "mean_depth_peak_minus_intent_m": _mean(depth_gaps),
        "mean_deposited_fraction": _mean(deposited_fractions),
        "target_cycle_gate_success": _int_or_none(
            rollout_summary.get("target_cycle_gate_success"),
        ),
        "target_cycle_completed_dump_count": _int_or_none(
            rollout_summary.get("target_cycle_completed_dump_count"),
        ),
        "transition_timeout_count": _int_or_none(
            rollout_summary.get("transition_timeout_count"),
        ),
    }


def _root_cause_hypothesis(summary: Mapping[str, Any]) -> dict[str, str]:
    if not summary:
        return {
            "status": "not_evaluated",
            "primary_category": "insufficient_execution_diagnostic_evidence",
            "planner_behavior_change_status": "not_made",
            "evidence_summary": "no aligned execution cycles",
        }
    if (
        int(summary.get("target_cycle_gate_success") or 0) == 1
        and int(summary.get("transition_timeout_count") or 0) == 0
        and int(summary.get("depth_overshoot_cycle_count") or 0) > 0
    ):
        return {
            "status": "present",
            "primary_category": "act_depth_execution_quality_or_dump_exit_state",
            "planner_behavior_change_status": "not_made",
            "evidence_summary": "gate reached with zero transition timeouts, but depth peak exceeds intent on completed cycles",
        }
    if int(summary.get("transition_timeout_count") or 0) > 0:
        return {
            "status": "present",
            "primary_category": "return_reachability_or_handoff_state",
            "planner_behavior_change_status": "not_made",
            "evidence_summary": "transition timeout present in rollout summary",
        }
    return {
        "status": "not_evaluated",
        "primary_category": "diagnostic_only",
        "planner_behavior_change_status": "not_made",
        "evidence_summary": "no single root-cause category selected",
    }


def _read_json_object(path: Path) -> tuple[dict[str, Any], list[str]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return {}, [f"{path} could not be read: {exc}"]
    except json.JSONDecodeError as exc:
        return {}, [f"{path} invalid JSON: {exc.msg}"]
    if not isinstance(payload, dict):
        return {}, [f"{path} must be a JSON object"]
    return payload, []


def _read_jsonl_records(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [], [f"{path} could not be read: {exc}"]
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            return [], [f"{path}:{line_number} invalid JSON: {exc.msg}"]
        if not isinstance(payload, dict):
            return [], [f"{path}:{line_number} must be a JSON object"]
        records.append(payload)
    return records, []


def _failed_envelope_check_names(value: Any) -> list[str]:
    if not isinstance(value, Mapping):
        return []
    failed = [
        str(name)
        for name, check in value.items()
        if isinstance(check, Mapping) and check.get("ok") is False
    ]
    return sorted(failed)


def _point_error(
    x0: Any,
    z0: Any,
    x1: Any,
    z1: Any,
) -> float | None:
    parsed = [_finite_float(value) for value in (x0, z0, x1, z1)]
    if any(value is None for value in parsed):
        return None
    start_x, start_z, end_x, end_z = [value for value in parsed if value is not None]
    return _metric_float(math.hypot(end_x - start_x, end_z - start_z))


def _delta(start: Any, end: Any) -> float | None:
    parsed_start = _finite_float(start)
    parsed_end = _finite_float(end)
    if parsed_start is None or parsed_end is None:
        return None
    return _metric_float(parsed_end - parsed_start)


def _mean(values: Sequence[Any]) -> float | None:
    parsed = [_finite_float(value) for value in values]
    finite = [value for value in parsed if value is not None]
    if not finite:
        return None
    return _metric_float(sum(finite) / len(finite))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _summary_float(summary: Mapping[str, Any], key: str) -> float | None:
    return _metric_float_or_none(summary.get(key))


def _sequence_float(value: Any, index: int) -> float | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    if len(value) <= index:
        return None
    return _finite_float(value[index])


def _bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return bool(value)
    return None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return value != 0
    return False


def _int_or_none(value: Any) -> int | None:
    parsed = _finite_float(value)
    return None if parsed is None else int(parsed)


def _metric_float_or_none(value: Any) -> float | None:
    parsed = _finite_float(value)
    return None if parsed is None else _metric_float(parsed)


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def _metric_float(value: float) -> float:
    rounded = round(float(value), 12)
    return 0.0 if rounded == -0.0 else rounded
