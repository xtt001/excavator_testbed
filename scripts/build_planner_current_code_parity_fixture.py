#!/usr/bin/env python3
"""Build the portable aggregate-TX24 planner parity fixture.

The source rollout is intentionally ignored because it is about 48 MB. This
script retains every field for the 112 golden-window rows, only the fields
needed to locate those rows elsewhere, and the first ten low-dimensional rows
used by the replay-input audit. The result is deterministic and suitable for
CPU contract tests in a clean clone.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

from testbed.planner.golden_window_parity import (
    AGGREGATE_TX24_ARTIFACTS,
    AGGREGATE_TX24_PORTABLE_ARTIFACTS,
    read_jsonl_rows,
    select_golden_window_indices,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_NAME = "manifest.json"
SELECTOR_FIELDS = (
    "step_id",
    "t",
    "skill_name",
    "skill_id",
    "skill_switch_reason",
    "coverage_terminal_stop_requested",
    "task_success",
)
REPLAY_AUDIT_FIELDS = ("qpos", "qvel", "env_state", "action", "debug")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _project_row(
    row: dict[str, Any],
    *,
    index: int,
    golden_indices: frozenset[int],
) -> dict[str, Any]:
    if index in golden_indices:
        return row
    fields = list(SELECTOR_FIELDS)
    if index < 10:
        fields.extend(REPLAY_AUDIT_FIELDS)
    return {field: row[field] for field in fields if field in row}


def build_fixture() -> dict[str, Any]:
    source = AGGREGATE_TX24_ARTIFACTS.at_root(REPO_ROOT)
    portable = AGGREGATE_TX24_PORTABLE_ARTIFACTS.at_root(REPO_ROOT)
    output_dir = portable.rollout_jsonl.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = read_jsonl_rows(source.rollout_jsonl)
    golden_indices = frozenset(select_golden_window_indices(rows))
    with portable.rollout_jsonl.open("wb") as raw_stream:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw_stream,
            mtime=0,
        ) as compressed:
            for index, row in enumerate(rows):
                projected = _project_row(
                    row,
                    index=index,
                    golden_indices=golden_indices,
                )
                line = json.dumps(
                    projected,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                compressed.write(line.encode("utf-8") + b"\n")

    for source_path, output_path in (
        (source.planner_trace, portable.planner_trace),
        (source.rollout_summary, portable.rollout_summary),
        (source.resolved_config, portable.resolved_config),
    ):
        shutil.copyfile(source_path, output_path)

    manifest = {
        "schema_version": "planner_current_code_parity_fixture_v1",
        "source_row_count": len(rows),
        "golden_window_count": len(golden_indices),
        "projection": {
            "golden_rows": "all_fields",
            "other_rows": list(SELECTOR_FIELDS),
            "first_ten_extra_fields": list(REPLAY_AUDIT_FIELDS),
        },
        "source_artifacts": {
            name: {
                "path": path.relative_to(REPO_ROOT).as_posix(),
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
            }
            for name, path in (
                ("rollout_jsonl", source.rollout_jsonl),
                ("planner_trace", source.planner_trace),
                ("rollout_summary", source.rollout_summary),
                ("resolved_config", source.resolved_config),
            )
        },
        "portable_artifacts": {
            name: {
                "path": path.relative_to(REPO_ROOT).as_posix(),
                "sha256": _sha256(path),
                "size_bytes": path.stat().st_size,
            }
            for name, path in (
                ("rollout_jsonl", portable.rollout_jsonl),
                ("planner_trace", portable.planner_trace),
                ("rollout_summary", portable.rollout_summary),
                ("resolved_config", portable.resolved_config),
            )
        },
    }
    manifest_path = output_dir / MANIFEST_NAME
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    manifest = build_fixture()
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
