"""Eval-only A/B run command plan for residual terrain experiments."""

from __future__ import annotations

import shlex
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


SCHEMA = "terrain_residual_eval_run_plan_v1"
SOURCE = "explicit_residual_eval_run_plan"
DEFAULT_PROFILE = "phase6g_residual_eval_run_plan"
BRANCH_ORDER = [
    "current_planner_baseline",
    "heuristic_residual_pipeline",
    "calibrated_residual_pipeline",
]
B_RUNTIME_BLOCKERS = [
    "missing_residual_runtime_planner_mode",
    "missing_cut_intent_to_dig_cut_token_adapter",
    "missing_simulated_branch_execution_artifacts",
]


def build_residual_eval_run_plan(
    *,
    current_eval_metadata: Mapping[str, Any],
    predicted_ab_artifacts: Mapping[str, Any],
    planned_results_root: Any,
    protected_evidence_roots: Sequence[Any],
    residual_runtime_integration_available: bool,
    heuristic_branch_argv: Sequence[Any] | None = None,
    calibration_available: bool = False,
    profile: str = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Build an explicit run plan for the next real residual A/B eval step."""

    normalized_root = _path_string(planned_results_root)
    protected_roots = _string_list(protected_evidence_roots)
    no_overwrite_validation = _no_overwrite_validation(
        planned_results_root=normalized_root,
        protected_evidence_roots=protected_roots,
    )
    if no_overwrite_validation["status"] != "present":
        return _result(
            status=str(no_overwrite_validation["status"]),
            profile=profile,
            planned_results_root=normalized_root,
            protected_evidence_roots=protected_roots,
            branches={},
            artifact_inputs={},
            no_overwrite_validation=no_overwrite_validation,
            validation_errors=list(no_overwrite_validation["validation_errors"]),
        )

    current_argv, current_errors = _current_eval_argv(current_eval_metadata)
    if current_errors:
        return _result(
            status="invalid_current_eval_metadata",
            profile=profile,
            planned_results_root=normalized_root,
            protected_evidence_roots=protected_roots,
            branches={},
            artifact_inputs={},
            no_overwrite_validation=no_overwrite_validation,
            validation_errors=current_errors,
        )

    artifact_summary, artifact_errors = _artifact_inputs(predicted_ab_artifacts)
    if artifact_errors:
        return _result(
            status="invalid_predicted_ab_artifacts",
            profile=profile,
            planned_results_root=normalized_root,
            protected_evidence_roots=protected_roots,
            branches={},
            artifact_inputs=artifact_summary,
            no_overwrite_validation=no_overwrite_validation,
            validation_errors=artifact_errors,
        )

    heuristic_argv, heuristic_errors = _heuristic_argv(
        residual_runtime_integration_available=residual_runtime_integration_available,
        heuristic_branch_argv=heuristic_branch_argv,
    )
    if heuristic_errors:
        return _result(
            status="invalid_residual_runtime_integration",
            profile=profile,
            planned_results_root=normalized_root,
            protected_evidence_roots=protected_roots,
            branches={},
            artifact_inputs=artifact_summary,
            no_overwrite_validation=no_overwrite_validation,
            validation_errors=heuristic_errors,
        )

    branches = _branches(
        planned_results_root=normalized_root,
        current_eval_metadata=current_eval_metadata,
        current_argv=current_argv,
        predicted_ab_artifacts=artifact_summary,
        residual_runtime_integration_available=residual_runtime_integration_available,
        heuristic_argv=heuristic_argv,
        calibration_available=calibration_available,
    )
    return _result(
        status="present",
        profile=profile,
        planned_results_root=normalized_root,
        protected_evidence_roots=protected_roots,
        branches=branches,
        artifact_inputs=artifact_summary,
        no_overwrite_validation=no_overwrite_validation,
        validation_errors=[],
    )


def _result(
    *,
    status: str,
    profile: str,
    planned_results_root: str | None,
    protected_evidence_roots: list[str],
    branches: Mapping[str, Any],
    artifact_inputs: Mapping[str, Any],
    no_overwrite_validation: Mapping[str, Any],
    validation_errors: list[str],
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "source": SOURCE,
        "status": status,
        "offline_only": True,
        "profile": str(profile),
        "branch_order": list(BRANCH_ORDER),
        "planned_results_root": planned_results_root,
        "branches": dict(branches),
        "artifact_inputs": dict(artifact_inputs),
        "no_overwrite_validation": dict(no_overwrite_validation),
        "validation_errors": list(validation_errors),
        "non_goal_statuses": _non_goal_statuses(),
        "provenance_statuses": _provenance_statuses(status),
        "protected_evidence_roots": list(protected_evidence_roots),
    }


def _branches(
    *,
    planned_results_root: str,
    current_eval_metadata: Mapping[str, Any],
    current_argv: list[str],
    predicted_ab_artifacts: Mapping[str, Any],
    residual_runtime_integration_available: bool,
    heuristic_argv: list[str] | None,
    calibration_available: bool,
) -> dict[str, dict[str, Any]]:
    branch_roots = {
        branch: _join_path(planned_results_root, branch) for branch in BRANCH_ORDER
    }
    current_planner_argv = _argv_with_output_dir(
        current_argv, branch_roots["current_planner_baseline"]
    )
    branches = {
        "current_planner_baseline": {
            "label": "A",
            "status": "runnable",
            "evidence_type": "current_eval_command_plan",
            "command_status": "runnable",
            "argv": current_planner_argv,
            "command": shlex.join(current_planner_argv),
            "planned_output_dir": branch_roots["current_planner_baseline"],
            "source_eval_status": str(current_eval_metadata.get("status", "unknown")),
            "source_config_path": _config_path(current_argv),
            "target_cycle_gate": current_eval_metadata.get("target_cycle_gate"),
        },
        "heuristic_residual_pipeline": _heuristic_branch(
            branch_root=branch_roots["heuristic_residual_pipeline"],
            predicted_ab_artifacts=predicted_ab_artifacts,
            residual_runtime_integration_available=residual_runtime_integration_available,
            heuristic_argv=heuristic_argv,
        ),
        "calibrated_residual_pipeline": _calibrated_branch(
            branch_root=branch_roots["calibrated_residual_pipeline"],
            calibration_available=calibration_available,
        ),
    }
    return branches


def _heuristic_branch(
    *,
    branch_root: str,
    predicted_ab_artifacts: Mapping[str, Any],
    residual_runtime_integration_available: bool,
    heuristic_argv: list[str] | None,
) -> dict[str, Any]:
    if not residual_runtime_integration_available:
        return {
            "label": "B",
            "status": "not_runnable",
            "evidence_type": "predicted_artifact_to_runtime_gap",
            "command_status": "not_runnable",
            "runtime_integration_status": "missing",
            "planned_output_dir": branch_root,
            "predicted_artifact_root": predicted_ab_artifacts.get("results_root"),
            "predicted_artifact_status": predicted_ab_artifacts.get("status"),
            "blockers": list(B_RUNTIME_BLOCKERS),
        }

    assert heuristic_argv is not None
    planned_argv = _argv_with_output_dir(heuristic_argv, branch_root)
    return {
        "label": "B",
        "status": "runnable",
        "evidence_type": "heuristic_residual_eval_command_plan",
        "command_status": "runnable",
        "runtime_integration_status": "available",
        "argv": planned_argv,
        "command": shlex.join(planned_argv),
        "planned_output_dir": branch_root,
        "predicted_artifact_root": predicted_ab_artifacts.get("results_root"),
        "predicted_artifact_status": predicted_ab_artifacts.get("status"),
        "blockers": [],
    }


def _calibrated_branch(
    *,
    branch_root: str,
    calibration_available: bool,
) -> dict[str, Any]:
    if not calibration_available:
        return {
            "label": "C",
            "status": "not_evaluated",
            "reason": "blocked_by_missing_gold_samples",
            "command_status": "not_runnable",
            "planned_output_dir": branch_root,
        }
    return {
        "label": "C",
        "status": "needs_explicit_calibrated_command",
        "reason": "calibration_available_but_command_not_supplied",
        "command_status": "not_runnable",
        "planned_output_dir": branch_root,
    }


def _current_eval_argv(metadata: Any) -> tuple[list[str], list[str]]:
    if not isinstance(metadata, Mapping):
        return [], ["current_eval_metadata must be a mapping"]
    argv = metadata.get("argv")
    if (
        not isinstance(argv, Sequence)
        or isinstance(argv, (str, bytes))
        or len(argv) == 0
    ):
        return [], ["current_eval_metadata must include a non-empty argv list"]
    normalized = [str(item) for item in argv]
    if not all(item for item in normalized):
        return [], ["current_eval_metadata argv entries must be non-empty strings"]
    return normalized, []


def _heuristic_argv(
    *,
    residual_runtime_integration_available: bool,
    heuristic_branch_argv: Any,
) -> tuple[list[str] | None, list[str]]:
    if not residual_runtime_integration_available:
        return None, []
    if (
        not isinstance(heuristic_branch_argv, Sequence)
        or isinstance(heuristic_branch_argv, (str, bytes))
        or len(heuristic_branch_argv) == 0
    ):
        return None, [
            "heuristic_branch_argv must be explicit when residual runtime integration is available"
        ]
    normalized = [str(item) for item in heuristic_branch_argv]
    if not all(item for item in normalized):
        return None, ["heuristic_branch_argv entries must be non-empty strings"]
    return normalized, []


def _artifact_inputs(artifacts: Any) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(artifacts, Mapping):
        return {}, ["predicted_ab_artifacts must be a mapping"]
    summary = {
        "status": str(artifacts.get("status", "")),
        "results_root": _path_string(artifacts.get("results_root")),
        "artifact_files": _string_list(artifacts.get("artifact_files", [])),
        "branch_statuses": dict(artifacts.get("branch_statuses", {}))
        if isinstance(artifacts.get("branch_statuses"), Mapping)
        else {},
    }
    errors: list[str] = []
    if summary["status"] != "present":
        errors.append("predicted_ab_artifacts status must be present")
    if not summary["results_root"]:
        errors.append("predicted_ab_artifacts must include results_root")
    if not summary["artifact_files"]:
        errors.append("predicted_ab_artifacts must include artifact_files")
    return summary, errors


def _argv_with_output_dir(argv: Sequence[str], output_dir: str) -> list[str]:
    normalized = [str(item) for item in argv]
    if "--output-dir" not in normalized:
        return [*normalized, "--output-dir", output_dir]
    index = normalized.index("--output-dir")
    if index == len(normalized) - 1:
        return [*normalized, output_dir]
    updated = list(normalized)
    updated[index + 1] = output_dir
    return updated


def _config_path(argv: Sequence[str]) -> str | None:
    normalized = [str(item) for item in argv]
    if "--config" in normalized:
        index = normalized.index("--config")
        if index < len(normalized) - 1:
            return normalized[index + 1]
    if "-c" in normalized:
        index = normalized.index("-c")
        if index < len(normalized) - 1:
            return normalized[index + 1]
    return None


def _no_overwrite_validation(
    *,
    planned_results_root: str | None,
    protected_evidence_roots: Sequence[str],
) -> dict[str, Any]:
    if planned_results_root is None:
        return {
            "status": "invalid_planned_results_root",
            "planned_results_root": planned_results_root,
            "protected_evidence_roots": list(protected_evidence_roots),
            "validation_errors": [
                "planned_results_root must be a non-empty path string"
            ],
        }
    root_path = _resolve_path(planned_results_root)
    protected_paths = [_resolve_path(path) for path in protected_evidence_roots]
    overlaps = [
        str(path)
        for path in protected_paths
        if _same_or_nested(root_path, path)
    ]
    if overlaps:
        return {
            "status": "protected_evidence_root_overlap",
            "planned_results_root": planned_results_root,
            "protected_evidence_roots": list(protected_evidence_roots),
            "overlapping_protected_roots": overlaps,
            "validation_errors": [
                "planned_results_root must not equal or nest under a protected evidence root"
            ],
        }
    return {
        "status": "present",
        "planned_results_root": planned_results_root,
        "protected_evidence_roots": list(protected_evidence_roots),
        "overlapping_protected_roots": [],
        "validation_errors": [],
    }


def _same_or_nested(child: Path, parent: Path) -> bool:
    return child == parent or parent in child.parents


def _resolve_path(path: str) -> Path:
    raw_path = Path(path)
    if not raw_path.is_absolute():
        raw_path = Path.cwd() / raw_path
    return raw_path.resolve(strict=False)


def _path_string(value: Any) -> str | None:
    if not isinstance(value, (str, Path)):
        return None
    text = str(value)
    if not text:
        return None
    return text


def _string_list(values: Any) -> list[str]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return []
    return [str(value) for value in values if str(value)]


def _join_path(root: str, child: str) -> str:
    return str(Path(root) / child)


def _non_goal_statuses() -> dict[str, str]:
    return {
        "simulation_status": "not_run_by_plan_builder",
        "artifact_write_status": "not_written_by_plan_builder",
        "production_planner_integration_status": "not_integrated_by_plan_builder",
        "rollout_review_schema_integration_status": "not_integrated",
        "runtime_action_status": "not_created",
        "pass_fail_status": "not_defined",
        "eval_success_status": "not_defined",
        "planner_success_status": "not_defined",
        "official_threshold_status": "not_defined",
        "calibrated_model_fallback_status": "not_invented",
    }


def _provenance_statuses(status: str) -> dict[str, str]:
    return {
        "current_eval_metadata_status": (
            "validated" if status == "present" else "not_validated"
        ),
        "predicted_artifact_status": (
            "validated" if status == "present" else "not_validated"
        ),
        "command_plan_status": "built" if status == "present" else "not_built",
    }
