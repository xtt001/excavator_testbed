"""Eval-only branch run-plan contract for terrain residual closed-loop experiments."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


SCHEMA = "terrain_residual_closed_loop_branch_run_plan_v1"
SOURCE = "explicit_closed_loop_branch_run_plan"
DEFAULT_PROFILE = "phase6e_branch_run_plan_contract"
BRANCH_ORDER = [
    "current_planner_baseline",
    "heuristic_residual_pipeline",
    "calibrated_residual_pipeline",
]
BRANCH_LABELS = {
    "current_planner_baseline": "A",
    "heuristic_residual_pipeline": "B",
    "calibrated_residual_pipeline": "C",
}
REQUIRED_CUT_INTENT_FIELDS = [
    "candidate_id",
    "anchor_cell_index",
    "anchor_row",
    "anchor_col",
    "direction",
    "candidate_depth_m",
    "score_rank_provenance",
    "effect_evidence_provenance",
    "target_spec_provenance",
    "safety_stop_condition_provenance",
]
MANIFEST_ERROR = (
    "experiment_manifest must be present with expected branch order, artifact layout, "
    "and no-overwrite validation"
)
BRANCH_INPUTS_ERROR = (
    "branch_inputs must include current_planner_baseline, "
    "heuristic_residual_pipeline, and calibrated_residual_pipeline"
)
CUT_INTENT_ERROR = (
    "cut_intent_contract must include all required future executable cut-intent fields"
)


def build_closed_loop_branch_run_plan(
    *,
    experiment_manifest: Mapping[str, Any],
    branch_inputs: Mapping[str, Any],
    cut_intent_contract: Mapping[str, Any],
    profile: str = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Build dry-run branch plans and the future cut-intent boundary contract."""

    manifest_status, manifest_errors = _validate_manifest(experiment_manifest)
    normalized_branch_inputs = _normalize_branch_inputs(branch_inputs)
    branch_status, branch_errors = _validate_branch_inputs(normalized_branch_inputs)
    cut_boundary = _cut_intent_boundary(cut_intent_contract)
    cut_status = cut_boundary["status"]

    validations = [
        (manifest_status, manifest_errors),
        (branch_status, branch_errors),
        (
            cut_status,
            [CUT_INTENT_ERROR] if cut_status != "present" else [],
        ),
    ]
    status, validation_errors = _first_status(validations)

    return {
        "schema": SCHEMA,
        "source": SOURCE,
        "status": status,
        "offline_only": True,
        "profile": str(profile),
        "branch_order": list(BRANCH_ORDER),
        "branch_run_plans": _branch_run_plans(
            experiment_manifest=experiment_manifest,
            branch_inputs=normalized_branch_inputs,
            cut_boundary=cut_boundary,
        ),
        "executable_cut_intent_boundary": cut_boundary,
        "validation_errors": validation_errors,
        "non_goal_statuses": _non_goal_statuses(),
        "provenance_statuses": _provenance_statuses(),
    }


def _validate_manifest(manifest: Mapping[str, Any]) -> tuple[str, list[str]]:
    if not isinstance(manifest, Mapping):
        return "invalid_manifest", [MANIFEST_ERROR]
    if manifest.get("status") != "present":
        return "invalid_manifest", [MANIFEST_ERROR]
    if manifest.get("offline_only") is not True:
        return "invalid_manifest", [MANIFEST_ERROR]
    if manifest.get("branch_order") != BRANCH_ORDER:
        return "invalid_manifest", [MANIFEST_ERROR]
    branches = manifest.get("branches")
    if not isinstance(branches, Mapping) or not all(
        branch_name in branches for branch_name in BRANCH_ORDER
    ):
        return "invalid_manifest", [MANIFEST_ERROR]
    artifact_layout = manifest.get("artifact_layout")
    if (
        not isinstance(artifact_layout, Mapping)
        or artifact_layout.get("writes_files") is not False
        or not isinstance(artifact_layout.get("expected_artifact_files"), Sequence)
    ):
        return "invalid_manifest", [MANIFEST_ERROR]
    no_overwrite_validation = manifest.get("no_overwrite_validation")
    if (
        not isinstance(no_overwrite_validation, Mapping)
        or no_overwrite_validation.get("status") != "present"
        or no_overwrite_validation.get("overlap_detected") is not False
    ):
        return "invalid_manifest", [MANIFEST_ERROR]
    return "present", []


def _normalize_branch_inputs(branch_inputs: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    if not isinstance(branch_inputs, Mapping):
        return {}
    normalized: dict[str, dict[str, Any]] = {}
    for branch_name in BRANCH_ORDER:
        value = branch_inputs.get(branch_name)
        if isinstance(value, Mapping):
            normalized[branch_name] = {str(key): nested for key, nested in value.items()}
    return normalized


def _validate_branch_inputs(
    branch_inputs: Mapping[str, Mapping[str, Any]],
) -> tuple[str, list[str]]:
    if not all(branch_name in branch_inputs for branch_name in BRANCH_ORDER):
        return "invalid_branch_inputs", [BRANCH_INPUTS_ERROR]
    for branch_name in BRANCH_ORDER:
        if not branch_inputs[branch_name].get("status"):
            return "invalid_branch_inputs", [
                f"branch_inputs[{branch_name}] must include status",
            ]
    return "present", []


def _cut_intent_boundary(cut_intent_contract: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(cut_intent_contract, Mapping):
        return _cut_boundary_result(
            status="invalid_cut_intent_contract",
            required_fields=[],
            source_statuses={},
        )

    required_fields = _string_list(cut_intent_contract.get("required_fields"))
    source_statuses = _source_statuses(cut_intent_contract.get("source_statuses"))
    missing_required_fields = sorted(
        field for field in REQUIRED_CUT_INTENT_FIELDS if field not in set(required_fields)
    )
    missing_source_statuses = sorted(
        field for field in REQUIRED_CUT_INTENT_FIELDS if field not in source_statuses
    )
    status = (
        "present"
        if cut_intent_contract.get("status") == "present"
        and not missing_required_fields
        and not missing_source_statuses
        else "invalid_cut_intent_contract"
    )
    return _cut_boundary_result(
        status=status,
        required_fields=required_fields,
        source_statuses=source_statuses,
        missing_required_fields=missing_required_fields,
    )


def _cut_boundary_result(
    *,
    status: str,
    required_fields: list[str],
    source_statuses: dict[str, str],
    missing_required_fields: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "semantics": "future_runner_contract_only",
        "required_fields": required_fields,
        "source_statuses": source_statuses,
        "missing_required_fields": (
            list(missing_required_fields) if missing_required_fields is not None else []
        ),
        "emits_selected_candidate": False,
        "emits_top_k": False,
        "emits_runtime_action": False,
        "runtime_integration_status": "not_integrated",
    }


def _branch_run_plans(
    *,
    experiment_manifest: Mapping[str, Any],
    branch_inputs: Mapping[str, Mapping[str, Any]],
    cut_boundary: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    return {
        "current_planner_baseline": _current_branch_plan(
            experiment_manifest=experiment_manifest,
            branch_input=branch_inputs.get("current_planner_baseline", {}),
        ),
        "heuristic_residual_pipeline": _heuristic_branch_plan(
            branch_input=branch_inputs.get("heuristic_residual_pipeline", {}),
            cut_boundary=cut_boundary,
        ),
        "calibrated_residual_pipeline": _calibrated_branch_plan(
            branch_input=branch_inputs.get("calibrated_residual_pipeline", {}),
            experiment_manifest=experiment_manifest,
        ),
    }


def _current_branch_plan(
    *,
    experiment_manifest: Mapping[str, Any],
    branch_input: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "branch_name": "current_planner_baseline",
        "label": _branch_label(experiment_manifest, "current_planner_baseline"),
        "status": str(branch_input.get("status", "invalid")),
        "plan_status": "dry_run_plan_only",
        "source_evidence_status": str(
            branch_input.get("source_evidence_status", "missing")
        ),
        "artifact_expectation_status": str(
            branch_input.get("artifact_expectation_status", "missing")
        ),
        "expected_artifact_files": _branch_artifacts(
            experiment_manifest,
            "current_planner_baseline",
        ),
        "run_status": "not_run",
    }


def _heuristic_branch_plan(
    *,
    branch_input: Mapping[str, Any],
    cut_boundary: Mapping[str, Any],
) -> dict[str, Any]:
    readiness_status = (
        "present"
        if all(
            branch_input.get(key) == "present"
            for key in (
                "candidate_generation_status",
                "candidate_evidence_status",
                "candidate_scoring_status",
                "candidate_effect_summary_status",
            )
        )
        else "incomplete"
    )
    return {
        "branch_name": "heuristic_residual_pipeline",
        "label": "B",
        "status": str(branch_input.get("status", "invalid")),
        "plan_status": "dry_run_plan_only",
        "input_readiness_status": readiness_status,
        "runtime_integration_status": str(
            branch_input.get("runtime_integration_status", "not_integrated")
        ),
        "cut_intent_boundary_status": str(cut_boundary.get("status")),
        "run_status": "not_run",
        "production_readiness_claim": "not_claimed",
    }


def _calibrated_branch_plan(
    *,
    branch_input: Mapping[str, Any],
    experiment_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    calibration_available = bool(
        branch_input.get(
            "calibration_available",
            _manifest_calibration_available(experiment_manifest),
        )
    )
    if calibration_available:
        status = str(branch_input.get("status", "present"))
        reason = str(branch_input.get("reason", "calibration_available"))
    else:
        status = "not_evaluated"
        reason = "blocked_by_missing_gold_samples"
    return {
        "branch_name": "calibrated_residual_pipeline",
        "label": _branch_label(experiment_manifest, "calibrated_residual_pipeline"),
        "status": status,
        "reason": reason,
        "calibration_available": calibration_available,
        "run_status": "not_run",
    }


def _branch_artifacts(
    experiment_manifest: Mapping[str, Any],
    branch_name: str,
) -> list[str]:
    artifact_layout = experiment_manifest.get("artifact_layout")
    if not isinstance(artifact_layout, Mapping):
        return []
    artifact_files = artifact_layout.get("expected_artifact_files")
    if not isinstance(artifact_files, Sequence) or isinstance(artifact_files, (str, bytes)):
        return []
    return [
        str(path)
        for path in artifact_files
        if isinstance(path, str) and branch_name in path
    ]


def _branch_label(experiment_manifest: Mapping[str, Any], branch_name: str) -> str:
    branches = experiment_manifest.get("branches")
    if isinstance(branches, Mapping):
        branch = branches.get(branch_name)
        if isinstance(branch, Mapping) and branch.get("label"):
            return str(branch["label"])
    return BRANCH_LABELS[branch_name]


def _manifest_calibration_available(experiment_manifest: Mapping[str, Any]) -> bool:
    branches = experiment_manifest.get("branches")
    if not isinstance(branches, Mapping):
        return False
    calibrated = branches.get("calibrated_residual_pipeline")
    return isinstance(calibrated, Mapping) and calibrated.get(
        "calibration_available"
    ) is True


def _first_status(
    validations: Sequence[tuple[str, list[str]]],
) -> tuple[str, list[str]]:
    for status, errors in validations:
        if status != "present":
            return status, errors
    return "present", []


def _string_list(value: Any) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return []
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            return []
        normalized.append(item)
    return normalized


def _source_statuses(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): str(status)
        for key, status in value.items()
        if isinstance(key, str) and key
    }


def _non_goal_statuses() -> dict[str, str]:
    return {
        "simulation_status": "not_run",
        "run_artifact_status": "not_created",
        "branch_output_file_status": "not_created",
        "production_planner_integration_status": "not_integrated",
        "rollout_review_schema_integration_status": "not_integrated",
        "runtime_action_selection_status": "not_defined",
        "official_success_semantics_status": "not_defined",
        "official_default_status": "not_defined",
        "official_threshold_status": "not_defined",
        "calibrated_model_fallback_status": "not_invented",
    }


def _provenance_statuses() -> dict[str, str]:
    return {
        "experiment_manifest_source": "explicit_input",
        "branch_inputs_source": "explicit_input",
        "cut_intent_contract_source": "explicit_input",
        "artifact_write_status": "not_written",
        "runner_execution_status": "not_run",
    }
