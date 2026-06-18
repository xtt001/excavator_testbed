from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from testbed.contracts.primitive_profile import (
    CYCLE_BOUNDARY_PROFILE_LEGACY,
    CYCLE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS,
    is_v2_4_5_cycle_boundary_profile,
)
from testbed.contracts.primitive_tokens import (
    DIG_CUT_TOKEN_DIM,
    DIG_DEPTH_PROFILE_TOKEN_DIM,
    RETURN_ENVELOPE_QPOS_VALID_IDX,
    RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_TARGET_TOKEN_DIM,
)
from testbed.data.schema import (
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
)
from testbed.planner.bootstrap import (
    BOOTSTRAP_RUNTIME_CONFIG_FIELDS,
    BootstrapEndDecision,
    BootstrapEndTransitionFacts,
    BootstrapTargetDecision,
    BootstrapTransitionConfig,
    BootstrapTransitionDecision,
    build_bootstrap_config_from_mapping,
)
from testbed.planner.cell_entry import (
    CELL_ENTRY_RUNTIME_STATE_FIELDS,
    CELL_ENTRY_TOKEN_DIM,
    CellEntryPlanner,
    CellEntryRuntimeCompletionResult,
    CellEntryRuntimeState,
    CellEntryRuntimeTokenResult,
    CellGridSpec,
    build_cell_entry_runtime_state_from_mapping,
)
from testbed.planner.dig_coverage.models import CoverageCorridorState
from testbed.planner.dig_cut_plan import DigCutPlanCycleApplyState, DigCutPlanState
from testbed.planner.dig_lifecycle import (
    DIG_LIFECYCLE_ENTRY_RUNTIME_FACT_FIELDS,
    DIG_LIFECYCLE_RUNTIME_CONFIG_KEYS,
    DigGateDecision,
    DigLifecycleEntryRuntimeState,
    DigProgressState,
    DigTransitionRuntimeOutcome,
    DigTransitionRuntimeProjection,
    FailedDigRecoveryDecision,
    FailedDigStopFacts,
    FailedDigStopState,
    build_dig_lifecycle_entry_runtime_facts_from_mapping,
    build_dig_lifecycle_runtime_config_from_mapping,
)
from testbed.planner.dig_start_alignment import (
    DIG_START_ALIGNMENT_RUNTIME_STATE_FIELDS,
    runtime_state_from_mapping,
)
from testbed.planner.dig_start_alignment_action import AlignmentActionDecision
from testbed.planner.dig_start_alignment_context import (
    DIG_START_ALIGNMENT_RUNTIME_CONFIG_FIELDS,
    DigStartAlignmentConfig,
    build_dig_start_alignment_runtime_config_from_mapping,
)
from testbed.planner.dig_start_alignment_outcome import (
    PreDigAlignOutcome,
    PreDigAlignOutcomeRuntimeFacts,
)
from testbed.planner.dig_start_alignment_readiness import (
    AlignmentReadyDecision,
    SurfaceGuardDecision,
    TimeoutHandoffDecision,
)
from testbed.planner.dump_lifecycle import (
    DUMP_LIFECYCLE_RUNTIME_CONFIG_KEYS,
    CarryTransitionRuntimeState,
    DumpLifecycleOutcome,
    DumpTransitionRuntimeState,
    build_dump_lifecycle_runtime_config_from_mapping,
)
from testbed.planner.policy_observation import (
    DIG_CONDITIONING_TOKEN_GATE_FACT_FIELDS,
    POLICY_OBSERVATION_REQUEST_FACT_FIELDS,
    DigConditioningObservationTokenGateDecision,
    PolicyObservationAssembly,
    PolicyObservationRequestConfig,
    PolicyObservationTokenRequest,
    PolicyObservationTokens,
)
from testbed.planner.return_handoff import (
    RETURN_TO_DIG_HANDOFF_CONFIG_FIELDS,
    ReturnToDigEntryErrorFacts,
    ReturnToDigHandoffStatusState,
    build_return_next_dig_entry_target_facts_from_runtime,
    build_return_to_dig_handoff_config_from_mapping,
    build_return_to_dig_handoff_context_from_runtime,
)
from testbed.planner.return_start_envelope import (
    RETURN_START_ENVELOPE_RUNTIME_CONFIG_FIELDS,
    build_return_start_envelope_config_from_mapping,
    build_return_start_envelope_for_plan,
    build_return_start_envelope_request_from_observation_view,
)
from testbed.planner.return_target_plan import (
    PendingDigCutPlanState,
    PendingReturnTargetActivationFacts,
    ReturnTargetPlanBuildAttemptFacts,
    ReturnTargetPlanBuildFacts,
    ReturnTargetPlanRuntimeUpdate,
    ReturnTargetPlanService,
    ReturnTargetPlanState,
)
from testbed.planner.return_to_dig_transition import (
    ReturnDirectHandoffRuntimeProjection,
    ReturnToDigTransitionCompletion,
    ReturnToDigTransitionCompletionConfig,
    ReturnToDigTransitionCompletionFacts,
    ReturnToDigTransitionCompletionRequest,
    ReturnToDigTransitionRuntimeProjection,
)
from testbed.planner.runtime import PlannerConditioningState
from testbed.policies.base import Policy
from testbed.policies.hybrid import primitive_planner as primitive_planner_module
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def _assert_optional_array_allclose(
    actual: np.ndarray | None,
    expected: np.ndarray | None,
) -> None:
    if expected is None:
        assert actual is None
        return
    assert actual is not None
    np.testing.assert_allclose(actual, expected)


def _assert_float_or_nan(actual: float, expected: float) -> None:
    if np.isnan(expected):
        assert np.isnan(actual)
        return
    assert actual == pytest.approx(expected)


def _assert_dig_start_alignment_configs_equal(
    actual: DigStartAlignmentConfig,
    expected: DigStartAlignmentConfig,
) -> None:
    assert actual.action_dim == expected.action_dim
    np.testing.assert_allclose(actual.qpos_min, expected.qpos_min)
    np.testing.assert_allclose(actual.qpos_max, expected.qpos_max)
    np.testing.assert_allclose(
        actual.qpos_from_token_coefficients,
        expected.qpos_from_token_coefficients,
    )
    np.testing.assert_array_equal(actual.controlled_dims, expected.controlled_dims)
    _assert_optional_array_allclose(
        actual.entry_intent_controlled_dims,
        expected.entry_intent_controlled_dims,
    )
    assert actual.bucket_target_qpos == expected.bucket_target_qpos
    assert actual.kp == pytest.approx(expected.kp)
    assert actual.kd == pytest.approx(expected.kd)
    np.testing.assert_allclose(actual.action_clip, expected.action_clip)
    np.testing.assert_allclose(actual.action_signs, expected.action_signs)
    assert actual.enabled is expected.enabled
    _assert_optional_array_allclose(actual.qpos_tolerance, expected.qpos_tolerance)
    assert actual.qvel_abs_max == pytest.approx(expected.qvel_abs_max)
    assert actual.hold_steps == expected.hold_steps
    assert actual.max_entry_error_m == expected.max_entry_error_m
    assert (
        actual.timeout_accept_entry_error_m
        == expected.timeout_accept_entry_error_m
    )
    assert actual.start_envelope_enabled is expected.start_envelope_enabled
    assert actual.start_envelope_max_entry_error_m == pytest.approx(
        expected.start_envelope_max_entry_error_m
    )
    assert (
        actual.first_dig_entry_close_handoff
        is expected.first_dig_entry_close_handoff
    )
    assert (
        actual.first_dig_entry_close_handoff_qvel_abs_max
        == expected.first_dig_entry_close_handoff_qvel_abs_max
    )
    assert (
        actual.entry_intent_handoff_enabled
        is expected.entry_intent_handoff_enabled
    )
    assert actual.surface_guard_enabled is expected.surface_guard_enabled
    assert actual.surface_guard_max_penetration_m == pytest.approx(
        expected.surface_guard_max_penetration_m
    )
    assert (
        actual.surface_guard_handoff_entry_error_m
        == expected.surface_guard_handoff_entry_error_m
    )
    assert (
        actual.surface_guard_use_contact_fallback
        is expected.surface_guard_use_contact_fallback
    )
    _assert_optional_array_allclose(actual.start_qpos_min, expected.start_qpos_min)
    _assert_optional_array_allclose(actual.start_qpos_max, expected.start_qpos_max)
    _assert_optional_array_allclose(actual.start_pose_min, expected.start_pose_min)
    _assert_optional_array_allclose(actual.start_pose_max, expected.start_pose_max)


def _assert_pre_dig_align_runtime_state_applied(
    policy: PrimitivePlannerACTPolicy,
    expected: Any,
) -> None:
    assert policy._pre_dig_align_step_count == expected.step_count
    assert policy._pre_dig_align_hold_count == expected.hold_count
    assert policy._pre_dig_align_timeout_count == expected.timeout_count
    assert policy._pre_dig_align_completed_count == expected.completed_count
    assert policy._pre_dig_align_replan_count == expected.replan_count
    np.testing.assert_allclose(policy._pre_dig_align_target_qpos, expected.target_qpos)
    np.testing.assert_allclose(policy._pre_dig_align_error, expected.error)
    _assert_float_or_nan(
        policy._pre_dig_align_entry_error_m,
        expected.entry_error_m,
    )
    assert policy._pre_dig_align_start_envelope_ready is (
        expected.start_envelope_ready
    )
    assert policy._pre_dig_align_entry_close_handoff_ready is (
        expected.entry_close_handoff_ready
    )
    assert policy._pre_dig_align_entry_intent_handoff_ready is (
        expected.entry_intent_handoff_ready
    )
    assert (
        policy._pre_dig_align_timeout_handoff_reason
        == expected.timeout_handoff_reason
    )
    _assert_float_or_nan(
        policy._pre_dig_align_surface_depth_m,
        expected.surface_depth_m,
    )
    assert policy._pre_dig_align_surface_guard_triggered is (
        expected.surface_guard_triggered
    )
    assert policy._pre_dig_align_surface_guard_count == (
        expected.surface_guard_count
    )


def test_return_entry_target_prefers_pending_raw_fields_over_active_corridor() -> None:
    policy = _make_policy()
    _set_active_corridor(policy, entry=(9.0, 9.5))
    policy._cycle_index = 4
    policy._pending_dig_cut_cycle_id = 5
    policy._pending_dig_cut_raw_fields = {
        "operator_entry_x_m": 1.25,
        "operator_entry_z_m": -0.75,
    }

    expected = (1.25, -0.75)

    _assert_facade_matches_resolver(policy, expected)
    context = policy._return_to_dig_handoff_context(
        _obs(),
        ensure_return_target=False,
    )
    assert context.entry_target == pytest.approx(expected)
    _assert_entry_error_facade_matches_service(
        policy,
        _obs(bucket_pose=(1.0, 0.0, -0.25)),
        expected=float(np.hypot(-0.25, 0.50)),
    )


def test_boundary_detector_update_facts_facade_preserves_predict_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy._skill_name = "carry"
    previous_action = np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
    env_state = np.ones(64, dtype=np.float32)
    qpos = np.asarray([1.0, 2.0], dtype=np.float32)
    successes = {"dig": 1}
    metrics = {"mass_in_bucket_kg": 3.0}
    obs = {
        "env_state": env_state,
        "qpos": qpos,
        "qvel": np.zeros(4, dtype=np.float32),
        "reward_phase": "digging",
        "task_step_successes": successes,
        "task_metrics": metrics,
    }
    spy_detector = _SpyBoundaryDetector()
    policy.boundary_detector = spy_detector
    policy._prev_action = previous_action
    monkeypatch.setattr(
        policy,
        "_maybe_switch_skill",
        lambda *, obs, boundary_event: None,
    )

    facts = policy._boundary_detector_update_facts(obs)

    assert facts.env_state is env_state
    assert facts.qpos is qpos
    assert facts.action is previous_action
    assert facts.reward_phase == "digging"
    assert facts.task_step_successes is successes
    assert facts.task_metrics is metrics

    policy.predict(obs)

    assert len(spy_detector.calls) == 1
    call = spy_detector.calls[0]
    assert call["env_state"] is env_state
    assert call["qpos"] is qpos
    assert call["action"] is previous_action
    assert call["reward_phase"] == "digging"
    assert call["task_step_successes"] is successes
    assert call["task_metrics"] is metrics


@pytest.mark.parametrize(
    ("pending_cycle_id", "raw_fields"),
    [
        (4, {"operator_entry_x_m": 1.25, "operator_entry_z_m": -0.75}),
        (5, {"operator_entry_x_m": 1.25}),
        (5, {"operator_entry_x_m": np.nan, "operator_entry_z_m": -0.75}),
        (5, {"operator_entry_x_m": 1.25, "operator_entry_z_m": np.inf}),
    ],
)
def test_return_entry_target_falls_back_to_active_corridor_for_bad_pending(
    pending_cycle_id: int,
    raw_fields: dict[str, float],
) -> None:
    policy = _make_policy()
    _set_active_corridor(policy, entry=(0.40, 0.80))
    policy._cycle_index = 4
    policy._pending_dig_cut_cycle_id = pending_cycle_id
    policy._pending_dig_cut_raw_fields = raw_fields

    _assert_facade_matches_resolver(policy, (0.40, 0.80))


def test_return_entry_target_returns_none_without_pending_or_active_corridor() -> None:
    policy = _make_policy()
    policy._cycle_index = 4
    policy._pending_dig_cut_cycle_id = -1
    policy._pending_dig_cut_raw_fields = None
    policy._coverage_active_corridor_id = -1
    policy._coverage_corridors = []

    _assert_facade_matches_resolver(policy, None)
    _assert_entry_error_facade_matches_service(policy, _obs(), expected=None)


def test_pre_dig_align_entry_error_facade_matches_service() -> None:
    policy = _make_policy()
    _set_active_corridor(policy, entry=(0.40, 0.80))
    obs = _obs(bucket_tip_pose=(0.10, 0.0, 0.40))

    _assert_pre_dig_align_entry_error_facade_matches_service(
        policy,
        obs,
        expected=0.5,
    )


def test_pre_dig_align_entry_error_returns_nan_without_active_corridor() -> None:
    policy = _make_policy()
    policy._coverage_active_corridor_id = -1
    policy._coverage_corridors = []

    _assert_pre_dig_align_entry_error_facade_matches_service(
        policy,
        _obs(bucket_tip_pose=(0.10, 0.0, 0.40)),
        expected=None,
    )


def test_dig_start_alignment_facts_facade_matches_service_builder() -> None:
    policy = _make_policy()
    _set_active_corridor(policy, entry=(0.40, 0.80))
    policy._cycle_index = 3
    policy._pre_dig_align_hold_count = 2
    obs = _obs(bucket_pose=(0.20, 0.0, 0.40), bucket_tip_pose=(0.10, 0.0, 0.40))
    obs["task_metrics"] = {
        "bucket_depth_below_local_surface_m": 0.06,
        "bucket_dig_area_penetration_contact_mask": 1.0,
    }
    qpos = np.asarray([[0.1, 0.2, 0.3, 0.4]], dtype=np.float64)
    qvel = np.asarray([[0.01, 0.02, 0.03, 0.04]], dtype=np.float64)
    target_qpos = np.asarray([[1.0, 2.0, 3.0, 4.0]], dtype=np.float64)
    snapshot = policy._make_snapshot(obs)
    entry_error = policy._pre_dig_align_entry_error(obs)

    actual = policy._dig_start_alignment_facts(
        obs,
        target_qpos=target_qpos,
        qpos=qpos,
        qvel=qvel,
    )
    expected = policy.dig_start_alignment_service.facts_from_observation_view(
        view=snapshot.view,
        target_qpos=target_qpos,
        entry_error_m=entry_error,
        qpos=qpos,
        qvel=qvel,
        cycle_index=policy._cycle_index,
        hold_count=policy._pre_dig_align_hold_count,
    )

    np.testing.assert_allclose(actual.qpos, expected.qpos)
    np.testing.assert_allclose(actual.qvel, expected.qvel)
    np.testing.assert_allclose(actual.target_qpos, expected.target_qpos)
    assert actual.qpos.dtype == np.float32
    assert actual.qvel.dtype == np.float32
    assert actual.target_qpos is not None
    assert actual.target_qpos.dtype == np.float32
    assert actual.entry_error_m == pytest.approx(0.5)
    assert actual.entry_error_m == pytest.approx(expected.entry_error_m)
    assert actual.bucket_pose == expected.bucket_pose
    if np.isnan(expected.surface_depth_m):
        assert np.isnan(actual.surface_depth_m)
    else:
        assert actual.surface_depth_m == pytest.approx(expected.surface_depth_m)
    assert actual.contact_mask is expected.contact_mask
    assert actual.cycle_index == expected.cycle_index
    assert actual.hold_count == expected.hold_count


def test_dig_start_alignment_facts_facade_preserves_qpos_qvel_overrides() -> None:
    policy = _make_policy()
    obs = _obs(bucket_pose=(0.20, 0.0, 0.40))
    obs["qpos"] = object()
    obs["qvel"] = object()
    qpos = np.asarray([[0.1, 0.2, 0.3, 0.4]], dtype=np.float64)
    qvel = np.asarray([[0.01, 0.02, 0.03, 0.04]], dtype=np.float64)

    facts = policy._dig_start_alignment_facts(
        obs,
        entry_error=float("nan"),
        qpos=qpos,
        qvel=qvel,
    )

    np.testing.assert_allclose(
        facts.qpos,
        np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
    )
    np.testing.assert_allclose(
        facts.qvel,
        np.asarray([0.01, 0.02, 0.03, 0.04], dtype=np.float32),
    )


def test_dig_start_alignment_config_facade_uses_domain_builder() -> None:
    policy = _make_policy()
    qpos_min = np.asarray([-1.0, -0.9, -0.8, -0.7], dtype=np.float64)
    qpos_max = np.asarray([1.0, 0.9, 0.8, 0.7], dtype=np.float64)
    coefficients = np.arange(12, dtype=np.float64).reshape(4, 3)
    controlled_dims = np.asarray([True, False, True, False])
    entry_intent_dims = np.asarray([False, True, False, True])
    qpos_tolerance = np.asarray([0.01, 0.02, 0.03, 0.04])
    start_qpos_min = np.asarray([-0.5, -0.4, -0.3, -0.2])
    start_qpos_max = np.asarray([0.5, 0.4, 0.3, 0.2])
    start_pose_min = np.asarray([-0.6, -0.7])
    start_pose_max = np.asarray([0.6, 0.7])

    policy.action_dim = "4"
    policy.pre_dig_align_qpos_min = qpos_min
    policy.pre_dig_align_qpos_max = qpos_max
    policy.pre_dig_align_qpos_from_token_coefficients = coefficients
    policy.pre_dig_align_controlled_dims = controlled_dims
    policy.pre_dig_align_entry_intent_controlled_dims = entry_intent_dims
    policy.pre_dig_align_bucket_target_qpos = "-0.25"
    policy.pre_dig_align_kp = "11.0"
    policy.pre_dig_align_kd = "0.5"
    policy.pre_dig_align_action_clip = [0.1, 0.2, 0.3, 0.4]
    policy.pre_dig_align_action_signs = [1.0, -1.0, 1.0, -1.0]
    policy.pre_dig_align_enabled = 1
    policy.pre_dig_align_qpos_tolerance = qpos_tolerance
    policy.pre_dig_align_qvel_abs_max = "0.12"
    policy.pre_dig_align_hold_steps = "3"
    policy.pre_dig_align_max_entry_error_m = "0.55"
    policy.pre_dig_align_timeout_accept_entry_error_m = "0.25"
    policy.pre_dig_align_start_envelope_enabled = 1
    policy.pre_dig_align_start_envelope_max_entry_error_m = "0.65"
    policy.pre_dig_align_first_dig_entry_close_handoff = 1
    policy.pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max = "0.07"
    policy.pre_dig_align_entry_intent_handoff_enabled = 1
    policy.pre_dig_align_surface_guard_enabled = 1
    policy.pre_dig_align_surface_guard_max_penetration_m = "0.005"
    policy.pre_dig_align_surface_guard_handoff_entry_error_m = "0.35"
    policy.pre_dig_align_surface_guard_use_contact_fallback = 0
    policy.pre_dig_align_start_qpos_min = start_qpos_min
    policy.pre_dig_align_start_qpos_max = start_qpos_max
    policy.pre_dig_align_start_pose_min = start_pose_min
    policy.pre_dig_align_start_pose_max = start_pose_max

    expected = build_dig_start_alignment_runtime_config_from_mapping(
        {
            config_key: getattr(policy, attr_name)
            for config_key, attr_name in (
                DIG_START_ALIGNMENT_RUNTIME_CONFIG_FIELDS
            )
        }
    )
    actual = policy._dig_start_alignment_config()

    _assert_dig_start_alignment_configs_equal(actual, expected)


def test_pre_dig_align_runtime_state_facade_uses_runtime_builder() -> None:
    policy = _make_policy()
    target_qpos = np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float64)
    error = np.asarray([0.01, -0.02, 0.03, -0.04], dtype=np.float64)
    policy._pre_dig_align_step_count = "1"
    policy._pre_dig_align_hold_count = np.int64(2)
    policy._pre_dig_align_timeout_count = "3"
    policy._pre_dig_align_completed_count = np.int64(4)
    policy._pre_dig_align_replan_count = "5"
    policy._pre_dig_align_target_qpos = target_qpos
    policy._pre_dig_align_error = error
    policy._pre_dig_align_entry_error_m = "0.25"
    policy._pre_dig_align_start_envelope_ready = 1
    policy._pre_dig_align_entry_close_handoff_ready = 0
    policy._pre_dig_align_entry_intent_handoff_ready = 1
    policy._pre_dig_align_timeout_handoff_reason = 123
    policy._pre_dig_align_surface_depth_m = "0.05"
    policy._pre_dig_align_surface_guard_triggered = 1
    policy._pre_dig_align_surface_guard_count = np.int64(6)

    expected = runtime_state_from_mapping(
        {
            field_name: getattr(policy, attr_name)
            for field_name, attr_name in DIG_START_ALIGNMENT_RUNTIME_STATE_FIELDS
        }
    )
    actual = policy._pre_dig_align_runtime_state()

    assert actual.step_count == expected.step_count
    assert actual.hold_count == expected.hold_count
    assert actual.timeout_count == expected.timeout_count
    assert actual.completed_count == expected.completed_count
    assert actual.replan_count == expected.replan_count
    assert actual.target_qpos is expected.target_qpos
    assert actual.error is expected.error
    assert actual.entry_error_m == expected.entry_error_m
    assert actual.start_envelope_ready is expected.start_envelope_ready
    assert actual.entry_close_handoff_ready is expected.entry_close_handoff_ready
    assert actual.entry_intent_handoff_ready is expected.entry_intent_handoff_ready
    assert actual.timeout_handoff_reason == expected.timeout_handoff_reason
    assert actual.surface_depth_m == expected.surface_depth_m
    assert actual.surface_guard_triggered is expected.surface_guard_triggered
    assert actual.surface_guard_count == expected.surface_guard_count


def test_pre_dig_align_surface_guard_decision_apply_facade_matches_service_projection() -> None:
    policy = _make_policy()
    policy._pre_dig_align_surface_depth_m = 0.02
    policy._pre_dig_align_surface_guard_triggered = False
    policy._pre_dig_align_surface_guard_count = 4
    decision = SurfaceGuardDecision(triggered=True, surface_depth_m=0.08)
    expected = policy.dig_start_alignment_service.surface_guard_runtime_state(
        policy._pre_dig_align_runtime_state(),
        decision,
    )

    assert policy._apply_pre_dig_align_surface_guard_decision(decision) is True

    _assert_pre_dig_align_runtime_state_applied(policy, expected)


def test_pre_dig_align_ready_decision_apply_facade_matches_service_projection() -> None:
    policy = _make_policy()
    decision = AlignmentReadyDecision(
        ready=True,
        hold_count=3,
        error=np.asarray([0.01, -0.02, 0.03, -0.04], dtype=np.float64),
        qpos_close=True,
        qvel_small=True,
        entry_close=True,
        start_envelope_ready=True,
        entry_close_handoff_ready=True,
        entry_intent_handoff_ready=False,
    )
    expected = policy.dig_start_alignment_service.ready_runtime_state(
        policy._pre_dig_align_runtime_state(),
        decision,
        entry_error_m=0.12,
    )

    assert (
        policy._apply_pre_dig_align_ready_decision(
            decision,
            entry_error_m=0.12,
        )
        is True
    )

    _assert_pre_dig_align_runtime_state_applied(policy, expected)
    assert policy._pre_dig_align_error.dtype == np.float32


def test_pre_dig_align_timeout_decision_apply_facade_matches_service_projection() -> None:
    policy = _make_policy()
    policy._pre_dig_align_entry_error_m = 0.77
    policy._pre_dig_align_start_envelope_ready = False
    policy._pre_dig_align_entry_intent_handoff_ready = True
    decision = TimeoutHandoffDecision(
        ready=False,
        reason="pre_dig_align_timeout_entry_gap",
        start_envelope_ready=True,
        entry_intent_handoff_ready=False,
    )
    expected = policy.dig_start_alignment_service.timeout_handoff_runtime_state(
        policy._pre_dig_align_runtime_state(),
        decision,
        sampled_entry_error_m=0.22,
    )

    assert (
        policy._apply_pre_dig_align_timeout_handoff_decision(
            decision,
            sampled_entry_error_m=0.22,
        )
        is False
    )

    _assert_pre_dig_align_runtime_state_applied(policy, expected)


def test_pre_dig_align_entry_error_runtime_apply_facade_matches_service_projection() -> None:
    policy = _make_policy()
    policy._pre_dig_align_entry_error_m = 0.77
    policy._pre_dig_align_start_envelope_ready = True
    policy._pre_dig_align_entry_close_handoff_ready = True
    policy._pre_dig_align_entry_intent_handoff_ready = True
    expected = policy.dig_start_alignment_service.entry_error_runtime_state(
        policy._pre_dig_align_runtime_state(),
        entry_error_m=0.18,
    )

    policy._apply_pre_dig_align_entry_error_runtime_state(entry_error_m=0.18)

    _assert_pre_dig_align_runtime_state_applied(policy, expected)


def test_pre_dig_align_action_decision_apply_facade_matches_service_projection() -> None:
    policy = _make_policy()
    decision = AlignmentActionDecision(
        action=np.asarray([0.10, -0.20, 0.30, -0.40], dtype=np.float64),
        error=np.asarray([0.01, -0.02, 0.03, -0.04], dtype=np.float64),
        entry_error_m=0.24,
    )
    expected = policy.dig_start_alignment_service.action_runtime_state(
        policy._pre_dig_align_runtime_state(),
        decision,
    )

    action = policy._apply_pre_dig_align_action_decision(decision)

    np.testing.assert_allclose(action, decision.action)
    assert action is decision.action
    _assert_pre_dig_align_runtime_state_applied(policy, expected)
    assert policy._pre_dig_align_error.dtype == np.float32


def test_pre_dig_align_target_runtime_apply_facade_matches_service_projection() -> None:
    policy = _make_policy()
    target_qpos = np.asarray([1.0, 2.0, 3.0, 4.0], dtype=np.float64)
    expected = policy.dig_start_alignment_service.target_runtime_state(
        policy._pre_dig_align_runtime_state(),
        target_qpos=target_qpos,
        config=policy._dig_start_alignment_config(),
    )

    policy._apply_pre_dig_align_target_runtime_state(target_qpos=target_qpos)

    _assert_pre_dig_align_runtime_state_applied(policy, expected)
    assert policy._pre_dig_align_target_qpos.dtype == np.float32
    assert policy._pre_dig_align_target_qpos is not target_qpos


def test_pre_dig_align_action_facade_matches_service_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy.pre_dig_align_enabled = True
    target_qpos = np.asarray([1.0, 2.0, 3.0, 4.0], dtype=np.float32)
    obs = _obs()
    obs["qpos"] = np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float64)
    obs["qvel"] = np.asarray([0.01, 0.02, 0.03, 0.04], dtype=np.float64)

    def target_for_obs(_obs: dict[str, np.ndarray]) -> np.ndarray:
        policy._pre_dig_align_target_qpos = target_qpos.copy()
        return target_qpos.copy()

    monkeypatch.setattr(policy, "_pre_dig_align_target", target_for_obs)
    monkeypatch.setattr(policy, "_pre_dig_align_entry_error", lambda _obs: 0.25)
    expected = (
        policy.dig_start_alignment_service.action_decision_from_observation_view(
            view=policy._make_snapshot(obs).view,
            target_qpos=target_qpos,
            entry_error_m=0.25,
            config=policy._dig_start_alignment_config(),
            cycle_index=policy._cycle_index,
            hold_count=policy._pre_dig_align_hold_count,
        )
    )

    action = policy._pre_dig_align_action(obs)

    np.testing.assert_allclose(action, expected.action)
    np.testing.assert_allclose(policy._pre_dig_align_error, expected.error)
    assert action.dtype == np.float32
    assert policy._pre_dig_align_error.dtype == np.float32
    assert policy._pre_dig_align_entry_error_m == pytest.approx(
        expected.entry_error_m
    )
    assert policy._pre_dig_align_step_count == 1


def test_pre_dig_align_ready_facade_matches_service_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy.pre_dig_align_enabled = True
    policy.pre_dig_align_hold_steps = 1
    policy.pre_dig_align_qpos_tolerance = np.asarray(
        [0.1, 0.1, 0.1, 0.1],
        dtype=np.float32,
    )
    target_qpos = np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
    obs = _obs()
    obs["qpos"] = target_qpos.astype(np.float64)
    obs["qvel"] = np.asarray([0.01, 0.02, 0.03, 0.04], dtype=np.float64)

    monkeypatch.setattr(
        policy,
        "_pre_dig_align_target",
        lambda _obs: target_qpos.copy(),
    )
    monkeypatch.setattr(policy, "_pre_dig_align_entry_error", lambda _obs: 0.05)
    expected = policy.dig_start_alignment_service.ready_from_observation_view(
        view=policy._make_snapshot(obs).view,
        target_qpos=target_qpos,
        entry_error_m=0.05,
        config=policy._dig_start_alignment_config(),
        cycle_index=policy._cycle_index,
        hold_count=policy._pre_dig_align_hold_count,
    )

    ready = policy._pre_dig_align_ready(obs)

    assert ready is expected.ready
    np.testing.assert_allclose(policy._pre_dig_align_error, expected.error)
    assert policy._pre_dig_align_error.dtype == np.float32
    assert policy._pre_dig_align_start_envelope_ready is (
        expected.start_envelope_ready
    )
    assert policy._pre_dig_align_entry_close_handoff_ready is (
        expected.entry_close_handoff_ready
    )
    assert policy._pre_dig_align_entry_intent_handoff_ready is (
        expected.entry_intent_handoff_ready
    )
    assert policy._pre_dig_align_hold_count == expected.hold_count
    assert policy._pre_dig_align_entry_error_m == pytest.approx(0.05)


def test_pre_dig_align_entry_close_handoff_facade_uses_service_facts() -> None:
    policy = _make_policy()
    policy.pre_dig_align_start_envelope_enabled = True
    policy.pre_dig_align_first_dig_entry_close_handoff = True
    policy.pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max = 0.15
    policy.pre_dig_align_max_entry_error_m = 0.35
    policy._cycle_index = np.int64(0)
    qvel = np.asarray([[0.0, 0.03, -0.10, -0.02]], dtype=np.float64)

    expected = (
        policy.dig_start_alignment_service.entry_close_handoff_ready_from_runtime_values(
            action_dim=int(policy.action_dim),
            qvel=qvel,
            entry_error_m=0.20,
            cycle_index=policy._cycle_index,
            config=policy._dig_start_alignment_config(),
            start_envelope_ready=True,
        )
    )
    actual = policy._pre_dig_align_entry_close_handoff_ready_for_state(
        entry_error=0.20,
        qvel=qvel,
        start_envelope_ready=True,
    )

    assert actual is expected


def test_pre_dig_align_start_envelope_facade_uses_service_facts() -> None:
    policy = _make_policy()
    policy.pre_dig_align_start_envelope_enabled = True
    policy.pre_dig_align_start_envelope_max_entry_error_m = 0.65
    policy.pre_dig_align_start_qpos_min = np.asarray(
        [0.0, 0.0, 0.0, 0.0],
        dtype=np.float64,
    )
    policy.pre_dig_align_start_qpos_max = np.asarray(
        [1.0, 1.0, 1.0, 1.0],
        dtype=np.float64,
    )
    policy.pre_dig_align_start_pose_min = np.asarray(
        [-0.6, -0.3, -1.5],
        dtype=np.float64,
    )
    policy.pre_dig_align_start_pose_max = np.asarray(
        [1.65, 0.25, 1.2],
        dtype=np.float64,
    )
    obs = _obs(bucket_pose=(0.5, 0.0, -0.5))
    obs["qvel"] = object()
    qpos = np.asarray([[0.5, 0.6, 0.1, 0.0]], dtype=np.float64)
    snapshot_obs = dict(obs)
    snapshot_obs["qpos"] = qpos
    snapshot_obs["qvel"] = np.zeros(policy.action_dim, dtype=np.float32)
    snapshot = policy._make_snapshot(snapshot_obs)

    expected = (
        policy.dig_start_alignment_service.start_envelope_ready_from_observation_view(
            view=snapshot.view,
            qpos=qpos,
            entry_error_m=0.40,
            config=policy._dig_start_alignment_config(),
        )
    )
    actual = policy._pre_dig_align_start_envelope_ready_for_state(
        obs=obs,
        qpos=qpos,
        entry_error=0.40,
    )

    assert actual is expected


def test_pre_dig_align_timeout_no_gate_uses_existing_entry_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy.pre_dig_align_timeout_accept_entry_error_m = None
    policy.pre_dig_align_max_entry_error_m = None
    policy._pre_dig_align_entry_error_m = 0.77

    def fail_entry_error(_obs: dict[str, np.ndarray]) -> float:
        raise AssertionError("no-entry-gate timeout should not resample entry error")

    monkeypatch.setattr(policy, "_pre_dig_align_entry_error", fail_entry_error)
    obs = _obs()
    obs["qpos"] = object()
    obs["qvel"] = object()
    config = policy._dig_start_alignment_config()
    request = policy.dig_start_alignment_service.timeout_handoff_request(
        current_entry_error_m=float(policy._pre_dig_align_entry_error_m),
        config=config,
    )
    expected = policy.dig_start_alignment_service.timeout_handoff_decision(
        request=request,
        config=config,
        action_dim=int(policy.action_dim),
    )

    assert policy._pre_dig_align_timeout_can_handoff(obs) is expected.ready
    assert policy._pre_dig_align_entry_error_m == pytest.approx(0.77)
    assert policy._pre_dig_align_timeout_handoff_reason == expected.reason


def test_pre_dig_align_timeout_threshold_samples_entry_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy.pre_dig_align_timeout_accept_entry_error_m = 0.20
    policy.pre_dig_align_max_entry_error_m = None
    policy._pre_dig_align_entry_error_m = 0.77
    calls: list[str] = []

    def entry_error(_obs: dict[str, np.ndarray]) -> float:
        calls.append("entry_error")
        return 0.10

    monkeypatch.setattr(policy, "_pre_dig_align_entry_error", entry_error)

    obs = _obs(bucket_pose=(0.5, 0.0, -0.5))
    obs["qpos"] = np.asarray([[0.1, 0.2, 0.3, 0.4]], dtype=np.float64)
    obs["qvel"] = np.asarray([[0.4, 0.3, 0.2, 0.1]], dtype=np.float64)
    request = policy.dig_start_alignment_service.timeout_handoff_request(
        current_entry_error_m=float(policy._pre_dig_align_entry_error_m),
        config=policy._dig_start_alignment_config(),
    )
    expected = policy.dig_start_alignment_service.timeout_handoff_decision(
        request=request,
        config=policy._dig_start_alignment_config(),
        action_dim=int(policy.action_dim),
        view=policy._make_snapshot(obs).view,
        sampled_entry_error_m=0.10,
    )

    assert policy._pre_dig_align_timeout_can_handoff(obs) is expected.ready
    assert calls == ["entry_error"]
    assert policy._pre_dig_align_entry_error_m == pytest.approx(0.10)
    assert policy._pre_dig_align_start_envelope_ready is expected.start_envelope_ready
    assert policy._pre_dig_align_entry_intent_handoff_ready is False
    assert policy._pre_dig_align_timeout_handoff_reason == expected.reason


def test_pre_dig_align_surface_guard_handoff_projects_entry_error_before_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy.pre_dig_align_surface_guard_handoff_entry_error_m = 0.20
    policy._pre_dig_align_entry_error_m = 0.77
    policy._pre_dig_align_step_count = 9
    policy._pre_dig_align_hold_count = 8
    policy._pre_dig_align_timeout_count = 7
    policy._pre_dig_align_completed_count = 6
    policy._pre_dig_align_replan_count = 5
    policy._pre_dig_align_start_envelope_ready = True
    policy._pre_dig_align_entry_close_handoff_ready = True
    policy._pre_dig_align_entry_intent_handoff_ready = True
    policy._pre_dig_align_timeout_handoff_reason = "old_timeout_reason"
    policy._pre_dig_align_surface_depth_m = 0.03
    policy._pre_dig_align_surface_guard_triggered = True
    policy._pre_dig_align_surface_guard_count = 4
    calls: list[str] = []

    monkeypatch.setattr(
        policy,
        "_ensure_dig_cut_plan_for_cycle",
        lambda _obs: calls.append("ensure"),
    )
    monkeypatch.setattr(policy, "_pre_dig_align_entry_error", lambda _obs: 0.12)

    def surface_guard_can_handoff_from_observation_view(
        *,
        view: Any,
        entry_error_m: float,
        config: DigStartAlignmentConfig,
        cycle_index: int = 0,
        hold_count: int = 0,
    ) -> bool:
        assert policy._pre_dig_align_entry_error_m == pytest.approx(0.12)
        assert entry_error_m == pytest.approx(0.12)
        assert view.action_dim == policy.action_dim
        assert config.surface_guard_handoff_entry_error_m == pytest.approx(0.20)
        assert cycle_index == policy._cycle_index
        assert hold_count == policy._pre_dig_align_hold_count
        calls.append("gate")
        return True

    monkeypatch.setattr(
        policy.dig_start_alignment_service,
        "surface_guard_can_handoff_from_observation_view",
        surface_guard_can_handoff_from_observation_view,
    )

    assert policy._pre_dig_align_surface_guard_can_handoff(_obs())

    assert calls == ["ensure", "gate"]
    assert policy._pre_dig_align_entry_error_m == pytest.approx(0.12)
    assert policy._pre_dig_align_step_count == 9
    assert policy._pre_dig_align_hold_count == 8
    assert policy._pre_dig_align_timeout_count == 7
    assert policy._pre_dig_align_completed_count == 6
    assert policy._pre_dig_align_replan_count == 5
    assert policy._pre_dig_align_start_envelope_ready is True
    assert policy._pre_dig_align_entry_close_handoff_ready is True
    assert policy._pre_dig_align_entry_intent_handoff_ready is True
    assert policy._pre_dig_align_timeout_handoff_reason == "old_timeout_reason"
    assert policy._pre_dig_align_surface_depth_m == pytest.approx(0.03)
    assert policy._pre_dig_align_surface_guard_triggered is True
    assert policy._pre_dig_align_surface_guard_count == 4


def test_pre_dig_align_outcome_runtime_projection_apply_facade_preserves_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy._skill_name = "pre_dig_align"
    policy._pre_dig_align_timeout_count = 7
    projection = policy.dig_start_alignment_service.outcome_runtime_projection(
        PreDigAlignOutcomeRuntimeFacts(
            outcome=PreDigAlignOutcome(
                action="timeout_replan",
                switch_reason="pre_dig_align_retry_entry_gap",
                reject_reason="align_entry_gap_timeout",
            ),
            state=policy._pre_dig_align_runtime_state(),
        )
    )
    events: list[tuple[str, str]] = []
    apply_runtime_state = policy._apply_pre_dig_align_runtime_state

    def apply_state(state: Any) -> None:
        apply_runtime_state(state)
        events.append(("apply_state", str(policy._pre_dig_align_timeout_count)))

    def reject(_obs: dict[str, np.ndarray], *, reason: str) -> None:
        assert policy._pre_dig_align_timeout_count == 8
        events.append(("reject", reason))

    def try_replan(_obs: dict[str, np.ndarray]) -> bool:
        assert policy._pre_dig_align_timeout_count == 8
        events.append(("try_replan", ""))
        return False

    def restart(reason: str) -> None:
        assert policy._pre_dig_align_timeout_count == 8
        events.append(("restart", reason))

    monkeypatch.setattr(policy, "_apply_pre_dig_align_runtime_state", apply_state)
    monkeypatch.setattr(policy, "_reject_active_coverage_corridor", reject)
    monkeypatch.setattr(policy, "_try_replan_pre_dig_align_handoff", try_replan)
    monkeypatch.setattr(policy, "_restart_pre_dig_align", restart)

    assert policy._apply_pre_dig_align_outcome_runtime_projection(
        projection,
        _obs(),
    )
    assert events == [
        ("apply_state", "8"),
        ("reject", "align_entry_gap_timeout"),
        ("try_replan", ""),
        ("restart", "pre_dig_align_retry_entry_gap"),
    ]


def test_pre_dig_align_outcome_apply_facade_projects_current_runtime_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy._pre_dig_align_timeout_count = 7
    policy._pre_dig_align_completed_count = 6
    policy._pre_dig_align_surface_guard_count = 4
    outcome = PreDigAlignOutcome(
        action="timeout_handoff",
        switch_reason="pre_dig_align_to_dig_timeout_close_enough",
    )
    calls: list[tuple[str, str]] = []

    def apply_projection(projection: Any, _obs: dict[str, np.ndarray]) -> bool:
        assert projection.should_handoff_to_dig
        assert (
            projection.switch_reason
            == "pre_dig_align_to_dig_timeout_close_enough"
        )
        assert projection.runtime_state.timeout_count == 8
        assert projection.runtime_state.completed_count == 6
        assert projection.runtime_state.surface_guard_count == 4
        calls.append(("apply_projection", projection.switch_reason))
        return True

    monkeypatch.setattr(
        policy,
        "_apply_pre_dig_align_outcome_runtime_projection",
        apply_projection,
    )

    assert policy._apply_pre_dig_align_outcome(outcome, _obs())
    assert calls == [
        ("apply_projection", "pre_dig_align_to_dig_timeout_close_enough")
    ]
    assert policy._pre_dig_align_timeout_count == 7
    assert policy._pre_dig_align_completed_count == 6
    assert policy._pre_dig_align_surface_guard_count == 4


def test_pre_dig_align_surface_guard_handoff_applies_projection_before_set_skill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy._skill_name = "pre_dig_align"
    policy._pre_dig_align_hold_count = 8
    policy._pre_dig_align_completed_count = 6
    policy._pre_dig_align_surface_guard_count = 4
    calls: list[tuple[str, str]] = []

    monkeypatch.setattr(
        policy,
        "_pre_dig_align_outcome",
        lambda _obs: PreDigAlignOutcome(
            action="surface_guard_handoff",
            switch_reason="pre_dig_align_to_dig_surface_guard",
        ),
    )

    def set_skill(skill_name: str, reason: str) -> None:
        assert policy._pre_dig_align_hold_count == 0
        assert policy._pre_dig_align_completed_count == 7
        assert policy._pre_dig_align_surface_guard_count == 5
        calls.append((skill_name, reason))

    monkeypatch.setattr(policy, "_set_skill", set_skill)

    policy._maybe_switch_skill(obs=_obs(), boundary_event=None)

    assert calls == [("dig", "pre_dig_align_to_dig_surface_guard")]


def test_pre_dig_align_timeout_replan_applies_projection_before_replan_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy._skill_name = "pre_dig_align"
    policy._pre_dig_align_timeout_count = 7
    events: list[tuple[str, str]] = []

    monkeypatch.setattr(
        policy,
        "_pre_dig_align_outcome",
        lambda _obs: PreDigAlignOutcome(
            action="timeout_replan",
            switch_reason="pre_dig_align_retry_entry_gap",
            reject_reason="align_entry_gap_timeout",
        ),
    )

    def reject(_obs: dict[str, np.ndarray], *, reason: str) -> None:
        assert policy._pre_dig_align_timeout_count == 8
        events.append(("reject", reason))

    def try_replan(_obs: dict[str, np.ndarray]) -> bool:
        assert policy._pre_dig_align_timeout_count == 8
        events.append(("try_replan", ""))
        return False

    def restart(reason: str) -> None:
        assert policy._pre_dig_align_timeout_count == 8
        events.append(("restart", reason))

    monkeypatch.setattr(policy, "_reject_active_coverage_corridor", reject)
    monkeypatch.setattr(policy, "_try_replan_pre_dig_align_handoff", try_replan)
    monkeypatch.setattr(policy, "_restart_pre_dig_align", restart)

    policy._maybe_switch_skill(obs=_obs(), boundary_event=None)

    assert events == [
        ("reject", "align_entry_gap_timeout"),
        ("try_replan", ""),
        ("restart", "pre_dig_align_retry_entry_gap"),
    ]


def test_pre_dig_align_lifecycle_runtime_apply_facades_match_service_projection() -> None:
    def seeded_policy() -> PrimitivePlannerACTPolicy:
        policy = _make_policy()
        policy._pre_dig_align_step_count = 9
        policy._pre_dig_align_hold_count = 8
        policy._pre_dig_align_timeout_count = 7
        policy._pre_dig_align_completed_count = 6
        policy._pre_dig_align_replan_count = 5
        policy._pre_dig_align_target_qpos = np.asarray(
            [0.1, 0.2, 0.3, 0.4],
            dtype=np.float32,
        )
        policy._pre_dig_align_error = np.asarray(
            [0.01, -0.02, 0.03, -0.04],
            dtype=np.float32,
        )
        policy._pre_dig_align_entry_error_m = 0.25
        policy._pre_dig_align_start_envelope_ready = True
        policy._pre_dig_align_entry_close_handoff_ready = True
        policy._pre_dig_align_entry_intent_handoff_ready = True
        policy._pre_dig_align_timeout_handoff_reason = (
            "pre_dig_align_to_dig_timeout_intent_aligned"
        )
        policy._pre_dig_align_surface_depth_m = 0.03
        policy._pre_dig_align_surface_guard_triggered = True
        policy._pre_dig_align_surface_guard_count = 4
        return policy

    cases = (
        (
            "_apply_pre_dig_align_initial_runtime_state",
            lambda policy: policy.dig_start_alignment_service.initial_runtime_state(
                policy._dig_start_alignment_config()
            ),
        ),
        (
            "_apply_pre_dig_align_enter_runtime_state",
            lambda policy: policy.dig_start_alignment_service.enter_runtime_state(
                policy._pre_dig_align_runtime_state(),
                policy._dig_start_alignment_config(),
            ),
        ),
        (
            "_apply_pre_dig_align_restart_runtime_state",
            lambda policy: policy.dig_start_alignment_service.restart_runtime_state(
                policy._pre_dig_align_runtime_state(),
                policy._dig_start_alignment_config(),
            ),
        ),
        (
            "_apply_pre_dig_align_replan_handoff_runtime_state",
            lambda policy: (
                policy.dig_start_alignment_service.replan_handoff_runtime_state(
                    policy._pre_dig_align_runtime_state(),
                    policy._dig_start_alignment_config(),
                )
            ),
        ),
    )

    for method_name, expected_state in cases:
        policy = seeded_policy()
        expected = expected_state(policy)

        getattr(policy, method_name)()

        _assert_pre_dig_align_runtime_state_applied(policy, expected)


def test_set_skill_pre_dig_align_applies_service_enter_runtime_projection() -> None:
    policy = _make_policy()
    policy._skill_name = "return"
    policy._return_next_dig_event_seen = True
    policy._pre_dig_align_step_count = 9
    policy._pre_dig_align_hold_count = 8
    policy._pre_dig_align_timeout_count = 7
    policy._pre_dig_align_completed_count = 6
    policy._pre_dig_align_replan_count = 5
    policy._pre_dig_align_target_qpos = np.asarray(
        [0.1, 0.2, 0.3, 0.4],
        dtype=np.float32,
    )
    policy._pre_dig_align_error = np.asarray(
        [0.01, -0.02, 0.03, -0.04],
        dtype=np.float32,
    )
    policy._pre_dig_align_entry_error_m = 0.25
    policy._pre_dig_align_start_envelope_ready = True
    policy._pre_dig_align_entry_close_handoff_ready = True
    policy._pre_dig_align_entry_intent_handoff_ready = True
    policy._pre_dig_align_timeout_handoff_reason = (
        "pre_dig_align_to_dig_timeout_intent_aligned"
    )
    policy._pre_dig_align_surface_depth_m = 0.03
    policy._pre_dig_align_surface_guard_triggered = True
    policy._pre_dig_align_surface_guard_count = 4
    policy._dig_cut_tokens = np.ones(DIG_CUT_TOKEN_DIM, dtype=np.float32)

    def fail_reset() -> None:
        raise AssertionError("pre-dig-align entry must not reset active policy")

    policy.return_policy.reset = fail_reset  # type: ignore[method-assign]

    policy._set_skill("pre_dig_align", "unit_enter")

    assert policy._skill_name == "pre_dig_align"
    assert policy._switch_reason == "unit_enter"
    assert policy._pre_dig_align_step_count == 0
    assert policy._pre_dig_align_hold_count == 0
    assert policy._pre_dig_align_timeout_count == 7
    assert policy._pre_dig_align_completed_count == 6
    assert policy._pre_dig_align_replan_count == 5
    np.testing.assert_allclose(
        policy._pre_dig_align_target_qpos,
        np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
    )
    np.testing.assert_allclose(
        policy._pre_dig_align_error,
        np.asarray([0.01, -0.02, 0.03, -0.04], dtype=np.float32),
    )
    assert policy._pre_dig_align_entry_error_m == pytest.approx(0.25)
    assert policy._pre_dig_align_start_envelope_ready is True
    assert policy._pre_dig_align_entry_close_handoff_ready is False
    assert policy._pre_dig_align_entry_intent_handoff_ready is False
    assert policy._pre_dig_align_timeout_handoff_reason == ""
    assert policy._pre_dig_align_surface_depth_m == pytest.approx(0.03)
    assert policy._pre_dig_align_surface_guard_triggered is False
    assert policy._pre_dig_align_surface_guard_count == 4
    assert policy._return_next_dig_event_seen is True
    assert float(np.min(policy._dig_cut_tokens)) == pytest.approx(1.0)


def test_try_replan_pre_dig_align_handoff_applies_service_runtime_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy.dig_cut_planner_mode = "operator_prior_coverage"
    policy._skill_name = "pre_dig_align"
    policy._coverage_active_corridor_id = 3
    policy._pending_dig_cut_cycle_id = 2
    policy._pending_dig_cut_raw_fields = {"operator_entry_x_m": 1.0}
    policy._pre_dig_align_step_count = 9
    policy._pre_dig_align_hold_count = 8
    policy._pre_dig_align_timeout_count = 7
    policy._pre_dig_align_completed_count = 6
    policy._pre_dig_align_replan_count = 5
    policy._pre_dig_align_target_qpos = np.asarray(
        [0.1, 0.2, 0.3, 0.4],
        dtype=np.float32,
    )
    policy._pre_dig_align_error = np.asarray(
        [0.01, -0.02, 0.03, -0.04],
        dtype=np.float32,
    )
    policy._pre_dig_align_entry_error_m = 0.25
    policy._pre_dig_align_start_envelope_ready = True
    policy._pre_dig_align_entry_close_handoff_ready = True
    policy._pre_dig_align_entry_intent_handoff_ready = False
    policy._pre_dig_align_timeout_handoff_reason = "old_timeout_reason"
    policy._pre_dig_align_surface_depth_m = 0.03
    policy._pre_dig_align_surface_guard_triggered = True
    policy._pre_dig_align_surface_guard_count = 4
    policy._dig_step_count = 11
    policy._dig_best_mass_kg = 22.0
    policy._dig_mass_plateau_count = 3
    policy._dig_to_carry_reason = "target_payload_loaded"
    policy._coverage_current_payload_gain_kg = 18.0
    token = np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float32)
    raw_fields = {"operator_entry_x_m": 0.40, "operator_entry_z_m": 0.80}
    reset_calls: list[str] = []

    monkeypatch.setattr(
        policy,
        "_build_operator_prior_coverage_dig_cut_tokens",
        lambda _obs: (token, raw_fields, "unit_replan", ""),
    )
    monkeypatch.setattr(policy, "_raw_fields_in_prior_range", lambda _fields: True)
    monkeypatch.setattr(policy, "_pre_dig_align_entry_error", lambda _obs: 0.12)

    def timeout_can_handoff(_obs: dict[str, np.ndarray]) -> bool:
        assert policy._pre_dig_align_entry_error_m == pytest.approx(0.12)
        policy._pre_dig_align_start_envelope_ready = False
        policy._pre_dig_align_entry_intent_handoff_ready = True
        policy._pre_dig_align_timeout_handoff_reason = (
            "pre_dig_align_to_dig_timeout_close_enough"
        )
        return True

    monkeypatch.setattr(
        policy,
        "_pre_dig_align_timeout_can_handoff",
        timeout_can_handoff,
    )

    def reset_dig_policy() -> None:
        reset_calls.append("dig")

    policy.dig_policy.reset = reset_dig_policy  # type: ignore[method-assign]

    assert policy._try_replan_pre_dig_align_handoff(_obs())

    assert policy._skill_name == "dig"
    assert policy._switch_reason == "pre_dig_align_replan_to_dig_entry_close"
    assert reset_calls == ["dig"]
    assert policy._coverage_active_corridor_id == -1
    assert policy._pending_dig_cut_cycle_id == -1
    assert policy._pending_dig_cut_raw_fields is None
    np.testing.assert_allclose(policy._dig_cut_tokens, token)
    assert policy._dig_cut_token_source == "unit_replan"
    assert policy._dig_cut_fallback_reason == ""
    assert policy._dig_cut_token_in_prior_p10_p90 is True
    assert policy._pre_dig_align_step_count == 0
    assert policy._pre_dig_align_hold_count == 0
    assert policy._pre_dig_align_timeout_count == 7
    assert policy._pre_dig_align_completed_count == 7
    assert policy._pre_dig_align_replan_count == 6
    np.testing.assert_allclose(
        policy._pre_dig_align_target_qpos,
        np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
    )
    np.testing.assert_allclose(
        policy._pre_dig_align_error,
        np.asarray([0.01, -0.02, 0.03, -0.04], dtype=np.float32),
    )
    assert policy._pre_dig_align_entry_error_m == pytest.approx(0.12)
    assert policy._pre_dig_align_start_envelope_ready is False
    assert policy._pre_dig_align_entry_close_handoff_ready is True
    assert policy._pre_dig_align_entry_intent_handoff_ready is True
    assert (
        policy._pre_dig_align_timeout_handoff_reason
        == "pre_dig_align_to_dig_timeout_close_enough"
    )
    assert policy._pre_dig_align_surface_depth_m == pytest.approx(0.03)
    assert policy._pre_dig_align_surface_guard_triggered is True
    assert policy._pre_dig_align_surface_guard_count == 4
    assert policy._dig_step_count == 0
    assert policy._dig_best_mass_kg == 0.0
    assert policy._dig_mass_plateau_count == 0
    assert policy._dig_to_carry_reason == ""
    assert policy._coverage_current_payload_gain_kg == 0.0


def test_restart_pre_dig_align_applies_service_runtime_projection() -> None:
    policy = _make_policy()
    _set_active_corridor(policy, entry=(0.40, 0.80))
    policy._skill_name = "dig"
    policy._pre_dig_align_step_count = 9
    policy._pre_dig_align_hold_count = 8
    policy._pre_dig_align_timeout_count = 7
    policy._pre_dig_align_completed_count = 6
    policy._pre_dig_align_replan_count = 5
    policy._pre_dig_align_target_qpos = np.asarray(
        [0.1, 0.2, 0.3, 0.4],
        dtype=np.float32,
    )
    policy._pre_dig_align_error = np.asarray(
        [0.01, -0.02, 0.03, -0.04],
        dtype=np.float32,
    )
    policy._pre_dig_align_entry_error_m = 0.25
    policy._pre_dig_align_start_envelope_ready = True
    policy._pre_dig_align_entry_close_handoff_ready = True
    policy._pre_dig_align_entry_intent_handoff_ready = True
    policy._pre_dig_align_timeout_handoff_reason = (
        "pre_dig_align_to_dig_timeout_intent_aligned"
    )
    policy._pre_dig_align_surface_depth_m = 0.03
    policy._pre_dig_align_surface_guard_triggered = True
    policy._pre_dig_align_surface_guard_count = 4
    policy._dig_step_count = 11
    policy._dig_best_mass_kg = 22.0
    policy._dig_mass_plateau_count = 3
    policy._dig_to_carry_reason = "target_payload_loaded"
    policy._coverage_current_payload_gain_kg = 18.0
    policy._pending_dig_cut_cycle_id = 2
    policy._pending_dig_cut_raw_fields = {"operator_entry_x_m": 1.0}
    policy._dig_cut_tokens = np.ones(DIG_CUT_TOKEN_DIM, dtype=np.float32)

    policy._restart_pre_dig_align("unit_restart")

    assert policy._skill_name == "pre_dig_align"
    assert policy._switch_reason == "unit_restart"
    assert policy._pre_dig_align_step_count == 0
    assert policy._pre_dig_align_hold_count == 0
    assert policy._pre_dig_align_timeout_count == 7
    assert policy._pre_dig_align_completed_count == 6
    assert policy._pre_dig_align_replan_count == 6
    np.testing.assert_allclose(
        policy._pre_dig_align_target_qpos,
        np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
    )
    np.testing.assert_allclose(
        policy._pre_dig_align_error,
        np.asarray([0.01, -0.02, 0.03, -0.04], dtype=np.float32),
    )
    assert policy._pre_dig_align_entry_error_m == pytest.approx(0.25)
    assert policy._pre_dig_align_start_envelope_ready is True
    assert policy._pre_dig_align_entry_close_handoff_ready is True
    assert policy._pre_dig_align_entry_intent_handoff_ready is False
    assert policy._pre_dig_align_timeout_handoff_reason == ""
    assert policy._pre_dig_align_surface_depth_m == pytest.approx(0.03)
    assert policy._pre_dig_align_surface_guard_triggered is False
    assert policy._pre_dig_align_surface_guard_count == 4
    assert policy._dig_step_count == 0
    assert policy._dig_best_mass_kg == 0.0
    assert policy._dig_mass_plateau_count == 0
    assert policy._dig_to_carry_reason == ""
    assert policy._coverage_current_payload_gain_kg == 0.0
    assert policy._coverage_active_corridor_id == -1
    assert policy._return_next_dig_event_seen is False
    assert policy._pending_dig_cut_cycle_id == -1
    assert policy._pending_dig_cut_raw_fields is None
    assert float(np.max(np.abs(policy._dig_cut_tokens))) == pytest.approx(0.0)


def test_pre_dig_align_target_from_token_facade_uses_facts_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    obs = _obs()
    obs["qpos"] = np.asarray([[0.1, 0.2, 0.3, 0.4]], dtype=np.float64)
    token = np.linspace(0.0, 1.0, DIG_CUT_TOKEN_DIM, dtype=np.float64)

    def fail_entry_error(_obs: dict[str, np.ndarray]) -> float:
        raise AssertionError("target projection should not sample entry error")

    monkeypatch.setattr(policy, "_pre_dig_align_entry_error", fail_entry_error)
    expected = policy.dig_start_alignment_service.target_from_token_from_observation_view(
        view=policy._make_snapshot(obs).view,
        token=token,
        config=policy._dig_start_alignment_config(),
        entry_error_m=float("nan"),
        cycle_index=policy._cycle_index,
        hold_count=policy._pre_dig_align_hold_count,
    )

    target = policy._pre_dig_align_target_from_token(
        token=token,
        obs=obs,
        update_state=True,
    )

    np.testing.assert_allclose(target, expected)
    np.testing.assert_allclose(policy._pre_dig_align_target_qpos, expected)
    assert target.dtype == np.float32
    assert policy._pre_dig_align_target_qpos.dtype == np.float32


def test_bootstrap_facts_facade_matches_service_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy._scripted_bootstrap_step_count = 3
    policy._scripted_bootstrap_hold_count = 2
    policy.bootstrap_policy = _ConstantPolicy(4.0)
    obs = _obs(bucket_pose=(0.30, 0.0, 0.40), deposited_mass=12.5)
    obs["qpos"] = np.asarray([[1.0, 2.0, 3.0, 4.0]], dtype=np.float64)
    obs["qvel"] = np.asarray([[0.1, 0.2, 0.3, 0.4]], dtype=np.float64)
    boundary_event = type(
        "_BoundaryEvent",
        (),
        {"qualified_dig_start": True},
    )()

    snapshot = policy._make_snapshot(obs, boundary_event=boundary_event)
    expected = policy.bootstrap_service.facts_from_observation_view(
        view=snapshot.view,
        boundary_event=boundary_event,
        step_count=policy._scripted_bootstrap_step_count,
        hold_count=policy._scripted_bootstrap_hold_count,
        bootstrap_policy_present=True,
    )
    captured: dict[str, object] = {}

    def facts_from_observation_view(**kwargs: object) -> object:
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(
        policy.bootstrap_service,
        "facts_from_observation_view",
        facts_from_observation_view,
    )

    assert policy._bootstrap_facts(obs=obs, boundary_event=boundary_event) is expected
    assert captured["view"].obs is obs
    assert captured["boundary_event"] is boundary_event
    assert captured["step_count"] == 3
    assert captured["hold_count"] == 2
    assert captured["bootstrap_policy_present"] is True


def test_bootstrap_config_facade_uses_runtime_mapping_builder() -> None:
    policy = _make_policy()
    target_qpos = np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
    action_signs = np.asarray([1.0, -1.0, 1.0, -1.0], dtype=np.float32)
    action_clip = [0.1, 0.2, 0.3, 0.4]
    policy.bootstrap_end_mode = "scripted_qpos"
    policy.bootstrap_end_min_bucket_mass_kg = 12.5
    policy.bootstrap_end_min_distance_to_dig_area_m = 0.75
    policy.scripted_bootstrap_target_qpos = target_qpos
    policy.scripted_bootstrap_kp = 3.0
    policy.scripted_bootstrap_kd = 0.75
    policy.scripted_bootstrap_action_clip = action_clip
    policy.scripted_bootstrap_action_signs = action_signs
    policy.scripted_bootstrap_qpos_tolerance = 0.03
    policy.scripted_bootstrap_qvel_abs_max = 0.09
    policy.scripted_bootstrap_hold_steps = 0
    policy.scripted_bootstrap_max_steps = 0

    actual = policy._bootstrap_config()
    expected = build_bootstrap_config_from_mapping(
        {
            config_key: getattr(policy, attr_name)
            for config_key, attr_name in BOOTSTRAP_RUNTIME_CONFIG_FIELDS
        },
        action_dim=policy.action_dim,
    )

    assert actual.action_dim == expected.action_dim
    assert actual.end_mode == expected.end_mode
    assert actual.end_min_bucket_mass_kg == pytest.approx(
        expected.end_min_bucket_mass_kg
    )
    assert actual.end_min_distance_to_dig_area_m == pytest.approx(
        expected.end_min_distance_to_dig_area_m
    )
    np.testing.assert_array_equal(actual.scripted_target_qpos, target_qpos)
    assert actual.scripted_kp == pytest.approx(expected.scripted_kp)
    assert actual.scripted_kd == pytest.approx(expected.scripted_kd)
    assert actual.scripted_action_clip is action_clip
    np.testing.assert_array_equal(actual.scripted_action_signs, action_signs)
    assert actual.scripted_qpos_tolerance == pytest.approx(
        expected.scripted_qpos_tolerance
    )
    assert actual.scripted_qvel_abs_max == pytest.approx(
        expected.scripted_qvel_abs_max
    )
    assert actual.scripted_hold_steps == 0
    assert actual.scripted_max_steps == 0


def test_bootstrap_end_decision_apply_facade_updates_counters() -> None:
    policy = _make_policy()
    policy._scripted_bootstrap_hold_count = 1
    policy._scripted_bootstrap_timeout_count = 2

    should_end = policy._apply_bootstrap_end_decision(
        BootstrapEndDecision(
            should_end=True,
            hold_count=5,
            timeout_increment=True,
        )
    )

    assert should_end is True
    assert policy._scripted_bootstrap_hold_count == 5
    assert policy._scripted_bootstrap_timeout_count == 3


def test_bootstrap_target_decision_apply_facade_updates_hold_count() -> None:
    policy = _make_policy()
    policy._scripted_bootstrap_hold_count = 1

    ready = policy._apply_bootstrap_target_decision(
        BootstrapTargetDecision(
            ready=True,
            hold_count=4,
        )
    )

    assert ready is True
    assert policy._scripted_bootstrap_hold_count == 4


def test_should_end_bootstrap_delegates_decision_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    obs = _obs()
    decision = BootstrapEndDecision(
        should_end=True,
        hold_count=6,
        timeout_increment=True,
    )
    applied: list[BootstrapEndDecision] = []

    def should_end(facts: object, config: object) -> BootstrapEndDecision:
        return decision

    def apply_decision(state: BootstrapEndDecision) -> bool:
        applied.append(state)
        return bool(state.should_end)

    monkeypatch.setattr(policy.bootstrap_service, "should_end", should_end)
    monkeypatch.setattr(policy, "_apply_bootstrap_end_decision", apply_decision)

    assert policy._should_end_bootstrap(obs=obs, boundary_event=None) is True
    assert applied == [decision]


def test_scripted_bootstrap_target_reached_delegates_decision_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    obs = _obs()
    decision = BootstrapTargetDecision(
        ready=True,
        hold_count=7,
    )
    applied: list[BootstrapTargetDecision] = []

    def scripted_target_reached(
        facts: object,
        config: object,
    ) -> BootstrapTargetDecision:
        return decision

    def apply_decision(state: BootstrapTargetDecision) -> bool:
        applied.append(state)
        return bool(state.ready)

    monkeypatch.setattr(
        policy.bootstrap_service,
        "scripted_target_reached",
        scripted_target_reached,
    )
    monkeypatch.setattr(policy, "_apply_bootstrap_target_decision", apply_decision)

    assert policy._scripted_bootstrap_target_reached(obs) is True
    assert applied == [decision]


def test_bootstrap_end_transition_facade_uses_service_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy._skill_name = "bootstrap"
    policy.bootstrap_end_mode = "first_qualified_dig_start"
    calls: list[
        tuple[
            BootstrapEndTransitionFacts,
            object,
            BootstrapTransitionConfig,
        ]
    ] = []

    def should_end_bootstrap(
        *,
        obs: dict,
        boundary_event: object | None,
    ) -> bool:
        return True

    def should_pre_dig_align_before_dig() -> bool:
        return True

    def end_transition(
        facts: BootstrapEndTransitionFacts,
        config: object,
        transition_config: BootstrapTransitionConfig,
    ) -> BootstrapTransitionDecision:
        calls.append((facts, config, transition_config))
        return BootstrapTransitionDecision(
            next_skill="dig",
            switch_reason="bootstrap_to_dig",
        )

    monkeypatch.setattr(policy, "_should_end_bootstrap", should_end_bootstrap)
    monkeypatch.setattr(
        policy,
        "_should_pre_dig_align_before_dig",
        should_pre_dig_align_before_dig,
    )
    monkeypatch.setattr(policy.bootstrap_service, "end_transition", end_transition)

    policy._maybe_switch_skill(obs=_obs(), boundary_event=None)

    assert len(calls) == 1
    facts, config, transition_config = calls[0]
    assert facts.pre_dig_align_before_dig is True
    assert getattr(config, "end_mode") == "first_qualified_dig_start"
    assert transition_config.pre_dig_align_skill_name == "pre_dig_align"
    assert policy._skill_name == "dig"
    assert policy._switch_reason == "bootstrap_to_dig"


def test_bootstrap_end_transition_facade_delegates_decision_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy._skill_name = "bootstrap"
    policy.bootstrap_end_mode = "first_qualified_dig_start"
    decision = BootstrapTransitionDecision(
        next_skill="dig",
        switch_reason="bootstrap_to_dig",
    )
    applied: list[BootstrapTransitionDecision] = []

    monkeypatch.setattr(
        policy,
        "_should_end_bootstrap",
        lambda *, obs, boundary_event: True,
    )
    monkeypatch.setattr(
        policy,
        "_should_pre_dig_align_before_dig",
        lambda: False,
    )
    monkeypatch.setattr(
        policy.bootstrap_service,
        "end_transition",
        lambda facts, config, transition_config: decision,
    )
    monkeypatch.setattr(
        policy,
        "_apply_bootstrap_transition_decision",
        lambda state: applied.append(state),
    )

    policy._maybe_switch_skill(obs=_obs(), boundary_event=None)

    assert applied == [decision]


def test_bootstrap_transition_decision_apply_facade_delegates_skill_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy._skill_name = "bootstrap"
    calls: list[tuple[str, str]] = []

    def set_skill(skill_name: str, reason: str) -> None:
        calls.append((skill_name, reason))

    monkeypatch.setattr(policy, "_set_skill", set_skill)

    decision = BootstrapTransitionDecision(
        next_skill="pre_dig_align",
        switch_reason="bootstrap_to_pre_dig_align",
    )
    policy._apply_bootstrap_transition_decision(decision)

    assert calls == [("pre_dig_align", "bootstrap_to_pre_dig_align")]


def test_return_to_dig_handoff_config_facade_uses_runtime_mapping_builder() -> None:
    policy = _make_policy()
    policy.return_to_dig_shallow_guard_enabled = 1
    policy.return_to_dig_max_bucket_mass_kg = "2.5"
    policy.return_to_dig_touch_tolerance_m = "0.15"
    policy.return_to_dig_min_depth_m = "0.03"
    policy.return_to_dig_max_depth_m = "0.18"
    policy.return_to_dig_max_entry_error_m = "0.55"
    policy.return_to_dig_start_envelope_gate_enabled = 1
    policy.return_to_dig_start_envelope_direct_handoff_enabled = 0

    actual = policy._return_to_dig_handoff_config()
    expected = build_return_to_dig_handoff_config_from_mapping(
        {
            config_key: getattr(policy, attr_name)
            for config_key, attr_name in RETURN_TO_DIG_HANDOFF_CONFIG_FIELDS
        }
    )

    assert actual == expected
    assert actual.shallow_guard_enabled == 1
    assert actual.max_bucket_mass_kg == "2.5"
    assert actual.touch_tolerance_m == "0.15"
    assert actual.min_depth_m == "0.03"
    assert actual.max_depth_m == "0.18"
    assert actual.max_entry_error_m == "0.55"
    assert actual.start_envelope_gate_enabled == 1
    assert actual.direct_handoff_enabled == 0


def test_return_handoff_context_prior_context_matches_return_envelope_helper() -> None:
    policy = _make_policy()
    _set_active_corridor(policy, entry=(0.40, 0.80), corridor_id=7, cell_id=4)
    token = np.zeros(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)
    token[RETURN_ENVELOPE_QPOS_VALID_IDX] = 1.0
    token[RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX] = 1.0
    lower = np.linspace(-0.5, 0.5, RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)
    upper = lower + 1.0
    policy.dig_cut_prior = {
        "return_start_envelope_cells": [
            {
                "cell_id": 4,
                "source_count": 2,
                "source_fraction": 0.5,
                "token_median": token,
                "token_p05": lower,
                "token_p95": upper,
            }
        ],
        "return_start_envelope_global": {"token_median": token + 2.0},
    }
    policy._return_start_envelope_tokens = token.copy()
    policy._pending_dig_cut_corridor_id = 7
    policy.return_to_dig_start_envelope_gate_enabled = True
    policy.return_start_envelope_use_cell_prior = True

    config = policy._current_return_start_envelope_config()
    expected = build_return_to_dig_handoff_context_from_runtime(
        entry_target=policy._return_to_dig_entry_target(),
        envelope_token=token,
        envelope_config=config,
        dig_cut_prior=policy.dig_cut_prior,
        pending_corridor_id=policy._pending_dig_cut_corridor_id,
        corridor_cell_id_resolver=policy._return_start_envelope_cell_id,
        use_prior_spatial_bounds=(
            policy._return_start_envelope_use_prior_spatial_bounds
        ),
        use_prior_qpos_bounds=policy._return_start_envelope_use_prior_qpos_bounds,
    )
    context = policy._return_to_dig_handoff_context(
        _obs(),
        ensure_return_target=False,
    )

    assert context.entry_target == expected.entry_target
    assert context.prior_mapping == expected.prior_mapping
    np.testing.assert_allclose(context.prior_lower, expected.prior_lower)
    np.testing.assert_allclose(context.prior_upper, expected.prior_upper)


def test_return_handoff_context_reuses_return_start_envelope_cell_id_facade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    token = np.zeros(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)
    token[RETURN_ENVELOPE_QPOS_VALID_IDX] = 1.0
    token[RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX] = 1.0
    lower = np.linspace(-0.5, 0.5, RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)
    upper = lower + 1.0
    policy.dig_cut_prior = {
        "return_start_envelope_cells": [
            {
                "cell_id": 42,
                "source_count": 3,
                "source_fraction": 0.75,
                "token_median": token,
                "token_p05": lower,
                "token_p95": upper,
            }
        ],
    }
    policy._return_start_envelope_tokens = token.copy()
    policy._pending_dig_cut_corridor_id = 7
    policy.return_to_dig_start_envelope_gate_enabled = True
    policy.return_start_envelope_use_cell_prior = True
    calls: list[int] = []

    def resolve_cell_id(corridor_id: int | None) -> int | None:
        assert corridor_id is not None
        calls.append(int(corridor_id))
        return 42

    monkeypatch.setattr(policy, "_return_start_envelope_cell_id", resolve_cell_id)

    context = policy._return_to_dig_handoff_context(
        _obs(),
        ensure_return_target=False,
    )

    assert calls == [7]
    assert context.prior_mapping is not None
    assert context.prior_mapping["cell_id"] == 42
    np.testing.assert_allclose(context.prior_lower, lower)
    np.testing.assert_allclose(context.prior_upper, upper)


def test_return_handoff_evaluation_applies_service_status_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy._return_next_dig_event_seen = True
    projection_calls: list[tuple[object, ReturnToDigHandoffStatusState]] = []
    applied_states: list[ReturnToDigHandoffStatusState] = []
    apply_runtime_state = policy._apply_return_to_dig_handoff_runtime_state

    def runtime_state_from_decision(
        decision: object,
        *,
        next_dig_event_seen: bool,
    ) -> ReturnToDigHandoffStatusState:
        assert next_dig_event_seen is True
        state = ReturnToDigHandoffStatusState(
            entry_error_m=1.25,
            entry_close=False,
            next_dig_event_seen=True,
            start_envelope_ready=False,
            start_envelope_error=2.5,
            start_envelope_checks={"projected": True},
        )
        projection_calls.append((decision, state))
        return state

    def apply_state(state: ReturnToDigHandoffStatusState) -> None:
        applied_states.append(state)
        apply_runtime_state(state)

    monkeypatch.setattr(
        policy.return_handoff_gate,
        "runtime_state_from_decision",
        runtime_state_from_decision,
    )
    monkeypatch.setattr(
        policy,
        "_apply_return_to_dig_handoff_runtime_state",
        apply_state,
    )

    decision = policy._evaluate_return_to_dig_handoff(
        _obs(),
        ensure_return_target=False,
    )

    assert len(projection_calls) == 1
    projected_decision, projected_state = projection_calls[0]
    assert projected_decision is decision
    assert applied_states == [projected_state]
    assert policy._return_to_dig_entry_error_m == pytest.approx(1.25)
    assert policy._return_to_dig_entry_close_state is False
    assert policy._return_next_dig_event_seen is True
    assert policy._return_to_dig_start_envelope_ready_state is False
    assert policy._return_to_dig_start_envelope_error == pytest.approx(2.5)
    assert policy._return_to_dig_start_envelope_checks == {"projected": True}


def test_return_start_envelope_config_facade_uses_domain_builder() -> None:
    policy = _make_policy()
    qpos_coefficients = np.arange(32, dtype=np.float64).reshape(4, 8)
    spatial_coefficients = np.arange(16, dtype=np.float64).reshape(2, 8)
    policy.return_start_envelope_use_cell_prior = 1
    policy.return_start_envelope_min_source_count = 0
    policy.return_start_envelope_min_source_fraction = "-0.5"
    policy.return_start_envelope_qpos_from_relocate_enabled = 1
    policy.return_start_envelope_qpos_from_relocate_coefficients = qpos_coefficients
    policy.return_start_envelope_qpos_from_relocate_min = [
        "0.1",
        "0.2",
        "0.3",
        "0.4",
    ]
    policy.return_start_envelope_qpos_from_relocate_max = [
        "0.5",
        "0.6",
        "0.7",
        "0.8",
    ]
    policy.return_start_envelope_qpos_from_relocate_use_prior_qpos_bounds = 1
    policy.return_start_envelope_spatial_from_relocate_enabled = 1
    policy.return_start_envelope_spatial_from_relocate_coefficients = (
        spatial_coefficients
    )
    policy.return_start_envelope_spatial_from_relocate_min = ["-0.2", "-0.1"]
    policy.return_start_envelope_spatial_from_relocate_max = ["0.9", "1.1"]
    policy.return_start_envelope_spatial_from_relocate_use_prior_spatial_bounds = 1
    policy.return_to_dig_start_envelope_gate_enabled = 1
    policy.return_to_dig_start_envelope_spatial_tolerance = "0.12"
    policy.return_to_dig_start_envelope_depth_tolerance_m = "0.07"
    policy.return_to_dig_start_envelope_local_depth_tolerance_m = "0.006"
    policy.return_to_dig_start_envelope_plane_depth_tolerance_m = "0.03"
    policy.return_to_dig_start_envelope_plane_depth_mode = "target_band"
    policy.return_to_dig_start_envelope_qpos_tolerance = "0.05"
    policy.return_to_dig_start_envelope_require_contact = 0

    expected = build_return_start_envelope_config_from_mapping(
        {
            config_key: getattr(policy, attr_name)
            for config_key, attr_name in (
                RETURN_START_ENVELOPE_RUNTIME_CONFIG_FIELDS
            )
        }
    )
    actual = policy._current_return_start_envelope_config()

    assert actual.use_cell_prior is expected.use_cell_prior
    assert actual.min_source_count == expected.min_source_count
    assert actual.min_source_fraction == pytest.approx(expected.min_source_fraction)
    assert actual.qpos_from_relocate_enabled is expected.qpos_from_relocate_enabled
    np.testing.assert_allclose(
        actual.qpos_from_relocate_coefficients,
        expected.qpos_from_relocate_coefficients,
    )
    np.testing.assert_allclose(
        actual.qpos_from_relocate_min,
        expected.qpos_from_relocate_min,
    )
    np.testing.assert_allclose(
        actual.qpos_from_relocate_max,
        expected.qpos_from_relocate_max,
    )
    assert (
        actual.qpos_from_relocate_use_prior_qpos_bounds
        is expected.qpos_from_relocate_use_prior_qpos_bounds
    )
    assert (
        actual.spatial_from_relocate_enabled
        is expected.spatial_from_relocate_enabled
    )
    np.testing.assert_allclose(
        actual.spatial_from_relocate_coefficients,
        expected.spatial_from_relocate_coefficients,
    )
    np.testing.assert_allclose(
        actual.spatial_from_relocate_min,
        expected.spatial_from_relocate_min,
    )
    np.testing.assert_allclose(
        actual.spatial_from_relocate_max,
        expected.spatial_from_relocate_max,
    )
    assert (
        actual.spatial_from_relocate_use_prior_spatial_bounds
        is expected.spatial_from_relocate_use_prior_spatial_bounds
    )
    assert actual.gate_enabled is expected.gate_enabled
    assert actual.spatial_tolerance == pytest.approx(expected.spatial_tolerance)
    assert actual.depth_tolerance_m == pytest.approx(expected.depth_tolerance_m)
    assert actual.local_depth_tolerance_m == pytest.approx(
        expected.local_depth_tolerance_m
    )
    assert actual.plane_depth_tolerance_m == pytest.approx(
        expected.plane_depth_tolerance_m
    )
    assert actual.plane_depth_mode == expected.plane_depth_mode
    assert actual.qpos_tolerance == pytest.approx(expected.qpos_tolerance)
    assert actual.require_contact is expected.require_contact


def test_return_start_envelope_cell_id_facade_falls_back_to_corridor_id() -> None:
    policy = _make_policy()
    _set_active_corridor(policy, entry=(0.40, 0.80), corridor_id=7, cell_id=4)

    assert policy._return_start_envelope_cell_id(7) == 4
    assert policy._return_start_envelope_cell_id(8) == 8
    assert policy._return_start_envelope_cell_id(-1) is None


def test_return_start_envelope_corridor_cell_id_compatibility_helper_has_no_id_fallback() -> None:
    policy = _make_policy()
    _set_active_corridor(policy, entry=(0.40, 0.80), corridor_id=7, cell_id=4)

    assert policy._return_start_envelope_corridor_cell_id(7) == 4
    assert policy._return_start_envelope_corridor_cell_id(8) is None
    assert policy._return_start_envelope_corridor_cell_id(-1) is None


def test_return_start_envelope_build_facade_matches_request_builder() -> None:
    policy = _make_policy()
    _set_active_corridor(policy, entry=(0.40, 0.80), corridor_id=7, cell_id=4)
    obs = _obs(bucket_pose=(0.25, 0.0, 0.40))
    obs["qpos"] = np.asarray([[0.51, 0.62, 0.22, 0.18]], dtype=np.float64)
    obs["qvel"] = np.asarray([[-0.1, 0.3, -0.2, 0.05]], dtype=np.float64)
    raw_fields = {"operator_cut_depth_peak_m": 0.12}
    expected_request = build_return_start_envelope_request_from_observation_view(
        policy._make_snapshot(obs).view,
        raw_fields=raw_fields,
        dig_cut_prior=policy.dig_cut_prior,
        config=policy._current_return_start_envelope_config(),
        cell_id=policy._return_start_envelope_cell_id(7),
    )
    request = policy._return_start_envelope_build_request(
        obs,
        raw_fields,
        corridor_id=7,
    )

    np.testing.assert_allclose(request.env_state, expected_request.env_state)
    assert request.qpos is expected_request.qpos
    assert request.qvel is expected_request.qvel
    assert request.raw_fields is expected_request.raw_fields
    assert request.action_dim == expected_request.action_dim
    assert request.dig_cut_prior is expected_request.dig_cut_prior
    for key, expected_value in expected_request.config.__dict__.items():
        actual_value = getattr(request.config, key)
        if isinstance(expected_value, np.ndarray):
            np.testing.assert_allclose(actual_value, expected_value)
        else:
            assert actual_value == expected_value
    assert request.cell_id == expected_request.cell_id

    expected_state = build_return_start_envelope_for_plan(expected_request)
    token = policy._build_return_start_envelope_tokens_for_obs(
        obs,
        raw_fields,
        corridor_id=7,
    )

    assert expected_state.token is not None
    np.testing.assert_allclose(token, expected_state.token)
    assert token.dtype == np.float32
    assert policy._return_start_envelope_token_source == expected_state.source
    assert policy._return_start_envelope_use_prior_spatial_bounds is (
        expected_state.use_prior_spatial_bounds
    )
    assert policy._return_start_envelope_use_prior_qpos_bounds is (
        expected_state.use_prior_qpos_bounds
    )


def test_ensure_dig_cut_plan_for_cycle_applies_cycle_state_after_depth_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy.dig_cut_planner_enabled = True
    policy.dig_cut_hold_token_until_skill_exit = False
    policy._cycle_index = 5
    dig_cut_tokens = np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float64)
    depth_profile_tokens = np.arange(
        DIG_DEPTH_PROFILE_TOKEN_DIM,
        dtype=np.float64,
    )
    events: list[str] = []
    apply_cycle_state = policy._apply_dig_cut_plan_cycle_state

    def build_dig_cut(_obs: dict[str, np.ndarray]) -> np.ndarray:
        events.append("dig_cut")
        return dig_cut_tokens

    def build_depth(_obs: dict[str, np.ndarray]) -> np.ndarray:
        events.append("depth")
        assert policy._dig_cut_tokens is dig_cut_tokens
        return depth_profile_tokens

    def apply_state(state: DigCutPlanCycleApplyState) -> None:
        events.append("apply")
        assert state.dig_cut_tokens is dig_cut_tokens
        assert state.dig_depth_profile_tokens is depth_profile_tokens
        assert state.planned_cycle_id == 5
        apply_cycle_state(state)

    monkeypatch.setattr(policy, "_build_dig_cut_tokens_for_obs", build_dig_cut)
    monkeypatch.setattr(
        policy,
        "_build_dig_depth_profile_tokens_for_obs",
        build_depth,
    )
    monkeypatch.setattr(policy, "_apply_dig_cut_plan_cycle_state", apply_state)

    policy._ensure_dig_cut_plan_for_cycle(_obs())

    assert events == ["dig_cut", "depth", "apply"]
    assert policy._dig_cut_tokens is dig_cut_tokens
    assert policy._dig_depth_profile_tokens is depth_profile_tokens
    assert policy._dig_cut_planned_cycle_id == 5


def test_ensure_return_target_plan_holds_existing_cycle_without_rebuild() -> None:
    policy = _make_policy()
    policy.return_target_planner_enabled = True
    policy.return_target_hold_token_until_skill_exit = True
    policy._cycle_index = 3
    policy._return_target_planned_cycle_id = 3
    original_tokens = policy._return_target_tokens.copy()

    def fail_build(_obs: dict[str, np.ndarray]) -> tuple[np.ndarray, dict, str, str, int]:
        raise AssertionError("return target plan should be held")

    policy._build_next_dig_cut_plan_for_return = fail_build  # type: ignore[method-assign]

    policy._ensure_return_target_plan_for_cycle(_obs())

    np.testing.assert_allclose(policy._return_target_tokens, original_tokens)
    assert policy._return_target_planned_cycle_id == 3


def test_ensure_return_target_plan_success_path_writes_pending_state() -> None:
    policy = _make_policy()
    policy.return_target_planner_enabled = True
    policy._cycle_index = 2
    token = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32)
    envelope = np.arange(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)
    raw_fields = {"operator_entry_x_m": 0.5, "operator_cut_valid": 1}
    depth_profile = np.arange(12, dtype=np.float32)
    policy._coverage_active_state_exemplar_profile_token = depth_profile.copy()
    policy._coverage_active_state_exemplar_ids = ["cell7_deep"]
    policy._coverage_active_state_exemplar_distance = 0.25
    policy._return_start_envelope_token_source = "qc6_return_start_envelope_cell_1"

    def build_plan(
        _obs: dict[str, np.ndarray],
    ) -> tuple[np.ndarray, dict[str, float | int], str, str, int]:
        return token, raw_fields, "return_target_operator_prior", "", 7

    def build_envelope(
        _obs: dict[str, np.ndarray],
        fields: dict[str, float | int],
        *,
        corridor_id: int | None = None,
    ) -> np.ndarray:
        assert fields == raw_fields
        assert corridor_id == 7
        return envelope

    policy._build_next_dig_cut_plan_for_return = build_plan  # type: ignore[method-assign]
    policy._build_return_start_envelope_tokens_for_obs = build_envelope  # type: ignore[method-assign]

    policy._ensure_return_target_plan_for_cycle(_obs())

    np.testing.assert_allclose(policy._return_target_tokens, token)
    np.testing.assert_allclose(policy._return_start_envelope_tokens, envelope)
    assert policy._return_target_token_source == "return_target_operator_prior"
    assert policy._return_start_envelope_token_source == (
        "qc6_return_start_envelope_cell_1"
    )
    assert policy._return_target_fallback_reason == ""
    assert policy._return_target_planned_cycle_id == 2
    assert policy._pending_dig_cut_cycle_id == 3
    assert policy._pending_dig_cut_corridor_id == 7
    assert policy._pending_dig_cut_raw_fields == raw_fields
    np.testing.assert_allclose(policy._pending_dig_cut_tokens, token)
    np.testing.assert_allclose(policy._pending_dig_depth_profile_tokens, depth_profile)
    assert policy._pending_dig_state_exemplar_ids == ["cell7_deep"]
    assert policy._pending_dig_state_exemplar_distance == pytest.approx(0.25)


def test_apply_return_target_plan_state_uses_service_runtime_update() -> None:
    policy = _make_policy()
    policy._return_start_envelope_token_source = "existing_envelope_source"
    target_tokens = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32)
    envelope_tokens = np.arange(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)
    pending_tokens = target_tokens + 10.0
    state = ReturnTargetPlanState(
        return_target_tokens=target_tokens,
        return_start_envelope_tokens=envelope_tokens,
        return_target_token_source="ignored",
        return_target_fallback_reason="ignored",
        return_target_planned_cycle_id=2,
        pending_dig_cut_cycle_id=3,
        pending_dig_cut_raw_fields={"operator_entry_x_m": 0.5},
        pending_dig_cut_tokens=pending_tokens,
        pending_dig_cut_corridor_id=7,
        pending_dig_depth_profile_tokens=None,
        pending_dig_state_exemplar_ids=("cell7_deep",),
        pending_dig_state_exemplar_distance=0.25,
    )
    update = ReturnTargetPlanRuntimeUpdate(
        return_target_tokens=target_tokens + 20.0,
        return_start_envelope_tokens=envelope_tokens + 30.0,
        return_target_token_source="projected_return_target",
        return_start_envelope_token_source=None,
        return_target_fallback_reason="projected_reason",
        return_target_planned_cycle_id=9,
        pending_plan=PendingDigCutPlanState(
            cycle_id=10,
            corridor_id=11,
            raw_fields={"operator_entry_x_m": 1.5},
            tokens=pending_tokens + 40.0,
            depth_profile_tokens=np.arange(12, dtype=np.float32),
            state_exemplar_ids=("projected_cell",),
            state_exemplar_distance=0.75,
        ),
    )
    calls: list[ReturnTargetPlanState] = []

    def runtime_update_from_plan_state(
        plan_state: ReturnTargetPlanState,
    ) -> ReturnTargetPlanRuntimeUpdate:
        calls.append(plan_state)
        return update

    policy.return_target_plan_service.runtime_update_from_plan_state = (  # type: ignore[method-assign]
        runtime_update_from_plan_state
    )

    policy._apply_return_target_plan_state(state)

    assert calls == [state]
    np.testing.assert_allclose(policy._return_target_tokens, update.return_target_tokens)
    np.testing.assert_allclose(
        policy._return_start_envelope_tokens,
        update.return_start_envelope_tokens,
    )
    assert policy._return_target_token_source == "projected_return_target"
    assert policy._return_start_envelope_token_source == "existing_envelope_source"
    assert policy._return_target_fallback_reason == "projected_reason"
    assert policy._return_target_planned_cycle_id == 9
    assert policy._pending_dig_cut_cycle_id == 10
    assert policy._pending_dig_cut_corridor_id == 11
    assert policy._pending_dig_cut_raw_fields == {"operator_entry_x_m": 1.5}
    np.testing.assert_allclose(
        policy._pending_dig_cut_tokens,
        update.pending_plan.tokens,
    )
    np.testing.assert_allclose(
        policy._pending_dig_depth_profile_tokens,
        update.pending_plan.depth_profile_tokens,
    )
    assert policy._pending_dig_state_exemplar_ids == ["projected_cell"]
    assert policy._pending_dig_state_exemplar_distance == pytest.approx(0.75)


def test_ensure_return_target_plan_delegates_build_attempt_finalization() -> None:
    policy = _make_policy()
    policy.return_target_planner_enabled = True
    policy._cycle_index = 2
    token = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32)
    envelope = np.arange(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)
    raw_fields = {"operator_entry_x_m": 0.5, "operator_cut_valid": 1}
    delegated_state = ReturnTargetPlanState(
        return_target_tokens=token + 10.0,
        return_start_envelope_tokens=envelope + 20.0,
        return_target_token_source="delegated_return_target",
        return_target_fallback_reason="",
        return_target_planned_cycle_id=9,
        pending_dig_cut_cycle_id=10,
        pending_dig_cut_raw_fields=raw_fields,
        pending_dig_cut_tokens=token + 30.0,
        pending_dig_cut_corridor_id=7,
        pending_dig_depth_profile_tokens=np.arange(12, dtype=np.float32),
        pending_dig_state_exemplar_ids=("cell7_deep",),
        pending_dig_state_exemplar_distance=0.25,
    )
    calls: list[ReturnTargetPlanBuildAttemptFacts] = []
    build_fact_calls: list[dict[str, object]] = []
    original_build_facts = policy.return_target_plan_service.plan_build_facts_from_parts

    def build_plan(
        _obs: dict[str, np.ndarray],
    ) -> tuple[np.ndarray, dict[str, float | int], str, str, int]:
        return token, raw_fields, "return_target_operator_prior", "", 7

    def build_envelope(
        _obs: dict[str, np.ndarray],
        fields: dict[str, float | int],
        *,
        corridor_id: int | None = None,
    ) -> np.ndarray:
        assert fields is raw_fields
        assert corridor_id == 7
        return envelope

    def state_from_build_attempt(
        facts: ReturnTargetPlanBuildAttemptFacts,
    ) -> ReturnTargetPlanState:
        calls.append(facts)
        return delegated_state

    def plan_build_facts_from_parts(**kwargs: object) -> ReturnTargetPlanBuildFacts:
        build_fact_calls.append(kwargs)
        return original_build_facts(**kwargs)

    policy._build_next_dig_cut_plan_for_return = build_plan  # type: ignore[method-assign]
    policy._build_return_start_envelope_tokens_for_obs = build_envelope  # type: ignore[method-assign]
    policy.return_target_plan_service.plan_build_facts_from_parts = (  # type: ignore[method-assign]
        plan_build_facts_from_parts
    )
    policy.return_target_plan_service.state_from_build_attempt = (  # type: ignore[method-assign]
        state_from_build_attempt
    )

    policy._ensure_return_target_plan_for_cycle(_obs())

    assert len(build_fact_calls) == 1
    assert build_fact_calls[0]["token"] is token
    assert build_fact_calls[0]["raw_fields"] is raw_fields
    assert build_fact_calls[0]["return_start_envelope_tokens"] is envelope
    assert build_fact_calls[0]["source"] == "return_target_operator_prior"
    assert build_fact_calls[0]["fallback_reason"] == ""
    assert build_fact_calls[0]["corridor_id"] == 7
    assert len(calls) == 1
    attempt_facts = calls[0]
    assert attempt_facts.request.cycle_index == 2
    assert attempt_facts.build_facts is not None
    assert attempt_facts.build_facts.token is token
    assert attempt_facts.build_facts.raw_fields is raw_fields
    assert attempt_facts.build_facts.return_start_envelope_tokens is envelope
    assert attempt_facts.build_facts.source == "return_target_operator_prior"
    assert attempt_facts.build_facts.fallback_reason == ""
    assert attempt_facts.build_facts.corridor_id == 7
    assert attempt_facts.failure_reason is None
    assert policy._return_target_token_source == "delegated_return_target"
    assert policy._return_target_planned_cycle_id == 9
    assert policy._pending_dig_cut_cycle_id == 10


def test_build_dig_cut_tokens_consumes_pending_return_target_state() -> None:
    policy = _make_policy()
    activation_service = _SpyPendingActivationService()
    policy.return_target_plan_service = activation_service  # type: ignore[assignment]
    policy._cycle_index = 4
    policy.dig_cut_planner_mode = "unsupported_mode"
    token = np.linspace(0.0, 1.0, RETURN_TARGET_TOKEN_DIM, dtype=np.float64)
    raw_fields = {"operator_entry_x_m": 0.5, "operator_cut_valid": 1}
    profile_token = np.arange(12, dtype=np.float64)
    policy._pending_dig_cut_cycle_id = 4
    policy._pending_dig_cut_corridor_id = 7
    policy._pending_dig_cut_raw_fields = raw_fields
    policy._pending_dig_cut_tokens = token
    policy._pending_dig_depth_profile_tokens = profile_token
    policy._pending_dig_state_exemplar_ids = ["cell7_deep"]
    policy._pending_dig_state_exemplar_distance = 0.25

    def raw_fields_in_prior_range(fields: dict[str, float | int]) -> bool:
        assert fields == raw_fields
        return True

    policy._raw_fields_in_prior_range = raw_fields_in_prior_range  # type: ignore[method-assign]

    result = policy._build_dig_cut_tokens_for_obs(_obs(deposited_mass=12.5))

    assert len(activation_service.calls) == 1
    facts = activation_service.calls[0]
    assert facts.pending_dig_cut_tokens is token
    assert facts.pending_dig_cut_raw_fields is raw_fields
    assert facts.pending_dig_cut_corridor_id == 7
    assert facts.pending_dig_depth_profile_tokens is profile_token
    assert facts.pending_dig_state_exemplar_ids == ["cell7_deep"]
    assert facts.pending_dig_state_exemplar_distance == pytest.approx(0.25)
    assert facts.raw_fields_in_prior_range is True
    assert facts.cycle_start_deposit_kg == pytest.approx(12.5)
    np.testing.assert_allclose(result, token)
    assert result.dtype == np.float32
    assert policy._dig_cut_token_source == "pending_return_target"
    assert policy._dig_cut_fallback_reason == ""
    assert policy._dig_cut_token_in_prior_p10_p90
    assert policy._coverage_active_corridor_id == 7
    assert policy._coverage_last_selected_corridor_id == 7
    assert policy._coverage_current_payload_gain_kg == pytest.approx(0.0)
    assert policy._coverage_cycle_start_deposit_kg == pytest.approx(12.5)
    assert policy._coverage_active_state_exemplar_ids == ["cell7_deep"]
    assert policy._coverage_active_state_exemplar_distance == pytest.approx(0.25)
    np.testing.assert_allclose(
        policy._coverage_active_state_exemplar_profile_token,
        profile_token,
    )
    assert policy._coverage_active_state_exemplar_profile_token.dtype == np.float32


def test_stale_pending_return_target_does_not_call_activation_service() -> None:
    policy = _make_policy()
    policy._cycle_index = 4
    policy.dig_cut_planner_mode = "conservative_pose"
    policy._pending_dig_cut_cycle_id = 3
    policy._pending_dig_cut_tokens = np.ones(RETURN_TARGET_TOKEN_DIM, dtype=np.float32)
    policy.return_target_plan_service = _FailingPendingActivationService()

    result = policy._build_dig_cut_tokens_for_obs(_obs())

    assert result.shape == (RETURN_TARGET_TOKEN_DIM,)
    assert policy._dig_cut_token_source == "conservative_pose"


@pytest.mark.parametrize(
    ("mode", "builder_name"),
    [
        ("operator_prior", "_build_operator_prior_dig_cut_tokens"),
        ("operator_prior_coverage", "_build_operator_prior_coverage_dig_cut_tokens"),
        (
            "operator_prior_sweep_belief",
            "_build_operator_prior_coverage_dig_cut_tokens",
        ),
    ],
)
def test_build_dig_cut_tokens_mode_writes_plan_state(
    mode: str,
    builder_name: str,
) -> None:
    policy = _make_policy()
    policy.dig_cut_planner_mode = mode
    token = np.linspace(0.0, 1.0, DIG_CUT_TOKEN_DIM, dtype=np.float64)
    raw_fields = {"operator_entry_x_m": 0.5, "operator_cut_valid": 1}

    def build_plan(
        _obs: dict[str, np.ndarray],
    ) -> tuple[np.ndarray, dict[str, float | int], str, str]:
        return token, raw_fields, "operator_prior_pose_clamped", ""

    def raw_fields_in_prior_range(fields: dict[str, float | int]) -> bool:
        assert fields == raw_fields
        return True

    setattr(policy, builder_name, build_plan)
    policy._raw_fields_in_prior_range = raw_fields_in_prior_range  # type: ignore[method-assign]

    result = policy._build_dig_cut_tokens_for_obs(_obs())

    np.testing.assert_allclose(result, token)
    assert result.dtype == np.float32
    assert policy._dig_cut_token_source == "operator_prior_pose_clamped"
    assert policy._dig_cut_fallback_reason == ""
    assert policy._dig_cut_token_in_prior_p10_p90


def test_dig_cut_plan_state_from_builder_delegates_attempt_resolution() -> None:
    policy = _make_policy()
    token = np.linspace(0.0, 1.0, DIG_CUT_TOKEN_DIM, dtype=np.float64)
    raw_fields = {"operator_entry_x_m": 0.5, "operator_cut_valid": 1}
    expected_state = DigCutPlanState(
        token=np.asarray(token, dtype=np.float32),
        source="operator_prior_pose_clamped",
        fallback_reason="",
        token_in_prior_p10_p90=True,
    )
    calls: list[tuple[dict[str, float | int], str]] = []

    def build_plan(
        _obs: dict[str, np.ndarray],
    ) -> tuple[np.ndarray, dict[str, float | int], str, str]:
        return token, raw_fields, "operator_prior_pose_clamped", ""

    def raw_fields_in_prior_range(fields: dict[str, float | int]) -> bool:
        assert fields is raw_fields
        return True

    def state_from_builder_attempt(
        *,
        build_plan: object,
        raw_fields_in_prior_range: object,
        fallback_mode: str,
        fallback_plan: object,
    ) -> DigCutPlanState:
        built_token, built_raw_fields, source, fallback_reason = build_plan()
        assert built_token is token
        assert built_raw_fields is raw_fields
        assert source == "operator_prior_pose_clamped"
        assert fallback_reason == ""
        assert raw_fields_in_prior_range(built_raw_fields) is True
        assert callable(fallback_plan)
        calls.append((built_raw_fields, fallback_mode))
        return expected_state

    policy._raw_fields_in_prior_range = raw_fields_in_prior_range  # type: ignore[method-assign]
    policy.dig_cut_plan_service.state_from_builder_attempt = (  # type: ignore[method-assign]
        state_from_builder_attempt
    )

    state = policy._dig_cut_plan_state_from_builder(_obs(), build_plan)

    assert state is expected_state
    assert calls == [(raw_fields, policy.dig_cut_planner_fallback_mode)]


@pytest.mark.parametrize(
    ("mode", "builder_name"),
    [
        ("operator_prior", "_build_operator_prior_dig_cut_tokens"),
        ("operator_prior_coverage", "_build_operator_prior_coverage_dig_cut_tokens"),
        (
            "operator_prior_sweep_belief",
            "_build_operator_prior_coverage_dig_cut_tokens",
        ),
    ],
)
def test_build_dig_cut_tokens_mode_falls_back_to_conservative_pose(
    mode: str,
    builder_name: str,
) -> None:
    policy = _make_policy()
    policy.dig_cut_planner_mode = mode
    policy.dig_cut_planner_fallback_mode = "conservative_pose"

    def fail_build(
        _obs: dict[str, np.ndarray],
    ) -> tuple[np.ndarray, dict[str, float | int], str, str]:
        raise RuntimeError("missing prior")

    setattr(policy, builder_name, fail_build)

    result = policy._build_dig_cut_tokens_for_obs(
        _obs(bucket_pose=(0.8, 0.0, -0.3))
    )

    assert result.shape == (DIG_CUT_TOKEN_DIM,)
    assert result.dtype == np.float32
    assert policy._dig_cut_token_source == "fallback_conservative_pose"
    assert policy._dig_cut_fallback_reason == "missing prior"
    assert not policy._dig_cut_token_in_prior_p10_p90


@pytest.mark.parametrize(
    ("mode", "builder_name"),
    [
        ("operator_prior", "_build_operator_prior_dig_cut_tokens"),
        ("operator_prior_coverage", "_build_operator_prior_coverage_dig_cut_tokens"),
        (
            "operator_prior_sweep_belief",
            "_build_operator_prior_coverage_dig_cut_tokens",
        ),
    ],
)
def test_build_dig_cut_tokens_mode_reraises_without_fallback(
    mode: str,
    builder_name: str,
) -> None:
    policy = _make_policy()
    policy.dig_cut_planner_mode = mode
    policy.dig_cut_planner_fallback_mode = "raise"

    def fail_build(
        _obs: dict[str, np.ndarray],
    ) -> tuple[np.ndarray, dict[str, float | int], str, str]:
        raise RuntimeError("missing prior")

    setattr(policy, builder_name, fail_build)

    with pytest.raises(RuntimeError, match="missing prior"):
        policy._build_dig_cut_tokens_for_obs(_obs())


def test_ensure_return_target_plan_failure_path_writes_fallback_zero() -> None:
    policy = _make_policy()
    policy.return_target_planner_enabled = True
    policy._cycle_index = 2

    def fail_build(_obs: dict[str, np.ndarray]) -> tuple[np.ndarray, dict, str, str, int]:
        raise RuntimeError("missing plan")

    policy._build_next_dig_cut_plan_for_return = fail_build  # type: ignore[method-assign]

    policy._ensure_return_target_plan_for_cycle(_obs())

    assert policy._return_target_token_source == "fallback_zero"
    assert policy._return_start_envelope_token_source == "fallback_zero"
    assert policy._return_target_fallback_reason == "missing plan"
    assert policy._return_target_planned_cycle_id == 2
    assert float(np.max(np.abs(policy._return_target_tokens))) == pytest.approx(0.0)
    assert float(np.max(np.abs(policy._return_start_envelope_tokens))) == pytest.approx(
        0.0
    )
    assert policy._pending_dig_cut_cycle_id == -1
    assert policy._pending_dig_cut_raw_fields is None
    assert policy._pending_dig_cut_tokens is None
    assert policy._pending_dig_cut_corridor_id == -1
    assert policy._pending_dig_depth_profile_tokens is None
    assert policy._pending_dig_state_exemplar_ids == []
    assert np.isnan(policy._pending_dig_state_exemplar_distance)


def test_dig_exit_guard_transition_does_not_call_later_gates() -> None:
    policy = _make_policy()
    policy._skill_name = "dig"
    calls: list[str] = []
    rejected: list[str] = []
    restarted: list[str] = []

    def exit_guard_ready(_obs: dict[str, np.ndarray]) -> bool:
        calls.append("exit_guard")
        return True

    def fail_bad_replan(_obs: dict[str, np.ndarray]) -> bool:
        raise AssertionError("bad_replan must not be checked after exit guard")

    def fail_complete_low(
        _obs: dict[str, np.ndarray],
        _boundary_event: Any | None,
    ) -> bool:
        raise AssertionError("complete_low must not be checked after exit guard")

    def fail_dig_to_carry(
        *,
        obs: dict[str, np.ndarray],
        boundary_event: Any | None,
    ) -> DigGateDecision:
        raise AssertionError("dig_to_carry must not be checked after exit guard")

    def reject_corridor(_obs: dict[str, np.ndarray], *, reason: str) -> None:
        assert policy._dig_exit_guard_replan_count == 1
        assert policy._dig_bad_replan_count == 0
        rejected.append(reason)

    def restart_after_failed_dig(reason: str, _obs: dict[str, np.ndarray]) -> None:
        assert policy._dig_exit_guard_replan_count == 1
        assert policy._dig_bad_replan_count == 0
        restarted.append(reason)

    policy._dig_exit_guard_ready = exit_guard_ready  # type: ignore[method-assign]
    policy._dig_bad_replan_ready = fail_bad_replan  # type: ignore[method-assign]
    policy._dig_complete_boundary_low_payload = fail_complete_low  # type: ignore[method-assign]
    policy._dig_to_carry_decision = fail_dig_to_carry  # type: ignore[method-assign]
    policy._reject_active_coverage_corridor = reject_corridor  # type: ignore[method-assign]
    policy._restart_after_failed_dig = restart_after_failed_dig  # type: ignore[method-assign]

    policy._maybe_switch_skill(obs=_obs(), boundary_event=None)

    assert calls == ["exit_guard"]
    assert policy._dig_exit_guard_replan_count == 1
    assert policy._dig_bad_replan_count == 0
    assert rejected == ["exit_overshoot_low_payload"]
    assert restarted == ["exit_overshoot_low_payload"]


def test_dig_complete_low_payload_preserves_reject_and_restart_reasons() -> None:
    policy = _make_policy()
    policy._skill_name = "dig"
    calls: list[str] = []
    rejected: list[str] = []
    restarted: list[str] = []

    def exit_guard_ready(_obs: dict[str, np.ndarray]) -> bool:
        calls.append("exit_guard")
        return False

    def bad_replan_ready(_obs: dict[str, np.ndarray]) -> bool:
        calls.append("bad_replan")
        return False

    def complete_low(
        _obs: dict[str, np.ndarray],
        _boundary_event: Any | None,
    ) -> bool:
        calls.append("complete_low")
        return True

    def fail_dig_to_carry(
        *,
        obs: dict[str, np.ndarray],
        boundary_event: Any | None,
    ) -> DigGateDecision:
        raise AssertionError("dig_to_carry must not be checked after complete_low")

    def reject_corridor(_obs: dict[str, np.ndarray], *, reason: str) -> None:
        assert policy._dig_exit_guard_replan_count == 0
        assert policy._dig_bad_replan_count == 1
        rejected.append(reason)

    def restart_after_failed_dig(reason: str, _obs: dict[str, np.ndarray]) -> None:
        assert policy._dig_exit_guard_replan_count == 0
        assert policy._dig_bad_replan_count == 1
        restarted.append(reason)

    policy._dig_exit_guard_ready = exit_guard_ready  # type: ignore[method-assign]
    policy._dig_bad_replan_ready = bad_replan_ready  # type: ignore[method-assign]
    policy._dig_complete_boundary_low_payload = complete_low  # type: ignore[method-assign]
    policy._dig_to_carry_decision = fail_dig_to_carry  # type: ignore[method-assign]
    policy._reject_active_coverage_corridor = reject_corridor  # type: ignore[method-assign]
    policy._restart_after_failed_dig = restart_after_failed_dig  # type: ignore[method-assign]

    policy._maybe_switch_skill(obs=_obs(), boundary_event=None)

    assert calls == ["exit_guard", "bad_replan", "complete_low"]
    assert policy._dig_exit_guard_replan_count == 0
    assert policy._dig_bad_replan_count == 1
    assert rejected == ["dig_complete_low_current_payload"]
    assert restarted == ["complete_low_payload"]


def test_dig_transition_runtime_projection_apply_facade_preserves_side_effect_order() -> None:
    policy = _make_policy()
    policy._skill_name = "dig"
    policy._switch_reason = "before"
    policy._dig_exit_guard_replan_count = 2
    policy._dig_bad_replan_count = 3
    events: list[tuple[str, str]] = []

    def reject_corridor(_obs: dict[str, np.ndarray], *, reason: str) -> None:
        assert policy._dig_exit_guard_replan_count == 3
        assert policy._dig_bad_replan_count == 3
        events.append(("reject", reason))

    def restart_after_failed_dig(reason: str, _obs: dict[str, np.ndarray]) -> None:
        assert policy._dig_exit_guard_replan_count == 3
        assert policy._dig_bad_replan_count == 3
        events.append(("restart", reason))

    policy._reject_active_coverage_corridor = reject_corridor  # type: ignore[method-assign]
    policy._restart_after_failed_dig = restart_after_failed_dig  # type: ignore[method-assign]

    projection = DigTransitionRuntimeProjection(
        outcome=DigTransitionRuntimeOutcome(
            action="failed_dig",
            counter="exit_guard_replan",
            failed_dig_reason="exit_overshoot_low_payload",
            coverage_reject_reason="exit_overshoot_low_payload",
        ),
        exit_guard_replan_count_increment=1,
        bad_replan_count_increment=0,
    )
    assert policy._apply_dig_transition_runtime_projection(projection, _obs()) is True

    assert policy._dig_exit_guard_replan_count == 3
    assert policy._dig_bad_replan_count == 3
    assert policy._skill_name == "dig"
    assert policy._switch_reason == "before"
    assert events == [
        ("reject", "exit_overshoot_low_payload"),
        ("restart", "exit_overshoot_low_payload"),
    ]

    wait = DigTransitionRuntimeProjection(
        outcome=DigTransitionRuntimeOutcome(action="none"),
    )
    assert policy._apply_dig_transition_runtime_projection(wait, _obs()) is False

    assert policy._dig_exit_guard_replan_count == 3
    assert policy._dig_bad_replan_count == 3
    assert policy._skill_name == "dig"
    assert policy._switch_reason == "before"
    assert events == [
        ("reject", "exit_overshoot_low_payload"),
        ("restart", "exit_overshoot_low_payload"),
    ]

    carry_policy = _make_policy()
    carry_events: list[tuple[str, str]] = []

    def complete_cell_entry(_obs: dict[str, np.ndarray]) -> None:
        carry_events.append(("complete_cell_entry", ""))

    def complete_coverage(_obs: dict[str, np.ndarray]) -> None:
        carry_events.append(("complete_coverage", ""))

    def set_skill(skill_name: str, reason: str) -> None:
        carry_events.append(("set_skill", f"{skill_name}:{reason}"))

    carry_policy._complete_cell_entry_dig = complete_cell_entry  # type: ignore[method-assign]
    carry_policy._complete_coverage_dig = complete_coverage  # type: ignore[method-assign]
    carry_policy._set_skill = set_skill  # type: ignore[method-assign]

    carry = DigTransitionRuntimeProjection(
        outcome=DigTransitionRuntimeOutcome(
            action="carry",
            switch_reason="dig_to_carry_target_payload_loaded",
        ),
    )

    assert carry_policy._apply_dig_transition_runtime_projection(carry, _obs()) is True
    assert carry_events == [
        ("complete_cell_entry", ""),
        ("complete_coverage", ""),
        ("set_skill", "carry:dig_to_carry_target_payload_loaded"),
    ]


def test_dig_to_carry_transition_preserves_completion_order_and_reason() -> None:
    policy = _make_policy()
    policy._skill_name = "dig"
    events: list[str] = []

    def exit_guard_ready(_obs: dict[str, np.ndarray]) -> bool:
        events.append("exit_guard")
        return False

    def bad_replan_ready(_obs: dict[str, np.ndarray]) -> bool:
        events.append("bad_replan")
        return False

    def complete_low(
        _obs: dict[str, np.ndarray],
        _boundary_event: Any | None,
    ) -> bool:
        events.append("complete_low")
        return False

    def dig_to_carry_decision(
        *,
        obs: dict[str, np.ndarray],
        boundary_event: Any | None,
    ) -> DigGateDecision:
        events.append("dig_to_carry")
        return DigGateDecision(True, "target_payload_loaded")

    def complete_cell_entry(_obs: dict[str, np.ndarray]) -> None:
        events.append("complete_cell_entry")

    def complete_coverage(_obs: dict[str, np.ndarray]) -> None:
        events.append("complete_coverage")

    policy._dig_exit_guard_ready = exit_guard_ready  # type: ignore[method-assign]
    policy._dig_bad_replan_ready = bad_replan_ready  # type: ignore[method-assign]
    policy._dig_complete_boundary_low_payload = complete_low  # type: ignore[method-assign]
    policy._dig_to_carry_decision = dig_to_carry_decision  # type: ignore[method-assign]
    policy._complete_cell_entry_dig = complete_cell_entry  # type: ignore[method-assign]
    policy._complete_coverage_dig = complete_coverage  # type: ignore[method-assign]

    policy._maybe_switch_skill(obs=_obs(), boundary_event=None)

    assert events == [
        "exit_guard",
        "bad_replan",
        "complete_low",
        "dig_to_carry",
        "complete_cell_entry",
        "complete_coverage",
    ]
    assert policy._skill_name == "carry"
    assert policy._switch_reason == "dig_to_carry_target_payload_loaded"


def test_dig_progress_state_apply_updates_runtime_fields() -> None:
    policy = _make_policy()
    state = DigProgressState(
        step_count=np.int64(7),
        best_mass_kg=np.float64(12.5),
        mass_plateau_count=np.int64(3),
        coverage_payload_gain_kg=np.float64(9.25),
    )

    policy._apply_dig_progress_state(state)

    assert policy._dig_step_count == 7
    assert policy._dig_best_mass_kg == 12.5
    assert policy._dig_mass_plateau_count == 3
    assert policy._coverage_current_payload_gain_kg == 9.25


def test_update_dig_progress_delegates_service_progress_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    obs = _obs()
    obs["task_metrics"] = {"mass_in_bucket_kg": 8.0}
    expected_facts = policy._dig_lifecycle_facts(obs)
    expected_config = policy._dig_lifecycle_config()
    progress = DigProgressState(
        step_count=4,
        best_mass_kg=8.0,
        mass_plateau_count=0,
        coverage_payload_gain_kg=5.0,
    )
    calls: list[tuple[str, object, object | None]] = []

    def update_progress(facts: object, config: object) -> DigProgressState:
        calls.append(("service", facts, config))
        return progress

    def apply_progress(state: DigProgressState) -> None:
        calls.append(("apply", state, None))

    monkeypatch.setattr(policy.dig_lifecycle_gate, "update_progress", update_progress)
    monkeypatch.setattr(policy, "_apply_dig_progress_state", apply_progress)

    policy._update_dig_progress(obs)

    assert calls == [
        ("service", expected_facts, expected_config),
        ("apply", progress, None),
    ]


def test_stop_after_failed_dig_applies_service_projection_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    _set_active_corridor(policy, entry=(0.40, 0.80))
    policy._coverage_current_payload_gain_kg = 12.0
    policy._dig_best_mass_kg = 18.0
    policy._dig_step_count = 42
    obs = _obs()
    obs["task_metrics"] = {"mass_in_bucket_kg": 16.0}
    events: list[tuple[str, dict[str, object]]] = []
    terminal: list[tuple[str, bool]] = []
    captured_facts: list[FailedDigStopFacts] = []
    captured_builder_kwargs: list[dict[str, object]] = []
    original_builder = primitive_planner_module.build_failed_dig_stop_facts_from_runtime
    failed_dig_stop_state = policy.dig_lifecycle_gate.failed_dig_stop_state

    def build_failed_dig_stop_facts_from_runtime(
        **kwargs: object,
    ) -> FailedDigStopFacts:
        captured_builder_kwargs.append(dict(kwargs))
        return original_builder(**kwargs)

    def capture_failed_dig_stop_state(
        facts: FailedDigStopFacts,
    ) -> object:
        captured_facts.append(facts)
        return failed_dig_stop_state(facts)

    def record_event(
        event: str,
        *,
        obs: dict[str, np.ndarray],
        corridor: CoverageCorridorState | None,
        extra: dict[str, object],
    ) -> None:
        assert corridor is policy._coverage_active_corridor()
        events.append((event, dict(extra)))

    def request_terminal_stop(reason: str, *, replace: bool = False) -> None:
        terminal.append((reason, bool(replace)))

    policy._record_coverage_decision_event = record_event  # type: ignore[method-assign]
    policy._request_coverage_terminal_stop = request_terminal_stop  # type: ignore[method-assign]
    policy.dig_lifecycle_gate.failed_dig_stop_state = capture_failed_dig_stop_state  # type: ignore[method-assign]
    monkeypatch.setattr(
        primitive_planner_module,
        "build_failed_dig_stop_facts_from_runtime",
        build_failed_dig_stop_facts_from_runtime,
    )

    policy._stop_after_failed_dig(
        "exit_overshoot_low_payload",
        obs,
        switch_reason="dig_failed_stop_exit_overshoot_low_payload",
        terminal_reason="dig_failed_exit_overshoot_low_payload",
    )

    assert policy._switch_reason == "dig_failed_stop_exit_overshoot_low_payload"
    assert captured_builder_kwargs == [
        {
            "reason": "exit_overshoot_low_payload",
            "coverage_current_payload_gain_kg": 12.0,
            "dig_best_mass_kg": 18.0,
            "current_bucket_mass_kg": 16.0,
            "dig_step_count": 42,
            "switch_reason": "dig_failed_stop_exit_overshoot_low_payload",
            "terminal_reason": "dig_failed_exit_overshoot_low_payload",
        }
    ]
    assert captured_facts == [
        FailedDigStopFacts(
            reason="exit_overshoot_low_payload",
            coverage_current_payload_gain_kg=12.0,
            dig_best_mass_kg=18.0,
            current_bucket_mass_kg=16.0,
            dig_step_count=42,
            switch_reason="dig_failed_stop_exit_overshoot_low_payload",
            terminal_reason="dig_failed_exit_overshoot_low_payload",
        )
    ]
    assert events == [
        (
            "failed_dig_stop",
            {
                "reason": "exit_overshoot_low_payload",
                "payload_gain_kg": 18.0,
                "current_bucket_mass_kg": 16.0,
                "dig_best_mass_kg": 18.0,
                "dig_step_count": 42,
            },
        )
    ]
    assert terminal == [("dig_failed_exit_overshoot_low_payload", True)]


def test_failed_dig_stop_state_apply_preserves_side_effect_order() -> None:
    policy = _make_policy()
    _set_active_corridor(policy, entry=(0.40, 0.80))
    obs = _obs()
    state = FailedDigStopState(
        switch_reason="dig_failed_stop_custom",
        terminal_reason="dig_failed_custom",
        coverage_event="failed_dig_stop",
        coverage_event_extra={"reason": "custom", "payload_gain_kg": 3.0},
        terminal_stop_replace=True,
    )
    events: list[tuple[str, object]] = []

    def record_event(
        event: str,
        *,
        obs: dict[str, np.ndarray],
        corridor: CoverageCorridorState | None,
        extra: dict[str, object],
    ) -> None:
        events.append(("record", event, corridor, dict(extra), policy._switch_reason))

    def request_terminal_stop(reason: str, *, replace: bool = False) -> None:
        events.append(("terminal", reason, bool(replace), policy._switch_reason))

    policy._record_coverage_decision_event = record_event  # type: ignore[method-assign]
    policy._request_coverage_terminal_stop = request_terminal_stop  # type: ignore[method-assign]
    corridor = policy._coverage_active_corridor()

    policy._apply_failed_dig_stop_state(state, obs=obs, corridor=corridor)

    assert policy._switch_reason == "dig_failed_stop_custom"
    assert events == [
        (
            "record",
            "failed_dig_stop",
            corridor,
            {"reason": "custom", "payload_gain_kg": 3.0},
            "dig_failed_stop_custom",
        ),
        ("terminal", "dig_failed_custom", True, "dig_failed_stop_custom"),
    ]


def test_stop_after_failed_dig_delegates_service_projection_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    obs = _obs()
    state = FailedDigStopState(
        switch_reason="dig_failed_stop_custom",
        terminal_reason="dig_failed_custom",
        coverage_event="failed_dig_stop",
        coverage_event_extra={"reason": "custom"},
        terminal_stop_replace=True,
    )
    calls: list[tuple[str, object]] = []

    def failed_dig_stop_state(facts: FailedDigStopFacts) -> FailedDigStopState:
        calls.append(("service", facts))
        return state

    def apply_state(
        applied_state: FailedDigStopState,
        *,
        obs: dict[str, np.ndarray],
        corridor: CoverageCorridorState | None,
    ) -> None:
        calls.append(("apply", applied_state, obs, corridor))

    monkeypatch.setattr(
        policy.dig_lifecycle_gate,
        "failed_dig_stop_state",
        failed_dig_stop_state,
    )
    monkeypatch.setattr(policy, "_apply_failed_dig_stop_state", apply_state)

    policy._stop_after_failed_dig("custom", obs)

    expected_corridor = policy._coverage_active_corridor()
    assert calls[0][0] == "service"
    assert isinstance(calls[0][1], FailedDigStopFacts)
    assert calls[1] == ("apply", state, obs, expected_corridor)


def test_restart_after_failed_dig_stop_uses_recovery_reasons() -> None:
    policy = _make_policy()
    policy.dig_failed_replan_next_skill = "stop"
    calls: list[tuple[str, str | None, str | None]] = []

    def stop_after_failed_dig(
        reason: str,
        _obs: dict[str, np.ndarray],
        *,
        switch_reason: str | None = None,
        terminal_reason: str | None = None,
    ) -> None:
        calls.append((reason, switch_reason, terminal_reason))

    policy._stop_after_failed_dig = stop_after_failed_dig  # type: ignore[method-assign]

    policy._restart_after_failed_dig("exit_overshoot_low_payload", _obs())

    assert calls == [
        (
            "exit_overshoot_low_payload",
            "dig_failed_stop_exit_overshoot_low_payload",
            "dig_failed_exit_overshoot_low_payload",
        )
    ]


def test_failed_dig_recovery_decision_apply_facade_preserves_side_effects() -> None:
    policy = _make_policy()
    obs = _obs()
    calls: list[tuple[str, object, object | None, str | None]] = []

    def restart_pre_dig_align(reason: str) -> None:
        calls.append(("pre_dig_align", reason, None, None))

    def stop_after_failed_dig(
        reason: str,
        _obs: dict[str, np.ndarray],
        *,
        switch_reason: str | None = None,
        terminal_reason: str | None = None,
    ) -> None:
        calls.append(("stop", reason, _obs, f"{switch_reason}|{terminal_reason}"))

    def restart_dig_with_new_cut(reason: str) -> None:
        calls.append(("dig", reason, None, None))

    policy._restart_pre_dig_align = restart_pre_dig_align  # type: ignore[method-assign]
    policy._stop_after_failed_dig = stop_after_failed_dig  # type: ignore[method-assign]
    policy._restart_dig_with_new_cut = restart_dig_with_new_cut  # type: ignore[method-assign]

    policy._apply_failed_dig_recovery_decision(
        FailedDigRecoveryDecision(
            next_skill="pre_dig_align",
            switch_reason="dig_to_pre_dig_align_bad_dig_low_payload",
        ),
        reason="bad_dig_low_payload",
        obs=obs,
    )
    policy._apply_failed_dig_recovery_decision(
        FailedDigRecoveryDecision(
            next_skill="stop",
            switch_reason="dig_failed_stop_exit_overshoot_low_payload",
            terminal_reason="dig_failed_exit_overshoot_low_payload",
        ),
        reason="exit_overshoot_low_payload",
        obs=obs,
    )
    policy._apply_failed_dig_recovery_decision(
        FailedDigRecoveryDecision(
            next_skill="dig",
            switch_reason="dig_retry_complete_low_payload",
        ),
        reason="complete_low_payload",
        obs=obs,
    )

    assert calls == [
        ("pre_dig_align", "dig_to_pre_dig_align_bad_dig_low_payload", None, None),
        (
            "stop",
            "exit_overshoot_low_payload",
            obs,
            (
                "dig_failed_stop_exit_overshoot_low_payload|"
                "dig_failed_exit_overshoot_low_payload"
            ),
        ),
        ("dig", "dig_retry_complete_low_payload", None, None),
    ]


def test_restart_after_failed_dig_delegates_recovery_decision_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    obs = _obs()
    decision = FailedDigRecoveryDecision(
        next_skill="dig",
        switch_reason="dig_retry_bad_dig_low_payload",
    )
    applied: list[tuple[FailedDigRecoveryDecision, str, dict[str, np.ndarray]]] = []

    def failed_dig_recovery(
        *,
        reason: str,
        facts: object,
        config: object,
    ) -> FailedDigRecoveryDecision:
        assert reason == "bad_dig_low_payload"
        return decision

    def apply_decision(
        state: FailedDigRecoveryDecision,
        *,
        reason: str,
        obs: dict[str, np.ndarray],
    ) -> None:
        applied.append((state, reason, obs))

    monkeypatch.setattr(
        policy.dig_lifecycle_gate,
        "failed_dig_recovery",
        failed_dig_recovery,
    )
    monkeypatch.setattr(
        policy,
        "_apply_failed_dig_recovery_decision",
        apply_decision,
    )

    policy._restart_after_failed_dig("bad_dig_low_payload", obs)

    assert applied == [(decision, "bad_dig_low_payload", obs)]


def test_reset_dig_entry_runtime_applies_service_projection() -> None:
    policy = _make_policy()
    policy._dig_step_count = 9
    policy._dig_best_mass_kg = 34.0
    policy._dig_mass_plateau_count = 5
    policy._dig_to_carry_reason = "target_payload_loaded"
    policy._coverage_current_payload_gain_kg = 21.0
    policy._dig_bad_replan_count = 2
    policy._dig_exit_guard_replan_count = 3

    policy._reset_dig_entry_runtime()

    assert policy._dig_step_count == 0
    assert policy._dig_best_mass_kg == 0.0
    assert policy._dig_mass_plateau_count == 0
    assert policy._dig_to_carry_reason == ""
    assert policy._coverage_current_payload_gain_kg == 0.0
    assert policy._dig_bad_replan_count == 2
    assert policy._dig_exit_guard_replan_count == 3


def test_reset_dig_entry_runtime_uses_domain_facts_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy._dig_bad_replan_count = "2"
    policy._dig_exit_guard_replan_count = np.int64(3)
    captured: list[object] = []

    def entry_runtime_state(facts: object) -> object:
        captured.append(facts)
        return policy.dig_lifecycle_gate.__class__.entry_runtime_state(facts)

    monkeypatch.setattr(
        policy.dig_lifecycle_gate,
        "entry_runtime_state",
        entry_runtime_state,
    )

    expected = build_dig_lifecycle_entry_runtime_facts_from_mapping(
        {
            field_name: getattr(policy, attr_name)
            for field_name, attr_name in DIG_LIFECYCLE_ENTRY_RUNTIME_FACT_FIELDS
        }
    )
    policy._reset_dig_entry_runtime()

    assert captured == [expected]
    assert policy._dig_bad_replan_count == 2
    assert policy._dig_exit_guard_replan_count == 3


def test_reset_dig_entry_runtime_applies_entry_state_facade(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy._dig_bad_replan_count = "2"
    policy._dig_exit_guard_replan_count = np.int64(3)
    state = DigLifecycleEntryRuntimeState(
        step_count=4,
        best_mass_kg=5.5,
        mass_plateau_count=6,
        dig_to_carry_reason="target_payload_loaded",
        coverage_payload_gain_kg=7.5,
        bad_replan_count=8,
        exit_guard_replan_count=9,
    )
    calls: list[tuple[str, object]] = []

    def entry_runtime_state(facts: object) -> object:
        calls.append(("entry", facts))
        return state

    def apply_state(applied_state: object) -> None:
        calls.append(("apply", applied_state))

    monkeypatch.setattr(
        policy.dig_lifecycle_gate,
        "entry_runtime_state",
        entry_runtime_state,
    )
    monkeypatch.setattr(
        policy,
        "_apply_dig_lifecycle_entry_runtime_state",
        apply_state,
    )

    expected = build_dig_lifecycle_entry_runtime_facts_from_mapping(
        {
            field_name: getattr(policy, attr_name)
            for field_name, attr_name in DIG_LIFECYCLE_ENTRY_RUNTIME_FACT_FIELDS
        }
    )
    policy._reset_dig_entry_runtime()

    assert calls == [("entry", expected), ("apply", state)]


def test_dig_lifecycle_facts_facade_uses_domain_builder() -> None:
    policy = _make_policy()
    _set_active_corridor(policy, entry=(0.40, 0.80))
    policy.boundary_detector.config.boundary_profile = (
        CYCLE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS
    )
    policy._coverage_terminal_stop_requested = True
    policy._dig_step_count = 6
    policy._dig_best_mass_kg = 14.0
    policy._dig_mass_plateau_count = 3
    policy._coverage_current_payload_gain_kg = 11.0
    obs = _obs(bucket_tip_pose=(0.20, 0.0, 0.50))
    obs["task_metrics"] = {
        "mass_in_bucket_kg": 12.0,
        "min_distance_to_dig_area_m": 0.25,
    }
    boundary_event = type(
        "_Boundary",
        (),
        {
            "dig_complete": True,
            "metrics": {
                "mass_in_bucket_kg": 18.0,
                "min_distance_to_dig_area_m": 0.45,
            },
        },
    )()

    snapshot = policy._make_snapshot(obs, boundary_event=boundary_event)
    expected = policy.dig_lifecycle_gate.facts_from_observation_view(
        view=snapshot.view,
        boundary_event=boundary_event,
        semantic_boundary_profile_active=(
            policy._semantic_boundary_profile_active()
        ),
        coverage_terminal_stop_requested=True,
        dig_step_count=6,
        dig_best_mass_kg=14.0,
        dig_mass_plateau_count=3,
        coverage_current_payload_gain_kg=11.0,
        active_corridor=policy._coverage_active_corridor(),
    )

    assert policy._dig_lifecycle_facts(obs, boundary_event) == expected


def test_dig_lifecycle_config_facade_uses_domain_builder() -> None:
    policy = _make_policy()
    policy.dig_to_carry_min_bucket_mass_kg = "15.0"
    policy.dig_to_carry_min_distance_to_dig_area_m = "0.25"
    policy.dig_to_carry_target_bucket_mass_kg = "30.0"
    policy.dig_to_carry_mass_plateau_enabled = 1
    policy.dig_to_carry_mass_plateau_min_bucket_mass_kg = "25.0"
    policy.dig_to_carry_mass_plateau_epsilon_kg = "0.5"
    policy.dig_to_carry_mass_plateau_hold_steps = 0
    policy.dig_to_carry_mass_plateau_min_steps = 0
    policy.dig_bad_replan_enabled = 1
    policy.dig_bad_replan_max_steps = 0
    policy.dig_bad_replan_min_bucket_mass_kg = "5.0"
    policy.dig_exit_guard_enabled = 1
    policy.dig_exit_guard_min_steps = 0
    policy.dig_exit_guard_overshoot_m = "0.2"
    policy.dig_exit_guard_min_bucket_mass_kg = "7.0"
    policy.dump_ready_min_bucket_mass_kg = "40.0"
    policy.dig_failed_replan_next_skill = "STOP"
    policy.pre_dig_align_enabled = 1
    policy.pre_dig_align_first_dig_only = 0
    policy.pre_dig_align_replan_after_failed_dig = 1

    expected = build_dig_lifecycle_runtime_config_from_mapping(
        {
            key: getattr(policy, key)
            for key in DIG_LIFECYCLE_RUNTIME_CONFIG_KEYS
        }
    )

    assert policy._dig_lifecycle_config() == expected


@pytest.mark.parametrize(
    "profile",
    [
        CYCLE_BOUNDARY_PROFILE_LEGACY,
        CYCLE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS,
        "unknown_profile",
        None,
    ],
)
def test_semantic_boundary_profile_facade_uses_contract_predicate(
    profile: object | None,
) -> None:
    policy = _make_policy()
    policy.boundary_detector.config.boundary_profile = profile

    assert policy._semantic_boundary_profile_active() is (
        is_v2_4_5_cycle_boundary_profile(profile)
    )


def test_dump_lifecycle_facts_facade_uses_domain_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy.boundary_detector.config.boundary_profile = (
        CYCLE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS
    )
    policy._coverage_cycle_start_deposit_kg = 6.5
    obs = _obs(deposited_mass=8.0)
    obs["task_metrics"] = {"mass_in_bucket_kg": 12.0}

    snapshot = policy._make_snapshot(obs)
    expected = policy.dump_lifecycle_gate.facts_from_observation_view(
        view=snapshot.view,
        semantic_boundary_profile_active=(
            policy._semantic_boundary_profile_active()
        ),
        coverage_cycle_start_deposit_kg=6.5,
    )
    captured: dict[str, object] = {}

    def facts_from_observation_view(**kwargs: object) -> object:
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(
        policy.dump_lifecycle_gate,
        "facts_from_observation_view",
        facts_from_observation_view,
    )

    assert policy._dump_lifecycle_facts(obs) is expected
    assert captured["view"].obs is obs
    assert captured["semantic_boundary_profile_active"] is True
    assert captured["coverage_cycle_start_deposit_kg"] == pytest.approx(6.5)


def test_dump_lifecycle_config_facade_uses_domain_builder() -> None:
    policy = _make_policy()
    policy.dump_ready_min_bucket_mass_kg = "12.5"
    policy.dump_ready_min_height_above_rim_m = "-0.1"
    policy.dump_ready_require_over_footprint = 0
    policy.dump_ready_require_clearance = 1
    policy.dump_ready_max_horizontal_distance_m = None
    policy.dump_ready_position_mode = "dump_area_relative"
    policy.dump_ready_max_dump_area_footprint_outside_distance_m = "0.30"
    policy.dump_ready_min_dump_area_relative_x_m = "-0.2"
    policy.dump_ready_max_dump_area_relative_x_m = "0.4"
    policy.dump_ready_min_dump_area_relative_z_m = None
    policy.dump_ready_max_dump_area_relative_z_m = "1.5"
    policy.dump_ready_near_window_enabled = 1
    policy.dump_ready_near_window_x_tolerance_m = "0.03"
    policy.dump_ready_near_window_z_tolerance_m = "0.04"
    policy.dump_ready_near_window_outside_tolerance_m = "0.02"
    policy.dump_ready_near_window_require_over_footprint = 0
    policy.dump_done_max_bucket_mass_kg = "8.0"
    policy.dump_done_min_deposit_delta_kg = "2.5"
    policy.approach_ready_min_bucket_mass_kg = "7.0"
    policy.approach_ready_max_horizontal_distance_m = "1.25"
    policy.approach_ready_min_height_above_rim_m = "-0.20"
    policy.approach_ready_require_clearance = 0

    expected = build_dump_lifecycle_runtime_config_from_mapping(
        {
            key: getattr(policy, key)
            for key in DUMP_LIFECYCLE_RUNTIME_CONFIG_KEYS
            if hasattr(policy, key)
        }
    )

    assert policy._dump_lifecycle_config() == expected


def test_dump_transition_runtime_apply_facades_preserve_side_effect_order() -> None:
    carry_policy = _make_policy()
    carry_policy._dump_ready_hold_count = 1
    carry_events: list[tuple[str, str]] = []

    def complete_dump(_obs: dict[str, np.ndarray], *, reason: str) -> None:
        assert carry_policy._dump_ready_hold_count == 4
        carry_events.append(("complete", reason))

    def set_return_or_direct_handoff(
        _obs: dict[str, np.ndarray],
        *,
        reason: str,
    ) -> None:
        assert carry_policy._dump_ready_hold_count == 4
        carry_events.append(("return", reason))

    carry_policy._complete_coverage_dump = complete_dump  # type: ignore[method-assign]
    carry_policy._set_return_or_direct_handoff = set_return_or_direct_handoff  # type: ignore[method-assign]

    carry_return = CarryTransitionRuntimeState(
        dump_ready_hold_count=4,
        outcome=DumpLifecycleOutcome(
            action="return",
            switch_reason="carry_to_return_release_safety",
            coverage_reason="carry_release_safety",
        ),
    )

    assert carry_policy._apply_carry_transition_runtime(carry_return, _obs()) is True
    assert carry_policy._dump_ready_hold_count == 4
    assert carry_events == [
        ("complete", "carry_release_safety"),
        ("return", "carry_to_return_release_safety"),
    ]

    carry_dump = _make_policy()
    carry_dump._deposited_mass = lambda _obs: 12.5  # type: ignore[method-assign]
    dump_events: list[tuple[str, str]] = []

    def set_skill(skill_name: str, reason: str) -> None:
        assert carry_dump._dump_ready_hold_count == 2
        assert carry_dump._dump_start_deposited_mass_kg == pytest.approx(12.5)
        dump_events.append((skill_name, reason))

    carry_dump._set_skill = set_skill  # type: ignore[method-assign]
    carry_dump_state = CarryTransitionRuntimeState(
        dump_ready_hold_count=2,
        outcome=DumpLifecycleOutcome(
            action="dump",
            switch_reason="carry_to_dump_target_ready",
        ),
    )

    assert carry_dump._apply_carry_transition_runtime(carry_dump_state, _obs()) is True
    assert dump_events == [("dump", "carry_to_dump_target_ready")]

    dump_policy = _make_policy()
    dump_events: list[tuple[str, str]] = []

    def complete_dump_done(_obs: dict[str, np.ndarray], *, reason: str) -> None:
        assert dump_policy._dump_done_hold_count == 3
        dump_events.append(("complete", reason))

    def set_return_done(
        _obs: dict[str, np.ndarray],
        *,
        reason: str,
    ) -> None:
        assert dump_policy._dump_done_hold_count == 3
        dump_events.append(("return", reason))

    dump_policy._complete_coverage_dump = complete_dump_done  # type: ignore[method-assign]
    dump_policy._set_return_or_direct_handoff = set_return_done  # type: ignore[method-assign]
    dump_return = DumpTransitionRuntimeState(
        dump_done_hold_count=3,
        outcome=DumpLifecycleOutcome(
            action="return",
            switch_reason="dump_to_return_mass_low",
            coverage_reason="dump_done_mass_low",
        ),
    )

    assert dump_policy._apply_dump_transition_runtime(dump_return, _obs()) is True
    assert dump_events == [
        ("complete", "dump_done_mass_low"),
        ("return", "dump_to_return_mass_low"),
    ]

    dump_wait = DumpTransitionRuntimeState(
        dump_done_hold_count=1,
        outcome=DumpLifecycleOutcome(action="none"),
    )
    assert dump_policy._apply_dump_transition_runtime(dump_wait, _obs()) is False
    assert dump_policy._dump_done_hold_count == 1
    assert dump_events == [
        ("complete", "dump_done_mass_low"),
        ("return", "dump_to_return_mass_low"),
    ]


def test_carry_transition_request_uses_lifecycle_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy._skill_name = "carry"
    policy._dump_ready_hold_count = 2
    policy.boundary_detector.config.boundary_profile = (
        CYCLE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS
    )
    boundary_event = type(
        "_Boundary",
        (),
        {"dump_complete": True},
    )()
    captured: dict[str, object] = {}
    original_builder = primitive_planner_module.build_carry_transition_runtime_request

    def build_request(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return original_builder(**kwargs)

    def fail_dump_ready(_obs: dict[str, np.ndarray]) -> bool:
        raise AssertionError("dump_ready must not be checked after boundary event")

    policy._carry_release_safety_done = lambda _obs: False  # type: ignore[method-assign]
    policy._dump_ready = fail_dump_ready  # type: ignore[method-assign]
    policy._complete_coverage_dump = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: None
    )
    policy._set_return_or_direct_handoff = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        primitive_planner_module,
        "build_carry_transition_runtime_request",
        build_request,
    )

    policy._maybe_switch_skill(
        obs=_obs(deposited_mass=7.0),
        boundary_event=boundary_event,
    )

    assert captured["release_safety_done"] is False
    assert captured["boundary_event"] is boundary_event
    assert captured["semantic_boundary_profile_active"] is True
    assert captured["current_dump_ready_hold_count"] == 2


def test_carry_boundary_event_does_not_call_dump_ready_gate() -> None:
    policy = _make_policy()
    policy._skill_name = "carry"

    def fail_dump_ready(_obs: dict[str, np.ndarray]) -> bool:
        raise AssertionError("dump_ready must not be checked after boundary event")

    policy._dump_ready = fail_dump_ready  # type: ignore[method-assign]

    policy._maybe_switch_skill(
        obs=_obs(deposited_mass=7.0),
        boundary_event=type(
            "_Boundary",
            (),
            {"dump_committed_start": True},
        )(),
    )

    assert policy._skill_name == "dump"
    assert policy._switch_reason == "carry_to_dump_dump_committed_boundary"
    assert policy._dump_ready_hold_count == policy.dump_ready_hold_steps


def test_carry_dump_complete_event_preserves_ready_hold_count() -> None:
    policy = _make_policy()
    policy._skill_name = "carry"
    policy._dump_ready_hold_count = 1
    completed: list[str] = []

    def fail_dump_ready(_obs: dict[str, np.ndarray]) -> bool:
        raise AssertionError("dump_ready must not be checked after dump complete")

    def complete_dump(_obs: dict[str, np.ndarray], *, reason: str) -> None:
        completed.append(reason)

    policy._dump_ready = fail_dump_ready  # type: ignore[method-assign]
    policy._complete_coverage_dump = complete_dump  # type: ignore[method-assign]

    policy._maybe_switch_skill(
        obs=_obs(deposited_mass=7.0),
        boundary_event=type(
            "_Boundary",
            (),
            {"dump_complete": True},
        )(),
    )

    assert completed == ["carry_dump_complete_boundary"]
    assert policy._dump_ready_hold_count == 1
    assert policy._skill_name == "return"
    assert policy._switch_reason == "carry_to_return_dump_complete_boundary"


def test_dump_transition_request_uses_lifecycle_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy._skill_name = "dump"
    policy._dump_done_hold_count = 3
    policy.dump_done_use_boundary_event = True
    policy.boundary_detector.config.boundary_profile = (
        CYCLE_BOUNDARY_PROFILE_V2_4_5_SPATIAL_MASS
    )
    boundary_event = type(
        "_Boundary",
        (),
        {"dump_complete": True},
    )()
    captured: dict[str, object] = {}
    original_builder = primitive_planner_module.build_dump_transition_runtime_request

    def build_request(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return original_builder(**kwargs)

    def fail_dump_done(_obs: dict[str, np.ndarray]) -> bool:
        raise AssertionError("dump_done must not be checked after boundary event")

    policy._dump_done = fail_dump_done  # type: ignore[method-assign]
    policy._complete_coverage_dump = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: None
    )
    policy._set_return_or_direct_handoff = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        primitive_planner_module,
        "build_dump_transition_runtime_request",
        build_request,
    )

    policy._maybe_switch_skill(
        obs=_obs(deposited_mass=7.0),
        boundary_event=boundary_event,
    )

    assert captured["dump_done_use_boundary_event"] is True
    assert captured["boundary_event"] is boundary_event
    assert captured["semantic_boundary_profile_active"] is True
    assert captured["current_dump_done_hold_count"] == 3


def test_dump_complete_event_does_not_call_dump_done_gate() -> None:
    policy = _make_policy()
    policy._skill_name = "dump"
    policy._dump_done_hold_count = 1
    completed: list[str] = []

    def fail_dump_done(_obs: dict[str, np.ndarray]) -> bool:
        raise AssertionError("dump_done must not be checked after boundary event")

    def complete_dump(_obs: dict[str, np.ndarray], *, reason: str) -> None:
        completed.append(reason)

    policy._dump_done = fail_dump_done  # type: ignore[method-assign]
    policy._complete_coverage_dump = complete_dump  # type: ignore[method-assign]

    policy._maybe_switch_skill(
        obs=_obs(deposited_mass=7.0),
        boundary_event=type(
            "_Boundary",
            (),
            {"dump_complete": True},
        )(),
    )

    assert completed == ["dump_complete_boundary"]
    assert policy._dump_done_hold_count == 1
    assert policy._skill_name == "return"
    assert policy._switch_reason == "dump_to_return_dump_complete_boundary"


def test_policy_obs_uses_request_gate_before_calling_token_helpers() -> None:
    policy = _make_policy()
    calls: list[str] = []

    def request() -> PolicyObservationTokenRequest:
        calls.append("request")
        return PolicyObservationTokenRequest(
            goal_tokens=True,
            cell_entry_tokens=False,
            dig_cut_tokens=False,
            dig_depth_profile_tokens=False,
            return_target_tokens=False,
            return_relocate_tokens=False,
            return_start_envelope_tokens=False,
        )

    def goal_tokens() -> np.ndarray:
        calls.append("goal")
        return np.asarray([1.0], dtype=np.float32)

    def forbidden(_obs: dict[str, np.ndarray]) -> None:
        raise AssertionError("disabled token helper must not be called")

    policy._policy_observation_token_request = request  # type: ignore[method-assign]
    policy._goal_tokens = goal_tokens  # type: ignore[method-assign]
    policy._cell_entry_tokens_for_obs = forbidden  # type: ignore[method-assign]
    policy._dig_cut_tokens_for_obs = forbidden  # type: ignore[method-assign]
    policy._dig_depth_profile_tokens_for_obs = forbidden  # type: ignore[method-assign]
    policy._return_target_tokens_for_obs = forbidden  # type: ignore[method-assign]
    policy._return_relocate_tokens_for_obs = forbidden  # type: ignore[method-assign]
    policy._return_start_envelope_tokens_for_obs = forbidden  # type: ignore[method-assign]

    policy_obs = policy._policy_obs(_obs())

    assert calls == ["request", "goal"]
    np.testing.assert_allclose(policy_obs["goal_tokens"], [1.0])
    assert not policy._cell_entry_token_injected
    assert not policy._dig_cut_token_injected
    assert not policy._dig_depth_profile_token_injected
    assert not policy._return_target_token_injected
    assert not policy._return_relocate_token_injected
    assert not policy._return_start_envelope_token_injected


def test_policy_observation_assembly_apply_updates_injection_flags() -> None:
    policy = _make_policy()
    previous_state = policy._planner_conditioning_state
    obs = {"qpos": np.asarray([1.0], dtype=np.float32)}
    assembly = PolicyObservationAssembly(
        obs=obs,
        cell_entry_token_injected=True,
        dig_cut_token_injected=False,
        dig_depth_profile_token_injected=True,
        return_target_token_injected=False,
        return_relocate_token_injected=True,
        return_start_envelope_token_injected=False,
    )

    returned = policy._apply_policy_observation_assembly(assembly)

    assert returned is obs
    assert policy._planner_conditioning_state is not previous_state
    assert policy._planner_conditioning_state.cell_entry_token_injected is True
    assert policy._planner_conditioning_state.dig_cut.token_injected is False
    assert (
        policy._planner_conditioning_state.dig_depth_profile.token_injected
        is True
    )
    assert (
        policy._planner_conditioning_state.return_target.target_token_injected
        is False
    )
    assert (
        policy._planner_conditioning_state.return_target.relocate_token_injected
        is True
    )
    assert (
        policy._planner_conditioning_state.return_target.start_envelope_token_injected
        is False
    )
    assert policy._cell_entry_token_injected is True
    assert policy._dig_cut_token_injected is False
    assert policy._dig_depth_profile_token_injected is True
    assert policy._return_target_token_injected is False
    assert policy._return_relocate_token_injected is True
    assert policy._return_start_envelope_token_injected is False


def test_policy_conditioning_private_fields_are_runtime_state_shims() -> None:
    policy = _make_policy()
    policy._planner_conditioning_state = PlannerConditioningState()
    dig_cut_tokens = np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float32)
    depth_tokens = np.arange(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float32)
    target_tokens = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32)
    relocate_tokens = target_tokens + 10.0
    envelope_tokens = np.arange(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)
    pending_tokens = dig_cut_tokens + 20.0
    pending_depth_tokens = depth_tokens + 30.0

    policy._cell_entry_token_injected = True
    policy._dig_cut_tokens = dig_cut_tokens
    policy._dig_cut_token_injected = True
    policy._dig_cut_planned_cycle_id = np.int64(4)
    policy._dig_cut_token_source = "dig_source"
    policy._dig_cut_fallback_reason = "dig_fallback"
    policy._dig_cut_token_in_prior_p10_p90 = True
    policy._dig_depth_profile_tokens = depth_tokens
    policy._dig_depth_profile_token_injected = True
    policy._dig_depth_profile_token_source = "depth_source"
    policy._dig_depth_profile_fallback_reason = "depth_fallback"
    policy._return_target_tokens = target_tokens
    policy._return_target_token_injected = True
    policy._return_target_token_source = "target_source"
    policy._return_target_fallback_reason = "target_fallback"
    policy._return_relocate_tokens = relocate_tokens
    policy._return_relocate_token_injected = True
    policy._return_start_envelope_tokens = envelope_tokens
    policy._return_start_envelope_token_injected = True
    policy._return_start_envelope_token_source = "envelope_source"
    policy._return_start_envelope_use_prior_spatial_bounds = False
    policy._return_start_envelope_use_prior_qpos_bounds = True
    policy._return_target_planned_cycle_id = np.int64(8)
    policy._pending_dig_cut_cycle_id = np.int64(9)
    policy._pending_dig_cut_corridor_id = np.int64(10)
    policy._pending_dig_cut_raw_fields = {"operator_entry_x_m": 1.5}
    policy._pending_dig_cut_tokens = pending_tokens
    policy._pending_dig_depth_profile_tokens = pending_depth_tokens
    policy._pending_dig_state_exemplar_ids = ["cell7_deep"]
    policy._pending_dig_state_exemplar_distance = np.float64(0.25)

    assert policy._cell_entry_token_injected is True
    assert policy._dig_cut_tokens is dig_cut_tokens
    assert policy._dig_cut_token_injected is True
    assert policy._dig_cut_planned_cycle_id == 4
    assert policy._dig_cut_token_source == "dig_source"
    assert policy._dig_cut_fallback_reason == "dig_fallback"
    assert policy._dig_cut_token_in_prior_p10_p90 is True
    assert policy._dig_depth_profile_tokens is depth_tokens
    assert policy._dig_depth_profile_token_source == "depth_source"
    assert policy._return_target_tokens is target_tokens
    assert policy._return_target_token_source == "target_source"
    assert policy._return_relocate_tokens is relocate_tokens
    assert policy._return_start_envelope_tokens is envelope_tokens
    assert policy._return_start_envelope_token_source == "envelope_source"
    assert policy._return_start_envelope_use_prior_spatial_bounds is False
    assert policy._return_start_envelope_use_prior_qpos_bounds is True
    assert policy._return_target_planned_cycle_id == 8
    assert policy._pending_dig_cut_cycle_id == 9
    assert policy._pending_dig_cut_corridor_id == 10
    assert policy._pending_dig_cut_raw_fields == {"operator_entry_x_m": 1.5}
    assert policy._pending_dig_cut_tokens is pending_tokens
    assert policy._pending_dig_depth_profile_tokens is pending_depth_tokens
    assert policy._pending_dig_state_exemplar_ids == ["cell7_deep"]
    assert policy._pending_dig_state_exemplar_distance == pytest.approx(0.25)


def test_policy_obs_delegates_assembly_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    obs = _obs()
    assembly = PolicyObservationAssembly(obs={"assembled": True})
    expected = {"applied": True}
    calls: list[tuple[str, object]] = []

    def request() -> PolicyObservationTokenRequest:
        calls.append(("request", None))
        return PolicyObservationTokenRequest(goal_tokens=False)

    def assemble(
        obs_arg: dict[str, object],
        tokens: PolicyObservationTokens,
    ) -> PolicyObservationAssembly:
        calls.append(("assemble", obs_arg))
        assert obs_arg is obs
        assert tokens.all_missing()
        return assembly

    def apply_assembly(applied_assembly: PolicyObservationAssembly) -> dict:
        calls.append(("apply", applied_assembly))
        return expected

    monkeypatch.setattr(policy, "_policy_observation_token_request", request)
    monkeypatch.setattr(policy.policy_observation_assembler, "assemble", assemble)
    monkeypatch.setattr(
        policy,
        "_apply_policy_observation_assembly",
        apply_assembly,
    )

    returned = policy._policy_obs(obs)

    assert returned is expected
    assert calls == [
        ("request", None),
        ("assemble", obs),
        ("apply", assembly),
    ]


def test_policy_observation_token_request_facade_uses_mapping_gate() -> None:
    policy = _make_policy()
    policy._skill_name = "bootstrap"
    policy.cell_entry_enabled = 1
    policy.dig_cut_planner_enabled = 1
    policy._coverage_terminal_stop_requested = False
    policy.return_target_planner_enabled = 1
    policy.bootstrap_policy = _ConstantPolicy(4.0)
    expected = PolicyObservationTokenRequest(
        goal_tokens=True,
        dig_cut_tokens=True,
        dig_depth_profile_tokens=True,
    )
    calls: list[tuple[dict[str, object], PolicyObservationRequestConfig | None]] = []

    def token_request_from_mapping(
        values: dict[str, object],
        config: PolicyObservationRequestConfig | None = None,
    ) -> PolicyObservationTokenRequest:
        calls.append((values, config))
        return expected

    policy.policy_observation_assembler.token_request_from_mapping = (  # type: ignore[method-assign]
        token_request_from_mapping
    )

    assert policy._policy_observation_token_request() is expected
    assert len(calls) == 1
    values, config = calls[0]
    assert values == {
        config_key: getattr(policy, attr_name)
        for config_key, attr_name in POLICY_OBSERVATION_REQUEST_FACT_FIELDS
    }
    assert config == PolicyObservationRequestConfig(
        dig_skill_name="dig",
        return_skill_name="return",
        bootstrap_skill_name="bootstrap",
    )


def test_dig_conditioning_token_facades_use_policy_observation_gate_mapping() -> None:
    policy = _make_policy()
    policy._skill_name = 123
    policy._coverage_terminal_stop_requested = 1
    calls: list[tuple[dict[str, object], bool, str]] = []

    def fail_ensure(_obs: dict[str, np.ndarray]) -> None:
        raise AssertionError("gate rejected token request; plan must not build")

    def gate_from_mapping(
        values: dict[str, object],
        *,
        token_requested: object,
        config: PolicyObservationRequestConfig | None = None,
    ) -> DigConditioningObservationTokenGateDecision:
        calls.append(
            (
                dict(values),
                bool(token_requested),
                "" if config is None else str(config.dig_skill_name),
            )
        )
        return DigConditioningObservationTokenGateDecision(
            return_token=False,
            should_build_plan=True,
        )

    policy._ensure_dig_cut_plan_for_cycle = fail_ensure  # type: ignore[method-assign]
    policy.policy_observation_assembler.dig_conditioning_token_gate_from_mapping = (  # type: ignore[method-assign]
        gate_from_mapping
    )

    assert (
        policy._dig_cut_tokens_for_obs(
            {},
            PolicyObservationTokenRequest(dig_cut_tokens=True),
        )
        is None
    )
    assert (
        policy._dig_depth_profile_tokens_for_obs(
            {},
            PolicyObservationTokenRequest(dig_depth_profile_tokens=False),
        )
        is None
    )

    expected_values = {
        field_name: getattr(policy, attr_name)
        for field_name, attr_name in DIG_CONDITIONING_TOKEN_GATE_FACT_FIELDS
    }
    assert calls == [
        (expected_values, True, "dig"),
        (expected_values, False, "dig"),
    ]


def test_cell_entry_runtime_facts_facade_uses_domain_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy._cycle_index = np.int64(3)
    policy._skill_name = 123
    obs = _obs(bucket_pose=(0.25, 0.0, 0.40), deposited_mass=12.5)

    snapshot = policy._make_snapshot(obs)
    expected = policy.cell_entry_runtime_service.facts_from_observation_view(
        view=snapshot.view,
        cycle_index=policy._cycle_index,
        active_skill=policy._skill_name,
    )
    captured: dict[str, object] = {}

    def facts_from_observation_view(**kwargs: object) -> object:
        captured.update(kwargs)
        return expected

    monkeypatch.setattr(
        policy.cell_entry_runtime_service,
        "facts_from_observation_view",
        facts_from_observation_view,
    )

    assert policy._cell_entry_runtime_facts(obs) is expected
    assert captured["view"].obs is obs
    assert captured["cycle_index"] is policy._cycle_index
    assert captured["active_skill"] is policy._skill_name


def test_cell_entry_runtime_state_facade_uses_domain_builder() -> None:
    policy = _make_policy()
    goal = CellEntryPlanner(grid=CellGridSpec()).plan(cycle_id=3)
    tokens = np.arange(CELL_ENTRY_TOKEN_DIM, dtype=np.float64)
    policy._cell_entry_goal = goal
    policy._cell_entry_goal_cycle_id = np.int64(3)
    policy._cell_entry_audit = object()
    policy._cell_entry_tokens = tokens
    policy._cell_entry_token_injected = True
    policy._cell_entry_seen_cell_id = np.int64(2)
    policy._cell_entry_trace = [{"cycle_id": 3, "audit_reason": "ok"}]

    expected = build_cell_entry_runtime_state_from_mapping(
        {
            field_name: getattr(policy, attr_name)
            for field_name, attr_name in CELL_ENTRY_RUNTIME_STATE_FIELDS
        }
    )
    actual = policy._cell_entry_runtime_state()

    assert actual.goal is expected.goal
    assert actual.goal_cycle_id == expected.goal_cycle_id
    assert actual.audit is expected.audit
    assert actual.tokens is tokens
    assert actual.tokens is expected.tokens
    assert actual.token_injected is False
    assert actual.seen_cell_id == expected.seen_cell_id
    assert actual.trace_events == ()


def test_cell_entry_runtime_token_result_apply_preserves_side_effect_boundary() -> None:
    policy = _make_policy()
    goal = CellEntryPlanner(grid=CellGridSpec()).plan(cycle_id=5)
    audit = object()
    tokens = np.arange(CELL_ENTRY_TOKEN_DIM, dtype=np.float64)
    original_trace = [{"cycle_id": 2, "audit_reason": "keep"}]
    policy._cell_entry_token_injected = True
    policy._cell_entry_trace = list(original_trace)

    result = CellEntryRuntimeTokenResult(
        tokens=tokens,
        state=CellEntryRuntimeState(
            goal=goal,
            goal_cycle_id=np.int64(5),
            audit=audit,
            tokens=np.full(CELL_ENTRY_TOKEN_DIM, -1.0, dtype=np.float32),
            token_injected=False,
            seen_cell_id=np.int64(4),
            trace_events=({"cycle_id": 99, "audit_reason": "ignored"},),
        ),
    )

    returned = policy._apply_cell_entry_runtime_token_result(result)

    assert policy._cell_entry_goal is goal
    assert policy._cell_entry_goal_cycle_id == 5
    assert policy._cell_entry_audit is audit
    assert policy._cell_entry_seen_cell_id == 4
    assert policy._cell_entry_token_injected is True
    assert policy._cell_entry_trace == original_trace
    np.testing.assert_allclose(policy._cell_entry_tokens, tokens.astype(np.float32))
    np.testing.assert_allclose(returned, policy._cell_entry_tokens)
    assert returned is not policy._cell_entry_tokens


def test_cell_entry_runtime_completion_result_apply_appends_trace_only() -> None:
    policy = _make_policy()
    old_goal = CellEntryPlanner(grid=CellGridSpec()).plan(cycle_id=1)
    ignored_goal = CellEntryPlanner(grid=CellGridSpec()).plan(cycle_id=3)
    trace_event = {"cycle_id": 3, "audit_reason": "ok"}
    policy._cell_entry_goal = old_goal
    policy._cell_entry_goal_cycle_id = 1
    policy._cell_entry_trace = [{"cycle_id": 1, "audit_reason": "keep"}]

    result = CellEntryRuntimeCompletionResult(
        trace_event=trace_event,
        outcome=None,
        state=CellEntryRuntimeState(
            goal=ignored_goal,
            goal_cycle_id=3,
            trace_events=({"cycle_id": 99, "audit_reason": "ignored"},),
        ),
    )

    policy._apply_cell_entry_runtime_completion_result(result)

    assert policy._cell_entry_goal is old_goal
    assert policy._cell_entry_goal_cycle_id == 1
    assert policy._cell_entry_trace[-1] is trace_event
    assert policy._cell_entry_trace == [
        {"cycle_id": 1, "audit_reason": "keep"},
        trace_event,
    ]


def test_cell_entry_tokens_for_obs_delegates_result_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    result = CellEntryRuntimeTokenResult(
        tokens=np.arange(CELL_ENTRY_TOKEN_DIM, dtype=np.float32),
        state=CellEntryRuntimeState(),
    )
    expected = np.asarray([42.0], dtype=np.float32)
    calls: list[tuple[str, object]] = []

    def tokens_for_obs(**_kwargs: object) -> CellEntryRuntimeTokenResult:
        calls.append(("service", result))
        return result

    def apply_result(
        applied_result: CellEntryRuntimeTokenResult,
    ) -> np.ndarray:
        calls.append(("apply", applied_result))
        return expected

    monkeypatch.setattr(
        policy.cell_entry_runtime_service,
        "tokens_for_obs",
        tokens_for_obs,
    )
    monkeypatch.setattr(
        policy,
        "_apply_cell_entry_runtime_token_result",
        apply_result,
    )

    actual = policy._cell_entry_tokens_for_obs(
        _obs(),
        PolicyObservationTokenRequest(cell_entry_tokens=True),
    )

    assert actual is expected
    assert calls == [("service", result), ("apply", result)]


def test_complete_cell_entry_dig_delegates_completion_result_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy.cell_entry_enabled = True
    policy._cell_entry_goal = CellEntryPlanner(grid=CellGridSpec()).plan(cycle_id=1)
    result = CellEntryRuntimeCompletionResult(
        trace_event={"cycle_id": 1, "audit_reason": "ok"},
        outcome=None,
        state=CellEntryRuntimeState(),
    )
    calls: list[tuple[str, object]] = []

    def complete_dig(**_kwargs: object) -> CellEntryRuntimeCompletionResult:
        calls.append(("service", result))
        return result

    def apply_result(applied_result: CellEntryRuntimeCompletionResult) -> None:
        calls.append(("apply", applied_result))

    monkeypatch.setattr(
        policy.cell_entry_runtime_service,
        "complete_dig",
        complete_dig,
    )
    monkeypatch.setattr(
        policy,
        "_apply_cell_entry_runtime_completion_result",
        apply_result,
    )

    policy._complete_cell_entry_dig(_obs())

    assert calls == [("service", result), ("apply", result)]


def test_policy_obs_preserves_enabled_token_helper_order() -> None:
    policy = _make_policy()
    calls: list[str] = []

    def request() -> PolicyObservationTokenRequest:
        calls.append("request")
        return PolicyObservationTokenRequest(
            goal_tokens=True,
            cell_entry_tokens=True,
            dig_cut_tokens=True,
            dig_depth_profile_tokens=True,
            return_target_tokens=True,
            return_relocate_tokens=True,
            return_start_envelope_tokens=True,
        )

    def token(name: str, value: float) -> np.ndarray:
        calls.append(name)
        return np.asarray([value], dtype=np.float32)

    policy._policy_observation_token_request = request  # type: ignore[method-assign]
    policy._goal_tokens = lambda: token("goal", 1.0)  # type: ignore[method-assign]
    policy._cell_entry_tokens_for_obs = lambda _obs, _request=None: token("cell", 2.0)  # type: ignore[method-assign]
    policy._dig_cut_tokens_for_obs = lambda _obs, _request=None: token("dig_cut", 3.0)  # type: ignore[method-assign]
    policy._dig_depth_profile_tokens_for_obs = lambda _obs, _request=None: token("depth", 4.0)  # type: ignore[method-assign]
    policy._return_target_tokens_for_obs = lambda _obs, _request=None: token("target", 5.0)  # type: ignore[method-assign]
    policy._return_relocate_tokens_for_obs = lambda _obs, _request=None: token("relocate", 6.0)  # type: ignore[method-assign]
    policy._return_start_envelope_tokens_for_obs = lambda _obs, _request=None: token("envelope", 7.0)  # type: ignore[method-assign]

    policy_obs = policy._policy_obs(_obs())

    assert calls == [
        "request",
        "goal",
        "cell",
        "dig_cut",
        "depth",
        "target",
        "relocate",
        "envelope",
    ]
    np.testing.assert_allclose(policy_obs["goal_tokens"], [1.0])
    np.testing.assert_allclose(policy_obs["cell_entry_tokens"], [2.0])
    np.testing.assert_allclose(policy_obs["dig_cut_tokens"], [3.0])
    np.testing.assert_allclose(policy_obs["dig_depth_profile_tokens_v1"], [4.0])
    np.testing.assert_allclose(policy_obs["return_target_tokens"], [5.0])
    np.testing.assert_allclose(policy_obs["return_relocate_tokens_v1"], [6.0])
    np.testing.assert_allclose(policy_obs["return_start_envelope_tokens_v1"], [7.0])
    assert policy._cell_entry_token_injected
    assert policy._dig_cut_token_injected
    assert policy._dig_depth_profile_token_injected
    assert policy._return_target_token_injected
    assert policy._return_relocate_token_injected
    assert policy._return_start_envelope_token_injected


def test_return_direct_handoff_facade_preserves_gate_call_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy._skill_name = "return"
    policy.return_target_planner_enabled = True
    policy.return_to_dig_start_envelope_direct_handoff_enabled = True
    calls: list[str] = []

    def ensure_return_target(_obs: dict[str, np.ndarray]) -> None:
        calls.append("ensure")

    def handoff_ready(_obs: dict[str, np.ndarray]) -> bool:
        calls.append("handoff")
        assert calls == ["ensure", "handoff"]
        return True

    def direct_handoff_ready(
        _obs: dict[str, np.ndarray],
        *,
        handoff_ready: bool | None = None,
    ) -> bool:
        calls.append("direct")
        assert handoff_ready is True
        assert calls == ["ensure", "handoff", "direct"]
        return True

    monkeypatch.setattr(policy, "_ensure_return_target_plan_for_cycle", ensure_return_target)
    monkeypatch.setattr(policy, "_return_to_dig_handoff_ready", handoff_ready)
    monkeypatch.setattr(policy, "_return_to_dig_direct_handoff_ready", direct_handoff_ready)

    assert policy._try_return_direct_handoff_at_current_obs(_obs()) is True
    assert calls == ["ensure", "handoff", "direct"]
    assert policy._skill_name == "dig"
    assert policy._switch_reason == "return_to_dig_start_envelope_ready"


def test_return_direct_handoff_facade_applies_completion_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy._skill_name = "return"
    policy.return_target_planner_enabled = True
    policy.return_to_dig_start_envelope_direct_handoff_enabled = True
    calls: list[
        tuple[
            str,
            ReturnToDigTransitionCompletionFacts,
            ReturnToDigTransitionCompletionConfig,
        ]
    ] = []
    request_calls: list[dict[str, object]] = []

    def completion_request(
        **kwargs: object,
    ) -> ReturnToDigTransitionCompletionRequest:
        request_calls.append(dict(kwargs))
        return ReturnToDigTransitionCompletionRequest(
            facts=ReturnToDigTransitionCompletionFacts(
                pre_dig_align_before_dig=bool(kwargs["pre_dig_align_before_dig"]),
            ),
            config=ReturnToDigTransitionCompletionConfig(
                pre_dig_align_skill_name=str(kwargs["pre_dig_align_skill_name"]),
            ),
        )

    def direct_completion(
        outcome: Any,
        facts: ReturnToDigTransitionCompletionFacts,
        config: ReturnToDigTransitionCompletionConfig,
    ) -> ReturnToDigTransitionCompletion:
        calls.append((str(outcome.action), facts, config))
        return ReturnToDigTransitionCompletion(
            should_transition=True,
            next_skill="dig",
            switch_reason="return_to_dig_start_envelope_ready",
        )

    def pre_dig_align_after_cycle_update() -> bool:
        assert policy._cycle_index == 1
        assert policy._completed_transition_count == 1
        return False

    monkeypatch.setattr(policy, "_ensure_return_target_plan_for_cycle", lambda _obs: None)
    monkeypatch.setattr(policy, "_return_to_dig_handoff_ready", lambda _obs: True)
    monkeypatch.setattr(
        policy,
        "_return_to_dig_direct_handoff_ready",
        lambda _obs, *, handoff_ready=None: bool(handoff_ready),
    )
    monkeypatch.setattr(
        policy,
        "_should_pre_dig_align_before_dig",
        pre_dig_align_after_cycle_update,
    )
    monkeypatch.setattr(
        policy.return_transition_service,
        "completion_request",
        completion_request,
    )
    monkeypatch.setattr(
        policy.return_transition_service,
        "direct_handoff_completion",
        direct_completion,
    )

    assert policy._try_return_direct_handoff_at_current_obs(_obs()) is True

    assert request_calls == [
        {
            "pre_dig_align_before_dig": False,
            "pre_dig_align_skill_name": "pre_dig_align",
        }
    ]
    assert calls == [
        (
            "direct_handoff",
            ReturnToDigTransitionCompletionFacts(pre_dig_align_before_dig=False),
            ReturnToDigTransitionCompletionConfig(
                pre_dig_align_skill_name="pre_dig_align",
            ),
        )
    ]
    assert policy._skill_name == "dig"
    assert policy._switch_reason == "return_to_dig_start_envelope_ready"
    assert policy._cycle_index == 1
    assert policy._completed_transition_count == 1


def test_return_direct_handoff_facade_delegates_completion_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy._skill_name = "return"
    policy.return_target_planner_enabled = True
    policy.return_to_dig_start_envelope_direct_handoff_enabled = True
    completion = ReturnToDigTransitionCompletion(
        should_transition=True,
        next_skill="dig",
        switch_reason="return_to_dig_start_envelope_ready",
    )
    applied: list[ReturnToDigTransitionCompletion] = []

    def direct_completion(
        outcome: Any,
        facts: ReturnToDigTransitionCompletionFacts,
        config: ReturnToDigTransitionCompletionConfig,
    ) -> ReturnToDigTransitionCompletion:
        assert str(outcome.action) == "direct_handoff"
        assert facts == ReturnToDigTransitionCompletionFacts(
            pre_dig_align_before_dig=False
        )
        assert config == ReturnToDigTransitionCompletionConfig(
            pre_dig_align_skill_name="pre_dig_align",
        )
        return completion

    def apply_completion(state: ReturnToDigTransitionCompletion) -> bool:
        applied.append(state)
        return True

    def pre_dig_align_after_cycle_update() -> bool:
        assert policy._cycle_index == 1
        assert policy._completed_transition_count == 1
        return False

    monkeypatch.setattr(policy, "_ensure_return_target_plan_for_cycle", lambda _obs: None)
    monkeypatch.setattr(policy, "_return_to_dig_handoff_ready", lambda _obs: True)
    monkeypatch.setattr(
        policy,
        "_return_to_dig_direct_handoff_ready",
        lambda _obs, *, handoff_ready=None: bool(handoff_ready),
    )
    monkeypatch.setattr(
        policy,
        "_should_pre_dig_align_before_dig",
        pre_dig_align_after_cycle_update,
    )
    monkeypatch.setattr(
        policy.return_transition_service,
        "direct_handoff_completion",
        direct_completion,
    )
    monkeypatch.setattr(
        policy,
        "_apply_return_to_dig_transition_completion",
        apply_completion,
    )

    assert policy._try_return_direct_handoff_at_current_obs(_obs()) is True
    assert applied == [completion]


def test_return_transition_runtime_projection_apply_facade_updates_lifecycle_state_only() -> None:
    policy = _make_policy()
    policy._skill_name = "return"
    policy._switch_reason = "before"
    policy._return_next_dig_event_seen = False
    policy._completed_transition_count = 4
    policy._cycle_index = 9

    waiting = ReturnToDigTransitionRuntimeProjection(
        next_dig_event_seen=True,
        should_transition=False,
        completed_transition_increment=99,
        cycle_index_increment=99,
    )
    assert policy._apply_return_to_dig_transition_runtime_projection(waiting) is False
    assert policy._return_next_dig_event_seen is True
    assert policy._completed_transition_count == 4
    assert policy._cycle_index == 9
    assert policy._skill_name == "return"
    assert policy._switch_reason == "before"

    transition = ReturnToDigTransitionRuntimeProjection(
        next_dig_event_seen=True,
        should_transition=True,
        completed_transition_increment=1,
        cycle_index_increment=1,
    )
    assert (
        policy._apply_return_to_dig_transition_runtime_projection(transition)
        is True
    )
    assert policy._return_next_dig_event_seen is True
    assert policy._completed_transition_count == 5
    assert policy._cycle_index == 10
    assert policy._skill_name == "return"
    assert policy._switch_reason == "before"

    direct_handoff = ReturnDirectHandoffRuntimeProjection(
        should_transition=True,
        completed_transition_increment=1,
        cycle_index_increment=1,
    )
    assert (
        policy._apply_return_to_dig_transition_runtime_projection(direct_handoff)
        is True
    )
    assert policy._return_next_dig_event_seen is True
    assert policy._completed_transition_count == 6
    assert policy._cycle_index == 11
    assert policy._skill_name == "return"
    assert policy._switch_reason == "before"


def test_return_transition_completion_apply_facade_delegates_skill_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy._skill_name = "return"
    policy._switch_reason = "before"
    calls: list[tuple[str, str]] = []

    def set_skill(skill_name: str, reason: str) -> None:
        calls.append((skill_name, reason))

    monkeypatch.setattr(policy, "_set_skill", set_skill)

    waiting = ReturnToDigTransitionCompletion(should_transition=False)
    assert policy._apply_return_to_dig_transition_completion(waiting) is False
    assert calls == []
    assert policy._skill_name == "return"
    assert policy._switch_reason == "before"

    completion = ReturnToDigTransitionCompletion(
        should_transition=True,
        next_skill="pre_dig_align",
        switch_reason="return_to_pre_dig_align_next_dig_entry_ready",
    )
    assert policy._apply_return_to_dig_transition_completion(completion) is True
    assert calls == [
        ("pre_dig_align", "return_to_pre_dig_align_next_dig_entry_ready")
    ]


def test_set_return_or_direct_handoff_can_same_frame_switch_to_pre_dig_align(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy._skill_name = "dump"
    policy.return_target_planner_enabled = True
    policy.return_to_dig_start_envelope_direct_handoff_enabled = True

    monkeypatch.setattr(policy, "_ensure_return_target_plan_for_cycle", lambda _obs: None)
    monkeypatch.setattr(policy, "_return_to_dig_handoff_ready", lambda _obs: True)
    monkeypatch.setattr(
        policy,
        "_return_to_dig_direct_handoff_ready",
        lambda _obs, *, handoff_ready=None: bool(handoff_ready),
    )
    monkeypatch.setattr(policy, "_should_pre_dig_align_before_dig", lambda: True)

    policy._set_return_or_direct_handoff(
        _obs(),
        reason="dump_to_return_dump_complete_boundary",
    )

    assert policy._skill_name == "pre_dig_align"
    assert policy._switch_reason == "return_to_pre_dig_align_start_envelope_ready"
    assert policy._cycle_index == 1
    assert policy._completed_transition_count == 1


def test_return_transition_facade_applies_completion_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy._skill_name = "return"
    calls: list[
        tuple[
            str,
            ReturnToDigTransitionCompletionFacts,
            ReturnToDigTransitionCompletionConfig,
        ]
    ] = []
    request_calls: list[dict[str, object]] = []

    def completion_request(
        **kwargs: object,
    ) -> ReturnToDigTransitionCompletionRequest:
        request_calls.append(dict(kwargs))
        return ReturnToDigTransitionCompletionRequest(
            facts=ReturnToDigTransitionCompletionFacts(
                pre_dig_align_before_dig=bool(kwargs["pre_dig_align_before_dig"]),
            ),
            config=ReturnToDigTransitionCompletionConfig(
                pre_dig_align_skill_name=str(kwargs["pre_dig_align_skill_name"]),
            ),
        )

    def transition_completion(
        outcome: Any,
        facts: ReturnToDigTransitionCompletionFacts,
        config: ReturnToDigTransitionCompletionConfig,
    ) -> ReturnToDigTransitionCompletion:
        calls.append((str(outcome.action), facts, config))
        return ReturnToDigTransitionCompletion(
            should_transition=True,
            next_skill="pre_dig_align",
            switch_reason="return_to_pre_dig_align_next_dig_entry_ready",
        )

    def pre_dig_align_after_cycle_update() -> bool:
        assert policy._cycle_index == 1
        assert policy._completed_transition_count == 1
        return True

    monkeypatch.setattr(policy, "_return_to_dig_handoff_ready", lambda _obs: True)
    monkeypatch.setattr(
        policy,
        "_return_to_dig_direct_handoff_ready",
        lambda _obs, *, handoff_ready=None: False,
    )
    monkeypatch.setattr(
        policy,
        "_return_to_dig_shallow_guard_ready",
        lambda *, obs, boundary_event: False,
    )
    monkeypatch.setattr(
        policy,
        "_should_pre_dig_align_before_dig",
        pre_dig_align_after_cycle_update,
    )
    monkeypatch.setattr(
        policy.return_transition_service,
        "completion_request",
        completion_request,
    )
    monkeypatch.setattr(
        policy.return_transition_service,
        "transition_completion",
        transition_completion,
    )

    policy._maybe_switch_skill(
        obs=_obs(),
        boundary_event=type("_Boundary", (), {"qualified_dig_start": True})(),
    )

    assert request_calls == [
        {
            "pre_dig_align_before_dig": True,
            "pre_dig_align_skill_name": "pre_dig_align",
        }
    ]
    assert calls == [
        (
            "next_dig_event",
            ReturnToDigTransitionCompletionFacts(pre_dig_align_before_dig=True),
            ReturnToDigTransitionCompletionConfig(
                pre_dig_align_skill_name="pre_dig_align",
            ),
        )
    ]
    assert policy._skill_name == "pre_dig_align"
    assert policy._switch_reason == "return_to_pre_dig_align_next_dig_entry_ready"
    assert policy._cycle_index == 1
    assert policy._completed_transition_count == 1


def test_return_transition_facade_delegates_completion_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy._skill_name = "return"
    completion = ReturnToDigTransitionCompletion(
        should_transition=True,
        next_skill="pre_dig_align",
        switch_reason="return_to_pre_dig_align_next_dig_entry_ready",
    )
    applied: list[ReturnToDigTransitionCompletion] = []

    def transition_completion(
        outcome: Any,
        facts: ReturnToDigTransitionCompletionFacts,
        config: ReturnToDigTransitionCompletionConfig,
    ) -> ReturnToDigTransitionCompletion:
        assert str(outcome.action) == "next_dig_event"
        assert facts == ReturnToDigTransitionCompletionFacts(
            pre_dig_align_before_dig=True
        )
        assert config == ReturnToDigTransitionCompletionConfig(
            pre_dig_align_skill_name="pre_dig_align",
        )
        return completion

    def apply_completion(state: ReturnToDigTransitionCompletion) -> bool:
        applied.append(state)
        return True

    def pre_dig_align_after_cycle_update() -> bool:
        assert policy._cycle_index == 1
        assert policy._completed_transition_count == 1
        return True

    monkeypatch.setattr(policy, "_return_to_dig_handoff_ready", lambda _obs: True)
    monkeypatch.setattr(
        policy,
        "_return_to_dig_direct_handoff_ready",
        lambda _obs, *, handoff_ready=None: False,
    )
    monkeypatch.setattr(
        policy,
        "_return_to_dig_shallow_guard_ready",
        lambda *, obs, boundary_event: False,
    )
    monkeypatch.setattr(
        policy,
        "_should_pre_dig_align_before_dig",
        pre_dig_align_after_cycle_update,
    )
    monkeypatch.setattr(
        policy.return_transition_service,
        "transition_completion",
        transition_completion,
    )
    monkeypatch.setattr(
        policy,
        "_apply_return_to_dig_transition_completion",
        apply_completion,
    )

    policy._maybe_switch_skill(
        obs=_obs(),
        boundary_event=type("_Boundary", (), {"qualified_dig_start": True})(),
    )

    assert applied == [completion]


def test_return_next_dig_event_skips_direct_and_shallow_gates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy._skill_name = "return"
    calls: list[str] = []

    def handoff_ready(_obs: dict[str, np.ndarray]) -> bool:
        calls.append("handoff")
        return True

    def fail_direct(
        _obs: dict[str, np.ndarray],
        *,
        handoff_ready: bool | None = None,
    ) -> bool:
        raise AssertionError("direct handoff must not run after next-dig event")

    def fail_shallow(
        *,
        obs: dict[str, np.ndarray],
        boundary_event: object | None,
    ) -> bool:
        raise AssertionError("shallow guard must not run after next-dig event")

    monkeypatch.setattr(policy, "_return_to_dig_handoff_ready", handoff_ready)
    monkeypatch.setattr(
        policy,
        "_return_to_dig_direct_handoff_ready",
        fail_direct,
    )
    monkeypatch.setattr(policy, "_return_to_dig_shallow_guard_ready", fail_shallow)
    monkeypatch.setattr(policy, "_should_pre_dig_align_before_dig", lambda: False)

    policy._maybe_switch_skill(
        obs=_obs(),
        boundary_event=type("_Boundary", (), {"qualified_dig_start": True})(),
    )

    assert calls == ["handoff"]
    assert policy._skill_name == "dig"
    assert policy._switch_reason == "return_to_dig_next_dig_entry_ready"
    assert policy._cycle_index == 1
    assert policy._completed_transition_count == 1


def _assert_facade_matches_resolver(
    policy: PrimitivePlannerACTPolicy,
    expected: tuple[float, float] | None,
) -> None:
    resolution = policy.return_entry_target_resolver.resolve(
        build_return_next_dig_entry_target_facts_from_runtime(
            cycle_index=policy._cycle_index,
            pending_dig_cut_cycle_id=policy._pending_dig_cut_cycle_id,
            pending_dig_cut_raw_fields=policy._pending_dig_cut_raw_fields,
            active_corridor=policy._coverage_active_corridor(),
        )
    )
    assert resolution.entry_target == expected
    assert policy._return_to_dig_entry_target() == expected


def _assert_entry_error_facade_matches_service(
    policy: PrimitivePlannerACTPolicy,
    obs: dict[str, np.ndarray],
    *,
    expected: float | None,
) -> None:
    facts = ReturnToDigEntryErrorFacts(
        entry_target=policy._return_to_dig_entry_target(),
        bucket_dig_area_pose=policy._bucket_dig_area_pose(obs),
    )
    service_error = policy.return_handoff_gate.entry_error(facts)
    facade_error = policy._return_to_dig_entry_error_for_obs(obs)
    if expected is None:
        assert np.isnan(service_error)
        assert np.isnan(facade_error)
    else:
        assert service_error == pytest.approx(expected)
        assert facade_error == pytest.approx(expected)


def _assert_pre_dig_align_entry_error_facade_matches_service(
    policy: PrimitivePlannerACTPolicy,
    obs: dict[str, np.ndarray],
    *,
    expected: float | None,
) -> None:
    corridor = policy._coverage_active_corridor()
    active_entry_xz = (
        None
        if corridor is None
        else (float(corridor.entry_x_m), float(corridor.entry_z_m))
    )
    service_error = (
        policy.dig_start_alignment_service.entry_error_from_observation_view(
            view=policy._make_snapshot(obs).view,
            active_corridor_entry_xz=active_entry_xz,
        )
    )
    facade_error = policy._pre_dig_align_entry_error(obs)
    if expected is None:
        assert np.isnan(service_error)
        assert np.isnan(facade_error)
    else:
        assert service_error == pytest.approx(expected)
        assert facade_error == pytest.approx(expected)


def _set_active_corridor(
    policy: PrimitivePlannerACTPolicy,
    *,
    entry: tuple[float, float],
    corridor_id: int = 7,
    cell_id: int = -1,
) -> None:
    corridor = CoverageCorridorState(
        corridor_id=int(corridor_id),
        entry_x_m=float(entry[0]),
        entry_z_m=float(entry[1]),
        exit_x_m=float(entry[0]) - 1.0,
        exit_z_m=float(entry[1]),
        cell_id=int(cell_id),
    )
    policy._coverage_corridors = [corridor]
    policy._coverage_active_corridor_id = int(corridor.corridor_id)


def _obs(
    *,
    bucket_pose: tuple[float, float, float] = (0.0, 0.0, 0.0),
    bucket_tip_pose: tuple[float, float, float] | None = None,
    deposited_mass: float = 0.0,
) -> dict[str, np.ndarray]:
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX] = float(bucket_pose[0])
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX] = float(bucket_pose[1])
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX] = float(bucket_pose[2])
    env_state[ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX] = float(deposited_mass)
    if bucket_tip_pose is not None:
        env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX] = float(bucket_tip_pose[0])
        env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX] = float(bucket_tip_pose[1])
        env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX] = float(bucket_tip_pose[2])
    return {
        "env_state": env_state,
        "qpos": np.zeros(4, dtype=np.float32),
        "qvel": np.zeros(4, dtype=np.float32),
    }


def _make_policy() -> PrimitivePlannerACTPolicy:
    return PrimitivePlannerACTPolicy(
        dig_policy=_ConstantPolicy(0.0),
        carry_policy=_ConstantPolicy(1.0),
        dump_policy=_ConstantPolicy(2.0),
        return_policy=_ConstantPolicy(3.0),
        boundary_detector=_FakeBoundaryDetector(),
    )


class _ConstantPolicy(Policy):
    def __init__(self, value: float) -> None:
        self.value = float(value)

    def predict(self, obs: dict) -> np.ndarray:
        action = np.zeros(4, dtype=np.float32)
        action[0] = self.value
        return action


class _FakeBoundaryDetector:
    def __init__(self) -> None:
        self.config = type(
            "_FakeBoundaryConfig",
            (),
            {"boundary_profile": "legacy"},
        )()

    def reset(self) -> None:
        pass

    def update(self, obs: dict, action: np.ndarray | None = None) -> Any:
        return None


class _SpyBoundaryDetector:
    def __init__(self) -> None:
        self.config = type(
            "_SpyBoundaryConfig",
            (),
            {"boundary_profile": "legacy"},
        )()
        self.calls: list[dict[str, Any]] = []

    def reset(self) -> None:
        pass

    def update(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return None


class _FailingPendingActivationService:
    def pending_activation(self, _facts: object) -> object:
        raise AssertionError("stale pending plan must not reach activation service")


class _SpyPendingActivationService:
    def __init__(self) -> None:
        self.calls: list[PendingReturnTargetActivationFacts] = []

    def pending_activation(self, facts: PendingReturnTargetActivationFacts) -> object:
        self.calls.append(facts)
        return ReturnTargetPlanService.pending_activation(facts)
