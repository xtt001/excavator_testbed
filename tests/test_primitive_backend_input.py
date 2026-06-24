from __future__ import annotations

from dataclasses import fields
from typing import Any

from testbed.planner.primitive.facts.backend import (
    PrimitiveBackendFactsAccess,
    PrimitiveBackendFactsPorts,
    PrimitiveBackendFactsSource,
)
from testbed.planner.primitive.decision.input import (
    PrimitiveBackendDecisionInput,
    PrimitiveBackendDecisionInputBuilder,
)
from testbed.planner.primitive.decision.capabilities import (
    PrimitiveDecisionCompatibilityActions,
)
from testbed.planner.primitive.decision.context import PrimitiveDecisionContext
from testbed.planner.primitive.facts.decision import PrimitiveDecisionFacts
from testbed.planner.primitive.execution.runtime import PrimitiveTickPreparation


def _context() -> PrimitiveDecisionContext:
    boundary_event = object()
    return PrimitiveDecisionContext.from_tick(
        obs={"qpos": [1.0]},
        boundary_event=boundary_event,
        preparation=PrimitiveTickPreparation(
            boundary_event=boundary_event,
            skill_name_before_decision="dig",
            dig_progress_updated=True,
        ),
    )


class _FakeFactsSource:
    def __init__(self) -> None:
        self.calls: list[tuple[str, PrimitiveDecisionContext, PrimitiveDecisionFacts | None]] = []
        self.first_common: PrimitiveDecisionFacts | None = None
        self.second_common: PrimitiveDecisionFacts | None = None
        self.backend_facts_result: PrimitiveBackendFactsAccess | object | None = None

    def decision_facts(self, context: PrimitiveDecisionContext) -> PrimitiveDecisionFacts:
        common = PrimitiveDecisionFacts.from_context(
            context,
            current_skill_name="dig",
            current_switch_reason="",
        )
        if self.first_common is None:
            self.first_common = common
        else:
            self.second_common = common
        self.calls.append(("decision_facts", context, None))
        return common

    def backend_facts(
        self,
        context: PrimitiveDecisionContext,
        *,
        facts: PrimitiveDecisionFacts | None = None,
    ) -> PrimitiveBackendFactsAccess | object:
        self.calls.append(("backend_facts", context, facts))
        self.backend_facts_result = _FakeBackendFacts(common=facts)
        return self.backend_facts_result


class _FakeBackendFacts:
    def __init__(self, common: PrimitiveDecisionFacts | None) -> None:
        self.common = common


class _FakeCompatibilityActions:
    def sync_dig_transition_reason(self, dig_facts: object) -> None:
        raise AssertionError("input construction must not sync dig reason")

    def refresh_return_transition_state(self, context: PrimitiveDecisionContext) -> None:
        raise AssertionError("input construction must not refresh return state")

    def handle_residual_pre_dig_align(self, context: PrimitiveDecisionContext) -> bool:
        raise AssertionError("input construction must not handle residual")


class _FakeTransitionStatusReader:
    def dig_transition_status(self, obs, boundary_event):
        raise AssertionError("input construction must not read dig transition facts")

    def carry_transition_status(self, obs, boundary_event):
        raise AssertionError("input construction must not read carry transition facts")

    def dump_transition_status(self, obs, boundary_event):
        raise AssertionError("input construction must not read dump transition facts")

    def return_transition_status(self, obs, boundary_event):
        raise AssertionError("input construction must not read return transition facts")


def test_backend_decision_input_from_context_reuses_common_identity() -> None:
    context = _context()
    facts_source = _FakeFactsSource()
    actions = _FakeCompatibilityActions()

    decision_input = PrimitiveBackendDecisionInput.from_context(
        context,
        facts_source=facts_source,
        compatibility_actions=actions,
    )

    assert decision_input.context is context
    assert decision_input.backend_facts is facts_source.backend_facts_result
    assert decision_input.compatibility_actions is actions
    assert decision_input.common is facts_source.first_common
    assert facts_source.calls == [
        ("decision_facts", context, None),
        ("backend_facts", context, facts_source.first_common),
    ]


def test_backend_decision_input_builder_uses_backend_facts_source_boundary() -> None:
    context = _context()
    facts_source = PrimitiveBackendFactsSource.from_ports(
        PrimitiveBackendFactsPorts(
            current_skill_name=lambda: "dig",
            current_switch_reason=lambda: "loaded",
            transition_status_reader=_FakeTransitionStatusReader(),
        )
    )
    actions = _FakeCompatibilityActions()

    decision_input = PrimitiveBackendDecisionInputBuilder.from_sources(
        facts_source=facts_source,
        compatibility_actions=actions,
    ).build(context)

    assert decision_input.context is context
    assert decision_input.compatibility_actions is actions
    assert decision_input.common.current_skill_name == "dig"
    assert decision_input.common.current_switch_reason == "loaded"
    assert decision_input.backend_facts.common is decision_input.common


def test_backend_decision_input_public_shape_avoids_planner_and_callback_fields() -> None:
    field_names = {field.name for field in fields(PrimitiveBackendDecisionInput)}
    public_names = {
        name for name in dir(PrimitiveBackendDecisionInput) if not name.startswith("_")
    }

    assert {"context", "backend_facts", "compatibility_actions"}.issubset(
        field_names
    )
    assert {
        "planner",
        "policy",
        "self",
        "callback",
        "provider",
        "applier",
        "effect_applier",
        "mutation_callback",
    }.isdisjoint(field_names)
    assert {
        "apply_effect",
        "effect_applier",
        "planner",
        "policy",
        "self",
        "set_skill",
    }.isdisjoint(public_names)


def test_backend_decision_input_common_reread_is_explicit_for_compatibility_actions() -> None:
    context = _context()
    facts_source = _FakeFactsSource()
    decision_input = PrimitiveBackendDecisionInput.from_context(
        context,
        facts_source=facts_source,
        compatibility_actions=_FakeCompatibilityActions(),
    )

    refreshed = decision_input.rebuild_common_facts_after_compatibility_action()

    assert refreshed is facts_source.second_common
    assert refreshed is not decision_input.common
    assert facts_source.calls == [
        ("decision_facts", context, None),
        ("backend_facts", context, facts_source.first_common),
        ("decision_facts", context, None),
    ]
