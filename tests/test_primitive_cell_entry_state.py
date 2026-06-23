from __future__ import annotations

from typing import Any

import numpy as np

from testbed.planner.cell_entry import CELL_ENTRY_TOKEN_DIM
from testbed.planner.primitive_cell_entry_state import (
    PrimitiveCellEntryCompatibilityRuntimeState,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def test_cell_entry_compatibility_runtime_state_fresh_matches_reset_defaults() -> None:
    state = PrimitiveCellEntryCompatibilityRuntimeState.fresh()

    assert state.goal is None
    assert state.goal_cycle_id == -1
    assert state.audit is None
    assert state.tokens.dtype == np.float32
    assert state.tokens.shape == (CELL_ENTRY_TOKEN_DIM,)
    assert np.all(state.tokens == 0.0)
    assert state.seen_cell_id == -1
    assert state.trace == []


def test_cell_entry_compatibility_runtime_state_owns_trace_and_token_copy() -> None:
    state = PrimitiveCellEntryCompatibilityRuntimeState.fresh()
    cached_tokens = np.arange(CELL_ENTRY_TOKEN_DIM, dtype=np.float32)

    state.tokens = cached_tokens
    state.trace.append({"cycle_id": 3})
    copied_tokens = state.copy_tokens()
    copied_tokens[0] = 99.0

    assert state.tokens is cached_tokens
    assert state.tokens[0] == 0.0
    assert copied_tokens is not state.tokens
    assert copied_tokens[0] == 99.0
    assert state.trace == [{"cycle_id": 3}]

    other = PrimitiveCellEntryCompatibilityRuntimeState.fresh()
    assert other.trace == []
    assert other.tokens[0] == 0.0
    assert other.tokens is not state.tokens


def test_policy_legacy_cell_entry_fields_are_backed_by_one_state_owner() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    state = policy._primitive_cell_entry_compatibility_runtime_state()
    goal = object()
    audit = object()
    tokens = np.ones(CELL_ENTRY_TOKEN_DIM, dtype=np.float32)
    trace = [{"cycle_id": 1}]

    policy._cell_entry_goal = goal
    policy._cell_entry_goal_cycle_id = 7
    policy._cell_entry_audit = audit
    policy._cell_entry_tokens = tokens
    policy._cell_entry_seen_cell_id = 4
    policy._cell_entry_trace = trace

    assert policy._primitive_cell_entry_compatibility_runtime_state() is state
    assert state.goal is goal
    assert state.goal_cycle_id == 7
    assert state.audit is audit
    assert state.tokens is tokens
    assert state.seen_cell_id == 4
    assert state.trace is trace
    assert policy._cell_entry_goal is goal
    assert policy._cell_entry_goal_cycle_id == 7
    assert policy._cell_entry_audit is audit
    assert policy._cell_entry_tokens is tokens
    assert policy._cell_entry_seen_cell_id == 4
    assert policy._cell_entry_trace is trace


def test_policy_reset_application_replaces_cell_entry_state_owner() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    old_state = policy._primitive_cell_entry_compatibility_runtime_state()
    old_state.goal_cycle_id = 9
    reset_state = PrimitiveCellEntryCompatibilityRuntimeState.fresh()

    class _ResetState:
        def as_policy_field_updates(self) -> dict[str, Any]:
            return {"_cell_entry_state": reset_state}

    policy._apply_reset_lifecycle_state(_ResetState())
    policy._cell_entry_goal_cycle_id = 2
    policy._cell_entry_trace.append({"cycle_id": 2})

    assert policy._primitive_cell_entry_compatibility_runtime_state() is reset_state
    assert policy._primitive_cell_entry_compatibility_runtime_state() is not old_state
    assert reset_state.goal_cycle_id == 2
    assert reset_state.trace == [{"cycle_id": 2}]
    assert old_state.goal_cycle_id == 9
    assert old_state.trace == []
