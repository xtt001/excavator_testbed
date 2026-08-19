"""File orchestration for the independent Dig joint-support validation audit.

The runner reads one Dig training configuration, writes a no-overwrite audit
artifact, and never opens a recorded Stage-A result.  Candidate fitting and
selection remain in the pure evaluator so this module only supplies lineage
and artifact handling.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from testbed.data.dig_joint_support_validation import (
    load_dig_joint_support_validation_rows,
)
from testbed.eval.dig_joint_support_validation_audit import (
    DIG_JOINT_SUPPORT_VALIDATION_AUDIT_SCHEMA,
    DIG_JOINT_SUPPORT_VALIDATION_CONTRACT_VERSION,
    run_dig_joint_support_validation_audit,
)

DIG_JOINT_SUPPORT_VALIDATION_MANIFEST_SCHEMA = (
    "dig_joint_support_validation_manifest_v1"
)
DIG_JOINT_SUPPORT_VALIDATION_CANDIDATES_SCHEMA = (
    "dig_joint_support_validation_candidates_v1"
)
DIG_JOINT_SUPPORT_VALIDATION_VALIDATION_SCHEMA = (
    "dig_joint_support_validation_validation_v1"
)


def run_dig_joint_support_validation_audit_from_file(
    *,
    dig_training_config_path: str | Path,
    output_root: str | Path,
) -> dict[str, Any]:
    """Write one no-overwrite Dig validation artifact from strict source data.

    ``dig_training_config_path`` is the only evidence input.  In particular,
    there is no source rollout path, Stage-A artifact path, or runtime-policy
    argument.  This keeps threshold selection separate from target outcomes.
    """

    destination = Path(output_root).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(
            f"Dig joint support-validation output already exists: {destination}"
        )
    clean_code = _clean_code_record()
    if not bool(clean_code["worktree_clean"]):
        raise RuntimeError(
            "Dig joint support-validation audit requires a clean Git worktree"
        )
    config_path = Path(dig_training_config_path).expanduser().resolve(strict=True)
    rows = load_dig_joint_support_validation_rows(
        training_config_path=str(config_path)
    )
    audit = run_dig_joint_support_validation_audit(rows=rows)
    _validate_audit_payload(audit)

    source_lineage = {
        "dig_training_config": _source_record(config_path),
        "primitive_dataset_dir": _directory_record(Path(rows.primitive_dataset_dir)),
        "source_aware_split": _source_record(Path(rows.split_path)),
        "code": clean_code,
    }
    manifest = {
        "schema": DIG_JOINT_SUPPORT_VALIDATION_MANIFEST_SCHEMA,
        "status": audit["status"],
        "support_contract_version": DIG_JOINT_SUPPORT_VALIDATION_CONTRACT_VERSION,
        "diagnostic_only": True,
        "promotion_eligible": False,
        "runtime_support_change": False,
        "target_rollout_used_for_selection": False,
        "selection_input_scope": "strict_train_and_held_validation_only",
        "source_lineage": source_lineage,
        "source_separation": audit["source_separation"],
        "validation_v1_edge_cohort": audit["validation_v1_edge_cohort"],
        "selected_candidate_id": audit["selected_candidate_id"],
        "selection_status": audit["selection_status"],
        "artifact_files": {
            "candidates": "candidates.json",
            "validation": "validation.json",
            "audit": "audit.json",
            "report": "report.md",
        },
    }
    candidates = {
        "schema": DIG_JOINT_SUPPORT_VALIDATION_CANDIDATES_SCHEMA,
        "support_contract_version": DIG_JOINT_SUPPORT_VALIDATION_CONTRACT_VERSION,
        "primitive": "dig",
        "target_rollout_used_for_selection": False,
        "candidate_family": audit["candidate_family"],
        "candidates": audit["candidates"],
        "selected_candidate_id": audit["selected_candidate_id"],
        "selection_status": audit["selection_status"],
    }
    validation = {
        "schema": DIG_JOINT_SUPPORT_VALIDATION_VALIDATION_SCHEMA,
        "support_contract_version": DIG_JOINT_SUPPORT_VALIDATION_CONTRACT_VERSION,
        "primitive": "dig",
        "target_rollout_used_for_selection": False,
        "selection_input_scope": audit["selection_input_scope"],
        "selection_metrics": audit["selection_metrics"],
        "source_separation": audit["source_separation"],
        "validation_v1_edge_cohort": audit["validation_v1_edge_cohort"],
        "frozen_obvious_ood": audit["frozen_obvious_ood"],
        "candidate_validation": [
            {
                key: record[key]
                for key in (
                    "candidate_id",
                    "fixed_order",
                    "train_score_quantile",
                    "validation_normal_coverage",
                    "validation_v1_edge_coverage",
                    "validation_v1_edge_nonempty",
                    "frozen_obvious_ood_rejection",
                    "validation_normal_coverage_passed",
                    "validation_v1_edge_coverage_passed",
                    "frozen_obvious_ood_rejection_passed",
                    "qualified",
                    "qualification_status",
                )
            }
            for record in audit["candidates"]
        ],
        "selected_candidate_id": audit["selected_candidate_id"],
        "selection_status": audit["selection_status"],
    }
    report = _render_report(audit=audit, source_lineage=source_lineage)

    # Only create the directory after every input has been parsed and the
    # complete result exists.  A created root is immutable evidence.
    destination.mkdir(parents=True, exist_ok=False)
    _write_json_exclusive(destination / "manifest.json", manifest)
    _write_json_exclusive(destination / "candidates.json", candidates)
    _write_json_exclusive(destination / "validation.json", validation)
    _write_json_exclusive(destination / "audit.json", audit)
    _write_text_exclusive(destination / "report.md", report)
    return {
        "status": audit["status"],
        "output_root": str(destination),
        "selected_candidate_id": audit["selected_candidate_id"],
        "manifest": manifest,
    }


def _validate_audit_payload(audit: Mapping[str, Any]) -> None:
    if audit.get("schema") != DIG_JOINT_SUPPORT_VALIDATION_AUDIT_SCHEMA:
        raise ValueError("Dig joint support-validation audit schema mismatch")
    if audit.get("support_contract_version") != DIG_JOINT_SUPPORT_VALIDATION_CONTRACT_VERSION:
        raise ValueError("Dig joint support-validation contract version mismatch")
    if audit.get("target_rollout_used_for_selection") is not False:
        raise ValueError("Dig joint support-validation audit admits target rollout input")
    if audit.get("runtime_support_change") is not False:
        raise ValueError("Dig joint support-validation audit changes runtime support")


def _source_record(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve(strict=True)
    return {
        "path": str(resolved),
        "sha256": _sha256(resolved),
        "size_bytes": int(resolved.stat().st_size),
    }


def _directory_record(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve(strict=True)
    if not resolved.is_dir():
        raise NotADirectoryError(resolved)
    return {"path": str(resolved)}


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


def _write_json_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _write_text_exclusive(path: Path, content: str) -> None:
    with path.open("x", encoding="utf-8") as handle:
        handle.write(content)


def _render_report(*, audit: Mapping[str, Any], source_lineage: Mapping[str, Any]) -> str:
    selected = audit.get("selected_candidate_id")
    status = audit.get("status")
    lines = [
        "# Dig 联合支持范围验证审计",
        "",
        f"- 状态：`{status}`",
        f"- 选中的候选：`{selected}`",
        "- 输入：仅 strict-train 与 source-disjoint held validation；未读取 Stage-A 或 target rollout。",
        "- 运行时：未改变 runtime support gate、Planner、ACT checkpoint 或安全阈值。",
        "- synthetic obvious-OOD 仅是数值负对照，不代表真实现场陌生状态。",
        f"- Dig 训练配置 SHA256：`{source_lineage['dig_training_config']['sha256']}`",
        "",
        "| candidate | validation coverage | v1 edge coverage | obvious-OOD rejection | qualified |",
        "|---|---:|---:|---:|---:|",
    ]
    for record in audit["candidates"]:
        lines.append(
            "| {candidate_id} | {coverage:.6f} | {edge} | {rejection:.6f} | {qualified} |".format(
                candidate_id=record["candidate_id"],
                coverage=float(record["validation_normal_coverage"]),
                edge=(
                    "n/a"
                    if record["validation_v1_edge_coverage"] is None
                    else f"{float(record['validation_v1_edge_coverage']):.6f}"
                ),
                rejection=float(record["frozen_obvious_ood_rejection"]),
                qualified=bool(record["qualified"]),
            )
        )
    lines.extend(
        [
            "",
            "该结果只冻结离线候选比较，不能证明记录回放或真实挖掘结果。",
            "",
        ]
    )
    return "\n".join(lines)


__all__ = [
    "DIG_JOINT_SUPPORT_VALIDATION_CANDIDATES_SCHEMA",
    "DIG_JOINT_SUPPORT_VALIDATION_MANIFEST_SCHEMA",
    "DIG_JOINT_SUPPORT_VALIDATION_VALIDATION_SCHEMA",
    "run_dig_joint_support_validation_audit_from_file",
]
