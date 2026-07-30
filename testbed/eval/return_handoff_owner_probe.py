"""No-overwrite orchestration for the return-handoff owner diagnostic."""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from testbed.eval.return_handoff_owner_diagnostic import (
    TARGET_COMPLETED_DUMPS,
    ReturnHandoffOwnerDiagnosticError,
    analyze_return_handoff_owner_replay,
    build_return_handoff_owner_config,
    gate_config_from_mapping,
    validate_return_handoff_owner_config,
)
from testbed.eval.unity_contact_observe_only_report import (
    build_unity_contact_observe_only_report,
)
from testbed.eval.unity_host_identity import (
    probe_agx_unity_host,
    validate_unity_host_evidence,
)
from testbed.eval.wall_contact_artifact_io import (
    artifact_ref,
    load_json,
    load_yaml,
    locked_ref,
    mapping,
    required_file,
    write_json_x,
    write_yaml_x,
)
from testbed.eval.wall_contact_evidence_contracts import (
    rollout_reset_state,
    validate_reset_pair,
)

_EVAL_BASE = Path(
    "/data/pingfan/excavator_testbed_runs/eval/"
    "yulong_strict18_terrain_residual_v0"
)
_SOURCE_ROOT = _EVAL_BASE / (
    "unity_contact_observe_only_multicycle_diagnostic_v7"
)
DEFAULT_SOURCE_CONFIG = (
    _SOURCE_ROOT / "run/results/eval_resolved_config.yaml"
)
DEFAULT_SOURCE_ROLLOUT = (
    _SOURCE_ROOT / "run/results/rollouts/rollout_000.jsonl"
)
DEFAULT_SOURCE_SUMMARY = (
    _SOURCE_ROOT / "run/results/rollouts/rollout_000_summary.json"
)
DEFAULT_SOURCE_REPORT = _SOURCE_ROOT / "run/report_reanalysis_v2.json"
DEFAULT_SOURCE_MANIFEST = _SOURCE_ROOT / "manifest.json"
DEFAULT_OUTPUT_ROOT = (
    _EVAL_BASE / "return_handoff_owner_target_scoped_diagnostic_v2"
)
PROBE_SCHEMA = "strict18_return_handoff_owner_bounded_diagnostic_v2"
PROBE_ATTEMPT_ID = (
    "strict18_seed_1000_return_handoff_owner_target_scoped_gate8"
)
OWNER_CONTROL_MIN_COMPLETED_DUMPS = 7
MAX_TARGET_COMPLETED_DUMPS = 10
MULTICYCLE_PROBE_SCHEMA = (
    "strict18_return_handoff_owner_multicycle_diagnostic_v1"
)

_CODE_PATHS = (
    "testbed/eval/return_handoff_owner_diagnostic.py",
    "testbed/eval/return_handoff_owner_probe.py",
    "testbed/planner/primitive/effects/return_handoff.py",
    "testbed/planner/primitive/effects/return_handoff_owner_control.py",
    "testbed/eval/unity_contact_observe_only_report.py",
)
_DOWNSTREAM_GATES = {
    "production_contract_change_allowed": False,
    "continuous_predictor_allowed": False,
    "offline_e0_g1_w1_allowed": False,
    "functional_1x10_allowed": False,
}


def _validated_probe_target(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ReturnHandoffOwnerDiagnosticError(
            "target_completed_dumps_invalid"
        )
    target = int(value)
    if (
        target <= OWNER_CONTROL_MIN_COMPLETED_DUMPS
        or target > MAX_TARGET_COMPLETED_DUMPS
    ):
        raise ReturnHandoffOwnerDiagnosticError(
            "target_completed_dumps_invalid"
        )
    return target


def _probe_attempt_id(target_completed_dumps: int) -> str:
    target = _validated_probe_target(target_completed_dumps)
    if target == TARGET_COMPLETED_DUMPS:
        return PROBE_ATTEMPT_ID
    return (
        "strict18_seed_1000_return_handoff_owner_target_scoped_"
        f"gate{target}"
    )


def _probe_schema(target_completed_dumps: int) -> str:
    target = _validated_probe_target(target_completed_dumps)
    return (
        PROBE_SCHEMA
        if target == TARGET_COMPLETED_DUMPS
        else MULTICYCLE_PROBE_SCHEMA
    )


def prepare_return_handoff_owner_probe(
    *,
    source_config_path: str | Path = DEFAULT_SOURCE_CONFIG,
    source_rollout_path: str | Path = DEFAULT_SOURCE_ROLLOUT,
    source_summary_path: str | Path = DEFAULT_SOURCE_SUMMARY,
    source_report_path: str | Path = DEFAULT_SOURCE_REPORT,
    source_manifest_path: str | Path = DEFAULT_SOURCE_MANIFEST,
    output_root: str | Path = DEFAULT_OUTPUT_ROOT,
    target_completed_dumps: int = TARGET_COMPLETED_DUMPS,
) -> dict[str, Any]:
    """Freeze v7, replay the owners, and write one bounded request."""

    target = _validated_probe_target(target_completed_dumps)
    attempt_id = _probe_attempt_id(target)
    probe_schema = _probe_schema(target)
    sources = {
        "source_config": required_file(
            source_config_path,
            "source_config",
        ),
        "source_rollout": required_file(
            source_rollout_path,
            "source_rollout",
        ),
        "source_summary": required_file(
            source_summary_path,
            "source_summary",
        ),
        "source_report": required_file(
            source_report_path,
            "source_report",
        ),
        "source_manifest": required_file(
            source_manifest_path,
            "source_manifest",
        ),
    }
    source_config = load_yaml(sources["source_config"])
    rows = _read_jsonl(sources["source_rollout"])
    offline = analyze_return_handoff_owner_replay(
        rows,
        gate_config=gate_config_from_mapping(source_config),
        cycle_id=7,
    )
    if not bool(offline["bounded_diagnostic_allowed"]):
        raise ReturnHandoffOwnerDiagnosticError(
            "offline_owner_proof_blocked:"
            + ",".join(offline["bounded_diagnostic_blockers"])
        )

    root = Path(output_root).expanduser().resolve()
    run_root = root / "run"
    config_path = (
        root
        / "configs"
        / f"{attempt_id}.yaml"
    )
    offline_path = root / "offline_owner_replay.json"
    manifest_path = root / "manifest.json"
    candidate = build_return_handoff_owner_config(
        source_config,
        run_root=run_root,
        min_completed_dump_count=OWNER_CONTROL_MIN_COMPLETED_DUMPS,
        target_completed_dumps=target,
        attempt_id=attempt_id,
        diagnostic_schema=probe_schema,
    )
    validate_return_handoff_owner_config(
        source=source_config,
        candidate=candidate,
        run_root=run_root,
        min_completed_dump_count=OWNER_CONTROL_MIN_COMPLETED_DUMPS,
        target_completed_dumps=target,
        attempt_id=attempt_id,
        diagnostic_schema=probe_schema,
    )
    repo_root = Path(__file__).resolve().parents[2]
    root.mkdir(parents=True, exist_ok=False)
    write_yaml_x(config_path, candidate)
    write_json_x(
        offline_path,
        {
            **offline,
            "source_rollout": artifact_ref(sources["source_rollout"]),
            "source_config": artifact_ref(sources["source_config"]),
        },
    )
    command = [
        "python",
        "-m",
        "testbed.cli.eval",
        "--config",
        str(config_path),
        "--num-rollouts",
        "1",
        "--target-cycle-gate",
        str(target),
        "--output-dir",
        str(run_root),
    ]
    manifest = {
        "schema": probe_schema,
        "status": "prepared",
        "attempt_id": attempt_id,
        "seed": int(mapping(candidate["eval"], "eval")["seed"]),
        "target_completed_dumps": target,
        "max_attempts": 1,
        "retry_allowed": False,
        "retry_count": 0,
        "diagnostic_only": True,
        "non_promotable": True,
        "writes_training_hdf5": False,
        "manifest_path": str(manifest_path),
        "config_path": str(config_path),
        "offline_owner_replay_path": str(offline_path),
        "run_root": str(run_root),
        "command_argv": command,
        "owner_delta": {
            "contact": {
                "from": "global_config_or_token",
                "to_after_seven_dumps": "return_start_envelope_token[6]",
                "config": {
                    "return_start_envelope_owner_control.contact_owner": (
                        "token"
                    ),
                },
            },
            "depth": {
                "from": "runtime_prior_with_contact_coupled_plane_floor",
                "to_after_seven_dumps": "runtime_prior_p05_p95",
                "config": {
                    "return_start_envelope_owner_control.depth_owner": (
                        "runtime_prior_p05_p95"
                    ),
                },
                "effective_bounds_changed": False,
            },
            "activation": {
                "min_completed_dump_count": (
                    OWNER_CONTROL_MIN_COMPLETED_DUMPS
                ),
                "before_activation": "source_v7_semantics",
            },
        },
        "source_lock": {
            **{
                name: artifact_ref(path)
                for name, path in sources.items()
            },
            "diagnostic_config": artifact_ref(config_path),
            "offline_owner_replay": artifact_ref(offline_path),
            "code": [
                artifact_ref((repo_root / relative).resolve())
                for relative in _CODE_PATHS
            ],
        },
        "downstream_gates": dict(_DOWNSTREAM_GATES),
    }
    write_json_x(manifest_path, manifest)
    return validate_return_handoff_owner_probe(manifest_path)


def validate_return_handoff_owner_probe(
    manifest_path: str | Path,
) -> dict[str, Any]:
    """Validate all frozen sources and the exact request-local config."""

    path = required_file(manifest_path, "diagnostic_manifest")
    manifest = load_json(path)
    target = _validated_probe_target(
        manifest.get("target_completed_dumps")
    )
    attempt_id = _probe_attempt_id(target)
    probe_schema = _probe_schema(target)
    expected = {
        "schema": probe_schema,
        "status": "prepared",
        "attempt_id": attempt_id,
        "target_completed_dumps": target,
        "max_attempts": 1,
        "retry_allowed": False,
        "retry_count": 0,
        "diagnostic_only": True,
        "non_promotable": True,
        "writes_training_hdf5": False,
    }
    for field, value in expected.items():
        if manifest.get(field) != value:
            raise ReturnHandoffOwnerDiagnosticError(
                f"manifest_contract_drift:{field}"
            )
    source_lock = mapping(manifest.get("source_lock"), "source_lock")
    for name in (
        "source_config",
        "source_rollout",
        "source_summary",
        "source_report",
        "source_manifest",
        "diagnostic_config",
        "offline_owner_replay",
    ):
        locked_ref(mapping(source_lock.get(name), name), name)
    code = source_lock.get("code")
    if not isinstance(code, list) or len(code) != len(_CODE_PATHS):
        raise ReturnHandoffOwnerDiagnosticError("code_lock_invalid")
    repo_root = Path(__file__).resolve().parents[2]
    for index, (reference, relative) in enumerate(
        zip(code, _CODE_PATHS, strict=True)
    ):
        actual = locked_ref(mapping(reference, "code"), f"code_{index}")
        if Path(actual["path"]) != (repo_root / relative).resolve():
            raise ReturnHandoffOwnerDiagnosticError("code_lock_invalid")

    source_config = load_yaml(
        Path(mapping(source_lock["source_config"], "source_config")["path"])
    )
    candidate = load_yaml(Path(str(manifest["config_path"])))
    run_root = Path(str(manifest["run_root"])).resolve()
    validate_return_handoff_owner_config(
        source=source_config,
        candidate=candidate,
        run_root=run_root,
        min_completed_dump_count=OWNER_CONTROL_MIN_COMPLETED_DUMPS,
        target_completed_dumps=target,
        attempt_id=attempt_id,
        diagnostic_schema=probe_schema,
    )
    offline = load_json(Path(str(manifest["offline_owner_replay_path"])))
    if not bool(offline.get("bounded_diagnostic_allowed")):
        raise ReturnHandoffOwnerDiagnosticError(
            "offline_owner_proof_not_passed"
        )
    return manifest


def run_return_handoff_owner_probe(
    *,
    manifest_path: str | Path,
    cwd: str | Path | None = None,
) -> dict[str, Any]:
    """Consume the sole bounded attempt against an already-running Unity host."""

    manifest = validate_return_handoff_owner_probe(manifest_path)
    run_root = Path(str(manifest["run_root"]))
    if run_root.exists():
        raise FileExistsError(f"diagnostic_attempt_consumed:{run_root}")
    source_config = load_yaml(Path(str(manifest["config_path"])))
    agx = mapping(source_config.get("agx"), "agx")
    host = validate_unity_host_evidence(
        probe_agx_unity_host(agx),
        agx=agx,
    )
    run_root.mkdir(parents=True, exist_ok=False)
    marker_path = run_root / "attempt_started.json"
    log_path = run_root / "eval_process.log"
    execution_path = run_root / "execution.json"
    started = _utc_now()
    write_json_x(
        marker_path,
        {
            "schema": "strict18_return_handoff_owner_attempt_started_v1",
            "attempt_id": str(manifest["attempt_id"]),
            "started_at_utc": started,
            "retry_count": 0,
            "unity_host_get_info": host,
            "manifest": artifact_ref(
                required_file(manifest_path, "diagnostic_manifest")
            ),
        },
    )
    command = [str(item) for item in manifest["command_argv"]]
    environment = dict(os.environ)
    environment["PYTHONUNBUFFERED"] = "1"
    execution_cwd = (
        Path(cwd).expanduser().resolve()
        if cwd is not None
        else Path(__file__).resolve().parents[2]
    )
    process_exception = ""
    returncode = -1
    with log_path.open("xb") as log:
        try:
            completed = subprocess.run(
                command,
                cwd=execution_cwd,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
            returncode = int(completed.returncode)
        except Exception as exc:  # pragma: no cover - operational evidence
            process_exception = f"{type(exc).__name__}:{exc}"
    write_json_x(
        execution_path,
        {
            "schema": "strict18_return_handoff_owner_execution_v1",
            "attempt_id": str(manifest["attempt_id"]),
            "started_at_utc": started,
            "ended_at_utc": _utc_now(),
            "process_returncode": returncode,
            "process_exception": process_exception,
            "retry_count": 0,
            "attempt_started": artifact_ref(marker_path),
            "process_log": artifact_ref(log_path),
        },
    )
    return collect_return_handoff_owner_probe(manifest_path=manifest_path)


def reanalyze_return_handoff_owner_probe(
    *,
    manifest_path: str | Path,
) -> dict[str, Any]:
    """Collect an immutable attempt after collector-only code changed."""

    path = required_file(manifest_path, "diagnostic_manifest")
    manifest = load_json(path)
    target = _validated_probe_target(
        manifest.get("target_completed_dumps")
    )
    expected = {
        "schema": _probe_schema(target),
        "status": "prepared",
        "attempt_id": _probe_attempt_id(target),
        "target_completed_dumps": target,
        "max_attempts": 1,
        "retry_allowed": False,
        "retry_count": 0,
        "diagnostic_only": True,
        "non_promotable": True,
        "writes_training_hdf5": False,
    }
    for field, value in expected.items():
        if manifest.get(field) != value:
            raise ReturnHandoffOwnerDiagnosticError(
                f"manifest_contract_drift:{field}"
            )
    source_lock = mapping(manifest.get("source_lock"), "source_lock")
    for name in (
        "source_config",
        "source_rollout",
        "source_summary",
        "source_report",
        "source_manifest",
        "diagnostic_config",
        "offline_owner_replay",
    ):
        locked_ref(mapping(source_lock.get(name), name), name)

    code = source_lock.get("code")
    if not isinstance(code, list) or len(code) != len(_CODE_PATHS):
        raise ReturnHandoffOwnerDiagnosticError("code_lock_invalid")
    repo_root = Path(__file__).resolve().parents[2]
    code_evidence = []
    collector_relative = "testbed/eval/return_handoff_owner_probe.py"
    for index, (reference, relative) in enumerate(
        zip(code, _CODE_PATHS, strict=True)
    ):
        original = mapping(reference, f"code_{index}")
        expected_path = (repo_root / relative).resolve()
        if Path(str(original.get("path", ""))) != expected_path:
            raise ReturnHandoffOwnerDiagnosticError("code_lock_invalid")
        if relative != collector_relative:
            locked_ref(original, f"code_{index}")
        current = artifact_ref(required_file(expected_path, f"code_{index}"))
        code_evidence.append(
            {
                "relative_path": relative,
                "execution_lock": dict(original),
                "reanalysis_code": current,
                "changed_after_execution": (
                    original.get("sha256") != current.get("sha256")
                    or original.get("size_bytes")
                    != current.get("size_bytes")
                ),
                "collector_only_drift_allowed": (
                    relative == collector_relative
                ),
            }
        )
    disallowed_drift = [
        item["relative_path"]
        for item in code_evidence
        if bool(item["changed_after_execution"])
        and not bool(item["collector_only_drift_allowed"])
    ]
    if disallowed_drift:
        raise ReturnHandoffOwnerDiagnosticError(
            "runtime_code_drift:" + ",".join(disallowed_drift)
        )

    source_config = load_yaml(
        Path(mapping(source_lock["source_config"], "source_config")["path"])
    )
    candidate = load_yaml(Path(str(manifest["config_path"])))
    validate_return_handoff_owner_config(
        source=source_config,
        candidate=candidate,
        run_root=Path(str(manifest["run_root"])).resolve(),
        min_completed_dump_count=OWNER_CONTROL_MIN_COMPLETED_DUMPS,
        target_completed_dumps=target,
        attempt_id=_probe_attempt_id(target),
        diagnostic_schema=_probe_schema(target),
    )
    offline = load_json(Path(str(manifest["offline_owner_replay_path"])))
    if not bool(offline.get("bounded_diagnostic_allowed")):
        raise ReturnHandoffOwnerDiagnosticError(
            "offline_owner_proof_not_passed"
        )
    return collect_return_handoff_owner_probe(
        manifest_path=path,
        _manifest_override=manifest,
        _report_filename="report_reanalysis_v1.json",
        _report_extra={
            "reanalysis_only": True,
            "physical_rollout_reexecuted": False,
            "source_attempt_immutable": True,
            "collector_code_evidence": code_evidence,
        },
    )


def collect_return_handoff_owner_probe(
    *,
    manifest_path: str | Path,
    _manifest_override: Mapping[str, Any] | None = None,
    _report_filename: str = "report.json",
    _report_extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate and summarize the consumed bounded diagnostic."""

    manifest = (
        dict(_manifest_override)
        if _manifest_override is not None
        else validate_return_handoff_owner_probe(manifest_path)
    )
    target = _validated_probe_target(
        manifest.get("target_completed_dumps")
    )
    run_root = Path(str(manifest["run_root"]))
    rollout_path = required_file(
        run_root / "results/rollouts/rollout_000.jsonl",
        "bounded_rollout",
    )
    summary_path = required_file(
        run_root / "results/rollouts/rollout_000_summary.json",
        "bounded_rollout_summary",
    )
    resolved_path = required_file(
        run_root / "results/eval_resolved_config.yaml",
        "bounded_resolved_config",
    )
    rows = _read_jsonl(rollout_path)
    summary = load_json(summary_path)
    resolved = load_yaml(resolved_path)
    switch = mapping(
        mapping(resolved.get("policy"), "policy").get("switch"),
        "policy.switch",
    )
    box = mapping(
        mapping(resolved.get("policy"), "policy").get("box_emptying"),
        "policy.box_emptying",
    )
    control = mapping(
        box.get("return_start_envelope_owner_control"),
        "return_start_envelope_owner_control",
    )
    if (
        switch.get("return_to_dig_start_envelope_require_contact")
        is not True
        or switch.get("return_to_dig_start_envelope_plane_depth_mode")
        != "p50_floor"
        or control
        != {
            "enabled": True,
            "diagnostic_only": True,
            "min_completed_dump_count": (
                OWNER_CONTROL_MIN_COMPLETED_DUMPS
            ),
            "contact_owner": "token",
            "depth_owner": "runtime_prior_p05_p95",
        }
    ):
        raise ReturnHandoffOwnerDiagnosticError(
            "resolved_owner_config_drift"
        )
    owner_evidence = _validate_owner_control_evidence(rows)
    bounded = summarize_bounded_rollout(
        rows=rows,
        summary=summary,
        target_completed_dumps=target,
    )
    source_lock = mapping(manifest.get("source_lock"), "source_lock")
    source_rollout_ref = mapping(
        source_lock.get("source_rollout"),
        "source_rollout",
    )
    source_rows = _read_jsonl(Path(str(source_rollout_ref["path"])))
    expected_reset = rollout_reset_state(source_rows[0])
    reset_fairness = validate_reset_pair(
        expected_reset_state=expected_reset,
        reset_a=expected_reset,
        reset_b=rollout_reset_state(rows[0]),
    )
    if not bool(reset_fairness["valid"]):
        raise ReturnHandoffOwnerDiagnosticError(
            "bounded_reset_fairness_failed:"
            + ",".join(reset_fairness["violations"])
        )
    contact_report = build_unity_contact_observe_only_report(
        rows=rows,
        summary=summary,
        max_shovels=target,
    )
    report_path = run_root / _report_filename
    execution_path = run_root / "execution.json"
    report = {
        "schema": (
            "strict18_return_handoff_owner_bounded_report_v2"
            if target == TARGET_COMPLETED_DUMPS
            else "strict18_return_handoff_owner_multicycle_report_v1"
        ),
        "status": (
            "passed"
            if bool(bounded["completed_target_dump"])
            else "failed"
        ),
        "attempt_id": str(manifest["attempt_id"]),
        "target_completed_dumps": target,
        "retry_count": 0,
        "diagnostic_only": True,
        "non_promotable": True,
        "writes_training_hdf5": False,
        "owner_contract": {
            "contact": "return_start_envelope_token[6]",
            "depth": "runtime_prior_p05_p95",
            "effective_depth_bounds_changed_from_v7": False,
            "activation_min_completed_dump_count": (
                OWNER_CONTROL_MIN_COMPLETED_DUMPS
            ),
        },
        "owner_control_evidence": owner_evidence,
        "reset_fairness": reset_fairness,
        "bounded_rollout": bounded,
        "contact_report": contact_report,
        "rollout_jsonl": artifact_ref(rollout_path),
        "rollout_summary": artifact_ref(summary_path),
        "resolved_config": artifact_ref(resolved_path),
        "execution": (
            artifact_ref(execution_path)
            if execution_path.is_file()
            else None
        ),
        "downstream_gates": dict(_DOWNSTREAM_GATES),
    }
    for key, value in dict(_report_extra or {}).items():
        if key in report:
            raise ReturnHandoffOwnerDiagnosticError(
                f"report_extra_overwrites_core_field:{key}"
            )
        report[key] = value
    write_json_x(report_path, report)
    return report


def summarize_bounded_rollout(
    *,
    rows: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
    target_completed_dumps: int = TARGET_COMPLETED_DUMPS,
) -> dict[str, Any]:
    """Summarize the requested final shovel without promoting the result."""

    target = _validated_probe_target(target_completed_dumps)
    target_cycle_id = target - 1
    completed_sources = {
        "completed_dump_count": int(
            summary.get("completed_dump_count", 0)
        ),
        "target_cycle_completed_dump_count": int(
            summary.get("target_cycle_completed_dump_count", 0)
        ),
        "dump_end_count": int(summary.get("dump_end_count", 0)),
    }
    completed = max(completed_sources.values())
    target_dig_rows = [
        row
        for row in rows
        if int(row.get("cycle_id", -1)) == target_cycle_id
        and str(row.get("skill_name", "")) == "dig"
    ]
    first_dig_step = (
        min(int(row["step_id"]) for row in target_dig_rows)
        if target_dig_rows
        else None
    )
    ready_rows = [
        row
        for row in rows
        if bool(row.get("return_to_dig_start_envelope_ready", False))
        and int(row.get("cycle_id", -1)) == target_cycle_id
        and (
            first_dig_step is None
            or int(row.get("step_id", -1)) <= first_dig_step
        )
    ]
    ready_return_rows = [
        row
        for row in ready_rows
        if str(row.get("skill_name", "")) == "return"
    ]
    handoff_rows = ready_return_rows or ready_rows
    handoff_ready_step = (
        max(int(row["step_id"]) for row in handoff_rows)
        if handoff_rows
        else None
    )
    stop_reason = str(summary.get("rollout_stop_reason", ""))
    safety_reasons = sorted(
        {
            str(row.get("box_safety_reason", ""))
            for row in rows
            if str(row.get("box_safety_reason", ""))
        }
    )
    if completed >= target:
        termination = (
            "target_eighth_dump_completed"
            if target == TARGET_COMPLETED_DUMPS
            else f"target_{target}_dump_completed"
        )
    elif any("high_force" in reason for reason in safety_reasons):
        termination = "high_force_stop"
    elif any("stuck" in reason for reason in safety_reasons):
        termination = "stuck_stop"
    elif "timeout" in stop_reason or any(
        "timeout" in reason for reason in safety_reasons
    ):
        termination = "timeout_stop"
    else:
        termination = "other_stop"
    result = {
        "target_completed_dumps": target,
        "completed_dump_count": completed,
        "completed_dump_count_sources": completed_sources,
        "entered_target_dig": bool(target_dig_rows),
        "completed_target_dump": completed >= target,
        "first_target_dig_step": first_dig_step,
        "handoff_ready_step": handoff_ready_step,
        "rollout_stop_reason": stop_reason,
        "safety_reasons": safety_reasons,
        "termination_category": termination,
    }
    if target == TARGET_COMPLETED_DUMPS:
        result.update(
            {
                "entered_eighth_dig": bool(target_dig_rows),
                "completed_eighth_dump": completed >= target,
                "first_eighth_dig_step": first_dig_step,
            }
        )
    return result


def _validate_owner_control_evidence(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    samples = []
    for row in rows:
        checks = row.get("return_to_dig_start_envelope_checks")
        if not isinstance(checks, Mapping):
            continue
        evidence = checks.get("diagnostic_owner_control")
        if not isinstance(evidence, Mapping):
            continue
        sample = {
            "step_id": int(row.get("step_id", -1)),
            "cycle_id": int(row.get("cycle_id", -1)),
            "skill_name": str(row.get("skill_name", "")),
            **dict(evidence),
        }
        if (
            sample.get("enabled") is not True
            or sample.get("diagnostic_only") is not True
            or int(sample.get("min_completed_dump_count", -1))
            != OWNER_CONTROL_MIN_COMPLETED_DUMPS
            or sample.get("contact_owner") != "token"
            or sample.get("depth_owner") != "runtime_prior_p05_p95"
        ):
            raise ReturnHandoffOwnerDiagnosticError(
                "owner_control_evidence_drift"
            )
        count = int(sample.get("completed_dump_count", -1))
        expected_active = count >= OWNER_CONTROL_MIN_COMPLETED_DUMPS
        if bool(sample.get("active")) != expected_active:
            raise ReturnHandoffOwnerDiagnosticError(
                "owner_control_activation_drift"
            )
        samples.append(sample)
    if not samples:
        raise ReturnHandoffOwnerDiagnosticError(
            "owner_control_evidence_missing"
        )
    active = [sample for sample in samples if bool(sample["active"])]
    inactive = [sample for sample in samples if not bool(sample["active"])]
    if not inactive:
        raise ReturnHandoffOwnerDiagnosticError(
            "owner_control_activation_boundary_not_exercised"
        )
    max_completed = max(
        int(sample["completed_dump_count"]) for sample in samples
    )
    if not active:
        if max_completed >= OWNER_CONTROL_MIN_COMPLETED_DUMPS:
            raise ReturnHandoffOwnerDiagnosticError(
                "owner_control_active_evidence_missing"
            )
        return {
            "sample_count": len(samples),
            "inactive_sample_count": len(inactive),
            "active_sample_count": 0,
            "activation_boundary_exercised": False,
            "first_active_step": None,
            "first_active_cycle_id": None,
            "first_active_completed_dump_count": None,
            "first_active_return_step": None,
            "first_active_return_cycle_id": None,
            "max_observed_completed_dump_count": max_completed,
            "activated_early": False,
        }
    first_active = min(active, key=lambda sample: int(sample["step_id"]))
    active_return = [
        sample
        for sample in active
        if str(sample["skill_name"]) == "return"
    ]
    if not active_return:
        raise ReturnHandoffOwnerDiagnosticError(
            "owner_control_active_return_evidence_missing"
        )
    first_active_return = min(
        active_return,
        key=lambda sample: int(sample["step_id"]),
    )
    return {
        "sample_count": len(samples),
        "inactive_sample_count": len(inactive),
        "active_sample_count": len(active),
        "activation_boundary_exercised": True,
        "first_active_step": int(first_active["step_id"]),
        "first_active_cycle_id": int(first_active["cycle_id"]),
        "first_active_completed_dump_count": int(
            first_active["completed_dump_count"]
        ),
        "first_active_return_step": int(first_active_return["step_id"]),
        "first_active_return_cycle_id": int(
            first_active_return["cycle_id"]
        ),
        "max_observed_completed_dump_count": max_completed,
        "activated_early": False,
    }


def _read_jsonl(path: Path) -> list[Mapping[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for index, line in enumerate(handle, start=1):
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ReturnHandoffOwnerDiagnosticError(
                    f"jsonl_invalid:line={index}"
                ) from exc
            rows.append(mapping(value, f"rollout_line_{index}"))
    if not rows:
        raise ReturnHandoffOwnerDiagnosticError("rollout_empty")
    return rows


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


__all__ = [
    "DEFAULT_OUTPUT_ROOT",
    "DEFAULT_SOURCE_CONFIG",
    "DEFAULT_SOURCE_MANIFEST",
    "DEFAULT_SOURCE_REPORT",
    "DEFAULT_SOURCE_ROLLOUT",
    "DEFAULT_SOURCE_SUMMARY",
    "collect_return_handoff_owner_probe",
    "prepare_return_handoff_owner_probe",
    "reanalyze_return_handoff_owner_probe",
    "run_return_handoff_owner_probe",
    "summarize_bounded_rollout",
    "validate_return_handoff_owner_probe",
]
