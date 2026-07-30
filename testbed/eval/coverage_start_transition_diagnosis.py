"""Build and classify recorded tuple-start geometry evidence; never promote."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import h5py
import numpy as np

TRANSITION_MEASUREMENT_INPUT_SCHEMA = "worktool_transition_sweep_input_v1"
TRANSITION_MEASUREMENT_OUTPUT_SCHEMA = "worktool_transition_sweep_measurement_v1"
START_TRANSITION_DIAGNOSIS_SCHEMA = "coverage_start_transition_geometry_diagnosis_v1"
TRANSITION_MEASUREMENT_INPUT_FILENAME = f"{TRANSITION_MEASUREMENT_INPUT_SCHEMA}.json"
START_TRANSITION_DIAGNOSIS_FILENAME = f"{START_TRANSITION_DIAGNOSIS_SCHEMA}.json"

_EXECUTION_LIBRARY_SCHEMA = "strict_train_coverage_execution_library_v1_1"
_RETURN_TRANSITION_SCHEMA = "strict_train_coverage_return_transition_library_v1"
_PRODUCTION_PREFLIGHT_SCHEMA = "coverage_execution_production_preflight_v2"
_EXPECTED_EXECUTION_LIBRARY_SIZE = 374
_CYCLE0_EXEMPLAR_ID = "episode_24"
_POST_RETURN_EXEMPLAR_ID = "episode_171"
_POST_RETURN_PAIRED_RETURN_ID = "episode_161"
_EXPECTED_LINKS = ("boom", "stick", "bucket")
_EXPECTED_WALLS = (
    "Dig_XMax_Board",
    "Dig_XMin_Board",
    "Dig_ZMax_Board",
    "Dig_ZMin_Board",
)


def build_start_transition_measurement_input(
    *,
    execution_library_path: str | Path,
    return_transition_artifact_path: str | Path,
    production_preflight_path: str | Path,
    cycle0_source_episode_path: str | Path,
    post_return_source_episode_path: str | Path,
    frozen_cycle0_rollout_path: str | Path,
    frozen_cycle0_observation_step: int,
    post_return_dig_end_step: int,
    output_dir: str | Path,
) -> dict[str, Any]:
    destination = Path(output_dir).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(
            f"refusing to overwrite transition diagnosis directory: {destination}"
        )

    execution_path = _require_file(execution_library_path)
    transition_path = _require_file(return_transition_artifact_path)
    preflight_path = _require_file(production_preflight_path)
    cycle0_path = _require_file(cycle0_source_episode_path)
    post_return_path = _require_file(post_return_source_episode_path)
    frozen_path = _require_file(frozen_cycle0_rollout_path)

    execution = _read_json_mapping(execution_path)
    transitions = _read_json_mapping(transition_path)
    preflight = _read_json_mapping(preflight_path)
    _require_schema_status(
        execution,
        schema=_EXECUTION_LIBRARY_SCHEMA,
        status="completed",
        label="execution library",
    )
    sample_count = int(execution.get("sample_count", -1))
    if sample_count not in (2, _EXPECTED_EXECUTION_LIBRARY_SIZE):
        # The two-record form is intentionally supported for focused tests.
        raise ValueError(
            "execution library sample_count must be 374 (or 2 in a focused fixture)"
        )
    _require_schema_status(
        transitions,
        schema=_RETURN_TRANSITION_SCHEMA,
        status="completed",
        label="return transition artifact",
    )
    _require_schema_status(
        preflight,
        schema=_PRODUCTION_PREFLIGHT_SCHEMA,
        status="failed",
        label="production preflight",
    )

    execution_records = _records_by_exemplar(
        execution,
        label="execution library",
    )
    transition_records = _records_by_exemplar(
        transitions,
        label="return transition artifact",
    )
    cycle0_execution = _required_record(
        execution_records,
        _CYCLE0_EXEMPLAR_ID,
    )
    post_execution = _required_record(
        execution_records,
        _POST_RETURN_EXEMPLAR_ID,
    )
    cycle0_transition = _required_record(
        transition_records,
        _CYCLE0_EXEMPLAR_ID,
    )
    post_transition = _required_record(
        transition_records,
        _POST_RETURN_EXEMPLAR_ID,
    )
    _validate_lineage(
        cycle0_execution=cycle0_execution,
        post_execution=post_execution,
        cycle0_transition=cycle0_transition,
        post_transition=post_transition,
    )

    contract = _measurement_contract(preflight)
    cycle0_trace = _candidate_trace(
        preflight,
        case_id="cycle0_reset_state",
        exemplar_id=_CYCLE0_EXEMPLAR_ID,
    )
    post_trace = _candidate_trace(
        preflight,
        case_id="post_return_reset_0",
        exemplar_id=_POST_RETURN_EXEMPLAR_ID,
    )

    cycle0_start = int(cycle0_transition["dig_start_source_step"])
    return_start = int(post_transition["return_start_source_step"])
    return_handoff = int(post_transition["return_handoff_source_step"])
    post_dig_start = int(post_transition["dig_start_source_step"])
    post_dig_end = int(post_return_dig_end_step)
    if not return_start <= return_handoff <= post_dig_start <= post_dig_end:
        raise ValueError(
            "post-return source steps are not ordered "
            "return_start<=handoff<=dig_start<=dig_end"
        )

    paths = [
        _path_record(
            path_id="cycle0_source_expert_preamble",
            kind="cycle0_initialization_to_tuple_start",
            path_source="recorded_strict_expert",
            source_path=cycle0_path,
            start_step=None,
            end_step=cycle0_start,
            endpoint_role="expert_tuple_start",
            exemplar_id=_CYCLE0_EXEMPLAR_ID,
            raw_fields_sha256=_execution_raw_fields_sha256(cycle0_execution),
            planner_bound_endpoint_match=False,
            conservative_start_bound_m=float(
                cycle0_trace["worktool_sweep_3d_live_start_displacement_bound_m"]
            ),
        ),
        _path_record(
            path_id="cycle0_frozen_runtime_prefix",
            kind="cycle0_recorded_runtime_prefix",
            path_source="recorded_live_qpos",
            source_path=frozen_path,
            start_step=None,
            end_step=int(frozen_cycle0_observation_step),
            endpoint_role="unmatched_live_start",
            exemplar_id=_CYCLE0_EXEMPLAR_ID,
            raw_fields_sha256=_execution_raw_fields_sha256(cycle0_execution),
            planner_bound_endpoint_match=False,
            conservative_start_bound_m=float(
                cycle0_trace["worktool_sweep_3d_live_start_displacement_bound_m"]
            ),
        ),
        _path_record(
            path_id="post_return_gold_full",
            kind="paired_gold_return_to_tuple_start",
            path_source="recorded_strict_expert",
            source_path=post_return_path,
            start_step=return_start,
            end_step=post_dig_start,
            endpoint_role="expert_tuple_start",
            exemplar_id=_POST_RETURN_EXEMPLAR_ID,
            raw_fields_sha256=_execution_raw_fields_sha256(post_execution),
            planner_bound_endpoint_match=False,
            conservative_start_bound_m=float(
                post_trace["worktool_sweep_3d_live_start_displacement_bound_m"]
            ),
            paired_return_exemplar_id=_POST_RETURN_PAIRED_RETURN_ID,
        ),
        _path_record(
            path_id="post_return_handoff_tail",
            kind="paired_return_handoff_to_tuple_start",
            path_source="recorded_strict_expert",
            source_path=post_return_path,
            start_step=return_handoff,
            end_step=post_dig_start,
            endpoint_role="expert_tuple_start",
            exemplar_id=_POST_RETURN_EXEMPLAR_ID,
            raw_fields_sha256=_execution_raw_fields_sha256(post_execution),
            planner_bound_endpoint_match=True,
            conservative_start_bound_m=float(
                post_trace["worktool_sweep_3d_live_start_displacement_bound_m"]
            ),
            paired_return_exemplar_id=_POST_RETURN_PAIRED_RETURN_ID,
        ),
        _path_record(
            path_id="post_return_handoff_plus_dig",
            kind="paired_return_handoff_and_expert_dig",
            path_source="recorded_strict_expert",
            source_path=post_return_path,
            start_step=return_handoff,
            end_step=post_dig_end,
            endpoint_role="expert_dig_end",
            exemplar_id=_POST_RETURN_EXEMPLAR_ID,
            raw_fields_sha256=_execution_raw_fields_sha256(post_execution),
            planner_bound_endpoint_match=False,
            conservative_start_bound_m=float(
                post_trace["worktool_sweep_3d_live_start_displacement_bound_m"]
            ),
            paired_return_exemplar_id=_POST_RETURN_PAIRED_RETURN_ID,
        ),
        _path_record(
            path_id="post_return_dig_only",
            kind="expert_dig_from_tuple_start",
            path_source="recorded_strict_expert",
            source_path=post_return_path,
            start_step=post_dig_start,
            end_step=post_dig_end,
            endpoint_role="expert_dig_end",
            exemplar_id=_POST_RETURN_EXEMPLAR_ID,
            raw_fields_sha256=_execution_raw_fields_sha256(post_execution),
            planner_bound_endpoint_match=False,
            conservative_start_bound_m=float(
                post_trace["worktool_sweep_3d_live_start_displacement_bound_m"]
            ),
            paired_return_exemplar_id=_POST_RETURN_PAIRED_RETURN_ID,
        ),
    ]

    artifact: dict[str, Any] = {
        "schema": TRANSITION_MEASUREMENT_INPUT_SCHEMA,
        "status": "ready",
        "profile": "phase_specific_recorded_start_transition_sweep_v1",
        "evidence_kind": "offline_recorded_qpos_geometry_request",
        "closed_loop_claim": False,
        "future_act_physics_simulation": False,
        "training_data_written": False,
        "contract": contract,
        "source_lock": {
            "execution_library": _source_record(execution_path),
            "return_transition_artifact": _source_record(transition_path),
            "production_preflight": _source_record(preflight_path),
            "cycle0_source_episode": _source_record(cycle0_path),
            "post_return_source_episode": _source_record(post_return_path),
            "frozen_cycle0_rollout": _source_record(frozen_path),
        },
        "lineage": {
            "cycle0": _lineage_record(
                execution=cycle0_execution,
                transition=cycle0_transition,
            ),
            "post_return": _lineage_record(
                execution=post_execution,
                transition=post_transition,
            ),
        },
        "interpretation_guard": {
            "cycle0_expert_preamble_is_current_runtime_alignment_proof": False,
            "post_return_uses_full_source_episode_continuity": True,
            "synthetic_interpolation_used": False,
            "threshold_change_authorized": False,
            "bounded_live_authorized": False,
        },
        "paths": paths,
    }
    destination.mkdir(parents=True, exist_ok=False)
    output_path = destination / TRANSITION_MEASUREMENT_INPUT_FILENAME
    _write_new_json(output_path, artifact)
    return artifact


def classify_start_transition_geometry(
    *,
    contract: Mapping[str, Any],
    input_paths: Mapping[str, Mapping[str, Any]],
    measured_clearance_by_path: Mapping[str, float],
    conservative_start_bounds: Mapping[str, float],
    endpoint_displacement_by_path: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    hard = _finite_nonnegative(contract, "hard_clearance_m")
    act = _finite_nonnegative(contract, "act_tracking_margin_m")
    interpolation = _finite_nonnegative(
        contract,
        "pose_interpolation_bound_m",
    )
    for key in ("cycle0", "post_return"):
        _finite_nonnegative(conservative_start_bounds, key)
    required = (
        "cycle0_source_expert_preamble",
        "cycle0_frozen_runtime_prefix",
        "post_return_gold_full",
        "post_return_handoff_tail",
        "post_return_handoff_plus_dig",
        "post_return_dig_only",
    )
    missing = [
        path_id for path_id in required if path_id not in measured_clearance_by_path
    ]
    if missing:
        raise ValueError(f"transition measurements missing paths: {missing}")
    measurements = {
        path_id: _finite_nonnegative(
            measured_clearance_by_path,
            path_id,
        )
        for path_id in required
    }

    post_nominal = min(
        measurements["post_return_handoff_plus_dig"],
        measurements["post_return_dig_only"],
    )
    post_effective = post_nominal - interpolation - act
    post_eligible = post_effective >= hard
    if post_eligible:
        post_classification = (
            "paired_transition_and_expert_dig_meet_calibrated_contract"
        )
    else:
        post_classification = (
            "reachable_tuple_nominal_clearance_below_calibrated_contract"
        )

    endpoint_comparison: dict[str, Any] = {}
    if endpoint_displacement_by_path is not None:
        for phase, path_id in (
            ("cycle0", "cycle0_source_expert_preamble"),
            ("post_return", "post_return_handoff_tail"),
        ):
            path_contract = input_paths.get(path_id, {})
            if not bool(path_contract.get("planner_bound_endpoint_match", False)):
                continue
            measured = _finite_nonnegative(
                endpoint_displacement_by_path,
                path_id,
            )
            conservative = float(conservative_start_bounds[phase])
            endpoint_comparison[phase] = {
                "measured_endpoint_cover_displacement_m": measured,
                "planner_conservative_start_bound_m": conservative,
                "planner_bound_minus_measured_m": conservative - measured,
                "planner_bound_is_conservative": (conservative + 1.0e-9 >= measured),
            }

    cycle0_endpoint_role = str(
        input_paths.get(
            "cycle0_frozen_runtime_prefix",
            {},
        ).get("endpoint_role", "")
    )
    cycle0_alignment_proven = cycle0_endpoint_role == "expert_tuple_start"
    cycle0_classification = (
        "recorded_runtime_reaches_exact_tuple_start"
        if cycle0_alignment_proven
        else "expert_preamble_is_not_current_runtime_alignment_proof"
    )

    # Promotion requires matched runtime transitions and a safe entire dig;
    # the frozen cycle-zero prefix deliberately proves neither.
    contract_change_allowed = bool(
        cycle0_alignment_proven
        and post_eligible
        and set(endpoint_comparison) == {"cycle0", "post_return"}
        and all(
            bool(item["planner_bound_is_conservative"])
            for item in endpoint_comparison.values()
        )
    )
    bounded_live_allowed = bool(contract_change_allowed and post_eligible)
    return {
        "schema": START_TRANSITION_DIAGNOSIS_SCHEMA,
        "status": ("passed" if bounded_live_allowed else "blocked"),
        "contract": {
            "hard_clearance_m": hard,
            "act_tracking_margin_m": act,
            "pose_interpolation_bound_m": interpolation,
        },
        "cycle0": {
            "source_expert_preamble_clearance_m": measurements[
                "cycle0_source_expert_preamble"
            ],
            "frozen_runtime_prefix_clearance_m": measurements[
                "cycle0_frozen_runtime_prefix"
            ],
            "alignment_proven": cycle0_alignment_proven,
            "classification": cycle0_classification,
        },
        "post_return": {
            "gold_return_to_dig_start_clearance_m": measurements[
                "post_return_gold_full"
            ],
            "handoff_to_dig_start_clearance_m": measurements[
                "post_return_handoff_tail"
            ],
            "handoff_plus_dig_clearance_m": measurements[
                "post_return_handoff_plus_dig"
            ],
            "dig_only_clearance_m": measurements["post_return_dig_only"],
            "measured_nominal_clearance_m": post_nominal,
            "measured_effective_clearance_m": post_effective,
            "eligible": post_eligible,
            "classification": post_classification,
        },
        "endpoint_bound_comparison": endpoint_comparison,
        "start_bound_contract_change_allowed": contract_change_allowed,
        "bounded_live_allowed": bounded_live_allowed,
        "thresholds_relaxed": False,
        "training_data_written": False,
        "next_action": (
            "rerun_production_preflight"
            if bounded_live_allowed
            else "stop_before_live_keep_calibrated_contract"
        ),
    }


def build_start_transition_geometry_diagnosis(
    *,
    measurement_input_path: str | Path,
    unity_measurement_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    input_path = _require_file(measurement_input_path)
    measurement_path = _require_file(unity_measurement_path)
    destination = Path(output_dir).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(
            f"refusing to overwrite transition diagnosis directory: {destination}"
        )
    request = _read_json_mapping(input_path)
    measurement = _read_json_mapping(measurement_path)
    _require_schema_status(
        request,
        schema=TRANSITION_MEASUREMENT_INPUT_SCHEMA,
        status="ready",
        label="transition measurement input",
    )
    _require_schema_status(
        measurement,
        schema=TRANSITION_MEASUREMENT_OUTPUT_SCHEMA,
        status="completed",
        label="Unity transition measurement",
    )
    source_lock = measurement.get("source_lock")
    if not isinstance(source_lock, Mapping):
        raise ValueError("Unity transition measurement source_lock is missing")
    expected_input_sha = _sha256_file(input_path)
    if str(source_lock.get("input_sha256", "")).lower() != expected_input_sha:
        raise ValueError("Unity transition measurement input SHA drift")

    request_paths = {
        str(item["path_id"]): item
        for item in _mapping_sequence(request.get("paths"), "request paths")
    }
    measured_paths = {
        str(item["path_id"]): item
        for item in _mapping_sequence(
            measurement.get("paths"),
            "measured paths",
        )
    }
    if set(request_paths) != set(measured_paths):
        raise ValueError("Unity transition measurement path set mismatch")
    measured_clearance: dict[str, float] = {}
    endpoint_displacement: dict[str, float] = {}
    for path_id, item in measured_paths.items():
        _validate_link_wall_witnesses(path_id, item)
        measured_clearance[path_id] = _finite_nonnegative(
            item,
            "sampled_convex_cover_clearance_m",
        )
        endpoint_displacement[path_id] = _finite_nonnegative(
            item,
            "endpoint_maximum_convex_cover_displacement_m",
        )

    contract = request.get("contract")
    if not isinstance(contract, Mapping):
        raise ValueError("transition request contract is missing")
    conservative_bounds = {
        "cycle0": float(
            request_paths["cycle0_source_expert_preamble"][
                "planner_start_displacement_bound_m"
            ]
        ),
        "post_return": float(
            request_paths["post_return_handoff_tail"][
                "planner_start_displacement_bound_m"
            ]
        ),
    }
    diagnosis = classify_start_transition_geometry(
        contract=contract,
        input_paths=request_paths,
        measured_clearance_by_path=measured_clearance,
        conservative_start_bounds=conservative_bounds,
        endpoint_displacement_by_path=endpoint_displacement,
    )
    diagnosis.update(
        {
            "evidence_kind": "offline_unity_shadow_fk_recorded_qpos",
            "closed_loop_claim": False,
            "source_lock": {
                "measurement_input": _source_record(input_path),
                "unity_measurement": _source_record(measurement_path),
            },
            "lineage": request.get("lineage"),
            "unity_measurement_summary": {
                path_id: {
                    "sampled_convex_cover_clearance_m": (measured_clearance[path_id]),
                    "endpoint_maximum_convex_cover_displacement_m": (
                        endpoint_displacement[path_id]
                    ),
                    "closest": item.get("closest"),
                }
                for path_id, item in measured_paths.items()
            },
        }
    )
    destination.mkdir(parents=True, exist_ok=False)
    _write_new_json(
        destination / START_TRANSITION_DIAGNOSIS_FILENAME,
        diagnosis,
    )
    return diagnosis


def _measurement_contract(preflight: Mapping[str, Any]) -> dict[str, float]:
    contract = preflight.get("contract")
    if not isinstance(contract, Mapping):
        raise ValueError("production preflight contract is missing")
    sweep = contract.get("worktool_sweep_3d")
    if not isinstance(sweep, Mapping):
        # Focused fixtures may provide the 3D contract directly.
        sweep = contract
    return {
        "hard_clearance_m": _finite_nonnegative(
            sweep,
            "hard_clearance_m",
        ),
        "act_tracking_margin_m": _finite_nonnegative(
            sweep,
            "act_tracking_margin_m",
        ),
        "pose_interpolation_bound_m": _finite_nonnegative(
            sweep,
            "pose_interpolation_bound_m",
        ),
    }


def _validate_lineage(
    *,
    cycle0_execution: Mapping[str, Any],
    post_execution: Mapping[str, Any],
    cycle0_transition: Mapping[str, Any],
    post_transition: Mapping[str, Any],
) -> None:
    if int(cycle0_execution.get("source_episode_id", -1)) != 6:
        raise ValueError("episode_24 must come from strict source episode 6")
    if int(post_execution.get("source_episode_id", -1)) != 24:
        raise ValueError("episode_171 must come from strict source episode 24")
    if int(cycle0_transition.get("source_episode_id", -1)) != 6:
        raise ValueError("episode_24 transition lineage mismatch")
    if int(cycle0_transition.get("source_cycle_id", -1)) != 0:
        raise ValueError("episode_24 must be material cycle 0")
    cycle0_eligibility = cycle0_transition.get("eligibility")
    if (
        not isinstance(cycle0_eligibility, Mapping)
        or not bool(cycle0_eligibility.get("cycle0"))
        or bool(cycle0_eligibility.get("post_return"))
        or cycle0_transition.get("paired_return_exemplar_id") is not None
    ):
        raise ValueError("episode_24 must remain cycle0-only")
    if int(post_transition.get("source_episode_id", -1)) != 24:
        raise ValueError("episode_171 transition lineage mismatch")
    post_eligibility = post_transition.get("eligibility")
    if (
        not isinstance(post_eligibility, Mapping)
        or not bool(post_eligibility.get("post_return"))
        or str(post_transition.get("paired_return_exemplar_id", ""))
        != _POST_RETURN_PAIRED_RETURN_ID
    ):
        raise ValueError("episode_171 must pair with gold return episode_161")
    for execution, transition in (
        (cycle0_execution, cycle0_transition),
        (post_execution, post_transition),
    ):
        expected = _execution_raw_fields_sha256(execution)
        observed = transition.get("raw_fields_sha256")
        if observed is not None and str(observed) != expected:
            raise ValueError("execution/transition raw-fields SHA mismatch")


def _lineage_record(
    *,
    execution: Mapping[str, Any],
    transition: Mapping[str, Any],
) -> dict[str, Any]:
    keys = (
        "exemplar_id",
        "primitive_episode_id",
        "source_episode_id",
        "source_cycle_id",
        "dig_start_source_step",
        "return_start_source_step",
        "return_handoff_source_step",
        "paired_return_exemplar_id",
        "paired_return_primitive_episode_id",
        "paired_return_source_sha256",
        "dig_source_sha256",
        "exact_return_start_envelope_sha256",
        "eligibility",
    )
    result = {key: transition.get(key) for key in keys}
    result["raw_fields_sha256"] = _execution_raw_fields_sha256(execution)
    return result


def _execution_raw_fields_sha256(record: Mapping[str, Any]) -> str:
    explicit = record.get("raw_fields_sha256")
    if explicit is not None:
        value = str(explicit).lower()
    else:
        raw_fields = record.get("raw_fields")
        if not isinstance(raw_fields, Mapping):
            raise ValueError("execution record raw_fields are missing")
        payload = json.dumps(
            dict(raw_fields),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        value = hashlib.sha256(payload).hexdigest()
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError("execution raw-fields SHA is invalid")
    return value


def _path_record(
    *,
    path_id: str,
    kind: str,
    path_source: str,
    source_path: Path,
    start_step: int | None,
    end_step: int,
    endpoint_role: str,
    exemplar_id: str,
    raw_fields_sha256: str,
    planner_bound_endpoint_match: bool,
    conservative_start_bound_m: float,
    paired_return_exemplar_id: str | None = None,
) -> dict[str, Any]:
    steps, qpos = _read_qpos_range(
        source_path,
        start_step=start_step,
        end_step=end_step,
    )
    return {
        "path_id": path_id,
        "kind": kind,
        "transition_kind": kind,
        "path_source": path_source,
        "source_step_ids": steps.tolist(),
        "qpos_path": qpos.astype(float).tolist(),
        "qpos_order": ["swing", "boom", "stick", "bucket"],
        "endpoint_role": endpoint_role,
        "target_exemplar_id": exemplar_id,
        "raw_fields_sha256": raw_fields_sha256,
        "paired_return_exemplar_id": paired_return_exemplar_id,
        "planner_bound_endpoint_match": bool(planner_bound_endpoint_match),
        "planner_start_displacement_bound_m": (
            _validated_nonnegative_float(
                conservative_start_bound_m,
                "planner start displacement bound",
            )
        ),
        "source": _source_record(source_path),
    }


def _read_qpos_range(
    path: Path,
    *,
    start_step: int | None,
    end_step: int,
) -> tuple[np.ndarray, np.ndarray]:
    with h5py.File(path, "r") as handle:
        step_key = next(
            (
                key
                for key in (
                    "timestamps/step_id",
                    "step_id",
                    "observations/step_id",
                )
                if key in handle
            ),
            None,
        )
        if step_key is None:
            raise ValueError(f"HDF5 step_id dataset missing: {path}")
        if "observations/qpos" not in handle:
            raise ValueError(f"HDF5 qpos dataset missing: {path}")
        steps = np.asarray(handle[step_key][...], dtype=np.int64).reshape(-1)
        qpos = np.asarray(
            handle["observations/qpos"][...],
            dtype=np.float64,
        )
    if qpos.ndim != 2 or qpos.shape != (steps.size, 4):
        raise ValueError(f"HDF5 qpos must have shape (N,4): {path}: {qpos.shape}")
    lower = int(steps[0]) if start_step is None else int(start_step)
    upper = int(end_step)
    if lower > upper:
        raise ValueError("qpos source range start exceeds end")
    mask = (steps >= lower) & (steps <= upper)
    selected_steps = steps[mask]
    selected_qpos = qpos[mask]
    expected_steps = np.arange(lower, upper + 1, dtype=np.int64)
    if not np.array_equal(selected_steps, expected_steps):
        raise ValueError(
            f"qpos source range is not continuous/inclusive: {path}:{lower}:{upper}"
        )
    if selected_qpos.shape[0] < 2:
        raise ValueError("transition qpos path must contain at least two poses")
    if not np.all(np.isfinite(selected_qpos)):
        raise ValueError("transition qpos path contains non-finite values")
    if np.any(selected_qpos < 0.0) or np.any(selected_qpos > 1.0):
        raise ValueError("transition normalized qpos falls outside [0,1]")
    return selected_steps, selected_qpos


def _candidate_trace(
    preflight: Mapping[str, Any],
    *,
    case_id: str,
    exemplar_id: str,
) -> Mapping[str, Any]:
    cases = _mapping_sequence(preflight.get("cases"), "preflight cases")
    case = next(
        (item for item in cases if str(item.get("case_id", "")) == case_id),
        None,
    )
    if case is None:
        raise ValueError(f"production preflight case missing: {case_id}")
    traces = _mapping_sequence(
        case.get("full_candidate_trace"),
        f"{case_id} full_candidate_trace",
    )
    trace = next(
        (item for item in traces if str(item.get("exemplar_id", "")) == exemplar_id),
        None,
    )
    if trace is None:
        raise ValueError(f"production preflight trace missing: {case_id}:{exemplar_id}")
    for key in (
        "worktool_sweep_3d_sampled_convex_cover_clearance_m",
        "worktool_sweep_3d_live_start_displacement_bound_m",
        "worktool_sweep_3d_effective_clearance_m",
    ):
        _finite_float(trace, key)
    return trace


def _validate_link_wall_witnesses(
    path_id: str,
    measurement: Mapping[str, Any],
) -> None:
    links = _mapping_sequence(
        measurement.get("link_sweeps"),
        f"{path_id} link_sweeps",
    )
    by_link = {str(item.get("link_name", "")): item for item in links}
    if set(by_link) != set(_EXPECTED_LINKS):
        raise ValueError(f"{path_id} must contain boom/stick/bucket sweeps")
    minima: list[float] = []
    for link_name in _EXPECTED_LINKS:
        walls = _mapping_sequence(
            by_link[link_name].get("wall_sweeps"),
            f"{path_id}:{link_name}:wall_sweeps",
        )
        by_wall = {str(item.get("wall_name", "")): item for item in walls}
        if set(by_wall) != set(_EXPECTED_WALLS):
            raise ValueError(f"{path_id}:{link_name} must contain all four walls")
        minima.extend(
            _finite_nonnegative(item, "sampled_convex_cover_clearance_m")
            for item in by_wall.values()
        )
    global_minimum = _finite_nonnegative(
        measurement,
        "sampled_convex_cover_clearance_m",
    )
    if not math.isclose(global_minimum, min(minima), abs_tol=1.0e-6):
        raise ValueError(f"{path_id} global clearance is not the 3x4 minimum")


def _records_by_exemplar(
    artifact: Mapping[str, Any],
    *,
    label: str,
) -> dict[str, Mapping[str, Any]]:
    records = _mapping_sequence(artifact.get("records"), f"{label} records")
    result: dict[str, Mapping[str, Any]] = {}
    for record in records:
        exemplar_id = str(record.get("exemplar_id", ""))
        if not exemplar_id or exemplar_id in result:
            raise ValueError(f"{label} exemplar IDs must be non-empty/unique")
        result[exemplar_id] = record
    return result


def _required_record(
    records: Mapping[str, Mapping[str, Any]],
    exemplar_id: str,
) -> Mapping[str, Any]:
    try:
        return records[exemplar_id]
    except KeyError as exc:
        raise ValueError(f"required exemplar missing: {exemplar_id}") from exc


def _mapping_sequence(value: Any, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(
        value,
        (str, bytes, bytearray),
    ):
        raise ValueError(f"{label} must be a sequence")
    result: list[Mapping[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError(f"{label} entries must be mappings")
        result.append(item)
    return result


def _require_schema_status(
    artifact: Mapping[str, Any],
    *,
    schema: str,
    status: str,
    label: str,
) -> None:
    if (
        str(artifact.get("schema", "")) != schema
        or str(artifact.get("status", "")) != status
    ):
        raise ValueError(f"{label} schema/status mismatch")


def _read_json_mapping(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"JSON root must be a mapping: {path}")
    return value


def _source_record(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "sha256": _sha256_file(path),
        "size_bytes": path.stat().st_size,
    }


def _require_file(path: str | Path) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return resolved


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finite_float(mapping: Mapping[str, Any], key: str) -> float:
    try:
        value = float(mapping[key])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be finite") from exc
    if not math.isfinite(value):
        raise ValueError(f"{key} must be finite")
    return value


def _finite_nonnegative(mapping: Mapping[str, Any], key: str) -> float:
    value = _finite_float(mapping, key)
    if value < 0.0:
        raise ValueError(f"{key} must be non-negative")
    return value


def _validated_nonnegative_float(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be finite/non-negative") from exc
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{label} must be finite/non-negative")
    return result


def _write_new_json(path: Path, value: Mapping[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
