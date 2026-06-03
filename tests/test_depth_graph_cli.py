import json
import subprocess
import sys
from pathlib import Path

import numpy as np


def test_depth_graph_cli_writes_npz(tmp_path: Path) -> None:
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
    output = tmp_path / "graph.npz"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "testbed.cli.depth_graph",
            str(snapshot),
            "--output",
            str(output),
            "--max-nodes",
            "6",
            "--max-edges",
            "12",
            "--gradient-node-ratio",
            "0.5",
            "--min-depth",
            "0.1",
            "--max-depth",
            "10.0",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    summary = json.loads(completed.stdout)
    assert summary["node_count"] == 6
    assert summary["edge_count"] == 12
    loaded = np.load(output, allow_pickle=True)
    assert loaded["node_features"].shape == (6, 8)
    assert loaded["edge_features"].shape == (12, 5)
    assert "roi_uv" not in loaded.files


def test_depth_graph_cli_uses_metadata_intrinsics_when_present(tmp_path: Path) -> None:
    snapshot = tmp_path / "depth_camera_with_intrinsics.json"
    depth = np.full((3, 3), 2.0, dtype=np.float32)
    snapshot.write_text(
        json.dumps(
            {
                "schema_version": "depth_camera_snapshot_v0",
                "metadata": {
                    "width": 3,
                    "height": 3,
                    "near_m": 0.1,
                    "far_m": 10.0,
                    "depth_semantics": "rendered_camera_eye_depth_m",
                    "fx_px": 2.0,
                    "fy_px": 2.0,
                    "cx_px": 1.0,
                    "cy_px": 1.0,
                },
                "depth_m": depth.reshape(-1).tolist(),
            }
        )
    )
    output = tmp_path / "graph_intrinsics.npz"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "testbed.cli.depth_graph",
            str(snapshot),
            "--output",
            str(output),
            "--max-nodes",
            "1",
            "--knn-k",
            "0",
            "--max-edges",
            "0",
            "--gradient-node-ratio",
            "0.5",
            "--min-depth",
            "0.1",
            "--max-depth",
            "10.0",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    summary = json.loads(completed.stdout)
    assert summary["intrinsics_used"] is True
    assert summary["node_count"] == 1
    loaded = np.load(output, allow_pickle=True)
    node_features = np.asarray(loaded["node_features"], dtype=np.float32)
    point = node_features[0, :3]
    assert np.isclose(point[2], 2.0)
    assert abs(float(point[0])) <= 1.0 + 1e-6
    assert abs(float(point[1])) <= 1.0 + 1e-6


def test_depth_graph_cli_falls_back_to_heuristic_when_intrinsics_missing(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "depth_camera_legacy.json"
    depth = np.ones((4, 4), dtype=np.float32)
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
    output = tmp_path / "graph_legacy.npz"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "testbed.cli.depth_graph",
            str(snapshot),
            "--output",
            str(output),
            "--max-nodes",
            "4",
            "--max-edges",
            "4",
            "--gradient-node-ratio",
            "0.5",
            "--min-depth",
            "0.1",
            "--max-depth",
            "10.0",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    summary = json.loads(completed.stdout)
    assert summary["intrinsics_used"] is False


def test_depth_graph_cli_persists_roi_when_provided(tmp_path: Path) -> None:
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
    output = tmp_path / "graph_roi.npz"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "testbed.cli.depth_graph",
            str(snapshot),
            "--output",
            str(output),
            "--max-nodes",
            "8",
            "--max-edges",
            "16",
            "--gradient-node-ratio",
            "0.5",
            "--min-depth",
            "0.1",
            "--max-depth",
            "10.0",
            "--roi-u-min",
            "0.5",
            "--roi-u-max",
            "1.0",
            "--roi-v-min",
            "0.0",
            "--roi-v-max",
            "0.5",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    summary = json.loads(completed.stdout)
    assert summary["roi_uv"] == [0.5, 1.0, 0.0, 0.5]
    loaded = np.load(output, allow_pickle=True)
    assert "roi_uv" in loaded.files
    np.testing.assert_allclose(
        np.asarray(loaded["roi_uv"], dtype=np.float32),
        np.asarray([0.5, 1.0, 0.0, 0.5], dtype=np.float32),
    )
    node_mask = np.asarray(loaded["node_mask"], dtype=np.uint8).astype(bool)
    node_features = np.asarray(loaded["node_features"], dtype=np.float32)
    u_norm = node_features[node_mask, 5]
    v_norm = node_features[node_mask, 6]
    assert node_mask.any()
    assert float(u_norm.min()) >= 0.5 - 1e-6
    assert float(u_norm.max()) <= 1.0 + 1e-6
    assert float(v_norm.min()) >= 0.0 - 1e-6
    assert float(v_norm.max()) <= 0.5 + 1e-6
