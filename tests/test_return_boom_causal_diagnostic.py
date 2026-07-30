from __future__ import annotations

import numpy as np

from testbed.eval.return_boom_causal_diagnostic import (
    analyze_actuator_trials,
    build_causal_report,
    candidate_similarity_metrics,
    classify_expert_evidence,
)


def test_expert_classification_rejects_contact_contract_outside_support() -> None:
    result = classify_expert_evidence(
        strict_joint_match_count=0,
        runtime_requires_contact=True,
        expert_handoff_count=416,
        expert_contact_match_count=0,
        upper_band_example_count=5,
        upper_band_brake_count=0,
    )

    assert result == "handoff_contract_outside_expert_support"


def test_expert_classification_identifies_supported_braking_mismatch() -> None:
    result = classify_expert_evidence(
        strict_joint_match_count=3,
        runtime_requires_contact=True,
        expert_handoff_count=6,
        expert_contact_match_count=6,
        upper_band_example_count=3,
        upper_band_brake_count=3,
    )

    assert result == "act_temporal_braking_mismatch"


def test_actuator_analysis_accepts_consistent_inverse_mapping() -> None:
    trials = [
        {
            "pose_id": "low",
            "command": 0.15,
            "duration_s": 0.4,
            "qpos_1_start": 0.40,
            "qpos_1_end": 0.388,
            "contact_free": True,
            "finite": True,
        },
        {
            "pose_id": "low",
            "command": -0.15,
            "duration_s": 0.4,
            "qpos_1_start": 0.40,
            "qpos_1_end": 0.412,
            "contact_free": True,
            "finite": True,
        },
        {
            "pose_id": "high",
            "command": 0.15,
            "duration_s": 0.4,
            "qpos_1_start": 0.62,
            "qpos_1_end": 0.610,
            "contact_free": True,
            "finite": True,
        },
        {
            "pose_id": "high",
            "command": -0.15,
            "duration_s": 0.4,
            "qpos_1_start": 0.62,
            "qpos_1_end": 0.630,
            "contact_free": True,
            "finite": True,
        },
    ]

    result = analyze_actuator_trials(
        trials,
        expected_positive_command_qpos_sign=-1,
        maximum_gain_ratio=2.0,
    )

    assert result["status"] == "passed"
    assert result["classification"] == "normal"
    assert result["positive_command_qpos_sign"] == -1
    assert result["cross_pose_gain_ratio"] < 2.0


def test_actuator_analysis_rejects_pose_dependent_sign_flip() -> None:
    trials = [
        {
            "pose_id": "low",
            "command": 0.15,
            "duration_s": 0.4,
            "qpos_1_start": 0.40,
            "qpos_1_end": 0.388,
            "contact_free": True,
            "finite": True,
        },
        {
            "pose_id": "low",
            "command": -0.15,
            "duration_s": 0.4,
            "qpos_1_start": 0.40,
            "qpos_1_end": 0.412,
            "contact_free": True,
            "finite": True,
        },
        {
            "pose_id": "high",
            "command": 0.15,
            "duration_s": 0.4,
            "qpos_1_start": 0.62,
            "qpos_1_end": 0.629,
            "contact_free": True,
            "finite": True,
        },
        {
            "pose_id": "high",
            "command": -0.15,
            "duration_s": 0.4,
            "qpos_1_start": 0.62,
            "qpos_1_end": 0.611,
            "contact_free": True,
            "finite": True,
        },
    ]

    result = analyze_actuator_trials(
        trials,
        expected_positive_command_qpos_sign=-1,
        maximum_gain_ratio=2.0,
    )

    assert result["status"] == "failed"
    assert result["classification"] == "direction_or_gain_anomaly"
    assert "positive_command_direction_mismatch" in result["violations"]


def test_actuator_analysis_fails_closed_on_contact() -> None:
    result = analyze_actuator_trials(
        [
            {
                "pose_id": "middle",
                "command": 0.1,
                "duration_s": 0.2,
                "qpos_1_start": 0.5,
                "qpos_1_end": 0.495,
                "contact_free": False,
                "finite": True,
            },
            {
                "pose_id": "middle",
                "command": -0.1,
                "duration_s": 0.2,
                "qpos_1_start": 0.5,
                "qpos_1_end": 0.505,
                "contact_free": True,
                "finite": True,
            },
        ],
        expected_positive_command_qpos_sign=-1,
        maximum_gain_ratio=2.0,
    )

    assert result["status"] == "failed"
    assert "contact_observed" in result["violations"]
    assert np.isfinite(result["cross_pose_gain_ratio"])


def test_actuator_analysis_fails_closed_on_realign_drift() -> None:
    result = analyze_actuator_trials(
        [
            {
                "pose_id": "middle",
                "command": 0.1,
                "duration_s": 0.2,
                "qpos_1_start": 0.5,
                "qpos_1_end": 0.495,
                "realign_within_0p005": False,
                "contact_free": True,
                "finite": True,
            },
            {
                "pose_id": "middle",
                "command": -0.1,
                "duration_s": 0.2,
                "qpos_1_start": 0.5,
                "qpos_1_end": 0.505,
                "realign_within_0p005": True,
                "contact_free": True,
                "finite": True,
            },
        ],
        expected_positive_command_qpos_sign=-1,
        maximum_gain_ratio=2.0,
    )

    assert result["status"] == "failed"
    assert "realign_pose_drift" in result["violations"]


def test_actuator_analysis_rejects_nonrepeatable_prepared_pose() -> None:
    result = analyze_actuator_trials(
        [
            {
                "pose_id": "upper",
                "command": 0.1,
                "duration_s": 0.2,
                "start_qpos": [0.5, 0.60, 0.69, 0.35],
                "start_qvel": [0.0, 0.0, 0.0, 0.0],
                "qpos_1_start": 0.60,
                "qpos_1_end": 0.595,
                "contact_free": True,
                "finite": True,
            },
            {
                "pose_id": "upper",
                "command": -0.1,
                "duration_s": 0.2,
                "start_qpos": [0.5, 0.61, 0.69, 0.35],
                "start_qvel": [0.0, 0.0, 0.0, 0.0],
                "qpos_1_start": 0.61,
                "qpos_1_end": 0.615,
                "contact_free": True,
                "finite": True,
            },
        ],
        expected_positive_command_qpos_sign=-1,
        maximum_gain_ratio=2.0,
    )

    assert result["status"] == "failed"
    assert "prepared_pose_mismatch:upper" in result["violations"]


def test_actuator_analysis_fails_closed_when_target_pose_is_not_reached() -> None:
    result = analyze_actuator_trials(
        [
            {
                "pose_id": "upper",
                "command": 0.1,
                "duration_s": 0.2,
                "qpos_1_start": 0.60,
                "qpos_1_end": 0.595,
                "pose_target_within_0p005": False,
                "contact_free": True,
                "finite": True,
            },
            {
                "pose_id": "upper",
                "command": -0.1,
                "duration_s": 0.2,
                "qpos_1_start": 0.60,
                "qpos_1_end": 0.605,
                "pose_target_within_0p005": True,
                "contact_free": True,
                "finite": True,
            },
        ],
        expected_positive_command_qpos_sign=-1,
        maximum_gain_ratio=2.0,
    )

    assert result["status"] == "failed"
    assert "prepared_pose_target_drift" in result["violations"]


def test_candidate_similarity_uses_physical_token_scales_and_contact() -> None:
    anchor = {
        "return_target_tokens": [
            0.25,
            -0.50,
            0.10,
            -0.40,
            -1.0,
            0.0,
            0.25,
            0.50,
            0.75,
            1.0,
        ],
        "return_start_envelope_tokens": [
            -0.50,
            0.20,
            0.01,
            0.20,
            0.00,
            0.04,
            0.00,
            0.55,
            0.63,
            0.34,
            0.21,
            0.02,
            0.03,
            0.02,
            0.02,
            0.10,
            1.00,
            1.00,
        ],
        "qpos": [0.55, 0.63, 0.34, 0.21],
        "qvel": [0.0, 0.20, -0.18, 0.10],
        "runtime_requires_contact": True,
        "runtime_local_depth_min_m": 0.001,
        "runtime_local_depth_max_m": 0.04,
    }
    expert = {
        "return_target_tokens": [
            0.30,
            -0.50,
            0.10,
            -0.45,
            -1.0,
            0.0,
            0.30,
            0.55,
            0.80,
            1.0,
        ],
        "return_start_envelope_tokens": [
            -0.45,
            0.25,
            0.02,
            0.20,
            0.00,
            0.05,
            0.00,
            0.56,
            0.61,
            0.35,
            0.20,
            0.03,
            0.03,
            0.02,
            0.02,
            0.11,
            1.00,
            1.00,
        ],
        "qpos": [0.56, 0.61, 0.35, 0.20],
        "qvel": [0.01, 0.17, -0.16, 0.08],
        "handoff_contact": False,
        "handoff_local_depth_m": 0.02,
    }

    metrics = candidate_similarity_metrics(anchor=anchor, expert=expert)

    assert np.isclose(metrics["entry_distance_m"], 0.1)
    assert np.isclose(metrics["exit_distance_m"], 0.1)
    assert np.isclose(metrics["length_abs_delta_m"], 0.1)
    assert np.isclose(metrics["depth_abs_delta_m"], 0.04)
    assert np.isclose(metrics["payload_abs_delta_kg"], 3.0)
    assert metrics["state_close"]
    assert metrics["target_close"]
    assert metrics["return_envelope_close"]
    assert metrics["depth_gate_match"]
    assert metrics["runtime_envelope_contact_override_conflict"]
    assert not metrics["envelope_contact_requirement_match"]
    assert not metrics["contact_requirement_match"]
    assert not metrics["strict_joint_match"]


def test_joint_report_prefers_contract_mismatch_when_unity_is_normal() -> None:
    report = build_causal_report(
        expert_audit={
            "schema": "strict18_return_boom_expert_action_support_v1",
            "status": "passed",
            "classification": "handoff_contract_outside_expert_support",
            "anchor": {
                "act_action": [0.0, -0.55, 0.0, 0.0],
                "qvel": [0.0, 0.21, 0.0, 0.0],
            },
            "expert_support": {
                "all_partition_handoff_count": 416,
                "same_cell_handoff_count": 81,
                "same_cell_strict_joint_match_count": 0,
            },
        },
        actuator_audit={
            "schema": "unity_boom_actuator_response_diagnostic_v1",
            "status": "passed",
            "classification": "normal",
            "analysis": {
                "cross_pose_gain_ratio": 1.12,
                "violations": [],
                "pose_summaries": [
                    {
                        "pose_id": "upper",
                        "negative": {
                            "command": -0.10,
                            "qpos_response_sign": 1,
                            "qvel_1_tail_mean_abs": 0.038,
                        },
                    }
                ],
            },
        },
    )

    assert report["status"] == "passed"
    assert (
        report["causal_classification"]
        == "return_handoff_contract_outside_expert_support"
    )
    assert report["production_change_allowed"] is False
    assert report["retraining_allowed"] is False
    assert np.isclose(
        report["evidence_summary"]["unity_scaled_anchor_qvel_1"],
        0.209,
    )
    assert np.isclose(
        report["evidence_summary"]["anchor_qvel_1_abs_error"],
        0.001,
    )
