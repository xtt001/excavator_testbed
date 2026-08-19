"""Shared ACT camera-input preprocessing without policy state.

The frozen ACT model consumes cameras in one configured order, as float32
``(camera, channel, height, width)`` tensors, then applies ImageNet
normalisation.  This module makes those stages inspectable for offline audits
without exposing an adapter's model, temporal cache, or private helpers.

The training dataset has one historical scaling edge case that is intentionally
represented explicitly: its HDF5 RGB path always divides channel-last images by
255, while the legacy runtime only divides when the channel-last maximum is
greater than one.  Keeping the modes separate preserves old checkpoints and
lets an audit prove equality for the source it actually replays.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import torch
import torchvision.transforms as transforms

from testbed.data.camera_images import observation_camera_rgb
from testbed.data.image_masks import apply_image_mask

ACT_IMAGE_VALUE_SCALING_RUNTIME_LEGACY = "runtime_legacy"
"""Historical inference scaling: divide HWC RGB only when max value is > 1."""

ACT_IMAGE_VALUE_SCALING_TRAINING_DATASET = "training_dataset"
"""Historical HDF5 dataset scaling: divide every HWC RGB image by 255."""

ACT_IMAGE_VALUE_SCALING_MODES = (
    ACT_IMAGE_VALUE_SCALING_RUNTIME_LEGACY,
    ACT_IMAGE_VALUE_SCALING_TRAINING_DATASET,
)

ACT_IMAGE_INPUT_LAYOUT_AUTO = "auto"
"""Historical runtime layout detection with channel-first precedence."""

ACT_IMAGE_INPUT_LAYOUT_HWC = "hwc"
"""Explicit channel-last layout used by the HDF5 ACT training dataset."""

ACT_IMAGE_INPUT_LAYOUT_MODES = (
    ACT_IMAGE_INPUT_LAYOUT_AUTO,
    ACT_IMAGE_INPUT_LAYOUT_HWC,
)

ACT_IMAGENET_MEAN = (0.485, 0.456, 0.406)
ACT_IMAGENET_STD = (0.229, 0.224, 0.225)

ImageValueScaling = Literal["runtime_legacy", "training_dataset"]
ImageInputLayout = Literal["auto", "hwc"]
ImageNormalizer = Callable[[torch.Tensor], torch.Tensor]


@dataclass(frozen=True)
class ACTImageTransformResult:
    """Camera inputs before and after ACT layout, mask, and scale transforms.

    ``raw_camera_images`` holds the selected RGB arrays before masking.  Its
    order exactly matches ``camera_names``.  ``transformed_images`` is float32
    ``(num_cameras, 3, height, width)`` and is the input to ImageNet
    normalisation.
    """

    camera_names: tuple[str, ...]
    raw_camera_images: tuple[np.ndarray, ...]
    transformed_images: np.ndarray
    value_scaling: ImageValueScaling
    input_layout: ImageInputLayout


@dataclass(frozen=True)
class ACTImagePreprocessingResult:
    """All inspectable ACT image stages for one observation.

    ``normalized_images`` is a batched tensor with shape
    ``(1, num_cameras, 3, height, width)`` on the requested device.  Offline
    callers can hash the camera names, raw arrays, transformed array, and this
    tensor (after moving it to CPU) to prove their model input is unchanged.
    """

    camera_names: tuple[str, ...]
    raw_camera_images: tuple[np.ndarray, ...]
    transformed_images: np.ndarray
    normalized_images: torch.Tensor
    value_scaling: ImageValueScaling
    input_layout: ImageInputLayout


def make_act_image_normalizer() -> transforms.Normalize:
    """Create the ImageNet normaliser used by ACT training and inference."""

    return transforms.Normalize(
        mean=list(ACT_IMAGENET_MEAN),
        std=list(ACT_IMAGENET_STD),
    )


def normalize_act_image_tensor(image: torch.Tensor) -> torch.Tensor:
    """Apply ACT's ImageNet normalisation to a camera tensor.

    The tensor may include any leading dimensions as long as its final three
    dimensions are ``(3, height, width)``.  This matches the legacy
    ``torchvision.transforms.Normalize`` path used by ``ACTAdapter``.
    """

    return make_act_image_normalizer()(image)


def transform_act_camera_images(
    *,
    camera_images: Mapping[str, Any],
    camera_names: Sequence[str],
    image_mask_config: Mapping[str, Any] | None = None,
    camera_masks: Mapping[str, np.ndarray | None] | None = None,
    method_name: str = "ACT image preprocessing",
    value_scaling: ImageValueScaling = ACT_IMAGE_VALUE_SCALING_RUNTIME_LEGACY,
    input_layout: ImageInputLayout = ACT_IMAGE_INPUT_LAYOUT_AUTO,
) -> ACTImageTransformResult:
    """Apply ACT's pure NumPy camera transform in configured camera order.

    ``camera_images`` is keyed by unprefixed camera name.  This form is used by
    the HDF5 training dataset and lets it share mask/layout/scale processing
    with frozen inference without constructing a policy object.  The dataset
    passes ``input_layout='hwc'`` because stored RGB is channel-last even when
    its height happens to equal three; runtime retains its legacy ``'auto'``
    channel-first precedence.
    """

    resolved_names = _resolve_camera_names(camera_names, method_name=method_name)
    resolved_scaling = _resolve_value_scaling(value_scaling)
    resolved_layout = _resolve_input_layout(input_layout)
    raw_images: list[np.ndarray] = []
    transformed_images: list[np.ndarray] = []
    for camera_name in resolved_names:
        try:
            camera_input = camera_images[camera_name]
        except KeyError as exc:
            raise ValueError(
                f"{method_name}: missing required camera input "
                f"{_camera_input_label(camera_name)!r}."
            ) from exc
        if camera_input is None:
            raise ValueError(
                f"{method_name}: missing required camera input "
                f"{_camera_input_label(camera_name)!r}."
            )
        raw_image = np.asarray(camera_input)
        mask = None if camera_masks is None else camera_masks.get(camera_name)
        transformed = _transform_one_camera(
            raw_image,
            camera_name=camera_name,
            image_mask_config=image_mask_config,
            mask=mask,
            method_name=method_name,
            value_scaling=resolved_scaling,
            input_layout=resolved_layout,
        )
        raw_images.append(raw_image)
        transformed_images.append(transformed)
    return ACTImageTransformResult(
        camera_names=resolved_names,
        raw_camera_images=tuple(raw_images),
        transformed_images=np.stack(transformed_images, axis=0),
        value_scaling=resolved_scaling,
        input_layout=resolved_layout,
    )


def preprocess_act_observation_images(
    observation: Mapping[str, Any],
    *,
    camera_names: Sequence[str],
    image_mask_config: Mapping[str, Any] | None = None,
    device: torch.device | str | None = None,
    method_name: str = "ACT image preprocessing",
    normalizer: ImageNormalizer | None = None,
) -> ACTImagePreprocessingResult:
    """Prepare one ACT inference observation through all image stages.

    Direct ``image_<camera>`` entries take precedence.  If absent, the helper
    decodes the existing nested raw/JPEG observation format exactly as the
    legacy adapter did.  The default normaliser is ImageNet; ``normalizer`` is
    injectable solely to preserve adapter compatibility and focused tests.
    """

    resolved_names = _resolve_camera_names(camera_names, method_name=method_name)
    camera_images: dict[str, Any] = {}
    camera_masks: dict[str, np.ndarray | None] = {}
    for camera_name in resolved_names:
        key = _camera_input_label(camera_name)
        camera_input = observation.get(key)
        if camera_input is None:
            try:
                camera_input = observation_camera_rgb(dict(observation), camera_name)
            except KeyError as exc:
                raise ValueError(
                    f"{method_name}: missing required camera input {key!r}."
                ) from exc
        camera_images[camera_name] = camera_input
        camera_masks[camera_name] = observation.get(f"image_mask_{camera_name}")

    transformed = transform_act_camera_images(
        camera_images=camera_images,
        camera_names=resolved_names,
        image_mask_config=image_mask_config,
        camera_masks=camera_masks,
        method_name=method_name,
        value_scaling=ACT_IMAGE_VALUE_SCALING_RUNTIME_LEGACY,
        input_layout=ACT_IMAGE_INPUT_LAYOUT_AUTO,
    )
    image = torch.from_numpy(transformed.transformed_images).float()
    if device is not None:
        image = image.to(device)
    batched_image = image.unsqueeze(0)
    normalize = normalize_act_image_tensor if normalizer is None else normalizer
    normalized = normalize(batched_image)
    if not isinstance(normalized, torch.Tensor):
        raise TypeError(f"{method_name}: image normalizer must return a torch.Tensor.")
    return ACTImagePreprocessingResult(
        camera_names=transformed.camera_names,
        raw_camera_images=transformed.raw_camera_images,
        transformed_images=transformed.transformed_images,
        normalized_images=normalized,
        value_scaling=transformed.value_scaling,
        input_layout=transformed.input_layout,
    )


def _transform_one_camera(
    raw_image: np.ndarray,
    *,
    camera_name: str,
    image_mask_config: Mapping[str, Any] | None,
    mask: np.ndarray | None,
    method_name: str,
    value_scaling: ImageValueScaling,
    input_layout: ImageInputLayout,
) -> np.ndarray:
    masked = apply_image_mask(
        raw_image,
        camera_name=camera_name,
        mask_config=None if image_mask_config is None else dict(image_mask_config),
        mask=mask,
    )
    image = np.asarray(masked, dtype=np.float32)
    key = _camera_input_label(camera_name)
    if image.ndim != 3:
        raise ValueError(
            f"{method_name}: expected {key!r} to be rank-3, got shape {image.shape}."
        )
    if input_layout == ACT_IMAGE_INPUT_LAYOUT_AUTO and image.shape[0] == 3:
        # Keep the legacy adapter's channel-first precedence for ambiguous
        # 3xHx3 runtime inputs.  Existing checkpoints therefore see the exact
        # same layout.
        return image
    if image.shape[-1] != 3:
        raise ValueError(
            f"{method_name}: expected {key!r} to have 3 channels, got shape {image.shape}."
        )
    image = np.transpose(image, (2, 0, 1))
    if value_scaling == ACT_IMAGE_VALUE_SCALING_RUNTIME_LEGACY:
        if image.max() > 1.0:
            image = image / 255.0
    else:
        image = image / 255.0
    return image


def _resolve_camera_names(
    camera_names: Sequence[str], *, method_name: str) -> tuple[str, ...]:
    names = tuple(str(name) for name in camera_names)
    if not names:
        raise ValueError(f"{method_name}: no camera inputs configured.")
    if any(not name for name in names):
        raise ValueError(f"{method_name}: configured camera names must be non-empty.")
    if len(set(names)) != len(names):
        raise ValueError(f"{method_name}: configured camera names contain duplicates.")
    return names


def _resolve_value_scaling(value: str) -> ImageValueScaling:
    if value not in ACT_IMAGE_VALUE_SCALING_MODES:
        raise ValueError(
            f"Unsupported ACT image value scaling {value!r}; expected one of "
            f"{ACT_IMAGE_VALUE_SCALING_MODES}."
        )
    return value  # type: ignore[return-value]


def _resolve_input_layout(value: str) -> ImageInputLayout:
    if value not in ACT_IMAGE_INPUT_LAYOUT_MODES:
        raise ValueError(
            f"Unsupported ACT image input layout {value!r}; expected one of "
            f"{ACT_IMAGE_INPUT_LAYOUT_MODES}."
        )
    return value  # type: ignore[return-value]


def _camera_input_label(camera_name: str) -> str:
    return f"image_{camera_name}"


__all__ = [
    "ACT_IMAGENET_MEAN",
    "ACT_IMAGENET_STD",
    "ACT_IMAGE_INPUT_LAYOUT_AUTO",
    "ACT_IMAGE_INPUT_LAYOUT_HWC",
    "ACT_IMAGE_INPUT_LAYOUT_MODES",
    "ACT_IMAGE_VALUE_SCALING_MODES",
    "ACT_IMAGE_VALUE_SCALING_RUNTIME_LEGACY",
    "ACT_IMAGE_VALUE_SCALING_TRAINING_DATASET",
    "ACTImagePreprocessingResult",
    "ACTImageTransformResult",
    "make_act_image_normalizer",
    "normalize_act_image_tensor",
    "preprocess_act_observation_images",
    "transform_act_camera_images",
]
