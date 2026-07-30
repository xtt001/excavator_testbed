from __future__ import annotations

import tempfile
from pathlib import Path

import cv2
import h5py
import numpy as np
import pytest

from testbed.data.dataset import EpisodicDataset
from testbed.data.hdf5_io import read_episode, write_episode
from testbed.data.recorder import EpisodeRecorder


CAMERAS = ["stick_up", "stick_down", "eye_left", "eye_right"]


def _jpeg(rgb: np.ndarray) -> np.ndarray:
    ok, encoded = cv2.imencode(
        ".jpg",
        cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
        [int(cv2.IMWRITE_JPEG_QUALITY), 95],
    )
    assert ok
    return encoded.reshape(-1)


def _encoded_frames() -> dict[str, list[np.ndarray]]:
    result = {}
    for camera_index, camera_name in enumerate(CAMERAS):
        frames = []
        for timestep in range(2):
            rgb = np.zeros((8, 10, 3), dtype=np.uint8)
            rgb[..., camera_index % 3] = 60 + 40 * camera_index + timestep
            frames.append(_jpeg(rgb))
        result[camera_name] = frames
    return result


def _episode_arrays() -> dict[str, np.ndarray]:
    return {
        "qpos": np.zeros((2, 4), dtype=np.float32),
        "qvel": np.zeros((2, 4), dtype=np.float32),
        "actions": np.zeros((2, 4), dtype=np.float32),
    }


def test_four_encoded_cameras_round_trip_as_decoded_rgb_in_metadata_order() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "episode_0.hdf5"
        encoded = _encoded_frames()
        original_bytes = {
            camera: [frame.tobytes() for frame in frames]
            for camera, frames in encoded.items()
        }
        write_episode(
            path,
            **_episode_arrays(),
            encoded_images=encoded,
            metadata={"camera_names": ",".join(CAMERAS), "image_format": "jpeg"},
        )

        with h5py.File(path, "r") as handle:
            assert "observations/images" not in handle
            assert set(handle["observations/encoded_images"].keys()) == set(CAMERAS)
            assert handle["metadata"].attrs["camera_names"] == ",".join(CAMERAS)
            for camera in CAMERAS:
                dataset = handle[f"observations/encoded_images/{camera}"]
                assert dataset.shape == (2,)
                assert dataset.attrs["encoding"] == "jpeg"
                assert bytes(dataset[0]) == original_bytes[camera][0]

        episode = read_episode(path)
        assert list(episode["images"]) == CAMERAS
        assert list(episode["encoded_images"]) == CAMERAS
        assert all(episode["images"][camera].shape == (2, 8, 10, 3) for camera in CAMERAS)

        metadata_only = read_episode(
            path,
            load_images=False,
            load_encoded_images=False,
        )
        assert metadata_only["images"] == {}
        assert metadata_only["encoded_images"] == {}


def test_recorder_preserves_already_encoded_frames_without_raw_duplicates() -> None:
    encoded = _encoded_frames()
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = EpisodeRecorder(tmpdir, 0, camera_names=CAMERAS)
        for timestep in range(2):
            recorder.record(
                {
                    "qpos": np.zeros(4, dtype=np.float32),
                    "qvel": np.zeros(4, dtype=np.float32),
                    "encoded_images": {
                        camera: {"encoding": "jpeg", "data": encoded[camera][timestep]}
                        for camera in CAMERAS
                    },
                },
                np.zeros(4, dtype=np.float32),
            )
        path = recorder.save()

        with h5py.File(path, "r") as handle:
            assert handle["metadata"].attrs["camera_names"] == ",".join(CAMERAS)
            assert handle["metadata"].attrs["image_format"] == "jpeg"
            assert "observations/images" not in handle
            for camera in CAMERAS:
                assert bytes(handle[f"observations/encoded_images/{camera}"][0]) == bytes(encoded[camera][0])


def test_act_dataset_decodes_four_cameras_in_configured_order() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "episode_0.hdf5"
        write_episode(
            path,
            **_episode_arrays(),
            encoded_images=_encoded_frames(),
            metadata={"camera_names": ",".join(CAMERAS)},
        )
        stats = {
            "action_mean": np.zeros(4, dtype=np.float32),
            "action_std": np.ones(4, dtype=np.float32),
            "proprio_mean": np.zeros(8, dtype=np.float32),
            "proprio_std": np.ones(8, dtype=np.float32),
        }
        dataset = EpisodicDataset(
            [0], tmpdir, list(reversed(CAMERAS)), stats, episode_len=2,
            low_dim_keys=["qpos", "qvel"],
        )
        images, _proprio, _actions, _is_pad = dataset[0]
        assert tuple(images.shape) == (4, 3, 8, 10)
        assert float(images[0].max()) > 0.5  # eye_right is first by caller order.


def test_legacy_dense_raw_rgb_remains_readable_and_train_compatible() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "episode_0.hdf5"
        raw = np.arange(2 * 4 * 5 * 3, dtype=np.uint8).reshape(2, 4, 5, 3)
        write_episode(path, **_episode_arrays(), images={"fpv": raw})
        episode = read_episode(path)
        np.testing.assert_array_equal(episode["images"]["fpv"], raw)
        assert episode["encoded_images"] == {}


def test_missing_or_mixed_camera_frames_fail_clearly() -> None:
    recorder = EpisodeRecorder(".", 0, camera_names=CAMERAS)
    with pytest.raises(KeyError, match="Missing requested camera frames"):
        recorder.record(
            {
                "qpos": np.zeros(4),
                "qvel": np.zeros(4),
                "encoded_images": {"stick_up": _encoded_frames()["stick_up"][0]},
            },
            np.zeros(4),
        )

    with tempfile.TemporaryDirectory() as tmpdir:
        with pytest.raises(ValueError, match="mixed raw and encoded"):
            write_episode(
                Path(tmpdir) / "episode_0.hdf5",
                **_episode_arrays(),
                images={"stick_up": np.zeros((2, 8, 10, 3), dtype=np.uint8)},
                encoded_images={"stick_down": _encoded_frames()["stick_down"]},
            )
