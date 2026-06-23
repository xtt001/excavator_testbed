from __future__ import annotations

from typing import Any

import numpy as np

from testbed.planner.primitive_pre_dig_align_state import (
    PrimitivePreDigAlignCompatibilityRuntimeState,
    PrimitivePreDigAlignReportConfig,
)
from testbed.planner.primitive_reset_lifecycle import (
    PrimitiveResetLifecyclePorts,
    PrimitiveResetLifecycleService,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


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


def test_policy_legacy_pre_dig_align_fields_are_backed_by_one_state_owner() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    policy.action_dim = 4
    state = policy._primitive_pre_dig_align_compatibility_runtime_state()
    target_qpos = np.arange(4, dtype=np.float32)
    error = np.arange(4, dtype=np.float32) * -1.0

    policy._pre_dig_align_step_count = 1
    policy._pre_dig_align_hold_count = 2
    policy._pre_dig_align_timeout_count = 3
    policy._pre_dig_align_completed_count = 4
    policy._pre_dig_align_replan_count = 5
    policy._pre_dig_align_target_qpos = target_qpos
    policy._pre_dig_align_error = error
    policy._pre_dig_align_entry_error_m = 0.25
    policy._pre_dig_align_start_envelope_ready = True
    policy._pre_dig_align_entry_close_handoff_ready = True
    policy._pre_dig_align_entry_intent_handoff_ready = True
    policy._pre_dig_align_timeout_handoff_reason = "entry_close"
    policy._pre_dig_align_surface_depth_m = 0.75
    policy._pre_dig_align_surface_guard_triggered = True
    policy._pre_dig_align_surface_guard_count = 6

    assert policy._primitive_pre_dig_align_compatibility_runtime_state() is state
    assert state.step_count == 1
    assert state.hold_count == 2
    assert state.timeout_count == 3
    assert state.completed_count == 4
    assert state.replan_count == 5
    assert state.target_qpos is target_qpos
    assert state.error is error
    assert state.entry_error_m == 0.25
    assert state.start_envelope_ready is True
    assert state.entry_close_handoff_ready is True
    assert state.entry_intent_handoff_ready is True
    assert state.timeout_handoff_reason == "entry_close"
    assert state.surface_depth_m == 0.75
    assert state.surface_guard_triggered is True
    assert state.surface_guard_count == 6
    assert policy._pre_dig_align_target_qpos is target_qpos
    assert policy._pre_dig_align_error is error


def test_reset_lifecycle_creates_pre_dig_align_state_owner_and_legacy_fields() -> None:
    ports = PrimitiveResetLifecyclePorts(
        all_policies=lambda: [],
        reset_boundary_detector=lambda: None,
        bootstrap_end_mode=lambda: "dig",
        bootstrap_policy_available=lambda: False,
        scripted_bootstrap_enabled=lambda: False,
        action_dim=4,
    )

    reset_state = PrimitiveResetLifecycleService(ports).reset()

    assert reset_state.pre_dig_align_state.step_count == 0
    assert reset_state.pre_dig_align_state.hold_count == 0
    assert reset_state.pre_dig_align_state.timeout_count == 0
    assert reset_state.pre_dig_align_state.completed_count == 0
    assert reset_state.pre_dig_align_state.replan_count == 0
    assert reset_state.pre_dig_align_target_qpos is reset_state.pre_dig_align_state.target_qpos
    assert reset_state.pre_dig_align_error is reset_state.pre_dig_align_state.error
    assert np.isnan(reset_state.pre_dig_align_state.entry_error_m)
    assert reset_state.pre_dig_align_start_envelope_ready is False
    assert reset_state.pre_dig_align_entry_close_handoff_ready is False
    assert reset_state.pre_dig_align_entry_intent_handoff_ready is False
    assert reset_state.pre_dig_align_timeout_handoff_reason == ""
    assert np.isnan(reset_state.pre_dig_align_state.surface_depth_m)
    assert reset_state.pre_dig_align_surface_guard_triggered is False
    assert reset_state.pre_dig_align_surface_guard_count == 0


def test_policy_reset_application_replaces_pre_dig_align_state_owner() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    policy.action_dim = 4
    old_state = policy._primitive_pre_dig_align_compatibility_runtime_state()
    old_state.step_count = 9
    reset_state = PrimitivePreDigAlignCompatibilityRuntimeState.fresh(action_dim=4)

    class _ResetState:
        def as_policy_field_updates(self) -> dict[str, Any]:
            return {"_pre_dig_align_state": reset_state}

    policy._apply_reset_lifecycle_state(_ResetState())
    policy._pre_dig_align_step_count = 2
    policy._pre_dig_align_target_qpos[0] = 5.0

    assert (
        policy._primitive_pre_dig_align_compatibility_runtime_state()
        is reset_state
    )
    assert policy._primitive_pre_dig_align_compatibility_runtime_state() is not old_state
    assert reset_state.step_count == 2
    assert reset_state.target_qpos[0] == 5.0
    assert old_state.step_count == 9
    assert old_state.target_qpos[0] == 0.0


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
    policy = object.__new__(PrimitivePlannerACTPolicy)
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
    policy._cycle_index = 0
    state = policy._primitive_pre_dig_align_compatibility_runtime_state()
    state.completed_count = 3
    state.timeout_count = 2
    state.replan_count = 1

    assert policy._debug_report_pre_dig_align_fields() == (
        state.to_report_status(policy._pre_dig_align_report_config()).debug_fields()
    )
