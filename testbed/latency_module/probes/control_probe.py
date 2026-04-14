"""
ControlProbe: zero-invasive wrapper around AgxSimClient that instruments
the control / video / feedback link timing.

How it works
------------
The AGX step-ack protocol uses a synchronous request-response loop:

    [Python]  STEP_REQ  ──────────►  [Unity]
                                       │  sim executes, captures image
    [Python]  STEP_RESP  ◄─────────   │

One round-trip carries:
  • the control command (sent)
  • the joint state + image observation (received)

We therefore instrument a *single* socket round-trip to extract:

  cmd_send_ns      time.time_ns() just before socket.sendall()
  cmd_recv_ns      time.time_ns() just after  read_frame() returns
  round_trip_ms    (cmd_recv_ns - cmd_send_ns) / 1e6
  sim_time_ns      Unity's simulation clock from StepResponse (cmd_apply proxy)
  payload_bytes    raw image payload size in bytes

Usage
-----
Wrap an existing AgxSimClient (or AgxSimBackend) before the episode loop:

    probe = ControlProbe(client=backend._client, logger=logger, ids=ids)
    # OR wrap the whole backend at a higher level:
    with ControlProbe.attach(backend, logger=logger, ids=ids):
        backend.step(action)   # timing logged automatically

Or as a standalone drop-in replacement for AgxSimClient:

    probe = ControlProbe.from_client(client, logger=logger, ids=ids)
    probe.step(step_id, action)
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np

from testbed.latency_module.instrumentation.event_schema import (
    EVT_CMD_SEND,
    EVT_CMD_RECV,
    EVT_CMD_APPLY,
    EVT_FRAME_RECV,
    EVT_STATE_FEEDBACK_READY,
    EVT_UNITY_REQ_RECV,
    EVT_UNITY_QUEUE_EXIT,
    EVT_UNITY_PHYSICS_DONE,
    EVT_UNITY_IMAGE_READY,
    EVT_UNITY_RESP_QUEUED,
    LogEntry,
)
from testbed.latency_module.instrumentation.id_manager import IDManager
from testbed.latency_module.instrumentation.trace_logger import TraceLogger


class ControlProbe:
    """
    Instruments a single AGX step() call.

    This class is intentionally *not* a full proxy of AgxSimClient —
    callers should keep a reference to the original client for all non-step
    operations (get_info, reset, close).  Only step() is intercepted.

    Parameters
    ----------
    client   The AgxSimClient instance to wrap.
    logger   TraceLogger to write events to.
    ids      IDManager that provides run_id / episode_id / cmd_id context.
    network_config  Optional dict with delay_inject_ms / jitter_inject_ms /
                    loss_rate (filled from tc netem config for reproducibility).
    stream_config   Optional dict with resolution / fps / bitrate / codec.
    """

    def __init__(
        self,
        client: Any,
        logger: TraceLogger,
        ids: IDManager,
        *,
        network_config: dict | None = None,
        stream_config: dict | None = None,
    ) -> None:
        self._client = client
        self._logger = logger
        self._ids    = ids
        self._net    = dict(network_config or {})
        self._stream = dict(stream_config or {})

    # ── Main instrumented step ────────────────────────────────────────────────

    def step(
        self,
        step_id: int,
        action: np.ndarray | list[float] | tuple[float, ...],
    ):
        """
        Instrument one step() call around the original client.

        Returns the original StepResponse unchanged.
        """
        from testbed.backends.agx.protocol import (
            encode_step_request,
            read_frame,
            decode_step_response,
            MessageType,
            AgxProtocolError,
        )

        ids    = self._ids
        logger = self._logger
        net    = self._net
        stream = self._stream

        action_arr = np.asarray(action, dtype=np.float32).reshape(-1)

        # ── Common context fields ─────────────────────────────────────────────
        cmd_id = ids.next_cmd()
        ctx = dict(
            run_id     = ids.run_id,
            trace_id   = ids.trace_id,
            episode_id = ids.episode_id,
            cmd_id     = cmd_id,
            frame_id   = cmd_id,
            step_id    = int(step_id),
            delay_inject_ms  = float(net.get("delay_inject_ms",  0.0)),
            jitter_inject_ms = float(net.get("jitter_inject_ms", 0.0)),
            loss_rate        = float(net.get("loss_rate",         0.0)),
            resolution = str(stream.get("resolution", "")),
            fps        = float(stream.get("fps",       0.0)),
            bitrate    = int(stream.get("bitrate",     0)),
            codec      = str(stream.get("codec",       "")),
        )

        # ── Delegate to the real client.step() but with timing hooks ─────────
        # We re-implement the critical path of AgxSimClient.step() here
        # so we can insert probes at the right places without patching the
        # original source.

        client_time_ns_before_encode = time.time_ns()
        request_frame = encode_step_request(
            step_id,
            action_arr,
            client_time_ns=client_time_ns_before_encode,
        )

        # cmd_send: just before bytes hit the wire
        t_send = time.time_ns()
        logger.log(EVT_CMD_SEND, timestamp_ns=t_send, **ctx)

        # --- wire round-trip (delegates to client's internal _roundtrip) ------
        # We call the *original* client._roundtrip() to reuse its lock/socket
        # management.  This means our send timestamp is slightly before actual
        # sendall(), but the error is sub-millisecond.
        with self._client._lock:
            try:
                sock = self._client._socket
                if sock is None:
                    self._client.connect()
                    sock = self._client._socket
                sock.sendall(request_frame)
                t_sent = time.time_ns()   # more accurate send timestamp
                response_type, payload = read_frame(sock)
            except Exception:
                self._client.close()
                raise

        t_recv = time.time_ns()

        # ── Validate response type ─────────────────────────────────────────
        if response_type != MessageType.STEP_RESP:
            raise AgxProtocolError(
                f"unexpected response type {response_type.name}, expected STEP_RESP"
            )

        resp = decode_step_response(payload)

        if not resp.success:
            from testbed.backends.agx.protocol import AgxServerError
            raise AgxServerError(resp.error, resp.warnings)

        if resp.step_id != int(step_id):
            raise AgxProtocolError(
                f"step_id mismatch: requested {step_id}, received {resp.step_id}"
            )

        # ── Round-trip latency ────────────────────────────────────────────────
        round_trip_ms = (t_recv - t_sent) / 1e6
        payload_bytes = len(resp.image_payload)

        # ── Compute per-segment breakdowns from Unity timestamps ──────────────
        # All segments in ms, computed relative to t_sent (Python cmd_send).
        # If Unity timestamps are -1, segment values stay -1.
        def _delta_ms(t_unity_ns: int, t_ref_ns: int) -> float:
            if t_unity_ns < 0 or t_ref_ns < 0:
                return -1.0
            return (t_unity_ns - t_ref_ns) / 1e6

        seg_py_to_unity_ms  = _delta_ms(resp.t_req_recv_ns,     t_sent)
        seg_queue_wait_ms   = _delta_ms(resp.t_queue_exit_ns,   resp.t_req_recv_ns)
        seg_physics_ms      = _delta_ms(resp.t_physics_done_ns, resp.t_queue_exit_ns)
        seg_image_ms        = _delta_ms(resp.t_image_ready_ns,  resp.t_physics_done_ns)
        seg_serialize_ms    = _delta_ms(resp.t_resp_queued_ns,  resp.t_image_ready_ns)
        seg_unity_to_py_ms  = _delta_ms(t_recv,                 resp.t_resp_queued_ns)

        breakdown = dict(
            seg_py_to_unity_ms  = seg_py_to_unity_ms,
            seg_queue_wait_ms   = seg_queue_wait_ms,
            seg_physics_ms      = seg_physics_ms,
            seg_image_ms        = seg_image_ms,
            seg_serialize_ms    = seg_serialize_ms,
            seg_unity_to_py_ms  = seg_unity_to_py_ms,
        )

        # cmd_recv: full STEP_RESP received — main latency record
        logger.log(
            EVT_CMD_RECV,
            timestamp_ns  = t_recv,
            round_trip_ms = round_trip_ms,
            payload_bytes = payload_bytes,
            **breakdown,
            **ctx,
        )

        # cmd_apply: Unity-side simulation time (different clock, delta only)
        logger.log(
            EVT_CMD_APPLY,
            timestamp_ns  = t_recv,
            sim_time_ns   = int(resp.sim_time_ns),
            round_trip_ms = round_trip_ms,
            **ctx,
        )

        # Unity-side breakdown events (only if timestamps available)
        if resp.t_req_recv_ns > 0:
            logger.log(EVT_UNITY_REQ_RECV,     timestamp_ns=resp.t_req_recv_ns,     **ctx)
        if resp.t_queue_exit_ns > 0:
            logger.log(EVT_UNITY_QUEUE_EXIT,   timestamp_ns=resp.t_queue_exit_ns,
                       seg_queue_wait_ms=seg_queue_wait_ms, **ctx)
        if resp.t_physics_done_ns > 0:
            logger.log(EVT_UNITY_PHYSICS_DONE, timestamp_ns=resp.t_physics_done_ns,
                       seg_physics_ms=seg_physics_ms, **ctx)
        if resp.t_image_ready_ns > 0:
            logger.log(EVT_UNITY_IMAGE_READY,  timestamp_ns=resp.t_image_ready_ns,
                       seg_image_ms=seg_image_ms, **ctx)
        if resp.t_resp_queued_ns > 0:
            logger.log(EVT_UNITY_RESP_QUEUED,  timestamp_ns=resp.t_resp_queued_ns,
                       seg_serialize_ms=seg_serialize_ms, **ctx)

        # frame_recv: image data arrived
        if payload_bytes > 0:
            logger.log(
                EVT_FRAME_RECV,
                timestamp_ns  = t_recv,
                payload_bytes = payload_bytes,
                round_trip_ms = round_trip_ms,
                extra = {"image_w": resp.image_w, "image_h": resp.image_h},
                **ctx,
            )

        # state_feedback_ready: obs immediately available after decode
        logger.log(
            EVT_STATE_FEEDBACK_READY,
            timestamp_ns  = t_recv,
            round_trip_ms = round_trip_ms,
            **ctx,
        )

        return resp

    # ── Convenience: patch an existing AgxSimClient in-place ─────────────────

    @classmethod
    def attach(
        cls,
        client: Any,
        logger: TraceLogger,
        ids: IDManager,
        **kwargs: Any,
    ) -> "ControlProbe":
        """
        Build a ControlProbe and monkey-patch client.step with it.

        The original step() is saved as client._original_step so it can be
        restored by detach().
        """
        probe = cls(client=client, logger=logger, ids=ids, **kwargs)
        client._original_step = client.step
        client.step = probe.step
        return probe

    @staticmethod
    def detach(client: Any) -> None:
        """Restore the original step() on a previously patched client."""
        if hasattr(client, "_original_step"):
            client.step = client._original_step
            del client._original_step
