from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from testbed.planner.decision_structure.tier1_validation import (
    Tier1ValidationError,
    validate_tier1_package,
)


def test_tier1_validator_accepts_gold_example_package(tmp_path: Path) -> None:
    package = _write_tier1_package(tmp_path)

    report = validate_tier1_package(package)

    assert report.passed
    assert report.dataset_id == "aggregate_tx24_20260618"
    assert report.select_event_summary["select_event_count"] == 10
    assert report.select_event_summary["select_event_indices"] == [
        0,
        2,
        4,
        6,
        8,
        10,
        12,
        14,
        16,
        19,
    ]
    utility = {row["name"]: row for row in report.gold_example_results["coverage_utility"]}
    assert utility["coverage_event_0"]["selection_matches"] == [3]
    assert utility["coverage_event_2"]["selection_matches"] == [1]
    assert utility["coverage_event_12"]["selection_matches"] == [2]
    assert utility["terminal_all_depleted_event_19"]["selection_matches"] == [
        0,
        1,
        3,
    ]
    claims = {
        row["claim"]: row for row in report.gold_example_results["llm_explanation"]
    }
    assert claims["coverage_corridor_confirmed_live"]["passed"]
    assert claims["cell_entry_parked"]["passed"]
    assert claims["artifact_limits"]["passed"]
    assert any(issue.code == "low_margin_case" for issue in report.audit_warnings)
    assert any(
        issue.code == "non_unique_selection" for issue in report.audit_warnings
    )


def test_tier1_validator_reports_hash_mismatch(tmp_path: Path) -> None:
    package = _write_tier1_package(tmp_path)
    summary_path = package / "inputs" / "rollout_000_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["completed_dump_count"] = 10
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    report = validate_tier1_package(package)

    assert not report.passed
    assert any(issue.code == "input_hash_mismatch" for issue in report.fail_fast_errors)


def test_tier1_validator_requires_package_readme(tmp_path: Path) -> None:
    package = _write_tier1_package(tmp_path)
    (package / "README.md").unlink()

    with pytest.raises(Tier1ValidationError, match="README.md"):
        validate_tier1_package(package)


def test_tier1_validator_requires_hash_entries_for_all_inputs(
    tmp_path: Path,
) -> None:
    package = _write_tier1_package(tmp_path)
    hash_path = package / "hashes" / "sha256sums.txt"
    lines = [
        line
        for line in hash_path.read_text(encoding="utf-8").splitlines()
        if "inputs/rollout_000_summary.json" not in line
    ]
    hash_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    report = validate_tier1_package(package)

    assert not report.passed
    assert any(
        issue.code == "input_hash_mismatch"
        and issue.path == "inputs/rollout_000_summary.json"
        for issue in report.fail_fast_errors
    )


def test_tier1_validator_fails_when_negative_rejection_does_not_pass(
    tmp_path: Path,
) -> None:
    package = _write_tier1_package(tmp_path)
    manifest_path = package / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["validation_limits"]["full_action_replay_supported"] = True
    _write_json(manifest_path, manifest)

    report = validate_tier1_package(package)

    assert not report.passed
    assert any(
        issue.code == "negative_rejection_failed"
        and "full_action_replay_parity" in issue.message
        for issue in report.fail_fast_errors
    )


def test_tier1_validator_reports_malformed_candidate_without_crashing(
    tmp_path: Path,
) -> None:
    package = _write_tier1_package(tmp_path)
    trace_path = package / "inputs" / "rollout_000_planner_trace.json"
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    event = trace["coverage_decision_trace"][0]
    selected_score = event["selected_score"]
    event["candidate_scores"][0] = {"score": selected_score}
    _write_json(trace_path, trace)
    _rewrite_input_hashes(package)

    report = validate_tier1_package(package)

    assert not report.passed
    assert any(
        issue.code == "candidate_identity_missing"
        for issue in report.fail_fast_errors
    )


def _write_tier1_package(tmp_path: Path) -> Path:
    package = tmp_path / "package"
    inputs = package / "inputs"
    hashes = package / "hashes"
    inputs.mkdir(parents=True)
    hashes.mkdir()

    trace = {
        "coverage_decision_trace": _coverage_decision_trace(),
        "coverage_terminal_stop_reason": "dig_area_depleted",
        "coverage_terminal_stop_requested": 1,
    }
    summary = {
        "success": True,
        "episode_len": 5584,
        "rollout_stop_reason": "dig_area_depleted",
        "target_cycle_completed_dump_count": 9,
        "completed_dump_count": 9,
        "coverage_completed_dump_count": 9,
        "coverage_depleted_count": 6,
        "coverage_selected_corridor_id": 0,
        "coverage_terminal_stop_requested": 1,
        "coverage_terminal_stop_reason": "dig_area_depleted",
        "pre_dig_align_enabled": 0,
        "primitive_final_skill": "return",
        "cell_entry_enabled": 0,
        "cell_entry_trace_count": 0,
    }
    evidence = {
        "schema_version": 1,
        "rows": [
            _evidence_row("coverage.corridor", "confirmed-live", "retain-and-migrate", 5319, 5319, 5319),
            _evidence_row("trace.planner_trace", "report-only", "retain-report-boundary", 1, 0, 1),
            _evidence_row("debug.debug_state", "report-only", "retain-report-boundary", 5584, 0, 5584),
            _evidence_row("report.rollout_summary", "report-only", "retain-report-boundary", 1, 0, 1),
            _evidence_row("token.cell_entry", "dead-candidate", "retain-legacy-parking", 0, 0, 0),
            _evidence_row("gate.pre_dig_align", "dead-candidate", "retain-legacy-parking", 0, 0, 0),
        ],
    }
    manifest = {
        "schema_version": "tier1_validation_package_manifest_v0",
        "dataset_id": "aggregate_tx24_20260618",
        "source": {
            "host": "pingfan",
            "repo_branch_observed": "fs/v2_4-refactor-tests",
            "repo_head_observed": "887256f",
        },
        "validation_limits": {
            "full_action_replay_supported": False,
            "raw_image_observations_included": False,
            "checkpoint_state_included": False,
            "unity_or_env_snapshot_included": False,
            "private_planner_mutable_state_included": False,
        },
    }
    files = {
        "manifest.json": manifest,
        "inputs/rollout_000_planner_trace.json": trace,
        "inputs/rollout_000_summary.json": summary,
        "inputs/planner_evidence_report.json": evidence,
    }
    for rel_path, payload in files.items():
        _write_json(package / rel_path, payload)
    (inputs / "rollout_000.jsonl").write_text(
        json.dumps({"rollout_id": 0, "step_id": 1, "skill_name": "dig"}) + "\n",
        encoding="utf-8",
    )
    (inputs / "eval_resolved_config.yaml").write_text(
        "policy:\n  dig_low_dim_keys: [qpos, qvel, dig_cut_tokens]\n",
        encoding="utf-8",
    )
    (inputs / "planner_evidence_report.md").write_text(
        "# Synthetic Evidence Report\n",
        encoding="utf-8",
    )
    (package / "README.md").write_text(
        "# Synthetic Tier 1 Validation Package\n",
        encoding="utf-8",
    )

    _rewrite_input_hashes(package)
    return package


def _rewrite_input_hashes(package: Path) -> None:
    lines = []
    for path in sorted((package / "inputs").iterdir()):
        if path.is_file():
            rel = path.relative_to(package)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            lines.append(f"{digest}  {rel.as_posix()}")
    (package / "hashes" / "sha256sums.txt").write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def _coverage_decision_trace() -> list[dict[str, object]]:
    trace: list[dict[str, object]] = []
    select_by_index = {
        0: _select_event(0, "dig", [(3, 4.180294018773603, 0), (2, 3.055178333610378, 0), (1, -1e12, 0), (0, -1e12, 0), (5, -1e12, 0), (4, -1e12, 0)]),
        2: _select_event(0, "return", [(1, 4.847767649391016, 0), (0, 4.691456375323683, 0), (5, 4.3, 0), (4, 3.9, 0), (2, 3.3, 0), (3, -1000000001.0, 1)]),
        4: _select_event(1, "return", [(0, 4.0, 0), (1, 3.0, 0), (2, 2.0, 0), (3, 1.0, 1), (4, 0.0, 0), (5, -1.0, 0)]),
        6: _select_event(2, "return", [(0, 4.0, 0), (1, 3.0, 0), (2, 2.0, 0), (3, 1.0, 1), (4, 0.0, 0), (5, -1.0, 0)]),
        8: _select_event(3, "return", [(0, 4.0, 0), (1, 3.0, 0), (2, 2.0, 0), (3, 1.0, 1), (4, 0.0, 0), (5, -1.0, 0)]),
        10: _select_event(4, "return", [(0, 4.0, 0), (1, 3.0, 0), (2, 2.0, 0), (3, 1.0, 1), (4, 0.0, 0), (5, -1.0, 0)]),
        12: _select_event(5, "return", [(2, 1.84523706678468, 0), (5, -0.6392190276559341, 0), (4, -100000001.0, 0), (0, -1000000001.0, 1), (1, -1000000001.0, 1), (3, -1000000001.0, 1)]),
        14: _select_event(6, "return", [(0, 4.0, 0), (1, 3.0, 0), (2, 2.0, 0), (3, 1.0, 1), (4, 0.0, 0), (5, -1.0, 0)]),
        16: _select_event(7, "return", [(0, 4.0, 0), (1, 3.0, 0), (2, 2.0, 0), (3, 1.0, 1), (4, 0.0, 0), (5, -1.0, 0)]),
        19: _select_event(8, "return", [(0, -1000000001.0, 1), (1, -1000000001.0, 1), (3, -1000000001.0, 1), (2, -1000000002.0, 1), (4, -1000000002.0, 1), (5, -1000000002.0, 1)], terminal=True),
    }
    for index in range(20):
        trace.append(select_by_index.get(index, {"event": "complete_dump", "cycle_index": index}))
    return trace


def _select_event(
    cycle_index: int,
    skill_name: str,
    candidates: list[tuple[int, float, int]],
    terminal: bool = False,
) -> dict[str, object]:
    return {
        "event": "select_corridor",
        "cycle_index": cycle_index,
        "skill_name": skill_name,
        "active_corridor_id": -1,
        "last_selected_corridor_id": -1,
        "selected_score": candidates[0][1],
        "terminal_stop_requested": 1 if terminal else 0,
        "terminal_stop_reason": "dig_area_depleted" if terminal else "",
        "candidate_scores": [
            _candidate(corridor_id, score, depleted)
            for corridor_id, score, depleted in candidates
        ],
    }


def _candidate(corridor_id: int, score: float, depleted: int) -> dict[str, object]:
    return {
        "corridor_id": corridor_id,
        "cell_id": corridor_id,
        "row_id": corridor_id // 2,
        "score": score,
        "attempts": 1 if depleted else 0,
        "attempt_limit": 3,
        "depleted": depleted,
        "source_count": 100,
        "source_fraction": 0.5,
        "cell_confidence": 1.0,
        "belief_coverage": 0.5,
        "remaining_depth_m": 0.05,
        "first_dig_bonus": 0.0,
        "first_dig_entry_distance_m": 0.1,
        "first_dig_entry_reachable": 1,
        "first_dig_qpos_delta_norm": 0.2,
        "first_dig_qpos_reachable": 1,
        "first_dig_reachable": 0 if score <= -1e12 else 1,
        "first_dig_gate_applied": 1,
        "first_dig_gated_out": 1 if score <= -1e12 else 0,
        "rare_first_dig_gated_out": 0,
        "first_dig_max_entry_distance_m": 0.45,
        "recent_row_penalty": 0.0,
        "same_recent_row": 0,
        "low_productivity_streak": 0,
        "state_exemplar_distance": 0.1,
        "state_exemplar_id": f"ex-{corridor_id}",
    }


def _evidence_row(
    capability_id: str,
    classification: str,
    retention_decision: str,
    observed_count: int,
    consumed_count: int,
    reported_count: int,
) -> dict[str, object]:
    return {
        "capability_id": capability_id,
        "classification": classification,
        "retention_decision": retention_decision,
        "observed_count": observed_count,
        "consumed_by_decision_count": consumed_count,
        "reported_count": reported_count,
    }


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
