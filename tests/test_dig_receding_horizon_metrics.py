from __future__ import annotations

import numpy as np

from testbed.eval.dig_receding_horizon_metrics import (
    classify_dispatch_diagnostic,
    hierarchical_paired_source_episode_bootstrap,
    projected_own_goal_metrics,
)


def test_projected_metrics_measure_each_arms_direction_ranking_and_separation() -> None:
    initial = np.asarray([0.0, 0.0, 0.0], dtype=np.float64)
    baseline_path = np.asarray([[-0.05, 0.0, 0.0], [-0.10, 0.0, 0.0]])
    alternate_path = np.asarray([[0.05, 0.0, 0.0], [0.10, 0.0, 0.0]])

    result = projected_own_goal_metrics(
        initial_tip_xyz_m=initial,
        baseline_tip_xyz_m=baseline_path,
        alternate_tip_xyz_m=alternate_path,
        baseline_goal={"entry_xz_m": [-1.0, 0.0], "exit_xz_m": [-1.2, 0.0]},
        alternate_goal={"entry_xz_m": [1.0, 0.0], "exit_xz_m": [1.2, 0.0]},
    )

    assert result["direction_success"] == 1.0
    assert result["ranking_accuracy"] == 1.0
    assert np.isclose(result["projected_tip_separation_m"], 0.2)


def test_paired_bootstrap_resamples_sources_then_episodes() -> None:
    rows = []
    for source in (3, 6, 7):
        for episode in range(4):
            rows.append(
                {
                    "source_episode_id": source,
                    "primitive_episode_id": source * 100 + episode,
                    "legacy": {"direction_success": 0.0, "ranking_accuracy": 0.0},
                    "latest": {"direction_success": 1.0, "ranking_accuracy": 1.0},
                }
            )

    result = hierarchical_paired_source_episode_bootstrap(
        rows,
        metrics=("direction_success", "ranking_accuracy"),
        resamples=500,
        seed=20260823,
    )

    assert result["source_count"] == 3
    assert result["episode_count"] == 12
    for metric in ("direction_success", "ranking_accuracy"):
        assert result["metrics"][metric]["point_difference"] == 1.0
        assert result["metrics"][metric]["ci95_low"] == 1.0
        assert result["metrics"][metric]["ci95_high"] == 1.0


def _passing_metrics() -> tuple[dict, dict]:
    pair_metrics = {
        "valid": True,
        "raw_goal_response": {"legacy": True, "latest": True},
        "horizon_10": {
            "legacy": {
                "direction_success": 0.60,
                "ranking_accuracy": 0.60,
                "projected_tip_separation_p10_m": 0.01,
                "action_support_violation_rate": 0.02,
            },
            "latest": {
                "direction_success": 0.85,
                "ranking_accuracy": 0.82,
                "projected_tip_separation_p10_m": 0.03,
                "action_support_violation_rate": 0.025,
            },
        },
    }
    bootstrap = {
        "metrics": {
            name: {"ci95_low": 0.01, "ci95_high": 0.20}
            for name in (
                "direction_success",
                "ranking_accuracy",
                "projected_tip_separation_m",
            )
        }
    }
    return pair_metrics, bootstrap


def test_decision_marks_latest_promising_only_when_every_gate_passes() -> None:
    pair_metrics, bootstrap = _passing_metrics()

    result = classify_dispatch_diagnostic(
        pair_metrics=pair_metrics,
        bootstrap=bootstrap,
        invalid_reasons=(),
    )

    assert result["classification"] == "latest_feedback_dispatch_promising"
    assert (
        result["next_experiment"] == "minimal_unity_single_shovel_dispatch_causal_test"
    )
    assert result["production_defaults_changed"] is False


def test_decision_fails_closed_before_interpreting_metrics() -> None:
    pair_metrics, bootstrap = _passing_metrics()

    result = classify_dispatch_diagnostic(
        pair_metrics=pair_metrics,
        bootstrap=bootstrap,
        invalid_reasons=("support_missing",),
    )

    assert result["classification"] == "invalid_diagnostic"


def test_decision_routes_failed_latest_to_act_vs_diffusion() -> None:
    pair_metrics, bootstrap = _passing_metrics()
    pair_metrics["horizon_10"]["latest"]["ranking_accuracy"] = 0.79

    result = classify_dispatch_diagnostic(
        pair_metrics=pair_metrics,
        bootstrap=bootstrap,
        invalid_reasons=(),
    )

    assert result["classification"] == "temporal_dispatch_not_primary"
    assert result["next_experiment"] == "goal_conditioned_act_vs_diffusion_policy"


def test_decision_detects_raw_goal_condition_regression() -> None:
    pair_metrics, bootstrap = _passing_metrics()
    pair_metrics["raw_goal_response"] = {"legacy": False, "latest": False}

    result = classify_dispatch_diagnostic(
        pair_metrics=pair_metrics,
        bootstrap=bootstrap,
        invalid_reasons=(),
    )

    assert result["classification"] == "goal_condition_response_regressed"
