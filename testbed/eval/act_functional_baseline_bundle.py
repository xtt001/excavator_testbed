"""Release a functional-only four-primitive ACT bundle after the 3x10 gate."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from testbed.eval.act_functional_10cycle_validation import (
    ActFunctional10CycleValidationError,
    evaluate_act_functional_10cycle_records,
)

SCHEMA = "act_functional_baseline_bundle_v1"
PRIMITIVES = ("dig", "carry", "dump", "return")


class FunctionalBaselineBundleError(RuntimeError):
    """Raised when functional-only release evidence is incomplete."""


def build_functional_baseline_bundle(
    *,
    primitive_checkpoint_paths: Mapping[str, str | Path],
    validation_records: Sequence[Mapping[str, Any]],
    runtime_config_path: str | Path,
    runtime_code_paths: Sequence[str | Path],
    carry_start_envelope_path: str | Path,
    unity_build_id: str,
    unity_scene_id: str,
    output_path: str | Path,
) -> dict[str, Any]:
    """Validate and write a no-overwrite bundle that cannot unlock later stages."""

    destination = Path(output_path).expanduser()
    if destination.exists():
        raise FileExistsError(
            f"functional baseline bundle already exists: {destination}"
        )
    if set(primitive_checkpoint_paths) != set(PRIMITIVES):
        raise FunctionalBaselineBundleError(
            "four_primitive_checkpoint_inventory_mismatch"
        )
    checkpoints: dict[str, dict[str, str]] = {}
    for primitive in PRIMITIVES:
        checkpoint = _required_file(
            primitive_checkpoint_paths[primitive],
            f"{primitive}.checkpoint",
        )
        if checkpoint.name != "policy_best.ckpt":
            raise FunctionalBaselineBundleError(
                f"{primitive}:checkpoint_must_be_policy_best"
            )
        checkpoints[primitive] = _artifact(checkpoint)

    try:
        aggregate = evaluate_act_functional_10cycle_records(
            validation_records
        )
    except ActFunctional10CycleValidationError as exc:
        raise FunctionalBaselineBundleError(
            f"functional_3x10_gate_failed:{exc}"
        ) from exc
    rollout_artifacts = [
        _validation_artifact(record, index=index)
        for index, record in enumerate(validation_records)
    ]

    runtime_config = _required_file(runtime_config_path, "runtime_config")
    if not runtime_code_paths:
        raise FunctionalBaselineBundleError("runtime_code_paths_missing")
    runtime_code: list[dict[str, str]] = []
    seen_code_paths: set[Path] = set()
    for index, value in enumerate(runtime_code_paths):
        path = _required_file(value, f"runtime_code[{index}]")
        resolved = path.resolve()
        if resolved in seen_code_paths:
            raise FunctionalBaselineBundleError(
                "runtime_code_path_duplicate"
            )
        seen_code_paths.add(resolved)
        runtime_code.append(_artifact(path))
    envelope = _required_file(
        carry_start_envelope_path,
        "carry_start_envelope",
    )
    build_id = str(unity_build_id).strip()
    scene_id = str(unity_scene_id).strip()
    if not build_id or not scene_id:
        raise FunctionalBaselineBundleError(
            "unity_build_or_scene_id_missing"
        )

    bundle: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "functional_baseline_only",
        "source": "strict18_runtime_regression_recovery_3x10",
        "gate": {
            **dict(aggregate),
            "remaining_mass_30pct_is_blocking": False,
            "formal_freeze_gate_evaluated": False,
        },
        "release_scope": {
            "formal_act_freeze": False,
            "effect_model_unlocked": False,
            "planned_cut_calibration_unlocked": False,
        },
        "checkpoints": checkpoints,
        "runtime_config": _artifact(runtime_config),
        "runtime_code": runtime_code,
        "carry_start_envelope": _artifact(envelope),
        "unity": {
            "build_id": build_id,
            "scene_id": scene_id,
        },
        "validation_rollouts": rollout_artifacts,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(bundle, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return bundle


def _validation_artifact(
    record: Mapping[str, Any],
    *,
    index: int,
) -> dict[str, Any]:
    path = _required_file(
        record.get("source_artifact_path"),
        f"validation[{index}].source_artifact",
    )
    observed_sha = _sha256(path)
    expected_sha = str(record.get("source_artifact_sha256", "")).strip()
    if observed_sha != expected_sha:
        raise FunctionalBaselineBundleError(
            f"validation[{index}]:source_artifact_sha256_mismatch"
        )
    return {
        "reset_id": str(record.get("reset_id", "")),
        "path": str(path.resolve()),
        "sha256": observed_sha,
    }


def _required_file(value: Any, label: str) -> Path:
    if value is None or not str(value).strip():
        raise FunctionalBaselineBundleError(f"{label}_path_missing")
    path = Path(str(value)).expanduser()
    if not path.is_file():
        raise FunctionalBaselineBundleError(f"{label}_file_missing:{path}")
    return path


def _artifact(path: Path) -> dict[str, str]:
    return {
        "path": str(path.resolve()),
        "sha256": _sha256(path),
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "FunctionalBaselineBundleError",
    "SCHEMA",
    "build_functional_baseline_bundle",
]
