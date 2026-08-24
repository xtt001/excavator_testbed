from __future__ import annotations

from testbed.eval.dig_receding_horizon_runtime import (
    build_diagnostic_contract,
    diagnostic_code_paths,
    run_diagnostic_dry_run,
)


def test_contract_freezes_only_two_dispatch_strategies_and_short_projection() -> None:
    contract = build_diagnostic_contract(variant_count=112, bootstrap_resamples=2000)

    assert tuple(contract["dispatch_strategies"]) == ("legacy", "latest")
    assert contract["dispatch_strategies"]["latest"]["default_enabled"] is False
    assert contract["dispatch_strategies"]["latest"]["request_local"] is True
    assert contract["projection"]["horizons"] == [5, 10]
    assert contract["data"]["dispatch_observation_frames_per_variant"] == 100
    assert contract["projection"]["recorded_state_anchor_count_per_variant"] == 91
    assert contract["projection"]["long_horizon_100_step_allowed"] is False
    assert contract["thresholds"] == {
        "latest_direction_success_min": 0.8,
        "latest_ranking_accuracy_min": 0.8,
        "latest_improvement_min_fraction": 0.15,
        "latest_projected_tip_separation_p10_min_m": 0.02,
        "action_support_violation_rate_delta_max": 0.01,
        "bootstrap_ci95_low_min": 0.0,
    }


def test_dry_run_declares_no_optimizer_backend_unity_or_action() -> None:
    result = run_diagnostic_dry_run(variant_count=112, bootstrap_resamples=2000)

    assert result["status"] == "dry_run"
    assert result["optimizer_created"] is False
    assert result["backend_called"] is False
    assert result["unity_started"] is False
    assert result["action_sent"] is False


def test_code_lineage_includes_dirty_direct_inference_dependencies() -> None:
    paths = set(diagnostic_code_paths())

    assert {
        "testbed/policies/act/adapter.py",
        "testbed/policies/act/detr/main.py",
        "testbed/policies/act/inference.py",
        "testbed/policies/dig_effect_fk.py",
        "testbed/policies/dig_transition_predictor.py",
        "testbed/eval/dig_receding_horizon_artifacts.py",
        "testbed/eval/temporal_dispatch_contract.py",
    } <= paths
