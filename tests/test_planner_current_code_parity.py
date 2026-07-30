from __future__ import annotations

import hashlib
import json
from pathlib import Path

from testbed.planner.golden_window_parity import (
    AGGREGATE_TX24_CONTRACT,
    AGGREGATE_TX24_PORTABLE_ARTIFACTS,
    assert_golden_window_contract,
    audit_full_replay_inputs,
    read_jsonl_rows,
    select_golden_window_indices,
    skill_switches,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
PORTABLE_FIXTURE_ROOT = (
    REPO_ROOT / "tests" / "fixtures" / "planner_current_code_parity"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_aggregate_tx24_portable_fixture_has_locked_lineage() -> None:
    manifest = json.loads(
        (PORTABLE_FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["schema_version"] == "planner_current_code_parity_fixture_v1"
    assert manifest["source_row_count"] == 5584
    assert manifest["golden_window_count"] == 112
    assert manifest["source_artifacts"]["rollout_jsonl"]["sha256"] == (
        "4857d6530e65c27158fc611b81be714a7820d1bc08ec8067b392049cc6cbba49"
    )
    for artifact in manifest["portable_artifacts"].values():
        artifact_path = REPO_ROOT / artifact["path"]
        assert artifact_path.is_file()
        assert _sha256(artifact_path) == artifact["sha256"]


def test_aggregate_tx24_artifacts_do_not_support_full_action_replay() -> None:
    audit = audit_full_replay_inputs(
        AGGREGATE_TX24_PORTABLE_ARTIFACTS.at_root(REPO_ROOT)
    )

    assert audit.feasible is False
    assert audit.parity_level == "artifact-golden-window-contract"
    assert "camera image observations or image frame paths" in audit.missing_inputs
    assert "embedded checkpoint weights and normalization/runtime policy state" in audit.missing_inputs
    assert "Unity/env simulator snapshot and planner private mutable state" in audit.missing_inputs


def test_aggregate_tx24_golden_windows_cover_every_skill_switch() -> None:
    rows = read_jsonl_rows(
        AGGREGATE_TX24_PORTABLE_ARTIFACTS.at_root(REPO_ROOT).rollout_jsonl
    )

    assert skill_switches(rows) == AGGREGATE_TX24_CONTRACT.expected_skill_switches

    indices = select_golden_window_indices(rows)
    assert len(indices) == AGGREGATE_TX24_CONTRACT.expected_window_count
    assert indices[:10] == (0, 1, 266, 267, 268, 416, 417, 418, 570, 571)
    assert indices[-10:] == (
        5207,
        5208,
        5261,
        5262,
        5263,
        5451,
        5452,
        5453,
        5582,
        5583,
    )


def test_aggregate_tx24_golden_window_snapshot_matches_contract() -> None:
    report = assert_golden_window_contract(
        AGGREGATE_TX24_PORTABLE_ARTIFACTS.at_root(REPO_ROOT),
        AGGREGATE_TX24_CONTRACT,
    )

    assert report.window_count == 112
    assert report.field_count == 75
    assert report.window_digest == (
        "71027afbf23c2f0080eda13fbd1d7b07566c17e9097c747374374caa19cbe8b5"
    )
    assert report.trace_contracts == {
        "dig_cut_token_contract_version": "v2_4_removed_depth_cut_v3",
        "return_target_token_contract_version": "v2_4_removed_depth_cut_v3",
        "return_start_envelope_token_contract_version": "return_start_envelope_tokens_v1",
        "coverage_decision_trace_count": 20,
        "cell_entry_trace_count": 0,
        "coverage_terminal_stop_requested": True,
        "coverage_terminal_stop_reason": "dig_area_depleted",
    }
    assert report.summary_metrics == {
        "episode_len": 5584,
        "episode_return": 19296.0,
        "legacy_success": True,
        "final_hold_success": True,
        "first_task_success_step": 760,
        "completed_transition_count": 8,
        "completed_dump_count": 9,
        "coverage_terminal_stop_requested": 1,
        "coverage_terminal_stop_reason": "dig_area_depleted",
        "coverage_depleted_count": 6,
        "coverage_selected_corridor_id": 0,
        "cell_entry_enabled": 0,
        "cell_entry_trace_count": 0,
        "pre_dig_align_enabled": 0,
        "pre_dig_align_completed_count": 0,
        "transition_timeout_count": 0,
        "dig_bad_replan_count": 0,
        "dig_exit_guard_replan_count": 0,
        "rollout_stop_reason": "dig_area_depleted",
    }
    assert report.config_contract == {
        "policy.pre_dig_align.enabled": False,
        "policy.cell_entry": "<missing>",
        "policy.cell_entry_enabled": "<missing>",
        "policy.dig_low_dim_keys": ["qpos", "qvel", "dig_cut_tokens"],
        "policy.return_low_dim_keys": [
            "qpos",
            "qvel",
            "return_start_envelope_tokens_v1",
            "return_relocate_tokens_v1",
        ],
    }
