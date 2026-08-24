from __future__ import annotations

import numpy as np

from testbed.eval.dig_diffusion_probe_metrics import (
    classify_minimal_dp_probe,
    condition_distribution_metrics,
    training_seed_direction_consistency,
)


def test_goal_effect_exceeds_diffusion_noise_under_paired_noise() -> None:
    # [train_seed, noise_seed, variant, frame, action]
    base = np.zeros((3, 3, 2, 4, 4), dtype=np.float32)
    alternate = base.copy()
    alternate[..., 0] = 1.0
    zero = base.copy()
    shuffled = base.copy()
    # Small variation across inference-noise seeds.
    alternate[:, 1, ..., 0] += 0.01
    alternate[:, 2, ..., 0] -= 0.01

    result = condition_distribution_metrics(
        base_correct=base,
        alternate_correct=alternate,
        zero=zero,
        shuffled=shuffled,
        action_std=np.ones(4, dtype=np.float32),
    )

    assert result["goal_effect_first_action_l2_p10"] > 0.9
    assert result["noise_effect_first_action_l2_p95"] < 0.03
    assert result["noise_p95_below_goal_p10"] is True
    assert result["goal_response_fraction"] == 1.0


def test_training_seed_direction_consistency_requires_aligned_goal_deltas() -> None:
    delta = np.zeros((3, 2, 4, 4), dtype=np.float32)
    delta[..., 0] = 1.0

    result = training_seed_direction_consistency(delta, cosine_threshold=0.5)

    assert result["consistent_fraction"] == 1.0
    delta[2, ..., 0] = -1.0
    failed = training_seed_direction_consistency(delta, cosine_threshold=0.5)
    assert failed["consistent_fraction"] == 0.0


def _passing_metrics() -> dict:
    return {
        "valid": True,
        "direction_success": 0.85,
        "ranking_accuracy": 0.82,
        "projected_tip_separation_p10_m": 0.03,
        "bootstrap_ci95_low": 0.01,
        "action_support_violation_rate": 0.08,
        "act_reference_support_violation_rate": 0.0765,
        "nonfinite_count": 0,
        "noise_p95_below_goal_p10": True,
        "training_seed_consistent_fraction": 0.85,
    }


def test_probe_can_pass_metrics_but_remains_non_promotable() -> None:
    decision = classify_minimal_dp_probe(metrics=_passing_metrics(), invalid_reasons=())

    assert decision["classification"] == "minimal_dp_probe_response_promising"
    assert decision["promotion_eligible"] is False
    assert decision["unity_allowed"] is False
    assert decision["production_defaults_changed"] is False


def test_probe_blocks_action_support_regression() -> None:
    metrics = _passing_metrics()
    metrics["action_support_violation_rate"] = 0.10

    decision = classify_minimal_dp_probe(metrics=metrics, invalid_reasons=())

    assert decision["classification"] == "minimal_dp_probe_action_support_blocked"
    assert decision["unity_allowed"] is False
