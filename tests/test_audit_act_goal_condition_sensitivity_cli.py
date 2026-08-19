from __future__ import annotations

import sys
from pathlib import Path

from testbed.cli import audit_act_goal_condition_sensitivity as module


def test_parser_defaults_to_the_frozen_stage_a_source() -> None:
    args = module.build_parser().parse_args([])

    assert args.source_results_root == module.DEFAULT_SOURCE_RESULTS_ROOT
    assert args.dig_training_config == module.DEFAULT_DIG_TRAINING_CONFIG
    assert args.return_training_config == module.DEFAULT_RETURN_TRAINING_CONFIG
    assert args.output_root == module.DEFAULT_SOURCE_RESULTS_ROOT.parent / module.OUTPUT_ROOT_NAME
    assert args.device == "cuda"


def test_main_forwards_all_explicit_arguments(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    source = tmp_path / "results"
    dig_config = tmp_path / "dig.yaml"
    return_config = tmp_path / "return.yaml"
    output = tmp_path / "output"
    captured: dict[str, object] = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {
            "status": "completed",
            "output_root": str(output),
            "manifest": {"schema": "act_goal_condition_sensitivity_manifest_v1"},
        }

    monkeypatch.setattr(module, "run_act_goal_condition_sensitivity_audit", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "tb-audit-act-goal-condition-sensitivity",
            "--source-results-root",
            str(source),
            "--dig-training-config",
            str(dig_config),
            "--return-training-config",
            str(return_config),
            "--output-root",
            str(output),
            "--device",
            "cpu",
        ],
    )

    module.main()

    assert captured == {
        "source_results_root": source,
        "dig_training_config_path": dig_config,
        "return_training_config_path": return_config,
        "output_root": output,
        "device": "cpu",
    }
    assert '"status": "completed"' in capsys.readouterr().out
