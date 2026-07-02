from __future__ import annotations

import json

from testbed.eval.terrain_residual_closed_loop_branch_plan import (
    build_closed_loop_branch_run_plan,
)
from testbed.eval.terrain_residual_closed_loop_manifest import (
    build_closed_loop_experiment_manifest,
)
from testbed.eval.terrain_residual_cut_intent import (
    build_heuristic_residual_cut_intent,
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


def _manifest() -> dict[str, object]:
    return build_closed_loop_experiment_manifest(
        results_root=(
            "runs/eval/oracle_terrain_residual_phase6d_t1_ab_20260702/results"
        ),
        target_spec=_target_spec(),
        branch_definitions={
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
        cycle_budget={"max_cycles": 10, "source": "current_10_cycle_baseline"},
        stop_conditions={
            "max_cycles": True,
            "target_residual_threshold": "required_before_run",
            "overdig_outside_protected_abort": "required_before_run",
            "no_valid_candidate": True,
            "low_payload_handling": "required_before_run",
            "simulation_runtime_failure": True,
        },
        expected_metric_names=["positive_residual", "overdig", "cycle_count"],
        expected_artifact_files=[
            "rollouts/current_planner_baseline/rollout_000.jsonl",
            "rollouts/heuristic_residual_pipeline/rollout_000.jsonl",
            "residual_per_cycle_report.json",
            "branch_comparison_report.json",
            "rollout_manifest.json",
        ],
        protected_evidence_roots=[
            "runs/eval/v2_5_bt_reproduce_aggregate_tx24_20260630_current_fixed_eval_tf32off/results"
        ],
        calibration_available=False,
    )


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


def _branch_run_plan(**overrides) -> dict[str, object]:
    kwargs = {
        "experiment_manifest": _manifest(),
        "branch_inputs": {
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
        },
        "cut_intent_contract": _cut_intent_contract(),
    }
    kwargs.update(overrides)
    return build_closed_loop_branch_run_plan(**kwargs)


def _candidate_generation() -> dict[str, object]:
    return {
        "status": "present",
        "source": "explicit_target_residual_discrete_candidate_generation",
        "offline_only": True,
        "candidate_count": 2,
        "candidates": [
            {
                "candidate_id": "cut_candidate_000009",
                "anchor_cell_index": 4,
                "anchor_row": 2,
                "anchor_col": 0,
                "direction": "col_forward",
                "candidate_depth_m": 0.166666666667,
                "offline_only": True,
            },
            {
                "candidate_id": "cut_candidate_000010",
                "anchor_cell_index": 4,
                "anchor_row": 2,
                "anchor_col": 0,
                "direction": "col_reverse",
                "candidate_depth_m": 0.125,
                "offline_only": True,
            },
        ],
    }


def _candidate_evidence() -> dict[str, object]:
    return {
        "status": "present",
        "source": "explicit_target_candidate_constraint_evidence",
        "offline_only": True,
        "candidate_count": 2,
        "evidence_records": [
            {
                "candidate_id": "cut_candidate_000009",
                "candidate_depth_m": 0.166666666667,
                "offline_only": True,
                "target_footprint_cell_indices": [4],
                "outside_target_footprint_cell_indices": [],
                "outside_protected_boundary_cell_indices": [],
                "depth_budget_status": "within_budget",
                "clipped_by_grid_boundary": False,
                "return_alignment_cost_proxy": {
                    "status": "present",
                    "manhattan_distance_cells": 2,
                },
            },
            {
                "candidate_id": "cut_candidate_000010",
                "candidate_depth_m": 0.125,
                "offline_only": True,
                "target_footprint_cell_indices": [4],
                "outside_target_footprint_cell_indices": [5],
                "outside_protected_boundary_cell_indices": [],
                "depth_budget_status": "within_budget",
                "clipped_by_grid_boundary": False,
                "return_alignment_cost_proxy": {
                    "status": "present",
                    "manhattan_distance_cells": 2,
                },
            },
        ],
    }


def _candidate_scoring() -> dict[str, object]:
    return {
        "status": "present",
        "source": "explicit_candidate_heuristic_score_evidence",
        "offline_only": True,
        "candidate_count": 2,
        "score_records": [
            {
                "candidate_id": "cut_candidate_000009",
                "input_index": 0,
                "offline_only": True,
                "total_score": 4.25,
                "score_components": {
                    "candidate_depth_reward": {"status": "present", "value": 1.666666666667}
                },
            },
            {
                "candidate_id": "cut_candidate_000010",
                "input_index": 1,
                "offline_only": True,
                "total_score": 1.25,
                "score_components": {
                    "candidate_depth_reward": {"status": "present", "value": 1.25}
                },
            },
        ],
        "ranking": {
            "semantics": "diagnostic_offline_ranking_only",
            "no_production_action": True,
            "ranked_candidate_ids": [
                "cut_candidate_000009",
                "cut_candidate_000010",
            ],
            "ranked_candidates": [
                {
                    "rank": 1,
                    "candidate_id": "cut_candidate_000009",
                    "total_score": 4.25,
                    "input_index": 0,
                },
                {
                    "rank": 2,
                    "candidate_id": "cut_candidate_000010",
                    "total_score": 1.25,
                    "input_index": 1,
                },
            ],
        },
    }


def _candidate_effect_summary() -> dict[str, object]:
    return {
        "status": "present",
        "source": "explicit_candidate_effect_summary",
        "offline_only": True,
        "effect_record_count": 2,
        "summary_records": [
            {
                "candidate_id": "cut_candidate_000009",
                "input_index": 0,
                "effect_status": "present",
                "offline_only": True,
                "expected_removed_volume_m3": 0.035997197265,
                "target_removed_volume_m3": 0.035997197265,
                "outside_target_removed_volume_m3": 0.0,
                "overdig_volume_delta_m3": 0.0,
                "footprint_cell_count": 2,
                "footprint_clipped_by_grid_boundary": False,
                "payload_proxy_volume_m3": 0.035997197265,
                "payload_proxy_fraction": 0.899929931625,
            },
            {
                "candidate_id": "cut_candidate_000010",
                "input_index": 1,
                "effect_status": "present",
                "offline_only": True,
                "expected_removed_volume_m3": 0.02,
                "target_removed_volume_m3": 0.015,
                "outside_target_removed_volume_m3": 0.005,
                "overdig_volume_delta_m3": 0.001,
                "footprint_cell_count": 1,
                "footprint_clipped_by_grid_boundary": True,
                "payload_proxy_volume_m3": 0.02,
                "payload_proxy_fraction": 0.5,
            },
        ],
    }


def _build_cut_intent(**overrides) -> dict[str, object]:
    kwargs = {
        "branch_run_plan": _branch_run_plan(),
        "candidate_generation": _candidate_generation(),
        "candidate_evidence": _candidate_evidence(),
        "candidate_scoring": _candidate_scoring(),
        "candidate_effect_summary": _candidate_effect_summary(),
        "target_spec": _target_spec(),
        "selection_policy": "score_ranking_first",
    }
    kwargs.update(overrides)
    return build_heuristic_residual_cut_intent(**kwargs)


def _all_keys(value):
    if isinstance(value, dict):
        for key, nested_value in value.items():
            yield key
            yield from _all_keys(nested_value)
    elif isinstance(value, list):
        for nested_value in value:
            yield from _all_keys(nested_value)


def test_cut_intent_selects_score_ranking_first_candidate_for_eval_harness() -> None:
    result = _build_cut_intent()

    assert result["status"] == "present"
    assert result["schema"] == "terrain_residual_heuristic_cut_intent_v1"
    assert result["source"] == "explicit_heuristic_residual_cut_intent"
    assert result["offline_only"] is True
    assert result["selection_policy"] == "score_ranking_first"
    assert result["b_branch_status"] == {
        "status": "present",
        "input_readiness_status": "present",
        "runtime_integration_status": "not_integrated",
        "cut_intent_boundary_status": "present",
    }
    assert result["cut_intent"] == {
        "cut_intent_candidate_id": "cut_candidate_000009",
        "candidate_id": "cut_candidate_000009",
        "offline_only": True,
        "anchor_cell_index": 4,
        "anchor_row": 2,
        "anchor_col": 0,
        "direction": "col_forward",
        "candidate_depth_m": 0.166666666667,
        "score_rank_provenance": {
            "source": "explicit_candidate_heuristic_score_evidence",
            "selection_policy": "score_ranking_first",
            "rank": 1,
            "total_score": 4.25,
            "input_index": 0,
            "score_record_status": "present",
        },
        "effect_evidence_provenance": {
            "source": "explicit_candidate_effect_summary",
            "effect_status": "present",
            "expected_removed_volume_m3": 0.035997197265,
            "target_removed_volume_m3": 0.035997197265,
            "outside_target_removed_volume_m3": 0.0,
            "overdig_volume_delta_m3": 0.0,
            "payload_proxy_fraction": 0.899929931625,
            "footprint_cell_count": 2,
            "footprint_clipped_by_grid_boundary": False,
        },
        "target_spec_provenance": {
            "source": "explicit_input_target_spec",
            "target_id": "t1_large_shallow_rectangular_pit",
            "grid_shape": [3, 2],
            "row_start": 0,
            "row_end": 2,
            "col_start": 0,
            "col_end": 1,
            "target_depth_m": 0.25,
            "official_semantics": "non_official_explicit_smoke_spec",
        },
        "safety_stop_condition_provenance_status": "from_branch_run_plan_contract",
        "runner_input_status": "ready_for_eval_harness",
        "production_runtime_action": False,
    }
    assert result["validation_errors"] == []
    assert result["non_goal_statuses"]["simulation_status"] == "not_run"
    assert result["non_goal_statuses"]["run_artifact_status"] == "not_created"

    all_keys = set(_all_keys(result))
    assert "selected_candidate_id" not in all_keys
    assert "top_k" not in all_keys
    assert "runtime_action" not in all_keys
    assert "pass_fail" not in all_keys
    assert "eval_success" not in all_keys
    assert "planner_success" not in all_keys
    assert "calibrated_fallback" not in all_keys
    serialized = json.dumps(result, sort_keys=True)
    assert "ready_for_eval_harness" in serialized
    assert "cut_candidate_000009" in serialized


def test_cut_intent_rejects_invalid_branch_plan_and_policy() -> None:
    invalid_plan = dict(_branch_run_plan())
    invalid_plan["status"] = "invalid_manifest"

    assert (
        _build_cut_intent(branch_run_plan=invalid_plan)["status"]
        == "invalid_branch_run_plan"
    )
    assert (
        _build_cut_intent(selection_policy="payload_proxy_first")["status"]
        == "invalid_selection_policy"
    )


def test_cut_intent_cross_checks_selected_candidate_across_evidence_sources() -> None:
    missing_candidate = _candidate_generation()
    missing_candidate["candidates"] = missing_candidate["candidates"][1:]
    assert (
        _build_cut_intent(candidate_generation=missing_candidate)["status"]
        == "invalid_candidate_generation"
    )

    missing_evidence = _candidate_evidence()
    missing_evidence["evidence_records"] = missing_evidence["evidence_records"][1:]
    assert (
        _build_cut_intent(candidate_evidence=missing_evidence)["status"]
        == "invalid_candidate_evidence"
    )

    missing_effect = _candidate_effect_summary()
    missing_effect["summary_records"] = missing_effect["summary_records"][1:]
    assert (
        _build_cut_intent(candidate_effect_summary=missing_effect)["status"]
        == "invalid_candidate_effect_summary"
    )


def test_cut_intent_rejects_invalid_scoring_and_target_spec() -> None:
    invalid_scoring = _candidate_scoring()
    invalid_scoring["ranking"] = {
        "semantics": "diagnostic_offline_ranking_only",
        "no_production_action": True,
        "ranked_candidate_ids": [],
        "ranked_candidates": [],
    }
    assert (
        _build_cut_intent(candidate_scoring=invalid_scoring)["status"]
        == "invalid_candidate_scoring"
    )

    invalid_target_spec = dict(_target_spec())
    del invalid_target_spec["official_semantics"]
    assert (
        _build_cut_intent(target_spec=invalid_target_spec)["status"]
        == "invalid_target_spec"
    )
