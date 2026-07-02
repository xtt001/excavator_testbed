from __future__ import annotations

import json
from pathlib import Path

from testbed.data.operator_first_v2_2 import DIG_CUT_TOKEN_DIM
from testbed.eval.terrain_residual_ab_artifact_writer import (
    write_predicted_residual_ab_artifacts,
)
from testbed.planner.primitive.token.residual_cut_intent_source import (
    RESIDUAL_CUT_INTENT_RUNTIME_SOURCE_SCHEMA,
    build_residual_cut_intent_plan_provider_from_source_path,
)


EXPECTED_FILES = [
    "eval_run_metadata.json",
    "experiment_manifest.json",
    "branch_run_plan.json",
    "predicted_b_rollout.json",
    "residual_cut_intent_runtime_source.json",
    "branch_comparison_report.json",
    "rollout_manifest.json",
]


def _manifest(results_root: str = "runs/eval/phase6f/results") -> dict[str, object]:
    return {
        "status": "present",
        "schema": "terrain_residual_closed_loop_experiment_manifest_v1",
        "source": "explicit_closed_loop_experiment_manifest",
        "offline_only": True,
        "branch_order": [
            "current_planner_baseline",
            "heuristic_residual_pipeline",
            "calibrated_residual_pipeline",
        ],
        "artifact_layout": {
            "results_root": results_root,
            "expected_artifact_files": EXPECTED_FILES,
            "artifact_count": len(EXPECTED_FILES),
            "writes_files": False,
        },
        "no_overwrite_validation": {
            "status": "present",
            "protected_evidence_roots": ["runs/eval/protected/results"],
            "overlap_detected": False,
        },
        "target_spec": {
            "target_id": "t1_large_shallow_rectangular_pit",
            "grid_shape": [3, 2],
            "row_start": 0,
            "row_end": 2,
            "col_start": 0,
            "col_end": 1,
            "target_depth_m": 0.25,
            "official_semantics": "non_official_explicit_smoke_spec",
        },
        "validation_errors": [],
    }


def _branch_run_plan() -> dict[str, object]:
    return {
        "status": "present",
        "schema": "terrain_residual_closed_loop_branch_run_plan_v1",
        "source": "explicit_closed_loop_branch_run_plan",
        "offline_only": True,
        "branch_order": [
            "current_planner_baseline",
            "heuristic_residual_pipeline",
            "calibrated_residual_pipeline",
        ],
        "branch_run_plans": {
            "current_planner_baseline": {
                "status": "present",
                "run_status": "not_run",
            },
            "heuristic_residual_pipeline": {
                "status": "present",
                "runtime_integration_status": "not_integrated",
                "run_status": "not_run",
            },
            "calibrated_residual_pipeline": {
                "status": "not_evaluated",
                "reason": "blocked_by_missing_gold_samples",
                "run_status": "not_run",
            },
        },
        "validation_errors": [],
    }


def _predicted_rollout() -> dict[str, object]:
    return {
        "status": "present",
        "schema": "terrain_residual_predicted_rollout_v1",
        "source": "explicit_predicted_residual_rollout",
        "offline_only": True,
        "step_count": 1,
        "stop_reason": "zero_target_positive_residual",
        "per_step_records": [
            {
                "step_index": 0,
                "cut_intent_candidate_id": "cut_candidate_000009",
                "expected_delta_depth_sum_m": 0.575955156237,
                "expected_delta_volume_m3": 0.035997197265,
            }
        ],
        "validation_errors": [],
    }


def _raw_fields(entry_x_m: float = 0.25) -> dict[str, float | int]:
    return {
        "operator_entry_x_m": entry_x_m,
        "operator_entry_y_m": 0.0,
        "operator_entry_z_m": 0.0,
        "operator_exit_x_m": entry_x_m,
        "operator_exit_y_m": 0.0,
        "operator_exit_z_m": 0.5,
        "operator_cut_direction_x": 0.0,
        "operator_cut_direction_y": 0.0,
        "operator_cut_direction_z": 1.0,
        "operator_cut_length_m": 0.5,
        "operator_cut_depth_peak_m": 0.2,
        "operator_cut_payload_gain_kg": 12.0,
        "operator_effective_deposit_delta_kg": 12.0,
        "operator_cut_valid": 1,
    }


def _runtime_source() -> dict[str, object]:
    return {
        "schema": RESIDUAL_CUT_INTENT_RUNTIME_SOURCE_SCHEMA,
        "source": "explicit_residual_cut_intent_runtime_source",
        "status": "present",
        "offline_only": True,
        "plans": [
            {
                "cycle_index": 0,
                "cut_intent_candidate_id": "cut_candidate_000009",
                "plan": {
                    "schema": "residual_cut_intent_dig_cut_token_v1",
                    "source": "explicit_residual_cut_intent_dig_cut_token",
                    "status": "present",
                    "offline_only": True,
                    "candidate_id": "cut_candidate_000009",
                    "raw_fields": _raw_fields(),
                    "dig_cut_tokens": [0.25] * DIG_CUT_TOKEN_DIM,
                    "validation_errors": [],
                },
            },
        ],
        "validation_errors": [],
    }


def _comparison() -> dict[str, object]:
    return {
        "status": "present",
        "schema": "terrain_residual_predicted_ab_comparison_v1",
        "source": "explicit_predicted_residual_ab_comparison",
        "offline_only": True,
        "branch_order": [
            "current_planner_baseline",
            "heuristic_residual_pipeline",
            "calibrated_residual_pipeline",
        ],
        "branches": {
            "current_planner_baseline": {
                "status": "present",
                "evidence_type": "current_rollout_evidence",
            },
            "heuristic_residual_pipeline": {
                "status": "present",
                "evidence_type": "predicted_counterfactual",
                "step_count": 1,
                "stop_reason": "zero_target_positive_residual",
                "cut_intent_candidate_ids": ["cut_candidate_000009"],
                "aggregate_delta_summary": {
                    "target_positive_residual_improvement_m": 0.374313589186,
                    "target_removed_completion_ratio_delta": 0.748627178372,
                    "target_overdig_depth_increase_m": 0.009656514972,
                    "outside_target_removed_depth_increase_m": 0.191985052079,
                    "expected_delta_depth_sum_m": 0.575955156237,
                    "expected_delta_volume_m3": 0.035997197265,
                },
            },
            "calibrated_residual_pipeline": {
                "status": "not_evaluated",
                "reason": "blocked_by_missing_gold_samples",
                "usable_gold_sample_count": 0,
                "usable_extracted_record_count": 0,
            },
        },
        "validation_errors": [],
    }


def _write_artifacts(**overrides):
    kwargs = {
        "results_root": "runs/eval/phase6f/results",
        "experiment_manifest": _manifest(),
        "branch_run_plan": _branch_run_plan(),
        "predicted_b_rollout": _predicted_rollout(),
        "residual_cut_intent_runtime_source": _runtime_source(),
        "predicted_ab_comparison": _comparison(),
        "source_rollout_path": "runs/eval/source/results/rollouts/rollout_000.jsonl",
        "protected_evidence_roots": ["runs/eval/protected/results"],
    }
    kwargs.update(overrides)
    return write_predicted_residual_ab_artifacts(**kwargs)


def _all_keys(value):
    if isinstance(value, dict):
        for key, nested_value in value.items():
            yield key
            yield from _all_keys(nested_value)
    elif isinstance(value, list):
        for nested_value in value:
            yield from _all_keys(nested_value)


def test_artifact_writer_materializes_predicted_ab_json_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = _write_artifacts()

    assert result["status"] == "present"
    assert result["schema"] == "terrain_residual_predicted_ab_artifacts_v1"
    assert result["source"] == "explicit_predicted_residual_ab_artifact_writer"
    assert result["offline_only"] is True
    assert result["results_root"] == "runs/eval/phase6f/results"
    assert result["written_files"] == EXPECTED_FILES
    assert result["artifact_count"] == 7
    assert result["source_rollout_path"] == (
        "runs/eval/source/results/rollouts/rollout_000.jsonl"
    )
    assert result["branch_statuses"] == {
        "current_planner_baseline": "present",
        "heuristic_residual_pipeline": "present",
        "calibrated_residual_pipeline": "not_evaluated",
    }
    assert result["no_overwrite_validation"] == {
        "status": "present",
        "protected_evidence_roots": ["runs/eval/protected/results"],
        "overlap_detected": False,
        "results_root_preexisting": False,
    }
    assert result["validation_errors"] == []
    assert result["non_goal_statuses"] == {
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
    assert result["provenance_statuses"]["artifact_write_status"] == "written"

    root = tmp_path / "runs/eval/phase6f/results"
    assert sorted(path.name for path in root.iterdir()) == sorted(EXPECTED_FILES)
    for relative_path in EXPECTED_FILES:
        payload = (root / relative_path).read_text(encoding="utf-8")
        assert payload.endswith("\n")
        parsed = json.loads(payload)
        assert isinstance(parsed, dict)

    metadata = json.loads((root / "eval_run_metadata.json").read_text())
    assert metadata["schema"] == "terrain_residual_predicted_ab_artifacts_v1"
    assert metadata["artifact_files"] == EXPECTED_FILES
    manifest = json.loads((root / "rollout_manifest.json").read_text())
    assert manifest["artifact_count"] == 7
    assert manifest["branch_statuses"]["calibrated_residual_pipeline"] == (
        "not_evaluated"
    )
    source_provider = build_residual_cut_intent_plan_provider_from_source_path(
        root / "residual_cut_intent_runtime_source.json",
        cycle_index=lambda: 0,
    )
    assert source_provider is not None
    token, raw_fields, source, fallback_reason = source_provider({"id": "obs"})
    assert token.tolist() == [0.25] * DIG_CUT_TOKEN_DIM
    assert raw_fields["operator_cut_valid"] == 1
    assert source == "explicit_residual_cut_intent_dig_cut_token"
    assert fallback_reason == ""

    all_keys = set(_all_keys(result))
    assert "runtime_action" not in all_keys
    assert "command_space_controls" not in all_keys
    assert "pass_fail" not in all_keys
    assert "eval_success" not in all_keys
    assert "planner_success" not in all_keys
    assert "production_readiness" not in all_keys
    assert "calibrated_fallback" not in all_keys


def test_artifact_writer_rejects_overwrite_and_protected_roots(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    protected_result = _write_artifacts(
        results_root="runs/eval/protected/results/phase6f",
    )
    assert protected_result["status"] == "protected_evidence_root_overlap"
    assert protected_result["validation_errors"] == [
        "results_root must not be the same as or nested under a protected evidence root",
    ]
    assert (tmp_path / "runs/eval/protected/results/phase6f").exists() is False

    existing_root = tmp_path / "runs/eval/existing/results"
    existing_root.mkdir(parents=True)
    existing_result = _write_artifacts(results_root="runs/eval/existing/results")
    assert existing_result["status"] == "results_root_already_exists"
    assert existing_result["validation_errors"] == [
        "results_root must not already exist before artifact materialization",
    ]


def test_artifact_writer_validates_evidence_and_paths(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    invalid_evidence = _write_artifacts(predicted_b_rollout={"status": "missing"})
    assert invalid_evidence["status"] == "invalid_evidence"
    assert invalid_evidence["validation_errors"] == [
        "predicted_b_rollout status must be present",
    ]

    escape_path = Path(tmp_path.parent) / "outside-results"
    invalid_root = _write_artifacts(results_root=str(escape_path))
    assert invalid_root["status"] == "invalid_results_root"
    assert invalid_root["validation_errors"] == [
        "results_root must be a relative path or stay under the current repository root",
    ]

    assert escape_path.exists() is False
