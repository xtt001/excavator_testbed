"""Conservative 2D wall clearance for coverage cut corridors.

This module intentionally models a local DigArea X/Z swept footprint rather
than predicting future Unity articulation.  The footprint is the complete
entry-to-exit segment expanded by half the configured work-tool width in the
direction perpendicular to the cut.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.data.schema import (
    ENV_STATE_DIG_AREA_CELL_LONG_SIZE_IDX,
    ENV_STATE_DIG_AREA_CELL_SHORT_SIZE_IDX,
    ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX,
    ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX,
    ENV_STATE_DIG_AREA_LONG_AXIS_IDX,
)
from testbed.planner.primitive.coverage.swept_cells import (
    CoverageSweptFootprint,
)

CONSERVATIVE_2D_WORKTOOL_SWEPT_FOOTPRINT_PROFILE = (
    "conservative_2d_worktool_swept_footprint_v1"
)
NO_WALL_SAFE_CORRIDOR_REASON = "no_wall_safe_corridor"
WALL_SAFETY_CLASS_DISABLED = "disabled"
WALL_SAFETY_CLASS_CLEAR = "clear"
WALL_SAFETY_CLASS_NEAR = "near_wall"
WALL_SAFETY_CLASS_REJECT = "hard_reject"
WALL_SAFETY_CLASS_INVALID = "invalid_geometry"


class CoverageWallSafetyError(RuntimeError):
    """Base error for fail-closed coverage wall-safety contracts."""


class NoWallSafeCorridorError(CoverageWallSafetyError):
    """Raised when coverage planning cannot produce a wall-safe corridor."""

    def __init__(
        self,
        *,
        candidate_scores: list[dict[str, Any]] | None = None,
        detail: str = "",
        reason: str = NO_WALL_SAFE_CORRIDOR_REASON,
    ) -> None:
        self.reason = str(reason or NO_WALL_SAFE_CORRIDOR_REASON)
        self.detail = str(detail)
        self.candidate_scores = list(candidate_scores or [])
        message = self.reason if not self.detail else f"{self.reason}:{self.detail}"
        super().__init__(message)


class CoverageFinalWallSafetyError(CoverageWallSafetyError):
    """Raised when final raw fields invalidate a prototype-safe corridor."""

    def __init__(
        self,
        *,
        corridor_id: int,
        evaluation: CoverageWallSafetyEvaluation,
        raw_fields: Mapping[str, Any],
    ) -> None:
        self.corridor_id = int(corridor_id)
        self.evaluation = evaluation
        self.raw_fields = dict(raw_fields)
        detail = str(evaluation.rejection_reason or evaluation.safety_class)
        super().__init__(
            f"coverage_final_wall_safety_rejected:"
            f"corridor={self.corridor_id}:{detail}"
        )


@dataclass(frozen=True)
class CoverageWallSafetyConfig:
    """Central configuration for conservative coverage wall clearance."""

    enabled: bool = False
    profile: str = CONSERVATIVE_2D_WORKTOOL_SWEPT_FOOTPRINT_PROFILE
    worktool_width_m: float = 0.70
    hard_clearance_m: float = 0.30
    soft_clearance_m: float = 0.45
    max_score_penalty: float = 1.0
    missing_geometry: str = "fail_closed"

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, Any] | None,
    ) -> CoverageWallSafetyConfig:
        mapping = dict(values or {})
        config = cls(
            enabled=bool(mapping.get("enabled", False)),
            profile=str(
                mapping.get(
                    "profile",
                    CONSERVATIVE_2D_WORKTOOL_SWEPT_FOOTPRINT_PROFILE,
                )
            ).strip(),
            worktool_width_m=float(mapping.get("worktool_width_m", 0.70)),
            hard_clearance_m=float(mapping.get("hard_clearance_m", 0.30)),
            soft_clearance_m=float(mapping.get("soft_clearance_m", 0.45)),
            max_score_penalty=float(mapping.get("max_score_penalty", 1.0)),
            missing_geometry=str(
                mapping.get("missing_geometry", "fail_closed")
            ).strip(),
        )
        config.validate()
        return config

    def validate(self) -> None:
        numeric = (
            self.worktool_width_m,
            self.hard_clearance_m,
            self.soft_clearance_m,
            self.max_score_penalty,
        )
        if not all(np.isfinite(float(value)) for value in numeric):
            raise ValueError("coverage.wall_safety numeric fields must be finite.")
        if self.enabled and (
            self.profile
            != CONSERVATIVE_2D_WORKTOOL_SWEPT_FOOTPRINT_PROFILE
        ):
            raise ValueError(
                "coverage.wall_safety.profile must be "
                f"{CONSERVATIVE_2D_WORKTOOL_SWEPT_FOOTPRINT_PROFILE!r}."
            )
        if float(self.worktool_width_m) <= 0.0:
            raise ValueError(
                "coverage.wall_safety.worktool_width_m must be positive."
            )
        if float(self.hard_clearance_m) < 0.0:
            raise ValueError(
                "coverage.wall_safety.hard_clearance_m must be non-negative."
            )
        if float(self.soft_clearance_m) <= float(self.hard_clearance_m):
            raise ValueError(
                "coverage.wall_safety.soft_clearance_m must exceed "
                "hard_clearance_m."
            )
        if float(self.max_score_penalty) < 0.0:
            raise ValueError(
                "coverage.wall_safety.max_score_penalty must be non-negative."
            )
        if self.missing_geometry != "fail_closed":
            raise ValueError(
                "coverage.wall_safety.missing_geometry must be 'fail_closed'."
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.enabled),
            "profile": str(self.profile),
            "worktool_width_m": float(self.worktool_width_m),
            "hard_clearance_m": float(self.hard_clearance_m),
            "soft_clearance_m": float(self.soft_clearance_m),
            "max_score_penalty": float(self.max_score_penalty),
            "missing_geometry": str(self.missing_geometry),
        }


@dataclass(frozen=True)
class CoverageWallGeometry:
    """Axis-aligned DigArea half extents in its local X/Z coordinates."""

    long_axis: int
    grid_long_count: int
    grid_short_count: int
    cell_long_size_m: float
    cell_short_size_m: float
    half_x_m: float
    half_z_m: float

    @classmethod
    def from_env_state(cls, env_state: Any) -> CoverageWallGeometry:
        env = np.asarray(env_state, dtype=np.float64).reshape(-1)
        required_size = ENV_STATE_DIG_AREA_CELL_SHORT_SIZE_IDX + 1
        if env.size < required_size:
            raise CoverageWallSafetyError(
                f"wall_geometry_missing:env_state_dim={env.size}"
            )
        raw = np.asarray(
            [
                env[ENV_STATE_DIG_AREA_LONG_AXIS_IDX],
                env[ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX],
                env[ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX],
                env[ENV_STATE_DIG_AREA_CELL_LONG_SIZE_IDX],
                env[ENV_STATE_DIG_AREA_CELL_SHORT_SIZE_IDX],
            ],
            dtype=np.float64,
        )
        if not np.isfinite(raw).all():
            raise CoverageWallSafetyError("wall_geometry_non_finite")
        long_axis = int(round(float(raw[0])))
        grid_long_count = int(round(float(raw[1])))
        grid_short_count = int(round(float(raw[2])))
        if abs(float(raw[0]) - long_axis) > 1.0e-6 or long_axis not in {0, 2}:
            raise CoverageWallSafetyError(
                f"wall_geometry_long_axis_invalid:{raw[0]}"
            )
        if (
            abs(float(raw[1]) - grid_long_count) > 1.0e-6
            or grid_long_count != 3
        ):
            raise CoverageWallSafetyError(
                f"wall_geometry_grid_long_count_invalid:{raw[1]}"
            )
        if (
            abs(float(raw[2]) - grid_short_count) > 1.0e-6
            or grid_short_count != 2
        ):
            raise CoverageWallSafetyError(
                f"wall_geometry_grid_short_count_invalid:{raw[2]}"
            )
        cell_long_size_m = float(raw[3])
        cell_short_size_m = float(raw[4])
        if cell_long_size_m <= 0.0 or cell_short_size_m <= 0.0:
            raise CoverageWallSafetyError(
                "wall_geometry_cell_size_non_positive"
            )
        half_long = 0.5 * grid_long_count * cell_long_size_m
        half_short = 0.5 * grid_short_count * cell_short_size_m
        half_x_m, half_z_m = (
            (half_long, half_short)
            if long_axis == 0
            else (half_short, half_long)
        )
        return cls(
            long_axis=long_axis,
            grid_long_count=grid_long_count,
            grid_short_count=grid_short_count,
            cell_long_size_m=cell_long_size_m,
            cell_short_size_m=cell_short_size_m,
            half_x_m=float(half_x_m),
            half_z_m=float(half_z_m),
        )


@dataclass(frozen=True)
class CoverageWallSafetyEvaluation:
    """One immutable footprint classification and score adjustment."""

    profile: str
    enabled: bool
    eligible: bool
    safety_class: str
    rejection_reason: str
    box_half_x_m: float
    box_half_z_m: float
    footprint_outer_x_m: float
    footprint_outer_z_m: float
    clearance_x_m: float
    clearance_z_m: float
    minimum_clearance_m: float
    score_penalty: float
    centerline_cell_ids: tuple[int, ...] = ()
    swept_cell_ids: tuple[int, ...] = ()
    depth_exhausted_swept_cell_ids: tuple[int, ...] = ()

    @classmethod
    def disabled(cls) -> CoverageWallSafetyEvaluation:
        return cls(
            profile="",
            enabled=False,
            eligible=True,
            safety_class=WALL_SAFETY_CLASS_DISABLED,
            rejection_reason="",
            box_half_x_m=float("nan"),
            box_half_z_m=float("nan"),
            footprint_outer_x_m=float("nan"),
            footprint_outer_z_m=float("nan"),
            clearance_x_m=float("nan"),
            clearance_z_m=float("nan"),
            minimum_clearance_m=float("nan"),
            score_penalty=0.0,
            centerline_cell_ids=(),
            swept_cell_ids=(),
            depth_exhausted_swept_cell_ids=(),
        )

    @classmethod
    def invalid(
        cls,
        *,
        profile: str,
        rejection_reason: str,
        max_score_penalty: float,
    ) -> CoverageWallSafetyEvaluation:
        return cls(
            profile=str(profile),
            enabled=True,
            eligible=False,
            safety_class=WALL_SAFETY_CLASS_INVALID,
            rejection_reason=str(rejection_reason),
            box_half_x_m=float("nan"),
            box_half_z_m=float("nan"),
            footprint_outer_x_m=float("nan"),
            footprint_outer_z_m=float("nan"),
            clearance_x_m=float("nan"),
            clearance_z_m=float("nan"),
            minimum_clearance_m=float("nan"),
            score_penalty=float(max_score_penalty),
            centerline_cell_ids=(),
            swept_cell_ids=(),
            depth_exhausted_swept_cell_ids=(),
        )

    def as_trace_fields(self) -> dict[str, Any]:
        return {
            "wall_safety_profile": str(self.profile),
            "wall_safety_enabled": int(self.enabled),
            "wall_safety_eligible": int(self.eligible),
            "wall_safety_class": str(self.safety_class),
            "wall_safety_rejection_reason": str(self.rejection_reason),
            "wall_box_half_x_m": float(self.box_half_x_m),
            "wall_box_half_z_m": float(self.box_half_z_m),
            "wall_footprint_outer_x_m": float(self.footprint_outer_x_m),
            "wall_footprint_outer_z_m": float(self.footprint_outer_z_m),
            "wall_clearance_x_m": float(self.clearance_x_m),
            "wall_clearance_z_m": float(self.clearance_z_m),
            "wall_minimum_clearance_m": float(self.minimum_clearance_m),
            "wall_score_penalty": float(self.score_penalty),
            "wall_centerline_cell_ids": [
                int(value) for value in self.centerline_cell_ids
            ],
            "wall_swept_cell_ids": [
                int(value) for value in self.swept_cell_ids
            ],
            "depth_exhausted_swept_cell_ids": [
                int(value)
                for value in self.depth_exhausted_swept_cell_ids
            ],
        }

    def with_depth_exhausted_cells(
        self,
        cell_ids: set[int] | frozenset[int],
    ) -> CoverageWallSafetyEvaluation:
        from dataclasses import replace

        exhausted = tuple(
            sorted(set(int(value) for value in self.swept_cell_ids) & set(cell_ids))
        )
        return replace(
            self,
            depth_exhausted_swept_cell_ids=exhausted,
        )

    def as_depth_exhausted_rejection(
        self,
    ) -> CoverageWallSafetyEvaluation:
        from dataclasses import replace

        if not self.depth_exhausted_swept_cell_ids:
            return self
        return replace(
            self,
            eligible=False,
            rejection_reason=(
                "swept_footprint_intersects_depth_exhausted_cell"
            ),
        )


@dataclass(frozen=True)
class CoverageWallSafetyService:
    """Evaluate coverage corridors against conservative local box clearance."""

    config: CoverageWallSafetyConfig

    def __post_init__(self) -> None:
        self.config.validate()

    def evaluate_segment(
        self,
        *,
        env_state: Any,
        entry_x_m: float,
        entry_z_m: float,
        exit_x_m: float,
        exit_z_m: float,
    ) -> CoverageWallSafetyEvaluation:
        if not self.config.enabled:
            return CoverageWallSafetyEvaluation.disabled()
        try:
            geometry = CoverageWallGeometry.from_env_state(env_state)
            points = np.asarray(
                [entry_x_m, entry_z_m, exit_x_m, exit_z_m],
                dtype=np.float64,
            )
            if not np.isfinite(points).all():
                raise CoverageWallSafetyError(
                    "wall_geometry_corridor_non_finite"
                )
            delta_x = float(exit_x_m) - float(entry_x_m)
            delta_z = float(exit_z_m) - float(entry_z_m)
            length = float(np.hypot(delta_x, delta_z))
            if length <= 1.0e-9:
                raise CoverageWallSafetyError(
                    "wall_geometry_corridor_zero_length"
                )
            footprint = CoverageSweptFootprint.from_segment(
                geometry=geometry,
                entry_x_m=float(entry_x_m),
                entry_z_m=float(entry_z_m),
                exit_x_m=float(exit_x_m),
                exit_z_m=float(exit_z_m),
                worktool_width_m=float(self.config.worktool_width_m),
            )
        except (TypeError, ValueError, CoverageWallSafetyError) as exc:
            detail = str(exc).strip() or "wall_geometry_invalid"
            if not detail.startswith("wall_geometry_"):
                detail = f"wall_geometry_invalid:{detail}"
            return CoverageWallSafetyEvaluation.invalid(
                profile=self.config.profile,
                rejection_reason=detail,
                max_score_penalty=self.config.max_score_penalty,
            )

        outer_x = max(abs(point[0]) for point in footprint.polygon_xz_m)
        outer_z = max(abs(point[1]) for point in footprint.polygon_xz_m)
        clearance_x = float(geometry.half_x_m - outer_x)
        clearance_z = float(geometry.half_z_m - outer_z)
        minimum_clearance = float(min(clearance_x, clearance_z))

        hard = float(self.config.hard_clearance_m)
        soft = float(self.config.soft_clearance_m)
        boundary_tolerance = 1.0e-9
        if minimum_clearance < hard - boundary_tolerance:
            safety_class = WALL_SAFETY_CLASS_REJECT
            eligible = False
            rejection_reason = "wall_clearance_below_hard_minimum"
            score_penalty = float(self.config.max_score_penalty)
        elif minimum_clearance < soft - boundary_tolerance:
            safety_class = WALL_SAFETY_CLASS_NEAR
            eligible = True
            rejection_reason = ""
            interpolation = (soft - minimum_clearance) / (soft - hard)
            score_penalty = float(
                self.config.max_score_penalty
                * np.clip(interpolation, 0.0, 1.0)
            )
        else:
            safety_class = WALL_SAFETY_CLASS_CLEAR
            eligible = True
            rejection_reason = ""
            score_penalty = 0.0
        return CoverageWallSafetyEvaluation(
            profile=str(self.config.profile),
            enabled=True,
            eligible=eligible,
            safety_class=safety_class,
            rejection_reason=rejection_reason,
            box_half_x_m=float(geometry.half_x_m),
            box_half_z_m=float(geometry.half_z_m),
            footprint_outer_x_m=float(outer_x),
            footprint_outer_z_m=float(outer_z),
            clearance_x_m=float(clearance_x),
            clearance_z_m=float(clearance_z),
            minimum_clearance_m=float(minimum_clearance),
            score_penalty=float(score_penalty),
            centerline_cell_ids=tuple(footprint.centerline_cell_ids),
            swept_cell_ids=tuple(footprint.swept_cell_ids),
            depth_exhausted_swept_cell_ids=(),
        )

    def evaluate_raw_fields(
        self,
        *,
        env_state: Any,
        raw_fields: Mapping[str, Any],
    ) -> CoverageWallSafetyEvaluation:
        if not self.config.enabled:
            return CoverageWallSafetyEvaluation.disabled()
        try:
            return self.evaluate_segment(
                env_state=env_state,
                entry_x_m=float(raw_fields["operator_entry_x_m"]),
                entry_z_m=float(raw_fields["operator_entry_z_m"]),
                exit_x_m=float(raw_fields["operator_exit_x_m"]),
                exit_z_m=float(raw_fields["operator_exit_z_m"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            return CoverageWallSafetyEvaluation.invalid(
                profile=self.config.profile,
                rejection_reason=f"wall_geometry_raw_fields_invalid:{exc}",
                max_score_penalty=self.config.max_score_penalty,
            )


@dataclass(frozen=True)
class CoverageWallSafetyPrePolicyGuardPorts:
    """Callbacks needed to prepare guarded plans before ACT inference."""

    config: CoverageWallSafetyConfig
    current_skill_name: Callable[[], str]
    ensure_dig_plan: Callable[[dict[str, Any]], None]
    ensure_return_plan: Callable[[dict[str, Any]], None]
    terminal_neutral_action: Callable[[dict[str, Any], str], Any]
    dig_skill_name: str = "dig"
    return_skill_name: str = "return"


@dataclass(frozen=True)
class CoverageWallSafetyPrePolicyGuard:
    """Convert a no-safe planning result into a neutral-first terminal event."""

    ports: CoverageWallSafetyPrePolicyGuardPorts

    def apply(self, obs: dict[str, Any]) -> Any | None:
        if not self.ports.config.enabled:
            return None
        skill_name = str(self.ports.current_skill_name())
        try:
            if skill_name == self.ports.dig_skill_name:
                self.ports.ensure_dig_plan(obs)
            elif skill_name == self.ports.return_skill_name:
                self.ports.ensure_return_plan(obs)
            else:
                return None
        except NoWallSafeCorridorError as exc:
            return self.ports.terminal_neutral_action(
                obs,
                str(exc.reason),
            )
        return None


__all__ = [
    "CONSERVATIVE_2D_WORKTOOL_SWEPT_FOOTPRINT_PROFILE",
    "CoverageFinalWallSafetyError",
    "CoverageWallGeometry",
    "CoverageWallSafetyConfig",
    "CoverageWallSafetyError",
    "CoverageWallSafetyEvaluation",
    "CoverageWallSafetyPrePolicyGuard",
    "CoverageWallSafetyPrePolicyGuardPorts",
    "CoverageWallSafetyService",
    "NO_WALL_SAFE_CORRIDOR_REASON",
    "NoWallSafeCorridorError",
    "WALL_SAFETY_CLASS_CLEAR",
    "WALL_SAFETY_CLASS_DISABLED",
    "WALL_SAFETY_CLASS_INVALID",
    "WALL_SAFETY_CLASS_NEAR",
    "WALL_SAFETY_CLASS_REJECT",
]
