"""Summarize tb-replay JSONL diagnostics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-replay-diagnostics",
        description="Summarize JSONL files written by tb-replay --diagnostic-log.",
    )
    parser.add_argument(
        "--input",
        "-i",
        type=Path,
        action="append",
        required=True,
        help="Diagnostic JSONL file or directory. May be repeated.",
    )
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--error-threshold", type=float, default=0.02)
    parser.add_argument("--jump-threshold", type=float, default=0.05)
    args = parser.parse_args()

    paths = _resolve_inputs(args.input)
    if not paths:
        raise SystemExit("No diagnostic JSONL files found.")

    for path in paths:
        _summarize_file(
            path,
            top=max(1, int(args.top)),
            error_threshold=float(args.error_threshold),
            jump_threshold=float(args.jump_threshold),
        )


def _resolve_inputs(inputs: list[Path]) -> list[Path]:
    paths: list[Path] = []
    for item in inputs:
        path = item.expanduser()
        if path.is_file():
            paths.append(path)
        elif path.is_dir():
            paths.extend(sorted(path.glob("*_diagnostics.jsonl")))
            paths.extend(
                p for p in sorted(path.glob("*.jsonl")) if p not in set(paths)
            )
    return sorted(paths)


def _summarize_file(
    path: Path,
    *,
    top: int,
    error_threshold: float,
    jump_threshold: float,
) -> None:
    header: dict[str, Any] = {}
    end: dict[str, Any] = {}
    steps: list[dict[str, Any]] = []
    exceptions: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            event = row.get("event")
            if event == "episode_start":
                header = row
            elif event == "episode_end":
                end = row
            elif event == "step_exception":
                exceptions.append(row)
            elif event == "step":
                steps.append(row)

    source = header.get("source_episode") or end.get("source_episode") or path.name
    print("=" * 88)
    print(f"{path}")
    print(f"source_episode={source}")
    if header:
        print(
            "qpos_order="
            f"{header.get('qpos_order', '')}  action_order={header.get('action_order', '')}"
        )
    if end:
        print(
            "episode_end "
            f"steps={end.get('steps')} "
            f"qpos_mean_diff={_fmt(end.get('qpos_mean_diff'))} "
            f"qpos_max_diff={_fmt(end.get('qpos_max_diff'))}"
        )
    print(f"logged_steps={len(steps)} exceptions={len(exceptions)}")

    if exceptions:
        print("first_exception:")
        print("  " + _format_row(exceptions[0]))

    first_error = next(
        (row for row in steps if _row_error(row) >= error_threshold),
        None,
    )
    first_jump = next(
        (row for row in steps if _num(row.get("replay_qpos_delta_max_abs")) >= jump_threshold),
        None,
    )
    first_collision = next(
        (
            row
            for row in steps
            if "hard_collision" in row.get("diagnostic_reason", [])
            or "target_hard_collision" in row.get("diagnostic_reason", [])
        ),
        None,
    )
    first_contact = next(
        (row for row in steps if "bucket_contact" in row.get("diagnostic_reason", [])),
        None,
    )

    for label, row in (
        ("first_error", first_error),
        ("first_jump", first_jump),
        ("first_collision", first_collision),
        ("first_contact", first_contact),
    ):
        if row is not None:
            print(f"{label}:")
            print("  " + _format_row(row))

    top_error = sorted(steps, key=_row_error, reverse=True)[:top]
    if top_error:
        print(f"top_{len(top_error)}_qpos_error:")
        for row in top_error:
            print("  " + _format_row(row))

    top_jump = sorted(
        steps,
        key=lambda row: _num(row.get("replay_qpos_delta_max_abs")),
        reverse=True,
    )[:top]
    if top_jump:
        print(f"top_{len(top_jump)}_qpos_jump:")
        for row in top_jump:
            print("  " + _format_row(row))


def _row_error(row: dict[str, Any]) -> float:
    return max(
        _num(row.get("qpos_max_error_before")),
        _num(row.get("qpos_max_error_after")),
    )


def _num(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _fmt(value: Any) -> str:
    return f"{_num(value):.6f}" if value is not None else "NA"


def _format_row(row: dict[str, Any]) -> str:
    env_after = row.get("env_state_after") or row.get("env_state_before") or {}
    action = _compact_vector(row.get("action"), max_items=4)
    qpos = _compact_vector(row.get("replay_qpos_after"), max_items=6)
    rel = [
        env_after.get("bucket_dig_area_relative_x_m"),
        env_after.get("bucket_dig_area_relative_y_m"),
        env_after.get("bucket_dig_area_relative_z_m"),
    ]
    tip = [
        env_after.get("bucket_tip_dig_area_x_m"),
        env_after.get("bucket_tip_dig_area_y_m"),
        env_after.get("bucket_tip_dig_area_z_m"),
    ]
    return (
        f"step={row.get('record_step_index')} "
        f"step_id={row.get('step_id_before')}->{row.get('step_id_after')} "
        f"reason={','.join(row.get('diagnostic_reason', []))} "
        f"err_before={_fmt(row.get('qpos_max_error_before'))} "
        f"err_after={_fmt(row.get('qpos_max_error_after'))} "
        f"jump={_fmt(row.get('replay_qpos_delta_max_abs'))} "
        f"action={action} qpos_after={qpos} "
        f"bucket_rel={_compact_vector(rel, max_items=3)} "
        f"bucket_tip={_compact_vector(tip, max_items=3)} "
        f"dig_contact={_fmt(env_after.get('bucket_contact_dig_area_mask'))} "
        f"dump_contact={_fmt(env_after.get('bucket_contact_dump_area_mask'))} "
        f"hard_collision={_fmt(env_after.get('hard_collision_count'))} "
        f"target_hard_collision={_fmt(env_after.get('target_hard_collision_count'))}"
    )


def _compact_vector(value: Any, *, max_items: int) -> str:
    if value is None:
        return "NA"
    if not isinstance(value, list):
        return str(value)
    items = value[:max_items]
    body = ",".join("NA" if item is None else f"{_num(item):.4f}" for item in items)
    if len(value) > max_items:
        body += ",..."
    return f"[{body}]"


if __name__ == "__main__":
    main()
