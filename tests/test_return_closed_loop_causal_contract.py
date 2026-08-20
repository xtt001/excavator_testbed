from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest

from testbed.data.recorded_return_closed_loop_fixture import (
    RecordedReturnClosedLoopFixture,
    RecordedReturnClosedLoopFixtureSet,
    RecordedReturnImageLineage,
    RecordedReturnInitialObservation,
    RecordedReturnTargetCondition,
)
from testbed.eval.return_closed_loop_causal_contract import (
    LATEST_CURRENT_CHUNK_DIAGNOSTIC,
    LEGACY_TEMPORAL_DISPATCH,
    RETURN_CLOSED_LOOP_MAX_STEPS,
    ReturnFixtureApplicationCapabilities,
    ReturnFixtureAppliedState,
    ReturnSafetyFacts,
    assess_return_action_continuity,
    assess_return_fixture_match,
    assess_return_target_envelope,
    build_return_closed_loop_causal_contract,
    classify_return_closed_loop_safety,
    measure_return_trajectory_separation,
    return_target_envelope_from_token,
)

CAMERAS = ("stick_up", "stick_down", "eye_left", "eye_right")


def _target(role: str, value: float) -> RecordedReturnTargetCondition:
    token = np.zeros(18, dtype=np.float32)
    token[:2] = [value, value + 0.1]
    token[2:6] = [0.02, 0.20, 0.0, 0.08]
    token[6] = 0.0
    token[7:11] = [0.5, 0.6, 0.4, 0.2]
    token[11:15] = [0.02, 0.05, 0.03, 0.02]
    token[15:] = [0.5, 1.0, 1.0]
    return RecordedReturnTargetCondition(
        target_role=role,
        segment_id=f"return:{role}:{value}",
        token_source=f"source_{role}",
        token_sha256=hashlib.sha256(
            np.asarray(token, dtype="<f4").tobytes()
        ).hexdigest(),
        token=token,
    )


def _fixture(fixture_id: str, role: str) -> RecordedReturnClosedLoopFixture:
    original_target = _target("original", 0.0)
    alternate_target = _target("alternate", 0.5)
    observation = RecordedReturnInitialObservation(
        action_step_id=10,
        observation_step_id=9,
        hdf5_observation_index=0,
        qpos=np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
        qvel=np.asarray([-0.1, 0.0, 0.1, 0.2], dtype=np.float32),
        env_state=np.linspace(0.0, 1.0, 107, dtype=np.float32),
        image_lineage=tuple(
            RecordedReturnImageLineage(
                camera_name=name,
                shape=(4, 6, 3),
                encoded_jpeg_size_bytes=100 + index,
                encoded_jpeg_sha256=f"{index + 1:064x}",
                rgb_sha256=f"{index + 5:064x}",
            )
            for index, name in enumerate(CAMERAS)
        ),
    )
    return RecordedReturnClosedLoopFixture(
        fixture_id=fixture_id,
        evidence_role=role,
        source_segment_id=original_target.segment_id,
        expected_classification=(
            "goal_response_invalid"
            if role == "offline_failed"
            else "goal_response_plausible"
        ),
        initial_observation=observation,
        original_target=original_target,
        alternate_target=alternate_target,
    )


def _fixture_set() -> RecordedReturnClosedLoopFixtureSet:
    return RecordedReturnClosedLoopFixtureSet(
        schema="recorded_return_closed_loop_fixture_set_v1",
        camera_names=CAMERAS,
        source_lineage={"manifest_sha256": "a" * 64},
        fixtures=(
            _fixture("F1", "offline_failed"),
            _fixture("N1", "offline_normal"),
            _fixture("F2", "offline_failed"),
            _fixture("N2", "offline_normal"),
        ),
    )


def test_contract_freezes_exact_16_return_only_no_retry_arms() -> None:
    contract = build_return_closed_loop_causal_contract(_fixture_set())

    assert len(contract.arms) == 16
    assert {arm.dispatch_strategy_id for arm in contract.arms} == {
        LEGACY_TEMPORAL_DISPATCH,
        LATEST_CURRENT_CHUNK_DIAGNOSTIC,
    }
    assert all(arm.allowed_primitive == "return" for arm in contract.arms)
    assert all(
        arm.forbidden_primitives == ("dig", "carry", "dump") for arm in contract.arms
    )
    assert all(
        arm.max_steps == RETURN_CLOSED_LOOP_MAX_STEPS == 420 for arm in contract.arms
    )
    assert all(arm.no_retry for arm in contract.arms)
    latest = contract.dispatch_strategies[LATEST_CURRENT_CHUNK_DIAGNOSTIC]
    assert latest.dispatch_api == "predict_action_chunk.first_action_each_frame"
    assert latest.diagnostic_only is True
    assert latest.promotion_eligible is False
    assert contract.runtime_default_changed is False
    assert contract.official_handoff_evaluator_required is True
    assert contract.as_dict()["arm_count"] == 16
    json.dumps(contract.as_dict(), allow_nan=False)


def test_fixture_match_requires_actual_qpos_and_qvel_application() -> None:
    reference = _fixture("F1", "offline_failed").initial_observation
    applied = ReturnFixtureAppliedState(
        qpos=reference.qpos.copy(),
        qvel=reference.qvel.copy(),
        env_state=reference.env_state.copy(),
        image_rgb_sha256={
            item.camera_name: item.rgb_sha256 for item in reference.image_lineage
        },
    )
    missing_qvel = assess_return_fixture_match(
        reference=reference,
        applied=applied,
        capabilities=ReturnFixtureApplicationCapabilities(
            full_reset_applied=True,
            qpos_actual_applied=True,
            qvel_actual_applied=False,
            observable_terrain_available=True,
            camera_observation_available=True,
            scene_actual_applied=True,
            physics_seed_actual_applied=True,
            terrain_state_actual_applied=True,
            terrain_restore_mode="full_terrain_snapshot",
        ),
    )
    assert missing_qvel.matched is False
    assert "qvel_not_actual_applied" in missing_qvel.failures

    passed = assess_return_fixture_match(
        reference=reference,
        applied=applied,
        capabilities=ReturnFixtureApplicationCapabilities(
            full_reset_applied=True,
            qpos_actual_applied=True,
            qvel_actual_applied=True,
            observable_terrain_available=True,
            camera_observation_available=True,
            scene_actual_applied=True,
            physics_seed_actual_applied=True,
            terrain_state_actual_applied=True,
            terrain_restore_mode="full_terrain_snapshot",
        ),
    )
    assert passed.matched is True

    observable_only = assess_return_fixture_match(
        reference=reference,
        applied=applied,
        capabilities=ReturnFixtureApplicationCapabilities(
            full_reset_applied=True,
            qpos_actual_applied=True,
            qvel_actual_applied=True,
            observable_terrain_available=True,
            camera_observation_available=True,
            scene_actual_applied=True,
            physics_seed_actual_applied=True,
            terrain_state_actual_applied=True,
        ),
    )
    assert observable_only.matched is False
    assert "terrain_restore_unsupported_observable_only" in observable_only.failures


def test_target_envelope_trajectory_and_action_metrics_are_frozen_pure_functions() -> (
    None
):
    envelope = return_target_envelope_from_token(_target("original", 0.0).token)
    hit = assess_return_target_envelope(
        envelope=envelope,
        long_norm=0.0,
        short_norm=0.1,
        local_depth_m=0.02,
        qpos=np.asarray([0.5, 0.6, 0.4, 0.2], dtype=np.float32),
        qvel=np.asarray([0.1, -0.1, 0.0, 0.2], dtype=np.float32),
        dig_contact=False,
    )
    assert hit.entered is True
    assert hit.as_dict()["assessment_kind"] == "direct_token_geometry_only"
    assert hit.as_dict()["official_handoff_ready"] is None
    miss = assess_return_target_envelope(
        envelope=envelope,
        long_norm=0.5,
        short_norm=0.5,
        local_depth_m=0.02,
        qpos=np.asarray([0.5, 0.6, 0.4, 0.2], dtype=np.float32),
        qvel=np.zeros(4, dtype=np.float32),
        dig_contact=False,
    )
    assert miss.entered is False
    assert "tip_radius" in miss.failed_checks

    original = np.zeros((8, 3), dtype=np.float32)
    alternate = np.zeros((8, 3), dtype=np.float32)
    alternate[3:, 0] = 0.03
    separation = measure_return_trajectory_separation(original, alternate)
    assert separation.separated is True
    assert separation.first_separation_frame == 3

    actions = np.asarray([[0.0, 0.0], [0.1, 0.0], [1.0, -1.1]], dtype=np.float32)
    quality = assess_return_action_continuity(
        actions,
        discontinuity_threshold=np.asarray([0.5, 0.5], dtype=np.float32),
    )
    assert quality.boundary_touch_count == 2
    assert quality.boundary_exceed_count == 1
    assert quality.discontinuity_count == 1
    np.testing.assert_allclose(quality.mean_abs_delta_by_axis, [0.5, 0.55])
    np.testing.assert_allclose(quality.max_abs_delta_by_axis, [0.9, 1.1])
    assert quality.p95_abs_delta_by_axis[0] < quality.max_abs_delta_by_axis[0]


def test_safety_classification_is_fail_closed_and_requires_neutral_ack() -> None:
    invalid = classify_return_closed_loop_safety(
        ReturnSafetyFacts(
            forbidden_primitive_dispatched=True,
            neutral_requested=False,
            neutral_acknowledged=False,
        )
    )
    assert invalid.classification == "artifact_invalid"

    missing_ack = classify_return_closed_loop_safety(
        ReturnSafetyFacts(
            hard_safety_stop=True,
            collision_detected=True,
            neutral_requested=True,
            neutral_acknowledged=False,
        )
    )
    assert missing_ack.classification == "artifact_invalid"
    assert "neutral_ack_missing" in missing_ack.reasons

    safe = classify_return_closed_loop_safety(
        ReturnSafetyFacts(
            handoff_would_fire=True,
            neutral_requested=True,
            neutral_acknowledged=True,
        )
    )
    assert safe.classification == "bounded_return_handoff_observed"
    assert safe.safe is True


def test_invalid_return_token_contract_fails_before_motion() -> None:
    token = _target("original", 0.0).token.copy()
    token[16] = 0.0
    with pytest.raises(ValueError, match="valid"):
        return_target_envelope_from_token(token)
