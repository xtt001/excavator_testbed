from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from testbed.planner.dig_coverage import CoverageServiceState
from testbed.planner.runtime import (
    PlannerBackend,
    PlannerRuntimeEffect,
    PlannerTickContext,
    PlannerTickResult,
)


def test_tick_context_references_coverage_state_without_copying() -> None:
    coverage_state = CoverageServiceState(active_corridor_id=7)

    context = PlannerTickContext(
        obs={"step": 3},
        coverage_state=coverage_state,
        blackboard={"skill_name": "dig"},
    )

    assert context.coverage_state is coverage_state
    assert dict(context.obs) == {"step": 3}
    assert dict(context.blackboard) == {"skill_name": "dig"}
    with pytest.raises(TypeError):
        context.obs["step"] = 4  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        context.coverage_state = None  # type: ignore[misc]

    coverage_state.active_corridor_id = 9
    assert context.coverage_state.active_corridor_id == 9


def test_runtime_effect_payload_is_an_immutable_hashable_copy() -> None:
    payload = {"skill_name": "dig", "reset": True}

    effect = PlannerRuntimeEffect("set_skill", payload)
    payload["skill_name"] = "return"

    assert effect.effect_type == "set_skill"
    assert dict(effect.payload) == {"skill_name": "dig", "reset": True}
    with pytest.raises(TypeError):
        effect.payload["skill_name"] = "carry"  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        effect.effect_type = "reset_policy"  # type: ignore[misc]
    assert hash(effect) == hash(
        PlannerRuntimeEffect("set_skill", {"skill_name": "dig", "reset": True})
    )


def test_tick_result_preserves_effect_order_and_hashable_scalar_contract() -> None:
    first = PlannerRuntimeEffect("set_skill", {"skill_name": "dig"})
    second = PlannerRuntimeEffect("reset_policy", {"policy": "dig"})
    third = PlannerRuntimeEffect("record_trace", {"reason": "dig_complete"})

    result = PlannerTickResult(
        node_path=["transition", "dig"],
        status="success",
        reason="dig_complete",
        effects=[first, second, third],
        diagnostics={"source": "unit-test"},
    )

    assert result.node_path == ("transition", "dig")
    assert result.effects == (first, second, third)
    assert [effect.effect_type for effect in result.effects] == [
        "set_skill",
        "reset_policy",
        "record_trace",
    ]
    assert dict(result.diagnostics) == {"source": "unit-test"}
    with pytest.raises(TypeError):
        result.diagnostics["source"] = "mutated"  # type: ignore[index]
    assert hash(result) == hash(
        PlannerTickResult(
            node_path=("transition", "dig"),
            status="success",
            reason="dig_complete",
            effects=(first, second, third),
            diagnostics={"source": "unit-test"},
        )
    )


def test_planner_backend_protocol_accepts_tick_implementation() -> None:
    class EchoBackend:
        name = "echo"

        def tick(self, context: PlannerTickContext) -> PlannerTickResult:
            return PlannerTickResult(
                node_path=("echo", str(context.obs["step"])),
                status="success",
                reason=self.name,
            )

    backend = EchoBackend()

    assert isinstance(backend, PlannerBackend)
    result = backend.tick(PlannerTickContext(obs={"step": 5}))

    assert result.node_path == ("echo", "5")
    assert result.status == "success"
    assert result.reason == "echo"
