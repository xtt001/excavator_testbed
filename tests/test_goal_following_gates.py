from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from testbed.eval.goal_following_gates import (
    BENCHMARK_DECISIONS,
    BoundedLiveConditionEvidence,
    FunctionalCycleEvidence,
    FunctionalG1Evidence,
    GoalFollowingGateEvidence,
    OfflineConditionEvidence,
    SweepConditionEvidence,
    evaluate_act_route,
    evaluate_goal_following_gates,
)


def _offline() -> tuple[OfflineConditionEvidence, ...]:
    return tuple(
        OfflineConditionEvidence(
            condition_id=condition,
            real_handoff_valid=True,
            complete_terrain_signature_valid=True,
            predictor_valid=True,
            calibrated_95_error_bound_valid=True,
            derived_return_envelope_valid=True,
        )
        for condition in ("E0", "G1", "W1")
    )


def _sweep() -> tuple[SweepConditionEvidence, ...]:
    return tuple(
        SweepConditionEvidence(
            condition_id=condition,
            uncertainty_tube_passed=True,
            all_12_link_wall_witnesses_valid=True,
        )
        for condition in ("E0", "G1", "W1")
    )


def _live() -> tuple[BoundedLiveConditionEvidence, ...]:
    return tuple(
        BoundedLiveConditionEvidence(
            condition_id=condition,
            attempt_count=1,
            retry_count=0,
            reset_valid=True,
            reset_fairness_valid=True,
            handoff_valid=True,
            goal_identity_valid=True,
            guard_3d_valid=True,
            tracking_valid=True,
            safety_valid=True,
            median_stop_valid=True,
        )
        for condition in ("E0", "G1", "W1")
    )


def _functional() -> FunctionalG1Evidence:
    return FunctionalG1Evidence(
        condition_id="G1",
        attempt_count=1,
        reset_count=1,
        retry_count=0,
        valid_dig_count=10,
        dump_count=10,
        handoff_count=9,
        median_stop_valid=True,
        cycles=tuple(
            FunctionalCycleEvidence(
                cycle_index=index,
                goal_identity_valid=True,
                guard_3d_valid=True,
                tracking_valid=True,
                safety_valid=True,
            )
            for index in range(10)
        ),
    )


def _all_evidence() -> GoalFollowingGateEvidence:
    return GoalFollowingGateEvidence(
        offline_conditions=_offline(),
        sweep_conditions=_sweep(),
        bounded_live_conditions=_live(),
        functional_g1=_functional(),
    )


def test_act_route_keeps_act_frozen_for_non_tracking_decisions() -> None:
    for decision in BENCHMARK_DECISIONS - {"act_tracking_primary"}:
        route = evaluate_act_route(benchmark_decision=decision)
        assert route.accepted
        assert route.runtime_act_frozen
        assert not route.existing_goal_conditioned_retrain_allowed
        assert not route.trajectory_conditioned_v1_allowed


def test_act_route_requires_existing_retrain_before_trajectory_conditioning() -> None:
    initial = evaluate_act_route(
        benchmark_decision="act_tracking_primary",
    )
    assert initial.accepted
    assert initial.runtime_act_frozen
    assert initial.existing_goal_conditioned_retrain_allowed
    assert not initial.trajectory_conditioned_v1_allowed

    still_outside = evaluate_act_route(
        benchmark_decision="act_tracking_primary",
        existing_goal_conditioned_retrain_completed=True,
        heldout_tracking_within_margin=False,
    )
    assert still_outside.accepted
    assert not still_outside.existing_goal_conditioned_retrain_allowed
    assert still_outside.trajectory_conditioned_v1_allowed

    recovered = evaluate_act_route(
        benchmark_decision="act_tracking_primary",
        existing_goal_conditioned_retrain_completed=True,
        heldout_tracking_within_margin=True,
    )
    assert recovered.accepted
    assert not recovered.existing_goal_conditioned_retrain_allowed
    assert not recovered.trajectory_conditioned_v1_allowed


def test_act_route_rejects_unknown_decision_or_planner_threshold_masking() -> None:
    unknown = evaluate_act_route(benchmark_decision="maybe_act")
    assert not unknown.accepted
    assert unknown.runtime_act_frozen
    assert unknown.reason == "benchmark_decision_invalid"

    masking = evaluate_act_route(
        benchmark_decision="act_tracking_primary",
        planner_threshold_masking_requested=True,
    )
    assert not masking.accepted
    assert masking.runtime_act_frozen
    assert masking.reason == "planner_threshold_masking_forbidden"


def test_four_level_gate_passes_in_strict_order_without_auto_promotion() -> None:
    result = evaluate_goal_following_gates(_all_evidence())

    assert tuple(stage.name for stage in result.stages) == (
        "offline_e0_g1_w1",
        "unity_3d_sweep",
        "bounded_live_e0_g1_w1",
        "g1_single_1x10",
    )
    assert all(stage.status == "passed" for stage in result.stages)
    assert result.promotion_evidence_ready
    assert not result.default_behavior_changed
    assert not result.auto_promotion_allowed


def test_failed_offline_gate_blocks_every_later_gate() -> None:
    evidence = _all_evidence()
    offline = list(evidence.offline_conditions)
    offline[1] = replace(offline[1], predictor_valid=False)
    result = evaluate_goal_following_gates(
        replace(evidence, offline_conditions=tuple(offline))
    )

    assert result.stages[0].status == "failed"
    assert result.stages[0].reasons == ("G1:predictor_invalid",)
    assert all(stage.status == "blocked" for stage in result.stages[1:])
    assert not result.promotion_evidence_ready


def test_bounded_live_is_each_once_with_no_retry_and_complete_evidence() -> None:
    evidence = _all_evidence()
    live = list(evidence.bounded_live_conditions)
    live[2] = replace(live[2], attempt_count=2, retry_count=1)
    result = evaluate_goal_following_gates(
        replace(evidence, bounded_live_conditions=tuple(live))
    )

    assert result.stages[0].status == "passed"
    assert result.stages[1].status == "passed"
    assert result.stages[2].status == "failed"
    assert "W1:attempt_count_not_one" in result.stages[2].reasons
    assert "W1:retry_forbidden" in result.stages[2].reasons
    assert result.stages[3].status == "blocked"


def test_bounded_live_fails_closed_for_reset_fairness_or_handoff() -> None:
    evidence = _all_evidence()
    live = list(evidence.bounded_live_conditions)
    live[1] = replace(
        live[1],
        reset_fairness_valid=False,
        handoff_valid=False,
    )
    result = evaluate_goal_following_gates(
        replace(evidence, bounded_live_conditions=tuple(live))
    )

    assert result.stages[2].status == "failed"
    assert "G1:reset_fairness_invalid" in result.stages[2].reasons
    assert "G1:handoff_invalid" in result.stages[2].reasons
    assert result.stages[3].status == "blocked"


def test_functional_gate_requires_exact_counts_and_per_cycle_evidence() -> None:
    evidence = _all_evidence()
    cycles = list(evidence.functional_g1.cycles)
    cycles[4] = replace(cycles[4], tracking_valid=False)
    invalid_functional = replace(
        evidence.functional_g1,
        dump_count=9,
        handoff_count=8,
        cycles=tuple(cycles),
    )
    result = evaluate_goal_following_gates(
        replace(evidence, functional_g1=invalid_functional)
    )

    assert result.stages[3].status == "failed"
    assert "G1:dump_count_not_10" in result.stages[3].reasons
    assert "G1:handoff_count_not_9" in result.stages[3].reasons
    assert "G1:cycle_4:tracking_invalid" in result.stages[3].reasons
    assert not result.promotion_evidence_ready


def test_gate_rejects_missing_or_duplicate_condition_inventory() -> None:
    evidence = _all_evidence()
    duplicate = (
        evidence.offline_conditions[0],
        evidence.offline_conditions[0],
        evidence.offline_conditions[2],
    )
    result = evaluate_goal_following_gates(
        replace(evidence, offline_conditions=duplicate)
    )

    assert result.stages[0].status == "failed"
    assert result.stages[0].reasons == (
        "condition_inventory_invalid:E0,E0,W1",
    )


@pytest.mark.parametrize(
    "field",
    (
        "real_handoff_valid",
        "complete_terrain_signature_valid",
        "predictor_valid",
        "calibrated_95_error_bound_valid",
        "derived_return_envelope_valid",
    ),
)
def test_offline_validity_fields_require_strict_bool(field: str) -> None:
    evidence = _all_evidence()
    conditions = list(evidence.offline_conditions)
    malformed: Any = 1
    conditions[0] = replace(conditions[0], **{field: malformed})
    result = evaluate_goal_following_gates(
        replace(evidence, offline_conditions=tuple(conditions))
    )

    assert result.stages[0].status == "failed"
    assert f"E0:{field}_type_invalid" in result.stages[0].reasons


@pytest.mark.parametrize(
    "field",
    (
        "uncertainty_tube_passed",
        "all_12_link_wall_witnesses_valid",
    ),
)
def test_sweep_validity_fields_require_strict_bool(field: str) -> None:
    evidence = _all_evidence()
    conditions = list(evidence.sweep_conditions)
    malformed: Any = "true"
    conditions[0] = replace(conditions[0], **{field: malformed})
    result = evaluate_goal_following_gates(
        replace(evidence, sweep_conditions=tuple(conditions))
    )

    assert result.stages[1].status == "failed"
    assert f"E0:{field}_type_invalid" in result.stages[1].reasons


@pytest.mark.parametrize(
    "field",
    (
        "reset_valid",
        "reset_fairness_valid",
        "handoff_valid",
        "goal_identity_valid",
        "guard_3d_valid",
        "tracking_valid",
        "safety_valid",
        "median_stop_valid",
    ),
)
def test_bounded_live_validity_fields_require_strict_bool(
    field: str,
) -> None:
    evidence = _all_evidence()
    conditions = list(evidence.bounded_live_conditions)
    malformed: Any = 1
    conditions[0] = replace(conditions[0], **{field: malformed})
    result = evaluate_goal_following_gates(
        replace(evidence, bounded_live_conditions=tuple(conditions))
    )

    assert result.stages[2].status == "failed"
    assert f"E0:{field}_type_invalid" in result.stages[2].reasons


@pytest.mark.parametrize("field", ("attempt_count", "retry_count"))
@pytest.mark.parametrize("malformed", (True, "1"))
def test_bounded_live_counts_require_strict_int(
    field: str,
    malformed: Any,
) -> None:
    evidence = _all_evidence()
    conditions = list(evidence.bounded_live_conditions)
    conditions[0] = replace(conditions[0], **{field: malformed})
    result = evaluate_goal_following_gates(
        replace(evidence, bounded_live_conditions=tuple(conditions))
    )

    assert result.stages[2].status == "failed"
    assert f"E0:{field}_type_invalid" in result.stages[2].reasons


@pytest.mark.parametrize(
    "field",
    (
        "attempt_count",
        "reset_count",
        "retry_count",
        "valid_dig_count",
        "dump_count",
        "handoff_count",
    ),
)
@pytest.mark.parametrize("malformed", (False, "0"))
def test_functional_counts_require_strict_int(
    field: str,
    malformed: Any,
) -> None:
    evidence = _all_evidence()
    functional = replace(
        evidence.functional_g1,
        **{field: malformed},
    )
    result = evaluate_goal_following_gates(
        replace(evidence, functional_g1=functional)
    )

    assert result.stages[3].status == "failed"
    assert f"G1:{field}_type_invalid" in result.stages[3].reasons


def test_functional_and_cycle_validity_fields_require_strict_bool() -> None:
    evidence = _all_evidence()
    malformed: Any = "yes"
    cycles = list(evidence.functional_g1.cycles)
    cycles[2] = replace(cycles[2], safety_valid=malformed)
    functional = replace(
        evidence.functional_g1,
        median_stop_valid=malformed,
        cycles=tuple(cycles),
    )
    result = evaluate_goal_following_gates(
        replace(evidence, functional_g1=functional)
    )

    assert result.stages[3].status == "failed"
    assert "G1:median_stop_valid_type_invalid" in result.stages[3].reasons
    assert (
        "G1:cycle_2:safety_valid_type_invalid"
        in result.stages[3].reasons
    )


@pytest.mark.parametrize("malformed", (True, "2"))
def test_cycle_index_requires_strict_int_without_raising(
    malformed: Any,
) -> None:
    evidence = _all_evidence()
    cycles = list(evidence.functional_g1.cycles)
    cycles[2] = replace(cycles[2], cycle_index=malformed)
    functional = replace(evidence.functional_g1, cycles=tuple(cycles))

    result = evaluate_goal_following_gates(
        replace(evidence, functional_g1=functional)
    )

    assert result.stages[3].status == "failed"
    assert (
        "G1:cycle_position_2:cycle_index_type_invalid"
        in result.stages[3].reasons
    )
