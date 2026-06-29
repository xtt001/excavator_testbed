from __future__ import annotations

import json

from testbed.planner.primitive.decision.backends.behavior_tree import (
    BehaviorTreeNodeTrace,
)
from testbed.planner.primitive.decision.contracts import (
    CompleteCoverageDigEffect,
    LEGACY_FSM_DECISION_SOURCE,
    RequestedPlannerEffect,
    SwitchSkillEffect,
    PrimitiveDecisionResult,
)
from testbed.planner.primitive.facts.capabilities import (
    CarryTransitionStatus,
    DigTransitionStatus,
    DumpTransitionStatus,
    ReturnTransitionStatus,
)
import testbed.planner.primitive.report.decision_trace as decision_trace_module
from testbed.planner.primitive.report.decision_trace import (
    DECISION_TRACE_SCHEMA_VERSION,
    DecisionDiagnosticCheck,
    DecisionTraceAssembler,
    DecisionTraceMetadata,
)


def _no_change_result() -> PrimitiveDecisionResult:
    return PrimitiveDecisionResult.from_requested_effects(
        decision_source="behavior_tree_continue_current_skill",
        status="no_change",
        skill_before="dig",
        skill_after="dig",
        switch_reason="",
        effects=(),
    )


def _dig_status(**overrides: object) -> DigTransitionStatus:
    values = {
        "dig_step_count": 0,
        "mass_in_bucket_kg": 0.0,
        "min_distance_to_dig_area_m": 0.0,
        "transition_mass_in_bucket_kg": 0.0,
        "transition_min_distance_to_dig_area_m": 0.0,
        "distance_ready": False,
        "semantic_boundary_profile_active": False,
        "coverage_terminal_stop_requested": False,
        "dig_complete_boundary": False,
        "dig_complete_boundary_low_payload": False,
        "dig_bad_replan_ready": False,
        "dig_exit_guard_ready": False,
        "dig_mass_plateau_ready": False,
        "dig_to_carry_ready": False,
        "dig_to_carry_reason": "",
    }
    values.update(overrides)
    return DigTransitionStatus(**values)


def _carry_status(**overrides: object) -> CarryTransitionStatus:
    values = {
        "mass_in_bucket_kg": 0.0,
        "deposited_mass_in_target_box_kg": 0.0,
        "deposit_delta_since_cycle_start_kg": 0.0,
        "semantic_boundary_profile_active": False,
        "dump_committed_event": False,
        "release_onset_event": False,
        "dump_complete_event": False,
        "legacy_dump_start_event": False,
        "carry_release_safety_done": False,
        "dump_ready": False,
        "next_dump_ready_hold_count": 0,
        "ready_to_dump": False,
        "carry_to_dump_reason": "",
        "carry_to_return_reason": "",
    }
    values.update(overrides)
    return CarryTransitionStatus(**values)


def _dump_status(**overrides: object) -> DumpTransitionStatus:
    values = {
        "mass_in_bucket_kg": 0.0,
        "deposited_mass_in_target_box_kg": 0.0,
        "deposit_delta_since_dump_start_kg": 0.0,
        "semantic_boundary_profile_active": False,
        "dump_complete_event": False,
        "legacy_dump_end_event": False,
        "boundary_dump_done": False,
        "dump_done_mass_low": False,
        "next_dump_done_hold_count": 0,
        "ready_to_return": False,
        "coverage_completion_reason": "",
        "dump_to_return_reason": "",
    }
    values.update(overrides)
    return DumpTransitionStatus(**values)


def _return_status(**overrides: object) -> ReturnTransitionStatus:
    values = {
        "mass_in_bucket_kg": 0.0,
        "min_distance_to_dig_area_m": 0.0,
        "bucket_depth_below_dig_area_plane_m": 0.0,
        "semantic_boundary_profile_active": False,
        "next_dig_event": False,
        "next_or_seen_dig_event": False,
        "entry_close": False,
        "start_envelope_ready": False,
        "handoff_ready": False,
        "direct_handoff_ready": False,
        "shallow_guard_ready": False,
        "shallow_guard_allowed": False,
        "completed_transition": False,
        "next_skill": "",
        "switch_reason": "",
    }
    values.update(overrides)
    return ReturnTransitionStatus(**values)


def test_no_change_result_assembles_compact_and_rich_trace() -> None:
    record = DecisionTraceAssembler.assemble(
        result=_no_change_result(),
        backend_payload=None,
        metadata=DecisionTraceMetadata(
            backend_name="behavior_tree_shadow",
            backend_kind="behavior_tree",
            tick_id="tick-001",
            episode_id="episode-a",
            sim_time_s=12.5,
            reason_codes=("bt_continue_fallback",),
            confidence=0.75,
            score=0.5,
        ),
    )

    assert record.schema_version == DECISION_TRACE_SCHEMA_VERSION
    assert record.backend_name == "behavior_tree_shadow"
    assert record.backend_kind == "behavior_tree"
    assert record.decision_source == "behavior_tree_continue_current_skill"
    assert record.decision_status == "no_change"
    assert record.trace_status == "success"
    assert record.validation_status == "skipped"
    assert record.skill_before == "dig"
    assert record.skill_after == "dig"
    assert record.selected_operation == "continue_current_skill"
    assert record.fallback_type == "none"
    assert record.reason_codes == ("bt_continue_fallback",)
    assert record.requested_effects_summary == ()

    compact = record.to_compact_dict()
    assert compact == {
        "schema_version": DECISION_TRACE_SCHEMA_VERSION,
        "backend_name": "behavior_tree_shadow",
        "backend_kind": "behavior_tree",
        "decision_source": "behavior_tree_continue_current_skill",
        "decision_status": "no_change",
        "trace_status": "success",
        "validation_status": "skipped",
        "skill_before": "dig",
        "skill_after": "dig",
        "selected_operation": "continue_current_skill",
        "fallback_type": "none",
        "reason_codes": ["bt_continue_fallback"],
        "requested_effects_summary": [],
        "confidence": 0.75,
        "score": 0.5,
        "tick_id": "tick-001",
        "sim_time_s": 12.5,
    }
    assert "backend_payload" not in compact
    assert "diagnostic_checks" not in compact
    json.dumps(compact, sort_keys=True)

    rich = record.to_rich_dict()
    assert rich["switch_reason"] == ""
    assert rich["episode_id"] == "episode-a"
    assert rich["backend_payload"] == {}
    assert rich["diagnostic_checks"] == []
    json.dumps(rich, sort_keys=True)


def test_requested_effect_result_summarizes_effects_without_applying_them() -> None:
    effect = SwitchSkillEffect(
        target_skill_name="carry",
        switch_reason="dig_to_carry_loaded",
    )
    result = PrimitiveDecisionResult.from_requested_effects(
        decision_source="legacy_fsm_dig_requested_effect",
        status="skill_switch",
        skill_before="dig",
        skill_after="carry",
        switch_reason="dig_to_carry_loaded",
        effects=(effect,),
    )

    record = DecisionTraceAssembler.assemble(
        result=result,
        backend_payload={"backend_family": "legacy_fsm"},
        metadata=DecisionTraceMetadata(
            backend_name="legacy_fsm",
            backend_kind="legacy_fsm",
            selected_operation="switch_skill",
            reason_codes=("legacy_fsm_branch_selected",),
        ),
    )

    assert result.effects == (effect,)
    assert record.requested_effects_summary[0].to_rich_dict() == {
        "effect_type": "switch_skill",
        "reason": "dig_to_carry_loaded",
        "already_applied": False,
        "payload_keys": [],
    }
    assert record.to_compact_dict()["requested_effects_summary"] == [
        {
            "effect_type": "switch_skill",
            "reason": "dig_to_carry_loaded",
            "already_applied": False,
        }
    ]


def test_bt_like_backend_payload_is_excluded_from_compact_and_included_in_rich() -> None:
    backend_payload = {
        "backend_family": "behavior_tree",
        "payload_schema_version": "behavior_tree_payload_v1",
        "payload_kind": "node_trace",
        "root_status": "success",
        "selected_path": ("behavior_tree_root", "continue_current_skill"),
        "node_results": (
            {
                "node_name": "behavior_tree_root",
                "status": "success",
                "reason": "selected:continue_current_skill",
            },
            {
                "node_name": "continue_current_skill",
                "status": "success",
                "reason": "continue_current_skill",
            },
        ),
        "failed_conditions": (),
    }

    record = DecisionTraceAssembler.assemble(
        result=_no_change_result(),
        backend_payload=backend_payload,
        metadata=DecisionTraceMetadata(
            backend_name="behavior_tree_shadow",
            backend_kind="behavior_tree",
            fallback_type="continue_current_skill",
            reason_codes=("bt_continue_fallback",),
        ),
    )

    compact = record.to_compact_dict()
    assert "backend_payload" not in compact
    assert record.trace_status == "fallback"

    rich = record.to_rich_dict()
    assert rich["backend_payload"] == {
        "backend_family": "behavior_tree",
        "payload_schema_version": "behavior_tree_payload_v1",
        "payload_kind": "node_trace",
        "root_status": "success",
        "selected_path": ["behavior_tree_root", "continue_current_skill"],
        "node_results": [
            {
                "node_name": "behavior_tree_root",
                "status": "success",
                "reason": "selected:continue_current_skill",
            },
            {
                "node_name": "continue_current_skill",
                "status": "success",
                "reason": "continue_current_skill",
            },
        ],
        "failed_conditions": [],
    }
    json.dumps(rich, sort_keys=True)


def test_diagnostic_checks_serialize_deterministically() -> None:
    checks = (
        DecisionDiagnosticCheck(
            name="return_handoff_gate",
            status="pass",
            reason="entry_ready",
            value={"entry_error_m": 0.01},
        ),
        DecisionDiagnosticCheck(
            name="vlm_grounding_check",
            status="unknown",
            reason="not_run",
            value=None,
        ),
    )
    record = DecisionTraceAssembler.assemble(
        result=_no_change_result(),
        backend_payload={},
        metadata=DecisionTraceMetadata(
            backend_name="mock_backend",
            backend_kind="external",
            diagnostic_checks=checks,
        ),
    )

    assert record.to_rich_dict()["diagnostic_checks"] == [
        {
            "name": "return_handoff_gate",
            "status": "pass",
            "reason": "entry_ready",
            "value": {"entry_error_m": 0.01},
        },
        {
            "name": "vlm_grounding_check",
            "status": "unknown",
            "reason": "not_run",
            "value": None,
        },
    ]
    assert record.to_compact_dict()["reason_codes"] == []


def test_assembler_does_not_mutate_result_or_effects() -> None:
    payload = {"alpha": 1}
    effect = RequestedPlannerEffect(
        effect_type="custom_trace_effect",
        reason="custom_reason",
        payload=payload,
    )
    result = PrimitiveDecisionResult.from_requested_effects(
        decision_source="external_shadow",
        status="no_change",
        skill_before="return",
        skill_after="return",
        switch_reason="",
        effects=(effect,),
    )
    effects_before = result.effects
    payload_before = dict(payload)

    record = DecisionTraceAssembler.assemble(
        result=result,
        backend_payload={"unsafe_tuple": ("a", "b")},
        metadata=DecisionTraceMetadata(
            backend_name="external_shadow",
            backend_kind="external",
        ),
    )

    assert result.effects is effects_before
    assert effect.payload == payload_before
    assert payload == payload_before
    assert record.to_rich_dict()["backend_payload"] == {"unsafe_tuple": ["a", "b"]}


def test_legacy_fsm_requested_effect_result_maps_payload_and_trace_fields() -> None:
    result = PrimitiveDecisionResult.from_requested_effects(
        decision_source="legacy_fsm_dig_requested_effect",
        status="skill_switch",
        skill_before="dig",
        skill_after="carry",
        switch_reason="dig_to_carry_loaded",
        effects=(
            CompleteCoverageDigEffect(),
            SwitchSkillEffect(
                target_skill_name="carry",
                switch_reason="dig_to_carry_loaded",
            ),
        ),
    )

    record = decision_trace_module.assemble_legacy_fsm_decision_trace(
        result=result,
        tick_id="legacy-tick-001",
    )

    compact = record.to_compact_dict()
    assert compact["backend_name"] == "legacy_fsm"
    assert compact["backend_kind"] == "legacy_fsm"
    assert compact["selected_operation"] == "switch_skill"
    assert compact["reason_codes"] == ["legacy_fsm_branch_selected"]
    assert "backend_payload" not in compact

    rich = record.to_rich_dict()
    payload = rich["backend_payload"]
    assert payload["backend_family"] == "legacy_fsm"
    assert payload["payload_schema_version"] == "legacy_fsm_payload_v1"
    assert payload["payload_kind"] == "requested_branch"
    assert payload["branch_name"] == "dig"
    assert payload["branch_order_index"] == 1
    assert payload["decision_source"] == "legacy_fsm_dig_requested_effect"
    assert payload["legacy_reason"] == "dig_to_carry_loaded"
    assert payload["side_effects_applied"] is False
    assert payload["effect_types"] == ["complete_coverage_dig", "switch_skill"]
    json.dumps(rich, sort_keys=True)


def test_legacy_fsm_compatibility_outcome_maps_without_private_branch_state() -> None:
    result = PrimitiveDecisionResult.from_legacy_fsm_outcome(
        skill_before="carry",
        skill_after="dump",
        switch_reason="carry_to_dump_target_ready",
        decision_source=LEGACY_FSM_DECISION_SOURCE,
    )

    record = decision_trace_module.assemble_legacy_fsm_decision_trace(
        result=result,
        episode_id="legacy-episode-a",
    )

    compact = record.to_compact_dict()
    assert compact["selected_operation"] == "switch_skill"
    assert compact["reason_codes"] == ["legacy_fsm_compatibility_outcome"]

    payload = record.to_rich_dict()["backend_payload"]
    assert payload["payload_kind"] == "compatibility_outcome"
    assert payload["branch_name"] == "unknown"
    assert payload["branch_order_index"] is None
    assert payload["legacy_reason"] == "carry_to_dump_target_ready"
    assert payload["side_effects_applied"] is True
    assert payload["effect_types"] == ["legacy_decision_outcome"]


def test_compact_trace_keys_match_for_legacy_and_behavior_tree_payloads() -> None:
    legacy_result = PrimitiveDecisionResult.from_requested_effects(
        decision_source="legacy_fsm_bootstrap_requested_effect",
        status="no_change",
        skill_before="bootstrap",
        skill_after="bootstrap",
        switch_reason="",
        effects=(),
    )
    legacy_record = decision_trace_module.assemble_legacy_fsm_decision_trace(
        result=legacy_result,
        tick_id="same-shape",
    )
    bt_record = decision_trace_module.assemble_behavior_tree_shadow_decision_trace(
        result=_no_change_result(),
        node_trace=(
            BehaviorTreeNodeTrace(
                node_name="behavior_tree_root",
                status="success",
                reason="selected:continue_current_skill",
            ),
            BehaviorTreeNodeTrace(
                node_name="continue_current_skill",
                status="success",
                reason="continue_current_skill",
            ),
        ),
        tick_id="same-shape",
    )

    assert list(legacy_record.to_compact_dict()) == list(bt_record.to_compact_dict())

    legacy_rich = legacy_record.to_rich_dict()
    bt_rich = bt_record.to_rich_dict()
    assert legacy_rich["backend_payload"]["backend_family"] == "legacy_fsm"
    assert bt_rich["backend_payload"]["backend_family"] == "behavior_tree"
    assert "branch_name" not in legacy_rich
    assert "node_results" not in bt_rich


def test_dig_status_maps_replan_exit_guard_and_carry_ready_diagnostics() -> None:
    checks = decision_trace_module.diagnostic_checks_from_dig_status(
        _dig_status(
            dig_step_count=8,
            mass_in_bucket_kg=1.25,
            min_distance_to_dig_area_m=0.42,
            transition_mass_in_bucket_kg=1.5,
            transition_min_distance_to_dig_area_m=0.5,
            distance_ready=True,
            dig_bad_replan_ready=True,
            dig_exit_guard_ready=False,
            dig_to_carry_ready=True,
            dig_to_carry_reason="target_payload_loaded",
        )
    )

    assert [check.to_dict() for check in checks] == [
        {
            "name": "dig_bad_replan_ready",
            "status": "pass",
            "reason": "dig_bad_replan_ready",
            "value": {
                "dig_step_count": 8,
                "mass_in_bucket_kg": 1.25,
                "coverage_terminal_stop_requested": False,
            },
        },
        {
            "name": "dig_exit_guard_ready",
            "status": "fail",
            "reason": "",
            "value": {
                "dig_step_count": 8,
                "mass_in_bucket_kg": 1.25,
                "coverage_terminal_stop_requested": False,
            },
        },
        {
            "name": "dig_to_carry_ready",
            "status": "pass",
            "reason": "target_payload_loaded",
            "value": {
                "transition_mass_in_bucket_kg": 1.5,
                "transition_min_distance_to_dig_area_m": 0.5,
                "distance_ready": True,
                "dig_complete_boundary": False,
                "dig_mass_plateau_ready": False,
            },
        },
    ]


def test_carry_status_maps_dump_and_return_ready_diagnostics() -> None:
    checks = decision_trace_module.diagnostic_checks_from_carry_status(
        _carry_status(
            mass_in_bucket_kg=2.0,
            deposited_mass_in_target_box_kg=4.5,
            deposit_delta_since_cycle_start_kg=0.7,
            dump_ready=True,
            next_dump_ready_hold_count=3,
            ready_to_dump=True,
            carry_to_dump_reason="target_ready",
            carry_release_safety_done=False,
            dump_complete_event=True,
            carry_to_return_reason="carry_to_return_dump_complete_boundary",
        )
    )

    assert [check.to_dict() for check in checks] == [
        {
            "name": "carry_dump_ready",
            "status": "pass",
            "reason": "target_ready",
            "value": {
                "dump_ready": True,
                "next_dump_ready_hold_count": 3,
                "ready_to_dump": True,
                "dump_committed_event": False,
                "release_onset_event": False,
                "legacy_dump_start_event": False,
            },
        },
        {
            "name": "carry_return_ready",
            "status": "pass",
            "reason": "carry_to_return_dump_complete_boundary",
            "value": {
                "carry_release_safety_done": False,
                "dump_complete_event": True,
                "deposit_delta_since_cycle_start_kg": 0.7,
            },
        },
    ]


def test_dump_status_maps_return_ready_diagnostics() -> None:
    checks = decision_trace_module.diagnostic_checks_from_dump_status(
        _dump_status(
            mass_in_bucket_kg=0.1,
            deposited_mass_in_target_box_kg=6.0,
            deposit_delta_since_dump_start_kg=1.2,
            boundary_dump_done=False,
            dump_done_mass_low=True,
            next_dump_done_hold_count=2,
            ready_to_return=True,
            coverage_completion_reason="dump_mass_low",
            dump_to_return_reason="dump_to_return_mass_low",
        )
    )

    assert [check.to_dict() for check in checks] == [
        {
            "name": "dump_return_ready",
            "status": "pass",
            "reason": "dump_to_return_mass_low",
            "value": {
                "boundary_dump_done": False,
                "dump_done_mass_low": True,
                "next_dump_done_hold_count": 2,
                "coverage_completion_reason": "dump_mass_low",
                "deposit_delta_since_dump_start_kg": 1.2,
            },
        },
    ]


def test_return_status_maps_handoff_diagnostics_from_public_fields() -> None:
    checks = decision_trace_module.diagnostic_checks_from_return_status(
        _return_status(
            mass_in_bucket_kg=0.0,
            min_distance_to_dig_area_m=0.02,
            bucket_depth_below_dig_area_plane_m=0.08,
            next_dig_event=True,
            next_or_seen_dig_event=True,
            entry_close=True,
            start_envelope_ready=True,
            handoff_ready=True,
            direct_handoff_ready=False,
            shallow_guard_ready=True,
            shallow_guard_allowed=True,
            completed_transition=True,
            next_skill="dig",
            switch_reason="return_to_dig_next_dig_entry_ready",
        )
    )

    assert [check.to_dict() for check in checks] == [
        {
            "name": "return_entry_close",
            "status": "pass",
            "reason": "entry_close",
            "value": {
                "min_distance_to_dig_area_m": 0.02,
                "next_dig_event": True,
                "next_or_seen_dig_event": True,
            },
        },
        {
            "name": "return_start_envelope_ready",
            "status": "pass",
            "reason": "start_envelope_ready",
            "value": {
                "bucket_depth_below_dig_area_plane_m": 0.08,
                "semantic_boundary_profile_active": False,
            },
        },
        {
            "name": "return_handoff_ready",
            "status": "pass",
            "reason": "return_to_dig_next_dig_entry_ready",
            "value": {
                "entry_close": True,
                "start_envelope_ready": True,
                "completed_transition": True,
                "next_skill": "dig",
            },
        },
        {
            "name": "return_direct_handoff_ready",
            "status": "fail",
            "reason": "",
            "value": {
                "direct_handoff_ready": False,
                "mass_in_bucket_kg": 0.0,
                "start_envelope_ready": True,
            },
        },
        {
            "name": "return_shallow_guard_ready",
            "status": "pass",
            "reason": "shallow_guard_allowed",
            "value": {
                "shallow_guard_ready": True,
                "shallow_guard_allowed": True,
                "mass_in_bucket_kg": 0.0,
                "bucket_depth_below_dig_area_plane_m": 0.08,
            },
        },
    ]


def test_unavailable_transition_status_maps_unknown_without_fabricated_facts() -> None:
    checks = (
        decision_trace_module.diagnostic_checks_from_dig_status(None)
        + decision_trace_module.diagnostic_checks_from_carry_status(None)
        + decision_trace_module.diagnostic_checks_from_dump_status(None)
        + decision_trace_module.diagnostic_checks_from_return_status(None)
    )

    assert all(check.status == "unknown" for check in checks)
    assert all(check.value is None for check in checks)
    json.dumps([check.to_dict() for check in checks], sort_keys=True)
