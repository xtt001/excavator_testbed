from __future__ import annotations

from types import MethodType
from typing import Any

from testbed.data.operator_first_v2_2 import DIG_CUT_TOKEN_CONTRACT
from testbed.planner.primitive_coverage_reports import CoverageTraceReportStatus
from testbed.planner.primitive_planner_trace import (
    PrimitivePlannerTraceBuilder,
    PrimitivePlannerTraceInputs,
)
from testbed.planner.primitive_token_state import PrimitiveTokenReportStatus
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def _inputs(**overrides: Any) -> PrimitivePlannerTraceInputs:
    token_status = PrimitiveTokenReportStatus(
        pending_dig_cut_cycle_id=4,
        pending_dig_cut_corridor_id=9,
        dig_cut_token_injected=True,
        dig_cut_planner_mode="operator_prior_coverage",
        dig_cut_prior_id="default",
        dig_cut_prior_path="/tmp/dig_prior.json",
        dig_cut_token_source="operator_prior_coverage",
        dig_cut_token_in_prior_p10_p90=True,
        dig_cut_fallback_reason="none",
    )
    coverage_status = CoverageTraceReportStatus(
        use_env_removed_depth=False,
        candidate_layout="corridor_grid",
        first_dig_strategy="preferred_corridor",
        pass_index=3,
        multi_pass_enabled=True,
        multi_pass_max_passes=4,
        multi_pass_min_remaining_depth_m=0.05,
        first_dig_preferred_corridor_id=None,
        corridors=[{"corridor_id": 7, "score": 1.25}],
        decision_trace=[{"event": "select_corridor"}],
        terminal_stop_requested=True,
        terminal_stop_reason="dig_area_depleted",
    )
    values: dict[str, Any] = {
        "cell_entry_trace": [{"cell_id": 2, "reason": "compatibility_only"}],
        "token": token_status,
        "return_target_planner_enabled": True,
        "coverage": coverage_status,
    }
    values.update(overrides)
    return PrimitivePlannerTraceInputs(**values)


def test_planner_trace_builder_preserves_contract_keys_and_strings() -> None:
    trace = PrimitivePlannerTraceBuilder().build(_inputs())

    assert trace["dig_cut_token_contract_version"] == DIG_CUT_TOKEN_CONTRACT
    assert trace["dig_cut_token_contract"] == (
        "entry_x,entry_z,exit_x,exit_z,dir_x,dir_z,"
        "length,cut_depth_semantic,payload,valid"
    )
    assert trace["return_target_token_contract_version"] == DIG_CUT_TOKEN_CONTRACT
    assert trace["return_target_token_contract"] == (
        "next entry_x,entry_z,exit_x,exit_z,dir_x,dir_z,"
        "length,cut_depth_semantic,payload,valid"
    )
    assert (
        trace["return_start_envelope_token_contract_version"]
        == "return_start_envelope_tokens_v1"
    )
    assert trace["return_start_envelope_token_contract"] == (
        "dig-grid long_norm,short_norm,depth_center,tip_radius,"
        "depth_min,depth_max,contact_allowed,qpos_center[4],"
        "qpos_half_width[4],qvel_abs_max,valid,no_dump_contact_required"
    )


def test_planner_trace_builder_preserves_coverage_fields_and_list_projection() -> None:
    inputs = _inputs()

    trace = PrimitivePlannerTraceBuilder().build(inputs)

    assert trace["dig_cut_planner_mode"] == "operator_prior_coverage"
    assert trace["dig_cut_prior_id"] == "default"
    assert trace["dig_cut_prior_path"] == "/tmp/dig_prior.json"
    assert trace["return_target_planner_enabled"] is True
    assert trace["coverage_use_env_removed_depth"] is False
    assert trace["coverage_candidate_layout"] == "corridor_grid"
    assert trace["coverage_first_dig_strategy"] == "preferred_corridor"
    assert trace["coverage_pass_index"] == 3
    assert trace["coverage_multi_pass_enabled"] is True
    assert trace["coverage_multi_pass_max_passes"] == 4
    assert trace["coverage_multi_pass_min_remaining_depth_m"] == 0.05
    assert trace["coverage_first_dig_preferred_corridor_id"] == -1
    assert trace["coverage_decision_trace_count"] == 1
    assert trace["coverage_terminal_stop_requested"] is True
    assert trace["coverage_terminal_stop_reason"] == "dig_area_depleted"

    assert trace["cell_entry_trace"] == [
        {"cell_id": 2, "reason": "compatibility_only"}
    ]
    assert trace["coverage_corridors"] == [{"corridor_id": 7, "score": 1.25}]
    assert trace["coverage_decision_trace"] == [{"event": "select_corridor"}]
    assert trace["cell_entry_trace"] is not inputs.cell_entry_trace
    assert trace["coverage_corridors"] is not inputs.coverage.corridors
    assert trace["coverage_decision_trace"] is not inputs.coverage.decision_trace
    assert trace["cell_entry_trace"][0] is inputs.cell_entry_trace[0]
    assert (
        trace["coverage_decision_trace"][0]
        is inputs.coverage.decision_trace[0]
    )


def test_policy_planner_trace_delegates_to_trace_builder() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    sentinel_inputs = object()
    built_trace = {"coverage_decision_trace_count": 0}

    class _FakeBuilder:
        def build(self, got_inputs: object) -> dict[str, Any]:
            assert got_inputs is sentinel_inputs
            return built_trace

    planner._planner_trace_inputs = MethodType(lambda self: sentinel_inputs, planner)
    planner._planner_trace_builder = MethodType(lambda self: _FakeBuilder(), planner)

    assert planner.planner_trace() is built_trace
