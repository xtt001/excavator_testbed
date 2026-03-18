"""
AGXUnity ↔ Python socket protocol (V0).

Wire format — all multi-byte fields are LITTLE-ENDIAN.

Header (16 bytes):
  uint32  magic        = 0xA6A6A6A6
  uint16  version      = 1
  uint16  msg_type     (MsgType enum)
  uint32  payload_len  (bytes that follow the header)
  uint32  crc32        (0 = not checked in V0)

Payloads
────────
GET_INFO_REQ  → empty (payload_len = 0)
GET_INFO_RESP → UTF-8 JSON string (variable length)

RESET_REQ (12 + N bytes):
  int32   seed              (-1 = unused)
  uint8   reset_terrain
  uint8   reset_pose
  uint8   _pad[2]
  uint32  scenario_id_len   (N, 0 if no scenario_id)
  char[]  scenario_id       (UTF-8, no null terminator)

RESET_RESP (16 bytes):
  uint8   success           (1 = ok)
  uint8   _pad[3]
  float32 dt
  float32 control_hz
  uint32  warning_flags     (0 = none)

STEP_REQ (32 bytes):
  int64   step_id
  float32 action[4]         (swing, boom, stick, bucket speed cmd)
  int64   client_time_ns    (0 = unused)

STEP_RESP (variable):
  int64   step_id
  float32 qpos[3]           (boom, stick, bucket position_norm)
  float32 qvel[4]           (swing, boom, stick, bucket speed)
  uint32  env_state_len     (M, number of float32 values)
  float32 env_state[M]
  float32 reward
  uint8   image_format      (ImageFormat enum)
  uint8   _pad[3]
  int32   image_w
  int32   image_h
  uint32  image_payload_len (K)
  uint8   image_payload[K]
"""

from __future__ import annotations

import json
import struct
import zlib
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

import numpy as np

# ─── Constants ───────────────────────────────────────────────────────────────

MAGIC:   int = 0xA6A6A6A6
VERSION: int = 1

# V0 vector dimensions (locked — bump version to change)
ACTION_DIM = 4   # [swing, boom, stick, bucket]
QPOS_DIM   = 3   # [boom, stick, bucket] position_norm
QVEL_DIM   = 4   # [swing, boom, stick, bucket] speed

# ─── Enums ───────────────────────────────────────────────────────────────────

class MsgType(IntEnum):
    GET_INFO_REQ  = 1
    GET_INFO_RESP = 2
    RESET_REQ     = 3
    RESET_RESP    = 4
    STEP_REQ      = 5
    STEP_RESP     = 6


class ImageFormat(IntEnum):
    NONE    = 0
    RAW_RGB = 1
    H264    = 2


# ─── Struct format strings (little-endian) ───────────────────────────────────

_HEADER_FMT  = "<IHHII"          # magic, version, msg_type, payload_len, crc32
HEADER_SIZE  = struct.calcsize(_HEADER_FMT)   # 16 bytes

_RESET_REQ_FIXED_FMT  = "<iBBxxI"       # seed(4), terrain(1), pose(1), pad(2), sid_len(4)
_RESET_REQ_FIXED_SIZE = struct.calcsize(_RESET_REQ_FIXED_FMT)  # 12 bytes

_RESET_RESP_FMT  = "<BxxxffI"      # success(1), pad(3), dt(4), ctrl_hz(4), warn(4)
_RESET_RESP_SIZE = struct.calcsize(_RESET_RESP_FMT)  # 16 bytes

_STEP_REQ_FMT  = "<qffffq"        # step_id(8), action[4](16), client_ns(8)
_STEP_REQ_SIZE = struct.calcsize(_STEP_REQ_FMT)  # 32 bytes

_STEP_RESP_FIXED_FMT  = "<qfffffffI"  # step_id(8), qpos[3](12), qvel[4](16), env_len(4)
_STEP_RESP_FIXED_SIZE = struct.calcsize(_STEP_RESP_FIXED_FMT)  # 40 bytes

_STEP_RESP_TAIL_FMT  = "<fBxxxiiI"   # reward(4), img_fmt(1), pad(3), w(4), h(4), img_len(4)
_STEP_RESP_TAIL_SIZE = struct.calcsize(_STEP_RESP_TAIL_FMT)  # 20 bytes


# ─── Dataclasses ─────────────────────────────────────────────────────────────

@dataclass
class ResetReq:
    seed:           int  = -1
    reset_terrain:  bool = True
    reset_pose:     bool = True
    scenario_id:    str  = ""


@dataclass
class ResetResp:
    success:       bool
    dt:            float
    control_hz:    float
    warning_flags: int = 0


@dataclass
class StepReq:
    step_id:        int
    action:         np.ndarray         # shape (4,) float32
    client_time_ns: int = 0


@dataclass
class StepResp:
    step_id:    int
    qpos:       np.ndarray             # shape (3,) float32
    qvel:       np.ndarray             # shape (4,) float32
    env_state:  np.ndarray             # shape (M,) float32
    reward:     float
    image:      np.ndarray | None      # (H, W, 3) uint8 or None
    image_fmt:  ImageFormat = ImageFormat.RAW_RGB


@dataclass
class GetInfoResp:
    raw: dict[str, Any] = field(default_factory=dict)


# ─── Header pack / unpack ────────────────────────────────────────────────────

def pack_header(msg_type: MsgType, payload: bytes, check_crc: bool = False) -> bytes:
    crc = zlib.crc32(payload) & 0xFFFFFFFF if check_crc else 0
    return struct.pack(_HEADER_FMT, MAGIC, VERSION, int(msg_type), len(payload), crc)


def unpack_header(data: bytes) -> tuple[MsgType, int, int]:
    """Returns (msg_type, payload_len, crc32)."""
    magic, version, msg_type, payload_len, crc = struct.unpack(_HEADER_FMT, data)
    if magic != MAGIC:
        raise ProtocolError(f"Bad magic: 0x{magic:08X}")
    if version != VERSION:
        raise ProtocolError(f"Unsupported version: {version}")
    return MsgType(msg_type), payload_len, crc


# ─── Message pack ────────────────────────────────────────────────────────────

def pack_get_info_req() -> bytes:
    payload = b""
    return pack_header(MsgType.GET_INFO_REQ, payload) + payload


def pack_reset_req(req: ResetReq) -> bytes:
    sid = req.scenario_id.encode("utf-8")
    payload = struct.pack(
        _RESET_REQ_FIXED_FMT,
        req.seed,
        int(req.reset_terrain),
        int(req.reset_pose),
        len(sid),
    ) + sid
    return pack_header(MsgType.RESET_REQ, payload) + payload


def pack_step_req(req: StepReq) -> bytes:
    a = req.action.astype(np.float32)
    payload = struct.pack(
        _STEP_REQ_FMT,
        req.step_id,
        float(a[0]), float(a[1]), float(a[2]), float(a[3]),
        req.client_time_ns,
    )
    return pack_header(MsgType.STEP_REQ, payload) + payload


# ─── Message unpack ──────────────────────────────────────────────────────────

def unpack_get_info_resp(payload: bytes) -> GetInfoResp:
    try:
        raw = json.loads(payload.decode("utf-8"))
    except Exception as exc:
        raise ProtocolError(f"GET_INFO_RESP JSON parse failed: {exc}") from exc
    return GetInfoResp(raw=raw)


def unpack_reset_resp(payload: bytes) -> ResetResp:
    if len(payload) < _RESET_RESP_SIZE:
        raise ProtocolError(
            f"RESET_RESP too short: {len(payload)} < {_RESET_RESP_SIZE}"
        )
    success, dt, control_hz, warning_flags = struct.unpack_from(_RESET_RESP_FMT, payload)
    return ResetResp(
        success=bool(success),
        dt=dt,
        control_hz=control_hz,
        warning_flags=warning_flags,
    )


def unpack_step_resp(payload: bytes) -> StepResp:
    if len(payload) < _STEP_RESP_FIXED_SIZE:
        raise ProtocolError(
            f"STEP_RESP too short for fixed header: {len(payload)} < {_STEP_RESP_FIXED_SIZE}"
        )
    offset = 0
    vals = struct.unpack_from(_STEP_RESP_FIXED_FMT, payload, offset)
    step_id   = vals[0]
    qpos      = np.array(vals[1:4],  dtype=np.float32)
    qvel      = np.array(vals[4:8],  dtype=np.float32)
    env_len   = vals[8]
    offset   += _STEP_RESP_FIXED_SIZE

    # env_state (variable)
    env_bytes = env_len * 4
    if len(payload) < offset + env_bytes + _STEP_RESP_TAIL_SIZE:
        raise ProtocolError("STEP_RESP too short for env_state + tail")
    env_state = np.frombuffer(payload[offset:offset + env_bytes], dtype="<f4").copy()
    offset   += env_bytes

    # tail
    reward, img_fmt_raw, img_w, img_h, img_payload_len = struct.unpack_from(
        _STEP_RESP_TAIL_FMT, payload, offset
    )
    offset += _STEP_RESP_TAIL_SIZE

    img_fmt = ImageFormat(img_fmt_raw)

    # image payload (variable)
    image: np.ndarray | None = None
    if img_fmt != ImageFormat.NONE and img_payload_len > 0:
        if len(payload) < offset + img_payload_len:
            raise ProtocolError("STEP_RESP truncated image payload")
        raw_bytes = payload[offset:offset + img_payload_len]
        if img_fmt == ImageFormat.RAW_RGB:
            image = np.frombuffer(raw_bytes, dtype=np.uint8).reshape(
                img_h, img_w, 3
            ).copy()
        # H264 would be decoded here in V1

    return StepResp(
        step_id=step_id,
        qpos=qpos,
        qvel=qvel,
        env_state=env_state,
        reward=float(reward),
        image=image,
        image_fmt=img_fmt,
    )


# ─── Error ───────────────────────────────────────────────────────────────────

class ProtocolError(Exception):
    """Raised when a message violates the AGX protocol spec."""
