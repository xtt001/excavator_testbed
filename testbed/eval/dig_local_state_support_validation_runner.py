"""No-overwrite file runner for local complete-state Dig support validation.

This runner intentionally has no Stage-A or target-rollout parameter.  It
freezes a local support candidate only from strict Dig training and held-out
validation evidence; a later target diagnosis must load this written result
instead of refitting from an observed OOS segment.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from testbed.data.dig_local_state_support import (
    load_strict_dig_local_state_support_rows,
)
from testbed.eval.dig_local_state_support_validation import (
    DIG_LOCAL_STATE_SUPPORT_CONTRACT_VERSION,
    DIG_LOCAL_STATE_SUPPORT_VALIDATION_SCHEMA,
    run_dig_local_state_support_validation,
)

DIG_LOCAL_STATE_SUPPORT_VALIDATION_MANIFEST_SCHEMA = (
    "dig_local_complete_state_validation_manifest_v1"
)
DIG_LOCAL_STATE_SUPPORT_CANDIDATES_SCHEMA = "dig_local_complete_state_candidates_v1"
DIG_LOCAL_STATE_SUPPORT_VALIDATION_ARTIFACT_SCHEMA = (
    "dig_local_complete_state_validation_artifact_v1"
)


def run_dig_local_state_support_validation_from_file(
    *,
    dig_training_config_path: str | Path,
    output_root: str | Path,
) -> dict[str, Any]:
    """Validate frozen local Dig support candidates into a new artifact root."""

    destination = Path(output_root).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(
            f"local Dig support-validation output already exists: {destination}"
        )
    clean_code = _clean_code_record()
    if not bool(clean_code["worktree_clean"]):
        raise RuntimeError("local Dig support-validation requires a clean Git worktree")
    config_path = Path(dig_training_config_path).expanduser().resolve(strict=True)
    rows = load_strict_dig_local_state_support_rows(training_config_path=config_path)
    audit = run_dig_local_state_support_validation(rows=rows)
    _validate_audit(audit)

    source_lineage = {
        "dig_training_config": _source_record(config_path),
        "primitive_dataset_dir": _directory_record(Path(rows.primitive_dataset_dir)),
        "source_aware_split": _source_record(Path(rows.split_path)),
        "code": clean_code,
    }
    manifest = {
        "schema": DIG_LOCAL_STATE_SUPPORT_VALIDATION_MANIFEST_SCHEMA,
        "status": audit["status"],
        "support_contract_version": DIG_LOCAL_STATE_SUPPORT_CONTRACT_VERSION,
        "diagnostic_only": True,
        "promotion_eligible": False,
        "runtime_support_change": False,
        "target_rollout_used_for_selection": False,
        "selection_input_scope": "strict_train_and_held_validation_only",
        "source_lineage": source_lineage,
        "source_separation": audit["source_separation"],
        "selected_candidate_id": audit["selected_candidate_id"],
        "selection_status": audit["selection_status"],
        "artifact_files": {
            "candidates": "candidates.json",
            "validation": "validation.json",
            "report": "report.md",
        },
    }
    candidates = {
        "schema": DIG_LOCAL_STATE_SUPPORT_CANDIDATES_SCHEMA,
        "support_contract_version": DIG_LOCAL_STATE_SUPPORT_CONTRACT_VERSION,
        "primitive": "dig",
        "target_rollout_used_for_selection": False,
        "candidate_family": audit["candidate_family"],
        "candidates": audit["candidates"],
        "selected_candidate_id": audit["selected_candidate_id"],
        "selection_status": audit["selection_status"],
    }
    validation = {
        "schema": DIG_LOCAL_STATE_SUPPORT_VALIDATION_ARTIFACT_SCHEMA,
        "support_contract_version": DIG_LOCAL_STATE_SUPPORT_CONTRACT_VERSION,
        "primitive": "dig",
        "target_rollout_used_for_selection": False,
        "selection_input_scope": audit["selection_input_scope"],
        "selection_metrics": audit["selection_metrics"],
        "source_separation": audit["source_separation"],
        "strict_train_feasibility": audit["strict_train_feasibility"],
        "validation_neighbor_cohort": audit["validation_neighbor_cohort"],
        "frozen_obvious_ood_neighbor_cohort": audit[
            "frozen_obvious_ood_neighbor_cohort"
        ],
        "frozen_obvious_ood": _compact_obvious_ood(audit["frozen_obvious_ood"]),
        "candidate_validation": [
            {
                key: candidate[key]
                for key in (
                    "candidate_id",
                    "fixed_order",
                    "validation_normal_coverage",
                    "validation_distance_coverage",
                    "validation_neighbor_count_coverage",
                    "validation_source_diversity_coverage",
                    "validation_action_coherence_coverage",
                    "validation_action_axis_coherence_coverage",
                    "frozen_obvious_ood_rejection",
                    "validation_normal_coverage_passed",
                    "frozen_obvious_ood_rejection_passed",
                    "qualified",
                    "qualification_status",
                )
            }
            for candidate in audit["candidates"]
        ],
        "selected_candidate_id": audit["selected_candidate_id"],
        "selection_status": audit["selection_status"],
    }
    report = _render_report(audit=audit, source_lineage=source_lineage)

    destination.mkdir(parents=True, exist_ok=False)
    _write_json_exclusive(destination / "manifest.json", manifest)
    _write_json_exclusive(destination / "candidates.json", candidates)
    _write_json_exclusive(destination / "validation.json", validation)
    _write_text_exclusive(destination / "report.md", report)
    return {
        "status": audit["status"],
        "output_root": str(destination),
        "selected_candidate_id": audit["selected_candidate_id"],
        "manifest": manifest,
    }


def _validate_audit(audit: Mapping[str, Any]) -> None:
    if audit.get("schema") != DIG_LOCAL_STATE_SUPPORT_VALIDATION_SCHEMA:
        raise ValueError("local Dig support-validation audit schema mismatch")
    if audit.get("support_contract_version") != DIG_LOCAL_STATE_SUPPORT_CONTRACT_VERSION:
        raise ValueError("local Dig support-validation contract version mismatch")
    if audit.get("target_rollout_used_for_selection") is not False:
        raise ValueError("local Dig support-validation admits target rollout evidence")
    if audit.get("runtime_support_change") is not False:
        raise ValueError("local Dig support-validation changes runtime support")


def _compact_obvious_ood(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("frozen local Dig OOD evidence must be a mapping")
    provenance = value.get("anchor_provenance", ())
    if not isinstance(provenance, Sequence) or isinstance(provenance, (str, bytes)):
        raise ValueError("frozen local Dig OOD provenance must be a sequence")
    source_ids = sorted(
        {
            int(item["source_episode_id"])
            for item in provenance
            if isinstance(item, Mapping) and "source_episode_id" in item
        }
    )
    return {
        "schema": value.get("schema"),
        "feature_order": value.get("feature_order"),
        "anchor_partition": value.get("anchor_partition"),
        "multiplier": value.get("multiplier"),
        "row_count": len(provenance),
        "anchor_source_episode_ids": source_ids,
        "provenance_serialized": False,
    }


def _render_report(*, audit: Mapping[str, Any], source_lineage: Mapping[str, Any]) -> str:
    lines = [
        "# Dig 局部完整状态支持合同验证",
        "",
        f"- 状态：`{audit['status']}`",
        f"- 选中的候选：`{audit['selected_candidate_id']}`",
        "- 输入仅包含 strict-train 和 source-disjoint held validation；没有读取 Stage-A 或目标 OOS 段。",
        "- 规则要求完整 18D 状态邻居、跨 source episode 和专家动作一致性；没有改变 runtime 或训练。",
        "- frozen obvious-OOD 是保留验证来源构造的数值负对照，不代表真实现场陌生状态。",
        f"- Dig 训练配置 SHA256：`{source_lineage['dig_training_config']['sha256']}`",
        "",
        "| candidate | validation coverage | OOD rejection | qualified |",
        "|---|---:|---:|---:|",
    ]
    for candidate in audit["candidates"]:
        lines.append(
            "| {candidate_id} | {coverage:.6f} | {rejection:.6f} | {qualified} |".format(
                candidate_id=candidate["candidate_id"],
                coverage=float(candidate["validation_normal_coverage"]),
                rejection=float(candidate["frozen_obvious_ood_rejection"]),
                qualified=bool(candidate["qualified"]),
            )
        )
    lines.extend(
        [
            "",
            "该工件只冻结离线局部支持比较，不能自动放宽 v1 或证明真实挖掘效果。",
            "",
        ]
    )
    return "\n".join(lines)


def _source_record(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve(strict=True)
    return {
        "path": str(resolved),
        "sha256": _sha256(resolved),
        "size_bytes": int(resolved.stat().st_size),
    }


def _directory_record(path: Path) -> dict[str, str]:
    resolved = path.expanduser().resolve(strict=True)
    if not resolved.is_dir():
        raise NotADirectoryError(resolved)
    return {"path": str(resolved)}


def _clean_code_record() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    return {
        "git_head": _git_output(root, "rev-parse", "HEAD"),
        "git_branch": _git_output(root, "branch", "--show-current"),
        "worktree_clean": not bool(_git_output(root, "status", "--short")),
    }


def _git_output(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=root, check=False, capture_output=True, text=True
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _write_text_exclusive(path: Path, text: str) -> None:
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


__all__ = [
    "DIG_LOCAL_STATE_SUPPORT_CANDIDATES_SCHEMA",
    "DIG_LOCAL_STATE_SUPPORT_VALIDATION_ARTIFACT_SCHEMA",
    "DIG_LOCAL_STATE_SUPPORT_VALIDATION_MANIFEST_SCHEMA",
    "run_dig_local_state_support_validation_from_file",
]
