from __future__ import annotations

from collections.abc import Callable
from dataclasses import fields
from typing import Any

import numpy as np
import pytest

from testbed.data.operator_first_v2_2 import DIG_CUT_TOKEN_DIM
from testbed.planner.primitive.facts.capabilities import PrimitiveObservationFacts
from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.decision.contracts import (
    CompleteCoverageDigEffect,
    CompleteCoverageDumpEffect,
    CompleteReturnTransitionEffect,
    IncrementDigBadReplanCountEffect,
    IncrementDigExitGuardReplanCountEffect,
    MarkReturnNextDigEventSeenEffect,
    PrimitiveDecisionContractError,
    RejectActiveCoverageCorridorEffect,
    ReplanOrRestartPreDigAlignEffect,
    RequestedPlannerEffect,
    RestartAfterFailedDigEffect,
    RestartDigWithNewCutEffect,
    SetDumpDoneHoldCountEffect,
    SetDumpReadyHoldCountEffect,
    SetDumpStartDepositedMassFromObservationEffect,
    SetReturnOrDirectHandoffEffect,
    SwitchSkillEffect,
    SwitchToNextSkillAfterReturnEffect,
)
from testbed.planner.primitive.effects.requested import (
    PrimitiveRequestedEffectRuntime,
    PrimitiveRequestedEffectRuntimePorts,
    RequestedEffectApplier,
    RequestedEffectApplierPorts,
)
from testbed.planner.primitive.execution.cycle_state import PrimitiveCycleRuntimeState
from testbed.planner.primitive.execution.dig_recovery import (
    PrimitiveDigRecoveryPorts,
    PrimitiveDigRecoveryService,
)
from testbed.planner.primitive.execution.pre_dig_align import (
    PrimitivePreDigAlignRuntimeState,
)
from testbed.planner.primitive.execution.return_state import PrimitiveReturnRuntimeState
from testbed.planner.primitive.execution.state import PrimitiveExecutionRuntimeState
from testbed.planner.primitive.token.state import PrimitiveTokenRuntimeState
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def _ports(
    events: list[str],
    *,
    observation_facts: Callable[[dict[str, Any]], PrimitiveObservationFacts]
    | None = None,
    next_skill_after_return_transition: Callable[[], str] | None = None,
    cycle_state: PrimitiveCycleRuntimeState | None = None,
    return_state: PrimitiveReturnRuntimeState | None = None,
) -> RequestedEffectApplierPorts:
    return RequestedEffectApplierPorts(
        cycle_state=cycle_state or PrimitiveCycleRuntimeState.fresh(),
        return_state=return_state or PrimitiveReturnRuntimeState.fresh(),
        set_skill=lambda skill, reason: events.append(f"skill:{skill}:{reason}"),
        next_skill_after_return_transition=(
            next_skill_after_return_transition or (lambda: "dig")
        ),
        reject_active_coverage_corridor=lambda obs, reason: events.append(
            f"reject:{reason}:{obs['tag']}"
        ),
        restart_after_failed_dig=lambda reason, obs: events.append(
            f"restart:{reason}:{obs['tag']}"
        ),
        restart_dig_with_new_cut=lambda reason: events.append(
            f"restart_new_cut:{reason}"
        ),
        replan_or_restart_pre_dig_align=(
            lambda obs, replan_reason, restart_reason: events.append(
                "pre_dig_replan_or_restart:"
                f"{replan_reason}:{restart_reason}:{obs['tag']}"
            )
        ),
        complete_coverage_dig=lambda obs: events.append(f"coverage_dig:{obs['tag']}"),
        observation_facts=observation_facts
        or (
            lambda obs: PrimitiveObservationFacts.from_obs(
                {
                    **obs,
                    "task_metrics": {
                        **dict(obs.get("task_metrics", {}) or {}),
                        "deposited_mass_in_target_box_kg": 12.5,
                    },
                },
                action_dim=4,
            )
        ),
        complete_coverage_dump=lambda obs, reason: events.append(
            f"coverage_dump:{reason}:{obs['tag']}"
        ),
        set_return_or_direct_handoff=lambda obs, reason: events.append(
            f"return:{reason}:{obs['tag']}"
        ),
    )


def test_requested_effect_ports_use_state_owners_not_storage_callbacks() -> None:
    field_names = {field.name for field in fields(RequestedEffectApplierPorts)}

    assert {"cycle_state", "return_state"} <= field_names
    assert "observation_facts" in field_names
    assert "deposited_mass" not in field_names
    assert "complete_cell_entry_dig" not in field_names
    assert not {
        "mark_return_next_dig_event_seen",
        "complete_return_transition",
        "increment_dig_exit_guard_replan_count",
        "increment_dig_bad_replan_count",
        "set_dump_ready_hold_count",
        "set_dump_start_deposited_mass",
        "set_dump_done_hold_count",
    } & field_names


def test_requested_effect_runtime_composes_applier_from_explicit_ports() -> None:
    events: list[str] = []
    obs = {
        "tag": "current",
        "task_metrics": {"deposited_mass_in_target_box_kg": 12.5},
    }
    cycle_state = PrimitiveCycleRuntimeState.fresh()
    return_state = PrimitiveReturnRuntimeState.fresh()

    class _CoverageEffectRuntime:
        def reject_active_coverage_corridor(self, got_obs, *, reason):
            assert got_obs is obs
            events.append(f"reject:{reason}")

        def complete_coverage_dig(self, got_obs):
            assert got_obs is obs
            events.append("coverage_dig")

        def complete_coverage_dump(self, got_obs, *, reason):
            assert got_obs is obs
            events.append(f"coverage_dump:{reason}")

    class _DigRecoveryService:
        def restart_after_failed_dig(self, reason, got_obs):
            assert got_obs is obs
            events.append(f"restart:{reason}")

        def restart_dig_with_new_cut(self, reason):
            events.append(f"restart_new_cut:{reason}")

        def replan_or_restart_pre_dig_align(
            self,
            got_obs,
            *,
            replan_reason,
            restart_reason,
        ):
            assert got_obs is obs
            events.append(f"pre_dig:{replan_reason}:{restart_reason}")

    class _ReturnHandoffRuntime:
        def apply_direct_handoff(self, got_obs, *, reason):
            assert got_obs is obs
            events.append(f"return:{reason}")

    runtime = PrimitiveRequestedEffectRuntime.from_ports(
        PrimitiveRequestedEffectRuntimePorts(
            cycle_state=cycle_state,
            return_state=return_state,
            set_skill=lambda skill, reason: events.append(
                f"skill:{skill}:{reason}"
            ),
            return_transition_next_skill_name="dig",
            coverage_effect_runtime=_CoverageEffectRuntime(),
            dig_recovery_service=_DigRecoveryService(),
            return_handoff_runtime=_ReturnHandoffRuntime(),
            action_dim=4,
        )
    )

    runtime.apply(
        obs,
        (
            SwitchSkillEffect("carry", "dig_to_carry_loaded"),
            RejectActiveCoverageCorridorEffect("bad_dig_low_payload"),
            RestartAfterFailedDigEffect("bad_dig_low_payload"),
            RestartDigWithNewCutEffect("pre_dig_align_to_dig_surface_guard_replan"),
            ReplanOrRestartPreDigAlignEffect(
                replan_reason="pre_dig_align_replan_to_dig_entry_close",
                restart_reason="pre_dig_align_retry_entry_gap",
            ),
            CompleteCoverageDigEffect(),
            SetDumpStartDepositedMassFromObservationEffect(),
            CompleteCoverageDumpEffect("dump_mass_low"),
            SetReturnOrDirectHandoffEffect("dump_to_return_mass_low"),
        ),
    )

    assert events == [
        "skill:carry:dig_to_carry_loaded",
        "reject:bad_dig_low_payload",
        "restart:bad_dig_low_payload",
        "restart_new_cut:pre_dig_align_to_dig_surface_guard_replan",
        "pre_dig:pre_dig_align_replan_to_dig_entry_close:pre_dig_align_retry_entry_gap",
        "coverage_dig",
        "coverage_dump:dump_mass_low",
        "return:dump_to_return_mass_low",
    ]
    assert cycle_state.dump_start_deposited_mass_kg == 12.5


def test_requested_effect_runtime_uses_return_transition_next_skill_selector() -> None:
    events: list[str] = []

    class _UnusedCoverageEffectRuntime:
        def reject_active_coverage_corridor(self, got_obs, *, reason):
            raise AssertionError("return completion must not reject coverage")

        def complete_coverage_dig(self, got_obs):
            raise AssertionError("return completion must not complete dig")

        def complete_coverage_dump(self, got_obs, *, reason):
            raise AssertionError("return completion must not complete dump")

    class _UnusedDigRecoveryService:
        def restart_after_failed_dig(self, reason, got_obs):
            raise AssertionError("return completion must not restart dig")

        def restart_dig_with_new_cut(self, reason):
            raise AssertionError("return completion must not restart dig")

        def replan_or_restart_pre_dig_align(
            self,
            got_obs,
            *,
            replan_reason,
            restart_reason,
        ):
            raise AssertionError("return completion must not restart pre-dig")

    class _UnusedReturnHandoffRuntime:
        def apply_direct_handoff(self, got_obs, *, reason):
            raise AssertionError("return completion must not direct-handoff")

    runtime = PrimitiveRequestedEffectRuntime.from_ports(
        PrimitiveRequestedEffectRuntimePorts(
            cycle_state=PrimitiveCycleRuntimeState.fresh(),
            return_state=PrimitiveReturnRuntimeState.fresh(),
            set_skill=lambda skill, reason: events.append(
                f"skill:{skill}:{reason}"
            ),
            return_transition_next_skill_name="dig",
            return_transition_next_skill=lambda: "pre_dig_align",
            coverage_effect_runtime=_UnusedCoverageEffectRuntime(),
            dig_recovery_service=_UnusedDigRecoveryService(),
            return_handoff_runtime=_UnusedReturnHandoffRuntime(),
            action_dim=4,
        )
    )

    runtime.apply(
        {"tag": "current"},
        (SwitchToNextSkillAfterReturnEffect(reason_suffix="start_envelope_ready"),),
    )

    assert events == [
        "skill:pre_dig_align:return_to_pre_dig_align_start_envelope_ready"
    ]


def test_requested_effect_runtime_replan_pre_dig_align_success_leaves_live_dig_state() -> None:
    obs = {"tag": "current"}
    events: list[str] = []
    execution_state = PrimitiveExecutionRuntimeState.fresh(
        initial_skill_name="pre_dig_align",
    )
    cycle_state = PrimitiveCycleRuntimeState.fresh()
    return_state = PrimitiveReturnRuntimeState.fresh()
    coverage_state = CoverageRuntimeState()
    token_state = PrimitiveTokenRuntimeState.fresh()
    pre_dig_align_state = PrimitivePreDigAlignRuntimeState.fresh(action_dim=4)

    def _set_skill(skill_name: str, reason: str) -> None:
        events.append(f"set:{skill_name}:{reason}")
        execution_state.set_skill_name(skill_name)
        execution_state.set_switch_reason(reason)

    dig_recovery = PrimitiveDigRecoveryService.from_ports(
        PrimitiveDigRecoveryPorts(
            execution_state=execution_state,
            cycle_state=cycle_state,
            return_state=return_state,
            coverage_state=coverage_state,
            token_state=token_state,
            pre_dig_align_state=pre_dig_align_state,
            reset_active_policy=lambda: events.append("reset"),
            invalidate_pending_dig_cut_plan=lambda: events.append("invalidate"),
            clear_dig_cut_plan=lambda: events.append("clear"),
            build_operator_prior_coverage_dig_cut_tokens=lambda got_obs: (
                np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float32),
                {"x": 1.0},
                "operator_prior_coverage",
                "fallback",
            ),
            raw_fields_in_prior_range=lambda raw_fields: True,
            pre_dig_align_entry_error=lambda got_obs: 0.02,
            pre_dig_align_timeout_can_handoff=lambda got_obs: True,
            set_skill=_set_skill,
            record_coverage_decision_event=lambda *args, **kwargs: None,
            request_coverage_terminal_stop=lambda *args, **kwargs: None,
            observation_facts=lambda got_obs: PrimitiveObservationFacts.from_obs(
                got_obs,
                action_dim=4,
            ),
            should_pre_dig_align_before_dig=lambda: False,
            should_pre_dig_align_after_failed_dig=lambda: False,
            dig_cut_planner_mode=lambda: "operator_prior_coverage",
            dig_failed_replan_next_skill=lambda: "dig",
            pre_dig_align_skill_name="pre_dig_align",
        )
    )

    class _UnusedCoverageEffectRuntime:
        def reject_active_coverage_corridor(self, got_obs, *, reason):
            raise AssertionError("replan effect must not reject coverage")

        def complete_coverage_dig(self, got_obs):
            raise AssertionError("replan effect must not complete dig")

        def complete_coverage_dump(self, got_obs, *, reason):
            raise AssertionError("replan effect must not complete dump")

    class _UnusedReturnHandoffRuntime:
        def apply_direct_handoff(self, got_obs, *, reason):
            raise AssertionError("replan effect must not direct-handoff")

    runtime = PrimitiveRequestedEffectRuntime.from_ports(
        PrimitiveRequestedEffectRuntimePorts(
            cycle_state=cycle_state,
            return_state=return_state,
            set_skill=_set_skill,
            return_transition_next_skill_name="dig",
            coverage_effect_runtime=_UnusedCoverageEffectRuntime(),
            dig_recovery_service=dig_recovery,
            return_handoff_runtime=_UnusedReturnHandoffRuntime(),
            action_dim=4,
        )
    )

    runtime.apply(
        obs,
        (
            ReplanOrRestartPreDigAlignEffect(
                replan_reason="pre_dig_align_replan_to_dig_entry_close",
                restart_reason="pre_dig_align_retry_entry_gap",
            ),
        ),
    )

    assert events == [
        "invalidate",
        "clear",
        "set:dig:pre_dig_align_replan_to_dig_entry_close",
    ]
    assert execution_state.skill_name == "dig"
    assert execution_state.switch_reason == "pre_dig_align_replan_to_dig_entry_close"
    assert pre_dig_align_state.completed_count == 1


def test_policy_no_longer_exposes_requested_effect_private_wrappers() -> None:
    old_applier_name = "_requested_effect_" + "applier"
    assert old_applier_name not in PrimitivePlannerACTPolicy.__dict__
    assert f"{old_applier_name}_ports" not in PrimitivePlannerACTPolicy.__dict__


def test_requested_effect_applier_applies_mixed_effects_in_order() -> None:
    events: list[str] = []
    obs = {"tag": "current"}
    cycle_state = PrimitiveCycleRuntimeState.fresh()
    return_state = PrimitiveReturnRuntimeState.fresh()

    def next_skill_after_return() -> str:
        events.append(f"next_skill:{cycle_state.cycle_index}")
        return "dig"

    ports = _ports(
        events,
        observation_facts=lambda got_obs: PrimitiveObservationFacts.from_obs(
            {
                **got_obs,
                "task_metrics": {
                    "deposited_mass_in_target_box_kg": 17.25,
                },
            },
            action_dim=4,
        ),
        next_skill_after_return_transition=next_skill_after_return,
        cycle_state=cycle_state,
        return_state=return_state,
    )
    applier = RequestedEffectApplier(ports=ports)

    applier.apply(
        obs,
        (
            SwitchSkillEffect(target_skill_name="carry", switch_reason="bootstrap_to_carry"),
            MarkReturnNextDigEventSeenEffect(),
            CompleteReturnTransitionEffect(),
            SwitchToNextSkillAfterReturnEffect(reason_suffix="next_dig_entry_ready"),
            IncrementDigExitGuardReplanCountEffect(),
            IncrementDigBadReplanCountEffect(),
            RejectActiveCoverageCorridorEffect(reason="bad_dig_low_payload"),
            RestartAfterFailedDigEffect(reason="bad_dig_low_payload"),
            RestartDigWithNewCutEffect(
                reason="pre_dig_align_to_dig_surface_guard_replan"
            ),
            ReplanOrRestartPreDigAlignEffect(
                replan_reason="pre_dig_align_replan_to_dig_entry_close",
                restart_reason="pre_dig_align_retry_entry_gap",
            ),
            CompleteCoverageDigEffect(),
            SetDumpReadyHoldCountEffect(value=4),
            SetDumpStartDepositedMassFromObservationEffect(),
            SetDumpDoneHoldCountEffect(value=2),
            CompleteCoverageDumpEffect(reason="dump_mass_low"),
            SetReturnOrDirectHandoffEffect(reason="dump_to_return_mass_low"),
        ),
    )

    assert events == [
        "skill:carry:bootstrap_to_carry",
        "next_skill:1",
        "skill:dig:return_to_dig_next_dig_entry_ready",
        "reject:bad_dig_low_payload:current",
        "restart:bad_dig_low_payload:current",
        "restart_new_cut:pre_dig_align_to_dig_surface_guard_replan",
        (
            "pre_dig_replan_or_restart:"
            "pre_dig_align_replan_to_dig_entry_close:"
            "pre_dig_align_retry_entry_gap:current"
        ),
        "coverage_dig:current",
        "coverage_dump:dump_mass_low:current",
        "return:dump_to_return_mass_low:current",
    ]
    assert return_state.return_next_dig_event_seen is True
    assert cycle_state.completed_transition_count == 1
    assert cycle_state.cycle_index == 1
    assert cycle_state.dig_exit_guard_replan_count == 1
    assert cycle_state.dig_bad_replan_count == 1
    assert cycle_state.dump_ready_hold_count == 4
    assert cycle_state.dump_start_deposited_mass_kg == 17.25
    assert cycle_state.dump_done_hold_count == 2


def test_requested_effect_applier_reads_deposited_mass_from_current_obs() -> None:
    events: list[str] = []
    first_obs = {"tag": "first"}
    second_obs = {"tag": "second"}

    def observation_facts(obs: dict[str, Any]) -> PrimitiveObservationFacts:
        events.append(f"read:{obs['tag']}")
        return PrimitiveObservationFacts.from_obs(
            {
                **obs,
                "task_metrics": {
                    "deposited_mass_in_target_box_kg": (
                        3.0 if obs is first_obs else 8.0
                    ),
                },
            },
            action_dim=4,
        )

    applier = RequestedEffectApplier(
        ports=_ports(events, observation_facts=observation_facts)
    )

    applier.apply(first_obs, (SetDumpStartDepositedMassFromObservationEffect(),))
    assert applier.ports.cycle_state.dump_start_deposited_mass_kg == 3.0
    applier.apply(second_obs, (SetDumpStartDepositedMassFromObservationEffect(),))

    assert events == ["read:first", "read:second"]
    assert applier.ports.cycle_state.dump_start_deposited_mass_kg == 8.0


@pytest.mark.parametrize(
    ("effect", "message"),
    [
        (
            SwitchSkillEffect(target_skill_name="", switch_reason="reason"),
            "SwitchSkill effect requires non-empty skill and reason",
        ),
        (
            SwitchSkillEffect(target_skill_name="dig", switch_reason=""),
            "SwitchSkill effect requires non-empty skill and reason",
        ),
        (
            SwitchToNextSkillAfterReturnEffect(reason_suffix=""),
            "SwitchToNextSkillAfterReturn effect requires non-empty reason suffix",
        ),
        (
            RejectActiveCoverageCorridorEffect(reason=""),
            "RejectActiveCoverageCorridor effect requires non-empty reason",
        ),
        (
            RestartAfterFailedDigEffect(reason=""),
            "RestartAfterFailedDig effect requires non-empty reason",
        ),
        (
            RestartDigWithNewCutEffect(reason=""),
            "RestartDigWithNewCut effect requires non-empty reason",
        ),
        (
            ReplanOrRestartPreDigAlignEffect(
                replan_reason="",
                restart_reason="pre_dig_align_retry_entry_gap",
            ),
            "ReplanOrRestartPreDigAlign effect requires non-empty reasons",
        ),
        (
            ReplanOrRestartPreDigAlignEffect(
                replan_reason="pre_dig_align_replan_to_dig_entry_close",
                restart_reason="",
            ),
            "ReplanOrRestartPreDigAlign effect requires non-empty reasons",
        ),
        (
            CompleteCoverageDumpEffect(reason=""),
            "CompleteCoverageDump effect requires non-empty reason",
        ),
        (
            SetReturnOrDirectHandoffEffect(reason=""),
            "SetReturnOrDirectHandoff effect requires non-empty reason",
        ),
    ],
)
def test_requested_effect_applier_rejects_empty_contract_fields(
    effect: RequestedPlannerEffect,
    message: str,
) -> None:
    applier = RequestedEffectApplier(ports=_ports([]))

    with pytest.raises(PrimitiveDecisionContractError, match=message):
        applier.apply({"tag": "current"}, (effect,))


def test_requested_effect_applier_rejects_unknown_requested_effect() -> None:
    applier = RequestedEffectApplier(ports=_ports([]))

    with pytest.raises(PrimitiveDecisionContractError) as exc_info:
        applier.apply(
            {"tag": "current"},
            (
                RequestedPlannerEffect(
                    effect_type="record_decision_trace",
                    reason="future_backend_probe",
                ),
            ),
        )

    message = str(exc_info.value)
    assert "real planner" in message
    assert "requested-effect application" in message
    assert "only supports SwitchSkill" in message
