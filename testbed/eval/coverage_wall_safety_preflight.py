"""No-overwrite preflight for the A0 coverage wall-safety rollout."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import h5py
import yaml

from testbed.planner.primitive.coverage.selection import (
    CoverageCandidateBuilder,
)
from testbed.planner.primitive.coverage.wall_safety import (
    CoverageWallGeometry,
    CoverageWallSafetyConfig,
    CoverageWallSafetyService,
)

SCHEMA = "coverage_wall_safety_preflight_v1"
EXPECTED_CLASSES = {
    0: "hard_reject",
    1: "hard_reject",
    2: "near_wall",
    3: "near_wall",
    4: "near_wall",
    5: "near_wall",
}
_CODE_PATHS = (
    "testbed/planner/primitive/coverage/wall_safety.py",
    "testbed/planner/primitive/coverage/selection.py",
    "testbed/planner/primitive/coverage/facts.py",
    "testbed/planner/primitive/coverage/selection_runtime.py",
    "testbed/planner/primitive/coverage/config.py",
)


class CoverageWallSafetyPreflightError(RuntimeError):
    """Raised when static evidence cannot authorize the live A0 rollout."""


def build_coverage_wall_safety_preflight(
    *,
    config_path: str | Path,
    env_state_hdf5_path: str | Path,
    unity_scene_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Validate A0 geometry/classification and write one immutable artifact."""

    destination = Path(output_dir).expanduser()
    if destination.exists():
        raise FileExistsError(
            f"coverage wall-safety preflight already exists: {destination}"
        )
    config_source = _require_file(config_path, "config")
    env_source = _require_file(env_state_hdf5_path, "env_state_hdf5")
    scene_source = _require_file(unity_scene_path, "unity_scene")
    config = _load_mapping(config_source, loader="yaml")
    policy = _mapping(config.get("policy"), "policy")
    dig_planner = _mapping(policy.get("dig_cut_planner"), "dig_cut_planner")
    coverage = _mapping(dig_planner.get("coverage"), "coverage")
    wall_config = CoverageWallSafetyConfig.from_mapping(
        coverage.get("wall_safety")
    )
    if not wall_config.enabled:
        raise CoverageWallSafetyPreflightError(
            "coverage_wall_safety_not_enabled"
        )
    if str(dig_planner.get("fallback_mode", "")) == "conservative_pose":
        raise CoverageWallSafetyPreflightError(
            "coverage_wall_safety_fallback_forbidden"
        )
    box = _mapping(policy.get("box_emptying"), "box_emptying")
    if not bool(box.get("safety_enabled", False)):
        raise CoverageWallSafetyPreflightError(
            "coverage_wall_safety_requires_typed_safety"
        )

    repository_root = config_source.parents[2]
    prior_source = Path(str(dig_planner.get("prior_path", ""))).expanduser()
    if not prior_source.is_absolute():
        prior_source = repository_root / prior_source
    prior_source = _require_file(prior_source, "prior")
    prior = _load_mapping(prior_source, loader="json")
    env_state, env_row_index = _load_env_state(env_source)
    geometry = CoverageWallGeometry.from_env_state(env_state)
    candidates = CoverageCandidateBuilder(
        candidate_layout=str(
            coverage.get("candidate_layout", "percentile_grid")
        ),
        entry_x_percentiles=tuple(
            coverage.get("entry_x_percentiles", ("p10", "p50", "p90"))
        ),
        entry_z_percentiles=tuple(
            coverage.get("entry_z_percentiles", ("p10", "p50", "p90"))
        ),
        cut_direction_percentile=str(
            coverage.get("cut_direction_percentile", "p50")
        ),
        cut_length_percentile=str(
            coverage.get("cut_length_percentile", "p50")
        ),
        cut_depth_percentile=str(
            coverage.get("cut_depth_percentile", "p50")
        ),
        payload_percentile=str(coverage.get("payload_percentile", "p50")),
    ).build(prior)
    service = CoverageWallSafetyService(wall_config)
    classifications: list[dict[str, Any]] = []
    for corridor in candidates:
        result = service.evaluate_segment(
            env_state=env_state,
            entry_x_m=corridor.entry_x_m,
            entry_z_m=corridor.entry_z_m,
            exit_x_m=corridor.exit_x_m,
            exit_z_m=corridor.exit_z_m,
        )
        classifications.append(
            {
                "corridor_id": int(corridor.corridor_id),
                "cell_id": int(corridor.cell_id),
                "entry_x_m": float(corridor.entry_x_m),
                "entry_z_m": float(corridor.entry_z_m),
                "exit_x_m": float(corridor.exit_x_m),
                "exit_z_m": float(corridor.exit_z_m),
                **result.as_trace_fields(),
            }
        )
    _validate_expected_classifications(classifications)
    scene_sha = _sha256(scene_source)
    configured_scene_id = str(
        _mapping(config.get("eval"), "eval")
        .get("record_hdf5_metadata", {})
        .get("unity_scene_id", "")
    )
    expected_scene_sha = _configured_sha256(configured_scene_id)
    if expected_scene_sha and expected_scene_sha != scene_sha:
        raise CoverageWallSafetyPreflightError(
            "unity_scene_sha256_mismatch:"
            f"expected={expected_scene_sha}:actual={scene_sha}"
        )
    code_files = {
        path: _sha256(_require_file(repository_root / path, f"code:{path}"))
        for path in _CODE_PATHS
    }
    code_composite = hashlib.sha256(
        "\n".join(f"{path}:{digest}" for path, digest in code_files.items()).encode(
            "utf-8"
        )
    ).hexdigest()
    evaluation = _mapping(config.get("eval"), "eval")
    act_params = _mapping(policy.get("act_params"), "act_params")
    artifact: dict[str, Any] = {
        "schema": SCHEMA,
        "status": "passed",
        "config": {
            "path": str(config_source.resolve()),
            "sha256": _sha256(config_source),
        },
        "prior": {
            "path": str(prior_source.resolve()),
            "sha256": _sha256(prior_source),
            "prior_id": str(prior.get("prior_id", "")),
        },
        "geometry_source": {
            "path": str(env_source.resolve()),
            "sha256": _sha256(env_source),
            "dataset": "observations/env_state",
            "row_index": int(env_row_index),
        },
        "geometry": {
            "long_axis": int(geometry.long_axis),
            "grid_long_count": int(geometry.grid_long_count),
            "grid_short_count": int(geometry.grid_short_count),
            "cell_long_size_m": float(geometry.cell_long_size_m),
            "cell_short_size_m": float(geometry.cell_short_size_m),
            "box_half_x_m": float(geometry.half_x_m),
            "box_half_z_m": float(geometry.half_z_m),
        },
        "wall_safety_config": wall_config.as_dict(),
        "candidate_classifications": classifications,
        "expected_classes": {
            str(cell): value for cell, value in EXPECTED_CLASSES.items()
        },
        "unity_scene": {
            "path": str(scene_source.resolve()),
            "sha256": scene_sha,
            "configured_scene_id": configured_scene_id,
        },
        "code": {
            "files": code_files,
            "composite_sha256": code_composite,
        },
        "a0_invariants": {
            "camera_names": list(
                _mapping(config.get("task"), "task").get("camera_names", [])
            ),
            "temporal_agg_window": int(
                act_params.get("temporal_agg_window", -1)
            ),
            "temporal_agg_weight_order": str(
                act_params.get("temporal_agg_weight_order", "")
            ),
            "temporal_variant": str(
                _mapping(
                    evaluation.get("record_hdf5_metadata"),
                    "record_hdf5_metadata",
                ).get("temporal_variant", "")
            ),
            "planner_safety_variant": str(
                _mapping(
                    evaluation.get("record_hdf5_metadata"),
                    "record_hdf5_metadata",
                ).get("planner_safety_variant", "")
            ),
        },
    }
    destination.mkdir(parents=True, exist_ok=False)
    output_path = destination / f"{SCHEMA}.json"
    output_path.write_text(
        json.dumps(
            artifact,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return artifact


def _validate_expected_classifications(
    classifications: list[dict[str, Any]],
) -> None:
    by_cell = {int(item["cell_id"]): item for item in classifications}
    if sorted(by_cell) != list(range(6)):
        raise CoverageWallSafetyPreflightError(
            f"candidate_inventory_mismatch:{sorted(by_cell)}"
        )
    mismatches = [
        (
            cell_id,
            EXPECTED_CLASSES[cell_id],
            str(by_cell[cell_id]["wall_safety_class"]),
        )
        for cell_id in range(6)
        if str(by_cell[cell_id]["wall_safety_class"])
        != EXPECTED_CLASSES[cell_id]
    ]
    if mismatches:
        raise CoverageWallSafetyPreflightError(
            f"candidate_classification_mismatch:{mismatches}"
        )
    if int(by_cell[2]["wall_safety_eligible"]) != 1:
        raise CoverageWallSafetyPreflightError(
            "candidate_classification_mismatch:C1_cell2_not_selectable"
        )


def _load_env_state(path: Path) -> tuple[Any, int]:
    try:
        with h5py.File(path, "r") as handle:
            dataset = handle["observations/env_state"]
            if dataset.ndim != 2 or dataset.shape[0] <= 0:
                raise CoverageWallSafetyPreflightError(
                    "env_state_dataset_invalid"
                )
            return dataset[0], 0
    except (OSError, KeyError) as exc:
        raise CoverageWallSafetyPreflightError(
            "env_state_dataset_missing_or_unreadable"
        ) from exc


def _load_mapping(path: Path, *, loader: str) -> dict[str, Any]:
    try:
        if loader == "yaml":
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
        else:
            value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise CoverageWallSafetyPreflightError(
            f"{loader}_source_invalid:{path}"
        ) from exc
    return _mapping(value, loader)


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CoverageWallSafetyPreflightError(f"{label}_must_be_mapping")
    return dict(value)


def _configured_sha256(value: str) -> str:
    marker = "@sha256:"
    if marker not in value:
        return ""
    return value.rsplit(marker, 1)[1].strip()


def _require_file(path: str | Path, label: str) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_file():
        raise CoverageWallSafetyPreflightError(
            f"{label}_missing:{candidate}"
        )
    return candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "CoverageWallSafetyPreflightError",
    "EXPECTED_CLASSES",
    "SCHEMA",
    "build_coverage_wall_safety_preflight",
]
