"""Focused action shaping for a bounded return-approach axis.

The service is deliberately opt-in and diagnostic-only.  It never changes a
return handoff envelope.  Instead, it reads the already locked qpos bound and
can replace one ACT action component with a bounded PD action before the
existing safety interlock runs.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np

RETURN_APPROACH_AXIS_LIMIT_LINEAGE_INVALID_REASON = (
    "diagnostic_return_approach_axis_limit_lineage_invalid"
)
RETURN_APPROACH_AXIS_LIMIT_LINEAGE_DRIFT_REASON = (
    "diagnostic_return_approach_axis_limit_lineage_drift"
)
RETURN_APPROACH_AXIS_LIMIT_OBSERVATION_INVALID_REASON = (
    "diagnostic_return_approach_axis_limit_observation_invalid"
)
_CONFIG_KEY = "return_approach_axis_limit"
_LINEAGE_TOLERANCE = 1.0e-6


@dataclass(frozen=True)
class ReturnApproachAxisLimitConfig:
    """Immutable opt-in contract for one diagnostic return-axis limiter."""

    enabled: bool = False
    diagnostic_only: bool = False
    action_dim: int = 4
    axis_index: int = 1
    min_completed_dump_count: int = 7
    required_cell_id: int | None = None
    lineage_warmup_ticks: int = 1
    activation_margin: float = 0.020
    target_margin: float = 0.016
    activation_velocity_min: float = 0.0
    kp: float = 4.0
    kd: float = 2.0
    action_sign: float = -1.0
    action_clip: float = 0.35

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ValueError("return_approach_axis_limit.enabled must be boolean")
        if not isinstance(self.diagnostic_only, bool):
            raise ValueError(
                "return_approach_axis_limit.diagnostic_only must be boolean"
            )
        if self.enabled and not self.diagnostic_only:
            raise ValueError(
                "enabled return_approach_axis_limit requires "
                "diagnostic_only=true"
            )
        if int(self.action_dim) <= 0:
            raise ValueError(
                "return_approach_axis_limit.action_dim must be positive"
            )
        if not 0 <= int(self.axis_index) < int(self.action_dim):
            raise ValueError(
                "return_approach_axis_limit.axis_index is outside action_dim"
            )
        if int(self.min_completed_dump_count) < 0:
            raise ValueError(
                "return_approach_axis_limit.min_completed_dump_count "
                "must be nonnegative"
            )
        if self.required_cell_id is not None and int(self.required_cell_id) < 0:
            raise ValueError(
                "return_approach_axis_limit.required_cell_id "
                "must be nonnegative or null"
            )
        if int(self.lineage_warmup_ticks) < 0:
            raise ValueError(
                "return_approach_axis_limit.lineage_warmup_ticks "
                "must be nonnegative"
            )
        activation_margin = _finite_positive(
            self.activation_margin,
            "activation_margin",
        )
        target_margin = _finite_positive(
            self.target_margin,
            "target_margin",
        )
        if target_margin >= activation_margin:
            raise ValueError(
                "return_approach_axis_limit.target_margin must be smaller "
                "than activation_margin"
            )
        if (
            not np.isfinite(float(self.activation_velocity_min))
            or float(self.activation_velocity_min) < 0.0
        ):
            raise ValueError(
                "return_approach_axis_limit.activation_velocity_min "
                "must be finite and nonnegative"
            )
        _finite_positive(self.kp, "kp")
        if not np.isfinite(float(self.kd)) or float(self.kd) < 0.0:
            raise ValueError(
                "return_approach_axis_limit.kd must be finite and nonnegative"
            )
        if float(self.action_sign) not in {-1.0, 1.0}:
            raise ValueError(
                "return_approach_axis_limit.action_sign must be -1 or 1"
            )
        _finite_positive(self.action_clip, "action_clip")

    @classmethod
    def from_box_emptying_mapping(
        cls,
        box_emptying: Mapping[str, Any] | None,
        *,
        action_dim: int = 4,
    ) -> ReturnApproachAxisLimitConfig:
        """Parse the focused config without duplicating its semantics."""

        parent = dict(box_emptying or {})
        raw = parent.get(_CONFIG_KEY, {})
        if raw is None:
            raw = {}
        if not isinstance(raw, Mapping):
            raise ValueError(f"box_emptying.{_CONFIG_KEY} must be a mapping")
        values = dict(raw)
        values.pop("action_dim", None)
        known = {
            "enabled",
            "diagnostic_only",
            "axis_index",
            "min_completed_dump_count",
            "required_cell_id",
            "lineage_warmup_ticks",
            "activation_margin",
            "target_margin",
            "activation_velocity_min",
            "kp",
            "kd",
            "action_sign",
            "action_clip",
        }
        unknown = sorted(set(values) - known)
        if unknown:
            raise ValueError(
                f"box_emptying.{_CONFIG_KEY} has unknown fields: {unknown}"
            )
        return cls(action_dim=int(action_dim), **values)


@dataclass
class ReturnApproachAxisLimitState:
    """Mutable per-rollout state for lineage lock and diagnostics."""

    latched: bool = False
    locked_cell_id: int = -1
    locked_axis_upper_bound: float = float("nan")
    target_qpos: float = float("nan")
    return_context_tick_count: int = 0
    eligible_tick_count: int = 0
    intervention_count: int = 0
    terminal_count: int = 0
    first_intervention_step_id: int = -1
    last_intervention_step_id: int = -1
    last_qpos: float = float("nan")
    last_qvel: float = float("nan")
    last_proposed_axis_action: float = float("nan")
    last_shaped_axis_action: float = float("nan")
    last_terminal_reason: str = ""

    def reset(self) -> None:
        fresh = type(self)()
        self.__dict__.update(fresh.__dict__)

    def clear_return_context(self) -> None:
        self.latched = False
        self.locked_cell_id = -1
        self.locked_axis_upper_bound = float("nan")
        self.target_qpos = float("nan")
        self.return_context_tick_count = 0


@dataclass(frozen=True)
class ReturnApproachAxisLimitDecision:
    """One action-shaping result consumed by the safety wiring."""

    action: np.ndarray
    active: bool
    terminal_reason: str = ""
    axis_upper_bound: float = float("nan")
    target_qpos: float = float("nan")


@dataclass
class ReturnApproachAxisLimitService:
    """Keep one return axis inside its existing envelope without widening it."""

    config: ReturnApproachAxisLimitConfig
    state: ReturnApproachAxisLimitState = field(
        default_factory=ReturnApproachAxisLimitState
    )

    def reset(self) -> None:
        self.state.reset()

    def shape_action(
        self,
        obs: Mapping[str, Any],
        proposed_action: Any,
        *,
        skill_name: str,
        completed_dump_count: int,
        goal_cell_id: int,
        envelope_checks: Mapping[str, Any] | None,
    ) -> ReturnApproachAxisLimitDecision:
        action = np.asarray(proposed_action, dtype=np.float32).reshape(
            int(self.config.action_dim)
        )
        action = action.copy()
        if not self.config.enabled:
            return ReturnApproachAxisLimitDecision(action=action, active=False)
        if str(skill_name) != "return":
            self.state.clear_return_context()
            return ReturnApproachAxisLimitDecision(action=action, active=False)
        if int(completed_dump_count) < int(
            self.config.min_completed_dump_count
        ):
            return ReturnApproachAxisLimitDecision(action=action, active=False)

        cell_id = int(goal_cell_id)
        required_cell_id = self.config.required_cell_id
        if cell_id < 0:
            return self._terminal(
                RETURN_APPROACH_AXIS_LIMIT_LINEAGE_INVALID_REASON
            )
        if required_cell_id is not None and cell_id != int(required_cell_id):
            if self.state.latched:
                return self._terminal(
                    RETURN_APPROACH_AXIS_LIMIT_LINEAGE_DRIFT_REASON
                )
            return ReturnApproachAxisLimitDecision(action=action, active=False)
        self.state.return_context_tick_count += 1
        if self.state.return_context_tick_count <= int(
            self.config.lineage_warmup_ticks
        ):
            return ReturnApproachAxisLimitDecision(action=action, active=False)

        vectors = self._observation_vectors(obs)
        if vectors is None:
            return self._terminal(
                RETURN_APPROACH_AXIS_LIMIT_OBSERVATION_INVALID_REASON
            )
        qpos, qvel = vectors
        lineage = self._axis_lineage(envelope_checks)
        if lineage is None:
            return self._terminal(
                RETURN_APPROACH_AXIS_LIMIT_LINEAGE_INVALID_REASON
            )
        lower_bound, upper_bound = lineage
        if self._lineage_drifted(
            cell_id=cell_id,
            upper_bound=upper_bound,
        ):
            return self._terminal(
                RETURN_APPROACH_AXIS_LIMIT_LINEAGE_DRIFT_REASON
            )
        if not np.isfinite(self.state.locked_axis_upper_bound):
            self.state.locked_cell_id = cell_id
            self.state.locked_axis_upper_bound = upper_bound
            self.state.target_qpos = (
                upper_bound - float(self.config.target_margin)
            )

        axis = int(self.config.axis_index)
        axis_qpos = float(qpos[axis])
        axis_qvel = float(qvel[axis])
        self.state.eligible_tick_count += 1
        self.state.last_qpos = axis_qpos
        self.state.last_qvel = axis_qvel
        self.state.last_proposed_axis_action = float(action[axis])
        activation_threshold = (
            upper_bound - float(self.config.activation_margin)
        )
        should_latch = bool(
            axis_qpos >= activation_threshold
            and (
                axis_qvel >= float(self.config.activation_velocity_min)
                or axis_qpos >= upper_bound
            )
        )
        if not self.state.latched and not should_latch:
            return ReturnApproachAxisLimitDecision(
                action=action,
                active=False,
                axis_upper_bound=upper_bound,
                target_qpos=float(self.state.target_qpos),
            )
        self.state.latched = True
        target = float(self.state.target_qpos)
        if not lower_bound < target < upper_bound:
            return self._terminal(
                RETURN_APPROACH_AXIS_LIMIT_LINEAGE_INVALID_REASON
            )
        raw_axis_action = float(self.config.action_sign) * (
            float(self.config.kp) * (target - axis_qpos)
            - float(self.config.kd) * axis_qvel
        )
        if not np.isfinite(raw_axis_action):
            return self._terminal(
                RETURN_APPROACH_AXIS_LIMIT_OBSERVATION_INVALID_REASON
            )
        shaped_axis_action = float(
            np.clip(
                raw_axis_action,
                -float(self.config.action_clip),
                float(self.config.action_clip),
            )
        )
        action[axis] = shaped_axis_action
        step_id = _safe_step_id(obs.get("step_id", -1))
        self.state.intervention_count += 1
        if self.state.first_intervention_step_id < 0:
            self.state.first_intervention_step_id = step_id
        self.state.last_intervention_step_id = step_id
        self.state.last_shaped_axis_action = shaped_axis_action
        self.state.last_terminal_reason = ""
        return ReturnApproachAxisLimitDecision(
            action=action,
            active=True,
            axis_upper_bound=upper_bound,
            target_qpos=target,
        )

    def debug_fields(self) -> dict[str, Any]:
        """Return stable recorder fields without changing report ownership."""

        return {
            "return_approach_axis_limit_enabled": bool(self.config.enabled),
            "return_approach_axis_limit_diagnostic_only": bool(
                self.config.diagnostic_only
            ),
            "return_approach_axis_limit_axis_index": int(
                self.config.axis_index
            ),
            "return_approach_axis_limit_min_completed_dump_count": int(
                self.config.min_completed_dump_count
            ),
            "return_approach_axis_limit_required_cell_id": (
                -1
                if self.config.required_cell_id is None
                else int(self.config.required_cell_id)
            ),
            "return_approach_axis_limit_lineage_warmup_ticks": int(
                self.config.lineage_warmup_ticks
            ),
            "return_approach_axis_limit_return_context_tick_count": int(
                self.state.return_context_tick_count
            ),
            "return_approach_axis_limit_latched": bool(self.state.latched),
            "return_approach_axis_limit_locked_cell_id": int(
                self.state.locked_cell_id
            ),
            "return_approach_axis_limit_axis_upper_bound": float(
                self.state.locked_axis_upper_bound
            ),
            "return_approach_axis_limit_target_qpos": float(
                self.state.target_qpos
            ),
            "return_approach_axis_limit_eligible_tick_count": int(
                self.state.eligible_tick_count
            ),
            "return_approach_axis_limit_intervention_count": int(
                self.state.intervention_count
            ),
            "return_approach_axis_limit_terminal_count": int(
                self.state.terminal_count
            ),
            "return_approach_axis_limit_first_intervention_step_id": int(
                self.state.first_intervention_step_id
            ),
            "return_approach_axis_limit_last_intervention_step_id": int(
                self.state.last_intervention_step_id
            ),
            "return_approach_axis_limit_qpos": float(self.state.last_qpos),
            "return_approach_axis_limit_qvel": float(self.state.last_qvel),
            "return_approach_axis_limit_proposed_axis_action": float(
                self.state.last_proposed_axis_action
            ),
            "return_approach_axis_limit_shaped_axis_action": float(
                self.state.last_shaped_axis_action
            ),
            "return_approach_axis_limit_terminal_reason": str(
                self.state.last_terminal_reason
            ),
        }

    def _observation_vectors(
        self,
        obs: Mapping[str, Any],
    ) -> tuple[np.ndarray, np.ndarray] | None:
        try:
            qpos = np.asarray(obs.get("qpos"), dtype=np.float64).reshape(-1)
            qvel = np.asarray(obs.get("qvel"), dtype=np.float64).reshape(-1)
        except (TypeError, ValueError):
            return None
        action_dim = int(self.config.action_dim)
        if qpos.size < action_dim or qvel.size < action_dim:
            return None
        qpos = qpos[:action_dim]
        qvel = qvel[:action_dim]
        if not np.all(np.isfinite(qpos)) or not np.all(np.isfinite(qvel)):
            return None
        return qpos, qvel

    def _axis_lineage(
        self,
        envelope_checks: Mapping[str, Any] | None,
    ) -> tuple[float, float] | None:
        if not isinstance(envelope_checks, Mapping):
            return None
        raw = envelope_checks.get(f"qpos_{int(self.config.axis_index)}")
        if not isinstance(raw, Mapping):
            return None
        try:
            lower = float(raw["min"])
            upper = float(raw["max"])
        except (KeyError, TypeError, ValueError):
            return None
        if not np.isfinite(lower) or not np.isfinite(upper) or lower >= upper:
            return None
        return lower, upper

    def _lineage_drifted(
        self,
        *,
        cell_id: int,
        upper_bound: float,
    ) -> bool:
        if not np.isfinite(self.state.locked_axis_upper_bound):
            return False
        return bool(
            int(self.state.locked_cell_id) != int(cell_id)
            or abs(
                float(self.state.locked_axis_upper_bound)
                - float(upper_bound)
            )
            > _LINEAGE_TOLERANCE
        )

    def _terminal(self, reason: str) -> ReturnApproachAxisLimitDecision:
        self.state.latched = False
        self.state.terminal_count += 1
        self.state.last_terminal_reason = str(reason)
        return ReturnApproachAxisLimitDecision(
            action=np.zeros(int(self.config.action_dim), dtype=np.float32),
            active=False,
            terminal_reason=str(reason),
            axis_upper_bound=float(self.state.locked_axis_upper_bound),
            target_qpos=float(self.state.target_qpos),
        )


def build_return_approach_axis_limit_log_fields(
    policy_debug: Mapping[str, Any],
) -> dict[str, Any]:
    """Project controller debug state into the stable rollout sidecar."""

    bool_fields = (
        "enabled",
        "diagnostic_only",
        "latched",
    )
    int_fields = (
        "axis_index",
        "min_completed_dump_count",
        "required_cell_id",
        "lineage_warmup_ticks",
        "return_context_tick_count",
        "locked_cell_id",
        "eligible_tick_count",
        "intervention_count",
        "terminal_count",
        "first_intervention_step_id",
        "last_intervention_step_id",
    )
    float_fields = (
        "axis_upper_bound",
        "target_qpos",
        "qpos",
        "qvel",
        "proposed_axis_action",
        "shaped_axis_action",
    )
    prefix = "return_approach_axis_limit_"
    result = {
        f"{prefix}{name}": bool(
            policy_debug.get(f"{prefix}{name}", False)
        )
        for name in bool_fields
    }
    result.update(
        {
            f"{prefix}{name}": _safe_int(
                policy_debug.get(f"{prefix}{name}", -1)
            )
            for name in int_fields
        }
    )
    result.update(
        {
            f"{prefix}{name}": _safe_float(
                policy_debug.get(f"{prefix}{name}", float("nan"))
            )
            for name in float_fields
        }
    )
    result[f"{prefix}terminal_reason"] = str(
        policy_debug.get(f"{prefix}terminal_reason", "")
    )
    return result


def _finite_positive(value: Any, name: str) -> float:
    parsed = float(value)
    if not np.isfinite(parsed) or parsed <= 0.0:
        raise ValueError(
            f"return_approach_axis_limit.{name} must be finite and positive"
        )
    return parsed


def _safe_step_id(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


__all__ = [
    "RETURN_APPROACH_AXIS_LIMIT_LINEAGE_DRIFT_REASON",
    "RETURN_APPROACH_AXIS_LIMIT_LINEAGE_INVALID_REASON",
    "RETURN_APPROACH_AXIS_LIMIT_OBSERVATION_INVALID_REASON",
    "ReturnApproachAxisLimitConfig",
    "ReturnApproachAxisLimitDecision",
    "ReturnApproachAxisLimitService",
    "ReturnApproachAxisLimitState",
    "build_return_approach_axis_limit_log_fields",
]
