"""Build no-overwrite A0 configs for the exact execution-tuple gates."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from testbed.planner.primitive.coverage.worktool_sweep import (
    CALIBRATED_ACT_TRACKING_MARGIN_M,
    CALIBRATED_HARD_CLEARANCE_M,
    CALIBRATED_POSE_INTERPOLATION_BOUND_M,
    TRACKING_CALIBRATION_ARTIFACT_SCHEMA,
    TRACKING_CALIBRATION_ARTIFACT_SHA256,
    TRACKING_CALIBRATION_PROFILE,
)

PURPOSE_BOUNDED_ONE_DIG = "bounded_one_dig"
PURPOSE_FUNCTIONAL_1X10 = "functional_1x10"
PURPOSE_FUNCTIONAL_3X10 = "functional_3x10"
SUPPORTED_PURPOSES = frozenset(
    {
        PURPOSE_BOUNDED_ONE_DIG,
        PURPOSE_FUNCTIONAL_1X10,
        PURPOSE_FUNCTIONAL_3X10,
    }
)
EXECUTION_CONTRACT_VARIANT = (
    "strict_train_actual_tuple_tail_pose_stable_3d_wall_safe_v1"
)
BOUNDED_VALIDATION_SCHEMA = "act_actual_tuple_bounded_one_dig_v1"


def build_coverage_execution_eval_config(
    *,
    base_config_path: str | Path,
    output_path: str | Path,
    run_root: str | Path,
    strict_execution_library_path: str | Path,
    strict_execution_library_sha256: str,
    worktool_sweep_artifact_path: str | Path,
    worktool_sweep_artifact_sha256: str,
    worktool_sweep_pose_library_sha256: str,
    return_transition_artifact_path: str | Path,
    return_transition_artifact_sha256: str,
    purpose: str,
) -> dict[str, Any]:
    """Resolve one exact-tuple eval config while preserving the A0 contract."""

    if purpose not in SUPPORTED_PURPOSES:
        raise ValueError(
            f"unsupported exact-tuple eval purpose: {purpose!r}"
        )
    base_path = Path(base_config_path).expanduser().resolve(strict=True)
    destination = Path(output_path).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite {destination}")
    library_path = Path(
        strict_execution_library_path
    ).expanduser().resolve(strict=True)
    expected_sha256 = str(strict_execution_library_sha256).strip().lower()
    actual_sha256 = hashlib.sha256(library_path.read_bytes()).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ValueError(
            "strict execution library SHA mismatch:"
            f"expected={expected_sha256}:actual={actual_sha256}"
        )
    sweep_path = Path(
        worktool_sweep_artifact_path
    ).expanduser().resolve(strict=True)
    expected_sweep_sha256 = str(
        worktool_sweep_artifact_sha256
    ).strip().lower()
    actual_sweep_sha256 = hashlib.sha256(
        sweep_path.read_bytes()
    ).hexdigest()
    if actual_sweep_sha256 != expected_sweep_sha256:
        raise ValueError(
            "worktool sweep artifact SHA mismatch:"
            f"expected={expected_sweep_sha256}:actual={actual_sweep_sha256}"
        )
    pose_library_sha256 = str(
        worktool_sweep_pose_library_sha256
    ).strip().lower()
    _validate_worktool_sweep_source_lock(
        path=sweep_path,
        execution_library_sha256=actual_sha256,
        pose_library_sha256=pose_library_sha256,
    )
    return_transition_path = Path(
        return_transition_artifact_path
    ).expanduser().resolve(strict=True)
    expected_return_transition_sha256 = str(
        return_transition_artifact_sha256
    ).strip().lower()
    actual_return_transition_sha256 = hashlib.sha256(
        return_transition_path.read_bytes()
    ).hexdigest()
    if actual_return_transition_sha256 != expected_return_transition_sha256:
        raise ValueError(
            "return transition artifact SHA mismatch:"
            f"expected={expected_return_transition_sha256}:"
            f"actual={actual_return_transition_sha256}"
        )
    _validate_return_transition_source_lock(
        path=return_transition_path,
        execution_library_sha256=actual_sha256,
    )
    raw = yaml.safe_load(base_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("base A0 config must contain a mapping")
    base = copy.deepcopy(raw)
    _validate_base_a0_contract(base)
    config = copy.deepcopy(base)

    root = Path(run_root).expanduser().resolve()
    results = root / "results"
    eval_config = config["eval"]
    eval_config.update(
        {
            "num_rollouts": (
                1
                if purpose == PURPOSE_FUNCTIONAL_1X10
                else 3
            ),
            "no_overwrite": True,
            "save_video": purpose != PURPOSE_BOUNDED_ONE_DIG,
            "video_dir": str(root / "videos"),
            "results_dir": str(results),
            "save_rollout_logs": True,
            "stream_rollout_logs": True,
            "rollout_log_dir": str(results / "rollouts"),
            "record_hdf5": True,
            "hdf5_dir": str(results / "hdf5_rollouts"),
        }
    )
    metadata = eval_config.setdefault("record_hdf5_metadata", {})
    metadata.update(
        {
            "planner_execution_contract_variant": (
                EXECUTION_CONTRACT_VARIANT
            ),
            "strict_execution_library_path": str(library_path),
            "strict_execution_library_sha256": actual_sha256,
            "worktool_sweep_artifact_path": str(sweep_path),
            "worktool_sweep_artifact_sha256": actual_sweep_sha256,
            "worktool_sweep_pose_library_sha256": pose_library_sha256,
            "worktool_tracking_calibration_profile": (
                TRACKING_CALIBRATION_PROFILE
            ),
            "worktool_tracking_calibration_schema": (
                TRACKING_CALIBRATION_ARTIFACT_SCHEMA
            ),
            "worktool_tracking_calibration_sha256": (
                TRACKING_CALIBRATION_ARTIFACT_SHA256
            ),
            "return_transition_artifact_path": str(
                return_transition_path
            ),
            "return_transition_artifact_sha256": (
                actual_return_transition_sha256
            ),
            "exact_tuple_eval_purpose": str(purpose),
            "diagnostic_only": int(
                purpose == PURPOSE_BOUNDED_ONE_DIG
            ),
            "promotion_eligible": int(
                purpose == PURPOSE_FUNCTIONAL_3X10
            ),
        }
    )
    metadata["planner_safety_variant"] = (
        "coverage_wall_safety_2d_plus_unity_3d_v1"
    )
    if purpose == PURPOSE_BOUNDED_ONE_DIG:
        metadata["validation_schema"] = BOUNDED_VALIDATION_SCHEMA

    coverage = config["policy"]["dig_cut_planner"]["coverage"]
    coverage["actual_tuple_execution_library"] = {
        "enabled": True,
        "path": str(library_path),
        "artifact_sha256": actual_sha256,
        "mode": "exact_k1",
        "missing_contract": "fail_closed",
        "hard_bottom_margin_m": 0.02,
        "first_plan_pose_stability": {
            "enabled": True,
            "hold_steps": 3,
            "max_step_delta_m": 0.05,
            "max_wait_steps": 30,
        },
        "worktool_sweep_3d": {
            "enabled": True,
            "profile": "unity_kinematic_convex_cover_worktool_sweep_v1",
            "hard_clearance_m": CALIBRATED_HARD_CLEARANCE_M,
            "act_tracking_margin_m": CALIBRATED_ACT_TRACKING_MARGIN_M,
            "pose_interpolation_bound_m": (
                CALIBRATED_POSE_INTERPOLATION_BOUND_M
            ),
            "artifact_path": str(sweep_path),
            "artifact_sha256": actual_sweep_sha256,
            "execution_library_sha256": actual_sha256,
            "pose_library_sha256": pose_library_sha256,
            "missing_contract": "fail_closed",
        },
        "start_reachability": {
            "enabled": True,
            "profile": "strict_train_return_start_reachability_11d_v1",
            "artifact_path": str(return_transition_path),
            "artifact_sha256": actual_return_transition_sha256,
            "execution_library_sha256": actual_sha256,
            "missing_contract": "fail_closed",
        },
    }
    box = config["policy"]["box_emptying"]
    functional = box["functional_cycle_gate"]
    functional["enabled"] = purpose != PURPOSE_BOUNDED_ONE_DIG
    if purpose == PURPOSE_BOUNDED_ONE_DIG:
        box["bounded_dig_probe_stop"] = {
            "enabled": True,
            "diagnostic_only": True,
            "target_cycle_index": 1,
            "max_dig_steps": 500,
        }
    else:
        box.pop("bounded_dig_probe_stop", None)

    _validate_locked_a0_fields_unchanged(base=base, resolved=config)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as handle:
        yaml.safe_dump(
            config,
            handle,
            sort_keys=False,
            allow_unicode=True,
        )
    return config


def _validate_worktool_sweep_source_lock(
    *,
    path: Path,
    execution_library_sha256: str,
    pose_library_sha256: str,
) -> None:
    if len(pose_library_sha256) != 64 or any(
        character not in "0123456789abcdef"
        for character in pose_library_sha256
    ):
        raise ValueError("worktool sweep pose library SHA must be a SHA256")
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("worktool sweep artifact is not valid JSON") from exc
    if (
        not isinstance(artifact, dict)
        or artifact.get("schema")
        != "coverage_worktool_sweep_library_v1"
        or artifact.get("status") != "completed"
        or artifact.get("profile")
        != "unity_kinematic_convex_cover_worktool_sweep_v1"
    ):
        raise ValueError("worktool sweep artifact schema/status/profile")
    source = artifact.get("source_lock")
    if not isinstance(source, dict):
        raise ValueError("worktool sweep artifact source lock missing")
    if (
        str(source.get("execution_library_sha256", "")).lower()
        != execution_library_sha256
        or str(source.get("pose_library_sha256", "")).lower()
        != pose_library_sha256
    ):
        raise ValueError("worktool sweep artifact source SHA drift")


def _validate_return_transition_source_lock(
    *,
    path: Path,
    execution_library_sha256: str,
) -> None:
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(
            "return transition artifact is not valid JSON"
        ) from exc
    if not isinstance(artifact, dict):
        raise ValueError(
            "return transition artifact schema/status/profile"
        )
    distance = artifact.get("distance_contract", {})
    source = artifact.get("source_lock", {})
    if (
        artifact.get("schema")
        != "strict_train_coverage_return_transition_library_v1"
        or artifact.get("status") != "completed"
        or not isinstance(distance, dict)
        or distance.get("profile")
        != "strict_train_return_start_reachability_11d_v1"
    ):
        raise ValueError(
            "return transition artifact schema/status/profile"
        )
    if (
        not isinstance(source, dict)
        or str(source.get("execution_library_sha256", "")).lower()
        != execution_library_sha256
    ):
        raise ValueError(
            "return transition artifact execution library SHA drift"
        )


def _validate_base_a0_contract(config: dict[str, Any]) -> None:
    task = config.get("task")
    policy = config.get("policy")
    if not isinstance(task, dict) or not isinstance(policy, dict):
        raise ValueError("base A0 config is missing task/policy mappings")
    if tuple(task.get("camera_names", ())) != (
        "stick_up",
        "stick_down",
        "eye_left",
        "eye_right",
    ):
        raise ValueError("base A0 camera order changed")
    act = dict(policy.get("act_params", {}) or {})
    if (
        int(act.get("temporal_agg_window", -1)) != 100
        or str(act.get("temporal_agg_weight_order", ""))
        != "legacy_oldest_first"
        or float(act.get("temporal_agg_decay", float("nan"))) != 0.01
    ):
        raise ValueError("base A0 temporal aggregation contract changed")
    planner = dict(policy.get("dig_cut_planner", {}) or {})
    if (
        str(planner.get("mode", "")) != "operator_prior_sweep_belief"
        or str(planner.get("fallback_mode", "")) != "raise"
    ):
        raise ValueError("base A0 coverage planner contract changed")
    wall = dict(
        dict(planner.get("coverage", {}) or {}).get(
            "wall_safety",
            {},
        )
        or {}
    )
    if not bool(wall.get("enabled", False)):
        raise ValueError("exact-tuple eval requires A0 wall safety")
    box = dict(policy.get("box_emptying", {}) or {})
    if not bool(box.get("safety_enabled", False)):
        raise ValueError("exact-tuple eval requires typed safety")


def _validate_locked_a0_fields_unchanged(
    *,
    base: dict[str, Any],
    resolved: dict[str, Any],
) -> None:
    base_policy = base["policy"]
    policy = resolved["policy"]
    for key in (
        "act_params",
        "switch",
        "bootstrap_end_mode",
        "scripted_bootstrap",
        "dig_ckpt_path",
        "dig_ckpt_dir",
        "carry_ckpt_path",
        "carry_ckpt_dir",
        "dump_ckpt_path",
        "dump_ckpt_dir",
        "return_ckpt_path",
        "return_ckpt_dir",
    ):
        if policy.get(key) != base_policy.get(key):
            raise ValueError(f"A0 locked policy field changed: {key}")
    if resolved["task"]["camera_names"] != base["task"]["camera_names"]:
        raise ValueError("A0 locked camera order changed")
    if resolved.get("boundary") != base.get("boundary"):
        raise ValueError("A0 locked boundary contract changed")
    base_box = base_policy["box_emptying"]
    box = policy["box_emptying"]
    for key in ("carry_start_envelope", "safety", "safety_enabled"):
        if box.get(key) != base_box.get(key):
            raise ValueError(f"A0 locked box contract changed: {key}")
    base_coverage = base_policy["dig_cut_planner"]["coverage"]
    coverage = policy["dig_cut_planner"]["coverage"]
    for key, value in base_coverage.items():
        if key == "actual_tuple_execution_library":
            continue
        if coverage.get(key) != value:
            raise ValueError(f"A0 locked coverage field changed: {key}")


__all__ = [
    "BOUNDED_VALIDATION_SCHEMA",
    "EXECUTION_CONTRACT_VARIANT",
    "PURPOSE_BOUNDED_ONE_DIG",
    "PURPOSE_FUNCTIONAL_1X10",
    "PURPOSE_FUNCTIONAL_3X10",
    "SUPPORTED_PURPOSES",
    "build_coverage_execution_eval_config",
]
