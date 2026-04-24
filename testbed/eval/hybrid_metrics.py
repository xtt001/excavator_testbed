"""Helpers for Stage-2 hybrid rollout summaries and aggregate metrics."""

from __future__ import annotations

from typing import Any

import numpy as np


def build_hybrid_summary(step_records: list[dict[str, Any]]) -> dict[str, float | int | str]:
    hybrid_rows = [
        row
        for row in step_records
        if str(row.get("hybrid_mode", "")).strip() != ""
    ]
    if not hybrid_rows:
        return {}

    transition_rows = [row for row in hybrid_rows if row.get("hybrid_mode") == "TRANSITION"]
    transition_timeout_count = int(sum(bool(row.get("transition_timeout", False)) for row in hybrid_rows))
    completed_rows = [
        row for row in hybrid_rows if bool(row.get("transition_completed", False))
    ]
    transition_collision_delta_total = int(
        sum(int(row.get("transition_collision_delta", 0)) for row in completed_rows)
        + sum(
            int(row.get("transition_collision_delta", 0))
            for row in hybrid_rows
            if bool(row.get("transition_timeout", False))
        )
    )
    transition_collision_rate = (
        float(transition_collision_delta_total) / float(len(transition_rows))
        if transition_rows else 0.0
    )

    return {
        "transition_source": str(hybrid_rows[-1].get("transition_source", "")),
        "transition_policy_mode": str(hybrid_rows[-1].get("transition_policy_mode", "")),
        "transition_timeout_count": transition_timeout_count,
        "transition_collision_rate": float(transition_collision_rate),
        "avg_corridor_align_steps": (
            float(np.mean([float(row.get("corridor_align_steps", 0)) for row in completed_rows]))
            if completed_rows else 0.0
        ),
        "avg_wait_next_dig_steps": (
            float(np.mean([float(row.get("wait_next_dig_steps", 0)) for row in completed_rows]))
            if completed_rows else 0.0
        ),
        "completed_transition_count": int(len(completed_rows)),
        "transition_fallback_count": int(
            max(int(row.get("transition_fallback_count", 0)) for row in hybrid_rows)
        ),
        "transition_fallback_reason": str(
            next(
                (
                    str(row.get("transition_fallback_reason", ""))
                    for row in reversed(hybrid_rows)
                    if str(row.get("transition_fallback_reason", "")).strip() != ""
                ),
                "",
            )
        ),
    }


def aggregate_hybrid_metrics(
    summaries: list[dict[str, float | int | str]],
) -> dict[str, float | int | str]:
    valid = [summary for summary in summaries if summary]
    if not valid:
        return {}

    numeric_keys = [
        "transition_timeout_count",
        "transition_collision_rate",
        "avg_corridor_align_steps",
        "avg_wait_next_dig_steps",
        "completed_transition_count",
    ]
    result: dict[str, float | int | str] = {
        "transition_source": str(valid[-1].get("transition_source", "")),
        "transition_policy_mode": str(valid[-1].get("transition_policy_mode", "")),
        "transition_fallback_reason": str(valid[-1].get("transition_fallback_reason", "")),
    }
    for key in numeric_keys:
        values = [float(summary.get(key, 0.0)) for summary in valid]
        result[key] = float(np.mean(values))
    fallback_values = [float(summary.get("transition_fallback_count", 0.0)) for summary in valid]
    result["transition_fallback_count"] = float(np.mean(fallback_values))
    return result
