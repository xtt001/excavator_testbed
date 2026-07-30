from __future__ import annotations

import io
from types import SimpleNamespace

import numpy as np
import pytest

from testbed.backends.agx.backend import AgxSimBackend
from testbed.backends.agx.protocol import (
    IMAGE_COLOR_SPACE,
    MULTI_CAMERA_STEP_MARKER,
    AgxProtocolError,
    ImageFrame,
    StepResponse,
    _pack_bool,
    _pack_bytes,
    _pack_float_array,
    _pack_string,
    _pack_string_array,
    decode_get_info_response,
    decode_step_response,
)

CAMERAS = ("stick_up", "stick_down", "eye_left", "eye_right")


def _i32(value: int) -> bytes:
    return int(value).to_bytes(4, "little", signed=True)


def _i64(value: int) -> bytes:
    return int(value).to_bytes(8, "little", signed=True)


def _f32(value: float) -> bytes:
    return np.float32(value).astype("<f4").tobytes()


def _multi_step_payload() -> tuple[bytes, dict[str, bytes]]:
    payloads = {name: b"\xff\xd8" + bytes([index]) + b"\xff\xd9" for index, name in enumerate(CAMERAS)}
    stream = io.BytesIO()
    stream.write(_pack_bool(True))
    stream.write(_pack_string(""))
    stream.write(_i64(7))
    stream.write(_pack_float_array([0.1, 0.2, 0.3, 0.4]))
    stream.write(_pack_float_array([0.0, 0.0, 0.0, 0.0]))
    stream.write(_pack_float_array([1.0, 2.0]))
    stream.write(_i32(MULTI_CAMERA_STEP_MARKER))
    stream.write(_i32(len(CAMERAS)))
    for name in CAMERAS:
        stream.write(_pack_string(name))
        stream.write(_pack_string("jpeg"))
        stream.write(_i32(512))
        stream.write(_i32(288))
        stream.write(_pack_string("top_to_bottom"))
        stream.write(_pack_string("rgb"))
        stream.write(_pack_bytes(payloads[name]))
    stream.write(_f32(3.5))
    stream.write(_i64(123))
    stream.write(_pack_string_array([]))
    return stream.getvalue(), payloads


def test_v1_get_info_decodes_four_camera_color_metadata() -> None:
    stream = io.BytesIO()
    stream.write(_pack_bool(True))
    stream.write(_pack_string(""))
    stream.write(_pack_string("agx-sim/v1"))
    stream.write(_f32(0.02))
    stream.write(_f32(50.0))
    stream.write(_pack_string("actuator_speed_cmd"))
    stream.write(_pack_string_array(["a0", "a1", "a2", "a3"]))
    stream.write(_pack_string_array(["q0", "q1", "q2", "q3"]))
    stream.write(_pack_string_array(["v0", "v1", "v2", "v3"]))
    stream.write(_pack_string_array([]))
    stream.write(_pack_string_array(CAMERAS))
    stream.write(_pack_bool(True))
    stream.write(_pack_bool(True))
    stream.write(_i32(4))
    for name in CAMERAS:
        stream.write(_pack_string(name))
        stream.write(_i32(512))
        stream.write(_i32(288))
        stream.write(_f32(50.0))
        stream.write(_pack_string("jpeg"))
        stream.write(_pack_string("top_to_bottom"))
        stream.write(_pack_string(IMAGE_COLOR_SPACE))
    stream.write(_pack_string_array([]))

    info = decode_get_info_response(stream.getvalue())
    assert info.camera_names == CAMERAS
    assert [camera.pixel_format for camera in info.cameras] == ["jpeg"] * 4
    assert [camera.color_space for camera in info.cameras] == ["rgb"] * 4


def test_multicamera_step_decoder_and_backend_preserve_exact_jpeg_bytes() -> None:
    payload, expected_payloads = _multi_step_payload()
    response = decode_step_response(payload)
    assert [frame.name for frame in response.images] == list(CAMERAS)
    assert {frame.name: frame.payload for frame in response.images} == expected_payloads
    assert response.image_payload == b""

    backend = AgxSimBackend.__new__(AgxSimBackend)
    backend.get_info = lambda: SimpleNamespace(camera_names=CAMERAS)
    observation = backend._obs_from_step_response(response)
    assert observation["images"] == {}
    assert list(observation["encoded_images"]) == list(CAMERAS)
    for name in CAMERAS:
        encoded = observation["encoded_images"][name]
        assert encoded["data"] == expected_payloads[name]
        assert encoded["shape"] == (288, 512, 3)


def test_backend_rejects_partial_or_reordered_multicamera_response() -> None:
    payload, _ = _multi_step_payload()
    response = decode_step_response(payload)
    reordered = StepResponse(**{**response.__dict__, "images": tuple(reversed(response.images))})
    backend = AgxSimBackend.__new__(AgxSimBackend)
    backend.get_info = lambda: SimpleNamespace(camera_names=CAMERAS)
    with pytest.raises(AgxProtocolError, match="camera frame order/set mismatch"):
        backend._obs_from_step_response(reordered)


def test_backend_rejects_invalid_encoded_frame_dimensions() -> None:
    payload, _ = _multi_step_payload()
    response = decode_step_response(payload)
    invalid_first = ImageFrame(**{**response.images[0].__dict__, "width": 0})
    invalid = StepResponse(
        **{**response.__dict__, "images": (invalid_first, *response.images[1:])}
    )
    backend = AgxSimBackend.__new__(AgxSimBackend)
    backend.get_info = lambda: SimpleNamespace(camera_names=CAMERAS)
    with pytest.raises(AgxProtocolError, match="invalid encoded camera"):
        backend._obs_from_step_response(invalid)


def test_legacy_raw_step_response_still_decodes_rgb() -> None:
    response = StepResponse(
        success=True,
        error="",
        step_id=1,
        qpos=np.zeros(4, dtype=np.float32),
        qvel=np.zeros(4, dtype=np.float32),
        env_state=np.zeros(2, dtype=np.float32),
        image_format="raw_rgb",
        image_w=2,
        image_h=1,
        image_payload=b"\x01\x02\x03\x04\x05\x06",
        reward=0.0,
        sim_time_ns=0,
        warnings=(),
    )
    backend = AgxSimBackend.__new__(AgxSimBackend)
    observation = backend._obs_from_step_response(response)
    assert observation["images"]["fpv"].shape == (1, 2, 3)
    assert observation["encoded_images"] == {}
