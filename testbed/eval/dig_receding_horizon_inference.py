"""Frozen ACT chunk collection and two-strategy dispatch reconstruction."""

from __future__ import annotations

import gc
from collections.abc import Mapping, Sequence
from typing import Any

import h5py
import numpy as np
import torch

from testbed.eval.dig_receding_horizon_data import (
    combined_state_lineage_sha256,
    read_dispatch_observation,
)
from testbed.eval.dig_receding_horizon_dispatch import (
    LatestChunkRecedingHorizonDispatcher,
    assess_action_support,
    latest_strategy,
    legacy_strategy_from_policy,
)
from testbed.eval.dig_receding_horizon_lineage import (
    AuthoritativeDigDispatchLineage,
    DiagnosticLineageError,
)
from testbed.eval.temporal_dispatch_contract import reconstruct_temporal_dispatch
from testbed.policies.act.inference import (
    build_act_adapter_config,
    describe_act_inference,
    load_act_policy,
)


def collect_frozen_act_dispatch_pairs(
    *,
    lineage: AuthoritativeDigDispatchLineage,
    variants: Sequence[Mapping[str, Any]],
    device: str,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]], dict[str, Any]]:
    """Collect public raw chunks once, then reconstruct exact A and B dispatches."""
    adapter_config = _adapter_config(lineage)
    policies = {
        arm: load_act_policy(
            ckpt_path=lineage.checkpoint.path,
            policy_config=adapter_config,
            norm_stats_path=lineage.stats.path,
            temporal_agg=True,
            device=device,
            create_optimizer=False,
        )
        for arm in ("baseline", "alternate")
    }
    if policies["baseline"] is policies["alternate"]:
        raise DiagnosticLineageError("arm_policy_identity_shared")
    descriptions = {
        arm: describe_act_inference(policy) for arm, policy in policies.items()
    }
    _validate_loaded_policies(policies, descriptions)
    dispatchers = {
        arm: LatestChunkRecedingHorizonDispatcher(policy)
        for arm, policy in policies.items()
    }
    legacy_strategy = legacy_strategy_from_policy(policies["baseline"])
    latest = latest_strategy(legacy_strategy.num_queries)
    action_std = np.asarray(descriptions["baseline"]["action_std"], dtype=np.float32)
    response_threshold = action_std * np.float32(0.05)
    traces: dict[str, list[dict[str, Any]]] = {"legacy": [], "latest": []}
    pairs: list[dict[str, Any]] = []
    state_rows: list[dict[str, Any]] = []

    for variant in variants:
        for dispatcher in dispatchers.values():
            dispatcher.begin_request()
        arm_records: dict[str, list[Any]] = {"baseline": [], "alternate": []}
        observation_lineage = []
        recorded_qpos = []
        recorded_qvel = []
        initial_qpos: np.ndarray | None = None
        initial_qvel: np.ndarray | None = None
        episode_path = str(variant["dataset_path"])
        frame_indices = [int(value) for value in variant["observation_frame_indices"]]
        with h5py.File(episode_path, "r") as hdf5_file:
            for local_frame, observation_frame in enumerate(frame_indices):
                observation, state = read_dispatch_observation(
                    hdf5_file,
                    frame_index=observation_frame,
                    camera_order=lineage.camera_order,
                )
                observation_lineage.append(state)
                recorded_qpos.append(
                    np.asarray(observation["qpos"], dtype=np.float32).copy()
                )
                recorded_qvel.append(
                    np.asarray(observation["qvel"], dtype=np.float32).copy()
                )
                if local_frame == 0:
                    initial_qpos = np.asarray(
                        observation["qpos"], dtype=np.float32
                    ).copy()
                    initial_qvel = np.asarray(
                        observation["qvel"], dtype=np.float32
                    ).copy()
                for arm, token_key in (
                    ("baseline", "base_token"),
                    ("alternate", "variant_token"),
                ):
                    record = dispatchers[arm].dispatch(observation, variant[token_key])
                    arm_records[arm].append(record)
                    state_rows.append(
                        {
                            "variant_id": str(variant["variant_id"]),
                            "arm": arm,
                            "frame_index": local_frame,
                            "observation_sha256": state["observation_sha256"],
                        }
                    )
        chunks = {
            arm: np.stack([record.raw_action_chunk for record in rows])
            for arm, rows in arm_records.items()
        }
        latest_actions = {arm: value[:, 0].copy() for arm, value in chunks.items()}
        legacy_traces = {
            arm: reconstruct_temporal_dispatch(
                chunks=value,
                strategy=legacy_strategy,
                reset_frame_indices=(0,),
            )
            for arm, value in chunks.items()
        }
        legacy_actions = {
            arm: trace.actions.copy() for arm, trace in legacy_traces.items()
        }
        responsive = np.any(
            np.abs(chunks["alternate"] - chunks["baseline"])
            > response_threshold[None, None, :],
            axis=(1, 2),
        )
        pair = {
            "variant_id": str(variant["variant_id"]),
            "variant_type": str(variant["variant_type"]),
            "source_episode_id": int(variant["source_episode_id"]),
            "primitive_episode_id": int(variant["primitive_episode_id"]),
            "frame_index": int(variant["frame_index"]),
            "initial_qpos": initial_qpos,
            "initial_qvel": initial_qvel,
            "recorded_qpos": np.stack(recorded_qpos),
            "recorded_qvel": np.stack(recorded_qvel),
            "goals": {
                "baseline": dict(variant["base_goal"]),
                "alternate": dict(variant["variant_goal"]),
            },
            "tokens": {
                "baseline": list(variant["base_token"]),
                "alternate": list(variant["variant_token"]),
            },
            "actions": {
                "legacy": legacy_actions,
                "latest": latest_actions,
            },
            "raw_goal_response": {
                "active_frame_fraction": float(np.mean(responsive)),
                "active_frame_count": int(np.count_nonzero(responsive)),
                "frame_count": len(responsive),
                "passes_fixed_80pct_gate": bool(np.mean(responsive) >= 0.80),
                "response_threshold": response_threshold.astype(float).tolist(),
            },
            "observation_lineage": observation_lineage,
        }
        _append_trace_rows(
            traces=traces,
            variant=variant,
            arm_records=arm_records,
            legacy_traces=legacy_traces,
            observation_lineage=observation_lineage,
            action_p01=lineage.action_p01,
            action_p99=lineage.action_p99,
        )
        pairs.append(pair)

    compatibility = _legacy_public_predict_compatibility(
        policies=policies,
        lineage=lineage,
        variant=variants[0],
        expected={
            arm: pairs[0]["actions"]["legacy"][arm] for arm in ("baseline", "alternate")
        },
    )
    cache_independent = bool(
        getattr(policies["baseline"], "_all_time_actions", None)
        is not getattr(policies["alternate"], "_all_time_actions", None)
    )
    metadata = {
        "schema": "dig_frozen_act_dispatch_collection_v1",
        "policy_instances_independent": True,
        "policy_cache_identity_independent": cache_independent,
        "optimizer_created": False,
        "backward_called": False,
        "checkpoint_parameters_modified": False,
        "policy_parameters_require_grad": {
            arm: any(
                parameter.requires_grad for parameter in policy._model.parameters()
            )
            for arm, policy in policies.items()
        },
        "policy": descriptions,
        "legacy_strategy": legacy_strategy.as_dict(),
        "latest_strategy": latest.as_dict(),
        "legacy_public_predict_compatibility": compatibility,
        "state_lineage_sha256": combined_state_lineage_sha256(state_rows),
        "state_lineage_row_count": len(state_rows),
        "same_recorded_observation_for_both_arms": True,
    }
    del dispatchers
    del policies
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return pairs, traces, metadata


def _append_trace_rows(
    *,
    traces: dict[str, list[dict[str, Any]]],
    variant: Mapping[str, Any],
    arm_records: Mapping[str, Sequence[Any]],
    legacy_traces: Mapping[str, Any],
    observation_lineage: Sequence[Mapping[str, Any]],
    action_p01: np.ndarray,
    action_p99: np.ndarray,
) -> None:
    for arm in ("baseline", "alternate"):
        for frame_index, record in enumerate(arm_records[arm]):
            common = {
                "schema": "dig_act_dispatch_trace_frame_v1",
                "variant_id": str(variant["variant_id"]),
                "variant_type": str(variant["variant_type"]),
                "source_episode_id": int(variant["source_episode_id"]),
                "primitive_episode_id": int(variant["primitive_episode_id"]),
                "arm": arm,
                "frame_index": frame_index,
                "observation_frame_index": int(
                    variant["observation_frame_indices"][frame_index]
                ),
                "goal_sha256": record.goal_sha256,
                "cache_reset": bool(frame_index == 0),
                "observation_sha256": str(
                    observation_lineage[frame_index]["observation_sha256"]
                ),
                "raw_action_chunk": record.raw_action_chunk.astype(float).tolist(),
                "raw_chunk_support": assess_action_support(
                    record.raw_action_chunk, p01=action_p01, p99=action_p99
                ),
                "clipping_applied": False,
                "nonfinite": bool(record.nonfinite),
            }
            latest_support = assess_action_support(
                record.dispatched_action[None], p01=action_p01, p99=action_p99
            )
            traces["latest"].append(
                {
                    **common,
                    "strategy": "latest",
                    "diagnostic_dispatched_action": record.dispatched_action.astype(
                        float
                    ).tolist(),
                    "contributing_chunk_ages": [0],
                    "contributing_chunk_weights": [1.0],
                    "action_support": latest_support,
                }
            )
            legacy_trace = legacy_traces[arm]
            contributors = legacy_trace.contributors[frame_index]
            legacy_action = legacy_trace.actions[frame_index]
            legacy_support = assess_action_support(
                legacy_action[None], p01=action_p01, p99=action_p99
            )
            traces["legacy"].append(
                {
                    **common,
                    "strategy": "legacy",
                    "diagnostic_dispatched_action": legacy_action.astype(
                        float
                    ).tolist(),
                    "contributing_chunk_ages": [item.age for item in contributors],
                    "contributing_chunk_weights": [
                        item.weight for item in contributors
                    ],
                    "action_support": legacy_support,
                }
            )


def _legacy_public_predict_compatibility(
    *,
    policies: Mapping[str, Any],
    lineage: AuthoritativeDigDispatchLineage,
    variant: Mapping[str, Any],
    expected: Mapping[str, np.ndarray],
) -> dict[str, Any]:
    results = {}
    with h5py.File(str(variant["dataset_path"]), "r") as hdf5_file:
        for arm, token_key in (
            ("baseline", "base_token"),
            ("alternate", "variant_token"),
        ):
            policy = policies[arm]
            policy.reset()
            actions = []
            for frame_index in variant["observation_frame_indices"]:
                observation, _ = read_dispatch_observation(
                    hdf5_file,
                    frame_index=int(frame_index),
                    camera_order=lineage.camera_order,
                )
                observation["dig_cut_tokens"] = np.asarray(
                    variant[token_key], dtype=np.float32
                )
                actions.append(
                    np.asarray(policy.predict(observation), dtype=np.float32)
                )
            actual = np.stack(actions)
            reference = np.asarray(expected[arm], dtype=np.float32)
            maximum = float(np.max(np.abs(actual - reference)))
            results[arm] = {
                "bitwise_equal": bool(actual.tobytes() == reference.tobytes()),
                "maximum_absolute_error": maximum,
                "behaviour_compatible_at_1e_6": bool(maximum <= 1.0e-6),
            }
    return {
        "checked_variant_id": str(variant["variant_id"]),
        "arms": results,
        "passed": all(
            value["behaviour_compatible_at_1e_6"] for value in results.values()
        ),
    }


def _adapter_config(lineage: AuthoritativeDigDispatchLineage) -> dict[str, Any]:
    config = lineage.resolved_training_config
    task = dict(config["task"])
    policy = dict(config["policy"])
    return build_act_adapter_config(
        config=config,
        camera_names=lineage.camera_order,
        equipment_model=str(task["equipment_model"]),
        max_episode_len=int(task["episode_len"]),
        low_dim_keys=lineage.low_dim_order,
        act_params=dict(policy.get("act_params", {}) or {}),
        outcome_head_config=dict(policy.get("outcome_head", {}) or {}),
        image_mask_config=dict(policy.get("image_mask", {}) or {}),
        supervision_keys=list(policy.get("supervision_keys", []) or []),
    )


def _validate_loaded_policies(
    policies: Mapping[str, Any], descriptions: Mapping[str, Mapping[str, Any]]
) -> None:
    if descriptions["baseline"] != descriptions["alternate"]:
        raise DiagnosticLineageError("independent_policy_contract_mismatch")
    contract = descriptions["baseline"]["temporal_aggregation"]
    expected = {
        "enabled": True,
        "num_queries": 100,
        "window": 100,
        "weight_order": "legacy_oldest_first",
        "decay": 0.01,
    }
    if contract != expected:
        raise DiagnosticLineageError("legacy_temporal_contract_drift")
    for policy in policies.values():
        if getattr(policy, "_optimizer", "missing") is not None:
            raise DiagnosticLineageError("optimizer_created_for_diagnostic")
        if any(parameter.requires_grad for parameter in policy._model.parameters()):
            raise DiagnosticLineageError("act_checkpoint_parameters_not_frozen")


__all__ = ["collect_frozen_act_dispatch_pairs"]
