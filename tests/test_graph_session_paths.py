import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import yaml

from testbed.cli.graph_session_paths import (
    depth_snapshot_dir_for_session,
    graph_dataset_dir_for_session,
    sanitize_session_id,
    session_data_dir,
    snapshot_map_for_session,
    teleop_dir_for_session,
)
from testbed.data.hdf5_io import read_episode, write_episode


def test_graph_session_path_conventions_are_stable() -> None:
    assert sanitize_session_id("graph smoke/003") == "graph_smoke_003"
    assert session_data_dir("graph_smoke_003") == Path(
        "data/graph_sessions/graph_smoke_003"
    )
    assert teleop_dir_for_session("graph_smoke_003") == Path(
        "data/graph_sessions/graph_smoke_003/teleop"
    )
    assert snapshot_map_for_session("graph_smoke_003") == Path(
        "data/graph_sessions/graph_smoke_003/graph_attach.yaml"
    )
    assert graph_dataset_dir_for_session("graph_smoke_003") == Path(
        "data/graph_sessions/graph_smoke_003/graph_time_v1"
    )
    assert depth_snapshot_dir_for_session(
        "graph_smoke_003",
        root="/tmp/depth-root",
    ) == Path("/tmp/depth-root/graph_smoke_003")


def test_build_graph_snapshot_map_graph_session_uses_session_subdir(
    tmp_path: Path,
) -> None:
    session = "graph_smoke_003"
    snapshot_root = tmp_path / "DepthCameraSnapshots" / session
    snapshot_root.mkdir(parents=True)
    _write_snapshot(
        snapshot_root / "depth_camera_graph_smoke_003_ep000000_seq000000_step000000_frame1.json",
        session_id=session,
        timestamp_ns=123,
    )

    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path.cwd())
    env["TESTBED_DEPTH_SNAPSHOT_ROOT"] = str(tmp_path / "DepthCameraSnapshots")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "testbed.cli.build_graph_snapshot_map",
            "--graph-session",
            session,
        ],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    output = tmp_path / "data" / "graph_sessions" / session / "graph_attach.yaml"
    payload = yaml.safe_load(output.read_text())
    assert payload["defaults"]["snapshot_root"] == str(snapshot_root.resolve())
    assert payload["episodes"][0]["snapshots"][0]["timestamp_ns"] == 123


def test_build_graph_dataset_graph_session_uses_derived_paths(tmp_path: Path) -> None:
    session = "graph_smoke_003"
    teleop_dir = tmp_path / "data" / "graph_sessions" / session / "teleop"
    teleop_dir.mkdir(parents=True)
    write_episode(
        teleop_dir / "episode_0.hdf5",
        qpos=np.zeros((2, 4), dtype=np.float32),
        qvel=np.zeros((2, 4), dtype=np.float32),
        actions=np.zeros((2, 4), dtype=np.float32),
        step_ns=np.asarray([100, 200], dtype=np.int64),
    )
    session_dir = tmp_path / "data" / "graph_sessions" / session
    snapshots = session_dir / "snapshots"
    snapshots.mkdir()
    _write_snapshot(snapshots / "depth_step_0.json", session_id=session, timestamp_ns=100)
    (session_dir / "graph_attach.yaml").write_text(
        "\n".join(
            [
                "defaults:",
                "  snapshot_root: snapshots",
                "episodes:",
                "  - episode_index: 0",
                "    snapshots:",
                "      - step_id: 0",
                "        timestamp_ns: 100",
                "        snapshot: depth_step_0.json",
                "",
            ]
        )
    )

    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path.cwd())
    subprocess.run(
        [
            sys.executable,
            "-m",
            "testbed.cli.build_graph_dataset",
            "--graph-session",
            session,
            "--max-nodes",
            "5",
            "--max-edges",
            "10",
        ],
        cwd=tmp_path,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    output = (
        tmp_path
        / "data"
        / "graph_sessions"
        / session
        / "graph_time_v1"
        / "episode_0.hdf5"
    )
    graph = read_episode(output, load_images=False)["observation_graph"]
    assert graph is not None
    np.testing.assert_array_equal(
        graph["source_time_ns"],
        np.asarray([100, 100], dtype=np.int64),
    )


def _write_snapshot(
    path: Path,
    *,
    session_id: str,
    timestamp_ns: int,
) -> None:
    path.write_text(
        (
            "{"
            '"schema_version":"depth_camera_snapshot_v0",'
            '"metadata":{'
            f'"session_id":"{session_id}",'
            '"episode_index":0,'
            '"sequence_index":0,'
            '"step_id":0,'
            f'"wall_time_unix_ns":{timestamp_ns},'
            '"width":3,'
            '"height":3,'
            '"near_m":0.1,'
            '"far_m":10.0,'
            '"fx_px":2.0,'
            '"fy_px":2.0,'
            '"cx_px":1.0,'
            '"cy_px":1.0,'
            '"depth_semantics":"rendered_camera_eye_depth_m"'
            "},"
            '"depth_m":[1,1,1,1,0.5,1,1,1,1]'
            "}"
        )
    )
