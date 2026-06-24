from __future__ import annotations

from types import MethodType, SimpleNamespace
from typing import Any

import testbed.planner.primitive.report.runtime as report_runtime_module
from testbed.planner.primitive.execution.pre_dig_align import (
    PrimitivePreDigAlignRuntimeState,
)
from testbed.planner.primitive.facts.observation import (
    PrimitiveObservationInjectionRuntimeState,
)
from testbed.planner.primitive.report.debug_report import (
    PrimitiveDebugReportBuilder,
    PrimitiveDebugReportInputs,
    PrimitiveDebugStateSnapshot,
)
from testbed.planner.primitive.report.runtime import (
    PrimitiveReportRuntime,
    PrimitiveReportRuntimePorts,
)
from testbed.planner.primitive.token.state import PrimitiveTokenRuntimeState
from testbed.planner.primitive.token.status import TokenStatus
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def _token_status() -> TokenStatus:
    return TokenStatus.from_inputs(
        cell_entry_enabled=False,
        cell_entry_token_injected=False,
        cell_entry_token_dim=0,
        dig_cut_token_injected=True,
        dig_cut_token_dim=3,
        dig_cut_token_source="operator_prior_coverage",
        dig_cut_tokens=[1.0, 2.0, 3.0],
        dig_cut_fallback_reason="fallback",
        dig_cut_token_in_prior_p10_p90=True,
        dig_depth_profile_token_injected=True,
        dig_depth_profile_token_dim=2,
        dig_depth_profile_source="prior_profile",
        dig_depth_profile_required=True,
        dig_depth_profile_token_source="depth_profile",
        dig_depth_profile_tokens=[4.0, 5.0],
        return_target_token_injected=True,
        return_target_token_dim=3,
        return_target_token_source="return_target_corridor_0",
        return_target_tokens=[6.0, 7.0, 8.0],
        return_relocate_token_injected=True,
        return_relocate_token_dim=3,
        return_relocate_token_source="return_target_corridor_0",
        return_relocate_tokens=[9.0, 10.0, 11.0],
        return_start_envelope_token_injected=True,
        return_start_envelope_token_dim=2,
        return_start_envelope_token_source="return_start_envelope",
        return_start_envelope_tokens=[12.0, 13.0],
    )


def _inputs(**overrides: Any) -> PrimitiveDebugReportInputs:
    values: dict[str, Any] = {
        "debug_state": PrimitiveDebugStateSnapshot(
            skill_name="dig",
            skill_id=0,
            skill_switch_reason="bootstrap_to_dig",
            primitive_checkpoint_path="/tmp/dig.ckpt",
            hybrid_mode="WORK",
            transition_timeout=False,
            transition_completed=True,
            completed_transition_count=2,
            transition_timeout_count=0,
            dump_ready_hold_count=3,
            dump_done_hold_count=4,
            approach_ready_hold_count=0,
            dump_release_ready_hold_count=0,
            primitive_cycle_index=5,
        ),
        "transition_source": "v2_2_primitive_return_policy",
        "transition_policy_mode": "primitive_return_policy",
        "transition_fallback_count": 0,
        "transition_fallback_reason": "",
        "primitive_goal_curr_sector_id": 1,
        "primitive_goal_next_sector_id": 2,
        "token_status": _token_status(),
        "dig_failed_replan_next_skill": "dig",
        "return_fields": {
            "return_to_dig_entry_error_m": 0.125,
            "return_to_dig_entry_close": True,
            "return_next_dig_event_seen": False,
            "return_to_dig_start_envelope_gate_enabled": True,
            "return_to_dig_start_envelope_direct_handoff_enabled": True,
            "return_to_dig_start_envelope_ready": False,
            "return_to_dig_start_envelope_plane_depth_mode": "p50_floor",
            "return_to_dig_start_envelope_local_depth_tolerance_m": 0.005,
            "return_to_dig_start_envelope_error": 0.25,
            "return_to_dig_start_envelope_checks": {
                "qpos_0": {"value": 1.0, "ok": False}
            },
        },
        "pending_fields": {
            "pending_dig_cut_cycle_id": 5,
            "pending_dig_cut_corridor_id": 9,
        },
        "dig_cut_fields": {
            "dig_cut_planner_mode": "operator_prior_coverage",
            "dig_cut_prior_id": "default",
        },
        "coverage_fields": {
            "coverage_corridor_id": 7,
            "coverage_selected_corridor_id": 7,
            "coverage_last_selected_corridor_id": 6,
            "coverage_depleted_count": 3,
            "coverage_terminal_stop_requested": True,
            "coverage_terminal_stop_reason": "dig_area_depleted",
            "coverage_corridors": [
                {"corridor_id": 7, "score": 1.5},
            ],
            "coverage_candidate_scores": [{"corridor_id": 7, "score": 1.5}],
        },
        "cell_entry_fields": {
            "cell_entry_selected_cell_id": 2,
            "cell_entry_audit_reason": "compatibility_only",
        },
        "scripted_bootstrap_fields": {
            "scripted_bootstrap_step_count": 10,
            "scripted_bootstrap_hold_count": 2,
            "scripted_bootstrap_timeout_count": 0,
        },
        "dig_progress_fields": {
            "dig_step_count": 42,
            "dig_best_mass_kg": 18.0,
            "dig_mass_plateau_count": 4,
            "dig_to_carry_reason": "semantic_material_loaded",
            "dig_bad_replan_count": 1,
            "dig_exit_guard_replan_count": 0,
        },
        "pre_dig_align_fields": {
            "pre_dig_align_enabled": False,
            "pre_dig_align_completed_count": 0,
            "pre_dig_align_timeout_count": 0,
            "pre_dig_align_replan_count": 0,
            "pre_dig_align_active_for_next_dig": False,
        },
    }
    values.update(overrides)
    return PrimitiveDebugReportInputs(**values)


def test_debug_report_builder_uses_token_status_legacy_fields() -> None:
    report = PrimitiveDebugReportBuilder().build(_inputs())

    assert report["skill_name"] == "dig"
    assert report["skill_id"] == 0
    assert report["skill_switch_reason"] == "bootstrap_to_dig"
    assert report["transition_source"] == "v2_2_primitive_return_policy"
    assert report["transition_policy_mode"] == "primitive_return_policy"
    assert report["completed_transition_count"] == 2
    assert report["primitive_cycle_index"] == 5
    assert report["cell_entry_enabled"] is False
    assert report["cell_entry_token_injected"] is False
    assert report["dig_cut_token_source"] == "operator_prior_coverage"
    assert report["dig_cut_tokens"] == [1.0, 2.0, 3.0]
    assert report["dig_depth_profile_token_source"] == "depth_profile"
    assert report["return_target_token_source"] == "return_target_corridor_0"
    assert report["return_start_envelope_tokens"] == [12.0, 13.0]
    assert report["dig_cut_token_in_prior_p10_p90"] is True
    assert report["fallback_reason"] == "fallback"


def test_debug_report_builder_projects_report_sections_without_aliasing() -> None:
    inputs = _inputs()

    report = PrimitiveDebugReportBuilder().build(inputs)

    assert report["return_to_dig_start_envelope_checks"] == {
        "qpos_0": {"value": 1.0, "ok": False}
    }
    assert report["coverage_corridors"] == [{"corridor_id": 7, "score": 1.5}]
    assert report["coverage_candidate_scores"] == [
        {"corridor_id": 7, "score": 1.5}
    ]
    assert report["cell_entry_audit_reason"] == "compatibility_only"
    assert report["pre_dig_align_completed_count"] == 0

    assert (
        report["return_to_dig_start_envelope_checks"]
        is not inputs.return_fields["return_to_dig_start_envelope_checks"]
    )
    assert report["coverage_corridors"] is not inputs.coverage_fields[
        "coverage_corridors"
    ]
    assert report["coverage_candidate_scores"] is not inputs.coverage_fields[
        "coverage_candidate_scores"
    ]


def test_policy_debug_state_delegates_to_report_builder() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    built_report = {"skill_name": "dig", "skill_id": 0}

    class _FakePublicRuntime:
        def debug_state(self) -> dict[str, Any]:
            return built_report

    planner._primitive_runtime_kernel_runtime = MethodType(
        lambda self: _FakePublicRuntime(), planner
    )

    assert planner.debug_state() is built_report


def test_policy_report_input_methods_delegate_to_report_runtime() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    sentinel_debug_inputs = object()
    sentinel_summary_inputs = object()
    sentinel_trace_inputs = object()

    class _FakeReportRuntime:
        def debug_report_inputs(self) -> object:
            return sentinel_debug_inputs

        def rollout_summary_inputs(self) -> object:
            return sentinel_summary_inputs

        def planner_trace_inputs(self) -> object:
            return sentinel_trace_inputs

    runtime = _FakeReportRuntime()
    planner._primitive_report_composition_runtime = MethodType(
        lambda self: SimpleNamespace(report_runtime=lambda: runtime),
        planner,
    )

    ports = planner._primitive_runtime_kernel_runtime_ports()

    report_runtime = ports.report_runtime()

    assert report_runtime.debug_report_inputs() is sentinel_debug_inputs
    assert report_runtime.rollout_summary_inputs() is sentinel_summary_inputs
    assert report_runtime.planner_trace_inputs() is sentinel_trace_inputs


def test_policy_no_longer_exposes_old_report_runtime_private_wrappers() -> None:
    old_names = {
        f"_{name}"
        for name in (
            "debug_report_inputs",
            "rollout_summary_inputs",
            "planner_trace_inputs",
            "debug_state_snapshot_for_report",
            "debug_report_return_fields",
            "debug_report_pending_fields",
            "debug_report_dig_cut_fields",
            "debug_report_coverage_fields",
            "debug_report_cell_entry_fields",
            "debug_report_scripted_bootstrap_fields",
            "debug_report_dig_progress_fields",
            "debug_report_pre_dig_align_fields",
        )
    }

    assert old_names.isdisjoint(PrimitivePlannerACTPolicy.__dict__)


def test_policy_no_longer_exposes_report_status_composition_private_wrappers() -> None:
    old_names = {
        "_primitive_report_runtime_ports",
        "_primitive_report_runtime",
        "_token_status_for_debug_report",
        "_token_report_status",
        "_cell_entry_report_config",
        "_cell_entry_report_status",
        "_pre_dig_align_report_config",
        "_pre_dig_align_report_status",
    }

    assert old_names.isdisjoint(PrimitivePlannerACTPolicy.__dict__)


def test_report_composition_runtime_projects_token_status_from_focused_states() -> None:
    token_state = PrimitiveTokenRuntimeState.fresh()
    token_state.dig_cut_token_source = "operator_prior_coverage"
    token_state.dig_depth_profile_token_source = "prior_profile"
    token_state.return_target_token_source = "return_target_corridor_0"
    injection_state = PrimitiveObservationInjectionRuntimeState(
        dig_cut_token_injected=True,
        dig_depth_profile_token_injected=True,
        return_target_token_injected=True,
    )
    runtime = report_runtime_module.PrimitiveReportCompositionRuntime.from_ports(
        report_runtime_module.PrimitiveReportCompositionPorts(
            debug_state=lambda: SimpleNamespace(
                skill_name="dig",
                skill_id=0,
                skill_switch_reason="reset",
                primitive_checkpoint_path="",
                hybrid_mode="WORK",
                transition_timeout=False,
                transition_completed=False,
                completed_transition_count=0,
                transition_timeout_count=0,
                dump_ready_hold_count=0,
                dump_done_hold_count=0,
                approach_ready_hold_count=0,
                dump_release_ready_hold_count=0,
                primitive_cycle_index=0,
            ),
            cycle_report_status=lambda: SimpleNamespace(
                primitive_cycle_index=0,
                completed_transition_count=0,
                transition_timeout_count=0,
                dig_bad_replan_count=0,
                dig_exit_guard_replan_count=0,
                dig_progress_debug_fields=lambda: {},
            ),
            return_report_status=lambda: SimpleNamespace(
                return_to_dig_entry_error_m=0.0,
                return_to_dig_entry_close=True,
                return_next_dig_event_seen=False,
                return_to_dig_start_envelope_gate_enabled=False,
                return_to_dig_start_envelope_direct_handoff_enabled=False,
                return_to_dig_start_envelope_ready=True,
                return_to_dig_start_envelope_plane_depth_mode="range",
                return_to_dig_start_envelope_local_depth_tolerance_m=0.0,
                return_to_dig_start_envelope_error=0.0,
                debug_fields=lambda: {},
            ),
            token_state=lambda: token_state,
            observation_injection_state=lambda: injection_state,
            coverage_state=lambda: object(),
            coverage_report_runtime=lambda: SimpleNamespace(
                report_config=lambda: object(),
                report_service=lambda: SimpleNamespace(
                    debug_fields_from_state=lambda *args, **kwargs: {},
                    summary_status_from_state=lambda *args, **kwargs: object(),
                    trace_status_from_state=lambda *args, **kwargs: object(),
                ),
            ),
            coverage_selection_service=lambda: object(),
            cell_entry_state=lambda: SimpleNamespace(
                to_report_status=lambda config: SimpleNamespace(
                    debug_fields=lambda: {}
                )
            ),
            scripted_bootstrap_report_status=lambda: SimpleNamespace(
                timeout_count=0,
                debug_fields=lambda: {},
            ),
            pre_dig_align_state=lambda: PrimitivePreDigAlignRuntimeState.fresh(
                action_dim=4
            ),
            pre_dig_align_enabled=lambda: False,
            pre_dig_align_first_dig_only=lambda: False,
            pre_dig_align_replan_after_failed_dig=lambda: False,
            pre_dig_align_entry_intent_controlled_dims=lambda: None,
            pre_dig_align_surface_guard_enabled=lambda: False,
            pre_dig_align_active_for_next_dig=lambda: False,
            pre_dig_align_first_dig_entry_close_handoff=lambda: False,
            pre_dig_align_entry_intent_handoff_enabled=lambda: False,
            pre_dig_align_first_dig_entry_close_handoff_qvel_abs_max=lambda: None,
            pre_dig_align_controlled_dims=lambda: [1, 0, 1, 0],
            pre_dig_align_bucket_target_qpos=lambda: None,
            action_dim=lambda: 4,
            goal_sector_id=lambda cycle_index: int(cycle_index),
            next_goal_sector_id=lambda: 0,
            dig_failed_replan_next_skill=lambda: "dig",
            dump_done_use_boundary_event=lambda: False,
            skill_name=lambda: "dig",
            return_target_planner_enabled=lambda: False,
            return_target_token_source=lambda: "none",
            return_to_dig_max_entry_error_m=lambda: None,
            dig_depth_profile_source=lambda: "prior_profile",
            dig_depth_profile_required=lambda: True,
            dig_cut_planner_mode=lambda: "operator_prior_coverage",
            dig_cut_prior_id=lambda: "default",
            dig_cut_prior_path=lambda: "/tmp/dig_prior.json",
        )
    )

    token_status = runtime.token_status_for_debug_report()
    token_report_status = runtime.token_report_status()
    token_debug_fields = token_status.to_debug_fields()

    assert token_debug_fields["dig_cut_token_source"] == "operator_prior_coverage"
    assert token_debug_fields["dig_depth_profile_token_injected"] is True
    assert token_debug_fields["return_target_token_source"] == "return_target_corridor_0"
    assert token_report_status.dig_cut_planner_mode == "operator_prior_coverage"
    assert token_report_status.dig_cut_prior_id == "default"


def test_report_runtime_assembles_public_report_inputs_from_typed_ports() -> None:
    coverage_state = object()
    coverage_config = object()
    coverage_selection_service = object()
    coverage_summary = object()
    coverage_trace = object()
    calls: list[tuple[str, object, object, object | None]] = []

    class _CoverageReports:
        def debug_fields_from_state(
            self,
            state: object,
            *,
            config: object,
            selection_service: object,
        ) -> dict[str, int]:
            calls.append(("debug", state, config, selection_service))
            return {"coverage_corridor_id": 4}

        def summary_status_from_state(
            self,
            state: object,
            *,
            config: object,
        ) -> object:
            calls.append(("summary", state, config, None))
            return coverage_summary

        def trace_status_from_state(
            self,
            state: object,
            *,
            config: object,
            selection_service: object,
        ) -> object:
            calls.append(("trace", state, config, selection_service))
            return coverage_trace

    cycle_status = SimpleNamespace(
        completed_transition_count=6,
        transition_timeout_count=1,
        primitive_cycle_index=5,
        dig_bad_replan_count=2,
        dig_exit_guard_replan_count=3,
        dig_progress_debug_fields=lambda: {"dig_step_count": 7},
    )
    return_status = SimpleNamespace(
        return_to_dig_entry_error_m=0.2,
        return_to_dig_entry_close=True,
        return_next_dig_event_seen=False,
        return_to_dig_start_envelope_gate_enabled=True,
        return_to_dig_start_envelope_direct_handoff_enabled=False,
        return_to_dig_start_envelope_ready=True,
        return_to_dig_start_envelope_plane_depth_mode="p50_floor",
        return_to_dig_start_envelope_local_depth_tolerance_m=0.03,
        return_to_dig_start_envelope_error=0.04,
        debug_fields=lambda: {"return_to_dig_entry_close": True},
    )
    token_report = SimpleNamespace(
        pending_debug_fields=lambda: {"pending_dig_cut_cycle_id": 5},
        dig_cut_debug_fields=lambda: {"dig_cut_planner_mode": "coverage"},
    )
    scripted_status = SimpleNamespace(
        timeout_count=8,
        debug_fields=lambda: {"scripted_bootstrap_timeout_count": 8},
    )
    cell_entry_status = SimpleNamespace(
        debug_fields=lambda: {"cell_entry_enabled": False}
    )
    pre_dig_status = SimpleNamespace(
        debug_fields=lambda: {"pre_dig_align_enabled": False}
    )
    debug_state = SimpleNamespace(
        skill_name="dig",
        skill_id=0,
        skill_switch_reason="reset",
        primitive_checkpoint_path="/tmp/dig.ckpt",
        hybrid_mode="WORK",
        transition_timeout=False,
        transition_completed=True,
        completed_transition_count=6,
        transition_timeout_count=1,
        dump_ready_hold_count=2,
        dump_done_hold_count=3,
        approach_ready_hold_count=0,
        dump_release_ready_hold_count=0,
        primitive_cycle_index=5,
    )
    runtime = PrimitiveReportRuntime.from_ports(
        PrimitiveReportRuntimePorts(
            debug_state=lambda: debug_state,
            cycle_report_status=lambda: cycle_status,
            return_report_status=lambda: return_status,
            token_status_for_debug_report=_token_status,
            token_report_status=lambda: token_report,
            coverage_state=lambda: coverage_state,
            coverage_report_config=lambda: coverage_config,
            coverage_selection_service=lambda: coverage_selection_service,
            coverage_report_service=lambda: _CoverageReports(),
            cell_entry_report_status=lambda: cell_entry_status,
            scripted_bootstrap_report_status=lambda: scripted_status,
            pre_dig_align_report_status=lambda: pre_dig_status,
            goal_sector_id=lambda cycle_index: 100 + int(cycle_index),
            next_goal_sector_id=lambda: 200,
            dig_failed_replan_next_skill=lambda: "dig",
            dump_done_use_boundary_event=lambda: True,
            skill_name=lambda: "return",
            return_target_planner_enabled=lambda: True,
            return_target_token_source=lambda: "return_target_corridor_0",
            return_to_dig_max_entry_error_m=lambda: None,
        )
    )

    debug_inputs = runtime.debug_report_inputs()
    summary_inputs = runtime.rollout_summary_inputs()
    trace_inputs = runtime.planner_trace_inputs()

    assert debug_inputs.debug_state.skill_name == "dig"
    assert debug_inputs.primitive_goal_curr_sector_id == 105
    assert debug_inputs.primitive_goal_next_sector_id == 200
    assert debug_inputs.coverage_fields == {"coverage_corridor_id": 4}
    assert debug_inputs.pending_fields == {"pending_dig_cut_cycle_id": 5}
    assert debug_inputs.dig_progress_fields == {"dig_step_count": 7}
    assert summary_inputs.primitive_final_skill == "return"
    assert summary_inputs.return_target_token_source == "return_target_corridor_0"
    assert summary_inputs.coverage is coverage_summary
    assert summary_inputs.scripted_bootstrap_timeout_count == 8
    assert trace_inputs.coverage is coverage_trace
    assert trace_inputs.return_target_planner_enabled is True
    assert calls == [
        ("debug", coverage_state, coverage_config, coverage_selection_service),
        ("summary", coverage_state, coverage_config, None),
        ("trace", coverage_state, coverage_config, coverage_selection_service),
    ]
