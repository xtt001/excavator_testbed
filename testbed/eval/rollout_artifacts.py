"""Helpers for per-rollout metric summaries and log artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from testbed.eval.hybrid_metrics import build_hybrid_summary
from testbed.eval.multi_cycle_metrics import build_multicycle_summary
from testbed.eval.quality_metrics import build_quality_summary
from testbed.eval.rollout_logs import (
    build_rollout_summary,
    write_json,
    write_jsonl,
)


@dataclass(frozen=True)
class RolloutMetricSummaries:
    hybrid_summary: dict[str, Any]
    multicycle_summary: dict[str, Any]
    quality_summary: dict[str, Any]


def build_rollout_metric_summaries(
    *,
    step_records: list[dict[str, Any]],
    policy: Any,
    success_summary: dict[str, Any] | None,
) -> RolloutMetricSummaries:
    """Build metric summaries shared by saved and unsaved rollout-log paths."""
    hybrid_summary = build_hybrid_summary(step_records)
    if hasattr(policy, "rollout_summary"):
        hybrid_summary.update(dict(policy.rollout_summary()))
    multicycle_summary = build_multicycle_summary(
        step_records,
        success_summary=success_summary,
        hybrid_summary=hybrid_summary,
    )
    quality_summary = build_quality_summary(step_records)
    return RolloutMetricSummaries(
        hybrid_summary=hybrid_summary,
        multicycle_summary=multicycle_summary,
        quality_summary=quality_summary,
    )


def write_rollout_log_artifacts(
    *,
    rollout_log_dir: Path,
    rollout_id: int,
    success: bool,
    rewards: list[float],
    step_records: list[dict[str, Any]],
    video_path: str,
    hdf5_path: str,
    cell_entry_summary: dict[str, Any],
    success_summary: dict[str, Any] | None,
    continuity_summary: dict[str, Any],
    metric_summaries: RolloutMetricSummaries,
    target_gate_summary: dict[str, Any],
    planner_trace: dict[str, Any],
    rollout_stop_reason: str,
) -> dict[str, Any]:
    """Write JSONL, summary, and optional planner trace for one rollout."""
    summary = build_rollout_summary(
        rollout_id=rollout_id,
        success=success,
        rewards=rewards,
        step_records=step_records,
        video_path=video_path,
    )
    if hdf5_path:
        summary["hdf5_path"] = hdf5_path
    if cell_entry_summary:
        summary["cell_entry_summary"] = cell_entry_summary
    if success_summary is not None:
        summary.update(success_summary)
    summary.update(continuity_summary)
    if target_gate_summary:
        summary.update(target_gate_summary)
    summary.update(metric_summaries.multicycle_summary)
    summary.update(metric_summaries.hybrid_summary)
    summary.update(metric_summaries.quality_summary)
    summary["rollout_stop_reason"] = str(rollout_stop_reason)

    jsonl_path = rollout_log_dir / f"rollout_{rollout_id:03d}.jsonl"
    summary_path = rollout_log_dir / f"rollout_{rollout_id:03d}_summary.json"
    write_jsonl(jsonl_path, step_records)
    write_json(summary_path, summary)

    if planner_trace:
        planner_trace_path = rollout_log_dir / f"rollout_{rollout_id:03d}_planner_trace.json"
        write_json(planner_trace_path, planner_trace)
        summary["planner_trace_path"] = str(planner_trace_path)
    summary["jsonl_path"] = str(jsonl_path)
    summary["summary_path"] = str(summary_path)
    return summary
