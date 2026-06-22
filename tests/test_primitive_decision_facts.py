from __future__ import annotations

from dataclasses import fields

from testbed.planner.primitive_decision_context import PrimitiveDecisionContext
from testbed.planner.primitive_capabilities import (
    CarryTransitionStatus,
    DigTransitionStatus,
    DumpTransitionStatus,
    ReturnTransitionStatus,
)
from testbed.planner.primitive_decision_facts import (
    PrimitiveCarryTransitionFacts,
    PrimitiveDecisionFacts,
    PrimitiveDigTransitionFacts,
    PrimitiveDumpTransitionFacts,
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


def test_dig_transition_facts_preserve_common_and_status_identity() -> None:
    context, obs, boundary_event, preparation = _context()
    common = PrimitiveDecisionFacts.from_context(
        context,
        current_skill_name="dig",
        current_switch_reason="",
    )
    status = _dig_status(
        dig_to_carry_ready=True,
        dig_to_carry_reason="boundary_confirmed",
    )

    dig_facts = PrimitiveDigTransitionFacts(common=common, status=status)

    assert dig_facts.common is common
    assert dig_facts.status is status
    assert dig_facts.context is context
    assert dig_facts.obs is obs
    assert dig_facts.boundary_event is boundary_event
    assert dig_facts.preparation is preparation
    assert dig_facts.current_skill_name == "dig"
    assert dig_facts.skill_name_before_decision == "dig"
    assert dig_facts.dig_to_carry_ready is True
    assert dig_facts.dig_to_carry_reason == "boundary_confirmed"


def test_dig_transition_facts_are_frozen_and_backend_facing_only() -> None:
    field_names = {field.name for field in fields(PrimitiveDigTransitionFacts)}

    assert field_names == {"common", "status"}
    assert {
        "self",
        "planner",
        "policy",
        "callback",
        "provider",
        "applier",
        "effect",
        "sync",
        "set_dig_to_carry_reason",
    }.isdisjoint(field_names)


def test_carry_transition_facts_preserve_common_and_status_identity() -> None:
    context, obs, boundary_event, preparation = _context()
    common = PrimitiveDecisionFacts.from_context(
        context,
        current_skill_name="carry",
        current_switch_reason="dig_to_carry_loaded",
    )
    status = _carry_status(
        ready_to_dump=True,
        carry_to_dump_reason="dump_committed_boundary",
        carry_release_safety_done=True,
        dump_complete_event=True,
        next_dump_ready_hold_count=3,
    )

    carry_facts = PrimitiveCarryTransitionFacts(common=common, status=status)

    assert carry_facts.common is common
    assert carry_facts.status is status
    assert carry_facts.context is context
    assert carry_facts.obs is obs
    assert carry_facts.boundary_event is boundary_event
    assert carry_facts.preparation is preparation
    assert carry_facts.current_skill_name == "carry"
    assert carry_facts.skill_name_before_decision == "dig"
    assert carry_facts.ready_to_dump is True
    assert carry_facts.carry_to_dump_reason == "dump_committed_boundary"
    assert carry_facts.carry_release_safety_done is True
    assert carry_facts.dump_complete_event is True
    assert carry_facts.next_dump_ready_hold_count == 3


def test_carry_transition_facts_are_frozen_and_backend_facing_only() -> None:
    field_names = {field.name for field in fields(PrimitiveCarryTransitionFacts)}

    assert field_names == {"common", "status"}
    assert {
        "self",
        "planner",
        "policy",
        "callback",
        "provider",
        "applier",
        "effect",
        "sync",
        "mutation",
        "setter",
        "refresh",
    }.isdisjoint(field_names)


def test_dump_transition_facts_preserve_common_and_status_identity() -> None:
    context, obs, boundary_event, preparation = _context()
    common = PrimitiveDecisionFacts.from_context(
        context,
        current_skill_name="dump",
        current_switch_reason="carry_to_dump_target_ready",
    )
    status = _dump_status(
        ready_to_return=True,
        dump_to_return_reason="dump_to_return_mass_low",
        coverage_completion_reason="dump_mass_low",
        next_dump_done_hold_count=2,
    )

    dump_facts = PrimitiveDumpTransitionFacts(common=common, status=status)

    assert dump_facts.common is common
    assert dump_facts.status is status
    assert dump_facts.context is context
    assert dump_facts.obs is obs
    assert dump_facts.boundary_event is boundary_event
    assert dump_facts.preparation is preparation
    assert dump_facts.current_skill_name == "dump"
    assert dump_facts.skill_name_before_decision == "dig"
    assert dump_facts.ready_to_return is True
    assert dump_facts.dump_to_return_reason == "dump_to_return_mass_low"
    assert dump_facts.coverage_completion_reason == "dump_mass_low"
    assert dump_facts.next_dump_done_hold_count == 2


def test_dump_transition_facts_are_frozen_and_backend_facing_only() -> None:
    field_names = {field.name for field in fields(PrimitiveDumpTransitionFacts)}

    assert field_names == {"common", "status"}
    assert {
        "self",
        "planner",
        "policy",
        "callback",
        "provider",
        "applier",
        "effect",
        "sync",
        "mutation",
        "setter",
        "refresh",
    }.isdisjoint(field_names)
