"""
tb-replay — Replay a recorded HDF5 episode back through AGXUnity.

Usage
-----
    tb-replay --episode data/agx_teleop/episode_0.hdf5
    tb-replay --episode data/agx_teleop/episode_0.hdf5 --config testbed/configs/teleop_v0.yaml
    tb-replay --episode data/agx_teleop/episode_0.hdf5 --save-video

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
import time
from pathlib import Path

import numpy as np
import yaml

log = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )

    parser = argparse.ArgumentParser(
        prog="tb-replay",
        description="Replay a recorded HDF5 episode through AGX and optionally record video.",
    )
    parser.add_argument("--episode", "-e", type=Path, required=True,
                        help="Path to episode_N.hdf5 to replay.")
    parser.add_argument("--config", "-c", type=Path, default=None,
                        help="Teleop YAML config (for AGX host/port). "
                             "If omitted, uses defaults (localhost:9000).")
    parser.add_argument("--save-video", action="store_true",
                        help="Save fpv frames to an mp4 video file.")
    parser.add_argument("--video-dir", type=Path, default=Path("runs/replay"),
                        help="Output directory for replay videos.")
    parser.add_argument("--realtime", action="store_true",
                        help="Sleep between steps to match original control rate.")
    args = parser.parse_args()

    # ── Load config ───────────────────────────────────────────────────────────
    agx_cfg: dict = {}
    task_cfg: dict = {}
    if args.config:
        with open(args.config) as f:
            cfg = yaml.safe_load(f) or {}
        agx_cfg  = cfg.get("agx", {})
        task_cfg = cfg.get("task", {})

    # ── Load episode ──────────────────────────────────────────────────────────
    from testbed.data.hdf5_io import read_episode
    ep = read_episode(args.episode)

    actions:  np.ndarray = ep["actions"]    # (T, 4)
    qpos_ref: np.ndarray = ep["qpos"]       # (T, 3)
    meta:     dict       = ep.get("metadata", {})
    T = len(actions)

    control_hz = float(meta.get("control_hz", task_cfg.get("control_hz", 50)))
    seed       = int(meta.get("seed", -1))

    log.info("Episode: %s  T=%d  control_hz=%.0f  seed=%d",
             args.episode.name, T, control_hz, seed)
    if ep.get("action_src_types"):
        log.info("Original source: %s / %s",
                 ep["action_src_types"][0], ep.get("action_src_ids", ["?"])[0])

    # ── Build backend ─────────────────────────────────────────────────────────
    from testbed.backends.agx.backend import AGXSimBackend
    backend = AGXSimBackend(
        host=agx_cfg.get("host", "127.0.0.1"),
        port=agx_cfg.get("port", 9000),
        timeout=agx_cfg.get("timeout", 10.0),
    )

    # ── Replay loop ───────────────────────────────────────────────────────────
    frames: list[np.ndarray] = []
    qpos_replay: list[np.ndarray] = []
    qvel_replay: list[np.ndarray] = []

    try:
        ts = backend.reset(seed=seed)

        for t in range(T):
            action = actions[t]
            ts     = backend.step(action)
            obs    = ts.observation

            qpos_replay.append(obs["qpos"].copy())
            qvel_replay.append(obs["qvel"].copy())

            if args.save_video and "fpv" in obs["images"] and obs["images"]["fpv"] is not None:
                frames.append(obs["images"]["fpv"].copy())

            if args.realtime:
                time.sleep(1.0 / control_hz)

            if (t + 1) % 50 == 0:
                log.info("  step %d / %d", t + 1, T)

    finally:
        backend.close()

    # ── QA report ─────────────────────────────────────────────────────────────
    qpos_arr = np.stack(qpos_replay)
    _print_replay_qa(qpos_ref, qpos_arr)

    # ── Save video ────────────────────────────────────────────────────────────
    if args.save_video and frames:
        args.video_dir.mkdir(parents=True, exist_ok=True)
        out_path = args.video_dir / f"{args.episode.stem}_replay.mp4"
        _save_video(frames, out_path, fps=int(control_hz))
        log.info("Video saved → %s", out_path)

    log.info("Replay done.")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _print_replay_qa(ref: np.ndarray, replay: np.ndarray) -> None:
    """Print a simple qpos comparison between recorded and replayed."""
    min_T = min(len(ref), len(replay))
    diff  = np.abs(ref[:min_T] - replay[:min_T])
    log.info(
        "QA — qpos diff: mean=%.4f  max=%.4f  (over %d steps)",
        diff.mean(), diff.max(), min_T,
    )


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
