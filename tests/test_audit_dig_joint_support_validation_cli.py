from __future__ import annotations

import sys
from pathlib import Path

from testbed.cli import audit_dig_joint_support_validation as module


def test_cli_defaults_are_fixed_to_strict_dig_and_no_overwrite_root() -> None:
    parser = module.build_parser()
    args = parser.parse_args([])

    assert args.dig_training_config == module.DEFAULT_DIG_TRAINING_CONFIG
    assert args.output_root == module.DEFAULT_OUTPUT_ROOT
    assert args.output_root.name == "dig_joint_support_validation_v1"
    assert args.output_root.parent == module.DEFAULT_SOURCE_RESULTS_ROOT.parent


def test_cli_only_forwards_dig_config_and_output_root(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    config = tmp_path / "dig.yaml"
    output = tmp_path / "audit"
    calls: list[dict[str, Path]] = []

    def fake_run(**kwargs):
        calls.append(kwargs)
        return {
            "status": "completed",
            "output_root": str(kwargs["output_root"]),
            "selected_candidate_id": "dig_joint_regularized_mahalanobis_p99_v1",
        }

    monkeypatch.setattr(module, "run_dig_joint_support_validation_audit_from_file", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "tb-audit-dig-joint-support-validation",
            "--dig-training-config",
            str(config),
            "--output-root",
            str(output),
        ],
    )

    module.main()

    assert calls == [
        {"dig_training_config_path": config, "output_root": output}
    ]
    assert "dig_joint_regularized_mahalanobis_p99_v1" in capsys.readouterr().out
