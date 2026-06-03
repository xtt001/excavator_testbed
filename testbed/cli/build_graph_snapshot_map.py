"""Build a graph snapshot-map YAML from Unity depth snapshot JSON files."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from testbed.cli.graph_session_paths import (
    depth_snapshot_dir_for_session,
    snapshot_map_for_session,
)


_EPISODE_RE = re.compile(r"_ep(?P<episode>\d+)_")
_STEP_RE = re.compile(r"_step(?P<step>\d+)_")
_SESSION_RE = re.compile(r"^depth_camera_(?P<session>.+?)_ep\d+_")


@dataclass(frozen=True)
class SnapshotEntry:
    episode_index: int
    step_id: int
    path: Path
    session_id: str
    sequence_index: int
    timestamp_ns: int | None


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tb-build-graph-snapshot-map",
        description="Scan Unity depth JSON snapshots and write graph_attach YAML.",
    )
    parser.add_argument(
        "--graph-session",
        default=None,
        help="Convenience session id. Defaults --session-id, --snapshot-root, and --output.",
    )
    parser.add_argument("--snapshot-root", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--pattern",
        default="depth_camera*.json",
        help="Glob pattern under --snapshot-root.",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="Optional session filter. Matches metadata.session_id or filename session token.",
    )
    parser.add_argument(
        "--episode-index",
        type=int,
        action="append",
        default=None,
        help="Optional episode filter. Can be repeated.",
    )
    parser.add_argument(
        "--absolute-paths",
        action="store_true",
        help="Write absolute snapshot paths instead of paths relative to snapshot_root.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the generated YAML without writing --output.",
    )
    parser.add_argument(
        "--duplicate-policy",
        choices=["error", "latest"],
        default=None,
        help="How to handle duplicate episode/step snapshots. Default: latest with --graph-session, otherwise error.",
    )
    args = parser.parse_args()
    graph_session = str(args.graph_session).strip() if args.graph_session else ""
    session_id = args.session_id or graph_session or None
    snapshot_root = args.snapshot_root
    output = args.output
    if graph_session:
        if snapshot_root is None:
            snapshot_root = depth_snapshot_dir_for_session(graph_session)
        if output is None:
            output = snapshot_map_for_session(graph_session)
    if snapshot_root is None:
        raise SystemExit("--snapshot-root is required unless --graph-session is provided.")
    if output is None:
        raise SystemExit("--output is required unless --graph-session is provided.")
    duplicate_policy = args.duplicate_policy or ("latest" if graph_session else "error")

    try:
        text = build_snapshot_map_text(
            snapshot_root=snapshot_root,
            pattern=str(args.pattern),
            session_id=session_id,
            episode_indices=args.episode_index,
            absolute_paths=bool(args.absolute_paths),
            duplicate_policy=duplicate_policy,
        )
    except Exception as exc:
        print(f"tb-build-graph-snapshot-map: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    if args.dry_run:
        print(text, end="")
        return

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text)
    print(
        json.dumps(
            {
                "output": str(output),
                "snapshot_root": str(snapshot_root),
                "episode_count": _count_episode_entries(text),
            },
            sort_keys=True,
        )
    )


def build_snapshot_map_text(
    *,
    snapshot_root: Path,
    pattern: str = "depth_camera*.json",
    session_id: str | None = None,
    episode_indices: list[int] | None = None,
    absolute_paths: bool = False,
    duplicate_policy: str = "error",
) -> str:
    if not snapshot_root.is_dir():
        raise FileNotFoundError(f"snapshot root not found: {snapshot_root}")
    if duplicate_policy not in {"error", "latest"}:
        raise ValueError("duplicate_policy must be one of: error, latest.")

    allowed_episodes = set(episode_indices or [])
    entries = [
        entry
        for entry in _scan_snapshot_entries(snapshot_root, pattern=pattern)
        if _entry_matches(entry, session_id=session_id, allowed_episodes=allowed_episodes)
    ]
    if not entries:
        raise FileNotFoundError("no matching depth snapshot JSON files found.")

    by_episode: dict[int, list[SnapshotEntry]] = {}
    for entry in entries:
        by_episode.setdefault(entry.episode_index, []).append(entry)

    payload: dict[str, Any] = {
        "defaults": {"snapshot_root": str(snapshot_root.resolve())},
        "episodes": [],
    }
    for episode_index in sorted(by_episode):
        snapshots = sorted(
            by_episode[episode_index],
            key=lambda item: (item.step_id, item.sequence_index, item.path.name),
        )
        snapshots = _deduplicate_snapshots(
            snapshots,
            episode_index=episode_index,
            duplicate_policy=duplicate_policy,
        )
        episode_snapshots: list[dict[str, Any]] = []
        for item in snapshots:
            episode_snapshots.append(
                {
                    "step_id": item.step_id,
                    **(
                        {"timestamp_ns": int(item.timestamp_ns)}
                        if item.timestamp_ns is not None
                        else {}
                    ),
                    "snapshot": _format_snapshot_path(
                        item.path,
                        snapshot_root=snapshot_root,
                        absolute_paths=absolute_paths,
                    ),
                }
            )
        payload["episodes"].append(
            {
                "episode_index": episode_index,
                "snapshots": episode_snapshots,
            }
        )

    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=False)


def _deduplicate_snapshots(
    snapshots: list[SnapshotEntry],
    *,
    episode_index: int,
    duplicate_policy: str,
) -> list[SnapshotEntry]:
    by_step: dict[int, list[SnapshotEntry]] = {}
    for item in snapshots:
        by_step.setdefault(item.step_id, []).append(item)

    selected: list[SnapshotEntry] = []
    for step_id in sorted(by_step):
        candidates = by_step[step_id]
        if len(candidates) > 1 and duplicate_policy == "error":
            raise ValueError(
                f"duplicate step_id {step_id} for episode {episode_index}"
            )
        selected.append(
            max(
                candidates,
                key=lambda item: (
                    item.timestamp_ns if item.timestamp_ns is not None else -1,
                    item.sequence_index,
                    item.path.stat().st_mtime_ns,
                    item.path.name,
                ),
            )
        )
    return selected


def _scan_snapshot_entries(snapshot_root: Path, *, pattern: str) -> list[SnapshotEntry]:
    entries: list[SnapshotEntry] = []
    for path in sorted(snapshot_root.glob(pattern)):
        if not path.is_file():
            continue
        entry = _read_snapshot_entry(path)
        if entry is not None:
            entries.append(entry)
    return entries


def _read_snapshot_entry(path: Path) -> SnapshotEntry | None:
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON snapshot: {path}") from exc

    metadata = payload.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    episode_index = _int_from_metadata_or_filename(
        metadata,
        "episode_index",
        path.name,
        _EPISODE_RE,
    )
    step_id = _int_from_metadata_or_filename(
        metadata,
        "step_id",
        path.name,
        _STEP_RE,
    )
    if episode_index is None or step_id is None:
        return None

    sequence_index = int(metadata.get("sequence_index", -1))
    session_id = str(metadata.get("session_id") or _session_from_filename(path.name))
    timestamp_ns = _timestamp_ns_from_metadata(metadata)
    return SnapshotEntry(
        episode_index=episode_index,
        step_id=step_id,
        path=path,
        session_id=session_id,
        sequence_index=sequence_index,
        timestamp_ns=timestamp_ns,
    )


def _int_from_metadata_or_filename(
    metadata: dict[str, Any],
    key: str,
    filename: str,
    pattern: re.Pattern[str],
) -> int | None:
    value = metadata.get(key)
    if value is not None:
        return int(value)
    match = pattern.search(filename)
    return int(match.group(1)) if match else None


def _session_from_filename(filename: str) -> str:
    match = _SESSION_RE.search(filename)
    return match.group("session") if match else ""


def _timestamp_ns_from_metadata(metadata: dict[str, Any]) -> int | None:
    value = metadata.get("wall_time_unix_ns")
    if value is not None:
        return int(value)

    wall_time_utc = metadata.get("wall_time_utc")
    if not wall_time_utc:
        return None

    text = str(wall_time_utc)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    text = _trim_fractional_seconds_to_microseconds(text)
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return int(dt.timestamp() * 1_000_000_000)


def _trim_fractional_seconds_to_microseconds(text: str) -> str:
    match = re.match(r"^(?P<prefix>.*?\.)(?P<fraction>\d{7,})(?P<suffix>(?:[+-]\d\d:\d\d)?)$", text)
    if match is None:
        return text
    return (
        match.group("prefix")
        + match.group("fraction")[:6]
        + match.group("suffix")
    )


def _entry_matches(
    entry: SnapshotEntry,
    *,
    session_id: str | None,
    allowed_episodes: set[int],
) -> bool:
    if session_id is not None and entry.session_id != session_id:
        return False
    if allowed_episodes and entry.episode_index not in allowed_episodes:
        return False
    return True


def _format_snapshot_path(
    path: Path,
    *,
    snapshot_root: Path,
    absolute_paths: bool,
) -> str:
    if absolute_paths:
        return str(path.resolve())
    return str(path.resolve().relative_to(snapshot_root.resolve()))


def _count_episode_entries(text: str) -> int:
    payload = yaml.safe_load(text) or {}
    episodes = payload.get("episodes") or []
    return len(episodes)


if __name__ == "__main__":
    main()
