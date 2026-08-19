"""Carry/Dump isolation replay for the Stage-A ACT sensitivity audit.

This module owns the unconditioned primitive check: adding a real Dig token to
an observation that a Carry or Dump policy must ignore cannot alter raw chunks
or temporal dispatched actions beyond measured baseline replica tolerance.
"""

from __future__ import annotations

import gc
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np

from testbed.data.recorded_act_replay import (
    RecordedActReplayFrame,
    RecordedActReplaySegment,
)
from testbed.eval.act_goal_condition_sensitivity import (
    EVIDENCE_KIND,
    derive_replica_tolerance,
)

ISOLATION_SCHEMA = "act_goal_condition_sensitivity_isolation_v1"
PolicyFactoryBuilder = Callable[[str, Mapping[str, Any]], Callable[[Mapping[str, Any], str], Any]]


def run_carry_dump_isolation(
    *,
    policy_cfg: Mapping[str, Any],
    segments: Sequence[RecordedActReplaySegment],
    dig_segments: Sequence[RecordedActReplaySegment],
    policy_factory_builder: PolicyFactoryBuilder,
    observation_reader: Callable[[RecordedActReplayFrame], Mapping[str, Any]],
    action_std_by_primitive: Mapping[str, np.ndarray],
) -> dict[str, Any]:
    """Replay one deterministic Carry/Dump segment with and without a Dig token."""

    if not dig_segments:
        return _isolation_invalid("no_real_dig_token_available")
    extraneous_source = min(dig_segments, key=lambda item: item.start_action_step_id)
    if extraneous_source.token is None or extraneous_source.token_sha256 is None:
        return _isolation_invalid("selected_dig_segment_has_no_token")
    checks: dict[str, dict[str, Any]] = {}
    for primitive in ("carry", "dump"):
        low_dim_keys = [str(value) for value in policy_cfg.get(f"{primitive}_low_dim_keys", ())]
        candidates = [item for item in segments if item.skill_name == primitive]
        if low_dim_keys != ["qpos", "qvel"]:
            checks[primitive] = {
                "passed": False,
                "reason": "unexpected_condition_input_contract",
                "low_dim_keys": low_dim_keys,
            }
            continue
        if not candidates:
            checks[primitive] = {
                "passed": False,
                "reason": "no_recorded_segment",
                "low_dim_keys": low_dim_keys,
            }
            continue
        selected = min(candidates, key=lambda item: item.start_action_step_id)
        try:
            factory = policy_factory_builder(primitive, policy_cfg)
            baseline_a = _run_unconditioned_policy_stream(
                policy_factory=factory,
                replica_id=f"{primitive}_isolation_baseline_replica_a",
                frames=selected.frames,
                observation_reader=observation_reader,
                extraneous_dig_token=None,
            )
            baseline_b = _run_unconditioned_policy_stream(
                policy_factory=factory,
                replica_id=f"{primitive}_isolation_baseline_replica_b",
                frames=selected.frames,
                observation_reader=observation_reader,
                extraneous_dig_token=None,
            )
            tolerance = derive_replica_tolerance(
                baseline_a_chunks=baseline_a["anchor_chunks"],
                baseline_b_chunks=baseline_b["anchor_chunks"],
                baseline_a_actions=baseline_a["actions"],
                baseline_b_actions=baseline_b["actions"],
                action_std=np.asarray(action_std_by_primitive[primitive], dtype=np.float32),
            )
            baseline_validity = _unconditioned_baseline_validity(
                frames=selected.frames,
                baseline_a=baseline_a,
                baseline_b=baseline_b,
                tolerance=tolerance,
            )
            if not bool(baseline_validity["passed"]):
                checks[primitive] = {
                    "passed": False,
                    "reason": "baseline_artifact_invalid",
                    "segment": _segment_record(selected),
                    "baseline_validity": baseline_validity,
                }
                continue
            extra = _run_unconditioned_policy_stream(
                policy_factory=factory,
                replica_id=f"{primitive}_isolation_extraneous_dig_token",
                frames=selected.frames,
                observation_reader=observation_reader,
                extraneous_dig_token=np.asarray(extraneous_source.token, dtype=np.float32),
            )
            comparison = _unconditioned_isolation_comparison(
                baseline=baseline_a,
                extraneous=extra,
                tolerance=tolerance,
            )
            checks[primitive] = {
                "passed": bool(comparison["passed"]),
                "reason": (
                    "extraneous_dig_token_inert"
                    if comparison["passed"]
                    else "extraneous_dig_token_changed_act_output"
                ),
                "low_dim_keys": low_dim_keys,
                "segment": _segment_record(selected),
                "extraneous_dig_token": {
                    "source_segment_id": extraneous_source.segment_id,
                    "source_token_sha256": extraneous_source.token_sha256,
                    "injected_input_key": "dig_cut_tokens",
                },
                "baseline_validity": baseline_validity,
                "comparison": comparison,
            }
        except (KeyError, TypeError, ValueError) as exc:
            checks[primitive] = {
                "passed": False,
                "reason": f"{type(exc).__name__}: {exc}",
                "segment": _segment_record(selected),
            }
    return {
        "schema": ISOLATION_SCHEMA,
        "status": "completed" if all(value["passed"] for value in checks.values()) else "artifact_invalid",
        "evidence_kind": EVIDENCE_KIND,
        "diagnostic_only": True,
        "promotion_eligible": False,
        "checks": checks,
    }


def _isolation_invalid(reason: str) -> dict[str, Any]:
    return {
        "schema": ISOLATION_SCHEMA,
        "status": "artifact_invalid",
        "evidence_kind": EVIDENCE_KIND,
        "diagnostic_only": True,
        "promotion_eligible": False,
        "checks": {},
        "reason": reason,
    }


def _run_unconditioned_policy_stream(
    *,
    policy_factory: Callable[[Mapping[str, Any], str], Any],
    replica_id: str,
    frames: Sequence[RecordedActReplayFrame],
    observation_reader: Callable[[RecordedActReplayFrame], Mapping[str, Any]],
    extraneous_dig_token: np.ndarray | None,
) -> dict[str, Any]:
    policy = policy_factory({"condition_id": "unconditioned"}, replica_id)
    try:
        policy.reset()
        anchor_indices = _anchor_indices(len(frames))
        anchor_chunks: list[np.ndarray] = []
        actions: list[np.ndarray] = []
        for index, frame in enumerate(frames):
            observation = dict(observation_reader(frame))
            if extraneous_dig_token is not None:
                if "dig_cut_tokens" in observation:
                    raise ValueError("unconditioned observation already has dig_cut_tokens")
                observation["dig_cut_tokens"] = np.asarray(
                    extraneous_dig_token,
                    dtype=np.float32,
                ).copy()
            if index in anchor_indices:
                chunk = np.asarray(policy.predict_action_chunk(observation).actions, dtype=np.float32)
                if chunk.ndim != 2 or not np.isfinite(chunk).all():
                    raise ValueError("unconditioned policy returned invalid action chunk")
                anchor_chunks.append(chunk)
            action = np.asarray(policy.predict(observation), dtype=np.float32).reshape(-1)
            if action.ndim != 1 or not np.isfinite(action).all():
                raise ValueError("unconditioned policy returned invalid action")
            actions.append(action)
        return {
            "instance_id": replica_id,
            "anchor_chunks": np.stack(anchor_chunks, axis=0),
            "actions": np.stack(actions, axis=0),
        }
    finally:
        del policy
        gc.collect()
        _release_cuda_cache()


def _unconditioned_baseline_validity(
    *,
    frames: Sequence[RecordedActReplayFrame],
    baseline_a: Mapping[str, Any],
    baseline_b: Mapping[str, Any],
    tolerance: Mapping[str, Any],
) -> dict[str, Any]:
    actions_a = np.asarray(baseline_a["actions"], dtype=np.float32)
    actions_b = np.asarray(baseline_b["actions"], dtype=np.float32)
    chunks_a = np.asarray(baseline_a["anchor_chunks"], dtype=np.float32)
    chunks_b = np.asarray(baseline_b["anchor_chunks"], dtype=np.float32)
    recorded = np.asarray([frame.action for frame in frames], dtype=np.float32)
    if actions_a.shape != actions_b.shape or actions_a.shape != recorded.shape or chunks_a.shape != chunks_b.shape:
        raise ValueError("unconditioned baseline output shapes differ")
    cap = np.asarray(tolerance["replica_noise_cap_axis"], dtype=np.float32)
    saved_tolerance = np.asarray(tolerance["dispatched_tolerance_axis"], dtype=np.float32)
    replica_action_delta = np.max(np.abs(actions_a - actions_b), axis=0)
    replica_chunk_delta = np.max(np.abs(chunks_a - chunks_b), axis=(0, 1))
    saved_a_delta = np.max(np.abs(actions_a - recorded), axis=0)
    saved_b_delta = np.max(np.abs(actions_b - recorded), axis=0)
    replicas_passed = bool(np.all(replica_action_delta <= cap) and np.all(replica_chunk_delta <= cap))
    saved_passed = bool(np.all(saved_a_delta <= saved_tolerance) and np.all(saved_b_delta <= saved_tolerance))
    return {
        "passed": bool(replicas_passed and saved_passed),
        "replica_tolerance": tolerance,
        "baseline_replicas": {
            "passed": replicas_passed,
            "max_dispatched_action_abs_delta_axis": _float_list(replica_action_delta),
            "max_anchor_chunk_abs_delta_axis": _float_list(replica_chunk_delta),
        },
        "saved_action_alignment": {
            "passed": saved_passed,
            "replica_a_max_abs_delta_axis": _float_list(saved_a_delta),
            "replica_b_max_abs_delta_axis": _float_list(saved_b_delta),
        },
    }


def _unconditioned_isolation_comparison(
    *,
    baseline: Mapping[str, Any],
    extraneous: Mapping[str, Any],
    tolerance: Mapping[str, Any],
) -> dict[str, Any]:
    baseline_actions = np.asarray(baseline["actions"], dtype=np.float32)
    extra_actions = np.asarray(extraneous["actions"], dtype=np.float32)
    baseline_chunks = np.asarray(baseline["anchor_chunks"], dtype=np.float32)
    extra_chunks = np.asarray(extraneous["anchor_chunks"], dtype=np.float32)
    if baseline_actions.shape != extra_actions.shape or baseline_chunks.shape != extra_chunks.shape:
        raise ValueError("isolation comparison output shapes differ")
    action_delta = np.max(np.abs(extra_actions - baseline_actions), axis=0)
    chunk_delta = np.max(np.abs(extra_chunks - baseline_chunks), axis=(0, 1))
    action_tolerance = np.asarray(tolerance["dispatched_tolerance_axis"], dtype=np.float32)
    chunk_tolerance = np.asarray(tolerance["replica_noise_cap_axis"], dtype=np.float32)
    passed = bool(np.all(action_delta <= action_tolerance) and np.all(chunk_delta <= chunk_tolerance))
    return {
        "passed": passed,
        "max_dispatched_action_abs_delta_axis": _float_list(action_delta),
        "max_anchor_chunk_abs_delta_axis": _float_list(chunk_delta),
        "dispatched_tolerance_axis": _float_list(action_tolerance),
        "anchor_chunk_tolerance_axis": _float_list(chunk_tolerance),
    }


def _segment_record(segment: RecordedActReplaySegment) -> dict[str, Any]:
    return {
        "segment_id": segment.segment_id,
        "primitive": segment.skill_name,
        "model_token_key": segment.model_token_key,
        "token_sha256": segment.token_sha256,
        "token_source": segment.token_source,
        "start_action_step_id": segment.start_action_step_id,
        "end_action_step_id": segment.end_action_step_id,
        "frame_count": segment.frame_count,
        "primitive_cycle_indices": list(segment.primitive_cycle_indices),
    }


def _anchor_indices(frame_count: int) -> tuple[int, int, int]:
    if frame_count < 3:
        raise ValueError("isolation segment requires at least three frames")
    return (0, frame_count // 2, frame_count - 1)


def _float_list(values: np.ndarray) -> list[float]:
    return [float(value) for value in np.asarray(values, dtype=np.float32).reshape(-1)]


def _release_cuda_cache() -> None:
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:  # pragma: no cover - torch is a runtime dependency.
        return


__all__ = ["ISOLATION_SCHEMA", "run_carry_dump_isolation"]
