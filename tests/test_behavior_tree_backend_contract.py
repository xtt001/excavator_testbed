from __future__ import annotations

from dataclasses import dataclass
import inspect
from typing import Any

import pytest

from testbed.planner.return_to_dig_transition import (
    ReturnToDigTransitionOutcome,
    ReturnToDigTransitionRuntimeProjection,
)
from testbed.planner.runtime import (
    PlannerBackendPorts,
    PlannerBackend,
    PlannerBlackboard,
    PlannerReturnTransitionPorts,
    PlannerSkillNames,
    PlannerTickContext,
)
from testbed.planner.runtime import behavior_tree
from testbed.planner.runtime.behavior_tree import (
    BEHAVIOR_TREE_EXPERIMENTAL_BACKEND_NAME,
    BehaviorTreeBackend,
)
from testbed.planner.runtime.effects import (
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
    source = inspect.getsource(behavior_tree)

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
