"""Read-only forensics for temporal dispatch in two frozen Return replays.

This module owns the pure contributor ranking.  Its checkpoint-backed facade
delegates immutable lineage and replay work to a focused sibling module so the
mathematics remains testable without a model and no runtime policy is changed.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from testbed.eval.return_goal_response_stability_contract import (
    EVIDENCE_KIND,
    REQUIRED_RESPONSIVE_FRAME_FRACTION,
    field,
    finite_array,
    finite_vector,
)
from testbed.eval.return_goal_response_stability_temporal import (
    normalise_temporal_contract,
    reconstruct_temporal_aggregated_actions,
)

RETURN_TEMPORAL_DISPATCH_FORENSICS_SCHEMA = "return_temporal_dispatch_forensics_v1"
"""Schema of the in-memory, JSON-ready forensic result."""

HISTORICAL_CACHE_NUMERIC_TOLERANCE = 1.0e-6
"""Fixed replay comparison tolerance; this is not a response threshold."""

DEFAULT_MAX_RANKED_HISTORICAL_CONTRIBUTORS = 8

PolicyFactoryBuilder = Callable[[str], Any]
PolicyDescriber = Callable[[Any], Mapping[str, Any]]


class ReturnTemporalDispatchForensicsError(ValueError):
    """Raised when frozen Return evidence cannot be reconstructed safely."""


def derive_return_temporal_dispatch_forensics(
    *,
    baseline_chunks: np.ndarray,
    alternate_chunks: np.ndarray,
    action_threshold: np.ndarray,
    temporal_contract: Mapping[str, Any],
    action_step_ids: Sequence[int] | None = None,
    max_ranked_historical_contributors: int = DEFAULT_MAX_RANKED_HISTORICAL_CONTRIBUTORS,
) -> dict[str, Any]:
    """Rank old chunk contributions that suppress a current raw response.

    The result contains compact rankings only for frames where query zero
    passes the frozen response test but scheduled temporal aggregation fails.
    The immutable Return stability artifact retains full cache records, which
    callers can compare with :func:`validate_historical_cache_reconstruction`.
    """

    values = _validated_temporal_values(
        baseline_chunks=baseline_chunks,
        alternate_chunks=alternate_chunks,
        action_threshold=action_threshold,
        temporal_contract=temporal_contract,
        action_step_ids=action_step_ids,
        max_ranked_historical_contributors=max_ranked_historical_contributors,
    )
    baseline = values["baseline"]
    alternate = values["alternate"]
    threshold = values["threshold"]
    contract = values["contract"]
    steps = values["action_step_ids"]
    max_ranked = values["max_ranked"]

    baseline_actions = reconstruct_temporal_aggregated_actions(
        chunks=baseline, temporal_contract=contract
    )
    alternate_actions = reconstruct_temporal_aggregated_actions(
        chunks=alternate, temporal_contract=contract
    )
    chunk_delta = alternate - baseline
    aggregate_delta = alternate_actions - baseline_actions
    raw_current_responsive = np.any(
        np.abs(chunk_delta[:, 0]) > threshold[None, :], axis=1
    )
    aggregate_responsive = np.any(np.abs(aggregate_delta) > threshold[None, :], axis=1)

    suppressed_frames: list[dict[str, Any]] = []
    temporal_dilution_indices: list[int] = []
    for current_step in range(chunk_delta.shape[0]):
        source_steps, weights = _contributors_for_step(
            current_step=current_step, temporal_contract=contract
        )
        contributor_delta = np.stack(
            [
                chunk_delta[source_step, current_step - source_step]
                for source_step in source_steps
            ],
            axis=0,
        )
        any_contributor_responsive = bool(
            np.any(np.abs(contributor_delta) > threshold[None, :])
        )
        if not bool(aggregate_responsive[current_step]) and any_contributor_responsive:
            temporal_dilution_indices.append(current_step)
        if bool(raw_current_responsive[current_step]) and not bool(
            aggregate_responsive[current_step]
        ):
            suppressed_frames.append(
                _suppressed_frame_record(
                    current_step=current_step,
                    source_steps=source_steps,
                    weights=weights,
                    contributor_delta=contributor_delta,
                    aggregate_delta=aggregate_delta[current_step],
                    threshold=threshold,
                    action_step_ids=steps,
                    max_ranked_historical_contributors=max_ranked,
                )
            )

    raw_fraction = float(np.mean(raw_current_responsive))
    aggregate_fraction = float(np.mean(aggregate_responsive))
    net_opposition_count = sum(
        bool(frame["historical_net_opposes_latest_response"])
        for frame in suppressed_frames
    )
    latest_weights = [
        float(frame["latest_query"]["weight"]) for frame in suppressed_frames
    ]
    return {
        "schema": RETURN_TEMPORAL_DISPATCH_FORENSICS_SCHEMA,
        "evidence_kind": EVIDENCE_KIND,
        "diagnostic_only": True,
        "promotion_eligible": False,
        "closed_loop_claim": False,
        "fixed_required_responsive_frame_fraction": REQUIRED_RESPONSIVE_FRAME_FRACTION,
        "temporal_contract": contract,
        "action_threshold_axis": _float_list(threshold),
        "raw_current_query_response_fraction": raw_fraction,
        "temporal_aggregated_response_fraction": aggregate_fraction,
        "raw_current_query_passes_fixed_gate": raw_fraction
        >= REQUIRED_RESPONSIVE_FRAME_FRACTION,
        "temporal_aggregated_passes_fixed_gate": aggregate_fraction
        >= REQUIRED_RESPONSIVE_FRAME_FRACTION,
        "temporal_dilution_frame_indices": temporal_dilution_indices,
        "temporal_dilution_frame_count": len(temporal_dilution_indices),
        "latest_response_suppressed_frame_count": len(suppressed_frames),
        "suppression_mechanism_summary": {
            "historical_net_opposes_latest_response_frame_count": net_opposition_count,
            "latest_weight_dilution_without_net_opposition_frame_count": (
                len(suppressed_frames) - net_opposition_count
            ),
            "latest_query_weight_min": min(latest_weights, default=0.0),
            "latest_query_weight_max": max(latest_weights, default=0.0),
            "latest_query_weight_mean": (
                float(np.mean(latest_weights)) if latest_weights else 0.0
            ),
        },
        "suppressed_frames": suppressed_frames,
        "interpretation_limit": (
            "rankings explain cancellation in teacher-forced recorded replay; "
            "they do not select or validate a replacement dispatch policy"
        ),
    }


def cache_contributor_summaries(
    *,
    baseline_chunks: np.ndarray,
    alternate_chunks: np.ndarray,
    action_threshold: np.ndarray,
    temporal_contract: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Reconstruct the compact all-frame cache summary saved by the prior audit."""

    values = _validated_temporal_values(
        baseline_chunks=baseline_chunks,
        alternate_chunks=alternate_chunks,
        action_threshold=action_threshold,
        temporal_contract=temporal_contract,
        action_step_ids=None,
        max_ranked_historical_contributors=1,
    )
    baseline = values["baseline"]
    alternate = values["alternate"]
    threshold = values["threshold"]
    contract = values["contract"]
    aggregate_delta = reconstruct_temporal_aggregated_actions(
        chunks=alternate, temporal_contract=contract
    ) - reconstruct_temporal_aggregated_actions(
        chunks=baseline, temporal_contract=contract
    )
    chunk_delta = alternate - baseline
    result: list[dict[str, Any]] = []
    for current_step in range(chunk_delta.shape[0]):
        source_steps, weights = _contributors_for_step(
            current_step=current_step, temporal_contract=contract
        )
        deltas = [
            chunk_delta[source_step, current_step - source_step]
            for source_step in source_steps
        ]
        result.append(
            {
                "frame_index": current_step,
                "aggregate_delta_max_abs": float(
                    np.max(np.abs(aggregate_delta[current_step]))
                ),
                "aggregate_responsive": bool(
                    np.any(np.abs(aggregate_delta[current_step]) > threshold)
                ),
                "contributors": [
                    {
                        "source_frame_index": source_step,
                        "query_index": int(current_step - source_step),
                        "weight": float(weight),
                        "delta_max_abs": float(np.max(np.abs(delta))),
                        "responsive": bool(np.any(np.abs(delta) > threshold)),
                    }
                    for source_step, weight, delta in zip(
                        source_steps, weights, deltas, strict=True
                    )
                ],
            }
        )
    return result


def validate_historical_cache_reconstruction(
    *,
    historical_cache_contributors: Sequence[Mapping[str, Any]],
    baseline_chunks: np.ndarray,
    alternate_chunks: np.ndarray,
    action_threshold: np.ndarray,
    temporal_contract: Mapping[str, Any],
) -> dict[str, Any]:
    """Compare a frozen all-frame cache record with a fresh public replay."""

    expected = cache_contributor_summaries(
        baseline_chunks=baseline_chunks,
        alternate_chunks=alternate_chunks,
        action_threshold=action_threshold,
        temporal_contract=temporal_contract,
    )
    actual = _mapping_sequence(
        historical_cache_contributors, label="historical cache contributors"
    )
    mismatches: list[str] = []
    if len(actual) != len(expected):
        mismatches.append("frame_count")
    for index, (stored, derived) in enumerate(zip(actual, expected, strict=False)):
        _compare_cache_frame(
            stored=stored, derived=derived, index=index, mismatches=mismatches
        )
    return {
        "passed": not mismatches,
        "verification": (
            "frozen Return stability cache records compared against a fresh "
            "public predict_action_chunk/predict replay reconstruction"
        ),
        "frame_count": len(expected),
        "historical_frame_count": len(actual),
        "numeric_tolerance": HISTORICAL_CACHE_NUMERIC_TOLERANCE,
        "mismatch_fields": sorted(set(mismatches)),
        "artifact_information_limit": (
            "the historical cache artifact records contributor max magnitudes "
            "rather than full action vectors; full vectors in this result come "
            "from the verified fresh public replay"
        ),
    }


def collect_public_policy_stream(
    *,
    policy: Any,
    observations: Sequence[Mapping[str, Any]],
    token_key: str,
    token: np.ndarray,
) -> dict[str, np.ndarray]:
    """Collect raw chunks and dispatched actions through public ACT methods.

    A single reset occurs at the segment entrance.  One non-advancing chunk
    inspection precedes exactly one stateful dispatch call for every recorded
    observation.  The caller validates cache state independently by
    reconstruction.
    """

    if not str(token_key):
        raise ReturnTemporalDispatchForensicsError(
            "Return segment lacks a model token key"
        )
    if not observations:
        raise ReturnTemporalDispatchForensicsError("Return segment has no observations")
    reset = getattr(policy, "reset", None)
    predict_chunk = getattr(policy, "predict_action_chunk", None)
    predict = getattr(policy, "predict", None)
    if not callable(reset) or not callable(predict_chunk) or not callable(predict):
        raise ReturnTemporalDispatchForensicsError(
            "forensic policy must implement reset(), predict_action_chunk(), and predict()"
        )
    condition = finite_vector(token, label="Return forensic token")
    reset()
    chunks: list[np.ndarray] = []
    actions: list[np.ndarray] = []
    for index, source_observation in enumerate(observations):
        observation = dict(source_observation)
        observation[str(token_key)] = condition.copy()
        raw_chunk = predict_chunk(observation)
        chunk = finite_array(
            field(raw_chunk, "actions", field(raw_chunk, "action_chunk", None)),
            label=f"Return forensic policy chunk {index}",
            ndim=2,
        )
        action = finite_vector(
            predict(observation), label=f"Return forensic action {index}"
        )
        if action.shape != (chunk.shape[1],):
            raise ReturnTemporalDispatchForensicsError(
                "public dispatched action width differs from action chunk width"
            )
        chunks.append(chunk)
        actions.append(action)
    return {"chunks": np.stack(chunks, axis=0), "actions": np.stack(actions, axis=0)}


def proposed_temporal_dispatch_strategies(
    *, temporal_contract: Mapping[str, Any]
) -> dict[str, Any]:
    """Name follow-up classes without treating them as forensic evidence."""

    baseline = normalise_temporal_contract(temporal_contract)
    return {
        "status": "not_evaluated",
        "evidence_role": "planning_only",
        "runtime_change": False,
        "selection_permitted": False,
        "required_next_evidence": (
            "source-disjoint Return validation with the fixed 80 percent "
            "response gate, action continuity, action-boundary and replica/cache checks"
        ),
        "candidates": [
            {
                "candidate_id": "baseline_legacy_oldest_first",
                "role": "frozen_evidence_baseline",
                "temporal_contract": baseline,
                "runtime_eligible": False,
            },
            {
                "candidate_id": "same_window_newest_biased",
                "role": "proposal_not_evaluated",
                "invariant": {"window": "same_as_frozen_baseline"},
                "change_under_test": "more weight on newer chunk plans",
                "runtime_eligible": False,
            },
            {
                "candidate_id": "bounded_age_aggregation",
                "role": "proposal_not_evaluated",
                "change_under_test": "exclude contributors older than a pre-registered age",
                "maximum_age": "not_selected_from_failed_pairs",
                "runtime_eligible": False,
            },
            {
                "candidate_id": "latest_chunk_diagnostic_only",
                "role": "diagnostic_control_not_a_runtime_candidate",
                "change_under_test": "dispatch query zero only",
                "runtime_eligible": False,
            },
        ],
    }


def run_return_temporal_dispatch_forensics(
    *,
    return_stability_output_root: str | Path,
    device: str = "cuda",
    policy_factory_builder: PolicyFactoryBuilder | None = None,
    policy_describer: PolicyDescriber | None = None,
) -> dict[str, Any]:
    """Run the read-only frozen replay through the focused lineage adapter."""

    from testbed.eval.return_temporal_dispatch_forensics_replay import (
        run_return_temporal_dispatch_forensics_replay,
    )

    return run_return_temporal_dispatch_forensics_replay(
        return_stability_output_root=return_stability_output_root,
        device=device,
        policy_factory_builder=policy_factory_builder,
        policy_describer=policy_describer,
    )


def _validated_temporal_values(
    *,
    baseline_chunks: np.ndarray,
    alternate_chunks: np.ndarray,
    action_threshold: np.ndarray,
    temporal_contract: Mapping[str, Any],
    action_step_ids: Sequence[int] | None,
    max_ranked_historical_contributors: int,
) -> dict[str, Any]:
    baseline = finite_array(baseline_chunks, label="baseline chunks", ndim=3)
    alternate = finite_array(alternate_chunks, label="alternate chunks", ndim=3)
    if baseline.shape != alternate.shape:
        raise ReturnTemporalDispatchForensicsError(
            "baseline and alternate chunks differ"
        )
    threshold = finite_vector(action_threshold, label="action threshold")
    if threshold.shape != (baseline.shape[2],) or np.any(threshold <= 0.0):
        raise ReturnTemporalDispatchForensicsError(
            "action threshold does not match chunk width"
        )
    contract = normalise_temporal_contract(temporal_contract)
    if not contract["enabled"]:
        raise ReturnTemporalDispatchForensicsError(
            "frozen Return forensic requires temporal aggregation"
        )
    if baseline.shape[1] != contract["num_queries"]:
        raise ReturnTemporalDispatchForensicsError(
            "chunk query count disagrees with temporal contract"
        )
    if (
        isinstance(max_ranked_historical_contributors, bool)
        or int(max_ranked_historical_contributors) < 1
    ):
        raise ReturnTemporalDispatchForensicsError(
            "max_ranked_historical_contributors must be a positive integer"
        )
    frame_count = baseline.shape[0]
    if action_step_ids is None:
        steps: list[int | None] = [None] * frame_count
    else:
        if len(action_step_ids) != frame_count:
            raise ReturnTemporalDispatchForensicsError(
                "action_step_ids length disagrees with chunk frame count"
            )
        steps = []
        for value in action_step_ids:
            if isinstance(value, bool):
                raise ReturnTemporalDispatchForensicsError(
                    "action step id must be an integer"
                )
            steps.append(int(value))
    return {
        "baseline": baseline,
        "alternate": alternate,
        "threshold": threshold,
        "contract": contract,
        "action_step_ids": steps,
        "max_ranked": int(max_ranked_historical_contributors),
    }


def _contributors_for_step(
    *, current_step: int, temporal_contract: Mapping[str, Any]
) -> tuple[list[int], np.ndarray]:
    start = max(0, current_step - int(temporal_contract["window"]) + 1)
    source_steps = list(range(start, current_step + 1))
    ages = np.asarray([current_step - step for step in source_steps], dtype=np.float64)
    if temporal_contract["weight_order"] == "legacy_oldest_first":
        distance = np.arange(len(source_steps), dtype=np.float64)
    else:
        distance = ages
    weights = np.exp(-float(temporal_contract["decay"]) * distance)
    return source_steps, weights / np.sum(weights)


def _suppressed_frame_record(
    *,
    current_step: int,
    source_steps: Sequence[int],
    weights: np.ndarray,
    contributor_delta: np.ndarray,
    aggregate_delta: np.ndarray,
    threshold: np.ndarray,
    action_step_ids: Sequence[int | None],
    max_ranked_historical_contributors: int,
) -> dict[str, Any]:
    latest_position = len(source_steps) - 1
    latest_delta = contributor_delta[latest_position]
    latest_weight = float(weights[latest_position])
    latest_weighted = latest_weight * latest_delta
    norm = float(np.linalg.norm(latest_delta))
    direction = latest_delta / norm if norm > 0.0 else np.zeros_like(latest_delta)
    records: list[dict[str, Any]] = []
    historical_weighted_total = np.zeros_like(latest_delta, dtype=np.float64)
    for position, (source_step, weight, raw_delta) in enumerate(
        zip(source_steps, weights, contributor_delta, strict=True)
    ):
        if position == latest_position:
            continue
        weighted = float(weight) * raw_delta
        historical_weighted_total += weighted
        signed_projection = float(np.dot(weighted, direction))
        suppression = max(0.0, -signed_projection)
        if suppression > 0.0:
            records.append(
                {
                    "source_frame_index": int(source_step),
                    "source_action_step_id": action_step_ids[source_step],
                    "query_index": int(current_step - source_step),
                    "weight": float(weight),
                    "raw_action_delta_vector": _float_list(raw_delta),
                    "weighted_contribution_vector": _float_list(weighted),
                    "signed_projection_on_latest_response": signed_projection,
                    "suppression_projection": suppression,
                }
            )
    records.sort(
        key=lambda item: (
            -float(item["suppression_projection"]),
            int(item["source_frame_index"]),
        )
    )
    historic_projection = float(np.dot(historical_weighted_total, direction))
    return {
        "frame_index": int(current_step),
        "action_step_id": action_step_ids[current_step],
        "aggregate_action_delta_vector": _float_list(aggregate_delta),
        "aggregate_responsive": bool(np.any(np.abs(aggregate_delta) > threshold)),
        "latest_query": {
            "source_frame_index": int(current_step),
            "source_action_step_id": action_step_ids[current_step],
            "query_index": 0,
            "weight": latest_weight,
            "raw_action_delta_vector": _float_list(latest_delta),
            "weighted_contribution_vector": _float_list(latest_weighted),
            "raw_response_axes": [
                bool(value) for value in np.abs(latest_delta) > threshold
            ],
        },
        "historical_contributor_count": len(source_steps) - 1,
        "historical_net_weighted_contribution_vector": _float_list(
            historical_weighted_total
        ),
        "historical_net_signed_projection_on_latest_response": historic_projection,
        "historical_net_suppression_projection": max(0.0, -historic_projection),
        "historical_net_opposes_latest_response": bool(historic_projection < 0.0),
        "historical_contributors_ranked_by_suppression": records[
            :max_ranked_historical_contributors
        ],
        "suppression_contributors_omitted": max(
            0, len(records) - max_ranked_historical_contributors
        ),
    }


def _compare_cache_frame(
    *,
    stored: Mapping[str, Any],
    derived: Mapping[str, Any],
    index: int,
    mismatches: list[str],
) -> None:
    if int(stored.get("frame_index", -1)) != int(derived["frame_index"]):
        mismatches.append("frame_index")
    if bool(stored.get("aggregate_responsive")) != bool(
        derived["aggregate_responsive"]
    ):
        mismatches.append("aggregate_responsive")
    _compare_float(
        stored.get("aggregate_delta_max_abs"),
        derived["aggregate_delta_max_abs"],
        "aggregate_delta_max_abs",
        mismatches,
    )
    stored_contributors = _mapping_sequence(
        stored.get("contributors", ()), label=f"historical contributors[{index}]"
    )
    derived_contributors = _mapping_sequence(
        derived["contributors"], label=f"derived contributors[{index}]"
    )
    if len(stored_contributors) != len(derived_contributors):
        mismatches.append("contributor_count")
    for actual, expected in zip(
        stored_contributors, derived_contributors, strict=False
    ):
        for name in ("source_frame_index", "query_index", "responsive"):
            if actual.get(name) != expected[name]:
                mismatches.append(name)
        for name in ("weight", "delta_max_abs"):
            _compare_float(actual.get(name), expected[name], name, mismatches)


def _compare_float(
    actual: Any, expected: float, name: str, mismatches: list[str]
) -> None:
    try:
        value = float(actual)
    except (TypeError, ValueError):
        mismatches.append(name)
        return
    if not math.isfinite(value) or not math.isclose(
        value,
        float(expected),
        rel_tol=HISTORICAL_CACHE_NUMERIC_TOLERANCE,
        abs_tol=HISTORICAL_CACHE_NUMERIC_TOLERANCE,
    ):
        mismatches.append(name)


def _mapping_sequence(value: Any, *, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ReturnTemporalDispatchForensicsError(f"{label} must be a sequence")
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ReturnTemporalDispatchForensicsError(f"{label} must contain mappings")
        result.append(dict(item))
    return result


def _float_list(values: Any) -> list[float]:
    return [float(value) for value in np.asarray(values, dtype=np.float64).reshape(-1)]


__all__ = [
    "DEFAULT_MAX_RANKED_HISTORICAL_CONTRIBUTORS",
    "HISTORICAL_CACHE_NUMERIC_TOLERANCE",
    "RETURN_TEMPORAL_DISPATCH_FORENSICS_SCHEMA",
    "ReturnTemporalDispatchForensicsError",
    "cache_contributor_summaries",
    "collect_public_policy_stream",
    "derive_return_temporal_dispatch_forensics",
    "proposed_temporal_dispatch_strategies",
    "run_return_temporal_dispatch_forensics",
    "validate_historical_cache_reconstruction",
]
