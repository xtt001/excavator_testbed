"""Plots and reader-facing report for the Dig data identifiability precheck."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def write_identifiability_plots(
    destination: Path,
    *,
    summary: Mapping[str, Any],
    noise_pairs: Sequence[Mapping[str, Any]],
    signal_pairs: Sequence[Mapping[str, Any]],
    coverage_rows: Sequence[Mapping[str, Any]],
) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    paths = []
    counts_path = destination / "pair_counts.png"
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(
        ["same-goal noise", "different-goal", "covered variants"],
        [
            int(summary["same_goal_noise_pair_count"]),
            int(summary["different_goal_pair_count"]),
            int(summary["covered_variant_count"]),
        ],
    )
    ax.axhline(100, color="black", linestyle="--", linewidth=1)
    ax.set_ylabel("count")
    fig.tight_layout()
    fig.savefig(counts_path, dpi=160)
    plt.close(fig)
    paths.append(counts_path.name)

    signal_path = destination / "action_signal_vs_noise.png"
    fig, ax = plt.subplots(figsize=(7, 4))
    noise = [float(row["first_10_mean_l2"]) for row in noise_pairs]
    signal = [float(row["first_10_mean_l2"]) for row in signal_pairs]
    values = []
    labels = []
    if noise:
        values.append(noise)
        labels.append("same-goal")
    if signal:
        values.append(signal)
        labels.append("different-goal")
    if values:
        ax.boxplot(values, tick_labels=labels, showfliers=False)
    else:
        ax.text(0.5, 0.5, "no qualifying pairs", ha="center", va="center")
        ax.set_xticks([])
    ax.set_ylabel("first-10 action delta L2")
    fig.tight_layout()
    fig.savefig(signal_path, dpi=160)
    plt.close(fig)
    paths.append(signal_path.name)

    coverage_path = destination / "variant_coverage.png"
    fig, ax = plt.subplots(figsize=(7, 4))
    covered = sum(bool(row["covered"]) for row in coverage_rows)
    ax.bar(["covered", "uncovered"], [covered, len(coverage_rows) - covered])
    ax.axhline(100, color="black", linestyle="--", linewidth=1)
    ax.set_ylabel("frozen evaluation variants")
    fig.tight_layout()
    fig.savefig(coverage_path, dpi=160)
    plt.close(fig)
    paths.append(coverage_path.name)
    return paths


def render_identifiability_report(
    *,
    summary: Mapping[str, Any],
    bootstrap: Mapping[str, Any],
    decision: Mapping[str, Any],
    output_dir: Path,
) -> str:
    classification = str(decision["classification"])
    if classification == "goal_action_supervision_identifiable":
        status = "数据门通过；下一步才允许创建公平的 ACT-vs-DP 训练任务。"
    elif classification == "data_supervision_unidentifiable":
        status = (
            "数据门未通过；ACT-vs-DP 训练没有启动，应先补同状态、多目标的配对动作示范。"
        )
    else:
        status = "合同或 lineage 不完整，本轮预检无效，任何策略训练均被禁止。"
    ci_low = bootstrap.get("ci95_low")
    ci_high = bootstrap.get("ci95_high")
    ci_text = (
        "unavailable"
        if ci_low is None or ci_high is None
        else f"[{float(ci_low):.6f}, {float(ci_high):.6f}]"
    )
    funnel = summary.get("pair_funnel", {})
    variant_funnel = summary.get("variant_demo_funnel", {})
    return f"""# Dig goal/action 数据可辨识性预检

## 结论

- 本轮只检查 strict-train 数据能否辨识“同状态、不同 Dig 目标、示教动作随目标改变”。{status}
- 没有加载或训练 ACT/DP，没有创建 optimizer、调用 backward、启动 Unity 或发送动作。
- source 33/34 未参与结构、阈值、配对或选择；默认 temporal aggregation 和生产配置均未改变。
- 下一步：`{decision["next_experiment"]}`。

## 技术依据

- 可用 t0 episode/source：`{summary["eligible_episode_count"]}` / `{summary["eligible_source_count"]}`。
- pair 漏斗（同 source/metadata → 机械状态 → 四相机）：`{funnel.get("source_metadata_episode_matched", 0)}` → `{funnel.get("mechanical_state_matched", 0)}` → `{funnel.get("camera_matched", 0)}`。
- 同目标噪声 pair/source：`{summary["same_goal_noise_pair_count"]}` / `{summary["same_goal_noise_source_count"]}`。
- 不同目标 pair/source：`{summary["different_goal_pair_count"]}` / `{summary["different_goal_source_count"]}`。
- 112 个冻结目标中可覆盖：`{summary["covered_variant_count"]}`；正式门要求至少 100。
- 具有 base/alternate 自然示范的目标：`{variant_funnel.get("variants_with_any_base_demo", 0)}` / `{variant_funnel.get("variants_with_any_alternate_demo", 0)}`。
- 不同目标动作信号通过率：`{summary["action_signal_pass_fraction"]:.6f}`；门为 0.80。
- 动作信号减同目标噪声的 source/episode bootstrap 95% 区间：`{ci_text}`。
- 分类：`{classification}`。
- 工件根：`{output_dir}`。

四相机只用于同观测匹配。这里的动作差异不证明真实轨迹或土体效果，也不构成任何模型架构结论。
"""


__all__ = ["render_identifiability_report", "write_identifiability_plots"]
