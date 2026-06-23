from __future__ import annotations

import math
from types import MethodType
from typing import Any

from testbed.planner.primitive_coverage_reports import CoverageSummaryReportStatus
from testbed.planner.primitive_cell_entry_state import (
    PrimitiveCellEntryReportStatus,
)
from testbed.planner.primitive_pre_dig_align_state import (
    PrimitivePreDigAlignReportStatus,
)
from testbed.planner.primitive_rollout_summary import (
    PrimitiveRolloutSummaryBuilder,
    PrimitiveRolloutSummaryInputs,
)
from testbed.planner.primitive_token_state import PrimitiveTokenReportStatus
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def _inputs(**overrides: Any) -> PrimitiveRolloutSummaryInputs:
    token = PrimitiveTokenReportStatus(
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
    coverage = CoverageSummaryReportStatus(
        selected_corridor_id=12,
        depleted_count=6,
        completed_dump_count=7,
        pass_index=1,
        multi_pass_enabled=True,
        use_env_removed_depth=False,
        candidate_layout="corridor_grid",
        first_dig_strategy="preferred_corridor",
        first_dig_preferred_corridor_id=None,
        first_dig_max_entry_distance_m=None,
        first_dig_qpos_delta_weight=0.75,
        terminal_stop_requested=True,
        terminal_stop_reason="dig_area_depleted",
    )
    cell_entry = PrimitiveCellEntryReportStatus(
        enabled=False,
        trace=[],
        selected_cell_id=-1,
        selected_long_index=-1,
        selected_short_index=-1,
        planned_entry_x_m=float("nan"),
        planned_entry_y_m=float("nan"),
        planned_entry_z_m=float("nan"),
        planner_ok=False,
        audit_reason_code=-1,
        audit_reason="",
        audit_risk_flags=0,
        inside_entry_envelope=False,
        distance_to_entry_envelope_m=float("nan"),
        seen_cell_id=-1,
    )
    pre_dig_align = PrimitivePreDigAlignReportStatus(
        enabled=False,
        first_dig_only=True,
        replan_after_failed_dig=False,
        entry_intent_controlled_dims=None,
        surface_guard_enabled=True,
        surface_depth_m=float("nan"),
        surface_guard_triggered=False,
        surface_guard_count=2,
        active_for_next_dig=False,
        step_count=1,
        hold_count=2,
        timeout_count=3,
        completed_count=4,
        replan_count=5,
        target_qpos=[0.0, 0.0, 0.0, 0.0],
        error=[0.0, 0.0, 0.0, 0.0],
        entry_error_m=float("nan"),
        start_envelope_ready=False,
        first_dig_entry_close_handoff=False,
        entry_close_handoff_ready=False,
        entry_intent_handoff_enabled=False,
        entry_intent_handoff_ready=False,
        first_dig_entry_close_handoff_qvel_abs_max=float("nan"),
        controlled_dims=[1, 1, 1, 1],
        bucket_target_qpos=float("nan"),
    )
    values: dict[str, Any] = {
        "transition_source": "v2_2_primitive_return_policy",
        "transition_policy_mode": "primitive_return_policy",
        "transition_fallback_count": 0,
        "transition_fallback_reason": "",
        "transition_timeout_count": 2,
        "completed_transition_count": 3,
        "dump_done_use_boundary_event": True,
        "primitive_final_skill": "return",
        "primitive_cycle_index": 4,
        "cell_entry": cell_entry,
        "dig_cut_token_dim": 10,
        "return_target_token_dim": 10,
        "return_target_token_source": "return_target_corridor_1",
        "return_to_dig_max_entry_error_m": None,
        "return_to_dig_entry_error_m": 0.12,
        "return_to_dig_entry_close": True,
        "return_next_dig_event_seen": False,
        "return_to_dig_start_envelope_gate_enabled": True,
        "return_to_dig_start_envelope_direct_handoff_enabled": False,
        "return_to_dig_start_envelope_ready": True,
        "return_to_dig_start_envelope_plane_depth_mode": "p50_floor",
        "return_to_dig_start_envelope_local_depth_tolerance_m": 0.03,
        "return_to_dig_start_envelope_error": 0.04,
        "token": token,
        "dig_failed_replan_next_skill": "dig",
        "coverage": coverage,
        "scripted_bootstrap_timeout_count": 8,
        "pre_dig_align": pre_dig_align,
        "dig_bad_replan_count": 6,
        "dig_exit_guard_replan_count": 7,
    }
    values.update(overrides)
    return PrimitiveRolloutSummaryInputs(**values)


def test_rollout_summary_builder_preserves_public_summary_keys() -> None:
    summary = PrimitiveRolloutSummaryBuilder().build(_inputs())

    assert summary["transition_source"] == "v2_2_primitive_return_policy"
    assert summary["transition_policy_mode"] == "primitive_return_policy"
    assert summary["transition_timeout_count"] == 2
    assert summary["completed_transition_count"] == 3
    assert summary["primitive_final_skill"] == "return"
    assert summary["primitive_cycle_index"] == 4
    assert summary["cell_entry_trace_count"] == 0
    assert summary["dig_cut_token_dim"] == 10
    assert summary["return_target_token_dim"] == 10
    assert summary["return_target_token_source"] == "return_target_corridor_1"
    assert summary["pending_dig_cut_cycle_id"] == 4
    assert summary["pending_dig_cut_corridor_id"] == 9
    assert summary["dig_cut_planner_mode"] == "operator_prior_coverage"
    assert summary["dig_cut_prior_id"] == "default"
    assert summary["dig_cut_token_source"] == "operator_prior_coverage"
    assert summary["dig_cut_fallback_reason"] == "none"
    assert summary["coverage_selected_corridor_id"] == 12
    assert summary["coverage_depleted_count"] == 6
    assert summary["coverage_completed_dump_count"] == 7
    assert summary["coverage_candidate_layout"] == "corridor_grid"
    assert summary["coverage_first_dig_strategy"] == "preferred_corridor"
    assert summary["coverage_first_dig_preferred_corridor_id"] == -1
    assert summary["scripted_bootstrap_timeout_count"] == 8
    assert summary["pre_dig_align_surface_guard_count"] == 2
    assert summary["pre_dig_align_timeout_count"] == 3
    assert summary["pre_dig_align_completed_count"] == 4
    assert summary["pre_dig_align_replan_count"] == 5
    assert summary["dig_bad_replan_count"] == 6
    assert summary["dig_exit_guard_replan_count"] == 7


def test_rollout_summary_builder_preserves_int_and_nan_projection() -> None:
    summary = PrimitiveRolloutSummaryBuilder().build(_inputs())

    for key in (
        "dump_done_use_boundary_event",
        "cell_entry_enabled",
        "return_to_dig_entry_close",
        "return_next_dig_event_seen",
        "return_to_dig_start_envelope_gate_enabled",
        "return_to_dig_start_envelope_direct_handoff_enabled",
        "return_to_dig_start_envelope_ready",
        "dig_cut_token_injected",
        "dig_cut_token_in_prior_p10_p90",
        "coverage_multi_pass_enabled",
        "coverage_use_env_removed_depth",
        "coverage_terminal_stop_requested",
        "pre_dig_align_enabled",
        "pre_dig_align_first_dig_only",
        "pre_dig_align_replan_after_failed_dig",
        "pre_dig_align_surface_guard_enabled",
    ):
        assert type(summary[key]) is int

    assert summary["cell_entry_enabled"] == 0
    assert summary["return_next_dig_event_seen"] == 0
    assert summary["coverage_use_env_removed_depth"] == 0
    assert summary["pre_dig_align_enabled"] == 0
    assert math.isnan(summary["return_to_dig_max_entry_error_m"])
    assert math.isnan(summary["coverage_first_dig_max_entry_distance_m"])


def test_policy_rollout_summary_delegates_to_summary_builder() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    sentinel_inputs = object()
    built_summary = {"primitive_final_skill": "dig", "primitive_cycle_index": 1}

    class _FakeBuilder:
        def build(self, got_inputs: object) -> dict[str, Any]:
            assert got_inputs is sentinel_inputs
            return built_summary

    planner._rollout_summary_inputs = MethodType(
        lambda self: sentinel_inputs, planner
    )
    planner._rollout_summary_builder = MethodType(lambda self: _FakeBuilder(), planner)

    assert planner.rollout_summary() is built_summary
