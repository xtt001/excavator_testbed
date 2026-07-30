"""Pure contracts for diagnostic wall-contact evidence.

These helpers deliberately do not make production safety decisions.  They
validate the append-only Unity sidecar and the reset/causal evidence used by
the contact-semantics experiment.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import Any

from testbed.data.schema import (
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_DIG_AREA_CURRENT_REMAINING_MASS_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
    ENV_STATE_V2_4_DIM,
)
from testbed.planner.box_emptying.wall_contact_detail import (
    WALL_CONTACT_HARD_MAX_FORCE_N,
    WORKTOOL_WALL_CONTACT_DETAIL_PREFIX,
    WORKTOOL_WALL_CONTACT_DETAIL_SCHEMA,
    WallContactDetailContractError,
)
from testbed.planner.box_emptying.wall_contact_detail import (
    parse_worktool_wall_contact_detail as _runtime_parse_contact_detail,
)

CONTACT_DETAIL_SCHEMA = WORKTOOL_WALL_CONTACT_DETAIL_SCHEMA
CONTACT_DETAIL_WARNING_PREFIX = WORKTOOL_WALL_CONTACT_DETAIL_PREFIX
HIGH_FORCE_N = WALL_CONTACT_HARD_MAX_FORCE_N
SCRAPE_TANGENTIAL_DISPLACEMENT_M = 0.01
SCRAPE_MIN_CONSECUTIVE_STEPS = 2

RESET_QPOS_MAX_ABS_DELTA = 0.005
RESET_QVEL_ABS_MAX = 0.10
RESET_QVEL_PAIRED_AXIS_MAX_ABS_DELTA = 0.02
RESET_BUCKET_TIP_MAX_DISPLACEMENT_M = 0.02
RESET_TERRAIN_DEPTH_MAX_ABS_DELTA_M = 0.002
RESET_REMAINING_MASS_MAX_ABS_DELTA_KG = 5.0


class ContactEvidenceContractError(ValueError):
    """Raised when contact evidence is missing, ambiguous, or non-finite."""


def parse_worktool_wall_contact_detail(
    warnings: Any,
) -> dict[str, Any]:
    """Return one canonical detail sidecar from a STEP warning sequence."""

    if not _is_sequence(warnings):
        raise ContactEvidenceContractError("contact_warnings_invalid")
    normalized = [
        (
            CONTACT_DETAIL_WARNING_PREFIX
            + json.dumps(dict(item), separators=(",", ":"), sort_keys=True)
            if isinstance(item, Mapping) and item.get("schema") == CONTACT_DETAIL_SCHEMA
            else item
        )
        for item in warnings
    ]
    try:
        parsed = _runtime_parse_contact_detail(normalized)
    except WallContactDetailContractError as exc:
        raise ContactEvidenceContractError(f"contact_detail_invalid:{exc}") from exc
    return _contact_detail_dict(parsed)


def validate_worktool_wall_contact_detail(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate and normalize one ``worktool_wall_contact_detail_v1``."""

    return parse_worktool_wall_contact_detail([value])


def validate_reset_pair(
    *,
    expected_reset_state: Mapping[str, Any],
    reset_a: Mapping[str, Any],
    reset_b: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate one pair against the frozen reset reference and each other."""

    expected = _reset_state(expected_reset_state, "expected_reset_state")
    a = _reset_state(reset_a, "reset_a")
    b = _reset_state(reset_b, "reset_b")
    metrics = {
        "a_qpos_max_abs_delta": _max_abs_delta(a["qpos"], expected["qpos"]),
        "b_qpos_max_abs_delta": _max_abs_delta(b["qpos"], expected["qpos"]),
        "a_qvel_abs_max": max(abs(value) for value in a["qvel"]),
        "b_qvel_abs_max": max(abs(value) for value in b["qvel"]),
        "qvel_paired_axis_max_abs_delta": _max_abs_delta(
            a["qvel"],
            b["qvel"],
        ),
        "a_bucket_tip_displacement_m": _euclidean(
            a["bucket_tip_m"],
            expected["bucket_tip_m"],
        ),
        "b_bucket_tip_displacement_m": _euclidean(
            b["bucket_tip_m"],
            expected["bucket_tip_m"],
        ),
        "a_terrain_depth_max_abs_delta_m": _max_abs_delta(
            a["terrain_depth_m"],
            expected["terrain_depth_m"],
        ),
        "b_terrain_depth_max_abs_delta_m": _max_abs_delta(
            b["terrain_depth_m"],
            expected["terrain_depth_m"],
        ),
        "a_remaining_mass_abs_delta_kg": abs(
            a["remaining_mass_kg"] - expected["remaining_mass_kg"]
        ),
        "b_remaining_mass_abs_delta_kg": abs(
            b["remaining_mass_kg"] - expected["remaining_mass_kg"]
        ),
    }
    violations: list[str] = []
    if (
        max(
            metrics["a_qpos_max_abs_delta"],
            metrics["b_qpos_max_abs_delta"],
        )
        > RESET_QPOS_MAX_ABS_DELTA
    ):
        violations.append("qpos_reset_reference_delta_exceeded")
    if max(metrics["a_qvel_abs_max"], metrics["b_qvel_abs_max"]) > (RESET_QVEL_ABS_MAX):
        violations.append("qvel_absolute_limit_exceeded")
    if metrics["qvel_paired_axis_max_abs_delta"] > (
        RESET_QVEL_PAIRED_AXIS_MAX_ABS_DELTA
    ):
        violations.append("qvel_paired_axis_delta_exceeded")
    if (
        max(
            metrics["a_bucket_tip_displacement_m"],
            metrics["b_bucket_tip_displacement_m"],
        )
        > RESET_BUCKET_TIP_MAX_DISPLACEMENT_M
    ):
        violations.append("bucket_tip_reset_reference_delta_exceeded")
    if (
        max(
            metrics["a_terrain_depth_max_abs_delta_m"],
            metrics["b_terrain_depth_max_abs_delta_m"],
        )
        > RESET_TERRAIN_DEPTH_MAX_ABS_DELTA_M
    ):
        violations.append("terrain_depth_handoff_delta_exceeded")
    if (
        max(
            metrics["a_remaining_mass_abs_delta_kg"],
            metrics["b_remaining_mass_abs_delta_kg"],
        )
        > RESET_REMAINING_MASS_MAX_ABS_DELTA_KG
    ):
        violations.append("remaining_mass_handoff_delta_exceeded")
    return {
        "valid": not violations,
        "violations": violations,
        "metrics": metrics,
        "limits": {
            "qpos_max_abs_delta": RESET_QPOS_MAX_ABS_DELTA,
            "qvel_abs_max": RESET_QVEL_ABS_MAX,
            "qvel_paired_axis_max_abs_delta": (RESET_QVEL_PAIRED_AXIS_MAX_ABS_DELTA),
            "bucket_tip_max_displacement_m": (RESET_BUCKET_TIP_MAX_DISPLACEMENT_M),
            "terrain_depth_max_abs_delta_m": (RESET_TERRAIN_DEPTH_MAX_ABS_DELTA_M),
            "remaining_mass_max_abs_delta_kg": (RESET_REMAINING_MASS_MAX_ABS_DELTA_KG),
        },
    }


def rollout_reset_state(row: Mapping[str, Any]) -> dict[str, Any]:
    """Extract the canonical first-post-reset state from one rollout row."""

    env = _vector(
        row.get("env_state"),
        width=ENV_STATE_V2_4_DIM,
        label="reset.env_state",
    )
    tip = ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX
    depth = ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX
    return _reset_state(
        {
            "qpos": row.get("qpos"),
            "qvel": row.get("qvel"),
            "bucket_tip_m": env[tip : tip + 3],
            "terrain_depth_m": env[depth : depth + 6],
            "remaining_mass_kg": env[
                ENV_STATE_DIG_AREA_CURRENT_REMAINING_MASS_IDX
            ],
        },
        "reset",
    )


def summarize_contact_details(
    details: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Aggregate diagnostic force/session/contact-region evidence."""

    if not details:
        return {
            "contact_observed": False,
            "categories": ["near_wall"],
            "peak_force_n": 0.0,
            "rms_force_n": 0.0,
            "normal_impulse_n_s": 0.0,
            "session_count": 0,
            "maximum_session_duration_s": 0.0,
            "maximum_tangential_displacement_m": 0.0,
            "components": [],
            "walls": [],
            "bucket_local_region_samples": [],
        }
    parsed = [validate_worktool_wall_contact_detail(item) for item in details]
    forces = [
        float(pair["max_total_force_n"])
        for detail in parsed
        for pair in detail["pairs"]
    ]
    components = sorted(
        {str(pair["component"]) for detail in parsed for pair in detail["pairs"]}
    )
    walls = sorted(
        {str(pair["wall_name"]) for detail in parsed for pair in detail["pairs"]}
    )
    session_impulses: dict[int, float] = {}
    categories: set[str] = set()
    region_samples: list[list[float]] = []
    max_tangential = 0.0
    max_duration = 0.0
    for detail in parsed:
        session_id = int(detail["session_id"])
        session_impulses[session_id] = max(
            session_impulses.get(session_id, 0.0),
            float(detail["session_normal_impulse_n_s"]),
        )
        max_duration = max(
            max_duration,
            float(detail["session_duration_s"]),
        )
        for pair in detail["pairs"]:
            component = str(pair["component"])
            force = float(pair["max_total_force_n"])
            displacement = float(pair["tangential_displacement_m"])
            max_tangential = max(max_tangential, displacement)
            if component in {"boom", "stick", "other"}:
                categories.add("forbidden_component")
            if force >= HIGH_FORCE_N:
                categories.add("high_force_collision")
            if component == "bucket":
                local = list(pair["representative_contact_point_component_local_m"])
                if local:
                    region_samples.append(local)
                if (
                    int(detail["consecutive_contact_steps"])
                    >= SCRAPE_MIN_CONSECUTIVE_STEPS
                    and displacement >= SCRAPE_TANGENTIAL_DISPLACEMENT_M
                ):
                    categories.add("bucket_scrape_like")
                else:
                    categories.add("bucket_touch")
    if not categories:
        categories.add("bucket_touch")
    return {
        "contact_observed": True,
        "categories": sorted(categories),
        "peak_force_n": max(forces),
        "rms_force_n": math.sqrt(sum(force * force for force in forces) / len(forces)),
        "normal_impulse_n_s": sum(session_impulses.values()),
        "session_count": len(session_impulses),
        "maximum_session_duration_s": max_duration,
        "maximum_tangential_displacement_m": max_tangential,
        "components": components,
        "walls": walls,
        "bucket_local_region_samples": region_samples,
    }


def causal_classification(
    *,
    attempts: Sequence[Mapping[str, Any]],
    expert_same_region_sub_100kn: bool,
    expert_lineage_complete: bool,
) -> str:
    """Apply the frozen diagnostic A/B causal categories."""

    b_rows = [item for item in attempts if str(item.get("condition", "")) == "B"]
    if (
        len(b_rows) != 3
        or {int(item.get("seed", -1)) for item in b_rows} != {0, 1, 2}
        or not all(bool(item.get("pair_valid", False)) for item in b_rows)
    ):
        return "inconclusive"
    dump_count = sum(bool(item.get("dump_completed", False)) for item in b_rows)
    if dump_count == 3 and all(
        bool(item.get("entered_carry", False))
        and bool(item.get("contact_ended_before_carry", False))
        and not bool(item.get("hard_violation", False))
        for item in b_rows
    ):
        return "safety_too_strict"
    contact_hard_failures = sum(
        bool(item.get("contact_driven_hard_failure", False)) for item in b_rows
    )
    if dump_count == 0 and contact_hard_failures >= 2:
        return "act_or_goal_geometry"
    if (
        dump_count in {1, 2}
        and expert_lineage_complete
        and expert_same_region_sub_100kn
    ):
        return "low_margin_dataset_style"
    return "inconclusive"


def expert_same_region_sub_100kn(
    *,
    attempts: Sequence[Mapping[str, Any]],
    train_source_summaries: Sequence[Mapping[str, Any]],
    match_radius_m: float = 0.05,
) -> bool:
    """Match each successful B contact to valid train bucket evidence."""

    successful = [
        row
        for row in attempts
        if row.get("condition") == "B" and row.get("dump_completed") is True
    ]
    if not 1 <= len(successful) <= 2:
        return False
    expert_pairs = []
    for source in train_source_summaries:
        summary = source.get("production_inference_contact_summary")
        pairs = (
            summary.get("component_wall_summaries", ())
            if isinstance(summary, Mapping)
            else ()
        )
        if isinstance(pairs, list):
            expert_pairs.extend(item for item in pairs if isinstance(item, Mapping))
    return all(
        _matches_train_bucket_region(row, expert_pairs, match_radius_m)
        for row in successful
    )


def _matches_train_bucket_region(
    attempt: Mapping[str, Any],
    expert_pairs: Sequence[Mapping[str, Any]],
    radius_m: float,
) -> bool:
    contact = attempt.get("contact")
    if not isinstance(contact, Mapping):
        return False
    try:
        peak = float(contact.get("peak_force_n", math.nan))
    except (TypeError, ValueError):
        return False
    samples = contact.get("bucket_local_region_samples")
    if (
        contact.get("components") != ["bucket"]
        or not math.isfinite(peak)
        or peak >= HIGH_FORCE_N
        or not isinstance(samples, list)
        or not samples
    ):
        return False
    walls = set(str(item) for item in contact.get("walls", ()))
    scrape = "bucket_scrape_like" in contact.get("categories", ())
    for pair in expert_pairs:
        if (
            pair.get("component") != "bucket"
            or str(pair.get("wall_name", "")) not in walls
        ):
            continue
        try:
            expert_peak = float(pair.get("peak_total_force_n", math.nan))
            tangential = float(pair.get("maximum_tangential_displacement_m", 0.0))
        except (TypeError, ValueError):
            continue
        if (
            not math.isfinite(expert_peak)
            or expert_peak >= HIGH_FORCE_N
            or (scrape and tangential < SCRAPE_TANGENTIAL_DISPLACEMENT_M)
        ):
            continue
        expert_samples = pair.get("bucket_local_contact_region_samples")
        if isinstance(expert_samples, list) and any(
            _euclidean(left, right) <= radius_m
            for left in samples
            for right in expert_samples
            if _is_sequence(left)
            and _is_sequence(right)
            and len(left) == len(right) == 3
        ):
            return True
    return False


def derive_expected_remaining_mass_kg(
    *,
    live_reset_initial_remaining_mass_kg: Any,
    source_removed_depth_grid_m: Any,
    source_cell_area_m2: Any,
    live_bulk_density_kg_m3: Any,
) -> float:
    """Map an 89D source depth delta onto the live reset mass lineage."""

    initial = _finite(
        live_reset_initial_remaining_mass_kg,
        "live_reset_initial_remaining_mass_kg",
        minimum=0.0,
    )
    depth = _vector(
        source_removed_depth_grid_m,
        width=6,
        label="source_removed_depth_grid_m",
    )
    if any(value < 0.0 for value in depth):
        raise ContactEvidenceContractError("source_removed_depth_grid_m_invalid")
    area = _finite(
        source_cell_area_m2,
        "source_cell_area_m2",
        minimum=0.0,
    )
    density = _finite(
        live_bulk_density_kg_m3,
        "live_bulk_density_kg_m3",
        minimum=0.0,
    )
    expected = initial - sum(depth) * area * density
    if expected < -RESET_REMAINING_MASS_MAX_ABS_DELTA_KG:
        raise ContactEvidenceContractError("derived_expected_remaining_mass_negative")
    return max(0.0, expected)


def validate_expert_window_fairness(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate replay-vs-recorded dig-window state differences."""

    if not isinstance(value, Mapping):
        raise ContactEvidenceContractError("expert_window_fairness_invalid")
    metrics = {
        "qpos_max_abs_difference": _finite(
            value.get("qpos_max_abs_difference"),
            "qpos_max_abs_difference",
            minimum=0.0,
        ),
        "qvel_max_abs_difference": _finite(
            value.get("qvel_max_abs_difference"),
            "qvel_max_abs_difference",
            minimum=0.0,
        ),
        "bucket_tip_displacement_m": _finite(
            value.get("bucket_tip_displacement_m"),
            "bucket_tip_displacement_m",
            minimum=0.0,
        ),
        "terrain_depth_max_abs_difference_m": _finite(
            value.get("terrain_depth_max_abs_difference_m"),
            "terrain_depth_max_abs_difference_m",
            minimum=0.0,
        ),
        "remaining_mass_abs_difference_kg": _finite(
            value.get("remaining_mass_abs_difference_kg"),
            "remaining_mass_abs_difference_kg",
            minimum=0.0,
        ),
    }
    checks = {
        "qpos": metrics["qpos_max_abs_difference"] <= RESET_QPOS_MAX_ABS_DELTA,
        "qvel": metrics["qvel_max_abs_difference"] <= RESET_QVEL_ABS_MAX,
        "bucket_tip": metrics["bucket_tip_displacement_m"]
        <= RESET_BUCKET_TIP_MAX_DISPLACEMENT_M,
        "terrain_depth": metrics["terrain_depth_max_abs_difference_m"]
        <= RESET_TERRAIN_DEPTH_MAX_ABS_DELTA_M,
        "remaining_mass": metrics["remaining_mass_abs_difference_kg"]
        <= RESET_REMAINING_MASS_MAX_ABS_DELTA_KG,
    }
    return {
        "valid": all(checks.values()),
        "checks": checks,
        "metrics": metrics,
    }


def terminal_matches_box_safety_reason(
    terminal_reason: Any,
    expected_reason: str,
) -> bool:
    """Accept canonical bare or EvalSuite-prefixed box-safety stop reasons."""

    reason = str(terminal_reason)
    return reason in {
        expected_reason,
        f"box_safety:{expected_reason}",
    }


def _contact_detail_dict(value: Any) -> dict[str, Any]:
    rendered = asdict(value)
    rendered["parts"] = list(rendered["parts"])
    rendered["walls"] = list(rendered["walls"])
    rendered["pairs"] = [dict(item) for item in rendered["pairs"]]
    for pair in rendered["pairs"]:
        pair["contact_points_world_m"] = [
            list(point) for point in pair["contact_points_world_m"]
        ]
        local = pair["representative_contact_point_component_local_m"]
        pair["representative_contact_point_component_local_m"] = (
            [] if local is None else list(local)
        )
    return rendered


def _reset_state(value: Mapping[str, Any], label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ContactEvidenceContractError(f"{label}_invalid")
    return {
        "qpos": _vector(value.get("qpos"), width=4, label=f"{label}.qpos"),
        "qvel": _vector(value.get("qvel"), width=4, label=f"{label}.qvel"),
        "bucket_tip_m": _vector(
            value.get("bucket_tip_m"),
            width=3,
            label=f"{label}.bucket_tip_m",
        ),
        "terrain_depth_m": _vector(
            value.get("terrain_depth_m"),
            width=6,
            label=f"{label}.terrain_depth_m",
        ),
        "remaining_mass_kg": _finite(
            value.get("remaining_mass_kg"),
            f"{label}.remaining_mass_kg",
            minimum=0.0,
        ),
    }


def _integer(
    value: Any,
    label: str,
    *,
    minimum: int,
) -> int:
    if isinstance(value, bool):
        raise ContactEvidenceContractError(f"{label}_invalid")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ContactEvidenceContractError(f"{label}_invalid") from exc
    if result != value or result < minimum:
        raise ContactEvidenceContractError(f"{label}_invalid")
    return result


def _finite(
    value: Any,
    label: str,
    *,
    minimum: float | None = None,
    strictly_positive: bool = False,
) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ContactEvidenceContractError(f"{label}_invalid") from exc
    if not math.isfinite(result):
        raise ContactEvidenceContractError(f"{label}_invalid")
    if minimum is not None and result < minimum:
        raise ContactEvidenceContractError(f"{label}_invalid")
    if strictly_positive and result <= 0.0:
        raise ContactEvidenceContractError(f"{label}_invalid")
    return result


def _vector(value: Any, *, width: int, label: str) -> list[float]:
    if not _is_sequence(value) or len(value) != width:
        raise ContactEvidenceContractError(f"{label}_invalid")
    return [_finite(item, label) for item in value]


def _max_abs_delta(left: Sequence[float], right: Sequence[float]) -> float:
    return max(abs(a - b) for a, b in zip(left, right, strict=True))


def _euclidean(left: Sequence[float], right: Sequence[float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right, strict=True)))


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    )


__all__ = [
    "CONTACT_DETAIL_SCHEMA",
    "CONTACT_DETAIL_WARNING_PREFIX",
    "ContactEvidenceContractError",
    "HIGH_FORCE_N",
    "causal_classification",
    "derive_expected_remaining_mass_kg",
    "parse_worktool_wall_contact_detail",
    "rollout_reset_state",
    "summarize_contact_details",
    "terminal_matches_box_safety_reason",
    "validate_expert_window_fairness",
    "validate_reset_pair",
    "validate_worktool_wall_contact_detail",
]
