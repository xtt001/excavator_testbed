from __future__ import annotations

import pytest

from testbed.eval.act_temporal_ab_validation import (
    TemporalABValidationError,
    evaluate_temporal_ab_candidate,
)


def _record(reset_id: str) -> dict[str, object]:
    return {
        "schema": "act_functional_10cycle_validation_v1",
        "status": "passed",
        "reset_id": reset_id,
        "completed_cycle_count": 10,
        "cycles": [{"cycle_index": index} for index in range(10)],
        "terminal_return_ready_step": 1000,
        "terminal_neutral_ack_step": 1001,
        "wall_contact_count": 0,
        "stuck_count": 0,
        "timeout_count": 0,
        "hard_bottom_event_count": 0,
        "hard_bottom_events": [],
        "diagnostics": {},
    }


BASELINE_METRICS = {
    "entry_error_mean_m": 0.20,
    "exit_error_mean_m": 0.40,
    "local_depth_abs_error_mean_m": 0.10,
    "payload_bonus_mean_kg": 55.0,
    "deposited_fraction_mean": 0.80,
}
CANDIDATE_METRICS = {
    "entry_error_mean_m": 0.17,
    "exit_error_mean_m": 0.36,
    "local_depth_abs_error_mean_m": 0.092,
    "payload_bonus_mean_kg": 54.0,
    "deposited_fraction_mean": 0.75,
}


def test_a1_single_reset_pass_is_only_eligible_for_3x10() -> None:
    result = evaluate_temporal_ab_candidate(
        candidate_name="A1",
        predecessor_temporal_contract={
            "window": 100,
            "weight_order": "legacy_oldest_first",
            "decay": 0.01,
        },
        candidate_temporal_contract={
            "window": 20,
            "weight_order": "legacy_oldest_first",
            "decay": 0.01,
        },
        baseline_metrics=BASELINE_METRICS,
        candidate_metrics=CANDIDATE_METRICS,
        functional_records=[_record("a1-reset-0")],
    )

    assert result["status"] == "eligible_for_3x10"
    assert result["changed_factor"] == "window"
    assert result["tracking_combined_improvement_fraction"] >= 0.10
    assert result["functional_bundle_replacement"] is False


def test_a2_three_reset_pass_can_replace_functional_bundle() -> None:
    result = evaluate_temporal_ab_candidate(
        candidate_name="A2",
        predecessor_temporal_contract={
            "window": 20,
            "weight_order": "legacy_oldest_first",
            "decay": 0.01,
        },
        candidate_temporal_contract={
            "window": 20,
            "weight_order": "newest_first",
            "decay": 0.01,
        },
        baseline_metrics=BASELINE_METRICS,
        candidate_metrics=CANDIDATE_METRICS,
        functional_records=[_record(f"a2-reset-{index}") for index in range(3)],
    )

    assert result["status"] == "accepted_functional_bundle_replacement"
    assert result["changed_factor"] == "weight_order"
    assert result["functional_bundle_replacement"] is True


@pytest.mark.parametrize(
    ("candidate_contract", "candidate_metrics", "reason"),
    [
        (
            {
                "window": 20,
                "weight_order": "newest_first",
                "decay": 0.01,
            },
            CANDIDATE_METRICS,
            "one_factor_at_a_time",
        ),
        (
            {
                "window": 20,
                "weight_order": "legacy_oldest_first",
                "decay": 0.01,
            },
            {
                **CANDIDATE_METRICS,
                "entry_error_mean_m": 0.23,
            },
            "tracking_metric_worsened_over_10pct",
        ),
        (
            {
                "window": 20,
                "weight_order": "legacy_oldest_first",
                "decay": 0.01,
            },
            {
                **CANDIDATE_METRICS,
                "payload_bonus_mean_kg": 48.0,
            },
            "transport_metric_worsened_over_10pct",
        ),
    ],
)
def test_temporal_ab_rejects_contract_or_promotion_regression(
    candidate_contract: dict[str, object],
    candidate_metrics: dict[str, float],
    reason: str,
) -> None:
    with pytest.raises(TemporalABValidationError, match=reason):
        evaluate_temporal_ab_candidate(
            candidate_name="A1",
            predecessor_temporal_contract={
                "window": 100,
                "weight_order": "legacy_oldest_first",
                "decay": 0.01,
            },
            candidate_temporal_contract=candidate_contract,
            baseline_metrics=BASELINE_METRICS,
            candidate_metrics=candidate_metrics,
            functional_records=[_record("a1-reset-0")],
        )


def test_temporal_ab_rejects_failed_ten_cycle_record() -> None:
    record = _record("failed")
    record["timeout_count"] = 1

    with pytest.raises(
        TemporalABValidationError,
        match="functional_record_failed",
    ):
        evaluate_temporal_ab_candidate(
            candidate_name="A1",
            predecessor_temporal_contract={
                "window": 100,
                "weight_order": "legacy_oldest_first",
                "decay": 0.01,
            },
            candidate_temporal_contract={
                "window": 20,
                "weight_order": "legacy_oldest_first",
                "decay": 0.01,
            },
            baseline_metrics=BASELINE_METRICS,
            candidate_metrics=CANDIDATE_METRICS,
            functional_records=[record],
        )
