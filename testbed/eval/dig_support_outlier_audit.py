"""No-overwrite offline audit for a frozen ACT numeric-support outlier.

The audit joins three separate facts before reporting a Dig OOS conclusion:

* the immutable Stage-A pair that was rejected;
* the recorded JSONL/HDF5 alignment used by that pair; and
* source-safe strict-train and held-validation distributions.

It never fits a replacement support rule from the target segment.  Its result
therefore distinguishes an input-contract defect from an unsupported state,
without promoting either a planner change or a runtime relaxation.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from testbed.data.dig_support_outlier_alignment import (
    DIG_SUPPORT_OUTLIER_ALIGNMENT_SCHEMA,
    audit_dig_support_outlier_alignment_from_paths,
)
from testbed.data.dig_support_outlier_distribution import (
    analyze_dig_support_outlier_segment,
    load_dig_support_outlier_distribution_references,
)
from testbed.eval.act_goal_condition_sensitivity import (
    ACT_GOAL_CONDITION_SENSITIVITY_MANIFEST_SCHEMA,
    EVIDENCE_KIND,
)

DIG_SUPPORT_OUTLIER_AUDIT_MANIFEST_SCHEMA = "dig_support_outlier_audit_manifest_v1"
DIG_SUPPORT_OUTLIER_AUDIT_RESULT_SCHEMA = "dig_support_outlier_audit_result_v1"
TARGET_SEGMENT_ID = "dig:1044-1083:37a4b7afda73"
V1_CANDIDATE_ID = "axis_p01_p99_v1"


class DigSupportOutlierAuditError(ValueError):
    """Raised when an OOS diagnosis would lose its immutable evidence boundary."""


def run_dig_support_outlier_audit(
    *,
    stage_a_v3_output_root: str | Path,
    output_root: str | Path,
    dig_training_config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Audit the fixed Stage-A Dig OOS segment into a fresh evidence root.

    The target replay is used only to describe its already-recorded feature
    trace.  All p01/p99 bounds, nearest neighbours, and held-validation
    statistics are loaded from the canonical strict Dig configuration.
    """

    destination = Path(output_root).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"Dig support-outlier output already exists: {destination}")
    clean_code = _clean_code_record()
    if not bool(clean_code["worktree_clean"]):
        raise RuntimeError("Dig support-outlier audit requires a clean Git worktree")

    stage_root = Path(stage_a_v3_output_root).expanduser().resolve(strict=True)
    stage_paths = _stage_a_paths(stage_root)
    stage_manifest = _load_json_mapping(stage_paths["manifest"])
    source = _validate_stage_a_v3_manifest(stage_manifest)
    dig_payload = _load_json_mapping(stage_paths["dig"])
    stage_pair = _validate_target_stage_pair(dig_payload)

    configured_training_path = Path(
        str(source["dig_training_config"]["path"])
    ).expanduser().resolve(strict=True)
    training_path = (
        configured_training_path
        if dig_training_config_path is None
        else Path(dig_training_config_path).expanduser().resolve(strict=True)
    )
    if training_path != configured_training_path:
        raise DigSupportOutlierAuditError(
            "requested Dig training config differs from immutable Stage-A v3 lineage"
        )
    _verify_record(source["dig_training_config"], training_path, "Dig training config")

    alignment = audit_dig_support_outlier_alignment_from_paths(
        rollout_hdf5_path=source["rollout_hdf5"]["path"],
        rollout_jsonl_path=source["rollout_jsonl"]["path"],
        dig_training_config_path=training_path,
        target_segment_id=TARGET_SEGMENT_ID,
    )
    if alignment.get("schema") != DIG_SUPPORT_OUTLIER_ALIGNMENT_SCHEMA:
        raise DigSupportOutlierAuditError("Dig alignment audit schema mismatch")
    target_features = _target_feature_matrix(alignment.get("frame_table"))
    references = load_dig_support_outlier_distribution_references(
        training_config_path=training_path,
    )
    distribution = analyze_dig_support_outlier_segment(
        references=references,
        target_features=target_features,
    ).as_dict()
    joint_validation = _load_and_validate_joint_validation(stage_manifest)
    decision = derive_dig_support_outlier_decision(
        alignment=alignment,
        distribution=distribution,
        joint_validation=joint_validation,
    )

    result = {
        "schema": DIG_SUPPORT_OUTLIER_AUDIT_RESULT_SCHEMA,
        "status": "completed",
        "evidence_kind": EVIDENCE_KIND,
        "diagnostic_only": True,
        "promotion_eligible": False,
        "closed_loop_claim": False,
        "runtime_support_change": False,
        "threshold_change": False,
        "training_change": False,
        "target_rollout_used_for_support_fit_or_selection": False,
        "target_segment_id": TARGET_SEGMENT_ID,
        "stage_a_v3_pair": stage_pair,
        "frame_table": alignment["frame_table"],
        "alignment": {
            key: value for key, value in alignment.items() if key != "frame_table"
        },
        "distribution": distribution,
        "decision": decision,
    }
    manifest = _manifest(
        stage_paths=stage_paths,
        source=source,
        training_path=training_path,
        joint_validation=joint_validation,
        clean_code=clean_code,
    )
    report = _render_report(result)
    _write_artifact(
        output_root=destination,
        manifest=manifest,
        result=result,
        report_markdown=report,
    )
    return {"status": "completed", "output_root": str(destination), "manifest": manifest}


def derive_dig_support_outlier_decision(
    *,
    alignment: Mapping[str, Any],
    distribution: Mapping[str, Any],
    joint_validation: Mapping[str, Any],
) -> dict[str, Any]:
    """Make only the fail-closed handling decision licensed by audit facts.

    This deliberately does not convert a nearest-neighbour distance into a new
    threshold.  A target may have single-axis numerical precedents while still
    lack a validation-qualified full-state support contract.
    """

    alignment_status = str(alignment.get("status", ""))
    if alignment_status != "completed":
        return {
            "decision": "repair_data_contract_then_rerun_stage_a",
            "reason": "recorded alignment or training feature contract did not pass",
            "runtime_handling": "do_not_interpret_current_oos_as_model_capability",
        }

    excursion = _mapping(
        distribution.get("segment_qvel1_excursion_measurement"),
        "qvel[1] excursion",
    )
    populations = _mapping(
        distribution.get("qvel1_v1_outside_numeric_range_populations"),
        "qvel[1] OOS-range populations",
    )
    train_overlap = _mapping(
        populations.get("strict_train_action_loss_mask_1"),
        "strict-train qvel[1] overlap",
    )
    joint_status = str(joint_validation.get("status", ""))
    selected = joint_validation.get("selected_candidate_id")
    multi_frame = excursion.get("v1_excursion_topology") == "one_contiguous_multi_frame_run"
    train_overlap_count = int(train_overlap.get("within_target_interval_row_count", 0))

    if multi_frame:
        recording_assessment = "not_a_single_frame_spike"
    else:
        recording_assessment = "requires_recording_qc_review"

    if train_overlap_count > 0:
        numeric_coverage = "qvel1_has_strict_train_numeric_precedents"
    else:
        numeric_coverage = "qvel1_has_no_strict_train_numeric_precedents"

    if joint_status == "support_contract_not_selected" and selected is None:
        validation_boundary = "no_validation_qualified_joint_rule_available"
    else:
        validation_boundary = "joint_validation_state_requires_manual_review"

    return {
        "decision": "retain_v1_runtime_rejection_or_stop",
        "reason": (
            "alignment is valid, but this audit does not establish a "
            "validation-qualified support relaxation"
        ),
        "alignment_assessment": "valid",
        "recording_assessment": recording_assessment,
        "numeric_coverage_assessment": numeric_coverage,
        "full_state_coverage_assessment": (
            "nearest-neighbour evidence is descriptive only; it does not certify "
            "a support contract"
        ),
        "validation_boundary": validation_boundary,
        "runtime_handling": (
            "keep support_contract_v1 and reject_or_stop this unsupported handoff; "
            "do not widen bounds"
        ),
        "if_operation_requires_this_state": (
            "collect expert data around the Return-to-Dig handoff and retrain only "
            "after a new source-disjoint validation contract is approved"
        ),
    }


def _stage_a_paths(root: Path) -> dict[str, Path]:
    paths = {"manifest": root / "manifest.json", "dig": root / "dig.json"}
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Stage-A v3 artifact lacks required files: {missing}")
    return paths


def _validate_stage_a_v3_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    if manifest.get("schema") != ACT_GOAL_CONDITION_SENSITIVITY_MANIFEST_SCHEMA:
        raise DigSupportOutlierAuditError("Stage-A v3 manifest schema mismatch")
    if manifest.get("status") != "completed":
        raise DigSupportOutlierAuditError("Stage-A v3 artifact is not completed")
    if (
        manifest.get("evidence_kind") != EVIDENCE_KIND
        or manifest.get("diagnostic_only") is not True
        or manifest.get("promotion_eligible") is not False
        or manifest.get("closed_loop_claim") is not False
    ):
        raise DigSupportOutlierAuditError("Stage-A v3 evidence boundary mismatch")
    clean = _mapping(manifest.get("clean_code"), "Stage-A v3 clean code")
    if clean.get("worktree_clean") is not True:
        raise DigSupportOutlierAuditError("Stage-A v3 source code was not clean")
    lineage = _mapping(manifest.get("source_lineage"), "Stage-A v3 source lineage")
    expected = ("rollout_hdf5", "rollout_jsonl", "dig_training_config")
    result = {name: _mapping(lineage.get(name), f"Stage-A v3 {name}") for name in expected}
    for name, record in result.items():
        _verify_record(record, Path(str(record["path"])), f"Stage-A v3 {name}")
    source_root = Path(str(lineage.get("source_results_root", ""))).expanduser().resolve(
        strict=True
    )
    result["source_results_root"] = str(source_root)
    result["additional_audit_lineage"] = _mapping(
        lineage.get("additional_audit_lineage"), "Stage-A v3 prerequisite lineage"
    )
    return result


def _validate_target_stage_pair(dig_payload: Mapping[str, Any]) -> dict[str, Any]:
    if dig_payload.get("primitive") != "dig" or dig_payload.get("status") != "completed":
        raise DigSupportOutlierAuditError("Stage-A v3 Dig payload is not completed")
    records = dig_payload.get("segment_pair_records")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise DigSupportOutlierAuditError("Stage-A v3 Dig payload lacks segment records")
    matches = [
        item
        for item in records
        if isinstance(item, Mapping)
        and _mapping(item.get("segment"), "Stage-A Dig segment").get("segment_id")
        == TARGET_SEGMENT_ID
    ]
    if len(matches) != 1:
        raise DigSupportOutlierAuditError("target Dig OOS segment is missing or duplicated")
    record = _mapping(matches[0], "target Dig OOS pair")
    result = _mapping(record.get("result"), "target Dig OOS result")
    if result.get("status") != "completed":
        raise DigSupportOutlierAuditError("target Dig OOS result is not completed")
    conditions = _mapping(result.get("conditions"), "target Dig OOS conditions")
    oos = [
        value
        for value in conditions.values()
        if isinstance(value, Mapping) and value.get("classification") == "out_of_support"
    ]
    if len(oos) != 1:
        raise DigSupportOutlierAuditError("target Dig segment no longer has one OOS pair")
    support = _mapping(oos[0].get("support"), "target Dig OOS support")
    violations = []
    for side in ("baseline", "counterfactual"):
        assessment = _mapping(support.get(side), f"target Dig {side} support")
        if assessment.get("status") != "out_of_support":
            raise DigSupportOutlierAuditError("target Dig OOS support status changed")
        violations.extend(
            item
            for row in assessment.get("violations", ())
            if isinstance(row, Sequence)
            for item in row
            if isinstance(item, Mapping)
        )
    if not any(item.get("field") == "qvel[1]" for item in violations):
        raise DigSupportOutlierAuditError("target Dig OOS is no longer attributed to qvel[1]")
    return {
        "segment_id": TARGET_SEGMENT_ID,
        "classification": "out_of_support",
        "support_candidate_id": V1_CANDIDATE_ID,
        "stage_pair_record": record,
    }


def _load_and_validate_joint_validation(
    stage_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    extra = _mapping(
        _mapping(
            _mapping(stage_manifest.get("source_lineage"), "Stage-A source lineage").get(
                "additional_audit_lineage"
            ),
            "Stage-A prerequisite lineage",
        ).get("a2_prerequisite_audits"),
        "Stage-A A.2 prerequisite lineage",
    )
    dig = _mapping(extra.get("dig_joint_support_validation"), "Dig joint validation lineage")
    manifest_record = _mapping(dig.get("manifest"), "Dig joint validation manifest")
    validation_record = _mapping(dig.get("validation"), "Dig joint validation payload")
    manifest_path = Path(str(manifest_record.get("path", ""))).expanduser().resolve(strict=True)
    validation_path = Path(str(validation_record.get("path", ""))).expanduser().resolve(strict=True)
    _verify_record(manifest_record, manifest_path, "Dig joint validation manifest")
    _verify_record(validation_record, validation_path, "Dig joint validation payload")
    manifest = _load_json_mapping(manifest_path)
    validation = _load_json_mapping(validation_path)
    if (
        manifest.get("status") != "support_contract_not_selected"
        or manifest.get("selected_candidate_id") is not None
        or validation.get("selection_status") != "not_selected"
    ):
        raise DigSupportOutlierAuditError(
            "Dig joint validation no longer proves the frozen no-selection boundary"
        )
    return {
        "status": str(manifest["status"]),
        "selected_candidate_id": None,
        "manifest": _source_record(manifest_path),
        "validation": _source_record(validation_path),
    }


def _target_feature_matrix(frame_table: Any) -> np.ndarray:
    if not isinstance(frame_table, Sequence) or isinstance(frame_table, (str, bytes)):
        raise DigSupportOutlierAuditError("Dig alignment frame table must be a sequence")
    rows: list[np.ndarray] = []
    for frame in frame_table:
        value = _mapping(frame, "Dig alignment frame")
        parts = (value.get("qpos"), value.get("qvel"), value.get("token"))
        arrays = [np.asarray(part, dtype=np.float64).reshape(-1) for part in parts]
        if [array.shape for array in arrays] != [(4,), (4,), (10,)]:
            raise DigSupportOutlierAuditError("Dig alignment frame feature width mismatch")
        rows.append(np.concatenate(arrays, axis=0))
    if not rows:
        raise DigSupportOutlierAuditError("Dig alignment frame table is empty")
    result = np.stack(rows, axis=0)
    if not np.isfinite(result).all():
        raise DigSupportOutlierAuditError("Dig target feature matrix is non-finite")
    result.setflags(write=False)
    return result


def _manifest(
    *,
    stage_paths: Mapping[str, Path],
    source: Mapping[str, Any],
    training_path: Path,
    joint_validation: Mapping[str, Any],
    clean_code: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": DIG_SUPPORT_OUTLIER_AUDIT_MANIFEST_SCHEMA,
        "status": "completed",
        "evidence_kind": EVIDENCE_KIND,
        "diagnostic_only": True,
        "promotion_eligible": False,
        "closed_loop_claim": False,
        "runtime_support_change": False,
        "threshold_change": False,
        "training_change": False,
        "target_rollout_used_for_support_fit_or_selection": False,
        "target_segment_id": TARGET_SEGMENT_ID,
        "source_lineage": {
            "stage_a_v3_manifest": _source_record(stage_paths["manifest"]),
            "stage_a_v3_dig": _source_record(stage_paths["dig"]),
            "rollout_hdf5": dict(source["rollout_hdf5"]),
            "rollout_jsonl": dict(source["rollout_jsonl"]),
            "dig_training_config": _source_record(training_path),
            "dig_joint_validation": dict(joint_validation),
            "code": dict(clean_code),
        },
        "output_files": [
            "manifest.json",
            "stage_a_v3_pair.json",
            "frame_table.json",
            "alignment.json",
            "distribution.json",
            "decision.json",
            "report.md",
        ],
    }


def _render_report(result: Mapping[str, Any]) -> str:
    alignment = _mapping(result.get("alignment"), "alignment result")
    distribution = _mapping(result.get("distribution"), "distribution result")
    decision = _mapping(result.get("decision"), "decision")
    excursion = _mapping(
        distribution.get("segment_qvel1_excursion_measurement"), "qvel excursion"
    )
    populations = _mapping(
        distribution.get("qvel1_v1_outside_numeric_range_populations"),
        "qvel OOS-range populations",
    )
    train = _mapping(populations.get("strict_train_action_loss_mask_1"), "strict train")
    return "\n".join(
        [
            "# Dig 数值支持范围异常离线审计",
            "",
            "这份工件只解释已被 v1 拒绝的记录状态，未修改支持范围、训练、运行时或安全链。",
            "",
            f"- 目标段：`{TARGET_SEGMENT_ID}`",
            f"- 对齐审计：`{alignment.get('status')}`；所有动作仍绑定前一帧 observation。",
            (
                "- qvel[1] v1 越界："
                f"{excursion.get('qvel1_v1_outside_frame_count')} 帧，"
                f"{excursion.get('v1_excursion_topology')}。"
            ),
            (
                "- 严格训练 action_loss_mask=1 在同一数值区间的行数："
                f"{train.get('within_target_interval_row_count')}。"
            ),
            f"- 处理决定：`{decision.get('decision')}`。",
            "",
            "该结果不证明实际挖掘效果、物理单位、闭环安全或“指哪挖哪”。",
            "",
        ]
    )


def _write_artifact(
    *,
    output_root: Path,
    manifest: Mapping[str, Any],
    result: Mapping[str, Any],
    report_markdown: str,
) -> None:
    if output_root.exists():
        raise FileExistsError(f"Dig support-outlier output already exists: {output_root}")
    output_root.mkdir(parents=True, exist_ok=False)
    _write_json_exclusive(output_root / "manifest.json", manifest)
    _write_json_exclusive(output_root / "stage_a_v3_pair.json", result["stage_a_v3_pair"])
    _write_json_exclusive(output_root / "frame_table.json", {"frames": result["frame_table"]})
    _write_json_exclusive(output_root / "alignment.json", result["alignment"])
    _write_json_exclusive(output_root / "distribution.json", result["distribution"])
    _write_json_exclusive(output_root / "decision.json", result["decision"])
    with (output_root / "report.md").open("x", encoding="utf-8") as handle:
        handle.write(report_markdown)


def _verify_record(record: Mapping[str, Any], path: Path, label: str) -> None:
    resolved = path.expanduser().resolve(strict=True)
    if Path(str(record.get("path", ""))).expanduser().resolve(strict=True) != resolved:
        raise DigSupportOutlierAuditError(f"{label} path disagrees with its lineage")
    if str(record.get("sha256", "")) != _sha256(resolved):
        raise DigSupportOutlierAuditError(f"{label} SHA disagrees with its lineage")
    if int(record.get("size_bytes", -1)) != int(resolved.stat().st_size):
        raise DigSupportOutlierAuditError(f"{label} size disagrees with its lineage")


def _source_record(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve(strict=True)
    return {
        "path": str(resolved),
        "sha256": _sha256(resolved),
        "size_bytes": int(resolved.stat().st_size),
    }


def _clean_code_record() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    return {
        "git_head": _git_output(root, "rev-parse", "HEAD"),
        "git_branch": _git_output(root, "branch", "--show-current"),
        "worktree_clean": not bool(_git_output(root, "status", "--short")),
    }


def _git_output(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, check=False, capture_output=True, text=True
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


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
        raise DigSupportOutlierAuditError(f"invalid JSON artifact: {path}") from exc
    return _mapping(payload, str(path))


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise DigSupportOutlierAuditError(f"{label} must be a mapping")
    return dict(value)


def _write_json_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


__all__ = [
    "DIG_SUPPORT_OUTLIER_AUDIT_MANIFEST_SCHEMA",
    "DIG_SUPPORT_OUTLIER_AUDIT_RESULT_SCHEMA",
    "DigSupportOutlierAuditError",
    "TARGET_SEGMENT_ID",
    "derive_dig_support_outlier_decision",
    "run_dig_support_outlier_audit",
]
