"""Pure paired metrics and decision gates for Dig dispatch diagnostics."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

DIRECTION_SUCCESS_MIN = 0.80
RANKING_ACCURACY_MIN = 0.80
IMPROVEMENT_MIN = 0.15
TIP_SEPARATION_P10_MIN_M = 0.02
ACTION_SUPPORT_RATE_DELTA_MAX = 0.01


def projected_own_goal_metrics(
    *,
    initial_tip_xyz_m: Sequence[float] | np.ndarray,
    baseline_tip_xyz_m: np.ndarray,
    alternate_tip_xyz_m: np.ndarray,
    baseline_goal: Mapping[str, Any],
    alternate_goal: Mapping[str, Any],
) -> dict[str, Any]:
    """Measure short-projection direction, ranking, and endpoint separation."""
    initial = _finite_vector(initial_tip_xyz_m, 3, "initial tip")
    baseline = _finite_path(baseline_tip_xyz_m, "baseline tip")
    alternate = _finite_path(alternate_tip_xyz_m, "alternate tip")
    if baseline.shape != alternate.shape:
        raise ValueError("baseline and alternate projected paths must match")
    base_geometry = _goal_geometry(baseline_goal, "baseline goal")
    alternate_geometry = _goal_geometry(alternate_goal, "alternate goal")
    initial_xz = initial[[0, 2]]
    base_result = _own_arm_result(
        initial_xz=initial_xz,
        endpoint_xz=baseline[-1, [0, 2]],
        own_goal=base_geometry,
        other_goal=alternate_geometry,
    )
    alternate_result = _own_arm_result(
        initial_xz=initial_xz,
        endpoint_xz=alternate[-1, [0, 2]],
        own_goal=alternate_geometry,
        other_goal=base_geometry,
    )
    separation = float(np.linalg.norm(alternate[-1, [0, 2]] - baseline[-1, [0, 2]]))
    return {
        "evidence_kind": "short_horizon_projection_only",
        "direction_success": float(
            (base_result["direction_success"] + alternate_result["direction_success"])
            / 2.0
        ),
        "ranking_accuracy": float(
            (base_result["ranking_success"] + alternate_result["ranking_success"]) / 2.0
        ),
        "projected_tip_separation_m": separation,
        "baseline": base_result,
        "alternate": alternate_result,
    }


def hierarchical_paired_source_episode_bootstrap(
    rows: Sequence[Mapping[str, Any]],
    *,
    metrics: Sequence[str],
    resamples: int,
    seed: int,
) -> dict[str, Any]:
    """Bootstrap paired B-A differences with source then episode sampling."""
    if resamples < 100:
        raise ValueError("paired bootstrap requires at least 100 resamples")
    metric_names = tuple(str(name) for name in metrics)
    if not metric_names or len(set(metric_names)) != len(metric_names):
        raise ValueError("paired bootstrap metric names are invalid")
    grouped: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    episode_keys: set[tuple[int, int]] = set()
    for row in rows:
        source = int(row["source_episode_id"])
        episode = int(row["primitive_episode_id"])
        key = (source, episode)
        if key in episode_keys:
            raise ValueError("paired bootstrap has overlapping source/episode rows")
        episode_keys.add(key)
        for strategy in ("legacy", "latest"):
            values = row.get(strategy)
            if not isinstance(values, Mapping):
                raise ValueError(f"paired bootstrap row lacks {strategy} metrics")
            for metric in metric_names:
                value = float(values[metric])
                if not np.isfinite(value):
                    raise ValueError("paired bootstrap metrics must be finite")
        grouped[source].append(row)
    sources = np.asarray(sorted(grouped), dtype=np.int64)
    if sources.size < 2 or not episode_keys:
        raise ValueError("paired bootstrap needs at least two sources")

    differences = {
        metric: {
            source: np.asarray(
                [
                    float(row["latest"][metric]) - float(row["legacy"][metric])
                    for row in grouped[source]
                ],
                dtype=np.float64,
            )
            for source in sources
        }
        for metric in metric_names
    }
    rng = np.random.default_rng(int(seed))
    samples = {
        metric: np.empty(int(resamples), dtype=np.float64) for metric in metric_names
    }
    for sample_index in range(int(resamples)):
        sampled_sources = rng.choice(sources, size=sources.size, replace=True)
        for metric in metric_names:
            source_means = []
            for source_value in sampled_sources:
                source = int(source_value)
                values = differences[metric][source]
                episode_indices = rng.integers(0, values.size, size=values.size)
                source_means.append(float(np.mean(values[episode_indices])))
            samples[metric][sample_index] = float(np.mean(source_means))

    return {
        "schema": "dig_dispatch_paired_source_episode_bootstrap_v1",
        "pairing": "source_then_episode_with_replacement",
        "source_count": int(sources.size),
        "episode_count": len(episode_keys),
        "resamples": int(resamples),
        "seed": int(seed),
        "metrics": {
            metric: {
                "point_difference": float(
                    np.mean(
                        [
                            float(np.mean(differences[metric][int(source)]))
                            for source in sources
                        ]
                    )
                ),
                "ci95_low": float(np.quantile(samples[metric], 0.025)),
                "ci95_high": float(np.quantile(samples[metric], 0.975)),
                "latest_better_confirmed": bool(
                    np.quantile(samples[metric], 0.025) > 0.0
                ),
            }
            for metric in metric_names
        },
    }


def classify_dispatch_diagnostic(
    *,
    pair_metrics: Mapping[str, Any],
    bootstrap: Mapping[str, Any],
    invalid_reasons: Sequence[str],
) -> dict[str, Any]:
    """Apply the sole pre-registered outcome ladder without changing defaults."""
    reasons = tuple(str(reason) for reason in invalid_reasons if str(reason))
    if reasons or not bool(pair_metrics.get("valid", False)):
        classification = "invalid_diagnostic"
        next_experiment = "repair_diagnostic_contract_lineage_or_support"
        gates: dict[str, bool] = {}
    else:
        raw = _mapping(pair_metrics.get("raw_goal_response"), "raw goal response")
        if not bool(raw.get("legacy")) and not bool(raw.get("latest")):
            classification = "goal_condition_response_regressed"
            next_experiment = (
                "repair_goal_condition_response_before_dispatch_comparison"
            )
            gates = {"raw_goal_response_present": False}
        else:
            horizon = _mapping(pair_metrics.get("horizon_10"), "horizon_10")
            legacy = _mapping(horizon.get("legacy"), "legacy horizon metrics")
            latest = _mapping(horizon.get("latest"), "latest horizon metrics")
            boot = _mapping(bootstrap.get("metrics"), "bootstrap metrics")
            direction_gain = float(latest["direction_success"]) - float(
                legacy["direction_success"]
            )
            ranking_gain = float(latest["ranking_accuracy"]) - float(
                legacy["ranking_accuracy"]
            )
            support_delta = float(latest["action_support_violation_rate"]) - float(
                legacy["action_support_violation_rate"]
            )
            gates = {
                "raw_goal_response_present": True,
                "latest_direction_success_at_least_80pct": bool(
                    float(latest["direction_success"]) >= DIRECTION_SUCCESS_MIN
                ),
                "latest_ranking_accuracy_at_least_80pct": bool(
                    float(latest["ranking_accuracy"]) >= RANKING_ACCURACY_MIN
                ),
                "direction_improvement_at_least_15pp": bool(
                    direction_gain >= IMPROVEMENT_MIN
                ),
                "ranking_improvement_at_least_15pp": bool(
                    ranking_gain >= IMPROVEMENT_MIN
                ),
                "latest_tip_separation_p10_at_least_2cm": bool(
                    float(latest["projected_tip_separation_p10_m"])
                    >= TIP_SEPARATION_P10_MIN_M
                ),
                "paired_bootstrap_direction_positive": _bootstrap_positive(
                    boot, "direction_success"
                ),
                "paired_bootstrap_ranking_positive": _bootstrap_positive(
                    boot, "ranking_accuracy"
                ),
                "paired_bootstrap_separation_positive": _bootstrap_positive(
                    boot, "projected_tip_separation_m"
                ),
                "action_support_rate_delta_within_1pp": bool(
                    support_delta <= ACTION_SUPPORT_RATE_DELTA_MAX
                ),
            }
            if all(gates.values()):
                classification = "latest_feedback_dispatch_promising"
                next_experiment = "minimal_unity_single_shovel_dispatch_causal_test"
            else:
                classification = "temporal_dispatch_not_primary"
                next_experiment = "goal_conditioned_act_vs_diffusion_policy"

    return {
        "schema": "dig_act_receding_horizon_dispatch_decision_v1",
        "status": "completed",
        "classification": classification,
        "next_experiment": next_experiment,
        "invalid_reasons": list(reasons),
        "gates": gates,
        "diagnostic_only": True,
        "short_horizon_projection_only": True,
        "production_defaults_changed": False,
        "act_checkpoint_modified": False,
        "act_trained": False,
        "unity_started": False,
        "action_sent": False,
        "promotion_eligible": False,
    }


def _own_arm_result(
    *,
    initial_xz: np.ndarray,
    endpoint_xz: np.ndarray,
    own_goal: Mapping[str, np.ndarray],
    other_goal: Mapping[str, np.ndarray],
) -> dict[str, Any]:
    entry_vector = own_goal["entry"] - initial_xz
    if float(np.linalg.norm(entry_vector)) <= 0.02:
        target_vector = own_goal["exit"] - own_goal["entry"]
        direction_reference = "cut_entry_to_exit"
    else:
        target_vector = entry_vector
        direction_reference = "initial_tip_to_entry"
    displacement = endpoint_xz - initial_xz
    projection = float(np.dot(displacement, target_vector))
    own_distance = float(np.linalg.norm(endpoint_xz - own_goal["entry"]))
    other_distance = float(np.linalg.norm(endpoint_xz - other_goal["entry"]))
    return {
        "direction_success": bool(projection > 0.0),
        "direction_projection_m2": projection,
        "direction_reference": direction_reference,
        "ranking_success": bool(own_distance < other_distance),
        "own_entry_distance_m": own_distance,
        "other_entry_distance_m": other_distance,
        "endpoint_xz_m": endpoint_xz.astype(float).tolist(),
    }


def _goal_geometry(value: Mapping[str, Any], label: str) -> dict[str, np.ndarray]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return {
        "entry": _finite_vector(value.get("entry_xz_m"), 2, f"{label} entry"),
        "exit": _finite_vector(value.get("exit_xz_m"), 2, f"{label} exit"),
    }


def _finite_path(value: np.ndarray, label: str) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64)
    if result.ndim != 2 or result.shape[0] < 1 or result.shape[1] != 3:
        raise ValueError(f"{label} must have shape [steps,3]")
    if not np.isfinite(result).all():
        raise ValueError(f"{label} must be finite")
    return result


def _finite_vector(value: Any, length: int, label: str) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64).reshape(-1)
    if result.shape != (length,) or not np.isfinite(result).all():
        raise ValueError(f"{label} must be finite {length}D")
    return result


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


def _bootstrap_positive(metrics: Mapping[str, Any], name: str) -> bool:
    value = _mapping(metrics.get(name), f"bootstrap {name}")
    return bool(float(value["ci95_low"]) > 0.0)


__all__ = [
    "ACTION_SUPPORT_RATE_DELTA_MAX",
    "DIRECTION_SUCCESS_MIN",
    "IMPROVEMENT_MIN",
    "RANKING_ACCURACY_MIN",
    "TIP_SEPARATION_P10_MIN_M",
    "classify_dispatch_diagnostic",
    "hierarchical_paired_source_episode_bootstrap",
    "projected_own_goal_metrics",
]
