"""Request-local A/B config invariants for wall-contact diagnostics."""

from __future__ import annotations

import copy
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from testbed.eval.wall_contact_artifact_io import (
    artifact_ref,
    json_sha256,
    locked_ref,
    mapping,
    mapping_mut,
    required_file,
)


class WallContactConfigError(RuntimeError):
    """Raised when the frozen A0 or paired single-factor contract drifts."""


def effective_action_scale(policy: Mapping[str, Any]) -> dict[str, Any]:
    configured = policy.get("action_scale")
    if configured is None:
        return {
            "configured": None,
            "effective": [1.0, 1.0, 1.0, 1.0],
            "source": "runtime_identity_no_action_scale_consumer",
        }
    if (
        not isinstance(configured, list)
        or len(configured) != 4
        or any(not isinstance(item, (int, float)) for item in configured)
    ):
        raise WallContactConfigError("base_action_scale_invalid")
    return {
        "configured": copy.deepcopy(configured),
        "effective": [1.0, 1.0, 1.0, 1.0],
        "source": "runtime_identity_no_action_scale_consumer",
    }


def base_config_source_lock(
    base: Mapping[str, Any],
    *,
    base_config_path: Path,
) -> dict[str, Any]:
    policy = mapping(base.get("policy"), "policy")
    checkpoints = {
        primitive: artifact_ref(
            required_file(
                policy.get(f"{primitive}_ckpt_path"),
                f"{primitive}_checkpoint",
            )
        )
        for primitive in ("dig", "carry", "dump", "return")
    }
    value = {
        "base_config": artifact_ref(base_config_path),
        "checkpoints": checkpoints,
        "action_scale": effective_action_scale(policy),
    }
    value["contract_sha256"] = json_sha256(value)
    return value


def validate_base_config_source_lock(value: Mapping[str, Any]) -> None:
    locked_ref(mapping(value.get("base_config"), "base_config"), "base_config")
    checkpoints = mapping(value.get("checkpoints"), "checkpoints")
    for primitive in ("dig", "carry", "dump", "return"):
        locked_ref(
            mapping(checkpoints.get(primitive), f"{primitive}_checkpoint"),
            f"{primitive}_checkpoint",
        )
    expected = str(value.get("contract_sha256", ""))
    unlocked = {key: item for key, item in value.items() if key != "contract_sha256"}
    if json_sha256(unlocked) != expected:
        raise WallContactConfigError("base_config_source_lock_drift")


def validate_base_config(base: Mapping[str, Any]) -> None:
    task = mapping(base.get("task"), "task")
    if tuple(task.get("camera_names", ())) != (
        "stick_up",
        "stick_down",
        "eye_left",
        "eye_right",
    ):
        raise WallContactConfigError("base_four_camera_contract_drift")
    policy = mapping(base.get("policy"), "policy")
    act = mapping(policy.get("act_params"), "act_params")
    if (
        int(act.get("temporal_agg_window", -1)) != 100
        or act.get("temporal_agg_weight_order") != "legacy_oldest_first"
    ):
        raise WallContactConfigError("base_temporal_contract_drift")
    for primitive in ("dig", "carry", "dump", "return"):
        if not str(policy.get(f"{primitive}_ckpt_path", "")).strip():
            raise WallContactConfigError(f"base_{primitive}_checkpoint_missing")
    box = mapping(policy.get("box_emptying"), "box_emptying")
    safety = mapping(box.get("safety"), "box_emptying.safety")
    if float(safety.get("wall_high_force_n", math.nan)) != 100_000.0:
        raise WallContactConfigError("base_wall_force_contract_drift")
    switch = mapping(policy.get("switch"), "switch")
    if int(switch.get("return_max_steps", -1)) <= 0:
        raise WallContactConfigError("base_return_timeout_missing")
    effective_action_scale(policy)


def normalized_ab_config(config: Mapping[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(dict(config))
    eval_config = mapping_mut(value, "eval")
    for key in (
        "results_dir",
        "video_dir",
        "rollout_log_dir",
        "hdf5_dir",
    ):
        eval_config[key] = "<output>"
    metadata = mapping_mut(eval_config, "record_hdf5_metadata")
    for key in (
        "contact_semantics_condition",
        "contact_semantics_attempt_id",
        "contact_semantics_sequence_index",
    ):
        metadata[key] = "<condition>"
    safety = mapping_mut(
        mapping_mut(mapping_mut(value, "policy"), "box_emptying"),
        "safety",
    )
    safety["wall_first_touch_mode"] = "<condition>"
    return value


def validate_wall_contact_resolved_config(
    *,
    configured: Mapping[str, Any],
    resolved: Mapping[str, Any],
    run_root: Path,
) -> None:
    """Allow only the documented ``testbed.cli.eval --output-dir`` overlay."""

    expected = copy.deepcopy(dict(configured))
    eval_config = mapping_mut(expected, "eval")
    results = run_root / "results"
    eval_config.update(
        {
            "results_dir": str(results),
            "video_dir": str(run_root / "videos"),
            "rollout_log_dir": str(results / "rollouts"),
            "hdf5_dir": str(results / "hdf5_rollouts"),
        }
    )
    if dict(resolved) != expected:
        raise WallContactConfigError("resolved_config_semantic_drift")


def locked_config_contract(config: Mapping[str, Any]) -> dict[str, Any]:
    task = mapping(config.get("task"), "task")
    policy = mapping(config.get("policy"), "policy")
    safety = copy.deepcopy(
        dict(
            mapping(
                mapping(policy.get("box_emptying"), "box_emptying").get("safety"),
                "safety",
            )
        )
    )
    safety.pop("wall_first_touch_mode", None)
    return {
        "camera_names": copy.deepcopy(task.get("camera_names")),
        "action_scale": effective_action_scale(policy),
        "checkpoints": {
            key: policy.get(key)
            for key in (
                "dig_ckpt_path",
                "carry_ckpt_path",
                "dump_ckpt_path",
                "return_ckpt_path",
            )
        },
        "act_params": copy.deepcopy(policy.get("act_params")),
        "dig_cut_planner": copy.deepcopy(policy.get("dig_cut_planner")),
        "switch": copy.deepcopy(policy.get("switch")),
        "boundary": copy.deepcopy(config.get("boundary")),
        "safety": safety,
        "episode_len": task.get("episode_len"),
    }


def paired_ab_configs(
    *,
    base: Mapping[str, Any],
    locked: Mapping[str, Any],
    destination: Path,
    sequence: Sequence[tuple[int, str]],
    schedule_schema: str,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Build the six request-local configs and their exactly-once schedule."""

    configs: dict[str, dict[str, Any]] = {}
    attempts: list[dict[str, Any]] = []
    for sequence_index, (seed, condition) in enumerate(sequence, start=1):
        pair_id = f"seed_{seed}"
        attempt_id = f"{pair_id}_{condition}"
        run_root = destination / "paired_ab" / "runs" / attempt_id
        config = copy.deepcopy(dict(base))
        eval_config = mapping_mut(config, "eval")
        eval_config.update(
            {
                "num_rollouts": 1,
                "seed": int(seed),
                "target_cycle_gate": 2,
                "target_cycle_gate_terminal_hold_steps": 0,
                "no_overwrite": True,
                "results_dir": str(run_root / "results"),
                "video_dir": str(run_root / "videos"),
                "save_rollout_logs": True,
                "stream_rollout_logs": True,
                "rollout_log_dir": str(run_root / "results" / "rollouts"),
                "record_hdf5": False,
                "hdf5_dir": str(run_root / "disabled_hdf5"),
            }
        )
        metadata = eval_config.setdefault("record_hdf5_metadata", {})
        if not isinstance(metadata, dict):
            raise WallContactConfigError("record_hdf5_metadata_invalid")
        metadata.update(
            {
                "validation_schema": "wall_contact_paired_ab_attempt_v1",
                "contact_semantics_condition": condition,
                "contact_semantics_pair_id": pair_id,
                "contact_semantics_attempt_id": attempt_id,
                "contact_semantics_sequence_index": sequence_index,
                "contact_semantics_reset_seed": int(seed),
                "diagnostic_only": True,
                "promotion_eligible": False,
                "frozen_target_handoff_sha256": locked["source_lock"][
                    "frozen_target_handoff"
                ]["sha256"],
                "expected_reset_state_sha256": locked["source_lock"][
                    "expected_reset_state"
                ]["sha256"],
            }
        )
        policy = mapping_mut(config, "policy")
        policy.setdefault(
            "action_scale",
            effective_action_scale(policy)["effective"],
        )
        planner = mapping_mut(policy, "dig_cut_planner")
        coverage = mapping_mut(planner, "coverage")
        exact_library = coverage.setdefault(
            "actual_tuple_execution_library",
            {},
        )
        if not isinstance(exact_library, dict):
            raise WallContactConfigError("exact_library_config_invalid")
        execution_ref = locked["source_lock"]["execution_library"]
        for key, value in (
            ("path", execution_ref["path"]),
            ("artifact_sha256", execution_ref["sha256"]),
        ):
            if key in exact_library and exact_library[key] != value:
                raise WallContactConfigError(f"exact_library_{key}_source_drift")
            exact_library[key] = value
        exact_library.update(
            {
                "enabled": True,
                "runtime_role": "diagnostic_legacy",
                "mode": "exact_k1",
                "missing_contract": "fail_closed",
            }
        )
        box = mapping_mut(policy, "box_emptying")
        bounded = box.setdefault("bounded_dig_probe_stop", {})
        if not isinstance(bounded, dict):
            raise WallContactConfigError("bounded_stop_config_invalid")
        bounded["enabled"] = False
        functional = box.setdefault("functional_cycle_gate", {})
        if not isinstance(functional, dict):
            raise WallContactConfigError("functional_gate_config_invalid")
        functional["enabled"] = False
        box["contact_semantics_one_cycle_validator"] = {
            "enabled": True,
            "diagnostic_only": True,
            "target_exemplar_id": "episode_168",
            "stop_on": ["target_dump_complete", "safety_terminal"],
        }
        safety = box.setdefault("safety", {})
        if not isinstance(safety, dict):
            raise WallContactConfigError("box_safety_config_invalid")
        safety["wall_contact_diagnostic_ab_enabled"] = True
        safety["wall_first_touch_mode"] = (
            "interrupt" if condition == "A" else "record_bucket_first_session"
        )
        config_path = destination / "paired_ab" / "configs" / f"{attempt_id}.yaml"
        configs[attempt_id] = config
        attempts.append(
            {
                "attempt_id": attempt_id,
                "pair_id": pair_id,
                "sequence_index": sequence_index,
                "seed": int(seed),
                "condition": condition,
                "wall_first_touch_mode": safety["wall_first_touch_mode"],
                "config_path": str(config_path),
                "run_root": str(run_root),
                "max_attempts": 1,
                "retry_allowed": False,
                "command_argv": [
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
                ],
            }
        )
    return configs, {
        "schema": schedule_schema,
        "status": "prepared",
        "diagnostic_only": True,
        "non_promotable": True,
        "attempt_count": len(attempts),
        "retry_allowed": False,
        "execution_order_is_mandatory": True,
        "target_contract": {
            "exemplar_id": "episode_168",
            "runtime_role": "diagnostic_legacy",
            "use_scope": "paired_ab_only",
            "production_lookup_allowed": False,
            "reset_checkpoint_semantics": "first_post_reset_control_step",
        },
        "attempts": attempts,
    }


__all__ = [
    "WallContactConfigError",
    "base_config_source_lock",
    "effective_action_scale",
    "locked_config_contract",
    "normalized_ab_config",
    "paired_ab_configs",
    "validate_base_config_source_lock",
    "validate_base_config",
    "validate_wall_contact_resolved_config",
]
