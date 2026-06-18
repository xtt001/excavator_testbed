from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from testbed.planner.dig_coverage import CoverageServiceState
from testbed.planner.runtime import (
    PlannerBlackboard,
    PlannerBackend,
    PlannerRuntimeEffect,
    PlannerTickContext,
    PlannerTickResult,
)


def test_planner_blackboard_defaults_are_minimal_runtime_state() -> None:
    blackboard = PlannerBlackboard()

    assert blackboard.current_skill == ""
    assert blackboard.switch_reason == ""
    assert blackboard.cycle_index == 0
    assert blackboard.completed_transition_count == 0
    assert blackboard.transition_timeout_count == 0


def test_planner_blackboard_is_immutable_and_hashable_snapshot() -> None:
    blackboard = PlannerBlackboard(
        current_skill="dig",
        switch_reason="reset",
        cycle_index=3,
        completed_transition_count=2,
        transition_timeout_count=1,
    )

    assert hash(blackboard) == hash(
        PlannerBlackboard(
            current_skill="dig",
            switch_reason="reset",
            cycle_index=3,
            completed_transition_count=2,
            transition_timeout_count=1,
        )
    )
    with pytest.raises(FrozenInstanceError):
        blackboard.current_skill = "return"  # type: ignore[misc]


def test_planner_blackboard_updates_return_new_lifecycle_snapshots() -> None:
    blackboard = PlannerBlackboard(
        current_skill="return",
        switch_reason="before",
        cycle_index=4,
        completed_transition_count=2,
        transition_timeout_count=1,
    )

    skill = blackboard.with_skill("dig", "return_to_dig_ready")
    reason = blackboard.with_switch_reason("cleared")
    timeout = blackboard.with_transition_timeout_increment()
    transition = blackboard.with_return_transition_counts(
        completed_increment=3,
        cycle_increment=5,
    )

    assert blackboard == PlannerBlackboard(
        current_skill="return",
        switch_reason="before",
        cycle_index=4,
        completed_transition_count=2,
        transition_timeout_count=1,
    )
    assert skill == PlannerBlackboard(
        current_skill="dig",
        switch_reason="return_to_dig_ready",
        cycle_index=4,
        completed_transition_count=2,
        transition_timeout_count=1,
    )
    assert reason.switch_reason == "cleared"
    assert reason.current_skill == "return"
    assert timeout.transition_timeout_count == 2
    assert timeout.cycle_index == 4
    assert transition.completed_transition_count == 5
    assert transition.cycle_index == 9


def test_tick_context_references_coverage_state_without_copying() -> None:
    coverage_state = CoverageServiceState(active_corridor_id=7)
    blackboard = PlannerBlackboard(current_skill="dig")

    context = PlannerTickContext(
        obs={"step": 3},
        coverage_state=coverage_state,
        blackboard=blackboard,
    )

    assert context.coverage_state is coverage_state
    assert dict(context.obs) == {"step": 3}
    assert context.blackboard is blackboard
    assert context.blackboard.current_skill == "dig"
    with pytest.raises(TypeError):
        context.obs["step"] = 4  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        context.coverage_state = None  # type: ignore[misc]

    coverage_state.active_corridor_id = 9
    assert context.coverage_state.active_corridor_id == 9


def test_tick_context_rejects_untyped_blackboard_mapping() -> None:
    with pytest.raises(TypeError, match="PlannerBlackboard"):
        PlannerTickContext(blackboard={"skill_name": "dig"})  # type: ignore[arg-type]


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
