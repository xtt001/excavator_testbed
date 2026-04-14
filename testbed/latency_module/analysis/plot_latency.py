"""
plot_latency.py — Auto-generate latency plots from a trace DataFrame.

All functions accept a DataFrame produced by parse_trace.load_trace() or
parse_trace.pivot_step_latency() and save PNG files to a given output dir.

Available plots
---------------
1. plot_e2e_distribution(df_steps, out_dir)
   Histogram + KDE of end-to-end round-trip latency.

2. plot_latency_timeseries(df_steps, out_dir)
   Time-series of round-trip latency per step (with p95 annotation).

3. plot_config_comparison(df_steps, out_dir, group_col)
   Box-plot comparison across different configurations (e.g. delay_inject_ms).

4. plot_payload_size(df_steps, out_dir)
   Image payload bytes per step (proxy for video bitrate).

5. plot_all(df_steps, out_dir)
   Convenience: generate all available plots.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd

# Suppress matplotlib warnings in headless environments
warnings.filterwarnings("ignore", category=UserWarning)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker


_FIGURE_DPI = 150
_STYLE = "seaborn-v0_8-whitegrid"


def _savefig(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=_FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  [latency_plot] saved → {path}")


# ── 1. E2E Latency Distribution ───────────────────────────────────────────────

def plot_e2e_distribution(
    df_steps: pd.DataFrame,
    out_dir: str | Path,
    filename: str = "e2e_distribution.png",
) -> None:
    """Histogram of round-trip latency with percentile annotations."""
    if df_steps.empty or "round_trip_ms" not in df_steps.columns:
        return

    series = df_steps["round_trip_ms"].dropna()
    if series.empty:
        return

    with plt.style.context(_STYLE):
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.hist(series, bins=50, color="#4C72B0", edgecolor="white", linewidth=0.3,
                label="round-trip latency")

        for pct, label, color in [
            (50, "p50", "#55A868"),
            (95, "p95", "#C44E52"),
            (99, "p99", "#8172B2"),
        ]:
            val = np.percentile(series, pct)
            ax.axvline(val, color=color, linestyle="--", linewidth=1.2,
                       label=f"{label}={val:.1f} ms")

        ax.set_xlabel("Round-trip Latency (ms)", fontsize=11)
        ax.set_ylabel("Count", fontsize=11)
        ax.set_title("End-to-End Step Round-Trip Latency Distribution", fontsize=12)
        ax.legend(fontsize=9)
        _savefig(fig, Path(out_dir) / filename)


# ── 2. Latency Time-Series ────────────────────────────────────────────────────

def plot_latency_timeseries(
    df_steps: pd.DataFrame,
    out_dir: str | Path,
    filename: str = "latency_timeseries.png",
) -> None:
    """Time-series of round-trip latency vs. step index."""
    if df_steps.empty or "round_trip_ms" not in df_steps.columns:
        return

    series = df_steps["round_trip_ms"].dropna()
    if series.empty:
        return

    with plt.style.context(_STYLE):
        fig, ax = plt.subplots(figsize=(12, 4))

        x = np.arange(len(series))
        ax.plot(x, series.values, color="#4C72B0", linewidth=0.7, alpha=0.8,
                label="round-trip")

        # Rolling p95 window
        window = max(20, len(series) // 50)
        rolling_p95 = series.rolling(window, min_periods=1).quantile(0.95)
        ax.plot(x, rolling_p95.values, color="#C44E52", linewidth=1.2,
                linestyle="--", label=f"rolling p95 (w={window})")

        p95_global = float(np.percentile(series, 95))
        ax.axhline(p95_global, color="#C44E52", linewidth=0.6, linestyle=":",
                   alpha=0.5)

        ax.set_xlabel("Step Index", fontsize=11)
        ax.set_ylabel("Latency (ms)", fontsize=11)
        ax.set_title("Round-Trip Latency per Step", fontsize=12)
        ax.legend(fontsize=9)
        _savefig(fig, Path(out_dir) / filename)


# ── 3. Config Comparison ──────────────────────────────────────────────────────

def plot_config_comparison(
    df_steps: pd.DataFrame,
    out_dir: str | Path,
    group_col: str = "delay_inject_ms",
    filename: str | None = None,
) -> None:
    """Box-plot comparison of round-trip latency across configurations."""
    if df_steps.empty or "round_trip_ms" not in df_steps.columns:
        return
    if group_col not in df_steps.columns:
        return
    if df_steps[group_col].nunique() <= 1:
        return

    groups = df_steps.groupby(group_col)["round_trip_ms"].apply(list)
    labels = [str(k) for k in groups.index]
    data   = [v for v in groups.values]

    with plt.style.context(_STYLE):
        fig, ax = plt.subplots(figsize=(max(6, len(labels) * 1.5), 5))
        bp = ax.boxplot(data, labels=labels, patch_artist=True, notch=False,
                        medianprops=dict(color="#C44E52", linewidth=1.5))
        colors = plt.cm.Blues(np.linspace(0.4, 0.8, len(data)))  # type: ignore[attr-defined]
        for patch, color in zip(bp["boxes"], colors):
            patch.set_facecolor(color)

        ax.set_xlabel(group_col.replace("_", " ").title(), fontsize=11)
        ax.set_ylabel("Round-trip Latency (ms)", fontsize=11)
        ax.set_title(f"Latency by {group_col.replace('_', ' ').title()}", fontsize=12)
        ax.yaxis.set_minor_locator(mticker.AutoMinorLocator())

        fn = filename or f"comparison_{group_col}.png"
        _savefig(fig, Path(out_dir) / fn)


# ── 4. Payload Size ───────────────────────────────────────────────────────────

def plot_payload_size(
    df_steps: pd.DataFrame,
    out_dir: str | Path,
    filename: str = "payload_bytes.png",
) -> None:
    """Image payload size per step (raw bytes, proxy for frame size)."""
    if df_steps.empty or "payload_bytes" not in df_steps.columns:
        return

    series = df_steps["payload_bytes"].dropna()
    if series.empty or (series == 0).all():
        return

    series_kb = series / 1024

    with plt.style.context(_STYLE):
        fig, ax = plt.subplots(figsize=(12, 3))
        ax.fill_between(np.arange(len(series_kb)), series_kb.values,
                        color="#55A868", alpha=0.7)
        ax.plot(np.arange(len(series_kb)), series_kb.values,
                color="#55A868", linewidth=0.5)
        ax.axhline(float(series_kb.mean()), color="#C44E52", linewidth=1.0,
                   linestyle="--", label=f"mean={series_kb.mean():.1f} KB")
        ax.set_xlabel("Step Index", fontsize=11)
        ax.set_ylabel("Payload (KB)", fontsize=11)
        ax.set_title("Image Payload Size per Step", fontsize=12)
        ax.legend(fontsize=9)
        _savefig(fig, Path(out_dir) / filename)


# ── 5. Stacked segment placeholder ───────────────────────────────────────────
# (Phase 2: will be enabled once per-segment timing is available via
#  hardware-level G2G measurements or Unity-side decode timestamps)

def plot_segment_breakdown(
    df_steps: pd.DataFrame,
    out_dir: str | Path,
    filename: str = "segment_breakdown.png",
) -> None:
    """
    Stacked-bar latency segment breakdown.

    Currently only shows the available round_trip_ms as a single bar.
    Will be extended in Phase 2 when encode / network / decode segments
    are measured separately.
    """
    if df_steps.empty or "round_trip_ms" not in df_steps.columns:
        return

    stats = df_steps["round_trip_ms"].describe()

    with plt.style.context(_STYLE):
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.bar(["round_trip"], [stats["mean"]], color="#4C72B0",
               yerr=[stats["std"]], capsize=4, label="mean ± std")
        ax.set_ylabel("Latency (ms)", fontsize=11)
        ax.set_title("Latency Segment Breakdown (Phase 1: round-trip only)", fontsize=11)
        ax.legend(fontsize=9)
        ax.text(0.98, 0.95,
                f"p95={np.percentile(df_steps['round_trip_ms'].dropna(), 95):.1f} ms",
                transform=ax.transAxes, ha="right", va="top", fontsize=9,
                color="#C44E52")
        _savefig(fig, Path(out_dir) / filename)


# ── 6. Generate all plots ─────────────────────────────────────────────────────

def plot_all(
    df_steps: pd.DataFrame,
    out_dir: str | Path,
    group_col: str = "delay_inject_ms",
) -> None:
    """Generate all standard latency plots into out_dir/plots/."""
    plots_dir = Path(out_dir) / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    plot_e2e_distribution(df_steps, plots_dir)
    plot_latency_timeseries(df_steps, plots_dir)
    plot_config_comparison(df_steps, plots_dir, group_col=group_col)
    plot_payload_size(df_steps, plots_dir)
    plot_segment_breakdown(df_steps, plots_dir)

    print(f"  [latency_plot] All plots saved to {plots_dir}")
