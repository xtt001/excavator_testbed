"""Coverage planning fact projection for primitive planner coverage paths."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.data.schema import (
    ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
    ENV_STATE_DIG_AREA_TARGET_DEPTH_START_IDX,
)
from testbed.planner.primitive_capabilities import PrimitiveObservationFacts
from testbed.planner.primitive_coverage import (
    CoverageCandidateSelectionFacts,
    CoverageCorridorState,
    CoverageSelectionService,
)
from testbed.planner.primitive_coverage_exemplars import (
    CoverageStateExemplarPlanInputs,
    CoverageStateExemplarPlanner,
)
from testbed.planner.primitive_coverage_state import CoverageRuntimeState
from testbed.planner.primitive_tokens import DigCutTokenPlanner


@dataclass(frozen=True)
class CoveragePlanningFactConfig:
    """Explicit config needed to project coverage planning facts."""

    prior_fields: dict[str, Any]
    cut_direction_percentile: str
    cut_length_percentile: str
    cut_depth_percentile: str
    payload_percentile: str


@dataclass(frozen=True)
class CoveragePlanningFactService:
    """Owns coverage selection facts, raw fields, and exemplar fact projection."""

    config: CoveragePlanningFactConfig
    coverage_state: CoverageRuntimeState
    state_exemplar_planner: CoverageStateExemplarPlanner
    coverage_state_exemplars_by_cell: dict[int, list[dict[str, Any]]]
    observation_facts: Callable[[dict], PrimitiveObservationFacts]
    first_dig_qpos_delta: Callable[[CoverageCorridorState, dict], np.ndarray]

    def selection_facts(
        self,
        obs: dict,
        corridors: list[CoverageCorridorState] | None = None,
    ) -> dict[int, CoverageCandidateSelectionFacts]:
        facts: dict[int, CoverageCandidateSelectionFacts] = {}
        for corridor in list(
            self.coverage_state.coverage_corridors if corridors is None else corridors
        ):
            facts[int(corridor.corridor_id)] = CoverageCandidateSelectionFacts(
                remaining_depth_m=float(
                    self.remaining_depth_for_corridor(obs, corridor)
                ),
                first_dig_entry_distance_m=float(
                    self.entry_distance_m(corridor, obs)
                ),
                first_dig_qpos_delta=self.first_dig_qpos_delta(corridor, obs),
                state_exemplar_distance=float(
                    self.state_exemplar_distance(corridor, obs)
                ),
                state_exemplar_id=str(self.state_exemplar_id(corridor, obs)),
            )
        return facts

    def entry_distance_m(
        self,
        corridor: CoverageCorridorState,
        obs: dict,
    ) -> float:
        pose = self.observation_facts(obs).bucket_tip_dig_area_pose()
        if pose is None:
            return float("nan")
        bucket_x, _, bucket_z = pose
        if not all(np.isfinite(value) for value in (bucket_x, bucket_z)):
            return float("nan")
        return float(
            np.hypot(
                float(bucket_x) - float(corridor.entry_x_m),
                float(bucket_z) - float(corridor.entry_z_m),
            )
        )

    def raw_fields(
        self,
        corridor: CoverageCorridorState,
        *,
        obs: dict | None = None,
        update_state: bool = False,
    ) -> dict[str, float | int]:
        if obs is not None:
            state_plan = self.state_conditioned_plan(
                corridor,
                obs,
                update_state=update_state,
            )
            if state_plan is not None:
                return dict(state_plan["raw_fields"])
        fields = dict(self.config.prior_fields)
        entry_x = self._clamp_to_prior(fields, "entry_x_m", corridor.entry_x_m)
        entry_z = self._clamp_to_prior(fields, "entry_z_m", corridor.entry_z_m)
        exit_x = self._clamp_to_prior(fields, "exit_x_m", corridor.exit_x_m)
        exit_z = self._clamp_to_prior(fields, "exit_z_m", corridor.exit_z_m)
        delta_x = exit_x - entry_x
        delta_z = exit_z - entry_z
        length = float(np.hypot(delta_x, delta_z))
        if length <= 1.0e-6:
            dir_x = self._prior_percentile(
                fields,
                "cut_direction_x",
                self.config.cut_direction_percentile,
            )
            dir_z = self._prior_percentile(
                fields,
                "cut_direction_z",
                self.config.cut_direction_percentile,
            )
            length = self._prior_percentile(
                fields,
                "cut_length_m",
                self.config.cut_length_percentile,
            )
        else:
            dir_x = delta_x / length
            dir_z = delta_z / length
        return {
            "operator_entry_x_m": float(entry_x),
            "operator_entry_y_m": 0.0,
            "operator_entry_z_m": float(entry_z),
            "operator_exit_x_m": float(exit_x),
            "operator_exit_y_m": 0.0,
            "operator_exit_z_m": float(exit_z),
            "operator_cut_direction_x": float(
                self._clamp_to_prior(fields, "cut_direction_x", dir_x)
            ),
            "operator_cut_direction_y": 0.0,
            "operator_cut_direction_z": float(
                self._clamp_to_prior(fields, "cut_direction_z", dir_z)
            ),
            "operator_cut_length_m": float(
                self._clamp_to_prior(fields, "cut_length_m", length)
            ),
            "operator_cut_depth_peak_m": float(
                self._clamp_to_prior(
                    fields,
                    "cut_depth_peak_m",
                    float(corridor.cut_depth_peak_m)
                    if np.isfinite(corridor.cut_depth_peak_m)
                    else self._prior_percentile(
                        fields,
                        "cut_depth_peak_m",
                        self.config.cut_depth_percentile,
                    ),
                )
            ),
            "operator_cut_payload_gain_kg": float(
                self._clamp_to_prior(
                    fields,
                    "payload_gain_kg",
                    float(corridor.payload_gain_kg)
                    if np.isfinite(corridor.payload_gain_kg)
                    else self._prior_percentile(
                        fields,
                        "payload_gain_kg",
                        self.config.payload_percentile,
                    ),
                )
            ),
            "operator_effective_deposit_delta_kg": float(
                self._clamp_to_prior(
                    fields,
                    "effective_deposit_delta_kg",
                    float(corridor.effective_deposit_delta_kg)
                    if np.isfinite(corridor.effective_deposit_delta_kg)
                    else self._prior_percentile(
                        fields,
                        "effective_deposit_delta_kg",
                        "p50",
                    ),
                )
            ),
            "operator_cut_valid": 1,
        }

    def state_conditioned_plan(
        self,
        corridor: CoverageCorridorState,
        obs: dict,
        *,
        update_state: bool,
    ) -> dict[str, object] | None:
        result = self.state_exemplar_planner.plan(
            CoverageStateExemplarPlanInputs(
                corridor=corridor,
                env_state=self.observation_facts(obs).env_state,
                exemplars_by_cell=self.coverage_state_exemplars_by_cell,
                rejected_exemplar_ids=(
                    self.coverage_state.coverage_rejected_state_exemplar_ids
                ),
            )
        )
        if result is None:
            return None
        if update_state:
            self.coverage_state.set_active_state_exemplar(
                exemplar_ids=list(result.exemplar_ids),
                distance=float(result.distance),
                profile_token=(
                    None
                    if result.profile_token is None
                    else result.profile_token.astype(np.float32).copy()
                ),
            )
            corridor.state_exemplar_id = ",".join(result.exemplar_ids)
            corridor.state_exemplar_distance = float(result.distance)
        return {
            "raw_fields": dict(result.raw_fields),
            "profile_token": result.profile_token,
            "exemplar_ids": list(result.exemplar_ids),
            "distance": float(result.distance),
        }

    def state_exemplar_distance(
        self,
        corridor: CoverageCorridorState,
        obs: dict,
    ) -> float:
        state_plan = self.state_conditioned_plan(corridor, obs, update_state=False)
        if state_plan is None:
            return float("nan")
        return float(state_plan["distance"])

    def state_exemplar_id(
        self,
        corridor: CoverageCorridorState,
        obs: dict,
    ) -> str:
        state_plan = self.state_conditioned_plan(corridor, obs, update_state=False)
        if state_plan is None:
            return ""
        exemplar_ids = state_plan.get("exemplar_ids", [])
        if not exemplar_ids:
            return ""
        return str(exemplar_ids[0])

    def removed_depth_grid(self, obs: dict) -> np.ndarray | None:
        return self.state_exemplar_planner.removed_depth_grid(
            self.observation_facts(obs).env_state
        )

    def state_exemplar_distance_for_grid(
        self,
        removed_grid: np.ndarray,
        exemplar: dict[str, Any],
        *,
        cell_id: int,
    ) -> float:
        return self.state_exemplar_planner.distance_for_grid(
            removed_grid,
            exemplar,
            cell_id=cell_id,
        )

    def state_exemplar_weights(
        self,
        selected: list[tuple[float, dict[str, Any]]],
    ) -> np.ndarray:
        return self.state_exemplar_planner.weights(selected)

    def weighted_state_exemplar_raw_fields(
        self,
        selected: list[tuple[float, dict[str, Any]]],
    ) -> dict[str, float | int]:
        return self.state_exemplar_planner.weighted_raw_fields(selected)

    def weighted_state_exemplar_profile_token(
        self,
        selected: list[tuple[float, dict[str, Any]]],
    ) -> np.ndarray | None:
        return self.state_exemplar_planner.weighted_profile_token(selected)

    def remaining_depth_for_corridor(
        self,
        obs: dict,
        corridor: CoverageCorridorState,
    ) -> float:
        env_state = self.observation_facts(obs).env_state
        cell_id = CoverageSelectionService.cell_id(corridor)
        target_idx = ENV_STATE_DIG_AREA_TARGET_DEPTH_START_IDX + cell_id
        removed_idx = ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX + cell_id
        valid_idx = ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX + cell_id
        if len(env_state) <= max(target_idx, removed_idx, valid_idx):
            return float("nan")
        if float(env_state[valid_idx]) <= 0.5:
            return float("nan")
        target_depth = float(env_state[target_idx])
        removed_depth = float(env_state[removed_idx])
        if not np.isfinite(target_depth) or not np.isfinite(removed_depth):
            return float("nan")
        return float(max(0.0, target_depth - removed_depth))

    @staticmethod
    def _prior_percentile(
        fields: dict[str, Any],
        field_name: str,
        percentile: str,
    ) -> float:
        return DigCutTokenPlanner.prior_percentile(fields, field_name, percentile)

    @staticmethod
    def _clamp_to_prior(
        fields: dict[str, Any],
        field_name: str,
        value: float,
    ) -> float:
        return DigCutTokenPlanner(prior={}).clamp_to_prior(fields, field_name, value)


__all__ = [
    "CoveragePlanningFactConfig",
    "CoveragePlanningFactService",
]
