"""Exactly-once owner for the Unity wall-and-floor contact diagnostic.

The probe reuses the historical seven-dump Strict-18 baseline lock and the
existing wall-contact artifact mechanics.  Its request-local delta enables
Unity-only observe mode for finite sub-100 kN bucket contact with either a Dig
wall or FactoryFloor.  It never promotes the diagnostic into production.
"""

from __future__ import annotations

import copy
import os
import subprocess
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from testbed.eval.unity_contact_lineage import (
    lock_unity_contact_environment,
    verify_unity_contact_environment,
)
from testbed.eval.unity_contact_observe_only_report import (
    REPORT_SCHEMA,
    UNITY_DIAGNOSTIC_BACKEND,
    UnityContactObserveOnlyReportError,
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
    required_file,
    resolve_config_artifact,
    runtime_code_refs,
    runtime_command,
    validate_execution_lineage,
    validate_runtime_code_refs,
    verify_ref,
)
from testbed.eval.wall_contact_rollout_probe import (
    DEFAULT_ENVIRONMENT_MANIFEST,
    DEFAULT_SOURCE_CONFIG,
    DEFAULT_SOURCE_RESET_VALIDATION,
    DEFAULT_SOURCE_ROLLOUT,
    DEFAULT_SOURCE_SUMMARY,
)
from testbed.eval.wall_contact_rollout_probe import (
    _read_jsonl as read_jsonl,
)
from testbed.eval.wall_contact_rollout_probe import (
    _validate_baseline_outcome as validate_baseline_outcome,
)

PROBE_SCHEMA = "unity_contact_observe_only_rollout_probe_v1"
PROBE_ATTEMPT_ID = "strict18_seed_1000_unity_contact_observe_only_1x10"
PROBE_START_SCHEMA = "unity_contact_observe_only_attempt_started_v1"
PROBE_EXECUTION_SCHEMA = "unity_contact_observe_only_execution_v1"
PROBE_MAX_SHOVELS = 10
PROBE_SEED = 1000

_EVAL_ROOT = Path("/data/pingfan/excavator_testbed_runs/eval") / (
    "yulong_strict18_terrain_residual_v0"
)
DEFAULT_OUTPUT_ROOT = (
    _EVAL_ROOT / "unity_contact_observe_only_multicycle_diagnostic_v1"
)
Executor = Callable[[list[str], Path, Path], int]
HostProbe = Callable[[Mapping[str, Any]], Mapping[str, Any]]

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
    {
        "path": (
            "policy.box_emptying.safety."
            "unity_contact_diagnostic_observe_only_enabled"
        ),
        "baseline_effective": False,
        "diagnostic": True,
    },
    {
        "path": (
            "policy.box_emptying.safety."
            "unity_contact_diagnostic_backend"
        ),
        "baseline_effective": "",
        "diagnostic": UNITY_DIAGNOSTIC_BACKEND,
    },
]
_HARD_STOP_CONTRACT = {
    "finite_bucket_wall_or_factory_floor_below_n": (
        "observe_only_strictly_below_100000"
    ),
    "wall_or_factory_floor_force_at_or_above_n": 100_000.0,
    "force_at_or_above_threshold": "terminal_neutral",
    "boom_contact": "terminal_neutral",
    "stick_contact": "terminal_neutral",
    "other_or_ambiguous_component": "terminal_neutral",
    "nonfinite_or_invalid_lineage": "terminal_neutral",
    "typed_hard_bottom_contact": (
        "bypassed_only_in_explicit_agx_unity_diagnostic"
    ),
    "hard_bottom_depth_budget_guard": (
        "bypassed_only_in_explicit_agx_unity_diagnostic"
    ),
    "stuck": "terminal_neutral",
    "timeout": "existing_terminal_stop",
}
_DOWNSTREAM_GATES = {
    "production_contact_contract_change_allowed": False,
    "continuous_predictor_allowed": False,
    "offline_e0_g1_w1_allowed": False,
    "bounded_live_allowed": False,
    "functional_1x10_allowed": False,
}
_DIAGNOSTIC_CODE_PATHS = (
    "testbed/eval/wall_contact_artifact_io.py",
    "testbed/eval/wall_contact_config_contracts.py",
    "testbed/eval/wall_contact_evidence_contracts.py",
    "testbed/eval/wall_contact_rollout_integrity.py",
    "testbed/eval/unity_contact_lineage.py",
    "testbed/eval/unity_contact_observe_only_report.py",
    "testbed/eval/unity_host_identity.py",
    "testbed/eval/unity_contact_rollout_probe.py",
    "testbed/cli/unity_contact_rollout_probe.py",
)


def prepare_unity_contact_rollout_probe(
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
    """Create a no-overwrite config and immutable source manifest."""

    sources = {
        "baseline_config": required_file(
            source_config_path, "baseline_config"
        ),
        "baseline_rollout_jsonl": required_file(
            source_rollout_path, "baseline_rollout_jsonl"
        ),
        "baseline_rollout_summary": required_file(
            source_summary_path, "baseline_rollout_summary"
        ),
        "baseline_reset_validation": required_file(
            source_reset_validation_path,
            "baseline_reset_validation",
        ),
        "environment_manifest": required_file(
            environment_manifest_path,
            "environment_manifest",
        ),
    }
    source_config = load_yaml(sources["baseline_config"])
    baseline_outcome = validate_baseline_outcome(
        load_json(sources["baseline_rollout_summary"]),
        load_json(sources["baseline_reset_validation"]),
    )
    source_contract = _source_contract(source_config)
    environment_lock = lock_unity_contact_environment(
        sources["environment_manifest"]
    )
    root = Path(output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=False)
    config_path = (
        root / "configs" / f"{PROBE_ATTEMPT_ID}.yaml"
    )
    manifest_path = root / "manifest.json"
    run_root = root / "run"
    config = _build_config(source_config, run_root=run_root)
    write_yaml_x(config_path, config)
    repo_root = Path(__file__).resolve().parents[2]
    source_lock = {
        **{key: artifact_ref(path) for key, path in sources.items()},
        "checkpoints": source_contract["checkpoints"],
        "dataset_stats": source_contract["dataset_stats"],
        "planner_prior": source_contract["planner_prior"],
        "unity": environment_lock,
        "agx": source_contract["agx"],
        "diagnostic_config": artifact_ref(config_path),
        "runtime_code": runtime_code_refs(repo_root),
        "diagnostic_code": _diagnostic_code_refs(repo_root),
    }
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
        "command_argv": _configured_command(config_path, run_root),
        "baseline_outcome": baseline_outcome,
        "runtime_semantic_delta": copy.deepcopy(
            _RUNTIME_SEMANTIC_DELTA
        ),
        "parent_contact_lineage_drift_expected_due_to_this_diagnostic": True,
        "allowed_parent_contact_lineage_drift_files": list(
            environment_lock[
                "allowed_parent_contact_lineage_drift_files"
            ]
        ),
        "operational_deltas": {
            "output_root": "request_local_no_overwrite",
            "num_rollouts": 1,
            "max_attempts": 1,
            "retry_allowed": False,
            "record_hdf5": False,
            "explicit_seed_preserves_implicit_default": PROBE_SEED,
        },
        "observe_only_contract": {
            "backend": UNITY_DIAGNOSTIC_BACKEND,
            "allowed_component": "bucket",
            "allowed_sources": ["dig_area_wall", "FactoryFloor"],
            "force_must_be_finite": True,
            "force_strictly_below_n": 100_000.0,
            "session_count_limited": False,
            "duration_limited": False,
            "contact_region_limited": False,
            "wall_identity_limited": False,
            "hard_bottom_depth_warning_enabled": False,
            "hard_bottom_takeover_enabled": False,
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
    return validate_unity_contact_rollout_probe(manifest_path)


def validate_unity_contact_rollout_probe(
    manifest_path: str | Path,
) -> dict[str, Any]:
    """Fail closed on source, code, config, command, or Unity drift."""

    path = required_file(manifest_path, "probe_manifest")
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
        "parent_contact_lineage_drift_expected_due_to_this_diagnostic": True,
    }
    for field, expected in required.items():
        if manifest.get(field) != expected:
            raise UnityContactObserveOnlyReportError(
                f"probe_manifest_contract_invalid:{field}"
            )
    if (
        manifest.get("runtime_semantic_delta")
        != _RUNTIME_SEMANTIC_DELTA
        or manifest.get("hard_stop_contract") != _HARD_STOP_CONTRACT
        or manifest.get("downstream_gates") != _DOWNSTREAM_GATES
    ):
        raise UnityContactObserveOnlyReportError(
            "probe_manifest_semantics_drift"
        )
    root = path.parent.resolve()
    if Path(str(manifest.get("manifest_path", ""))).resolve() != path:
        raise UnityContactObserveOnlyReportError(
            "probe_manifest_path_drift"
        )
    config_path = required_file(
        manifest.get("config_path"),
        "diagnostic_config",
    )
    run_root = Path(str(manifest.get("run_root", ""))).resolve()
    if (
        config_path
        != root / "configs" / f"{PROBE_ATTEMPT_ID}.yaml"
        or run_root != root / "run"
    ):
        raise UnityContactObserveOnlyReportError(
            "probe_output_path_drift"
        )
    lock = _mapping(manifest.get("source_lock"), "source_lock")
    unity_lock = _mapping(lock.get("unity"), "unity")
    if manifest.get(
        "allowed_parent_contact_lineage_drift_files"
    ) != unity_lock.get("allowed_parent_contact_lineage_drift_files"):
        raise UnityContactObserveOnlyReportError(
            "probe_unity_drift_scope_invalid"
        )
    locked = {
        field: verify_ref(lock.get(field), field)
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
    stats = _mapping(lock.get("dataset_stats"), "dataset_stats")
    for primitive in ("dig", "carry", "dump", "return"):
        verify_ref(
            checkpoints.get(primitive),
            f"{primitive}_checkpoint",
        )
        verify_ref(
            stats.get(primitive),
            f"{primitive}_dataset_stats",
        )
    verify_ref(lock.get("planner_prior"), "planner_prior")
    repo_root = Path(__file__).resolve().parents[2]
    validate_runtime_code_refs(
        lock.get("runtime_code"),
        repo_root=repo_root,
    )
    _validate_diagnostic_code_refs(
        lock.get("diagnostic_code"),
        repo_root=repo_root,
    )
    verify_unity_contact_environment(
        unity_lock,
        locked["environment_manifest"],
    )
    source_config = load_yaml(locked["baseline_config"])
    baseline_outcome = validate_baseline_outcome(
        load_json(locked["baseline_rollout_summary"]),
        load_json(locked["baseline_reset_validation"]),
    )
    if baseline_outcome != manifest.get("baseline_outcome"):
        raise UnityContactObserveOnlyReportError(
            "baseline_outcome_lineage_drift"
        )
    source_contract = _source_contract(source_config)
    if (
        source_contract["checkpoints"] != checkpoints
        or source_contract["dataset_stats"] != stats
        or source_contract["planner_prior"] != lock.get("planner_prior")
        or source_contract["agx"] != lock.get("agx")
    ):
        raise UnityContactObserveOnlyReportError(
            "source_config_artifact_lineage_drift"
        )
    expected_config = _build_config(
        source_config,
        run_root=run_root,
    )
    observed_config = load_yaml(config_path)
    if observed_config != expected_config:
        raise UnityContactObserveOnlyReportError(
            "diagnostic_config_contract_drift"
        )
    _validate_config(observed_config, run_root=run_root)
    expected_command = _configured_command(config_path, run_root)
    if manifest.get("command_argv") != expected_command:
        raise UnityContactObserveOnlyReportError(
            "probe_command_lineage_drift"
        )
    return manifest


def run_unity_contact_rollout_probe(
    *,
    manifest_path: str | Path,
    executor: Executor | None = None,
    host_probe: HostProbe | None = None,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Consume and execute the sole permitted rollout attempt."""

    manifest = validate_unity_contact_rollout_probe(manifest_path)
    run_root = Path(str(manifest["run_root"]))
    if run_root.exists():
        raise FileExistsError(
            f"diagnostic attempt already consumed: {run_root}"
        )
    agx_lock = _mapping(
        _mapping(
            manifest.get("source_lock"),
            "source_lock",
        ).get("agx"),
        "agx",
    )
    host_evidence = _validate_unity_host_evidence(
        (host_probe or _probe_agx_unity_host)(agx_lock),
        agx=agx_lock,
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
    run_executor = executor or _execute_subprocess
    process_exception = ""
    try:
        returncode = int(
            run_executor(command, execution_cwd, log_path)
        )
    except Exception as exc:  # exactly-once failures remain evidence
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
    return collect_unity_contact_rollout_probe(
        manifest_path=manifest_path
    )


def collect_unity_contact_rollout_probe(
    *,
    manifest_path: str | Path,
) -> dict[str, Any]:
    """Collect the consumed attempt into one immutable diagnostic report."""

    manifest = validate_unity_contact_rollout_probe(manifest_path)
    run_root = Path(str(manifest["run_root"]))
    if not run_root.is_dir():
        raise FileNotFoundError(f"diagnostic attempt missing: {run_root}")
    marker_path = run_root / "attempt_started.json"
    execution_path = run_root / "execution.json"
    report_path = run_root / "report.json"
    if report_path.exists():
        raise FileExistsError(
            f"diagnostic report already exists: {report_path}"
        )
    rollout_path = run_root / "results/rollouts/rollout_000.jsonl"
    summary_path = (
        run_root / "results/rollouts/rollout_000_summary.json"
    )
    resolved_path = run_root / "results/eval_resolved_config.yaml"
    returncode = -1
    host_evidence: dict[str, Any] | None = None
    try:
        marker = load_json(
            required_file(marker_path, "attempt_started")
        )
        execution = load_json(
            required_file(execution_path, "execution")
        )
        validate_execution_lineage(
            marker,
            execution,
            manifest,
            start_schema=PROBE_START_SCHEMA,
            execution_schema=PROBE_EXECUTION_SCHEMA,
            attempt_id=PROBE_ATTEMPT_ID,
            seed=PROBE_SEED,
        )
        host_evidence = _validate_unity_host_evidence(
            marker.get("unity_host_get_info"),
            agx=_mapping(
                _mapping(
                    manifest.get("source_lock"),
                    "source_lock",
                ).get("agx"),
                "agx",
            ),
        )
        returncode = int(execution.get("process_returncode", -1))
        if sorted(run_root.rglob("*.hdf5")):
            raise UnityContactObserveOnlyReportError(
                "unexpected_hdf5_artifact"
            )
        if (
            returncode == 0
            and rollout_path.is_file()
            and summary_path.is_file()
            and resolved_path.is_file()
        ):
            rows = read_jsonl(rollout_path)
            validate_wall_contact_resolved_config(
                configured=load_yaml(
                    Path(str(manifest["config_path"]))
                ),
                resolved=load_yaml(resolved_path),
                run_root=run_root,
            )
            report = build_unity_contact_observe_only_report(
                rows=rows,
                summary=load_json(summary_path),
                max_shovels=PROBE_MAX_SHOVELS,
            )
            baseline_path = verify_ref(
                _mapping(
                    manifest["source_lock"],
                    "source_lock",
                )["baseline_rollout_jsonl"],
                "baseline_rollout_jsonl",
            )
            expected_reset = rollout_reset_state(
                read_jsonl(baseline_path)[0]
            )
            reset_fairness = validate_reset_pair(
                expected_reset_state=expected_reset,
                reset_a=expected_reset,
                reset_b=rollout_reset_state(rows[0]),
            )
            report["reset_fairness"] = reset_fairness
            if not reset_fairness["valid"]:
                report["status"] = "failed"
                report["termination_category"] = "failed"
                report["blockers"] = list(
                    reset_fairness["violations"]
                )
        else:
            blockers = []
            if returncode != 0:
                blockers.append(
                    f"eval_process_returncode:{returncode}"
                )
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
        "downstream_gates": dict(_DOWNSTREAM_GATES),
    }
    write_json_x(report_path, report)
    return report


def _source_contract(config: Mapping[str, Any]) -> dict[str, Any]:
    agx = dict(_mapping(config.get("agx"), "agx"))
    if agx != {"host": "127.0.0.1", "port": 5057, "timeout": 10.0}:
        raise UnityContactObserveOnlyReportError(
            "baseline_agx_contract_invalid"
        )
    task = _mapping(config.get("task"), "task")
    eval_config = _mapping(config.get("eval"), "eval")
    policy = _mapping(config.get("policy"), "policy")
    if (
        list(task.get("camera_names", []))
        != ["stick_up", "stick_down", "eye_left", "eye_right"]
        or _strict_int(task.get("episode_len"), "episode_len") != 24000
        or _strict_int(
            eval_config.get("num_rollouts"),
            "num_rollouts",
        )
        != 1
        or _strict_int(
            eval_config.get("target_cycle_gate"),
            "target_cycle_gate",
        )
        != PROBE_MAX_SHOVELS
        or eval_config.get("temporal_agg") is not True
    ):
        raise UnityContactObserveOnlyReportError(
            "baseline_config_contract_invalid"
        )
    if _strict_int(
        eval_config.get("seed", PROBE_SEED),
        "seed",
    ) != PROBE_SEED:
        raise UnityContactObserveOnlyReportError(
            "baseline_reset_seed_invalid"
        )
    if _strict_int(
        _mapping(policy.get("act_params"), "act_params").get(
            "chunk_size"
        ),
        "chunk_size",
    ) != 100:
        raise UnityContactObserveOnlyReportError(
            "baseline_temporal_contract_invalid"
        )
    planner = _mapping(
        policy.get("dig_cut_planner"),
        "dig_cut_planner",
    )
    if planner.get("mode") != "operator_prior_sweep_belief":
        raise UnityContactObserveOnlyReportError(
            "baseline_planner_mode_invalid"
        )
    safety = _mapping(
        _mapping(
            policy.get("box_emptying"),
            "box_emptying",
        ).get("safety"),
        "safety",
    )
    expected_safety = {
        "wall_high_force_n": 100_000.0,
        "stuck_action_l1_min": 0.1,
        "stuck_window_steps": 50,
        "stuck_qpos_max_change": 0.005,
        "stuck_bucket_tip_max_displacement_m": 0.02,
    }
    for field, expected in expected_safety.items():
        if float(safety.get(field, -1.0)) != float(expected):
            raise UnityContactObserveOnlyReportError(
                f"baseline_safety_threshold_invalid:{field}"
            )
    switch = _mapping(policy.get("switch"), "switch")
    if (
        _strict_int(
            switch.get("return_max_steps"),
            "return_max_steps",
        )
        != 420
        or _strict_int(
            switch.get("dig_bad_replan_max_steps"),
            "dig_bad_replan_max_steps",
        )
        != 220
    ):
        raise UnityContactObserveOnlyReportError(
            "baseline_timeout_contract_invalid"
        )
    artifacts = lock_act_artifacts(
        eval_config=eval_config,
        policy=policy,
        repo_root=Path(__file__).resolve().parents[2],
    )
    prior = resolve_config_artifact(
        planner.get("prior_path"),
        "planner_prior",
        repo_root=Path(__file__).resolve().parents[2],
    )
    return {
        **artifacts,
        "planner_prior": artifact_ref(prior),
        "agx": agx,
    }


def _build_config(
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
        raise UnityContactObserveOnlyReportError(
            "record_hdf5_metadata_invalid"
        )
    metadata.update(
        {
            "validation_schema": PROBE_SCHEMA,
            "contact_semantics_attempt_id": PROBE_ATTEMPT_ID,
            "contact_semantics_reset_seed": PROBE_SEED,
            "contact_semantics_diagnostic_variant": (
                "unity_wall_and_factory_floor_observe_only"
            ),
            "diagnostic_only": True,
            "promotion_eligible": False,
        }
    )
    safety = _mapping_mut(
        _mapping_mut(
            _mapping_mut(config, "policy"),
            "box_emptying",
        ),
        "safety",
    )
    safety.update(
        {
            "wall_first_touch_mode": "record_bucket_all_contacts",
            "wall_contact_diagnostic_ab_enabled": False,
            "wall_contact_diagnostic_observe_only_enabled": True,
            "unity_contact_diagnostic_observe_only_enabled": True,
            "unity_contact_diagnostic_backend": (
                UNITY_DIAGNOSTIC_BACKEND
            ),
        }
    )
    return config


def _validate_config(
    config: Mapping[str, Any],
    *,
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
            raise UnityContactObserveOnlyReportError(
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
            raise UnityContactObserveOnlyReportError(
                f"diagnostic_output_path_drift:{field}"
            )
    safety = _mapping(
        _mapping(
            _mapping(config.get("policy"), "policy").get(
                "box_emptying"
            ),
            "box_emptying",
        ).get("safety"),
        "safety",
    )
    required_safety = {
        "wall_first_touch_mode": "record_bucket_all_contacts",
        "wall_contact_diagnostic_ab_enabled": False,
        "wall_contact_diagnostic_observe_only_enabled": True,
        "unity_contact_diagnostic_observe_only_enabled": True,
        "unity_contact_diagnostic_backend": UNITY_DIAGNOSTIC_BACKEND,
        "wall_high_force_n": 100_000.0,
    }
    for field, expected in required_safety.items():
        if safety.get(field) != expected:
            raise UnityContactObserveOnlyReportError(
                f"diagnostic_safety_contract_drift:{field}"
            )


def _diagnostic_code_refs(repo_root: Path) -> list[dict[str, Any]]:
    return [
        artifact_ref((repo_root / relative).resolve())
        for relative in _DIAGNOSTIC_CODE_PATHS
    ]


def _validate_diagnostic_code_refs(
    value: Any,
    *,
    repo_root: Path,
) -> None:
    if (
        not isinstance(value, list)
        or len(value) != len(_DIAGNOSTIC_CODE_PATHS)
    ):
        raise UnityContactObserveOnlyReportError(
            "diagnostic_code_lock_invalid"
        )
    for index, (reference, relative) in enumerate(
        zip(value, _DIAGNOSTIC_CODE_PATHS, strict=True)
    ):
        if verify_ref(reference, f"diagnostic_code_{index}") != (
            repo_root / relative
        ).resolve():
            raise UnityContactObserveOnlyReportError(
                "diagnostic_code_lock_invalid"
            )


def _failed_report(*blockers: str) -> dict[str, Any]:
    return {
        "schema": REPORT_SCHEMA,
        "status": "failed",
        "termination_category": "failed",
        "blockers": list(blockers),
        "max_shovels": PROBE_MAX_SHOVELS,
        "started_shovel_count": 0,
        "completed_dump_count": 0,
        "partial_shovel_count": 0,
        "shovels": [],
    }


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
        str(PROBE_MAX_SHOVELS),
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


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise UnityContactObserveOnlyReportError(
            f"{label}_must_be_mapping"
        )
    return value


def _mapping_mut(value: dict[str, Any], key: str) -> dict[str, Any]:
    child = value.get(key)
    if not isinstance(child, dict):
        raise UnityContactObserveOnlyReportError(
            f"{key}_must_be_mapping"
        )
    return child


def _strict_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise UnityContactObserveOnlyReportError(
            f"{label}_invalid"
        )
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
    "UnityContactObserveOnlyReportError",
    "collect_unity_contact_rollout_probe",
    "prepare_unity_contact_rollout_probe",
    "run_unity_contact_rollout_probe",
    "validate_unity_contact_rollout_probe",
]
