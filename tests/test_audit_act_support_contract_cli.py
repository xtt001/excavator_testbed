from __future__ import annotations

import sys
from pathlib import Path

from testbed.cli import audit_act_support_contract as module


def test_parser_defaults_to_frozen_support_audit_sources() -> None:
    args = module.build_parser().parse_args([])

    assert args.source_results_root == module.DEFAULT_SOURCE_RESULTS_ROOT
    assert args.stage_a_output_root == module.DEFAULT_STAGE_A_OUTPUT_ROOT
    assert args.output_root == module.DEFAULT_OUTPUT_ROOT


def test_main_forwards_explicit_paths(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    source = tmp_path / "results"
    stage = tmp_path / "stage-a"
    dig = tmp_path / "dig.yaml"
    return_config = tmp_path / "return.yaml"
    output = tmp_path / "output"
    captured: dict[str, object] = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {"status": "support_contract_not_selected", "output_root": str(output)}

    monkeypatch.setattr(module, "run_support_contract_audit_from_files", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "tb-audit-act-support-contract",
            "--source-results-root",
            str(source),
            "--stage-a-output-root",
            str(stage),
            "--dig-training-config",
            str(dig),
            "--return-training-config",
            str(return_config),
            "--output-root",
            str(output),
        ],
    )

    module.main()

    assert captured == {
        "source_results_root": source,
        "stage_a_output_root": stage,
        "dig_training_config_path": dig,
        "return_training_config_path": return_config,
        "output_root": output,
    }
    assert "support_contract_not_selected" in capsys.readouterr().out
