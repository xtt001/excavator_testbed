"""Pre-dig alignment runtime state projections."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import numpy as np

from testbed.planner.dig_start_alignment_context import DigStartAlignmentConfig

if TYPE_CHECKING:
    from testbed.planner.dig_start_alignment_action import AlignmentActionDecision
    from testbed.planner.dig_start_alignment_readiness import (
        AlignmentReadyDecision,
        SurfaceGuardDecision,
        TimeoutHandoffDecision,
    )


@dataclass(frozen=True)
class DigStartAlignmentRuntimeState:
    step_count: int
    hold_count: int
    timeout_count: int
    completed_count: int
    replan_count: int
    target_qpos: np.ndarray
    error: np.ndarray
    entry_error_m: float
    start_envelope_ready: bool
    entry_close_handoff_ready: bool
    entry_intent_handoff_ready: bool
    timeout_handoff_reason: str
    surface_depth_m: float
    surface_guard_triggered: bool
    surface_guard_count: int


DIG_START_ALIGNMENT_RUNTIME_STATE_FIELDS: tuple[tuple[str, str], ...] = (
    ("step_count", "_pre_dig_align_step_count"),
    ("hold_count", "_pre_dig_align_hold_count"),
    ("timeout_count", "_pre_dig_align_timeout_count"),
    ("completed_count", "_pre_dig_align_completed_count"),
    ("replan_count", "_pre_dig_align_replan_count"),
    ("target_qpos", "_pre_dig_align_target_qpos"),
    ("error", "_pre_dig_align_error"),
    ("entry_error_m", "_pre_dig_align_entry_error_m"),
    ("start_envelope_ready", "_pre_dig_align_start_envelope_ready"),
    ("entry_close_handoff_ready", "_pre_dig_align_entry_close_handoff_ready"),
    ("entry_intent_handoff_ready", "_pre_dig_align_entry_intent_handoff_ready"),
    ("timeout_handoff_reason", "_pre_dig_align_timeout_handoff_reason"),
    ("surface_depth_m", "_pre_dig_align_surface_depth_m"),
    ("surface_guard_triggered", "_pre_dig_align_surface_guard_triggered"),
    ("surface_guard_count", "_pre_dig_align_surface_guard_count"),
)


def runtime_state_from_mapping(
    values: Mapping[str, object],
) -> DigStartAlignmentRuntimeState:
    return DigStartAlignmentRuntimeState(
        step_count=int(values["step_count"]),
        hold_count=int(values["hold_count"]),
        timeout_count=int(values["timeout_count"]),
        completed_count=int(values["completed_count"]),
        replan_count=int(values["replan_count"]),
        target_qpos=values["target_qpos"],
        error=values["error"],
        entry_error_m=float(values["entry_error_m"]),
        start_envelope_ready=bool(values["start_envelope_ready"]),
        entry_close_handoff_ready=bool(values["entry_close_handoff_ready"]),
        entry_intent_handoff_ready=bool(values["entry_intent_handoff_ready"]),
        timeout_handoff_reason=str(values["timeout_handoff_reason"]),
        surface_depth_m=float(values["surface_depth_m"]),
        surface_guard_triggered=bool(values["surface_guard_triggered"]),
        surface_guard_count=int(values["surface_guard_count"]),
    )


@dataclass(frozen=True)
class DigStartAlignmentDebugState:
    surface_depth_m: float
    surface_guard_triggered: bool
    surface_guard_count: int
    step_count: int
    hold_count: int
    timeout_count: int
    completed_count: int
    replan_count: int
    target_qpos: np.ndarray
    error: np.ndarray
    entry_error_m: float
    start_envelope_ready: bool
    entry_close_handoff_ready: bool
    entry_intent_handoff_ready: bool


DIG_START_ALIGNMENT_DEBUG_STATE_FIELDS: tuple[tuple[str, str], ...] = (
    ("surface_depth_m", "_pre_dig_align_surface_depth_m"),
    ("surface_guard_triggered", "_pre_dig_align_surface_guard_triggered"),
    ("surface_guard_count", "_pre_dig_align_surface_guard_count"),
    ("step_count", "_pre_dig_align_step_count"),
    ("hold_count", "_pre_dig_align_hold_count"),
    ("timeout_count", "_pre_dig_align_timeout_count"),
    ("completed_count", "_pre_dig_align_completed_count"),
    ("replan_count", "_pre_dig_align_replan_count"),
    ("target_qpos", "_pre_dig_align_target_qpos"),
    ("error", "_pre_dig_align_error"),
    ("entry_error_m", "_pre_dig_align_entry_error_m"),
    ("start_envelope_ready", "_pre_dig_align_start_envelope_ready"),
    ("entry_close_handoff_ready", "_pre_dig_align_entry_close_handoff_ready"),
    ("entry_intent_handoff_ready", "_pre_dig_align_entry_intent_handoff_ready"),
)


def debug_state_from_mapping(
    values: Mapping[str, object],
) -> DigStartAlignmentDebugState:
    return DigStartAlignmentDebugState(
        surface_depth_m=float(values["surface_depth_m"]),
        surface_guard_triggered=bool(values["surface_guard_triggered"]),
        surface_guard_count=int(values["surface_guard_count"]),
        step_count=int(values["step_count"]),
        hold_count=int(values["hold_count"]),
        timeout_count=int(values["timeout_count"]),
        completed_count=int(values["completed_count"]),
        replan_count=int(values["replan_count"]),
        target_qpos=values["target_qpos"],
        error=values["error"],
        entry_error_m=float(values["entry_error_m"]),
        start_envelope_ready=bool(values["start_envelope_ready"]),
        entry_close_handoff_ready=bool(values["entry_close_handoff_ready"]),
        entry_intent_handoff_ready=bool(values["entry_intent_handoff_ready"]),
    )


@dataclass(frozen=True)
class DigStartAlignmentDebugSnapshot:
    enabled: bool
    entry_intent_controlled_dims: np.ndarray | None
    surface_guard_enabled: bool
    surface_depth_m: float
    surface_guard_triggered: bool
    surface_guard_count: int
    step_count: int
    hold_count: int
    timeout_count: int
    completed_count: int
    replan_count: int
    target_qpos: np.ndarray
    error: np.ndarray
    entry_error_m: float
    start_envelope_ready: bool
    first_dig_entry_close_handoff: bool
    entry_close_handoff_ready: bool
    entry_intent_handoff_enabled: bool
    entry_intent_handoff_ready: bool
    first_dig_entry_close_handoff_qvel_abs_max: float | None
    controlled_dims: np.ndarray
    bucket_target_qpos: float | None


@dataclass(frozen=True)
class PreDigAlignOutcomeRuntimeProjection:
    runtime_state: DigStartAlignmentRuntimeState
    transition_action: str = "none"
    switch_reason: str = ""
    reject_reason: str = ""

    @property
    def should_handoff_to_dig(self) -> bool:
        return self.transition_action == "handoff_to_dig"

    @property
    def should_restart_dig_with_new_cut(self) -> bool:
        return self.transition_action == "restart_dig_with_new_cut"

    @property
    def should_try_replan_handoff(self) -> bool:
        return self.transition_action == "timeout_replan"

    @property
    def should_reject_active_corridor(self) -> bool:
        return self.transition_action in {
            "restart_dig_with_new_cut",
            "timeout_replan",
        }


class DigStartAlignmentRuntimeService:
    """Projects pre-dig alignment runtime state without scheduler side effects."""

    @staticmethod
    def initial_runtime_state(
        config: DigStartAlignmentConfig,
    ) -> DigStartAlignmentRuntimeState:
        return initial_runtime_state(action_dim=int(config.action_dim))

    @staticmethod
    def enter_runtime_state(
        state: DigStartAlignmentRuntimeState,
        config: DigStartAlignmentConfig,
    ) -> DigStartAlignmentRuntimeState:
        return enter_runtime_state(state, action_dim=int(config.action_dim))

    @staticmethod
    def restart_runtime_state(
        state: DigStartAlignmentRuntimeState,
        config: DigStartAlignmentConfig,
    ) -> DigStartAlignmentRuntimeState:
        return restart_runtime_state(state, action_dim=int(config.action_dim))

    @staticmethod
    def replan_handoff_runtime_state(
        state: DigStartAlignmentRuntimeState,
        config: DigStartAlignmentConfig,
    ) -> DigStartAlignmentRuntimeState:
        return replan_handoff_runtime_state(state, action_dim=int(config.action_dim))

    @staticmethod
    def surface_guard_runtime_state(
        state: DigStartAlignmentRuntimeState,
        decision: SurfaceGuardDecision,
    ) -> DigStartAlignmentRuntimeState:
        return surface_guard_runtime_state(state, decision)

    @staticmethod
    def entry_error_runtime_state(
        state: DigStartAlignmentRuntimeState,
        *,
        entry_error_m: float,
    ) -> DigStartAlignmentRuntimeState:
        return entry_error_runtime_state(state, entry_error_m=entry_error_m)

    @staticmethod
    def ready_runtime_state(
        state: DigStartAlignmentRuntimeState,
        decision: AlignmentReadyDecision,
        *,
        entry_error_m: float,
    ) -> DigStartAlignmentRuntimeState:
        return ready_runtime_state(
            state,
            decision,
            entry_error_m=entry_error_m,
        )

    @staticmethod
    def timeout_handoff_runtime_state(
        state: DigStartAlignmentRuntimeState,
        decision: TimeoutHandoffDecision,
        *,
        sampled_entry_error_m: float | None = None,
    ) -> DigStartAlignmentRuntimeState:
        return timeout_handoff_runtime_state(
            state,
            decision,
            sampled_entry_error_m=sampled_entry_error_m,
        )

    @staticmethod
    def action_runtime_state(
        state: DigStartAlignmentRuntimeState,
        decision: AlignmentActionDecision,
    ) -> DigStartAlignmentRuntimeState:
        return action_runtime_state(state, decision)

    @staticmethod
    def target_runtime_state(
        state: DigStartAlignmentRuntimeState,
        *,
        target_qpos: object,
        config: DigStartAlignmentConfig,
    ) -> DigStartAlignmentRuntimeState:
        return target_runtime_state(
            state,
            target_qpos=target_qpos,
            action_dim=int(config.action_dim),
        )

    @staticmethod
    def debug_snapshot(
        *,
        config: DigStartAlignmentConfig,
        state: DigStartAlignmentDebugState,
    ) -> DigStartAlignmentDebugSnapshot:
        return debug_snapshot(
            action_dim=int(config.action_dim),
            enabled=bool(config.enabled),
            entry_intent_controlled_dims=config.entry_intent_controlled_dims,
            surface_guard_enabled=bool(config.surface_guard_enabled),
            first_dig_entry_close_handoff=bool(config.first_dig_entry_close_handoff),
            entry_intent_handoff_enabled=bool(config.entry_intent_handoff_enabled),
            first_dig_entry_close_handoff_qvel_abs_max=(
                config.first_dig_entry_close_handoff_qvel_abs_max
            ),
            controlled_dims=config.controlled_dims,
            bucket_target_qpos=config.bucket_target_qpos,
            state=state,
        )


def initial_runtime_state(*, action_dim: int) -> DigStartAlignmentRuntimeState:
    dim = int(action_dim)
    return DigStartAlignmentRuntimeState(
        step_count=0,
        hold_count=0,
        timeout_count=0,
        completed_count=0,
        replan_count=0,
        target_qpos=np.zeros(dim, dtype=np.float32),
        error=np.zeros(dim, dtype=np.float32),
        entry_error_m=float("nan"),
        start_envelope_ready=False,
        entry_close_handoff_ready=False,
        entry_intent_handoff_ready=False,
        timeout_handoff_reason="",
        surface_depth_m=float("nan"),
        surface_guard_triggered=False,
        surface_guard_count=0,
    )


def enter_runtime_state(
    state: DigStartAlignmentRuntimeState,
    *,
    action_dim: int,
) -> DigStartAlignmentRuntimeState:
    dim = int(action_dim)
    return DigStartAlignmentRuntimeState(
        step_count=0,
        hold_count=0,
        timeout_count=int(state.timeout_count),
        completed_count=int(state.completed_count),
        replan_count=int(state.replan_count),
        target_qpos=np.asarray(state.target_qpos, dtype=np.float32)
        .reshape(dim)
        .copy(),
        error=np.asarray(state.error, dtype=np.float32).reshape(dim).copy(),
        entry_error_m=float(state.entry_error_m),
        start_envelope_ready=bool(state.start_envelope_ready),
        entry_close_handoff_ready=False,
        entry_intent_handoff_ready=False,
        timeout_handoff_reason="",
        surface_depth_m=float(state.surface_depth_m),
        surface_guard_triggered=False,
        surface_guard_count=int(state.surface_guard_count),
    )


def restart_runtime_state(
    state: DigStartAlignmentRuntimeState,
    *,
    action_dim: int,
) -> DigStartAlignmentRuntimeState:
    dim = int(action_dim)
    return DigStartAlignmentRuntimeState(
        step_count=0,
        hold_count=0,
        timeout_count=int(state.timeout_count),
        completed_count=int(state.completed_count),
        replan_count=int(state.replan_count) + 1,
        target_qpos=np.asarray(state.target_qpos, dtype=np.float32)
        .reshape(dim)
        .copy(),
        error=np.asarray(state.error, dtype=np.float32).reshape(dim).copy(),
        entry_error_m=float(state.entry_error_m),
        start_envelope_ready=bool(state.start_envelope_ready),
        entry_close_handoff_ready=bool(state.entry_close_handoff_ready),
        entry_intent_handoff_ready=False,
        timeout_handoff_reason="",
        surface_depth_m=float(state.surface_depth_m),
        surface_guard_triggered=False,
        surface_guard_count=int(state.surface_guard_count),
    )


def replan_handoff_runtime_state(
    state: DigStartAlignmentRuntimeState,
    *,
    action_dim: int,
) -> DigStartAlignmentRuntimeState:
    dim = int(action_dim)
    return DigStartAlignmentRuntimeState(
        step_count=0,
        hold_count=0,
        timeout_count=int(state.timeout_count),
        completed_count=int(state.completed_count) + 1,
        replan_count=int(state.replan_count) + 1,
        target_qpos=np.asarray(state.target_qpos, dtype=np.float32)
        .reshape(dim)
        .copy(),
        error=np.asarray(state.error, dtype=np.float32).reshape(dim).copy(),
        entry_error_m=float(state.entry_error_m),
        start_envelope_ready=bool(state.start_envelope_ready),
        entry_close_handoff_ready=bool(state.entry_close_handoff_ready),
        entry_intent_handoff_ready=bool(state.entry_intent_handoff_ready),
        timeout_handoff_reason=str(state.timeout_handoff_reason),
        surface_depth_m=float(state.surface_depth_m),
        surface_guard_triggered=bool(state.surface_guard_triggered),
        surface_guard_count=int(state.surface_guard_count),
    )


def surface_guard_runtime_state(
    state: DigStartAlignmentRuntimeState,
    decision: SurfaceGuardDecision,
) -> DigStartAlignmentRuntimeState:
    return replace(
        state,
        surface_depth_m=float(decision.surface_depth_m),
        surface_guard_triggered=bool(decision.triggered),
    )


def entry_error_runtime_state(
    state: DigStartAlignmentRuntimeState,
    *,
    entry_error_m: float,
) -> DigStartAlignmentRuntimeState:
    return replace(state, entry_error_m=float(entry_error_m))


def ready_runtime_state(
    state: DigStartAlignmentRuntimeState,
    decision: AlignmentReadyDecision,
    *,
    entry_error_m: float,
) -> DigStartAlignmentRuntimeState:
    return replace(
        state,
        hold_count=int(decision.hold_count),
        error=np.asarray(decision.error, dtype=np.float32).copy(),
        entry_error_m=float(entry_error_m),
        start_envelope_ready=bool(decision.start_envelope_ready),
        entry_close_handoff_ready=bool(decision.entry_close_handoff_ready),
        entry_intent_handoff_ready=bool(decision.entry_intent_handoff_ready),
    )


def timeout_handoff_runtime_state(
    state: DigStartAlignmentRuntimeState,
    decision: TimeoutHandoffDecision,
    *,
    sampled_entry_error_m: float | None = None,
) -> DigStartAlignmentRuntimeState:
    updates: dict[str, object] = {
        "timeout_handoff_reason": str(decision.reason),
    }
    if sampled_entry_error_m is not None:
        updates["entry_error_m"] = float(sampled_entry_error_m)
        updates["start_envelope_ready"] = bool(decision.start_envelope_ready)
        updates["entry_intent_handoff_ready"] = bool(
            state.entry_intent_handoff_ready
            or bool(decision.entry_intent_handoff_ready)
        )
    return replace(state, **updates)


def action_runtime_state(
    state: DigStartAlignmentRuntimeState,
    decision: AlignmentActionDecision,
) -> DigStartAlignmentRuntimeState:
    return replace(
        state,
        error=np.asarray(decision.error, dtype=np.float32).copy(),
        entry_error_m=float(decision.entry_error_m),
    )


def target_runtime_state(
    state: DigStartAlignmentRuntimeState,
    *,
    target_qpos: object,
    action_dim: int,
) -> DigStartAlignmentRuntimeState:
    return replace(
        state,
        target_qpos=np.asarray(target_qpos, dtype=np.float32)
        .reshape(int(action_dim))
        .copy(),
    )


def debug_snapshot(
    *,
    action_dim: int,
    enabled: bool,
    entry_intent_controlled_dims: np.ndarray | None,
    surface_guard_enabled: bool,
    first_dig_entry_close_handoff: bool,
    entry_intent_handoff_enabled: bool,
    first_dig_entry_close_handoff_qvel_abs_max: float | None,
    controlled_dims: np.ndarray,
    bucket_target_qpos: float | None,
    state: DigStartAlignmentDebugState,
) -> DigStartAlignmentDebugSnapshot:
    dim = int(action_dim)
    entry_intent_dims = (
        None
        if entry_intent_controlled_dims is None
        else np.asarray(
            entry_intent_controlled_dims,
            dtype=bool,
        ).reshape(dim).copy()
    )
    return DigStartAlignmentDebugSnapshot(
        enabled=bool(enabled),
        entry_intent_controlled_dims=entry_intent_dims,
        surface_guard_enabled=bool(surface_guard_enabled),
        surface_depth_m=float(state.surface_depth_m),
        surface_guard_triggered=bool(state.surface_guard_triggered),
        surface_guard_count=int(state.surface_guard_count),
        step_count=int(state.step_count),
        hold_count=int(state.hold_count),
        timeout_count=int(state.timeout_count),
        completed_count=int(state.completed_count),
        replan_count=int(state.replan_count),
        target_qpos=np.asarray(state.target_qpos, dtype=np.float32)
        .reshape(dim)
        .copy(),
        error=np.asarray(state.error, dtype=np.float32).reshape(dim).copy(),
        entry_error_m=float(state.entry_error_m),
        start_envelope_ready=bool(state.start_envelope_ready),
        first_dig_entry_close_handoff=bool(first_dig_entry_close_handoff),
        entry_close_handoff_ready=bool(state.entry_close_handoff_ready),
        entry_intent_handoff_enabled=bool(entry_intent_handoff_enabled),
        entry_intent_handoff_ready=bool(state.entry_intent_handoff_ready),
        first_dig_entry_close_handoff_qvel_abs_max=(
            None
            if first_dig_entry_close_handoff_qvel_abs_max is None
            else float(first_dig_entry_close_handoff_qvel_abs_max)
        ),
        controlled_dims=np.asarray(controlled_dims, dtype=bool).reshape(dim).copy(),
        bucket_target_qpos=(
            None if bucket_target_qpos is None else float(bucket_target_qpos)
        ),
    )


def project_pre_dig_align_outcome_runtime(
    *,
    state: DigStartAlignmentRuntimeState,
    outcome_action: str,
    switch_reason: str = "",
    reject_reason: str = "",
) -> PreDigAlignOutcomeRuntimeProjection:
    action = str(outcome_action)
    runtime_state = state
    transition_action = "none"

    if action == "surface_guard_handoff":
        runtime_state = replace(
            state,
            hold_count=0,
            completed_count=int(state.completed_count) + 1,
            surface_guard_count=int(state.surface_guard_count) + 1,
        )
        transition_action = "handoff_to_dig"
    elif action == "surface_guard_replan":
        runtime_state = replace(
            state,
            hold_count=0,
            surface_guard_count=int(state.surface_guard_count) + 1,
        )
        transition_action = "restart_dig_with_new_cut"
    elif action == "ready":
        runtime_state = replace(
            state,
            completed_count=int(state.completed_count) + 1,
        )
        transition_action = "handoff_to_dig"
    elif action == "timeout_handoff":
        runtime_state = replace(
            state,
            timeout_count=int(state.timeout_count) + 1,
        )
        transition_action = "handoff_to_dig"
    elif action == "timeout_replan":
        runtime_state = replace(
            state,
            timeout_count=int(state.timeout_count) + 1,
        )
        transition_action = "timeout_replan"

    return PreDigAlignOutcomeRuntimeProjection(
        runtime_state=runtime_state,
        transition_action=transition_action,
        switch_reason=str(switch_reason),
        reject_reason=str(reject_reason),
    )
