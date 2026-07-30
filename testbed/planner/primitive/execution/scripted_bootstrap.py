"""Scripted bootstrap runtime state and action service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class PrimitiveScriptedBootstrapReportStatus:
    """Projected scripted-bootstrap runtime counters for reports."""

    step_count: int
    hold_count: int
    timeout_count: int

    def debug_fields(self) -> dict[str, int]:
        """Return the public scripted-bootstrap debug field projection."""

        return {
            "scripted_bootstrap_step_count": int(self.step_count),
            "scripted_bootstrap_hold_count": int(self.hold_count),
            "scripted_bootstrap_timeout_count": int(self.timeout_count),
        }


@dataclass
class PrimitiveScriptedBootstrapRuntimeState:
    """Mutable counters owned by the scripted bootstrap runtime path."""

    step_count: int = 0
    hold_count: int = 0
    timeout_count: int = 0

    @classmethod
    def fresh(cls) -> PrimitiveScriptedBootstrapRuntimeState:
        return cls()

    def to_report_status(self) -> PrimitiveScriptedBootstrapReportStatus:
        """Project live scripted-bootstrap counters for reporting."""

        return PrimitiveScriptedBootstrapReportStatus(
            step_count=int(self.step_count),
            hold_count=int(self.hold_count),
            timeout_count=int(self.timeout_count),
        )


@dataclass(frozen=True)
class PrimitiveScriptedBootstrapRuntimeConfig:
    """Read-only scripted bootstrap configuration snapshot."""

    action_dim: int
    bootstrap_end_mode: str
    target_qpos: np.ndarray | None
    kp: float
    kd: float
    action_clip: float | np.ndarray | list[float] | tuple[float, ...]
    action_signs: np.ndarray | list[float] | tuple[float, ...] | None
    qpos_tolerance: float
    qvel_abs_max: float
    hold_steps: int
    max_steps: int


@dataclass(frozen=True)
class PrimitiveScriptedBootstrapRuntimeService:
    """Own scripted bootstrap readiness and PD action generation."""

    config: PrimitiveScriptedBootstrapRuntimeConfig
    state: PrimitiveScriptedBootstrapRuntimeState

    def enabled(self) -> bool:
        return bool(
            self.config.bootstrap_end_mode == "scripted_qpos"
            and self.config.target_qpos is not None
        )

    def target_reached(self, obs: dict[str, Any]) -> bool:
        target_qpos = self.config.target_qpos
        if target_qpos is None:
            return False
        qpos = self._obs_vector(obs, "qpos")
        qvel = self._obs_vector(obs, "qvel")
        target = np.asarray(target_qpos, dtype=np.float32).reshape(
            int(self.config.action_dim)
        )
        qpos_close = bool(
            np.all(np.abs(qpos - target) <= float(self.config.qpos_tolerance))
        )
        qvel_small = bool(np.all(np.abs(qvel) <= float(self.config.qvel_abs_max)))
        if qpos_close and qvel_small:
            self.state.hold_count += 1
        else:
            self.state.hold_count = 0
        return bool(self.state.hold_count >= int(self.config.hold_steps))

    def should_end_bootstrap(self, obs: dict[str, Any]) -> bool:
        if not self.enabled():
            return False
        if self.target_reached(obs):
            return True
        if int(self.state.step_count) >= int(self.config.max_steps):
            self.state.timeout_count += 1
            return True
        return False

    def action(self, obs: dict[str, Any]) -> np.ndarray:
        target_qpos = self.config.target_qpos
        if target_qpos is None:
            raise RuntimeError("scripted bootstrap is active without target qpos.")
        self.state.step_count += 1
        qpos = self._obs_vector(obs, "qpos")
        qvel = self._obs_vector(obs, "qvel")
        target = np.asarray(target_qpos, dtype=np.float32).reshape(qpos.shape)
        action = float(self.config.kp) * (target - qpos) - float(self.config.kd) * qvel
        if self.config.action_signs is not None:
            action = (
                np.asarray(self.config.action_signs, dtype=np.float32).reshape(
                    action.shape
                )
                * action
            )
        action_clip = np.asarray(self.config.action_clip, dtype=np.float32)
        if action_clip.ndim == 0:
            action_clip = np.full_like(action, float(action_clip))
        return np.clip(action, -action_clip, action_clip).astype(np.float32)

    def _obs_vector(self, obs: dict[str, Any], key: str) -> np.ndarray:
        action_dim = int(self.config.action_dim)
        return np.asarray(
            obs.get(key, np.zeros(action_dim, dtype=np.float32)),
            dtype=np.float32,
        ).reshape(action_dim)


__all__ = [
    "PrimitiveScriptedBootstrapReportStatus",
    "PrimitiveScriptedBootstrapRuntimeConfig",
    "PrimitiveScriptedBootstrapRuntimeService",
    "PrimitiveScriptedBootstrapRuntimeState",
]
