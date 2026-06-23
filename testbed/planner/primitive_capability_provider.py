"""Primitive FSM transition-status provider wiring."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.planner.primitive_capabilities import (
    CarryTransitionStatus,
    DigTransitionStatus,
    DumpTransitionStatus,
    PrimitiveObservationFacts,
    ReturnTransitionStatus,
)
from testbed.planner.primitive_coverage_state import CoverageRuntimeState
from testbed.planner.primitive_cycle_state import PrimitiveCycleRuntimeState
from testbed.planner.primitive_return_state import PrimitiveReturnRuntimeState


@dataclass(frozen=True)
class PrimitiveFSMCapabilityProviderPorts:
    """Read-only shell ports for primitive FSM transition status assembly."""

    action_dim: int
    semantic_boundary_profile_active: Callable[[], bool]
    cycle_state: PrimitiveCycleRuntimeState
    coverage_state: CoverageRuntimeState
    return_state: PrimitiveReturnRuntimeState
    dig_to_carry_min_distance_to_dig_area_m: float
    dig_to_carry_min_bucket_mass_kg: float
    dig_to_carry_target_bucket_mass_kg: float
    dig_to_carry_mass_plateau_enabled: bool
    dig_to_carry_mass_plateau_min_bucket_mass_kg: float
    dig_to_carry_mass_plateau_hold_steps: int
    dig_to_carry_mass_plateau_min_steps: int
    dump_ready_min_bucket_mass_kg: float
    dig_bad_replan_enabled: bool
    dig_bad_replan_max_steps: int
    dig_bad_replan_min_bucket_mass_kg: float
    dig_exit_guard_enabled: bool
    dig_exit_guard_min_steps: int
    dig_exit_guard_min_bucket_mass_kg: float
    dig_exit_guard_overshoot_m: float
    dump_ready_hold_steps: int
    dump_ready_min_height_above_rim_m: float
    dump_ready_require_over_footprint: bool
    dump_ready_require_clearance: bool
    dump_ready_max_horizontal_distance_m: float | None
    dump_ready_position_mode: str
    dump_ready_max_dump_area_footprint_outside_distance_m: float | None
    dump_ready_min_dump_area_relative_x_m: float | None
    dump_ready_max_dump_area_relative_x_m: float | None
    dump_ready_min_dump_area_relative_z_m: float | None
    dump_ready_max_dump_area_relative_z_m: float | None
    dump_ready_near_window_enabled: bool
    dump_ready_near_window_x_tolerance_m: float
    dump_ready_near_window_z_tolerance_m: float
    dump_ready_near_window_outside_tolerance_m: float
    dump_ready_near_window_require_over_footprint: bool
    dump_done_max_bucket_mass_kg: float
    dump_done_min_deposit_delta_kg: float
    dump_done_use_boundary_event: bool
    dump_done_hold_steps: int
    refresh_return_handoff_state: Callable[[dict[str, Any]], None]
    pre_dig_align_before_dig: Callable[[], bool]
    return_to_dig_start_envelope_direct_handoff_enabled: bool
    return_to_dig_start_envelope_gate_enabled: bool
    return_to_dig_shallow_guard_enabled: bool
    return_to_dig_max_bucket_mass_kg: float
    return_to_dig_touch_tolerance_m: float
    return_to_dig_min_depth_m: float
    return_to_dig_max_depth_m: float
    return_to_dig_max_entry_error_m: float | None


@dataclass(frozen=True)
class PrimitiveFSMCapabilityProvider:
    """Build read-only FSM transition statuses from shell ports and observations."""

    ports: PrimitiveFSMCapabilityProviderPorts

    @classmethod
    def from_ports(
        cls,
        ports: PrimitiveFSMCapabilityProviderPorts,
    ) -> "PrimitiveFSMCapabilityProvider":
        return cls(ports=ports)

    def dig_transition_status(
        self,
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> DigTransitionStatus:
        ports = self.ports
        observation = self._observation(obs)
        return DigTransitionStatus.from_inputs(
            observation=observation,
            boundary_event=boundary_event,
            semantic_boundary_profile_active=(
                ports.semantic_boundary_profile_active()
            ),
            coverage_terminal_stop_requested=(
                ports.coverage_state.coverage_terminal_stop_requested
            ),
            dig_step_count=ports.cycle_state.dig_step_count,
            dig_mass_plateau_count=ports.cycle_state.dig_mass_plateau_count,
            dig_to_carry_min_distance_to_dig_area_m=(
                ports.dig_to_carry_min_distance_to_dig_area_m
            ),
            dig_to_carry_min_bucket_mass_kg=(
                ports.dig_to_carry_min_bucket_mass_kg
            ),
            dig_to_carry_target_bucket_mass_kg=(
                ports.dig_to_carry_target_bucket_mass_kg
            ),
            dig_to_carry_mass_plateau_enabled=(
                ports.dig_to_carry_mass_plateau_enabled
            ),
            dig_to_carry_mass_plateau_min_bucket_mass_kg=(
                ports.dig_to_carry_mass_plateau_min_bucket_mass_kg
            ),
            dig_to_carry_mass_plateau_hold_steps=(
                ports.dig_to_carry_mass_plateau_hold_steps
            ),
            dig_to_carry_mass_plateau_min_steps=(
                ports.dig_to_carry_mass_plateau_min_steps
            ),
            dump_ready_min_bucket_mass_kg=ports.dump_ready_min_bucket_mass_kg,
            dig_bad_replan_enabled=ports.dig_bad_replan_enabled,
            dig_bad_replan_max_steps=ports.dig_bad_replan_max_steps,
            dig_bad_replan_min_bucket_mass_kg=(
                ports.dig_bad_replan_min_bucket_mass_kg
            ),
            dig_exit_guard_enabled=ports.dig_exit_guard_enabled,
            dig_exit_guard_min_steps=ports.dig_exit_guard_min_steps,
            dig_exit_guard_min_bucket_mass_kg=(
                ports.dig_exit_guard_min_bucket_mass_kg
            ),
            dig_exit_guard_overshoot_m=ports.dig_exit_guard_overshoot_m,
            dig_exit_overshoot_m=self._dig_exit_overshoot_m(observation),
        )

    def sync_dig_transition_reason(
        self,
        status: DigTransitionStatus,
    ) -> None:
        self.ports.cycle_state.dig_to_carry_reason = str(
            status.dig_to_carry_reason
        )

    def carry_transition_status(
        self,
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> CarryTransitionStatus:
        ports = self.ports
        return CarryTransitionStatus.from_inputs(
            observation=self._observation(obs),
            boundary_event=boundary_event,
            semantic_boundary_profile_active=(
                ports.semantic_boundary_profile_active()
            ),
            coverage_cycle_start_deposit_kg=(
                ports.coverage_state.coverage_cycle_start_deposit_kg
            ),
            dump_ready_hold_count=ports.cycle_state.dump_ready_hold_count,
            dump_ready_hold_steps=ports.dump_ready_hold_steps,
            dump_ready_min_bucket_mass_kg=ports.dump_ready_min_bucket_mass_kg,
            dump_ready_min_height_above_rim_m=(
                ports.dump_ready_min_height_above_rim_m
            ),
            dump_ready_require_over_footprint=(
                ports.dump_ready_require_over_footprint
            ),
            dump_ready_require_clearance=ports.dump_ready_require_clearance,
            dump_ready_max_horizontal_distance_m=(
                ports.dump_ready_max_horizontal_distance_m
            ),
            dump_ready_position_mode=ports.dump_ready_position_mode,
            dump_ready_max_dump_area_footprint_outside_distance_m=(
                ports.dump_ready_max_dump_area_footprint_outside_distance_m
            ),
            dump_ready_min_dump_area_relative_x_m=(
                ports.dump_ready_min_dump_area_relative_x_m
            ),
            dump_ready_max_dump_area_relative_x_m=(
                ports.dump_ready_max_dump_area_relative_x_m
            ),
            dump_ready_min_dump_area_relative_z_m=(
                ports.dump_ready_min_dump_area_relative_z_m
            ),
            dump_ready_max_dump_area_relative_z_m=(
                ports.dump_ready_max_dump_area_relative_z_m
            ),
            dump_ready_near_window_enabled=ports.dump_ready_near_window_enabled,
            dump_ready_near_window_x_tolerance_m=(
                ports.dump_ready_near_window_x_tolerance_m
            ),
            dump_ready_near_window_z_tolerance_m=(
                ports.dump_ready_near_window_z_tolerance_m
            ),
            dump_ready_near_window_outside_tolerance_m=(
                ports.dump_ready_near_window_outside_tolerance_m
            ),
            dump_ready_near_window_require_over_footprint=(
                ports.dump_ready_near_window_require_over_footprint
            ),
            dump_done_max_bucket_mass_kg=ports.dump_done_max_bucket_mass_kg,
            dump_done_min_deposit_delta_kg=ports.dump_done_min_deposit_delta_kg,
        )

    def dump_transition_status(
        self,
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> DumpTransitionStatus:
        ports = self.ports
        return DumpTransitionStatus.from_inputs(
            observation=self._observation(obs),
            boundary_event=boundary_event,
            semantic_boundary_profile_active=(
                ports.semantic_boundary_profile_active()
            ),
            dump_done_use_boundary_event=ports.dump_done_use_boundary_event,
            dump_start_deposited_mass_kg=(
                ports.cycle_state.dump_start_deposited_mass_kg
            ),
            dump_done_hold_count=ports.cycle_state.dump_done_hold_count,
            dump_done_hold_steps=ports.dump_done_hold_steps,
            dump_done_max_bucket_mass_kg=ports.dump_done_max_bucket_mass_kg,
            dump_done_min_deposit_delta_kg=ports.dump_done_min_deposit_delta_kg,
        )

    def refresh_return_transition_state(self, obs: dict[str, Any]) -> None:
        self.ports.refresh_return_handoff_state(obs)

    def return_transition_status(
        self,
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> ReturnTransitionStatus:
        ports = self.ports
        return ReturnTransitionStatus.from_inputs(
            observation=self._observation(obs),
            boundary_event=boundary_event,
            semantic_boundary_profile_active=(
                ports.semantic_boundary_profile_active()
            ),
            return_next_dig_event_seen=(
                ports.return_state.return_next_dig_event_seen
            ),
            entry_close=ports.return_state.return_to_dig_entry_close_state,
            start_envelope_ready=(
                ports.return_state.return_to_dig_start_envelope_ready_state
            ),
            pre_dig_align_before_dig=ports.pre_dig_align_before_dig(),
            return_to_dig_start_envelope_direct_handoff_enabled=(
                ports.return_to_dig_start_envelope_direct_handoff_enabled
            ),
            return_to_dig_start_envelope_gate_enabled=(
                ports.return_to_dig_start_envelope_gate_enabled
            ),
            return_to_dig_shallow_guard_enabled=(
                ports.return_to_dig_shallow_guard_enabled
            ),
            return_to_dig_max_bucket_mass_kg=(
                ports.return_to_dig_max_bucket_mass_kg
            ),
            return_to_dig_touch_tolerance_m=(
                ports.return_to_dig_touch_tolerance_m
            ),
            return_to_dig_min_depth_m=ports.return_to_dig_min_depth_m,
            return_to_dig_max_depth_m=ports.return_to_dig_max_depth_m,
            return_to_dig_max_entry_error_m=ports.return_to_dig_max_entry_error_m,
        )

    def _observation(self, obs: dict[str, Any]) -> PrimitiveObservationFacts:
        return PrimitiveObservationFacts.from_obs(
            obs,
            action_dim=self.ports.action_dim,
        )

    def _dig_exit_overshoot_m(
        self,
        observation: PrimitiveObservationFacts,
    ) -> float:
        corridor = self.ports.coverage_state.active_corridor()
        if corridor is None:
            return float("nan")
        pose = observation.bucket_tip_dig_area_pose()
        if pose is None:
            return float("nan")
        entry = np.asarray(
            [float(corridor.entry_x_m), float(corridor.entry_z_m)],
            dtype=np.float32,
        )
        exit_point = np.asarray(
            [float(corridor.exit_x_m), float(corridor.exit_z_m)],
            dtype=np.float32,
        )
        tip = np.asarray([float(pose[0]), float(pose[2])], dtype=np.float32)
        direction = exit_point - entry
        length = float(np.linalg.norm(direction))
        if length <= 1.0e-6 or not np.all(np.isfinite(tip)):
            return float("nan")
        unit = direction / length
        progress = float(np.dot(tip - entry, unit))
        return float(progress - length)


__all__ = [
    "PrimitiveFSMCapabilityProvider",
    "PrimitiveFSMCapabilityProviderPorts",
]
