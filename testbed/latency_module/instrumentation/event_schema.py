"""
Event name constants and LogEntry schema for the latency instrumentation module.

Event naming convention:
    <chain>_<event>
    chain: ctrl | video | feedback
    event: e.g. send, recv, apply, render ...

Each LogEntry maps to one JSONL line in the trace file.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


# ── Control-link events ───────────────────────────────────────────────────────
EVT_CMD_INPUT  = "cmd_input"   # action computed by policy / operator
EVT_CMD_SEND   = "cmd_send"    # STEP_REQ bytes queued to socket
EVT_CMD_RECV   = "cmd_recv"    # STEP_RESP bytes fully received
EVT_CMD_APPLY  = "cmd_apply"   # Unity sim_time stamp inside STEP_RESP

# ── Unity-side breakdown events (timestamps carried inside STEP_RESP) ─────────
EVT_UNITY_REQ_RECV     = "unity_req_recv"     # TCP thread: STEP_REQ fully read
EVT_UNITY_QUEUE_EXIT   = "unity_queue_exit"   # Update thread: dequeued
EVT_UNITY_PHYSICS_DONE = "unity_physics_done" # After DoStep()
EVT_UNITY_IMAGE_READY  = "unity_image_ready"  # After Collect() / image captured
EVT_UNITY_RESP_QUEUED  = "unity_resp_queued"  # Serialised, about to TCP-send

# ── Video-link events (carried inside the same STEP_RESP as the control link) ─
EVT_FRAME_RECV   = "frame_recv"    # image bytes received (same ts as cmd_recv)
EVT_FRAME_RENDER = "frame_render"  # image written / displayed (if tracked)

# ── Closed-loop feedback events ───────────────────────────────────────────────
EVT_STATE_FEEDBACK_READY = "state_feedback_ready"   # obs dict built from resp
EVT_STATE_FEEDBACK_SEND  = "state_feedback_send"    # obs handed to policy/op
EVT_STATE_FEEDBACK_RECV  = "state_feedback_recv"    # alias for cmd_recv in sync loop

# ── Session lifecycle events ──────────────────────────────────────────────────
EVT_SESSION_START = "session_start"
EVT_SESSION_END   = "session_end"
EVT_EPISODE_START = "episode_start"
EVT_EPISODE_END   = "episode_end"


@dataclass
class LogEntry:
    """One structured event record written as a single JSONL line."""

    # ── Mandatory ─────────────────────────────────────────────────────────────
    timestamp_ns: int           # wall-clock nanoseconds (time.time_ns())
    event_name:   str

    # ── Trace context ─────────────────────────────────────────────────────────
    run_id:    str = ""
    trace_id:  str = ""         # unique per top-level experiment run (same as run_id usually)
    episode_id: str = ""
    cmd_id:    int = -1         # monotonic step counter within an episode
    frame_id:  int = -1         # same as cmd_id for the synchronous step-ack loop

    # ── Video stream config snapshot (filled at session start / on change) ────
    resolution: str = ""        # e.g. "1920x1080"
    fps:        float = 0.0
    bitrate:    int   = 0       # kbps
    codec:      str = ""        # e.g. "raw_rgb", "h264"

    # ── Network condition snapshot ────────────────────────────────────────────
    delay_inject_ms:  float = 0.0
    jitter_inject_ms: float = 0.0
    loss_rate:        float = 0.0

    # ── Unity sim context ─────────────────────────────────────────────────────
    sim_time_ns: int = -1       # Unity simulation clock (from StepResponse)
    step_id:     int = -1       # protocol-level step_id echoed by Unity

    # ── Computed latency fields (filled post-hoc or inline) ──────────────────
    round_trip_ms: float = -1.0     # cmd_send → cmd_recv in ms
    payload_bytes: int   = -1       # image payload size in bytes

    # ── Unity-side breakdown (filled from StepResponse timestamps) ────────────
    # All in ms relative to t_cmd_send, so they're directly comparable.
    # -1 means the Unity build does not support this field yet.
    seg_py_to_unity_ms:  float = -1.0  # cmd_send → unity_req_recv  (STEP_REQ network + queue)
    seg_queue_wait_ms:   float = -1.0  # unity_req_recv → unity_queue_exit  (Update tick wait)
    seg_physics_ms:      float = -1.0  # unity_queue_exit → unity_physics_done  (DoStep)
    seg_image_ms:        float = -1.0  # unity_physics_done → unity_image_ready  (Collect)
    seg_serialize_ms:    float = -1.0  # unity_image_ready → unity_resp_queued  (serialization)
    seg_unity_to_py_ms:  float = -1.0  # unity_resp_queued → cmd_recv  (STEP_RESP network)

    # ── Catch-all for extra fields ────────────────────────────────────────────
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Flatten extra into top-level for easier jq / pandas queries
        extra = d.pop("extra", {}) or {}
        d.update(extra)
        return d
