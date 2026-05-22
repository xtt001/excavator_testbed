from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import h5py
import numpy as np

from testbed.data.hdf5_io import write_episode


def _write_minimal_episode(path: Path, *, v2: dict | None = None, scenario_id: str = "s0_truck") -> None:
    steps = 8
    write_episode(
        path,
        qpos=np.zeros((steps, 4), dtype=np.float32),
        qvel=np.zeros((steps, 4), dtype=np.float32),
        actions=np.zeros((steps, 4), dtype=np.float32),
        env_state=np.zeros((steps, 64), dtype=np.float32),
        metadata={"scenario_id": scenario_id, "qualified_dig_start_mode": "progress"},
        v2=v2,
    )


def test_label_v2_1_can_transfer_existing_v2_labels_to_replayed_vds(tmp_path: Path) -> None:
    replay_dir = tmp_path / "replay"
    label_dir = tmp_path / "labels"
    output_dir = tmp_path / "relabeled_vds"
    replay_dir.mkdir()
    label_dir.mkdir()

    v2_payload = {
        "step": {
            "cycle_id": np.asarray([-1, 0, 0, 0, 0, 1, 1, 1], dtype=np.int32),
            "qualified_dig_start_mask": np.asarray([0, 1, 0, 0, 0, 1, 0, 0], dtype=np.uint8),
        },
        "cycle": {
            "cycle_id": np.asarray([0, 1], dtype=np.int32),
            "start_step": np.asarray([1, 5], dtype=np.int32),
            "dump_end_step": np.asarray([3, 7], dtype=np.int32),
            "cycle_success": np.asarray([1, 1], dtype=np.uint8),
        },
    }
    _write_minimal_episode(replay_dir / "episode_0.hdf5")
    _write_minimal_episode(label_dir / "episode_0.hdf5", v2=v2_payload)

    subprocess.run(
        [
            sys.executable,
            "-m",
            "testbed.cli.label_v2_1",
            "--dataset-dir",
            str(replay_dir),
            "--output-dir",
            str(output_dir),
            "--storage-mode",
            "vds",
            "--v2-label-source-dir",
            str(label_dir),
        ],
        check=True,
        cwd=Path(__file__).resolve().parents[1],
    )

    with h5py.File(output_dir / "episode_0.hdf5", "r") as handle:
        assert handle["observations/qpos"].is_virtual
        assert handle["metadata"].attrs["label_storage_mode"] == "transfer"
        assert "v2_label_source_path" in handle["metadata"].attrs
        np.testing.assert_array_equal(
            handle["v2/cycle/start_step"][()],
            np.asarray([1, 5], dtype=np.int32),
        )
        np.testing.assert_array_equal(
            handle["v2/step/qualified_dig_start_mask"][()],
            np.asarray([0, 1, 0, 0, 0, 1, 0, 0], dtype=np.uint8),
        )
