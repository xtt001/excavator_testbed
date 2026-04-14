"""
IDManager: centralized tracking ID provider for the latency module.

Provides:
    run_id      — unique string per top-level experiment run (UUID4 prefix)
    trace_id    — alias for run_id (one trace file per run)
    episode_id  — "episode_N" string, reset on each new episode
    cmd_id      — monotonic int per step within the current episode
    frame_id    — same as cmd_id (video and control are in the same step-ack)
"""

from __future__ import annotations

import threading
import time
import uuid


class IDManager:
    """
    Lightweight, thread-safe ID manager.

    Usage
    -----
        ids = IDManager()
        ids.new_run()
        ids.new_episode(0)
        cmd_id = ids.next_cmd()
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._run_id   = ""
        self._trace_id = ""
        self._episode_id = ""
        self._cmd_counter = 0
        self._episode_counter = 0

    # ── Run / session ─────────────────────────────────────────────────────────

    def new_run(self, run_id: str | None = None) -> str:
        """
        Start a new run.  Generates a short UUID-based ID if not provided.
        Resets episode and cmd counters.
        """
        with self._lock:
            if run_id is None:
                ts = time.strftime("%Y%m%d_%H%M%S")
                short_uuid = uuid.uuid4().hex[:6]
                run_id = f"run_{ts}_{short_uuid}"
            self._run_id   = run_id
            self._trace_id = run_id
            self._episode_id = ""
            self._cmd_counter = 0
            self._episode_counter = 0
        return run_id

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def trace_id(self) -> str:
        return self._trace_id

    # ── Episode ───────────────────────────────────────────────────────────────

    def new_episode(self, episode_idx: int | None = None) -> str:
        """
        Start a new episode.  Resets cmd counter.
        """
        with self._lock:
            if episode_idx is None:
                episode_idx = self._episode_counter
            self._episode_id  = f"episode_{episode_idx}"
            self._episode_counter = episode_idx + 1
            self._cmd_counter = 0
        return self._episode_id

    @property
    def episode_id(self) -> str:
        return self._episode_id

    # ── Step / command ────────────────────────────────────────────────────────

    def next_cmd(self) -> int:
        """Increment and return the current cmd_id (= frame_id)."""
        with self._lock:
            cid = self._cmd_counter
            self._cmd_counter += 1
        return cid

    @property
    def cmd_id(self) -> int:
        """Current cmd_id without incrementing."""
        return self._cmd_counter

    @property
    def frame_id(self) -> int:
        """Alias for cmd_id (video and control share the same step-ack)."""
        return self._cmd_counter

    # ── Convenience snapshot ─────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Return current IDs as a dict for embedding in LogEntry."""
        with self._lock:
            return {
                "run_id":     self._run_id,
                "trace_id":   self._trace_id,
                "episode_id": self._episode_id,
            }
