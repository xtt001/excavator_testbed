"""Fail-closed teacher-forced ACT goal-condition sensitivity evaluation.

This module owns the *evaluation* half of Strict-18 Stage A.  The data layer
owns recorded HDF5/JSONL alignment and stable-token segment selection; callers
pass those immutable frames here with a policy factory and an observation
reader.  This module never chooses goals, runs a Unity rollout, or changes a
runtime policy.
"""

from __future__ import annotations

import gc
import json
import math
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

ACT_GOAL_CONDITION_SENSITIVITY_MANIFEST_SCHEMA = (
    "act_goal_condition_sensitivity_manifest_v1"
)
ACT_GOAL_CONDITION_SENSITIVITY_RESULTS_SCHEMA = (
    "act_goal_condition_sensitivity_results_v1"
)
EVIDENCE_KIND = "teacher_forced_recorded_observation"
OUTPUT_ROOT_NAME = "act_goal_condition_sensitivity_v1"
ACTION_STD_FRACTION = 0.05
REQUIRED_RESPONSIVE_FRAME_FRACTION = 0.80
ANCHOR_COUNT = 3
_SUPPORTED_SUPPORT_STATUSES = frozenset({"supported", "out_of_support"})
_CLASSIFICATIONS = frozenset(
    {
        "goal_insensitive",
        "goal_response_invalid",
        "out_of_support",
        "goal_response_plausible",
    }
)


class PhaseAContractError(ValueError):
    """Raised internally while turning a malformed input into artifact evidence."""


PolicyFactory = Callable[[Mapping[str, Any], str], Any]
ObservationReader = Callable[[Any], Mapping[str, Any]]
SupportAssessor = Callable[[Mapping[str, Any], Any], Mapping[str, Any]]
IsolationCheck = Callable[[Any, Sequence[Mapping[str, Any]]], Mapping[str, Any]]


def evaluate_goal_condition_sensitivity_segment(
    *,
    segment: Any,
    conditions: Sequence[Mapping[str, Any]],
    policy_factory: PolicyFactory,
    action_std: np.ndarray,
    observation_reader: ObservationReader | None = None,
    support_assessor: SupportAssessor | None = None,
    isolation_check: IsolationCheck | None = None,
) -> dict[str, Any]:
    """Evaluate one frozen Dig or Return segment, or a Carry/Dump isolation hook.

    Two independent baseline replicas are always replayed first.  Their observed
    numerical difference is registered as the only tolerance before any
    counterfactual policy is created.  A failed preflight, replica execution,
    saved-action alignment, or isolation check returns ``artifact_invalid`` and
    deliberately omits all four-class classifications.

    ``direction`` is intentionally not inferred: a teacher-forced action delta
    cannot identify whether a counterfactual physical trajectory is reasonable.
    """

    condition_records = _condition_skeletons(conditions)
    base_result = _base_result(segment=segment, condition_records=condition_records)
    try:
        normalized = _normalise_inputs(segment=segment, conditions=conditions)
        frozen_action_std = _finite_array(
            action_std,
            label="frozen_checkpoint_action_std",
            ndim=1,
        )
    except PhaseAContractError as exc:
        return _artifact_invalid(base_result, stage="preflight", reason=str(exc))

    primitive = normalized["primitive"]
    if primitive in {"carry", "dump"}:
        return _evaluate_isolation_only(
            base_result=base_result,
            segment=segment,
            conditions=normalized["conditions"],
            isolation_check=isolation_check,
        )

    try:
        baseline_a = _run_policy_stream(
            policy_factory=policy_factory,
            condition=normalized["baseline"],
            replica_id="baseline_replica_a",
            frames=normalized["frames"],
            condition_input_key=normalized["condition_input_key"],
            observation_reader=observation_reader,
        )
        baseline_b = _run_policy_stream(
            policy_factory=policy_factory,
            condition=normalized["baseline"],
            replica_id="baseline_replica_b",
            frames=normalized["frames"],
            condition_input_key=normalized["condition_input_key"],
            observation_reader=observation_reader,
        )
        tolerance = derive_replica_tolerance(
            baseline_a_chunks=baseline_a["anchor_chunks"],
            baseline_b_chunks=baseline_b["anchor_chunks"],
            baseline_a_actions=baseline_a["dispatched_actions"],
            baseline_b_actions=baseline_b["dispatched_actions"],
            action_std=frozen_action_std,
        )
        validity = _validate_baseline_artifact(
            frames=normalized["frames"],
            baseline_a=baseline_a,
            baseline_b=baseline_b,
            tolerance=tolerance,
        )
    except (PhaseAContractError, KeyError, TypeError, ValueError) as exc:
        return _artifact_invalid(
            base_result,
            stage="baseline_execution",
            reason=f"{type(exc).__name__}: {exc}",
        )

    base_result["artifact_validity"] = validity
    if not bool(validity["passed"]):
        base_result["status"] = "artifact_invalid"
        return base_result

    baseline_actions = np.asarray(baseline_a["dispatched_actions"], dtype=np.float32)
    if frozen_action_std.shape != (baseline_actions.shape[1],):
        return _artifact_invalid(
            base_result,
            stage="baseline_action_std",
            reason="frozen checkpoint action_std width does not match dispatched action",
        )
    action_threshold = frozen_action_std * np.float32(ACTION_STD_FRACTION)
    base_result["baseline"] = {
        "condition_id": normalized["baseline"]["condition_id"],
        "status": "aligned",
        "frame_count": int(len(normalized["frames"])),
        "anchor_indices": list(normalized["anchor_indices"]),
        "action_std": _float_list(frozen_action_std),
        "response_threshold": _float_list(action_threshold),
        "replica_instance_ids": [
            baseline_a["instance_id"],
            baseline_b["instance_id"],
        ],
    }

    try:
        baseline_support = _assess_support(
            condition=normalized["baseline"],
            segment=segment,
            support_assessor=support_assessor,
        )
    except (PhaseAContractError, KeyError, TypeError, ValueError) as exc:
        return _artifact_invalid(
            base_result,
            stage="baseline_support",
            reason=f"{type(exc).__name__}: {exc}",
        )
    base_result["baseline"]["support"] = baseline_support

    for condition in normalized["counterfactuals"]:
        try:
            support = _assess_support(
                condition=condition,
                segment=segment,
                support_assessor=support_assessor,
            )
        except (PhaseAContractError, KeyError, TypeError, ValueError) as exc:
            return _artifact_invalid(
                base_result,
                stage="counterfactual_support",
                reason=(
                    f"condition={condition['condition_id']}; "
                    f"{type(exc).__name__}: {exc}"
                ),
            )
        if (
            baseline_support["status"] == "out_of_support"
            or support["status"] == "out_of_support"
        ):
            base_result["conditions"][condition["condition_id"]] = {
                **_condition_record(condition),
                "support": {
                    "baseline": baseline_support,
                    "counterfactual": support,
                },
                "classification": "out_of_support",
                "direction": "not_identifiable_in_teacher_forced_replay",
            }
            continue

        try:
            candidate_a = _run_policy_stream(
                policy_factory=policy_factory,
                condition=condition,
                replica_id=f"condition_{condition['condition_id']}_replica_a",
                frames=normalized["frames"],
                condition_input_key=normalized["condition_input_key"],
                observation_reader=observation_reader,
            )
            candidate_b = _run_policy_stream(
                policy_factory=policy_factory,
                condition=condition,
                replica_id=f"condition_{condition['condition_id']}_replica_b",
                frames=normalized["frames"],
                condition_input_key=normalized["condition_input_key"],
                observation_reader=observation_reader,
            )
        except (PhaseAContractError, KeyError, TypeError, ValueError) as exc:
            return _artifact_invalid(
                base_result,
                stage="counterfactual_execution",
                reason=(
                    f"condition={condition['condition_id']}; "
                    f"{type(exc).__name__}: {exc}"
                ),
            )

        try:
            candidate_replica = _validate_counterfactual_replicas(
                candidate_a=candidate_a,
                candidate_b=candidate_b,
                tolerance=tolerance,
            )
        except (PhaseAContractError, KeyError, TypeError, ValueError) as exc:
            return _artifact_invalid(
                base_result,
                stage="counterfactual_replica_integrity",
                reason=(
                    f"condition={condition['condition_id']}; "
                    f"{type(exc).__name__}: {exc}"
                ),
            )
        if not bool(candidate_replica["passed"]):
            base_result["conditions"][condition["condition_id"]] = {
                **_condition_record(condition),
                "support": {
                    "baseline": baseline_support,
                    "counterfactual": support,
                },
                "classification": "goal_response_invalid",
                "direction": "not_identifiable_in_teacher_forced_replay",
                "replica_validity": candidate_replica,
            }
            continue
        response = _response_gate(
            baseline_actions=baseline_actions,
            candidate_actions=np.asarray(candidate_a["dispatched_actions"], dtype=np.float32),
            baseline_anchor_chunks=np.asarray(baseline_a["anchor_chunks"], dtype=np.float32),
            candidate_anchor_chunks=np.asarray(candidate_a["anchor_chunks"], dtype=np.float32),
            action_threshold=action_threshold,
            anchor_indices=normalized["anchor_indices"],
        )
        if bool(response["passed"]):
            classification = "goal_response_plausible"
        elif bool(response["all_deltas_within_threshold"]):
            classification = "goal_insensitive"
        else:
            classification = "goal_response_invalid"
        base_result["conditions"][condition["condition_id"]] = {
            **_condition_record(condition),
            "support": {
                "baseline": baseline_support,
                "counterfactual": support,
            },
            "classification": classification,
            "direction": "not_identifiable_in_teacher_forced_replay",
            "response_gate": response["gate"],
            "anchor_chunk_deltas": response["anchor_chunk_deltas"],
            "temporal_aggregated_action_deltas": response[
                "temporal_aggregated_action_deltas"
            ],
            "replica_validity": candidate_replica,
            "policy_instance_ids": [
                candidate_a["instance_id"],
                candidate_b["instance_id"],
            ],
        }

    base_result["status"] = "completed"
    return base_result


def derive_replica_tolerance(
    *,
    baseline_a_chunks: np.ndarray,
    baseline_b_chunks: np.ndarray,
    baseline_a_actions: np.ndarray,
    baseline_b_actions: np.ndarray,
    action_std: np.ndarray,
) -> dict[str, Any]:
    """Register numerical tolerance from two independently replayed baselines.

    This is deliberately derived before counterfactual execution.  It is not a
    caller-provided threshold and is retained in the artifact for replay audit.
    """

    chunks_a = _finite_array(baseline_a_chunks, label="baseline_a_chunks", ndim=3)
    chunks_b = _finite_array(baseline_b_chunks, label="baseline_b_chunks", ndim=3)
    actions_a = _finite_array(baseline_a_actions, label="baseline_a_actions", ndim=2)
    actions_b = _finite_array(baseline_b_actions, label="baseline_b_actions", ndim=2)
    if chunks_a.shape != chunks_b.shape:
        raise PhaseAContractError("baseline replica chunk shapes differ")
    if actions_a.shape != actions_b.shape:
        raise PhaseAContractError("baseline replica action shapes differ")
    std = _finite_array(action_std, label="baseline_action_std", ndim=1)
    if std.shape != (actions_a.shape[1],):
        raise PhaseAContractError("baseline action std width does not match actions")
    chunk_delta_axis = np.max(np.abs(chunks_a - chunks_b), axis=(0, 1))
    dispatched_delta_axis = np.max(np.abs(actions_a - actions_b), axis=0)
    replica_noise_cap_axis = np.maximum(
        np.float32(1.0e-6),
        np.float32(0.005) * np.abs(std),
    )
    dispatched_tolerance_axis = np.maximum(
        np.float32(1.0e-6),
        np.float32(10.0) * dispatched_delta_axis,
    )
    return {
        "source": "two_baseline_replicas",
        "replica_noise_cap_derivation": "max(1e-6, 0.005 * abs(baseline_action_std_axis))",
        "dispatched_tolerance_derivation": "max(1e-6, 10 * max_abs_replica_dispatched_delta_axis)",
        "replica_noise_cap_axis": _float_list(replica_noise_cap_axis),
        "chunk_max_abs_delta_axis": _float_list(chunk_delta_axis),
        "dispatched_max_abs_delta_axis": _float_list(dispatched_delta_axis),
        "dispatched_tolerance_axis": _float_list(dispatched_tolerance_axis),
    }


def write_goal_condition_sensitivity_artifact(
    *,
    output_root: str | Path,
    manifest: Mapping[str, Any],
    baseline: Mapping[str, Any],
    dig: Mapping[str, Any],
    return_: Mapping[str, Any],
    carry_dump_isolation: Mapping[str, Any],
    report_markdown: str,
) -> dict[str, Any]:
    """Exclusively write the six fixed Stage-A evidence files.

    The caller must assemble every payload before this operation.  That keeps a
    failed read or policy load from leaving a partially populated evidence root.
    """

    destination = Path(output_root).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"Stage-A output already exists: {destination}")
    manifest_payload = _json_ready(dict(manifest))
    if manifest_payload.get("schema") != ACT_GOAL_CONDITION_SENSITIVITY_MANIFEST_SCHEMA:
        raise PhaseAContractError("manifest schema is not Stage-A manifest v1")
    destination.mkdir(parents=True, exist_ok=False)
    _write_json_exclusive(destination / "manifest.json", manifest_payload)
    _write_json_exclusive(destination / "baseline.json", baseline)
    _write_json_exclusive(destination / "dig.json", dig)
    _write_json_exclusive(destination / "return.json", return_)
    _write_json_exclusive(destination / "carry_dump_isolation.json", carry_dump_isolation)
    with (destination / "report.md").open("x", encoding="utf-8") as handle:
        handle.write(str(report_markdown))
    return manifest_payload


def _normalise_inputs(
    *,
    segment: Any,
    conditions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    primitive = str(_field(segment, "primitive", "")).strip().lower()
    if primitive not in {"dig", "return", "carry", "dump"}:
        raise PhaseAContractError(f"unsupported Stage-A primitive {primitive!r}")
    frames = list(_field(segment, "frames", ()))
    if len(frames) < ANCHOR_COUNT:
        raise PhaseAContractError(
            f"Stage-A segment requires at least three frames, got {len(frames)}"
        )
    normalised_conditions = [_normalise_condition(value, index) for index, value in enumerate(conditions)]
    if len(normalised_conditions) < 2:
        raise PhaseAContractError("Stage-A requires one baseline and one alternate condition")
    baseline_candidates = [
        condition
        for condition in normalised_conditions
        if bool(condition.get("is_baseline", False))
    ]
    baseline = (
        baseline_candidates[0]
        if baseline_candidates
        else normalised_conditions[0]
    )
    if len(baseline_candidates) > 1:
        raise PhaseAContractError("Stage-A has multiple baseline conditions")
    counterfactuals = [
        value for value in normalised_conditions if value is not baseline
    ]
    if not counterfactuals:
        raise PhaseAContractError("Stage-A has no counterfactual condition")
    if primitive in {"dig", "return"}:
        condition_input_key = _field(
            segment,
            "condition_input_key",
            _field(segment, "model_token_key", None),
        )
        if not isinstance(condition_input_key, str) or not condition_input_key:
            raise PhaseAContractError("conditioned segment lacks model token key")
    else:
        condition_input_key = None
    _validate_frames(frames)
    return {
        "primitive": primitive,
        "frames": frames,
        "conditions": normalised_conditions,
        "baseline": baseline,
        "counterfactuals": counterfactuals,
        "condition_input_key": condition_input_key,
        "anchor_indices": _anchor_indices(len(frames)),
    }


def _normalise_condition(value: Mapping[str, Any], index: int) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise PhaseAContractError(f"condition[{index}] must be a mapping")
    condition_id = str(value.get("condition_id", "")).strip()
    if not condition_id:
        raise PhaseAContractError(f"condition[{index}] lacks condition_id")
    token = _finite_array(value.get("token"), label=f"condition[{condition_id}].token", ndim=1)
    status = str(value.get("support_status", "supported"))
    if status not in _SUPPORTED_SUPPORT_STATUSES:
        raise PhaseAContractError(
            f"condition[{condition_id}] has unsupported support_status {status!r}"
        )
    return {
        "condition_id": condition_id,
        "token": token,
        "support_status": status,
        "provenance": _json_ready(dict(value.get("provenance", {}) or {})),
        "is_baseline": bool(value.get("is_baseline", False)),
    }


def _validate_frames(frames: Sequence[Any]) -> None:
    previous_action_step: int | None = None
    for index, frame in enumerate(frames):
        action_step = _int_field(frame, "action_step_id")
        observation_step = _int_field(frame, "observation_step_id")
        if observation_step != action_step - 1:
            raise PhaseAContractError(
                "action/pre-observation steps are not contiguous at "
                f"frame={index}: action={action_step}, observation={observation_step}"
            )
        if previous_action_step is not None and action_step != previous_action_step + 1:
            raise PhaseAContractError(
                f"action steps are not contiguous at frame={index}: "
                f"previous={previous_action_step}, current={action_step}"
            )
        _finite_array(_recorded_action(frame), label=f"frame[{index}].recorded_action", ndim=1)
        if not bool(_field(frame, "policy_dispatched", True)):
            raise PhaseAContractError(
                f"frame[{index}] was not a raw policy dispatch"
            )
        previous_action_step = action_step


def _run_policy_stream(
    *,
    policy_factory: PolicyFactory,
    condition: Mapping[str, Any],
    replica_id: str,
    frames: Sequence[Any],
    condition_input_key: str,
    observation_reader: ObservationReader | None,
) -> dict[str, Any]:
    """Load, reset, replay, and release exactly one policy instance."""

    policy = policy_factory(condition, replica_id)
    if policy is None:
        raise PhaseAContractError(f"policy_factory returned None for {replica_id}")
    try:
        reset = getattr(policy, "reset", None)
        if not callable(reset):
            raise PhaseAContractError(f"policy {replica_id} has no reset()")
        reset()
        anchor_indices = set(_anchor_indices(len(frames)))
        anchor_chunks: list[np.ndarray] = []
        actions: list[np.ndarray] = []
        for index, frame in enumerate(frames):
            observation = dict(_read_observation(frame, observation_reader))
            observation[condition_input_key] = np.asarray(
                condition["token"], dtype=np.float32
            ).copy()
            if index in anchor_indices:
                predict_chunk = getattr(policy, "predict_action_chunk", None)
                if not callable(predict_chunk):
                    raise PhaseAContractError(
                        f"policy {replica_id} has no predict_action_chunk()"
                    )
                raw_chunk = predict_chunk(observation)
                anchor_chunks.append(_chunk_actions(raw_chunk, label=replica_id))
            predict = getattr(policy, "predict", None)
            if not callable(predict):
                raise PhaseAContractError(f"policy {replica_id} has no predict()")
            actions.append(_finite_array(predict(observation), label=replica_id, ndim=1))
        return {
            "instance_id": replica_id,
            "anchor_chunks": np.stack(anchor_chunks, axis=0),
            "dispatched_actions": np.stack(actions, axis=0),
        }
    finally:
        del policy
        gc.collect()
        _release_cuda_cache()


def _validate_baseline_artifact(
    *,
    frames: Sequence[Any],
    baseline_a: Mapping[str, Any],
    baseline_b: Mapping[str, Any],
    tolerance: Mapping[str, Any],
) -> dict[str, Any]:
    action_a = _finite_array(baseline_a["dispatched_actions"], label="baseline_a", ndim=2)
    action_b = _finite_array(baseline_b["dispatched_actions"], label="baseline_b", ndim=2)
    chunks_a = _finite_array(baseline_a["anchor_chunks"], label="baseline_a_chunks", ndim=3)
    chunks_b = _finite_array(baseline_b["anchor_chunks"], label="baseline_b_chunks", ndim=3)
    recorded = np.stack([_recorded_action(frame) for frame in frames], axis=0)
    if action_a.shape != action_b.shape or action_a.shape != recorded.shape:
        raise PhaseAContractError("baseline and recorded dispatched action shapes differ")
    if chunks_a.shape != chunks_b.shape:
        raise PhaseAContractError("baseline replica chunk shapes differ")
    replica_cap = np.asarray(tolerance["replica_noise_cap_axis"], dtype=np.float32)
    saved_tolerance = np.asarray(
        tolerance["dispatched_tolerance_axis"],
        dtype=np.float32,
    )
    if replica_cap.shape != (action_a.shape[1],) or saved_tolerance.shape != (
        action_a.shape[1],
    ):
        raise PhaseAContractError("replica tolerance width does not match actions")
    replica_dispatch_delta = np.max(np.abs(action_a - action_b), axis=0)
    replica_chunk_delta = np.max(np.abs(chunks_a - chunks_b), axis=(0, 1))
    saved_a_delta = np.max(np.abs(action_a - recorded), axis=0)
    saved_b_delta = np.max(np.abs(action_b - recorded), axis=0)
    saved_passed = bool(
        np.all(saved_a_delta <= saved_tolerance)
        and np.all(saved_b_delta <= saved_tolerance)
    )
    replica_passed = bool(
        np.all(replica_dispatch_delta <= replica_cap)
        and np.all(replica_chunk_delta <= replica_cap)
    )
    return {
        "passed": bool(replica_passed and saved_passed),
        "preflight": {"passed": True},
        "baseline_replicas": {
            "passed": replica_passed,
            "replica_a_instance_id": baseline_a["instance_id"],
            "replica_b_instance_id": baseline_b["instance_id"],
            "max_dispatched_action_abs_delta_axis": _float_list(replica_dispatch_delta),
            "max_anchor_chunk_abs_delta_axis": _float_list(replica_chunk_delta),
        },
        "replica_tolerance": dict(tolerance),
        "saved_action_alignment": {
            "passed": saved_passed,
            "replica_a_max_abs_delta_axis": _float_list(saved_a_delta),
            "replica_b_max_abs_delta_axis": _float_list(saved_b_delta),
        },
    }


def _validate_counterfactual_replicas(
    *,
    candidate_a: Mapping[str, Any],
    candidate_b: Mapping[str, Any],
    tolerance: Mapping[str, Any],
) -> dict[str, Any]:
    """Require a counterfactual response to reproduce below the frozen cap."""

    action_a = _finite_array(
        candidate_a["dispatched_actions"],
        label="counterfactual_replica_a",
        ndim=2,
    )
    action_b = _finite_array(
        candidate_b["dispatched_actions"],
        label="counterfactual_replica_b",
        ndim=2,
    )
    chunks_a = _finite_array(
        candidate_a["anchor_chunks"],
        label="counterfactual_replica_a_chunks",
        ndim=3,
    )
    chunks_b = _finite_array(
        candidate_b["anchor_chunks"],
        label="counterfactual_replica_b_chunks",
        ndim=3,
    )
    if action_a.shape != action_b.shape or chunks_a.shape != chunks_b.shape:
        raise PhaseAContractError("counterfactual replica output shapes differ")
    cap = np.asarray(tolerance["replica_noise_cap_axis"], dtype=np.float32)
    if cap.shape != (action_a.shape[1],):
        raise PhaseAContractError("counterfactual replica cap width does not match actions")
    dispatch_delta = np.max(np.abs(action_a - action_b), axis=0)
    chunk_delta = np.max(np.abs(chunks_a - chunks_b), axis=(0, 1))
    passed = bool(np.all(dispatch_delta <= cap) and np.all(chunk_delta <= cap))
    return {
        "passed": passed,
        "replica_a_instance_id": candidate_a["instance_id"],
        "replica_b_instance_id": candidate_b["instance_id"],
        "replica_noise_cap_axis": _float_list(cap),
        "max_dispatched_action_abs_delta_axis": _float_list(dispatch_delta),
        "max_anchor_chunk_abs_delta_axis": _float_list(chunk_delta),
    }


def _response_gate(
    *,
    baseline_actions: np.ndarray,
    candidate_actions: np.ndarray,
    baseline_anchor_chunks: np.ndarray,
    candidate_anchor_chunks: np.ndarray,
    action_threshold: np.ndarray,
    anchor_indices: Sequence[int],
) -> dict[str, Any]:
    if baseline_actions.shape != candidate_actions.shape:
        raise PhaseAContractError("counterfactual action shape differs from baseline")
    if baseline_anchor_chunks.shape != candidate_anchor_chunks.shape:
        raise PhaseAContractError("counterfactual chunk shape differs from baseline")
    action_delta = candidate_actions - baseline_actions
    responsive_frames = np.any(np.abs(action_delta) > action_threshold[None, :], axis=1)
    chunk_delta = candidate_anchor_chunks - baseline_anchor_chunks
    responsive_anchors = np.asarray(
        [
            bool(np.any(np.abs(delta) > action_threshold[None, :]))
            for delta in chunk_delta
        ],
        dtype=bool,
    )
    responsive_frame_fraction = float(np.mean(responsive_frames))
    responsive_anchor_count = int(np.sum(responsive_anchors))
    passed = bool(
        responsive_frame_fraction >= REQUIRED_RESPONSIVE_FRAME_FRACTION
        and responsive_anchor_count == ANCHOR_COUNT
    )
    all_deltas_within_threshold = bool(
        np.all(np.abs(action_delta) <= action_threshold[None, :])
        and np.all(np.abs(chunk_delta) <= action_threshold[None, None, :])
    )
    anchor_chunk_deltas = [
        {
            "frame_index": int(frame_index),
            "max_abs_delta": float(np.max(np.abs(delta))),
            "responsive": bool(responsive),
        }
        for frame_index, delta, responsive in zip(
            anchor_indices,
            chunk_delta,
            responsive_anchors,
            strict=True,
        )
    ]
    return {
        "passed": passed,
        "all_deltas_within_threshold": all_deltas_within_threshold,
        "gate": {
            "action_std_fraction": ACTION_STD_FRACTION,
            "responsive_frame_fraction": responsive_frame_fraction,
            "required_responsive_frame_fraction": REQUIRED_RESPONSIVE_FRAME_FRACTION,
            "anchor_count": ANCHOR_COUNT,
            "responsive_anchor_count": responsive_anchor_count,
            "passed": passed,
        },
        "anchor_chunk_deltas": anchor_chunk_deltas,
        "temporal_aggregated_action_deltas": [
            _float_list(value) for value in action_delta
        ],
    }


def _assess_support(
    *,
    condition: Mapping[str, Any],
    segment: Any,
    support_assessor: SupportAssessor | None,
) -> dict[str, Any]:
    if support_assessor is None:
        return {"status": condition["support_status"], "source": "condition"}
    assessed = support_assessor(condition, segment)
    if not isinstance(assessed, Mapping):
        raise PhaseAContractError("support_assessor must return a mapping")
    status = str(assessed.get("status", ""))
    if status not in _SUPPORTED_SUPPORT_STATUSES:
        raise PhaseAContractError(f"support_assessor returned unsupported status {status!r}")
    return _json_ready(dict(assessed))


def _evaluate_isolation_only(
    *,
    base_result: dict[str, Any],
    segment: Any,
    conditions: Sequence[Mapping[str, Any]],
    isolation_check: IsolationCheck | None,
) -> dict[str, Any]:
    isolation = (
        {"passed": True, "reason": "no_goal_condition_input_for_isolation_primitive"}
        if isolation_check is None
        else _json_ready(dict(isolation_check(segment, conditions)))
    )
    if not bool(isolation.get("passed", False)):
        return _artifact_invalid(
            base_result,
            stage="isolation",
            reason=str(isolation.get("reason", "isolation_check_failed")),
            extra_validity={"isolation": isolation},
        )
    base_result["artifact_validity"] = {
        "passed": True,
        "preflight": {"passed": True},
        "isolation": isolation,
    }
    base_result["status"] = "completed"
    return base_result


def _base_result(*, segment: Any, condition_records: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": ACT_GOAL_CONDITION_SENSITIVITY_RESULTS_SCHEMA,
        "status": "artifact_invalid",
        "evidence_kind": EVIDENCE_KIND,
        "diagnostic_only": True,
        "promotion_eligible": False,
        "closed_loop_claim": False,
        "direction": "not_identifiable_in_teacher_forced_replay",
        "primitive": str(_field(segment, "primitive", "unknown")),
        "segment_id": str(_field(segment, "segment_id", "unknown")),
        "conditions": condition_records,
        "artifact_validity": {"passed": False},
    }


def _artifact_invalid(
    result: dict[str, Any],
    *,
    stage: str,
    reason: str,
    extra_validity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    result["status"] = "artifact_invalid"
    result["artifact_validity"] = {
        "passed": False,
        "failure_stage": stage,
        "reason": reason,
        **dict(extra_validity or {}),
    }
    for payload in result["conditions"].values():
        payload.pop("classification", None)
    return result


def _condition_skeletons(conditions: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for index, value in enumerate(conditions):
        if isinstance(value, Mapping):
            condition_id = str(value.get("condition_id", f"condition_{index}"))
        else:
            condition_id = f"condition_{index}"
        output[condition_id] = {"condition_id": condition_id}
    return output


def _condition_record(condition: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "condition_id": str(condition["condition_id"]),
        "support_status": str(condition["support_status"]),
        "provenance": _json_ready(dict(condition.get("provenance", {}) or {})),
    }


def _read_observation(
    frame: Any,
    observation_reader: ObservationReader | None,
) -> Mapping[str, Any]:
    if observation_reader is not None:
        observation = observation_reader(frame)
    else:
        observation = _field(frame, "observation", None)
    if not isinstance(observation, Mapping):
        raise PhaseAContractError(
            "Stage-A needs an observation_reader or frame.observation mapping"
        )
    return observation


def _recorded_action(frame: Any) -> np.ndarray:
    for name in ("recorded_action", "actual_action", "action"):
        value = _field(frame, name, None)
        if value is not None:
            return np.asarray(value, dtype=np.float32).reshape(-1)
    raise PhaseAContractError("frame lacks recorded action")


def _chunk_actions(value: Any, *, label: str) -> np.ndarray:
    actions = _field(value, "actions", _field(value, "action_chunk", None))
    return _finite_array(actions, label=f"{label}.action_chunk", ndim=2)


def _anchor_indices(frame_count: int) -> tuple[int, int, int]:
    if frame_count < ANCHOR_COUNT:
        raise PhaseAContractError("Stage-A requires at least three anchor frames")
    return (0, frame_count // 2, frame_count - 1)


def _finite_array(value: Any, *, label: str, ndim: int) -> np.ndarray:
    if value is None:
        raise PhaseAContractError(f"{label} is missing")
    array = np.asarray(value, dtype=np.float32)
    if array.ndim != ndim or array.size == 0 or not np.isfinite(array).all():
        raise PhaseAContractError(
            f"{label} must be finite non-empty rank-{ndim}, got shape={array.shape}"
        )
    return array


def _field(value: Any, name: str, default: Any) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _int_field(value: Any, name: str) -> int:
    raw = _field(value, name, None)
    if isinstance(raw, bool):
        raise PhaseAContractError(f"{name} must be an integer")
    try:
        parsed = int(raw)
    except (TypeError, ValueError) as exc:
        raise PhaseAContractError(f"{name} must be an integer") from exc
    return parsed


def _float_list(values: np.ndarray) -> list[float]:
    return [float(value) for value in np.asarray(values, dtype=np.float32).reshape(-1)]


def _json_ready(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return _json_ready(value.tolist())
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise PhaseAContractError("artifact JSON cannot contain non-finite floats")
    return value


def _write_json_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(_json_ready(dict(payload)), handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def _release_cuda_cache() -> None:
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:  # pragma: no cover - torch is a runtime dependency.
        return


def run_act_goal_condition_sensitivity_audit(**kwargs: Any) -> dict[str, Any]:
    """Lazy facade for the file-orchestration entrypoint used by a thin CLI."""

    from testbed.eval.act_goal_condition_sensitivity_runner import (
        run_act_goal_condition_sensitivity_audit as _run,
    )

    return _run(**kwargs)


__all__ = [
    "ACT_GOAL_CONDITION_SENSITIVITY_MANIFEST_SCHEMA",
    "ACT_GOAL_CONDITION_SENSITIVITY_RESULTS_SCHEMA",
    "PhaseAContractError",
    "derive_replica_tolerance",
    "evaluate_goal_condition_sensitivity_segment",
    "run_act_goal_condition_sensitivity_audit",
    "write_goal_condition_sensitivity_artifact",
]
