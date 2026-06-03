import json
import subprocess
import sys
from pathlib import Path

import numpy as np

from testbed.data.hdf5_io import read_episode, write_episode


def test_build_graph_dataset_end_to_end_smoke(tmp_path: Path) -> None:
    teleop_dir, snapshot_map, output_dir = _make_fixture(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "testbed.cli.build_graph_dataset",
            "--teleop-dir",
            str(teleop_dir),
            "--snapshot-map",
            str(snapshot_map),
            "--output-dir",
            str(output_dir),
            "--max-nodes",
            "5",
            "--max-edges",
            "10",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    output_episode = output_dir / "episode_000000.hdf5"
    assert output_episode.exists()
    episode = read_episode(output_episode, load_images=False)
    graph = episode["observation_graph"]

    assert graph is not None
    assert graph["node_features"].shape == (4, 5, 8)
    assert all(
        np.array_equal(graph["node_features"][0], graph["node_features"][t])
        for t in range(4)
    )

    lines = [json.loads(line) for line in completed.stdout.splitlines()]
    assert lines[0]["intrinsics_used"] is True
    assert lines[-1]["aggregate"] is True
    assert lines[-1]["episodes_processed"] == 1


def test_build_graph_dataset_dry_run_writes_nothing(tmp_path: Path) -> None:
    teleop_dir, snapshot_map, output_dir = _make_fixture(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "testbed.cli.build_graph_dataset",
            "--teleop-dir",
            str(teleop_dir),
            "--snapshot-map",
            str(snapshot_map),
            "--output-dir",
            str(output_dir),
            "--dry-run",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    lines = [json.loads(line) for line in completed.stdout.splitlines()]
    assert lines[0]["dry_run"] is True
    assert not list(output_dir.glob("episode_*.hdf5"))


def test_build_graph_dataset_missing_episode_reports_filename(tmp_path: Path) -> None:
    teleop_dir = tmp_path / "teleop"
    teleop_dir.mkdir()
    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    _write_snapshot(snapshots / "depth_camera_fixture.json")
    snapshot_map = tmp_path / "graph_attach.yaml"
    snapshot_map.write_text(
        "\n".join(
            [
                "defaults:",
                "  snapshot_root: snapshots",
                "episodes:",
                "  - episode_index: 5",
                "    snapshot: depth_camera_fixture.json",
                "",
            ]
        )
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "testbed.cli.build_graph_dataset",
            "--teleop-dir",
            str(teleop_dir),
            "--snapshot-map",
            str(snapshot_map),
            "--output-dir",
            str(tmp_path / "out"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "episode_000005.hdf5" in completed.stderr


def test_build_graph_dataset_aligns_snapshot_sequence_by_stride(tmp_path: Path) -> None:
    teleop_dir = tmp_path / "teleop"
    teleop_dir.mkdir()
    write_episode(
        teleop_dir / "episode_000000.hdf5",
        qpos=np.zeros((6, 4), dtype=np.float32),
        qvel=np.zeros((6, 4), dtype=np.float32),
        actions=np.zeros((6, 4), dtype=np.float32),
        metadata={"control_hz": 50},
    )

    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    _write_snapshot(snapshots / "depth_step_000000.json", center_depth=0.5)
    _write_snapshot(snapshots / "depth_step_000001.json", center_depth=0.6)
    _write_snapshot(snapshots / "depth_step_000002.json", center_depth=0.7)
    _write_snapshot(snapshots / "depth_step_000004.json", center_depth=0.9)
    snapshot_map = tmp_path / "graph_attach_sequence.yaml"
    snapshot_map.write_text(
        "\n".join(
            [
                "defaults:",
                "  snapshot_root: snapshots",
                "episodes:",
                "  - episode_index: 0",
                "    snapshots:",
                "      - step_id: 0",
                "        snapshot: depth_step_000000.json",
                "      - step_id: 1",
                "        snapshot: depth_step_000001.json",
                "      - step_id: 2",
                "        snapshot: depth_step_000002.json",
                "      - step_id: 4",
                "        snapshot: depth_step_000004.json",
                "",
            ]
        )
    )
    output_dir = tmp_path / "teleop_graph"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "testbed.cli.build_graph_dataset",
            "--teleop-dir",
            str(teleop_dir),
            "--snapshot-map",
            str(snapshot_map),
            "--output-dir",
            str(output_dir),
            "--max-nodes",
            "5",
            "--max-edges",
            "10",
            "--graph-stride",
            "2",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    graph = read_episode(
        output_dir / "episode_000000.hdf5",
        load_images=False,
    )["observation_graph"]
    assert graph is not None
    np.testing.assert_array_equal(
        graph["source_step_id"],
        np.asarray([0, 0, 2, 2, 4, 4], dtype=np.int64),
    )
    np.testing.assert_array_equal(
        graph["is_fresh"],
        np.asarray([1, 0, 1, 0, 1, 0], dtype=np.uint8),
    )
    assert not np.array_equal(graph["node_features"][0], graph["node_features"][2])

    lines = [json.loads(line) for line in completed.stdout.splitlines()]
    assert lines[0]["snapshot_count"] == 4
    assert lines[0]["graph_keyframe_count"] == 3
    assert lines[0]["fresh_count"] == 3


def test_build_graph_dataset_aligns_snapshot_sequence_by_rate(tmp_path: Path) -> None:
    teleop_dir = tmp_path / "teleop"
    teleop_dir.mkdir()
    write_episode(
        teleop_dir / "episode_000000.hdf5",
        qpos=np.zeros((6, 4), dtype=np.float32),
        qvel=np.zeros((6, 4), dtype=np.float32),
        actions=np.zeros((6, 4), dtype=np.float32),
        metadata={"control_hz": 50},
    )

    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    for step in range(6):
        _write_snapshot(
            snapshots / f"depth_step_{step:06d}.json",
            center_depth=0.5 + 0.1 * step,
        )
    snapshot_map = tmp_path / "graph_attach_sequence.yaml"
    snapshot_map.write_text(
        "\n".join(
            [
                "defaults:",
                "  snapshot_root: snapshots",
                "episodes:",
                "  - episode_index: 0",
                "    snapshots:",
                *[
                    line
                    for step in range(6)
                    for line in (
                        f"      - step_id: {step}",
                        f"        snapshot: depth_step_{step:06d}.json",
                    )
                ],
                "",
            ]
        )
    )
    output_dir = tmp_path / "teleop_graph"

    subprocess.run(
        [
            sys.executable,
            "-m",
            "testbed.cli.build_graph_dataset",
            "--teleop-dir",
            str(teleop_dir),
            "--snapshot-map",
            str(snapshot_map),
            "--output-dir",
            str(output_dir),
            "--max-nodes",
            "5",
            "--max-edges",
            "10",
            "--graph-rate-hz",
            "25",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    graph = read_episode(
        output_dir / "episode_000000.hdf5",
        load_images=False,
    )["observation_graph"]
    assert graph is not None
    np.testing.assert_array_equal(
        graph["source_step_id"],
        np.asarray([0, 0, 2, 2, 4, 4], dtype=np.int64),
    )


def test_build_graph_dataset_accepts_unpadded_episode_filename(tmp_path: Path) -> None:
    teleop_dir = tmp_path / "teleop"
    teleop_dir.mkdir()
    write_episode(
        teleop_dir / "episode_4.hdf5",
        qpos=np.zeros((4, 4), dtype=np.float32),
        qvel=np.zeros((4, 4), dtype=np.float32),
        actions=np.zeros((4, 4), dtype=np.float32),
        metadata={"control_hz": 50},
    )

    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    _write_snapshot(snapshots / "depth_step_000000.json")
    snapshot_map = tmp_path / "graph_attach_sequence.yaml"
    snapshot_map.write_text(
        "\n".join(
            [
                "defaults:",
                "  snapshot_root: snapshots",
                "episodes:",
                "  - episode_index: 4",
                "    snapshots:",
                "      - step_id: 0",
                "        snapshot: depth_step_000000.json",
                "",
            ]
        )
    )
    output_dir = tmp_path / "teleop_graph"

    subprocess.run(
        [
            sys.executable,
            "-m",
            "testbed.cli.build_graph_dataset",
            "--teleop-dir",
            str(teleop_dir),
            "--snapshot-map",
            str(snapshot_map),
            "--output-dir",
            str(output_dir),
            "--max-nodes",
            "5",
            "--max-edges",
            "10",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert (output_dir / "episode_4.hdf5").exists()
    graph = read_episode(output_dir / "episode_4.hdf5", load_images=False)[
        "observation_graph"
    ]
    assert graph is not None


def test_build_graph_dataset_aligns_snapshot_sequence_by_timestamp(tmp_path: Path) -> None:
    teleop_dir = tmp_path / "teleop"
    teleop_dir.mkdir()
    write_episode(
        teleop_dir / "episode_000000.hdf5",
        qpos=np.zeros((5, 4), dtype=np.float32),
        qvel=np.zeros((5, 4), dtype=np.float32),
        actions=np.zeros((5, 4), dtype=np.float32),
        metadata={"control_hz": 50},
        step_ns=np.asarray([1000, 2000, 3000, 4000, 5000], dtype=np.int64),
    )

    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    _write_snapshot(snapshots / "depth_time_000000.json", center_depth=0.5)
    _write_snapshot(snapshots / "depth_time_000010.json", center_depth=0.9)
    snapshot_map = tmp_path / "graph_attach_time.yaml"
    snapshot_map.write_text(
        "\n".join(
            [
                "defaults:",
                "  snapshot_root: snapshots",
                "episodes:",
                "  - episode_index: 0",
                "    snapshots:",
                "      - step_id: 0",
                "        timestamp_ns: 1000",
                "        snapshot: depth_time_000000.json",
                "      - step_id: 10",
                "        timestamp_ns: 3500",
                "        snapshot: depth_time_000010.json",
                "",
            ]
        )
    )
    output_dir = tmp_path / "teleop_graph"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "testbed.cli.build_graph_dataset",
            "--teleop-dir",
            str(teleop_dir),
            "--snapshot-map",
            str(snapshot_map),
            "--output-dir",
            str(output_dir),
            "--max-nodes",
            "5",
            "--max-edges",
            "10",
            "--align-domain",
            "time",
            "--align-mode",
            "previous",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    graph = read_episode(
        output_dir / "episode_000000.hdf5",
        load_images=False,
    )["observation_graph"]
    assert graph is not None
    np.testing.assert_array_equal(
        graph["source_step_id"],
        np.asarray([0, 0, 0, 10, 10], dtype=np.int64),
    )
    np.testing.assert_array_equal(
        graph["source_time_ns"],
        np.asarray([1000, 1000, 1000, 3500, 3500], dtype=np.int64),
    )
    np.testing.assert_array_equal(
        graph["alignment_delta_ns"],
        np.asarray([0, 1000, 2000, 500, 1500], dtype=np.int64),
    )
    np.testing.assert_array_equal(
        graph["is_fresh"],
        np.asarray([1, 0, 0, 1, 0], dtype=np.uint8),
    )

    lines = [json.loads(line) for line in completed.stdout.splitlines()]
    assert lines[0]["align_domain"] == "time"


def _make_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    teleop_dir = tmp_path / "teleop"
    teleop_dir.mkdir()
    write_episode(
        teleop_dir / "episode_000000.hdf5",
        qpos=np.zeros((4, 4), dtype=np.float32),
        qvel=np.ones((4, 4), dtype=np.float32),
        actions=np.full((4, 4), 0.25, dtype=np.float32),
        images={"fpv": np.zeros((4, 2, 2, 3), dtype=np.uint8)},
        rewards=np.arange(4, dtype=np.float32),
        metadata={"operator_id": "tester", "session_id": "graph-smoke"},
    )

    snapshots = tmp_path / "snapshots"
    snapshots.mkdir()
    _write_snapshot(snapshots / "depth_camera_fixture.json")
    snapshot_map = tmp_path / "graph_attach.yaml"
    snapshot_map.write_text(
        "\n".join(
            [
                "defaults:",
                "  snapshot_root: snapshots",
                "episodes:",
                "  - episode_index: 0",
                "    snapshot: depth_camera_fixture.json",
                "",
            ]
        )
    )

    return teleop_dir, snapshot_map, tmp_path / "teleop_graph"


def _write_snapshot(path: Path, *, center_depth: float = 0.5) -> None:
    depth = np.asarray(
        [
            [1.0, 1.0, 1.0],
            [1.0, center_depth, 1.0],
            [1.0, 1.0, 1.0],
        ],
        dtype=np.float32,
    )
    path.write_text(
        json.dumps(
            {
                "schema_version": "depth_camera_snapshot_v0",
                "metadata": {
                    "width": 3,
                    "height": 3,
                    "near_m": 0.1,
                    "far_m": 10.0,
                    "fx_px": 2.0,
                    "fy_px": 2.0,
                    "cx_px": 1.0,
                    "cy_px": 1.0,
                    "depth_semantics": "rendered_camera_eye_depth_m",
                },
                "depth_m": depth.reshape(-1).tolist(),
            }
        )
    )
