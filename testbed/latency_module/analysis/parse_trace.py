"""
parse_trace.py — Load a trace.jsonl file into a pandas DataFrame.

Usage
-----
    from testbed.latency_module.analysis.parse_trace import load_trace, filter_events

    df = load_trace("outputs/run_20240101_abc123/trace.jsonl")
    cmd_recv = filter_events(df, "cmd_recv")
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


def load_trace(trace_path: str | Path) -> pd.DataFrame:
    """
    Load a JSONL trace file into a DataFrame.

    Each line is one LogEntry.  Returns an empty DataFrame if the file is
    empty or does not exist.
    """
    trace_path = Path(trace_path)
    if not trace_path.exists():
        return pd.DataFrame()

    df = pd.read_json(trace_path, lines=True)
    if df.empty:
        return df

    # Ensure numeric types for key fields
    for col in ("timestamp_ns", "sim_time_ns", "round_trip_ms", "payload_bytes",
                "cmd_id", "frame_id", "step_id"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Derived wall-clock column in seconds (useful for time-series plots)
    if "timestamp_ns" in df.columns:
        t0 = df["timestamp_ns"].min()
        df["t_s"] = (df["timestamp_ns"] - t0) / 1e9

    return df.sort_values("timestamp_ns").reset_index(drop=True)


def filter_events(df: pd.DataFrame, event_name: str) -> pd.DataFrame:
    """Return only rows where event_name matches."""
    if df.empty or "event_name" not in df.columns:
        return pd.DataFrame()
    return df[df["event_name"] == event_name].copy()


def pivot_step_latency(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build a per-step latency table by pivoting cmd_send / cmd_recv events.

    Returns a DataFrame with columns:
        cmd_id, episode_id, run_id,
        t_send_ns, t_recv_ns, round_trip_ms,
        sim_time_ns, payload_bytes,
        delay_inject_ms, jitter_inject_ms, loss_rate,
        resolution, fps, bitrate, codec
    """
    if df.empty:
        return pd.DataFrame()

    sends  = filter_events(df, "cmd_send").set_index("cmd_id")
    recvs  = filter_events(df, "cmd_recv").set_index("cmd_id")
    apply_ = filter_events(df, "cmd_apply").set_index("cmd_id")

    result = pd.DataFrame(index=sends.index)

    # Timestamps
    result["t_send_ns"] = sends["timestamp_ns"]
    result["t_recv_ns"] = recvs["timestamp_ns"] if not recvs.empty else pd.NA

    # Latency (use pre-computed field if available, else compute from ts)
    if "round_trip_ms" in recvs.columns and not recvs.empty:
        result["round_trip_ms"] = recvs["round_trip_ms"]
    elif "t_recv_ns" in result.columns:
        result["round_trip_ms"] = (
            result["t_recv_ns"] - result["t_send_ns"]
        ) / 1e6

    # Unity sim context
    if not apply_.empty and "sim_time_ns" in apply_.columns:
        result["sim_time_ns"] = apply_["sim_time_ns"]

    # Image info
    if not recvs.empty and "payload_bytes" in recvs.columns:
        result["payload_bytes"] = recvs["payload_bytes"]

    # Context columns (copy from sends)
    for col in ("episode_id", "run_id", "delay_inject_ms", "jitter_inject_ms",
                "loss_rate", "resolution", "fps", "bitrate", "codec"):
        if col in sends.columns:
            result[col] = sends[col]

    return result.reset_index()


def load_all_runs(outputs_dir: str | Path) -> pd.DataFrame:
    """
    Load and concatenate trace.jsonl files from all run subdirectories
    under outputs_dir.

    Useful for multi-config comparison experiments.
    """
    outputs_dir = Path(outputs_dir)
    frames: list[pd.DataFrame] = []
    for trace_file in sorted(outputs_dir.glob("*/trace.jsonl")):
        df = load_trace(trace_file)
        if not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)
