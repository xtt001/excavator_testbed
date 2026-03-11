"""
Video saving utilities for evaluation.

Two entry points:
  save_videos(image_dict_or_list, dt, path)
      Direct port of legacy visualize_episodes.save_videos — accepts both
      list-of-dicts (per-step) and dict-of-arrays (per-camera) formats.

  save_eval_video(frames, dt, path, reward_curve, phase_labels, success)
      Enriched version with on-frame overlays:
        • Reward curve in top-right corner
        • Phase label (e.g. "LIFT", "DUMP") in bottom-left
        • "SUCCESS" / "FAIL" banner on final frame
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import cv2
import numpy as np


# ─── Legacy-compatible save_videos ───────────────────────────────────────────

def save_videos(
    video,
    dt: float,
    video_path: str | Path | None = None,
) -> None:
    """
    Save a multi-camera video to an MP4 file.

    Parameters
    ----------
    video       Either:
                  • list[dict[cam_name, (H,W,3) uint8]]  — one dict per step
                  • dict[cam_name, (T,H,W,3) uint8]      — one array per camera
    dt          Timestep (seconds); fps = 1/dt.
    video_path  Output file path.  If None, nothing is written.
    """
    if video_path is None:
        return

    video_path = Path(video_path)
    video_path.parent.mkdir(parents=True, exist_ok=True)
    fps = max(1, int(round(1.0 / dt)))

    if isinstance(video, list):
        # list-of-dicts format
        cam_names = list(video[0].keys())
        h, w, _ = video[0][cam_names[0]].shape
        total_w  = w * len(cam_names)
        out = cv2.VideoWriter(
            str(video_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (total_w, h),
        )
        for img_dict in video:
            frames = [img_dict[c][:, :, ::-1] for c in cam_names]  # RGB→BGR
            out.write(np.concatenate(frames, axis=1))
        out.release()

    elif isinstance(video, dict):
        # dict-of-arrays format
        cam_names = list(video.keys())
        all_arrays = np.concatenate(
            [video[c] for c in cam_names], axis=2
        )  # (T, H, W_total, 3)
        n_frames, h, w, _ = all_arrays.shape
        out = cv2.VideoWriter(
            str(video_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (w, h),
        )
        for t in range(n_frames):
            out.write(all_arrays[t, :, :, ::-1])  # RGB→BGR
        out.release()

    else:
        raise TypeError(f"save_videos: unsupported video type {type(video)}")

    print(f"Saved video to: {video_path}")


# ─── Enriched eval video ──────────────────────────────────────────────────────

def save_eval_video(
    frames: list[np.ndarray] | np.ndarray,
    dt: float,
    video_path: str | Path,
    *,
    reward_curve: Sequence[float] | None = None,
    phase_labels: Sequence[str] | None = None,
    success: bool | None = None,
) -> None:
    """
    Save a single-camera evaluation video with overlays.

    Parameters
    ----------
    frames        (T, H, W, 3) uint8 array or list of (H, W, 3) frames.
    dt            Timestep in seconds.
    video_path    Output path.
    reward_curve  Per-step rewards (length T).  If provided, a reward bar
                  graph is rendered in the top-right corner.
    phase_labels  Per-step phase label strings.  Rendered bottom-left.
    success       If provided, final frame gets a SUCCESS/FAIL banner.
    """
    frames_arr = np.array(frames, dtype=np.uint8)  # (T, H, W, 3)
    T, H, W, _ = frames_arr.shape
    fps = max(1, int(round(1.0 / dt)))

    video_path = Path(video_path)
    video_path.parent.mkdir(parents=True, exist_ok=True)

    out = cv2.VideoWriter(
        str(video_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (W, H),
    )

    max_r = max(reward_curve) if reward_curve is not None else 1.0

    for t, frame in enumerate(frames_arr):
        img = frame[:, :, ::-1].copy()  # RGB → BGR

        # ── phase label ───────────────────────────────────────────────────
        if phase_labels is not None and t < len(phase_labels):
            label = str(phase_labels[t])
            cv2.putText(
                img, label,
                (10, H - 15),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7,
                (255, 255, 255), 2, cv2.LINE_AA,
            )

        # ── step counter ──────────────────────────────────────────────────
        cv2.putText(
            img, f"t={t}",
            (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX, 0.55,
            (200, 200, 200), 1, cv2.LINE_AA,
        )

        # ── reward bar ────────────────────────────────────────────────────
        if reward_curve is not None and t < len(reward_curve):
            r = float(reward_curve[t])
            bar_h    = 12
            bar_maxw = 120
            bar_x    = W - bar_maxw - 10
            bar_y    = 10
            fill = int(bar_maxw * r / max(max_r, 1e-6))
            cv2.rectangle(img, (bar_x, bar_y), (bar_x + bar_maxw, bar_y + bar_h), (80, 80, 80), -1)
            cv2.rectangle(img, (bar_x, bar_y), (bar_x + fill, bar_y + bar_h), (0, 200, 100), -1)
            cv2.putText(
                img, f"r={r:.2f}",
                (bar_x, bar_y + bar_h + 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4,
                (200, 200, 200), 1, cv2.LINE_AA,
            )

        # ── final-frame banner ────────────────────────────────────────────
        if t == T - 1 and success is not None:
            text  = "SUCCESS" if success else "FAIL"
            color = (0, 220, 0) if success else (0, 0, 220)
            font_scale = 2.0
            thickness  = 3
            (tw, th), _ = cv2.getTextSize(
                text, cv2.FONT_HERSHEY_DUPLEX, font_scale, thickness
            )
            tx = (W - tw) // 2
            ty = (H + th) // 2
            # dark shadow
            cv2.putText(img, text, (tx + 2, ty + 2),
                        cv2.FONT_HERSHEY_DUPLEX, font_scale, (0, 0, 0), thickness + 2, cv2.LINE_AA)
            cv2.putText(img, text, (tx, ty),
                        cv2.FONT_HERSHEY_DUPLEX, font_scale, color, thickness, cv2.LINE_AA)

        out.write(img)

    out.release()
    print(f"Saved eval video to: {video_path}")
