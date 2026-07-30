from __future__ import annotations

import json
import sys
from pathlib import Path

from testbed.cli import build_act_functional_10cycle_validation as cli


def test_cli_delegates_to_functional_validation_builder(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    results = tmp_path / "results"
    output = tmp_path / "functional-validation"
    calls: list[dict[str, object]] = []

    def fake_build(
        *,
        results_dir: Path,
        output_dir: Path,
        expected_rollout_count: int,
        seed_base: int,
    ) -> list[dict[str, object]]:
        calls.append(
            {
                "results_dir": results_dir,
                "output_dir": output_dir,
                "expected_rollout_count": expected_rollout_count,
                "seed_base": seed_base,
            }
        )
        return [{"status": "passed"}] * expected_rollout_count

    monkeypatch.setattr(
        cli,
        "build_act_functional_10cycle_records",
        fake_build,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "tb-build-act-functional-10cycle-validation",
            "--results-dir",
            str(results),
            "--output-dir",
            str(output),
            "--expected-rollout-count",
            "3",
            "--seed-base",
            "1200",
        ],
    )

    cli.main()

    assert calls == [
        {
            "results_dir": results,
            "output_dir": output,
            "expected_rollout_count": 3,
            "seed_base": 1200,
        }
    ]
    assert json.loads(capsys.readouterr().out) == {
        "manifest_path": str((output / "validation_manifest.json").resolve()),
        "record_count": 3,
        "schema": "act_functional_10cycle_validation_manifest_v1",
        "status": "built",
    }
