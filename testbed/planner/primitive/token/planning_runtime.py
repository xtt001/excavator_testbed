"""Token planning service composition for primitive planner runtime."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.planner.primitive.facts.capabilities import PrimitiveObservationFacts
from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.token.dig_planning import (
    CoverageRawFieldsBuilder as DigCoverageRawFieldsBuilder,
    DigCutPlanTuple,
    PrimitiveDigTokenPlanningPorts,
    PrimitiveDigTokenPlanningService,
    ResidualCutIntentPlanProvider,
)
from testbed.planner.primitive.token.return_planning import (
    PrimitiveReturnTokenPlanningPorts,
    PrimitiveReturnTokenPlanningService,
    ReturnTargetPlanTuple,
)
from testbed.planner.primitive.token.state import PrimitiveTokenRuntimeState
from testbed.planner.primitive.token.tokens import (
    DigCutTokenPlan,
    DigDepthProfileTokenPlan,
    ReturnStartEnvelopeTokenPlan,
)


@dataclass(frozen=True)
class PrimitiveTokenPlanningRuntimePorts:
    """Typed ports for dig and return token planning service composition."""

    token_state: PrimitiveTokenRuntimeState
    coverage_state: CoverageRuntimeState
    dig_cut_planner_mode: Callable[[], str]
    dig_cut_planner_fallback_mode: Callable[[], str]
    cycle_index: Callable[[], int]
    dig_cut_token_planner: Callable[[], Any]
    dig_depth_profile_token_planner: Callable[[], Any]
    return_target_token_planner: Callable[[], Any]
    return_start_envelope_token_planner: Callable[[], Any]
    observation_facts: Callable[[dict[str, Any]], PrimitiveObservationFacts]
    select_next_coverage_corridor: Callable[[dict[str, Any]], Any]
    coverage_raw_fields: DigCoverageRawFieldsBuilder
    residual_cut_intent_plan_provider: ResidualCutIntentPlanProvider | None = None
    residual_cut_intent_return_target_plan_provider: (
        ResidualCutIntentPlanProvider | None
    ) = None
    ensure_coverage_corridors: Callable[[], None] = lambda: None


@dataclass(frozen=True)
class PrimitiveTokenPlanningRuntime:
    """Compose focused dig and return token planning services from typed ports."""

    ports: PrimitiveTokenPlanningRuntimePorts

    @classmethod
    def from_ports(
        cls,
        ports: PrimitiveTokenPlanningRuntimePorts,
    ) -> "PrimitiveTokenPlanningRuntime":
        return cls(ports=ports)

    def dig_token_planning_service(self) -> PrimitiveDigTokenPlanningService:
        return PrimitiveDigTokenPlanningService.from_ports(
            self.dig_token_planning_ports()
        )

    def dig_token_planning_ports(self) -> PrimitiveDigTokenPlanningPorts:
        ports = self.ports
        return PrimitiveDigTokenPlanningPorts(
            token_state=ports.token_state,
            coverage_state=ports.coverage_state,
            dig_cut_planner_mode=ports.dig_cut_planner_mode,
            dig_cut_planner_fallback_mode=ports.dig_cut_planner_fallback_mode,
            cycle_index=ports.cycle_index,
            dig_cut_token_planner=ports.dig_cut_token_planner,
            dig_depth_profile_token_planner=ports.dig_depth_profile_token_planner,
            observation_facts=ports.observation_facts,
            select_next_coverage_corridor=ports.select_next_coverage_corridor,
            coverage_raw_fields=ports.coverage_raw_fields,
            residual_cut_intent_plan_provider=(
                ports.residual_cut_intent_plan_provider
            ),
        )

    def return_token_planning_service(self) -> PrimitiveReturnTokenPlanningService:
        return PrimitiveReturnTokenPlanningService.from_ports(
            self.return_token_planning_ports()
        )

    def return_token_planning_ports(self) -> PrimitiveReturnTokenPlanningPorts:
        ports = self.ports
        return PrimitiveReturnTokenPlanningPorts(
            token_state=ports.token_state,
            coverage_state=ports.coverage_state,
            dig_cut_planner_mode=ports.dig_cut_planner_mode,
            return_target_token_planner=ports.return_target_token_planner,
            return_start_envelope_token_planner=(
                ports.return_start_envelope_token_planner
            ),
            observation_facts=ports.observation_facts,
            select_next_coverage_corridor=ports.select_next_coverage_corridor,
            coverage_raw_fields=ports.coverage_raw_fields,
            residual_cut_intent_return_target_plan_provider=(
                ports.residual_cut_intent_return_target_plan_provider
            ),
            ensure_coverage_corridors=ports.ensure_coverage_corridors,
        )

    def build_dig_depth_profile_tokens_for_obs(
        self,
        obs: dict[str, Any],
    ) -> np.ndarray:
        return (
            self.dig_token_planning_service()
            .build_dig_depth_profile_tokens_for_obs(obs)
        )

    def apply_dig_depth_profile_token_plan(
        self,
        plan: DigDepthProfileTokenPlan,
    ) -> np.ndarray:
        return (
            self.dig_token_planning_service()
            .apply_dig_depth_profile_token_plan(plan)
        )

    def build_live_dig_depth_profile_tokens_for_obs(
        self,
        obs: dict[str, Any],
        *,
        cell_id: int,
    ) -> np.ndarray:
        return (
            self.dig_token_planning_service()
            .build_live_dig_depth_profile_tokens_for_obs(obs, cell_id=cell_id)
        )

    def dig_depth_profile_prior_token(
        self,
        cell_id: int,
    ) -> tuple[np.ndarray | None, str, str]:
        return self.dig_token_planning_service().dig_depth_profile_prior_token(
            cell_id
        )

    def dig_depth_profile_prior_mapping(
        self,
        cell_id: int,
    ) -> tuple[dict[str, object] | None, str, str]:
        return self.dig_token_planning_service().dig_depth_profile_prior_mapping(
            cell_id
        )

    def dig_depth_profile_raw_fields(
        self,
        obs: dict[str, Any],
    ) -> dict[str, float | int]:
        return self.dig_token_planning_service().dig_depth_profile_raw_fields(obs)

    def dig_depth_profile_cell_id(self, obs: dict[str, Any]) -> int:
        return self.dig_token_planning_service().dig_depth_profile_cell_id(obs)

    def build_dig_cut_tokens_for_obs(self, obs: dict[str, Any]) -> np.ndarray:
        return self.dig_token_planning_service().build_dig_cut_tokens_for_obs(obs)

    def apply_dig_cut_token_plan(self, plan: DigCutTokenPlan) -> np.ndarray:
        return self.dig_token_planning_service().apply_dig_cut_token_plan(plan)

    def build_next_dig_cut_plan_for_return(
        self,
        obs: dict[str, Any],
    ) -> ReturnTargetPlanTuple:
        return (
            self.return_token_planning_service()
            .build_next_dig_cut_plan_for_return(obs)
        )

    def build_return_start_envelope_tokens_for_obs(
        self,
        obs: dict[str, Any],
        raw_fields: dict[str, float | int],
        *,
        corridor_id: int | None = None,
    ) -> np.ndarray:
        return (
            self.return_token_planning_service()
            .build_return_start_envelope_tokens_for_obs(
                obs,
                raw_fields,
                corridor_id=corridor_id,
            )
        )

    def apply_return_start_envelope_token_plan(
        self,
        plan: ReturnStartEnvelopeTokenPlan,
    ) -> np.ndarray:
        return (
            self.return_token_planning_service()
            .apply_return_start_envelope_token_plan(plan)
        )

    def condition_return_start_envelope_qpos_from_relocate(
        self,
        token: np.ndarray,
        *,
        raw_fields: dict[str, float | int],
        source: str,
    ) -> np.ndarray:
        return (
            self.return_token_planning_service()
            .condition_return_start_envelope_qpos_from_relocate(
                token,
                raw_fields=raw_fields,
                source=source,
            )
        )

    def return_start_envelope_prior_token(
        self,
        *,
        corridor_id: int | None,
    ) -> tuple[np.ndarray | None, str]:
        return self.return_token_planning_service().return_start_envelope_prior_token(
            corridor_id=corridor_id
        )

    def return_start_envelope_prior_mapping(
        self,
        *,
        corridor_id: int | None,
    ) -> tuple[dict[str, object] | None, str]:
        return (
            self.return_token_planning_service()
            .return_start_envelope_prior_mapping(corridor_id=corridor_id)
        )

    def return_start_envelope_prior_bounds(
        self,
        corridor_id: int | None,
    ) -> tuple[np.ndarray | None, np.ndarray | None]:
        return self.return_token_planning_service().return_start_envelope_prior_bounds(
            corridor_id
        )

    def return_start_envelope_cell_id(
        self,
        corridor_id: int | None,
    ) -> int | None:
        return self.return_token_planning_service().return_start_envelope_cell_id(
            corridor_id
        )

    def raw_fields_from_live_pose(
        self,
        obs: dict[str, Any],
    ) -> dict[str, float | int]:
        return self.dig_token_planning_service().raw_fields_from_live_pose(obs)

    def build_operator_prior_dig_cut_tokens(
        self,
        obs: dict[str, Any],
    ) -> DigCutPlanTuple:
        return self.dig_token_planning_service().build_operator_prior_dig_cut_tokens(
            obs
        )

    def build_operator_prior_coverage_dig_cut_tokens(
        self,
        obs: dict[str, Any],
    ) -> DigCutPlanTuple:
        return (
            self.dig_token_planning_service()
            .build_operator_prior_coverage_dig_cut_tokens(obs)
        )


__all__ = [
    "PrimitiveTokenPlanningRuntime",
    "PrimitiveTokenPlanningRuntimePorts",
]
