"""Runner-facing B-branch invocation artifacts for residual terrain eval."""

from __future__ import annotations

import copy
import json
import math
import shlex
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

from testbed.eval.terrain_residual_eval_run_plan import (
    build_residual_eval_run_plan,
)
from testbed.planner.primitive.token.dig_planning import (
    DIG_CUT_PLANNER_MODE_RESIDUAL_CUT_INTENT,
)
from testbed.planner.primitive.token.residual_cut_intent_source import (
    RESIDUAL_CUT_INTENT_RUNTIME_SOURCE_SCHEMA,
)


SCHEMA = "terrain_residual_b_branch_eval_request_v1"
SOURCE = "explicit_residual_b_branch_eval_request"
DEFAULT_PROFILE = "phase6g_f_residual_b_branch_eval_request"
BRANCH_NAME = "heuristic_residual_pipeline"
CONFIG_FILENAME = "heuristic_residual_pipeline_eval_config.yaml"
INVOCATION_FILENAME = "heuristic_residual_pipeline_invocation.json"
RUN_PLAN_FILENAME = "residual_eval_run_plan.json"
B_BRANCH_TARGET_CYCLE_GATE_TERMINAL_HOLD_STEPS = 0
WRITTEN_FILES = [
    CONFIG_FILENAME,
    INVOCATION_FILENAME,
    RUN_PLAN_FILENAME,
]
REQUEST_ROOT_ERROR = (
    "request_root must be a relative path or stay under the current repository root"
)
PLANNED_ROOT_ERROR = (
    "planned_results_root must be a relative path or stay under the current repository root"
)
PROTECTED_ROOT_ERROR = (
    "request_root and planned_results_root must not equal or nest under a protected evidence root"
)


def write_residual_b_branch_eval_request(
    *,
    current_eval_metadata: Mapping[str, Any],
    predicted_ab_artifact_root: Any,
    runtime_source_path: Any,
    request_root: Any,
    planned_results_root: Any,
    protected_evidence_roots: Sequence[Any],
    target_cycle_gate: Any | None = None,
    profile: str = DEFAULT_PROFILE,
) -> dict[str, Any]:
    """Write an explicit B-branch eval request consumable by ``tb-eval``."""

    normalized_request_root = _path_string(request_root)
    normalized_planned_root = _path_string(planned_results_root)
    protected_roots = _string_list(protected_evidence_roots)
    no_overwrite_validation = _no_overwrite_validation(
        request_root=normalized_request_root,
        planned_results_root=normalized_planned_root,
        protected_evidence_roots=protected_roots,
    )
    if no_overwrite_validation["status"] != "present":
        return _result(
            status=str(no_overwrite_validation["status"]),
            profile=profile,
            request_root=normalized_request_root,
            planned_results_root=normalized_planned_root,
            protected_evidence_roots=protected_roots,
            runtime_config={},
            runtime_source={},
            invocation={},
            expected_branch_outputs={},
            eval_run_plan={},
            written_files=[],
            no_overwrite_validation=no_overwrite_validation,
            validation_errors=list(no_overwrite_validation["validation_errors"]),
        )

    current_argv, argv_errors = _current_eval_argv(current_eval_metadata)
    if argv_errors:
        return _invalid_result(
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
        return _invalid_result(
            status="invalid_current_eval_config",
            profile=profile,
            request_root=normalized_request_root,
            planned_results_root=normalized_planned_root,
            protected_evidence_roots=protected_roots,
            no_overwrite_validation=no_overwrite_validation,
            validation_errors=config_errors,
        )

    predicted_artifacts, artifact_errors = _predicted_artifact_summary(
        predicted_ab_artifact_root
    )
    if artifact_errors:
        return _invalid_result(
            status="invalid_predicted_ab_artifacts",
            profile=profile,
            request_root=normalized_request_root,
            planned_results_root=normalized_planned_root,
            protected_evidence_roots=protected_roots,
            no_overwrite_validation=no_overwrite_validation,
            validation_errors=artifact_errors,
        )

    normalized_runtime_source_path = _path_string(runtime_source_path)
    normalized_target_cycle_gate, target_cycle_gate_error = _target_cycle_gate(
        target_cycle_gate
    )
    if target_cycle_gate_error is not None:
        return _invalid_result(
            status="invalid_target_cycle_gate",
            profile=profile,
            request_root=normalized_request_root,
            planned_results_root=normalized_planned_root,
            protected_evidence_roots=protected_roots,
            no_overwrite_validation=no_overwrite_validation,
            validation_errors=[target_cycle_gate_error],
        )
    runtime_source_summary, runtime_source_errors = _runtime_source_summary(
        normalized_runtime_source_path,
        target_cycle_gate=normalized_target_cycle_gate,
    )
    if runtime_source_errors:
        return _invalid_result(
            status="invalid_runtime_source",
            profile=profile,
            request_root=normalized_request_root,
            planned_results_root=normalized_planned_root,
            protected_evidence_roots=protected_roots,
            no_overwrite_validation=no_overwrite_validation,
            validation_errors=runtime_source_errors,
        )

    assert normalized_request_root is not None
    assert normalized_planned_root is not None
    config_artifact_path = str(Path(normalized_request_root) / CONFIG_FILENAME)
    branch_output_dir = str(Path(normalized_planned_root) / BRANCH_NAME)
    generated_config, runtime_config = _b_branch_eval_config(
        baseline_config,
        runtime_source_path=normalized_runtime_source_path,
        target_cycle_gate=normalized_target_cycle_gate,
    )
    heuristic_argv = _argv_with_config_output_and_target_gate(
        current_argv,
        config_path=config_artifact_path,
        output_dir=branch_output_dir,
        target_cycle_gate=normalized_target_cycle_gate,
    )
    eval_run_plan = build_residual_eval_run_plan(
        current_eval_metadata=current_eval_metadata,
        predicted_ab_artifacts=predicted_artifacts,
        planned_results_root=normalized_planned_root,
        protected_evidence_roots=protected_roots,
        residual_runtime_integration_available=True,
        residual_runtime_planner_mode_available=True,
        residual_cut_intent_token_adapter_available=True,
        residual_cut_intent_source_provider_available=True,
        heuristic_branch_argv=heuristic_argv,
    )
    if eval_run_plan.get("status") != "present":
        return _invalid_result(
            status="invalid_eval_run_plan",
            profile=profile,
            request_root=normalized_request_root,
            planned_results_root=normalized_planned_root,
            protected_evidence_roots=protected_roots,
            no_overwrite_validation=no_overwrite_validation,
            validation_errors=list(eval_run_plan.get("validation_errors", []))
            or ["residual eval run plan status must be present"],
        )

    expected_outputs = _expected_branch_outputs(branch_output_dir)
    invocation = _invocation_payload(
        profile=profile,
        argv=heuristic_argv,
        command_status="ready_for_runner_invocation",
        branch_output_dir=branch_output_dir,
        config_artifact_path=config_artifact_path,
        runtime_source_summary=runtime_source_summary,
        predicted_artifacts=predicted_artifacts,
        expected_branch_outputs=expected_outputs,
        no_overwrite_validation=no_overwrite_validation,
    )
    payloads = {
        CONFIG_FILENAME: generated_config,
        INVOCATION_FILENAME: invocation,
        RUN_PLAN_FILENAME: eval_run_plan,
    }

    root_path = _resolve_path(normalized_request_root)
    written_files: list[str] = []
    try:
        root_path.mkdir(parents=True, exist_ok=False)
        for relative_path in WRITTEN_FILES:
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
        return _result(
            status="request_root_already_exists",
            profile=profile,
            request_root=normalized_request_root,
            planned_results_root=normalized_planned_root,
            protected_evidence_roots=protected_roots,
            runtime_config=runtime_config,
            runtime_source=runtime_source_summary,
            invocation=invocation,
            expected_branch_outputs=expected_outputs,
            eval_run_plan=eval_run_plan,
            written_files=written_files,
            no_overwrite_validation={
                **no_overwrite_validation,
                "request_root_preexisting": True,
            },
            validation_errors=["request_root must not already exist before writing"],
        )
    except OSError as exc:
        return _result(
            status="write_failed",
            profile=profile,
            request_root=normalized_request_root,
            planned_results_root=normalized_planned_root,
            protected_evidence_roots=protected_roots,
            runtime_config=runtime_config,
            runtime_source=runtime_source_summary,
            invocation=invocation,
            expected_branch_outputs=expected_outputs,
            eval_run_plan=eval_run_plan,
            written_files=written_files,
            no_overwrite_validation=no_overwrite_validation,
            validation_errors=[f"B branch request write failed: {exc}"],
        )

    return _result(
        status="present",
        profile=profile,
        request_root=normalized_request_root,
        planned_results_root=normalized_planned_root,
        protected_evidence_roots=protected_roots,
        runtime_config=runtime_config,
        runtime_source=runtime_source_summary,
        invocation=invocation,
        expected_branch_outputs=expected_outputs,
        eval_run_plan=eval_run_plan,
        written_files=written_files,
        no_overwrite_validation=no_overwrite_validation,
        validation_errors=[],
    )


def _invalid_result(
    *,
    status: str,
    profile: str,
    request_root: str | None,
    planned_results_root: str | None,
    protected_evidence_roots: list[str],
    no_overwrite_validation: Mapping[str, Any],
    validation_errors: list[str],
) -> dict[str, Any]:
    return _result(
        status=status,
        profile=profile,
        request_root=request_root,
        planned_results_root=planned_results_root,
        protected_evidence_roots=protected_evidence_roots,
        runtime_config={},
        runtime_source={},
        invocation={},
        expected_branch_outputs={},
        eval_run_plan={},
        written_files=[],
        no_overwrite_validation=no_overwrite_validation,
        validation_errors=validation_errors,
    )


def _result(
    *,
    status: str,
    profile: str,
    request_root: str | None,
    planned_results_root: str | None,
    protected_evidence_roots: list[str],
    runtime_config: Mapping[str, Any],
    runtime_source: Mapping[str, Any],
    invocation: Mapping[str, Any],
    expected_branch_outputs: Mapping[str, Any],
    eval_run_plan: Mapping[str, Any],
    written_files: list[str],
    no_overwrite_validation: Mapping[str, Any],
    validation_errors: list[str],
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "source": SOURCE,
        "status": status,
        "offline_only": True,
        "profile": str(profile),
        "branch": BRANCH_NAME,
        "request_root": request_root,
        "planned_results_root": planned_results_root,
        "written_files": list(written_files),
        "artifact_count": len(written_files),
        "runtime_config": dict(runtime_config),
        "runtime_source": dict(runtime_source),
        "argv": list(invocation.get("argv", [])),
        "command": invocation.get("command"),
        "command_status": invocation.get("command_status"),
        "execution_status": "not_run",
        "expected_branch_outputs": dict(expected_branch_outputs),
        "eval_run_plan": dict(eval_run_plan),
        "no_overwrite_validation": dict(no_overwrite_validation),
        "validation_errors": list(validation_errors),
        "non_goal_statuses": _non_goal_statuses(),
        "provenance_statuses": _provenance_statuses(status),
        "protected_evidence_roots": list(protected_evidence_roots),
    }


def _invocation_payload(
    *,
    profile: str,
    argv: Sequence[str],
    command_status: str,
    branch_output_dir: str,
    config_artifact_path: str,
    runtime_source_summary: Mapping[str, Any],
    predicted_artifacts: Mapping[str, Any],
    expected_branch_outputs: Mapping[str, Any],
    no_overwrite_validation: Mapping[str, Any],
) -> dict[str, Any]:
    normalized_argv = [str(item) for item in argv]
    return {
        "schema": SCHEMA,
        "source": SOURCE,
        "status": "present",
        "offline_only": True,
        "profile": str(profile),
        "branch": BRANCH_NAME,
        "command_status": command_status,
        "execution_status": "not_run",
        "argv": normalized_argv,
        "command": shlex.join(normalized_argv),
        "planned_output_dir": branch_output_dir,
        "config_path": config_artifact_path,
        "runtime_source": dict(runtime_source_summary),
        "predicted_ab_artifacts": dict(predicted_artifacts),
        "expected_branch_outputs": dict(expected_branch_outputs),
        "no_overwrite_validation": dict(no_overwrite_validation),
        "non_goal_statuses": _non_goal_statuses(),
    }


def _b_branch_eval_config(
    baseline_config: Mapping[str, Any],
    *,
    runtime_source_path: str | None,
    target_cycle_gate: int | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    config = copy.deepcopy(dict(baseline_config))
    eval_cfg = config.setdefault("eval", {})
    if not isinstance(eval_cfg, dict):
        raise ValueError("eval config must be a mapping")
    eval_cfg["target_cycle_gate_terminal_hold_steps"] = (
        B_BRANCH_TARGET_CYCLE_GATE_TERMINAL_HOLD_STEPS
    )
    if target_cycle_gate is not None:
        eval_cfg["target_cycle_gate"] = int(target_cycle_gate)
    policy_cfg = config.setdefault("policy", {})
    if not isinstance(policy_cfg, dict):
        raise ValueError("policy config must be a mapping")
    dig_cut_cfg = dict(policy_cfg.get("dig_cut_planner", {}) or {})
    dig_cut_cfg.update(
        {
            "enabled": True,
            "mode": DIG_CUT_PLANNER_MODE_RESIDUAL_CUT_INTENT,
            "residual_cut_intent_source_path": str(runtime_source_path),
            "fallback_mode": "raise",
            "hold_token_until_skill_exit": False,
            "prior_path": "",
        }
    )
    policy_cfg["dig_cut_planner"] = dig_cut_cfg
    runtime_config = {
        "eval.target_cycle_gate_terminal_hold_steps": (
            B_BRANCH_TARGET_CYCLE_GATE_TERMINAL_HOLD_STEPS
        ),
        "dig_cut_planner.enabled": True,
        "dig_cut_planner.mode": DIG_CUT_PLANNER_MODE_RESIDUAL_CUT_INTENT,
        "dig_cut_planner.residual_cut_intent_source_path": str(runtime_source_path),
        "dig_cut_planner.fallback_mode": "raise",
        "dig_cut_planner.hold_token_until_skill_exit": False,
        "dig_cut_planner.prior_path": "",
    }
    if target_cycle_gate is not None:
        runtime_config["eval.target_cycle_gate"] = int(target_cycle_gate)
    return config, runtime_config


def _predicted_artifact_summary(root_value: Any) -> tuple[dict[str, Any], list[str]]:
    root = _path_string(root_value)
    if root is None:
        return {}, ["predicted_ab_artifact_root must be a non-empty path string"]
    root_path = _resolve_path(root)
    metadata_path = root_path / "eval_run_metadata.json"
    if not metadata_path.is_file():
        return {}, ["predicted_ab_artifact_root must contain eval_run_metadata.json"]
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [f"predicted artifact metadata read failed: {exc}"]
    if not isinstance(metadata, Mapping):
        return {}, ["predicted artifact metadata must be a JSON object"]
    artifact_files = _string_list(metadata.get("artifact_files", []))
    if "residual_cut_intent_runtime_source.json" not in artifact_files:
        return {}, [
            "predicted artifact metadata must list residual_cut_intent_runtime_source.json"
        ]
    return {
        "status": str(metadata.get("status", "present")),
        "results_root": root,
        "artifact_files": artifact_files,
        "branch_statuses": (
            dict(metadata.get("branch_statuses", {}))
            if isinstance(metadata.get("branch_statuses"), Mapping)
            else {}
        ),
        "metadata_path": str(metadata_path),
    }, []


def _runtime_source_summary(
    path_value: str | None,
    *,
    target_cycle_gate: int | None,
) -> tuple[dict[str, Any], list[str]]:
    if path_value is None:
        return {}, ["runtime_source_path must be a non-empty path string"]
    source_path = _resolve_path(path_value)
    if not source_path.is_file():
        return {}, ["runtime_source_path must point to an existing JSON file"]
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [f"runtime source read failed: {exc}"]
    if not isinstance(payload, Mapping):
        return {}, ["runtime source must be a JSON object"]
    if payload.get("status") != "present":
        return {}, ["runtime source status must be present"]
    if payload.get("schema") != RESIDUAL_CUT_INTENT_RUNTIME_SOURCE_SCHEMA:
        return {}, [
            f"runtime source schema must be {RESIDUAL_CUT_INTENT_RUNTIME_SOURCE_SCHEMA}"
        ]
    plans = payload.get("plans")
    if not isinstance(plans, Sequence) or isinstance(plans, (str, bytes)):
        return {}, ["runtime source must include a plans list"]
    cycle_indices = sorted(
        {
            cycle
            for plan in plans
            if isinstance(plan, Mapping)
            for cycle in [_nonnegative_int(plan.get("cycle_index"))]
            if cycle is not None
        }
    )
    required_cycle_indices = (
        list(range(int(target_cycle_gate))) if target_cycle_gate is not None else []
    )
    missing_required_cycle_indices = [
        cycle for cycle in required_cycle_indices if cycle not in cycle_indices
    ]
    if missing_required_cycle_indices:
        return {}, [
            "runtime source missing required cycle plans for target_cycle_gate "
            f"{target_cycle_gate}: {missing_required_cycle_indices}"
        ]
    candidate_ids = [
        str(plan.get("cut_intent_candidate_id"))
        for plan in plans
        if isinstance(plan, Mapping) and plan.get("cut_intent_candidate_id") is not None
    ]
    return {
        "path": path_value,
        "schema": str(payload.get("schema")),
        "source": str(payload.get("source", "")),
        "status": "present",
        "plan_count": len(plans),
        "cycle_indices": cycle_indices,
        "required_cycle_indices": required_cycle_indices,
        "missing_required_cycle_indices": missing_required_cycle_indices,
        "candidate_ids": candidate_ids,
    }, []


def _read_eval_config(path_value: str | None) -> tuple[dict[str, Any], list[str]]:
    if path_value is None:
        return {}, ["current eval argv must include --config or -c"]
    config_path = _resolve_path(path_value)
    if not config_path.is_file():
        return {}, ["current eval config path must point to an existing YAML file"]
    try:
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        return {}, [f"current eval config read failed: {exc}"]
    if not isinstance(payload, Mapping):
        return {}, ["current eval config must be a mapping"]
    policy = payload.get("policy")
    if not isinstance(policy, Mapping):
        return {}, ["current eval config must include policy mapping"]
    if str(policy.get("class", "")).lower() != "primitive_planner_act":
        return {}, ["current eval config policy.class must be primitive_planner_act"]
    return dict(payload), []


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


def _argv_with_config_output_and_target_gate(
    argv: Sequence[str],
    *,
    config_path: str,
    output_dir: str,
    target_cycle_gate: int | None,
) -> list[str]:
    updated = _argv_with_value(argv, "--config", config_path, alternate="-c")
    if target_cycle_gate is not None:
        updated = _argv_with_value(
            updated,
            "--target-cycle-gate",
            str(int(target_cycle_gate)),
        )
    return _argv_with_value(updated, "--output-dir", output_dir)


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


def _no_overwrite_validation(
    *,
    request_root: str | None,
    planned_results_root: str | None,
    protected_evidence_roots: Sequence[str],
) -> dict[str, Any]:
    if request_root is None:
        return {
            "status": "invalid_request_root",
            "request_root": request_root,
            "planned_results_root": planned_results_root,
            "protected_evidence_roots": list(protected_evidence_roots),
            "validation_errors": ["request_root must be a non-empty path string"],
        }
    if planned_results_root is None:
        return {
            "status": "invalid_planned_results_root",
            "request_root": request_root,
            "planned_results_root": planned_results_root,
            "protected_evidence_roots": list(protected_evidence_roots),
            "validation_errors": [
                "planned_results_root must be a non-empty path string"
            ],
        }
    request_path = _resolve_path(request_root)
    planned_path = _resolve_path(planned_results_root)
    cwd = Path.cwd().resolve(strict=False)
    if not _same_or_nested(request_path, cwd):
        return {
            "status": "invalid_request_root",
            "request_root": request_root,
            "planned_results_root": planned_results_root,
            "protected_evidence_roots": list(protected_evidence_roots),
            "validation_errors": [REQUEST_ROOT_ERROR],
        }
    if not _same_or_nested(planned_path, cwd):
        return {
            "status": "invalid_planned_results_root",
            "request_root": request_root,
            "planned_results_root": planned_results_root,
            "protected_evidence_roots": list(protected_evidence_roots),
            "validation_errors": [PLANNED_ROOT_ERROR],
        }
    protected_paths = [_resolve_path(path) for path in protected_evidence_roots]
    overlaps = [
        str(path)
        for path in protected_paths
        if _same_or_nested(request_path, path) or _same_or_nested(planned_path, path)
    ]
    if overlaps:
        return {
            "status": "protected_evidence_root_overlap",
            "request_root": request_root,
            "planned_results_root": planned_results_root,
            "protected_evidence_roots": list(protected_evidence_roots),
            "overlapping_protected_roots": overlaps,
            "validation_errors": [PROTECTED_ROOT_ERROR],
        }
    if request_path.exists():
        return {
            "status": "request_root_already_exists",
            "request_root": request_root,
            "planned_results_root": planned_results_root,
            "protected_evidence_roots": list(protected_evidence_roots),
            "overlapping_protected_roots": [],
            "validation_errors": [
                "request_root must not already exist before writing"
            ],
        }
    if planned_path.exists():
        return {
            "status": "planned_results_root_already_exists",
            "request_root": request_root,
            "planned_results_root": planned_results_root,
            "protected_evidence_roots": list(protected_evidence_roots),
            "overlapping_protected_roots": [],
            "validation_errors": [
                "planned_results_root must not already exist before request writing"
            ],
        }
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


def _same_or_nested(child: Path, parent: Path) -> bool:
    return child == parent or parent in child.parents


def _resolve_path(path: str) -> Path:
    raw_path = Path(path)
    if not raw_path.is_absolute():
        raw_path = Path.cwd() / raw_path
    return raw_path.resolve(strict=False)


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


def _target_cycle_gate(value: Any | None) -> tuple[int | None, str | None]:
    if value is None:
        return None, None
    parsed = _nonnegative_int(value)
    if parsed is None or parsed <= 0:
        return None, "target_cycle_gate must be a positive integer when provided"
    return parsed, None


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed < 0.0:
        return None
    integer = int(parsed)
    if not math.isclose(parsed, float(integer), abs_tol=1.0e-9):
        return None
    return integer


def _non_goal_statuses() -> dict[str, str]:
    return {
        "simulation_status": "not_run",
        "branch_execution_artifact_status": "not_created",
        "production_planner_integration_status": "not_integrated",
        "rollout_review_schema_integration_status": "not_integrated",
        "runtime_action_status": "not_created",
        "command_space_control_status": "not_created",
        "official_success_semantics_status": "not_defined",
        "official_default_status": "not_defined",
        "official_threshold_status": "not_defined",
        "calibrated_model_fallback_status": "not_invented",
    }


def _provenance_statuses(status: str) -> dict[str, str]:
    return {
        "current_eval_metadata_status": (
            "validated" if status == "present" else "not_validated"
        ),
        "current_eval_config_status": (
            "materialized_with_explicit_b_branch_overrides"
            if status == "present"
            else "not_materialized"
        ),
        "runtime_source_status": (
            "validated" if status == "present" else "not_validated"
        ),
        "runner_invocation_status": (
            "written" if status == "present" else "not_written"
        ),
    }


__all__ = ["write_residual_b_branch_eval_request"]
