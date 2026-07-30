from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
import torch
import yaml

from testbed.data.camera_images import observation_camera_rgb
from testbed.policies.act.adapter import ACTAdapter


CAMERAS = ["stick_up", "stick_down", "eye_left", "eye_right"]


def _jpeg(rgb: np.ndarray) -> bytes:
    ok, payload = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    assert ok
    return payload.tobytes()


def test_live_camera_helper_decodes_encoded_jpeg_to_rgb() -> None:
    rgb = np.zeros((6, 8, 3), dtype=np.uint8)
    rgb[..., 0] = 220
    decoded = observation_camera_rgb(
        {
            "images": {},
            "encoded_images": {
                "stick_up": {"encoding": "jpeg", "data": _jpeg(rgb)}
            },
        },
        "stick_up",
    )
    assert decoded.shape == rgb.shape
    assert decoded.dtype == np.uint8
    assert float(decoded[..., 0].mean()) > 200
    assert float(decoded[..., 2].mean()) < 20


def test_live_camera_helper_preserves_legacy_raw_rgb() -> None:
    rgb = np.arange(18, dtype=np.uint8).reshape(2, 3, 3)
    decoded = observation_camera_rgb({"images": {"fpv": rgb}}, "fpv")
    np.testing.assert_array_equal(decoded, rgb)


def test_live_camera_helper_fails_for_missing_or_duplicate_camera() -> None:
    with pytest.raises(KeyError, match="eye_right"):
        observation_camera_rgb({"images": {}, "encoded_images": {}}, "eye_right")

    rgb = np.zeros((2, 3, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="both raw and encoded"):
        observation_camera_rgb(
            {
                "images": {"eye_left": rgb},
                "encoded_images": {"eye_left": _jpeg(rgb)},
            },
            "eye_left",
        )


class _FakeActModel:
    def eval(self) -> None:
        return None

    def __call__(self, proprio, image, _actions):
        assert tuple(image.shape) == (1, 1, 3, 6, 8)
        return torch.zeros((1, 1, 4)), None, (None, None)


def test_act_adapter_accepts_nested_encoded_live_observation() -> None:
    adapter = ACTAdapter.__new__(ACTAdapter)
    adapter.device = torch.device("cpu")
    adapter._camera_names = ["stick_up"]
    adapter._low_dim_keys = ["qpos"]
    adapter._image_mask_config = {}
    adapter._normalize = lambda value: value
    adapter._proprio_mean = torch.zeros((1, 4), dtype=torch.float32)
    adapter._proprio_std = torch.ones((1, 4), dtype=torch.float32)
    adapter._model = _FakeActModel()
    adapter.temporal_agg = False
    adapter._num_queries = 1
    adapter._t = 0
    adapter.norm_stats = {
        "action_mean": np.zeros(4, dtype=np.float32),
        "action_std": np.ones(4, dtype=np.float32),
    }

    rgb = np.zeros((6, 8, 3), dtype=np.uint8)
    action = adapter.predict(
        {
            "qpos": np.zeros(4, dtype=np.float32),
            "encoded_images": {
                "stick_up": {"encoding": "jpeg", "data": _jpeg(rgb)}
            },
        }
    )
    np.testing.assert_array_equal(action, np.zeros(4, dtype=np.float32))


def test_four_camera_teleop_config_is_explicit_and_legacy_config_is_unchanged() -> None:
    config_root = Path("testbed/configs")
    legacy = yaml.safe_load(
        (config_root / "teleop_yulong_v2_2_pro_full_task.yaml").read_text()
    )
    four_camera = yaml.safe_load(
        (
            config_root
            / "teleop_yulong_v2_2_pro_full_task_four_camera_jpeg.yaml"
        ).read_text()
    )

    assert legacy["task"]["camera_names"] == ["fpv"]
    assert four_camera["task"]["camera_names"] == CAMERAS
    assert four_camera["task"]["dataset_dir"] != legacy["task"]["dataset_dir"]
    assert legacy["teleop"]["joystick"]["scale"] == [0.6, 0.3, 0.7, 0.7]
    assert legacy["teleop"]["joystick"]["response_profile"]["deadzone"] == [
        0.05,
        0.05,
        0.05,
        0.05,
    ]
    assert four_camera["teleop"]["joystick"]["scale"] == [1.0, 1.0, 1.0, 1.0]
    assert four_camera["teleop"]["joystick"]["response_profile"]["deadzone"] == [
        0.1,
        0.1,
        0.1,
        0.1,
    ]
    assert four_camera["success"] == legacy["success"]
    assert four_camera["reward"] == legacy["reward"]
    assert four_camera["action_semantics"] == legacy["action_semantics"]
