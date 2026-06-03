from pathlib import Path
import json
import os
import time

import numpy as np
import pytest

from testbed.perception.live_graph_provider import (
    LatestSnapshotGraphProvider,
    LatestSnapshotGraphProviderConfig,
    build_latest_snapshot_graph_provider,
)


def test_latest_snapshot_graph_provider_builds_graph_from_newest_snapshot(tmp_path: Path) -> None:
    older = tmp_path / "depth_old.json"
    newer = tmp_path / "depth_new.json"
    _write_snapshot(older, timestamp_ns=100, depth_value=0.5)
    _write_snapshot(newer, timestamp_ns=200, depth_value=0.8)
    provider = LatestSnapshotGraphProvider(
        LatestSnapshotGraphProviderConfig(
            snapshot_dir=tmp_path,
            max_nodes=5,
            max_edges=10,
            wait_for_first_timeout_s=0.01,
        )
    )
    provider.reset(start_time_ns=0)

    graph = provider.get_graph(require_first=True)

    assert graph["node_features"].shape == (5, 8)
    assert graph["edge_indices"].shape == (10, 2)
    assert graph["graph_globals"].shape == (6,)
    assert graph["node_features"][graph["node_mask"].astype(bool), 3].mean() == pytest.approx(0.8)


def test_latest_snapshot_graph_provider_ignores_snapshots_before_reset(tmp_path: Path) -> None:
    _write_snapshot(tmp_path / "depth_old.json", timestamp_ns=100, depth_value=0.5)
    provider = LatestSnapshotGraphProvider(
        LatestSnapshotGraphProviderConfig(
            snapshot_dir=tmp_path,
            max_nodes=5,
            max_edges=10,
            wait_for_first_timeout_s=0.01,
            poll_interval_s=0.001,
        )
    )
    provider.reset(start_time_ns=200)

    with pytest.raises(RuntimeError, match="could not find"):
        provider.get_graph(require_first=True)


def test_latest_snapshot_graph_provider_reuses_cached_graph(tmp_path: Path) -> None:
    _write_snapshot(tmp_path / "depth.json", timestamp_ns=100, depth_value=0.5)
    provider = LatestSnapshotGraphProvider(
        LatestSnapshotGraphProviderConfig(
            snapshot_dir=tmp_path,
            max_nodes=5,
            max_edges=10,
            wait_for_first_timeout_s=0.01,
            reuse_last_graph=True,
        )
    )
    provider.reset(start_time_ns=0)
    first = provider.get_graph(require_first=True)
    (tmp_path / "depth.json").unlink()

    reused = provider.get_graph(require_first=False)

    np.testing.assert_array_equal(first["node_features"], reused["node_features"])


def test_build_latest_snapshot_graph_provider_requires_snapshot_dir() -> None:
    with pytest.raises(ValueError, match="snapshot_dir"):
        build_latest_snapshot_graph_provider({})


def _write_snapshot(path: Path, *, timestamp_ns: int, depth_value: float) -> None:
    width = 4
    height = 4
    payload = {
        "metadata": {
            "width": width,
            "height": height,
            "near_m": 0.1,
            "far_m": 5.0,
            "wall_time_unix_ns": int(timestamp_ns),
            "fx_px": 4.0,
            "fy_px": 4.0,
            "cx_px": 1.5,
            "cy_px": 1.5,
        },
        "depth_m": [float(depth_value)] * (width * height),
    }
    path.write_text(json.dumps(payload))
    os.utime(path, ns=(int(timestamp_ns), int(timestamp_ns)))
