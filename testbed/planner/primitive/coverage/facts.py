"""Coverage planning fact projection for primitive planner coverage paths."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from testbed.data.schema import (
    ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
    ENV_STATE_DIG_AREA_TARGET_DEPTH_START_IDX,
)
from testbed.planner.primitive.coverage.exemplars import (
    CoverageStateExemplarPlanInputs,
    CoverageStateExemplarPlanner,
)
from testbed.planner.primitive.coverage.selection import (
    CoverageCandidateSelectionFacts,
    CoverageCorridorState,
    CoverageSelectionService,
)
from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.coverage.wall_safety import (
    CoverageFinalWallSafetyError,
    CoverageWallSafetyConfig,
    CoverageWallSafetyEvaluation,
    CoverageWallSafetyService,
)
from testbed.planner.primitive.facts.capabilities import PrimitiveObservationFacts
from testbed.planner.primitive.token.tokens import DigCutTokenPlanner


@dataclass(frozen=True)
class CoveragePlanningFactConfig:
    """Explicit config needed to project coverage planning facts."""

    prior_fields: dict[str, Any]
    cut_direction_percentile: str
    cut_length_percentile: str
    cut_depth_percentile: str
    payload_percentile: str
    wall_safety: CoverageWallSafetyConfig = field(
        default_factory=CoverageWallSafetyConfig
    )


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
            wall_safety = self.wall_safety_service().evaluate_segment(
                env_state=self.observation_facts(obs).env_state,
                entry_x_m=float(corridor.entry_x_m),
                entry_z_m=float(corridor.entry_z_m),
                exit_x_m=float(corridor.exit_x_m),
                exit_z_m=float(corridor.exit_z_m),
            ).with_depth_exhausted_cells(
                self.coverage_state.coverage_depth_exhausted_physical_cell_ids
            )
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
                wall_safety=wall_safety,
                final_wall_rejected=self.coverage_state.wall_corridor_rejected(
                    corridor.corridor_id
                ),
            )
        return facts

    def wall_safety_service(self) -> CoverageWallSafetyService:
        return CoverageWallSafetyService(self.config.wall_safety)

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
        state_plan: dict[str, object] | None = None
        if obs is not None:
            state_plan = self.state_conditioned_plan(
                corridor,
                obs,
                update_state=False,
            )
            if state_plan is not None:
                raw_fields = dict(state_plan["raw_fields"])
                self._validate_final_wall_safety(
                    corridor,
                    obs=obs,
                    raw_fields=raw_fields,
                    update_state=update_state,
                )
                if update_state:
                    self._apply_state_conditioned_plan(corridor, state_plan)
                return raw_fields
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
        raw_fields: dict[str, float | int] = {
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
        self._validate_final_wall_safety(
            corridor,
            obs=obs,
            raw_fields=raw_fields,
            update_state=update_state,
        )
        return raw_fields

    def _validate_final_wall_safety(
        self,
        corridor: CoverageCorridorState,
        *,
        obs: dict | None,
        raw_fields: dict[str, float | int],
        update_state: bool,
    ) -> CoverageWallSafetyEvaluation:
        env_state = (
            np.asarray([], dtype=np.float32)
            if obs is None
            else self.observation_facts(obs).env_state
        )
        evaluation = self.wall_safety_service().evaluate_raw_fields(
            env_state=env_state,
            raw_fields=raw_fields,
        ).with_depth_exhausted_cells(
            self.coverage_state.coverage_depth_exhausted_physical_cell_ids
        )
        evaluation = evaluation.as_depth_exhausted_rejection()
        if (
            not evaluation.eligible
            or evaluation.depth_exhausted_swept_cell_ids
        ):
            raise CoverageFinalWallSafetyError(
                corridor_id=int(corridor.corridor_id),
                evaluation=evaluation,
                raw_fields=raw_fields,
            )
        if update_state:
            self.coverage_state.set_wall_safety_final_fields(
                evaluation.as_trace_fields()
            )
        return evaluation

    def _apply_state_conditioned_plan(
        self,
        corridor: CoverageCorridorState,
        state_plan: dict[str, object],
    ) -> None:
        exemplar_ids = list(state_plan.get("exemplar_ids", []))
        profile_token = state_plan.get("profile_token")
        distance = float(state_plan.get("distance", float("nan")))
        self.coverage_state.set_active_state_exemplar(
            exemplar_ids=exemplar_ids,
            distance=distance,
            profile_token=(
                None
                if profile_token is None
                else np.asarray(profile_token, dtype=np.float32).copy()
            ),
        )
        corridor.state_exemplar_id = ",".join(str(value) for value in exemplar_ids)
        corridor.state_exemplar_distance = distance

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
        state_plan = {
            "raw_fields": dict(result.raw_fields),
            "profile_token": result.profile_token,
            "exemplar_ids": list(result.exemplar_ids),
            "distance": float(result.distance),
        }
        if update_state:
            self._apply_state_conditioned_plan(corridor, state_plan)
        return state_plan

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
