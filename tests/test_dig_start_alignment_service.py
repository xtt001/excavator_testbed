from __future__ import annotations

import numpy as np

from testbed.contracts.primitive_tokens import (
    CUT_ENTRY_X_IDX,
    CUT_ENTRY_Z_IDX,
    DIG_CUT_TOKEN_DIM,
)
from testbed.planner.dig_start_alignment import (
    DigStartAlignmentConfig,
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
