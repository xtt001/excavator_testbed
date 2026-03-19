from __future__ import annotations

import io
import socket
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from testbed.backends.agx.backend import AgxSimBackend
from testbed.backends.agx.protocol import (
    IMAGE_PIXEL_FORMAT,
    AgxProtocolError,
    AgxSimClient,
    MessageType,
    StepResponse,
    _pack_bool,
    _pack_bytes,
    _pack_float_array,
    _pack_string,
    _pack_string_array,
    encode_frame,
    read_frame,
)


def _build_get_info_response() -> bytes:
    payload = io.BytesIO()
    payload.write(_pack_bool(True))
    payload.write(_pack_string(""))
    payload.write(_pack_string("agx-sim/v0"))
    payload.write(np.float32(0.02).astype("<f4").tobytes())
    payload.write(np.float32(50.0).astype("<f4").tobytes())
    payload.write(_pack_string("actuator_speed_cmd"))
    payload.write(
        _pack_string_array(
            ["swing_speed_cmd", "boom_speed_cmd", "stick_speed_cmd", "bucket_speed_cmd"]
        )
    )
    payload.write(
        _pack_string_array(
            [
                "swing_position_norm",
                "boom_position_norm",
                "stick_position_norm",
                "bucket_position_norm",
            ]
        )
    )
    payload.write(
        _pack_string_array(["swing_speed", "boom_speed", "stick_speed", "bucket_speed"])
    )
    payload.write(_pack_string_array(["mass_in_bucket_kg"]))
    payload.write(_pack_string_array(["fpv"]))
    payload.write(_pack_bool(True))
    payload.write(_pack_bool(True))
    payload.write((1).to_bytes(4, "little", signed=True))
    payload.write(_pack_string("fpv"))
    payload.write((2).to_bytes(4, "little", signed=True))
    payload.write((1).to_bytes(4, "little", signed=True))
    payload.write(np.float32(50.0).astype("<f4").tobytes())
    payload.write(_pack_string("raw_rgb"))
    payload.write(_pack_string("top_to_bottom"))
    payload.write(_pack_string_array([]))
    return encode_frame(MessageType.GET_INFO_RESP, payload.getvalue())


def _build_reset_response() -> bytes:
    payload = io.BytesIO()
    payload.write(_pack_bool(True))
    payload.write(_pack_string(""))
    payload.write(_pack_bool(True))
    payload.write(np.float32(0.02).astype("<f4").tobytes())
    payload.write(np.float32(50.0).astype("<f4").tobytes())
    payload.write(_pack_string_array([]))
    return encode_frame(MessageType.RESET_RESP, payload.getvalue())


def _build_step_response(
    step_id: int,
    image_bytes: bytes = b"\x01\x02\x03\x04\x05\x06",
) -> bytes:
    payload = io.BytesIO()
    payload.write(_pack_bool(True))
    payload.write(_pack_string(""))
    payload.write(np.int64(step_id).astype("<i8").tobytes())
    payload.write(_pack_float_array([0.1, 0.2, 0.3, 0.4]))
    payload.write(_pack_float_array([1.0, 2.0, 3.0, 4.0]))
    payload.write(_pack_float_array([5.0]))
    payload.write(_pack_string(IMAGE_PIXEL_FORMAT))
    payload.write((2).to_bytes(4, "little", signed=True))
    payload.write((1).to_bytes(4, "little", signed=True))
    payload.write(_pack_bytes(image_bytes))
    payload.write(np.float32(0.0).astype("<f4").tobytes())
    payload.write(np.int64(123456789).astype("<i8").tobytes())
    payload.write(_pack_string_array(["auto_stepping_disabled_by_server"]))
    return encode_frame(MessageType.STEP_RESP, payload.getvalue())


def _serve_scripted(
    script: list[tuple[MessageType, bytes]]
) -> tuple[str, int, threading.Thread]:
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    host, port = server.getsockname()

    def _worker() -> None:
        conn, _ = server.accept()
        with conn:
            for expected_type, response_frame in script:
                request_type, _ = read_frame(conn)
                if request_type != expected_type:
                    raise AssertionError(
                        f"expected request {expected_type}, got {request_type}"
                    )
                conn.sendall(response_frame)
        server.close()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return host, port, thread


class AgxProtocolTests(unittest.TestCase):
    def test_client_roundtrip(self) -> None:
        host, port, thread = _serve_scripted(
            [
                (MessageType.GET_INFO_REQ, _build_get_info_response()),
                (MessageType.RESET_REQ, _build_reset_response()),
                (MessageType.STEP_REQ, _build_step_response(step_id=7)),
            ]
        )

        with AgxSimClient(host=host, port=port, timeout_s=1.0) as client:
            info = client.get_info()
            self.assertEqual(info.protocol_version, "agx-sim/v0")
            self.assertEqual(info.camera_names, ("fpv",))

            reset = client.reset(seed=3)
            self.assertTrue(reset.reset_applied)

            step = client.step(7, np.zeros(4, dtype=np.float32))
            self.assertEqual(step.step_id, 7)
            np.testing.assert_allclose(step.qpos, [0.1, 0.2, 0.3, 0.4])
            np.testing.assert_allclose(step.qvel, [1.0, 2.0, 3.0, 4.0])
            np.testing.assert_allclose(step.env_state, [5.0])
            self.assertEqual(step.decode_rgb_image().shape, (1, 2, 3))

        thread.join(timeout=1.0)
        self.assertFalse(thread.is_alive())

    def test_backend_reset_synthesizes_initial_observation(self) -> None:
        host, port, thread = _serve_scripted(
            [
                (MessageType.GET_INFO_REQ, _build_get_info_response()),
                (MessageType.RESET_REQ, _build_reset_response()),
                (MessageType.STEP_REQ, _build_step_response(step_id=0)),
            ]
        )

        backend = AgxSimBackend(host=host, port=port, timeout_s=1.0)
        try:
            ts = backend.reset(seed=11)
            self.assertEqual(ts.observation["step_id"], 0)
            self.assertTrue(ts.observation["reset_applied"])
            self.assertEqual(ts.observation["images"]["fpv"].shape, (1, 2, 3))
            self.assertEqual(backend.render("fpv", height=1, width=2).shape, (1, 2, 3))
        finally:
            backend.close()

        thread.join(timeout=1.0)
        self.assertFalse(thread.is_alive())

    def test_backend_reset_uses_configured_reset_flags(self) -> None:
        backend = AgxSimBackend(
            host="127.0.0.1",
            port=5057,
            timeout_s=1.0,
            reset_terrain=False,
            reset_pose=True,
        )
        backend._info = SimpleNamespace(
            action_order=(
                "swing_speed_cmd",
                "boom_speed_cmd",
                "stick_speed_cmd",
                "bucket_speed_cmd",
            )
        )

        fake_reset = SimpleNamespace(reset_applied=True, warnings=())
        fake_timestep = SimpleNamespace(observation={})

        with (
            patch.object(backend._client, "reset", return_value=fake_reset) as mock_reset,
            patch.object(backend, "_step_with_id", return_value=fake_timestep),
        ):
            backend.reset(seed=11)

        mock_reset.assert_called_once_with(
            seed=11,
            reset_terrain=False,
            reset_pose=True,
        )
        self.assertTrue(fake_timestep.observation["reset_applied"])
        self.assertEqual(fake_timestep.observation["reset_warnings"], [])

    def test_step_image_payload_size_is_validated(self) -> None:
        response = StepResponse(
            success=True,
            error="",
            step_id=0,
            qpos=np.zeros(4, dtype=np.float32),
            qvel=np.zeros(4, dtype=np.float32),
            env_state=np.zeros(1, dtype=np.float32),
            image_format=IMAGE_PIXEL_FORMAT,
            image_w=2,
            image_h=1,
            image_payload=b"\x01\x02\x03",
            reward=0.0,
            sim_time_ns=0,
            warnings=(),
        )
        with self.assertRaises(AgxProtocolError):
            response.decode_rgb_image()


if __name__ == "__main__":
    unittest.main()
