"""Thin orchestration for the frozen Return goal-response stability audit.

Stable support modules own immutable lineage, input transformations and pure
temporal reconstruction.  This module only composes those facts with the
public ACT inference API.  Its diagnostic reset/cache experiments are evidence
about the already-invalid pairs; they never replace the fixed Stage-A class.
"""

from __future__ import annotations

import gc
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from testbed.data.recorded_act_replay import (
    RecordedActReplaySegment,
    join_recorded_act_replay_frames,
    split_stable_recorded_act_segments,
)
from testbed.eval.return_goal_response_stability_contract import (
    ACTION_STD_FRACTION,
    EVIDENCE_KIND,
    OUTPUT_ROOT_NAME,
    REQUIRED_RESPONSIVE_FRAME_FRACTION,
    RETURN_GOAL_RESPONSE_STABILITY_MANIFEST_SCHEMA,
    RETURN_GOAL_RESPONSE_STABILITY_RESULTS_SCHEMA,
    RETURN_INVALID_SEGMENT_IDS,
    ReturnGoalResponseStabilityAuditError,
    clean_code_record,
    field,
    finite_array,
    finite_vector,
    invalid_condition_from_stage_record,
    load_immutable_stage_context,
    mapping,
    report_markdown,
    source_record,
    write_artifact,
)
from testbed.eval.return_goal_response_stability_inputs import (
    audit_pre_action_observation_identity,
    audit_pre_action_observation_identity_from_path,
    audit_return_token_normalisation,
    read_segment_observations_from_path,
)
from testbed.eval.return_goal_response_stability_temporal import (
    derive_temporal_aggregation_diagnostics,
    normalise_temporal_contract,
    reconstruct_temporal_aggregated_actions,
)
from testbed.policies.act.inference import (
    build_act_adapter_config,
    describe_act_inference,
    load_act_policy,
)
from testbed.runtime.torch_performance import (
    configure_torch_performance,
    eval_torch_performance_config,
)

PolicyFactoryBuilder = Callable[[str], Any]
PolicyDescriber = Callable[[Any], Mapping[str, Any]]


def run_return_goal_response_stability_audit(
    *,
    stage_a_v2_output_root: str | Path,
    output_root: str | Path,
    device: str = "cuda",
    policy_factory_builder: PolicyFactoryBuilder | None = None,
    policy_describer: PolicyDescriber | None = None,
    require_clean_worktree: bool = True,
) -> dict[str, Any]:
    """Audit exactly two immutable v2 Return pairs in a no-overwrite root."""

    destination = Path(output_root).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(
            f"Return response-stability output already exists: {destination}"
        )
    clean_code = clean_code_record()
    if require_clean_worktree and not bool(clean_code["worktree_clean"]):
        raise RuntimeError(
            "Return response-stability audit requires a clean Git worktree"
        )
    context = load_immutable_stage_context(stage_a_v2_output_root)
    performance = eval_torch_performance_config(context["eval_config"].get("eval", {}))
    configure_torch_performance(performance, device=str(device))
    _verify_stage_performance(
        stage_performance=context["stage_manifest"].get("torch_performance"),
        resolved=performance.as_config_dict(),
    )
    expected_temporal = _return_stage_temporal_contract(
        manifest=context["stage_manifest"],
        checkpoint=context["paths"]["checkpoint"],
    )
    segments = _load_return_segments(
        rollout_hdf5_path=context["paths"]["rollout_hdf5"],
        rollout_jsonl_path=context["paths"]["rollout_jsonl"],
    )
    factory = policy_factory_builder or _production_policy_factory_builder(
        eval_config=context["eval_config"],
        checkpoint=context["paths"]["checkpoint"],
        stats_path=context["paths"]["stats"],
        device=str(device),
    )
    describer = policy_describer or describe_act_inference
    policy = mapping(context["eval_config"].get("policy"), "resolved eval policy")
    image_mask_config = dict(policy.get("image_mask", {}) or {})

    segment_results: list[dict[str, Any]] = []
    for record in context["invalid_records"]:
        baseline_id = str(record["segment"]["segment_id"])
        alternate_id = str(record["alternate_segment"]["segment_id"])
        try:
            baseline_segment = segments[baseline_id]
            alternate_segment = segments[alternate_id]
        except KeyError as exc:
            raise ReturnGoalResponseStabilityAuditError(
                f"immutable Stage-A segment is absent from source replay: {exc.args[0]}"
            ) from exc
        segment_results.append(
            _audit_segment(
                stage_record=record,
                baseline_segment=baseline_segment,
                alternate_segment=alternate_segment,
                hdf5_path=context["paths"]["rollout_hdf5"],
                camera_names=context["camera_names"],
                image_mask_config=image_mask_config,
                low_dim_keys=context["low_dim_keys"],
                norm_stats=context["norm_stats"],
                expected_temporal_contract=expected_temporal,
                policy_factory_builder=factory,
                policy_describer=describer,
            )
        )
    status = (
        "completed"
        if all(item.get("status") == "completed" for item in segment_results)
        else "artifact_invalid"
    )
    manifest = _manifest(
        context=context,
        clean_code=clean_code,
        status=status,
        performance=performance.as_config_dict(),
    )
    payload = {
        "schema": RETURN_GOAL_RESPONSE_STABILITY_RESULTS_SCHEMA,
        "status": status,
        "evidence_kind": EVIDENCE_KIND,
        "diagnostic_only": True,
        "promotion_eligible": False,
        "fixed_required_responsive_frame_fraction": REQUIRED_RESPONSIVE_FRAME_FRACTION,
        "segments": segment_results,
    }
    write_artifact(
        output_root=destination,
        manifest=manifest,
        segment_results=payload,
        report_markdown=report_markdown(status=status, segments=segment_results),
    )
    return {"status": status, "output_root": str(destination), "manifest": manifest}


def _audit_segment(
    *,
    stage_record: Mapping[str, Any],
    baseline_segment: RecordedActReplaySegment,
    alternate_segment: RecordedActReplaySegment,
    hdf5_path: Path,
    camera_names: Sequence[str],
    image_mask_config: Mapping[str, Any],
    low_dim_keys: Sequence[str],
    norm_stats: Mapping[str, Any],
    expected_temporal_contract: Mapping[str, Any],
    policy_factory_builder: PolicyFactoryBuilder,
    policy_describer: PolicyDescriber,
) -> dict[str, Any]:
    invalid_condition = invalid_condition_from_stage_record(stage_record)
    stage_result = mapping(stage_record["result"], "Stage-A result")
    stage_baseline = mapping(stage_result.get("baseline"), "Stage-A baseline")
    stage_threshold = finite_vector(
        stage_baseline.get("response_threshold"), label="Stage-A response threshold"
    )
    stage_delta = finite_array(
        invalid_condition.get("temporal_aggregated_action_deltas"),
        label="Stage-A temporal action deltas",
        ndim=2,
    )
    if stage_delta.shape != (baseline_segment.frame_count, stage_threshold.size):
        raise ReturnGoalResponseStabilityAuditError(
            "Stage-A temporal action delta shape disagrees with target segment"
        )
    observation_identity = audit_pre_action_observation_identity_from_path(
        hdf5_path=hdf5_path,
        frames=baseline_segment.frames,
        camera_names=camera_names,
        image_mask_config=image_mask_config,
    )
    observations = read_segment_observations_from_path(
        hdf5_path=hdf5_path,
        segment=baseline_segment,
        camera_names=camera_names,
    )
    token_audit = audit_return_token_normalisation(
        observations=observations,
        token=np.asarray(alternate_segment.token, dtype=np.float32),
        low_dim_keys=low_dim_keys,
        norm_stats=norm_stats,
    )
    input_status = _input_causal_status(
        token_audit=token_audit,
        observation_identity=observation_identity,
    )
    if input_status is not None:
        return _input_mismatch_result(
            baseline_segment=baseline_segment,
            alternate_segment=alternate_segment,
            stage_record=stage_record,
            token_audit=token_audit,
            observation_identity=observation_identity,
            causal_status=input_status,
        )

    baseline_policy = policy_factory_builder(f"{baseline_segment.segment_id}:baseline")
    alternate_policy = policy_factory_builder(f"{baseline_segment.segment_id}:alternate")
    try:
        baseline_description = dict(policy_describer(baseline_policy))
        alternate_description = dict(policy_describer(alternate_policy))
        contract = _validate_live_policy_contract(
            baseline_description=baseline_description,
            alternate_description=alternate_description,
            expected_temporal_contract=expected_temporal_contract,
            norm_stats=norm_stats,
            stage_baseline=stage_baseline,
        )
        baseline_stream = _collect_policy_stream(
            policy=baseline_policy,
            observations=observations,
            token_key=baseline_segment.model_token_key,
            token=np.asarray(baseline_segment.token, dtype=np.float32),
        )
        alternate_stream = _collect_policy_stream(
            policy=alternate_policy,
            observations=observations,
            token_key=baseline_segment.model_token_key,
            token=np.asarray(alternate_segment.token, dtype=np.float32),
        )
        alternate_predict_only = _collect_predict_only_stream(
            policy=alternate_policy,
            observations=observations,
            token_key=baseline_segment.model_token_key,
            token=np.asarray(alternate_segment.token, dtype=np.float32),
        )
    finally:
        del baseline_policy
        del alternate_policy
        gc.collect()
        _release_cuda_cache()

    tolerances = _stage_replay_tolerances(stage_record, action_dim=stage_threshold.size)
    reconstruction = _verify_actual_temporal_reconstruction(
        baseline_stream=baseline_stream,
        alternate_stream=alternate_stream,
        contract=contract,
        dispatched_tolerance=tolerances["dispatched_tolerance_axis"],
    )
    replay_delta = alternate_stream["actions"] - baseline_stream["actions"]
    replay_stage_match = _verify_immutable_stage_replay(
        stage_delta=stage_delta,
        replay_delta=replay_delta,
        action_threshold=stage_threshold,
        replica_noise_cap=tolerances["replica_noise_cap_axis"],
    )
    chunk_nonadvancing = _verify_chunk_nonadvancing(
        interleaved_actions=alternate_stream["actions"],
        predict_only_actions=alternate_predict_only,
        replica_noise_cap=tolerances["replica_noise_cap_axis"],
    )
    temporal = derive_temporal_aggregation_diagnostics(
        baseline_chunks=baseline_stream["chunks"],
        alternate_chunks=alternate_stream["chunks"],
        action_threshold=stage_threshold,
        temporal_contract=contract,
    )
    stage_gate = mapping(invalid_condition.get("response_gate"), "Stage-A response gate")
    temporal["stage_a_replayed_response_fraction"] = float(
        stage_gate["responsive_frame_fraction"]
    )
    temporal["replayed_response_fraction"] = float(
        np.mean(np.any(np.abs(replay_delta) > stage_threshold[None, :], axis=1))
    )
    integrity_passed = bool(
        reconstruction["passed"]
        and replay_stage_match["passed"]
        and chunk_nonadvancing["passed"]
    )
    return {
        "schema": RETURN_GOAL_RESPONSE_STABILITY_RESULTS_SCHEMA,
        "status": "completed" if integrity_passed else "artifact_invalid",
        "baseline_segment": _segment_record(baseline_segment),
        "alternate_segment": _segment_record(alternate_segment),
        "historical_stage_a": {
            "classification": "goal_response_invalid",
            "response_gate": dict(stage_gate),
            "support": dict(invalid_condition["support"]),
            "replica_validity": dict(invalid_condition["replica_validity"]),
        },
        "token_normalisation": token_audit,
        "pre_action_observation_identity": observation_identity,
        "segment_reset_boundary": _segment_boundary_record(baseline_segment),
        "live_inference": {
            "baseline": baseline_description,
            "alternate": alternate_description,
            "temporal_contract": contract,
        },
        "temporal_reconstruction": reconstruction,
        "replay_matches_immutable_stage_a": replay_stage_match,
        "predict_action_chunk_cache_check": chunk_nonadvancing,
        "temporal_aggregation": temporal,
        "causal_status": _temporal_causal_status(
            integrity_passed=integrity_passed,
            temporal=temporal,
        ),
    }


def _input_mismatch_result(
    *,
    baseline_segment: RecordedActReplaySegment,
    alternate_segment: RecordedActReplaySegment,
    stage_record: Mapping[str, Any],
    token_audit: Mapping[str, Any],
    observation_identity: Mapping[str, Any],
    causal_status: Mapping[str, Any],
) -> dict[str, Any]:
    """Record a diagnosed input mismatch; do not turn it into a new class."""

    return {
        "schema": RETURN_GOAL_RESPONSE_STABILITY_RESULTS_SCHEMA,
        "status": "completed",
        "baseline_segment": _segment_record(baseline_segment),
        "alternate_segment": _segment_record(alternate_segment),
        "historical_stage_a": {
            "classification": "goal_response_invalid",
            "source_record_present": bool(stage_record),
        },
        "token_normalisation": dict(token_audit),
        "pre_action_observation_identity": dict(observation_identity),
        "causal_status": dict(causal_status),
    }


def _input_causal_status(
    *,
    token_audit: Mapping[str, Any],
    observation_identity: Mapping[str, Any],
) -> dict[str, Any] | None:
    findings: list[str] = []
    if token_audit.get("status") != "passed":
        findings.append("normalization_mismatch")
    if observation_identity.get("status") != "passed":
        findings.append("observation_history_mismatch")
    if not findings:
        return None
    return {
        "status": findings[0],
        "additional_statuses": findings[1:],
        "reason": "frozen input contract did not reproduce before policy replay",
    }


def _temporal_causal_status(
    *,
    integrity_passed: bool,
    temporal: Mapping[str, Any],
) -> dict[str, str]:
    if not integrity_passed:
        return {
            "status": "not_explained_by_frozen_inputs",
            "finding": "audit_artifact_invalid",
            "reason": "checkpoint replay or cache control did not reproduce immutable Stage-A",
        }
    if bool(temporal["temporal_dilution_explains_gate_failure"]):
        return {
            "status": "temporal_aggregation_dilution",
            "reason": "raw current-query response passes 80 percent while actual aggregation does not",
        }
    result = {
        "status": "not_explained_by_frozen_inputs",
        "reason": "input contract and temporal cache checks passed without a sufficient dilution explanation",
    }
    if float(temporal["raw_current_query_response_fraction"]) < REQUIRED_RESPONSIVE_FRAME_FRACTION:
        result["finding"] = "raw_frozen_policy_response_intermittent"
    return result


def _collect_policy_stream(
    *,
    policy: Any,
    observations: Sequence[Mapping[str, Any]],
    token_key: str | None,
    token: np.ndarray,
) -> dict[str, np.ndarray]:
    """Run the public non-advancing chunk query before each stateful predict."""

    if not token_key:
        raise ReturnGoalResponseStabilityAuditError("Return segment lacks model token key")
    reset = getattr(policy, "reset", None)
    predict_chunk = getattr(policy, "predict_action_chunk", None)
    predict = getattr(policy, "predict", None)
    if not callable(reset) or not callable(predict_chunk) or not callable(predict):
        raise ReturnGoalResponseStabilityAuditError(
            "audit policy must implement reset(), predict_action_chunk(), and predict()"
        )
    reset()
    chunks: list[np.ndarray] = []
    actions: list[np.ndarray] = []
    for index, source_observation in enumerate(observations):
        observation = dict(source_observation)
        observation[token_key] = np.asarray(token, dtype=np.float32).copy()
        raw_chunk = predict_chunk(observation)
        chunk = finite_array(
            field(raw_chunk, "actions", field(raw_chunk, "action_chunk", None)),
            label=f"policy chunk {index}",
            ndim=2,
        )
        action = finite_vector(predict(observation), label=f"policy action {index}")
        if action.shape != (chunk.shape[1],):
            raise ReturnGoalResponseStabilityAuditError(
                "policy action width differs from chunk action width"
            )
        chunks.append(chunk)
        actions.append(action)
    return {"chunks": np.stack(chunks, axis=0), "actions": np.stack(actions, axis=0)}


def _collect_predict_only_stream(
    *,
    policy: Any,
    observations: Sequence[Mapping[str, Any]],
    token_key: str | None,
    token: np.ndarray,
) -> np.ndarray:
    """Control replay used only to prove chunk inspection did not advance cache."""

    if not token_key:
        raise ReturnGoalResponseStabilityAuditError("Return segment lacks model token key")
    reset = getattr(policy, "reset", None)
    predict = getattr(policy, "predict", None)
    if not callable(reset) or not callable(predict):
        raise ReturnGoalResponseStabilityAuditError("audit policy must implement reset() and predict()")
    reset()
    actions: list[np.ndarray] = []
    for index, source_observation in enumerate(observations):
        observation = dict(source_observation)
        observation[token_key] = np.asarray(token, dtype=np.float32).copy()
        actions.append(finite_vector(predict(observation), label=f"predict-only action {index}"))
    return np.stack(actions, axis=0)


def _validate_live_policy_contract(
    *,
    baseline_description: Mapping[str, Any],
    alternate_description: Mapping[str, Any],
    expected_temporal_contract: Mapping[str, Any],
    norm_stats: Mapping[str, Any],
    stage_baseline: Mapping[str, Any],
) -> dict[str, Any]:
    baseline_contract = normalise_temporal_contract(
        mapping(baseline_description.get("temporal_aggregation"), "baseline temporal contract")
    )
    alternate_contract = normalise_temporal_contract(
        mapping(alternate_description.get("temporal_aggregation"), "alternate temporal contract")
    )
    if baseline_contract != alternate_contract or baseline_contract != dict(expected_temporal_contract):
        raise ReturnGoalResponseStabilityAuditError(
            "loaded policy temporal contract differs from immutable Stage-A contract"
        )
    if not baseline_contract["enabled"]:
        raise ReturnGoalResponseStabilityAuditError("immutable Stage-A Return replay requires temporal aggregation")
    action_std = finite_vector(norm_stats.get("action_std"), label="dataset_stats action_std")
    described_std = finite_vector(baseline_description.get("action_std"), label="loaded policy action_std")
    stage_std = finite_vector(stage_baseline.get("action_std"), label="Stage-A action_std")
    if not np.array_equal(action_std, described_std) or not np.array_equal(action_std, stage_std):
        raise ReturnGoalResponseStabilityAuditError(
            "loaded policy action_std disagrees with immutable dataset_stats or Stage-A"
        )
    return baseline_contract


def _stage_replay_tolerances(
    stage_record: Mapping[str, Any],
    *,
    action_dim: int,
) -> dict[str, np.ndarray]:
    result = mapping(stage_record.get("result"), "stage result")
    validity = mapping(result.get("artifact_validity"), "stage artifact validity")
    stage_tolerance = mapping(validity.get("replica_tolerance"), "stage replica tolerance")
    dispatched = finite_vector(
        stage_tolerance.get("dispatched_tolerance_axis"),
        label="Stage-A dispatched tolerance",
    )
    replica_cap = finite_vector(
        stage_tolerance.get("replica_noise_cap_axis"),
        label="Stage-A replica noise cap",
    )
    if (
        dispatched.shape != (action_dim,)
        or replica_cap.shape != (action_dim,)
        or np.any(dispatched <= 0.0)
        or np.any(replica_cap <= 0.0)
    ):
        raise ReturnGoalResponseStabilityAuditError("Stage-A replay tolerances are invalid")
    return {"dispatched_tolerance_axis": dispatched, "replica_noise_cap_axis": replica_cap}


def _verify_actual_temporal_reconstruction(
    *,
    baseline_stream: Mapping[str, np.ndarray],
    alternate_stream: Mapping[str, np.ndarray],
    contract: Mapping[str, Any],
    dispatched_tolerance: np.ndarray,
) -> dict[str, Any]:
    baseline_reconstructed = reconstruct_temporal_aggregated_actions(
        chunks=baseline_stream["chunks"], temporal_contract=contract
    )
    alternate_reconstructed = reconstruct_temporal_aggregated_actions(
        chunks=alternate_stream["chunks"], temporal_contract=contract
    )
    baseline_delta = np.max(
        np.abs(baseline_stream["actions"] - baseline_reconstructed), axis=0
    )
    alternate_delta = np.max(
        np.abs(alternate_stream["actions"] - alternate_reconstructed), axis=0
    )
    return {
        "passed": bool(
            np.all(baseline_delta <= dispatched_tolerance)
            and np.all(alternate_delta <= dispatched_tolerance)
        ),
        "verification": "actual stateful predict stream compared with independently reconstructed public chunks",
        "baseline_predict_vs_reconstructed_max_abs_delta_axis": _float_list(baseline_delta),
        "alternate_predict_vs_reconstructed_max_abs_delta_axis": _float_list(alternate_delta),
        "tolerance_axis": _float_list(dispatched_tolerance),
    }


def _verify_immutable_stage_replay(
    *,
    stage_delta: np.ndarray,
    replay_delta: np.ndarray,
    action_threshold: np.ndarray,
    replica_noise_cap: np.ndarray,
) -> dict[str, Any]:
    max_delta = np.max(np.abs(replay_delta - stage_delta), axis=0)
    stage_mask = np.any(np.abs(stage_delta) > action_threshold[None, :], axis=1)
    replay_mask = np.any(np.abs(replay_delta) > action_threshold[None, :], axis=1)
    return {
        "passed": bool(np.all(max_delta <= replica_noise_cap) and np.array_equal(stage_mask, replay_mask)),
        "max_abs_delta_axis": _float_list(max_delta),
        "pre_registered_replica_noise_cap_axis": _float_list(replica_noise_cap),
        "response_mask_matches_immutable_stage_a": bool(np.array_equal(stage_mask, replay_mask)),
    }


def _verify_chunk_nonadvancing(
    *,
    interleaved_actions: np.ndarray,
    predict_only_actions: np.ndarray,
    replica_noise_cap: np.ndarray,
) -> dict[str, Any]:
    max_delta = np.max(np.abs(interleaved_actions - predict_only_actions), axis=0)
    return {
        "passed": bool(np.all(max_delta <= replica_noise_cap)),
        "verification": "reset control compares predict_action_chunk then predict against predict-only stream",
        "role": "diagnostic cache-state check; not a Stage-A classification replay",
        "max_abs_delta_axis": _float_list(max_delta),
        "pre_registered_replica_noise_cap_axis": _float_list(replica_noise_cap),
    }


def _load_return_segments(
    *,
    rollout_hdf5_path: Path,
    rollout_jsonl_path: Path,
) -> dict[str, RecordedActReplaySegment]:
    frames = join_recorded_act_replay_frames(
        rollout_hdf5_path=rollout_hdf5_path,
        rollout_jsonl_path=rollout_jsonl_path,
        skills=("dig", "return", "carry", "dump"),
    )
    result = {
        segment.segment_id: segment
        for segment in split_stable_recorded_act_segments(frames)
        if segment.skill_name == "return"
    }
    if not result:
        raise ReturnGoalResponseStabilityAuditError("source rollout has no stable Return segments")
    return result


def _production_policy_factory_builder(
    *,
    eval_config: Mapping[str, Any],
    checkpoint: Path,
    stats_path: Path,
    device: str,
) -> PolicyFactoryBuilder:
    policy = mapping(eval_config.get("policy"), "resolved eval policy")
    task = mapping(eval_config.get("task"), "resolved eval task")
    adapter_config = build_act_adapter_config(
        config=eval_config,
        camera_names=[str(value) for value in task["camera_names"]],
        equipment_model=str(task["equipment_model"]),
        max_episode_len=int(task["episode_len"]),
        low_dim_keys=[str(value) for value in policy["return_low_dim_keys"]],
        act_params=mapping(policy.get("act_params"), "resolved eval act_params"),
        outcome_head_config=dict(policy.get("return_outcome_head", {}) or {}),
        image_mask_config=dict(policy.get("image_mask", {}) or {}),
    )

    def build(_label: str) -> Any:
        return load_act_policy(
            ckpt_path=checkpoint,
            policy_config=adapter_config,
            norm_stats_path=stats_path,
            temporal_agg=True,
            device=device,
        )

    return build


def _return_stage_temporal_contract(
    *,
    manifest: Mapping[str, Any],
    checkpoint: Path,
) -> dict[str, Any]:
    instances = mapping(manifest.get("inference_instances"), "Stage-A inference instances")
    matches: list[dict[str, Any]] = []
    for value in instances.values():
        if not isinstance(value, Mapping):
            continue
        checkpoint_record = value.get("checkpoint")
        if not isinstance(checkpoint_record, Mapping):
            continue
        if Path(str(checkpoint_record.get("path", ""))).expanduser() != checkpoint:
            continue
        matches.append(normalise_temporal_contract(mapping(value.get("temporal_aggregation"), "Stage-A temporal contract")))
    if not matches or any(item != matches[0] for item in matches[1:]):
        raise ReturnGoalResponseStabilityAuditError(
            "Stage-A Return inference instances lack one consistent temporal contract"
        )
    return matches[0]


def _segment_boundary_record(segment: RecordedActReplaySegment) -> dict[str, Any]:
    first = segment.frames[0]
    switch_reason = str(field(first, "skill_switch_reason", "")).strip()
    policy_restarted = bool(field(first, "policy_restarted", False))
    source_boundary = bool(switch_reason or policy_restarted)
    return {
        "status": "passed" if source_boundary else "unproven",
        "stage_a_policy_reset_at_segment_entry": True,
        "recorded_skill_switch_reason": switch_reason or None,
        "recorded_policy_restarted": policy_restarted,
        "source_boundary_observed": source_boundary,
        "semantic_limit": (
            "the recorded boundary supports the Stage-A reset point; it does not "
            "reconstruct unrecorded prior Return-policy cache state"
        ),
    }


def _verify_stage_performance(*, stage_performance: Any, resolved: Mapping[str, Any]) -> None:
    stage = mapping(stage_performance, "Stage-A torch performance")
    required = {"allow_tf32", "cudnn_benchmark", "matmul_precision"}
    if not required <= set(stage):
        raise ReturnGoalResponseStabilityAuditError("Stage-A torch performance record is incomplete")
    if {key: stage[key] for key in required} != {key: resolved[key] for key in required}:
        raise ReturnGoalResponseStabilityAuditError(
            "current replay performance settings differ from immutable Stage-A settings"
        )


def _manifest(
    *,
    context: Mapping[str, Any],
    clean_code: Mapping[str, Any],
    status: str,
    performance: Mapping[str, Any],
) -> dict[str, Any]:
    paths = context["paths"]
    stage_paths = context["stage_paths"]
    return {
        "schema": RETURN_GOAL_RESPONSE_STABILITY_MANIFEST_SCHEMA,
        "status": status,
        "evidence_kind": EVIDENCE_KIND,
        "diagnostic_only": True,
        "promotion_eligible": False,
        "closed_loop_claim": False,
        "direction": "not_identifiable_in_teacher_forced_replay",
        "fixed_gate": {
            "required_responsive_frame_fraction": REQUIRED_RESPONSIVE_FRAME_FRACTION,
            "action_std_fraction": ACTION_STD_FRACTION,
            "change_policy": "no_threshold_change_permitted",
        },
        "target_segment_ids": list(RETURN_INVALID_SEGMENT_IDS),
        "source_lineage": {
            "stage_a_v2_manifest": source_record(stage_paths["manifest"]),
            "stage_a_v2_baseline": source_record(stage_paths["baseline"]),
            "stage_a_v2_return": source_record(stage_paths["return"]),
            "source_results_root": str(context["source_results_root"]),
            "eval_resolved_config": source_record(paths["eval_config"]),
            "eval_run_metadata": source_record(paths["eval_metadata"]),
            "rollout_jsonl": source_record(paths["rollout_jsonl"]),
            "rollout_hdf5": source_record(paths["rollout_hdf5"]),
            "return_training_config": source_record(paths["return_training_config"]),
            "return_checkpoint": source_record(paths["checkpoint"]),
            "return_dataset_stats": source_record(paths["stats"]),
            "code": dict(clean_code),
        },
        "torch_performance": dict(performance),
        "output_files": ["manifest.json", "return_segments.json", "report.md"],
    }


def _segment_record(segment: RecordedActReplaySegment) -> dict[str, Any]:
    return {
        "segment_id": segment.segment_id,
        "token_sha256": segment.token_sha256,
        "token_source": segment.token_source,
        "start_action_step_id": segment.start_action_step_id,
        "end_action_step_id": segment.end_action_step_id,
        "frame_count": segment.frame_count,
    }


def _float_list(values: np.ndarray) -> list[float]:
    return [float(value) for value in np.asarray(values, dtype=np.float32).reshape(-1)]


def _release_cuda_cache() -> None:
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


__all__ = [
    "OUTPUT_ROOT_NAME",
    "RETURN_GOAL_RESPONSE_STABILITY_MANIFEST_SCHEMA",
    "RETURN_GOAL_RESPONSE_STABILITY_RESULTS_SCHEMA",
    "RETURN_INVALID_SEGMENT_IDS",
    "audit_pre_action_observation_identity",
    "audit_return_token_normalisation",
    "derive_temporal_aggregation_diagnostics",
    "reconstruct_temporal_aggregated_actions",
    "run_return_goal_response_stability_audit",
]
