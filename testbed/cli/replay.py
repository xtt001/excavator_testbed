"""
tb-replay — Replay recorded HDF5 episodes back through AGXUnity.

Usage
-----
    # Single episode
    tb-replay --episode data/agx_teleop/episode_0.hdf5

    # All episodes in a directory (sorted by episode index)
    tb-replay --episode data/agx_teleop_v1/

    # With config and video output
    tb-replay --episode data/agx_teleop_v1/ --config testbed/configs/teleop_v1.yaml --save-video

Purpose
-------
QA check: replay action[t] step-by-step and verify that:
  - qpos/qvel time series are visually consistent with the recording
  - step_id increments match expectations

Outputs (when --save-video)
    runs/replay/<episode_stem>_replay.mp4
"""

from __future__ import annotations

import argparse
import logging
import re
import time
from pathlib import Path

import numpy as np
import yaml

log = logging.getLogger(__name__)


def _episode_sort_key(path: Path) -> tuple[int, str]:
    """Sort episode files by numeric index, falling back to name."""
    match = re.search(r"episode_(\d+)", path.stem)
    return (int(match.group(1)), path.stem) if match else (999999, path.stem)


def _resolve_episodes(path: Path) -> list[Path]:
    """Return a sorted list of .hdf5 episode files from a file or directory."""
    if path.is_file():
        return [path]
    if path.is_dir():
        episodes = sorted(path.glob("episode_*.hdf5"), key=_episode_sort_key)
        if not episodes:
            episodes = sorted(path.glob("*.hdf5"), key=_episode_sort_key)
        return episodes
    raise FileNotFoundError(f"Not a file or directory: {path}")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    parser = argparse.ArgumentParser(
        prog="tb-replay",
        description="Replay recorded HDF5 episode(s) through AGX and optionally record video.",
    )
    parser.add_argument("--episode", "-e", type=Path, required=True,
                        help="Path to a single episode_N.hdf5 or a directory of episodes.")
    parser.add_argument("--config", "-c", type=Path, default=None,
                        help="Teleop YAML config (for AGX host/port). "
                             "If omitted, uses defaults (localhost:5057).")
    parser.add_argument("--save-video", action="store_true",
                        help="Save fpv frames to an mp4 video file.")
    parser.add_argument("--video-dir", type=Path, default=Path("runs/replay"),
                        help="Output directory for replay videos.")
    parser.add_argument("--realtime", action="store_true",
                        help="Sleep between steps to match original control rate.")
    args = parser.parse_args()

    episodes = _resolve_episodes(args.episode)
    if not episodes:
        log.error("No .hdf5 episode files found at %s", args.episode)
        return
    log.info("Found %d episode(s) to replay.", len(episodes))

    # ── Load config ───────────────────────────────────────────────────────────
    agx_cfg: dict = {}
    task_cfg: dict = {}
    success_cfg: dict = {}
    reward_cfg: dict = {}
    if args.config:
        with open(args.config) as f:
            cfg = yaml.safe_load(f) or {}
        agx_cfg  = cfg.get("agx", {})
        task_cfg = cfg.get("task", {})
        success_cfg = cfg.get("success", {})
        reward_cfg = cfg.get("reward", {})

    # ── Build backend (shared across all episodes) ────────────────────────────
    from testbed.backends.agx.backend import AGXSimBackend
    from testbed.tasks.logic.excavator_reward import (
        build_agx_excavation_mission_overrides,
    )

    first_meta = _peek_metadata(episodes[0], task_cfg)
    reward_overrides = build_agx_excavation_mission_overrides(
        success_cfg=success_cfg,
        reward_cfg=reward_cfg,
    )
    backend = AGXSimBackend(
        host=agx_cfg.get("host", "127.0.0.1"),
        port=agx_cfg.get("port", 5057),
        timeout=agx_cfg.get("timeout", 10.0),
        task_name=first_meta["task_name"],
        reward_overrides=reward_overrides,
    )

    # ── Replay each episode ───────────────────────────────────────────────────
    summary: list[dict] = []
    try:
        for ep_idx, ep_path in enumerate(episodes):
            result = _replay_one(
                backend=backend,
                ep_path=ep_path,
                ep_idx=ep_idx,
                total=len(episodes),
                task_cfg=task_cfg,
                save_video=args.save_video,
                video_dir=args.video_dir,
                realtime=args.realtime,
            )
            summary.append(result)
    finally:
        backend.close()

    # ── Summary ───────────────────────────────────────────────────────────────
    _print_batch_summary(summary)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _peek_metadata(ep_path: Path, task_cfg: dict) -> dict:
    from testbed.data.hdf5_io import read_episode
    ep = read_episode(ep_path)
    meta = ep.get("metadata", {})
    return {
        "task_name": str(meta.get("task_name", task_cfg.get("task_name", "agx_excavation_teleop"))),
    }


def _replay_one(
    *,
    backend,
    ep_path: Path,
    ep_idx: int,
    total: int,
    task_cfg: dict,
    save_video: bool,
    video_dir: Path,
    realtime: bool,
) -> dict:
    from testbed.data.hdf5_io import read_episode
    ep = read_episode(ep_path)

    actions:  np.ndarray = ep["actions"]
    qpos_ref: np.ndarray = ep["qpos"]
    meta:     dict       = ep.get("metadata", {})
    T = len(actions)

    control_hz = float(meta.get("control_hz", task_cfg.get("control_hz", 50)))
    seed       = int(meta.get("seed", -1))

    log.info(
        "[%d/%d] Episode: %s  T=%d  control_hz=%.0f  seed=%d",
        ep_idx + 1, total, ep_path.name, T, control_hz, seed,
    )

    frames: list[np.ndarray] = []
    qpos_replay: list[np.ndarray] = []

    ts = backend.reset(seed=seed)

    for t in range(T):
        ts = backend.step(actions[t])
        obs = ts.observation

        qpos_replay.append(obs["qpos"].copy())

        if save_video and "fpv" in obs["images"] and obs["images"]["fpv"] is not None:
            frames.append(obs["images"]["fpv"].copy())

        if realtime:
            time.sleep(1.0 / control_hz)

        if (t + 1) % 100 == 0:
            log.info("  step %d / %d", t + 1, T)

    qpos_arr = np.stack(qpos_replay)
    min_T = min(len(qpos_ref), len(qpos_arr))
    diff = np.abs(qpos_ref[:min_T] - qpos_arr[:min_T])
    mean_diff, max_diff = float(diff.mean()), float(diff.max())
    log.info(
        "[%d/%d] QA — qpos diff: mean=%.4f  max=%.4f  (%d steps)",
        ep_idx + 1, total, mean_diff, max_diff, min_T,
    )

    if save_video and frames:
        video_dir.mkdir(parents=True, exist_ok=True)
        out_path = video_dir / f"{ep_path.stem}_replay.mp4"
        _save_video(frames, out_path, fps=int(control_hz))
        log.info("[%d/%d] Video saved → %s", ep_idx + 1, total, out_path)

    return {
        "episode": ep_path.name,
        "steps": T,
        "qpos_mean_diff": mean_diff,
        "qpos_max_diff": max_diff,
    }


def _print_batch_summary(summary: list[dict]) -> None:
    if not summary:
        return
    log.info("=" * 60)
    log.info("Batch replay summary: %d episode(s)", len(summary))
    log.info("%-25s %6s %12s %12s", "episode", "steps", "mean_diff", "max_diff")
    for s in summary:
        log.info(
            "%-25s %6d %12.4f %12.4f",
            s["episode"], s["steps"], s["qpos_mean_diff"], s["qpos_max_diff"],
        )
    all_mean = np.mean([s["qpos_mean_diff"] for s in summary])
    all_max  = np.max([s["qpos_max_diff"]  for s in summary])
    log.info("%-25s %6s %12.4f %12.4f", "OVERALL", "", all_mean, all_max)
    log.info("=" * 60)


def _save_video(frames: list[np.ndarray], path: Path, fps: int = 50) -> None:
    """Write frames as an mp4 using OpenCV."""
    try:
        import cv2
    except ImportError:
        log.error("opencv-python not installed — cannot save video.")
        return

    if not frames:
        return

    h, w = frames[0].shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, (w, h))
    for frame in frames:
        writer.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
    writer.release()


if __name__ == "__main__":
    main()
