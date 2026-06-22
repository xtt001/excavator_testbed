from __future__ import annotations

from collections.abc import Callable
from dataclasses import fields
from typing import Any

from testbed.planner.primitive_backend import (
    LegacyFSMBackendAdapter,
    LegacyFSMBranchPorts,
    LegacyFSMBranchSet,
    LegacyFSMBootstrapBranch,
    LegacyFSMBootstrapConfig,
    LegacyFSMCarryBranch,
    LegacyFSMCarryConfig,
    LegacyFSMCompatibilityDecisionBackend,
    LegacyFSMDumpBranch,
    LegacyFSMDumpConfig,
    LegacyFSMDigBranch,
    LegacyFSMDigConfig,
    LegacyFSMResidualPreDigAlignAdapter,
    LegacyFSMRequestedDecisionBackend,
    LegacyFSMReturnBranch,
    LegacyFSMReturnConfig,
    PrimitiveRequestedBranchRunner,
    RESIDUAL_PRE_DIG_ALIGN_DECISION_SOURCE,
)
from testbed.planner.primitive_capabilities import (
    CarryTransitionStatus,
    DigTransitionStatus,
    DumpTransitionStatus,
    ReturnTransitionStatus,
)
from testbed.planner.primitive_backend_facts import (
    BootstrapDecisionStatus,
    PrimitiveBackendFactsAccess,
    PrimitiveBootstrapDecisionFacts,
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
from testbed.planner.primitive_decision_capabilities import (
    PrimitiveDecisionCapabilities,
    PrimitiveDecisionCapabilitiesPorts,
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


class _RecordingBranch:
    def __init__(
        self,
        name: str,
        result: PrimitiveDecisionResult | None = None,
        calls: list[str] | None = None,
        contexts: list[PrimitiveDecisionContext] | None = None,
    ) -> None:
        self.name = name
        self.result = result
        self.calls = calls if calls is not None else []
        self.contexts = contexts if contexts is not None else []

    def decide_context(self, context: PrimitiveDecisionContext):
        self.contexts.append(context)
        self.calls.append(self.name)
        return self.result

    def decide_tick(self, *, obs, boundary_event, preparation):
        return self.decide_context(
            PrimitiveDecisionContext.from_tick(
                obs=obs,
                boundary_event=boundary_event,
                preparation=preparation,
            )
        )


class _RecordingCompatBranch(_RecordingBranch):
    def __init__(
        self,
        name: str,
        handled: bool,
        calls: list[str],
    ) -> None:
        super().__init__(name=name, result=None, calls=calls)
        self.handled = handled

    def maybe_handle(self, *, obs, boundary_event):
        self.calls.append(self.name)
        return self.handled


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


def _default_carry_status() -> CarryTransitionStatus:
    return CarryTransitionStatus(
        mass_in_bucket_kg=0.0,
        deposited_mass_in_target_box_kg=0.0,
        deposit_delta_since_cycle_start_kg=0.0,
        semantic_boundary_profile_active=False,
        dump_committed_event=False,
        release_onset_event=False,
        dump_complete_event=False,
        legacy_dump_start_event=False,
        carry_release_safety_done=False,
        dump_ready=False,
        next_dump_ready_hold_count=0,
        ready_to_dump=False,
        carry_to_dump_reason="",
        carry_to_return_reason="",
    )


def _default_dig_status(**overrides: Any) -> DigTransitionStatus:
    values: dict[str, Any] = {
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


def _default_dump_status() -> DumpTransitionStatus:
    return DumpTransitionStatus(
        mass_in_bucket_kg=0.0,
        deposited_mass_in_target_box_kg=0.0,
        deposit_delta_since_dump_start_kg=0.0,
        semantic_boundary_profile_active=False,
        dump_complete_event=False,
        legacy_dump_end_event=False,
        boundary_dump_done=False,
        dump_done_mass_low=False,
        next_dump_done_hold_count=0,
        ready_to_return=False,
        coverage_completion_reason="dump_mass_low",
        dump_to_return_reason="dump_to_return_mass_low",
    )


def _default_return_status() -> ReturnTransitionStatus:
    return ReturnTransitionStatus(
        semantic_boundary_profile_active=False,
        next_dig_event=False,
        return_next_dig_event_seen=False,
        next_or_seen_dig_event=False,
        entry_close=False,
        handoff_ready=False,
        direct_handoff_ready=False,
        shallow_guard_allowed=False,
        completed_transition=False,
    )


class _TransitionStatusProvider:
    def __init__(
        self,
        *,
        dig_transition_status: Callable[
            [dict[str, Any], Any | None],
            DigTransitionStatus,
        ]
        | None = None,
        carry_transition_status: Callable[
            [dict[str, Any], Any | None],
            CarryTransitionStatus,
        ]
        | None = None,
        dump_transition_status: Callable[
            [dict[str, Any], Any | None],
            DumpTransitionStatus,
        ]
        | None = None,
        sync_dig_transition_reason: Callable[[DigTransitionStatus], None]
        | None = None,
        refresh_return_transition_state: Callable[[dict[str, Any]], None]
        | None = None,
        return_transition_status: Callable[
            [dict[str, Any], Any | None],
            ReturnTransitionStatus,
        ]
        | None = None,
    ) -> None:
        self._dig_transition_status = (
            dig_transition_status or (lambda obs, boundary_event: _default_dig_status())
        )
        self._carry_transition_status = carry_transition_status or (
            lambda obs, boundary_event: _default_carry_status()
        )
        self._dump_transition_status = dump_transition_status or (
            lambda obs, boundary_event: _default_dump_status()
        )
        self._sync_dig_transition_reason = (
            sync_dig_transition_reason or (lambda status: None)
        )
        self._refresh_return_transition_state = (
            refresh_return_transition_state or (lambda obs: None)
        )
        self._return_transition_status = return_transition_status or (
            lambda obs, boundary_event: _default_return_status()
        )

    def dig_transition_status(
        self,
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> DigTransitionStatus:
        return self._dig_transition_status(obs, boundary_event)

    def carry_transition_status(
        self,
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> CarryTransitionStatus:
        return self._carry_transition_status(obs, boundary_event)

    def dump_transition_status(
        self,
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> DumpTransitionStatus:
        return self._dump_transition_status(obs, boundary_event)

    def sync_dig_transition_reason(
        self,
        status: DigTransitionStatus,
    ) -> None:
        self._sync_dig_transition_reason(status)

    def return_transition_status(
        self,
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> ReturnTransitionStatus:
        return self._return_transition_status(obs, boundary_event)

    def refresh_return_transition_state(
        self,
        obs: dict[str, Any],
    ) -> None:
        self._refresh_return_transition_state(obs)


def _decision_capabilities(
    *,
    current_skill_name: Callable[[], str] | None = None,
    current_switch_reason: Callable[[], str] | None = None,
    should_end_bootstrap: Callable[..., bool] | None = None,
    bootstrap_end_mode: Callable[[], str] | None = None,
    should_pre_dig_align_before_dig: Callable[[], bool] | None = None,
    maybe_handle_pre_dig_align_skill: Callable[[dict[str, Any]], bool] | None = None,
    dig_transition_status: Callable[
        [dict[str, Any], Any | None],
        DigTransitionStatus,
    ]
    | None = None,
    carry_transition_status: Callable[
        [dict[str, Any], Any | None],
        CarryTransitionStatus,
    ]
    | None = None,
    dump_transition_status: Callable[
        [dict[str, Any], Any | None],
        DumpTransitionStatus,
    ]
    | None = None,
    sync_dig_transition_reason: Callable[[DigTransitionStatus], None] | None = None,
    refresh_return_transition_state: Callable[[dict[str, Any]], None] | None = None,
    return_transition_status: Callable[
        [dict[str, Any], Any | None],
        ReturnTransitionStatus,
    ]
    | None = None,
) -> PrimitiveDecisionCapabilities:
    return PrimitiveDecisionCapabilities.from_ports(
        PrimitiveDecisionCapabilitiesPorts(
            current_skill_name=current_skill_name or (lambda: "dig"),
            current_switch_reason=current_switch_reason or (lambda: ""),
            should_end_bootstrap=should_end_bootstrap
            or (lambda *, obs, boundary_event: False),
            bootstrap_end_mode=bootstrap_end_mode
            or (lambda: "first_qualified_dig_start"),
            should_pre_dig_align_before_dig=(
                should_pre_dig_align_before_dig or (lambda: False)
            ),
            transition_status_provider=_TransitionStatusProvider(
                dig_transition_status=dig_transition_status,
                carry_transition_status=carry_transition_status,
                dump_transition_status=dump_transition_status,
                sync_dig_transition_reason=sync_dig_transition_reason,
                refresh_return_transition_state=refresh_return_transition_state,
                return_transition_status=return_transition_status,
            ),
            maybe_handle_residual_pre_dig_align=(
                maybe_handle_pre_dig_align_skill or (lambda obs: False)
            ),
        )
    )


def _legacy_fsm_branch_ports(
    *,
    state: dict[str, str] | None = None,
) -> LegacyFSMBranchPorts:
    state = state if state is not None else {"skill": "legacy_skill", "reason": ""}

    return LegacyFSMBranchPorts(
        bootstrap_skill_name="bootstrap",
        pre_dig_align_skill_name="pre_dig_align",
        dig_skill_name="dig",
        carry_skill_name="carry",
        dump_skill_name="dump",
        return_skill_name="return",
        capabilities=_decision_capabilities(
            current_skill_name=lambda: state["skill"],
            current_switch_reason=lambda: state["reason"],
        ),
    )


def _legacy_fsm_dig_branch(
    *,
    current_skill_name: Callable[[], str] | None = None,
    dig_transition_status: Callable[
        [dict[str, Any], Any | None],
        DigTransitionStatus,
    ]
    | None = None,
) -> LegacyFSMDigBranch:
    return LegacyFSMDigBranch(
        config=LegacyFSMDigConfig(dig_skill_name="dig"),
        capabilities=_decision_capabilities(
            current_skill_name=current_skill_name or (lambda: "dig"),
            dig_transition_status=dig_transition_status
            or (lambda obs, boundary_event: _default_dig_status()),
        ),
    )


def test_legacy_fsm_branch_set_from_ports_builds_backend_and_runner() -> None:
    branch_set = LegacyFSMBranchSet.from_ports(_legacy_fsm_branch_ports())

    backend = branch_set.requested_decision_backend()
    runner = branch_set.requested_runner()

    assert isinstance(backend, LegacyFSMRequestedDecisionBackend)
    assert isinstance(runner, PrimitiveRequestedBranchRunner)
    assert runner.bootstrap_branch is branch_set.bootstrap_branch
    assert runner.dig_branch is branch_set.dig_branch
    assert runner.carry_branch is branch_set.carry_branch
    assert runner.dump_branch is branch_set.dump_branch
    assert runner.return_branch is branch_set.return_branch
    assert runner.residual_branch is branch_set.residual_branch


def test_legacy_fsm_branch_ports_exposes_decision_capabilities_not_callback_bag() -> None:
    ports = _legacy_fsm_branch_ports()
    field_names = {field.name for field in fields(LegacyFSMBranchPorts)}

    assert isinstance(ports.capabilities, PrimitiveDecisionCapabilities)
    for removed_name in (
        "current_skill_name",
        "current_switch_reason",
        "should_end_bootstrap",
        "bootstrap_end_mode",
        "should_pre_dig_align_before_dig",
        "maybe_handle_pre_dig_align_skill",
        "dig_transition_status",
        "carry_transition_status",
        "dump_transition_status",
        "return_transition_status",
        "dig_exit_guard_ready",
        "dig_bad_replan_ready",
        "dig_complete_boundary_low_payload",
        "dig_to_carry_ready",
        "dig_to_carry_reason",
    ):
        assert removed_name not in field_names


def test_legacy_fsm_branch_set_requested_backend_uses_stable_order() -> None:
    calls: list[str] = []
    expected = _requested_no_change_result(decision_source="return_branch")
    branch_set = LegacyFSMBranchSet(
        bootstrap_branch=_RecordingBranch("bootstrap", None, calls),
        dig_branch=_RecordingBranch("dig", None, calls),
        carry_branch=_RecordingBranch("carry", None, calls),
        dump_branch=_RecordingBranch("dump", None, calls),
        return_branch=_RecordingBranch("return", expected, calls),
        residual_branch=_RecordingBranch("residual", _requested_no_change_result(), calls),
    )

    result = branch_set.requested_decision_backend().decide_tick(
        obs={},
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="return",
            dig_progress_updated=False,
        ),
    )

    assert result is expected
    assert calls == ["bootstrap", "dig", "carry", "dump", "return"]


def test_legacy_fsm_branch_set_compatibility_backend_uses_legacy_order() -> None:
    calls: list[str] = []
    expected = _requested_no_change_result(decision_source="dig_branch")
    branch_set = LegacyFSMBranchSet(
        bootstrap_branch=_RecordingBranch("bootstrap", None, calls),
        dig_branch=_RecordingBranch("dig", expected, calls),
        carry_branch=_RecordingBranch("carry", _requested_no_change_result(), calls),
        dump_branch=_RecordingBranch("dump", _requested_no_change_result(), calls),
        return_branch=_RecordingBranch("return", _requested_no_change_result(), calls),
        residual_branch=_RecordingBranch("residual", None, calls),
    )

    backend = branch_set.compatibility_decision_backend()
    result = backend.decide_tick(
        obs={},
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="dig",
            dig_progress_updated=True,
        ),
    )

    assert isinstance(backend, LegacyFSMCompatibilityDecisionBackend)
    assert result is expected
    assert calls == ["bootstrap", "residual", "dig"]


def test_legacy_fsm_branch_set_compatibility_backend_returns_none_on_all_miss() -> None:
    calls: list[str] = []
    branch_set = LegacyFSMBranchSet(
        bootstrap_branch=_RecordingBranch("bootstrap", None, calls),
        dig_branch=_RecordingBranch("dig", None, calls),
        carry_branch=_RecordingBranch("carry", None, calls),
        dump_branch=_RecordingBranch("dump", None, calls),
        return_branch=_RecordingBranch("return", None, calls),
        residual_branch=_RecordingBranch("residual", None, calls),
    )

    result = branch_set.compatibility_decision_backend().decide_tick(
        obs={},
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="legacy_skill",
            dig_progress_updated=False,
        ),
    )

    assert result is None
    assert calls == ["bootstrap", "residual", "dig", "carry", "dump", "return"]


def test_legacy_fsm_branch_ports_do_not_expose_mainline_mutation_ports() -> None:
    field_names = {field.name for field in fields(LegacyFSMBranchPorts)}

    assert {
        "set_skill",
        "increment_dig_exit_guard_replan_count",
        "reject_active_coverage_corridor",
        "restart_after_failed_dig",
        "increment_dig_bad_replan_count",
        "complete_cell_entry_dig",
        "complete_coverage_dig",
        "complete_coverage_dump",
        "set_return_or_direct_handoff",
        "set_dump_ready_hold_count",
        "deposited_mass",
        "set_dump_start_deposited_mass",
        "set_dump_done_hold_count",
        "mark_return_next_dig_event_seen",
        "complete_return_transition",
        "next_skill_after_return_transition",
    }.isdisjoint(field_names)


def test_mainline_legacy_fsm_branches_do_not_expose_local_effect_application() -> None:
    for branch_type in (
        LegacyFSMBootstrapBranch,
        LegacyFSMDigBranch,
        LegacyFSMCarryBranch,
        LegacyFSMDumpBranch,
        LegacyFSMReturnBranch,
    ):
        assert not hasattr(branch_type, "maybe_handle")
        assert not hasattr(branch_type, "_apply_effects")


def test_legacy_fsm_branch_set_requested_backend_fails_fast_when_all_decline() -> None:
    calls: list[str] = []
    branch_set = LegacyFSMBranchSet(
        bootstrap_branch=_RecordingBranch("bootstrap", None, calls),
        dig_branch=_RecordingBranch("dig", None, calls),
        carry_branch=_RecordingBranch("carry", None, calls),
        dump_branch=_RecordingBranch("dump", None, calls),
        return_branch=_RecordingBranch("return", None, calls),
        residual_branch=_RecordingBranch("residual", None, calls),
    )

    try:
        branch_set.requested_decision_backend().decide_tick(
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
        raise AssertionError("backend accepted an unhandled planner skill")

    assert calls == ["bootstrap", "dig", "carry", "dump", "return", "residual"]
    assert "broad legacy fallback is retired" in message
    assert "legacy_skill" in message


def test_legacy_fsm_branch_set_compatibility_order_keeps_residual_second() -> None:
    calls: list[str] = []
    expected = _requested_no_change_result(decision_source="return_branch")
    branch_set = LegacyFSMBranchSet(
        bootstrap_branch=_RecordingBranch("bootstrap", None, calls),
        dig_branch=_RecordingBranch("dig", None, calls),
        carry_branch=_RecordingBranch("carry", None, calls),
        dump_branch=_RecordingBranch("dump", None, calls),
        return_branch=_RecordingBranch("return", expected, calls),
        residual_branch=_RecordingBranch("residual", None, calls),
    )

    result = branch_set.compatibility_decision_backend().decide_tick(
        obs={},
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="return",
            dig_progress_updated=False,
        ),
    )

    assert result is expected
    assert calls == ["bootstrap", "residual", "dig", "carry", "dump", "return"]


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


def test_requested_branch_runner_uses_single_context_for_ordered_branches() -> None:
    calls: list[str] = []
    contexts: list[PrimitiveDecisionContext] = []
    expected = _requested_no_change_result(decision_source="return_branch")
    runner = PrimitiveRequestedBranchRunner(
        bootstrap_branch=_RecordingBranch("bootstrap", None, calls, contexts),
        dig_branch=_RecordingBranch("dig", None, calls, contexts),
        carry_branch=_RecordingBranch("carry", None, calls, contexts),
        dump_branch=_RecordingBranch("dump", None, calls, contexts),
        return_branch=_RecordingBranch("return", expected, calls, contexts),
        residual_branch=_RecordingBranch("residual", None, calls, contexts),
    )
    context = PrimitiveDecisionContext.from_tick(
        obs={"qpos": [1.0]},
        boundary_event=object(),
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="return",
            dig_progress_updated=False,
        ),
    )

    result = runner.decide_context(context)

    assert result is expected
    assert calls == ["bootstrap", "dig", "carry", "dump", "return"]
    assert contexts == [context, context, context, context, context]


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


def test_compatibility_backend_uses_single_context_for_legacy_order() -> None:
    calls: list[str] = []
    contexts: list[PrimitiveDecisionContext] = []
    expected = _requested_no_change_result(decision_source="dig_branch")
    branch_set = LegacyFSMBranchSet(
        bootstrap_branch=_RecordingBranch("bootstrap", None, calls, contexts),
        dig_branch=_RecordingBranch("dig", expected, calls, contexts),
        carry_branch=_RecordingBranch("carry", None, calls, contexts),
        dump_branch=_RecordingBranch("dump", None, calls, contexts),
        return_branch=_RecordingBranch("return", None, calls, contexts),
        residual_branch=_RecordingBranch("residual", None, calls, contexts),
    )
    context = PrimitiveDecisionContext.from_tick(
        obs={},
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="dig",
            dig_progress_updated=True,
        ),
    )

    result = branch_set.compatibility_decision_backend().decide_context(context)

    assert result is expected
    assert calls == ["bootstrap", "residual", "dig"]
    assert contexts == [context, context, context]


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
        capabilities=_decision_capabilities(
            current_skill_name=lambda: state["skill"],
            current_switch_reason=lambda: state["reason"],
            maybe_handle_pre_dig_align_skill=maybe_handle_pre_dig_align_skill,
        ),
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
        capabilities=_decision_capabilities(
            current_skill_name=lambda: "dig",
            maybe_handle_pre_dig_align_skill=lambda obs: True,
        ),
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
    branch = LegacyFSMBootstrapBranch(
        config=LegacyFSMBootstrapConfig(
            bootstrap_skill_name="bootstrap",
            pre_dig_align_skill_name="pre_dig_align",
        ),
        capabilities=_decision_capabilities(
            current_skill_name=lambda: state["skill"],
            should_end_bootstrap=lambda *, obs, boundary_event: True,
            bootstrap_end_mode=lambda: "first_qualified_dig_start",
            should_pre_dig_align_before_dig=lambda: True,
        ),
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

    assert result is not None
    assert result.effects == (
        SwitchSkillEffect(
            target_skill_name="pre_dig_align",
            switch_reason="bootstrap_to_pre_dig_align",
        ),
    )


def test_legacy_fsm_bootstrap_branch_returns_requested_switch_effect() -> None:
    obs: dict[str, Any] = {"qpos": [1.0]}
    boundary_event = object()
    branch = LegacyFSMBootstrapBranch(
        config=LegacyFSMBootstrapConfig(
            bootstrap_skill_name="bootstrap",
            pre_dig_align_skill_name="pre_dig_align",
        ),
        capabilities=_decision_capabilities(
            current_skill_name=lambda: "bootstrap",
            should_end_bootstrap=lambda *, obs, boundary_event: True,
            bootstrap_end_mode=lambda: "first_qualified_dig_start",
            should_pre_dig_align_before_dig=lambda: True,
        ),
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
    def fail_dig_status(
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> DigTransitionStatus:
        raise AssertionError("bootstrap branch must not request dig status")

    def fail_carry_status(
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> CarryTransitionStatus:
        raise AssertionError("bootstrap branch must not request carry status")

    def fail_dump_status(
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> DumpTransitionStatus:
        raise AssertionError("bootstrap branch must not request dump status")

    def fail_return_status(
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> ReturnTransitionStatus:
        raise AssertionError("bootstrap branch must not request return status")

    branch = LegacyFSMBootstrapBranch(
        config=LegacyFSMBootstrapConfig(
            bootstrap_skill_name="bootstrap",
            pre_dig_align_skill_name="pre_dig_align",
        ),
        capabilities=_decision_capabilities(
            current_skill_name=lambda: "dig",
            should_end_bootstrap=lambda *, obs, boundary_event: True,
            bootstrap_end_mode=lambda: "first_qualified_dig_start",
            should_pre_dig_align_before_dig=lambda: True,
            dig_transition_status=fail_dig_status,
            carry_transition_status=fail_carry_status,
            dump_transition_status=fail_dump_status,
            return_transition_status=fail_return_status,
        ),
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


def test_legacy_fsm_bootstrap_branch_consumes_backend_facts_no_change() -> None:
    calls: list[str] = []
    obs: dict[str, Any] = {"qpos": [1.0]}
    boundary_event = object()
    status = BootstrapDecisionStatus(
        current_skill_name="bootstrap",
        should_end_bootstrap=False,
        bootstrap_end_mode="first_qualified_dig_start",
        should_pre_dig_align_before_dig=False,
        next_skill_after_bootstrap="dig",
    )

    class _BootstrapBackendFacts:
        def __init__(self, common: PrimitiveDecisionFacts) -> None:
            self.common = common

        def bootstrap_decision(
            self,
            *,
            pre_dig_align_skill_name: str,
        ) -> PrimitiveBootstrapDecisionFacts:
            assert pre_dig_align_skill_name == "pre_dig_align"
            calls.append("bootstrap_status")
            return PrimitiveBootstrapDecisionFacts(common=self.common, status=status)

        def dig_transition(self) -> PrimitiveDigTransitionFacts:
            raise AssertionError("bootstrap branch must not read dig transition")

        def carry_transition(self) -> PrimitiveCarryTransitionFacts:
            raise AssertionError("bootstrap branch must not read carry transition")

        def dump_transition(self) -> PrimitiveDumpTransitionFacts:
            raise AssertionError("bootstrap branch must not read dump transition")

        def return_transition(self) -> PrimitiveReturnTransitionFacts:
            raise AssertionError("bootstrap branch must not read return transition")

    class _BootstrapFactsCapabilities:
        def backend_facts(
            self,
            context: PrimitiveDecisionContext,
            *,
            facts: PrimitiveDecisionFacts | None = None,
        ) -> _BootstrapBackendFacts:
            assert facts is None
            assert context.obs is obs
            assert context.boundary_event is boundary_event
            calls.append("current_skill")
            calls.append("current_reason")
            common = PrimitiveDecisionFacts.from_context(
                context,
                current_skill_name="bootstrap",
                current_switch_reason="",
            )
            return _BootstrapBackendFacts(common)

        def decision_facts(
            self,
            context: PrimitiveDecisionContext,
        ) -> PrimitiveDecisionFacts:
            raise AssertionError("bootstrap branch must consume backend facts access")

        def bootstrap_status(self, *args: Any, **kwargs: Any) -> BootstrapDecisionStatus:
            raise AssertionError("bootstrap branch must consume bootstrap facts view")

        def handle_residual_pre_dig_align(
            self,
            context: PrimitiveDecisionContext,
        ) -> bool:
            raise AssertionError("bootstrap branch must not call residual handler")

        def sync_dig_transition_reason(
            self,
            dig_facts: PrimitiveDigTransitionFacts,
        ) -> None:
            raise AssertionError("bootstrap branch must not sync dig reason")

        def refresh_return_transition_state(
            self,
            context: PrimitiveDecisionContext,
        ) -> None:
            raise AssertionError("bootstrap branch must not refresh return")

    branch = LegacyFSMBootstrapBranch(
        config=LegacyFSMBootstrapConfig(
            bootstrap_skill_name="bootstrap",
            pre_dig_align_skill_name="pre_dig_align",
        ),
        capabilities=_BootstrapFactsCapabilities(),
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

    assert calls == ["current_skill", "current_reason", "bootstrap_status"]
    assert result is not None
    assert result.decision_source == "legacy_fsm_bootstrap_requested_effect"
    assert result.status == "no_change"
    assert result.skill_before == "bootstrap"
    assert result.skill_after == "bootstrap"
    assert result.switch_reason == ""
    assert result.effects == ()


def test_legacy_fsm_bootstrap_branch_consumes_backend_facts_switch_to_dig() -> None:
    calls: list[str] = []
    obs: dict[str, Any] = {"qpos": [1.0]}
    boundary_event = object()
    status = BootstrapDecisionStatus(
        current_skill_name="bootstrap",
        should_end_bootstrap=True,
        bootstrap_end_mode="first_qualified_dig_start",
        should_pre_dig_align_before_dig=False,
        next_skill_after_bootstrap="dig",
    )

    class _BootstrapBackendFacts:
        def __init__(self, common: PrimitiveDecisionFacts) -> None:
            self.common = common

        def bootstrap_decision(
            self,
            *,
            pre_dig_align_skill_name: str,
        ) -> PrimitiveBootstrapDecisionFacts:
            assert pre_dig_align_skill_name == "pre_dig_align"
            calls.append("bootstrap_status")
            return PrimitiveBootstrapDecisionFacts(common=self.common, status=status)

    class _BootstrapFactsCapabilities:
        def backend_facts(
            self,
            context: PrimitiveDecisionContext,
            *,
            facts: PrimitiveDecisionFacts | None = None,
        ) -> _BootstrapBackendFacts:
            assert facts is None
            calls.append("current_skill")
            calls.append("current_reason")
            return _BootstrapBackendFacts(
                PrimitiveDecisionFacts.from_context(
                    context,
                    current_skill_name="bootstrap",
                    current_switch_reason="",
                )
            )

        def decision_facts(
            self,
            context: PrimitiveDecisionContext,
        ) -> PrimitiveDecisionFacts:
            raise AssertionError("bootstrap branch must consume backend facts access")

        def bootstrap_status(self, *args: Any, **kwargs: Any) -> BootstrapDecisionStatus:
            raise AssertionError("bootstrap branch must consume bootstrap facts view")

    branch = LegacyFSMBootstrapBranch(
        config=LegacyFSMBootstrapConfig(
            bootstrap_skill_name="bootstrap",
            pre_dig_align_skill_name="pre_dig_align",
        ),
        capabilities=_BootstrapFactsCapabilities(),
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

    assert calls == ["current_skill", "current_reason", "bootstrap_status"]
    assert result is not None
    assert result.status == "skill_switch"
    assert result.skill_after == "dig"
    assert result.switch_reason == "bootstrap_to_dig"
    assert result.effects == (
        SwitchSkillEffect(
            target_skill_name="dig",
            switch_reason="bootstrap_to_dig",
        ),
    )


def test_legacy_fsm_bootstrap_branch_ignores_non_bootstrap_skill() -> None:
    branch = LegacyFSMBootstrapBranch(
        config=LegacyFSMBootstrapConfig(
            bootstrap_skill_name="bootstrap",
            pre_dig_align_skill_name="pre_dig_align",
        ),
        capabilities=_decision_capabilities(
            current_skill_name=lambda: "dig",
            should_end_bootstrap=lambda *, obs, boundary_event: True,
            bootstrap_end_mode=lambda: "disabled",
            should_pre_dig_align_before_dig=lambda: False,
        ),
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


def test_legacy_fsm_dig_branch_completes_dig_to_carry_in_order() -> None:
    obs: dict[str, Any] = {"qpos": [1.0]}
    boundary_event = object()
    branch = _legacy_fsm_dig_branch(
        dig_transition_status=lambda obs, boundary_event: _default_dig_status(
            dig_to_carry_ready=True,
            dig_to_carry_reason="boundary_confirmed",
        ),
    )

    result = branch.decide_tick(
        obs=obs,
        boundary_event=boundary_event,
        preparation=PrimitiveTickPreparation(
            boundary_event=boundary_event,
            skill_name_before_decision="dig",
            dig_progress_updated=True,
        ),
    )

    assert result is not None
    assert result.effects == (
        CompleteCellEntryDigCompatibilityEffect(),
        CompleteCoverageDigEffect(),
        SwitchSkillEffect(
            target_skill_name="carry",
            switch_reason="dig_to_carry_boundary_confirmed",
        ),
    )


def test_legacy_fsm_dig_branch_consumes_backend_facts_and_syncs_reason() -> None:
    calls: list[str] = []
    obs: dict[str, Any] = {"qpos": [1.0]}
    boundary_event = object()
    common_facts: PrimitiveDecisionFacts | None = None
    status = _default_dig_status(
        dig_to_carry_ready=True,
        dig_to_carry_reason="boundary_confirmed",
    )

    class _DigBackendFacts:
        def __init__(self, common: PrimitiveDecisionFacts) -> None:
            self.common = common

        def dig_transition(self) -> PrimitiveDigTransitionFacts:
            calls.append("dig_status")
            return PrimitiveDigTransitionFacts(common=self.common, status=status)

    class _DigFactsCapabilities:
        def backend_facts(
            self,
            context: PrimitiveDecisionContext,
            *,
            facts: PrimitiveDecisionFacts | None = None,
        ) -> _DigBackendFacts:
            nonlocal common_facts
            assert facts is None
            assert context.obs is obs
            assert context.boundary_event is boundary_event
            calls.append("current_skill")
            calls.append("current_reason")
            common_facts = PrimitiveDecisionFacts.from_context(
                context,
                current_skill_name="dig",
                current_switch_reason="",
            )
            return _DigBackendFacts(common_facts)

        def decision_facts(
            self,
            context: PrimitiveDecisionContext,
        ) -> PrimitiveDecisionFacts:
            raise AssertionError("dig branch must consume backend facts access")

        def dig_transition_facts(
            self,
            context: PrimitiveDecisionContext,
            *,
            facts: PrimitiveDecisionFacts | None = None,
        ) -> PrimitiveDigTransitionFacts:
            raise AssertionError("dig branch must consume backend facts access")

        def sync_dig_transition_reason(
            self,
            dig_facts: PrimitiveDigTransitionFacts,
        ) -> None:
            assert dig_facts.common is common_facts
            assert dig_facts.status is status
            calls.append("sync_dig_reason")

        def dig_transition_status(
            self,
            context: PrimitiveDecisionContext,
        ) -> DigTransitionStatus:
            raise AssertionError("dig branch must consume dig facts view")

    branch = LegacyFSMDigBranch(
        config=LegacyFSMDigConfig(dig_skill_name="dig"),
        capabilities=_DigFactsCapabilities(),
    )

    result = branch.decide_tick(
        obs=obs,
        boundary_event=boundary_event,
        preparation=PrimitiveTickPreparation(
            boundary_event=boundary_event,
            skill_name_before_decision="dig",
            dig_progress_updated=True,
        ),
    )

    assert calls == [
        "current_skill",
        "current_reason",
        "dig_status",
        "sync_dig_reason",
    ]
    assert result is not None
    assert result.effects == (
        CompleteCellEntryDigCompatibilityEffect(),
        CompleteCoverageDigEffect(),
        SwitchSkillEffect(
            target_skill_name="carry",
            switch_reason="dig_to_carry_boundary_confirmed",
        ),
    )


def test_legacy_fsm_dig_branch_requested_exit_guard_effects_in_order() -> None:
    branch = _legacy_fsm_dig_branch(
        dig_transition_status=lambda obs, boundary_event: _default_dig_status(
            dig_exit_guard_ready=True,
            dig_bad_replan_ready=True,
            dig_complete_boundary_low_payload=True,
            dig_to_carry_ready=True,
            dig_to_carry_reason="boundary_confirmed",
        ),
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

    assert result is not None
    assert result.side_effects_applied is False
    assert result.effects == (
        IncrementDigExitGuardReplanCountEffect(),
        RejectActiveCoverageCorridorEffect(reason="exit_overshoot_low_payload"),
        RestartAfterFailedDigEffect(reason="exit_overshoot_low_payload"),
    )


def test_legacy_fsm_dig_branch_requested_bad_dig_effects_in_order() -> None:
    branch = _legacy_fsm_dig_branch(
        dig_transition_status=lambda obs, boundary_event: _default_dig_status(
            dig_bad_replan_ready=True,
            dig_complete_boundary_low_payload=True,
            dig_to_carry_ready=True,
            dig_to_carry_reason="boundary_confirmed",
        ),
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
    branch = _legacy_fsm_dig_branch(
        dig_transition_status=lambda obs, boundary_event: _default_dig_status(
            dig_complete_boundary_low_payload=True,
            dig_to_carry_ready=True,
            dig_to_carry_reason="boundary_confirmed",
        ),
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
    branch = _legacy_fsm_dig_branch(
        dig_transition_status=lambda obs, boundary_event: _default_dig_status(
            dig_to_carry_ready=True,
            dig_to_carry_reason="boundary_confirmed",
        ),
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
    branch = _legacy_fsm_dig_branch()

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
    def fail_if_called(obs: dict[str, Any], boundary_event: Any | None) -> DigTransitionStatus:
        raise AssertionError("non-dig skill must not request dig transition status")

    branch = _legacy_fsm_dig_branch(
        current_skill_name=lambda: "carry",
        dig_transition_status=fail_if_called,
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


def test_legacy_fsm_dig_branch_non_dig_skill_does_not_read_or_sync_dig_facts() -> None:
    calls: list[str] = []

    class _NonDigBackendFacts:
        def __init__(self, common: PrimitiveDecisionFacts) -> None:
            self.common = common

        def dig_transition(self) -> PrimitiveDigTransitionFacts:
            calls.append("dig_status")
            raise AssertionError("non-dig skill must not request dig facts")

    class _NonDigCapabilities:
        def backend_facts(
            self,
            context: PrimitiveDecisionContext,
            *,
            facts: PrimitiveDecisionFacts | None = None,
        ) -> _NonDigBackendFacts:
            assert facts is None
            calls.append("current_skill")
            calls.append("current_reason")
            common = PrimitiveDecisionFacts.from_context(
                context,
                current_skill_name="carry",
                current_switch_reason="dig_to_carry_loaded",
            )
            return _NonDigBackendFacts(common)

        def decision_facts(
            self,
            context: PrimitiveDecisionContext,
        ) -> PrimitiveDecisionFacts:
            raise AssertionError("dig branch must consume backend facts access")

        def dig_transition_facts(
            self,
            context: PrimitiveDecisionContext,
            *,
            facts: PrimitiveDecisionFacts | None = None,
        ) -> PrimitiveDigTransitionFacts:
            raise AssertionError("dig branch must consume backend facts access")

        def sync_dig_transition_reason(
            self,
            dig_facts: PrimitiveDigTransitionFacts,
        ) -> None:
            calls.append("sync_dig_reason")
            raise AssertionError("non-dig skill must not sync dig reason")

    branch = LegacyFSMDigBranch(
        config=LegacyFSMDigConfig(dig_skill_name="dig"),
        capabilities=_NonDigCapabilities(),
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
    assert calls == ["current_skill", "current_reason"]


def test_legacy_fsm_compatibility_backend_returns_dig_requested_effects() -> None:
    branch_set = LegacyFSMBranchSet(
        bootstrap_branch=_RecordingBranch("bootstrap", None, []),
        dig_branch=_legacy_fsm_dig_branch(
        dig_transition_status=lambda obs, boundary_event: _default_dig_status(
            dig_exit_guard_ready=True,
            dig_bad_replan_ready=True,
            dig_complete_boundary_low_payload=True,
            dig_to_carry_ready=True,
            dig_to_carry_reason="boundary_confirmed",
        ),
        ),
        carry_branch=_RecordingBranch("carry", None, []),
        dump_branch=_RecordingBranch("dump", None, []),
        return_branch=_RecordingBranch("return", None, []),
        residual_branch=_RecordingBranch("residual", None, []),
    )

    result = branch_set.compatibility_decision_backend().decide_tick(
        obs={"qpos": [1.0]},
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="dig",
            dig_progress_updated=True,
        ),
    )

    assert result is not None
    assert result.side_effects_applied is False
    assert result.effects == (
        IncrementDigExitGuardReplanCountEffect(),
        RejectActiveCoverageCorridorEffect(reason="exit_overshoot_low_payload"),
        RestartAfterFailedDigEffect(reason="exit_overshoot_low_payload"),
    )


def test_legacy_fsm_dig_branch_ignores_non_dig_skill() -> None:
    def fail_if_called(obs: dict[str, Any], boundary_event: Any | None) -> DigTransitionStatus:
        raise AssertionError("non-dig skill must not request dig transition status")

    branch = _legacy_fsm_dig_branch(
        current_skill_name=lambda: "carry",
        dig_transition_status=fail_if_called,
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


def test_legacy_fsm_carry_branch_release_safety_handoffs_to_return() -> None:
    obs: dict[str, Any] = {"qpos": [1.0]}
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
        capabilities=_decision_capabilities(
            current_skill_name=lambda: "carry",
            carry_transition_status=lambda obs, boundary_event: status,
        ),
    )

    result = branch.decide_tick(
        obs=obs,
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="carry",
            dig_progress_updated=False,
        ),
    )

    assert result is not None
    assert result.effects == (
        CompleteCoverageDumpEffect(reason="carry_release_safety"),
        SetReturnOrDirectHandoffEffect(reason="carry_to_return_release_safety"),
    )


def test_legacy_fsm_carry_branch_requested_release_safety_handoff_effects() -> None:
    branch = LegacyFSMCarryBranch(
        config=LegacyFSMCarryConfig(carry_skill_name="carry"),
        capabilities=_decision_capabilities(
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
        ),
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
        capabilities=_decision_capabilities(
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
        ),
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
        capabilities=_decision_capabilities(
            current_skill_name=lambda: "carry",
            carry_transition_status=lambda obs, boundary_event: status,
        ),
    )

    result = branch.decide_tick(
        obs=obs,
        boundary_event=boundary_event,
        preparation=PrimitiveTickPreparation(
            boundary_event=boundary_event,
            skill_name_before_decision="carry",
            dig_progress_updated=False,
        ),
    )

    assert result is not None
    assert result.effects == (
        SetDumpReadyHoldCountEffect(value=3),
        SetDumpStartDepositedMassFromObservationEffect(),
        SwitchSkillEffect(
            target_skill_name="dump",
            switch_reason="carry_to_dump_dump_committed_boundary",
        ),
    )


def test_legacy_fsm_carry_branch_consumes_backend_facts_view() -> None:
    calls: list[str] = []
    obs: dict[str, Any] = {"qpos": [1.0]}
    boundary_event = object()
    common_facts: PrimitiveDecisionFacts | None = None
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

    class _CarryBackendFacts:
        def __init__(self, common: PrimitiveDecisionFacts) -> None:
            self.common = common

        def carry_transition(self) -> PrimitiveCarryTransitionFacts:
            calls.append("carry_status")
            return PrimitiveCarryTransitionFacts(common=self.common, status=status)

    class _CarryFactsCapabilities:
        def backend_facts(
            self,
            context: PrimitiveDecisionContext,
            *,
            facts: PrimitiveDecisionFacts | None = None,
        ) -> _CarryBackendFacts:
            nonlocal common_facts
            assert facts is None
            assert context.obs is obs
            assert context.boundary_event is boundary_event
            calls.append("current_skill")
            calls.append("current_reason")
            common_facts = PrimitiveDecisionFacts.from_context(
                context,
                current_skill_name="carry",
                current_switch_reason="dig_to_carry_loaded",
            )
            return _CarryBackendFacts(common_facts)

        def decision_facts(
            self,
            context: PrimitiveDecisionContext,
        ) -> PrimitiveDecisionFacts:
            raise AssertionError("carry branch must consume backend facts access")

        def carry_transition_facts(
            self,
            context: PrimitiveDecisionContext,
            *,
            facts: PrimitiveDecisionFacts | None = None,
        ) -> PrimitiveCarryTransitionFacts:
            raise AssertionError("carry branch must consume backend facts access")

        def carry_transition_status(
            self,
            context: PrimitiveDecisionContext,
        ) -> CarryTransitionStatus:
            raise AssertionError("carry branch must consume carry facts view")

    branch = LegacyFSMCarryBranch(
        config=LegacyFSMCarryConfig(carry_skill_name="carry"),
        capabilities=_CarryFactsCapabilities(),
    )

    result = branch.decide_tick(
        obs=obs,
        boundary_event=boundary_event,
        preparation=PrimitiveTickPreparation(
            boundary_event=boundary_event,
            skill_name_before_decision="carry",
            dig_progress_updated=False,
        ),
    )

    assert calls == ["current_skill", "current_reason", "carry_status"]
    assert result is not None
    assert result.effects == (
        SetDumpReadyHoldCountEffect(value=3),
        SetDumpStartDepositedMassFromObservationEffect(),
        SwitchSkillEffect(
            target_skill_name="dump",
            switch_reason="carry_to_dump_dump_committed_boundary",
        ),
    )


def test_legacy_fsm_carry_branch_requested_ready_to_dump_effects_in_order() -> None:
    branch = LegacyFSMCarryBranch(
        config=LegacyFSMCarryConfig(carry_skill_name="carry"),
        capabilities=_decision_capabilities(
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
        ),
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
    def fail_if_called(
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> CarryTransitionStatus:
        raise AssertionError("non-carry skill must not request carry transition status")

    branch = LegacyFSMCarryBranch(
        config=LegacyFSMCarryConfig(carry_skill_name="carry"),
        capabilities=_decision_capabilities(
            current_skill_name=lambda: "dump",
            carry_transition_status=fail_if_called,
        ),
    )

    result = branch.decide_tick(
        obs={},
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="dump",
            dig_progress_updated=False,
        ),
    )

    assert result is None


def test_legacy_fsm_carry_branch_non_carry_skill_does_not_read_carry_facts() -> None:
    calls: list[str] = []

    class _NonCarryBackendFacts:
        def __init__(self, common: PrimitiveDecisionFacts) -> None:
            self.common = common

        def carry_transition(self) -> PrimitiveCarryTransitionFacts:
            calls.append("carry_status")
            raise AssertionError("non-carry skill must not request carry facts")

    class _NonCarryCapabilities:
        def backend_facts(
            self,
            context: PrimitiveDecisionContext,
            *,
            facts: PrimitiveDecisionFacts | None = None,
        ) -> _NonCarryBackendFacts:
            assert facts is None
            calls.append("current_skill")
            calls.append("current_reason")
            common = PrimitiveDecisionFacts.from_context(
                context,
                current_skill_name="dump",
                current_switch_reason="carry_to_dump_target_ready",
            )
            return _NonCarryBackendFacts(common)

        def decision_facts(
            self,
            context: PrimitiveDecisionContext,
        ) -> PrimitiveDecisionFacts:
            raise AssertionError("carry branch must consume backend facts access")

        def carry_transition_facts(
            self,
            context: PrimitiveDecisionContext,
            *,
            facts: PrimitiveDecisionFacts | None = None,
        ) -> PrimitiveCarryTransitionFacts:
            raise AssertionError("carry branch must consume backend facts access")

    branch = LegacyFSMCarryBranch(
        config=LegacyFSMCarryConfig(carry_skill_name="carry"),
        capabilities=_NonCarryCapabilities(),
    )

    result = branch.decide_tick(
        obs={},
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="dump",
            dig_progress_updated=False,
        ),
    )

    assert result is None
    assert calls == ["current_skill", "current_reason"]


def test_legacy_fsm_dump_branch_boundary_handoffs_to_return() -> None:
    obs: dict[str, Any] = {"qpos": [1.0]}
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
        capabilities=_decision_capabilities(
            current_skill_name=lambda: "dump",
            dump_transition_status=lambda obs, boundary_event: status,
        ),
    )

    result = branch.decide_tick(
        obs=obs,
        boundary_event=object(),
        preparation=PrimitiveTickPreparation(
            boundary_event=object(),
            skill_name_before_decision="dump",
            dig_progress_updated=False,
        ),
    )

    assert result is not None
    assert result.effects == (
        CompleteCoverageDumpEffect(reason="dump_complete_boundary"),
        SetReturnOrDirectHandoffEffect(reason="dump_to_return_dump_complete_boundary"),
    )


def test_legacy_fsm_dump_branch_consumes_backend_facts_view() -> None:
    calls: list[str] = []
    obs: dict[str, Any] = {"qpos": [1.0]}
    boundary_event = object()
    common_facts: PrimitiveDecisionFacts | None = None
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

    class _DumpBackendFacts:
        def __init__(self, common: PrimitiveDecisionFacts) -> None:
            self.common = common

        def dump_transition(self) -> PrimitiveDumpTransitionFacts:
            calls.append("dump_status")
            return PrimitiveDumpTransitionFacts(common=self.common, status=status)

    class _DumpFactsCapabilities:
        def backend_facts(
            self,
            context: PrimitiveDecisionContext,
            *,
            facts: PrimitiveDecisionFacts | None = None,
        ) -> _DumpBackendFacts:
            nonlocal common_facts
            assert facts is None
            assert context.obs is obs
            assert context.boundary_event is boundary_event
            calls.append("current_skill")
            calls.append("current_reason")
            common_facts = PrimitiveDecisionFacts.from_context(
                context,
                current_skill_name="dump",
                current_switch_reason="carry_to_dump_target_ready",
            )
            return _DumpBackendFacts(common_facts)

        def decision_facts(
            self,
            context: PrimitiveDecisionContext,
        ) -> PrimitiveDecisionFacts:
            raise AssertionError("dump branch must consume backend facts access")

        def dump_transition_facts(
            self,
            context: PrimitiveDecisionContext,
            *,
            facts: PrimitiveDecisionFacts | None = None,
        ) -> PrimitiveDumpTransitionFacts:
            raise AssertionError("dump branch must consume backend facts access")

        def dump_transition_status(
            self,
            context: PrimitiveDecisionContext,
        ) -> DumpTransitionStatus:
            raise AssertionError("dump branch must consume dump facts view")

    branch = LegacyFSMDumpBranch(
        config=LegacyFSMDumpConfig(dump_skill_name="dump"),
        capabilities=_DumpFactsCapabilities(),
    )

    result = branch.decide_tick(
        obs=obs,
        boundary_event=boundary_event,
        preparation=PrimitiveTickPreparation(
            boundary_event=boundary_event,
            skill_name_before_decision="dump",
            dig_progress_updated=False,
        ),
    )

    assert calls == ["current_skill", "current_reason", "dump_status"]
    assert result is not None
    assert result.effects == (
        SetDumpDoneHoldCountEffect(value=2),
        CompleteCoverageDumpEffect(reason="dump_mass_low"),
        SetReturnOrDirectHandoffEffect(reason="dump_to_return_mass_low"),
    )


def test_legacy_fsm_dump_branch_requested_boundary_done_effects() -> None:
    branch = LegacyFSMDumpBranch(
        config=LegacyFSMDumpConfig(dump_skill_name="dump"),
        capabilities=_decision_capabilities(
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
        ),
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

    assert result is not None
    assert result.effects == (
        CompleteCoverageDumpEffect(reason="dump_complete_boundary"),
        SetReturnOrDirectHandoffEffect(reason="dump_to_return_dump_complete_boundary"),
    )


def test_legacy_fsm_dump_branch_mass_low_hold_switches_to_return() -> None:
    obs: dict[str, Any] = {"qpos": [1.0]}
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
        capabilities=_decision_capabilities(
            current_skill_name=lambda: "dump",
            dump_transition_status=lambda obs, boundary_event: status,
        ),
    )

    result = branch.decide_tick(
        obs=obs,
        boundary_event=None,
        preparation=PrimitiveTickPreparation(
            boundary_event=None,
            skill_name_before_decision="dump",
            dig_progress_updated=False,
        ),
    )

    assert result is not None
    assert result.effects == (
        SetDumpDoneHoldCountEffect(value=2),
        CompleteCoverageDumpEffect(reason="dump_mass_low"),
        SetReturnOrDirectHandoffEffect(reason="dump_to_return_mass_low"),
    )


def test_legacy_fsm_dump_branch_requested_ready_to_return_effects_in_order() -> None:
    branch = LegacyFSMDumpBranch(
        config=LegacyFSMDumpConfig(dump_skill_name="dump"),
        capabilities=_decision_capabilities(
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
        ),
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

    assert result is not None
    assert result.effects == (
        SetDumpDoneHoldCountEffect(value=2),
        CompleteCoverageDumpEffect(reason="dump_mass_low"),
        SetReturnOrDirectHandoffEffect(reason="dump_to_return_mass_low"),
    )


def test_legacy_fsm_dump_branch_ignores_non_dump_skill() -> None:
    def fail_if_called(
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> DumpTransitionStatus:
        raise AssertionError("non-dump skill must not request dump transition status")

    branch = LegacyFSMDumpBranch(
        config=LegacyFSMDumpConfig(dump_skill_name="dump"),
        capabilities=_decision_capabilities(
            current_skill_name=lambda: "return",
            dump_transition_status=fail_if_called,
        ),
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

    assert result is None


def test_legacy_fsm_dump_branch_non_dump_skill_does_not_read_dump_facts() -> None:
    calls: list[str] = []

    class _NonDumpBackendFacts:
        def __init__(self, common: PrimitiveDecisionFacts) -> None:
            self.common = common

        def dump_transition(self) -> PrimitiveDumpTransitionFacts:
            calls.append("dump_status")
            raise AssertionError("non-dump skill must not request dump facts")

    class _NonDumpCapabilities:
        def backend_facts(
            self,
            context: PrimitiveDecisionContext,
            *,
            facts: PrimitiveDecisionFacts | None = None,
        ) -> _NonDumpBackendFacts:
            assert facts is None
            calls.append("current_skill")
            calls.append("current_reason")
            common = PrimitiveDecisionFacts.from_context(
                context,
                current_skill_name="return",
                current_switch_reason="dump_to_return_mass_low",
            )
            return _NonDumpBackendFacts(common)

        def decision_facts(
            self,
            context: PrimitiveDecisionContext,
        ) -> PrimitiveDecisionFacts:
            raise AssertionError("dump branch must consume backend facts access")

        def dump_transition_facts(
            self,
            context: PrimitiveDecisionContext,
            *,
            facts: PrimitiveDecisionFacts | None = None,
        ) -> PrimitiveDumpTransitionFacts:
            raise AssertionError("dump branch must consume backend facts access")

    branch = LegacyFSMDumpBranch(
        config=LegacyFSMDumpConfig(dump_skill_name="dump"),
        capabilities=_NonDumpCapabilities(),
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

    assert result is None
    assert calls == ["current_skill", "current_reason"]


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
    branch = LegacyFSMReturnBranch(
        config=LegacyFSMReturnConfig(return_skill_name="return"),
        capabilities=_decision_capabilities(
            current_skill_name=lambda: "return",
            return_transition_status=lambda obs, boundary_event: _return_status(
                next_dig_event=True,
                next_or_seen_dig_event=True,
            ),
        ),
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

    assert result is not None
    assert result.side_effects_applied is False
    assert result.status == "no_change"
    assert result.effects == (MarkReturnNextDigEventSeenEffect(),)


def test_legacy_fsm_return_branch_requested_completion_orders_effects() -> None:
    branch = LegacyFSMReturnBranch(
        config=LegacyFSMReturnConfig(return_skill_name="return"),
        capabilities=_decision_capabilities(
            current_skill_name=lambda: "return",
            return_transition_status=lambda obs, boundary_event: _return_status(
                next_or_seen_dig_event=True,
                entry_close=True,
                start_envelope_ready=True,
                handoff_ready=True,
                completed_transition=True,
            ),
        ),
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
    assert result.side_effects_applied is False
    assert result.status == "skill_switch"
    assert result.effects == (
        CompleteReturnTransitionEffect(),
        SwitchToNextSkillAfterReturnEffect(reason_suffix="next_dig_entry_ready"),
    )


def test_legacy_fsm_return_branch_requested_event_then_completion_order() -> None:
    branch = LegacyFSMReturnBranch(
        config=LegacyFSMReturnConfig(return_skill_name="return"),
        capabilities=_decision_capabilities(
            current_skill_name=lambda: "return",
            return_transition_status=lambda obs, boundary_event: _return_status(
                next_dig_event=True,
                next_or_seen_dig_event=True,
                entry_close=True,
                start_envelope_ready=True,
                handoff_ready=True,
                completed_transition=True,
            ),
        ),
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
        capabilities=_decision_capabilities(
            current_skill_name=lambda: "return",
            return_transition_status=lambda obs, boundary_event: _return_status(),
        ),
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


def test_legacy_fsm_return_branch_refreshes_before_reading_return_status() -> None:
    calls: list[str] = []
    obs: dict[str, Any] = {"qpos": [1.0]}
    boundary_event = object()

    def current_skill_name() -> str:
        calls.append("current_skill")
        return "return"

    def current_switch_reason() -> str:
        calls.append("current_reason")
        return ""

    def refresh(obs_arg: dict[str, Any]) -> None:
        assert obs_arg is obs
        calls.append("refresh_return")

    def return_status(
        obs_arg: dict[str, Any],
        boundary_event_arg: Any | None,
    ) -> ReturnTransitionStatus:
        assert obs_arg is obs
        assert boundary_event_arg is boundary_event
        calls.append("return_status")
        return _return_status(
            next_dig_event=True,
            next_or_seen_dig_event=True,
            entry_close=True,
            start_envelope_ready=True,
            handoff_ready=True,
            completed_transition=True,
        )

    branch = LegacyFSMReturnBranch(
        config=LegacyFSMReturnConfig(return_skill_name="return"),
        capabilities=_decision_capabilities(
            current_skill_name=current_skill_name,
            current_switch_reason=current_switch_reason,
            refresh_return_transition_state=refresh,
            return_transition_status=return_status,
        ),
    )

    result = branch.decide_tick(
        obs=obs,
        boundary_event=boundary_event,
        preparation=PrimitiveTickPreparation(
            boundary_event=boundary_event,
            skill_name_before_decision="return",
            dig_progress_updated=False,
        ),
    )

    assert calls == [
        "current_skill",
        "current_reason",
        "refresh_return",
        "return_status",
    ]
    assert result is not None
    assert result.effects == (
        MarkReturnNextDigEventSeenEffect(),
        CompleteReturnTransitionEffect(),
        SwitchToNextSkillAfterReturnEffect(reason_suffix="next_dig_entry_ready"),
    )


def test_legacy_fsm_return_branch_consumes_backend_facts_view() -> None:
    calls: list[str] = []
    obs: dict[str, Any] = {"qpos": [1.0]}
    boundary_event = object()
    common_facts: PrimitiveDecisionFacts | None = None
    status = _return_status(
        next_dig_event=True,
        next_or_seen_dig_event=True,
        entry_close=True,
        start_envelope_ready=True,
        handoff_ready=True,
        completed_transition=True,
    )

    class _ReturnBackendFacts:
        def __init__(self, common: PrimitiveDecisionFacts) -> None:
            self.common = common

        def return_transition(self) -> PrimitiveReturnTransitionFacts:
            calls.append("return_status")
            return PrimitiveReturnTransitionFacts(common=self.common, status=status)

    class _ReturnFactsCapabilities:
        def backend_facts(
            self,
            context: PrimitiveDecisionContext,
            *,
            facts: PrimitiveDecisionFacts | None = None,
        ) -> _ReturnBackendFacts:
            nonlocal common_facts
            assert facts is None
            assert context.obs is obs
            assert context.boundary_event is boundary_event
            calls.append("current_skill")
            calls.append("current_reason")
            common_facts = PrimitiveDecisionFacts.from_context(
                context,
                current_skill_name="return",
                current_switch_reason="",
            )
            return _ReturnBackendFacts(common_facts)

        def decision_facts(
            self,
            context: PrimitiveDecisionContext,
        ) -> PrimitiveDecisionFacts:
            raise AssertionError("return branch must consume backend facts access")

        def refresh_return_transition_state(
            self,
            context: PrimitiveDecisionContext,
        ) -> None:
            assert context.obs is obs
            calls.append("refresh_return")

        def return_transition_facts(
            self,
            context: PrimitiveDecisionContext,
            *,
            facts: PrimitiveDecisionFacts | None = None,
        ) -> PrimitiveReturnTransitionFacts:
            raise AssertionError("return branch must consume backend facts access")

        def return_transition_status(
            self,
            context: PrimitiveDecisionContext,
        ) -> ReturnTransitionStatus:
            raise AssertionError("return branch must consume return facts view")

    branch = LegacyFSMReturnBranch(
        config=LegacyFSMReturnConfig(return_skill_name="return"),
        capabilities=_ReturnFactsCapabilities(),
    )

    result = branch.decide_tick(
        obs=obs,
        boundary_event=boundary_event,
        preparation=PrimitiveTickPreparation(
            boundary_event=boundary_event,
            skill_name_before_decision="return",
            dig_progress_updated=False,
        ),
    )

    assert calls == [
        "current_skill",
        "current_reason",
        "refresh_return",
        "return_status",
    ]
    assert result is not None
    assert result.effects == (
        MarkReturnNextDigEventSeenEffect(),
        CompleteReturnTransitionEffect(),
        SwitchToNextSkillAfterReturnEffect(reason_suffix="next_dig_entry_ready"),
    )


def test_legacy_fsm_return_branch_requested_ignores_non_return_skill() -> None:
    calls: list[str] = []

    def fail_refresh(obs: dict[str, Any]) -> None:
        calls.append("refresh_return")
        raise AssertionError("non-return skill must not refresh return state")

    def fail_if_called(
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> ReturnTransitionStatus:
        calls.append("return_status")
        raise AssertionError("non-return skill must not request return transition status")

    branch = LegacyFSMReturnBranch(
        config=LegacyFSMReturnConfig(return_skill_name="return"),
        capabilities=_decision_capabilities(
            current_skill_name=lambda: "dig",
            refresh_return_transition_state=fail_refresh,
            return_transition_status=fail_if_called,
        ),
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
    assert calls == []


def test_legacy_fsm_return_branch_latches_next_dig_event_without_switch() -> None:
    obs: dict[str, Any] = {"qpos": [1.0]}
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
        capabilities=_decision_capabilities(
            current_skill_name=lambda: "return",
            return_transition_status=lambda obs, boundary_event: status,
        ),
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

    assert result is not None
    assert result.effects == (MarkReturnNextDigEventSeenEffect(),)


def test_legacy_fsm_return_branch_completes_next_dig_handoff_in_order() -> None:
    obs: dict[str, Any] = {"qpos": [1.0]}
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
        capabilities=_decision_capabilities(
            current_skill_name=lambda: "return",
            return_transition_status=lambda obs, boundary_event: status,
        ),
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

    assert result is not None
    assert result.effects == (
        MarkReturnNextDigEventSeenEffect(),
        CompleteReturnTransitionEffect(),
        SwitchToNextSkillAfterReturnEffect(reason_suffix="next_dig_entry_ready"),
    )


def test_legacy_fsm_return_branch_defers_next_skill_selection_to_applier() -> None:
    obs: dict[str, Any] = {"qpos": [1.0]}
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
        capabilities=_decision_capabilities(
            current_skill_name=lambda: "return",
            return_transition_status=lambda obs, boundary_event: status,
        ),
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

    assert result is not None
    assert result.effects == (
        MarkReturnNextDigEventSeenEffect(),
        CompleteReturnTransitionEffect(),
        SwitchToNextSkillAfterReturnEffect(reason_suffix="next_dig_entry_ready"),
    )


def test_legacy_fsm_return_branch_ignores_non_return_skill() -> None:
    branch = LegacyFSMReturnBranch(
        config=LegacyFSMReturnConfig(return_skill_name="return"),
        capabilities=_decision_capabilities(
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
        ),
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
