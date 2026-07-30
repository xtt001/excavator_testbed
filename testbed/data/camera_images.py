"""Camera image layout, ordering, and JPEG decoding for episode HDF5 files."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np

from testbed.data.schema import ATTR_CAMERA_NAMES, GRP_ENCODED_IMAGES

JPEG_ENCODING = "jpeg"


def camera_names_from_metadata(metadata: dict[str, Any] | None) -> list[str]:
    raw = (metadata or {}).get(ATTR_CAMERA_NAMES)
    if raw is None:
        return []
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="strict")
    if isinstance(raw, str):
        names = [item.strip() for item in raw.split(",") if item.strip()]
    elif isinstance(raw, (list, tuple, np.ndarray)):
        names = [
            str(_decode_text(item)).strip()
            for item in raw
            if str(_decode_text(item)).strip()
        ]
    else:
        names = [str(raw).strip()] if str(raw).strip() else []
    if len(names) != len(set(names)):
        raise ValueError(f"camera_names contains duplicates: {names!r}")
    return names


def ordered_camera_names(
    available: Iterable[str], metadata: dict[str, Any] | None = None
) -> list[str]:
    available_names = [str(name) for name in available]
    configured = camera_names_from_metadata(metadata)
    if not configured:
        return available_names
    if set(configured) != set(available_names):
        missing = [name for name in configured if name not in available_names]
        unexpected = [name for name in available_names if name not in configured]
        raise ValueError(
            "camera_names does not match stored camera datasets: "
            f"missing={missing}, unexpected={unexpected}"
        )
    return configured


def validate_exclusive_camera_layout(
    raw_names: Iterable[str], encoded_names: Iterable[str]
) -> list[str]:
    raw = [str(name) for name in raw_names]
    encoded = [str(name) for name in encoded_names]
    if raw and encoded:
        raise ValueError(
            "mixed raw and encoded camera layouts are not supported in one episode: "
            f"raw={raw}, encoded={encoded}"
        )
    return raw or encoded


def validate_camera_step(
    *,
    requested_names: Iterable[str] | None,
    raw_images: dict[str, Any],
    encoded_images: dict[str, Any],
    previous_mode: str | None,
) -> tuple[list[str], str | None]:
    names = list(requested_names or raw_images.keys() or encoded_images.keys())
    missing = [
        name
        for name in names
        if name not in raw_images and name not in encoded_images
    ]
    duplicate = [name for name in names if name in raw_images and name in encoded_images]
    if missing:
        raise KeyError(f"Missing requested camera frames: {missing}")
    if duplicate:
        raise ValueError(f"Cameras supplied as both raw and encoded frames: {duplicate}")
    modes = {"raw" if name in raw_images else "encoded" for name in names}
    if len(modes) > 1:
        raise ValueError(f"Mixed raw and encoded cameras in one timestep: {names}")
    mode = next(iter(modes), None)
    if previous_mode is not None and mode != previous_mode:
        raise ValueError(
            f"Camera storage mode changed within episode: {previous_mode} -> {mode}"
        )
    return names, mode


def encoded_frame_to_uint8(frame: Any) -> np.ndarray:
    if isinstance(frame, dict):
        encoding = str(frame.get("encoding", JPEG_ENCODING)).lower()
        if encoding not in {JPEG_ENCODING, "mjpeg"}:
            raise ValueError(f"unsupported encoded camera format {encoding!r}")
        frame = frame.get("data", frame.get("bytes", b""))
    if isinstance(frame, (bytes, bytearray, memoryview)):
        return np.frombuffer(bytes(frame), dtype=np.uint8).copy()
    return np.asarray(frame, dtype=np.uint8).reshape(-1).copy()


def decode_jpeg_rgb(frame: Any) -> np.ndarray:
    import cv2

    encoded = encoded_frame_to_uint8(frame)
    bgr = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if bgr is None:
        raise ValueError("failed to decode JPEG camera frame")
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)


def observation_camera_rgb(observation: dict[str, Any], camera_name: str) -> np.ndarray:
    """Return one named observation camera as RGB HWC without re-encoding it."""
    raw_images = observation.get("images", {}) or {}
    encoded_images = observation.get("encoded_images", {}) or {}
    has_raw = camera_name in raw_images and raw_images[camera_name] is not None
    has_encoded = camera_name in encoded_images and encoded_images[camera_name] is not None
    if has_raw and has_encoded:
        raise ValueError(
            f"camera {camera_name!r} is present as both raw and encoded observation data"
        )
    if has_raw:
        image = np.asarray(raw_images[camera_name], dtype=np.uint8)
        if image.ndim != 3 or image.shape[-1] != 3:
            raise ValueError(
                f"camera {camera_name!r} raw observation must be HWC RGB, got {image.shape}"
            )
        return image
    if has_encoded:
        return decode_jpeg_rgb(encoded_images[camera_name])
    raise KeyError(f"Camera {camera_name!r} is missing from observation.")


def read_camera_rgb(h5_file: Any, camera_name: str, timestep: int) -> np.ndarray:
    raw_path = f"observations/images/{camera_name}"
    encoded_path = f"{GRP_ENCODED_IMAGES}/{camera_name}"
    has_raw = raw_path in h5_file
    has_encoded = encoded_path in h5_file
    if has_raw and has_encoded:
        raise ValueError(f"camera {camera_name!r} is stored as both raw and encoded data")
    if has_raw:
        return np.asarray(h5_file[raw_path][timestep], dtype=np.uint8)
    if has_encoded:
        dataset = h5_file[encoded_path]
        encoding = _decode_text(dataset.attrs.get("encoding", ""))
        if str(encoding).lower() != JPEG_ENCODING:
            raise ValueError(
                f"camera {camera_name!r} has unsupported encoding {encoding!r}"
            )
        return decode_jpeg_rgb(dataset[timestep])
    raise KeyError(f"Camera {camera_name!r} not found as raw or encoded image data.")


def _decode_text(value: Any) -> Any:
    return value.decode("utf-8") if isinstance(value, (bytes, np.bytes_)) else value
