"""Static coverage configuration owned by the coverage lane."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from testbed.planner.primitive.coverage.effects import (
    CoverageRuntimeConfig,
    CoverageUpdateConfig,
)
from testbed.planner.primitive.coverage.exemplars import (
    CoverageStateExemplarPlannerConfig,
)
from testbed.planner.primitive.coverage.facts import CoveragePlanningFactConfig
from testbed.planner.primitive.coverage.reports import CoverageReportConfig
from testbed.planner.primitive.coverage.selection import CoverageSelectionConfig
from testbed.planner.primitive.coverage.state import CoverageRuntimeState


@dataclass(frozen=True)
class PrimitiveCoverageStaticConfig:
    """Static coverage config snapshot used by coverage runtimes."""

    dig_cut_prior: dict[str, object]
    dig_cut_prior_path: str
    dig_cut_planner_mode: str
    action_dim: int

    candidate_layout: str
    entry_x_percentiles: tuple[str, ...]
    entry_z_percentiles: tuple[str, ...]
    cut_direction_percentile: str
    cut_length_percentile: str
    cut_depth_percentile: str
    payload_percentile: str

    use_env_removed_depth: bool
    max_attempts_per_corridor: int
    recent_selection_penalty: float
    unattempted_bonus: float
    attempt_penalty: float
    cell_confidence_weight: float
    rare_cell_source_fraction_threshold: float
    rare_cell_max_attempts: int
    recent_row_selection_penalty: float

    first_dig_strategy: str
    first_dig_preferred_corridor_id: int | None
    first_dig_preferred_bonus: float
    first_dig_proximity_weight: float
    first_dig_max_entry_distance_m: float | None
    first_dig_qpos_delta_weight: float
    first_dig_max_qpos_delta: np.ndarray | None
    pre_dig_align_controlled_dims: np.ndarray

    state_exemplars_enabled: bool
    state_exemplar_path: str
    state_exemplar_k: int
    state_exemplar_removed_depth_scale_m: float
    state_exemplar_target_cell_weight: float
    state_exemplar_temperature: float
    state_exemplar_skip_rejected: bool
    state_exemplar_score_weight: float
    state_exemplars_by_cell: dict[int, list[dict[str, object]]]

    multi_pass_enabled: bool
    multi_pass_max_passes: int
    multi_pass_min_remaining_depth_m: float

    low_productivity_payload_kg: float
    low_productivity_deposit_kg: float
    deplete_after_low_streak: int
    min_remaining_depth_m: float
    belief_depleted_score: float
    belief_gain_scale: float
    global_low_productivity_stop: int

    @property
    def prior_fields(self) -> dict[str, object]:
        fields = self.dig_cut_prior.get("fields", {})
        if not isinstance(fields, dict):
            return {}
        return dict(fields)

    def report_config(self) -> CoverageReportConfig:
        return CoverageReportConfig(
            state_exemplar_enabled=bool(self.state_exemplars_enabled),
            multi_pass_enabled=bool(self.multi_pass_enabled),
            multi_pass_max_passes=int(self.multi_pass_max_passes),
            multi_pass_min_remaining_depth_m=float(
                self.multi_pass_min_remaining_depth_m
            ),
            use_env_removed_depth=bool(self.use_env_removed_depth),
            candidate_layout=str(self.candidate_layout),
            first_dig_strategy=str(self.first_dig_strategy),
            first_dig_preferred_corridor_id=(
                None
                if self.first_dig_preferred_corridor_id is None
                else int(self.first_dig_preferred_corridor_id)
            ),
            first_dig_max_entry_distance_m=self.first_dig_max_entry_distance_m,
            first_dig_qpos_delta_weight=float(self.first_dig_qpos_delta_weight),
            first_dig_max_qpos_delta=self.first_dig_max_qpos_delta,
        )

    def selection_config(
        self,
        state: CoverageRuntimeState,
        *,
        cycle_index: int,
    ) -> CoverageSelectionConfig:
        max_qpos_delta = self.first_dig_max_qpos_delta
        return CoverageSelectionConfig(
            candidate_layout=str(self.candidate_layout),
            prior_fields=self.prior_fields,
            cut_depth_percentile=str(self.cut_depth_percentile),
            use_env_removed_depth=bool(self.use_env_removed_depth),
            max_attempts_per_corridor=int(self.max_attempts_per_corridor),
            recent_selection_penalty=float(self.recent_selection_penalty),
            unattempted_bonus=float(self.unattempted_bonus),
            attempt_penalty=float(self.attempt_penalty),
            cell_confidence_weight=float(self.cell_confidence_weight),
            rare_cell_source_fraction_threshold=float(
                self.rare_cell_source_fraction_threshold
            ),
            rare_cell_max_attempts=int(self.rare_cell_max_attempts),
            recent_row_selection_penalty=float(self.recent_row_selection_penalty),
            last_selected_corridor_id=int(state.coverage_last_selected_corridor_id),
            cycle_index=int(cycle_index),
            completed_dump_count=int(state.coverage_completed_dump_count),
            first_dig_strategy=str(self.first_dig_strategy),
            first_dig_preferred_corridor_id=(
                None
                if self.first_dig_preferred_corridor_id is None
                else int(self.first_dig_preferred_corridor_id)
            ),
            first_dig_preferred_bonus=float(self.first_dig_preferred_bonus),
            first_dig_proximity_weight=float(self.first_dig_proximity_weight),
            first_dig_max_entry_distance_m=(
                None
                if self.first_dig_max_entry_distance_m is None
                else float(self.first_dig_max_entry_distance_m)
            ),
            first_dig_qpos_delta_weight=float(self.first_dig_qpos_delta_weight),
            first_dig_max_qpos_delta=(
                None
                if max_qpos_delta is None
                else np.asarray(max_qpos_delta, dtype=np.float32).copy()
            ),
            pre_dig_align_controlled_dims=np.asarray(
                self.pre_dig_align_controlled_dims,
                dtype=bool,
            ).copy(),
            state_exemplars_enabled=bool(self.state_exemplars_enabled),
            state_exemplar_score_weight=float(self.state_exemplar_score_weight),
        )

    def planning_fact_config(self) -> CoveragePlanningFactConfig:
        return CoveragePlanningFactConfig(
            prior_fields=self.prior_fields,
            cut_direction_percentile=str(self.cut_direction_percentile),
            cut_length_percentile=str(self.cut_length_percentile),
            cut_depth_percentile=str(self.cut_depth_percentile),
            payload_percentile=str(self.payload_percentile),
        )

    def state_exemplar_planner_config(self) -> CoverageStateExemplarPlannerConfig:
        return CoverageStateExemplarPlannerConfig(
            enabled=bool(self.state_exemplars_enabled),
            path=str(self.state_exemplar_path),
            dig_cut_prior_path=str(self.dig_cut_prior_path),
            k=int(self.state_exemplar_k),
            removed_depth_scale_m=float(self.state_exemplar_removed_depth_scale_m),
            target_cell_weight=float(self.state_exemplar_target_cell_weight),
            temperature=float(self.state_exemplar_temperature),
            skip_rejected=bool(self.state_exemplar_skip_rejected),
        )

    def update_config(self) -> CoverageUpdateConfig:
        return CoverageUpdateConfig(
            prior_fields=self.prior_fields,
            use_env_removed_depth=bool(self.use_env_removed_depth),
            low_productivity_payload_kg=float(self.low_productivity_payload_kg),
            low_productivity_deposit_kg=float(self.low_productivity_deposit_kg),
            deplete_after_low_streak=int(self.deplete_after_low_streak),
            min_remaining_depth_m=float(self.min_remaining_depth_m),
            belief_depleted_score=float(self.belief_depleted_score),
            belief_gain_scale=float(self.belief_gain_scale),
        )

    def runtime_config(self) -> CoverageRuntimeConfig:
        return CoverageRuntimeConfig(
            multi_pass_enabled=bool(self.multi_pass_enabled),
            use_env_removed_depth=bool(self.use_env_removed_depth),
            multi_pass_max_passes=int(self.multi_pass_max_passes),
            multi_pass_min_remaining_depth_m=float(
                self.multi_pass_min_remaining_depth_m
            ),
        )


__all__ = ["PrimitiveCoverageStaticConfig"]
