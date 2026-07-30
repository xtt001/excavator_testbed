"""Extract stable executed-cut effect samples from a strict replay corpus."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from testbed.eval.executed_cut_effect_corpus import (
    build_executed_cut_effect_corpus,
    write_executed_cut_effect_corpus,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m testbed.cli.build_executed_cut_effect_samples",
        description="Build replay-derived silver effect samples from strict wrappers only.",
    )
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--records-jsonl", type=Path, required=True)
    parser.add_argument("--manifest-json", type=Path, required=True)
    parser.add_argument("--expected-episode-count", type=int, default=None)
    parser.add_argument(
        "--effective-move-min-volume-m3",
        type=float,
        default=None,
        help=(
            "Optional explicit label threshold. Omit it rather than inventing an "
            "effective-move label."
        ),
    )
    parser.add_argument("--summary-json", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        corpus = build_executed_cut_effect_corpus(
            args.source_root,
            expected_episode_count=args.expected_episode_count,
            effective_move_min_volume_m3=args.effective_move_min_volume_m3,
        )
        write_result = write_executed_cut_effect_corpus(
            corpus,
            records_jsonl_path=args.records_jsonl,
            manifest_json_path=args.manifest_json,
        )
        result = {
            "schema": "executed_cut_effect_sample_cli_result_v1",
            "status": write_result["status"],
            "corpus_status": corpus["status"],
            "episode_count": corpus.get("episode_count"),
            "record_count": corpus.get("record_count"),
            "rejected_eligible_cycle_count": corpus.get(
                "rejected_eligible_cycle_count"
            ),
            "write_result": write_result,
        }
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        result = {
            "schema": "executed_cut_effect_sample_cli_result_v1",
            "status": "error",
            "error": str(exc),
        }
        _emit(result, args.summary_json)
        return 2
    _emit(result, args.summary_json)
    return 0 if result["status"] == "present" and corpus["status"] == "present" else 1


def _emit(result: Mapping[str, Any], output_path: Path | None) -> None:
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if output_path is None:
        print(payload, end="")
        return
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(payload, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
