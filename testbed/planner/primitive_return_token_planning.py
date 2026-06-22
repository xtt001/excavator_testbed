"""Return token planning orchestration for primitive planner runtime."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from testbed.planner.primitive_tokens import (
    ReturnStartEnvelopeTokenPlan,
    ReturnStartEnvelopeTokenPlanner,
    ReturnTargetTokenPlan,
)


ReturnTargetPlanTuple = tuple[np.ndarray, dict[str, float | int], str, str, int]


class CoverageRawFieldsBuilder(Protocol):
    """Build dig-cut raw fields from a selected coverage corridor."""

    def __call__(
        self,
        corridor: Any,
        *,
        obs: dict[str, Any],
        update_state: bool,
    ) -> dict[str, float | int]:
        ...


@dataclass(frozen=True)
class PrimitiveReturnTokenPlanningPorts:
    """Shell-owned readers, writers, and token algorithm providers."""

    dig_cut_planner_mode: Callable[[], str]
    return_target_token_planner: Callable[[], Any]
    return_start_envelope_token_planner: Callable[[], ReturnStartEnvelopeTokenPlanner]
    bucket_dig_area_pose: Callable[[dict[str, Any]], tuple[float, float, float] | None]
    select_next_coverage_corridor: Callable[[dict[str, Any]], Any]
    set_coverage_active_corridor_id: Callable[[int], None]
    coverage_raw_fields: CoverageRawFieldsBuilder
    env_state: Callable[[dict[str, Any]], np.ndarray]
    qpos: Callable[[dict[str, Any]], np.ndarray]
    qvel: Callable[[dict[str, Any]], np.ndarray]
    coverage_corridor_by_id: Callable[[int], Any | None]
    get_return_start_envelope_use_prior_spatial_bounds: Callable[[], bool]
    get_return_start_envelope_use_prior_qpos_bounds: Callable[[], bool]
    set_return_start_envelope_token_source: Callable[[str], None]
    set_return_start_envelope_use_prior_spatial_bounds: Callable[[bool], None]
    set_return_start_envelope_use_prior_qpos_bounds: Callable[[bool], None]


@dataclass(frozen=True)
class PrimitiveReturnTokenPlanningService:
    """Own return-target and return start-envelope token planning sequencing."""

    ports: PrimitiveReturnTokenPlanningPorts

    @classmethod
    def from_ports(
        cls,
        ports: PrimitiveReturnTokenPlanningPorts,
    ) -> "PrimitiveReturnTokenPlanningService":
        return cls(ports=ports)

    def build_next_dig_cut_plan_for_return(
        self,
        obs: dict[str, Any],
    ) -> ReturnTargetPlanTuple:
        ports = self.ports
        planner = ports.return_target_token_planner()
        mode = str(ports.dig_cut_planner_mode())
        if mode == "conservative_pose":
            return self.unpack_return_target_token_plan(
                planner.plan_conservative_pose(ports.bucket_dig_area_pose(obs))
            )
        if mode == "operator_prior":
            return self.unpack_return_target_token_plan(
                planner.plan_operator_prior(ports.bucket_dig_area_pose(obs))
            )
        if mode in {"operator_prior_coverage", "operator_prior_sweep_belief"}:
            corridor = ports.select_next_coverage_corridor(obs)
            corridor_id = int(corridor.corridor_id)
            ports.set_coverage_active_corridor_id(corridor_id)
            raw_fields = ports.coverage_raw_fields(
                corridor,
                obs=obs,
                update_state=True,
            )
            return self.unpack_return_target_token_plan(
                planner.plan_from_coverage_raw_fields(
                    raw_fields,
                    dig_cut_planner_mode=mode,
                    corridor_id=corridor_id,
                )
            )
        raise ValueError(f"Unsupported dig_cut_planner mode {mode!r}.")

    @staticmethod
    def unpack_return_target_token_plan(
        plan: ReturnTargetTokenPlan,
    ) -> ReturnTargetPlanTuple:
        return (
            plan.token.copy(),
            dict(plan.raw_fields),
            str(plan.source),
            str(plan.fallback_reason),
            int(plan.corridor_id),
        )

    def build_return_start_envelope_tokens_for_obs(
        self,
        obs: dict[str, Any],
        raw_fields: dict[str, float | int],
        *,
        corridor_id: int | None = None,
    ) -> np.ndarray:
        plan = self.ports.return_start_envelope_token_planner().plan(
            raw_fields=raw_fields,
            env_state=self.ports.env_state(obs),
            qpos=self.ports.qpos(obs),
            qvel=self.ports.qvel(obs),
            cell_id=self.return_start_envelope_cell_id(corridor_id),
        )
        return self.apply_return_start_envelope_token_plan(plan)

    def apply_return_start_envelope_token_plan(
        self,
        plan: ReturnStartEnvelopeTokenPlan,
    ) -> np.ndarray:
        self.ports.set_return_start_envelope_token_source(str(plan.source))
        self.ports.set_return_start_envelope_use_prior_spatial_bounds(
            bool(plan.use_prior_spatial_bounds)
        )
        self.ports.set_return_start_envelope_use_prior_qpos_bounds(
            bool(plan.use_prior_qpos_bounds)
        )
        return plan.token.copy()

    def condition_return_start_envelope_qpos_from_relocate(
        self,
        token: np.ndarray,
        *,
        raw_fields: dict[str, float | int],
        source: str,
    ) -> np.ndarray:
        plan = self.ports.return_start_envelope_token_planner().condition_token(
            token,
            raw_fields=raw_fields,
            source=source,
            use_prior_spatial_bounds=(
                self.ports.get_return_start_envelope_use_prior_spatial_bounds()
            ),
            use_prior_qpos_bounds=(
                self.ports.get_return_start_envelope_use_prior_qpos_bounds()
            ),
        )
        return self.apply_return_start_envelope_token_plan(plan)

    def return_start_envelope_prior_token(
        self,
        *,
        corridor_id: int | None,
    ) -> tuple[np.ndarray | None, str]:
        return self.ports.return_start_envelope_token_planner().prior_token(
            cell_id=self.return_start_envelope_cell_id(corridor_id)
        )

    def return_start_envelope_prior_mapping(
        self,
        *,
        corridor_id: int | None,
    ) -> tuple[dict[str, object] | None, str]:
        return self.ports.return_start_envelope_token_planner().prior_mapping(
            cell_id=self.return_start_envelope_cell_id(corridor_id)
        )

    def return_start_envelope_prior_bounds(
        self,
        corridor_id: int | None,
    ) -> tuple[np.ndarray | None, np.ndarray | None]:
        return self.ports.return_start_envelope_token_planner().prior_bounds(
            cell_id=self.return_start_envelope_cell_id(corridor_id)
        )

    def return_start_envelope_cell_id(
        self,
        corridor_id: int | None,
    ) -> int | None:
        if corridor_id is None:
            return None
        try:
            corridor = self.ports.coverage_corridor_by_id(int(corridor_id))
        except Exception:
            corridor = None
        if corridor is not None:
            return int(corridor.cell_id)
        if int(corridor_id) >= 0:
            return int(corridor_id)
        return None

    @staticmethod
    def return_start_envelope_token_from_prior_mapping(
        mapping: dict[str, object],
    ) -> np.ndarray | None:
        return ReturnStartEnvelopeTokenPlanner.token_from_prior_mapping(mapping)


__all__ = [
    "CoverageRawFieldsBuilder",
    "PrimitiveReturnTokenPlanningPorts",
    "PrimitiveReturnTokenPlanningService",
    "ReturnTargetPlanTuple",
]
