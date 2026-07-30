"""Artifact and execution-lineage integrity for wall-contact rollouts."""

from __future__ import annotations

import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from testbed.eval.wall_contact_artifact_io import (
    artifact_ref,
    sha256_file,
)
from testbed.eval.wall_contact_rollout_diagnostic import (
    WallContactRolloutDiagnosticError,
)

PRIMITIVES = ("dig", "carry", "dump", "return")
RUNTIME_CODE_PATHS = (
    "testbed/backends/agx/backend.py",
    "testbed/backends/agx/protocol.py",
    "testbed/data/schema.py",
    "testbed/planner/box_emptying/bottom_contact_detail.py",
    "testbed/planner/box_emptying/contact_ownership.py",
    "testbed/planner/box_emptying/runtime_monitor.py",
    "testbed/planner/box_emptying/wall_contact_detail.py",
    "testbed/planner/box_emptying/safety_contracts.py",
    "testbed/planner/box_emptying/safety_effects.py",
    "testbed/planner/box_emptying/safety_interlock.py",
    "testbed/planner/box_emptying/stop_conditions.py",
    "testbed/planner/primitive/config/adapter.py",
    "testbed/planner/primitive/execution/action_dispatch.py",
    "testbed/planner/primitive/execution/return_approach_control.py",
    "testbed/policies/act/adapter.py",
    "testbed/policies/hybrid/adapter.py",
    "testbed/policies/hybrid/box_emptying_runtime.py",
    "testbed/policies/hybrid/primitive_planner.py",
    "testbed/runtime/_eval.py",
    "testbed/cli/eval.py",
    "testbed/eval/suite.py",
    "testbed/eval/wall_contact_rollout_diagnostic.py",
    "testbed/eval/wall_contact_rollout_safety_evidence.py",
    "testbed/eval/wall_contact_rollout_integrity.py",
    "testbed/eval/unity_host_identity.py",
    "testbed/eval/wall_contact_rollout_probe.py",
    "testbed/cli/wall_contact_rollout_probe.py",
)


def lock_act_artifacts(
    *,
    eval_config: Mapping[str, Any],
    policy: Mapping[str, Any],
    repo_root: Path,
) -> dict[str, dict[str, dict[str, Any]]]:
    """Lock the checkpoint and normalization file actually used per skill."""

    checkpoints: dict[str, dict[str, Any]] = {}
    dataset_stats: dict[str, dict[str, Any]] = {}
    for primitive in PRIMITIVES:
        checkpoint_value = eval_config.get(
            f"{primitive}_ckpt_path"
        ) or policy.get(f"{primitive}_ckpt_path")
        ckpt_dir_value = eval_config.get(
            f"{primitive}_ckpt_dir"
        ) or policy.get(f"{primitive}_ckpt_dir")
        checkpoint_source = checkpoint_value or (
            Path(str(ckpt_dir_value)) / "policy_best.ckpt"
        )
        checkpoint = resolve_config_artifact(
            checkpoint_source,
            f"{primitive}_checkpoint",
            repo_root=repo_root,
        )
        stats_parent = (
            Path(str(ckpt_dir_value))
            if ckpt_dir_value
            else checkpoint.parent
        )
        stats_path = resolve_config_artifact(
            stats_parent / "dataset_stats.pkl",
            f"{primitive}_dataset_stats",
            repo_root=repo_root,
        )
        checkpoints[primitive] = artifact_ref(checkpoint)
        dataset_stats[primitive] = artifact_ref(stats_path)
    return {
        "checkpoints": checkpoints,
        "dataset_stats": dataset_stats,
    }


def runtime_code_refs(repo_root: Path) -> list[dict[str, Any]]:
    """Return ordered, exact references for code that can change ACT output."""

    return [
        artifact_ref((repo_root / relative).resolve())
        for relative in RUNTIME_CODE_PATHS
    ]


def validate_runtime_code_refs(
    value: Any,
    *,
    repo_root: Path,
) -> None:
    """Reject missing, reordered, substituted, or content-drifted code refs."""

    if not isinstance(value, list) or len(value) != len(RUNTIME_CODE_PATHS):
        raise WallContactRolloutDiagnosticError("runtime_code_lock_invalid")
    for index, (reference, relative) in enumerate(
        zip(value, RUNTIME_CODE_PATHS, strict=True)
    ):
        if verify_ref(reference, f"runtime_code_{index}") != (
            repo_root / relative
        ).resolve():
            raise WallContactRolloutDiagnosticError(
                "runtime_code_lock_invalid"
            )


def validate_execution_lineage(
    marker: Mapping[str, Any],
    execution: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    start_schema: str,
    execution_schema: str,
    attempt_id: str,
    seed: int,
) -> None:
    """Validate the manifest -> marker -> argv/log/execution evidence chain."""

    try:
        manifest_path = required_file(
            manifest.get("manifest_path"),
            "probe_manifest",
        )
        run_root = Path(str(manifest.get("run_root", ""))).resolve()
        marker_ref = artifact_ref(
            required_file(
                run_root / "attempt_started.json",
                "attempt_started",
            )
        )
        log_ref = artifact_ref(
            required_file(run_root / "eval_process.log", "process_log")
        )
        expected_marker = {
            "schema": start_schema,
            "attempt_id": attempt_id,
            "seed": seed,
            "retry_count": 0,
            "manifest": artifact_ref(manifest_path),
            "configured_argv": manifest.get("command_argv"),
            "executed_argv": runtime_command(manifest.get("command_argv")),
        }
        expected_execution = {
            "schema": execution_schema,
            "attempt_id": attempt_id,
            "seed": seed,
            "retry_count": 0,
            "attempt_started": marker_ref,
            "process_log": log_ref,
        }
        valid = all(
            marker.get(field) == expected
            for field, expected in expected_marker.items()
        ) and all(
            execution.get(field) == expected
            for field, expected in expected_execution.items()
        )
    except Exception as exc:
        raise WallContactRolloutDiagnosticError(
            "attempt_execution_lineage_invalid"
        ) from exc
    if not valid:
        raise WallContactRolloutDiagnosticError(
            "attempt_execution_lineage_invalid"
        )


def resolve_config_artifact(
    value: Any,
    label: str,
    *,
    repo_root: Path,
) -> Path:
    """Resolve an execution artifact using the live eval cwd rules."""

    raw = Path(str(value)).expanduser()
    candidates = [raw]
    if not raw.is_absolute():
        candidates = [repo_root / raw, Path.cwd() / raw]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(f"{label}_missing:{raw}")


def verify_ref(value: Any, label: str) -> Path:
    """Verify an exact path, SHA-256, and size reference."""

    record = _mapping(value, label)
    path = required_file(record.get("path"), label)
    expected_sha = str(record.get("sha256", "")).lower()
    expected_size = record.get("size_bytes")
    if (
        sha256_file(path) != expected_sha
        or not isinstance(expected_size, int)
        or path.stat().st_size != expected_size
    ):
        raise WallContactRolloutDiagnosticError(f"artifact_drift:{label}")
    return path


def runtime_command(value: Any) -> list[str]:
    """Resolve the configured Python executable without changing argv."""

    if (
        isinstance(value, (str, bytes))
        or not isinstance(value, Sequence)
        or not all(isinstance(item, str) for item in value)
    ):
        raise WallContactRolloutDiagnosticError("probe_command_invalid")
    command = list(value)
    if command and command[0] == "python":
        command[0] = sys.executable
    return command


def required_file(value: Any, label: str) -> Path:
    path = Path(str(value)).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{label}_missing:{path}")
    return path


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise WallContactRolloutDiagnosticError(
            f"{label}_must_be_mapping"
        )
    return value


__all__ = [
    "RUNTIME_CODE_PATHS",
    "lock_act_artifacts",
    "resolve_config_artifact",
    "runtime_code_refs",
    "runtime_command",
    "validate_execution_lineage",
    "validate_runtime_code_refs",
    "verify_ref",
]
