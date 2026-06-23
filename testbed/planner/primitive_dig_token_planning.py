"""Active dig token planning orchestration for primitive planner runtime."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

import numpy as np

from testbed.data.operator_first_v2_2 import (
    DIG_CUT_DEPTH_SCALE_M,
    DIG_CUT_LENGTH_SCALE_M,
    DIG_CUT_PAYLOAD_SCALE_KG,
    DIG_CUT_POSITION_SCALE_M,
    DIG_CUT_TOKEN_DIM,
)
from testbed.data.schema import ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX
from testbed.planner.primitive_tokens import (
    DigCutTokenPlan,
    DigDepthProfileTokenPlan,
    DigDepthProfileTokenPlanner,
    DigDepthProfileTokenPlanningError,
)

if TYPE_CHECKING:
    from testbed.planner.primitive_coverage_state import CoverageRuntimeState
    from testbed.planner.primitive_token_state import PrimitiveTokenRuntimeState


DigCutPlanTuple = tuple[np.ndarray, dict[str, float | int], str, str]


class CoverageRawFieldsBuilder(Protocol):
    """Build dig-cut raw fields from a coverage corridor."""

    def __call__(
        self,
        corridor: Any,
        *,
        obs: dict[str, Any],
        update_state: bool = False,
    ) -> dict[str, float | int]:
        ...


@dataclass(frozen=True)
class PrimitiveDigTokenPlanningPorts:
    """Shell-owned readers, writers, and token algorithm providers."""

    token_state: PrimitiveTokenRuntimeState
    coverage_state: CoverageRuntimeState
    dig_cut_planner_mode: Callable[[], str]
    dig_cut_planner_fallback_mode: Callable[[], str]
    cycle_index: Callable[[], int]
    dig_cut_token_planner: Callable[[], Any]
    dig_depth_profile_token_planner: Callable[[], Any]
    bucket_dig_area_pose: Callable[[dict[str, Any]], tuple[float, float, float] | None]
    deposited_mass: Callable[[dict[str, Any]], float]
    env_state: Callable[[dict[str, Any]], np.ndarray]

    select_next_coverage_corridor: Callable[[dict[str, Any]], Any]
    coverage_raw_fields: CoverageRawFieldsBuilder


@dataclass(frozen=True)
class PrimitiveDigTokenPlanningService:
    """Own active dig-cut and dig-depth-profile planning sequencing."""

    ports: PrimitiveDigTokenPlanningPorts

    @classmethod
    def from_ports(
        cls,
        ports: PrimitiveDigTokenPlanningPorts,
    ) -> "PrimitiveDigTokenPlanningService":
        return cls(ports=ports)

    def build_dig_cut_tokens_for_obs(self, obs: dict[str, Any]) -> np.ndarray:
        ports = self.ports
        token_state = ports.token_state
        coverage_state = ports.coverage_state
        mode = str(ports.dig_cut_planner_mode())
        planner = ports.dig_cut_token_planner()
        token_state.dig_cut_fallback_reason = ""
        if self._pending_dig_cut_matches_current_cycle():
            plan = planner.plan_pending_return_target(
                tokens=token_state.pending_dig_cut_tokens,
                raw_fields=token_state.pending_dig_cut_raw_fields,
            )
            corridor_id = int(token_state.pending_dig_cut_corridor_id)
            coverage_state.set_selected_corridor_ids(
                active_corridor_id=corridor_id,
                last_selected_corridor_id=corridor_id,
            )
            coverage_state.set_current_payload_gain_kg(0.0)
            coverage_state.set_cycle_start_deposit_kg(ports.deposited_mass(obs))
            profile_token = token_state.pending_dig_depth_profile_tokens
            coverage_state.set_active_state_exemplar(
                exemplar_ids=list(token_state.pending_dig_state_exemplar_ids),
                distance=float(token_state.pending_dig_state_exemplar_distance),
                profile_token=(
                    None
                    if profile_token is None
                    else np.asarray(profile_token, dtype=np.float32).astype(
                        np.float32
                    ).copy()
                ),
            )
            return self.apply_dig_cut_token_plan(plan)
        if mode == "conservative_pose":
            return self.apply_dig_cut_token_plan(
                planner.plan_conservative_pose(ports.bucket_dig_area_pose(obs))
            )
        if mode == "operator_prior":
            try:
                return self.apply_dig_cut_token_plan(
                    planner.plan_operator_prior(ports.bucket_dig_area_pose(obs))
                )
            except Exception as exc:
                if str(ports.dig_cut_planner_fallback_mode()) != "conservative_pose":
                    raise
                return self.apply_dig_cut_token_plan(
                    planner.plan_fallback_conservative_pose(
                        ports.bucket_dig_area_pose(obs),
                        fallback_reason=str(exc),
                    )
                )
        if mode in {"operator_prior_coverage", "operator_prior_sweep_belief"}:
            try:
                _token, raw_fields, source, fallback_reason = (
                    self.build_operator_prior_coverage_dig_cut_tokens(obs)
                )
                return self.apply_dig_cut_token_plan(
                    planner.plan_from_raw_fields(
                        raw_fields,
                        source=source,
                        fallback_reason=fallback_reason,
                    )
                )
            except Exception as exc:
                if str(ports.dig_cut_planner_fallback_mode()) != "conservative_pose":
                    raise
                return self.apply_dig_cut_token_plan(
                    planner.plan_fallback_conservative_pose(
                        ports.bucket_dig_area_pose(obs),
                        fallback_reason=str(exc),
                    )
                )
        raise ValueError(f"Unsupported dig_cut_planner mode {mode!r}.")

    def apply_dig_cut_token_plan(self, plan: DigCutTokenPlan) -> np.ndarray:
        token_state = self.ports.token_state
        token_state.dig_cut_token_source = str(plan.source)
        token_state.dig_cut_fallback_reason = str(plan.fallback_reason)
        token_state.dig_cut_token_in_prior_p10_p90 = bool(
            plan.in_prior_p10_p90
        )
        return plan.token.copy()

    def build_operator_prior_dig_cut_tokens(
        self,
        obs: dict[str, Any],
    ) -> DigCutPlanTuple:
        plan = self.ports.dig_cut_token_planner().plan_operator_prior(
            self.ports.bucket_dig_area_pose(obs)
        )
        return self.unpack_dig_cut_token_plan(plan)

    def build_operator_prior_coverage_dig_cut_tokens(
        self,
        obs: dict[str, Any],
    ) -> DigCutPlanTuple:
        ports = self.ports
        corridor = ports.select_next_coverage_corridor(obs)
        ports.coverage_state.set_current_payload_gain_kg(0.0)
        ports.coverage_state.set_cycle_start_deposit_kg(ports.deposited_mass(obs))
        raw_fields = ports.coverage_raw_fields(
            corridor,
            obs=obs,
            update_state=True,
        )
        plan = ports.dig_cut_token_planner().plan_from_raw_fields(
            raw_fields,
            source="operator_prior_coverage",
        )
        return self.unpack_dig_cut_token_plan(plan)

    @staticmethod
    def unpack_dig_cut_token_plan(plan: DigCutTokenPlan) -> DigCutPlanTuple:
        return (
            plan.token.copy(),
            dict(plan.raw_fields),
            str(plan.source),
            str(plan.fallback_reason),
        )

    def build_dig_depth_profile_tokens_for_obs(
        self,
        obs: dict[str, Any],
    ) -> np.ndarray:
        planner = self.ports.dig_depth_profile_token_planner()
        try:
            plan = planner.plan(
                cell_id=self.dig_depth_profile_cell_id(obs),
                raw_fields=self.dig_depth_profile_raw_fields(obs),
                env_state=self.ports.env_state(obs),
                state_exemplar_profile_token=(
                    self.ports.coverage_state.coverage_active_state_exemplar_profile_token
                ),
            )
        except DigDepthProfileTokenPlanningError as exc:
            token_state = self.ports.token_state
            token_state.dig_depth_profile_token_source = str(exc.token_source)
            token_state.dig_depth_profile_fallback_reason = str(
                exc.fallback_reason
            )
            raise
        return self.apply_dig_depth_profile_token_plan(plan)

    def apply_dig_depth_profile_token_plan(
        self,
        plan: DigDepthProfileTokenPlan,
    ) -> np.ndarray:
        token_state = self.ports.token_state
        token_state.dig_depth_profile_token_source = str(plan.source)
        token_state.dig_depth_profile_fallback_reason = str(plan.fallback_reason)
        return plan.token.copy()

    def build_live_dig_depth_profile_tokens_for_obs(
        self,
        obs: dict[str, Any],
        *,
        cell_id: int,
    ) -> np.ndarray:
        return self.ports.dig_depth_profile_token_planner().live_plan_token(
            cell_id=int(cell_id),
            raw_fields=self.dig_depth_profile_raw_fields(obs),
            env_state=self.ports.env_state(obs),
        )

    def dig_depth_profile_prior_token(
        self,
        cell_id: int,
    ) -> tuple[np.ndarray | None, str, str]:
        return self.ports.dig_depth_profile_token_planner().prior_token(cell_id)

    def dig_depth_profile_prior_mapping(
        self,
        cell_id: int,
    ) -> tuple[dict[str, object] | None, str, str]:
        return self.ports.dig_depth_profile_token_planner().prior_mapping(cell_id)

    @staticmethod
    def dig_depth_profile_token_from_prior_mapping(
        mapping: dict[str, object],
    ) -> np.ndarray | None:
        return DigDepthProfileTokenPlanner.token_from_prior_mapping(mapping)

    def dig_depth_profile_raw_fields(
        self,
        obs: dict[str, Any],
    ) -> dict[str, float | int]:
        pending_raw = self.ports.token_state.pending_dig_cut_raw_fields
        if pending_raw is not None and self._pending_cycle_matches_current_cycle():
            return dict(pending_raw)
        corridor = self.ports.coverage_state.active_corridor()
        if corridor is not None:
            return self.ports.coverage_raw_fields(corridor, obs=obs)
        raw_fields = self.raw_fields_from_live_pose(obs)
        token = np.asarray(
            self.ports.token_state.dig_cut_tokens,
            dtype=np.float32,
        ).reshape(-1)
        if token.size >= DIG_CUT_TOKEN_DIM:
            raw_fields.update(
                {
                    "operator_entry_x_m": float(token[0])
                    * DIG_CUT_POSITION_SCALE_M,
                    "operator_entry_z_m": float(token[1])
                    * DIG_CUT_POSITION_SCALE_M,
                    "operator_exit_x_m": float(token[2]) * DIG_CUT_POSITION_SCALE_M,
                    "operator_exit_z_m": float(token[3]) * DIG_CUT_POSITION_SCALE_M,
                    "operator_cut_direction_x": float(token[4]),
                    "operator_cut_direction_z": float(token[5]),
                    "operator_cut_length_m": float(token[6])
                    * DIG_CUT_LENGTH_SCALE_M,
                    "operator_cut_depth_peak_m": float(token[7])
                    * DIG_CUT_DEPTH_SCALE_M,
                    "operator_cut_payload_gain_kg": float(token[8])
                    * DIG_CUT_PAYLOAD_SCALE_KG,
                    "operator_cut_valid": int(float(token[9]) > 0.5),
                }
            )
        return raw_fields

    def raw_fields_from_live_pose(
        self,
        obs: dict[str, Any],
    ) -> dict[str, float | int]:
        return self.ports.dig_cut_token_planner().raw_fields_from_live_pose(
            self.ports.bucket_dig_area_pose(obs)
        )

    def dig_depth_profile_cell_id(self, obs: dict[str, Any]) -> int:
        pending_corridor_id = int(self.ports.token_state.pending_dig_cut_corridor_id)
        if pending_corridor_id >= 0 and self._pending_cycle_matches_current_cycle():
            corridor = self.ports.coverage_state.corridor_by_id(
                pending_corridor_id
            )
            if corridor is not None:
                return int(corridor.cell_id)
        corridor = self.ports.coverage_state.active_corridor()
        if corridor is not None:
            return int(corridor.cell_id)
        env_state = self.ports.env_state(obs)
        if len(env_state) > ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX:
            value = float(env_state[ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX])
            if np.isfinite(value):
                return int(max(0, min(5, round(value))))
        return 0

    def _pending_dig_cut_matches_current_cycle(self) -> bool:
        return bool(
            self.ports.token_state.pending_dig_cut_tokens is not None
            and self._pending_cycle_matches_current_cycle()
        )

    def _pending_cycle_matches_current_cycle(self) -> bool:
        return bool(
            int(self.ports.token_state.pending_dig_cut_cycle_id)
            == int(self.ports.cycle_index())
        )


__all__ = [
    "CoverageRawFieldsBuilder",
    "DigCutPlanTuple",
    "PrimitiveDigTokenPlanningPorts",
    "PrimitiveDigTokenPlanningService",
]
