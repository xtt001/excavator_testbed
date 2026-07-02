"""Materialize eval-only predicted A/B residual evidence artifacts."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any


SCHEMA = "terrain_residual_predicted_ab_artifacts_v1"
SOURCE = "explicit_predicted_residual_ab_artifact_writer"
DEFAULT_PROFILE = "phase6f_predicted_ab_artifact_materialization"
ARTIFACT_FILES = [
    "eval_run_metadata.json",
    "experiment_manifest.json",
    "branch_run_plan.json",
    "predicted_b_rollout.json",
    "residual_cut_intent_runtime_source.json",
    "branch_comparison_report.json",
    "rollout_manifest.json",
]
BRANCH_ORDER = [
    "current_planner_baseline",
    "heuristic_residual_pipeline",
    "calibrated_residual_pipeline",
]
RESULTS_ROOT_ERROR = (
    "results_root must be a relative path or stay under the current repository root"
)
PROTECTED_ROOT_ERROR = (
    "results_root must not be the same as or nested under a protected evidence root"
)
PREEXISTING_ROOT_ERROR = (
    "results_root must not already exist before artifact materialization"
)


def write_predicted_residual_ab_artifacts(
    *,
    results_root: Any,
    experiment_manifest: Mapping[str, Any],
    branch_run_plan: Mapping[str, Any],
    predicted_b_rollout: Mapping[str, Any],
    residual_cut_intent_runtime_source: Mapping[str, Any],
    predicted_ab_comparison: Mapping[str, Any],
    source_rollout_path: Any,
    protected_evidence_roots: Sequence[Any],
    profile: str = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Write deterministic JSON artifacts for an offline predicted A/B comparison."""

    normalized_results_root = _path_string(results_root)
    normalized_source_rollout_path = _path_string(source_rollout_path)
    normalized_protected_roots = _string_list(protected_evidence_roots)
    branch_statuses = _branch_statuses(predicted_ab_comparison)
    no_overwrite_validation = _no_overwrite_validation(
        results_root=normalized_results_root,
        protected_evidence_roots=normalized_protected_roots,
    )

    if normalized_results_root is None or no_overwrite_validation["status"] == (
        "invalid_results_root"
    ):
        return _result(
            status="invalid_results_root",
            profile=profile,
            results_root=normalized_results_root,
            written_files=[],
            source_rollout_path=normalized_source_rollout_path,
            branch_statuses=branch_statuses,
            no_overwrite_validation=no_overwrite_validation,
            validation_errors=[RESULTS_ROOT_ERROR],
        )
    if no_overwrite_validation["status"] == "protected_evidence_root_overlap":
        return _result(
            status="protected_evidence_root_overlap",
            profile=profile,
            results_root=normalized_results_root,
            written_files=[],
            source_rollout_path=normalized_source_rollout_path,
            branch_statuses=branch_statuses,
            no_overwrite_validation=no_overwrite_validation,
            validation_errors=[PROTECTED_ROOT_ERROR],
        )
    if no_overwrite_validation["status"] == "results_root_already_exists":
        return _result(
            status="results_root_already_exists",
            profile=profile,
            results_root=normalized_results_root,
            written_files=[],
            source_rollout_path=normalized_source_rollout_path,
            branch_statuses=branch_statuses,
            no_overwrite_validation=no_overwrite_validation,
            validation_errors=[PREEXISTING_ROOT_ERROR],
        )

    evidence_error = _evidence_error(
        experiment_manifest=experiment_manifest,
        branch_run_plan=branch_run_plan,
        predicted_b_rollout=predicted_b_rollout,
        residual_cut_intent_runtime_source=residual_cut_intent_runtime_source,
        predicted_ab_comparison=predicted_ab_comparison,
        source_rollout_path=normalized_source_rollout_path,
    )
    if evidence_error is not None:
        return _result(
            status="invalid_evidence",
            profile=profile,
            results_root=normalized_results_root,
            written_files=[],
            source_rollout_path=normalized_source_rollout_path,
            branch_statuses=branch_statuses,
            no_overwrite_validation=no_overwrite_validation,
            validation_errors=[evidence_error],
        )

    artifact_error = _artifact_path_error(ARTIFACT_FILES)
    if artifact_error is not None:
        return _result(
            status="invalid_results_root",
            profile=profile,
            results_root=normalized_results_root,
            written_files=[],
            source_rollout_path=normalized_source_rollout_path,
            branch_statuses=branch_statuses,
            no_overwrite_validation=no_overwrite_validation,
            validation_errors=[artifact_error],
        )

    root_path = _resolved_root(normalized_results_root)
    written_files: list[str] = []
    try:
        root_path.mkdir(parents=True, exist_ok=False)
        payloads = _artifact_payloads(
            profile=profile,
            results_root=normalized_results_root,
            experiment_manifest=experiment_manifest,
            branch_run_plan=branch_run_plan,
            predicted_b_rollout=predicted_b_rollout,
            residual_cut_intent_runtime_source=residual_cut_intent_runtime_source,
            predicted_ab_comparison=predicted_ab_comparison,
            source_rollout_path=normalized_source_rollout_path,
            branch_statuses=branch_statuses,
            no_overwrite_validation=no_overwrite_validation,
        )
        for relative_path in ARTIFACT_FILES:
            _write_json(root_path / relative_path, payloads[relative_path])
            written_files.append(relative_path)
    except FileExistsError:
        return _result(
            status="results_root_already_exists",
            profile=profile,
            results_root=normalized_results_root,
            written_files=written_files,
            source_rollout_path=normalized_source_rollout_path,
            branch_statuses=branch_statuses,
            no_overwrite_validation={
                **no_overwrite_validation,
                "results_root_preexisting": True,
            },
            validation_errors=[PREEXISTING_ROOT_ERROR],
        )
    except OSError as exc:
        return _result(
            status="write_failed",
            profile=profile,
            results_root=normalized_results_root,
            written_files=written_files,
            source_rollout_path=normalized_source_rollout_path,
            branch_statuses=branch_statuses,
            no_overwrite_validation=no_overwrite_validation,
            validation_errors=[f"artifact write failed: {exc}"],
        )

    return _result(
        status="present",
        profile=profile,
        results_root=normalized_results_root,
        written_files=written_files,
        source_rollout_path=normalized_source_rollout_path,
        branch_statuses=branch_statuses,
        no_overwrite_validation=no_overwrite_validation,
        validation_errors=[],
    )


def _artifact_payloads(
    *,
    profile: str,
    results_root: str,
    experiment_manifest: Mapping[str, Any],
    branch_run_plan: Mapping[str, Any],
    predicted_b_rollout: Mapping[str, Any],
    residual_cut_intent_runtime_source: Mapping[str, Any],
    predicted_ab_comparison: Mapping[str, Any],
    source_rollout_path: str,
    branch_statuses: Mapping[str, Any],
    no_overwrite_validation: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    metadata = {
        "schema": SCHEMA,
        "source": SOURCE,
        "status": "present",
        "offline_only": True,
        "profile": str(profile),
        "results_root": results_root,
        "artifact_files": list(ARTIFACT_FILES),
        "artifact_count": len(ARTIFACT_FILES),
        "source_rollout_path": source_rollout_path,
        "branch_statuses": dict(branch_statuses),
        "non_goal_statuses": _non_goal_statuses(),
        "provenance_statuses": _provenance_statuses("written"),
    }
    rollout_manifest = {
        "schema": "terrain_residual_predicted_ab_rollout_manifest_v1",
        "source": SOURCE,
        "status": "present",
        "offline_only": True,
        "results_root": results_root,
        "artifact_files": list(ARTIFACT_FILES),
        "artifact_count": len(ARTIFACT_FILES),
        "source_rollout_path": source_rollout_path,
        "branch_statuses": dict(branch_statuses),
        "comparison_status": predicted_ab_comparison.get("status"),
        "predicted_b_rollout_status": predicted_b_rollout.get("status"),
        "no_overwrite_validation": dict(no_overwrite_validation),
        "non_goal_statuses": _non_goal_statuses(),
    }
    return {
        "eval_run_metadata.json": metadata,
        "experiment_manifest.json": dict(experiment_manifest),
        "branch_run_plan.json": dict(branch_run_plan),
        "predicted_b_rollout.json": dict(predicted_b_rollout),
        "residual_cut_intent_runtime_source.json": dict(
            residual_cut_intent_runtime_source
        ),
        "branch_comparison_report.json": dict(predicted_ab_comparison),
        "rollout_manifest.json": rollout_manifest,
    }


def _result(
    *,
    status: str,
    profile: str,
    results_root: str | None,
    written_files: list[str],
    source_rollout_path: str | None,
    branch_statuses: Mapping[str, Any],
    no_overwrite_validation: Mapping[str, Any],
    validation_errors: list[str],
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "source": SOURCE,
        "status": status,
        "offline_only": True,
        "profile": str(profile),
        "results_root": results_root,
        "written_files": list(written_files),
        "artifact_count": len(written_files),
        "source_rollout_path": source_rollout_path,
        "branch_statuses": dict(branch_statuses),
        "no_overwrite_validation": dict(no_overwrite_validation),
        "validation_errors": validation_errors,
        "non_goal_statuses": _non_goal_statuses(),
        "provenance_statuses": _provenance_statuses(
            "written" if status == "present" else "not_written"
        ),
    }


def _evidence_error(
    *,
    experiment_manifest: Any,
    branch_run_plan: Any,
    predicted_b_rollout: Any,
    residual_cut_intent_runtime_source: Any,
    predicted_ab_comparison: Any,
    source_rollout_path: str | None,
) -> str | None:
    for label, evidence in (
        ("experiment_manifest", experiment_manifest),
        ("branch_run_plan", branch_run_plan),
        ("predicted_b_rollout", predicted_b_rollout),
        (
            "residual_cut_intent_runtime_source",
            residual_cut_intent_runtime_source,
        ),
        ("predicted_ab_comparison", predicted_ab_comparison),
    ):
        if not isinstance(evidence, Mapping) or evidence.get("status") != "present":
            return f"{label} status must be present"
    if not source_rollout_path:
        return "source_rollout_path must be a non-empty path string"

    branches = predicted_ab_comparison.get("branches")
    if not isinstance(branches, Mapping):
        return "predicted_ab_comparison must include branch summaries"
    for branch_name in ("current_planner_baseline", "heuristic_residual_pipeline"):
        branch = branches.get(branch_name)
        if not isinstance(branch, Mapping) or branch.get("status") != "present":
            return f"predicted_ab_comparison {branch_name} status must be present"
    calibrated = branches.get("calibrated_residual_pipeline")
    if not isinstance(calibrated, Mapping):
        return "predicted_ab_comparison calibrated_residual_pipeline must be present"
    if calibrated.get("status") == "not_evaluated":
        if calibrated.get("reason") != "blocked_by_missing_gold_samples":
            return (
                "predicted_ab_comparison calibrated_residual_pipeline not_evaluated "
                "reason must be blocked_by_missing_gold_samples"
            )
    elif calibrated.get("status") != "present":
        return "predicted_ab_comparison calibrated_residual_pipeline status is invalid"
    return None


def _no_overwrite_validation(
    *,
    results_root: str | None,
    protected_evidence_roots: Sequence[str],
) -> dict[str, Any]:
    base = {
        "status": "present",
        "protected_evidence_roots": list(protected_evidence_roots),
        "overlap_detected": False,
        "results_root_preexisting": False,
    }
    if not results_root:
        return {**base, "status": "invalid_results_root"}

    root = _resolved_root(results_root)
    repo_root = Path.cwd().resolve()
    if not _is_same_or_nested(root, repo_root):
        return {**base, "status": "invalid_results_root"}

    protected_roots = [_resolved_root(path) for path in protected_evidence_roots]
    overlap_detected = any(_is_same_or_nested(root, protected) for protected in protected_roots)
    if overlap_detected:
        return {
            **base,
            "status": "protected_evidence_root_overlap",
            "overlap_detected": True,
        }
    if root.exists():
        return {
            **base,
            "status": "results_root_already_exists",
            "results_root_preexisting": True,
        }
    return base


def _branch_statuses(predicted_ab_comparison: Any) -> dict[str, str]:
    statuses: dict[str, str] = {}
    branches = predicted_ab_comparison.get("branches") if isinstance(predicted_ab_comparison, Mapping) else None
    if not isinstance(branches, Mapping):
        return statuses
    for branch_name in BRANCH_ORDER:
        branch = branches.get(branch_name)
        if isinstance(branch, Mapping) and branch.get("status") is not None:
            statuses[branch_name] = str(branch.get("status"))
    return statuses


def _non_goal_statuses() -> dict[str, str]:
    return {
        "simulation_status": "not_run",
        "production_planner_integration_status": "not_integrated",
        "rollout_review_schema_integration_status": "not_integrated",
        "runtime_action_status": "not_created",
        "command_space_control_status": "not_created",
        "official_success_semantics_status": "not_defined",
        "official_default_status": "not_defined",
        "official_threshold_status": "not_defined",
        "calibrated_model_fallback_status": "not_invented",
    }


def _provenance_statuses(artifact_write_status: str) -> dict[str, str]:
    return {
        "results_root_source": "explicit_input",
        "source_rollout_path_source": "explicit_input",
        "experiment_manifest_source": "explicit_input",
        "branch_run_plan_source": "explicit_input",
        "predicted_b_rollout_source": "explicit_input",
        "predicted_ab_comparison_source": "explicit_input",
        "artifact_write_status": artifact_write_status,
    }


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(nested) for key, nested in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(nested) for nested in value]
    if isinstance(value, Path):
        return str(value)
    return value


def _path_string(value: Any) -> str | None:
    if isinstance(value, Path):
        value = str(value)
    if not isinstance(value, str) or not value:
        return None
    return value


def _string_list(value: Sequence[Any]) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return []
    strings: list[str] = []
    for item in value:
        path = _path_string(item)
        if path is not None:
            strings.append(path)
    return strings


def _resolved_root(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return candidate.resolve()


def _is_same_or_nested(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def _artifact_path_error(paths: Sequence[str]) -> str | None:
    if not paths:
        return "artifact file list must not be empty"
    for path in paths:
        pure_path = PurePosixPath(path)
        if pure_path.is_absolute() or ".." in pure_path.parts or not path:
            return "artifact files must be relative paths that stay under results_root"
    return None


__all__ = ["write_predicted_residual_ab_artifacts"]
