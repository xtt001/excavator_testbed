from __future__ import annotations

import json
from pathlib import Path

import pytest

from testbed.eval.coverage_execution_gate_preflight import (
    REQUIRED_PRODUCTION_CASE_IDS,
    build_gate_decision,
    summarize_candidate_trace,
    write_preflight_artifact,
)


def _case(
    case_id: str,
    *,
    status: str = "selected",
    clearance_m: float = 0.25,
) -> dict[str, object]:
    selected = (
        {
            "source_exemplar_id": f"{case_id}_tuple",
            "worktool_sweep_3d_effective_clearance_m": clearance_m,
        }
        if status == "selected"
        else {}
    )
    return {
        "case_id": case_id,
        "selection": {
            "status": status,
            "selected_candidate": selected,
        },
        "candidate_summary": {
            "candidate_count": 374,
            "selected_legal_candidate_count": int(status == "selected"),
        },
    }


def test_gate_uses_configured_calibrated_clearance_not_legacy_030() -> None:
    cases = [
        _case(case_id, clearance_m=0.25)
        for case_id in REQUIRED_PRODUCTION_CASE_IDS
    ]

    decision = build_gate_decision(
        cases,
        configured_hard_clearance_m=0.24,
    )

    assert decision["all_required_states_have_legal_candidate"] is True
    assert decision["bounded_live_allowed"] is True
    assert decision["configured_hard_clearance_m"] == pytest.approx(0.24)


def test_any_required_state_without_candidate_blocks_bounded_live() -> None:
    cases = [
        _case(
            case_id,
            status=(
                "no_wall_safe_corridor"
                if case_id == "post_return_reset_1"
                else "selected"
            ),
        )
        for case_id in REQUIRED_PRODUCTION_CASE_IDS
    ]

    decision = build_gate_decision(
        cases,
        configured_hard_clearance_m=0.24,
    )

    assert decision["all_required_states_have_legal_candidate"] is False
    assert decision["bounded_live_allowed"] is False
    assert decision["failed_case_ids"] == ["post_return_reset_1"]
    assert decision["blocker"] == "production_full_gate_has_no_legal_candidate"


def test_candidate_summary_preserves_full_trace_and_gate_waterfall() -> None:
    trace = [
        {
            "exemplar_id": "episode_0",
            "status": "rejected",
            "rejection_reason": "wall_clearance_below_hard_minimum",
        },
        {
            "exemplar_id": "episode_1",
            "status": "rejected",
            "rejection_reason": "tuple_start_out_of_support",
        },
        {
            "exemplar_id": "episode_2",
            "status": "rejected",
            "rejection_reason": "worktool_3d_clearance_below_minimum",
            "worktool_sweep_3d_effective_clearance_m": 0.15,
        },
        {
            "exemplar_id": "episode_3",
            "status": "rejected",
            "rejection_reason": "outcome_depleted",
        },
    ]

    summary = summarize_candidate_trace(trace)

    assert summary["candidate_count"] == 4
    assert summary["rejection_count_by_gate"] == {
        "outcome_state": 1,
        "tuple_start_reachability": 1,
        "wall_safety_2d": 1,
        "worktool_sweep_3d": 1,
    }
    assert summary["worktool_sweep_3d_evaluated_count"] == 1
    assert summary["maximum_worktool_sweep_3d_effective_clearance_m"] == (
        pytest.approx(0.15)
    )


def test_preflight_writer_is_no_overwrite(tmp_path: Path) -> None:
    output_dir = tmp_path / "preflight"
    artifact = {
        "schema": "coverage_execution_production_preflight_v2",
        "status": "failed",
    }

    output_path = write_preflight_artifact(
        artifact=artifact,
        output_dir=output_dir,
    )

    assert json.loads(output_path.read_text(encoding="utf-8")) == artifact
    with pytest.raises(FileExistsError):
        write_preflight_artifact(
            artifact=artifact,
            output_dir=output_dir,
        )
