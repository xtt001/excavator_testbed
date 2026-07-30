from __future__ import annotations

import math
from dataclasses import replace

import pytest

from testbed.planner.box_emptying.candidate_planner import (
    BoxEmptyingCandidatePlanner,
    CandidateEffectPrediction,
    CandidatePlannerConfig,
    EffectArtifactContractError,
)
from testbed.planner.box_emptying.contracts import TerrainBoxResidual
from testbed.planner.box_emptying.stop_conditions import (
    BoxEmptyingStopController,
    CycleOutcome,
)


class _Predictor:
    contract_version = "planned_cut_effect_v1"

    def predict(self, candidate, residual):
        cell = candidate.cell_id
        return CandidateEffectPrediction(
            signed_cell_delta_m3=(0.0,) * cell
            + (0.02 + 0.01 * cell,)
            + (0.0,) * (5 - cell),
            payload_kg=30.0 + 10.0 * cell,
            removed_volume_m3=0.02 + 0.01 * cell,
            uncertainty_m3=0.001 * (5 - cell),
        )


def _residual() -> TerrainBoxResidual:
    return TerrainBoxResidual(
        remaining_volume_m3=(0.50, 0.40, 0.30, 0.20, 0.10, 0.10),
        hard_bottom_depth_m=0.60,
        soil_density_kg_m3=1600.0,
        current_remaining_mass_kg=2496.0,
        initial_remaining_mass_kg=3000.0,
        remaining_fraction=0.842,
        valid=True,
    )


def test_candidate_generation_is_six_by_four_by_three() -> None:
    planner = BoxEmptyingCandidatePlanner(
        predictor=_Predictor(),
        config=CandidatePlannerConfig(
            support_envelope={
                "planned_depth_m": [0.05, 0.60],
                "cut_length_m": [0.75, 0.75],
            }
        ),
    )
    candidates = planner.generate_candidates(_residual())

    assert len(candidates) == 72
    assert {candidate.cell_id for candidate in candidates} == set(range(6))
    assert {candidate.direction for candidate in candidates} == {
        "long_forward",
        "long_reverse",
        "short_forward",
        "short_reverse",
    }
    assert {candidate.depth_fraction for candidate in candidates} == {
        0.5,
        0.75,
        1.0,
    }
    assert all(0.05 <= candidate.planned_depth_m <= 0.60 for candidate in candidates)
    assert all(
        candidate.planned_depth_m
        <= candidate.local_remaining_depth_m - 0.02 + 1.0e-12
        for candidate in candidates
    )
    assert all(
        math.hypot(
            candidate.exit_x_m - candidate.entry_x_m,
            candidate.exit_z_m - candidate.entry_z_m,
        )
        == pytest.approx(
            math.sqrt(
                candidate.cut_length_m**2 - candidate.planned_depth_m**2
            )
        )
        for candidate in candidates
    )
    assert all(
        math.hypot(candidate.direction_x, candidate.direction_z)
        == pytest.approx(
            math.sqrt(
                candidate.cut_length_m**2 - candidate.planned_depth_m**2
            )
            / candidate.cut_length_m
        )
        for candidate in candidates
    )


def test_filters_exhausted_blocked_ood_and_known_failures_before_scoring() -> None:
    planner = BoxEmptyingCandidatePlanner(
        predictor=_Predictor(),
        config=CandidatePlannerConfig(
            support_envelope={
                "planned_depth_m": [0.10, 0.40],
                "cut_length_m": [0.75, 0.75],
            },
            blocked_cell_ids=frozenset({1}),
            blocked_corridor_ids=frozenset({"cell2:long_forward"}),
            depth_exhausted_cell_ids=frozenset({3}),
            known_failure_candidate_ids=frozenset(
                {"cell4:short_reverse:depth0.5"}
            ),
        ),
    )
    evaluated = planner.evaluate_candidates(_residual())

    by_id = {item.candidate.candidate_id: item for item in evaluated}
    assert all(
        item.rejection_reason == "blocked_cell"
        for item in evaluated
        if item.candidate.cell_id == 1
    )
    assert all(
        item.rejection_reason == "depth_exhausted_cell"
        for item in evaluated
        if item.candidate.cell_id == 3
    )
    assert by_id["cell2:long_forward:depth0.5"].rejection_reason == "blocked_corridor"
    assert by_id["cell4:short_reverse:depth0.5"].rejection_reason == "known_failure"
    assert any(item.rejection_reason == "outside_support_envelope" for item in evaluated)


def test_strict18_support_still_leaves_a_feasible_candidate_for_every_cell() -> None:
    strict18_support = {
        "planned_depth_m": [0.0867, 0.7438],
        "cut_length_m": [0.3538, 1.5123],
        "entry_x_m": [0.1537, 1.1366],
        "entry_z_m": [-1.4040, 1.0849],
        "exit_x_m": [-0.9422, 1.1638],
        "exit_z_m": [-1.3942, 1.1275],
        "direction_x": [-0.9905, 0.8722],
        "direction_z": [-0.7778, 0.8764],
    }
    initial = replace(
        _residual(),
        remaining_volume_m3=(0.75,) * 6,
    )
    planner = BoxEmptyingCandidatePlanner(
        predictor=_Predictor(),
        config=CandidatePlannerConfig(
            support_envelope=strict18_support,
            long_axis=2,
        ),
    )

    accepted = [
        item.candidate
        for item in planner.evaluate_candidates(initial)
        if not item.rejection_reason
    ]

    assert {candidate.cell_id for candidate in accepted} == set(range(6))
    assert all(planner._wall_footprint_safe(candidate) for candidate in accepted)


def test_selection_uses_lexicographic_lcb_payload_uncertainty_and_cost() -> None:
    planner = BoxEmptyingCandidatePlanner(
        predictor=_Predictor(),
        config=CandidatePlannerConfig(
            support_envelope={
                "planned_depth_m": [0.05, 0.60],
                "cut_length_m": [0.75, 0.75],
            },
            wall_inset_m=0.0,
        ),
    )
    selection = planner.select(_residual())

    assert selection.candidate.cell_id == 5
    assert selection.prediction.payload_bonus_kg == pytest.approx(60.0)
    assert selection.prediction.effective_volume_lcb_m3 > 0.0


def test_missing_or_mismatched_effect_artifact_fails_explicitly() -> None:
    with pytest.raises(EffectArtifactContractError, match="artifact_missing"):
        BoxEmptyingCandidatePlanner(
            predictor=None,
            config=CandidatePlannerConfig(support_envelope={}),
        )

    predictor = _Predictor()
    predictor.contract_version = "executed_cut_effect_v1"
    with pytest.raises(EffectArtifactContractError, match="contract_mismatch"):
        BoxEmptyingCandidatePlanner(
            predictor=predictor,
            config=CandidatePlannerConfig(support_envelope={}),
        )


def test_locked_plan_recomputes_at_most_once_for_terrain_change() -> None:
    planner = BoxEmptyingCandidatePlanner(
        predictor=_Predictor(),
        config=CandidatePlannerConfig(
            support_envelope={
                "planned_depth_m": [0.05, 0.60],
                "cut_length_m": [0.75, 0.75],
            },
            wall_inset_m=0.0,
        ),
    )
    lock = planner.lock_selection(_residual())
    unchanged = planner.validate_locked_selection(lock, _residual())
    assert unchanged is lock

    changed_residual = replace(
        _residual(),
        remaining_volume_m3=(0.503, 0.40, 0.30, 0.20, 0.10, 0.10),
    )
    recomputed = planner.validate_locked_selection(lock, changed_residual)
    assert recomputed.recompute_count == 1

    changed_again = replace(
        changed_residual,
        remaining_volume_m3=(0.507, 0.40, 0.30, 0.20, 0.10, 0.10),
    )
    with pytest.raises(RuntimeError, match="locked_plan_changed_more_than_once"):
        planner.validate_locked_selection(recomputed, changed_again)


def test_stop_controller_holds_empty_for_three_observations_and_dumps_payload() -> None:
    controller = BoxEmptyingStopController()
    low = replace(_residual(), remaining_fraction=0.05)

    assert controller.observe_residual(low, payload_kg=0.0).stop is False
    assert controller.observe_residual(low, payload_kg=0.0).stop is False
    stopped = controller.observe_residual(low, payload_kg=0.0)
    assert stopped.stop is True
    assert stopped.reason == "empty_box_5pct_three_observations"

    controller.reset()
    for _ in range(2):
        controller.observe_residual(low, payload_kg=20.0)
    pending_dump = controller.observe_residual(low, payload_kg=20.0)
    assert pending_dump.stop is False
    assert pending_dump.dump_before_stop is True


def test_stop_controller_enforces_ineffective_streak_and_cycle_cap() -> None:
    controller = BoxEmptyingStopController()
    ineffective = CycleOutcome(payload_kg=14.9, stable_net_removed_volume_m3=0.0049)
    for _ in range(2):
        assert controller.record_cycle(ineffective).stop is False
    assert controller.record_cycle(ineffective).reason == "three_consecutive_ineffective"

    controller.reset()
    effective = CycleOutcome(payload_kg=15.0, stable_net_removed_volume_m3=0.005)
    for _ in range(119):
        assert controller.record_cycle(effective).stop is False
    capped = controller.record_cycle(effective)
    assert capped.stop is True
    assert capped.reason == "maximum_120_cycles"
