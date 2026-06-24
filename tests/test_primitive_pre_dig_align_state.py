from __future__ import annotations

import numpy as np

from testbed.planner.primitive.compatibility.pre_dig_align import (
    PrimitivePreDigAlignCompatibilityRuntimeState,
    PrimitivePreDigAlignReportConfig,
)
from testbed.planner.primitive.execution.pre_dig_align import (
    PrimitivePreDigAlignRuntimeState,
)
from testbed.planner.primitive.execution.reset_lifecycle import (
    PrimitiveResetLifecyclePorts,
    PrimitiveResetLifecycleService,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy
from tests.primitive_policy_test_helpers import make_policy_shell_for_private_weld_tests


def test_pre_dig_align_compatibility_runtime_state_fresh_matches_reset_defaults() -> None:
    state = PrimitivePreDigAlignCompatibilityRuntimeState.fresh(action_dim=4)

    assert state.step_count == 0
    assert state.hold_count == 0
    assert state.timeout_count == 0
    assert state.completed_count == 0
    assert state.replan_count == 0
    assert state.target_qpos.dtype == np.float32
    assert state.target_qpos.shape == (4,)
    assert np.all(state.target_qpos == 0.0)
    assert state.error.dtype == np.float32
    assert state.error.shape == (4,)
    assert np.all(state.error == 0.0)
    assert np.isnan(state.entry_error_m)
    assert state.start_envelope_ready is False
    assert state.entry_close_handoff_ready is False
    assert state.entry_intent_handoff_ready is False
    assert state.timeout_handoff_reason == ""
    assert np.isnan(state.surface_depth_m)
    assert state.surface_guard_triggered is False
    assert state.surface_guard_count == 0


def test_pre_dig_align_compatibility_runtime_state_uses_fresh_arrays() -> None:
    state = PrimitivePreDigAlignCompatibilityRuntimeState.fresh(action_dim=4)
    other = PrimitivePreDigAlignCompatibilityRuntimeState.fresh(action_dim=4)

    state.target_qpos[0] = 7.0
    state.error[1] = -3.0

    assert other.target_qpos[0] == 0.0
    assert other.error[1] == 0.0
    assert other.target_qpos is not state.target_qpos
    assert other.error is not state.error


def test_policy_no_longer_exposes_private_pre_dig_align_runtime_facades() -> None:
    removed_names = {
        "_primitive_pre_dig_align_compatibility_runtime_state",
        "_pre_dig_align_step_count",
        "_pre_dig_align_hold_count",
        "_pre_dig_align_timeout_count",
        "_pre_dig_align_completed_count",
        "_pre_dig_align_replan_count",
        "_pre_dig_align_target_qpos",
        "_pre_dig_align_error",
        "_pre_dig_align_entry_error_m",
        "_pre_dig_align_start_envelope_ready",
        "_pre_dig_align_entry_close_handoff_ready",
        "_pre_dig_align_entry_intent_handoff_ready",
        "_pre_dig_align_timeout_handoff_reason",
        "_pre_dig_align_surface_depth_m",
        "_pre_dig_align_surface_guard_triggered",
        "_pre_dig_align_surface_guard_count",
    }

    assert removed_names.isdisjoint(PrimitivePlannerACTPolicy.__dict__)


def test_reset_lifecycle_no_longer_emits_pre_dig_align_runtime_fields() -> None:
    ports = PrimitiveResetLifecyclePorts(
        all_policies=lambda: [],
        reset_boundary_detector=lambda: None,
        bootstrap_end_mode=lambda: "dig",
        bootstrap_policy_available=lambda: False,
        scripted_bootstrap_enabled=lambda: False,
        should_pre_dig_align_before_dig=lambda: False,
        action_dim=4,
    )

    reset_state = PrimitiveResetLifecycleService(ports).reset()
    updates = reset_state.as_policy_field_updates()
    removed_field_names = {
        "pre_dig_align_state",
        "pre_dig_align_step_count",
        "pre_dig_align_hold_count",
        "pre_dig_align_timeout_count",
        "pre_dig_align_completed_count",
        "pre_dig_align_replan_count",
        "pre_dig_align_target_qpos",
        "pre_dig_align_error",
        "pre_dig_align_entry_error_m",
        "pre_dig_align_start_envelope_ready",
        "pre_dig_align_entry_close_handoff_ready",
        "pre_dig_align_entry_intent_handoff_ready",
        "pre_dig_align_timeout_handoff_reason",
        "pre_dig_align_surface_depth_m",
        "pre_dig_align_surface_guard_triggered",
        "pre_dig_align_surface_guard_count",
    }
    removed_update_names = {f"_{name}" for name in removed_field_names}

    assert removed_field_names.isdisjoint(reset_state.__dataclass_fields__)
    assert removed_update_names.isdisjoint(updates)


def _report_config(**overrides: Any) -> PrimitivePreDigAlignReportConfig:
    values: dict[str, Any] = {
        "enabled": True,
        "first_dig_only": False,
        "replan_after_failed_dig": True,
        "entry_intent_controlled_dims": np.asarray([True, False, True, False]),
        "surface_guard_enabled": True,
        "active_for_next_dig": True,
        "first_dig_entry_close_handoff": True,
        "entry_intent_handoff_enabled": True,
        "first_dig_entry_close_handoff_qvel_abs_max": None,
        "controlled_dims": np.asarray([True, True, False, False]),
        "bucket_target_qpos": None,
    }
    values.update(overrides)
    return PrimitivePreDigAlignReportConfig(**values)


def test_pre_dig_align_state_projects_default_report_status() -> None:
    state = PrimitivePreDigAlignCompatibilityRuntimeState.fresh(action_dim=4)

    status = state.to_report_status(_report_config(active_for_next_dig=False))

    assert status.enabled is True
    assert status.first_dig_only is False
    assert status.replan_after_failed_dig is True
    assert status.entry_intent_controlled_dims == [1, 0, 1, 0]
    assert status.surface_guard_enabled is True
    assert np.isnan(status.surface_depth_m)
    assert status.surface_guard_triggered is False
    assert status.surface_guard_count == 0
    assert status.active_for_next_dig is False
    assert status.step_count == 0
    assert status.hold_count == 0
    assert status.timeout_count == 0
    assert status.completed_count == 0
    assert status.replan_count == 0
    assert status.target_qpos == [0.0, 0.0, 0.0, 0.0]
    assert status.error == [0.0, 0.0, 0.0, 0.0]
    assert np.isnan(status.entry_error_m)
    assert status.start_envelope_ready is False
    assert status.first_dig_entry_close_handoff is True
    assert status.entry_close_handoff_ready is False
    assert status.entry_intent_handoff_enabled is True
    assert status.entry_intent_handoff_ready is False
    assert np.isnan(status.first_dig_entry_close_handoff_qvel_abs_max)
    assert status.controlled_dims == [1, 1, 0, 0]
    assert np.isnan(status.bucket_target_qpos)


def test_pre_dig_align_state_projects_populated_debug_fields() -> None:
    state = PrimitivePreDigAlignCompatibilityRuntimeState.fresh(action_dim=4)
    state.step_count = 11
    state.hold_count = 12
    state.timeout_count = 13
    state.completed_count = 14
    state.replan_count = 15
    state.target_qpos = np.asarray([1.0, 2.0, 3.0, 4.0], dtype=np.float32)
    state.error = np.asarray([-1.0, -2.0, -3.0, -4.0], dtype=np.float32)
    state.entry_error_m = 0.25
    state.start_envelope_ready = True
    state.entry_close_handoff_ready = True
    state.entry_intent_handoff_ready = True
    state.timeout_handoff_reason = "entry_close"
    state.surface_depth_m = -0.05
    state.surface_guard_triggered = True
    state.surface_guard_count = 16

    fields = state.to_report_status(
        _report_config(
            entry_intent_controlled_dims=None,
            first_dig_entry_close_handoff_qvel_abs_max=0.5,
            bucket_target_qpos=-0.2,
        )
    ).debug_fields()

    assert fields["pre_dig_align_enabled"] is True
    assert fields["pre_dig_align_entry_intent_controlled_dims"] is None
    assert fields["pre_dig_align_surface_depth_m"] == -0.05
    assert fields["pre_dig_align_surface_guard_triggered"] is True
    assert fields["pre_dig_align_surface_guard_count"] == 16
    assert fields["pre_dig_align_active_for_next_dig"] is True
    assert fields["pre_dig_align_step_count"] == 11
    assert fields["pre_dig_align_hold_count"] == 12
    assert fields["pre_dig_align_timeout_count"] == 13
    assert fields["pre_dig_align_completed_count"] == 14
    assert fields["pre_dig_align_replan_count"] == 15
    assert fields["pre_dig_align_target_qpos"] == [1.0, 2.0, 3.0, 4.0]
    assert fields["pre_dig_align_error"] == [-1.0, -2.0, -3.0, -4.0]
    assert fields["pre_dig_align_entry_error_m"] == 0.25
    assert fields["pre_dig_align_start_envelope_ready"] is True
    assert fields["pre_dig_align_first_dig_entry_close_handoff"] is True
    assert fields["pre_dig_align_entry_close_handoff_ready"] is True
    assert fields["pre_dig_align_entry_intent_handoff_enabled"] is True
    assert fields["pre_dig_align_entry_intent_handoff_ready"] is True
    assert fields["pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max"] == 0.5
    assert fields["pre_dig_align_controlled_dims"] == [1, 1, 0, 0]
    assert fields["pre_dig_align_bucket_target_qpos"] == -0.2


def test_policy_pre_dig_align_debug_facade_delegates_to_state_report_status() -> None:
    policy = make_policy_shell_for_private_weld_tests()
    policy.action_dim = 4
    policy.pre_dig_align_enabled = True
    policy.pre_dig_align_first_dig_only = True
    policy.pre_dig_align_replan_after_failed_dig = False
    policy.pre_dig_align_entry_intent_controlled_dims = np.asarray(
        [False, True, False, True],
        dtype=bool,
    )
    policy.pre_dig_align_surface_guard_enabled = True
    policy.pre_dig_align_first_dig_entry_close_handoff = True
    policy.pre_dig_align_entry_intent_handoff_enabled = False
    policy.pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max = None
    policy.pre_dig_align_controlled_dims = np.asarray(
        [True, False, True, False],
        dtype=bool,
    )
    policy.pre_dig_align_bucket_target_qpos = None
    policy.pre_dig_align_kp = 2.0
    policy.pre_dig_align_kd = 0.25
    policy.pre_dig_align_action_clip = np.asarray(
        [0.55, 0.35, 0.35, 0.35],
        dtype=np.float32,
    )
    policy.pre_dig_align_action_signs = np.asarray(
        [1.0, -1.0, 1.0, 1.0],
        dtype=np.float32,
    )
    policy.pre_dig_align_qpos_tolerance = np.asarray(
        [0.025, 0.04, 0.05, 0.06],
        dtype=np.float32,
    )
    policy.pre_dig_align_qvel_abs_max = 0.12
    policy.pre_dig_align_hold_steps = 3
    policy.pre_dig_align_max_steps = 140
    policy.pre_dig_align_max_entry_error_m = None
    policy.pre_dig_align_timeout_accept_entry_error_m = None
    policy.pre_dig_align_timeout_replan_entry_error_m = None
    policy.pre_dig_align_start_envelope_enabled = False
    policy.pre_dig_align_start_envelope_max_entry_error_m = 0.65
    policy.pre_dig_align_surface_guard_max_penetration_m = 0.005
    policy.pre_dig_align_surface_guard_handoff_entry_error_m = None
    policy.pre_dig_align_surface_guard_use_contact_fallback = True
    policy.pre_dig_align_start_qpos_min = np.asarray(
        [0.45, 0.52, 0.0, 0.0],
        dtype=np.float32,
    )
    policy.pre_dig_align_start_qpos_max = np.asarray(
        [0.57, 0.78, 0.40, 0.12],
        dtype=np.float32,
    )
    policy.pre_dig_align_start_pose_min = np.asarray(
        [-0.60, -0.30, -1.50],
        dtype=np.float32,
    )
    policy.pre_dig_align_start_pose_max = np.asarray(
        [1.65, 0.25, 1.20],
        dtype=np.float32,
    )
    policy.pre_dig_align_qpos_min = np.asarray(
        [0.44, 0.50, 0.0, 0.0],
        dtype=np.float32,
    )
    policy.pre_dig_align_qpos_max = np.asarray(
        [0.56, 0.79, 0.42, 0.36],
        dtype=np.float32,
    )
    policy.pre_dig_align_qpos_from_token_coefficients = np.asarray(
        [
            [0.49761536, -0.00324577, -0.07974796],
            [0.48509995, 0.34124863, -0.02063946],
            [0.39998216, -0.50266185, 0.04142020],
            [0.21223230, -0.14153491, -0.01244724],
        ],
        dtype=np.float32,
    )
    policy._primitive_cycle_runtime_state().cycle_index = 0
    state = PrimitivePreDigAlignRuntimeState.fresh(action_dim=4)
    state.completed_count = 3
    state.timeout_count = 2
    state.replan_count = 1
    policy.__dict__["_pre_dig_align_runtime_state"] = state

    fields = policy._primitive_report_composition_runtime().report_runtime().debug_report_pre_dig_align_fields()

    assert fields["pre_dig_align_enabled"] is True
    assert fields["pre_dig_align_completed_count"] == 3
    assert fields["pre_dig_align_timeout_count"] == 2
    assert fields["pre_dig_align_replan_count"] == 1
