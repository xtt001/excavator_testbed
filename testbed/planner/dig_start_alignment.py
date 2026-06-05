"""Dig-start alignment target and action helpers."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from testbed.contracts.primitive_tokens import (
    CUT_ENTRY_X_IDX,
    CUT_ENTRY_Z_IDX,
    DIG_CUT_TOKEN_DIM,
)


@dataclass(frozen=True)
class DigStartAlignmentConfig:
    action_dim: int
    qpos_min: np.ndarray
    qpos_max: np.ndarray
    qpos_from_token_coefficients: np.ndarray
    controlled_dims: np.ndarray
    entry_intent_controlled_dims: np.ndarray | None
    bucket_target_qpos: float | None
    kp: float
    kd: float
    action_clip: float | np.ndarray | list[float] | tuple[float, ...]
    action_signs: np.ndarray | list[float] | tuple[float, ...] | None = None
    enabled: bool = False
    qpos_tolerance: np.ndarray | None = None
    qvel_abs_max: float = 0.12
    hold_steps: int = 1
    max_entry_error_m: float | None = None
    timeout_accept_entry_error_m: float | None = None
    start_envelope_enabled: bool = False
    start_envelope_max_entry_error_m: float = 0.65
    first_dig_entry_close_handoff: bool = False
    first_dig_entry_close_handoff_qvel_abs_max: float | None = None
    entry_intent_handoff_enabled: bool = False
    surface_guard_enabled: bool = False
    surface_guard_max_penetration_m: float = 0.005
    surface_guard_handoff_entry_error_m: float | None = None
    surface_guard_use_contact_fallback: bool = True
    start_qpos_min: np.ndarray | None = None
    start_qpos_max: np.ndarray | None = None
    start_pose_min: np.ndarray | None = None
    start_pose_max: np.ndarray | None = None


@dataclass(frozen=True)
class DigStartAlignmentFacts:
    qpos: np.ndarray
    qvel: np.ndarray
    target_qpos: np.ndarray | None = None
    entry_error_m: float = float("nan")
    bucket_pose: tuple[float, float, float] | None = None
    surface_depth_m: float = float("nan")
    contact_mask: bool = False
    cycle_index: int = 0
    hold_count: int = 0


@dataclass(frozen=True)
class SurfaceGuardDecision:
    triggered: bool
    surface_depth_m: float


@dataclass(frozen=True)
class AlignmentReadyDecision:
    ready: bool
    hold_count: int
    error: np.ndarray
    qpos_close: bool
    qvel_small: bool
    entry_close: bool
    start_envelope_ready: bool
    entry_close_handoff_ready: bool
    entry_intent_handoff_ready: bool


@dataclass(frozen=True)
class TimeoutHandoffDecision:
    ready: bool
    reason: str
    start_envelope_ready: bool
    entry_intent_handoff_ready: bool


class DigStartAlignmentService:
    """Computes pre-dig alignment targets and actions without scheduler state."""

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

    def surface_guard_triggered(
        self,
        facts: DigStartAlignmentFacts,
        config: DigStartAlignmentConfig,
    ) -> SurfaceGuardDecision:
        surface_depth = float(facts.surface_depth_m)
        if not (bool(config.enabled) and bool(config.surface_guard_enabled)):
            return SurfaceGuardDecision(False, surface_depth)
        if (
            np.isfinite(surface_depth)
            and surface_depth > float(config.surface_guard_max_penetration_m)
        ):
            return SurfaceGuardDecision(True, surface_depth)
        if (
            not np.isfinite(surface_depth)
            and bool(config.surface_guard_use_contact_fallback)
            and bool(facts.contact_mask)
        ):
            return SurfaceGuardDecision(True, surface_depth)
        return SurfaceGuardDecision(False, surface_depth)

    def surface_guard_can_handoff(
        self,
        facts: DigStartAlignmentFacts,
        config: DigStartAlignmentConfig,
    ) -> bool:
        threshold = config.surface_guard_handoff_entry_error_m
        if threshold is None:
            threshold = config.max_entry_error_m
        if threshold is None:
            threshold = config.start_envelope_max_entry_error_m
        return self.entry_close(facts.entry_error_m, threshold=threshold)

    def ready(
        self,
        facts: DigStartAlignmentFacts,
        config: DigStartAlignmentConfig,
    ) -> AlignmentReadyDecision:
        if not bool(config.enabled):
            return AlignmentReadyDecision(
                ready=True,
                hold_count=int(facts.hold_count),
                error=np.zeros(int(config.action_dim), dtype=np.float32),
                qpos_close=True,
                qvel_small=True,
                entry_close=True,
                start_envelope_ready=False,
                entry_close_handoff_ready=False,
                entry_intent_handoff_ready=False,
            )
        qpos = np.asarray(facts.qpos, dtype=np.float32).reshape(int(config.action_dim))
        qvel = np.asarray(facts.qvel, dtype=np.float32).reshape(int(config.action_dim))
        target_qpos = np.asarray(
            facts.target_qpos,
            dtype=np.float32,
        ).reshape(int(config.action_dim))
        error = (target_qpos - qpos).astype(np.float32)
        controlled = np.asarray(config.controlled_dims, dtype=bool).reshape(
            int(config.action_dim)
        )
        qpos_tolerance = self._qpos_tolerance(config)
        qpos_close = bool(
            np.all(np.abs(error[controlled]) <= qpos_tolerance[controlled])
            if np.any(controlled)
            else True
        )
        qvel_small = bool(
            np.all(np.abs(qvel[controlled]) <= float(config.qvel_abs_max))
            if np.any(controlled)
            else True
        )
        entry_close = self.entry_close(
            facts.entry_error_m,
            threshold=config.max_entry_error_m,
        )
        start_ready = self.start_envelope_ready(facts, config)
        entry_close_ready = self.entry_close_handoff_ready(
            facts=facts,
            config=config,
            start_envelope_ready=start_ready,
        )
        intent_ready = self.entry_intent_handoff_ready(
            qpos_close=qpos_close,
            qvel_small=qvel_small,
            config=config,
        )
        should_hold = bool(
            entry_close_ready
            or intent_ready
            or (qpos_close and qvel_small and (entry_close or start_ready))
        )
        hold_count = int(facts.hold_count) + 1 if should_hold else 0
        return AlignmentReadyDecision(
            ready=bool(hold_count >= int(config.hold_steps)),
            hold_count=hold_count,
            error=error,
            qpos_close=qpos_close,
            qvel_small=qvel_small,
            entry_close=entry_close,
            start_envelope_ready=start_ready,
            entry_close_handoff_ready=entry_close_ready,
            entry_intent_handoff_ready=intent_ready,
        )

    @staticmethod
    def entry_close(entry_error: float, *, threshold: float | None) -> bool:
        if threshold is None:
            return True
        return bool(np.isfinite(entry_error) and float(entry_error) <= float(threshold))

    def entry_close_handoff_ready(
        self,
        *,
        facts: DigStartAlignmentFacts,
        config: DigStartAlignmentConfig,
        start_envelope_ready: bool,
    ) -> bool:
        if not bool(config.first_dig_entry_close_handoff):
            return False
        if int(facts.cycle_index) != 0:
            return False
        if bool(config.start_envelope_enabled) and not bool(start_envelope_ready):
            return False
        if not self.entry_close(
            facts.entry_error_m,
            threshold=config.max_entry_error_m,
        ):
            return False
        qvel_abs_max = config.first_dig_entry_close_handoff_qvel_abs_max
        if qvel_abs_max is None:
            qvel_abs_max = config.qvel_abs_max
        controlled = np.asarray(config.controlled_dims, dtype=bool).reshape(
            int(config.action_dim)
        )
        if not np.any(controlled):
            return True
        qvel = np.asarray(facts.qvel, dtype=np.float32).reshape(int(config.action_dim))
        return bool(np.all(np.abs(qvel[controlled]) <= float(qvel_abs_max)))

    def entry_intent_mode_enabled(self, config: DigStartAlignmentConfig) -> bool:
        if not bool(config.entry_intent_handoff_enabled):
            return False
        intent_dims = config.entry_intent_controlled_dims
        if intent_dims is None:
            return False
        controlled = np.asarray(config.controlled_dims, dtype=bool).reshape(
            int(config.action_dim)
        )
        intent = np.asarray(intent_dims, dtype=bool).reshape(int(config.action_dim))
        return bool(np.any(controlled & intent) and np.any(controlled & ~intent))

    def entry_intent_handoff_ready(
        self,
        *,
        qpos_close: bool,
        qvel_small: bool,
        config: DigStartAlignmentConfig,
    ) -> bool:
        return bool(
            self.entry_intent_mode_enabled(config)
            and bool(qpos_close)
            and bool(qvel_small)
        )

    def timeout_can_handoff(
        self,
        facts: DigStartAlignmentFacts,
        config: DigStartAlignmentConfig,
    ) -> TimeoutHandoffDecision:
        threshold = config.timeout_accept_entry_error_m
        if threshold is None:
            threshold = config.max_entry_error_m
        if threshold is None:
            return TimeoutHandoffDecision(
                ready=True,
                reason="pre_dig_align_to_dig_timeout_no_entry_gate",
                start_envelope_ready=False,
                entry_intent_handoff_ready=False,
            )
        start_ready = self.start_envelope_ready(facts, config)
        if self.entry_intent_mode_enabled(config):
            return TimeoutHandoffDecision(
                ready=True,
                reason="pre_dig_align_to_dig_timeout_intent_aligned",
                start_envelope_ready=start_ready,
                entry_intent_handoff_ready=True,
            )
        ready = bool(
            self.entry_close(facts.entry_error_m, threshold=threshold) or start_ready
        )
        return TimeoutHandoffDecision(
            ready=ready,
            reason="pre_dig_align_to_dig_timeout_close_enough" if ready else "",
            start_envelope_ready=start_ready,
            entry_intent_handoff_ready=False,
        )

    def start_envelope_ready(
        self,
        facts: DigStartAlignmentFacts,
        config: DigStartAlignmentConfig,
    ) -> bool:
        if not bool(config.start_envelope_enabled):
            return False
        if (
            not np.isfinite(facts.entry_error_m)
            or float(facts.entry_error_m)
            > float(config.start_envelope_max_entry_error_m)
        ):
            return False
        qpos = np.asarray(facts.qpos, dtype=np.float32).reshape(int(config.action_dim))
        start_qpos_min = self._start_qpos_min(config)
        start_qpos_max = self._start_qpos_max(config)
        if not np.all(qpos >= start_qpos_min):
            return False
        if not np.all(qpos <= start_qpos_max):
            return False
        if facts.bucket_pose is None:
            return False
        pose_arr = np.asarray(facts.bucket_pose, dtype=np.float32).reshape(3)
        start_pose_min = self._start_pose_min(config)
        start_pose_max = self._start_pose_max(config)
        return bool(
            np.all(pose_arr >= start_pose_min)
            and np.all(pose_arr <= start_pose_max)
        )

    def _qpos_tolerance(self, config: DigStartAlignmentConfig) -> np.ndarray:
        if config.qpos_tolerance is None:
            return np.zeros(int(config.action_dim), dtype=np.float32)
        return np.asarray(config.qpos_tolerance, dtype=np.float32).reshape(
            int(config.action_dim)
        )

    def _start_qpos_min(self, config: DigStartAlignmentConfig) -> np.ndarray:
        if config.start_qpos_min is None:
            return np.full(int(config.action_dim), -np.inf, dtype=np.float32)
        return np.asarray(config.start_qpos_min, dtype=np.float32).reshape(
            int(config.action_dim)
        )

    def _start_qpos_max(self, config: DigStartAlignmentConfig) -> np.ndarray:
        if config.start_qpos_max is None:
            return np.full(int(config.action_dim), np.inf, dtype=np.float32)
        return np.asarray(config.start_qpos_max, dtype=np.float32).reshape(
            int(config.action_dim)
        )

    @staticmethod
    def _start_pose_min(config: DigStartAlignmentConfig) -> np.ndarray:
        if config.start_pose_min is None:
            return np.full(3, -np.inf, dtype=np.float32)
        return np.asarray(config.start_pose_min, dtype=np.float32).reshape(3)

    @staticmethod
    def _start_pose_max(config: DigStartAlignmentConfig) -> np.ndarray:
        if config.start_pose_max is None:
            return np.full(3, np.inf, dtype=np.float32)
        return np.asarray(config.start_pose_max, dtype=np.float32).reshape(3)


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
