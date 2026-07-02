from __future__ import annotations

from testbed.eval.terrain_residual_eval_run_plan import (
    build_residual_eval_run_plan,
)


def _current_eval_metadata() -> dict[str, object]:
    return {
        "status": "completed",
        "command": (
            "testbed/cli/eval.py --config testbed/configs/eval.yaml "
            "--num-rollouts 1 --target-cycle-gate 15 "
            "--output-dir runs/eval/current_baseline"
        ),
        "argv": [
            "testbed/cli/eval.py",
            "--config",
            "testbed/configs/eval.yaml",
            "--num-rollouts",
            "1",
            "--target-cycle-gate",
            "15",
            "--output-dir",
            "runs/eval/current_baseline",
        ],
        "paths": {
            "results_dir": (
                "runs/eval/current_baseline/results"
            ),
            "resolved_config": (
                "runs/eval/current_baseline/results/eval_resolved_config.yaml"
            ),
            "rollout_manifest": (
                "runs/eval/current_baseline/results/rollout_manifest.json"
            ),
        },
        "target_cycle_gate": 15,
        "metrics": {"n_rollouts": 1},
    }


def _predicted_ab_artifacts() -> dict[str, object]:
    return {
        "status": "present",
        "results_root": "runs/eval/predicted_ab/results",
        "artifact_files": [
            "eval_run_metadata.json",
            "experiment_manifest.json",
            "branch_run_plan.json",
            "predicted_b_rollout.json",
            "branch_comparison_report.json",
            "rollout_manifest.json",
        ],
        "branch_statuses": {
            "current_planner_baseline": "present",
            "heuristic_residual_pipeline": "present",
            "calibrated_residual_pipeline": "not_evaluated",
        },
    }


def _all_keys(value):
    if isinstance(value, dict):
        for key, nested_value in value.items():
            yield key
            yield from _all_keys(nested_value)
    elif isinstance(value, list):
        for nested_value in value:
            yield from _all_keys(nested_value)


def test_plan_builds_runnable_a_command_and_blocks_b_without_runtime_adapter():
    result = build_residual_eval_run_plan(
        current_eval_metadata=_current_eval_metadata(),
        predicted_ab_artifacts=_predicted_ab_artifacts(),
        planned_results_root="runs/eval/phase6g_real_ab_20260702",
        protected_evidence_roots=["runs/eval/current_baseline/results"],
        residual_runtime_integration_available=False,
    )

    assert result["schema"] == "terrain_residual_eval_run_plan_v1"
    assert result["source"] == "explicit_residual_eval_run_plan"
    assert result["status"] == "present"
    assert result["offline_only"] is True
    assert result["branch_order"] == [
        "current_planner_baseline",
        "heuristic_residual_pipeline",
        "calibrated_residual_pipeline",
    ]
    assert result["validation_errors"] == []
    assert result["no_overwrite_validation"]["status"] == "present"

    branch_a = result["branches"]["current_planner_baseline"]
    assert branch_a["status"] == "runnable"
    assert branch_a["command_status"] == "runnable"
    assert branch_a["planned_output_dir"] == (
        "runs/eval/phase6g_real_ab_20260702/current_planner_baseline"
    )
    assert branch_a["argv"] == [
        "testbed/cli/eval.py",
        "--config",
        "testbed/configs/eval.yaml",
        "--num-rollouts",
        "1",
        "--target-cycle-gate",
        "15",
        "--output-dir",
        "runs/eval/phase6g_real_ab_20260702/current_planner_baseline",
    ]

    branch_b = result["branches"]["heuristic_residual_pipeline"]
    assert branch_b["status"] == "not_runnable"
    assert branch_b["command_status"] == "not_runnable"
    assert branch_b["runtime_integration_status"] == "missing"
    assert branch_b["predicted_artifact_root"] == "runs/eval/predicted_ab/results"
    assert branch_b["blockers"] == [
        "missing_residual_runtime_planner_mode",
        "missing_cut_intent_to_dig_cut_token_adapter",
        "missing_residual_cut_intent_source_provider",
        "missing_simulated_branch_execution_artifacts",
    ]

    branch_c = result["branches"]["calibrated_residual_pipeline"]
    assert branch_c["status"] == "not_evaluated"
    assert branch_c["reason"] == "blocked_by_missing_gold_samples"

    all_keys = set(_all_keys(result))
    assert "pass_fail" not in all_keys
    assert "eval_success" not in all_keys
    assert "planner_success" not in all_keys
    assert "official_threshold" not in all_keys
    assert "runtime_action" not in all_keys
    assert "calibrated_fallback" not in all_keys


def test_plan_removes_adapter_blocker_when_token_adapter_is_explicitly_available():
    result = build_residual_eval_run_plan(
        current_eval_metadata=_current_eval_metadata(),
        predicted_ab_artifacts=_predicted_ab_artifacts(),
        planned_results_root="runs/eval/phase6g_real_ab_20260702",
        protected_evidence_roots=["runs/eval/current_baseline/results"],
        residual_runtime_integration_available=False,
        residual_cut_intent_token_adapter_available=True,
    )

    branch_b = result["branches"]["heuristic_residual_pipeline"]
    assert branch_b["status"] == "not_runnable"
    assert branch_b["command_status"] == "not_runnable"
    assert branch_b["runtime_integration_status"] == "missing"
    assert branch_b["cut_intent_token_adapter_status"] == "available"
    assert branch_b["blockers"] == [
        "missing_residual_runtime_planner_mode",
        "missing_residual_cut_intent_source_provider",
        "missing_simulated_branch_execution_artifacts",
    ]


def test_plan_removes_runtime_mode_and_adapter_blockers_when_explicitly_available():
    result = build_residual_eval_run_plan(
        current_eval_metadata=_current_eval_metadata(),
        predicted_ab_artifacts=_predicted_ab_artifacts(),
        planned_results_root="runs/eval/phase6g_real_ab_20260702",
        protected_evidence_roots=["runs/eval/current_baseline/results"],
        residual_runtime_integration_available=False,
        residual_runtime_planner_mode_available=True,
        residual_cut_intent_token_adapter_available=True,
    )

    branch_b = result["branches"]["heuristic_residual_pipeline"]
    assert branch_b["status"] == "not_runnable"
    assert branch_b["command_status"] == "not_runnable"
    assert branch_b["runtime_integration_status"] == "missing"
    assert branch_b["runtime_planner_mode_status"] == "available"
    assert branch_b["cut_intent_token_adapter_status"] == "available"
    assert branch_b["blockers"] == [
        "missing_residual_cut_intent_source_provider",
        "missing_simulated_branch_execution_artifacts",
    ]


def test_plan_removes_source_provider_blocker_when_explicitly_available():
    result = build_residual_eval_run_plan(
        current_eval_metadata=_current_eval_metadata(),
        predicted_ab_artifacts=_predicted_ab_artifacts(),
        planned_results_root="runs/eval/phase6g_real_ab_20260702",
        protected_evidence_roots=["runs/eval/current_baseline/results"],
        residual_runtime_integration_available=False,
        residual_runtime_planner_mode_available=True,
        residual_cut_intent_token_adapter_available=True,
        residual_cut_intent_source_provider_available=True,
    )

    branch_b = result["branches"]["heuristic_residual_pipeline"]
    assert branch_b["status"] == "not_runnable"
    assert branch_b["runtime_planner_mode_status"] == "available"
    assert branch_b["cut_intent_token_adapter_status"] == "available"
    assert branch_b["cut_intent_source_provider_status"] == "available"
    assert branch_b["blockers"] == [
        "missing_simulated_branch_execution_artifacts",
    ]


def test_plan_rejects_missing_current_eval_argv():
    metadata = _current_eval_metadata()
    metadata.pop("argv")

    result = build_residual_eval_run_plan(
        current_eval_metadata=metadata,
        predicted_ab_artifacts=_predicted_ab_artifacts(),
        planned_results_root="runs/eval/phase6g_real_ab_20260702",
        protected_evidence_roots=[],
        residual_runtime_integration_available=False,
    )

    assert result["status"] == "invalid_current_eval_metadata"
    assert result["branches"] == {}
    assert result["validation_errors"] == [
        "current_eval_metadata must include a non-empty argv list"
    ]


def test_plan_rejects_protected_root_overlap():
    result = build_residual_eval_run_plan(
        current_eval_metadata=_current_eval_metadata(),
        predicted_ab_artifacts=_predicted_ab_artifacts(),
        planned_results_root="runs/eval/current_baseline/results/phase6g",
        protected_evidence_roots=["runs/eval/current_baseline/results"],
        residual_runtime_integration_available=False,
    )

    assert result["status"] == "protected_evidence_root_overlap"
    assert result["no_overwrite_validation"]["status"] == (
        "protected_evidence_root_overlap"
    )
    assert result["branches"] == {}


def test_plan_requires_explicit_b_argv_when_runtime_integration_is_available():
    result = build_residual_eval_run_plan(
        current_eval_metadata=_current_eval_metadata(),
        predicted_ab_artifacts=_predicted_ab_artifacts(),
        planned_results_root="runs/eval/phase6g_real_ab_20260702",
        protected_evidence_roots=[],
        residual_runtime_integration_available=True,
    )

    assert result["status"] == "invalid_residual_runtime_integration"
    assert result["branches"] == {}
    assert result["validation_errors"] == [
        "heuristic_branch_argv must be explicit when residual runtime integration is available"
    ]
