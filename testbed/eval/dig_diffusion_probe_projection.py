"""Frozen 5/10-step OOF projection for DP first-action dispatch replicas."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import torch

from testbed.eval.dig_diffusion_probe_metrics import source_episode_bootstrap_metric
from testbed.eval.dig_receding_horizon_lineage import AuthoritativeDigDispatchLineage
from testbed.eval.dig_receding_horizon_metrics import projected_own_goal_metrics
from testbed.eval.dig_receding_horizon_projection_runtime import (
    build_sliding_projection_windows,
)
from testbed.eval.dig_short_horizon_projection import (
    project_frozen_joint_tip_ensemble,
)
from testbed.policies.dig_effect_fk import (
    DifferentiableFixedTipFK,
    load_fixed_tip_fk_artifact,
)
from testbed.policies.dig_transition_predictor import load_joint_transition_checkpoint


def project_dp_dispatch_replicas(
    *,
    replicas: Sequence[Mapping[str, Any]],
    variants: Sequence[Mapping[str, Any]],
    recorded_qpos: np.ndarray,
    recorded_qvel: np.ndarray,
    lineage: AuthoritativeDigDispatchLineage,
    bootstrap_resamples: int,
    bootstrap_seed: int,
    device: str = "cpu",
) -> dict[str, Any]:
    variant_rows = list(variants)
    qpos = np.asarray(recorded_qpos, dtype=np.float32)
    qvel = np.asarray(recorded_qvel, dtype=np.float32)
    if qpos.shape != (len(variant_rows), 100, 4) or qvel.shape != qpos.shape:
        raise ValueError("DP projection recorded state must be [112,100,4]")
    target_device = torch.device(device)
    fk = DifferentiableFixedTipFK(
        load_fixed_tip_fk_artifact(lineage.fixed_tip_fk.path)
    ).to(target_device)
    fk_validation = fk.validate_fixtures(max_error_m=0.002)
    if not fk_validation["passed"]:
        raise ValueError("DP probe fixed-tip FK validation failed")
    rows = []
    all_h10_separation = []
    fold_records = []
    for fold in lineage.dynamics_folds:
        fold_sources = {int(value) for value in fold["validation_source_episode_ids"]}
        indices = [
            index
            for index, variant in enumerate(variant_rows)
            if int(variant["source_episode_id"]) in fold_sources
        ]
        if not indices:
            continue
        models = [
            load_joint_transition_checkpoint(
                member["checkpoint"]["path"], device=target_device, frozen=True
            )
            for member in fold["members"]
        ]
        fold_qpos = qpos[indices]
        fold_qvel = qvel[indices]
        for replica in replicas:
            base_actions = np.asarray(replica["base_correct"], dtype=np.float32)[
                indices
            ]
            alternate_actions = np.asarray(
                replica["alternate_correct"], dtype=np.float32
            )[indices]
            base_windows = build_sliding_projection_windows(
                recorded_qpos=fold_qpos,
                recorded_qvel=fold_qvel,
                actions=base_actions,
            )
            alternate_windows = build_sliding_projection_windows(
                recorded_qpos=fold_qpos,
                recorded_qvel=fold_qvel,
                actions=alternate_actions,
            )
            base_projection = project_frozen_joint_tip_ensemble(
                models=models,
                fixed_tip_fk=fk,
                initial_qpos=base_windows["initial_qpos"],
                initial_qvel=base_windows["initial_qvel"],
                actions=base_windows["actions"],
                horizons=(5, 10),
                device=target_device,
            )
            alternate_projection = project_frozen_joint_tip_ensemble(
                models=models,
                fixed_tip_fk=fk,
                initial_qpos=alternate_windows["initial_qpos"],
                initial_qvel=alternate_windows["initial_qvel"],
                actions=alternate_windows["actions"],
                horizons=(5, 10),
                device=target_device,
            )
            for local_index, variant_index in enumerate(indices):
                start = local_index * 91
                horizon_metrics = {}
                for horizon in (5, 10):
                    anchor_values = []
                    for anchor in range(91):
                        projection_index = start + anchor
                        anchor_values.append(
                            projected_own_goal_metrics(
                                initial_tip_xyz_m=base_projection["initial_tip_xyz_m"][
                                    projection_index
                                ],
                                baseline_tip_xyz_m=base_projection["tip_xyz_m"][
                                    projection_index, :horizon
                                ],
                                alternate_tip_xyz_m=alternate_projection["tip_xyz_m"][
                                    projection_index, :horizon
                                ],
                                baseline_goal=variant_rows[variant_index]["base_goal"],
                                alternate_goal=variant_rows[variant_index][
                                    "variant_goal"
                                ],
                            )
                        )
                    separation = np.asarray(
                        [value["projected_tip_separation_m"] for value in anchor_values]
                    )
                    horizon_metrics[f"horizon_{horizon}"] = {
                        "direction_success": float(
                            np.mean(
                                [value["direction_success"] for value in anchor_values]
                            )
                        ),
                        "ranking_accuracy": float(
                            np.mean(
                                [value["ranking_accuracy"] for value in anchor_values]
                            )
                        ),
                        "projected_tip_separation_mean_m": float(np.mean(separation)),
                        "projected_tip_separation_p10_m": float(
                            np.quantile(separation, 0.10)
                        ),
                    }
                    if horizon == 10:
                        all_h10_separation.extend(separation.tolist())
                variant = variant_rows[variant_index]
                rows.append(
                    {
                        "training_seed": int(replica["training_seed"]),
                        "inference_noise_seed": int(replica["inference_noise_seed"]),
                        "variant_id": str(variant["variant_id"]),
                        "source_episode_id": int(variant["source_episode_id"]),
                        "primitive_episode_id": int(variant["primitive_episode_id"]),
                        **horizon_metrics,
                    }
                )
        fold_records.append(
            {
                "fold_index": int(fold["fold_index"]),
                "source_episode_ids": sorted(fold_sources),
                "variant_count": len(indices),
                "members": list(fold["members"]),
            }
        )
    expected = len(replicas) * len(variant_rows)
    if len(rows) != expected:
        raise ValueError(
            f"DP projection missed replica/variant rows: {len(rows)}/{expected}"
        )
    episode_rows = _replica_equal_episode_rows(rows)
    direction_bootstrap = source_episode_bootstrap_metric(
        episode_rows,
        key="direction_success",
        resamples=bootstrap_resamples,
        seed=bootstrap_seed,
    )
    ranking_bootstrap = source_episode_bootstrap_metric(
        episode_rows,
        key="ranking_accuracy",
        resamples=bootstrap_resamples,
        seed=bootstrap_seed + 1,
    )
    return {
        "schema": "minimal_dp_short_horizon_projection_v1",
        "evidence_kind": "short_horizon_projection_only",
        "replica_count": len(replicas),
        "variant_count": len(variant_rows),
        "anchor_count_per_replica_variant": 91,
        "direction_success": direction_bootstrap["point"],
        "ranking_accuracy": ranking_bootstrap["point"],
        "projected_tip_separation_p10_m": float(np.quantile(all_h10_separation, 0.10)),
        "projected_tip_separation_mean_m": float(np.mean(all_h10_separation)),
        "bootstrap": {
            "direction": direction_bootstrap,
            "ranking": ranking_bootstrap,
            "joint_margin_ci95_low": min(
                direction_bootstrap["ci95_low"] - 0.80,
                ranking_bootstrap["ci95_low"] - 0.80,
            ),
        },
        "fk_validation": fk_validation,
        "folds": fold_records,
        "rows": rows,
        "failed_100_step_dynamics_used": False,
    }


def _replica_equal_episode_rows(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["variant_id"])].append(row)
    result = []
    for variant_id, values in grouped.items():
        first = values[0]
        result.append(
            {
                "variant_id": variant_id,
                "source_episode_id": int(first["source_episode_id"]),
                "primitive_episode_id": int(first["primitive_episode_id"]),
                "direction_success": float(
                    np.mean(
                        [value["horizon_10"]["direction_success"] for value in values]
                    )
                ),
                "ranking_accuracy": float(
                    np.mean(
                        [value["horizon_10"]["ranking_accuracy"] for value in values]
                    )
                ),
            }
        )
    return result


__all__ = ["project_dp_dispatch_replicas"]
