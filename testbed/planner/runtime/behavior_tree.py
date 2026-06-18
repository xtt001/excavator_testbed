"""Experimental behavior-tree backend runtime contract."""

from __future__ import annotations

from dataclasses import dataclass

from typing import Any

from testbed.planner.runtime.contracts import (
    PlannerRuntimeEffect,
    PlannerTickContext,
    PlannerTickResult,
)
from testbed.planner.runtime.effects import (
    APPLY_RETURN_TO_DIG_TRANSITION_RUNTIME_EFFECT,
)
from testbed.planner.runtime.ports import PlannerReturnTransitionPorts

BEHAVIOR_TREE_EXPERIMENTAL_BACKEND_NAME = "behavior_tree_experimental"


@dataclass(frozen=True, slots=True)
class BehaviorTreeBackend:
    """Experimental behavior-tree backend with explicitly wired runtime nodes."""

    name: str = BEHAVIOR_TREE_EXPERIMENTAL_BACKEND_NAME

    def tick(self, context: PlannerTickContext) -> PlannerTickResult:
        """Run one experimental behavior-tree runtime node when wired."""

        skill_names = context.ports.skill_names
        if skill_names is not None and (
            context.blackboard.current_skill == skill_names.return_skill
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

    def _tick_return(
        self,
        context: PlannerTickContext,
        *,
        active_skill: str,
        ports: PlannerReturnTransitionPorts,
    ) -> PlannerTickResult:
        obs = dict(context.obs)
        runtime = ports.return_transition_runtime(
            obs=obs,
            boundary_event=context.boundary_event,
            previous_next_dig_event_seen=(
                context.blackboard.return_next_dig_event_seen
            ),
        )
        outcome = runtime.outcome
        projection = runtime.projection
        return PlannerTickResult(
            node_path=("behavior_tree", "transition", active_skill),
            status="running",
            reason=str(getattr(outcome, "reason_suffix", "")),
            effects=(
                PlannerRuntimeEffect(
                    APPLY_RETURN_TO_DIG_TRANSITION_RUNTIME_EFFECT,
                    {"outcome": outcome, "projection": projection},
                ),
            ),
            diagnostics={
                "active_skill": active_skill,
                "action": str(getattr(outcome, "action", "")),
                "reason_suffix": str(getattr(outcome, "reason_suffix", "")),
                "next_dig_event_seen": bool(
                    getattr(outcome, "next_dig_event_seen", False)
                ),
            },
        )


def _required_port(port: Any | None, name: str) -> Any:
    if port is None:
        raise ValueError(f"Behavior tree backend requires typed port {name!r}.")
    return port


__all__ = [
    "BEHAVIOR_TREE_EXPERIMENTAL_BACKEND_NAME",
    "BehaviorTreeBackend",
]
