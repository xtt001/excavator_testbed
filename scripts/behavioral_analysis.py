"""
Behavioral analysis of ACT policy rollouts across latency conditions.

Plots per-step state signals averaged over 10 rollouts per condition:
  1. mass_in_bucket_kg  – did the robot learn to dig?
  2. min_distance_to_dig_area_m  – does it approach the dig zone?
  3. reward_phase distribution (stacked bar) – which task phases are reached?
  4. qpos[0] over time  – swing joint trajectory (shows swing behaviour)
  5. excavated_mass_kg  – cumulative excavation

Run:
    conda run -n aloha python scripts/behavioral_analysis.py
"""
import json
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# ---------------------------------------------------------------------------
CONDITIONS = [
    ("rq1_act_fullres", "0ms fullres", "#1a9641"),
    ("rq1_act_25ms",    "25ms delay",  "#fdae61"),
    ("rq1_act_50ms",    "50ms delay",  "#d7191c"),
    ("rq1_act_100ms",   "100ms delay", "#7b2d8b"),
]

BASE = "runs/eval"
OUT  = "outputs/rq1/latency_proof_4cond"
os.makedirs(OUT, exist_ok=True)

N_STEPS = 1000
N_ROLLOUTS = 10

PHASE_ORDER = ["idle", "loading", "approaching_target", "depositing", "retained_success"]
PHASE_COLORS = {
    "idle":               "#cccccc",
    "loading":            "#4dac26",
    "approaching_target": "#f1b800",
    "depositing":         "#d7191c",
    "retained_success":   "#1a9641",
}

# ---------------------------------------------------------------------------
def load_rollouts(exp_name):
    """Return list of per-step records for all 10 rollouts."""
    rollouts = []
    for i in range(N_ROLLOUTS):
        path = f"{BASE}/{exp_name}/results/rollouts/rollout_{i:03d}.jsonl"
        steps = []
        with open(path) as f:
            for line in f:
                steps.append(json.loads(line))
        rollouts.append(steps)
    return rollouts


def extract_metric(rollouts, metric_fn):
    """
    metric_fn(step_event) -> float
    Returns array [N_ROLLOUTS, N_STEPS].
    """
    data = np.zeros((N_ROLLOUTS, N_STEPS))
    for r, steps in enumerate(rollouts):
        for t, e in enumerate(steps):
            if t >= N_STEPS:
                break
            data[r, t] = metric_fn(e)
    return data


def extract_phases(rollouts):
    """
    Returns dict phase -> array [N_ROLLOUTS, N_STEPS] (binary 0/1).
    """
    phase_data = {p: np.zeros((N_ROLLOUTS, N_STEPS)) for p in PHASE_ORDER}
    phase_data["other"] = np.zeros((N_ROLLOUTS, N_STEPS))
    for r, steps in enumerate(rollouts):
        for t, e in enumerate(steps):
            if t >= N_STEPS:
                break
            p = e.get("reward_phase", "idle")
            if p in phase_data:
                phase_data[p][r, t] = 1
            else:
                phase_data["other"][r, t] = 1
    return phase_data


# ---------------------------------------------------------------------------
# Load all data
print("Loading rollout data...")
all_data = {}
for exp, label, color in CONDITIONS:
    rollouts = load_rollouts(exp)
    all_data[exp] = {
        "label": label,
        "color": color,
        "rollouts": rollouts,
        "bucket_mass":   extract_metric(rollouts, lambda e: e["task_metrics"]["mass_in_bucket_kg"]),
        "dist_dig":      extract_metric(rollouts, lambda e: e["task_metrics"]["min_distance_to_dig_area_m"]),
        "dist_target":   extract_metric(rollouts, lambda e: e["task_metrics"]["min_distance_to_target_m"]),
        "excavated":     extract_metric(rollouts, lambda e: e["task_metrics"]["excavated_mass_kg"]),
        "deposited":     extract_metric(rollouts, lambda e: e["task_metrics"]["deposited_mass_in_target_box_kg"]),
        "qpos":          extract_metric(rollouts, lambda e: e["qpos"][0] if e.get("qpos") else 0),
        "phases":        extract_phases(rollouts),
    }

steps = np.arange(N_STEPS)


# ---------------------------------------------------------------------------
# Figure: 5-panel behavioral comparison
fig, axes = plt.subplots(2, 3, figsize=(18, 10))
fig.suptitle("Policy Behavioral Analysis Across Latency Conditions\n(mean ± std over 10 rollouts)",
             fontsize=14, fontweight="bold")


def plot_mean_std(ax, data_dict, key, ylabel, title, yscale="linear"):
    for exp, label, color in CONDITIONS:
        d = data_dict[exp][key]
        mean = d.mean(axis=0)
        std  = d.std(axis=0)
        ax.plot(steps, mean, color=color, label=label, lw=1.8)
        ax.fill_between(steps, mean - std, mean + std, color=color, alpha=0.15)
    ax.set_xlabel("Eval step")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.set_yscale(yscale)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)


# --- Panel 1: mass in bucket over time ---
plot_mean_std(axes[0, 0], all_data, "bucket_mass",
              "Mass in bucket (kg)", "① Mass in Bucket\n(reaches 0 → never dug)")

# --- Panel 2: distance to dig area ---
plot_mean_std(axes[0, 1], all_data, "dist_dig",
              "Distance to dig area (m)", "② Distance to Dig Area\n(approaches → trying to dig)")

# --- Panel 3: excavated mass ---
plot_mean_std(axes[0, 2], all_data, "excavated",
              "Cumulative excavated mass (kg)", "③ Excavated Mass\n(non-zero → bucket was filled)")

# --- Panel 4: deposited mass (success signal) ---
plot_mean_std(axes[1, 0], all_data, "deposited",
              "Deposited in target (kg)", "④ Deposited Mass\n(non-zero → reaching dump zone)")

# --- Panel 5: swing joint (qpos[0]) ---
plot_mean_std(axes[1, 1], all_data, "qpos",
              "Swing joint angle (rad)", "⑤ Swing Joint Trajectory\n(shows spatial exploration)")

# --- Panel 6: reward phase stacked bar per condition ---
ax = axes[1, 2]
bar_w = 0.6
phase_fractions = {}
for exp, label, color in CONDITIONS:
    pdata = all_data[exp]["phases"]
    fracs = {}
    for p in PHASE_ORDER:
        fracs[p] = pdata[p].mean()   # mean over rollouts and steps
    phase_fractions[exp] = fracs

labels_cond = [all_data[exp]["label"] for exp, _, _ in CONDITIONS]
x = np.arange(len(CONDITIONS))
bottoms = np.zeros(len(CONDITIONS))

for p in PHASE_ORDER:
    vals = [phase_fractions[exp][p] for exp, _, _ in CONDITIONS]
    ax.bar(x, vals, bar_w, bottom=bottoms, color=PHASE_COLORS[p],
           label=p.replace("_", " "))
    bottoms += np.array(vals)

ax.set_xticks(x)
ax.set_xticklabels(labels_cond, fontsize=9)
ax.set_ylabel("Fraction of steps")
ax.set_ylim(0, 1)
ax.set_title("⑥ Task Phase Distribution\n(how far does each policy get?)")
ax.legend(fontsize=8, loc="upper right")
ax.grid(True, alpha=0.3, axis="y")

plt.tight_layout()
out_path = f"{OUT}/behavioral_analysis.png"
fig.savefig(out_path, dpi=150, bbox_inches="tight")
print(f"Saved: {out_path}")
plt.close()


# ---------------------------------------------------------------------------
# Also save a compact 2-panel version for papers
fig2, (ax_phase, ax_bucket) = plt.subplots(1, 2, figsize=(12, 5))
fig2.suptitle("ACT Policy Behavior Under Network Latency", fontsize=13, fontweight="bold")

# Phase stacked bar
bottoms = np.zeros(len(CONDITIONS))
for p in PHASE_ORDER:
    vals = [phase_fractions[exp][p] for exp, _, _ in CONDITIONS]
    ax_phase.bar(x, vals, bar_w, bottom=bottoms, color=PHASE_COLORS[p],
                 label=p.replace("_", " "))
    bottoms += np.array(vals)
ax_phase.set_xticks(x)
ax_phase.set_xticklabels(labels_cond)
ax_phase.set_ylabel("Fraction of eval steps")
ax_phase.set_title("Task Phase Distribution")
ax_phase.legend(fontsize=9)
ax_phase.grid(True, alpha=0.3, axis="y")

# Bucket mass curves
for exp, label, color in CONDITIONS:
    d = all_data[exp]["bucket_mass"]
    mean = d.mean(axis=0)
    std = d.std(axis=0)
    ax_bucket.plot(steps, mean, color=color, label=label, lw=2)
    ax_bucket.fill_between(steps, mean - std, mean + std, color=color, alpha=0.15)
ax_bucket.set_xlabel("Eval step")
ax_bucket.set_ylabel("Mass in bucket (kg)")
ax_bucket.set_title("Bucket Mass Over Time")
ax_bucket.legend()
ax_bucket.grid(True, alpha=0.3)

plt.tight_layout()
out2 = f"{OUT}/behavioral_compact.png"
fig2.savefig(out2, dpi=150, bbox_inches="tight")
print(f"Saved: {out2}")
plt.close()

print("Done.")

# ---------------------------------------------------------------------------
# Extra figure: zoom in on the 3 latency conditions only
# (to reveal subtle differences invisible when fullres dominates y-axis)
LATENCY_CONDS = [
    ("rq1_act_25ms",    "25ms delay",  "#fdae61"),
    ("rq1_act_50ms",    "50ms delay",  "#d7191c"),
    ("rq1_act_100ms",   "100ms delay", "#7b2d8b"),
]

fig3, axes3 = plt.subplots(1, 3, figsize=(16, 5))
fig3.suptitle("Behavioral Analysis – Latency Conditions Only\n(Subtle differences among 25 / 50 / 100 ms)",
              fontsize=13, fontweight="bold")

# Panel A: distance to dig area (zoomed)
ax = axes3[0]
for exp, label, color in LATENCY_CONDS:
    d = all_data[exp]["dist_dig"]
    mean = d.mean(axis=0)
    std  = d.std(axis=0)
    ax.plot(steps, mean, color=color, label=label, lw=2)
    ax.fill_between(steps, mean - std, mean + std, color=color, alpha=0.2)
ax.set_xlabel("Eval step")
ax.set_ylabel("Distance to dig area (m)")
ax.set_title("Distance to Dig Area\n(lower = more likely to dig)")
ax.legend()
ax.grid(True, alpha=0.3)
# Annotate min distance
for exp, label, color in LATENCY_CONDS:
    d = all_data[exp]["dist_dig"]
    min_val = d.mean(axis=0).min()
    ax.axhline(min_val, color=color, ls="--", lw=0.8, alpha=0.6)

# Panel B: swing joint range (shows spatial exploration)
ax = axes3[1]
for exp, label, color in LATENCY_CONDS:
    d = all_data[exp]["qpos"]
    mean = d.mean(axis=0)
    std  = d.std(axis=0)
    ax.plot(steps, mean, color=color, label=label, lw=2)
    ax.fill_between(steps, mean - std, mean + std, color=color, alpha=0.2)
ax.set_xlabel("Eval step")
ax.set_ylabel("Swing joint angle (rad)")
ax.set_title("Swing Joint Trajectory\n(flat = frozen / not exploring)")
ax.legend()
ax.grid(True, alpha=0.3)

# Panel C: summary bar chart of 4 fine metrics
metrics_bar = [
    ("Min dist to dig (m)",  [all_data[exp]["dist_dig"].mean(axis=0).min() for exp, _, _ in LATENCY_CONDS]),
    ("Swing joint range (rad)", [all_data[exp]["qpos"].max() - all_data[exp]["qpos"].min() for exp, _, _ in LATENCY_CONDS]),
]
ax = axes3[2]
x_bar = np.arange(len(LATENCY_CONDS))
width = 0.35

vals_dist = [all_data[exp]["dist_dig"].mean(axis=0).min() for exp, _, _ in LATENCY_CONDS]
vals_swing = [(all_data[exp]["qpos"].mean(axis=0).max() - all_data[exp]["qpos"].mean(axis=0).min()) for exp, _, _ in LATENCY_CONDS]

ax_twin = ax.twinx()
bars1 = ax.bar(x_bar - width/2, vals_dist,  width, color=[c for _, _, c in LATENCY_CONDS], alpha=0.8, label="Min dist to dig (m)")
bars2 = ax_twin.bar(x_bar + width/2, vals_swing, width, color=[c for _, _, c in LATENCY_CONDS], alpha=0.4, hatch="//", label="Swing range (rad)")
ax.set_xticks(x_bar)
ax.set_xticklabels([l for _, l, _ in LATENCY_CONDS])
ax.set_ylabel("Min dist to dig area (m)", color="black")
ax_twin.set_ylabel("Swing joint range (rad)", color="grey")
ax.set_title("Summary: Fine-Grained Metrics\n(subtle gradient within latency group)")
lines1 = mpatches.Patch(color='grey', alpha=0.7, label='Min dist to dig (m)')
lines2 = mpatches.Patch(color='grey', alpha=0.3, hatch='//', label='Swing range (rad)')
ax.legend(handles=[lines1, lines2], fontsize=9)
ax.grid(True, alpha=0.3, axis="y")

plt.tight_layout()
out3 = f"{OUT}/behavioral_latency_zoom.png"
fig3.savefig(out3, dpi=150, bbox_inches="tight")
print(f"Saved: {out3}")
plt.close()
