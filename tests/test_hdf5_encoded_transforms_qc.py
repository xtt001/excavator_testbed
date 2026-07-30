from __future__ import annotations

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


def _jpeg(value: int, *, shape: tuple[int, int] = (6, 8)) -> np.ndarray:
    rgb = np.full((*shape, 3), value, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    assert ok
    return encoded.reshape(-1)


def _write_encoded_episode(
    path: Path,
    *,
    camera_names: list[str] = CAMERAS,
    shapes: dict[str, tuple[int, int]] | None = None,
) -> dict[str, list[bytes]]:
    encoded = {
        camera: [
            _jpeg(20 + camera_index * 30 + step, shape=(shapes or {}).get(camera, (6, 8)))
            for step in range(3)
        ]
        for camera_index, camera in enumerate(camera_names)
    }
    write_episode(
        path,
        qpos=np.zeros((3, 4), dtype=np.float32),
        qvel=np.zeros((3, 4), dtype=np.float32),
        actions=np.zeros((3, 4), dtype=np.float32),
        encoded_images=encoded,
        metadata={"camera_names": ",".join(camera_names)},
    )
    return {
        camera: [frame.tobytes() for frame in frames]
        for camera, frames in encoded.items()
    }


def test_encoded_vds_materialize_and_virtualize_preserve_jpeg_bytes(tmp_path: Path) -> None:
    source = tmp_path / "raw" / "episode_0.hdf5"
    wrapper = tmp_path / "vds" / "episode_0.hdf5"
    materialized = tmp_path / "copy" / "episode_0.hdf5"
    archive = tmp_path / "archive" / "episode_0.hdf5"
    original = _write_encoded_episode(source)

    write_vds_episode(wrapper, source_path=source, crop=slice(1, 3))
    with h5py.File(wrapper, "r") as handle:
        for camera in CAMERAS:
            dataset = handle[f"observations/encoded_images/{camera}"]
            assert dataset.is_virtual
            assert dataset.attrs["encoding"] == "jpeg"
            assert [bytes(frame) for frame in dataset] == original[camera][1:3]

    materialize_episode(wrapper, materialized)
    with h5py.File(materialized, "r") as handle:
        for camera in CAMERAS:
            dataset = handle[f"observations/encoded_images/{camera}"]
            assert not dataset.is_virtual
            assert dataset.attrs["encoding"] == "jpeg"
            assert [bytes(frame) for frame in dataset] == original[camera][1:3]

    virtualize_episode_images(materialized, archive)
    with h5py.File(archive, "r") as handle:
        for camera in CAMERAS:
            dataset = handle[f"observations/encoded_images/{camera}"]
            assert dataset.is_virtual
            assert dataset.attrs["encoding"] == "jpeg"
            assert [bytes(frame) for frame in dataset] == original[camera][1:3]


def test_qc_accepts_valid_encoded_four_camera_episode(tmp_path: Path) -> None:
    _write_encoded_episode(tmp_path / "episode_0.hdf5")

    result = run_dataset_qc(
        tmp_path,
        expected_camera_names=CAMERAS,
        short_episode_threshold=0,
    )

    warnings = result["summary"]["warnings"]
    assert warnings["camera_contract_error_ids"] == []
    assert warnings["missing_image_ids"] == []


def test_qc_reports_corrupt_missing_order_and_dimension_errors(tmp_path: Path) -> None:
    corrupt = tmp_path / "episode_0.hdf5"
    _write_encoded_episode(corrupt)
    with h5py.File(corrupt, "r+") as handle:
        handle["observations/encoded_images/stick_up"][1] = np.array([1, 2, 3], dtype=np.uint8)

    missing = tmp_path / "episode_1.hdf5"
    _write_encoded_episode(missing, camera_names=CAMERAS[:-1])

    wrong_order = tmp_path / "episode_2.hdf5"
    _write_encoded_episode(wrong_order, camera_names=list(reversed(CAMERAS)))

    mismatched = tmp_path / "episode_3.hdf5"
    _write_encoded_episode(mismatched, shapes={"eye_right": (5, 8)})

    result = run_dataset_qc(
        tmp_path,
        expected_camera_names=CAMERAS,
        short_episode_threshold=0,
    )
    errors = result["summary"]["warnings"]["camera_contract_errors"]

    assert any("jpeg_decode_failed" in issue for issue in errors["episode_0"])
    assert any("expected_camera_set_mismatch" in issue for issue in errors["episode_1"])
    assert any("camera_order_mismatch" in issue for issue in errors["episode_2"])
    assert any("camera_dimensions_inconsistent" in issue for issue in errors["episode_3"])


def test_qc_keeps_legacy_single_raw_camera_compatible(tmp_path: Path) -> None:
    write_episode(
        tmp_path / "episode_0.hdf5",
        qpos=np.zeros((2, 4), dtype=np.float32),
        qvel=np.zeros((2, 4), dtype=np.float32),
        actions=np.zeros((2, 4), dtype=np.float32),
        images={"fpv": np.zeros((2, 4, 5, 3), dtype=np.uint8)},
        metadata={"camera_names": "fpv"},
    )

    result = run_dataset_qc(tmp_path, short_episode_threshold=0)
    assert result["summary"]["warnings"]["camera_contract_error_ids"] == []
