from __future__ import annotations

from dataclasses import fields

from testbed.planner.primitive_decision_context import PrimitiveDecisionContext
from testbed.planner.primitive_capabilities import ReturnTransitionStatus
from testbed.planner.primitive_decision_facts import (
    PrimitiveDecisionFacts,
    PrimitiveReturnTransitionFacts,
)
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


def test_return_transition_facts_preserve_common_and_status_identity() -> None:
    context, obs, boundary_event, preparation = _context()
    common = PrimitiveDecisionFacts.from_context(
        context,
        current_skill_name="return",
        current_switch_reason="dump_to_return_mass_low",
    )
    status = _return_status(
        completed_transition=True,
        switch_reason="return_to_dig_next_dig_entry_ready",
    )

    return_facts = PrimitiveReturnTransitionFacts(common=common, status=status)

    assert return_facts.common is common
    assert return_facts.status is status
    assert return_facts.context is context
    assert return_facts.obs is obs
    assert return_facts.boundary_event is boundary_event
    assert return_facts.preparation is preparation
    assert return_facts.current_skill_name == "return"
    assert return_facts.skill_name_before_decision == "dig"
    assert return_facts.completed_transition is True
    assert return_facts.switch_reason == "return_to_dig_next_dig_entry_ready"


def test_return_transition_facts_are_frozen_and_backend_facing_only() -> None:
    field_names = {field.name for field in fields(PrimitiveReturnTransitionFacts)}

    assert field_names == {"common", "status"}
    assert {
        "self",
        "planner",
        "policy",
        "callback",
        "provider",
        "applier",
        "effect",
        "refresh_return_transition_state",
    }.isdisjoint(field_names)
