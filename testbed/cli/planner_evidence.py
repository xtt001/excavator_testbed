"""Classify primitive planner evidence from rollout and evidence traces."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from testbed.planner.evidence_trace import (
    EvidenceEvent,
    classify_evidence,
    events_from_planner_trace,
    events_from_rollout_summary,
    read_evidence_jsonl,
    read_rollout_jsonl_events,
    write_report_json,
    write_report_markdown,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="tb-planner-evidence",
        description="Classify primitive planner capabilities from evidence traces.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    classify_parser = subparsers.add_parser(
        "classify",
        help="Classify planner capabilities from rollout JSONL or evidence JSONL.",
    )
    classify_parser.add_argument(
        "--rollout-jsonl",
        type=Path,
        action="append",
        default=[],
        help="Existing rollout JSONL file. May be repeated.",
    )
    classify_parser.add_argument(
        "--evidence-jsonl",
        type=Path,
        action="append",
        default=[],
        help="Planner evidence JSONL file using evidence_trace schema.",
    )
    classify_parser.add_argument(
        "--planner-trace",
        type=Path,
        action="append",
        default=[],
        help="Existing planner_trace.json file. May be repeated.",
    )
    classify_parser.add_argument(
        "--rollout-summary",
        type=Path,
        action="append",
        default=[],
        help="Existing rollout summary JSON file. May be repeated.",
    )
    classify_parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Write machine-readable classification report JSON.",
    )
    classify_parser.add_argument(
        "--output-md",
        type=Path,
        default=None,
        help="Write Markdown classification report.",
    )
    classify_parser.add_argument(
        "--evidence-packet-count",
        type=int,
        default=None,
        help="Override evidence packet count used for dead-candidate gating.",
    )
    classify_parser.add_argument(
        "--dead-candidate-min-packets",
        type=int,
        default=1,
        help="Minimum packet count before unobserved capabilities become dead-candidates.",
    )

    args = parser.parse_args(argv)
    if args.command == "classify":
        return _classify(args)
    raise AssertionError(f"unhandled command: {args.command}")


def _classify(args: argparse.Namespace) -> int:
    events: list[EvidenceEvent] = []
    input_count = 0
    for path in args.evidence_jsonl:
        events.extend(read_evidence_jsonl(path))
        input_count += 1
    for path in args.rollout_jsonl:
        events.extend(read_rollout_jsonl_events(path))
        input_count += 1
    for path in args.planner_trace:
        events.extend(_read_planner_trace_events(path))
        input_count += 1
    for path in args.rollout_summary:
        events.extend(_read_rollout_summary_events(path))
        input_count += 1
    if input_count == 0:
        raise SystemExit("Provide at least one --rollout-jsonl, --evidence-jsonl, or --planner-trace.")

    evidence_packet_count = (
        int(args.evidence_packet_count)
        if args.evidence_packet_count is not None
        else input_count
    )
    report = classify_evidence(
        events,
        evidence_packet_count=evidence_packet_count,
        dead_candidate_min_packets=max(1, int(args.dead_candidate_min_packets)),
    )

    if args.output_json is not None:
        write_report_json(args.output_json, report)
    if args.output_md is not None:
        write_report_markdown(args.output_md, report)
    if args.output_json is None and args.output_md is None:
        print(json.dumps(report.to_json(), indent=2, sort_keys=True))
    return 0


def _read_planner_trace_events(path: Path) -> list[EvidenceEvent]:
    with path.open("r", encoding="utf-8") as f:
        trace: Any = json.load(f)
    if not isinstance(trace, dict):
        raise SystemExit(f"{path} must contain a JSON object.")
    return events_from_planner_trace(trace)


def _read_rollout_summary_events(path: Path) -> list[EvidenceEvent]:
    with path.open("r", encoding="utf-8") as f:
        summary: Any = json.load(f)
    if not isinstance(summary, dict):
        raise SystemExit(f"{path} must contain a JSON object.")
    return events_from_rollout_summary(summary)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
