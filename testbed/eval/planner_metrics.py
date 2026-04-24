"""Helpers for Stage-4 planner rollout summaries and aggregate metrics."""

from __future__ import annotations

from typing import Any

import numpy as np


def aggregate_planner_metrics(
    summaries: list[dict[str, Any]],
) -> dict[str, float | int | list[str]]:
    valid = [
        summary
        for summary in summaries
        if any(
            key in summary
            for key in (
                "planner_replan_count",
                "planner_blocked_sector_count",
                "planner_done_sector_count",
            )
        )
    ]
    if not valid:
        return {}

    result: dict[str, float | int | list[str]] = {
        "avg_planner_replan_count": float(
            np.mean([float(item.get("planner_replan_count", 0.0)) for item in valid])
        ),
        "avg_planner_blocked_sector_count": float(
            np.mean(
                [float(item.get("planner_blocked_sector_count", 0.0)) for item in valid]
            )
        ),
        "avg_planner_done_sector_count": float(
            np.mean(
                [float(item.get("planner_done_sector_count", 0.0)) for item in valid]
            )
        ),
        "planner_sector_sequences": [
            "->".join(map(str, item.get("planner_sector_sequence", [])))
            for item in valid
            if item.get("planner_sector_sequence")
        ],
    }
    return result
