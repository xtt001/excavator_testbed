from __future__ import annotations

import numpy as np

from testbed.planner.cell_entry import (
    CELL_ENTRY_TOKEN_DIM,
    CellEntryGoal,
    EntryEnvelope,
    PlannerDecisionAudit,
)
from testbed.planner.primitive.compatibility.cell_entry import (
    PrimitiveCellEntryCompatibilityRuntimeState,
    PrimitiveCellEntryReportConfig,
    PrimitiveCellEntryReportStatus,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy
from tests.primitive_policy_test_helpers import make_policy_shell_for_private_weld_tests


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


def test_policy_no_longer_exposes_private_cell_entry_runtime_facades() -> None:
    removed_names = {
        "_primitive_cell_entry_compatibility_runtime_state",
        "_cell_entry_goal",
        "_cell_entry_goal_cycle_id",
        "_cell_entry_audit",
        "_cell_entry_tokens",
        "_cell_entry_seen_cell_id",
        "_cell_entry_trace",
    }

    assert removed_names.isdisjoint(PrimitivePlannerACTPolicy.__dict__)


def test_cell_entry_debug_fields_match_policy_facade_for_fresh_state() -> None:
    policy = make_policy_shell_for_private_weld_tests()
    state = PrimitiveCellEntryCompatibilityRuntimeState.fresh()

    fields = state.debug_fields()

    assert fields == policy._primitive_report_composition_runtime().report_runtime().debug_report_cell_entry_fields()
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


def test_policy_cell_entry_debug_facade_ignores_removed_runtime_state() -> None:
    policy = make_policy_shell_for_private_weld_tests()
    state = PrimitiveCellEntryCompatibilityRuntimeState.fresh()
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
    policy.__dict__["_cell_entry_state"] = state

    fields = policy._primitive_report_composition_runtime().report_runtime().debug_report_cell_entry_fields()

    assert fields["cell_entry_selected_cell_id"] == -1
    assert fields["cell_entry_selected_long_index"] == -1
    assert fields["cell_entry_selected_short_index"] == -1
    assert fields["cell_entry_planner_ok"] is False
    assert fields["cell_entry_audit_reason_code"] == -1
    assert fields["cell_entry_audit_reason"] == ""
    assert fields["cell_entry_audit_risk_flags"] == 0
    assert fields["cell_entry_inside_entry_envelope"] is False
    assert fields["cell_entry_seen_cell_id"] == -1
    assert np.isnan(fields["cell_entry_planned_entry_x_m"])
    assert np.isnan(fields["cell_entry_planned_entry_y_m"])
    assert np.isnan(fields["cell_entry_planned_entry_z_m"])
    assert np.isnan(fields["cell_entry_distance_to_entry_envelope_m"])


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
    policy = make_policy_shell_for_private_weld_tests()
    policy.cell_entry_enabled = True
    state = PrimitiveCellEntryCompatibilityRuntimeState.fresh()
    state.seen_cell_id = 5
    policy.__dict__["_cell_entry_state"] = state

    assert policy._primitive_report_composition_runtime().report_runtime().debug_report_cell_entry_fields() == (
        PrimitiveCellEntryCompatibilityRuntimeState.fresh()
        .to_report_status(
            policy._primitive_report_composition_runtime().cell_entry_report_config()
        )
        .debug_fields()
    )
    assert (
        policy._primitive_report_composition_runtime().cell_entry_report_status().enabled
        is False
    )
