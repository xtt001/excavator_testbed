"""Return start-envelope token and handoff-gate helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

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
    RETURN_START_ENVELOPE_TOKEN_KEY,
    derive_return_relocate_token,
    validate_primitive_token_shape,
)
from testbed.data.operator_first_v2_2 import _build_dig_cut_token
from testbed.data.schema import (
    ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX,
    ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX,
)


@dataclass(frozen=True)
class ReturnStartEnvelopeConfig:
    use_cell_prior: bool = False
    min_source_count: int = 1
    min_source_fraction: float = 0.0
    qpos_from_relocate_enabled: bool = False
    qpos_from_relocate_coefficients: Any | None = None
    qpos_from_relocate_min: Any = (0.44, 0.50, 0.0, 0.0)
    qpos_from_relocate_max: Any = (0.56, 0.80, 0.56, 0.48)
    qpos_from_relocate_use_prior_qpos_bounds: bool = False
    spatial_from_relocate_enabled: bool = False
    spatial_from_relocate_coefficients: Any | None = None
    spatial_from_relocate_min: Any = (-1.0, -0.10)
    spatial_from_relocate_max: Any = (1.0, 1.0)
    spatial_from_relocate_use_prior_spatial_bounds: bool = False
    gate_enabled: bool = False
    spatial_tolerance: float = 0.10
    depth_tolerance_m: float = 0.08
    local_depth_tolerance_m: float = 0.005
    plane_depth_tolerance_m: float = 0.05
    plane_depth_mode: str = "range"
    qpos_tolerance: float = 0.04
    require_contact: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "use_cell_prior", bool(self.use_cell_prior))
        object.__setattr__(
            self,
            "min_source_count",
            max(1, int(self.min_source_count)),
        )
        object.__setattr__(
            self,
            "min_source_fraction",
            max(0.0, float(self.min_source_fraction)),
        )
        object.__setattr__(
            self,
            "qpos_from_relocate_enabled",
            bool(self.qpos_from_relocate_enabled),
        )
        object.__setattr__(
            self,
            "qpos_from_relocate_coefficients",
            _optional_matrix(self.qpos_from_relocate_coefficients, shape=(4, 8)),
        )
        object.__setattr__(
            self,
            "qpos_from_relocate_min",
            _vector(self.qpos_from_relocate_min, shape=(4,)),
        )
        object.__setattr__(
            self,
            "qpos_from_relocate_max",
            _vector(self.qpos_from_relocate_max, shape=(4,)),
        )
        object.__setattr__(
            self,
            "qpos_from_relocate_use_prior_qpos_bounds",
            bool(self.qpos_from_relocate_use_prior_qpos_bounds),
        )
        object.__setattr__(
            self,
            "spatial_from_relocate_enabled",
            bool(self.spatial_from_relocate_enabled),
        )
        object.__setattr__(
            self,
            "spatial_from_relocate_coefficients",
            _optional_matrix(
                self.spatial_from_relocate_coefficients,
                shape=(2, 8),
            ),
        )
        object.__setattr__(
            self,
            "spatial_from_relocate_min",
            _vector(self.spatial_from_relocate_min, shape=(2,)),
        )
        object.__setattr__(
            self,
            "spatial_from_relocate_max",
            _vector(self.spatial_from_relocate_max, shape=(2,)),
        )
        object.__setattr__(
            self,
            "spatial_from_relocate_use_prior_spatial_bounds",
            bool(self.spatial_from_relocate_use_prior_spatial_bounds),
        )
        object.__setattr__(self, "gate_enabled", bool(self.gate_enabled))
        object.__setattr__(
            self,
            "spatial_tolerance",
            float(self.spatial_tolerance),
        )
        object.__setattr__(
            self,
            "depth_tolerance_m",
            float(self.depth_tolerance_m),
        )
        object.__setattr__(
            self,
            "local_depth_tolerance_m",
            float(self.local_depth_tolerance_m),
        )
        object.__setattr__(
            self,
            "plane_depth_tolerance_m",
            float(self.plane_depth_tolerance_m),
        )
        object.__setattr__(self, "plane_depth_mode", str(self.plane_depth_mode))
        object.__setattr__(self, "qpos_tolerance", float(self.qpos_tolerance))
        object.__setattr__(self, "require_contact", bool(self.require_contact))


@dataclass(frozen=True)
class ReturnStartEnvelopeState:
    token: np.ndarray | None = None
    source: str = "none"
    use_prior_spatial_bounds: bool = True
    use_prior_qpos_bounds: bool = True
    ready: bool = True
    error: float = float("nan")
    checks: dict[str, Any] = field(default_factory=dict)


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


def return_start_envelope_prior_mapping(
    dig_cut_prior: dict[str, Any] | None,
    *,
    config: ReturnStartEnvelopeConfig,
    cell_id: int | None,
) -> tuple[dict[str, object] | None, str]:
    if not dig_cut_prior:
        return None, "missing_dig_cut_prior"
    cells = dig_cut_prior.get("return_start_envelope_cells", [])
    if config.use_cell_prior and cell_id is not None and isinstance(cells, list):
        for cell in cells:
            cell_dict = dict(cell)
            if int(cell_dict.get("cell_id", -999999)) == int(cell_id):
                source_count = int(cell_dict.get("source_count", 0) or 0)
                source_fraction = float(cell_dict.get("source_fraction", 0.0) or 0.0)
                if (
                    source_count >= config.min_source_count
                    and source_fraction >= config.min_source_fraction
                ):
                    return cell_dict, "cell"
                break
    global_prior = dig_cut_prior.get("return_start_envelope_global")
    if isinstance(global_prior, dict):
        if config.use_cell_prior and cell_id is not None and isinstance(cells, list):
            return dict(global_prior), "global_low_support_cell"
        return dict(global_prior), "global"
    return None, "missing_return_start_envelope_prior"


def return_start_envelope_prior_token(
    mapping: dict[str, object] | None,
    *,
    source: str,
    cell_id: int | None,
) -> tuple[np.ndarray | None, str]:
    if mapping is not None:
        token = return_start_envelope_token_from_prior_mapping(mapping)
        if token is not None:
            if cell_id is not None and source == "cell":
                return token, f"qc6_return_start_envelope_cell_{int(cell_id)}"
            if cell_id is not None and source == "global_low_support_cell":
                return (
                    token,
                    f"qc6_return_start_envelope_global_low_support_cell_{int(cell_id)}",
                )
            return token, "qc6_return_start_envelope_global"
    return None, "missing_return_start_envelope_prior"


def return_start_envelope_prior_bounds(
    mapping: dict[str, object] | None,
) -> tuple[np.ndarray | None, np.ndarray | None]:
    if mapping is None:
        return None, None
    if "token_p05" not in mapping or "token_p95" not in mapping:
        return None, None
    lower = np.asarray(mapping["token_p05"], dtype=np.float32).reshape(-1)
    upper = np.asarray(mapping["token_p95"], dtype=np.float32).reshape(-1)
    if (
        lower.shape[0] != RETURN_START_ENVELOPE_TOKEN_DIM
        or upper.shape[0] != RETURN_START_ENVELOPE_TOKEN_DIM
    ):
        return None, None
    return lower.copy(), upper.copy()


def return_start_envelope_token_from_prior_mapping(
    mapping: dict[str, object],
) -> np.ndarray | None:
    for key in ("token_median", "token", "median"):
        if key not in mapping:
            continue
        token = np.asarray(mapping[key], dtype=np.float32).reshape(-1)
        try:
            token = validate_primitive_token_shape(
                RETURN_START_ENVELOPE_TOKEN_KEY,
                token,
                allow_sequence=False,
            ).reshape(-1)
        except ValueError as exc:
            raise ValueError(
                "return_start_envelope prior token must have "
                f"{RETURN_START_ENVELOPE_TOKEN_DIM} values, got {token.shape[0]}"
            ) from exc
        return token.copy()
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


def _optional_matrix(value: Any, *, shape: tuple[int, int]) -> np.ndarray | None:
    if value is None:
        return None
    return np.asarray(value, dtype=np.float32).reshape(shape)


def _vector(value: Any, *, shape: tuple[int, ...]) -> np.ndarray:
    return np.asarray(value, dtype=np.float32).reshape(shape)


def _state_vector(value: Any | None, action_dim: int) -> np.ndarray:
    if value is None:
        value = np.zeros(int(action_dim), dtype=np.float32)
    return np.asarray(value, dtype=np.float32).reshape(-1)
