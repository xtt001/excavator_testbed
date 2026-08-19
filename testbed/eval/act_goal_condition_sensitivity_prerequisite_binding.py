"""Bind immutable A.2 audits before the Strict-18 Stage-A v3 replay.

This module deliberately owns evidence binding only.  It never refits a
support rule, adjusts the 80 percent response gate, changes the runtime, or
interprets a Stage-A classification.  It verifies that the independent A.2
artifacts describe the same recorded source and frozen configurations, then
delegates the actual replay to the existing primitive-scoped Stage-A runner.

The runner receives the verified records before it creates the no-overwrite
v3 root, so the resulting manifest has the complete A.2 lineage at creation
time rather than being mutated after it becomes immutable evidence.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from testbed.eval.act_goal_condition_sensitivity import (
    ACT_GOAL_CONDITION_SENSITIVITY_MANIFEST_SCHEMA,
    EVIDENCE_KIND,
)
from testbed.eval.act_goal_condition_sensitivity_support_contract import (
    run_primitive_scoped_stage_a_support_audit,
)

SUPPORT_AUDIT_MANIFEST_SCHEMA = "act_support_contract_audit_manifest_v1"
SUPPORT_AUDIT_CANDIDATES_SCHEMA = "act_support_contract_candidates_v1"
SUPPORT_AUDIT_VALIDATION_SCHEMA = "act_support_contract_validation_v1"
SUPPORT_CONTRACT_VERSION = "support_contract_v2"
RETURN_STABILITY_MANIFEST_SCHEMA = "return_goal_response_stability_audit_manifest_v1"
RETURN_STABILITY_RESULTS_SCHEMA = "return_goal_response_stability_audit_results_v1"
DIG_JOINT_MANIFEST_SCHEMA = "dig_joint_support_validation_manifest_v1"
DIG_JOINT_CANDIDATES_SCHEMA = "dig_joint_support_validation_candidates_v1"
DIG_JOINT_VALIDATION_SCHEMA = "dig_joint_support_validation_validation_v1"
DIG_JOINT_CONTRACT_VERSION = "support_contract_v2_dig_joint_v1"
V3_PREREQUISITE_BINDING_SCHEMA = (
    "act_goal_condition_sensitivity_v3_prerequisite_binding_v1"
)
REQUIRED_RESPONSIVE_FRAME_FRACTION = 0.80
RETURN_INVALID_SEGMENT_IDS = (
    "return:898-1043:bb329f176aba",
    "return:3959-4161:4afcef2eee82",
)
_EXPECTED_RETURN_ALTERNATE_SEGMENT_IDS = {
    "return:898-1043:bb329f176aba": "return:3959-4161:4afcef2eee82",
    "return:3959-4161:4afcef2eee82": "return:2323-2534:87aa0fb8c981",
}
_ALLOWED_RETURN_CAUSAL_STATUSES = frozenset(
    {"not_explained_by_frozen_inputs", "temporal_aggregation_dilution"}
)

PrimitiveScopedStageARunner = Callable[..., Mapping[str, Any]]


class StageAV3PrerequisiteBindingError(ValueError):
    """Raised when a v3 replay would not have an immutable A.2 evidence basis."""


def run_stage_a_v3_after_prerequisite_audits(
    *,
    source_results_root: str | Path,
    stage_a_v1_output_root: str | Path,
    support_audit_output_root: str | Path,
    stage_a_v2_output_root: str | Path,
    return_stability_output_root: str | Path,
    dig_joint_validation_output_root: str | Path,
    dig_training_config_path: str | Path,
    return_training_config_path: str | Path,
    output_root: str | Path,
    device: str = "cuda",
    primitive_scoped_runner: PrimitiveScopedStageARunner | None = None,
) -> dict[str, Any]:
    """Run a v3 replay only after verifying its immutable A.2 prerequisites.

    Return continues to use the independently selected frozen v2 candidate.
    Dig is intentionally left on v1 only when the independent Dig validation
    explicitly selected no candidate.  A selected Dig candidate fails closed
    here because this binder does not deserialize or inject it.
    """

    destination = Path(output_root).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"Stage-A v3 output already exists: {destination}")

    source_root = Path(source_results_root).expanduser().resolve(strict=True)
    stage_v1_root = Path(stage_a_v1_output_root).expanduser().resolve(strict=True)
    support_root = Path(support_audit_output_root).expanduser().resolve(strict=True)
    stage_v2_root = Path(stage_a_v2_output_root).expanduser().resolve(strict=True)
    return_stability_root = Path(return_stability_output_root).expanduser().resolve(
        strict=True
    )
    dig_validation_root = Path(dig_joint_validation_output_root).expanduser().resolve(
        strict=True
    )
    dig_config = Path(dig_training_config_path).expanduser().resolve(strict=True)
    return_config = Path(return_training_config_path).expanduser().resolve(strict=True)
    _require_distinct_output_root(
        destination=destination,
        immutable_roots={
            "source results": source_root,
            "Stage-A v1": stage_v1_root,
            "support-contract audit": support_root,
            "Stage-A v2 Return": stage_v2_root,
            "Return stability audit": return_stability_root,
            "Dig joint validation": dig_validation_root,
        },
    )

    source_paths = _source_paths(source_root)
    stage_v1_paths = _stage_a_paths(stage_v1_root, label="Stage-A v1")
    support_paths = _support_paths(support_root)
    stage_v2_paths = _stage_a_paths(stage_v2_root, label="Stage-A v2 Return")
    return_stability_paths = _return_stability_paths(return_stability_root)
    dig_validation_paths = _dig_validation_paths(dig_validation_root)

    stage_v1_manifest = _load_json_mapping(stage_v1_paths["manifest"])
    _validate_stage_a_manifest(
        stage_v1_manifest,
        label="Stage-A v1",
        source_root=source_root,
        source_paths=source_paths,
        dig_config=dig_config,
        return_config=return_config,
    )
    support_manifest = _load_json_mapping(support_paths["manifest"])
    selected_return_candidate = _validate_support_audit(
        support_manifest,
        source_root=source_root,
        source_paths=source_paths,
        stage_v1_paths=stage_v1_paths,
        dig_config=dig_config,
        return_config=return_config,
    )
    _validate_support_payloads(
        candidates=_load_json_mapping(support_paths["candidates"]),
        validation=_load_json_mapping(support_paths["validation"]),
        selected_return_candidate=selected_return_candidate,
    )

    stage_v2_manifest = _load_json_mapping(stage_v2_paths["manifest"])
    _validate_stage_a_manifest(
        stage_v2_manifest,
        label="Stage-A v2 Return",
        source_root=source_root,
        source_paths=source_paths,
        dig_config=dig_config,
        return_config=return_config,
    )
    _validate_stage_v2_return_support(
        stage_v2_manifest,
        support_paths=support_paths,
        selected_return_candidate=selected_return_candidate,
    )

    return_stability_manifest = _load_json_mapping(return_stability_paths["manifest"])
    return_segments = _load_json_mapping(return_stability_paths["return_segments"])
    return_causal_status = _validate_return_stability_audit(
        manifest=return_stability_manifest,
        payload=return_segments,
        source_root=source_root,
        source_paths=source_paths,
        return_config=return_config,
        stage_v2_paths=stage_v2_paths,
    )

    dig_manifest = _load_json_mapping(dig_validation_paths["manifest"])
    dig_candidates = _load_json_mapping(dig_validation_paths["candidates"])
    dig_validation = _load_json_mapping(dig_validation_paths["validation"])
    dig_support_decision = _validate_dig_joint_validation(
        manifest=dig_manifest,
        candidates=dig_candidates,
        validation=dig_validation,
        dig_config=dig_config,
    )

    additional_lineage = {
        "a2_prerequisite_audits": {
            "schema": V3_PREREQUISITE_BINDING_SCHEMA,
            "stage_b_eligible": False,
            "stage_a_v1": {name: _source_record(path) for name, path in stage_v1_paths.items()},
            "support_contract_v2": {
                name: _source_record(path) for name, path in support_paths.items()
            },
            "stage_a_v2_return": {
                name: _source_record(path) for name, path in stage_v2_paths.items()
            },
            "return_goal_response_stability": {
                **{
                    name: _source_record(path)
                    for name, path in return_stability_paths.items()
                },
                "fixed_required_responsive_frame_fraction": REQUIRED_RESPONSIVE_FRAME_FRACTION,
                "segment_causal_status": return_causal_status,
            },
            "dig_joint_support_validation": {
                **{
                    name: _source_record(path)
                    for name, path in dig_validation_paths.items()
                },
                **dig_support_decision,
            },
            "applied_support_contracts": {
                "dig": {
                    "support_contract_version": "support_contract_v1",
                    "candidate_id": "axis_p01_p99_v1",
                },
                "return": {
                    "support_contract_version": SUPPORT_CONTRACT_VERSION,
                    "candidate_id": selected_return_candidate,
                },
            },
            "stage_b_claim": "none",
        }
    }

    runner = primitive_scoped_runner or run_primitive_scoped_stage_a_support_audit
    result = runner(
        source_results_root=source_root,
        stage_a_v1_output_root=stage_v1_root,
        support_audit_output_root=support_root,
        dig_training_config_path=dig_config,
        return_training_config_path=return_config,
        output_root=destination,
        device=str(device),
        additional_source_lineage=additional_lineage,
    )
    if not isinstance(result, Mapping):
        raise StageAV3PrerequisiteBindingError(
            "primitive-scoped Stage-A runner must return a mapping"
        )
    return {
        **dict(result),
        "dig_support_decision": dig_support_decision,
        "stage_a_v3_prerequisite_binding": additional_lineage[
            "a2_prerequisite_audits"
        ],
    }


def _source_paths(source_root: Path) -> dict[str, Path]:
    paths = {
        "eval_resolved_config": source_root / "eval_resolved_config.yaml",
        "eval_run_metadata": source_root / "eval_run_metadata.json",
        "rollout_jsonl": source_root / "rollouts" / "rollout_000.jsonl",
        "rollout_hdf5": source_root / "hdf5_rollouts" / "episode_0.hdf5",
    }
    _require_files(paths, label="source results")
    return paths


def _stage_a_paths(root: Path, *, label: str) -> dict[str, Path]:
    paths = {
        "manifest": root / "manifest.json",
        "baseline": root / "baseline.json",
        "dig": root / "dig.json",
        "return": root / "return.json",
    }
    _require_files(paths, label=label)
    return paths


def _support_paths(root: Path) -> dict[str, Path]:
    paths = {
        "manifest": root / "manifest.json",
        "candidates": root / "candidates.json",
        "validation": root / "validation.json",
    }
    _require_files(paths, label="support-contract audit")
    return paths


def _return_stability_paths(root: Path) -> dict[str, Path]:
    paths = {
        "manifest": root / "manifest.json",
        "return_segments": root / "return_segments.json",
    }
    _require_files(paths, label="Return stability audit")
    return paths


def _dig_validation_paths(root: Path) -> dict[str, Path]:
    paths = {
        "manifest": root / "manifest.json",
        "candidates": root / "candidates.json",
        "validation": root / "validation.json",
    }
    _require_files(paths, label="Dig joint validation")
    return paths


def _validate_stage_a_manifest(
    manifest: Mapping[str, Any],
    *,
    label: str,
    source_root: Path,
    source_paths: Mapping[str, Path],
    dig_config: Path,
    return_config: Path,
) -> None:
    if manifest.get("schema") != ACT_GOAL_CONDITION_SENSITIVITY_MANIFEST_SCHEMA:
        raise StageAV3PrerequisiteBindingError(f"{label} manifest schema mismatch")
    if manifest.get("status") != "completed":
        raise StageAV3PrerequisiteBindingError(f"{label} artifact is not completed")
    _validate_teacher_forced_boundary(manifest, label=label)
    _require_clean_code(manifest.get("clean_code"), label=f"{label} code")
    lineage = _mapping(manifest.get("source_lineage"), f"{label} source lineage")
    _verify_source_root(lineage, source_root=source_root, label=label)
    _verify_source_records(
        lineage,
        paths={
            **source_paths,
            "dig_training_config": dig_config,
            "return_training_config": return_config,
        },
        label=label,
    )


def _validate_support_audit(
    manifest: Mapping[str, Any],
    *,
    source_root: Path,
    source_paths: Mapping[str, Path],
    stage_v1_paths: Mapping[str, Path],
    dig_config: Path,
    return_config: Path,
) -> str:
    if manifest.get("schema") != SUPPORT_AUDIT_MANIFEST_SCHEMA:
        raise StageAV3PrerequisiteBindingError("support-contract manifest schema mismatch")
    if manifest.get("support_contract_version") != SUPPORT_CONTRACT_VERSION:
        raise StageAV3PrerequisiteBindingError("support-contract version mismatch")
    if str(manifest.get("status", "")) not in {
        "completed",
        "support_contract_not_selected",
    }:
        raise StageAV3PrerequisiteBindingError("support-contract audit is not completed")
    _validate_teacher_forced_boundary(manifest, label="support-contract audit")
    if manifest.get("target_rollout_used_for_selection") is not False:
        raise StageAV3PrerequisiteBindingError(
            "support-contract selection used target rollout evidence"
        )
    lineage = _mapping(manifest.get("source_lineage"), "support-contract source lineage")
    _require_clean_code(lineage.get("code"), label="support-contract code")
    _verify_source_root(lineage, source_root=source_root, label="support-contract audit")
    _verify_source_records(
        lineage,
        paths={
            **source_paths,
            "dig_training_config": dig_config,
            "return_training_config": return_config,
        },
        label="support-contract audit",
    )
    _verify_source_records(
        lineage,
        paths={
            f"stage_a_{name}": path for name, path in stage_v1_paths.items()
        },
        label="support-contract audit",
    )
    selected = _mapping(
        manifest.get("selected_candidate_by_primitive"),
        "support-contract selected candidates",
    )
    selection_status = _mapping(
        manifest.get("selection_status_by_primitive"),
        "support-contract selection statuses",
    )
    candidate = str(selected.get("return", "")).strip()
    if not candidate or selection_status.get("return") != "selected":
        raise StageAV3PrerequisiteBindingError(
            "support-contract audit has no selected Return candidate"
        )
    return candidate


def _validate_support_payloads(
    *,
    candidates: Mapping[str, Any],
    validation: Mapping[str, Any],
    selected_return_candidate: str,
) -> None:
    if candidates.get("schema") != SUPPORT_AUDIT_CANDIDATES_SCHEMA:
        raise StageAV3PrerequisiteBindingError("support candidates schema mismatch")
    if candidates.get("support_contract_version") != SUPPORT_CONTRACT_VERSION:
        raise StageAV3PrerequisiteBindingError("support candidates contract mismatch")
    primitives = _mapping(candidates.get("primitives"), "support candidates primitives")
    return_candidates = primitives.get("return")
    if not isinstance(return_candidates, Sequence) or isinstance(
        return_candidates, (str, bytes)
    ):
        raise StageAV3PrerequisiteBindingError("support candidates lack Return records")
    if not any(
        isinstance(candidate, Mapping)
        and str(candidate.get("candidate_id", "")).strip()
        == selected_return_candidate
        for candidate in return_candidates
    ):
        raise StageAV3PrerequisiteBindingError(
            "selected Return candidate is absent from immutable candidates"
        )
    if validation.get("schema") != SUPPORT_AUDIT_VALIDATION_SCHEMA:
        raise StageAV3PrerequisiteBindingError("support validation schema mismatch")
    if validation.get("support_contract_version") != SUPPORT_CONTRACT_VERSION:
        raise StageAV3PrerequisiteBindingError("support validation contract mismatch")
    if validation.get("target_rollout_used_for_selection") is not False:
        raise StageAV3PrerequisiteBindingError("support validation admits target rollout")


def _validate_stage_v2_return_support(
    manifest: Mapping[str, Any],
    *,
    support_paths: Mapping[str, Path],
    selected_return_candidate: str,
) -> None:
    contracts = _mapping(
        manifest.get("applied_support_contract_by_primitive"),
        "Stage-A v2 applied support contracts",
    )
    return_contract = _mapping(contracts.get("return"), "Stage-A v2 Return support")
    if return_contract.get("support_contract_version") != SUPPORT_CONTRACT_VERSION:
        raise StageAV3PrerequisiteBindingError(
            "Stage-A v2 Return did not apply support_contract_v2"
        )
    if str(return_contract.get("candidate_id", "")).strip() != selected_return_candidate:
        raise StageAV3PrerequisiteBindingError(
            "Stage-A v2 Return candidate differs from support-contract audit"
        )
    _verify_record(
        return_contract.get("support_audit_manifest"),
        path=support_paths["manifest"],
        label="Stage-A v2 support manifest",
    )
    _verify_record(
        return_contract.get("support_audit_candidates"),
        path=support_paths["candidates"],
        label="Stage-A v2 support candidates",
    )


def _validate_return_stability_audit(
    *,
    manifest: Mapping[str, Any],
    payload: Mapping[str, Any],
    source_root: Path,
    source_paths: Mapping[str, Path],
    return_config: Path,
    stage_v2_paths: Mapping[str, Path],
) -> dict[str, str]:
    if manifest.get("schema") != RETURN_STABILITY_MANIFEST_SCHEMA:
        raise StageAV3PrerequisiteBindingError("Return stability manifest schema mismatch")
    if manifest.get("status") != "completed":
        raise StageAV3PrerequisiteBindingError("Return stability audit is not completed")
    _validate_teacher_forced_boundary(manifest, label="Return stability audit")
    fixed_gate = _mapping(manifest.get("fixed_gate"), "Return stability fixed gate")
    if not math.isclose(
        float(fixed_gate.get("required_responsive_frame_fraction", -1.0)),
        REQUIRED_RESPONSIVE_FRAME_FRACTION,
        rel_tol=0.0,
        abs_tol=0.0,
    ) or fixed_gate.get("change_policy") != "no_threshold_change_permitted":
        raise StageAV3PrerequisiteBindingError(
            "Return stability audit did not preserve the fixed 80 percent gate"
        )
    if tuple(manifest.get("target_segment_ids", ())) != RETURN_INVALID_SEGMENT_IDS:
        raise StageAV3PrerequisiteBindingError("Return stability target segment set changed")
    lineage = _mapping(manifest.get("source_lineage"), "Return stability source lineage")
    _require_clean_code(lineage.get("code"), label="Return stability code")
    _verify_source_root(lineage, source_root=source_root, label="Return stability audit")
    _verify_source_records(
        lineage,
        paths={**source_paths, "return_training_config": return_config},
        label="Return stability audit",
    )
    _verify_source_records(
        lineage,
        paths={f"stage_a_v2_{name}": path for name, path in stage_v2_paths.items() if name != "dig"},
        label="Return stability audit",
    )

    if payload.get("schema") != RETURN_STABILITY_RESULTS_SCHEMA:
        raise StageAV3PrerequisiteBindingError("Return stability segments schema mismatch")
    if payload.get("status") != "completed":
        raise StageAV3PrerequisiteBindingError("Return stability segments are not completed")
    if payload.get("evidence_kind") != EVIDENCE_KIND:
        raise StageAV3PrerequisiteBindingError("Return stability segments evidence kind mismatch")
    if payload.get("diagnostic_only") is not True or payload.get("promotion_eligible") is not False:
        raise StageAV3PrerequisiteBindingError("Return stability segments evidence boundary mismatch")
    segments = payload.get("segments")
    if not isinstance(segments, Sequence) or isinstance(segments, (str, bytes)):
        raise StageAV3PrerequisiteBindingError("Return stability segments must be a sequence")
    by_id: dict[str, Mapping[str, Any]] = {}
    for item in segments:
        record = _mapping(item, "Return stability segment")
        baseline = _mapping(record.get("baseline_segment"), "Return stability baseline segment")
        segment_id = str(baseline.get("segment_id", "")).strip()
        if not segment_id or segment_id in by_id:
            raise StageAV3PrerequisiteBindingError("Return stability segment ids are invalid")
        by_id[segment_id] = record
    if tuple(by_id) != RETURN_INVALID_SEGMENT_IDS:
        raise StageAV3PrerequisiteBindingError("Return stability segments differ from fixed invalid pairs")
    statuses: dict[str, str] = {}
    for segment_id in RETURN_INVALID_SEGMENT_IDS:
        record = by_id[segment_id]
        if record.get("status") != "completed":
            raise StageAV3PrerequisiteBindingError(
                f"Return stability segment is not completed: {segment_id}"
            )
        alternate = _mapping(
            record.get("alternate_segment"),
            "Return stability alternate segment",
        )
        if (
            str(alternate.get("segment_id", "")).strip()
            != _EXPECTED_RETURN_ALTERNATE_SEGMENT_IDS[segment_id]
        ):
            raise StageAV3PrerequisiteBindingError(
                f"Return stability alternate segment changed: {segment_id}"
            )
        causal = _mapping(record.get("causal_status"), "Return stability causal status")
        status = str(causal.get("status", "")).strip()
        if status in {"normalization_mismatch", "observation_history_mismatch"}:
            raise StageAV3PrerequisiteBindingError(
                f"Return stability causal status blocks v3: {status} ({segment_id})"
            )
        if status not in _ALLOWED_RETURN_CAUSAL_STATUSES:
            raise StageAV3PrerequisiteBindingError(
                f"Return stability causal status is not recognised: {status} ({segment_id})"
            )
        statuses[segment_id] = status
    return statuses


def _validate_dig_joint_validation(
    *,
    manifest: Mapping[str, Any],
    candidates: Mapping[str, Any],
    validation: Mapping[str, Any],
    dig_config: Path,
) -> dict[str, str]:
    if manifest.get("schema") != DIG_JOINT_MANIFEST_SCHEMA:
        raise StageAV3PrerequisiteBindingError("Dig joint manifest schema mismatch")
    if manifest.get("support_contract_version") != DIG_JOINT_CONTRACT_VERSION:
        raise StageAV3PrerequisiteBindingError("Dig joint contract version mismatch")
    if manifest.get("diagnostic_only") is not True or manifest.get("promotion_eligible") is not False:
        raise StageAV3PrerequisiteBindingError("Dig joint evidence boundary mismatch")
    if manifest.get("runtime_support_change") is not False:
        raise StageAV3PrerequisiteBindingError("Dig joint audit changed runtime support")
    if manifest.get("target_rollout_used_for_selection") is not False:
        raise StageAV3PrerequisiteBindingError("Dig joint selection used target evidence")
    if manifest.get("selection_input_scope") != "strict_train_and_held_validation_only":
        raise StageAV3PrerequisiteBindingError("Dig joint selection input scope changed")
    lineage = _mapping(manifest.get("source_lineage"), "Dig joint source lineage")
    _require_clean_code(lineage.get("code"), label="Dig joint validation code")
    _verify_record(
        lineage.get("dig_training_config"),
        path=dig_config,
        label="Dig joint training config",
    )
    _validate_dig_joint_payload(
        payload=candidates,
        expected_schema=DIG_JOINT_CANDIDATES_SCHEMA,
        label="Dig joint candidates",
    )
    _validate_dig_joint_payload(
        payload=validation,
        expected_schema=DIG_JOINT_VALIDATION_SCHEMA,
        label="Dig joint validation",
    )
    selected_values = (
        manifest.get("selected_candidate_id"),
        candidates.get("selected_candidate_id"),
        validation.get("selected_candidate_id"),
    )
    statuses = (
        manifest.get("selection_status"),
        candidates.get("selection_status"),
        validation.get("selection_status"),
    )
    if len(set(selected_values)) != 1 or len(set(statuses)) != 1:
        raise StageAV3PrerequisiteBindingError("Dig joint selection records disagree")
    selected = selected_values[0]
    selection_status = str(statuses[0])
    if (
        manifest.get("status") == "support_contract_not_selected"
        and selected is None
        and selection_status == "not_selected"
    ):
        return {
            "decision": "keep_support_contract_v1",
            "candidate_id": "axis_p01_p99_v1",
            "reason": "independent_dig_joint_validation_support_contract_not_selected",
        }
    if manifest.get("status") == "completed" and selected is not None and selection_status == "selected":
        raise StageAV3PrerequisiteBindingError(
            "Dig joint validation selected a Dig candidate; v3 cannot silently fall back to v1"
        )
    raise StageAV3PrerequisiteBindingError("Dig joint audit status is not bindable")


def _validate_dig_joint_payload(
    *,
    payload: Mapping[str, Any],
    expected_schema: str,
    label: str,
) -> None:
    if payload.get("schema") != expected_schema:
        raise StageAV3PrerequisiteBindingError(f"{label} schema mismatch")
    if payload.get("support_contract_version") != DIG_JOINT_CONTRACT_VERSION:
        raise StageAV3PrerequisiteBindingError(f"{label} contract mismatch")
    if payload.get("primitive") != "dig":
        raise StageAV3PrerequisiteBindingError(f"{label} primitive mismatch")
    if payload.get("target_rollout_used_for_selection") is not False:
        raise StageAV3PrerequisiteBindingError(f"{label} admits target rollout")


def _validate_teacher_forced_boundary(manifest: Mapping[str, Any], *, label: str) -> None:
    if manifest.get("evidence_kind") != EVIDENCE_KIND:
        raise StageAV3PrerequisiteBindingError(f"{label} evidence kind mismatch")
    if manifest.get("diagnostic_only") is not True:
        raise StageAV3PrerequisiteBindingError(f"{label} is not diagnostic-only")
    if manifest.get("promotion_eligible") is not False:
        raise StageAV3PrerequisiteBindingError(f"{label} is promotion-eligible")
    if manifest.get("closed_loop_claim") is not False:
        raise StageAV3PrerequisiteBindingError(f"{label} has a closed-loop claim")


def _verify_source_root(
    lineage: Mapping[str, Any],
    *,
    source_root: Path,
    label: str,
) -> None:
    raw = lineage.get("source_results_root")
    if raw is None:
        raise StageAV3PrerequisiteBindingError(f"{label} lacks source_results_root")
    try:
        recorded = Path(str(raw)).expanduser().resolve(strict=True)
    except OSError as exc:
        raise StageAV3PrerequisiteBindingError(
            f"{label} source_results_root is not readable"
        ) from exc
    if recorded != source_root:
        raise StageAV3PrerequisiteBindingError(
            f"{label} source_results_root does not match requested source"
        )


def _verify_source_records(
    lineage: Mapping[str, Any],
    *,
    paths: Mapping[str, Path],
    label: str,
) -> None:
    for name, path in paths.items():
        _verify_record(lineage.get(name), path=path, label=f"{label} {name}")


def _verify_record(raw: Any, *, path: Path, label: str) -> None:
    record = _mapping(raw, f"{label} lineage record")
    resolved = path.expanduser().resolve(strict=True)
    recorded_path = record.get("path")
    if recorded_path is None:
        raise StageAV3PrerequisiteBindingError(f"{label} lineage record lacks path")
    try:
        expected_path = Path(str(recorded_path)).expanduser().resolve(strict=True)
    except OSError as exc:
        raise StageAV3PrerequisiteBindingError(f"{label} lineage path is not readable") from exc
    if expected_path != resolved:
        raise StageAV3PrerequisiteBindingError(f"{label} lineage path mismatch")
    if str(record.get("sha256", "")) != _sha256(resolved):
        raise StageAV3PrerequisiteBindingError(f"{label} SHA mismatch")
    if "size_bytes" in record and int(record["size_bytes"]) != resolved.stat().st_size:
        raise StageAV3PrerequisiteBindingError(f"{label} size mismatch")


def _require_clean_code(value: Any, *, label: str) -> None:
    record = _mapping(value, label)
    if record.get("worktree_clean") is not True:
        raise StageAV3PrerequisiteBindingError(f"{label} was not produced from a clean worktree")
    if not str(record.get("git_head", "")).strip():
        raise StageAV3PrerequisiteBindingError(f"{label} lacks git head")


def _require_distinct_output_root(
    *,
    destination: Path,
    immutable_roots: Mapping[str, Path],
) -> None:
    for label, root in immutable_roots.items():
        if destination == root or _is_relative_to(destination, root):
            raise StageAV3PrerequisiteBindingError(
                f"output_root must be distinct from {label}"
            )


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _source_record(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve(strict=True)
    return {
        "path": str(resolved),
        "sha256": _sha256(resolved),
        "size_bytes": int(resolved.stat().st_size),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json_mapping(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StageAV3PrerequisiteBindingError(f"invalid JSON artifact: {path}") from exc
    return _mapping(payload, str(path))


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise StageAV3PrerequisiteBindingError(f"{label} must be a mapping")
    return dict(value)


def _require_files(paths: Mapping[str, Path], *, label: str) -> None:
    missing = [f"{name}={path}" for name, path in paths.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"{label} missing required files: {', '.join(missing)}")


__all__ = [
    "StageAV3PrerequisiteBindingError",
    "run_stage_a_v3_after_prerequisite_audits",
]
