import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from testbed.perception.depth_graph import DepthGraphConfig, depth_frame_to_graph


def test_depth_graph_preview_cli_writes_ppm_images(tmp_path: Path) -> None:
    snapshot = tmp_path / "depth_camera_fixture.json"
    depth = np.ones((4, 4), dtype=np.float32)
    depth[1:3, 1:3] = 0.5
    snapshot.write_text(
        json.dumps(
            {
                "schema_version": "depth_camera_snapshot_v0",
                "metadata": {
                    "width": 4,
                    "height": 4,
                    "near_m": 0.1,
                    "far_m": 10.0,
                    "depth_semantics": "rendered_camera_eye_depth_m",
                },
                "depth_m": depth.reshape(-1).tolist(),
            }
        )
    )

    graph = depth_frame_to_graph(
        depth,
        DepthGraphConfig(max_nodes=6, knn_k=2, max_edges=12),
    )
    graph_path = tmp_path / "graph.npz"
    np.savez_compressed(
        graph_path,
        node_features=graph.node_features,
        node_mask=graph.node_mask,
        edge_indices=graph.edge_indices,
        edge_features=graph.edge_features,
        edge_mask=graph.edge_mask,
        graph_globals=graph.graph_globals,
        node_feature_names=np.asarray(graph.node_feature_names, dtype=object),
        edge_feature_names=np.asarray(graph.edge_feature_names, dtype=object),
        source_snapshot=str(snapshot),
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "testbed.cli.depth_graph_preview",
            str(snapshot),
            str(graph_path),
            "--output-dir",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    summary = json.loads(completed.stdout)
    depth_preview = Path(summary["depth_preview"])
    overlay = Path(summary["graph_overlay"])
    assert summary["node_count"] == 6
    assert summary["edge_count"] == 12
    assert "roi_uv" not in summary
    assert depth_preview.read_bytes().startswith(b"P6\n4 4\n255\n")
    assert overlay.read_bytes().startswith(b"P6\n4 4\n255\n")


def test_depth_graph_preview_cli_renders_roi_when_present(tmp_path: Path) -> None:
    snapshot = tmp_path / "depth_camera_fixture.json"
    depth = np.linspace(1.0, 4.0, 64, dtype=np.float32).reshape(8, 8)
    snapshot.write_text(
        json.dumps(
            {
                "schema_version": "depth_camera_snapshot_v0",
                "metadata": {
                    "width": 8,
                    "height": 8,
                    "near_m": 0.1,
                    "far_m": 10.0,
                    "depth_semantics": "rendered_camera_eye_depth_m",
                },
                "depth_m": depth.reshape(-1).tolist(),
            }
        )
    )

    config = DepthGraphConfig(
        max_nodes=8,
        knn_k=2,
        max_edges=16,
        gradient_node_ratio=0.5,
        roi_u_min=0.5,
        roi_u_max=1.0,
        roi_v_min=0.0,
        roi_v_max=0.5,
    )
    graph = depth_frame_to_graph(depth, config)
    graph_path = tmp_path / "graph_roi.npz"
    np.savez_compressed(
        graph_path,
        node_features=graph.node_features,
        node_mask=graph.node_mask,
        edge_indices=graph.edge_indices,
        edge_features=graph.edge_features,
        edge_mask=graph.edge_mask,
        graph_globals=graph.graph_globals,
        node_feature_names=np.asarray(graph.node_feature_names, dtype=object),
        edge_feature_names=np.asarray(graph.edge_feature_names, dtype=object),
        source_snapshot=str(snapshot),
        roi_uv=np.asarray([0.5, 1.0, 0.0, 0.5], dtype=np.float32),
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "testbed.cli.depth_graph_preview",
            str(snapshot),
            str(graph_path),
            "--output-dir",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    summary = json.loads(completed.stdout)
    assert summary["roi_uv"] == [0.5, 1.0, 0.0, 0.5]
    overlay = Path(summary["graph_overlay"])
    overlay_bytes = overlay.read_bytes()
    assert overlay_bytes.startswith(b"P6\n8 8\n255\n")
    body = overlay_bytes.split(b"\n", 3)[3]
    overlay_pixels = np.frombuffer(body, dtype=np.uint8).reshape(8, 8, 3)
    box_color = np.asarray([64, 220, 64], dtype=np.uint8)
    assert np.any(np.all(overlay_pixels[0, 3:8] == box_color, axis=-1))
    node_mask = graph.node_mask.astype(bool)
    assert node_mask.any()
    u_norm = graph.node_features[node_mask, 5]
    v_norm = graph.node_features[node_mask, 6]
    assert float(u_norm.min()) >= 0.5 - 1e-6
    assert float(v_norm.max()) <= 0.5 + 1e-6
