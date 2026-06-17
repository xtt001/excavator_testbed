"""Experimental behavior-tree backend runtime contract."""

from __future__ import annotations

from dataclasses import dataclass

from testbed.planner.runtime.contracts import PlannerTickContext, PlannerTickResult

BEHAVIOR_TREE_EXPERIMENTAL_BACKEND_NAME = "behavior_tree_experimental"


@dataclass(frozen=True, slots=True)
class BehaviorTreeBackend:
    """Fail-closed backend skeleton for future behavior-tree runtime work."""

    name: str = BEHAVIOR_TREE_EXPERIMENTAL_BACKEND_NAME

    def tick(self, context: PlannerTickContext) -> PlannerTickResult:
        """Refuse execution until runtime nodes and effects are implemented."""

        del context
        raise NotImplementedError(
            "BehaviorTreeBackend is experimental and not wired to runtime nodes."
        )


__all__ = [
    "BEHAVIOR_TREE_EXPERIMENTAL_BACKEND_NAME",
    "BehaviorTreeBackend",
]
