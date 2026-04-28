"""Image masking helpers for visual ACT inputs."""

from __future__ import annotations

from typing import Any

import numpy as np


def apply_image_mask(
    image: np.ndarray,
    *,
    camera_name: str,
    mask_config: dict[str, Any] | None,
    mask: np.ndarray | None = None,
) -> np.ndarray:
    """Apply a configured binary mask to an RGB image.

    The output keeps the same channel count as the input. This lets us feed a
    masked RGB view into the existing ACT ResNet backbone without changing the
    model architecture or invalidating old checkpoints.
    """

    if not _masking_enabled(mask_config):
        return image
    spec = _camera_spec(mask_config, camera_name)
    if spec is None:
        return image

    arr = np.asarray(image)
    if arr.ndim != 3:
        raise ValueError(
            f"image mask expects rank-3 RGB input for camera {camera_name!r}, "
            f"got shape {arr.shape}."
        )
    channel_first = _is_channel_first(arr)
    height, width = _spatial_shape(arr, channel_first=channel_first)
    mask_arr = _resolve_mask(
        height=height,
        width=width,
        spec=spec,
        camera_name=camera_name,
        mask=mask,
    )
    if bool(spec.get("invert", mask_config.get("invert", False))):
        mask_arr = 1.0 - mask_arr

    mode = str(spec.get("mode", mask_config.get("mode", "multiply"))).lower()
    outside_value = float(spec.get("outside_value", mask_config.get("outside_value", 0.0)))
    work = arr.astype(np.float32, copy=True)
    broadcast_mask = mask_arr[None, :, :] if channel_first else mask_arr[:, :, None]

    if mode == "multiply":
        work = work * broadcast_mask + outside_value * (1.0 - broadcast_mask)
    else:
        raise ValueError(
            f"Unsupported image mask mode {mode!r}. Supported modes: multiply."
        )

    if np.issubdtype(arr.dtype, np.integer):
        info = np.iinfo(arr.dtype)
        work = np.clip(np.rint(work), info.min, info.max).astype(arr.dtype)
    else:
        work = work.astype(arr.dtype, copy=False)
    return work


def mask_dataset_path(
    *,
    camera_name: str,
    mask_config: dict[str, Any] | None,
) -> str | None:
    """Return optional HDF5 mask dataset path for a camera."""

    if not _masking_enabled(mask_config):
        return None
    spec = _camera_spec(mask_config, camera_name)
    if spec is None:
        return None
    value = spec.get("mask_dataset", spec.get("dataset_path"))
    if value is None:
        return None
    path = str(value)
    if "{camera}" in path:
        path = path.format(camera=camera_name)
    return path


def require_mask_dataset(
    *,
    camera_name: str,
    mask_config: dict[str, Any] | None,
) -> bool:
    if not _masking_enabled(mask_config):
        return False
    spec = _camera_spec(mask_config, camera_name)
    if spec is None:
        return False
    return bool(spec.get("require_mask_dataset", False))


def _masking_enabled(mask_config: dict[str, Any] | None) -> bool:
    return bool(mask_config) and bool(mask_config.get("enabled", True))


def _camera_spec(mask_config: dict[str, Any] | None, camera_name: str) -> dict[str, Any] | None:
    if mask_config is None:
        return None
    cameras = mask_config.get("cameras")
    if isinstance(cameras, dict):
        spec = cameras.get(camera_name)
        if spec is None:
            return None
        if spec is True:
            return {}
        if not isinstance(spec, dict):
            raise ValueError(
                f"image_mask.cameras[{camera_name!r}] must be a mapping or true."
            )
        return spec
    return mask_config


def _resolve_mask(
    *,
    height: int,
    width: int,
    spec: dict[str, Any],
    camera_name: str,
    mask: np.ndarray | None,
) -> np.ndarray:
    if mask is not None:
        return _normalize_mask(mask, height=height, width=width, camera_name=camera_name)
    if "rect_xyxy_norm" in spec:
        return _rect_mask_from_norm(spec["rect_xyxy_norm"], height=height, width=width)
    if "rect_xyxy_px" in spec:
        return _rect_mask_from_px(spec["rect_xyxy_px"], height=height, width=width)
    raise ValueError(
        f"image_mask for camera {camera_name!r} needs either mask_dataset, "
        "rect_xyxy_norm, or rect_xyxy_px."
    )


def _normalize_mask(
    mask: np.ndarray,
    *,
    height: int,
    width: int,
    camera_name: str,
) -> np.ndarray:
    arr = np.asarray(mask)
    if arr.ndim == 3 and arr.shape[-1] == 1:
        arr = arr[..., 0]
    elif arr.ndim == 3 and arr.shape[0] == 1:
        arr = arr[0]
    if arr.shape != (height, width):
        raise ValueError(
            f"Mask for camera {camera_name!r} has shape {arr.shape}, expected "
            f"({height}, {width})."
        )
    arr = arr.astype(np.float32)
    if arr.max(initial=0.0) > 1.0:
        arr = arr / 255.0
    return (arr > 0.5).astype(np.float32)


def _rect_mask_from_norm(values: Any, *, height: int, width: int) -> np.ndarray:
    x0, y0, x1, y1 = _parse_rect(values)
    return _rect_mask_from_px(
        [
            int(round(x0 * width)),
            int(round(y0 * height)),
            int(round(x1 * width)),
            int(round(y1 * height)),
        ],
        height=height,
        width=width,
    )


def _rect_mask_from_px(values: Any, *, height: int, width: int) -> np.ndarray:
    x0, y0, x1, y1 = _parse_rect(values)
    x0_i = int(np.clip(np.floor(x0), 0, width))
    y0_i = int(np.clip(np.floor(y0), 0, height))
    x1_i = int(np.clip(np.ceil(x1), 0, width))
    y1_i = int(np.clip(np.ceil(y1), 0, height))
    if x1_i <= x0_i or y1_i <= y0_i:
        raise ValueError(
            "image mask rectangle must have positive area after clipping; "
            f"got {[x0, y0, x1, y1]} for image {width}x{height}."
        )
    mask = np.zeros((height, width), dtype=np.float32)
    mask[y0_i:y1_i, x0_i:x1_i] = 1.0
    return mask


def _parse_rect(values: Any) -> tuple[float, float, float, float]:
    arr = np.asarray(values, dtype=np.float32).reshape(-1)
    if arr.shape[0] != 4:
        raise ValueError(f"image mask rectangle must contain 4 values, got {values!r}.")
    return float(arr[0]), float(arr[1]), float(arr[2]), float(arr[3])


def _is_channel_first(image: np.ndarray) -> bool:
    return image.shape[0] in (1, 3) and image.shape[-1] not in (1, 3)


def _spatial_shape(image: np.ndarray, *, channel_first: bool) -> tuple[int, int]:
    if channel_first:
        return int(image.shape[1]), int(image.shape[2])
    return int(image.shape[0]), int(image.shape[1])
