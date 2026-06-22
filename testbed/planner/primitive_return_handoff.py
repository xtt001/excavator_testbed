"""Return handoff gate services for primitive planning."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.data.operator_first_v2_2 import RETURN_START_ENVELOPE_TOKEN_DIM
from testbed.data.schema import (
    ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX,
    ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX,
)


@dataclass(frozen=True)
class ReturnStartEnvelopeGateConfig:
    """Static gate configuration for return-to-dig start-envelope readiness."""

    enabled: bool
    action_dim: int
    spatial_tolerance: float
    depth_tolerance_m: float
    local_depth_tolerance_m: float
    plane_depth_tolerance_m: float
    plane_depth_mode: str
    qpos_tolerance: float
    require_contact: bool


@dataclass(frozen=True)
class ReturnStartEnvelopeGateInputs:
    """Per-tick inputs for return-to-dig start-envelope readiness."""

    token: Any
    env_state: Any
    qpos: Any
    prior_bounds: Callable[[], tuple[np.ndarray | None, np.ndarray | None]]
    prior_mapping: Callable[[], dict[str, object] | None]
    use_prior_spatial_bounds: bool
    use_prior_qpos_bounds: bool


@dataclass(frozen=True)
class ReturnStartEnvelopeGateResult:
    """Computed return-to-dig start-envelope gate state."""

    ready: bool
    error: float
    checks: dict[str, Any]


@dataclass(frozen=True)
class ReturnStartEnvelopeGateService:
    """Compute return-to-dig start-envelope readiness and diagnostic checks."""

    config: ReturnStartEnvelopeGateConfig

    def evaluate(
        self,
        inputs: ReturnStartEnvelopeGateInputs,
    ) -> ReturnStartEnvelopeGateResult:
        config = self.config
        if not config.enabled:
            return ReturnStartEnvelopeGateResult(
                ready=True,
                error=float("nan"),
                checks={},
            )

        token = np.asarray(inputs.token, dtype=np.float32).reshape(-1)
        if token.shape[0] != RETURN_START_ENVELOPE_TOKEN_DIM:
            return ReturnStartEnvelopeGateResult(
                ready=True,
                error=float("nan"),
                checks={"missing_token": True},
            )
        if float(token[16]) <= 0.5 and float(token[17]) <= 0.5:
            return ReturnStartEnvelopeGateResult(
                ready=True,
                error=float("nan"),
                checks={"invalid_token": True},
            )

        lower, upper = inputs.prior_bounds()
        prior_mapping = inputs.prior_mapping()
        state = _GateState()
        env_state = np.asarray(inputs.env_state, dtype=np.float32).reshape(-1)
        local_depth_prior = (
            None
            if prior_mapping is None
            else prior_mapping.get("dig_start_local_depth_m")
        )
        local_depth_prior_used = False
        require_contact = bool(config.require_contact or float(token[6]) > 0.5)

        if float(token[17]) > 0.5:
            if len(env_state) > ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX:
                spatial_tol = config.spatial_tolerance
                low, high = _bounds_for(
                    token=token,
                    lower=lower,
                    upper=upper,
                    index=0,
                    tolerance=spatial_tol,
                    use_prior_bounds=inputs.use_prior_spatial_bounds,
                )
                state.add_check(
                    "long_norm",
                    float(env_state[ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX]),
                    low,
                    high,
                )
                low, high = _bounds_for(
                    token=token,
                    lower=lower,
                    upper=upper,
                    index=1,
                    tolerance=spatial_tol,
                    use_prior_bounds=inputs.use_prior_spatial_bounds,
                )
                state.add_check(
                    "short_norm",
                    float(env_state[ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX]),
                    low,
                    high,
                )
            else:
                state.ready = False
                state.checks["spatial_missing"] = True

            if len(env_state) > ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX:
                local_value = float(
                    env_state[ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX]
                )
                if isinstance(local_depth_prior, dict):
                    local_depth_prior_used = True
                    local_tol = config.local_depth_tolerance_m
                    p05 = float(local_depth_prior.get("p05", token[4]))
                    p50 = float(local_depth_prior.get("p50", token[2]))
                    p95 = float(local_depth_prior.get("p95", token[5]))
                    state.add_check(
                        "local_depth_m",
                        local_value,
                        p05 - local_tol,
                        p95 + local_tol,
                    )
                    state.checks["local_depth_m"].update(
                        {
                            "mode": "prior_range",
                            "target": float(p50),
                            "p05": float(p05),
                            "p50": float(p50),
                            "p95": float(p95),
                        }
                    )
                else:
                    depth_tol = config.depth_tolerance_m
                    low = float(token[4]) - depth_tol
                    high = float(token[5]) + depth_tol
                    state.add_check("local_depth_m", local_value, low, high)
                    state.checks["local_depth_m"].update({"mode": "token_range"})
            else:
                state.ready = False
                state.checks["local_depth_missing"] = True

            plane_depth_prior = (
                None
                if prior_mapping is None
                else prior_mapping.get("dig_start_plane_depth_m")
            )
            if isinstance(plane_depth_prior, dict):
                plane_tol = config.plane_depth_tolerance_m
                p05 = float(plane_depth_prior.get("p05", token[2]))
                p50 = float(plane_depth_prior.get("p50", token[2]))
                p95 = float(plane_depth_prior.get("p95", token[5]))
                mode = str(config.plane_depth_mode)
                if mode == "target_band":
                    low = p50 - plane_tol
                    high = p50 + plane_tol
                elif mode == "p50_floor":
                    plane_floor = (
                        p05 if local_depth_prior_used and require_contact else p50
                    )
                    low = plane_floor - plane_tol
                    high = p95 + plane_tol
                else:
                    low = p05 - plane_tol
                    high = p95 + plane_tol
                state.add_check(
                    "plane_depth_m",
                    float(env_state[ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX]),
                    low,
                    high,
                )
                state.checks["plane_depth_m"].update(
                    {
                        "mode": str(mode),
                        "target": float(p50),
                        "p05": float(p05),
                        "p50": float(p50),
                        "p95": float(p95),
                        "floor_source": (
                            "p05_local_contact_prior"
                            if mode == "p50_floor"
                            and local_depth_prior_used
                            and require_contact
                            else "p50"
                            if mode == "p50_floor"
                            else "range"
                        ),
                    }
                )

            if require_contact:
                if len(env_state) > ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX:
                    contact = float(env_state[ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX])
                    ok = bool(contact > 0.5)
                    state.ready = bool(state.ready and ok)
                    state.checks["dig_contact"] = {
                        "value": contact,
                        "ok": ok,
                        "required_by_config": bool(config.require_contact),
                        "required_by_token": bool(float(token[6]) > 0.5),
                    }
                else:
                    state.ready = False
                    state.checks["dig_contact_missing"] = True

        if float(token[16]) > 0.5:
            qpos = np.asarray(inputs.qpos, dtype=np.float32).reshape(-1)
            if qpos.shape[0] >= 4:
                qpos_tol = config.qpos_tolerance
                for offset in range(4):
                    index = 7 + offset
                    if (
                        inputs.use_prior_qpos_bounds
                        and lower is not None
                        and upper is not None
                    ):
                        low = float(lower[index]) - qpos_tol
                        high = float(upper[index]) + qpos_tol
                    else:
                        half_width = max(float(token[11 + offset]), qpos_tol)
                        low = float(token[index]) - half_width - qpos_tol
                        high = float(token[index]) + half_width + qpos_tol
                    state.add_check(f"qpos_{offset}", float(qpos[offset]), low, high)
            else:
                state.ready = False
                state.checks["qpos_missing"] = True

        return ReturnStartEnvelopeGateResult(
            ready=bool(state.ready),
            error=float(state.max_error),
            checks=state.checks,
        )


@dataclass
class _GateState:
    ready: bool = True
    max_error: float = 0.0
    checks: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.checks is None:
            self.checks = {}

    def add_check(self, name: str, value: float, low: float, high: float) -> bool:
        finite = bool(np.isfinite(value) and np.isfinite(low) and np.isfinite(high))
        if not finite:
            ok = False
            error = float("inf")
        else:
            error = max(float(low) - float(value), float(value) - float(high), 0.0)
            ok = bool(error <= 1.0e-6)
            self.max_error = max(self.max_error, float(error))
        self.ready = bool(self.ready and ok)
        assert self.checks is not None
        self.checks[name] = {
            "value": float(value),
            "min": float(low),
            "max": float(high),
            "ok": bool(ok),
            "error": float(error),
        }
        return bool(ok)


def _bounds_for(
    *,
    token: np.ndarray,
    lower: np.ndarray | None,
    upper: np.ndarray | None,
    index: int,
    tolerance: float,
    use_prior_bounds: bool,
) -> tuple[float, float]:
    if use_prior_bounds and lower is not None and upper is not None:
        low = float(lower[index]) - float(tolerance)
        high = float(upper[index]) + float(tolerance)
    else:
        low = float(token[index]) - float(tolerance)
        high = float(token[index]) + float(tolerance)
    return low, high


__all__ = [
    "ReturnStartEnvelopeGateConfig",
    "ReturnStartEnvelopeGateInputs",
    "ReturnStartEnvelopeGateResult",
    "ReturnStartEnvelopeGateService",
]
