from __future__ import annotations

import json
from typing import Any

import testbed.planner.primitive.report.decision_trace as decision_trace_module
from testbed.planner.primitive.decision.backends.behavior_tree import (
    BEHAVIOR_TREE_DECISION_BACKEND_NAME,
    BEHAVIOR_TREE_CONTINUE_DECISION_SOURCE,
    BEHAVIOR_TREE_RETURN_COMPLETED_DECISION_SOURCE,
    BehaviorTreeDecisionBackendFactory,
    BehaviorTreeDecisionBackendFactoryPorts,
)
from testbed.planner.primitive.decision.context import PrimitiveDecisionContext
from testbed.planner.primitive.decision.contracts import (
    CompleteReturnTransitionEffect,
    MarkReturnNextDigEventSeenEffect,
    SwitchToNextSkillAfterReturnEffect,
)
from testbed.planner.primitive.decision.input import (
    PrimitiveBackendDecisionInputBuilder,
)
from testbed.planner.primitive.decision.runtime import (
    PrimitiveDecisionRuntime,
    PrimitiveDecisionRuntimeConfig,
    PrimitiveDecisionRuntimePorts,
)
from testbed.planner.primitive.decision.validation import DecisionProposalValidator
from testbed.planner.primitive.execution.runtime import PrimitiveTickPreparation
from testbed.planner.primitive.facts.capabilities import ReturnTransitionStatus
from testbed.planner.primitive.facts.backend import (
    PrimitiveBackendFactsPorts,
    PrimitiveBackendFactsSource,
)
from testbed.planner.primitive.report.decision_trace import (
    DecisionTraceAssembler,
    DecisionTraceMetadata,
)
from testbed.planner.primitive.report.decision_trace_export import (
    to_offline_rich_trace,
    to_online_compact_trace,
)
from testbed.planner.primitive.report.decision_validation_trace import (
    project_validation_result_to_trace,
)


class _TransitionFactsMustStayLazy:
    def dig_transition_status(self, obs: dict[str, Any], boundary_event: Any | None):
        raise AssertionError("BT continue fallback must not read dig transition facts")

    def carry_transition_status(self, obs: dict[str, Any], boundary_event: Any | None):
        raise AssertionError("BT continue fallback must not read carry transition facts")

    def dump_transition_status(self, obs: dict[str, Any], boundary_event: Any | None):
        raise AssertionError("BT continue fallback must not read dump transition facts")

    def return_transition_status(self, obs: dict[str, Any], boundary_event: Any | None):
        raise AssertionError("BT continue fallback must not read return transition facts")


class _ReturnTransitionReader(_TransitionFactsMustStayLazy):
    def __init__(self, status: ReturnTransitionStatus) -> None:
        self.status = status
        self.return_reads = 0

    def return_transition_status(
        self,
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> ReturnTransitionStatus:
        self.return_reads += 1
        return self.status


class _NoCompatibilityActions:
    def sync_dig_transition_reason(self, dig_facts: object) -> None:
        raise AssertionError("BT continue fallback must not sync dig reason")

    def refresh_return_transition_state(self, context: PrimitiveDecisionContext) -> None:
        raise AssertionError("BT continue fallback must not refresh return state")


def _context(skill: str = "dig") -> PrimitiveDecisionContext:
    return PrimitiveDecisionContext.from_tick(
        obs={"qpos": [1.0]},
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision=skill,
            dig_progress_updated=skill == "dig",
        ),
    )


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


def _input_builder(
    skill: str = "dig",
    *,
    transition_status_reader: object | None = None,
) -> PrimitiveBackendDecisionInputBuilder:
    return PrimitiveBackendDecisionInputBuilder.from_sources(
        facts_source=PrimitiveBackendFactsSource.from_ports(
            PrimitiveBackendFactsPorts(
                current_skill_name=lambda: skill,
                current_switch_reason=lambda: "",
                transition_status_reader=(
                    transition_status_reader or _TransitionFactsMustStayLazy()
                ),
            )
        ),
        compatibility_actions=_NoCompatibilityActions(),
    )


def _factory(
    *,
    skill: str = "dig",
    transition_status_reader: object | None = None,
) -> BehaviorTreeDecisionBackendFactory:
    return BehaviorTreeDecisionBackendFactory.from_ports(
        BehaviorTreeDecisionBackendFactoryPorts(
            input_builder=_input_builder(
                skill,
                transition_status_reader=transition_status_reader,
            )
        )
    )


def test_behavior_tree_backend_returns_backend_specific_continue_trace() -> None:
    backend = _factory(skill="dig").requested_decision_backend()

    outcome = backend.decide_context_with_trace(_context("dig"))

    assert outcome.result.decision_source == BEHAVIOR_TREE_CONTINUE_DECISION_SOURCE
    assert outcome.result.status == "no_change"
    assert outcome.result.skill_before == "dig"
    assert outcome.result.skill_after == "dig"
    assert outcome.result.switch_reason == ""
    assert outcome.result.effects == ()
    assert not outcome.result.side_effects_applied
    assert [
        (entry.node_name, entry.status, entry.reason) for entry in outcome.trace
    ] == [
        ("behavior_tree_root", "success", "selected:continue_current_skill"),
        ("return_completed_transition", "failure", "not_return_skill"),
        ("continue_current_skill", "success", "continue_current_skill"),
    ]


def test_behavior_tree_factory_has_no_legacy_compatibility_decision() -> None:
    backend = _factory(skill="carry").compatibility_decision_backend()

    assert backend.decide_context(_context("carry")) is None


def test_behavior_tree_backend_is_only_used_when_explicitly_registered() -> None:
    reader = _ReturnTransitionReader(_return_status(completed_transition=False))
    factory = _factory(skill="return", transition_status_reader=reader)
    runtime = PrimitiveDecisionRuntime.from_ports(
        PrimitiveDecisionRuntimePorts(
            backend_factories={BEHAVIOR_TREE_DECISION_BACKEND_NAME: lambda: factory}
        ),
        config=PrimitiveDecisionRuntimeConfig(
            backend_name=BEHAVIOR_TREE_DECISION_BACKEND_NAME
        ),
    )

    result = runtime.decide_tick(
        obs={"qpos": [1.0]},
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="return",
            dig_progress_updated=False,
        ),
    )

    assert result.decision_source == BEHAVIOR_TREE_CONTINUE_DECISION_SOURCE
    assert result.status == "no_change"
    assert result.skill_before == "return"
    assert result.skill_after == "return"
    assert reader.return_reads == 1


def test_behavior_tree_return_incomplete_falls_back_after_failure_trace() -> None:
    reader = _ReturnTransitionReader(_return_status(completed_transition=False))
    backend = _factory(
        skill="return",
        transition_status_reader=reader,
    ).requested_decision_backend()

    outcome = backend.decide_context_with_trace(_context("return"))

    assert reader.return_reads == 1
    assert outcome.result.decision_source == BEHAVIOR_TREE_CONTINUE_DECISION_SOURCE
    assert outcome.result.status == "no_change"
    assert outcome.result.skill_before == "return"
    assert outcome.result.skill_after == "return"
    assert outcome.result.effects == ()
    assert [
        (entry.node_name, entry.status, entry.reason) for entry in outcome.trace
    ] == [
        ("behavior_tree_root", "success", "selected:continue_current_skill"),
        (
            "return_completed_transition",
            "failure",
            "return_transition_incomplete",
        ),
        ("continue_current_skill", "success", "continue_current_skill"),
    ]


def test_behavior_tree_return_completed_requests_approved_effects() -> None:
    reader = _ReturnTransitionReader(
        _return_status(
            next_dig_event=True,
            next_or_seen_dig_event=True,
            handoff_ready=True,
            completed_transition=True,
            next_skill="dig",
            switch_reason="return_to_dig_next_dig_entry_ready",
        )
    )
    backend = _factory(
        skill="return",
        transition_status_reader=reader,
    ).requested_decision_backend()

    outcome = backend.decide_context_with_trace(_context("return"))

    assert reader.return_reads == 1
    assert outcome.result.decision_source == BEHAVIOR_TREE_RETURN_COMPLETED_DECISION_SOURCE
    assert outcome.result.status == "skill_switch"
    assert outcome.result.skill_before == "return"
    assert outcome.result.skill_after == "dig"
    assert outcome.result.switch_reason == "return_to_dig_next_dig_entry_ready"
    assert tuple(type(effect) for effect in outcome.result.effects) == (
        MarkReturnNextDigEventSeenEffect,
        CompleteReturnTransitionEffect,
        SwitchToNextSkillAfterReturnEffect,
    )
    assert outcome.result.effects[2].reason_suffix == "next_dig_entry_ready"
    assert [
        (entry.node_name, entry.status, entry.reason) for entry in outcome.trace
    ] == [
        ("behavior_tree_root", "success", "selected:return_completed_transition"),
        (
            "return_completed_transition",
            "success",
            "return_to_dig_next_dig_entry_ready",
        ),
    ]

    validation = DecisionProposalValidator.validate(
        result=outcome.result,
        backend_name=BEHAVIOR_TREE_DECISION_BACKEND_NAME,
        backend_kind="behavior_tree",
        expected_skill_before="return",
    )
    assert validation.accepted is True


def test_behavior_tree_return_completed_runtime_trace_validation_and_export() -> None:
    reader = _ReturnTransitionReader(
        _return_status(
            next_or_seen_dig_event=True,
            handoff_ready=True,
            completed_transition=True,
            next_skill="dig",
            switch_reason="return_to_dig_next_dig_entry_ready",
        )
    )
    factory = _factory(skill="return", transition_status_reader=reader)
    runtime = PrimitiveDecisionRuntime.from_ports(
        PrimitiveDecisionRuntimePorts(
            backend_factories={BEHAVIOR_TREE_DECISION_BACKEND_NAME: lambda: factory}
        ),
        config=PrimitiveDecisionRuntimeConfig(
            backend_name=BEHAVIOR_TREE_DECISION_BACKEND_NAME
        ),
    )
    context = _context("return")
    backend = runtime.requested_backend_for(BEHAVIOR_TREE_DECISION_BACKEND_NAME)

    outcome = backend.decide_context_with_trace(context)
    validation = DecisionProposalValidator.validate(
        result=outcome.result,
        backend_name=BEHAVIOR_TREE_DECISION_BACKEND_NAME,
        backend_kind="behavior_tree",
        expected_skill_before="return",
    )
    validation_projection = project_validation_result_to_trace(validation)
    bt_payload = decision_trace_module.build_behavior_tree_backend_payload(
        outcome.trace
    )
    record = DecisionTraceAssembler.assemble(
        result=outcome.result,
        backend_payload=validation_projection.with_backend_payload(bt_payload),
        metadata=DecisionTraceMetadata(
            backend_name=BEHAVIOR_TREE_DECISION_BACKEND_NAME,
            backend_kind="behavior_tree",
            selected_operation="switch_skill",
            validation_status=validation_projection.validation_status,
            reason_codes=validation_projection.reason_codes,
            diagnostic_checks=validation_projection.diagnostic_checks,
            tick_id="bt-return-tick-001",
        ),
    )

    compact = to_online_compact_trace(record)
    assert compact["backend_name"] == BEHAVIOR_TREE_DECISION_BACKEND_NAME
    assert compact["selected_operation"] == "switch_skill"
    assert compact["validation_status"] == "accepted"
    assert compact["requested_effects_summary"] == [
        {
            "effect_type": "complete_return_transition",
            "reason": "",
            "already_applied": False,
        },
        {
            "effect_type": "switch_to_next_skill_after_return",
            "reason": "next_dig_entry_ready",
            "already_applied": False,
        },
    ]
    assert "backend_payload" not in compact

    rich = to_offline_rich_trace(record)
    payload = rich["backend_payload"]
    assert payload["backend_family"] == "behavior_tree"
    assert payload["selected_path"] == [
        "behavior_tree_root",
        "return_completed_transition",
    ]
    assert payload["validation"]["status"] == "accepted"
    assert "backend_payload" not in compact
    json.dumps(compact, sort_keys=True)
    json.dumps(rich, sort_keys=True)


def test_behavior_tree_shadow_outcome_maps_to_generic_trace_payload() -> None:
    backend = _factory(skill="dig").requested_decision_backend()
    outcome = backend.decide_context_with_trace(_context("dig"))

    record = decision_trace_module.assemble_behavior_tree_shadow_decision_trace(
        result=outcome.result,
        node_trace=outcome.trace,
        tick_id="bt-tick-001",
    )

    compact = record.to_compact_dict()
    assert compact["backend_name"] == BEHAVIOR_TREE_DECISION_BACKEND_NAME
    assert compact["backend_kind"] == "behavior_tree"
    assert compact["selected_operation"] == "continue_current_skill"
    assert compact["fallback_type"] == "continue_current_skill"
    assert compact["reason_codes"] == ["bt_node_selected", "bt_continue_fallback"]
    assert "backend_payload" not in compact

    rich = record.to_rich_dict()
    payload = rich["backend_payload"]
    assert payload["backend_family"] == "behavior_tree"
    assert payload["payload_schema_version"] == "behavior_tree_payload_v1"
    assert payload["payload_kind"] == "node_trace"
    assert payload["root_status"] == "success"
    assert payload["selected_path"] == [
        "behavior_tree_root",
        "continue_current_skill",
    ]
    assert payload["node_results"] == [
        {
            "node_name": "behavior_tree_root",
            "status": "success",
            "reason": "selected:continue_current_skill",
        },
        {
            "node_name": "return_completed_transition",
            "status": "failure",
            "reason": "not_return_skill",
        },
        {
            "node_name": "continue_current_skill",
            "status": "success",
            "reason": "continue_current_skill",
        },
    ]
    assert "node_results" not in rich
    json.dumps(rich, sort_keys=True)
