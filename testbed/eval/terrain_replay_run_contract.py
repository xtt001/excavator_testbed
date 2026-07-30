"""Immutable source, runtime, and resume contracts for terrain replay builds."""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import yaml

from testbed.backends.agx.protocol import (
    PRODUCTION_CONTROL_PROFILE,
    RECORDING_PRE_FIX_CONTROL_PROFILE,
)
from testbed.data.action_contract_calibration import (
    CURRENT_EQUIVALENT_ACTION_CONTRACT,
    DEFAULT_CALIBRATED_OUTPUT_ROOT,
    POST_REFERENCE_EPISODE_IDS,
    PRE_CALIBRATION_EPISODE_IDS,
)
from testbed.data.terrain_cycle_cleaning import APPROVED_TERRAIN_DATASET_ROOT
from testbed.data.terrain_replay_dataset import (
    REPLAY_CAMERA_NAMES,
    REPLAY_ENV_STATE_CONTRACT,
    REPLAY_ENV_STATE_DIM,
    REPLAY_PROTOCOL_VERSION,
    REPLAY_TERRAIN_STATE_CONTRACT,
    REPLAY_TERRAIN_VOLUME_SOURCE,
    sha256_file,
)
from testbed.eval.terrain_replay_selection import (
    CALIBRATED_MIXED_SELECTION_PROFILE,
)

RUN_CONTRACT_SCHEMA = "terrain_replay_selected_dataset_run_contract_v3"
MAX_ATTEMPTS = 5
SMOKE_EPISODE_IDS = (28, 1, 19)
HIGH_RISK_EPISODE_IDS = (9, 16, 20)
EXPECTED_VALID_ACTION_STEP_COUNT = 409_692
CALIBRATED_SOURCE_ROOT = DEFAULT_CALIBRATED_OUTPUT_ROOT / "mixed_current_equivalent_vds"
CLEAN_DATASET_ROOT = APPROVED_TERRAIN_DATASET_ROOT.with_name(
    f"{APPROVED_TERRAIN_DATASET_ROOT.name}_cycle_clean_v1"
)
DEFAULT_OUTPUT_ROOT = APPROVED_TERRAIN_DATASET_ROOT.with_name(
    f"{APPROVED_TERRAIN_DATASET_ROOT.name}_cycle_action_calibrated_"
    "replay_selected_control_compatible_v2"
)
DEFAULT_REPLAY_CONFIG = (
    Path(__file__).resolve().parents[1]
    / "configs"
    / "teleop_yulong_v2_2_pro_full_task_four_camera_jpeg.yaml"
)


class HardReplayContractError(RuntimeError):
    """A global protocol/data contract failed and the batch must stop."""


def replay_step_id_semantics(*, corrected: bool) -> str:
    """Name the persisted replay step-id contract.

    A pose-realign RPC can advance the backend response id without consuming a
    source action, and the immediately following action response can repeat that
    id.  Corrected replay therefore persists the causal source-action index as
    ``timestamps/step_id``.  The raw backend before/after ids remain available
    in replay diagnostics.
    """

    return (
        "causal_source_action_index_v1"
        if bool(corrected)
        else "backend_step_id_v1"
    )


def recorded_replay_step_id(
    *,
    record_step_index: int,
    backend_step_id: Any,
    corrected: bool,
) -> int:
    """Resolve one persisted step id without hiding corrected-replay actions."""

    causal_index = int(record_step_index)
    if causal_index < 0:
        raise ValueError("record_step_index must be nonnegative.")
    if bool(corrected) or backend_step_id is None:
        return causal_index
    return int(backend_step_id)


def ordered_replay_episode_ids() -> tuple[int, ...]:
    """Return the fixed smoke -> post -> clean pre -> high-risk order."""

    smoke = list(SMOKE_EPISODE_IDS)
    remaining_post = [
        value for value in POST_REFERENCE_EPISODE_IDS if value not in set(smoke)
    ]
    ordinary_pre = [
        value
        for value in PRE_CALIBRATION_EPISODE_IDS
        if value not in set(smoke) and value not in set(HIGH_RISK_EPISODE_IDS)
    ]
    ordered = (*smoke, *remaining_post, *ordinary_pre, *HIGH_RISK_EPISODE_IDS)
    expected = set((*PRE_CALIBRATION_EPISODE_IDS, *POST_REFERENCE_EPISODE_IDS))
    if len(ordered) != len(expected) or set(ordered) != expected:
        raise AssertionError(
            "Fixed replay ordering does not match the 24-source inventory."
        )
    return tuple(int(value) for value in ordered)


def replay_control_profile_for_episode(episode_id: int) -> str:
    """Route each fixed source to its recording-era or production control law."""

    value = int(episode_id)
    if value in set(PRE_CALIBRATION_EPISODE_IDS):
        return RECORDING_PRE_FIX_CONTROL_PROFILE
    if value in set(POST_REFERENCE_EPISODE_IDS):
        return PRODUCTION_CONTROL_PROFILE
    raise ValueError(
        f"Episode {value} is outside the fixed 24-source inventory."
    )


def initialize_run_root(
    *,
    output_root: str | Path,
    contract: Mapping[str, Any],
    resume: bool,
) -> dict[str, Any]:
    """Create a no-overwrite run root or verify an exact resumable contract."""

    root = Path(output_root).expanduser()
    contract_path = root / "run_contract.json"
    normalized = _json_roundtrip(contract)
    if root.exists():
        if not resume:
            raise FileExistsError(
                f"Output root {root} already exists; no-overwrite is mandatory."
            )
        if not contract_path.is_file():
            raise ValueError(f"Resume root has no run contract: {contract_path}")
        stored = json.loads(contract_path.read_text(encoding="utf-8"))
        if stored != normalized:
            raise ValueError("Resume run contract mismatch; refusing mixed lineage.")
        return {"output_root": str(root.resolve()), "resumed": True}

    if resume:
        raise FileNotFoundError(f"Resume output root does not exist: {root}")
    root.mkdir(parents=True, exist_ok=False)
    for name in ("attempts", "selected_full_hdf5", "training_configs"):
        (root / name).mkdir(exist_ok=False)
    contract_path.write_text(
        json.dumps(normalized, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return {"output_root": str(root.resolve()), "resumed": False}


def build_replay_preflight(*, replay_config: str | Path) -> dict[str, Any]:
    """Validate fixed sources, 89D live runtime, lineage, and disk budget."""

    config_path = Path(replay_config).expanduser().resolve(strict=True)
    errors: list[str] = []
    expected_ids = set((*PRE_CALIBRATION_EPISODE_IDS, *POST_REFERENCE_EPISODE_IDS))
    discovered = {
        _episode_id(path): path.resolve()
        for path in CALIBRATED_SOURCE_ROOT.glob("episode_*.hdf5")
    }
    if set(discovered) != expected_ids:
        errors.append("calibrated_episode_inventory_mismatch")
    valid_action_steps = 0
    total_action_steps = 0
    source_rows: list[dict[str, Any]] = []
    for episode_id in sorted(expected_ids):
        path = discovered.get(episode_id)
        if path is None:
            continue
        try:
            with h5py.File(path, "r") as handle:
                action = handle["action"]
                mask = np.asarray(
                    handle["v2/step/action_loss_mask"][()], dtype=np.uint8
                ).reshape(-1)
                metadata = handle["metadata"].attrs
                if action.shape != (len(mask), 4):
                    errors.append(f"episode_{episode_id}:action_or_mask_shape")
                if _text(metadata.get("action_contract", "")) != (
                    CURRENT_EQUIVALENT_ACTION_CONTRACT
                ):
                    errors.append(f"episode_{episode_id}:action_contract")
                _require_lineage_path(
                    metadata.get("raw_source_realpath", ""),
                    root=APPROVED_TERRAIN_DATASET_ROOT,
                    errors=errors,
                    label=f"episode_{episode_id}:raw_lineage",
                )
                _require_lineage_path(
                    metadata.get("vds_source_abs_path", ""),
                    root=CLEAN_DATASET_ROOT,
                    errors=errors,
                    label=f"episode_{episode_id}:clean_lineage",
                )
                valid_action_steps += int(np.count_nonzero(mask))
                total_action_steps += int(action.shape[0])
                source_rows.append(
                    {
                        "episode_id": episode_id,
                        "path": str(path),
                        "sha256": sha256_file(path),
                        "action_steps": int(action.shape[0]),
                        "valid_action_steps": int(np.count_nonzero(mask)),
                    }
                )
        except (KeyError, OSError, ValueError) as exc:
            errors.append(f"episode_{episode_id}:hdf5:{type(exc).__name__}")
    if valid_action_steps != EXPECTED_VALID_ACTION_STEP_COUNT:
        errors.append("valid_action_step_count_mismatch")

    runtime: dict[str, Any] = {}
    try:
        config_payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        agx = dict(config_payload.get("agx", {}) or {})
        from testbed.backends.agx.protocol import AgxSimClient

        with AgxSimClient(
            host=str(agx.get("host", "127.0.0.1")),
            port=int(agx.get("port", 5057)),
            timeout_s=float(agx.get("timeout", 10.0)),
        ) as client:
            info = client.get_info()
        runtime = {
            "protocol_version": info.protocol_version,
            "env_state_dim": len(info.env_state_order),
            "env_state_contract_version": info.env_state_contract_version,
            "runtime_build_id": info.runtime_build_id,
            "terrain_state_contract_version": info.terrain_state_contract_version,
            "terrain_volume_source": info.terrain_volume_source,
            "camera_names": list(info.camera_names),
            "action_order": list(info.action_order),
            "control_hz": float(info.control_hz),
        }
        expected_runtime = {
            "protocol_version": REPLAY_PROTOCOL_VERSION,
            "env_state_dim": REPLAY_ENV_STATE_DIM,
            "env_state_contract_version": REPLAY_ENV_STATE_CONTRACT,
            "terrain_state_contract_version": REPLAY_TERRAIN_STATE_CONTRACT,
            "terrain_volume_source": REPLAY_TERRAIN_VOLUME_SOURCE,
            "camera_names": list(REPLAY_CAMERA_NAMES),
        }
        for key, expected in expected_runtime.items():
            if runtime.get(key) != expected:
                errors.append(f"runtime_contract_mismatch:{key}")
        if not str(runtime.get("runtime_build_id", "")).strip():
            errors.append("runtime_build_id_missing")
    except Exception as exc:
        errors.append(f"unity_get_info_failed:{type(exc).__name__}:{exc}")

    disk = shutil.disk_usage(DEFAULT_OUTPUT_ROOT.parent)
    raw_sizes = []
    for row in source_rows:
        with h5py.File(row["path"], "r") as handle:
            raw_path = Path(_text(handle["metadata"].attrs["raw_source_realpath"]))
        raw_sizes.append(int(raw_path.stat().st_size))
    estimated_selected_bytes = int(sum(raw_sizes))
    required_free_bytes = (
        estimated_selected_bytes + max(raw_sizes, default=0) + 10 * 2**30
    )
    if int(disk.free) < required_free_bytes:
        errors.append("insufficient_disk_space")
    return {
        "schema": "terrain_replay_selected_preflight_v1",
        "pass": not errors,
        "errors": errors,
        "calibrated_source_root": str(CALIBRATED_SOURCE_ROOT),
        "episode_count": len(source_rows),
        "total_action_step_count": total_action_steps,
        "valid_action_step_count": valid_action_steps,
        "expected_valid_action_step_count": EXPECTED_VALID_ACTION_STEP_COUNT,
        "source_files": source_rows,
        "runtime_contract": runtime,
        "disk": {
            "free_bytes": int(disk.free),
            "estimated_selected_bytes": estimated_selected_bytes,
            "required_free_bytes": required_free_bytes,
        },
    }


def build_run_contract(
    *,
    output_root: Path,
    replay_config: Path,
    preflight: Mapping[str, Any],
    max_attempts: int,
    selection_policy: str,
) -> dict[str, Any]:
    """Build the exact resume contract for one fixed replay run."""

    return {
        "schema": RUN_CONTRACT_SCHEMA,
        "output_root": str(output_root),
        "selection_profile": CALIBRATED_MIXED_SELECTION_PROFILE,
        "selection_policy": str(selection_policy),
        "max_attempts": int(max_attempts),
        "source_episode_ids": list(ordered_replay_episode_ids()),
        "control_compatibility_routing": {
            f"episode_{episode_id}": replay_control_profile_for_episode(episode_id)
            for episode_id in ordered_replay_episode_ids()
        },
        "calibrated_source_root": str(CALIBRATED_SOURCE_ROOT.resolve()),
        "clean_root": str(CLEAN_DATASET_ROOT.resolve()),
        "raw_root": str(APPROVED_TERRAIN_DATASET_ROOT.resolve()),
        "replay_config": str(replay_config),
        "replay_config_sha256": sha256_file(replay_config),
        "cycle_eligibility_sha256": sha256_file(
            CLEAN_DATASET_ROOT / "cycle_eligibility.jsonl"
        ),
        "calibration_manifest_sha256": sha256_file(
            DEFAULT_CALIBRATED_OUTPUT_ROOT / "calibration_manifest.json"
        ),
        "calibrated_source_sha256": {
            str(row["episode_id"]): str(row["sha256"])
            for row in preflight.get("source_files", [])
        },
        "runtime_contract": dict(preflight.get("runtime_contract", {})),
        "fixed_unity_steps_per_action": 1,
        "mask_intervals_skipped": False,
        "pose_realign": False,
        "wall_clock_resampling": False,
        "post_tail_steps": 0,
        "repeatability_status": "not_assessed_single_attempt",
        "gold_status": "not_gold",
    }


def all_source_snapshots() -> dict[str, Any]:
    """Capture size, mtime, and HDF5 structure for every protected source."""

    raw_paths = [
        APPROVED_TERRAIN_DATASET_ROOT / f"episode_{episode_id}.hdf5"
        for episode_id in range(36)
    ]
    calibrated_paths = [
        CALIBRATED_SOURCE_ROOT / f"episode_{episode_id}.hdf5"
        for episode_id in sorted(ordered_replay_episode_ids())
    ]
    clean_paths: set[Path] = set()
    for path in calibrated_paths:
        with h5py.File(path, "r") as handle:
            clean_paths.add(
                Path(_text(handle["metadata"].attrs["vds_source_abs_path"]))
                .expanduser()
                .resolve(strict=True)
            )
    return {
        "schema": "terrain_replay_source_immutability_snapshot_v1",
        "raw_36": [_hdf5_snapshot(path) for path in raw_paths],
        "clean_24": [_hdf5_snapshot(path) for path in sorted(clean_paths)],
        "calibrated_24": [_hdf5_snapshot(path) for path in calibrated_paths],
    }


def _hdf5_snapshot(path: Path) -> dict[str, Any]:
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
    return {
        "realpath": str(resolved),
        "size_bytes": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "datasets": datasets,
    }


def _require_lineage_path(
    value: Any, *, root: Path, errors: list[str], label: str
) -> None:
    try:
        path = Path(_text(value)).expanduser().resolve(strict=True)
        path.relative_to(root.resolve())
    except (FileNotFoundError, ValueError):
        errors.append(label)


def _episode_id(path: Path) -> int:
    return int(path.stem.rsplit("_", 1)[1])


def _text(value: Any) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def _json_roundtrip(value: Mapping[str, Any]) -> dict[str, Any]:
    payload = json.dumps(dict(value), sort_keys=True, allow_nan=False)
    result = json.loads(payload)
    if not isinstance(result, dict):
        raise ValueError("Run contract must be a JSON object.")
    return result


__all__ = [
    "CALIBRATED_SOURCE_ROOT",
    "CLEAN_DATASET_ROOT",
    "DEFAULT_OUTPUT_ROOT",
    "DEFAULT_REPLAY_CONFIG",
    "EXPECTED_VALID_ACTION_STEP_COUNT",
    "HIGH_RISK_EPISODE_IDS",
    "HardReplayContractError",
    "MAX_ATTEMPTS",
    "RUN_CONTRACT_SCHEMA",
    "SMOKE_EPISODE_IDS",
    "all_source_snapshots",
    "build_replay_preflight",
    "build_run_contract",
    "initialize_run_root",
    "ordered_replay_episode_ids",
    "recorded_replay_step_id",
    "replay_step_id_semantics",
]
