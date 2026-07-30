"""Pure contracts for continuous goal-conditioned recovery evidence."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import struct
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from testbed.planner.primitive.coverage.continuous_worktool_sweep import (
    CONTINUOUS_ACT_TRACKING_MARGIN_M as ACT_TRACKING_MARGIN_M,
)
from testbed.planner.primitive.coverage.continuous_worktool_sweep import (
    CONTINUOUS_HARD_CLEARANCE_M as HARD_CLEARANCE_M,
)
from testbed.planner.primitive.coverage.continuous_worktool_sweep import (
    CONTINUOUS_POSE_INTERPOLATION_BOUND_M as POSE_INTERPOLATION_BOUND_M,
)
from testbed.planner.primitive.coverage.continuous_worktool_sweep import (
    CONTINUOUS_QPOS_ORDER,
)
from testbed.planner.primitive.coverage.continuous_worktool_sweep import (
    CONTINUOUS_QPOS_PATH_START_TOLERANCE as PATH_START_TOLERANCE,
)

GEOMETRY_TOLERANCE = 1.0e-9
CAMERA_ORDER = ("stick_up", "stick_down", "eye_left", "eye_right")
PRIMITIVES = ("dig", "carry", "dump", "return")
WORKTOOL_MEASUREMENT_SCHEMA = (
    "continuous_goal_worktool_sweep_measurement_v1"
)
RESET_FAIRNESS_LIMITS = {
    "qpos_max_abs_delta": 0.005,
    "qvel_abs_max": 0.10,
    "qvel_cross_condition_max_abs_delta": 0.02,
    "bucket_tip_displacement_m": 0.02,
    "terrain_depth_max_abs_delta_m": 0.002,
    "remaining_mass_abs_delta_kg": 5.0,
}
_HEX_DIGITS = frozenset("0123456789abcdef")
_WITNESS_KEYS = frozenset(
    (link, wall)
    for link in ("boom", "stick", "bucket")
    for wall in ("x_min", "x_max", "z_min", "z_max")
)


class ExperimentContractError(RuntimeError):
    """Raised when experiment evidence violates the frozen contract."""


def canonical_goal_id(goal: Mapping[str, Any]) -> str:
    """Return the canonical SHA-256 for a complete cut goal."""

    payload = dict(goal)
    payload.pop("goal_id", None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def validate_goal(value: Any, *, label: str) -> Mapping[str, Any]:
    goal = mapping(value, label)
    if goal.get("schema") != "continuous_cut_goal_v1":
        raise ExperimentContractError(f"{label}:schema_invalid")
    entry = finite_vector(goal.get("entry_xz_m"), 2, f"{label}.entry_xz_m")
    exit_ = finite_vector(goal.get("exit_xz_m"), 2, f"{label}.exit_xz_m")
    delta = (exit_[0] - entry[0], exit_[1] - entry[1])
    expected_length = math.hypot(*delta)
    if expected_length <= GEOMETRY_TOLERANCE:
        raise ExperimentContractError(f"{label}:degenerate_cut")
    direction = finite_vector(
        goal.get("direction_xz"),
        2,
        f"{label}.direction_xz",
    )
    expected_direction = (
        delta[0] / expected_length,
        delta[1] / expected_length,
    )
    if max(
        abs(direction[index] - expected_direction[index])
        for index in range(2)
    ) > GEOMETRY_TOLERANCE:
        raise ExperimentContractError(f"{label}:direction_inconsistent")
    length = finite_float(goal.get("cut_length_m"), f"{label}.cut_length_m")
    if abs(length - expected_length) > GEOMETRY_TOLERANCE:
        raise ExperimentContractError(f"{label}:length_inconsistent")
    if finite_float(
        goal.get("planned_depth_m"),
        f"{label}.planned_depth_m",
    ) <= 0.0:
        raise ExperimentContractError(f"{label}:planned_depth_invalid")
    integer(goal.get("target_cell_id"), default=None)
    mapping(goal.get("effect_intent"), f"{label}.effect_intent")
    mapping(goal.get("terrain_signature"), f"{label}.terrain_signature")
    finite_float(
        goal.get("payload_intent_kg"),
        f"{label}.payload_intent_kg",
    )
    goal_id = str(goal.get("goal_id", ""))
    if not is_sha256(goal_id) or goal_id != canonical_goal_id(goal):
        raise ExperimentContractError(f"{label}:goal_id_invalid")
    return goal


def validate_return_envelope(
    value: Any,
    *,
    goal_id: str,
    predictor_evidence: Mapping[str, Any] | None = None,
) -> None:
    envelope = mapping(value, "derived_return_envelope")
    if envelope.get("schema") != "cut_goal_return_envelope_v1":
        raise ExperimentContractError("return_envelope_schema_invalid")
    if envelope.get("goal_id") != goal_id:
        raise ExperimentContractError("return_envelope_goal_identity_drift")
    if envelope.get("derivation") != "continuous_cut_goal":
        raise ExperimentContractError("return_envelope_not_goal_derived")
    token = finite_vector(envelope.get("token"), 18, "return_envelope.token")
    if token[16] <= 0.5 or token[17] <= 0.5:
        raise ExperimentContractError("return_envelope_token_incomplete")
    finite_float(
        envelope.get("prior_independent_local_depth_m"),
        "return_envelope.prior_independent_local_depth_m",
    )
    finite_float(
        envelope.get("prior_independent_plane_depth_m"),
        "return_envelope.prior_independent_plane_depth_m",
    )
    reference = mapping(
        envelope.get("handoff_reference"),
        "return_envelope.handoff_reference",
    )
    if reference.get("goal_id") != goal_id:
        raise ExperimentContractError(
            "return_envelope_handoff_goal_identity_drift"
        )
    qpos = finite_vector(
        reference.get("qpos"),
        4,
        "return_envelope.handoff_reference.qpos",
    )
    half_width = finite_vector(
        reference.get("qpos_half_width"),
        4,
        "return_envelope.handoff_reference.qpos_half_width",
    )
    if any(value < 0.0 for value in half_width):
        raise ExperimentContractError(
            "return_envelope_qpos_half_width_invalid"
        )
    for field in ("qvel_abs_max", "spatial_half_width_norm"):
        if finite_float(
            reference.get(field),
            f"return_envelope.handoff_reference.{field}",
        ) < 0.0:
            raise ExperimentContractError(
                f"return_envelope_handoff_{field}_invalid"
            )
    if not isinstance(reference.get("expected_contact"), bool):
        raise ExperimentContractError(
            "return_envelope_expected_contact_invalid"
        )
    for field in ("predictor_profile", "predictor_version"):
        if not str(reference.get(field, "")).strip():
            raise ExperimentContractError(
                f"return_envelope_handoff_{field}_missing"
            )
    if not is_sha256(str(reference.get("predictor_code_sha256", ""))):
        raise ExperimentContractError(
            "return_envelope_handoff_predictor_code_sha_invalid"
        )
    if predictor_evidence is not None:
        predictor = mapping(
            predictor_evidence.get("predictor"),
            "predictor_evidence.predictor",
        )
        for reference_field, predictor_field in (
            ("predictor_profile", "profile"),
            ("predictor_version", "version"),
            ("predictor_code_sha256", "code_sha256"),
        ):
            if reference.get(reference_field) != predictor.get(
                predictor_field
            ):
                raise ExperimentContractError(
                    "return_envelope_predictor_lineage_drift"
                )
        predictor_handoff = finite_vector(
            predictor_evidence.get("handoff_qpos"),
            4,
            "predictor_evidence.handoff_qpos",
        )
        if max(
            abs(qpos[index] - predictor_handoff[index])
            for index in range(4)
        ) > PATH_START_TOLERANCE:
            raise ExperimentContractError(
                "return_envelope_handoff_qpos_drift"
            )


def validate_support_diagnostic(value: Any) -> None:
    support = mapping(value, "support_ood")
    if support.get("schema") != "continuous_goal_support_diagnostic_v1":
        raise ExperimentContractError("support_ood_schema_invalid")
    if support.get("support_status") not in {"supported", "ood", "unknown"}:
        raise ExperimentContractError("support_ood_status_invalid")
    if support.get("whole_goal_distance") is not None:
        finite_float(
            support.get("whole_goal_distance"),
            "support_ood.whole_goal_distance",
        )
    if support.get("episode_snap_applied") is not False:
        raise ExperimentContractError("support_ood_episode_snap_forbidden")
    if support.get("diagnostic_only") is not True:
        raise ExperimentContractError("support_ood_must_be_diagnostic")


def validate_predictor_record(
    value: Any,
    *,
    goal_id: str,
) -> dict[str, Any]:
    record = mapping(value, "predictor_record")
    if record.get("status") != "passed":
        raise ExperimentContractError("predictor_missing_or_not_passed")
    if record.get("goal_id") != goal_id:
        raise ExperimentContractError("predictor_goal_identity_drift")
    predictor = mapping(record.get("predictor"), "predictor")
    provider = str(predictor.get("provider", "")).strip()
    if not provider or "expert" in provider.lower() or "nearest" in provider.lower():
        raise ExperimentContractError("predictor_fallback_forbidden")
    if not is_sha256(str(predictor.get("code_sha256", ""))):
        raise ExperimentContractError("predictor_code_sha_invalid")
    for field in ("profile", "version"):
        if not str(predictor.get(field, "")).strip():
            raise ExperimentContractError(f"predictor_{field}_missing")
    handoff = finite_vector(record.get("handoff_qpos"), 4, "handoff_qpos")
    finite_vector(record.get("handoff_qvel"), 4, "handoff_qvel")
    qpos_order = record.get("qpos_order")
    if (
        not sequence(qpos_order)
        or tuple(qpos_order) != CONTINUOUS_QPOS_ORDER
    ):
        raise ExperimentContractError("qpos_order_invalid")
    raw_path = record.get("planned_qpos_path")
    if not sequence(raw_path) or len(raw_path) < 2:
        raise ExperimentContractError("planned_qpos_path_invalid")
    path = [
        finite_vector(row, 4, f"planned_qpos_path[{index}]")
        for index, row in enumerate(raw_path)
    ]
    if max(abs(path[0][index] - handoff[index]) for index in range(4)) > (
        PATH_START_TOLERANCE
    ):
        raise ExperimentContractError("planned_qpos_path_start_mismatch")
    path_sha = qpos_path_sha256(path)
    if record.get("path_sha256") != path_sha:
        raise ExperimentContractError("planned_qpos_path_sha_invalid")
    measurement = mapping(record.get("unity_measurement"), "unity_measurement")
    if measurement.get("schema") != WORKTOOL_MEASUREMENT_SCHEMA:
        raise ExperimentContractError("unity_measurement_schema_invalid")
    if (
        measurement.get("goal_id") != goal_id
        or measurement.get("path_sha256") != path_sha
    ):
        raise ExperimentContractError("unity_measurement_lineage_invalid")
    expected_lineage = {
        "predictor_profile": predictor["profile"],
        "predictor_version": predictor["version"],
        "predictor_code_sha256": predictor["code_sha256"],
        "goal_sha256": goal_id,
    }
    for field, expected in expected_lineage.items():
        if measurement.get(field) != expected:
            raise ExperimentContractError(
                f"unity_measurement_lineage_invalid:{field}"
            )
    input_sha256 = record.get("input_sha256")
    if input_sha256 is not None:
        if not is_sha256(str(input_sha256)) or (
            measurement.get("input_sha256") != input_sha256
        ):
            raise ExperimentContractError(
                "unity_measurement_lineage_invalid:input_sha256"
            )
    nominal = finite_float(
        measurement.get("nominal_minimum_clearance_m"),
        "nominal_minimum_clearance_m",
    )
    witnesses = measurement.get("witnesses")
    if not sequence(witnesses):
        raise ExperimentContractError("unity_witnesses_invalid")
    witness_keys: set[tuple[str, str]] = set()
    for index, witness in enumerate(witnesses):
        item = mapping(witness, f"witnesses[{index}]")
        key = (str(item.get("link", "")), str(item.get("wall", "")))
        witness_keys.add(key)
        finite_float(
            item.get("minimum_clearance_m"),
            f"witnesses[{index}].minimum_clearance_m",
        )
    if witness_keys != _WITNESS_KEYS or len(witnesses) != 12:
        raise ExperimentContractError("unity_witness_inventory_invalid")
    effective = (
        nominal - ACT_TRACKING_MARGIN_M - POSE_INTERPOLATION_BOUND_M
    )
    return {
        "goal_id": goal_id,
        "predictor": copy.deepcopy(predictor),
        "handoff_qpos": list(handoff),
        "handoff_qvel": list(
            finite_vector(record.get("handoff_qvel"), 4, "handoff_qvel")
        ),
        "path_sha256": path_sha,
        "planned_qpos_sample_count": len(path),
        "nominal_minimum_clearance_m": nominal,
        "act_tracking_margin_m": ACT_TRACKING_MARGIN_M,
        "pose_interpolation_bound_m": POSE_INTERPOLATION_BOUND_M,
        "effective_minimum_clearance_m": effective,
        "hard_clearance_m": HARD_CLEARANCE_M,
        "witness_count": 12,
        "safe": effective + 1.0e-12 >= HARD_CLEARANCE_M,
    }


def a0_contract(base: Mapping[str, Any]) -> dict[str, Any]:
    task = mapping(base.get("task"), "base.task")
    if tuple(task.get("camera_names", ())) != CAMERA_ORDER:
        raise ExperimentContractError("a0_contract_drift:camera_order")
    evaluation = mapping(base.get("eval"), "base.eval")
    if evaluation.get("no_overwrite") is not True:
        raise ExperimentContractError("a0_contract_drift:no_overwrite")
    policy = mapping(base.get("policy"), "base.policy")
    planner = mapping(policy.get("dig_cut_planner"), "dig_cut_planner")
    if planner.get("fallback_mode") != "raise":
        raise ExperimentContractError("a0_contract_drift:fallback_mode")
    act = mapping(policy.get("act_params"), "policy.act_params")
    if (
        integer(act.get("temporal_agg_window"), default=-1) != 100
        or act.get("temporal_agg_weight_order") != "legacy_oldest_first"
    ):
        raise ExperimentContractError("a0_contract_drift:temporal_aggregation")
    box = mapping(policy.get("box_emptying"), "policy.box_emptying")
    if box.get("safety_enabled") is not True:
        raise ExperimentContractError("a0_contract_drift:typed_safety")
    carry = mapping(
        box.get("carry_start_envelope"),
        "box_emptying.carry_start_envelope",
    )
    if carry.get("enabled") is not True:
        raise ExperimentContractError("a0_contract_drift:carry_envelope")
    checkpoints: dict[str, dict[str, Any]] = {}
    for primitive in PRIMITIVES:
        path = require_file(policy.get(f"{primitive}_ckpt_path"))
        checkpoints[primitive] = {
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "sha256": sha256(path),
        }
    locked = {
        "checkpoints": checkpoints,
        "camera_order": list(CAMERA_ORDER),
        "action_scale": copy.deepcopy(policy.get("action_scale")),
        "action_scale_explicit": "action_scale" in policy,
        "temporal_aggregation": {
            "window": 100,
            "weight_order": "legacy_oldest_first",
            "decay": act.get("temporal_agg_decay"),
        },
        "carry_start_envelope": copy.deepcopy(carry),
        "typed_safety": {
            "safety_enabled": True,
            "safety": copy.deepcopy(box.get("safety")),
        },
        "switch": copy.deepcopy(policy.get("switch")),
        "boundary": copy.deepcopy(base.get("boundary")),
        "terminal": {
            "target_cycle_gate": evaluation.get("target_cycle_gate"),
            "target_cycle_gate_terminal_hold_steps": evaluation.get(
                "target_cycle_gate_terminal_hold_steps"
            ),
        },
    }
    locked["contract_sha256"] = hashlib.sha256(
        canonical_json_bytes(locked)
    ).hexdigest()
    return locked


def assert_single_factor_config_mappings(
    configs: Mapping[str, Mapping[str, Any]],
    *,
    condition_ids: Sequence[str],
) -> None:
    if set(configs) != set(condition_ids):
        raise ExperimentContractError("condition_config_inventory_invalid")
    normalized: list[bytes] = []
    for condition_id in condition_ids:
        config = copy.deepcopy(dict(configs[condition_id]))
        evaluation = mapping(config.get("eval"), "config.eval")
        for field in (
            "results_dir",
            "video_dir",
            "rollout_log_dir",
            "hdf5_dir",
        ):
            evaluation[field] = "<condition-output>"
        metadata = mapping(
            evaluation.get("record_hdf5_metadata"),
            "record_hdf5_metadata",
        )
        metadata["condition_id"] = "<condition-id>"
        metadata["goal_source_kind"] = "<goal-source-kind>"
        planner = mapping(
            mapping(config.get("policy"), "config.policy").get(
                "dig_cut_planner"
            ),
            "dig_cut_planner",
        )
        continuous = mapping(
            planner.get("continuous_goal_conditioned"),
            "continuous_goal_conditioned",
        )
        continuous["source"] = "<condition-source>"
        normalized.append(canonical_json_bytes(config))
    if len(set(normalized)) != 1:
        raise ExperimentContractError("a0_contract_drift")


def validate_live_record(
    record: Mapping[str, Any],
    *,
    condition_id: str,
    expected_sequence_index: int,
) -> None:
    if (
        record.get("schema")
        != "goal_conditioned_return_to_dig_probe_record_v1"
        or record.get("condition_id") != condition_id
        or record.get("status") not in {"passed", "failed", "invalid"}
    ):
        raise ExperimentContractError(
            f"{condition_id}:live_record_contract_invalid"
        )
    if (
        integer(record.get("attempt_index"), default=-1) != 1
        or integer(record.get("retry_count"), default=-1) != 0
        or integer(record.get("live_sequence_index"), default=-1)
        != expected_sequence_index
    ):
        raise ExperimentContractError(
            f"{condition_id}:single_attempt_order_contract_invalid"
        )
    for field in (
        "initial_state_valid",
        "return_handoff_passed",
        "worktool_3d_guard_passed",
        "actual_path_within_reference_sweep",
        "terminal_zero_action",
        "neutral_acknowledged",
    ):
        if not isinstance(record.get(field), bool):
            raise ExperimentContractError(
                f"{condition_id}:live_boolean_missing:{field}"
            )
    fairness = mapping(
        record.get("reset_fairness"),
        f"{condition_id}.reset_fairness",
    )
    fairness_valid = True
    for field, limit in RESET_FAIRNESS_LIMITS.items():
        observed = finite_float(
            fairness.get(field),
            f"{condition_id}.reset_fairness.{field}",
        )
        if observed < 0.0 or observed > limit + 1.0e-12:
            fairness_valid = False
    if not isinstance(fairness.get("soil_seed_controlled"), bool):
        raise ExperimentContractError(
            f"{condition_id}:soil_seed_control_state_missing"
        )
    if (
        fairness.get("soil_seed_controlled") is False
        and not str(fairness.get("soil_seed_note", "")).strip()
    ):
        raise ExperimentContractError(
            f"{condition_id}:soil_seed_difference_note_missing"
        )
    if bool(record.get("initial_state_valid")) != fairness_valid:
        raise ExperimentContractError(
            f"{condition_id}:reset_fairness_status_inconsistent"
        )
    if record.get("status") == "passed" and not fairness_valid:
        raise ExperimentContractError(
            f"{condition_id}:passed_with_invalid_reset"
        )
    safety_counts: list[int] = []
    for field in (
        "wall_contact_count",
        "bottom_contact_count",
        "stuck_count",
        "timeout_count",
    ):
        count = integer(record.get(field), default=-1)
        if count < 0:
            raise ExperimentContractError(
                f"{condition_id}:live_count_invalid:{field}"
            )
        safety_counts.append(count)
    if record.get("status") == "passed" and any(safety_counts):
        raise ExperimentContractError(
            f"{condition_id}:passed_with_safety_abort"
        )
    if record.get("terminal_zero_action") is not True or (
        record.get("neutral_acknowledged") is not True
    ):
        raise ExperimentContractError(
            f"{condition_id}:terminal_neutral_contract_failed"
        )


def verify_source_lock(source_lock: Mapping[str, Any]) -> None:
    for label, raw in source_lock.items():
        record = mapping(raw, f"source_lock.{label}")
        verify_file_sha(
            record.get("path"),
            record.get("sha256"),
            label=str(label),
        )
        path = require_file(record.get("path"))
        if path.stat().st_size != integer(
            record.get("size_bytes"),
            default=-1,
        ):
            raise ExperimentContractError(
                f"source_artifact_drift:{label}:size"
            )


def verify_a0_contract_sources(contract: Mapping[str, Any]) -> None:
    checkpoints = mapping(
        contract.get("checkpoints"),
        "a0_contract.checkpoints",
    )
    if set(checkpoints) != set(PRIMITIVES):
        raise ExperimentContractError("a0_contract_drift:checkpoint_inventory")
    for primitive in PRIMITIVES:
        record = mapping(
            checkpoints[primitive],
            f"a0_contract.checkpoints.{primitive}",
        )
        path = require_file(record.get("path"))
        if (
            path.stat().st_size
            != integer(record.get("size_bytes"), default=-1)
            or sha256(path) != record.get("sha256")
        ):
            raise ExperimentContractError(
                f"source_artifact_drift:a0_checkpoint:{primitive}"
            )


def verify_file_sha(
    path_value: Any,
    expected_sha256: Any,
    *,
    label: str,
) -> None:
    path = require_file(path_value)
    if sha256(path) != str(expected_sha256):
        raise ExperimentContractError(f"source_artifact_drift:{label}:sha256")


def source_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def require_file(value: Any) -> Path:
    if value is None:
        raise FileNotFoundError("required file path is missing")
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def load_json_mapping(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    return dict(mapping(value, str(path)))


def load_yaml_mapping(path: Path) -> dict[str, Any]:
    import yaml

    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    return dict(mapping(value, str(path)))


def mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ExperimentContractError(f"{label}:mapping_required")
    return value if isinstance(value, dict) else dict(value)


def sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    )


def finite_vector(
    value: Any,
    length: int,
    label: str,
) -> tuple[float, ...]:
    if not sequence(value) or len(value) != length:
        raise ExperimentContractError(f"{label}:length_invalid")
    return tuple(
        finite_float(item, f"{label}[{index}]")
        for index, item in enumerate(value)
    )


def finite_float(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ExperimentContractError(f"{label}:not_numeric") from exc
    if not math.isfinite(result):
        raise ExperimentContractError(f"{label}:not_finite")
    return result


def integer(value: Any, *, default: int | None) -> int:
    if isinstance(value, bool):
        if default is not None:
            return default
        raise ExperimentContractError("integer_required")
    try:
        result = int(value)
    except (TypeError, ValueError):
        if default is not None:
            return default
        raise ExperimentContractError("integer_required") from None
    if isinstance(value, float) and not value.is_integer():
        if default is not None:
            return default
        raise ExperimentContractError("integer_required")
    return result


def is_sha256(value: str) -> bool:
    return (
        len(value) == 64
        and value == value.lower()
        and set(value) <= _HEX_DIGITS
    )


def canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ExperimentContractError("canonical_json_invalid") from exc


def pretty_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def write_json_exclusive(path: Path, value: Any) -> None:
    with path.open("xb") as handle:
        handle.write(pretty_json_bytes(value))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def qpos_path_sha256(path: Sequence[Sequence[float]]) -> str:
    """Hash normalized qpos as float32 LE row-major bytes."""

    payload = b"".join(
        struct.pack("<f", float(value))
        for row in path
        for value in row
    )
    return hashlib.sha256(payload).hexdigest()
