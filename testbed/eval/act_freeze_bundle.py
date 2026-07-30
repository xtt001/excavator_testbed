"""Gate and freeze a four-primitive ACT bundle after real Unity validation."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

FREEZE_BUNDLE_SCHEMA = "frozen_four_primitive_act_bundle_v1"
VALIDATION_SCHEMA = "act_unity_closed_loop_validation_v1"
PRIMITIVES = ("dig", "carry", "dump", "return")


class ActFreezeGateError(RuntimeError):
    """Raised when a model or real closed-loop freeze prerequisite fails."""


def build_frozen_act_bundle(
    *,
    primitive_artifacts: Mapping[str, Mapping[str, Any]],
    validation_rollouts: Sequence[Mapping[str, Any]],
    data_lineage_path: str | Path,
    output_path: str | Path,
) -> dict[str, Any]:
    """Validate the locked 3x10 gate and write one no-overwrite bundle."""

    destination = Path(output_path)
    if destination.exists():
        raise FileExistsError(f"freeze bundle already exists: {destination}")
    lineage_path = _required_file(data_lineage_path, "data_lineage")
    models = _validate_primitive_artifacts(primitive_artifacts)
    rollout_records, unity = _validate_rollouts(validation_rollouts)
    bundle: dict[str, Any] = {
        "schema": FREEZE_BUNDLE_SCHEMA,
        "source": "strict18_four_primitive_act_real_unity_freeze_gate",
        "status": "frozen",
        "gate": {
            "passed": True,
            "independent_reset_count": 3,
            "cycles_per_reset": 10,
            "min_completed_full_cycles": 9,
            "min_effective_move_cycles": 8,
            "min_remaining_mass_drop_fraction": 0.30,
            "max_four_camera_inference_p95_ms": 50.0,
            "required_zero_counts": ["wall_contact", "stuck", "timeout"],
        },
        "primitives": models,
        "data_lineage": {
            "path": str(lineage_path.resolve()),
            "sha256": _sha256(lineage_path),
        },
        "unity": unity,
        "closed_loop_validation_rollouts": rollout_records,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(bundle, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return bundle


def _validate_primitive_artifacts(
    primitive_artifacts: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    if set(primitive_artifacts) != set(PRIMITIVES):
        raise ActFreezeGateError("four_primitive_inventory_mismatch")
    result: dict[str, dict[str, Any]] = {}
    for primitive in PRIMITIVES:
        artifact = primitive_artifacts[primitive]
        checkpoint = _required_file(
            artifact.get("checkpoint_path"),
            f"{primitive}.checkpoint",
        )
        if checkpoint.name != "policy_best.ckpt":
            raise ActFreezeGateError(
                f"{primitive}:checkpoint_must_be_policy_best"
            )
        run_metadata_path = _required_file(
            artifact.get("run_metadata_path"),
            f"{primitive}.run_metadata",
        )
        try:
            run_metadata = json.loads(
                run_metadata_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise ActFreezeGateError(
                f"{primitive}:run_metadata_invalid"
            ) from exc
        if not isinstance(run_metadata, Mapping) or run_metadata.get("status") != "completed":
            raise ActFreezeGateError(
                f"{primitive}:run_metadata_not_completed"
            )
        paths = {
            name: _required_file(artifact.get(f"{name}_path"), f"{primitive}.{name}")
            for name in ("stats", "resolved_config", "split")
        }
        result[primitive] = {
            "checkpoint_path": str(checkpoint.resolve()),
            "checkpoint_sha256": _sha256(checkpoint),
            "run_metadata_path": str(run_metadata_path.resolve()),
            "run_metadata_sha256": _sha256(run_metadata_path),
            **{
                f"{name}_path": str(path.resolve())
                for name, path in paths.items()
            },
            **{
                f"{name}_sha256": _sha256(path)
                for name, path in paths.items()
            },
        }
    return result


def _validate_rollouts(
    rollouts: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    if len(rollouts) != 3:
        raise ActFreezeGateError("exactly_three_resets_required")
    reset_ids: set[str] = set()
    build_ids: set[str] = set()
    scene_ids: set[str] = set()
    records: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, raw in enumerate(rollouts):
        prefix = f"reset[{index}]"
        if raw.get("schema") != VALIDATION_SCHEMA:
            errors.append(f"{prefix}:validation_schema_mismatch")
            continue
        reset_id = str(raw.get("reset_id", "")).strip()
        if not reset_id or reset_id in reset_ids:
            errors.append(f"{prefix}:independent_reset_id_invalid")
        reset_ids.add(reset_id)
        if int(raw.get("cycle_count", -1)) != 10:
            errors.append(f"{prefix}:cycle_count_not_10")
        if int(raw.get("completed_full_cycle_count", -1)) < 9:
            errors.append(f"{prefix}:completed_cycles_below_9")
        if int(raw.get("effective_move_cycle_count", -1)) < 8:
            errors.append(f"{prefix}:effective_cycles_below_8")
        initial_mass = _finite_float(
            raw.get("initial_remaining_mass_kg"),
            f"{prefix}:initial_mass_invalid",
        )
        final_mass = _finite_float(
            raw.get("final_remaining_mass_kg"),
            f"{prefix}:final_mass_invalid",
        )
        if initial_mass <= 0.0 or 1.0 - final_mass / initial_mass < 0.30 - 1.0e-12:
            errors.append(f"{prefix}:remaining_mass_drop_below_30pct")
        for field, reason in (
            ("wall_contact_count", "wall_contact_present"),
            ("stuck_count", "stuck_present"),
            ("timeout_count", "timeout_present"),
        ):
            if int(raw.get(field, -1)) != 0:
                errors.append(f"{prefix}:{reason}")
        latencies = np.asarray(
            raw.get("four_camera_inference_latency_ms", []),
            dtype=np.float64,
        ).reshape(-1)
        if latencies.size == 0 or not np.isfinite(latencies).all():
            errors.append(f"{prefix}:inference_latency_missing")
            inference_p95 = float("nan")
        else:
            inference_p95 = float(np.percentile(latencies, 95))
            if inference_p95 > 50.0:
                errors.append(f"{prefix}:inference_p95_above_50ms")
        artifact_path = _required_file(
            raw.get("artifact_path"),
            f"{prefix}.artifact",
        )
        build_id = str(raw.get("unity_build_id", "")).strip()
        scene_id = str(raw.get("scene_id", "")).strip()
        if not build_id or not scene_id:
            errors.append(f"{prefix}:unity_build_or_scene_missing")
        build_ids.add(build_id)
        scene_ids.add(scene_id)
        records.append(
            {
                **dict(raw),
                "artifact_path": str(artifact_path.resolve()),
                "artifact_sha256": _sha256(artifact_path),
                "remaining_mass_drop_fraction": 1.0 - final_mass / initial_mass,
                "four_camera_inference_p95_ms": inference_p95,
            }
        )
    if len(build_ids) != 1 or len(scene_ids) != 1:
        errors.append("unity_build_or_scene_mismatch")
    if errors:
        raise ActFreezeGateError(";".join(errors))
    return records, {
        "build_id": next(iter(build_ids)),
        "scene_id": next(iter(scene_ids)),
    }


def _required_file(value: Any, label: str) -> Path:
    if value is None or not str(value).strip():
        raise ActFreezeGateError(f"{label}_path_missing")
    path = Path(str(value)).expanduser()
    if not path.is_file():
        raise ActFreezeGateError(f"{label}_file_missing:{path}")
    return path


def _finite_float(value: Any, reason: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ActFreezeGateError(reason) from exc
    if not np.isfinite(parsed):
        raise ActFreezeGateError(reason)
    return parsed


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "ActFreezeGateError",
    "FREEZE_BUNDLE_SCHEMA",
    "VALIDATION_SCHEMA",
    "build_frozen_act_bundle",
]
