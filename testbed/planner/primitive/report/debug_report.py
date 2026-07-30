"""Public debug-state report assembly for the primitive planner."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from testbed.planner.primitive.token.status import TokenStatus


@dataclass(frozen=True)
class PrimitiveDebugStateSnapshot:
    """Per-tick debug fields produced by planner tick finalization."""

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
    approach_ready_hold_count: int = 0
    dump_release_ready_hold_count: int = 0
    primitive_cycle_index: int = 0


@dataclass(frozen=True)
class PrimitiveDebugReportInputs:
    """Snapshot values required to assemble the public debug-state dict."""

    debug_state: PrimitiveDebugStateSnapshot
    transition_source: str
    transition_policy_mode: str
    transition_fallback_count: int
    transition_fallback_reason: str
    primitive_goal_curr_sector_id: int
    primitive_goal_next_sector_id: int
    token_status: TokenStatus
    dig_failed_replan_next_skill: str
    return_fields: Mapping[str, Any] = field(default_factory=dict)
    pending_fields: Mapping[str, Any] = field(default_factory=dict)
    dig_cut_fields: Mapping[str, Any] = field(default_factory=dict)
    coverage_fields: Mapping[str, Any] = field(default_factory=dict)
    cell_entry_fields: Mapping[str, Any] = field(default_factory=dict)
    scripted_bootstrap_fields: Mapping[str, Any] = field(default_factory=dict)
    dig_progress_fields: Mapping[str, Any] = field(default_factory=dict)
    pre_dig_align_fields: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PrimitiveDebugReportBuilder:
    """Build the public primitive planner debug-state payload."""

    def build(self, inputs: PrimitiveDebugReportInputs) -> dict[str, Any]:
        state = inputs.debug_state
        report: dict[str, Any] = {
            "skill_name": str(state.skill_name),
            "skill_id": int(state.skill_id),
            "skill_switch_reason": str(state.skill_switch_reason),
            "primitive_checkpoint_path": str(state.primitive_checkpoint_path),
            "hybrid_mode": str(state.hybrid_mode),
            "transition_timeout": bool(state.transition_timeout),
            "transition_completed": bool(state.transition_completed),
            "transition_source": str(inputs.transition_source),
            "transition_policy_mode": str(inputs.transition_policy_mode),
            "transition_fallback_count": int(inputs.transition_fallback_count),
            "transition_fallback_reason": str(inputs.transition_fallback_reason),
            "completed_transition_count": int(state.completed_transition_count),
            "transition_timeout_count": int(state.transition_timeout_count),
            "dump_ready_hold_count": int(state.dump_ready_hold_count),
            "dump_done_hold_count": int(state.dump_done_hold_count),
            "approach_ready_hold_count": int(state.approach_ready_hold_count),
            "dump_release_ready_hold_count": int(
                state.dump_release_ready_hold_count
            ),
            "primitive_cycle_index": int(state.primitive_cycle_index),
            "primitive_goal_curr_sector_id": int(
                inputs.primitive_goal_curr_sector_id
            ),
            "primitive_goal_next_sector_id": int(
                inputs.primitive_goal_next_sector_id
            ),
        }
        report.update(inputs.token_status.to_debug_fields())
        report["dig_failed_replan_next_skill"] = str(
            inputs.dig_failed_replan_next_skill
        )
        for section in (
            inputs.return_fields,
            inputs.pending_fields,
            inputs.dig_cut_fields,
            inputs.coverage_fields,
            inputs.cell_entry_fields,
            inputs.scripted_bootstrap_fields,
            inputs.dig_progress_fields,
            inputs.pre_dig_align_fields,
        ):
            report.update(_project_section(section))
        return report


def _project_section(section: Mapping[str, Any]) -> dict[str, Any]:
    """Return a plain debug payload copy for one report section."""

    return {str(key): deepcopy(value) for key, value in section.items()}


__all__ = [
    "PrimitiveDebugReportBuilder",
    "PrimitiveDebugReportInputs",
    "PrimitiveDebugStateSnapshot",
]
