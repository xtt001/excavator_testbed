"""Semantic acceptance gate for repeated terrain replay pilots.

The gate deliberately separates process integrity, episode-level task semantics,
and selective replay-derived effect labels.  Post-contact trajectory error stays
visible as a diagnostic, but it cannot invalidate otherwise useful expert ACT
supervision or stable terrain outcomes.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from functools import cache
from typing import Any

import numpy as np

from testbed.data.schema import (
    ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
)
from testbed.eval.terrain_replay_relabel_stats import build_replay_relabel_stats
from testbed.eval.terrain_residual_contract import list_replay_snapshot_target_specs
from testbed.eval.terrain_target_grid import build_rectangular_target_grid
from testbed.eval.terrain_target_metrics import build_target_residual_metrics

SCHEMA = "terrain_replay_pilot_gate_v2"
SOURCE = "terrain_replay_semantic_pilot_gate"
SOURCE_REFERENCE_SCHEMA = "terrain_replay_source_semantic_reference_v1"
GRID_CELL_COUNT = 6


def build_source_semantic_reference(
    *,
    source_episode_id: str,
    control_hz: float,
    env_state: Any,
    cycle_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build the readonly expert baseline used by semantic replay evaluation."""

    validation_errors: list[str] = []
    complete_cycles: list[dict[str, int]] = []
    for index, raw_record in enumerate(cycle_records):
        record = _mapping(raw_record)
        if not bool(record.get("complete_cycle", False)):
            continue
        if not bool(record.get("replay_candidate", False)):
            continue
        cycle_id = _finite_int(
            record.get("cycle_id", record.get("cycle_index")),
        )
        dump_end_step = _finite_int(record.get("dump_end_step"))
        end_step_exclusive = _finite_int(record.get("end_step_exclusive"))
        if cycle_id is None or dump_end_step is None or end_step_exclusive is None:
            validation_errors.append(f"cycle_records[{index}] is missing boundaries")
            continue
        complete_cycles.append(
            {
                "source_cycle_id": cycle_id,
                "dump_end_step": dump_end_step,
                "end_step_exclusive": end_step_exclusive,
            }
        )

    complete_cycles.sort(key=lambda item: item["dump_end_step"])
    parsed_control_hz = _finite_float(control_hz)
    if parsed_control_hz is None or parsed_control_hz <= 0.0:
        validation_errors.append("control_hz must be finite and positive")
    if not complete_cycles:
        validation_errors.append("source has no complete replay-candidate cycles")

    source_end_step_exclusive = (
        max(item["end_step_exclusive"] for item in complete_cycles)
        if complete_cycles
        else 0
    )
    final_row: Any = None
    try:
        if source_end_step_exclusive <= 0 or source_end_step_exclusive > len(env_state):
            validation_errors.append("source semantic endpoint is outside env_state")
        else:
            final_row = env_state[source_end_step_exclusive - 1]
    except (TypeError, IndexError):
        validation_errors.append("env_state must be an indexable timestep array")

    removed_depth = _numeric_slice(
        final_row,
        ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
        GRID_CELL_COUNT,
    )
    valid_mask = _numeric_slice(
        final_row,
        ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
        GRID_CELL_COUNT,
    )
    if removed_depth is None:
        validation_errors.append("source endpoint is missing removed-depth grid")
    if valid_mask is None:
        validation_errors.append("source endpoint is missing grid valid mask")

    target_summaries: dict[str, dict[str, float]] = {}
    if removed_depth is not None and valid_mask is not None:
        for target in _official_target_specs():
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
            if target_grid.get("status") != "present":
                validation_errors.extend(
                    f"{target['target_id']}.{error}"
                    for error in target_grid.get("validation_errors", [])
                )
                continue
            metrics = build_target_residual_metrics(
                removed_depth_grid_m=removed_depth,
                target_depth_grid_m=target_grid["target_depth_grid_m"],
                target_region_mask=target_grid["target_region_mask"],
                valid_mask=valid_mask,
                profile=str(target["profile"]),
                grid_shape=target["grid_shape"],
            )
            if metrics.get("status") != "present":
                validation_errors.extend(
                    f"{target['target_id']}.{error}"
                    for error in metrics.get("validation_errors", [])
                )
                continue
            target_summaries[str(target["target_id"])] = {
                "target_removed_completion_ratio": float(
                    metrics["target_removed_completion_ratio"]
                ),
                "target_positive_residual_depth_sum_m": float(
                    metrics["target_positive_residual_depth_sum_m"]
                ),
                "target_overdig_depth_sum_m": float(
                    metrics["target_overdig_depth_sum_m"]
                ),
                "outside_target_removed_depth_sum_m": float(
                    metrics["outside_target_removed_depth_sum_m"]
                ),
            }

    return {
        "schema": SOURCE_REFERENCE_SCHEMA,
        "status": "present" if not validation_errors else "invalid_source_reference",
        "source_episode_id": str(source_episode_id),
        "control_hz": parsed_control_hz,
        "complete_cycle_count": len(complete_cycles),
        "source_end_step_exclusive": source_end_step_exclusive,
        "cycle_boundaries": [
            {
                "source_cycle_id": item["source_cycle_id"],
                "dump_end_step": item["dump_end_step"],
            }
            for item in complete_cycles
        ],
        "removed_depth_grid_end_m": removed_depth or [],
        "valid_mask": valid_mask or [],
        "target_summaries": target_summaries,
        "validation_errors": validation_errors,
    }


def evaluate_replay_pilot_gate(
    repeats: Sequence[Mapping[str, Any]],
    *,
    source_reference: Mapping[str, Any],
    required_source_episode_id: str = "episode_28",
    required_repeat_count: int = 5,
    pre_contact_qpos_max_error_limit: float = 0.02,
    target_cell_valid_fraction_min: float = 0.5,
    semantic_repeat_fraction_min: float = 0.8,
    cycle_completion_ratio_min: float = 0.85,
    target_completion_drop_max: float = 0.05,
    target_completion_std_max: float = 0.05,
    final_grid_max_cell_std_m: float = 0.06,
    positive_residual_tolerance_m: float = 0.05,
    shape_relative_tolerance: float = 0.15,
    shape_absolute_tolerance_m: float = 0.05,
    boundary_tolerance_s: float = 1.0,
    min_official_ab_fraction: float = 0.8,
) -> dict[str, Any]:
    """Evaluate process integrity, semantic quality, and effect-label yield."""

    validation_errors: list[str] = []
    failed_checks: list[str] = []
    reference = _mapping(source_reference)
    validation_errors.extend(str(item) for item in reference.get("validation_errors", []))

    source_episode_id = str(reference.get("source_episode_id", ""))
    if source_episode_id != str(required_source_episode_id):
        validation_errors.append(
            "source_reference.source_episode_id does not match required source"
        )
    source_cycle_count = _finite_int(reference.get("complete_cycle_count"))
    source_end_step_exclusive = _finite_int(
        reference.get("source_end_step_exclusive")
    )
    control_hz = _finite_float(reference.get("control_hz"))
    target_references = _mapping(reference.get("target_summaries"))
    source_boundaries = _source_boundaries(reference.get("cycle_boundaries"))
    if source_cycle_count is None or source_cycle_count <= 0:
        validation_errors.append("source_reference.complete_cycle_count must be positive")
    if source_end_step_exclusive is None or source_end_step_exclusive <= 0:
        validation_errors.append(
            "source_reference.source_end_step_exclusive must be positive"
        )
    if control_hz is None or control_hz <= 0.0:
        validation_errors.append("source_reference.control_hz must be positive")
    if not source_boundaries:
        validation_errors.append("source_reference.cycle_boundaries is required")

    official_targets = tuple(str(spec["target_id"]) for spec in _official_target_specs())
    for target_id in official_targets:
        if target_id not in target_references:
            validation_errors.append(
                f"source_reference.target_summaries.{target_id} is required"
            )

    repeat_maps = [_mapping(value) for value in repeats]
    if len(repeat_maps) != int(required_repeat_count):
        failed_checks.append("repeat_count_mismatch")

    reference_geometry: tuple[float, ...] | None = None
    geometry_stable = True
    valid_fraction_ok = True
    target_set_complete = True
    source_episode_matches = True
    qpos_max = 0.0
    pre_contact_qpos_max = 0.0
    exception_count = 0
    pose_realign_count = 0
    step_sequences_complete = True
    semantic_repeat_results: list[dict[str, Any]] = []
    formal_repeats: list[dict[str, Any]] = []
    final_grids: list[list[float]] = []
    target_completion_values: dict[str, list[float]] = {
        target_id: [] for target_id in official_targets
    }
    boundary_match_summaries: list[dict[str, Any]] = []
    boundary_tolerance_steps = int(
        round(float(boundary_tolerance_s) * float(control_hz or 0.0))
    )

    for repeat_index, repeat in enumerate(repeat_maps):
        diagnostic = _mapping(repeat.get("diagnostic_summary"))
        qpos = _finite_float(diagnostic.get("qpos_max_error_max"))
        pre_contact_qpos = _finite_float(
            diagnostic.get("qpos_pre_contact_max_error_max")
        )
        first_contact_step = _finite_int(
            diagnostic.get("first_qualified_contact_step")
        )
        exceptions = _finite_int(diagnostic.get("exception_count"))
        realigns = _finite_int(diagnostic.get("pose_realign_count"))
        step_sequence_complete = diagnostic.get("step_sequence_complete")
        replay_source_step_count = _finite_int(diagnostic.get("source_step_count"))
        final_replay_grid = _float_sequence(
            diagnostic.get("final_removed_depth_grid_m")
        )
        if (
            qpos is None
            or pre_contact_qpos is None
            or first_contact_step is None
            or exceptions is None
            or realigns is None
            or not isinstance(step_sequence_complete, bool)
            or replay_source_step_count is None
            or final_replay_grid is None
            or len(final_replay_grid) != GRID_CELL_COUNT
        ):
            validation_errors.append(
                f"repeats[{repeat_index}].diagnostic_summary is incomplete"
            )
        else:
            qpos_max = max(qpos_max, qpos)
            pre_contact_qpos_max = max(pre_contact_qpos_max, pre_contact_qpos)
            exception_count += exceptions
            pose_realign_count += realigns
            step_sequences_complete = (
                step_sequences_complete
                and step_sequence_complete
                and replay_source_step_count == source_end_step_exclusive
            )

        raw_records = repeat.get("candidate_records")
        if not isinstance(raw_records, Sequence) or isinstance(
            raw_records, (str, bytes)
        ):
            validation_errors.append(
                f"repeats[{repeat_index}].candidate_records must be a list"
            )
            continue
        records = [_mapping(value) for value in raw_records]
        observed_boundaries = _observed_boundaries(records)
        matches = match_monotonic_boundaries(
            source_boundaries,
            observed_boundaries,
            tolerance_steps=max(0, boundary_tolerance_steps),
        )
        observed_to_source = {
            item["observed_cycle_index"]: item["source_cycle_id"]
            for item in matches
        }
        boundary_match_summaries.append(
            {
                "repeat_id": str(
                    repeat.get("repeat_id", f"repeat_{repeat_index:03d}")
                ),
                "observed_cycle_count": len(observed_boundaries),
                "matched_cycle_count": len(matches),
                "source_cycle_count": int(source_cycle_count or 0),
                "matched_cycle_fraction": (
                    len(matches) / int(source_cycle_count)
                    if source_cycle_count
                    else 0.0
                ),
                "max_boundary_error_steps": max(
                    (item["boundary_error_steps"] for item in matches),
                    default=None,
                ),
            }
        )

        targets_by_cycle: dict[int, set[str]] = {}
        aligned_formal_records: list[dict[str, Any]] = []
        for record_index, record in enumerate(records):
            record_source_episode_id = str(
                record.get("source_episode_id") or record.get("episode_id") or ""
            )
            if record_source_episode_id != str(required_source_episode_id):
                source_episode_matches = False
            target_id = str(record.get("target_id", ""))
            cycle_index = _finite_int(record.get("cycle_index"))
            if not target_id or cycle_index is None:
                validation_errors.append(
                    f"repeats[{repeat_index}].candidate_records[{record_index}] "
                    "is missing target/cycle fields"
                )
                continue
            targets_by_cycle.setdefault(cycle_index, set()).add(target_id)
            if target_id in official_targets and cycle_index in observed_to_source:
                aligned_formal_records.append(
                    {
                        **record,
                        "source_episode_id": record_source_episode_id,
                        "source_cycle_id": observed_to_source[cycle_index],
                    }
                )

            geometry_start = _float_sequence(record.get("grid_geometry_start"))
            geometry_end = _float_sequence(record.get("grid_geometry_end"))
            if (
                not bool(record.get("grid_geometry_stable", False))
                or geometry_start is None
                or geometry_end is None
                or not _vectors_close(geometry_start, geometry_end)
            ):
                geometry_stable = False
            elif reference_geometry is None:
                reference_geometry = tuple(geometry_end)
            elif not _vectors_close(reference_geometry, geometry_end):
                geometry_stable = False

            target_mask = _float_sequence(record.get("target_region_mask"))
            valid_start = _float_sequence(record.get("surface_valid_fraction_start"))
            valid_end = _float_sequence(record.get("surface_valid_fraction_end"))
            if (
                target_mask is None
                or valid_start is None
                or valid_end is None
                or not (len(target_mask) == len(valid_start) == len(valid_end))
            ):
                validation_errors.append(
                    f"repeats[{repeat_index}].candidate_records[{record_index}] "
                    "is missing grid validity fields"
                )
            else:
                for mask, start_fraction, end_fraction in zip(
                    target_mask,
                    valid_start,
                    valid_end,
                    strict=True,
                ):
                    if mask > 0.5 and min(start_fraction, end_fraction) < float(
                        target_cell_valid_fraction_min
                    ):
                        valid_fraction_ok = False

        expected_targets = {
            str(spec["target_id"]) for spec in list_replay_snapshot_target_specs()
        }
        for present_targets in targets_by_cycle.values():
            if present_targets != expected_targets:
                target_set_complete = False

        semantic_result = _evaluate_repeat_semantics(
            records=records,
            final_removed_depth_grid_m=final_replay_grid,
            source_valid_mask=_float_sequence(reference.get("valid_mask")),
            official_targets=official_targets,
            target_references=target_references,
            source_cycle_count=int(source_cycle_count or 0),
            cycle_completion_ratio_min=float(cycle_completion_ratio_min),
            target_completion_drop_max=float(target_completion_drop_max),
            positive_residual_tolerance_m=float(positive_residual_tolerance_m),
            shape_relative_tolerance=float(shape_relative_tolerance),
            shape_absolute_tolerance_m=float(shape_absolute_tolerance_m),
        )
        semantic_result["repeat_id"] = str(
            repeat.get("repeat_id", f"repeat_{repeat_index:03d}")
        )
        semantic_repeat_results.append(semantic_result)
        if semantic_result["final_removed_depth_grid_m"]:
            final_grids.append(semantic_result["final_removed_depth_grid_m"])
        for target_id, metrics in semantic_result["target_results"].items():
            completion = _finite_float(metrics.get("completion"))
            if completion is not None:
                target_completion_values[target_id].append(completion)

        formal_repeats.append(
            {
                "repeat_id": semantic_result["repeat_id"],
                "diagnostic_summary": diagnostic,
                "candidate_records": aligned_formal_records,
            }
        )

    if exception_count != 0:
        failed_checks.append("exception_present")
    if pose_realign_count != 0:
        failed_checks.append("pose_realign_present")
    if not step_sequences_complete:
        failed_checks.append("replay_step_sequence_incomplete")
    if pre_contact_qpos_max > float(pre_contact_qpos_max_error_limit):
        failed_checks.append("pre_contact_qpos_max_error_exceeded")
    if not geometry_stable:
        failed_checks.append("grid_geometry_unstable")
    if not valid_fraction_ok:
        failed_checks.append("target_cell_valid_fraction_below_minimum")
    if not target_set_complete:
        failed_checks.append("replay_snapshot_target_set_incomplete")
    if not source_episode_matches:
        failed_checks.append("pilot_source_episode_mismatch")

    semantic_pass_count = sum(bool(item["pass"]) for item in semantic_repeat_results)
    semantic_pass_required = math.ceil(
        int(required_repeat_count) * float(semantic_repeat_fraction_min)
    )
    if semantic_pass_count < semantic_pass_required:
        failed_checks.append("semantic_pass_repeat_count_below_minimum")

    completion_std_by_target: dict[str, float | None] = {}
    for target_id, values in target_completion_values.items():
        if len(values) != len(repeat_maps):
            completion_std_by_target[target_id] = None
            validation_errors.append(
                f"target completion is incomplete across repeats: {target_id}"
            )
            continue
        completion_std_by_target[target_id] = float(np.std(values))
    completion_std_max = max(
        (value for value in completion_std_by_target.values() if value is not None),
        default=0.0,
    )
    if completion_std_max > float(target_completion_std_max):
        failed_checks.append("target_completion_std_exceeded")

    final_grid_max_std = _final_grid_max_cell_std(final_grids)
    if final_grid_max_std is None:
        validation_errors.append("final removed-depth grid is incomplete across repeats")
    elif final_grid_max_std > float(final_grid_max_cell_std_m):
        failed_checks.append("final_grid_max_cell_std_exceeded")

    variance = build_replay_relabel_stats(
        formal_repeats,
        min_repeat_count=int(required_repeat_count),
    )
    variance_records = list(variance.get("records", []))
    usable = sum(record.get("tier") in {"A", "B"} for record in variance_records)
    ab_fraction = usable / len(variance_records) if variance_records else 0.0
    if variance.get("status") != "present":
        validation_errors.extend(str(item) for item in variance["validation_errors"])
    usable_source_cycles = _usable_source_cycles(
        variance_records,
        official_targets=official_targets,
    )

    failed_checks = list(dict.fromkeys(failed_checks))
    validation_errors = list(dict.fromkeys(validation_errors))
    status = "present" if not validation_errors else "invalid_inputs"
    process_check_names = {
        "repeat_count_mismatch",
        "exception_present",
        "pose_realign_present",
        "replay_step_sequence_incomplete",
        "pre_contact_qpos_max_error_exceeded",
        "grid_geometry_unstable",
        "target_cell_valid_fraction_below_minimum",
        "replay_snapshot_target_set_incomplete",
        "pilot_source_episode_mismatch",
    }
    semantic_check_names = {
        "semantic_pass_repeat_count_below_minimum",
        "target_completion_std_exceeded",
        "final_grid_max_cell_std_exceeded",
    }
    process_integrity_pass = status == "present" and not any(
        check in process_check_names for check in failed_checks
    )
    episode_semantic_pass = status == "present" and not any(
        check in semantic_check_names for check in failed_checks
    )
    passed = process_integrity_pass and episode_semantic_pass and not failed_checks
    semantic_grade = _semantic_grade(
        passed=passed,
        semantic_pass_count=semantic_pass_count,
        repeat_count=len(repeat_maps),
        cycle_completion_ratio_min_observed=min(
            (item["cycle_completion_ratio"] for item in semantic_repeat_results),
            default=0.0,
        ),
        completion_std_max=completion_std_max,
        final_grid_max_cell_std=final_grid_max_std,
    )
    return {
        "schema": SCHEMA,
        "source": SOURCE,
        "status": status,
        "pass": passed,
        "process_integrity_pass": process_integrity_pass,
        "episode_semantic_pass": episode_semantic_pass,
        "semantic_grade": semantic_grade,
        "repeat_count": len(repeat_maps),
        "required_repeat_count": int(required_repeat_count),
        "required_source_episode_id": str(required_source_episode_id),
        "source_complete_cycle_count": int(source_cycle_count or 0),
        "qpos_max_error_max": qpos_max,
        "qpos_pre_contact_max_error_max": pre_contact_qpos_max,
        "pre_contact_qpos_max_error_limit": float(pre_contact_qpos_max_error_limit),
        "post_contact_qpos_gate": "diagnostic_only",
        "exception_count": exception_count,
        "pose_realign_count": pose_realign_count,
        "replay_step_sequences_complete": step_sequences_complete,
        "grid_geometry_stable": geometry_stable,
        "target_cell_valid_fraction_min": float(target_cell_valid_fraction_min),
        "replay_snapshot_target_set_complete": target_set_complete,
        "semantic_repeat_fraction_min": float(semantic_repeat_fraction_min),
        "cycle_completion_ratio_min": float(cycle_completion_ratio_min),
        "target_completion_drop_max": float(target_completion_drop_max),
        "positive_residual_tolerance_m": float(positive_residual_tolerance_m),
        "shape_relative_tolerance": float(shape_relative_tolerance),
        "shape_absolute_tolerance_m": float(shape_absolute_tolerance_m),
        "semantic_pass_repeat_count": semantic_pass_count,
        "semantic_pass_repeat_count_required": semantic_pass_required,
        "semantic_repeat_results": semantic_repeat_results,
        "target_completion_std_by_target": completion_std_by_target,
        "target_completion_std_max": completion_std_max,
        "target_completion_std_limit": float(target_completion_std_max),
        "final_grid_max_cell_std_m": final_grid_max_std,
        "final_grid_max_cell_std_limit_m": float(final_grid_max_cell_std_m),
        "boundary_exact_match_required": False,
        "boundary_tolerance_s": float(boundary_tolerance_s),
        "boundary_match_summaries": boundary_match_summaries,
        "official_ab_fraction": ab_fraction,
        "official_ab_fraction_previous_hard_min": float(min_official_ab_fraction),
        "effect_label_yield_is_hard_gate": False,
        "effect_usable_source_cycle_count": len(usable_source_cycles),
        "effect_usable_source_cycle_ids": usable_source_cycles,
        "variance_tier_counts": variance.get("tier_counts", {}),
        "variance_records": variance_records,
        "act_training_decision": "not_rejected_by_replay",
        "effect_training_decision": "use_a_b_only_mask_c",
        "action_replay_contract": "exact_source_action_per_fixed_unity_step",
        "semantic_endpoint_source": "diagnostic_terminal_env_state",
        "failed_checks": failed_checks,
        "validation_errors": validation_errors,
    }


def _evaluate_repeat_semantics(
    *,
    records: Sequence[Mapping[str, Any]],
    final_removed_depth_grid_m: Sequence[float] | None,
    source_valid_mask: Sequence[float] | None,
    official_targets: Sequence[str],
    target_references: Mapping[str, Any],
    source_cycle_count: int,
    cycle_completion_ratio_min: float,
    target_completion_drop_max: float,
    positive_residual_tolerance_m: float,
    shape_relative_tolerance: float,
    shape_absolute_tolerance_m: float,
) -> dict[str, Any]:
    failures: list[str] = []
    observed_cycles = {
        int(cycle_index)
        for cycle_index in (_finite_int(record.get("cycle_index")) for record in records)
        if cycle_index is not None
    }
    cycle_completion_ratio = (
        min(len(observed_cycles) / source_cycle_count, 1.0)
        if source_cycle_count > 0
        else 0.0
    )
    if cycle_completion_ratio < cycle_completion_ratio_min:
        failures.append("cycle_completion_ratio_below_minimum")

    target_results: dict[str, dict[str, Any]] = {}
    for target_id in official_targets:
        reference = _mapping(target_references.get(target_id))
        replay_metrics = _target_metrics_from_final_grid(
            target_id=target_id,
            removed_depth_grid_m=final_removed_depth_grid_m,
            valid_mask=source_valid_mask,
        )
        completion = _finite_float(
            replay_metrics.get("target_removed_completion_ratio")
        )
        residual = _finite_float(
            replay_metrics.get("target_positive_residual_depth_sum_m")
        )
        overdig = _finite_float(replay_metrics.get("target_overdig_depth_sum_m"))
        outside = _finite_float(
            replay_metrics.get("outside_target_removed_depth_sum_m")
        )
        source_completion = _finite_float(
            reference.get("target_removed_completion_ratio")
        )
        source_residual = _finite_float(
            reference.get("target_positive_residual_depth_sum_m")
        )
        source_overdig = _finite_float(reference.get("target_overdig_depth_sum_m"))
        source_outside = _finite_float(
            reference.get("outside_target_removed_depth_sum_m")
        )
        values = (
            completion,
            residual,
            overdig,
            outside,
            source_completion,
            source_residual,
            source_overdig,
            source_outside,
        )
        if any(value is None for value in values):
            failures.append(f"incomplete_target_metrics:{target_id}")
            continue

        target_failures: list[str] = []
        if completion < source_completion - target_completion_drop_max:
            target_failures.append("completion_below_source_tolerance")
        if residual > source_residual + positive_residual_tolerance_m:
            target_failures.append("positive_residual_above_source_tolerance")
        overdig_tolerance = max(
            shape_absolute_tolerance_m,
            abs(source_overdig) * shape_relative_tolerance,
        )
        outside_tolerance = max(
            shape_absolute_tolerance_m,
            abs(source_outside) * shape_relative_tolerance,
        )
        if overdig > source_overdig + overdig_tolerance:
            target_failures.append("overdig_above_source_tolerance")
        if outside > source_outside + outside_tolerance:
            target_failures.append("outside_removal_above_source_tolerance")
        failures.extend(f"{target_id}:{item}" for item in target_failures)
        target_results[target_id] = {
            "completion": completion,
            "source_completion": source_completion,
            "positive_residual_depth_sum_m": residual,
            "source_positive_residual_depth_sum_m": source_residual,
            "overdig_depth_sum_m": overdig,
            "source_overdig_depth_sum_m": source_overdig,
            "outside_target_removed_depth_sum_m": outside,
            "source_outside_target_removed_depth_sum_m": source_outside,
            "failed_checks": target_failures,
        }

    final_grid = _float_sequence(final_removed_depth_grid_m)
    if final_grid is None or len(final_grid) != GRID_CELL_COUNT:
        failures.append("missing_final_removed_depth_grid")
        final_grid = []
    return {
        "pass": not failures,
        "observed_cycle_count": len(observed_cycles),
        "cycle_completion_ratio": cycle_completion_ratio,
        "target_results": target_results,
        "final_removed_depth_grid_m": final_grid,
        "failed_checks": failures,
    }


def _target_metrics_from_final_grid(
    *,
    target_id: str,
    removed_depth_grid_m: Sequence[float] | None,
    valid_mask: Sequence[float] | None,
) -> Mapping[str, Any]:
    if (
        removed_depth_grid_m is None
        or valid_mask is None
        or len(removed_depth_grid_m) != GRID_CELL_COUNT
        or len(valid_mask) != GRID_CELL_COUNT
    ):
        return {}
    target = next(
        (
            spec
            for spec in _official_target_specs()
            if str(spec["target_id"]) == str(target_id)
        ),
        None,
    )
    if target is None:
        return {}
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
    if target_grid.get("status") != "present":
        return {}
    return build_target_residual_metrics(
        removed_depth_grid_m=removed_depth_grid_m,
        target_depth_grid_m=target_grid["target_depth_grid_m"],
        target_region_mask=target_grid["target_region_mask"],
        valid_mask=valid_mask,
        profile=str(target["profile"]),
        grid_shape=target["grid_shape"],
    )


def match_monotonic_boundaries(
    source: Sequence[tuple[int, int]],
    observed: Sequence[tuple[int, int]],
    *,
    tolerance_steps: int,
) -> list[dict[str, int]]:
    """Maximize monotonic matches, then minimize total boundary error."""

    @cache
    def solve(i: int, j: int) -> tuple[int, int, tuple[tuple[int, int, int], ...]]:
        if i >= len(source) or j >= len(observed):
            return 0, 0, ()
        options = [solve(i + 1, j), solve(i, j + 1)]
        source_cycle_id, source_step = source[i]
        observed_cycle_index, observed_step = observed[j]
        error = abs(source_step - observed_step)
        if error <= tolerance_steps:
            count, cost, pairs = solve(i + 1, j + 1)
            options.append(
                (
                    count + 1,
                    cost + error,
                    ((source_cycle_id, observed_cycle_index, error),) + pairs,
                )
            )
        return max(options, key=lambda item: (item[0], -item[1]))

    _, _, pairs = solve(0, 0)
    return [
        {
            "source_cycle_id": source_cycle_id,
            "observed_cycle_index": observed_cycle_index,
            "boundary_error_steps": error,
        }
        for source_cycle_id, observed_cycle_index, error in pairs
    ]


def _source_boundaries(value: Any) -> list[tuple[int, int]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    parsed: list[tuple[int, int]] = []
    for item in value:
        record = _mapping(item)
        cycle_id = _finite_int(record.get("source_cycle_id"))
        step = _finite_int(record.get("dump_end_step"))
        if cycle_id is not None and step is not None:
            parsed.append((cycle_id, step))
    return sorted(parsed, key=lambda item: item[1])


def _observed_boundaries(records: Sequence[Mapping[str, Any]]) -> list[tuple[int, int]]:
    by_cycle: dict[int, int] = {}
    for record in records:
        cycle_index = _finite_int(record.get("cycle_index"))
        end = _finite_int(record.get("cycle_end_observation_index"))
        if cycle_index is not None and end is not None:
            by_cycle.setdefault(cycle_index, end)
    return sorted(by_cycle.items(), key=lambda item: item[1])


def _final_grid_record(
    records: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    diagnostic_target = "recording_depth_0p08_full_grid_diagnostic"
    candidates = [
        record for record in records if str(record.get("target_id")) == diagnostic_target
    ]
    if not candidates:
        candidates = list(records)
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda record: _finite_int(
            record.get("cycle_end_observation_index"),
            default=-1,
        ),
    )


def _final_grid_max_cell_std(grids: Sequence[Sequence[float]]) -> float | None:
    if not grids or any(len(grid) != GRID_CELL_COUNT for grid in grids):
        return None
    return float(np.max(np.std(np.asarray(grids, dtype=float), axis=0)))


def _usable_source_cycles(
    records: Sequence[Mapping[str, Any]],
    *,
    official_targets: Sequence[str],
) -> list[int]:
    by_cycle: dict[int, set[str]] = {}
    for record in records:
        if record.get("tier") not in {"A", "B"}:
            continue
        cycle_id = _finite_int(record.get("source_cycle_id"))
        target_id = str(record.get("target_id", ""))
        if cycle_id is not None:
            by_cycle.setdefault(cycle_id, set()).add(target_id)
    required = set(official_targets)
    return sorted(cycle_id for cycle_id, targets in by_cycle.items() if targets == required)


def _semantic_grade(
    *,
    passed: bool,
    semantic_pass_count: int,
    repeat_count: int,
    cycle_completion_ratio_min_observed: float,
    completion_std_max: float,
    final_grid_max_cell_std: float | None,
) -> str:
    if not passed:
        return "C"
    if (
        semantic_pass_count == repeat_count
        and cycle_completion_ratio_min_observed >= 0.95
        and completion_std_max <= 0.02
        and final_grid_max_cell_std is not None
        and final_grid_max_cell_std <= 0.02
    ):
        return "A"
    return "B"


def _official_target_specs() -> list[dict[str, Any]]:
    return [
        dict(spec)
        for spec in list_replay_snapshot_target_specs()
        if spec.get("evidence_role") == "official_residual"
    ]


def _numeric_slice(value: Any, start: int, count: int) -> list[float] | None:
    if value is None:
        return None
    try:
        parsed = [_finite_float(value[index]) for index in range(start, start + count)]
    except (IndexError, TypeError):
        return None
    if any(item is None for item in parsed):
        return None
    return [float(item) for item in parsed if item is not None]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _finite_float(value: Any, *, default: float | None = None) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _finite_int(value: Any, *, default: int | None = None) -> int | None:
    parsed = _finite_float(value)
    return default if parsed is None else int(parsed)


def _float_sequence(value: Any) -> list[float] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    result = [_finite_float(item) for item in value]
    if any(item is None for item in result):
        return None
    return [float(item) for item in result if item is not None]


def _vectors_close(
    left: Sequence[float],
    right: Sequence[float],
    *,
    tolerance: float = 1.0e-6,
) -> bool:
    return len(left) == len(right) and all(
        abs(float(a) - float(b)) <= tolerance
        for a, b in zip(left, right, strict=True)
    )


__all__ = [
    "build_source_semantic_reference",
    "evaluate_replay_pilot_gate",
    "match_monotonic_boundaries",
]
