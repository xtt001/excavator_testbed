from __future__ import annotations

import pytest

from testbed.planner.primitive_coverage_status import CoverageStatus


def test_coverage_status_freezes_selected_corridor_and_candidate_scores() -> None:
    candidate_scores = [
        {"corridor_id": 0, "score": 1.25, "reason": "selected"},
        {"corridor_id": 1, "score": 0.25, "reason": "deprioritized"},
    ]

    status = CoverageStatus.from_inputs(
        selected_corridor_id=0,
        selected_corridor_score=1.25,
        candidate_scores=candidate_scores,
    )

    candidate_scores[0]["score"] = 99.0

    assert status.selected_corridor_id == 0
    assert status.selected_corridor_score == 1.25
    assert status.candidate_scores[0]["score"] == 1.25
    with pytest.raises(TypeError):
        status.candidate_scores[0]["score"] = 2.0


def test_coverage_status_records_terminal_stop_state() -> None:
    status = CoverageStatus.from_inputs(
        coverage_terminal_stop_requested=True,
        coverage_terminal_stop_reason="dig_area_depleted",
        coverage_depleted_count=6,
    )

    assert status.terminal_stop_requested is True
    assert status.terminal_stop_reason == "dig_area_depleted"
    assert status.depleted_count == 6


def test_coverage_status_records_completion_and_rejection_observables() -> None:
    active_ids = ["active-a"]
    rejected_ids = {"reject-a"}

    status = CoverageStatus.from_inputs(
        active_state_exemplar_ids=active_ids,
        rejected_state_exemplar_ids=rejected_ids,
        last_payload_gain_kg=42.0,
        last_effective_deposit_delta_kg=17.5,
        active_corridor_depleted=True,
        rejected_active_corridor=True,
    )

    active_ids.append("mutated")
    rejected_ids.add("mutated")

    assert status.active_state_exemplar_ids == ("active-a",)
    assert status.rejected_state_exemplar_ids == frozenset({"reject-a"})
    assert status.last_payload_gain_kg == 42.0
    assert status.last_effective_deposit_delta_kg == 17.5
    assert status.active_corridor_depleted is True
    assert status.rejected_active_corridor is True
