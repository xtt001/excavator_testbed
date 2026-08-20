"""Post-run metrics for the frozen Return closed-loop causal matrix."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from testbed.data.schema import (
    ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX,
    ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
)
from testbed.eval.return_closed_loop_causal_contract import (
    LATEST_CURRENT_CHUNK_DIAGNOSTIC,
    LEGACY_TEMPORAL_DISPATCH,
    RETURN_TRAJECTORY_SEPARATION_HOLD_FRAMES,
    ReturnSafetyFacts,
    ReturnTargetEnvelope,
    assess_return_action_continuity,
    assess_return_target_envelope,
    classify_return_closed_loop_safety,
    measure_return_trajectory_separation,
)

RESULTS_SCHEMA = "strict18_return_closed_loop_results_v1"


def evaluate_return_closed_loop_results(
    *,
    output_root: str | Path,
    arms: Sequence[Mapping[str, Any]],
    action_discontinuity_threshold: Sequence[float],
) -> dict[str, Any]:
    """Evaluate endpoints, action quality, safety, and target-pair separation."""

    threshold = np.asarray(
        action_discontinuity_threshold, dtype=np.float32
    ).reshape(-1)
    if threshold.shape != (4,) or not np.isfinite(threshold).all():
        raise ValueError("action discontinuity threshold must be a finite 4-vector")
    root = Path(output_root)
    arm_results: list[dict[str, Any]] = []
    trajectories: dict[str, np.ndarray] = {}
    for arm in arms:
        arm_id = str(arm["arm_id"])
        rows = _read_trace(root / "arms" / arm_id / "trace.jsonl")
        actions = np.asarray(
            [row["applied_action"] for row in rows], dtype=np.float32
        )
        if actions.size == 0:
            actions = np.empty((0, 4), dtype=np.float32)
        continuity = (
            None
            if len(actions) == 0
            else assess_return_action_continuity(
                actions,
                discontinuity_threshold=threshold,
            ).as_dict()
        )
        envelope = ReturnTargetEnvelope(**dict(arm["target_envelope"]))
        other_envelope = ReturnTargetEnvelope(
            **dict(arm["other_target_envelope"])
        )
        envelope_rows = _envelope_assessments(rows, envelope=envelope)
        other_envelope_rows = _envelope_assessments(
            rows, envelope=other_envelope
        )
        official_handoff_frames = [
            index
            for index, row in enumerate(rows)
            if bool((row.get("handoff") or {}).get("would_handoff", False))
        ]
        finite_observations = _trace_vectors_finite(
            rows,
            fields=("qpos_before", "qvel_before", "env_state_before"),
        )
        finite_actions = _trace_vectors_finite(
            rows,
            fields=("proposed_action", "dispatched_action", "applied_action"),
        )
        termination = str(arm.get("termination_reason", ""))
        run_completed = bool(arm.get("executed")) and not (
            termination.startswith("execution_exception")
            or termination == "execution_fixture_recheck_blocked"
            or not termination
        )
        collision = "collision" in termination
        hard_stop = bool(
            run_completed
            and termination
            not in {"would_handoff", "return_horizon_420", "backend_done"}
        )
        safety = classify_return_closed_loop_safety(
            ReturnSafetyFacts(
                forbidden_primitive_dispatched=bool(
                    arm.get("dig_or_dump_called", False)
                ),
                retry_attempted=int(arm.get("attempt_count", 0)) > 1,
                input_lineage_valid=not bool(arm.get("setup_blockers")),
                fixture_match_valid=not bool(arm.get("setup_blockers")),
                finite_observations=finite_observations,
                finite_actions=finite_actions,
                target_token_held_constant=_field_constant(
                    rows,
                    "target_token_sha256",
                    str(arm["target_token_sha256"]),
                ),
                dispatch_strategy_held_constant=_field_constant(
                    rows,
                    "dispatch_strategy_id",
                    str(arm["dispatch_strategy_id"]),
                ),
                hard_safety_stop=hard_stop,
                collision_detected=collision,
                handoff_would_fire=termination == "would_handoff",
                timeout_reached=termination == "return_horizon_420",
                neutral_requested=bool(termination),
                neutral_acknowledged=bool(
                    arm.get("neutral_acknowledged", False)
                ),
                run_completed=run_completed,
                step_count=sum(not bool(row.get("neutral_ack")) for row in rows),
            )
        ).as_dict()
        trajectory = _bucket_tip_trajectory(rows)
        trajectories[arm_id] = trajectory
        arm_results.append(
            {
                "arm_id": arm_id,
                "fixture_id": str(arm["fixture_id"]),
                "target_role": str(arm["target_role"]),
                "dispatch_strategy_id": str(arm["dispatch_strategy_id"]),
                "target_token_sha256": str(arm["target_token_sha256"]),
                "target_envelope": envelope.as_dict(),
                "other_target_envelope": other_envelope.as_dict(),
                "direct_token_geometry": {
                    "assessment_kind": "direct_token_geometry_only",
                    "official_handoff_equivalent": False,
                    "own_target": _entry_summary(envelope_rows),
                    "other_target": _entry_summary(other_envelope_rows),
                },
                "official_handoff": {
                    "observed": bool(official_handoff_frames),
                    "first_frame": (
                        official_handoff_frames[0]
                        if official_handoff_frames
                        else None
                    ),
                    "source": "injected_resolved_official_gate",
                },
                "target_envelope_final": (
                    envelope_rows[-1] if envelope_rows else None
                ),
                "other_target_envelope_final": (
                    other_envelope_rows[-1] if other_envelope_rows else None
                ),
                "action_continuity": continuity,
                "action_limit_intervention": _limit_intervention_summary(rows),
                "safety": safety,
                "bucket_tip_trajectory_frame_count": len(trajectory),
            }
        )

    by_key = {
        (item["fixture_id"], item["target_role"], item["dispatch_strategy_id"]): item
        for item in arm_results
    }
    pair_results: list[dict[str, Any]] = []
    fixture_ids = sorted({item["fixture_id"] for item in arm_results})
    for fixture_id in fixture_ids:
        for strategy in (
            LEGACY_TEMPORAL_DISPATCH,
            LATEST_CURRENT_CHUNK_DIAGNOSTIC,
        ):
            original = by_key[(fixture_id, "original", strategy)]
            alternate = by_key[(fixture_id, "alternate", strategy)]
            separation = _separation(
                trajectories[original["arm_id"]],
                trajectories[alternate["arm_id"]],
            )
            pair_results.append(
                {
                    "fixture_id": fixture_id,
                    "dispatch_strategy_id": strategy,
                    "original_arm_id": original["arm_id"],
                    "alternate_arm_id": alternate["arm_id"],
                    "trajectory_separation": separation,
                    "original_final_target_entered": _final_entered(original),
                    "alternate_final_target_entered": _final_entered(alternate),
                    "original_final_other_target_entered": (
                        _final_other_entered(original)
                    ),
                    "alternate_final_other_target_entered": (
                        _final_other_entered(alternate)
                    ),
                    "both_own_direct_token_envelopes_entered": bool(
                        _final_entered(original) and _final_entered(alternate)
                    ),
                    "cross_envelope_entry_observed": bool(
                        _final_other_entered(original)
                        or _final_other_entered(alternate)
                    ),
                }
            )
    comparisons = [
        _compare_dispatches(
            fixture_id,
            pair_results=pair_results,
            by_key=by_key,
        )
        for fixture_id in fixture_ids
    ]
    return {
        "schema": RESULTS_SCHEMA,
        "status": "evaluated",
        "diagnostic_only": True,
        "promotion_eligible": False,
        "runtime_default_changed": False,
        "action_discontinuity_threshold": threshold.astype(float).tolist(),
        "arm_count": len(arm_results),
        "pair_count": len(pair_results),
        "arm_results": arm_results,
        "target_pair_results": pair_results,
        "fixture_dispatch_comparisons": comparisons,
    }


def _envelope_assessments(
    rows: Sequence[Mapping[str, Any]],
    *,
    envelope: ReturnTargetEnvelope,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        env = np.asarray(row.get("env_state_after", ()), dtype=np.float32).reshape(-1)
        qpos = np.asarray(row.get("qpos_after", ()), dtype=np.float32).reshape(-1)
        qvel = np.asarray(row.get("qvel_after", ()), dtype=np.float32).reshape(-1)
        if env.size <= ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX:
            continue
        assessment = assess_return_target_envelope(
            envelope=envelope,
            long_norm=float(env[ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX]),
            short_norm=float(env[ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX]),
            local_depth_m=float(
                env[ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX]
            ),
            qpos=qpos,
            qvel=qvel,
            dig_contact=bool(
                env[ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX] >= 0.5
            ),
        )
        results.append({"frame_index": index, **assessment.as_dict()})
    return results


def _bucket_tip_trajectory(rows: Sequence[Mapping[str, Any]]) -> np.ndarray:
    values: list[list[float]] = []
    for row in rows:
        env = np.asarray(row.get("env_state_after", ()), dtype=np.float32).reshape(-1)
        stop = ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX + 3
        if env.size >= stop and np.isfinite(env[ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX:stop]).all():
            values.append(
                env[ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX:stop]
                .astype(float)
                .tolist()
            )
    return np.asarray(values, dtype=np.float32).reshape(-1, 3)


def _separation(original: np.ndarray, alternate: np.ndarray) -> dict[str, Any]:
    if len(original) < 1 or len(alternate) < 1:
        return {"status": "not_identifiable", "reason": "trajectory_missing"}
    return {
        "status": "measured",
        **measure_return_trajectory_separation(original, alternate).as_dict(),
    }


def _compare_dispatches(
    fixture_id: str,
    *,
    pair_results: Sequence[Mapping[str, Any]],
    by_key: Mapping[tuple[str, str, str], Mapping[str, Any]],
) -> dict[str, Any]:
    pairs = {
        str(item["dispatch_strategy_id"]): item
        for item in pair_results
        if item["fixture_id"] == fixture_id
    }
    legacy_split = bool(
        pairs[LEGACY_TEMPORAL_DISPATCH]["trajectory_separation"].get(
            "separated", False
        )
    )
    latest_split = bool(
        pairs[LATEST_CURRENT_CHUNK_DIAGNOSTIC]["trajectory_separation"].get(
            "separated", False
        )
    )
    latest_quality_worse = _latest_quality_worse(fixture_id, by_key=by_key)
    safe_valid = all(
        bool(by_key[(fixture_id, role, strategy)]["safety"]["safe"])
        and bool(
            by_key[(fixture_id, role, strategy)]["safety"]["valid_artifact"]
        )
        for role in ("original", "alternate")
        for strategy in (
            LEGACY_TEMPORAL_DISPATCH,
            LATEST_CURRENT_CHUNK_DIAGNOSTIC,
        )
    )
    if not safe_valid:
        pattern = "inconclusive_invalid_or_safety_interrupted"
    elif legacy_split:
        pattern = (
            "both_dispatches_separate_latest_quality_worse"
            if latest_split and latest_quality_worse
            else "legacy_separates_targets"
        )
    elif latest_split:
        pattern = "legacy_converges_latest_separates"
    else:
        pattern = "both_dispatches_converge"
    return {
        "fixture_id": fixture_id,
        "legacy_targets_separated": legacy_split,
        "latest_current_targets_separated": latest_split,
        "latest_current_action_quality_worse": latest_quality_worse,
        "all_four_arms_safe_valid": safe_valid,
        "diagnostic_pattern": pattern,
        "causal_claim_limit": (
            "bounded Unity Return diagnostic only; latest-current is not a "
            "promotion candidate"
        ),
    }


def _latest_quality_worse(
    fixture_id: str,
    *,
    by_key: Mapping[tuple[str, str, str], Mapping[str, Any]],
) -> bool:
    def total(strategy: str, field: str) -> int:
        return sum(
            int(
                (
                    by_key[(fixture_id, role, strategy)].get(
                        "action_continuity"
                    )
                    or {}
                ).get(field, 0)
            )
            for role in ("original", "alternate")
        )

    return bool(
        total(LATEST_CURRENT_CHUNK_DIAGNOSTIC, "discontinuity_count")
        > total(LEGACY_TEMPORAL_DISPATCH, "discontinuity_count")
        or total(LATEST_CURRENT_CHUNK_DIAGNOSTIC, "boundary_touch_count")
        > total(LEGACY_TEMPORAL_DISPATCH, "boundary_touch_count")
        or total(LATEST_CURRENT_CHUNK_DIAGNOSTIC, "boundary_exceed_count")
        > total(LEGACY_TEMPORAL_DISPATCH, "boundary_exceed_count")
        or _p95_delta_worse(fixture_id, by_key=by_key)
    )


def _final_entered(value: Mapping[str, Any]) -> bool:
    final = value.get("target_envelope_final")
    return bool(
        isinstance(final, Mapping)
        and final.get(
            "direct_token_geometry_entered", final.get("entered", False)
        )
    )


def _final_other_entered(value: Mapping[str, Any]) -> bool:
    final = value.get("other_target_envelope_final")
    return bool(
        isinstance(final, Mapping)
        and final.get(
            "direct_token_geometry_entered", final.get("entered", False)
        )
    )


def _first_entry(values: Sequence[Mapping[str, Any]]) -> int | None:
    return next(
        (
            int(item["frame_index"])
            for item in values
            if bool(
                item.get(
                    "direct_token_geometry_entered",
                    item.get("entered", False),
                )
            )
        ),
        None,
    )


def _entry_summary(values: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    entered = [
        bool(
            item.get(
                "direct_token_geometry_entered", item.get("entered", False)
            )
        )
        for item in values
    ]
    max_consecutive, first_sustained = _entry_runs(entered)
    return {
        "frame_count": len(values),
        "first_entry_frame": _first_entry(values),
        "max_consecutive_entry_frames": max_consecutive,
        "required_sustained_frames": (
            RETURN_TRAJECTORY_SEPARATION_HOLD_FRAMES
        ),
        "first_sustained_entry_frame": first_sustained,
        "final": values[-1] if values else None,
    }


def _entry_runs(values: Sequence[bool]) -> tuple[int, int | None]:
    maximum = 0
    current = 0
    start = 0
    first_sustained: int | None = None
    required = RETURN_TRAJECTORY_SEPARATION_HOLD_FRAMES
    for index, entered in enumerate(values):
        if entered:
            if current == 0:
                start = index
            current += 1
            maximum = max(maximum, current)
            if current >= required and first_sustained is None:
                first_sustained = start
        else:
            current = 0
    return maximum, first_sustained


def _p95_delta_worse(
    fixture_id: str,
    *,
    by_key: Mapping[tuple[str, str, str], Mapping[str, Any]],
) -> bool:
    def maximum(strategy: str) -> np.ndarray:
        arrays = [
            np.asarray(
                (
                    by_key[(fixture_id, role, strategy)].get(
                        "action_continuity"
                    )
                    or {}
                ).get("p95_abs_delta_by_axis", [0.0] * 4),
                dtype=np.float64,
            )
            for role in ("original", "alternate")
        ]
        return np.max(np.stack(arrays, axis=0), axis=0)

    return bool(
        np.any(
            maximum(LATEST_CURRENT_CHUNK_DIAGNOSTIC)
            > maximum(LEGACY_TEMPORAL_DISPATCH)
        )
    )


def _field_constant(
    rows: Sequence[Mapping[str, Any]], field: str, expected: str
) -> bool:
    return bool(rows) and all(str(row.get(field, "")) == expected for row in rows)


def _trace_vectors_finite(
    rows: Sequence[Mapping[str, Any]],
    *,
    fields: Sequence[str],
) -> bool:
    if not rows:
        return False
    for row in rows:
        for field in fields:
            values = np.asarray(row.get(field, ()), dtype=np.float64).reshape(-1)
            if not values.size or not np.isfinite(values).all():
                return False
    return True


def _limit_intervention_summary(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    values = np.asarray(
        [row.get("action_limit_intervention", ()) for row in rows]
    )
    if values.shape != (len(rows), 4):
        return {
            "telemetry_valid": False,
            "frame_count": len(rows),
            "intervention_frame_count": None,
            "intervention_count_by_axis": None,
        }
    mask = values.astype(bool)
    return {
        "telemetry_valid": bool(
            all(
                row.get("action_application_telemetry_valid") is True
                for row in rows
            )
        ),
        "frame_count": len(rows),
        "intervention_frame_count": int(np.count_nonzero(np.any(mask, axis=1))),
        "intervention_count_by_axis": np.count_nonzero(mask, axis=0)
        .astype(int)
        .tolist(),
    }


def _read_trace(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"trace row is not a mapping: {path}")
                rows.append(value)
    return rows


__all__ = ["RESULTS_SCHEMA", "evaluate_return_closed_loop_results"]
