"""Mutable primitive mainline cycle/progress runtime state owner."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PrimitiveCycleReportStatus:
    """Projected cycle/progress runtime facts for reports and finalization."""

    completed_transition_count: int
    transition_timeout_count: int
    dump_ready_hold_count: int
    dump_done_hold_count: int
    primitive_cycle_index: int
    dig_step_count: int
    dig_best_mass_kg: float
    dig_mass_plateau_count: int
    dig_to_carry_reason: str
    dig_bad_replan_count: int
    dig_exit_guard_replan_count: int

    def dig_progress_debug_fields(self) -> dict[str, int | float | str]:
        """Return the public dig-progress debug report field projection."""

        return {
            "dig_step_count": int(self.dig_step_count),
            "dig_best_mass_kg": float(self.dig_best_mass_kg),
            "dig_mass_plateau_count": int(self.dig_mass_plateau_count),
            "dig_to_carry_reason": str(self.dig_to_carry_reason),
            "dig_bad_replan_count": int(self.dig_bad_replan_count),
            "dig_exit_guard_replan_count": int(
                self.dig_exit_guard_replan_count
            ),
        }


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

    def to_report_status(self) -> PrimitiveCycleReportStatus:
        """Project live cycle/progress state for reports and finalization."""

        return PrimitiveCycleReportStatus(
            completed_transition_count=int(self.completed_transition_count),
            transition_timeout_count=int(self.transition_timeout_count),
            dump_ready_hold_count=int(self.dump_ready_hold_count),
            dump_done_hold_count=int(self.dump_done_hold_count),
            primitive_cycle_index=int(self.cycle_index),
            dig_step_count=int(self.dig_step_count),
            dig_best_mass_kg=float(self.dig_best_mass_kg),
            dig_mass_plateau_count=int(self.dig_mass_plateau_count),
            dig_to_carry_reason=str(self.dig_to_carry_reason),
            dig_bad_replan_count=int(self.dig_bad_replan_count),
            dig_exit_guard_replan_count=int(self.dig_exit_guard_replan_count),
        )

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


__all__ = ["PrimitiveCycleReportStatus", "PrimitiveCycleRuntimeState"]
