from __future__ import annotations

from types import MethodType
from typing import Any

from testbed.planner.primitive_debug_report import (
    PrimitiveDebugReportBuilder,
    PrimitiveDebugReportInputs,
    PrimitiveDebugStateSnapshot,
)
from testbed.planner.primitive_token_status import TokenStatus
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def _token_status() -> TokenStatus:
    return TokenStatus.from_inputs(
        cell_entry_enabled=True,
        cell_entry_token_injected=True,
        cell_entry_token_dim=6,
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
    assert report["cell_entry_enabled"] is True
    assert report["cell_entry_token_injected"] is True
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
    sentinel_inputs = object()
    built_report = {"skill_name": "dig", "skill_id": 0}

    class _FakeBuilder:
        def build(self, got_inputs: object) -> dict[str, Any]:
            assert got_inputs is sentinel_inputs
            return built_report

    planner._debug_report_inputs = MethodType(lambda self: sentinel_inputs, planner)
    planner._debug_report_builder = MethodType(lambda self: _FakeBuilder(), planner)

    assert planner.debug_state() is built_report
