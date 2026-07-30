"""Independent exactly-once diagnostic for wall-contact session gap semantics."""

from __future__ import annotations

import copy
import math
import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from testbed.eval.wall_contact_ab_collection import (
    TARGET_EXEMPLAR_ID,
    TARGET_RAW_FIELDS_SHA256,
    extract_paired_ab_attempt,
    failed_paired_ab_attempt,
)
from testbed.eval.wall_contact_artifact_io import (
    artifact_ref,
    json_sha256,
    load_json,
    load_yaml,
    mapping,
    mapping_mut,
    required_file,
    sha256_file,
    sha256_value,
    write_json_x,
    write_yaml_x,
)
from testbed.eval.wall_contact_session_gap_evidence import (
    build_session_gap_report,
    lock_b2_code_lineage,
    lock_original_environment,
    summarize_session_gap_evidence,
)

PROBE_SCHEMA = "wall_contact_session_gap_probe_v1"
PROBE_ATTEMPT_ID = "seed_2_B2"
PROBE_ATTEMPT_SCHEMA = "wall_contact_session_gap_probe_attempt_v1"
PROBE_START_MARKER_SCHEMA = "wall_contact_session_gap_probe_started_v1"
PROBE_EXECUTION_SCHEMA = "wall_contact_session_gap_probe_execution_v1"
PROBE_REPORT_SCHEMA = "wall_contact_session_gap_probe_report_v1"
PROBE_CLEAR_TICKS = 2
PROBE_SEED = 2

DEFAULT_SOURCE_ROOT = Path(
    "/data/pingfan/excavator_testbed_runs/eval/"
    "yulong_strict18_terrain_residual_v0/"
    "wall_contact_semantics_recovery_v1"
)
DEFAULT_SOURCE_CONFIG = (
    DEFAULT_SOURCE_ROOT / "paired_ab" / "configs" / "seed_2_B.yaml"
)
DEFAULT_SOURCE_ATTEMPT = (
    DEFAULT_SOURCE_ROOT
    / "reanalysis_v4"
    / "paired_ab"
    / "reextracted"
    / "attempts"
    / "seed_2_B.json"
)
DEFAULT_EXPECTED_RESET_STATE = (
    DEFAULT_SOURCE_ROOT
    / "source_lock"
    / "ab_lineage"
    / "expected_reset_state.json"
)
DEFAULT_OUTPUT_ROOT = Path(
    "/data/pingfan/excavator_testbed_runs/eval/"
    "yulong_strict18_terrain_residual_v0/"
    "wall_contact_session_gap_diagnostic_b2_v1"
)

Executor = Callable[[list[str], Path, Path], int]
_OUTPUT_FIELDS = ("video_dir", "results_dir", "rollout_log_dir", "hdf5_dir")
_DOWNSTREAM_GATES = {
    "contact_budget_freeze_allowed": False,
    "continuous_predictor_allowed": False,
    "offline_e0_g1_w1_allowed": False,
    "bounded_live_allowed": False,
    "functional_1x10_allowed": False,
}
_SESSION_END_CONTRACT = {
    "contact_free_ticks_required": PROBE_CLEAR_TICKS,
    "single_contact_free_tick_remains_same_logical_session": True,
    "nominal_tick_duration_s": 0.02,
    "physical_session_owner": "unity_worktool_wall_contact_detail_v1",
    "logical_session_owner": "python_diagnostic_b2",
}
_RUNTIME_SEMANTIC_DIFF = [
    {
        "path": (
            "policy.box_emptying.safety."
            "wall_contact_session_end_clear_ticks"
        ),
        "source_effective": 1,
        "probe": PROBE_CLEAR_TICKS,
    }
]
_ALLOWED_NONSEMANTIC_DIFF_PATHS = [
    *(f"eval.{field}" for field in _OUTPUT_FIELDS),
    "eval.record_hdf5_metadata.validation_schema",
    "eval.record_hdf5_metadata.contact_semantics_attempt_id",
    "eval.record_hdf5_metadata.contact_semantics_diagnostic_variant",
]
class WallContactSessionGapProbeError(RuntimeError):
    """Raised when the B2 one-factor or exactly-once contract is unsafe."""
def prepare_wall_contact_session_gap_probe(
    *,
    source_config_path: str | Path = DEFAULT_SOURCE_CONFIG,
    source_attempt_path: str | Path = DEFAULT_SOURCE_ATTEMPT,
    expected_reset_state_path: str | Path | None = None,
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
) -> dict[str, Any]:
    """Create a fresh B2 root from the immutable seed-2 B evidence."""

    source_config_path = required_file(
        source_config_path,
        "b2_source_seed_2_B_config",
    )
    source_attempt_path = required_file(
        source_attempt_path,
        "b2_source_seed_2_B_attempt",
    )
    source_config = load_yaml(source_config_path)
    source_attempt = load_json(source_attempt_path)
    source_lineage = _validate_source_lineage(
        config=source_config,
        attempt=source_attempt,
    )
    original_environment = lock_original_environment(source_config_path)
    if (
        source_config_path == DEFAULT_SOURCE_CONFIG.resolve()
        and original_environment.get("status") != "verified"
    ):
        raise WallContactSessionGapProbeError(
            "original_environment_lock_missing"
        )
    if (
        original_environment.get("status") == "verified"
        and original_environment["frozen_target_handoff"]["sha256"]
        != source_lineage["frozen_target_handoff_sha256"]
    ):
        raise WallContactSessionGapProbeError("frozen_target_lineage_drift")
    if expected_reset_state_path is None:
        relative_reset = (
            Path("source_lock")
            / "ab_lineage"
            / "expected_reset_state.json"
        )
        candidates = [
            source_config_path.parent / relative_reset,
            source_config_path.parents[2] / relative_reset,
        ]
        expected_reset_state_path = next(
            (candidate for candidate in candidates if candidate.is_file()),
            candidates[-1],
        )
    expected_reset_state_path = required_file(
        expected_reset_state_path,
        "b2_frozen_expected_reset_state",
    )
    expected_reset_state = load_json(expected_reset_state_path)
    _validate_expected_reset_state(
        expected_reset_state,
        expected_sha256=source_lineage["expected_reset_state_sha256"],
        path=expected_reset_state_path,
    )

    root = Path(output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=False)
    config_path = root / "configs" / f"{PROBE_ATTEMPT_ID}.yaml"
    run_root = root / "run"
    manifest_path = root / "manifest.json"

    probe_config = _build_probe_config(
        source_config=source_config,
        run_root=run_root,
    )
    write_yaml_x(config_path, probe_config)
    command = _configured_command(config_path=config_path, run_root=run_root)
    manifest = {
        "schema": PROBE_SCHEMA,
        "status": "prepared",
        "blockers": [],
        "attempt_id": PROBE_ATTEMPT_ID,
        "source_attempt_id": "seed_2_B",
        "diagnostic_variant": "B2",
        "seed": PROBE_SEED,
        "condition": "B",
        "max_attempts": 1,
        "retry_allowed": False,
        "retry_count": 0,
        "execution_order": [PROBE_ATTEMPT_ID],
        "session_end_contract": dict(_SESSION_END_CONTRACT),
        "runtime_semantic_diff": copy.deepcopy(_RUNTIME_SEMANTIC_DIFF),
        "allowed_nonsemantic_diff_paths": list(
            _ALLOWED_NONSEMANTIC_DIFF_PATHS
        ),
        "config_path": str(config_path),
        "run_root": str(run_root),
        "manifest_path": str(manifest_path),
        "command_argv": command,
        "target_lineage": {
            "exemplar_id": TARGET_EXEMPLAR_ID,
            "raw_fields_sha256": TARGET_RAW_FIELDS_SHA256,
            "runtime_role": "diagnostic_legacy",
            "production_lookup_allowed": False,
            "frozen_target_handoff_sha256": source_lineage[
                "frozen_target_handoff_sha256"
            ],
        },
        "reset_lineage": {
            "checkpoint_semantics": (
                "first_post_reset_control_step"
            ),
            "expected_reset_state_sha256": source_lineage[
                "expected_reset_state_sha256"
            ],
            "expected_reset_state": artifact_ref(expected_reset_state_path),
            "source_reset_state": copy.deepcopy(source_attempt["reset_state"]),
        },
        "source_lock": {
            "baseline_config": artifact_ref(source_config_path),
            "baseline_attempt": artifact_ref(source_attempt_path),
            "baseline_rollout_jsonl": source_lineage[
                "rollout_jsonl"
            ],
            "baseline_rollout_summary": source_lineage[
                "rollout_summary"
            ],
            "expected_reset_state": artifact_ref(
                expected_reset_state_path
            ),
            "checkpoints": copy.deepcopy(source_lineage["checkpoints"]),
            "original_environment": original_environment,
            "baseline_effective_config_sha256": _effective_config_sha256(
                source_config
            ),
            "probe_config": artifact_ref(config_path),
            "b2_code_lineage": lock_b2_code_lineage(
                Path(__file__).resolve().parents[2]
            ),
        },
        "baseline_outcome": {
            "entered_carry": bool(source_attempt.get("entered_carry", False)),
            "dump_completed": bool(source_attempt.get("dump_completed", False)),
            "terminal_reason": str(
                source_attempt.get("terminal_reason", "")
            ),
            "hard_stop_violations": list(
                source_attempt.get("hard_stop_violations", [])
            ),
        },
        "diagnostic_only": True,
        "non_promotable": True,
        "production_promotion_allowed": False,
        "writes_training_hdf5": False,
        "modifies_original_ab_conclusion": False,
        "downstream_gates": dict(_DOWNSTREAM_GATES),
    }
    write_json_x(manifest_path, manifest)
    return validate_wall_contact_session_gap_probe(manifest_path)


def validate_wall_contact_session_gap_probe(
    manifest_path: str | Path,
) -> dict[str, Any]:
    """Validate source hashes, one-factor config, paths, and run command."""

    path = required_file(manifest_path, "b2_manifest")
    manifest = load_json(path)
    if manifest.get("schema") != PROBE_SCHEMA:
        raise WallContactSessionGapProbeError("probe_manifest_schema_invalid")
    required_flags = {
        "status": "prepared",
        "attempt_id": PROBE_ATTEMPT_ID,
        "source_attempt_id": "seed_2_B",
        "diagnostic_variant": "B2",
        "seed": PROBE_SEED,
        "condition": "B",
        "max_attempts": 1,
        "retry_allowed": False,
        "retry_count": 0,
        "diagnostic_only": True,
        "non_promotable": True,
        "production_promotion_allowed": False,
        "writes_training_hdf5": False,
        "modifies_original_ab_conclusion": False,
    }
    for field, expected in required_flags.items():
        if manifest.get(field) != expected:
            raise WallContactSessionGapProbeError(
                f"probe_manifest_flag_invalid:{field}"
            )
    if manifest.get("downstream_gates") != _DOWNSTREAM_GATES:
        raise WallContactSessionGapProbeError(
            "probe_downstream_gate_contract_invalid"
        )
    if (
        manifest.get("session_end_contract") != _SESSION_END_CONTRACT
        or manifest.get("runtime_semantic_diff") != _RUNTIME_SEMANTIC_DIFF
        or manifest.get("allowed_nonsemantic_diff_paths")
        != _ALLOWED_NONSEMANTIC_DIFF_PATHS
    ):
        raise WallContactSessionGapProbeError(
            "probe_single_factor_manifest_drift"
        )

    root = path.parent.resolve()
    if Path(str(manifest.get("manifest_path", ""))).resolve() != path:
        raise WallContactSessionGapProbeError("probe_manifest_path_drift")
    config_path = required_file(
        manifest.get("config_path"),
        "b2_probe_config",
    )
    run_root = Path(str(manifest.get("run_root", ""))).resolve()
    if (
        config_path != root / "configs" / f"{PROBE_ATTEMPT_ID}.yaml"
        or run_root != root / "run"
    ):
        raise WallContactSessionGapProbeError("probe_output_path_drift")

    source_lock = mapping(manifest.get("source_lock"), "source_lock")
    source_config_path = _verify_artifact_lock(
        source_lock.get("baseline_config"),
        "baseline_config",
    )
    source_attempt_path = _verify_artifact_lock(
        source_lock.get("baseline_attempt"),
        "baseline_attempt",
    )
    _verify_artifact_lock(
        source_lock.get("baseline_rollout_jsonl"),
        "baseline_rollout_jsonl",
    )
    _verify_artifact_lock(
        source_lock.get("baseline_rollout_summary"),
        "baseline_rollout_summary",
    )
    expected_reset_path = _verify_artifact_lock(
        source_lock.get("expected_reset_state"),
        "expected_reset_state",
    )
    checkpoint_locks = mapping(
        source_lock.get("checkpoints"),
        "checkpoints",
    )
    for primitive in ("dig", "carry", "dump", "return"):
        _verify_artifact_lock(
            checkpoint_locks.get(primitive),
            f"{primitive}_checkpoint",
        )
    _verify_artifact_lock(source_lock.get("probe_config"), "probe_config")
    if source_lock.get("b2_code_lineage") != lock_b2_code_lineage(
        Path(__file__).resolve().parents[2]
    ):
        raise WallContactSessionGapProbeError("b2_code_lineage_drift")

    source_config = load_yaml(source_config_path)
    source_attempt = load_json(source_attempt_path)
    if lock_original_environment(source_config_path) != source_lock.get(
        "original_environment"
    ):
        raise WallContactSessionGapProbeError(
            "original_environment_artifact_drift"
        )
    source_lineage = _validate_source_lineage(
        config=source_config,
        attempt=source_attempt,
    )
    expected_reset_state = load_json(expected_reset_path)
    _validate_expected_reset_state(
        expected_reset_state,
        expected_sha256=source_lineage["expected_reset_state_sha256"],
        path=expected_reset_path,
    )
    reset_lineage = mapping(
        manifest.get("reset_lineage"),
        "reset_lineage",
    )
    if (
        reset_lineage.get("expected_reset_state")
        != source_lock.get("expected_reset_state")
        or reset_lineage.get("expected_reset_state_sha256")
        != source_lineage["expected_reset_state_sha256"]
    ):
        raise WallContactSessionGapProbeError(
            "expected_reset_state_lineage_drift"
        )
    if source_lock.get(
        "baseline_effective_config_sha256"
    ) != _effective_config_sha256(source_config):
        raise WallContactSessionGapProbeError(
            "baseline_effective_config_sha256_drift"
        )
    for field in ("rollout_jsonl", "rollout_summary"):
        if source_lineage[field] != source_lock[f"baseline_{field}"]:
            raise WallContactSessionGapProbeError(
                f"baseline_{field}_lineage_drift"
            )
    if source_lineage["checkpoints"] != checkpoint_locks:
        raise WallContactSessionGapProbeError(
            "checkpoint_source_lineage_drift"
        )

    expected_config = _build_probe_config(
        source_config=source_config,
        run_root=run_root,
    )
    observed_config = load_yaml(config_path)
    if observed_config != expected_config:
        raise WallContactSessionGapProbeError(
            "probe_config_lineage_drift"
        )
    _validate_probe_config(observed_config, run_root=run_root)
    expected_command = _configured_command(
        config_path=config_path,
        run_root=run_root,
    )
    if manifest.get("command_argv") != expected_command:
        raise WallContactSessionGapProbeError("probe_command_lineage_drift")
    return manifest


def run_wall_contact_session_gap_probe(
    *,
    manifest_path: str | Path,
    executor: Executor | None = None,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Execute seed 2 exactly once, then collect its immutable report."""

    manifest = validate_wall_contact_session_gap_probe(manifest_path)
    run_root = Path(str(manifest["run_root"]))
    if run_root.exists():
        raise FileExistsError(
            f"B2 diagnostic attempt already started: {run_root}"
        )
    run_root.mkdir(parents=True, exist_ok=False)
    marker_path = run_root / "attempt_started.json"
    log_path = run_root / "eval_process.log"
    execution_path = run_root / "execution.json"
    command = _runtime_command(manifest["command_argv"])
    execution_cwd = (
        Path(cwd).expanduser().resolve()
        if cwd is not None
        else Path(__file__).resolve().parents[2]
    )
    started_at = _utc_now()
    write_json_x(
        marker_path,
        {
            "schema": PROBE_START_MARKER_SCHEMA,
            "attempt_id": PROBE_ATTEMPT_ID,
            "seed": PROBE_SEED,
            "retry_count": 0,
            "started_at_utc": started_at,
            "manifest": artifact_ref(Path(str(manifest["manifest_path"]))),
            "configured_argv": list(manifest["command_argv"]),
            "executed_argv": command,
            "cwd": str(execution_cwd),
        },
    )
    log_path.open("x", encoding="utf-8").close()
    process_exception = ""
    run_executor = executor or _execute_subprocess
    try:
        returncode = int(run_executor(command, execution_cwd, log_path))
    except Exception as exc:  # retain the exactly-once failure as evidence
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
    return collect_wall_contact_session_gap_probe(
        manifest_path=manifest_path,
    )


def collect_wall_contact_session_gap_probe(
    *,
    manifest_path: str | Path,
) -> dict[str, Any]:
    """Collect the already-executed B2 attempt without invoking eval."""

    manifest = validate_wall_contact_session_gap_probe(manifest_path)
    run_root = Path(str(manifest["run_root"]))
    marker_path = required_file(
        run_root / "attempt_started.json",
        "b2_attempt_started",
    )
    execution_path = required_file(
        run_root / "execution.json",
        "b2_execution",
    )
    result_path = run_root / "attempt_result.json"
    report_path = run_root / "report.json"
    if result_path.exists() or report_path.exists():
        raise FileExistsError("B2 diagnostic result already collected")
    marker = load_json(marker_path)
    execution = load_json(execution_path)
    _validate_execution_lineage(
        marker=marker,
        execution=execution,
        manifest=manifest,
    )
    returncode = int(execution["process_returncode"])
    rollout_path = run_root / "results" / "rollouts" / "rollout_000.jsonl"
    summary_path = (
        run_root / "results" / "rollouts" / "rollout_000_summary.json"
    )
    expected = {
        "attempt_id": PROBE_ATTEMPT_ID,
        "pair_id": "seed_2",
        "sequence_index": 1,
        "seed": PROBE_SEED,
        "condition": "B",
        "wall_first_touch_mode": "record_bucket_first_session",
        "wall_contact_session_end_clear_ticks": PROBE_CLEAR_TICKS,
        "max_attempts": 1,
        "retry_allowed": False,
    }
    if rollout_path.is_file() and summary_path.is_file():
        try:
            attempt = extract_paired_ab_attempt(
                expected=expected,
                rollout_jsonl_path=rollout_path,
                rollout_summary_path=summary_path,
                process_returncode=returncode,
            )
        except Exception as exc:
            attempt = failed_paired_ab_attempt(
                expected=expected,
                returncode=returncode,
                blocker=(
                    "b2_rollout_extraction_failed:"
                    f"{type(exc).__name__}:{exc}"
                ),
            )
    else:
        attempt = failed_paired_ab_attempt(
            expected=expected,
            returncode=returncode,
            blocker="b2_complete_rollout_artifacts_missing",
        )
    attempt.update(
        {
            "b2_schema": PROBE_ATTEMPT_SCHEMA,
            "run_root": str(run_root),
            "retry_count": 0,
            "attempt_started": artifact_ref(marker_path),
            "execution": artifact_ref(execution_path),
            "diagnostic_only": True,
            "non_promotable": True,
            "writes_training_hdf5": False,
        }
    )
    write_json_x(result_path, attempt)
    contact_evidence = summarize_session_gap_evidence(
        rollout_path=rollout_path if rollout_path.is_file() else None,
        target_cycle=int(attempt.get("target_cycle_index", -1)),
        clear_ticks_required=PROBE_CLEAR_TICKS,
    )
    expected_reset = load_json(
        _verify_artifact_lock(
            mapping(manifest.get("source_lock"), "source_lock").get(
                "expected_reset_state"
            ),
            "expected_reset_state",
        )
    )
    report = build_session_gap_report(
        manifest=manifest,
        attempt=attempt,
        attempt_path=result_path,
        contact_evidence=contact_evidence,
        expected_reset=expected_reset,
        report_schema=PROBE_REPORT_SCHEMA,
        attempt_id=PROBE_ATTEMPT_ID,
        seed=PROBE_SEED,
        clear_ticks_required=PROBE_CLEAR_TICKS,
        target_exemplar_id=TARGET_EXEMPLAR_ID,
        target_raw_fields_sha256=TARGET_RAW_FIELDS_SHA256,
        downstream_gates=_DOWNSTREAM_GATES,
    )
    write_json_x(report_path, report)
    return report


def _build_probe_config(
    *,
    source_config: Mapping[str, Any],
    run_root: Path,
) -> dict[str, Any]:
    probe = copy.deepcopy(dict(source_config))
    eval_config = mapping_mut(probe, "eval")
    eval_config.update(
        {
            "num_rollouts": 1,
            "no_overwrite": True,
            "video_dir": str(run_root / "videos"),
            "results_dir": str(run_root / "results"),
            "rollout_log_dir": str(run_root / "results" / "rollouts"),
            "record_hdf5": False,
            "hdf5_dir": str(run_root / "disabled_hdf5"),
            "target_cycle_gate": 2,
            "target_cycle_gate_terminal_hold_steps": 0,
            "seed": PROBE_SEED,
        }
    )
    metadata = mapping_mut(eval_config, "record_hdf5_metadata")
    metadata["validation_schema"] = PROBE_ATTEMPT_SCHEMA
    metadata["contact_semantics_attempt_id"] = PROBE_ATTEMPT_ID
    metadata["contact_semantics_diagnostic_variant"] = "B2"
    policy = mapping_mut(probe, "policy")
    box = mapping_mut(policy, "box_emptying")
    safety = mapping_mut(box, "safety")
    source_clear_ticks = safety.get(
        "wall_contact_session_end_clear_ticks",
        1,
    )
    if source_clear_ticks != 1:
        raise WallContactSessionGapProbeError(
            "source_session_end_clear_ticks_not_baseline_one"
        )
    safety["wall_contact_session_end_clear_ticks"] = PROBE_CLEAR_TICKS
    return probe


def _validate_source_lineage(
    *,
    config: Mapping[str, Any],
    attempt: Mapping[str, Any],
) -> dict[str, Any]:
    expected_attempt = {
        "schema": "wall_contact_paired_ab_attempt_v1",
        "status": "passed",
        "attempt_id": "seed_2_B",
        "seed": PROBE_SEED,
        "condition": "B",
        "retry_count": 0,
        "selected_exemplar_id": TARGET_EXEMPLAR_ID,
        "selected_raw_fields_sha256": TARGET_RAW_FIELDS_SHA256,
        "reset_checkpoint_semantics": (
            "first_post_reset_control_step"
        ),
    }
    for field, expected in expected_attempt.items():
        if attempt.get(field) != expected:
            raise WallContactSessionGapProbeError(
                f"source_attempt_lineage_invalid:{field}"
            )
    reset = mapping(attempt.get("reset_state"), "source_reset_state")
    _validate_reset_state(reset)
    source_lock = mapping(attempt.get("source_lock"), "source_attempt_lock")
    rollout = _verify_artifact_lock(
        source_lock.get("rollout_jsonl"),
        "source_rollout_jsonl",
    )
    summary = _verify_artifact_lock(
        source_lock.get("rollout_summary"),
        "source_rollout_summary",
    )

    eval_config = mapping(config.get("eval"), "source.eval")
    if (
        eval_config.get("num_rollouts") != 1
        or eval_config.get("seed") != PROBE_SEED
        or eval_config.get("target_cycle_gate") != 2
        or eval_config.get("target_cycle_gate_terminal_hold_steps") != 0
        or eval_config.get("record_hdf5") is not False
    ):
        raise WallContactSessionGapProbeError(
            "source_eval_contract_invalid"
        )
    metadata = mapping(
        eval_config.get("record_hdf5_metadata"),
        "source.record_hdf5_metadata",
    )
    metadata_expected = {
        "contact_semantics_condition": "B",
        "contact_semantics_pair_id": "seed_2",
        "contact_semantics_attempt_id": "seed_2_B",
        "contact_semantics_reset_seed": PROBE_SEED,
        "diagnostic_only": True,
        "promotion_eligible": False,
    }
    for field, expected in metadata_expected.items():
        if metadata.get(field) != expected:
            raise WallContactSessionGapProbeError(
                f"source_metadata_lineage_invalid:{field}"
            )
    policy = mapping(config.get("policy"), "source.policy")
    planner = mapping(policy.get("dig_cut_planner"), "source.planner")
    coverage = mapping(planner.get("coverage"), "source.coverage")
    exact = mapping(
        coverage.get("actual_tuple_execution_library"),
        "source.actual_tuple_execution_library",
    )
    if exact.get("runtime_role") != "diagnostic_legacy":
        raise WallContactSessionGapProbeError(
            "source_exact_runtime_role_invalid"
        )
    box = mapping(policy.get("box_emptying"), "source.box_emptying")
    safety = mapping(box.get("safety"), "source.safety")
    if (
        safety.get("wall_contact_diagnostic_ab_enabled") is not True
        or safety.get("wall_first_touch_mode")
        != "record_bucket_first_session"
        or safety.get("wall_contact_session_end_clear_ticks", 1) != 1
    ):
        raise WallContactSessionGapProbeError(
            "source_contact_mode_invalid"
        )
    if (
        mapping(
            box.get("bounded_dig_probe_stop"),
            "source.bounded_dig_probe_stop",
        ).get("enabled")
        is not False
        or mapping(
            box.get("functional_cycle_gate"),
            "source.functional_cycle_gate",
        ).get("enabled")
        is not False
    ):
        raise WallContactSessionGapProbeError(
            "source_stop_wrapper_contract_invalid"
        )
    validator = mapping(
        box.get("contact_semantics_one_cycle_validator"),
        "source.one_cycle_validator",
    )
    if validator != {
        "enabled": True,
        "diagnostic_only": True,
        "target_exemplar_id": TARGET_EXEMPLAR_ID,
        "stop_on": ["target_dump_complete", "safety_terminal"],
    }:
        raise WallContactSessionGapProbeError(
            "source_one_cycle_validator_invalid"
        )
    checkpoints = {
        primitive: artifact_ref(
            required_file(
                policy.get(f"{primitive}_ckpt_path"),
                f"source_{primitive}_checkpoint",
            )
        )
        for primitive in ("dig", "carry", "dump", "return")
    }
    return {
        "rollout_jsonl": artifact_ref(rollout),
        "rollout_summary": artifact_ref(summary),
        "frozen_target_handoff_sha256": sha256_value(
            metadata.get("frozen_target_handoff_sha256"),
            "frozen_target_handoff_sha256",
        ),
        "expected_reset_state_sha256": sha256_value(
            metadata.get("expected_reset_state_sha256"),
            "expected_reset_state_sha256",
        ),
        "checkpoints": checkpoints,
    }


def _validate_probe_config(
    config: Mapping[str, Any],
    *,
    run_root: Path,
) -> None:
    eval_config = mapping(config.get("eval"), "probe.eval")
    required_eval = {
        "num_rollouts": 1,
        "no_overwrite": True,
        "record_hdf5": False,
        "target_cycle_gate": 2,
        "target_cycle_gate_terminal_hold_steps": 0,
        "seed": PROBE_SEED,
    }
    for field, expected in required_eval.items():
        if eval_config.get(field) != expected:
            raise WallContactSessionGapProbeError(
                f"probe_eval_contract_drift:{field}"
            )
    expected_paths = {
        "video_dir": run_root / "videos",
        "results_dir": run_root / "results",
        "rollout_log_dir": run_root / "results" / "rollouts",
        "hdf5_dir": run_root / "disabled_hdf5",
    }
    for field, expected in expected_paths.items():
        observed = Path(str(eval_config.get(field, ""))).resolve()
        if observed != expected:
            raise WallContactSessionGapProbeError(
                f"probe_output_path_drift:{field}"
            )
    metadata = mapping(
        eval_config.get("record_hdf5_metadata"),
        "probe.metadata",
    )
    if (
        metadata.get("validation_schema") != PROBE_ATTEMPT_SCHEMA
        or metadata.get("contact_semantics_attempt_id")
        != PROBE_ATTEMPT_ID
        or metadata.get("contact_semantics_diagnostic_variant") != "B2"
    ):
        raise WallContactSessionGapProbeError(
            "probe_metadata_contract_drift"
        )
    safety = mapping(
        mapping(
            mapping(config.get("policy"), "probe.policy").get(
                "box_emptying"
            ),
            "probe.box_emptying",
        ).get("safety"),
        "probe.safety",
    )
    if (
        safety.get("wall_contact_diagnostic_ab_enabled") is not True
        or safety.get("wall_first_touch_mode")
        != "record_bucket_first_session"
        or safety.get("wall_contact_session_end_clear_ticks")
        != PROBE_CLEAR_TICKS
    ):
        raise WallContactSessionGapProbeError(
            "probe_contact_mode_contract_drift"
        )


def _validate_execution_lineage(
    *,
    marker: Mapping[str, Any],
    execution: Mapping[str, Any],
    manifest: Mapping[str, Any],
) -> None:
    if (
        marker.get("schema") != PROBE_START_MARKER_SCHEMA
        or marker.get("attempt_id") != PROBE_ATTEMPT_ID
        or marker.get("seed") != PROBE_SEED
        or marker.get("retry_count") != 0
        or marker.get("configured_argv") != manifest.get("command_argv")
        or execution.get("schema") != PROBE_EXECUTION_SCHEMA
        or execution.get("attempt_id") != PROBE_ATTEMPT_ID
        or execution.get("seed") != PROBE_SEED
        or execution.get("retry_count") != 0
    ):
        raise WallContactSessionGapProbeError(
            "probe_execution_lineage_invalid"
        )


def _effective_config_sha256(config: Mapping[str, Any]) -> str:
    effective = copy.deepcopy(dict(config))
    safety = mapping_mut(
        mapping_mut(
            mapping_mut(effective, "policy"),
            "box_emptying",
        ),
        "safety",
    )
    safety.setdefault("wall_contact_session_end_clear_ticks", 1)
    return json_sha256(effective)


def _validate_reset_state(value: Mapping[str, Any]) -> None:
    _vector(value.get("qpos"), 4, "reset.qpos")
    _vector(value.get("qvel"), 4, "reset.qvel")
    _vector(value.get("bucket_tip_m"), 3, "reset.bucket_tip_m")
    _vector(value.get("terrain_depth_m"), 6, "reset.terrain_depth_m")
    mass = float(value.get("remaining_mass_kg", math.nan))
    if not math.isfinite(mass) or mass < 0.0:
        raise WallContactSessionGapProbeError(
            "source_reset_remaining_mass_invalid"
        )


def _validate_expected_reset_state(
    value: Mapping[str, Any],
    *,
    expected_sha256: str,
    path: Path,
) -> None:
    if (
        value.get("schema") != "wall_contact_expected_reset_state_v1"
        or value.get("checkpoint_semantics")
        != "first_post_reset_control_step"
        or sha256_file(path) != expected_sha256
    ):
        raise WallContactSessionGapProbeError(
            "expected_reset_state_lineage_invalid"
        )
    _validate_reset_state(value)


def _vector(value: Any, size: int, label: str) -> list[float]:
    if (
        isinstance(value, (str, bytes))
        or not isinstance(value, Sequence)
        or len(value) != size
    ):
        raise ValueError(f"{label}_invalid")
    result = [float(item) for item in value]
    if not all(math.isfinite(item) for item in result):
        raise ValueError(f"{label}_nonfinite")
    return result


def _verify_artifact_lock(value: Any, label: str) -> Path:
    record = mapping(value, label)
    path = required_file(record.get("path"), label)
    expected = sha256_value(record.get("sha256"), f"{label}.sha256")
    actual = sha256_file(path)
    if actual != expected or int(record.get("size_bytes", -1)) != path.stat().st_size:
        raise WallContactSessionGapProbeError(
            f"{label}_artifact_drift"
        )
    return path


def _configured_command(*, config_path: Path, run_root: Path) -> list[str]:
    return [
        "python",
        "-m",
        "testbed.cli.eval",
        "--config",
        str(config_path),
        "--num-rollouts",
        "1",
        "--target-cycle-gate",
        "2",
        "--output-dir",
        str(run_root),
    ]


def _runtime_command(value: Any) -> list[str]:
    if (
        isinstance(value, (str, bytes))
        or not isinstance(value, Sequence)
        or not all(isinstance(item, str) for item in value)
    ):
        raise WallContactSessionGapProbeError("probe_command_invalid")
    command = list(value)
    if command and command[0] == "python":
        command[0] = sys.executable
    return command


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


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "DEFAULT_OUTPUT_ROOT",
    "DEFAULT_SOURCE_ATTEMPT",
    "DEFAULT_SOURCE_CONFIG",
    "PROBE_ATTEMPT_ID",
    "PROBE_REPORT_SCHEMA",
    "PROBE_SCHEMA",
    "WallContactSessionGapProbeError",
    "collect_wall_contact_session_gap_probe",
    "prepare_wall_contact_session_gap_probe",
    "run_wall_contact_session_gap_probe",
    "validate_wall_contact_session_gap_probe",
]
