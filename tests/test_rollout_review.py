from __future__ import annotations

import json
from pathlib import Path

from testbed.eval.rollout_review import build_rollout_review


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    return path


def _env_state(*, plane_depth: float, local_surface_depth: float) -> list[float]:
    values = [0.0] * 64
    values[8] = plane_depth
    values[31] = local_surface_depth
    return values


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


def test_rollout_review_ignores_terminal_return_segment_for_handoff(
    tmp_path: Path,
) -> None:
    results_dir = tmp_path / "results"
    summary_path = _write_json(
        results_dir / "rollouts" / "rollout_000_summary.json",
        {
            "rollout_id": 0,
            "success": True,
            "target_cycle_gate_success": 0,
            "quality_issue_count": 0,
            "return_to_dig_entry_close": 0,
            "return_to_dig_entry_error_m": 4.83,
            "return_to_dig_max_entry_error_m": 0.55,
            "coverage_terminal_stop_requested": 1,
            "coverage_terminal_stop_reason": "dig_area_depleted",
            "rollout_stop_reason": "dig_area_depleted",
        },
    )
    _write_json(
        results_dir / "rollouts" / "rollout_000_planner_trace.json",
        {
            "coverage_decision_trace": [{"event": "select_corridor"}],
            "coverage_terminal_stop_requested": True,
            "coverage_terminal_stop_reason": "dig_area_depleted",
        },
    )
    _write_jsonl(
        results_dir / "rollouts" / "rollout_000.jsonl",
        [
            {
                "t": 10,
                "skill_name": "return",
                "return_to_dig_entry_close": False,
                "return_to_dig_entry_error_m": 4.2,
                "return_to_dig_max_entry_error_m": 0.55,
                "coverage_terminal_stop_requested": False,
            },
            {
                "t": 11,
                "skill_name": "dig",
                "skill_switch_reason": "return_to_dig_start_envelope_ready",
                "return_to_dig_entry_close": True,
                "return_to_dig_entry_error_m": 0.24,
                "return_to_dig_max_entry_error_m": 0.55,
                "coverage_terminal_stop_requested": False,
            },
            {
                "t": 20,
                "skill_name": "return",
                "return_to_dig_entry_close": False,
                "return_to_dig_entry_error_m": 4.83,
                "return_to_dig_max_entry_error_m": 0.55,
                "coverage_terminal_stop_requested": True,
                "coverage_terminal_stop_reason": "dig_area_depleted",
            },
        ],
    )
    _write_json(
        results_dir / "rollout_manifest.json",
        {
            "rollouts": [{"rollout_id": 0, "summary_path": str(summary_path)}],
        },
    )

    review = build_rollout_review(results_dir)

    handoff = review["rollout_reviews"][0]["handoff"]
    assert handoff["status"] == "ready"
    assert handoff["source"] == "rollout_jsonl_completed_return_to_dig_transitions"
    assert handoff["return_to_dig_entry_close"] is True
    assert handoff["return_to_dig_entry_error_m"] == 0.24
    assert handoff["completed_handoff_count"] == 1
    assert handoff["ignored_incomplete_return_segment_count"] == 1
    assert handoff["summary_snapshot"]["return_to_dig_entry_error_m"] == 4.83


def test_rollout_review_marks_terminal_only_return_handoff_not_applicable(
    tmp_path: Path,
) -> None:
    results_dir = tmp_path / "results"
    summary_path = _write_json(
        results_dir / "rollouts" / "rollout_000_summary.json",
        {
            "rollout_id": 0,
            "success": True,
            "quality_issue_count": 0,
            "return_to_dig_entry_close": 0,
            "return_to_dig_entry_error_m": 4.83,
            "return_to_dig_max_entry_error_m": 0.55,
            "coverage_terminal_stop_requested": 1,
            "coverage_terminal_stop_reason": "dig_area_depleted",
            "rollout_stop_reason": "dig_area_depleted",
        },
    )
    _write_json(
        results_dir / "rollouts" / "rollout_000_planner_trace.json",
        {"coverage_decision_trace": [{"event": "terminal_stop"}]},
    )
    _write_jsonl(
        results_dir / "rollouts" / "rollout_000.jsonl",
        [
            {
                "t": 20,
                "skill_name": "return",
                "return_to_dig_entry_close": False,
                "return_to_dig_entry_error_m": 4.83,
                "return_to_dig_max_entry_error_m": 0.55,
                "coverage_terminal_stop_requested": True,
                "coverage_terminal_stop_reason": "dig_area_depleted",
            },
        ],
    )
    _write_json(
        results_dir / "rollout_manifest.json",
        {"rollouts": [{"rollout_id": 0, "summary_path": str(summary_path)}]},
    )

    review = build_rollout_review(results_dir)

    handoff = review["rollout_reviews"][0]["handoff"]
    assert handoff["status"] == "not_applicable"
    assert handoff["source"] == "rollout_jsonl_no_completed_return_to_dig_transitions"
    assert handoff["return_to_dig_entry_error_m"] is None
    assert handoff["ignored_terminal_return_segment_count"] == 1
    assert handoff["summary_snapshot"]["return_to_dig_entry_error_m"] == 4.83


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


def test_rollout_review_reports_local_surface_depth_separately_from_summary_plane_depth(
    tmp_path: Path,
) -> None:
    results_dir = tmp_path / "results"
    summary_path = _write_json(
        results_dir / "rollouts" / "rollout_004_summary.json",
        {
            "rollout_id": 4,
            "success": True,
            "quality_issue_count": 0,
            "return_to_dig_entry_close": 1,
            "return_to_dig_entry_error_m": 0.1,
            "return_to_dig_max_entry_error_m": 0.55,
            "cycle1_depth_target_m": 0.25,
            "cycle1_depth_peak_m": 0.52,
            "cycle1_depth_error_m": 0.27,
            "cycle1_depth_expert_p95_overshoot_m": 0.11,
        },
    )
    _write_json(
        results_dir / "rollouts" / "rollout_004_planner_trace.json",
        {"coverage_decision_trace": [{"event": "select_corridor"}]},
    )
    _write_jsonl(
        results_dir / "rollouts" / "rollout_004.jsonl",
        [
            {
                "skill_name": "dig",
                "dig_cut_tokens": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.3125, 1.0, 1.0],
                "env_state": _env_state(plane_depth=0.50, local_surface_depth=0.20),
            },
            {
                "skill_name": "dig",
                "dig_cut_tokens": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.3125, 1.0, 1.0],
                "env_state": _env_state(plane_depth=0.52, local_surface_depth=0.27),
            },
            {
                "skill_name": "carry",
                "dig_cut_tokens": [0.0] * 10,
                "env_state": _env_state(plane_depth=0.60, local_surface_depth=0.40),
            },
        ],
    )
    _write_json(
        results_dir / "rollout_manifest.json",
        {"rollouts": [{"rollout_id": 4, "summary_path": str(summary_path)}]},
    )

    review = build_rollout_review(results_dir)

    depth = review["rollout_reviews"][0]["depth_tracking"]
    assert depth["status"] == "present"
    assert depth["dig_local_surface"]["source"] == (
        "rollout_jsonl_contiguous_dig_segments_env_state_31"
    )
    assert depth["dig_local_surface"]["target_source"] == "dig_cut_tokens[7]*0.8"
    assert depth["dig_local_surface"]["error_mean_m"] == 0.020000000000000018
    assert depth["summary_plane_depth"]["error_mean_m"] == 0.27
    assert depth["cycles"][0]["dig_local_surface_depth_error_m"] == 0.020000000000000018
    assert depth["cycles"][0]["summary_plane_depth_error_m"] == 0.27
