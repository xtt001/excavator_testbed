"""CLI for the fixed five-repeat replay pilot acceptance gate."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from testbed.eval.terrain_replay_pilot_gate import (
    build_source_semantic_reference,
    evaluate_replay_pilot_gate,
)
from testbed.eval.terrain_replay_relabel_stats import load_replay_diagnostic_summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tb-terrain-replay-pilot-gate")
    parser.add_argument("--repeat-jsonl", type=Path, action="append", required=True)
    parser.add_argument("--diagnostic-log", type=Path, action="append", required=True)
    parser.add_argument(
        "--source-episode",
        type=Path,
        required=True,
        help="Readonly source HDF5 used to build expert terrain semantics.",
    )
    parser.add_argument(
        "--cycle-eligibility-jsonl",
        type=Path,
        required=True,
        help="Clean-builder cycle eligibility records containing source boundaries.",
    )
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args(argv)
    if len(args.repeat_jsonl) != 5 or len(args.diagnostic_log) != 5:
        parser.error("exactly five --repeat-jsonl and five --diagnostic-log inputs are required")
    if args.output_json.exists():
        parser.error(f"output already exists; no-overwrite: {args.output_json}")

    source_episode_id = args.source_episode.stem
    source_reference = _load_source_reference(
        source_episode=args.source_episode,
        cycle_eligibility_path=args.cycle_eligibility_jsonl,
        source_episode_id=source_episode_id,
    )
    repeats = []
    for index, (records_path, diagnostic_path) in enumerate(
        zip(args.repeat_jsonl, args.diagnostic_log, strict=True)
    ):
        records = _load_episode_candidate_records(records_path, source_episode_id)
        repeats.append(
            {
                "repeat_id": f"repeat_{index:02d}",
                "candidate_records": records,
                "diagnostic_summary": load_replay_diagnostic_summary(
                    diagnostic_path
                ),
            }
        )
    result = evaluate_replay_pilot_gate(
        repeats,
        source_reference=source_reference,
        required_source_episode_id=source_episode_id,
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": result["status"], "pass": result["pass"]}))
    return 0 if result["pass"] else 2


def _load_source_reference(
    *,
    source_episode: Path,
    cycle_eligibility_path: Path,
    source_episode_id: str,
) -> dict[str, object]:
    from testbed.data.hdf5_io import read_episode

    episode = read_episode(source_episode, load_images=False)
    metadata = episode.get("metadata", {})
    cycle_records = [
        record
        for record in _read_jsonl(cycle_eligibility_path)
        if str(record.get("source_episode_id", "")) == source_episode_id
    ]
    return build_source_semantic_reference(
        source_episode_id=source_episode_id,
        control_hz=float(metadata.get("control_hz", 0.0)),
        env_state=episode.get("env_state"),
        cycle_records=cycle_records,
    )


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


def _load_episode_candidate_records(
    path: Path,
    source_episode_id: str,
) -> list[dict[str, object]]:
    """Select one episode from a per-repeat JSONL shared by a batch replay."""

    selected: list[dict[str, object]] = []
    for record in _read_jsonl(path):
        record_episode_id = str(
            record.get("source_episode_id") or record.get("episode_id") or ""
        )
        if record_episode_id == str(source_episode_id):
            selected.append(record)
    return selected


if __name__ == "__main__":
    raise SystemExit(main())
