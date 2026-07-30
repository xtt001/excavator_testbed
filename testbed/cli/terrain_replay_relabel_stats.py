"""CLI for current-Unity terrain replay relabel variance stats."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from testbed.eval.terrain_replay_relabel_stats import (
    load_replay_diagnostic_summary,
    write_replay_relabel_outputs,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tb-terrain-replay-relabel-stats",
        description=(
            "Aggregate repeated current-Unity replay relabel JSONL outputs into "
            "variance-tiered silver cycle labels."
        ),
    )
    parser.add_argument(
        "--repeat-jsonl",
        type=Path,
        action="append",
        required=True,
        help="Candidate cycle JSONL for one replay repeat. May be repeated.",
    )
    parser.add_argument(
        "--diagnostic-log",
        type=Path,
        action="append",
        default=[],
        help=(
            "tb-replay diagnostic JSONL aligned with --repeat-jsonl order. "
            "May be repeated."
        ),
    )
    parser.add_argument(
        "--source-episode-id",
        required=True,
        help="Readonly source HDF5 episode id used as the trajectory source.",
    )
    parser.add_argument(
        "--target-id",
        required=True,
        help="Terrain target id shared by the repeated relabel records.",
    )
    parser.add_argument(
        "--report-json",
        type=Path,
        required=True,
        help="Fresh output path for terrain_replay_relabel_stats_v2 JSON.",
    )
    parser.add_argument(
        "--samples-jsonl",
        type=Path,
        required=True,
        help="Fresh output path for terrain_replay_relabel_cycle_sample_v2 JSONL.",
    )
    parser.add_argument(
        "--min-repeat-count",
        type=int,
        default=5,
        help="Minimum repeats required before fine/weak relabel use is allowed.",
    )
    args = parser.parse_args(argv)

    if args.diagnostic_log and len(args.diagnostic_log) != len(args.repeat_jsonl):
        parser.error("--diagnostic-log count must match --repeat-jsonl count")

    repeats = _load_repeats(
        repeat_paths=args.repeat_jsonl,
        diagnostic_paths=args.diagnostic_log,
    )
    result = write_replay_relabel_outputs(
        repeats,
        report_path=args.report_json,
        samples_path=args.samples_jsonl,
        source_episode_id=args.source_episode_id,
        target_id=args.target_id,
        min_repeat_count=args.min_repeat_count,
    )
    print(
        json.dumps(
            {
                "schema": result.get("schema"),
                "status": result.get("status"),
                "report_path": result.get("report_path"),
                "samples_path": result.get("samples_path"),
                "group_count": result.get("group_count", 0),
                "record_count": result.get("record_count", 0),
                "tier_counts": result.get("tier_counts", {}),
                "gold_status": result.get("gold_status", "not_gold"),
            },
            sort_keys=True,
        )
    )
    return 0 if result.get("status") == "present" else 2


def _load_repeats(
    *,
    repeat_paths: Sequence[Path],
    diagnostic_paths: Sequence[Path],
) -> list[dict[str, Any]]:
    repeats: list[dict[str, Any]] = []
    for index, repeat_path in enumerate(repeat_paths):
        repeat = repeat_path.expanduser()
        diagnostic_summary: dict[str, Any] = {}
        if diagnostic_paths:
            diagnostic_summary = load_replay_diagnostic_summary(
                diagnostic_paths[index].expanduser()
            )
        repeats.append(
            {
                "repeat_id": repeat.stem,
                "candidate_records": _read_jsonl(repeat),
                "diagnostic_summary": diagnostic_summary,
            }
        )
    return repeats


def _read_jsonl(path: Path) -> list[Any]:
    rows: list[Any] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            rows.append(json.loads(text))
    return rows


if __name__ == "__main__":
    raise SystemExit(main())
