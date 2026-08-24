"""Fail-closed lineage resolution for the Dig dispatch diagnostic."""

from __future__ import annotations

import hashlib
import json
import pickle
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from testbed.data.operator_first_v2_2 import (
    DIG_CUT_DEPTH_SCALE_M,
    DIG_CUT_LENGTH_SCALE_M,
    DIG_CUT_POSITION_SCALE_M,
    DIG_CUT_TOKEN_DIM,
)


class DiagnosticLineageError(ValueError):
    """Raised when a required formal artifact cannot be bound exactly."""


@dataclass(frozen=True)
class FileIdentity:
    path: Path
    sha256: str
    size_bytes: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "sha256": self.sha256,
            "size_bytes": int(self.size_bytes),
        }


@dataclass(frozen=True)
class AuthoritativeDigDispatchLineage:
    checkpoint: FileIdentity
    stats: FileIdentity
    support: FileIdentity
    variant_manifest: FileIdentity
    variant_jsonl: FileIdentity
    split: FileIdentity
    resolved_config: FileIdentity
    run_metadata: FileIdentity
    token_prior: FileIdentity
    fixed_tip_fk: FileIdentity
    curriculum_artifact: FileIdentity
    comparison_artifact: FileIdentity
    reanchor_artifact: FileIdentity
    internal_support_contract: FileIdentity
    dataset_dir: Path
    low_dim_order: tuple[str, ...]
    camera_order: tuple[str, ...]
    token_order: tuple[str, ...]
    valid_cell_ids: tuple[int, ...]
    support_feature_order: tuple[str, ...]
    support_p01: np.ndarray
    support_p99: np.ndarray
    action_p01: np.ndarray
    action_p99: np.ndarray
    train_source_episode_ids: tuple[int, ...]
    validation_source_episode_ids: tuple[int, ...]
    dynamics_eligible_source_ids: tuple[int, ...]
    dynamics_folds: tuple[dict[str, Any], ...]
    short_horizon_gate: dict[str, Any]
    resolved_training_config: dict[str, Any]

    def as_manifest(self) -> dict[str, Any]:
        identities = {
            name: getattr(self, name).as_dict()
            for name in (
                "checkpoint",
                "stats",
                "support",
                "variant_manifest",
                "variant_jsonl",
                "split",
                "resolved_config",
                "run_metadata",
                "token_prior",
                "fixed_tip_fk",
                "curriculum_artifact",
                "comparison_artifact",
                "reanchor_artifact",
                "internal_support_contract",
            )
        }
        return {
            "status": "complete",
            "files": identities,
            "dataset_dir": str(self.dataset_dir),
            "orders": {
                "low_dim": list(self.low_dim_order),
                "camera": list(self.camera_order),
                "token": list(self.token_order),
                "support_feature": list(self.support_feature_order),
                "low_dim_sha256": _sha256_json(list(self.low_dim_order)),
                "camera_sha256": _sha256_json(list(self.camera_order)),
                "token_sha256": _sha256_json(list(self.token_order)),
            },
            "support": {
                "p01": self.support_p01.astype(float).tolist(),
                "p99": self.support_p99.astype(float).tolist(),
                "action_p01": self.action_p01.astype(float).tolist(),
                "action_p99": self.action_p99.astype(float).tolist(),
            },
            "sources": {
                "strict_train": list(self.train_source_episode_ids),
                "historical_validation_not_used": list(
                    self.validation_source_episode_ids
                ),
                "short_dynamics_eligible": list(self.dynamics_eligible_source_ids),
            },
            "valid_cell_ids": list(self.valid_cell_ids),
            "dynamics_folds": list(self.dynamics_folds),
            "short_horizon_gate": dict(self.short_horizon_gate),
        }


def require_complete_lineage(value: Mapping[str, Any]) -> None:
    """Reject an assembled run manifest if a required lock is absent."""
    for key in ("checkpoint", "stats", "support"):
        record = value.get(key)
        if not isinstance(record, Mapping):
            raise DiagnosticLineageError(f"{key}_missing")
        if not str(record.get("path", "")) or not _is_sha256(record.get("sha256")):
            raise DiagnosticLineageError(f"{key}_lineage_invalid")
    orders = {
        "token_order": 10,
        "observation_order": 1,
        "camera_order": 1,
    }
    for key, minimum in orders.items():
        order = value.get(key)
        if not isinstance(order, Sequence) or isinstance(order, (str, bytes)):
            raise DiagnosticLineageError(f"{key}_missing")
        if len(order) < minimum or any(not str(item) for item in order):
            raise DiagnosticLineageError(f"{key}_missing")
    if not _is_sha256(value.get("state_lineage_sha256")):
        raise DiagnosticLineageError("state_lineage_missing")


def resolve_authoritative_lineage(
    *,
    reanchor_decision_path: str | Path,
    structure_decision_path: str | Path,
    comparison_artifact_path: str | Path,
) -> AuthoritativeDigDispatchLineage:
    """Resolve every runtime input by following the supplied formal artifacts."""
    reanchor_decision_file = _path(reanchor_decision_path)
    structure_decision_file = _path(structure_decision_path)
    comparison_file = _path(comparison_artifact_path)
    reanchor_decision = _json(reanchor_decision_file)
    structure_decision = _json(structure_decision_file)
    comparison = _json(comparison_file)
    _require_schema(
        reanchor_decision,
        "bucket_reanchor_route_decision_v1",
        "reanchor decision",
    )
    _require_schema(
        structure_decision,
        "dig_trajectory_structure_route_decision_v1",
        "structure decision",
    )
    _require_schema(
        comparison,
        "bucket_finite_history_input_comparison_v1",
        "comparison artifact",
    )
    if not bool(structure_decision.get("offline_physical_constraint_branch_stopped")):
        raise DiagnosticLineageError("failed_100_step_predictor_branch_not_stopped")

    comparison_identity = _identity(comparison_file)
    reanchor_artifact_file = _path(reanchor_decision_file.parent / "artifact.json")
    reanchor_artifact = _json(reanchor_artifact_file)
    _require_schema(
        reanchor_artifact,
        "bucket_periodic_true_state_reanchor_eval_v1",
        "reanchor artifact",
    )
    if reanchor_artifact.get("decision") != reanchor_decision:
        raise DiagnosticLineageError("reanchor_decision_embedding_mismatch")
    _require_record_identity(
        reanchor_artifact["inputs"]["bucket_comparison_artifact"],
        comparison_identity,
        "reanchor comparison",
    )

    experiment_root, experiment_manifest = _find_experiment_root(comparison_file)
    formal_decision_identity = _identity_from_record(
        experiment_manifest["authoritative"]["decision"],
        "experiment authoritative decision",
    )
    formal_decision = _json(formal_decision_identity.path)
    lineage = _mapping(formal_decision.get("lineage"), "formal ACT lineage")
    checkpoint = _identity_from_record(lineage.get("checkpoint"), "ACT checkpoint")
    stats = _identity_from_record(lineage.get("stats"), "ACT dataset stats")
    variant_manifest_identity = _identity_from_record(
        lineage.get("variant_manifest"), "planner variant manifest"
    )
    variant_manifest = _json(variant_manifest_identity.path)
    _require_schema(
        variant_manifest,
        "planner_reachable_dig_variant_set_v1",
        "planner variant manifest",
    )
    train_partition = _mapping(
        variant_manifest.get("partitions", {}).get("train"), "train variants"
    )
    train_sources = tuple(int(value) for value in train_partition["source_episode_ids"])
    if 33 in train_sources or 34 in train_sources:
        raise DiagnosticLineageError("source_33_34_present_in_train_variants")
    variant_jsonl = _identity(_path(train_partition["path"]))

    support = _identity(_path(variant_manifest["support_path"]))
    support_payload = _json(support.path)
    _require_schema(
        support_payload,
        "act_goal_condition_sensitivity_primitive_v1",
        "strict-train support",
    )
    support_contract = _mapping(
        support_payload.get("applied_support_contract"), "support contract"
    )
    numeric_support = _mapping(
        support_payload.get("numeric_support"), "numeric support"
    )
    feature_order = tuple(str(value) for value in support_contract["feature_order"])
    expected_features = tuple(
        [f"qpos[{index}]" for index in range(4)]
        + [f"qvel[{index}]" for index in range(4)]
        + [f"dig_cut_tokens[{index}]" for index in range(10)]
    )
    if feature_order != expected_features:
        raise DiagnosticLineageError("support_feature_order_mismatch")
    support_p01 = _finite_vector(numeric_support.get("p01"), 18, "support p01")
    support_p99 = _finite_vector(numeric_support.get("p99"), 18, "support p99")
    if np.any(support_p01 > support_p99):
        raise DiagnosticLineageError("support_bounds_invalid")

    prior = _identity(_path(variant_manifest["prior_path"]))
    prior_payload = _json(prior.path)
    token_order = tuple(str(value) for value in prior_payload.get("token_order", ()))
    if len(token_order) != DIG_CUT_TOKEN_DIM or len(set(token_order)) != len(
        token_order
    ):
        raise DiagnosticLineageError("token_order_missing")
    valid_cell_ids = tuple(
        sorted(int(value["cell_id"]) for value in prior_payload["coverage_cells"])
    )
    if not valid_cell_ids or len(set(valid_cell_ids)) != len(valid_cell_ids):
        raise DiagnosticLineageError("valid_cell_contract_missing")

    run_metadata = _identity(_path(checkpoint.path.parent / "run_metadata.json"))
    metadata = _json(run_metadata.path)
    metadata_paths = _mapping(metadata.get("paths"), "training metadata paths")
    if _path(metadata_paths["dataset_stats"]) != stats.path:
        raise DiagnosticLineageError("stats_path_disagrees_with_training_metadata")
    resolved_config = _identity(_path(metadata_paths["resolved_config"]))
    config_payload = _mapping(
        yaml.safe_load(resolved_config.path.read_text(encoding="utf-8")),
        "resolved training config",
    )
    task_config = _mapping(config_payload.get("task"), "resolved task config")
    policy_config = _mapping(config_payload.get("policy"), "resolved policy config")
    low_dim_order = tuple(str(value) for value in policy_config["low_dim_keys"])
    camera_order = tuple(str(value) for value in task_config["camera_names"])
    if low_dim_order != ("qpos", "qvel", "dig_cut_tokens"):
        raise DiagnosticLineageError("observation_order_mismatch")
    if not camera_order or len(set(camera_order)) != len(camera_order):
        raise DiagnosticLineageError("camera_order_missing")
    with stats.path.open("rb") as handle:
        stats_payload = pickle.load(handle)
    stats_keys = tuple(str(value) for value in stats_payload.get("proprio_keys", ()))
    if stats_keys != low_dim_order:
        raise DiagnosticLineageError("stats_observation_order_mismatch")

    split = _identity(_path(metadata_paths["train_val_split"]))
    if split.path != _path(variant_manifest["split_path"]):
        raise DiagnosticLineageError("variant_split_path_mismatch")
    dataset_dir = _path(metadata_paths["dataset_dir"])
    if dataset_dir != _path(task_config["dataset_dir"]):
        raise DiagnosticLineageError("dataset_path_mismatch")

    fixed_tip_fk = _identity_from_record(
        comparison["inputs"]["fixed_tip_fk_artifact"], "fixed-tip FK"
    )
    curriculum = _identity_from_record(
        comparison["inputs"]["frozen_curriculum_artifact"],
        "frozen joint dynamics",
    )
    curriculum_payload = _json(curriculum.path)
    _require_schema(
        curriculum_payload,
        "dig_closed_loop_rollout_curriculum_v1",
        "frozen joint dynamics",
    )
    dynamics_folds = _resolve_dynamics_folds(comparison, curriculum_payload)

    internal_artifact = _identity_from_record(
        reanchor_artifact["inputs"]["internal_support_artifact"],
        "internal dynamics support artifact",
    )
    internal_contract = _identity(
        _path(internal_artifact.path.parent / "contract.json")
    )
    internal_payload = _json(internal_contract.path)
    _require_schema(
        internal_payload,
        "bucket_internal_support_eval_contract_v1",
        "internal dynamics support contract",
        allow_frozen_status=True,
    )
    support_bounds = _mapping(
        internal_payload["real_data_selection"]["support_bounds"],
        "action support bounds",
    )
    action_p01 = _finite_vector(support_bounds["action_p01"], 4, "action p01")
    action_p99 = _finite_vector(support_bounds["action_p99"], 4, "action p99")
    if np.any(action_p01 > action_p99):
        raise DiagnosticLineageError("action_support_bounds_invalid")

    coverage = _mapping(reanchor_artifact.get("coverage"), "reanchor coverage")
    retained = _mapping(coverage.get("retained_by_source"), "reanchor source coverage")
    dynamics_sources = tuple(
        sorted(
            int(source)
            for source, values in retained.items()
            if int(values.get("episode_count", 0)) > 0
            and int(values.get("window_count", 0)) > 0
            and int(source) not in (33, 34)
        )
    )
    short_gate = _short_horizon_gate(
        reanchor_decision=reanchor_decision,
        comparison=comparison,
        curriculum=curriculum_payload,
        dynamics_sources=dynamics_sources,
        train_sources=train_sources,
    )
    validation_sources = tuple(
        int(value) for value in support_contract["validation_source_episode_ids"]
    )
    if set(validation_sources) != {33, 34}:
        raise DiagnosticLineageError("historical_validation_source_contract_drift")

    return AuthoritativeDigDispatchLineage(
        checkpoint=checkpoint,
        stats=stats,
        support=support,
        variant_manifest=variant_manifest_identity,
        variant_jsonl=variant_jsonl,
        split=split,
        resolved_config=resolved_config,
        run_metadata=run_metadata,
        token_prior=prior,
        fixed_tip_fk=fixed_tip_fk,
        curriculum_artifact=curriculum,
        comparison_artifact=comparison_identity,
        reanchor_artifact=_identity(reanchor_artifact_file),
        internal_support_contract=internal_contract,
        dataset_dir=dataset_dir,
        low_dim_order=low_dim_order,
        camera_order=camera_order,
        token_order=token_order,
        valid_cell_ids=valid_cell_ids,
        support_feature_order=feature_order,
        support_p01=support_p01,
        support_p99=support_p99,
        action_p01=action_p01,
        action_p99=action_p99,
        train_source_episode_ids=tuple(
            int(value) for value in support_contract["train_source_episode_ids"]
        ),
        validation_source_episode_ids=validation_sources,
        dynamics_eligible_source_ids=dynamics_sources,
        dynamics_folds=dynamics_folds,
        short_horizon_gate=short_gate,
        resolved_training_config=dict(config_payload),
    )


def select_source_episode_balanced_variants(
    records: Sequence[Mapping[str, Any]],
    *,
    count: int,
    eligible_source_ids: Sequence[int] | None = None,
    minimum_episodes_per_source: int = 1,
) -> list[dict[str, Any]]:
    """Select one fixed position variant per episode in source round-robin order."""
    if count < 1:
        raise ValueError("variant count must be positive")
    if minimum_episodes_per_source < 1:
        raise ValueError("minimum episodes per source must be positive")
    eligible = (
        None if eligible_source_ids is None else {int(v) for v in eligible_source_ids}
    )
    by_source_episode: dict[int, dict[int, dict[str, Any]]] = defaultdict(dict)
    ordered = sorted(
        (dict(value) for value in records),
        key=lambda value: (
            int(value["source_episode_id"]),
            int(value["primitive_episode_id"]),
            str(value["variant_id"]),
        ),
    )
    for value in ordered:
        source = int(value["source_episode_id"])
        episode = int(value["primitive_episode_id"])
        if source in (33, 34) or (eligible is not None and source not in eligible):
            continue
        if value.get("variant_type") != "position_translation":
            continue
        by_source_episode[source].setdefault(episode, value)
    queues = {
        source: [episodes[key] for key in sorted(episodes)]
        for source, episodes in sorted(by_source_episode.items())
        if len(episodes) >= minimum_episodes_per_source
    }
    selected: list[dict[str, Any]] = []
    offset = 0
    while len(selected) < count:
        progressed = False
        for source in sorted(queues):
            if offset < len(queues[source]):
                selected.append(queues[source][offset])
                progressed = True
                if len(selected) == count:
                    break
        if not progressed:
            raise DiagnosticLineageError(
                f"planner_reachable_variant_count_insufficient:{len(selected)}/{count}"
            )
        offset += 1
    return selected


def validate_planner_variant(
    value: Mapping[str, Any],
    *,
    qpos: np.ndarray,
    qvel: np.ndarray,
    support_p01: Sequence[float] | np.ndarray,
    support_p99: Sequence[float] | np.ndarray,
    valid_cell_ids: set[int] | Sequence[int],
) -> dict[str, Any]:
    """Recheck the formal 18D, geometry, and cell contracts on used frames."""
    reasons: list[str] = []
    if value.get("schema") != "planner_reachable_dig_variant_v1":
        reasons.append("variant_schema_mismatch")
    positions = _finite_matrix(qpos, 4, "variant qpos")
    velocities = _finite_matrix(qvel, 4, "variant qvel")
    if positions.shape != velocities.shape:
        raise ValueError("variant qpos/qvel frame shapes differ")
    base_token = _finite_vector(value.get("base_token"), 10, "base token")
    variant_token = _finite_vector(value.get("variant_token"), 10, "variant token")
    lower = _finite_vector(support_p01, 18, "support p01")
    upper = _finite_vector(support_p99, 18, "support p99")
    base_features = np.concatenate(
        (positions, velocities, np.repeat(base_token[None], len(positions), axis=0)),
        axis=1,
    )
    variant_features = np.concatenate(
        (positions, velocities, np.repeat(variant_token[None], len(positions), axis=0)),
        axis=1,
    )
    support_ok = bool(
        np.all(base_features >= lower - 1.0e-8)
        and np.all(base_features <= upper + 1.0e-8)
        and np.all(variant_features >= lower - 1.0e-8)
        and np.all(variant_features <= upper + 1.0e-8)
    )
    if not support_ok:
        reasons.append("full_18d_support_failed")

    base_goal = _mapping(value.get("base_goal"), "base goal")
    variant_goal = _mapping(value.get("variant_goal"), "variant goal")
    base_geometry = _token_matches_goal(base_token, base_goal)
    variant_geometry = _token_matches_goal(variant_token, variant_goal)
    geometry_ok = bool(base_geometry and variant_geometry)
    if value.get("variant_type") == "position_translation":
        base_entry = _finite_vector(base_goal["entry_xz_m"], 2, "base entry")
        base_exit = _finite_vector(base_goal["exit_xz_m"], 2, "base exit")
        alternate_entry = _finite_vector(variant_goal["entry_xz_m"], 2, "variant entry")
        alternate_exit = _finite_vector(variant_goal["exit_xz_m"], 2, "variant exit")
        geometry_ok = bool(
            geometry_ok
            and np.allclose(
                alternate_entry - base_entry,
                alternate_exit - base_exit,
                rtol=0.0,
                atol=1.0e-6,
            )
            and np.allclose(base_token[4:], variant_token[4:], rtol=0.0, atol=1.0e-6)
        )
    if not geometry_ok:
        reasons.append("geometry_self_consistency_failed")

    cells = {int(item) for item in valid_cell_ids}
    target_cell = int(value.get("target_cell_id", -1))
    variant_cell = int(variant_goal.get("target_cell_id", -1))
    cell_ok = bool(target_cell in cells and variant_cell == target_cell)
    if not cell_ok:
        reasons.append("valid_cell_failed")
    return {
        "valid": not reasons,
        "reasons": reasons,
        "full_18d_support": support_ok,
        "geometry_self_consistent": geometry_ok,
        "valid_cell": cell_ok,
        "frame_count": int(positions.shape[0]),
    }


def _token_matches_goal(token: np.ndarray, goal: Mapping[str, Any]) -> bool:
    entry = _finite_vector(goal["entry_xz_m"], 2, "goal entry")
    exit_ = _finite_vector(goal["exit_xz_m"], 2, "goal exit")
    direction = _finite_vector(goal["direction_xz"], 2, "goal direction")
    cut = exit_ - entry
    length = float(np.linalg.norm(cut))
    if length <= 1.0e-8:
        return False
    checks = [
        np.allclose(token[:2] * DIG_CUT_POSITION_SCALE_M, entry, atol=1.0e-6),
        np.allclose(token[2:4] * DIG_CUT_POSITION_SCALE_M, exit_, atol=1.0e-6),
        np.allclose(token[4:6], direction, atol=1.0e-6),
        np.allclose(token[4:6], cut / length, atol=1.0e-6),
        np.isclose(token[6] * DIG_CUT_LENGTH_SCALE_M, length, atol=1.0e-6),
        bool(token[9] > 0.5),
    ]
    if "planned_depth_m" in goal:
        checks.append(
            np.isclose(
                token[7] * DIG_CUT_DEPTH_SCALE_M,
                float(goal["planned_depth_m"]),
                atol=1.0e-6,
            )
        )
    return bool(all(checks))


def _resolve_dynamics_folds(
    comparison: Mapping[str, Any], curriculum: Mapping[str, Any]
) -> tuple[dict[str, Any], ...]:
    curriculum_by_fold = {
        int(value["fold_index"]): value for value in curriculum["folds"]
    }
    result = []
    for fold in comparison["folds"]:
        fold_index = int(fold["fold_index"])
        sources = tuple(int(value) for value in fold["validation_source_episode_ids"])
        if sources != tuple(
            int(value)
            for value in curriculum_by_fold[fold_index]["validation_source_episode_ids"]
        ):
            raise DiagnosticLineageError("dynamics_fold_source_mismatch")
        members = []
        for member in fold["frozen_base_members"]:
            identity = _identity_from_record(
                {
                    "path": member["checkpoint_path"],
                    "sha256": member["checkpoint_sha256"],
                },
                "joint dynamics checkpoint",
            )
            members.append(
                {
                    "seed": int(member["seed"]),
                    "checkpoint": identity.as_dict(),
                    "eval_mode": True,
                    "parameters_require_grad": False,
                }
            )
        result.append(
            {
                "fold_index": fold_index,
                "validation_source_episode_ids": list(sources),
                "members": members,
            }
        )
    return tuple(result)


def _short_horizon_gate(
    *,
    reanchor_decision: Mapping[str, Any],
    comparison: Mapping[str, Any],
    curriculum: Mapping[str, Any],
    dynamics_sources: tuple[int, ...],
    train_sources: tuple[int, ...],
) -> dict[str, Any]:
    passing = {int(value) for value in reanchor_decision["passing_anchor_intervals"]}
    worst = {
        int(key): float(value)
        for key, value in reanchor_decision[
            "worst_source_endpoint_by_anchor_interval_m"
        ].items()
    }
    endpoint_gate = float(reanchor_decision["endpoint_gate_m"])
    fk_passed = bool(comparison.get("fk_validation", {}).get("passed"))
    curriculum_metrics = _mapping(
        curriculum.get("curriculum_metrics"), "curriculum metrics"
    )
    scoped_errors: dict[int, dict[int, float]] = {}
    for horizon in (5, 10):
        metric = _mapping(
            curriculum_metrics.get(f"tip_error_h{horizon}_m"),
            f"curriculum tip h{horizon}",
        )
        by_source = _mapping(metric.get("by_source"), f"curriculum h{horizon} source")
        scoped_errors[horizon] = {
            source: float(by_source[str(source)]) for source in dynamics_sources
        }
    base_h5_worst = max(scoped_errors[5].values())
    base_h10_worst = max(scoped_errors[10].values())
    return {
        "schema": "dig_short_horizon_projection_gate_v1",
        "horizon_5_passed": bool(
            fk_passed
            and base_h5_worst <= endpoint_gate
            and 5 in passing
            and worst[5] <= endpoint_gate
        ),
        "horizon_10_passed": bool(
            fk_passed
            and base_h10_worst <= endpoint_gate
            and 10 in passing
            and worst[10] <= endpoint_gate
        ),
        "projection_model": "source_grouped_curriculum_base_ensemble",
        "projection_model_worst_source_h5_m": base_h5_worst,
        "projection_model_worst_source_h10_m": base_h10_worst,
        "reanchor_corroboration_worst_source_h5_m": worst[5],
        "reanchor_corroboration_worst_source_h10_m": worst[10],
        "endpoint_gate_m": endpoint_gate,
        "fixed_tip_fk_passed": fk_passed,
        "projection_scope_source_ids": list(dynamics_sources),
        "excluded_unsupported_source_ids": sorted(
            set(train_sources) - set(dynamics_sources)
        ),
        "historical_overall_coverage_gate_passed": bool(
            reanchor_decision.get("coverage_gate_passed")
        ),
        "scope_limited_to_sources_with_retained_real_support": True,
        "long_horizon_evidence_allowed": False,
    }


def _find_experiment_root(path: Path) -> tuple[Path, dict[str, Any]]:
    for parent in path.parents:
        candidate = parent / "experiment_manifest.json"
        if candidate.is_file():
            payload = _json(candidate)
            if (
                payload.get("schema")
                == "dig_token_swap_effect_consistency_experiment_v1"
            ):
                return parent, payload
    raise DiagnosticLineageError("authoritative_experiment_manifest_missing")


def _require_record_identity(
    record: Mapping[str, Any], actual: FileIdentity, label: str
) -> None:
    expected = _identity_from_record(record, label)
    if expected != actual:
        raise DiagnosticLineageError(f"{label.replace(' ', '_')}_identity_mismatch")


def _identity_from_record(value: Any, label: str) -> FileIdentity:
    record = _mapping(value, label)
    path = _path(record.get("path"))
    actual = _identity(path)
    expected_sha = str(record.get("sha256", ""))
    if not _is_sha256(expected_sha) or actual.sha256 != expected_sha:
        raise DiagnosticLineageError(f"{label.replace(' ', '_')}_sha256_mismatch")
    if "size_bytes" in record and int(record["size_bytes"]) != actual.size_bytes:
        raise DiagnosticLineageError(f"{label.replace(' ', '_')}_size_mismatch")
    return actual


def _identity(path: Path) -> FileIdentity:
    if not path.is_file():
        raise DiagnosticLineageError(f"lineage_file_missing:{path}")
    return FileIdentity(
        path=path, sha256=_sha256_file(path), size_bytes=path.stat().st_size
    )


def _path(value: Any) -> Path:
    text = str(value or "").strip()
    if not text:
        raise DiagnosticLineageError("lineage_path_missing")
    try:
        return Path(text).expanduser().resolve(strict=True)
    except FileNotFoundError as exc:
        raise DiagnosticLineageError(f"lineage_path_missing:{text}") from exc


def _json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return dict(_mapping(payload, str(path)))


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DiagnosticLineageError(f"{label.replace(' ', '_')}_missing")
    return value


def _require_schema(
    value: Mapping[str, Any],
    schema: str,
    label: str,
    *,
    allow_frozen_status: bool = False,
) -> None:
    if value.get("schema") != schema:
        raise DiagnosticLineageError(f"{label.replace(' ', '_')}_schema_mismatch")
    allowed = (
        {"completed", "frozen_before_model_inference"}
        if allow_frozen_status
        else {"completed"}
    )
    if value.get("status") not in allowed:
        raise DiagnosticLineageError(f"{label.replace(' ', '_')}_status_invalid")


def _finite_vector(value: Any, length: int, label: str) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64).reshape(-1)
    if result.shape != (length,) or not np.isfinite(result).all():
        raise DiagnosticLineageError(f"{label.replace(' ', '_')}_invalid")
    return result


def _finite_matrix(value: Any, width: int, label: str) -> np.ndarray:
    result = np.asarray(value, dtype=np.float64)
    if result.ndim != 2 or result.shape[1] != width or not np.isfinite(result).all():
        raise DiagnosticLineageError(f"{label.replace(' ', '_')}_invalid")
    return result


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_json(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(
        character in "0123456789abcdef" for character in text
    )


__all__ = [
    "AuthoritativeDigDispatchLineage",
    "DiagnosticLineageError",
    "FileIdentity",
    "require_complete_lineage",
    "resolve_authoritative_lineage",
    "select_source_episode_balanced_variants",
    "validate_planner_variant",
]
