"""
LatencySession: high-level context manager that wires together
IDManager + TraceLogger + ControlProbe into a single easy-to-use object.

Usage
-----
    # In record_teleop.py main() — only a few lines to add:

    from testbed.latency_module import LatencySession

    session = LatencySession.from_config(cfg)   # cfg is the full teleop YAML dict
    session.open()
    session.start_run()

    backend._client = session.attach_probe(backend._client)  # one-liner hook

    for episode_idx in range(num_episodes):
        session.start_episode(episode_idx)
        ts = backend.reset(seed=ep_seed)

        for step in range(max_steps):
            # Normal teleop loop — timing logged automatically by probe
            action_info = action_source.next_action(ts.observation)
            session.log_cmd_input(action_info)   # optional: log operator input ts
            ts = backend.step(action)            # ← probe intercepts here

        session.end_episode(success=episode_success)

    session.close()   # auto-exports summary + plots if configured

    # --- OR use as a context manager ---
    with LatencySession.from_config(cfg) as session:
        session.start_run()
        ...
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from testbed.latency_module.instrumentation.event_schema import (
    EVT_SESSION_START,
    EVT_SESSION_END,
    EVT_EPISODE_START,
    EVT_EPISODE_END,
    EVT_CMD_INPUT,
    LogEntry,
)
from testbed.latency_module.instrumentation.id_manager import IDManager
from testbed.latency_module.instrumentation.trace_logger import TraceLogger
from testbed.latency_module.probes.control_probe import ControlProbe


class LatencySession:
    """
    Orchestrates one teleoperation session's latency instrumentation.

    Parameters
    ----------
    enabled        Master switch.  All methods are no-ops if False.
    output_dir     Root directory for trace outputs.
    run_id         Override run ID (auto-generated if empty).
    network_config Dict with delay_inject_ms / jitter_inject_ms / loss_rate.
    stream_config  Dict with resolution / fps / bitrate / codec.
    auto_export    If True, call export_run_summary() on close().
    """

    def __init__(
        self,
        *,
        enabled: bool = True,
        output_dir: str | Path = "outputs",
        run_id: str = "",
        network_config: dict | None = None,
        stream_config: dict | None = None,
        auto_export: bool = True,
    ) -> None:
        self._enabled     = enabled
        self._output_dir  = Path(output_dir)
        self._run_id_hint = run_id
        self._net         = dict(network_config or {})
        self._stream      = dict(stream_config  or {})
        self._auto_export = auto_export

        self._ids    = IDManager()
        self._logger = TraceLogger.disabled()
        self._probe: ControlProbe | None = None
        self._patched_clients: list[Any] = []

    # ── Factory ───────────────────────────────────────────────────────────────

    @classmethod
    def from_config(cls, cfg: dict) -> "LatencySession":
        """
        Build a LatencySession from the full teleop YAML config dict.

        Reads from cfg['latency']:
            enabled, output_dir, run_id,
            network.{delay_inject_ms, jitter_inject_ms, loss_rate},
            stream.{resolution, fps, bitrate, codec},
            analysis.auto_export_on_close
        """
        lat_cfg = cfg.get("latency", {})
        enabled  = bool(lat_cfg.get("enabled", False))
        out_dir  = str(lat_cfg.get("output_dir", "outputs"))
        run_id   = str(lat_cfg.get("run_id", ""))
        net_cfg  = dict(lat_cfg.get("network", {}))
        stream_cfg = dict(lat_cfg.get("stream", {}))
        auto_exp = bool(lat_cfg.get("analysis", {}).get("auto_export_on_close", True))
        return cls(
            enabled       = enabled,
            output_dir    = out_dir,
            run_id        = run_id,
            network_config = net_cfg,
            stream_config  = stream_cfg,
            auto_export   = auto_exp,
        )

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def open(self) -> "LatencySession":
        """Initialise IDs and open the trace file."""
        if not self._enabled:
            return self
        run_id = self._ids.new_run(self._run_id_hint or None)
        self._logger = TraceLogger(
            output_dir=self._output_dir,
            run_id=run_id,
            enabled=True,
        )
        self._logger.open()
        return self

    def close(self) -> None:
        """Flush trace, detach probes, optionally export summary."""
        if not self._enabled:
            return

        # Log session end
        self._logger.log(
            EVT_SESSION_END,
            **self._ids.snapshot(),
        )
        self._logger.close()

        # Detach any patched clients
        for client in self._patched_clients:
            ControlProbe.detach(client)
        self._patched_clients.clear()

        # Auto-export
        if self._auto_export and self._logger.trace_path:
            try:
                from testbed.latency_module.analysis.export_summary import export_run_summary
                export_run_summary(self._logger.trace_path.parent)
            except Exception as exc:
                print(f"  [LatencySession] auto-export failed: {exc}")

    def __enter__(self) -> "LatencySession":
        return self.open()

    def __exit__(self, *_: Any) -> None:
        self.close()

    # ── Run / episode helpers ─────────────────────────────────────────────────

    def start_run(self) -> None:
        """Log session_start event (call after open())."""
        if not self._enabled:
            return
        self._logger.log(
            EVT_SESSION_START,
            **self._ids.snapshot(),
            extra={"network": self._net, "stream": self._stream},
        )

    def start_episode(self, episode_idx: int | None = None) -> str:
        """Increment episode ID and log episode_start."""
        if not self._enabled:
            return ""
        ep_id = self._ids.new_episode(episode_idx)
        self._logger.log(EVT_EPISODE_START, **self._ids.snapshot())
        return ep_id

    def end_episode(self, *, success: bool = False) -> None:
        """Log episode_end with outcome."""
        if not self._enabled:
            return
        self._logger.log(
            EVT_EPISODE_END,
            **self._ids.snapshot(),
            extra={"success": success},
        )

    # ── Probe attachment ──────────────────────────────────────────────────────

    def attach_probe(self, client: Any) -> Any:
        """
        Monkey-patch client.step() with timing instrumentation.

        Returns the same client object (modified in-place).
        Call this once after backend.get_info() and before the episode loop.
        """
        if not self._enabled:
            return client
        self._probe = ControlProbe.attach(
            client,
            logger = self._logger,
            ids    = self._ids,
            network_config = self._net,
            stream_config  = self._stream,
        )
        self._patched_clients.append(client)
        return client

    # ── Optional inline logging ───────────────────────────────────────────────

    def log_cmd_input(self, action_or_info: Any = None) -> None:
        """
        Log the moment the operator's action is computed.

        Called just before backend.step() in the teleop loop.
        """
        if not self._enabled:
            return
        self._logger.log(
            EVT_CMD_INPUT,
            timestamp_ns = time.time_ns(),
            **self._ids.snapshot(),
            cmd_id   = self._ids.cmd_id,
            frame_id = self._ids.frame_id,
            **self._net,
        )

    # ── Properties ───────────────────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def ids(self) -> IDManager:
        return self._ids

    @property
    def logger(self) -> TraceLogger:
        return self._logger

    @property
    def trace_path(self) -> Path | None:
        return self._logger.trace_path
