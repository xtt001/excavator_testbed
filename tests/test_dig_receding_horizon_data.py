from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pytest

from testbed.eval.dig_receding_horizon_data import read_dispatch_observation

CAMERAS = ("stick_up", "stick_down", "eye_left", "eye_right")


def _episode(path: Path) -> None:
    with h5py.File(path, "w") as handle:
        metadata = handle.create_group("metadata")
        metadata.attrs["camera_names"] = ",".join(CAMERAS)
        observations = handle.create_group("observations")
        observations.create_dataset(
            "qpos", data=np.asarray([[0.1, 0.2, 0.3, 0.4]], dtype=np.float32)
        )
        observations.create_dataset(
            "qvel", data=np.asarray([[0.0, 0.1, 0.2, 0.3]], dtype=np.float32)
        )
        images = observations.create_group("images")
        for index, camera in enumerate(CAMERAS):
            images.create_dataset(
                camera,
                data=np.full((1, 2, 3, 3), index, dtype=np.uint8),
            )


def test_observation_reader_locks_state_and_camera_bytes(tmp_path: Path) -> None:
    path = tmp_path / "episode_1.hdf5"
    _episode(path)

    with h5py.File(path, "r") as handle:
        observation, lineage = read_dispatch_observation(
            handle,
            frame_index=0,
            camera_order=CAMERAS,
        )

    assert tuple(observation) == (
        "qpos",
        "qvel",
        "image_stick_up",
        "image_stick_down",
        "image_eye_left",
        "image_eye_right",
    )
    assert len(lineage["observation_sha256"]) == 64
    assert set(lineage["camera_frame_sha256"]) == set(CAMERAS)
    assert lineage["frame_index"] == 0


def test_observation_reader_rejects_camera_order_drift(tmp_path: Path) -> None:
    path = tmp_path / "episode_2.hdf5"
    _episode(path)

    with (
        h5py.File(path, "r") as handle,
        pytest.raises(ValueError, match="camera order"),
    ):
        read_dispatch_observation(
            handle,
            frame_index=0,
            camera_order=tuple(reversed(CAMERAS)),
        )
