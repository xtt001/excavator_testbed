from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from testbed.planner.primitive_execution_state import (
    PrimitiveExecutionRuntimeState,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def test_execution_runtime_state_fresh_matches_reset_lifecycle_defaults() -> None:
    state = PrimitiveExecutionRuntimeState.fresh(
        initial_skill_name="bootstrap",
        switch_reason="reset",
    )

    assert state.skill_name == "bootstrap"
    assert state.switch_reason == "reset"
    assert state.prev_action is None
    assert state.debug_state is None


def test_execution_runtime_state_setters_coerce_legacy_scalar_fields() -> None:
    state = PrimitiveExecutionRuntimeState.fresh(initial_skill_name="dig")
    action = np.arange(4, dtype=np.float32)
    debug_state = {"skill": "carry"}

    state.set_skill_name("carry")
    state.set_switch_reason(123)
    state.set_prev_action(action)
    state.set_debug_state(debug_state)

    assert state.skill_name == "carry"
    assert state.switch_reason == "123"
    assert state.prev_action is action
    assert state.debug_state is debug_state


def test_policy_legacy_execution_fields_are_backed_by_one_state_owner() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    state = policy._primitive_execution_runtime_state()
    action = np.ones(4, dtype=np.float32)
    debug_state = SimpleNamespace(skill_name="dump")

    policy._skill_name = "return"
    policy._switch_reason = "dump_to_return_mass_low"
    policy._prev_action = action
    policy._debug_state = debug_state

    assert policy._primitive_execution_runtime_state() is state
    assert state.skill_name == "return"
    assert state.switch_reason == "dump_to_return_mass_low"
    assert state.prev_action is action
    assert state.debug_state is debug_state
    assert policy._skill_name == "return"
    assert policy._switch_reason == "dump_to_return_mass_low"
    assert policy._prev_action is action
    assert policy._debug_state is debug_state


def test_policy_reset_application_replaces_execution_state_owner() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    old_state = policy._primitive_execution_runtime_state()
    old_state.set_skill_name("return")
    reset_state = PrimitiveExecutionRuntimeState.fresh(
        initial_skill_name="bootstrap",
        switch_reason="reset",
    )

    class _ResetState:
        def as_policy_field_updates(self):
            return {"_execution_state": reset_state}

    policy._apply_reset_lifecycle_state(_ResetState())
    policy._skill_name = "dig"
    policy._switch_reason = "bootstrap_to_dig"

    assert policy._primitive_execution_runtime_state() is reset_state
    assert policy._primitive_execution_runtime_state() is not old_state
    assert reset_state.skill_name == "dig"
    assert reset_state.switch_reason == "bootstrap_to_dig"
    assert old_state.skill_name == "return"
