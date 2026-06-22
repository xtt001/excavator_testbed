"""Mutable runtime state owner for primitive coverage planning."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from testbed.planner.primitive_coverage import CoverageCorridorState


@dataclass
class CoverageRuntimeState:
    """Owns the mutable coverage state used by selection, effects, and reports."""

    coverage_corridors: list[CoverageCorridorState] = field(default_factory=list)
    coverage_active_corridor_id: int = -1
    coverage_last_selected_corridor_id: int = -1
    coverage_current_payload_gain_kg: float = 0.0
    coverage_cycle_start_deposit_kg: float = 0.0
    coverage_last_payload_gain_kg: float = 0.0
    coverage_last_effective_deposit_delta_kg: float = 0.0
    coverage_global_low_productivity_streak: int = 0
    coverage_completed_dump_count: int = 0
    coverage_pass_index: int = 0
    coverage_terminal_stop_requested: bool = False
    coverage_terminal_stop_reason: str = ""
    coverage_candidate_scores: list[dict[str, Any]] = field(default_factory=list)
    coverage_decision_trace: list[dict[str, Any]] = field(default_factory=list)
    coverage_active_state_exemplar_ids: list[str] = field(default_factory=list)
    coverage_rejected_state_exemplar_ids: set[str] = field(default_factory=set)
    coverage_active_state_exemplar_distance: float = float("nan")
    coverage_active_state_exemplar_profile_token: np.ndarray | None = None

    def reset(self) -> None:
        fresh = type(self)()
        self.__dict__.update(fresh.__dict__)

    def corridor_by_id(self, corridor_id: int) -> CoverageCorridorState | None:
        for corridor in self.coverage_corridors:
            if int(corridor.corridor_id) == int(corridor_id):
                return corridor
        return None

    def active_corridor(self) -> CoverageCorridorState | None:
        return self.corridor_by_id(self.coverage_active_corridor_id)

    def depleted_count(self) -> int:
        return int(sum(1 for corridor in self.coverage_corridors if corridor.depleted))

    def all_depleted(self) -> bool:
        return bool(
            self.coverage_corridors
            and all(corridor.depleted for corridor in self.coverage_corridors)
        )

    def set_coverage_corridors(
        self,
        corridors: list[CoverageCorridorState],
    ) -> None:
        self.coverage_corridors = corridors

    def set_candidate_scores(self, candidate_scores: list[dict[str, Any]]) -> None:
        self.coverage_candidate_scores = list(candidate_scores)

    def set_active_corridor_id(self, value: int) -> None:
        self.coverage_active_corridor_id = int(value)

    def set_last_selected_corridor_id(self, value: int) -> None:
        self.coverage_last_selected_corridor_id = int(value)

    def set_selected_corridor_ids(
        self,
        *,
        active_corridor_id: int,
        last_selected_corridor_id: int,
    ) -> None:
        self.set_active_corridor_id(active_corridor_id)
        self.set_last_selected_corridor_id(last_selected_corridor_id)

    def set_current_payload_gain_kg(self, value: float) -> None:
        self.coverage_current_payload_gain_kg = float(value)

    def set_cycle_start_deposit_kg(self, value: float) -> None:
        self.coverage_cycle_start_deposit_kg = float(value)

    def set_last_payload_gain_kg(self, value: float) -> None:
        self.coverage_last_payload_gain_kg = float(value)

    def set_last_effective_deposit_delta_kg(self, value: float) -> None:
        self.coverage_last_effective_deposit_delta_kg = float(value)

    def set_completed_dump_count(self, value: int) -> None:
        self.coverage_completed_dump_count = int(value)

    def set_global_low_productivity_streak(self, value: int) -> None:
        self.coverage_global_low_productivity_streak = int(value)

    def set_coverage_pass_index(self, value: int) -> None:
        self.coverage_pass_index = int(value)

    def set_terminal_stop(self, *, requested: bool, reason: str) -> None:
        self.coverage_terminal_stop_requested = bool(requested)
        self.coverage_terminal_stop_reason = str(reason)

    def set_terminal_stop_requested(self, value: bool) -> None:
        self.coverage_terminal_stop_requested = bool(value)

    def set_terminal_stop_reason(self, value: str) -> None:
        self.coverage_terminal_stop_reason = str(value)

    def update_rejected_state_exemplar_ids(
        self,
        exemplar_ids: tuple[str, ...],
    ) -> None:
        self.coverage_rejected_state_exemplar_ids.update(exemplar_ids)

    def clear_rejected_state_exemplar_ids(self) -> None:
        self.coverage_rejected_state_exemplar_ids.clear()

    def set_active_state_exemplar(
        self,
        *,
        exemplar_ids: list[str],
        distance: float,
        profile_token: np.ndarray | None,
    ) -> None:
        self.coverage_active_state_exemplar_ids = list(exemplar_ids)
        self.coverage_active_state_exemplar_distance = float(distance)
        self.coverage_active_state_exemplar_profile_token = profile_token

    def clear_active_state_exemplar(self) -> None:
        self.coverage_active_state_exemplar_ids = []
        self.coverage_active_state_exemplar_distance = float("nan")
        self.coverage_active_state_exemplar_profile_token = None


__all__ = ["CoverageRuntimeState"]
