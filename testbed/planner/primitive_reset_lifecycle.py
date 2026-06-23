"""Reset lifecycle rules for primitive planner public adapter."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.planner.cell_entry import CELL_ENTRY_TOKEN_DIM
from testbed.planner.primitive_coverage_state import CoverageRuntimeState
from testbed.planner.primitive_cycle_state import PrimitiveCycleRuntimeState
from testbed.planner.primitive_return_state import PrimitiveReturnRuntimeState
from testbed.planner.primitive_token_state import PrimitiveTokenRuntimeState


@dataclass(frozen=True)
class PrimitiveResetLifecyclePorts:
    """Shell-owned reset hooks and read-only configuration snapshot."""

    all_policies: Callable[[], Sequence[Any]]
    reset_boundary_detector: Callable[[], None]
    reset_cell_entry_planner: Callable[[], None]
    bootstrap_end_mode: Callable[[], str]
    bootstrap_policy_available: Callable[[], bool]
    scripted_bootstrap_enabled: Callable[[], bool]
    should_pre_dig_align_before_dig: Callable[[], bool]
    action_dim: int
    bootstrap_skill_name: str = "bootstrap"
    pre_dig_align_skill_name: str = "pre_dig_align"
    dig_skill_name: str = "dig"


@dataclass
class PrimitiveResetLifecycleState:
    """Complete shell state snapshot produced by the reset lifecycle."""

    skill_name: str
    prev_action: np.ndarray | None
    switch_reason: str
    cycle_state: PrimitiveCycleRuntimeState
    dump_ready_hold_count: int
    dump_done_hold_count: int
    return_step_count: int
    scripted_bootstrap_step_count: int
    scripted_bootstrap_hold_count: int
    scripted_bootstrap_timeout_count: int
    pre_dig_align_step_count: int
    pre_dig_align_hold_count: int
    pre_dig_align_timeout_count: int
    pre_dig_align_completed_count: int
    pre_dig_align_replan_count: int
    pre_dig_align_target_qpos: np.ndarray
    pre_dig_align_error: np.ndarray
    pre_dig_align_entry_error_m: float
    pre_dig_align_start_envelope_ready: bool
    pre_dig_align_entry_close_handoff_ready: bool
    pre_dig_align_entry_intent_handoff_ready: bool
    pre_dig_align_timeout_handoff_reason: str
    pre_dig_align_surface_depth_m: float
    pre_dig_align_surface_guard_triggered: bool
    pre_dig_align_surface_guard_count: int
    dig_step_count: int
    dig_best_mass_kg: float
    dig_mass_plateau_count: int
    dig_to_carry_reason: str
    dig_bad_replan_count: int
    dig_exit_guard_replan_count: int
    completed_transition_count: int
    transition_timeout_count: int
    return_state: PrimitiveReturnRuntimeState
    cycle_index: int
    dump_start_deposited_mass_kg: float
    cell_entry_goal: Any | None
    cell_entry_goal_cycle_id: int
    cell_entry_audit: Any | None
    cell_entry_tokens: np.ndarray
    cell_entry_token_injected: bool
    token_state: PrimitiveTokenRuntimeState
    dig_cut_tokens: np.ndarray
    dig_cut_token_injected: bool
    dig_depth_profile_tokens: np.ndarray
    dig_depth_profile_token_injected: bool
    dig_depth_profile_token_source: str
    dig_depth_profile_fallback_reason: str
    return_target_tokens: np.ndarray
    return_target_token_injected: bool
    return_relocate_tokens: np.ndarray
    return_relocate_token_injected: bool
    return_start_envelope_tokens: np.ndarray
    return_start_envelope_token_injected: bool
    return_start_envelope_token_source: str
    return_start_envelope_use_prior_spatial_bounds: bool
    return_start_envelope_use_prior_qpos_bounds: bool
    return_target_planned_cycle_id: int
    return_target_token_source: str
    return_target_fallback_reason: str
    return_to_dig_entry_error_m: float
    return_to_dig_entry_close_state: bool
    return_next_dig_event_seen: bool
    return_to_dig_start_envelope_ready_state: bool
    return_to_dig_start_envelope_error: float
    return_to_dig_start_envelope_checks: dict[str, Any]
    pending_dig_cut_cycle_id: int
    pending_dig_cut_corridor_id: int
    pending_dig_cut_raw_fields: dict[str, float | int] | None
    pending_dig_cut_tokens: np.ndarray | None
    pending_dig_depth_profile_tokens: np.ndarray | None
    pending_dig_state_exemplar_ids: list[str]
    pending_dig_state_exemplar_distance: float
    cell_entry_seen_cell_id: int
    cell_entry_trace: list[dict[str, Any]]
    dig_cut_planned_cycle_id: int
    dig_cut_token_source: str
    dig_cut_fallback_reason: str
    dig_cut_token_in_prior_p10_p90: bool
    coverage_state: CoverageRuntimeState
    debug_transition_timeout: bool
    debug_transition_completed: bool

    def as_policy_field_updates(self) -> dict[str, Any]:
        """Map reset state to the legacy private field names owned by policy."""

        return {
            "_skill_name": self.skill_name,
            "_prev_action": self.prev_action,
            "_switch_reason": self.switch_reason,
            "_cycle_state": self.cycle_state,
            "_dump_ready_hold_count": self.dump_ready_hold_count,
            "_dump_done_hold_count": self.dump_done_hold_count,
            "_return_step_count": self.return_step_count,
            "_scripted_bootstrap_step_count": self.scripted_bootstrap_step_count,
            "_scripted_bootstrap_hold_count": self.scripted_bootstrap_hold_count,
            "_scripted_bootstrap_timeout_count": self.scripted_bootstrap_timeout_count,
            "_pre_dig_align_step_count": self.pre_dig_align_step_count,
            "_pre_dig_align_hold_count": self.pre_dig_align_hold_count,
            "_pre_dig_align_timeout_count": self.pre_dig_align_timeout_count,
            "_pre_dig_align_completed_count": self.pre_dig_align_completed_count,
            "_pre_dig_align_replan_count": self.pre_dig_align_replan_count,
            "_pre_dig_align_target_qpos": self.pre_dig_align_target_qpos,
            "_pre_dig_align_error": self.pre_dig_align_error,
            "_pre_dig_align_entry_error_m": self.pre_dig_align_entry_error_m,
            "_pre_dig_align_start_envelope_ready": (
                self.pre_dig_align_start_envelope_ready
            ),
            "_pre_dig_align_entry_close_handoff_ready": (
                self.pre_dig_align_entry_close_handoff_ready
            ),
            "_pre_dig_align_entry_intent_handoff_ready": (
                self.pre_dig_align_entry_intent_handoff_ready
            ),
            "_pre_dig_align_timeout_handoff_reason": (
                self.pre_dig_align_timeout_handoff_reason
            ),
            "_pre_dig_align_surface_depth_m": self.pre_dig_align_surface_depth_m,
            "_pre_dig_align_surface_guard_triggered": (
                self.pre_dig_align_surface_guard_triggered
            ),
            "_pre_dig_align_surface_guard_count": (
                self.pre_dig_align_surface_guard_count
            ),
            "_dig_step_count": self.dig_step_count,
            "_dig_best_mass_kg": self.dig_best_mass_kg,
            "_dig_mass_plateau_count": self.dig_mass_plateau_count,
            "_dig_to_carry_reason": self.dig_to_carry_reason,
            "_dig_bad_replan_count": self.dig_bad_replan_count,
            "_dig_exit_guard_replan_count": self.dig_exit_guard_replan_count,
            "_completed_transition_count": self.completed_transition_count,
            "_transition_timeout_count": self.transition_timeout_count,
            "_return_state": self.return_state,
            "_cycle_index": self.cycle_index,
            "_dump_start_deposited_mass_kg": self.dump_start_deposited_mass_kg,
            "_cell_entry_goal": self.cell_entry_goal,
            "_cell_entry_goal_cycle_id": self.cell_entry_goal_cycle_id,
            "_cell_entry_audit": self.cell_entry_audit,
            "_cell_entry_tokens": self.cell_entry_tokens,
            "_cell_entry_token_injected": self.cell_entry_token_injected,
            "_token_state": self.token_state,
            "_dig_cut_tokens": self.dig_cut_tokens,
            "_dig_cut_token_injected": self.dig_cut_token_injected,
            "_dig_depth_profile_tokens": self.dig_depth_profile_tokens,
            "_dig_depth_profile_token_injected": (
                self.dig_depth_profile_token_injected
            ),
            "_dig_depth_profile_token_source": self.dig_depth_profile_token_source,
            "_dig_depth_profile_fallback_reason": (
                self.dig_depth_profile_fallback_reason
            ),
            "_return_target_tokens": self.return_target_tokens,
            "_return_target_token_injected": self.return_target_token_injected,
            "_return_relocate_tokens": self.return_relocate_tokens,
            "_return_relocate_token_injected": self.return_relocate_token_injected,
            "_return_start_envelope_tokens": self.return_start_envelope_tokens,
            "_return_start_envelope_token_injected": (
                self.return_start_envelope_token_injected
            ),
            "_return_start_envelope_token_source": (
                self.return_start_envelope_token_source
            ),
            "_return_start_envelope_use_prior_spatial_bounds": (
                self.return_start_envelope_use_prior_spatial_bounds
            ),
            "_return_start_envelope_use_prior_qpos_bounds": (
                self.return_start_envelope_use_prior_qpos_bounds
            ),
            "_return_target_planned_cycle_id": self.return_target_planned_cycle_id,
            "_return_target_token_source": self.return_target_token_source,
            "_return_target_fallback_reason": self.return_target_fallback_reason,
            "_return_to_dig_entry_error_m": self.return_to_dig_entry_error_m,
            "_return_to_dig_entry_close_state": self.return_to_dig_entry_close_state,
            "_return_next_dig_event_seen": self.return_next_dig_event_seen,
            "_return_to_dig_start_envelope_ready_state": (
                self.return_to_dig_start_envelope_ready_state
            ),
            "_return_to_dig_start_envelope_error": (
                self.return_to_dig_start_envelope_error
            ),
            "_return_to_dig_start_envelope_checks": (
                self.return_to_dig_start_envelope_checks
            ),
            "_pending_dig_cut_cycle_id": self.pending_dig_cut_cycle_id,
            "_pending_dig_cut_corridor_id": self.pending_dig_cut_corridor_id,
            "_pending_dig_cut_raw_fields": self.pending_dig_cut_raw_fields,
            "_pending_dig_cut_tokens": self.pending_dig_cut_tokens,
            "_pending_dig_depth_profile_tokens": (
                self.pending_dig_depth_profile_tokens
            ),
            "_pending_dig_state_exemplar_ids": self.pending_dig_state_exemplar_ids,
            "_pending_dig_state_exemplar_distance": (
                self.pending_dig_state_exemplar_distance
            ),
            "_cell_entry_seen_cell_id": self.cell_entry_seen_cell_id,
            "_cell_entry_trace": self.cell_entry_trace,
            "_dig_cut_planned_cycle_id": self.dig_cut_planned_cycle_id,
            "_dig_cut_token_source": self.dig_cut_token_source,
            "_dig_cut_fallback_reason": self.dig_cut_fallback_reason,
            "_dig_cut_token_in_prior_p10_p90": (
                self.dig_cut_token_in_prior_p10_p90
            ),
            "_coverage_state": self.coverage_state,
        }


@dataclass(frozen=True)
class PrimitiveResetLifecycleService:
    """Own reset sequencing and legacy 4P reset-state defaults."""

    ports: PrimitiveResetLifecyclePorts

    @classmethod
    def from_ports(
        cls,
        ports: PrimitiveResetLifecyclePorts,
    ) -> "PrimitiveResetLifecycleService":
        return cls(ports=ports)

    def reset(self) -> PrimitiveResetLifecycleState:
        ports = self.ports
        for policy in ports.all_policies():
            policy.reset()
        ports.reset_boundary_detector()
        skill_name = self._initial_skill_name()
        ports.reset_cell_entry_planner()
        action_dim = int(ports.action_dim)
        cycle_state = PrimitiveCycleRuntimeState.fresh()
        token_state = PrimitiveTokenRuntimeState.fresh()
        return_state = PrimitiveReturnRuntimeState.fresh()
        return PrimitiveResetLifecycleState(
            skill_name=skill_name,
            prev_action=None,
            switch_reason="reset",
            cycle_state=cycle_state,
            dump_ready_hold_count=cycle_state.dump_ready_hold_count,
            dump_done_hold_count=cycle_state.dump_done_hold_count,
            return_step_count=return_state.return_step_count,
            scripted_bootstrap_step_count=0,
            scripted_bootstrap_hold_count=0,
            scripted_bootstrap_timeout_count=0,
            pre_dig_align_step_count=0,
            pre_dig_align_hold_count=0,
            pre_dig_align_timeout_count=0,
            pre_dig_align_completed_count=0,
            pre_dig_align_replan_count=0,
            pre_dig_align_target_qpos=np.zeros(action_dim, dtype=np.float32),
            pre_dig_align_error=np.zeros(action_dim, dtype=np.float32),
            pre_dig_align_entry_error_m=float("nan"),
            pre_dig_align_start_envelope_ready=False,
            pre_dig_align_entry_close_handoff_ready=False,
            pre_dig_align_entry_intent_handoff_ready=False,
            pre_dig_align_timeout_handoff_reason="",
            pre_dig_align_surface_depth_m=float("nan"),
            pre_dig_align_surface_guard_triggered=False,
            pre_dig_align_surface_guard_count=0,
            dig_step_count=cycle_state.dig_step_count,
            dig_best_mass_kg=cycle_state.dig_best_mass_kg,
            dig_mass_plateau_count=cycle_state.dig_mass_plateau_count,
            dig_to_carry_reason=cycle_state.dig_to_carry_reason,
            dig_bad_replan_count=cycle_state.dig_bad_replan_count,
            dig_exit_guard_replan_count=cycle_state.dig_exit_guard_replan_count,
            completed_transition_count=cycle_state.completed_transition_count,
            transition_timeout_count=cycle_state.transition_timeout_count,
            return_state=return_state,
            cycle_index=cycle_state.cycle_index,
            dump_start_deposited_mass_kg=(
                cycle_state.dump_start_deposited_mass_kg
            ),
            cell_entry_goal=None,
            cell_entry_goal_cycle_id=-1,
            cell_entry_audit=None,
            cell_entry_tokens=np.zeros(CELL_ENTRY_TOKEN_DIM, dtype=np.float32),
            cell_entry_token_injected=False,
            token_state=token_state,
            dig_cut_tokens=token_state.dig_cut_tokens,
            dig_cut_token_injected=False,
            dig_depth_profile_tokens=token_state.dig_depth_profile_tokens,
            dig_depth_profile_token_injected=False,
            dig_depth_profile_token_source=token_state.dig_depth_profile_token_source,
            dig_depth_profile_fallback_reason=(
                token_state.dig_depth_profile_fallback_reason
            ),
            return_target_tokens=token_state.return_target_tokens,
            return_target_token_injected=False,
            return_relocate_tokens=token_state.return_relocate_tokens,
            return_relocate_token_injected=False,
            return_start_envelope_tokens=token_state.return_start_envelope_tokens,
            return_start_envelope_token_injected=False,
            return_start_envelope_token_source=(
                token_state.return_start_envelope_token_source
            ),
            return_start_envelope_use_prior_spatial_bounds=(
                token_state.return_start_envelope_use_prior_spatial_bounds
            ),
            return_start_envelope_use_prior_qpos_bounds=(
                token_state.return_start_envelope_use_prior_qpos_bounds
            ),
            return_target_planned_cycle_id=token_state.return_target_planned_cycle_id,
            return_target_token_source=token_state.return_target_token_source,
            return_target_fallback_reason=token_state.return_target_fallback_reason,
            return_to_dig_entry_error_m=return_state.return_to_dig_entry_error_m,
            return_to_dig_entry_close_state=(
                return_state.return_to_dig_entry_close_state
            ),
            return_next_dig_event_seen=return_state.return_next_dig_event_seen,
            return_to_dig_start_envelope_ready_state=(
                return_state.return_to_dig_start_envelope_ready_state
            ),
            return_to_dig_start_envelope_error=(
                return_state.return_to_dig_start_envelope_error
            ),
            return_to_dig_start_envelope_checks=(
                return_state.return_to_dig_start_envelope_checks
            ),
            pending_dig_cut_cycle_id=token_state.pending_dig_cut_cycle_id,
            pending_dig_cut_corridor_id=token_state.pending_dig_cut_corridor_id,
            pending_dig_cut_raw_fields=token_state.pending_dig_cut_raw_fields,
            pending_dig_cut_tokens=token_state.pending_dig_cut_tokens,
            pending_dig_depth_profile_tokens=(
                token_state.pending_dig_depth_profile_tokens
            ),
            pending_dig_state_exemplar_ids=(
                token_state.pending_dig_state_exemplar_ids
            ),
            pending_dig_state_exemplar_distance=(
                token_state.pending_dig_state_exemplar_distance
            ),
            cell_entry_seen_cell_id=-1,
            cell_entry_trace=[],
            dig_cut_planned_cycle_id=token_state.dig_cut_planned_cycle_id,
            dig_cut_token_source=token_state.dig_cut_token_source,
            dig_cut_fallback_reason=token_state.dig_cut_fallback_reason,
            dig_cut_token_in_prior_p10_p90=(
                token_state.dig_cut_token_in_prior_p10_p90
            ),
            coverage_state=CoverageRuntimeState(),
            debug_transition_timeout=False,
            debug_transition_completed=False,
        )

    def _initial_skill_name(self) -> str:
        ports = self.ports
        has_bootstrap = (
            str(ports.bootstrap_end_mode()) != "disabled"
            and (
                bool(ports.bootstrap_policy_available())
                or bool(ports.scripted_bootstrap_enabled())
            )
        )
        if has_bootstrap:
            return str(ports.bootstrap_skill_name)
        if bool(ports.should_pre_dig_align_before_dig()):
            return str(ports.pre_dig_align_skill_name)
        return str(ports.dig_skill_name)


__all__ = [
    "PrimitiveResetLifecyclePorts",
    "PrimitiveResetLifecycleService",
    "PrimitiveResetLifecycleState",
]
