"""Immutable parent, live runtime, and resume contracts for replay salvage."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import h5py

from testbed.data.terrain_replay_dataset import sha256_file
from testbed.eval.terrain_replay_relabel_stats import load_replay_diagnostic_summary
from testbed.eval.terrain_replay_run_contract import (
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_REPLAY_CONFIG,
    build_replay_preflight,
)
from testbed.eval.terrain_replay_salvage import (
    CORRECTED_MAX_ATTEMPTS,
    PARENT_SELECTED_EPISODE_IDS,
    SALVAGE_EPISODE_IDS,
    SALVAGE_RUN_CONTRACT_SCHEMA,
    STRICT_ATTEMPT_BUDGETS,
    STRICT_REPLAY_ORDER,
    validate_parent_salvage_inventory,
)
from testbed.eval.terrain_replay_selection import (
    CALIBRATED_MIXED_SELECTION_PROFILE,
    CORRECTED_PARTIAL_SALVAGE_EVIDENCE_PROFILE,
)

DEFAULT_PARENT_RUN_ROOT = DEFAULT_OUTPUT_ROOT
DEFAULT_SALVAGE_OUTPUT_ROOT = Path(f"{DEFAULT_OUTPUT_ROOT}_salvage_v1")


def build_salvage_preflight(
    *,
    replay_config: str | Path = DEFAULT_REPLAY_CONFIG,
    parent_root: str | Path = DEFAULT_PARENT_RUN_ROOT,
    verify_parent_checksums: bool = True,
) -> dict[str, Any]:
    """Validate live runtime, fixed sources, and the immutable parent 17 run."""

    config = Path(replay_config).expanduser().resolve(strict=True)
    parent = Path(parent_root).expanduser().resolve(strict=True)
    errors: list[str] = []
    if parent != DEFAULT_PARENT_RUN_ROOT.expanduser().resolve(strict=True):
        errors.append("parent_run_root_mismatch")
    base = build_replay_preflight(replay_config=config)
    errors.extend(str(value) for value in base.get("errors", ()))

    required = (
        "completion_report.json",
        "run_contract.json",
        "selected_manifest.jsonl",
        "calibrated_replay_selection.jsonl",
    )
    missing = [name for name in required if not (parent / name).is_file()]
    errors.extend(f"parent_artifact_missing:{name}" for name in missing)
    inventory: dict[str, Any] = {}
    parent_contract: dict[str, Any] = {}
    selected_manifest: list[dict[str, Any]] = []
    if not missing:
        try:
            inventory = validate_parent_salvage_inventory(
                _read_json(parent / "completion_report.json")
            )
            parent_contract = _read_json(parent / "run_contract.json")
            selected_manifest = _read_jsonl(parent / "selected_manifest.jsonl")
        except (OSError, ValueError, TypeError) as exc:
            errors.append(f"parent_artifact_invalid:{type(exc).__name__}:{exc}")

    selected_rows: list[dict[str, Any]] = []
    selected_ids: set[int] = set()
    for row in selected_manifest:
        try:
            episode_id = _episode_number(str(row["source_episode_id"]))
            path = Path(str(row["selected_hdf5_path"])).resolve(strict=True)
            path.relative_to((parent / "selected_full_hdf5").resolve(strict=True))
            if path.name != f"episode_{episode_id}.hdf5":
                raise ValueError("selected filename mismatch")
            snapshot = _hdf5_snapshot(
                path,
                include_sha256=bool(verify_parent_checksums),
            )
            expected_hash = str(row.get("sha256", ""))
            if verify_parent_checksums and snapshot["sha256"] != expected_hash:
                errors.append(f"parent_selected_checksum_mismatch:episode_{episode_id}")
            snapshot.update(
                {
                    "episode_id": episode_id,
                    "manifest_sha256": expected_hash,
                }
            )
            selected_rows.append(snapshot)
            selected_ids.add(episode_id)
        except (KeyError, OSError, ValueError) as exc:
            errors.append(f"parent_selected_invalid:{type(exc).__name__}:{exc}")
    if selected_ids != set(PARENT_SELECTED_EPISODE_IDS):
        errors.append("parent_selected_manifest_inventory_mismatch")
    parent_clean_ids = {
        _episode_number(path.stem)
        for path in (parent / "selected_replay_clean_vds").glob("episode_*.hdf5")
    }
    if parent_clean_ids != set(PARENT_SELECTED_EPISODE_IDS):
        errors.append("parent_clean_vds_inventory_mismatch")
    for episode_id in SALVAGE_EPISODE_IDS:
        attempts = sorted(
            (parent / "attempts" / f"episode_{episode_id}").glob(
                "attempt_*/attempt_result.json"
            )
        )
        if len(attempts) != 5:
            errors.append(f"parent_failure_attempt_count:episode_{episode_id}")

    runtime = dict(base.get("runtime_contract", {}) or {})
    parent_runtime = dict(parent_contract.get("runtime_contract", {}) or {})
    if parent_runtime and runtime != parent_runtime:
        errors.append("runtime_contract_changed_from_parent")
    parent_source_hashes = {
        str(key): str(value)
        for key, value in dict(
            parent_contract.get("calibrated_source_sha256", {}) or {}
        ).items()
    }
    current_source_hashes = {
        str(row["episode_id"]): str(row["sha256"])
        for row in base.get("source_files", ())
    }
    if parent_source_hashes and parent_source_hashes != current_source_hashes:
        errors.append("calibrated_source_hash_changed_from_parent")

    parent_artifacts = {
        name: {
            "path": str((parent / name).resolve()),
            "sha256": sha256_file(parent / name),
            "size_bytes": int((parent / name).stat().st_size),
            "mtime_ns": int((parent / name).stat().st_mtime_ns),
        }
        for name in required
        if (parent / name).is_file()
    }
    return {
        "schema": "terrain_replay_salvage_preflight_v1",
        "pass": not errors,
        "errors": list(dict.fromkeys(errors)),
        "base_replay_preflight": base,
        "parent_root": str(parent),
        "parent_inventory": inventory,
        "parent_artifacts": parent_artifacts,
        "parent_selected_files": selected_rows,
        "parent_selected_checksums_verified": bool(verify_parent_checksums),
        "runtime_contract": runtime,
        "source_files": list(base.get("source_files", ())),
        "disk": dict(base.get("disk", {}) or {}),
    }


def build_salvage_run_contract(
    *,
    output_root: Path,
    replay_config: Path,
    preflight: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the stable exact-resume contract without volatile disk fields."""

    return {
        "schema": SALVAGE_RUN_CONTRACT_SCHEMA,
        "output_root": str(output_root),
        "parent_root": str(preflight["parent_root"]),
        "parent_artifacts": dict(preflight.get("parent_artifacts", {}) or {}),
        "parent_selected_sha256": {
            str(row["episode_id"]): str(row.get("manifest_sha256", ""))
            for row in preflight.get("parent_selected_files", ())
        },
        "source_sha256": {
            str(row["episode_id"]): str(row["sha256"])
            for row in preflight.get("source_files", ())
        },
        "runtime_contract": dict(preflight.get("runtime_contract", {}) or {}),
        "replay_config": str(replay_config),
        "replay_config_sha256": sha256_file(replay_config),
        "selection_profile": CALIBRATED_MIXED_SELECTION_PROFILE,
        "strict_selection_policy": "first_passing_attempt_v1",
        "strict_episode_ids": list(SALVAGE_EPISODE_IDS),
        "strict_replay_order": list(STRICT_REPLAY_ORDER),
        "strict_attempt_budgets": {
            str(key): int(value) for key, value in STRICT_ATTEMPT_BUDGETS.items()
        },
        "corrected_max_attempts": CORRECTED_MAX_ATTEMPTS,
        "corrected_evidence_profile": CORRECTED_PARTIAL_SALVAGE_EVIDENCE_PROFILE,
        "corrected_realign_contract": {
            "axis": "all",
            "error_threshold": 0.04,
            "hold_steps": 3,
            "min_steps_between": 200,
            "burn_in_steps": 15,
            "max_count": 20,
        },
        "fixed_unity_steps_per_action": 1,
        "mask_intervals_skipped": False,
        "wall_clock_resampling": False,
        "strict_pose_realign": False,
        "source_identity_policy": "one_source_one_replay_identity",
        "gold_status": "not_gold",
    }


def build_existing_failure_diagnosis(
    parent_root: str | Path = DEFAULT_PARENT_RUN_ROOT,
) -> dict[str, Any]:
    """Summarize the existing 35 failed attempts without reconstructing HDF5."""

    parent = Path(parent_root).expanduser().resolve(strict=True)
    episodes: list[dict[str, Any]] = []
    for episode_id in SALVAGE_EPISODE_IDS:
        attempts: list[dict[str, Any]] = []
        episode_dir = parent / "attempts" / f"episode_{episode_id}"
        for result_path in sorted(episode_dir.glob("attempt_*/attempt_result.json")):
            result = _read_json(result_path)
            gate_path = Path(str(result.get("gate_path", "")))
            diagnostic_path = Path(str(result.get("diagnostic_path", "")))
            gate = _read_json(gate_path) if gate_path.is_file() else {}
            diagnostic = (
                load_replay_diagnostic_summary(diagnostic_path)
                if diagnostic_path.is_file()
                else {}
            )
            semantic = dict(gate.get("semantic_result", {}) or {})
            attempts.append(
                {
                    "attempt_id": str(result.get("attempt_id", result_path.parent.name)),
                    "process_returncode": result.get("process_returncode"),
                    "qpos_pre_contact_max_error": diagnostic.get(
                        "qpos_pre_contact_max_error_max"
                    ),
                    "qpos_max_error": diagnostic.get("qpos_max_error_max"),
                    "first_qualified_contact_step": diagnostic.get(
                        "first_qualified_contact_step"
                    ),
                    "final_bucket_mass_kg": _terminal_bucket_mass(diagnostic_path),
                    "final_removed_depth_grid_m": diagnostic.get(
                        "final_removed_depth_grid_m"
                    ),
                    "observed_cycle_count": semantic.get("observed_cycle_count"),
                    "cycle_completion_ratio": semantic.get("cycle_completion_ratio"),
                    "semantic_failed_checks": list(
                        semantic.get("failed_checks", ()) or ()
                    ),
                    "target_results": dict(semantic.get("target_results", {}) or {}),
                    "exception_count": diagnostic.get("exception_count"),
                    "pose_realign_count": diagnostic.get("pose_realign_count"),
                    "step_sequence_complete": diagnostic.get(
                        "step_sequence_complete"
                    ),
                }
            )
        episodes.append(
            {
                "source_episode_id": f"episode_{episode_id}",
                "attempt_count": len(attempts),
                "attempts": attempts,
            }
        )
    return {
        "schema": "terrain_replay_existing_failure_diagnosis_v1",
        "parent_root": str(parent),
        "episode_count": len(episodes),
        "attempt_count": sum(int(row["attempt_count"]) for row in episodes),
        "episodes": episodes,
    }


def verify_parent_after(preflight: Mapping[str, Any]) -> dict[str, Any]:
    """Recheck parent manifests and selected HDF5 stat/structure after salvage."""

    artifact_matches = True
    artifact_rows: dict[str, Any] = {}
    for name, before in dict(preflight["parent_artifacts"]).items():
        path = Path(str(before["path"])).resolve(strict=True)
        current = {
            "path": str(path),
            "size_bytes": int(path.stat().st_size),
            "mtime_ns": int(path.stat().st_mtime_ns),
            "sha256": sha256_file(path),
        }
        current["matches_before"] = all(
            current[key] == before[key]
            for key in ("size_bytes", "mtime_ns", "sha256")
        )
        artifact_matches &= bool(current["matches_before"])
        artifact_rows[name] = current
    selected_matches = True
    selected_rows: list[dict[str, Any]] = []
    for before in preflight.get("parent_selected_files", ()):
        path = Path(str(before["realpath"])).resolve(strict=True)
        current = _hdf5_snapshot(path, include_sha256=False)
        current["episode_id"] = int(before["episode_id"])
        current["matches_before"] = all(
            current[key] == before[key]
            for key in ("size_bytes", "mtime_ns", "datasets")
        )
        current["checksum_verified_before"] = bool(
            preflight.get("parent_selected_checksums_verified", False)
        )
        selected_matches &= bool(current["matches_before"])
        selected_rows.append(current)
    return {
        "schema": "terrain_replay_parent_immutability_after_v1",
        "matches_before": bool(artifact_matches and selected_matches),
        "artifact_matches": artifact_matches,
        "selected_hdf5_matches": selected_matches,
        "parent_artifacts": artifact_rows,
        "selected_files": selected_rows,
    }


def _hdf5_snapshot(path: Path, *, include_sha256: bool) -> dict[str, Any]:
    resolved = path.expanduser().resolve(strict=True)
    stat = resolved.stat()
    datasets: dict[str, Any] = {}
    with h5py.File(resolved, "r") as handle:

        def visitor(name: str, item: h5py.Group | h5py.Dataset) -> None:
            if isinstance(item, h5py.Dataset):
                datasets[name] = {
                    "shape": list(item.shape),
                    "dtype": str(item.dtype),
                    "is_virtual": bool(item.is_virtual),
                }

        handle.visititems(visitor)
    row = {
        "realpath": str(resolved),
        "size_bytes": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "datasets": datasets,
    }
    if include_sha256:
        row["sha256"] = sha256_file(resolved)
    return row


def _terminal_bucket_mass(path: Path) -> float | None:
    if not path.is_file():
        return None
    terminal: float | None = None
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("event") != "episode_end":
                continue
            state = dict(row.get("final_env_state", {}) or {})
            value = state.get("mass_in_bucket_kg")
            if value is not None:
                terminal = float(value)
    return terminal


def _episode_number(value: str) -> int:
    return int(str(value).rsplit("_", 1)[1])


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append(value)
    return rows


__all__ = [
    "DEFAULT_PARENT_RUN_ROOT",
    "DEFAULT_SALVAGE_OUTPUT_ROOT",
    "build_existing_failure_diagnosis",
    "build_salvage_preflight",
    "build_salvage_run_contract",
    "verify_parent_after",
]
