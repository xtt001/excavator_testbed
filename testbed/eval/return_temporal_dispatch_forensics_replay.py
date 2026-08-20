"""Frozen-artifact replay for :mod:`return_temporal_dispatch_forensics`.

This module owns path verification and checkpoint replay.  The sibling module
owns the pure contributor ranking; keeping the two separate prevents a
large read-only forensic runner from becoming the semantic source of the
temporal dispatch calculation.
"""

from __future__ import annotations

import gc
import json
import math
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
    EVIDENCE_KIND,
    REQUIRED_RESPONSIVE_FRAME_FRACTION,
    RETURN_GOAL_RESPONSE_STABILITY_MANIFEST_SCHEMA,
    RETURN_GOAL_RESPONSE_STABILITY_RESULTS_SCHEMA,
    RETURN_INVALID_SEGMENT_IDS,
    finite_array,
    finite_vector,
    invalid_condition_from_stage_record,
    load_immutable_stage_context,
    mapping,
    source_record,
    verify_source_record,
)
from testbed.eval.return_goal_response_stability_inputs import (
    read_segment_observations_from_path,
)
from testbed.eval.return_goal_response_stability_temporal import (
    normalise_temporal_contract,
    reconstruct_temporal_aggregated_actions,
)
from testbed.eval.return_temporal_dispatch_forensics import (
    HISTORICAL_CACHE_NUMERIC_TOLERANCE,
    RETURN_TEMPORAL_DISPATCH_FORENSICS_SCHEMA,
    ReturnTemporalDispatchForensicsError,
    collect_public_policy_stream,
    derive_return_temporal_dispatch_forensics,
    proposed_temporal_dispatch_strategies,
    validate_historical_cache_reconstruction,
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


def run_return_temporal_dispatch_forensics_replay(
    *,
    return_stability_output_root: str | Path,
    device: str = "cuda",
    policy_factory_builder: PolicyFactoryBuilder | None = None,
    policy_describer: PolicyDescriber | None = None,
) -> dict[str, Any]:
    """Reconstruct the two immutable failures without writing any files.

    Before interpreting a single contributor, this validates the prior
    no-overwrite artifact, its source-v2 lineage, the historical cache summary,
    public replay reconstruction, and the Stage-A response mask.  A return
    value is intentionally in-memory only; callers decide whether and where to
    preserve a later audit artifact.
    """

    stability = _load_immutable_stability_context(return_stability_output_root)
    stage_context = load_immutable_stage_context(stability["stage_a_v2_root"])
    _validate_stability_stage_lineage(stability=stability, stage_context=stage_context)
    performance = eval_torch_performance_config(
        stage_context["eval_config"].get("eval", {})
    )
    configure_torch_performance(performance, device=str(device))
    _validate_stage_performance(
        stage_context["stage_manifest"].get("torch_performance"),
        performance.as_config_dict(),
    )
    segments = _load_return_segments(
        rollout_hdf5_path=stage_context["paths"]["rollout_hdf5"],
        rollout_jsonl_path=stage_context["paths"]["rollout_jsonl"],
    )
    factory = policy_factory_builder or _production_policy_factory_builder(
        eval_config=stage_context["eval_config"],
        checkpoint=stage_context["paths"]["checkpoint"],
        stats_path=stage_context["paths"]["stats"],
        device=str(device),
    )
    describer = policy_describer or describe_act_inference

    records = {
        str(record["segment"]["segment_id"]): record
        for record in stage_context["invalid_records"]
    }
    results: list[dict[str, Any]] = []
    for segment_id in RETURN_INVALID_SEGMENT_IDS:
        stage_record = records.get(segment_id)
        stability_record = stability["segments_by_baseline"].get(segment_id)
        if stage_record is None or stability_record is None:
            raise ReturnTemporalDispatchForensicsError(
                f"immutable target segment is missing: {segment_id}"
            )
        results.append(
            _run_segment_forensics(
                stage_record=stage_record,
                stability_record=stability_record,
                segments=segments,
                stage_context=stage_context,
                policy_factory_builder=factory,
                policy_describer=describer,
            )
        )
    status = (
        "completed"
        if all(item["status"] == "completed" for item in results)
        else "artifact_invalid"
    )
    return {
        "schema": RETURN_TEMPORAL_DISPATCH_FORENSICS_SCHEMA,
        "status": status,
        "evidence_kind": EVIDENCE_KIND,
        "diagnostic_only": True,
        "promotion_eligible": False,
        "closed_loop_claim": False,
        "fixed_required_responsive_frame_fraction": REQUIRED_RESPONSIVE_FRAME_FRACTION,
        "input_artifact": {
            "return_goal_response_stability": source_record(
                stability["root"] / "return_segments.json"
            ),
            "stage_a_v2": source_record(stability["stage_a_v2_root"] / "manifest.json"),
        },
        "torch_performance": performance.as_config_dict(),
        "segments": results,
        "proposed_temporal_dispatch_strategies": proposed_temporal_dispatch_strategies(
            temporal_contract=results[0]["temporal_contract"]
        ),
        "output_policy": "read_only_in_memory_result_no_artifact_written",
    }


def _run_segment_forensics(
    *,
    stage_record: Mapping[str, Any],
    stability_record: Mapping[str, Any],
    segments: Mapping[str, RecordedActReplaySegment],
    stage_context: Mapping[str, Any],
    policy_factory_builder: PolicyFactoryBuilder,
    policy_describer: PolicyDescriber,
) -> dict[str, Any]:
    baseline_id = str(
        mapping(stage_record.get("segment"), "Stage-A baseline segment")["segment_id"]
    )
    alternate_id = str(
        mapping(stage_record.get("alternate_segment"), "Stage-A alternate segment")[
            "segment_id"
        ]
    )
    baseline_segment = _segment_or_error(segments, baseline_id)
    alternate_segment = _segment_or_error(segments, alternate_id)
    stage_result = mapping(stage_record.get("result"), "Stage-A result")
    stage_baseline = mapping(stage_result.get("baseline"), "Stage-A baseline")
    threshold = finite_vector(
        stage_baseline.get("response_threshold"), label="Stage-A response threshold"
    )
    historical = _validate_historical_stability_record(
        stability_record=stability_record,
        segment_id=baseline_id,
        expected_frame_count=baseline_segment.frame_count,
    )
    expected_contract = normalise_temporal_contract(
        mapping(
            historical["temporal_aggregation"].get("temporal_contract"),
            "historical temporal contract",
        )
    )
    observations = read_segment_observations_from_path(
        hdf5_path=stage_context["paths"]["rollout_hdf5"],
        segment=baseline_segment,
        camera_names=stage_context["camera_names"],
    )
    baseline_description, baseline_stream = _collect_one_policy_stream(
        label=f"{baseline_id}:forensic-baseline",
        policy_factory_builder=policy_factory_builder,
        policy_describer=policy_describer,
        observations=observations,
        token_key=baseline_segment.model_token_key,
        token=np.asarray(baseline_segment.token, dtype=np.float32),
    )
    alternate_description, alternate_stream = _collect_one_policy_stream(
        label=f"{baseline_id}:forensic-alternate",
        policy_factory_builder=policy_factory_builder,
        policy_describer=policy_describer,
        observations=observations,
        token_key=baseline_segment.model_token_key,
        token=np.asarray(alternate_segment.token, dtype=np.float32),
    )
    live_contract = _validate_live_temporal_contract(
        baseline_description=baseline_description,
        alternate_description=alternate_description,
        expected_contract=expected_contract,
    )
    tolerances = _stage_tolerances(stage_record, action_dim=threshold.size)
    public_reconstruction = _validate_public_reconstruction(
        baseline_stream=baseline_stream,
        alternate_stream=alternate_stream,
        contract=live_contract,
        tolerance=tolerances["dispatched_tolerance_axis"],
    )
    stage_replay = _validate_stage_replay(
        stage_record=stage_record,
        alternate_actions=alternate_stream["actions"],
        baseline_actions=baseline_stream["actions"],
        action_threshold=threshold,
        replica_noise_cap=tolerances["replica_noise_cap_axis"],
    )
    cache_validation = validate_historical_cache_reconstruction(
        historical_cache_contributors=historical["temporal_aggregation"][
            "cache_contributors"
        ],
        baseline_chunks=baseline_stream["chunks"],
        alternate_chunks=alternate_stream["chunks"],
        action_threshold=threshold,
        temporal_contract=live_contract,
    )
    evidence = derive_return_temporal_dispatch_forensics(
        baseline_chunks=baseline_stream["chunks"],
        alternate_chunks=alternate_stream["chunks"],
        action_threshold=threshold,
        temporal_contract=live_contract,
        action_step_ids=[
            int(frame.action_step_id) for frame in baseline_segment.frames
        ],
    )
    historical_fraction = float(
        historical["temporal_aggregation"]["temporal_aggregated_response_fraction"]
    )
    fraction_match = math.isclose(
        float(evidence["temporal_aggregated_response_fraction"]),
        historical_fraction,
        rel_tol=0.0,
        abs_tol=HISTORICAL_CACHE_NUMERIC_TOLERANCE,
    )
    integrity_passed = bool(
        public_reconstruction["passed"]
        and stage_replay["passed"]
        and cache_validation["passed"]
        and fraction_match
    )
    return {
        "segment_id": baseline_id,
        "alternate_segment_id": alternate_id,
        "status": "completed" if integrity_passed else "artifact_invalid",
        "historical_validation": {
            "prior_input_and_cache_controls_passed": True,
            "historical_causal_status": historical["causal_status"],
            "historical_temporal_response_fraction": historical_fraction,
            "fresh_temporal_response_fraction_matches_historical": fraction_match,
            "public_predict_reconstruction": public_reconstruction,
            "stage_a_replay": stage_replay,
            "historical_cache_reconstruction": cache_validation,
        },
        "temporal_contract": live_contract,
        "forensic_ranking": evidence,
        "evidence_boundary": (
            "contributors identify replay cancellation only; they do not prove "
            "which alternative temporal dispatch is safe or better in Unity"
        ),
    }


def _load_immutable_stability_context(root: str | Path) -> dict[str, Any]:
    destination = Path(root).expanduser().resolve(strict=True)
    manifest_path = destination / "manifest.json"
    payload_path = destination / "return_segments.json"
    manifest = _load_json_mapping(manifest_path, label="Return stability manifest")
    payload = _load_json_mapping(payload_path, label="Return stability result")
    if manifest.get("schema") != RETURN_GOAL_RESPONSE_STABILITY_MANIFEST_SCHEMA:
        raise ReturnTemporalDispatchForensicsError(
            "Return stability manifest schema mismatch"
        )
    if payload.get("schema") != RETURN_GOAL_RESPONSE_STABILITY_RESULTS_SCHEMA:
        raise ReturnTemporalDispatchForensicsError(
            "Return stability result schema mismatch"
        )
    for item, label in ((manifest, "manifest"), (payload, "result")):
        if item.get("status") != "completed":
            raise ReturnTemporalDispatchForensicsError(
                f"Return stability {label} is not completed"
            )
        if item.get("evidence_kind") != EVIDENCE_KIND:
            raise ReturnTemporalDispatchForensicsError(
                f"Return stability {label} evidence kind differs"
            )
        if (
            item.get("diagnostic_only") is not True
            or item.get("promotion_eligible") is not False
        ):
            raise ReturnTemporalDispatchForensicsError(
                f"Return stability {label} evidence boundary differs"
            )
    lineage = mapping(manifest.get("source_lineage"), "Return stability source lineage")
    stage_manifest = verify_source_record(
        mapping(
            lineage.get("stage_a_v2_manifest"), "Return stability Stage-A manifest"
        ),
        label="Return stability Stage-A manifest",
    )
    stage_root = stage_manifest.parent
    for name in ("stage_a_v2_baseline", "stage_a_v2_return"):
        record_path = verify_source_record(
            mapping(lineage.get(name), f"Return stability {name}"),
            label=f"Return stability {name}",
        )
        if record_path.parent != stage_root:
            raise ReturnTemporalDispatchForensicsError(
                "Return stability Stage-A lineage points to multiple roots"
            )
    records = _mapping_sequence(
        payload.get("segments", ()), label="Return stability segments"
    )
    by_baseline: dict[str, dict[str, Any]] = {}
    for record in records:
        baseline = mapping(
            record.get("baseline_segment"), "Return stability baseline segment"
        )
        segment_id = str(baseline.get("segment_id", ""))
        if segment_id in RETURN_INVALID_SEGMENT_IDS:
            by_baseline[segment_id] = record
    if set(by_baseline) != set(RETURN_INVALID_SEGMENT_IDS):
        raise ReturnTemporalDispatchForensicsError(
            "Return stability artifact does not contain exactly both target failures"
        )
    return {
        "root": destination,
        "manifest": manifest,
        "payload": payload,
        "stage_a_v2_root": stage_root,
        "segments_by_baseline": by_baseline,
    }


def _validate_stability_stage_lineage(
    *,
    stability: Mapping[str, Any],
    stage_context: Mapping[str, Any],
) -> None:
    lineage = mapping(
        stability["manifest"].get("source_lineage"), "Return stability lineage"
    )
    for name, path in stage_context["stage_paths"].items():
        expected_name = f"stage_a_v2_{name}"
        if source_record(path) != mapping(lineage.get(expected_name), expected_name):
            raise ReturnTemporalDispatchForensicsError(
                f"Return stability {expected_name} does not match frozen Stage-A v2"
            )


def _validate_historical_stability_record(
    *,
    stability_record: Mapping[str, Any],
    segment_id: str,
    expected_frame_count: int,
) -> dict[str, Any]:
    if stability_record.get("status") != "completed":
        raise ReturnTemporalDispatchForensicsError(
            "historical Return segment was not completed"
        )
    baseline = mapping(stability_record.get("baseline_segment"), "historical baseline")
    if str(baseline.get("segment_id", "")) != segment_id:
        raise ReturnTemporalDispatchForensicsError(
            "historical Return segment identity changed"
        )
    if int(baseline.get("frame_count", -1)) != expected_frame_count:
        raise ReturnTemporalDispatchForensicsError(
            "historical Return frame count changed"
        )
    causal = mapping(stability_record.get("causal_status"), "historical causal status")
    if causal.get("status") != "temporal_aggregation_dilution":
        raise ReturnTemporalDispatchForensicsError(
            "historical Return cause is not temporal dilution"
        )
    for name in (
        "token_normalisation",
        "pre_action_observation_identity",
        "temporal_reconstruction",
        "replay_matches_immutable_stage_a",
        "predict_action_chunk_cache_check",
    ):
        item = mapping(stability_record.get(name), f"historical {name}")
        if (
            item.get("status") not in (None, "passed")
            and item.get("passed") is not True
        ):
            raise ReturnTemporalDispatchForensicsError(
                f"historical {name} was not valid"
            )
    temporal = mapping(
        stability_record.get("temporal_aggregation"), "historical aggregation"
    )
    if not bool(temporal.get("temporal_dilution_explains_gate_failure")):
        raise ReturnTemporalDispatchForensicsError(
            "historical temporal dilution is not established"
        )
    cache = _mapping_sequence(
        temporal.get("cache_contributors", ()), label="historical cache"
    )
    if len(cache) != expected_frame_count:
        raise ReturnTemporalDispatchForensicsError(
            "historical cache frame count differs"
        )
    return dict(stability_record)


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
        raise ReturnTemporalDispatchForensicsError(
            "source rollout has no stable Return segments"
        )
    return result


def _segment_or_error(
    segments: Mapping[str, RecordedActReplaySegment],
    segment_id: str,
) -> RecordedActReplaySegment:
    try:
        return segments[segment_id]
    except KeyError as exc:
        raise ReturnTemporalDispatchForensicsError(
            f"immutable Return segment is absent: {segment_id}"
        ) from exc


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


def _collect_one_policy_stream(
    *,
    label: str,
    policy_factory_builder: PolicyFactoryBuilder,
    policy_describer: PolicyDescriber,
    observations: Sequence[Mapping[str, Any]],
    token_key: str | None,
    token: np.ndarray,
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    if not token_key:
        raise ReturnTemporalDispatchForensicsError(
            "Return segment lacks model token key"
        )
    policy = policy_factory_builder(label)
    try:
        description = dict(policy_describer(policy))
        stream = collect_public_policy_stream(
            policy=policy,
            observations=observations,
            token_key=token_key,
            token=token,
        )
        return description, stream
    finally:
        del policy
        gc.collect()
        _release_cuda_cache()


def _validate_live_temporal_contract(
    *,
    baseline_description: Mapping[str, Any],
    alternate_description: Mapping[str, Any],
    expected_contract: Mapping[str, Any],
) -> dict[str, Any]:
    baseline = normalise_temporal_contract(
        mapping(
            baseline_description.get("temporal_aggregation"),
            "baseline temporal contract",
        )
    )
    alternate = normalise_temporal_contract(
        mapping(
            alternate_description.get("temporal_aggregation"),
            "alternate temporal contract",
        )
    )
    if baseline != alternate or baseline != dict(expected_contract):
        raise ReturnTemporalDispatchForensicsError(
            "loaded public policy temporal contract differs from frozen evidence"
        )
    if not baseline["enabled"]:
        raise ReturnTemporalDispatchForensicsError(
            "frozen Return contract requires temporal aggregation"
        )
    return baseline


def _stage_tolerances(
    stage_record: Mapping[str, Any],
    *,
    action_dim: int,
) -> dict[str, np.ndarray]:
    result = mapping(stage_record.get("result"), "Stage-A result")
    validity = mapping(result.get("artifact_validity"), "Stage-A artifact validity")
    tolerance = mapping(validity.get("replica_tolerance"), "Stage-A replica tolerance")
    dispatched = finite_vector(
        tolerance.get("dispatched_tolerance_axis"), label="Stage-A dispatched tolerance"
    )
    replica = finite_vector(
        tolerance.get("replica_noise_cap_axis"), label="Stage-A replica noise cap"
    )
    if (
        dispatched.shape != (action_dim,)
        or replica.shape != (action_dim,)
        or np.any(dispatched <= 0.0)
        or np.any(replica <= 0.0)
    ):
        raise ReturnTemporalDispatchForensicsError(
            "Stage-A replay tolerances are invalid"
        )
    return {"dispatched_tolerance_axis": dispatched, "replica_noise_cap_axis": replica}


def _validate_public_reconstruction(
    *,
    baseline_stream: Mapping[str, np.ndarray],
    alternate_stream: Mapping[str, np.ndarray],
    contract: Mapping[str, Any],
    tolerance: np.ndarray,
) -> dict[str, Any]:
    checks: dict[str, list[float]] = {}
    passed = True
    for name, stream in (
        ("baseline", baseline_stream),
        ("alternate", alternate_stream),
    ):
        reconstructed = reconstruct_temporal_aggregated_actions(
            chunks=stream["chunks"], temporal_contract=contract
        )
        delta = np.max(np.abs(stream["actions"] - reconstructed), axis=0)
        checks[f"{name}_predict_vs_reconstructed_max_abs_delta_axis"] = _float_list(
            delta
        )
        passed = passed and bool(np.all(delta <= tolerance))
    return {
        "passed": passed,
        "verification": "actual public predict stream compared with reconstruction from public chunks",
        **checks,
        "tolerance_axis": _float_list(tolerance),
    }


def _validate_stage_replay(
    *,
    stage_record: Mapping[str, Any],
    alternate_actions: np.ndarray,
    baseline_actions: np.ndarray,
    action_threshold: np.ndarray,
    replica_noise_cap: np.ndarray,
) -> dict[str, Any]:
    condition = invalid_condition_from_stage_record(stage_record)
    stage_delta = finite_array(
        condition.get("temporal_aggregated_action_deltas"),
        label="Stage-A temporal action deltas",
        ndim=2,
    )
    replay_delta = alternate_actions - baseline_actions
    if stage_delta.shape != replay_delta.shape:
        raise ReturnTemporalDispatchForensicsError("Stage-A action delta shape changed")
    max_delta = np.max(np.abs(replay_delta - stage_delta), axis=0)
    stage_mask = np.any(np.abs(stage_delta) > action_threshold[None, :], axis=1)
    replay_mask = np.any(np.abs(replay_delta) > action_threshold[None, :], axis=1)
    return {
        "passed": bool(
            np.all(max_delta <= replica_noise_cap)
            and np.array_equal(stage_mask, replay_mask)
        ),
        "max_abs_delta_axis": _float_list(max_delta),
        "pre_registered_replica_noise_cap_axis": _float_list(replica_noise_cap),
        "response_mask_matches_immutable_stage_a": bool(
            np.array_equal(stage_mask, replay_mask)
        ),
    }


def _validate_stage_performance(
    stage_performance: Any, resolved: Mapping[str, Any]
) -> None:
    stage = mapping(stage_performance, "Stage-A torch performance")
    required = {"allow_tf32", "cudnn_benchmark", "matmul_precision"}
    if not required <= set(stage):
        raise ReturnTemporalDispatchForensicsError(
            "Stage-A torch performance is incomplete"
        )
    if {key: stage[key] for key in required} != {
        key: resolved[key] for key in required
    }:
        raise ReturnTemporalDispatchForensicsError(
            "current replay performance differs from frozen Stage-A performance"
        )


def _mapping_sequence(value: Any, *, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ReturnTemporalDispatchForensicsError(f"{label} must be a sequence")
    result: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ReturnTemporalDispatchForensicsError(f"{label} must contain mappings")
        result.append(dict(item))
    return result


def _load_json_mapping(path: Path, *, label: str) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            result = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ReturnTemporalDispatchForensicsError(
            f"cannot read {label}: {path}"
        ) from exc
    return mapping(result, label)


def _float_list(values: Any) -> list[float]:
    return [float(value) for value in np.asarray(values, dtype=np.float64).reshape(-1)]


def _release_cuda_cache() -> None:
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


__all__ = ["run_return_temporal_dispatch_forensics_replay"]
