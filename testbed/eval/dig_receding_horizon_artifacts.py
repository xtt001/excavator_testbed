"""No-overwrite artifact primitives for the Dig dispatch diagnostic."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

FIXED_ARTIFACT_PATHS = (
    "contract.json",
    "input_manifest.json",
    "variants.jsonl",
    "legacy/trace.jsonl",
    "latest/trace.jsonl",
    "pair_metrics.json",
    "bootstrap.json",
    "decision.json",
    "report.md",
)


def create_no_overwrite_output_root(path: str | Path) -> Path:
    destination = Path(path).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "legacy").mkdir()
    (destination / "latest").mkdir()
    return destination


def write_json_exclusive(path: str | Path, value: Mapping[str, Any]) -> None:
    destination = Path(path)
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def write_jsonl_exclusive(path: str | Path, rows: Iterable[Mapping[str, Any]]) -> None:
    destination = Path(path)
    with destination.open("x", encoding="utf-8") as handle:
        for row in rows:
            handle.write(
                json.dumps(
                    row,
                    sort_keys=True,
                    separators=(",", ":"),
                    allow_nan=False,
                )
            )
            handle.write("\n")


def write_text_exclusive(path: str | Path, value: str) -> None:
    destination = Path(path)
    with destination.open("x", encoding="utf-8") as handle:
        handle.write(value)
        if value and not value.endswith("\n"):
            handle.write("\n")


def file_identity(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve(strict=True)
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return {
        "path": str(source),
        "sha256": digest.hexdigest(),
        "size_bytes": source.stat().st_size,
    }


__all__ = [
    "FIXED_ARTIFACT_PATHS",
    "create_no_overwrite_output_root",
    "file_identity",
    "write_json_exclusive",
    "write_jsonl_exclusive",
    "write_text_exclusive",
]
