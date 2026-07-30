"""Create the immutable input specification for wall-contact evidence."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from testbed.eval.wall_contact_artifact_io import (
    artifact_ref,
    artifact_refs_aggregate_sha256,
    load_json,
    locked_ref,
    mapping,
    required_file,
    sha256_file,
    sha256_value,
    write_json_x,
)

CONTACT_LINEAGE_REQUIRED_BASENAMES = (
    "WorktoolWallContactDetail.cs",
    "BucketContactForceMonitor.cs",
    "AgxSimStepAckServer.cs",
    "ExpertWorktoolContactSweep.cs",
    "CodexExpertWorktoolContactSweepUtility.cs",
)

PYTHON_LINEAGE_REQUIRED_RELATIVE_PATHS = (
    "testbed/planner/box_emptying/wall_contact_detail.py",
    "testbed/planner/box_emptying/safety_contracts.py",
    "testbed/planner/box_emptying/safety_interlock.py",
    "testbed/planner/box_emptying/contact_ownership.py",
    "testbed/planner/box_emptying/safety_effects.py",
    "testbed/planner/box_emptying/runtime_monitor.py",
    "testbed/planner/box_emptying/stop_conditions.py",
    "testbed/planner/primitive/config/adapter.py",
    "testbed/policies/hybrid/box_emptying_runtime.py",
    "testbed/policies/hybrid/primitive_planner.py",
    "testbed/eval/suite.py",
    "testbed/eval/expert_wall_contact_replay.py",
    "testbed/cli/expert_wall_contact_replay.py",
    "testbed/eval/wall_contact_ab_runner.py",
    "testbed/eval/wall_contact_ab_collection.py",
    "testbed/cli/wall_contact_ab_runner.py",
    "testbed/eval/wall_contact_artifact_io.py",
    "testbed/eval/wall_contact_config_contracts.py",
    "testbed/eval/wall_contact_evidence_contracts.py",
    "testbed/eval/wall_contact_evidence_reporting.py",
    "testbed/eval/wall_contact_experiment_contracts.py",
    "testbed/eval/wall_contact_ab_lineage.py",
    "testbed/eval/wall_contact_semantics_experiment.py",
    "testbed/eval/wall_contact_source_spec.py",
    "testbed/cli/wall_contact_semantics_experiment.py",
)


class WallContactSourceSpecError(RuntimeError):
    """Raised when source artifacts cannot form a trustworthy lock."""


def build_source_spec(
    *,
    full_source_dir: str | Path,
    split_path: str | Path,
    dig_primitives_dir: str | Path,
    execution_library_path: str | Path,
    pose_library_path: str | Path,
    legacy_sweep_path: str | Path,
    unity_repo_root: str | Path,
    contact_monitor_code_paths: Sequence[str | Path],
    frozen_target_handoff_path: str | Path,
    expected_reset_state_path: str | Path,
    output_path: str | Path,
    source_episode_ids: Sequence[int],
    schema: str,
) -> dict[str, Any]:
    """Hash every external input and write one create-new source spec."""

    full_root = Path(full_source_dir).expanduser().resolve()
    dig_root = Path(dig_primitives_dir).expanduser().resolve()
    unity_root = Path(unity_repo_root).expanduser().resolve()
    for label, root in (
        ("full_source_dir", full_root),
        ("dig_primitives_dir", dig_root),
        ("unity_repo_root", unity_root),
    ):
        if not root.is_dir():
            raise FileNotFoundError(f"{label}_missing:{root}")

    legacy_path = required_file(legacy_sweep_path, "legacy_sweep")
    legacy = load_json(legacy_path)
    source_lock = mapping(
        legacy.get("source_lock"),
        "legacy_sweep.source_lock",
    )
    scene_path = _unity_locked_file(
        unity_root,
        source_lock,
        path_key="scene_path",
        sha_key="scene_sha256",
        label="unity_scene",
    )
    _unity_locked_file(
        unity_root,
        source_lock,
        path_key="normalization_path",
        sha_key="normalization_sha256",
        label="unity_normalization",
    )
    contact_lineage_files = _build_contact_lineage_files(contact_monitor_code_paths)

    episode_refs: dict[str, dict[str, Any]] = {}
    for source_id in source_episode_ids:
        source_path = required_file(
            full_root / f"episode_{int(source_id)}.hdf5",
            f"source_episode_{int(source_id)}",
        )
        episode_refs[str(int(source_id))] = artifact_ref(source_path)

    spec = {
        "schema": schema,
        "diagnostic_only": True,
        "full_source_episodes": episode_refs,
        "split": artifact_ref(required_file(split_path, "split")),
        "dig_primitives_dir": str(dig_root),
        "execution_library": artifact_ref(
            required_file(execution_library_path, "execution_library")
        ),
        "pose_library": artifact_ref(required_file(pose_library_path, "pose_library")),
        "legacy_sweep": artifact_ref(legacy_path),
        "frozen_target_handoff": artifact_ref(
            required_file(
                frozen_target_handoff_path,
                "frozen_target_handoff",
            )
        ),
        "expected_reset_state": artifact_ref(
            required_file(expected_reset_state_path, "expected_reset_state")
        ),
        "unity": {
            "repo_root": str(unity_root),
            "scene_sha256": sha256_file(scene_path),
            "contact_lineage_files": contact_lineage_files,
            "contact_lineage_aggregate_sha256": (
                artifact_refs_aggregate_sha256(contact_lineage_files)
            ),
        },
        "python": build_python_source_lineage(),
    }
    write_json_x(Path(output_path).expanduser().resolve(), spec)
    return spec


def lock_contact_lineage(
    unity: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], str]:
    """Verify every sidecar/adapter source and its ordered aggregate."""

    raw = unity.get("contact_lineage_files")
    if not isinstance(raw, list):
        raise WallContactSourceSpecError("contact_lineage_files_invalid")
    references = [
        locked_ref(
            mapping(item, f"contact_lineage_file_{index}"),
            f"contact_lineage_file_{index}",
        )
        for index, item in enumerate(raw)
    ]
    _validate_contact_lineage_inventory(references)
    expected = sha256_value(
        unity.get("contact_lineage_aggregate_sha256"),
        "contact_lineage_aggregate_sha256",
    )
    actual = artifact_refs_aggregate_sha256(references)
    if actual != expected:
        raise WallContactSourceSpecError("contact_lineage_aggregate_sha256_drift")
    return references, actual


def build_python_source_lineage(
    *,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    """Hash the fixed Python execution/evidence chain for this stage."""

    root = (
        Path(repo_root).expanduser().resolve()
        if repo_root is not None
        else Path(__file__).resolve().parents[2]
    )
    references = []
    for relative in PYTHON_LINEAGE_REQUIRED_RELATIVE_PATHS:
        reference = artifact_ref(required_file(root / relative, relative))
        references.append({"relative_path": relative, **reference})
    return {
        "repo_root": str(root),
        "lineage_files": references,
        "lineage_aggregate_sha256": artifact_refs_aggregate_sha256(references),
    }


def lock_python_source_lineage(
    python: Mapping[str, Any],
    *,
    expected_repo_root: str | Path | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Revalidate the fixed Python source inventory and ordered aggregate."""

    expected_root = (
        Path(expected_repo_root).expanduser().resolve()
        if expected_repo_root is not None
        else Path(__file__).resolve().parents[2]
    )
    recorded_root = Path(str(python.get("repo_root", ""))).expanduser().resolve()
    if recorded_root != expected_root:
        raise WallContactSourceSpecError("python_lineage_repo_root_drift")
    raw = python.get("lineage_files")
    if not isinstance(raw, list):
        raise WallContactSourceSpecError("python_lineage_files_invalid")
    relative_paths = [str(item.get("relative_path", "")) for item in raw]
    if relative_paths != list(PYTHON_LINEAGE_REQUIRED_RELATIVE_PATHS):
        raise WallContactSourceSpecError("python_lineage_inventory_drift")
    references = []
    for index, item in enumerate(raw):
        relative = relative_paths[index]
        locked = locked_ref(
            mapping(item, f"python_lineage_file_{index}"),
            f"python_lineage_file_{index}",
        )
        if Path(locked["path"]) != expected_root / relative:
            raise WallContactSourceSpecError("python_lineage_path_drift")
        references.append({"relative_path": relative, **locked})
    expected = sha256_value(
        python.get("lineage_aggregate_sha256"),
        "python_lineage_aggregate_sha256",
    )
    actual = artifact_refs_aggregate_sha256(references)
    if actual != expected:
        raise WallContactSourceSpecError(
            "python_lineage_aggregate_sha256_drift"
        )
    return references, actual


def _build_contact_lineage_files(
    values: Sequence[str | Path],
) -> list[dict[str, Any]]:
    by_name: dict[str, Path] = {}
    for index, value in enumerate(values):
        path = required_file(value, f"contact_lineage_file_{index}")
        if path.name in by_name:
            raise WallContactSourceSpecError(
                f"contact_lineage_basename_duplicate:{path.name}"
            )
        by_name[path.name] = path
    missing = set(CONTACT_LINEAGE_REQUIRED_BASENAMES).difference(by_name)
    if missing:
        raise WallContactSourceSpecError(
            "contact_lineage_required_files_missing:" + ",".join(sorted(missing))
        )
    ordered_names = [
        *CONTACT_LINEAGE_REQUIRED_BASENAMES,
        *sorted(set(by_name).difference(CONTACT_LINEAGE_REQUIRED_BASENAMES)),
    ]
    return [artifact_ref(by_name[name]) for name in ordered_names]


def _validate_contact_lineage_inventory(
    references: Sequence[Mapping[str, Any]],
) -> None:
    names = [Path(str(item.get("path", ""))).name for item in references]
    required_prefix = list(CONTACT_LINEAGE_REQUIRED_BASENAMES)
    if (
        names[: len(required_prefix)] != required_prefix
        or names[len(required_prefix) :] != sorted(names[len(required_prefix) :])
        or len(names) != len(set(names))
    ):
        raise WallContactSourceSpecError("contact_lineage_order_invalid")


def _unity_locked_file(
    unity_root: Path,
    source_lock: Mapping[str, Any],
    *,
    path_key: str,
    sha_key: str,
    label: str,
) -> Path:
    relative = str(source_lock.get(path_key, "")).strip()
    if not relative:
        raise WallContactSourceSpecError(f"{label}_path_missing")
    path = required_file(unity_root / relative, label)
    expected_sha = sha256_value(source_lock.get(sha_key), sha_key)
    actual_sha = sha256_file(path)
    if actual_sha != expected_sha:
        raise WallContactSourceSpecError(
            f"{label}_sha256_drift:expected={expected_sha}:actual={actual_sha}"
        )
    return path


__all__ = [
    "CONTACT_LINEAGE_REQUIRED_BASENAMES",
    "PYTHON_LINEAGE_REQUIRED_RELATIVE_PATHS",
    "WallContactSourceSpecError",
    "build_python_source_lineage",
    "build_source_spec",
    "lock_contact_lineage",
    "lock_python_source_lineage",
]
