"""Single-factor diagnostic for the final Strict-18 return approach.

The probe keeps the frozen v7 reset, ACT checkpoints, planner, contact rules,
handoff envelope, and timeouts.  Its sole control change is an opt-in
diagnostic limiter that shapes boom action near the existing qpos upper bound.
The evaluator horizon is shortened from ten to eight completed dumps so the
run answers only whether the previously blocked eighth shovel becomes
reachable.
"""

from __future__ import annotations

import copy
import os
import subprocess
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from testbed.eval.coverage_return_alignment import (
    RETURN_AXIS_TRAIN_SUPPORT_SCHEMA,
    build_return_axis_train_support,
)
from testbed.eval.unity_contact_lineage import (
    verify_unity_contact_environment,
)
from testbed.eval.unity_contact_observe_only_report import (
    REPORT_SCHEMA,
    build_unity_contact_observe_only_report,
)
from testbed.eval.unity_host_identity import (
    probe_agx_unity_host as _probe_agx_unity_host,
)
from testbed.eval.unity_host_identity import (
    validate_unity_host_evidence as _validate_unity_host_evidence,
)
from testbed.eval.wall_contact_artifact_io import (
    artifact_ref,
    load_json,
    load_yaml,
    mapping,
    mapping_mut,
    required_file,
    write_json_x,
    write_yaml_x,
)
from testbed.eval.wall_contact_config_contracts import (
    validate_wall_contact_resolved_config,
)
from testbed.eval.wall_contact_evidence_contracts import (
    rollout_reset_state,
    validate_reset_pair,
)
from testbed.eval.wall_contact_rollout_integrity import (
    lock_act_artifacts,
    resolve_config_artifact,
    runtime_code_refs,
    runtime_command,
    validate_execution_lineage,
    validate_runtime_code_refs,
    verify_ref,
)
from testbed.eval.wall_contact_rollout_probe import (
    _read_jsonl as read_jsonl,
)

PROBE_SCHEMA = "strict18_return_approach_axis_limit_probe_v1"
TRACE_AUDIT_SCHEMA = "strict18_return_approach_action_trace_audit_v1"
PROBE_START_SCHEMA = "strict18_return_approach_axis_limit_attempt_started_v1"
PROBE_EXECUTION_SCHEMA = "strict18_return_approach_axis_limit_execution_v1"
TRAIN_SUPPORT_SCHEMA = RETURN_AXIS_TRAIN_SUPPORT_SCHEMA
PROBE_ATTEMPT_ID = (
    "strict18_seed_1000_return_approach_axis_limit_locked_goal_cell_gate8"
)
PROBE_SEED = 1000
TARGET_COMPLETED_DUMPS = 8
SOURCE_COMPLETED_DUMPS = 7
AXIS_INDEX = 1
ACTIVATION_MARGIN = 0.020
TARGET_MARGIN = 0.016
EXPECTED_CELL_IDS = tuple(range(6))

_EVAL_ROOT = Path("/data/pingfan/excavator_testbed_runs/eval") / (
    "yulong_strict18_terrain_residual_v0"
)
_SOURCE_ROOT = _EVAL_ROOT / (
    "unity_contact_observe_only_multicycle_diagnostic_v7"
)
DEFAULT_SOURCE_CONFIG = _SOURCE_ROOT / (
    "configs/strict18_seed_1000_unity_contact_observe_only_1x10.yaml"
)
DEFAULT_SOURCE_ROLLOUT = (
    _SOURCE_ROOT / "run/results/rollouts/rollout_000.jsonl"
)
DEFAULT_SOURCE_SUMMARY = (
    _SOURCE_ROOT / "run/results/rollouts/rollout_000_summary.json"
)
DEFAULT_SOURCE_REPORT = _SOURCE_ROOT / "run/report_reanalysis_v2.json"
DEFAULT_SOURCE_MANIFEST = _SOURCE_ROOT / "manifest.json"
DEFAULT_QPOS_SUPPORT_AUDIT = _EVAL_ROOT / (
    "return_handoff_qpos1_gate_diagnostic_v1/"
    "expert_handoff_qpos1_support_audit.json"
)
DEFAULT_OUTPUT_ROOT = (
    _EVAL_ROOT / "return_approach_axis_limit_diagnostic_v5"
)

_CONTROL_CONFIG = {
    "enabled": True,
    "diagnostic_only": True,
    "axis_index": AXIS_INDEX,
    "min_completed_dump_count": SOURCE_COMPLETED_DUMPS,
    "required_cell_id": None,
    "lineage_warmup_ticks": 1,
    "activation_margin": ACTIVATION_MARGIN,
    "target_margin": TARGET_MARGIN,
    "activation_velocity_min": 0.0,
    "kp": 4.0,
    "kd": 2.0,
    "action_sign": -1.0,
    "action_clip": 0.35,
}
_CONTROL_DELTA = {
    "path": "policy.box_emptying.return_approach_axis_limit",
    "baseline_effective": {"enabled": False},
    "diagnostic": copy.deepcopy(_CONTROL_CONFIG),
    "handoff_qpos_bound_changed": False,
    "contact_safety_changed": False,
}
_DOWNSTREAM_GATES = {
    "production_contact_contract_change_allowed": False,
    "continuous_predictor_allowed": False,
    "offline_e0_g1_w1_allowed": False,
    "bounded_live_allowed": False,
    "functional_1x10_allowed": False,
}
_PROBE_CODE_PATHS = (
    "testbed/planner/primitive/execution/return_approach_control.py",
    "testbed/eval/coverage_return_alignment.py",
    "testbed/eval/return_approach_probe.py",
    "testbed/cli/return_approach_probe.py",
)

Executor = Callable[[list[str], Path, Path], int]
HostProbe = Callable[[Mapping[str, Any]], Mapping[str, Any]]


class ReturnApproachProbeError(RuntimeError):
    """Raised when the diagnostic source or one-factor contract drifts."""


def analyze_return_approach_trace(
    rows: Sequence[Mapping[str, Any]],
    *,
    same_cell_train_qpos1_max: float,
) -> dict[str, Any]:
    """Reconstruct the seven-dump return failure from recorder debug rows."""

    ordered = sorted(
        (dict(row) for row in rows),
        key=lambda row: int(row.get("step_id", -1)),
    )
    if not ordered:
        raise ReturnApproachProbeError("source_rollout_empty")
    dump_rows = [
        row for row in ordered if bool(row.get("dump_end_mask", False))
    ]
    if len(dump_rows) != SOURCE_COMPLETED_DUMPS:
        raise ReturnApproachProbeError(
            "source_completed_dump_count_drift"
        )
    final_dump_step = int(dump_rows[-1]["step_id"])
    final_return = [
        row
        for row in ordered
        if int(row.get("step_id", -1)) > final_dump_step
        and str(row.get("skill_name", "")) == "return"
    ]
    if not final_return:
        raise ReturnApproachProbeError("source_final_return_missing")
    final_return_start = int(final_return[0]["step_id"])

    axis_records = []
    for row in final_return:
        source = str(row.get("return_start_envelope_token_source", ""))
        checks = row.get("return_to_dig_start_envelope_checks")
        if (
            "cell_0" not in source
            or not isinstance(checks, Mapping)
            or not isinstance(checks.get("qpos_1"), Mapping)
        ):
            continue
        axis = mapping(checks["qpos_1"], "qpos_1")
        try:
            axis_records.append(
                {
                    "row": row,
                    "value": float(axis["value"]),
                    "lower": float(axis["min"]),
                    "upper": float(axis["max"]),
                    "ok": bool(axis["ok"]),
                }
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ReturnApproachProbeError(
                "source_qpos1_check_invalid"
            ) from exc
    if not axis_records:
        raise ReturnApproachProbeError("source_cell0_qpos1_checks_missing")
    upper_counts: dict[float, int] = {}
    for item in axis_records:
        upper = float(item["upper"])
        upper_counts[upper] = upper_counts.get(upper, 0) + 1
    axis_upper = max(
        upper_counts,
        key=lambda value: (upper_counts[value], value),
    )
    stable = [
        item
        for item in axis_records
        if abs(float(item["upper"]) - axis_upper) <= 1.0e-9
    ]
    if len(stable) < 2:
        raise ReturnApproachProbeError(
            "source_qpos1_bound_not_stable"
        )
    axis_lower = float(stable[0]["lower"])
    if any(
        abs(float(item["lower"]) - axis_lower) > 1.0e-9
        for item in stable
    ):
        raise ReturnApproachProbeError(
            "source_qpos1_lower_bound_drift"
        )

    activation_threshold = axis_upper - ACTIVATION_MARGIN
    servo_target = axis_upper - TARGET_MARGIN
    first_activation = _first(
        stable,
        lambda item: float(item["value"]) >= activation_threshold,
    )
    first_violation = _first(
        stable,
        lambda item: float(item["value"]) > float(item["upper"]),
    )
    first_contact = _first(
        stable,
        lambda item: _check_ok(item["row"], "dig_contact"),
    )
    if first_activation is None or first_violation is None or first_contact is None:
        raise ReturnApproachProbeError(
            "source_return_failure_edge_missing"
        )
    activation_row = mapping(first_activation["row"], "activation_row")
    violation_row = mapping(first_violation["row"], "violation_row")
    contact_row = mapping(first_contact["row"], "contact_row")
    activation_action = _axis_value(
        activation_row.get("action"),
        AXIS_INDEX,
        "activation_action",
    )
    violation_action = _axis_value(
        violation_row.get("action"),
        AXIS_INDEX,
        "violation_action",
    )

    all_except_axis_steps: list[int] = []
    all_except_contact_steps: list[int] = []
    for item in stable:
        row = mapping(item["row"], "stable_row")
        checks = mapping(
            row.get("return_to_dig_start_envelope_checks"),
            "return_checks",
        )
        if _all_checks_ok_except(checks, {"qpos_1"}):
            all_except_axis_steps.append(int(row["step_id"]))
        if _all_checks_ok_except(checks, {"dig_contact"}):
            all_except_contact_steps.append(int(row["step_id"]))

    prior_successes = _successful_prior_cell0_returns(
        ordered,
        before_step=final_dump_step,
    )
    train_max = float(same_cell_train_qpos1_max)
    if not axis_lower < train_max < axis_upper:
        raise ReturnApproachProbeError(
            "same_cell_train_qpos1_support_invalid"
        )
    return {
        "schema": TRACE_AUDIT_SCHEMA,
        "status": "passed",
        "diagnostic_only": True,
        "non_promotable": True,
        "completed_dump_count": len(dump_rows),
        "final_dump_step_id": final_dump_step,
        "final_return_start_step_id": final_return_start,
        "final_return_tick_count": len(final_return),
        "axis_index": AXIS_INDEX,
        "axis_name": "boom",
        "axis_lower_bound": axis_lower,
        "axis_upper_bound": axis_upper,
        "activation_margin": ACTIVATION_MARGIN,
        "activation_threshold": activation_threshold,
        "target_margin": TARGET_MARGIN,
        "servo_target_qpos": servo_target,
        "same_cell_train_qpos1_max": train_max,
        "servo_target_within_same_cell_train_support": bool(
            servo_target <= train_max
        ),
        "first_activation_candidate_step_id": int(
            activation_row["step_id"]
        ),
        "first_activation_candidate_qpos_1": float(
            first_activation["value"]
        ),
        "first_activation_candidate_qvel_1": _axis_value(
            activation_row.get("qvel"),
            AXIS_INDEX,
            "activation_qvel",
        ),
        "first_activation_candidate_act_action_1": activation_action,
        "first_qpos_1_violation_step_id": int(violation_row["step_id"]),
        "first_qpos_1_violation_value": float(first_violation["value"]),
        "first_qpos_1_violation_act_action_1": violation_action,
        "first_contact_ready_step_id": int(contact_row["step_id"]),
        "qpos_violation_not_after_contact": bool(
            int(violation_row["step_id"]) <= int(contact_row["step_id"])
        ),
        "negative_act_command_before_qpos_violation": bool(
            activation_action < 0.0 and violation_action < 0.0
        ),
        "all_checks_except_qpos_1_step_ids": all_except_axis_steps,
        "all_checks_except_contact_step_ids": all_except_contact_steps,
        "successful_prior_cell0_return_count": len(prior_successes),
        "successful_prior_cell0_returns": prior_successes,
        "handoff_qpos_bound_changed": False,
        "contact_safety_changed": False,
        "causal_hypothesis": (
            "return_boom_command_overshoot_before_contact"
        ),
        "recommended_single_factor": (
            "shape only boom action toward a same-cell-train-supported "
            "target while preserving the locked handoff envelope"
        ),
    }


def build_return_approach_probe_config(
    source: Mapping[str, Any],
    *,
    run_root: Path,
) -> dict[str, Any]:
    """Deep-copy v7 and add only the diagnostic control plus run metadata."""

    config = copy.deepcopy(dict(source))
    eval_config = mapping_mut(config, "eval")
    eval_config.update(
        {
            "num_rollouts": 1,
            "seed": PROBE_SEED,
            "target_cycle_gate": TARGET_COMPLETED_DUMPS,
            "no_overwrite": True,
            "video_dir": str(run_root / "videos"),
            "results_dir": str(run_root / "results"),
            "rollout_log_dir": str(run_root / "results/rollouts"),
            "record_hdf5": False,
            "hdf5_dir": str(run_root / "disabled_hdf5"),
        }
    )
    metadata = eval_config.setdefault("record_hdf5_metadata", {})
    if not isinstance(metadata, dict):
        raise ReturnApproachProbeError(
            "record_hdf5_metadata_invalid"
        )
    metadata.update(
        {
            "validation_schema": PROBE_SCHEMA,
            "return_approach_attempt_id": PROBE_ATTEMPT_ID,
            "return_approach_reset_seed": PROBE_SEED,
            "return_approach_target_completed_dumps": (
                TARGET_COMPLETED_DUMPS
            ),
            "diagnostic_only": True,
            "promotion_eligible": False,
        }
    )
    policy = mapping_mut(config, "policy")
    box = mapping_mut(policy, "box_emptying")
    if "return_approach_axis_limit" in box:
        raise ReturnApproachProbeError(
            "source_return_approach_axis_limit_already_present"
        )
    box["return_approach_axis_limit"] = copy.deepcopy(_CONTROL_CONFIG)
    return config


def validate_return_approach_probe_config(
    *,
    source: Mapping[str, Any],
    candidate: Mapping[str, Any],
    run_root: Path,
) -> None:
    """Reject every config delta outside the explicit builder."""

    expected = build_return_approach_probe_config(
        source,
        run_root=run_root,
    )
    if dict(candidate) != expected:
        raise ReturnApproachProbeError("single_factor_config_drift")


def prepare_return_approach_probe(
    *,
    source_config_path: str | Path = DEFAULT_SOURCE_CONFIG,
    source_rollout_path: str | Path = DEFAULT_SOURCE_ROLLOUT,
    source_summary_path: str | Path = DEFAULT_SOURCE_SUMMARY,
    source_report_path: str | Path = DEFAULT_SOURCE_REPORT,
    source_manifest_path: str | Path = DEFAULT_SOURCE_MANIFEST,
    qpos_support_audit_path: str | Path = DEFAULT_QPOS_SUPPORT_AUDIT,
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, Any]:
    """Freeze v7, write the trace audit, and prepare one no-overwrite run."""

    sources = {
        "source_config": required_file(source_config_path, "source_config"),
        "source_rollout": required_file(
            source_rollout_path,
            "source_rollout",
        ),
        "source_summary": required_file(
            source_summary_path,
            "source_summary",
        ),
        "source_report": required_file(source_report_path, "source_report"),
        "source_manifest": required_file(
            source_manifest_path,
            "source_manifest",
        ),
        "qpos_support_audit": required_file(
            qpos_support_audit_path,
            "qpos_support_audit",
        ),
    }
    source_config = load_yaml(sources["source_config"])
    source_summary = load_json(sources["source_summary"])
    source_report = load_json(sources["source_report"])
    source_manifest = load_json(sources["source_manifest"])
    qpos_support = load_json(sources["qpos_support_audit"])
    _validate_source_lineage(
        sources=sources,
        source_manifest=source_manifest,
        source_summary=source_summary,
        source_report=source_report,
        qpos_support=qpos_support,
    )
    policy = mapping(source_config.get("policy"), "policy")
    switch = mapping(policy.get("switch"), "switch")
    try:
        qpos_tolerance = float(
            switch["return_to_dig_start_envelope_qpos_tolerance"]
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ReturnApproachProbeError(
            "source_return_qpos_tolerance_invalid"
        ) from exc
    train_support = build_return_axis_train_support(
        qpos_support,
        axis_index=AXIS_INDEX,
        qpos_tolerance=qpos_tolerance,
        activation_margin=ACTIVATION_MARGIN,
        target_margin=TARGET_MARGIN,
        expected_cell_ids=EXPECTED_CELL_IDS,
    )
    if train_support["status"] != "passed":
        raise ReturnApproachProbeError(
            "return_axis_all_cell_train_support_blocked:"
            + ",".join(train_support["blockers"])
        )
    train_max = float(train_support["cells"]["0"]["train_max_qpos_1"])
    trace = analyze_return_approach_trace(
        read_jsonl(sources["source_rollout"]),
        same_cell_train_qpos1_max=train_max,
    )
    if not trace["servo_target_within_same_cell_train_support"]:
        raise ReturnApproachProbeError(
            "servo_target_outside_same_cell_train_support"
        )

    root = Path(output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=False)
    config_path = root / "configs" / f"{PROBE_ATTEMPT_ID}.yaml"
    trace_path = root / "source_trace_audit.json"
    train_support_path = root / "axis_train_support.json"
    manifest_path = root / "manifest.json"
    run_root = root / "run"
    config = build_return_approach_probe_config(
        source_config,
        run_root=run_root,
    )
    validate_return_approach_probe_config(
        source=source_config,
        candidate=config,
        run_root=run_root,
    )
    write_yaml_x(config_path, config)
    write_json_x(
        trace_path,
        {
            **trace,
            "source_rollout": artifact_ref(sources["source_rollout"]),
            "qpos_support_audit": artifact_ref(
                sources["qpos_support_audit"]
            ),
        },
    )
    write_json_x(train_support_path, train_support)
    repo_root = Path(__file__).resolve().parents[2]
    eval_config = mapping(source_config.get("eval"), "eval")
    act_artifacts = lock_act_artifacts(
        eval_config=eval_config,
        policy=policy,
        repo_root=repo_root,
    )
    planner = mapping(policy.get("dig_cut_planner"), "dig_cut_planner")
    planner_prior = resolve_config_artifact(
        planner.get("prior_path"),
        "planner_prior",
        repo_root=repo_root,
    )
    source_lock = mapping(source_manifest.get("source_lock"), "source_lock")
    manifest = {
        "schema": PROBE_SCHEMA,
        "status": "prepared",
        "attempt_id": PROBE_ATTEMPT_ID,
        "seed": PROBE_SEED,
        "source_completed_dumps": SOURCE_COMPLETED_DUMPS,
        "target_completed_dumps": TARGET_COMPLETED_DUMPS,
        "max_attempts": 1,
        "retry_allowed": False,
        "retry_count": 0,
        "diagnostic_only": True,
        "non_promotable": True,
        "writes_training_hdf5": False,
        "manifest_path": str(manifest_path),
        "config_path": str(config_path),
        "trace_audit_path": str(trace_path),
        "axis_train_support_path": str(train_support_path),
        "run_root": str(run_root),
        "command_argv": _configured_command(config_path, run_root),
        "control_delta": copy.deepcopy(_CONTROL_DELTA),
        "operational_deltas": {
            "output_root": "request_local_no_overwrite",
            "target_cycle_gate": TARGET_COMPLETED_DUMPS,
            "target_cycle_gate_effect": (
                "stop only after the eighth completed dump"
            ),
            "record_hdf5": False,
        },
        "hard_stop_contract": {
            "contact_safety": "identical_to_source_v7",
            "wall_high_force_n": 100_000.0,
            "boom_stick_other_contact": "existing_terminal_neutral",
            "invalid_data": "existing_terminal_neutral",
            "stuck": "existing_terminal_neutral",
            "timeout": "existing_terminal_neutral",
        },
        "source_trace_conclusion": trace,
        "axis_train_support": train_support,
        "target_cell_scope": "locked_active_return_cell_any_0_through_5",
        "source_lock": {
            **{
                name: artifact_ref(path)
                for name, path in sources.items()
            },
            "diagnostic_config": artifact_ref(config_path),
            "trace_audit": artifact_ref(trace_path),
            "axis_train_support": artifact_ref(train_support_path),
            "checkpoints": act_artifacts["checkpoints"],
            "dataset_stats": act_artifacts["dataset_stats"],
            "planner_prior": artifact_ref(planner_prior),
            "runtime_code": runtime_code_refs(repo_root),
            "probe_code": _probe_code_refs(repo_root),
            "agx": copy.deepcopy(source_lock["agx"]),
            "unity": copy.deepcopy(source_lock["unity"]),
            "environment_manifest": copy.deepcopy(
                source_lock["environment_manifest"]
            ),
        },
        "downstream_gates": copy.deepcopy(_DOWNSTREAM_GATES),
    }
    write_json_x(manifest_path, manifest)
    return validate_return_approach_probe(manifest_path)


def validate_return_approach_probe(
    manifest_path: str | Path,
) -> dict[str, Any]:
    """Verify every frozen input before consuming the diagnostic attempt."""

    path = required_file(manifest_path, "probe_manifest")
    manifest = load_json(path)
    expected_fields = {
        "schema": PROBE_SCHEMA,
        "status": "prepared",
        "attempt_id": PROBE_ATTEMPT_ID,
        "seed": PROBE_SEED,
        "source_completed_dumps": SOURCE_COMPLETED_DUMPS,
        "target_completed_dumps": TARGET_COMPLETED_DUMPS,
        "max_attempts": 1,
        "retry_allowed": False,
        "retry_count": 0,
        "diagnostic_only": True,
        "non_promotable": True,
        "writes_training_hdf5": False,
    }
    for field, expected in expected_fields.items():
        if manifest.get(field) != expected:
            raise ReturnApproachProbeError(
                f"probe_manifest_contract_invalid:{field}"
            )
    if (
        manifest.get("control_delta") != _CONTROL_DELTA
        or manifest.get("downstream_gates") != _DOWNSTREAM_GATES
    ):
        raise ReturnApproachProbeError("probe_manifest_semantics_drift")
    root = path.parent.resolve()
    if Path(str(manifest.get("manifest_path", ""))).resolve() != path:
        raise ReturnApproachProbeError("probe_manifest_path_drift")
    config_path = required_file(
        manifest.get("config_path"),
        "diagnostic_config",
    )
    trace_path = required_file(
        manifest.get("trace_audit_path"),
        "trace_audit",
    )
    train_support_path = required_file(
        manifest.get("axis_train_support_path"),
        "axis_train_support",
    )
    run_root = Path(str(manifest.get("run_root", ""))).resolve()
    if (
        config_path
        != root / "configs" / f"{PROBE_ATTEMPT_ID}.yaml"
        or trace_path != root / "source_trace_audit.json"
        or train_support_path != root / "axis_train_support.json"
        or run_root != root / "run"
    ):
        raise ReturnApproachProbeError("probe_output_path_drift")
    lock = mapping(manifest.get("source_lock"), "source_lock")
    locked = {
        name: verify_ref(lock.get(name), name)
        for name in (
            "source_config",
            "source_rollout",
            "source_summary",
            "source_report",
            "source_manifest",
            "qpos_support_audit",
            "diagnostic_config",
            "trace_audit",
            "axis_train_support",
        )
    }
    if locked["axis_train_support"] != train_support_path:
        raise ReturnApproachProbeError("axis_train_support_path_drift")
    for primitive in ("dig", "carry", "dump", "return"):
        verify_ref(
            mapping(lock.get("checkpoints"), "checkpoints").get(primitive),
            f"{primitive}_checkpoint",
        )
        verify_ref(
            mapping(lock.get("dataset_stats"), "dataset_stats").get(primitive),
            f"{primitive}_dataset_stats",
        )
    verify_ref(lock.get("planner_prior"), "planner_prior")
    repo_root = Path(__file__).resolve().parents[2]
    validate_runtime_code_refs(lock.get("runtime_code"), repo_root=repo_root)
    _validate_probe_code_refs(lock.get("probe_code"), repo_root=repo_root)
    verify_unity_contact_environment(
        mapping(lock.get("unity"), "unity"),
        verify_ref(lock.get("environment_manifest"), "environment_manifest"),
    )
    source_manifest = load_json(locked["source_manifest"])
    if (
        mapping(
            mapping(source_manifest.get("source_lock"), "source_lock").get(
                "unity"
            ),
            "source_unity",
        )
        != mapping(lock.get("unity"), "unity")
    ):
        raise ReturnApproachProbeError("source_unity_lineage_drift")
    source_config = load_yaml(locked["source_config"])
    observed_config = load_yaml(config_path)
    validate_return_approach_probe_config(
        source=source_config,
        candidate=observed_config,
        run_root=run_root,
    )
    if manifest.get("command_argv") != _configured_command(
        config_path,
        run_root,
    ):
        raise ReturnApproachProbeError("probe_command_lineage_drift")
    qpos_support = load_json(locked["qpos_support_audit"])
    switch = mapping(
        mapping(source_config.get("policy"), "policy").get("switch"),
        "switch",
    )
    try:
        qpos_tolerance = float(
            switch["return_to_dig_start_envelope_qpos_tolerance"]
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ReturnApproachProbeError(
            "source_return_qpos_tolerance_invalid"
        ) from exc
    train_support = build_return_axis_train_support(
        qpos_support,
        axis_index=AXIS_INDEX,
        qpos_tolerance=qpos_tolerance,
        activation_margin=ACTIVATION_MARGIN,
        target_margin=TARGET_MARGIN,
        expected_cell_ids=EXPECTED_CELL_IDS,
    )
    if (
        train_support["status"] != "passed"
        or manifest.get("axis_train_support") != train_support
        or load_json(train_support_path) != train_support
    ):
        raise ReturnApproachProbeError("axis_train_support_drift")
    train_max = float(train_support["cells"]["0"]["train_max_qpos_1"])
    trace = analyze_return_approach_trace(
        read_jsonl(locked["source_rollout"]),
        same_cell_train_qpos1_max=train_max,
    )
    if (
        manifest.get("source_trace_conclusion") != trace
        or {
            key: value
            for key, value in load_json(trace_path).items()
            if key not in {"source_rollout", "qpos_support_audit"}
        }
        != trace
    ):
        raise ReturnApproachProbeError("source_trace_audit_drift")
    return manifest


def run_return_approach_probe(
    *,
    manifest_path: str | Path,
    executor: Executor | None = None,
    host_probe: HostProbe | None = None,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Consume the sole diagnostic attempt and collect its report."""

    manifest = validate_return_approach_probe(manifest_path)
    run_root = Path(str(manifest["run_root"]))
    if run_root.exists():
        raise FileExistsError(f"diagnostic attempt consumed:{run_root}")
    agx = mapping(
        mapping(manifest.get("source_lock"), "source_lock").get("agx"),
        "agx",
    )
    host_evidence = _validate_unity_host_evidence(
        (host_probe or _probe_agx_unity_host)(agx),
        agx=agx,
    )
    run_root.mkdir(parents=True, exist_ok=False)
    marker_path = run_root / "attempt_started.json"
    log_path = run_root / "eval_process.log"
    execution_path = run_root / "execution.json"
    execution_cwd = (
        Path(cwd).expanduser().resolve()
        if cwd is not None
        else Path(__file__).resolve().parents[2]
    )
    configured = list(manifest["command_argv"])
    command = runtime_command(configured)
    started_at = _utc_now()
    write_json_x(
        marker_path,
        {
            "schema": PROBE_START_SCHEMA,
            "attempt_id": PROBE_ATTEMPT_ID,
            "seed": PROBE_SEED,
            "retry_count": 0,
            "started_at_utc": started_at,
            "manifest": artifact_ref(
                Path(str(manifest["manifest_path"]))
            ),
            "configured_argv": configured,
            "executed_argv": command,
            "cwd": str(execution_cwd),
            "unity_host_get_info": host_evidence,
        },
    )
    log_path.open("x", encoding="utf-8").close()
    process_exception = ""
    try:
        returncode = int(
            (executor or _execute_subprocess)(
                command,
                execution_cwd,
                log_path,
            )
        )
    except Exception as exc:  # consumed failures remain evidence
        returncode = -1
        process_exception = f"{type(exc).__name__}:{exc}"
    write_json_x(
        execution_path,
        {
            "schema": PROBE_EXECUTION_SCHEMA,
            "attempt_id": PROBE_ATTEMPT_ID,
            "seed": PROBE_SEED,
            "retry_count": 0,
            "process_returncode": returncode,
            "process_exception": process_exception,
            "started_at_utc": started_at,
            "ended_at_utc": _utc_now(),
            "attempt_started": artifact_ref(marker_path),
            "process_log": artifact_ref(log_path),
        },
    )
    return collect_return_approach_probe(manifest_path=manifest_path)


def collect_return_approach_probe(
    *,
    manifest_path: str | Path,
) -> dict[str, Any]:
    """Collect contact, fairness, and eighth-shovel evidence append-only."""

    manifest = validate_return_approach_probe(manifest_path)
    run_root = Path(str(manifest["run_root"]))
    if not run_root.is_dir():
        raise FileNotFoundError(f"diagnostic attempt missing:{run_root}")
    marker_path = run_root / "attempt_started.json"
    execution_path = run_root / "execution.json"
    report_path = run_root / "report.json"
    if report_path.exists():
        raise FileExistsError(f"diagnostic report exists:{report_path}")
    rollout_path = run_root / "results/rollouts/rollout_000.jsonl"
    summary_path = (
        run_root / "results/rollouts/rollout_000_summary.json"
    )
    resolved_path = run_root / "results/eval_resolved_config.yaml"
    returncode = -1
    host_evidence: dict[str, Any] | None = None
    try:
        marker = load_json(required_file(marker_path, "attempt_started"))
        execution = load_json(required_file(execution_path, "execution"))
        validate_execution_lineage(
            marker,
            execution,
            manifest,
            start_schema=PROBE_START_SCHEMA,
            execution_schema=PROBE_EXECUTION_SCHEMA,
            attempt_id=PROBE_ATTEMPT_ID,
            seed=PROBE_SEED,
        )
        agx = mapping(
            mapping(manifest.get("source_lock"), "source_lock").get("agx"),
            "agx",
        )
        host_evidence = _validate_unity_host_evidence(
            marker.get("unity_host_get_info"),
            agx=agx,
        )
        returncode = int(execution.get("process_returncode", -1))
        if sorted(run_root.rglob("*.hdf5")):
            raise ReturnApproachProbeError("unexpected_hdf5_artifact")
        if (
            returncode != 0
            or not rollout_path.is_file()
            or not summary_path.is_file()
            or not resolved_path.is_file()
        ):
            blockers = []
            if returncode != 0:
                blockers.append(f"eval_process_returncode:{returncode}")
            if not rollout_path.is_file():
                blockers.append("rollout_jsonl_missing")
            if not summary_path.is_file():
                blockers.append("rollout_summary_missing")
            if not resolved_path.is_file():
                blockers.append("resolved_config_missing")
            report = _failed_report(blockers)
        else:
            rows = read_jsonl(rollout_path)
            validate_wall_contact_resolved_config(
                configured=load_yaml(
                    Path(str(manifest["config_path"]))
                ),
                resolved=load_yaml(resolved_path),
                run_root=run_root,
            )
            contact_report = build_unity_contact_observe_only_report(
                rows=rows,
                summary=load_json(summary_path),
                max_shovels=TARGET_COMPLETED_DUMPS,
            )
            source_rollout = verify_ref(
                mapping(
                    manifest.get("source_lock"),
                    "source_lock",
                ).get("source_rollout"),
                "source_rollout",
            )
            expected_reset = rollout_reset_state(
                read_jsonl(source_rollout)[0]
            )
            reset_fairness = validate_reset_pair(
                expected_reset_state=expected_reset,
                reset_a=expected_reset,
                reset_b=rollout_reset_state(rows[0]),
            )
            axis_result = _collect_axis_result(rows)
            report = {
                **contact_report,
                "reset_fairness": reset_fairness,
                "return_approach_axis_limit": axis_result,
            }
            report = _apply_axis_exercise_gate(report, axis_result)
            if not reset_fairness["valid"]:
                report["status"] = "failed"
                report["termination_category"] = "failed"
                report["blockers"] = list(reset_fairness["violations"])
    except Exception as exc:
        report = _failed_report(
            [f"rollout_evidence_invalid:{type(exc).__name__}:{exc}"]
        )
    report = {
        **report,
        "probe_schema": PROBE_SCHEMA,
        "attempt_id": PROBE_ATTEMPT_ID,
        "seed": PROBE_SEED,
        "executed_attempt_count": 1,
        "retry_count": 0,
        "max_attempts": 1,
        "retry_allowed": False,
        "process_returncode": returncode,
        "unity_host_get_info": host_evidence,
        "attempt_started": (
            artifact_ref(marker_path) if marker_path.is_file() else None
        ),
        "execution": (
            artifact_ref(execution_path)
            if execution_path.is_file()
            else None
        ),
        "rollout_jsonl": (
            artifact_ref(rollout_path)
            if rollout_path.is_file()
            else None
        ),
        "rollout_summary": (
            artifact_ref(summary_path)
            if summary_path.is_file()
            else None
        ),
        "resolved_config": (
            artifact_ref(resolved_path)
            if resolved_path.is_file()
            else None
        ),
        "diagnostic_only": True,
        "non_promotable": True,
        "writes_training_hdf5": False,
        "downstream_gates": copy.deepcopy(_DOWNSTREAM_GATES),
    }
    write_json_x(report_path, report)
    return report


def _validate_source_lineage(
    *,
    sources: Mapping[str, Path],
    source_manifest: Mapping[str, Any],
    source_summary: Mapping[str, Any],
    source_report: Mapping[str, Any],
    qpos_support: Mapping[str, Any],
) -> None:
    if source_manifest.get("attempt_id") != (
        "strict18_seed_1000_unity_contact_observe_only_1x10"
    ):
        raise ReturnApproachProbeError("source_manifest_attempt_drift")
    source_lock = mapping(source_manifest.get("source_lock"), "source_lock")
    if verify_ref(
        source_lock.get("diagnostic_config"),
        "source_diagnostic_config",
    ) != sources["source_config"]:
        raise ReturnApproachProbeError("source_config_lineage_drift")
    corrected_report = (
        mapping(source_report.get("corrected_report"), "corrected_report")
        if "corrected_report" in source_report
        else source_report
    )
    if (
        int(source_summary.get("coverage_completed_dump_count", -1))
        != SOURCE_COMPLETED_DUMPS
        and int(corrected_report.get("completed_dump_count", -1))
        != SOURCE_COMPLETED_DUMPS
    ):
        raise ReturnApproachProbeError("source_outcome_drift")
    if (
        corrected_report.get("status") != "passed"
        or corrected_report.get("termination_category") != "timeout"
    ):
        raise ReturnApproachProbeError("source_report_contract_drift")
    decision = mapping(qpos_support.get("decision"), "qpos_decision")
    if (
        qpos_support.get("status") != "passed"
        or decision.get("axis1_plus_0p005_rollout_allowed") is not False
        or decision.get("runtime_or_config_changed") is not False
    ):
        raise ReturnApproachProbeError("qpos_support_audit_contract_drift")
    verify_unity_contact_environment(
        mapping(source_lock.get("unity"), "source_unity"),
        verify_ref(
            source_lock.get("environment_manifest"),
            "source_environment_manifest",
        ),
    )


def _successful_prior_cell0_returns(
    rows: Sequence[Mapping[str, Any]],
    *,
    before_step: int,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    segment: list[Mapping[str, Any]] = []
    for row in rows:
        step_id = int(row.get("step_id", -1))
        if step_id >= before_step:
            break
        if str(row.get("skill_name", "")) == "return":
            segment.append(row)
            continue
        if segment:
            if (
                str(row.get("skill_name", "")) == "dig"
                and any(
                    "cell_0"
                    in str(
                        item.get(
                            "return_start_envelope_token_source",
                            "",
                        )
                    )
                    for item in segment
                )
            ):
                last = segment[-1]
                checks = mapping(
                    last.get("return_to_dig_start_envelope_checks"),
                    "prior_return_checks",
                )
                qpos_axis = mapping(checks.get("qpos_1"), "prior_qpos_1")
                result.append(
                    {
                        "start_step_id": int(segment[0]["step_id"]),
                        "end_step_id": int(last["step_id"]),
                        "handoff_step_id": step_id,
                        "handoff_qpos_1": float(qpos_axis["value"]),
                        "handoff_qpos_1_ok": bool(qpos_axis["ok"]),
                    }
                )
            segment = []
    return result


def _collect_axis_result(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    dump_steps = [
        int(row.get("step_id", -1))
        for row in rows
        if bool(row.get("dump_end_mask", False))
    ]
    last_count = 0
    first_intervention = -1
    last_intervention = -1
    terminal_reasons: set[str] = set()
    max_qpos_1 = float("-inf")
    for row in rows:
        qpos = row.get("qpos")
        if isinstance(qpos, Sequence) and len(qpos) > AXIS_INDEX:
            max_qpos_1 = max(max_qpos_1, float(qpos[AXIS_INDEX]))
        count = int(
            row.get(
                "return_approach_axis_limit_intervention_count",
                last_count,
            )
        )
        if count > last_count:
            if first_intervention < 0:
                first_intervention = int(
                    row.get(
                        "return_approach_axis_limit_first_intervention_step_id",
                        -1,
                    )
                )
            last_intervention = int(
                row.get(
                    "return_approach_axis_limit_last_intervention_step_id",
                    -1,
                )
            )
        last_count = max(last_count, count)
        reason = str(
            row.get("return_approach_axis_limit_terminal_reason", "")
        )
        if reason:
            terminal_reasons.add(reason)
    seventh_dump = dump_steps[6] if len(dump_steps) >= 7 else 10**18
    entered_eighth_dig = any(
        int(row.get("step_id", -1)) > seventh_dump
        and str(row.get("skill_name", "")) == "dig"
        for row in rows
    )
    enabled = any(
        bool(
            row.get(
                "return_approach_axis_limit_enabled",
                False,
            )
        )
        for row in rows
    )
    return {
        "enabled": enabled,
        "exercised": bool(enabled and last_count > 0),
        "intervention_count": last_count,
        "first_intervention_step_id": first_intervention,
        "last_intervention_step_id": last_intervention,
        "terminal_reasons": sorted(terminal_reasons),
        "max_observed_qpos_1": (
            max_qpos_1 if max_qpos_1 != float("-inf") else float("nan")
        ),
        "entered_eighth_dig": entered_eighth_dig,
        "completed_eighth_dump": len(dump_steps) >= 8,
        "completed_dump_count": len(dump_steps),
        "handoff_qpos_bound_changed": False,
        "contact_safety_changed": False,
    }


def _apply_axis_exercise_gate(
    report: Mapping[str, Any],
    axis_result: Mapping[str, Any],
) -> dict[str, Any]:
    result = dict(report)
    if bool(axis_result.get("exercised", False)):
        return result
    blockers = list(result.get("blockers", []))
    blocker = (
        "return_approach_axis_limit_evidence_missing"
        if not bool(axis_result.get("enabled", False))
        else "return_approach_axis_limit_not_exercised"
    )
    if blocker not in blockers:
        blockers.append(blocker)
    result["status"] = "failed"
    result["termination_category"] = "diagnostic_not_exercised"
    result["blockers"] = blockers
    return result


def _all_checks_ok_except(
    checks: Mapping[str, Any],
    excluded: set[str],
) -> bool:
    required = {
        "long_norm",
        "short_norm",
        "local_depth_m",
        "plane_depth_m",
        "dig_contact",
        "qpos_0",
        "qpos_1",
        "qpos_2",
        "qpos_3",
        "qvel_abs_max",
    }
    if not required <= set(checks):
        return False
    return all(
        bool(mapping(checks[name], name).get("ok", False))
        for name in required - excluded
    ) and all(
        not bool(mapping(checks[name], name).get("ok", False))
        for name in excluded
    )


def _check_ok(row: Mapping[str, Any], name: str) -> bool:
    checks = row.get("return_to_dig_start_envelope_checks")
    if not isinstance(checks, Mapping):
        return False
    value = checks.get(name)
    return bool(isinstance(value, Mapping) and value.get("ok", False))


def _axis_value(value: Any, axis: int, label: str) -> float:
    if (
        isinstance(value, (str, bytes))
        or not isinstance(value, Sequence)
        or len(value) <= axis
    ):
        raise ReturnApproachProbeError(f"{label}_invalid")
    return float(value[axis])


def _first(
    items: Sequence[Mapping[str, Any]],
    predicate: Callable[[Mapping[str, Any]], bool],
) -> Mapping[str, Any] | None:
    return next((item for item in items if predicate(item)), None)


def _probe_code_refs(repo_root: Path) -> list[dict[str, Any]]:
    return [
        artifact_ref((repo_root / relative).resolve())
        for relative in _PROBE_CODE_PATHS
    ]


def _validate_probe_code_refs(
    value: Any,
    *,
    repo_root: Path,
) -> None:
    if (
        not isinstance(value, list)
        or len(value) != len(_PROBE_CODE_PATHS)
    ):
        raise ReturnApproachProbeError("probe_code_lock_invalid")
    for index, (reference, relative) in enumerate(
        zip(value, _PROBE_CODE_PATHS, strict=True)
    ):
        if verify_ref(reference, f"probe_code_{index}") != (
            repo_root / relative
        ).resolve():
            raise ReturnApproachProbeError("probe_code_lock_invalid")


def _configured_command(
    config_path: Path,
    run_root: Path,
) -> list[str]:
    return [
        "python",
        "-m",
        "testbed.cli.eval",
        "--config",
        str(config_path),
        "--num-rollouts",
        "1",
        "--target-cycle-gate",
        str(TARGET_COMPLETED_DUMPS),
        "--output-dir",
        str(run_root),
    ]


def _execute_subprocess(
    command: list[str],
    cwd: Path,
    log_path: Path,
) -> int:
    with log_path.open("a", encoding="utf-8") as sink:
        completed = subprocess.run(
            command,
            cwd=cwd,
            stdout=sink,
            stderr=subprocess.STDOUT,
            check=False,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
    return int(completed.returncode)


def _failed_report(blockers: Sequence[str]) -> dict[str, Any]:
    return {
        "schema": REPORT_SCHEMA,
        "status": "failed",
        "termination_category": "failed",
        "blockers": list(blockers),
        "max_shovels": TARGET_COMPLETED_DUMPS,
        "started_shovel_count": 0,
        "completed_dump_count": 0,
        "partial_shovel_count": 0,
        "shovels": [],
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "DEFAULT_OUTPUT_ROOT",
    "DEFAULT_QPOS_SUPPORT_AUDIT",
    "DEFAULT_SOURCE_CONFIG",
    "DEFAULT_SOURCE_MANIFEST",
    "DEFAULT_SOURCE_REPORT",
    "DEFAULT_SOURCE_ROLLOUT",
    "DEFAULT_SOURCE_SUMMARY",
    "PROBE_ATTEMPT_ID",
    "PROBE_SCHEMA",
    "TRAIN_SUPPORT_SCHEMA",
    "ReturnApproachProbeError",
    "analyze_return_approach_trace",
    "build_return_axis_train_support",
    "build_return_approach_probe_config",
    "collect_return_approach_probe",
    "prepare_return_approach_probe",
    "run_return_approach_probe",
    "validate_return_approach_probe",
    "validate_return_approach_probe_config",
]
