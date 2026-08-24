"""Aggregation, plots, and Chinese report for the Dig dispatch diagnostic."""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np


def aggregate_pair_metrics(
    *,
    pairs: Sequence[Mapping[str, Any]],
    traces: Mapping[str, Sequence[Mapping[str, Any]]],
    collection: Mapping[str, Any],
    short_horizon_gate: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], tuple[str, ...]]:
    if len(pairs) < 100:
        invalid_reasons = (f"variant_count_below_100:{len(pairs)}",)
    else:
        invalid_reasons = ()
    if not bool(collection["legacy_public_predict_compatibility"]["passed"]):
        invalid_reasons += ("legacy_public_predict_compatibility_failed",)
    if not bool(collection["policy_instances_independent"]):
        invalid_reasons += ("arm_policy_identity_shared",)
    if not bool(collection["policy_cache_identity_independent"]):
        invalid_reasons += ("arm_cache_identity_shared",)
    if any(collection["policy_parameters_require_grad"].values()):
        invalid_reasons += ("act_parameters_not_frozen",)
    if not bool(short_horizon_gate.get("horizon_5_passed")) or not bool(
        short_horizon_gate.get("horizon_10_passed")
    ):
        invalid_reasons += ("short_horizon_dynamics_gate_failed",)

    trace_support = {
        strategy: _trace_support(rows) for strategy, rows in traces.items()
    }
    if any(value["nonfinite_count"] for value in trace_support.values()):
        invalid_reasons += ("nonfinite_action_or_chunk",)
    if any(
        bool(row.get("clipping_applied")) for rows in traces.values() for row in rows
    ):
        invalid_reasons += ("diagnostic_action_clipped",)

    raw_by_source: dict[int, list[float]] = defaultdict(list)
    for pair in pairs:
        raw_by_source[int(pair["source_episode_id"])].append(
            float(pair["raw_goal_response"]["passes_fixed_80pct_gate"])
        )
    raw_success_fraction = float(
        np.mean([np.mean(values) for values in raw_by_source.values()])
    )
    horizon_payload = {}
    bootstrap_rows = []
    by_source: dict[str, Any] = {}
    for horizon in (5, 10):
        key = f"horizon_{horizon}"
        horizon_payload[key] = {}
        for strategy in ("legacy", "latest"):
            values = [pair["projection"]["horizons"][key][strategy] for pair in pairs]
            direction = np.asarray(
                [value["direction_success"] for value in values], dtype=np.float64
            )
            ranking = np.asarray(
                [value["ranking_accuracy"] for value in values], dtype=np.float64
            )
            pair_separation = np.asarray(
                [value["projected_tip_separation_m"] for value in values],
                dtype=np.float64,
            )
            separation = np.asarray(
                [
                    anchor["projected_tip_separation_m"]
                    for value in values
                    for anchor in value["anchors"]
                ],
                dtype=np.float64,
            )
            source_direction = _source_values(pairs, direction)
            source_ranking = _source_values(pairs, ranking)
            source_separation = _source_values(pairs, pair_separation)
            horizon_payload[key][strategy] = {
                "direction_success": float(
                    np.mean([np.mean(value) for value in source_direction.values()])
                ),
                "ranking_accuracy": float(
                    np.mean([np.mean(value) for value in source_ranking.values()])
                ),
                "projected_tip_separation_p10_m": float(np.quantile(separation, 0.10)),
                "projected_tip_separation_median_m": float(np.median(separation)),
                "projected_tip_separation_mean_m": float(np.mean(separation)),
                "dispatched_action_separation_mean_l2": float(
                    np.mean(
                        [
                            pair["action_separation"][strategy][
                                f"horizon_{horizon}_mean_l2"
                            ]
                            for pair in pairs
                        ]
                    )
                ),
                "action_support_violation_rate": trace_support[strategy][
                    "source_equal_support_violation_rate"
                ],
                "by_source": {
                    str(source): {
                        "direction_success": float(np.mean(source_direction[source])),
                        "ranking_accuracy": float(np.mean(source_ranking[source])),
                        "projected_tip_separation_mean_m": float(
                            np.mean(source_separation[source])
                        ),
                    }
                    for source in sorted(source_direction)
                },
            }
        by_source[key] = {
            strategy: horizon_payload[key][strategy]["by_source"]
            for strategy in ("legacy", "latest")
        }

    for pair in pairs:
        bootstrap_rows.append(
            {
                "source_episode_id": int(pair["source_episode_id"]),
                "primitive_episode_id": int(pair["primitive_episode_id"]),
                "legacy": {
                    name: float(
                        pair["projection"]["horizons"]["horizon_10"]["legacy"][name]
                    )
                    for name in (
                        "direction_success",
                        "ranking_accuracy",
                        "projected_tip_separation_m",
                    )
                },
                "latest": {
                    name: float(
                        pair["projection"]["horizons"]["horizon_10"]["latest"][name]
                    )
                    for name in (
                        "direction_success",
                        "ranking_accuracy",
                        "projected_tip_separation_m",
                    )
                },
            }
        )
    by_variant = [_pair_json(pair) for pair in pairs]
    by_episode = {
        str(pair["primitive_episode_id"]): {
            "variant_id": str(pair["variant_id"]),
            "source_episode_id": int(pair["source_episode_id"]),
            "horizon_5": pair["projection"]["horizons"]["horizon_5"],
            "horizon_10": pair["projection"]["horizons"]["horizon_10"],
            "action_separation": pair["action_separation"],
            "raw_goal_response": pair["raw_goal_response"],
        }
        for pair in pairs
    }
    payload = {
        "schema": "dig_act_receding_horizon_pair_metrics_v1",
        "status": "completed",
        "valid": not invalid_reasons,
        "invalid_reasons": list(invalid_reasons),
        "evidence_kind": "teacher_forced_recorded_observation_plus_short_horizon_projection_only",
        "variant_count": len(pairs),
        "source_count": len({int(pair["source_episode_id"]) for pair in pairs}),
        "episode_count": len({int(pair["primitive_episode_id"]) for pair in pairs}),
        "source_33_34_used": False,
        "window_random_split": False,
        "raw_goal_response": {
            "legacy": bool(raw_success_fraction >= 0.80),
            "latest": bool(raw_success_fraction >= 0.80),
            "source_equal_variant_success_fraction": raw_success_fraction,
            "required_fraction": 0.80,
        },
        **horizon_payload,
        "action_support": trace_support,
        "legacy_contributing_chunk_age": _legacy_age_summary(traces["legacy"]),
        "by_source": by_source,
        "by_episode": by_episode,
        "by_variant": by_variant,
        "production_defaults_changed": False,
        "short_horizon_projection_only": True,
    }
    return payload, bootstrap_rows, invalid_reasons


def write_diagnostic_plots(
    destination: Path,
    *,
    pair_metrics: Mapping[str, Any],
) -> list[str]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    paths = []
    horizon = pair_metrics["horizon_10"]
    metric_path = destination / "goal_direction_ranking.png"
    if metric_path.exists():
        raise FileExistsError(metric_path)
    fig, ax = plt.subplots(figsize=(7, 4))
    x = np.arange(2)
    width = 0.35
    ax.bar(
        x - width / 2,
        [horizon["legacy"]["direction_success"], horizon["legacy"]["ranking_accuracy"]],
        width,
        label="legacy",
    )
    ax.bar(
        x + width / 2,
        [horizon["latest"]["direction_success"], horizon["latest"]["ranking_accuracy"]],
        width,
        label="latest",
    )
    ax.axhline(0.8, color="black", linestyle="--", linewidth=1)
    ax.set_xticks(x, ["direction", "ranking"])
    ax.set_ylim(0.0, 1.0)
    ax.set_ylabel("source-equal success fraction")
    ax.legend()
    fig.tight_layout()
    fig.savefig(metric_path, dpi=160)
    plt.close(fig)
    paths.append(metric_path.name)

    separation_path = destination / "projected_tip_separation.png"
    if separation_path.exists():
        raise FileExistsError(separation_path)
    legacy = [
        row["projection"]["horizons"]["horizon_10"]["legacy"][
            "projected_tip_separation_m"
        ]
        for row in pair_metrics["by_variant"]
    ]
    latest = [
        row["projection"]["horizons"]["horizon_10"]["latest"][
            "projected_tip_separation_m"
        ]
        for row in pair_metrics["by_variant"]
    ]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.boxplot([legacy, latest], tick_labels=["legacy", "latest"], showfliers=False)
    ax.axhline(0.02, color="black", linestyle="--", linewidth=1)
    ax.set_ylabel("10-step projected tip separation (m)")
    fig.tight_layout()
    fig.savefig(separation_path, dpi=160)
    plt.close(fig)
    paths.append(separation_path.name)

    age_path = destination / "legacy_contributing_chunk_age.png"
    if age_path.exists():
        raise FileExistsError(age_path)
    age_counts = pair_metrics["legacy_contributing_chunk_age"]["count_by_age"]
    fig, ax = plt.subplots(figsize=(7, 4))
    ages = np.asarray([int(key) for key in age_counts], dtype=int)
    counts = np.asarray([age_counts[str(age)] for age in ages], dtype=int)
    ax.bar(ages, counts)
    ax.set_xlabel("contributing chunk age (frames)")
    ax.set_ylabel("contributor count")
    fig.tight_layout()
    fig.savefig(age_path, dpi=160)
    plt.close(fig)
    paths.append(age_path.name)
    return paths


def render_report(
    *,
    pair_metrics: Mapping[str, Any],
    bootstrap: Mapping[str, Any],
    decision: Mapping[str, Any],
    output_dir: Path,
) -> str:
    classification = str(decision["classification"])
    interpretation = {
        "invalid_diagnostic": "合同、lineage、支持或短期投影门不完整，本轮不能归因。",
        "temporal_dispatch_not_primary": (
            "只使用最新 chunk 的首动作没有通过预注册改善门，legacy temporal aggregation "
            "不是当前空间目标跟随失败的主要阻塞。"
        ),
        "latest_feedback_dispatch_promising": (
            "最新反馈 dispatch 在离线短期投影中明显优于 legacy；这只允许申请一次最小 Unity 因果验证。"
        ),
        "goal_condition_response_regressed": "两种策略都缺少 raw goal response，应先修复条件响应回归。",
    }[classification]
    h10 = pair_metrics["horizon_10"]
    boot = bootstrap["metrics"]
    return f"""# Dig ACT receding-horizon dispatch 离线诊断

## 结论

- 本轮只比较相同 recorded observation 下的 legacy temporal aggregation 与 request-local latest-chunk 首动作 dispatch。{interpretation}
- 没有训练或修改 ACT，没有创建 optimizer，没有调用 backward；默认 ACT dispatch 和生产配置未改变。
- 没有启动 Unity，也没有发送任何动作。5/10 步结果仅为冻结 joint dynamics 加 fixed-tip FK 的 `short_horizon_projection_only`，不是 Unity/真实轨迹或土体效果。
- 唯一下一步：`{decision["next_experiment"]}`。

## 技术依据

- 变体/episode/source：`{pair_metrics["variant_count"]}` / `{pair_metrics["episode_count"]}` / `{pair_metrics["source_count"]}`；source 33/34 未使用。
- 10-step direction success：legacy `{h10["legacy"]["direction_success"]:.4f}`，latest `{h10["latest"]["direction_success"]:.4f}`。
- 10-step ranking accuracy：legacy `{h10["legacy"]["ranking_accuracy"]:.4f}`，latest `{h10["latest"]["ranking_accuracy"]:.4f}`。
- 10-step projected tip separation p10：legacy `{h10["legacy"]["projected_tip_separation_p10_m"]:.6f} m`，latest `{h10["latest"]["projected_tip_separation_p10_m"]:.6f} m`。
- action support violation：legacy `{h10["legacy"]["action_support_violation_rate"]:.6f}`，latest `{h10["latest"]["action_support_violation_rate"]:.6f}`。
- paired bootstrap 95% CI，latest-legacy direction：`[{boot["direction_success"]["ci95_low"]:.4f}, {boot["direction_success"]["ci95_high"]:.4f}]`；ranking：`[{boot["ranking_accuracy"]["ci95_low"]:.4f}, {boot["ranking_accuracy"]["ci95_high"]:.4f}]`。
- 分类：`{classification}`。
- 工件根：`{output_dir}`。
"""


def _trace_support(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    by_source: dict[int, list[float]] = defaultdict(list)
    violation_count = 0
    nonfinite_count = 0
    for row in rows:
        support = row["action_support"]
        violation = int(support["support_violation_count"] > 0)
        violation_count += violation
        nonfinite_count += int(row["nonfinite"] or support["nonfinite_count"] > 0)
        by_source[int(row["source_episode_id"])].append(float(violation))
    count = len(rows)
    return {
        "action_count": count,
        "support_violation_count": violation_count,
        "support_violation_rate": violation_count / count if count else 0.0,
        "source_equal_support_violation_rate": float(
            np.mean([np.mean(value) for value in by_source.values()])
        ),
        "nonfinite_count": nonfinite_count,
        "clipping_applied": False,
        "by_source": {
            str(source): float(np.mean(values))
            for source, values in sorted(by_source.items())
        },
    }


def _source_values(
    pairs: Sequence[Mapping[str, Any]], values: np.ndarray
) -> dict[int, np.ndarray]:
    grouped: dict[int, list[float]] = defaultdict(list)
    for pair, value in zip(pairs, values, strict=True):
        grouped[int(pair["source_episode_id"])].append(float(value))
    return {
        source: np.asarray(source_values, dtype=np.float64)
        for source, source_values in grouped.items()
    }


def _legacy_age_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    ages = [int(age) for row in rows for age in row["contributing_chunk_ages"]]
    counts = {str(age): ages.count(age) for age in sorted(set(ages))}
    return {
        "contributor_count": len(ages),
        "count_by_age": counts,
        "maximum_age": max(ages) if ages else None,
        "p01": float(np.quantile(ages, 0.01)) if ages else None,
        "p50": float(np.quantile(ages, 0.50)) if ages else None,
        "p99": float(np.quantile(ages, 0.99)) if ages else None,
    }


def _pair_json(pair: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(
        json.dumps(
            {
                "variant_id": pair["variant_id"],
                "variant_type": pair["variant_type"],
                "source_episode_id": pair["source_episode_id"],
                "primitive_episode_id": pair["primitive_episode_id"],
                "frame_index": pair["frame_index"],
                "goals": pair["goals"],
                "tokens": pair["tokens"],
                "raw_goal_response": pair["raw_goal_response"],
                "action_separation": pair["action_separation"],
                "projection": pair["projection"],
            },
            allow_nan=False,
        )
    )


__all__ = [
    "aggregate_pair_metrics",
    "render_report",
    "write_diagnostic_plots",
]
