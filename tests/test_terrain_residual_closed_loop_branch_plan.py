from __future__ import annotations

import json

from testbed.eval.terrain_residual_closed_loop_branch_plan import (
    build_closed_loop_branch_run_plan,
)
from testbed.eval.terrain_residual_closed_loop_manifest import (
    build_closed_loop_experiment_manifest,
)


def _manifest(**overrides):
    kwargs = {
        "results_root": "runs/eval/oracle_terrain_residual_phase6d_t1_ab_20260702/results",
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
        "branch_definitions": {
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
        },
        "cycle_budget": {"max_cycles": 10, "source": "current_10_cycle_baseline"},
        "stop_conditions": {
            "max_cycles": True,
            "target_residual_threshold": "required_before_run",
            "overdig_outside_protected_abort": "required_before_run",
            "no_valid_candidate": True,
            "low_payload_handling": "required_before_run",
            "simulation_runtime_failure": True,
        },
        "expected_metric_names": [
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
        ],
        "expected_artifact_files": [
            "eval_resolved_config.yaml",
            "eval_run_metadata.json",
            "rollouts/current_planner_baseline/rollout_000.jsonl",
            "rollouts/current_planner_baseline/rollout_000_summary.json",
            "rollouts/current_planner_baseline/rollout_000_planner_trace.json",
            "rollouts/heuristic_residual_pipeline/rollout_000.jsonl",
            "residual_per_cycle_report.json",
            "branch_comparison_report.json",
            "rollout_manifest.json",
        ],
        "protected_evidence_roots": [
            "runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results"
        ],
        "calibration_available": False,
    }
    kwargs.update(overrides)
    return build_closed_loop_experiment_manifest(**kwargs)


def _branch_inputs() -> dict[str, dict[str, object]]:
    return {
        "current_planner_baseline": {
            "status": "present",
            "source_evidence_status": "present",
            "artifact_expectation_status": "manifest_defined",
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
            "status": "not_evaluated",
            "reason": "blocked_by_missing_gold_samples",
            "calibration_available": False,
        },
    }


def _cut_intent_contract() -> dict[str, object]:
    required_fields = [
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
    return {
        "status": "present",
        "required_fields": required_fields,
        "source_statuses": {
            field: "required_before_runner" for field in required_fields
        },
    }


def _build_plan(**overrides):
    kwargs = {
        "experiment_manifest": _manifest(),
        "branch_inputs": _branch_inputs(),
        "cut_intent_contract": _cut_intent_contract(),
    }
    kwargs.update(overrides)
    return build_closed_loop_branch_run_plan(**kwargs)


def _all_keys(value):
    if isinstance(value, dict):
        for key, nested_value in value.items():
            yield key
            yield from _all_keys(nested_value)
    elif isinstance(value, list):
        for nested_value in value:
            yield from _all_keys(nested_value)


def test_branch_run_plan_records_dry_run_plans_and_cut_intent_boundary() -> None:
    plan = _build_plan()

    assert plan["status"] == "present"
    assert plan["schema"] == "terrain_residual_closed_loop_branch_run_plan_v1"
    assert plan["source"] == "explicit_closed_loop_branch_run_plan"
    assert plan["offline_only"] is True
    assert plan["profile"] == "phase6e_branch_run_plan_contract"
    assert plan["branch_order"] == [
        "current_planner_baseline",
        "heuristic_residual_pipeline",
        "calibrated_residual_pipeline",
    ]
    assert plan["branch_run_plans"]["current_planner_baseline"] == {
        "branch_name": "current_planner_baseline",
        "label": "A",
        "status": "present",
        "plan_status": "dry_run_plan_only",
        "source_evidence_status": "present",
        "artifact_expectation_status": "manifest_defined",
        "expected_artifact_files": [
            "rollouts/current_planner_baseline/rollout_000.jsonl",
            "rollouts/current_planner_baseline/rollout_000_summary.json",
            "rollouts/current_planner_baseline/rollout_000_planner_trace.json",
        ],
        "run_status": "not_run",
    }
    assert plan["branch_run_plans"]["heuristic_residual_pipeline"] == {
        "branch_name": "heuristic_residual_pipeline",
        "label": "B",
        "status": "present",
        "plan_status": "dry_run_plan_only",
        "input_readiness_status": "present",
        "runtime_integration_status": "not_integrated",
        "cut_intent_boundary_status": "present",
        "run_status": "not_run",
        "production_readiness_claim": "not_claimed",
    }
    assert plan["executable_cut_intent_boundary"] == {
        "status": "present",
        "semantics": "future_runner_contract_only",
        "required_fields": _cut_intent_contract()["required_fields"],
        "source_statuses": _cut_intent_contract()["source_statuses"],
        "missing_required_fields": [],
        "emits_selected_candidate": False,
        "emits_top_k": False,
        "emits_runtime_action": False,
        "runtime_integration_status": "not_integrated",
    }
    assert plan["validation_errors"] == []
    assert plan["non_goal_statuses"] == {
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

    all_keys = set(_all_keys(plan))
    assert "selected_candidate_id" not in all_keys
    assert "top_k" not in all_keys
    assert "runtime_action" not in all_keys
    assert "eval_success" not in all_keys
    assert "planner_success" not in all_keys
    assert "pass_fail" not in all_keys
    assert "production_ready" not in all_keys
    serialized = json.dumps(plan, sort_keys=True)
    assert "candidate_id" in serialized
    assert "future_runner_contract_only" in serialized


def test_branch_run_plan_keeps_calibrated_branch_blocked_without_calibration() -> None:
    plan = _build_plan()

    assert plan["branch_run_plans"]["calibrated_residual_pipeline"] == {
        "branch_name": "calibrated_residual_pipeline",
        "label": "C",
        "status": "not_evaluated",
        "reason": "blocked_by_missing_gold_samples",
        "calibration_available": False,
        "run_status": "not_run",
    }


def test_branch_run_plan_validates_manifest_shape() -> None:
    invalid_manifest = dict(_manifest())
    invalid_manifest["status"] = "protected_evidence_root_overlap"

    plan = _build_plan(experiment_manifest=invalid_manifest)

    assert plan["status"] == "invalid_manifest"
    assert plan["validation_errors"] == [
        "experiment_manifest must be present with expected branch order, artifact layout, and no-overwrite validation",
    ]


def test_branch_run_plan_validates_branch_inputs() -> None:
    branch_inputs = _branch_inputs()
    del branch_inputs["heuristic_residual_pipeline"]

    plan = _build_plan(branch_inputs=branch_inputs)

    assert plan["status"] == "invalid_branch_inputs"
    assert plan["validation_errors"] == [
        "branch_inputs must include current_planner_baseline, heuristic_residual_pipeline, and calibrated_residual_pipeline",
    ]


def test_branch_run_plan_validates_cut_intent_contract() -> None:
    contract = _cut_intent_contract()
    contract["required_fields"] = ["candidate_id", "direction"]

    plan = _build_plan(cut_intent_contract=contract)

    assert plan["status"] == "invalid_cut_intent_contract"
    assert plan["executable_cut_intent_boundary"]["missing_required_fields"] == [
        "anchor_cell_index",
        "anchor_col",
        "anchor_row",
        "candidate_depth_m",
        "effect_evidence_provenance",
        "safety_stop_condition_provenance",
        "score_rank_provenance",
        "target_spec_provenance",
    ]
    assert plan["validation_errors"] == [
        "cut_intent_contract must include all required future executable cut-intent fields",
    ]
