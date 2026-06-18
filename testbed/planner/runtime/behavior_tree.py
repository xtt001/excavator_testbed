"""Experimental behavior-tree backend runtime contract."""

from __future__ import annotations

from dataclasses import dataclass

from typing import Any

from testbed.planner.runtime.contracts import PlannerTickContext, PlannerTickResult
from testbed.planner.runtime.ports import (
    PlannerDigTransitionPorts,
    PlannerReturnTransitionPorts,
)
from testbed.planner.runtime.transition_nodes import (
    build_dig_transition_result,
    build_return_transition_result,
)

BEHAVIOR_TREE_EXPERIMENTAL_BACKEND_NAME = "behavior_tree_experimental"


@dataclass(frozen=True, slots=True)
class BehaviorTreeBackend:
    """Experimental behavior-tree backend with explicitly wired runtime nodes."""

    name: str = BEHAVIOR_TREE_EXPERIMENTAL_BACKEND_NAME

    def tick(self, context: PlannerTickContext) -> PlannerTickResult:
        """Run one experimental behavior-tree runtime node when wired."""

        skill_names = context.ports.skill_names
        if (
            skill_names is not None
            and context.blackboard.current_skill == skill_names.dig
        ):
            return self._tick_dig(
                context,
                active_skill=context.blackboard.current_skill,
                ports=_required_port(
                    context.ports.dig_transition,
                    "dig_transition",
                ),
            )
        if skill_names is not None and context.blackboard.current_skill == (
            skill_names.return_skill
        ):
            return self._tick_return(
                context,
                active_skill=context.blackboard.current_skill,
                ports=_required_port(
                    context.ports.return_transition,
                    "return_transition",
                ),
            )
        raise NotImplementedError(
            "BehaviorTreeBackend is experimental and not wired to runtime nodes "
            f"for skill {context.blackboard.current_skill!r}."
        )

    def _tick_dig(
        self,
        context: PlannerTickContext,
        *,
        active_skill: str,
        ports: PlannerDigTransitionPorts,
    ) -> PlannerTickResult:
        return build_dig_transition_result(
            context,
            active_skill=active_skill,
            node_root="behavior_tree",
            ports=ports,
        )

    def _tick_return(
        self,
        context: PlannerTickContext,
        *,
        active_skill: str,
        ports: PlannerReturnTransitionPorts,
    ) -> PlannerTickResult:
        return build_return_transition_result(
            context,
            active_skill=active_skill,
            node_root="behavior_tree",
            ports=ports,
        )


def _required_port(port: Any | None, name: str) -> Any:
    if port is None:
        raise ValueError(f"Behavior tree backend requires typed port {name!r}.")
    return port


__all__ = [
    "BEHAVIOR_TREE_EXPERIMENTAL_BACKEND_NAME",
    "BehaviorTreeBackend",
]
