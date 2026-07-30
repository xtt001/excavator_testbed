"""Pure, fail-closed decisions for Goal-Following ACT and stage gates."""

from __future__ import annotations

from dataclasses import dataclass

BENCHMARK_DECISIONS = frozenset(
    {
        "reference_or_goal_primary",
        "act_tracking_primary",
        "effect_calibration_primary",
        "insufficient_evidence",
    }
)
CONDITION_IDS = ("E0", "G1", "W1")
STAGE_NAMES = (
    "offline_e0_g1_w1",
    "unity_3d_sweep",
    "bounded_live_e0_g1_w1",
    "g1_single_1x10",
)


@dataclass(frozen=True)
class ActRouteDecision:
    accepted: bool
    reason: str
    runtime_act_frozen: bool
    existing_goal_conditioned_retrain_allowed: bool
    trajectory_conditioned_v1_allowed: bool
    planner_threshold_masking_allowed: bool
    default_behavior_changed: bool


def evaluate_act_route(
    *,
    benchmark_decision: str,
    existing_goal_conditioned_retrain_completed: bool = False,
    heldout_tracking_within_margin: bool | None = None,
    planner_threshold_masking_requested: bool = False,
) -> ActRouteDecision:
    """Apply the only allowed ACT decision tree.

    Training permission never changes the runtime/default checkpoint.  That
    remains frozen until a separate promotion approval.
    """

    if type(existing_goal_conditioned_retrain_completed) is not bool:
        return _act_route(
            accepted=False,
            reason="existing_retrain_completed_type_invalid",
        )
    if (
        heldout_tracking_within_margin is not None
        and type(heldout_tracking_within_margin) is not bool
    ):
        return _act_route(
            accepted=False,
            reason="heldout_tracking_within_margin_type_invalid",
        )
    if type(planner_threshold_masking_requested) is not bool:
        return _act_route(
            accepted=False,
            reason="planner_threshold_masking_requested_type_invalid",
        )
    if benchmark_decision not in BENCHMARK_DECISIONS:
        return _act_route(accepted=False, reason="benchmark_decision_invalid")
    if planner_threshold_masking_requested:
        return _act_route(
            accepted=False,
            reason="planner_threshold_masking_forbidden",
        )
    if benchmark_decision != "act_tracking_primary":
        return _act_route(
            accepted=True,
            reason=f"act_frozen:{benchmark_decision}",
        )
    if not existing_goal_conditioned_retrain_completed:
        if heldout_tracking_within_margin is not None:
            return _act_route(
                accepted=False,
                reason="heldout_result_without_existing_retrain",
            )
        return _act_route(
            accepted=True,
            reason="retrain_existing_goal_conditioned_act",
            existing_retrain=True,
        )
    if heldout_tracking_within_margin is None:
        return _act_route(
            accepted=False,
            reason="heldout_tracking_result_required",
        )
    if heldout_tracking_within_margin:
        return _act_route(
            accepted=True,
            reason="existing_goal_conditioned_act_within_margin",
        )
    return _act_route(
        accepted=True,
        reason="trajectory_conditioned_act_v1_allowed",
        trajectory_v1=True,
    )


def _act_route(
    *,
    accepted: bool,
    reason: str,
    existing_retrain: bool = False,
    trajectory_v1: bool = False,
) -> ActRouteDecision:
    return ActRouteDecision(
        accepted=accepted,
        reason=reason,
        runtime_act_frozen=True,
        existing_goal_conditioned_retrain_allowed=existing_retrain,
        trajectory_conditioned_v1_allowed=trajectory_v1,
        planner_threshold_masking_allowed=False,
        default_behavior_changed=False,
    )


@dataclass(frozen=True)
class OfflineConditionEvidence:
    condition_id: str
    real_handoff_valid: bool
    complete_terrain_signature_valid: bool
    predictor_valid: bool
    calibrated_95_error_bound_valid: bool
    derived_return_envelope_valid: bool


@dataclass(frozen=True)
class SweepConditionEvidence:
    condition_id: str
    uncertainty_tube_passed: bool
    all_12_link_wall_witnesses_valid: bool


@dataclass(frozen=True)
class BoundedLiveConditionEvidence:
    condition_id: str
    attempt_count: int
    retry_count: int
    reset_valid: bool
    reset_fairness_valid: bool
    handoff_valid: bool
    goal_identity_valid: bool
    guard_3d_valid: bool
    tracking_valid: bool
    safety_valid: bool
    median_stop_valid: bool


@dataclass(frozen=True)
class FunctionalCycleEvidence:
    cycle_index: int
    goal_identity_valid: bool
    guard_3d_valid: bool
    tracking_valid: bool
    safety_valid: bool


@dataclass(frozen=True)
class FunctionalG1Evidence:
    condition_id: str
    attempt_count: int
    reset_count: int
    retry_count: int
    valid_dig_count: int
    dump_count: int
    handoff_count: int
    median_stop_valid: bool
    cycles: tuple[FunctionalCycleEvidence, ...]


@dataclass(frozen=True)
class GoalFollowingGateEvidence:
    offline_conditions: tuple[OfflineConditionEvidence, ...]
    sweep_conditions: tuple[SweepConditionEvidence, ...]
    bounded_live_conditions: tuple[BoundedLiveConditionEvidence, ...]
    functional_g1: FunctionalG1Evidence | None


@dataclass(frozen=True)
class GateStageResult:
    name: str
    status: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class GoalFollowingGateResult:
    stages: tuple[GateStageResult, ...]
    promotion_evidence_ready: bool
    auto_promotion_allowed: bool
    default_behavior_changed: bool


def evaluate_goal_following_gates(
    evidence: GoalFollowingGateEvidence,
) -> GoalFollowingGateResult:
    """Evaluate all four stages without permitting dependency bypass."""

    stages: list[GateStageResult] = []
    offline = _evaluate_offline(evidence.offline_conditions)
    stages.append(offline)
    if offline.status != "passed":
        return _blocked_result(stages)

    sweep = _evaluate_sweep(evidence.sweep_conditions)
    stages.append(sweep)
    if sweep.status != "passed":
        return _blocked_result(stages)

    live = _evaluate_bounded_live(evidence.bounded_live_conditions)
    stages.append(live)
    if live.status != "passed":
        return _blocked_result(stages)

    functional = _evaluate_functional(evidence.functional_g1)
    stages.append(functional)
    return GoalFollowingGateResult(
        stages=tuple(stages),
        promotion_evidence_ready=functional.status == "passed",
        auto_promotion_allowed=False,
        default_behavior_changed=False,
    )


def _evaluate_offline(
    conditions: tuple[OfflineConditionEvidence, ...],
) -> GateStageResult:
    inventory_reason = _condition_inventory_reason(conditions)
    if inventory_reason is not None:
        return _failed_stage(STAGE_NAMES[0], (inventory_reason,))
    by_id = {item.condition_id: item for item in conditions}
    reasons: list[str] = []
    fields = (
        ("real_handoff_valid", "real_handoff_invalid"),
        (
            "complete_terrain_signature_valid",
            "terrain_signature_incomplete",
        ),
        ("predictor_valid", "predictor_invalid"),
        (
            "calibrated_95_error_bound_valid",
            "calibrated_95_error_bound_invalid",
        ),
        (
            "derived_return_envelope_valid",
            "derived_return_envelope_invalid",
        ),
    )
    for condition_id in CONDITION_IDS:
        item = by_id[condition_id]
        for field, reason in fields:
            _validate_bool_field(
                reasons,
                prefix=condition_id,
                field=field,
                value=getattr(item, field),
                false_reason=reason,
            )
    return _stage(STAGE_NAMES[0], reasons)


def _evaluate_sweep(
    conditions: tuple[SweepConditionEvidence, ...],
) -> GateStageResult:
    inventory_reason = _condition_inventory_reason(conditions)
    if inventory_reason is not None:
        return _failed_stage(STAGE_NAMES[1], (inventory_reason,))
    by_id = {item.condition_id: item for item in conditions}
    reasons: list[str] = []
    for condition_id in CONDITION_IDS:
        item = by_id[condition_id]
        _validate_bool_field(
            reasons,
            prefix=condition_id,
            field="uncertainty_tube_passed",
            value=item.uncertainty_tube_passed,
            false_reason="uncertainty_tube_failed",
        )
        _validate_bool_field(
            reasons,
            prefix=condition_id,
            field="all_12_link_wall_witnesses_valid",
            value=item.all_12_link_wall_witnesses_valid,
            false_reason="link_wall_witnesses_invalid",
        )
    return _stage(STAGE_NAMES[1], reasons)


def _evaluate_bounded_live(
    conditions: tuple[BoundedLiveConditionEvidence, ...],
) -> GateStageResult:
    inventory_reason = _condition_inventory_reason(conditions)
    if inventory_reason is not None:
        return _failed_stage(STAGE_NAMES[2], (inventory_reason,))
    by_id = {item.condition_id: item for item in conditions}
    reasons: list[str] = []
    flag_fields = (
        ("reset_valid", "reset_invalid"),
        ("reset_fairness_valid", "reset_fairness_invalid"),
        ("handoff_valid", "handoff_invalid"),
        ("goal_identity_valid", "goal_identity_invalid"),
        ("guard_3d_valid", "guard_3d_invalid"),
        ("tracking_valid", "tracking_invalid"),
        ("safety_valid", "safety_invalid"),
        ("median_stop_valid", "median_stop_invalid"),
    )
    for condition_id in CONDITION_IDS:
        item = by_id[condition_id]
        _validate_int_field(
            reasons,
            prefix=condition_id,
            field="attempt_count",
            value=item.attempt_count,
            expected=1,
            mismatch_reason="attempt_count_not_one",
        )
        _validate_int_field(
            reasons,
            prefix=condition_id,
            field="retry_count",
            value=item.retry_count,
            expected=0,
            mismatch_reason="retry_forbidden",
        )
        for field, reason in flag_fields:
            _validate_bool_field(
                reasons,
                prefix=condition_id,
                field=field,
                value=getattr(item, field),
                false_reason=reason,
            )
    return _stage(STAGE_NAMES[2], reasons)


def _evaluate_functional(
    evidence: FunctionalG1Evidence | None,
) -> GateStageResult:
    if evidence is None:
        return _failed_stage(
            STAGE_NAMES[3],
            ("G1:functional_evidence_missing",),
        )
    reasons: list[str] = []
    if evidence.condition_id != "G1":
        reasons.append("functional_condition_not_G1")
    count_contracts = (
        ("attempt_count", 1, "attempt_count_not_one"),
        ("reset_count", 1, "reset_count_not_one"),
        ("retry_count", 0, "retry_forbidden"),
        ("valid_dig_count", 10, "valid_dig_count_not_10"),
        ("dump_count", 10, "dump_count_not_10"),
        ("handoff_count", 9, "handoff_count_not_9"),
    )
    for field, expected, reason in count_contracts:
        _validate_int_field(
            reasons,
            prefix="G1",
            field=field,
            value=getattr(evidence, field),
            expected=expected,
            mismatch_reason=reason,
        )
    _validate_bool_field(
        reasons,
        prefix="G1",
        field="median_stop_valid",
        value=evidence.median_stop_valid,
        false_reason="median_stop_invalid",
    )
    try:
        cycles = tuple(evidence.cycles)
    except TypeError:
        reasons.append("G1:cycles_type_invalid")
        cycles = ()
    valid_cycle_indices: list[int] = []
    display_cycle_indices: list[str] = []
    for position, cycle in enumerate(cycles):
        cycle_index = getattr(cycle, "cycle_index", None)
        display_cycle_indices.append(str(cycle_index))
        if type(cycle_index) is not int:
            reasons.append(
                f"G1:cycle_position_{position}:cycle_index_type_invalid"
            )
        else:
            valid_cycle_indices.append(cycle_index)
    if (
        len(cycles) != 10
        or len(valid_cycle_indices) != 10
        or set(valid_cycle_indices) != set(range(10))
    ):
        joined = ",".join(display_cycle_indices)
        reasons.append(f"G1:cycle_inventory_invalid:{joined}")
    cycle_fields = (
        ("goal_identity_valid", "goal_identity_invalid"),
        ("guard_3d_valid", "guard_3d_invalid"),
        ("tracking_valid", "tracking_invalid"),
        ("safety_valid", "safety_invalid"),
    )
    for position, cycle in enumerate(cycles):
        cycle_index = getattr(cycle, "cycle_index", None)
        label = (
            f"cycle_{cycle_index}"
            if type(cycle_index) is int
            else f"cycle_position_{position}"
        )
        for field, reason in cycle_fields:
            _validate_bool_field(
                reasons,
                prefix=f"G1:{label}",
                field=field,
                value=getattr(cycle, field, None),
                false_reason=reason,
            )
    return _stage(STAGE_NAMES[3], reasons)


def _condition_inventory_reason(
    conditions: tuple[object, ...],
) -> str | None:
    ids = tuple(str(getattr(item, "condition_id", "")) for item in conditions)
    if len(ids) != len(CONDITION_IDS) or set(ids) != set(CONDITION_IDS):
        return f"condition_inventory_invalid:{','.join(ids)}"
    return None


def _validate_bool_field(
    reasons: list[str],
    *,
    prefix: str,
    field: str,
    value: object,
    false_reason: str,
) -> None:
    if type(value) is not bool:
        reasons.append(f"{prefix}:{field}_type_invalid")
    elif value is False:
        reasons.append(f"{prefix}:{false_reason}")


def _validate_int_field(
    reasons: list[str],
    *,
    prefix: str,
    field: str,
    value: object,
    expected: int,
    mismatch_reason: str,
) -> None:
    if type(value) is not int:
        reasons.append(f"{prefix}:{field}_type_invalid")
    elif value != expected:
        reasons.append(f"{prefix}:{mismatch_reason}")


def _stage(name: str, reasons: list[str]) -> GateStageResult:
    return GateStageResult(
        name=name,
        status="passed" if not reasons else "failed",
        reasons=tuple(reasons),
    )


def _failed_stage(
    name: str,
    reasons: tuple[str, ...],
) -> GateStageResult:
    return GateStageResult(name=name, status="failed", reasons=reasons)


def _blocked_result(
    stages: list[GateStageResult],
) -> GoalFollowingGateResult:
    blocker = stages[-1].name
    for name in STAGE_NAMES[len(stages) :]:
        stages.append(
            GateStageResult(
                name=name,
                status="blocked",
                reasons=(f"dependency_not_passed:{blocker}",),
            )
        )
    return GoalFollowingGateResult(
        stages=tuple(stages),
        promotion_evidence_ready=False,
        auto_promotion_allowed=False,
        default_behavior_changed=False,
    )
