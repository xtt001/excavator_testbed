from __future__ import annotations

import json

from testbed.eval.terrain_residual_closed_loop_manifest import (
    build_closed_loop_experiment_manifest,
)


def _target_spec() -> dict[str, object]:
    return {
        "target_id": "t1_large_shallow_rectangular_pit",
        "grid_shape": [3, 2],
        "row_start": 0,
        "row_end": 2,
        "col_start": 0,
        "col_end": 1,
        "target_depth_m": 0.25,
        "official_semantics": "non_official_explicit_smoke_spec",
    }


def _branch_definitions() -> dict[str, dict[str, object]]:
    return {
        "current_planner_baseline": {
            "label": "A",
            "status": "present",
            "source": "current_planner_rollout",
        },
        "heuristic_residual_pipeline": {
            "label": "B",
            "status": "present",
            "runtime_integration_status": "not_integrated",
        },
        "calibrated_residual_pipeline": {
            "label": "C",
            "status": "not_evaluated",
            "reason": "blocked_by_missing_gold_samples",
        },
    }


def _cycle_budget() -> dict[str, object]:
    return {
        "max_cycles": 10,
        "source": "current_10_cycle_baseline",
    }


def _stop_conditions() -> dict[str, object]:
    return {
        "max_cycles": True,
        "target_residual_threshold": "required_before_run",
        "overdig_outside_protected_abort": "required_before_run",
        "no_valid_candidate": True,
        "low_payload_handling": "required_before_run",
        "simulation_runtime_failure": True,
    }


def _expected_metrics() -> list[str]:
    return [
        "positive_residual",
        "overdig",
        "outside_target_removed",
        "outside_protected_removed",
        "target_completion",
        "target_depth_error",
        "payload_fraction",
        "deposited_fraction",
        "low_payload_events",
        "cycle_count",
        "handoff_quality",
        "deposit_quality",
        "cycle_time_available",
    ]


def _expected_artifact_files() -> list[str]:
    return [
        "eval_resolved_config.yaml",
        "eval_run_metadata.json",
        "rollouts/current_planner_baseline/rollout_000.jsonl",
        "rollouts/current_planner_baseline/rollout_000_summary.json",
        "rollouts/current_planner_baseline/rollout_000_planner_trace.json",
        "rollouts/heuristic_residual_pipeline/rollout_000.jsonl",
        "residual_per_cycle_report.json",
        "branch_comparison_report.json",
        "rollout_manifest.json",
    ]


def _build_manifest(**overrides):
    kwargs = {
        "results_root": "runs/eval/oracle_terrain_residual_phase6d_t1_ab_20260702/results",
        "target_spec": _target_spec(),
        "branch_definitions": _branch_definitions(),
        "cycle_budget": _cycle_budget(),
        "stop_conditions": _stop_conditions(),
        "expected_metric_names": _expected_metrics(),
        "expected_artifact_files": _expected_artifact_files(),
        "protected_evidence_roots": [
            "runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results"
        ],
        "calibration_available": False,
    }
    kwargs.update(overrides)
    return build_closed_loop_experiment_manifest(**kwargs)


def _all_keys(value):
    if isinstance(value, dict):
        for key, nested_value in value.items():
            yield key
            yield from _all_keys(nested_value)
    elif isinstance(value, list):
        for nested_value in value:
            yield from _all_keys(nested_value)


def test_closed_loop_experiment_manifest_records_phase6d_t1_ab_contract() -> None:
    manifest = _build_manifest()

    assert manifest["status"] == "present"
    assert manifest["schema"] == "terrain_residual_closed_loop_experiment_manifest_v1"
    assert manifest["source"] == "explicit_closed_loop_experiment_manifest"
    assert manifest["offline_only"] is True
    assert manifest["profile"] == "phase6d_t1_ab_closed_loop_manifest"
    assert manifest["branch_order"] == [
        "current_planner_baseline",
        "heuristic_residual_pipeline",
        "calibrated_residual_pipeline",
    ]
    assert manifest["target_spec"] == _target_spec()
    assert manifest["artifact_layout"] == {
        "results_root": (
            "runs/eval/oracle_terrain_residual_phase6d_t1_ab_20260702/results"
        ),
        "expected_artifact_files": _expected_artifact_files(),
        "artifact_count": 9,
        "writes_files": False,
    }
    assert manifest["no_overwrite_validation"] == {
        "status": "present",
        "protected_evidence_roots": [
            "runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results"
        ],
        "overlap_detected": False,
    }
    assert manifest["cycle_budget"] == _cycle_budget()
    assert manifest["stop_condition_summary"] == _stop_conditions()
    assert manifest["expected_metric_names"] == _expected_metrics()
    assert manifest["validation_errors"] == []
    assert manifest["non_goal_statuses"] == {
        "simulation_status": "not_run",
        "run_artifact_status": "not_created",
        "production_planner_integration_status": "not_integrated",
        "rollout_review_schema_integration_status": "not_integrated",
        "official_success_semantics_status": "not_defined",
        "official_default_status": "not_defined",
        "runtime_action_selection_status": "not_defined",
        "calibrated_model_fallback_status": "not_invented",
    }

    all_keys = set(_all_keys(manifest))
    assert "selected_candidate_id" not in all_keys
    assert "top_k" not in all_keys
    assert "runtime_action" not in all_keys
    assert "eval_success" not in all_keys
    assert "planner_success" not in all_keys
    assert "pass_fail" not in all_keys
    serialized = json.dumps(manifest, sort_keys=True)
    assert "current_planner_baseline" in serialized
    assert "heuristic_residual_pipeline" in serialized


def test_closed_loop_experiment_manifest_keeps_calibrated_branch_not_evaluated() -> None:
    manifest = _build_manifest()

    calibrated = manifest["branches"]["calibrated_residual_pipeline"]
    assert calibrated == {
        "branch_name": "calibrated_residual_pipeline",
        "label": "C",
        "status": "not_evaluated",
        "reason": "blocked_by_missing_gold_samples",
        "calibration_available": False,
    }


def test_closed_loop_experiment_manifest_rejects_protected_evidence_root_overlap() -> None:
    protected_root = (
        "runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results"
    )
    manifest = _build_manifest(results_root=f"{protected_root}/phase6e_attempt")

    assert manifest["status"] == "protected_evidence_root_overlap"
    assert manifest["no_overwrite_validation"]["status"] == (
        "protected_evidence_root_overlap"
    )
    assert manifest["no_overwrite_validation"]["overlap_detected"] is True
    assert manifest["validation_errors"] == [
        "results_root must not be the same as or nested under a protected evidence root",
    ]


def test_closed_loop_experiment_manifest_validates_artifact_paths_and_required_inputs() -> None:
    artifact_result = _build_manifest(
        expected_artifact_files=[
            "rollouts/current_planner_baseline/rollout_000.jsonl",
            "/tmp/escape.json",
            "../escape.json",
        ],
    )

    assert artifact_result["status"] == "invalid_artifact_layout"
    assert artifact_result["validation_errors"] == [
        "expected_artifact_files must be relative paths that stay under results_root",
    ]

    target_result = _build_manifest(target_spec={"grid_shape": [3, 2]})
    assert target_result["status"] == "invalid_target_spec"
    assert target_result["validation_errors"] == [
        "target_spec must include grid_shape, row_start, row_end, col_start, col_end, target_depth_m, and official_semantics",
    ]

    branch_result = _build_manifest(branch_definitions={})
    assert branch_result["status"] == "invalid_branch_definitions"
    assert branch_result["validation_errors"] == [
        "branch_definitions must include current_planner_baseline, heuristic_residual_pipeline, and calibrated_residual_pipeline",
    ]


def test_closed_loop_experiment_manifest_does_not_create_future_results_root(
    tmp_path,
) -> None:
    future_results = tmp_path / "phase6e" / "results"
    manifest = _build_manifest(results_root=str(future_results))

    assert manifest["status"] == "present"
    assert future_results.exists() is False
