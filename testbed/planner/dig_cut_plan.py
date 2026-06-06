"""Dig-cut plan assembly for planner-generated ACT conditioning tokens."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.contracts.primitive_tokens import (
    DIG_CUT_TOKEN_DIM,
    DIG_DEPTH_PROFILE_TOKEN_DIM,
)
from testbed.data.operator_first_v2_2 import _build_dig_cut_token

Pose3D = tuple[float, float, float]


@dataclass(frozen=True)
class DigCutPlan:
    token: np.ndarray
    raw_fields: dict[str, float | int]
    source: str
    fallback_reason: str = ""


@dataclass(frozen=True)
class DigCutPlanAttempt:
    plan: DigCutPlan | None = None
    raw_fields_in_prior_range: bool = False
    failure_reason: object | None = None
    fallback_plan: DigCutPlan | None = None

    @classmethod
    def success(
        cls,
        *,
        plan: DigCutPlan,
        raw_fields_in_prior_range: bool,
    ) -> DigCutPlanAttempt:
        return cls(
            plan=plan,
            raw_fields_in_prior_range=bool(raw_fields_in_prior_range),
        )

    @classmethod
    def failure(
        cls,
        *,
        reason: object,
        fallback_plan: DigCutPlan,
    ) -> DigCutPlanAttempt:
        return cls(failure_reason=reason, fallback_plan=fallback_plan)


@dataclass(frozen=True)
class DigCutPlanSuccessAttemptFacts:
    token: Any
    raw_fields: Mapping[str, float | int]
    source: str
    fallback_reason: str
    raw_fields_in_prior_range: bool


@dataclass(frozen=True)
class DigCutPlanFailureAttemptFacts:
    reason: object
    fallback_plan: DigCutPlan


@dataclass(frozen=True)
class DigCutPlanState:
    token: np.ndarray
    source: str
    fallback_reason: str
    token_in_prior_p10_p90: bool


@dataclass(frozen=True)
class DigCutPlanTokenResult:
    token: np.ndarray
    source: str
    fallback_reason: str
    token_in_prior_p10_p90: bool


@dataclass(frozen=True)
class DigCutObservationTokenResult:
    token: np.ndarray


@dataclass(frozen=True)
class DigCutRuntimeState:
    tokens: np.ndarray
    token_injected: bool
    planned_cycle_id: int
    token_source: str
    fallback_reason: str
    token_in_prior_p10_p90: bool


@dataclass(frozen=True)
class DigCutPlanCycleConfig:
    enabled: bool
    hold_until_skill_exit: bool


@dataclass(frozen=True)
class DigCutPlanCycleFacts:
    planned_cycle_id: int
    cycle_index: int


@dataclass(frozen=True)
class DigCutPlanCycleDecision:
    action: str
    should_build: bool


@dataclass(frozen=True)
class DigCutPlanCycleApplyState:
    dig_cut_tokens: Any
    dig_depth_profile_tokens: Any
    planned_cycle_id: int


@dataclass(frozen=True)
class DigCutPlanDispatchFacts:
    planner_mode: str
    pending_tokens_present: bool
    pending_cycle_id: int
    cycle_index: int


DIG_CUT_PLAN_DISPATCH_FACT_FIELDS: tuple[tuple[str, str], ...] = (
    ("planner_mode", "dig_cut_planner_mode"),
    ("pending_tokens", "_pending_dig_cut_tokens"),
    ("pending_cycle_id", "_pending_dig_cut_cycle_id"),
    ("cycle_index", "_cycle_index"),
)


@dataclass(frozen=True)
class DigCutPlanDispatchDecision:
    action: str
    builder_kind: str = ""


@dataclass(frozen=True)
class DigCutRuntimeStatusConfig:
    planner_mode: str
    prior_id: str


DIG_CUT_RUNTIME_STATUS_CONFIG_FIELDS: tuple[tuple[str, str], ...] = (
    ("planner_mode", "dig_cut_planner_mode"),
    ("prior_id", "dig_cut_prior_id"),
)


@dataclass(frozen=True)
class DigCutRuntimeStatusState:
    pending_cycle_id: int
    pending_corridor_id: int
    token_injected: bool
    token_source: str
    tokens: np.ndarray
    token_in_prior_p10_p90: bool
    fallback_reason: str


DIG_CUT_RUNTIME_STATUS_STATE_FIELDS: tuple[tuple[str, str], ...] = (
    ("pending_cycle_id", "_pending_dig_cut_cycle_id"),
    ("pending_corridor_id", "_pending_dig_cut_corridor_id"),
    ("token_injected", "_dig_cut_token_injected"),
    ("token_source", "_dig_cut_token_source"),
    ("tokens", "_dig_cut_tokens"),
    ("token_in_prior_p10_p90", "_dig_cut_token_in_prior_p10_p90"),
    ("fallback_reason", "_dig_cut_fallback_reason"),
)


@dataclass(frozen=True)
class DigCutRuntimeStatusSnapshot:
    pending_cycle_id: int
    pending_corridor_id: int
    token_injected: bool
    planner_mode: str
    prior_id: str
    token_source: str
    tokens: np.ndarray
    token_in_prior_p10_p90: bool
    fallback_reason: str


@dataclass(frozen=True)
class DigCutPlanClearState:
    planned_cycle_id: int
    dig_cut_tokens: np.ndarray
    dig_depth_profile_tokens: np.ndarray
    token_source: str
    fallback_reason: str
    token_in_prior_p10_p90: bool


def build_dig_cut_runtime_status_config_from_mapping(
    values: Mapping[str, Any],
) -> DigCutRuntimeStatusConfig:
    return DigCutRuntimeStatusConfig(
        planner_mode=str(values["planner_mode"]),
        prior_id=str(values["prior_id"]),
    )


def build_dig_cut_runtime_status_state_from_mapping(
    values: Mapping[str, Any],
) -> DigCutRuntimeStatusState:
    return DigCutRuntimeStatusState(
        pending_cycle_id=int(values["pending_cycle_id"]),
        pending_corridor_id=int(values["pending_corridor_id"]),
        token_injected=bool(values["token_injected"]),
        token_source=str(values["token_source"]),
        tokens=values["tokens"],
        token_in_prior_p10_p90=bool(values["token_in_prior_p10_p90"]),
        fallback_reason=str(values["fallback_reason"]),
    )


def build_dig_cut_plan_dispatch_facts_from_mapping(
    values: Mapping[str, Any],
    *,
    pending_tokens_present: object | None = None,
) -> DigCutPlanDispatchFacts:
    if pending_tokens_present is None:
        pending_tokens_present = values["pending_tokens"] is not None
    return DigCutPlanDispatchFacts(
        planner_mode=str(values["planner_mode"]),
        pending_tokens_present=bool(pending_tokens_present),
        pending_cycle_id=int(values["pending_cycle_id"]),
        cycle_index=int(values["cycle_index"]),
    )


@dataclass(frozen=True)
class OperatorPriorDigCutPlanRequest:
    dig_cut_prior: dict[str, Any]
    bucket_dig_area_pose: Pose3D | None


class DigCutPlanService:
    """Assembles dig-cut token state after planner mode selection."""

    @staticmethod
    def cleared_plan_state() -> DigCutPlanClearState:
        return DigCutPlanClearState(
            planned_cycle_id=-1,
            dig_cut_tokens=np.zeros(DIG_CUT_TOKEN_DIM, dtype=np.float32),
            dig_depth_profile_tokens=np.zeros(
                DIG_DEPTH_PROFILE_TOKEN_DIM,
                dtype=np.float32,
            ),
            token_source="none",
            fallback_reason="",
            token_in_prior_p10_p90=False,
        )

    @staticmethod
    def initial_runtime_state() -> DigCutRuntimeState:
        return DigCutRuntimeState(
            tokens=np.zeros(DIG_CUT_TOKEN_DIM, dtype=np.float32),
            token_injected=False,
            planned_cycle_id=-1,
            token_source="none",
            fallback_reason="",
            token_in_prior_p10_p90=False,
        )

    @staticmethod
    def cycle_decision(
        *,
        config: DigCutPlanCycleConfig,
        facts: DigCutPlanCycleFacts,
    ) -> DigCutPlanCycleDecision:
        if not bool(config.enabled):
            return DigCutPlanCycleDecision(
                action="disabled",
                should_build=False,
            )
        if bool(config.hold_until_skill_exit) and int(
            facts.planned_cycle_id
        ) == int(facts.cycle_index):
            return DigCutPlanCycleDecision(
                action="hold_existing",
                should_build=False,
            )
        return DigCutPlanCycleDecision(action="build", should_build=True)

    @staticmethod
    def cycle_decision_from_runtime(
        *,
        enabled: object,
        hold_until_skill_exit: object,
        planned_cycle_id: object,
        cycle_index: object,
    ) -> DigCutPlanCycleDecision:
        return DigCutPlanService.cycle_decision(
            config=DigCutPlanCycleConfig(
                enabled=bool(enabled),
                hold_until_skill_exit=bool(hold_until_skill_exit),
            ),
            facts=DigCutPlanCycleFacts(
                planned_cycle_id=int(planned_cycle_id),
                cycle_index=int(cycle_index),
            ),
        )

    @staticmethod
    def cycle_apply_state(
        *,
        dig_cut_tokens: Any,
        dig_depth_profile_tokens: Any,
        cycle_index: int,
    ) -> DigCutPlanCycleApplyState:
        return DigCutPlanCycleApplyState(
            dig_cut_tokens=dig_cut_tokens,
            dig_depth_profile_tokens=dig_depth_profile_tokens,
            planned_cycle_id=int(cycle_index),
        )

    @staticmethod
    def dispatch_decision(
        facts: DigCutPlanDispatchFacts,
    ) -> DigCutPlanDispatchDecision:
        if bool(facts.pending_tokens_present) and int(
            facts.pending_cycle_id
        ) == int(facts.cycle_index):
            return DigCutPlanDispatchDecision(action="pending_return_target")

        mode = str(facts.planner_mode)
        if mode == "conservative_pose":
            return DigCutPlanDispatchDecision(
                action="build_plan",
                builder_kind="conservative_pose",
            )
        if mode == "operator_prior":
            return DigCutPlanDispatchDecision(
                action="build_plan",
                builder_kind="operator_prior",
            )
        if mode == "operator_prior_coverage":
            return DigCutPlanDispatchDecision(
                action="build_plan",
                builder_kind="operator_prior_coverage",
            )
        if mode == "operator_prior_sweep_belief":
            return DigCutPlanDispatchDecision(
                action="build_plan",
                builder_kind="operator_prior_coverage",
            )
        raise ValueError(f"Unsupported dig_cut_planner mode {mode!r}.")

    @staticmethod
    def runtime_status_snapshot(
        *,
        config: DigCutRuntimeStatusConfig,
        state: DigCutRuntimeStatusState,
    ) -> DigCutRuntimeStatusSnapshot:
        return DigCutRuntimeStatusSnapshot(
            pending_cycle_id=int(state.pending_cycle_id),
            pending_corridor_id=int(state.pending_corridor_id),
            token_injected=bool(state.token_injected),
            planner_mode=str(config.planner_mode),
            prior_id=str(config.prior_id),
            token_source=str(state.token_source),
            tokens=np.asarray(state.tokens, dtype=np.float32).copy(),
            token_in_prior_p10_p90=bool(state.token_in_prior_p10_p90),
            fallback_reason=str(state.fallback_reason),
        )

    @staticmethod
    def runtime_status_snapshot_from_mappings(
        *,
        config_values: Mapping[str, Any],
        state_values: Mapping[str, Any],
    ) -> DigCutRuntimeStatusSnapshot:
        return DigCutPlanService.runtime_status_snapshot(
            config=build_dig_cut_runtime_status_config_from_mapping(config_values),
            state=build_dig_cut_runtime_status_state_from_mapping(state_values),
        )

    @staticmethod
    def state_from_attempt(attempt: DigCutPlanAttempt) -> DigCutPlanState:
        if attempt.failure_reason is not None:
            if attempt.fallback_plan is None:
                raise ValueError("failed dig-cut plan attempt requires fallback plan.")
            return DigCutPlanService._state_from_plan(
                attempt.fallback_plan,
                token_in_prior_p10_p90=False,
            )
        if attempt.plan is None:
            raise ValueError("dig-cut plan attempt requires a plan or failure reason.")
        return DigCutPlanService._state_from_plan(
            attempt.plan,
            token_in_prior_p10_p90=bool(attempt.raw_fields_in_prior_range),
        )

    @staticmethod
    def state_from_success_plan(
        plan: DigCutPlan,
        *,
        raw_fields_in_prior_range: bool,
    ) -> DigCutPlanState:
        return DigCutPlanService.state_from_attempt(
            DigCutPlanAttempt.success(
                plan=plan,
                raw_fields_in_prior_range=bool(raw_fields_in_prior_range),
            )
        )

    @staticmethod
    def success_attempt(
        facts: DigCutPlanSuccessAttemptFacts,
    ) -> DigCutPlanAttempt:
        return DigCutPlanAttempt.success(
            plan=DigCutPlan(
                token=facts.token,
                raw_fields=dict(facts.raw_fields),
                source=facts.source,
                fallback_reason=facts.fallback_reason,
            ),
            raw_fields_in_prior_range=bool(facts.raw_fields_in_prior_range),
        )

    @staticmethod
    def failure_attempt(
        facts: DigCutPlanFailureAttemptFacts,
    ) -> DigCutPlanAttempt:
        return DigCutPlanAttempt.failure(
            reason=facts.reason,
            fallback_plan=facts.fallback_plan,
        )

    @staticmethod
    def state_from_builder_attempt(
        *,
        build_plan: Callable[[], tuple[Any, Mapping[str, float | int], str, str]],
        raw_fields_in_prior_range: Callable[[Mapping[str, float | int]], bool],
        fallback_mode: str,
        fallback_plan: Callable[[Exception], DigCutPlan],
    ) -> DigCutPlanState:
        try:
            token, raw_fields, source, fallback_reason = build_plan()
            attempt = DigCutPlanService.success_attempt(
                DigCutPlanSuccessAttemptFacts(
                    token=token,
                    raw_fields=raw_fields,
                    source=source,
                    fallback_reason=fallback_reason,
                    raw_fields_in_prior_range=raw_fields_in_prior_range(
                        raw_fields
                    ),
                )
            )
        except Exception as exc:
            if str(fallback_mode) != "conservative_pose":
                raise
            attempt = DigCutPlanService.failure_attempt(
                DigCutPlanFailureAttemptFacts(
                    reason=exc,
                    fallback_plan=fallback_plan(exc),
                )
            )
        return DigCutPlanService.state_from_attempt(attempt)

    @staticmethod
    def token_result(state: DigCutPlanState) -> DigCutPlanTokenResult:
        return DigCutPlanTokenResult(
            token=np.asarray(state.token, dtype=np.float32),
            source=str(state.source),
            fallback_reason=str(state.fallback_reason),
            token_in_prior_p10_p90=bool(state.token_in_prior_p10_p90),
        )

    @staticmethod
    def observation_token_result(tokens: Any) -> DigCutObservationTokenResult:
        return DigCutObservationTokenResult(token=np.asarray(tokens).copy())

    @staticmethod
    def _state_from_plan(
        plan: DigCutPlan,
        *,
        token_in_prior_p10_p90: bool,
    ) -> DigCutPlanState:
        return DigCutPlanState(
            token=np.asarray(plan.token, dtype=np.float32),
            source=str(plan.source),
            fallback_reason=str(plan.fallback_reason),
            token_in_prior_p10_p90=bool(token_in_prior_p10_p90),
        )


def build_conservative_pose_dig_cut_plan(
    pose: Pose3D | None,
    *,
    source: str = "conservative_pose",
    fallback_reason: str = "",
) -> DigCutPlan:
    raw_fields = raw_fields_from_live_pose(pose)
    return DigCutPlan(
        token=_build_dig_cut_token(raw_fields),
        raw_fields=raw_fields,
        source=str(source),
        fallback_reason=str(fallback_reason),
    )


def build_raw_fields_dig_cut_plan(
    raw_fields: dict[str, float | int],
    *,
    source: str,
    fallback_reason: str = "",
) -> DigCutPlan:
    return DigCutPlan(
        token=_build_dig_cut_token(raw_fields),
        raw_fields=raw_fields,
        source=str(source),
        fallback_reason=str(fallback_reason),
    )


def build_operator_prior_dig_cut_plan(
    request: OperatorPriorDigCutPlanRequest,
) -> DigCutPlan:
    if not request.dig_cut_prior:
        raise ValueError("operator_prior mode requires a dig cut prior JSON.")
    fields = dict(request.dig_cut_prior.get("fields", {}))
    pose = request.bucket_dig_area_pose
    fallback_reason = ""
    if pose is None:
        entry_x = prior_percentile(fields, "entry_x_m", "p50")
        entry_y = 0.0
        entry_z = prior_percentile(fields, "entry_z_m", "p50")
        source = "operator_prior_median_pose_fallback"
        fallback_reason = "missing_bucket_dig_area_pose"
    else:
        entry_x = clamp_to_prior(fields, "entry_x_m", float(pose[0]))
        entry_y = float(pose[1])
        entry_z = clamp_to_prior(fields, "entry_z_m", float(pose[2]))
        source = "operator_prior_pose_clamped"

    dir_x = prior_percentile(fields, "cut_direction_x", "p50")
    dir_z = prior_percentile(fields, "cut_direction_z", "p50")
    norm = float(np.hypot(dir_x, dir_z))
    if norm <= 1.0e-6:
        dir_x, dir_z = -1.0, 0.0
    else:
        dir_x, dir_z = dir_x / norm, dir_z / norm
    length = prior_percentile(fields, "cut_length_m", "p50")
    exit_x = clamp_to_prior(fields, "exit_x_m", entry_x + dir_x * length)
    exit_z = clamp_to_prior(fields, "exit_z_m", entry_z + dir_z * length)

    delta_x = exit_x - entry_x
    delta_z = exit_z - entry_z
    generated_length = float(np.hypot(delta_x, delta_z))
    if generated_length > 1.0e-6:
        dir_x = delta_x / generated_length
        dir_z = delta_z / generated_length
        length = generated_length

    raw_fields = {
        "operator_entry_x_m": float(entry_x),
        "operator_entry_y_m": float(entry_y),
        "operator_entry_z_m": float(entry_z),
        "operator_exit_x_m": float(exit_x),
        "operator_exit_y_m": float(entry_y),
        "operator_exit_z_m": float(exit_z),
        "operator_cut_direction_x": float(
            clamp_to_prior(fields, "cut_direction_x", dir_x)
        ),
        "operator_cut_direction_y": 0.0,
        "operator_cut_direction_z": float(
            clamp_to_prior(fields, "cut_direction_z", dir_z)
        ),
        "operator_cut_length_m": float(
            clamp_to_prior(fields, "cut_length_m", length)
        ),
        "operator_cut_depth_peak_m": float(
            prior_percentile(fields, "cut_depth_peak_m", "p50")
        ),
        "operator_cut_payload_gain_kg": float(
            prior_percentile(fields, "payload_gain_kg", "p50")
        ),
        "operator_effective_deposit_delta_kg": float(
            prior_percentile(fields, "effective_deposit_delta_kg", "p50")
        ),
        "operator_cut_valid": 1,
    }
    return DigCutPlan(
        token=_build_dig_cut_token(raw_fields),
        raw_fields=raw_fields,
        source=source,
        fallback_reason=fallback_reason,
    )


def raw_fields_from_live_pose(pose: Pose3D | None) -> dict[str, float | int]:
    if pose is None:
        return {
            "operator_entry_x_m": 0.0,
            "operator_entry_y_m": 0.0,
            "operator_entry_z_m": 0.0,
            "operator_exit_x_m": 0.0,
            "operator_exit_y_m": 0.0,
            "operator_exit_z_m": 0.0,
            "operator_cut_direction_x": 0.0,
            "operator_cut_direction_y": 0.0,
            "operator_cut_direction_z": 0.0,
            "operator_cut_length_m": 0.0,
            "operator_cut_depth_peak_m": 0.0,
            "operator_cut_payload_gain_kg": 0.0,
            "operator_effective_deposit_delta_kg": 0.0,
            "operator_cut_valid": 0,
        }
    entry_x, entry_y, entry_z = float(pose[0]), float(pose[1]), float(pose[2])
    exit_x = entry_x - 1.2
    exit_z = entry_z
    return {
        "operator_entry_x_m": entry_x,
        "operator_entry_y_m": entry_y,
        "operator_entry_z_m": entry_z,
        "operator_exit_x_m": exit_x,
        "operator_exit_y_m": entry_y,
        "operator_exit_z_m": exit_z,
        "operator_cut_direction_x": -1.0,
        "operator_cut_direction_y": 0.0,
        "operator_cut_direction_z": 0.0,
        "operator_cut_length_m": 1.2,
        "operator_cut_depth_peak_m": 0.08,
        "operator_cut_payload_gain_kg": 55.0,
        "operator_effective_deposit_delta_kg": 55.0,
        "operator_cut_valid": 1,
    }


def prior_percentile(
    fields: dict[str, Any],
    field_name: str,
    percentile: str,
) -> float:
    try:
        return float(fields[field_name][percentile])
    except KeyError as exc:
        raise KeyError(f"Missing prior field {field_name}.{percentile}") from exc


def clamp_to_prior(fields: dict[str, Any], field_name: str, value: float) -> float:
    lo = prior_percentile(fields, field_name, "p10")
    hi = prior_percentile(fields, field_name, "p90")
    return float(np.clip(float(value), lo, hi))
