"""Build small GNN graph tensors from depth-camera frames.

This module is deliberately Unity-agnostic. Repo B can export a true depth
image/depth grid later; Repo A can then convert that frame into the optional
``/observations/graph`` HDF5 group without depending on Unity internals.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

import numpy as np


NODE_FEATURE_NAMES = (
    "x_m",
    "y_m",
    "z_m",
    "depth_m",
    "gradient_m_per_px",
    "u_norm",
    "v_norm",
    "valid",
)

EDGE_FEATURE_NAMES = (
    "dx_m",
    "dy_m",
    "dz_m",
    "distance_m",
    "depth_delta_m",
)


@dataclass(frozen=True)
class DepthCameraIntrinsics:
    """Pinhole depth-camera intrinsics in pixel units."""

    fx_px: float
    fy_px: float
    cx_px: float
    cy_px: float

    def validate(self) -> None:
        if self.fx_px <= 0.0 or self.fy_px <= 0.0:
            raise ValueError("fx_px and fy_px must be positive.")

    @classmethod
    def from_metadata(cls, meta: Mapping[str, object]) -> "DepthCameraIntrinsics | None":
        """Build intrinsics from a depth-snapshot ``metadata`` mapping.

        Returns ``None`` when any of ``fx_px``, ``fy_px``, ``cx_px``, ``cy_px``
        is missing, non-finite, or non-positive — so callers can fall back to
        the pixel-size heuristic without raising on legacy snapshots.
        """

        try:
            fx = float(meta["fx_px"])  # type: ignore[index]
            fy = float(meta["fy_px"])  # type: ignore[index]
            cx = float(meta["cx_px"])  # type: ignore[index]
            cy = float(meta["cy_px"])  # type: ignore[index]
        except (KeyError, TypeError, ValueError):
            return None
        for value in (fx, fy, cx, cy):
            if not math.isfinite(value):
                return None
            if value <= 0.0:
                return None
        return cls(fx_px=fx, fy_px=fy, cx_px=cx, cy_px=cy)


@dataclass(frozen=True)
class DepthGraphConfig:
    """Configuration for one padded graph built from a depth frame.

    ROI fields ``roi_u_min/u_max/v_min/v_max`` are optional normalized image
    coordinates in ``[0, 1]`` (u = horizontal, v = vertical). When all four are
    ``None`` the entire image participates in node selection (legacy behavior).
    When at least one bound is provided the others default to the image edge.
    This is an image-space crop only and is not semantic segmentation, so any
    excavator self-occlusion still occupying the ROI is treated as valid depth.
    """

    max_nodes: int = 64
    knn_k: int = 4
    max_edges: int = 256
    gradient_node_ratio: float = 0.5
    min_depth_m: float = 0.001
    max_depth_m: float | None = None
    pixel_size_x_m: float = 0.02
    pixel_size_y_m: float = 0.02
    roi_u_min: float | None = None
    roi_u_max: float | None = None
    roi_v_min: float | None = None
    roi_v_max: float | None = None

    def validate(self) -> None:
        if self.max_nodes <= 0:
            raise ValueError("max_nodes must be positive.")
        if self.knn_k < 0:
            raise ValueError("knn_k must be non-negative.")
        if self.max_edges < 0:
            raise ValueError("max_edges must be non-negative.")
        if not 0.0 <= self.gradient_node_ratio <= 1.0:
            raise ValueError("gradient_node_ratio must be between 0 and 1.")
        if self.min_depth_m < 0.0:
            raise ValueError("min_depth_m must be non-negative.")
        if self.max_depth_m is not None and self.max_depth_m < self.min_depth_m:
            raise ValueError("max_depth_m must be >= min_depth_m.")
        if self.pixel_size_x_m <= 0.0 or self.pixel_size_y_m <= 0.0:
            raise ValueError("pixel sizes must be positive.")
        for name, value in (
            ("roi_u_min", self.roi_u_min),
            ("roi_u_max", self.roi_u_max),
            ("roi_v_min", self.roi_v_min),
            ("roi_v_max", self.roi_v_max),
        ):
            if value is None:
                continue
            if not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"{name} must be within [0, 1].")
        u_min, u_max = self.resolved_roi_u()
        v_min, v_max = self.resolved_roi_v()
        if u_min > u_max:
            raise ValueError("roi_u_min must be <= roi_u_max.")
        if v_min > v_max:
            raise ValueError("roi_v_min must be <= roi_v_max.")

    def has_roi(self) -> bool:
        return (
            self.roi_u_min is not None
            or self.roi_u_max is not None
            or self.roi_v_min is not None
            or self.roi_v_max is not None
        )

    def resolved_roi_u(self) -> tuple[float, float]:
        u_min = 0.0 if self.roi_u_min is None else float(self.roi_u_min)
        u_max = 1.0 if self.roi_u_max is None else float(self.roi_u_max)
        return u_min, u_max

    def resolved_roi_v(self) -> tuple[float, float]:
        v_min = 0.0 if self.roi_v_min is None else float(self.roi_v_min)
        v_max = 1.0 if self.roi_v_max is None else float(self.roi_v_max)
        return v_min, v_max


@dataclass(frozen=True)
class DepthGraphResult:
    """Padded graph tensors derived from one depth frame."""

    node_features: np.ndarray
    node_mask: np.ndarray
    edge_indices: np.ndarray
    edge_features: np.ndarray
    edge_mask: np.ndarray
    graph_globals: np.ndarray
    node_feature_names: tuple[str, ...]
    edge_feature_names: tuple[str, ...]

    def as_observation_graph(self) -> dict[str, np.ndarray]:
        """Return a one-frame payload compatible with HDF5 observation_graph."""

        return {
            "node_features": self.node_features[np.newaxis, ...].astype(np.float32),
            "node_mask": self.node_mask[np.newaxis, ...].astype(np.uint8),
            "edge_indices": self.edge_indices[np.newaxis, ...].astype(np.int64),
            "edge_features": self.edge_features[np.newaxis, ...].astype(np.float32),
            "edge_mask": self.edge_mask[np.newaxis, ...].astype(np.uint8),
            "graph_globals": self.graph_globals[np.newaxis, ...].astype(np.float32),
        }


def depth_frame_to_graph(
    depth_m: np.ndarray,
    config: DepthGraphConfig | None = None,
    intrinsics: DepthCameraIntrinsics | None = None,
) -> DepthGraphResult:
    """Convert one depth image into padded node/edge tensors.

    Nodes use a hybrid policy: high depth-gradient pixels preserve ridges,
    pit boundaries, and silhouettes, while uniformly spaced valid pixels keep
    broad terrain coverage. This keeps the graph useful even when excavator
    occlusions dominate the strongest gradients.
    """

    cfg = config or DepthGraphConfig()
    cfg.validate()
    if intrinsics is not None:
        intrinsics.validate()

    depth = _as_depth_image(depth_m)
    height, width = depth.shape

    # ROI semantics: treat ROI as a hard crop, not a soft mask. Building the
    # graph on the cropped view means the gradient sees only real adjacent
    # depth — no fake high-gradient ring along the ROI boundary from filling
    # outside pixels with a constant median.
    v_start, v_stop, u_start, u_stop = _roi_pixel_bounds(height, width, cfg)
    depth_crop = depth[v_start:v_stop, u_start:u_stop]

    valid_crop = np.isfinite(depth_crop) & (depth_crop >= cfg.min_depth_m)
    if cfg.max_depth_m is not None:
        valid_crop &= depth_crop <= float(cfg.max_depth_m)

    gradient_crop = _depth_gradient(depth_crop, valid_crop)
    rows_crop, cols_crop = _select_hybrid_pixels(
        gradient=gradient_crop,
        valid=valid_crop,
        max_nodes=cfg.max_nodes,
        gradient_node_ratio=cfg.gradient_node_ratio,
    )

    # Map crop-local pixel indices back into the full image so xyz
    # reconstruction uses original-image intrinsics and u_norm / v_norm match
    # the full frame's downstream contract.
    rows = rows_crop + v_start
    cols = cols_crop + u_start

    points = _pixels_to_points(depth, rows, cols, cfg, intrinsics)

    node_features = np.zeros((cfg.max_nodes, len(NODE_FEATURE_NAMES)), dtype=np.float32)
    node_mask = np.zeros((cfg.max_nodes,), dtype=np.uint8)
    node_count = int(points.shape[0])
    if node_count > 0:
        selected_depth = depth[rows, cols].astype(np.float32)
        selected_gradient = gradient_crop[rows_crop, cols_crop].astype(np.float32)
        u_norm = cols.astype(np.float32) / max(1.0, float(width - 1))
        v_norm = rows.astype(np.float32) / max(1.0, float(height - 1))
        node_features[:node_count] = np.column_stack(
            [
                points[:, 0],
                points[:, 1],
                points[:, 2],
                selected_depth,
                selected_gradient,
                u_norm,
                v_norm,
                np.ones((node_count,), dtype=np.float32),
            ]
        )
        node_mask[:node_count] = 1

    edge_indices, edge_features, edge_mask = _build_knn_edges(
        points=points,
        depth_values=depth[rows, cols].astype(np.float32) if node_count > 0 else np.empty((0,), dtype=np.float32),
        knn_k=cfg.knn_k,
        max_edges=cfg.max_edges,
    )

    valid_depth = depth_crop[valid_crop]
    graph_globals = np.asarray(
        [
            float(np.count_nonzero(valid_crop)) / float(depth.size),
            float(np.min(valid_depth)) if valid_depth.size else 0.0,
            float(np.max(valid_depth)) if valid_depth.size else 0.0,
            float(np.mean(valid_depth)) if valid_depth.size else 0.0,
            float(node_count),
            float(np.count_nonzero(edge_mask)),
        ],
        dtype=np.float32,
    )

    return DepthGraphResult(
        node_features=node_features,
        node_mask=node_mask,
        edge_indices=edge_indices,
        edge_features=edge_features,
        edge_mask=edge_mask,
        graph_globals=graph_globals,
        node_feature_names=NODE_FEATURE_NAMES,
        edge_feature_names=EDGE_FEATURE_NAMES,
    )


def _as_depth_image(depth_m: np.ndarray) -> np.ndarray:
    depth = np.asarray(depth_m, dtype=np.float32)
    if depth.ndim != 2:
        raise ValueError("depth_m must be a 2D array.")
    return depth


def _roi_pixel_bounds(
    height: int, width: int, config: DepthGraphConfig
) -> tuple[int, int, int, int]:
    """Resolve ROI normalized coords to half-open pixel ranges.

    Returns ``(v_start, v_stop, u_start, u_stop)`` so that
    ``depth[v_start:v_stop, u_start:u_stop]`` yields the ROI region. When no
    ROI is configured this is the full image, making ROI-less callers a
    transparent special case of the cropped path.

    Pixel selection matches the legacy normalized-mask semantics: a pixel
    ``c`` is included iff ``u_min <= c / (width - 1) <= u_max`` (and likewise
    for rows). ``ceil`` / ``floor`` round inward so floating-point ROI bounds
    never include a pixel the mask would have excluded.
    """

    if not config.has_roi():
        return 0, height, 0, width
    u_min, u_max = config.resolved_roi_u()
    v_min, v_max = config.resolved_roi_v()
    if width <= 1:
        u_start, u_stop = 0, width
    else:
        u_start = max(0, int(np.ceil(u_min * (width - 1))))
        u_stop = min(width, int(np.floor(u_max * (width - 1))) + 1)
    if height <= 1:
        v_start, v_stop = 0, height
    else:
        v_start = max(0, int(np.ceil(v_min * (height - 1))))
        v_stop = min(height, int(np.floor(v_max * (height - 1))) + 1)
    if u_stop < u_start:
        u_stop = u_start
    if v_stop < v_start:
        v_stop = v_start
    return v_start, v_stop, u_start, u_stop


def _depth_gradient(depth: np.ndarray, valid: np.ndarray) -> np.ndarray:
    if not np.any(valid):
        return np.zeros_like(depth, dtype=np.float32)
    fill_value = float(np.median(depth[valid]))
    filled = np.where(valid, depth, fill_value).astype(np.float32)
    grad_y, grad_x = np.gradient(filled)
    gradient = np.sqrt(grad_x * grad_x + grad_y * grad_y).astype(np.float32)
    gradient[~valid] = 0.0
    return gradient


def _select_hybrid_pixels(
    *,
    gradient: np.ndarray,
    valid: np.ndarray,
    max_nodes: int,
    gradient_node_ratio: float,
) -> tuple[np.ndarray, np.ndarray]:
    candidate_rows, candidate_cols = np.nonzero(valid)
    if candidate_rows.size == 0:
        return (
            np.empty((0,), dtype=np.int64),
            np.empty((0,), dtype=np.int64),
        )

    gradient_count = int(round(float(max_nodes) * float(gradient_node_ratio)))
    gradient_count = max(0, min(max_nodes, gradient_count))
    uniform_count = max_nodes - gradient_count
    selected: list[tuple[int, int]] = []
    selected_set: set[tuple[int, int]] = set()

    for row, col in _rank_keypoint_pixels(gradient, valid):
        if len(selected) >= gradient_count:
            break
        pixel = (int(row), int(col))
        selected.append(pixel)
        selected_set.add(pixel)

    for row, col in _rank_uniform_pixels(valid, max(0, uniform_count)):
        if len(selected) >= max_nodes:
            break
        pixel = (int(row), int(col))
        if pixel in selected_set:
            continue
        selected.append(pixel)
        selected_set.add(pixel)

    for row, col in _rank_keypoint_pixels(gradient, valid):
        if len(selected) >= max_nodes:
            break
        pixel = (int(row), int(col))
        if pixel in selected_set:
            continue
        selected.append(pixel)
        selected_set.add(pixel)

    rows = np.asarray([pixel[0] for pixel in selected], dtype=np.int64)
    cols = np.asarray([pixel[1] for pixel in selected], dtype=np.int64)
    return rows, cols


def _rank_keypoint_pixels(
    gradient: np.ndarray,
    valid: np.ndarray,
) -> list[tuple[int, int]]:
    candidate_rows, candidate_cols = np.nonzero(valid)
    if candidate_rows.size == 0:
        return []
    scores = gradient[candidate_rows, candidate_cols]
    order = np.lexsort((candidate_cols, candidate_rows, -scores))
    return [
        (int(candidate_rows[index]), int(candidate_cols[index]))
        for index in order
    ]


def _rank_uniform_pixels(valid: np.ndarray, target_count: int) -> list[tuple[int, int]]:
    if target_count <= 0:
        return []

    candidate_rows, candidate_cols = np.nonzero(valid)
    if candidate_rows.size == 0:
        return []

    height, width = valid.shape
    grid_cols = int(np.ceil(np.sqrt(target_count * max(1.0, width / max(1, height)))))
    grid_cols = max(1, min(width, grid_cols))
    grid_rows = int(np.ceil(target_count / grid_cols))
    grid_rows = max(1, min(height, grid_rows))

    row_targets = np.linspace(0.0, float(height - 1), grid_rows, dtype=np.float32)
    col_targets = np.linspace(0.0, float(width - 1), grid_cols, dtype=np.float32)

    ranked: list[tuple[int, int]] = []
    used: set[tuple[int, int]] = set()
    valid_points = np.column_stack([candidate_rows, candidate_cols]).astype(np.float32)
    for target_row in row_targets:
        for target_col in col_targets:
            distances = np.sum(
                (valid_points - np.asarray([target_row, target_col], dtype=np.float32)) ** 2,
                axis=1,
            )
            for index in np.argsort(distances, kind="stable"):
                pixel = (int(candidate_rows[index]), int(candidate_cols[index]))
                if pixel not in used:
                    ranked.append(pixel)
                    used.add(pixel)
                    break
            if len(ranked) >= target_count:
                return ranked

    return ranked


def _pixels_to_points(
    depth: np.ndarray,
    rows: np.ndarray,
    cols: np.ndarray,
    config: DepthGraphConfig,
    intrinsics: DepthCameraIntrinsics | None,
) -> np.ndarray:
    if rows.size == 0:
        return np.empty((0, 3), dtype=np.float32)
    z = depth[rows, cols].astype(np.float32)
    if intrinsics is not None:
        x = (cols.astype(np.float32) - float(intrinsics.cx_px)) * z / float(intrinsics.fx_px)
        y = -(rows.astype(np.float32) - float(intrinsics.cy_px)) * z / float(intrinsics.fy_px)
    else:
        center_col = (depth.shape[1] - 1) * 0.5
        center_row = (depth.shape[0] - 1) * 0.5
        x = (cols.astype(np.float32) - center_col) * float(config.pixel_size_x_m)
        y = -(rows.astype(np.float32) - center_row) * float(config.pixel_size_y_m)
    return np.column_stack([x, y, z]).astype(np.float32)


def _build_knn_edges(
    *,
    points: np.ndarray,
    depth_values: np.ndarray,
    knn_k: int,
    max_edges: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    edge_indices = np.zeros((max_edges, 2), dtype=np.int64)
    edge_features = np.zeros((max_edges, len(EDGE_FEATURE_NAMES)), dtype=np.float32)
    edge_mask = np.zeros((max_edges,), dtype=np.uint8)
    if points.shape[0] < 2 or knn_k <= 0 or max_edges <= 0:
        return edge_indices, edge_features, edge_mask

    edge_cursor = 0
    for src in range(points.shape[0]):
        diff = points - points[src]
        distances = np.linalg.norm(diff, axis=1)
        distances[src] = np.inf
        neighbor_order = np.argsort(distances, kind="stable")[:knn_k]
        for dst in neighbor_order:
            if not np.isfinite(distances[dst]) or edge_cursor >= max_edges:
                break
            delta = points[dst] - points[src]
            edge_indices[edge_cursor] = [src, int(dst)]
            edge_features[edge_cursor] = [
                delta[0],
                delta[1],
                delta[2],
                distances[dst],
                depth_values[dst] - depth_values[src],
            ]
            edge_mask[edge_cursor] = 1
            edge_cursor += 1
        if edge_cursor >= max_edges:
            break

    return edge_indices, edge_features, edge_mask
