"""Coverage selection and planning-fact composition runtime."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.planner.primitive.facts.capabilities import PrimitiveObservationFacts
from testbed.planner.primitive.coverage.config import PrimitiveCoverageStaticConfig
from testbed.planner.primitive.coverage.selection import (
    CoverageCandidateBuilder,
    CoverageCandidateSelectionFacts,
    CoverageCorridorState,
    CoverageSelectionConfig,
    CoverageSelectionRuntimeCoordinator,
    CoverageSelectionRuntimePorts,
    CoverageSelectionService,
)
from testbed.planner.primitive.coverage.exemplars import (
    CoverageStateExemplarPlanner,
    CoverageStateExemplarPlannerConfig,
)
from testbed.planner.primitive.coverage.facts import (
    CoveragePlanningFactConfig,
    CoveragePlanningFactService,
)
from testbed.planner.primitive.coverage.state import CoverageRuntimeState


@dataclass(frozen=True)
class PrimitiveCoverageSelectionRuntimePorts:
    """Typed coverage-selection and planning-fact composition ports."""

    state: CoverageRuntimeState
    static_config: PrimitiveCoverageStaticConfig
    cycle_index: Callable[[], int]
    observation_facts: Callable[[dict[str, Any]], PrimitiveObservationFacts]
    maybe_reopen_pass: Callable[[dict[str, Any], str], bool]
    request_terminal_stop: Callable[[str], None]
    record_decision_event: Callable[..., None]


@dataclass(frozen=True)
class PrimitiveCoverageSelectionRuntime:
    """Compose coverage selection, scoring, and planning-fact services."""

    ports: PrimitiveCoverageSelectionRuntimePorts

    @classmethod
    def from_ports(
        cls,
        ports: PrimitiveCoverageSelectionRuntimePorts,
    ) -> "PrimitiveCoverageSelectionRuntime":
        return cls(ports=ports)

    def coverage_selection_runtime_ports(self) -> CoverageSelectionRuntimePorts:
        return CoverageSelectionRuntimePorts(
            state=self.ports.state,
            dig_cut_prior=lambda: dict(self.ports.static_config.dig_cut_prior or {}),
            dig_cut_planner_mode=lambda: str(
                self.ports.static_config.dig_cut_planner_mode
            ),
            candidate_builder=lambda: self.coverage_candidate_builder(),
            selection_service=lambda: self.coverage_selection_service(),
            selection_facts=(
                lambda obs, corridors: self.coverage_selection_facts(
                    obs,
                    corridors,
                )
            ),
            recent_row_reference=lambda: self.coverage_recent_row_reference_corridor(),
            maybe_reopen_pass=(
                lambda obs, reason: self.ports.maybe_reopen_pass(obs, reason)
            ),
            request_terminal_stop=self.ports.request_terminal_stop,
            record_decision_event=self.ports.record_decision_event,
        )

    def coverage_selection_runtime_coordinator(
        self,
    ) -> CoverageSelectionRuntimeCoordinator:
        return CoverageSelectionRuntimeCoordinator.from_ports(
            self.coverage_selection_runtime_ports()
        )

    def select_next_coverage_corridor(
        self,
        obs: dict[str, Any],
    ) -> CoverageCorridorState:
        return self.coverage_selection_runtime_coordinator().select_next_corridor(
            obs
        )

    def ensure_coverage_corridors(self) -> None:
        self.coverage_selection_runtime_coordinator().ensure_corridors()

    def select_coverage_corridor(
        self,
        obs: dict[str, Any],
    ) -> CoverageCorridorState:
        return self.coverage_selection_runtime_coordinator().select_corridor(obs)

    def build_cell_weighted_coverage_corridors(
        self,
        fields: dict[str, object],
    ) -> list[CoverageCorridorState]:
        prior = dict(self.ports.static_config.dig_cut_prior or {})
        prior["fields"] = dict(fields)
        return self.coverage_candidate_builder(
            candidate_layout="cell_weighted_3x2"
        ).build(prior)

    def coverage_candidate_builder(
        self,
        *,
        candidate_layout: str | None = None,
    ) -> CoverageCandidateBuilder:
        config = self.ports.static_config
        return CoverageCandidateBuilder(
            candidate_layout=str(candidate_layout or config.candidate_layout),
            entry_x_percentiles=tuple(config.entry_x_percentiles),
            entry_z_percentiles=tuple(config.entry_z_percentiles),
            cut_direction_percentile=str(config.cut_direction_percentile),
            cut_length_percentile=str(config.cut_length_percentile),
            cut_depth_percentile=str(config.cut_depth_percentile),
            payload_percentile=str(config.payload_percentile),
        )

    def coverage_selection_config(self) -> CoverageSelectionConfig:
        return self.ports.static_config.selection_config(
            self.ports.state,
            cycle_index=int(self.ports.cycle_index()),
        )

    def coverage_selection_service(self) -> CoverageSelectionService:
        return CoverageSelectionService(self.coverage_selection_config())

    def coverage_planning_fact_config(self) -> CoveragePlanningFactConfig:
        return self.ports.static_config.planning_fact_config()

    def coverage_planning_fact_service(self) -> CoveragePlanningFactService:
        return CoveragePlanningFactService(
            config=self.coverage_planning_fact_config(),
            coverage_state=self.ports.state,
            state_exemplar_planner=self.coverage_state_exemplar_planner(),
            coverage_state_exemplars_by_cell=(
                self.ports.static_config.state_exemplars_by_cell
            ),
            observation_facts=self.ports.observation_facts,
            first_dig_qpos_delta=(
                lambda corridor, obs: self.coverage_first_dig_qpos_delta(
                    corridor,
                    obs,
                )
            ),
        )

    def coverage_selection_facts(
        self,
        obs: dict[str, Any],
        corridors: list[CoverageCorridorState] | None = None,
    ) -> dict[int, CoverageCandidateSelectionFacts]:
        return self.coverage_planning_fact_service().selection_facts(obs, corridors)

    def coverage_first_dig_active(self) -> bool:
        return self.coverage_selection_service().first_dig_active()

    def coverage_first_dig_gate_available(self, obs: dict[str, Any]) -> bool:
        return self.coverage_selection_service().first_dig_gate_available(
            self.ports.state.coverage_corridors,
            facts_by_corridor_id=self.coverage_selection_facts(obs),
        )

    def coverage_first_dig_entry_reachable(self, distance: float) -> bool:
        return self.coverage_selection_service().first_dig_entry_reachable(distance)

    def coverage_score(
        self,
        corridor: CoverageCorridorState,
        remaining_depth_m: float,
        *,
        obs: dict[str, Any] | None = None,
    ) -> float:
        return self.coverage_selection_service().score(
            corridor,
            remaining_depth_m,
            state_exemplar_distance=(
                float("nan")
                if obs is None
                else self.coverage_state_exemplar_distance(corridor, obs)
            ),
            recent_row_reference=self.coverage_recent_row_reference_corridor(),
        )

    def coverage_cell_confidence(self, corridor: CoverageCorridorState) -> float:
        return self.coverage_selection_service().cell_confidence(corridor)

    def coverage_corridor_is_rare(self, corridor: CoverageCorridorState) -> bool:
        return self.coverage_selection_service().corridor_is_rare(corridor)

    def coverage_corridor_attempt_limit(
        self,
        corridor: CoverageCorridorState,
    ) -> int:
        return self.coverage_selection_service().corridor_attempt_limit(corridor)

    def coverage_rare_first_dig_gated_out(
        self,
        corridor: CoverageCorridorState,
    ) -> bool:
        return self.coverage_selection_service().rare_first_dig_gated_out(
            corridor,
            self.ports.state.coverage_corridors,
        )

    def coverage_recent_row_penalty(
        self,
        corridor: CoverageCorridorState,
    ) -> float:
        return self.coverage_selection_service().recent_row_penalty(
            corridor,
            recent_row_reference=self.coverage_recent_row_reference_corridor(),
        )

    def coverage_recent_row_reference_corridor(
        self,
    ) -> CoverageCorridorState | None:
        previous = self.ports.state.corridor_by_id(
            self.ports.state.coverage_last_selected_corridor_id
        )
        if previous is not None:
            return previous
        return self.ports.state.active_corridor()

    def coverage_first_dig_bonus(
        self,
        corridor: CoverageCorridorState,
        obs: dict[str, Any],
    ) -> float:
        return self.coverage_selection_service().first_dig_bonus(
            corridor,
            CoverageCandidateSelectionFacts(
                remaining_depth_m=float("nan"),
                first_dig_entry_distance_m=float(
                    self.coverage_entry_distance_m(corridor, obs)
                ),
                first_dig_qpos_delta=self.coverage_first_dig_qpos_delta(
                    corridor,
                    obs,
                ),
            ),
        )

    def coverage_entry_distance_m(
        self,
        corridor: CoverageCorridorState,
        obs: dict[str, Any],
    ) -> float:
        return self.coverage_planning_fact_service().entry_distance_m(corridor, obs)

    def coverage_first_dig_qpos_delta(
        self,
        corridor: CoverageCorridorState,
        obs: dict[str, Any],
    ) -> np.ndarray:
        del corridor, obs
        return np.zeros(int(self.ports.static_config.action_dim), dtype=np.float32)

    def coverage_first_dig_qpos_reachable(self, delta: np.ndarray) -> bool:
        return self.coverage_selection_service().first_dig_qpos_reachable(delta)

    def coverage_first_dig_qpos_delta_penalty(self, delta: np.ndarray) -> float:
        return self.coverage_selection_service().first_dig_qpos_delta_penalty(delta)

    def coverage_raw_fields(
        self,
        corridor: CoverageCorridorState,
        *,
        obs: dict[str, Any] | None = None,
        update_state: bool = False,
    ) -> dict[str, float | int]:
        return self.coverage_planning_fact_service().raw_fields(
            corridor,
            obs=obs,
            update_state=update_state,
        )

    def coverage_state_exemplar_planner_config(
        self,
    ) -> CoverageStateExemplarPlannerConfig:
        return self.ports.static_config.state_exemplar_planner_config()

    def coverage_state_exemplar_planner(self) -> CoverageStateExemplarPlanner:
        return CoverageStateExemplarPlanner(
            self.coverage_state_exemplar_planner_config()
        )

    def load_coverage_state_exemplars(self) -> dict[int, list[dict[str, Any]]]:
        return self.coverage_state_exemplar_planner().load_exemplars()

    def coverage_state_conditioned_plan(
        self,
        corridor: CoverageCorridorState,
        obs: dict[str, Any],
        *,
        update_state: bool,
    ) -> dict[str, object] | None:
        return self.coverage_planning_fact_service().state_conditioned_plan(
            corridor,
            obs,
            update_state=update_state,
        )

    def coverage_state_exemplar_distance(
        self,
        corridor: CoverageCorridorState,
        obs: dict[str, Any],
    ) -> float:
        return self.coverage_planning_fact_service().state_exemplar_distance(
            corridor,
            obs,
        )

    def coverage_state_exemplar_id(
        self,
        corridor: CoverageCorridorState,
        obs: dict[str, Any],
    ) -> str:
        return self.coverage_planning_fact_service().state_exemplar_id(corridor, obs)

    def coverage_removed_depth_grid(self, obs: dict[str, Any]) -> np.ndarray | None:
        return self.coverage_planning_fact_service().removed_depth_grid(obs)

    def coverage_state_exemplar_distance_for_grid(
        self,
        removed_grid: np.ndarray,
        exemplar: dict[str, Any],
        *,
        cell_id: int,
    ) -> float:
        return self.coverage_planning_fact_service().state_exemplar_distance_for_grid(
            removed_grid,
            exemplar,
            cell_id=cell_id,
        )

    def state_exemplar_weights(
        self,
        selected: list[tuple[float, dict[str, Any]]],
    ) -> np.ndarray:
        return self.coverage_planning_fact_service().state_exemplar_weights(selected)

    def weighted_state_exemplar_raw_fields(
        self,
        selected: list[tuple[float, dict[str, Any]]],
    ) -> dict[str, float | int]:
        return (
            self.coverage_planning_fact_service()
            .weighted_state_exemplar_raw_fields(selected)
        )

    def weighted_state_exemplar_profile_token(
        self,
        selected: list[tuple[float, dict[str, Any]]],
    ) -> np.ndarray | None:
        return (
            self.coverage_planning_fact_service()
            .weighted_state_exemplar_profile_token(selected)
        )

    def coverage_remaining_depth_for_corridor(
        self,
        obs: dict[str, Any],
        corridor: CoverageCorridorState,
    ) -> float:
        return self.coverage_planning_fact_service().remaining_depth_for_corridor(
            obs,
            corridor,
        )


__all__ = [
    "PrimitiveCoverageSelectionRuntime",
    "PrimitiveCoverageSelectionRuntimePorts",
]
