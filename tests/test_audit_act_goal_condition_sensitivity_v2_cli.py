from __future__ import annotations

import sys
from pathlib import Path

from testbed.cli import audit_act_goal_condition_sensitivity_v2 as module


def test_parser_defaults_to_distinct_v1_support_and_v2_roots() -> None:
    args = module.build_parser().parse_args([])

    assert args.source_results_root == module.DEFAULT_SOURCE_RESULTS_ROOT
    assert args.stage_a_v1_output_root == module.DEFAULT_STAGE_A_V1_OUTPUT_ROOT
    assert args.support_audit_output_root == module.DEFAULT_SUPPORT_AUDIT_OUTPUT_ROOT
    assert args.output_root == module.DEFAULT_OUTPUT_ROOT
    assert args.output_root not in {
        args.stage_a_v1_output_root,
        args.support_audit_output_root,
    }


def test_main_forwards_primitive_scoped_v2_paths(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    source = tmp_path / "results"
    stage = tmp_path / "stage-a-v1"
    support = tmp_path / "support-audit"
    dig = tmp_path / "dig.yaml"
    return_config = tmp_path / "return.yaml"
    output = tmp_path / "stage-a-v2-return"
    captured: dict[str, object] = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {"status": "completed", "output_root": str(output)}

    monkeypatch.setattr(module, "run_primitive_scoped_stage_a_support_audit", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "tb-audit-act-goal-condition-sensitivity-v2",
            "--source-results-root", str(source),
            "--stage-a-v1-output-root", str(stage),
            "--support-audit-output-root", str(support),
            "--dig-training-config", str(dig),
            "--return-training-config", str(return_config),
            "--output-root", str(output),
            "--device", "cpu",
        ],
    )

    module.main()

    assert captured == {
        "source_results_root": source,
        "stage_a_v1_output_root": stage,
        "support_audit_output_root": support,
        "dig_training_config_path": dig,
        "return_training_config_path": return_config,
        "output_root": output,
        "device": "cpu",
    }
    assert '"status": "completed"' in capsys.readouterr().out
