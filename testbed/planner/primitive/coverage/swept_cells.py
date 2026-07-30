"""Project conservative coverage work-tool footprints onto the 3x2 grid."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


class CoverageGridGeometry(Protocol):
    """Geometry fields required by the physical-cell projection."""

    long_axis: int
    grid_long_count: int
    grid_short_count: int
    cell_long_size_m: float
    cell_short_size_m: float


@dataclass(frozen=True)
class CoverageCellBounds:
    cell_id: int
    x_min_m: float
    x_max_m: float
    z_min_m: float
    z_max_m: float


@dataclass(frozen=True)
class CoverageSweptFootprint:
    """One segment, its lateral-width polygon, and intersected physical cells."""

    polygon_xz_m: tuple[tuple[float, float], ...]
    centerline_cell_ids: tuple[int, ...]
    swept_cell_ids: tuple[int, ...]

    @classmethod
    def from_segment(
        cls,
        *,
        geometry: CoverageGridGeometry,
        entry_x_m: float,
        entry_z_m: float,
        exit_x_m: float,
        exit_z_m: float,
        worktool_width_m: float,
    ) -> CoverageSweptFootprint:
        points = np.asarray(
            [entry_x_m, entry_z_m, exit_x_m, exit_z_m, worktool_width_m],
            dtype=np.float64,
        )
        if not np.isfinite(points).all():
            raise ValueError("coverage swept footprint values must be finite")
        if float(worktool_width_m) <= 0.0:
            raise ValueError("coverage swept footprint width must be positive")
        entry = np.asarray([entry_x_m, entry_z_m], dtype=np.float64)
        exit_point = np.asarray([exit_x_m, exit_z_m], dtype=np.float64)
        delta = exit_point - entry
        length = float(np.linalg.norm(delta))
        if length <= 1.0e-9:
            raise ValueError("coverage swept footprint segment is zero length")
        perpendicular = np.asarray(
            [-delta[1], delta[0]],
            dtype=np.float64,
        ) / length
        offset = perpendicular * (0.5 * float(worktool_width_m))
        polygon = np.stack(
            [
                entry + offset,
                exit_point + offset,
                exit_point - offset,
                entry - offset,
            ]
        )
        cells = _cell_bounds(geometry)
        centerline = tuple(
            cell.cell_id
            for cell in cells
            if _segment_intersects_rect(entry, exit_point, cell)
        )
        swept = tuple(
            cell.cell_id
            for cell in cells
            if _polygon_intersects_rect(polygon, cell)
        )
        return cls(
            polygon_xz_m=tuple(
                (float(point[0]), float(point[1])) for point in polygon
            ),
            centerline_cell_ids=tuple(sorted(centerline)),
            swept_cell_ids=tuple(sorted(swept)),
        )


def _cell_bounds(
    geometry: CoverageGridGeometry,
) -> tuple[CoverageCellBounds, ...]:
    long_count = int(geometry.grid_long_count)
    short_count = int(geometry.grid_short_count)
    cell_long = float(geometry.cell_long_size_m)
    cell_short = float(geometry.cell_short_size_m)
    if long_count != 3 or short_count != 2:
        raise ValueError("coverage physical-cell projection requires a 3x2 grid")
    if int(geometry.long_axis) not in {0, 2}:
        raise ValueError("coverage physical-cell long_axis must be 0 or 2")
    half_long = 0.5 * long_count * cell_long
    half_short = 0.5 * short_count * cell_short
    result: list[CoverageCellBounds] = []
    for long_index in range(long_count):
        long_min = -half_long + long_index * cell_long
        long_max = long_min + cell_long
        for short_index in range(short_count):
            short_min = -half_short + short_index * cell_short
            short_max = short_min + cell_short
            if int(geometry.long_axis) == 0:
                x_min, x_max = long_min, long_max
                z_min, z_max = short_min, short_max
            else:
                x_min, x_max = short_min, short_max
                z_min, z_max = long_min, long_max
            result.append(
                CoverageCellBounds(
                    cell_id=int(long_index * short_count + short_index),
                    x_min_m=float(x_min),
                    x_max_m=float(x_max),
                    z_min_m=float(z_min),
                    z_max_m=float(z_max),
                )
            )
    return tuple(result)


def _point_in_rect(point: np.ndarray, rect: CoverageCellBounds) -> bool:
    tolerance = 1.0e-9
    return bool(
        rect.x_min_m - tolerance <= float(point[0]) <= rect.x_max_m + tolerance
        and rect.z_min_m - tolerance
        <= float(point[1])
        <= rect.z_max_m + tolerance
    )


def _segment_intersects_rect(
    start: np.ndarray,
    end: np.ndarray,
    rect: CoverageCellBounds,
) -> bool:
    if _point_in_rect(start, rect) or _point_in_rect(end, rect):
        return True
    corners = _rect_corners(rect)
    return any(
        _segments_intersect(start, end, corners[index], corners[(index + 1) % 4])
        for index in range(4)
    )


def _polygon_intersects_rect(
    polygon: np.ndarray,
    rect: CoverageCellBounds,
) -> bool:
    if any(_point_in_rect(point, rect) for point in polygon):
        return True
    corners = _rect_corners(rect)
    if any(_point_in_convex_polygon(corner, polygon) for corner in corners):
        return True
    for polygon_index in range(len(polygon)):
        polygon_start = polygon[polygon_index]
        polygon_end = polygon[(polygon_index + 1) % len(polygon)]
        for rect_index in range(4):
            if _segments_intersect(
                polygon_start,
                polygon_end,
                corners[rect_index],
                corners[(rect_index + 1) % 4],
            ):
                return True
    return False


def _rect_corners(rect: CoverageCellBounds) -> tuple[np.ndarray, ...]:
    return (
        np.asarray([rect.x_min_m, rect.z_min_m], dtype=np.float64),
        np.asarray([rect.x_max_m, rect.z_min_m], dtype=np.float64),
        np.asarray([rect.x_max_m, rect.z_max_m], dtype=np.float64),
        np.asarray([rect.x_min_m, rect.z_max_m], dtype=np.float64),
    )


def _point_in_convex_polygon(
    point: np.ndarray,
    polygon: np.ndarray,
) -> bool:
    tolerance = 1.0e-9
    signs: list[float] = []
    for index in range(len(polygon)):
        start = polygon[index]
        end = polygon[(index + 1) % len(polygon)]
        signs.append(_cross_2d(end - start, point - start))
    return bool(
        all(value >= -tolerance for value in signs)
        or all(value <= tolerance for value in signs)
    )


def _segments_intersect(
    first_start: np.ndarray,
    first_end: np.ndarray,
    second_start: np.ndarray,
    second_end: np.ndarray,
) -> bool:
    tolerance = 1.0e-9

    def orientation(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
        return _cross_2d(b - a, c - a)

    o1 = orientation(first_start, first_end, second_start)
    o2 = orientation(first_start, first_end, second_end)
    o3 = orientation(second_start, second_end, first_start)
    o4 = orientation(second_start, second_end, first_end)
    if (
        ((o1 > tolerance and o2 < -tolerance) or (o1 < -tolerance and o2 > tolerance))
        and ((o3 > tolerance and o4 < -tolerance) or (o3 < -tolerance and o4 > tolerance))
    ):
        return True
    for value, point, start, end in (
        (o1, second_start, first_start, first_end),
        (o2, second_end, first_start, first_end),
        (o3, first_start, second_start, second_end),
        (o4, first_end, second_start, second_end),
    ):
        if abs(value) <= tolerance and _point_on_segment(point, start, end):
            return True
    return False


def _point_on_segment(
    point: np.ndarray,
    start: np.ndarray,
    end: np.ndarray,
) -> bool:
    tolerance = 1.0e-9
    return bool(
        min(float(start[0]), float(end[0])) - tolerance
        <= float(point[0])
        <= max(float(start[0]), float(end[0])) + tolerance
        and min(float(start[1]), float(end[1])) - tolerance
        <= float(point[1])
        <= max(float(start[1]), float(end[1])) + tolerance
    )


def _cross_2d(first: np.ndarray, second: np.ndarray) -> float:
    return float(
        float(first[0]) * float(second[1])
        - float(first[1]) * float(second[0])
    )


__all__ = [
    "CoverageCellBounds",
    "CoverageGridGeometry",
    "CoverageSweptFootprint",
]
