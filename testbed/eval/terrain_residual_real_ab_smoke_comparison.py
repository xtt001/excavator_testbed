"""Real bounded-smoke A/B eval artifacts for terrain residual planning."""

from __future__ import annotations

import copy
import json
import shlex
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from testbed.eval.terrain_residual_contract import official_contract_statuses


CURRENT_REQUEST_SCHEMA = "terrain_residual_current_bounded_smoke_request_v1"
CURRENT_REQUEST_SOURCE = "explicit_current_planner_bounded_smoke_request"
COMPARISON_SCHEMA = "terrain_residual_real_ab_bounded_smoke_comparison_v1"
COMPARISON_SOURCE = "explicit_real_ab_bounded_smoke_comparison"
DEFAULT_CURRENT_REQUEST_PROFILE = "phase6g_h_current_bounded_smoke_request"
DEFAULT_COMPARISON_PROFILE = "phase6g_h_real_ab_bounded_smoke_comparison"
CURRENT_BRANCH_NAME = "current_planner_baseline"
HEURISTIC_BRANCH_NAME = "heuristic_residual_pipeline"
CALIBRATED_BRANCH_NAME = "calibrated_residual_pipeline"
BRANCH_ORDER = [
    CURRENT_BRANCH_NAME,
    HEURISTIC_BRANCH_NAME,
    CALIBRATED_BRANCH_NAME,
]
CURRENT_CONFIG_FILENAME = "current_planner_baseline_eval_config.yaml"
CURRENT_INVOCATION_FILENAME = "current_planner_baseline_invocation.json"
CURRENT_REQUEST_FILES = [
    CURRENT_CONFIG_FILENAME,
    CURRENT_INVOCATION_FILENAME,
]
TARGET_CYCLE_GATE_TERMINAL_HOLD_STEPS = 0


def write_current_planner_bounded_smoke_request(
    *,
    current_eval_metadata: Mapping[str, Any],
    request_root: Any,
    planned_results_root: Any,
    protected_evidence_roots: Sequence[Any],
    target_cycle_gate: int = 1,
    profile: str = DEFAULT_CURRENT_REQUEST_PROFILE,
) -> dict[str, Any]:
    """Write request-local A-branch config/argv for a one-cycle smoke run."""

    normalized_request_root = _path_string(request_root)
    normalized_planned_root = _path_string(planned_results_root)
    protected_roots = _string_list(protected_evidence_roots)
    no_overwrite_validation = _request_no_overwrite_validation(
        request_root=normalized_request_root,
        planned_results_root=normalized_planned_root,
        protected_evidence_roots=protected_roots,
    )
    if no_overwrite_validation["status"] != "present":
        return _current_request_result(
            status=str(no_overwrite_validation["status"]),
            profile=profile,
            request_root=normalized_request_root,
            planned_results_root=normalized_planned_root,
            protected_evidence_roots=protected_roots,
            runtime_config={},
            invocation={},
            expected_branch_outputs={},
            written_files=[],
            no_overwrite_validation=no_overwrite_validation,
            validation_errors=list(no_overwrite_validation["validation_errors"]),
        )

    current_argv, argv_errors = _current_eval_argv(current_eval_metadata)
    if argv_errors:
        return _invalid_current_request(
            status="invalid_current_eval_metadata",
            profile=profile,
            request_root=normalized_request_root,
            planned_results_root=normalized_planned_root,
            protected_evidence_roots=protected_roots,
            no_overwrite_validation=no_overwrite_validation,
            validation_errors=argv_errors,
        )

    config_path = _config_path_from_argv(current_argv)
    baseline_config, config_errors = _read_eval_config(config_path)
    if config_errors:
        return _invalid_current_request(
            status="invalid_current_eval_config",
            profile=profile,
            request_root=normalized_request_root,
            planned_results_root=normalized_planned_root,
            protected_evidence_roots=protected_roots,
            no_overwrite_validation=no_overwrite_validation,
            validation_errors=config_errors,
        )

    assert normalized_request_root is not None
    assert normalized_planned_root is not None
    target_cycle_gate = int(target_cycle_gate)
    config_artifact_path = str(Path(normalized_request_root) / CURRENT_CONFIG_FILENAME)
    branch_output_dir = str(Path(normalized_planned_root) / CURRENT_BRANCH_NAME)
    generated_config, runtime_config = _current_branch_eval_config(
        baseline_config,
        target_cycle_gate=target_cycle_gate,
    )
    current_branch_argv = _argv_with_smoke_overrides(
        current_argv,
        config_path=config_artifact_path,
        output_dir=branch_output_dir,
        target_cycle_gate=target_cycle_gate,
    )
    expected_outputs = _expected_branch_outputs(branch_output_dir)
    invocation = _invocation_payload(
        schema=CURRENT_REQUEST_SCHEMA,
        source=CURRENT_REQUEST_SOURCE,
        profile=profile,
        branch=CURRENT_BRANCH_NAME,
        argv=current_branch_argv,
        branch_output_dir=branch_output_dir,
        config_artifact_path=config_artifact_path,
        expected_branch_outputs=expected_outputs,
        no_overwrite_validation=no_overwrite_validation,
    )
    payloads = {
        CURRENT_CONFIG_FILENAME: generated_config,
        CURRENT_INVOCATION_FILENAME: invocation,
    }

    root_path = _resolve_path(normalized_request_root)
    written_files: list[str] = []
    try:
        root_path.mkdir(parents=True, exist_ok=False)
        for relative_path in CURRENT_REQUEST_FILES:
            target_path = root_path / relative_path
            if relative_path.endswith(".yaml"):
                target_path.write_text(
                    yaml.safe_dump(payloads[relative_path], sort_keys=False),
                    encoding="utf-8",
                )
            else:
                target_path.write_text(
                    json.dumps(payloads[relative_path], indent=2, sort_keys=True)
                    + "\n",
                    encoding="utf-8",
                )
            written_files.append(relative_path)
    except FileExistsError:
        return _current_request_result(
            status="request_root_already_exists",
            profile=profile,
            request_root=normalized_request_root,
            planned_results_root=normalized_planned_root,
            protected_evidence_roots=protected_roots,
            runtime_config=runtime_config,
            invocation=invocation,
            expected_branch_outputs=expected_outputs,
            written_files=written_files,
            no_overwrite_validation={
                **no_overwrite_validation,
                "request_root_preexisting": True,
            },
            validation_errors=["request_root must not already exist before writing"],
        )
    except OSError as exc:
        return _current_request_result(
            status="write_failed",
            profile=profile,
            request_root=normalized_request_root,
            planned_results_root=normalized_planned_root,
            protected_evidence_roots=protected_roots,
            runtime_config=runtime_config,
            invocation=invocation,
            expected_branch_outputs=expected_outputs,
            written_files=written_files,
            no_overwrite_validation=no_overwrite_validation,
            validation_errors=[f"current branch request write failed: {exc}"],
        )

    return _current_request_result(
        status="present",
        profile=profile,
        request_root=normalized_request_root,
        planned_results_root=normalized_planned_root,
        protected_evidence_roots=protected_roots,
        runtime_config=runtime_config,
        invocation=invocation,
        expected_branch_outputs=expected_outputs,
        written_files=written_files,
        no_overwrite_validation=no_overwrite_validation,
        validation_errors=[],
    )


def write_real_ab_bounded_smoke_comparison(
    *,
    current_results_root: Any,
    heuristic_results_root: Any,
    output_path: Any,
    protected_evidence_roots: Sequence[Any],
    expected_target_cycle_gate: int = 1,
    expected_terminal_hold_steps: int = TARGET_CYCLE_GATE_TERMINAL_HOLD_STEPS,
    profile: str = DEFAULT_COMPARISON_PROFILE,
) -> dict[str, Any]:
    """Write a comparison JSON from real A/B bounded smoke result roots."""

    normalized_current_root = _path_string(current_results_root)
    normalized_heuristic_root = _path_string(heuristic_results_root)
    normalized_output_path = _path_string(output_path)
    protected_roots = _string_list(protected_evidence_roots)
    no_overwrite_validation = _output_no_overwrite_validation(
        output_path=normalized_output_path,
        protected_evidence_roots=protected_roots,
    )
    branches = {
        CURRENT_BRANCH_NAME: _branch_summary(
            CURRENT_BRANCH_NAME,
            normalized_current_root,
        ),
        HEURISTIC_BRANCH_NAME: _branch_summary(
            HEURISTIC_BRANCH_NAME,
            normalized_heuristic_root,
        ),
        CALIBRATED_BRANCH_NAME: _calibrated_branch(),
    }
    validation_errors = _comparison_validation_errors(
        branches,
        no_overwrite_validation=no_overwrite_validation,
        expected_target_cycle_gate=int(expected_target_cycle_gate),
        expected_terminal_hold_steps=int(expected_terminal_hold_steps),
    )
    status = "present" if not validation_errors else "invalid_branch_artifacts"
    result = _comparison_result(
        status=status,
        profile=profile,
        output_path=normalized_output_path,
        protected_evidence_roots=protected_roots,
        branches=branches,
        no_overwrite_validation=no_overwrite_validation,
        expected_target_cycle_gate=int(expected_target_cycle_gate),
        validation_errors=validation_errors,
    )
    if status != "present":
        return result

    assert normalized_output_path is not None
    target_path = _resolve_path(normalized_output_path)
    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except FileExistsError:
        return _comparison_result(
            status="output_path_already_exists",
            profile=profile,
            output_path=normalized_output_path,
            protected_evidence_roots=protected_roots,
            branches=branches,
            no_overwrite_validation={
                **no_overwrite_validation,
                "output_path_preexisting": True,
            },
            expected_target_cycle_gate=int(expected_target_cycle_gate),
            validation_errors=["output_path must not already exist before writing"],
        )
    except OSError as exc:
        return _comparison_result(
            status="write_failed",
            profile=profile,
            output_path=normalized_output_path,
            protected_evidence_roots=protected_roots,
            branches=branches,
            no_overwrite_validation=no_overwrite_validation,
            expected_target_cycle_gate=int(expected_target_cycle_gate),
            validation_errors=[f"real A/B smoke comparison write failed: {exc}"],
        )
    return result


def _invalid_current_request(
    *,
    status: str,
    profile: str,
    request_root: str | None,
    planned_results_root: str | None,
    protected_evidence_roots: list[str],
    no_overwrite_validation: Mapping[str, Any],
    validation_errors: list[str],
) -> dict[str, Any]:
    return _current_request_result(
        status=status,
        profile=profile,
        request_root=request_root,
        planned_results_root=planned_results_root,
        protected_evidence_roots=protected_evidence_roots,
        runtime_config={},
        invocation={},
        expected_branch_outputs={},
        written_files=[],
        no_overwrite_validation=no_overwrite_validation,
        validation_errors=validation_errors,
    )


def _current_request_result(
    *,
    status: str,
    profile: str,
    request_root: str | None,
    planned_results_root: str | None,
    protected_evidence_roots: list[str],
    runtime_config: Mapping[str, Any],
    invocation: Mapping[str, Any],
    expected_branch_outputs: Mapping[str, Any],
    written_files: list[str],
    no_overwrite_validation: Mapping[str, Any],
    validation_errors: list[str],
) -> dict[str, Any]:
    return {
        "schema": CURRENT_REQUEST_SCHEMA,
        "source": CURRENT_REQUEST_SOURCE,
        "status": status,
        "offline_only": True,
        "profile": str(profile),
        "branch": CURRENT_BRANCH_NAME,
        "request_root": request_root,
        "planned_results_root": planned_results_root,
        "written_files": list(written_files),
        "artifact_count": len(written_files),
        "runtime_config": dict(runtime_config),
        "argv": list(invocation.get("argv", [])),
        "command": invocation.get("command"),
        "command_status": invocation.get("command_status"),
        "execution_status": "not_run",
        "expected_branch_outputs": dict(expected_branch_outputs),
        "no_overwrite_validation": dict(no_overwrite_validation),
        "validation_errors": list(validation_errors),
        "non_goal_statuses": _non_goal_statuses(),
        "protected_evidence_roots": list(protected_evidence_roots),
    }


def _comparison_result(
    *,
    status: str,
    profile: str,
    output_path: str | None,
    protected_evidence_roots: list[str],
    branches: Mapping[str, Mapping[str, Any]],
    no_overwrite_validation: Mapping[str, Any],
    expected_target_cycle_gate: int,
    validation_errors: list[str],
) -> dict[str, Any]:
    return {
        "schema": COMPARISON_SCHEMA,
        "source": COMPARISON_SOURCE,
        "status": status,
        "offline_only": True,
        "bounded_smoke_only": True,
        "profile": str(profile),
        "output_path": output_path,
        "branch_order": list(BRANCH_ORDER),
        "branches": {name: dict(branches[name]) for name in BRANCH_ORDER},
        "comparison_scope": _comparison_scope(expected_target_cycle_gate),
        "no_overwrite_validation": dict(no_overwrite_validation),
        "validation_errors": list(validation_errors),
        "non_goal_statuses": _non_goal_statuses(),
        "protected_evidence_roots": list(protected_evidence_roots),
    }


def _invocation_payload(
    *,
    schema: str,
    source: str,
    profile: str,
    branch: str,
    argv: Sequence[str],
    branch_output_dir: str,
    config_artifact_path: str,
    expected_branch_outputs: Mapping[str, Any],
    no_overwrite_validation: Mapping[str, Any],
) -> dict[str, Any]:
    normalized_argv = [str(item) for item in argv]
    return {
        "schema": schema,
        "source": source,
        "status": "present",
        "offline_only": True,
        "profile": str(profile),
        "branch": branch,
        "command_status": "ready_for_runner_invocation",
        "execution_status": "not_run",
        "argv": normalized_argv,
        "command": shlex.join(normalized_argv),
        "planned_output_dir": branch_output_dir,
        "config_path": config_artifact_path,
        "expected_branch_outputs": dict(expected_branch_outputs),
        "no_overwrite_validation": dict(no_overwrite_validation),
        "non_goal_statuses": _non_goal_statuses(),
    }


def _current_branch_eval_config(
    baseline_config: Mapping[str, Any],
    *,
    target_cycle_gate: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    config = copy.deepcopy(dict(baseline_config))
    eval_cfg = config.setdefault("eval", {})
    if not isinstance(eval_cfg, dict):
        raise ValueError("eval config must be a mapping")
    eval_cfg["target_cycle_gate"] = int(target_cycle_gate)
    eval_cfg["target_cycle_gate_terminal_hold_steps"] = (
        TARGET_CYCLE_GATE_TERMINAL_HOLD_STEPS
    )
    eval_cfg["save_video"] = False
    policy_cfg = config.setdefault("policy", {})
    dig_cut_cfg = (
        policy_cfg.get("dig_cut_planner", {})
        if isinstance(policy_cfg, Mapping)
        else {}
    )
    runtime_config = {
        "eval.target_cycle_gate_terminal_hold_steps": (
            TARGET_CYCLE_GATE_TERMINAL_HOLD_STEPS
        ),
        "eval.target_cycle_gate": int(target_cycle_gate),
        "eval.save_video": False,
        "dig_cut_planner.mode": _string_or_none(
            _mapping_value(dig_cut_cfg).get("mode")
        ),
    }
    return config, runtime_config


def _branch_summary(branch_name: str, results_root_value: str | None) -> dict[str, Any]:
    if results_root_value is None:
        return {
            "branch_name": branch_name,
            "status": "missing",
            "reason": "results_root must be a non-empty path string",
        }
    results_root = _resolve_path(results_root_value)
    metadata, metadata_error = _read_json_object(results_root / "eval_run_metadata.json")
    metrics, metrics_error = _read_json_object(results_root / "metrics.json")
    manifest, manifest_error = _read_json_object(results_root / "rollout_manifest.json")
    summary, summary_error = _read_json_object(
        results_root / "rollouts" / "rollout_000_summary.json"
    )
    resolved_config, config_error = _read_yaml_object(
        results_root / "eval_resolved_config.yaml"
    )
    read_errors = [
        error
        for error in (
            metadata_error,
            metrics_error,
            manifest_error,
            summary_error,
            config_error,
        )
        if error is not None
    ]
    if read_errors:
        return {
            "branch_name": branch_name,
            "status": "missing_artifacts",
            "results_root": results_root_value,
            "validation_errors": read_errors,
        }

    eval_cfg = _mapping_value(resolved_config.get("eval"))
    policy_cfg = _mapping_value(resolved_config.get("policy"))
    dig_cut_cfg = _mapping_value(policy_cfg.get("dig_cut_planner"))
    metrics_extra = _mapping_value(metrics.get("extra"))
    rollout_record = _first_rollout_record(manifest)
    line_count, rollout_log_path = _rollout_line_count(results_root)
    metadata_status = str(metadata.get("status", ""))
    return {
        "branch_name": branch_name,
        "status": "present" if metadata_status == "completed" else "invalid",
        "evidence_type": "real_tb_eval_bounded_smoke",
        "results_root": results_root_value,
        "metadata_status": metadata_status,
        "metadata_error": metadata.get("error"),
        "argv": [str(item) for item in metadata.get("argv", [])]
        if isinstance(metadata.get("argv"), Sequence)
        and not isinstance(metadata.get("argv"), (str, bytes))
        else [],
        "config_facts": {
            "eval.target_cycle_gate": _int_or_none(eval_cfg.get("target_cycle_gate")),
            "eval.target_cycle_gate_terminal_hold_steps": _int_or_none(
                eval_cfg.get("target_cycle_gate_terminal_hold_steps")
            ),
            "eval.save_video": bool(eval_cfg.get("save_video")),
            "dig_cut_planner.mode": _string_or_none(dig_cut_cfg.get("mode")),
            "dig_cut_planner.residual_cut_intent_source_path": _string_or_none(
                dig_cut_cfg.get("residual_cut_intent_source_path")
            ),
            "dig_cut_planner.fallback_mode": _string_or_none(
                dig_cut_cfg.get("fallback_mode")
            ),
            "dig_cut_planner.hold_token_until_skill_exit": dig_cut_cfg.get(
                "hold_token_until_skill_exit"
            ),
        },
        "target_cycle_gate": _coalesce(
            summary.get("target_cycle_gate"),
            metrics_extra.get("target_cycle_gate"),
            metadata.get("target_cycle_gate"),
        ),
        "target_cycle_gate_terminal_hold_steps": _coalesce(
            metrics_extra.get("target_cycle_gate_terminal_hold_steps"),
            eval_cfg.get("target_cycle_gate_terminal_hold_steps"),
        ),
        "target_cycle_gate_success_rate": metrics_extra.get(
            "target_cycle_gate_success_rate"
        ),
        "target_cycle_completed_dump_mean": metrics_extra.get(
            "target_cycle_completed_dump_mean"
        ),
        "target_cycle_completed_dump_count": _coalesce(
            summary.get("target_cycle_completed_dump_count"),
            rollout_record.get("target_cycle_completed_dump_count"),
        ),
        "target_cycle_gate_success": _coalesce(
            summary.get("target_cycle_gate_success"),
            rollout_record.get("target_cycle_gate_success"),
        ),
        "target_cycle_gate_stop_reason": _coalesce(
            summary.get("target_cycle_gate_stop_reason"),
            rollout_record.get("target_cycle_gate_stop_reason"),
        ),
        "completed_dump_count": _coalesce(
            summary.get("completed_dump_count"),
            rollout_record.get("completed_dump_count"),
        ),
        "primitive_cycle_index": _coalesce(
            summary.get("primitive_cycle_index"),
            rollout_record.get("primitive_cycle_index"),
        ),
        "rollout_line_count": line_count,
        "rollout_log_path": rollout_log_path,
        "metrics": {
            "n_rollouts": metrics.get("n_rollouts"),
            "success_rate": metrics.get("success_rate"),
            "avg_episode_len": metrics.get("avg_episode_len"),
            "avg_final_bucket_mass": metrics_extra.get("avg_final_bucket_mass"),
            "avg_max_success_signal": metrics_extra.get("avg_max_success_signal"),
        },
    }


def _comparison_validation_errors(
    branches: Mapping[str, Mapping[str, Any]],
    *,
    no_overwrite_validation: Mapping[str, Any],
    expected_target_cycle_gate: int,
    expected_terminal_hold_steps: int,
) -> list[str]:
    if no_overwrite_validation["status"] != "present":
        return list(no_overwrite_validation["validation_errors"])
    errors: list[str] = []
    for branch_name in (CURRENT_BRANCH_NAME, HEURISTIC_BRANCH_NAME):
        branch = branches[branch_name]
        if branch.get("status") != "present":
            errors.append(f"{branch_name} result artifacts must be present")
            continue
        if _int_or_none(branch.get("target_cycle_gate")) != expected_target_cycle_gate:
            errors.append(
                f"{branch_name} target_cycle_gate must be {expected_target_cycle_gate}"
            )
        if (
            _int_or_none(branch.get("target_cycle_gate_terminal_hold_steps"))
            != expected_terminal_hold_steps
        ):
            errors.append(
                f"{branch_name} target_cycle_gate_terminal_hold_steps must be {expected_terminal_hold_steps}"
            )
    heuristic_mode = _mapping_value(
        branches[HEURISTIC_BRANCH_NAME].get("config_facts")
    ).get("dig_cut_planner.mode")
    if branches[HEURISTIC_BRANCH_NAME].get("status") == "present" and (
        heuristic_mode != "residual_cut_intent"
    ):
        errors.append(
            "heuristic_residual_pipeline dig_cut_planner.mode must be residual_cut_intent"
        )
    return errors


def _calibrated_branch() -> dict[str, Any]:
    return {
        "branch_name": CALIBRATED_BRANCH_NAME,
        "status": "not_evaluated",
        "reason": "blocked_by_missing_gold_samples",
    }


def _current_eval_argv(metadata: Any) -> tuple[list[str], list[str]]:
    if not isinstance(metadata, Mapping):
        return [], ["current_eval_metadata must be a mapping"]
    argv = metadata.get("argv")
    if not isinstance(argv, Sequence) or isinstance(argv, (str, bytes)) or not argv:
        return [], ["current_eval_metadata must include a non-empty argv list"]
    normalized = [str(item) for item in argv]
    if not all(normalized):
        return [], ["current_eval_metadata argv entries must be non-empty strings"]
    return normalized, []


def _read_eval_config(path_value: str | None) -> tuple[dict[str, Any], list[str]]:
    if path_value is None:
        return {}, ["current eval argv must include --config or -c"]
    config_path = _resolve_path(path_value)
    payload, error = _read_yaml_object(config_path)
    if error is not None:
        return {}, [error.replace(str(config_path), "current eval config", 1)]
    policy = payload.get("policy")
    if not isinstance(policy, Mapping):
        return {}, ["current eval config must include policy mapping"]
    if str(policy.get("class", "")).lower() != "primitive_planner_act":
        return {}, ["current eval config policy.class must be primitive_planner_act"]
    return dict(payload), []


def _read_json_object(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, f"{path} read failed: {exc}"
    if not isinstance(parsed, Mapping):
        return {}, f"{path} must contain a JSON object"
    return {str(key): value for key, value in parsed.items()}, None


def _read_yaml_object(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        return {}, f"{path} read failed: {exc}"
    if not isinstance(parsed, Mapping):
        return {}, f"{path} must contain a YAML mapping"
    return {str(key): value for key, value in parsed.items()}, None


def _argv_with_smoke_overrides(
    argv: Sequence[str],
    *,
    config_path: str,
    output_dir: str,
    target_cycle_gate: int,
) -> list[str]:
    updated = _argv_with_value(argv, "--config", config_path, alternate="-c")
    updated = _argv_with_value(updated, "--output-dir", output_dir)
    updated = _argv_with_value(
        updated,
        "--target-cycle-gate",
        str(int(target_cycle_gate)),
    )
    return _argv_with_flag(updated, "--no-video")


def _argv_with_value(
    argv: Sequence[str],
    flag: str,
    value: str,
    *,
    alternate: str | None = None,
) -> list[str]:
    normalized = [str(item) for item in argv]
    candidates = [flag]
    if alternate is not None:
        candidates.append(alternate)
    for candidate in candidates:
        if candidate in normalized:
            index = normalized.index(candidate)
            if index == len(normalized) - 1:
                return [*normalized, value]
            updated = list(normalized)
            updated[index + 1] = value
            return updated
    return [*normalized, flag, value]


def _argv_with_flag(argv: Sequence[str], flag: str) -> list[str]:
    normalized = [str(item) for item in argv]
    return normalized if flag in normalized else [*normalized, flag]


def _config_path_from_argv(argv: Sequence[str]) -> str | None:
    normalized = [str(item) for item in argv]
    for flag in ("--config", "-c"):
        if flag in normalized:
            index = normalized.index(flag)
            if index < len(normalized) - 1:
                return normalized[index + 1]
    return None


def _expected_branch_outputs(branch_output_dir: str) -> dict[str, str]:
    results_dir = str(Path(branch_output_dir) / "results")
    return {
        "output_dir": branch_output_dir,
        "results_dir": results_dir,
        "eval_run_metadata": str(Path(results_dir) / "eval_run_metadata.json"),
        "eval_resolved_config": str(Path(results_dir) / "eval_resolved_config.yaml"),
        "metrics_json": str(Path(results_dir) / "metrics.json"),
        "results_csv": str(Path(results_dir) / "results.csv"),
        "rollout_manifest": str(Path(results_dir) / "rollout_manifest.json"),
        "rollout_log_dir": str(Path(results_dir) / "rollouts"),
        "hdf5_dir": str(Path(results_dir) / "hdf5_rollouts"),
    }


def _request_no_overwrite_validation(
    *,
    request_root: str | None,
    planned_results_root: str | None,
    protected_evidence_roots: Sequence[str],
) -> dict[str, Any]:
    if request_root is None:
        return _invalid_no_overwrite(
            "invalid_request_root",
            "request_root must be a non-empty path string",
            request_root=request_root,
            planned_results_root=planned_results_root,
            protected_evidence_roots=protected_evidence_roots,
        )
    if planned_results_root is None:
        return _invalid_no_overwrite(
            "invalid_planned_results_root",
            "planned_results_root must be a non-empty path string",
            request_root=request_root,
            planned_results_root=planned_results_root,
            protected_evidence_roots=protected_evidence_roots,
        )
    request_path = _resolve_path(request_root)
    planned_path = _resolve_path(planned_results_root)
    cwd = Path.cwd().resolve(strict=False)
    if not _same_or_nested(request_path, cwd):
        return _invalid_no_overwrite(
            "invalid_request_root",
            "request_root must be a relative path or stay under the current repository root",
            request_root=request_root,
            planned_results_root=planned_results_root,
            protected_evidence_roots=protected_evidence_roots,
        )
    if not _same_or_nested(planned_path, cwd):
        return _invalid_no_overwrite(
            "invalid_planned_results_root",
            "planned_results_root must be a relative path or stay under the current repository root",
            request_root=request_root,
            planned_results_root=planned_results_root,
            protected_evidence_roots=protected_evidence_roots,
        )
    overlaps = _protected_overlaps(
        [request_path, planned_path],
        protected_evidence_roots,
    )
    if overlaps:
        return {
            "status": "protected_evidence_root_overlap",
            "request_root": request_root,
            "planned_results_root": planned_results_root,
            "protected_evidence_roots": list(protected_evidence_roots),
            "overlapping_protected_roots": overlaps,
            "validation_errors": [
                "request_root and planned_results_root must not equal or nest under a protected evidence root"
            ],
        }
    if request_path.exists():
        return _invalid_no_overwrite(
            "request_root_already_exists",
            "request_root must not already exist before writing",
            request_root=request_root,
            planned_results_root=planned_results_root,
            protected_evidence_roots=protected_evidence_roots,
        )
    if planned_path.exists():
        return _invalid_no_overwrite(
            "planned_results_root_already_exists",
            "planned_results_root must not already exist before request writing",
            request_root=request_root,
            planned_results_root=planned_results_root,
            protected_evidence_roots=protected_evidence_roots,
        )
    return {
        "status": "present",
        "request_root": request_root,
        "planned_results_root": planned_results_root,
        "protected_evidence_roots": list(protected_evidence_roots),
        "overlapping_protected_roots": [],
        "request_root_preexisting": False,
        "planned_results_root_preexisting": False,
        "validation_errors": [],
    }


def _output_no_overwrite_validation(
    *,
    output_path: str | None,
    protected_evidence_roots: Sequence[str],
) -> dict[str, Any]:
    if output_path is None:
        return {
            "status": "invalid_output_path",
            "output_path": output_path,
            "protected_evidence_roots": list(protected_evidence_roots),
            "validation_errors": ["output_path must be a non-empty path string"],
        }
    resolved_output = _resolve_path(output_path)
    cwd = Path.cwd().resolve(strict=False)
    if not _same_or_nested(resolved_output, cwd):
        return {
            "status": "invalid_output_path",
            "output_path": output_path,
            "protected_evidence_roots": list(protected_evidence_roots),
            "validation_errors": [
                "output_path must be a relative path or stay under the current repository root"
            ],
        }
    overlaps = _protected_overlaps([resolved_output], protected_evidence_roots)
    if overlaps:
        return {
            "status": "protected_evidence_root_overlap",
            "output_path": output_path,
            "protected_evidence_roots": list(protected_evidence_roots),
            "overlapping_protected_roots": overlaps,
            "validation_errors": [
                "output_path must not equal or nest under a protected evidence root"
            ],
        }
    if resolved_output.exists():
        return {
            "status": "output_path_already_exists",
            "output_path": output_path,
            "protected_evidence_roots": list(protected_evidence_roots),
            "overlapping_protected_roots": [],
            "validation_errors": [
                "output_path must not already exist before writing"
            ],
        }
    return {
        "status": "present",
        "output_path": output_path,
        "protected_evidence_roots": list(protected_evidence_roots),
        "overlapping_protected_roots": [],
        "output_path_preexisting": False,
        "validation_errors": [],
    }


def _invalid_no_overwrite(
    status: str,
    error: str,
    *,
    request_root: str | None,
    planned_results_root: str | None,
    protected_evidence_roots: Sequence[str],
) -> dict[str, Any]:
    return {
        "status": status,
        "request_root": request_root,
        "planned_results_root": planned_results_root,
        "protected_evidence_roots": list(protected_evidence_roots),
        "overlapping_protected_roots": [],
        "validation_errors": [error],
    }


def _protected_overlaps(
    candidate_paths: Sequence[Path],
    protected_evidence_roots: Sequence[str],
) -> list[str]:
    protected_paths = [_resolve_path(path) for path in protected_evidence_roots]
    return [
        str(protected_path)
        for protected_path in protected_paths
        if any(_same_or_nested(candidate, protected_path) for candidate in candidate_paths)
    ]


def _first_rollout_record(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    rollouts = manifest.get("rollouts")
    if isinstance(rollouts, Sequence) and not isinstance(rollouts, (str, bytes)):
        for record in rollouts:
            if isinstance(record, Mapping):
                return record
    return {}


def _rollout_line_count(results_root: Path) -> tuple[int | None, str | None]:
    for path in (
        results_root / "rollouts" / "rollout_000.jsonl",
        results_root / "rollouts" / "rollout_000.partial.jsonl",
    ):
        if not path.is_file():
            continue
        try:
            return sum(1 for _ in path.open(encoding="utf-8")), str(path)
        except OSError:
            return None, str(path)
    return None, None


def _comparison_scope(expected_target_cycle_gate: int) -> dict[str, str]:
    evidence_scope = (
        "bounded_one_cycle_smoke"
        if expected_target_cycle_gate <= 1
        else "bounded_multi_cycle_smoke"
    )
    return {
        "evidence_scope": evidence_scope,
        "full_phase6_success_claim": "not_claimed",
        "official_pass_fail_status": "defined_by_terrain_residual_pass_fail_v1",
        "production_readiness_status": "not_claimed",
        "calibrated_fallback_status": "not_invented",
    }


def _non_goal_statuses() -> dict[str, str]:
    return {
        "production_planner_integration_status": "not_integrated",
        "rollout_review_schema_integration_status": "not_integrated",
        "runtime_action_status": "not_created",
        "command_space_control_status": "not_created",
        **official_contract_statuses(),
    }


def _path_string(value: Any) -> str | None:
    if isinstance(value, Path):
        value = str(value)
    if not isinstance(value, str) or not value:
        return None
    return value


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [str(item) for item in value if str(item)]


def _resolve_path(path: str) -> Path:
    raw_path = Path(path)
    if not raw_path.is_absolute():
        raw_path = Path.cwd() / raw_path
    return raw_path.resolve(strict=False)


def _same_or_nested(child: Path, parent: Path) -> bool:
    return child == parent or parent in child.parents


def _mapping_value(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coalesce(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


__all__ = [
    "write_current_planner_bounded_smoke_request",
    "write_real_ab_bounded_smoke_comparison",
]
