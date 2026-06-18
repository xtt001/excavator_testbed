from __future__ import annotations

from dataclasses import dataclass
import inspect
from typing import Any

import pytest

from testbed.planner.dig_lifecycle import (
    DigGateDecision,
    DigLifecycleGateService,
    DigTransitionRuntimeOutcome,
    DigTransitionRuntimeProjection,
)
from testbed.planner.return_to_dig_transition import (
    ReturnToDigTransitionOutcome,
    ReturnToDigTransitionRuntimeProjection,
)
from testbed.planner.runtime import (
    PlannerBackendPorts,
    PlannerBackend,
    PlannerBlackboard,
    PlannerDigTransitionPorts,
    PlannerReturnTransitionPorts,
    PlannerSkillNames,
    PlannerTickContext,
)
from testbed.planner.runtime import behavior_tree
from testbed.planner.runtime import transition_nodes
from testbed.planner.runtime.behavior_tree import (
    BEHAVIOR_TREE_EXPERIMENTAL_BACKEND_NAME,
    BehaviorTreeBackend,
)
from testbed.planner.runtime.effects import (
    APPLY_DIG_TRANSITION_RUNTIME_PROJECTION_EFFECT,
    APPLY_RETURN_TO_DIG_TRANSITION_RUNTIME_EFFECT,
)


def test_behavior_tree_backend_is_experimental_backend_contract() -> None:
    backend = BehaviorTreeBackend()

    assert backend.name == BEHAVIOR_TREE_EXPERIMENTAL_BACKEND_NAME
    assert isinstance(backend, PlannerBackend)
    with pytest.raises(NotImplementedError, match="experimental.*not wired"):
        backend.tick(
            PlannerTickContext(
                obs={"step": 1},
                blackboard=PlannerBlackboard(current_skill="dig"),
            )
        )


def test_behavior_tree_runtime_contract_does_not_import_shadow_runner_or_shell() -> None:
    source = inspect.getsource(behavior_tree) + inspect.getsource(transition_nodes)

    assert "legacy_fsm" not in source
    assert "primitive_action_tree" not in source
    assert "primitive_planner" not in source


def test_behavior_tree_return_node_uses_runtime_ports_without_shell() -> None:
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

    result = BehaviorTreeBackend().tick(
        PlannerTickContext(
            obs={"step": 11},
            boundary_event=object(),
            blackboard=PlannerBlackboard(
                current_skill="return",
                return_next_dig_event_seen=True,
            ),
            ports=PlannerBackendPorts(
                skill_names=PlannerSkillNames(
                    bootstrap="bootstrap",
                    pre_dig_align="pre_dig_align",
                    dig="dig",
                    carry="carry",
                    dump="dump",
                    return_skill="return",
                ),
                return_transition=PlannerReturnTransitionPorts(
                    return_transition_runtime=return_transition_runtime,
                ),
            ),
        )
    )

    assert calls == ["return:11:True:True"]
    assert result.node_path == ("behavior_tree", "transition", "return")
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


def test_behavior_tree_dig_node_uses_runtime_ports_without_shell() -> None:
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

    result = BehaviorTreeBackend().tick(
        PlannerTickContext(
            obs={"step": 15},
            boundary_event=object(),
            blackboard=PlannerBlackboard(current_skill="dig"),
            ports=PlannerBackendPorts(
                skill_names=PlannerSkillNames(
                    bootstrap="bootstrap",
                    pre_dig_align="pre_dig_align",
                    dig="dig",
                    carry="carry",
                    dump="dump",
                    return_skill="return",
                ),
                dig_transition=PlannerDigTransitionPorts(
                    lifecycle_gate=DigLifecycleGateService(),
                    exit_guard_ready=exit_guard_ready,
                    bad_replan_ready=bad_replan_ready,
                    complete_boundary_low_payload=(
                        complete_boundary_low_payload
                    ),
                    dig_to_carry_decision=dig_to_carry_decision,
                ),
            ),
        )
    )

    assert calls == [
        "exit_guard:15",
        "bad_replan:15",
        "complete_low:15:True",
        "dig_to_carry:15:True",
    ]
    assert result.node_path == ("behavior_tree", "transition", "dig")
    assert result.status == "running"
    assert result.reason == "dig_to_carry_target_payload_loaded"
    assert result.effects[0].effect_type == (
        APPLY_DIG_TRANSITION_RUNTIME_PROJECTION_EFFECT
    )
    assert dict(result.effects[0].payload["obs"]) == {"step": 15}
    projection = result.effects[0].payload["projection"]
    assert isinstance(projection, DigTransitionRuntimeProjection)
    assert projection.outcome == DigTransitionRuntimeOutcome(
        action="carry",
        switch_reason="dig_to_carry_target_payload_loaded",
    )
    assert dict(result.diagnostics) == {
        "active_skill": "dig",
        "action": "carry",
        "switch_reason": "dig_to_carry_target_payload_loaded",
    }
