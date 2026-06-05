from __future__ import annotations

import numpy as np

from testbed.contracts.primitive_tokens import (
    CUT_ENTRY_X_IDX,
    CUT_ENTRY_Z_IDX,
    DIG_CUT_TOKEN_DIM,
)
from testbed.planner.dig_start_alignment import (
    DigStartAlignmentConfig,
    DigStartAlignmentFacts,
    DigStartAlignmentService,
    pd_servo_action,
)


def _config(**overrides: object) -> DigStartAlignmentConfig:
    values = {
        "action_dim": 4,
        "qpos_min": np.asarray([-1.0, -1.0, -1.0, -1.0], dtype=np.float32),
        "qpos_max": np.asarray([1.0, 1.0, 1.0, 1.0], dtype=np.float32),
        "qpos_from_token_coefficients": np.asarray(
            [
                [0.0, 2.0, 0.0],
                [0.0, 0.0, 3.0],
                [0.0, 1.0, 1.0],
                [0.0, 0.0, 0.0],
            ],
            dtype=np.float32,
        ),
        "controlled_dims": np.asarray([True, True, True, False]),
        "entry_intent_controlled_dims": None,
        "bucket_target_qpos": None,
        "kp": 2.0,
        "kd": 0.5,
        "action_clip": np.asarray([1.0, 1.0, 0.5, 1.0], dtype=np.float32),
        "action_signs": np.asarray([1.0, -1.0, 1.0, 1.0], dtype=np.float32),
    }
    values.update(overrides)
    return DigStartAlignmentConfig(**values)


def _token(entry_x: float = 0.4, entry_z: float = -0.3) -> np.ndarray:
    token = np.zeros(DIG_CUT_TOKEN_DIM, dtype=np.float32)
    token[CUT_ENTRY_X_IDX] = float(entry_x)
    token[CUT_ENTRY_Z_IDX] = float(entry_z)
    return token


def test_target_from_token_clips_and_preserves_uncontrolled_dims() -> None:
    service = DigStartAlignmentService()
    target = service.target_from_token(
        token=_token(entry_x=0.8, entry_z=-0.5),
        qpos=np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
        config=_config(),
    )
    np.testing.assert_allclose(
        target,
        np.asarray([1.0, -1.0, 0.3, 0.4], dtype=np.float32),
        atol=1.0e-6,
    )


def test_target_from_token_can_hold_non_intent_axes() -> None:
    service = DigStartAlignmentService()
    target = service.target_from_token(
        token=_token(entry_x=0.4, entry_z=-0.3),
        qpos=np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
        config=_config(
            controlled_dims=np.asarray([True, True, True, True]),
            entry_intent_controlled_dims=np.asarray(
                [True, False, False, False],
                dtype=bool,
            ),
            bucket_target_qpos=0.0,
        ),
    )
    np.testing.assert_allclose(
        target,
        np.asarray([0.8, 0.2, 0.3, 0.4], dtype=np.float32),
        atol=1.0e-6,
    )


def test_target_from_token_applies_bucket_target_when_bucket_is_controlled() -> None:
    service = DigStartAlignmentService()
    target = service.target_from_token(
        token=_token(entry_x=0.4, entry_z=-0.3),
        qpos=np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
        config=_config(
            controlled_dims=np.asarray([True, True, True, True]),
            bucket_target_qpos=-0.2,
        ),
    )
    assert target[3] == np.float32(-0.2)


def test_action_for_target_applies_pd_clip_signs_and_control_mask() -> None:
    service = DigStartAlignmentService()
    action = service.action_for_target(
        qpos=np.zeros(4, dtype=np.float32),
        qvel=np.ones(4, dtype=np.float32),
        target_qpos=np.ones(4, dtype=np.float32),
        config=_config(
            controlled_dims=np.asarray([True, False, True, False]),
        ),
    )
    np.testing.assert_allclose(
        action,
        np.asarray([1.0, 0.0, 0.5, 0.0], dtype=np.float32),
        atol=1.0e-6,
    )


def test_pd_servo_action_preserves_legacy_clip_and_sign_semantics() -> None:
    action = pd_servo_action(
        qpos=np.zeros(4, dtype=np.float32),
        qvel=np.ones(4, dtype=np.float32),
        target_qpos=np.ones(4, dtype=np.float32),
        kp=2.0,
        kd=0.5,
        action_clip=np.asarray([1.0, 1.0, 0.5, 1.0], dtype=np.float32),
        action_signs=np.asarray([1.0, -1.0, 1.0, 1.0], dtype=np.float32),
    )
    np.testing.assert_allclose(
        action,
        np.asarray([1.0, -1.0, 0.5, 1.0], dtype=np.float32),
        atol=1.0e-6,
    )


def test_entry_close_threshold_handles_none_and_nan() -> None:
    service = DigStartAlignmentService()
    assert service.entry_close(float("nan"), threshold=None)
    assert not service.entry_close(float("nan"), threshold=0.1)
    assert service.entry_close(0.1, threshold=0.1)
    assert not service.entry_close(0.11, threshold=0.1)


def test_start_envelope_requires_entry_qpos_and_pose() -> None:
    service = DigStartAlignmentService()
    config = _config(
        start_envelope_enabled=True,
        start_envelope_max_entry_error_m=0.65,
        start_qpos_min=np.asarray([0.0, 0.0, 0.0, 0.0], dtype=np.float32),
        start_qpos_max=np.asarray([1.0, 1.0, 1.0, 1.0], dtype=np.float32),
        start_pose_min=np.asarray([-0.6, -0.3, -1.5], dtype=np.float32),
        start_pose_max=np.asarray([1.65, 0.25, 1.2], dtype=np.float32),
    )
    facts = DigStartAlignmentFacts(
        qpos=np.asarray([0.5, 0.6, 0.1, 0.0], dtype=np.float32),
        qvel=np.zeros(4, dtype=np.float32),
        entry_error_m=0.4,
        bucket_pose=(0.5, 0.0, -0.5),
    )
    assert service.start_envelope_ready(facts, config)
    assert not service.start_envelope_ready(
        DigStartAlignmentFacts(
            qpos=np.asarray([1.2, 0.6, 0.1, 0.0], dtype=np.float32),
            qvel=np.zeros(4, dtype=np.float32),
            entry_error_m=0.4,
            bucket_pose=(0.5, 0.0, -0.5),
        ),
        config,
    )
    assert not service.start_envelope_ready(
        DigStartAlignmentFacts(
            qpos=np.asarray([0.5, 0.6, 0.1, 0.0], dtype=np.float32),
            qvel=np.zeros(4, dtype=np.float32),
            entry_error_m=0.8,
            bucket_pose=(0.5, 0.0, -0.5),
        ),
        config,
    )
    assert not service.start_envelope_ready(
        DigStartAlignmentFacts(
            qpos=np.asarray([0.5, 0.6, 0.1, 0.0], dtype=np.float32),
            qvel=np.zeros(4, dtype=np.float32),
            entry_error_m=0.4,
            bucket_pose=(2.0, 0.0, -0.5),
        ),
        config,
    )


def test_first_dig_entry_close_handoff_requires_cycle_start_envelope_and_qvel() -> None:
    service = DigStartAlignmentService()
    config = _config(
        start_envelope_enabled=True,
        first_dig_entry_close_handoff=True,
        first_dig_entry_close_handoff_qvel_abs_max=0.15,
        max_entry_error_m=0.35,
    )
    facts = DigStartAlignmentFacts(
        qpos=np.zeros(4, dtype=np.float32),
        qvel=np.asarray([0.0, 0.03, -0.10, -0.02], dtype=np.float32),
        entry_error_m=0.20,
        cycle_index=0,
    )
    assert service.entry_close_handoff_ready(
        facts=facts,
        config=config,
        start_envelope_ready=True,
    )
    assert not service.entry_close_handoff_ready(
        facts=DigStartAlignmentFacts(
            qpos=np.zeros(4, dtype=np.float32),
            qvel=facts.qvel,
            entry_error_m=0.20,
            cycle_index=1,
        ),
        config=config,
        start_envelope_ready=True,
    )
    assert not service.entry_close_handoff_ready(
        facts=facts,
        config=config,
        start_envelope_ready=False,
    )
    assert not service.entry_close_handoff_ready(
        facts=DigStartAlignmentFacts(
            qpos=np.zeros(4, dtype=np.float32),
            qvel=np.asarray([0.0, 0.03, -0.20, -0.02], dtype=np.float32),
            entry_error_m=0.20,
            cycle_index=0,
        ),
        config=config,
        start_envelope_ready=True,
    )


def test_entry_intent_handoff_ignores_entry_close_when_intent_axes_stable() -> None:
    service = DigStartAlignmentService()
    config = _config(
        enabled=True,
        controlled_dims=np.asarray([True, True, True, True]),
        entry_intent_controlled_dims=np.asarray(
            [True, False, False, False],
            dtype=bool,
        ),
        entry_intent_handoff_enabled=True,
        qpos_tolerance=np.asarray([0.05, 0.05, 0.05, 0.05], dtype=np.float32),
        max_entry_error_m=0.01,
        hold_steps=1,
    )
    decision = service.ready(
        DigStartAlignmentFacts(
            qpos=np.zeros(4, dtype=np.float32),
            qvel=np.zeros(4, dtype=np.float32),
            target_qpos=np.zeros(4, dtype=np.float32),
            entry_error_m=0.20,
            hold_count=0,
        ),
        config,
    )
    assert decision.ready
    assert decision.entry_intent_handoff_ready
    assert not decision.entry_close


def test_timeout_decision_returns_no_gate_intent_and_close_enough_reasons() -> None:
    service = DigStartAlignmentService()
    no_gate = service.timeout_can_handoff(
        DigStartAlignmentFacts(
            qpos=np.zeros(4, dtype=np.float32),
            qvel=np.zeros(4, dtype=np.float32),
            entry_error_m=float("nan"),
        ),
        _config(timeout_accept_entry_error_m=None, max_entry_error_m=None),
    )
    assert no_gate.ready
    assert no_gate.reason == "pre_dig_align_to_dig_timeout_no_entry_gate"

    intent = service.timeout_can_handoff(
        DigStartAlignmentFacts(
            qpos=np.zeros(4, dtype=np.float32),
            qvel=np.zeros(4, dtype=np.float32),
            entry_error_m=1.0,
        ),
        _config(
            timeout_accept_entry_error_m=0.01,
            entry_intent_handoff_enabled=True,
            entry_intent_controlled_dims=np.asarray(
                [True, False, False, False],
                dtype=bool,
            ),
            controlled_dims=np.asarray([True, True, True, True]),
        ),
    )
    assert intent.ready
    assert intent.reason == "pre_dig_align_to_dig_timeout_intent_aligned"

    close = service.timeout_can_handoff(
        DigStartAlignmentFacts(
            qpos=np.zeros(4, dtype=np.float32),
            qvel=np.zeros(4, dtype=np.float32),
            entry_error_m=0.01,
        ),
        _config(timeout_accept_entry_error_m=0.01),
    )
    assert close.ready
    assert close.reason == "pre_dig_align_to_dig_timeout_close_enough"


def test_surface_guard_trigger_and_handoff_threshold() -> None:
    service = DigStartAlignmentService()
    config = _config(
        enabled=True,
        surface_guard_enabled=True,
        surface_guard_max_penetration_m=0.005,
        surface_guard_handoff_entry_error_m=0.35,
    )
    triggered = service.surface_guard_triggered(
        DigStartAlignmentFacts(
            qpos=np.zeros(4, dtype=np.float32),
            qvel=np.zeros(4, dtype=np.float32),
            surface_depth_m=0.03,
        ),
        config,
    )
    assert triggered.triggered
    assert np.isclose(triggered.surface_depth_m, 0.03)
    fallback = service.surface_guard_triggered(
        DigStartAlignmentFacts(
            qpos=np.zeros(4, dtype=np.float32),
            qvel=np.zeros(4, dtype=np.float32),
            surface_depth_m=float("nan"),
            contact_mask=True,
        ),
        config,
    )
    assert fallback.triggered
    assert service.surface_guard_can_handoff(
        DigStartAlignmentFacts(
            qpos=np.zeros(4, dtype=np.float32),
            qvel=np.zeros(4, dtype=np.float32),
            entry_error_m=0.20,
        ),
        config,
    )
    assert not service.surface_guard_can_handoff(
        DigStartAlignmentFacts(
            qpos=np.zeros(4, dtype=np.float32),
            qvel=np.zeros(4, dtype=np.float32),
            entry_error_m=0.40,
        ),
        config,
    )
