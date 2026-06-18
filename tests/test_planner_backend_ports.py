from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from testbed.planner.dig_lifecycle import (
    DigGateDecision,
    DigLifecycleGateService,
    DigTransitionRuntimeOutcome,
    DigTransitionRuntimeProjection,
)
from testbed.planner.dump_lifecycle import (
    CarryTransitionRuntimeState,
    DumpLifecycleOutcome,
    DumpTransitionRuntimeState,
)
from testbed.planner.return_to_dig_transition import (
    ReturnToDigTransitionOutcome,
    ReturnToDigTransitionRuntimeProjection,
)
from testbed.planner.runtime import (
    LegacyFsmBackendPorts,
    LegacyFsmSkillNames,
    PlannerBackendPorts,
    PlannerBlackboard,
    PlannerDigTransitionPorts,
    PlannerDumpLifecyclePorts,
    PlannerReturnTransitionPorts,
    PlannerTickContext,
)
from testbed.planner.runtime.legacy_fsm import (
    APPLY_CARRY_TRANSITION_RUNTIME_EFFECT,
    APPLY_DIG_TRANSITION_RUNTIME_PROJECTION_EFFECT,
    APPLY_DUMP_TRANSITION_RUNTIME_EFFECT,
    APPLY_RETURN_TO_DIG_TRANSITION_RUNTIME_EFFECT,
    LegacyStateMachineBackend,
)


def test_tick_context_uses_typed_backend_ports_and_rejects_services_mapping() -> None:
    ports = PlannerBackendPorts(
        legacy_fsm=LegacyFsmBackendPorts(skill_names=_skill_names())
    )

    context = PlannerTickContext(ports=ports)

    assert context.ports is ports
    assert context.ports.legacy_fsm is not None
    assert context.ports.legacy_fsm.skill_names.dig == "dig"
    assert not hasattr(context, "services")
    with pytest.raises(TypeError, match="services"):
        PlannerTickContext(services={"dig_skill_name": "dig"})  # type: ignore[call-arg]


def test_legacy_fsm_backend_dig_uses_typed_ports_preserving_gate_order() -> None:
    calls: list[str] = []

    def exit_guard_ready(obs: dict) -> bool:
        calls.append(f"exit_guard:{obs['step']}")
        return False

    def bad_replan_ready(obs: dict) -> bool:
        calls.append(f"bad_replan:{obs['step']}")
        return False

    def complete_boundary_low_payload(
        obs: dict,
        boundary_event: Any | None,
    ) -> bool:
        calls.append(f"complete_low:{obs['step']}:{boundary_event is not None}")
        return False

    def dig_to_carry_decision(
        *,
        obs: dict,
        boundary_event: Any | None,
    ) -> DigGateDecision:
        calls.append(f"dig_to_carry:{obs['step']}:{boundary_event is not None}")
        return DigGateDecision(True, "target_payload_loaded")

    result = LegacyStateMachineBackend().tick(
        PlannerTickContext(
            obs={"step": 15},
            boundary_event=_FakeBoundaryEvent(dig_complete=True),
            blackboard=PlannerBlackboard(current_skill="dig"),
            ports=PlannerBackendPorts(
                dig_transition=PlannerDigTransitionPorts(
                    lifecycle_gate=DigLifecycleGateService(),
                    exit_guard_ready=exit_guard_ready,
                    bad_replan_ready=bad_replan_ready,
                    complete_boundary_low_payload=(
                        complete_boundary_low_payload
                    ),
                    dig_to_carry_decision=dig_to_carry_decision,
                ),
                legacy_fsm=LegacyFsmBackendPorts(
                    skill_names=_skill_names(),
                )
            ),
        )
    )

    assert result.node_path == ("legacy_fsm", "transition", "dig")
    assert result.status == "running"
    assert result.reason == "dig_to_carry_target_payload_loaded"
    assert calls == [
        "exit_guard:15",
        "bad_replan:15",
        "complete_low:15:True",
        "dig_to_carry:15:True",
    ]
    effect = result.effects[0]
    assert effect.effect_type == APPLY_DIG_TRANSITION_RUNTIME_PROJECTION_EFFECT
    assert dict(effect.payload["obs"]) == {"step": 15}
    projection = effect.payload["projection"]
    assert isinstance(projection, DigTransitionRuntimeProjection)
    assert projection.outcome == DigTransitionRuntimeOutcome(
        action="carry",
        switch_reason="dig_to_carry_target_payload_loaded",
    )


def test_legacy_fsm_backend_carry_dump_use_typed_runtime_ports() -> None:
    calls: list[str] = []

    def carry_transition_runtime(
        *,
        obs: dict,
        boundary_event: Any | None,
        current_dump_ready_hold_count: int,
    ) -> CarryTransitionRuntimeState:
        calls.append(
            "carry:"
            f"{obs['step']}:"
            f"{boundary_event is not None}:"
            f"{current_dump_ready_hold_count}"
        )
        return CarryTransitionRuntimeState(
            dump_ready_hold_count=current_dump_ready_hold_count + 1,
            outcome=DumpLifecycleOutcome(
                action="dump",
                switch_reason="carry_to_dump_target_ready",
            ),
        )

    def dump_transition_runtime(
        *,
        obs: dict,
        boundary_event: Any | None,
        current_dump_done_hold_count: int,
    ) -> DumpTransitionRuntimeState:
        calls.append(
            "dump:"
            f"{obs['step']}:"
            f"{boundary_event is not None}:"
            f"{current_dump_done_hold_count}"
        )
        return DumpTransitionRuntimeState(
            dump_done_hold_count=current_dump_done_hold_count + 1,
            outcome=DumpLifecycleOutcome(
                action="return",
                switch_reason="dump_to_return_mass_low",
                coverage_reason="dump_mass_low",
            ),
        )

    ports = PlannerBackendPorts(
        dump_lifecycle=PlannerDumpLifecyclePorts(
            carry_transition_runtime=carry_transition_runtime,
            dump_transition_runtime=dump_transition_runtime,
        ),
        legacy_fsm=LegacyFsmBackendPorts(
            skill_names=_skill_names(),
        )
    )

    carry_result = LegacyStateMachineBackend().tick(
        PlannerTickContext(
            obs={"step": 18},
            boundary_event=None,
            blackboard=PlannerBlackboard(
                current_skill="carry",
                dump_ready_hold_count=1,
            ),
            ports=ports,
        )
    )
    dump_result = LegacyStateMachineBackend().tick(
        PlannerTickContext(
            obs={"step": 21},
            boundary_event=_FakeBoundaryEvent(dump_complete=True),
            blackboard=PlannerBlackboard(
                current_skill="dump",
                dump_done_hold_count=2,
            ),
            ports=ports,
        )
    )

    assert calls == ["carry:18:False:1", "dump:21:True:2"]
    assert carry_result.reason == "carry_to_dump_target_ready"
    assert carry_result.effects[0].effect_type == APPLY_CARRY_TRANSITION_RUNTIME_EFFECT
    assert carry_result.effects[0].payload["runtime"] == CarryTransitionRuntimeState(
        dump_ready_hold_count=2,
        outcome=DumpLifecycleOutcome(
            action="dump",
            switch_reason="carry_to_dump_target_ready",
        ),
    )
    assert dump_result.reason == "dump_to_return_mass_low"
    assert dump_result.effects[0].effect_type == APPLY_DUMP_TRANSITION_RUNTIME_EFFECT
    assert dump_result.effects[0].payload["runtime"] == DumpTransitionRuntimeState(
        dump_done_hold_count=3,
        outcome=DumpLifecycleOutcome(
            action="return",
            switch_reason="dump_to_return_mass_low",
            coverage_reason="dump_mass_low",
        ),
    )


def test_legacy_fsm_backend_return_uses_typed_runtime_port() -> None:
    calls: list[str] = []

    outcome = ReturnToDigTransitionOutcome(
        action="next_dig_event",
        reason_suffix="next_dig_entry_ready",
        next_dig_event_seen=True,
    )
    projection = ReturnToDigTransitionRuntimeProjection(
        next_dig_event_seen=True,
        should_transition=True,
        completed_transition_increment=1,
        cycle_index_increment=1,
    )

    @dataclass(frozen=True)
    class ReturnRuntime:
        outcome: ReturnToDigTransitionOutcome
        projection: ReturnToDigTransitionRuntimeProjection

    def return_transition_runtime(
        *,
        obs: dict,
        boundary_event: Any | None,
        previous_next_dig_event_seen: bool,
    ) -> ReturnRuntime:
        calls.append(
            "return:"
            f"{obs['step']}:"
            f"{boundary_event is not None}:"
            f"{previous_next_dig_event_seen}"
        )
        return ReturnRuntime(outcome=outcome, projection=projection)

    result = LegacyStateMachineBackend().tick(
        PlannerTickContext(
            obs={"step": 24},
            boundary_event=_FakeBoundaryEvent(next_dig_entry_ready=True),
            blackboard=PlannerBlackboard(
                current_skill="return",
                return_next_dig_event_seen=True,
            ),
            ports=PlannerBackendPorts(
                return_transition=PlannerReturnTransitionPorts(
                    return_transition_runtime=return_transition_runtime,
                ),
                legacy_fsm=LegacyFsmBackendPorts(
                    skill_names=_skill_names(),
                )
            ),
        )
    )

    assert calls == ["return:24:True:True"]
    assert result.node_path == ("legacy_fsm", "transition", "return")
    assert result.status == "running"
    assert result.reason == "next_dig_entry_ready"
    assert result.effects[0].effect_type == (
        APPLY_RETURN_TO_DIG_TRANSITION_RUNTIME_EFFECT
    )
    assert result.effects[0].payload == {
        "outcome": outcome,
        "projection": projection,
    }
    assert dict(result.diagnostics) == {
        "active_skill": "return",
        "action": "next_dig_event",
        "reason_suffix": "next_dig_entry_ready",
        "next_dig_event_seen": True,
    }


def _skill_names() -> LegacyFsmSkillNames:
    return LegacyFsmSkillNames(
        bootstrap="bootstrap",
        pre_dig_align="pre_dig_align",
        dig="dig",
        carry="carry",
        dump="dump",
        return_skill="return",
    )


class _FakeBoundaryEvent:
    def __init__(self, **flags: bool) -> None:
        self.flags = flags

    def __getattr__(self, name: str) -> bool:
        return bool(self.flags.get(name, False))
