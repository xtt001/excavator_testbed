"""Offline source-disjoint selection of Return temporal-dispatch candidates.

This module owns threshold derivation, candidate comparison, and selection.
Public ACT replay/cache verification lives in the focused sibling
``return_temporal_dispatch_validation_replay``.  No function here accepts a
Stage-A failed segment or runtime configuration, so target evidence cannot
select a window, weight order, or threshold.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from testbed.data.return_temporal_dispatch_sampling import (
    RETURN_TEMPORAL_DISPATCH_SAMPLE_SCHEMA,
    ReturnTemporalDispatchValidationSample,
)
from testbed.data.return_temporal_dispatch_validation import (
    RETURN_TEMPORAL_DISPATCH_VALIDATION_SCHEMA,
    ReturnTemporalDispatchFrame,
    ReturnTemporalDispatchValidationPopulation,
    ReturnValidationCounterfactualPair,
    read_return_temporal_dispatch_observation,
)
from testbed.eval.return_temporal_dispatch_validation_replay import (
    PUBLIC_LEGACY_RECONSTRUCTION_TOLERANCE,
    REPLICA_STABILITY_TOLERANCE,
    ObservationReader,
    PolicyDescriber,
    PolicyFactory,
    ReturnTemporalDispatchValidationEvaluationError,
    replay_return_temporal_dispatch_pair,
)
from testbed.eval.temporal_dispatch_contract import (
    REQUIRED_RESPONSE_ACTIVE_FRACTION,
    TemporalDispatchMetricContract,
    TemporalDispatchStrategy,
    evaluate_temporal_dispatch_metrics,
    pre_registered_temporal_dispatch_strategies,
    reconstruct_temporal_dispatch,
)
from testbed.policies.act.inference import describe_act_inference

RETURN_TEMPORAL_DISPATCH_VALIDATION_EVALUATION_SCHEMA = (
    "return_temporal_dispatch_validation_evaluation_v1"
)
RETURN_TEMPORAL_DISPATCH_REQUIRED_SAMPLED_SEGMENT_COUNT = 16
RETURN_TEMPORAL_DISPATCH_RESPONSE_ACTION_SCALE_FRACTION = 0.05

_LEGACY = "legacy_100_oldest_first_decay_0p01"
_CANDIDATES = (
    "newest_first_100_decay_0p01",
    "newest_first_max_age_20_decay_0p01",
)
_DIAGNOSTIC = "latest_current_chunk_diagnostic"
_STRATEGY_IDS = (_LEGACY, *_CANDIDATES, _DIAGNOSTIC)


def build_return_temporal_dispatch_metric_contract(
    population: ReturnTemporalDispatchValidationPopulation,
) -> TemporalDispatchMetricContract:
    """Derive response and action-quality limits from strict Return train only."""

    _validate_population(population)
    reference = population.action_reference
    if reference.fit_partition != "strict_train":
        raise ReturnTemporalDispatchValidationEvaluationError(
            "Return action reference must be fit only on strict train"
        )
    scale = _vector(reference.action_scale, "strict-train action scale")
    lower = _vector(reference.action_p01, "strict-train action p01")
    upper = _vector(reference.action_p99, "strict-train action p99")
    delta_p99 = _vector(reference.action_delta_abs_p99, "strict-train action-delta p99")
    if (
        np.any(scale <= 0.0)
        or scale.shape != lower.shape
        or scale.shape != upper.shape
        or scale.shape != delta_p99.shape
        or np.any(lower > upper)
        or np.any(delta_p99 < 0.0)
    ):
        raise ReturnTemporalDispatchValidationEvaluationError(
            "strict-train Return action reference is invalid"
        )
    return TemporalDispatchMetricContract(
        response_threshold=np.maximum(
            PUBLIC_LEGACY_RECONSTRUCTION_TOLERANCE,
            RETURN_TEMPORAL_DISPATCH_RESPONSE_ACTION_SCALE_FRACTION * scale,
        ),
        action_scale=scale,
        envelope_lower=lower,
        envelope_upper=upper,
        jitter_mean_abs_limit=delta_p99,
        discontinuity_threshold=delta_p99,
    )


def evaluate_return_temporal_dispatch_validation(
    *,
    population: ReturnTemporalDispatchValidationPopulation,
    sample: ReturnTemporalDispatchValidationSample,
    policy_factory: PolicyFactory,
    observation_reader: ObservationReader | None = None,
    policy_describer: PolicyDescriber | None = None,
) -> dict[str, Any]:
    """Evaluate exactly 16 held source-balanced Return counterfactual pairs.

    The factory is called for independent baseline/alternate primary and
    replica streams. Each stream is reset once at its segment entrance. A
    selected result remains an opt-in shadow candidate, not a runtime change.
    """

    _validate_inputs(population=population, sample=sample)
    metric = build_return_temporal_dispatch_metric_contract(population)
    strategies = _strategies()
    reader = observation_reader or _reader_for(population)
    describer = policy_describer or describe_act_inference
    records: list[dict[str, Any]] = []
    expected_signature: dict[str, Any] | None = None
    for pair in sample.counterfactual_pairs:
        record = replay_return_temporal_dispatch_pair(
            pair=pair,
            token_key=population.model_token_key,
            policy_factory=policy_factory,
            observation_reader=reader,
            policy_describer=describer,
            metric_contract=metric,
            legacy_strategy=strategies[_LEGACY],
        )
        signature = record["policy_signature"]
        if expected_signature is None:
            expected_signature = signature
        elif signature != expected_signature:
            raise ReturnTemporalDispatchValidationEvaluationError(
                "policy temporal contract or action scale changed across held pairs"
            )
        records.append(record)

    results = _evaluate_strategies(
        records=records, metric=metric, strategies=strategies
    )
    selection = _select(results)
    return {
        "schema": RETURN_TEMPORAL_DISPATCH_VALIDATION_EVALUATION_SCHEMA,
        "evidence_kind": "teacher_forced_source_disjoint_held_validation",
        "diagnostic_only": True,
        "promotion_eligible": False,
        "closed_loop_claim": False,
        "target_stage_a_failures_used": False,
        "runtime_default_changed": False,
        "input_scope": {
            "fit_partition": "strict_train",
            "evaluation_partition": "held_out_source_disjoint_return",
            "counterfactual_tokens": "real_held_validation_tokens_only",
            "target_rollout_input_accepted": False,
            "stage_a_artifact_input_accepted": False,
        },
        "sample": _sample_summary(sample),
        "metric_contract": {
            **metric.as_dict(),
            "response_threshold_definition": "max(1e-6, strict_train_action_scale * 0.05)",
            "jitter_and_discontinuity_definition": "strict_train_action_delta_abs_p99_per_axis",
        },
        "policy_verification": {
            "all_pairs_passed": True,
            "legacy_reconstruction_tolerance": PUBLIC_LEGACY_RECONSTRUCTION_TOLERANCE,
            "replica_stability_tolerance": REPLICA_STABILITY_TOLERANCE,
            "resolved_policy_signature": expected_signature,
            "per_pair": [record["verification"] for record in records],
        },
        "strategies": results,
        "selection": selection,
        "interpretation_limit": (
            "A selected strategy is only an opt-in diagnostic shadow candidate; "
            "Unity/closed-loop evidence is required before a default change."
        ),
    }


def _strategies() -> dict[str, TemporalDispatchStrategy]:
    strategies = pre_registered_temporal_dispatch_strategies()
    if tuple(strategies) != _STRATEGY_IDS:
        raise ReturnTemporalDispatchValidationEvaluationError(
            "temporal strategy set differs from its pre-registered contract"
        )
    if strategies[_LEGACY].promotion_eligible or strategies[_LEGACY].diagnostic_only:
        raise ReturnTemporalDispatchValidationEvaluationError(
            "legacy strategy must remain comparison-only"
        )
    if any(
        not strategies[item].promotion_eligible or strategies[item].diagnostic_only
        for item in _CANDIDATES
    ):
        raise ReturnTemporalDispatchValidationEvaluationError(
            "Return promotion-candidate flags are invalid"
        )
    if (
        not strategies[_DIAGNOSTIC].diagnostic_only
        or strategies[_DIAGNOSTIC].promotion_eligible
    ):
        raise ReturnTemporalDispatchValidationEvaluationError(
            "latest-current strategy must stay diagnostic-only"
        )
    return strategies


def _validate_inputs(
    *,
    population: ReturnTemporalDispatchValidationPopulation,
    sample: ReturnTemporalDispatchValidationSample,
) -> None:
    _validate_population(population)
    if (
        not isinstance(sample, ReturnTemporalDispatchValidationSample)
        or sample.schema != RETURN_TEMPORAL_DISPATCH_SAMPLE_SCHEMA
    ):
        raise ReturnTemporalDispatchValidationEvaluationError(
            "Return temporal dispatch sample schema mismatch"
        )
    segments, pairs = sample.sampled_segments, sample.counterfactual_pairs
    if len(segments) != RETURN_TEMPORAL_DISPATCH_REQUIRED_SAMPLED_SEGMENT_COUNT:
        raise ReturnTemporalDispatchValidationEvaluationError(
            "Return temporal dispatch validation requires exactly 16 source-balanced segments"
        )
    if len(pairs) != len(segments):
        raise ReturnTemporalDispatchValidationEvaluationError(
            "Return pairs must cover every sampled segment exactly once"
        )
    held = {item.segment_id: item for item in population.validation_segments}
    sampled_ids = [item.segment_id for item in segments]
    if len(set(sampled_ids)) != len(segments) or not set(sampled_ids) <= set(held):
        raise ReturnTemporalDispatchValidationEvaluationError(
            "Return sampled segments leave source-disjoint held validation"
        )
    validation_sources = set(population.validation_source_episode_ids)
    train_sources = set(population.train_source_episode_ids)
    counts = _source_counts([item.source_episode_id for item in segments])
    if (
        validation_sources & train_sources
        or not set(counts) <= validation_sources
        or len(counts) < 2
        or len(set(counts.values())) != 1
    ):
        raise ReturnTemporalDispatchValidationEvaluationError(
            "Return sampled population is not source-disjoint and balanced"
        )
    source_summaries = {item.source_episode_id: item for item in sample.source_samples}
    expected_ids_by_source = {
        source: tuple(
            item.segment_id for item in segments if item.source_episode_id == source
        )
        for source in counts
    }
    if (
        len(source_summaries) != len(sample.source_samples)
        or set(source_summaries) != set(counts)
        or any(
            source_summaries[source].sampled_segment_ids != expected_ids
            for source, expected_ids in expected_ids_by_source.items()
        )
    ):
        raise ReturnTemporalDispatchValidationEvaluationError(
            "Return source summaries disagree with the held population"
        )
    pairs_by_id = {item.baseline_segment.segment_id: item for item in pairs}
    if len(pairs_by_id) != len(pairs) or set(pairs_by_id) != set(sampled_ids):
        raise ReturnTemporalDispatchValidationEvaluationError(
            "Return pairs do not exactly cover sampled baselines"
        )
    for pair in pairs:
        baseline = pair.baseline_segment
        canonical = held.get(baseline.segment_id)
        if (
            canonical is None
            or canonical.token_sha256 != baseline.token_sha256
            or baseline.source_episode_id not in validation_sources
            or pair.alternate_token_source_episode_id not in validation_sources
            or pair.alternate_token_sha256 == baseline.token_sha256
            or not baseline.frames
        ):
            raise ReturnTemporalDispatchValidationEvaluationError(
                "Return pair is not a real held-validation counterfactual"
            )
        if (
            _vector(pair.alternate_token, "Return alternate token").shape
            != baseline.token.shape
        ):
            raise ReturnTemporalDispatchValidationEvaluationError(
                "Return alternate token shape differs from its baseline"
            )


def _validate_population(
    population: ReturnTemporalDispatchValidationPopulation,
) -> None:
    if (
        not isinstance(population, ReturnTemporalDispatchValidationPopulation)
        or population.schema != RETURN_TEMPORAL_DISPATCH_VALIDATION_SCHEMA
        or population.model_token_key != "return_start_envelope_tokens_v1"
        or not population.train_source_episode_ids
        or not population.validation_source_episode_ids
    ):
        raise ReturnTemporalDispatchValidationEvaluationError(
            "Return strict validation population is invalid"
        )


def _reader_for(
    population: ReturnTemporalDispatchValidationPopulation,
) -> ObservationReader:
    def read(frame: ReturnTemporalDispatchFrame) -> Mapping[str, Any]:
        return read_return_temporal_dispatch_observation(
            frame=frame, camera_names=population.camera_names
        )

    return read


def _evaluate_strategies(
    *,
    records: Sequence[Mapping[str, Any]],
    metric: TemporalDispatchMetricContract,
    strategies: Mapping[str, TemporalDispatchStrategy],
) -> dict[str, Any]:
    results: dict[str, dict[str, Any]] = {}
    for strategy_id, strategy in strategies.items():
        pairs = []
        for record in records:
            streams, pair = record["streams"], record["pair"]
            baseline = reconstruct_temporal_dispatch(
                chunks=streams["baseline_primary"]["chunks"],
                strategy=strategy,
                reset_frame_indices=(0,),
            )
            alternate = reconstruct_temporal_dispatch(
                chunks=streams["alternate_primary"]["chunks"],
                strategy=strategy,
                reset_frame_indices=(0,),
            )
            reference = reconstruct_temporal_dispatch(
                chunks=streams["baseline_primary"]["chunks"],
                strategy=strategies[_LEGACY],
                reset_frame_indices=(0,),
            )
            pairs.append(
                _compact_metrics(
                    pair=pair,
                    metrics=evaluate_temporal_dispatch_metrics(
                        baseline=baseline,
                        alternate=alternate,
                        metric_contract=metric,
                        reference_actions=reference.actions,
                    ),
                )
            )
        results[strategy_id] = {
            "strategy": strategy.as_dict(),
            "selection_eligible": strategy_id in _CANDIDATES,
            "pair_metrics": pairs,
            "aggregate": _aggregate(pairs),
        }

    legacy = results[_LEGACY]
    for result in results.values():
        quality = _quality_vs_legacy(result, legacy)
        response = result["aggregate"]["response"]
        old_response = legacy["aggregate"]["response"]
        response_passed = bool(
            response["passes_fixed_gate"]
            and all(
                item["response"]["passes_fixed_gate"] for item in result["pair_metrics"]
            )
        )
        improved = response["active_frame_count"] > old_response["active_frame_count"]
        result["quality_vs_legacy"] = quality
        result["response_improvement_vs_legacy"] = {
            "candidate_active_frame_count": response["active_frame_count"],
            "legacy_active_frame_count": old_response["active_frame_count"],
            "strictly_improves_legacy": improved,
        }
        result["pre_registered_gates"] = {
            "every_pair_reaches_fixed_80_percent_response": response_passed,
            "aggregate_reaches_fixed_80_percent_response": response[
                "passes_fixed_gate"
            ],
            "quality_is_no_worse_than_legacy": quality["passed"],
            "strictly_improves_legacy_aggregate_response": improved,
        }
        result["passes_pre_registered_selection"] = bool(
            result["selection_eligible"]
            and response_passed
            and quality["passed"]
            and improved
        )
    return results


def _compact_metrics(
    *, pair: ReturnValidationCounterfactualPair, metrics: Mapping[str, Any]
) -> dict[str, Any]:
    response = _mapping(metrics.get("response"), "response metrics")
    frames = _integer(
        response.get("frame_count"), "response frame count", positive=True
    )
    active = _integer(response.get("active_frame_count"), "response active count")
    if active > frames:
        raise ReturnTemporalDispatchValidationEvaluationError(
            "response active count exceeds frame count"
        )
    return {
        "pair_id": pair.pair_id,
        "baseline_segment_id": pair.baseline_segment.segment_id,
        "source_episode_id": pair.baseline_segment.source_episode_id,
        "frame_count": frames,
        "response": {
            "active_frame_count": active,
            "active_frame_fraction": _fraction(response.get("active_frame_fraction")),
            "passes_fixed_gate": bool(response.get("passes_fixed_gate")),
            "required_active_frame_fraction": float(
                response["required_active_frame_fraction"]
            ),
            "action_delta_max_abs": float(response["action_delta_max_abs"]),
        },
        "baseline_action_quality": _compact_quality(
            metrics["baseline_action_quality"], frames
        ),
        "alternate_action_quality": _compact_quality(
            metrics["alternate_action_quality"], frames
        ),
    }


def _compact_quality(value: Any, frames: int) -> dict[str, Any]:
    quality = _mapping(value, "action quality")
    envelope = _mapping(quality.get("envelope"), "action envelope")
    delta = _mapping(quality.get("first_difference"), "action delta")
    scale = _mapping(quality.get("action_scale"), "action scale")
    violations = _integer(envelope.get("violation_frame_count"), "envelope violations")
    discontinuities = _integer(
        delta.get("discontinuity_transition_count"), "discontinuities"
    )
    transitions = max(frames - 1, 0)
    if violations > frames or discontinuities > transitions:
        raise ReturnTemporalDispatchValidationEvaluationError(
            "invalid compact action-quality counts"
        )
    return {
        "envelope_violation_frame_count": violations,
        "envelope_violation_frame_rate": _rate(violations, frames),
        "within_frozen_envelope": bool(envelope.get("within_frozen_envelope")),
        "discontinuity_transition_count": discontinuities,
        "discontinuity_transition_rate": _rate(discontinuities, transitions),
        "passes_train_action_delta_p99_jitter": bool(delta.get("passes_jitter_limit")),
        "mean_abs_first_difference": _floats(
            _vector(delta.get("mean_abs"), "mean action delta")
        ),
        "max_abs_over_train_action_scale": _floats(
            _vector(scale.get("max_abs_over_scale"), "action scale ratio")
        ),
    }


def _aggregate(pairs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not pairs:
        raise ReturnTemporalDispatchValidationEvaluationError(
            "strategy has no held pair metrics"
        )
    frames = sum(
        _integer(item["frame_count"], "pair frame count", positive=True)
        for item in pairs
    )
    transitions = sum(max(item["frame_count"] - 1, 0) for item in pairs)
    active = sum(item["response"]["active_frame_count"] for item in pairs)
    return {
        "frame_count": frames,
        "response": {
            "active_frame_count": active,
            "active_frame_fraction": _rate(active, frames),
            "passes_fixed_gate": _rate(active, frames)
            >= REQUIRED_RESPONSE_ACTIVE_FRACTION,
            "required_active_frame_fraction": REQUIRED_RESPONSE_ACTIVE_FRACTION,
        },
        "baseline_action_quality": _aggregate_quality(
            pairs, "baseline_action_quality", frames, transitions
        ),
        "alternate_action_quality": _aggregate_quality(
            pairs, "alternate_action_quality", frames, transitions
        ),
    }


def _aggregate_quality(
    pairs: Sequence[Mapping[str, Any]], key: str, frames: int, transitions: int
) -> dict[str, Any]:
    values = [item[key] for item in pairs]
    violations = sum(item["envelope_violation_frame_count"] for item in values)
    discontinuities = sum(item["discontinuity_transition_count"] for item in values)
    if violations > frames or discontinuities > transitions:
        raise ReturnTemporalDispatchValidationEvaluationError(
            "invalid aggregate action-quality counts"
        )
    return {
        "envelope_violation_frame_count": violations,
        "envelope_violation_frame_rate": _rate(violations, frames),
        "discontinuity_transition_count": discontinuities,
        "discontinuity_transition_rate": _rate(discontinuities, transitions),
        "passes_train_action_delta_p99_jitter": all(
            item["passes_train_action_delta_p99_jitter"] for item in values
        ),
        "max_mean_abs_first_difference": _floats(
            np.max([item["mean_abs_first_difference"] for item in values], axis=0)
        ),
        "max_abs_over_train_action_scale": _floats(
            np.max([item["max_abs_over_train_action_scale"] for item in values], axis=0)
        ),
    }


def _quality_vs_legacy(
    candidate: Mapping[str, Any], legacy: Mapping[str, Any]
) -> dict[str, Any]:
    old_pairs = {item["pair_id"]: item for item in legacy["pair_metrics"]}
    checks = []
    for item in candidate["pair_metrics"]:
        old = old_pairs.get(item["pair_id"])
        if old is None:
            raise ReturnTemporalDispatchValidationEvaluationError(
                "strategy pair coverage differs from legacy"
            )
        baseline = _quality_not_worse(
            item["baseline_action_quality"], old["baseline_action_quality"]
        )
        alternate = _quality_not_worse(
            item["alternate_action_quality"], old["alternate_action_quality"]
        )
        checks.append(
            {
                "pair_id": item["pair_id"],
                "baseline_condition": baseline,
                "alternate_condition": alternate,
                "passed": baseline["passed"] and alternate["passed"],
            }
        )
    aggregate = {
        "baseline_condition": _quality_not_worse(
            candidate["aggregate"]["baseline_action_quality"],
            legacy["aggregate"]["baseline_action_quality"],
        ),
        "alternate_condition": _quality_not_worse(
            candidate["aggregate"]["alternate_action_quality"],
            legacy["aggregate"]["alternate_action_quality"],
        ),
    }
    aggregate["passed"] = (
        aggregate["baseline_condition"]["passed"]
        and aggregate["alternate_condition"]["passed"]
    )
    return {
        "per_pair": checks,
        "aggregate": aggregate,
        "passed": aggregate["passed"] and all(item["passed"] for item in checks),
    }


def _quality_not_worse(
    candidate: Mapping[str, Any], legacy: Mapping[str, Any]
) -> dict[str, bool]:
    envelope = (
        candidate["envelope_violation_frame_rate"]
        <= legacy["envelope_violation_frame_rate"]
    )
    discontinuity = (
        candidate["discontinuity_transition_rate"]
        <= legacy["discontinuity_transition_rate"]
    )
    jitter = bool(candidate["passes_train_action_delta_p99_jitter"])
    return {
        "envelope_violation_rate_no_worse": envelope,
        "discontinuity_rate_no_worse": discontinuity,
        "passes_train_action_delta_p99_jitter": jitter,
        "passed": envelope and discontinuity and jitter,
    }


def _select(results: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    passed = [
        item for item in _CANDIDATES if results[item]["passes_pre_registered_selection"]
    ]
    ranked = sorted(passed, key=lambda item: _rank(results[item], item))
    selected = ranked[0] if ranked else None
    return {
        "selection_scope": "offline_source_disjoint_validation_only",
        "legacy_strategy_retained_as_comparison_only": _LEGACY,
        "diagnostic_only_strategy_never_selectable": _DIAGNOSTIC,
        "candidate_ids_considered": list(_CANDIDATES),
        "passed_candidate_ids_in_fixed_rank_order": ranked,
        "selected_strategy_id": selected,
        "candidate_frozen_for_opt_in_shadow_only": bool(selected),
        "runtime_default_changed": False,
        "selection_tie_break_order": [
            "higher_aggregate_active_response_fraction",
            "lower_combined_envelope_violation_rate",
            "lower_combined_discontinuity_transition_rate",
            "lower_max_action_over_strict_train_action_scale",
            "strategy_id_lexicographic",
        ],
        "no_candidate_reason": (
            None
            if selected
            else "No promotable candidate passed every response, quality, and improvement gate."
        ),
    }


def _rank(result: Mapping[str, Any], strategy_id: str) -> tuple[Any, ...]:
    aggregate = result["aggregate"]
    baseline = aggregate["baseline_action_quality"]
    alternate = aggregate["alternate_action_quality"]
    return (
        -aggregate["response"]["active_frame_fraction"],
        baseline["envelope_violation_frame_rate"]
        + alternate["envelope_violation_frame_rate"],
        baseline["discontinuity_transition_rate"]
        + alternate["discontinuity_transition_rate"],
        max(
            max(baseline["max_abs_over_train_action_scale"]),
            max(alternate["max_abs_over_train_action_scale"]),
        ),
        strategy_id,
    )


def _sample_summary(sample: ReturnTemporalDispatchValidationSample) -> dict[str, Any]:
    counts = _source_counts(
        [item.source_episode_id for item in sample.sampled_segments]
    )
    return {
        "schema": sample.schema,
        "sampled_segment_count": len(sample.sampled_segments),
        "counterfactual_pair_count": len(sample.counterfactual_pairs),
        "source_episode_ids": sorted(counts),
        "source_segment_counts": {
            str(key): value for key, value in sorted(counts.items())
        },
        "selection_excludes_target_stage_a_segments": True,
        "coverage_scope": "fixed_16_source_balanced_held_validation_segments_only",
    }


def _source_counts(values: Sequence[int]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for value in values:
        counts[int(value)] = counts.get(int(value), 0) + 1
    return counts


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReturnTemporalDispatchValidationEvaluationError(
            f"{label} must be a mapping"
        )
    return value


def _vector(value: Any, label: str) -> np.ndarray:
    try:
        result = np.asarray(value, dtype=np.float32)
    except (TypeError, ValueError) as exc:
        raise ReturnTemporalDispatchValidationEvaluationError(
            f"{label} must be numeric"
        ) from exc
    if result.ndim != 1 or not np.isfinite(result).all():
        raise ReturnTemporalDispatchValidationEvaluationError(
            f"{label} must be a finite vector"
        )
    return result


def _integer(value: Any, label: str, *, positive: bool = False) -> int:
    if isinstance(value, bool):
        raise ReturnTemporalDispatchValidationEvaluationError(
            f"{label} must be an integer"
        )
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ReturnTemporalDispatchValidationEvaluationError(
            f"{label} must be an integer"
        ) from exc
    if result != value or result < (1 if positive else 0):
        raise ReturnTemporalDispatchValidationEvaluationError(
            f"{label} is outside its valid range"
        )
    return result


def _fraction(value: Any) -> float:
    result = float(value)
    if not math.isfinite(result) or not 0.0 <= result <= 1.0:
        raise ReturnTemporalDispatchValidationEvaluationError(
            "fraction must lie in [0, 1]"
        )
    return result


def _rate(count: int, total: int) -> float:
    return 0.0 if total < 1 else float(count) / float(total)


def _floats(value: Any) -> list[float]:
    return [float(item) for item in np.asarray(value, dtype=np.float64).reshape(-1)]


__all__ = [
    "PUBLIC_LEGACY_RECONSTRUCTION_TOLERANCE",
    "REPLICA_STABILITY_TOLERANCE",
    "RETURN_TEMPORAL_DISPATCH_REQUIRED_SAMPLED_SEGMENT_COUNT",
    "RETURN_TEMPORAL_DISPATCH_RESPONSE_ACTION_SCALE_FRACTION",
    "RETURN_TEMPORAL_DISPATCH_VALIDATION_EVALUATION_SCHEMA",
    "ReturnTemporalDispatchValidationEvaluationError",
    "build_return_temporal_dispatch_metric_contract",
    "evaluate_return_temporal_dispatch_validation",
]
