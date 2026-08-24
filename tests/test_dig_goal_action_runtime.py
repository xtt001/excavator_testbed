from __future__ import annotations

from testbed.eval.dig_goal_action_identifiability_runtime import (
    build_precheck_contract,
    run_identifiability_dry_run,
)


def test_precheck_contract_freezes_data_gate_before_training() -> None:
    contract = build_precheck_contract(bootstrap_resamples=2000)

    assert contract["default_enabled"] is False
    assert contract["data"]["frame_scope"] == "primitive_t0_only"
    assert contract["data"]["action_horizon"] == 100
    assert contract["data"]["planned_variant_count"] == 112
    assert contract["matching"]["qpos_max_abs"] == 0.005
    assert contract["matching"]["qvel_max_abs"] == 0.02
    assert contract["gates"]["minimum_covered_variants"] == 100
    assert contract["gates"]["minimum_different_goal_pairs"] == 100
    assert contract["hard_boundaries"]["act_dp_training_allowed_in_precheck"] is False
    assert contract["hard_boundaries"]["unity_start_allowed"] is False


def test_precheck_dry_run_never_starts_models_or_unity() -> None:
    result = run_identifiability_dry_run(bootstrap_resamples=2000)

    assert result["status"] == "dry_run"
    assert result["act_dp_training_started"] is False
    assert result["optimizer_created"] is False
    assert result["backend_called"] is False
    assert result["unity_started"] is False
    assert result["action_sent"] is False
