"""Tick-finalization rules for primitive planner execution."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.planner.primitive.execution.cycle_state import (
    PrimitiveCycleReportStatus,
    PrimitiveCycleRuntimeState,
)
from testbed.planner.primitive.execution.state import PrimitiveExecutionRuntimeState
from testbed.planner.primitive.execution.return_state import PrimitiveReturnRuntimeState


@dataclass(frozen=True)
class PrimitivePlannerDebugState:
    skill_name: str
    skill_id: int
    skill_switch_reason: str
    primitive_checkpoint_path: str
    hybrid_mode: str
    transition_timeout: bool
    transition_completed: bool
    completed_transition_count: int
    transition_timeout_count: int
    dump_ready_hold_count: int
    dump_done_hold_count: int
    primitive_cycle_index: int
    approach_ready_hold_count: int = 0
    dump_release_ready_hold_count: int = 0


@dataclass(frozen=True)
class PrimitiveTickFinalizationInputs:
    """Explicit state snapshot needed to assemble compact tick debug state."""

    skill_name: str
    skill_ids: Mapping[str, int]
    skill_switch_reason: str
    primitive_checkpoint_paths: Mapping[str, str]
    first_dig_policy_active: bool
    transition_skill_names: Sequence[str]
    transition_timeout: bool
    transition_completed: bool
    completed_transition_count: int
    transition_timeout_count: int
    dump_ready_hold_count: int
    dump_done_hold_count: int
    primitive_cycle_index: int
    work_hybrid_mode: str = "WORK"
    transition_hybrid_mode: str = "TRANSITION"
    approach_ready_hold_count: int = 0
    dump_release_ready_hold_count: int = 0


@dataclass(frozen=True)
class PrimitiveTickFinalizationService:
    """Own final per-tick action-copy and compact debug-state rules."""

    transition_completed_reason_prefixes: tuple[str, ...] = (
        "return_to_dig_",
    )

    def copy_previous_action(self, action: Any) -> np.ndarray:
        return np.asarray(action).copy()

    def transition_completed_after_dispatch(self, switch_reason: str) -> bool:
        return str(switch_reason).startswith(self.transition_completed_reason_prefixes)

    def make_debug_state(
        self,
        inputs: PrimitiveTickFinalizationInputs,
    ) -> PrimitivePlannerDebugState:
        skill_name = str(inputs.skill_name)
        checkpoint_skill_name = (
            "first_dig" if bool(inputs.first_dig_policy_active) else skill_name
        )
        hybrid_mode = (
            str(inputs.transition_hybrid_mode)
            if skill_name in set(inputs.transition_skill_names)
            else str(inputs.work_hybrid_mode)
        )
        return PrimitivePlannerDebugState(
            skill_name=skill_name,
            skill_id=int(inputs.skill_ids.get(skill_name, -1)),
            skill_switch_reason=str(inputs.skill_switch_reason),
            primitive_checkpoint_path=str(
                inputs.primitive_checkpoint_paths.get(checkpoint_skill_name, "")
            ),
            hybrid_mode=hybrid_mode,
            transition_timeout=bool(inputs.transition_timeout),
            transition_completed=bool(inputs.transition_completed),
            completed_transition_count=int(inputs.completed_transition_count),
            transition_timeout_count=int(inputs.transition_timeout_count),
            dump_ready_hold_count=int(inputs.dump_ready_hold_count),
            dump_done_hold_count=int(inputs.dump_done_hold_count),
            primitive_cycle_index=int(inputs.primitive_cycle_index),
            approach_ready_hold_count=int(inputs.approach_ready_hold_count),
            dump_release_ready_hold_count=int(inputs.dump_release_ready_hold_count),
        )


@dataclass(frozen=True)
class PrimitiveTickFinalizationRuntimePorts:
    """Typed owner ports for per-tick debug finalization and return timeout."""

    execution_state: PrimitiveExecutionRuntimeState
    cycle_state: PrimitiveCycleRuntimeState
    return_state: PrimitiveReturnRuntimeState
    cycle_report_status: Callable[[], PrimitiveCycleReportStatus]
    first_dig_policy_active: Callable[[], bool]
    skill_ids: Mapping[str, int]
    primitive_checkpoint_paths: Mapping[str, str]
    transition_skill_names: Sequence[str]
    return_skill_name: str = "return"
    return_max_steps: int = 0
    work_hybrid_mode: str = "WORK"
    transition_hybrid_mode: str = "TRANSITION"


@dataclass(frozen=True)
class PrimitiveTickFinalizationRuntime:
    """Own live tick-finalization input snapshots and timeout accounting."""

    ports: PrimitiveTickFinalizationRuntimePorts
    service: PrimitiveTickFinalizationService = PrimitiveTickFinalizationService()

    @classmethod
    def from_ports(
        cls,
        ports: PrimitiveTickFinalizationRuntimePorts,
    ) -> "PrimitiveTickFinalizationRuntime":
        return cls(ports=ports)

    def finalization_inputs(
        self,
        *,
        transition_timeout: bool,
        transition_completed: bool,
    ) -> PrimitiveTickFinalizationInputs:
        ports = self.ports
        cycle_status = ports.cycle_report_status()
        return PrimitiveTickFinalizationInputs(
            skill_name=str(ports.execution_state.skill_name),
            skill_ids=ports.skill_ids,
            skill_switch_reason=str(ports.execution_state.switch_reason),
            primitive_checkpoint_paths=ports.primitive_checkpoint_paths,
            first_dig_policy_active=bool(ports.first_dig_policy_active()),
            transition_skill_names=ports.transition_skill_names,
            transition_timeout=bool(transition_timeout),
            transition_completed=bool(transition_completed),
            completed_transition_count=cycle_status.completed_transition_count,
            transition_timeout_count=cycle_status.transition_timeout_count,
            dump_ready_hold_count=cycle_status.dump_ready_hold_count,
            dump_done_hold_count=cycle_status.dump_done_hold_count,
            primitive_cycle_index=cycle_status.primitive_cycle_index,
            work_hybrid_mode=str(ports.work_hybrid_mode),
            transition_hybrid_mode=str(ports.transition_hybrid_mode),
        )

    def make_debug_state(
        self,
        *,
        transition_timeout: bool,
        transition_completed: bool,
    ) -> PrimitivePlannerDebugState:
        return self.service.make_debug_state(
            self.finalization_inputs(
                transition_timeout=transition_timeout,
                transition_completed=transition_completed,
            )
        )

    def finalize_debug_state(
        self,
        *,
        transition_timeout: bool,
        transition_completed: bool,
    ) -> None:
        self.ports.execution_state.set_debug_state(
            self.make_debug_state(
                transition_timeout=transition_timeout,
                transition_completed=transition_completed,
            )
        )

    def account_return_timeout(self) -> bool:
        ports = self.ports
        if str(ports.execution_state.skill_name) != str(ports.return_skill_name):
            return False

        ports.return_state.return_step_count += 1
        if (
            int(ports.return_max_steps) > 0
            and ports.return_state.return_step_count >= int(ports.return_max_steps)
        ):
            ports.cycle_state.increment_transition_timeout_count()
            return True
        return False


__all__ = [
    "PrimitivePlannerDebugState",
    "PrimitiveTickFinalizationInputs",
    "PrimitiveTickFinalizationRuntime",
    "PrimitiveTickFinalizationRuntimePorts",
    "PrimitiveTickFinalizationService",
]
