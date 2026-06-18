from __future__ import annotations

from typing import Any

import pytest

from testbed.planner.dig_lifecycle import (
    DigLifecycleGateService,
    DigTransitionRuntimeOutcome,
    DigTransitionRuntimeProjection,
)
from testbed.planner.runtime import (
    LegacyFsmBackendPorts,
    LegacyFsmDigTransitionPorts,
    LegacyFsmSkillNames,
    PlannerBackendPorts,
    PlannerBlackboard,
    PlannerTickContext,
)
from testbed.planner.runtime.legacy_fsm import (
    APPLY_DIG_TRANSITION_RUNTIME_PROJECTION_EFFECT,
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

    def dig_to_carry_ready(
        *,
        obs: dict,
        boundary_event: Any | None,
    ) -> bool:
        calls.append(f"dig_to_carry:{obs['step']}:{boundary_event is not None}")
        return True

    result = LegacyStateMachineBackend().tick(
        PlannerTickContext(
            obs={"step": 15},
            boundary_event=_FakeBoundaryEvent(dig_complete=True),
            blackboard=PlannerBlackboard(current_skill="dig"),
            ports=PlannerBackendPorts(
                legacy_fsm=LegacyFsmBackendPorts(
                    skill_names=_skill_names(),
                    dig_transition=LegacyFsmDigTransitionPorts(
                        lifecycle_gate=DigLifecycleGateService(),
                        exit_guard_ready=exit_guard_ready,
                        bad_replan_ready=bad_replan_ready,
                        complete_boundary_low_payload=(
                            complete_boundary_low_payload
                        ),
                        dig_to_carry_ready=dig_to_carry_ready,
                        dig_to_carry_reason=lambda: "target_payload_loaded",
                    ),
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
