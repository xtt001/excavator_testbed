"""Return target plan state assembly for primitive scheduler facades."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.contracts.primitive_tokens import (
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_TARGET_TOKEN_DIM,
    derive_return_relocate_token,
)
from testbed.planner.return_target_dig_cut_build import (
    ReturnTargetDigCutBuildCallbacks,
    ReturnTargetDigCutBuildContext,
    ReturnTargetDigCutBuildFacts,
    ReturnTargetDigCutBuildResult,
    ReturnTargetDigCutBuildResultConfig,
    ReturnTargetDigCutBuildService,
)


@dataclass(frozen=True)
class ReturnTargetPlanBuild:
    token: Any
    raw_fields: Mapping[str, float | int]
    return_start_envelope_tokens: Any
    source: str
    fallback_reason: str
    corridor_id: int


@dataclass(frozen=True)
class ReturnTargetPlanBuildFacts:
    token: Any
    raw_fields: Mapping[str, float | int]
    return_start_envelope_tokens: Any
    source: str
    fallback_reason: str
    corridor_id: int


@dataclass(frozen=True)
class ReturnTargetExemplarSnapshot:
    depth_profile_token: Any | None = None
    state_exemplar_ids: Sequence[str] = ()
    state_exemplar_distance: float = float("nan")


@dataclass(frozen=True)
class ReturnTargetPlanAttempt:
    cycle_index: int
    plan: ReturnTargetPlanBuild | None = None
    failure_reason: object | None = None

    @classmethod
    def success(
        cls,
        *,
        cycle_index: int,
        plan: ReturnTargetPlanBuild,
    ) -> ReturnTargetPlanAttempt:
        return cls(cycle_index=int(cycle_index), plan=plan)

    @classmethod
    def failure(
        cls,
        *,
        cycle_index: int,
        reason: object,
    ) -> ReturnTargetPlanAttempt:
        return cls(cycle_index=int(cycle_index), failure_reason=reason)


@dataclass(frozen=True)
class ReturnTargetPlanState:
    return_target_tokens: np.ndarray
    return_start_envelope_tokens: np.ndarray
    return_target_token_source: str
    return_target_fallback_reason: str
    return_target_planned_cycle_id: int
    pending_dig_cut_cycle_id: int
    pending_dig_cut_raw_fields: dict[str, float | int] | None
    pending_dig_cut_tokens: np.ndarray | None
    pending_dig_cut_corridor_id: int
    pending_dig_depth_profile_tokens: np.ndarray | None
    pending_dig_state_exemplar_ids: tuple[str, ...]
    pending_dig_state_exemplar_distance: float
    return_start_envelope_token_source: str | None = None


@dataclass(frozen=True)
class ReturnTargetPlanRuntimeUpdate:
    return_target_tokens: np.ndarray
    return_start_envelope_tokens: np.ndarray
    return_target_token_source: str
    return_start_envelope_token_source: str | None
    return_target_fallback_reason: str
    return_target_planned_cycle_id: int
    pending_plan: PendingDigCutPlanState


@dataclass(frozen=True)
class ReturnTargetPlanCycleConfig:
    enabled: bool
    hold_until_skill_exit: bool


@dataclass(frozen=True)
class ReturnTargetPlanCycleFacts:
    planned_cycle_id: int
    cycle_index: int


@dataclass(frozen=True)
class ReturnTargetPlanCycleDecision:
    action: str
    should_build: bool


@dataclass(frozen=True)
class ReturnTargetPlanRequest:
    decision: ReturnTargetPlanCycleDecision
    exemplar: ReturnTargetExemplarSnapshot
    cycle_index: int

    @property
    def should_build(self) -> bool:
        return bool(self.decision.should_build)

    def success_attempt(
        self,
        plan: ReturnTargetPlanBuild,
    ) -> ReturnTargetPlanAttempt:
        return ReturnTargetPlanAttempt.success(
            cycle_index=int(self.cycle_index),
            plan=plan,
        )

    def success_attempt_from_facts(
        self,
        facts: ReturnTargetPlanBuildFacts,
    ) -> ReturnTargetPlanAttempt:
        return self.success_attempt(
            ReturnTargetPlanBuild(
                token=facts.token,
                raw_fields=facts.raw_fields,
                return_start_envelope_tokens=facts.return_start_envelope_tokens,
                source=facts.source,
                fallback_reason=facts.fallback_reason,
                corridor_id=facts.corridor_id,
            )
        )

    def failure_attempt(self, reason: object) -> ReturnTargetPlanAttempt:
        return ReturnTargetPlanAttempt.failure(
            cycle_index=int(self.cycle_index),
            reason=reason,
        )


@dataclass(frozen=True)
class ReturnTargetPlanBuildAttemptFacts:
    request: ReturnTargetPlanRequest
    build_facts: ReturnTargetPlanBuildFacts | None = None
    failure_reason: object | None = None


@dataclass(frozen=True)
class PendingReturnTargetActivationFacts:
    pending_dig_cut_tokens: Any
    pending_dig_cut_raw_fields: Mapping[str, float | int] | None = None
    pending_dig_cut_corridor_id: int = -1
    pending_dig_depth_profile_tokens: Any | None = None
    pending_dig_state_exemplar_ids: Sequence[str] = ()
    pending_dig_state_exemplar_distance: float = float("nan")
    raw_fields_in_prior_range: bool = False
    cycle_start_deposit_kg: float = 0.0


PENDING_RETURN_TARGET_ACTIVATION_FACT_FIELDS: tuple[tuple[str, str], ...] = (
    ("pending_dig_cut_tokens", "_pending_dig_cut_tokens"),
    ("pending_dig_cut_raw_fields", "_pending_dig_cut_raw_fields"),
    ("pending_dig_cut_corridor_id", "_pending_dig_cut_corridor_id"),
    ("pending_dig_depth_profile_tokens", "_pending_dig_depth_profile_tokens"),
    ("pending_dig_state_exemplar_ids", "_pending_dig_state_exemplar_ids"),
    ("pending_dig_state_exemplar_distance", "_pending_dig_state_exemplar_distance"),
)


def build_pending_return_target_activation_facts(
    *,
    pending_dig_cut_tokens: Any,
    pending_dig_cut_raw_fields: Mapping[str, float | int] | None = None,
    pending_dig_cut_corridor_id: int = -1,
    pending_dig_depth_profile_tokens: Any | None = None,
    pending_dig_state_exemplar_ids: Sequence[str] = (),
    pending_dig_state_exemplar_distance: float = float("nan"),
    raw_fields_in_prior_range: bool = False,
    cycle_start_deposit_kg: float = 0.0,
) -> PendingReturnTargetActivationFacts:
    return PendingReturnTargetActivationFacts(
        pending_dig_cut_tokens=pending_dig_cut_tokens,
        pending_dig_cut_raw_fields=pending_dig_cut_raw_fields,
        pending_dig_cut_corridor_id=int(pending_dig_cut_corridor_id),
        pending_dig_depth_profile_tokens=pending_dig_depth_profile_tokens,
        pending_dig_state_exemplar_ids=pending_dig_state_exemplar_ids,
        pending_dig_state_exemplar_distance=float(
            pending_dig_state_exemplar_distance
        ),
        raw_fields_in_prior_range=bool(raw_fields_in_prior_range),
        cycle_start_deposit_kg=float(cycle_start_deposit_kg),
    )


def build_pending_return_target_activation_facts_from_mapping(
    values: Mapping[str, Any],
    *,
    raw_fields_in_prior_range: object,
    cycle_start_deposit_kg: object,
) -> PendingReturnTargetActivationFacts:
    return build_pending_return_target_activation_facts(
        pending_dig_cut_tokens=values["pending_dig_cut_tokens"],
        pending_dig_cut_raw_fields=values["pending_dig_cut_raw_fields"],
        pending_dig_cut_corridor_id=values["pending_dig_cut_corridor_id"],
        pending_dig_depth_profile_tokens=values[
            "pending_dig_depth_profile_tokens"
        ],
        pending_dig_state_exemplar_ids=values["pending_dig_state_exemplar_ids"],
        pending_dig_state_exemplar_distance=values[
            "pending_dig_state_exemplar_distance"
        ],
        raw_fields_in_prior_range=raw_fields_in_prior_range,
        cycle_start_deposit_kg=cycle_start_deposit_kg,
    )


@dataclass(frozen=True)
class PendingReturnTargetActivation:
    dig_cut_tokens: np.ndarray
    dig_cut_token_source: str = ""
    dig_cut_fallback_reason: str = ""
    dig_cut_token_in_prior_p10_p90: bool = False
    coverage_active_corridor_id: int = -1
    coverage_last_selected_corridor_id: int = -1
    coverage_current_payload_gain_kg: float = 0.0
    coverage_cycle_start_deposit_kg: float = 0.0
    active_state_exemplar_ids: tuple[str, ...] = ()
    active_state_exemplar_distance: float = float("nan")
    active_state_exemplar_profile_token: np.ndarray | None = None


@dataclass(frozen=True)
class PendingDigCutPlanState:
    cycle_id: int
    corridor_id: int
    raw_fields: dict[str, float | int] | None
    tokens: np.ndarray | None
    depth_profile_tokens: np.ndarray | None
    state_exemplar_ids: tuple[str, ...]
    state_exemplar_distance: float


@dataclass(frozen=True)
class ReturnTargetConditioningStatusState:
    target_token_injected: bool
    target_token_source: str
    target_tokens: np.ndarray
    target_fallback_reason: str
    relocate_token_injected: bool
    relocate_tokens: np.ndarray
    start_envelope_token_injected: bool
    start_envelope_token_source: str
    start_envelope_tokens: np.ndarray


RETURN_TARGET_CONDITIONING_STATUS_FIELDS: tuple[tuple[str, str], ...] = (
    ("target_token_injected", "_return_target_token_injected"),
    ("target_token_source", "_return_target_token_source"),
    ("target_tokens", "_return_target_tokens"),
    ("target_fallback_reason", "_return_target_fallback_reason"),
    ("relocate_token_injected", "_return_relocate_token_injected"),
    ("relocate_tokens", "_return_relocate_tokens"),
    ("start_envelope_token_injected", "_return_start_envelope_token_injected"),
    ("start_envelope_token_source", "_return_start_envelope_token_source"),
    ("start_envelope_tokens", "_return_start_envelope_tokens"),
)


@dataclass(frozen=True)
class ReturnTargetConditioningRuntimeState:
    target_tokens: np.ndarray
    target_token_injected: bool
    target_token_source: str
    target_fallback_reason: str
    relocate_tokens: np.ndarray
    relocate_token_injected: bool
    start_envelope_tokens: np.ndarray
    start_envelope_token_injected: bool
    start_envelope_token_source: str
    start_envelope_use_prior_spatial_bounds: bool
    start_envelope_use_prior_qpos_bounds: bool
    planned_cycle_id: int
    pending_dig_cut_cycle_id: int
    pending_dig_cut_corridor_id: int
    pending_dig_cut_raw_fields: dict[str, float | int] | None
    pending_dig_cut_tokens: np.ndarray | None
    pending_dig_depth_profile_tokens: np.ndarray | None
    pending_dig_state_exemplar_ids: tuple[str, ...]
    pending_dig_state_exemplar_distance: float


@dataclass(frozen=True)
class ReturnTargetConditioningStatusSnapshot:
    target_token_injected: bool
    target_token_source: str
    target_tokens: np.ndarray
    target_fallback_reason: str
    relocate_token_injected: bool
    relocate_tokens: np.ndarray
    start_envelope_token_injected: bool
    start_envelope_token_source: str
    start_envelope_tokens: np.ndarray


def build_return_target_conditioning_status_state_from_mapping(
    values: Mapping[str, Any],
) -> ReturnTargetConditioningStatusState:
    return ReturnTargetConditioningStatusState(
        target_token_injected=bool(values["target_token_injected"]),
        target_token_source=str(values["target_token_source"]),
        target_tokens=values["target_tokens"],
        target_fallback_reason=str(values["target_fallback_reason"]),
        relocate_token_injected=bool(values["relocate_token_injected"]),
        relocate_tokens=values["relocate_tokens"],
        start_envelope_token_injected=bool(
            values["start_envelope_token_injected"]
        ),
        start_envelope_token_source=str(values["start_envelope_token_source"]),
        start_envelope_tokens=values["start_envelope_tokens"],
    )


@dataclass(frozen=True)
class ReturnTargetObservationTokenResult:
    tokens: np.ndarray


@dataclass(frozen=True)
class ReturnRelocateObservationTokenResult:
    tokens: np.ndarray


@dataclass(frozen=True)
class ReturnStartEnvelopeObservationTokenResult:
    tokens: np.ndarray


class ReturnTargetPlanService:
    """Assembles return target planner state without selecting targets."""

    @staticmethod
    def invalidated_pending_dig_cut_plan() -> PendingDigCutPlanState:
        return PendingDigCutPlanState(
            cycle_id=-1,
            corridor_id=-1,
            raw_fields=None,
            tokens=None,
            depth_profile_tokens=None,
            state_exemplar_ids=(),
            state_exemplar_distance=float("nan"),
        )

    @staticmethod
    def pending_plan_state_from_return_target_state(
        state: ReturnTargetPlanState,
    ) -> PendingDigCutPlanState:
        return PendingDigCutPlanState(
            cycle_id=int(state.pending_dig_cut_cycle_id),
            corridor_id=int(state.pending_dig_cut_corridor_id),
            raw_fields=state.pending_dig_cut_raw_fields,
            tokens=state.pending_dig_cut_tokens,
            depth_profile_tokens=state.pending_dig_depth_profile_tokens,
            state_exemplar_ids=tuple(state.pending_dig_state_exemplar_ids),
            state_exemplar_distance=float(state.pending_dig_state_exemplar_distance),
        )

    @staticmethod
    def runtime_update_from_plan_state(
        state: ReturnTargetPlanState,
    ) -> ReturnTargetPlanRuntimeUpdate:
        return ReturnTargetPlanRuntimeUpdate(
            return_target_tokens=np.asarray(
                state.return_target_tokens,
                dtype=np.float32,
            ),
            return_start_envelope_tokens=np.asarray(
                state.return_start_envelope_tokens,
                dtype=np.float32,
            ),
            return_target_token_source=str(state.return_target_token_source),
            return_start_envelope_token_source=(
                None
                if state.return_start_envelope_token_source is None
                else str(state.return_start_envelope_token_source)
            ),
            return_target_fallback_reason=str(state.return_target_fallback_reason),
            return_target_planned_cycle_id=int(state.return_target_planned_cycle_id),
            pending_plan=ReturnTargetPlanService.pending_plan_state_from_return_target_state(
                state
            ),
        )

    @staticmethod
    def pending_plan_state_from_conditioning_state(
        state: ReturnTargetConditioningRuntimeState,
    ) -> PendingDigCutPlanState:
        return PendingDigCutPlanState(
            cycle_id=int(state.pending_dig_cut_cycle_id),
            corridor_id=int(state.pending_dig_cut_corridor_id),
            raw_fields=state.pending_dig_cut_raw_fields,
            tokens=state.pending_dig_cut_tokens,
            depth_profile_tokens=state.pending_dig_depth_profile_tokens,
            state_exemplar_ids=tuple(state.pending_dig_state_exemplar_ids),
            state_exemplar_distance=float(state.pending_dig_state_exemplar_distance),
        )

    @staticmethod
    def initial_conditioning_state() -> ReturnTargetConditioningRuntimeState:
        pending = ReturnTargetPlanService.invalidated_pending_dig_cut_plan()
        return ReturnTargetConditioningRuntimeState(
            target_tokens=np.zeros(RETURN_TARGET_TOKEN_DIM, dtype=np.float32),
            target_token_injected=False,
            target_token_source="none",
            target_fallback_reason="",
            relocate_tokens=np.zeros(RETURN_TARGET_TOKEN_DIM, dtype=np.float32),
            relocate_token_injected=False,
            start_envelope_tokens=np.zeros(
                RETURN_START_ENVELOPE_TOKEN_DIM,
                dtype=np.float32,
            ),
            start_envelope_token_injected=False,
            start_envelope_token_source="none",
            start_envelope_use_prior_spatial_bounds=True,
            start_envelope_use_prior_qpos_bounds=True,
            planned_cycle_id=-1,
            pending_dig_cut_cycle_id=int(pending.cycle_id),
            pending_dig_cut_corridor_id=int(pending.corridor_id),
            pending_dig_cut_raw_fields=pending.raw_fields,
            pending_dig_cut_tokens=pending.tokens,
            pending_dig_depth_profile_tokens=pending.depth_profile_tokens,
            pending_dig_state_exemplar_ids=tuple(pending.state_exemplar_ids),
            pending_dig_state_exemplar_distance=float(pending.state_exemplar_distance),
        )

    @staticmethod
    def conditioning_status_snapshot(
        state: ReturnTargetConditioningStatusState,
    ) -> ReturnTargetConditioningStatusSnapshot:
        return ReturnTargetConditioningStatusSnapshot(
            target_token_injected=bool(state.target_token_injected),
            target_token_source=str(state.target_token_source),
            target_tokens=np.asarray(
                state.target_tokens,
                dtype=np.float32,
            ).copy(),
            target_fallback_reason=str(state.target_fallback_reason),
            relocate_token_injected=bool(state.relocate_token_injected),
            relocate_tokens=np.asarray(
                state.relocate_tokens,
                dtype=np.float32,
            ).copy(),
            start_envelope_token_injected=bool(
                state.start_envelope_token_injected
            ),
            start_envelope_token_source=str(state.start_envelope_token_source),
            start_envelope_tokens=np.asarray(
                state.start_envelope_tokens,
                dtype=np.float32,
            ).copy(),
        )

    @staticmethod
    def conditioning_status_snapshot_from_mapping(
        values: Mapping[str, Any],
    ) -> ReturnTargetConditioningStatusSnapshot:
        return ReturnTargetPlanService.conditioning_status_snapshot(
            build_return_target_conditioning_status_state_from_mapping(values)
        )

    @staticmethod
    def return_target_token_result(
        return_target_tokens: Any,
    ) -> ReturnTargetObservationTokenResult:
        return ReturnTargetObservationTokenResult(
            tokens=np.asarray(return_target_tokens).copy()
        )

    @staticmethod
    def return_relocate_token_result(
        return_target_tokens: Any,
    ) -> ReturnRelocateObservationTokenResult:
        return ReturnRelocateObservationTokenResult(
            tokens=derive_return_relocate_token(return_target_tokens)
        )

    @staticmethod
    def return_start_envelope_token_result(
        return_start_envelope_tokens: Any,
    ) -> ReturnStartEnvelopeObservationTokenResult:
        return ReturnStartEnvelopeObservationTokenResult(
            tokens=np.asarray(return_start_envelope_tokens).copy()
        )

    @staticmethod
    def dig_cut_build_context(
        *,
        source_prefix: object,
        builder_kind: object,
        planner_mode: object,
    ) -> ReturnTargetDigCutBuildContext:
        return ReturnTargetDigCutBuildService.context(
            source_prefix=source_prefix,
            builder_kind=builder_kind,
            planner_mode=planner_mode,
        )

    @staticmethod
    def dig_cut_build_result(
        *,
        config: ReturnTargetDigCutBuildResultConfig,
        facts: ReturnTargetDigCutBuildFacts,
    ) -> ReturnTargetDigCutBuildResult:
        return ReturnTargetDigCutBuildService.result(config=config, facts=facts)

    @staticmethod
    def dig_cut_build_result_from_parts(
        context: ReturnTargetDigCutBuildContext,
        *,
        token: Any,
        raw_fields: dict[str, float | int],
        source_suffix: object,
        fallback_reason: object = "",
        corridor_id: object = -1,
    ) -> ReturnTargetDigCutBuildResult:
        return ReturnTargetDigCutBuildService.result_from_parts(
            context,
            token=token,
            raw_fields=raw_fields,
            source_suffix=source_suffix,
            fallback_reason=fallback_reason,
            corridor_id=corridor_id,
        )

    @staticmethod
    def dig_cut_build_result_from_plan(
        context: ReturnTargetDigCutBuildContext,
        plan: Any,
        *,
        corridor_id: object = -1,
    ) -> ReturnTargetDigCutBuildResult:
        return ReturnTargetDigCutBuildService.result_from_plan(
            context,
            plan,
            corridor_id=corridor_id,
        )

    def dig_cut_build_result_from_callbacks(
        self,
        context: ReturnTargetDigCutBuildContext,
        callbacks: ReturnTargetDigCutBuildCallbacks,
    ) -> ReturnTargetDigCutBuildResult:
        return ReturnTargetDigCutBuildService.result_from_callbacks(
            context,
            callbacks,
        )

    @staticmethod
    def should_hold_plan(
        *,
        hold_until_skill_exit: bool,
        planned_cycle_id: int,
        cycle_index: int,
    ) -> bool:
        return bool(
            hold_until_skill_exit and int(planned_cycle_id) == int(cycle_index)
        )

    def cycle_decision(
        self,
        *,
        config: ReturnTargetPlanCycleConfig,
        facts: ReturnTargetPlanCycleFacts,
    ) -> ReturnTargetPlanCycleDecision:
        if not bool(config.enabled):
            return ReturnTargetPlanCycleDecision(
                action="disabled",
                should_build=False,
            )
        if self.should_hold_plan(
            hold_until_skill_exit=bool(config.hold_until_skill_exit),
            planned_cycle_id=int(facts.planned_cycle_id),
            cycle_index=int(facts.cycle_index),
        ):
            return ReturnTargetPlanCycleDecision(
                action="hold_existing",
                should_build=False,
            )
        return ReturnTargetPlanCycleDecision(action="build", should_build=True)

    def plan_request(
        self,
        *,
        config: ReturnTargetPlanCycleConfig,
        facts: ReturnTargetPlanCycleFacts,
        depth_profile_token: Any | None = None,
        state_exemplar_ids: Sequence[str] = (),
        state_exemplar_distance: float = float("nan"),
    ) -> ReturnTargetPlanRequest:
        return ReturnTargetPlanRequest(
            decision=self.cycle_decision(config=config, facts=facts),
            exemplar=ReturnTargetExemplarSnapshot(
                depth_profile_token=depth_profile_token,
                state_exemplar_ids=state_exemplar_ids,
                state_exemplar_distance=float(state_exemplar_distance),
            ),
            cycle_index=int(facts.cycle_index),
        )

    def plan_request_from_runtime(
        self,
        *,
        enabled: object,
        hold_until_skill_exit: object,
        planned_cycle_id: object,
        cycle_index: object,
        depth_profile_token: Any | None = None,
        state_exemplar_ids: Sequence[str] = (),
        state_exemplar_distance: object = float("nan"),
    ) -> ReturnTargetPlanRequest:
        return self.plan_request(
            config=ReturnTargetPlanCycleConfig(
                enabled=bool(enabled),
                hold_until_skill_exit=bool(hold_until_skill_exit),
            ),
            facts=ReturnTargetPlanCycleFacts(
                planned_cycle_id=int(planned_cycle_id),
                cycle_index=int(cycle_index),
            ),
            depth_profile_token=depth_profile_token,
            state_exemplar_ids=state_exemplar_ids,
            state_exemplar_distance=float(state_exemplar_distance),
        )

    def state_from_attempt(
        self,
        attempt: ReturnTargetPlanAttempt,
        *,
        exemplar: ReturnTargetExemplarSnapshot,
    ) -> ReturnTargetPlanState:
        if attempt.failure_reason is not None:
            return self.failure_state(
                cycle_index=int(attempt.cycle_index),
                reason=attempt.failure_reason,
            )
        if attempt.plan is None:
            raise ValueError(
                "return target plan attempt requires a plan or failure reason."
            )
        return self.success_state(
            cycle_index=int(attempt.cycle_index),
            plan=attempt.plan,
            exemplar=exemplar,
        )

    def state_from_build_attempt(
        self,
        facts: ReturnTargetPlanBuildAttemptFacts,
    ) -> ReturnTargetPlanState:
        request = facts.request
        if facts.failure_reason is not None:
            attempt = request.failure_attempt(facts.failure_reason)
        else:
            if facts.build_facts is None:
                raise ValueError(
                    "return target build attempt requires build facts or "
                    "failure reason."
                )
            attempt = request.success_attempt_from_facts(facts.build_facts)
        return self.state_from_attempt(attempt, exemplar=request.exemplar)

    @staticmethod
    def plan_build_facts_from_parts(
        *,
        token: Any,
        raw_fields: Mapping[str, float | int],
        return_start_envelope_tokens: Any,
        source: object,
        fallback_reason: object,
        corridor_id: object,
    ) -> ReturnTargetPlanBuildFacts:
        return ReturnTargetPlanBuildFacts(
            token=token,
            raw_fields=raw_fields,
            return_start_envelope_tokens=return_start_envelope_tokens,
            source=str(source),
            fallback_reason=str(fallback_reason),
            corridor_id=int(corridor_id),
        )

    def state_from_build_facts_callback(
        self,
        *,
        request: ReturnTargetPlanRequest,
        build_facts: Callable[[], ReturnTargetPlanBuildFacts],
    ) -> ReturnTargetPlanState:
        try:
            attempt_facts = ReturnTargetPlanBuildAttemptFacts(
                request=request,
                build_facts=build_facts(),
            )
        except Exception as exc:
            attempt_facts = ReturnTargetPlanBuildAttemptFacts(
                request=request,
                failure_reason=exc,
            )
        return self.state_from_build_attempt(attempt_facts)

    @staticmethod
    def pending_activation(
        facts: PendingReturnTargetActivationFacts,
    ) -> PendingReturnTargetActivation:
        corridor_id = int(facts.pending_dig_cut_corridor_id)
        profile_token = (
            None
            if facts.pending_dig_depth_profile_tokens is None
            else np.asarray(
                facts.pending_dig_depth_profile_tokens,
                dtype=np.float32,
            ).copy()
        )
        return PendingReturnTargetActivation(
            dig_cut_tokens=np.asarray(
                facts.pending_dig_cut_tokens,
                dtype=np.float32,
            ).copy(),
            dig_cut_token_source="pending_return_target",
            dig_cut_fallback_reason="",
            dig_cut_token_in_prior_p10_p90=(
                False
                if facts.pending_dig_cut_raw_fields is None
                else bool(facts.raw_fields_in_prior_range)
            ),
            coverage_active_corridor_id=corridor_id,
            coverage_last_selected_corridor_id=corridor_id,
            coverage_current_payload_gain_kg=0.0,
            coverage_cycle_start_deposit_kg=float(facts.cycle_start_deposit_kg),
            active_state_exemplar_ids=tuple(facts.pending_dig_state_exemplar_ids),
            active_state_exemplar_distance=float(
                facts.pending_dig_state_exemplar_distance
            ),
            active_state_exemplar_profile_token=profile_token,
        )

    @staticmethod
    def success_state(
        *,
        cycle_index: int,
        plan: ReturnTargetPlanBuild,
        exemplar: ReturnTargetExemplarSnapshot,
    ) -> ReturnTargetPlanState:
        target_tokens = np.asarray(plan.token, dtype=np.float32).copy()
        envelope_tokens = np.asarray(
            plan.return_start_envelope_tokens,
            dtype=np.float32,
        ).copy()
        depth_profile = (
            None
            if exemplar.depth_profile_token is None
            else np.asarray(exemplar.depth_profile_token, dtype=np.float32).copy()
        )
        return ReturnTargetPlanState(
            return_target_tokens=target_tokens,
            return_start_envelope_tokens=envelope_tokens,
            return_target_token_source=str(plan.source),
            return_target_fallback_reason=str(plan.fallback_reason),
            return_target_planned_cycle_id=int(cycle_index),
            pending_dig_cut_cycle_id=int(cycle_index) + 1,
            pending_dig_cut_raw_fields=dict(plan.raw_fields),
            pending_dig_cut_tokens=target_tokens.copy(),
            pending_dig_cut_corridor_id=int(plan.corridor_id),
            pending_dig_depth_profile_tokens=depth_profile,
            pending_dig_state_exemplar_ids=tuple(exemplar.state_exemplar_ids),
            pending_dig_state_exemplar_distance=float(
                exemplar.state_exemplar_distance
            ),
        )

    @staticmethod
    def failure_state(
        *,
        cycle_index: int,
        reason: object,
    ) -> ReturnTargetPlanState:
        pending = ReturnTargetPlanService.invalidated_pending_dig_cut_plan()
        return ReturnTargetPlanState(
            return_target_tokens=np.zeros(
                RETURN_TARGET_TOKEN_DIM,
                dtype=np.float32,
            ),
            return_start_envelope_tokens=np.zeros(
                RETURN_START_ENVELOPE_TOKEN_DIM,
                dtype=np.float32,
            ),
            return_target_token_source="fallback_zero",
            return_start_envelope_token_source="fallback_zero",
            return_target_fallback_reason=str(reason),
            return_target_planned_cycle_id=int(cycle_index),
            pending_dig_cut_cycle_id=int(pending.cycle_id),
            pending_dig_cut_raw_fields=pending.raw_fields,
            pending_dig_cut_tokens=pending.tokens,
            pending_dig_cut_corridor_id=int(pending.corridor_id),
            pending_dig_depth_profile_tokens=pending.depth_profile_tokens,
            pending_dig_state_exemplar_ids=tuple(pending.state_exemplar_ids),
            pending_dig_state_exemplar_distance=float(pending.state_exemplar_distance),
        )
