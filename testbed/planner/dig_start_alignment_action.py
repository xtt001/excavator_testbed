"""Pre-dig alignment target projection and action helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from testbed.contracts.primitive_tokens import (
    CUT_ENTRY_X_IDX,
    CUT_ENTRY_Z_IDX,
    DIG_CUT_TOKEN_DIM,
)
from testbed.planner.dig_start_alignment_context import (
    DigStartAlignmentConfig,
    DigStartAlignmentFacts,
    build_dig_start_alignment_facts_from_observation_view,
)

if TYPE_CHECKING:
    from testbed.planner.snapshots import PlannerObservationView


@dataclass(frozen=True)
class AlignmentActionDecision:
    action: np.ndarray
    error: np.ndarray
    entry_error_m: float


class DigStartAlignmentActionService:
    """Computes pre-dig alignment targets and servo actions."""

    def target_from_token(
        self,
        *,
        token: np.ndarray,
        qpos: np.ndarray,
        config: DigStartAlignmentConfig,
    ) -> np.ndarray:
        action_dim = int(config.action_dim)
        token = np.asarray(token, dtype=np.float32).reshape(-1)
        if len(token) < 2:
            token = np.zeros(DIG_CUT_TOKEN_DIM, dtype=np.float32)
        features = np.asarray(
            [
                1.0,
                float(token[CUT_ENTRY_X_IDX]),
                float(token[CUT_ENTRY_Z_IDX]),
            ],
            dtype=np.float32,
        )
        coefficients = np.asarray(
            config.qpos_from_token_coefficients,
            dtype=np.float32,
        ).reshape(action_dim, 3)
        qpos_min = np.asarray(config.qpos_min, dtype=np.float32).reshape(action_dim)
        qpos_max = np.asarray(config.qpos_max, dtype=np.float32).reshape(action_dim)
        current_qpos = np.asarray(qpos, dtype=np.float32).reshape(action_dim)
        target = coefficients @ features
        target = np.clip(target, qpos_min, qpos_max)
        if config.bucket_target_qpos is not None and action_dim >= 4:
            target[3] = float(
                np.clip(
                    config.bucket_target_qpos,
                    qpos_min[3],
                    qpos_max[3],
                )
            )
        controlled = np.asarray(config.controlled_dims, dtype=bool).reshape(action_dim)
        intent_dims = config.entry_intent_controlled_dims
        if intent_dims is not None:
            intent_controlled = np.asarray(intent_dims, dtype=bool).reshape(action_dim)
            hold_dims = controlled & ~intent_controlled
            target[hold_dims] = current_qpos[hold_dims]
        target[~controlled] = current_qpos[~controlled]
        return target.astype(np.float32).copy()

    def target_from_token_from_observation_view(
        self,
        *,
        view: PlannerObservationView,
        token: np.ndarray,
        config: DigStartAlignmentConfig,
        entry_error_m: float = float("nan"),
        qpos: np.ndarray | None = None,
        cycle_index: int = 0,
        hold_count: int = 0,
    ) -> np.ndarray:
        facts = build_dig_start_alignment_facts_from_observation_view(
            view=view,
            entry_error_m=entry_error_m,
            qpos=qpos,
            cycle_index=cycle_index,
            hold_count=hold_count,
        )
        return self.target_from_token(
            token=token,
            qpos=facts.qpos,
            config=config,
        )

    def action_for_target(
        self,
        *,
        qpos: np.ndarray,
        qvel: np.ndarray,
        target_qpos: np.ndarray,
        config: DigStartAlignmentConfig,
    ) -> np.ndarray:
        action = pd_servo_action(
            qpos=qpos,
            qvel=qvel,
            target_qpos=target_qpos,
            kp=config.kp,
            kd=config.kd,
            action_clip=config.action_clip,
            action_signs=config.action_signs,
        )
        controlled = np.asarray(config.controlled_dims, dtype=bool).reshape(
            int(config.action_dim)
        )
        action[~controlled] = 0.0
        return action.astype(np.float32).copy()

    def action_decision(
        self,
        facts: DigStartAlignmentFacts,
        config: DigStartAlignmentConfig,
    ) -> AlignmentActionDecision:
        action_dim = int(config.action_dim)
        qpos = np.asarray(facts.qpos, dtype=np.float32).reshape(action_dim)
        qvel = np.asarray(facts.qvel, dtype=np.float32).reshape(action_dim)
        target_qpos = np.asarray(facts.target_qpos, dtype=np.float32).reshape(
            action_dim
        )
        error = (target_qpos - qpos).astype(np.float32)
        return AlignmentActionDecision(
            action=self.action_for_target(
                qpos=qpos,
                qvel=qvel,
                target_qpos=target_qpos,
                config=config,
            ),
            error=error,
            entry_error_m=float(facts.entry_error_m),
        )

    def action_decision_from_observation_view(
        self,
        *,
        view: PlannerObservationView,
        target_qpos: np.ndarray,
        entry_error_m: float,
        config: DigStartAlignmentConfig,
        qpos: np.ndarray | None = None,
        qvel: np.ndarray | None = None,
        cycle_index: int = 0,
        hold_count: int = 0,
    ) -> AlignmentActionDecision:
        return self.action_decision(
            build_dig_start_alignment_facts_from_observation_view(
                view=view,
                target_qpos=target_qpos,
                entry_error_m=entry_error_m,
                qpos=qpos,
                qvel=qvel,
                cycle_index=cycle_index,
                hold_count=hold_count,
            ),
            config,
        )


def pd_servo_action(
    *,
    qpos: np.ndarray,
    qvel: np.ndarray,
    target_qpos: np.ndarray,
    kp: float,
    kd: float,
    action_clip: float | np.ndarray | list[float] | tuple[float, ...],
    action_signs: np.ndarray | list[float] | tuple[float, ...] | None = None,
) -> np.ndarray:
    action = float(kp) * (target_qpos - qpos) - float(kd) * qvel
    if action_signs is not None:
        action = (
            np.asarray(action_signs, dtype=np.float32).reshape(action.shape) * action
        )
    action_clip_arr = np.asarray(action_clip, dtype=np.float32)
    if action_clip_arr.ndim == 0:
        action_clip_arr = np.full_like(action, float(action_clip_arr))
    return np.clip(action, -action_clip_arr, action_clip_arr).astype(np.float32)
