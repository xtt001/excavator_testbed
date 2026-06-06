"""Return start-envelope token and handoff-gate helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

import testbed.planner.return_start_envelope_config as _return_start_envelope_config
import testbed.planner.return_start_envelope_prior as _return_start_envelope_prior
from testbed.contracts.primitive_tokens import (
    CUT_RELOCATION_SLICE,
    CUT_VALID_IDX,
    RETURN_ENVELOPE_CONTACT_FLAG_IDX,
    RETURN_ENVELOPE_DEPTH_CENTER_IDX,
    RETURN_ENVELOPE_DEPTH_MAX_IDX,
    RETURN_ENVELOPE_DEPTH_MIN_IDX,
    RETURN_ENVELOPE_LONG_NORM_IDX,
    RETURN_ENVELOPE_QPOS_CENTER_SLICE,
    RETURN_ENVELOPE_QPOS_HALF_WIDTH_SLICE,
    RETURN_ENVELOPE_QPOS_VALID_IDX,
    RETURN_ENVELOPE_QVEL_ABS_MAX_IDX,
    RETURN_ENVELOPE_SHORT_NORM_IDX,
    RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX,
    RETURN_ENVELOPE_TIP_RADIUS_IDX,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    derive_return_relocate_token,
)
from testbed.data.operator_first_v2_2 import _build_dig_cut_token
from testbed.data.schema import (
    ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX,
    ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX,
)
from testbed.planner.snapshots import PlannerObservationView, env_state_from_obs

RETURN_START_ENVELOPE_RUNTIME_CONFIG_FIELDS = (
    _return_start_envelope_config.RETURN_START_ENVELOPE_RUNTIME_CONFIG_FIELDS
)
ReturnStartEnvelopeGatePriorContext = (
    _return_start_envelope_prior.ReturnStartEnvelopeGatePriorContext
)
ReturnStartEnvelopeConfig = _return_start_envelope_config.ReturnStartEnvelopeConfig
build_return_start_envelope_config = (
    _return_start_envelope_config.build_return_start_envelope_config
)
build_return_start_envelope_config_from_mapping = (
    _return_start_envelope_config.build_return_start_envelope_config_from_mapping
)
normalize_plane_depth_mode = _return_start_envelope_config.normalize_plane_depth_mode
return_start_envelope_gate_prior_context = (
    _return_start_envelope_prior.return_start_envelope_gate_prior_context
)
return_start_envelope_prior_bounds = (
    _return_start_envelope_prior.return_start_envelope_prior_bounds
)
return_start_envelope_prior_mapping = (
    _return_start_envelope_prior.return_start_envelope_prior_mapping
)
return_start_envelope_prior_token = (
    _return_start_envelope_prior.return_start_envelope_prior_token
)
return_start_envelope_token_from_prior_mapping = (
    _return_start_envelope_prior.return_start_envelope_token_from_prior_mapping
)
return_start_envelope_token_has_gate_bounds = (
    _return_start_envelope_prior.return_start_envelope_token_has_gate_bounds
)

@dataclass(frozen=True)
class ReturnStartEnvelopeState:
    token: np.ndarray | None = None
    source: str = "none"
    use_prior_spatial_bounds: bool = True
    use_prior_qpos_bounds: bool = True
    ready: bool = True
    error: float = float("nan")
    checks: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReturnStartEnvelopeTokenResult:
    token: np.ndarray
    source: str
    use_prior_spatial_bounds: bool
    use_prior_qpos_bounds: bool


@dataclass(frozen=True)
class ReturnStartEnvelopeBuildRequest:
    env_state: Any
    qpos: Any | None
    qvel: Any | None
    raw_fields: dict[str, float | int]
    action_dim: int
    dig_cut_prior: dict[str, Any] | None = None
    config: ReturnStartEnvelopeConfig = field(
        default_factory=ReturnStartEnvelopeConfig
    )
    cell_id: int | None = None


def build_return_start_envelope_request(
    *,
    env_state: Any,
    qpos: Any | None,
    qvel: Any | None,
    raw_fields: dict[str, float | int],
    action_dim: int,
    dig_cut_prior: dict[str, Any] | None = None,
    config: ReturnStartEnvelopeConfig | None = None,
    cell_id: int | None = None,
) -> ReturnStartEnvelopeBuildRequest:
    dim = int(action_dim)
    return ReturnStartEnvelopeBuildRequest(
        env_state=env_state,
        qpos=np.zeros(dim) if qpos is None else qpos,
        qvel=np.zeros(dim) if qvel is None else qvel,
        raw_fields=raw_fields,
        action_dim=dim,
        dig_cut_prior=dig_cut_prior,
        config=ReturnStartEnvelopeConfig() if config is None else config,
        cell_id=None if cell_id is None else int(cell_id),
    )


def build_return_start_envelope_request_from_observation_view(
    view: PlannerObservationView,
    *,
    raw_fields: dict[str, float | int],
    dig_cut_prior: dict[str, Any] | None = None,
    config: ReturnStartEnvelopeConfig | None = None,
    cell_id: int | None = None,
) -> ReturnStartEnvelopeBuildRequest:
    return build_return_start_envelope_request(
        env_state=env_state_from_obs(view.obs),
        qpos=view.obs.get("qpos", np.zeros(int(view.action_dim))),
        qvel=view.obs.get("qvel", np.zeros(int(view.action_dim))),
        raw_fields=raw_fields,
        action_dim=int(view.action_dim),
        dig_cut_prior=dig_cut_prior,
        config=config,
        cell_id=cell_id,
    )


def require_return_start_envelope_token_result(
    state: ReturnStartEnvelopeState,
) -> ReturnStartEnvelopeTokenResult:
    if state.token is None:
        raise RuntimeError("return start-envelope builder returned no token.")
    return ReturnStartEnvelopeTokenResult(
        token=np.asarray(state.token, dtype=np.float32),
        source=str(state.source),
        use_prior_spatial_bounds=bool(state.use_prior_spatial_bounds),
        use_prior_qpos_bounds=bool(state.use_prior_qpos_bounds),
    )


def build_return_start_envelope_for_plan(
    request: ReturnStartEnvelopeBuildRequest,
) -> ReturnStartEnvelopeState:
    mapping, mapping_source = return_start_envelope_prior_mapping(
        request.dig_cut_prior,
        config=request.config,
        cell_id=request.cell_id,
    )
    prior_token, prior_source = return_start_envelope_prior_token(
        mapping,
        source=mapping_source,
        cell_id=request.cell_id,
    )
    if prior_token is not None:
        return condition_return_start_envelope_from_relocate(
            prior_token.astype(np.float32),
            raw_fields=request.raw_fields,
            config=request.config,
            source=prior_source,
            use_prior_spatial_bounds=True,
            use_prior_qpos_bounds=True,
        )

    token = build_live_return_start_envelope_token(
        env_state=request.env_state,
        qpos=request.qpos,
        qvel=request.qvel,
        raw_fields=request.raw_fields,
        action_dim=request.action_dim,
    )
    return condition_return_start_envelope_from_relocate(
        token,
        raw_fields=request.raw_fields,
        config=request.config,
        source="live_current_obs_fallback",
        use_prior_spatial_bounds=True,
        use_prior_qpos_bounds=True,
    )


def build_live_return_start_envelope_token(
    *,
    env_state: Any,
    qpos: Any | None,
    qvel: Any | None,
    raw_fields: dict[str, float | int],
    action_dim: int,
) -> np.ndarray:
    token = np.zeros(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)
    env = np.asarray(env_state, dtype=np.float32).reshape(-1)
    if len(env) > ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX:
        token[RETURN_ENVELOPE_LONG_NORM_IDX] = float(
            env[ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX]
        )
    if len(env) > ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX:
        token[RETURN_ENVELOPE_SHORT_NORM_IDX] = float(
            env[ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX]
        )
    token[RETURN_ENVELOPE_DEPTH_CENTER_IDX] = float(
        max(0.0, float(raw_fields.get("operator_cut_depth_peak_m", 0.08)))
    )
    token[RETURN_ENVELOPE_TIP_RADIUS_IDX] = 0.20
    token[RETURN_ENVELOPE_DEPTH_MIN_IDX] = float(
        max(0.0, token[RETURN_ENVELOPE_DEPTH_CENTER_IDX] - 0.08)
    )
    token[RETURN_ENVELOPE_DEPTH_MAX_IDX] = float(
        token[RETURN_ENVELOPE_DEPTH_CENTER_IDX] + 0.08
    )
    token[RETURN_ENVELOPE_CONTACT_FLAG_IDX] = 0.0

    qpos_arr = _state_vector(qpos, action_dim)
    qvel_arr = _state_vector(qvel, action_dim)
    if qpos_arr.size >= 4 and np.all(np.isfinite(qpos_arr[:4])):
        token[RETURN_ENVELOPE_QPOS_CENTER_SLICE] = qpos_arr[:4]
        token[RETURN_ENVELOPE_QPOS_HALF_WIDTH_SLICE] = np.asarray(
            [0.05, 0.05, 0.05, 0.05],
            dtype=np.float32,
        )
        token[RETURN_ENVELOPE_QPOS_VALID_IDX] = 1.0
    if qvel_arr.size >= 4:
        token[RETURN_ENVELOPE_QVEL_ABS_MAX_IDX] = float(np.max(np.abs(qvel_arr[:4])))
    token[RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX] = 1.0
    return token.astype(np.float32)


def condition_return_start_envelope_from_relocate(
    token: Any,
    *,
    raw_fields: dict[str, float | int],
    config: ReturnStartEnvelopeConfig,
    source: str,
    use_prior_spatial_bounds: bool = True,
    use_prior_qpos_bounds: bool = True,
) -> ReturnStartEnvelopeState:
    token_arr = np.asarray(token, dtype=np.float32)
    if not config.qpos_from_relocate_enabled:
        return ReturnStartEnvelopeState(
            token=token_arr,
            source=source,
            use_prior_spatial_bounds=use_prior_spatial_bounds,
            use_prior_qpos_bounds=use_prior_qpos_bounds,
        )
    coefficients = config.qpos_from_relocate_coefficients
    if coefficients is None:
        return ReturnStartEnvelopeState(
            token=token_arr,
            source=source,
            use_prior_spatial_bounds=use_prior_spatial_bounds,
            use_prior_qpos_bounds=use_prior_qpos_bounds,
        )

    relocate_token = derive_return_relocate_token(_build_dig_cut_token(raw_fields))
    if (
        float(relocate_token[CUT_VALID_IDX]) <= 0.5
        or np.linalg.norm(relocate_token[CUT_RELOCATION_SLICE]) <= 1.0e-6
    ):
        return ReturnStartEnvelopeState(
            token=token_arr,
            source=source,
            use_prior_spatial_bounds=use_prior_spatial_bounds,
            use_prior_qpos_bounds=use_prior_qpos_bounds,
        )

    features = np.concatenate(
        [
            np.ones(1, dtype=np.float32),
            relocate_token[CUT_RELOCATION_SLICE].astype(np.float32),
        ]
    )
    qpos = np.asarray(coefficients @ features, dtype=np.float32).reshape(4)
    qpos = np.clip(
        qpos,
        config.qpos_from_relocate_min,
        config.qpos_from_relocate_max,
    )
    conditioned = token_arr.astype(np.float32, copy=True)
    source_suffixes: list[str] = []
    spatial_coefficients = config.spatial_from_relocate_coefficients
    if config.spatial_from_relocate_enabled and spatial_coefficients is not None:
        spatial = np.asarray(
            spatial_coefficients @ features,
            dtype=np.float32,
        ).reshape(2)
        spatial = np.clip(
            spatial,
            config.spatial_from_relocate_min,
            config.spatial_from_relocate_max,
        )
        conditioned[RETURN_ENVELOPE_LONG_NORM_IDX] = float(spatial[0])
        conditioned[RETURN_ENVELOPE_SHORT_NORM_IDX] = float(spatial[1])
        source_suffixes.append("relocate_spatial_linear")
        use_prior_spatial_bounds = bool(
            config.spatial_from_relocate_use_prior_spatial_bounds
        )

    conditioned[RETURN_ENVELOPE_QPOS_CENTER_SLICE] = qpos
    source_suffixes.append("relocate_qpos_linear")
    use_prior_qpos_bounds = bool(config.qpos_from_relocate_use_prior_qpos_bounds)
    return ReturnStartEnvelopeState(
        token=conditioned,
        source=f"{source}+{'+'.join(source_suffixes)}",
        use_prior_spatial_bounds=use_prior_spatial_bounds,
        use_prior_qpos_bounds=use_prior_qpos_bounds,
    )


def resolve_return_start_envelope_cell_id(
    *,
    corridor_id: int | None,
    corridor_cell_id: int | None = None,
) -> int | None:
    if corridor_id is None:
        return None
    if corridor_cell_id is not None:
        return int(corridor_cell_id)
    normalized = int(corridor_id)
    if normalized >= 0:
        return normalized
    return None


def return_to_dig_start_envelope_ready(
    token: Any,
    *,
    config: ReturnStartEnvelopeConfig,
    env_state: Any,
    qpos: Any | None,
    action_dim: int,
    lower: np.ndarray | None = None,
    upper: np.ndarray | None = None,
    prior_mapping: dict[str, object] | None = None,
    use_prior_spatial_bounds: bool = True,
    use_prior_qpos_bounds: bool = True,
) -> ReturnStartEnvelopeState:
    if not config.gate_enabled:
        return ReturnStartEnvelopeState(ready=True, error=float("nan"), checks={})

    token_arr = np.asarray(token, dtype=np.float32).reshape(-1)
    if token_arr.shape[0] != RETURN_START_ENVELOPE_TOKEN_DIM:
        return ReturnStartEnvelopeState(
            token=token_arr,
            ready=True,
            error=float("nan"),
            checks={"missing_token": True},
        )
    if (
        float(token_arr[RETURN_ENVELOPE_QPOS_VALID_IDX]) <= 0.5
        and float(token_arr[RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX]) <= 0.5
    ):
        return ReturnStartEnvelopeState(
            token=token_arr,
            ready=True,
            error=float("nan"),
            checks={"invalid_token": True},
        )

    checks: dict[str, Any] = {}
    max_error = 0.0
    ready = True

    def bounds_for(
        index: int,
        tolerance: float,
        *,
        use_prior_bounds: bool = True,
    ) -> tuple[float, float]:
        if use_prior_bounds and lower is not None and upper is not None:
            low = float(lower[index]) - float(tolerance)
            high = float(upper[index]) + float(tolerance)
        else:
            low = float(token_arr[index]) - float(tolerance)
            high = float(token_arr[index]) + float(tolerance)
        return low, high

    def add_check(name: str, value: float, low: float, high: float) -> bool:
        nonlocal max_error, ready
        finite = bool(np.isfinite(value) and np.isfinite(low) and np.isfinite(high))
        if not finite:
            ok = False
            error = float("inf")
        else:
            error = max(float(low) - float(value), float(value) - float(high), 0.0)
            ok = bool(error <= 1.0e-6)
            max_error = max(max_error, float(error))
        ready = bool(ready and ok)
        checks[name] = {
            "value": float(value),
            "min": float(low),
            "max": float(high),
            "ok": bool(ok),
            "error": float(error),
        }
        return bool(ok)

    env = np.asarray(env_state, dtype=np.float32).reshape(-1)
    local_depth_prior = (
        None if prior_mapping is None else prior_mapping.get("dig_start_local_depth_m")
    )
    local_depth_prior_used = False
    require_contact = bool(
        config.require_contact
        or float(token_arr[RETURN_ENVELOPE_CONTACT_FLAG_IDX]) > 0.5
    )
    if float(token_arr[RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX]) > 0.5:
        if len(env) > ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX:
            spatial_tol = config.spatial_tolerance
            low, high = bounds_for(
                RETURN_ENVELOPE_LONG_NORM_IDX,
                spatial_tol,
                use_prior_bounds=use_prior_spatial_bounds,
            )
            add_check(
                "long_norm",
                float(env[ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX]),
                low,
                high,
            )
            low, high = bounds_for(
                RETURN_ENVELOPE_SHORT_NORM_IDX,
                spatial_tol,
                use_prior_bounds=use_prior_spatial_bounds,
            )
            add_check(
                "short_norm",
                float(env[ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX]),
                low,
                high,
            )
        else:
            ready = False
            checks["spatial_missing"] = True

        if len(env) > ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX:
            local_value = float(env[ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX])
            if isinstance(local_depth_prior, dict):
                local_depth_prior_used = True
                local_tol = config.local_depth_tolerance_m
                p05 = float(
                    local_depth_prior.get("p05", token_arr[RETURN_ENVELOPE_DEPTH_MIN_IDX])
                )
                p50 = float(
                    local_depth_prior.get(
                        "p50",
                        token_arr[RETURN_ENVELOPE_DEPTH_CENTER_IDX],
                    )
                )
                p95 = float(
                    local_depth_prior.get("p95", token_arr[RETURN_ENVELOPE_DEPTH_MAX_IDX])
                )
                low = p05 - local_tol
                high = p95 + local_tol
                add_check("local_depth_m", local_value, low, high)
                checks["local_depth_m"].update(
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
                low = float(token_arr[RETURN_ENVELOPE_DEPTH_MIN_IDX]) - depth_tol
                high = float(token_arr[RETURN_ENVELOPE_DEPTH_MAX_IDX]) + depth_tol
                add_check("local_depth_m", local_value, low, high)
                checks["local_depth_m"].update({"mode": "token_range"})
        else:
            ready = False
            checks["local_depth_missing"] = True

        plane_depth_prior = (
            None
            if prior_mapping is None
            else prior_mapping.get("dig_start_plane_depth_m")
        )
        if isinstance(plane_depth_prior, dict):
            plane_tol = config.plane_depth_tolerance_m
            p05 = float(
                plane_depth_prior.get(
                    "p05",
                    token_arr[RETURN_ENVELOPE_DEPTH_CENTER_IDX],
                )
            )
            p50 = float(
                plane_depth_prior.get(
                    "p50",
                    token_arr[RETURN_ENVELOPE_DEPTH_CENTER_IDX],
                )
            )
            p95 = float(
                plane_depth_prior.get(
                    "p95",
                    token_arr[RETURN_ENVELOPE_DEPTH_MAX_IDX],
                )
            )
            mode = config.plane_depth_mode
            if mode == "target_band":
                low = p50 - plane_tol
                high = p50 + plane_tol
            elif mode == "p50_floor":
                plane_floor = p05 if local_depth_prior_used and require_contact else p50
                low = plane_floor - plane_tol
                high = p95 + plane_tol
            else:
                low = p05 - plane_tol
                high = p95 + plane_tol
            add_check(
                "plane_depth_m",
                float(env[ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX]),
                low,
                high,
            )
            checks["plane_depth_m"].update(
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
            if len(env) > ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX:
                contact = float(env[ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX])
                ok = bool(contact > 0.5)
                ready = bool(ready and ok)
                checks["dig_contact"] = {
                    "value": contact,
                    "ok": ok,
                    "required_by_config": bool(config.require_contact),
                    "required_by_token": bool(
                        float(token_arr[RETURN_ENVELOPE_CONTACT_FLAG_IDX]) > 0.5
                    ),
                }
            else:
                ready = False
                checks["dig_contact_missing"] = True

    if float(token_arr[RETURN_ENVELOPE_QPOS_VALID_IDX]) > 0.5:
        qpos_arr = _state_vector(qpos, action_dim)
        if qpos_arr.shape[0] >= 4:
            qpos_tol = config.qpos_tolerance
            for offset in range(4):
                index = int(RETURN_ENVELOPE_QPOS_CENTER_SLICE.start) + offset
                if use_prior_qpos_bounds and lower is not None and upper is not None:
                    low = float(lower[index]) - qpos_tol
                    high = float(upper[index]) + qpos_tol
                else:
                    half_width_index = (
                        int(RETURN_ENVELOPE_QPOS_HALF_WIDTH_SLICE.start) + offset
                    )
                    half_width = max(float(token_arr[half_width_index]), qpos_tol)
                    low = float(token_arr[index]) - half_width - qpos_tol
                    high = float(token_arr[index]) + half_width + qpos_tol
                add_check(f"qpos_{offset}", float(qpos_arr[offset]), low, high)
        else:
            ready = False
            checks["qpos_missing"] = True

    return ReturnStartEnvelopeState(
        token=token_arr,
        ready=bool(ready),
        error=float(max_error),
        checks=checks,
    )


def _state_vector(value: Any | None, action_dim: int) -> np.ndarray:
    if value is None:
        value = np.zeros(int(action_dim), dtype=np.float32)
    return np.asarray(value, dtype=np.float32).reshape(-1)
