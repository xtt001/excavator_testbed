"""Return start-envelope runtime config projection."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np


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


RETURN_START_ENVELOPE_RUNTIME_CONFIG_FIELDS: tuple[tuple[str, str], ...] = (
    ("use_cell_prior", "return_start_envelope_use_cell_prior"),
    ("min_source_count", "return_start_envelope_min_source_count"),
    ("min_source_fraction", "return_start_envelope_min_source_fraction"),
    ("qpos_from_relocate_enabled", "return_start_envelope_qpos_from_relocate_enabled"),
    (
        "qpos_from_relocate_coefficients",
        "return_start_envelope_qpos_from_relocate_coefficients",
    ),
    ("qpos_from_relocate_min", "return_start_envelope_qpos_from_relocate_min"),
    ("qpos_from_relocate_max", "return_start_envelope_qpos_from_relocate_max"),
    (
        "qpos_from_relocate_use_prior_qpos_bounds",
        "return_start_envelope_qpos_from_relocate_use_prior_qpos_bounds",
    ),
    (
        "spatial_from_relocate_enabled",
        "return_start_envelope_spatial_from_relocate_enabled",
    ),
    (
        "spatial_from_relocate_coefficients",
        "return_start_envelope_spatial_from_relocate_coefficients",
    ),
    ("spatial_from_relocate_min", "return_start_envelope_spatial_from_relocate_min"),
    ("spatial_from_relocate_max", "return_start_envelope_spatial_from_relocate_max"),
    (
        "spatial_from_relocate_use_prior_spatial_bounds",
        "return_start_envelope_spatial_from_relocate_use_prior_spatial_bounds",
    ),
    ("gate_enabled", "return_to_dig_start_envelope_gate_enabled"),
    ("spatial_tolerance", "return_to_dig_start_envelope_spatial_tolerance"),
    ("depth_tolerance_m", "return_to_dig_start_envelope_depth_tolerance_m"),
    (
        "local_depth_tolerance_m",
        "return_to_dig_start_envelope_local_depth_tolerance_m",
    ),
    (
        "plane_depth_tolerance_m",
        "return_to_dig_start_envelope_plane_depth_tolerance_m",
    ),
    ("plane_depth_mode", "return_to_dig_start_envelope_plane_depth_mode"),
    ("qpos_tolerance", "return_to_dig_start_envelope_qpos_tolerance"),
    ("require_contact", "return_to_dig_start_envelope_require_contact"),
)


def build_return_start_envelope_config(
    *,
    use_cell_prior: object = False,
    min_source_count: object = 1,
    min_source_fraction: object = 0.0,
    qpos_from_relocate_enabled: object = False,
    qpos_from_relocate_coefficients: Any | None = None,
    qpos_from_relocate_min: Any = (0.44, 0.50, 0.0, 0.0),
    qpos_from_relocate_max: Any = (0.56, 0.80, 0.56, 0.48),
    qpos_from_relocate_use_prior_qpos_bounds: object = False,
    spatial_from_relocate_enabled: object = False,
    spatial_from_relocate_coefficients: Any | None = None,
    spatial_from_relocate_min: Any = (-1.0, -0.10),
    spatial_from_relocate_max: Any = (1.0, 1.0),
    spatial_from_relocate_use_prior_spatial_bounds: object = False,
    gate_enabled: object = False,
    spatial_tolerance: object = 0.10,
    depth_tolerance_m: object = 0.08,
    local_depth_tolerance_m: object = 0.005,
    plane_depth_tolerance_m: object = 0.05,
    plane_depth_mode: object = "range",
    qpos_tolerance: object = 0.04,
    require_contact: object = True,
) -> ReturnStartEnvelopeConfig:
    return ReturnStartEnvelopeConfig(
        use_cell_prior=use_cell_prior,
        min_source_count=min_source_count,
        min_source_fraction=min_source_fraction,
        qpos_from_relocate_enabled=qpos_from_relocate_enabled,
        qpos_from_relocate_coefficients=qpos_from_relocate_coefficients,
        qpos_from_relocate_min=qpos_from_relocate_min,
        qpos_from_relocate_max=qpos_from_relocate_max,
        qpos_from_relocate_use_prior_qpos_bounds=(
            qpos_from_relocate_use_prior_qpos_bounds
        ),
        spatial_from_relocate_enabled=spatial_from_relocate_enabled,
        spatial_from_relocate_coefficients=spatial_from_relocate_coefficients,
        spatial_from_relocate_min=spatial_from_relocate_min,
        spatial_from_relocate_max=spatial_from_relocate_max,
        spatial_from_relocate_use_prior_spatial_bounds=(
            spatial_from_relocate_use_prior_spatial_bounds
        ),
        gate_enabled=gate_enabled,
        spatial_tolerance=spatial_tolerance,
        depth_tolerance_m=depth_tolerance_m,
        local_depth_tolerance_m=local_depth_tolerance_m,
        plane_depth_tolerance_m=plane_depth_tolerance_m,
        plane_depth_mode=plane_depth_mode,
        qpos_tolerance=qpos_tolerance,
        require_contact=require_contact,
    )


def build_return_start_envelope_config_from_mapping(
    values: Mapping[str, object],
) -> ReturnStartEnvelopeConfig:
    kwargs = {
        key: values[key] for key, _ in RETURN_START_ENVELOPE_RUNTIME_CONFIG_FIELDS
    }
    return build_return_start_envelope_config(**kwargs)


def normalize_plane_depth_mode(value: object) -> str:
    mode = str(value or "range").strip().lower().replace("-", "_")
    aliases = {
        "legacy": "range",
        "p05_p95": "range",
        "median_floor": "p50_floor",
        "target_floor": "p50_floor",
        "median_band": "target_band",
    }
    mode = aliases.get(mode, mode)
    if mode not in {"range", "p50_floor", "target_band"}:
        raise ValueError(
            "return_to_dig_start_envelope_plane_depth_mode must be one of "
            "'range', 'p50_floor', or 'target_band'"
        )
    return mode


def _optional_matrix(value: Any, *, shape: tuple[int, int]) -> np.ndarray | None:
    if value is None:
        return None
    return np.asarray(value, dtype=np.float32).reshape(shape)


def _vector(value: Any, *, shape: tuple[int, ...]) -> np.ndarray:
    return np.asarray(value, dtype=np.float32).reshape(shape)
