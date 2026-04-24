"""Multicycle rollout summaries for Stage-1/4 V2.1 evaluation."""

from __future__ import annotations

from typing import Any

import numpy as np


def build_multicycle_summary(
    step_records: list[dict[str, Any]],
    *,
    success_summary: dict[str, Any] | None = None,
    hybrid_summary: dict[str, Any] | None = None,
) -> dict[str, float | int]:
    if not step_records:
        return {
            "dump_to_next_dig_gap_steps": 0.0,
            "dump_to_next_dig_gap_count": 0,
            "cycle1_success": 0,
            "cycle2_success": 0,
            "cycle3_success": 0,
            "completed_dump_count": 0,
        }

    qualified_steps = [
        int(record.get("t", 0))
        for record in step_records
        if bool(record.get("qualified_dig_start_mask", 0))
    ]
    dump_end_steps = [
        int(record.get("t", 0))
        for record in step_records
        if bool(record.get("dump_end_mask", 0))
    ]

    gaps: list[int] = []
    for dump_step in dump_end_steps:
        next_dig = next((step for step in qualified_steps if step > dump_step), None)
        if next_dig is not None:
            gaps.append(int(next_dig - dump_step))

    completed_dump_count = len(dump_end_steps)
    terminal_dump_complete = bool(
        (success_summary or {}).get("dump_complete_final_hold_success", False)
    )
    completed_transition_count = int(
        (hybrid_summary or {}).get("completed_transition_count", 0)
    )
    if terminal_dump_complete:
        completed_dump_count = max(
            int(completed_dump_count),
            int(completed_transition_count) + 1,
        )
    return {
        "dump_to_next_dig_gap_steps": float(np.mean(gaps)) if gaps else 0.0,
        "dump_to_next_dig_gap_count": int(len(gaps)),
        "cycle1_success": int(completed_dump_count >= 1),
        "cycle2_success": int(completed_dump_count >= 2),
        "cycle3_success": int(completed_dump_count >= 3),
        "completed_dump_count": int(completed_dump_count),
    }


def aggregate_multicycle_metrics(
    summaries: list[dict[str, float | int]],
) -> dict[str, float]:
    if not summaries:
        return {
            "avg_dump_to_next_dig_gap_steps": 0.0,
            "cycle1_success_rate": 0.0,
            "cycle2_success_rate": 0.0,
            "cycle3_success_rate": 0.0,
            "carry_over_drop": 0.0,
        }

    valid_gap_values = [
        float(item["dump_to_next_dig_gap_steps"])
        for item in summaries
        if int(item.get("dump_to_next_dig_gap_count", 0)) > 0
    ]
    cycle1_success_rate = float(
        np.mean([float(item.get("cycle1_success", 0)) for item in summaries])
    )
    cycle2_success_rate = float(
        np.mean([float(item.get("cycle2_success", 0)) for item in summaries])
    )
    cycle3_success_rate = float(
        np.mean([float(item.get("cycle3_success", 0)) for item in summaries])
    )

    return {
        "avg_dump_to_next_dig_gap_steps": (
            float(np.mean(valid_gap_values)) if valid_gap_values else 0.0
        ),
        "cycle1_success_rate": cycle1_success_rate,
        "cycle2_success_rate": cycle2_success_rate,
        "cycle3_success_rate": cycle3_success_rate,
        "carry_over_drop": float(cycle1_success_rate - cycle3_success_rate),
    }
