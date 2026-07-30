"""Fail-closed offline owner for goal-conditioned recovery evidence."""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from testbed.eval import goal_conditioned_recovery_contracts as _contracts

ACT_TRACKING_MARGIN_M = _contracts.ACT_TRACKING_MARGIN_M
HARD_CLEARANCE_M = _contracts.HARD_CLEARANCE_M
POSE_INTERPOLATION_BOUND_M = _contracts.POSE_INTERPOLATION_BOUND_M
ExperimentContractError = _contracts.ExperimentContractError
canonical_goal_id = _contracts.canonical_goal_id
_a0_contract = _contracts.a0_contract
_assert_config_mappings = _contracts.assert_single_factor_config_mappings
_integer = _contracts.integer
_is_sha256 = _contracts.is_sha256
_load_json_mapping = _contracts.load_json_mapping
_load_yaml_mapping = _contracts.load_yaml_mapping
_mapping = _contracts.mapping
_pretty_json_bytes = _contracts.pretty_json_bytes
_require_file = _contracts.require_file
_sequence = _contracts.sequence
_sha256 = _contracts.sha256
_source_record = _contracts.source_record
_validate_goal = _contracts.validate_goal
_validate_live_record = _contracts.validate_live_record
_validate_predictor_record = _contracts.validate_predictor_record
_validate_return_envelope = _contracts.validate_return_envelope
_validate_support_diagnostic = _contracts.validate_support_diagnostic
_verify_a0_contract_sources = _contracts.verify_a0_contract_sources
_verify_file_sha = _contracts.verify_file_sha
_verify_source_lock = _contracts.verify_source_lock
_write_json_exclusive = _contracts.write_json_exclusive

EXPERIMENT_SCHEMA = "goal_conditioned_runtime_recovery_v1"
CONDITION_SET_SCHEMA = "goal_conditioned_three_way_condition_set_v1"
OFFLINE_RECORD_SCHEMA = "goal_conditioned_offline_preflight_record_v1"
EVIDENCE_MATRIX_SCHEMA = "goal_conditioned_three_way_evidence_matrix_v1"
CAUSAL_DECISION_SCHEMA = "goal_conditioned_three_way_causal_decision_v1"
FUNCTIONAL_CONFIG_SCHEMA = "goal_conditioned_functional_10cycle_config_v1"
FUNCTIONAL_RECORD_SCHEMA = "goal_conditioned_functional_10cycle_record_v1"
FUNCTIONAL_VALIDATION_SCHEMA = (
    "goal_conditioned_functional_10cycle_validation_v1"
)
PREDICTOR_MANIFEST_SCHEMA = (
    "continuous_goal_qpos_sweep_predictor_manifest_v1"
)
CONDITION_IDS = (
    "E0_expert_goal",
    "G1_planner_continuous_goal",
    "W1_internal_wall_safe_goal",
)
_BLOCKER_PRIORITY = (
    "source_artifact_drift",
    "a0_contract_drift",
    "continuous_goal_contract_invalid",
    "return_envelope_contract_invalid",
    "continuous_goal_3d_predictor_missing",
    "continuous_goal_unsafe_3d",
)
_CONDITION_SOURCE_KINDS = {
    "E0_expert_goal": "expert_goal_control",
    "G1_planner_continuous_goal": "planner_continuous_goal",
    "W1_internal_wall_safe_goal": "internal_wall_safe_goal",
}


def build_goal_conditioned_recovery_preflight(
    *,
    base_config_path: str | Path,
    condition_set_path: str | Path,
    output_root: str | Path,
    predictor_manifest_path: str | Path | None = None,
    exact_diagnostic_artifact_path: str | Path | None = None,
    exact_diagnostic_artifact_sha256: str | None = None,
) -> dict[str, Any]:
    """Build the no-overwrite three-way offline preflight root.

    This function only prepares files.  In particular, a passing preflight does
    not run the three-way live probe and can never unlock the functional 1x10 by
    itself.
    """

    destination = Path(output_root).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"experiment output already exists: {destination}")
    base_path = _require_file(base_config_path)
    condition_path = _require_file(condition_set_path)
    base = _load_yaml_mapping(base_path)
    a0_contract = _a0_contract(base)
    condition_set = _load_json_mapping(condition_path)
    if condition_set.get("schema") != CONDITION_SET_SCHEMA:
        raise ExperimentContractError("condition_set_schema_invalid")
    raw_conditions = _mapping(
        condition_set.get("conditions"),
        "condition_set.conditions",
    )
    if set(raw_conditions) != set(CONDITION_IDS):
        raise ExperimentContractError("condition_inventory_invalid")

    predictor_path: Path | None = None
    predictor_conditions: Mapping[str, Any] | None = None
    if predictor_manifest_path is not None:
        predictor_path = _require_file(predictor_manifest_path)
        predictor = _load_json_mapping(predictor_path)
        if predictor.get("schema") != PREDICTOR_MANIFEST_SCHEMA:
            raise ExperimentContractError("predictor_manifest_schema_invalid")
        predictor_conditions = _mapping(
            predictor.get("conditions"),
            "predictor_manifest.conditions",
        )
        if set(predictor_conditions) != set(CONDITION_IDS):
            raise ExperimentContractError("predictor_condition_inventory_invalid")

    exact_diagnostic = _optional_exact_diagnostic(
        exact_diagnostic_artifact_path,
        exact_diagnostic_artifact_sha256,
    )
    serialized_goals: dict[str, bytes] = {}
    offline_records: dict[str, dict[str, Any]] = {}
    for condition_id in CONDITION_IDS:
        condition = _mapping(
            raw_conditions[condition_id],
            f"conditions.{condition_id}",
        )
        runtime_goal_artifact = _runtime_goal_artifact(
            condition_id=condition_id,
            condition=condition,
        )
        serialized_goals[condition_id] = _pretty_json_bytes(
            runtime_goal_artifact
        )
        offline_records[condition_id] = _offline_record(
            condition_id=condition_id,
            condition=condition,
            predictor_record=(
                None
                if predictor_conditions is None
                else predictor_conditions.get(condition_id)
            ),
        )

    overall_status = _overall_offline_status(offline_records.values())
    primary_blocker = _primary_blocker(offline_records.values())
    source_lock = {
        "base_config": _source_record(base_path),
        "condition_set": _source_record(condition_path),
    }
    if predictor_path is not None:
        source_lock["predictor_manifest"] = _source_record(predictor_path)

    configs: dict[str, dict[str, Any]] = {}
    config_bytes: dict[str, bytes] = {}
    for condition_id in CONDITION_IDS:
        goal_path = destination / "goals" / f"{condition_id}.json"
        config = _condition_config(
            base=base,
            condition_id=condition_id,
            output_root=destination,
            goal_path=goal_path,
            goal_sha256=hashlib.sha256(
                serialized_goals[condition_id]
            ).hexdigest(),
            a0_contract_sha256=a0_contract["contract_sha256"],
        )
        configs[condition_id] = config
        config_bytes[condition_id] = yaml.safe_dump(
            config,
            sort_keys=False,
        ).encode("utf-8")
    _assert_single_factor_config_mappings(configs)

    condition_entries: dict[str, dict[str, Any]] = {}
    for condition_id in CONDITION_IDS:
        config_path = destination / "configs" / f"{condition_id}.yaml"
        goal_path = destination / "goals" / f"{condition_id}.json"
        offline_path = destination / "offline" / f"{condition_id}.json"
        condition_entries[condition_id] = {
            "source_kind": _CONDITION_SOURCE_KINDS[condition_id],
            "config_path": str(config_path),
            "config_sha256": hashlib.sha256(
                config_bytes[condition_id]
            ).hexdigest(),
            "goal_artifact_path": str(goal_path),
            "goal_artifact_sha256": hashlib.sha256(
                serialized_goals[condition_id]
            ).hexdigest(),
            "offline_record_path": str(offline_path),
            "offline_record_sha256": hashlib.sha256(
                _pretty_json_bytes(offline_records[condition_id])
            ).hexdigest(),
        }

    manifest_path = destination / "experiment_manifest.json"
    manifest: dict[str, Any] = {
        "schema": EXPERIMENT_SCHEMA,
        "status": overall_status,
        "offline_only": True,
        "closed_loop_claim": False,
        "live_allowed": overall_status == "passed",
        "functional_1x10_allowed": False,
        "primary_blocker": primary_blocker,
        "condition_order": list(CONDITION_IDS),
        "a0_contract": a0_contract,
        "safety_margins": {
            "act_tracking_margin_m": ACT_TRACKING_MARGIN_M,
            "pose_interpolation_bound_m": POSE_INTERPOLATION_BOUND_M,
            "hard_clearance_m": HARD_CLEARANCE_M,
            "owner": "python",
        },
        "reset_fairness": {
            "qpos_max_abs_delta": 0.005,
            "qvel_abs_max": 0.10,
            "qvel_cross_condition_max_abs_delta": 0.02,
            "bucket_tip_max_displacement_m": 0.02,
            "terrain_depth_max_abs_delta_m": 0.002,
            "remaining_mass_max_abs_delta_kg": 5.0,
            "out_of_contract_disposition": "invalid_no_retry",
        },
        "exact_diagnostic_artifact": exact_diagnostic,
        "exact_artifact_required_for_continuous_mode": False,
        "source_lock": source_lock,
        "conditions": condition_entries,
        "manifest_path": str(manifest_path),
    }
    offline_matrix = _evidence_matrix(
        manifest=manifest,
        offline_records=offline_records,
        live_records=None,
    )
    offline_decision = _causal_decision(
        manifest=manifest,
        offline_records=offline_records,
        live_records=None,
        experiment_manifest_path=manifest_path,
        experiment_manifest_sha256=None,
    )
    report = _report_text(
        manifest=manifest,
        decision=offline_decision,
    )

    destination.mkdir(parents=True, exist_ok=False)
    (destination / "configs").mkdir()
    (destination / "goals").mkdir()
    (destination / "offline").mkdir()
    (destination / "evidence").mkdir()
    for condition_id in CONDITION_IDS:
        (destination / "goals" / f"{condition_id}.json").write_bytes(
            serialized_goals[condition_id]
        )
        (destination / "configs" / f"{condition_id}.yaml").write_bytes(
            config_bytes[condition_id]
        )
        _write_json_exclusive(
            destination / "offline" / f"{condition_id}.json",
            offline_records[condition_id],
        )
        provenance = _mapping(
            raw_conditions[condition_id],
            f"conditions.{condition_id}",
        ).get("provenance")
        if provenance is not None:
            provenance_dir = destination / "provenance"
            provenance_dir.mkdir(exist_ok=True)
            _write_json_exclusive(
                provenance_dir / f"{condition_id}.json",
                {
                    "schema": "goal_condition_provenance_v1",
                    "condition_id": condition_id,
                    "runtime_lookup_allowed": False,
                    "provenance": provenance,
                },
            )
    _write_json_exclusive(manifest_path, manifest)
    _write_json_exclusive(
        destination / "evidence" / "offline_evidence_matrix.json",
        offline_matrix,
    )
    _write_json_exclusive(
        destination / "evidence" / "offline_causal_decision.json",
        offline_decision,
    )
    (destination / "offline_preflight_report.md").write_text(
        report,
        encoding="utf-8",
    )
    return manifest


def assert_three_way_single_factor_configs(
    config_paths: Mapping[str, str | Path],
) -> None:
    """Reject any drift beyond the frozen three condition-specific fields."""

    if set(config_paths) != set(CONDITION_IDS):
        raise ExperimentContractError("condition_config_inventory_invalid")
    configs = {
        condition_id: _load_yaml_mapping(_require_file(config_paths[condition_id]))
        for condition_id in CONDITION_IDS
    }
    _assert_single_factor_config_mappings(configs)


def collect_goal_conditioned_recovery_evidence(
    *,
    experiment_manifest_path: str | Path,
    live_record_paths: Mapping[str, str | Path] | None,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Collect pre-existing evidence and issue the frozen causal decision."""

    output = Path(output_dir).expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"evidence output already exists: {output}")
    manifest_path = _require_file(experiment_manifest_path)
    manifest = _load_json_mapping(manifest_path)
    if manifest.get("schema") != EXPERIMENT_SCHEMA:
        raise ExperimentContractError("experiment_manifest_schema_invalid")
    _verify_source_lock(_mapping(manifest.get("source_lock"), "source_lock"))
    _verify_a0_contract_sources(
        _mapping(manifest.get("a0_contract"), "a0_contract")
    )
    condition_entries = _mapping(
        manifest.get("conditions"),
        "manifest.conditions",
    )
    offline_records: dict[str, dict[str, Any]] = {}
    for condition_id in CONDITION_IDS:
        entry = _mapping(
            condition_entries.get(condition_id),
            f"manifest.conditions.{condition_id}",
        )
        for label, path_key, sha_key in (
            ("config", "config_path", "config_sha256"),
            ("goal", "goal_artifact_path", "goal_artifact_sha256"),
            (
                "offline",
                "offline_record_path",
                "offline_record_sha256",
            ),
        ):
            _verify_file_sha(
                entry.get(path_key),
                entry.get(sha_key),
                label=f"{condition_id}.{label}",
            )
        offline_records[condition_id] = _load_json_mapping(
            _require_file(entry["offline_record_path"])
        )

    live_records: dict[str, dict[str, Any]] | None = None
    if live_record_paths is not None:
        if not bool(manifest.get("live_allowed")):
            raise ExperimentContractError(
                "live_not_allowed_by_offline_preflight"
            )
        if set(live_record_paths) != set(CONDITION_IDS):
            raise ExperimentContractError("live_record_inventory_invalid")
        live_records = {}
        for condition_id in CONDITION_IDS:
            record_path = _require_file(live_record_paths[condition_id])
            record = _load_json_mapping(record_path)
            _validate_live_record(
                record,
                condition_id=condition_id,
                expected_sequence_index=CONDITION_IDS.index(condition_id) + 1,
            )
            live_records[condition_id] = {
                **record,
                "source_path": str(record_path),
                "source_sha256": _sha256(record_path),
            }

    manifest_sha = _sha256(manifest_path)
    matrix = _evidence_matrix(
        manifest=manifest,
        offline_records=offline_records,
        live_records=live_records,
    )
    decision = _causal_decision(
        manifest=manifest,
        offline_records=offline_records,
        live_records=live_records,
        experiment_manifest_path=manifest_path,
        experiment_manifest_sha256=manifest_sha,
    )
    report = _report_text(manifest=manifest, decision=decision)
    output.mkdir(parents=True, exist_ok=False)
    _write_json_exclusive(output / "evidence_matrix.json", matrix)
    _write_json_exclusive(output / "causal_decision.json", decision)
    (output / "report.md").write_text(report, encoding="utf-8")
    return {
        "evidence_matrix": matrix,
        "causal_decision": decision,
    }


def build_goal_conditioned_functional_config(
    *,
    causal_decision_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Build one G1 A0 1x10 config only after all three probes pass."""

    output = Path(output_dir).expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"functional output already exists: {output}")
    decision_path = _require_file(causal_decision_path)
    decision = _load_json_mapping(decision_path)
    if decision.get("schema") != CAUSAL_DECISION_SCHEMA:
        raise ExperimentContractError("causal_decision_schema_invalid")
    if not bool(decision.get("functional_1x10_allowed")):
        raise ExperimentContractError("functional_1x10_not_allowed")
    manifest_path = _require_file(decision.get("experiment_manifest_path"))
    _verify_file_sha(
        manifest_path,
        decision.get("experiment_manifest_sha256"),
        label="experiment_manifest",
    )
    manifest = _load_json_mapping(manifest_path)
    _verify_a0_contract_sources(
        _mapping(manifest.get("a0_contract"), "a0_contract")
    )
    condition_entries = _mapping(
        manifest.get("conditions"),
        "manifest.conditions",
    )
    g1_entry = _mapping(
        condition_entries.get("G1_planner_continuous_goal"),
        "G1 condition",
    )
    g1_config_path = _require_file(g1_entry.get("config_path"))
    _verify_file_sha(
        g1_config_path,
        g1_entry.get("config_sha256"),
        label="G1 config",
    )
    config = copy.deepcopy(_load_yaml_mapping(g1_config_path))
    evaluation = _mapping(config.get("eval"), "config.eval")
    evaluation["num_rollouts"] = 1
    evaluation["no_overwrite"] = True
    evaluation["results_dir"] = str(output / "results")
    evaluation["video_dir"] = str(output / "videos")
    evaluation["rollout_log_dir"] = str(output / "results" / "rollouts")
    evaluation["hdf5_dir"] = str(
        output / "results" / "hdf5_rollouts"
    )
    metadata = _mapping(
        evaluation.setdefault("record_hdf5_metadata", {}),
        "eval.record_hdf5_metadata",
    )
    metadata["validation_schema"] = FUNCTIONAL_VALIDATION_SCHEMA
    metadata["experiment_mode"] = "goal_conditioned_functional_1x10"
    metadata.pop("condition_id", None)
    metadata.pop("goal_source_kind", None)
    planner = _mapping(
        _mapping(config.get("policy"), "config.policy").get(
            "dig_cut_planner"
        ),
        "policy.dig_cut_planner",
    )
    planner["mode"] = "continuous_goal_conditioned"
    planner["fallback_mode"] = "raise"
    planner["hold_token_until_skill_exit"] = True
    continuous = _mapping(
        planner.setdefault("continuous_goal_conditioned", {}),
        "continuous_goal_conditioned",
    )
    continuous["source"] = {"kind": "planner_continuous_goal"}
    box = _mapping(
        _mapping(config.get("policy"), "config.policy").get("box_emptying"),
        "policy.box_emptying",
    )
    box["functional_cycle_gate"] = {
        "enabled": True,
        "target_cycles": 10,
        "max_bucket_mass_kg": 15.0,
    }
    config_path = output / "goal_conditioned_a0_1x10.yaml"
    config_payload = yaml.safe_dump(config, sort_keys=False).encode("utf-8")
    artifact = {
        "schema": FUNCTIONAL_CONFIG_SCHEMA,
        "status": "built_not_run",
        "live_run_started": False,
        "single_run_only": True,
        "automatic_retry_allowed": False,
        "condition": "G1_planner_continuous_goal",
        "config_path": str(config_path),
        "config_sha256": hashlib.sha256(config_payload).hexdigest(),
        "causal_decision_path": str(decision_path),
        "causal_decision_sha256": _sha256(decision_path),
        "a0_contract_sha256": _mapping(
            manifest.get("a0_contract"),
            "manifest.a0_contract",
        ).get("contract_sha256"),
        "formal_bundle_allowed": False,
        "functional_3x10_allowed": False,
    }
    output.mkdir(parents=True, exist_ok=False)
    config_path.write_bytes(config_payload)
    _write_json_exclusive(output / "manifest.json", artifact)
    return artifact


def validate_goal_conditioned_functional_record(
    *,
    record_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Validate the one-shot goal-conditioned functional 1x10 record."""

    output = Path(output_dir).expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"validation output already exists: {output}")
    source = _require_file(record_path)
    record = _load_json_mapping(source)
    errors: list[str] = []
    if record.get("schema") != FUNCTIONAL_RECORD_SCHEMA:
        errors.append("functional_record_schema_invalid")
    if record.get("status") != "passed":
        errors.append("functional_record_not_passed")
    if _integer(record.get("run_count"), default=-1) != 1:
        errors.append("single_run_contract_invalid")
    if _integer(record.get("temporal_agg_window"), default=-1) != 100:
        errors.append("a0_temporal_window_drift")
    for field in ("wall_contact_count", "stuck_count", "timeout_count"):
        if _integer(record.get(field), default=-1) != 0:
            errors.append(f"{field}_not_zero")
    cycles = record.get("cycles")
    if not _sequence(cycles) or len(cycles) != 10:
        errors.append("ten_complete_cycles_required")
        cycles = ()
    for expected_index, raw_cycle in enumerate(cycles):
        if not isinstance(raw_cycle, Mapping):
            errors.append(f"cycle_{expected_index}:record_invalid")
            continue
        if _integer(raw_cycle.get("cycle_index"), default=-1) != expected_index:
            errors.append(f"cycle_{expected_index}:index_invalid")
        goal_id = str(raw_cycle.get("goal_id", ""))
        return_goal_id = str(raw_cycle.get("return_goal_id", ""))
        if not _is_sha256(goal_id) or return_goal_id != goal_id:
            errors.append(f"cycle_{expected_index}:goal_identity_drift")
        if raw_cycle.get("geometry_consistent") is not True:
            errors.append(f"cycle_{expected_index}:geometry_invalid")
        if raw_cycle.get("worktool_3d_guard_passed") is not True:
            errors.append(f"cycle_{expected_index}:3d_guard_not_passed")
        if raw_cycle.get("exhausted_physical_cell_reused") is not False:
            errors.append(f"cycle_{expected_index}:exhausted_cell_reused")
        if raw_cycle.get("return_handoff_ready") is not True:
            errors.append(f"cycle_{expected_index}:return_handoff_not_ready")
        if expected_index < 9 and raw_cycle.get("next_dig_started") is not True:
            errors.append(f"cycle_{expected_index}:next_dig_not_started")
    hard_bottom_events = record.get("hard_bottom_events")
    if not _sequence(hard_bottom_events):
        errors.append("hard_bottom_events_invalid")
    else:
        for index, event in enumerate(hard_bottom_events):
            if (
                not isinstance(event, Mapping)
                or event.get("neutral_action_sent") is not True
                or event.get("replan_completed") is not True
            ):
                errors.append(
                    f"hard_bottom_event_{index}:neutral_replan_contract_failed"
                )
    for field in (
        "terminal_return_handoff_ready",
        "terminal_zero_action",
        "terminal_neutral_acknowledged",
    ):
        if record.get(field) is not True:
            errors.append(f"{field}_missing")
    if errors:
        raise ExperimentContractError(";".join(errors))
    artifact = {
        "schema": FUNCTIONAL_VALIDATION_SCHEMA,
        "status": "passed",
        "completed_cycle_count": 10,
        "single_run_verified": True,
        "source_record_path": str(source),
        "source_record_sha256": _sha256(source),
        "wall_contact_count": 0,
        "stuck_count": 0,
        "timeout_count": 0,
        "goal_identity_verified_cycle_count": 10,
        "worktool_3d_guard_verified_cycle_count": 10,
        "exhausted_cell_reuse_count": 0,
        "terminal_neutral_acknowledged": True,
        "automatic_retry_allowed": False,
        "functional_3x10_allowed": False,
        "formal_bundle_allowed": False,
        "effect_model_allowed": False,
        "retraining_allowed": False,
    }
    output.mkdir(parents=True, exist_ok=False)
    _write_json_exclusive(output / "validation_manifest.json", artifact)
    return artifact


def _runtime_goal_artifact(
    *,
    condition_id: str,
    condition: Mapping[str, Any],
) -> dict[str, Any]:
    """Strip provenance so E0 cannot become an episode runtime lookup."""

    return {
        "schema": "goal_condition_runtime_input_v1",
        "condition_id": condition_id,
        "source_kind": _CONDITION_SOURCE_KINDS[condition_id],
        "goal": copy.deepcopy(condition.get("goal")),
        "derived_return_envelope": copy.deepcopy(
            condition.get("derived_return_envelope")
        ),
        "support_ood": copy.deepcopy(condition.get("support_ood")),
    }


def _offline_record(
    *,
    condition_id: str,
    condition: Mapping[str, Any],
    predictor_record: Any,
) -> dict[str, Any]:
    blockers: list[str] = []
    goal: Mapping[str, Any] | None = None
    return_envelope_contract_status = "not_evaluated_goal_invalid"
    try:
        goal = _validate_goal(
            condition.get("goal"),
            label=f"{condition_id}.goal",
        )
    except (ExperimentContractError, ValueError, TypeError):
        blockers.append("continuous_goal_contract_invalid")
    if goal is not None:
        try:
            _validate_support_diagnostic(condition.get("support_ood"))
        except (ExperimentContractError, ValueError, TypeError):
            blockers.append("continuous_goal_contract_invalid")

    predictor_evidence: dict[str, Any] | None = None
    if goal is not None:
        if predictor_record is None:
            blockers.append("continuous_goal_3d_predictor_missing")
            return_envelope_contract_status = (
                "not_evaluated_predictor_missing"
            )
        else:
            try:
                predictor_evidence = _validate_predictor_record(
                    predictor_record,
                    goal_id=str(goal["goal_id"]),
                )
                if not predictor_evidence["safe"]:
                    blockers.append("continuous_goal_unsafe_3d")
                try:
                    _validate_return_envelope(
                        condition.get("derived_return_envelope"),
                        goal_id=str(goal["goal_id"]),
                        predictor_evidence=predictor_evidence,
                    )
                    return_envelope_contract_status = "passed"
                except (
                    ExperimentContractError,
                    ValueError,
                    TypeError,
                ):
                    blockers.append("return_envelope_contract_invalid")
                    return_envelope_contract_status = "failed"
            except ExperimentContractError as exc:
                if "unsafe" in str(exc):
                    blockers.append("continuous_goal_unsafe_3d")
                else:
                    blockers.append("continuous_goal_3d_predictor_missing")
                return_envelope_contract_status = (
                    "not_evaluated_predictor_invalid"
                )

    blockers = list(dict.fromkeys(blockers))
    if "continuous_goal_contract_invalid" in blockers or (
        "return_envelope_contract_invalid" in blockers
    ):
        status = "failed"
    elif blockers:
        status = "blocked"
    else:
        status = "passed"
    return {
        "schema": OFFLINE_RECORD_SCHEMA,
        "condition_id": condition_id,
        "status": status,
        "blockers": blockers,
        "goal_id": None if goal is None else goal["goal_id"],
        "goal_contract_valid": goal is not None,
        "return_envelope_contract_valid": (
            return_envelope_contract_status == "passed"
        ),
        "return_envelope_contract_status": (
            return_envelope_contract_status
        ),
        "predictor_evidence": predictor_evidence,
        "act_inference_allowed": status == "passed",
        "live_allowed": status == "passed",
        "closed_loop_claim": False,
    }


def _condition_config(
    *,
    base: Mapping[str, Any],
    condition_id: str,
    output_root: Path,
    goal_path: Path,
    goal_sha256: str,
    a0_contract_sha256: str,
) -> dict[str, Any]:
    config = copy.deepcopy(dict(base))
    evaluation = _mapping(config.get("eval"), "config.eval")
    run_root = output_root / "runs" / condition_id
    evaluation["num_rollouts"] = 1
    evaluation["no_overwrite"] = True
    evaluation["save_video"] = True
    evaluation["record_hdf5"] = True
    evaluation["save_rollout_logs"] = True
    evaluation["results_dir"] = str(run_root / "results")
    evaluation["video_dir"] = str(run_root / "videos")
    evaluation["rollout_log_dir"] = str(run_root / "results" / "rollouts")
    evaluation["hdf5_dir"] = str(
        run_root / "results" / "hdf5_rollouts"
    )
    metadata = _mapping(
        evaluation.setdefault("record_hdf5_metadata", {}),
        "eval.record_hdf5_metadata",
    )
    metadata["experiment_schema"] = EXPERIMENT_SCHEMA
    metadata["condition_id"] = condition_id
    metadata["goal_source_kind"] = _CONDITION_SOURCE_KINDS[condition_id]
    metadata["a0_contract_sha256"] = a0_contract_sha256
    policy = _mapping(config.get("policy"), "config.policy")
    planner = _mapping(policy.get("dig_cut_planner"), "dig_cut_planner")
    planner["mode"] = "continuous_goal_conditioned"
    planner["fallback_mode"] = "raise"
    planner["hold_token_until_skill_exit"] = True
    return_envelope = _mapping(
        planner.setdefault("return_start_envelope", {}),
        "dig_cut_planner.return_start_envelope",
    )
    return_envelope["use_cell_prior"] = False
    for field in ("qpos_from_relocate", "spatial_from_relocate"):
        relocate = _mapping(
            return_envelope.setdefault(field, {}),
            f"dig_cut_planner.return_start_envelope.{field}",
        )
        relocate["enabled"] = False
    planner["continuous_goal_conditioned"] = {
        "hold_goal_through_return_and_dig": True,
        "fallback_mode": "raise",
        "source": {
            "kind": _CONDITION_SOURCE_KINDS[condition_id],
            "condition_id": condition_id,
            "goal_artifact_path": str(goal_path),
            "goal_artifact_sha256": goal_sha256,
        },
    }
    return config


def _assert_single_factor_config_mappings(
    configs: Mapping[str, Mapping[str, Any]],
) -> None:
    _assert_config_mappings(configs, condition_ids=CONDITION_IDS)


def _evidence_matrix(
    *,
    manifest: Mapping[str, Any],
    offline_records: Mapping[str, Mapping[str, Any]],
    live_records: Mapping[str, Mapping[str, Any]] | None,
) -> dict[str, Any]:
    return {
        "schema": EVIDENCE_MATRIX_SCHEMA,
        "status": "present",
        "offline_only": live_records is None,
        "closed_loop_claim": live_records is not None,
        "condition_order": list(CONDITION_IDS),
        "a0_contract_sha256": _mapping(
            manifest.get("a0_contract"),
            "manifest.a0_contract",
        ).get("contract_sha256"),
        "offline": {
            condition_id: copy.deepcopy(offline_records[condition_id])
            for condition_id in CONDITION_IDS
        },
        "live": (
            None
            if live_records is None
            else {
                condition_id: copy.deepcopy(live_records[condition_id])
                for condition_id in CONDITION_IDS
            }
        ),
    }


def _causal_decision(
    *,
    manifest: Mapping[str, Any],
    offline_records: Mapping[str, Mapping[str, Any]],
    live_records: Mapping[str, Mapping[str, Any]] | None,
    experiment_manifest_path: Path,
    experiment_manifest_sha256: str | None,
) -> dict[str, Any]:
    blockers = [
        str(blocker)
        for condition_id in CONDITION_IDS
        for blocker in offline_records[condition_id].get("blockers", ())
    ]
    if blockers:
        classification = next(
            (
                blocker
                for blocker in _BLOCKER_PRIORITY
                if blocker in blockers
            ),
            blockers[0],
        )
    elif live_records is None:
        classification = "three_way_live_evidence_missing"
    elif any(
        record.get("initial_state_valid") is not True
        for record in live_records.values()
    ):
        classification = "reset_fairness_invalid"
    elif any(
        record.get("return_handoff_passed") is not True
        for record in live_records.values()
    ):
        classification = "return_handoff_blocker"
    elif any(
        record.get("worktool_3d_guard_passed") is not True
        for record in live_records.values()
    ):
        classification = "continuous_goal_unsafe_3d"
    elif any(
        record.get("actual_path_within_reference_sweep") is not True
        for record in live_records.values()
    ):
        classification = "act_execution_capability"
    elif (
        live_records["E0_expert_goal"].get("status") == "passed"
        and live_records["G1_planner_continuous_goal"].get("status")
        != "passed"
    ):
        classification = "act_goal_conditioning_or_support_insufficient"
    elif all(
        live_records[condition_id].get("status") == "passed"
        for condition_id in CONDITION_IDS
    ):
        classification = "exact_tuple_runtime_constraint_unnecessary"
    else:
        classification = "three_way_probe_not_all_passed"
    allowed = classification == "exact_tuple_runtime_constraint_unnecessary"
    manifest_conditions = _mapping(
        manifest.get("conditions"),
        "manifest.conditions",
    )
    g1 = _mapping(
        manifest_conditions.get("G1_planner_continuous_goal"),
        "G1 condition",
    )
    return {
        "schema": CAUSAL_DECISION_SCHEMA,
        "status": "passed" if allowed else "blocked",
        "classification": classification,
        "functional_1x10_allowed": allowed,
        "planner_filter_change_allowed": False,
        "automatic_retry_allowed": False,
        "effect_model_allowed": False,
        "retraining_allowed": False,
        "new_recording_allowed": False,
        "a1_a2_allowed": False,
        "functional_3x10_allowed": False,
        "formal_bundle_allowed": False,
        "experiment_manifest_path": str(
            experiment_manifest_path.resolve()
        ),
        "experiment_manifest_sha256": experiment_manifest_sha256,
        "g1_config_path": g1.get("config_path"),
        "required_next_action": (
            "build_single_g1_goal_conditioned_a0_1x10_config"
            if allowed
            else _next_action(classification)
        ),
    }


def _overall_offline_status(
    records: Sequence[Mapping[str, Any]],
) -> str:
    statuses = {str(record.get("status")) for record in records}
    if "failed" in statuses:
        return "failed"
    if "blocked" in statuses:
        return "blocked"
    return "passed"


def _primary_blocker(
    records: Sequence[Mapping[str, Any]],
) -> str | None:
    blockers = {
        str(blocker)
        for record in records
        for blocker in record.get("blockers", ())
    }
    return next(
        (blocker for blocker in _BLOCKER_PRIORITY if blocker in blockers),
        None,
    )


def _next_action(classification: str) -> str:
    return {
        "continuous_goal_3d_predictor_missing": (
            "implement_trusted_continuous_goal_qpos_sweep_predictor"
        ),
        "continuous_goal_unsafe_3d": "revise_continuous_goal_before_act",
        "return_handoff_blocker": "diagnose_return_and_handoff_only",
        "act_execution_capability": "diagnose_act_reference_sweep_tracking",
        "act_goal_conditioning_or_support_insufficient": (
            "write_training_repair_requirements_without_retraining"
        ),
        "three_way_live_evidence_missing": (
            "run_each_return_to_dig_probe_once_in_e0_g1_w1_order"
        ),
    }.get(classification, "stop_without_promotion")


def _report_text(
    *,
    manifest: Mapping[str, Any],
    decision: Mapping[str, Any],
) -> str:
    return (
        "# Goal-conditioned runtime recovery\n\n"
        f"- Offline preflight: `{manifest.get('status')}`\n"
        f"- Causal classification: `{decision.get('classification')}`\n"
        f"- Live allowed: `{str(bool(manifest.get('live_allowed'))).lower()}`\n"
        "- Functional 1x10 allowed: "
        f"`{str(bool(decision.get('functional_1x10_allowed'))).lower()}`\n"
        "- Exact tuple role: `optional diagnostic legacy evidence`\n"
        "- Automatic retry: `forbidden`\n"
        "- Retraining/new recording/effect model: `paused`\n"
    )


def _optional_exact_diagnostic(
    path_value: str | Path | None,
    expected_sha256: str | None,
) -> dict[str, Any] | None:
    if path_value is None:
        if expected_sha256 is not None:
            raise ValueError(
                "exact diagnostic SHA requires an exact diagnostic path"
            )
        return None
    path = _require_file(path_value)
    actual = _sha256(path)
    if expected_sha256 is not None and actual != str(expected_sha256):
        raise ExperimentContractError("source_artifact_drift:exact_diagnostic")
    return {
        "runtime_role": "diagnostic_legacy",
        "runtime_lookup_allowed": False,
        "required": False,
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": actual,
    }
