"""Shared path conventions for depth-graph teleop smoke sessions."""

from __future__ import annotations

import os
from pathlib import Path


DEFAULT_UNITY_DEPTH_SNAPSHOT_ROOT = Path(
    "/home/zhaoshuai/workspace_uinty/GraphPerceptionPrj/output/DepthCameraSnapshots"
)


def sanitize_session_id(value: str) -> str:
    """Return a filesystem-friendly session token."""
    token = str(value).strip()
    if not token:
        raise ValueError("session id must not be empty.")
    chars = []
    for char in token:
        if char.isalnum() or char in {"-", "_"}:
            chars.append(char)
        else:
            chars.append("_")
    return "".join(chars)


def default_depth_snapshot_root_base(
    *,
    configured_root: str | Path | None = None,
) -> Path:
    """Resolve the base Unity depth snapshot root.

    Priority:
    1. explicit config/CLI value
    2. TESTBED_DEPTH_SNAPSHOT_ROOT
    3. current workspace's known Unity Repo B output root
    """
    if configured_root:
        return Path(configured_root).expanduser()
    env_value = os.environ.get("TESTBED_DEPTH_SNAPSHOT_ROOT")
    if env_value:
        return Path(env_value).expanduser()
    return DEFAULT_UNITY_DEPTH_SNAPSHOT_ROOT


def teleop_dir_for_session(session_id: str) -> Path:
    return session_data_dir(session_id) / "teleop"


def depth_snapshot_dir_for_session(
    session_id: str,
    *,
    root: str | Path | None = None,
) -> Path:
    token = sanitize_session_id(session_id)
    return default_depth_snapshot_root_base(configured_root=root) / token


def snapshot_map_for_session(session_id: str) -> Path:
    return session_data_dir(session_id) / "graph_attach.yaml"


def graph_dataset_dir_for_session(session_id: str) -> Path:
    return session_data_dir(session_id) / "graph_time_v1"


def session_data_dir(session_id: str) -> Path:
    token = sanitize_session_id(session_id)
    return Path("data") / "graph_sessions" / token
