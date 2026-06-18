from __future__ import annotations

import inspect

import pytest

from testbed.planner.runtime import (
    PlannerBackend,
    PlannerBlackboard,
    PlannerTickContext,
)
from testbed.planner.runtime import behavior_tree
from testbed.planner.runtime.behavior_tree import (
    BEHAVIOR_TREE_EXPERIMENTAL_BACKEND_NAME,
    BehaviorTreeBackend,
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

    assert "primitive_action_tree" not in source
    assert "primitive_planner" not in source
