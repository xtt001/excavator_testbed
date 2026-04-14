"""
compute_metrics.py — Compute latency statistics from a parsed trace.

Functions
---------
latency_stats(series)
    Return a dict with mean / median / std / p90 / p95 / p99 / min / max.

compute_step_metrics(df_steps)
    Compute full per-run latency summary from the pivot table returned by
    parse_trace.pivot_step_latency().

compute_chain_metrics(df_trace)
    Compute per-chain (control / video / feedback) latency metrics from the
    raw trace DataFrame.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ── Core statistics helper ────────────────────────────────────────────────────

def latency_stats(series: pd.Series) -> dict:
    """
    Compute descriptive statistics for a latency series (ms).

    Returns
    -------
    dict with keys: mean, median, std, p90, p95, p99, min, max, count
    """
    s = series.dropna()
    if s.empty:
        return {k: float("nan") for k in
                ("mean", "median", "std", "p90", "p95", "p99", "min", "max", "count")}
    return {
        "mean":   float(s.mean()),
        "median": float(s.median()),
        "std":    float(s.std()),
        "p90":    float(np.percentile(s, 90)),
        "p95":    float(np.percentile(s, 95)),
        "p99":    float(np.percentile(s, 99)),
        "min":    float(s.min()),
        "max":    float(s.max()),
        "count":  int(len(s)),
    }


# ── Step-level metrics (from pivot table) ────────────────────────────────────

def compute_step_metrics(df_steps: pd.DataFrame) -> dict:
    """
    Compute latency summary from the per-step pivot table produced by
    parse_trace.pivot_step_latency().

    Returns a nested dict:
        {
          "step_round_trip": { mean, median, std, p90, p95, p99, min, max, count },
          "by_config": { <config_key>: { ... } }   # if multiple configs present
        }
    """
    if df_steps.empty or "round_trip_ms" not in df_steps.columns:
        return {}

    result: dict = {}

    # Overall stats
    result["step_round_trip_ms"] = latency_stats(df_steps["round_trip_ms"])

    # Per-config breakdown (group by delay_inject_ms if available)
    groupby_cols = [c for c in ("delay_inject_ms", "jitter_inject_ms", "resolution",
                                "bitrate", "run_id")
                    if c in df_steps.columns and df_steps[c].nunique() > 1]
    if groupby_cols:
        by_config: dict = {}
        for keys, group in df_steps.groupby(groupby_cols):
            if not isinstance(keys, tuple):
                keys = (keys,)
            label = "_".join(f"{c}={v}" for c, v in zip(groupby_cols, keys))
            by_config[label] = latency_stats(group["round_trip_ms"])
        result["by_config"] = by_config

    return result


# ── Chain-level metrics (from raw trace) ─────────────────────────────────────

def compute_chain_metrics(df_trace: pd.DataFrame) -> dict:
    """
    Compute per-chain latency metrics from the raw LogEntry DataFrame.

    This function looks for pre-computed round_trip_ms in cmd_recv events
    (fastest path) and also reconstructs from timestamps if needed.

    Returns
    -------
    dict with keys:
        "control_round_trip_ms"  — cmd_send → cmd_recv (includes image transfer)
        "step_count"             — number of instrumented steps
    """
    from testbed.latency_module.analysis.parse_trace import filter_events

    if df_trace.empty:
        return {}

    result: dict = {}

    # Control round-trip (pre-computed in probe)
    recvs = filter_events(df_trace, "cmd_recv")
    if not recvs.empty and "round_trip_ms" in recvs.columns:
        result["control_round_trip_ms"] = latency_stats(recvs["round_trip_ms"])
        result["step_count"] = int(len(recvs))

    return result


# ── Convenience: compute everything from a trace file ────────────────────────

def metrics_from_trace(trace_path: str) -> dict:
    """
    Load a trace.jsonl and compute all available metrics.

    Returns a flat summary dict suitable for JSON export.
    """
    from testbed.latency_module.analysis.parse_trace import load_trace, pivot_step_latency

    df = load_trace(trace_path)
    if df.empty:
        return {"error": "empty_trace"}

    chain_metrics = compute_chain_metrics(df)
    steps = pivot_step_latency(df)
    step_metrics = compute_step_metrics(steps) if not steps.empty else {}

    return {**chain_metrics, **step_metrics, "trace_path": str(trace_path)}
