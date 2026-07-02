import json

from testbed.eval.terrain_residual_baseline_comparison import (
    build_predicted_residual_ab_comparison,
    build_residual_planner_baseline_comparison,
)


def _current_evidence():
    return {
        "status": "present",
        "source": "rollout_review_snapshot",
        "planned_cycle_count": 10,
        "actual_cycle_count": 10,
        "payload_summary": {
            "total_deposited_fraction": 0.91,
        },
    }


def _target_report():
    return {
        "status": "present",
        "diagnostic_summary": {
            "latest_snapshot_row_index": 6147,
            "latest_target_positive_residual_depth_sum_m": 0.374313589186,
            "latest_target_overdig_depth_sum_m": 0.0,
            "latest_target_removed_completion_ratio": 0.251372821628,
            "latest_outside_target_removed_depth_sum_m": 0.488698139786,
            "convergence_summary_status": "present",
            "convergence_point_count": 10,
            "convergence_diagnostic_trend": (
                "target_positive_residual_reduced_outside_removed_increased"
            ),
        },
    }


def _candidate_generation():
    return {
        "status": "present",
        "candidate_count": 24,
        "positive_residual_cell_count": 2,
        "positive_residual_coverage": {
            "status": "present",
            "covered_cell_indices": [0, 2],
        },
    }


def _candidate_evidence():
    return {
        "status": "present",
        "candidate_count": 24,
        "constraint_summary": {
            "over_depth_budget_candidate_count": 0,
            "outside_target_footprint_candidate_count": 12,
        },
    }


def _candidate_scoring():
    return {
        "status": "present",
        "candidate_count": 24,
        "ranking": {
            "ranked_candidate_ids": [
                "cut_candidate_000009",
                "cut_candidate_000001",
            ],
            "ranked_candidates": [
                {
                    "rank": 1,
                    "candidate_id": "cut_candidate_000009",
                    "total_score": 2.0,
                    "input_index": 8,
                },
                {
                    "rank": 2,
                    "candidate_id": "cut_candidate_000001",
                    "total_score": 1.5,
                    "input_index": 0,
                },
            ],
        },
        "score_summary": {
            "best_candidate_id": "cut_candidate_000009",
            "best_score": 2.0,
            "worst_candidate_id": "cut_candidate_000001",
            "worst_score": 1.5,
        },
    }


def _effect_summary():
    return {
        "status": "present",
        "effect_record_count": 24,
        "aggregate_summary": {
            "payload_proxy_fraction_max": 1.0,
            "expected_removed_volume_total_m3": 0.21,
            "target_removed_volume_total_m3": 0.14,
            "outside_target_removed_volume_total_m3": 0.07,
            "overdig_volume_delta_total_m3": 0.03,
            "max_payload_proxy_candidate_id": "cut_candidate_000009",
            "max_outside_target_volume_candidate_id": "cut_candidate_000001",
            "max_overdig_volume_candidate_id": "cut_candidate_000001",
        },
        "diagnostic_rankings": {
            "payload_proxy_desc": [
                {"rank": 1, "candidate_id": "cut_candidate_000009"}
            ],
            "outside_target_volume_desc": [
                {"rank": 1, "candidate_id": "cut_candidate_000001"}
            ],
            "overdig_volume_desc": [
                {"rank": 1, "candidate_id": "cut_candidate_000001"}
            ],
        },
    }


def _predicted_rollout():
    return {
        "status": "present",
        "schema": "terrain_residual_predicted_rollout_v1",
        "source": "explicit_predicted_residual_rollout",
        "offline_only": True,
        "step_count": 1,
        "stop_reason": "zero_target_positive_residual",
        "initial_metrics": {
            "status": "present",
            "target_positive_residual_depth_sum_m": 0.374313589186,
            "target_overdig_depth_sum_m": 0.0,
            "outside_target_removed_depth_sum_m": 0.488698139786,
            "target_removed_completion_ratio": 0.251372821628,
        },
        "final_metrics": {
            "status": "present",
            "target_positive_residual_depth_sum_m": 0.0,
            "target_overdig_depth_sum_m": 0.009656514972,
            "outside_target_removed_depth_sum_m": 0.680683191865,
            "target_removed_completion_ratio": 1.0,
        },
        "per_step_records": [
            {
                "step_index": 0,
                "status": "present",
                "cut_intent_candidate_id": "cut_candidate_000009",
                "expected_delta_depth_sum_m": 0.575955156237,
                "expected_delta_volume_m3": 0.035997197265,
            }
        ],
        "aggregate_delta_summary": {
            "target_positive_residual_depth_delta_m": -0.374313589186,
            "target_overdig_depth_delta_m": 0.009656514972,
            "outside_target_removed_depth_delta_m": 0.191985052079,
            "target_removed_completion_ratio_delta": 0.748627178372,
            "expected_delta_depth_sum_m": 0.575955156237,
            "expected_delta_volume_m3": 0.035997197265,
        },
        "validation_errors": [],
    }


def _missing_gold_sample_evidence():
    return {
        "status": "present",
        "usable_record_count": 0,
        "usable_extracted_record_count": 0,
        "schema_gap_summary": {
            "usable_record_implication": (
                "no_usable_records_for_explicit_required_fields_and_split_keys"
            )
        },
    }


def _all_keys(value):
    if isinstance(value, dict):
        for key, nested_value in value.items():
            yield key
            yield from _all_keys(nested_value)
    elif isinstance(value, list):
        for nested_value in value:
            yield from _all_keys(nested_value)


def test_residual_planner_baseline_comparison_reports_three_branches():
    comparison = build_residual_planner_baseline_comparison(
        current_planner_evidence=_current_evidence(),
        target_residual_report=_target_report(),
        candidate_generation=_candidate_generation(),
        candidate_evidence=_candidate_evidence(),
        candidate_scoring=_candidate_scoring(),
        candidate_effect_summary=_effect_summary(),
        calibrated_branch_evidence=_missing_gold_sample_evidence(),
    )

    assert comparison["status"] == "present"
    assert comparison["schema"] == "terrain_residual_planner_baseline_comparison_v1"
    assert comparison["source"] == "explicit_offline_residual_planner_baseline_comparison"
    assert comparison["offline_only"] is True
    assert comparison["branch_order"] == [
        "current_planner_baseline",
        "heuristic_residual_pipeline",
        "calibrated_residual_pipeline",
    ]
    assert comparison["branches"]["current_planner_baseline"] == {
        "branch_name": "current_planner_baseline",
        "status": "present",
        "source_status": "present",
        "rollout_evidence": {
            "planned_cycle_count": 10,
            "actual_cycle_count": 10,
            "payload_summary": {"total_deposited_fraction": 0.91},
        },
        "target_residual_evidence": {
            "report_status": "present",
            "latest_snapshot_row_index": 6147,
            "latest_target_positive_residual_depth_sum_m": 0.374313589186,
            "latest_target_overdig_depth_sum_m": 0.0,
            "latest_outside_target_removed_depth_sum_m": 0.488698139786,
            "convergence_summary_status": "present",
            "convergence_point_count": 10,
            "convergence_diagnostic_trend": (
                "target_positive_residual_reduced_outside_removed_increased"
            ),
        },
        "target_success_claim": "not_claimed",
    }
    assert comparison["branches"]["heuristic_residual_pipeline"] == {
        "branch_name": "heuristic_residual_pipeline",
        "status": "present",
        "candidate_count": 24,
        "positive_residual_cell_count": 2,
        "candidate_coverage_status": "present",
        "constraint_summary": {
            "over_depth_budget_candidate_count": 0,
            "outside_target_footprint_candidate_count": 12,
        },
        "score_summary": {
            "best_candidate_id": "cut_candidate_000009",
            "best_score": 2.0,
            "worst_candidate_id": "cut_candidate_000001",
            "worst_score": 1.5,
        },
        "diagnostic_ranking": {
            "ranked_candidate_ids": [
                "cut_candidate_000009",
                "cut_candidate_000001",
            ],
            "best_candidate_id": "cut_candidate_000009",
        },
        "effect_summary": {
            "effect_record_count": 24,
            "payload_proxy_fraction_max": 1.0,
            "expected_removed_volume_total_m3": 0.21,
            "target_removed_volume_total_m3": 0.14,
            "outside_target_removed_volume_total_m3": 0.07,
            "overdig_volume_delta_total_m3": 0.03,
            "max_payload_proxy_candidate_id": "cut_candidate_000009",
            "max_outside_target_volume_candidate_id": "cut_candidate_000001",
            "max_overdig_volume_candidate_id": "cut_candidate_000001",
        },
        "closed_loop_proof_status": "not_run",
    }
    assert comparison["branches"]["calibrated_residual_pipeline"] == {
        "branch_name": "calibrated_residual_pipeline",
        "status": "not_evaluated",
        "reason": "blocked_by_missing_gold_samples",
        "usable_gold_sample_count": 0,
        "usable_extracted_record_count": 0,
        "schema_gap_implication": (
            "no_usable_records_for_explicit_required_fields_and_split_keys"
        ),
    }
    assert comparison["comparison_limits"] == {
        "closed_loop_resimulation_status": "not_run",
        "counterfactual_cycle_count_status": "not_available",
        "cycle_time_status": "not_available",
        "production_integration_status": "not_integrated",
        "official_success_semantics_status": "not_defined",
        "calibrated_model_fallback_status": "not_invented",
    }
    all_keys = set(_all_keys(comparison))
    assert "selected_candidate_id" not in all_keys
    assert "action" not in all_keys
    assert "top_k" not in all_keys
    assert "pass_fail_status" not in all_keys
    serialized = json.dumps(comparison, sort_keys=True)
    assert "target_success_claim" in serialized


def test_residual_planner_baseline_comparison_requires_current_branch_evidence():
    comparison = build_residual_planner_baseline_comparison(
        current_planner_evidence={"status": "missing"},
        target_residual_report=_target_report(),
        candidate_generation=_candidate_generation(),
        candidate_evidence=_candidate_evidence(),
        candidate_scoring=_candidate_scoring(),
        candidate_effect_summary=_effect_summary(),
        calibrated_branch_evidence=_missing_gold_sample_evidence(),
    )

    assert comparison["status"] == "invalid_current_planner_evidence"
    assert comparison["branches"]["current_planner_baseline"]["status"] == "invalid"
    assert comparison["validation_errors"]


def test_residual_planner_baseline_comparison_requires_heuristic_evidence():
    comparison = build_residual_planner_baseline_comparison(
        current_planner_evidence=_current_evidence(),
        target_residual_report=_target_report(),
        candidate_generation={"status": "invalid_grid_shape"},
        candidate_evidence=_candidate_evidence(),
        candidate_scoring=_candidate_scoring(),
        candidate_effect_summary=_effect_summary(),
        calibrated_branch_evidence=_missing_gold_sample_evidence(),
    )

    assert comparison["status"] == "invalid_heuristic_evidence"
    assert comparison["branches"]["heuristic_residual_pipeline"]["status"] == "invalid"
    assert comparison["validation_errors"] == [
        "candidate_generation status must be present",
    ]


def test_residual_planner_baseline_comparison_validates_calibrated_evidence():
    comparison = build_residual_planner_baseline_comparison(
        current_planner_evidence=_current_evidence(),
        target_residual_report=_target_report(),
        candidate_generation=_candidate_generation(),
        candidate_evidence=_candidate_evidence(),
        candidate_scoring=_candidate_scoring(),
        candidate_effect_summary=_effect_summary(),
        calibrated_branch_evidence={"status": "present"},
    )

    assert comparison["status"] == "invalid_calibrated_evidence"
    assert comparison["branches"]["calibrated_residual_pipeline"]["status"] == (
        "invalid"
    )
    assert comparison["validation_errors"] == [
        "calibrated branch evidence must include usable gold sample count",
    ]


def test_predicted_residual_ab_comparison_reports_current_and_predicted_branches():
    comparison = build_predicted_residual_ab_comparison(
        current_planner_evidence=_current_evidence(),
        target_residual_report=_target_report(),
        predicted_b_rollout=_predicted_rollout(),
        calibrated_branch_evidence=_missing_gold_sample_evidence(),
    )

    assert comparison["status"] == "present"
    assert comparison["schema"] == "terrain_residual_predicted_ab_comparison_v1"
    assert comparison["source"] == "explicit_predicted_residual_ab_comparison"
    assert comparison["offline_only"] is True
    assert comparison["branch_order"] == [
        "current_planner_baseline",
        "heuristic_residual_pipeline",
        "calibrated_residual_pipeline",
    ]
    assert comparison["branches"]["current_planner_baseline"] == {
        "branch_name": "current_planner_baseline",
        "status": "present",
        "evidence_type": "current_rollout_evidence",
        "source_status": "present",
        "rollout_evidence": {
            "planned_cycle_count": 10,
            "actual_cycle_count": 10,
            "payload_summary": {"total_deposited_fraction": 0.91},
        },
        "target_residual_evidence": {
            "report_status": "present",
            "latest_snapshot_row_index": 6147,
            "target_positive_residual_depth_sum_m": 0.374313589186,
            "target_removed_completion_ratio": 0.251372821628,
            "target_overdig_depth_sum_m": 0.0,
            "outside_target_removed_depth_sum_m": 0.488698139786,
        },
        "target_success_claim": "not_claimed",
    }
    assert comparison["branches"]["heuristic_residual_pipeline"] == {
        "branch_name": "heuristic_residual_pipeline",
        "status": "present",
        "evidence_type": "predicted_counterfactual",
        "predicted_rollout_status": "present",
        "step_count": 1,
        "stop_reason": "zero_target_positive_residual",
        "cut_intent_candidate_ids": ["cut_candidate_000009"],
        "initial_metrics": {
            "target_positive_residual_depth_sum_m": 0.374313589186,
            "target_removed_completion_ratio": 0.251372821628,
            "target_overdig_depth_sum_m": 0.0,
            "outside_target_removed_depth_sum_m": 0.488698139786,
        },
        "final_metrics": {
            "target_positive_residual_depth_sum_m": 0.0,
            "target_removed_completion_ratio": 1.0,
            "target_overdig_depth_sum_m": 0.009656514972,
            "outside_target_removed_depth_sum_m": 0.680683191865,
        },
        "aggregate_delta_summary": {
            "target_positive_residual_depth_delta_m": -0.374313589186,
            "target_positive_residual_improvement_m": 0.374313589186,
            "target_removed_completion_ratio_delta": 0.748627178372,
            "target_overdig_depth_increase_m": 0.009656514972,
            "outside_target_removed_depth_increase_m": 0.191985052079,
            "expected_delta_depth_sum_m": 0.575955156237,
            "expected_delta_volume_m3": 0.035997197265,
        },
        "real_simulation_status": "not_run",
        "production_runtime_status": "not_integrated",
    }
    assert comparison["branches"]["calibrated_residual_pipeline"] == {
        "branch_name": "calibrated_residual_pipeline",
        "status": "not_evaluated",
        "reason": "blocked_by_missing_gold_samples",
        "usable_gold_sample_count": 0,
        "usable_extracted_record_count": 0,
        "schema_gap_implication": (
            "no_usable_records_for_explicit_required_fields_and_split_keys"
        ),
    }
    assert comparison["comparison_limits"] == {
        "a_branch_evidence_type": "current_rollout_evidence",
        "b_branch_evidence_type": "predicted_counterfactual",
        "b_real_simulation_status": "not_run",
        "production_integration_status": "not_integrated",
        "official_success_semantics_status": "not_defined",
        "official_threshold_status": "not_defined",
        "calibrated_model_fallback_status": "not_invented",
    }
    assert comparison["validation_errors"] == []

    all_keys = set(_all_keys(comparison))
    assert "runtime_action" not in all_keys
    assert "command_space_controls" not in all_keys
    assert "production_readiness" not in all_keys
    assert "pass_fail" not in all_keys
    assert "eval_success" not in all_keys
    assert "planner_success" not in all_keys
    assert "official_threshold" not in all_keys
    assert "calibrated_fallback" not in all_keys
    serialized = json.dumps(comparison, sort_keys=True)
    assert "predicted_counterfactual" in serialized
    assert "current_rollout_evidence" in serialized


def test_predicted_residual_ab_comparison_validates_current_and_predicted_inputs():
    invalid_current = build_predicted_residual_ab_comparison(
        current_planner_evidence={"status": "missing"},
        target_residual_report=_target_report(),
        predicted_b_rollout=_predicted_rollout(),
        calibrated_branch_evidence=_missing_gold_sample_evidence(),
    )
    assert invalid_current["status"] == "invalid_current_planner_evidence"
    assert invalid_current["validation_errors"] == [
        "current_planner_evidence status must be present",
    ]

    invalid_report = build_predicted_residual_ab_comparison(
        current_planner_evidence=_current_evidence(),
        target_residual_report={"status": "missing"},
        predicted_b_rollout=_predicted_rollout(),
        calibrated_branch_evidence=_missing_gold_sample_evidence(),
    )
    assert invalid_report["status"] == "invalid_current_planner_evidence"
    assert invalid_report["validation_errors"] == [
        "target_residual_report status must be present",
    ]

    invalid_predicted = build_predicted_residual_ab_comparison(
        current_planner_evidence=_current_evidence(),
        target_residual_report=_target_report(),
        predicted_b_rollout={"status": "invalid_branch_run_plan"},
        calibrated_branch_evidence=_missing_gold_sample_evidence(),
    )
    assert invalid_predicted["status"] == "invalid_predicted_rollout_evidence"
    assert invalid_predicted["validation_errors"] == [
        "predicted_b_rollout status must be present",
    ]
