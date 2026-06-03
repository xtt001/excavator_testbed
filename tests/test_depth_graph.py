from pathlib import Path

import numpy as np

from testbed.data.hdf5_io import read_episode, write_episode
from testbed.perception.depth_graph import (
    DepthCameraIntrinsics,
    DepthGraphConfig,
    depth_frame_to_graph,
)


def test_depth_frame_to_graph_uses_hybrid_keypoints_and_coverage() -> None:
    depth = np.ones((5, 5), dtype=np.float32)
    depth[:, 3:] = 2.0
    config = DepthGraphConfig(max_nodes=4, knn_k=2, max_edges=8)

    graph = depth_frame_to_graph(depth, config)

    assert graph.node_features.shape == (4, 8)
    assert graph.edge_indices.shape == (8, 2)
    assert int(graph.node_mask.sum()) == 4
    assert int(graph.edge_mask.sum()) > 0
    u_norm = graph.node_features[:4, 5]
    gradient = graph.node_features[:4, 4]
    assert np.any(gradient > 0.0)
    assert float(np.max(u_norm) - np.min(u_norm)) >= 0.5


def test_depth_frame_to_graph_can_select_keypoints_only() -> None:
    depth = np.ones((5, 5), dtype=np.float32)
    depth[:, 3:] = 2.0
    config = DepthGraphConfig(
        max_nodes=4,
        knn_k=0,
        max_edges=0,
        gradient_node_ratio=1.0,
    )

    graph = depth_frame_to_graph(depth, config)

    u_norm = graph.node_features[:4, 5]
    assert np.all((u_norm >= 0.25) & (u_norm <= 0.75))


def test_depth_graph_config_rejects_invalid_gradient_ratio() -> None:
    depth = np.ones((3, 3), dtype=np.float32)
    config = DepthGraphConfig(gradient_node_ratio=1.5)

    try:
        depth_frame_to_graph(depth, config)
    except ValueError as exc:
        assert "gradient_node_ratio" in str(exc)
    else:
        raise AssertionError("Expected invalid gradient_node_ratio to raise.")


def test_depth_frame_to_graph_uses_camera_intrinsics_for_metric_points() -> None:
    depth = np.full((3, 3), 2.0, dtype=np.float32)
    config = DepthGraphConfig(max_nodes=1, knn_k=0, max_edges=0)
    intrinsics = DepthCameraIntrinsics(fx_px=2.0, fy_px=2.0, cx_px=1.0, cy_px=1.0)

    graph = depth_frame_to_graph(depth, config, intrinsics)

    assert int(graph.node_mask.sum()) == 1
    point = graph.node_features[0, :3]
    assert point.shape == (3,)
    assert np.isclose(point[2], 2.0)


def test_depth_frame_to_graph_handles_empty_valid_depth() -> None:
    depth = np.zeros((4, 4), dtype=np.float32)

    graph = depth_frame_to_graph(depth, DepthGraphConfig(max_nodes=3, max_edges=2))

    assert int(graph.node_mask.sum()) == 0
    assert int(graph.edge_mask.sum()) == 0
    assert np.all(graph.node_features == 0.0)


def test_depth_frame_to_graph_restricts_nodes_to_roi() -> None:
    depth = np.linspace(1.0, 4.0, 64, dtype=np.float32).reshape(8, 8)
    config = DepthGraphConfig(
        max_nodes=12,
        knn_k=2,
        max_edges=24,
        gradient_node_ratio=0.5,
        roi_u_min=0.5,
        roi_u_max=1.0,
        roi_v_min=0.0,
        roi_v_max=0.5,
    )

    graph = depth_frame_to_graph(depth, config)

    assert graph.node_features.shape == (12, 8)
    assert graph.edge_features.shape == (24, 5)
    mask = graph.node_mask.astype(bool)
    assert mask.any()
    u_norm = graph.node_features[mask, 5]
    v_norm = graph.node_features[mask, 6]
    assert float(u_norm.min()) >= 0.5 - 1e-6
    assert float(u_norm.max()) <= 1.0 + 1e-6
    assert float(v_norm.min()) >= 0.0 - 1e-6
    assert float(v_norm.max()) <= 0.5 + 1e-6


def test_depth_frame_to_graph_without_roi_matches_legacy() -> None:
    depth = np.linspace(1.0, 4.0, 64, dtype=np.float32).reshape(8, 8)
    config_default = DepthGraphConfig(max_nodes=8, knn_k=2, max_edges=16)
    config_full_roi = DepthGraphConfig(
        max_nodes=8,
        knn_k=2,
        max_edges=16,
        roi_u_min=0.0,
        roi_u_max=1.0,
        roi_v_min=0.0,
        roi_v_max=1.0,
    )

    legacy = depth_frame_to_graph(depth, config_default)
    full_roi = depth_frame_to_graph(depth, config_full_roi)

    np.testing.assert_array_equal(legacy.node_features, full_roi.node_features)
    np.testing.assert_array_equal(legacy.edge_indices, full_roi.edge_indices)
    np.testing.assert_array_equal(legacy.node_mask, full_roi.node_mask)


def test_depth_graph_config_rejects_inverted_roi() -> None:
    try:
        DepthGraphConfig(roi_u_min=0.9, roi_u_max=0.1).validate()
    except ValueError as exc:
        assert "roi_u_min" in str(exc)
    else:
        raise AssertionError("Expected inverted ROI to raise.")


def test_intrinsics_from_metadata_returns_instance_for_valid_floats() -> None:
    meta = {"fx_px": 320.0, "fy_px": 320.0, "cx_px": 31.5, "cy_px": 31.5}

    intrinsics = DepthCameraIntrinsics.from_metadata(meta)

    assert intrinsics is not None
    assert intrinsics.fx_px == 320.0
    assert intrinsics.fy_px == 320.0
    assert intrinsics.cx_px == 31.5
    assert intrinsics.cy_px == 31.5


def test_intrinsics_from_metadata_returns_none_when_field_missing() -> None:
    meta = {"fx_px": 320.0, "fy_px": 320.0, "cx_px": 31.5}

    assert DepthCameraIntrinsics.from_metadata(meta) is None


def test_intrinsics_from_metadata_returns_none_for_non_positive() -> None:
    base = {"fx_px": 320.0, "fy_px": 320.0, "cx_px": 31.5, "cy_px": 31.5}
    for key in ("fx_px", "fy_px", "cx_px", "cy_px"):
        meta = dict(base)
        meta[key] = 0.0
        assert DepthCameraIntrinsics.from_metadata(meta) is None, key
        meta[key] = -1.0
        assert DepthCameraIntrinsics.from_metadata(meta) is None, key


def test_intrinsics_from_metadata_returns_none_for_non_finite() -> None:
    meta_inf = {"fx_px": float("inf"), "fy_px": 320.0, "cx_px": 31.5, "cy_px": 31.5}
    assert DepthCameraIntrinsics.from_metadata(meta_inf) is None

    meta_nan = {"fx_px": 320.0, "fy_px": float("nan"), "cx_px": 31.5, "cy_px": 31.5}
    assert DepthCameraIntrinsics.from_metadata(meta_nan) is None


def test_intrinsics_from_metadata_returns_none_for_non_numeric() -> None:
    meta_bad = {"fx_px": None, "fy_px": 320.0, "cx_px": 31.5, "cy_px": 31.5}
    assert DepthCameraIntrinsics.from_metadata(meta_bad) is None


def test_depth_graph_payload_round_trips_through_hdf5(tmp_path: Path) -> None:
    depth = np.ones((4, 4), dtype=np.float32)
    depth[1:3, 1:3] = 0.5
    graph = depth_frame_to_graph(
        depth,
        DepthGraphConfig(max_nodes=6, knn_k=2, max_edges=12),
    )
    path = tmp_path / "episode_0.hdf5"

    write_episode(
        path,
        qpos=np.zeros((1, 4), dtype=np.float32),
        qvel=np.zeros((1, 4), dtype=np.float32),
        actions=np.zeros((1, 4), dtype=np.float32),
        images={"fpv": np.zeros((1, 4, 4, 3), dtype=np.uint8)},
        observation_graph=graph.as_observation_graph(),
    )

    episode = read_episode(path, load_images=False)
    loaded = episode["observation_graph"]

    assert loaded is not None
    assert loaded["node_features"].shape == (1, 6, 8)
    assert loaded["edge_features"].shape == (1, 12, 5)
    np.testing.assert_array_equal(loaded["node_mask"][0], graph.node_mask)
