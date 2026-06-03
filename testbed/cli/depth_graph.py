"""Convert a Unity depth-camera snapshot JSON into graph tensors."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from testbed.perception.depth_graph import (
    DepthCameraIntrinsics,
    DepthGraphConfig,
    depth_frame_to_graph,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-depth-graph",
        description="Convert a Unity depth snapshot JSON into padded GNN graph tensors.",
    )
    parser.add_argument(
        "snapshot",
        type=Path,
        help="Path to depth_camera_*.json exported by DepthCameraSnapshotExporter.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output .npz path. Defaults beside the snapshot with _graph.npz suffix.",
    )
    parser.add_argument("--max-nodes", type=int, default=64)
    parser.add_argument("--knn-k", type=int, default=4)
    parser.add_argument("--max-edges", type=int, default=256)
    parser.add_argument(
        "--gradient-node-ratio",
        type=float,
        default=0.5,
        help="Fraction of graph nodes selected by depth-gradient keypoints; the rest are spatial coverage nodes.",
    )
    parser.add_argument(
        "--min-depth",
        type=float,
        default=None,
        help="Minimum valid depth in meters. Defaults to snapshot near_m.",
    )
    parser.add_argument(
        "--max-depth",
        type=float,
        default=None,
        help="Maximum valid depth in meters. Defaults to snapshot far_m.",
    )
    parser.add_argument(
        "--roi-u-min",
        type=float,
        default=None,
        help="Optional normalized horizontal ROI lower bound in [0, 1].",
    )
    parser.add_argument(
        "--roi-u-max",
        type=float,
        default=None,
        help="Optional normalized horizontal ROI upper bound in [0, 1].",
    )
    parser.add_argument(
        "--roi-v-min",
        type=float,
        default=None,
        help="Optional normalized vertical ROI lower bound in [0, 1].",
    )
    parser.add_argument(
        "--roi-v-max",
        type=float,
        default=None,
        help="Optional normalized vertical ROI upper bound in [0, 1].",
    )
    args = parser.parse_args()

    snapshot = _load_snapshot(args.snapshot)
    meta = snapshot["metadata"]
    width = int(meta["width"])
    height = int(meta["height"])
    depth = np.asarray(snapshot["depth_m"], dtype=np.float32).reshape(height, width)

    config = DepthGraphConfig(
        max_nodes=int(args.max_nodes),
        knn_k=int(args.knn_k),
        max_edges=int(args.max_edges),
        gradient_node_ratio=float(args.gradient_node_ratio),
        min_depth_m=float(args.min_depth) if args.min_depth is not None else float(meta.get("near_m", 0.001)),
        max_depth_m=(
            float(args.max_depth)
            if args.max_depth is not None
            else float(meta["far_m"]) if "far_m" in meta else None
        ),
        roi_u_min=args.roi_u_min,
        roi_u_max=args.roi_u_max,
        roi_v_min=args.roi_v_min,
        roi_v_max=args.roi_v_max,
    )
    intrinsics = DepthCameraIntrinsics.from_metadata(meta)
    graph = depth_frame_to_graph(depth, config, intrinsics)

    output_path = args.output or args.snapshot.with_name(
        f"{args.snapshot.stem}_graph.npz"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    savez_kwargs: dict[str, np.ndarray] = dict(
        node_features=graph.node_features,
        node_mask=graph.node_mask,
        edge_indices=graph.edge_indices,
        edge_features=graph.edge_features,
        edge_mask=graph.edge_mask,
        graph_globals=graph.graph_globals,
        node_feature_names=np.asarray(graph.node_feature_names, dtype=object),
        edge_feature_names=np.asarray(graph.edge_feature_names, dtype=object),
        source_snapshot=np.asarray(str(args.snapshot)),
    )
    roi_payload: list[float] | None = None
    if config.has_roi():
        u_min, u_max = config.resolved_roi_u()
        v_min, v_max = config.resolved_roi_v()
        roi_payload = [u_min, u_max, v_min, v_max]
        savez_kwargs["roi_uv"] = np.asarray(roi_payload, dtype=np.float32)
    np.savez_compressed(output_path, **savez_kwargs)
    summary: dict[str, object] = {
        "output": str(output_path),
        "depth_shape": [height, width],
        "node_count": int(graph.node_mask.sum()),
        "edge_count": int(graph.edge_mask.sum()),
        "depth_semantics": str(meta.get("depth_semantics", "")),
        "graph_globals": graph.graph_globals.tolist(),
        "intrinsics_used": intrinsics is not None,
    }
    if roi_payload is not None:
        summary["roi_uv"] = roi_payload
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


if __name__ == "__main__":
    main()
