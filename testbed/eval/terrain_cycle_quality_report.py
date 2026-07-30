"""Per-cycle terrain residual and execution-quality diagnostics."""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from testbed.data.schema import (
    ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
    ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX,
    ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
)
from testbed.eval.terrain_residual_contract import (
    evaluate_cycle_quality_against_baseline,
    get_official_terrain_residual_target_spec,
)
from testbed.eval.terrain_target_grid import build_rectangular_target_grid
from testbed.eval.terrain_target_metrics import build_target_residual_metrics

SCHEMA = "terrain_cycle_quality_report_v1"
SOURCE = "rollout_jsonl_per_cycle_terrain_quality_report"
DEFAULT_PROFILE = "explicit_t1_like_rectangular_shallow_pit"
GRID_CELL_COUNT = 6
RETURN_HANDOFF_READY_REASON = "return_to_dig_start_envelope_ready"


def build_terrain_cycle_quality_report(
    rollout_records: list[dict[str, Any]],
    *,
    grid_shape: Sequence[Any] | None = None,
    row_start: int | None = None,
    row_end: int | None = None,
    col_start: int | None = None,
    col_end: int | None = None,
    target_depth_m: float | None = None,
    official_target_id: str | None = None,
    branch_name: str = "",
    rollout_summary: Mapping[str, Any] | None = None,
    baseline_quality_summary: Mapping[str, Any] | None = None,
    profile: str = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Build a diagnostic per-cycle report from one rollout and explicit target."""

    cycle_rows, transition_events, timeout_events = _cycle_inputs(rollout_records)
    target_spec = _target_spec(
        grid_shape=grid_shape,
        row_start=row_start,
        row_end=row_end,
        col_start=col_start,
        col_end=col_end,
        target_depth_m=target_depth_m,
        official_target_id=official_target_id,
        profile=profile,
    )
    if target_spec.get("status") != "present":
        return {
            "status": "invalid_target_spec",
            "source": SOURCE,
            "schema": SCHEMA,
            "branch_name": str(branch_name),
            "target_spec": target_spec,
            "cycles": [],
            "summary": _summary("invalid_target_spec", []),
            "official_quality_summary": {},
            "official_pass_fail": _official_pass_fail_not_evaluated(
                "invalid_target_spec",
            ),
            "limitations": _limitations("invalid_target_spec"),
        }
    resolved_grid_shape = target_spec["grid_shape"]
    resolved_row_start = int(target_spec["row_start"])
    resolved_row_end = int(target_spec["row_end"])
    resolved_col_start = int(target_spec["col_start"])
    resolved_col_end = int(target_spec["col_end"])
    resolved_target_depth_m = float(target_spec["target_depth_m"])
    cycles = [
        _cycle_report(
            cycle_index,
            rows,
            transition_events=transition_events.get(cycle_index, []),
            timeout_events=timeout_events.get(cycle_index, []),
            grid_shape=resolved_grid_shape,
            row_start=resolved_row_start,
            row_end=resolved_row_end,
            col_start=resolved_col_start,
            col_end=resolved_col_end,
            target_depth_m=resolved_target_depth_m,
            rollout_summary=rollout_summary or {},
            profile=profile,
        )
        for cycle_index, rows in sorted(cycle_rows.items())
    ]
    status = "present" if cycles else "missing_cycles"
    summary = _summary(status, cycles)
    official_quality_summary = _official_quality_summary(
        summary,
        cycles=cycles,
        rollout_summary=rollout_summary or {},
    )
    official_pass_fail = (
        evaluate_cycle_quality_against_baseline(
            candidate_summary=official_quality_summary,
            baseline_summary=baseline_quality_summary,
            target_id=str(target_spec.get("target_id", "")),
        )
        if baseline_quality_summary is not None and target_spec.get("target_id")
        else _official_pass_fail_not_evaluated("baseline_quality_summary_not_provided")
    )
    return {
        "status": status,
        "source": SOURCE,
        "schema": SCHEMA,
        "branch_name": str(branch_name),
        "target_spec": target_spec,
        "cycles": cycles,
        "summary": summary,
        "official_quality_summary": official_quality_summary,
        "official_pass_fail": official_pass_fail,
        "limitations": _limitations(str(official_pass_fail.get("status"))),
    }


def write_terrain_cycle_quality_report(
    *,
    rollout_jsonl_path: Any,
    rollout_summary_path: Any,
    output_path: Any,
    grid_shape: Sequence[Any] | None = None,
    row_start: int | None = None,
    row_end: int | None = None,
    col_start: int | None = None,
    col_end: int | None = None,
    target_depth_m: float | None = None,
    official_target_id: str | None = None,
    branch_name: str = "",
    profile: str = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Read one rollout's artifacts and write a per-cycle quality report JSON."""

    normalized_output_path = str(output_path)
    target_path = Path(normalized_output_path)
    if target_path.exists():
        return {
            "status": "output_path_already_exists",
            "source": SOURCE,
            "schema": SCHEMA,
            "branch_name": str(branch_name),
            "output_path": normalized_output_path,
            "validation_errors": ["output_path must not already exist before writing"],
        }

    records, record_errors = _read_jsonl_records(Path(rollout_jsonl_path))
    summary, summary_errors = _read_json_object(Path(rollout_summary_path))
    validation_errors = record_errors + summary_errors
    if validation_errors:
        return {
            "status": "invalid_input_artifacts",
            "source": SOURCE,
            "schema": SCHEMA,
            "branch_name": str(branch_name),
            "output_path": normalized_output_path,
            "validation_errors": validation_errors,
        }

    report = build_terrain_cycle_quality_report(
        records,
        grid_shape=grid_shape,
        row_start=row_start,
        row_end=row_end,
        col_start=col_start,
        col_end=col_end,
        target_depth_m=target_depth_m,
        official_target_id=official_target_id,
        branch_name=branch_name,
        rollout_summary=summary,
        profile=profile,
    )
    result = {
        **report,
        "output_path": normalized_output_path,
        "input_paths": {
            "rollout_jsonl_path": str(rollout_jsonl_path),
            "rollout_summary_path": str(rollout_summary_path),
        },
        "validation_errors": [],
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
            "validation_errors": [f"cycle quality report write failed: {exc}"],
        }
    return result


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


def _cycle_inputs(
    rollout_records: list[dict[str, Any]],
) -> tuple[
    dict[int, list[tuple[int, dict[str, Any]]]],
    dict[int, list[int]],
    dict[int, list[int]],
]:
    cycle_rows: dict[int, list[tuple[int, dict[str, Any]]]] = {}
    transition_events: dict[int, list[int]] = {}
    timeout_events: dict[int, list[int]] = {}
    for row_index, row in enumerate(rollout_records):
        cycle_index = _int_or_none(row.get("primitive_cycle_index"))
        if cycle_index is not None and cycle_index >= 0:
            cycle_rows.setdefault(cycle_index, []).append((row_index, row))

        reason = str(row.get("skill_switch_reason") or "")
        if reason == RETURN_HANDOFF_READY_REASON and cycle_index is not None:
            handoff_cycle = cycle_index - 1 if cycle_index > 0 else cycle_index
            if handoff_cycle >= 0:
                transition_events.setdefault(handoff_cycle, []).append(row_index)
        if "return_to_dig" in reason and "timeout" in reason and cycle_index is not None:
            timeout_events.setdefault(cycle_index, []).append(row_index)
    return cycle_rows, transition_events, timeout_events


def _cycle_report(
    cycle_index: int,
    rows: list[tuple[int, dict[str, Any]]],
    *,
    transition_events: list[int],
    timeout_events: list[int],
    grid_shape: Sequence[Any],
    row_start: int,
    row_end: int,
    col_start: int,
    col_end: int,
    target_depth_m: float,
    rollout_summary: Mapping[str, Any],
    profile: str,
) -> dict[str, Any]:
    row_indices = [row_index for row_index, _ in rows]
    skill_counts = Counter(str(row.get("skill_name", "")) for _, row in rows)
    residual_summary = _cycle_residual_summary(
        rows,
        grid_shape=grid_shape,
        row_start=row_start,
        row_end=row_end,
        col_start=col_start,
        col_end=col_end,
        target_depth_m=target_depth_m,
        profile=profile,
    )
    payload_summary = _payload_summary(cycle_index, rows, rollout_summary)
    return {
        "cycle_index": int(cycle_index),
        "row_start_index": min(row_indices),
        "row_end_index": max(row_indices),
        "row_count": len(rows),
        "skill_counts": {key: int(value) for key, value in sorted(skill_counts.items())},
        "dump_start_count": _mask_count(rows, "dump_start_mask"),
        "dump_end_count": _mask_count(rows, "dump_end_mask"),
        "residual_summary": residual_summary,
        "payload_summary": payload_summary,
        "execution_quality_summary": _execution_quality_summary(
            cycle_index,
            rollout_summary,
        ),
        "handoff_summary": _handoff_summary(
            rows,
            transition_events=transition_events,
            timeout_events=timeout_events,
        ),
    }


def _cycle_residual_summary(
    rows: list[tuple[int, dict[str, Any]]],
    *,
    grid_shape: Sequence[Any],
    row_start: int,
    row_end: int,
    col_start: int,
    col_end: int,
    target_depth_m: float,
    profile: str,
) -> dict[str, Any]:
    snapshots = [
        snapshot
        for row_index, row in rows
        if (snapshot := _grid_snapshot_from_row(row_index, row)) is not None
    ]
    if not snapshots:
        return _empty_residual_summary("missing_snapshot")
    start = snapshots[0]
    end = snapshots[-1]
    start_metrics = _target_metrics_for_snapshot(
        start,
        grid_shape=grid_shape,
        row_start=row_start,
        row_end=row_end,
        col_start=col_start,
        col_end=col_end,
        target_depth_m=target_depth_m,
        profile=profile,
    )
    end_metrics = _target_metrics_for_snapshot(
        end,
        grid_shape=grid_shape,
        row_start=row_start,
        row_end=row_end,
        col_start=col_start,
        col_end=col_end,
        target_depth_m=target_depth_m,
        profile=profile,
    )
    if start_metrics.get("status") != "present" or end_metrics.get("status") != "present":
        return _empty_residual_summary(str(end_metrics.get("status") or start_metrics.get("status")))
    return {
        "status": "present",
        "start_row_index": int(start["row_index"]),
        "end_row_index": int(end["row_index"]),
        "removed_depth_grid_start_m": list(start_metrics["removed_depth_grid_m"]),
        "removed_depth_grid_end_m": list(end_metrics["removed_depth_grid_m"]),
        "target_depth_grid_m": list(end_metrics["target_depth_grid_m"]),
        "target_region_mask": list(end_metrics["target_region_mask"]),
        "valid_mask": list(end_metrics["valid_mask"]),
        **_metric_pair_delta(
            start_metrics,
            end_metrics,
            "target_positive_residual_depth_sum_m",
        ),
        **_metric_pair_delta(start_metrics, end_metrics, "target_overdig_depth_sum_m"),
        **_metric_pair_delta(
            start_metrics,
            end_metrics,
            "outside_target_removed_depth_sum_m",
        ),
        **_metric_pair_delta(
            start_metrics,
            end_metrics,
            "target_removed_completion_ratio",
        ),
    }


def _target_metrics_for_snapshot(
    snapshot: Mapping[str, Any],
    *,
    grid_shape: Sequence[Any],
    row_start: int,
    row_end: int,
    col_start: int,
    col_end: int,
    target_depth_m: float,
    profile: str,
) -> dict[str, Any]:
    target_grid = build_rectangular_target_grid(
        grid_shape=grid_shape,
        valid_mask=snapshot["valid_mask"],
        row_start=row_start,
        row_end=row_end,
        col_start=col_start,
        col_end=col_end,
        target_depth_m=target_depth_m,
        profile=profile,
    )
    if target_grid["status"] != "present":
        return {"status": target_grid["status"]}
    metrics = build_target_residual_metrics(
        removed_depth_grid_m=snapshot["removed_depth_grid_m"],
        target_depth_grid_m=target_grid["target_depth_grid_m"],
        target_region_mask=target_grid["target_region_mask"],
        valid_mask=snapshot["valid_mask"],
        grid_shape=grid_shape,
    )
    if metrics["status"] != "present":
        return metrics
    return {
        **metrics,
        "removed_depth_grid_m": list(snapshot["removed_depth_grid_m"]),
        "target_depth_grid_m": _metric_sequence(target_grid["target_depth_grid_m"]),
        "target_region_mask": _metric_sequence(target_grid["target_region_mask"]),
        "valid_mask": _metric_sequence(snapshot["valid_mask"]),
    }


def _payload_summary(
    cycle_index: int,
    rows: list[tuple[int, dict[str, Any]]],
    rollout_summary: Mapping[str, Any],
) -> dict[str, Any]:
    prefix = f"cycle{cycle_index + 1}_"
    payload_peak = _summary_float(rollout_summary, prefix + "bucket_mass_out_kg")
    if payload_peak is None:
        payload_peak = _max_row_float(rows, ("dig_best_mass_kg", "coverage_last_payload_gain_kg"))
    deposit_delta = _summary_float(
        rollout_summary,
        prefix + "target_deposit_final_delta_kg",
    )
    if deposit_delta is None:
        deposit_delta = _max_row_float(rows, ("coverage_last_effective_deposit_delta_kg",))
    deposited_fraction = _summary_float(rollout_summary, prefix + "deposited_fraction")
    if deposited_fraction is None and payload_peak and deposit_delta is not None:
        deposited_fraction = _metric_float(deposit_delta / payload_peak)
    return {
        "payload_peak_kg": payload_peak,
        "effective_deposit_delta_kg": deposit_delta,
        "deposited_fraction": deposited_fraction,
    }


def _execution_quality_summary(
    cycle_index: int,
    rollout_summary: Mapping[str, Any],
) -> dict[str, Any]:
    prefix = f"cycle{cycle_index + 1}_"
    return {
        "success": _summary_int(rollout_summary, prefix + "success"),
        "entry_error_m": _summary_float(rollout_summary, prefix + "entry_error_m"),
        "entry_planned_x_m": _summary_float(
            rollout_summary,
            prefix + "entry_planned_x_m",
        ),
        "entry_planned_z_m": _summary_float(
            rollout_summary,
            prefix + "entry_planned_z_m",
        ),
        "entry_actual_x_m": _summary_float(
            rollout_summary,
            prefix + "entry_actual_x_m",
        ),
        "entry_actual_z_m": _summary_float(
            rollout_summary,
            prefix + "entry_actual_z_m",
        ),
        "exit_error_m": _summary_float(rollout_summary, prefix + "exit_error_m"),
        "exit_abs_overshoot_m": _summary_float(
            rollout_summary,
            prefix + "exit_abs_overshoot_m",
        ),
        "exit_signed_error_m": _summary_float(
            rollout_summary,
            prefix + "exit_signed_error_m",
        ),
        "exit_planned_x_m": _summary_float(
            rollout_summary,
            prefix + "exit_planned_x_m",
        ),
        "exit_planned_z_m": _summary_float(
            rollout_summary,
            prefix + "exit_planned_z_m",
        ),
        "exit_actual_x_m": _summary_float(
            rollout_summary,
            prefix + "exit_actual_x_m",
        ),
        "exit_actual_z_m": _summary_float(
            rollout_summary,
            prefix + "exit_actual_z_m",
        ),
        "depth_target_m": _summary_float(
            rollout_summary,
            prefix + "depth_target_m",
        ),
        "depth_peak_m": _summary_float(
            rollout_summary,
            prefix + "depth_peak_m",
        ),
        "depth_error_m": _summary_float(
            rollout_summary,
            prefix + "depth_error_m",
        ),
        "depth_abs_error_m": _summary_float(
            rollout_summary,
            prefix + "depth_abs_error_m",
        ),
    }


def _handoff_summary(
    rows: list[tuple[int, dict[str, Any]]],
    *,
    transition_events: list[int],
    timeout_events: list[int],
) -> dict[str, Any]:
    return_rows = [(row_index, row) for row_index, row in rows if row.get("skill_name") == "return"]
    errors = [
        value
        for _, row in return_rows
        if (value := _finite_float(row.get("return_to_dig_start_envelope_error")))
        is not None
    ]
    return {
        "return_row_count": len(return_rows),
        "entry_close_return_row_count": sum(
            1 for _, row in return_rows if bool(row.get("return_to_dig_entry_close"))
        ),
        "envelope_ready_return_row_count": sum(
            1
            for _, row in return_rows
            if bool(row.get("return_to_dig_start_envelope_ready"))
        ),
        "completed_transition_count": len(transition_events),
        "completed_transition_row_indices": [int(index) for index in transition_events],
        "transition_timeout_count": len(timeout_events),
        "transition_timeout_row_indices": [int(index) for index in timeout_events],
        "max_return_start_envelope_error": _metric_float(max(errors)) if errors else None,
        "failed_envelope_check_names": _failed_envelope_check_names(return_rows),
    }


def _summary(status: str, cycles: list[dict[str, Any]]) -> dict[str, Any]:
    if not cycles:
        return {
            "status": status,
            "cycle_count": 0,
            "completed_cycle_count": 0,
            "target_positive_residual_depth_sum_start_m": None,
            "target_positive_residual_depth_sum_end_m": None,
            "target_positive_residual_depth_sum_delta_m": None,
            "target_overdig_depth_sum_start_m": None,
            "target_overdig_depth_sum_end_m": None,
            "target_overdig_depth_sum_delta_m": None,
            "outside_target_removed_depth_sum_start_m": None,
            "outside_target_removed_depth_sum_end_m": None,
            "outside_target_removed_depth_sum_delta_m": None,
            "payload_peak_kg_mean": None,
            "effective_deposit_delta_kg_mean": None,
            "deposited_fraction_mean": None,
            "deposited_fraction_min": None,
            "completed_transition_count": 0,
            "transition_timeout_count": 0,
        }
    first_residual = cycles[0]["residual_summary"]
    last_residual = cycles[-1]["residual_summary"]
    return {
        "status": status,
        "cycle_count": len(cycles),
        "completed_cycle_count": sum(1 for cycle in cycles if cycle["dump_end_count"] > 0),
        "target_positive_residual_depth_sum_start_m": first_residual.get(
            "target_positive_residual_depth_sum_start_m"
        ),
        "target_positive_residual_depth_sum_end_m": last_residual.get(
            "target_positive_residual_depth_sum_end_m"
        ),
        "target_positive_residual_depth_sum_delta_m": _delta_from_values(
            first_residual.get("target_positive_residual_depth_sum_start_m"),
            last_residual.get("target_positive_residual_depth_sum_end_m"),
        ),
        "target_overdig_depth_sum_start_m": first_residual.get(
            "target_overdig_depth_sum_start_m"
        ),
        "target_overdig_depth_sum_end_m": last_residual.get(
            "target_overdig_depth_sum_end_m"
        ),
        "target_overdig_depth_sum_delta_m": _delta_from_values(
            first_residual.get("target_overdig_depth_sum_start_m"),
            last_residual.get("target_overdig_depth_sum_end_m"),
        ),
        "outside_target_removed_depth_sum_start_m": first_residual.get(
            "outside_target_removed_depth_sum_start_m"
        ),
        "outside_target_removed_depth_sum_end_m": last_residual.get(
            "outside_target_removed_depth_sum_end_m"
        ),
        "outside_target_removed_depth_sum_delta_m": _delta_from_values(
            first_residual.get("outside_target_removed_depth_sum_start_m"),
            last_residual.get("outside_target_removed_depth_sum_end_m"),
        ),
        "payload_peak_kg_mean": _mean(
            cycle["payload_summary"].get("payload_peak_kg") for cycle in cycles
        ),
        "effective_deposit_delta_kg_mean": _mean(
            cycle["payload_summary"].get("effective_deposit_delta_kg") for cycle in cycles
        ),
        "deposited_fraction_mean": _mean(
            cycle["payload_summary"].get("deposited_fraction") for cycle in cycles
        ),
        "deposited_fraction_min": _minimum(
            cycle["payload_summary"].get("deposited_fraction") for cycle in cycles
        ),
        "completed_transition_count": sum(
            cycle["handoff_summary"]["completed_transition_count"] for cycle in cycles
        ),
        "transition_timeout_count": sum(
            cycle["handoff_summary"]["transition_timeout_count"] for cycle in cycles
        ),
    }


def _metric_pair_delta(
    start_metrics: Mapping[str, Any],
    end_metrics: Mapping[str, Any],
    field: str,
) -> dict[str, float | None]:
    start_value = _finite_float(start_metrics.get(field))
    end_value = _finite_float(end_metrics.get(field))
    base = field[:-2] if field.endswith("_m") else field
    suffix = "_m" if field.endswith("_m") else ""
    return {
        f"{base}_start{suffix}": start_value,
        f"{base}_end{suffix}": end_value,
        f"{base}_delta{suffix}": _delta_from_values(
            start_value,
            end_value,
        ),
    }


def _delta_from_values(start_value: Any, end_value: Any) -> float | None:
    start = _finite_float(start_value)
    end = _finite_float(end_value)
    if start is None or end is None:
        return None
    return _metric_float(end - start)


def _empty_residual_summary(status: str) -> dict[str, Any]:
    return {
        "status": status,
        "start_row_index": None,
        "end_row_index": None,
        "removed_depth_grid_start_m": None,
        "removed_depth_grid_end_m": None,
        "target_depth_grid_m": None,
        "target_region_mask": None,
        "valid_mask": None,
        "target_positive_residual_depth_sum_start_m": None,
        "target_positive_residual_depth_sum_end_m": None,
        "target_positive_residual_depth_sum_delta_m": None,
        "target_overdig_depth_sum_start_m": None,
        "target_overdig_depth_sum_end_m": None,
        "target_overdig_depth_sum_delta_m": None,
        "outside_target_removed_depth_sum_start_m": None,
        "outside_target_removed_depth_sum_end_m": None,
        "outside_target_removed_depth_sum_delta_m": None,
        "target_removed_completion_ratio_start": None,
        "target_removed_completion_ratio_end": None,
        "target_removed_completion_ratio_delta": None,
    }


def _grid_snapshot_from_row(row_index: int, row: Mapping[str, Any]) -> dict[str, Any] | None:
    env_state = row.get("env_state")
    if not isinstance(env_state, (list, tuple)):
        return None
    removed_depth = _float_slice(
        env_state,
        ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
        GRID_CELL_COUNT,
    )
    valid_mask = _float_slice(
        env_state,
        ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
        GRID_CELL_COUNT,
    )
    if removed_depth is None or valid_mask is None:
        return None
    return {
        "row_index": int(row_index),
        "long_count": _sequence_float(env_state, ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX),
        "short_count": _sequence_float(env_state, ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX),
        "removed_depth_grid_m": removed_depth,
        "valid_mask": valid_mask,
    }


def _float_slice(
    values: list[Any] | tuple[Any, ...],
    start: int,
    count: int,
) -> list[float] | None:
    end = start + count
    if len(values) < end:
        return None
    parsed = [_sequence_float(values, index) for index in range(start, end)]
    if any(value is None for value in parsed):
        return None
    return [_metric_float(float(value)) for value in parsed if value is not None]


def _sequence_float(values: list[Any] | tuple[Any, ...], index: int) -> float | None:
    if len(values) <= index:
        return None
    return _finite_float(values[index])


def _failed_envelope_check_names(
    return_rows: list[tuple[int, dict[str, Any]]],
) -> list[str]:
    failed = set()
    for _, row in return_rows:
        checks = row.get("return_to_dig_start_envelope_checks")
        if not isinstance(checks, Mapping):
            continue
        for name, check in checks.items():
            if isinstance(check, Mapping) and check.get("ok") is False:
                failed.add(str(name))
    return sorted(failed)


def _target_spec(
    *,
    grid_shape: Sequence[Any] | None,
    row_start: int | None,
    row_end: int | None,
    col_start: int | None,
    col_end: int | None,
    target_depth_m: float | None,
    official_target_id: str | None,
    profile: str,
) -> dict[str, Any]:
    if official_target_id:
        target = get_official_terrain_residual_target_spec(official_target_id)
        return {
            **target,
            "status": "present",
        }
    if (
        grid_shape is None
        or row_start is None
        or row_end is None
        or col_start is None
        or col_end is None
        or target_depth_m is None
    ):
        return {
            "status": "invalid_explicit_target_spec",
            "validation_errors": [
                "explicit target spec requires grid_shape, row_start, row_end, col_start, col_end, and target_depth_m",
            ],
        }
    return {
        "status": "present",
        "grid_shape": [int(grid_shape[0]), int(grid_shape[1])]
        if len(grid_shape) == 2
        else None,
        "row_start": int(row_start),
        "row_end": int(row_end),
        "col_start": int(col_start),
        "col_end": int(col_end),
        "target_depth_m": _metric_float(float(target_depth_m)),
        "profile": str(profile),
    }


def _official_quality_summary(
    summary: Mapping[str, Any],
    *,
    cycles: list[dict[str, Any]],
    rollout_summary: Mapping[str, Any],
) -> dict[str, Any]:
    completed_dumps = _summary_int(
        rollout_summary,
        "target_cycle_completed_dump_count",
    )
    if completed_dumps is None:
        completed_dumps = _summary_int(summary, "completed_cycle_count") or 0
    gate_success = _summary_int(rollout_summary, "target_cycle_gate_success")
    if gate_success is None:
        gate_success = 1 if completed_dumps >= 2 else 0
    return {
        "target_cycle_gate_success": int(gate_success),
        "target_cycle_completed_dump_count": int(completed_dumps),
        "transition_timeout_count": int(
            _summary_int(summary, "transition_timeout_count") or 0
        ),
        "latest_target_positive_residual_depth_sum_m": summary.get(
            "target_positive_residual_depth_sum_end_m"
        ),
        "latest_target_overdig_depth_sum_m": summary.get(
            "target_overdig_depth_sum_end_m"
        ),
        "latest_outside_target_removed_depth_sum_m": summary.get(
            "outside_target_removed_depth_sum_end_m"
        ),
        "deposited_fraction_mean": summary.get("deposited_fraction_mean"),
        "depth_abs_error_m_mean": _mean(
            cycle["execution_quality_summary"].get("depth_abs_error_m")
            for cycle in cycles
        ),
    }


def _official_pass_fail_not_evaluated(reason: str) -> dict[str, Any]:
    return {
        "schema": "terrain_residual_pass_fail_v1",
        "source": "official_a_baseline_anchored_terrain_quality_pass_fail",
        "status": "not_evaluated",
        "reason": str(reason),
        "pass": False,
        "failed_checks": [],
        "validation_errors": [],
    }


def _limitations(official_pass_fail_status: str) -> dict[str, Any]:
    return {
        "diagnostic_only": True,
        "bounded_smoke_only": True,
        "official_pass_fail_status": official_pass_fail_status,
        "production_readiness_status": "not_claimed",
        "terrain_provenance_status": "compact_removed_depth_grid_only",
    }


def _mask_count(rows: list[tuple[int, dict[str, Any]]], field: str) -> int:
    return sum(1 for _, row in rows if _truthy_number(row.get(field)))


def _max_row_float(
    rows: list[tuple[int, dict[str, Any]]],
    fields: tuple[str, ...],
) -> float | None:
    values = [
        value
        for _, row in rows
        for field in fields
        if (value := _finite_float(row.get(field))) is not None
    ]
    return _metric_float(max(values)) if values else None


def _mean(values: Any) -> float | None:
    parsed = [_finite_float(value) for value in values]
    finite = [value for value in parsed if value is not None]
    if not finite:
        return None
    return _metric_float(sum(finite) / len(finite))


def _minimum(values: Any) -> float | None:
    parsed = [_finite_float(value) for value in values]
    finite = [value for value in parsed if value is not None]
    if not finite:
        return None
    return _metric_float(min(finite))


def _summary_float(summary: Mapping[str, Any], field: str) -> float | None:
    return _finite_float(summary.get(field))


def _summary_int(summary: Mapping[str, Any], field: str) -> int | None:
    value = _finite_float(summary.get(field))
    if value is None:
        return None
    return int(value)


def _int_or_none(value: Any) -> int | None:
    parsed = _finite_float(value)
    if parsed is None:
        return None
    return int(parsed)


def _truthy_number(value: Any) -> bool:
    parsed = _finite_float(value)
    return parsed is not None and parsed != 0.0


def _finite_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _metric_float(value: float) -> float:
    rounded = round(float(value), 12)
    return 0.0 if rounded == -0.0 else rounded


def _metric_sequence(values: Any) -> list[float]:
    return [_metric_float(float(value)) for value in values]


__all__ = [
    "build_terrain_cycle_quality_report",
    "write_terrain_cycle_quality_report",
]
