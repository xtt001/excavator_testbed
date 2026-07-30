"""Strong rollout evidence for the A0 coverage wall-safety contract."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from testbed.planner.primitive.coverage.wall_safety import (
    CONSERVATIVE_2D_WORKTOOL_SWEPT_FOOTPRINT_PROFILE,
    CoverageWallSafetyConfig,
)

EXPECTED_A0_CAMERAS = (
    "stick_up",
    "stick_down",
    "eye_left",
    "eye_right",
)
EXPECTED_A0_TEMPORAL_WINDOW = 100
EXPECTED_A0_TEMPORAL_WEIGHT_ORDER = "legacy_oldest_first"
EXPECTED_TEMPORAL_VARIANT = "A0"
EXPECTED_PLANNER_SAFETY_VARIANT = "coverage_wall_safety_v1"


class CoverageWallSafetyRolloutValidationError(RuntimeError):
    """Raised when recorded rollout evidence cannot prove wall-safe execution."""


@dataclass(frozen=True)
class CoverageWallSafetyRolloutContract:
    """Resolved A0 settings required by the formal wall-safe 1x10 gate."""

    profile: str
    hard_clearance_m: float
    worktool_width_m: float
    soft_clearance_m: float
    max_score_penalty: float
    missing_geometry: str
    camera_names: tuple[str, ...]
    temporal_agg_window: int
    temporal_agg_weight_order: str
    temporal_variant: str
    planner_safety_variant: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "hard_clearance_m": self.hard_clearance_m,
            "worktool_width_m": self.worktool_width_m,
            "soft_clearance_m": self.soft_clearance_m,
            "max_score_penalty": self.max_score_penalty,
            "missing_geometry": self.missing_geometry,
            "camera_names": list(self.camera_names),
            "temporal_agg_window": self.temporal_agg_window,
            "temporal_agg_weight_order": self.temporal_agg_weight_order,
            "temporal_variant": self.temporal_variant,
            "planner_safety_variant": self.planner_safety_variant,
        }


def coverage_wall_safety_enabled(config: Mapping[str, Any]) -> bool:
    """Return whether the resolved config opts into the new wall contract."""

    wall = _nested_mapping(
        config,
        "policy",
        "dig_cut_planner",
        "coverage",
        "wall_safety",
        required=False,
    )
    return bool(wall.get("enabled", False))


def load_optional_coverage_wall_safety_rollout_contract(
    resolved_config_path: str | Path,
) -> CoverageWallSafetyRolloutContract | None:
    """Load the contract when a resolved config explicitly enables it."""

    path = Path(resolved_config_path).expanduser()
    if not path.is_file():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise CoverageWallSafetyRolloutValidationError(
            f"resolved_config_invalid:{path}"
        ) from exc
    if not isinstance(raw, Mapping):
        raise CoverageWallSafetyRolloutValidationError(
            f"resolved_config_not_mapping:{path}"
        )
    if not coverage_wall_safety_enabled(raw):
        return None
    return load_coverage_wall_safety_rollout_contract(raw)


def load_coverage_wall_safety_rollout_contract(
    config: Mapping[str, Any],
) -> CoverageWallSafetyRolloutContract:
    """Validate exact A0 settings and construct the rollout evidence contract."""

    wall_mapping = _nested_mapping(
        config,
        "policy",
        "dig_cut_planner",
        "coverage",
        "wall_safety",
    )
    try:
        wall = CoverageWallSafetyConfig.from_mapping(wall_mapping)
    except (TypeError, ValueError) as exc:
        raise CoverageWallSafetyRolloutValidationError(
            f"wall_safety_config_invalid:{exc}"
        ) from exc
    if not wall.enabled:
        raise CoverageWallSafetyRolloutValidationError(
            "wall_safety_not_enabled"
        )
    expected_wall_values = {
        "profile": CONSERVATIVE_2D_WORKTOOL_SWEPT_FOOTPRINT_PROFILE,
        "worktool_width_m": 0.70,
        "hard_clearance_m": 0.30,
        "soft_clearance_m": 0.45,
        "max_score_penalty": 1.0,
        "missing_geometry": "fail_closed",
    }
    actual_wall_values = wall.as_dict()
    for field, expected in expected_wall_values.items():
        actual = actual_wall_values[field]
        if isinstance(expected, float):
            matches = bool(
                np.isfinite(float(actual))
                and abs(float(actual) - expected) <= 1.0e-12
            )
        else:
            matches = actual == expected
        if not matches:
            raise CoverageWallSafetyRolloutValidationError(
                f"wall_safety_{field}_mismatch:"
                f"expected={expected}:actual={actual}"
            )

    task = _nested_mapping(config, "task")
    camera_names = tuple(str(item) for item in task.get("camera_names", ()))
    if camera_names != EXPECTED_A0_CAMERAS:
        raise CoverageWallSafetyRolloutValidationError(
            "a0_camera_order_mismatch:"
            f"expected={list(EXPECTED_A0_CAMERAS)}:actual={list(camera_names)}"
        )
    act = _nested_mapping(config, "policy", "act_params")
    temporal_window = _strict_int(act.get("temporal_agg_window"))
    if temporal_window != EXPECTED_A0_TEMPORAL_WINDOW:
        raise CoverageWallSafetyRolloutValidationError(
            "a0_temporal_agg_window_mismatch:"
            f"expected={EXPECTED_A0_TEMPORAL_WINDOW}:actual={temporal_window}"
        )
    temporal_weight_order = str(
        act.get("temporal_agg_weight_order", "")
    ).strip()
    if temporal_weight_order != EXPECTED_A0_TEMPORAL_WEIGHT_ORDER:
        raise CoverageWallSafetyRolloutValidationError(
            "a0_temporal_agg_weight_order_mismatch:"
            f"expected={EXPECTED_A0_TEMPORAL_WEIGHT_ORDER}:"
            f"actual={temporal_weight_order}"
        )
    metadata = _nested_mapping(
        config,
        "eval",
        "record_hdf5_metadata",
    )
    temporal_variant = str(metadata.get("temporal_variant", "")).strip()
    if temporal_variant != EXPECTED_TEMPORAL_VARIANT:
        raise CoverageWallSafetyRolloutValidationError(
            "temporal_variant_mismatch:"
            f"expected={EXPECTED_TEMPORAL_VARIANT}:actual={temporal_variant}"
        )
    planner_safety_variant = str(
        metadata.get("planner_safety_variant", "")
    ).strip()
    if planner_safety_variant != EXPECTED_PLANNER_SAFETY_VARIANT:
        raise CoverageWallSafetyRolloutValidationError(
            "planner_safety_variant_mismatch:"
            f"expected={EXPECTED_PLANNER_SAFETY_VARIANT}:"
            f"actual={planner_safety_variant}"
        )
    return CoverageWallSafetyRolloutContract(
        profile=wall.profile,
        hard_clearance_m=float(wall.hard_clearance_m),
        worktool_width_m=float(wall.worktool_width_m),
        soft_clearance_m=float(wall.soft_clearance_m),
        max_score_penalty=float(wall.max_score_penalty),
        missing_geometry=wall.missing_geometry,
        camera_names=camera_names,
        temporal_agg_window=temporal_window,
        temporal_agg_weight_order=temporal_weight_order,
        temporal_variant=temporal_variant,
        planner_safety_variant=planner_safety_variant,
    )


def validate_coverage_wall_safety_rollout(
    *,
    rows: Sequence[Mapping[str, Any]],
    contract: CoverageWallSafetyRolloutContract,
) -> dict[str, Any]:
    """Fail closed unless every executed coverage selection is wall safe."""

    selected: dict[tuple[int, int], dict[str, Any]] = {}
    selected_cycles: set[int] = set()
    for row_index, row in enumerate(rows):
        corridor_id = _strict_int(row.get("coverage_corridor_id"), default=-1)
        planned_cell_id = _strict_int(row.get("planned_cut_cell_id"), default=-1)
        if corridor_id < 0 and planned_cell_id < 0:
            continue
        if corridor_id < 0 or planned_cell_id < 0:
            raise CoverageWallSafetyRolloutValidationError(
                f"row_{row_index}:selected_corridor_identity_incomplete"
            )
        cycle = _strict_int(row.get("primitive_cycle_index"), default=-1)
        if cycle < 0:
            raise CoverageWallSafetyRolloutValidationError(
                f"row_{row_index}:selected_cycle_invalid"
            )
        profile = str(row.get("coverage_wall_safety_profile", "")).strip()
        if profile != contract.profile:
            raise CoverageWallSafetyRolloutValidationError(
                f"row_{row_index}:selected_wall_profile_mismatch"
            )
        if row.get("coverage_wall_safety_eligible") is not True:
            raise CoverageWallSafetyRolloutValidationError(
                f"row_{row_index}:selected_final_wall_ineligible"
            )
        clearance = _finite_float(
            row.get("coverage_wall_minimum_clearance_m")
        )
        if clearance + 1.0e-9 < contract.hard_clearance_m:
            raise CoverageWallSafetyRolloutValidationError(
                f"row_{row_index}:selected_clearance_below_hard_limit:"
                f"clearance={clearance}:required={contract.hard_clearance_m}"
            )
        rejected_corridors = _integer_set(
            row.get("coverage_wall_rejected_corridor_ids")
        )
        if corridor_id in rejected_corridors:
            raise CoverageWallSafetyRolloutValidationError(
                f"row_{row_index}:selected_corridor_was_wall_rejected:"
                f"corridor={corridor_id}"
            )
        rejected_cells = _integer_set(
            row.get("coverage_wall_rejected_cell_ids")
        )
        if planned_cell_id in rejected_cells:
            raise CoverageWallSafetyRolloutValidationError(
                f"row_{row_index}:selected_cell_was_wall_rejected:"
                f"cell={planned_cell_id}"
            )
        trace = _selected_candidate_trace(
            row.get("coverage_candidate_scores"),
            corridor_id=corridor_id,
            row_index=row_index,
        )
        trace_cell_id = _strict_int(trace.get("cell_id"), default=-1)
        if trace_cell_id != planned_cell_id:
            raise CoverageWallSafetyRolloutValidationError(
                f"row_{row_index}:selected_candidate_cell_mismatch"
            )
        if _strict_int(trace.get("selectable"), default=0) != 1:
            raise CoverageWallSafetyRolloutValidationError(
                f"row_{row_index}:selected_candidate_not_selectable"
            )
        if _strict_int(trace.get("depleted"), default=1) != 0:
            raise CoverageWallSafetyRolloutValidationError(
                f"row_{row_index}:selected_candidate_depleted"
            )
        if _strict_int(trace.get("wall_safety_eligible"), default=0) != 1:
            raise CoverageWallSafetyRolloutValidationError(
                f"row_{row_index}:selected_candidate_wall_ineligible"
            )
        trace_clearance = _finite_float(
            trace.get("wall_minimum_clearance_m")
        )
        if trace_clearance + 1.0e-9 < contract.hard_clearance_m:
            raise CoverageWallSafetyRolloutValidationError(
                f"row_{row_index}:selected_candidate_clearance_below_hard_limit"
            )
        if str(trace.get("rejection_reason", "")).strip():
            raise CoverageWallSafetyRolloutValidationError(
                f"row_{row_index}:selected_candidate_has_rejection_reason"
            )
        selected_cycles.add(cycle)
        selected.setdefault(
            (cycle, corridor_id),
            {
                "cycle_index": cycle,
                "corridor_id": corridor_id,
                "cell_id": planned_cell_id,
                "wall_safety_class": str(
                    row.get("coverage_wall_safety_class", "")
                ),
                "minimum_clearance_m": clearance,
                "prototype_minimum_clearance_m": trace_clearance,
            },
        )
    if selected_cycles != set(range(10)):
        raise CoverageWallSafetyRolloutValidationError(
            "selected_corridor_cycle_inventory_mismatch:"
            f"actual={sorted(selected_cycles)}"
        )
    selected_rows = list(selected.values())
    return {
        "schema": "coverage_wall_safety_rollout_evidence_v1",
        "status": "passed",
        **contract.as_dict(),
        "selected_corridor_count": len(selected_rows),
        "minimum_selected_clearance_m": min(
            float(item["minimum_clearance_m"]) for item in selected_rows
        ),
        "selections": selected_rows,
    }


def _selected_candidate_trace(
    value: Any,
    *,
    corridor_id: int,
    row_index: int,
) -> Mapping[str, Any]:
    if not isinstance(value, Sequence) or isinstance(
        value, (str, bytes, bytearray)
    ):
        raise CoverageWallSafetyRolloutValidationError(
            f"row_{row_index}:coverage_candidate_scores_missing"
        )
    matches = [
        item
        for item in value
        if isinstance(item, Mapping)
        and _strict_int(item.get("corridor_id"), default=-1) == corridor_id
    ]
    if len(matches) != 1:
        raise CoverageWallSafetyRolloutValidationError(
            f"row_{row_index}:selected_candidate_trace_not_unique"
        )
    return matches[0]


def _nested_mapping(
    value: Mapping[str, Any],
    *path: str,
    required: bool = True,
) -> Mapping[str, Any]:
    current: Any = value
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            if required:
                raise CoverageWallSafetyRolloutValidationError(
                    f"resolved_config_field_missing:{'.'.join(path)}"
                )
            return {}
        current = current[key]
    if not isinstance(current, Mapping):
        raise CoverageWallSafetyRolloutValidationError(
            f"resolved_config_field_invalid:{'.'.join(path)}"
        )
    return current


def _strict_int(value: Any, *, default: int | None = None) -> int:
    if isinstance(value, bool):
        if default is not None:
            return default
        raise CoverageWallSafetyRolloutValidationError("integer_field_invalid")
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        if default is not None:
            return default
        raise CoverageWallSafetyRolloutValidationError(
            "integer_field_invalid"
        ) from exc
    try:
        exact = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        if default is not None:
            return default
        raise CoverageWallSafetyRolloutValidationError(
            "integer_field_invalid"
        ) from exc
    if not np.isfinite(exact) or abs(exact - result) > 1.0e-9:
        if default is not None:
            return default
        raise CoverageWallSafetyRolloutValidationError("integer_field_invalid")
    return result


def _finite_float(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CoverageWallSafetyRolloutValidationError(
            "wall_clearance_invalid"
        ) from exc
    if not np.isfinite(result):
        raise CoverageWallSafetyRolloutValidationError(
            "wall_clearance_invalid"
        )
    return result


def _integer_set(value: Any) -> set[int]:
    if not isinstance(value, Sequence) or isinstance(
        value, (str, bytes, bytearray)
    ):
        raise CoverageWallSafetyRolloutValidationError(
            "wall_rejected_ids_invalid"
        )
    result: set[int] = set()
    for item in value:
        parsed = _strict_int(item, default=-1)
        if parsed < 0:
            raise CoverageWallSafetyRolloutValidationError(
                "wall_rejected_ids_invalid"
            )
        result.add(parsed)
    return result


__all__ = [
    "CoverageWallSafetyRolloutContract",
    "CoverageWallSafetyRolloutValidationError",
    "coverage_wall_safety_enabled",
    "load_coverage_wall_safety_rollout_contract",
    "load_optional_coverage_wall_safety_rollout_contract",
    "validate_coverage_wall_safety_rollout",
]
