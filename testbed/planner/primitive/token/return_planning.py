"""Return token planning orchestration for primitive planner runtime."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

import numpy as np

from testbed.planner.primitive.token.dig_planning import (
    DIG_CUT_PLANNER_MODE_RESIDUAL_CUT_INTENT,
    RESIDUAL_CUT_INTENT_NO_PLAN_REASON,
    ResidualCutIntentPlanProvider,
)
from testbed.planner.primitive.token.tokens import (
    DigCutTokenPlan,
    ReturnStartEnvelopeTokenPlan,
    ReturnStartEnvelopeTokenPlanner,
    ReturnTargetTokenPlan,
)

if TYPE_CHECKING:
    from testbed.planner.primitive.facts.capabilities import PrimitiveObservationFacts
    from testbed.planner.primitive.coverage.state import CoverageRuntimeState
    from testbed.planner.primitive.token.state import PrimitiveTokenRuntimeState


ReturnTargetPlanTuple = tuple[np.ndarray, dict[str, float | int], str, str, int]


def _noop() -> None:
    return None


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

    token_state: PrimitiveTokenRuntimeState
    coverage_state: CoverageRuntimeState
    dig_cut_planner_mode: Callable[[], str]
    return_target_token_planner: Callable[[], Any]
    return_start_envelope_token_planner: Callable[[], ReturnStartEnvelopeTokenPlanner]
    observation_facts: Callable[[dict[str, Any]], PrimitiveObservationFacts]
    select_next_coverage_corridor: Callable[[dict[str, Any]], Any]
    coverage_raw_fields: CoverageRawFieldsBuilder
    residual_cut_intent_return_target_plan_provider: (
        ResidualCutIntentPlanProvider | None
    ) = None
    ensure_coverage_corridors: Callable[[], None] = _noop


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
                planner.plan_conservative_pose(
                    self.observation_facts(obs).bucket_dig_area_pose()
                )
            )
        if mode == "operator_prior":
            return self.unpack_return_target_token_plan(
                planner.plan_operator_prior(
                    self.observation_facts(obs).bucket_dig_area_pose()
                )
            )
        if mode in {"operator_prior_coverage", "operator_prior_sweep_belief"}:
            corridor = ports.select_next_coverage_corridor(obs)
            corridor_id = int(corridor.corridor_id)
            ports.coverage_state.set_active_corridor_id(corridor_id)
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
        if mode == DIG_CUT_PLANNER_MODE_RESIDUAL_CUT_INTENT:
            return self.unpack_return_target_token_plan(
                self.build_residual_cut_intent_return_target_plan(obs)
            )
        raise ValueError(f"Unsupported dig_cut_planner mode {mode!r}.")

    def build_residual_cut_intent_return_target_plan(
        self,
        obs: dict[str, Any],
    ) -> ReturnTargetTokenPlan:
        provider = self.ports.residual_cut_intent_return_target_plan_provider
        if provider is None:
            raise ValueError(RESIDUAL_CUT_INTENT_NO_PLAN_REASON)
        result = provider(obs)
        if result is None:
            raise ValueError(RESIDUAL_CUT_INTENT_NO_PLAN_REASON)
        planner = self.ports.return_target_token_planner()
        if isinstance(result, DigCutTokenPlan):
            dig_cut_plan = result
        elif isinstance(result, tuple) and len(result) == 4:
            _token, raw_fields, source, fallback_reason = result
            if not isinstance(raw_fields, Mapping):
                raise TypeError(
                    "residual_cut_intent return target provider raw_fields must be a mapping"
                )
            dig_cut_plan = planner.dig_cut_planner.plan_from_raw_fields(
                dict(raw_fields),
                source=str(source),
                fallback_reason=str(fallback_reason),
            )
        else:
            raise TypeError(
                "residual_cut_intent return target provider must return "
                "DigCutTokenPlan or DigCutPlanTuple"
            )
        corridor_id = self.return_start_envelope_corridor_id_from_raw_fields(
            dict(dig_cut_plan.raw_fields)
        )
        return planner.plan_from_dig_cut_plan(
            dig_cut_plan,
            source_suffix=str(dig_cut_plan.source),
            corridor_id=-1 if corridor_id is None else int(corridor_id),
        )

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
        facts = self.observation_facts(obs)
        plan = self.ports.return_start_envelope_token_planner().plan(
            raw_fields=raw_fields,
            env_state=facts.env_state,
            qpos=facts.qpos,
            qvel=facts.qvel,
            cell_id=self.return_start_envelope_cell_id(corridor_id),
        )
        return self.apply_return_start_envelope_token_plan(plan)

    def apply_return_start_envelope_token_plan(
        self,
        plan: ReturnStartEnvelopeTokenPlan,
    ) -> np.ndarray:
        token_state = self.ports.token_state
        token_state.return_start_envelope_token_source = str(plan.source)
        token_state.return_start_envelope_use_prior_spatial_bounds = bool(
            plan.use_prior_spatial_bounds
        )
        token_state.return_start_envelope_use_prior_qpos_bounds = bool(
            plan.use_prior_qpos_bounds
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
                self.ports.token_state.return_start_envelope_use_prior_spatial_bounds
            ),
            use_prior_qpos_bounds=(
                self.ports.token_state.return_start_envelope_use_prior_qpos_bounds
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
            corridor = self.ports.coverage_state.corridor_by_id(int(corridor_id))
        except Exception:
            corridor = None
        if corridor is not None:
            return int(corridor.cell_id)
        if int(corridor_id) >= 0:
            return int(corridor_id)
        return None

    def return_start_envelope_corridor_id_from_raw_fields(
        self,
        raw_fields: Mapping[str, float | int],
    ) -> int | None:
        """Map a planned next-dig entry to the nearest coverage corridor."""

        try:
            entry_x = float(raw_fields.get("operator_entry_x_m", float("nan")))
            entry_z = float(raw_fields.get("operator_entry_z_m", float("nan")))
        except Exception:
            return None
        if not (np.isfinite(entry_x) and np.isfinite(entry_z)):
            return None

        self.ensure_coverage_corridors_available()
        best_corridor_id: int | None = None
        best_distance = float("inf")
        for corridor in self.ports.coverage_state.coverage_corridors:
            corridor_entry_x = float(getattr(corridor, "entry_x_m", float("nan")))
            corridor_entry_z = float(getattr(corridor, "entry_z_m", float("nan")))
            if not (np.isfinite(corridor_entry_x) and np.isfinite(corridor_entry_z)):
                continue
            distance = float(
                (entry_x - corridor_entry_x) ** 2
                + (entry_z - corridor_entry_z) ** 2
            )
            if distance < best_distance:
                best_distance = distance
                best_corridor_id = int(getattr(corridor, "corridor_id", -1))
        if best_corridor_id is None or best_corridor_id < 0:
            return None
        return int(best_corridor_id)

    def ensure_coverage_corridors_available(self) -> None:
        if self.ports.coverage_state.coverage_corridors:
            return
        try:
            self.ports.ensure_coverage_corridors()
        except Exception:
            return

    def observation_facts(
        self,
        obs: dict[str, Any],
    ) -> "PrimitiveObservationFacts":
        return self.ports.observation_facts(obs)

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
