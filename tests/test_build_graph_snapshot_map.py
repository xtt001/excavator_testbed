import json
import subprocess
import sys
from pathlib import Path

import yaml


def test_build_graph_snapshot_map_scans_sequence_metadata(tmp_path: Path) -> None:
    root = tmp_path / "DepthCameraSnapshots"
    root.mkdir()
    _write_snapshot(
        root / "depth_camera_graph_smoke_001_ep000000_seq000001_step000005_frame100.json",
        session_id="graph_smoke_001",
        episode_index=0,
        sequence_index=1,
        step_id=5,
    )
    _write_snapshot(
        root / "depth_camera_graph_smoke_001_ep000000_seq000000_step000000_frame090.json",
        session_id="graph_smoke_001",
        episode_index=0,
        sequence_index=0,
        step_id=0,
    )
    _write_snapshot(
        root / "depth_camera_other_ep000000_seq000000_step000000_frame001.json",
        session_id="other",
        episode_index=0,
        sequence_index=0,
        step_id=0,
    )

    output = tmp_path / "graph_attach_graph_smoke_001.yaml"
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "testbed.cli.build_graph_snapshot_map",
            "--snapshot-root",
            str(root),
            "--session-id",
            "graph_smoke_001",
            "--output",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(completed.stdout)["episode_count"] == 1
    payload = yaml.safe_load(output.read_text())
    assert payload["defaults"]["snapshot_root"] == str(root.resolve())
    assert payload["episodes"] == [
        {
            "episode_index": 0,
            "snapshots": [
                {
                    "step_id": 0,
                    "snapshot": "depth_camera_graph_smoke_001_ep000000_seq000000_step000000_frame090.json",
                },
                {
                    "step_id": 5,
                    "snapshot": "depth_camera_graph_smoke_001_ep000000_seq000001_step000005_frame100.json",
                },
            ],
        }
    ]


def test_build_graph_snapshot_map_falls_back_to_filename(tmp_path: Path) -> None:
    root = tmp_path / "DepthCameraSnapshots"
    root.mkdir()
    _write_snapshot(
        root / "depth_camera_graph_smoke_001_ep000002_seq000003_step000015_frame100.json",
        include_sequence_metadata=False,
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "testbed.cli.build_graph_snapshot_map",
            "--snapshot-root",
            str(root),
            "--session-id",
            "graph_smoke_001",
            "--output",
            str(tmp_path / "graph_attach.yaml"),
            "--dry-run",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = yaml.safe_load(completed.stdout)
    assert payload["episodes"][0]["episode_index"] == 2
    assert payload["episodes"][0]["snapshots"][0]["step_id"] == 15


def test_build_graph_snapshot_map_writes_timestamp_ns_from_metadata(tmp_path: Path) -> None:
    root = tmp_path / "DepthCameraSnapshots"
    root.mkdir()
    _write_snapshot(
        root / "depth_camera_graph_smoke_001_ep000000_seq000000_step000000_frame001.json",
        wall_time_utc="2026-06-02T03:40:47.4115210+00:00",
    )
    _write_snapshot(
        root / "depth_camera_graph_smoke_001_ep000000_seq000001_step000005_frame002.json",
        sequence_index=1,
        step_id=5,
        wall_time_unix_ns=1_779_000_000_000_000_123,
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "testbed.cli.build_graph_snapshot_map",
            "--snapshot-root",
            str(root),
            "--session-id",
            "graph_smoke_001",
            "--output",
            str(tmp_path / "graph_attach.yaml"),
            "--dry-run",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = yaml.safe_load(completed.stdout)
    snapshots = payload["episodes"][0]["snapshots"]
    assert snapshots[0]["timestamp_ns"] == 1_780_371_647_411_521_024
    assert snapshots[1]["timestamp_ns"] == 1_779_000_000_000_000_123


def test_build_graph_snapshot_map_reports_missing_matches(tmp_path: Path) -> None:
    root = tmp_path / "DepthCameraSnapshots"
    root.mkdir()

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "testbed.cli.build_graph_snapshot_map",
            "--snapshot-root",
            str(root),
            "--output",
            str(tmp_path / "graph_attach.yaml"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "no matching depth snapshot JSON files found" in completed.stderr


def test_build_graph_snapshot_map_reports_duplicate_step_by_default(tmp_path: Path) -> None:
    root = tmp_path / "DepthCameraSnapshots"
    root.mkdir()
    _write_snapshot(
        root / "depth_camera_graph_smoke_001_ep000000_seq000000_step000000_frame001.json",
        wall_time_unix_ns=100,
    )
    _write_snapshot(
        root / "depth_camera_graph_smoke_001_ep000000_seq000001_step000000_frame002.json",
        sequence_index=1,
        wall_time_unix_ns=200,
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "testbed.cli.build_graph_snapshot_map",
            "--snapshot-root",
            str(root),
            "--session-id",
            "graph_smoke_001",
            "--output",
            str(tmp_path / "graph_attach.yaml"),
            "--dry-run",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "duplicate step_id 0 for episode 0" in completed.stderr


def test_build_graph_snapshot_map_can_keep_latest_duplicate_step(tmp_path: Path) -> None:
    root = tmp_path / "DepthCameraSnapshots"
    root.mkdir()
    _write_snapshot(
        root / "depth_camera_graph_smoke_001_ep000000_seq000000_step000000_frame001.json",
        wall_time_unix_ns=100,
    )
    _write_snapshot(
        root / "depth_camera_graph_smoke_001_ep000000_seq000001_step000000_frame002.json",
        sequence_index=1,
        wall_time_unix_ns=200,
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "testbed.cli.build_graph_snapshot_map",
            "--snapshot-root",
            str(root),
            "--session-id",
            "graph_smoke_001",
            "--output",
            str(tmp_path / "graph_attach.yaml"),
            "--duplicate-policy",
            "latest",
            "--dry-run",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    payload = yaml.safe_load(completed.stdout)
    snapshots = payload["episodes"][0]["snapshots"]
    assert len(snapshots) == 1
    assert snapshots[0]["timestamp_ns"] == 200
    assert snapshots[0]["snapshot"].endswith("frame002.json")


def _write_snapshot(
    path: Path,
    *,
    session_id: str = "graph_smoke_001",
    episode_index: int = 0,
    sequence_index: int = 0,
    step_id: int = 0,
    include_sequence_metadata: bool = True,
    wall_time_utc: str | None = None,
    wall_time_unix_ns: int | None = None,
) -> None:
    metadata = {
        "width": 1,
        "height": 1,
        "near_m": 0.1,
        "far_m": 10.0,
        "depth_semantics": "rendered_camera_eye_depth_m",
    }
    if include_sequence_metadata:
        metadata.update(
            {
                "session_id": session_id,
                "episode_index": episode_index,
                "sequence_index": sequence_index,
                "step_id": step_id,
            }
        )
    if wall_time_utc is not None:
        metadata["wall_time_utc"] = wall_time_utc
    if wall_time_unix_ns is not None:
        metadata["wall_time_unix_ns"] = wall_time_unix_ns
    path.write_text(
        json.dumps(
            {
                "schema_version": "depth_camera_snapshot_v0",
                "metadata": metadata,
                "depth_m": [1.0],
            }
        )
    )
