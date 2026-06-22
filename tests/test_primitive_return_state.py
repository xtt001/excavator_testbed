from __future__ import annotations

from types import MethodType

import numpy as np

from testbed.planner.primitive_return_handoff import ReturnStartEnvelopeGateResult
from testbed.planner.primitive_return_state import PrimitiveReturnRuntimeState
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def test_return_runtime_state_fresh_matches_legacy_reset_defaults() -> None:
    state = PrimitiveReturnRuntimeState.fresh()

    assert state.return_step_count == 0
    assert np.isnan(state.return_to_dig_entry_error_m)
    assert state.return_to_dig_entry_close_state is True
    assert state.return_next_dig_event_seen is False
    assert state.return_to_dig_start_envelope_ready_state is True
    assert np.isnan(state.return_to_dig_start_envelope_error)
    assert state.return_to_dig_start_envelope_checks == {}


def test_return_runtime_state_fresh_does_not_alias_mutable_checks() -> None:
    first = PrimitiveReturnRuntimeState.fresh()
    second = PrimitiveReturnRuntimeState.fresh()

    first.return_to_dig_start_envelope_checks["changed"] = True

    assert second.return_to_dig_start_envelope_checks == {}
    assert (
        first.return_to_dig_start_envelope_checks
        is not second.return_to_dig_start_envelope_checks
    )


def test_policy_legacy_return_fields_are_backed_by_one_state_owner() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    state = policy._primitive_return_runtime_state()

    policy._return_step_count = 11
    policy._return_to_dig_entry_error_m = 0.25
    policy._return_to_dig_entry_close_state = False
    policy._return_next_dig_event_seen = True
    policy._return_to_dig_start_envelope_ready_state = False
    policy._return_to_dig_start_envelope_error = 0.5
    policy._return_to_dig_start_envelope_checks = {"qpos_0": {"ok": False}}

    assert policy._primitive_return_runtime_state() is state
    assert state.return_step_count == 11
    assert state.return_to_dig_entry_error_m == 0.25
    assert state.return_to_dig_entry_close_state is False
    assert state.return_next_dig_event_seen is True
    assert state.return_to_dig_start_envelope_ready_state is False
    assert state.return_to_dig_start_envelope_error == 0.5
    assert (
        policy._return_to_dig_start_envelope_checks
        is state.return_to_dig_start_envelope_checks
    )


def test_policy_reset_application_replaces_return_state_owner() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    old_state = policy._primitive_return_runtime_state()
    old_state.return_step_count = 9
    old_state.return_to_dig_start_envelope_checks["old"] = True
    reset_state = PrimitiveReturnRuntimeState.fresh()

    class _ResetState:
        def as_policy_field_updates(self):
            return {"_return_state": reset_state}

    policy._apply_reset_lifecycle_state(_ResetState())

    assert policy._primitive_return_runtime_state() is reset_state
    assert policy._primitive_return_runtime_state() is not old_state
    assert policy._return_step_count == 0
    assert policy._return_to_dig_start_envelope_checks == {}
    assert (
        policy._return_to_dig_start_envelope_checks
        is not old_state.return_to_dig_start_envelope_checks
    )


def test_policy_return_state_methods_write_state_owner() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    state = policy._primitive_return_runtime_state()

    policy._mark_return_next_dig_event_seen()
    policy._apply_return_start_envelope_gate_result(
        ReturnStartEnvelopeGateResult(
            ready=False,
            error=0.75,
            checks={"qpos_0": {"ok": False}},
        )
    )

    assert state.return_next_dig_event_seen is True
    assert state.return_to_dig_start_envelope_ready_state is False
    assert state.return_to_dig_start_envelope_error == 0.75
    assert state.return_to_dig_start_envelope_checks == {"qpos_0": {"ok": False}}


def test_skill_lifecycle_return_ports_write_return_state_owner() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    state = policy._primitive_return_runtime_state()
    state.return_step_count = 9
    state.return_next_dig_event_seen = True
    policy._skill_name = "dig"
    policy._switch_reason = ""
    policy._active_policy = MethodType(
        lambda self: type("_Policy", (), {"reset": lambda self: None})(),
        policy,
    )
    policy._clear_dig_cut_plan = MethodType(lambda self: None, policy)

    ports = policy._primitive_skill_lifecycle_ports()
    ports.set_return_step_count(0)
    ports.set_return_next_dig_event_seen(False)

    assert state.return_step_count == 0
    assert state.return_next_dig_event_seen is False


def test_return_direct_handoff_effect_ports_read_return_state_owner() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    state = policy._primitive_return_runtime_state()
    state.return_next_dig_event_seen = True
    state.return_to_dig_entry_close_state = False
    state.return_to_dig_start_envelope_ready_state = True
    policy._skill_name = "return"
    policy.return_target_planner_enabled = True
    policy.return_to_dig_start_envelope_direct_handoff_enabled = True
    policy._set_skill = MethodType(lambda self, skill, reason: None, policy)
    policy._ensure_return_target_plan_for_cycle = MethodType(lambda self, obs: None, policy)
    policy._return_to_dig_handoff_ready = MethodType(lambda self, obs: False, policy)
    policy._return_to_dig_direct_handoff_ready = MethodType(
        lambda self, obs, *, handoff_ready: False,
        policy,
    )
    policy._complete_return_transition_for_backend = MethodType(lambda self: None, policy)
    policy._next_skill_after_return_transition = MethodType(lambda self: "dig", policy)

    ports = policy._return_direct_handoff_effect_ports()

    assert ports.current_skill_name() == "return"
    assert state.return_next_dig_event_seen is True
    assert state.return_to_dig_entry_close_state is False
    assert state.return_to_dig_start_envelope_ready_state is True
