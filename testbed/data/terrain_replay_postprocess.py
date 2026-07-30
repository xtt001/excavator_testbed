"""Replay-native label, hindsight, and cleaning chain for selected episodes."""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import yaml

from testbed.data.hindsight_goal_v2_4 import build_hindsight_goal_dataset
from testbed.data.operator_first_v2_2 import build_operator_first_dataset
from testbed.data.terrain_cycle_cleaning import (
    CLEANING_SCHEMA,
    analyze_episode_cleaning,
)
from testbed.data.terrain_replay_dataset import replay_camera_step_valid_mask
from testbed.data.v2_1 import label_episode_v2_1
from testbed.data.vds import STORAGE_MODE_VDS, write_lineage_json, write_vds_episode
from testbed.planner.boundary_detector import QUALIFIED_DIG_START_MODE_CONTACT_DEPTH

LABEL_VIEW = "replay_labels_v2_1_vds"
OPERATOR_VIEW = "replay_operator_first_vds"
HINDSIGHT_VIEW = "replay_hindsight_vds"
CLEAN_VIEW = "selected_replay_clean_vds"
ACTION_LOSS_MASK_SCOPE = "loss_sampling_stats"


def build_selected_replay_postprocess(
    *,
    selected_root: str | Path,
    output_root: str | Path,
    label_config_path: str | Path,
    selected_episode_ids: Sequence[int],
    complete_inventory: bool,
    evidence_kind: str = "replay_derived_selected_pass",
    training_usage: str = "selected_replay_training_candidate",
    training_config_name: str = "selected_replay_22train_2val.yaml",
) -> dict[str, Any]:
    """Recompute labels from replay state, then build the final clean VDS view."""

    selected = Path(selected_root).expanduser().resolve(strict=True)
    output = Path(output_root).expanduser().resolve(strict=True)
    config = Path(label_config_path).expanduser().resolve(strict=True)
    episode_ids = tuple(sorted(set(int(value) for value in selected_episode_ids)))
    evidence = str(evidence_kind).strip()
    if not evidence:
        raise ValueError("evidence_kind must be nonempty.")
    source_paths = [selected / f"episode_{value}.hdf5" for value in episode_ids]
    missing = [str(path) for path in source_paths if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Selected replay HDF5 files are missing: {missing}")

    final_report = output / "post_replay_qc.json"
    if final_report.is_file():
        existing = json.loads(final_report.read_text(encoding="utf-8"))
        if existing.get("selected_episode_ids") != list(episode_ids):
            raise ValueError("Existing post-replay QC inventory does not match resume.")
        if existing.get("evidence_kind") != evidence:
            raise ValueError("Existing post-replay QC evidence kind does not match resume.")
        return existing

    config_payload = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    success_cfg = dict(config_payload.get("success", {}) or {})
    reward_cfg = dict(config_payload.get("reward", {}) or {})
    reward_cfg["qualified_dig_start_mode"] = QUALIFIED_DIG_START_MODE_CONTACT_DEPTH

    labels = output / LABEL_VIEW
    if not (labels / "lineage.json").is_file():
        _require_fresh_stage(labels)
        _build_replay_label_layer(
            source_paths=source_paths,
            output_dir=labels,
            success_cfg=success_cfg,
            reward_cfg=reward_cfg,
            label_config_path=config,
            evidence_kind=evidence,
        )
    _validate_stage_inventory(labels, episode_ids)

    operator = output / OPERATOR_VIEW
    if not (operator / "operator_first_summary.json").is_file():
        _require_fresh_stage(operator)
        build_operator_first_dataset(
            dataset_dir=labels,
            output_dir=operator,
            overwrite=False,
            storage_mode=STORAGE_MODE_VDS,
        )
    _validate_stage_inventory(operator, episode_ids)

    hindsight = output / HINDSIGHT_VIEW
    if not (hindsight / "hindsight_goal_summary.json").is_file():
        _require_fresh_stage(hindsight)
        build_hindsight_goal_dataset(
            dataset_dir=operator,
            output_dir=hindsight,
            overwrite=False,
            storage_mode=STORAGE_MODE_VDS,
        )
    _validate_stage_inventory(hindsight, episode_ids)

    clean = output / CLEAN_VIEW
    if clean.exists():
        raise FileExistsError(
            f"Incomplete clean replay stage already exists; no-overwrite: {clean}"
        )
    clean.mkdir(parents=True, exist_ok=False)
    windows: list[dict[str, Any]] = []
    cycles: list[dict[str, Any]] = []
    episode_reports: list[dict[str, Any]] = []
    for episode_id in episode_ids:
        source_path = hindsight / f"episode_{episode_id}.hdf5"
        selected_path = selected / f"episode_{episode_id}.hdf5"
        episode = _read_core_episode(source_path)
        camera_mask, camera_issues = replay_camera_step_valid_mask(selected_path)
        result = analyze_episode_cleaning(
            episode_id=episode_id,
            actions=episode["actions"],
            qpos=episode["qpos"],
            qvel=episode["qvel"],
            step_ids=episode["step_ids"],
            step_ns=episode["step_ns"],
            v2_step=episode["v2"]["step"],
            v2_cycle=episode["v2"]["cycle"],
            camera_step_valid_mask=camera_mask,
        )
        for row in result.windows:
            row["source_path"] = str(selected_path.resolve())
            row["evidence_kind"] = evidence
        for row in result.cycles:
            row["source_path"] = str(selected_path.resolve())
            row["evidence_kind"] = evidence
        windows.extend(result.windows)
        cycles.extend(result.cycles)
        _write_clean_replay_episode(
            target_path=clean / source_path.name,
            source_path=source_path,
            selected_path=selected_path,
            episode=episode,
            cleaning_result=result,
            evidence_kind=evidence,
        )
        episode_reports.append(
            {
                "source_episode_id": f"episode_{episode_id}",
                "step_count": int(len(episode["actions"])),
                "valid_action_step_count": int(
                    np.count_nonzero(
                        _read_dataset(
                            clean / source_path.name,
                            "v2/step/action_loss_mask",
                        )
                    )
                ),
                "replay_qc_masked_step_count": int(
                    np.count_nonzero(result.default_action_loss_mask == 0)
                ),
                "cycle_count": len(result.cycles),
                "replay_candidate_cycle_count": sum(
                    bool(row["replay_candidate"]) for row in result.cycles
                ),
                "camera_invalid_step_count": int(np.count_nonzero(camera_mask == 0)),
                "camera_issues": camera_issues,
                "diagnostics": result.diagnostics,
            }
        )

    write_lineage_json(
        clean,
        builder="tb-build-terrain-replay-dataset:clean",
        storage_mode=STORAGE_MODE_VDS,
        source_roots=[hindsight, selected],
        input_dataset_ids=[hindsight.name, selected.name],
        schema_versions={
            "terrain_cleaning": CLEANING_SCHEMA,
            "replay_evidence": evidence,
        },
        extra={
            "action_loss_mask_scope": ACTION_LOSS_MASK_SCOPE,
            "source_identity_policy": "one_source_one_selected_replay",
            "gold_status": "not_gold",
        },
    )
    _write_jsonl(output / "post_replay_contamination_windows.jsonl", windows)
    _write_jsonl(output / "post_replay_cycle_eligibility.jsonl", cycles)
    training_config = _write_training_config(
        output_root=output,
        dataset_dir=clean,
        selected_episode_ids=episode_ids,
        complete_inventory=bool(complete_inventory),
        evidence_kind=evidence,
        usage=str(training_usage),
        config_name=str(training_config_name),
    )
    report = {
        "schema": "terrain_replay_postprocess_qc_v1",
        "status": "complete" if complete_inventory else "partial",
        "default_training_enabled": bool(complete_inventory),
        "selected_episode_ids": list(episode_ids),
        "selected_episode_count": len(episode_ids),
        "episode_reports": episode_reports,
        "total_valid_action_step_count": sum(
            int(row["valid_action_step_count"]) for row in episode_reports
        ),
        "total_cycle_count": len(cycles),
        "replay_candidate_cycle_count": sum(
            bool(row["replay_candidate"]) for row in cycles
        ),
        "label_chain": {
            "labels_v2_1": str(labels.resolve()),
            "operator_first": str(operator.resolve()),
            "hindsight": str(hindsight.resolve()),
            "clean_selected": str(clean.resolve()),
        },
        "training_config": str(training_config.resolve()),
        "evidence_kind": evidence,
        "repeatability_status": "not_assessed_single_attempt",
        "gold_status": "not_gold",
        "closed_loop_status": "not_run_by_this_builder",
        "planner_fields_status": "missing_not_generated_by_replay",
        "volume_label_status": "derived_grid_integral",
        "direct_volume_status": "unavailable_no_sensor",
    }
    _write_json(final_report, report)
    return report


def _build_replay_label_layer(
    *,
    source_paths: list[Path],
    output_dir: Path,
    success_cfg: dict[str, Any],
    reward_cfg: dict[str, Any],
    label_config_path: Path,
    evidence_kind: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    for source_path in source_paths:
        episode = _read_core_episode(source_path)
        metadata = dict(episode["metadata"])
        scenario_id = str(_text(metadata.get("scenario_id", ""))).strip()
        if not scenario_id:
            raise KeyError(f"{source_path.name} is missing metadata.scenario_id.")
        v2_payload, metadata_updates = label_episode_v2_1(
            qpos=episode["qpos"],
            actions=episode["actions"],
            env_state=episode["env_state"],
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
                "qualified_dig_start_mode": QUALIFIED_DIG_START_MODE_CONTACT_DEPTH,
                "label_config_path": str(label_config_path),
                "label_source_semantics": "replay_native_recomputed",
                "evidence_kind": evidence_kind,
            }
        )
        write_vds_episode(
            output_dir / source_path.name,
            source_path=source_path,
            crop=slice(0, len(episode["actions"])),
            metadata=metadata,
            v2_step_overlay=dict(v2_payload.get("step", {}) or {}),
            v2_cycle_payload=dict(v2_payload.get("cycle", {}) or {}),
        )
    write_lineage_json(
        output_dir,
        builder="tb-build-terrain-replay-dataset:labels_v2_1",
        storage_mode=STORAGE_MODE_VDS,
        source_roots=[source_paths[0].parent],
        input_dataset_ids=[source_paths[0].parent.name],
        schema_versions={"v2_labels": "v2_1"},
        extra={
            "qualified_dig_start_mode": QUALIFIED_DIG_START_MODE_CONTACT_DEPTH,
            "label_source_semantics": "replay_native_recomputed",
            "evidence_kind": evidence_kind,
        },
    )


def _write_clean_replay_episode(
    *,
    target_path: Path,
    source_path: Path,
    selected_path: Path,
    episode: dict[str, Any],
    cleaning_result: Any,
    evidence_kind: str,
) -> None:
    step = dict(episode["v2"]["step"])
    cycle = dict(episode["v2"]["cycle"])
    replay_qc_mask = np.asarray(
        cleaning_result.default_action_loss_mask, dtype=np.uint8
    ).reshape(-1)
    source_mask = np.asarray(
        step.get("action_loss_mask", np.ones(len(replay_qc_mask), dtype=np.uint8)),
        dtype=np.uint8,
    ).reshape(-1)
    if source_mask.shape != replay_qc_mask.shape:
        raise ValueError(f"Source/replay action mask mismatch: {source_path}")
    final_mask = (source_mask.astype(bool) & replay_qc_mask.astype(bool)).astype(
        np.uint8
    )
    if np.any(final_mask > source_mask):
        raise AssertionError("Replay cleaning reopened source-masked action rows.")
    overlay: dict[str, np.ndarray] = {
        "replay_qc_mask": replay_qc_mask,
        "action_loss_mask": final_mask,
    }
    rejected = [
        row
        for row in cleaning_result.cycles
        if bool(row["review_required"]) or not bool(row["replay_candidate"])
    ]
    for key in ("dig_goal_valid_mask", "return_goal_valid_mask"):
        if key not in step:
            continue
        validity = np.asarray(step[key], dtype=np.uint8).copy()
        for row in rejected:
            validity[int(row["start_step"]) : int(row["end_step_exclusive"])] = 0
        overlay[key] = validity
    if cleaning_result.cycles:
        cycle.update(
            {
                "cleaning_act_training_eligible": np.asarray(
                    [row["act_training_eligible"] for row in cleaning_result.cycles],
                    dtype=np.uint8,
                ),
                "cleaning_effect_calibration_eligible": np.asarray(
                    [
                        row["effect_calibration_eligible"]
                        for row in cleaning_result.cycles
                    ],
                    dtype=np.uint8,
                ),
                "cleaning_replay_candidate": np.asarray(
                    [row["replay_candidate"] for row in cleaning_result.cycles],
                    dtype=np.uint8,
                ),
                "cleaning_review_required": np.asarray(
                    [row["review_required"] for row in cleaning_result.cycles],
                    dtype=np.uint8,
                ),
                "cleaning_deposit_label_valid": np.asarray(
                    [row["deposit_label_valid"] for row in cleaning_result.cycles],
                    dtype=np.uint8,
                ),
                "cleaning_reason_codes": np.asarray(
                    [",".join(row["reason_codes"]) for row in cleaning_result.cycles],
                    dtype=object,
                ),
            }
        )
    metadata = dict(episode["metadata"])
    metadata.update(
        {
            "terrain_cleaning_schema": CLEANING_SCHEMA,
            "action_loss_mask_scope": ACTION_LOSS_MASK_SCOPE,
            "replay_qc_source": "replay_native_labels_and_dynamics_v1",
            "selected_replay_source_realpath": str(selected_path.resolve()),
            "evidence_kind": evidence_kind,
            "gold_status": "not_gold",
            "source_identity_policy": "one_source_one_selected_replay",
        }
    )
    write_vds_episode(
        target_path,
        source_path=source_path,
        crop=slice(0, len(episode["actions"])),
        metadata=metadata,
        v2_step_overlay=overlay,
        v2_cycle_payload=cycle,
    )


def _read_core_episode(path: Path) -> dict[str, Any]:
    with h5py.File(path, "r") as handle:
        metadata = dict(handle["metadata"].attrs) if "metadata" in handle else {}
        v2 = {"step": {}, "cycle": {}}
        for section in ("step", "cycle"):
            group = handle.get(f"v2/{section}")
            if group is not None:
                v2[section] = {
                    str(name): np.asarray(dataset[()])
                    for name, dataset in group.items()
                }
        return {
            "qpos": np.asarray(handle["observations/qpos"][()], dtype=np.float32),
            "qvel": np.asarray(handle["observations/qvel"][()], dtype=np.float32),
            "actions": np.asarray(handle["action"][()], dtype=np.float32),
            "env_state": np.asarray(
                handle["observations/env_state"][()], dtype=np.float32
            ),
            "step_ids": (
                np.asarray(handle["timestamps/step_id"][()], dtype=np.int64)
                if "timestamps/step_id" in handle
                else None
            ),
            "step_ns": (
                np.asarray(handle["timestamps/step_ns"][()], dtype=np.int64)
                if "timestamps/step_ns" in handle
                else None
            ),
            "metadata": metadata,
            "v2": v2,
        }


def _write_training_config(
    *,
    output_root: Path,
    dataset_dir: Path,
    selected_episode_ids: tuple[int, ...],
    complete_inventory: bool,
    evidence_kind: str,
    usage: str,
    config_name: str,
) -> Path:
    validation_ids = (33, 34)
    train_ids = tuple(
        value for value in selected_episode_ids if value not in set(validation_ids)
    )
    present_validation = tuple(
        value for value in validation_ids if value in set(selected_episode_ids)
    )
    path = output_root / "training_configs" / str(config_name)
    payload = {
        "schema": "terrain_replay_selected_training_view_v1",
        "usage": str(usage),
        "default_enabled": bool(complete_inventory),
        "dataset_dir": str(dataset_dir.resolve()),
        "source_identity_policy": "one_source_one_selected_replay",
        "action_loss_mask_scope": ACTION_LOSS_MASK_SCOPE,
        "train_ids": list(train_ids),
        "val_ids": list(present_validation),
        "expected_val_ids": list(validation_ids),
        "selected_episode_ids": list(selected_episode_ids),
        "missing_episode_ids": sorted(
            set(
                (
                    1,
                    3,
                    4,
                    6,
                    7,
                    8,
                    9,
                    10,
                    12,
                    13,
                    14,
                    16,
                    19,
                    20,
                    23,
                    24,
                    25,
                    27,
                    28,
                    29,
                    30,
                    32,
                    33,
                    34,
                )
            )
            - set(selected_episode_ids)
        ),
        "evidence_kind": str(evidence_kind),
        "gold_status": "not_gold",
    }
    _write_yaml(path, payload)
    return path


def _validate_stage_inventory(path: Path, expected_ids: tuple[int, ...]) -> None:
    actual = sorted(
        int(item.stem.rsplit("_", 1)[1]) for item in path.glob("episode_*.hdf5")
    )
    if actual != list(expected_ids):
        raise ValueError(f"Stage inventory mismatch at {path}: {actual}")


def _require_fresh_stage(path: Path) -> None:
    if path.exists():
        raise FileExistsError(f"Incomplete stage exists; no-overwrite: {path}")


def _read_dataset(path: Path, dataset: str) -> np.ndarray:
    with h5py.File(path, "r") as handle:
        return np.asarray(handle[dataset][()])


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"No-overwrite output already exists: {path}")
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: Sequence[dict[str, Any]]) -> None:
    if path.exists():
        raise FileExistsError(f"No-overwrite output already exists: {path}")
    lines = [json.dumps(row, sort_keys=True, allow_nan=False) for row in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def _write_yaml(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"No-overwrite output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _text(value: Any) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


__all__ = ["build_selected_replay_postprocess"]
