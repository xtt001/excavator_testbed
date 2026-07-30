"""Source, measurement, and request contracts for wall-contact diagnostics."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import h5py

from testbed.eval.wall_contact_artifact_io import (
    artifact_ref,
    finite,
    integer_list,
    is_sha256,
    json_sha256,
    load_json,
    load_json_sequence,
    load_locked_ref,
    load_yaml,
    locked_ref,
    mapping,
    qpos_float32_sha256,
    qpos_sha256,
    read_primitive_qpos,
    required_file,
    sha256_file,
    sha256_value,
    string_list,
    unique_records,
    validate_bucket_region_samples,
    validate_detailed_contact_summary,
    validate_intervals,
    validate_qpos_path,
    validate_reset_state,
)
from testbed.eval.wall_contact_evidence_contracts import (
    ContactEvidenceContractError,
    derive_expected_remaining_mass_kg,
    parse_worktool_wall_contact_detail,
    summarize_contact_details,
    terminal_matches_box_safety_reason,
    validate_expert_window_fairness,
)
from testbed.eval.wall_contact_source_spec import (
    lock_contact_lineage,
    lock_python_source_lineage,
)

_COMPONENTS = ("boom", "stick", "bucket")
_WALLS = (
    "Dig_XMin_Board",
    "Dig_XMax_Board",
    "Dig_ZMin_Board",
    "Dig_ZMax_Board",
)


class WallContactExperimentContractError(RuntimeError):
    """Raised for a source, schema, or evidence lineage violation."""


WallContactSupportError = WallContactExperimentContractError


def lock_sources(
    spec: Mapping[str, Any],
    *,
    train_source_ids: Sequence[int],
    holdout_source_ids: Sequence[int],
    expected_execution_records: int,
    expected_validation_paths: int,
    qpos_order: Sequence[str],
) -> dict[str, Any]:
    """Verify all frozen source artifacts and build split-authorized paths."""

    episodes_raw = mapping(
        spec.get("full_source_episodes"),
        "full_source_episodes",
    )
    expected_sources = tuple(train_source_ids) + tuple(holdout_source_ids)
    if {int(key) for key in episodes_raw} != set(expected_sources):
        raise WallContactExperimentContractError("source_episode_inventory_invalid")
    episodes: dict[int, dict[str, Any]] = {}
    for source_id in expected_sources:
        record = locked_ref(
            mapping(episodes_raw.get(str(source_id)), f"episode_{source_id}"),
            f"episode_{source_id}",
        )
        with h5py.File(record["path"], "r") as handle:
            if (
                "observations/env_state" not in handle
                or handle["observations/env_state"].ndim != 2
                or handle["observations/env_state"].shape[1] != 89
            ):
                raise WallContactSupportError(
                    f"source_env_state_not_89d:episode_{source_id}"
                )
            metadata = handle.get("metadata")
            profile_value = (
                None
                if metadata is None
                else metadata.attrs.get("replay_control_compatibility_profile")
            )
            if isinstance(profile_value, bytes):
                profile_value = profile_value.decode("utf-8")
            profile = str(profile_value or "").strip()
            if not profile:
                raise WallContactSupportError(
                    f"source_control_profile_missing:episode_{source_id}"
                )
        record["source_episode_id"] = int(source_id)
        record["split"] = "train" if source_id in train_source_ids else "validation"
        record["typed_contact_status"] = "typed_contact_fields_missing"
        record["replay_control_compatibility_profile"] = profile
        episodes[source_id] = record

    split_ref = locked_ref(mapping(spec.get("split"), "split"), "split")
    split = load_yaml(Path(split_ref["path"]))
    if split.get("split_policy") != "source_identity_exact_allowlist_v1":
        raise WallContactSupportError("split_policy_invalid")
    train_ids = integer_list(split.get("train_ids"), "train_ids")
    validation_ids = integer_list(split.get("val_ids"), "val_ids")
    if len(train_ids) != expected_execution_records:
        raise WallContactSupportError("strict_train_count_invalid")
    if len(validation_ids) != expected_validation_paths:
        raise WallContactSupportError("strict_validation_count_invalid")
    if integer_list(
        split.get("train_source_episode_ids"),
        "train_source_episode_ids",
    ) != list(train_source_ids):
        raise WallContactSupportError("train_source_split_drift")
    if integer_list(
        split.get("val_source_episode_ids"),
        "val_source_episode_ids",
    ) != list(holdout_source_ids):
        raise WallContactSupportError("validation_source_split_drift")
    allowed = integer_list(
        split.get("allowed_source_episode_ids"),
        "allowed_source_episode_ids",
    )
    if allowed != list(expected_sources):
        raise WallContactSupportError("allowed_source_split_drift")
    source_by_primitive = {
        int(key): int(value)
        for key, value in mapping(
            split.get("source_episode_id_by_primitive_episode_id"),
            "source_episode_mapping",
        ).items()
    }
    dig_root = Path(str(spec.get("dig_primitives_dir", ""))).resolve()
    if not dig_root.is_dir():
        raise FileNotFoundError(f"dig_primitives_dir_missing:{dig_root}")
    if Path(str(split.get("dataset_dir", ""))).resolve() != dig_root:
        raise WallContactSupportError("split_dig_root_drift")

    execution_ref = locked_ref(
        mapping(spec.get("execution_library"), "execution_library"),
        "execution_library",
    )
    execution = load_json(Path(execution_ref["path"]))
    if (
        execution.get("schema") != "strict_train_coverage_execution_library_v1_1"
        or execution.get("status") != "completed"
        or int(execution.get("sample_count", -1)) != expected_execution_records
    ):
        raise WallContactSupportError("execution_library_contract_invalid")
    execution_records = unique_records(
        execution.get("records"),
        key="primitive_episode_id",
        label="execution records",
        integer_key=True,
    )
    if set(execution_records) != set(train_ids):
        raise WallContactSupportError("execution_split_drift")

    pose_ref = locked_ref(
        mapping(spec.get("pose_library"), "pose_library"),
        "pose_library",
    )
    pose = load_json(Path(pose_ref["path"]))
    if (
        pose.get("schema") != "strict_train_coverage_pose_paths_v1"
        or pose.get("status") != "completed"
        or int(pose.get("sample_count", -1)) != expected_execution_records
    ):
        raise WallContactSupportError("pose_library_contract_invalid")
    pose_order = tuple(
        mapping(pose.get("qpos_contract"), "qpos_contract").get("order", ())
    )
    if pose_order != tuple(qpos_order):
        raise WallContactSupportError("pose_qpos_order_drift")
    pose_records = unique_records(
        pose.get("records"),
        key="primitive_episode_id",
        label="pose records",
        integer_key=True,
    )
    if set(pose_records) != set(train_ids):
        raise WallContactSupportError("pose_split_drift")

    sweep_ref = locked_ref(
        mapping(spec.get("legacy_sweep"), "legacy_sweep"),
        "legacy_sweep",
    )
    sweep = load_json(Path(sweep_ref["path"]))
    sweep_lock = mapping(sweep.get("source_lock"), "legacy_sweep.source_lock")
    if (
        sweep.get("schema") != "coverage_worktool_sweep_library_v1"
        or sweep.get("status") != "completed"
        or int(sweep.get("sample_count", -1)) != expected_execution_records
        or str(sweep_lock.get("execution_library_sha256", "")).lower()
        != execution_ref["sha256"]
        or str(sweep_lock.get("pose_library_sha256", "")).lower() != pose_ref["sha256"]
    ):
        raise WallContactSupportError("legacy_sweep_contract_drift")
    unity = mapping(spec.get("unity"), "unity")
    unity_root = Path(str(unity.get("repo_root", ""))).resolve()
    if not unity_root.is_dir():
        raise FileNotFoundError(f"unity_repo_root_missing:{unity_root}")
    scene_sha = sha256_value(unity.get("scene_sha256"), "scene_sha256")
    if str(sweep_lock.get("scene_sha256", "")).lower() != scene_sha:
        raise WallContactSupportError("unity_scene_sha_drift")
    contact_lineage_files, contact_lineage_sha = lock_contact_lineage(unity)
    python_lineage_files, python_lineage_sha = lock_python_source_lineage(
        mapping(spec.get("python"), "python")
    )
    scene_path = required_file(
        unity_root / str(sweep_lock.get("scene_path", "")),
        "unity_scene",
    )
    if sha256_file(scene_path) != scene_sha:
        raise WallContactSupportError("unity_scene_file_sha_drift")
    normalization_sha = sha256_value(
        sweep_lock.get("normalization_sha256"),
        "normalization_sha256",
    )
    normalization_path = required_file(
        unity_root / str(sweep_lock.get("normalization_path", "")),
        "unity_normalization",
    )
    if sha256_file(normalization_path) != normalization_sha:
        raise WallContactSupportError("unity_normalization_sha_drift")

    target_ref = locked_ref(
        mapping(
            spec.get("frozen_target_handoff"),
            "frozen_target_handoff",
        ),
        "frozen_target_handoff",
    )
    target = load_json(Path(target_ref["path"]))
    if (
        target.get("schema") != "episode_168_bounded_handoff_v1"
        or target.get("exemplar_id") != "episode_168"
        or not is_sha256(target.get("raw_fields_sha256"))
    ):
        raise WallContactSupportError("frozen_target_handoff_invalid")
    validate_reset_state(target)
    if (
        int(target.get("handoff_row_index", -1)) + 1
        != int(target.get("first_dig_row_index", -1))
        or int(target.get("handoff_t", -1)) + 1 != int(target.get("first_dig_t", -1))
        or int(target.get("handoff_step_id", -1)) + 1
        != int(target.get("first_dig_step_id", -1))
        or int(target.get("cycle_index", -1)) < 0
        or int(target.get("selection_event_cycle_index", -2))
        != int(target.get("cycle_index", -1)) - 1
        or int(target.get("corridor_id", -1)) < 0
    ):
        raise WallContactSupportError("frozen_target_handoff_row_lineage_invalid")
    target_rollout_lock = _ab_lineage_source_lock(target)
    reset_ref = locked_ref(
        mapping(spec.get("expected_reset_state"), "expected_reset_state"),
        "expected_reset_state",
    )
    reset = load_json(Path(reset_ref["path"]))
    validate_reset_state(reset)
    if (
        reset.get("schema") != "wall_contact_expected_reset_state_v1"
        or reset.get("checkpoint_semantics") != "first_post_reset_control_step"
    ):
        raise WallContactSupportError("expected_reset_state_semantics_invalid")
    reset_rollout_lock = _ab_lineage_source_lock(reset)
    if reset_rollout_lock != target_rollout_lock:
        raise WallContactSupportError("ab_lineage_source_lock_drift")

    window_lock, windows = window_records(split)
    source_windows: dict[int, list[dict[str, Any]]] = {
        source_id: [] for source_id in expected_sources
    }
    for primitive_id, window in sorted(windows.items()):
        source_label = str(window.get("source_episode_id", ""))
        try:
            source_id = int(source_label.removeprefix("episode_"))
        except ValueError as exc:
            raise WallContactSupportError("window_source_episode_id_invalid") from exc
        if source_id not in source_windows:
            continue
        source_windows[source_id].append(
            {
                "window_id": f"dig_episode_{primitive_id}",
                "primitive_episode_id": primitive_id,
                "source_cycle_id": int(window.get("source_cycle_id", -1)),
                "start_step": int(window.get("source_start_step", -1)),
                "end_step_exclusive": int(window.get("source_end_step_exclusive", -1)),
            }
        )
    if windows and any(not value for value in source_windows.values()):
        raise WallContactSupportError("source_authorized_windows_missing")
    geometry_paths = build_geometry_paths(
        train_ids=train_ids,
        validation_ids=validation_ids,
        source_by_primitive=source_by_primitive,
        pose_records=pose_records,
        dig_root=dig_root,
        episodes=episodes,
        windows=windows,
    )
    return {
        "episodes": episodes,
        "source_windows": source_windows,
        "geometry_paths": geometry_paths,
        "target": target,
        "reset": reset,
        "source_lock": {
            "full_source_episodes": {
                str(key): value for key, value in episodes.items()
            },
            "split": split_ref,
            "window_manifest": window_lock,
            "execution_library": execution_ref,
            "pose_library": pose_ref,
            "legacy_sweep": {
                **sweep_ref,
                "runtime_role": "diagnostic_legacy",
                "may_unlock_contact_semantics": False,
            },
            "frozen_target_handoff": target_ref,
            "expected_reset_state": reset_ref,
            "unity": {
                "scene_sha256": scene_sha,
                "scene_path": str(scene_path),
                "contact_lineage_files": contact_lineage_files,
                "contact_lineage_aggregate_sha256": contact_lineage_sha,
                "legacy_sweep_predictor_code_sha256": str(
                    sweep_lock.get("predictor_code_sha256", "")
                ),
                "normalization_sha256": normalization_sha,
                "normalization_path": str(normalization_path),
            },
            "python": {
                "repo_root": str(Path(__file__).resolve().parents[2]),
                "lineage_files": python_lineage_files,
                "lineage_aggregate_sha256": python_lineage_sha,
            },
        },
    }


def _ab_lineage_source_lock(
    value: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    source = mapping(value.get("source_lock"), "ab_lineage.source_lock")
    return {
        key: locked_ref(mapping(source.get(key), key), key)
        for key in ("bounded_rollout_jsonl", "planner_trace")
    }


def geometry_request(
    *,
    locked: Mapping[str, Any],
    destination: Path,
    schema: str,
    qpos_order: Sequence[str],
) -> dict[str, Any]:
    source = mapping(locked["source_lock"], "source_lock")
    return {
        "schema": schema,
        "status": "ready",
        "diagnostic_only": True,
        "non_promotable": True,
        "qpos_space": "normalized_act",
        "split_manifest_path": source["split"]["path"],
        "split_manifest_sha256": source["split"]["sha256"],
        "qpos_order": list(qpos_order),
        "split_authorization": {
            "train_source_episode_ids": [
                source_id
                for source_id, record in locked["episodes"].items()
                if record["split"] == "train"
            ],
            "validation_source_episode_ids": [
                source_id
                for source_id, record in locked["episodes"].items()
                if record["split"] == "validation"
            ],
            "train_path_count": sum(
                item["split"] == "train" for item in locked["geometry_paths"]
            ),
            "validation_path_count": sum(
                item["split"] == "validation" for item in locked["geometry_paths"]
            ),
        },
        "legacy_v1_artifact_path": source["legacy_sweep"]["path"],
        "legacy_v1_artifact_sha256": source["legacy_sweep"]["sha256"],
        "legacy_v1_runtime_role": "diagnostic_legacy",
        "scene_path": source["unity"]["scene_path"],
        "scene_sha256": source["unity"]["scene_sha256"],
        "normalization_path": source["unity"]["normalization_path"],
        "normalization_sha256": source["unity"]["normalization_sha256"],
        "contact_lineage_files": source["unity"]["contact_lineage_files"],
        "contact_lineage_aggregate_sha256": source["unity"][
            "contact_lineage_aggregate_sha256"
        ],
        "output_path": str(destination / "expert_geometry" / "unity_measurement.json"),
        "status_path": str(destination / "expert_geometry" / "unity_status.json"),
        "paths": list(locked["geometry_paths"]),
    }


def expert_replay_schedule(
    *,
    locked: Mapping[str, Any],
    destination: Path,
    schema: str,
) -> dict[str, Any]:
    attempts = []
    for sequence_index, source_id in enumerate(
        sorted(locked["episodes"]),
        start=1,
    ):
        source = locked["episodes"][source_id]
        attempt_id = f"{source['split']}_source_{source_id}"
        attempts.append(
            {
                "attempt_id": attempt_id,
                "sequence_index": sequence_index,
                "source_episode_id": source_id,
                "split": source["split"],
                "source_hdf5_path": source["path"],
                "source_hdf5_sha256": source["sha256"],
                "control_compatibility_profile": source[
                    "replay_control_compatibility_profile"
                ],
                "authorized_windows": list(locked["source_windows"].get(source_id, ())),
                "attempt_index": 1,
                "max_attempts": 1,
                "retry_allowed": False,
                "replay_scope": "complete_recorded_action_source",
                "warning_schema": "worktool_wall_contact_detail_v1",
                "output_path": str(
                    destination
                    / "expert_replay"
                    / "measurements"
                    / f"{attempt_id}.json"
                ),
                "runner_contract": {
                    "status": "requires_dedicated_recorded_action_runner",
                    "generic_replay_substitution_allowed": False,
                    "first_session_scope": "per_dig_window",
                    "complete_source_replay_required": True,
                    "contact_safety_early_stop_allowed": False,
                },
            }
        )
    return {
        "schema": schema,
        "status": "prepared",
        "diagnostic_only": True,
        "attempt_count": len(attempts),
        "retry_allowed": False,
        "attempts": attempts,
    }


def validate_geometry_measurement_top(
    measurement: Mapping[str, Any],
    request: Mapping[str, Any],
    *,
    schema: str,
) -> None:
    if measurement.get("schema") != schema or measurement.get("status") != "completed":
        raise WallContactSupportError("geometry_measurement_contract_invalid")
    if str(measurement.get("request_sha256", "")).lower() != json_sha256(request):
        raise WallContactSupportError("geometry_request_sha_drift")
    for field in ("split_manifest_sha256", "qpos_order"):
        if measurement.get(field) != request.get(field):
            raise WallContactSupportError(f"geometry_{field}_drift")
    source = mapping(measurement.get("source_lock"), "geometry.source_lock")
    if source.get("scene_sha256") != request.get("scene_sha256"):
        raise WallContactSupportError("geometry_scene_sha_drift")
    if source.get("normalization_sha256") != request.get("normalization_sha256"):
        raise WallContactSupportError("geometry_normalization_sha_drift")
    if source.get("contact_lineage_aggregate_sha256") != request.get(
        "contact_lineage_aggregate_sha256"
    ):
        raise WallContactSupportError("geometry_contact_lineage_sha_drift")
    sha256_value(
        source.get("contact_sweep_code_sha256"),
        "contact_sweep_code_sha256",
    )


def validate_geometry_path(
    *,
    expected: Mapping[str, Any],
    measured: Mapping[str, Any],
) -> dict[str, Any]:
    for field in (
        "path_id",
        "source_episode_id",
        "split",
        "source_hdf5_sha256",
        "qpos_path_sha256",
    ):
        if measured.get(field) != expected.get(field):
            raise WallContactSupportError(
                f"geometry_path_lineage_drift:{expected['path_id']}:{field}"
            )
    adaptive = mapping(
        measured.get("adaptive_sampling"),
        "adaptive_sampling",
    )
    if (
        adaptive.get("proved") is not True
        or finite(
            adaptive.get("maximum_subsegment_motion_bound_m"),
            "maximum_subsegment_motion_bound_m",
            minimum=0.0,
        )
        > 0.01
    ):
        raise WallContactSupportError(
            f"geometry_adaptive_proof_invalid:{expected['path_id']}"
        )
    pairs = measured.get("component_wall_pairs")
    if not isinstance(pairs, list):
        raise WallContactSupportError("geometry_component_pairs_missing")
    indexed: dict[tuple[str, str], Mapping[str, Any]] = {}
    all_pairs: list[dict[str, Any]] = []
    contact_pairs: list[dict[str, Any]] = []
    for raw in pairs:
        pair = mapping(raw, "component_wall_pair")
        key = (str(pair.get("component")), str(pair.get("wall_name")))
        if key in indexed:
            raise WallContactSupportError("geometry_pair_duplicate")
        indexed[key] = pair
    expected_keys = {(component, wall) for component in _COMPONENTS for wall in _WALLS}
    if set(indexed) != expected_keys:
        raise WallContactSupportError(
            f"geometry_pair_inventory_invalid:{expected['path_id']}"
        )
    for key in sorted(indexed):
        pair = indexed[key]
        machine_paths = string_list(
            pair.get("machine_shape_paths"),
            "machine_shape_paths",
        )
        wall_paths = string_list(
            pair.get("wall_shape_paths"),
            "wall_shape_paths",
        )
        clearance = finite(
            pair.get("minimum_clearance_m"),
            "minimum_clearance_m",
        )
        contact_intervals = validate_intervals(
            pair.get("contact_or_overlap_intervals"),
            "contact_or_overlap_intervals",
            len(expected["qpos_path"]),
        )
        overlap_intervals = validate_intervals(
            pair.get("overlap_intervals"),
            "overlap_intervals",
            len(expected["qpos_path"]),
        )
        samples = validate_bucket_region_samples(
            pair.get("bucket_local_contact_region_samples"),
            path_id=str(expected["path_id"]),
            component=key[0],
            wall=key[1],
            machine_paths=machine_paths,
            wall_paths=wall_paths,
        )
        if key[0] == "bucket" and contact_intervals and not samples:
            raise WallContactSupportError(
                f"bucket_contact_region_lineage_missing:{expected['path_id']}"
            )
        if key[0] != "bucket" and samples:
            raise WallContactSupportError("non_bucket_local_contact_region_forbidden")
        validated_pair = {
            "component": key[0],
            "wall_name": key[1],
            "minimum_clearance_m": clearance,
            "contact_or_overlap_intervals": contact_intervals,
            "overlap_intervals": overlap_intervals,
            "bucket_local_contact_region_samples": samples,
        }
        all_pairs.append(validated_pair)
        if contact_intervals or overlap_intervals:
            contact_pairs.append(validated_pair)
    return {
        "path_id": expected["path_id"],
        "source_episode_id": expected["source_episode_id"],
        "split": expected["split"],
        "minimum_clearance_m": min(
            finite(pair.get("minimum_clearance_m"), "minimum_clearance_m")
            for pair in indexed.values()
        ),
        "component_wall_pairs": all_pairs,
        "contact_or_overlap_pairs": contact_pairs,
    }


def validate_expert_replay_source(
    *,
    expected: Mapping[str, Any],
    measured: Mapping[str, Any],
) -> dict[str, Any]:
    source_id = int(expected["source_episode_id"])
    for field in (
        "attempt_id",
        "source_episode_id",
        "split",
        "source_hdf5_path",
        "source_hdf5_sha256",
        "control_compatibility_profile",
    ):
        if measured.get(field) != expected.get(field):
            raise WallContactSupportError(
                f"expert_source_lineage_drift:{source_id}:{field}"
            )
    if (
        int(measured.get("attempt_index", -1)) != 1
        or int(measured.get("retry_count", -1)) != 0
    ):
        raise WallContactSupportError(
            f"expert_source_retry_contract_invalid:{source_id}"
        )
    windows = measured.get("dig_windows")
    if not isinstance(windows, list) or not windows:
        raise WallContactSupportError(f"expert_source_dig_windows_missing:{source_id}")
    expected_windows = {
        str(item["window_id"]): item for item in expected.get("authorized_windows", ())
    }
    measured_windows = {
        str(item.get("window_id", "")): item
        for item in windows
        if isinstance(item, Mapping)
    }
    if set(measured_windows) != set(expected_windows):
        raise WallContactSupportError(f"expert_window_inventory_drift:{source_id}")
    blockers: list[str] = []
    valid_details: list[dict[str, Any]] = []
    window_rows: list[dict[str, Any]] = []
    for index, raw in enumerate(windows):
        window = mapping(raw, "expert dig window")
        window_id = str(window.get("window_id", ""))
        expected_window = expected_windows[window_id]
        for field in (
            "source_cycle_id",
            "start_step",
            "end_step_exclusive",
        ):
            if window.get(field) != expected_window.get(field):
                blockers.append(
                    f"expert_window_lineage_drift:{source_id}:{window_id}:{field}"
                )
        fairness = validate_expert_window_fairness(
            mapping(window.get("replay_fairness"), "replay_fairness")
        )
        mass_lineage = mapping(window.get("mass_lineage"), "mass_lineage")
        expected_mass = derive_expected_remaining_mass_kg(
            live_reset_initial_remaining_mass_kg=mass_lineage.get(
                "live_reset_initial_remaining_mass_kg"
            ),
            source_removed_depth_grid_m=mass_lineage.get("source_removed_depth_grid_m"),
            source_cell_area_m2=mass_lineage.get("source_cell_area_m2"),
            live_bulk_density_kg_m3=mass_lineage.get("live_bulk_density_kg_m3"),
        )
        observed_mass = finite(
            mass_lineage.get("observed_remaining_mass_kg"),
            "observed_remaining_mass_kg",
            minimum=0.0,
        )
        reported_difference = fairness["metrics"]["remaining_mass_abs_difference_kg"]
        if not math.isclose(
            abs(observed_mass - expected_mass),
            reported_difference,
            abs_tol=1.0e-6,
            rel_tol=0.0,
        ):
            blockers.append(f"remaining_mass_lineage_drift:{source_id}:{index}")
        wall_observed = bool(window.get("wall_contact_observed", False))
        details: list[dict[str, Any]] = []
        warning_rows = window.get("warnings_by_step", ())
        if not isinstance(warning_rows, list):
            blockers.append(f"warning_rows_invalid:{source_id}:{index}")
            warning_rows = []
        for warning_row in warning_rows:
            row = mapping(warning_row, "warning row")
            try:
                details.append(
                    parse_worktool_wall_contact_detail(row.get("warnings", ()))
                )
            except ContactEvidenceContractError as exc:
                blockers.append(
                    f"typed_contact_lineage_invalid:{source_id}:{index}:{exc}"
                )
        if wall_observed and not details:
            blockers.append(f"typed_contact_lineage_missing:{source_id}:{index}")
        summary = summarize_contact_details(details)
        window_status = str(window.get("status", ""))
        expected_status = "passed" if fairness["valid"] else "invalid"
        if window_status != expected_status:
            blockers.append(f"expert_window_status_drift:{source_id}:{index}")
        production_eligible = (
            fairness["valid"]
            and window_status == "passed"
            and expected["split"] == "train"
        )
        if window.get("production_inference_eligible") is not production_eligible:
            blockers.append(f"production_eligibility_drift:{source_id}:{index}")
        all_diagnostic = validate_detailed_contact_summary(
            window.get("all_diagnostic_contact_summary"),
            label=f"all_diagnostic_contact_summary:{source_id}:{index}",
            allowed_walls=_WALLS,
        )
        production = validate_detailed_contact_summary(
            window.get("production_inference_contact_summary"),
            label=f"production_inference_contact_summary:{source_id}:{index}",
            allowed_walls=_WALLS,
        )
        if (
            all_diagnostic.get("contact_observed") != summary["contact_observed"]
            or all_diagnostic.get("categories") != summary["categories"]
            or not math.isclose(
                float(all_diagnostic.get("peak_force_n", math.nan)),
                float(summary["peak_force_n"]),
                abs_tol=1.0e-6,
                rel_tol=0.0,
            )
        ):
            blockers.append(f"diagnostic_contact_summary_drift:{source_id}:{index}")
        if not production_eligible and (
            production.get("contact_observed") is not False
            or production["component_wall_summaries"]
        ):
            blockers.append(
                f"invalid_or_holdout_force_not_excluded:{source_id}:{index}"
            )
        if production_eligible:
            valid_details.extend(details)
        hard_contact = bool(
            {"forbidden_component", "high_force_collision"}.intersection(
                summary["categories"]
            )
        )
        window_rows.append(
            {
                "window_index": index,
                "status": window_status,
                "valid_for_inference": production_eligible,
                "fairness": fairness,
                "contact": summary,
                "all_diagnostic_contact_summary": all_diagnostic,
                "production_inference_contact_summary": production,
                "hard_contact_observed": hard_contact,
            }
        )
    if measured.get("status") not in {"passed", "blocked"}:
        blockers.append(f"expert_source_status_invalid:{source_id}")
    if measured.get("status") == "blocked":
        blockers.append(f"expert_source_blocked:{source_id}")
    all_authorized_summary = validate_detailed_contact_summary(
        measured.get("all_authorized_window_contact_summary"),
        label=f"all_authorized_window_contact_summary:{source_id}",
        allowed_walls=_WALLS,
    )
    production_summary = validate_detailed_contact_summary(
        measured.get("production_inference_contact_summary"),
        label=f"source_production_inference_contact_summary:{source_id}",
        allowed_walls=_WALLS,
    )
    if expected["split"] == "validation" and (
        measured.get("holdout_used_for_region_or_budget_selection") is not False
        or production_summary.get("contact_observed") is not False
        or production_summary["component_wall_summaries"]
    ):
        blockers.append(f"holdout_selection_leak:{source_id}")
    return {
        "source_episode_id": source_id,
        "split": expected["split"],
        "status": str(measured.get("status", "")),
        "blockers": blockers,
        "windows": window_rows,
        "valid_contact_summary": summarize_contact_details(valid_details),
        "all_authorized_window_contact_summary": all_authorized_summary,
        "production_inference_contact_summary": production_summary,
        "holdout_used_for_region_or_budget_selection": False,
    }


def validate_ab_attempt(
    *,
    raw: Mapping[str, Any],
    expected: Mapping[str, Any],
    pair_valid: bool,
    fairness: Mapping[str, Any],
    target: Mapping[str, Any],
) -> dict[str, Any]:
    if raw.get("schema") != "wall_contact_paired_ab_attempt_v1":
        raise WallContactSupportError("paired_ab_attempt_schema_invalid")
    for field in ("attempt_id", "pair_id", "seed", "condition"):
        if raw.get(field) != expected.get(field):
            raise WallContactSupportError(
                f"paired_ab_attempt_lineage_drift:{expected['attempt_id']}:{field}"
            )
    target_payload = load_locked_ref(target)
    if raw.get("selected_exemplar_id") != target_payload.get("exemplar_id") or raw.get(
        "selected_raw_fields_sha256"
    ) != target_payload.get("raw_fields_sha256"):
        raise WallContactSupportError("paired_ab_target_identity_drift")
    details: list[dict[str, Any]] = []
    for warning_row in raw.get("warnings_by_step", ()):
        row = mapping(warning_row, "A/B warning row")
        details.append(parse_worktool_wall_contact_detail(row.get("warnings", ())))
    contact = summarize_contact_details(details)
    terminal_reason = str(raw.get("terminal_reason", ""))
    debug = mapping(raw.get("debug_fields"), "paired_ab.debug_fields")
    if raw.get("reset_checkpoint_semantics") != "first_post_reset_control_step":
        raise WallContactSupportError("paired_ab_reset_checkpoint_semantics_invalid")
    expected_mode = str(expected["wall_first_touch_mode"])
    if (
        debug.get("box_safety_wall_contact_diagnostic_ab_enabled") is not True
        or debug.get("box_safety_wall_first_touch_mode") != expected_mode
    ):
        raise WallContactSupportError("paired_ab_debug_lineage_invalid")
    contact_hard_reasons = {
        "wall_contact_detail_invalid",
        "wall_contact_forbidden_component",
        "wall_contact_high_force",
        "wall_contact_repeat_session",
        "wall_contact_identity_drift",
    }
    allowed_violations = {
        *contact_hard_reasons,
        "persistent_contact",
        "stuck",
        "timeout",
        "hard_bottom_contact",
    }
    raw_violations = raw.get("hard_stop_violations")
    if (
        not isinstance(raw_violations, list)
        or raw_violations != sorted(set(str(item) for item in raw_violations))
        or not set(raw_violations).issubset(allowed_violations)
    ):
        raise WallContactSupportError("paired_ab_hard_stop_violations_invalid")
    hard_violation = bool(raw_violations)
    if raw.get("hard_violation") is not hard_violation:
        raise WallContactSupportError("paired_ab_hard_violation_drift")
    contact_failure_reasons = {
        *contact_hard_reasons,
        "persistent_contact",
        "stuck",
    }
    contact_driven_failure = bool(
        not raw.get("dump_completed", False)
        and contact_failure_reasons.intersection(raw_violations)
    )
    if raw.get("contact_driven_hard_failure") is not contact_driven_failure:
        raise WallContactSupportError("paired_ab_contact_driven_failure_drift")
    if (
        expected["condition"] == "A"
        and details
        and not (
            terminal_matches_box_safety_reason(
                terminal_reason,
                "wall_contact_first_session",
            )
            or terminal_reason in contact_hard_reasons
        )
    ):
        raise WallContactSupportError("condition_a_first_touch_not_stopped")
    if (
        expected["condition"] == "A"
        and details
        and (
            raw.get("zero_action_after_first_contact") is not True
            or raw.get("neutral_acknowledged") is not True
        )
    ):
        raise WallContactSupportError("condition_a_terminal_neutral_contract_invalid")
    if (
        expected["condition"] == "B"
        and details
        and not hard_violation
        and raw.get("diagnostic_allowed_observed") is not True
    ):
        raise WallContactSupportError("condition_b_diagnostic_allow_lineage_missing")
    return {
        "attempt_id": expected["attempt_id"],
        "pair_id": expected["pair_id"],
        "sequence_index": expected["sequence_index"],
        "seed": expected["seed"],
        "condition": expected["condition"],
        "pair_valid": pair_valid,
        "reset_fairness": dict(fairness),
        "entered_carry": bool(raw.get("entered_carry", False)),
        "dump_completed": bool(raw.get("dump_completed", False)),
        "contact_ended_before_carry": bool(
            raw.get("contact_ended_before_carry", False)
        ),
        "terminal_reason": terminal_reason,
        "hard_violation": hard_violation,
        "hard_stop_violations": list(raw_violations),
        "contact_driven_hard_failure": contact_driven_failure,
        "contact": contact,
    }


def build_geometry_paths(
    *,
    train_ids: Sequence[int],
    validation_ids: Sequence[int],
    source_by_primitive: Mapping[int, int],
    pose_records: Mapping[int, Mapping[str, Any]],
    dig_root: Path,
    episodes: Mapping[int, Mapping[str, Any]],
    windows: Mapping[int, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for primitive_id in list(train_ids) + list(validation_ids):
        split = "train" if primitive_id in set(train_ids) else "validation"
        source_id = int(source_by_primitive[primitive_id])
        primitive_path = dig_root / f"episode_{primitive_id}.hdf5"
        if not primitive_path.is_file():
            raise FileNotFoundError(f"dig_primitive_missing:{primitive_path}")
        if split == "train":
            pose = pose_records[primitive_id]
            qpos = validate_qpos_path(pose.get("qpos_path"))
            legacy_recorded_sha = str(pose.get("qpos_path_sha256", "")).lower()
            if qpos_sha256(qpos) != legacy_recorded_sha:
                raise WallContactSupportError(
                    f"pose_qpos_path_sha_drift:{primitive_id}"
                )
            local_start = int(pose.get("path_start_local_index", 0))
            local_end = int(
                pose.get("path_end_local_index", local_start + len(qpos) - 1)
            )
        else:
            qpos, local_start, local_end = read_primitive_qpos(primitive_path)
        request_sha = qpos_float32_sha256(qpos)
        window = windows.get(primitive_id, {})
        source_start = int(window.get("source_start_step", 0))
        full_source = episodes[source_id]
        result.append(
            {
                "path_id": f"episode_{primitive_id}",
                "source_episode_id": source_id,
                "split": split,
                "source_hdf5_path": full_source["path"],
                "source_hdf5_sha256": full_source["sha256"],
                "dig_start_step": source_start + local_start,
                "dig_end_step": source_start + local_end,
                "qpos_path_sha256": request_sha,
                "qpos_path": qpos,
            }
        )
    return result


def window_records(
    split: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[int, Mapping[str, Any]]]:
    raw_path = str(split.get("window_manifest_path", "")).strip()
    if not raw_path:
        return {
            "path": "",
            "sha256": "",
            "status": "not_declared_by_fixture_split",
        }, {}
    path = required_file(raw_path, "window_manifest")
    payload = load_json_sequence(path)
    records: dict[int, Mapping[str, Any]] = {}
    for item in payload:
        if item.get("primitive_name") != "dig":
            continue
        primitive_id = int(item.get("primitive_episode_id", -1))
        if primitive_id in records:
            raise WallContactSupportError("window_manifest_duplicate_dig")
        records[primitive_id] = item
    return artifact_ref(path), records
