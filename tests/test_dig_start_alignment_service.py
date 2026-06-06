from __future__ import annotations

import numpy as np
import pytest

from testbed.contracts.primitive_tokens import (
    CUT_ENTRY_X_IDX,
    CUT_ENTRY_Z_IDX,
    DIG_CUT_TOKEN_DIM,
)
from testbed.data.schema import (
    ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX,
)
from testbed.planner import (
    dig_start_alignment as dig_start_alignment_module,
)
from testbed.planner import (
    dig_start_alignment_action,
    dig_start_alignment_context,
    dig_start_alignment_outcome,
    dig_start_alignment_readiness,
    dig_start_alignment_runtime,
)
from testbed.planner.dig_start_alignment import (
    DIG_START_ALIGNMENT_DEBUG_STATE_FIELDS,
    DIG_START_ALIGNMENT_RUNTIME_STATE_FIELDS,
    DigStartAlignmentDebugState,
    DigStartAlignmentRuntimeState,
    DigStartAlignmentService,
    debug_state_from_mapping,
    runtime_state_from_mapping,
)
from testbed.planner.dig_start_alignment_action import (
    AlignmentActionDecision,
    pd_servo_action,
)
from testbed.planner.dig_start_alignment_context import (
    DIG_START_ALIGNMENT_FACT_FIELDS,
    DIG_START_ALIGNMENT_RUNTIME_CONFIG_FIELDS,
    DigStartAlignmentConfig,
    DigStartAlignmentEntryErrorFacts,
    DigStartAlignmentFacts,
    build_dig_start_alignment_entry_error_facts_from_observation_view,
    build_dig_start_alignment_facts,
    build_dig_start_alignment_facts_from_mapping,
    build_dig_start_alignment_facts_from_observation_view,
    build_dig_start_alignment_runtime_config,
    build_dig_start_alignment_runtime_config_from_mapping,
    dig_start_alignment_entry_error,
)
from testbed.planner.dig_start_alignment_outcome import (
    PreDigAlignOutcome,
    PreDigAlignOutcomeRuntimeFacts,
)
from testbed.planner.dig_start_alignment_readiness import (
    AlignmentReadyDecision,
    PreDigAlignTimeoutHandoffRequest,
    SurfaceGuardDecision,
    TimeoutHandoffDecision,
)
from testbed.planner.snapshots import build_planner_snapshot


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


def test_dig_start_alignment_reexports_outcome_symbols_for_compatibility() -> None:
    assert dig_start_alignment_module.PreDigAlignOutcome is (
        dig_start_alignment_outcome.PreDigAlignOutcome
    )
    assert dig_start_alignment_module.PreDigAlignOutcomeRuntimeFacts is (
        dig_start_alignment_outcome.PreDigAlignOutcomeRuntimeFacts
    )
    assert dig_start_alignment_module.PreDigAlignOutcomeRequest is (
        dig_start_alignment_outcome.PreDigAlignOutcomeRequest
    )
    assert issubclass(
        DigStartAlignmentService,
        dig_start_alignment_outcome.DigStartAlignmentOutcomeService,
    )


def test_dig_start_alignment_reexports_context_symbols_for_compatibility() -> None:
    assert dig_start_alignment_module.DigStartAlignmentConfig is (
        dig_start_alignment_context.DigStartAlignmentConfig
    )
    assert dig_start_alignment_module.DigStartAlignmentFacts is (
        dig_start_alignment_context.DigStartAlignmentFacts
    )
    assert dig_start_alignment_module.DigStartAlignmentEntryErrorFacts is (
        dig_start_alignment_context.DigStartAlignmentEntryErrorFacts
    )
    assert dig_start_alignment_module.DIG_START_ALIGNMENT_RUNTIME_CONFIG_FIELDS is (
        dig_start_alignment_context.DIG_START_ALIGNMENT_RUNTIME_CONFIG_FIELDS
    )
    assert dig_start_alignment_module.DIG_START_ALIGNMENT_FACT_FIELDS is (
        dig_start_alignment_context.DIG_START_ALIGNMENT_FACT_FIELDS
    )
    assert dig_start_alignment_module.build_dig_start_alignment_runtime_config is (
        dig_start_alignment_context.build_dig_start_alignment_runtime_config
    )
    assert dig_start_alignment_module.build_dig_start_alignment_facts is (
        dig_start_alignment_context.build_dig_start_alignment_facts
    )
    assert (
        dig_start_alignment_module.build_dig_start_alignment_facts_from_observation_view
        is dig_start_alignment_context.build_dig_start_alignment_facts_from_observation_view
    )
    assert (
        dig_start_alignment_module.build_dig_start_alignment_entry_error_facts_from_observation_view
        is dig_start_alignment_context.build_dig_start_alignment_entry_error_facts_from_observation_view
    )
    assert dig_start_alignment_module.dig_start_alignment_entry_error is (
        dig_start_alignment_context.dig_start_alignment_entry_error
    )


def test_dig_start_alignment_reexports_readiness_symbols_for_compatibility() -> None:
    assert dig_start_alignment_module.SurfaceGuardDecision is (
        dig_start_alignment_readiness.SurfaceGuardDecision
    )
    assert dig_start_alignment_module.AlignmentReadyDecision is (
        dig_start_alignment_readiness.AlignmentReadyDecision
    )
    assert dig_start_alignment_module.TimeoutHandoffDecision is (
        dig_start_alignment_readiness.TimeoutHandoffDecision
    )
    assert dig_start_alignment_module.PreDigAlignTimeoutHandoffRequest is (
        dig_start_alignment_readiness.PreDigAlignTimeoutHandoffRequest
    )
    assert issubclass(
        DigStartAlignmentService,
        dig_start_alignment_readiness.DigStartAlignmentReadinessService,
    )


def test_dig_start_alignment_reexports_action_symbols_for_compatibility() -> None:
    assert dig_start_alignment_module.AlignmentActionDecision is (
        dig_start_alignment_action.AlignmentActionDecision
    )
    assert dig_start_alignment_module.pd_servo_action is (
        dig_start_alignment_action.pd_servo_action
    )
    assert issubclass(
        DigStartAlignmentService,
        dig_start_alignment_action.DigStartAlignmentActionService,
    )


def test_dig_start_alignment_reexports_runtime_service_for_compatibility() -> None:
    assert dig_start_alignment_module.DigStartAlignmentRuntimeService is (
        dig_start_alignment_runtime.DigStartAlignmentRuntimeService
    )
    assert issubclass(
        DigStartAlignmentService,
        dig_start_alignment_runtime.DigStartAlignmentRuntimeService,
    )


def test_build_dig_start_alignment_runtime_config_preserves_legacy_projection() -> None:
    values = {
        "action_dim": "4",
        "qpos_min": np.asarray([-1.0, -0.9, -0.8, -0.7], dtype=np.float64),
        "qpos_max": np.asarray([1.0, 0.9, 0.8, 0.7], dtype=np.float64),
        "qpos_from_token_coefficients": np.arange(12, dtype=np.float64).reshape(4, 3),
        "controlled_dims": np.asarray([True, False, True, False]),
        "entry_intent_controlled_dims": np.asarray([False, True, False, True]),
        "bucket_target_qpos": "-0.25", "kp": "11.0", "kd": "0.5",
        "action_clip": [0.1, 0.2, 0.3, 0.4],
        "action_signs": [1.0, -1.0, 1.0, -1.0],
        "enabled": 1,
        "qpos_tolerance": np.asarray([0.01, 0.02, 0.03, 0.04]),
        "qvel_abs_max": "0.12", "hold_steps": "3",
        "max_entry_error_m": "0.55",
        "timeout_accept_entry_error_m": "0.25",
        "start_envelope_enabled": 1,
        "start_envelope_max_entry_error_m": "0.65",
        "first_dig_entry_close_handoff": 1,
        "first_dig_entry_close_handoff_qvel_abs_max": "0.07",
        "entry_intent_handoff_enabled": 1,
        "surface_guard_enabled": 1,
        "surface_guard_max_penetration_m": "0.005",
        "surface_guard_handoff_entry_error_m": "0.35",
        "surface_guard_use_contact_fallback": 0,
        "start_qpos_min": np.asarray([-0.5, -0.4, -0.3, -0.2]),
        "start_qpos_max": np.asarray([0.5, 0.4, 0.3, 0.2]),
        "start_pose_min": np.asarray([-0.6, -0.7]),
        "start_pose_max": np.asarray([0.6, 0.7]),
    }

    direct = build_dig_start_alignment_runtime_config(**values)
    config = build_dig_start_alignment_runtime_config_from_mapping(
        {**values, "ignored": object()}
    )
    for key in values:
        assert getattr(config, key) is getattr(direct, key) or getattr(
            config, key
        ) == getattr(direct, key)
    assert {key for key, _ in DIG_START_ALIGNMENT_RUNTIME_CONFIG_FIELDS} == set(
        values
    )

    assert config.action_dim == 4
    assert config.qpos_min is values["qpos_min"]
    assert config.qpos_max is values["qpos_max"]
    assert config.qpos_from_token_coefficients is values[
        "qpos_from_token_coefficients"
    ]
    assert config.controlled_dims is values["controlled_dims"]
    assert config.entry_intent_controlled_dims is values[
        "entry_intent_controlled_dims"
    ]
    assert config.bucket_target_qpos == "-0.25"
    assert config.kp == pytest.approx(11.0)
    assert config.kd == pytest.approx(0.5)
    assert config.action_clip == [0.1, 0.2, 0.3, 0.4]
    assert config.action_signs == [1.0, -1.0, 1.0, -1.0]
    assert config.enabled is True
    assert config.qpos_tolerance is values["qpos_tolerance"]
    assert config.qvel_abs_max == pytest.approx(0.12)
    assert config.hold_steps == 3
    assert config.max_entry_error_m == "0.55"
    assert config.timeout_accept_entry_error_m == "0.25"
    assert config.start_envelope_enabled is True
    assert config.start_envelope_max_entry_error_m == pytest.approx(0.65)
    assert config.first_dig_entry_close_handoff is True
    assert config.first_dig_entry_close_handoff_qvel_abs_max == "0.07"
    assert config.entry_intent_handoff_enabled is True
    assert config.surface_guard_enabled is True
    assert config.surface_guard_max_penetration_m == pytest.approx(0.005)
    assert config.surface_guard_handoff_entry_error_m == "0.35"
    assert config.surface_guard_use_contact_fallback is False
    assert config.start_qpos_min is values["start_qpos_min"]
    assert config.start_qpos_max is values["start_qpos_max"]
    assert config.start_pose_min is values["start_pose_min"]
    assert config.start_pose_max is values["start_pose_max"]


def test_runtime_state_mapping_preserves_legacy_projection() -> None:
    target_qpos = np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float64)
    error = np.asarray([0.01, -0.02, 0.03, -0.04], dtype=np.float64)
    values = {
        "step_count": "1",
        "hold_count": np.int64(2),
        "timeout_count": "3",
        "completed_count": np.int64(4),
        "replan_count": "5",
        "target_qpos": target_qpos,
        "error": error,
        "entry_error_m": "0.25",
        "start_envelope_ready": 1,
        "entry_close_handoff_ready": 0,
        "entry_intent_handoff_ready": 1,
        "timeout_handoff_reason": 123,
        "surface_depth_m": "0.05",
        "surface_guard_triggered": 1,
        "surface_guard_count": np.int64(6),
        "ignored": object(),
    }

    state = runtime_state_from_mapping(values)

    assert {key for key, _ in DIG_START_ALIGNMENT_RUNTIME_STATE_FIELDS} == (
        set(values) - {"ignored"}
    )
    assert state.step_count == 1
    assert state.hold_count == 2
    assert state.timeout_count == 3
    assert state.completed_count == 4
    assert state.replan_count == 5
    assert state.target_qpos is target_qpos
    assert state.error is error
    assert state.entry_error_m == pytest.approx(0.25)
    assert state.start_envelope_ready is True
    assert state.entry_close_handoff_ready is False
    assert state.entry_intent_handoff_ready is True
    assert state.timeout_handoff_reason == "123"
    assert state.surface_depth_m == pytest.approx(0.05)
    assert state.surface_guard_triggered is True
    assert state.surface_guard_count == 6


def test_debug_state_mapping_preserves_legacy_projection() -> None:
    target_qpos = np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float64)
    error = np.asarray([0.01, -0.02, 0.03, -0.04], dtype=np.float64)
    values = {
        "surface_depth_m": "0.05",
        "surface_guard_triggered": 1,
        "surface_guard_count": np.int64(2),
        "step_count": "3",
        "hold_count": np.int64(4),
        "timeout_count": "5",
        "completed_count": np.int64(6),
        "replan_count": "7",
        "target_qpos": target_qpos,
        "error": error,
        "entry_error_m": "0.08",
        "start_envelope_ready": 1,
        "entry_close_handoff_ready": 0,
        "entry_intent_handoff_ready": 1,
        "ignored": object(),
    }

    state = debug_state_from_mapping(values)

    assert {key for key, _ in DIG_START_ALIGNMENT_DEBUG_STATE_FIELDS} == (
        set(values) - {"ignored"}
    )
    assert state.surface_depth_m == pytest.approx(0.05)
    assert state.surface_guard_triggered is True
    assert state.surface_guard_count == 2
    assert state.step_count == 3
    assert state.hold_count == 4
    assert state.timeout_count == 5
    assert state.completed_count == 6
    assert state.replan_count == 7
    assert state.target_qpos is target_qpos
    assert state.error is error
    assert state.entry_error_m == pytest.approx(0.08)
    assert state.start_envelope_ready is True
    assert state.entry_close_handoff_ready is False
    assert state.entry_intent_handoff_ready is True


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


def test_target_from_token_from_observation_view_matches_fact_projection() -> None:
    service = DigStartAlignmentService()
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX] = 0.2
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX] = 0.0
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX] = 0.4
    obs = {
        "env_state": env_state,
        "qpos": np.asarray([[0.1, 0.2, 0.3, 0.4]], dtype=np.float64),
        "qvel": np.asarray([[0.4, 0.3, 0.2, 0.1]], dtype=np.float64),
    }
    snapshot = build_planner_snapshot(
        obs,
        active_skill="pre_dig_align",
        cycle_index=5,
        prev_action=None,
        boundary_event=None,
        action_dim=4,
    )
    token = _token(entry_x=0.8, entry_z=-0.5)
    config = _config()
    expected = service.target_from_token(
        token=token,
        qpos=build_dig_start_alignment_facts_from_observation_view(
            view=snapshot.view,
            entry_error_m=float("nan"),
            cycle_index=5,
            hold_count=3,
        ).qpos,
        config=config,
    )

    actual = service.target_from_token_from_observation_view(
        view=snapshot.view,
        token=token,
        config=config,
        entry_error_m=float("nan"),
        cycle_index=5,
        hold_count=3,
    )

    np.testing.assert_allclose(actual, expected)
    assert actual.dtype == np.float32


def test_build_dig_start_alignment_facts_projects_inputs_to_legacy_shape() -> None:
    facts = build_dig_start_alignment_facts(
        action_dim=4,
        qpos=np.asarray([[1.0, 2.0, 3.0, 4.0]], dtype=np.float64),
        qvel=np.asarray([[0.1, 0.2, 0.3, 0.4]], dtype=np.float64),
        target_qpos=np.asarray([[4.0, 3.0, 2.0, 1.0]], dtype=np.float64),
        entry_error_m="0.25",
        bucket_pose=(0.1, 0.2, 0.3),
        surface_depth_m="0.05",
        contact_mask=1,
        cycle_index="3",
        hold_count="2",
    )

    np.testing.assert_allclose(
        facts.qpos,
        np.asarray([1.0, 2.0, 3.0, 4.0], dtype=np.float32),
    )
    np.testing.assert_allclose(
        facts.qvel,
        np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
    )
    np.testing.assert_allclose(
        facts.target_qpos,
        np.asarray([4.0, 3.0, 2.0, 1.0], dtype=np.float32),
    )
    assert facts.qpos.dtype == np.float32
    assert facts.qvel.dtype == np.float32
    assert facts.target_qpos is not None
    assert facts.target_qpos.dtype == np.float32
    assert facts.entry_error_m == pytest.approx(0.25)
    assert facts.bucket_pose == (0.1, 0.2, 0.3)
    assert facts.surface_depth_m == pytest.approx(0.05)
    assert facts.contact_mask is True
    assert facts.cycle_index == 3
    assert facts.hold_count == 2


def test_build_dig_start_alignment_facts_from_mapping_preserves_projection() -> None:
    values = {
        "action_dim": "4",
        "qpos": np.asarray([[1.0, 2.0, 3.0, 4.0]], dtype=np.float64),
        "qvel": np.asarray([[0.1, 0.2, 0.3, 0.4]], dtype=np.float64),
        "target_qpos": np.asarray([[4.0, 3.0, 2.0, 1.0]], dtype=np.float64),
        "entry_error_m": "0.25",
        "bucket_pose": (0.1, 0.2, 0.3),
        "surface_depth_m": "0.05",
        "contact_mask": 1,
        "cycle_index": "3",
        "hold_count": np.int64(2),
        "ignored": object(),
    }

    facts = build_dig_start_alignment_facts_from_mapping(values)

    assert set(DIG_START_ALIGNMENT_FACT_FIELDS) == (set(values) - {"ignored"})
    np.testing.assert_allclose(
        facts.qpos,
        np.asarray([1.0, 2.0, 3.0, 4.0], dtype=np.float32),
    )
    np.testing.assert_allclose(
        facts.qvel,
        np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
    )
    np.testing.assert_allclose(
        facts.target_qpos,
        np.asarray([4.0, 3.0, 2.0, 1.0], dtype=np.float32),
    )
    assert facts.entry_error_m == pytest.approx(0.25)
    assert facts.bucket_pose == (0.1, 0.2, 0.3)
    assert facts.surface_depth_m == pytest.approx(0.05)
    assert facts.contact_mask is True
    assert facts.cycle_index == 3
    assert facts.hold_count == 2


def test_build_dig_start_alignment_facts_from_observation_view_preserves_sources() -> None:
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX] = 0.2
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX] = 0.0
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX] = 0.4
    env_state[ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX] = 0.06
    env_state[ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX] = 1.0
    obs = {
        "env_state": env_state,
        "qpos": np.asarray([[1.0, 2.0, 3.0, 4.0]], dtype=np.float64),
        "qvel": np.asarray([[0.1, 0.2, 0.3, 0.4]], dtype=np.float64),
    }
    snapshot = build_planner_snapshot(
        obs,
        active_skill="pre_dig_align",
        cycle_index=5,
        prev_action=None,
        boundary_event=None,
        action_dim=4,
    )
    target_qpos = np.asarray([[4.0, 3.0, 2.0, 1.0]], dtype=np.float64)

    facts = build_dig_start_alignment_facts_from_observation_view(
        view=snapshot.view,
        target_qpos=target_qpos,
        entry_error_m=0.45,
        cycle_index=5,
        hold_count=3,
    )
    service_facts = DigStartAlignmentService.facts_from_observation_view(
        view=snapshot.view,
        target_qpos=target_qpos,
        entry_error_m=0.45,
        cycle_index=5,
        hold_count=3,
    )
    expected = build_dig_start_alignment_facts(
        action_dim=4,
        qpos=obs["qpos"],
        qvel=obs["qvel"],
        target_qpos=target_qpos,
        entry_error_m=0.45,
        bucket_pose=(0.2, 0.0, 0.4),
        surface_depth_m=0.06,
        contact_mask=True,
        cycle_index=5,
        hold_count=3,
    )

    np.testing.assert_allclose(facts.qpos, expected.qpos)
    np.testing.assert_allclose(facts.qvel, expected.qvel)
    np.testing.assert_allclose(facts.target_qpos, expected.target_qpos)
    assert facts.entry_error_m == pytest.approx(expected.entry_error_m)
    np.testing.assert_allclose(facts.bucket_pose, expected.bucket_pose)
    assert facts.surface_depth_m == pytest.approx(expected.surface_depth_m)
    assert facts.contact_mask is expected.contact_mask
    assert facts.cycle_index == expected.cycle_index
    assert facts.hold_count == expected.hold_count
    np.testing.assert_allclose(service_facts.qpos, facts.qpos)
    np.testing.assert_allclose(service_facts.qvel, facts.qvel)
    np.testing.assert_allclose(service_facts.target_qpos, facts.target_qpos)
    assert service_facts.entry_error_m == pytest.approx(facts.entry_error_m)
    np.testing.assert_allclose(service_facts.bucket_pose, facts.bucket_pose)
    assert service_facts.surface_depth_m == pytest.approx(facts.surface_depth_m)
    assert service_facts.contact_mask is facts.contact_mask
    assert service_facts.cycle_index == facts.cycle_index
    assert service_facts.hold_count == facts.hold_count


def test_build_dig_start_alignment_facts_preserves_optional_defaults() -> None:
    facts = build_dig_start_alignment_facts(
        action_dim=4,
        qpos=None,
        qvel=None,
    )

    np.testing.assert_array_equal(facts.qpos, np.zeros(4, dtype=np.float32))
    np.testing.assert_array_equal(facts.qvel, np.zeros(4, dtype=np.float32))
    assert facts.target_qpos is None
    assert np.isnan(facts.entry_error_m)
    assert facts.bucket_pose is None
    assert np.isnan(facts.surface_depth_m)
    assert facts.contact_mask is False
    assert facts.cycle_index == 0
    assert facts.hold_count == 0


def test_debug_snapshot_projects_alignment_config_and_runtime_state() -> None:
    service = DigStartAlignmentService()
    target = np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
    error = np.asarray([0.01, -0.02, 0.03, -0.04], dtype=np.float32)
    config = _config(
        enabled=True,
        entry_intent_controlled_dims=np.asarray(
            [True, False, True, False],
            dtype=bool,
        ),
        surface_guard_enabled=True,
        first_dig_entry_close_handoff=True,
        entry_intent_handoff_enabled=True,
        first_dig_entry_close_handoff_qvel_abs_max=0.07,
        controlled_dims=np.asarray([True, True, False, False], dtype=bool),
        bucket_target_qpos=-0.2,
    )
    state = DigStartAlignmentDebugState(
        surface_depth_m=0.05,
        surface_guard_triggered=True,
        surface_guard_count=2,
        step_count=3,
        hold_count=4,
        timeout_count=5,
        completed_count=6,
        replan_count=7,
        target_qpos=target,
        error=error,
        entry_error_m=0.08,
        start_envelope_ready=True,
        entry_close_handoff_ready=True,
        entry_intent_handoff_ready=True,
    )

    snapshot = service.debug_snapshot(
        config=config,
        state=state,
    )
    direct_snapshot = dig_start_alignment_runtime.debug_snapshot(
        action_dim=config.action_dim,
        enabled=config.enabled,
        entry_intent_controlled_dims=config.entry_intent_controlled_dims,
        surface_guard_enabled=config.surface_guard_enabled,
        first_dig_entry_close_handoff=config.first_dig_entry_close_handoff,
        entry_intent_handoff_enabled=config.entry_intent_handoff_enabled,
        first_dig_entry_close_handoff_qvel_abs_max=(
            config.first_dig_entry_close_handoff_qvel_abs_max
        ),
        controlled_dims=config.controlled_dims,
        bucket_target_qpos=config.bucket_target_qpos,
        state=state,
    )
    target[0] = 99.0
    error[0] = 99.0

    assert isinstance(snapshot, type(direct_snapshot))
    assert snapshot.surface_guard_count == direct_snapshot.surface_guard_count
    np.testing.assert_allclose(snapshot.target_qpos, direct_snapshot.target_qpos)
    np.testing.assert_allclose(snapshot.error, direct_snapshot.error)
    np.testing.assert_array_equal(
        snapshot.controlled_dims,
        direct_snapshot.controlled_dims,
    )
    assert snapshot.enabled
    np.testing.assert_array_equal(
        snapshot.entry_intent_controlled_dims,
        np.asarray([True, False, True, False], dtype=bool),
    )
    assert snapshot.surface_guard_enabled
    assert snapshot.surface_depth_m == 0.05
    assert snapshot.surface_guard_triggered
    assert snapshot.surface_guard_count == 2
    assert snapshot.step_count == 3
    assert snapshot.hold_count == 4
    assert snapshot.timeout_count == 5
    assert snapshot.completed_count == 6
    assert snapshot.replan_count == 7
    np.testing.assert_allclose(
        snapshot.target_qpos,
        np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
    )
    np.testing.assert_allclose(
        snapshot.error,
        np.asarray([0.01, -0.02, 0.03, -0.04], dtype=np.float32),
    )
    assert snapshot.entry_error_m == 0.08
    assert snapshot.start_envelope_ready
    assert snapshot.first_dig_entry_close_handoff
    assert snapshot.entry_close_handoff_ready
    assert snapshot.entry_intent_handoff_enabled
    assert snapshot.entry_intent_handoff_ready
    assert snapshot.first_dig_entry_close_handoff_qvel_abs_max == 0.07
    np.testing.assert_array_equal(
        snapshot.controlled_dims,
        np.asarray([True, True, False, False], dtype=bool),
    )
    assert snapshot.bucket_target_qpos == -0.2


def test_debug_snapshot_preserves_none_alignment_config_fields() -> None:
    snapshot = DigStartAlignmentService.debug_snapshot(
        config=_config(
            enabled=False,
            entry_intent_controlled_dims=None,
            first_dig_entry_close_handoff_qvel_abs_max=None,
            bucket_target_qpos=None,
        ),
        state=DigStartAlignmentDebugState(
            surface_depth_m=float("nan"),
            surface_guard_triggered=False,
            surface_guard_count=0,
            step_count=0,
            hold_count=0,
            timeout_count=0,
            completed_count=0,
            replan_count=0,
            target_qpos=np.zeros(4, dtype=np.float32),
            error=np.zeros(4, dtype=np.float32),
            entry_error_m=float("nan"),
            start_envelope_ready=False,
            entry_close_handoff_ready=False,
            entry_intent_handoff_ready=False,
        ),
    )

    assert not snapshot.enabled
    assert snapshot.entry_intent_controlled_dims is None
    assert snapshot.first_dig_entry_close_handoff_qvel_abs_max is None
    assert snapshot.bucket_target_qpos is None
    assert np.isnan(snapshot.surface_depth_m)
    assert np.isnan(snapshot.entry_error_m)


def test_initial_runtime_state_preserves_legacy_reset_defaults() -> None:
    service = DigStartAlignmentService()
    state = service.initial_runtime_state(_config(action_dim=4))
    other_state = service.initial_runtime_state(_config(action_dim=4))

    assert isinstance(state, DigStartAlignmentRuntimeState)
    assert state.step_count == 0
    assert state.hold_count == 0
    assert state.timeout_count == 0
    assert state.completed_count == 0
    assert state.replan_count == 0
    np.testing.assert_array_equal(state.target_qpos, np.zeros(4, dtype=np.float32))
    np.testing.assert_array_equal(state.error, np.zeros(4, dtype=np.float32))
    assert state.target_qpos.dtype == np.float32
    assert state.error.dtype == np.float32
    assert np.isnan(state.entry_error_m)
    assert state.start_envelope_ready is False
    assert state.entry_close_handoff_ready is False
    assert state.entry_intent_handoff_ready is False
    assert state.timeout_handoff_reason == ""
    assert np.isnan(state.surface_depth_m)
    assert state.surface_guard_triggered is False
    assert state.surface_guard_count == 0

    state.target_qpos[0] = 99.0
    assert other_state.target_qpos[0] == np.float32(0.0)


def test_restart_runtime_state_resets_attempt_fields_and_preserves_status() -> None:
    service = DigStartAlignmentService()
    target = np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float64)
    error = np.asarray([0.01, -0.02, 0.03, -0.04], dtype=np.float64)

    state = service.restart_runtime_state(
        DigStartAlignmentRuntimeState(
            step_count=9,
            hold_count=8,
            timeout_count=7,
            completed_count=6,
            replan_count=5,
            target_qpos=target,
            error=error,
            entry_error_m=0.25,
            start_envelope_ready=True,
            entry_close_handoff_ready=True,
            entry_intent_handoff_ready=True,
            timeout_handoff_reason="pre_dig_align_to_dig_timeout_intent_aligned",
            surface_depth_m=0.03,
            surface_guard_triggered=True,
            surface_guard_count=4,
        ),
        _config(action_dim=4),
    )
    target[0] = 99.0
    error[0] = 99.0

    assert state.step_count == 0
    assert state.hold_count == 0
    assert state.timeout_count == 7
    assert state.completed_count == 6
    assert state.replan_count == 6
    np.testing.assert_allclose(
        state.target_qpos,
        np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
    )
    np.testing.assert_allclose(
        state.error,
        np.asarray([0.01, -0.02, 0.03, -0.04], dtype=np.float32),
    )
    assert state.target_qpos.dtype == np.float32
    assert state.error.dtype == np.float32
    assert state.entry_error_m == pytest.approx(0.25)
    assert state.start_envelope_ready is True
    assert state.entry_close_handoff_ready is True
    assert state.entry_intent_handoff_ready is False
    assert state.timeout_handoff_reason == ""
    assert state.surface_depth_m == pytest.approx(0.03)
    assert state.surface_guard_triggered is False
    assert state.surface_guard_count == 4


def test_enter_runtime_state_resets_entry_fields_and_preserves_status() -> None:
    service = DigStartAlignmentService()
    target = np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float64)
    error = np.asarray([0.01, -0.02, 0.03, -0.04], dtype=np.float64)

    state = service.enter_runtime_state(
        DigStartAlignmentRuntimeState(
            step_count=9,
            hold_count=8,
            timeout_count=7,
            completed_count=6,
            replan_count=5,
            target_qpos=target,
            error=error,
            entry_error_m=0.25,
            start_envelope_ready=True,
            entry_close_handoff_ready=True,
            entry_intent_handoff_ready=True,
            timeout_handoff_reason="pre_dig_align_to_dig_timeout_intent_aligned",
            surface_depth_m=0.03,
            surface_guard_triggered=True,
            surface_guard_count=4,
        ),
        _config(action_dim=4),
    )
    target[0] = 99.0
    error[0] = 99.0

    assert state.step_count == 0
    assert state.hold_count == 0
    assert state.timeout_count == 7
    assert state.completed_count == 6
    assert state.replan_count == 5
    np.testing.assert_allclose(
        state.target_qpos,
        np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
    )
    np.testing.assert_allclose(
        state.error,
        np.asarray([0.01, -0.02, 0.03, -0.04], dtype=np.float32),
    )
    assert state.target_qpos.dtype == np.float32
    assert state.error.dtype == np.float32
    assert state.entry_error_m == pytest.approx(0.25)
    assert state.start_envelope_ready is True
    assert state.entry_close_handoff_ready is False
    assert state.entry_intent_handoff_ready is False
    assert state.timeout_handoff_reason == ""
    assert state.surface_depth_m == pytest.approx(0.03)
    assert state.surface_guard_triggered is False
    assert state.surface_guard_count == 4


def test_replan_handoff_runtime_state_counts_success_and_preserves_status() -> None:
    service = DigStartAlignmentService()
    target = np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float64)
    error = np.asarray([0.01, -0.02, 0.03, -0.04], dtype=np.float64)

    state = service.replan_handoff_runtime_state(
        DigStartAlignmentRuntimeState(
            step_count=9,
            hold_count=8,
            timeout_count=7,
            completed_count=6,
            replan_count=5,
            target_qpos=target,
            error=error,
            entry_error_m=0.25,
            start_envelope_ready=True,
            entry_close_handoff_ready=True,
            entry_intent_handoff_ready=True,
            timeout_handoff_reason="pre_dig_align_to_dig_timeout_intent_aligned",
            surface_depth_m=0.03,
            surface_guard_triggered=True,
            surface_guard_count=4,
        ),
        _config(action_dim=4),
    )
    target[0] = 99.0
    error[0] = 99.0

    assert state.step_count == 0
    assert state.hold_count == 0
    assert state.timeout_count == 7
    assert state.completed_count == 7
    assert state.replan_count == 6
    np.testing.assert_allclose(
        state.target_qpos,
        np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
    )
    np.testing.assert_allclose(
        state.error,
        np.asarray([0.01, -0.02, 0.03, -0.04], dtype=np.float32),
    )
    assert state.target_qpos.dtype == np.float32
    assert state.error.dtype == np.float32
    assert state.entry_error_m == pytest.approx(0.25)
    assert state.start_envelope_ready is True
    assert state.entry_close_handoff_ready is True
    assert state.entry_intent_handoff_ready is True
    assert (
        state.timeout_handoff_reason
        == "pre_dig_align_to_dig_timeout_intent_aligned"
    )
    assert state.surface_depth_m == pytest.approx(0.03)
    assert state.surface_guard_triggered is True
    assert state.surface_guard_count == 4


def test_pre_dig_align_outcome_runtime_projection_updates_counters_and_actions() -> None:
    service = DigStartAlignmentService()
    base = DigStartAlignmentRuntimeState(
        step_count=9,
        hold_count=8,
        timeout_count=7,
        completed_count=6,
        replan_count=5,
        target_qpos=np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
        error=np.asarray([0.01, -0.02, 0.03, -0.04], dtype=np.float32),
        entry_error_m=0.25,
        start_envelope_ready=True,
        entry_close_handoff_ready=True,
        entry_intent_handoff_ready=True,
        timeout_handoff_reason="pre_dig_align_to_dig_timeout_intent_aligned",
        surface_depth_m=0.03,
        surface_guard_triggered=True,
        surface_guard_count=4,
    )

    surface_handoff = service.outcome_runtime_projection(
        PreDigAlignOutcomeRuntimeFacts(
            outcome=PreDigAlignOutcome(
                action="surface_guard_handoff",
                switch_reason="pre_dig_align_to_dig_surface_guard",
            ),
            state=base,
        )
    )
    surface_replan = service.outcome_runtime_projection(
        PreDigAlignOutcomeRuntimeFacts(
            outcome=PreDigAlignOutcome(
                action="surface_guard_replan",
                switch_reason="pre_dig_align_to_dig_surface_guard_replan",
                reject_reason="pre_align_surface_penetration_entry_gap",
            ),
            state=base,
        )
    )
    ready = service.outcome_runtime_projection(
        PreDigAlignOutcomeRuntimeFacts(
            outcome=PreDigAlignOutcome(
                action="ready",
                switch_reason="pre_dig_align_to_dig_ready",
            ),
            state=base,
        )
    )
    timeout_handoff = service.outcome_runtime_projection(
        PreDigAlignOutcomeRuntimeFacts(
            outcome=PreDigAlignOutcome(
                action="timeout_handoff",
                switch_reason="pre_dig_align_to_dig_timeout_close_enough",
            ),
            state=base,
        )
    )
    timeout_replan = service.outcome_runtime_projection(
        PreDigAlignOutcomeRuntimeFacts(
            outcome=PreDigAlignOutcome(
                action="timeout_replan",
                switch_reason="pre_dig_align_retry_entry_gap",
                reject_reason="align_entry_gap_timeout",
            ),
            state=base,
        )
    )
    none = service.outcome_runtime_projection(
        PreDigAlignOutcomeRuntimeFacts(
            outcome=PreDigAlignOutcome(action="none"),
            state=base,
        )
    )

    assert surface_handoff.should_handoff_to_dig
    assert surface_handoff.switch_reason == "pre_dig_align_to_dig_surface_guard"
    assert surface_handoff.runtime_state.hold_count == 0
    assert surface_handoff.runtime_state.completed_count == 7
    assert surface_handoff.runtime_state.surface_guard_count == 5
    assert surface_replan.should_restart_dig_with_new_cut
    assert surface_replan.should_reject_active_corridor
    assert surface_replan.reject_reason == "pre_align_surface_penetration_entry_gap"
    assert surface_replan.runtime_state.hold_count == 0
    assert surface_replan.runtime_state.completed_count == 6
    assert surface_replan.runtime_state.surface_guard_count == 5
    assert ready.should_handoff_to_dig
    assert ready.runtime_state.completed_count == 7
    assert ready.runtime_state.hold_count == 8
    assert timeout_handoff.should_handoff_to_dig
    assert timeout_handoff.runtime_state.timeout_count == 8
    assert timeout_replan.should_try_replan_handoff
    assert timeout_replan.should_reject_active_corridor
    assert timeout_replan.reject_reason == "align_entry_gap_timeout"
    assert timeout_replan.runtime_state.timeout_count == 8
    assert none.transition_action == "none"
    assert none.runtime_state is base


def test_pre_dig_align_outcome_runtime_projection_from_state_matches_facts() -> None:
    service = DigStartAlignmentService()
    base = DigStartAlignmentRuntimeState(
        step_count=9,
        hold_count=8,
        timeout_count=7,
        completed_count=6,
        replan_count=5,
        target_qpos=np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
        error=np.asarray([0.01, -0.02, 0.03, -0.04], dtype=np.float32),
        entry_error_m=0.25,
        start_envelope_ready=True,
        entry_close_handoff_ready=True,
        entry_intent_handoff_ready=True,
        timeout_handoff_reason="pre_dig_align_to_dig_timeout_intent_aligned",
        surface_depth_m=0.03,
        surface_guard_triggered=True,
        surface_guard_count=4,
    )
    outcome = PreDigAlignOutcome(
        action="timeout_replan",
        switch_reason="pre_dig_align_retry_entry_gap",
        reject_reason="align_entry_gap_timeout",
    )

    actual = service.outcome_runtime_projection_from_state(
        outcome=outcome,
        state=base,
    )
    expected = service.outcome_runtime_projection(
        PreDigAlignOutcomeRuntimeFacts(
            outcome=outcome,
            state=base,
        )
    )

    assert actual.transition_action == expected.transition_action
    assert actual.switch_reason == expected.switch_reason
    assert actual.reject_reason == expected.reject_reason
    assert actual.runtime_state.timeout_count == expected.runtime_state.timeout_count
    assert actual.runtime_state.completed_count == expected.runtime_state.completed_count
    assert (
        actual.runtime_state.surface_guard_count
        == expected.runtime_state.surface_guard_count
    )


def test_readiness_runtime_projection_updates_gate_fields_without_side_effects() -> None:
    service = DigStartAlignmentService()
    base = DigStartAlignmentRuntimeState(
        step_count=9,
        hold_count=8,
        timeout_count=7,
        completed_count=6,
        replan_count=5,
        target_qpos=np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
        error=np.asarray([0.01, -0.02, 0.03, -0.04], dtype=np.float32),
        entry_error_m=0.25,
        start_envelope_ready=False,
        entry_close_handoff_ready=False,
        entry_intent_handoff_ready=True,
        timeout_handoff_reason="old_timeout",
        surface_depth_m=float("nan"),
        surface_guard_triggered=False,
        surface_guard_count=4,
    )

    surface = service.surface_guard_runtime_state(
        base,
        SurfaceGuardDecision(triggered=True, surface_depth_m=0.03),
    )
    ready = service.ready_runtime_state(
        surface,
        AlignmentReadyDecision(
            ready=True,
            hold_count=3,
            error=np.asarray([0.4, 0.3, 0.2, 0.1], dtype=np.float64),
            qpos_close=True,
            qvel_small=True,
            entry_close=True,
            start_envelope_ready=True,
            entry_close_handoff_ready=True,
            entry_intent_handoff_ready=False,
        ),
        entry_error_m="0.12",
    )
    timeout = service.timeout_handoff_runtime_state(
        ready,
        TimeoutHandoffDecision(
            ready=True,
            reason="pre_dig_align_to_dig_timeout_close_enough",
            start_envelope_ready=False,
            entry_intent_handoff_ready=False,
        ),
        sampled_entry_error_m=0.10,
    )
    sticky_timeout = service.timeout_handoff_runtime_state(
        base,
        TimeoutHandoffDecision(
            ready=True,
            reason="pre_dig_align_to_dig_timeout_close_enough",
            start_envelope_ready=True,
            entry_intent_handoff_ready=False,
        ),
        sampled_entry_error_m=0.11,
    )
    no_sample = service.timeout_handoff_runtime_state(
        timeout,
        TimeoutHandoffDecision(
            ready=True,
            reason="pre_dig_align_to_dig_timeout_no_entry_gate",
            start_envelope_ready=True,
            entry_intent_handoff_ready=True,
        ),
    )

    assert surface.surface_guard_triggered is True
    assert surface.surface_depth_m == pytest.approx(0.03)
    assert surface.hold_count == 8
    assert ready.hold_count == 3
    np.testing.assert_allclose(
        ready.error,
        np.asarray([0.4, 0.3, 0.2, 0.1], dtype=np.float32),
    )
    assert ready.error.dtype == np.float32
    assert ready.entry_error_m == pytest.approx(0.12)
    assert ready.start_envelope_ready is True
    assert ready.entry_close_handoff_ready is True
    assert ready.entry_intent_handoff_ready is False
    assert timeout.entry_error_m == pytest.approx(0.10)
    assert timeout.start_envelope_ready is False
    assert timeout.entry_intent_handoff_ready is False
    assert timeout.timeout_handoff_reason == (
        "pre_dig_align_to_dig_timeout_close_enough"
    )
    assert sticky_timeout.entry_error_m == pytest.approx(0.11)
    assert sticky_timeout.start_envelope_ready is True
    assert sticky_timeout.entry_intent_handoff_ready is True
    assert no_sample.entry_error_m == pytest.approx(0.10)
    assert no_sample.start_envelope_ready is False
    assert no_sample.entry_intent_handoff_ready is False
    assert no_sample.timeout_handoff_reason == (
        "pre_dig_align_to_dig_timeout_no_entry_gate"
    )
    assert no_sample.timeout_count == 7
    assert no_sample.completed_count == 6
    assert no_sample.replan_count == 5
    assert base.timeout_handoff_reason == "old_timeout"


def test_action_runtime_projection_updates_action_fields_only() -> None:
    service = DigStartAlignmentService()
    base = DigStartAlignmentRuntimeState(
        step_count=9,
        hold_count=8,
        timeout_count=7,
        completed_count=6,
        replan_count=5,
        target_qpos=np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
        error=np.asarray([0.01, -0.02, 0.03, -0.04], dtype=np.float32),
        entry_error_m=0.25,
        start_envelope_ready=True,
        entry_close_handoff_ready=True,
        entry_intent_handoff_ready=True,
        timeout_handoff_reason="pre_dig_align_to_dig_timeout_close_enough",
        surface_depth_m=0.03,
        surface_guard_triggered=True,
        surface_guard_count=4,
    )

    state = service.action_runtime_state(
        base,
        AlignmentActionDecision(
            action=np.ones(4, dtype=np.float32),
            error=np.asarray([0.4, 0.3, 0.2, 0.1], dtype=np.float64),
            entry_error_m="0.12",
        ),
    )

    np.testing.assert_allclose(
        state.error,
        np.asarray([0.4, 0.3, 0.2, 0.1], dtype=np.float32),
    )
    assert state.error.dtype == np.float32
    assert state.entry_error_m == pytest.approx(0.12)
    assert state.step_count == 9
    assert state.hold_count == 8
    assert state.timeout_count == 7
    assert state.completed_count == 6
    assert state.replan_count == 5
    np.testing.assert_allclose(
        state.target_qpos,
        np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
    )
    assert state.start_envelope_ready is True
    assert state.entry_close_handoff_ready is True
    assert state.entry_intent_handoff_ready is True
    assert (
        state.timeout_handoff_reason
        == "pre_dig_align_to_dig_timeout_close_enough"
    )
    assert state.surface_depth_m == pytest.approx(0.03)
    assert state.surface_guard_triggered is True
    assert state.surface_guard_count == 4
    np.testing.assert_allclose(
        base.error,
        np.asarray([0.01, -0.02, 0.03, -0.04], dtype=np.float32),
    )
    assert base.entry_error_m == pytest.approx(0.25)


def test_target_runtime_projection_updates_target_qpos_only() -> None:
    service = DigStartAlignmentService()
    base = DigStartAlignmentRuntimeState(
        step_count=9,
        hold_count=8,
        timeout_count=7,
        completed_count=6,
        replan_count=5,
        target_qpos=np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
        error=np.asarray([0.01, -0.02, 0.03, -0.04], dtype=np.float32),
        entry_error_m=0.25,
        start_envelope_ready=True,
        entry_close_handoff_ready=True,
        entry_intent_handoff_ready=True,
        timeout_handoff_reason="pre_dig_align_to_dig_timeout_close_enough",
        surface_depth_m=0.03,
        surface_guard_triggered=True,
        surface_guard_count=4,
    )
    target = np.asarray([[0.4, 0.3, 0.2, 0.1]], dtype=np.float64)

    state = service.target_runtime_state(
        base,
        target_qpos=target,
        config=_config(action_dim=4),
    )
    target[0, 0] = 99.0

    np.testing.assert_allclose(
        state.target_qpos,
        np.asarray([0.4, 0.3, 0.2, 0.1], dtype=np.float32),
    )
    assert state.target_qpos.dtype == np.float32
    assert state.step_count == 9
    assert state.hold_count == 8
    assert state.timeout_count == 7
    assert state.completed_count == 6
    assert state.replan_count == 5
    np.testing.assert_allclose(
        state.error,
        np.asarray([0.01, -0.02, 0.03, -0.04], dtype=np.float32),
    )
    assert state.entry_error_m == pytest.approx(0.25)
    assert state.start_envelope_ready is True
    assert state.entry_close_handoff_ready is True
    assert state.entry_intent_handoff_ready is True
    assert (
        state.timeout_handoff_reason
        == "pre_dig_align_to_dig_timeout_close_enough"
    )
    assert state.surface_depth_m == pytest.approx(0.03)
    assert state.surface_guard_triggered is True
    assert state.surface_guard_count == 4
    np.testing.assert_allclose(
        base.target_qpos,
        np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
    )


def test_entry_error_runtime_projection_updates_entry_error_only() -> None:
    service = DigStartAlignmentService()
    base = DigStartAlignmentRuntimeState(
        step_count=9,
        hold_count=8,
        timeout_count=7,
        completed_count=6,
        replan_count=5,
        target_qpos=np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
        error=np.asarray([0.01, -0.02, 0.03, -0.04], dtype=np.float32),
        entry_error_m=0.25,
        start_envelope_ready=True,
        entry_close_handoff_ready=True,
        entry_intent_handoff_ready=True,
        timeout_handoff_reason="pre_dig_align_to_dig_timeout_close_enough",
        surface_depth_m=0.03,
        surface_guard_triggered=True,
        surface_guard_count=4,
    )

    state = service.entry_error_runtime_state(base, entry_error_m="0.12")

    assert state.entry_error_m == pytest.approx(0.12)
    assert state.step_count == 9
    assert state.hold_count == 8
    assert state.timeout_count == 7
    assert state.completed_count == 6
    assert state.replan_count == 5
    np.testing.assert_allclose(
        state.target_qpos,
        np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
    )
    np.testing.assert_allclose(
        state.error,
        np.asarray([0.01, -0.02, 0.03, -0.04], dtype=np.float32),
    )
    assert state.start_envelope_ready is True
    assert state.entry_close_handoff_ready is True
    assert state.entry_intent_handoff_ready is True
    assert (
        state.timeout_handoff_reason
        == "pre_dig_align_to_dig_timeout_close_enough"
    )
    assert state.surface_depth_m == pytest.approx(0.03)
    assert state.surface_guard_triggered is True
    assert state.surface_guard_count == 4


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


def test_action_decision_projects_action_error_and_entry_error() -> None:
    service = DigStartAlignmentService()
    decision = service.action_decision(
        build_dig_start_alignment_facts(
            action_dim=4,
            qpos=np.zeros(4, dtype=np.float64),
            qvel=np.ones(4, dtype=np.float64),
            target_qpos=np.ones(4, dtype=np.float64),
            entry_error_m="0.25",
        ),
        _config(
            controlled_dims=np.asarray([True, False, True, False]),
        ),
    )

    np.testing.assert_allclose(
        decision.action,
        np.asarray([1.0, 0.0, 0.5, 0.0], dtype=np.float32),
        atol=1.0e-6,
    )
    np.testing.assert_allclose(
        decision.error,
        np.ones(4, dtype=np.float32),
        atol=1.0e-6,
    )
    assert decision.action.dtype == np.float32
    assert decision.error.dtype == np.float32
    assert decision.entry_error_m == pytest.approx(0.25)


def test_action_decision_from_observation_view_matches_fact_projection() -> None:
    service = DigStartAlignmentService()
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX] = 0.2
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX] = 0.0
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX] = 0.4
    obs = {
        "env_state": env_state,
        "qpos": np.asarray([[0.0, 0.0, 0.0, 0.0]], dtype=np.float64),
        "qvel": np.asarray([[1.0, 1.0, 1.0, 1.0]], dtype=np.float64),
    }
    snapshot = build_planner_snapshot(
        obs,
        active_skill="pre_dig_align",
        cycle_index=5,
        prev_action=None,
        boundary_event=None,
        action_dim=4,
    )
    target_qpos = np.ones(4, dtype=np.float64)
    config = _config(
        controlled_dims=np.asarray([True, False, True, False]),
    )
    expected = service.action_decision(
        build_dig_start_alignment_facts_from_observation_view(
            view=snapshot.view,
            target_qpos=target_qpos,
            entry_error_m=0.25,
            cycle_index=5,
            hold_count=3,
        ),
        config,
    )

    actual = service.action_decision_from_observation_view(
        view=snapshot.view,
        target_qpos=target_qpos,
        entry_error_m=0.25,
        config=config,
        cycle_index=5,
        hold_count=3,
    )

    np.testing.assert_allclose(actual.action, expected.action)
    np.testing.assert_allclose(actual.error, expected.error)
    assert actual.entry_error_m == pytest.approx(expected.entry_error_m)
    assert actual.action.dtype == np.float32
    assert actual.error.dtype == np.float32


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


def test_entry_error_uses_bucket_tip_xz_and_corridor_entry_xz() -> None:
    service = DigStartAlignmentService()
    facts = DigStartAlignmentEntryErrorFacts(
        bucket_tip_dig_area_pose=(0.10, 99.0, 0.40),
        active_corridor_entry_xz=(0.40, 0.80),
    )

    error = service.entry_error(facts)

    assert np.isclose(error, 0.5)
    assert error == dig_start_alignment_entry_error(facts)


def test_entry_error_from_observation_view_matches_fact_projection() -> None:
    service = DigStartAlignmentService()
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX] = 0.10
    env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX] = 99.0
    env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX] = 0.40
    obs = {
        "env_state": env_state,
        "qpos": np.asarray([[0.1, 0.2, 0.3, 0.4]], dtype=np.float64),
        "qvel": np.asarray([[0.4, 0.3, 0.2, 0.1]], dtype=np.float64),
    }
    snapshot = build_planner_snapshot(
        obs,
        active_skill="pre_dig_align",
        cycle_index=5,
        prev_action=None,
        boundary_event=None,
        action_dim=4,
    )
    active_entry_xz = (0.40, 0.80)
    expected = service.entry_error(
        build_dig_start_alignment_entry_error_facts_from_observation_view(
            view=snapshot.view,
            active_corridor_entry_xz=active_entry_xz,
        )
    )

    actual = service.entry_error_from_observation_view(
        view=snapshot.view,
        active_corridor_entry_xz=active_entry_xz,
    )

    assert actual == pytest.approx(expected)
    assert np.isclose(actual, 0.5)


def test_entry_error_returns_nan_without_tip_pose_or_corridor_entry() -> None:
    service = DigStartAlignmentService()

    assert np.isnan(
        service.entry_error(
            DigStartAlignmentEntryErrorFacts(
                bucket_tip_dig_area_pose=None,
                active_corridor_entry_xz=(0.40, 0.80),
            )
        )
    )
    assert np.isnan(
        service.entry_error(
            DigStartAlignmentEntryErrorFacts(
                bucket_tip_dig_area_pose=(0.10, 0.0, 0.40),
                active_corridor_entry_xz=None,
            )
        )
    )


def test_entry_error_preserves_legacy_non_finite_coordinate_result() -> None:
    service = DigStartAlignmentService()

    assert np.isinf(
        service.entry_error(
            DigStartAlignmentEntryErrorFacts(
                bucket_tip_dig_area_pose=(np.inf, 0.0, 0.40),
                active_corridor_entry_xz=(0.40, 0.80),
            )
        )
    )
    assert np.isnan(
        service.entry_error(
            DigStartAlignmentEntryErrorFacts(
                bucket_tip_dig_area_pose=(0.10, 0.0, 0.40),
                active_corridor_entry_xz=(np.nan, 0.80),
            )
        )
    )


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


def test_entry_close_handoff_facts_project_legacy_defaults() -> None:
    facts = DigStartAlignmentService.entry_close_handoff_facts(
        action_dim=4,
        qvel=np.asarray([[0.0, 0.03, -0.10, -0.02]], dtype=np.float64),
        entry_error_m="0.20",
        cycle_index=np.int64(3),
    )

    np.testing.assert_array_equal(facts.qpos, np.zeros(4, dtype=np.float32))
    np.testing.assert_allclose(
        facts.qvel,
        np.asarray([0.0, 0.03, -0.10, -0.02], dtype=np.float32),
    )
    assert facts.qpos.dtype == np.float32
    assert facts.qvel.dtype == np.float32
    assert facts.target_qpos is None
    assert facts.entry_error_m == pytest.approx(0.20)
    assert facts.bucket_pose is None
    assert facts.cycle_index == 3
    assert facts.hold_count == 0


def test_entry_close_handoff_ready_from_runtime_values_matches_fact_gate() -> None:
    service = DigStartAlignmentService()
    config = _config(
        start_envelope_enabled=True,
        first_dig_entry_close_handoff=True,
        first_dig_entry_close_handoff_qvel_abs_max=0.15,
        max_entry_error_m=0.35,
    )
    qvel = np.asarray([[0.0, 0.03, -0.10, -0.02]], dtype=np.float64)

    actual = service.entry_close_handoff_ready_from_runtime_values(
        action_dim=4,
        qvel=qvel,
        entry_error_m="0.20",
        cycle_index=np.int64(0),
        config=config,
        start_envelope_ready=True,
    )
    expected = service.entry_close_handoff_ready(
        facts=service.entry_close_handoff_facts(
            action_dim=4,
            qvel=qvel,
            entry_error_m="0.20",
            cycle_index=np.int64(0),
        ),
        config=config,
        start_envelope_ready=True,
    )

    assert actual is expected


def test_ready_from_observation_view_matches_fact_gate() -> None:
    service = DigStartAlignmentService()
    config = _config(
        enabled=True,
        hold_steps=1,
        qpos_tolerance=np.asarray([0.1, 0.1, 0.1, 0.1], dtype=np.float32),
        max_entry_error_m=0.35,
    )
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX] = 0.2
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX] = 0.0
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX] = 0.4
    obs = {
        "env_state": env_state,
        "qpos": np.asarray([[0.1, 0.2, 0.3, 0.4]], dtype=np.float64),
        "qvel": np.asarray([[0.01, 0.02, 0.03, 0.04]], dtype=np.float64),
    }
    snapshot = build_planner_snapshot(
        obs,
        active_skill="pre_dig_align",
        cycle_index=5,
        prev_action=None,
        boundary_event=None,
        action_dim=4,
    )
    target_qpos = np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
    expected = service.ready(
        build_dig_start_alignment_facts_from_observation_view(
            view=snapshot.view,
            target_qpos=target_qpos,
            entry_error_m=0.20,
            cycle_index=5,
            hold_count=2,
        ),
        config,
    )

    actual = service.ready_from_observation_view(
        view=snapshot.view,
        target_qpos=target_qpos,
        entry_error_m=0.20,
        config=config,
        cycle_index=5,
        hold_count=2,
    )

    assert actual.ready is expected.ready
    assert actual.hold_count == expected.hold_count
    np.testing.assert_allclose(actual.error, expected.error)
    assert actual.qpos_close is expected.qpos_close
    assert actual.qvel_small is expected.qvel_small
    assert actual.entry_close is expected.entry_close
    assert actual.start_envelope_ready is expected.start_envelope_ready
    assert actual.entry_close_handoff_ready is expected.entry_close_handoff_ready
    assert actual.entry_intent_handoff_ready is expected.entry_intent_handoff_ready


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


def test_pre_dig_align_outcome_classifies_surface_guard_paths() -> None:
    handoff = DigStartAlignmentService.classify_outcome(
        surface_guard_triggered=True,
        surface_guard_can_handoff=True,
    )
    assert handoff.action == "surface_guard_handoff"
    assert handoff.switch_reason == "pre_dig_align_to_dig_surface_guard"
    assert handoff.reject_reason == ""

    replan = DigStartAlignmentService.classify_outcome(
        surface_guard_triggered=True,
        surface_guard_can_handoff=False,
    )
    assert replan.action == "surface_guard_replan"
    assert replan.switch_reason == "pre_dig_align_to_dig_surface_guard_replan"
    assert replan.reject_reason == "pre_align_surface_penetration_entry_gap"


def test_pre_dig_align_outcome_classifies_ready_and_timeout_paths() -> None:
    ready = DigStartAlignmentService.classify_outcome(
        surface_guard_triggered=False,
        ready=True,
    )
    assert ready.action == "ready"
    assert ready.switch_reason == "pre_dig_align_to_dig_ready"

    timeout_handoff = DigStartAlignmentService.classify_outcome(
        surface_guard_triggered=False,
        timed_out=True,
        timeout_can_handoff=True,
        timeout_reason="pre_dig_align_to_dig_timeout_intent_aligned",
    )
    assert timeout_handoff.action == "timeout_handoff"
    assert (
        timeout_handoff.switch_reason
        == "pre_dig_align_to_dig_timeout_intent_aligned"
    )

    timeout_default = DigStartAlignmentService.classify_outcome(
        surface_guard_triggered=False,
        timed_out=True,
        timeout_can_handoff=True,
    )
    assert timeout_default.action == "timeout_handoff"
    assert (
        timeout_default.switch_reason
        == "pre_dig_align_to_dig_timeout_close_enough"
    )

    timeout_replan = DigStartAlignmentService.classify_outcome(
        surface_guard_triggered=False,
        timed_out=True,
        timeout_can_handoff=False,
    )
    assert timeout_replan.action == "timeout_replan"
    assert timeout_replan.switch_reason == "pre_dig_align_retry_entry_gap"
    assert timeout_replan.reject_reason == "align_entry_gap_timeout"

    assert (
        DigStartAlignmentService.classify_outcome(
            surface_guard_triggered=False,
        ).action
        == "none"
    )


def test_pre_dig_align_outcome_request_preserves_gate_order() -> None:
    surface = DigStartAlignmentService.outcome_request(
        surface_guard_triggered=True,
        step_count=20,
        max_steps=10,
    )

    assert surface.should_check_surface_guard_handoff
    assert not surface.should_check_ready
    assert not surface.should_check_timeout(ready=False)
    surface_replan = surface.outcome_with_gate_results(
        surface_guard_can_handoff=False,
    )
    assert surface_replan.action == "surface_guard_replan"
    assert (
        surface_replan.reject_reason == "pre_align_surface_penetration_entry_gap"
    )

    waiting = DigStartAlignmentService.outcome_request(
        surface_guard_triggered=False,
        step_count=9,
        max_steps=10,
    )
    assert not waiting.should_check_surface_guard_handoff
    assert waiting.should_check_ready
    assert not waiting.should_check_timeout(ready=False)
    assert waiting.outcome_with_gate_results(ready=False).action == "none"

    timed_out = DigStartAlignmentService.outcome_request(
        surface_guard_triggered=False,
        step_count=10,
        max_steps=10,
    )
    assert timed_out.should_check_ready
    assert not timed_out.should_check_timeout(ready=True)
    assert timed_out.should_check_timeout(ready=False)
    timeout = timed_out.outcome_with_gate_results(
        ready=False,
        timeout_can_handoff=True,
        timeout_reason="pre_dig_align_to_dig_timeout_intent_aligned",
    )
    assert timeout.action == "timeout_handoff"
    assert (
        timeout.switch_reason
        == "pre_dig_align_to_dig_timeout_intent_aligned"
    )


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


def test_start_envelope_facts_project_legacy_defaults() -> None:
    facts = DigStartAlignmentService.start_envelope_facts(
        action_dim=4,
        qpos=np.asarray([[0.5, 0.6, 0.1, 0.0]], dtype=np.float64),
        entry_error_m="0.40",
        bucket_pose=(0.5, 0.0, -0.5),
    )

    np.testing.assert_allclose(
        facts.qpos,
        np.asarray([0.5, 0.6, 0.1, 0.0], dtype=np.float32),
    )
    np.testing.assert_array_equal(facts.qvel, np.zeros(4, dtype=np.float32))
    assert facts.qpos.dtype == np.float32
    assert facts.qvel.dtype == np.float32
    assert facts.entry_error_m == pytest.approx(0.40)
    assert facts.bucket_pose == (0.5, 0.0, -0.5)
    assert facts.cycle_index == 0
    assert facts.hold_count == 0


def test_start_envelope_facts_from_observation_view_preserves_sources() -> None:
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX] = 0.5
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX] = 0.0
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX] = -0.5
    obs = {
        "env_state": env_state,
        "qpos": np.asarray([99.0, 99.0, 99.0, 99.0], dtype=np.float32),
    }
    snapshot = build_planner_snapshot(
        obs,
        active_skill="pre_dig_align",
        cycle_index=5,
        prev_action=None,
        boundary_event=None,
        action_dim=4,
    )
    qpos = np.asarray([[0.5, 0.6, 0.1, 0.0]], dtype=np.float64)

    facts = DigStartAlignmentService.start_envelope_facts_from_observation_view(
        view=snapshot.view,
        qpos=qpos,
        entry_error_m="0.40",
    )

    np.testing.assert_allclose(
        facts.qpos,
        np.asarray([0.5, 0.6, 0.1, 0.0], dtype=np.float32),
    )
    np.testing.assert_array_equal(facts.qvel, np.zeros(4, dtype=np.float32))
    assert facts.qpos.dtype == np.float32
    assert facts.qvel.dtype == np.float32
    assert facts.entry_error_m == pytest.approx(0.40)
    np.testing.assert_allclose(facts.bucket_pose, (0.5, 0.0, -0.5))
    assert facts.cycle_index == 0
    assert facts.hold_count == 0


def test_start_envelope_ready_from_observation_view_matches_fact_gate() -> None:
    service = DigStartAlignmentService()
    config = _config(
        start_envelope_enabled=True,
        start_envelope_max_entry_error_m=0.65,
        start_qpos_min=np.asarray([0.0, 0.0, 0.0, 0.0], dtype=np.float64),
        start_qpos_max=np.asarray([1.0, 1.0, 1.0, 1.0], dtype=np.float64),
        start_pose_min=np.asarray([-0.6, -0.3, -1.5], dtype=np.float64),
        start_pose_max=np.asarray([1.65, 0.25, 1.2], dtype=np.float64),
    )
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX] = 0.5
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX] = 0.0
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX] = -0.5
    obs = {
        "env_state": env_state,
        "qpos": np.asarray([99.0, 99.0, 99.0, 99.0], dtype=np.float32),
        "qvel": np.asarray([88.0, 88.0, 88.0, 88.0], dtype=np.float32),
    }
    snapshot = build_planner_snapshot(
        obs,
        active_skill="pre_dig_align",
        cycle_index=5,
        prev_action=None,
        boundary_event=None,
        action_dim=4,
    )
    qpos = np.asarray([[0.5, 0.6, 0.1, 0.0]], dtype=np.float64)

    actual = service.start_envelope_ready_from_observation_view(
        view=snapshot.view,
        qpos=qpos,
        entry_error_m="0.40",
        config=config,
    )
    expected = service.start_envelope_ready(
        service.start_envelope_facts_from_observation_view(
            view=snapshot.view,
            qpos=qpos,
            entry_error_m="0.40",
        ),
        config,
    )

    assert actual is expected


def test_timeout_handoff_request_selects_entry_error_sampling_path() -> None:
    service = DigStartAlignmentService()

    no_gate = service.timeout_handoff_request(
        current_entry_error_m="0.77",
        config=_config(timeout_accept_entry_error_m=None, max_entry_error_m=None),
    )
    assert isinstance(no_gate, PreDigAlignTimeoutHandoffRequest)
    assert not no_gate.should_sample_entry_error
    facts = no_gate.facts_without_entry_sampling(action_dim=4)
    np.testing.assert_array_equal(facts.qpos, np.zeros(4, dtype=np.float32))
    np.testing.assert_array_equal(facts.qvel, np.zeros(4, dtype=np.float32))
    assert facts.entry_error_m == pytest.approx(0.77)

    timeout_threshold = service.timeout_handoff_request(
        current_entry_error_m=0.77,
        config=_config(timeout_accept_entry_error_m=0.10, max_entry_error_m=None),
    )
    assert timeout_threshold.should_sample_entry_error

    sampled_facts = timeout_threshold.facts_with_entry_sampling(
        action_dim=4,
        qpos=np.asarray([[0.1, 0.2, 0.3, 0.4]], dtype=np.float64),
        entry_error_m="0.12",
        bucket_pose=(0.5, 0.0, -0.5),
    )
    np.testing.assert_allclose(
        sampled_facts.qpos,
        np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
    )
    np.testing.assert_array_equal(
        sampled_facts.qvel,
        np.zeros(4, dtype=np.float32),
    )
    assert sampled_facts.entry_error_m == pytest.approx(0.12)
    assert sampled_facts.bucket_pose == (0.5, 0.0, -0.5)

    max_entry_threshold = service.timeout_handoff_request(
        current_entry_error_m=0.77,
        config=_config(timeout_accept_entry_error_m=None, max_entry_error_m=0.20),
    )
    assert max_entry_threshold.should_sample_entry_error


def test_timeout_handoff_request_entry_sampling_from_observation_view_preserves_sources() -> None:
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX] = 0.5
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX] = 0.0
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX] = -0.5
    obs = {
        "env_state": env_state,
        "qpos": np.asarray([[0.1, 0.2, 0.3, 0.4]], dtype=np.float64),
        "qvel": np.asarray([[0.4, 0.3, 0.2, 0.1]], dtype=np.float64),
    }
    snapshot = build_planner_snapshot(
        obs,
        active_skill="pre_dig_align",
        cycle_index=5,
        prev_action=None,
        boundary_event=None,
        action_dim=4,
    )
    request = PreDigAlignTimeoutHandoffRequest(
        should_sample_entry_error=True,
        current_entry_error_m=0.77,
    )

    facts = request.facts_with_entry_sampling_from_observation_view(
        view=snapshot.view,
        entry_error_m="0.12",
    )

    np.testing.assert_allclose(
        facts.qpos,
        np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
    )
    np.testing.assert_allclose(
        facts.qvel,
        np.asarray([0.4, 0.3, 0.2, 0.1], dtype=np.float32),
    )
    assert facts.qpos.dtype == np.float32
    assert facts.qvel.dtype == np.float32
    assert facts.entry_error_m == pytest.approx(0.12)
    np.testing.assert_allclose(facts.bucket_pose, (0.5, 0.0, -0.5))
    assert facts.cycle_index == 0
    assert facts.hold_count == 0


def test_timeout_handoff_decision_matches_request_fact_projection() -> None:
    service = DigStartAlignmentService()
    no_gate_config = _config(timeout_accept_entry_error_m=None, max_entry_error_m=None)
    no_gate = service.timeout_handoff_request(
        current_entry_error_m="0.77",
        config=no_gate_config,
    )
    assert service.timeout_handoff_decision(
        request=no_gate,
        config=no_gate_config,
        action_dim=4,
    ) == service.timeout_can_handoff(
        no_gate.facts_without_entry_sampling(action_dim=4),
        no_gate_config,
    )

    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX] = 0.5
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX] = 0.0
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX] = -0.5
    obs = {
        "env_state": env_state,
        "qpos": np.asarray([[0.1, 0.2, 0.3, 0.4]], dtype=np.float64),
        "qvel": np.asarray([[0.4, 0.3, 0.2, 0.1]], dtype=np.float64),
    }
    snapshot = build_planner_snapshot(
        obs,
        active_skill="pre_dig_align",
        cycle_index=5,
        prev_action=None,
        boundary_event=None,
        action_dim=4,
    )
    threshold_config = _config(timeout_accept_entry_error_m=0.20)
    sampled = service.timeout_handoff_request(
        current_entry_error_m=0.77,
        config=threshold_config,
    )
    assert service.timeout_handoff_decision(
        request=sampled,
        config=threshold_config,
        action_dim=4,
        view=snapshot.view,
        sampled_entry_error_m=0.12,
    ) == service.timeout_can_handoff(
        sampled.facts_with_entry_sampling_from_observation_view(
            view=snapshot.view,
            entry_error_m=0.12,
        ),
        threshold_config,
    )


def test_timeout_handoff_decision_requires_sample_inputs() -> None:
    service = DigStartAlignmentService()
    config = _config(timeout_accept_entry_error_m=0.20)
    request = service.timeout_handoff_request(
        current_entry_error_m=0.77,
        config=config,
    )

    with pytest.raises(ValueError, match="timeout handoff sampling requires"):
        service.timeout_handoff_decision(
            request=request,
            config=config,
            action_dim=4,
        )


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


def test_surface_guard_triggered_from_observation_view_matches_fact_gate() -> None:
    service = DigStartAlignmentService()
    config = _config(
        enabled=True,
        surface_guard_enabled=True,
        surface_guard_max_penetration_m=0.005,
    )
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX] = 0.2
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX] = 0.0
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX] = 0.4
    env_state[ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX] = 0.03
    obs = {
        "env_state": env_state,
        "qpos": np.asarray([[0.1, 0.2, 0.3, 0.4]], dtype=np.float64),
        "qvel": np.asarray([[0.4, 0.3, 0.2, 0.1]], dtype=np.float64),
    }
    snapshot = build_planner_snapshot(
        obs,
        active_skill="pre_dig_align",
        cycle_index=5,
        prev_action=None,
        boundary_event=None,
        action_dim=4,
    )
    expected = service.surface_guard_triggered(
        build_dig_start_alignment_facts_from_observation_view(
            view=snapshot.view,
            entry_error_m=0.25,
            cycle_index=5,
            hold_count=3,
        ),
        config,
    )

    assert service.surface_guard_triggered_from_observation_view(
        view=snapshot.view,
        config=config,
        entry_error_m=0.25,
        cycle_index=5,
        hold_count=3,
    ) == expected


def test_surface_guard_can_handoff_from_observation_view_matches_fact_gate() -> None:
    service = DigStartAlignmentService()
    config = _config(
        enabled=True,
        surface_guard_enabled=True,
        surface_guard_handoff_entry_error_m=0.35,
    )
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX] = 0.2
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX] = 0.0
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX] = 0.4
    obs = {
        "env_state": env_state,
        "qpos": np.asarray([[0.1, 0.2, 0.3, 0.4]], dtype=np.float64),
        "qvel": np.asarray([[0.4, 0.3, 0.2, 0.1]], dtype=np.float64),
    }
    snapshot = build_planner_snapshot(
        obs,
        active_skill="pre_dig_align",
        cycle_index=6,
        prev_action=None,
        boundary_event=None,
        action_dim=4,
    )
    expected = service.surface_guard_can_handoff(
        build_dig_start_alignment_facts_from_observation_view(
            view=snapshot.view,
            entry_error_m=0.20,
            cycle_index=6,
            hold_count=4,
        ),
        config,
    )

    assert (
        service.surface_guard_can_handoff_from_observation_view(
            view=snapshot.view,
            entry_error_m=0.20,
            config=config,
            cycle_index=6,
            hold_count=4,
        )
        is expected
    )
