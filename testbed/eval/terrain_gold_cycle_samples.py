"""Official gold cycle sample JSONL records for terrain-residual calibration.

Replay recorder inputs are Unity/HDF5 env_state rows, so numeric parsing accepts
standard Python numeric values and numpy scalar numeric values.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from numbers import Real
from pathlib import Path
from typing import Any

from testbed.data.schema import (
    ENV_STATE_DEPOSITED_MASS_IN_DUMP_AREA_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_DIG_AREA_BASELINE_DEPTH_START_IDX,
    ENV_STATE_DIG_AREA_CELL_AREA_IDX,
    ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
    ENV_STATE_DIG_AREA_GRID_ORIGIN_WORLD_START_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
    ENV_STATE_DIG_AREA_SURFACE_VALID_FRACTION_START_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
)
from testbed.eval.terrain_grid_volume import (
    DIRECT_VOLUME_STATUS,
    VOLUME_LABEL_STATUS,
    compute_grid_volume_change,
)
from testbed.eval.terrain_residual_contract import get_replay_snapshot_target_spec
from testbed.eval.terrain_target_grid import build_rectangular_target_grid
from testbed.eval.terrain_target_metrics import build_target_residual_metrics

SCHEMA = "terrain_gold_cycle_samples_v1"
RECORD_SCHEMA = "terrain_gold_cycle_sample_v1"
SOURCE = "official_gold_cycle_sample_builder"
REQUIRED_PAYLOAD_LABEL = "payload_mass_kg"
GRID_CELL_COUNT = 6
GRID_GEOMETRY_FIELD_COUNT = 13


class GoldCycleSampleReplayRecorder:
    """Collect one official gold cycle sample per replay dump-end event."""

    def __init__(
        self,
        *,
        target_id: str,
        episode_id: str | None = None,
        rollout_id: str | None = None,
        low_payload_mass_threshold_kg: float,
    ) -> None:
        self._target = get_replay_snapshot_target_spec(target_id)
        self._episode_id = _optional_text(episode_id)
        self._rollout_id = _optional_text(rollout_id)
        self._low_payload_mass_threshold_kg = float(low_payload_mass_threshold_kg)
        self._records: list[dict[str, Any]] = []
        self._cycle_start: dict[str, Any] | None = None
        self._cycle_start_deposit_mass_kg = 0.0
        self._payload_peak_kg = 0.0
        self._observation_index = -1
        self._cycle_start_observation_index = 0

    def observe(self, env_state: Any, *, dump_end: bool = False) -> None:
        self._observation_index += 1
        snapshot = _snapshot_from_env_state(env_state, target=self._target)
        if snapshot is None:
            return
        if self._cycle_start is None:
            self._cycle_start = snapshot
            self._cycle_start_observation_index = self._observation_index
            self._cycle_start_deposit_mass_kg = snapshot["deposit_mass_kg"]
            self._payload_peak_kg = 0.0
        self._payload_peak_kg = max(self._payload_peak_kg, snapshot["bucket_mass_kg"])
        if dump_end:
            self._records.append(
                _record_from_snapshots(
                    start=self._cycle_start,
                    end=snapshot,
                    target_id=str(self._target["target_id"]),
                    branch_name="replay",
                    cycle_index=len(self._records),
                    episode_id=self._episode_id,
                    rollout_id=self._rollout_id,
                    payload_mass_kg=self._payload_peak_kg,
                    effective_deposit_mass_kg=(
                        snapshot["deposit_mass_kg"]
                        - self._cycle_start_deposit_mass_kg
                    ),
                    low_payload_mass_threshold_kg=(
                        self._low_payload_mass_threshold_kg
                    ),
                    cycle_start_observation_index=self._cycle_start_observation_index,
                    cycle_end_observation_index=self._observation_index,
                )
            )
            self._cycle_start = snapshot
            self._cycle_start_deposit_mass_kg = snapshot["deposit_mass_kg"]
            self._payload_peak_kg = 0.0
            self._cycle_start_observation_index = self._observation_index

    def build_result(self) -> dict[str, Any]:
        if self._episode_id is None and self._rollout_id is None:
            return _result(
                status="missing_split_key",
                records=[],
                validation_errors=[
                    "at least one split key is required: episode_id or rollout_id",
                ],
            )
        return _result(
            status="present" if self._records else "no_completed_cycles",
            records=list(self._records),
            validation_errors=[],
        )


def build_gold_cycle_sample_records(
    cycle_quality_report: Mapping[str, Any],
    *,
    episode_id: str | None = None,
    rollout_id: str | None = None,
    low_payload_mass_threshold_kg: float,
) -> dict[str, Any]:
    """Build one official calibration sample record per report cycle."""

    normalized_episode_id = _optional_text(episode_id)
    normalized_rollout_id = _optional_text(rollout_id)
    if normalized_episode_id is None and normalized_rollout_id is None:
        return _result(
            status="missing_split_key",
            records=[],
            validation_errors=[
                "at least one split key is required: episode_id or rollout_id",
            ],
        )

    threshold = _finite_float(low_payload_mass_threshold_kg)
    if threshold is None:
        return _result(
            status="invalid_low_payload_threshold",
            records=[],
            validation_errors=[
                "low_payload_mass_threshold_kg must be finite",
            ],
        )

    cycles = cycle_quality_report.get("cycles")
    if not isinstance(cycles, list):
        return _result(
            status="invalid_cycle_quality_report",
            records=[],
            validation_errors=["cycle_quality_report must include cycles list"],
        )

    records: list[dict[str, Any]] = []
    validation_errors: list[str] = []
    for index, cycle in enumerate(cycles):
        if not isinstance(cycle, Mapping):
            validation_errors.append(f"cycles[{index}] must be a mapping")
            continue
        record, errors = _sample_record(
            cycle,
            report=cycle_quality_report,
            episode_id=normalized_episode_id,
            rollout_id=normalized_rollout_id,
            low_payload_mass_threshold_kg=threshold,
        )
        if errors:
            validation_errors.extend(f"cycles[{index}].{error}" for error in errors)
            continue
        records.append(record)

    return _result(
        status="present" if not validation_errors else "invalid_cycle_records",
        records=records if not validation_errors else [],
        validation_errors=validation_errors,
    )


def write_gold_cycle_sample_jsonl(
    cycle_quality_report: Mapping[str, Any],
    *,
    output_path: Any,
    episode_id: str | None = None,
    rollout_id: str | None = None,
    low_payload_mass_threshold_kg: float,
) -> dict[str, Any]:
    """Write official gold cycle sample records as no-overwrite JSONL."""

    path = Path(output_path)
    if path.exists():
        return {
            **_result(
                status="output_path_already_exists",
                records=[],
                validation_errors=["output_path must not already exist before writing"],
            ),
            "output_path": str(path),
        }

    result = build_gold_cycle_sample_records(
        cycle_quality_report,
        episode_id=episode_id,
        rollout_id=rollout_id,
        low_payload_mass_threshold_kg=low_payload_mass_threshold_kg,
    )
    result = {**result, "output_path": str(path)}
    if result["status"] != "present":
        return result

    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(record, sort_keys=True, allow_nan=False)
        for record in result["records"]
    ]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return result


def append_gold_cycle_sample_records(
    *,
    output_path: Any,
    records: list[dict[str, Any]],
) -> None:
    """Append records to a JSONL file after the caller has checked no-overwrite."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as sink:
        for record in records:
            sink.write(json.dumps(record, sort_keys=True, allow_nan=False) + "\n")


def _result(
    *,
    status: str,
    records: list[dict[str, Any]],
    validation_errors: list[str],
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "source": SOURCE,
        "status": status,
        "record_count": len(records),
        "records": records,
        "required_payload_label": REQUIRED_PAYLOAD_LABEL,
        "volume_label_status": VOLUME_LABEL_STATUS,
        "validation_errors": validation_errors,
    }


def _sample_record(
    cycle: Mapping[str, Any],
    *,
    report: Mapping[str, Any],
    episode_id: str | None,
    rollout_id: str | None,
    low_payload_mass_threshold_kg: float,
) -> tuple[dict[str, Any], list[str]]:
    residual = _mapping(cycle.get("residual_summary"))
    payload = _mapping(cycle.get("payload_summary"))
    execution = _mapping(cycle.get("execution_quality_summary"))
    handoff = _mapping(cycle.get("handoff_summary"))
    target_spec = _mapping(report.get("target_spec"))
    required_values = {
        "cycle_index": cycle.get("cycle_index"),
        "target_positive_residual_depth_sum_start_m": residual.get(
            "target_positive_residual_depth_sum_start_m"
        ),
        "target_positive_residual_depth_sum_end_m": residual.get(
            "target_positive_residual_depth_sum_end_m"
        ),
        "target_positive_residual_depth_sum_delta_m": residual.get(
            "target_positive_residual_depth_sum_delta_m"
        ),
        "target_removed_completion_ratio_start": residual.get(
            "target_removed_completion_ratio_start"
        ),
        "target_removed_completion_ratio_end": residual.get(
            "target_removed_completion_ratio_end"
        ),
        "target_removed_completion_ratio_delta": residual.get(
            "target_removed_completion_ratio_delta"
        ),
        "target_overdig_depth_sum_m": residual.get("target_overdig_depth_sum_end_m"),
        "outside_target_removed_depth_sum_m": residual.get(
            "outside_target_removed_depth_sum_end_m"
        ),
        "payload_mass_kg": payload.get("payload_peak_kg"),
        "effective_deposit_mass_kg": payload.get("effective_deposit_delta_kg"),
        "deposited_fraction": payload.get("deposited_fraction"),
        "depth_target_m": execution.get("depth_target_m"),
        "depth_peak_m": execution.get("depth_peak_m"),
        "depth_error_m": execution.get("depth_error_m"),
        "depth_abs_error_m": execution.get("depth_abs_error_m"),
        "entry_planned_x_m": execution.get("entry_planned_x_m"),
        "entry_planned_z_m": execution.get("entry_planned_z_m"),
        "entry_actual_x_m": execution.get("entry_actual_x_m"),
        "entry_actual_z_m": execution.get("entry_actual_z_m"),
        "entry_error_m": execution.get("entry_error_m"),
        "exit_planned_x_m": execution.get("exit_planned_x_m"),
        "exit_planned_z_m": execution.get("exit_planned_z_m"),
        "exit_actual_x_m": execution.get("exit_actual_x_m"),
        "exit_actual_z_m": execution.get("exit_actual_z_m"),
        "exit_error_m": execution.get("exit_error_m"),
        "exit_abs_overshoot_m": execution.get("exit_abs_overshoot_m"),
        "completed_transition_count": handoff.get("completed_transition_count"),
        "transition_timeout_count": handoff.get("transition_timeout_count"),
        "cell_area_m2": residual.get("cell_area_m2"),
    }
    parsed, errors = _parse_required_values(required_values)
    required_sequences = {
        "removed_depth_grid_start_m": residual.get("removed_depth_grid_start_m"),
        "removed_depth_grid_end_m": residual.get("removed_depth_grid_end_m"),
        "target_depth_grid_m": residual.get("target_depth_grid_m"),
        "target_region_mask": residual.get("target_region_mask"),
        "valid_mask": residual.get("valid_mask"),
    }
    parsed_sequences, sequence_errors = _parse_required_sequences(required_sequences)
    errors.extend(sequence_errors)
    if errors:
        return {}, errors

    target_id = _optional_text(target_spec.get("target_id")) or ""
    branch_name = _optional_text(report.get("branch_name")) or ""
    overdig_event = float(parsed["target_overdig_depth_sum_m"]) > 0.0
    low_payload_event = (
        float(parsed["payload_mass_kg"]) < low_payload_mass_threshold_kg
    )
    volume = _normalized_volume(
        compute_grid_volume_change(
            start_removed_depth_m=parsed_sequences["removed_depth_grid_start_m"],
            end_removed_depth_m=parsed_sequences["removed_depth_grid_end_m"],
            cell_area_m2=float(parsed["cell_area_m2"]),
            valid_mask=parsed_sequences["valid_mask"],
        )
    )
    record = {
        "schema": RECORD_SCHEMA,
        "source": SOURCE,
        "episode_id": episode_id,
        "rollout_id": rollout_id,
        "cycle_index": int(parsed["cycle_index"]),
        "branch_name": branch_name,
        "target_id": target_id,
        "removed_depth_grid_start_m": parsed_sequences["removed_depth_grid_start_m"],
        "removed_depth_grid_end_m": parsed_sequences["removed_depth_grid_end_m"],
        "target_depth_grid_m": parsed_sequences["target_depth_grid_m"],
        "target_region_mask": parsed_sequences["target_region_mask"],
        "valid_mask": parsed_sequences["valid_mask"],
        "target_positive_residual_depth_sum_start_m": parsed[
            "target_positive_residual_depth_sum_start_m"
        ],
        "target_positive_residual_depth_sum_end_m": parsed[
            "target_positive_residual_depth_sum_end_m"
        ],
        "target_positive_residual_depth_sum_delta_m": parsed[
            "target_positive_residual_depth_sum_delta_m"
        ],
        "target_removed_completion_ratio_start": parsed[
            "target_removed_completion_ratio_start"
        ],
        "target_removed_completion_ratio_end": parsed[
            "target_removed_completion_ratio_end"
        ],
        "target_removed_completion_ratio_delta": parsed[
            "target_removed_completion_ratio_delta"
        ],
        "target_overdig_depth_sum_m": parsed["target_overdig_depth_sum_m"],
        "outside_target_removed_depth_sum_m": parsed[
            "outside_target_removed_depth_sum_m"
        ],
        "payload_mass_kg": parsed["payload_mass_kg"],
        "effective_deposit_mass_kg": parsed["effective_deposit_mass_kg"],
        "deposited_fraction": parsed["deposited_fraction"],
        "depth_target_m": parsed["depth_target_m"],
        "depth_peak_m": parsed["depth_peak_m"],
        "depth_error_m": parsed["depth_error_m"],
        "depth_abs_error_m": parsed["depth_abs_error_m"],
        "entry_planned_x_m": parsed["entry_planned_x_m"],
        "entry_planned_z_m": parsed["entry_planned_z_m"],
        "entry_actual_x_m": parsed["entry_actual_x_m"],
        "entry_actual_z_m": parsed["entry_actual_z_m"],
        "entry_error_m": parsed["entry_error_m"],
        "exit_planned_x_m": parsed["exit_planned_x_m"],
        "exit_planned_z_m": parsed["exit_planned_z_m"],
        "exit_actual_x_m": parsed["exit_actual_x_m"],
        "exit_actual_z_m": parsed["exit_actual_z_m"],
        "exit_error_m": parsed["exit_error_m"],
        "exit_abs_overshoot_m": parsed["exit_abs_overshoot_m"],
        "completed_transition_count": int(parsed["completed_transition_count"]),
        "transition_timeout_count": int(parsed["transition_timeout_count"]),
        "success": bool(execution.get("success")),
        "overdig_event": overdig_event,
        "low_payload_event": low_payload_event,
        **volume,
    }
    if episode_id is None:
        record.pop("episode_id")
    if rollout_id is None:
        record.pop("rollout_id")
    return record, []


def _snapshot_from_env_state(
    env_state: Any,
    *,
    target: Mapping[str, Any],
) -> dict[str, Any] | None:
    if not _indexable_sequence(env_state):
        return None
    removed_depth = _env_slice(
        env_state,
        ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
        GRID_CELL_COUNT,
    )
    valid_mask = _env_slice(
        env_state,
        ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
        GRID_CELL_COUNT,
    )
    if removed_depth is None or valid_mask is None:
        return None
    cell_area_m2 = _env_value(env_state, ENV_STATE_DIG_AREA_CELL_AREA_IDX)
    surface_valid_fraction = _env_slice(
        env_state,
        ENV_STATE_DIG_AREA_SURFACE_VALID_FRACTION_START_IDX,
        GRID_CELL_COUNT,
    )
    grid_geometry = _env_slice(
        env_state,
        ENV_STATE_DIG_AREA_GRID_ORIGIN_WORLD_START_IDX,
        GRID_GEOMETRY_FIELD_COUNT,
    )
    baseline_depth = _env_slice(
        env_state,
        ENV_STATE_DIG_AREA_BASELINE_DEPTH_START_IDX,
        GRID_CELL_COUNT,
    )
    if (
        cell_area_m2 <= 0.0
        or surface_valid_fraction is None
        or grid_geometry is None
        or baseline_depth is None
    ):
        return None
    target_grid = build_rectangular_target_grid(
        grid_shape=target["grid_shape"],
        valid_mask=valid_mask,
        row_start=int(target["row_start"]),
        row_end=int(target["row_end"]),
        col_start=int(target["col_start"]),
        col_end=int(target["col_end"]),
        target_depth_m=float(target["target_depth_m"]),
        profile=str(target["profile"]),
    )
    if target_grid["status"] != "present":
        return None
    metrics = build_target_residual_metrics(
        removed_depth_grid_m=removed_depth,
        target_depth_grid_m=target_grid["target_depth_grid_m"],
        target_region_mask=target_grid["target_region_mask"],
        valid_mask=valid_mask,
        grid_shape=target["grid_shape"],
    )
    if metrics["status"] != "present":
        return None
    return {
        "metrics": metrics,
        "removed_depth_grid_m": removed_depth,
        "target_depth_grid_m": target_grid["target_depth_grid_m"],
        "target_region_mask": target_grid["target_region_mask"],
        "valid_mask": valid_mask,
        "surface_valid_fraction": surface_valid_fraction,
        "cell_area_m2": cell_area_m2,
        "grid_geometry": grid_geometry,
        "baseline_depth_grid_m": baseline_depth,
        "bucket_mass_kg": _env_value(env_state, ENV_STATE_MASS_IN_BUCKET_IDX),
        "deposit_mass_kg": _deposit_mass(env_state),
    }


def _record_from_snapshots(
    *,
    start: Mapping[str, Any],
    end: Mapping[str, Any],
    target_id: str,
    branch_name: str,
    cycle_index: int,
    episode_id: str | None,
    rollout_id: str | None,
    payload_mass_kg: float,
    effective_deposit_mass_kg: float,
    low_payload_mass_threshold_kg: float,
    cycle_start_observation_index: int | None = None,
    cycle_end_observation_index: int | None = None,
) -> dict[str, Any]:
    start_metrics = _mapping(start["metrics"])
    end_metrics = _mapping(end["metrics"])
    start_positive = _finite_float(
        start_metrics.get("target_positive_residual_depth_sum_m")
    )
    end_positive = _finite_float(
        end_metrics.get("target_positive_residual_depth_sum_m")
    )
    start_completion = _finite_float(
        start_metrics.get("target_removed_completion_ratio")
    )
    end_completion = _finite_float(
        end_metrics.get("target_removed_completion_ratio")
    )
    overdig = _finite_float(end_metrics.get("target_overdig_depth_sum_m")) or 0.0
    outside = _finite_float(end_metrics.get("outside_target_removed_depth_sum_m")) or 0.0
    volume_valid = [
        min(float(start["valid_mask"][index]), float(end["valid_mask"][index]))
        * min(
            float(start["surface_valid_fraction"][index]),
            float(end["surface_valid_fraction"][index]),
        )
        for index in range(GRID_CELL_COUNT)
    ]
    volume = _normalized_volume(
        compute_grid_volume_change(
            start_removed_depth_m=start["removed_depth_grid_m"],
            end_removed_depth_m=end["removed_depth_grid_m"],
            cell_area_m2=float(end["cell_area_m2"]),
            valid_mask=volume_valid,
        )
    )
    record = {
        "schema": RECORD_SCHEMA,
        "source": SOURCE,
        "episode_id": episode_id,
        "rollout_id": rollout_id,
        "cycle_index": int(cycle_index),
        "branch_name": branch_name,
        "target_id": target_id,
        "removed_depth_grid_start_m": list(start["removed_depth_grid_m"]),
        "removed_depth_grid_end_m": list(end["removed_depth_grid_m"]),
        "target_depth_grid_m": [
            _metric_float(float(value)) for value in end["target_depth_grid_m"]
        ],
        "target_region_mask": [
            _metric_float(float(value)) for value in end["target_region_mask"]
        ],
        "valid_mask": [_metric_float(float(value)) for value in end["valid_mask"]],
        "surface_valid_fraction_start": [
            _metric_float(float(value)) for value in start["surface_valid_fraction"]
        ],
        "surface_valid_fraction_end": [
            _metric_float(float(value)) for value in end["surface_valid_fraction"]
        ],
        "cell_area_m2": _metric_float(float(end["cell_area_m2"])),
        "grid_geometry_start": list(start["grid_geometry"]),
        "grid_geometry_end": list(end["grid_geometry"]),
        "grid_geometry_stable": _vectors_close(
            start["grid_geometry"], end["grid_geometry"]
        ),
        "baseline_depth_grid_start_m": list(start["baseline_depth_grid_m"]),
        "baseline_depth_grid_end_m": list(end["baseline_depth_grid_m"]),
        "target_positive_residual_depth_sum_start_m": start_positive,
        "target_positive_residual_depth_sum_end_m": end_positive,
        "target_positive_residual_depth_sum_delta_m": _delta(
            start_positive,
            end_positive,
        ),
        "target_removed_completion_ratio_start": start_completion,
        "target_removed_completion_ratio_end": end_completion,
        "target_removed_completion_ratio_delta": _delta(
            start_completion,
            end_completion,
        ),
        "target_overdig_depth_sum_m": overdig,
        "outside_target_removed_depth_sum_m": outside,
        "payload_mass_kg": _metric_float(payload_mass_kg),
        "effective_deposit_mass_kg": _metric_float(effective_deposit_mass_kg),
        "deposited_fraction": (
            _metric_float(effective_deposit_mass_kg / payload_mass_kg)
            if payload_mass_kg > 0.0
            else None
        ),
        "evidence_kind": "replay_derived_open_loop",
        "planner_trace_status": "missing_not_generated_by_replay",
        "planned_cut_status": "missing_not_generated_by_replay",
        "entry_exit_status": "missing_not_generated_by_replay",
        "gate_transition_status": "missing_not_generated_by_replay",
        "actual_response_status": "missing_not_generated_by_replay",
        "overdig_event": overdig > 0.0,
        "low_payload_event": payload_mass_kg < low_payload_mass_threshold_kg,
        **volume,
    }
    if cycle_start_observation_index is not None:
        record["cycle_start_observation_index"] = int(
            cycle_start_observation_index
        )
    if cycle_end_observation_index is not None:
        record["cycle_end_observation_index"] = int(cycle_end_observation_index)
    if episode_id is None:
        record.pop("episode_id")
    if rollout_id is None:
        record.pop("rollout_id")
    return record


def _env_slice(values: Any, start: int, count: int) -> list[float] | None:
    end = start + count
    if len(values) < end:
        return None
    try:
        parsed = [_finite_float(values[index]) for index in range(start, end)]
    except (IndexError, KeyError, TypeError):
        return None
    if any(value is None for value in parsed):
        return None
    return [_metric_float(value) for value in parsed if value is not None]


def _env_value(values: Any, index: int) -> float:
    if len(values) <= index:
        return 0.0
    try:
        return _finite_float(values[index]) or 0.0
    except (IndexError, KeyError, TypeError):
        return 0.0


def _deposit_mass(values: Any) -> float:
    dump_area = _env_value(values, ENV_STATE_DEPOSITED_MASS_IN_DUMP_AREA_IDX)
    if dump_area > 0.0:
        return dump_area
    return _env_value(values, ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX)


def _delta(start: float | None, end: float | None) -> float | None:
    if start is None or end is None:
        return None
    return _metric_float(end - start)


def _parse_required_values(
    values: Mapping[str, Any],
) -> tuple[dict[str, float | int], list[str]]:
    parsed: dict[str, float | int] = {}
    errors: list[str] = []
    for field, value in values.items():
        number = _finite_float(value)
        if number is None:
            errors.append(field)
            continue
        parsed[field] = int(number) if field.endswith("_count") or field == "cycle_index" else number
    return parsed, errors


def _parse_required_sequences(
    values: Mapping[str, Any],
) -> tuple[dict[str, list[float]], list[str]]:
    parsed: dict[str, list[float]] = {}
    errors: list[str] = []
    for field, value in values.items():
        if isinstance(value, (str, bytes, Mapping)) or not isinstance(value, list):
            errors.append(field)
            continue
        numbers = [_finite_float(item) for item in value]
        if not value or any(number is None for number in numbers):
            errors.append(field)
            continue
        parsed[field] = [
            _metric_float(number) for number in numbers if number is not None
        ]
    return parsed, errors


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _optional_text(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return value


def _indexable_sequence(value: Any) -> bool:
    if isinstance(value, (str, bytes, Mapping)):
        return False
    return hasattr(value, "__len__") and hasattr(value, "__getitem__")


def _finite_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def _metric_float(value: float) -> float:
    rounded = round(float(value), 12)
    return 0.0 if rounded == -0.0 else rounded


def _normalized_volume(payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, list):
            normalized[key] = [_metric_float(float(item)) for item in value]
        elif isinstance(value, Real) and not isinstance(value, bool):
            normalized[key] = _metric_float(float(value))
        else:
            normalized[key] = value
    normalized["volume_label_status"] = VOLUME_LABEL_STATUS
    normalized["direct_volume_status"] = DIRECT_VOLUME_STATUS
    return normalized


def _vectors_close(left: Any, right: Any, *, tolerance: float = 1.0e-6) -> bool:
    if len(left) != len(right):
        return False
    return all(abs(float(a) - float(b)) <= tolerance for a, b in zip(left, right))
