"""CLI for aggregating per-episode semantic replay gates."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from testbed.eval.terrain_replay_batch_assessment import (
    build_replay_batch_assessment,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tb-terrain-replay-batch-assessment")
    parser.add_argument("--gate-json", type=Path, action="append", required=True)
    parser.add_argument("--selection-manifest", type=Path, required=True)
    parser.add_argument(
        "--cycle-eligibility-jsonl",
        type=Path,
        required=True,
        help="Full clean-builder eligibility file, including ACT-only tail cycles.",
    )
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output_json.exists():
        parser.error(f"output already exists; no-overwrite: {args.output_json}")

    selection_cycles = _read_jsonl(args.selection_manifest)
    source_cycles = _read_jsonl(args.cycle_eligibility_jsonl)
    expected_episode_ids = sorted(
        {
            str(record.get("source_episode_id", ""))
            for record in selection_cycles
            if bool(record.get("replay_candidate", False))
            and str(record.get("source_episode_id", ""))
        },
        key=_episode_sort_key,
    )
    gates = [
        json.loads(path.read_text(encoding="utf-8")) for path in args.gate_json
    ]
    result = build_replay_batch_assessment(
        gates,
        source_cycle_records=source_cycles,
        expected_episode_ids=expected_episode_ids,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": result["status"],
                "semantic_usable_episode_count": result[
                    "semantic_usable_episode_count"
                ],
                "expected_episode_count": result["expected_episode_count"],
                "effect_relabel_strict_source_cycle_count": result[
                    "effect_relabel_strict_source_cycle_count"
                ],
            }
        )
    )
    return 0 if result["status"] == "present" else 2


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if not text:
                continue
            value = json.loads(text)
            if isinstance(value, dict):
                records.append(value)
    return records


def _episode_sort_key(value: str) -> tuple[int, str]:
    try:
        return int(value.rsplit("_", 1)[1]), value
    except (IndexError, ValueError):
        return 10**9, value


if __name__ == "__main__":
    raise SystemExit(main())
