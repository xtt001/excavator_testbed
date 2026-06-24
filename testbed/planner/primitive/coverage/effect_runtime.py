"""Coverage effect and update composition runtime."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from testbed.planner.primitive.facts.capabilities import PrimitiveObservationFacts
from testbed.planner.primitive.coverage.config import PrimitiveCoverageStaticConfig
from testbed.planner.primitive.coverage.selection import CoverageCorridorState
from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.coverage.effects import (
    CoverageEffectRuntimeCoordinator,
    CoverageEffectRuntimePorts,
    CoverageRuntimeConfig,
    CoverageRuntimeService,
    CoverageUpdateConfig,
    CoverageUpdateService,
)
from testbed.planner.primitive.execution.cycle_state import PrimitiveCycleRuntimeState


@dataclass(frozen=True)
class PrimitiveCoverageEffectRuntimePorts:
    """Typed coverage effect/update composition ports."""

    state: CoverageRuntimeState
    cycle_state: PrimitiveCycleRuntimeState
    static_config: PrimitiveCoverageStaticConfig
    observation_facts: Callable[[dict[str, Any]], PrimitiveObservationFacts]
    remaining_depth: Callable[[dict[str, Any], CoverageCorridorState], float]
    corridor_attempt_limit: Callable[[CoverageCorridorState], int]
    record_decision_event: Callable[..., None]


@dataclass(frozen=True)
class PrimitiveCoverageEffectRuntime:
    """Compose coverage effect/update configs, services, and coordinator ports."""

    ports: PrimitiveCoverageEffectRuntimePorts

    @classmethod
    def from_ports(
        cls,
        ports: PrimitiveCoverageEffectRuntimePorts,
    ) -> "PrimitiveCoverageEffectRuntime":
        return cls(ports=ports)

    def coverage_update_config(self) -> CoverageUpdateConfig:
        return self.ports.static_config.update_config()

    def coverage_update_service(self) -> CoverageUpdateService:
        return CoverageUpdateService(self.coverage_update_config())

    def coverage_runtime_config(self) -> CoverageRuntimeConfig:
        return self.ports.static_config.runtime_config()

    def coverage_runtime_service(self) -> CoverageRuntimeService:
        return CoverageRuntimeService(self.coverage_runtime_config())

    def coverage_effect_runtime_ports(self) -> CoverageEffectRuntimePorts:
        ports = self.ports
        return CoverageEffectRuntimePorts(
            state=ports.state,
            cycle_state=ports.cycle_state,
            coverage_mode=lambda: str(ports.static_config.dig_cut_planner_mode),
            coverage_update_service=lambda: self.coverage_update_service(),
            coverage_runtime_service=lambda: self.coverage_runtime_service(),
            observation_facts=ports.observation_facts,
            remaining_depth=ports.remaining_depth,
            corridor_attempt_limit=ports.corridor_attempt_limit,
            record_decision_event=ports.record_decision_event,
            coverage_global_low_productivity_stop=(
                lambda: int(ports.static_config.global_low_productivity_stop)
            ),
            coverage_low_productivity_payload_kg=(
                lambda: float(ports.static_config.low_productivity_payload_kg)
            ),
            coverage_low_productivity_deposit_kg=(
                lambda: float(ports.static_config.low_productivity_deposit_kg)
            ),
        )

    def coverage_effect_runtime_coordinator(self) -> CoverageEffectRuntimeCoordinator:
        return CoverageEffectRuntimeCoordinator.from_ports(
            self.coverage_effect_runtime_ports()
        )

    def complete_coverage_dig(self, obs: dict[str, Any]) -> None:
        self.coverage_effect_runtime_coordinator().complete_dig(obs)

    def complete_coverage_dump(self, obs: dict[str, Any], *, reason: str) -> None:
        self.coverage_effect_runtime_coordinator().complete_dump(
            obs,
            reason=reason,
        )

    def reject_active_coverage_corridor(
        self,
        obs: dict[str, Any],
        *,
        reason: str,
    ) -> None:
        self.coverage_effect_runtime_coordinator().reject_active_corridor(
            obs,
            reason=reason,
        )

    def update_corridor_belief(
        self,
        corridor: CoverageCorridorState,
        *,
        payload_gain_kg: float,
        effective_deposit_delta_kg: float,
    ) -> None:
        self.coverage_update_service().update_belief(
            corridor,
            payload_gain_kg=payload_gain_kg,
            effective_deposit_delta_kg=effective_deposit_delta_kg,
        )

    def maybe_reopen_coverage_pass(
        self,
        obs: dict[str, Any],
        *,
        reason: str,
    ) -> bool:
        return self.coverage_effect_runtime_coordinator().maybe_reopen_pass(
            obs,
            reason=reason,
        )

    def request_coverage_terminal_stop(
        self,
        reason: str,
        *,
        replace: bool = False,
    ) -> None:
        self.coverage_effect_runtime_coordinator().request_terminal_stop(
            reason,
            replace=replace,
        )


__all__ = [
    "PrimitiveCoverageEffectRuntime",
    "PrimitiveCoverageEffectRuntimePorts",
]
