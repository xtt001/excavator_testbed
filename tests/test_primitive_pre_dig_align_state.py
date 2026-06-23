from __future__ import annotations

from typing import Any

import numpy as np

from testbed.planner.primitive_pre_dig_align_state import (
    PrimitivePreDigAlignCompatibilityRuntimeState,
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
        reset_cell_entry_planner=lambda: None,
        bootstrap_end_mode=lambda: "dig",
        bootstrap_policy_available=lambda: False,
        scripted_bootstrap_enabled=lambda: False,
        should_pre_dig_align_before_dig=lambda: False,
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
