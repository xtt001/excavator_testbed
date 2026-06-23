"""Mutable primitive mainline cycle/progress runtime state owner."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PrimitiveCycleRuntimeState:
    """Own mutable 4P mainline cycle/progress counters and mirrors."""

    dump_ready_hold_count: int = 0
    dump_done_hold_count: int = 0
    dig_step_count: int = 0
    dig_best_mass_kg: float = 0.0
    dig_mass_plateau_count: int = 0
    dig_to_carry_reason: str = ""
    dig_bad_replan_count: int = 0
    dig_exit_guard_replan_count: int = 0
    completed_transition_count: int = 0
    transition_timeout_count: int = 0
    cycle_index: int = 0
    dump_start_deposited_mass_kg: float = 0.0

    @classmethod
    def fresh(cls) -> "PrimitiveCycleRuntimeState":
        """Return a fresh cycle runtime state matching reset defaults."""
        return cls()

    def set_dump_ready_hold_count(self, value: int) -> None:
        self.dump_ready_hold_count = int(value)

    def set_dump_done_hold_count(self, value: int) -> None:
        self.dump_done_hold_count = int(value)

    def set_dump_start_deposited_mass_kg(self, value: float) -> None:
        self.dump_start_deposited_mass_kg = float(value)

    def increment_transition_timeout_count(self) -> None:
        self.transition_timeout_count += 1

    def complete_return_transition(self) -> None:
        self.completed_transition_count += 1
        self.cycle_index += 1

    def increment_dig_bad_replan_count(self) -> None:
        self.dig_bad_replan_count += 1

    def increment_dig_exit_guard_replan_count(self) -> None:
        self.dig_exit_guard_replan_count += 1

    def reset_dig_progress(self) -> None:
        self.dig_step_count = 0
        self.dig_best_mass_kg = 0.0
        self.dig_mass_plateau_count = 0
        self.dig_to_carry_reason = ""

    def update_dig_progress(
        self,
        *,
        mass_in_bucket_kg: float,
        plateau_epsilon_kg: float,
    ) -> None:
        self.dig_step_count += 1
        mass = float(mass_in_bucket_kg)
        previous_best = float(self.dig_best_mass_kg)
        if mass > previous_best + float(plateau_epsilon_kg):
            self.dig_best_mass_kg = mass
            self.dig_mass_plateau_count = 0
            return
        self.dig_best_mass_kg = max(previous_best, mass)
        self.dig_mass_plateau_count += 1


__all__ = ["PrimitiveCycleRuntimeState"]
