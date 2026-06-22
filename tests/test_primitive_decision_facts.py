from __future__ import annotations

from dataclasses import fields

from testbed.planner.primitive_decision_context import PrimitiveDecisionContext
from testbed.planner.primitive_decision_facts import PrimitiveDecisionFacts
from testbed.planner.primitive_execution import PrimitiveTickPreparation


def _context() -> tuple[PrimitiveDecisionContext, dict[str, object], object, PrimitiveTickPreparation]:
    obs: dict[str, object] = {"qpos": [1.0]}
    boundary_event = object()
    preparation = PrimitiveTickPreparation(
        boundary_event=boundary_event,
        skill_name_before_decision="dig",
        dig_progress_updated=True,
    )
    return (
        PrimitiveDecisionContext.from_tick(
            obs=obs,
            boundary_event=boundary_event,
            preparation=preparation,
        ),
        obs,
        boundary_event,
        preparation,
    )


def test_decision_facts_preserve_context_identity_and_mirror_context_accessors() -> None:
    context, obs, boundary_event, preparation = _context()

    facts = PrimitiveDecisionFacts.from_context(
        context,
        current_skill_name="carry",
        current_switch_reason="dig_to_carry_loaded",
    )

    assert facts.context is context
    assert facts.obs is obs
    assert facts.boundary_event is boundary_event
    assert facts.preparation is preparation
    assert facts.skill_name_before_decision == "dig"
    assert facts.dig_progress_updated is True


def test_decision_facts_normalize_current_skill_and_reason_to_strings() -> None:
    context, _, _, _ = _context()

    facts = PrimitiveDecisionFacts.from_context(
        context,
        current_skill_name=123,
        current_switch_reason=None,
    )

    assert facts.current_skill_name == "123"
    assert facts.current_switch_reason == "None"


def test_decision_facts_expose_current_skill_helper() -> None:
    context, _, _, _ = _context()
    facts = PrimitiveDecisionFacts.from_context(
        context,
        current_skill_name="return",
        current_switch_reason="",
    )

    assert facts.is_current_skill("return") is True
    assert facts.is_current_skill("dig") is False


def test_decision_facts_do_not_expose_mutation_or_status_provider_fields() -> None:
    field_names = {field.name for field in fields(PrimitiveDecisionFacts)}

    assert field_names == {
        "context",
        "current_skill_name",
        "current_switch_reason",
    }
    assert {
        "planner",
        "self",
        "dig_transition_status",
        "carry_transition_status",
        "dump_transition_status",
        "return_transition_status",
        "effect_applier",
        "set_skill",
    }.isdisjoint(field_names)
