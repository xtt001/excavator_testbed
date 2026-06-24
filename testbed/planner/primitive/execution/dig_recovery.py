"""Failed-dig and restart recovery boundary for primitive planner runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from testbed.planner.primitive.facts.capabilities import PrimitiveObservationFacts
from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.execution.cycle_state import PrimitiveCycleRuntimeState
from testbed.planner.primitive.execution.state import PrimitiveExecutionRuntimeState
from testbed.planner.primitive.execution.return_state import PrimitiveReturnRuntimeState


@dataclass(frozen=True)
class PrimitiveDigRecoveryPorts:
    """Explicit ports for failed-dig restart and recovery behavior."""

    execution_state: PrimitiveExecutionRuntimeState
    cycle_state: PrimitiveCycleRuntimeState
    return_state: PrimitiveReturnRuntimeState
    coverage_state: CoverageRuntimeState
    reset_active_policy: Callable[[], None]
    invalidate_pending_dig_cut_plan: Callable[[], None]
    clear_dig_cut_plan: Callable[[], None]
    set_skill: Callable[[str, str], None]
    record_coverage_decision_event: Callable[..., None]
    request_coverage_terminal_stop: Callable[..., None]
    observation_facts: Callable[[dict[str, Any]], PrimitiveObservationFacts]
    dig_failed_replan_next_skill: Callable[[], str]
    dig_skill_name: str = "dig"


@dataclass(frozen=True)
class PrimitiveDigRecoveryService:
    """Own failed-dig recovery and restart orchestration."""

    ports: PrimitiveDigRecoveryPorts

    @classmethod
    def from_ports(
        cls,
        ports: PrimitiveDigRecoveryPorts,
    ) -> "PrimitiveDigRecoveryService":
        return cls(ports=ports)

    def restart_dig_with_new_cut(self, reason: str) -> None:
        ports = self.ports
        ports.execution_state.set_skill_name(ports.dig_skill_name)
        ports.execution_state.set_switch_reason(str(reason))
        ports.reset_active_policy()
        ports.cycle_state.reset_dig_progress()
        ports.coverage_state.set_current_payload_gain_kg(0.0)
        ports.coverage_state.set_active_corridor_id(-1)
        ports.invalidate_pending_dig_cut_plan()
        ports.clear_dig_cut_plan()

    def stop_after_failed_dig(self, reason: str, obs: dict[str, Any]) -> None:
        ports = self.ports
        corridor = ports.coverage_state.active_corridor()
        bucket_mass = float(ports.observation_facts(obs).mass_in_bucket_kg)
        payload_gain = max(
            float(ports.coverage_state.coverage_current_payload_gain_kg),
            float(ports.cycle_state.dig_best_mass_kg),
            bucket_mass,
            0.0,
        )
        ports.execution_state.set_switch_reason(f"dig_failed_stop_{reason}")
        ports.record_coverage_decision_event(
            "failed_dig_stop",
            obs=obs,
            corridor=corridor,
            extra={
                "reason": str(reason),
                "payload_gain_kg": float(payload_gain),
                "current_bucket_mass_kg": float(bucket_mass),
                "dig_best_mass_kg": float(ports.cycle_state.dig_best_mass_kg),
                "dig_step_count": int(ports.cycle_state.dig_step_count),
            },
        )
        ports.request_coverage_terminal_stop(
            f"dig_failed_{reason}",
            replace=True,
        )

    def restart_after_failed_dig(self, reason: str, obs: dict[str, Any]) -> None:
        ports = self.ports
        if ports.dig_failed_replan_next_skill() == "stop":
            self.stop_after_failed_dig(reason, obs)
            return
        self.restart_dig_with_new_cut(f"dig_retry_{reason}")


__all__ = [
    "PrimitiveDigRecoveryPorts",
    "PrimitiveDigRecoveryService",
]
