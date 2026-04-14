"""
TraceLogger: thread-safe JSONL writer for the latency instrumentation module.

Design
------
- One JSONL file per run, written to outputs/<run_id>/trace.jsonl.
- Each call to log_event() appends one JSON line immediately (no buffering).
- Disabled by default; enable by calling open() or using as a context manager.
- All public methods are no-ops when disabled, so callers need no guard logic.

Usage
-----
    logger = TraceLogger(output_dir=Path("outputs"), run_id="run_20240101_abc123")
    logger.open()
    logger.log_event(LogEntry(
        timestamp_ns=time.time_ns(),
        event_name=EVT_CMD_SEND,
        run_id=ids.run_id,
        cmd_id=cmd_id,
    ))
    logger.close()

    # Or as context manager:
    with TraceLogger(output_dir=Path("outputs"), run_id=ids.run_id) as logger:
        ...
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from testbed.latency_module.instrumentation.event_schema import LogEntry


class TraceLogger:
    """
    Append-only JSONL trace writer.

    Parameters
    ----------
    output_dir  Root output directory.  A subdirectory <run_id>/ is created
                inside it.  Set to None to run in dry-run (no-op) mode.
    run_id      Identifies this run; also used as the subdirectory name.
    enabled     Master on/off switch.  If False, all methods are no-ops.
    """

    def __init__(
        self,
        output_dir: Path | str | None = None,
        run_id: str = "",
        *,
        enabled: bool = True,
    ) -> None:
        self._output_dir = Path(output_dir) if output_dir else None
        self._run_id     = run_id
        self._enabled    = enabled and (output_dir is not None)
        self._file       = None
        self._lock       = threading.Lock()
        self._trace_path: Path | None = None
        self._event_count = 0

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def open(self) -> "TraceLogger":
        if not self._enabled:
            return self
        run_dir = self._output_dir / self._run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        self._trace_path = run_dir / "trace.jsonl"
        self._file = open(self._trace_path, "a", encoding="utf-8")  # noqa: WPS515
        return self

    def close(self) -> None:
        if self._file is not None:
            self._file.flush()
            self._file.close()
            self._file = None

    def __enter__(self) -> "TraceLogger":
        return self.open()

    def __exit__(self, *_: Any) -> None:
        self.close()

    # ── Logging ───────────────────────────────────────────────────────────────

    def log_event(self, entry: LogEntry) -> None:
        """Append one LogEntry as a JSON line.  Thread-safe no-op when disabled."""
        if not self._enabled or self._file is None:
            return
        line = json.dumps(entry.to_dict(), ensure_ascii=False)
        with self._lock:
            self._file.write(line + "\n")
            self._event_count += 1

    def log(
        self,
        event_name: str,
        *,
        timestamp_ns: int | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Convenience wrapper: build a LogEntry from keyword args and log it.

        All LogEntry fields can be passed as kwargs.
        Any unrecognised kwargs go into LogEntry.extra.
        """
        if not self._enabled or self._file is None:
            return

        ts = timestamp_ns if timestamp_ns is not None else time.time_ns()
        known_fields = LogEntry.__dataclass_fields__.keys()
        entry_kwargs: dict[str, Any] = {"timestamp_ns": ts, "event_name": event_name}
        extra: dict[str, Any] = {}
        for k, v in kwargs.items():
            if k in known_fields:
                entry_kwargs[k] = v
            else:
                extra[k] = v
        if extra:
            entry_kwargs["extra"] = extra
        self.log_event(LogEntry(**entry_kwargs))

    # ── Properties ───────────────────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def trace_path(self) -> Path | None:
        return self._trace_path

    @property
    def event_count(self) -> int:
        return self._event_count

    # ── Factory ───────────────────────────────────────────────────────────────

    @classmethod
    def disabled(cls) -> "TraceLogger":
        """Return a no-op logger (useful as a default argument)."""
        return cls(output_dir=None, enabled=False)
