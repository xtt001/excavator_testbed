from __future__ import annotations

import json
from pathlib import Path

import yaml

from testbed.eval.terrain_residual_real_ab_smoke_comparison import (
    write_current_planner_bounded_smoke_request,
    write_real_ab_bounded_smoke_comparison,
)


def _baseline_config(path: Path) -> None:
    payload = {
        "eval": {
            "results_dir": "runs/eval/current_baseline/results",
            "video_dir": "runs/eval/current_baseline/videos",
            "rollout_log_dir": "runs/eval/current_baseline/results/rollouts",
            "target_cycle_gate": 15,
            "target_cycle_gate_terminal_hold_steps": 100,
            "save_video": True,
        },
        "policy": {
            "class": "primitive_planner_act",
            "dig_cut_planner": {
                "enabled": True,
                "mode": "operator_prior_sweep_belief",
                "fallback_mode": "raise",
                "hold_token_until_skill_exit": True,
                "prior_path": "runs/prior.json",
            },
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _current_eval_metadata(config_path: Path) -> dict[str, object]:
    return {
        "status": "completed",
        "argv": [
            "testbed/cli/eval.py",
            "--config",
            str(config_path),
            "--num-rollouts",
            "1",
            "--target-cycle-gate",
            "15",
            "--output-dir",
            "runs/eval/current_baseline",
        ],
    }


def _write_result_root(
    root: Path,
    *,
    branch_name: str,
    mode: str,
    target_cycle_gate: int = 1,
    terminal_hold_steps: int = 0,
    stop_reason: str = "target_cycle_gate_reached",
    line_count: int = 3,
    residual_source_path: str | None = None,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    config = {
        "eval": {
            "target_cycle_gate": target_cycle_gate,
            "target_cycle_gate_terminal_hold_steps": terminal_hold_steps,
            "save_video": False,
        },
        "policy": {
            "class": "primitive_planner_act",
            "dig_cut_planner": {
                "enabled": True,
                "mode": mode,
                "fallback_mode": "raise",
                "hold_token_until_skill_exit": mode != "residual_cut_intent",
                "prior_path": "" if mode == "residual_cut_intent" else "runs/prior.json",
            },
        },
    }
    if residual_source_path is not None:
        config["policy"]["dig_cut_planner"][
            "residual_cut_intent_source_path"
        ] = residual_source_path
    (root / "eval_resolved_config.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False),
        encoding="utf-8",
    )
    (root / "eval_run_metadata.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "error": None,
                "argv": [
                    "testbed/cli/eval.py",
                    "--config",
                    f"requests/{branch_name}.yaml",
                    "--num-rollouts",
                    "1",
                    "--target-cycle-gate",
                    str(target_cycle_gate),
                    "--no-video",
                    "--output-dir",
                    f"runs/eval/{branch_name}",
                ],
                "target_cycle_gate": target_cycle_gate,
                "paths": {
                    "results_dir": str(root),
                    "resolved_config": str(root / "eval_resolved_config.yaml"),
                    "metrics_json": str(root / "metrics.json"),
                    "rollout_manifest": str(root / "rollout_manifest.json"),
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (root / "metrics.json").write_text(
        json.dumps(
            {
                "n_rollouts": 1,
                "success_rate": 0.0,
                "avg_episode_len": 100.0,
                "extra": {
                    "target_cycle_gate": target_cycle_gate,
                    "target_cycle_gate_terminal_hold_steps": terminal_hold_steps,
                    "target_cycle_gate_success_rate": 1.0,
                    "target_cycle_completed_dump_mean": 1.0,
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (root / "rollout_manifest.json").write_text(
        json.dumps(
            {
                "n_rollouts": 1,
                "rollouts": [
                    {
                        "target_cycle_gate": target_cycle_gate,
                        "target_cycle_completed_dump_count": 1,
                        "target_cycle_gate_success": 1,
                        "target_cycle_gate_stop_reason": stop_reason,
                        "completed_dump_count": 0,
                        "primitive_cycle_index": 0,
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    rollouts = root / "rollouts"
    rollouts.mkdir()
    (rollouts / "rollout_000_summary.json").write_text(
        json.dumps(
            {
                "target_cycle_gate": target_cycle_gate,
                "target_cycle_completed_dump_count": 1,
                "target_cycle_gate_success": 1,
                "target_cycle_gate_stop_reason": stop_reason,
                "completed_dump_count": 0,
                "primitive_cycle_index": 0,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (rollouts / "rollout_000.jsonl").write_text(
        "".join(json.dumps({"step": index}) + "\n" for index in range(line_count)),
        encoding="utf-8",
    )
    return root


def test_current_planner_bounded_request_preserves_a_branch_and_sets_zero_hold(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    baseline_config = tmp_path / "configs/current_eval.yaml"
    _baseline_config(baseline_config)
    request_root = tmp_path / "phase6g_h_request"
    planned_results_root = tmp_path / "phase6g_h_real_ab"

    result = write_current_planner_bounded_smoke_request(
        current_eval_metadata=_current_eval_metadata(baseline_config),
        request_root=request_root,
        planned_results_root=planned_results_root,
        protected_evidence_roots=[tmp_path / "protected/results"],
        target_cycle_gate=1,
    )

    assert result["schema"] == "terrain_residual_current_bounded_smoke_request_v1"
    assert result["source"] == "explicit_current_planner_bounded_smoke_request"
    assert result["status"] == "present"
    assert result["branch"] == "current_planner_baseline"
    assert result["runtime_config"] == {
        "eval.target_cycle_gate_terminal_hold_steps": 0,
        "eval.target_cycle_gate": 1,
        "eval.save_video": False,
        "dig_cut_planner.mode": "operator_prior_sweep_belief",
    }
    assert result["written_files"] == [
        "current_planner_baseline_eval_config.yaml",
        "current_planner_baseline_invocation.json",
    ]
    assert planned_results_root.exists() is False

    generated_config = yaml.safe_load(
        (request_root / "current_planner_baseline_eval_config.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert generated_config["eval"]["target_cycle_gate_terminal_hold_steps"] == 0
    assert generated_config["eval"]["target_cycle_gate"] == 1
    assert generated_config["eval"]["save_video"] is False
    assert generated_config["policy"]["dig_cut_planner"]["mode"] == (
        "operator_prior_sweep_belief"
    )
    assert generated_config["policy"]["dig_cut_planner"][
        "hold_token_until_skill_exit"
    ] is True

    invocation = json.loads(
        (request_root / "current_planner_baseline_invocation.json").read_text(
            encoding="utf-8"
        )
    )
    assert invocation["argv"] == [
        "testbed/cli/eval.py",
        "--config",
        str(request_root / "current_planner_baseline_eval_config.yaml"),
        "--num-rollouts",
        "1",
        "--target-cycle-gate",
        "1",
        "--output-dir",
        str(planned_results_root / "current_planner_baseline"),
        "--no-video",
    ]


def test_real_ab_bounded_smoke_comparison_reads_artifacts_and_labels_limits(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    a_root = _write_result_root(
        tmp_path / "real_ab/current_planner_baseline/results",
        branch_name="current_planner_baseline",
        mode="operator_prior_sweep_belief",
        line_count=11,
    )
    b_root = _write_result_root(
        tmp_path / "phase6g_g_b/heuristic_residual_pipeline/results",
        branch_name="heuristic_residual_pipeline",
        mode="residual_cut_intent",
        residual_source_path="predicted_ab/residual_cut_intent_runtime_source.json",
        line_count=13,
    )
    output_path = tmp_path / "real_ab/comparison/real_ab_bounded_smoke_comparison.json"

    result = write_real_ab_bounded_smoke_comparison(
        current_results_root=a_root,
        heuristic_results_root=b_root,
        output_path=output_path,
        protected_evidence_roots=[tmp_path / "protected/results"],
        expected_target_cycle_gate=1,
        expected_terminal_hold_steps=0,
    )

    assert result["schema"] == "terrain_residual_real_ab_bounded_smoke_comparison_v1"
    assert result["source"] == "explicit_real_ab_bounded_smoke_comparison"
    assert result["status"] == "present"
    assert result["branch_order"] == [
        "current_planner_baseline",
        "heuristic_residual_pipeline",
        "calibrated_residual_pipeline",
    ]
    assert result["comparison_scope"] == {
        "evidence_scope": "bounded_one_cycle_smoke",
        "full_phase6_success_claim": "not_claimed",
        "official_pass_fail_status": "defined_by_terrain_residual_pass_fail_v1",
        "production_readiness_status": "not_claimed",
        "calibrated_fallback_status": "not_invented",
    }
    assert result["branches"]["current_planner_baseline"]["config_facts"][
        "dig_cut_planner.mode"
    ] == "operator_prior_sweep_belief"
    assert result["branches"]["heuristic_residual_pipeline"]["config_facts"][
        "dig_cut_planner.mode"
    ] == "residual_cut_intent"
    assert result["branches"]["heuristic_residual_pipeline"]["config_facts"][
        "dig_cut_planner.residual_cut_intent_source_path"
    ] == "predicted_ab/residual_cut_intent_runtime_source.json"
    assert result["branches"]["current_planner_baseline"]["rollout_line_count"] == 11
    assert result["branches"]["heuristic_residual_pipeline"]["rollout_line_count"] == 13
    assert result["branches"]["calibrated_residual_pipeline"] == {
        "branch_name": "calibrated_residual_pipeline",
        "status": "not_evaluated",
        "reason": "blocked_by_missing_gold_samples",
    }
    assert result["non_goal_statuses"] == {
        "production_planner_integration_status": "not_integrated",
        "rollout_review_schema_integration_status": "not_integrated",
        "runtime_action_status": "not_created",
        "command_space_control_status": "not_created",
        "official_success_semantics_status": "defined_by_terrain_residual_pass_fail_v1",
        "official_default_status": "defined_by_terrain_residual_target_v1",
        "official_threshold_status": "defined_by_a_baseline_anchored_v0",
        "calibrated_model_fallback_status": "not_invented",
    }
    assert output_path.is_file()
    assert json.loads(output_path.read_text(encoding="utf-8")) == result


def test_real_ab_bounded_smoke_comparison_labels_multi_cycle_gate_scope(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    a_root = _write_result_root(
        tmp_path / "real_ab/current_planner_baseline/results",
        branch_name="current_planner_baseline",
        mode="operator_prior_sweep_belief",
        target_cycle_gate=2,
    )
    b_root = _write_result_root(
        tmp_path / "real_ab/heuristic_residual_pipeline/results",
        branch_name="heuristic_residual_pipeline",
        mode="residual_cut_intent",
        target_cycle_gate=2,
        residual_source_path="predicted_ab/residual_cut_intent_runtime_source.json",
    )

    result = write_real_ab_bounded_smoke_comparison(
        current_results_root=a_root,
        heuristic_results_root=b_root,
        output_path=tmp_path / "real_ab/comparison/gate2_comparison.json",
        protected_evidence_roots=[],
        expected_target_cycle_gate=2,
        expected_terminal_hold_steps=0,
    )

    assert result["status"] == "present"
    assert result["comparison_scope"]["evidence_scope"] == (
        "bounded_multi_cycle_smoke"
    )
    assert result["branches"]["current_planner_baseline"]["target_cycle_gate"] == 2
    assert result["branches"]["heuristic_residual_pipeline"]["target_cycle_gate"] == 2


def test_real_ab_bounded_smoke_comparison_rejects_gate_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    a_root = _write_result_root(
        tmp_path / "real_ab/current_planner_baseline/results",
        branch_name="current_planner_baseline",
        mode="operator_prior_sweep_belief",
        target_cycle_gate=2,
    )
    b_root = _write_result_root(
        tmp_path / "phase6g_g_b/heuristic_residual_pipeline/results",
        branch_name="heuristic_residual_pipeline",
        mode="residual_cut_intent",
    )

    result = write_real_ab_bounded_smoke_comparison(
        current_results_root=a_root,
        heuristic_results_root=b_root,
        output_path=tmp_path / "comparison.json",
        protected_evidence_roots=[],
        expected_target_cycle_gate=1,
        expected_terminal_hold_steps=0,
    )

    assert result["status"] == "invalid_branch_artifacts"
    assert result["validation_errors"] == [
        "current_planner_baseline target_cycle_gate must be 1"
    ]
    assert (tmp_path / "comparison.json").exists() is False
