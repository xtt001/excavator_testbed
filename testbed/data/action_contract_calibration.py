"""Calibrate recorded actuator commands to one current-controller contract.

The July 2026 YuLong batch spans four target-speed configurations.  This
module preserves every original command while materialising a second, uniform
top-level ``/action`` whose value produces the same target speed under the
current controller.  Raw and existing clean HDF5 files remain immutable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import h5py
import numpy as np
import yaml

from testbed.data.schema import DS_ACTION, DS_QVEL, GRP_METADATA, GRP_V2_CYCLE
from testbed.data.terrain_cycle_cleaning import APPROVED_TERRAIN_DATASET_ROOT
from testbed.data.vds import STORAGE_MODE_VDS, write_lineage_json, write_vds_episode


ACTION_AXIS_ORDER = ("swing", "boom", "stick", "bucket")
ACTION_CALIBRATION_SCHEMA = "yulong_action_contract_calibration_v2"
CURRENT_EQUIVALENT_ACTION_CONTRACT = (
    "yulong_current_equivalent_normalized_speed_v2"
)
ACTION_LOSS_MASK_SCOPE = "loss_sampling_stats"

APPROVED_CLEAN_DATASET_ROOT = APPROVED_TERRAIN_DATASET_ROOT.with_name(
    f"{APPROVED_TERRAIN_DATASET_ROOT.name}_cycle_clean_v1"
)
DEFAULT_CALIBRATED_OUTPUT_ROOT = APPROVED_TERRAIN_DATASET_ROOT.with_name(
    f"{APPROVED_TERRAIN_DATASET_ROOT.name}_cycle_action_calibrated_v2"
)

PRE_CALIBRATION_EPISODE_IDS = (
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
)
POST_REFERENCE_EPISODE_IDS = (23, 24, 25, 27, 28, 29, 30, 32, 33, 34)

_PRE_SOURCE_VIEW = "pre_fix_salvage_vds"
_POST_SOURCE_VIEW = "post_fix_default_vds"
_MIXED_OUTPUT_VIEW = "mixed_current_equivalent_vds"
_PRE_OUTPUT_VIEW = "pre_calibrated_vds"
_POST_OUTPUT_VIEW = "post_reference_vds"

_NEUTRAL_ACTION_THRESHOLD = 0.05
_NEUTRAL_QVEL_QUANTILE = 0.995
_NEUTRAL_QVEL_MIN_ABS = np.asarray([0.05, 0.02, 0.05, 0.20], dtype=np.float32)
_DEFAULT_ANOMALY_GUARD_STEPS = 50


@dataclass(frozen=True)
class ControllerActionProfile:
    """Recorded normalized-command to physical-target-speed contract."""

    name: str
    first_episode_id: int
    last_episode_id: int
    max_target_speed_values: tuple[float, float, float, float]
    evidence: str

    @property
    def max_target_speed(self) -> np.ndarray:
        return np.asarray(self.max_target_speed_values, dtype=np.float32)


EARLY_CONTROLLER_PROFILE = ControllerActionProfile(
    name="early_controller",
    first_episode_id=0,
    last_episode_id=2,
    max_target_speed_values=(0.5, 0.05, 0.05, 0.1),
    evidence="recorded_scene_limits_and_qvel_action_response",
)
EARLY_BOOM_TUNED_CONTROLLER_PROFILE = ControllerActionProfile(
    name="early_boom_tuned",
    first_episode_id=3,
    last_episode_id=17,
    max_target_speed_values=(0.5, 0.07, 0.05, 0.1),
    evidence=(
        "recorded_free_motion_qvel_action_response_corrected_by_live_replay"
    ),
)
INTERMEDIATE_CONTROLLER_PROFILE = ControllerActionProfile(
    name="intermediate_tuning",
    first_episode_id=18,
    last_episode_id=20,
    max_target_speed_values=(0.6, 0.07, 0.07, 0.15),
    evidence="recorded_scene_diff_and_qvel_action_response",
)
CURRENT_CONTROLLER_PROFILE = ControllerActionProfile(
    name="current_controller",
    first_episode_id=21,
    last_episode_id=35,
    max_target_speed_values=(0.7, 0.1, 0.1, 0.2),
    evidence="current_unity_scene_limits_and_qvel_action_response",
)
CONTROLLER_ACTION_PROFILES = (
    EARLY_CONTROLLER_PROFILE,
    EARLY_BOOM_TUNED_CONTROLLER_PROFILE,
    INTERMEDIATE_CONTROLLER_PROFILE,
    CURRENT_CONTROLLER_PROFILE,
)


def controller_profile_for_episode(episode_id: int) -> ControllerActionProfile:
    """Return the one recorded controller profile owning ``episode_id``."""
    episode_id = int(episode_id)
    for profile in CONTROLLER_ACTION_PROFILES:
        if profile.first_episode_id <= episode_id <= profile.last_episode_id:
            return profile
    raise ValueError(
        f"Episode {episode_id} is outside the approved episode range 0..35."
    )


def calibrate_actions_to_current_contract(
    actions: np.ndarray,
    *,
    episode_id: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Map normalized actions while preserving their physical target speed."""
    action_array = np.asarray(actions, dtype=np.float32)
    if action_array.ndim != 2 or action_array.shape[1] != len(ACTION_AXIS_ORDER):
        raise ValueError(
            "Recorded actions must have shape (T, 4) in "
            f"{ACTION_AXIS_ORDER} order; got {action_array.shape}."
        )
    if not np.isfinite(action_array).all():
        raise ValueError("Recorded actions contain non-finite values.")
    source_profile = controller_profile_for_episode(int(episode_id))
    scale = source_profile.max_target_speed / CURRENT_CONTROLLER_PROFILE.max_target_speed
    calibrated = np.clip(action_array * scale.reshape(1, -1), -1.0, 1.0)
    return calibrated.astype(np.float32), scale.astype(np.float32)


def build_action_calibrated_dataset(
    *,
    clean_root: str | Path = APPROVED_CLEAN_DATASET_ROOT,
    output_root: str | Path = DEFAULT_CALIBRATED_OUTPUT_ROOT,
    pre_episode_ids: Iterable[int] = PRE_CALIBRATION_EPISODE_IDS,
    post_episode_ids: Iterable[int] = POST_REFERENCE_EPISODE_IDS,
    neutral_qvel_quantile: float = _NEUTRAL_QVEL_QUANTILE,
    neutral_qvel_min_samples: int = 100,
    anomaly_guard_steps: int = _DEFAULT_ANOMALY_GUARD_STEPS,
) -> dict[str, Any]:
    """Build no-overwrite calibrated pre, post-reference, and mixed VDS views."""
    clean_root = Path(clean_root).expanduser().resolve()
    output_root = Path(output_root).expanduser()
    if output_root.exists():
        raise FileExistsError(
            f"Output root {output_root} already exists; no-overwrite is mandatory."
        )

    pre_ids = tuple(sorted(int(value) for value in pre_episode_ids))
    post_ids = tuple(sorted(int(value) for value in post_episode_ids))
    if set(pre_ids) & set(post_ids):
        raise ValueError("Pre-calibration and post-reference episode ids overlap.")
    _validate_profile_membership(pre_ids=pre_ids, post_ids=post_ids)
    source_paths = _resolve_source_paths(
        clean_root=clean_root,
        pre_ids=pre_ids,
        post_ids=post_ids,
    )
    source_before = {
        episode_id: _file_snapshot(path)
        for episode_id, path in source_paths.items()
    }

    neutral_qvel_thresholds, neutral_counts = _derive_current_neutral_qvel_thresholds(
        [source_paths[episode_id] for episode_id in post_ids],
        quantile=float(neutral_qvel_quantile),
        min_samples=int(neutral_qvel_min_samples),
    )

    output_root.mkdir(parents=True, exist_ok=False)
    mixed_root = output_root / _MIXED_OUTPUT_VIEW
    pre_root = output_root / _PRE_OUTPUT_VIEW
    post_root = output_root / _POST_OUTPUT_VIEW
    for path in (mixed_root, pre_root, post_root):
        path.mkdir(parents=True, exist_ok=False)

    manifest_rows: list[dict[str, Any]] = []
    max_equivalence_error = 0.0
    max_post_identity_error = 0.0
    total_source_valid_steps = 0
    total_output_valid_steps = 0
    total_anomaly_steps = 0
    for episode_id in (*pre_ids, *post_ids):
        source_path = source_paths[episode_id]
        is_pre = episode_id in set(pre_ids)
        payload = _read_source_episode(source_path)
        calibrated, scale = calibrate_actions_to_current_contract(
            payload["actions"],
            episode_id=episode_id,
        )
        profile = controller_profile_for_episode(episode_id)
        calibration_valid = np.ones(len(calibrated), dtype=np.uint8)
        anomaly_step_count = 0
        if is_pre:
            calibration_valid = _legacy_response_valid_mask(
                actions=payload["actions"],
                qvel=payload["qvel"],
                neutral_qvel_thresholds=neutral_qvel_thresholds,
                guard_steps=int(anomaly_guard_steps),
            )
            anomaly_step_count = int(np.count_nonzero(calibration_valid == 0))
        source_mask = payload["action_loss_mask"]
        output_mask = np.asarray(
            (source_mask != 0) & (calibration_valid != 0), dtype=np.uint8
        )

        physical_before = payload["actions"] * profile.max_target_speed.reshape(1, -1)
        physical_after = calibrated * CURRENT_CONTROLLER_PROFILE.max_target_speed.reshape(1, -1)
        equivalence_error = float(np.max(np.abs(physical_before - physical_after)))
        max_equivalence_error = max(max_equivalence_error, equivalence_error)
        if not is_pre:
            max_post_identity_error = max(
                max_post_identity_error,
                float(np.max(np.abs(calibrated - payload["actions"]))),
            )

        metadata = dict(payload["metadata"])
        metadata.update(
            {
                "action_axis_order": ",".join(ACTION_AXIS_ORDER),
                "action_calibration_applied": int(is_pre),
                "action_calibration_scale": scale,
                "action_calibration_schema": ACTION_CALIBRATION_SCHEMA,
                "action_contract": CURRENT_EQUIVALENT_ACTION_CONTRACT,
                "action_loss_mask_scope": ACTION_LOSS_MASK_SCOPE,
                "action_original_dataset": "v2/step/action_original",
                "action_source_controller_profile": profile.name,
                "action_source_max_target_speed": profile.max_target_speed,
                "action_target_controller_profile": CURRENT_CONTROLLER_PROFILE.name,
                "action_target_max_target_speed": CURRENT_CONTROLLER_PROFILE.max_target_speed,
                "calibration_neutral_qvel_quantile": float(neutral_qvel_quantile),
                "calibration_neutral_qvel_thresholds": neutral_qvel_thresholds,
                "calibration_anomaly_guard_steps": int(anomaly_guard_steps),
            }
        )
        step_overlay = {
            "action_loss_mask": output_mask,
            "action_calibration_valid_mask": calibration_valid,
            "action_original": payload["actions"],
        }
        targets = [mixed_root / source_path.name]
        targets.append((pre_root if is_pre else post_root) / source_path.name)
        for target_path in targets:
            _write_calibrated_episode(
                target_path=target_path,
                source_path=source_path,
                calibrated_actions=calibrated,
                metadata=metadata,
                step_overlay=step_overlay,
                cycle_payload=payload["cycle"],
            )

        source_valid_count = int(np.count_nonzero(source_mask))
        output_valid_count = int(np.count_nonzero(output_mask))
        total_source_valid_steps += source_valid_count
        total_output_valid_steps += output_valid_count
        total_anomaly_steps += anomaly_step_count
        manifest_rows.append(
            {
                "episode_id": int(episode_id),
                "episode_name": source_path.stem,
                "role": "pre_calibrated" if is_pre else "post_reference",
                "source_path": str(source_path),
                "source_profile": profile.name,
                "target_profile": CURRENT_CONTROLLER_PROFILE.name,
                "source_max_target_speed": profile.max_target_speed.tolist(),
                "target_max_target_speed": CURRENT_CONTROLLER_PROFILE.max_target_speed.tolist(),
                "action_calibration_scale": scale.tolist(),
                "source_valid_step_count": source_valid_count,
                "output_valid_step_count": output_valid_count,
                "legacy_response_masked_step_count": anomaly_step_count,
                "max_physical_target_speed_error": equivalence_error,
            }
        )

    for view_root, view_name in (
        (mixed_root, _MIXED_OUTPUT_VIEW),
        (pre_root, _PRE_OUTPUT_VIEW),
        (post_root, _POST_OUTPUT_VIEW),
    ):
        write_lineage_json(
            view_root,
            builder="tb-build-action-calibrated-dataset",
            storage_mode=STORAGE_MODE_VDS,
            source_roots=[clean_root],
            input_dataset_ids=[clean_root.name],
            schema_versions={
                "action_calibration": ACTION_CALIBRATION_SCHEMA,
                "action_contract": CURRENT_EQUIVALENT_ACTION_CONTRACT,
            },
            extra={
                "view": view_name,
                "action_loss_mask_scope": ACTION_LOSS_MASK_SCOPE,
                "source_episode_ids": [
                    int(row["episode_id"])
                    for row in manifest_rows
                    if view_name == _MIXED_OUTPUT_VIEW
                    or row["role"]
                    == ("pre_calibrated" if view_name == _PRE_OUTPUT_VIEW else "post_reference")
                ],
            },
        )

    split_path = _write_recommended_post_holdout_split(
        output_root=output_root,
        dataset_dir=mixed_root,
        pre_ids=pre_ids,
        post_ids=post_ids,
    )
    training_configs = _write_training_configs(
        output_root=output_root,
        mixed_root=mixed_root,
        pre_root=pre_root,
        post_root=post_root,
        split_path=split_path,
    )

    source_after = {
        episode_id: _file_snapshot(path)
        for episode_id, path in source_paths.items()
    }
    source_immutable = source_before == source_after
    checks = {
        "exact_episode_inventory": {
            "pass": len(pre_ids) == len(list(pre_root.glob("episode_*.hdf5")))
            and len(post_ids) == len(list(post_root.glob("episode_*.hdf5")))
            and len(pre_ids) + len(post_ids)
            == len(list(mixed_root.glob("episode_*.hdf5"))),
            "pre_episode_ids": list(pre_ids),
            "post_episode_ids": list(post_ids),
        },
        "physical_target_speed_equivalence": {
            "pass": max_equivalence_error <= 1.0e-6,
            "max_abs_error": max_equivalence_error,
        },
        "post_actions_are_identity": {
            "pass": max_post_identity_error <= 1.0e-7,
            "max_abs_error": max_post_identity_error,
        },
        "masks_only_remove_steps": {
            "pass": total_output_valid_steps <= total_source_valid_steps,
            "source_valid_step_count": total_source_valid_steps,
            "output_valid_step_count": total_output_valid_steps,
            "legacy_response_masked_step_count": total_anomaly_steps,
        },
        "source_immutable": {"pass": source_immutable},
        "uniform_action_contract": _audit_uniform_action_contract(
            mixed_root,
            expected_ids=(*pre_ids, *post_ids),
        ),
    }
    status = "passed" if all(bool(item["pass"]) for item in checks.values()) else "failed"
    manifest = {
        "schema": ACTION_CALIBRATION_SCHEMA,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "clean_root": str(clean_root),
        "output_root": str(output_root.resolve()),
        "action_axis_order": list(ACTION_AXIS_ORDER),
        "target_action_contract": CURRENT_EQUIVALENT_ACTION_CONTRACT,
        "target_controller_profile": _profile_json(CURRENT_CONTROLLER_PROFILE),
        "controller_profiles": [
            _profile_json(profile) for profile in CONTROLLER_ACTION_PROFILES
        ],
        "neutral_qvel_reference": {
            "quantile": float(neutral_qvel_quantile),
            "thresholds": neutral_qvel_thresholds.tolist(),
            "sample_counts": neutral_counts.tolist(),
            "guard_steps": int(anomaly_guard_steps),
        },
        "episodes": manifest_rows,
    }
    _write_json(output_root / "calibration_manifest.json", manifest)
    report = {
        "schema": "action_calibration_acceptance_v2",
        "status": status,
        "evidence_scope": "offline_action_contract_calibration",
        "closed_loop_status": "not_run_by_this_report",
        "checks": checks,
    }
    _write_json(output_root / "calibration_acceptance_report.json", report)
    summary = {
        "status": status,
        "schema": ACTION_CALIBRATION_SCHEMA,
        "clean_root": str(clean_root),
        "output_root": str(output_root.resolve()),
        "pre_calibrated_episode_count": len(pre_ids),
        "post_reference_episode_count": len(post_ids),
        "mixed_episode_count": len(pre_ids) + len(post_ids),
        "source_valid_step_count": total_source_valid_steps,
        "output_valid_step_count": total_output_valid_steps,
        "legacy_response_masked_step_count": total_anomaly_steps,
        "max_physical_target_speed_error": max_equivalence_error,
        "outputs": {
            "mixed_current_equivalent_vds": str(mixed_root.resolve()),
            "pre_calibrated_vds": str(pre_root.resolve()),
            "post_reference_vds": str(post_root.resolve()),
            "recommended_post_holdout_split": str(split_path.resolve()),
            "training_configs": training_configs,
        },
    }
    _write_json(output_root / "summary.json", summary)
    if status != "passed":
        raise RuntimeError(
            f"Action calibration acceptance failed; diagnostics retained at {output_root}."
        )
    return summary


def _validate_profile_membership(
    *,
    pre_ids: tuple[int, ...],
    post_ids: tuple[int, ...],
) -> None:
    for episode_id in pre_ids:
        if controller_profile_for_episode(episode_id) is CURRENT_CONTROLLER_PROFILE:
            raise ValueError(
                f"Pre-calibration episode {episode_id} already uses the current profile."
            )
    for episode_id in post_ids:
        if controller_profile_for_episode(episode_id) is not CURRENT_CONTROLLER_PROFILE:
            raise ValueError(
                f"Post-reference episode {episode_id} does not use the current profile."
            )


def _resolve_source_paths(
    *,
    clean_root: Path,
    pre_ids: tuple[int, ...],
    post_ids: tuple[int, ...],
) -> dict[int, Path]:
    paths: dict[int, Path] = {}
    for episode_id, view in (
        *((episode_id, _PRE_SOURCE_VIEW) for episode_id in pre_ids),
        *((episode_id, _POST_SOURCE_VIEW) for episode_id in post_ids),
    ):
        path = clean_root / view / f"episode_{episode_id}.hdf5"
        if not path.is_file():
            raise FileNotFoundError(f"Required clean source episode is missing: {path}")
        if not path.resolve().is_relative_to(clean_root):
            raise ValueError(f"Source episode escapes the approved clean root: {path}")
        paths[int(episode_id)] = path.resolve()
    return paths


def _derive_current_neutral_qvel_thresholds(
    paths: list[Path],
    *,
    quantile: float,
    min_samples: int,
) -> tuple[np.ndarray, np.ndarray]:
    if not 0.5 < float(quantile) < 1.0:
        raise ValueError("neutral_qvel_quantile must be between 0.5 and 1.0.")
    values: list[list[np.ndarray]] = [[] for _ in ACTION_AXIS_ORDER]
    for path in paths:
        with h5py.File(path, "r") as handle:
            actions = np.asarray(handle[DS_ACTION][()], dtype=np.float32)
            qvel = np.asarray(handle[DS_QVEL][()], dtype=np.float32)
            mask = np.asarray(
                handle["v2/step/action_loss_mask"][()], dtype=np.uint8
            ).reshape(-1)
        for axis in range(len(ACTION_AXIS_ORDER)):
            selected = (mask != 0) & (
                np.abs(actions[:, axis]) < _NEUTRAL_ACTION_THRESHOLD
            )
            values[axis].append(np.abs(qvel[selected, axis]))
    thresholds = np.empty(len(ACTION_AXIS_ORDER), dtype=np.float32)
    counts = np.empty(len(ACTION_AXIS_ORDER), dtype=np.int64)
    for axis, chunks in enumerate(values):
        merged = np.concatenate(chunks) if chunks else np.asarray([], dtype=np.float32)
        counts[axis] = int(merged.size)
        if merged.size < int(min_samples):
            raise ValueError(
                f"Current-reference neutral sample count for {ACTION_AXIS_ORDER[axis]} "
                f"is {merged.size}, below required {min_samples}."
            )
        thresholds[axis] = max(
            float(np.quantile(merged, float(quantile))),
            float(_NEUTRAL_QVEL_MIN_ABS[axis]),
        )
    return thresholds, counts


def _legacy_response_valid_mask(
    *,
    actions: np.ndarray,
    qvel: np.ndarray,
    neutral_qvel_thresholds: np.ndarray,
    guard_steps: int,
) -> np.ndarray:
    neutral = np.abs(actions) < _NEUTRAL_ACTION_THRESHOLD
    outside_current_support = np.abs(qvel) > np.asarray(
        neutral_qvel_thresholds, dtype=np.float32
    ).reshape(1, -1)
    bad = np.any(neutral & outside_current_support, axis=1)
    guard_steps = max(0, int(guard_steps))
    if guard_steps and np.any(bad):
        starts = np.maximum(np.flatnonzero(bad) - guard_steps, 0)
        ends = np.minimum(np.flatnonzero(bad) + guard_steps + 1, len(bad))
        diff = np.zeros(len(bad) + 1, dtype=np.int32)
        np.add.at(diff, starts, 1)
        np.add.at(diff, ends, -1)
        bad = np.cumsum(diff[:-1]) > 0
    return np.asarray(~bad, dtype=np.uint8)


def _read_source_episode(path: Path) -> dict[str, Any]:
    with h5py.File(path, "r") as handle:
        actions = np.asarray(handle[DS_ACTION][()], dtype=np.float32)
        qvel = np.asarray(handle[DS_QVEL][()], dtype=np.float32)
        if "v2/step/action_loss_mask" not in handle:
            raise KeyError(f"Clean source {path} is missing action_loss_mask.")
        action_loss_mask = np.asarray(
            handle["v2/step/action_loss_mask"][()], dtype=np.uint8
        ).reshape(-1)
        if len(action_loss_mask) != len(actions):
            raise ValueError(
                f"Clean source {path} action_loss_mask length does not match action."
            )
        metadata = dict(handle[GRP_METADATA].attrs) if GRP_METADATA in handle else {}
        cycle = {
            str(key): np.asarray(dataset[()])
            for key, dataset in (
                handle[GRP_V2_CYCLE].items() if GRP_V2_CYCLE in handle else []
            )
        }
    return {
        "actions": actions,
        "qvel": qvel,
        "action_loss_mask": action_loss_mask,
        "metadata": metadata,
        "cycle": cycle,
    }


def _write_calibrated_episode(
    *,
    target_path: Path,
    source_path: Path,
    calibrated_actions: np.ndarray,
    metadata: dict[str, Any],
    step_overlay: dict[str, np.ndarray],
    cycle_payload: dict[str, np.ndarray],
) -> None:
    write_vds_episode(
        target_path,
        source_path=source_path,
        crop=slice(0, len(calibrated_actions)),
        metadata=metadata,
        v2_step_overlay=step_overlay,
        v2_cycle_payload=cycle_payload,
        relative_paths=True,
    )
    with h5py.File(target_path, "r+") as handle:
        del handle[DS_ACTION]
        handle.create_dataset(
            DS_ACTION,
            data=np.asarray(calibrated_actions, dtype=np.float32),
            compression="gzip",
            compression_opts=1,
            shuffle=True,
        )


def _write_recommended_post_holdout_split(
    *,
    output_root: Path,
    dataset_dir: Path,
    pre_ids: tuple[int, ...],
    post_ids: tuple[int, ...],
) -> Path:
    if len(post_ids) < 2:
        val_ids = (post_ids[-1],) if post_ids else pre_ids[-1:]
    else:
        val_count = max(1, int(round(len(post_ids) * 0.2)))
        val_ids = tuple(post_ids[-val_count:])
    train_ids = tuple(
        episode_id
        for episode_id in (*pre_ids, *post_ids)
        if episode_id not in set(val_ids)
    )
    path = output_root / "training_configs/recommended_post_holdout_split.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_dir": str(dataset_dir.resolve()),
        "requested_num_episodes": 0,
        "available_episode_ids": list((*pre_ids, *post_ids)),
        "split_seed": 0,
        "train_split_ratio": len(train_ids) / max(1, len(train_ids) + len(val_ids)),
        "train_ids": list(train_ids),
        "val_ids": list(val_ids),
        "split_policy": "post_controller_holdout_v1",
        "reused_existing_split": False,
    }
    with open(path, "w") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)
    return path


def _write_training_configs(
    *,
    output_root: Path,
    mixed_root: Path,
    pre_root: Path,
    post_root: Path,
    split_path: Path,
) -> dict[str, str]:
    config_root = output_root / "training_configs"
    configs = {
        "mixed_current_equivalent_data.yaml": {
            "schema": "terrain_clean_training_view_v1",
            "usage": "calibrated_mixed_training_candidate",
            "default_enabled": False,
            "task": {"dataset_dir": str(mixed_root.resolve())},
            "train": {
                "action_loss_mask_scope": ACTION_LOSS_MASK_SCOPE,
                "metadata_filters": {
                    "action_contract": CURRENT_EQUIVALENT_ACTION_CONTRACT
                },
                "split_path": str(split_path.resolve()),
                "reuse_split": True,
            },
            "lineage_path": str((mixed_root / "lineage.json").resolve()),
        },
        "pre_calibrated_data.yaml": {
            "schema": "terrain_clean_training_view_v1",
            "usage": "calibrated_pre_ablation",
            "default_enabled": False,
            "task": {"dataset_dir": str(pre_root.resolve())},
            "train": {
                "action_loss_mask_scope": ACTION_LOSS_MASK_SCOPE,
                "metadata_filters": {
                    "action_contract": CURRENT_EQUIVALENT_ACTION_CONTRACT
                },
            },
            "lineage_path": str((pre_root / "lineage.json").resolve()),
        },
        "post_reference_data.yaml": {
            "schema": "terrain_clean_training_view_v1",
            "usage": "post_controller_reference_ablation",
            "default_enabled": False,
            "task": {"dataset_dir": str(post_root.resolve())},
            "train": {
                "action_loss_mask_scope": ACTION_LOSS_MASK_SCOPE,
                "metadata_filters": {
                    "action_contract": CURRENT_EQUIVALENT_ACTION_CONTRACT
                },
            },
            "lineage_path": str((post_root / "lineage.json").resolve()),
        },
    }
    output: dict[str, str] = {}
    for name, payload in configs.items():
        path = config_root / name
        with open(path, "w") as handle:
            yaml.safe_dump(payload, handle, sort_keys=False)
        output[name] = str(path.resolve())
    return output


def _audit_uniform_action_contract(
    dataset_root: Path,
    *,
    expected_ids: Iterable[int],
) -> dict[str, Any]:
    errors: list[str] = []
    for episode_id in expected_ids:
        path = dataset_root / f"episode_{int(episode_id)}.hdf5"
        try:
            with h5py.File(path, "r") as handle:
                if handle[GRP_METADATA].attrs.get("action_contract") != CURRENT_EQUIVALENT_ACTION_CONTRACT:
                    errors.append(f"episode_{episode_id}: action_contract")
                actions = np.asarray(handle[DS_ACTION][()], dtype=np.float32)
                if actions.ndim != 2 or actions.shape[1] != 4:
                    errors.append(f"episode_{episode_id}: action_shape")
                if not np.isfinite(actions).all() or np.max(np.abs(actions)) > 1.0:
                    errors.append(f"episode_{episode_id}: action_bounds")
                for required in (
                    "v2/step/action_original",
                    "v2/step/action_calibration_valid_mask",
                    "v2/step/action_loss_mask",
                ):
                    if required not in handle:
                        errors.append(f"episode_{episode_id}: missing {required}")
        except OSError as exc:
            errors.append(f"episode_{episode_id}: {exc}")
    return {"pass": not errors, "errors": errors}


def _file_snapshot(path: Path) -> dict[str, Any]:
    stat = path.stat()
    with h5py.File(path, "r") as handle:
        action_shape = tuple(int(value) for value in handle[DS_ACTION].shape)
    return {
        "realpath": str(path.resolve()),
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "action_shape": list(action_shape),
    }


def _profile_json(profile: ControllerActionProfile) -> dict[str, Any]:
    return {
        "name": profile.name,
        "episode_range": [profile.first_episode_id, profile.last_episode_id],
        "max_target_speed": profile.max_target_speed.tolist(),
        "evidence": profile.evidence,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    with open(path, "w") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
