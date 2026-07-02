"""Eval-only pipeline for materialized predicted A/B residual artifacts."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from testbed.eval.terrain_residual_ab_artifact_writer import (
    ARTIFACT_FILES,
    write_predicted_residual_ab_artifacts,
)
from testbed.eval.terrain_residual_baseline_comparison import (
    build_predicted_residual_ab_comparison,
)
from testbed.eval.terrain_residual_cut_intent_runtime_source import (
    build_residual_cut_intent_runtime_source,
)
from testbed.eval.terrain_residual_closed_loop_branch_plan import (
    REQUIRED_CUT_INTENT_FIELDS,
    build_closed_loop_branch_run_plan,
)
from testbed.eval.terrain_residual_closed_loop_manifest import (
    build_closed_loop_experiment_manifest,
)
from testbed.eval.terrain_residual_predicted_rollout import (
    build_predicted_residual_rollout,
)
from testbed.eval.terrain_target_report import (
    build_explicit_target_residual_baseline_report,
)


SCHEMA = "terrain_residual_predicted_ab_artifact_pipeline_v1"
SOURCE = "explicit_predicted_residual_ab_artifact_pipeline"
DEFAULT_PROFILE = "phase6f_predicted_ab_artifact_pipeline"
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
EXPECTED_METRIC_NAMES = [
    "target_positive_residual_depth_sum_m",
    "target_overdig_depth_sum_m",
    "outside_target_removed_depth_sum_m",
    "target_removed_completion_ratio",
    "expected_delta_depth_sum_m",
    "expected_delta_volume_m3",
]
STOP_CONDITIONS = {
    "max_cycles": "explicit_cycle_budget",
    "target_residual_zero": "diagnostic_stop_only",
    "no_valid_candidate": "diagnostic_stop_only",
    "low_payload": "not_defined_for_pipeline",
    "simulation_failure": "not_applicable_no_simulation",
}


def build_and_write_predicted_residual_ab_artifacts(
    *,
    source_rollout_path: Any,
    results_root: Any,
    target_spec: Mapping[str, Any],
    cycle_budget: Mapping[str, Any],
    candidate_generation_options: Mapping[str, Any],
    candidate_constraint_options: Mapping[str, Any],
    scoring_weights: Mapping[str, Any],
    effect_geometry: Mapping[str, Any],
    payload_capacity_m3: Any,
    residual_cut_intent_runtime_source_inputs: Mapping[str, Any],
    selection_policy: Any,
    protected_evidence_roots: Sequence[Any],
    calibration_evidence: Mapping[str, Any] | None = None,
    profile: str = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Build current-vs-predicted residual evidence and write JSON artifacts."""

    normalized_source_path = _path_string(source_rollout_path)
    normalized_results_root = _path_string(results_root)
    normalized_protected_roots = _string_list(protected_evidence_roots)

    source_records, source_status, source_errors = _read_jsonl_records(
        normalized_source_path
    )
    if source_status != "present":
        return _pipeline_result(
            status="invalid_source_rollout",
            profile=profile,
            source_rollout_path=normalized_source_path,
            results_root=normalized_results_root,
            source_record_count=0,
            nested_statuses={"source_rollout": source_status},
            artifact_writer={},
            predicted_b_rollout={},
            predicted_ab_comparison={},
            validation_errors=source_errors,
        )

    normalized_target_spec, target_errors = _normalize_target_spec(target_spec)
    if target_errors:
        return _pipeline_result(
            status="invalid_target_spec",
            profile=profile,
            source_rollout_path=normalized_source_path,
            results_root=normalized_results_root,
            source_record_count=len(source_records),
            nested_statuses={"source_rollout": "present"},
            artifact_writer={},
            predicted_b_rollout={},
            predicted_ab_comparison={},
            validation_errors=target_errors,
        )

    option_error = _pipeline_option_error(
        cycle_budget=cycle_budget,
        candidate_generation_options=candidate_generation_options,
        candidate_constraint_options=candidate_constraint_options,
        scoring_weights=scoring_weights,
        effect_geometry=effect_geometry,
        payload_capacity_m3=payload_capacity_m3,
        selection_policy=selection_policy,
    )
    if option_error is not None:
        return _pipeline_result(
            status="invalid_pipeline_options",
            profile=profile,
            source_rollout_path=normalized_source_path,
            results_root=normalized_results_root,
            source_record_count=len(source_records),
            nested_statuses={
                "source_rollout": "present",
                "predicted_b_rollout": option_error["status"],
            },
            artifact_writer={},
            predicted_b_rollout={},
            predicted_ab_comparison={},
            validation_errors=option_error["validation_errors"],
        )

    target_report = build_explicit_target_residual_baseline_report(
        source_records,
        grid_shape=normalized_target_spec["grid_shape"],
        row_start=normalized_target_spec["row_start"],
        row_end=normalized_target_spec["row_end"],
        col_start=normalized_target_spec["col_start"],
        col_end=normalized_target_spec["col_end"],
        target_depth_m=normalized_target_spec["target_depth_m"],
        profile=str(normalized_target_spec["official_semantics"]),
    )
    if target_report.get("status") != "present":
        return _pipeline_result(
            status="invalid_source_rollout",
            profile=profile,
            source_rollout_path=normalized_source_path,
            results_root=normalized_results_root,
            source_record_count=len(source_records),
            nested_statuses={
                "source_rollout": "present",
                "target_residual_report": str(target_report.get("status")),
            },
            artifact_writer={},
            predicted_b_rollout={},
            predicted_ab_comparison={},
            validation_errors=list(target_report.get("validation_errors", []))
            or ["target residual report status must be present"],
        )

    calibration = _calibration_evidence(calibration_evidence)
    calibration_available = _calibration_available(calibration)
    experiment_manifest = build_closed_loop_experiment_manifest(
        results_root=normalized_results_root,
        target_spec=normalized_target_spec,
        branch_definitions=_branch_definitions(calibration_available),
        cycle_budget=cycle_budget,
        stop_conditions=STOP_CONDITIONS,
        expected_metric_names=EXPECTED_METRIC_NAMES,
        expected_artifact_files=ARTIFACT_FILES,
        protected_evidence_roots=normalized_protected_roots,
        calibration_available=calibration_available,
    )
    branch_run_plan = build_closed_loop_branch_run_plan(
        experiment_manifest=experiment_manifest,
        branch_inputs=_branch_inputs(calibration_available),
        cut_intent_contract=_cut_intent_contract(),
    )
    pre_rollout_status = _pre_rollout_blocking_status(
        experiment_manifest=experiment_manifest,
        branch_run_plan=branch_run_plan,
    )
    if pre_rollout_status is not None:
        return _pipeline_result(
            status=pre_rollout_status,
            profile=profile,
            source_rollout_path=normalized_source_path,
            results_root=normalized_results_root,
            source_record_count=len(source_records),
            nested_statuses=_nested_statuses(
                target_report=target_report,
                experiment_manifest=experiment_manifest,
                branch_run_plan=branch_run_plan,
                predicted_b_rollout={},
                predicted_ab_comparison={},
                artifact_writer={},
            ),
            artifact_writer={},
            predicted_b_rollout={},
            predicted_ab_comparison={},
            validation_errors=_combined_validation_errors(
                experiment_manifest, branch_run_plan
            ),
        )

    latest_projection = _mapping(target_report.get("latest_projection"))
    target_grid = _mapping(latest_projection.get("target_grid"))
    predicted_b_rollout = build_predicted_residual_rollout(
        branch_run_plan=branch_run_plan,
        initial_removed_depth_grid_m=_sequence_value(
            latest_projection.get("removed_depth_grid_m")
        ),
        target_depth_grid_m=_sequence_value(target_grid.get("target_depth_grid_m")),
        target_region_mask=_sequence_value(target_grid.get("target_region_mask")),
        valid_mask=_sequence_value(latest_projection.get("valid_mask")),
        grid_shape=normalized_target_spec["grid_shape"],
        target_spec=normalized_target_spec,
        cycle_budget=cycle_budget,
        candidate_generation_options=candidate_generation_options,
        candidate_constraint_options=candidate_constraint_options,
        scoring_weights=scoring_weights,
        effect_geometry=effect_geometry,
        payload_capacity_m3=payload_capacity_m3,
        selection_policy=selection_policy,
    )
    if predicted_b_rollout.get("status") != "present":
        return _pipeline_result(
            status="invalid_pipeline_options",
            profile=profile,
            source_rollout_path=normalized_source_path,
            results_root=normalized_results_root,
            source_record_count=len(source_records),
            nested_statuses=_nested_statuses(
                target_report=target_report,
                experiment_manifest=experiment_manifest,
                branch_run_plan=branch_run_plan,
                predicted_b_rollout=predicted_b_rollout,
                residual_cut_intent_runtime_source={},
                predicted_ab_comparison={},
                artifact_writer={},
            ),
            artifact_writer={},
            predicted_b_rollout=predicted_b_rollout,
            predicted_ab_comparison={},
            validation_errors=list(predicted_b_rollout.get("validation_errors", []))
            or ["predicted B rollout status must be present"],
        )

    residual_cut_intent_runtime_source = build_residual_cut_intent_runtime_source(
        predicted_b_rollout=predicted_b_rollout,
        runtime_source_inputs=residual_cut_intent_runtime_source_inputs,
    )
    if residual_cut_intent_runtime_source.get("status") != "present":
        return _pipeline_result(
            status="invalid_runtime_source_inputs",
            profile=profile,
            source_rollout_path=normalized_source_path,
            results_root=normalized_results_root,
            source_record_count=len(source_records),
            nested_statuses=_nested_statuses(
                target_report=target_report,
                experiment_manifest=experiment_manifest,
                branch_run_plan=branch_run_plan,
                predicted_b_rollout=predicted_b_rollout,
                residual_cut_intent_runtime_source=residual_cut_intent_runtime_source,
                predicted_ab_comparison={},
                artifact_writer={},
            ),
            artifact_writer={},
            predicted_b_rollout=predicted_b_rollout,
            predicted_ab_comparison={},
            validation_errors=list(
                residual_cut_intent_runtime_source.get("validation_errors", [])
            )
            or ["residual cut-intent runtime source status must be present"],
        )

    predicted_ab_comparison = build_predicted_residual_ab_comparison(
        current_planner_evidence=_current_planner_evidence(
            source_record_count=len(source_records),
            cycle_budget=cycle_budget,
        ),
        target_residual_report=target_report,
        predicted_b_rollout=predicted_b_rollout,
        calibrated_branch_evidence=calibration,
    )
    if predicted_ab_comparison.get("status") != "present":
        return _pipeline_result(
            status=str(predicted_ab_comparison.get("status", "invalid_evidence")),
            profile=profile,
            source_rollout_path=normalized_source_path,
            results_root=normalized_results_root,
            source_record_count=len(source_records),
            nested_statuses=_nested_statuses(
                target_report=target_report,
                experiment_manifest=experiment_manifest,
                branch_run_plan=branch_run_plan,
                predicted_b_rollout=predicted_b_rollout,
                residual_cut_intent_runtime_source=residual_cut_intent_runtime_source,
                predicted_ab_comparison=predicted_ab_comparison,
                artifact_writer={},
            ),
            artifact_writer={},
            predicted_b_rollout=predicted_b_rollout,
            predicted_ab_comparison=predicted_ab_comparison,
            validation_errors=list(predicted_ab_comparison.get("validation_errors", [])),
        )

    artifact_writer = write_predicted_residual_ab_artifacts(
        results_root=normalized_results_root,
        experiment_manifest=experiment_manifest,
        branch_run_plan=branch_run_plan,
        predicted_b_rollout=predicted_b_rollout,
        residual_cut_intent_runtime_source=residual_cut_intent_runtime_source,
        predicted_ab_comparison=predicted_ab_comparison,
        source_rollout_path=normalized_source_path,
        protected_evidence_roots=normalized_protected_roots,
    )

    return _pipeline_result(
        status=str(artifact_writer.get("status")),
        profile=profile,
        source_rollout_path=normalized_source_path,
        results_root=normalized_results_root,
        source_record_count=len(source_records),
        nested_statuses=_nested_statuses(
            target_report=target_report,
            experiment_manifest=experiment_manifest,
            branch_run_plan=branch_run_plan,
            predicted_b_rollout=predicted_b_rollout,
            residual_cut_intent_runtime_source=residual_cut_intent_runtime_source,
            predicted_ab_comparison=predicted_ab_comparison,
            artifact_writer=artifact_writer,
        ),
        artifact_writer=artifact_writer,
        predicted_b_rollout=predicted_b_rollout,
        predicted_ab_comparison=predicted_ab_comparison,
        validation_errors=list(artifact_writer.get("validation_errors", [])),
    )


def _pipeline_result(
    *,
    status: str,
    profile: str,
    source_rollout_path: str | None,
    results_root: str | None,
    source_record_count: int,
    nested_statuses: Mapping[str, Any],
    artifact_writer: Mapping[str, Any],
    predicted_b_rollout: Mapping[str, Any],
    predicted_ab_comparison: Mapping[str, Any],
    validation_errors: list[str],
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "source": SOURCE,
        "status": status,
        "offline_only": True,
        "profile": str(profile),
        "source_rollout_path": source_rollout_path,
        "results_root": results_root,
        "source_record_count": int(source_record_count),
        "nested_statuses": dict(nested_statuses),
        "artifact_summary": _artifact_summary(artifact_writer),
        "branch_statuses": _branch_statuses(predicted_ab_comparison, artifact_writer),
        "predicted_b_rollout_summary": _predicted_rollout_summary(
            predicted_b_rollout
        ),
        "comparison_delta_summary": _comparison_delta_summary(
            predicted_ab_comparison
        ),
        "validation_errors": validation_errors,
        "non_goal_statuses": _non_goal_statuses(),
        "provenance_statuses": _provenance_statuses(
            jsonl_read_status="read" if source_record_count > 0 else "not_read",
            artifact_write_status="written" if status == "present" else "not_written",
        ),
    }


def _read_jsonl_records(path: str | None) -> tuple[list[dict[str, Any]], str, list[str]]:
    if path is None:
        return [], "missing", ["source_rollout_path must be a non-empty path string"]
    source_path = Path(path)
    if not source_path.is_absolute():
        source_path = Path.cwd() / source_path
    if not source_path.is_file():
        return [], "missing", ["source_rollout_path must point to an existing JSONL file"]

    records: list[dict[str, Any]] = []
    try:
        with source_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                parsed = json.loads(stripped)
                if not isinstance(parsed, dict):
                    return [], "invalid_records", [
                        f"JSONL line {line_number} must be an object record"
                    ]
                records.append(parsed)
    except (OSError, json.JSONDecodeError) as exc:
        return [], "parse_error", [f"source rollout JSONL read failed: {exc}"]
    if not records:
        return [], "empty", ["source rollout JSONL must contain object records"]
    return records, "present", []


def _normalize_target_spec(target_spec: Any) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(target_spec, Mapping):
        return {}, ["target_spec must be a mapping"]
    normalized = {str(key): value for key, value in target_spec.items()}
    missing = [field for field in TARGET_REQUIRED_FIELDS if field not in normalized]
    if missing:
        return normalized, [f"target_spec missing required fields: {missing}"]
    grid_shape = normalized.get("grid_shape")
    if (
        not isinstance(grid_shape, Sequence)
        or isinstance(grid_shape, (str, bytes))
        or len(grid_shape) != 2
    ):
        return normalized, ["target_spec grid_shape must contain two values"]
    try:
        normalized["grid_shape"] = [int(grid_shape[0]), int(grid_shape[1])]
        normalized["row_start"] = int(normalized["row_start"])
        normalized["row_end"] = int(normalized["row_end"])
        normalized["col_start"] = int(normalized["col_start"])
        normalized["col_end"] = int(normalized["col_end"])
        normalized["target_depth_m"] = float(normalized["target_depth_m"])
    except (TypeError, ValueError):
        return normalized, ["target_spec numeric fields must be finite values"]
    return normalized, []


def _pipeline_option_error(
    *,
    cycle_budget: Any,
    candidate_generation_options: Any,
    candidate_constraint_options: Any,
    scoring_weights: Any,
    effect_geometry: Any,
    payload_capacity_m3: Any,
    selection_policy: Any,
) -> dict[str, Any] | None:
    if not isinstance(cycle_budget, Mapping) or not isinstance(
        cycle_budget.get("max_cycles"), int
    ) or cycle_budget.get("max_cycles") <= 0:
        return {
            "status": "invalid_cycle_budget",
            "validation_errors": ["cycle_budget must include positive integer max_cycles"],
        }
    for label, options in (
        ("candidate_generation_options", candidate_generation_options),
        ("candidate_constraint_options", candidate_constraint_options),
        ("scoring_weights", scoring_weights),
        ("effect_geometry", effect_geometry),
    ):
        if not isinstance(options, Mapping):
            return {
                "status": f"invalid_{label}",
                "validation_errors": [f"{label} must be a mapping"],
            }
    if not isinstance(payload_capacity_m3, (int, float)) or payload_capacity_m3 <= 0:
        return {
            "status": "invalid_payload_capacity",
            "validation_errors": [
                "payload_capacity_m3 must be a finite positive number",
            ],
        }
    if selection_policy != "score_ranking_first":
        return {
            "status": "invalid_selection_policy",
            "validation_errors": [
                "selection_policy must be explicit score_ranking_first",
            ],
        }
    return None


def _branch_definitions(calibration_available: bool) -> dict[str, dict[str, Any]]:
    return {
        "current_planner_baseline": {
            "status": "present",
            "label": "A",
            "evidence_type": "current_rollout_evidence",
        },
        "heuristic_residual_pipeline": {
            "status": "present",
            "label": "B",
            "evidence_type": "predicted_counterfactual",
            "runtime_integration_status": "not_integrated",
        },
        "calibrated_residual_pipeline": {
            "status": "present" if calibration_available else "not_evaluated",
            "label": "C",
            "reason": (
                "calibration_available"
                if calibration_available
                else "blocked_by_missing_gold_samples"
            ),
        },
    }


def _branch_inputs(calibration_available: bool) -> dict[str, dict[str, Any]]:
    return {
        "current_planner_baseline": {
            "status": "present",
            "source_evidence_status": "present",
            "artifact_expectation_status": "present",
        },
        "heuristic_residual_pipeline": {
            "status": "present",
            "candidate_generation_status": "present",
            "candidate_evidence_status": "present",
            "candidate_scoring_status": "present",
            "candidate_effect_summary_status": "present",
            "runtime_integration_status": "not_integrated",
        },
        "calibrated_residual_pipeline": {
            "status": "present" if calibration_available else "not_evaluated",
            "reason": (
                "calibration_available"
                if calibration_available
                else "blocked_by_missing_gold_samples"
            ),
            "calibration_available": calibration_available,
        },
    }


def _cut_intent_contract() -> dict[str, Any]:
    return {
        "status": "present",
        "required_fields": list(REQUIRED_CUT_INTENT_FIELDS),
        "source_statuses": {
            field: "required_future_runner_evidence"
            for field in REQUIRED_CUT_INTENT_FIELDS
        },
    }


def _current_planner_evidence(
    *,
    source_record_count: int,
    cycle_budget: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "status": "present",
        "source": "explicit_source_rollout_jsonl",
        "planned_cycle_count": cycle_budget.get("max_cycles"),
        "actual_cycle_count": source_record_count,
        "payload_summary": None,
    }


def _calibration_evidence(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {str(key): nested for key, nested in value.items()}
    return {
        "status": "present",
        "usable_record_count": 0,
        "usable_extracted_record_count": 0,
        "schema_gap_summary": {
            "usable_record_implication": (
                "no_usable_records_for_explicit_required_fields_and_split_keys"
            ),
        },
    }


def _calibration_available(calibration_evidence: Mapping[str, Any]) -> bool:
    return bool(
        calibration_evidence.get("usable_record_count", 0)
        or calibration_evidence.get("usable_extracted_record_count", 0)
    )


def _nested_statuses(
    *,
    target_report: Mapping[str, Any],
    experiment_manifest: Mapping[str, Any],
    branch_run_plan: Mapping[str, Any],
    predicted_b_rollout: Mapping[str, Any],
    predicted_ab_comparison: Mapping[str, Any],
    artifact_writer: Mapping[str, Any],
    residual_cut_intent_runtime_source: Mapping[str, Any] | None = None,
) -> dict[str, str | None]:
    return {
        "target_residual_report": _status(target_report),
        "experiment_manifest": _status(experiment_manifest),
        "branch_run_plan": _status(branch_run_plan),
        "predicted_b_rollout": _status(predicted_b_rollout),
        "residual_cut_intent_runtime_source": _status(
            residual_cut_intent_runtime_source or {}
        ),
        "predicted_ab_comparison": _status(predicted_ab_comparison),
        "artifact_writer": _status(artifact_writer),
    }


def _pre_rollout_blocking_status(
    *,
    experiment_manifest: Mapping[str, Any],
    branch_run_plan: Mapping[str, Any],
) -> str | None:
    manifest_status = _status(experiment_manifest)
    if manifest_status != "present":
        return manifest_status or "invalid_manifest"
    branch_plan_status = _status(branch_run_plan)
    if branch_plan_status != "present":
        return branch_plan_status or "invalid_branch_run_plan"
    return None


def _combined_validation_errors(*records: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    for record in records:
        record_errors = record.get("validation_errors") if isinstance(record, Mapping) else None
        if isinstance(record_errors, Sequence) and not isinstance(record_errors, (str, bytes)):
            errors.extend(str(error) for error in record_errors)
    return errors


def _artifact_summary(artifact_writer: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": artifact_writer.get("status"),
        "artifact_count": artifact_writer.get("artifact_count", 0),
        "written_files": list(artifact_writer.get("written_files", [])),
        "results_root": artifact_writer.get("results_root"),
    }


def _branch_statuses(
    predicted_ab_comparison: Mapping[str, Any],
    artifact_writer: Mapping[str, Any],
) -> dict[str, str]:
    writer_statuses = artifact_writer.get("branch_statuses")
    if isinstance(writer_statuses, Mapping) and writer_statuses:
        return {str(key): str(value) for key, value in writer_statuses.items()}
    branches = predicted_ab_comparison.get("branches")
    if not isinstance(branches, Mapping):
        return {}
    statuses: dict[str, str] = {}
    for branch_name in BRANCH_ORDER:
        branch = branches.get(branch_name)
        if isinstance(branch, Mapping) and branch.get("status") is not None:
            statuses[branch_name] = str(branch["status"])
    return statuses


def _predicted_rollout_summary(predicted_b_rollout: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": predicted_b_rollout.get("status"),
        "step_count": predicted_b_rollout.get("step_count", 0),
        "stop_reason": predicted_b_rollout.get("stop_reason"),
        "selected_candidate_ids": [
            record.get("cut_intent_candidate_id")
            for record in predicted_b_rollout.get("per_step_records", [])
            if isinstance(record, Mapping)
        ],
    }


def _comparison_delta_summary(predicted_ab_comparison: Mapping[str, Any]) -> dict[str, Any]:
    branches = predicted_ab_comparison.get("branches")
    if not isinstance(branches, Mapping):
        return {}
    heuristic_branch = branches.get("heuristic_residual_pipeline")
    if not isinstance(heuristic_branch, Mapping):
        return {}
    summary = heuristic_branch.get("aggregate_delta_summary")
    if not isinstance(summary, Mapping):
        return {}
    return {str(key): value for key, value in summary.items()}


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


def _provenance_statuses(
    *,
    jsonl_read_status: str,
    artifact_write_status: str,
) -> dict[str, str]:
    return {
        "source_rollout_path_source": "explicit_input",
        "results_root_source": "explicit_input",
        "target_spec_source": "explicit_input",
        "pipeline_options_source": "explicit_input",
        "jsonl_read_status": jsonl_read_status,
        "artifact_write_status": artifact_write_status,
    }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence_value(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else []


def _status(value: Mapping[str, Any]) -> str | None:
    status = value.get("status") if isinstance(value, Mapping) else None
    return str(status) if status is not None else None


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


__all__ = ["build_and_write_predicted_residual_ab_artifacts"]
