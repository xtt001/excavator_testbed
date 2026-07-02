from __future__ import annotations

import json
import tomllib
from pathlib import Path

import yaml

from testbed.cli.terrain_residual_b_branch_eval_request import main
from testbed.eval.terrain_residual_b_branch_eval_request import (
    write_residual_b_branch_eval_request,
)
from testbed.planner.primitive.token.residual_cut_intent_source import (
    RESIDUAL_CUT_INTENT_RUNTIME_SOURCE_SCHEMA,
)


EXPECTED_REQUEST_FILES = [
    "heuristic_residual_pipeline_eval_config.yaml",
    "heuristic_residual_pipeline_invocation.json",
    "residual_eval_run_plan.json",
]


def _baseline_config(path: Path) -> None:
    payload = {
        "task": {"name": "agx_excavation_teleop", "scenario_id": "s0_truck"},
        "eval": {
            "results_dir": "runs/eval/current_baseline/results",
            "video_dir": "runs/eval/current_baseline/videos",
            "rollout_log_dir": "runs/eval/current_baseline/results/rollouts",
            "target_cycle_gate": 15,
            "save_video": False,
        },
        "policy": {
            "class": "primitive_planner_act",
            "action_dim": 4,
            "dig_cut_planner": {
                "enabled": True,
                "mode": "operator_prior_sweep_belief",
                "prior_path": "testbed/configs/planner_priors/legacy_prior.json",
                "fallback_mode": "conservative_pose",
                "hold_token_until_skill_exit": True,
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
        "paths": {
            "results_dir": "runs/eval/current_baseline/results",
            "resolved_config": (
                "runs/eval/current_baseline/results/eval_resolved_config.yaml"
            ),
        },
        "target_cycle_gate": 15,
    }


def _predicted_artifact_root(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    metadata = {
        "status": "present",
        "artifact_files": [
            "eval_run_metadata.json",
            "experiment_manifest.json",
            "branch_run_plan.json",
            "predicted_b_rollout.json",
            "residual_cut_intent_runtime_source.json",
            "branch_comparison_report.json",
            "rollout_manifest.json",
        ],
        "branch_statuses": {
            "current_planner_baseline": "present",
            "heuristic_residual_pipeline": "present",
            "calibrated_residual_pipeline": "not_evaluated",
        },
    }
    (root / "eval_run_metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )
    return root


def _runtime_source(
    path: Path,
    *,
    status: str = "present",
    cycle_indices: tuple[int, ...] = (0,),
) -> Path:
    payload = {
        "schema": RESIDUAL_CUT_INTENT_RUNTIME_SOURCE_SCHEMA,
        "source": "explicit_residual_cut_intent_runtime_source",
        "status": status,
        "offline_only": True,
        "plans": [
            {
                "cycle_index": cycle_index,
                "cut_intent_candidate_id": "cut_candidate_000009",
                "plan": {
                    "status": "present",
                    "source": "explicit_residual_cut_intent_dig_cut_token",
                    "raw_fields": {"operator_cut_valid": 1},
                    "dig_cut_tokens": [0.1] * 10,
                },
            }
            for cycle_index in cycle_indices
        ],
        "validation_errors": [],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def test_request_writer_materializes_runner_consumable_b_branch_invocation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    baseline_config = tmp_path / "configs/current_eval.yaml"
    _baseline_config(baseline_config)
    predicted_root = _predicted_artifact_root(tmp_path / "predicted_ab/results")
    runtime_source = _runtime_source(
        predicted_root / "residual_cut_intent_runtime_source.json"
    )
    request_root = tmp_path / "phase6g_f_request"
    planned_results_root = tmp_path / "phase6g_f_real_ab"

    result = write_residual_b_branch_eval_request(
        current_eval_metadata=_current_eval_metadata(baseline_config),
        predicted_ab_artifact_root=predicted_root,
        runtime_source_path=runtime_source,
        request_root=request_root,
        planned_results_root=planned_results_root,
        protected_evidence_roots=[tmp_path / "current_baseline/results"],
    )

    assert result["schema"] == "terrain_residual_b_branch_eval_request_v1"
    assert result["source"] == "explicit_residual_b_branch_eval_request"
    assert result["status"] == "present"
    assert result["offline_only"] is True
    assert result["written_files"] == EXPECTED_REQUEST_FILES
    assert result["request_root"] == str(request_root)
    assert result["planned_results_root"] == str(planned_results_root)
    assert result["branch"] == "heuristic_residual_pipeline"
    assert result["runtime_config"] == {
        "eval.target_cycle_gate_terminal_hold_steps": 0,
        "dig_cut_planner.enabled": True,
        "dig_cut_planner.mode": "residual_cut_intent",
        "dig_cut_planner.residual_cut_intent_source_path": str(runtime_source),
        "dig_cut_planner.fallback_mode": "raise",
        "dig_cut_planner.hold_token_until_skill_exit": False,
        "dig_cut_planner.prior_path": "",
    }
    assert result["runtime_source"]["status"] == "present"
    assert result["runtime_source"]["plan_count"] == 1
    assert result["runtime_source"]["candidate_ids"] == ["cut_candidate_000009"]
    assert result["expected_branch_outputs"]["results_dir"] == (
        str(planned_results_root / "heuristic_residual_pipeline" / "results")
    )
    assert result["execution_status"] == "not_run"
    assert planned_results_root.exists() is False

    generated_config = yaml.safe_load(
        (request_root / "heuristic_residual_pipeline_eval_config.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert generated_config["eval"]["target_cycle_gate_terminal_hold_steps"] == 0
    dig_cut_planner = generated_config["policy"]["dig_cut_planner"]
    assert dig_cut_planner["enabled"] is True
    assert dig_cut_planner["mode"] == "residual_cut_intent"
    assert dig_cut_planner["residual_cut_intent_source_path"] == str(runtime_source)
    assert dig_cut_planner["fallback_mode"] == "raise"
    assert dig_cut_planner["hold_token_until_skill_exit"] is False
    assert dig_cut_planner["prior_path"] == ""

    invocation = json.loads(
        (request_root / "heuristic_residual_pipeline_invocation.json").read_text(
            encoding="utf-8"
        )
    )
    assert invocation["argv"] == [
        "testbed/cli/eval.py",
        "--config",
        str(request_root / "heuristic_residual_pipeline_eval_config.yaml"),
        "--num-rollouts",
        "1",
        "--target-cycle-gate",
        "15",
        "--output-dir",
        str(planned_results_root / "heuristic_residual_pipeline"),
    ]
    assert invocation["command_status"] == "ready_for_runner_invocation"

    run_plan = json.loads(
        (request_root / "residual_eval_run_plan.json").read_text(encoding="utf-8")
    )
    branch_b = run_plan["branches"]["heuristic_residual_pipeline"]
    assert branch_b["status"] == "runnable"
    assert branch_b["runtime_integration_status"] == "available"
    assert branch_b["argv"] == invocation["argv"]
    assert branch_b["planned_output_dir"] == (
        str(planned_results_root / "heuristic_residual_pipeline")
    )


def test_request_writer_rejects_target_cycle_gate_without_source_coverage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    baseline_config = tmp_path / "configs/current_eval.yaml"
    _baseline_config(baseline_config)
    predicted_root = _predicted_artifact_root(tmp_path / "predicted_ab/results")
    runtime_source = _runtime_source(
        predicted_root / "residual_cut_intent_runtime_source.json",
        cycle_indices=(0,),
    )
    request_root = tmp_path / "phase6g_i_request"

    result = write_residual_b_branch_eval_request(
        current_eval_metadata=_current_eval_metadata(baseline_config),
        predicted_ab_artifact_root=predicted_root,
        runtime_source_path=runtime_source,
        request_root=request_root,
        planned_results_root=tmp_path / "phase6g_i_real_ab",
        protected_evidence_roots=[],
        target_cycle_gate=2,
    )

    assert result["status"] == "invalid_runtime_source"
    assert result["validation_errors"] == [
        "runtime source missing required cycle plans for target_cycle_gate 2: [1]"
    ]
    assert request_root.exists() is False


def test_request_writer_materializes_explicit_target_cycle_gate_when_source_covers_it(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    baseline_config = tmp_path / "configs/current_eval.yaml"
    _baseline_config(baseline_config)
    predicted_root = _predicted_artifact_root(tmp_path / "predicted_ab/results")
    runtime_source = _runtime_source(
        predicted_root / "residual_cut_intent_runtime_source.json",
        cycle_indices=(0, 1),
    )
    request_root = tmp_path / "phase6g_i_request"
    planned_results_root = tmp_path / "phase6g_i_real_ab"

    result = write_residual_b_branch_eval_request(
        current_eval_metadata=_current_eval_metadata(baseline_config),
        predicted_ab_artifact_root=predicted_root,
        runtime_source_path=runtime_source,
        request_root=request_root,
        planned_results_root=planned_results_root,
        protected_evidence_roots=[],
        target_cycle_gate=2,
    )

    assert result["status"] == "present"
    assert result["runtime_config"]["eval.target_cycle_gate"] == 2
    assert result["runtime_source"]["cycle_indices"] == [0, 1]
    assert result["runtime_source"]["required_cycle_indices"] == [0, 1]
    assert result["runtime_source"]["missing_required_cycle_indices"] == []

    generated_config = yaml.safe_load(
        (request_root / "heuristic_residual_pipeline_eval_config.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert generated_config["eval"]["target_cycle_gate"] == 2

    invocation = json.loads(
        (request_root / "heuristic_residual_pipeline_invocation.json").read_text(
            encoding="utf-8"
        )
    )
    assert invocation["argv"] == [
        "testbed/cli/eval.py",
        "--config",
        str(request_root / "heuristic_residual_pipeline_eval_config.yaml"),
        "--num-rollouts",
        "1",
        "--target-cycle-gate",
        "2",
        "--output-dir",
        str(planned_results_root / "heuristic_residual_pipeline"),
    ]


def test_request_writer_sets_explicit_zero_target_cycle_terminal_hold(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    baseline_config = tmp_path / "configs/current_eval.yaml"
    _baseline_config(baseline_config)
    baseline_payload = yaml.safe_load(baseline_config.read_text(encoding="utf-8"))
    baseline_payload["eval"]["target_cycle_gate_terminal_hold_steps"] = 100
    baseline_config.write_text(
        yaml.safe_dump(baseline_payload, sort_keys=False),
        encoding="utf-8",
    )
    predicted_root = _predicted_artifact_root(tmp_path / "predicted_ab/results")
    runtime_source = _runtime_source(
        predicted_root / "residual_cut_intent_runtime_source.json"
    )
    request_root = tmp_path / "phase6g_f_request"

    result = write_residual_b_branch_eval_request(
        current_eval_metadata=_current_eval_metadata(baseline_config),
        predicted_ab_artifact_root=predicted_root,
        runtime_source_path=runtime_source,
        request_root=request_root,
        planned_results_root=tmp_path / "phase6g_f_real_ab",
        protected_evidence_roots=[],
    )

    assert result["status"] == "present"
    assert result["runtime_config"]["eval.target_cycle_gate_terminal_hold_steps"] == 0
    generated_config = yaml.safe_load(
        (request_root / "heuristic_residual_pipeline_eval_config.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert generated_config["eval"]["target_cycle_gate_terminal_hold_steps"] == 0


def test_request_writer_rejects_existing_or_protected_roots(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    baseline_config = tmp_path / "configs/current_eval.yaml"
    _baseline_config(baseline_config)
    predicted_root = _predicted_artifact_root(tmp_path / "predicted_ab/results")
    runtime_source = _runtime_source(
        predicted_root / "residual_cut_intent_runtime_source.json"
    )
    existing_request_root = tmp_path / "existing_request"
    existing_request_root.mkdir()

    existing = write_residual_b_branch_eval_request(
        current_eval_metadata=_current_eval_metadata(baseline_config),
        predicted_ab_artifact_root=predicted_root,
        runtime_source_path=runtime_source,
        request_root=existing_request_root,
        planned_results_root=tmp_path / "phase6g_f_real_ab",
        protected_evidence_roots=[],
    )
    assert existing["status"] == "request_root_already_exists"
    assert existing["written_files"] == []

    protected = write_residual_b_branch_eval_request(
        current_eval_metadata=_current_eval_metadata(baseline_config),
        predicted_ab_artifact_root=predicted_root,
        runtime_source_path=runtime_source,
        request_root=tmp_path / "fresh_request",
        planned_results_root=tmp_path / "protected/results/b_branch",
        protected_evidence_roots=[tmp_path / "protected/results"],
    )
    assert protected["status"] == "protected_evidence_root_overlap"
    assert protected["written_files"] == []
    assert (tmp_path / "fresh_request").exists() is False


def test_request_writer_rejects_invalid_runtime_source_before_writing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    baseline_config = tmp_path / "configs/current_eval.yaml"
    _baseline_config(baseline_config)
    predicted_root = _predicted_artifact_root(tmp_path / "predicted_ab/results")
    runtime_source = _runtime_source(
        predicted_root / "residual_cut_intent_runtime_source.json",
        status="invalid_runtime_source_inputs",
    )
    request_root = tmp_path / "phase6g_f_request"

    result = write_residual_b_branch_eval_request(
        current_eval_metadata=_current_eval_metadata(baseline_config),
        predicted_ab_artifact_root=predicted_root,
        runtime_source_path=runtime_source,
        request_root=request_root,
        planned_results_root=tmp_path / "phase6g_f_real_ab",
        protected_evidence_roots=[],
    )

    assert result["status"] == "invalid_runtime_source"
    assert result["written_files"] == []
    assert result["validation_errors"] == [
        "runtime source status must be present"
    ]
    assert request_root.exists() is False


def test_cli_writes_b_branch_request_from_explicit_request_json(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    baseline_config = tmp_path / "configs/current_eval.yaml"
    _baseline_config(baseline_config)
    current_metadata_path = tmp_path / "current/results/eval_run_metadata.json"
    current_metadata_path.parent.mkdir(parents=True, exist_ok=True)
    current_metadata_path.write_text(
        json.dumps(_current_eval_metadata(baseline_config), indent=2),
        encoding="utf-8",
    )
    predicted_root = _predicted_artifact_root(tmp_path / "predicted_ab/results")
    runtime_source = _runtime_source(
        predicted_root / "residual_cut_intent_runtime_source.json",
        cycle_indices=(0, 1),
    )
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "request_result.json"
    request_root = tmp_path / "phase6g_f_request"
    request_path.write_text(
        json.dumps(
            {
                "current_eval_metadata_path": str(current_metadata_path),
                "predicted_ab_artifact_root": str(predicted_root),
                "runtime_source_path": str(runtime_source),
                "request_root": str(request_root),
                "planned_results_root": str(tmp_path / "phase6g_f_real_ab"),
                "protected_evidence_roots": [str(current_metadata_path.parent)],
                "target_cycle_gate": 2,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    rc = main(
        [
            "--request-json",
            str(request_path),
            "--output-json",
            str(output_path),
        ]
    )

    assert rc == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "present"
    assert payload["runtime_config"]["eval.target_cycle_gate"] == 2
    assert payload["written_files"] == EXPECTED_REQUEST_FILES
    generated_config = yaml.safe_load(
        (request_root / "heuristic_residual_pipeline_eval_config.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert generated_config["eval"]["target_cycle_gate"] == 2
    assert (request_root / "heuristic_residual_pipeline_invocation.json").is_file()
    assert (request_root / "residual_eval_run_plan.json").is_file()


def test_cli_rejects_missing_runtime_source_path_before_writing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "request_result.json"
    request_root = tmp_path / "phase6g_f_request"
    request_path.write_text(
        json.dumps(
            {
                "current_eval_metadata_path": "current/results/eval_run_metadata.json",
                "predicted_ab_artifact_root": "predicted_ab/results",
                "request_root": str(request_root),
                "planned_results_root": "phase6g_f_real_ab",
                "protected_evidence_roots": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    rc = main(
        [
            "--request-json",
            str(request_path),
            "--output-json",
            str(output_path),
        ]
    )

    assert rc == 2
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "invalid_request"
    assert payload["validation_errors"] == [
        "request JSON missing required fields: ['runtime_source_path']"
    ]
    assert request_root.exists() is False


def test_console_script_exposes_b_branch_eval_request_entrypoint() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"][
        "tb-terrain-residual-b-branch-request"
    ] == "testbed.cli.terrain_residual_b_branch_eval_request:main"
