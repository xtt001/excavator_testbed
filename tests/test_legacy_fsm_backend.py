from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from testbed.data.schema import (
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
    ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_DUMP_CLEARANCE_OK_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
    ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
)
from testbed.planner.bootstrap import (
    BootstrapConfig,
    BootstrapService,
    BootstrapTransitionDecision,
)
from testbed.planner.dig_lifecycle import (
    DigLifecycleGateService,
    DigTransitionRuntimeOutcome,
    DigTransitionRuntimeProjection,
)
from testbed.planner.dig_start_alignment_outcome import PreDigAlignOutcome
from testbed.planner.dump_lifecycle import (
    CarryTransitionRuntimeState,
    DumpLifecycleGateService,
    DumpLifecycleOutcome,
    DumpTransitionRuntimeState,
    build_carry_transition_runtime_request,
    build_dump_transition_runtime_request,
)
from testbed.planner.runtime import (
    LegacyFsmBackendPorts,
    LegacyFsmBootstrapPorts,
    LegacyFsmBoundaryProfilePorts,
    LegacyFsmDigTransitionPorts,
    LegacyFsmDumpLifecyclePorts,
    LegacyFsmPreDigAlignmentPorts,
    LegacyFsmSkillNames,
    PlannerBackendPorts,
    PlannerBlackboard,
    PlannerRuntimeEffect,
    PlannerTickContext,
    PlannerTickResult,
)
from testbed.planner.runtime.legacy_fsm import (
    APPLY_BOOTSTRAP_TRANSITION_DECISION_EFFECT,
    APPLY_CARRY_TRANSITION_RUNTIME_EFFECT,
    APPLY_DUMP_TRANSITION_RUNTIME_EFFECT,
    APPLY_PRE_DIG_ALIGN_OUTCOME_EFFECT,
    LEGACY_FSM_TRANSITION_EFFECT,
    LegacyStateMachineBackend,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def _skill_names() -> LegacyFsmSkillNames:
    return LegacyFsmSkillNames(
        bootstrap="bootstrap",
        pre_dig_align="pre_dig_align",
        dig="dig",
        carry="carry",
        dump="dump",
        return_skill="return",
    )


def _ports(**legacy_ports: object) -> PlannerBackendPorts:
    return PlannerBackendPorts(
        legacy_fsm=LegacyFsmBackendPorts(
            skill_names=_skill_names(),
            **legacy_ports,
        )
    )


def _boundary_ports(
    semantic_boundary_profile_active=lambda: False,
) -> LegacyFsmBoundaryProfilePorts:
    return LegacyFsmBoundaryProfilePorts(
        semantic_boundary_profile_active=semantic_boundary_profile_active,
    )


def _bootstrap_ports(
    *,
    should_end,
    service=None,
    should_pre_dig_align_before_dig=lambda: False,
    config=lambda: BootstrapConfig(
        action_dim=4,
        end_mode="first_qualified_dig_start",
        end_min_bucket_mass_kg=300.0,
        end_min_distance_to_dig_area_m=0.25,
    ),
) -> LegacyFsmBootstrapPorts:
    return LegacyFsmBootstrapPorts(
        service=BootstrapService() if service is None else service,
        should_end=should_end,
        should_pre_dig_align_before_dig=should_pre_dig_align_before_dig,
        config=config,
    )


def test_legacy_fsm_backend_returns_transition_effect_contract() -> None:
    boundary_event = _FakeBoundaryEvent(dig_complete=True)
    context = PlannerTickContext(
        obs={"step": 3},
        boundary_event=boundary_event,
        blackboard=PlannerBlackboard(current_skill="dig"),
    )

    result = LegacyStateMachineBackend().tick(context)

    assert result.node_path == ("legacy_fsm", "transition", "dig")
    assert result.status == "running"
    assert result.reason == ""
    assert len(result.effects) == 1
    effect = result.effects[0]
    assert effect.effect_type == LEGACY_FSM_TRANSITION_EFFECT
    assert dict(effect.payload["obs"]) == {"step": 3}
    assert effect.payload["boundary_event"] is boundary_event
    assert dict(result.diagnostics) == {"active_skill": "dig"}


def test_legacy_fsm_backend_without_bootstrap_skill_name_uses_generic_effect() -> None:
    context = PlannerTickContext(blackboard=PlannerBlackboard(current_skill=""))

    result = LegacyStateMachineBackend().tick(context)

    assert result.node_path == ("legacy_fsm", "transition", "")
    assert len(result.effects) == 1
    assert result.effects[0].effect_type == LEGACY_FSM_TRANSITION_EFFECT


def test_legacy_fsm_backend_bootstrap_running_returns_no_effects() -> None:
    boundary_event = _FakeBoundaryEvent(qualified_dig_start=False)
    calls: list[tuple[dict[str, Any], object]] = []

    def should_end_bootstrap(*, obs: dict, boundary_event: Any | None) -> bool:
        calls.append((dict(obs), boundary_event))
        return False

    result = LegacyStateMachineBackend().tick(
        PlannerTickContext(
            obs={"step": 11},
            boundary_event=boundary_event,
            blackboard=PlannerBlackboard(current_skill="bootstrap"),
            ports=_ports(
                bootstrap_transition=_bootstrap_ports(
                    should_end=should_end_bootstrap,
                ),
            ),
        )
    )

    assert result.node_path == ("legacy_fsm", "transition", "bootstrap")
    assert result.status == "running"
    assert result.reason == ""
    assert result.effects == ()
    assert calls == [({"step": 11}, boundary_event)]
    assert dict(result.diagnostics) == {"active_skill": "bootstrap"}


def test_legacy_fsm_backend_bootstrap_end_returns_apply_decision_effect() -> None:
    boundary_event = _FakeBoundaryEvent(qualified_dig_start=True)
    bootstrap_service = BootstrapService()

    result = LegacyStateMachineBackend().tick(
        PlannerTickContext(
            obs={"step": 12},
            boundary_event=boundary_event,
            blackboard=PlannerBlackboard(current_skill="bootstrap"),
            ports=_ports(
                bootstrap_transition=_bootstrap_ports(
                    service=bootstrap_service,
                    should_end=lambda *, obs, boundary_event: True,
                    should_pre_dig_align_before_dig=lambda: True,
                    config=lambda: BootstrapConfig(
                        action_dim=4,
                        end_mode="first_qualified_dig_start",
                        end_min_bucket_mass_kg=300.0,
                        end_min_distance_to_dig_area_m=0.25,
                    ),
                ),
            ),
        )
    )

    assert result.node_path == ("legacy_fsm", "transition", "bootstrap")
    assert result.status == "running"
    assert len(result.effects) == 1
    effect = result.effects[0]
    assert effect.effect_type == APPLY_BOOTSTRAP_TRANSITION_DECISION_EFFECT
    decision = effect.payload["decision"]
    assert decision == BootstrapTransitionDecision(
        next_skill="pre_dig_align",
        switch_reason="bootstrap_to_pre_dig_align",
    )
    assert dict(result.diagnostics) == {
        "active_skill": "bootstrap",
        "next_skill": "pre_dig_align",
        "switch_reason": "bootstrap_to_pre_dig_align",
    }


def test_legacy_fsm_backend_pre_dig_align_returns_apply_outcome_effect() -> None:
    outcome = PreDigAlignOutcome(
        action="ready",
        switch_reason="pre_dig_align_to_dig_ready",
    )
    calls: list[dict[str, Any]] = []

    def pre_dig_align_outcome(obs: dict) -> PreDigAlignOutcome:
        calls.append(dict(obs))
        return outcome

    result = LegacyStateMachineBackend().tick(
        PlannerTickContext(
            obs={"step": 13},
            blackboard=PlannerBlackboard(current_skill="pre_dig_align"),
            ports=_ports(
                pre_dig_alignment=LegacyFsmPreDigAlignmentPorts(
                    compute_outcome=pre_dig_align_outcome,
                ),
            ),
        )
    )

    assert result.node_path == ("legacy_fsm", "transition", "pre_dig_align")
    assert result.status == "running"
    assert result.reason == "pre_dig_align_to_dig_ready"
    assert len(result.effects) == 1
    effect = result.effects[0]
    assert effect.effect_type == APPLY_PRE_DIG_ALIGN_OUTCOME_EFFECT
    assert effect.payload["outcome"] is outcome
    assert dict(effect.payload["obs"]) == {"step": 13}
    assert calls == [{"step": 13}]
    assert dict(result.diagnostics) == {
        "active_skill": "pre_dig_align",
        "action": "ready",
        "switch_reason": "pre_dig_align_to_dig_ready",
    }


def test_legacy_fsm_backend_dig_exit_guard_skips_later_gates() -> None:
    calls: list[str] = []

    def exit_guard_ready(_obs: dict) -> bool:
        calls.append("exit_guard")
        return True

    def fail_later_gate(*_args: Any, **_kwargs: Any) -> bool:
        raise AssertionError("later dig gates must not be checked after exit guard")

    result = LegacyStateMachineBackend().tick(
        PlannerTickContext(
            obs={"step": 16},
            blackboard=PlannerBlackboard(current_skill="dig"),
            ports=_ports(
                dig_transition=LegacyFsmDigTransitionPorts(
                    lifecycle_gate=DigLifecycleGateService(),
                    exit_guard_ready=exit_guard_ready,
                    bad_replan_ready=fail_later_gate,
                    complete_boundary_low_payload=fail_later_gate,
                    dig_to_carry_ready=fail_later_gate,
                    dig_to_carry_reason=lambda: "",
                ),
            ),
        )
    )

    assert calls == ["exit_guard"]
    projection = result.effects[0].payload["projection"]
    assert projection.outcome == DigTransitionRuntimeOutcome(
        action="failed_dig",
        counter="exit_guard_replan",
        failed_dig_reason="exit_overshoot_low_payload",
        coverage_reject_reason="exit_overshoot_low_payload",
    )
    assert projection.exit_guard_replan_count_increment == 1
    assert projection.bad_replan_count_increment == 0


def test_legacy_fsm_backend_carry_returns_apply_runtime_effect() -> None:
    calls: list[str] = []

    def carry_release_safety_done(obs: dict) -> bool:
        calls.append(f"release_safety:{obs['step']}")
        return False

    def dump_ready(obs: dict) -> bool:
        calls.append(f"dump_ready:{obs['step']}")
        return True

    result = LegacyStateMachineBackend().tick(
        PlannerTickContext(
            obs={"step": 18},
            boundary_event=None,
            blackboard=PlannerBlackboard(
                current_skill="carry",
                dump_ready_hold_count=1,
            ),
            ports=_ports(
                dump_lifecycle=LegacyFsmDumpLifecyclePorts(
                    lifecycle_gate=DumpLifecycleGateService(),
                    build_carry_transition_runtime_request=(
                        build_carry_transition_runtime_request
                    ),
                    build_dump_transition_runtime_request=(
                        build_dump_transition_runtime_request
                    ),
                    carry_release_safety_done=carry_release_safety_done,
                    dump_ready_hold_steps=lambda: 2,
                    dump_done_hold_steps=lambda: 1,
                    dump_done_use_boundary_event=lambda: True,
                    dump_ready=dump_ready,
                    dump_done=lambda obs: False,
                ),
                boundary_profile=_boundary_ports(),
            ),
        )
    )

    assert result.node_path == ("legacy_fsm", "transition", "carry")
    assert result.status == "running"
    assert result.reason == "carry_to_dump_target_ready"
    assert calls == ["release_safety:18", "dump_ready:18"]
    assert len(result.effects) == 1
    effect = result.effects[0]
    assert effect.effect_type == APPLY_CARRY_TRANSITION_RUNTIME_EFFECT
    assert dict(effect.payload["obs"]) == {"step": 18}
    assert effect.payload["runtime"] == CarryTransitionRuntimeState(
        dump_ready_hold_count=2,
        outcome=DumpLifecycleOutcome(
            action="dump",
            switch_reason="carry_to_dump_target_ready",
        ),
    )
    assert dict(result.diagnostics) == {
        "active_skill": "carry",
        "action": "dump",
        "switch_reason": "carry_to_dump_target_ready",
    }


def test_legacy_fsm_backend_carry_boundary_event_skips_dump_ready_gate() -> None:
    def dump_ready(_obs: dict) -> bool:
        raise AssertionError("dump_ready must not run after dump boundary event")

    result = LegacyStateMachineBackend().tick(
        PlannerTickContext(
            obs={"step": 19},
            boundary_event=_FakeBoundaryEvent(dump_committed_start=True),
            blackboard=PlannerBlackboard(
                current_skill="carry",
                dump_ready_hold_count=0,
            ),
            ports=_ports(
                dump_lifecycle=LegacyFsmDumpLifecyclePorts(
                    lifecycle_gate=DumpLifecycleGateService(),
                    build_carry_transition_runtime_request=(
                        build_carry_transition_runtime_request
                    ),
                    build_dump_transition_runtime_request=(
                        build_dump_transition_runtime_request
                    ),
                    carry_release_safety_done=lambda obs: False,
                    dump_ready_hold_steps=lambda: 3,
                    dump_done_hold_steps=lambda: 1,
                    dump_done_use_boundary_event=lambda: True,
                    dump_ready=dump_ready,
                    dump_done=lambda obs: False,
                ),
                boundary_profile=_boundary_ports(),
            ),
        )
    )

    assert result.reason == "carry_to_dump_dump_committed_boundary"
    runtime = result.effects[0].payload["runtime"]
    assert runtime == CarryTransitionRuntimeState(
        dump_ready_hold_count=3,
        outcome=DumpLifecycleOutcome(
            action="dump",
            switch_reason="carry_to_dump_dump_committed_boundary",
        ),
    )


def test_legacy_fsm_backend_dump_returns_apply_runtime_effect() -> None:
    calls: list[str] = []

    def dump_done(obs: dict) -> bool:
        calls.append(f"dump_done:{obs['step']}")
        return True

    result = LegacyStateMachineBackend().tick(
        PlannerTickContext(
            obs={"step": 21},
            boundary_event=None,
            blackboard=PlannerBlackboard(
                current_skill="dump",
                dump_done_hold_count=1,
            ),
            ports=_ports(
                dump_lifecycle=LegacyFsmDumpLifecyclePorts(
                    lifecycle_gate=DumpLifecycleGateService(),
                    build_carry_transition_runtime_request=(
                        build_carry_transition_runtime_request
                    ),
                    build_dump_transition_runtime_request=(
                        build_dump_transition_runtime_request
                    ),
                    carry_release_safety_done=lambda obs: True,
                    dump_ready_hold_steps=lambda: 1,
                    dump_done_hold_steps=lambda: 2,
                    dump_done_use_boundary_event=lambda: True,
                    dump_ready=lambda obs: False,
                    dump_done=dump_done,
                ),
                boundary_profile=_boundary_ports(),
            ),
        )
    )

    assert result.node_path == ("legacy_fsm", "transition", "dump")
    assert result.status == "running"
    assert result.reason == "dump_to_return_mass_low"
    assert calls == ["dump_done:21"]
    assert len(result.effects) == 1
    effect = result.effects[0]
    assert effect.effect_type == APPLY_DUMP_TRANSITION_RUNTIME_EFFECT
    assert dict(effect.payload["obs"]) == {"step": 21}
    assert effect.payload["runtime"] == DumpTransitionRuntimeState(
        dump_done_hold_count=2,
        outcome=DumpLifecycleOutcome(
            action="return",
            switch_reason="dump_to_return_mass_low",
            coverage_reason="dump_mass_low",
        ),
    )
    assert dict(result.diagnostics) == {
        "active_skill": "dump",
        "action": "return",
        "switch_reason": "dump_to_return_mass_low",
    }


def test_legacy_fsm_backend_dump_complete_event_skips_dump_done_gate() -> None:
    def dump_done(_obs: dict) -> bool:
        raise AssertionError("dump_done must not run after dump complete event")

    result = LegacyStateMachineBackend().tick(
        PlannerTickContext(
            obs={"step": 22},
            boundary_event=_FakeBoundaryEvent(dump_complete=True),
            blackboard=PlannerBlackboard(
                current_skill="dump",
                dump_done_hold_count=1,
            ),
            ports=_ports(
                dump_lifecycle=LegacyFsmDumpLifecyclePorts(
                    lifecycle_gate=DumpLifecycleGateService(),
                    build_carry_transition_runtime_request=(
                        build_carry_transition_runtime_request
                    ),
                    build_dump_transition_runtime_request=(
                        build_dump_transition_runtime_request
                    ),
                    carry_release_safety_done=lambda obs: True,
                    dump_ready_hold_steps=lambda: 1,
                    dump_done_hold_steps=lambda: 3,
                    dump_done_use_boundary_event=lambda: True,
                    dump_ready=lambda obs: False,
                    dump_done=dump_done,
                ),
                boundary_profile=_boundary_ports(),
            ),
        )
    )

    assert result.reason == "dump_to_return_dump_complete_boundary"
    runtime = result.effects[0].payload["runtime"]
    assert runtime == DumpTransitionRuntimeState(
        dump_done_hold_count=1,
        outcome=DumpLifecycleOutcome(
            action="return",
            switch_reason="dump_to_return_dump_complete_boundary",
            coverage_reason="dump_complete_boundary",
        ),
    )


def test_policy_maybe_switch_skill_applies_legacy_backend_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy._skill_name = "carry"
    boundary_event = _FakeBoundaryEvent(dump_committed_start=True)
    seen_contexts: list[PlannerTickContext] = []
    calls: list[tuple[dict[str, Any], object]] = []

    class Backend:
        def tick(self, context: PlannerTickContext):
            seen_contexts.append(context)
            return type(
                "_Result",
                (),
                {
                    "effects": (
                        PlannerRuntimeEffect(
                            LEGACY_FSM_TRANSITION_EFFECT,
                            {
                                "obs": context.obs,
                                "boundary_event": context.boundary_event,
                            },
                        ),
                    )
                },
            )()

    policy._legacy_fsm_backend = Backend()
    monkeypatch.setattr(
        policy,
        "_run_legacy_fsm_transition",
        lambda *, obs, boundary_event: calls.append((dict(obs), boundary_event)),
    )

    policy._maybe_switch_skill(obs={"step": 7}, boundary_event=boundary_event)

    assert len(seen_contexts) == 1
    assert dict(seen_contexts[0].obs) == {"step": 7}
    assert seen_contexts[0].boundary_event is boundary_event
    assert seen_contexts[0].blackboard == PlannerBlackboard(
        current_skill="carry",
        switch_reason=policy._switch_reason,
        cycle_index=policy._cycle_index,
        completed_transition_count=policy._completed_transition_count,
        transition_timeout_count=policy._transition_timeout_count,
        return_step_count=policy._return_step_count,
        return_next_dig_event_seen=policy._return_next_dig_event_seen,
        dump_ready_hold_count=policy._dump_ready_hold_count,
        dump_done_hold_count=policy._dump_done_hold_count,
    )
    assert isinstance(seen_contexts[0].ports.legacy_fsm, LegacyFsmBackendPorts)
    assert not hasattr(seen_contexts[0], "services")
    assert calls == [({"step": 7}, boundary_event)]


def test_policy_lifecycle_private_fields_are_blackboard_shims() -> None:
    policy = _make_policy()
    policy._planner_blackboard = PlannerBlackboard(
        current_skill="carry",
        switch_reason="from_blackboard",
        cycle_index=4,
        completed_transition_count=3,
        transition_timeout_count=2,
        return_step_count=6,
        return_next_dig_event_seen=True,
        dump_ready_hold_count=7,
        dump_done_hold_count=8,
    )

    assert policy._skill_name == "carry"
    assert policy._switch_reason == "from_blackboard"
    assert policy._cycle_index == 4
    assert policy._completed_transition_count == 3
    assert policy._transition_timeout_count == 2
    assert policy._return_step_count == 6
    assert policy._return_next_dig_event_seen is True
    assert policy._dump_ready_hold_count == 7
    assert policy._dump_done_hold_count == 8

    policy._skill_name = "return"
    policy._switch_reason = "unit_reason"
    policy._cycle_index = np.int64(7)
    policy._completed_transition_count = np.int64(5)
    policy._transition_timeout_count = np.int64(6)
    policy._return_step_count = np.int64(9)
    policy._return_next_dig_event_seen = False
    policy._dump_ready_hold_count = np.int64(10)
    policy._dump_done_hold_count = np.int64(11)

    assert policy._planner_blackboard == PlannerBlackboard(
        current_skill="return",
        switch_reason="unit_reason",
        cycle_index=7,
        completed_transition_count=5,
        transition_timeout_count=6,
        return_step_count=9,
        return_next_dig_event_seen=False,
        dump_ready_hold_count=10,
        dump_done_hold_count=11,
    )


def test_policy_tick_context_uses_canonical_planner_blackboard() -> None:
    policy = _make_policy()
    policy._planner_blackboard = PlannerBlackboard(
        current_skill="dump",
        switch_reason="unit_reason",
        cycle_index=8,
        completed_transition_count=3,
        transition_timeout_count=1,
        return_step_count=4,
        return_next_dig_event_seen=True,
        dump_ready_hold_count=5,
        dump_done_hold_count=6,
    )

    context = policy._legacy_fsm_tick_context(
        obs={"step": 10},
        boundary_event=_FakeBoundaryEvent(dump_complete=True),
    )

    assert context.blackboard is policy._planner_blackboard
    assert context.blackboard.current_skill == "dump"
    assert context.blackboard.switch_reason == "unit_reason"
    assert context.blackboard.return_step_count == 4
    assert context.blackboard.return_next_dig_event_seen is True
    assert context.blackboard.dump_ready_hold_count == 5
    assert context.blackboard.dump_done_hold_count == 6
    assert context.coverage_state is policy.coverage_service.state
    assert isinstance(context.ports.legacy_fsm, LegacyFsmBackendPorts)
    assert context.ports.legacy_fsm.dig_transition is not None
    assert context.ports.legacy_fsm.return_transition is not None
    assert not hasattr(context, "services")


def test_policy_reset_initializes_planner_blackboard_lifecycle_state() -> None:
    policy = _make_policy()
    policy._planner_blackboard = PlannerBlackboard(
        current_skill="return",
        switch_reason="stale",
        cycle_index=99,
        completed_transition_count=88,
        transition_timeout_count=77,
        return_step_count=66,
        return_next_dig_event_seen=True,
        dump_ready_hold_count=55,
        dump_done_hold_count=44,
    )

    policy.reset()

    assert policy._planner_blackboard == PlannerBlackboard(
        current_skill=policy._skill_name,
        switch_reason="reset",
        cycle_index=0,
        completed_transition_count=0,
        transition_timeout_count=0,
        return_step_count=0,
        return_next_dig_event_seen=False,
        dump_ready_hold_count=0,
        dump_done_hold_count=0,
    )


def test_policy_maybe_switch_skill_applies_bootstrap_backend_decision_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy(
        bootstrap_policy=_ConstantPolicy(4.0),
        bootstrap_end_mode="first_qualified_dig_start",
    )
    policy._skill_name = "bootstrap"
    boundary_event = _FakeBoundaryEvent(qualified_dig_start=True)

    def fail_fallback(*, obs: dict, boundary_event: Any | None) -> None:
        raise AssertionError("bootstrap should be handled by backend decision effect")

    monkeypatch.setattr(policy, "_run_legacy_fsm_transition", fail_fallback)

    policy._maybe_switch_skill(
        obs=_obs(mass=0.0, dig_distance=0.0),
        boundary_event=boundary_event,
    )

    assert policy._skill_name == "dig"
    assert policy._switch_reason == "bootstrap_to_dig"


def test_policy_maybe_switch_skill_applies_pre_dig_align_backend_outcome_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy._skill_name = "pre_dig_align"
    outcome = PreDigAlignOutcome(
        action="ready",
        switch_reason="pre_dig_align_to_dig_ready",
    )
    applied: list[tuple[PreDigAlignOutcome, dict[str, Any]]] = []

    def fail_fallback(*, obs: dict, boundary_event: Any | None) -> None:
        raise AssertionError("pre_dig_align should be handled by backend outcome effect")

    monkeypatch.setattr(policy, "_pre_dig_align_outcome", lambda obs: outcome)
    monkeypatch.setattr(
        policy,
        "_apply_pre_dig_align_outcome",
        lambda outcome, obs: applied.append((outcome, dict(obs))) or False,
    )
    monkeypatch.setattr(policy, "_run_legacy_fsm_transition", fail_fallback)

    policy._maybe_switch_skill(obs={"step": 14}, boundary_event=None)

    assert applied == [(outcome, {"step": 14})]


def test_policy_maybe_switch_skill_applies_dig_backend_projection_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy._skill_name = "dig"
    applied: list[tuple[DigTransitionRuntimeProjection, dict[str, Any]]] = []

    def dig_to_carry_ready(
        *,
        obs: dict,
        boundary_event: Any | None,
    ) -> bool:
        policy._dig_to_carry_reason = "target_payload_loaded"
        return True

    def fail_fallback(*, obs: dict, boundary_event: Any | None) -> None:
        raise AssertionError("dig should be handled by backend projection effect")

    monkeypatch.setattr(policy, "_dig_exit_guard_ready", lambda obs: False)
    monkeypatch.setattr(policy, "_dig_bad_replan_ready", lambda obs: False)
    monkeypatch.setattr(
        policy,
        "_dig_complete_boundary_low_payload",
        lambda obs, boundary_event: False,
    )
    monkeypatch.setattr(policy, "_dig_to_carry_ready", dig_to_carry_ready)
    monkeypatch.setattr(
        policy,
        "_apply_dig_transition_runtime_projection",
        lambda projection, obs: applied.append((projection, dict(obs))) or True,
    )
    monkeypatch.setattr(policy, "_run_legacy_fsm_transition", fail_fallback)

    policy._maybe_switch_skill(obs={"step": 17}, boundary_event=None)

    assert len(applied) == 1
    projection, obs = applied[0]
    assert obs == {"step": 17}
    assert projection.outcome == DigTransitionRuntimeOutcome(
        action="carry",
        switch_reason="dig_to_carry_target_payload_loaded",
    )


def test_policy_maybe_switch_skill_applies_carry_backend_runtime_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy._skill_name = "carry"
    boundary_event = _FakeBoundaryEvent(dump_committed_start=True)
    applied: list[tuple[CarryTransitionRuntimeState, dict[str, Any]]] = []

    def fail_fallback(*, obs: dict, boundary_event: Any | None) -> None:
        raise AssertionError("carry should be handled by backend runtime effect")

    monkeypatch.setattr(
        policy,
        "_apply_carry_transition_runtime",
        lambda runtime, obs: applied.append((runtime, dict(obs))) or True,
    )
    monkeypatch.setattr(policy, "_run_legacy_fsm_transition", fail_fallback)

    policy._maybe_switch_skill(obs={"step": 20}, boundary_event=boundary_event)

    assert len(applied) == 1
    runtime, obs = applied[0]
    assert obs == {"step": 20}
    assert runtime == CarryTransitionRuntimeState(
        dump_ready_hold_count=policy.dump_ready_hold_steps,
        outcome=DumpLifecycleOutcome(
            action="dump",
            switch_reason="carry_to_dump_dump_committed_boundary",
        ),
    )


def test_policy_maybe_switch_skill_applies_dump_backend_runtime_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy._skill_name = "dump"
    boundary_event = _FakeBoundaryEvent(dump_complete=True)
    applied: list[tuple[DumpTransitionRuntimeState, dict[str, Any]]] = []

    def fail_fallback(*, obs: dict, boundary_event: Any | None) -> None:
        raise AssertionError("dump should be handled by backend runtime effect")

    monkeypatch.setattr(
        policy,
        "_apply_dump_transition_runtime",
        lambda runtime, obs: applied.append((runtime, dict(obs))) or True,
    )
    monkeypatch.setattr(policy, "_run_legacy_fsm_transition", fail_fallback)

    policy._maybe_switch_skill(obs={"step": 23}, boundary_event=boundary_event)

    assert len(applied) == 1
    runtime, obs = applied[0]
    assert obs == {"step": 23}
    assert runtime == DumpTransitionRuntimeState(
        dump_done_hold_count=0,
        outcome=DumpLifecycleOutcome(
            action="return",
            switch_reason="dump_to_return_dump_complete_boundary",
            coverage_reason="dump_complete_boundary",
        ),
    )


def test_legacy_fsm_fallback_rejects_explicit_skill_to_avoid_recursion() -> None:
    policy = _make_policy()
    policy._skill_name = "dig"
    policy._legacy_fsm_backend = _FallbackOnlyBackend()

    with pytest.raises(ValueError, match="explicit legacy FSM branch.*dig"):
        policy._maybe_switch_skill(
            obs=_obs(mass=1000.0, dig_distance=0.0),
            boundary_event=_FakeBoundaryEvent(dig_complete=True),
        )


def _make_policy(**overrides: Any) -> PrimitivePlannerACTPolicy:
    kwargs: dict[str, Any] = {
        "dig_policy": _ConstantPolicy(0.0),
        "carry_policy": _ConstantPolicy(1.0),
        "dump_policy": _ConstantPolicy(2.0),
        "return_policy": _ConstantPolicy(3.0),
        "boundary_detector": _FakeBoundaryDetector(
            boundary_profile="v2_4_5_spatial_mass"
        ),
        "dig_to_carry_min_bucket_mass_kg": 999.0,
        "dump_ready_hold_steps": 3,
        "dump_done_hold_steps": 30,
    }
    kwargs.update(overrides)
    return PrimitivePlannerACTPolicy(**kwargs)


def _obs(
    *,
    mass: float,
    dig_distance: float,
    bucket_depth: float = 0.0,
    dump_ready: bool = False,
    deposited: float = 0.0,
) -> dict[str, Any]:
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_MASS_IN_BUCKET_IDX] = float(mass)
    env_state[ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX] = float(deposited)
    env_state[ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX] = float(dig_distance)
    env_state[ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX] = float(bucket_depth)
    env_state[ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX] = 0.15 if dump_ready else 2.0
    env_state[ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX] = (
        0.50 if dump_ready else -0.20
    )
    env_state[ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX] = 1.0 if dump_ready else 0.0
    env_state[ENV_STATE_DUMP_CLEARANCE_OK_IDX] = 1.0 if dump_ready else 0.0
    env_state[ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX] = 0.0
    env_state[ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX] = 0.0
    env_state[ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX] = (
        0.0 if dump_ready else 2.0
    )
    return {
        "qpos": np.zeros(4, dtype=np.float32),
        "qvel": np.zeros(4, dtype=np.float32),
        "env_state": env_state,
        "task_metrics": {
            "mass_in_bucket_kg": float(mass),
            "deposited_mass_in_target_box_kg": float(deposited),
            "min_distance_to_dig_area_m": float(dig_distance),
            "bucket_depth_below_dig_area_plane_m": float(bucket_depth),
            "target_geometry_available": 1.0,
            "target_horizontal_distance_m": float(
                env_state[ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX]
            ),
            "bucket_height_above_target_rim_m": float(
                env_state[ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX]
            ),
            "bucket_over_target_footprint_mask": float(
                env_state[ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX]
            ),
            "dump_clearance_ok_mask": float(
                env_state[ENV_STATE_DUMP_CLEARANCE_OK_IDX]
            ),
            "bucket_dump_area_relative_x_m": float(
                env_state[ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX]
            ),
            "bucket_dump_area_relative_z_m": float(
                env_state[ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX]
            ),
            "bucket_dump_area_footprint_outside_distance_m": float(
                env_state[ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX]
            ),
        },
    }


def _policy_reset_counts(policy: PrimitivePlannerACTPolicy) -> tuple[int, int, int, int]:
    return (
        policy.dig_policy.reset_count,
        policy.carry_policy.reset_count,
        policy.dump_policy.reset_count,
        policy.return_policy.reset_count,
    )


class _ConstantPolicy:
    def __init__(self, value: float) -> None:
        self.value = float(value)
        self.reset_count = 0

    def reset(self) -> None:
        self.reset_count += 1

    def predict(self, _obs: dict[str, Any]) -> np.ndarray:
        action = np.zeros(4, dtype=np.float32)
        action[0] = self.value
        return action


class _FallbackOnlyBackend:
    name = "fallback_only"

    def tick(self, context: PlannerTickContext) -> PlannerTickResult:
        return PlannerTickResult(
            node_path=("fallback_only",),
            effects=(
                PlannerRuntimeEffect(
                    LEGACY_FSM_TRANSITION_EFFECT,
                    {
                        "obs": context.obs,
                        "boundary_event": context.boundary_event,
                    },
                ),
            ),
        )


class _FakeBoundaryEvent:
    def __init__(
        self,
        *,
        qualified_dig_start: bool = False,
        dig_complete: bool = False,
        dump_committed_start: bool = False,
        dump_complete: bool = False,
        next_dig_entry_ready: bool = False,
        dump_end: bool = False,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        self.qualified_dig_start = bool(qualified_dig_start)
        self.dig_complete = bool(dig_complete)
        self.dump_committed_start = bool(dump_committed_start)
        self.dump_complete = bool(dump_complete)
        self.next_dig_entry_ready = bool(next_dig_entry_ready)
        self.dump_end = bool(dump_end)
        self.metrics = dict(metrics or {})


class _FakeBoundaryDetector:
    def __init__(self, *, boundary_profile: str) -> None:
        self.config = type(
            "_FakeBoundaryConfig",
            (),
            {"boundary_profile": str(boundary_profile)},
        )()

    def reset(self) -> None:
        pass

    def update(self, **_kwargs: Any) -> _FakeBoundaryEvent:
        return _FakeBoundaryEvent()
