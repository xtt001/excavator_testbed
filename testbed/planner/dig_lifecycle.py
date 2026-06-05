"""Dig lifecycle gates for primitive planner state transitions."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class DigLifecycleConfig:
    dig_to_carry_min_bucket_mass_kg: float
    dig_to_carry_min_distance_to_dig_area_m: float
    dig_to_carry_target_bucket_mass_kg: float
    dig_to_carry_mass_plateau_enabled: bool
    dig_to_carry_mass_plateau_min_bucket_mass_kg: float
    dig_to_carry_mass_plateau_epsilon_kg: float
    dig_to_carry_mass_plateau_hold_steps: int
    dig_to_carry_mass_plateau_min_steps: int
    dig_bad_replan_enabled: bool
    dig_bad_replan_max_steps: int
    dig_bad_replan_min_bucket_mass_kg: float
    dig_exit_guard_enabled: bool
    dig_exit_guard_min_steps: int
    dig_exit_guard_overshoot_m: float
    dig_exit_guard_min_bucket_mass_kg: float
    dump_ready_min_bucket_mass_kg: float


@dataclass(frozen=True)
class DigLifecycleFacts:
    mass_in_bucket_kg: float
    min_distance_to_dig_area_m: float
    carry_mass_in_bucket_kg: float
    carry_min_distance_to_dig_area_m: float
    semantic_boundary_profile_active: bool
    boundary_dig_complete: bool
    coverage_terminal_stop_requested: bool
    dig_step_count: int
    dig_best_mass_kg: float
    dig_mass_plateau_count: int
    coverage_current_payload_gain_kg: float
    active_corridor_entry_xz: tuple[float, float] | None = None
    active_corridor_exit_xz: tuple[float, float] | None = None
    bucket_tip_xz: tuple[float, float] | None = None


@dataclass(frozen=True)
class DigProgressState:
    step_count: int
    best_mass_kg: float
    mass_plateau_count: int
    coverage_payload_gain_kg: float


@dataclass(frozen=True)
class DigGateDecision:
    ready: bool
    reason: str = ""


class DigLifecycleGateService:
    """Evaluates dig lifecycle gates without owning scheduler state."""

    def update_progress(
        self,
        facts: DigLifecycleFacts,
        config: DigLifecycleConfig,
    ) -> DigProgressState:
        step_count = int(facts.dig_step_count) + 1
        mass = float(facts.mass_in_bucket_kg)
        previous_best = float(facts.dig_best_mass_kg)
        if mass > previous_best + float(config.dig_to_carry_mass_plateau_epsilon_kg):
            best_mass = mass
            plateau_count = 0
        else:
            best_mass = max(previous_best, mass)
            plateau_count = int(facts.dig_mass_plateau_count) + 1
        payload_gain = max(
            float(facts.coverage_current_payload_gain_kg),
            mass,
        )
        return DigProgressState(
            step_count=step_count,
            best_mass_kg=float(best_mass),
            mass_plateau_count=int(plateau_count),
            coverage_payload_gain_kg=float(payload_gain),
        )

    def bad_replan_ready(
        self,
        facts: DigLifecycleFacts,
        config: DigLifecycleConfig,
    ) -> bool:
        if not bool(config.dig_bad_replan_enabled):
            return False
        if bool(facts.coverage_terminal_stop_requested):
            return False
        if int(facts.dig_step_count) < int(config.dig_bad_replan_max_steps):
            return False
        return bool(
            float(facts.mass_in_bucket_kg)
            < float(config.dig_bad_replan_min_bucket_mass_kg)
        )

    def exit_guard_ready(
        self,
        facts: DigLifecycleFacts,
        config: DigLifecycleConfig,
    ) -> bool:
        if not bool(config.dig_exit_guard_enabled):
            return False
        if bool(facts.coverage_terminal_stop_requested):
            return False
        if int(facts.dig_step_count) < int(config.dig_exit_guard_min_steps):
            return False
        if float(facts.mass_in_bucket_kg) >= float(
            config.dig_exit_guard_min_bucket_mass_kg
        ):
            return False
        overshoot = self.exit_overshoot_m(facts)
        return bool(
            np.isfinite(overshoot)
            and overshoot >= float(config.dig_exit_guard_overshoot_m)
        )

    @staticmethod
    def exit_overshoot_m(facts: DigLifecycleFacts) -> float:
        if (
            facts.active_corridor_entry_xz is None
            or facts.active_corridor_exit_xz is None
            or facts.bucket_tip_xz is None
        ):
            return float("nan")
        entry = np.asarray(facts.active_corridor_entry_xz, dtype=np.float32).reshape(2)
        exit_point = np.asarray(
            facts.active_corridor_exit_xz,
            dtype=np.float32,
        ).reshape(2)
        tip = np.asarray(facts.bucket_tip_xz, dtype=np.float32).reshape(2)
        direction = exit_point - entry
        length = float(np.linalg.norm(direction))
        if length <= 1.0e-6 or not np.all(np.isfinite(tip)):
            return float("nan")
        unit = direction / length
        progress = float(np.dot(tip - entry, unit))
        return float(progress - length)

    def dig_to_carry_ready(
        self,
        facts: DigLifecycleFacts,
        config: DigLifecycleConfig,
    ) -> DigGateDecision:
        if bool(facts.boundary_dig_complete):
            return DigGateDecision(True, "dig_complete_boundary")
        if bool(facts.semantic_boundary_profile_active):
            return self.semantic_liveness_ready(facts, config)
        mass = float(facts.carry_mass_in_bucket_kg)
        dig_distance = float(facts.carry_min_distance_to_dig_area_m)
        distance_ready = bool(
            dig_distance >= float(config.dig_to_carry_min_distance_to_dig_area_m)
        )
        if mass >= float(config.dig_to_carry_target_bucket_mass_kg) and distance_ready:
            if (
                abs(
                    float(config.dig_to_carry_target_bucket_mass_kg)
                    - float(config.dig_to_carry_min_bucket_mass_kg)
                )
                <= 1.0e-6
            ):
                return DigGateDecision(True, "loaded")
            return DigGateDecision(True, "target_payload_loaded")
        if (
            bool(config.dig_to_carry_mass_plateau_enabled)
            and int(facts.dig_step_count)
            >= int(config.dig_to_carry_mass_plateau_min_steps)
            and mass >= float(config.dig_to_carry_mass_plateau_min_bucket_mass_kg)
            and int(facts.dig_mass_plateau_count)
            >= int(config.dig_to_carry_mass_plateau_hold_steps)
            and distance_ready
        ):
            return DigGateDecision(True, "mass_plateau")
        return DigGateDecision(False, "")

    def semantic_liveness_ready(
        self,
        facts: DigLifecycleFacts,
        config: DigLifecycleConfig,
    ) -> DigGateDecision:
        mass = float(facts.carry_mass_in_bucket_kg)
        dig_distance = float(facts.carry_min_distance_to_dig_area_m)
        distance_ready = bool(
            dig_distance >= float(config.dig_to_carry_min_distance_to_dig_area_m)
        )
        if not distance_ready:
            return DigGateDecision(False, "")
        if mass >= float(config.dig_to_carry_target_bucket_mass_kg):
            return DigGateDecision(True, "semantic_material_loaded")
        if (
            bool(config.dig_to_carry_mass_plateau_enabled)
            and int(facts.dig_step_count)
            >= int(config.dig_to_carry_mass_plateau_min_steps)
            and mass >= float(config.dig_to_carry_mass_plateau_min_bucket_mass_kg)
            and int(facts.dig_mass_plateau_count)
            >= int(config.dig_to_carry_mass_plateau_hold_steps)
        ):
            return DigGateDecision(True, "semantic_material_plateau")
        return DigGateDecision(False, "")

    def complete_boundary_low_payload(
        self,
        facts: DigLifecycleFacts,
        config: DigLifecycleConfig,
    ) -> bool:
        if not bool(facts.semantic_boundary_profile_active):
            return False
        if not bool(facts.boundary_dig_complete):
            return False
        min_carry_mass = max(
            float(config.dig_to_carry_min_bucket_mass_kg),
            float(config.dump_ready_min_bucket_mass_kg),
        )
        return bool(float(facts.mass_in_bucket_kg) < min_carry_mass)
