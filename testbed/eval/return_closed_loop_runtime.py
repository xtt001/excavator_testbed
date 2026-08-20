"""File-backed runtime wiring for the bounded Return-only probe."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from testbed.backends.agx.backend import AgxSimBackend
from testbed.data.recorded_return_closed_loop_fixture import (
    load_frozen_recorded_return_closed_loop_fixture_set,
)
from testbed.data.schema import (
    ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX,
    ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX,
)
from testbed.eval.return_closed_loop_causal_contract import (
    RETURN_FIXTURE_FLOAT_ATOL,
    ReturnTargetEnvelope,
    assess_return_target_envelope,
    build_return_closed_loop_causal_contract,
)
from testbed.eval.return_closed_loop_preflight import file_sha256
from testbed.eval.return_closed_loop_probe import run_return_closed_loop_probe
from testbed.policies.act.inference import (
    build_act_adapter_config,
    load_act_policy,
)

DEFAULT_UNITY_REPO = Path("/home/pingfan/AGXUnityE85ExcavatorSim")


def build_current_return_closed_loop_runtime_lock(
    *,
    stage_a_v3_root: str | Path,
    return_validation_path: str | Path,
    unity_repo: str | Path = DEFAULT_UNITY_REPO,
) -> dict[str, Any]:
    """Build a read-only lock that explicitly records current blockers."""

    stage_root = Path(stage_a_v3_root).expanduser().resolve(strict=True)
    stage_manifest_path = (stage_root / "manifest.json").resolve(strict=True)
    stage_manifest = _read_json(stage_manifest_path)
    source = _mapping(stage_manifest.get("source_lineage"), "source_lineage")
    artifacts = _mapping(
        source.get("checkpoints_and_stats"), "checkpoints_and_stats"
    )
    return_artifacts = _mapping(artifacts.get("return"), "return artifacts")
    return_training_config = _verified_source_artifact(
        source.get("return_training_config"),
        "return_training_config",
    )

    validation_path = Path(return_validation_path).expanduser().resolve(strict=True)
    validation = _read_json(validation_path)
    metric = _validate_return_validation_artifact(validation)
    threshold = [float(value) for value in metric["discontinuity_threshold"]]
    fixture_set = load_frozen_recorded_return_closed_loop_fixture_set(
        stage_a_v3_root=stage_root
    )
    reset_context = _mapping(
        fixture_set.source_lineage.get("recorded_reset_context"),
        "recorded_reset_context",
    )
    scene_identity = str(reset_context["unity_scene_id"])
    scene_id, separator, scene_sha = scene_identity.partition("@sha256:")
    if not separator or len(scene_sha) != 64:
        raise ValueError("recorded Unity scene identity lacks SHA-256")

    python_root = Path(__file__).resolve().parents[2]
    unity_root = Path(unity_repo).expanduser().resolve(strict=True)
    unity_head = _git_output(unity_root, "rev-parse", "HEAD")
    unity_clean = not bool(_git_output(unity_root, "status", "--short"))
    recorded_hdf5 = _mapping(
        fixture_set.source_lineage.get("rollout_hdf5"), "rollout_hdf5"
    )
    recorded_metadata = _recorded_unity_metadata(recorded_hdf5["path"])
    source_rebuildable = bool(
        not recorded_metadata["unity_git_dirty"]
        and unity_clean
        and unity_head == recorded_metadata["unity_git_commit"]
    )
    return {
        "schema": "strict18_return_closed_loop_runtime_lock_v1",
        "source_sha": _git_output(python_root, "rev-parse", "HEAD"),
        "runtime_build_id": str(reset_context["runtime_build_id"]),
        "scene_id": scene_id,
        "scene_sha256": scene_sha,
        "camera_names": list(fixture_set.camera_names),
        "action_order": list(reset_context["action_order"]),
        "qpos_order": list(reset_context["qpos_order"]),
        "qvel_order": list(reset_context["qvel_order"]),
        "return_checkpoint": dict(
            _mapping(return_artifacts["checkpoint"], "Return checkpoint")
        ),
        "return_stats": dict(
            _mapping(return_artifacts["dataset_stats"], "Return stats")
        ),
        "return_training_config": return_training_config,
        "stage_a_v3_manifest": _file_record(stage_manifest_path),
        "return_validation": _file_record(validation_path),
        "qpos_atol": RETURN_FIXTURE_FLOAT_ATOL,
        "qvel_atol": RETURN_FIXTURE_FLOAT_ATOL,
        "action_discontinuity_threshold": threshold,
        "unity_worktree_clean": unity_clean,
        "unity_source_rebuildable": source_rebuildable,
        "qvel_fixture_application_supported": False,
        "applied_action_telemetry_confirmed": False,
        "atomic_action_limit_telemetry_confirmed": False,
        "full_state_snapshot_restore_supported": False,
        "deterministic_physics_seed_confirmed": False,
        "terrain_state_restore_supported": False,
        "official_handoff_evaluator_confirmed": False,
        "lineage": {
            "stage_a_v3_manifest": _file_record(stage_manifest_path),
            "return_validation": _file_record(validation_path),
            "action_discontinuity_threshold_definition": str(
                metric.get("jitter_and_discontinuity_definition", "")
            ),
            "unity_current_head": unity_head,
            "unity_recorded_head": recorded_metadata["unity_git_commit"],
            "unity_recorded_dirty": recorded_metadata["unity_git_dirty"],
            "source_rebuildable": source_rebuildable,
            "capability_assessment": (
                "current_protocol_has_no_actual_qvel/full_state/terrain_restore_"
                "or_atomic_applied_action_limit_telemetry"
            ),
        },
    }


def run_return_closed_loop_probe_from_files(
    *,
    stage_a_v3_root: str | Path,
    return_training_config_path: str | Path,
    runtime_lock_path: str | Path,
    output_root: str | Path,
    execute: bool = False,
    device: str = "cuda",
    host: str = "127.0.0.1",
    port: int = 5057,
    timeout_s: float = 10.0,
    official_handoff_evaluator: Callable[[Mapping[str, Any], Mapping[str, Any]], Any]
    | None = None,
) -> dict[str, Any]:
    """Load frozen sources and run preflight, with motion opt-in only."""

    fixture_set = load_frozen_recorded_return_closed_loop_fixture_set(
        stage_a_v3_root=stage_a_v3_root
    )
    causal_contract = build_return_closed_loop_causal_contract(fixture_set)
    runtime_lock = _read_json(runtime_lock_path)
    _require_artifact_match(
        Path(stage_a_v3_root).expanduser().resolve(strict=True) / "manifest.json",
        runtime_lock.get("stage_a_v3_manifest"),
        "stage_a_v3_manifest",
    )
    _require_artifact_match(
        Path(return_training_config_path).expanduser().resolve(strict=True),
        runtime_lock.get("return_training_config"),
        "return_training_config",
    )
    if official_handoff_evaluator is None:
        runtime_lock["official_handoff_evaluator_confirmed"] = False
    training_config = _read_yaml(return_training_config_path)
    policy_factory = _ReturnPolicyFactory(
        training_config=training_config,
        runtime_lock=runtime_lock,
        device=device,
    )

    def backend_factory(_: Mapping[str, Any]) -> AgxSimBackend:
        return AgxSimBackend(
            host=str(host),
            port=int(port),
            timeout_s=float(timeout_s),
            task_name=str(
                training_config.get("task", {}).get(
                    "task_name", "agx_excavation_teleop"
                )
            ),
            reset_terrain=True,
            reset_pose=True,
        )

    return run_return_closed_loop_probe(
        causal_contract=causal_contract,
        fixture_set=fixture_set,
        runtime_lock=runtime_lock,
        output_root=output_root,
        execute=execute,
        backend_factory=backend_factory,
        policy_factory=policy_factory,
        handoff_evaluator=(
            official_handoff_evaluator or _observe_direct_geometry_only
        ),
    )


class _ReturnPolicyFactory:
    """Load an independent Return-only ACT instance for every executed arm."""

    def __init__(
        self,
        *,
        training_config: Mapping[str, Any],
        runtime_lock: Mapping[str, Any],
        device: str,
    ) -> None:
        task = _mapping(training_config.get("task"), "task")
        policy = _mapping(training_config.get("policy"), "policy")
        low_dim_keys = [str(value) for value in policy.get("low_dim_keys", ())]
        if low_dim_keys != [
            "qpos",
            "qvel",
            "return_start_envelope_tokens_v1",
        ]:
            raise ValueError("Return probe training config low_dim_keys drifted")
        self._policy_config = build_act_adapter_config(
            config=training_config,
            camera_names=[str(value) for value in task["camera_names"]],
            equipment_model=str(task["equipment_model"]),
            max_episode_len=int(task["episode_len"]),
            low_dim_keys=low_dim_keys,
            act_params=_mapping(policy.get("act_params", {}), "act_params"),
            outcome_head_config=dict(policy.get("outcome_head", {}) or {}),
            image_mask_config=dict(policy.get("image_mask", {}) or {}),
            supervision_keys=[
                str(value) for value in policy.get("supervision_keys", ())
            ],
        )
        self._checkpoint = Path(
            str(_mapping(runtime_lock["return_checkpoint"], "checkpoint")["path"])
        )
        self._stats = Path(
            str(_mapping(runtime_lock["return_stats"], "stats")["path"])
        )
        self._device = str(device)

    def __call__(self, arm: Mapping[str, Any]) -> Any:
        if arm.get("allowed_primitive") != "return":
            raise ValueError("Return policy factory received a non-Return arm")
        return load_act_policy(
            ckpt_path=self._checkpoint,
            policy_config=self._policy_config,
            norm_stats_path=self._stats,
            temporal_agg=True,
            device=self._device,
        )


def _observe_direct_geometry_only(
    obs: Mapping[str, Any],
    arm: Mapping[str, Any],
) -> dict[str, Any]:
    envelope = ReturnTargetEnvelope(**dict(arm["target_envelope"]))
    env = np.asarray(obs.get("env_state"), dtype=np.float32).reshape(-1)
    assessment = assess_return_target_envelope(
        envelope=envelope,
        long_norm=float(env[ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX]),
        short_norm=float(env[ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX]),
        local_depth_m=float(env[ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX]),
        qpos=obs.get("qpos"),
        qvel=obs.get("qvel"),
        dig_contact=bool(
            env[ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX] >= 0.5
        ),
    )
    return {
        "would_handoff": False,
        "official_handoff_ready": None,
        "official_handoff_evaluator_available": False,
        "direct_token_geometry": assessment.as_dict(),
        "evidence_boundary": (
            "direct token geometry is not the resolved official handoff gate"
        ),
    }


def _read_json(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve(strict=True)
    value = json.loads(resolved.read_text(encoding="utf-8"))
    return dict(_mapping(value, str(resolved)))


def _read_yaml(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve(strict=True)
    value = yaml.safe_load(resolved.read_text(encoding="utf-8")) or {}
    return dict(_mapping(value, str(resolved)))


def _recorded_unity_metadata(hdf5_path: str | Path) -> dict[str, Any]:
    import h5py

    with h5py.File(Path(hdf5_path), "r") as handle:
        attrs = handle["metadata"].attrs
        return {
            "unity_git_commit": str(attrs["unity_git_commit"]),
            "unity_git_dirty": bool(int(attrs["unity_git_dirty"])),
        }


def _validate_return_validation_artifact(
    value: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Accept only the frozen source-disjoint Return validation contract."""

    if value.get("schema") != "return_temporal_dispatch_validation_artifact_v1":
        raise ValueError("Return validation schema mismatch")
    if value.get("primitive") != "return":
        raise ValueError("Return validation primitive mismatch")
    if value.get("target_stage_a_failures_used") is not False:
        raise ValueError("Return validation must not use target failures")
    scope = _mapping(value.get("input_scope"), "Return validation input_scope")
    expected_scope = {
        "fit_partition": "strict_train",
        "evaluation_partition": "held_out_source_disjoint_return",
        "counterfactual_tokens": "real_held_validation_tokens_only",
        "stage_a_artifact_input_accepted": False,
        "target_rollout_input_accepted": False,
    }
    for field, expected in expected_scope.items():
        if scope.get(field) != expected:
            raise ValueError(
                f"Return validation input_scope.{field} is not frozen"
            )
    selection = _mapping(
        value.get("selection"), "Return validation selection"
    )
    if (
        selection.get("runtime_default_changed") is not False
        or selection.get("selected_strategy_id") is not None
        or selection.get("candidate_frozen_for_opt_in_shadow_only") is not False
    ):
        raise ValueError("Return validation must retain legacy with no candidate")
    verification = _mapping(
        value.get("policy_verification"),
        "Return validation policy_verification",
    )
    if verification.get("all_pairs_passed") is not True:
        raise ValueError("Return validation policy verification did not pass")
    metric = _mapping(value.get("metric_contract"), "metric_contract")
    if metric.get("jitter_and_discontinuity_definition") != (
        "strict_train_action_delta_abs_p99_per_axis"
    ):
        raise ValueError("Return validation discontinuity definition drifted")
    threshold = np.asarray(
        metric.get("discontinuity_threshold"), dtype=np.float64
    ).reshape(-1)
    if (
        threshold.shape != (4,)
        or not np.isfinite(threshold).all()
        or np.any(threshold <= 0.0)
    ):
        raise ValueError("Return validation discontinuity threshold is not 4D")
    return metric


def _verified_source_artifact(value: Any, label: str) -> dict[str, Any]:
    record = dict(_mapping(value, label))
    path = Path(str(record.get("path", ""))).expanduser().resolve(strict=True)
    expected_sha = str(record.get("sha256", ""))
    actual_sha = file_sha256(path)
    if len(expected_sha) != 64 or actual_sha != expected_sha:
        raise ValueError(f"{label} SHA-256 mismatch")
    return {
        "path": str(path),
        "sha256": actual_sha,
        "size_bytes": path.stat().st_size,
    }


def _file_record(path: Path) -> dict[str, Any]:
    resolved = path.expanduser().resolve(strict=True)
    return {
        "path": str(resolved),
        "sha256": file_sha256(resolved),
        "size_bytes": resolved.stat().st_size,
    }


def _require_artifact_match(path: Path, value: Any, label: str) -> None:
    record = _mapping(value, f"runtime_lock.{label}")
    expected_sha = str(record.get("sha256", ""))
    if len(expected_sha) != 64 or file_sha256(path) != expected_sha:
        raise ValueError(f"{label} disagrees with runtime lock")


def _git_output(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be a mapping")
    return value


__all__ = [
    "DEFAULT_UNITY_REPO",
    "build_current_return_closed_loop_runtime_lock",
    "run_return_closed_loop_probe_from_files",
]
