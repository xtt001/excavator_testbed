"""Pre-dig-align runtime service for primitive execution."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from testbed.data.operator_first_v2_2 import DIG_CUT_TOKEN_DIM


@dataclass(frozen=True)
class PrimitivePreDigAlignRuntimeConfig:
    """Read-only pre-dig-align runtime configuration snapshot."""

    action_dim: int
    enabled: bool
    first_dig_only: bool
    replan_after_failed_dig: bool
    kp: float
    kd: float
    action_clip: float | np.ndarray | list[float] | tuple[float, ...]
    action_signs: np.ndarray | list[float] | tuple[float, ...] | None
    controlled_dims: np.ndarray | list[bool] | tuple[bool, ...]
    entry_intent_controlled_dims: (
        np.ndarray | list[bool] | tuple[bool, ...] | None
    )
    bucket_target_qpos: float | None
    qpos_tolerance: np.ndarray | list[float] | tuple[float, ...]
    qvel_abs_max: float
    hold_steps: int
    max_steps: int
    max_entry_error_m: float | None
    timeout_accept_entry_error_m: float | None
    timeout_replan_entry_error_m: float | None
    start_envelope_enabled: bool
    first_dig_entry_close_handoff: bool
    first_dig_entry_close_handoff_qvel_abs_max: float | None
    start_envelope_max_entry_error_m: float
    entry_intent_handoff_enabled: bool
    surface_guard_enabled: bool
    surface_guard_max_penetration_m: float
    surface_guard_handoff_entry_error_m: float | None
    surface_guard_use_contact_fallback: bool
    start_qpos_min: np.ndarray | list[float] | tuple[float, ...]
    start_qpos_max: np.ndarray | list[float] | tuple[float, ...]
    start_pose_min: np.ndarray | list[float] | tuple[float, ...]
    start_pose_max: np.ndarray | list[float] | tuple[float, ...]
    qpos_min: np.ndarray | list[float] | tuple[float, ...]
    qpos_max: np.ndarray | list[float] | tuple[float, ...]
    qpos_from_token_coefficients: np.ndarray | list[list[float]]


@dataclass
class PrimitivePreDigAlignRuntimeState:
    """Mutable runtime state owned by the pre-dig-align execution service."""

    step_count: int = 0
    hold_count: int = 0
    timeout_count: int = 0
    completed_count: int = 0
    replan_count: int = 0
    target_qpos: np.ndarray = field(
        default_factory=lambda: np.zeros(4, dtype=np.float32)
    )
    error: np.ndarray = field(default_factory=lambda: np.zeros(4, dtype=np.float32))
    entry_error_m: float = float("nan")
    start_envelope_ready: bool = False
    entry_close_handoff_ready: bool = False
    entry_intent_handoff_ready: bool = False
    timeout_handoff_reason: str = ""
    surface_depth_m: float = float("nan")
    surface_guard_triggered: bool = False
    surface_guard_count: int = 0

    @classmethod
    def fresh(
        cls,
        *,
        action_dim: int,
    ) -> PrimitivePreDigAlignRuntimeState:
        return cls(
            target_qpos=np.zeros(int(action_dim), dtype=np.float32),
            error=np.zeros(int(action_dim), dtype=np.float32),
        )


@dataclass(frozen=True)
class PrimitivePreDigAlignPorts:
    """Explicit runtime ports required by pre-dig-align algorithms."""

    ensure_dig_cut_plan_for_cycle: Callable[[dict[str, Any]], None]
    dig_cut_tokens: Callable[[], Any]
    active_coverage_corridor: Callable[[], Any | None]
    bucket_tip_dig_area_pose: Callable[[dict[str, Any]], Any | None]
    bucket_dig_area_pose: Callable[[dict[str, Any]], Any | None]
    bucket_depth_below_local_surface: Callable[[dict[str, Any]], float]
    bucket_dig_area_contact_mask: Callable[[dict[str, Any]], bool]
    cycle_index: Callable[[], int]


@dataclass(frozen=True)
class PrimitivePreDigAlignRuntimeService:
    """Own pre-dig-align target, readiness, timeout, guard, and action logic."""

    config: PrimitivePreDigAlignRuntimeConfig
    state: PrimitivePreDigAlignRuntimeState
    ports: PrimitivePreDigAlignPorts

    @classmethod
    def from_ports(
        cls,
        *,
        config: PrimitivePreDigAlignRuntimeConfig,
        state: PrimitivePreDigAlignRuntimeState,
        ports: PrimitivePreDigAlignPorts,
    ) -> PrimitivePreDigAlignRuntimeService:
        return cls(config=config, state=state, ports=ports)

    def should_pre_dig_align_before_dig(self) -> bool:
        if not bool(self.config.enabled):
            return False
        if not bool(self.config.first_dig_only):
            return True
        return int(self.ports.cycle_index()) == 0

    def should_pre_dig_align_after_failed_dig(self) -> bool:
        return bool(
            self.config.enabled and self.config.replan_after_failed_dig
        )

    def target_from_token(
        self,
        *,
        token: np.ndarray,
        obs: dict[str, Any],
        update_state: bool,
    ) -> np.ndarray:
        token = np.asarray(token, dtype=np.float32).reshape(-1)
        if len(token) < 2:
            token = np.zeros(DIG_CUT_TOKEN_DIM, dtype=np.float32)
        features = np.asarray(
            [1.0, float(token[0]), float(token[1])],
            dtype=np.float32,
        )
        target = self._qpos_from_token_coefficients() @ features
        target = np.clip(target, self._qpos_min(), self._qpos_max())
        if self.config.bucket_target_qpos is not None and self.action_dim >= 4:
            target[3] = float(
                np.clip(
                    self.config.bucket_target_qpos,
                    self._qpos_min()[3],
                    self._qpos_max()[3],
                )
            )
        qpos = self._obs_vector(obs, "qpos")
        intent_dims = self._entry_intent_controlled_dims()
        if intent_dims is not None:
            controlled = self._controlled_dims()
            hold_dims = controlled & ~intent_dims
            target[hold_dims] = qpos[hold_dims]
        target[~self._controlled_dims()] = qpos[~self._controlled_dims()]
        target = target.astype(np.float32)
        if update_state:
            self.state.target_qpos = target.copy()
        return target.copy()

    def target(self, obs: dict[str, Any]) -> np.ndarray:
        self.ports.ensure_dig_cut_plan_for_cycle(obs)
        token = np.asarray(self.ports.dig_cut_tokens(), dtype=np.float32).reshape(-1)
        return self.target_from_token(token=token, obs=obs, update_state=True)

    def entry_error(self, obs: dict[str, Any]) -> float:
        pose = self.ports.bucket_tip_dig_area_pose(obs)
        corridor = self.ports.active_coverage_corridor()
        if pose is None or corridor is None:
            return float("nan")
        pose_arr = np.asarray(pose, dtype=np.float32).reshape(3)
        dx = float(pose_arr[0]) - float(corridor.entry_x_m)
        dz = float(pose_arr[2]) - float(corridor.entry_z_m)
        return float(np.hypot(dx, dz))

    def surface_guard_triggered_for_state(self, obs: dict[str, Any]) -> bool:
        self.state.surface_depth_m = float(
            self.ports.bucket_depth_below_local_surface(obs)
        )
        self.state.surface_guard_triggered = False
        if not (
            bool(self.config.enabled)
            and bool(self.config.surface_guard_enabled)
        ):
            return False
        depth = float(self.state.surface_depth_m)
        if (
            np.isfinite(depth)
            and depth > float(self.config.surface_guard_max_penetration_m)
        ):
            self.state.surface_guard_triggered = True
            return True
        if (
            not np.isfinite(depth)
            and bool(self.config.surface_guard_use_contact_fallback)
            and bool(self.ports.bucket_dig_area_contact_mask(obs))
        ):
            self.state.surface_guard_triggered = True
            return True
        return False

    def surface_guard_can_handoff(self, obs: dict[str, Any]) -> bool:
        self.ports.ensure_dig_cut_plan_for_cycle(obs)
        threshold = self.config.surface_guard_handoff_entry_error_m
        if threshold is None:
            threshold = self.config.max_entry_error_m
        if threshold is None:
            threshold = self.config.start_envelope_max_entry_error_m
        entry_error = self.entry_error(obs)
        self.state.entry_error_m = float(entry_error)
        return self._entry_close(entry_error, threshold=threshold)

    def ready(self, obs: dict[str, Any]) -> bool:
        if not bool(self.config.enabled):
            return True
        target_qpos = self.target(obs)
        qpos = self._obs_vector(obs, "qpos")
        qvel = self._obs_vector(obs, "qvel")
        self.state.error = (target_qpos - qpos).astype(np.float32)
        entry_error = self.entry_error(obs)
        self.state.entry_error_m = float(entry_error)
        controlled = self._controlled_dims()
        qpos_close = bool(
            np.all(
                np.abs(self.state.error[controlled])
                <= self._qpos_tolerance()[controlled]
            )
            if np.any(controlled)
            else True
        )
        qvel_small = bool(
            np.all(np.abs(qvel[controlled]) <= float(self.config.qvel_abs_max))
            if np.any(controlled)
            else True
        )
        entry_close = self._entry_close(
            entry_error,
            threshold=self.config.max_entry_error_m,
        )
        start_envelope_ready = self._start_envelope_ready_for_state(
            obs=obs,
            qpos=qpos,
            entry_error=entry_error,
        )
        self.state.start_envelope_ready = bool(start_envelope_ready)
        entry_close_handoff_ready = self._entry_close_handoff_ready_for_state(
            entry_error=entry_error,
            qvel=qvel,
            start_envelope_ready=start_envelope_ready,
        )
        self.state.entry_close_handoff_ready = bool(entry_close_handoff_ready)
        entry_intent_handoff_ready = (
            self._entry_intent_handoff_ready_for_state(
                qpos_close=qpos_close,
                qvel_small=qvel_small,
            )
        )
        self.state.entry_intent_handoff_ready = bool(entry_intent_handoff_ready)
        if entry_close_handoff_ready or entry_intent_handoff_ready or (
            qpos_close and qvel_small and (entry_close or start_envelope_ready)
        ):
            self.state.hold_count += 1
        else:
            self.state.hold_count = 0
        return bool(self.state.hold_count >= max(1, int(self.config.hold_steps)))

    def timeout_can_handoff(self, obs: dict[str, Any]) -> bool:
        self.state.timeout_handoff_reason = ""
        threshold = self.config.timeout_accept_entry_error_m
        if threshold is None:
            threshold = self.config.max_entry_error_m
        if threshold is None:
            self.state.timeout_handoff_reason = (
                "pre_dig_align_to_dig_timeout_no_entry_gate"
            )
            return True
        entry_error = self.entry_error(obs)
        self.state.entry_error_m = float(entry_error)
        qpos = self._obs_vector(obs, "qpos")
        start_envelope_ready = self._start_envelope_ready_for_state(
            obs=obs,
            qpos=qpos,
            entry_error=entry_error,
        )
        self.state.start_envelope_ready = bool(start_envelope_ready)
        if self._entry_intent_mode_enabled():
            self.state.entry_intent_handoff_ready = True
            self.state.timeout_handoff_reason = (
                "pre_dig_align_to_dig_timeout_intent_aligned"
            )
            return True
        if (
            self._entry_close(entry_error, threshold=threshold)
            or start_envelope_ready
        ):
            self.state.timeout_handoff_reason = (
                "pre_dig_align_to_dig_timeout_close_enough"
            )
        return bool(
            self._entry_close(entry_error, threshold=threshold)
            or start_envelope_ready
        )

    def mark_completed(self) -> None:
        self.state.completed_count += 1

    def mark_surface_guard(self) -> None:
        self.state.surface_guard_count += 1

    def timed_out(self) -> bool:
        return bool(
            int(self.config.max_steps) > 0
            and int(self.state.step_count) >= int(self.config.max_steps)
        )

    def mark_timeout(self) -> None:
        self.state.timeout_count += 1

    def reset_hold(self) -> None:
        self.state.hold_count = 0

    def action(self, obs: dict[str, Any]) -> np.ndarray:
        if not bool(self.config.enabled):
            raise RuntimeError("pre-dig align action requested while disabled.")
        self.state.step_count += 1
        if self.surface_guard_triggered_for_state(obs):
            return np.zeros(self.action_dim, dtype=np.float32)
        target_qpos = self.target(obs)
        qpos = self._obs_vector(obs, "qpos")
        qvel = self._obs_vector(obs, "qvel")
        self.state.error = (target_qpos - qpos).astype(np.float32)
        self.state.entry_error_m = float(self.entry_error(obs))
        return self.pd_servo_action(
            qpos=qpos,
            qvel=qvel,
            target_qpos=target_qpos,
        )

    def pd_servo_action(
        self,
        *,
        qpos: np.ndarray,
        qvel: np.ndarray,
        target_qpos: np.ndarray,
    ) -> np.ndarray:
        action = (
            float(self.config.kp) * (target_qpos - qpos)
            - float(self.config.kd) * qvel
        )
        if self.config.action_signs is not None:
            action = self._action_signs() * action
        action_clip = np.asarray(self.config.action_clip, dtype=np.float32)
        if action_clip.ndim == 0:
            action_clip = np.full_like(action, float(action_clip))
        else:
            action_clip = action_clip.reshape(action.shape)
        action = np.clip(action, -action_clip, action_clip).astype(np.float32)
        action[~self._controlled_dims()] = 0.0
        return action

    @property
    def action_dim(self) -> int:
        return int(self.config.action_dim)

    def _entry_close(
        self,
        entry_error: float,
        *,
        threshold: float | None,
    ) -> bool:
        if threshold is None:
            return True
        return bool(np.isfinite(entry_error) and float(entry_error) <= float(threshold))

    def _entry_close_handoff_ready_for_state(
        self,
        *,
        entry_error: float,
        qvel: np.ndarray,
        start_envelope_ready: bool,
    ) -> bool:
        if not bool(self.config.first_dig_entry_close_handoff):
            return False
        if int(self.ports.cycle_index()) != 0:
            return False
        if (
            bool(self.config.start_envelope_enabled)
            and not bool(start_envelope_ready)
        ):
            return False
        if not self._entry_close(
            entry_error,
            threshold=self.config.max_entry_error_m,
        ):
            return False
        qvel_abs_max = self.config.first_dig_entry_close_handoff_qvel_abs_max
        if qvel_abs_max is None:
            qvel_abs_max = self.config.qvel_abs_max
        controlled = self._controlled_dims()
        if not np.any(controlled):
            return True
        return bool(np.all(np.abs(qvel[controlled]) <= float(qvel_abs_max)))

    def _entry_intent_mode_enabled(self) -> bool:
        if not bool(self.config.entry_intent_handoff_enabled):
            return False
        intent_dims = self._entry_intent_controlled_dims()
        if intent_dims is None:
            return False
        controlled = self._controlled_dims()
        return bool(np.any(controlled & intent_dims) and np.any(controlled & ~intent_dims))

    def _entry_intent_handoff_ready_for_state(
        self,
        *,
        qpos_close: bool,
        qvel_small: bool,
    ) -> bool:
        return bool(
            self._entry_intent_mode_enabled()
            and qpos_close
            and qvel_small
        )

    def _start_envelope_ready_for_state(
        self,
        *,
        obs: dict[str, Any],
        qpos: np.ndarray,
        entry_error: float,
    ) -> bool:
        if not bool(self.config.start_envelope_enabled):
            return False
        if (
            not np.isfinite(entry_error)
            or float(entry_error)
            > float(self.config.start_envelope_max_entry_error_m)
        ):
            return False
        if not np.all(qpos >= self._start_qpos_min()):
            return False
        if not np.all(qpos <= self._start_qpos_max()):
            return False
        pose = self.ports.bucket_dig_area_pose(obs)
        if pose is None:
            return False
        pose_arr = np.asarray(pose, dtype=np.float32).reshape(3)
        return bool(
            np.all(pose_arr >= self._start_pose_min())
            and np.all(pose_arr <= self._start_pose_max())
        )

    def _obs_vector(self, obs: dict[str, Any], key: str) -> np.ndarray:
        return np.asarray(
            obs.get(key, np.zeros(self.action_dim, dtype=np.float32)),
            dtype=np.float32,
        ).reshape(self.action_dim)

    def _controlled_dims(self) -> np.ndarray:
        return np.asarray(self.config.controlled_dims, dtype=bool).reshape(
            self.action_dim
        )

    def _entry_intent_controlled_dims(self) -> np.ndarray | None:
        if self.config.entry_intent_controlled_dims is None:
            return None
        return np.asarray(
            self.config.entry_intent_controlled_dims,
            dtype=bool,
        ).reshape(self.action_dim)

    def _action_signs(self) -> np.ndarray:
        return np.asarray(self.config.action_signs, dtype=np.float32).reshape(
            self.action_dim
        )

    def _qpos_tolerance(self) -> np.ndarray:
        return np.asarray(self.config.qpos_tolerance, dtype=np.float32).reshape(
            self.action_dim
        )

    def _qpos_min(self) -> np.ndarray:
        return np.asarray(self.config.qpos_min, dtype=np.float32).reshape(
            self.action_dim
        )

    def _qpos_max(self) -> np.ndarray:
        return np.asarray(self.config.qpos_max, dtype=np.float32).reshape(
            self.action_dim
        )

    def _start_qpos_min(self) -> np.ndarray:
        return np.asarray(self.config.start_qpos_min, dtype=np.float32).reshape(
            self.action_dim
        )

    def _start_qpos_max(self) -> np.ndarray:
        return np.asarray(self.config.start_qpos_max, dtype=np.float32).reshape(
            self.action_dim
        )

    def _start_pose_min(self) -> np.ndarray:
        return np.asarray(self.config.start_pose_min, dtype=np.float32).reshape(3)

    def _start_pose_max(self) -> np.ndarray:
        return np.asarray(self.config.start_pose_max, dtype=np.float32).reshape(3)

    def _qpos_from_token_coefficients(self) -> np.ndarray:
        return np.asarray(
            self.config.qpos_from_token_coefficients,
            dtype=np.float32,
        ).reshape(self.action_dim, 3)


__all__ = [
    "PrimitivePreDigAlignPorts",
    "PrimitivePreDigAlignRuntimeConfig",
    "PrimitivePreDigAlignRuntimeService",
    "PrimitivePreDigAlignRuntimeState",
]
