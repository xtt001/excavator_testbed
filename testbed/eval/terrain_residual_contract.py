"""Official Phase 6 terrain-residual target and pass/fail contract."""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

TARGET_SCHEMA = "terrain_residual_target_v1"
TARGET_SOURCE = "official_terrain_residual_target_contract"
OFFICIAL_SEMANTICS = "official_phase6_v0_default"
OFFICIAL_PASS_FAIL_PROFILE_ID = "not_worse_than_current_A_gate2_baseline"
PASS_FAIL_SCHEMA = "terrain_residual_pass_fail_v1"
PASS_FAIL_SOURCE = "official_a_baseline_anchored_terrain_quality_pass_fail"
MIN_COMPLETED_DUMP_COUNT = 2
METRIC_TOLERANCE = 1.0e-12
RECORDING_DIAGNOSTIC_TARGET_ID = "recording_depth_0p08_full_grid_diagnostic"


_OFFICIAL_TARGETS: dict[str, dict[str, Any]] = {
    "t1_large_shallow_rectangular_pit_default": {
        "target_id": "t1_large_shallow_rectangular_pit_default",
        "schema": TARGET_SCHEMA,
        "source": TARGET_SOURCE,
        "official_semantics": OFFICIAL_SEMANTICS,
        "grid_shape": [3, 2],
        "row_start": 0,
        "row_end": 2,
        "col_start": 0,
        "col_end": 2,
        "target_depth_m": 0.25,
        "profile": "official_phase6_v0_t1_large_shallow_rectangular_pit",
    },
    "t2_long_shallow_trench_default": {
        "target_id": "t2_long_shallow_trench_default",
        "schema": TARGET_SCHEMA,
        "source": TARGET_SOURCE,
        "official_semantics": OFFICIAL_SEMANTICS,
        "grid_shape": [3, 2],
        "row_start": 0,
        "row_end": 3,
        "col_start": 0,
        "col_end": 1,
        "target_depth_m": 0.25,
        "profile": "official_phase6_v0_t2_long_shallow_trench",
    },
}

_RECORDING_DIAGNOSTIC_TARGET = {
    "target_id": RECORDING_DIAGNOSTIC_TARGET_ID,
    "schema": TARGET_SCHEMA,
    "source": TARGET_SOURCE,
    "official_semantics": "recording_depth_diagnostic_only",
    "grid_shape": [3, 2],
    "row_start": 0,
    "row_end": 3,
    "col_start": 0,
    "col_end": 2,
    "target_depth_m": 0.08,
    "profile": "recording_depth_0p08_full_grid_diagnostic",
    "evidence_role": "recording_diagnostic",
}


def list_official_terrain_residual_target_specs() -> dict[str, Any]:
    """Return the official Phase 6 v0 terrain-residual targets."""

    return {
        "schema": TARGET_SCHEMA,
        "source": TARGET_SOURCE,
        "status": "present",
        "official_semantics": OFFICIAL_SEMANTICS,
        "targets": [dict(target) for target in _OFFICIAL_TARGETS.values()],
    }


def get_official_terrain_residual_target_spec(target_id: str) -> dict[str, Any]:
    """Return one official target spec by stable target id."""

    target = _OFFICIAL_TARGETS.get(str(target_id))
    if target is None:
        raise KeyError(f"unknown official terrain residual target: {target_id}")
    return dict(target)


def list_replay_snapshot_target_specs() -> list[dict[str, Any]]:
    """Return the one diagnostic and two official views of each replay snapshot."""
    official_ids = (
        "t1_large_shallow_rectangular_pit_default",
        "t2_long_shallow_trench_default",
    )
    specs = [dict(_RECORDING_DIAGNOSTIC_TARGET)]
    for target_id in official_ids:
        spec = dict(_OFFICIAL_TARGETS[target_id])
        spec["evidence_role"] = "official_residual"
        specs.append(spec)
    return specs


def get_replay_snapshot_target_spec(target_id: str) -> dict[str, Any]:
    if str(target_id) == RECORDING_DIAGNOSTIC_TARGET_ID:
        return dict(_RECORDING_DIAGNOSTIC_TARGET)
    spec = get_official_terrain_residual_target_spec(target_id)
    spec["evidence_role"] = "official_residual"
    return spec


def official_contract_statuses() -> dict[str, str]:
    """Return shared official-semantics status fields for eval artifacts."""

    return {
        "official_success_semantics_status": "defined_by_terrain_residual_pass_fail_v1",
        "official_default_status": "defined_by_terrain_residual_target_v1",
        "official_threshold_status": "defined_by_a_baseline_anchored_v0",
        "calibrated_model_fallback_status": "not_invented",
    }


def evaluate_cycle_quality_against_baseline(
    *,
    candidate_summary: Mapping[str, Any],
    baseline_summary: Mapping[str, Any],
    target_id: str,
    profile: str = OFFICIAL_PASS_FAIL_PROFILE_ID,
) -> dict[str, Any]:
    """Evaluate a branch summary against the official A-baseline anchored profile."""

    if profile != OFFICIAL_PASS_FAIL_PROFILE_ID:
        return _pass_fail_result(
            status="invalid_profile",
            target_id=target_id,
            profile=profile,
            passed=False,
            failed_checks=[],
            validation_errors=[
                f"profile must be {OFFICIAL_PASS_FAIL_PROFILE_ID}",
            ],
            check_values={},
        )

    try:
        target = get_official_terrain_residual_target_spec(target_id)
    except KeyError as exc:
        return _pass_fail_result(
            status="invalid_target_id",
            target_id=str(target_id),
            profile=profile,
            passed=False,
            failed_checks=[],
            validation_errors=[str(exc)],
            check_values={},
        )

    check_values, validation_errors = _required_check_values(
        candidate_summary=candidate_summary,
        baseline_summary=baseline_summary,
    )
    if validation_errors:
        return _pass_fail_result(
            status="missing_required_fields",
            target_id=target["target_id"],
            profile=profile,
            passed=False,
            failed_checks=[],
            validation_errors=validation_errors,
            check_values=check_values,
        )

    failed_checks = _failed_checks(check_values)
    return _pass_fail_result(
        status="present",
        target_id=target["target_id"],
        profile=profile,
        passed=not failed_checks,
        failed_checks=failed_checks,
        validation_errors=[],
        check_values=check_values,
    )


def _pass_fail_result(
    *,
    status: str,
    target_id: str,
    profile: str,
    passed: bool,
    failed_checks: list[str],
    validation_errors: list[str],
    check_values: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": PASS_FAIL_SCHEMA,
        "source": PASS_FAIL_SOURCE,
        "status": status,
        "profile": profile,
        "comparison_basis": OFFICIAL_PASS_FAIL_PROFILE_ID,
        "target_id": str(target_id),
        "pass": bool(passed),
        "failed_checks": list(failed_checks),
        "validation_errors": list(validation_errors),
        "check_values": dict(check_values),
    }


def _required_check_values(
    *,
    candidate_summary: Mapping[str, Any],
    baseline_summary: Mapping[str, Any],
) -> tuple[dict[str, float | int], list[str]]:
    checks = {
        "target_cycle_gate_success": "int",
        "target_cycle_completed_dump_count": "int",
        "transition_timeout_count": "int",
        "latest_target_positive_residual_depth_sum_m": "float",
        "latest_target_overdig_depth_sum_m": "float",
        "latest_outside_target_removed_depth_sum_m": "float",
        "deposited_fraction_mean": "float",
        "depth_abs_error_m_mean": "float",
    }
    values: dict[str, float | int] = {}
    errors: list[str] = []
    for prefix, summary in (
        ("candidate", candidate_summary),
        ("baseline", baseline_summary),
    ):
        for field, kind in checks.items():
            raw_value = summary.get(field)
            parsed = _finite_number(raw_value)
            if parsed is None:
                errors.append(f"{prefix}.{field}")
                continue
            values[f"{prefix}.{field}"] = (
                int(parsed) if kind == "int" else float(parsed)
            )
    return values, errors


def _failed_checks(values: Mapping[str, float | int]) -> list[str]:
    failed: list[str] = []
    if int(values["candidate.target_cycle_gate_success"]) != 1:
        failed.append("target_cycle_gate_not_reached")
    if int(values["candidate.target_cycle_completed_dump_count"]) < MIN_COMPLETED_DUMP_COUNT:
        failed.append("completed_dump_count_below_minimum")
    if int(values["candidate.transition_timeout_count"]) != 0:
        failed.append("transition_timeout_present")

    if _greater_than_baseline(
        values,
        "latest_target_positive_residual_depth_sum_m",
    ):
        failed.append("target_positive_residual_worse_than_baseline")
    if _greater_than_baseline(values, "latest_target_overdig_depth_sum_m"):
        failed.append("target_overdig_worse_than_baseline")
    if _greater_than_baseline(values, "latest_outside_target_removed_depth_sum_m"):
        failed.append("outside_target_removed_worse_than_baseline")
    if _less_than_baseline(values, "deposited_fraction_mean"):
        failed.append("deposited_fraction_below_baseline")
    if _greater_than_baseline(values, "depth_abs_error_m_mean"):
        failed.append("depth_abs_error_above_baseline")
    return failed


def _greater_than_baseline(values: Mapping[str, float | int], field: str) -> bool:
    return (
        float(values[f"candidate.{field}"])
        > float(values[f"baseline.{field}"]) + METRIC_TOLERANCE
    )


def _less_than_baseline(values: Mapping[str, float | int], field: str) -> bool:
    return (
        float(values[f"candidate.{field}"])
        < float(values[f"baseline.{field}"]) - METRIC_TOLERANCE
    )


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(int(value))
    if not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None
