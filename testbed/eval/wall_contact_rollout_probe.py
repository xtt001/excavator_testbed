"""Exactly-once launcher for the observe-only wall-contact rollout.

The probe deliberately keeps the historical seven-dump Strict-18 rollout as
its configuration/reset/checkpoint baseline. Its only runtime safety semantic
change is that finite, sub-threshold bucket-to-wall contact is observed without
causing neutral, policy reset, replan, or corridor blocking. All output and
execution bookkeeping changes are diagnostic plumbing rather than policy
semantics.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from testbed.eval.wall_contact_artifact_io import (
    artifact_ref,
    load_json,
    load_yaml,
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
from testbed.eval.wall_contact_rollout_diagnostic import (
    REPORT_SCHEMA,
    WallContactRolloutDiagnosticError,
    build_wall_contact_rollout_report,
)
from testbed.eval.wall_contact_rollout_integrity import (
    lock_act_artifacts,
    runtime_code_refs,
    validate_runtime_code_refs,
)
from testbed.eval.wall_contact_rollout_integrity import (
    resolve_config_artifact as _resolve_config_artifact,
)
from testbed.eval.wall_contact_rollout_integrity import (
    runtime_command as _runtime_command,
)
from testbed.eval.wall_contact_rollout_integrity import (
    validate_execution_lineage as _validate_execution,
)
from testbed.eval.wall_contact_rollout_integrity import (
    verify_ref as _verify_ref,
)

PROBE_SCHEMA = "wall_contact_observe_only_rollout_probe_v1"
PROBE_ATTEMPT_ID = "strict18_seed_1000_observe_only_1x10"
PROBE_START_SCHEMA = "wall_contact_observe_only_attempt_started_v1"
PROBE_EXECUTION_SCHEMA = "wall_contact_observe_only_execution_v1"
PROBE_MAX_SHOVELS = 10
PROBE_SEED = 1000

_EVAL_ROOT = Path("/data/pingfan/excavator_testbed_runs/eval") / (
    "yulong_strict18_terrain_residual_v0"
)
DEFAULT_SOURCE_ROOT = _EVAL_ROOT / "act_freeze_probe_1x10_strict_prior_v1"
DEFAULT_SOURCE_CONFIG = DEFAULT_SOURCE_ROOT / "results/eval_resolved_config.yaml"
DEFAULT_SOURCE_ROLLOUT = DEFAULT_SOURCE_ROOT / "results/rollouts/rollout_000.jsonl"
DEFAULT_SOURCE_SUMMARY = DEFAULT_SOURCE_ROOT / (
    "results/rollouts/rollout_000_summary.json"
)
DEFAULT_SOURCE_RESET_VALIDATION = DEFAULT_SOURCE_ROOT / (
    "validation_v1/validation_reset_000.json"
)
DEFAULT_ENVIRONMENT_MANIFEST = (
    _EVAL_ROOT
    / "wall_contact_semantics_recovery_v1"
    / "reanalysis_v4"
    / "experiment_manifest.json"
)
DEFAULT_OUTPUT_ROOT = _EVAL_ROOT / "wall_contact_observe_only_multicycle_diagnostic_v1"

Executor = Callable[[list[str], Path, Path], int]

_OUTPUT_FIELDS = ("video_dir", "results_dir", "rollout_log_dir", "hdf5_dir")
_RUNTIME_SEMANTIC_DELTA = [
    {
        "path": "policy.box_emptying.safety.wall_first_touch_mode",
        "baseline_effective": "interrupt",
        "diagnostic": "record_bucket_all_contacts",
    },
    {
        "path": (
            "policy.box_emptying.safety."
            "wall_contact_diagnostic_observe_only_enabled"
        ),
        "baseline_effective": False,
        "diagnostic": True,
    },
]
_HARD_STOP_CONTRACT = {
    "wall_force_at_or_above_n": 100_000.0,
    "boom_contact": "terminal_neutral",
    "stick_contact": "terminal_neutral",
    "other_or_ambiguous_component": "terminal_neutral",
    "hard_bottom": "terminal_neutral",
    "nonfinite_or_invalid_lineage": "terminal_neutral",
    "stuck": "terminal_neutral",
    "timeout": "existing_terminal_stop",
}
_DOWNSTREAM_GATES = {
    "contact_budget_freeze_allowed": False,
    "continuous_predictor_allowed": False,
    "offline_e0_g1_w1_allowed": False,
    "bounded_live_allowed": False,
    "functional_1x10_allowed": False,
}


def prepare_wall_contact_rollout_probe(
    *,
    source_config_path: str | Path = DEFAULT_SOURCE_CONFIG,
    source_rollout_path: str | Path = DEFAULT_SOURCE_ROLLOUT,
    source_summary_path: str | Path = DEFAULT_SOURCE_SUMMARY,
    source_reset_validation_path: str | Path = (
        DEFAULT_SOURCE_RESET_VALIDATION
    ),
    environment_manifest_path: str | Path = DEFAULT_ENVIRONMENT_MANIFEST,
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, Any]:
    """Create a no-overwrite manifest and request-local diagnostic config."""
    sources = {
        "baseline_config": _required_file(
            source_config_path, "baseline_config"
        ),
        "baseline_rollout_jsonl": _required_file(
            source_rollout_path, "baseline_rollout_jsonl"
        ),
        "baseline_rollout_summary": _required_file(
            source_summary_path, "baseline_rollout_summary"
        ),
        "baseline_reset_validation": _required_file(
            source_reset_validation_path,
            "baseline_reset_validation",
        ),
        "environment_manifest": _required_file(
            environment_manifest_path, "environment_manifest"
        ),
    }
    source_config = load_yaml(sources["baseline_config"])
    source_summary = load_json(sources["baseline_rollout_summary"])
    reset_validation = load_json(sources["baseline_reset_validation"])
    baseline_outcome = _validate_baseline_outcome(
        source_summary,
        reset_validation,
    )
    source_contract = _validate_source_config(source_config)
    environment_lock = _lock_environment(
        sources["environment_manifest"]
    )
    root = Path(output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=False)
    config_path = root / "configs" / f"{PROBE_ATTEMPT_ID}.yaml"
    manifest_path = root / "manifest.json"
    run_root = root / "run"
    diagnostic_config = _build_diagnostic_config(
        source_config,
        run_root=run_root,
    )
    write_yaml_x(config_path, diagnostic_config)
    source_lock = {
        **{key: artifact_ref(path) for key, path in sources.items()},
        "checkpoints": source_contract["checkpoints"],
        "dataset_stats": source_contract["dataset_stats"],
        "planner_prior": source_contract["planner_prior"],
        "unity": environment_lock,
        "diagnostic_config": artifact_ref(config_path),
        "runtime_code": runtime_code_refs(
            Path(__file__).resolve().parents[2]
        ),
    }
    command = _configured_command(config_path, run_root)
    manifest = {
        "schema": PROBE_SCHEMA,
        "status": "prepared",
        "attempt_id": PROBE_ATTEMPT_ID,
        "seed": PROBE_SEED,
        "max_attempts": 1,
        "retry_allowed": False,
        "retry_count": 0,
        "max_shovels": PROBE_MAX_SHOVELS,
        "config_path": str(config_path),
        "run_root": str(run_root),
        "manifest_path": str(manifest_path),
        "command_argv": command,
        "baseline_outcome": baseline_outcome,
        "runtime_semantic_delta": copy.deepcopy(_RUNTIME_SEMANTIC_DELTA),
        "operational_deltas": {
            "output_root": "request_local_no_overwrite",
            "num_rollouts": 1,
            "max_attempts": 1,
            "retry_allowed": False,
            "record_hdf5": False,
            "explicit_seed_preserves_implicit_default": PROBE_SEED,
        },
        "observe_only_contract": {
            "allowed_component": "bucket",
            "force_must_be_finite": True,
            "force_strictly_below_n": 100_000.0,
            "session_count_limited": False,
            "duration_limited": False,
            "contact_region_limited": False,
            "wall_identity_limited": False,
            "neutral_allowed": False,
            "act_reset_allowed": False,
            "replan_allowed": False,
            "corridor_block_allowed": False,
        },
        "hard_stop_contract": dict(_HARD_STOP_CONTRACT),
        "source_lock": source_lock,
        "diagnostic_only": True,
        "non_promotable": True,
        "writes_training_hdf5": False,
        "downstream_gates": dict(_DOWNSTREAM_GATES),
    }
    write_json_x(manifest_path, manifest)
    return validate_wall_contact_rollout_probe(manifest_path)


def validate_wall_contact_rollout_probe(
    manifest_path: str | Path,
) -> dict[str, Any]:
    """Fail closed on source, generated-config, or command lineage drift."""
    path = _required_file(manifest_path, "probe_manifest")
    manifest = load_json(path)
    required = {
        "schema": PROBE_SCHEMA,
        "status": "prepared",
        "attempt_id": PROBE_ATTEMPT_ID,
        "seed": PROBE_SEED,
        "max_attempts": 1,
        "retry_allowed": False,
        "retry_count": 0,
        "max_shovels": PROBE_MAX_SHOVELS,
        "diagnostic_only": True,
        "non_promotable": True,
        "writes_training_hdf5": False,
    }
    for field, expected in required.items():
        if manifest.get(field) != expected:
            raise WallContactRolloutDiagnosticError(
                f"probe_manifest_contract_invalid:{field}"
            )
    if (
        manifest.get("runtime_semantic_delta") != _RUNTIME_SEMANTIC_DELTA
        or manifest.get("hard_stop_contract") != _HARD_STOP_CONTRACT
        or manifest.get("downstream_gates") != _DOWNSTREAM_GATES
    ):
        raise WallContactRolloutDiagnosticError(
            "probe_manifest_semantics_drift"
        )
    root = path.parent.resolve()
    if Path(str(manifest.get("manifest_path", ""))).resolve() != path:
        raise WallContactRolloutDiagnosticError("probe_manifest_path_drift")
    config_path = _required_file(
        manifest.get("config_path"), "diagnostic_config"
    )
    run_root = Path(str(manifest.get("run_root", ""))).resolve()
    if (
        config_path != root / "configs" / f"{PROBE_ATTEMPT_ID}.yaml"
        or run_root != root / "run"
    ):
        raise WallContactRolloutDiagnosticError("probe_output_path_drift")
    lock = _mapping(manifest.get("source_lock"), "source_lock")
    locked_paths = {
        field: _verify_ref(lock.get(field), field)
        for field in (
            "baseline_config",
            "baseline_rollout_jsonl",
            "baseline_rollout_summary",
            "baseline_reset_validation",
            "environment_manifest",
            "diagnostic_config",
        )
    }
    checkpoints = _mapping(lock.get("checkpoints"), "checkpoints")
    dataset_stats = _mapping(lock.get("dataset_stats"), "dataset_stats")
    for primitive in ("dig", "carry", "dump", "return"):
        _verify_ref(checkpoints.get(primitive), f"{primitive}_checkpoint")
        _verify_ref(
            dataset_stats.get(primitive),
            f"{primitive}_dataset_stats",
        )
    _verify_ref(lock.get("planner_prior"), "planner_prior")
    validate_runtime_code_refs(
        lock.get("runtime_code"),
        repo_root=Path(__file__).resolve().parents[2],
    )
    _verify_environment_lock(
        _mapping(lock.get("unity"), "unity"),
        locked_paths["environment_manifest"],
    )
    source_config = load_yaml(locked_paths["baseline_config"])
    source_summary = load_json(locked_paths["baseline_rollout_summary"])
    reset_validation = load_json(
        locked_paths["baseline_reset_validation"]
    )
    baseline_outcome = _validate_baseline_outcome(
        source_summary,
        reset_validation,
    )
    if baseline_outcome != manifest.get("baseline_outcome"):
        raise WallContactRolloutDiagnosticError(
            "baseline_outcome_lineage_drift"
        )
    source_contract = _validate_source_config(source_config)
    if (
        source_contract["checkpoints"] != checkpoints
        or source_contract["dataset_stats"] != dataset_stats
        or source_contract["planner_prior"] != lock.get("planner_prior")
    ):
        raise WallContactRolloutDiagnosticError(
            "source_config_artifact_lineage_drift"
        )
    expected_config = _build_diagnostic_config(
        source_config,
        run_root=run_root,
    )
    observed_config = load_yaml(config_path)
    if observed_config != expected_config:
        raise WallContactRolloutDiagnosticError(
            "diagnostic_config_contract_drift"
        )
    _validate_diagnostic_config(observed_config, run_root)
    expected_command = _configured_command(config_path, run_root)
    if manifest.get("command_argv") != expected_command:
        raise WallContactRolloutDiagnosticError(
            "probe_command_lineage_drift"
        )
    return manifest


def run_wall_contact_rollout_probe(
    *,
    manifest_path: str | Path,
    executor: Executor | None = None,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Run the single attempt, permanently consuming it before execution."""
    manifest = validate_wall_contact_rollout_probe(manifest_path)
    run_root = Path(str(manifest["run_root"]))
    if run_root.exists():
        raise FileExistsError(
            f"diagnostic attempt already consumed: {run_root}"
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
    command = _runtime_command(configured)
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
        },
    )
    log_path.open("x", encoding="utf-8").close()
    run_executor = executor or _execute_subprocess
    process_exception = ""
    try:
        returncode = int(run_executor(command, execution_cwd, log_path))
    except Exception as exc:  # preserve an exactly-once failed attempt
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
    return collect_wall_contact_rollout_probe(
        manifest_path=manifest_path
    )


def collect_wall_contact_rollout_probe(
    *,
    manifest_path: str | Path,
) -> dict[str, Any]:
    """Collect the immutable rollout into the focused diagnostic report."""
    manifest = validate_wall_contact_rollout_probe(manifest_path)
    run_root = Path(str(manifest["run_root"]))
    if not run_root.is_dir():
        raise FileNotFoundError(f"diagnostic attempt missing: {run_root}")
    marker_path = run_root / "attempt_started.json"
    execution_path = run_root / "execution.json"
    report_path = run_root / "report.json"
    if report_path.exists():
        raise FileExistsError(f"diagnostic report already exists: {report_path}")
    rollout_path = run_root / "results/rollouts/rollout_000.jsonl"
    summary_path = run_root / "results/rollouts/rollout_000_summary.json"
    resolved_path = run_root / "results/eval_resolved_config.yaml"
    returncode = -1
    try:
        marker = load_json(_required_file(marker_path, "attempt_started"))
        execution = load_json(_required_file(execution_path, "execution"))
        _validate_execution(
            marker,
            execution,
            manifest,
            start_schema=PROBE_START_SCHEMA,
            execution_schema=PROBE_EXECUTION_SCHEMA,
            attempt_id=PROBE_ATTEMPT_ID,
            seed=PROBE_SEED,
        )
        returncode = int(execution.get("process_returncode", -1))
        if sorted(run_root.rglob("*.hdf5")):
            raise WallContactRolloutDiagnosticError(
                "unexpected_hdf5_artifact"
            )
        if (
            returncode == 0
            and rollout_path.is_file()
            and summary_path.is_file()
            and resolved_path.is_file()
        ):
            rows = _read_jsonl(rollout_path)
            summary = load_json(summary_path)
            validate_wall_contact_resolved_config(
                configured=load_yaml(Path(str(manifest["config_path"]))),
                resolved=load_yaml(resolved_path),
                run_root=run_root,
            )
            report = build_wall_contact_rollout_report(
                rows=rows,
                summary=summary,
                max_shovels=PROBE_MAX_SHOVELS,
            )
            baseline_path = _verify_ref(
                _mapping(manifest["source_lock"], "source_lock")[
                    "baseline_rollout_jsonl"
                ],
                "baseline_rollout_jsonl",
            )
            expected_reset = rollout_reset_state(
                _read_jsonl(baseline_path)[0]
            )
            reset_fairness = validate_reset_pair(
                expected_reset_state=expected_reset,
                reset_a=expected_reset,
                reset_b=rollout_reset_state(rows[0]),
            )
            report["reset_fairness"] = reset_fairness
            if not reset_fairness["valid"]:
                report["status"] = "failed"
                report["outcome"] = "inconclusive"
                report["blockers"] = list(reset_fairness["violations"])
        else:
            blockers = []
            if returncode != 0:
                blockers.append(f"eval_process_returncode:{returncode}")
            if not rollout_path.is_file():
                blockers.append("rollout_jsonl_missing")
            if not summary_path.is_file():
                blockers.append("rollout_summary_missing")
            if not resolved_path.is_file():
                blockers.append("resolved_config_missing")
            report = _failed_report(*blockers)
    except Exception as exc:
        report = _failed_report(
            f"rollout_evidence_invalid:{type(exc).__name__}:{exc}"
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
        "attempt_started": (
            artifact_ref(marker_path) if marker_path.is_file() else None
        ),
        "execution": (
            artifact_ref(execution_path) if execution_path.is_file() else None
        ),
        "rollout_jsonl": (
            artifact_ref(rollout_path) if rollout_path.is_file() else None
        ),
        "rollout_summary": (
            artifact_ref(summary_path) if summary_path.is_file() else None
        ),
        "resolved_config": (
            artifact_ref(resolved_path) if resolved_path.is_file() else None
        ),
        "diagnostic_only": True,
        "non_promotable": True,
        "writes_training_hdf5": False,
        "downstream_gates": dict(_DOWNSTREAM_GATES),
    }
    write_json_x(report_path, report)
    return report


def _failed_report(*blockers: str) -> dict[str, Any]:
    return {
        "schema": REPORT_SCHEMA,
        "status": "failed",
        "outcome": "attempt_failed",
        "blockers": list(blockers),
        "max_shovels": PROBE_MAX_SHOVELS,
        "started_shovel_count": 0,
        "completed_dump_count": 0,
        "partial_shovel_count": 0,
        "shovels": [],
    }


def _validate_baseline_outcome(
    summary: Mapping[str, Any],
    reset_validation: Mapping[str, Any],
) -> dict[str, Any]:
    counts = {
        "completed_dump_count": _strict_int(
            summary.get("completed_dump_count"),
            "completed_dump_count",
        ),
        "target_cycle_completed_dump_count": _strict_int(
            summary.get("target_cycle_completed_dump_count"),
            "target_cycle_completed_dump_count",
        ),
        "coverage_completed_dump_count": _strict_int(
            summary.get("coverage_completed_dump_count"),
            "coverage_completed_dump_count",
        ),
        "completed_full_cycle_count": _strict_int(
            reset_validation.get("completed_full_cycle_count"),
            "completed_full_cycle_count",
        ),
    }
    if set(counts.values()) != {7}:
        raise WallContactRolloutDiagnosticError(
            "baseline_seven_dump_contract_invalid"
        )
    reset_id = str(reset_validation.get("reset_id", ""))
    if reset_id not in {"seed_1000", "seed-1000"}:
        raise WallContactRolloutDiagnosticError(
            "baseline_reset_seed_invalid"
        )
    stop_reason = str(summary.get("rollout_stop_reason", ""))
    if stop_reason != "box_safety:wall_contact_terminal":
        raise WallContactRolloutDiagnosticError(
            "baseline_stop_reason_invalid"
        )
    return {
        "completed_dump_count": 7,
        "started_cycle_count": 8,
        "reset_id": reset_id,
        "stop_reason": stop_reason,
    }


def _validate_source_config(
    config: Mapping[str, Any],
) -> dict[str, Any]:
    task = _mapping(config.get("task"), "task")
    eval_config = _mapping(config.get("eval"), "eval")
    policy = _mapping(config.get("policy"), "policy")
    if (
        list(task.get("camera_names", []))
        != ["stick_up", "stick_down", "eye_left", "eye_right"]
        or _strict_int(task.get("episode_len"), "episode_len") != 24000
        or _strict_int(eval_config.get("num_rollouts"), "num_rollouts") != 1
        or _strict_int(
            eval_config.get("target_cycle_gate"), "target_cycle_gate"
        )
        != PROBE_MAX_SHOVELS
        or eval_config.get("temporal_agg") is not True
    ):
        raise WallContactRolloutDiagnosticError(
            "baseline_config_contract_invalid"
        )
    configured_seed = eval_config.get("seed", PROBE_SEED)
    if _strict_int(configured_seed, "seed") != PROBE_SEED:
        raise WallContactRolloutDiagnosticError(
            "baseline_reset_seed_invalid"
        )
    act = _mapping(policy.get("act_params"), "act_params")
    if _strict_int(act.get("chunk_size"), "chunk_size") != 100:
        raise WallContactRolloutDiagnosticError(
            "baseline_temporal_contract_invalid"
        )
    planner = _mapping(policy.get("dig_cut_planner"), "dig_cut_planner")
    if planner.get("mode") != "operator_prior_sweep_belief":
        raise WallContactRolloutDiagnosticError(
            "baseline_planner_mode_invalid"
        )
    safety = _mapping(
        _mapping(policy.get("box_emptying"), "box_emptying").get("safety"),
        "safety",
    )
    if float(safety.get("wall_high_force_n", 0.0)) != 100_000.0:
        raise WallContactRolloutDiagnosticError(
            "baseline_wall_force_threshold_invalid"
        )
    expected_stuck = {
        "stuck_action_l1_min": 0.1,
        "stuck_window_steps": 50,
        "stuck_qpos_max_change": 0.005,
        "stuck_bucket_tip_max_displacement_m": 0.02,
    }
    for field, expected in expected_stuck.items():
        if float(safety.get(field, -1.0)) != float(expected):
            raise WallContactRolloutDiagnosticError(
                f"baseline_safety_threshold_invalid:{field}"
            )
    switch = _mapping(policy.get("switch"), "switch")
    if (
        _strict_int(switch.get("return_max_steps"), "return_max_steps")
        != 420
        or _strict_int(
            switch.get("dig_bad_replan_max_steps"),
            "dig_bad_replan_max_steps",
        )
        != 220
    ):
        raise WallContactRolloutDiagnosticError(
            "baseline_timeout_contract_invalid"
        )
    act_artifacts = lock_act_artifacts(
        eval_config=eval_config,
        policy=policy,
        repo_root=Path(__file__).resolve().parents[2],
    )
    prior = _resolve_config_artifact(
        planner.get("prior_path"),
        "planner_prior",
        repo_root=Path(__file__).resolve().parents[2],
    )
    return {
        **act_artifacts,
        "planner_prior": artifact_ref(prior),
    }


def _build_diagnostic_config(
    source: Mapping[str, Any],
    *,
    run_root: Path,
) -> dict[str, Any]:
    config = copy.deepcopy(dict(source))
    eval_config = _mapping_mut(config, "eval")
    eval_config.update(
        {
            "num_rollouts": 1,
            "no_overwrite": True,
            "seed": PROBE_SEED,
            "video_dir": str(run_root / "videos"),
            "results_dir": str(run_root / "results"),
            "rollout_log_dir": str(run_root / "results/rollouts"),
            "record_hdf5": False,
            "hdf5_dir": str(run_root / "disabled_hdf5"),
            "target_cycle_gate": PROBE_MAX_SHOVELS,
        }
    )
    metadata = eval_config.setdefault("record_hdf5_metadata", {})
    if not isinstance(metadata, dict):
        raise WallContactRolloutDiagnosticError(
            "record_hdf5_metadata_invalid"
        )
    metadata.update(
        {
            "validation_schema": PROBE_SCHEMA,
            "contact_semantics_attempt_id": PROBE_ATTEMPT_ID,
            "contact_semantics_reset_seed": PROBE_SEED,
            "contact_semantics_diagnostic_variant": (
                "observe_only_all_bucket_contacts"
            ),
            "diagnostic_only": True,
            "promotion_eligible": False,
        }
    )
    policy = _mapping_mut(config, "policy")
    box = _mapping_mut(policy, "box_emptying")
    safety = _mapping_mut(box, "safety")
    safety.update(
        {
            "wall_first_touch_mode": "record_bucket_all_contacts",
            "wall_contact_diagnostic_ab_enabled": False,
            "wall_contact_diagnostic_observe_only_enabled": True,
        }
    )
    return config


def _validate_diagnostic_config(
    config: Mapping[str, Any],
    run_root: Path,
) -> None:
    eval_config = _mapping(config.get("eval"), "eval")
    required_eval = {
        "num_rollouts": 1,
        "no_overwrite": True,
        "seed": PROBE_SEED,
        "record_hdf5": False,
        "target_cycle_gate": PROBE_MAX_SHOVELS,
    }
    for field, expected in required_eval.items():
        if eval_config.get(field) != expected:
            raise WallContactRolloutDiagnosticError(
                f"diagnostic_eval_contract_drift:{field}"
            )
    expected_paths = {
        "video_dir": run_root / "videos",
        "results_dir": run_root / "results",
        "rollout_log_dir": run_root / "results/rollouts",
        "hdf5_dir": run_root / "disabled_hdf5",
    }
    for field, expected in expected_paths.items():
        if Path(str(eval_config.get(field, ""))).resolve() != expected:
            raise WallContactRolloutDiagnosticError(
                f"diagnostic_output_path_drift:{field}"
            )
    safety = _mapping(
        _mapping(
            _mapping(config.get("policy"), "policy").get("box_emptying"),
            "box_emptying",
        ).get("safety"),
        "safety",
    )
    required_safety = {
        "wall_first_touch_mode": "record_bucket_all_contacts",
        "wall_contact_diagnostic_ab_enabled": False,
        "wall_contact_diagnostic_observe_only_enabled": True,
        "wall_high_force_n": 100_000.0,
    }
    for field, expected in required_safety.items():
        if safety.get(field) != expected:
            raise WallContactRolloutDiagnosticError(
                f"diagnostic_safety_contract_drift:{field}"
            )


def _lock_environment(manifest_path: Path) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    source_lock = _mapping(manifest.get("source_lock"), "environment.source_lock")
    unity = _mapping(source_lock.get("unity"), "environment.unity")
    scene = _lock_path_and_sha(unity, "scene", "scene_path", "scene_sha256")
    normalization = _lock_path_and_sha(
        unity,
        "normalization",
        "normalization_path",
        "normalization_sha256",
    )
    raw_contact = unity.get("contact_lineage_files")
    if not isinstance(raw_contact, list) or not raw_contact:
        raise WallContactRolloutDiagnosticError(
            "environment_contact_lineage_missing"
        )
    contact_files = [
        artifact_ref(
            _required_file(
                _mapping(item, "contact_lineage_file").get("path"),
                "contact_lineage_file",
            )
        )
        for item in raw_contact
    ]
    for expected, observed in zip(raw_contact, contact_files, strict=True):
        if str(expected.get("sha256", "")).lower() != observed["sha256"]:
            raise WallContactRolloutDiagnosticError(
                "artifact_drift:contact_lineage_file"
            )
    return {
        "scene": scene,
        "normalization": normalization,
        "contact_lineage_files": contact_files,
        "contact_lineage_aggregate_sha256": str(
            unity.get("contact_lineage_aggregate_sha256", "")
        ),
    }


def _verify_environment_lock(
    lock: Mapping[str, Any],
    manifest_path: Path,
) -> None:
    current = _lock_environment(manifest_path)
    if current != lock:
        raise WallContactRolloutDiagnosticError(
            "artifact_drift:unity_environment"
        )


def _lock_path_and_sha(
    value: Mapping[str, Any],
    label: str,
    path_key: str,
    sha_key: str,
) -> dict[str, Any]:
    path = _required_file(value.get(path_key), label)
    observed = artifact_ref(path)
    if str(value.get(sha_key, "")).lower() != observed["sha256"]:
        raise WallContactRolloutDiagnosticError(
            f"artifact_drift:{label}"
        )
    return observed


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise WallContactRolloutDiagnosticError(
                f"rollout_jsonl_invalid:{line_number}"
            ) from exc
        rows.append(dict(_mapping(value, f"rollout_row_{line_number}")))
    if not rows:
        raise WallContactRolloutDiagnosticError("rollout_jsonl_empty")
    return rows


def _configured_command(config_path: Path, run_root: Path) -> list[str]:
    return [
        "python",
        "-m",
        "testbed.cli.eval",
        "--config",
        str(config_path),
        "--num-rollouts",
        "1",
        "--target-cycle-gate",
        str(PROBE_MAX_SHOVELS),
        "--output-dir",
        str(run_root),
    ]


def _execute_subprocess(command: list[str], cwd: Path, log_path: Path) -> int:
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


def _required_file(value: Any, label: str) -> Path:
    path = Path(str(value)).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"{label}_missing:{path}")
    return path


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise WallContactRolloutDiagnosticError(
            f"{label}_must_be_mapping"
        )
    return value


def _mapping_mut(value: dict[str, Any], key: str) -> dict[str, Any]:
    child = value.get(key)
    if not isinstance(child, dict):
        raise WallContactRolloutDiagnosticError(
            f"{key}_must_be_mapping"
        )
    return child


def _strict_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WallContactRolloutDiagnosticError(f"{label}_invalid")
    return value


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "DEFAULT_ENVIRONMENT_MANIFEST",
    "DEFAULT_OUTPUT_ROOT",
    "DEFAULT_SOURCE_CONFIG",
    "DEFAULT_SOURCE_RESET_VALIDATION",
    "DEFAULT_SOURCE_ROLLOUT",
    "DEFAULT_SOURCE_SUMMARY",
    "PROBE_ATTEMPT_ID",
    "PROBE_SCHEMA",
    "WallContactRolloutDiagnosticError",
    "collect_wall_contact_rollout_probe",
    "prepare_wall_contact_rollout_probe",
    "run_wall_contact_rollout_probe",
    "validate_wall_contact_rollout_probe",
]
