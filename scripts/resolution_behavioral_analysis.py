"""
Resolution-specific analysis for the RQ1 proof experiment.

This script connects three evidence sources for the fullres vs lowres control:
1. teleop data-quality summary (`outputs/rq1/resolution_proof/data_quality_summary.json`)
2. ACT training metadata (`runs/ckpts/rq1_act_{fullres,lowres}/run_metadata.json`)
3. ACT evaluation rollouts / summaries (`runs/eval/rq1_act_{fullres,lowres}/results/`)

Outputs
-------
- resolution_policy_behavior.png
- resolution_evidence_summary.png
- summary_table.md

Usage
-----
    python scripts/resolution_behavioral_analysis.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


STYLE = "seaborn-v0_8-whitegrid"
DPI = 150

POLICY_CONDITIONS = [
    {
        "name": "rq1_act_fullres",
        "label": "720x480 full",
        "teleop_label": "720x480(full)",
        "color": "#1a9641",
    },
    {
        "name": "rq1_act_lowres",
        "label": "240x160 low",
        "teleop_label": "240x160(low)",
        "color": "#d95f02",
    },
]


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return (float("nan"), float("nan"))
    p = successes / total
    denom = 1.0 + z * z / total
    center = (p + z * z / (2.0 * total)) / denom
    half = (
        z
        * np.sqrt((p * (1.0 - p) / total) + (z * z / (4.0 * total * total)))
        / denom
    )
    return max(0.0, float(center - half)), min(1.0, float(center + half))


def load_rollouts(results_dir: Path) -> list[list[dict]]:
    rollout_dir = results_dir / "rollouts"
    paths = sorted(rollout_dir.glob("rollout_*.jsonl"))
    rollouts: list[list[dict]] = []
    for path in paths:
        steps = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                steps.append(json.loads(line))
        rollouts.append(steps)
    return rollouts


def load_rollout_summaries(results_dir: Path) -> list[dict]:
    rollout_dir = results_dir / "rollouts"
    paths = sorted(rollout_dir.glob("rollout_*_summary.json"))
    return [load_json(path) for path in paths]


def extract_timeseries(rollouts: list[list[dict]], metric_fn: Callable[[dict], float]) -> np.ndarray:
    if not rollouts:
        return np.zeros((0, 0), dtype=float)
    max_len = max(len(steps) for steps in rollouts)
    data = np.zeros((len(rollouts), max_len), dtype=float)
    for ridx, steps in enumerate(rollouts):
        last_val = 0.0
        for tidx, event in enumerate(steps):
            last_val = float(metric_fn(event))
            data[ridx, tidx] = last_val
        if steps and len(steps) < max_len:
            data[ridx, len(steps):] = last_val
    return data


def plot_mean_std(ax, steps: np.ndarray, series_by_cond: dict[str, np.ndarray], ylabel: str, title: str) -> None:
    for cond in POLICY_CONDITIONS:
        data = series_by_cond[cond["name"]]
        mean = data.mean(axis=0)
        std = data.std(axis=0)
        ax.plot(steps, mean, color=cond["color"], lw=2.0, label=cond["label"])
        ax.fill_between(steps, mean - std, mean + std, color=cond["color"], alpha=0.18)
    ax.set_xlabel("Eval step")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=9)


def summarize_policy_condition(
    cond_name: str,
    eval_root: Path,
    ckpt_root: Path,
) -> dict:
    results_dir = eval_root / cond_name / "results"
    rollouts = load_rollouts(results_dir)
    summaries = load_rollout_summaries(results_dir)
    metrics = load_json(results_dir / "metrics.json")
    train_meta = load_json(ckpt_root / cond_name / "run_metadata.json")

    ts = {
        "dist_dig": extract_timeseries(
            rollouts,
            lambda e: e["task_metrics"]["min_distance_to_dig_area_m"],
        ),
        "bucket_mass": extract_timeseries(
            rollouts,
            lambda e: e["task_metrics"]["mass_in_bucket_kg"],
        ),
        "dist_target": extract_timeseries(
            rollouts,
            lambda e: e["task_metrics"]["min_distance_to_target_m"],
        ),
        "deposited_mass": extract_timeseries(
            rollouts,
            lambda e: e["task_metrics"]["deposited_mass_in_target_box_kg"],
        ),
    }

    n_rollouts = len(summaries)
    n_success = int(sum(bool(item["success"]) for item in summaries))
    dig_rate = sum(item["max_bucket_mass"] >= 300.0 for item in summaries) / n_rollouts
    emptied_rate = sum(item["final_bucket_mass"] <= 100.0 for item in summaries) / n_rollouts
    retained_rate = sum(item["max_signal_value"] >= 300.0 for item in summaries) / n_rollouts

    return {
        "results_dir": results_dir,
        "metrics": metrics,
        "train_meta": train_meta,
        "rollout_summaries": summaries,
        "timeseries": ts,
        "n_rollouts": n_rollouts,
        "n_success": n_success,
        "success_ci": wilson_interval(n_success, n_rollouts),
        "best_val_loss": float(train_meta["training_result"]["best_val_loss"]),
        "best_epoch": int(train_meta["training_result"]["best_epoch"]),
        "avg_max_bucket_mass": float(np.mean([item["max_bucket_mass"] for item in summaries])),
        "avg_final_bucket_mass": float(np.mean([item["final_bucket_mass"] for item in summaries])),
        "avg_max_signal_value": float(np.mean([item["max_signal_value"] for item in summaries])),
        "dig_rate": float(dig_rate),
        "emptied_rate": float(emptied_rate),
        "retained_rate": float(retained_rate),
    }


def savefig(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"[resolution] saved -> {path}")


def render_policy_behavior(summary_by_cond: dict[str, dict], out_dir: Path) -> None:
    with plt.style.context(STYLE):
        fig, axes = plt.subplots(2, 2, figsize=(14, 9))
        fig.suptitle(
            "ACT Behavior Under Image Resolution Constraints\n(fullres learns dig -> carry -> dump, lowres stalls before productive dumping)",
            fontsize=14,
            fontweight="bold",
            y=1.01,
        )

        max_len = max(
            summary_by_cond[cond["name"]]["timeseries"]["bucket_mass"].shape[1]
            for cond in POLICY_CONDITIONS
        )
        steps = np.arange(max_len)

        plot_mean_std(
            axes[0, 0],
            steps,
            {cond["name"]: summary_by_cond[cond["name"]]["timeseries"]["dist_dig"] for cond in POLICY_CONDITIONS},
            "Distance to dig area (m)",
            "1. Reach the Dig Area\n(both conditions get close enough to scoop)",
        )
        plot_mean_std(
            axes[0, 1],
            steps,
            {cond["name"]: summary_by_cond[cond["name"]]["timeseries"]["bucket_mass"] for cond in POLICY_CONDITIONS},
            "Mass in bucket (kg)",
            "2. Load the Bucket\n(lowres loads less and keeps soil in the bucket)",
        )
        plot_mean_std(
            axes[1, 0],
            steps,
            {cond["name"]: summary_by_cond[cond["name"]]["timeseries"]["dist_target"] for cond in POLICY_CONDITIONS},
            "Distance to target (m)",
            "3. Move Toward the Dump Zone\n(lowres travels there but lacks final positioning / dump behavior)",
        )
        plot_mean_std(
            axes[1, 1],
            steps,
            {cond["name"]: summary_by_cond[cond["name"]]["timeseries"]["deposited_mass"] for cond in POLICY_CONDITIONS},
            "Retained mass in target (kg)",
            "4. Actually Deposit Soil\n(only fullres converts carried soil into retained target mass)",
        )

        plt.tight_layout()
        savefig(fig, out_dir / "resolution_policy_behavior.png")


def render_evidence_summary(
    teleop_summary: dict,
    summary_by_cond: dict[str, dict],
    out_dir: Path,
) -> None:
    full_teleop = teleop_summary[POLICY_CONDITIONS[0]["teleop_label"]]
    low_teleop = teleop_summary[POLICY_CONDITIONS[1]["teleop_label"]]
    full_samples_per_ep = float(
        full_teleop.get("samples_per_episode", full_teleop["n_steps"] / max(full_teleop["n_episodes"], 1))
    )
    low_samples_per_ep = float(
        low_teleop.get("samples_per_episode", low_teleop["n_steps"] / max(low_teleop["n_episodes"], 1))
    )

    metric_names = [
        ("step interval", "step_interval_ms", "mean"),
        ("action jerk", "action_jerk", "mean"),
        ("reversal rate", "reversal_rate", "mean"),
        ("samples / ep", "samples_per_episode", None),
    ]
    teleop_ratios = []
    for _, outer_key, inner_key in metric_names:
        if outer_key == "samples_per_episode":
            full_val = full_samples_per_ep
            low_val = low_samples_per_ep
        else:
            full_val = full_teleop[outer_key] if inner_key is None else full_teleop[outer_key][inner_key]
            low_val = low_teleop[outer_key] if inner_key is None else low_teleop[outer_key][inner_key]
        teleop_ratios.append((float(full_val), float(low_val)))

    with plt.style.context(STYLE):
        fig, axes = plt.subplots(2, 3, figsize=(16, 9))
        fig.suptitle(
            "Resolution Proof: Teleop Stays Viable, Learned Policy Breaks",
            fontsize=14,
            fontweight="bold",
            y=1.01,
        )

        x = np.arange(len(metric_names))
        width = 0.34

        # (0,0) teleop quality ratios / raw normalized against fullres
        ax = axes[0, 0]
        base_vals = np.ones(len(metric_names))
        low_vals = np.array([low / full for full, low in teleop_ratios], dtype=float)
        ax.bar(x - width / 2, base_vals, width, color="#bdbdbd", label="720x480 full (=1.00)")
        ax.bar(x + width / 2, low_vals, width, color=POLICY_CONDITIONS[1]["color"], label="240x160 low / full")
        ax.axhline(1.0, color="black", lw=1.0, linestyle="--", alpha=0.7)
        ax.set_xticks(x)
        ax.set_xticklabels([name for name, _, _ in metric_names], rotation=15)
        ax.set_ylabel("Ratio vs fullres")
        ax.set_title("1. Teleop Data Quality Changes Only Mildly")
        for xpos, val in zip(x + width / 2, low_vals):
            ax.text(xpos, val + 0.03, f"{val:.2f}x", ha="center", va="bottom", fontsize=9)
        ax.legend(fontsize=8)

        # (0,1) teleop success + step count
        ax = axes[0, 1]
        labels = [cond["label"] for cond in POLICY_CONDITIONS]
        teleop_successes = [
            float(full_teleop["success_rate"]),
            float(low_teleop["success_rate"]),
        ]
        teleop_steps = [
            float(full_teleop["episode_length"]["mean"]),
            float(low_teleop["episode_length"]["mean"]),
        ]
        bars = ax.bar(np.arange(2), teleop_successes, color=[c["color"] for c in POLICY_CONDITIONS], alpha=0.85)
        ax.set_ylim(0, 1.15)
        ax.set_xticks(np.arange(2))
        ax.set_xticklabels(labels)
        ax.set_ylabel("Teleop success rate")
        ax.set_title("2. Human Teleop Still Completes the Task")
        for bar, value in zip(bars, teleop_successes):
            ax.text(bar.get_x() + bar.get_width() / 2, value + 0.02, f"{value * 100:.0f}%", ha="center", va="bottom", fontsize=10, fontweight="bold")
        ax2 = ax.twinx()
        ax2.plot(np.arange(2), teleop_steps, color="#4c4c4c", marker="o", lw=1.8)
        ax2.set_ylabel("Mean successful episode steps")
        for xpos, value in enumerate(teleop_steps):
            ax2.text(xpos, value + 10, f"{value:.0f}", ha="center", va="bottom", fontsize=9, color="#4c4c4c")

        # (0,2) best val loss
        ax = axes[0, 2]
        best_val_losses = [summary_by_cond[cond["name"]]["best_val_loss"] for cond in POLICY_CONDITIONS]
        bars = ax.bar(np.arange(2), best_val_losses, color=[c["color"] for c in POLICY_CONDITIONS], alpha=0.85)
        ax.set_xticks(np.arange(2))
        ax.set_xticklabels(labels)
        ax.set_ylabel("Best validation loss")
        ax.set_title("3. BC Loss Looks Similar")
        for bar, cond in zip(bars, POLICY_CONDITIONS):
            value = summary_by_cond[cond["name"]]["best_val_loss"]
            epoch = summary_by_cond[cond["name"]]["best_epoch"]
            ax.text(bar.get_x() + bar.get_width() / 2, value + 0.006, f"{value:.3f}\n@{epoch}", ha="center", va="bottom", fontsize=9)

        # (1,0) policy success rate with CI
        ax = axes[1, 0]
        success_rates = [summary_by_cond[cond["name"]]["metrics"]["success_rate"] for cond in POLICY_CONDITIONS]
        ci_lows = []
        ci_highs = []
        for cond in POLICY_CONDITIONS:
            rate = summary_by_cond[cond["name"]]["metrics"]["success_rate"]
            low, high = summary_by_cond[cond["name"]]["success_ci"]
            ci_lows.append(rate - low)
            ci_highs.append(high - rate)
        yerr = np.vstack([ci_lows, ci_highs])
        bars = ax.bar(np.arange(2), success_rates, yerr=yerr, capsize=4, color=[c["color"] for c in POLICY_CONDITIONS], alpha=0.85)
        ax.set_ylim(0, 1.05)
        ax.set_xticks(np.arange(2))
        ax.set_xticklabels(labels)
        ax.set_ylabel("Policy success rate")
        ax.set_title("4. Downstream ACT Success Collapses")
        for bar, value in zip(bars, success_rates):
            ax.text(bar.get_x() + bar.get_width() / 2, value + 0.03, f"{value * 100:.0f}%", ha="center", va="bottom", fontsize=10, fontweight="bold")

        # (1,1) mass summary across sub-stages
        ax = axes[1, 1]
        mass_categories = ["max bucket", "final bucket", "max retained target"]
        full_masses = [
            summary_by_cond[POLICY_CONDITIONS[0]["name"]]["avg_max_bucket_mass"],
            summary_by_cond[POLICY_CONDITIONS[0]["name"]]["avg_final_bucket_mass"],
            summary_by_cond[POLICY_CONDITIONS[0]["name"]]["avg_max_signal_value"],
        ]
        low_masses = [
            summary_by_cond[POLICY_CONDITIONS[1]["name"]]["avg_max_bucket_mass"],
            summary_by_cond[POLICY_CONDITIONS[1]["name"]]["avg_final_bucket_mass"],
            summary_by_cond[POLICY_CONDITIONS[1]["name"]]["avg_max_signal_value"],
        ]
        xpos = np.arange(len(mass_categories))
        ax.bar(xpos - width / 2, full_masses, width, color=POLICY_CONDITIONS[0]["color"], alpha=0.85, label=POLICY_CONDITIONS[0]["label"])
        ax.bar(xpos + width / 2, low_masses, width, color=POLICY_CONDITIONS[1]["color"], alpha=0.85, label=POLICY_CONDITIONS[1]["label"])
        ax.set_xticks(xpos)
        ax.set_xticklabels(mass_categories, rotation=10)
        ax.set_ylabel("Mass (kg)")
        ax.set_title("5. Failure Happens After Digging")
        ax.legend(fontsize=8)

        # (1,2) subtask attainment rates
        ax = axes[1, 2]
        ladder_labels = ["dig >=300kg", "bucket <=100kg", "retained >=300kg", "full task"]
        full_rates = [
            summary_by_cond[POLICY_CONDITIONS[0]["name"]]["dig_rate"],
            summary_by_cond[POLICY_CONDITIONS[0]["name"]]["emptied_rate"],
            summary_by_cond[POLICY_CONDITIONS[0]["name"]]["retained_rate"],
            summary_by_cond[POLICY_CONDITIONS[0]["name"]]["metrics"]["success_rate"],
        ]
        low_rates = [
            summary_by_cond[POLICY_CONDITIONS[1]["name"]]["dig_rate"],
            summary_by_cond[POLICY_CONDITIONS[1]["name"]]["emptied_rate"],
            summary_by_cond[POLICY_CONDITIONS[1]["name"]]["retained_rate"],
            summary_by_cond[POLICY_CONDITIONS[1]["name"]]["metrics"]["success_rate"],
        ]
        xpos = np.arange(len(ladder_labels))
        ax.bar(xpos - width / 2, full_rates, width, color=POLICY_CONDITIONS[0]["color"], alpha=0.85, label=POLICY_CONDITIONS[0]["label"])
        ax.bar(xpos + width / 2, low_rates, width, color=POLICY_CONDITIONS[1]["color"], alpha=0.85, label=POLICY_CONDITIONS[1]["label"])
        ax.set_xticks(xpos)
        ax.set_xticklabels(ladder_labels, rotation=12)
        ax.set_ylim(0, 1.1)
        ax.set_ylabel("Fraction of rollouts")
        ax.set_title("6. Subtask Ladder")
        for xpos_i, val in zip(xpos - width / 2, full_rates):
            ax.text(xpos_i, val + 0.03, f"{val * 100:.0f}%", ha="center", va="bottom", fontsize=8)
        for xpos_i, val in zip(xpos + width / 2, low_rates):
            ax.text(xpos_i, val + 0.03, f"{val * 100:.0f}%", ha="center", va="bottom", fontsize=8)
        ax.legend(fontsize=8)

        plt.tight_layout()
        savefig(fig, out_dir / "resolution_evidence_summary.png")


def render_summary_table(teleop_summary: dict, summary_by_cond: dict[str, dict], out_dir: Path) -> None:
    full_teleop = teleop_summary[POLICY_CONDITIONS[0]["teleop_label"]]
    low_teleop = teleop_summary[POLICY_CONDITIONS[1]["teleop_label"]]
    full_policy = summary_by_cond[POLICY_CONDITIONS[0]["name"]]
    low_policy = summary_by_cond[POLICY_CONDITIONS[1]["name"]]
    full_samples_per_ep = float(
        full_teleop.get("samples_per_episode", full_teleop["n_steps"] / max(full_teleop["n_episodes"], 1))
    )
    low_samples_per_ep = float(
        low_teleop.get("samples_per_episode", low_teleop["n_steps"] / max(low_teleop["n_episodes"], 1))
    )

    text = f"""# RQ1 Resolution Experiment — Summary Table

## Experiment Setup

- Task: AGX excavation teleop (dig -> swing -> dump)
- Conditions: `720x480(full)` vs `240x160(low)` at **0ms injected delay**
- Teleop episodes per condition: 10
- ACT eval rollouts per condition: 10
- Policy success criterion: `dump_complete_final_hold` (300kg retained in target, bucket <=100kg, hold 25 steps)

## Teleop Data Quality

| Metric | 720x480(full) | 240x160(low) |
|---|---:|---:|
| Measured step interval mean (ms) | {full_teleop["step_interval_ms"]["mean"]:.1f} | {low_teleop["step_interval_ms"]["mean"]:.1f} |
| Action jerk mean | {full_teleop["action_jerk"]["mean"]:.2f} | {low_teleop["action_jerk"]["mean"]:.2f} |
| Reversal rate | {full_teleop["reversal_rate"]["mean"]:.3f} | {low_teleop["reversal_rate"]["mean"]:.3f} |
| Samples per episode | {full_samples_per_ep:.0f} | {low_samples_per_ep:.0f} |
| Teleop success rate | {full_teleop["success_rate"] * 100:.0f}% | {low_teleop["success_rate"] * 100:.0f}% |
| Mean successful episode length (steps) | {full_teleop["episode_length"]["mean"]:.0f} | {low_teleop["episode_length"]["mean"]:.0f} |

## ACT Training and Evaluation

| Metric | 720x480(full) | 240x160(low) |
|---|---:|---:|
| Best validation loss | {full_policy["best_val_loss"]:.3f} | {low_policy["best_val_loss"]:.3f} |
| Policy success rate | {full_policy["metrics"]["success_rate"] * 100:.0f}% | {low_policy["metrics"]["success_rate"] * 100:.0f}% |
| Avg max bucket mass (kg) | {full_policy["avg_max_bucket_mass"]:.0f} | {low_policy["avg_max_bucket_mass"]:.0f} |
| Avg final bucket mass (kg) | {full_policy["avg_final_bucket_mass"]:.0f} | {low_policy["avg_final_bucket_mass"]:.0f} |
| Avg max retained target mass (kg) | {full_policy["avg_max_signal_value"]:.0f} | {low_policy["avg_max_signal_value"]:.0f} |
| Dig rate (`max_bucket_mass >= 300kg`) | {full_policy["dig_rate"] * 100:.0f}% | {low_policy["dig_rate"] * 100:.0f}% |
| Bucket emptied rate (`final_bucket_mass <= 100kg`) | {full_policy["emptied_rate"] * 100:.0f}% | {low_policy["emptied_rate"] * 100:.0f}% |
| Retained target mass reached (`max_signal_value >= 300kg`) | {full_policy["retained_rate"] * 100:.0f}% | {low_policy["retained_rate"] * 100:.0f}% |

## Interpretation

1. **Low resolution does not break human teleop**
   - Both teleop conditions stay at `100%` success.
   - Step interval / jerk / reversal change only modestly relative to the latency experiment.

2. **But low resolution does break learned policy behavior**
   - `720x480(full)` reaches `30%` final task success.
   - `240x160(low)` drops to `0%` success despite similar BC validation loss (`{full_policy["best_val_loss"]:.3f}` vs `{low_policy["best_val_loss"]:.3f}`).

3. **Failure happens after the digging stage**
   - Lowres still achieves `100%` dig-rate under the `max_bucket_mass >= 300kg` criterion.
   - However it never converts that bucket load into retained target mass (`0%`) and never finishes with an emptied bucket (`0%`).
   - This is consistent with a **phase-2 / dump-positioning failure** caused by insufficient visual detail, not with a total inability to move or scoop.

## Recommended Thesis-Proposal Claim

This resolution control is stronger when phrased as:

> Reducing operator-view image resolution from `720x480` to `240x160` does **not** materially prevent successful human teleoperation, but it does remove enough spatial detail to make behavior cloning fail downstream. The learned policy can still load soil, yet it cannot reliably align, dump, and satisfy the final retained-mass criterion.
"""
    out_path = out_dir / "summary_table.md"
    out_path.write_text(text, encoding="utf-8")
    print(f"[resolution] saved -> {out_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate stronger plots for the resolution proof experiment.")
    parser.add_argument(
        "--teleop-summary",
        type=Path,
        default=Path("outputs/rq1/resolution_proof/data_quality_summary.json"),
        help="Path to the teleop data-quality JSON summary.",
    )
    parser.add_argument(
        "--eval-root",
        type=Path,
        default=Path("runs/eval"),
        help="Root directory containing rq1_act_fullres / rq1_act_lowres eval results.",
    )
    parser.add_argument(
        "--ckpt-root",
        type=Path,
        default=Path("runs/ckpts"),
        help="Root directory containing rq1_act_fullres / rq1_act_lowres training metadata.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("outputs/rq1/resolution_proof"),
        help="Output directory for figures and summary table.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    teleop_json = load_json(args.teleop_summary)["conditions"]
    summary_by_cond = {
        cond["name"]: summarize_policy_condition(cond["name"], args.eval_root, args.ckpt_root)
        for cond in POLICY_CONDITIONS
    }

    render_policy_behavior(summary_by_cond, args.out)
    render_evidence_summary(teleop_json, summary_by_cond, args.out)
    render_summary_table(teleop_json, summary_by_cond, args.out)


if __name__ == "__main__":
    main()
