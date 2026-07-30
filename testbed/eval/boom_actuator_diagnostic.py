"""No-ACT Unity boom command-response diagnostics.

The collector disables terrain physics, starts each pulse from a reproducible
pose prepared only through the production actuator interface, and rejects any
external-shape, wall, or factory-floor contact.  It does not change controller
settings, safety thresholds, planner behavior, or model inputs.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from testbed.backends.agx.protocol import (
    ACTION_ORDER_V2,
    PROTOCOL_VERSION,
    QPOS_ORDER_V2,
    QVEL_ORDER_V2,
    AgxSimClient,
)
from testbed.data.schema import (
    ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_TYPED_MASK_IDX,
)
from testbed.eval.return_boom_diagnostic_contract import (
    ACTUATOR_AUDIT_SCHEMA,
    BOOM_AXIS,
    DIAGNOSTIC_SCHEMA,
)

PREPARED_QPOS_TOLERANCE = 0.005
PREPARED_QVEL_TOLERANCE = 0.01
BUCKET_CONTACT_COUNT_PREFIX = "bucket_contact_diagnostic:contact_count="
COMMAND_TO_QPOS_SIGN = np.asarray((1.0, -1.0, 1.0, 1.0), dtype=np.float64)


def analyze_actuator_trials(
    trials: Sequence[Mapping[str, Any]],
    *,
    expected_positive_command_qpos_sign: int,
    maximum_gain_ratio: float,
) -> dict[str, Any]:
    """Validate paired boom pulses and summarize direction/local gain."""

    expected_sign = int(expected_positive_command_qpos_sign)
    if expected_sign not in (-1, 1):
        raise ValueError("expected positive-command qpos sign must be -1 or +1")
    gain_limit = float(maximum_gain_ratio)
    if not math.isfinite(gain_limit) or gain_limit < 1.0:
        raise ValueError("maximum gain ratio must be finite and at least 1")
    if not trials:
        raise ValueError("at least one actuator trial is required")

    normalized: list[dict[str, Any]] = []
    violations: list[str] = []
    for index, raw in enumerate(trials):
        pose_id = str(raw.get("pose_id", "")).strip()
        command = _finite_float(raw.get("command"), label="command")
        duration = _finite_float(raw.get("duration_s"), label="duration_s")
        start = _finite_float(raw.get("qpos_1_start"), label="qpos_1_start")
        end = _finite_float(raw.get("qpos_1_end"), label="qpos_1_end")
        finite = bool(raw.get("finite", False))
        contact_free = bool(raw.get("contact_free", False))
        realign_within = bool(raw.get("realign_within_0p005", True))
        target_within = bool(raw.get("pose_target_within_0p005", True))
        if not pose_id:
            raise ValueError(f"trial {index} is missing pose_id")
        if abs(command) <= 1.0e-9 or duration <= 0.0:
            raise ValueError(f"trial {index} command/duration is invalid")
        start_qpos = _optional_vector(
            raw.get("start_qpos"),
            width=4,
            label=f"trial {index} start_qpos",
        )
        start_qvel = _optional_vector(
            raw.get("start_qvel"),
            width=4,
            label=f"trial {index} start_qvel",
        )
        delta = end - start
        sign = _sign(delta)
        gain = abs(delta) / (abs(command) * duration)
        normalized.append(
            {
                **dict(raw),
                "pose_id": pose_id,
                "command": command,
                "duration_s": duration,
                "qpos_1_start": start,
                "qpos_1_end": end,
                "qpos_1_delta": delta,
                "qpos_response_sign": sign,
                "normalized_qpos_gain_per_s": gain,
                "finite": finite,
                "contact_free": contact_free,
                "start_qpos": (
                    start_qpos.tolist() if start_qpos is not None else None
                ),
                "start_qvel": (
                    start_qvel.tolist() if start_qvel is not None else None
                ),
            }
        )
        if not finite:
            violations.append("nonfinite_measurement")
        if not contact_free:
            violations.append("contact_observed")
        if not realign_within:
            violations.append("realign_pose_drift")
        if not target_within:
            violations.append("prepared_pose_target_drift")
        if (
            start_qvel is not None
            and float(np.max(np.abs(start_qvel))) > PREPARED_QVEL_TOLERANCE
        ):
            violations.append(f"prepared_pose_not_settled:{pose_id}")
        expected_trial_sign = expected_sign if command > 0.0 else -expected_sign
        if sign != expected_trial_sign:
            violations.append(
                "positive_command_direction_mismatch"
                if command > 0.0
                else "negative_command_direction_mismatch"
            )

    by_pose: dict[str, dict[int, dict[str, Any]]] = {}
    for item in normalized:
        command_sign = 1 if float(item["command"]) > 0.0 else -1
        slot = by_pose.setdefault(str(item["pose_id"]), {})
        if command_sign in slot:
            raise ValueError(
                f"pose {item['pose_id']!r} repeats command sign {command_sign}"
            )
        slot[command_sign] = item
    for pose_id, pair in by_pose.items():
        if set(pair) != {-1, 1}:
            violations.append(f"unpaired_pose:{pose_id}")

    gains = [
        float(item["normalized_qpos_gain_per_s"])
        for item in normalized
        if float(item["normalized_qpos_gain_per_s"]) > 1.0e-12
    ]
    if gains:
        cross_pose_gain_ratio = max(gains) / min(gains)
    else:
        cross_pose_gain_ratio = math.inf
        violations.append("zero_response_gain")
    if cross_pose_gain_ratio > gain_limit:
        violations.append("pose_dependent_gain_amplification")

    pose_summaries: list[dict[str, Any]] = []
    for pose_id, pair in sorted(by_pose.items()):
        pair_gains = [
            float(item["normalized_qpos_gain_per_s"])
            for item in pair.values()
            if float(item["normalized_qpos_gain_per_s"]) > 1.0e-12
        ]
        symmetry_ratio = (
            max(pair_gains) / min(pair_gains)
            if len(pair_gains) == 2
            else math.inf
        )
        if symmetry_ratio > gain_limit:
            violations.append(f"command_sign_gain_asymmetry:{pose_id}")

        start_qpos_delta = _paired_vector_delta(pair, "start_qpos")
        start_qvel_delta = _paired_vector_delta(pair, "start_qvel")
        if (
            start_qpos_delta is not None
            and start_qpos_delta > PREPARED_QPOS_TOLERANCE
        ):
            violations.append(f"prepared_pose_mismatch:{pose_id}")
        if (
            start_qvel_delta is not None
            and start_qvel_delta > PREPARED_QVEL_TOLERANCE
        ):
            violations.append(f"prepared_velocity_mismatch:{pose_id}")

        pose_summaries.append(
            {
                "pose_id": pose_id,
                "paired": set(pair) == {-1, 1},
                "paired_start_qpos_max_abs_delta": start_qpos_delta,
                "paired_start_qvel_max_abs_delta": start_qvel_delta,
                "gain_symmetry_ratio": symmetry_ratio,
                "positive": pair.get(1),
                "negative": pair.get(-1),
            }
        )

    unique_violations = sorted(set(violations))
    status = "passed" if not unique_violations else "failed"
    return {
        "status": status,
        "classification": (
            "normal" if status == "passed" else "direction_or_gain_anomaly"
        ),
        "expected_positive_command_qpos_sign": expected_sign,
        "positive_command_qpos_sign": _consensus_sign(
            item["qpos_response_sign"]
            for item in normalized
            if float(item["command"]) > 0.0
        ),
        "negative_command_qpos_sign": _consensus_sign(
            item["qpos_response_sign"]
            for item in normalized
            if float(item["command"]) < 0.0
        ),
        "cross_pose_gain_ratio": cross_pose_gain_ratio,
        "maximum_gain_ratio": gain_limit,
        "prepared_qpos_tolerance": PREPARED_QPOS_TOLERANCE,
        "prepared_qvel_tolerance": PREPARED_QVEL_TOLERANCE,
        "violations": unique_violations,
        "pose_summaries": pose_summaries,
        "trials": normalized,
    }


def collect_unity_boom_actuator_response(
    *,
    host: str,
    port: int,
    poses: Sequence[Mapping[str, Any]],
    output_path: str | Path,
    command_amplitude: float = 0.10,
    pulse_steps: int = 20,
    settle_steps: int = 30,
    neutral_steps: int = 30,
    pose_prepare_action_limit: float = 0.20,
    pose_prepare_gain: float = 2.0,
    pose_prepare_max_steps: int = 900,
    pose_prepare_tolerance: float = 0.003,
    timeout_s: float = 10.0,
    expected_positive_command_qpos_sign: int = -1,
    maximum_gain_ratio: float = 2.0,
) -> Path:
    """Collect paired small boom pulses from action-prepared fixed poses."""

    amplitude = abs(_finite_float(command_amplitude, label="command amplitude"))
    prepare_limit = abs(
        _finite_float(
            pose_prepare_action_limit,
            label="pose prepare action limit",
        )
    )
    prepare_gain = _finite_float(
        pose_prepare_gain,
        label="pose prepare gain",
    )
    prepare_tolerance = _finite_float(
        pose_prepare_tolerance,
        label="pose prepare tolerance",
    )
    if not 0.0 < amplitude <= 1.0:
        raise ValueError("command amplitude must be in (0, 1]")
    if not 0.0 < prepare_limit <= 1.0:
        raise ValueError("pose prepare action limit must be in (0, 1]")
    if prepare_gain <= 0.0:
        raise ValueError("pose prepare gain must be positive")
    if not 0.0 < prepare_tolerance <= PREPARED_QPOS_TOLERANCE:
        raise ValueError("pose prepare tolerance must be in (0, 0.005]")
    for value, label in (
        (pulse_steps, "pulse_steps"),
        (settle_steps, "settle_steps"),
        (neutral_steps, "neutral_steps"),
        (pose_prepare_max_steps, "pose_prepare_max_steps"),
    ):
        if int(value) < 1:
            raise ValueError(f"{label} must be positive")
    normalized_poses = _validated_prepared_poses(poses)

    trials: list[dict[str, Any]] = []
    step_id = 0
    info_payload: dict[str, Any]
    with AgxSimClient(
        host=str(host),
        port=int(port),
        timeout_s=float(timeout_s),
    ) as client:
        info = client.get_info()
        _validate_unity_info(info)
        for pose in normalized_poses:
            for command_sign in (1, -1):
                reset = client.reset(
                    seed=0,
                    reset_terrain=True,
                    reset_pose=True,
                    diagnostic_terrain_mode="terrain_disabled",
                    control_compatibility_profile="production",
                )
                _validate_reset_warnings(reset.warnings)
                trial, step_id = _collect_one_prepared_trial(
                    client=client,
                    step_id=step_id,
                    pose=pose,
                    command=float(command_sign) * amplitude,
                    dt=float(info.dt),
                    pulse_steps=int(pulse_steps),
                    settle_steps=int(settle_steps),
                    neutral_steps=int(neutral_steps),
                    pose_prepare_action_limit=prepare_limit,
                    pose_prepare_gain=prepare_gain,
                    pose_prepare_max_steps=int(pose_prepare_max_steps),
                    pose_prepare_tolerance=prepare_tolerance,
                    reset_warnings=reset.warnings,
                )
                trials.append(trial)

        terminal = client.step(
            step_id=step_id,
            action=np.zeros(4, dtype=np.float32),
        )
        terminal_neutral = {
            "step_id": int(terminal.step_id),
            "action": [0.0, 0.0, 0.0, 0.0],
            "qpos": terminal.qpos.tolist(),
            "qvel": terminal.qvel.tolist(),
            "finite": bool(
                np.isfinite(terminal.qpos).all()
                and np.isfinite(terminal.qvel).all()
            ),
        }
        info_payload = {
            "host": str(host),
            "port": int(port),
            "protocol_version": info.protocol_version,
            "runtime_build_id": info.runtime_build_id,
            "dt": float(info.dt),
            "control_hz": float(info.control_hz),
            "action_order": list(info.action_order),
            "qpos_order": list(info.qpos_order),
            "qvel_order": list(info.qvel_order),
            "env_state_contract_version": info.env_state_contract_version,
        }

    analysis = analyze_actuator_trials(
        trials,
        expected_positive_command_qpos_sign=(
            expected_positive_command_qpos_sign
        ),
        maximum_gain_ratio=maximum_gain_ratio,
    )
    artifact = {
        "schema": ACTUATOR_AUDIT_SCHEMA,
        "diagnostic_schema": DIAGNOSTIC_SCHEMA,
        "status": analysis["status"],
        "classification": analysis["classification"],
        "diagnostic_only": True,
        "non_promotable": True,
        "act_inference_executed": False,
        "realign_pose_used": False,
        "pose_preparation": (
            "reset_then_closed_loop_small_action_pose_servo_then_neutral_settle"
        ),
        "terrain_mode": "terrain_disabled",
        "terrain_physics_disabled": True,
        "dig_area_geometric_mask_is_not_contact_evidence": True,
        "external_shape_contact_required_absent": True,
        "wall_and_factory_floor_contact_required_absent": True,
        "production_control_profile": True,
        "production_thresholds_changed": False,
        "fixed_poses": normalized_poses,
        "command_amplitude": amplitude,
        "pulse_steps": int(pulse_steps),
        "settle_steps": int(settle_steps),
        "neutral_steps": int(neutral_steps),
        "pose_prepare_action_limit": prepare_limit,
        "pose_prepare_gain": prepare_gain,
        "pose_prepare_max_steps": int(pose_prepare_max_steps),
        "pose_prepare_tolerance": prepare_tolerance,
        "command_to_qpos_sign": COMMAND_TO_QPOS_SIGN.tolist(),
        "analysis": analysis,
        "terminal_neutral": terminal_neutral,
        "unity": info_payload,
    }
    return _write_json_exclusive(output_path, artifact)


def _validated_prepared_poses(
    poses: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if not poses:
        raise ValueError("at least one fixed pose is required")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in poses:
        pose_id = str(raw.get("pose_id", "")).strip()
        if not pose_id or pose_id in seen:
            raise ValueError("fixed pose IDs must be non-empty and unique")
        target_qpos = _finite_vector(
            raw.get("qpos"),
            width=4,
            label=f"fixed pose {pose_id!r} qpos",
        )
        if np.any(target_qpos < 0.0) or np.any(target_qpos > 1.0):
            raise ValueError(f"fixed pose {pose_id!r} qpos is outside [0,1]")
        seen.add(pose_id)
        result.append(
            {
                "pose_id": pose_id,
                "qpos": target_qpos.tolist(),
            }
        )
    return result


def _validate_unity_info(info: Any) -> None:
    if info.protocol_version != PROTOCOL_VERSION:
        raise ValueError(
            f"Unity protocol must be {PROTOCOL_VERSION}, got {info.protocol_version}"
        )
    if tuple(info.action_order) != ACTION_ORDER_V2:
        raise ValueError("Unity action order mismatch")
    if tuple(info.qpos_order) != QPOS_ORDER_V2:
        raise ValueError("Unity qpos order mismatch")
    if tuple(info.qvel_order) != QVEL_ORDER_V2:
        raise ValueError("Unity qvel order mismatch")


def _validate_reset_warnings(warnings: Sequence[str]) -> None:
    if "diagnostic_terrain_mode:terrain_disabled" not in warnings:
        raise ValueError(
            "Unity did not acknowledge terrain_disabled diagnostic mode"
        )
    if "replay_control_compatibility_profile:production" not in warnings:
        raise ValueError(
            "Unity did not acknowledge production control profile"
        )


def _collect_one_prepared_trial(
    *,
    client: AgxSimClient,
    step_id: int,
    pose: Mapping[str, Any],
    command: float,
    dt: float,
    pulse_steps: int,
    settle_steps: int,
    neutral_steps: int,
    pose_prepare_action_limit: float,
    pose_prepare_gain: float,
    pose_prepare_max_steps: int,
    pose_prepare_tolerance: float,
    reset_warnings: Sequence[str],
) -> tuple[dict[str, Any], int]:
    responses: list[Any] = []
    target_qpos = _finite_vector(
        pose.get("qpos"),
        width=4,
        label=f"fixed pose {pose['pose_id']!r} qpos",
    )
    response = client.step(
        step_id=step_id,
        action=np.zeros(4, dtype=np.float32),
    )
    responses.append(response)
    step_id += 1

    preparation_step_count = 0
    for preparation_step_count in range(1, pose_prepare_max_steps + 1):
        error = target_qpos - np.asarray(response.qpos, dtype=np.float64)
        if float(np.max(np.abs(error))) <= pose_prepare_tolerance:
            preparation_step_count -= 1
            break
        preparation_action = np.clip(
            pose_prepare_gain * error / COMMAND_TO_QPOS_SIGN,
            -pose_prepare_action_limit,
            pose_prepare_action_limit,
        )
        preparation_action[
            np.abs(error) < min(0.001, pose_prepare_tolerance / 2.0)
        ] = 0.0
        response = client.step(
            step_id=step_id,
            action=preparation_action.astype(np.float32),
        )
        responses.append(response)
        step_id += 1
        if not _unity_contact_snapshot(response)["contact_free"]:
            raise ValueError(
                f"physical contact while preparing pose {pose['pose_id']!r}"
            )
    else:
        raise ValueError(
            f"pose preparation did not converge for {pose['pose_id']!r}"
        )

    for _ in range(settle_steps):
        response = client.step(
            step_id=step_id,
            action=np.zeros(4, dtype=np.float32),
        )
        responses.append(response)
        step_id += 1
    baseline = responses[-1]
    pose_target_error = float(
        np.max(
            np.abs(
                np.asarray(baseline.qpos, dtype=np.float64) - target_qpos
            )
        )
    )

    pulse_action = np.zeros(4, dtype=np.float32)
    pulse_action[BOOM_AXIS] = np.float32(command)
    pulse_responses: list[Any] = []
    for _ in range(pulse_steps):
        response = client.step(step_id=step_id, action=pulse_action)
        pulse_responses.append(response)
        responses.append(response)
        step_id += 1
    pulse_end = pulse_responses[-1]

    for _ in range(neutral_steps):
        response = client.step(
            step_id=step_id,
            action=np.zeros(4, dtype=np.float32),
        )
        responses.append(response)
        step_id += 1

    contact = [_unity_contact_snapshot(item) for item in responses]
    finite = all(
        np.isfinite(item.qpos).all()
        and np.isfinite(item.qvel).all()
        and np.isfinite(item.env_state).all()
        for item in responses
    )
    contact_free = all(
        not item["external_shape_contact"]
        and not item["wall_contact"]
        and not item["factory_floor_contact"]
        for item in contact
    )
    qvel_trace = np.asarray(
        [float(item.qvel[BOOM_AXIS]) for item in pulse_responses],
        dtype=np.float64,
    )
    tail_width = min(5, qvel_trace.size)
    return (
        {
            "pose_id": str(pose["pose_id"]),
            "target_qpos": target_qpos.tolist(),
            "preparation_step_count": int(preparation_step_count),
            "pose_target_max_abs_error": pose_target_error,
            "pose_target_within_0p005": (
                pose_target_error <= PREPARED_QPOS_TOLERANCE
            ),
            "command": float(command),
            "duration_s": float(pulse_steps * dt),
            "start_qpos": baseline.qpos.tolist(),
            "start_qvel": baseline.qvel.tolist(),
            "qpos_1_start": float(baseline.qpos[BOOM_AXIS]),
            "qpos_1_end": float(pulse_end.qpos[BOOM_AXIS]),
            "qpos_1_trace": [
                float(item.qpos[BOOM_AXIS]) for item in pulse_responses
            ],
            "qvel_1_trace": qvel_trace.tolist(),
            "qvel_1_peak_abs": float(np.max(np.abs(qvel_trace))),
            "qvel_1_tail_mean_abs": float(
                np.mean(np.abs(qvel_trace[-tail_width:]))
            ),
            "finite": finite,
            "contact_free": contact_free,
            "external_shape_contact_tick_count": sum(
                bool(item["external_shape_contact"]) for item in contact
            ),
            "wall_contact_tick_count": sum(
                bool(item["wall_contact"]) for item in contact
            ),
            "factory_floor_contact_tick_count": sum(
                bool(item["factory_floor_contact"]) for item in contact
            ),
            "dig_area_geometric_mask_tick_count": sum(
                bool(item["dig_area_geometric_mask"]) for item in contact
            ),
            "reset_warnings": list(reset_warnings),
            "warning_count": sum(len(item.warnings) for item in responses),
        },
        step_id,
    )


def _unity_contact_snapshot(response: Any) -> dict[str, bool]:
    env = np.asarray(response.env_state, dtype=np.float64).reshape(-1)
    required_width = max(
        ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
        ENV_STATE_EXCAVATOR_WALL_CONTACT_TYPED_MASK_IDX,
        ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX,
    ) + 1
    if env.size < required_width or not np.isfinite(env).all():
        raise ValueError("Unity contact diagnostic requires finite 107D state")
    external_shape_contact = any(
        str(warning).startswith(BUCKET_CONTACT_COUNT_PREFIX)
        for warning in response.warnings
    )
    snapshot = {
        "external_shape_contact": external_shape_contact,
        "dig_area_geometric_mask": bool(
            env[ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX] > 0.5
        ),
        "wall_contact": bool(
            env[ENV_STATE_EXCAVATOR_WALL_CONTACT_TYPED_MASK_IDX] > 0.5
        ),
        "factory_floor_contact": bool(
            env[ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX] > 0.5
        ),
    }
    snapshot["contact_free"] = not (
        snapshot["external_shape_contact"]
        or snapshot["wall_contact"]
        or snapshot["factory_floor_contact"]
    )
    return snapshot


def _paired_vector_delta(
    pair: Mapping[int, Mapping[str, Any]],
    key: str,
) -> float | None:
    if set(pair) != {-1, 1}:
        return None
    positive = pair[1].get(key)
    negative = pair[-1].get(key)
    if positive is None or negative is None:
        return None
    first = _finite_vector(positive, width=4, label=f"positive {key}")
    second = _finite_vector(negative, width=4, label=f"negative {key}")
    return float(np.max(np.abs(first - second)))


def _optional_vector(
    value: Any,
    *,
    width: int,
    label: str,
) -> np.ndarray | None:
    if value is None:
        return None
    return _finite_vector(value, width=width, label=label)


def _finite_vector(value: Any, *, width: int, label: str) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64).reshape(-1)
    if array.shape != (width,) or not np.isfinite(array).all():
        raise ValueError(f"{label} must contain {width} finite values")
    return array


def _finite_float(value: Any, *, label: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _sign(value: float, *, epsilon: float = 1.0e-9) -> int:
    if value > epsilon:
        return 1
    if value < -epsilon:
        return -1
    return 0


def _consensus_sign(values: Sequence[Any] | Any) -> int:
    signs = {_sign(float(value)) for value in values}
    signs.discard(0)
    if len(signs) == 1:
        return signs.pop()
    return 0


def _write_json_exclusive(
    path_value: str | Path,
    payload: Mapping[str, Any],
) -> Path:
    path = Path(path_value).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with path.open("x", encoding="utf-8") as handle:
        handle.write(body)
    return path
