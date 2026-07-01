import json

from testbed.eval.terrain_residual_baseline_comparison import (
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
