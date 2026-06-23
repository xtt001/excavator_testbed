from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from typing import Any

import pytest

from testbed.planner.primitive_backend_facts import (
    BootstrapDecisionStatus,
    PrimitiveBootstrapDecisionFacts,
    PrimitiveBackendFactsAccess,
    PrimitiveTransitionStatusReader,
)
from testbed.planner.primitive_capabilities import (
    CarryTransitionStatus,
    DigTransitionStatus,
    DumpTransitionStatus,
    ReturnTransitionStatus,
)
from testbed.planner.primitive_decision_context import PrimitiveDecisionContext
from testbed.planner.primitive_decision_facts import (
    PrimitiveCarryTransitionFacts,
    PrimitiveDecisionFacts,
    PrimitiveDigTransitionFacts,
    PrimitiveDumpTransitionFacts,
    PrimitiveReturnTransitionFacts,
)
from testbed.planner.primitive_execution import PrimitiveTickPreparation


def _context() -> tuple[
    PrimitiveDecisionContext,
    dict[str, object],
    object,
    PrimitiveTickPreparation,
]:
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


def _common(context: PrimitiveDecisionContext) -> PrimitiveDecisionFacts:
    return PrimitiveDecisionFacts.from_context(
        context,
        current_skill_name="dig",
        current_switch_reason="",
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


class _RecordingStatusReader:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any], object | None]] = []
        self.dig_status = _dig_status(dig_to_carry_ready=True)
        self.carry_status = _carry_status(ready_to_dump=True)
        self.dump_status = _dump_status(ready_to_return=True)
        self.return_status = _return_status(completed_transition=True)

    def dig_transition_status(
        self,
        obs: dict[str, Any],
        boundary_event: object | None,
    ) -> DigTransitionStatus:
        self.calls.append(("dig", obs, boundary_event))
        return self.dig_status

    def carry_transition_status(
        self,
        obs: dict[str, Any],
        boundary_event: object | None,
    ) -> CarryTransitionStatus:
        self.calls.append(("carry", obs, boundary_event))
        return self.carry_status

    def dump_transition_status(
        self,
        obs: dict[str, Any],
        boundary_event: object | None,
    ) -> DumpTransitionStatus:
        self.calls.append(("dump", obs, boundary_event))
        return self.dump_status

    def return_transition_status(
        self,
        obs: dict[str, Any],
        boundary_event: object | None,
    ) -> ReturnTransitionStatus:
        self.calls.append(("return", obs, boundary_event))
        return self.return_status


class _RecordingBootstrapReader:
    def __init__(
        self,
        *,
        should_end_bootstrap: bool = True,
        bootstrap_end_mode: str = "first_qualified_dig_start",
    ) -> None:
        self.calls: list[tuple[str, dict[str, Any] | None, object | None]] = []
        self.should_end_bootstrap_value = should_end_bootstrap
        self.bootstrap_end_mode_value = bootstrap_end_mode

    def should_end_bootstrap(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: object | None,
    ) -> bool:
        self.calls.append(("should_end_bootstrap", obs, boundary_event))
        return self.should_end_bootstrap_value

    def bootstrap_end_mode(self) -> str:
        self.calls.append(("bootstrap_end_mode", None, None))
        return self.bootstrap_end_mode_value

def _access() -> tuple[
    PrimitiveBackendFactsAccess,
    _RecordingStatusReader,
    PrimitiveDecisionContext,
    PrimitiveDecisionFacts,
    dict[str, object],
    object,
    PrimitiveTickPreparation,
]:
    context, obs, boundary_event, preparation = _context()
    common = _common(context)
    reader = _RecordingStatusReader()
    access = PrimitiveBackendFactsAccess.from_reader(
        context=context,
        common=common,
        transition_status_reader=reader,
    )
    return access, reader, context, common, obs, boundary_event, preparation


def _access_with_bootstrap_reader(
    *,
    current_skill_name: str = "bootstrap",
    bootstrap_reader: _RecordingBootstrapReader | None = None,
) -> tuple[
    PrimitiveBackendFactsAccess,
    _RecordingStatusReader,
    _RecordingBootstrapReader,
    PrimitiveDecisionContext,
    PrimitiveDecisionFacts,
    dict[str, object],
    object,
    PrimitiveTickPreparation,
]:
    context, obs, boundary_event, preparation = _context()
    common = PrimitiveDecisionFacts.from_context(
        context,
        current_skill_name=current_skill_name,
        current_switch_reason="",
    )
    transition_reader = _RecordingStatusReader()
    bootstrap_reader = bootstrap_reader or _RecordingBootstrapReader()
    access = PrimitiveBackendFactsAccess.from_reader(
        context=context,
        common=common,
        transition_status_reader=transition_reader,
        bootstrap_decision_reader=bootstrap_reader,
    )
    return (
        access,
        transition_reader,
        bootstrap_reader,
        context,
        common,
        obs,
        boundary_event,
        preparation,
    )


def test_backend_facts_access_preserves_context_and_common_identity() -> None:
    access, _, context, common, obs, boundary_event, preparation = _access()

    assert access.context is context
    assert access.common is common
    assert access.common.obs is obs
    assert access.common.boundary_event is boundary_event
    assert access.common.preparation is preparation


def test_backend_facts_access_transition_views_reuse_common_identity() -> None:
    access, reader, _, common, _, _, _ = _access()

    dig_facts = access.dig_transition()
    carry_facts = access.carry_transition()
    dump_facts = access.dump_transition()
    return_facts = access.return_transition()

    assert isinstance(dig_facts, PrimitiveDigTransitionFacts)
    assert isinstance(carry_facts, PrimitiveCarryTransitionFacts)
    assert isinstance(dump_facts, PrimitiveDumpTransitionFacts)
    assert isinstance(return_facts, PrimitiveReturnTransitionFacts)
    assert dig_facts.common is common
    assert carry_facts.common is common
    assert dump_facts.common is common
    assert return_facts.common is common
    assert dig_facts.status is reader.dig_status
    assert carry_facts.status is reader.carry_status
    assert dump_facts.status is reader.dump_status
    assert return_facts.status is reader.return_status


def test_backend_facts_access_transition_reads_are_lazy_and_branch_local() -> None:
    access, reader, _, _, obs, boundary_event, _ = _access()

    assert reader.calls == []

    assert access.carry_transition().status is reader.carry_status
    assert reader.calls == [("carry", obs, boundary_event)]

    assert access.return_transition().status is reader.return_status
    assert reader.calls == [
        ("carry", obs, boundary_event),
        ("return", obs, boundary_event),
    ]


def test_bootstrap_facts_view_preserves_identity_and_projects_status() -> None:
    (
        access,
        transition_reader,
        bootstrap_reader,
        context,
        common,
        obs,
        boundary_event,
        preparation,
    ) = _access_with_bootstrap_reader(
        bootstrap_reader=_RecordingBootstrapReader(
            should_end_bootstrap=True,
            bootstrap_end_mode="first_qualified_dig_start",
        )
    )

    bootstrap_facts = access.bootstrap_decision()

    assert isinstance(bootstrap_facts, PrimitiveBootstrapDecisionFacts)
    assert bootstrap_facts.common is common
    assert bootstrap_facts.context is context
    assert bootstrap_facts.obs is obs
    assert bootstrap_facts.boundary_event is boundary_event
    assert bootstrap_facts.preparation is preparation
    assert bootstrap_facts.current_skill_name == "bootstrap"
    assert bootstrap_facts.skill_name_before_decision == "dig"
    assert bootstrap_facts.should_end_bootstrap is True
    assert bootstrap_facts.bootstrap_end_mode == "first_qualified_dig_start"
    assert bootstrap_facts.next_skill_after_bootstrap == "dig"
    assert bootstrap_facts.status == BootstrapDecisionStatus(
        current_skill_name="bootstrap",
        should_end_bootstrap=True,
        bootstrap_end_mode="first_qualified_dig_start",
        next_skill_after_bootstrap="dig",
    )
    assert transition_reader.calls == []
    assert bootstrap_reader.calls == [
        ("bootstrap_end_mode", None, None),
        ("should_end_bootstrap", obs, boundary_event),
    ]


def test_bootstrap_facts_view_is_backend_facing_read_only_shape() -> None:
    access, _, _, _, _, _, _, _ = _access_with_bootstrap_reader()

    bootstrap_facts = access.bootstrap_decision()

    assert {field.name for field in fields(PrimitiveBootstrapDecisionFacts)} == {
        "common",
        "status",
    }
    assert {
        "self",
        "planner",
        "policy",
        "callback",
        "provider",
        "applier",
        "effect",
        "mutation",
        "setter",
        "refresh",
        "sync",
        "residual",
    }.isdisjoint({field.name for field in fields(PrimitiveBootstrapDecisionFacts)})
    with pytest.raises(FrozenInstanceError):
        bootstrap_facts.status = bootstrap_facts.status


def test_backend_facts_bootstrap_decision_is_lazy_and_read_only() -> None:
    access, transition_reader, bootstrap_reader, _, _, obs, boundary_event, _ = (
        _access_with_bootstrap_reader()
    )

    assert bootstrap_reader.calls == []
    assert transition_reader.calls == []

    bootstrap_facts = access.bootstrap_decision()

    assert bootstrap_facts.status.next_skill_after_bootstrap == "dig"
    assert bootstrap_reader.calls == [
        ("bootstrap_end_mode", None, None),
        ("should_end_bootstrap", obs, boundary_event),
    ]
    assert transition_reader.calls == []


def test_backend_facts_transition_reads_do_not_call_bootstrap_gates() -> None:
    access, transition_reader, bootstrap_reader, _, _, obs, boundary_event, _ = (
        _access_with_bootstrap_reader()
    )

    assert access.dig_transition().status is transition_reader.dig_status

    assert transition_reader.calls == [("dig", obs, boundary_event)]
    assert bootstrap_reader.calls == []


def test_backend_facts_access_public_api_is_read_only() -> None:
    access, _, _, _, _, _, _ = _access()
    public_names = {name for name in dir(access) if not name.startswith("_")}
    field_names = {field.name for field in fields(PrimitiveBackendFactsAccess)}
    protocol_names = set(PrimitiveTransitionStatusReader.__dict__)

    assert {
        "sync_dig_transition_reason",
        "refresh_return_transition_state",
        "handle_residual_pre_dig_align",
        "apply_effect",
        "effect_applier",
        "set_skill",
        "planner",
        "policy",
        "self",
        "mutation",
    }.isdisjoint(public_names)
    assert {
        "callback",
        "provider",
        "applier",
        "effect",
        "setter",
        "refresh",
        "sync",
        "residual",
    }.isdisjoint(field_names)
    assert {
        "sync_dig_transition_reason",
        "refresh_return_transition_state",
        "handle_residual_pre_dig_align",
    }.isdisjoint(protocol_names)
    assert {
        "context",
        "common",
        "_transition_status_reader",
        "_bootstrap_decision_reader",
    }.issubset(field_names)
