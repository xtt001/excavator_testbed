"""Pure goal-following tracking benchmark and decision contract.

The benchmark compares continuous goals, safe reference paths, actual ACT
execution, and observed effects.  It is intentionally offline-only: nearest
expert matching is diagnostic evidence, and no report can unlock live
execution or change a planner default.
"""

from __future__ import annotations

import copy
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

import numpy as np

from testbed.data.terrain_signature import (
    TERRAIN_SIGNATURE_FIELD_NAMES,
    TerrainSignatureV1,
    build_terrain_signature_v1,
)
from testbed.eval.goal_following_metrics import (
    ACT_TRACKING_MARGIN_M,
    PHASE_POINT_COUNT,
    compute_goal_following_tracking_metrics,
    finite_float,
    finite_vector,
)
from testbed.planner.primitive.coverage.continuous_goal import (
    ContinuousCutGoal,
    ContinuousGoalContractError,
)

GOAL_FOLLOWING_BENCHMARK_SCHEMA = "goal_following_benchmark_v1"
MINIMUM_REPEATED_FAILURES = 2
DECISIONS = frozenset(
    {
        "reference_or_goal_primary",
        "act_tracking_primary",
        "effect_calibration_primary",
        "insufficient_evidence",
    }
)
SPLITS = frozenset({"train", "source_heldout", "rollout_eval"})
_RUNTIME_BINDING_KEYS = frozenset(
    {
        "episode_id",
        "source_episode_id",
        "primitive_episode_id",
        "expert_id",
        "expert_episode_id",
        "exemplar_id",
        "paired_return_exemplar_id",
    }
)


@dataclass(frozen=True)
class GoalFollowingCycleInput:
    """Complete input for one completed dig tracking sample."""

    cycle_id: str
    split: str
    source_episode_id: int | None
    rollout_cycle: int | None
    is_first_dig: bool
    target_region: str
    remaining_depth_m: float
    continuous_goal: Mapping[str, Any]
    handoff_qpos: Sequence[float]
    handoff_qvel: Sequence[float]
    terrain_signature: TerrainSignatureV1
    planned_entry_xz_m: Sequence[float]
    actual_entry_xz_m: Sequence[float]
    planned_exit_xz_m: Sequence[float]
    actual_exit_xz_m: Sequence[float]
    planned_terrain_relative_depth_m: float
    actual_terrain_relative_depth_m: float
    planned_duration_s: float
    actual_duration_s: float
    reference_qpos_path: Sequence[Sequence[float]] | np.ndarray
    actual_qpos_path: Sequence[Sequence[float]] | np.ndarray
    reference_timestamps_s: Sequence[float] | np.ndarray
    actual_timestamps_s: Sequence[float] | np.ndarray
    reference_phase: Sequence[float] | np.ndarray
    actual_phase: Sequence[float] | np.ndarray
    qpos_abs_error_bound: Sequence[Sequence[float]] | np.ndarray
    reference_worktool_path: Sequence[Sequence[float]] | np.ndarray
    actual_worktool_path: Sequence[Sequence[float]] | np.ndarray
    reference_safe: bool
    support_status: str
    goal_valid: bool
    planned_effect: Sequence[float] = ()
    actual_effect: Sequence[float] = ()
    effect_abs_tolerance: Sequence[float] = ()


@dataclass(frozen=True)
class GoalMatchingFeatures:
    """Whole-goal diagnostic features with no episode/expert binding."""

    continuous_goal: Mapping[str, Any]
    handoff_qpos: tuple[float, float, float, float]
    handoff_qvel: tuple[float, float, float, float]
    terrain_signature: tuple[float, ...]
    numeric_feature_names: tuple[str, ...]
    numeric_values: tuple[float, ...]
    categorical_features: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class DiagnosticNearestExpertMatch:
    window_id: str
    distance: float
    diagnostic_only: bool = True
    runtime_binding_allowed: bool = False


@dataclass(frozen=True)
class GoalFollowingCycleMetrics:
    """Metrics and decision evidence for one completed dig cycle."""

    cycle_id: str
    geometry: Mapping[str, Any]
    phase_normalized_qpos: Mapping[str, Any]
    raw_time_qpos: Mapping[str, Any]
    dtw_qpos: Mapping[str, Any]
    worktool_tracking_3d: Mapping[str, Any]
    calibrated_qpos_tube_breach: bool
    worktool_margin_breach: bool
    tracking_breach: bool
    effect_evidence_available: bool
    effect_mismatch: bool
    reference_safe: bool
    support_status: str
    goal_valid: bool
    strata: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "geometry": copy.deepcopy(dict(self.geometry)),
            "phase_normalized_qpos": dict(self.phase_normalized_qpos),
            "raw_time_qpos": dict(self.raw_time_qpos),
            "dtw_qpos": dict(self.dtw_qpos),
            "worktool_tracking_3d": dict(self.worktool_tracking_3d),
            "calibrated_qpos_tube_breach": (self.calibrated_qpos_tube_breach),
            "worktool_margin_breach": self.worktool_margin_breach,
            "tracking_breach": self.tracking_breach,
            "effect_evidence_available": self.effect_evidence_available,
            "effect_mismatch": self.effect_mismatch,
            "reference_safe": self.reference_safe,
            "support_status": self.support_status,
            "goal_valid": self.goal_valid,
            "strata": dict(self.strata),
        }


@dataclass(frozen=True)
class GoalFollowingBenchmarkReport:
    """Offline-only benchmark report with one of four decisions."""

    decision: str
    cycles: tuple[GoalFollowingCycleMetrics, ...]
    remaining_depth_quantiles: Mapping[str, Any]
    stratified_counts: tuple[Mapping[str, Any], ...]
    decision_evidence: Mapping[str, Any]
    act_retraining_allowed: bool
    live_unlocked: bool = False
    promotion_eligible: bool = False
    schema: str = GOAL_FOLLOWING_BENCHMARK_SCHEMA

    def __post_init__(self) -> None:
        if self.decision not in DECISIONS:
            raise ValueError("benchmark decision is outside the frozen set")
        if self.live_unlocked or self.promotion_eligible:
            raise ValueError("goal-following benchmark cannot unlock live execution")
        if self.act_retraining_allowed != (self.decision == "act_tracking_primary"):
            raise ValueError("only act_tracking_primary may allow ACT retraining")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "decision": self.decision,
            "cycles": [cycle.as_dict() for cycle in self.cycles],
            "remaining_depth_quantiles": dict(self.remaining_depth_quantiles),
            "stratified_counts": [dict(row) for row in self.stratified_counts],
            "decision_evidence": dict(self.decision_evidence),
            "act_retraining_allowed": self.act_retraining_allowed,
            "live_unlocked": False,
            "promotion_eligible": False,
        }


def build_matching_features(
    *,
    continuous_goal: Mapping[str, Any],
    handoff_qpos: Sequence[float],
    handoff_qvel: Sequence[float],
    terrain_signature: TerrainSignatureV1 | Mapping[str, Any],
) -> GoalMatchingFeatures:
    """Build whole-goal features for offline nearest-expert diagnostics."""

    goal = _complete_continuous_goal(continuous_goal)
    qpos = finite_vector(handoff_qpos, 4, label="handoff_qpos")
    qvel = finite_vector(handoff_qvel, 4, label="handoff_qvel")
    signature = _terrain_signature(terrain_signature)
    numeric: dict[str, float] = {}
    categorical: dict[str, str] = {}
    _flatten_goal_features(
        goal,
        path="continuous_goal",
        numeric=numeric,
        categorical=categorical,
    )
    for index, value in enumerate(qpos):
        numeric[f"handoff_qpos[{index}]"] = value
    for index, value in enumerate(qvel):
        numeric[f"handoff_qvel[{index}]"] = value
    for name, value in zip(
        TERRAIN_SIGNATURE_FIELD_NAMES,
        signature.values,
        strict=True,
    ):
        numeric[f"terrain_signature.{name}"] = value
    numeric_items = tuple(sorted(numeric.items()))
    return GoalMatchingFeatures(
        continuous_goal=goal,
        handoff_qpos=qpos,
        handoff_qvel=qvel,
        terrain_signature=signature.values,
        numeric_feature_names=tuple(name for name, _ in numeric_items),
        numeric_values=tuple(value for _, value in numeric_items),
        categorical_features=tuple(sorted(categorical.items())),
    )


def diagnostic_nearest_expert(
    query: GoalMatchingFeatures,
    candidates: Mapping[str, GoalMatchingFeatures],
) -> DiagnosticNearestExpertMatch:
    """Find the nearest whole-goal expert for diagnostics, never binding."""

    if not candidates:
        raise ValueError("nearest-expert diagnostic requires candidates")
    best_id = ""
    best_distance = float("inf")
    for raw_id, candidate in candidates.items():
        window_id = str(raw_id).strip()
        if not window_id:
            raise ValueError("diagnostic candidate window id must be non-empty")
        distance = _matching_distance(query, candidate)
        if distance < best_distance:
            best_id = window_id
            best_distance = distance
    if not best_id or not math.isfinite(best_distance):
        raise ValueError(
            "nearest-expert diagnostic has no structurally compatible candidate"
        )
    return DiagnosticNearestExpertMatch(
        window_id=best_id,
        distance=best_distance,
    )


def evaluate_goal_following_cycle(
    cycle: GoalFollowingCycleInput,
) -> GoalFollowingCycleMetrics:
    """Compute geometry, trajectory, DTW, and 3D tracking metrics."""

    cycle_id = str(cycle.cycle_id).strip()
    if not cycle_id:
        raise ValueError("cycle_id must be non-empty")
    split = str(cycle.split).strip()
    if split not in SPLITS:
        raise ValueError(f"unsupported goal-following split: {split!r}")
    target_region = str(cycle.target_region).strip()
    if not target_region:
        raise ValueError("target_region must be non-empty")
    if split == "source_heldout" and cycle.source_episode_id not in {33, 34}:
        raise ValueError(
            "source_heldout benchmark cycles must come from sources 33 or 34"
        )
    if split == "train" and cycle.source_episode_id in {33, 34}:
        raise ValueError("held-out sources 33/34 cannot enter train metrics")
    if split == "rollout_eval" and cycle.rollout_cycle is None:
        raise ValueError("rollout_eval cycles require rollout_cycle")
    _complete_continuous_goal(cycle.continuous_goal)
    finite_vector(cycle.handoff_qpos, 4, label="handoff_qpos")
    finite_vector(cycle.handoff_qvel, 4, label="handoff_qvel")
    _terrain_signature(cycle.terrain_signature)

    finite_float(
        cycle.remaining_depth_m,
        label="remaining_depth_m",
    )
    tracking = compute_goal_following_tracking_metrics(
        planned_entry_xz_m=cycle.planned_entry_xz_m,
        actual_entry_xz_m=cycle.actual_entry_xz_m,
        planned_exit_xz_m=cycle.planned_exit_xz_m,
        actual_exit_xz_m=cycle.actual_exit_xz_m,
        planned_terrain_relative_depth_m=(cycle.planned_terrain_relative_depth_m),
        actual_terrain_relative_depth_m=(cycle.actual_terrain_relative_depth_m),
        planned_duration_s=cycle.planned_duration_s,
        actual_duration_s=cycle.actual_duration_s,
        reference_qpos_path=cycle.reference_qpos_path,
        actual_qpos_path=cycle.actual_qpos_path,
        reference_timestamps_s=cycle.reference_timestamps_s,
        actual_timestamps_s=cycle.actual_timestamps_s,
        reference_phase=cycle.reference_phase,
        actual_phase=cycle.actual_phase,
        qpos_abs_error_bound=cycle.qpos_abs_error_bound,
        reference_worktool_path=cycle.reference_worktool_path,
        actual_worktool_path=cycle.actual_worktool_path,
    )

    effect_available, effect_mismatch = _effect_evidence(cycle)
    support_status = str(cycle.support_status).strip().lower()
    if support_status not in {"supported", "ood", "unknown"}:
        raise ValueError("support_status must be supported, ood, or unknown")
    if not isinstance(cycle.reference_safe, bool):
        raise ValueError("reference_safe must be a bool")
    if not isinstance(cycle.goal_valid, bool):
        raise ValueError("goal_valid must be a bool")
    return GoalFollowingCycleMetrics(
        cycle_id=cycle_id,
        geometry=tracking.geometry,
        phase_normalized_qpos=tracking.phase_normalized_qpos,
        raw_time_qpos=tracking.raw_time_qpos,
        dtw_qpos=tracking.dtw_qpos,
        worktool_tracking_3d=tracking.worktool_tracking_3d,
        calibrated_qpos_tube_breach=(tracking.calibrated_qpos_tube_breach),
        worktool_margin_breach=tracking.worktool_margin_breach,
        tracking_breach=tracking.tracking_breach,
        effect_evidence_available=effect_available,
        effect_mismatch=effect_mismatch,
        reference_safe=cycle.reference_safe,
        support_status=support_status,
        goal_valid=cycle.goal_valid,
        strata={
            "dig_history": ("first_dig" if cycle.is_first_dig else "repeated_dig"),
            "target_region": target_region,
            "remaining_depth_quantile": None,
            "split": split,
            "rollout_cycle": cycle.rollout_cycle,
        },
    )


def run_goal_following_benchmark(
    cycles: Sequence[GoalFollowingCycleInput],
) -> GoalFollowingBenchmarkReport:
    """Evaluate completed cycles and emit exactly one frozen decision."""

    if not cycles:
        return GoalFollowingBenchmarkReport(
            decision="insufficient_evidence",
            cycles=(),
            remaining_depth_quantiles={
                "fit_partition": "train",
                "sample_count": 0,
                "status": "missing_train_evidence",
            },
            stratified_counts=(),
            decision_evidence={
                "reason": "no_completed_dig_cycles",
                "reference_or_goal_issue_count": 0,
                "tracking_breach_count": 0,
                "effect_mismatch_count": 0,
            },
            act_retraining_allowed=False,
        )
    metrics = [evaluate_goal_following_cycle(cycle) for cycle in cycles]
    quantile_contract = _remaining_depth_quantile_contract(cycles)
    stratified: list[GoalFollowingCycleMetrics] = []
    for cycle, metric in zip(cycles, metrics, strict=True):
        strata = dict(metric.strata)
        strata["remaining_depth_quantile"] = _remaining_depth_bin(
            float(cycle.remaining_depth_m),
            quantile_contract["edges_m"],
        )
        stratified.append(replace(metric, strata=strata))

    reference_issues = [
        metric
        for metric in stratified
        if (
            not metric.reference_safe
            or not metric.goal_valid
            or metric.support_status != "supported"
        )
    ]
    tracking_breaches = [metric for metric in stratified if metric.tracking_breach]
    effect_mismatches = [
        metric
        for metric in stratified
        if (
            metric.effect_evidence_available
            and metric.effect_mismatch
            and not metric.tracking_breach
        )
    ]
    if reference_issues:
        decision = "reference_or_goal_primary"
        reason = "goal_support_or_safe_reference_invalid"
    elif len(tracking_breaches) >= MINIMUM_REPEATED_FAILURES:
        decision = "act_tracking_primary"
        reason = "safe_reference_repeated_tracking_breach"
    elif len(effect_mismatches) >= MINIMUM_REPEATED_FAILURES:
        decision = "effect_calibration_primary"
        reason = "tracked_reference_repeated_effect_mismatch"
    else:
        decision = "insufficient_evidence"
        reason = "no_primary_failure_has_repeated_support"
    return GoalFollowingBenchmarkReport(
        decision=decision,
        cycles=tuple(stratified),
        remaining_depth_quantiles={
            key: (list(value) if isinstance(value, tuple) else value)
            for key, value in quantile_contract.items()
        },
        stratified_counts=_stratified_counts(stratified),
        decision_evidence={
            "reason": reason,
            "minimum_repeated_failures": MINIMUM_REPEATED_FAILURES,
            "reference_or_goal_issue_count": len(reference_issues),
            "tracking_breach_count": len(tracking_breaches),
            "effect_mismatch_count": len(effect_mismatches),
            "worktool_tracking_margin_m": ACT_TRACKING_MARGIN_M,
        },
        act_retraining_allowed=decision == "act_tracking_primary",
    )


def _complete_continuous_goal(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    goal = copy.deepcopy(dict(value))
    _reject_runtime_bindings(goal, path="continuous_goal")
    try:
        return ContinuousCutGoal.from_mapping(goal).as_dict()
    except ContinuousGoalContractError as exc:
        raise ValueError(f"continuous goal is invalid: {exc}") from exc


def _terrain_signature(
    value: TerrainSignatureV1 | Mapping[str, Any],
) -> TerrainSignatureV1:
    if isinstance(value, TerrainSignatureV1):
        return value
    payload = dict(value)
    if "values" in payload:
        names = tuple(payload.get("field_names", ()))
        return TerrainSignatureV1(
            values=tuple(payload["values"]),
            field_names=names,
            schema=str(payload.get("schema", "")),
        )
    return build_terrain_signature_v1(payload)


def _reject_runtime_bindings(value: Any, *, path: str) -> None:
    if isinstance(value, Mapping):
        for raw_key, child in value.items():
            key = str(raw_key)
            if key in _RUNTIME_BINDING_KEYS:
                raise ValueError(f"{path}.{key} is a forbidden runtime binding")
            _reject_runtime_bindings(child, path=f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        for index, child in enumerate(value):
            _reject_runtime_bindings(child, path=f"{path}[{index}]")


def _flatten_goal_features(
    value: Any,
    *,
    path: str,
    numeric: dict[str, float],
    categorical: dict[str, str],
) -> None:
    if isinstance(value, Mapping):
        for key in sorted(value):
            if key == "goal_id":
                continue
            _flatten_goal_features(
                value[key],
                path=f"{path}.{key}",
                numeric=numeric,
                categorical=categorical,
            )
        return
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        for index, child in enumerate(value):
            _flatten_goal_features(
                child,
                path=f"{path}[{index}]",
                numeric=numeric,
                categorical=categorical,
            )
        return
    if isinstance(value, bool):
        categorical[path] = "true" if value else "false"
        return
    if isinstance(value, (int, float, np.number)):
        numeric[path] = finite_float(value, label=path)
        return
    if isinstance(value, str):
        categorical[path] = value
        return
    if value is None:
        categorical[path] = "null"
        return
    raise ValueError(f"unsupported matching feature at {path}")


def _matching_distance(
    left: GoalMatchingFeatures,
    right: GoalMatchingFeatures,
) -> float:
    if left.numeric_feature_names != right.numeric_feature_names:
        return float("inf")
    left_values = np.asarray(left.numeric_values, dtype=np.float64)
    right_values = np.asarray(right.numeric_values, dtype=np.float64)
    numeric_distance_squared = float(np.sum(np.square(left_values - right_values)))
    left_categories = dict(left.categorical_features)
    right_categories = dict(right.categorical_features)
    if set(left_categories) != set(right_categories):
        return float("inf")
    categorical_mismatches = sum(
        left_categories[name] != right_categories[name] for name in left_categories
    )
    return float(math.sqrt(numeric_distance_squared + categorical_mismatches))


def _effect_evidence(
    cycle: GoalFollowingCycleInput,
) -> tuple[bool, bool]:
    planned = np.asarray(cycle.planned_effect, dtype=np.float64)
    actual = np.asarray(cycle.actual_effect, dtype=np.float64)
    tolerance = np.asarray(cycle.effect_abs_tolerance, dtype=np.float64)
    if planned.size == actual.size == tolerance.size == 0:
        return False, False
    if (
        planned.ndim != 1
        or actual.shape != planned.shape
        or tolerance.shape != planned.shape
        or planned.size == 0
        or not np.isfinite(planned).all()
        or not np.isfinite(actual).all()
        or not np.isfinite(tolerance).all()
        or np.any(tolerance < 0.0)
    ):
        raise ValueError(
            "effect evidence must be equal-length finite 1D vectors with "
            "non-negative tolerances"
        )
    return True, bool(np.any(np.abs(actual - planned) > tolerance))


def _remaining_depth_quantile_contract(
    cycles: Sequence[GoalFollowingCycleInput],
) -> dict[str, Any]:
    train_values = np.asarray(
        [
            finite_float(
                cycle.remaining_depth_m,
                label=f"{cycle.cycle_id}.remaining_depth_m",
            )
            for cycle in cycles
            if cycle.split == "train"
        ],
        dtype=np.float64,
    )
    if train_values.size == 0:
        raise ValueError("remaining-depth quantiles require non-empty train evidence")
    probabilities = (0.0, 0.25, 0.5, 0.75, 1.0)
    edges = tuple(float(value) for value in np.quantile(train_values, probabilities))
    return {
        "fit_partition": "train",
        "sample_count": int(train_values.size),
        "probabilities": probabilities,
        "edges_m": edges,
        "minimum_m": float(np.min(train_values)),
        "maximum_m": float(np.max(train_values)),
    }


def _remaining_depth_bin(
    value: float,
    edges: Sequence[float],
) -> str:
    internal = np.asarray(tuple(edges)[1:-1], dtype=np.float64)
    index = int(np.searchsorted(internal, value, side="right"))
    return f"q{index + 1}"


def _stratified_counts(
    metrics: Sequence[GoalFollowingCycleMetrics],
) -> tuple[Mapping[str, Any], ...]:
    keys = [
        (
            str(metric.strata["dig_history"]),
            str(metric.strata["target_region"]),
            str(metric.strata["remaining_depth_quantile"]),
            str(metric.strata["split"]),
            metric.strata["rollout_cycle"],
        )
        for metric in metrics
    ]
    counts = Counter(keys)
    return tuple(
        {
            "dig_history": key[0],
            "target_region": key[1],
            "remaining_depth_quantile": key[2],
            "split": key[3],
            "rollout_cycle": key[4],
            "count": count,
        }
        for key, count in sorted(
            counts.items(),
            key=lambda item: tuple(str(value) for value in item[0]),
        )
    )


__all__ = [
    "ACT_TRACKING_MARGIN_M",
    "DECISIONS",
    "DiagnosticNearestExpertMatch",
    "GOAL_FOLLOWING_BENCHMARK_SCHEMA",
    "GoalFollowingBenchmarkReport",
    "GoalFollowingCycleInput",
    "GoalFollowingCycleMetrics",
    "GoalMatchingFeatures",
    "MINIMUM_REPEATED_FAILURES",
    "PHASE_POINT_COUNT",
    "build_matching_features",
    "diagnostic_nearest_expert",
    "evaluate_goal_following_cycle",
    "run_goal_following_benchmark",
]
