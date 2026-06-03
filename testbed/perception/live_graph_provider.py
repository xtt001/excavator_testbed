"""Online graph providers for ACT_GRAPH eval."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from testbed.perception.depth_graph import (
    DepthCameraIntrinsics,
    DepthGraphConfig,
    depth_frame_to_graph,
)


@dataclass(frozen=True)
class LatestSnapshotGraphProviderConfig:
    snapshot_dir: Path
    max_nodes: int = 256
    knn_k: int = 4
    max_edges: int = 1024
    gradient_node_ratio: float = 0.5
    min_depth_m: float | None = None
    max_depth_m: float | None = None
    roi_u_min: float | None = None
    roi_u_max: float | None = None
    roi_v_min: float | None = None
    roi_v_max: float | None = None
    wait_for_first_timeout_s: float = 5.0
    poll_interval_s: float = 0.05
    reuse_last_graph: bool = True


class LatestSnapshotGraphProvider:
    """Build graph observations from the newest Unity depth snapshot JSON."""

    def __init__(self, config: LatestSnapshotGraphProviderConfig):
        self.config = config
        self.snapshot_dir = Path(config.snapshot_dir)
        self._last_path: Path | None = None
        self._last_graph: dict[str, np.ndarray] | None = None
        self._start_time_ns = 0

    def reset(self, *, start_time_ns: int | None = None) -> None:
        self._last_path = None
        self._last_graph = None
        self._start_time_ns = int(time.time_ns() if start_time_ns is None else start_time_ns)

    def get_graph(self, *, require_first: bool = False) -> dict[str, np.ndarray]:
        deadline = time.monotonic() + (
            float(self.config.wait_for_first_timeout_s) if require_first else 0.0
        )
        while True:
            latest = self._find_latest_snapshot()
            if latest is not None and latest != self._last_path:
                self._last_graph = self._build_graph(latest)
                self._last_path = latest
                return _copy_graph(self._last_graph)
            if self._last_graph is not None and self.config.reuse_last_graph:
                return _copy_graph(self._last_graph)
            if not require_first or time.monotonic() >= deadline:
                break
            time.sleep(max(0.001, float(self.config.poll_interval_s)))

        raise RuntimeError(
            "LatestSnapshotGraphProvider could not find a depth snapshot to build "
            f"an online graph under {self.snapshot_dir}."
        )

    def _find_latest_snapshot(self) -> Path | None:
        if not self.snapshot_dir.exists():
            return None
        candidates: list[tuple[int, Path]] = []
        for path in self.snapshot_dir.glob("*.json"):
            if not path.is_file():
                continue
            modified_time_ns = int(path.stat().st_mtime_ns)
            if modified_time_ns < self._start_time_ns:
                continue
            candidates.append((modified_time_ns, path))
        if not candidates:
            return None
        return max(candidates, key=lambda item: (item[0], item[1].name))[1]

    def _build_graph(self, path: Path) -> dict[str, np.ndarray]:
        payload = _load_snapshot(path)
        meta = payload["metadata"]
        width = int(meta["width"])
        height = int(meta["height"])
        depth = np.asarray(payload["depth_m"], dtype=np.float32).reshape(height, width)
        graph_config = DepthGraphConfig(
            max_nodes=int(self.config.max_nodes),
            knn_k=int(self.config.knn_k),
            max_edges=int(self.config.max_edges),
            gradient_node_ratio=float(self.config.gradient_node_ratio),
            min_depth_m=(
                float(self.config.min_depth_m)
                if self.config.min_depth_m is not None
                else float(meta.get("near_m", 0.001))
            ),
            max_depth_m=(
                float(self.config.max_depth_m)
                if self.config.max_depth_m is not None
                else float(meta["far_m"]) if "far_m" in meta else None
            ),
            roi_u_min=self.config.roi_u_min,
            roi_u_max=self.config.roi_u_max,
            roi_v_min=self.config.roi_v_min,
            roi_v_max=self.config.roi_v_max,
        )
        intrinsics = DepthCameraIntrinsics.from_metadata(meta)
        graph = depth_frame_to_graph(depth, graph_config, intrinsics)
        return {
            "node_features": graph.node_features.astype(np.float32),
            "node_mask": graph.node_mask.astype(np.uint8),
            "edge_indices": graph.edge_indices.astype(np.int64),
            "edge_features": graph.edge_features.astype(np.float32),
            "edge_mask": graph.edge_mask.astype(np.uint8),
            "graph_globals": graph.graph_globals.astype(np.float32),
        }


def build_latest_snapshot_graph_provider(raw_config: dict[str, Any]) -> LatestSnapshotGraphProvider:
    cfg = dict(raw_config or {})
    snapshot_dir = cfg.get("snapshot_dir") or cfg.get("snapshot_root")
    if not snapshot_dir:
        raise ValueError("graph_observation.snapshot_dir is required.")
    return LatestSnapshotGraphProvider(
        LatestSnapshotGraphProviderConfig(
            snapshot_dir=Path(snapshot_dir),
            max_nodes=int(cfg.get("max_nodes", 256)),
            knn_k=int(cfg.get("knn_k", 4)),
            max_edges=int(cfg.get("max_edges", 1024)),
            gradient_node_ratio=float(cfg.get("gradient_node_ratio", 0.5)),
            min_depth_m=_optional_float(cfg.get("min_depth_m", cfg.get("min_depth"))),
            max_depth_m=_optional_float(cfg.get("max_depth_m", cfg.get("max_depth"))),
            roi_u_min=_optional_float(cfg.get("roi_u_min")),
            roi_u_max=_optional_float(cfg.get("roi_u_max")),
            roi_v_min=_optional_float(cfg.get("roi_v_min")),
            roi_v_max=_optional_float(cfg.get("roi_v_max")),
            wait_for_first_timeout_s=float(cfg.get("wait_for_first_timeout_s", 5.0)),
            poll_interval_s=float(cfg.get("poll_interval_s", 0.05)),
            reuse_last_graph=bool(cfg.get("reuse_last_graph", True)),
        )
    )


def _load_snapshot(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    meta = payload.get("metadata") or {}
    width = int(meta.get("width", 0))
    height = int(meta.get("height", 0))
    depth = payload.get("depth_m")
    if width <= 0 or height <= 0:
        raise ValueError(f"Snapshot {path} metadata must contain positive width/height.")
    if not isinstance(depth, list) or len(depth) != width * height:
        raise ValueError(f"Snapshot {path} depth_m length does not match width*height.")
    return {"metadata": meta, "depth_m": depth}


def _copy_graph(graph: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    return {key: value.copy() for key, value in graph.items()}


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
