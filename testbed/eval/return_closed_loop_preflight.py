"""Pre-motion identity and fixture checks for Return closed-loop probes."""

from __future__ import annotations

import dataclasses
import hashlib
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

from testbed.data.camera_images import observation_camera_rgb
from testbed.data.recorded_return_closed_loop_fixture import (
    RecordedReturnImageLineage,
    RecordedReturnInitialObservation,
)
from testbed.eval.return_closed_loop_causal_contract import (
    ReturnFixtureApplicationCapabilities,
    ReturnFixtureAppliedState,
    assess_return_fixture_match,
)


class ReturnClosedLoopPreflightError(ValueError):
    """Raised when an input cannot satisfy the preflight data contract."""


def mapping_record(value: Any, label: str) -> Mapping[str, Any]:
    """Accept JSON mappings and contract dataclasses through one boundary."""

    as_dict = getattr(value, "as_dict", None)
    if callable(as_dict):
        value = as_dict()
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        value = dataclasses.asdict(value)
    if not isinstance(value, Mapping):
        raise ReturnClosedLoopPreflightError(
            f"{label} must be a mapping or dataclass"
        )
    return value


def object_record(value: Any) -> dict[str, Any]:
    """Project dataclass or protocol responses onto preflight fields."""

    if isinstance(value, Mapping):
        return dict(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    fields = (
        "runtime_build_id",
        "scene_id",
        "unity_scene_id",
        "scene_sha256",
        "unity_scene_sha256",
        "camera_names",
        "action_order",
        "qpos_order",
        "qvel_order",
    )
    return {
        field: getattr(value, field)
        for field in fields
        if hasattr(value, field)
    }


def observation(value: Any) -> dict[str, Any]:
    """Extract an observation mapping from a backend timestep."""

    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    result = getattr(value, "observation", None)
    if isinstance(result, Mapping):
        return dict(result)
    raise ReturnClosedLoopPreflightError(
        "backend result has no observation mapping"
    )


def step_action_telemetry(
    value: Any,
    *,
    action_dim: int = 4,
) -> dict[str, Any]:
    """Project atomic Unity applied-action and per-axis limit telemetry."""

    raw = getattr(value, "info", None)
    info = dict(raw) if isinstance(raw, Mapping) else {}
    applied = _optional_vector(info.get("applied_action"), action_dim)
    intervention = _optional_bool_vector(
        info.get("action_limit_intervention"), action_dim
    )
    return {
        "applied_action_available": applied is not None,
        "action_limit_intervention_available": intervention is not None,
        "applied_action": [] if applied is None else applied.astype(float).tolist(),
        "action_limit_intervention": (
            [] if intervention is None else intervention.astype(bool).tolist()
        ),
    }


def request_neutral_step_ack(
    backend: Any,
    *,
    action_dim: int = 4,
    atol: float = 1.0e-7,
) -> dict[str, Any]:
    """Send one zero STEP and require atomic telemetry to acknowledge it."""

    if backend is None:
        return {"acknowledged": False, "step_id": None}
    try:
        step = backend.step(np.zeros(action_dim, dtype=np.float32))
        obs = observation(step)
        telemetry = step_action_telemetry(step, action_dim=action_dim)
        applied = np.asarray(
            telemetry.get("applied_action", ()), dtype=np.float32
        ).reshape(-1)
        return {
            "acknowledged": bool(
                telemetry["applied_action_available"]
                and telemetry["action_limit_intervention_available"]
                and applied.shape == (action_dim,)
                and np.allclose(applied, 0.0, rtol=0.0, atol=float(atol))
            ),
            "step_id": int(obs.get("step_id", -1)),
            "observation": obs,
            "action_telemetry": telemetry,
        }
    except Exception as exc:
        return {
            "acknowledged": False,
            "step_id": None,
            "error": type(exc).__name__,
        }


def prepare_return_fixture(
    backend: Any,
    fixture: Mapping[str, Any],
) -> dict[str, Any]:
    """Reset and apply one qpos+qvel fixture without sending a non-zero action."""

    custom = getattr(backend, "prepare_fixture", None)
    if callable(custom):
        result = dict(mapping_record(custom(dict(fixture)), "prepare_fixture"))
        result["observation"] = observation(result.get("observation"))
        return result

    initial = mapping_record(
        fixture.get("initial_observation"), "initial_observation"
    )
    reset_ts = backend.reset(seed=int(fixture.get("seed", 1000)))
    reset_obs = observation(reset_ts)
    realigned = backend.realign_pose(
        np.asarray(initial["qpos"], dtype=np.float32),
        qvel=np.asarray(initial["qvel"], dtype=np.float32),
        burn_in_steps=0,
        reason=f"Return closed-loop fixture {fixture.get('fixture_id', '')}",
    )
    result_obs = observation(realigned)
    warnings = [
        str(item)
        for item in (
            result_obs.get("warnings", ())
            or getattr(realigned, "info", {}).get("warnings", ())
        )
    ]
    warning_text = " ".join(warnings).lower()
    return {
        "reset_applied": reset_obs.get("reset_applied") is True,
        "qpos_applied": (
            "qpos_status=ignored" not in warning_text
            and "qposapplied=false" not in warning_text
        ),
        "qvel_applied": (
            "qvel_status=applied" in warning_text
            or "qvelapplied=true" in warning_text
        ),
        "observation": result_obs,
        "warnings": warnings,
        "observable_terrain_available": bool(
            np.asarray(result_obs.get("env_state", ())).size >= 107
        ),
        "camera_observation_available": bool(
            result_obs.get("encoded_images") or result_obs.get("images")
        ),
        "scene_actual_applied": False,
        "physics_seed_actual_applied": False,
        "terrain_state_actual_applied": False,
    }


def get_info_blockers(
    observed: Mapping[str, Any],
    *,
    runtime_lock: Mapping[str, Any],
) -> list[str]:
    """Compare live GET_INFO identity to the frozen runtime lock."""

    blockers: list[str] = []
    aliases = {
        "runtime_build_id": ("runtime_build_id",),
        "scene_id": ("scene_id", "unity_scene_id"),
        "scene_sha256": ("scene_sha256", "unity_scene_sha256"),
        "camera_names": ("camera_names",),
        "action_order": ("action_order",),
        "qpos_order": ("qpos_order",),
        "qvel_order": ("qvel_order",),
    }
    for expected_field, names in aliases.items():
        actual = next(
            (observed[name] for name in names if name in observed),
            None,
        )
        expected = runtime_lock[expected_field]
        if isinstance(expected, list) and actual is not None:
            actual = [str(item) for item in actual]
        if actual != expected:
            blockers.append(f"get_info_{expected_field}_mismatch")
    return blockers


def fixture_application_blockers(
    prepared: Mapping[str, Any],
    *,
    fixture: Mapping[str, Any],
    runtime_lock: Mapping[str, Any],
) -> list[str]:
    """Require explicit application acknowledgement and observed state match."""

    blockers: list[str] = []
    if prepared.get("reset_applied") is not True:
        blockers.append("reset_not_applied")
    if prepared.get("qpos_applied") is not True:
        blockers.append("fixture_qpos_not_confirmed")
    if prepared.get("qvel_applied") is not True:
        blockers.append("fixture_qvel_not_confirmed")
    obs = observation(prepared.get("observation"))
    initial = mapping_record(
        fixture.get("initial_observation"), "initial_observation"
    )
    if not _allclose_vector(
        obs.get("qpos"),
        initial.get("qpos"),
        atol=float(runtime_lock["qpos_atol"]),
    ):
        blockers.append("fixture_qpos_mismatch")
    if not _allclose_vector(
        obs.get("qvel"),
        initial.get("qvel"),
        atol=float(runtime_lock["qvel_atol"]),
    ):
        blockers.append("fixture_qvel_mismatch")
    encoded = obs.get("encoded_images")
    images = obs.get("images")
    names = set(encoded) if isinstance(encoded, Mapping) else set()
    if not names and isinstance(images, Mapping):
        names = set(images)
    if names != set(runtime_lock["camera_names"]):
        blockers.append("fixture_camera_observation_mismatch")
    image_lineage = initial.get("image_lineage")
    if isinstance(image_lineage, list) and image_lineage:
        try:
            assessment = _strict_fixture_assessment(
                initial=initial,
                observation_value=obs,
                prepared=prepared,
                camera_names=runtime_lock["camera_names"],
            )
        except Exception as exc:
            blockers.append(
                f"fixture_strict_match_exception:{type(exc).__name__}"
            )
        else:
            blockers.extend(
                f"fixture_strict_match:{reason}"
                for reason in assessment.failures
            )
    return blockers


def _strict_fixture_assessment(
    *,
    initial: Mapping[str, Any],
    observation_value: Mapping[str, Any],
    prepared: Mapping[str, Any],
    camera_names: list[str],
) -> Any:
    lineage = tuple(
        RecordedReturnImageLineage(
            camera_name=str(item["camera_name"]),
            shape=tuple(int(value) for value in item["shape"]),
            encoded_jpeg_size_bytes=int(item["encoded_jpeg_size_bytes"]),
            encoded_jpeg_sha256=str(item["encoded_jpeg_sha256"]),
            rgb_sha256=str(item["rgb_sha256"]),
        )
        for item in initial["image_lineage"]
    )
    reference = RecordedReturnInitialObservation(
        action_step_id=int(initial["action_step_id"]),
        observation_step_id=int(initial["observation_step_id"]),
        hdf5_observation_index=int(initial["hdf5_observation_index"]),
        qpos=np.asarray(initial["qpos"], dtype=np.float32),
        qvel=np.asarray(initial["qvel"], dtype=np.float32),
        env_state=np.asarray(initial["env_state"], dtype=np.float32),
        image_lineage=lineage,
    )
    hashes = prepared.get("image_rgb_sha256")
    if not isinstance(hashes, Mapping):
        hashes = {
            name: hashlib.sha256(
                observation_camera_rgb(dict(observation_value), name).tobytes()
            ).hexdigest()
            for name in camera_names
        }
    applied = ReturnFixtureAppliedState(
        qpos=np.asarray(observation_value.get("qpos"), dtype=np.float32),
        qvel=np.asarray(observation_value.get("qvel"), dtype=np.float32),
        env_state=np.asarray(observation_value.get("env_state"), dtype=np.float32),
        image_rgb_sha256={str(key): str(value) for key, value in hashes.items()},
    )
    capabilities = ReturnFixtureApplicationCapabilities(
        full_reset_applied=prepared.get("reset_applied") is True,
        qpos_actual_applied=prepared.get("qpos_applied") is True,
        qvel_actual_applied=prepared.get("qvel_applied") is True,
        observable_terrain_available=(
            prepared.get("observable_terrain_available") is True
        ),
        camera_observation_available=(
            prepared.get("camera_observation_available") is True
        ),
        scene_actual_applied=prepared.get("scene_actual_applied") is True,
        physics_seed_actual_applied=(
            prepared.get("physics_seed_actual_applied") is True
        ),
        terrain_state_actual_applied=(
            prepared.get("terrain_state_actual_applied") is True
        ),
    )
    return assess_return_fixture_match(
        reference=reference,
        applied=applied,
        capabilities=capabilities,
    )


def static_preflight_blockers(
    *,
    git_state: Mapping[str, Any],
    runtime_lock: Mapping[str, Any],
    fixture_source_lineage: Mapping[str, Any] | None = None,
) -> list[str]:
    """Check source/artifact/capability locks before opening a policy."""

    blockers: list[str] = []
    if git_state.get("worktree_clean") is not True:
        blockers.append("python_worktree_not_clean")
    if str(git_state.get("git_head", "")) != str(runtime_lock["source_sha"]):
        blockers.append("python_source_sha_mismatch")
    capability_fields = {
        "unity_worktree_clean": "unity_worktree_not_clean",
        "unity_source_rebuildable": "unity_source_not_rebuildable",
        "qvel_fixture_application_supported": (
            "qvel_fixture_application_not_supported"
        ),
        "applied_action_telemetry_confirmed": (
            "applied_action_telemetry_not_confirmed"
        ),
        "atomic_action_limit_telemetry_confirmed": (
            "atomic_action_limit_telemetry_not_confirmed"
        ),
        "full_state_snapshot_restore_supported": (
            "full_state_snapshot_restore_not_supported"
        ),
        "deterministic_physics_seed_confirmed": (
            "deterministic_physics_seed_not_confirmed"
        ),
        "terrain_state_restore_supported": (
            "terrain_state_restore_not_supported"
        ),
        "official_handoff_evaluator_confirmed": (
            "official_handoff_evaluator_not_confirmed"
        ),
    }
    for field, blocker in capability_fields.items():
        if runtime_lock.get(field) is not True:
            blockers.append(blocker)
    lineage = fixture_source_lineage or {}
    reset_context = lineage.get("recorded_reset_context", {})
    if not isinstance(reset_context, Mapping):
        reset_context = {}
    full_snapshot = reset_context.get("full_terrain_snapshot_recorded") is True
    deterministic_soil_seed = (
        reset_context.get("deterministic_soil_seed_recorded") is True
    )
    if not (full_snapshot or deterministic_soil_seed):
        blockers.append("source_terrain_restore_identity_not_recorded")
    restore_evidence = reset_context.get("terrain_restore_evidence")
    if restore_evidence not in {
        "full_state_restorable",
        "deterministic_soil_seed_restorable",
    }:
        blockers.append("source_terrain_state_not_restorable")
    for field in (
        "return_checkpoint",
        "return_stats",
        "return_training_config",
        "stage_a_v3_manifest",
        "return_validation",
    ):
        record = runtime_lock[field]
        path = Path(str(record["path"])).expanduser()
        if not path.is_file():
            blockers.append(f"{field}_missing")
        elif file_sha256(path) != str(record["sha256"]):
            blockers.append(f"{field}_sha256_mismatch")
    return blockers


def clean_code_record() -> dict[str, Any]:
    """Return the local Python source identity used immediately pre-motion."""

    root = Path(__file__).resolve().parents[2]
    return {
        "git_head": _git_output(root, "rev-parse", "HEAD"),
        "git_branch": _git_output(root, "branch", "--show-current"),
        "worktree_clean": not bool(_git_output(root, "status", "--short")),
    }


def finite_vector(value: Any, size: int, label: str) -> np.ndarray:
    try:
        array = np.asarray(value, dtype=np.float32).reshape(-1)
    except Exception as exc:
        raise ReturnClosedLoopPreflightError(f"{label} must be numeric") from exc
    if array.shape != (size,) or not np.isfinite(array).all():
        raise ReturnClosedLoopPreflightError(
            f"{label} must be a finite vector with width {size}"
        )
    return array


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _allclose_vector(actual: Any, expected: Any, *, atol: float) -> bool:
    try:
        left = np.asarray(actual, dtype=np.float64).reshape(-1)
        right = np.asarray(expected, dtype=np.float64).reshape(-1)
    except Exception:
        return False
    return bool(
        left.shape == right.shape
        and np.isfinite(left).all()
        and np.isfinite(right).all()
        and np.allclose(left, right, rtol=0.0, atol=atol)
    )


def _optional_vector(value: Any, size: int) -> np.ndarray | None:
    try:
        array = np.asarray(value, dtype=np.float32).reshape(-1)
    except Exception:
        return None
    if array.shape != (size,) or not np.isfinite(array).all():
        return None
    return array


def _optional_bool_vector(value: Any, size: int) -> np.ndarray | None:
    try:
        array = np.asarray(value).reshape(-1)
    except Exception:
        return None
    if array.shape != (size,) or array.dtype.kind not in {"b", "i", "u"}:
        return None
    numeric = array.astype(np.int64)
    if not bool(np.all((numeric == 0) | (numeric == 1))):
        return None
    return numeric.astype(np.bool_)


def _git_output(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


__all__ = [
    "ReturnClosedLoopPreflightError",
    "clean_code_record",
    "file_sha256",
    "finite_vector",
    "fixture_application_blockers",
    "get_info_blockers",
    "mapping_record",
    "object_record",
    "observation",
    "prepare_return_fixture",
    "request_neutral_step_ack",
    "step_action_telemetry",
    "static_preflight_blockers",
]
