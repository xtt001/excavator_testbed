"""Primitive skill switch lifecycle sequencing."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from testbed.planner.primitive_coverage_state import CoverageRuntimeState
from testbed.planner.primitive_cycle_state import PrimitiveCycleRuntimeState
from testbed.planner.primitive_execution_state import PrimitiveExecutionRuntimeState
from testbed.planner.primitive_pre_dig_align_state import (
    PrimitivePreDigAlignCompatibilityRuntimeState,
)
from testbed.planner.primitive_return_state import PrimitiveReturnRuntimeState


@dataclass(frozen=True)
class PrimitiveSkillLifecyclePorts:
    """Shell-owned state ports used by primitive skill lifecycle service."""

    execution_state: PrimitiveExecutionRuntimeState
    cycle_state: PrimitiveCycleRuntimeState
    return_state: PrimitiveReturnRuntimeState
    pre_dig_align_state: PrimitivePreDigAlignCompatibilityRuntimeState
    coverage_state: CoverageRuntimeState
    reset_active_policy: Callable[[], None]
    clear_dig_cut_plan: Callable[[], None]
    pre_dig_align_skill_name: str = "pre_dig_align"


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
        if target_skill != str(ports.pre_dig_align_skill_name):
            ports.reset_active_policy()

        if target_skill == "carry":
            ports.cycle_state.set_dump_ready_hold_count(0)
        elif target_skill == "dump":
            ports.cycle_state.set_dump_done_hold_count(0)
        elif target_skill == "return":
            ports.return_state.return_step_count = 0
            ports.return_state.clear_next_dig_event_seen()
        elif target_skill == str(ports.pre_dig_align_skill_name):
            self._reset_pre_dig_align()
        elif target_skill == "dig":
            self._reset_dig()

        if target_skill not in {"dig", str(ports.pre_dig_align_skill_name)}:
            ports.clear_dig_cut_plan()

    def _reset_pre_dig_align(self) -> None:
        state = self.ports.pre_dig_align_state
        state.step_count = 0
        state.hold_count = 0
        state.entry_close_handoff_ready = False
        state.entry_intent_handoff_ready = False
        state.timeout_handoff_reason = ""
        state.surface_guard_triggered = False

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
