from __future__ import annotations

import sys
from pathlib import Path

from testbed.cli import audit_return_goal_response_stability as module


def test_parser_defaults_to_distinct_v2_stage_and_no_overwrite_audit_roots() -> None:
    args = module.build_parser().parse_args([])

    assert args.stage_a_v2_output_root == module.DEFAULT_STAGE_A_V2_OUTPUT_ROOT
    assert args.output_root == module.DEFAULT_OUTPUT_ROOT
    assert args.output_root != args.stage_a_v2_output_root


def test_main_forwards_only_immutable_stage_root_output_and_device(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    stage = tmp_path / "stage-a-v2"
    output = tmp_path / "audit"
    captured: dict[str, object] = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {"status": "completed", "output_root": str(output)}

    monkeypatch.setattr(module, "run_return_goal_response_stability_audit", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "tb-audit-return-goal-response-stability",
            "--stage-a-v2-output-root",
            str(stage),
            "--output-root",
            str(output),
            "--device",
            "cpu",
        ],
    )

    module.main()

    assert captured == {
        "stage_a_v2_output_root": stage,
        "output_root": output,
        "device": "cpu",
    }
    assert '"status": "completed"' in capsys.readouterr().out
