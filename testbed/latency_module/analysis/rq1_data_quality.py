"""
rq1_data_quality.py — Compute and plot action quality metrics from recorded
HDF5 demos, for the RQ1 control experiment.

Metrics
-------
- step_interval_ms   step-ack RTT proxy (from timestamps/step_ns)
- action_jerk        rate of change of action magnitude per step  (畸变指标 1)
- reversal_rate      fraction of steps where action direction reverses (畸变指标 2)

Usage (CLI)
-----------
    python -m testbed.latency_module.analysis.rq1_data_quality \
        --datasets data/rq1/c0_baseline:C0_0ms \
                   data/rq1/c100ms_delay:C1_100ms \
                   data/rq1/c200ms_delay:C2_200ms \
        --out outputs/rq1/data_quality

Usage (programmatic)
--------------------
    from testbed.latency_module.analysis.rq1_data_quality import compare_conditions
    compare_conditions(
        conditions=[
            ("data/rq1/c0_baseline",   "C0_0ms"),
            ("data/rq1/c100ms_delay",  "C1_100ms"),
            ("data/rq1/c200ms_delay",  "C2_200ms"),
        ],
        out_dir="outputs/rq1/data_quality",
    )
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import numpy as np

warnings.filterwarnings("ignore", category=UserWarning)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

_STYLE = "seaborn-v0_8-whitegrid"
_DPI   = 150


# ── Per-episode metric extraction ────────────────────────────────────────────

def read_dataset_resolution(dataset_dir: str | Path) -> str:
    """
    Read the actual image resolution stored in the first HDF5 episode.
    Returns a string like '720x480' or '240x160', or 'unknown'.
    """
    import h5py, os
    d = Path(dataset_dir)
    eps = sorted([f for f in os.listdir(d) if f.endswith(".hdf5")],
                 key=lambda x: int(x.split("_")[1].split(".")[0]))
    if not eps:
        return "unknown"
    with h5py.File(d / eps[0], "r") as f:
        if "observations/images/fpv" in f:
            shape = f["observations/images/fpv"].shape  # (T, H, W, 3)
            if len(shape) == 4:
                return f"{shape[2]}x{shape[1]}"
        # Fall back to metadata attrs
        w = f["metadata"].attrs.get("camera_width", 0)
        h = f["metadata"].attrs.get("camera_height", 0)
        if w and h:
            return f"{w}x{h}"
    return "unknown"


def episode_metrics(hdf5_path: str | Path) -> dict[str, Any]:
    """
    Extract data quality metrics from one HDF5 episode.

    Returns
    -------
    dict with keys:
        step_intervals_ms   np.ndarray  (N-1,)
        action_jerk         np.ndarray  (N-2,)  ‖Δa[t] - Δa[t-1]‖ / dt_sim²  (fixed sim dt)
        reversal_rate       float       fraction of steps with direction reversal
        n_steps             int
        success             int         1 if episode succeeded, 0 otherwise
        wall_duration_s     float       wall-clock duration of episode
        est_sim_time_s      float       estimated sim time (wall time for realtime, n_steps*dt for sync)
    """
    import h5py
    with h5py.File(Path(hdf5_path), "r") as f:
        action   = f["action"][:]             # (T, 4) float32
        step_ns  = f["timestamps/step_ns"][:] # (T,)   int64
        control_hz = float(f["metadata"].attrs.get("control_hz", 50))
        dt_sim = 1.0 / control_hz
        success  = int(f["metadata"].attrs.get("success", -1))

    step_ns = step_ns.astype(np.float64)

    # step interval in ms
    step_intervals_ms = np.diff(step_ns) / 1e6

    # Wall-clock duration of episode
    wall_duration_s = (step_ns[-1] - step_ns[0]) / 1e9 if len(step_ns) > 1 else 0.0

    # Estimated sim time: if mean step interval >> dt_sim, we're in Realtime
    # mode and wall time ≈ sim time. Otherwise sync mode: sim_time = n_steps * dt_sim.
    mean_interval_s = float(np.mean(step_intervals_ms)) / 1000.0 if len(step_intervals_ms) > 0 else dt_sim
    if mean_interval_s > dt_sim * 1.5:
        est_sim_time_s = wall_duration_s
    else:
        est_sim_time_s = len(action) * dt_sim

    # Jerk uses FIXED sim dt so it's comparable across conditions.
    # jerk = ||Δ²action|| / dt_sim² — measures how aggressively the operator
    # changes their input per unit of simulation time, regardless of sampling rate.
    delta_a = np.diff(action, axis=0)            # (T-1, 4)
    if len(delta_a) > 1:
        dt_sim2 = dt_sim ** 2
        jerk_vec = np.diff(delta_a, axis=0) / dt_sim2
        action_jerk = np.linalg.norm(jerk_vec, axis=1)  # (T-2,)
    else:
        action_jerk = np.array([])

    # Reversal rate: for each DOF, count sign changes in delta_a
    sign_changes = np.diff(np.sign(delta_a), axis=0)  # (T-2, 4)
    any_reversal = (np.abs(sign_changes) > 0).any(axis=1)  # (T-2,)
    reversal_rate = float(any_reversal.mean()) if len(any_reversal) > 0 else 0.0

    return {
        "step_intervals_ms": step_intervals_ms,
        "action_jerk":       action_jerk,
        "reversal_rate":     reversal_rate,
        "n_steps":           len(action),
        "success":           success,
        "wall_duration_s":   wall_duration_s,
        "est_sim_time_s":    est_sim_time_s,
    }


def dataset_metrics(dataset_dir: str | Path) -> dict[str, Any]:
    """
    Aggregate metrics across all episodes in a dataset directory.

    Returns
    -------
    dict with keys:
        all_intervals_ms   np.ndarray  all step intervals
        all_jerk           np.ndarray  all jerk values
        reversal_rates     np.ndarray  per-episode reversal rate
        n_episodes         int
        n_steps_total      int
    """
    import os
    d = Path(dataset_dir)
    eps = sorted([f for f in os.listdir(d) if f.endswith(".hdf5")],
                 key=lambda x: int(x.split("_")[1].split(".")[0]))

    all_intervals: list[np.ndarray] = []
    all_jerk: list[np.ndarray] = []
    reversal_rates: list[float] = []
    successes: list[int] = []
    success_ep_lengths: list[int] = []
    ep_step_counts: list[int] = []
    ep_sim_times: list[float] = []
    success_sim_times: list[float] = []
    n_steps_total = 0

    for ep in eps:
        m = episode_metrics(d / ep)
        if len(m["step_intervals_ms"]) > 0:
            all_intervals.append(m["step_intervals_ms"])
        if len(m["action_jerk"]) > 0:
            all_jerk.append(m["action_jerk"])
        reversal_rates.append(m["reversal_rate"])
        n_steps_total += m["n_steps"]
        successes.append(m["success"])
        ep_step_counts.append(m["n_steps"])
        ep_sim_times.append(m["est_sim_time_s"])
        if m["success"] == 1:
            success_ep_lengths.append(m["n_steps"])
            success_sim_times.append(m["est_sim_time_s"])

    return {
        "all_intervals_ms":   np.concatenate(all_intervals) if all_intervals else np.array([]),
        "all_jerk":           np.concatenate(all_jerk) if all_jerk else np.array([]),
        "reversal_rates":     np.array(reversal_rates),
        "successes":          np.array(successes),
        "success_ep_lengths": np.array(success_ep_lengths),
        "ep_step_counts":     np.array(ep_step_counts),
        "ep_sim_times":       np.array(ep_sim_times),
        "success_sim_times":  np.array(success_sim_times),
        "n_episodes":         len(eps),
        "n_steps_total":      n_steps_total,
    }


def _stats(arr: np.ndarray) -> dict:
    if len(arr) == 0:
        return {"mean": float("nan"), "median": float("nan"), "std": float("nan"),
                "p95": float("nan"), "p99": float("nan")}
    return {
        "mean":   float(arr.mean()),
        "median": float(np.median(arr)),
        "std":    float(arr.std()),
        "p95":    float(np.percentile(arr, 95)),
        "p99":    float(np.percentile(arr, 99)),
    }


# ── Multi-condition comparison ────────────────────────────────────────────────

def compare_conditions(
    conditions: list[tuple[str, str]],
    out_dir: str | Path,
) -> dict:
    """
    Compute and plot data quality metrics for multiple conditions.

    Parameters
    ----------
    conditions  List of (dataset_dir, label) tuples.
    out_dir     Output directory for plots and summary JSON.

    Returns
    -------
    dict of {label: metrics_dict}
    """
    import json
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_metrics: dict[str, Any] = {}
    labels = []
    interval_arrays:    list[np.ndarray] = []
    jerk_arrays:        list[np.ndarray] = []
    reversal_means:     list[float]      = []
    success_rates:      list[float]      = []
    ep_length_arrays:   list[np.ndarray] = []
    samples_per_ep:     list[float]      = []
    sim_time_means:     list[float]      = []

    for dataset_dir, label in conditions:
        p = Path(dataset_dir)
        if not p.exists():
            print(f"  [rq1_dq] WARNING: {dataset_dir} not found, skipping.")
            continue
        actual_res = read_dataset_resolution(dataset_dir)
        print(f"  [rq1_dq] Processing {label} ({dataset_dir})  actual_resolution={actual_res} ...")
        m = dataset_metrics(dataset_dir)

        n_ep = m["n_episodes"]
        suc  = m["successes"]
        sr   = float(suc[suc >= 0].mean()) if len(suc[suc >= 0]) > 0 else float("nan")
        mean_samples = float(m["ep_step_counts"].mean()) if len(m["ep_step_counts"]) > 0 else float("nan")
        mean_sim_time = float(m["ep_sim_times"].mean()) if len(m["ep_sim_times"]) > 0 else float("nan")

        stats = {
            "label":              label,
            "actual_resolution":  actual_res,
            "n_episodes":         n_ep,
            "n_steps":            m["n_steps_total"],
            "step_interval_ms": _stats(m["all_intervals_ms"]),
            "action_jerk":    _stats(m["all_jerk"]),
            "reversal_rate":  {
                "mean": float(m["reversal_rates"].mean()) if len(m["reversal_rates"]) else float("nan"),
                "std":  float(m["reversal_rates"].std())  if len(m["reversal_rates"]) else float("nan"),
            },
            "success_rate":     sr,
            "episode_length":   _stats(m["success_ep_lengths"]),
            "samples_per_episode": mean_samples,
            "est_sim_time_s": {
                "mean": mean_sim_time,
                "success_only": _stats(m["success_sim_times"]),
            },
        }
        all_metrics[label] = stats
        labels.append(label)
        interval_arrays.append(m["all_intervals_ms"])
        jerk_arrays.append(m["all_jerk"])
        reversal_means.append(stats["reversal_rate"]["mean"])
        success_rates.append(sr)
        ep_length_arrays.append(m["success_ep_lengths"])
        samples_per_ep.append(mean_samples)
        sim_time_means.append(mean_sim_time)

    if not labels:
        print("  [rq1_dq] No valid conditions found.")
        return {}

    # ── Save JSON summary ─────────────────────────────────────────────────
    summary_path = out_dir / "data_quality_summary.json"
    summary_path.write_text(
        json.dumps({"conditions": all_metrics}, indent=2, ensure_ascii=False)
    )
    print(f"  [rq1_dq] Summary → {summary_path}")

    _plot_interval_boxplot(labels, interval_arrays, out_dir)
    _plot_jerk_boxplot(labels, jerk_arrays, out_dir)
    _plot_reversal_rate(labels, reversal_means, out_dir)
    _plot_interval_distributions(labels, interval_arrays, out_dir)
    _plot_success_and_length(labels, success_rates, ep_length_arrays, out_dir)
    _plot_proof_summary(labels, interval_arrays, jerk_arrays, reversal_means,
                        success_rates, ep_length_arrays, out_dir,
                        samples_per_ep=samples_per_ep,
                        sim_time_means=sim_time_means)

    return all_metrics


# ── Plot helpers ──────────────────────────────────────────────────────────────

def _savefig(fig, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=_DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  [rq1_dq] saved → {path}")


def _plot_interval_boxplot(labels, arrays, out_dir):
    with plt.style.context(_STYLE):
        fig, ax = plt.subplots(figsize=(max(6, len(labels)*2), 5))
        data = [a for a in arrays if len(a) > 0]
        valid_labels = [l for l, a in zip(labels, arrays) if len(a) > 0]
        bp = ax.boxplot(data, labels=valid_labels, patch_artist=True, notch=False,
                        medianprops=dict(color="#C44E52", linewidth=2))
        import matplotlib.cm as cm
        colors = cm.Blues(np.linspace(0.4, 0.8, len(data)))
        for patch, c in zip(bp["boxes"], colors):
            patch.set_facecolor(c)
        ax.axhline(20, color="#55A868", linestyle="--", linewidth=1.2,
                   label="target 20ms (50Hz)")
        ax.set_ylabel("Step Interval (ms)", fontsize=11)
        ax.set_title("Step-Ack RTT Distribution by Condition\n(Step interval proxy — lower is better)", fontsize=11)
        ax.legend(fontsize=9)
        _savefig(fig, out_dir / "interval_boxplot.png")


def _plot_jerk_boxplot(labels, arrays, out_dir):
    with plt.style.context(_STYLE):
        fig, ax = plt.subplots(figsize=(max(6, len(labels)*2), 5))
        data = [a for a in arrays if len(a) > 0]
        valid_labels = [l for l, a in zip(labels, arrays) if len(a) > 0]
        bp = ax.boxplot(data, labels=valid_labels, patch_artist=True, notch=False,
                        medianprops=dict(color="#C44E52", linewidth=2),
                        showfliers=False)
        import matplotlib.cm as cm
        colors = cm.Oranges(np.linspace(0.4, 0.8, len(data)))
        for patch, c in zip(bp["boxes"], colors):
            patch.set_facecolor(c)
        ax.set_ylabel("Action Jerk (rad/s³ or unit/s³)", fontsize=11)
        ax.set_title("Action Jerk by Condition\n(Higher jerk = more operator over-compensation)", fontsize=11)
        _savefig(fig, out_dir / "action_jerk_boxplot.png")


def _plot_reversal_rate(labels, reversal_means, out_dir):
    with plt.style.context(_STYLE):
        fig, ax = plt.subplots(figsize=(max(6, len(labels)*2), 4))
        x = np.arange(len(labels))
        bars = ax.bar(x, reversal_means, color="#4C72B0", alpha=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.set_ylabel("Reversal Rate (fraction of steps)", fontsize=11)
        ax.set_title("Action Direction Reversal Rate by Condition\n(Higher = more 'move-and-wait' behavior)", fontsize=11)
        for bar, v in zip(bars, reversal_means):
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.002,
                    f"{v:.3f}", ha="center", va="bottom", fontsize=9)
        _savefig(fig, out_dir / "reversal_rate.png")


def _plot_interval_distributions(labels, arrays, out_dir):
    with plt.style.context(_STYLE):
        fig, ax = plt.subplots(figsize=(8, 4))
        colors = ["#4C72B0", "#C44E52", "#55A868", "#8172B2"]
        for label, arr, color in zip(labels, arrays, colors):
            if len(arr) == 0:
                continue
            arr_clipped = np.clip(arr, 0, 200)
            ax.hist(arr_clipped, bins=60, alpha=0.5, color=color,
                    label=f"{label} (mean={arr.mean():.1f}ms)",
                    density=True, edgecolor="none")
        ax.axvline(20, color="black", linestyle="--", linewidth=1, label="target 20ms")
        ax.set_xlabel("Step Interval (ms)", fontsize=11)
        ax.set_ylabel("Density", fontsize=11)
        ax.set_title("Step Interval Distribution — All Conditions", fontsize=11)
        ax.legend(fontsize=8)
        _savefig(fig, out_dir / "interval_distributions.png")


def _plot_success_and_length(labels, success_rates, ep_length_arrays, out_dir):
    with plt.style.context(_STYLE):
        fig, axes = plt.subplots(1, 2, figsize=(max(8, len(labels)*2.5), 4))
        colors = ["#4C72B0", "#C44E52", "#55A868", "#8172B2"][:len(labels)]
        x = np.arange(len(labels))

        # success rate
        ax = axes[0]
        bars = ax.bar(x, success_rates, color=colors, alpha=0.85, width=0.5)
        ax.set_xticks(x); ax.set_xticklabels(labels)
        ax.set_ylim(0, 1.15)
        ax.set_ylabel("Success Rate", fontsize=11)
        ax.set_title("Task Success Rate by Condition\n(Higher latency → harder to succeed)", fontsize=10)
        for bar, v in zip(bars, success_rates):
            if not np.isnan(v):
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                        f"{v*100:.0f}%", ha="center", va="bottom", fontsize=10, fontweight="bold")

        # episode length (steps for successful episodes)
        ax = axes[1]
        valid = [(l, arr) for l, arr in zip(labels, ep_length_arrays) if len(arr) > 0]
        if valid:
            bp = ax.boxplot([arr for _, arr in valid],
                            labels=[l for l, _ in valid],
                            patch_artist=True, notch=False,
                            medianprops=dict(color="#C44E52", linewidth=2))
            for patch, c in zip(bp["boxes"], colors):
                patch.set_facecolor(c)
                patch.set_alpha(0.7)
        ax.set_ylabel("Steps to Success", fontsize=11)
        ax.set_title("Episode Length (Successful Only)\n(More steps = slower / more corrections)", fontsize=10)

        plt.tight_layout()
        _savefig(fig, out_dir / "success_and_length.png")


def _plot_proof_summary(labels, interval_arrays, jerk_arrays, reversal_means,
                        success_rates, ep_length_arrays, out_dir,
                        samples_per_ep=None, sim_time_means=None):
    """Single combined 2×3 figure suitable for inclusion in the paper motivation section."""
    colors = ["#4C72B0", "#C44E52", "#55A868", "#8172B2", "#CCB974", "#64B5CD"][:len(labels)]
    x = np.arange(len(labels))

    with plt.style.context(_STYLE):
        fig, axes = plt.subplots(2, 3, figsize=(16, 8))
        fig.suptitle("Effect of Injected Latency on Teleoperation Data Quality",
                     fontsize=13, fontweight="bold", y=1.01)

        # (0,0) RTT distribution
        ax = axes[0, 0]
        for label, arr, color in zip(labels, interval_arrays, colors):
            if len(arr) == 0:
                continue
            ax.hist(np.clip(arr, 0, 500), bins=60, alpha=0.55, color=color,
                    label=f"{label} (μ={arr.mean():.0f}ms)", density=True, edgecolor="none")
        ax.axvline(20, color="black", linestyle="--", lw=1, label="target 20ms")
        ax.set_xlabel("Step Interval (ms)"); ax.set_ylabel("Density")
        ax.set_title("Step-Ack RTT Distribution")
        ax.legend(fontsize=7)

        # (0,1) Action jerk (now with fixed sim-dt normalization)
        ax = axes[0, 1]
        data_jerk = [a for a in jerk_arrays if len(a) > 0]
        vlabels   = [l for l, a in zip(labels, jerk_arrays) if len(a) > 0]
        if data_jerk:
            bp = ax.boxplot(data_jerk, labels=vlabels, patch_artist=True,
                            showfliers=False, medianprops=dict(color="black", linewidth=1.8))
            for patch, c in zip(bp["boxes"], colors):
                patch.set_facecolor(c); patch.set_alpha(0.7)
        ax.set_ylabel("Action Jerk (norm / sim_dt²)")
        ax.set_title("Action Jerk\n(normalized by sim dt)")

        # (0,2) Samples per episode (information density)
        ax = axes[0, 2]
        if samples_per_ep is not None:
            bars = ax.bar(x, samples_per_ep, color=colors, alpha=0.85, width=0.5)
            ax.set_xticks(x); ax.set_xticklabels(labels)
            ax.set_ylabel("Samples / Episode")
            ax.set_title("Information Density\n(samples per episode)")
            for bar, v in zip(bars, samples_per_ep):
                if not np.isnan(v):
                    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 5,
                            f"{v:.0f}", ha="center", va="bottom", fontsize=9)

        # (1,0) Reversal rate
        ax = axes[1, 0]
        bars = ax.bar(x, reversal_means, color=colors, alpha=0.85, width=0.5)
        ax.set_xticks(x); ax.set_xticklabels(labels)
        ax.set_ylabel("Reversal Rate")
        ax.set_title("Action Reversal Rate\n(back-and-forth corrections)")
        for bar, v in zip(bars, reversal_means):
            if not np.isnan(v):
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.003,
                        f"{v:.3f}", ha="center", va="bottom", fontsize=9)

        # (1,1) Success rate
        ax = axes[1, 1]
        bars = ax.bar(x, success_rates, color=colors, alpha=0.85, width=0.5)
        ax.set_xticks(x); ax.set_xticklabels(labels)
        ax.set_ylim(0, 1.15)
        ax.set_ylabel("Success Rate")
        ax.set_title("Task Success Rate\n(task-level degradation)")
        for bar, v in zip(bars, success_rates):
            if not np.isnan(v):
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                        f"{v*100:.0f}%", ha="center", va="bottom",
                        fontsize=10, fontweight="bold")

        # (1,2) Estimated sim time per episode
        ax = axes[1, 2]
        if sim_time_means is not None:
            bars = ax.bar(x, sim_time_means, color=colors, alpha=0.85, width=0.5)
            ax.set_xticks(x); ax.set_xticklabels(labels)
            ax.set_ylabel("Sim Time (s)")
            ax.set_title("Avg Episode Duration\n(estimated sim time)")
            for bar, v in zip(bars, sim_time_means):
                if not np.isnan(v):
                    ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.2,
                            f"{v:.1f}s", ha="center", va="bottom", fontsize=9)

        plt.tight_layout()
        _savefig(fig, out_dir / "proof_summary.png")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(
        prog="rq1-data-quality",
        description="Compute RQ1 data quality metrics from HDF5 datasets.",
    )
    parser.add_argument(
        "--datasets", "-d", nargs="+", required=True,
        metavar="DIR:LABEL",
        help="One or more dataset_dir:label pairs, e.g. data/rq1/c0:C0_0ms",
    )
    parser.add_argument("--out", "-o", type=Path, default=Path("outputs/rq1/data_quality"))
    args = parser.parse_args()

    conditions = []
    for item in args.datasets:
        if ":" in item:
            d, label = item.split(":", 1)
        else:
            d, label = item, Path(item).name
        conditions.append((d, label))

    compare_conditions(conditions, args.out)


if __name__ == "__main__":
    main()
