"""Distribution, seed-consistency, and non-promotion gates for the DP probe."""

from __future__ import annotations

import itertools
import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np


def condition_distribution_metrics(
    *,
    base_correct: np.ndarray,
    alternate_correct: np.ndarray,
    zero: np.ndarray,
    shuffled: np.ndarray,
    action_std: np.ndarray,
) -> dict[str, Any]:
    arrays = {
        name: np.asarray(value, dtype=np.float64)
        for name, value in (
            ("base_correct", base_correct),
            ("alternate_correct", alternate_correct),
            ("zero", zero),
            ("shuffled", shuffled),
        )
    }
    shape = arrays["base_correct"].shape
    if len(shape) != 5 or shape[0] != 3 or shape[1] < 2 or shape[-1] != 4:
        raise ValueError("condition actions must be [3,noise,variant,frame,4]")
    if any(value.shape != shape for value in arrays.values()):
        raise ValueError("condition action arrays must align")
    scale = np.asarray(action_std, dtype=np.float64).reshape(-1)
    if scale.shape != (4,) or not np.isfinite(scale).all() or np.any(scale <= 0.0):
        raise ValueError("condition metrics require positive 4D action_std")
    nonfinite = sum(
        int(np.count_nonzero(~np.isfinite(value))) for value in arrays.values()
    )
    goal_delta = arrays["alternate_correct"] - arrays["base_correct"]
    zero_delta = arrays["alternate_correct"] - arrays["zero"]
    shuffle_delta = arrays["alternate_correct"] - arrays["shuffled"]
    goal_norm = np.linalg.norm(goal_delta, axis=-1)
    zero_norm = np.linalg.norm(zero_delta, axis=-1)
    shuffle_norm = np.linalg.norm(shuffle_delta, axis=-1)
    threshold = scale * 0.05
    responsive = np.any(np.abs(goal_delta) > threshold, axis=-1)
    noise_values = []
    for train_seed in range(shape[0]):
        for left, right in itertools.combinations(range(shape[1]), 2):
            delta = (
                arrays["alternate_correct"][train_seed, left]
                - arrays["alternate_correct"][train_seed, right]
            )
            noise_values.append(np.linalg.norm(delta, axis=-1).reshape(-1))
    noise_norm = np.concatenate(noise_values)
    goal_p10 = float(np.quantile(goal_norm, 0.10))
    noise_p95 = float(np.quantile(noise_norm, 0.95))
    return {
        "schema": "minimal_dp_condition_distribution_metrics_v1",
        "goal_effect_first_action_l2_p10": goal_p10,
        "goal_effect_first_action_l2_p50": float(np.median(goal_norm)),
        "goal_effect_first_action_l2_p90": float(np.quantile(goal_norm, 0.90)),
        "zero_effect_first_action_l2_p50": float(np.median(zero_norm)),
        "shuffled_effect_first_action_l2_p50": float(np.median(shuffle_norm)),
        "noise_effect_first_action_l2_p50": float(np.median(noise_norm)),
        "noise_effect_first_action_l2_p95": noise_p95,
        "noise_p95_below_goal_p10": bool(noise_p95 < goal_p10),
        "goal_response_fraction": float(np.mean(responsive)),
        "response_threshold": threshold.tolist(),
        "nonfinite_count": nonfinite,
    }


def training_seed_direction_consistency(
    goal_delta_by_seed: np.ndarray, *, cosine_threshold: float
) -> dict[str, Any]:
    values = np.asarray(goal_delta_by_seed, dtype=np.float64)
    if values.ndim != 4 or values.shape[0] != 3 or values.shape[-1] != 4:
        raise ValueError("training seed goal deltas must be [3,variant,frame,4]")
    if not np.isfinite(values).all():
        raise ValueError("training seed goal deltas must be finite")
    pair_cosines = []
    for left, right in itertools.combinations(range(3), 2):
        left_value = values[left]
        right_value = values[right]
        numerator = np.sum(left_value * right_value, axis=-1)
        denominator = np.linalg.norm(left_value, axis=-1) * np.linalg.norm(
            right_value, axis=-1
        )
        cosine = np.divide(
            numerator,
            denominator,
            out=np.full_like(numerator, -1.0),
            where=denominator > 1.0e-12,
        )
        pair_cosines.append(cosine)
    stacked = np.stack(pair_cosines, axis=0)
    consistent = np.all(stacked >= float(cosine_threshold), axis=0)
    return {
        "schema": "minimal_dp_training_seed_direction_consistency_v1",
        "cosine_threshold": float(cosine_threshold),
        "consistent_fraction": float(np.mean(consistent)),
        "pairwise_cosine_p10": float(np.quantile(stacked, 0.10)),
        "pairwise_cosine_p50": float(np.median(stacked)),
        "pairwise_cosine_p90": float(np.quantile(stacked, 0.90)),
    }


def classify_minimal_dp_probe(
    *, metrics: Mapping[str, Any], invalid_reasons: Sequence[str]
) -> dict[str, Any]:
    reasons = tuple(str(value) for value in invalid_reasons if str(value))
    if reasons or not bool(metrics.get("valid", False)):
        classification = "invalid_minimal_dp_probe"
        checks: dict[str, bool] = {}
    else:
        support_delta = float(metrics["action_support_violation_rate"]) - float(
            metrics["act_reference_support_violation_rate"]
        )
        checks = {
            "direction_at_least_80pct": float(metrics["direction_success"]) >= 0.80,
            "ranking_at_least_80pct": float(metrics["ranking_accuracy"]) >= 0.80,
            "separation_p10_at_least_2cm": float(
                metrics["projected_tip_separation_p10_m"]
            )
            >= 0.02,
            "bootstrap_positive": float(metrics["bootstrap_ci95_low"]) > 0.0,
            "action_support_not_worse_by_more_than_1pp": support_delta <= 0.01,
            "nonfinite_absent": int(metrics["nonfinite_count"]) == 0,
            "noise_below_goal": bool(metrics["noise_p95_below_goal_p10"]),
            "training_seed_consistency_at_least_80pct": float(
                metrics["training_seed_consistent_fraction"]
            )
            >= 0.80,
        }
        if not checks["action_support_not_worse_by_more_than_1pp"]:
            classification = "minimal_dp_probe_action_support_blocked"
        elif not checks["noise_below_goal"]:
            classification = "minimal_dp_probe_noise_dominates"
        elif all(checks.values()):
            classification = "minimal_dp_probe_response_promising"
        else:
            classification = "minimal_dp_probe_goal_response_insufficient"
    return {
        "schema": "minimal_dig_diffusion_probe_decision_v1",
        "status": "completed",
        "classification": classification,
        "checks": checks,
        "invalid_reasons": list(reasons),
        "diagnostic_only": True,
        "data_identifiability_precheck_passed": False,
        "promotion_eligible": False,
        "unity_allowed": False,
        "next_experiment": "paired_goal_action_demonstrations",
        "production_defaults_changed": False,
        "act_modified": False,
        "soil_model_trained": False,
        "unity_started": False,
        "action_sent": False,
    }


def source_episode_bootstrap_metric(
    rows: Sequence[Mapping[str, Any]],
    *,
    key: str,
    resamples: int,
    seed: int,
) -> dict[str, Any]:
    if resamples < 100:
        raise ValueError("DP metric bootstrap requires at least 100 resamples")
    grouped: dict[int, list[float]] = {}
    for row in rows:
        grouped.setdefault(int(row["source_episode_id"]), []).append(float(row[key]))
    sources = np.asarray(sorted(grouped), dtype=np.int64)
    if sources.size < 2:
        raise ValueError("DP metric bootstrap requires at least two sources")
    rng = np.random.default_rng(int(seed))
    samples = np.empty(resamples, dtype=np.float64)
    for index in range(resamples):
        sampled_sources = rng.choice(sources, size=sources.size, replace=True)
        means = []
        for source_value in sampled_sources:
            values = np.asarray(grouped[int(source_value)], dtype=np.float64)
            means.append(
                float(np.mean(rng.choice(values, size=values.size, replace=True)))
            )
        samples[index] = float(np.mean(means))
    point = float(np.mean([np.mean(grouped[int(source)]) for source in sources]))
    return {
        "point": point,
        "ci95_low": float(np.quantile(samples, 0.025)),
        "ci95_high": float(np.quantile(samples, 0.975)),
        "source_count": int(sources.size),
        "episode_count": len(rows),
        "resamples": resamples,
        "seed": seed,
    }


def _finite(value: Any, label: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


__all__ = [
    "classify_minimal_dp_probe",
    "condition_distribution_metrics",
    "source_episode_bootstrap_metric",
    "training_seed_direction_consistency",
]
