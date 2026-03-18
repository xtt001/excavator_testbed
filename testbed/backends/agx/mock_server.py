"""
Mock AGX server — speaks the full V0 socket protocol.

Run this on the Python machine to test the full pipeline without Unity:

    python -m testbed.backends.agx.mock_server          # default port 9000
    python -m testbed.backends.agx.mock_server --port 9001
    python -m testbed.backends.agx.mock_server --chaos  # inject random delays

Then run the client as normal:
    tb-record-teleop --config testbed/configs/teleop_v0.yaml

Behaviour
─────────
• GET_INFO_REQ  → responds with a JSON capabilities object
• RESET_REQ     → resets internal state, responds ok
• STEP_REQ      → advances a simple sine-wave kinematic sim, echoes step_id,
                  returns random-walk qpos/qvel, synthetic env_state
                  (mass_in_bucket slowly ramps up), and a solid-colour fpv frame
                  that changes hue each step so you can visually confirm frames arrive.

Synthetic mass_in_bucket
  Starts at 0.  Ramps linearly to 2.0 over the first 200 steps, then holds.
  This lets you verify the evaluator success rule fires correctly.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import random
import socket
import struct
import threading
import time

import numpy as np

from testbed.backends.agx.protocol import (
    HEADER_SIZE,
    MAGIC,
    VERSION,
    ACTION_DIM,
    QPOS_DIM,
    QVEL_DIM,
    ImageFormat,
    MsgType,
    pack_header,
    unpack_header,
    _RESET_REQ_FIXED_FMT,
    _RESET_REQ_FIXED_SIZE,
    _STEP_REQ_FMT,
)

log = logging.getLogger(__name__)

# ── Configurable defaults ────────────────────────────────────────────────────
DEFAULT_PORT    = 9000
IMAGE_W         = 320
IMAGE_H         = 240
CONTROL_HZ      = 50.0
DT              = 1.0 / CONTROL_HZ
ENV_STATE_DIM   = 2          # [mass_in_bucket, dummy]
MASS_RAMP_STEPS = 200        # steps to ramp from 0→2.0


# ─── Server ───────────────────────────────────────────────────────────────────

class MockAGXServer:
    def __init__(self, host: str = "0.0.0.0", port: int = DEFAULT_PORT,
                 chaos: bool = False, send_images: bool = True):
        self.host         = host
        self.port         = port
        self.chaos        = chaos
        self.send_images  = send_images
        self._sock        = None

    def serve_forever(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.listen(1)
        log.info("Mock AGX server listening on %s:%d", self.host, self.port)

        while True:
            conn, addr = self._sock.accept()
            log.info("Client connected: %s", addr)
            t = threading.Thread(
                target=self._handle_client, args=(conn,), daemon=True
            )
            t.start()

    def _handle_client(self, conn: socket.socket) -> None:
        state = _SimState()
        try:
            while True:
                # Read header
                header = _recv_exact(conn, HEADER_SIZE)
                msg_type, payload_len, _ = unpack_header(header)
                payload = _recv_exact(conn, payload_len) if payload_len > 0 else b""

                if self.chaos:
                    time.sleep(random.uniform(0, 0.005))

                if msg_type == MsgType.GET_INFO_REQ:
                    resp = self._handle_get_info()
                elif msg_type == MsgType.RESET_REQ:
                    resp = self._handle_reset(payload, state)
                elif msg_type == MsgType.STEP_REQ:
                    resp = self._handle_step(payload, state)
                else:
                    log.warning("Unknown msg_type %s — ignoring", msg_type)
                    continue

                conn.sendall(resp)
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            log.info("Client disconnected.")
        except Exception as exc:
            log.exception("Handler error: %s", exc)
        finally:
            conn.close()

    # ── Message handlers ──────────────────────────────────────────────────────

    def _handle_get_info(self) -> bytes:
        info = {
            "protocol_version": 1,
            "dt":               DT,
            "control_hz":       CONTROL_HZ,
            "action_semantics": "actuator_speed_cmd",
            "action_dim":       ACTION_DIM,
            "action_order":     ["swing", "boom", "stick", "bucket"],
            "qpos_dim":         QPOS_DIM,
            "qpos_order":       ["boom_pos_norm", "stick_pos_norm", "bucket_pos_norm"],
            "qvel_dim":         QVEL_DIM,
            "qvel_order":       ["swing_speed", "boom_speed", "stick_speed", "bucket_speed"],
            "cameras":          [{"name": "fpv", "width": IMAGE_W, "height": IMAGE_H,
                                  "fps": CONTROL_HZ, "format": "raw_rgb"}],
            "env_state_dim":    ENV_STATE_DIM,
            "env_state_layout": {
                "mass_in_bucket": 0,
                "dummy":          1,
            },
            "mock": True,
        }
        payload = json.dumps(info).encode("utf-8")
        return pack_header(MsgType.GET_INFO_RESP, payload) + payload

    def _handle_reset(self, payload: bytes, state: "_SimState") -> bytes:
        # Parse RESET_REQ (ignore fields, just reset state)
        state.reset()
        log.info("RESET  step_counter=0")

        # RESET_RESP: success(1), pad(3), dt(4), ctrl_hz(4), warn(4)
        resp_payload = struct.pack("<BxxxffI", 1, DT, CONTROL_HZ, 0)
        return pack_header(MsgType.RESET_RESP, resp_payload) + resp_payload

    def _handle_step(self, payload: bytes, state: "_SimState") -> bytes:
        # Parse STEP_REQ
        step_id, s, bo, st, bu, client_ns = struct.unpack(_STEP_REQ_FMT, payload)
        action = np.array([s, bo, st, bu], dtype=np.float32)

        # Advance kinematics
        state.step(action)

        qpos      = state.qpos
        qvel      = state.qvel
        env_state = state.env_state

        # Build image payload
        if self.send_images:
            frame    = _make_color_frame(state.step_count, IMAGE_H, IMAGE_W)
            img_data = frame.tobytes()
            img_fmt  = ImageFormat.RAW_RGB
        else:
            img_data = b""
            img_fmt  = ImageFormat.NONE

        # Build STEP_RESP payload
        # Fixed header: step_id(8) qpos[3](12) qvel[4](16) env_len(4) = 40 bytes
        fixed = struct.pack(
            "<qfffffffI",
            step_id,
            qpos[0], qpos[1], qpos[2],
            qvel[0], qvel[1], qvel[2], qvel[3],
            len(env_state),
        )
        # env_state floats
        env_bytes = struct.pack(f"<{len(env_state)}f", *env_state)
        # tail: reward(4) img_fmt(1) pad(3) w(4) h(4) img_len(4)
        tail = struct.pack(
            "<fBxxxiiI",
            0.0,           # reward (computed in evaluator)
            int(img_fmt),
            IMAGE_W if img_data else 0,
            IMAGE_H if img_data else 0,
            len(img_data),
        )
        resp_payload = fixed + env_bytes + tail + img_data
        return pack_header(MsgType.STEP_RESP, resp_payload) + resp_payload


# ─── Synthetic simulation state ───────────────────────────────────────────────

class _SimState:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.step_count = 0
        # qpos: [boom, stick, bucket] in [0, 1]
        self._pos = np.array([0.5, 0.5, 0.5], dtype=np.float32)
        # qvel: [swing, boom, stick, bucket]
        self._vel = np.zeros(4, dtype=np.float32)

    def step(self, action: np.ndarray) -> None:
        """Simple Euler integration with clamped positions."""
        self._vel = np.clip(action * 0.1, -0.1, 0.1).astype(np.float32)
        # qvel[1:4] correspond to boom/stick/bucket → integrate qpos
        self._pos += self._vel[1:] * DT
        self._pos  = np.clip(self._pos, 0.0, 1.0)
        self.step_count += 1

    @property
    def qpos(self) -> np.ndarray:
        return self._pos.copy()

    @property
    def qvel(self) -> np.ndarray:
        return self._vel.copy()

    @property
    def env_state(self) -> np.ndarray:
        # mass_in_bucket ramps linearly from 0 to 2.0 over MASS_RAMP_STEPS
        mass = min(2.0, 2.0 * self.step_count / max(1, MASS_RAMP_STEPS))
        return np.array([mass, 0.0], dtype=np.float32)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _recv_exact(conn: socket.socket, n: int) -> bytes:
    chunks = []
    received = 0
    while received < n:
        chunk = conn.recv(n - received)
        if not chunk:
            raise ConnectionResetError(f"Socket closed after {received}/{n} bytes")
        chunks.append(chunk)
        received += len(chunk)
    return b"".join(chunks)


def _make_color_frame(step: int, h: int, w: int) -> np.ndarray:
    """Return a solid-colour (H,W,3) uint8 frame that rotates through hue."""
    import colorsys
    hue   = (step * 3) % 360 / 360.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.8, 0.9)
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:, :] = (int(r * 255), int(g * 255), int(b * 255))
    return frame


# ─── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    parser = argparse.ArgumentParser(description="Mock AGX server for offline testing.")
    parser.add_argument("--port",    type=int,  default=DEFAULT_PORT)
    parser.add_argument("--host",    type=str,  default="0.0.0.0")
    parser.add_argument("--chaos",   action="store_true",
                        help="Add random delays to test client timeout handling.")
    parser.add_argument("--no-images", action="store_true",
                        help="Disable image payload (faster, for protocol-only tests).")
    args = parser.parse_args()

    server = MockAGXServer(
        host=args.host,
        port=args.port,
        chaos=args.chaos,
        send_images=not args.no_images,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
