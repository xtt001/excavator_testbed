from __future__ import annotations

from typing import Any

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
    LegacyFsmDumpLifecyclePorts,
    LegacyFsmSkillNames,
    PlannerBackendPorts,
    PlannerBlackboard,
    PlannerTickContext,
)
from testbed.planner.runtime.legacy_fsm import (
    APPLY_CARRY_TRANSITION_RUNTIME_EFFECT,
    APPLY_DUMP_TRANSITION_RUNTIME_EFFECT,
    LegacyStateMachineBackend,
)


def test_legacy_fsm_backend_carry_returns_apply_runtime_effect() -> None:
    calls: list[str] = []

    def carry_release_safety_done(obs: dict) -> bool:
        calls.append(f"release_safety:{obs['step']}")
        return False

    def dump_ready(obs: dict) -> bool:
        calls.append(f"dump_ready:{obs['step']}")
        return True

    service = DumpLifecycleGateService()

    def carry_transition_runtime(
        *,
        obs: dict,
        boundary_event: Any | None,
        current_dump_ready_hold_count: int,
    ) -> CarryTransitionRuntimeState:
        release_safety_done = carry_release_safety_done(obs)
        request = build_carry_transition_runtime_request(
            release_safety_done=release_safety_done,
            boundary_event=boundary_event,
            semantic_boundary_profile_active=False,
            current_dump_ready_hold_count=current_dump_ready_hold_count,
        )
        ready = bool(dump_ready(obs)) if request.should_check_dump_ready else False
        return service.carry_transition_runtime(
            request.facts_with_dump_ready(ready),
            dump_ready_hold_steps=2,
        )

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
                    carry_transition_runtime=carry_transition_runtime,
                    dump_transition_runtime=_unused_dump_transition_runtime,
                ),
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

    service = DumpLifecycleGateService()

    def carry_transition_runtime(
        *,
        obs: dict,
        boundary_event: Any | None,
        current_dump_ready_hold_count: int,
    ) -> CarryTransitionRuntimeState:
        request = build_carry_transition_runtime_request(
            release_safety_done=False,
            boundary_event=boundary_event,
            semantic_boundary_profile_active=False,
            current_dump_ready_hold_count=current_dump_ready_hold_count,
        )
        ready = bool(dump_ready(obs)) if request.should_check_dump_ready else False
        return service.carry_transition_runtime(
            request.facts_with_dump_ready(ready),
            dump_ready_hold_steps=3,
        )

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
                    carry_transition_runtime=carry_transition_runtime,
                    dump_transition_runtime=_unused_dump_transition_runtime,
                ),
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

    service = DumpLifecycleGateService()

    def dump_transition_runtime(
        *,
        obs: dict,
        boundary_event: Any | None,
        current_dump_done_hold_count: int,
    ) -> DumpTransitionRuntimeState:
        request = build_dump_transition_runtime_request(
            dump_done_use_boundary_event=True,
            boundary_event=boundary_event,
            semantic_boundary_profile_active=False,
            current_dump_done_hold_count=current_dump_done_hold_count,
        )
        done = bool(dump_done(obs)) if request.should_check_dump_done else False
        return service.dump_transition_runtime(
            request.facts_with_dump_done(done),
            dump_done_hold_steps=2,
        )

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
                    carry_transition_runtime=_unused_carry_transition_runtime,
                    dump_transition_runtime=dump_transition_runtime,
                ),
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

    service = DumpLifecycleGateService()

    def dump_transition_runtime(
        *,
        obs: dict,
        boundary_event: Any | None,
        current_dump_done_hold_count: int,
    ) -> DumpTransitionRuntimeState:
        request = build_dump_transition_runtime_request(
            dump_done_use_boundary_event=True,
            boundary_event=boundary_event,
            semantic_boundary_profile_active=False,
            current_dump_done_hold_count=current_dump_done_hold_count,
        )
        done = bool(dump_done(obs)) if request.should_check_dump_done else False
        return service.dump_transition_runtime(
            request.facts_with_dump_done(done),
            dump_done_hold_steps=3,
        )

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
                    carry_transition_runtime=_unused_carry_transition_runtime,
                    dump_transition_runtime=dump_transition_runtime,
                ),
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


def _ports(**legacy_ports: object) -> PlannerBackendPorts:
    return PlannerBackendPorts(
        legacy_fsm=LegacyFsmBackendPorts(
            skill_names=LegacyFsmSkillNames(
                bootstrap="bootstrap",
                pre_dig_align="pre_dig_align",
                dig="dig",
                carry="carry",
                dump="dump",
                return_skill="return",
            ),
            **legacy_ports,
        )
    )


def _unused_carry_transition_runtime(**_kwargs: object) -> CarryTransitionRuntimeState:
    return CarryTransitionRuntimeState(
        dump_ready_hold_count=0,
        outcome=DumpLifecycleOutcome(action="none"),
    )


def _unused_dump_transition_runtime(**_kwargs: object) -> DumpTransitionRuntimeState:
    return DumpTransitionRuntimeState(
        dump_done_hold_count=0,
        outcome=DumpLifecycleOutcome(action="none"),
    )


class _FakeBoundaryEvent:
    def __init__(self, **flags: bool) -> None:
        self.flags = flags

    def __getattr__(self, name: str) -> bool:
        return bool(self.flags.get(name, False))
