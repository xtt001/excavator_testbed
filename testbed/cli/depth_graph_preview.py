"""Render quick PPM previews for depth snapshots and depth-derived graphs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-depth-graph-preview",
        description="Visualize a Unity depth snapshot and its padded graph .npz as PPM images.",
    )
    parser.add_argument(
        "snapshot",
        type=Path,
        help="Path to depth_camera_*.json exported by DepthCameraSnapshotExporter.",
    )
    parser.add_argument(
        "graph",
        type=Path,
        help="Path to graph .npz written by tb-depth-graph.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for preview images. Defaults beside the graph file.",
    )
    parser.add_argument(
        "--node-radius",
        type=int,
        default=2,
        help="Node marker radius in pixels.",
    )
    args = parser.parse_args()

    snapshot = _load_snapshot(args.snapshot)
    meta = snapshot["metadata"]
    width = int(meta["width"])
    height = int(meta["height"])
    depth = np.asarray(snapshot["depth_m"], dtype=np.float32).reshape(height, width)

    graph = np.load(args.graph, allow_pickle=True)
    output_dir = args.output_dir or args.graph.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    base = args.graph.stem
    depth_path = output_dir / f"{base}_depth.ppm"
    overlay_path = output_dir / f"{base}_graph_overlay.ppm"

    depth_rgb = _depth_to_rgb(depth)
    overlay_rgb = depth_rgb.copy()
    _draw_edges(overlay_rgb, graph)
    _draw_nodes(overlay_rgb, graph, radius=max(1, int(args.node_radius)))
    roi_uv = _extract_roi(graph)
    if roi_uv is not None:
        _draw_roi_box(overlay_rgb, roi_uv)

    _write_ppm(depth_path, depth_rgb)
    _write_ppm(overlay_path, overlay_rgb)

    summary: dict[str, object] = {
        "depth_preview": str(depth_path),
        "graph_overlay": str(overlay_path),
        "depth_shape": [height, width],
        "node_count": int(np.asarray(graph["node_mask"]).sum()),
        "edge_count": int(np.asarray(graph["edge_mask"]).sum()),
    }
    if roi_uv is not None:
        summary["roi_uv"] = [float(value) for value in roi_uv]
    print(json.dumps(summary, indent=2))


def _load_snapshot(path: Path) -> dict:
    payload = json.loads(path.read_text())
    meta = payload.get("metadata") or {}
    width = int(meta.get("width", 0))
    height = int(meta.get("height", 0))
    depth = payload.get("depth_m")
    if width <= 0 or height <= 0:
        raise ValueError("Snapshot metadata must contain positive width/height.")
    if not isinstance(depth, list) or len(depth) != width * height:
        raise ValueError("Snapshot depth_m length does not match width*height.")
    return payload


def _depth_to_rgb(depth: np.ndarray) -> np.ndarray:
    valid = np.isfinite(depth) & (depth > 0.0)
    gray = np.zeros(depth.shape, dtype=np.uint8)
    if np.any(valid):
        valid_depth = depth[valid]
        low = float(np.percentile(valid_depth, 2.0))
        high = float(np.percentile(valid_depth, 98.0))
        if high <= low:
            high = low + 1.0
        normalized = np.clip((depth - low) / (high - low), 0.0, 1.0)
        gray = ((1.0 - normalized) * 255.0).astype(np.uint8)
        gray[~valid] = 0
    return np.repeat(gray[..., np.newaxis], 3, axis=2)


def _draw_nodes(image: np.ndarray, graph: np.lib.npyio.NpzFile, *, radius: int) -> None:
    node_features = np.asarray(graph["node_features"], dtype=np.float32)
    node_mask = np.asarray(graph["node_mask"], dtype=np.uint8).astype(bool)
    height, width = image.shape[:2]
    for row, col in _node_pixels(node_features, node_mask, width=width, height=height):
        r0 = max(0, row - radius)
        r1 = min(height, row + radius + 1)
        c0 = max(0, col - radius)
        c1 = min(width, col + radius + 1)
        image[r0:r1, c0:c1] = np.asarray([255, 48, 48], dtype=np.uint8)


def _draw_edges(image: np.ndarray, graph: np.lib.npyio.NpzFile) -> None:
    node_features = np.asarray(graph["node_features"], dtype=np.float32)
    node_mask = np.asarray(graph["node_mask"], dtype=np.uint8).astype(bool)
    edge_indices = np.asarray(graph["edge_indices"], dtype=np.int64)
    edge_mask = np.asarray(graph["edge_mask"], dtype=np.uint8).astype(bool)
    height, width = image.shape[:2]
    pixels = _node_pixels(node_features, node_mask, width=width, height=height)
    for src, dst in edge_indices[edge_mask]:
        if src < 0 or dst < 0 or src >= len(pixels) or dst >= len(pixels):
            continue
        _draw_line(image, pixels[int(src)], pixels[int(dst)])


def _node_pixels(
    node_features: np.ndarray,
    node_mask: np.ndarray,
    *,
    width: int,
    height: int,
) -> list[tuple[int, int]]:
    pixels: list[tuple[int, int]] = []
    for node in node_features[node_mask]:
        col = int(round(float(node[5]) * max(1, width - 1)))
        row = int(round(float(node[6]) * max(1, height - 1)))
        pixels.append((max(0, min(height - 1, row)), max(0, min(width - 1, col))))
    return pixels


def _extract_roi(graph: np.lib.npyio.NpzFile) -> np.ndarray | None:
    if "roi_uv" not in graph.files:
        return None
    roi = np.asarray(graph["roi_uv"], dtype=np.float32).reshape(-1)
    if roi.size != 4:
        return None
    return roi


def _draw_roi_box(image: np.ndarray, roi_uv: np.ndarray) -> None:
    height, width = image.shape[:2]
    u_min, u_max, v_min, v_max = (float(value) for value in roi_uv)
    col_min = int(round(max(0.0, min(1.0, u_min)) * max(1, width - 1)))
    col_max = int(round(max(0.0, min(1.0, u_max)) * max(1, width - 1)))
    row_min = int(round(max(0.0, min(1.0, v_min)) * max(1, height - 1)))
    row_max = int(round(max(0.0, min(1.0, v_max)) * max(1, height - 1)))
    if col_max < col_min or row_max < row_min:
        return
    color = np.asarray([64, 220, 64], dtype=np.uint8)
    image[row_min, col_min : col_max + 1] = color
    image[row_max, col_min : col_max + 1] = color
    image[row_min : row_max + 1, col_min] = color
    image[row_min : row_max + 1, col_max] = color


def _draw_line(image: np.ndarray, start: tuple[int, int], end: tuple[int, int]) -> None:
    r0, c0 = start
    r1, c1 = end
    steps = max(abs(r1 - r0), abs(c1 - c0), 1)
    rows = np.rint(np.linspace(r0, r1, steps + 1)).astype(np.int64)
    cols = np.rint(np.linspace(c0, c1, steps + 1)).astype(np.int64)
    image[rows, cols] = np.asarray([32, 220, 255], dtype=np.uint8)


def _write_ppm(path: Path, image: np.ndarray) -> None:
    if image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("image must have shape HxWx3.")
    header = f"P6\n{image.shape[1]} {image.shape[0]}\n255\n".encode("ascii")
    path.write_bytes(header + np.asarray(image, dtype=np.uint8).tobytes())


if __name__ == "__main__":
    main()
