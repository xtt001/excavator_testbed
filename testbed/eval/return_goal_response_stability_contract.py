"""Immutable evidence and artifact contracts for the Return stability audit.

This module owns filesystem lineage checks and no-overwrite evidence writing.
It does not load an ACT model, construct a replay observation, or interpret
temporal aggregation.
"""

from __future__ import annotations

import hashlib
import json
import math
import pickle
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from testbed.eval.act_goal_condition_sensitivity import EVIDENCE_KIND

STAGE_A_MANIFEST_SCHEMA = "act_goal_condition_sensitivity_manifest_v1"
RETURN_GOAL_RESPONSE_STABILITY_MANIFEST_SCHEMA = (
    "return_goal_response_stability_audit_manifest_v1"
)
RETURN_GOAL_RESPONSE_STABILITY_RESULTS_SCHEMA = (
    "return_goal_response_stability_audit_results_v1"
)
OUTPUT_ROOT_NAME = "return_goal_response_stability_audit_v1"
SUPPORT_CONTRACT_VERSION = "support_contract_v2"
REQUIRED_RESPONSIVE_FRAME_FRACTION = 0.80
ACTION_STD_FRACTION = 0.05
RETURN_INVALID_SEGMENT_IDS = (
    "return:898-1043:bb329f176aba",
    "return:3959-4161:4afcef2eee82",
)
_EXPECTED_ALTERNATE_SEGMENT_BY_BASELINE = {
    RETURN_INVALID_SEGMENT_IDS[0]: RETURN_INVALID_SEGMENT_IDS[1],
    RETURN_INVALID_SEGMENT_IDS[1]: "return:2323-2534:87aa0fb8c981",
}


class ReturnGoalResponseStabilityAuditError(ValueError):
    """Raised when immutable Stage-A evidence cannot safely be audited."""


def load_immutable_stage_context(stage_root: str | Path) -> dict[str, Any]:
    """Resolve and SHA-verify every immutable input required by the audit."""

    root = Path(stage_root).expanduser().resolve(strict=True)
    stage_paths = {
        "manifest": root / "manifest.json",
        "baseline": root / "baseline.json",
        "return": root / "return.json",
    }
    require_files(stage_paths, label="immutable Return-v2 Stage-A evidence")
    manifest = load_json_mapping(stage_paths["manifest"])
    payload = load_json_mapping(stage_paths["return"])
    validate_stage_manifest(manifest)
    invalid_records = select_invalid_records(payload)
    lineage = mapping(manifest.get("source_lineage"), "Stage-A source lineage")
    source_root = Path(str(lineage.get("source_results_root", ""))).expanduser().resolve(strict=True)
    paths = {
        "eval_config": verify_source_lineage_record(lineage, "eval_resolved_config"),
        "eval_metadata": verify_source_lineage_record(lineage, "eval_run_metadata"),
        "rollout_jsonl": verify_source_lineage_record(lineage, "rollout_jsonl"),
        "rollout_hdf5": verify_source_lineage_record(lineage, "rollout_hdf5"),
        "return_training_config": verify_source_lineage_record(
            lineage, "return_training_config"
        ),
    }
    checkpoints = mapping(lineage.get("checkpoints_and_stats"), "Stage-A checkpoints")
    return_checkpoint = mapping(checkpoints.get("return"), "Stage-A Return checkpoint")
    paths["checkpoint"] = verify_source_record(
        mapping(return_checkpoint.get("checkpoint"), "Return checkpoint record"),
        label="Return checkpoint",
    )
    paths["stats"] = verify_source_record(
        mapping(return_checkpoint.get("dataset_stats"), "Return stats record"),
        label="Return dataset stats",
    )
    eval_config = load_yaml_mapping(paths["eval_config"])
    training_config = load_yaml_mapping(paths["return_training_config"])
    policy = mapping(eval_config.get("policy"), "resolved eval policy")
    task = mapping(eval_config.get("task"), "resolved eval task")
    low_dim_keys = tuple(str(value) for value in policy.get("return_low_dim_keys", ()))
    expected_keys = ("qpos", "qvel", "return_start_envelope_tokens_v1")
    if low_dim_keys != expected_keys:
        raise ReturnGoalResponseStabilityAuditError(
            f"resolved Return low_dim_keys must be {expected_keys!r}, got {low_dim_keys!r}"
        )
    training_policy = mapping(training_config.get("policy"), "Return training policy")
    train_keys = tuple(str(value) for value in training_policy.get("low_dim_keys", ()))
    if train_keys != low_dim_keys:
        raise ReturnGoalResponseStabilityAuditError(
            "Return training and resolved evaluation low_dim_keys differ"
        )
    config_checkpoint = Path(str(policy.get("return_ckpt_path", ""))).expanduser().resolve(strict=True)
    if config_checkpoint != paths["checkpoint"]:
        raise ReturnGoalResponseStabilityAuditError(
            "resolved evaluation Return checkpoint differs from immutable Stage-A lineage"
        )
    camera_names = tuple(str(value) for value in task.get("camera_names", ()))
    if not camera_names or len(camera_names) != len(set(camera_names)):
        raise ReturnGoalResponseStabilityAuditError("resolved evaluation camera order is invalid")
    with paths["stats"].open("rb") as handle:
        norm_stats = pickle.load(handle)
    if not isinstance(norm_stats, Mapping):
        raise ReturnGoalResponseStabilityAuditError("Return dataset_stats.pkl is not a mapping")
    return {
        "stage_paths": stage_paths,
        "stage_manifest": manifest,
        "invalid_records": invalid_records,
        "source_results_root": source_root,
        "paths": paths,
        "eval_config": eval_config,
        "low_dim_keys": low_dim_keys,
        "camera_names": camera_names,
        "norm_stats": dict(norm_stats),
    }


def validate_stage_manifest(manifest: Mapping[str, Any]) -> None:
    """Require the exact diagnostic-only Return-v2 Stage-A boundary."""

    if manifest.get("schema") != STAGE_A_MANIFEST_SCHEMA:
        raise ReturnGoalResponseStabilityAuditError("Stage-A manifest schema mismatch")
    if manifest.get("status") != "completed":
        raise ReturnGoalResponseStabilityAuditError("Stage-A v2 artifact is not completed")
    if manifest.get("evidence_kind") != EVIDENCE_KIND:
        raise ReturnGoalResponseStabilityAuditError("Stage-A evidence kind is not teacher-forced replay")
    if (
        manifest.get("diagnostic_only") is not True
        or manifest.get("promotion_eligible") is not False
        or manifest.get("closed_loop_claim") is not False
    ):
        raise ReturnGoalResponseStabilityAuditError("Stage-A evidence boundary is invalid")
    contracts = mapping(
        manifest.get("applied_support_contract_by_primitive"),
        "Stage-A support contracts",
    )
    return_contract = mapping(contracts.get("return"), "Stage-A Return support contract")
    if return_contract.get("support_contract_version") != SUPPORT_CONTRACT_VERSION:
        raise ReturnGoalResponseStabilityAuditError("Stage-A Return artifact did not use support_contract_v2")


def select_invalid_records(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Select only the two pre-registered invalid pairs from Stage-A v2."""

    if payload.get("primitive") != "return" or payload.get("status") != "completed":
        raise ReturnGoalResponseStabilityAuditError("Stage-A Return payload is not completed")
    records = payload.get("segment_pair_records")
    if not isinstance(records, Sequence):
        raise ReturnGoalResponseStabilityAuditError("Stage-A Return payload lacks segment pair records")
    by_id = {
        str(mapping(record, "Stage-A segment record").get("segment", {}).get("segment_id", "")): dict(record)
        for record in records
        if isinstance(record, Mapping)
    }
    selected: list[dict[str, Any]] = []
    for segment_id in RETURN_INVALID_SEGMENT_IDS:
        record = by_id.get(segment_id)
        if record is None:
            raise ReturnGoalResponseStabilityAuditError(
                f"immutable target segment is missing: {segment_id}"
            )
        alternate_id = str(
            mapping(record.get("alternate_segment"), "Stage-A alternate segment").get(
                "segment_id", ""
            )
        )
        if alternate_id != _EXPECTED_ALTERNATE_SEGMENT_BY_BASELINE[segment_id]:
            raise ReturnGoalResponseStabilityAuditError(
                f"immutable alternate segment changed for {segment_id}"
            )
        invalid_condition_from_stage_record(record)
        selected.append(record)
    return selected


def invalid_condition_from_stage_record(record: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the precondition that a pair is v2-supported but gate-invalid."""

    result = mapping(record.get("result"), "Stage-A segment result")
    if result.get("status") != "completed":
        raise ReturnGoalResponseStabilityAuditError("target Stage-A segment is not completed")
    validity = mapping(result.get("artifact_validity"), "target artifact validity")
    if validity.get("passed") is not True:
        raise ReturnGoalResponseStabilityAuditError("target Stage-A artifact validity failed")
    conditions = mapping(result.get("conditions"), "target Stage-A conditions")
    invalid = [
        dict(value)
        for value in conditions.values()
        if isinstance(value, Mapping) and value.get("classification") == "goal_response_invalid"
    ]
    if len(invalid) != 1:
        raise ReturnGoalResponseStabilityAuditError(
            "target Stage-A record must contain exactly one invalid alternate"
        )
    condition = invalid[0]
    support = mapping(condition.get("support"), "target alternate support")
    for name in ("baseline", "counterfactual"):
        item = mapping(support.get(name), f"target {name} support")
        if item.get("status") != "supported" or float(item.get("in_support_fraction", 0.0)) != 1.0:
            raise ReturnGoalResponseStabilityAuditError(
                "target invalid Return pair is not fully in support_contract_v2"
            )
    replica = mapping(condition.get("replica_validity"), "target replica validity")
    if replica.get("passed") is not True:
        raise ReturnGoalResponseStabilityAuditError("target alternate replicas were not exact")
    gate = mapping(condition.get("response_gate"), "target response gate")
    if (
        gate.get("passed") is not False
        or not math.isclose(
            float(gate.get("required_responsive_frame_fraction", -1.0)),
            REQUIRED_RESPONSIVE_FRAME_FRACTION,
            rel_tol=0.0,
            abs_tol=0.0,
        )
        or int(gate.get("responsive_anchor_count", -1)) != int(gate.get("anchor_count", -2))
        or int(gate.get("anchor_count", -1)) != 3
    ):
        raise ReturnGoalResponseStabilityAuditError("target invalid pair does not match fixed 80 percent Stage-A gate")
    return condition


def write_artifact(
    *,
    output_root: str | Path,
    manifest: Mapping[str, Any],
    segment_results: Mapping[str, Any],
    report_markdown: str,
) -> None:
    """Write the fixed audit root once, after all diagnostic values exist."""

    destination = Path(output_root).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"Return response-stability output already exists: {destination}")
    destination.mkdir(parents=True, exist_ok=False)
    write_json_exclusive(destination / "manifest.json", manifest)
    write_json_exclusive(destination / "return_segments.json", segment_results)
    with (destination / "report.md").open("x", encoding="utf-8") as handle:
        handle.write(report_markdown)


def source_record(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve(strict=True)
    return {
        "path": str(resolved),
        "sha256": sha256(resolved),
        "size_bytes": int(resolved.stat().st_size),
    }


def verify_source_lineage_record(lineage: Mapping[str, Any], name: str) -> Path:
    return verify_source_record(
        mapping(lineage.get(name), f"Stage-A source lineage {name}"),
        label=f"Stage-A source lineage {name}",
    )


def verify_source_record(record: Mapping[str, Any], *, label: str) -> Path:
    path = Path(str(record.get("path", ""))).expanduser().resolve(strict=True)
    expected_hash = str(record.get("sha256", ""))
    expected_size = int(record.get("size_bytes", -1))
    if not expected_hash or sha256(path) != expected_hash or path.stat().st_size != expected_size:
        raise ReturnGoalResponseStabilityAuditError(f"immutable source lineage mismatch: {label}")
    return path


def report_markdown(*, status: str, segments: Sequence[Mapping[str, Any]]) -> str:
    """Render a concise reader-facing report from already computed evidence."""

    lines = [
        "# Return 目标条件响应稳定性离线审计",
        "",
        f"状态：`{status}`。固定响应门槛仍为 80%，本审计没有降低或重新拟合该门槛。",
        "证据只来自冻结 checkpoint 下的 teacher-forced 记录回放，不证明 Unity 闭环、土方效果或生产可用性。",
        "",
    ]
    for item in segments:
        baseline = mapping(item.get("baseline_segment"), "audit baseline segment")
        causal = mapping(item.get("causal_status"), "audit causal status")
        temporal = item.get("temporal_aggregation", {})
        fraction = (
            "unknown"
            if not isinstance(temporal, Mapping)
            else f"{float(temporal.get('temporal_aggregated_response_fraction', float('nan'))):.3f}"
        )
        lines.append(
            f"- `{baseline.get('segment_id', 'unknown')}`：`{causal.get('status', 'unknown')}`；"
            f"重放聚合响应比例 {fraction}。"
        )
    lines.extend(
        (
            "",
            "若输入合同和重放均可复现，下一步只能针对明确归因处理；不能用本工件降低 80% 门槛。",
            "",
        )
    )
    return "\n".join(lines)


def clean_code_record() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    return {
        "git_head": git_output(root, "rev-parse", "HEAD"),
        "git_branch": git_output(root, "branch", "--show-current"),
        "worktree_clean": not bool(git_output(root, "status", "--short")),
    }


def mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ReturnGoalResponseStabilityAuditError(f"{label} must be a mapping")
    return dict(value)


def finite_vector(value: Any, *, label: str):
    """Deferred NumPy conversion helper, kept here to share validation text."""

    import numpy as np

    array = np.asarray(value, dtype=np.float32).reshape(-1)
    if array.size == 0 or not np.isfinite(array).all():
        raise ReturnGoalResponseStabilityAuditError(f"{label} must be a finite vector")
    return array


def finite_array(value: Any, *, label: str, ndim: int):
    """Deferred NumPy conversion helper, kept here to share validation text."""

    import numpy as np

    array = np.asarray(value, dtype=np.float32)
    if array.ndim != ndim or array.size == 0 or not np.isfinite(array).all():
        raise ReturnGoalResponseStabilityAuditError(
            f"{label} must be a finite rank-{ndim} array"
        )
    return array


def field(value: Any, name: str, default: Any) -> Any:
    return value.get(name, default) if isinstance(value, Mapping) else getattr(value, name, default)


def integer_field(value: Any, name: str) -> int:
    raw = field(value, name, None)
    if isinstance(raw, bool):
        raise ReturnGoalResponseStabilityAuditError(f"{name} must be an integer")
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ReturnGoalResponseStabilityAuditError(f"{name} must be an integer") from exc


def sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json_exclusive(path: Path, payload: Mapping[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(json_ready(dict(payload)), handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")


def json_ready(value: Any) -> Any:
    try:
        import numpy as np

        if isinstance(value, np.ndarray):
            return json_ready(value.tolist())
        if isinstance(value, np.generic):
            return value.item()
    except ImportError:
        pass
    if isinstance(value, Mapping):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ReturnGoalResponseStabilityAuditError("audit JSON cannot contain non-finite values")
    return value


def load_json_mapping(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReturnGoalResponseStabilityAuditError(f"invalid JSON artifact: {path}") from exc
    return mapping(value, str(path))


def load_yaml_mapping(path: Path) -> dict[str, Any]:
    return mapping(yaml.safe_load(path.read_text(encoding="utf-8")) or {}, str(path))


def require_files(paths: Mapping[str, Path], *, label: str) -> None:
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"{label} missing required files: {', '.join(missing)}")


def git_output(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


__all__ = [
    "ACTION_STD_FRACTION",
    "EVIDENCE_KIND",
    "OUTPUT_ROOT_NAME",
    "REQUIRED_RESPONSIVE_FRAME_FRACTION",
    "RETURN_GOAL_RESPONSE_STABILITY_MANIFEST_SCHEMA",
    "RETURN_GOAL_RESPONSE_STABILITY_RESULTS_SCHEMA",
    "RETURN_INVALID_SEGMENT_IDS",
    "ReturnGoalResponseStabilityAuditError",
    "STAGE_A_MANIFEST_SCHEMA",
    "SUPPORT_CONTRACT_VERSION",
    "clean_code_record",
    "field",
    "finite_array",
    "finite_vector",
    "integer_field",
    "invalid_condition_from_stage_record",
    "json_ready",
    "load_immutable_stage_context",
    "mapping",
    "report_markdown",
    "sha256",
    "source_record",
    "write_artifact",
]
