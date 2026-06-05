"""Return target plan state assembly for primitive scheduler facades."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.contracts.primitive_tokens import (
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_TARGET_TOKEN_DIM,
)


@dataclass(frozen=True)
class ReturnTargetPlanBuild:
    token: Any
    raw_fields: Mapping[str, float | int]
    return_start_envelope_tokens: Any
    source: str
    fallback_reason: str
    corridor_id: int


@dataclass(frozen=True)
class ReturnTargetExemplarSnapshot:
    depth_profile_token: Any | None = None
    state_exemplar_ids: Sequence[str] = ()
    state_exemplar_distance: float = float("nan")


@dataclass(frozen=True)
class ReturnTargetPlanState:
    return_target_tokens: np.ndarray
    return_start_envelope_tokens: np.ndarray
    return_target_token_source: str
    return_target_fallback_reason: str
    return_target_planned_cycle_id: int
    pending_dig_cut_cycle_id: int
    pending_dig_cut_raw_fields: dict[str, float | int] | None
    pending_dig_cut_tokens: np.ndarray | None
    pending_dig_cut_corridor_id: int
    pending_dig_depth_profile_tokens: np.ndarray | None
    pending_dig_state_exemplar_ids: tuple[str, ...]
    pending_dig_state_exemplar_distance: float
    return_start_envelope_token_source: str | None = None


class ReturnTargetPlanService:
    """Assembles return target planner state without selecting targets."""

    @staticmethod
    def should_hold_plan(
        *,
        hold_until_skill_exit: bool,
        planned_cycle_id: int,
        cycle_index: int,
    ) -> bool:
        return bool(
            hold_until_skill_exit and int(planned_cycle_id) == int(cycle_index)
        )

    @staticmethod
    def success_state(
        *,
        cycle_index: int,
        plan: ReturnTargetPlanBuild,
        exemplar: ReturnTargetExemplarSnapshot,
    ) -> ReturnTargetPlanState:
        target_tokens = np.asarray(plan.token, dtype=np.float32).copy()
        envelope_tokens = np.asarray(
            plan.return_start_envelope_tokens,
            dtype=np.float32,
        ).copy()
        depth_profile = (
            None
            if exemplar.depth_profile_token is None
            else np.asarray(exemplar.depth_profile_token, dtype=np.float32).copy()
        )
        return ReturnTargetPlanState(
            return_target_tokens=target_tokens,
            return_start_envelope_tokens=envelope_tokens,
            return_target_token_source=str(plan.source),
            return_target_fallback_reason=str(plan.fallback_reason),
            return_target_planned_cycle_id=int(cycle_index),
            pending_dig_cut_cycle_id=int(cycle_index) + 1,
            pending_dig_cut_raw_fields=dict(plan.raw_fields),
            pending_dig_cut_tokens=target_tokens.copy(),
            pending_dig_cut_corridor_id=int(plan.corridor_id),
            pending_dig_depth_profile_tokens=depth_profile,
            pending_dig_state_exemplar_ids=tuple(exemplar.state_exemplar_ids),
            pending_dig_state_exemplar_distance=float(
                exemplar.state_exemplar_distance
            ),
        )

    @staticmethod
    def failure_state(
        *,
        cycle_index: int,
        reason: object,
    ) -> ReturnTargetPlanState:
        return ReturnTargetPlanState(
            return_target_tokens=np.zeros(
                RETURN_TARGET_TOKEN_DIM,
                dtype=np.float32,
            ),
            return_start_envelope_tokens=np.zeros(
                RETURN_START_ENVELOPE_TOKEN_DIM,
                dtype=np.float32,
            ),
            return_target_token_source="fallback_zero",
            return_start_envelope_token_source="fallback_zero",
            return_target_fallback_reason=str(reason),
            return_target_planned_cycle_id=int(cycle_index),
            pending_dig_cut_cycle_id=-1,
            pending_dig_cut_raw_fields=None,
            pending_dig_cut_tokens=None,
            pending_dig_cut_corridor_id=-1,
            pending_dig_depth_profile_tokens=None,
            pending_dig_state_exemplar_ids=(),
            pending_dig_state_exemplar_distance=float("nan"),
        )
