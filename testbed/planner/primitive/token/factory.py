"""Token planner factory composition for primitive planner runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.planner.primitive.token.tokens import (
    DigCutTokenPlanner,
    DigDepthProfileTokenPlanner,
    GoalTokenProvider,
    ReturnRelocateTokenPlanner,
    ReturnStartEnvelopeConditioningConfig,
    ReturnStartEnvelopeTokenPlanner,
    ReturnTargetTokenPlanner,
)


@dataclass(frozen=True)
class PrimitiveTokenPlannerFactoryConfig:
    """Static token planner construction inputs normalized by the policy shell."""

    goal_sequence: tuple[int, ...]
    goal_scenario_id: str
    goal_depth_norm: float
    goal_dump_target_norm: float
    dig_cut_prior: dict[str, Any]
    dig_depth_profile_source: str
    dig_depth_profile_required: bool
    dig_depth_profile_allow_live_fallback: bool
    dig_depth_profile_allow_global_fallback: bool
    return_target_token_source_prefix: str
    return_start_envelope_use_cell_prior: bool
    return_start_envelope_min_source_count: int
    return_start_envelope_min_source_fraction: float
    return_start_envelope_qpos_from_relocate_enabled: bool
    return_start_envelope_qpos_from_relocate_coefficients: np.ndarray | None
    return_start_envelope_qpos_from_relocate_min: np.ndarray | None
    return_start_envelope_qpos_from_relocate_max: np.ndarray | None
    return_start_envelope_qpos_from_relocate_use_prior_qpos_bounds: bool
    return_start_envelope_spatial_from_relocate_enabled: bool
    return_start_envelope_spatial_from_relocate_coefficients: np.ndarray | None
    return_start_envelope_spatial_from_relocate_min: np.ndarray | None
    return_start_envelope_spatial_from_relocate_max: np.ndarray | None
    return_start_envelope_spatial_from_relocate_use_prior_spatial_bounds: bool


@dataclass(frozen=True)
class PrimitiveTokenPlannerFactory:
    """Build token planners from explicit static token configuration."""

    config: PrimitiveTokenPlannerFactoryConfig

    def goal_token_provider(self) -> GoalTokenProvider:
        config = self.config
        return GoalTokenProvider(
            goal_sequence=tuple(config.goal_sequence),
            scenario_id=str(config.goal_scenario_id),
            depth_norm=float(config.goal_depth_norm),
            dump_target_norm=float(config.goal_dump_target_norm),
        )

    def goal_tokens_for_cycle(self, cycle_index: int) -> np.ndarray | None:
        return self.goal_token_provider().tokens_for_cycle(cycle_index)

    def goal_sector_id(self, cycle_index: int) -> int:
        return self.goal_token_provider().sector_id(cycle_index)

    def next_goal_sector_id(self, cycle_index: int) -> int:
        return self.goal_token_provider().next_sector_id(cycle_index)

    def dig_cut_token_planner(self) -> DigCutTokenPlanner:
        return DigCutTokenPlanner(prior=dict(self.config.dig_cut_prior or {}))

    def dig_depth_profile_token_planner(self) -> DigDepthProfileTokenPlanner:
        config = self.config
        return DigDepthProfileTokenPlanner(
            prior=dict(config.dig_cut_prior or {}),
            source=str(config.dig_depth_profile_source),
            required=bool(config.dig_depth_profile_required),
            allow_live_fallback=bool(config.dig_depth_profile_allow_live_fallback),
            allow_global_fallback=bool(config.dig_depth_profile_allow_global_fallback),
        )

    def return_target_token_planner(self) -> ReturnTargetTokenPlanner:
        return ReturnTargetTokenPlanner(
            dig_cut_planner=self.dig_cut_token_planner(),
            source_prefix=str(self.config.return_target_token_source_prefix),
        )

    def return_relocate_token_planner(self) -> ReturnRelocateTokenPlanner:
        return ReturnRelocateTokenPlanner()

    def return_start_envelope_token_planner(
        self,
    ) -> ReturnStartEnvelopeTokenPlanner:
        config = self.config
        return ReturnStartEnvelopeTokenPlanner(
            prior=dict(config.dig_cut_prior or {}),
            use_cell_prior=bool(config.return_start_envelope_use_cell_prior),
            min_source_count=int(config.return_start_envelope_min_source_count),
            min_source_fraction=float(
                config.return_start_envelope_min_source_fraction
            ),
            conditioning=ReturnStartEnvelopeConditioningConfig(
                qpos_enabled=bool(
                    config.return_start_envelope_qpos_from_relocate_enabled
                ),
                qpos_coefficients=(
                    config.return_start_envelope_qpos_from_relocate_coefficients
                ),
                qpos_min=config.return_start_envelope_qpos_from_relocate_min,
                qpos_max=config.return_start_envelope_qpos_from_relocate_max,
                qpos_use_prior_bounds=bool(
                    config.return_start_envelope_qpos_from_relocate_use_prior_qpos_bounds
                ),
                spatial_enabled=bool(
                    config.return_start_envelope_spatial_from_relocate_enabled
                ),
                spatial_coefficients=(
                    config.return_start_envelope_spatial_from_relocate_coefficients
                ),
                spatial_min=config.return_start_envelope_spatial_from_relocate_min,
                spatial_max=config.return_start_envelope_spatial_from_relocate_max,
                spatial_use_prior_bounds=bool(
                    config.return_start_envelope_spatial_from_relocate_use_prior_spatial_bounds
                ),
            ),
        )


__all__ = [
    "PrimitiveTokenPlannerFactory",
    "PrimitiveTokenPlannerFactoryConfig",
]
