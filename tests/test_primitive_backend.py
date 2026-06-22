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
    LegacyFSMResidualPreDigAlignAdapter,
    LegacyFSMReturnBranch,
    LegacyFSMReturnConfig,
    PrimitiveRequestedBranchRunner,
    RESIDUAL_PRE_DIG_ALIGN_DECISION_SOURCE,
)
from testbed.planner.primitive_capabilities import (
    CarryTransitionStatus,
    DumpTransitionStatus,
    ReturnTransitionStatus,
)
from testbed.planner.primitive_decision import (
    LEGACY_FSM_DECISION_SOURCE,
    CompleteCellEntryDigCompatibilityEffect,
    CompleteCoverageDigEffect,
    CompleteReturnTransitionEffect,
    CompleteCoverageDumpEffect,
    IncrementDigBadReplanCountEffect,
    IncrementDigExitGuardReplanCountEffect,
    MarkReturnNextDigEventSeenEffect,
    RejectActiveCoverageCorridorEffect,
    RestartAfterFailedDigEffect,
    SetDumpDoneHoldCountEffect,
    SetDumpReadyHoldCountEffect,
    SetDumpStartDepositedMassFromObservationEffect,
    SetReturnOrDirectHandoffEffect,
    PrimitiveDecisionContractError,
    PrimitiveDecisionResult,
    SwitchToNextSkillAfterReturnEffect,
    SwitchSkillEffect,
)
from testbed.planner.primitive_execution import PrimitiveTickPreparation


class _RecordingBranch:
    def __init__(
        self,
        name: str,
        result: PrimitiveDecisionResult | None = None,
        calls: list[str] | None = None,
    ) -> None:
        self.name = name
        self.result = result
        self.calls = calls if calls is not None else []

    def decide_tick(self, *, obs, boundary_event, preparation):
        self.calls.append(self.name)
        return self.result


def _requested_no_change_result(
    *,
    decision_source: str = "test_branch",
    skill: str = "dig",
) -> PrimitiveDecisionResult:
    return PrimitiveDecisionResult.from_requested_effects(
        decision_source=decision_source,
        status="no_change",
        skill_before=skill,
        skill_after=skill,
        switch_reason="",
        effects=(),
    )


def test_requested_branch_runner_returns_first_non_none_result_and_stops() -> None:
    calls: list[str] = []
    expected = _requested_no_change_result(decision_source="dig_branch")
    runner = PrimitiveRequestedBranchRunner(
        bootstrap_branch=_RecordingBranch("bootstrap", None, calls),
        dig_branch=_RecordingBranch("dig", expected, calls),
        carry_branch=_RecordingBranch("carry", _requested_no_change_result(), calls),
        dump_branch=_RecordingBranch("dump", _requested_no_change_result(), calls),
        return_branch=_RecordingBranch("return", _requested_no_change_result(), calls),
        residual_branch=_RecordingBranch("residual", _requested_no_change_result(), calls),
    )

    result = runner.decide_tick(
        obs={"qpos": [1.0]},
        boundary_event=object(),
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="dig",
            dig_progress_updated=True,
        ),
    )

    assert result is expected
    assert calls == ["bootstrap", "dig"]


def test_requested_branch_runner_calls_branches_in_stable_order_before_residual() -> None:
    calls: list[str] = []
    residual = _requested_no_change_result(
        decision_source=RESIDUAL_PRE_DIG_ALIGN_DECISION_SOURCE,
        skill="pre_dig_align",
    )
    runner = PrimitiveRequestedBranchRunner(
        bootstrap_branch=_RecordingBranch("bootstrap", None, calls),
        dig_branch=_RecordingBranch("dig", None, calls),
        carry_branch=_RecordingBranch("carry", None, calls),
        dump_branch=_RecordingBranch("dump", None, calls),
        return_branch=_RecordingBranch("return", None, calls),
        residual_branch=_RecordingBranch("residual", residual, calls),
    )

    result = runner.decide_tick(
        obs={},
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="pre_dig_align",
            dig_progress_updated=False,
        ),
    )

    assert result is residual
    assert calls == ["bootstrap", "dig", "carry", "dump", "return", "residual"]


def test_requested_branch_runner_fails_fast_when_all_branches_decline() -> None:
    calls: list[str] = []
    runner = PrimitiveRequestedBranchRunner(
        bootstrap_branch=_RecordingBranch("bootstrap", None, calls),
        dig_branch=_RecordingBranch("dig", None, calls),
        carry_branch=_RecordingBranch("carry", None, calls),
        dump_branch=_RecordingBranch("dump", None, calls),
        return_branch=_RecordingBranch("return", None, calls),
        residual_branch=_RecordingBranch("residual", None, calls),
    )

    try:
        runner.decide_tick(
            obs={},
            boundary_event=None,
            preparation=PrimitiveTickPreparation(
                boundary_event=None,
                skill_name_before_decision="legacy_skill",
                dig_progress_updated=False,
            ),
        )
    except PrimitiveDecisionContractError as exc:
        message = str(exc)
    else:
        raise AssertionError("runner accepted an unhandled planner skill")

    assert calls == ["bootstrap", "dig", "carry", "dump", "return", "residual"]
    assert "unhandled planner skill" in message
    assert "broad legacy fallback is retired" in message
    assert "legacy_skill" in message


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


def test_residual_pre_dig_align_adapter_is_explicit_already_applied_path() -> None:
    obs: dict[str, Any] = {"qpos": [1.0]}
    boundary_event = object()
    state = {"skill": "pre_dig_align", "reason": ""}
    calls: list[dict[str, Any]] = []

    def maybe_handle_pre_dig_align_skill(got_obs: dict[str, Any]) -> bool:
        calls.append(got_obs)
        state["skill"] = "dig"
        state["reason"] = "pre_dig_align_to_dig_ready"
        return True

    adapter = LegacyFSMResidualPreDigAlignAdapter(
        pre_dig_align_skill_name="pre_dig_align",
        current_skill_name=lambda: state["skill"],
        current_switch_reason=lambda: state["reason"],
        maybe_handle_pre_dig_align_skill=maybe_handle_pre_dig_align_skill,
    )

    result = adapter.decide_tick(
        obs=obs,
        boundary_event=boundary_event,
        preparation=PrimitiveTickPreparation(
            boundary_event=boundary_event,
            skill_name_before_decision="pre_dig_align",
            dig_progress_updated=False,
        ),
    )

    assert calls == [obs]
    assert result is not None
    assert result.decision_source == RESIDUAL_PRE_DIG_ALIGN_DECISION_SOURCE
    assert result.side_effects_applied is True
    assert result.skill_before == "pre_dig_align"
    assert result.skill_after == "dig"
    assert result.switch_reason == "pre_dig_align_to_dig_ready"


def test_residual_pre_dig_align_adapter_ignores_non_residual_skill() -> None:
    adapter = LegacyFSMResidualPreDigAlignAdapter(
        pre_dig_align_skill_name="pre_dig_align",
        current_skill_name=lambda: "dig",
        current_switch_reason=lambda: "",
        maybe_handle_pre_dig_align_skill=lambda obs: True,
    )

    result = adapter.decide_tick(
        obs={},
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="dig",
            dig_progress_updated=True,
        ),
    )

    assert result is None


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


def test_legacy_fsm_bootstrap_branch_returns_requested_switch_effect() -> None:
    obs: dict[str, Any] = {"qpos": [1.0]}
    boundary_event = object()
    switches: list[tuple[str, str]] = []
    branch = LegacyFSMBootstrapBranch(
        config=LegacyFSMBootstrapConfig(
            bootstrap_skill_name="bootstrap",
            pre_dig_align_skill_name="pre_dig_align",
        ),
        current_skill_name=lambda: "bootstrap",
        should_end_bootstrap=lambda *, obs, boundary_event: True,
        bootstrap_end_mode=lambda: "first_qualified_dig_start",
        should_pre_dig_align_before_dig=lambda: True,
        set_skill=lambda skill, reason: switches.append((skill, reason)),
    )

    result = branch.decide_tick(
        obs=obs,
        boundary_event=boundary_event,
        preparation=PrimitiveTickPreparation(
            boundary_event=boundary_event,
            skill_name_before_decision="bootstrap",
            dig_progress_updated=False,
        ),
    )

    assert switches == []
    assert result is not None
    assert result.side_effects_applied is False
    assert result.skill_before == "bootstrap"
    assert result.skill_after == "pre_dig_align"
    assert result.switch_reason == "bootstrap_to_pre_dig_align"
    assert result.effects == (
        SwitchSkillEffect(
            target_skill_name="pre_dig_align",
            switch_reason="bootstrap_to_pre_dig_align",
        ),
    )


def test_legacy_fsm_bootstrap_branch_requested_decision_ignores_non_bootstrap() -> None:
    branch = LegacyFSMBootstrapBranch(
        config=LegacyFSMBootstrapConfig(
            bootstrap_skill_name="bootstrap",
            pre_dig_align_skill_name="pre_dig_align",
        ),
        current_skill_name=lambda: "dig",
        should_end_bootstrap=lambda *, obs, boundary_event: True,
        bootstrap_end_mode=lambda: "first_qualified_dig_start",
        should_pre_dig_align_before_dig=lambda: True,
        set_skill=lambda skill, reason: None,
    )

    result = branch.decide_tick(
        obs={},
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="dig",
            dig_progress_updated=True,
        ),
    )

    assert result is None


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


def test_legacy_fsm_dig_branch_requested_exit_guard_effects_in_order() -> None:
    callbacks: list[str] = []
    branch = LegacyFSMDigBranch(
        config=LegacyFSMDigConfig(dig_skill_name="dig"),
        current_skill_name=lambda: "dig",
        dig_exit_guard_ready=lambda obs: True,
        increment_dig_exit_guard_replan_count=lambda: callbacks.append("exit_count"),
        reject_active_coverage_corridor=lambda obs, reason: callbacks.append(
            f"reject:{reason}"
        ),
        restart_after_failed_dig=lambda reason, obs: callbacks.append(
            f"restart:{reason}"
        ),
        dig_bad_replan_ready=lambda obs: True,
        increment_dig_bad_replan_count=lambda: callbacks.append("bad_count"),
        dig_complete_boundary_low_payload=lambda obs, boundary_event: True,
        dig_to_carry_ready=lambda *, obs, boundary_event: True,
        complete_cell_entry_dig=lambda obs: callbacks.append("cell"),
        complete_coverage_dig=lambda obs: callbacks.append("coverage"),
        dig_to_carry_reason=lambda: "boundary_confirmed",
        set_skill=lambda skill, reason: callbacks.append(f"{skill}:{reason}"),
    )

    result = branch.decide_tick(
        obs={"qpos": [1.0]},
        boundary_event=object(),
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="dig",
            dig_progress_updated=True,
        ),
    )

    assert callbacks == []
    assert result is not None
    assert result.side_effects_applied is False
    assert result.effects == (
        IncrementDigExitGuardReplanCountEffect(),
        RejectActiveCoverageCorridorEffect(reason="exit_overshoot_low_payload"),
        RestartAfterFailedDigEffect(reason="exit_overshoot_low_payload"),
    )


def test_legacy_fsm_dig_branch_requested_bad_dig_effects_in_order() -> None:
    branch = LegacyFSMDigBranch(
        config=LegacyFSMDigConfig(dig_skill_name="dig"),
        current_skill_name=lambda: "dig",
        dig_exit_guard_ready=lambda obs: False,
        increment_dig_exit_guard_replan_count=lambda: None,
        reject_active_coverage_corridor=lambda obs, reason: None,
        restart_after_failed_dig=lambda reason, obs: None,
        dig_bad_replan_ready=lambda obs: True,
        increment_dig_bad_replan_count=lambda: None,
        dig_complete_boundary_low_payload=lambda obs, boundary_event: True,
        dig_to_carry_ready=lambda *, obs, boundary_event: True,
        complete_cell_entry_dig=lambda obs: None,
        complete_coverage_dig=lambda obs: None,
        dig_to_carry_reason=lambda: "boundary_confirmed",
        set_skill=lambda skill, reason: None,
    )

    result = branch.decide_tick(
        obs={},
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="dig",
            dig_progress_updated=True,
        ),
    )

    assert result is not None
    assert result.effects == (
        IncrementDigBadReplanCountEffect(),
        RejectActiveCoverageCorridorEffect(reason="bad_dig_low_payload"),
        RestartAfterFailedDigEffect(reason="bad_dig_low_payload"),
    )


def test_legacy_fsm_dig_branch_requested_complete_low_payload_effects_in_order() -> None:
    branch = LegacyFSMDigBranch(
        config=LegacyFSMDigConfig(dig_skill_name="dig"),
        current_skill_name=lambda: "dig",
        dig_exit_guard_ready=lambda obs: False,
        increment_dig_exit_guard_replan_count=lambda: None,
        reject_active_coverage_corridor=lambda obs, reason: None,
        restart_after_failed_dig=lambda reason, obs: None,
        dig_bad_replan_ready=lambda obs: False,
        increment_dig_bad_replan_count=lambda: None,
        dig_complete_boundary_low_payload=lambda obs, boundary_event: True,
        dig_to_carry_ready=lambda *, obs, boundary_event: True,
        complete_cell_entry_dig=lambda obs: None,
        complete_coverage_dig=lambda obs: None,
        dig_to_carry_reason=lambda: "boundary_confirmed",
        set_skill=lambda skill, reason: None,
    )

    result = branch.decide_tick(
        obs={},
        boundary_event=object(),
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="dig",
            dig_progress_updated=True,
        ),
    )

    assert result is not None
    assert result.effects == (
        IncrementDigBadReplanCountEffect(),
        RejectActiveCoverageCorridorEffect(
            reason="dig_complete_low_current_payload"
        ),
        RestartAfterFailedDigEffect(reason="complete_low_payload"),
    )


def test_legacy_fsm_dig_branch_requested_dig_to_carry_effects_in_order() -> None:
    callbacks: list[str] = []
    branch = LegacyFSMDigBranch(
        config=LegacyFSMDigConfig(dig_skill_name="dig"),
        current_skill_name=lambda: "dig",
        dig_exit_guard_ready=lambda obs: False,
        increment_dig_exit_guard_replan_count=lambda: callbacks.append("exit_count"),
        reject_active_coverage_corridor=lambda obs, reason: callbacks.append(
            f"reject:{reason}"
        ),
        restart_after_failed_dig=lambda reason, obs: callbacks.append(
            f"restart:{reason}"
        ),
        dig_bad_replan_ready=lambda obs: False,
        increment_dig_bad_replan_count=lambda: callbacks.append("bad_count"),
        dig_complete_boundary_low_payload=lambda obs, boundary_event: False,
        dig_to_carry_ready=lambda *, obs, boundary_event: True,
        complete_cell_entry_dig=lambda obs: callbacks.append("cell"),
        complete_coverage_dig=lambda obs: callbacks.append("coverage"),
        dig_to_carry_reason=lambda: "boundary_confirmed",
        set_skill=lambda skill, reason: callbacks.append(f"{skill}:{reason}"),
    )

    result = branch.decide_tick(
        obs={"qpos": [1.0]},
        boundary_event=object(),
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="dig",
            dig_progress_updated=True,
        ),
    )

    assert callbacks == []
    assert result is not None
    assert result.status == "skill_switch"
    assert result.skill_after == "carry"
    assert result.switch_reason == "dig_to_carry_boundary_confirmed"
    assert result.effects == (
        CompleteCellEntryDigCompatibilityEffect(),
        CompleteCoverageDigEffect(),
        SwitchSkillEffect(
            target_skill_name="carry",
            switch_reason="dig_to_carry_boundary_confirmed",
        ),
    )


def test_legacy_fsm_dig_branch_requested_no_change_for_unready_dig() -> None:
    branch = LegacyFSMDigBranch(
        config=LegacyFSMDigConfig(dig_skill_name="dig"),
        current_skill_name=lambda: "dig",
        dig_exit_guard_ready=lambda obs: False,
        increment_dig_exit_guard_replan_count=lambda: None,
        reject_active_coverage_corridor=lambda obs, reason: None,
        restart_after_failed_dig=lambda reason, obs: None,
        dig_bad_replan_ready=lambda obs: False,
        increment_dig_bad_replan_count=lambda: None,
        dig_complete_boundary_low_payload=lambda obs, boundary_event: False,
        dig_to_carry_ready=lambda *, obs, boundary_event: False,
        complete_cell_entry_dig=lambda obs: None,
        complete_coverage_dig=lambda obs: None,
        dig_to_carry_reason=lambda: "",
        set_skill=lambda skill, reason: None,
    )

    result = branch.decide_tick(
        obs={},
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="dig",
            dig_progress_updated=True,
        ),
    )

    assert result is not None
    assert result.status == "no_change"
    assert result.side_effects_applied is False
    assert result.effects == ()


def test_legacy_fsm_dig_branch_requested_ignores_non_dig_skill() -> None:
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

    result = branch.decide_tick(
        obs={},
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="carry",
            dig_progress_updated=False,
        ),
    )

    assert result is None


def test_legacy_fsm_dig_branch_compat_facade_reuses_requested_effects() -> None:
    obs: dict[str, Any] = {"qpos": [1.0]}
    events: list[str] = []
    branch = LegacyFSMDigBranch(
        config=LegacyFSMDigConfig(dig_skill_name="dig"),
        current_skill_name=lambda: "dig",
        dig_exit_guard_ready=lambda obs: True,
        increment_dig_exit_guard_replan_count=lambda: events.append("exit_count"),
        reject_active_coverage_corridor=lambda obs, reason: events.append(
            f"reject:{reason}"
        ),
        restart_after_failed_dig=lambda reason, obs: events.append(
            f"restart:{reason}"
        ),
        dig_bad_replan_ready=lambda obs: True,
        increment_dig_bad_replan_count=lambda: events.append("bad_count"),
        dig_complete_boundary_low_payload=lambda obs, boundary_event: True,
        dig_to_carry_ready=lambda *, obs, boundary_event: True,
        complete_cell_entry_dig=lambda obs: events.append("cell"),
        complete_coverage_dig=lambda obs: events.append("coverage"),
        dig_to_carry_reason=lambda: "boundary_confirmed",
        set_skill=lambda skill, reason: events.append(f"{skill}:{reason}"),
    )

    handled = branch.maybe_handle(obs=obs, boundary_event=None)

    assert handled is True
    assert events == [
        "exit_count",
        "reject:exit_overshoot_low_payload",
        "restart:exit_overshoot_low_payload",
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


def test_legacy_fsm_carry_branch_requested_release_safety_handoff_effects() -> None:
    callbacks: list[str] = []
    branch = LegacyFSMCarryBranch(
        config=LegacyFSMCarryConfig(carry_skill_name="carry"),
        current_skill_name=lambda: "carry",
        carry_transition_status=lambda obs, boundary_event: CarryTransitionStatus(
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
        ),
        complete_coverage_dump=lambda obs, reason: callbacks.append(
            f"complete:{reason}"
        ),
        set_return_or_direct_handoff=lambda obs, reason: callbacks.append(
            f"return:{reason}"
        ),
        set_dump_ready_hold_count=lambda value: callbacks.append(f"hold:{value}"),
        deposited_mass=lambda obs: 20.0,
        set_dump_start_deposited_mass=lambda value: callbacks.append(
            f"deposit:{value}"
        ),
        set_skill=lambda skill, reason: callbacks.append(f"{skill}:{reason}"),
    )

    result = branch.decide_tick(
        obs={"qpos": [1.0]},
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="carry",
            dig_progress_updated=False,
        ),
    )

    assert callbacks == []
    assert result is not None
    assert result.side_effects_applied is False
    assert result.status == "skill_switch"
    assert result.effects == (
        CompleteCoverageDumpEffect(reason="carry_release_safety"),
        SetReturnOrDirectHandoffEffect(reason="carry_to_return_release_safety"),
    )


def test_legacy_fsm_carry_branch_requested_dump_complete_boundary_effects() -> None:
    branch = LegacyFSMCarryBranch(
        config=LegacyFSMCarryConfig(carry_skill_name="carry"),
        current_skill_name=lambda: "carry",
        carry_transition_status=lambda obs, boundary_event: CarryTransitionStatus(
            mass_in_bucket_kg=0.0,
            deposited_mass_in_target_box_kg=20.0,
            deposit_delta_since_cycle_start_kg=10.0,
            semantic_boundary_profile_active=True,
            dump_committed_event=False,
            release_onset_event=False,
            dump_complete_event=True,
            legacy_dump_start_event=False,
            carry_release_safety_done=False,
            dump_ready=False,
            next_dump_ready_hold_count=0,
            ready_to_dump=False,
            carry_to_dump_reason="",
            carry_to_return_reason="carry_to_return_dump_complete_boundary",
        ),
        complete_coverage_dump=lambda obs, reason: None,
        set_return_or_direct_handoff=lambda obs, reason: None,
        set_dump_ready_hold_count=lambda value: None,
        deposited_mass=lambda obs: 20.0,
        set_dump_start_deposited_mass=lambda value: None,
        set_skill=lambda skill, reason: None,
    )

    result = branch.decide_tick(
        obs={},
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="carry",
            dig_progress_updated=False,
        ),
    )

    assert result is not None
    assert result.effects == (
        CompleteCoverageDumpEffect(reason="carry_dump_complete_boundary"),
        SetReturnOrDirectHandoffEffect(
            reason="carry_to_return_dump_complete_boundary"
        ),
    )


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


def test_legacy_fsm_carry_branch_requested_ready_to_dump_effects_in_order() -> None:
    callbacks: list[str] = []
    branch = LegacyFSMCarryBranch(
        config=LegacyFSMCarryConfig(carry_skill_name="carry"),
        current_skill_name=lambda: "carry",
        carry_transition_status=lambda obs, boundary_event: CarryTransitionStatus(
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
        ),
        complete_coverage_dump=lambda obs, reason: callbacks.append(
            f"complete:{reason}"
        ),
        set_return_or_direct_handoff=lambda obs, reason: callbacks.append(
            f"return:{reason}"
        ),
        set_dump_ready_hold_count=lambda value: callbacks.append(f"hold:{value}"),
        deposited_mass=lambda obs: 8.5,
        set_dump_start_deposited_mass=lambda value: callbacks.append(
            f"deposit:{value}"
        ),
        set_skill=lambda skill, reason: callbacks.append(f"{skill}:{reason}"),
    )

    result = branch.decide_tick(
        obs={"qpos": [1.0]},
        boundary_event=object(),
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="carry",
            dig_progress_updated=False,
        ),
    )

    assert callbacks == []
    assert result is not None
    assert result.effects == (
        SetDumpReadyHoldCountEffect(value=3),
        SetDumpStartDepositedMassFromObservationEffect(),
        SwitchSkillEffect(
            target_skill_name="dump",
            switch_reason="carry_to_dump_dump_committed_boundary",
        ),
    )


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


def test_legacy_fsm_dump_branch_requested_boundary_done_effects() -> None:
    callbacks: list[str] = []
    branch = LegacyFSMDumpBranch(
        config=LegacyFSMDumpConfig(dump_skill_name="dump"),
        current_skill_name=lambda: "dump",
        dump_transition_status=lambda obs, boundary_event: DumpTransitionStatus(
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
        ),
        complete_coverage_dump=lambda obs, reason: callbacks.append(
            f"complete:{reason}"
        ),
        set_return_or_direct_handoff=lambda obs, reason: callbacks.append(
            f"return:{reason}"
        ),
        set_dump_done_hold_count=lambda value: callbacks.append(f"hold:{value}"),
    )

    result = branch.decide_tick(
        obs={"qpos": [1.0]},
        boundary_event=object(),
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="dump",
            dig_progress_updated=False,
        ),
    )

    assert callbacks == []
    assert result is not None
    assert result.effects == (
        CompleteCoverageDumpEffect(reason="dump_complete_boundary"),
        SetReturnOrDirectHandoffEffect(reason="dump_to_return_dump_complete_boundary"),
    )


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


def test_legacy_fsm_dump_branch_requested_ready_to_return_effects_in_order() -> None:
    callbacks: list[str] = []
    branch = LegacyFSMDumpBranch(
        config=LegacyFSMDumpConfig(dump_skill_name="dump"),
        current_skill_name=lambda: "dump",
        dump_transition_status=lambda obs, boundary_event: DumpTransitionStatus(
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
        ),
        complete_coverage_dump=lambda obs, reason: callbacks.append(
            f"complete:{reason}"
        ),
        set_return_or_direct_handoff=lambda obs, reason: callbacks.append(
            f"return:{reason}"
        ),
        set_dump_done_hold_count=lambda value: callbacks.append(f"hold:{value}"),
    )

    result = branch.decide_tick(
        obs={"qpos": [1.0]},
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="dump",
            dig_progress_updated=False,
        ),
    )

    assert callbacks == []
    assert result is not None
    assert result.effects == (
        SetDumpDoneHoldCountEffect(value=2),
        CompleteCoverageDumpEffect(reason="dump_mass_low"),
        SetReturnOrDirectHandoffEffect(reason="dump_to_return_mass_low"),
    )


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


def _return_status(
    *,
    next_dig_event: bool = False,
    next_or_seen_dig_event: bool = False,
    entry_close: bool = False,
    start_envelope_ready: bool = False,
    handoff_ready: bool = False,
    direct_handoff_ready: bool = False,
    shallow_guard_ready: bool = False,
    shallow_guard_allowed: bool = False,
    completed_transition: bool = False,
    next_skill: str = "",
    switch_reason: str = "",
) -> ReturnTransitionStatus:
    return ReturnTransitionStatus(
        mass_in_bucket_kg=0.0,
        min_distance_to_dig_area_m=0.0,
        bucket_depth_below_dig_area_plane_m=0.0,
        semantic_boundary_profile_active=True,
        next_dig_event=next_dig_event,
        next_or_seen_dig_event=next_or_seen_dig_event,
        entry_close=entry_close,
        start_envelope_ready=start_envelope_ready,
        handoff_ready=handoff_ready,
        direct_handoff_ready=direct_handoff_ready,
        shallow_guard_ready=shallow_guard_ready,
        shallow_guard_allowed=shallow_guard_allowed,
        completed_transition=completed_transition,
        next_skill=next_skill,
        switch_reason=switch_reason,
    )


def test_legacy_fsm_return_branch_requested_next_dig_event_marks_only() -> None:
    obs: dict[str, Any] = {"qpos": [1.0]}
    callbacks: list[str] = []
    branch = LegacyFSMReturnBranch(
        config=LegacyFSMReturnConfig(return_skill_name="return"),
        current_skill_name=lambda: "return",
        return_transition_status=lambda obs, boundary_event: _return_status(
            next_dig_event=True,
            next_or_seen_dig_event=True,
        ),
        mark_return_next_dig_event_seen=lambda: callbacks.append("seen"),
        complete_return_transition=lambda: callbacks.append("complete"),
        next_skill_after_return_transition=lambda: "dig",
        set_skill=lambda skill, reason: callbacks.append(f"{skill}:{reason}"),
    )

    result = branch.decide_tick(
        obs=obs,
        boundary_event=object(),
        preparation=PrimitiveTickPreparation(
            boundary_event=object(),
            skill_name_before_decision="return",
            dig_progress_updated=False,
        ),
    )

    assert callbacks == []
    assert result is not None
    assert result.side_effects_applied is False
    assert result.status == "no_change"
    assert result.effects == (MarkReturnNextDigEventSeenEffect(),)


def test_legacy_fsm_return_branch_requested_completion_orders_effects() -> None:
    callbacks: list[str] = []
    branch = LegacyFSMReturnBranch(
        config=LegacyFSMReturnConfig(return_skill_name="return"),
        current_skill_name=lambda: "return",
        return_transition_status=lambda obs, boundary_event: _return_status(
            next_or_seen_dig_event=True,
            entry_close=True,
            start_envelope_ready=True,
            handoff_ready=True,
            completed_transition=True,
        ),
        mark_return_next_dig_event_seen=lambda: callbacks.append("seen"),
        complete_return_transition=lambda: callbacks.append("complete"),
        next_skill_after_return_transition=lambda: "dig",
        set_skill=lambda skill, reason: callbacks.append(f"{skill}:{reason}"),
    )

    result = branch.decide_tick(
        obs={},
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="return",
            dig_progress_updated=False,
        ),
    )

    assert callbacks == []
    assert result is not None
    assert result.side_effects_applied is False
    assert result.status == "skill_switch"
    assert result.effects == (
        CompleteReturnTransitionEffect(),
        SwitchToNextSkillAfterReturnEffect(reason_suffix="next_dig_entry_ready"),
    )


def test_legacy_fsm_return_branch_requested_event_then_completion_order() -> None:
    branch = LegacyFSMReturnBranch(
        config=LegacyFSMReturnConfig(return_skill_name="return"),
        current_skill_name=lambda: "return",
        return_transition_status=lambda obs, boundary_event: _return_status(
            next_dig_event=True,
            next_or_seen_dig_event=True,
            entry_close=True,
            start_envelope_ready=True,
            handoff_ready=True,
            completed_transition=True,
        ),
        mark_return_next_dig_event_seen=lambda: None,
        complete_return_transition=lambda: None,
        next_skill_after_return_transition=lambda: "dig",
        set_skill=lambda skill, reason: None,
    )

    result = branch.decide_tick(
        obs={},
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="return",
            dig_progress_updated=False,
        ),
    )

    assert result is not None
    assert result.effects == (
        MarkReturnNextDigEventSeenEffect(),
        CompleteReturnTransitionEffect(),
        SwitchToNextSkillAfterReturnEffect(reason_suffix="next_dig_entry_ready"),
    )


def test_legacy_fsm_return_branch_requested_no_effects_for_unready_return() -> None:
    branch = LegacyFSMReturnBranch(
        config=LegacyFSMReturnConfig(return_skill_name="return"),
        current_skill_name=lambda: "return",
        return_transition_status=lambda obs, boundary_event: _return_status(),
        mark_return_next_dig_event_seen=lambda: None,
        complete_return_transition=lambda: None,
        next_skill_after_return_transition=lambda: "dig",
        set_skill=lambda skill, reason: None,
    )

    result = branch.decide_tick(
        obs={},
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="return",
            dig_progress_updated=False,
        ),
    )

    assert result is not None
    assert result.status == "no_change"
    assert result.effects == ()


def test_legacy_fsm_return_branch_requested_ignores_non_return_skill() -> None:
    branch = LegacyFSMReturnBranch(
        config=LegacyFSMReturnConfig(return_skill_name="return"),
        current_skill_name=lambda: "dig",
        return_transition_status=lambda obs, boundary_event: _return_status(
            next_dig_event=True,
            completed_transition=True,
        ),
        mark_return_next_dig_event_seen=lambda: None,
        complete_return_transition=lambda: None,
        next_skill_after_return_transition=lambda: "dig",
        set_skill=lambda skill, reason: None,
    )

    result = branch.decide_tick(
        obs={},
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="dig",
            dig_progress_updated=True,
        ),
    )

    assert result is None


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
