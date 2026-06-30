from __future__ import annotations

import json
from pathlib import Path

from testbed.eval.rollout_review import build_rollout_review


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def test_rollout_review_flags_successful_rollout_with_quality_issues_and_missing_coverage_trace(
    tmp_path: Path,
) -> None:
    results_dir = tmp_path / "results"
    summary_path = _write_json(
        results_dir / "rollouts" / "rollout_000_summary.json",
        {
            "rollout_id": 0,
            "success": True,
            "target_cycle_gate_success": 1,
            "quality_issue_count": 225,
            "low_cycle_deposited_fraction_count": 7,
            "cycle_deposited_fraction_min": 0.467,
            "return_to_dig_entry_close": 1,
            "return_to_dig_entry_error_m": 0.539,
            "return_to_dig_max_entry_error_m": 0.55,
            "rollout_stop_reason": "target_cycle_gate_terminal_hold_reached",
        },
    )
    _write_json(
        results_dir / "rollouts" / "rollout_000_planner_trace.json",
        {
            "coverage_decision_trace": [],
            "coverage_terminal_stop_requested": False,
            "coverage_terminal_stop_reason": "",
        },
    )
    _write_json(
        results_dir / "rollout_manifest.json",
        {
            "n_rollouts": 1,
            "success_rates_by_mode": {"success": 1.0},
            "rollouts": [{"rollout_id": 0, "summary_path": str(summary_path)}],
        },
    )

    review = build_rollout_review(results_dir)

    assert review["schema_version"] == "rollout_review_v1"
    assert review["overall_status"] == "needs_root_cause_audit"
    assert review["llm_candidate_ranking_ready"] is False
    assert "success_does_not_prove_quality" in review["root_cause_hints"]
    assert "rollout_0:coverage_decision_trace_missing" in review["evidence_gaps"]
    rollout_review = review["rollout_reviews"][0]
    assert rollout_review["status"] == "needs_root_cause_audit"
    assert "quality_issue_count" in rollout_review["quality"]["flags"]
    assert rollout_review["handoff"]["return_to_dig_entry_close"] is True


def test_rollout_review_marks_llm_candidate_ranking_ready_when_coverage_trace_explains_issue(
    tmp_path: Path,
) -> None:
    results_dir = tmp_path / "results"
    summary_path = _write_json(
        results_dir / "rollouts" / "rollout_001_summary.json",
        {
            "rollout_id": 1,
            "success": False,
            "quality_issue_count": 0,
            "coverage_depleted_count": 3,
            "coverage_terminal_stop_requested": 1,
            "coverage_terminal_stop_reason": "dig_area_depleted",
            "return_to_dig_entry_close": 1,
            "return_to_dig_entry_error_m": 0.12,
            "return_to_dig_max_entry_error_m": 0.55,
            "rollout_stop_reason": "planner_terminal_stop",
        },
    )
    _write_json(
        results_dir / "rollouts" / "rollout_001_planner_trace.json",
        {
            "coverage_decision_trace": [
                {"event": "select_corridor", "corridor": {"corridor_id": 0}},
                {"event": "reject_corridor", "extra": {"reason": "low_productivity"}},
                {"event": "terminal_stop", "extra": {"reason": "dig_area_depleted"}},
            ],
            "coverage_terminal_stop_requested": True,
            "coverage_terminal_stop_reason": "dig_area_depleted",
        },
    )
    _write_json(
        results_dir / "rollout_manifest.json",
        {
            "n_rollouts": 1,
            "success_rates_by_mode": {"success": 0.0},
            "rollouts": [{"rollout_id": 1, "summary_path": str(summary_path)}],
        },
    )

    review = build_rollout_review(results_dir)

    assert review["overall_status"] == "llm_candidate_ranking_candidate"
    assert review["llm_candidate_ranking_ready"] is True
    assert "coverage_candidate_ranking_review" in review["root_cause_hints"]
    assert "rollout_1:coverage_decision_trace_missing" not in review["evidence_gaps"]
    rollout_review = review["rollout_reviews"][0]
    assert rollout_review["coverage"]["decision_trace_count"] == 3
    assert rollout_review["coverage"]["terminal_stop_reason"] == "dig_area_depleted"


def test_rollout_review_reports_handoff_evidence_gap_when_return_fields_are_missing(
    tmp_path: Path,
) -> None:
    results_dir = tmp_path / "results"
    summary_path = _write_json(
        results_dir / "rollouts" / "rollout_002_summary.json",
        {
            "rollout_id": 2,
            "success": True,
            "quality_issue_count": 0,
            "rollout_stop_reason": "episode_len_reached",
        },
    )
    _write_json(
        results_dir / "rollouts" / "rollout_002_planner_trace.json",
        {"coverage_decision_trace": [{"event": "select_corridor"}]},
    )
    _write_json(
        results_dir / "rollout_manifest.json",
        {"rollouts": [{"rollout_id": 2, "summary_path": str(summary_path)}]},
    )

    review = build_rollout_review(results_dir)

    assert review["overall_status"] == "insufficient_evidence"
    assert "rollout_2:return_to_dig_handoff_fields_missing" in review["evidence_gaps"]
    assert review["rollout_reviews"][0]["handoff"]["status"] == "missing"


def test_rollout_review_resolves_repo_relative_manifest_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    results_dir = Path("runs/eval/demo/results")
    summary_path = _write_json(
        results_dir / "rollouts" / "rollout_003_summary.json",
        {
            "rollout_id": 3,
            "success": True,
            "quality_issue_count": 0,
            "return_to_dig_entry_close": 1,
            "return_to_dig_entry_error_m": 0.1,
            "return_to_dig_max_entry_error_m": 0.55,
            "planner_trace_path": str(
                results_dir / "rollouts" / "rollout_003_planner_trace.json"
            ),
        },
    )
    _write_json(
        results_dir / "rollouts" / "rollout_003_planner_trace.json",
        {"coverage_decision_trace": [{"event": "select_corridor"}]},
    )
    _write_json(
        results_dir / "rollout_manifest.json",
        {"rollouts": [{"rollout_id": 3, "summary_path": str(summary_path)}]},
    )

    review = build_rollout_review(results_dir)

    assert review["overall_status"] == "reviewed"
    assert review["evidence_gaps"] == []
    assert review["rollout_reviews"][0]["coverage"]["status"] == "present"
