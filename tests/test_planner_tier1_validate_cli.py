from __future__ import annotations

import json
from pathlib import Path

from testbed.cli.planner_tier1_validate import main
from tests.test_planner_tier1_validation import _write_tier1_package


def test_planner_tier1_validate_cli_writes_reports(tmp_path: Path) -> None:
    package = _write_tier1_package(tmp_path)
    output_json = tmp_path / "report.json"
    output_md = tmp_path / "report.md"

    rc = main(
        [
            "validate",
            "--package",
            str(package),
            "--output-json",
            str(output_json),
            "--output-md",
            str(output_md),
        ]
    )

    assert rc == 0
    report = json.loads(output_json.read_text(encoding="utf-8"))
    assert report["schema_version"] == "tier1_validation_report_v0"
    assert report["passed"] is True
    assert report["select_event_summary"]["select_event_count"] == 10
    assert "Tier 1 Decision-Structure Validation Report" in output_md.read_text(
        encoding="utf-8"
    )


def test_planner_tier1_validate_cli_reports_malformed_hash_file(
    tmp_path: Path,
) -> None:
    package = _write_tier1_package(tmp_path)
    (package / "hashes" / "sha256sums.txt").write_text(
        "not-a-valid-sha-line\n",
        encoding="utf-8",
    )

    rc = main(["validate", "--package", str(package)])

    assert rc == 2
