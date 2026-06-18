from __future__ import annotations

from typing import Any

from testbed.planner.primitive_backend import (
    LegacyFSMBackendAdapter,
    LegacyFSMBootstrapBranch,
    LegacyFSMBootstrapConfig,
    LegacyFSMCarryBranch,
    LegacyFSMCarryConfig,
    LegacyFSMDumpBranch,
    LegacyFSMDumpConfig,
    LegacyFSMDigBranch,
    LegacyFSMDigConfig,
    LegacyFSMReturnBranch,
    LegacyFSMReturnConfig,
)
from testbed.planner.primitive_capabilities import (
    CarryTransitionStatus,
    DumpTransitionStatus,
    ReturnTransitionStatus,
)
from testbed.planner.primitive_decision import LEGACY_FSM_DECISION_SOURCE
from testbed.planner.primitive_execution import PrimitiveTickPreparation


def test_legacy_fsm_backend_adapter_wraps_existing_switch_callback() -> None:
    obs: dict[str, Any] = {"qpos": [1.0]}
    boundary_event = object()
    state = {"skill": "dig", "reason": ""}
    calls: list[tuple[dict[str, Any], object, str]] = []

    def maybe_switch_skill(*, obs: dict[str, Any], boundary_event: object) -> None:
        calls.append((obs, boundary_event, state["skill"]))
        state["skill"] = "carry"
        state["reason"] = "dig_to_carry_boundary_confirmed"

    backend = LegacyFSMBackendAdapter(
        maybe_switch_skill=maybe_switch_skill,
        current_skill_name=lambda: state["skill"],
        current_switch_reason=lambda: state["reason"],
    )

    result = backend.decide_tick(
        obs=obs,
        boundary_event=boundary_event,
        preparation=PrimitiveTickPreparation(
            boundary_event=boundary_event,
            skill_name_before_decision="dig",
            dig_progress_updated=True,
        ),
    )

    assert calls == [(obs, boundary_event, "dig")]
    assert result.decision_source == LEGACY_FSM_DECISION_SOURCE
    assert result.status == "skill_switch"
    assert result.skill_before == "dig"
    assert result.skill_after == "carry"
    assert result.switch_reason == "dig_to_carry_boundary_confirmed"


def test_legacy_fsm_bootstrap_branch_selects_pre_dig_align_when_enabled() -> None:
    obs: dict[str, Any] = {"qpos": [1.0]}
    boundary_event = object()
    state = {"skill": "bootstrap"}
    switches: list[tuple[str, str]] = []
    branch = LegacyFSMBootstrapBranch(
        config=LegacyFSMBootstrapConfig(
            bootstrap_skill_name="bootstrap",
            pre_dig_align_skill_name="pre_dig_align",
        ),
        current_skill_name=lambda: state["skill"],
        should_end_bootstrap=lambda *, obs, boundary_event: True,
        bootstrap_end_mode=lambda: "first_qualified_dig_start",
        should_pre_dig_align_before_dig=lambda: True,
        set_skill=lambda skill, reason: switches.append((skill, reason)),
    )

    handled = branch.maybe_handle(obs=obs, boundary_event=boundary_event)

    assert handled is True
    assert switches == [("pre_dig_align", "bootstrap_to_pre_dig_align")]


def test_legacy_fsm_bootstrap_branch_ignores_non_bootstrap_skill() -> None:
    branch = LegacyFSMBootstrapBranch(
        config=LegacyFSMBootstrapConfig(
            bootstrap_skill_name="bootstrap",
            pre_dig_align_skill_name="pre_dig_align",
        ),
        current_skill_name=lambda: "dig",
        should_end_bootstrap=lambda *, obs, boundary_event: True,
        bootstrap_end_mode=lambda: "disabled",
        should_pre_dig_align_before_dig=lambda: False,
        set_skill=lambda skill, reason: None,
    )

    assert branch.maybe_handle(obs={}, boundary_event=None) is False


def test_legacy_fsm_dig_branch_completes_dig_to_carry_in_order() -> None:
    obs: dict[str, Any] = {"qpos": [1.0]}
    boundary_event = object()
    events: list[tuple[str, str]] = []
    branch = LegacyFSMDigBranch(
        config=LegacyFSMDigConfig(dig_skill_name="dig"),
        current_skill_name=lambda: "dig",
        dig_exit_guard_ready=lambda obs: False,
        increment_dig_exit_guard_replan_count=lambda: events.append(("inc", "exit")),
        reject_active_coverage_corridor=lambda obs, reason: events.append(
            ("reject", reason)
        ),
        restart_after_failed_dig=lambda reason, obs: events.append(
            ("restart", reason)
        ),
        dig_bad_replan_ready=lambda obs: False,
        increment_dig_bad_replan_count=lambda: events.append(("inc", "bad")),
        dig_complete_boundary_low_payload=lambda obs, boundary_event: False,
        dig_to_carry_ready=lambda *, obs, boundary_event: True,
        complete_cell_entry_dig=lambda obs: events.append(("complete", "cell")),
        complete_coverage_dig=lambda obs: events.append(("complete", "coverage")),
        dig_to_carry_reason=lambda: "boundary_confirmed",
        set_skill=lambda skill, reason: events.append((skill, reason)),
    )

    handled = branch.maybe_handle(obs=obs, boundary_event=boundary_event)

    assert handled is True
    assert events == [
        ("complete", "cell"),
        ("complete", "coverage"),
        ("carry", "dig_to_carry_boundary_confirmed"),
    ]


def test_legacy_fsm_dig_branch_ignores_non_dig_skill() -> None:
    branch = LegacyFSMDigBranch(
        config=LegacyFSMDigConfig(dig_skill_name="dig"),
        current_skill_name=lambda: "carry",
        dig_exit_guard_ready=lambda obs: True,
        increment_dig_exit_guard_replan_count=lambda: None,
        reject_active_coverage_corridor=lambda obs, reason: None,
        restart_after_failed_dig=lambda reason, obs: None,
        dig_bad_replan_ready=lambda obs: True,
        increment_dig_bad_replan_count=lambda: None,
        dig_complete_boundary_low_payload=lambda obs, boundary_event: True,
        dig_to_carry_ready=lambda *, obs, boundary_event: True,
        complete_cell_entry_dig=lambda obs: None,
        complete_coverage_dig=lambda obs: None,
        dig_to_carry_reason=lambda: "",
        set_skill=lambda skill, reason: None,
    )

    assert branch.maybe_handle(obs={}, boundary_event=None) is False


def test_legacy_fsm_carry_branch_release_safety_handoffs_to_return() -> None:
    obs: dict[str, Any] = {"qpos": [1.0]}
    events: list[tuple[str, str]] = []
    status = CarryTransitionStatus(
        mass_in_bucket_kg=0.0,
        deposited_mass_in_target_box_kg=20.0,
        deposit_delta_since_cycle_start_kg=10.0,
        semantic_boundary_profile_active=True,
        dump_committed_event=False,
        release_onset_event=False,
        dump_complete_event=False,
        legacy_dump_start_event=False,
        carry_release_safety_done=True,
        dump_ready=False,
        next_dump_ready_hold_count=0,
        ready_to_dump=False,
        carry_to_dump_reason="",
        carry_to_return_reason="carry_to_return_release_safety",
    )
    branch = LegacyFSMCarryBranch(
        config=LegacyFSMCarryConfig(carry_skill_name="carry"),
        current_skill_name=lambda: "carry",
        carry_transition_status=lambda obs, boundary_event: status,
        complete_coverage_dump=lambda obs, reason: events.append(
            ("complete_dump", reason)
        ),
        set_return_or_direct_handoff=lambda obs, reason: events.append(
            ("return", reason)
        ),
        set_dump_ready_hold_count=lambda value: events.append(("hold", str(value))),
        deposited_mass=lambda obs: 20.0,
        set_dump_start_deposited_mass=lambda value: events.append(
            ("deposit", str(value))
        ),
        set_skill=lambda skill, reason: events.append((skill, reason)),
    )

    handled = branch.maybe_handle(obs=obs, boundary_event=None)

    assert handled is True
    assert events == [
        ("complete_dump", "carry_release_safety"),
        ("return", "carry_to_return_release_safety"),
    ]


def test_legacy_fsm_carry_branch_committed_boundary_switches_to_dump() -> None:
    obs: dict[str, Any] = {"qpos": [1.0]}
    boundary_event = object()
    state = {"hold": 0, "deposit": 0.0}
    events: list[tuple[str, str]] = []
    status = CarryTransitionStatus(
        mass_in_bucket_kg=120.0,
        deposited_mass_in_target_box_kg=8.5,
        deposit_delta_since_cycle_start_kg=8.5,
        semantic_boundary_profile_active=True,
        dump_committed_event=True,
        release_onset_event=False,
        dump_complete_event=False,
        legacy_dump_start_event=False,
        carry_release_safety_done=False,
        dump_ready=False,
        next_dump_ready_hold_count=3,
        ready_to_dump=True,
        carry_to_dump_reason="dump_committed_boundary",
        carry_to_return_reason="",
    )
    branch = LegacyFSMCarryBranch(
        config=LegacyFSMCarryConfig(carry_skill_name="carry"),
        current_skill_name=lambda: "carry",
        carry_transition_status=lambda obs, boundary_event: status,
        complete_coverage_dump=lambda obs, reason: events.append(
            ("complete_dump", reason)
        ),
        set_return_or_direct_handoff=lambda obs, reason: events.append(
            ("return", reason)
        ),
        set_dump_ready_hold_count=lambda value: state.__setitem__("hold", value),
        deposited_mass=lambda obs: 8.5,
        set_dump_start_deposited_mass=lambda value: state.__setitem__(
            "deposit",
            value,
        ),
        set_skill=lambda skill, reason: events.append((skill, reason)),
    )

    handled = branch.maybe_handle(obs=obs, boundary_event=boundary_event)

    assert handled is True
    assert state == {"hold": 3, "deposit": 8.5}
    assert events == [("dump", "carry_to_dump_dump_committed_boundary")]


def test_legacy_fsm_carry_branch_ignores_non_carry_skill() -> None:
    branch = LegacyFSMCarryBranch(
        config=LegacyFSMCarryConfig(carry_skill_name="carry"),
        current_skill_name=lambda: "dump",
        carry_transition_status=lambda obs, boundary_event: CarryTransitionStatus(
            mass_in_bucket_kg=0.0,
            deposited_mass_in_target_box_kg=0.0,
            deposit_delta_since_cycle_start_kg=0.0,
            semantic_boundary_profile_active=False,
            dump_committed_event=False,
            release_onset_event=False,
            dump_complete_event=False,
            legacy_dump_start_event=False,
            carry_release_safety_done=True,
            dump_ready=False,
            next_dump_ready_hold_count=0,
            ready_to_dump=False,
            carry_to_dump_reason="",
            carry_to_return_reason="carry_to_return_release_safety",
        ),
        complete_coverage_dump=lambda obs, reason: None,
        set_return_or_direct_handoff=lambda obs, reason: None,
        set_dump_ready_hold_count=lambda value: None,
        deposited_mass=lambda obs: 0.0,
        set_dump_start_deposited_mass=lambda value: None,
        set_skill=lambda skill, reason: None,
    )

    assert branch.maybe_handle(obs={}, boundary_event=None) is False


def test_legacy_fsm_dump_branch_boundary_handoffs_to_return() -> None:
    obs: dict[str, Any] = {"qpos": [1.0]}
    events: list[tuple[str, str]] = []
    status = DumpTransitionStatus(
        mass_in_bucket_kg=0.0,
        deposited_mass_in_target_box_kg=20.0,
        deposit_delta_since_dump_start_kg=10.0,
        semantic_boundary_profile_active=True,
        dump_complete_event=True,
        legacy_dump_end_event=False,
        boundary_dump_done=True,
        dump_done_mass_low=False,
        next_dump_done_hold_count=0,
        ready_to_return=True,
        coverage_completion_reason="dump_complete_boundary",
        dump_to_return_reason="dump_to_return_dump_complete_boundary",
    )
    branch = LegacyFSMDumpBranch(
        config=LegacyFSMDumpConfig(dump_skill_name="dump"),
        current_skill_name=lambda: "dump",
        dump_transition_status=lambda obs, boundary_event: status,
        complete_coverage_dump=lambda obs, reason: events.append(
            ("complete_dump", reason)
        ),
        set_return_or_direct_handoff=lambda obs, reason: events.append(
            ("return", reason)
        ),
        set_dump_done_hold_count=lambda value: events.append(("hold", str(value))),
    )

    handled = branch.maybe_handle(obs=obs, boundary_event=object())

    assert handled is True
    assert events == [
        ("complete_dump", "dump_complete_boundary"),
        ("return", "dump_to_return_dump_complete_boundary"),
    ]


def test_legacy_fsm_dump_branch_mass_low_hold_switches_to_return() -> None:
    obs: dict[str, Any] = {"qpos": [1.0]}
    state = {"hold": 0}
    events: list[tuple[str, str]] = []
    status = DumpTransitionStatus(
        mass_in_bucket_kg=5.0,
        deposited_mass_in_target_box_kg=20.0,
        deposit_delta_since_dump_start_kg=10.0,
        semantic_boundary_profile_active=False,
        dump_complete_event=False,
        legacy_dump_end_event=False,
        boundary_dump_done=False,
        dump_done_mass_low=True,
        next_dump_done_hold_count=2,
        ready_to_return=True,
        coverage_completion_reason="dump_mass_low",
        dump_to_return_reason="dump_to_return_mass_low",
    )
    branch = LegacyFSMDumpBranch(
        config=LegacyFSMDumpConfig(dump_skill_name="dump"),
        current_skill_name=lambda: "dump",
        dump_transition_status=lambda obs, boundary_event: status,
        complete_coverage_dump=lambda obs, reason: events.append(
            ("complete_dump", reason)
        ),
        set_return_or_direct_handoff=lambda obs, reason: events.append(
            ("return", reason)
        ),
        set_dump_done_hold_count=lambda value: state.__setitem__("hold", value),
    )

    handled = branch.maybe_handle(obs=obs, boundary_event=None)

    assert handled is True
    assert state == {"hold": 2}
    assert events == [
        ("complete_dump", "dump_mass_low"),
        ("return", "dump_to_return_mass_low"),
    ]


def test_legacy_fsm_dump_branch_ignores_non_dump_skill() -> None:
    branch = LegacyFSMDumpBranch(
        config=LegacyFSMDumpConfig(dump_skill_name="dump"),
        current_skill_name=lambda: "return",
        dump_transition_status=lambda obs, boundary_event: DumpTransitionStatus(
            mass_in_bucket_kg=0.0,
            deposited_mass_in_target_box_kg=0.0,
            deposit_delta_since_dump_start_kg=0.0,
            semantic_boundary_profile_active=False,
            dump_complete_event=True,
            legacy_dump_end_event=False,
            boundary_dump_done=True,
            dump_done_mass_low=False,
            next_dump_done_hold_count=0,
            ready_to_return=True,
            coverage_completion_reason="dump_complete_boundary",
            dump_to_return_reason="dump_to_return_dump_complete_boundary",
        ),
        complete_coverage_dump=lambda obs, reason: None,
        set_return_or_direct_handoff=lambda obs, reason: None,
        set_dump_done_hold_count=lambda value: None,
    )

    assert branch.maybe_handle(obs={}, boundary_event=None) is False


def test_legacy_fsm_return_branch_latches_next_dig_event_without_switch() -> None:
    obs: dict[str, Any] = {"qpos": [1.0]}
    events: list[str] = []
    status = ReturnTransitionStatus(
        mass_in_bucket_kg=0.0,
        min_distance_to_dig_area_m=0.0,
        bucket_depth_below_dig_area_plane_m=0.0,
        semantic_boundary_profile_active=True,
        next_dig_event=True,
        next_or_seen_dig_event=True,
        entry_close=False,
        start_envelope_ready=False,
        handoff_ready=False,
        direct_handoff_ready=False,
        shallow_guard_ready=False,
        shallow_guard_allowed=False,
        completed_transition=False,
        next_skill="",
        switch_reason="",
    )
    branch = LegacyFSMReturnBranch(
        config=LegacyFSMReturnConfig(return_skill_name="return"),
        current_skill_name=lambda: "return",
        return_transition_status=lambda obs, boundary_event: status,
        mark_return_next_dig_event_seen=lambda: events.append("seen"),
        complete_return_transition=lambda: events.append("complete"),
        next_skill_after_return_transition=lambda: "dig",
        set_skill=lambda skill, reason: events.append(f"{skill}:{reason}"),
    )

    handled = branch.maybe_handle(obs=obs, boundary_event=object())

    assert handled is True
    assert events == ["seen"]


def test_legacy_fsm_return_branch_completes_next_dig_handoff_in_order() -> None:
    obs: dict[str, Any] = {"qpos": [1.0]}
    events: list[str] = []
    status = ReturnTransitionStatus(
        mass_in_bucket_kg=0.0,
        min_distance_to_dig_area_m=0.0,
        bucket_depth_below_dig_area_plane_m=0.0,
        semantic_boundary_profile_active=True,
        next_dig_event=True,
        next_or_seen_dig_event=True,
        entry_close=True,
        start_envelope_ready=True,
        handoff_ready=True,
        direct_handoff_ready=True,
        shallow_guard_ready=False,
        shallow_guard_allowed=False,
        completed_transition=True,
        next_skill="dig",
        switch_reason="return_to_dig_next_dig_entry_ready",
    )
    branch = LegacyFSMReturnBranch(
        config=LegacyFSMReturnConfig(return_skill_name="return"),
        current_skill_name=lambda: "return",
        return_transition_status=lambda obs, boundary_event: status,
        mark_return_next_dig_event_seen=lambda: events.append("seen"),
        complete_return_transition=lambda: events.append("complete"),
        next_skill_after_return_transition=lambda: "dig",
        set_skill=lambda skill, reason: events.append(f"{skill}:{reason}"),
    )

    handled = branch.maybe_handle(obs=obs, boundary_event=object())

    assert handled is True
    assert events == [
        "seen",
        "complete",
        "dig:return_to_dig_next_dig_entry_ready",
    ]


def test_legacy_fsm_return_branch_selects_next_skill_after_completion() -> None:
    obs: dict[str, Any] = {"qpos": [1.0]}
    state = {"cycle": 0}
    events: list[str] = []
    status = ReturnTransitionStatus(
        mass_in_bucket_kg=0.0,
        min_distance_to_dig_area_m=0.0,
        bucket_depth_below_dig_area_plane_m=0.0,
        semantic_boundary_profile_active=True,
        next_dig_event=True,
        next_or_seen_dig_event=True,
        entry_close=True,
        start_envelope_ready=True,
        handoff_ready=True,
        direct_handoff_ready=False,
        shallow_guard_ready=False,
        shallow_guard_allowed=False,
        completed_transition=True,
        next_skill="pre_dig_align",
        switch_reason="return_to_pre_dig_align_next_dig_entry_ready",
    )
    branch = LegacyFSMReturnBranch(
        config=LegacyFSMReturnConfig(return_skill_name="return"),
        current_skill_name=lambda: "return",
        return_transition_status=lambda obs, boundary_event: status,
        mark_return_next_dig_event_seen=lambda: events.append("seen"),
        complete_return_transition=lambda: state.__setitem__(
            "cycle",
            state["cycle"] + 1,
        ),
        next_skill_after_return_transition=lambda: (
            "pre_dig_align" if state["cycle"] == 0 else "dig"
        ),
        set_skill=lambda skill, reason: events.append(f"{skill}:{reason}"),
    )

    handled = branch.maybe_handle(obs=obs, boundary_event=object())

    assert handled is True
    assert state == {"cycle": 1}
    assert events == ["seen", "dig:return_to_dig_next_dig_entry_ready"]


def test_legacy_fsm_return_branch_ignores_non_return_skill() -> None:
    branch = LegacyFSMReturnBranch(
        config=LegacyFSMReturnConfig(return_skill_name="return"),
        current_skill_name=lambda: "dig",
        return_transition_status=lambda obs, boundary_event: ReturnTransitionStatus(
            mass_in_bucket_kg=0.0,
            min_distance_to_dig_area_m=0.0,
            bucket_depth_below_dig_area_plane_m=0.0,
            semantic_boundary_profile_active=False,
            next_dig_event=True,
            next_or_seen_dig_event=True,
            entry_close=True,
            start_envelope_ready=True,
            handoff_ready=True,
            direct_handoff_ready=False,
            shallow_guard_ready=False,
            shallow_guard_allowed=False,
            completed_transition=True,
            next_skill="dig",
            switch_reason="return_to_dig_next_dig_entry_ready",
        ),
        mark_return_next_dig_event_seen=lambda: None,
        complete_return_transition=lambda: None,
        next_skill_after_return_transition=lambda: "dig",
        set_skill=lambda skill, reason: None,
    )

    assert branch.maybe_handle(obs={}, boundary_event=None) is False
