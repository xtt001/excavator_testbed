from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import testbed.eval.act_goal_execution_contract_recovery as recovery
from testbed.eval.act_goal_execution_contract_recovery import (
    ACT_GOAL_EXECUTION_CONTRACT_RECOVERY_SCHEMA,
    MANIFEST_FILENAME,
    build_act_goal_execution_contract_recovery,
)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _token() -> list[float]:
    return [0.1, 0.2, 0.3, 0.4, -0.8, 0.6, 0.25, 0.375, 1.0, 1.0]


def _raw_fields() -> dict[str, float | int]:
    return {
        "operator_entry_x_m": 0.6,
        "operator_entry_y_m": 0.0,
        "operator_entry_z_m": 0.5,
        "operator_exit_x_m": 0.4,
        "operator_exit_y_m": 0.0,
        "operator_exit_z_m": 0.7,
        "operator_cut_direction_x": -0.8,
        "operator_cut_direction_y": 0.0,
        "operator_cut_direction_z": 0.6,
        "operator_cut_length_m": 0.5,
        "operator_cut_depth_peak_m": 0.3,
        "operator_cut_payload_gain_kg": 60.0,
        "operator_effective_deposit_delta_kg": 45.0,
        "operator_cut_valid": 1,
    }


def _diagnosis(source_manifest_sha256: str) -> dict[str, object]:
    return {
        "schema": "act_hard_bottom_cycle6_diagnosis_v1",
        "status": "completed",
        "evidence_scope": "frozen_recorded_closed_loop",
        "cycle_index": 5,
        "source_manifest": {
            "schema": "frozen_failure_artifact_sha256_manifest_v1",
            "filename": "source_lock_manifest.json",
            "sha256": source_manifest_sha256,
        },
        "cut_window": {
            "first_action_step_id": 101,
            "first_pre_action_observation_step_id": 100,
            "contact_observation_step_id": 104,
            "last_cut_action_step_id": 104,
            "safety_trigger_action_step_id": 105,
        },
        "plan": {
            "logical_cell_id": 4,
            "corridor_id": 4,
            "planned_depth_m": 0.3,
            "entry_x_m": 0.6,
            "entry_z_m": 0.5,
            "exit_x_m": 0.4,
            "exit_z_m": 0.7,
            "dig_cut_tokens": _token(),
            "centerline_physical_cell_ids": [5],
            "swept_physical_cell_ids": [3, 5],
        },
        "execution": {
            "actual_peak_penetration_m": 0.44,
            "contact_bucket_tip_clearance_m": 0.006,
        },
        "trajectory": [
            {
                "observation_step_id": 100,
                "bucket_tip_xyz_m": [0.60, -0.1, 0.50],
                "bucket_tip_plane_depth_m": 0.20,
                "env_state_local_penetration_m": 0.10,
                "typed_bottom_contact": False,
            },
            {
                "observation_step_id": 101,
                "bucket_tip_xyz_m": [0.54, -0.2, 0.56],
                "bucket_tip_plane_depth_m": 0.31,
                "env_state_local_penetration_m": 0.29,
                "typed_bottom_contact": False,
            },
            {
                "observation_step_id": 102,
                "bucket_tip_xyz_m": [0.50, -0.3, 0.60],
                "bucket_tip_plane_depth_m": 0.35,
                "env_state_local_penetration_m": 0.31,
                "typed_bottom_contact": False,
            },
            {
                "observation_step_id": 103,
                "bucket_tip_xyz_m": [0.44, -0.4, 0.64],
                "bucket_tip_plane_depth_m": 0.41,
                "env_state_local_penetration_m": 0.39,
                "typed_bottom_contact": False,
            },
            {
                "observation_step_id": 104,
                "bucket_tip_xyz_m": [0.38, -0.5, 0.68],
                "bucket_tip_plane_depth_m": 0.46,
                "env_state_local_penetration_m": 0.44,
                "typed_bottom_contact": True,
            },
        ],
    }


def _comparison() -> dict[str, object]:
    target = {
        "dig_cut_tokens": _token(),
        "raw_fields": _raw_fields(),
    }
    return {
        "schema": "hard_bottom_goal_comparison_v1",
        "status": "complete_with_policy_replay_blocked",
        "evidence_scope": "teacher_forced_recorded_observation",
        "cycle_index": 5,
        "target_order": ["M0", "E1", "W1"],
        "targets": {
            "M0": {**target, "target_id": "M0"},
            "E1": {**target, "target_id": "E1"},
            "W1": {**target, "target_id": "W1"},
        },
        "recorded_observation_window": {
            "first_action_step_id": 101,
            "last_action_step_id": 104,
            "first_observation_step_id": 100,
            "last_observation_step_id": 103,
            "frame_count": 4,
            "start_removed_depth_grid_m": [0.01, 0.02, 0.03, 0.04, 0.05, 0.06],
        },
    }


def _action(value: float) -> list[float]:
    return [value, -value, value * 0.5, value * 2.0]


def _policy_replay(goal_comparison_path: Path) -> dict[str, object]:
    records = []
    for observation_step_id, value in ((100, 0.1), (101, 0.2), (102, 0.3), (103, 0.4)):
        records.append(
            {
                "observation_step_id": observation_step_id,
                "action_step_id": observation_step_id + 1,
                "fresh_action": _action(value),
                "aggregated_action": _action(value + 0.01),
                "nearest_train_expert_action": _action(value + 0.02),
                "recorded_actual_action": _action(value + 0.01),
            }
        )
    return {
        "schema": "hard_bottom_goal_policy_replay_v1",
        "status": "complete",
        "evidence_scope": "teacher_forced_recorded_observation",
        "target_order": ["M0", "E1", "W1"],
        "recorded_observation_window": {
            "first_action_step_id": 101,
            "last_action_step_id": 104,
            "frame_count": 4,
        },
        "independent_policy_state_contract": {
            "status": "passed",
            "shared_temporal_buffer": False,
        },
        "targets": {
            target_id: {
                "dig_cut_tokens": _token(),
                "records": records,
            }
            for target_id in ("M0", "E1", "W1")
        },
        "source_lock": {
            "goal_comparison": {
                "path": str(goal_comparison_path.resolve()),
                "sha256": _sha256(goal_comparison_path),
            }
        },
    }


def _strict_library() -> dict[str, object]:
    return {
        "schema": "strict_train_coverage_execution_library_v1_1",
        "status": "completed",
        "sample_count": 374,
        "distance_contract": {
            "state_vector": "start_removed_depth_grid_m cells 0..5",
        },
        "tail_audit": {
            "local_max_minus_token_gt_0_02_count": 218,
            "execution_tail_plane_depth_reserve_m": {
                "p50": 0.04,
                "p90": 0.08,
                "p95": 0.10,
                "p99": 0.13,
                "max": 0.16,
            },
            "local_max_minus_token_m": {
                "p50": 0.025,
                "p90": 0.05,
                "p95": 0.06,
                "p99": 0.08,
                "max": 0.11,
            },
        },
        "cell_summary": {
            "4": {
                "leave_one_out_nearest_neighbor_distance_p99": 1.2,
                "leave_one_out_nearest_neighbor_token_rms_residual_p99": 0.09,
            }
        },
        "records": [],
        "source_lineage": {
            "partition": "train",
            "validation_source_episode_ids": [33, 34],
        },
    }


def _write_sources(tmp_path: Path) -> dict[str, Path]:
    root = tmp_path / "diagnosis"
    source_manifest = root / "source_lock_manifest.json"
    _write_json(
        source_manifest,
        {
            "schema": "frozen_failure_artifact_sha256_manifest_v1",
            "status": "frozen",
        },
    )
    diagnosis = root / "cycle6_execution_diagnosis.json"
    comparison = root / "goal_comparison" / "manifest.json"
    replay = root / "goal_comparison" / "policy_replay_v1" / "manifest.json"
    library = tmp_path / "strict_train_coverage_execution_library_v1.json"
    _write_json(diagnosis, _diagnosis(_sha256(source_manifest)))
    _write_json(comparison, _comparison())
    _write_json(replay, _policy_replay(comparison))
    _write_json(library, _strict_library())
    return {
        "diagnosis": diagnosis,
        "comparison": comparison,
        "replay": replay,
        "library": library,
        "source_manifest": source_manifest,
    }


@pytest.fixture
def query_result() -> dict[str, object]:
    return {
        "effect_outcome_cell_id": 4,
        "nearest_exemplar_id": "episode_168",
        "removed_depth_distance": 0.7,
        "removed_depth_distance_p99": 1.2,
        "tuple_consistency_residual_m": 0.14,
        "tuple_consistency_residual_p99_m": 0.09,
        "outcome_cell_tuple_consistency_residual_p99_m": 0.08,
        "raw_field_residuals_from_nearest_exemplar": {
            "operator_cut_length_m": 0.21,
            "operator_cut_depth_peak_m": 0.02,
        },
    }


def test_builds_no_overwrite_contract_recovery_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    query_result: dict[str, object],
) -> None:
    sources = _write_sources(tmp_path)
    monkeypatch.setattr(
        recovery,
        "evaluate_coverage_execution_query",
        lambda *_args, **_kwargs: query_result,
    )

    artifact = build_act_goal_execution_contract_recovery(
        cycle6_diagnosis_path=sources["diagnosis"],
        goal_comparison_path=sources["comparison"],
        policy_replay_path=sources["replay"],
        strict_execution_library_path=sources["library"],
        output_dir=tmp_path / "audit",
    )

    assert artifact["schema"] == ACT_GOAL_EXECUTION_CONTRACT_RECOVERY_SCHEMA
    assert artifact["status"] == "gate_pending"
    assert artifact["evidence_scope"] == "offline_frozen_and_teacher_forced"
    assert artifact["classification"] == {
        "primary": "planner_act_execution_contract_primary",
        "findings": [
            "synthetic_goal_tuple_joint_ood",
            "dig_goal_supervision_horizon_mismatch",
            "effect_outcome_cell_not_safety_geometry",
        ],
    }
    tuple_evidence = artifact["m0_tuple_consistency"]
    assert tuple_evidence["residual"] == pytest.approx(0.14)
    assert tuple_evidence["strict_train_p99"] == pytest.approx(0.09)
    assert tuple_evidence["out_of_strict_train_support"] is True
    assert tuple_evidence["nearest_exemplar_id"] == "episode_168"

    crossing = artifact["target_crossing"]
    assert crossing["observation_step_id"] == 102
    assert crossing["first_post_crossing_action_step_id"] == 103
    assert crossing["planned_depth_m"] == pytest.approx(0.3)
    assert crossing["actual_local_penetration_m"] == pytest.approx(0.31)
    assert crossing["planned_segment_progress_fraction"] == pytest.approx(0.5)
    assert crossing["crossing_to_contact_horizontal_displacement_m"] == (
        pytest.approx(0.144222051, rel=1.0e-6)
    )

    tail = artifact["crossing_to_contact_tail"]
    assert tail["observation_count"] == 3
    assert tail["post_crossing_action_count"] == 2
    assert tail["plane_depth_delta_m"] == pytest.approx(0.11)
    assert tail["plane_depth_peak_minus_crossing_m"] == pytest.approx(0.11)
    assert tail["contact_observation_step_id"] == 104
    action_tail = tail["action_direction_evidence"]
    assert action_tail["fresh_action"]["sample_count"] == 2
    assert action_tail["aggregated_action"]["mean_sign"] == [1, -1, 1, 1]
    assert action_tail["nearest_train_expert_action"]["mean_sign"] == [
        1,
        -1,
        1,
        1,
    ]
    assert action_tail["joint_axes_1_to_3_mean_sign_consensus"] is True

    supervision = artifact["strict_train_supervision_tail"]
    assert supervision["sample_count"] == 374
    assert supervision["local_max_minus_token_gt_0_02_count"] == 218
    assert supervision["local_max_minus_token_gt_0_02_fraction"] == (
        pytest.approx(218 / 374)
    )
    assert supervision["execution_tail_plane_depth_reserve_m"]["p99"] == (
        pytest.approx(0.13)
    )
    shadow = artifact["planned_depth_guard_shadow"]
    assert shadow["mode"] == "shadow_only"
    assert shadow["would_trigger"] is True
    assert shadow["trigger_observation_step_id"] == 102
    assert shadow["runtime_enforced"] is False
    assert shadow["closed_loop_success_claim"] is False

    assert artifact["production_replan_gate"]["status"] == "gate_pending"
    assert artifact["gate"]["formal_a0_1x10_allowed"] is False
    assert artifact["gate"]["next_action"] == (
        "single_factor_planner_act_execution_contract_fix"
    )
    assert set(artifact["source_lock"]) == {
        "cycle6_diagnosis",
        "cycle6_source_manifest",
        "goal_comparison",
        "policy_replay",
        "strict_execution_library",
    }
    assert artifact["source_lock"]["cycle6_diagnosis"]["sha256"] == _sha256(
        sources["diagnosis"]
    )

    output_path = tmp_path / "audit" / MANIFEST_FILENAME
    assert json.loads(output_path.read_text(encoding="utf-8")) == artifact
    with pytest.raises(FileExistsError, match="output directory already exists"):
        build_act_goal_execution_contract_recovery(
            cycle6_diagnosis_path=sources["diagnosis"],
            goal_comparison_path=sources["comparison"],
            policy_replay_path=sources["replay"],
            strict_execution_library_path=sources["library"],
            output_dir=tmp_path / "audit",
        )


def _production_replan(*, selected: bool) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": "coverage_execution_candidate_replan_v1",
        "replan_step_id": 2987,
        "status": "selected" if selected else "no_wall_safe_corridor",
    }
    if selected:
        payload["selected_candidate"] = {
            "corridor_id": 1000168,
            "exemplar_id": "episode_168",
            "source_primitive_episode_id": 168,
            "source_episode_id": 24,
            "effect_outcome_cell_id": 1,
            "return_envelope_cell_id": 0,
            "live_centerline_physical_cell_ids": [3],
            "live_swept_physical_cell_ids": [1, 3],
            "wall_minimum_clearance_m": 0.3736593339760881,
            "planned_hard_bottom_clearance_before_tail_m": (
                0.06416751444339752
            ),
            "execution_tail_plane_depth_reserve_m": 0.0034275054931640625,
            "planned_hard_bottom_budget_after_tail_m": 0.06074000895023346,
        }
    return payload


def test_optional_production_replan_pre_post_is_checked_without_opening_live_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    query_result: dict[str, object],
) -> None:
    sources = _write_sources(tmp_path)
    monkeypatch.setattr(
        recovery,
        "evaluate_coverage_execution_query",
        lambda *_args, **_kwargs: query_result,
    )
    pre = tmp_path / "replan_pre.json"
    post = tmp_path / "replan_post.json"
    _write_json(pre, _production_replan(selected=False))
    _write_json(post, _production_replan(selected=True))

    artifact = build_act_goal_execution_contract_recovery(
        cycle6_diagnosis_path=sources["diagnosis"],
        goal_comparison_path=sources["comparison"],
        policy_replay_path=sources["replay"],
        strict_execution_library_path=sources["library"],
        production_replan_pre_path=pre,
        production_replan_post_path=post,
        output_dir=tmp_path / "audit_with_replan",
    )

    assert artifact["status"] == "completed"
    gate = artifact["production_replan_gate"]
    assert gate["status"] == "passed"
    assert gate["all_checks_passed"] is True
    assert gate["selected_candidate"]["source_exemplar_id"] == "episode_168"
    assert gate["selected_candidate"]["live_swept_physical_cell_ids"] == [1, 3]
    assert all(check["passed"] for check in gate["checks"])
    assert artifact["gate"]["formal_a0_1x10_allowed"] is False


def test_replan_mismatch_fails_closed_and_one_sided_pair_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    query_result: dict[str, object],
) -> None:
    sources = _write_sources(tmp_path)
    monkeypatch.setattr(
        recovery,
        "evaluate_coverage_execution_query",
        lambda *_args, **_kwargs: query_result,
    )
    pre = tmp_path / "replan_pre.json"
    post = tmp_path / "replan_post.json"
    _write_json(pre, _production_replan(selected=False))
    wrong = _production_replan(selected=True)
    selected = wrong["selected_candidate"]
    assert isinstance(selected, dict)
    selected["source_episode_id"] = 25
    _write_json(post, wrong)

    artifact = build_act_goal_execution_contract_recovery(
        cycle6_diagnosis_path=sources["diagnosis"],
        goal_comparison_path=sources["comparison"],
        policy_replay_path=sources["replay"],
        strict_execution_library_path=sources["library"],
        production_replan_pre_path=pre,
        production_replan_post_path=post,
        output_dir=tmp_path / "audit_failed_replan",
    )
    assert artifact["status"] == "gate_failed"
    assert artifact["production_replan_gate"]["status"] == "failed"
    assert artifact["production_replan_gate"]["all_checks_passed"] is False

    with pytest.raises(ValueError, match="must be provided together"):
        build_act_goal_execution_contract_recovery(
            cycle6_diagnosis_path=sources["diagnosis"],
            goal_comparison_path=sources["comparison"],
            policy_replay_path=sources["replay"],
            strict_execution_library_path=sources["library"],
            production_replan_pre_path=pre,
            output_dir=tmp_path / "one_sided_replan",
        )


def test_rejects_source_sha_drift_before_writing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    query_result: dict[str, object],
) -> None:
    sources = _write_sources(tmp_path)
    monkeypatch.setattr(
        recovery,
        "evaluate_coverage_execution_query",
        lambda *_args, **_kwargs: query_result,
    )
    comparison = json.loads(sources["comparison"].read_text(encoding="utf-8"))
    comparison["status"] = "mutated_after_policy_replay"
    _write_json(sources["comparison"], comparison)

    with pytest.raises(ValueError, match="policy replay goal-comparison SHA"):
        build_act_goal_execution_contract_recovery(
            cycle6_diagnosis_path=sources["diagnosis"],
            goal_comparison_path=sources["comparison"],
            policy_replay_path=sources["replay"],
            strict_execution_library_path=sources["library"],
            output_dir=tmp_path / "drifted",
        )
    assert not (tmp_path / "drifted").exists()
