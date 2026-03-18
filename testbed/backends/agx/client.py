"""
AGXSimClient — TCP socket client implementing the V0 step-ack protocol.

Thread safety: NOT thread-safe. Use from a single thread only.

Usage
-----
    client = AGXSimClient("192.168.1.100", 9000)
    client.connect()
    info  = client.get_info()
    resp  = client.reset(ResetReq(reset_terrain=True, reset_pose=True))
    sresp = client.step(StepReq(step_id=0, action=np.zeros(4)))
    client.close()
"""

from __future__ import annotations

import logging
import socket
import time

import numpy as np

from testbed.backends.agx.protocol import (
    HEADER_SIZE,
    GetInfoResp,
    ImageFormat,
    MsgType,
    ProtocolError,
    ResetReq,
    ResetResp,
    StepReq,
    StepResp,
    pack_get_info_req,
    pack_reset_req,
    pack_step_req,
    unpack_get_info_resp,
    unpack_header,
    unpack_reset_resp,
    unpack_step_resp,
)

log = logging.getLogger(__name__)


class AGXSimClient:
    """
    Low-level TCP client for the AGXUnity simulation bridge.

    Parameters
    ----------
    host        Unity machine hostname or IP.
    port        Listening port on the Unity side.
    timeout     Socket receive timeout in seconds.
    recv_buf    Socket receive buffer size (bytes).  Increase for large images.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9000,
        timeout: float = 10.0,
        recv_buf: int = 8 * 1024 * 1024,  # 8 MB — enough for 1080p raw RGB
    ) -> None:
        self.host     = host
        self.port     = port
        self.timeout  = timeout
        self.recv_buf = recv_buf
        self._sock: socket.socket | None = None

    # ─── Connection management ────────────────────────────────────────────────

    def connect(self) -> None:
        """Open TCP connection to AGXUnity bridge."""
        log.info("Connecting to AGX at %s:%d …", self.host, self.port)
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self.recv_buf)
        self._sock.settimeout(self.timeout)
        self._sock.connect((self.host, self.port))
        log.info("Connected.")

    def close(self) -> None:
        """Close the TCP connection."""
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
            log.info("Disconnected from AGX.")

    def __enter__(self) -> "AGXSimClient":
        self.connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ─── High-level API ───────────────────────────────────────────────────────

    def get_info(self) -> GetInfoResp:
        """Query simulation capabilities (one-time handshake)."""
        self._send_raw(pack_get_info_req())
        msg_type, payload = self._recv_msg()
        if msg_type != MsgType.GET_INFO_RESP:
            raise ProtocolError(f"Expected GET_INFO_RESP, got {msg_type}")
        resp = unpack_get_info_resp(payload)
        log.info("GET_INFO: %s", resp.raw)
        return resp

    def reset(self, req: ResetReq | None = None) -> ResetResp:
        """Reset the simulation. Returns confirmation + dt/control_hz."""
        if req is None:
            req = ResetReq()
        self._send_raw(pack_reset_req(req))
        msg_type, payload = self._recv_msg()
        if msg_type != MsgType.RESET_RESP:
            raise ProtocolError(f"Expected RESET_RESP, got {msg_type}")
        resp = unpack_reset_resp(payload)
        if not resp.success:
            raise RuntimeError("AGX RESET_RESP reported failure (success=0)")
        log.debug("RESET ok: dt=%.4f ctrl_hz=%.1f warn=0x%x",
                  resp.dt, resp.control_hz, resp.warning_flags)
        return resp

    def step(self, req: StepReq) -> StepResp:
        """
        Send STEP_REQ and block until matching STEP_RESP arrives.

        Enforces the step-ack contract:
            STEP_RESP.step_id must equal STEP_REQ.step_id.

        Raises
        ------
        ProtocolError  if step_id in response doesn't match.
        """
        self._send_raw(pack_step_req(req))
        msg_type, payload = self._recv_msg()
        if msg_type != MsgType.STEP_RESP:
            raise ProtocolError(f"Expected STEP_RESP, got {msg_type}")
        resp = unpack_step_resp(payload)
        if resp.step_id != req.step_id:
            raise ProtocolError(
                f"step_id mismatch: sent {req.step_id}, got {resp.step_id}"
            )
        return resp

    # ─── Transport helpers ────────────────────────────────────────────────────

    def _send_raw(self, data: bytes) -> None:
        """Send all bytes, handling partial writes."""
        if self._sock is None:
            raise RuntimeError("AGXSimClient: not connected")
        total = 0
        view = memoryview(data)
        while total < len(data):
            sent = self._sock.send(view[total:])
            if sent == 0:
                raise ConnectionResetError("AGX socket closed during send")
            total += sent

    def _recv_exact(self, n: int) -> bytes:
        """Receive exactly n bytes (blocks until done or timeout)."""
        if self._sock is None:
            raise RuntimeError("AGXSimClient: not connected")
        chunks: list[bytes] = []
        received = 0
        while received < n:
            chunk = self._sock.recv(n - received)
            if not chunk:
                raise ConnectionResetError(
                    f"AGX socket closed after {received}/{n} bytes"
                )
            chunks.append(chunk)
            received += len(chunk)
        return b"".join(chunks)

    def _recv_msg(self) -> tuple[MsgType, bytes]:
        """Read one framed message: header then payload."""
        header_bytes = self._recv_exact(HEADER_SIZE)
        msg_type, payload_len, _crc = unpack_header(header_bytes)
        payload = self._recv_exact(payload_len) if payload_len > 0 else b""
        return msg_type, payload
