"""File orchestration for the Strict-18 Stage-A ACT sensitivity audit.

The core evaluator deliberately accepts already aligned frames.  This runner is
the narrow bridge from an immutable recorded-results root to that evaluator: it
uses the data-layer contracts, loads one policy instance at a time, and writes
the fixed six-file evidence root.
"""

from __future__ import annotations

import hashlib
import json
import pickle
import subprocess
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import yaml

from testbed.data.recorded_act_replay import (
    NumericSupportAssessment,
    RecordedActReplayFrame,
    RecordedActReplaySegment,
    StrictTrainNumericSupport,
    assess_strict_train_numeric_support,
    build_strict_train_numeric_support,
    join_recorded_act_replay_frames,
    read_recorded_act_observation,
    select_deterministic_alternate_segment,
    split_stable_recorded_act_segments,
)
from testbed.eval.act_goal_condition_sensitivity import (
    ACT_GOAL_CONDITION_SENSITIVITY_MANIFEST_SCHEMA,
    EVIDENCE_KIND,
    evaluate_goal_condition_sensitivity_segment,
    write_goal_condition_sensitivity_artifact,
)
from testbed.eval.act_goal_condition_sensitivity_isolation import (
    run_carry_dump_isolation,
)
from testbed.policies.act.inference import (
    build_act_adapter_config,
    describe_act_inference,
    load_act_policy,
)
from testbed.runtime._eval import _configure_eval_torch_performance

BASELINE_SCHEMA = "act_goal_condition_sensitivity_baseline_v1"
PRIMITIVE_SCHEMA = "act_goal_condition_sensitivity_primitive_v1"
PolicyFactoryBuilder = Callable[[str, Mapping[str, Any]], Callable[[Mapping[str, Any], str], Any]]
SupportAssessor = Callable[[Mapping[str, Any], Any], Mapping[str, Any]]


def run_act_goal_condition_sensitivity_audit(
    *,
    source_results_root: str | Path,
    dig_training_config_path: str | Path,
    return_training_config_path: str | Path,
    output_root: str | Path,
    device: str = "cuda",
    policy_factory_builder: PolicyFactoryBuilder | None = None,
    action_std_by_primitive: Mapping[str, np.ndarray] | None = None,
    support_assessors_by_primitive: Mapping[str, SupportAssessor] | None = None,
    support_lineage_by_primitive: Mapping[str, Mapping[str, Any]] | None = None,
    additional_source_lineage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run all stable Dig/Return pairs and write the Stage-A evidence root.

    This is still teacher-forced, diagnostic-only evidence.  It never calls a
    simulator or real machine.  The optional factory builder exists only for
    focused tests; production callers use frozen checkpoint loading below.
    """

    source_root = Path(source_results_root).expanduser().resolve(strict=True)
    destination = Path(output_root).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"Stage-A output already exists: {destination}")
    clean_code = _clean_code_record()
    if not bool(clean_code["worktree_clean"]):
        raise RuntimeError("Stage-A audit requires a clean Git worktree")
    source_paths = _source_paths(source_root)
    eval_config = _load_yaml_mapping(source_paths["eval_config"])
    dig_train = _load_yaml_mapping(Path(dig_training_config_path))
    return_train = _load_yaml_mapping(Path(return_training_config_path))
    camera_names = _camera_names(eval_config)
    policy_cfg = _mapping(eval_config.get("policy"), "eval policy")
    task_cfg = _mapping(eval_config.get("task"), "eval task")
    resolved_performance = _configure_eval_torch_performance(
        dict(_mapping(eval_config.get("eval"), "eval settings")),
        device=str(device),
    )
    frames = join_recorded_act_replay_frames(
        rollout_hdf5_path=source_paths["rollout_hdf5"],
        rollout_jsonl_path=source_paths["rollout_jsonl"],
        skills=("dig", "return", "carry", "dump"),
    )
    all_segments = split_stable_recorded_act_segments(frames)
    primitive_segments = {
        primitive: [
            segment for segment in all_segments if segment.skill_name == primitive
        ]
        for primitive in ("dig", "return")
    }
    if not primitive_segments["dig"] or not primitive_segments["return"]:
        raise ValueError("recorded results lack stable Dig or Return segments")

    supports = {
        "dig": _strict_train_support(dig_train, skill_name="dig"),
        "return": _strict_train_support(return_train, skill_name="return"),
    }
    applied_supports = _resolve_applied_supports(
        supports=supports,
        support_assessors_by_primitive=support_assessors_by_primitive,
        support_lineage_by_primitive=support_lineage_by_primitive,
    )
    source_lineage = {
        "source_results_root": str(source_root),
        "eval_resolved_config": _source_record(source_paths["eval_config"]),
        "rollout_jsonl": _source_record(source_paths["rollout_jsonl"]),
        "rollout_hdf5": _source_record(source_paths["rollout_hdf5"]),
        "dig_training_config": _source_record(Path(dig_training_config_path)),
        "return_training_config": _source_record(Path(return_training_config_path)),
        "eval_run_metadata": _source_record(source_paths["eval_run_metadata"]),
        "artifact_repo_commit": _artifact_repo_commit(source_paths["eval_run_metadata"]),
    }
    extra_lineage = _normalise_additional_source_lineage(additional_source_lineage)
    if extra_lineage is not None:
        # The caller supplies already SHA-verified immutable prerequisites.
        # Store them before artifact creation; never amend a written manifest.
        source_lineage["additional_audit_lineage"] = extra_lineage
    frozen_action_std = (
        {
            primitive: np.asarray(action_std_by_primitive[primitive], dtype=np.float32)
            for primitive in ("dig", "return", "carry", "dump")
        }
        if action_std_by_primitive is not None
        else _frozen_action_std_by_primitive(policy_cfg)
    )
    source_lineage["checkpoints_and_stats"] = _checkpoint_stats_lineage(
        policy_cfg,
        required=policy_factory_builder is None,
    )
    source_lineage["applied_support_contract_by_primitive"] = {
        primitive: dict(applied_supports[primitive]["lineage"])
        for primitive in ("dig", "return")
    }
    inference_descriptions: dict[str, dict[str, Any]] = {}
    factory_builder = policy_factory_builder or _production_policy_factory_builder(
        eval_config=eval_config,
        policy_cfg=policy_cfg,
        task_cfg=task_cfg,
        device=str(device),
        inference_descriptions=inference_descriptions,
        frozen_action_std=frozen_action_std,
    )

    primitive_payloads: dict[str, dict[str, Any]] = {}
    with h5py.File(source_paths["rollout_hdf5"], "r") as hdf5_file:
        for primitive in ("dig", "return"):
            reader = _observation_reader(hdf5_file, camera_names=camera_names)
            records = _evaluate_primitive_segments(
                primitive=primitive,
                segments=primitive_segments[primitive],
                support_assessor=applied_supports[primitive]["assessor"],
                policy_factory=factory_builder(primitive, policy_cfg),
                observation_reader=reader,
                action_std=frozen_action_std[primitive],
            )
            primitive_payloads[primitive] = _primitive_payload(
                primitive=primitive,
                records=records,
                support=supports[primitive],
                applied_support_contract=applied_supports[primitive]["lineage"],
            )
        isolation = run_carry_dump_isolation(
            policy_cfg=policy_cfg,
            segments=all_segments,
            dig_segments=primitive_segments["dig"],
            policy_factory_builder=factory_builder,
            observation_reader=_observation_reader(hdf5_file, camera_names=camera_names),
            action_std_by_primitive=frozen_action_std,
        )
    baseline = _baseline_payload(primitive_payloads)
    overall_status = _overall_status(
        primitive_payloads=primitive_payloads,
        isolation=isolation,
    )
    manifest = _manifest(
        status=overall_status,
        source_lineage=source_lineage,
        performance=resolved_performance.as_config_dict(),
        primitive_payloads=primitive_payloads,
        baseline=baseline,
        isolation=isolation,
        inference_descriptions=inference_descriptions,
        clean_code=clean_code,
    )
    report = _report_markdown(
        status=overall_status,
        primitive_payloads=primitive_payloads,
        isolation=isolation,
    )
    written_manifest = write_goal_condition_sensitivity_artifact(
        output_root=destination,
        manifest=manifest,
        baseline=baseline,
        dig=primitive_payloads["dig"],
        return_=primitive_payloads["return"],
        carry_dump_isolation=isolation,
        report_markdown=report,
    )
    return {
        "manifest": written_manifest,
        "output_root": str(destination),
        "status": overall_status,
    }


def _source_paths(source_root: Path) -> dict[str, Path]:
    paths = {
        "eval_config": source_root / "eval_resolved_config.yaml",
        "eval_run_metadata": source_root / "eval_run_metadata.json",
        "rollout_jsonl": source_root / "rollouts" / "rollout_000.jsonl",
        "rollout_hdf5": source_root / "hdf5_rollouts" / "episode_0.hdf5",
    }
    for label, path in paths.items():
        if not path.is_file():
            raise FileNotFoundError(f"Stage-A source is missing {label}: {path}")
    return paths


def _normalise_additional_source_lineage(
    value: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Accept only JSON-safe immutable prerequisite lineage supplied by a binder."""

    if value is None:
        return None
    if not isinstance(value, Mapping) or not value:
        raise ValueError("additional_source_lineage must be a non-empty mapping")
    try:
        # Round-trip also detaches this manifest input from caller-owned state.
        return json.loads(json.dumps(dict(value), allow_nan=False, sort_keys=True))
    except (TypeError, ValueError) as exc:
        raise ValueError("additional_source_lineage must be JSON-safe") from exc


def _evaluate_primitive_segments(
    *,
    primitive: str,
    segments: Sequence[RecordedActReplaySegment],
    support_assessor: SupportAssessor,
    policy_factory: Callable[[Mapping[str, Any], str], Any],
    observation_reader: Callable[[RecordedActReplayFrame], Mapping[str, Any]],
    action_std: np.ndarray,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for segment in segments:
        alternate = select_deterministic_alternate_segment(
            segments=segments,
            baseline=segment,
        )
        evaluation_segment = {
            "primitive": primitive,
            "condition_input_key": segment.model_token_key,
            "segment_id": segment.segment_id,
            "frames": segment.frames,
        }
        conditions = [
            _condition_from_segment(segment, is_baseline=True),
            _condition_from_segment(alternate, is_baseline=False),
        ]
        result = evaluate_goal_condition_sensitivity_segment(
            segment=evaluation_segment,
            conditions=conditions,
            policy_factory=policy_factory,
            action_std=action_std,
            observation_reader=observation_reader,
            support_assessor=support_assessor,
        )
        records.append(
            {
                "segment": _segment_record(segment),
                "alternate_segment": _segment_record(alternate),
                "result": result,
            }
        )
    return records


def _condition_from_segment(
    segment: RecordedActReplaySegment,
    *,
    is_baseline: bool,
) -> dict[str, Any]:
    return {
        "condition_id": (
            "recorded_token"
            if is_baseline
            else f"alternate_real_token_{segment.token_sha256[:12]}"
        ),
        "token": np.asarray(segment.token, dtype=np.float32).copy(),
        "support_status": "supported",
        "is_baseline": is_baseline,
        "provenance": {
            "kind": "recorded_real_token",
            "token_sha256": segment.token_sha256,
            "token_source": segment.token_source,
            "source_segment_id": segment.segment_id,
        },
    }


def _support_assessor(
    support: StrictTrainNumericSupport,
) -> Callable[[Mapping[str, Any], Any], Mapping[str, Any]]:
    def assess(condition: Mapping[str, Any], segment: Any) -> Mapping[str, Any]:
        frames = list(_field(segment, "frames", ()))
        qpos = np.asarray([frame.qpos for frame in frames], dtype=np.float32)
        qvel = np.asarray([frame.qvel for frame in frames], dtype=np.float32)
        token = np.repeat(
            np.asarray(condition["token"], dtype=np.float32).reshape(1, -1),
            len(frames),
            axis=0,
        )
        assessment = assess_strict_train_numeric_support(
            support,
            qpos=qpos,
            qvel=qvel,
            token=token,
        )
        return _support_record(assessment)

    return assess


def build_frozen_candidate_support_assessor(candidate: Any) -> SupportAssessor:
    """Build a no-fit assessor from one already-frozen support candidate.

    The candidate is supplied by the support-contract audit caller.  This
    function never reads rows, computes a quantile, or changes a threshold; it
    only evaluates the recorded qpos/qvel stream plus the condition token that
    the Stage-A replay already passes to ACT.
    """

    from testbed.data.act_support_contract import assess_support_candidate

    candidate_id = str(_field(candidate, "candidate_id", "")).strip()
    feature_order = tuple(str(value) for value in _field(candidate, "feature_order", ()))
    fit_partition = str(_field(candidate, "fit_partition", "")).strip()
    if not candidate_id or not feature_order:
        raise ValueError("frozen support candidate lacks candidate_id or feature_order")
    if fit_partition != "strict_train":
        raise ValueError("injected support candidate must be fitted on strict_train")

    def assess(condition: Mapping[str, Any], segment: Any) -> Mapping[str, Any]:
        feature = _support_feature_matrix(condition=condition, segment=segment)
        if feature.shape[1] != len(feature_order):
            raise ValueError(
                "injected support candidate feature width does not match replay input"
            )
        assessment = assess_support_candidate(candidate, feature)
        record = dict(assessment.as_dict())
        record["status"] = (
            "supported" if bool(np.all(assessment.frame_in_support)) else "out_of_support"
        )
        return record

    return assess


def _resolve_applied_supports(
    *,
    supports: Mapping[str, StrictTrainNumericSupport],
    support_assessors_by_primitive: Mapping[str, SupportAssessor] | None,
    support_lineage_by_primitive: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    """Bind default v1 or injected frozen support without touching ACT state."""

    expected = {"dig", "return"}
    overrides = _normalise_support_override_mapping(
        support_assessors_by_primitive,
        label="support_assessors_by_primitive",
    )
    lineages = _normalise_support_override_mapping(
        support_lineage_by_primitive,
        label="support_lineage_by_primitive",
        require_callable=False,
    )
    if set(overrides) != set(lineages):
        raise ValueError(
            "support assessor overrides and support lineage must cover the same primitives"
        )
    result: dict[str, dict[str, Any]] = {}
    for primitive in ("dig", "return"):
        support = supports.get(primitive)
        if support is None:
            raise ValueError(f"strict v1 support is missing {primitive}")
        if primitive in overrides:
            assessor = overrides[primitive]
            lineage = _injected_support_lineage(lineages[primitive], primitive=primitive)
        else:
            assessor = _support_assessor(support)
            lineage = _default_support_lineage(support)
        result[primitive] = {
            "assessor": _lineaged_support_assessor(assessor, lineage),
            "lineage": lineage,
        }
    if set(result) != expected:  # Defensive invariant if supported primitives change.
        raise ValueError("applied support binding does not cover Dig and Return")
    return result


def _normalise_support_override_mapping(
    value: Mapping[str, Any] | None,
    *,
    label: str,
    require_callable: bool = True,
) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    expected = {"dig", "return"}
    result = {str(primitive): item for primitive, item in value.items()}
    extra = sorted(set(result) - expected)
    if extra:
        raise ValueError(f"{label} has unsupported primitives {extra!r}")
    if any(item is None for item in result.values()):
        raise ValueError(f"{label} contains a missing override")
    if require_callable and any(not callable(item) for item in result.values()):
        raise ValueError(f"{label} values must be callable")
    if not require_callable and any(not isinstance(item, Mapping) for item in result.values()):
        raise ValueError(f"{label} values must be mappings")
    return result


def _default_support_lineage(
    support: StrictTrainNumericSupport,
) -> dict[str, Any]:
    return {
        "binding": "default_strict_train_numeric_support",
        "support_contract_version": "support_contract_v1",
        "candidate_id": "axis_p01_p99_v1",
        "fit_partition": "strict_train",
        "feature_order": list(support.feature_order),
        "train_source_episode_ids": list(support.train_source_episode_ids),
        "validation_source_episode_ids": list(support.validation_source_episode_ids),
        "kept_step_count": support.kept_step_count,
    }


def _injected_support_lineage(
    raw: Mapping[str, Any],
    *,
    primitive: str,
) -> dict[str, Any]:
    lineage = dict(raw)
    candidate_id = str(lineage.get("candidate_id", "")).strip()
    version = str(lineage.get("support_contract_version", "")).strip()
    if not candidate_id or not version:
        raise ValueError(
            f"injected {primitive} support lineage requires candidate_id and "
            "support_contract_version"
        )
    if "binding" in lineage and lineage["binding"] != "injected_frozen_support_assessor":
        raise ValueError("injected support lineage binding is not recognized")
    return {
        "binding": "injected_frozen_support_assessor",
        **lineage,
    }


def _lineaged_support_assessor(
    assessor: SupportAssessor,
    lineage: Mapping[str, Any],
) -> SupportAssessor:
    frozen_lineage = dict(lineage)

    def assess(condition: Mapping[str, Any], segment: Any) -> Mapping[str, Any]:
        result = assessor(condition, segment)
        if not isinstance(result, Mapping):
            raise ValueError("support assessor must return a mapping")
        record = dict(result)
        existing = record.get("support_contract")
        if existing is not None and dict(existing) != frozen_lineage:
            raise ValueError("support assessor returned conflicting support contract lineage")
        record["support_contract"] = dict(frozen_lineage)
        return record

    return assess


def _support_feature_matrix(
    *,
    condition: Mapping[str, Any],
    segment: Any,
) -> np.ndarray:
    frames = list(_field(segment, "frames", ()))
    if not frames:
        raise ValueError("support assessment requires recorded frames")
    qpos = np.asarray([frame.qpos for frame in frames], dtype=np.float64)
    qvel = np.asarray([frame.qvel for frame in frames], dtype=np.float64)
    token = np.repeat(
        np.asarray(condition["token"], dtype=np.float64).reshape(1, -1),
        len(frames),
        axis=0,
    )
    if qpos.shape != (len(frames), 4) or qvel.shape != (len(frames), 4):
        raise ValueError("support replay qpos/qvel must each have shape (frame_count, 4)")
    feature = np.concatenate((qpos, qvel, token), axis=1)
    if not np.isfinite(feature).all():
        raise ValueError("support replay feature contains non-finite values")
    return feature


def _support_record(assessment: NumericSupportAssessment) -> dict[str, Any]:
    violations = [
        [
            {
                "field": item.field,
                "value": item.value,
                "p01": item.p01,
                "p99": item.p99,
                "kind": item.kind,
            }
            for item in row
        ]
        for row in assessment.violations
    ]
    passed = bool(np.all(assessment.frame_in_support))
    return {
        "status": "supported" if passed else "out_of_support",
        "frame_in_support": [bool(value) for value in assessment.frame_in_support],
        "in_support_fraction": assessment.in_support_fraction,
        "violations": violations,
    }


def _production_policy_factory_builder(
    *,
    eval_config: Mapping[str, Any],
    policy_cfg: Mapping[str, Any],
    task_cfg: Mapping[str, Any],
    device: str,
    inference_descriptions: dict[str, dict[str, Any]],
    frozen_action_std: Mapping[str, np.ndarray],
) -> PolicyFactoryBuilder:
    camera_names = [str(value) for value in task_cfg["camera_names"]]
    equipment_model = str(task_cfg["equipment_model"])
    episode_len = int(task_cfg["episode_len"])
    act_params = dict(_mapping(policy_cfg.get("act_params"), "policy.act_params"))

    def build_for_primitive(
        primitive: str,
        _unused_policy_cfg: Mapping[str, Any],
    ) -> Callable[[Mapping[str, Any], str], Any]:
        low_dim_keys = list(policy_cfg[f"{primitive}_low_dim_keys"])
        checkpoint = Path(str(policy_cfg[f"{primitive}_ckpt_path"])).expanduser().resolve(strict=True)
        stats = checkpoint.parent / "dataset_stats.pkl"
        if not stats.is_file():
            raise FileNotFoundError(stats)
        adapter_config = build_act_adapter_config(
            config=eval_config,
            camera_names=camera_names,
            equipment_model=equipment_model,
            max_episode_len=episode_len,
            low_dim_keys=low_dim_keys,
            act_params=act_params,
            outcome_head_config=dict(policy_cfg.get(f"{primitive}_outcome_head", {}) or {}),
            image_mask_config=dict(policy_cfg.get("image_mask", {}) or {}),
        )

        def factory(_condition: Mapping[str, Any], replica_id: str) -> Any:
            policy = load_act_policy(
                ckpt_path=checkpoint,
                policy_config=adapter_config,
                norm_stats_path=stats,
                temporal_agg=True,
                device=device,
            )
            inference_descriptions[replica_id] = {
                **describe_act_inference(policy),
                "checkpoint": _source_record(checkpoint),
                "stats": _source_record(stats),
            }
            described_std = np.asarray(
                inference_descriptions[replica_id]["action_std"],
                dtype=np.float32,
            )
            if not np.array_equal(described_std, frozen_action_std[primitive]):
                raise ValueError(
                    f"{primitive} loaded policy action_std disagrees with dataset_stats.pkl"
                )
            return policy

        return factory

    return build_for_primitive


def _frozen_action_std_by_primitive(
    policy_cfg: Mapping[str, Any],
) -> dict[str, np.ndarray]:
    output: dict[str, np.ndarray] = {}
    for primitive in ("dig", "return", "carry", "dump"):
        checkpoint = Path(str(policy_cfg[f"{primitive}_ckpt_path"])).expanduser().resolve(strict=True)
        stats = checkpoint.parent / "dataset_stats.pkl"
        if not stats.is_file():
            raise FileNotFoundError(stats)
        with stats.open("rb") as handle:
            payload = pickle.load(handle)
        if not isinstance(payload, Mapping):
            raise ValueError(f"{primitive} dataset_stats.pkl must be a mapping")
        action_std = np.asarray(payload.get("action_std"), dtype=np.float32).reshape(-1)
        if action_std.shape != (4,) or not np.isfinite(action_std).all() or np.any(action_std < 0.0):
            raise ValueError(f"{primitive} dataset_stats.pkl has invalid action_std")
        output[primitive] = action_std
    return output


def _observation_reader(
    hdf5_file: h5py.File,
    *,
    camera_names: Sequence[str],
) -> Callable[[RecordedActReplayFrame], Mapping[str, Any]]:
    def read(frame: RecordedActReplayFrame) -> Mapping[str, Any]:
        return read_recorded_act_observation(
            hdf5_file=hdf5_file,
            frame=frame,
            camera_names=camera_names,
        )

    return read


def _strict_train_support(
    config: Mapping[str, Any],
    *,
    skill_name: str,
) -> StrictTrainNumericSupport:
    task = _mapping(config.get("task"), f"{skill_name} train task")
    train = _mapping(config.get("train"), f"{skill_name} train settings")
    dataset_dir = Path(str(task.get("dataset_dir", ""))).expanduser()
    split_path = Path(str(train.get("split_path", ""))).expanduser()
    if not str(dataset_dir) or not str(split_path):
        raise ValueError(f"{skill_name} train config lacks dataset_dir or split_path")
    return build_strict_train_numeric_support(
        primitive_dataset_dir=dataset_dir,
        split_path=split_path,
        skill_name=skill_name,
    )


def _primitive_payload(
    *,
    primitive: str,
    records: Sequence[Mapping[str, Any]],
    support: StrictTrainNumericSupport,
    applied_support_contract: Mapping[str, Any],
) -> dict[str, Any]:
    outcomes = [str(record["result"].get("status")) for record in records]
    classifications = Counter(
        str(condition["classification"])
        for record in records
        for condition in record["result"].get("conditions", {}).values()
        if "classification" in condition
    )
    aggregate_classification = _aggregate_classification(records)
    return {
        "schema": PRIMITIVE_SCHEMA,
        "primitive": primitive,
        "status": "completed" if all(status == "completed" for status in outcomes) else "artifact_invalid",
        "evidence_kind": EVIDENCE_KIND,
        "diagnostic_only": True,
        "promotion_eligible": False,
        "direction": "not_identifiable_in_teacher_forced_replay",
        "numeric_support": {
            "feature_order": list(support.feature_order),
            "p01": _float_list(support.p01),
            "p99": _float_list(support.p99),
            "train_source_episode_ids": list(support.train_source_episode_ids),
            "validation_source_episode_ids": list(support.validation_source_episode_ids),
            "total_step_count": support.total_step_count,
            "kept_step_count": support.kept_step_count,
            "masked_step_count": support.masked_step_count,
        },
        "applied_support_contract": dict(applied_support_contract),
        "segment_pair_records": list(records),
        "aggregate": {
            "segment_pair_count": len(records),
            "completed_count": outcomes.count("completed"),
            "artifact_invalid_count": outcomes.count("artifact_invalid"),
            "classification_counts": dict(sorted(classifications.items())),
            "classification": aggregate_classification,
        },
    }


def _aggregate_classification(
    records: Sequence[Mapping[str, Any]],
) -> str | None:
    """Apply the frozen aggregate precedence after artifact validity succeeds."""

    if any(record["result"].get("status") != "completed" for record in records):
        return None
    classifications = [
        str(condition["classification"])
        for record in records
        for condition in record["result"].get("conditions", {}).values()
        if "classification" in condition
    ]
    if not classifications:
        return None
    if "out_of_support" in classifications:
        return "out_of_support"
    if all(value == "goal_insensitive" for value in classifications):
        return "goal_insensitive"
    if all(value == "goal_response_plausible" for value in classifications):
        return "goal_response_plausible"
    return "goal_response_invalid"


def _baseline_payload(primitive_payloads: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "schema": BASELINE_SCHEMA,
        "status": (
            "completed"
            if all(payload.get("status") == "completed" for payload in primitive_payloads.values())
            else "artifact_invalid"
        ),
        "evidence_kind": EVIDENCE_KIND,
        "primitives": {
            primitive: [
                {
                    "segment_id": record["segment"]["segment_id"],
                    "artifact_validity": record["result"].get("artifact_validity", {}),
                    "baseline": record["result"].get("baseline"),
                }
                for record in payload["segment_pair_records"]
            ]
            for primitive, payload in primitive_payloads.items()
        },
    }


def _manifest(
    *,
    status: str,
    source_lineage: Mapping[str, Any],
    performance: Mapping[str, Any],
    primitive_payloads: Mapping[str, Mapping[str, Any]],
    baseline: Mapping[str, Any],
    isolation: Mapping[str, Any],
    inference_descriptions: Mapping[str, Mapping[str, Any]],
    clean_code: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": ACT_GOAL_CONDITION_SENSITIVITY_MANIFEST_SCHEMA,
        "status": status,
        "evidence_kind": EVIDENCE_KIND,
        "diagnostic_only": True,
        "promotion_eligible": False,
        "closed_loop_claim": False,
        "direction": "not_identifiable_in_teacher_forced_replay",
        "output_files": [
            "manifest.json",
            "baseline.json",
            "dig.json",
            "return.json",
            "carry_dump_isolation.json",
            "report.md",
        ],
        "source_lineage": dict(source_lineage),
        "applied_support_contract_by_primitive": {
            name: payload.get("applied_support_contract", {})
            for name, payload in primitive_payloads.items()
        },
        "clean_code": dict(clean_code),
        "torch_performance": dict(performance),
        "primitive_status": {
            name: payload.get("status") for name, payload in primitive_payloads.items()
        },
        "primitive_aggregate_classification": {
            name: payload.get("aggregate", {}).get("classification")
            for name, payload in primitive_payloads.items()
        },
        "baseline_status": baseline.get("status"),
        "carry_dump_isolation_status": isolation.get("status"),
        "inference_instances": dict(inference_descriptions),
    }


def _overall_status(
    *,
    primitive_payloads: Mapping[str, Mapping[str, Any]],
    isolation: Mapping[str, Any],
) -> str:
    return (
        "completed"
        if all(payload.get("status") == "completed" for payload in primitive_payloads.values())
        and isolation.get("status") == "completed"
        else "artifact_invalid"
    )


def _report_markdown(
    *,
    status: str,
    primitive_payloads: Mapping[str, Mapping[str, Any]],
    isolation: Mapping[str, Any],
) -> str:
    lines = [
        "# Strict-18 阶段 A：冻结 ACT 目标条件敏感性离线审计",
        "",
        f"状态：`{status}`。证据类型为记录观测 teacher-forced 回放。",
        "本结果不证明 Unity 闭环、真实机器效果或生产可用性。",
        "",
    ]
    for primitive in ("dig", "return"):
        aggregate = primitive_payloads[primitive]["aggregate"]
        lines.append(
            f"- {primitive.capitalize()}：{aggregate['segment_pair_count']} 个稳定 token 段，"
            f"完成 {aggregate['completed_count']} 个，工件无效 {aggregate['artifact_invalid_count']} 个；"
            f"汇总结论 `{aggregate['classification']}`，分类 "
            f"{json.dumps(aggregate['classification_counts'], ensure_ascii=False, sort_keys=True)}。"
        )
    lines.extend(
        (
            f"- Carry/Dump 隔离：`{isolation['status']}`。",
            "- teacher-forced 回放无法识别反事实动作变化的物理方向是否合理。",
            "",
        )
    )
    return "\n".join(lines)


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


def _camera_names(config: Mapping[str, Any]) -> list[str]:
    task = _mapping(config.get("task"), "eval task")
    names = [str(value) for value in task.get("camera_names", ())]
    if not names or len(names) != len(set(names)):
        raise ValueError("eval task camera_names must be a non-empty unique sequence")
    return names


def _source_record(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve(strict=True)
    return {
        "path": str(resolved),
        "sha256": _sha256(resolved),
        "size_bytes": resolved.stat().st_size,
    }


def _artifact_repo_commit(metadata_path: Path) -> str:
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("eval_run_metadata.json must be a mapping")
    snapshots = payload.get("repo_snapshots", {})
    if not isinstance(snapshots, Mapping):
        raise ValueError("eval_run_metadata.json lacks repo_snapshots")
    repo_a = snapshots.get("repo_a", {})
    if not isinstance(repo_a, Mapping):
        raise ValueError("eval_run_metadata.json lacks repo_a snapshot")
    commit = str(repo_a.get("commit", "")).strip()
    if len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit.lower()):
        raise ValueError("eval_run_metadata.json has invalid artifact repo commit")
    return commit


def _checkpoint_stats_lineage(
    policy_cfg: Mapping[str, Any],
    *,
    required: bool,
) -> dict[str, Any]:
    lineage: dict[str, Any] = {}
    for primitive in ("dig", "return", "carry", "dump"):
        raw_checkpoint = policy_cfg.get(f"{primitive}_ckpt_path")
        if raw_checkpoint is None:
            if required:
                raise ValueError(f"policy config lacks {primitive}_ckpt_path")
            lineage[primitive] = {"status": "injected_test_policy_factory"}
            continue
        checkpoint = Path(str(raw_checkpoint)).expanduser()
        stats = checkpoint.parent / "dataset_stats.pkl"
        if not checkpoint.is_file() or not stats.is_file():
            if required:
                missing = checkpoint if not checkpoint.is_file() else stats
                raise FileNotFoundError(missing)
            lineage[primitive] = {"status": "injected_test_policy_factory"}
            continue
        lineage[primitive] = {
            "checkpoint": _source_record(checkpoint),
            "dataset_stats": _source_record(stats),
        }
    return lineage


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _clean_code_record() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    return {
        "git_head": _git_output(root, "rev-parse", "HEAD"),
        "git_branch": _git_output(root, "branch", "--show-current"),
        "worktree_clean": not bool(_git_output(root, "status", "--short")),
    }


def _git_output(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve(strict=True)
    payload = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
    return _mapping(payload, str(resolved))


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return dict(value)


def _field(value: Any, name: str, default: Any) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _float_list(values: np.ndarray) -> list[float]:
    return [float(value) for value in np.asarray(values, dtype=np.float32).reshape(-1)]


__all__ = [
    "build_frozen_candidate_support_assessor",
    "run_act_goal_condition_sensitivity_audit",
]
