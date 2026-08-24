from __future__ import annotations

from pathlib import Path

import pytest

from testbed.eval.dig_receding_horizon_artifacts import (
    FIXED_ARTIFACT_PATHS,
    create_no_overwrite_output_root,
    write_json_exclusive,
)


def test_output_root_is_no_overwrite_and_prepares_only_trace_directories(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "new_diagnostic"

    create_no_overwrite_output_root(destination)

    assert destination.is_dir()
    assert (destination / "legacy").is_dir()
    assert (destination / "latest").is_dir()
    assert set(FIXED_ARTIFACT_PATHS) >= {
        "contract.json",
        "input_manifest.json",
        "variants.jsonl",
        "legacy/trace.jsonl",
        "latest/trace.jsonl",
        "pair_metrics.json",
        "bootstrap.json",
        "decision.json",
        "report.md",
    }
    with pytest.raises(FileExistsError):
        create_no_overwrite_output_root(destination)


def test_json_writer_never_overwrites(tmp_path: Path) -> None:
    path = tmp_path / "artifact.json"
    write_json_exclusive(path, {"status": "first"})

    with pytest.raises(FileExistsError):
        write_json_exclusive(path, {"status": "second"})
