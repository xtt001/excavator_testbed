"""Convert LiDAR point clouds into local 2.5D height/depth grids.

The converter is intentionally ROS-agnostic. Live ROS 2 nodes should parse
``sensor_msgs/msg/PointCloud2`` into an ``(N, 3)`` array and call this module.
Keeping the grid logic pure makes it easy to test and reuse for planners and
policies.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class LidarHeightmapConfig:
    """Grid bounds for a local LiDAR-derived terrain map.

    Coordinates follow the AGX/Unity convention used by the current sim:
    ``x`` and ``z`` are horizontal, ``y`` is vertical. Bounds are half-open:
    ``x_min_m <= x < x_max_m`` and ``z_min_m <= z < z_max_m``.
    """

    x_min_m: float = -5.0
    x_max_m: float = 5.0
    z_min_m: float = -5.0
    z_max_m: float = 5.0
    resolution_m: float = 0.05
    min_height_m: float | None = None
    max_height_m: float | None = None
    reference_height_m: float | None = None

    def validate(self) -> None:
        if self.resolution_m <= 0.0:
            raise ValueError("resolution_m must be positive.")
        if self.x_max_m <= self.x_min_m:
            raise ValueError("x_max_m must be greater than x_min_m.")
        if self.z_max_m <= self.z_min_m:
            raise ValueError("z_max_m must be greater than z_min_m.")
        if (
            self.min_height_m is not None
            and self.max_height_m is not None
            and self.max_height_m < self.min_height_m
        ):
            raise ValueError("max_height_m must be >= min_height_m.")

    @property
    def width(self) -> int:
        self.validate()
        return int(np.ceil((self.x_max_m - self.x_min_m) / self.resolution_m))

    @property
    def height(self) -> int:
        self.validate()
        return int(np.ceil((self.z_max_m - self.z_min_m) / self.resolution_m))


@dataclass(frozen=True)
class HeightmapResult:
    """Local 2.5D terrain grids derived from one point cloud frame."""

    height_m: np.ndarray
    depth_m: np.ndarray
    point_count: np.ndarray
    x_centers_m: np.ndarray
    z_centers_m: np.ndarray
    reference_height_m: float
    config: LidarHeightmapConfig

    @property
    def valid_mask(self) -> np.ndarray:
        return self.point_count > 0


def points_to_heightmap(
    points_xyz: np.ndarray,
    config: LidarHeightmapConfig | None = None,
) -> HeightmapResult:
    """Rasterize ``(x, y, z)`` points into local height and depth grids.

    The height of a cell is the maximum vertical ``y`` value of points that land
    in that cell. Depth is ``reference_height_m - height`` and is clipped at
    zero, so depressions become positive values while high obstacles remain zero.
    Empty cells are represented with ``NaN`` in both float grids and zero in
    ``point_count``.
    """

    cfg = config or LidarHeightmapConfig()
    cfg.validate()

    points = _as_xyz_array(points_xyz)
    width = cfg.width
    height = cfg.height
    x_centers = (
        cfg.x_min_m + (np.arange(width, dtype=np.float32) + 0.5) * cfg.resolution_m
    )
    z_centers = (
        cfg.z_min_m + (np.arange(height, dtype=np.float32) + 0.5) * cfg.resolution_m
    )

    max_grid = np.full((height, width), -np.inf, dtype=np.float32)
    counts = np.zeros((height, width), dtype=np.uint32)

    if points.size > 0:
        finite_mask = np.isfinite(points).all(axis=1)
        filtered = points[finite_mask]
        if cfg.min_height_m is not None:
            filtered = filtered[filtered[:, 1] >= float(cfg.min_height_m)]
        if cfg.max_height_m is not None:
            filtered = filtered[filtered[:, 1] <= float(cfg.max_height_m)]

        if filtered.size > 0:
            x = filtered[:, 0]
            y = filtered[:, 1]
            z = filtered[:, 2]
            col = np.floor((x - cfg.x_min_m) / cfg.resolution_m).astype(np.int64)
            row = np.floor((z - cfg.z_min_m) / cfg.resolution_m).astype(np.int64)
            in_bounds = (col >= 0) & (col < width) & (row >= 0) & (row < height)
            if np.any(in_bounds):
                valid_row = row[in_bounds]
                valid_col = col[in_bounds]
                np.maximum.at(max_grid, (valid_row, valid_col), y[in_bounds])
                np.add.at(counts, (valid_row, valid_col), 1)

    valid = counts > 0
    height_grid = np.full((height, width), np.nan, dtype=np.float32)
    height_grid[valid] = max_grid[valid]

    if cfg.reference_height_m is None:
        reference_height = float(np.nanmax(height_grid)) if np.any(valid) else 0.0
    else:
        reference_height = float(cfg.reference_height_m)

    depth_grid = np.full((height, width), np.nan, dtype=np.float32)
    depth_grid[valid] = np.maximum(0.0, reference_height - height_grid[valid])

    return HeightmapResult(
        height_m=height_grid,
        depth_m=depth_grid,
        point_count=counts,
        x_centers_m=x_centers,
        z_centers_m=z_centers,
        reference_height_m=reference_height,
        config=cfg,
    )


def save_heightmap_npz(result: HeightmapResult, path: str | Path) -> Path:
    """Persist a heightmap result as a compact NumPy artifact."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output_path,
        height_m=result.height_m,
        depth_m=result.depth_m,
        point_count=result.point_count,
        x_centers_m=result.x_centers_m,
        z_centers_m=result.z_centers_m,
        reference_height_m=np.asarray(result.reference_height_m, dtype=np.float32),
        bounds_m=np.asarray(
            [
                result.config.x_min_m,
                result.config.x_max_m,
                result.config.z_min_m,
                result.config.z_max_m,
            ],
            dtype=np.float32,
        ),
        resolution_m=np.asarray(result.config.resolution_m, dtype=np.float32),
    )
    return output_path


def _as_xyz_array(points_xyz: np.ndarray) -> np.ndarray:
    points = np.asarray(points_xyz, dtype=np.float32)
    if points.size == 0:
        return np.empty((0, 3), dtype=np.float32)
    if points.ndim != 2 or points.shape[1] != 3:
        raise ValueError("points_xyz must have shape (N, 3).")
    return points
