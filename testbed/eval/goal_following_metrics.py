"""Pure trajectory metrics for the goal-following benchmark."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

PHASE_POINT_COUNT = 64
ACT_TRACKING_MARGIN_M = 0.05
QPOS_ORDER = ("swing", "boom", "stick", "bucket")


@dataclass(frozen=True)
class GoalFollowingTrackingMetrics:
    """Geometry and path-tracking evidence for one completed dig."""

    geometry: Mapping[str, Any]
    phase_normalized_qpos: Mapping[str, Any]
    raw_time_qpos: Mapping[str, Any]
    dtw_qpos: Mapping[str, Any]
    worktool_tracking_3d: Mapping[str, Any]
    calibrated_qpos_tube_breach: bool
    worktool_margin_breach: bool

    @property
    def tracking_breach(self) -> bool:
        return self.calibrated_qpos_tube_breach or self.worktool_margin_breach


def compute_goal_following_tracking_metrics(
    *,
    planned_entry_xz_m: Sequence[float],
    actual_entry_xz_m: Sequence[float],
    planned_exit_xz_m: Sequence[float],
    actual_exit_xz_m: Sequence[float],
    planned_terrain_relative_depth_m: float,
    actual_terrain_relative_depth_m: float,
    planned_duration_s: float,
    actual_duration_s: float,
    reference_qpos_path: Sequence[Sequence[float]] | np.ndarray,
    actual_qpos_path: Sequence[Sequence[float]] | np.ndarray,
    reference_timestamps_s: Sequence[float] | np.ndarray,
    actual_timestamps_s: Sequence[float] | np.ndarray,
    reference_phase: Sequence[float] | np.ndarray,
    actual_phase: Sequence[float] | np.ndarray,
    qpos_abs_error_bound: Sequence[Sequence[float]] | np.ndarray,
    reference_worktool_path: Sequence[Sequence[float]] | np.ndarray,
    actual_worktool_path: Sequence[Sequence[float]] | np.ndarray,
) -> GoalFollowingTrackingMetrics:
    """Compute planned/actual geometry, qpos, DTW, and 3D errors."""

    planned_geometry = cut_geometry(
        entry=planned_entry_xz_m,
        exit_=planned_exit_xz_m,
        terrain_relative_depth_m=planned_terrain_relative_depth_m,
        duration_s=planned_duration_s,
        label="planned",
    )
    actual_geometry = cut_geometry(
        entry=actual_entry_xz_m,
        exit_=actual_exit_xz_m,
        terrain_relative_depth_m=actual_terrain_relative_depth_m,
        duration_s=actual_duration_s,
        label="actual",
    )
    reference_qpos = _finite_matrix(
        reference_qpos_path,
        width=4,
        minimum_rows=2,
        label="reference_qpos_path",
    )
    actual_qpos = _finite_matrix(
        actual_qpos_path,
        width=4,
        minimum_rows=2,
        label="actual_qpos_path",
    )
    reference_phase_array = _monotonic_coordinate(
        reference_phase,
        expected_rows=reference_qpos.shape[0],
        label="reference_phase",
        normalize=True,
    )
    actual_phase_array = _monotonic_coordinate(
        actual_phase,
        expected_rows=actual_qpos.shape[0],
        label="actual_phase",
        normalize=True,
    )
    progress = np.linspace(0.0, 1.0, PHASE_POINT_COUNT)
    reference_qpos_phase = _resample(
        reference_qpos,
        reference_phase_array,
        progress,
    )
    actual_qpos_phase = _resample(
        actual_qpos,
        actual_phase_array,
        progress,
    )
    phase_error = actual_qpos_phase - reference_qpos_phase
    phase_metrics = _per_dimension_error_summary(phase_error)

    reference_time = _monotonic_coordinate(
        reference_timestamps_s,
        expected_rows=reference_qpos.shape[0],
        label="reference_timestamps_s",
        normalize=False,
    )
    actual_time = _monotonic_coordinate(
        actual_timestamps_s,
        expected_rows=actual_qpos.shape[0],
        label="actual_timestamps_s",
        normalize=False,
    )
    common_start = max(reference_time[0], actual_time[0])
    common_end = min(reference_time[-1], actual_time[-1])
    if common_end <= common_start:
        raise ValueError("reference and actual timestamps must have positive overlap")
    common_time = np.linspace(
        common_start,
        common_end,
        PHASE_POINT_COUNT,
    )
    raw_time_error = _resample(
        actual_qpos,
        actual_time,
        common_time,
    ) - _resample(reference_qpos, reference_time, common_time)
    raw_time_metrics = _per_dimension_error_summary(raw_time_error)
    raw_time_metrics["overlap_duration_s"] = float(common_end - common_start)

    bounds = _finite_matrix(
        qpos_abs_error_bound,
        width=4,
        minimum_rows=PHASE_POINT_COUNT,
        label="qpos_abs_error_bound",
    )
    if bounds.shape != (PHASE_POINT_COUNT, 4) or np.any(bounds < 0.0):
        raise ValueError(
            "qpos_abs_error_bound must have shape (64, 4) and be non-negative"
        )
    qpos_tube_breach = bool(np.any(np.abs(phase_error) > bounds + 1.0e-12))

    reference_worktool = _finite_matrix(
        reference_worktool_path,
        width=3,
        minimum_rows=2,
        label="reference_worktool_path",
    )
    actual_worktool = _finite_matrix(
        actual_worktool_path,
        width=3,
        minimum_rows=2,
        label="actual_worktool_path",
    )
    if reference_worktool.shape[0] != reference_qpos.shape[0]:
        raise ValueError("reference worktool/qpos paths must have matching rows")
    if actual_worktool.shape[0] != actual_qpos.shape[0]:
        raise ValueError("actual worktool/qpos paths must have matching rows")
    worktool_error = np.linalg.norm(
        _resample(actual_worktool, actual_phase_array, progress)
        - _resample(reference_worktool, reference_phase_array, progress),
        axis=1,
    )
    worktool_metrics = _scalar_error_summary(worktool_error)
    worktool_metrics["tracking_margin_m"] = ACT_TRACKING_MARGIN_M
    worktool_margin_breach = bool(
        worktool_metrics["max_m"] > ACT_TRACKING_MARGIN_M + 1.0e-12
    )
    return GoalFollowingTrackingMetrics(
        geometry={
            "planned": planned_geometry,
            "actual": actual_geometry,
        },
        phase_normalized_qpos=phase_metrics,
        raw_time_qpos=raw_time_metrics,
        dtw_qpos=_dtw_metrics(reference_qpos, actual_qpos),
        worktool_tracking_3d=worktool_metrics,
        calibrated_qpos_tube_breach=qpos_tube_breach,
        worktool_margin_breach=worktool_margin_breach,
    )


def cut_geometry(
    *,
    entry: Sequence[float],
    exit_: Sequence[float],
    terrain_relative_depth_m: Any,
    duration_s: Any,
    label: str,
) -> dict[str, Any]:
    """Return entry/exit-derived direction and length with cut scalars."""

    entry_xz = finite_vector(entry, 2, label=f"{label}.entry_xz_m")
    exit_xz = finite_vector(exit_, 2, label=f"{label}.exit_xz_m")
    delta = (
        exit_xz[0] - entry_xz[0],
        exit_xz[1] - entry_xz[1],
    )
    length = math.hypot(*delta)
    if length <= 1.0e-12:
        raise ValueError(f"{label} cut entry/exit must be non-degenerate")
    depth = finite_float(
        terrain_relative_depth_m,
        label=f"{label}.terrain_relative_depth_m",
    )
    duration = finite_float(duration_s, label=f"{label}.duration_s")
    if duration <= 0.0:
        raise ValueError(f"{label}.duration_s must be positive")
    return {
        "entry_xz_m": list(entry_xz),
        "exit_xz_m": list(exit_xz),
        "direction_xz": [delta[0] / length, delta[1] / length],
        "length_m": length,
        "terrain_relative_depth_m": depth,
        "duration_s": duration,
    }


def finite_float(value: Any, *, label: str) -> float:
    """Parse one required finite scalar."""

    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be numeric") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{label} must be finite")
    return parsed


def finite_vector(
    value: Sequence[float] | np.ndarray,
    width: int,
    *,
    label: str,
) -> tuple[float, ...]:
    """Parse one required finite fixed-width vector."""

    array = np.asarray(value, dtype=np.float64)
    if array.shape != (width,) or not np.isfinite(array).all():
        raise ValueError(f"{label} must be a finite {width}D vector")
    return tuple(float(item) for item in array)


def _finite_matrix(
    value: Sequence[Sequence[float]] | np.ndarray,
    *,
    width: int,
    minimum_rows: int,
    label: str,
) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    if (
        array.ndim != 2
        or array.shape[1] != width
        or array.shape[0] < minimum_rows
        or not np.isfinite(array).all()
    ):
        raise ValueError(
            f"{label} must be a finite (N, {width}) matrix with at least "
            f"{minimum_rows} rows"
        )
    return array


def _monotonic_coordinate(
    value: Sequence[float] | np.ndarray,
    *,
    expected_rows: int,
    label: str,
    normalize: bool,
) -> np.ndarray:
    coordinate = np.asarray(value, dtype=np.float64)
    if (
        coordinate.shape != (expected_rows,)
        or not np.isfinite(coordinate).all()
        or np.any(np.diff(coordinate) <= 0.0)
    ):
        raise ValueError(
            f"{label} must be finite, strictly increasing, and match path rows"
        )
    if not normalize:
        return coordinate
    span = coordinate[-1] - coordinate[0]
    if span <= 0.0:
        raise ValueError(f"{label} must have positive span")
    return (coordinate - coordinate[0]) / span


def _resample(
    path: np.ndarray,
    coordinate: np.ndarray,
    target: np.ndarray,
) -> np.ndarray:
    return np.stack(
        [
            np.interp(target, coordinate, path[:, column])
            for column in range(path.shape[1])
        ],
        axis=1,
    )


def _per_dimension_error_summary(error: np.ndarray) -> dict[str, Any]:
    absolute = np.abs(error)
    return {
        "mae": np.mean(absolute, axis=0).tolist(),
        "rmse": np.sqrt(np.mean(np.square(error), axis=0)).tolist(),
        "p95": np.quantile(absolute, 0.95, axis=0).tolist(),
        "max": np.max(absolute, axis=0).tolist(),
        "end_error": absolute[-1].tolist(),
        "sample_count": int(error.shape[0]),
        "qpos_order": list(QPOS_ORDER),
    }


def _scalar_error_summary(error_m: np.ndarray) -> dict[str, Any]:
    return {
        "mean_m": float(np.mean(error_m)),
        "rmse_m": float(np.sqrt(np.mean(np.square(error_m)))),
        "p95_m": float(np.quantile(error_m, 0.95)),
        "max_m": float(np.max(error_m)),
        "end_error_m": float(error_m[-1]),
        "sample_count": int(error_m.shape[0]),
    }


def _dtw_metrics(reference: np.ndarray, actual: np.ndarray) -> dict[str, Any]:
    rows, columns = reference.shape[0], actual.shape[0]
    costs = np.full((rows + 1, columns + 1), np.inf, dtype=np.float64)
    costs[0, 0] = 0.0
    for row in range(1, rows + 1):
        for column in range(1, columns + 1):
            local = float(np.linalg.norm(reference[row - 1] - actual[column - 1]))
            costs[row, column] = local + min(
                costs[row - 1, column],
                costs[row, column - 1],
                costs[row - 1, column - 1],
            )
    pairs: list[tuple[int, int]] = []
    row, column = rows, columns
    while row > 0 and column > 0:
        pairs.append((row - 1, column - 1))
        predecessors = (
            (costs[row - 1, column - 1], row - 1, column - 1),
            (costs[row - 1, column], row - 1, column),
            (costs[row, column - 1], row, column - 1),
        )
        _, row, column = min(predecessors, key=lambda item: item[0])
    pairs.reverse()
    if not pairs:
        raise ValueError("DTW alignment produced no pairs")
    aligned_error = np.stack(
        [actual[right] - reference[left] for left, right in pairs],
        axis=0,
    )
    l2 = np.linalg.norm(aligned_error, axis=1)
    return {
        "alignment": "monotonic_dtw",
        "auxiliary_only": True,
        "path_length": len(pairs),
        "mean_l2_error": float(np.mean(l2)),
        "per_joint_mae": np.mean(np.abs(aligned_error), axis=0).tolist(),
        "qpos_order": list(QPOS_ORDER),
    }


__all__ = [
    "ACT_TRACKING_MARGIN_M",
    "GoalFollowingTrackingMetrics",
    "PHASE_POINT_COUNT",
    "QPOS_ORDER",
    "compute_goal_following_tracking_metrics",
    "cut_geometry",
    "finite_float",
    "finite_vector",
]
