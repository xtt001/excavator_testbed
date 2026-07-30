from __future__ import annotations

import json
import sys
from pathlib import Path

from testbed.cli import build_carry_start_envelope as cli


def test_cli_delegates_to_data_builder(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    split_path = tmp_path / "carry_source_split.yaml"
    output_path = tmp_path / "carry_start_envelope_v1.json"
    calls: list[dict[str, Path]] = []

    def fake_build_carry_start_envelope(
        *,
        split_path: Path,
        output_path: Path,
    ) -> Path:
        calls.append({"split_path": split_path, "output_path": output_path})
        return output_path.resolve()

    monkeypatch.setattr(
        cli,
        "build_carry_start_envelope",
        fake_build_carry_start_envelope,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "tb-build-carry-start-envelope",
            "--split-path",
            str(split_path),
            "--output-path",
            str(output_path),
        ],
    )

    cli.main()

    assert calls == [{"split_path": split_path, "output_path": output_path}]
    assert json.loads(capsys.readouterr().out) == {
        "artifact_path": str(output_path.resolve()),
        "schema": "carry_start_envelope_v1",
    }
