"""Live dig-progress tick update runtime boundary."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from testbed.planner.primitive.facts.capabilities import PrimitiveObservationFacts
from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.execution.cycle_state import PrimitiveCycleRuntimeState


@dataclass(frozen=True)
class PrimitiveDigProgressRuntimeConfig:
    """Configuration for per-tick dig progress support updates."""

    plateau_epsilon_kg: float


@dataclass(frozen=True)
class PrimitiveDigProgressRuntimePorts:
    """Focused owners and typed observation facts for dig progress updates."""

    cycle_state: PrimitiveCycleRuntimeState
    coverage_state: CoverageRuntimeState
    observation_facts: Callable[[dict[str, Any]], PrimitiveObservationFacts]
    config: PrimitiveDigProgressRuntimeConfig


@dataclass(frozen=True)
class PrimitiveDigProgressRuntimeService:
    """Apply the live dig-progress and coverage payload tick update."""

    ports: PrimitiveDigProgressRuntimePorts

    @classmethod
    def from_ports(
        cls,
        ports: PrimitiveDigProgressRuntimePorts,
    ) -> "PrimitiveDigProgressRuntimeService":
        return cls(ports=ports)

    def update(self, obs: dict[str, Any]) -> None:
        facts = self.ports.observation_facts(obs)
        mass = float(facts.mass_in_bucket_kg)
        self.ports.cycle_state.update_dig_progress(
            mass_in_bucket_kg=mass,
            plateau_epsilon_kg=float(self.ports.config.plateau_epsilon_kg),
        )
        self.ports.coverage_state.set_current_payload_gain_kg(
            max(
                float(self.ports.coverage_state.coverage_current_payload_gain_kg),
                mass,
            )
        )


__all__ = [
    "PrimitiveDigProgressRuntimeConfig",
    "PrimitiveDigProgressRuntimePorts",
    "PrimitiveDigProgressRuntimeService",
]
