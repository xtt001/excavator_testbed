from __future__ import annotations

from testbed.eval.terrain_residual_contract import (
    OFFICIAL_PASS_FAIL_PROFILE_ID,
    get_official_terrain_residual_target_spec,
    official_contract_statuses,
    list_official_terrain_residual_target_specs,
    evaluate_cycle_quality_against_baseline,
)


def _quality_summary(**overrides: object) -> dict[str, object]:
    summary: dict[str, object] = {
        "target_cycle_gate_success": 1,
        "target_cycle_completed_dump_count": 2,
        "transition_timeout_count": 0,
        "latest_target_positive_residual_depth_sum_m": 0.895146647118,
        "latest_target_overdig_depth_sum_m": 0.0,
        "latest_outside_target_removed_depth_sum_m": 0.0,
        "deposited_fraction_mean": 0.804524348062,
        "depth_abs_error_m_mean": 0.035039126873,
    }
    summary.update(overrides)
    return summary


def test_official_terrain_residual_targets_define_t1_and_t2() -> None:
    targets = list_official_terrain_residual_target_specs()

    assert targets["schema"] == "terrain_residual_target_v1"
    assert targets["source"] == "official_terrain_residual_target_contract"
    assert targets["status"] == "present"
    assert [target["target_id"] for target in targets["targets"]] == [
        "t1_large_shallow_rectangular_pit_default",
        "t2_long_shallow_trench_default",
    ]

    t1 = get_official_terrain_residual_target_spec(
        "t1_large_shallow_rectangular_pit_default"
    )
    t2 = get_official_terrain_residual_target_spec(
        "t2_long_shallow_trench_default"
    )

    assert t1 == {
        "target_id": "t1_large_shallow_rectangular_pit_default",
        "schema": "terrain_residual_target_v1",
        "source": "official_terrain_residual_target_contract",
        "official_semantics": "official_phase6_v0_default",
        "grid_shape": [3, 2],
        "row_start": 0,
        "row_end": 2,
        "col_start": 0,
        "col_end": 2,
        "target_depth_m": 0.25,
        "profile": "official_phase6_v0_t1_large_shallow_rectangular_pit",
    }
    assert t2["grid_shape"] == [3, 2]
    assert t2["row_start"] == 0
    assert t2["row_end"] == 3
    assert t2["col_start"] == 0
    assert t2["col_end"] == 1
    assert t2["target_depth_m"] == 0.25


def test_official_contract_statuses_are_single_source_of_truth() -> None:
    assert official_contract_statuses() == {
        "official_success_semantics_status": "defined_by_terrain_residual_pass_fail_v1",
        "official_default_status": "defined_by_terrain_residual_target_v1",
        "official_threshold_status": "defined_by_a_baseline_anchored_v0",
        "calibrated_model_fallback_status": "not_invented",
    }


def test_a_baseline_anchored_pass_fail_passes_baseline_and_fails_worse_b() -> None:
    baseline = _quality_summary()
    b_branch = _quality_summary(
        latest_target_positive_residual_depth_sum_m=0.90853878684,
        deposited_fraction_mean=0.7219475943,
        depth_abs_error_m_mean=0.223569767177,
    )

    baseline_result = evaluate_cycle_quality_against_baseline(
        candidate_summary=baseline,
        baseline_summary=baseline,
        target_id="t1_large_shallow_rectangular_pit_default",
    )
    b_result = evaluate_cycle_quality_against_baseline(
        candidate_summary=b_branch,
        baseline_summary=baseline,
        target_id="t1_large_shallow_rectangular_pit_default",
    )

    assert baseline_result["status"] == "present"
    assert baseline_result["profile"] == OFFICIAL_PASS_FAIL_PROFILE_ID
    assert baseline_result["pass"] is True
    assert baseline_result["failed_checks"] == []

    assert b_result["status"] == "present"
    assert b_result["pass"] is False
    assert b_result["failed_checks"] == [
        "target_positive_residual_worse_than_baseline",
        "deposited_fraction_below_baseline",
        "depth_abs_error_above_baseline",
    ]
    assert b_result["comparison_basis"] == "not_worse_than_current_A_gate2_baseline"


def test_pass_fail_blocks_missing_required_quality_fields() -> None:
    result = evaluate_cycle_quality_against_baseline(
        candidate_summary={"target_cycle_gate_success": 1},
        baseline_summary=_quality_summary(),
        target_id="t1_large_shallow_rectangular_pit_default",
    )

    assert result["status"] == "missing_required_fields"
    assert "candidate.target_cycle_completed_dump_count" in result["validation_errors"]
