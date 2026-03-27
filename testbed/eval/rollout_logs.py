"""Helpers for saving per-rollout timestep logs and summaries."""

from __future__ import annotations

import collections
import datetime
import json
from pathlib import Path
from typing import Any

import numpy as np


def to_jsonable(value: Any) -> Any:
    """Convert numpy-heavy rollout data into JSON-serialisable values."""
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def write_json(path: Path | str, payload: dict[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(to_jsonable(payload), f, indent=2)
    return path


def write_jsonl(path: Path | str, rows: list[dict[str, Any]]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for row in rows:
            f.write(json.dumps(to_jsonable(row), separators=(",", ":")))
            f.write("\n")
    return path


def build_rollout_summary(
    *,
    rollout_id: int,
    success: bool,
    rewards: list[float],
    step_records: list[dict[str, Any]],
    video_path: str = "",
) -> dict[str, Any]:
    failure_counts: collections.Counter[str] = collections.Counter()
    first_success_step: int | None = None
    first_failure_step: int | None = None

    for record in step_records:
        step_index = int(record.get("t", 0))
        task_success = bool(record.get("task_success", False))
        task_step_successes = list(record.get("task_step_successes", []))
        task_step_failures = list(record.get("task_step_failures", []))

        if first_success_step is None and (task_success or task_step_successes):
            first_success_step = step_index
        if task_step_failures and first_failure_step is None:
            first_failure_step = step_index
        failure_counts.update(task_step_failures)

    return {
        "rollout_id": int(rollout_id),
        "generated_at": datetime.datetime.utcnow().isoformat(),
        "success": bool(success),
        "episode_return": float(np.sum(rewards)) if rewards else 0.0,
        "episode_len": len(rewards),
        "highest_reward": float(max(rewards)) if rewards else 0.0,
        "first_success_step": first_success_step,
        "first_failure_step": first_failure_step,
        "failure_counts": dict(sorted(failure_counts.items())),
        "video_path": str(video_path),
    }


def build_rollout_manifest(
    *,
    task_name: str,
    policy_name: str,
    ckpt_path: str,
    rollout_log_dir: Path | str,
    rollouts: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "generated_at": datetime.datetime.utcnow().isoformat(),
        "task_name": task_name,
        "policy_name": policy_name,
        "ckpt_path": str(ckpt_path),
        "rollout_log_dir": str(rollout_log_dir),
        "n_rollouts": len(rollouts),
        "rollouts": [to_jsonable(rollout) for rollout in rollouts],
    }
