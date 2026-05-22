"""
AGX Unity step-ack binary protocol client helpers.

Implements the wire format documented in:
  /home/pingfan/AGXUnityE85ExcavatorSim/Assets/AGXUnity_Excavator/Docs/protocol.md
"""

from __future__ import annotations

import io
import socket
import struct
import threading
import time
import zlib
from dataclasses import dataclass
from enum import IntEnum

import numpy as np


MAGIC = 0xA6A6A6A6
HEADER_VERSION = 1
HEADER_SIZE_BYTES = 16
MAX_PAYLOAD_BYTES = 128 * 1024 * 1024

IMAGE_PIXEL_FORMAT = "raw_rgb"
IMAGE_ROW_ORDER = "top_to_bottom"
PROTOCOL_VERSION = "agx-sim/v0"


class AgxProtocolError(RuntimeError):
    """Raised when the TCP frame or payload is malformed."""


class AgxServerError(RuntimeError):
    """Raised when Unity responds with success = false."""

    def __init__(self, error: str, warnings: tuple[str, ...] = ()) -> None:
        detail = error or "unknown_server_error"
        if warnings:
            detail = f"{detail} (warnings: {', '.join(warnings)})"
        super().__init__(detail)
        self.error = error
        self.warnings = warnings


class AgxConnectionClosedError(ConnectionError):
    """Raised when the Unity server closes the socket mid-frame."""


class MessageType(IntEnum):
    GET_INFO_REQ = 1
    GET_INFO_RESP = 2
    RESET_REQ = 3
    RESET_RESP = 4
    STEP_REQ = 5
    STEP_RESP = 6
    REALIGN_POSE_REQ = 7
    REALIGN_POSE_RESP = 8


@dataclass(frozen=True)
class CameraDescriptor:
    name: str
    width: int
    height: int
    fps: float
    pixel_format: str
    row_order: str


@dataclass(frozen=True)
class GetInfoResponse:
    success: bool
    error: str
    protocol_version: str
    dt: float
    control_hz: float
    action_semantics: str
    action_order: tuple[str, ...]
    qpos_order: tuple[str, ...]
    qvel_order: tuple[str, ...]
    env_state_order: tuple[str, ...]
    camera_names: tuple[str, ...]
    supports_reset_pose: bool
    supports_images: bool
    cameras: tuple[CameraDescriptor, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ResetResponse:
    success: bool
    error: str
    reset_applied: bool
    dt: float
    control_hz: float
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class StepResponse:
    success: bool
    error: str
    step_id: int
    qpos: np.ndarray
    qvel: np.ndarray
    env_state: np.ndarray
    image_format: str
    image_w: int
    image_h: int
    image_payload: bytes
    reward: float
    sim_time_ns: int
    warnings: tuple[str, ...]

    def decode_rgb_image(self) -> np.ndarray | None:
        if self.image_w == 0 or self.image_h == 0:
            if self.image_payload:
                raise AgxProtocolError(
                    "image dims are zero but payload is non-empty"
                )
            return None

        if self.image_format != IMAGE_PIXEL_FORMAT:
            raise AgxProtocolError(
                f"unsupported image_format {self.image_format!r}, "
                f"expected {IMAGE_PIXEL_FORMAT!r}"
            )

        expected_bytes = self.image_w * self.image_h * 3
        if len(self.image_payload) != expected_bytes:
            raise AgxProtocolError(
                "image payload size mismatch: "
                f"expected {expected_bytes}, got {len(self.image_payload)}"
            )

        return np.frombuffer(self.image_payload, dtype=np.uint8).reshape(
            self.image_h, self.image_w, 3
        )


class _PayloadReader:
    def __init__(self, payload: bytes) -> None:
        self._payload = memoryview(payload)
        self._offset = 0

    def _take(self, n_bytes: int) -> memoryview:
        end = self._offset + n_bytes
        if end > len(self._payload):
            raise AgxProtocolError("payload_truncated")
        data = self._payload[self._offset : end]
        self._offset = end
        return data

    def read_bool(self) -> bool:
        return bool(struct.unpack("<B", self._take(1))[0])

    def read_int32(self) -> int:
        return struct.unpack("<i", self._take(4))[0]

    def read_int64(self) -> int:
        return struct.unpack("<q", self._take(8))[0]

    def read_float32(self) -> float:
        return struct.unpack("<f", self._take(4))[0]

    def read_string(self) -> str:
        length = self.read_int32()
        if length < 0 or length > MAX_PAYLOAD_BYTES:
            raise AgxProtocolError("string_length_invalid")
        if length == 0:
            return ""
        return self._take(length).tobytes().decode("utf-8")

    def read_string_array(self) -> tuple[str, ...]:
        length = self.read_int32()
        if length < 0 or length > 1_000_000:
            raise AgxProtocolError("string_array_length_invalid")
        return tuple(self.read_string() for _ in range(length))

    def read_float_array(self) -> np.ndarray:
        length = self.read_int32()
        if length < 0 or length > 1_000_000:
            raise AgxProtocolError("float_array_length_invalid")
        if length == 0:
            return np.zeros(0, dtype=np.float32)
        byte_count = length * 4
        data = self._take(byte_count)
        return np.frombuffer(data, dtype="<f4").astype(np.float32, copy=True)

    def read_bytes(self) -> bytes:
        length = self.read_int32()
        if length < 0 or length > MAX_PAYLOAD_BYTES:
            raise AgxProtocolError("byte_array_length_invalid")
        return self._take(length).tobytes()

    def ensure_fully_consumed(self) -> None:
        if self._offset != len(self._payload):
            raise AgxProtocolError("payload_has_trailing_bytes")


def _pack_bool(value: bool) -> bytes:
    return struct.pack("<B", 1 if value else 0)


def _pack_string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack("<i", len(encoded)) + encoded


def _pack_string_array(values: list[str] | tuple[str, ...]) -> bytes:
    buf = io.BytesIO()
    buf.write(struct.pack("<i", len(values)))
    for value in values:
        buf.write(_pack_string(value))
    return buf.getvalue()


def _pack_float_array(values: np.ndarray | list[float] | tuple[float, ...]) -> bytes:
    arr = np.asarray(values, dtype=np.float32).reshape(-1)
    return struct.pack("<i", arr.size) + arr.astype("<f4", copy=False).tobytes()


def _pack_bytes(value: bytes) -> bytes:
    return struct.pack("<i", len(value)) + value


def crc32(payload: bytes) -> int:
    return zlib.crc32(payload) & 0xFFFFFFFF


def encode_frame(message_type: MessageType, payload: bytes = b"") -> bytes:
    if len(payload) > MAX_PAYLOAD_BYTES:
        raise ValueError(f"payload exceeds {MAX_PAYLOAD_BYTES} bytes")
    return struct.pack(
        "<IHHII",
        MAGIC,
        HEADER_VERSION,
        int(message_type),
        len(payload),
        crc32(payload),
    ) + payload


def encode_get_info_request() -> bytes:
    return encode_frame(MessageType.GET_INFO_REQ)


def encode_reset_request(
    *,
    seed: int = 0,
    reset_terrain: bool = True,
    reset_pose: bool = True,
    client_time_ns: int | None = None,
    scenario_id: str | None = None,
) -> bytes:
    payload = io.BytesIO()
    payload.write(struct.pack("<i", int(seed)))
    payload.write(_pack_bool(reset_terrain))
    payload.write(_pack_bool(reset_pose))
    if client_time_ns is not None or scenario_id is not None:
        client_time = client_time_ns if client_time_ns is not None else -1
        payload.write(struct.pack("<q", int(client_time)))
    if scenario_id is not None:
        payload.write(_pack_string(scenario_id))
    return encode_frame(MessageType.RESET_REQ, payload.getvalue())


def encode_step_request(
    step_id: int,
    action: np.ndarray | list[float] | tuple[float, ...],
    *,
    client_time_ns: int | None = None,
    planner_debug_json: str | None = None,
) -> bytes:
    payload = io.BytesIO()
    payload.write(struct.pack("<q", int(step_id)))
    payload.write(_pack_float_array(action))
    if client_time_ns is not None or planner_debug_json is not None:
        payload.write(
            struct.pack(
                "<q",
                int(client_time_ns if client_time_ns is not None else -1),
            )
        )
    if planner_debug_json is not None:
        payload.write(_pack_string(str(planner_debug_json)))
    return encode_frame(MessageType.STEP_REQ, payload.getvalue())


def encode_realign_pose_request(
    step_id: int,
    qpos: np.ndarray | list[float] | tuple[float, ...],
    *,
    qvel: np.ndarray | list[float] | tuple[float, ...] | None = None,
    burn_in_steps: int = 0,
    client_time_ns: int | None = None,
    reason: str | None = None,
) -> bytes:
    payload = io.BytesIO()
    payload.write(struct.pack("<q", int(step_id)))
    payload.write(_pack_float_array(qpos))
    payload.write(_pack_float_array([] if qvel is None else qvel))
    payload.write(struct.pack("<i", int(burn_in_steps)))
    payload.write(
        struct.pack(
            "<q",
            int(client_time_ns if client_time_ns is not None else -1),
        )
    )
    payload.write(_pack_string("" if reason is None else str(reason)))
    return encode_frame(MessageType.REALIGN_POSE_REQ, payload.getvalue())


def _read_exact(sock: socket.socket, n_bytes: int) -> bytes:
    chunks: list[bytes] = []
    remaining = n_bytes
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise AgxConnectionClosedError("socket closed while reading frame")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_frame(sock: socket.socket) -> tuple[MessageType, bytes]:
    header = _read_exact(sock, HEADER_SIZE_BYTES)
    magic, version, raw_message_type, payload_len, expected_crc = struct.unpack(
        "<IHHII", header
    )
    if magic != MAGIC:
        raise AgxProtocolError(f"invalid magic 0x{magic:08X}")
    if version != HEADER_VERSION:
        raise AgxProtocolError(f"unsupported header version {version}")
    if payload_len > MAX_PAYLOAD_BYTES:
        raise AgxProtocolError(f"payload_too_large:{payload_len}")

    try:
        message_type = MessageType(raw_message_type)
    except ValueError as exc:
        raise AgxProtocolError(f"unknown message type {raw_message_type}") from exc

    payload = _read_exact(sock, payload_len) if payload_len else b""
    actual_crc = crc32(payload)
    if actual_crc != expected_crc:
        raise AgxProtocolError(
            f"crc_mismatch: expected 0x{expected_crc:08X}, got 0x{actual_crc:08X}"
        )
    return message_type, payload


def _parse_common_prefix(reader: _PayloadReader) -> tuple[bool, str]:
    return reader.read_bool(), reader.read_string()


def decode_get_info_response(payload: bytes) -> GetInfoResponse:
    reader = _PayloadReader(payload)
    success, error = _parse_common_prefix(reader)
    protocol_version = reader.read_string()
    dt = reader.read_float32()
    control_hz = reader.read_float32()
    action_semantics = reader.read_string()
    action_order = reader.read_string_array()
    qpos_order = reader.read_string_array()
    qvel_order = reader.read_string_array()
    env_state_order = reader.read_string_array()
    camera_names = reader.read_string_array()
    supports_reset_pose = reader.read_bool()
    supports_images = reader.read_bool()

    camera_count = reader.read_int32()
    if camera_count < 0 or camera_count > 1024:
        raise AgxProtocolError("camera_descriptor_count_invalid")
    cameras = []
    for _ in range(camera_count):
        cameras.append(
            CameraDescriptor(
                name=reader.read_string(),
                width=reader.read_int32(),
                height=reader.read_int32(),
                fps=reader.read_float32(),
                pixel_format=reader.read_string(),
                row_order=reader.read_string(),
            )
        )

    warnings = reader.read_string_array()
    reader.ensure_fully_consumed()

    return GetInfoResponse(
        success=success,
        error=error,
        protocol_version=protocol_version,
        dt=dt,
        control_hz=control_hz,
        action_semantics=action_semantics,
        action_order=action_order,
        qpos_order=qpos_order,
        qvel_order=qvel_order,
        env_state_order=env_state_order,
        camera_names=camera_names,
        supports_reset_pose=supports_reset_pose,
        supports_images=supports_images,
        cameras=tuple(cameras),
        warnings=warnings,
    )


def decode_reset_response(payload: bytes) -> ResetResponse:
    reader = _PayloadReader(payload)
    success, error = _parse_common_prefix(reader)
    reset_applied = reader.read_bool()
    dt = reader.read_float32()
    control_hz = reader.read_float32()
    warnings = reader.read_string_array()
    reader.ensure_fully_consumed()
    return ResetResponse(
        success=success,
        error=error,
        reset_applied=reset_applied,
        dt=dt,
        control_hz=control_hz,
        warnings=warnings,
    )


def decode_step_response(payload: bytes) -> StepResponse:
    reader = _PayloadReader(payload)
    success, error = _parse_common_prefix(reader)
    step_id = reader.read_int64()
    qpos = reader.read_float_array()
    qvel = reader.read_float_array()
    env_state = reader.read_float_array()
    image_format = reader.read_string()
    image_w = reader.read_int32()
    image_h = reader.read_int32()
    image_payload = reader.read_bytes()
    reward = reader.read_float32()
    sim_time_ns = reader.read_int64()
    warnings = reader.read_string_array()
    reader.ensure_fully_consumed()
    return StepResponse(
        success=success,
        error=error,
        step_id=step_id,
        qpos=qpos,
        qvel=qvel,
        env_state=env_state,
        image_format=image_format,
        image_w=image_w,
        image_h=image_h,
        image_payload=image_payload,
        reward=reward,
        sim_time_ns=sim_time_ns,
        warnings=warnings,
    )


class AgxSimClient:
    """Small synchronous client for the Unity AGX step-ack server."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 5057,
        *,
        timeout_s: float = 5.0,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout_s = timeout_s
        self._socket: socket.socket | None = None
        self._lock = threading.Lock()

    def connect(self) -> None:
        if self._socket is not None:
            return
        sock = socket.create_connection((self.host, self.port), timeout=self.timeout_s)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.settimeout(self.timeout_s)
        self._socket = sock

    def close(self) -> None:
        if self._socket is None:
            return
        try:
            self._socket.close()
        finally:
            self._socket = None

    def __enter__(self) -> "AgxSimClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def get_info(self) -> GetInfoResponse:
        response = self._roundtrip(
            encode_get_info_request(),
            expected=MessageType.GET_INFO_RESP,
        )
        parsed = decode_get_info_response(response)
        if not parsed.success:
            raise AgxServerError(parsed.error, parsed.warnings)
        return parsed

    def reset(
        self,
        *,
        seed: int = 0,
        reset_terrain: bool = True,
        reset_pose: bool = True,
        scenario_id: str | None = None,
    ) -> ResetResponse:
        response = self._roundtrip(
            encode_reset_request(
                seed=seed,
                reset_terrain=reset_terrain,
                reset_pose=reset_pose,
                client_time_ns=time.time_ns(),
                scenario_id=scenario_id,
            ),
            expected=MessageType.RESET_RESP,
        )
        parsed = decode_reset_response(response)
        if not parsed.success:
            raise AgxServerError(parsed.error, parsed.warnings)
        return parsed

    def step(
        self,
        step_id: int,
        action: np.ndarray | list[float] | tuple[float, ...],
        *,
        planner_debug_json: str | None = None,
    ) -> StepResponse:
        action_arr = np.asarray(action, dtype=np.float32).reshape(-1)
        if action_arr.size < 4:
            raise ValueError(
                "AGX Unity backend expects at least 4 action values, "
                f"got {action_arr.size}"
            )
        response = self._roundtrip(
            encode_step_request(
                step_id=step_id,
                action=action_arr,
                client_time_ns=time.time_ns(),
                planner_debug_json=planner_debug_json,
            ),
            expected=MessageType.STEP_RESP,
        )
        parsed = decode_step_response(response)
        if not parsed.success:
            raise AgxServerError(parsed.error, parsed.warnings)
        if parsed.step_id != int(step_id):
            raise AgxProtocolError(
                f"step_id mismatch: requested {step_id}, received {parsed.step_id}"
            )
        return parsed

    def realign_pose(
        self,
        step_id: int,
        qpos: np.ndarray | list[float] | tuple[float, ...],
        *,
        qvel: np.ndarray | list[float] | tuple[float, ...] | None = None,
        burn_in_steps: int = 0,
        reason: str | None = None,
    ) -> StepResponse:
        qpos_arr = np.asarray(qpos, dtype=np.float32).reshape(-1)
        if qpos_arr.size < 4:
            raise ValueError(
                "AGX Unity backend expects at least 4 qpos values, "
                f"got {qpos_arr.size}"
            )
        qvel_arr = None if qvel is None else np.asarray(qvel, dtype=np.float32).reshape(-1)
        response = self._roundtrip(
            encode_realign_pose_request(
                step_id=step_id,
                qpos=qpos_arr,
                qvel=qvel_arr,
                burn_in_steps=int(burn_in_steps),
                client_time_ns=time.time_ns(),
                reason=reason,
            ),
            expected=MessageType.REALIGN_POSE_RESP,
        )
        parsed = decode_step_response(response)
        if not parsed.success:
            raise AgxServerError(parsed.error, parsed.warnings)
        if parsed.step_id != int(step_id):
            raise AgxProtocolError(
                f"step_id mismatch: requested {step_id}, received {parsed.step_id}"
            )
        return parsed

    def _roundtrip(self, request_frame: bytes, *, expected: MessageType) -> bytes:
        self.connect()
        assert self._socket is not None
        with self._lock:
            try:
                self._socket.sendall(request_frame)
                response_type, payload = read_frame(self._socket)
                if response_type != expected:
                    response_type, payload = read_frame(self._socket)
            except Exception:
                self.close()
                raise
        if response_type != expected:
            raise AgxProtocolError(
                f"unexpected response type {response_type.name}, expected {expected.name}"
            )
        return payload
