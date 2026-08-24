"""Source-grouped frozen dynamics execution for Dig dispatch action pairs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import torch

from testbed.eval.dig_receding_horizon_lineage import (
    AuthoritativeDigDispatchLineage,
    DiagnosticLineageError,
)
from testbed.eval.dig_receding_horizon_metrics import projected_own_goal_metrics
from testbed.eval.dig_short_horizon_projection import (
    project_frozen_joint_tip_ensemble,
)
from testbed.policies.dig_effect_fk import (
    DifferentiableFixedTipFK,
    load_fixed_tip_fk_artifact,
)
from testbed.policies.dig_transition_predictor import (
    load_joint_transition_checkpoint,
)


def project_dispatch_pairs(
    pairs: Sequence[Mapping[str, Any]],
    *,
    lineage: AuthoritativeDigDispatchLineage,
    device: str = "cpu",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Attach OOF 5/10-step tip metrics to every paired dispatch record."""
    if not pairs:
        raise ValueError("short projection requires paired actions")
    target_device = torch.device(device)
    fk = DifferentiableFixedTipFK(
        load_fixed_tip_fk_artifact(lineage.fixed_tip_fk.path)
    ).to(target_device)
    fk_validation = fk.validate_fixtures(max_error_m=0.002)
    if not fk_validation["passed"]:
        raise DiagnosticLineageError("fixed_tip_fk_runtime_validation_failed")
    output: dict[str, dict[str, Any]] = {
        paired_projection_key(pair): dict(pair) for pair in pairs
    }
    if len(output) != len(pairs):
        raise DiagnosticLineageError("paired_projection_identity_not_unique")
    projected_ids: set[str] = set()
    fold_lineage = []
    for fold in lineage.dynamics_folds:
        source_ids = {
            int(value) for value in fold["validation_source_episode_ids"]
        } & set(lineage.dynamics_eligible_source_ids)
        fold_pairs = [
            pair for pair in pairs if int(pair["source_episode_id"]) in source_ids
        ]
        if not fold_pairs:
            continue
        models = []
        for member in fold["members"]:
            model = load_joint_transition_checkpoint(
                member["checkpoint"]["path"],
                device=target_device,
                frozen=True,
            )
            if model.training or any(
                parameter.requires_grad for parameter in model.parameters()
            ):
                raise RuntimeError("loaded short dynamics member is not frozen")
            models.append(model)
        recorded_qpos = np.stack(
            [np.asarray(pair["recorded_qpos"], dtype=np.float32) for pair in fold_pairs]
        )
        recorded_qvel = np.stack(
            [np.asarray(pair["recorded_qvel"], dtype=np.float32) for pair in fold_pairs]
        )
        projections: dict[str, dict[str, dict[str, Any]]] = {}
        for strategy in ("legacy", "latest"):
            projections[strategy] = {}
            for arm in ("baseline", "alternate"):
                actions = np.stack(
                    [
                        np.asarray(pair["actions"][strategy][arm], dtype=np.float32)
                        for pair in fold_pairs
                    ]
                )
                windows = build_sliding_projection_windows(
                    recorded_qpos=recorded_qpos,
                    recorded_qvel=recorded_qvel,
                    actions=actions,
                )
                projections[strategy][arm] = {
                    "windows": windows,
                    "result": project_frozen_joint_tip_ensemble(
                        models=models,
                        fixed_tip_fk=fk,
                        initial_qpos=windows["initial_qpos"],
                        initial_qvel=windows["initial_qvel"],
                        actions=windows["actions"],
                        horizons=(5, 10),
                        device=target_device,
                    ),
                }
        for pair_index, pair in enumerate(fold_pairs):
            pair_key = paired_projection_key(pair)
            if pair_key in projected_ids:
                raise DiagnosticLineageError("pair_projected_by_multiple_folds")
            projected_ids.add(pair_key)
            result = output[pair_key]
            result["projection"] = {
                "evidence_kind": "short_horizon_projection_only",
                "fold_index": int(fold["fold_index"]),
                "model_count": len(models),
                "recorded_state_anchor_count": 91,
                "horizons": {},
            }
            for strategy in ("legacy", "latest"):
                base_projection = projections[strategy]["baseline"]["result"]
                alternate_projection = projections[strategy]["alternate"]["result"]
                start = pair_index * 91
                for horizon in (5, 10):
                    horizon_key = f"horizon_{horizon}"
                    result["projection"]["horizons"].setdefault(horizon_key, {})
                    anchor_metrics = []
                    for anchor_frame in range(91):
                        projection_index = start + anchor_frame
                        metric = projected_own_goal_metrics(
                            initial_tip_xyz_m=base_projection["initial_tip_xyz_m"][
                                projection_index
                            ],
                            baseline_tip_xyz_m=base_projection["tip_xyz_m"][
                                projection_index, :horizon
                            ],
                            alternate_tip_xyz_m=alternate_projection["tip_xyz_m"][
                                projection_index, :horizon
                            ],
                            baseline_goal=pair["goals"]["baseline"],
                            alternate_goal=pair["goals"]["alternate"],
                        )
                        anchor_metrics.append(
                            {
                                "anchor_frame_index": anchor_frame,
                                "direction_success": metric["direction_success"],
                                "ranking_accuracy": metric["ranking_accuracy"],
                                "projected_tip_separation_m": metric[
                                    "projected_tip_separation_m"
                                ],
                                "baseline_direction_success": metric["baseline"][
                                    "direction_success"
                                ],
                                "alternate_direction_success": metric["alternate"][
                                    "direction_success"
                                ],
                                "baseline_ranking_success": metric["baseline"][
                                    "ranking_success"
                                ],
                                "alternate_ranking_success": metric["alternate"][
                                    "ranking_success"
                                ],
                            }
                        )
                    separations = np.asarray(
                        [
                            value["projected_tip_separation_m"]
                            for value in anchor_metrics
                        ],
                        dtype=np.float64,
                    )
                    result["projection"]["horizons"][horizon_key][strategy] = {
                        "evidence_kind": "short_horizon_projection_only",
                        "anchor_count": len(anchor_metrics),
                        "direction_success": float(
                            np.mean(
                                [value["direction_success"] for value in anchor_metrics]
                            )
                        ),
                        "ranking_accuracy": float(
                            np.mean(
                                [value["ranking_accuracy"] for value in anchor_metrics]
                            )
                        ),
                        "projected_tip_separation_m": float(np.mean(separations)),
                        "projected_tip_separation_p10_m": float(
                            np.quantile(separations, 0.10)
                        ),
                        "anchors": anchor_metrics,
                    }
            result["action_separation"] = {
                strategy: _action_separation(result["actions"][strategy])
                for strategy in ("legacy", "latest")
            }
        fold_lineage.append(
            {
                "fold_index": int(fold["fold_index"]),
                "source_episode_ids": sorted(source_ids),
                "variant_count": len(fold_pairs),
                "members": list(fold["members"]),
            }
        )
        del models
    expected_ids = {paired_projection_key(pair) for pair in pairs}
    if projected_ids != expected_ids:
        missing = sorted(expected_ids - projected_ids)
        raise DiagnosticLineageError(f"variants_missing_oof_projection:{missing}")
    return [output[paired_projection_key(pair)] for pair in pairs], {
        "schema": "dig_short_horizon_projection_runtime_v1",
        "evidence_kind": "short_horizon_projection_only",
        "horizons": [5, 10],
        "long_horizon_100_step_used": False,
        "fk_validation": fk_validation,
        "folds": fold_lineage,
        "optimizer_created": False,
        "backward_called": False,
        "parameters_modified": False,
    }


def _action_separation(value: Mapping[str, Any]) -> dict[str, Any]:
    baseline = np.asarray(value["baseline"], dtype=np.float64)
    alternate = np.asarray(value["alternate"], dtype=np.float64)
    if baseline.shape != (100, 4) or alternate.shape != baseline.shape:
        raise ValueError("paired diagnostic actions must each be [100,4]")
    norms = np.linalg.norm(alternate - baseline, axis=1)
    return {
        "per_frame_l2": norms.tolist(),
        "horizon_5_mean_l2": float(np.mean(norms)),
        "horizon_10_mean_l2": float(np.mean(norms)),
        "full_100_mean_l2": float(np.mean(norms)),
        "horizon_10_p10_l2": float(np.quantile(norms, 0.10)),
        "horizon_10_median_l2": float(np.median(norms)),
    }


def build_sliding_projection_windows(
    *,
    recorded_qpos: np.ndarray,
    recorded_qvel: np.ndarray,
    actions: np.ndarray,
) -> dict[str, np.ndarray]:
    """Build 91 ten-step projections, each anchored to its recorded state."""
    qpos = np.asarray(recorded_qpos, dtype=np.float32)
    qvel = np.asarray(recorded_qvel, dtype=np.float32)
    action_values = np.asarray(actions, dtype=np.float32)
    if (
        qpos.ndim != 3
        or qpos.shape[1:] != (100, 4)
        or qvel.shape != qpos.shape
        or action_values.shape != qpos.shape
        or not np.isfinite(qpos).all()
        or not np.isfinite(qvel).all()
        or not np.isfinite(action_values).all()
    ):
        raise ValueError("sliding projection inputs must be finite [batch,100,4]")
    owner_indices = []
    anchor_indices = []
    initial_qpos = []
    initial_qvel = []
    action_windows = []
    for owner in range(qpos.shape[0]):
        for anchor in range(91):
            owner_indices.append(owner)
            anchor_indices.append(anchor)
            initial_qpos.append(qpos[owner, anchor])
            initial_qvel.append(qvel[owner, anchor])
            action_windows.append(action_values[owner, anchor : anchor + 10])
    return {
        "initial_qpos": np.stack(initial_qpos),
        "initial_qvel": np.stack(initial_qvel),
        "actions": np.stack(action_windows),
        "owner_index": np.asarray(owner_indices, dtype=np.int32),
        "anchor_frame_index": np.asarray(anchor_indices, dtype=np.int32),
    }


def paired_projection_key(value: Mapping[str, Any]) -> str:
    """Bind a token variant to its source and primitive episode identity."""
    return (
        f"{int(value['source_episode_id'])}:"
        f"{int(value['primitive_episode_id'])}:"
        f"{str(value['variant_id'])}"
    )


__all__ = [
    "build_sliding_projection_windows",
    "paired_projection_key",
    "project_dispatch_pairs",
]
