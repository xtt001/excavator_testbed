"""Plots and report for the offline non-promotable minimal DP probe."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def write_minimal_dp_probe_plots(
    destination: Path,
    *,
    training_histories: Sequence[Mapping[str, Any]],
    metrics: Mapping[str, Any],
) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    paths = []
    loss_path = destination / "training_loss.png"
    fig, ax = plt.subplots(figsize=(7, 4))
    for history in training_histories:
        ax.plot(history["loss"], label=f"seed {history['seed']}")
    ax.set_xlabel("update")
    ax.set_ylabel("epsilon MSE")
    ax.legend()
    fig.tight_layout()
    fig.savefig(loss_path, dpi=160)
    plt.close(fig)
    paths.append(loss_path.name)

    effect_path = destination / "goal_vs_noise_effect.png"
    distribution = metrics["condition_distribution"]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(
        ["goal p10", "goal p50", "noise p95", "zero p50", "shuffle p50"],
        [
            distribution["goal_effect_first_action_l2_p10"],
            distribution["goal_effect_first_action_l2_p50"],
            distribution["noise_effect_first_action_l2_p95"],
            distribution["zero_effect_first_action_l2_p50"],
            distribution["shuffled_effect_first_action_l2_p50"],
        ],
    )
    ax.set_ylabel("first-action L2")
    fig.tight_layout()
    fig.savefig(effect_path, dpi=160)
    plt.close(fig)
    paths.append(effect_path.name)

    gate_path = destination / "projection_absolute_gates.png"
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(
        ["direction", "ranking", "separation/2cm"],
        [
            metrics["direction_success"],
            metrics["ranking_accuracy"],
            metrics["projected_tip_separation_p10_m"] / 0.02,
        ],
    )
    ax.axhline(0.8, color="black", linestyle="--", linewidth=1)
    ax.set_ylim(0.0, max(1.0, metrics["projected_tip_separation_p10_m"] / 0.02 + 0.1))
    fig.tight_layout()
    fig.savefig(gate_path, dpi=160)
    plt.close(fig)
    paths.append(gate_path.name)
    return paths


def render_minimal_dp_probe_report(
    *,
    metrics: Mapping[str, Any],
    decision: Mapping[str, Any],
    output_dir: Path,
) -> str:
    classification = str(decision["classification"])
    interpretation = {
        "minimal_dp_probe_response_promising": (
            "最小 DP 在离线绝对门上表现出响应，但数据可辨识性前置门仍失败，所以结果不可晋级。"
        ),
        "minimal_dp_probe_action_support_blocked": (
            "DP 的动作支持恶化超过限制，离线探针被支持门阻断。"
        ),
        "minimal_dp_probe_noise_dominates": (
            "diffusion noise 造成的差异不小于 goal 造成的差异，无法归因于 token。"
        ),
        "minimal_dp_probe_goal_response_insufficient": (
            "DP 没有同时通过方向、排序、分离、bootstrap 和 seed 一致性门。"
        ),
        "invalid_minimal_dp_probe": "合同、lineage 或数值完整性失败，本探针无效。",
    }[classification]
    distribution = metrics["condition_distribution"]
    return f"""# 最小 Dig Diffusion Policy 离线探针

## 结论

- 本轮只训练并评估默认关闭、不可晋级的最小 DP 探针。{interpretation}
- 每帧从当前 observation 重新采样 100×4 chunk，只使用第一个动作；未使用 temporal aggregation。
- 没有修改或训练 ACT，没有训练土体模型，没有启动 Unity 或发送动作，生产默认未改变。
- 数据可辨识性硬门仍为失败，因此任何正结果都只能看作架构响应诊断，不能申请 Unity。

## 技术依据

- 10-step direction/ranking：`{metrics["direction_success"]:.6f}` / `{metrics["ranking_accuracy"]:.6f}`。
- 10-step projected separation p10：`{metrics["projected_tip_separation_p10_m"]:.6f} m`，门为 0.02 m。
- source/episode bootstrap joint margin 下界：`{metrics["bootstrap_ci95_low"]:.6f}`。
- dispatched action support violation：`{metrics["action_support_violation_rate"]:.6f}`；ACT latest 参照为 `{metrics["act_reference_support_violation_rate"]:.6f}`。
- goal first-action L2 p10：`{distribution["goal_effect_first_action_l2_p10"]:.6f}`；noise p95：`{distribution["noise_effect_first_action_l2_p95"]:.6f}`。
- 训练 seed 方向一致率：`{metrics["training_seed_consistent_fraction"]:.6f}`。
- 分类：`{classification}`；下一步仍是 `{decision["next_experiment"]}`。
- 工件根：`{output_dir}`。

5/10 步结果仅为 `short_horizon_projection_only`，不是 Unity/真实轨迹或土体效果。
"""


__all__ = ["render_minimal_dp_probe_report", "write_minimal_dp_probe_plots"]
