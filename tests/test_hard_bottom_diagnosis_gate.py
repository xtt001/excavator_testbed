from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from testbed.eval.hard_bottom_diagnosis_gate import (
    HARD_BOTTOM_DIAGNOSIS_GATE_SCHEMA,
    HARD_BOTTOM_DIAGNOSIS_GATE_V2_SCHEMA,
    build_hard_bottom_diagnosis_gate,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _diagnosis_payload() -> dict[str, object]:
    return {
        "schema": "act_hard_bottom_cycle6_diagnosis_v1",
        "status": "complete",
        "evidence_scope": "frozen_live_rollout_offline_reconstruction",
        "classification": {
            "primary_cause": "act_execution_capability_primary",
            "additional_findings": ["data_scene_cell_semantic_mismatch"],
            "facts": {
                "hard_bottom_margin_m": 0.02,
                "planned_depth_m": 0.364648,
                "planned_minimum_clearance_m": 0.0787,
                "actual_peak_penetration_m": 0.502483,
                "actual_penetration_overshoot_m": 0.137835,
                "contact_bucket_tip_clearance_m": 0.006493,
                "logical_cell_id": 4,
                "centerline_physical_cell_ids": [5],
                "swept_physical_cell_ids": [3, 5],
            },
        },
    }


def _replan_payload() -> dict[str, object]:
    return {
        "schema": "coverage_replan_replay_v1",
        "evidence_kind": "offline_production_service_replay",
        "teacher_forced_recorded_observation": True,
        "root_cause_flags": {
            "bookkeeping_corridor_4_wall_depletion_removed": True,
            "data_scene_cell_semantic_mismatch": True,
        },
        "contact_ownership_only_counterfactual": {
            "status": "selected",
            "selected_corridor_id": 4,
        },
        "corrected_production_replan": {
            "status": "no_wall_safe_corridor",
            "selected_corridor_id": -1,
            "candidate_scores": [
                {
                    "corridor_id": 4,
                    "wall_swept_cell_ids": [3, 5],
                    "depth_exhausted_swept_cell_ids": [5],
                    "rejection_reason": (
                        "swept_footprint_intersects_depth_exhausted_cell"
                    ),
                }
            ],
        },
        "live_1x10_allowed": False,
        "live_gate_reason": "data_scene_cell_semantic_mismatch",
    }


def _comparison_payload() -> dict[str, object]:
    target = {
        "raw_fields": {
            "operator_entry_x_m": 0.6,
            "operator_entry_z_m": 0.5,
            "operator_exit_x_m": 0.4,
            "operator_exit_z_m": 0.7,
            "operator_cut_depth_peak_m": 0.36,
        },
        "dig_cut_tokens": [0.0] * 10,
    }
    return {
        "schema": "hard_bottom_goal_comparison_v1",
        "status": "complete_with_policy_replay_blocked",
        "evidence_scope": "teacher_forced_recorded_observation",
        "offline_only": True,
        "promotion_eligible": False,
        "target_order": ["M0", "E1", "W1"],
        "targets": {
            "M0": dict(target),
            "E1": {
                **target,
                "exemplar_id": "episode_354",
                "source_episode_id": 32,
                "distance": 0.4955235,
            },
            "W1": {
                **target,
                "artifact_sha256": "8" * 64,
            },
        },
        "recorded_observation_window": {
            "first_action_step_id": 2935,
            "last_action_step_id": 2974,
            "frame_count": 40,
            "post_contact_clearance_excluded": True,
        },
        "temporal_state_contract": {
            "validation": {
                "status": "passed_structural_only",
                "unique_state_ids": True,
                "unique_buffer_owner_ids": True,
                "unique_cached_chunk_owner_ids": True,
            }
        },
        "policy_action_evidence": {
            "status": "blocked",
            "fresh_action_status": "blocked",
            "a0_window_100_action_status": "blocked",
            "no_synthetic_policy_actions_emitted": True,
        },
        "train_support_evidence": {
            "status": "complete",
            "kept_step_count": 76469,
            "train_source_episode_ids": [
                3,
                6,
                7,
                8,
                9,
                13,
                16,
                19,
                23,
                24,
                25,
                27,
                28,
                29,
                30,
                32,
            ],
            "validation_source_episode_ids_excluded": [33, 34],
            "targets": {
                target_id: {
                    "frame_count": 40,
                    "p01_p99_in_support_fraction": 1.0,
                }
                for target_id in ("M0", "E1", "W1")
            },
        },
    }


def _policy_replay_payload() -> dict[str, object]:
    summary = {
        "frame_count": 40,
        "fresh_mean": [0.0, -0.5, -0.1, 0.1],
        "aggregated_mean": [0.0, -0.52, -0.03, 0.15],
        "nearest_train_expert_mean": [0.0, -0.33, 0.05, 0.33],
        "fresh_vs_expert_mae": [0.01, 0.2, 0.1, 0.26],
        "aggregated_vs_expert_mae": [0.01, 0.19, 0.08, 0.19],
        "fresh_expert_sign_agreement": 0.47,
        "aggregated_expert_sign_agreement": 0.49,
    }
    return {
        "schema": "hard_bottom_goal_policy_replay_v1",
        "status": "complete",
        "evidence_scope": "teacher_forced_recorded_observation",
        "target_order": ["M0", "E1", "W1"],
        "recorded_observation_window": {
            "frame_count": 40,
            "first_action_step_id": 2935,
            "last_action_step_id": 2974,
        },
        "independent_policy_state_contract": {
            "status": "passed",
            "branch_count": 3,
            "shared_temporal_buffer": False,
        },
        "cross_target_summary": {
            target_id: dict(summary)
            for target_id in ("M0", "E1", "W1")
        },
        "diagnostic_limits": {
            "teacher_forced_only": True,
            "closed_loop_claim": False,
        },
    }


def test_gate_reports_two_unresolved_causes_and_blocks_live(
    tmp_path: Path,
) -> None:
    diagnosis_path = tmp_path / "diagnosis.json"
    replan_path = tmp_path / "replan.json"
    comparison_path = tmp_path / "comparison.json"
    _write_json(diagnosis_path, _diagnosis_payload())
    _write_json(replan_path, _replan_payload())
    _write_json(comparison_path, _comparison_payload())

    report = build_hard_bottom_diagnosis_gate(
        execution_diagnosis_path=diagnosis_path,
        coverage_replan_path=replan_path,
        goal_comparison_path=comparison_path,
        output_dir=tmp_path / "report",
    )

    assert report["schema"] == HARD_BOTTOM_DIAGNOSIS_GATE_SCHEMA
    assert report["root_cause"]["primary"] == (
        "act_execution_capability_primary"
    )
    assert report["root_cause"]["additional"] == [
        "data_scene_cell_semantic_mismatch"
    ]
    assert report["bookkeeping"]["ownership_fix_confirmed"] is True
    assert report["bookkeeping"]["is_only_remaining_problem"] is False
    assert report["gate"]["bounded_probe_required"] is False
    assert report["gate"]["formal_a0_1x10_allowed"] is False
    assert report["gate"]["formal_a0_1x10_executed"] is False
    assert report["gate"]["next_action"] == (
        "separate_act_conditioning_single_factor_fix"
    )
    assert report["evidence_matrix"]["bounded_live_probe"]["status"] == (
        "not_run_not_required"
    )
    assert report["evidence_matrix"]["formal_a0_1x10"]["status"] == (
        "not_run_gate_closed"
    )
    assert report["goal_comparison"]["policy_action_evidence_status"] == (
        "blocked"
    )
    assert report["goal_comparison"][
        "no_synthetic_policy_actions_emitted"
    ] is True
    assert (tmp_path / "report" / "root_cause_report.json").is_file()
    assert (tmp_path / "report" / "root_cause_report.md").is_file()


def test_v2_gate_incorporates_independent_checkpoint_policy_replay(
    tmp_path: Path,
) -> None:
    diagnosis_path = tmp_path / "diagnosis.json"
    replan_path = tmp_path / "replan.json"
    comparison_path = tmp_path / "comparison.json"
    replay_path = tmp_path / "policy_replay.json"
    _write_json(diagnosis_path, _diagnosis_payload())
    _write_json(replan_path, _replan_payload())
    _write_json(comparison_path, _comparison_payload())
    _write_json(replay_path, _policy_replay_payload())

    report = build_hard_bottom_diagnosis_gate(
        execution_diagnosis_path=diagnosis_path,
        coverage_replan_path=replan_path,
        goal_comparison_path=comparison_path,
        policy_replay_path=replay_path,
        output_dir=tmp_path / "report",
    )

    assert report["schema"] == HARD_BOTTOM_DIAGNOSIS_GATE_V2_SCHEMA
    assert report["goal_comparison"]["policy_action_evidence_status"] == (
        "complete_independent_checkpoint_replay"
    )
    assert report["goal_comparison"]["policy_replay"]["M0"][
        "aggregated_mean"
    ] == [0.0, -0.52, -0.03, 0.15]
    assert report["evidence_matrix"]["three_goal_comparison"]["policy_actions"] == (
        "complete_independent_checkpoint_replay"
    )
    assert report["gate"]["bounded_probe_required"] is False
    assert report["gate"]["formal_a0_1x10_allowed"] is False
    assert (tmp_path / "report" / "root_cause_report_v2.json").is_file()
    assert (tmp_path / "report" / "root_cause_report_v2.md").is_file()


def test_gate_locks_input_sha_and_refuses_overwrite(tmp_path: Path) -> None:
    diagnosis_path = tmp_path / "diagnosis.json"
    replan_path = tmp_path / "replan.json"
    comparison_path = tmp_path / "comparison.json"
    _write_json(diagnosis_path, _diagnosis_payload())
    _write_json(replan_path, _replan_payload())
    _write_json(comparison_path, _comparison_payload())
    output_dir = tmp_path / "report"

    report = build_hard_bottom_diagnosis_gate(
        execution_diagnosis_path=diagnosis_path,
        coverage_replan_path=replan_path,
        goal_comparison_path=comparison_path,
        output_dir=output_dir,
    )

    assert report["source_lock"]["execution_diagnosis"]["sha256"] == (
        hashlib.sha256(diagnosis_path.read_bytes()).hexdigest()
    )
    with pytest.raises(FileExistsError):
        build_hard_bottom_diagnosis_gate(
            execution_diagnosis_path=diagnosis_path,
            coverage_replan_path=replan_path,
            goal_comparison_path=comparison_path,
            output_dir=output_dir,
        )


def test_gate_rejects_unexpected_schema(tmp_path: Path) -> None:
    diagnosis_path = tmp_path / "diagnosis.json"
    replan_path = tmp_path / "replan.json"
    comparison_path = tmp_path / "comparison.json"
    diagnosis = _diagnosis_payload()
    diagnosis["schema"] = "unexpected"
    _write_json(diagnosis_path, diagnosis)
    _write_json(replan_path, _replan_payload())
    _write_json(comparison_path, _comparison_payload())

    with pytest.raises(ValueError, match="execution diagnosis schema"):
        build_hard_bottom_diagnosis_gate(
            execution_diagnosis_path=diagnosis_path,
            coverage_replan_path=replan_path,
            goal_comparison_path=comparison_path,
            output_dir=tmp_path / "report",
        )
