"""Tick-finalization rules for primitive planner execution."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np


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
        "return_to_pre_dig_align_",
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


__all__ = [
    "PrimitivePlannerDebugState",
    "PrimitiveTickFinalizationInputs",
    "PrimitiveTickFinalizationService",
]
