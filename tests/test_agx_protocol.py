from __future__ import annotations

import io
import socket
import struct
import threading
import unittest
import zlib
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
    _PayloadReader,
    _pack_bool,
    _pack_bytes,
    _pack_float_array,
    _pack_string,
    _pack_string_array,
    encode_frame,
    encode_realign_pose_request,
    encode_step_request,
    read_frame,
)
from testbed.tasks.logic.excavator_reward import (
    AgxExcavationRewardTracker,
    get_agx_excavation_mission,
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
    payload.write(
        _pack_string_array(
            [
                "mass_in_bucket_kg",
                "excavated_mass_kg",
                "mass_in_target_box_kg",
                "deposited_mass_in_target_box_kg",
                "min_distance_to_target_m",
                "target_hard_collision_count",
                "target_contact_max_normal_force_n",
                "min_distance_to_dig_area_m",
                "bucket_depth_below_dig_area_plane_m",
            ]
        )
    )
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
    message_type: MessageType = MessageType.STEP_RESP,
) -> bytes:
    payload = io.BytesIO()
    payload.write(_pack_bool(True))
    payload.write(_pack_string(""))
    payload.write(np.int64(step_id).astype("<i8").tobytes())
    payload.write(_pack_float_array([0.1, 0.2, 0.3, 0.4]))
    payload.write(_pack_float_array([1.0, 2.0, 3.0, 4.0]))
    payload.write(_pack_float_array([5.0, 6.0, 7.0, 8.0, 1.5, 0.0, 0.0, 0.25, 0.0]))
    payload.write(_pack_string(IMAGE_PIXEL_FORMAT))
    payload.write((2).to_bytes(4, "little", signed=True))
    payload.write((1).to_bytes(4, "little", signed=True))
    payload.write(_pack_bytes(image_bytes))
    payload.write(np.float32(0.0).astype("<f4").tobytes())
    payload.write(np.int64(123456789).astype("<i8").tobytes())
    payload.write(_pack_string_array(["auto_stepping_disabled_by_server"]))
    return encode_frame(message_type, payload.getvalue())


def _serve_scripted(
    script: list[tuple[MessageType, bytes | list[bytes] | tuple[bytes, ...]]]
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
                if isinstance(response_frame, (list, tuple)):
                    for frame in response_frame:
                        conn.sendall(frame)
                else:
                    conn.sendall(response_frame)
        server.close()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return host, port, thread


def _decode_request_frame(frame: bytes) -> tuple[MessageType, bytes]:
    magic, version, raw_message_type, payload_len, expected_crc = struct.unpack(
        "<IHHII",
        frame[:16],
    )
    self_crc = zlib.crc32(frame[16:]) & 0xFFFFFFFF
    if magic != 0xA6A6A6A6 or version != 1:
        raise AssertionError("invalid encoded test frame header")
    if payload_len != len(frame) - 16:
        raise AssertionError("invalid encoded test frame payload length")
    if self_crc != expected_crc:
        raise AssertionError("invalid encoded test frame crc")
    return MessageType(raw_message_type), frame[16:]


class AgxProtocolTests(unittest.TestCase):
    def test_step_request_encoder_keeps_legacy_layout_without_debug(self) -> None:
        frame = encode_step_request(7, np.zeros(4, dtype=np.float32))
        message_type, payload = _decode_request_frame(frame)
        self.assertEqual(message_type, MessageType.STEP_REQ)

        reader = _PayloadReader(payload)
        self.assertEqual(reader.read_int64(), 7)
        np.testing.assert_allclose(reader.read_float_array(), np.zeros(4))
        reader.ensure_fully_consumed()

    def test_step_request_encoder_appends_planner_debug_json(self) -> None:
        frame = encode_step_request(
            8,
            np.ones(4, dtype=np.float32),
            client_time_ns=123,
            planner_debug_json='{"mode":"operator_prior_coverage"}',
        )
        message_type, payload = _decode_request_frame(frame)
        self.assertEqual(message_type, MessageType.STEP_REQ)

        reader = _PayloadReader(payload)
        self.assertEqual(reader.read_int64(), 8)
        np.testing.assert_allclose(reader.read_float_array(), np.ones(4))
        self.assertEqual(reader.read_int64(), 123)
        self.assertEqual(
            reader.read_string(),
            '{"mode":"operator_prior_coverage"}',
        )
        reader.ensure_fully_consumed()

    def test_realign_pose_request_encoder(self) -> None:
        frame = encode_realign_pose_request(
            9,
            [0.5, 0.2, 0.3, 0.4],
            qvel=[0.0, 1.0, 2.0, 3.0],
            burn_in_steps=7,
            client_time_ns=456,
            reason="swing_jump_replay",
        )
        message_type, payload = _decode_request_frame(frame)
        self.assertEqual(message_type, MessageType.REALIGN_POSE_REQ)

        reader = _PayloadReader(payload)
        self.assertEqual(reader.read_int64(), 9)
        np.testing.assert_allclose(reader.read_float_array(), [0.5, 0.2, 0.3, 0.4])
        np.testing.assert_allclose(reader.read_float_array(), [0.0, 1.0, 2.0, 3.0])
        self.assertEqual(reader.read_int32(), 7)
        self.assertEqual(reader.read_int64(), 456)
        self.assertEqual(reader.read_string(), "swing_jump_replay")
        reader.ensure_fully_consumed()

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
            np.testing.assert_allclose(
                step.env_state,
                [5.0, 6.0, 7.0, 8.0, 1.5, 0.0, 0.0, 0.25, 0.0],
            )
            self.assertEqual(step.decode_rgb_image().shape, (1, 2, 3))

        thread.join(timeout=1.0)
        self.assertFalse(thread.is_alive())

    def test_client_realign_pose_roundtrip(self) -> None:
        host, port, thread = _serve_scripted(
            [
                (
                    MessageType.REALIGN_POSE_REQ,
                    _build_step_response(
                        step_id=9,
                        message_type=MessageType.REALIGN_POSE_RESP,
                    ),
                ),
            ]
        )

        with AgxSimClient(host=host, port=port, timeout_s=1.0) as client:
            response = client.realign_pose(
                9,
                np.array([0.5, 0.2, 0.3, 0.4], dtype=np.float32),
                burn_in_steps=3,
                reason="unit_test",
            )
            self.assertEqual(response.step_id, 9)
            np.testing.assert_allclose(response.qpos, [0.1, 0.2, 0.3, 0.4])

        thread.join(timeout=1.0)
        self.assertFalse(thread.is_alive())

    def test_client_roundtrip_skips_one_stale_response_frame(self) -> None:
        host, port, thread = _serve_scripted(
            [
                (
                    MessageType.GET_INFO_REQ,
                    [_build_reset_response(), _build_get_info_response()],
                ),
                (
                    MessageType.RESET_REQ,
                    [_build_get_info_response(), _build_reset_response()],
                ),
                (
                    MessageType.STEP_REQ,
                    [_build_reset_response(), _build_step_response(step_id=7)],
                ),
            ]
        )

        with AgxSimClient(host=host, port=port, timeout_s=1.0) as client:
            info = client.get_info()
            self.assertEqual(info.protocol_version, "agx-sim/v0")

            reset = client.reset(seed=3)
            self.assertTrue(reset.reset_applied)

            step = client.step(7, np.zeros(4, dtype=np.float32))
            self.assertEqual(step.step_id, 7)

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
            scenario_id=None,
        )
        self.assertTrue(fake_timestep.observation["reset_applied"])
        self.assertEqual(fake_timestep.observation["reset_warnings"], [])

    def test_backend_reset_uses_configured_scenario_id(self) -> None:
        backend = AgxSimBackend(
            host="127.0.0.1",
            port=5057,
            timeout_s=1.0,
            scenario_id="s0_baseline",
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
            backend.reset(seed=5)

        mock_reset.assert_called_once_with(
            seed=5,
            reset_terrain=True,
            reset_pose=True,
            scenario_id="s0_baseline",
        )

    def test_backend_get_info_retries_once_after_unexpected_response_type(self) -> None:
        backend = AgxSimBackend(host="127.0.0.1", port=5057, timeout_s=1.0)
        fake_info = SimpleNamespace(
            protocol_version="agx-sim/v0",
            env_state_order=(
                "mass_in_bucket_kg",
                "excavated_mass_kg",
                "mass_in_target_box_kg",
                "deposited_mass_in_target_box_kg",
                "min_distance_to_target_m",
                "target_hard_collision_count",
                "target_contact_max_normal_force_n",
                "min_distance_to_dig_area_m",
                "bucket_depth_below_dig_area_plane_m",
            ),
        )

        with (
            patch.object(
                backend._client,
                "get_info",
                side_effect=[
                    AgxProtocolError(
                        "unexpected response type STEP_RESP, expected GET_INFO_RESP"
                    ),
                    fake_info,
                ],
            ) as mock_get_info,
            patch.object(backend._client, "close") as mock_close,
        ):
            info = backend.get_info()

        self.assertIs(info, fake_info)
        self.assertEqual(mock_get_info.call_count, 2)
        mock_close.assert_called_once()

    def test_backend_reset_retries_once_after_unexpected_response_type(self) -> None:
        backend = AgxSimBackend(host="127.0.0.1", port=5057, timeout_s=1.0)
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
            patch.object(
                backend._client,
                "reset",
                side_effect=[
                    AgxProtocolError(
                        "unexpected response type GET_INFO_RESP, expected RESET_RESP"
                    ),
                    fake_reset,
                ],
            ) as mock_reset,
            patch.object(backend._client, "close") as mock_close,
            patch.object(backend, "_step_with_id", return_value=fake_timestep),
        ):
            backend.reset(seed=9)

        self.assertEqual(mock_reset.call_count, 2)
        mock_close.assert_called_once()
        self.assertTrue(fake_timestep.observation["reset_applied"])

    def test_step_image_payload_size_is_validated(self) -> None:
        response = StepResponse(
            success=True,
            error="",
            step_id=0,
            qpos=np.zeros(4, dtype=np.float32),
            qvel=np.zeros(4, dtype=np.float32),
            env_state=np.zeros(9, dtype=np.float32),
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

    def test_reward_tracker_uses_target_mass_success_signal(self) -> None:
        mission = get_agx_excavation_mission(
            "agx_excavation_teleop",
            success_mode="final_hold",
            success_mass_thresh=10.0,
            success_hold_steps=2,
        )
        tracker = AgxExcavationRewardTracker(
            mission=mission,
            env_state_order=(
                "mass_in_bucket_kg",
                "excavated_mass_kg",
                "mass_in_target_box_kg",
                "deposited_mass_in_target_box_kg",
                "min_distance_to_target_m",
                "target_hard_collision_count",
                "target_contact_max_normal_force_n",
                "min_distance_to_dig_area_m",
                "bucket_depth_below_dig_area_plane_m",
            ),
        )

        loaded = tracker.update(
            np.array([120.0, 140.0, 0.0, 0.0, 2.0, 0.0, 0.0, 0.01, 0.04], dtype=np.float32)
        )
        self.assertEqual(loaded.phase_label, "loading")
        self.assertFalse(loaded.success)
        self.assertIn("good_dig_start", loaded.step_successes)

        depositing = tracker.update(
            np.array([20.0, 140.0, 30.0, 12.0, 0.8, 0.0, 0.0, 0.8, 0.0], dtype=np.float32)
        )
        self.assertEqual(depositing.phase_label, "depositing")
        self.assertFalse(depositing.success)
        self.assertIn("deposit_progress", depositing.step_successes)

        retained = tracker.update(
            np.array([10.0, 140.0, 30.0, 12.0, 0.8, 0.0, 0.0, 0.8, 0.0], dtype=np.float32)
        )
        self.assertTrue(retained.success)
        self.assertEqual(retained.reward, 4.0)
        self.assertIn("mission_success", retained.step_successes)

    def test_reward_tracker_supports_dump_complete_success_mode(self) -> None:
        mission = get_agx_excavation_mission(
            "agx_excavation_teleop",
            success_mode="dump_complete_final_hold",
            success_mass_thresh=300.0,
            success_hold_steps=2,
            residual_bucket_mass_thresh=100.0,
        )
        tracker = AgxExcavationRewardTracker(
            mission=mission,
            env_state_order=(
                "mass_in_bucket_kg",
                "excavated_mass_kg",
                "mass_in_target_box_kg",
                "deposited_mass_in_target_box_kg",
                "min_distance_to_target_m",
                "target_hard_collision_count",
                "target_contact_max_normal_force_n",
                "min_distance_to_dig_area_m",
                "bucket_depth_below_dig_area_plane_m",
            ),
        )

        almost_done = tracker.update(
            np.array([180.0, 140.0, 500.0, 320.0, 0.8, 0.0, 0.0, 0.8, 0.0], dtype=np.float32)
        )
        self.assertFalse(almost_done.success)
        self.assertEqual(almost_done.metrics["success_condition_met"], 0.0)

        held_once = tracker.update(
            np.array([80.0, 140.0, 500.0, 320.0, 0.8, 0.0, 0.0, 0.8, 0.0], dtype=np.float32)
        )
        self.assertFalse(held_once.success)
        self.assertEqual(held_once.metrics["success_condition_met"], 1.0)

        held_twice = tracker.update(
            np.array([70.0, 140.0, 500.0, 320.0, 0.8, 0.0, 0.0, 0.8, 0.0], dtype=np.float32)
        )
        self.assertTrue(held_twice.success)
        self.assertEqual(held_twice.metrics["success_mode_is_dump_complete"], 1.0)

    def test_reward_tracker_blocks_load_progress_until_dig_area_good_start(self) -> None:
        mission = get_agx_excavation_mission("agx_excavation_teleop")
        tracker = AgxExcavationRewardTracker(
            mission=mission,
            env_state_order=(
                "mass_in_bucket_kg",
                "excavated_mass_kg",
                "mass_in_target_box_kg",
                "deposited_mass_in_target_box_kg",
                "min_distance_to_target_m",
                "target_hard_collision_count",
                "target_contact_max_normal_force_n",
                "min_distance_to_dig_area_m",
                "bucket_depth_below_dig_area_plane_m",
            ),
        )

        invalid_start = tracker.update(
            np.array([120.0, 130.0, 0.0, 0.0, 1.8, 0.0, 0.0, 0.20, 0.0], dtype=np.float32)
        )
        self.assertEqual(invalid_start.phase_label, "idle")
        self.assertEqual(invalid_start.reward, 0.0)
        self.assertIn("load_outside_dig_area", invalid_start.step_failures)
        self.assertNotIn("good_dig_start", invalid_start.step_successes)
        self.assertEqual(invalid_start.metrics["good_dig_started"], 0.0)

        valid_start = tracker.update(
            np.array([130.0, 140.0, 0.0, 0.0, 2.2, 0.0, 0.0, 0.01, 0.05], dtype=np.float32)
        )
        self.assertEqual(valid_start.phase_label, "loading")
        self.assertGreater(valid_start.reward, 0.0)
        self.assertIn("good_dig_start", valid_start.step_successes)
        self.assertEqual(valid_start.metrics["good_dig_started"], 1.0)

    def test_reward_tracker_dig_area_defaults_do_not_false_positive(self) -> None:
        mission = get_agx_excavation_mission("agx_excavation_teleop")
        tracker = AgxExcavationRewardTracker(
            mission=mission,
            env_state_order=(
                "mass_in_bucket_kg",
                "excavated_mass_kg",
                "mass_in_target_box_kg",
                "deposited_mass_in_target_box_kg",
                "min_distance_to_target_m",
                "target_hard_collision_count",
                "target_contact_max_normal_force_n",
                "min_distance_to_dig_area_m",
                "bucket_depth_below_dig_area_plane_m",
            ),
        )

        result = tracker.update(
            np.array([110.0, 130.0, 0.0, 0.0, 1.8, 0.0, 0.0, -1.0, 0.0], dtype=np.float32)
        )
        self.assertEqual(result.reward, 0.0)
        self.assertEqual(result.phase_label, "idle")
        self.assertIn("load_outside_dig_area", result.step_failures)
        self.assertNotIn("good_dig_start", result.step_successes)

    def test_reward_tracker_does_not_flag_spill_inside_valid_dump_geometry(self) -> None:
        mission = get_agx_excavation_mission(
            "agx_excavation_teleop",
            load_mass_threshold_kg=20.0,
            bucket_mass_delta_tol_kg=5.0,
            target_mass_delta_tol_kg=2.0,
        )
        env_state_order = (
            "mass_in_bucket_kg",
            "excavated_mass_kg",
            "mass_in_target_box_kg",
            "deposited_mass_in_target_box_kg",
            "min_distance_to_target_m",
            "target_hard_collision_count",
            "target_contact_max_normal_force_n",
            "min_distance_to_dig_area_m",
            "bucket_depth_below_dig_area_plane_m",
            "target_horizontal_distance_m",
            "bucket_height_above_target_rim_m",
            "bucket_over_target_footprint_mask",
            "dump_clearance_ok_mask",
            "bucket_dump_area_relative_x_m",
            "bucket_dump_area_relative_z_m",
            "bucket_dump_area_footprint_outside_distance_m",
        )

        tracker = AgxExcavationRewardTracker(
            mission=mission,
            env_state_order=env_state_order,
        )
        tracker.update(
            np.array(
                [
                    30.0,
                    30.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.01,
                    0.05,
                    0.0,
                    0.80,
                    1.0,
                    1.0,
                    0.0,
                    0.0,
                    0.0,
                ],
                dtype=np.float32,
            )
        )

        release_in_target = tracker.update(
            np.array(
                [
                    20.0,
                    30.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.30,
                    0.0,
                    0.0,
                    0.80,
                    1.0,
                    1.0,
                    0.0,
                    0.0,
                    0.0,
                ],
                dtype=np.float32,
            )
        )
        self.assertNotIn("spill_before_target", release_in_target.step_failures)
        self.assertEqual(release_in_target.metrics["dump_clearance_ok"], 1.0)

        tracker = AgxExcavationRewardTracker(
            mission=mission,
            env_state_order=env_state_order,
        )
        tracker.update(
            np.array(
                [
                    30.0,
                    30.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.01,
                    0.05,
                    0.50,
                    0.20,
                    0.0,
                    0.0,
                    0.8,
                    1.2,
                    0.5,
                ],
                dtype=np.float32,
            )
        )

        release_outside_target = tracker.update(
            np.array(
                [
                    20.0,
                    30.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.30,
                    0.0,
                    0.50,
                    0.20,
                    0.0,
                    0.0,
                    0.8,
                    1.2,
                    0.5,
                ],
                dtype=np.float32,
            )
        )
        self.assertIn("spill_before_target", release_outside_target.step_failures)

    def test_reward_tracker_defaults_missing_collision_signals_for_legacy_env_state(self) -> None:
        mission = get_agx_excavation_mission("agx_excavation_teleop")
        tracker = AgxExcavationRewardTracker(
            mission=mission,
            env_state_order=(
                "mass_in_bucket_kg",
                "excavated_mass_kg",
                "mass_in_target_box_kg",
                "deposited_mass_in_target_box_kg",
                "min_distance_to_target_m",
            ),
        )

        result = tracker.update(np.array([110.0, 130.0, 0.0, 0.0, 1.8], dtype=np.float32))
        self.assertEqual(result.metrics["target_hard_collision_count"], 0.0)
        self.assertEqual(result.metrics["target_contact_max_normal_force_n"], 0.0)
        self.assertNotIn("hard_target_collision", result.step_failures)

    def test_reward_tracker_ignores_subthreshold_collision_force(self) -> None:
        mission = get_agx_excavation_mission("agx_excavation_teleop")
        tracker = AgxExcavationRewardTracker(
            mission=mission,
            env_state_order=(
                "mass_in_bucket_kg",
                "excavated_mass_kg",
                "mass_in_target_box_kg",
                "deposited_mass_in_target_box_kg",
                "min_distance_to_target_m",
                "target_hard_collision_count",
                "target_contact_max_normal_force_n",
            ),
        )

        result = tracker.update(
            np.array([110.0, 130.0, 0.0, 0.0, 1.8, 0.0, 4200.0], dtype=np.float32)
        )
        self.assertEqual(result.metrics["target_hard_collision_count"], 0.0)
        self.assertEqual(result.metrics["target_contact_max_normal_force_n"], 4200.0)
        self.assertNotIn("hard_target_collision", result.step_failures)

    def test_reward_tracker_applies_hard_collision_penalty_only_on_count_increase(self) -> None:
        mission = get_agx_excavation_mission("agx_excavation_teleop")
        env_state_order = (
            "mass_in_bucket_kg",
            "excavated_mass_kg",
            "mass_in_target_box_kg",
            "deposited_mass_in_target_box_kg",
            "min_distance_to_target_m",
            "target_hard_collision_count",
            "target_contact_max_normal_force_n",
        )

        tracker_clean = AgxExcavationRewardTracker(mission=mission, env_state_order=env_state_order)
        clean = tracker_clean.update(
            np.array([120.0, 140.0, 0.0, 0.0, 1.5, 0.0, 0.0], dtype=np.float32)
        )

        tracker_collision = AgxExcavationRewardTracker(
            mission=mission,
            env_state_order=env_state_order,
        )
        collided = tracker_collision.update(
            np.array([120.0, 140.0, 0.0, 0.0, 1.5, 1.0, 6500.0], dtype=np.float32)
        )

        self.assertAlmostEqual(
            collided.reward,
            max(0.0, clean.reward - mission.hard_collision_penalty),
        )
        self.assertIn("hard_target_collision", collided.step_failures)
        self.assertEqual(collided.metrics["target_hard_collision_count"], 1.0)
        self.assertEqual(collided.metrics["target_contact_max_normal_force_n"], 6500.0)
        self.assertEqual(collided.metrics["delta_target_hard_collision_count"], 1.0)

        clean_next = tracker_clean.update(
            np.array([120.0, 140.0, 0.0, 0.0, 1.5, 0.0, 0.0], dtype=np.float32)
        )
        collided_next = tracker_collision.update(
            np.array([120.0, 140.0, 0.0, 0.0, 1.5, 1.0, 9200.0], dtype=np.float32)
        )

        self.assertAlmostEqual(collided_next.reward, clean_next.reward)
        self.assertNotIn("hard_target_collision", collided_next.step_failures)
        self.assertEqual(collided_next.metrics["target_hard_collision_count"], 1.0)
        self.assertEqual(collided_next.metrics["delta_target_hard_collision_count"], 0.0)
        self.assertEqual(collided_next.metrics["target_contact_max_normal_force_n"], 9200.0)


if __name__ == "__main__":
    unittest.main()
