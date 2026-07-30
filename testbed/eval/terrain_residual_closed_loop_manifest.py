"""Eval-only closed-loop experiment manifest contract for terrain residual planning."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import PurePosixPath
from typing import Any

from testbed.eval.terrain_residual_contract import official_contract_statuses


SCHEMA = "terrain_residual_closed_loop_experiment_manifest_v1"
SOURCE = "explicit_closed_loop_experiment_manifest"
DEFAULT_PROFILE = "phase6d_t1_ab_closed_loop_manifest"
BRANCH_ORDER = [
    "current_planner_baseline",
    "heuristic_residual_pipeline",
    "calibrated_residual_pipeline",
]
TARGET_REQUIRED_FIELDS = [
    "grid_shape",
    "row_start",
    "row_end",
    "col_start",
    "col_end",
    "target_depth_m",
    "official_semantics",
]
TARGET_REQUIRED_ERROR = (
    "target_spec must include grid_shape, row_start, row_end, col_start, col_end, "
    "target_depth_m, and official_semantics"
)
ARTIFACT_PATH_ERROR = (
    "expected_artifact_files must be relative paths that stay under results_root"
)
NO_OVERWRITE_ERROR = (
    "results_root must not be the same as or nested under a protected evidence root"
)
BRANCH_DEFINITIONS_ERROR = (
    "branch_definitions must include current_planner_baseline, "
    "heuristic_residual_pipeline, and calibrated_residual_pipeline"
)


def build_closed_loop_experiment_manifest(
    *,
    results_root: Any,
    target_spec: Mapping[str, Any],
    branch_definitions: Mapping[str, Any],
    cycle_budget: Mapping[str, Any],
    stop_conditions: Mapping[str, Any],
    expected_metric_names: Sequence[Any],
    expected_artifact_files: Sequence[Any],
    protected_evidence_roots: Sequence[Any],
    calibration_available: Any = False,
    profile: str = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Build a pure eval manifest for a future closed-loop A/B experiment."""

    normalized_results_root = _string_value(results_root)
    normalized_target_spec = _normalize_target_spec(target_spec)
    normalized_branches = _normalize_branches(
        branch_definitions,
        calibration_available=bool(calibration_available),
    )
    normalized_cycle_budget = _normalize_cycle_budget(cycle_budget)
    normalized_stop_conditions = _normalize_stop_conditions(stop_conditions)
    normalized_metric_names = _normalize_string_sequence(expected_metric_names)
    normalized_artifact_files = _normalize_artifact_files(expected_artifact_files)
    normalized_protected_roots = _normalize_string_sequence(protected_evidence_roots)

    validations = [
        _validate_results_root(normalized_results_root),
        _validate_target_spec(normalized_target_spec),
        _validate_branch_definitions(normalized_branches),
        _validate_cycle_budget(normalized_cycle_budget),
        _validate_stop_conditions(normalized_stop_conditions),
        _validate_metric_names(normalized_metric_names),
        _validate_artifact_files(normalized_artifact_files),
        _validate_protected_roots(normalized_protected_roots),
    ]
    no_overwrite_validation = _no_overwrite_validation(
        results_root=normalized_results_root,
        protected_evidence_roots=normalized_protected_roots,
    )
    if no_overwrite_validation["status"] != "present":
        validations.append(
            ("protected_evidence_root_overlap", [NO_OVERWRITE_ERROR])
        )

    status, validation_errors = _first_status(validations)
    return {
        "schema": SCHEMA,
        "source": SOURCE,
        "status": status,
        "offline_only": True,
        "profile": str(profile),
        "branch_order": list(BRANCH_ORDER),
        "branches": normalized_branches,
        "artifact_layout": {
            "results_root": normalized_results_root,
            "expected_artifact_files": normalized_artifact_files,
            "artifact_count": len(normalized_artifact_files),
            "writes_files": False,
        },
        "no_overwrite_validation": no_overwrite_validation,
        "target_spec": normalized_target_spec,
        "cycle_budget": normalized_cycle_budget,
        "stop_condition_summary": normalized_stop_conditions,
        "expected_metric_names": normalized_metric_names,
        "validation_errors": validation_errors,
        "non_goal_statuses": _non_goal_statuses(),
        "provenance_statuses": _provenance_statuses(),
    }


def _normalize_target_spec(target_spec: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(target_spec, Mapping):
        return {}
    return {str(key): value for key, value in target_spec.items()}


def _normalize_branches(
    branch_definitions: Mapping[str, Any],
    *,
    calibration_available: bool,
) -> dict[str, dict[str, Any]]:
    if not isinstance(branch_definitions, Mapping):
        return {}

    branches: dict[str, dict[str, Any]] = {}
    for branch_name in BRANCH_ORDER:
        branch_definition = branch_definitions.get(branch_name)
        if not isinstance(branch_definition, Mapping):
            continue
        branch = {str(key): value for key, value in branch_definition.items()}
        branch["branch_name"] = branch_name
        if branch_name == "calibrated_residual_pipeline":
            branch["calibration_available"] = calibration_available
            if not calibration_available:
                branch["status"] = "not_evaluated"
                branch["reason"] = "blocked_by_missing_gold_samples"
            else:
                branch.setdefault("status", "present")
        elif branch_name == "heuristic_residual_pipeline":
            branch.setdefault("runtime_integration_status", "not_integrated")
            branch.setdefault("status", "present")
        else:
            branch.setdefault("status", "present")
        branches[branch_name] = branch
    return branches


def _normalize_cycle_budget(cycle_budget: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(cycle_budget, Mapping):
        return {}
    return {str(key): value for key, value in cycle_budget.items()}


def _normalize_stop_conditions(stop_conditions: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(stop_conditions, Mapping):
        return {}
    return {str(key): value for key, value in stop_conditions.items()}


def _normalize_string_sequence(value: Sequence[Any]) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return []
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            return []
        normalized.append(item)
    return normalized


def _normalize_artifact_files(expected_artifact_files: Sequence[Any]) -> list[str]:
    return _normalize_string_sequence(expected_artifact_files)


def _validate_results_root(results_root: str | None) -> tuple[str, list[str]]:
    if not results_root:
        return "invalid_artifact_layout", ["results_root must be a non-empty path string"]
    return "present", []


def _validate_target_spec(target_spec: Mapping[str, Any]) -> tuple[str, list[str]]:
    if not all(field in target_spec for field in TARGET_REQUIRED_FIELDS):
        return "invalid_target_spec", [TARGET_REQUIRED_ERROR]
    grid_shape = target_spec.get("grid_shape")
    if (
        not isinstance(grid_shape, Sequence)
        or isinstance(grid_shape, (str, bytes))
        or len(grid_shape) != 2
    ):
        return "invalid_target_spec", ["target_spec grid_shape must contain two values"]
    depth = target_spec.get("target_depth_m")
    if not _finite_number(depth):
        return "invalid_target_spec", ["target_depth_m must be a finite number"]
    return "present", []


def _validate_branch_definitions(
    branch_definitions: Mapping[str, Mapping[str, Any]],
) -> tuple[str, list[str]]:
    if not all(branch_name in branch_definitions for branch_name in BRANCH_ORDER):
        return "invalid_branch_definitions", [BRANCH_DEFINITIONS_ERROR]
    return "present", []


def _validate_cycle_budget(cycle_budget: Mapping[str, Any]) -> tuple[str, list[str]]:
    max_cycles = cycle_budget.get("max_cycles")
    if not isinstance(max_cycles, int) or max_cycles <= 0:
        return "invalid_cycle_budget", ["cycle_budget must include positive integer max_cycles"]
    return "present", []


def _validate_stop_conditions(
    stop_conditions: Mapping[str, Any],
) -> tuple[str, list[str]]:
    if not stop_conditions:
        return "invalid_stop_conditions", ["stop_conditions must not be empty"]
    return "present", []


def _validate_metric_names(metric_names: Sequence[str]) -> tuple[str, list[str]]:
    if not metric_names:
        return "invalid_metric_names", ["expected_metric_names must contain names"]
    return "present", []


def _validate_artifact_files(
    expected_artifact_files: Sequence[str],
) -> tuple[str, list[str]]:
    if not expected_artifact_files:
        return "invalid_artifact_layout", [ARTIFACT_PATH_ERROR]
    if not all(_is_relative_artifact_path(path) for path in expected_artifact_files):
        return "invalid_artifact_layout", [ARTIFACT_PATH_ERROR]
    return "present", []


def _validate_protected_roots(
    protected_evidence_roots: Sequence[str],
) -> tuple[str, list[str]]:
    if not protected_evidence_roots:
        return "invalid_protected_evidence_roots", [
            "protected_evidence_roots must contain at least one root",
        ]
    return "present", []


def _no_overwrite_validation(
    *,
    results_root: str | None,
    protected_evidence_roots: Sequence[str],
) -> dict[str, Any]:
    overlap_detected = False
    if results_root:
        overlap_detected = any(
            _is_same_or_nested(results_root, protected_root)
            for protected_root in protected_evidence_roots
        )
    return {
        "status": "protected_evidence_root_overlap"
        if overlap_detected
        else "present",
        "protected_evidence_roots": list(protected_evidence_roots),
        "overlap_detected": overlap_detected,
    }


def _first_status(
    validations: Sequence[tuple[str, list[str]]],
) -> tuple[str, list[str]]:
    for status, errors in validations:
        if status != "present":
            return status, errors
    return "present", []


def _is_relative_artifact_path(path: str) -> bool:
    pure_path = PurePosixPath(path)
    if pure_path.is_absolute():
        return False
    return ".." not in pure_path.parts and "." not in pure_path.parts


def _is_same_or_nested(path: str, parent: str) -> bool:
    path_parts = _normalized_path_parts(path)
    parent_parts = _normalized_path_parts(parent)
    if not path_parts or not parent_parts:
        return False
    return len(path_parts) >= len(parent_parts) and path_parts[: len(parent_parts)] == parent_parts


def _normalized_path_parts(path: str) -> tuple[str, ...]:
    return tuple(part for part in PurePosixPath(path).parts if part not in ("", "."))


def _string_value(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _non_goal_statuses() -> dict[str, str]:
    return {
        "simulation_status": "not_run",
        "run_artifact_status": "not_created",
        "production_planner_integration_status": "not_integrated",
        "rollout_review_schema_integration_status": "not_integrated",
        "runtime_action_selection_status": "not_defined",
        **official_contract_statuses(),
    }


def _provenance_statuses() -> dict[str, str]:
    return {
        "target_spec_source": "explicit_input",
        "results_root_source": "explicit_input",
        "branch_definitions_source": "explicit_input",
        "cycle_budget_source": "explicit_input",
        "stop_conditions_source": "explicit_input",
        "expected_metrics_source": "explicit_input",
        "expected_artifact_files_source": "explicit_input",
        "protected_evidence_roots_source": "explicit_input",
        "artifact_write_status": "not_written",
    }
