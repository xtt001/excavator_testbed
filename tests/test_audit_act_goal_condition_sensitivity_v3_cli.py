from __future__ import annotations

import sys
from pathlib import Path

from testbed.cli import audit_act_goal_condition_sensitivity_v3 as module


def test_parser_defaults_to_distinct_a2_and_v3_roots() -> None:
    args = module.build_parser().parse_args([])

    assert args.source_results_root == module.DEFAULT_SOURCE_RESULTS_ROOT
    assert args.stage_a_v1_output_root == module.DEFAULT_STAGE_A_V1_OUTPUT_ROOT
    assert args.support_audit_output_root == module.DEFAULT_SUPPORT_AUDIT_OUTPUT_ROOT
    assert args.stage_a_v2_output_root == module.DEFAULT_STAGE_A_V2_OUTPUT_ROOT
    assert args.return_stability_output_root == module.DEFAULT_RETURN_STABILITY_OUTPUT_ROOT
    assert args.dig_joint_validation_output_root == module.DEFAULT_DIG_JOINT_VALIDATION_OUTPUT_ROOT
    assert args.output_root == module.DEFAULT_OUTPUT_ROOT
    assert args.output_root not in {
        args.stage_a_v1_output_root,
        args.support_audit_output_root,
        args.stage_a_v2_output_root,
        args.return_stability_output_root,
        args.dig_joint_validation_output_root,
    }


def test_main_forwards_v3_prerequisite_paths(monkeypatch, tmp_path: Path, capsys) -> None:
    paths = {
        "source": tmp_path / "results",
        "stage_v1": tmp_path / "stage-v1",
        "support": tmp_path / "support",
        "stage_v2": tmp_path / "stage-v2",
        "return_stability": tmp_path / "return-stability",
        "dig_validation": tmp_path / "dig-validation",
        "dig": tmp_path / "dig.yaml",
        "return_config": tmp_path / "return.yaml",
        "output": tmp_path / "stage-v3",
    }
    captured: dict[str, object] = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {"status": "completed", "output_root": str(paths["output"])}

    monkeypatch.setattr(module, "run_stage_a_v3_after_prerequisite_audits", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "tb-audit-act-goal-condition-sensitivity-v3",
            "--source-results-root", str(paths["source"]),
            "--stage-a-v1-output-root", str(paths["stage_v1"]),
            "--support-audit-output-root", str(paths["support"]),
            "--stage-a-v2-output-root", str(paths["stage_v2"]),
            "--return-stability-output-root", str(paths["return_stability"]),
            "--dig-joint-validation-output-root", str(paths["dig_validation"]),
            "--dig-training-config", str(paths["dig"]),
            "--return-training-config", str(paths["return_config"]),
            "--output-root", str(paths["output"]),
            "--device", "cpu",
        ],
    )

    module.main()

    assert captured == {
        "source_results_root": paths["source"],
        "stage_a_v1_output_root": paths["stage_v1"],
        "support_audit_output_root": paths["support"],
        "stage_a_v2_output_root": paths["stage_v2"],
        "return_stability_output_root": paths["return_stability"],
        "dig_joint_validation_output_root": paths["dig_validation"],
        "dig_training_config_path": paths["dig"],
        "return_training_config_path": paths["return_config"],
        "output_root": paths["output"],
        "device": "cpu",
    }
    assert '"status": "completed"' in capsys.readouterr().out
