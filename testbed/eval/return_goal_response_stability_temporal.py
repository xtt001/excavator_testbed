"""Pure temporal-aggregation reconstruction for Return stability diagnostics.

The functions here operate on already produced unnormalised action chunks. They
never instantiate a policy, advance an ACT cache, or change the fixed 80%
response criterion.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import numpy as np

from testbed.eval.return_goal_response_stability_contract import (
    REQUIRED_RESPONSIVE_FRAME_FRACTION,
    ReturnGoalResponseStabilityAuditError,
    finite_array,
    finite_vector,
)


def normalise_temporal_contract(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a resolved public ACT temporal aggregation contract."""

    enabled = bool(value.get("enabled"))
    num_queries = int(value.get("num_queries", 0))
    window = int(value.get("window", 0))
    order = str(value.get("weight_order", ""))
    decay = float(value.get("decay", float("nan")))
    if (
        num_queries < 1
        or window < 1
        or window > num_queries
        or order not in {"legacy_oldest_first", "newest_first"}
        or not math.isfinite(decay)
        or decay < 0.0
    ):
        raise ReturnGoalResponseStabilityAuditError("temporal aggregation contract is invalid")
    return {
        "enabled": enabled,
        "num_queries": num_queries,
        "window": window,
        "weight_order": order,
        "decay": decay,
    }


def reconstruct_temporal_aggregated_actions(
    *,
    chunks: np.ndarray,
    temporal_contract: Mapping[str, Any],
) -> np.ndarray:
    """Reconstruct ACT's temporal action aggregation from public raw chunks.

    This is an independently computed check of the stateful ``predict()``
    stream. The orchestrator compares it against actual dispatched actions;
    reconstruction alone is never reported as proof of cache behaviour.
    """

    values = finite_array(chunks, label="chunks", ndim=3)
    contract = normalise_temporal_contract(temporal_contract)
    frame_count, num_queries, action_dim = values.shape
    if num_queries != contract["num_queries"]:
        raise ReturnGoalResponseStabilityAuditError(
            "raw action chunk query count disagrees with temporal contract"
        )
    if not contract["enabled"]:
        raise ReturnGoalResponseStabilityAuditError(
            "this audit only reproduces temporally aggregated Stage-A streams"
        )
    actions = np.empty((frame_count, action_dim), dtype=np.float32)
    for current_step in range(frame_count):
        start = max(0, current_step - contract["window"] + 1)
        contributors = [
            values[source_step, current_step - source_step]
            for source_step in range(start, current_step + 1)
        ]
        ages = np.asarray(
            [current_step - source_step for source_step in range(start, current_step + 1)],
            dtype=np.float64,
        )
        if contract["weight_order"] == "legacy_oldest_first":
            distance = np.arange(len(contributors), dtype=np.float64)
        else:
            distance = ages
        weights = np.exp(-contract["decay"] * distance)
        weights = weights / np.sum(weights)
        actions[current_step] = np.sum(
            np.stack(contributors, axis=0) * weights[:, None],
            axis=0,
        )
    return actions


def derive_temporal_aggregation_diagnostics(
    *,
    baseline_chunks: np.ndarray,
    alternate_chunks: np.ndarray,
    action_threshold: np.ndarray,
    temporal_contract: Mapping[str, Any],
    required_responsive_frame_fraction: float = REQUIRED_RESPONSIVE_FRAME_FRACTION,
) -> dict[str, Any]:
    """Report whether averaging cancels a raw condition-responsive action.

    The fixed 80% gate is an input invariant. Passing any other value raises,
    preventing a diagnostic caller from changing the Stage-A classification
    criterion by accident.
    """

    baseline = finite_array(baseline_chunks, label="baseline_chunks", ndim=3)
    alternate = finite_array(alternate_chunks, label="alternate_chunks", ndim=3)
    if baseline.shape != alternate.shape:
        raise ReturnGoalResponseStabilityAuditError("baseline and alternate chunk shapes differ")
    threshold = finite_vector(action_threshold, label="action_threshold")
    if threshold.shape != (baseline.shape[2],) or np.any(threshold <= 0.0):
        raise ReturnGoalResponseStabilityAuditError("action threshold does not match action chunk width")
    if not math.isclose(
        float(required_responsive_frame_fraction),
        REQUIRED_RESPONSIVE_FRAME_FRACTION,
        rel_tol=0.0,
        abs_tol=0.0,
    ):
        raise ReturnGoalResponseStabilityAuditError(
            "Return stability audit fixes the responsive-frame gate at 80%"
        )
    contract = normalise_temporal_contract(temporal_contract)
    baseline_actions = reconstruct_temporal_aggregated_actions(
        chunks=baseline,
        temporal_contract=contract,
    )
    alternate_actions = reconstruct_temporal_aggregated_actions(
        chunks=alternate,
        temporal_contract=contract,
    )
    chunk_delta = alternate - baseline
    action_delta = alternate_actions - baseline_actions
    raw_current_responsive = np.any(
        np.abs(chunk_delta[:, 0]) > threshold[None, :], axis=1
    )
    aggregated_responsive = np.any(
        np.abs(action_delta) > threshold[None, :], axis=1
    )
    dilution_indices: list[int] = []
    contributor_counts: list[int] = []
    cache_contributors: list[dict[str, Any]] = []
    for current_step in range(chunk_delta.shape[0]):
        start = max(0, current_step - contract["window"] + 1)
        source_steps = list(range(start, current_step + 1))
        contributor_delta = np.stack(
            [
                chunk_delta[source_step, current_step - source_step]
                for source_step in source_steps
            ],
            axis=0,
        )
        contributor_counts.append(int(contributor_delta.shape[0]))
        ages = np.asarray(
            [current_step - source_step for source_step in source_steps], dtype=np.float64
        )
        distance = (
            np.arange(len(source_steps), dtype=np.float64)
            if contract["weight_order"] == "legacy_oldest_first"
            else ages
        )
        weights = np.exp(-contract["decay"] * distance)
        weights = weights / np.sum(weights)
        cache_contributors.append(
            {
                "frame_index": current_step,
                "aggregate_delta_max_abs": float(np.max(np.abs(action_delta[current_step]))),
                "aggregate_responsive": bool(aggregated_responsive[current_step]),
                "contributors": [
                    {
                        "source_frame_index": source_step,
                        "query_index": int(current_step - source_step),
                        "weight": float(weight),
                        "delta_max_abs": float(np.max(np.abs(delta))),
                        "responsive": bool(np.any(np.abs(delta) > threshold)),
                    }
                    for source_step, weight, delta in zip(
                        source_steps,
                        weights,
                        contributor_delta,
                        strict=True,
                    )
                ],
            }
        )
        if (
            not bool(aggregated_responsive[current_step])
            and bool(np.any(np.abs(contributor_delta) > threshold[None, :]))
        ):
            dilution_indices.append(current_step)
    raw_fraction = float(np.mean(raw_current_responsive))
    aggregate_fraction = float(np.mean(aggregated_responsive))
    return {
        "temporal_contract": contract,
        "fixed_required_responsive_frame_fraction": REQUIRED_RESPONSIVE_FRAME_FRACTION,
        "raw_current_query_response_fraction": raw_fraction,
        "temporal_aggregated_response_fraction": aggregate_fraction,
        "raw_current_query_passes_fixed_gate": raw_fraction >= REQUIRED_RESPONSIVE_FRAME_FRACTION,
        "temporal_aggregated_passes_fixed_gate": aggregate_fraction >= REQUIRED_RESPONSIVE_FRAME_FRACTION,
        "temporal_dilution_frame_indices": dilution_indices,
        "temporal_dilution_frame_count": len(dilution_indices),
        "cache_contributors": cache_contributors,
        "contributor_count_min": min(contributor_counts),
        "contributor_count_max": max(contributor_counts),
        "temporal_dilution_explains_gate_failure": bool(
            raw_fraction >= REQUIRED_RESPONSIVE_FRAME_FRACTION
            and aggregate_fraction < REQUIRED_RESPONSIVE_FRAME_FRACTION
            and dilution_indices
        ),
        "temporal_aggregated_action_delta_max_abs": float(np.max(np.abs(action_delta))),
    }


__all__ = [
    "derive_temporal_aggregation_diagnostics",
    "normalise_temporal_contract",
    "reconstruct_temporal_aggregated_actions",
]
