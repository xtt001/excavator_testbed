from __future__ import annotations

import tempfile
from pathlib import Path

import cv2
import h5py
import numpy as np

from testbed.data.hdf5_io import write_episode
from testbed.data.materialize import materialize_episode
from testbed.data.qc import run_dataset_qc
from testbed.data.vds import write_vds_episode
from testbed.data.virtualize_images import virtualize_episode_images

CAMERAS = ["stick_up", "stick_down", "eye_left", "eye_right"]


def _jpeg(value: int, shape: tuple[int, int] = (8, 10)) -> np.ndarray:
    rgb = np.full((*shape, 3), value, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    assert ok
    return encoded.reshape(-1)


def _encoded(length: int = 3) -> dict[str, list[np.ndarray]]:
    return {
        camera: [_jpeg(20 + camera_index * 30 + step) for step in range(length)]
        for camera_index, camera in enumerate(CAMERAS)
    }


def _write(path: Path, *, length: int = 3) -> dict[str, list[np.ndarray]]:
    encoded = _encoded(length)
    write_episode(
        path,
        qpos=np.zeros((length, 4), dtype=np.float32),
        qvel=np.zeros((length, 4), dtype=np.float32),
        actions=np.zeros((length, 4), dtype=np.float32),
        encoded_images=encoded,
        metadata={"camera_names": ",".join(CAMERAS), "image_format": "jpeg"},
    )
    return encoded


def _bytes(dataset: h5py.Dataset) -> list[bytes]:
    return [np.asarray(dataset[index], dtype=np.uint8).tobytes() for index in range(dataset.shape[0])]


def test_vlen_jpeg_vds_materialize_and_virtualize_preserve_exact_bytes() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        source = root / "raw" / "episode_0.hdf5"
        wrapper = root / "vds" / "episode_0.hdf5"
        materialized = root / "copy" / "episode_0.hdf5"
        archive = root / "archive" / "episode_0.hdf5"
        encoded = _write(source)
        write_vds_episode(
            wrapper,
            source_path=source,
            crop=slice(1, 3),
            metadata={"camera_names": ",".join(CAMERAS), "image_format": "jpeg"},
        )

        with h5py.File(wrapper, "r") as handle:
            for camera in CAMERAS:
                dataset = handle[f"observations/encoded_images/{camera}"]
                assert dataset.is_virtual
                assert dataset.attrs["encoding"] == "jpeg"
                assert _bytes(dataset) == [frame.tobytes() for frame in encoded[camera][1:3]]

        stats = materialize_episode(wrapper, materialized)
        assert stats.image_dataset_count == 4
        with h5py.File(materialized, "r") as handle:
            for camera in CAMERAS:
                dataset = handle[f"observations/encoded_images/{camera}"]
                assert not dataset.is_virtual
                assert _bytes(dataset) == [frame.tobytes() for frame in encoded[camera][1:3]]

        virtualized = virtualize_episode_images(materialized, archive)
        assert virtualized.image_dataset_count == 4
        with h5py.File(archive, "r") as handle:
            for camera in CAMERAS:
                dataset = handle[f"observations/encoded_images/{camera}"]
                assert dataset.is_virtual
                assert dataset.attrs["encoding"] == "jpeg"
                assert _bytes(dataset) == [frame.tobytes() for frame in encoded[camera][1:3]]


def test_qc_reports_four_camera_metrics_and_camera_specific_failures() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        _write(root / "episode_0.hdf5")
        corrupt = root / "episode_1.hdf5"
        _write(corrupt)
        with h5py.File(corrupt, "a") as handle:
            handle["observations/encoded_images/stick_down"][1] = np.arange(8, dtype=np.uint8)

        missing = root / "episode_2.hdf5"
        _write(missing)
        with h5py.File(missing, "a") as handle:
            del handle["observations/encoded_images/eye_right"]

        reordered = root / "episode_3.hdf5"
        _write(reordered)
        with h5py.File(reordered, "a") as handle:
            handle["metadata"].attrs["camera_names"] = ",".join(reversed(CAMERAS))

        short_stream = root / "episode_4.hdf5"
        _write(short_stream)
        with h5py.File(short_stream, "a") as handle:
            group = handle["observations/encoded_images"]
            original = [np.asarray(group["eye_left"][i], dtype=np.uint8) for i in range(2)]
            del group["eye_left"]
            dataset = group.create_dataset(
                "eye_left", (2,), dtype=h5py.vlen_dtype(np.dtype("uint8"))
            )
            dataset.attrs["encoding"] = "jpeg"
            for index, frame in enumerate(original):
                dataset[index] = frame

        result = run_dataset_qc(
            root,
            short_episode_threshold=1,
            expected_camera_names=CAMERAS,
        )
        warnings = result["summary"]["warnings"]
        assert "episode_0" not in warnings["camera_contract_error_ids"]
        assert set(warnings["camera_contract_error_ids"]) == {
            "episode_1", "episode_2", "episode_3", "episode_4"
        }
        errors = warnings["camera_contract_errors"]
        assert any("camera=stick_down:frame=1:jpeg_decode_failed" in item for item in errors["episode_1"])
        assert any("camera_set_mismatch" in item and "eye_right" in item for item in errors["episode_2"])
        assert any("camera_order_mismatch" in item for item in errors["episode_3"])
        assert any("camera=eye_left:length_mismatch" in item for item in errors["episode_4"])

        with open(result["episodes_csv_path"]) as csv_file:
            header = csv_file.readline()
        assert "camera_count" in header
        assert "camera_shapes" in header
        assert "camera_errors" in header
