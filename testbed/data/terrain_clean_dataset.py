"""Immutable raw-to-clean VDS pipeline for the approved terrain batch.

The builder owns orchestration and audit artifacts.  Step/cycle decisions stay
in :mod:`testbed.data.terrain_cycle_cleaning`; existing label enrichers remain
the semantic sources of truth for V2.1, operator-first, and hindsight fields.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import h5py
import numpy as np
import yaml

from testbed.data.camera_images import (
    JPEG_ENCODING,
    camera_names_from_metadata,
    decode_jpeg_rgb,
)
from testbed.data.hdf5_io import read_episode
from testbed.data.hindsight_goal_v2_4 import build_hindsight_goal_dataset
from testbed.data.operator_first_v2_2 import build_operator_first_dataset
from testbed.data.schema import (
    DS_ACTION,
    DS_ENV_STATE,
    DS_QPOS,
    DS_QVEL,
    DS_STEP_ID,
    DS_STEP_NS,
    ENV_STATE_ORDER_V2_3,
    GRP_ENCODED_IMAGES,
)
from testbed.data.terrain_cycle_cleaning import (
    APPROVED_TERRAIN_DATASET_ROOT,
    CLEANING_SCHEMA,
    EXPECTED_TERRAIN_EPISODE_COUNT,
    EpisodeCleaningResult,
    TerrainCycleCleaningConfig,
    analyze_episode_cleaning,
    resolve_approved_episode_paths,
)
from testbed.data.v2_1 import label_episode_v2_1
from testbed.data.vds import STORAGE_MODE_VDS, write_lineage_json, write_vds_episode
from testbed.planner.boundary_detector import (
    QUALIFIED_DIG_START_MODE_CONTACT_DEPTH,
    QUALIFIED_DIG_START_MODES,
)


REQUIRED_CAMERA_NAMES = ("stick_up", "stick_down", "eye_left", "eye_right")
PIPELINE_VERSION = "terrain_clean_dataset_v1"
ACTION_LOSS_MASK_SCOPE = "loss_sampling_stats"
TRAINING_VIEW_SCHEMA = "terrain_clean_training_view_v1"

_LAYER_LABELS = "labels_v2_1_vds"
_LAYER_OPERATOR = "operator_first_vds"
_LAYER_HINDSIGHT = "hindsight_vds"
_VIEW_CLEAN_ALL = "clean_all_vds"
_VIEW_POST_FIX = "post_fix_default_vds"
_VIEW_PRE_FIX = "pre_fix_salvage_vds"


def build_terrain_clean_dataset(
    *,
    dataset_dir: str | Path,
    output_root: str | Path,
    label_config_path: str | Path | None = None,
    qualified_dig_start_mode: str = QUALIFIED_DIG_START_MODE_CONTACT_DEPTH,
    approved_root: str | Path = APPROVED_TERRAIN_DATASET_ROOT,
    expected_episode_count: int = EXPECTED_TERRAIN_EPISODE_COUNT,
    episode_ids: Iterable[int] | None = None,
    cleaning_config: TerrainCycleCleaningConfig | None = None,
    validate_jpeg_decode: bool = True,
) -> dict[str, Any]:
    """Build the fixed label -> operator -> hindsight -> clean VDS chain.

    ``approved_root`` and ``expected_episode_count`` are injectable only for
    isolated tests.  The CLI exposes neither and therefore remains hard-locked
    to the 2026-07-17 batch.
    """
    source_root = Path(dataset_dir).expanduser().resolve()
    source_paths = resolve_approved_episode_paths(
        source_root,
        approved_root=approved_root,
        expected_episode_count=int(expected_episode_count),
    )
    selected_ids = _resolve_episode_ids(
        episode_ids,
        expected_episode_count=int(expected_episode_count),
    )
    selected_paths = [source_paths[episode_id] for episode_id in selected_ids]

    output_root = Path(output_root).expanduser()
    if output_root.exists():
        raise FileExistsError(
            f"Output root {output_root} already exists; no-overwrite is mandatory."
        )
    output_root.mkdir(parents=True, exist_ok=False)

    label_root = output_root / _LAYER_LABELS
    operator_root = output_root / _LAYER_OPERATOR
    hindsight_root = output_root / _LAYER_HINDSIGHT
    clean_all_root = output_root / _VIEW_CLEAN_ALL
    post_fix_root = output_root / _VIEW_POST_FIX
    pre_fix_root = output_root / _VIEW_PRE_FIX
    for path in (clean_all_root, post_fix_root, pre_fix_root):
        path.mkdir(parents=True, exist_ok=False)

    source_before = [_source_snapshot(path) for path in selected_paths]
    source_manifest: dict[str, Any] = {
        "schema": "terrain_source_manifest_v1",
        "approved_source_root": str(source_root),
        "expected_episode_count": int(expected_episode_count),
        "processed_episode_ids": selected_ids,
        "episodes": source_before,
        "source_immutable_verified": False,
    }
    _write_json(output_root / "source_manifest.json", source_manifest)

    camera_audits: dict[int, dict[str, Any]] = {}
    for episode_id, source_path in zip(selected_ids, selected_paths, strict=True):
        camera_audits[episode_id] = audit_four_camera_jpeg_steps(
            source_path,
            decode_frames=bool(validate_jpeg_decode),
        )

    success_cfg, reward_cfg = _load_label_config(label_config_path)
    if qualified_dig_start_mode not in QUALIFIED_DIG_START_MODES:
        raise ValueError(
            f"Unsupported qualified dig-start mode {qualified_dig_start_mode!r}."
        )
    reward_cfg["qualified_dig_start_mode"] = qualified_dig_start_mode
    _build_label_layer(
        source_paths=selected_paths,
        output_dir=label_root,
        success_cfg=success_cfg,
        reward_cfg=reward_cfg,
        qualified_dig_start_mode=qualified_dig_start_mode,
        label_config_path=(
            None if label_config_path is None else Path(label_config_path).resolve()
        ),
    )
    build_operator_first_dataset(
        dataset_dir=label_root,
        output_dir=operator_root,
        overwrite=False,
        storage_mode=STORAGE_MODE_VDS,
    )
    build_hindsight_goal_dataset(
        dataset_dir=operator_root,
        output_dir=hindsight_root,
        overwrite=False,
        storage_mode=STORAGE_MODE_VDS,
    )

    all_windows: list[dict[str, Any]] = []
    all_cycles: list[dict[str, Any]] = []
    episode_reports: list[dict[str, Any]] = []
    diagnostic_episode_ids: list[int] = []
    for episode_id, raw_path in zip(selected_ids, selected_paths, strict=True):
        source_path = hindsight_root / raw_path.name
        episode = read_episode(source_path, load_images=False)
        v2 = dict(episode.get("v2") or {})
        v2_step = {
            str(key): np.asarray(value)
            for key, value in dict(v2.get("step", {}) or {}).items()
        }
        v2_cycle = {
            str(key): np.asarray(value)
            for key, value in dict(v2.get("cycle", {}) or {}).items()
        }
        camera_audit = camera_audits[episode_id]
        result = analyze_episode_cleaning(
            episode_id=episode_id,
            actions=np.asarray(episode["actions"], dtype=np.float32),
            qpos=np.asarray(episode["qpos"], dtype=np.float32),
            qvel=np.asarray(episode["qvel"], dtype=np.float32),
            step_ids=episode.get("step_ids"),
            step_ns=episode.get("step_ns"),
            v2_step=v2_step,
            v2_cycle=v2_cycle,
            camera_step_valid_mask=np.asarray(
                camera_audit["step_valid_mask"], dtype=np.uint8
            ),
            config=cleaning_config,
        )
        _set_raw_source_provenance(result, raw_path)
        all_windows.extend(result.windows)
        all_cycles.extend(result.cycles)
        episode_reports.append(
            {
                "episode_id": episode_id,
                "controller_epoch": result.controller_epoch,
                "episode_role": result.episode_role,
                "diagnostics": result.diagnostics,
                "camera_audit": _camera_audit_report(camera_audit),
            }
        )
        if result.episode_role == "diagnostic_only":
            diagnostic_episode_ids.append(episode_id)
            continue

        clean_metadata = _clean_metadata(
            episode=episode,
            raw_path=raw_path,
            result=result,
            view_name=_VIEW_CLEAN_ALL,
        )
        _write_clean_episode(
            target_path=clean_all_root / raw_path.name,
            source_path=source_path,
            episode=episode,
            result=result,
            action_loss_mask=result.action_loss_mask,
            metadata=clean_metadata,
        )

        if result.controller_epoch == "post_fix_candidate":
            pool_root = post_fix_root
            view_name = _VIEW_POST_FIX
        else:
            pool_root = pre_fix_root
            view_name = _VIEW_PRE_FIX
        _write_clean_episode(
            target_path=pool_root / raw_path.name,
            source_path=source_path,
            episode=episode,
            result=result,
            action_loss_mask=result.default_action_loss_mask,
            metadata=_clean_metadata(
                episode=episode,
                raw_path=raw_path,
                result=result,
                view_name=view_name,
            ),
        )

    _write_jsonl(output_root / "contamination_windows.jsonl", all_windows)
    _write_jsonl(output_root / "cycle_eligibility.jsonl", all_cycles)
    _write_jsonl(
        output_root / "post_fix_replay_selection.jsonl",
        [
            row
            for row in all_cycles
            if row["controller_epoch"] == "post_fix_candidate"
            and bool(row["replay_candidate"])
        ],
    )
    _write_jsonl(
        output_root / "pre_fix_salvage_selection.jsonl",
        [
            row
            for row in all_cycles
            if row["controller_epoch"] == "pre_fix_candidate"
            and bool(row["replay_candidate"])
        ],
    )
    _write_json(
        output_root / "field_gap_report.json",
        _build_field_gap_report(selected_paths),
    )
    _write_json(output_root / "episode_cleaning_report.json", episode_reports)

    for view_root, view_name in (
        (clean_all_root, _VIEW_CLEAN_ALL),
        (post_fix_root, _VIEW_POST_FIX),
        (pre_fix_root, _VIEW_PRE_FIX),
    ):
        write_lineage_json(
            view_root,
            builder="tb-build-terrain-clean-dataset",
            storage_mode=STORAGE_MODE_VDS,
            source_roots=[source_root],
            input_dataset_ids=[source_root.name],
            schema_versions={
                "hdf5": "1.1",
                "cleaning": CLEANING_SCHEMA,
            },
            extra={
                "pipeline_version": PIPELINE_VERSION,
                "view": view_name,
                "action_loss_mask_scope": ACTION_LOSS_MASK_SCOPE,
                "approved_source_root": str(source_root),
            },
        )

    training_configs = write_training_view_configs(
        output_root=output_root,
        approved_source_root=source_root,
        post_fix_root=post_fix_root,
        pre_fix_root=pre_fix_root,
    )

    source_after = [_source_snapshot(path) for path in selected_paths]
    if source_after != source_before:
        raise RuntimeError("Immutable source verification failed after VDS build.")
    source_manifest["source_immutable_verified"] = True
    _write_json(output_root / "source_manifest.json", source_manifest)

    summary = {
        "pipeline_version": PIPELINE_VERSION,
        "approved_source_root": str(source_root),
        "output_root": str(output_root.resolve()),
        "source_episode_count": len(source_paths),
        "processed_episode_ids": selected_ids,
        "processed_episode_count": len(selected_ids),
        "diagnostic_episode_ids": diagnostic_episode_ids,
        "contamination_window_count": len(all_windows),
        "cycle_count": len(all_cycles),
        "post_fix_replay_candidate_count": sum(
            row["controller_epoch"] == "post_fix_candidate"
            and bool(row["replay_candidate"])
            for row in all_cycles
        ),
        "outputs": {
            "labels_v2_1_vds": str(label_root.resolve()),
            "operator_first_vds": str(operator_root.resolve()),
            "hindsight_vds": str(hindsight_root.resolve()),
            "clean_all_vds": str(clean_all_root.resolve()),
            "post_fix_default_vds": str(post_fix_root.resolve()),
            "pre_fix_salvage_vds": str(pre_fix_root.resolve()),
            "post_fix_training_config": training_configs["post_fix_default"],
            "pre_fix_training_config": training_configs[
                "pre_fix_salvage_ablation"
            ],
        },
        "source_immutable_verified": True,
    }
    _write_json(output_root / "summary.json", summary)
    return summary


def write_training_view_configs(
    *,
    output_root: str | Path,
    approved_source_root: str | Path,
    post_fix_root: str | Path,
    pre_fix_root: str | Path,
) -> dict[str, str]:
    """Write two no-overwrite data overlays with disjoint roots and lineage."""
    root = Path(output_root).expanduser().resolve()
    approved = Path(approved_source_root).expanduser().resolve()
    post_fix = Path(post_fix_root).expanduser().resolve()
    pre_fix = Path(pre_fix_root).expanduser().resolve()
    config_root = root / "training_configs"
    config_root.mkdir(parents=True, exist_ok=True)
    configs = {
        "post_fix_default": (
            config_root / "post_fix_default_data.yaml",
            {
                "schema": TRAINING_VIEW_SCHEMA,
                "view": "post_fix_default",
                "usage": "default_pool",
                "default_enabled": True,
                "approved_source_root": str(approved),
                "task": {"dataset_dir": str(post_fix)},
                "train": {
                    "action_loss_mask_scope": ACTION_LOSS_MASK_SCOPE,
                    "metadata_filters": {
                        "controller_epoch": "post_fix_candidate"
                    },
                },
                "lineage_path": str(post_fix / "lineage.json"),
            },
        ),
        "pre_fix_salvage_ablation": (
            config_root / "pre_fix_salvage_ablation_data.yaml",
            {
                "schema": TRAINING_VIEW_SCHEMA,
                "view": "pre_fix_salvage",
                "usage": "salvage_ablation_only",
                "default_enabled": False,
                "approved_source_root": str(approved),
                "task": {"dataset_dir": str(pre_fix)},
                "train": {
                    "action_loss_mask_scope": ACTION_LOSS_MASK_SCOPE,
                    "metadata_filters": {
                        "controller_epoch": "pre_fix_candidate"
                    },
                },
                "lineage_path": str(pre_fix / "lineage.json"),
            },
        ),
    }
    written: dict[str, str] = {}
    for key, (path, payload) in configs.items():
        if path.exists():
            raise FileExistsError(f"Training view config already exists: {path}")
        with path.open("x", encoding="utf-8") as stream:
            yaml.safe_dump(payload, stream, sort_keys=False)
        written[key] = str(path.resolve())
    return written


def audit_four_camera_jpeg_steps(
    path: str | Path,
    *,
    decode_frames: bool = True,
) -> dict[str, Any]:
    """Return a per-step validity mask; one broken JPEG masks only that row."""
    path = Path(path)
    issues: list[dict[str, Any]] = []
    with h5py.File(path, "r") as handle:
        steps = int(handle[DS_ACTION].shape[0])
        valid = np.ones(steps, dtype=np.uint8)
        metadata = dict(handle["metadata"].attrs) if "metadata" in handle else {}
        configured = tuple(camera_names_from_metadata(metadata))
        if configured != REQUIRED_CAMERA_NAMES:
            valid[:] = 0
            issues.append(
                {
                    "reason": "camera_order_or_set_mismatch",
                    "expected": list(REQUIRED_CAMERA_NAMES),
                    "actual": list(configured),
                }
            )
        encoded_group = handle.get(GRP_ENCODED_IMAGES)
        if encoded_group is None:
            valid[:] = 0
            issues.append({"reason": "missing_encoded_camera_group"})
            return {
                "step_valid_mask": valid,
                "issues": issues,
                "missing_entire_route": True,
                "invalid_step_count": steps,
            }

        missing = [name for name in REQUIRED_CAMERA_NAMES if name not in encoded_group]
        if missing:
            valid[:] = 0
            issues.append({"reason": "missing_camera_routes", "cameras": missing})
        for camera_name in REQUIRED_CAMERA_NAMES:
            if camera_name not in encoded_group:
                continue
            dataset = encoded_group[camera_name]
            encoding = _text(dataset.attrs.get("encoding", ""))
            if dataset.ndim != 1 or h5py.check_vlen_dtype(dataset.dtype) != np.dtype(
                "uint8"
            ):
                valid[:] = 0
                issues.append(
                    {
                        "reason": "encoded_camera_layout_invalid",
                        "camera": camera_name,
                        "shape": list(dataset.shape),
                        "dtype": str(dataset.dtype),
                    }
                )
                continue
            if str(encoding).lower() != JPEG_ENCODING:
                valid[:] = 0
                issues.append(
                    {
                        "reason": "encoded_camera_encoding_invalid",
                        "camera": camera_name,
                        "encoding": str(encoding),
                    }
                )
            route_steps = int(dataset.shape[0])
            if route_steps != steps:
                valid[min(route_steps, steps) :] = 0
                issues.append(
                    {
                        "reason": "camera_length_mismatch",
                        "camera": camera_name,
                        "expected": steps,
                        "actual": route_steps,
                    }
                )
            for step_index in range(min(steps, route_steps)):
                try:
                    frame = np.asarray(dataset[step_index], dtype=np.uint8).reshape(-1)
                    if (
                        frame.size < 4
                        or bytes(frame[:2]) != b"\xff\xd8"
                        or bytes(frame[-2:]) != b"\xff\xd9"
                    ):
                        raise ValueError("jpeg_marker_invalid")
                    if decode_frames:
                        decoded = decode_jpeg_rgb(frame)
                        if decoded.ndim != 3 or decoded.shape[-1] != 3:
                            raise ValueError(f"decoded_shape_invalid:{decoded.shape}")
                except Exception as exc:
                    valid[step_index] = 0
                    issues.append(
                        {
                            "reason": "jpeg_frame_invalid",
                            "camera": camera_name,
                            "step": step_index,
                            "error": str(exc),
                        }
                    )
    return {
        "step_valid_mask": valid,
        "issues": issues,
        "missing_entire_route": bool(not np.any(valid)),
        "invalid_step_count": int(np.sum(valid == 0)),
    }


def _build_label_layer(
    *,
    source_paths: list[Path],
    output_dir: Path,
    success_cfg: dict[str, Any],
    reward_cfg: dict[str, Any],
    qualified_dig_start_mode: str,
    label_config_path: Path | None,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    for source_path in source_paths:
        episode = read_episode(source_path, load_images=False)
        metadata = dict(episode.get("metadata", {}) or {})
        scenario_id = str(metadata.get("scenario_id", "")).strip()
        if not scenario_id:
            raise KeyError(f"{source_path.name} is missing metadata.scenario_id.")
        env_state = episode.get("env_state")
        if env_state is None:
            raise ValueError(f"{source_path.name} is missing env_state.")
        v2_payload, metadata_updates = label_episode_v2_1(
            qpos=episode["qpos"],
            actions=episode["actions"],
            env_state=env_state,
            metadata=metadata,
            scenario_id=scenario_id,
            pause_action_eps=0.05,
            reward_cfg=reward_cfg,
            success_cfg=success_cfg,
        )
        metadata.update(metadata_updates)
        metadata.update(
            {
                "label_storage_mode": STORAGE_MODE_VDS,
                "qualified_dig_start_mode": qualified_dig_start_mode,
            }
        )
        if label_config_path is not None:
            metadata["label_config_path"] = str(label_config_path)
        write_vds_episode(
            output_dir / source_path.name,
            source_path=source_path,
            crop=slice(0, int(np.asarray(episode["actions"]).shape[0])),
            metadata=metadata,
            v2_step_overlay=dict(v2_payload.get("step", {}) or {}),
            v2_cycle_payload=dict(v2_payload.get("cycle", {}) or {}),
            action_src_types=episode.get("action_src_types"),
            action_src_ids=episode.get("action_src_ids"),
        )
    write_lineage_json(
        output_dir,
        builder="tb-build-terrain-clean-dataset:labels_v2_1",
        storage_mode=STORAGE_MODE_VDS,
        source_roots=[path.parent for path in source_paths[:1]],
        input_dataset_ids=[source_paths[0].parent.name] if source_paths else [],
        schema_versions={"hdf5": "1.1", "v2_labels": "v2_1"},
        extra={
            "qualified_dig_start_mode": qualified_dig_start_mode,
            "pipeline_version": PIPELINE_VERSION,
        },
    )


def _write_clean_episode(
    *,
    target_path: Path,
    source_path: Path,
    episode: dict[str, Any],
    result: EpisodeCleaningResult,
    action_loss_mask: np.ndarray,
    metadata: dict[str, Any],
) -> None:
    v2 = dict(episode.get("v2") or {})
    step = {
        str(key): np.asarray(value)
        for key, value in dict(v2.get("step", {}) or {}).items()
    }
    cycle = {
        str(key): np.asarray(value)
        for key, value in dict(v2.get("cycle", {}) or {}).items()
    }
    mask = np.asarray(action_loss_mask, dtype=np.uint8).reshape(-1)
    existing_mask = np.asarray(
        step.get("action_loss_mask", np.ones(mask.shape[0], dtype=np.uint8)),
        dtype=np.uint8,
    ).reshape(-1)
    if existing_mask.shape != mask.shape:
        raise ValueError(f"Existing action_loss_mask shape mismatch in {source_path}.")
    step_overlay: dict[str, np.ndarray] = {
        "action_loss_mask": (mask.astype(bool) & existing_mask.astype(bool)).astype(
            np.uint8
        )
    }
    rejected = [
        row
        for row in result.cycles
        if bool(row["review_required"]) or not bool(row["replay_candidate"])
    ]
    for key in ("dig_goal_valid_mask", "return_goal_valid_mask"):
        if key not in step:
            continue
        validity = np.asarray(step[key], dtype=np.uint8).copy()
        for row in rejected:
            validity[int(row["start_step"]) : int(row["end_step_exclusive"])] = 0
        step_overlay[key] = validity

    if result.cycles:
        cycle["cleaning_act_training_eligible"] = np.asarray(
            [row["act_training_eligible"] for row in result.cycles], dtype=np.uint8
        )
        cycle["cleaning_effect_calibration_eligible"] = np.asarray(
            [row["effect_calibration_eligible"] for row in result.cycles],
            dtype=np.uint8,
        )
        cycle["cleaning_replay_candidate"] = np.asarray(
            [row["replay_candidate"] for row in result.cycles], dtype=np.uint8
        )
        cycle["cleaning_review_required"] = np.asarray(
            [row["review_required"] for row in result.cycles], dtype=np.uint8
        )
        cycle["cleaning_deposit_label_valid"] = np.asarray(
            [row["deposit_label_valid"] for row in result.cycles], dtype=np.uint8
        )
        cycle["cleaning_reason_codes"] = np.asarray(
            [",".join(row["reason_codes"]) for row in result.cycles], dtype=object
        )

    write_vds_episode(
        target_path,
        source_path=source_path,
        crop=slice(0, int(np.asarray(episode["actions"]).shape[0])),
        metadata=metadata,
        v2_step_overlay=step_overlay,
        v2_cycle_payload=cycle,
        action_src_types=episode.get("action_src_types"),
        action_src_ids=episode.get("action_src_ids"),
    )


def _clean_metadata(
    *,
    episode: dict[str, Any],
    raw_path: Path,
    result: EpisodeCleaningResult,
    view_name: str,
) -> dict[str, Any]:
    metadata = dict(episode.get("metadata", {}) or {})
    metadata.update(
        {
            "terrain_cleaning_schema": CLEANING_SCHEMA,
            "terrain_clean_dataset_version": PIPELINE_VERSION,
            "controller_epoch": result.controller_epoch,
            "episode_role": result.episode_role,
            "clean_dataset_view": view_name,
            "action_loss_mask_scope": ACTION_LOSS_MASK_SCOPE,
            "raw_source_realpath": str(raw_path.resolve()),
            "raw_rows_deleted": 0,
            "raw_resampled": 0,
        }
    )
    return metadata


def _source_snapshot(path: Path) -> dict[str, Any]:
    stat = path.stat()
    datasets: dict[str, dict[str, Any]] = {}
    with h5py.File(path, "r") as handle:
        def visitor(name: str, item: h5py.Group | h5py.Dataset) -> None:
            if isinstance(item, h5py.Dataset):
                datasets[name] = {
                    "shape": list(item.shape),
                    "dtype": str(item.dtype),
                    "is_virtual": bool(item.is_virtual),
                }

        handle.visititems(visitor)
    return {
        "episode_id": _episode_id(path),
        "filename": path.name,
        "realpath": str(path.resolve()),
        "size_bytes": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "datasets": datasets,
    }


def _build_field_gap_report(source_paths: list[Path]) -> dict[str, Any]:
    episodes: list[dict[str, Any]] = []
    for path in source_paths:
        with h5py.File(path, "r") as handle:
            metadata = dict(handle["metadata"].attrs) if "metadata" in handle else {}
            missing_paths = [
                name
                for name in (
                    DS_ACTION,
                    DS_QPOS,
                    DS_QVEL,
                    DS_ENV_STATE,
                    DS_STEP_ID,
                    DS_STEP_NS,
                )
                if name not in handle
            ]
            env_dim = int(handle[DS_ENV_STATE].shape[1]) if DS_ENV_STATE in handle else 0
            raw_order = _text(metadata.get("env_state_order", ""))
            env_order = tuple(
                item.strip() for item in str(raw_order).split(",") if item.strip()
            )
            episodes.append(
                {
                    "episode_id": _episode_id(path),
                    "source_path": str(path.resolve()),
                    "missing_required_paths": missing_paths,
                    "env_state_dim": env_dim,
                    "env_state_contract_version": str(
                        _text(metadata.get("env_state_contract_version", ""))
                    ),
                    "missing_v2_3_env_fields": [
                        name for name in ENV_STATE_ORDER_V2_3 if name not in env_order
                    ],
                    "runtime_build_id": str(
                        _text(metadata.get("runtime_build_id", ""))
                    ),
                    "terrain_state_contract_version": str(
                        _text(metadata.get("terrain_state_contract_version", ""))
                    ),
                    "terrain_volume_source": str(
                        _text(metadata.get("terrain_volume_source", ""))
                    ),
                    "direct_volume_status": "unavailable_no_sensor",
                }
            )
    return {
        "schema": "terrain_field_gap_report_v1",
        "required_env_state_contract": "agx_env_state_v2_3_89",
        "required_terrain_state_contract": "terrain_state_grid_3x2_v1",
        "volume_label_status": "derived_grid_integral",
        "direct_volume_status": "unavailable_no_sensor",
        "episodes": episodes,
    }


def _set_raw_source_provenance(
    result: EpisodeCleaningResult,
    raw_path: Path,
) -> None:
    raw = str(raw_path.resolve())
    for row in result.cycles:
        row["source_path"] = raw
    for row in result.windows:
        row["source_path"] = raw


def _camera_audit_report(audit: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in audit.items()
        if key != "step_valid_mask"
    }


def _load_label_config(
    path: str | Path | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if path is None:
        return {}, {}
    config_path = Path(path)
    with config_path.open() as stream:
        config = yaml.safe_load(stream) or {}
    if not isinstance(config, dict):
        raise ValueError(f"Label config {config_path} must be a YAML mapping.")
    return dict(config.get("success", {}) or {}), dict(config.get("reward", {}) or {})


def _resolve_episode_ids(
    episode_ids: Iterable[int] | None,
    *,
    expected_episode_count: int,
) -> list[int]:
    if episode_ids is None:
        return list(range(expected_episode_count))
    values = sorted(set(int(value) for value in episode_ids))
    invalid = [value for value in values if value < 0 or value >= expected_episode_count]
    if invalid:
        raise ValueError(f"Episode ids outside approved inventory: {invalid}.")
    if not values:
        raise ValueError("At least one episode id must be selected.")
    return values


def _episode_id(path: Path) -> int:
    return int(path.stem.split("_", 1)[1])


def _text(value: Any) -> Any:
    return value.decode("utf-8") if isinstance(value, (bytes, np.bytes_)) else value


def _write_json(path: Path, payload: Any) -> None:
    with path.open("w", encoding="utf-8") as stream:
        json.dump(_jsonable(payload), stream, indent=2, sort_keys=True)
        stream.write("\n")


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(_jsonable(row), sort_keys=True))
            stream.write("\n")


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    return value


__all__ = [
    "ACTION_LOSS_MASK_SCOPE",
    "PIPELINE_VERSION",
    "REQUIRED_CAMERA_NAMES",
    "audit_four_camera_jpeg_steps",
    "build_terrain_clean_dataset",
    "write_training_view_configs",
]
