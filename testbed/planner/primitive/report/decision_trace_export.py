"""Eval-facing export adapters for primitive decision trace records."""

from __future__ import annotations

from testbed.planner.primitive.report.decision_trace import DecisionTraceRecord


class DecisionTraceExportAdapter:
    """Pure adapter boundary for online compact and rich trace dictionaries."""

    @staticmethod
    def to_online_compact_trace(
        record: DecisionTraceRecord | None,
    ) -> dict[str, object] | None:
        if record is None:
            return None
        return record.to_compact_dict()

    @staticmethod
    def to_offline_rich_trace(
        record: DecisionTraceRecord | None,
    ) -> dict[str, object] | None:
        if record is None:
            return None
        return record.to_rich_dict()


def to_online_compact_trace(
    record: DecisionTraceRecord | None,
) -> dict[str, object] | None:
    """Return the bounded per-tick trace dictionary for online consumers."""

    return DecisionTraceExportAdapter.to_online_compact_trace(record)


def to_offline_rich_trace(
    record: DecisionTraceRecord | None,
) -> dict[str, object] | None:
    """Return the rich JSON-compatible trace dictionary for replay consumers."""

    return DecisionTraceExportAdapter.to_offline_rich_trace(record)


__all__ = [
    "DecisionTraceExportAdapter",
    "to_offline_rich_trace",
    "to_online_compact_trace",
]
