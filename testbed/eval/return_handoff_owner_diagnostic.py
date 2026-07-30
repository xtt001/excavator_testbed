"""Offline owner audit for the Strict-18 return-to-dig handoff gate.

The audit replays the gate from recorded pre-action observations.  It first
removes only the global contact requirement, then isolates depth from that
contact decision while preserving the effective v7 prior bounds.  The module
also owns the request-local bounded configuration used after the offline proof.
Production defaults are never changed.
"""

from __future__ import annotations

import copy
import math
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np

from testbed.planner.primitive.effects.return_handoff import (
    ReturnStartEnvelopeGateConfig,
    ReturnStartEnvelopeGateInputs,
    ReturnStartEnvelopeGateResult,
    ReturnStartEnvelopeGateService,
)

OFFLINE_SCHEMA = "strict18_return_handoff_owner_offline_replay_v1"
DIAGNOSTIC_SCHEMA = "strict18_return_handoff_owner_bounded_diagnostic_v1"
DIAGNOSTIC_ATTEMPT_ID = (
    "strict18_seed_1000_return_handoff_owner_isolated_gate8"
)
TARGET_COMPLETED_DUMPS = 8

_CONTACT_FIELD = "return_to_dig_start_envelope_require_contact"
_PLANE_MODE_FIELD = "return_to_dig_start_envelope_plane_depth_mode"
_CHECKS_FIELD = "return_to_dig_start_envelope_checks"
_TOKEN_FIELD = "return_start_envelope_tokens"
_QPOS_CHECKS = tuple(f"qpos_{axis}" for axis in range(4))


class ReturnHandoffOwnerDiagnosticError(RuntimeError):
    """Raised when the recorded owner audit cannot be trusted."""


def analyze_return_handoff_owner_replay(
    rows: Sequence[Mapping[str, Any]],
    *,
    gate_config: ReturnStartEnvelopeGateConfig,
    cycle_id: int,
) -> dict[str, Any]:
    """Replay one return segment under baseline and owner-isolated semantics."""

    indexed = {
        _integer(row.get("step_id"), "step_id"): row
        for row in rows
        if isinstance(row, Mapping)
    }
    selected = [
        row
        for row in rows
        if (
            isinstance(row, Mapping)
            and _integer(row.get("cycle_id"), "cycle_id") == int(cycle_id)
            and str(row.get("skill_name", "")) == "return"
            and isinstance(row.get(_CHECKS_FIELD), Mapping)
            and not bool(row.get("box_safety_neutral_acknowledged", False))
            and not bool(
                row.get(
                    "functional_terminal_neutral_acknowledged",
                    False,
                )
            )
        )
    ]
    if not selected:
        raise ReturnHandoffOwnerDiagnosticError(
            "recorded_return_gate_segment_missing"
        )
    selected.sort(key=lambda row: _integer(row.get("step_id"), "step_id"))

    baseline = _replay_variant(
        selected,
        indexed=indexed,
        gate_config=gate_config,
    )
    if not baseline["fidelity_exact"]:
        raise ReturnHandoffOwnerDiagnosticError(
            "source_gate_replay_fidelity_failed"
        )

    contact_only_config = replace(gate_config, require_contact=False)
    contact_only = _replay_variant(
        selected,
        indexed=indexed,
        gate_config=contact_only_config,
    )
    owner_isolated_config = replace(
        contact_only_config,
        plane_depth_mode="range",
    )
    owner_isolated = _replay_variant(
        selected,
        indexed=indexed,
        gate_config=owner_isolated_config,
    )

    qpos_violation_step = _first_qpos_violation_step(baseline["frames"])
    in_bound_step = _last_in_bound_step(
        baseline["frames"],
        qpos_violation_step=qpos_violation_step,
    )
    source_frame = _frame_at(baseline["frames"], in_bound_step)
    contact_frame = _frame_at(contact_only["frames"], in_bound_step)
    isolated_frame = _frame_at(owner_isolated["frames"], in_bound_step)
    source_plane = _check(source_frame, "plane_depth_m")
    contact_plane = _check(contact_frame, "plane_depth_m")
    contact_blockers = _blocking_checks(contact_frame)
    contact_depth_blockers = [
        name
        for name in contact_blockers
        if name in {"local_depth_m", "plane_depth_m"}
    ]
    contact_only_blocker = (
        contact_depth_blockers[0] if len(contact_depth_blockers) == 1 else ""
    )
    coupling = bool(
        source_plane.get("floor_source") == "p05_local_contact_prior"
        and contact_plane.get("floor_source") == "p50"
        and contact_only_blocker == "plane_depth_m"
    )
    depth_bounds_unchanged = _depth_bounds_equal(
        baseline["frames"],
        owner_isolated["frames"],
    )

    source_summary = _variant_summary(
        baseline,
        qpos_violation_step=qpos_violation_step,
    )
    contact_summary = _variant_summary(
        contact_only,
        qpos_violation_step=qpos_violation_step,
    )
    isolated_summary = _variant_summary(
        owner_isolated,
        qpos_violation_step=qpos_violation_step,
    )
    isolated_summary.update(
        {
            "contact_owner": "return_start_envelope_token[6]",
            "depth_owner": "runtime_prior_p05_p95",
            "depth_bounds_unchanged_from_source": depth_bounds_unchanged,
            "first_in_bound_owner_proof": {
                "step_id": in_bound_step,
                "source": _compact_frame(source_frame),
                "contact_only": _compact_frame(contact_frame),
                "owner_isolated": _compact_frame(isolated_frame),
            },
        }
    )
    bounded_allowed = bool(
        coupling
        and depth_bounds_unchanged
        and isolated_summary["ready_before_qpos_violation"]
    )
    return {
        "schema": OFFLINE_SCHEMA,
        "status": "passed" if bounded_allowed else "blocked",
        "cycle_id": int(cycle_id),
        "evaluated_step_count": len(selected),
        "source_replay": {
            **source_summary,
            "fidelity": "exact",
            "fidelity_checked_step_count": len(selected),
        },
        "contact_only": {
            **contact_summary,
            "config_delta": {_CONTACT_FIELD: False},
        },
        "depth_owner_audit": {
            "contact_to_plane_depth_coupling_observed": coupling,
            "contact_only_blocker": contact_only_blocker,
            "source_plane_floor_source": source_plane.get("floor_source", ""),
            "contact_only_plane_floor_source": contact_plane.get(
                "floor_source",
                "",
            ),
            "effective_depth_owner": "runtime_prior",
            "token_depth_simultaneously_applied": False,
        },
        "owner_isolated": {
            **isolated_summary,
            "config_delta": {
                _CONTACT_FIELD: False,
                _PLANE_MODE_FIELD: "range",
            },
        },
        "bounded_diagnostic_allowed": bounded_allowed,
        "bounded_diagnostic_blockers": (
            []
            if bounded_allowed
            else _owner_isolation_blockers(
                coupling=coupling,
                depth_bounds_unchanged=depth_bounds_unchanged,
                ready_before_qpos=bool(
                    isolated_summary["ready_before_qpos_violation"]
                ),
            )
        ),
    }


def build_return_handoff_owner_config(
    source: Mapping[str, Any],
    *,
    run_root: Path,
    min_completed_dump_count: int | None = None,
    target_completed_dumps: int = TARGET_COMPLETED_DUMPS,
    attempt_id: str = DIAGNOSTIC_ATTEMPT_ID,
    diagnostic_schema: str = DIAGNOSTIC_SCHEMA,
) -> dict[str, Any]:
    """Deep-copy v7 and isolate contact/depth ownership request-locally."""

    config = copy.deepcopy(dict(source))
    eval_config = _mapping_mut(config, "eval")
    policy = _mapping_mut(config, "policy")
    switch = _mapping_mut(policy, "switch")
    box = _mapping_mut(policy, "box_emptying")

    if switch.get(_CONTACT_FIELD) is not True:
        raise ReturnHandoffOwnerDiagnosticError(
            "source_global_contact_requirement_not_enabled"
        )
    if str(switch.get(_PLANE_MODE_FIELD, "")) != "p50_floor":
        raise ReturnHandoffOwnerDiagnosticError(
            "source_plane_depth_mode_not_p50_floor"
        )
    if switch.get("return_to_dig_start_envelope_gate_enabled") is not True:
        raise ReturnHandoffOwnerDiagnosticError(
            "source_return_envelope_gate_not_enabled"
        )
    if "return_approach_axis_limit" in box:
        raise ReturnHandoffOwnerDiagnosticError(
            "source_axis_limit_diagnostic_present"
        )
    if "return_start_envelope_owner_control" in box:
        raise ReturnHandoffOwnerDiagnosticError(
            "source_owner_control_already_present"
        )
    if (
        min_completed_dump_count is not None
        and int(min_completed_dump_count) < 0
    ):
        raise ReturnHandoffOwnerDiagnosticError(
            "min_completed_dump_count_invalid"
        )
    if (
        isinstance(target_completed_dumps, bool)
        or not isinstance(target_completed_dumps, int)
        or target_completed_dumps < 1
        or target_completed_dumps > 10
    ):
        raise ReturnHandoffOwnerDiagnosticError(
            "target_completed_dumps_invalid"
        )
    if (
        min_completed_dump_count is not None
        and target_completed_dumps <= int(min_completed_dump_count)
    ):
        raise ReturnHandoffOwnerDiagnosticError(
            "target_completed_dumps_does_not_exercise_owner_control"
        )

    eval_config.update(
        {
            "num_rollouts": 1,
            "seed": int(eval_config.get("seed", 1000)),
            "target_cycle_gate": int(target_completed_dumps),
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
        raise ReturnHandoffOwnerDiagnosticError(
            "record_hdf5_metadata_invalid"
        )
    metadata.update(
        {
            "validation_schema": str(diagnostic_schema),
            "return_handoff_owner_attempt_id": str(attempt_id),
            "return_handoff_contact_owner": (
                "return_start_envelope_token[6]"
            ),
            "return_handoff_depth_owner": "runtime_prior_p05_p95",
            "diagnostic_only": True,
            "promotion_eligible": False,
        }
    )
    if min_completed_dump_count is None:
        switch[_CONTACT_FIELD] = False
        switch[_PLANE_MODE_FIELD] = "range"
    else:
        box["return_start_envelope_owner_control"] = {
            "enabled": True,
            "diagnostic_only": True,
            "min_completed_dump_count": int(
                min_completed_dump_count
            ),
            "contact_owner": "token",
            "depth_owner": "runtime_prior_p05_p95",
        }
    return config


def validate_return_handoff_owner_config(
    *,
    source: Mapping[str, Any],
    candidate: Mapping[str, Any],
    run_root: Path,
    min_completed_dump_count: int | None = None,
    target_completed_dumps: int = TARGET_COMPLETED_DUMPS,
    attempt_id: str = DIAGNOSTIC_ATTEMPT_ID,
    diagnostic_schema: str = DIAGNOSTIC_SCHEMA,
) -> None:
    """Fail closed on any delta outside owner isolation and output routing."""

    expected = build_return_handoff_owner_config(
        source,
        run_root=run_root,
        min_completed_dump_count=min_completed_dump_count,
        target_completed_dumps=target_completed_dumps,
        attempt_id=attempt_id,
        diagnostic_schema=diagnostic_schema,
    )
    if dict(candidate) != expected:
        raise ReturnHandoffOwnerDiagnosticError(
            "request_local_config_drift"
        )


def gate_config_from_mapping(
    source: Mapping[str, Any],
) -> ReturnStartEnvelopeGateConfig:
    """Build the production gate service config from one resolved eval config."""

    policy = _mapping(source.get("policy"), "policy")
    switch = _mapping(policy.get("switch"), "policy.switch")
    try:
        return ReturnStartEnvelopeGateConfig(
            enabled=bool(
                switch["return_to_dig_start_envelope_gate_enabled"]
            ),
            action_dim=int(
                _mapping(policy.get("act_params"), "policy.act_params").get(
                    "action_dim",
                    4,
                )
            ),
            spatial_tolerance=float(
                switch[
                    "return_to_dig_start_envelope_spatial_tolerance"
                ]
            ),
            depth_tolerance_m=float(
                switch[
                    "return_to_dig_start_envelope_depth_tolerance_m"
                ]
            ),
            local_depth_tolerance_m=float(
                switch[
                    "return_to_dig_start_envelope_local_depth_tolerance_m"
                ]
            ),
            plane_depth_tolerance_m=float(
                switch[
                    "return_to_dig_start_envelope_plane_depth_tolerance_m"
                ]
            ),
            plane_depth_mode=str(switch[_PLANE_MODE_FIELD]),
            qpos_tolerance=float(
                switch[
                    "return_to_dig_start_envelope_qpos_tolerance"
                ]
            ),
            require_contact=bool(switch[_CONTACT_FIELD]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ReturnHandoffOwnerDiagnosticError(
            "source_gate_config_invalid"
        ) from exc


def _replay_variant(
    selected: Sequence[Mapping[str, Any]],
    *,
    indexed: Mapping[int, Mapping[str, Any]],
    gate_config: ReturnStartEnvelopeGateConfig,
) -> dict[str, Any]:
    service = ReturnStartEnvelopeGateService(gate_config)
    frames: list[dict[str, Any]] = []
    fidelity_exact = True
    for row in selected:
        step_id = _integer(row.get("step_id"), "step_id")
        previous = indexed.get(step_id - 1)
        if previous is None:
            raise ReturnHandoffOwnerDiagnosticError(
                f"pre_action_observation_missing:step={step_id}"
            )
        inputs = _recorded_gate_inputs(
            row=row,
            previous=previous,
            gate_config=gate_config,
        )
        result = service.evaluate(inputs)
        frame = _result_frame(step_id, result)
        frames.append(frame)
        if gate_config.require_contact and gate_config.plane_depth_mode == (
            "p50_floor"
        ):
            fidelity_exact = bool(
                fidelity_exact and _matches_recorded_result(row, result)
            )
    return {
        "frames": frames,
        "fidelity_exact": fidelity_exact,
    }


def _recorded_gate_inputs(
    *,
    row: Mapping[str, Any],
    previous: Mapping[str, Any],
    gate_config: ReturnStartEnvelopeGateConfig,
) -> ReturnStartEnvelopeGateInputs:
    token = np.asarray(row.get(_TOKEN_FIELD), dtype=np.float32).reshape(-1)
    if token.shape != (18,) or not bool(np.all(np.isfinite(token))):
        raise ReturnHandoffOwnerDiagnosticError(
            "recorded_return_envelope_token_invalid"
        )
    checks = _mapping(row.get(_CHECKS_FIELD), _CHECKS_FIELD)
    lower = token.copy()
    upper = token.copy()
    use_prior_spatial = _restore_bounds(
        lower=lower,
        upper=upper,
        checks=checks,
        fields=(("long_norm", 0), ("short_norm", 1)),
        tolerance=gate_config.spatial_tolerance,
        token=token,
    )
    use_prior_qpos = _restore_bounds(
        lower=lower,
        upper=upper,
        checks=checks,
        fields=tuple(
            (f"qpos_{axis}", 7 + axis) for axis in range(4)
        ),
        tolerance=gate_config.qpos_tolerance,
        token=token,
    )
    prior_mapping = {
        "dig_start_local_depth_m": _prior_percentiles(
            checks,
            "local_depth_m",
        ),
        "dig_start_plane_depth_m": _prior_percentiles(
            checks,
            "plane_depth_m",
        ),
    }
    return ReturnStartEnvelopeGateInputs(
        token=token,
        env_state=_finite_vector(previous.get("env_state"), "env_state"),
        qpos=_finite_vector(previous.get("qpos"), "qpos", size=4),
        qvel=_finite_vector(previous.get("qvel"), "qvel", size=4),
        prior_bounds=lambda: (lower, upper),
        prior_mapping=lambda: prior_mapping,
        use_prior_spatial_bounds=use_prior_spatial,
        use_prior_qpos_bounds=use_prior_qpos,
        use_prior_depth_bounds=True,
    )


def _restore_bounds(
    *,
    lower: np.ndarray,
    upper: np.ndarray,
    checks: Mapping[str, Any],
    fields: Sequence[tuple[str, int]],
    tolerance: float,
    token: np.ndarray,
) -> bool:
    prior_used = False
    for name, index in fields:
        check = _check_mapping(checks, name)
        low = _finite(check.get("min"), f"{name}.min")
        high = _finite(check.get("max"), f"{name}.max")
        lower[index] = low + float(tolerance)
        upper[index] = high - float(tolerance)
        token_low = float(token[index]) - float(tolerance)
        token_high = float(token[index]) + float(tolerance)
        prior_used = bool(
            prior_used
            or not math.isclose(low, token_low, abs_tol=1e-6)
            or not math.isclose(high, token_high, abs_tol=1e-6)
        )
    return prior_used


def _prior_percentiles(
    checks: Mapping[str, Any],
    name: str,
) -> dict[str, float]:
    check = _check_mapping(checks, name)
    try:
        return {
            key: _finite(check[key], f"{name}.{key}")
            for key in ("p05", "p50", "p95")
        }
    except KeyError as exc:
        raise ReturnHandoffOwnerDiagnosticError(
            f"{name}_prior_lineage_missing"
        ) from exc


def _matches_recorded_result(
    row: Mapping[str, Any],
    result: ReturnStartEnvelopeGateResult,
) -> bool:
    if bool(row.get("return_to_dig_start_envelope_ready")) != result.ready:
        return False
    recorded_error = _finite(
        row.get("return_to_dig_start_envelope_error"),
        "recorded_envelope_error",
    )
    if not math.isclose(recorded_error, result.error, abs_tol=1e-6):
        return False
    recorded_checks = _mapping(row.get(_CHECKS_FIELD), _CHECKS_FIELD)
    if set(recorded_checks) != set(result.checks):
        return False
    return all(
        _mapping_close(recorded_checks[name], result.checks[name])
        for name in recorded_checks
    )


def _mapping_close(left: Any, right: Any) -> bool:
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        if set(left) != set(right):
            return False
        return all(_mapping_close(left[key], right[key]) for key in left)
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return math.isclose(float(left), float(right), abs_tol=1e-6)
    return left == right


def _result_frame(
    step_id: int,
    result: ReturnStartEnvelopeGateResult,
) -> dict[str, Any]:
    return {
        "step_id": int(step_id),
        "ready": bool(result.ready),
        "error": float(result.error),
        "checks": copy.deepcopy(result.checks),
    }


def _variant_summary(
    replay: Mapping[str, Any],
    *,
    qpos_violation_step: int | None,
) -> dict[str, Any]:
    frames = replay["frames"]
    ready_steps = [
        int(frame["step_id"]) for frame in frames if bool(frame["ready"])
    ]
    first_ready = ready_steps[0] if ready_steps else None
    return {
        "first_ready_step": first_ready,
        "ready_step_count": len(ready_steps),
        "first_qpos_violation_step": qpos_violation_step,
        "ready_before_qpos_violation": bool(
            first_ready is not None
            and (
                qpos_violation_step is None
                or int(first_ready) < int(qpos_violation_step)
            )
        ),
    }


def _first_qpos_violation_step(
    frames: Sequence[Mapping[str, Any]],
) -> int | None:
    for frame in frames:
        checks = _mapping(frame.get("checks"), "frame.checks")
        qpos_1 = _check_mapping(checks, "qpos_1")
        if qpos_1.get("ok") is False:
            return _integer(frame.get("step_id"), "frame.step_id")
    return None


def _last_in_bound_step(
    frames: Sequence[Mapping[str, Any]],
    *,
    qpos_violation_step: int | None,
) -> int:
    candidates = [
        _integer(frame.get("step_id"), "frame.step_id")
        for frame in frames
        if (
            qpos_violation_step is None
            or _integer(frame.get("step_id"), "frame.step_id")
            < qpos_violation_step
        )
    ]
    if not candidates:
        raise ReturnHandoffOwnerDiagnosticError(
            "no_pre_qpos_violation_frame"
        )
    return max(candidates)


def _frame_at(
    frames: Sequence[Mapping[str, Any]],
    step_id: int,
) -> Mapping[str, Any]:
    for frame in frames:
        if _integer(frame.get("step_id"), "frame.step_id") == step_id:
            return frame
    raise ReturnHandoffOwnerDiagnosticError(
        f"gate_frame_missing:step={step_id}"
    )


def _check(frame: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    return _check_mapping(
        _mapping(frame.get("checks"), "frame.checks"),
        name,
    )


def _blocking_checks(frame: Mapping[str, Any]) -> list[str]:
    checks = _mapping(frame.get("checks"), "frame.checks")
    return [
        str(name)
        for name, value in checks.items()
        if isinstance(value, Mapping)
        and "ok" in value
        and value.get("ok") is False
    ]


def _depth_bounds_equal(
    baseline: Sequence[Mapping[str, Any]],
    isolated: Sequence[Mapping[str, Any]],
) -> bool:
    if len(baseline) != len(isolated):
        return False
    for source, candidate in zip(baseline, isolated, strict=True):
        for name in ("local_depth_m", "plane_depth_m"):
            left = _check(source, name)
            right = _check(candidate, name)
            for field in ("min", "max"):
                if not math.isclose(
                    _finite(left.get(field), f"{name}.{field}"),
                    _finite(right.get(field), f"{name}.{field}"),
                    abs_tol=1e-6,
                ):
                    return False
    return True


def _compact_frame(frame: Mapping[str, Any]) -> dict[str, Any]:
    checks = _mapping(frame.get("checks"), "frame.checks")
    return {
        "ready": bool(frame.get("ready")),
        "error": _finite(frame.get("error"), "frame.error"),
        "blockers": _blocking_checks(frame),
        "local_depth_m": dict(_check_mapping(checks, "local_depth_m")),
        "plane_depth_m": dict(_check_mapping(checks, "plane_depth_m")),
        "qpos_1": dict(_check_mapping(checks, "qpos_1")),
        "dig_contact": (
            dict(_check_mapping(checks, "dig_contact"))
            if "dig_contact" in checks
            else {
                "omitted": True,
                "owner": "return_start_envelope_token[6]",
            }
        ),
    }


def _owner_isolation_blockers(
    *,
    coupling: bool,
    depth_bounds_unchanged: bool,
    ready_before_qpos: bool,
) -> list[str]:
    blockers = []
    if not coupling:
        blockers.append("contact_depth_coupling_not_proven")
    if not depth_bounds_unchanged:
        blockers.append("depth_bounds_changed")
    if not ready_before_qpos:
        blockers.append("handoff_not_ready_before_qpos_violation")
    return blockers


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ReturnHandoffOwnerDiagnosticError(f"{label}_must_be_mapping")
    return value


def _mapping_mut(value: dict[str, Any], key: str) -> dict[str, Any]:
    item = value.get(key)
    if not isinstance(item, dict):
        raise ReturnHandoffOwnerDiagnosticError(
            f"{key}_must_be_mutable_mapping"
        )
    return item


def _check_mapping(
    checks: Mapping[str, Any],
    name: str,
) -> Mapping[str, Any]:
    value = checks.get(name)
    if not isinstance(value, Mapping):
        raise ReturnHandoffOwnerDiagnosticError(
            f"recorded_check_missing:{name}"
        )
    return value


def _finite_vector(
    value: Any,
    label: str,
    *,
    size: int | None = None,
) -> np.ndarray:
    vector = np.asarray(value, dtype=np.float32).reshape(-1)
    if (
        (size is not None and vector.shape != (size,))
        or not bool(np.all(np.isfinite(vector)))
    ):
        raise ReturnHandoffOwnerDiagnosticError(f"{label}_invalid")
    return vector


def _finite(value: Any, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ReturnHandoffOwnerDiagnosticError(
            f"{label}_not_numeric"
        ) from exc
    if not math.isfinite(number):
        raise ReturnHandoffOwnerDiagnosticError(f"{label}_nonfinite")
    return number


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ReturnHandoffOwnerDiagnosticError(f"{label}_not_integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ReturnHandoffOwnerDiagnosticError(
            f"{label}_not_integer"
        ) from exc
    return number


__all__ = [
    "DIAGNOSTIC_ATTEMPT_ID",
    "DIAGNOSTIC_SCHEMA",
    "OFFLINE_SCHEMA",
    "ReturnHandoffOwnerDiagnosticError",
    "TARGET_COMPLETED_DUMPS",
    "analyze_return_handoff_owner_replay",
    "build_return_handoff_owner_config",
    "gate_config_from_mapping",
    "validate_return_handoff_owner_config",
]
