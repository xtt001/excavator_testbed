from __future__ import annotations

from typing import Any

import numpy as np

from testbed.planner.cell_entry import (
    CELL_ENTRY_TOKEN_DIM,
    CellEntryGoal,
    EntryEnvelope,
    PlannerDecisionAudit,
)
from testbed.planner.primitive_cell_entry_state import (
    PrimitiveCellEntryCompatibilityRuntimeState,
    PrimitiveCellEntryReportConfig,
    PrimitiveCellEntryReportStatus,
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


def test_cell_entry_debug_fields_match_policy_facade_for_fresh_state() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    state = policy._primitive_cell_entry_compatibility_runtime_state()

    fields = state.debug_fields()

    assert fields == policy._debug_report_cell_entry_fields()
    assert fields["cell_entry_selected_cell_id"] == -1
    assert fields["cell_entry_selected_long_index"] == -1
    assert fields["cell_entry_selected_short_index"] == -1
    assert np.isnan(fields["cell_entry_planned_entry_x_m"])
    assert np.isnan(fields["cell_entry_planned_entry_y_m"])
    assert np.isnan(fields["cell_entry_planned_entry_z_m"])
    assert fields["cell_entry_planner_ok"] is False
    assert fields["cell_entry_audit_reason_code"] == -1
    assert fields["cell_entry_audit_reason"] == ""
    assert fields["cell_entry_audit_risk_flags"] == 0
    assert fields["cell_entry_inside_entry_envelope"] is False
    assert np.isnan(fields["cell_entry_distance_to_entry_envelope_m"])
    assert fields["cell_entry_seen_cell_id"] == -1


def test_cell_entry_debug_fields_match_policy_facade_for_populated_state() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    state = policy._primitive_cell_entry_compatibility_runtime_state()
    state.goal = CellEntryGoal(
        cycle_id=3,
        selected_cell_id=4,
        selected_long_index=1,
        selected_short_index=2,
        planned_entry_x_m=1.25,
        planned_entry_y_m=2.5,
        planned_entry_z_m=-0.75,
        planned_bite_x_m=3.0,
        planned_bite_y_m=4.0,
        planned_bite_z_m=5.0,
        entry_envelope=EntryEnvelope(
            x_min_m=0.0,
            x_max_m=1.0,
            y_min_m=2.0,
            y_max_m=3.0,
            z_min_m=-1.0,
            z_max_m=0.0,
        ),
    )
    state.audit = PlannerDecisionAudit(
        cycle_id=3,
        planner_ok=True,
        risk_flags=5,
        reason_code=9,
        reason="inside_entry_envelope",
        inside_entry_envelope=True,
        distance_to_entry_envelope_m=0.125,
        entry_delta_x_m=0.1,
        entry_delta_y_m=0.2,
        entry_delta_z_m=0.3,
        target_cell_match=True,
    )
    state.seen_cell_id = 6

    fields = state.debug_fields()

    assert fields == policy._debug_report_cell_entry_fields()
    assert fields == {
        "cell_entry_selected_cell_id": 4,
        "cell_entry_selected_long_index": 1,
        "cell_entry_selected_short_index": 2,
        "cell_entry_planned_entry_x_m": 1.25,
        "cell_entry_planned_entry_y_m": 2.5,
        "cell_entry_planned_entry_z_m": -0.75,
        "cell_entry_planner_ok": True,
        "cell_entry_audit_reason_code": 9,
        "cell_entry_audit_reason": "inside_entry_envelope",
        "cell_entry_audit_risk_flags": 5,
        "cell_entry_inside_entry_envelope": True,
        "cell_entry_distance_to_entry_envelope_m": 0.125,
        "cell_entry_seen_cell_id": 6,
    }


def test_cell_entry_report_status_projects_summary_and_trace_defaults() -> None:
    state = PrimitiveCellEntryCompatibilityRuntimeState.fresh()

    status = state.to_report_status(PrimitiveCellEntryReportConfig(enabled=False))

    assert status.enabled is False
    assert status.trace_count == 0
    assert status.trace == []
    assert status.trace_for_planner_trace() == []
    assert status.debug_fields() == state.debug_fields()


def test_cell_entry_report_status_projects_populated_trace_with_shallow_copy() -> None:
    state = PrimitiveCellEntryCompatibilityRuntimeState.fresh()
    event = {"cycle_id": 3, "reason": "compatibility_only"}
    state.trace.append(event)
    state.seen_cell_id = 8

    status = state.to_report_status(PrimitiveCellEntryReportConfig(enabled=True))
    trace_payload = status.trace_for_planner_trace()

    assert status.enabled is True
    assert status.trace == [event]
    assert status.selected_cell_id == -1
    assert status.selected_long_index == -1
    assert status.selected_short_index == -1
    assert np.isnan(status.planned_entry_x_m)
    assert np.isnan(status.planned_entry_y_m)
    assert np.isnan(status.planned_entry_z_m)
    assert status.planner_ok is False
    assert status.audit_reason_code == -1
    assert status.audit_reason == ""
    assert status.audit_risk_flags == 0
    assert status.inside_entry_envelope is False
    assert np.isnan(status.distance_to_entry_envelope_m)
    assert status.seen_cell_id == 8
    assert status.trace is not state.trace
    assert trace_payload is not status.trace
    assert trace_payload[0] is event


def test_policy_cell_entry_debug_facade_delegates_to_report_status() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    policy.cell_entry_enabled = True
    state = policy._primitive_cell_entry_compatibility_runtime_state()
    state.seen_cell_id = 5

    assert policy._debug_report_cell_entry_fields() == (
        state.to_report_status(policy._cell_entry_report_config()).debug_fields()
    )
    assert policy._cell_entry_report_status().enabled is False
