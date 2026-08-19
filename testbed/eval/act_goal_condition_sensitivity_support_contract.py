"""Primitive-scoped binding from frozen support evidence to a new Stage-A replay.

This module is intentionally a narrow orchestration boundary.  It does not fit
or relax a support rule, alter ACT inference, or write a new artifact itself.
It verifies immutable Stage-A and support-audit lineage, loads the already
selected Return candidate, then delegates the no-overwrite replay to the
existing Stage-A runner.  Dig is deliberately omitted from the override map so
the runner retains its published v1 support contract.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import numpy as np

from testbed.data.frozen_act_support_candidate import (
    load_frozen_selected_support_candidate,
)
from testbed.eval.act_goal_condition_sensitivity import (
    ACT_GOAL_CONDITION_SENSITIVITY_MANIFEST_SCHEMA,
    EVIDENCE_KIND,
)
from testbed.eval.act_goal_condition_sensitivity_runner import (
    build_frozen_candidate_support_assessor,
    run_act_goal_condition_sensitivity_audit,
)

SUPPORT_AUDIT_MANIFEST_SCHEMA = "act_support_contract_audit_manifest_v1"
SUPPORT_CONTRACT_VERSION = "support_contract_v2"
_ALLOWED_SUPPORT_AUDIT_STATUSES = frozenset(
    {"completed", "support_contract_not_selected"}
)

FrozenCandidateLoader = Callable[..., Any]
SupportAssessorBuilder = Callable[[Any], Callable[..., Mapping[str, Any]]]
StageARunner = Callable[..., Mapping[str, Any]]


class PrimitiveScopedSupportBindingError(ValueError):
    """Raised when immutable support evidence cannot safely bind to Stage A."""


def run_primitive_scoped_stage_a_support_audit(
    *,
    source_results_root: str | Path,
    stage_a_v1_output_root: str | Path,
    support_audit_output_root: str | Path,
    dig_training_config_path: str | Path,
    return_training_config_path: str | Path,
    output_root: str | Path,
    device: str = "cuda",
    policy_factory_builder: Any | None = None,
    action_std_by_primitive: Mapping[str, np.ndarray] | None = None,
    frozen_candidate_loader: FrozenCandidateLoader | None = None,
    support_assessor_builder: SupportAssessorBuilder | None = None,
    stage_a_runner: StageARunner | None = None,
    additional_source_lineage: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a new Stage-A artifact with Return v2 and Dig v1 support.

    A top-level support-audit status of ``support_contract_not_selected`` is
    allowed when (and only when) Return was selected independently.  That
    status means no single v2 rule covered every primitive; it does not revoke
    the frozen Return selection.  The delegated Stage-A runner remains the
    sole writer and retains its original no-overwrite behavior.
    """

    destination = Path(output_root).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"Stage-A support-contract output already exists: {destination}")
    source_root = Path(source_results_root).expanduser().resolve(strict=True)
    stage_root = Path(stage_a_v1_output_root).expanduser().resolve(strict=True)
    support_root = Path(support_audit_output_root).expanduser().resolve(strict=True)
    _require_distinct_output_root(
        destination=destination,
        source_root=source_root,
        stage_root=stage_root,
        support_root=support_root,
    )
    source_paths = _source_paths(source_root)
    stage_paths = _stage_a_paths(stage_root)
    support_paths = _support_audit_paths(support_root)
    dig_config = Path(dig_training_config_path).expanduser().resolve(strict=True)
    return_config = Path(return_training_config_path).expanduser().resolve(strict=True)

    stage_manifest = _load_json_mapping(stage_paths["manifest"])
    _validate_stage_a_v1_manifest(stage_manifest, source_root=source_root, source_paths=source_paths)
    support_manifest = _load_json_mapping(support_paths["manifest"])
    selected_return_candidate = _validate_support_audit_manifest(
        support_manifest,
        source_root=source_root,
        source_paths=source_paths,
        stage_paths=stage_paths,
        dig_config=dig_config,
        return_config=return_config,
    )

    loader = frozen_candidate_loader or load_frozen_selected_support_candidate
    candidate = loader(
        candidates_json_path=support_paths["candidates"],
        primitive="return",
        candidate_id=selected_return_candidate,
    )
    candidate_id = _candidate_id(candidate)
    if candidate_id != selected_return_candidate:
        raise PrimitiveScopedSupportBindingError(
            "frozen Return candidate id disagrees with support-audit selection"
        )
    assessor_builder = support_assessor_builder or build_frozen_candidate_support_assessor
    return_assessor = assessor_builder(candidate)
    if not callable(return_assessor):
        raise PrimitiveScopedSupportBindingError(
            "frozen Return support assessor builder must return a callable"
        )
    return_lineage = {
        "support_contract_version": SUPPORT_CONTRACT_VERSION,
        "candidate_id": candidate_id,
        "support_audit_status": str(support_manifest["status"]),
        "support_audit_manifest": _source_record(support_paths["manifest"]),
        "support_audit_candidates": _source_record(support_paths["candidates"]),
    }

    runner = stage_a_runner or run_act_goal_condition_sensitivity_audit
    runner_kwargs: dict[str, Any] = {
        "source_results_root": source_root,
        "dig_training_config_path": dig_config,
        "return_training_config_path": return_config,
        "output_root": destination,
        "device": str(device),
        "policy_factory_builder": policy_factory_builder,
        "action_std_by_primitive": action_std_by_primitive,
        "support_assessors_by_primitive": {"return": return_assessor},
        "support_lineage_by_primitive": {"return": return_lineage},
    }
    if additional_source_lineage is not None:
        if not isinstance(additional_source_lineage, Mapping) or not additional_source_lineage:
            raise PrimitiveScopedSupportBindingError(
                "additional_source_lineage must be a non-empty mapping"
            )
        runner_kwargs["additional_source_lineage"] = dict(additional_source_lineage)
    runner_result = runner(
        **runner_kwargs,
    )
    if not isinstance(runner_result, Mapping):
        raise PrimitiveScopedSupportBindingError("Stage-A runner must return a mapping")
    return {
        **dict(runner_result),
        "primitive_scoped_support_binding": {
            "dig": {
                "support_contract_version": "support_contract_v1",
                "candidate_id": "axis_p01_p99_v1",
                "binding": "default_stage_a_runner_support",
            },
            "return": return_lineage,
        },
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


def _stage_a_paths(stage_root: Path) -> dict[str, Path]:
    paths = {
        "manifest": stage_root / "manifest.json",
        "baseline": stage_root / "baseline.json",
        "dig": stage_root / "dig.json",
        "return": stage_root / "return.json",
    }
    _require_files(paths, label="Stage-A v1 evidence")
    return paths


def _support_audit_paths(support_root: Path) -> dict[str, Path]:
    paths = {
        "manifest": support_root / "manifest.json",
        "candidates": support_root / "candidates.json",
    }
    _require_files(paths, label="support-contract evidence")
    return paths


def _validate_stage_a_v1_manifest(
    manifest: Mapping[str, Any],
    *,
    source_root: Path,
    source_paths: Mapping[str, Path],
) -> None:
    if manifest.get("schema") != ACT_GOAL_CONDITION_SENSITIVITY_MANIFEST_SCHEMA:
        raise PrimitiveScopedSupportBindingError("Stage-A v1 manifest schema mismatch")
    if manifest.get("status") != "completed":
        raise PrimitiveScopedSupportBindingError("Stage-A v1 manifest is not completed")
    _validate_evidence_boundary(manifest, label="Stage-A v1 manifest")
    lineage = _required_mapping(manifest.get("source_lineage"), "Stage-A v1 source lineage")
    _verify_source_root(lineage, source_root=source_root, label="Stage-A v1")
    for key, path in source_paths.items():
        _verify_source_record(lineage.get(key), path=path, label=f"Stage-A v1 {key}")


def _validate_support_audit_manifest(
    manifest: Mapping[str, Any],
    *,
    source_root: Path,
    source_paths: Mapping[str, Path],
    stage_paths: Mapping[str, Path],
    dig_config: Path,
    return_config: Path,
) -> str:
    if manifest.get("schema") != SUPPORT_AUDIT_MANIFEST_SCHEMA:
        raise PrimitiveScopedSupportBindingError("support-audit manifest schema mismatch")
    if manifest.get("support_contract_version") != SUPPORT_CONTRACT_VERSION:
        raise PrimitiveScopedSupportBindingError("support-audit contract version mismatch")
    status = str(manifest.get("status", ""))
    if status not in _ALLOWED_SUPPORT_AUDIT_STATUSES:
        raise PrimitiveScopedSupportBindingError(
            f"support-audit status {status!r} cannot bind a Stage-A replay"
        )
    _validate_evidence_boundary(manifest, label="support-audit manifest")
    if manifest.get("target_rollout_used_for_selection") is not False:
        raise PrimitiveScopedSupportBindingError(
            "support-audit manifest permits target rollout in candidate selection"
        )
    selected = _required_mapping(
        manifest.get("selected_candidate_by_primitive"),
        "support-audit selected candidates",
    )
    selection_status = _required_mapping(
        manifest.get("selection_status_by_primitive"),
        "support-audit selection status",
    )
    raw_return_candidate = selected.get("return")
    return_candidate = (
        "" if raw_return_candidate is None else str(raw_return_candidate).strip()
    )
    if not return_candidate or selection_status.get("return") != "selected":
        raise PrimitiveScopedSupportBindingError(
            "support-audit has no independently selected Return candidate"
        )
    lineage = _required_mapping(manifest.get("source_lineage"), "support-audit source lineage")
    _verify_source_root(lineage, source_root=source_root, label="support-audit")
    for key, path in source_paths.items():
        _verify_source_record(lineage.get(key), path=path, label=f"support-audit {key}")
    for key, path in stage_paths.items():
        _verify_source_record(
            lineage.get(f"stage_a_{key}"),
            path=path,
            label=f"support-audit stage_a_{key}",
        )
    _verify_source_record(
        lineage.get("dig_training_config"),
        path=dig_config,
        label="support-audit dig_training_config",
    )
    _verify_source_record(
        lineage.get("return_training_config"),
        path=return_config,
        label="support-audit return_training_config",
    )
    return return_candidate


def _validate_evidence_boundary(manifest: Mapping[str, Any], *, label: str) -> None:
    if manifest.get("evidence_kind") != EVIDENCE_KIND:
        raise PrimitiveScopedSupportBindingError(f"{label} evidence kind mismatch")
    if manifest.get("diagnostic_only") is not True:
        raise PrimitiveScopedSupportBindingError(f"{label} is not diagnostic-only")
    if manifest.get("promotion_eligible") is not False:
        raise PrimitiveScopedSupportBindingError(f"{label} is promotion-eligible")
    if manifest.get("closed_loop_claim") is not False:
        raise PrimitiveScopedSupportBindingError(f"{label} has a closed-loop claim")


def _verify_source_root(
    lineage: Mapping[str, Any],
    *,
    source_root: Path,
    label: str,
) -> None:
    raw = lineage.get("source_results_root")
    if raw is None:
        raise PrimitiveScopedSupportBindingError(f"{label} lacks source_results_root")
    try:
        recorded = Path(str(raw)).expanduser().resolve(strict=True)
    except OSError as exc:
        raise PrimitiveScopedSupportBindingError(
            f"{label} source_results_root is not readable"
        ) from exc
    if recorded != source_root:
        raise PrimitiveScopedSupportBindingError(
            f"{label} source_results_root does not match requested source"
        )


def _verify_source_record(raw: Any, *, path: Path, label: str) -> None:
    record = _required_mapping(raw, f"{label} lineage record")
    recorded_sha = str(record.get("sha256", "")).strip()
    if recorded_sha != _sha256(path):
        raise PrimitiveScopedSupportBindingError(f"{label} SHA mismatch")
    recorded_path = record.get("path")
    if recorded_path is None:
        raise PrimitiveScopedSupportBindingError(f"{label} lineage record lacks path")
    try:
        resolved = Path(str(recorded_path)).expanduser().resolve(strict=True)
    except OSError as exc:
        raise PrimitiveScopedSupportBindingError(f"{label} lineage path is not readable") from exc
    if resolved != path:
        raise PrimitiveScopedSupportBindingError(f"{label} lineage path mismatch")


def _require_distinct_output_root(
    *,
    destination: Path,
    source_root: Path,
    stage_root: Path,
    support_root: Path,
) -> None:
    for label, immutable_root in (
        ("source results", source_root),
        ("Stage-A v1 evidence", stage_root),
        ("support-contract evidence", support_root),
    ):
        if destination == immutable_root or _is_relative_to(destination, immutable_root):
            raise PrimitiveScopedSupportBindingError(
                f"output_root must be distinct from {label}"
            )


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _candidate_id(candidate: Any) -> str:
    if isinstance(candidate, Mapping):
        value = candidate.get("candidate_id")
    else:
        value = getattr(candidate, "candidate_id", None)
    return "" if value is None else str(value).strip()


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


def _require_files(paths: Mapping[str, Path], *, label: str) -> None:
    missing = [f"{name}={path}" for name, path in paths.items() if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"{label} missing required files: {', '.join(missing)}")


def _load_json_mapping(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PrimitiveScopedSupportBindingError(
            f"{path} is not valid JSON"
        ) from exc
    return _required_mapping(payload, str(path))


def _required_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise PrimitiveScopedSupportBindingError(f"{label} must be a mapping")
    return dict(value)


__all__ = [
    "PrimitiveScopedSupportBindingError",
    "run_primitive_scoped_stage_a_support_audit",
]
