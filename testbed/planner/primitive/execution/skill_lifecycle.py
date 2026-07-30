"""Primitive skill switch lifecycle sequencing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.execution.cycle_state import PrimitiveCycleRuntimeState
from testbed.planner.primitive.execution.state import PrimitiveExecutionRuntimeState
from testbed.planner.primitive.execution.return_state import PrimitiveReturnRuntimeState


@dataclass(frozen=True)
class PrimitiveSkillLifecyclePorts:
    """Shell-owned state ports used by primitive skill lifecycle service."""

    execution_state: PrimitiveExecutionRuntimeState
    cycle_state: PrimitiveCycleRuntimeState
    return_state: PrimitiveReturnRuntimeState
    coverage_state: CoverageRuntimeState
    reset_active_policy: Callable[[], None]
    clear_dig_cut_plan: Callable[[], None]


@dataclass(frozen=True)
class PrimitiveSkillLifecycleService:
    """Own 4P primitive skill switch lifecycle ordering."""

    ports: PrimitiveSkillLifecyclePorts

    @classmethod
    def from_ports(
        cls,
        ports: PrimitiveSkillLifecyclePorts,
    ) -> "PrimitiveSkillLifecycleService":
        return cls(ports=ports)

    def set_skill(self, skill_name: str, reason: str) -> None:
        ports = self.ports
        target_skill = str(skill_name)
        if target_skill == str(ports.execution_state.skill_name):
            return

        ports.execution_state.set_skill_name(target_skill)
        ports.execution_state.set_switch_reason(str(reason))
        ports.reset_active_policy()
        self._reset_skill_state(target_skill)

    def restart_skill(self, reason: str) -> None:
        """Restart the current primitive even when its skill name is unchanged."""

        ports = self.ports
        target_skill = str(ports.execution_state.skill_name)
        ports.execution_state.set_switch_reason(str(reason))
        ports.reset_active_policy()
        self._reset_skill_state(target_skill)

    def _reset_skill_state(self, target_skill: str) -> None:
        ports = self.ports
        if target_skill == "carry":
            ports.cycle_state.set_dump_ready_hold_count(0)
        elif target_skill == "dump":
            ports.cycle_state.set_dump_done_hold_count(0)
        elif target_skill == "return":
            ports.return_state.return_step_count = 0
            ports.return_state.clear_next_dig_event_seen()
        elif target_skill == "dig":
            self._reset_dig()

        if target_skill != "dig":
            ports.clear_dig_cut_plan()

    def _reset_dig(self) -> None:
        ports = self.ports
        ports.return_state.clear_next_dig_event_seen()
        ports.cycle_state.set_dump_ready_hold_count(0)
        ports.cycle_state.set_dump_done_hold_count(0)
        ports.coverage_state.set_current_payload_gain_kg(0.0)
        ports.cycle_state.reset_dig_progress()


__all__ = [
    "PrimitiveSkillLifecyclePorts",
    "PrimitiveSkillLifecycleService",
]
