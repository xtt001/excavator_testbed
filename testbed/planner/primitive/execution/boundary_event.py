"""Live boundary-event tick source runtime boundary."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from testbed.planner.primitive.execution.state import PrimitiveExecutionRuntimeState
from testbed.planner.primitive.facts.capabilities import PrimitiveObservationFacts


@dataclass(frozen=True)
class PrimitiveBoundaryEventRuntimePorts:
    """Focused inputs for boundary-event tick source projection."""

    execution_state: PrimitiveExecutionRuntimeState
    boundary_detector: Any
    observation_facts: Callable[[dict[str, Any]], PrimitiveObservationFacts]


@dataclass(frozen=True)
class PrimitiveBoundaryEventRuntimeService:
    """Project one tick's boundary-detector input from focused runtime facts."""

    ports: PrimitiveBoundaryEventRuntimePorts

    @classmethod
    def from_ports(
        cls,
        ports: PrimitiveBoundaryEventRuntimePorts,
    ) -> PrimitiveBoundaryEventRuntimeService:
        return cls(ports=ports)

    def update(self, obs: dict[str, Any]) -> Any | None:
        action = self.ports.execution_state.prev_action
        if action is None:
            return None
        facts = self.ports.observation_facts(obs)
        return self.ports.boundary_detector.update(
            env_state=facts.env_state,
            action=action,
            qpos=facts.qpos,
            reward_phase=facts.reward_phase,
            task_step_successes=facts.task_step_successes,
            task_metrics=facts.task_metrics,
        )


__all__ = [
    "PrimitiveBoundaryEventRuntimePorts",
    "PrimitiveBoundaryEventRuntimeService",
]
