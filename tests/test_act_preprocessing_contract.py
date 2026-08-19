"""Equivalence tests for public ACT input preprocessing contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pytest
import torch

from testbed.data import assemble_act_low_dim_observation
from testbed.data.dataset import _assemble_low_dim_observation
from testbed.data.image_masks import apply_image_mask
from testbed.policies.act.adapter import ACTAdapter
from testbed.policies.act.image_preprocessing import (
    ACT_IMAGE_INPUT_LAYOUT_HWC,
    ACT_IMAGE_VALUE_SCALING_RUNTIME_LEGACY,
    ACT_IMAGE_VALUE_SCALING_TRAINING_DATASET,
    make_act_image_normalizer,
    preprocess_act_observation_images,
    transform_act_camera_images,
)


def _adapter(*, camera_names: Sequence[str]) -> ACTAdapter:
    adapter = object.__new__(ACTAdapter)
    adapter.device = torch.device("cpu")
    adapter._camera_names = list(camera_names)
    adapter._low_dim_keys = ["qpos"]
    adapter._image_mask_config = {
        "enabled": True,
        "mode": "multiply",
        "cameras": {"left": {"rect_xyxy_px": [1, 0, 3, 2]}},
    }
    adapter._normalize = make_act_image_normalizer()
    adapter._proprio_mean = torch.zeros(4, dtype=torch.float32)
    adapter._proprio_std = torch.ones(4, dtype=torch.float32)
    return adapter


def _legacy_runtime_image_preprocessing(
    observation: Mapping[str, Any],
    *,
    camera_names: Sequence[str],
    image_mask_config: Mapping[str, Any] | None,
) -> torch.Tensor:
    """Frozen reference of the pre-refactor adapter image path."""

    camera_images: list[np.ndarray] = []
    for camera_name in camera_names:
        key = f"image_{camera_name}"
        image = np.asarray(observation[key])
        image = apply_image_mask(
            image,
            camera_name=camera_name,
            mask_config=None if image_mask_config is None else dict(image_mask_config),
            mask=observation.get(f"image_mask_{camera_name}"),
        )
        image = np.asarray(image, dtype=np.float32)
        if image.ndim != 3:
            raise ValueError(f"expected {key!r} to be rank-3")
        if image.shape[0] == 3:
            pass
        elif image.shape[-1] == 3:
            image = np.transpose(image, (2, 0, 1))
            if image.max() > 1.0:
                image = image / 255.0
        else:
            raise ValueError(f"expected {key!r} to have 3 channels")
        camera_images.append(image)
    return make_act_image_normalizer()(
        torch.from_numpy(np.stack(camera_images, axis=0)).float().unsqueeze(0)
    )


def test_public_low_dim_assembly_matches_legacy_dataset_facade_for_sequence() -> None:
    qpos = np.arange(8, dtype=np.float64).reshape(2, 4)
    qvel = qpos + 10.0
    token = np.arange(20, dtype=np.float64).reshape(2, 10) / 10.0
    expected = _assemble_low_dim_observation(
        qpos=qpos,
        qvel=qvel,
        dig_cut_tokens=token,
        low_dim_keys=["qvel", "dig_cut_tokens", "qpos"],
    )
    actual = assemble_act_low_dim_observation(
        qpos=qpos,
        qvel=qvel,
        dig_cut_tokens=token,
        low_dim_keys=["qvel", "dig_cut_tokens", "qpos"],
    )

    assert actual.dtype == np.float32
    np.testing.assert_array_equal(actual, expected)


def test_public_preprocessor_matches_legacy_runtime_for_masked_hwc_uint8_order() -> None:
    left = np.zeros((2, 3, 3), dtype=np.uint8)
    left[..., 0] = 255
    right = np.zeros((2, 3, 3), dtype=np.uint8)
    right[..., 1] = 128
    observation = {
        "qpos": np.zeros(4, dtype=np.float32),
        "image_left": left,
        "image_right": right,
    }
    adapter = _adapter(camera_names=["right", "left"])

    public = preprocess_act_observation_images(
        observation,
        camera_names=adapter._camera_names,
        image_mask_config=adapter._image_mask_config,
        device="cpu",
    )
    legacy = _legacy_runtime_image_preprocessing(
        observation,
        camera_names=adapter._camera_names,
        image_mask_config=adapter._image_mask_config,
    )
    _, adapter_image = adapter._prepare_inference_inputs(
        observation,
        method_name="test",
    )

    assert public.camera_names == ("right", "left")
    np.testing.assert_array_equal(public.raw_camera_images[0], right)
    np.testing.assert_array_equal(public.raw_camera_images[1], left)
    assert public.transformed_images.shape == (2, 3, 2, 3)
    assert public.transformed_images[0, 1, 0, 0] == pytest.approx(128.0 / 255.0)
    assert public.transformed_images[1, 0, 0, 0] == pytest.approx(0.0)
    assert public.transformed_images[1, 0, 0, 1] == pytest.approx(1.0)
    torch.testing.assert_close(public.normalized_images, legacy)
    torch.testing.assert_close(adapter_image, legacy)


def test_public_preprocessor_preserves_channel_first_float_runtime_input() -> None:
    image = np.full((3, 2, 2), 0.25, dtype=np.float32)
    observation = {
        "qpos": np.zeros(4, dtype=np.float32),
        "image_fpv": image,
    }
    adapter = _adapter(camera_names=["fpv"])
    adapter._image_mask_config = {}

    public = preprocess_act_observation_images(
        observation,
        camera_names=["fpv"],
        image_mask_config={},
        device="cpu",
    )
    _, adapter_image = adapter._prepare_inference_inputs(
        observation,
        method_name="test",
    )

    np.testing.assert_array_equal(public.transformed_images[0], image)
    torch.testing.assert_close(adapter_image, public.normalized_images)


def test_pure_training_and_runtime_transform_modes_preserve_historical_scaling() -> None:
    image = np.ones((2, 2, 3), dtype=np.uint8)
    runtime = transform_act_camera_images(
        camera_images={"fpv": image},
        camera_names=["fpv"],
        value_scaling=ACT_IMAGE_VALUE_SCALING_RUNTIME_LEGACY,
    )
    training = transform_act_camera_images(
        camera_images={"fpv": image},
        camera_names=["fpv"],
        value_scaling=ACT_IMAGE_VALUE_SCALING_TRAINING_DATASET,
    )

    assert runtime.transformed_images[0, 0, 0, 0] == pytest.approx(1.0)
    assert training.transformed_images[0, 0, 0, 0] == pytest.approx(1.0 / 255.0)


def test_training_hwc_layout_preserves_legacy_dataset_when_height_is_three() -> None:
    image = np.arange(18, dtype=np.uint8).reshape(3, 2, 3)
    transformed = transform_act_camera_images(
        camera_images={"fpv": image},
        camera_names=["fpv"],
        value_scaling=ACT_IMAGE_VALUE_SCALING_TRAINING_DATASET,
        input_layout=ACT_IMAGE_INPUT_LAYOUT_HWC,
    )
    legacy = torch.einsum(
        "k h w c -> k c h w",
        torch.from_numpy(image[None]),
    ).float() / 255.0

    torch.testing.assert_close(
        torch.from_numpy(transformed.transformed_images),
        legacy,
    )
    assert transformed.input_layout == ACT_IMAGE_INPUT_LAYOUT_HWC


def test_public_preprocessor_rejects_bad_masks_missing_cameras_and_duplicate_order() -> None:
    image = np.zeros((2, 2, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="image_right"):
        transform_act_camera_images(
            camera_images={"left": image},
            camera_names=["left", "right"],
        )
    with pytest.raises(ValueError, match="Mask.*expected"):
        transform_act_camera_images(
            camera_images={"left": image},
            camera_names=["left"],
            image_mask_config={
                "enabled": True,
                "cameras": {"left": {"mask_dataset": "unused"}},
            },
            camera_masks={"left": np.zeros((1, 2), dtype=np.uint8)},
        )
    with pytest.raises(ValueError, match="duplicates"):
        transform_act_camera_images(
            camera_images={"left": image},
            camera_names=["left", "left"],
        )
