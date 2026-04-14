"""
hdf5_bridge.py — Extract timing information from existing HDF5 episodes
and convert them into latency_module trace format for offline analysis.

This bridges historical recorded data (which has timestamps/step_ns)
into the same analysis pipeline as live-instrumented traces.

Usage
-----
    from testbed.latency_module.analysis.hdf5_bridge import dataset_to_trace
    df = dataset_to_trace("data/agx_teleop_fulltest", label="fulltest_720x480")

    # Or generate a trace.jsonl from an entire dataset directory:
    python -m testbed.latency_module.analysis.hdf5_bridge \
        --dataset data/agx_teleop_fulltest \
        --label   fulltest_720x480 \
        --out     outputs/hdf5_analysis/fulltest
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def episode_step_intervals(hdf5_path: str | Path) -> dict[str, Any]:
    """
    Extract per-step timing from one HDF5 episode.

    Returns a dict with:
        step_ns      (N,)  wall-clock ns for each recorded step
        step_interval_ms  (N-1,)  time between consecutive steps (= RTT proxy)
        image_shape  tuple  (H, W, C)
        n_steps      int
        metadata     dict
    """
    import h5py
    p = Path(hdf5_path)
    with h5py.File(p, "r") as f:
        step_ns = f["timestamps/step_ns"][:].astype(np.int64) if "timestamps" in f else None
        img_shape = tuple(f["observations/images/fpv"].shape[1:]) if "observations/images/fpv" in f else None
        n_steps = len(f["observations/qpos"]) if "observations/qpos" in f else 0
        meta = dict(f["metadata"].attrs) if "metadata" in f else {}

    result: dict[str, Any] = {
        "step_ns":    step_ns,
        "n_steps":    n_steps,
        "image_shape": img_shape,
        "metadata":   meta,
    }
    if step_ns is not None and len(step_ns) > 1:
        result["step_interval_ms"] = np.diff(step_ns) / 1e6
    else:
        result["step_interval_ms"] = np.array([])
    return result


def dataset_to_trace(
    dataset_dir: str | Path,
    *,
    label: str = "",
    delay_inject_ms: float = 0.0,
    jitter_inject_ms: float = 0.0,
    loss_rate: float = 0.0,
    resolution: str = "",
) -> pd.DataFrame:
    """
    Build a DataFrame in latency-module trace format from all episodes in a
    dataset directory.

    Each row corresponds to one step's timing event (event_name = 'cmd_recv').
    The step_interval_ms is used as the round_trip_ms proxy.

    Parameters
    ----------
    dataset_dir       Directory containing episode_N.hdf5 files.
    label             Experiment label (used as run_id).
    delay_inject_ms   Metadata: injected one-way delay (0 for historical data).
    """
    import os
    dataset_dir = Path(dataset_dir)
    eps = sorted(
        [f for f in os.listdir(dataset_dir) if f.endswith(".hdf5")],
        key=lambda x: int(x.split("_")[1].split(".")[0]),
    )

    run_id = label or dataset_dir.name
    rows: list[dict] = []
    ep_idx = 0

    for ep_file in eps:
        ep = episode_step_intervals(dataset_dir / ep_file)
        intervals = ep["step_interval_ms"]
        step_ns   = ep["step_ns"]
        img_shape = ep["image_shape"]
        meta      = ep["metadata"]

        if img_shape:
            res_str = resolution or f"{img_shape[1]}x{img_shape[0]}"
            payload_bytes = img_shape[0] * img_shape[1] * img_shape[2]
        else:
            res_str = resolution or ""
            payload_bytes = -1

        for i, interval_ms in enumerate(intervals):
            # step_ns[i+1] is when step i+1 completed — use as recv timestamp
            ts_recv = int(step_ns[i + 1]) if step_ns is not None else -1
            rows.append({
                "timestamp_ns":      ts_recv,
                "event_name":        "cmd_recv",
                "run_id":            run_id,
                "trace_id":          run_id,
                "episode_id":        f"episode_{ep_idx}",
                "cmd_id":            i,
                "frame_id":          i,
                "round_trip_ms":     float(interval_ms),
                "payload_bytes":     payload_bytes,
                "resolution":        res_str,
                "delay_inject_ms":   delay_inject_ms,
                "jitter_inject_ms":  jitter_inject_ms,
                "loss_rate":         loss_rate,
                "control_hz":        float(meta.get("control_hz", 50)),
                "target_dt_ms":      1000.0 / float(meta.get("control_hz", 50)),
            })
        ep_idx += 1

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    t0 = df["timestamp_ns"].min()
    df["t_s"] = (df["timestamp_ns"] - t0) / 1e9
    return df.sort_values("timestamp_ns").reset_index(drop=True)


def save_trace(df: pd.DataFrame, out_dir: str | Path) -> Path:
    """Save a DataFrame as trace.jsonl in out_dir."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    trace_path = out_dir / "trace.jsonl"
    with open(trace_path, "w") as f:
        for row in df.to_dict(orient="records"):
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"  [hdf5_bridge] wrote {len(df)} events → {trace_path}")
    return trace_path


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        prog="hdf5-bridge",
        description="Convert HDF5 dataset timing into latency_module trace.",
    )
    parser.add_argument("--dataset", "-d", type=Path, required=True)
    parser.add_argument("--label",   "-l", type=str, default="")
    parser.add_argument("--out",     "-o", type=Path, required=True)
    parser.add_argument("--delay-inject-ms",  type=float, default=0.0)
    parser.add_argument("--jitter-inject-ms", type=float, default=0.0)
    parser.add_argument("--resolution", type=str, default="")
    args = parser.parse_args()

    df = dataset_to_trace(
        args.dataset,
        label=args.label or args.dataset.name,
        delay_inject_ms=args.delay_inject_ms,
        jitter_inject_ms=args.jitter_inject_ms,
        resolution=args.resolution,
    )
    if df.empty:
        print("No timing data found.")
        return

    run_dir = args.out / (args.label or args.dataset.name)
    save_trace(df, run_dir)

    from testbed.latency_module.analysis.export_summary import export_run_summary
    export_run_summary(run_dir)


if __name__ == "__main__":
    main()
