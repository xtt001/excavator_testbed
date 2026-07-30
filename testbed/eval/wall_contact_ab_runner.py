"""Exactly-once execution owner for the Strict-18 paired contact A/B."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from testbed.eval.wall_contact_ab_collection import (
    ATTEMPT_SCHEMA,
    ATTEMPT_SET_SCHEMA,
    START_MARKER_SCHEMA,
    TARGET_EXEMPLAR_ID,
    TARGET_RAW_FIELDS_SHA256,
    extract_paired_ab_attempt,
    failed_paired_ab_attempt,
    write_paired_ab_attempt_set,
)
from testbed.eval.wall_contact_artifact_io import (
    artifact_ref,
    load_json,
    load_yaml,
    mapping,
    required_file,
    sha256_value,
    write_json_x,
)

SCHEDULE_SCHEMA = "wall_contact_paired_ab_schedule_v1"
EXPECTED_SEQUENCE = (
    (0, "A"),
    (0, "B"),
    (1, "B"),
    (1, "A"),
    (2, "A"),
    (2, "B"),
)
_MODES = {
    "A": "interrupt",
    "B": "record_bucket_first_session",
}
Executor = Callable[[list[str], Path, Path], int]


class WallContactABRunnerError(RuntimeError):
    """Raised before execution when the exactly-once contract is unsafe."""


def validate_paired_ab_schedule(
    schedule_path: str | Path,
) -> dict[str, Any]:
    """Validate all six configs and commands before any Unity connection."""

    source = required_file(schedule_path, "paired_ab_schedule")
    raw = load_json(source)
    if raw.get("schema") != SCHEDULE_SCHEMA:
        raise WallContactABRunnerError("paired_ab_schedule_schema_invalid")
    if (
        raw.get("status") != "prepared"
        or raw.get("diagnostic_only") is not True
        or raw.get("non_promotable") is not True
        or raw.get("retry_allowed") is not False
        or raw.get("execution_order_is_mandatory") is not True
        or int(raw.get("attempt_count", -1)) != len(EXPECTED_SEQUENCE)
    ):
        raise WallContactABRunnerError("paired_ab_schedule_flags_invalid")
    if raw.get("target_contract") != {
        "exemplar_id": TARGET_EXEMPLAR_ID,
        "runtime_role": "diagnostic_legacy",
        "use_scope": "paired_ab_only",
        "production_lookup_allowed": False,
        "reset_checkpoint_semantics": "first_post_reset_control_step",
    }:
        raise WallContactABRunnerError("paired_ab_target_contract_invalid")
    attempts_raw = raw.get("attempts")
    if not isinstance(attempts_raw, list) or len(attempts_raw) != 6:
        raise WallContactABRunnerError("paired_ab_attempt_inventory_invalid")

    schedule_root = source.parent
    attempts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sequence_index, ((seed, condition), item) in enumerate(
        zip(EXPECTED_SEQUENCE, attempts_raw, strict=True),
        start=1,
    ):
        if not isinstance(item, Mapping):
            raise WallContactABRunnerError("paired_ab_attempt_invalid")
        attempt = dict(item)
        attempt_id = f"seed_{seed}_{condition}"
        expected = {
            "attempt_id": attempt_id,
            "pair_id": f"seed_{seed}",
            "sequence_index": sequence_index,
            "seed": seed,
            "condition": condition,
            "wall_first_touch_mode": _MODES[condition],
            "max_attempts": 1,
            "retry_allowed": False,
        }
        for field, value in expected.items():
            if attempt.get(field) != value:
                raise WallContactABRunnerError(
                    f"paired_ab_attempt_lineage_drift:{attempt_id}:{field}"
                )
        if attempt_id in seen:
            raise WallContactABRunnerError("paired_ab_attempt_duplicate")
        seen.add(attempt_id)
        config_path = required_file(
            attempt.get("config_path"),
            f"{attempt_id}.config",
        )
        run_root = Path(str(attempt.get("run_root", ""))).expanduser().resolve()
        expected_config = (
            schedule_root / "configs" / f"{attempt_id}.yaml"
        ).resolve()
        expected_run = (schedule_root / "runs" / attempt_id).resolve()
        if config_path != expected_config or run_root != expected_run:
            raise WallContactABRunnerError(
                f"paired_ab_attempt_path_drift:{attempt_id}"
            )
        _validate_attempt_config(
            config_path=config_path,
            expected=expected,
            run_root=run_root,
        )
        command = _validate_command(
            attempt.get("command_argv"),
            config_path=config_path,
            run_root=run_root,
        )
        attempt.update(
            {
                **expected,
                "config_path": str(config_path),
                "run_root": str(run_root),
                "command_argv": command,
            }
        )
        attempts.append(attempt)
    return {**raw, "attempts": attempts, "schedule_path": str(source)}


def run_paired_ab_schedule(
    *,
    schedule_path: str | Path,
    attempt_set_output_path: str | Path,
    executor: Executor | None = None,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Run all six attempts once, retaining failures and never retrying."""

    schedule = validate_paired_ab_schedule(schedule_path)
    output = Path(attempt_set_output_path).expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"refusing to overwrite {output}")
    for attempt in schedule["attempts"]:
        run_root = Path(str(attempt["run_root"]))
        if run_root.exists():
            raise FileExistsError(
                f"paired A/B attempt already started: {attempt['attempt_id']}"
            )

    execution_cwd = (
        Path(cwd).expanduser().resolve()
        if cwd is not None
        else Path(__file__).resolve().parents[2]
    )
    run_executor = executor or _execute_subprocess
    for attempt in schedule["attempts"]:
        _run_one_attempt(
            attempt=attempt,
            schedule_path=Path(str(schedule["schedule_path"])),
            execution_cwd=execution_cwd,
            executor=run_executor,
        )
    return write_paired_ab_attempt_set(
        schedule=schedule,
        output_path=output,
    )


def collect_paired_ab_attempt_set(
    *,
    schedule_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    """Collect an already completed immutable six-attempt schedule."""

    return write_paired_ab_attempt_set(
        schedule=validate_paired_ab_schedule(schedule_path),
        output_path=output_path,
    )


def reextract_paired_ab_attempt_set(
    *,
    schedule_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Re-run only immutable rollout extraction; never execute an attempt."""

    schedule = validate_paired_ab_schedule(schedule_path)
    destination = Path(output_dir).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite {destination}")
    attempts_dir = destination / "attempts"
    attempts_dir.mkdir(parents=True, exist_ok=False)

    attempts: list[dict[str, Any]] = []
    original_refs: list[dict[str, Any]] = []
    reanalysis_refs: list[dict[str, Any]] = []
    handoff_shas: set[str] = set()
    for expected in schedule["attempts"]:
        run_root = Path(str(expected["run_root"]))
        marker_path = required_file(
            run_root / "attempt_started.json",
            f"{expected['attempt_id']}.attempt_started",
        )
        original_path = required_file(
            run_root / "attempt_result.json",
            f"{expected['attempt_id']}.attempt_result",
        )
        rollout_path = required_file(
            run_root / "results" / "rollouts" / "rollout_000.jsonl",
            f"{expected['attempt_id']}.rollout_jsonl",
        )
        summary_path = required_file(
            run_root
            / "results"
            / "rollouts"
            / "rollout_000_summary.json",
            f"{expected['attempt_id']}.rollout_summary",
        )
        marker = load_json(marker_path)
        original = load_json(original_path)
        if (
            marker.get("schema") != START_MARKER_SCHEMA
            or marker.get("attempt_id") != expected["attempt_id"]
            or original.get("schema") != ATTEMPT_SCHEMA
            or original.get("attempt_id") != expected["attempt_id"]
            or int(original.get("retry_count", -1)) != 0
        ):
            raise WallContactABRunnerError(
                f"paired_ab_reanalysis_source_invalid:{expected['attempt_id']}"
            )
        result = extract_paired_ab_attempt(
            expected=expected,
            rollout_jsonl_path=rollout_path,
            rollout_summary_path=summary_path,
            process_returncode=int(original.get("process_returncode", -1)),
        )
        result.update(
            {
                "reanalysis_only": True,
                "executed_during_reanalysis": False,
                "reanalysis_of": artifact_ref(original_path),
            }
        )
        result_path = attempts_dir / f"{expected['attempt_id']}.json"
        write_json_x(result_path, result)
        attempts.append(result)
        original_refs.append(artifact_ref(original_path))
        reanalysis_refs.append(artifact_ref(result_path))
        handoff_shas.add(
            _config_frozen_handoff_sha(Path(str(expected["config_path"])))
        )
    if len(handoff_shas) != 1:
        raise WallContactABRunnerError("frozen_handoff_sha_drift")

    failed = [
        str(item["attempt_id"])
        for item in attempts
        if item.get("status") != "passed"
    ]
    artifact = {
        "schema": ATTEMPT_SET_SCHEMA,
        "status": "passed" if not failed else "failed",
        "blockers": (
            [] if not failed else ["paired_ab_attempt_reanalysis_failed"]
        ),
        "failed_attempt_ids": failed,
        "attempt_count": len(attempts),
        "retry_allowed": False,
        "execution_order": [str(item["attempt_id"]) for item in attempts],
        "frozen_handoff_sha256": next(iter(handoff_shas)),
        "expert_same_region_sub_100kn": False,
        "expert_lineage_complete": False,
        "expert_cross_evidence_status": "not_owned_by_ab_runner",
        "attempts": attempts,
        "reanalysis_only": True,
        "executed_attempt_count": 0,
        "raw_rollout_attempt_count": len(attempts),
        "diagnostic_only": True,
        "non_promotable": True,
        "production_promotion_allowed": False,
        "writes_training_hdf5": False,
        "source_lock": {
            "schedule": artifact_ref(Path(str(schedule["schedule_path"]))),
            "original_attempt_results": original_refs,
            "reanalysis_attempt_results": reanalysis_refs,
            "postprocessor": artifact_ref(
                Path(__file__).with_name("wall_contact_ab_collection.py")
            ),
        },
    }
    write_json_x(destination / "attempt_set.json", artifact)
    return artifact


def _run_one_attempt(
    *,
    attempt: Mapping[str, Any],
    schedule_path: Path,
    execution_cwd: Path,
    executor: Executor,
) -> None:
    run_root = Path(str(attempt["run_root"]))
    run_root.mkdir(parents=True, exist_ok=False)
    marker_path = run_root / "attempt_started.json"
    result_path = run_root / "attempt_result.json"
    log_path = run_root / "eval_process.log"
    command = _runtime_command(attempt["command_argv"])
    started_at = _utc_now()
    write_json_x(
        marker_path,
        {
            "schema": START_MARKER_SCHEMA,
            "attempt_id": attempt["attempt_id"],
            "pair_id": attempt["pair_id"],
            "sequence_index": attempt["sequence_index"],
            "seed": attempt["seed"],
            "condition": attempt["condition"],
            "retry_count": 0,
            "started_at_utc": started_at,
            "schedule": artifact_ref(schedule_path),
            "configured_argv": list(attempt["command_argv"]),
            "executed_argv": command,
            "cwd": str(execution_cwd),
        },
    )
    log_path.open("x", encoding="utf-8").close()
    process_exception = ""
    try:
        returncode = int(executor(command, execution_cwd, log_path))
    except Exception as exc:  # retain exactly-once failure evidence
        returncode = -1
        process_exception = f"{type(exc).__name__}:{exc}"
    ended_at = _utc_now()
    rollout_dir = run_root / "results" / "rollouts"
    rollout_path = rollout_dir / "rollout_000.jsonl"
    summary_path = rollout_dir / "rollout_000_summary.json"
    if rollout_path.is_file() and summary_path.is_file():
        try:
            result = extract_paired_ab_attempt(
                expected=attempt,
                rollout_jsonl_path=rollout_path,
                rollout_summary_path=summary_path,
                process_returncode=returncode,
            )
        except Exception as exc:
            result = failed_paired_ab_attempt(
                expected=attempt,
                returncode=returncode,
                blocker=f"rollout_extraction_failed:{type(exc).__name__}:{exc}",
            )
    else:
        result = failed_paired_ab_attempt(
            expected=attempt,
            returncode=returncode,
            blocker="complete_rollout_artifacts_missing",
        )
    result.update(
        {
            "run_root": str(run_root),
            "started_at_utc": started_at,
            "ended_at_utc": ended_at,
            "process_exception": process_exception,
            "executed_argv": command,
            "process_log": artifact_ref(log_path),
            "attempt_started": artifact_ref(marker_path),
        }
    )
    write_json_x(result_path, result)


def _validate_attempt_config(
    *,
    config_path: Path,
    expected: Mapping[str, Any],
    run_root: Path,
) -> None:
    config = load_yaml(config_path)
    eval_config = mapping(config.get("eval"), "eval")
    required_eval = {
        "num_rollouts": 1,
        "seed": expected["seed"],
        "target_cycle_gate": 2,
        "target_cycle_gate_terminal_hold_steps": 0,
        "no_overwrite": True,
        "record_hdf5": False,
    }
    for field, value in required_eval.items():
        if eval_config.get(field) != value:
            raise WallContactABRunnerError(
                f"paired_ab_eval_contract_drift:{expected['attempt_id']}:{field}"
            )
    paths = {
        "results_dir": run_root / "results",
        "video_dir": run_root / "videos",
        "rollout_log_dir": run_root / "results" / "rollouts",
        "hdf5_dir": run_root / "disabled_hdf5",
    }
    for field, value in paths.items():
        observed = Path(str(eval_config.get(field, ""))).expanduser().resolve()
        if observed != value.resolve():
            raise WallContactABRunnerError(
                f"paired_ab_output_path_drift:{expected['attempt_id']}:{field}"
            )
    metadata = mapping(
        eval_config.get("record_hdf5_metadata"),
        "record_hdf5_metadata",
    )
    metadata_contract = {
        "validation_schema": ATTEMPT_SCHEMA,
        "contact_semantics_attempt_id": expected["attempt_id"],
        "contact_semantics_pair_id": expected["pair_id"],
        "contact_semantics_condition": expected["condition"],
        "contact_semantics_sequence_index": expected["sequence_index"],
        "contact_semantics_reset_seed": expected["seed"],
        "diagnostic_only": True,
        "promotion_eligible": False,
    }
    for field, value in metadata_contract.items():
        if metadata.get(field) != value:
            raise WallContactABRunnerError(
                f"paired_ab_metadata_drift:{expected['attempt_id']}:{field}"
            )
    sha256_value(
        metadata.get("frozen_target_handoff_sha256"),
        "frozen_handoff",
    )
    sha256_value(
        metadata.get("expected_reset_state_sha256"),
        "expected_reset_state",
    )
    policy = mapping(config.get("policy"), "policy")
    planner = mapping(policy.get("dig_cut_planner"), "dig_cut_planner")
    coverage = mapping(planner.get("coverage"), "coverage")
    exact = mapping(
        coverage.get("actual_tuple_execution_library"),
        "actual_tuple_execution_library",
    )
    if exact.get("runtime_role") != "diagnostic_legacy":
        raise WallContactABRunnerError("exact_runtime_role_not_diagnostic_legacy")
    box = mapping(policy.get("box_emptying"), "box_emptying")
    bounded = mapping(
        box.get("bounded_dig_probe_stop"),
        "bounded_dig_probe_stop",
    )
    if bounded.get("enabled") is not False:
        raise WallContactABRunnerError(
            "bounded_stop_wrapper_must_be_disabled"
        )
    functional = mapping(
        box.get("functional_cycle_gate"),
        "functional_cycle_gate",
    )
    if functional.get("enabled") is not False:
        raise WallContactABRunnerError("functional_cycle_gate_must_be_disabled")
    validator = mapping(
        box.get("contact_semantics_one_cycle_validator"),
        "contact_semantics_one_cycle_validator",
    )
    if validator != {
        "enabled": True,
        "diagnostic_only": True,
        "target_exemplar_id": TARGET_EXEMPLAR_ID,
        "stop_on": ["target_dump_complete", "safety_terminal"],
    }:
        raise WallContactABRunnerError("one_cycle_validator_contract_drift")
    safety = mapping(box.get("safety"), "box_emptying.safety")
    if (
        safety.get("wall_contact_diagnostic_ab_enabled") is not True
        or safety.get("wall_first_touch_mode")
        != expected["wall_first_touch_mode"]
    ):
        raise WallContactABRunnerError("diagnostic_contact_mode_drift")


def _validate_command(
    value: Any,
    *,
    config_path: Path,
    run_root: Path,
) -> list[str]:
    if (
        isinstance(value, (str, bytes))
        or not isinstance(value, Sequence)
        or not all(isinstance(item, str) for item in value)
    ):
        raise WallContactABRunnerError("paired_ab_command_invalid")
    command = list(value)
    expected = [
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
    if command != expected:
        raise WallContactABRunnerError("paired_ab_command_drift")
    return command


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


def _config_frozen_handoff_sha(config_path: Path) -> str:
    config = load_yaml(config_path)
    metadata = mapping(
        mapping(config.get("eval"), "eval").get("record_hdf5_metadata"),
        "record_hdf5_metadata",
    )
    return sha256_value(
        metadata.get("frozen_target_handoff_sha256"),
        "frozen_handoff",
    )


def _runtime_command(command: Sequence[str]) -> list[str]:
    result = list(command)
    if result and result[0] == "python":
        result[0] = sys.executable
    return result


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "ATTEMPT_SCHEMA",
    "ATTEMPT_SET_SCHEMA",
    "EXPECTED_SEQUENCE",
    "SCHEDULE_SCHEMA",
    "TARGET_EXEMPLAR_ID",
    "TARGET_RAW_FIELDS_SHA256",
    "WallContactABRunnerError",
    "collect_paired_ab_attempt_set",
    "extract_paired_ab_attempt",
    "reextract_paired_ab_attempt_set",
    "run_paired_ab_schedule",
    "validate_paired_ab_schedule",
]
