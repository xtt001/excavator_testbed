"""Exclusive artifact writers for bounded Return closed-loop probes."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np


def json_safe(value: Any) -> Any:
    """Convert probe records to deterministic JSON values."""

    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return json_safe(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        return value.astype(float).tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, bytes):
        return {"bytes": len(value)}
    return value


def write_json_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(
            json_safe(payload),
            handle,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        handle.write("\n")


def write_jsonl_exclusive(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    with path.open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(
                json.dumps(json_safe(row), ensure_ascii=False, sort_keys=True)
            )
            handle.write("\n")


def write_text_exclusive(path: Path, text: str) -> None:
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


def render_return_closed_loop_report(
    *,
    manifest: Mapping[str, Any],
    preflight: Mapping[str, Any],
    arms: Sequence[Mapping[str, Any]],
) -> str:
    """Render the human-readable summary without duplicating trace data."""

    lines = [
        "# Strict-18 Return-only bounded closed-loop probe",
        "",
        f"- Status: `{manifest['status']}`",
        f"- Execution requested: `{manifest['execution_requested']}`",
        f"- Arms: `{manifest['arm_count']}`",
        f"- Non-zero actions: `{manifest['nonzero_action_count']}`",
        "- Runtime/default strategy changed: `false`",
        "- Latest-current chunk is diagnostic-only and non-promotable.",
        "- Dig, Carry, and Dump transitions are forbidden.",
        "",
        "## Preflight",
        "",
        f"- Status: `{preflight['status']}`",
        f"- qpos applied for every arm: `{preflight['qpos_fixture_application_confirmed']}`",
        f"- qvel applied for every arm: `{preflight['qvel_fixture_application_confirmed']}`",
    ]
    blockers = list(preflight.get("blockers", ()))
    if blockers:
        lines.extend(["- Blockers:", *[f"  - `{item}`" for item in blockers]])
    if manifest["execution_requested"] and not blockers:
        lines.extend(
            [
                "",
                "## Arm terminations",
                "",
                *[
                    f"- `{arm['arm_id']}`: `{arm.get('termination_reason', '')}`; "
                    f"neutral_ack=`{arm.get('neutral_acknowledged', False)}`"
                    for arm in arms
                ],
            ]
        )
    return "\n".join(lines) + "\n"


__all__ = [
    "json_safe",
    "render_return_closed_loop_report",
    "write_json_exclusive",
    "write_jsonl_exclusive",
    "write_text_exclusive",
]
