"""No-overwrite owner for the Strict-18 contact-semantics evidence stage."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from testbed.eval.wall_contact_ab_lineage import (
    WallContactABLineageError,
    build_ab_lineage,
)
from testbed.eval.wall_contact_artifact_io import (
    WallContactArtifactError,
)
from testbed.eval.wall_contact_artifact_io import (
    artifact_ref as _artifact_ref,
)
from testbed.eval.wall_contact_artifact_io import (
    load_json as _load_json,
)
from testbed.eval.wall_contact_artifact_io import (
    load_locked_ref as _load_locked_ref,
)
from testbed.eval.wall_contact_artifact_io import (
    load_yaml as _load_yaml,
)
from testbed.eval.wall_contact_artifact_io import (
    mapping as _mapping,
)
from testbed.eval.wall_contact_artifact_io import (
    required_file as _required_file,
)
from testbed.eval.wall_contact_artifact_io import (
    unique_records as _unique_records,
)
from testbed.eval.wall_contact_artifact_io import (
    write_json_x as _write_json_x,
)
from testbed.eval.wall_contact_artifact_io import (
    write_yaml_x as _write_yaml_x,
)
from testbed.eval.wall_contact_config_contracts import (
    WallContactConfigError,
)
from testbed.eval.wall_contact_config_contracts import (
    base_config_source_lock as _base_config_source_lock,
)
from testbed.eval.wall_contact_config_contracts import (
    locked_config_contract as _locked_config_contract,
)
from testbed.eval.wall_contact_config_contracts import (
    normalized_ab_config as _normalized_ab_config,
)
from testbed.eval.wall_contact_config_contracts import (
    paired_ab_configs as _support_paired_ab_configs,
)
from testbed.eval.wall_contact_config_contracts import (
    validate_base_config as _validate_base_config,
)
from testbed.eval.wall_contact_config_contracts import (
    validate_base_config_source_lock as _validate_base_config_source_lock,
)
from testbed.eval.wall_contact_evidence_contracts import (
    ContactEvidenceContractError,
    causal_classification,
    expert_same_region_sub_100kn,
    validate_reset_pair,
)
from testbed.eval.wall_contact_evidence_reporting import (
    build_causal_report_sections,
    render_causal_report_markdown,
    summarize_expert_replay_records,
    summarize_geometry_paths,
    summarize_paired_ab_attempts,
)
from testbed.eval.wall_contact_experiment_contracts import (
    WallContactExperimentContractError,
)
from testbed.eval.wall_contact_experiment_contracts import (
    expert_replay_schedule as _support_expert_replay_schedule,
)
from testbed.eval.wall_contact_experiment_contracts import (
    geometry_request as _support_geometry_request,
)
from testbed.eval.wall_contact_experiment_contracts import (
    lock_sources as _support_lock_sources,
)
from testbed.eval.wall_contact_experiment_contracts import (
    validate_ab_attempt as _validate_ab_attempt,
)
from testbed.eval.wall_contact_experiment_contracts import (
    validate_expert_replay_source as _validate_expert_replay_source,
)
from testbed.eval.wall_contact_experiment_contracts import (
    validate_geometry_measurement_top as _support_validate_geometry_measurement_top,
)
from testbed.eval.wall_contact_experiment_contracts import (
    validate_geometry_path as _validate_geometry_path,
)
from testbed.eval.wall_contact_source_spec import (
    WallContactSourceSpecError,
)
from testbed.eval.wall_contact_source_spec import (
    build_source_spec as _build_source_spec,
)
from testbed.eval.wall_contact_source_spec import (
    lock_python_source_lineage as _lock_python_source_lineage,
)

EXPERIMENT_SCHEMA = "wall_contact_semantics_recovery_v1"
SOURCE_SPEC_SCHEMA = "wall_contact_semantics_source_lock_spec_v1"
GEOMETRY_INPUT_SCHEMA = "expert_worktool_contact_sweep_input_v1"
GEOMETRY_MEASUREMENT_SCHEMA = "expert_worktool_contact_sweep_measurement_v1"
EXPERT_REPLAY_SCHEDULE_SCHEMA = "expert_recorded_action_contact_replay_schedule_v1"
EXPERT_REPLAY_MEASUREMENT_SCHEMA = (
    "expert_recorded_action_contact_replay_measurement_v1"
)
AB_SCHEDULE_SCHEMA = "wall_contact_paired_ab_schedule_v1"
AB_ATTEMPT_SET_SCHEMA = "wall_contact_paired_ab_attempt_set_v1"
AB_ATTEMPT_SCHEMA = "wall_contact_paired_ab_attempt_v1"
AB_COLLECTION_SCHEMA = "wall_contact_paired_ab_collection_v1"
FINAL_REPORT_SCHEMA = "wall_contact_semantics_causal_report_v1"

TRAIN_SOURCE_EPISODE_IDS = (
    3,
    6,
    7,
    8,
    9,
    13,
    16,
    19,
    23,
    24,
    25,
    27,
    28,
    29,
    30,
    32,
)
HOLDOUT_SOURCE_EPISODE_IDS = (33, 34)
EXPECTED_EXECUTION_RECORDS = 374
EXPECTED_VALIDATION_PATHS = 59
QPOS_ORDER = (
    "swing",
    "boom",
    "stick",
    "bucket",
)
SOURCE_QPOS_ORDER = (
    "swing_position_norm",
    "boom_position_norm",
    "stick_position_norm",
    "bucket_position_norm",
)
AB_SEQUENCE = (
    (0, "A"),
    (0, "B"),
    (1, "B"),
    (1, "A"),
    (2, "A"),
    (2, "B"),
)


class WallContactSemanticsExperimentError(RuntimeError):
    """Raised when diagnostic artifacts violate their frozen contract."""


def initialize_wall_contact_semantics_experiment(
    *,
    rollout_jsonl_path: str | Path,
    planner_trace_path: str | Path,
    target_episode_id: str,
    target_raw_fields_sha256: str,
    target_cycle_index: int,
    full_source_dir: str | Path,
    split_path: str | Path,
    dig_primitives_dir: str | Path,
    execution_library_path: str | Path,
    pose_library_path: str | Path,
    legacy_sweep_path: str | Path,
    unity_repo_root: str | Path,
    contact_monitor_code_paths: Sequence[str | Path],
    base_config_path: str | Path,
    output_root: str | Path,
) -> dict[str, Any]:
    """Create every new source lock and request under one no-overwrite root."""

    destination = Path(output_root).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite {destination}")
    destination.mkdir(parents=True, exist_ok=False)
    manifest_path = destination / "experiment_manifest.json"
    try:
        lineage = build_ab_lineage(
            rollout_jsonl_path=rollout_jsonl_path,
            planner_trace_path=planner_trace_path,
            target_episode_id=target_episode_id,
            target_raw_fields_sha256=target_raw_fields_sha256,
            target_cycle_index=target_cycle_index,
            output_dir=destination / "source_lock" / "ab_lineage",
        )
        source_spec_path = destination / "source_lock" / "source_spec.json"
        build_wall_contact_source_spec(
            full_source_dir=full_source_dir,
            split_path=split_path,
            dig_primitives_dir=dig_primitives_dir,
            execution_library_path=execution_library_path,
            pose_library_path=pose_library_path,
            legacy_sweep_path=legacy_sweep_path,
            unity_repo_root=unity_repo_root,
            contact_monitor_code_paths=contact_monitor_code_paths,
            frozen_target_handoff_path=lineage["frozen_target_handoff"]["path"],
            expected_reset_state_path=lineage["expected_reset_state"]["path"],
            output_path=source_spec_path,
        )
        return prepare_wall_contact_semantics_experiment(
            source_spec_path=source_spec_path,
            base_config_path=base_config_path,
            output_root=destination,
            _initialized_root=True,
        )
    except (
        ContactEvidenceContractError,
        FileNotFoundError,
        OSError,
        ValueError,
        WallContactABLineageError,
        WallContactArtifactError,
        WallContactConfigError,
        WallContactExperimentContractError,
        WallContactSemanticsExperimentError,
        WallContactSourceSpecError,
    ) as exc:
        manifest = {
            "schema": EXPERIMENT_SCHEMA,
            "status": "blocked",
            "primary_blocker": _prepare_blocker(exc),
            "blockers": [str(exc)],
            "diagnostic_only": True,
            "non_promotable": True,
            "production_promotion_allowed": False,
            "writes_training_hdf5": False,
            "manifest_path": str(manifest_path),
        }
        _write_json_x(manifest_path, manifest)
        return manifest


def build_wall_contact_source_spec(
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
) -> dict[str, Any]:
    """Create the frozen 18-source specification without running anything."""

    return _build_source_spec(
        full_source_dir=full_source_dir,
        split_path=split_path,
        dig_primitives_dir=dig_primitives_dir,
        execution_library_path=execution_library_path,
        pose_library_path=pose_library_path,
        legacy_sweep_path=legacy_sweep_path,
        unity_repo_root=unity_repo_root,
        contact_monitor_code_paths=contact_monitor_code_paths,
        frozen_target_handoff_path=frozen_target_handoff_path,
        expected_reset_state_path=expected_reset_state_path,
        output_path=output_path,
        source_episode_ids=(
            *TRAIN_SOURCE_EPISODE_IDS,
            *HOLDOUT_SOURCE_EPISODE_IDS,
        ),
        schema=SOURCE_SPEC_SCHEMA,
    )


def prepare_wall_contact_semantics_experiment(
    *,
    source_spec_path: str | Path,
    base_config_path: str | Path,
    output_root: str | Path,
    _initialized_root: bool = False,
) -> dict[str, Any]:
    """Prepare source locks, Unity requests, replay schedule, and six configs."""

    destination = Path(output_root).expanduser().resolve()
    if _initialized_root:
        if (
            not destination.is_dir()
            or (destination / "experiment_manifest.json").exists()
        ):
            raise FileExistsError(f"initialized root is not create-new:{destination}")
    else:
        if destination.exists():
            raise FileExistsError(f"refusing to overwrite {destination}")
        destination.mkdir(parents=True, exist_ok=False)
    manifest_path = destination / "experiment_manifest.json"
    try:
        spec_path = _required_file(source_spec_path, "source_spec")
        base_path = _required_file(base_config_path, "base_config")
        spec = _load_json(spec_path)
        if spec.get("schema") != SOURCE_SPEC_SCHEMA:
            raise WallContactSemanticsExperimentError("source_spec_schema_invalid")
        locked = _lock_sources(spec)
        base = _load_yaml(base_path)
        _validate_base_config(base)
        config_lock = _base_config_source_lock(
            base,
            base_config_path=base_path,
        )
        geometry_request = _geometry_request(
            locked=locked,
            destination=destination,
        )
        replay_schedule = _expert_replay_schedule(
            locked=locked,
            destination=destination,
        )
        configs, ab_schedule = _paired_ab_configs(
            base=base,
            locked=locked,
            destination=destination,
        )
        assert_paired_ab_single_factor(list(configs.values()))
        (destination / "expert_geometry").mkdir()
        (destination / "expert_replay").mkdir()
        (destination / "paired_ab" / "configs").mkdir(parents=True)
        _write_json_x(
            destination / "expert_geometry" / "request.json",
            geometry_request,
        )
        _write_json_x(
            destination / "expert_replay" / "schedule.json",
            replay_schedule,
        )
        for attempt_id, config in configs.items():
            path = destination / "paired_ab" / "configs" / f"{attempt_id}.yaml"
            _write_yaml_x(path, config)
        _write_json_x(
            destination / "paired_ab" / "schedule.json",
            ab_schedule,
        )
        manifest = {
            "schema": EXPERIMENT_SCHEMA,
            "status": "blocked",
            "primary_blocker": "contact_measurements_missing",
            "blockers": [
                "expert_geometry_measurement_missing",
                "expert_recorded_action_replay_missing",
                "paired_ab_attempts_missing",
            ],
            "diagnostic_only": True,
            "non_promotable": True,
            "production_promotion_allowed": False,
            "continuous_contract_change_allowed": False,
            "qpos_predictor_implementation_allowed": False,
            "production_live_allowed": False,
            "e0_g1_w1_live_allowed": False,
            "functional_1x10_allowed": False,
            "writes_training_hdf5": False,
            "source_semantics": {
                "recorded_env_state_dim": 89,
                "typed_contact_status": "typed_contact_fields_missing",
                "generic_collision_zero_interpretation": (
                    "not_proof_of_no_wall_contact"
                ),
                "reset_checkpoint_semantics": ("first_post_reset_control_step"),
            },
            "source_lock": locked["source_lock"],
            "source_lock_spec": _artifact_ref(spec_path),
            "config_lock": config_lock,
            "artifacts": {
                "expert_geometry_request": _artifact_ref(
                    destination / "expert_geometry" / "request.json"
                ),
                "expert_replay_schedule": _artifact_ref(
                    destination / "expert_replay" / "schedule.json"
                ),
                "paired_ab_schedule": _artifact_ref(
                    destination / "paired_ab" / "schedule.json"
                ),
            },
            "execution_contract": {
                "actual_executions_permitted_by_prepare": 0,
                "expert_replay_attempts": len(replay_schedule["attempts"]),
                "expert_replay_retry_allowed": False,
                "paired_ab_attempts": len(ab_schedule["attempts"]),
                "paired_ab_retry_allowed": False,
                "paired_ab_order": [
                    f"{seed}:{condition}" for seed, condition in AB_SEQUENCE
                ],
                "production_commands_included": False,
            },
            "next_steps": [
                "run Unity expert geometry adapter against request",
                "run each expert recorded-action replay exactly once",
                "collect geometry and replay measurements",
                "run paired A/B schedule exactly once per attempt",
                "collect attempts and finalize diagnostic report",
                "pause for human contact-budget review",
            ],
            "manifest_path": str(manifest_path),
        }
    except (
        ContactEvidenceContractError,
        FileNotFoundError,
        OSError,
        ValueError,
        WallContactArtifactError,
        WallContactConfigError,
        WallContactExperimentContractError,
        WallContactSemanticsExperimentError,
        WallContactSourceSpecError,
    ) as exc:
        manifest = {
            "schema": EXPERIMENT_SCHEMA,
            "status": "blocked",
            "primary_blocker": _prepare_blocker(exc),
            "blockers": [str(exc)],
            "diagnostic_only": True,
            "non_promotable": True,
            "production_promotion_allowed": False,
            "continuous_contract_change_allowed": False,
            "qpos_predictor_implementation_allowed": False,
            "production_live_allowed": False,
            "e0_g1_w1_live_allowed": False,
            "functional_1x10_allowed": False,
            "writes_training_hdf5": False,
            "manifest_path": str(manifest_path),
        }
    _write_json_x(manifest_path, manifest)
    return manifest


def collect_expert_geometry_evidence(
    *,
    experiment_manifest_path: str | Path,
    measurement_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    """Validate one create-new Unity geometry measurement."""

    manifest, request = _prepared_manifest_and_artifact(
        experiment_manifest_path,
        "expert_geometry_request",
    )
    measurement_source = _required_file(
        measurement_path,
        "geometry_measurement",
    )
    measurement = _load_json(measurement_source)
    blockers: list[str] = []
    rows: list[dict[str, Any]] = []
    try:
        _validate_geometry_measurement_top(measurement, request)
        expected = {str(item["path_id"]): item for item in request["paths"]}
        measured = _unique_records(
            measurement.get("paths"),
            key="path_id",
            label="geometry paths",
        )
        if set(measured) != set(expected):
            raise WallContactSemanticsExperimentError(
                "geometry_path_inventory_incomplete"
            )
        for path_id in sorted(expected):
            rows.append(
                _validate_geometry_path(
                    expected=expected[path_id],
                    measured=measured[path_id],
                )
            )
    except (
        ContactEvidenceContractError,
        ValueError,
        WallContactArtifactError,
        WallContactConfigError,
        WallContactExperimentContractError,
        WallContactSemanticsExperimentError,
    ) as exc:
        blockers.append(str(exc))
    artifact = {
        "schema": "expert_worktool_contact_sweep_collection_v1",
        "status": "passed" if not blockers else "blocked",
        "blockers": blockers,
        "diagnostic_only": True,
        "non_promotable": True,
        "production_promotion_allowed": False,
        "paths": rows,
        "summary": summarize_geometry_paths(rows),
        "source_lock": {
            "experiment_manifest": _artifact_ref(
                Path(experiment_manifest_path).resolve()
            ),
            "request": manifest["artifacts"]["expert_geometry_request"],
            "measurement": _artifact_ref(measurement_source),
        },
    }
    _write_json_x(Path(output_path).expanduser().resolve(), artifact)
    return artifact


def collect_expert_replay_evidence(
    *,
    experiment_manifest_path: str | Path,
    measurement_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    """Validate the exactly-once 18-source recorded-action replay."""

    manifest, schedule = _prepared_manifest_and_artifact(
        experiment_manifest_path,
        "expert_replay_schedule",
    )
    measurement_source = _required_file(
        measurement_path,
        "expert_replay_measurement",
    )
    measurement = _load_json(measurement_source)
    blockers: list[str] = []
    records: list[dict[str, Any]] = []
    if measurement.get("schema") != EXPERT_REPLAY_MEASUREMENT_SCHEMA:
        blockers.append("expert_replay_measurement_schema_invalid")
    else:
        expected = {
            int(item["source_episode_id"]): item for item in schedule["attempts"]
        }
        try:
            measured = _unique_records(
                measurement.get("sources"),
                key="source_episode_id",
                label="expert replay sources",
                integer_key=True,
            )
            if set(measured) != set(expected):
                raise WallContactSemanticsExperimentError(
                    "expert_replay_source_inventory_incomplete"
                )
            for source_id in sorted(expected):
                row = _validate_expert_replay_source(
                    expected=expected[source_id],
                    measured=measured[source_id],
                )
                records.append(row)
                blockers.extend(row["blockers"])
        except (
            ContactEvidenceContractError,
            ValueError,
            WallContactArtifactError,
            WallContactConfigError,
            WallContactExperimentContractError,
            WallContactSemanticsExperimentError,
        ) as exc:
            blockers.append(str(exc))
    train = [item for item in records if item.get("split") == "train"]
    holdout = [item for item in records if item.get("split") == "validation"]
    artifact = {
        "schema": "expert_recorded_action_contact_replay_collection_v1",
        "status": "passed" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
        "diagnostic_only": True,
        "non_promotable": True,
        "production_promotion_allowed": False,
        "training_inference": {
            "source_count": len(train),
            "summaries": train,
        },
        "holdout_evidence": {
            "source_count": len(holdout),
            "used_for_region_or_budget_selection": False,
            "summaries": holdout,
        },
        "typed_contact_lineage_complete": not blockers,
        "summary": summarize_expert_replay_records(records),
        "source_lock": {
            "experiment_manifest": _artifact_ref(
                Path(experiment_manifest_path).resolve()
            ),
            "schedule": manifest["artifacts"]["expert_replay_schedule"],
            "measurement": _artifact_ref(measurement_source),
        },
    }
    _write_json_x(Path(output_path).expanduser().resolve(), artifact)
    return artifact


def collect_paired_ab_evidence(
    *,
    experiment_manifest_path: str | Path,
    attempt_set_path: str | Path,
    output_path: str | Path,
    expert_replay_collection_path: str | Path | None = None,
) -> dict[str, Any]:
    """Validate six exactly-once attempts and apply reset fairness per pair."""

    manifest, schedule = _prepared_manifest_and_artifact(
        experiment_manifest_path,
        "paired_ab_schedule",
    )
    attempt_source = _required_file(attempt_set_path, "attempt_set")
    attempt_set = _load_json(attempt_source)
    blockers: list[str] = []
    attempts_out: list[dict[str, Any]] = []
    invalid_pairs: list[str] = []
    if attempt_set.get("schema") != AB_ATTEMPT_SET_SCHEMA:
        blockers.append("paired_ab_attempt_set_schema_invalid")
    if attempt_set.get("status") != "passed":
        blockers.append("paired_ab_attempt_execution_failed")
    expected = {str(item["attempt_id"]): item for item in schedule["attempts"]}
    try:
        measured = _unique_records(
            attempt_set.get("attempts"),
            key="attempt_id",
            label="paired A/B attempts",
        )
        if set(measured) != set(expected):
            raise WallContactSemanticsExperimentError(
                "paired_ab_attempt_inventory_incomplete"
            )
        if any(int(measured[key].get("retry_count", -1)) != 0 for key in expected):
            raise WallContactSemanticsExperimentError("paired_ab_retry_forbidden")
        if any(measured[key].get("status") != "passed" for key in expected):
            blockers.append("paired_ab_attempt_execution_failed")
        reset_reference = _load_locked_ref(
            manifest["source_lock"]["expected_reset_state"]
        )
        for seed in (0, 1, 2):
            pair_id = f"seed_{seed}"
            a = next(
                measured[item["attempt_id"]]
                for item in schedule["attempts"]
                if item["pair_id"] == pair_id and item["condition"] == "A"
            )
            b = next(
                measured[item["attempt_id"]]
                for item in schedule["attempts"]
                if item["pair_id"] == pair_id and item["condition"] == "B"
            )
            fairness = validate_reset_pair(
                expected_reset_state=reset_reference,
                reset_a=_mapping(a.get("reset_state"), "reset_state"),
                reset_b=_mapping(b.get("reset_state"), "reset_state"),
            )
            if not fairness["valid"]:
                invalid_pairs.append(pair_id)
            for raw in (a, b):
                attempts_out.append(
                    _validate_ab_attempt(
                        raw=raw,
                        expected=expected[str(raw["attempt_id"])],
                        pair_valid=bool(fairness["valid"]),
                        fairness=fairness,
                        target=manifest["source_lock"]["frozen_target_handoff"],
                    )
                )
    except (
        ContactEvidenceContractError,
        KeyError,
        StopIteration,
        ValueError,
        WallContactArtifactError,
        WallContactConfigError,
        WallContactExperimentContractError,
        WallContactSemanticsExperimentError,
    ) as exc:
        blockers.append(str(exc))
    if invalid_pairs:
        blockers.append("reset_fairness_invalid_no_retry")
    attempts_out.sort(key=lambda item: int(item["sequence_index"]))
    expert_lineage_complete = False
    same_region = False
    expert_ref: dict[str, Any] | None = None
    if expert_replay_collection_path is not None:
        expert_path = _required_file(
            expert_replay_collection_path,
            "expert_replay_collection",
        )
        expert_ref = _artifact_ref(expert_path)
        expert = _load_json(expert_path)
        training = _mapping(
            expert.get("training_inference"),
            "training_inference",
        )
        summaries = training.get("summaries")
        expert_lineage_complete = (
            expert.get("schema")
            == "expert_recorded_action_contact_replay_collection_v1"
            and expert.get("status") == "passed"
            and expert.get("typed_contact_lineage_complete") is True
            and isinstance(summaries, list)
        )
        if expert_lineage_complete:
            same_region = expert_same_region_sub_100kn(
                attempts=attempts_out,
                train_source_summaries=summaries,
            )
        else:
            blockers.append("expert_replay_lineage_invalid")
    decision = causal_classification(
        attempts=attempts_out,
        expert_same_region_sub_100kn=same_region,
        expert_lineage_complete=expert_lineage_complete,
    )
    artifact = {
        "schema": AB_COLLECTION_SCHEMA,
        "status": "passed" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
        "invalid_pair_ids": sorted(invalid_pairs),
        "causal_classification": decision,
        "attempts": attempts_out,
        "diagnostic_only": True,
        "non_promotable": True,
        "production_promotion_allowed": False,
        "retry_allowed": False,
        "expert_same_region_sub_100kn": same_region,
        "expert_lineage_complete": expert_lineage_complete,
        "diagnostic_region_match_radius_m": 0.05,
        "summary": summarize_paired_ab_attempts(attempts_out),
        "source_lock": {
            "experiment_manifest": _artifact_ref(
                Path(experiment_manifest_path).resolve()
            ),
            "schedule": manifest["artifacts"]["paired_ab_schedule"],
            "attempt_set": _artifact_ref(attempt_source),
            **(
                {"expert_replay_collection": expert_ref}
                if expert_ref is not None
                else {}
            ),
        },
    }
    _write_json_x(Path(output_path).expanduser().resolve(), artifact)
    return artifact


def finalize_wall_contact_semantics_experiment(
    *,
    experiment_manifest_path: str | Path,
    geometry_collection_path: str | Path,
    expert_replay_collection_path: str | Path,
    paired_ab_collection_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Create the causal report and stop at the human contract-freeze gate."""

    manifest = _load_json(
        _required_file(experiment_manifest_path, "experiment_manifest")
    )
    if manifest.get("schema") != EXPERIMENT_SCHEMA:
        raise WallContactSemanticsExperimentError("experiment_manifest_schema_invalid")
    _validate_base_config_source_lock(
        _mapping(manifest.get("config_lock"), "config_lock")
    )
    _verify_python_source_lineage(manifest)
    geometry_path = _required_file(
        geometry_collection_path,
        "geometry_collection",
    )
    replay_path = _required_file(
        expert_replay_collection_path,
        "expert_replay_collection",
    )
    ab_path = _required_file(paired_ab_collection_path, "paired_ab_collection")
    geometry = _load_json(geometry_path)
    replay = _load_json(replay_path)
    ab = _load_json(ab_path)
    blockers = [
        label
        for label, artifact in (
            ("expert_geometry_blocked", geometry),
            ("expert_replay_blocked", replay),
            ("paired_ab_blocked", ab),
        )
        if artifact.get("status") != "passed"
    ]
    classification = (
        str(ab.get("causal_classification", "inconclusive"))
        if not blockers
        else "inconclusive"
    )
    report_sections = build_causal_report_sections(
        geometry_collection=geometry,
        expert_replay_collection=replay,
        paired_ab_collection=ab,
        classification=classification,
        blockers=blockers,
    )
    report = {
        "schema": FINAL_REPORT_SCHEMA,
        "status": "passed" if not blockers else "blocked",
        "blockers": blockers,
        "causal_classification": classification,
        "human_contact_budget_review_required": True,
        "continuous_contact_contract_frozen": False,
        "diagnostic_only": True,
        "non_promotable": True,
        "production_promotion_allowed": False,
        "qpos_predictor_implementation_allowed": False,
        "e0_g1_w1_live_allowed": False,
        "functional_1x10_allowed": False,
        "writes_training_hdf5": False,
        "next_gate": (
            "human_freeze_bucket_contact_region_force_duration_impulse_budget"
        ),
        **report_sections,
        "config_lock": manifest["config_lock"],
        "source_lock": {
            "experiment_manifest": _artifact_ref(
                Path(experiment_manifest_path).resolve()
            ),
            "expert_geometry": _artifact_ref(geometry_path),
            "expert_replay": _artifact_ref(replay_path),
            "paired_ab": _artifact_ref(ab_path),
        },
    }
    destination = Path(output_dir).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite {destination}")
    destination.mkdir(parents=True, exist_ok=False)
    _write_json_x(destination / "causal_report.json", report)
    (destination / "report.md").write_text(
        render_causal_report_markdown(report),
        encoding="utf-8",
    )
    return report


def assert_paired_ab_single_factor(
    configs: Sequence[Mapping[str, Any]],
) -> None:
    """Require A/B equality inside each seed pair except frozen paths."""

    if len(configs) != 6:
        raise WallContactSemanticsExperimentError("paired_ab_config_count_invalid")
    by_pair: dict[str, list[Mapping[str, Any]]] = {}
    for config in configs:
        metadata = _mapping(
            _mapping(config.get("eval"), "eval").get("record_hdf5_metadata"),
            "record_hdf5_metadata",
        )
        pair_id = str(metadata.get("contact_semantics_pair_id", ""))
        by_pair.setdefault(pair_id, []).append(config)
    if set(by_pair) != {"seed_0", "seed_1", "seed_2"}:
        raise WallContactSemanticsExperimentError("paired_ab_pair_inventory_invalid")
    for pair_id, pair in by_pair.items():
        if len(pair) != 2:
            raise WallContactSemanticsExperimentError(
                f"paired_ab_pair_size_invalid:{pair_id}"
            )
        left = _normalized_ab_config(pair[0])
        right = _normalized_ab_config(pair[1])
        if left != right:
            raise WallContactSemanticsExperimentError(
                f"paired_ab_single_factor_drift:{pair_id}"
            )
    invariant_fields = [_locked_config_contract(config) for config in configs]
    if any(item != invariant_fields[0] for item in invariant_fields[1:]):
        raise WallContactSemanticsExperimentError("paired_ab_locked_contract_drift")


def _lock_sources(spec: Mapping[str, Any]) -> dict[str, Any]:
    return _support_lock_sources(
        spec,
        train_source_ids=TRAIN_SOURCE_EPISODE_IDS,
        holdout_source_ids=HOLDOUT_SOURCE_EPISODE_IDS,
        expected_execution_records=EXPECTED_EXECUTION_RECORDS,
        expected_validation_paths=EXPECTED_VALIDATION_PATHS,
        qpos_order=SOURCE_QPOS_ORDER,
    )


def _geometry_request(
    *,
    locked: Mapping[str, Any],
    destination: Path,
) -> dict[str, Any]:
    return _support_geometry_request(
        locked=locked,
        destination=destination,
        schema=GEOMETRY_INPUT_SCHEMA,
        qpos_order=QPOS_ORDER,
    )


def _expert_replay_schedule(
    *,
    locked: Mapping[str, Any],
    destination: Path,
) -> dict[str, Any]:
    return _support_expert_replay_schedule(
        locked=locked,
        destination=destination,
        schema=EXPERT_REPLAY_SCHEDULE_SCHEMA,
    )


def _paired_ab_configs(
    *,
    base: Mapping[str, Any],
    locked: Mapping[str, Any],
    destination: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    return _support_paired_ab_configs(
        base=base,
        locked=locked,
        destination=destination,
        sequence=AB_SEQUENCE,
        schedule_schema=AB_SCHEDULE_SCHEMA,
    )


def _validate_geometry_measurement_top(
    measurement: Mapping[str, Any],
    request: Mapping[str, Any],
) -> None:
    _support_validate_geometry_measurement_top(
        measurement,
        request,
        schema=GEOMETRY_MEASUREMENT_SCHEMA,
    )


def _prepared_manifest_and_artifact(
    manifest_path: str | Path,
    artifact_key: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    path = _required_file(manifest_path, "experiment_manifest")
    manifest = _load_json(path)
    if manifest.get("schema") != EXPERIMENT_SCHEMA:
        raise WallContactSemanticsExperimentError("experiment_manifest_schema_invalid")
    _validate_base_config_source_lock(
        _mapping(manifest.get("config_lock"), "config_lock")
    )
    _verify_python_source_lineage(manifest)
    artifacts = _mapping(manifest.get("artifacts"), "artifacts")
    reference = _mapping(artifacts.get(artifact_key), artifact_key)
    return manifest, _load_locked_ref(reference)


def _verify_python_source_lineage(manifest: Mapping[str, Any]) -> None:
    source = _mapping(manifest.get("source_lock"), "source_lock")
    _lock_python_source_lineage(
        _mapping(source.get("python"), "source_lock.python")
    )


def _prepare_blocker(exc: Exception) -> str:
    text = str(exc).lower()
    if any(
        marker in text
        for marker in (
            "sha256",
            "source_",
            "split_",
            "library_",
            "scene_",
            "contact_lineage",
            "python_lineage",
        )
    ):
        return "source_artifact_drift"
    if any(marker in text for marker in ("base_", "checkpoint", "camera", "temporal")):
        return "a0_contract_drift"
    return "contact_evidence_contract_invalid"


__all__ = [
    "AB_ATTEMPT_SCHEMA",
    "AB_SEQUENCE",
    "EXPERIMENT_SCHEMA",
    "WallContactSemanticsExperimentError",
    "assert_paired_ab_single_factor",
    "build_wall_contact_source_spec",
    "collect_expert_geometry_evidence",
    "collect_expert_replay_evidence",
    "collect_paired_ab_evidence",
    "finalize_wall_contact_semantics_experiment",
    "initialize_wall_contact_semantics_experiment",
    "prepare_wall_contact_semantics_experiment",
]
