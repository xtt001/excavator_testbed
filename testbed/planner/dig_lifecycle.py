"""Dig lifecycle gates for primitive planner state transitions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from testbed.planner import dig_lifecycle_transition as _dig_transition

if TYPE_CHECKING:
    from testbed.planner.snapshots import PlannerObservationView

DigLifecycleTransitionService = _dig_transition.DigLifecycleTransitionService
DigTransitionRuntimeFacts = _dig_transition.DigTransitionRuntimeFacts
DigTransitionRuntimeOutcome = _dig_transition.DigTransitionRuntimeOutcome
DigTransitionRuntimeProjection = _dig_transition.DigTransitionRuntimeProjection
DigTransitionRuntimeRequest = _dig_transition.DigTransitionRuntimeRequest
FAILED_DIG_STOP_FACT_FIELDS = _dig_transition.FAILED_DIG_STOP_FACT_FIELDS
FailedDigStopFacts = _dig_transition.FailedDigStopFacts
FailedDigStopState = _dig_transition.FailedDigStopState
build_failed_dig_stop_facts_from_mapping = (
    _dig_transition.build_failed_dig_stop_facts_from_mapping
)
build_failed_dig_stop_facts_from_runtime = (
    _dig_transition.build_failed_dig_stop_facts_from_runtime
)


@dataclass(frozen=True)
class DigLifecycleConfig:
    dig_to_carry_min_bucket_mass_kg: float
    dig_to_carry_min_distance_to_dig_area_m: float
    dig_to_carry_target_bucket_mass_kg: float
    dig_to_carry_mass_plateau_enabled: bool
    dig_to_carry_mass_plateau_min_bucket_mass_kg: float
    dig_to_carry_mass_plateau_epsilon_kg: float
    dig_to_carry_mass_plateau_hold_steps: int
    dig_to_carry_mass_plateau_min_steps: int
    dig_bad_replan_enabled: bool
    dig_bad_replan_max_steps: int
    dig_bad_replan_min_bucket_mass_kg: float
    dig_exit_guard_enabled: bool
    dig_exit_guard_min_steps: int
    dig_exit_guard_overshoot_m: float
    dig_exit_guard_min_bucket_mass_kg: float
    dump_ready_min_bucket_mass_kg: float
    dig_failed_replan_next_skill: str = "dig"
    pre_dig_align_enabled: bool = False
    pre_dig_align_first_dig_only: bool = False
    pre_dig_align_replan_after_failed_dig: bool = False


@dataclass(frozen=True)
class DigLifecyclePlannerConfig:
    dig_to_carry_min_bucket_mass_kg: float
    dig_to_carry_min_distance_to_dig_area_m: float
    dig_to_carry_target_bucket_mass_kg: float
    dig_to_carry_mass_plateau_enabled: bool
    dig_to_carry_mass_plateau_min_bucket_mass_kg: float
    dig_to_carry_mass_plateau_epsilon_kg: float
    dig_to_carry_mass_plateau_hold_steps: int
    dig_to_carry_mass_plateau_min_steps: int
    dig_bad_replan_enabled: bool
    dig_bad_replan_max_steps: int
    dig_bad_replan_min_bucket_mass_kg: float
    dig_exit_guard_enabled: bool
    dig_exit_guard_min_steps: int
    dig_exit_guard_overshoot_m: float
    dig_exit_guard_min_bucket_mass_kg: float
    dig_failed_replan_next_skill: str

    def planner_items(self) -> tuple[tuple[str, Any], ...]:
        return tuple(self.__dict__.items())


DIG_LIFECYCLE_CONFIG_KEYS: tuple[str, ...] = (
    "dig_to_carry_min_bucket_mass_kg",
    "dig_to_carry_min_distance_to_dig_area_m",
    "dig_to_carry_target_bucket_mass_kg",
    "dig_to_carry_mass_plateau_enabled",
    "dig_to_carry_mass_plateau_min_bucket_mass_kg",
    "dig_to_carry_mass_plateau_epsilon_kg",
    "dig_to_carry_mass_plateau_hold_steps",
    "dig_to_carry_mass_plateau_min_steps",
    "dig_bad_replan_enabled",
    "dig_bad_replan_max_steps",
    "dig_bad_replan_min_bucket_mass_kg",
    "dig_exit_guard_enabled",
    "dig_exit_guard_min_steps",
    "dig_exit_guard_overshoot_m",
    "dig_exit_guard_min_bucket_mass_kg",
    "dig_failed_replan_next_skill",
)

DIG_LIFECYCLE_RUNTIME_CONFIG_KEYS: tuple[str, ...] = (
    "dig_to_carry_min_bucket_mass_kg",
    "dig_to_carry_min_distance_to_dig_area_m",
    "dig_to_carry_target_bucket_mass_kg",
    "dig_to_carry_mass_plateau_enabled",
    "dig_to_carry_mass_plateau_min_bucket_mass_kg",
    "dig_to_carry_mass_plateau_epsilon_kg",
    "dig_to_carry_mass_plateau_hold_steps",
    "dig_to_carry_mass_plateau_min_steps",
    "dig_bad_replan_enabled",
    "dig_bad_replan_max_steps",
    "dig_bad_replan_min_bucket_mass_kg",
    "dig_exit_guard_enabled",
    "dig_exit_guard_min_steps",
    "dig_exit_guard_overshoot_m",
    "dig_exit_guard_min_bucket_mass_kg",
    "dump_ready_min_bucket_mass_kg",
    "dig_failed_replan_next_skill",
    "pre_dig_align_enabled",
    "pre_dig_align_first_dig_only",
    "pre_dig_align_replan_after_failed_dig",
)


@dataclass(frozen=True)
class DigLifecycleFacts:
    mass_in_bucket_kg: float
    min_distance_to_dig_area_m: float
    carry_mass_in_bucket_kg: float
    carry_min_distance_to_dig_area_m: float
    semantic_boundary_profile_active: bool
    boundary_dig_complete: bool
    coverage_terminal_stop_requested: bool
    dig_step_count: int
    dig_best_mass_kg: float
    dig_mass_plateau_count: int
    coverage_current_payload_gain_kg: float
    active_corridor_entry_xz: tuple[float, float] | None = None
    active_corridor_exit_xz: tuple[float, float] | None = None
    bucket_tip_xz: tuple[float, float] | None = None


DIG_LIFECYCLE_FACT_FIELDS: tuple[str, ...] = (
    "mass_in_bucket_kg",
    "min_distance_to_dig_area_m",
    "boundary_metrics",
    "semantic_boundary_profile_active",
    "boundary_dig_complete",
    "coverage_terminal_stop_requested",
    "dig_step_count",
    "dig_best_mass_kg",
    "dig_mass_plateau_count",
    "coverage_current_payload_gain_kg",
    "active_corridor",
    "bucket_tip_dig_area_pose",
)


def build_dig_lifecycle_facts(
    *,
    mass_in_bucket_kg: float,
    min_distance_to_dig_area_m: float,
    boundary_metrics: Mapping[str, Any] | None,
    semantic_boundary_profile_active: bool,
    boundary_dig_complete: bool,
    coverage_terminal_stop_requested: bool,
    dig_step_count: int,
    dig_best_mass_kg: float,
    dig_mass_plateau_count: int,
    coverage_current_payload_gain_kg: float,
    active_corridor: Any | None = None,
    bucket_tip_dig_area_pose: tuple[float, float, float] | None = None,
) -> DigLifecycleFacts:
    metrics = dict(boundary_metrics or {})
    mass = float(mass_in_bucket_kg)
    dig_distance = float(min_distance_to_dig_area_m)
    carry_mass = float(metrics.get("mass_in_bucket_kg", mass))
    carry_distance = float(
        metrics.get("min_distance_to_dig_area_m", dig_distance)
    )
    entry_xz: tuple[float, float] | None = None
    exit_xz: tuple[float, float] | None = None
    if active_corridor is not None:
        entry_xz = (
            float(active_corridor.entry_x_m),
            float(active_corridor.entry_z_m),
        )
        exit_xz = (
            float(active_corridor.exit_x_m),
            float(active_corridor.exit_z_m),
        )
    tip_xz = (
        None
        if bucket_tip_dig_area_pose is None
        else (float(bucket_tip_dig_area_pose[0]), float(bucket_tip_dig_area_pose[2]))
    )
    return DigLifecycleFacts(
        mass_in_bucket_kg=mass,
        min_distance_to_dig_area_m=dig_distance,
        carry_mass_in_bucket_kg=carry_mass,
        carry_min_distance_to_dig_area_m=carry_distance,
        semantic_boundary_profile_active=bool(semantic_boundary_profile_active),
        boundary_dig_complete=bool(boundary_dig_complete),
        coverage_terminal_stop_requested=bool(coverage_terminal_stop_requested),
        dig_step_count=int(dig_step_count),
        dig_best_mass_kg=float(dig_best_mass_kg),
        dig_mass_plateau_count=int(dig_mass_plateau_count),
        coverage_current_payload_gain_kg=float(coverage_current_payload_gain_kg),
        active_corridor_entry_xz=entry_xz,
        active_corridor_exit_xz=exit_xz,
        bucket_tip_xz=tip_xz,
    )


def build_dig_lifecycle_facts_from_mapping(
    values: Mapping[str, Any],
) -> DigLifecycleFacts:
    return build_dig_lifecycle_facts(
        mass_in_bucket_kg=values["mass_in_bucket_kg"],
        min_distance_to_dig_area_m=values["min_distance_to_dig_area_m"],
        boundary_metrics=values["boundary_metrics"],
        semantic_boundary_profile_active=(
            values["semantic_boundary_profile_active"]
        ),
        boundary_dig_complete=values["boundary_dig_complete"],
        coverage_terminal_stop_requested=(
            values["coverage_terminal_stop_requested"]
        ),
        dig_step_count=values["dig_step_count"],
        dig_best_mass_kg=values["dig_best_mass_kg"],
        dig_mass_plateau_count=values["dig_mass_plateau_count"],
        coverage_current_payload_gain_kg=(
            values["coverage_current_payload_gain_kg"]
        ),
        active_corridor=values["active_corridor"],
        bucket_tip_dig_area_pose=values["bucket_tip_dig_area_pose"],
    )


def build_dig_lifecycle_facts_from_observation_view(
    *,
    view: PlannerObservationView,
    boundary_event: Any | None,
    semantic_boundary_profile_active: bool,
    coverage_terminal_stop_requested: bool,
    dig_step_count: int,
    dig_best_mass_kg: float,
    dig_mass_plateau_count: int,
    coverage_current_payload_gain_kg: float,
    active_corridor: Any | None = None,
) -> DigLifecycleFacts:
    return build_dig_lifecycle_facts(
        mass_in_bucket_kg=view.mass_in_bucket_kg,
        min_distance_to_dig_area_m=view.min_distance_to_dig_area_m,
        boundary_metrics=getattr(boundary_event, "metrics", None),
        semantic_boundary_profile_active=semantic_boundary_profile_active,
        boundary_dig_complete=(
            boundary_event is not None
            and getattr(boundary_event, "dig_complete", False)
        ),
        coverage_terminal_stop_requested=coverage_terminal_stop_requested,
        dig_step_count=dig_step_count,
        dig_best_mass_kg=dig_best_mass_kg,
        dig_mass_plateau_count=dig_mass_plateau_count,
        coverage_current_payload_gain_kg=coverage_current_payload_gain_kg,
        active_corridor=active_corridor,
        bucket_tip_dig_area_pose=view.bucket_tip_dig_area_pose,
    )


@dataclass(frozen=True)
class DigProgressState:
    step_count: int
    best_mass_kg: float
    mass_plateau_count: int
    coverage_payload_gain_kg: float


@dataclass(frozen=True)
class DigLifecycleEntryRuntimeFacts:
    bad_replan_count: int
    exit_guard_replan_count: int


DIG_LIFECYCLE_ENTRY_RUNTIME_FACT_FIELDS: tuple[tuple[str, str], ...] = (
    ("bad_replan_count", "_dig_bad_replan_count"),
    ("exit_guard_replan_count", "_dig_exit_guard_replan_count"),
)


def build_dig_lifecycle_entry_runtime_facts_from_mapping(
    values: Mapping[str, Any],
) -> DigLifecycleEntryRuntimeFacts:
    return DigLifecycleEntryRuntimeFacts(
        bad_replan_count=int(values["bad_replan_count"]),
        exit_guard_replan_count=int(values["exit_guard_replan_count"]),
    )


@dataclass(frozen=True)
class DigLifecycleEntryRuntimeState:
    step_count: int
    best_mass_kg: float
    mass_plateau_count: int
    dig_to_carry_reason: str
    coverage_payload_gain_kg: float
    bad_replan_count: int
    exit_guard_replan_count: int


@dataclass(frozen=True)
class DigLifecycleRuntimeStatusState:
    step_count: int
    best_mass_kg: float
    mass_plateau_count: int
    dig_to_carry_reason: str
    bad_replan_count: int
    exit_guard_replan_count: int


DIG_LIFECYCLE_RUNTIME_STATUS_FIELDS: tuple[tuple[str, str], ...] = (
    ("step_count", "_dig_step_count"),
    ("best_mass_kg", "_dig_best_mass_kg"),
    ("mass_plateau_count", "_dig_mass_plateau_count"),
    ("dig_to_carry_reason", "_dig_to_carry_reason"),
    ("bad_replan_count", "_dig_bad_replan_count"),
    ("exit_guard_replan_count", "_dig_exit_guard_replan_count"),
)


@dataclass(frozen=True)
class DigLifecycleRuntimeStatusSnapshot:
    failed_replan_next_skill: str
    step_count: int
    best_mass_kg: float
    mass_plateau_count: int
    dig_to_carry_reason: str
    bad_replan_count: int
    exit_guard_replan_count: int


@dataclass(frozen=True)
class DigGateDecision:
    ready: bool
    reason: str = ""


@dataclass(frozen=True)
class FailedDigRecoveryFacts:
    cycle_index: int


@dataclass(frozen=True)
class FailedDigRecoveryDecision:
    next_skill: str
    switch_reason: str
    terminal_reason: str = ""


def normalize_failed_dig_replan_skill(value: object) -> str:
    skill = str(value or "dig").strip().lower().replace("-", "_")
    aliases = {
        "fail": "stop",
        "fail_fast": "stop",
        "terminal": "stop",
        "terminal_stop": "stop",
        "same": "dig",
        "same_dig": "dig",
        "new_dig": "dig",
    }
    skill = aliases.get(skill, skill)
    if skill not in {"dig", "stop"}:
        raise ValueError("dig_failed_replan_next_skill must be 'dig' or 'stop'.")
    return skill


def build_dig_lifecycle_config_from_mapping(
    values: Mapping[str, Any],
) -> DigLifecyclePlannerConfig:
    return build_dig_lifecycle_config(
        **{key: values[key] for key in DIG_LIFECYCLE_CONFIG_KEYS}
    )


def build_dig_lifecycle_config(
    *,
    dig_to_carry_min_bucket_mass_kg: float,
    dig_to_carry_min_distance_to_dig_area_m: float,
    dig_to_carry_target_bucket_mass_kg: float | None,
    dig_to_carry_mass_plateau_enabled: bool,
    dig_to_carry_mass_plateau_min_bucket_mass_kg: float,
    dig_to_carry_mass_plateau_epsilon_kg: float,
    dig_to_carry_mass_plateau_hold_steps: int,
    dig_to_carry_mass_plateau_min_steps: int,
    dig_bad_replan_enabled: bool,
    dig_bad_replan_max_steps: int,
    dig_bad_replan_min_bucket_mass_kg: float,
    dig_exit_guard_enabled: bool,
    dig_exit_guard_min_steps: int,
    dig_exit_guard_overshoot_m: float,
    dig_exit_guard_min_bucket_mass_kg: float,
    dig_failed_replan_next_skill: object,
) -> DigLifecyclePlannerConfig:
    min_bucket_mass = float(dig_to_carry_min_bucket_mass_kg)
    return DigLifecyclePlannerConfig(
        dig_to_carry_min_bucket_mass_kg=min_bucket_mass,
        dig_to_carry_min_distance_to_dig_area_m=float(
            dig_to_carry_min_distance_to_dig_area_m
        ),
        dig_to_carry_target_bucket_mass_kg=float(
            min_bucket_mass
            if dig_to_carry_target_bucket_mass_kg is None
            else dig_to_carry_target_bucket_mass_kg
        ),
        dig_to_carry_mass_plateau_enabled=bool(
            dig_to_carry_mass_plateau_enabled
        ),
        dig_to_carry_mass_plateau_min_bucket_mass_kg=float(
            dig_to_carry_mass_plateau_min_bucket_mass_kg
        ),
        dig_to_carry_mass_plateau_epsilon_kg=float(
            dig_to_carry_mass_plateau_epsilon_kg
        ),
        dig_to_carry_mass_plateau_hold_steps=max(
            1,
            int(dig_to_carry_mass_plateau_hold_steps),
        ),
        dig_to_carry_mass_plateau_min_steps=max(
            1,
            int(dig_to_carry_mass_plateau_min_steps),
        ),
        dig_bad_replan_enabled=bool(dig_bad_replan_enabled),
        dig_bad_replan_max_steps=max(1, int(dig_bad_replan_max_steps)),
        dig_bad_replan_min_bucket_mass_kg=float(
            dig_bad_replan_min_bucket_mass_kg
        ),
        dig_exit_guard_enabled=bool(dig_exit_guard_enabled),
        dig_exit_guard_min_steps=max(1, int(dig_exit_guard_min_steps)),
        dig_exit_guard_overshoot_m=float(dig_exit_guard_overshoot_m),
        dig_exit_guard_min_bucket_mass_kg=float(
            dig_exit_guard_min_bucket_mass_kg
        ),
        dig_failed_replan_next_skill=normalize_failed_dig_replan_skill(
            dig_failed_replan_next_skill
        ),
    )


def build_dig_lifecycle_runtime_config(
    *,
    dig_to_carry_min_bucket_mass_kg: object,
    dig_to_carry_min_distance_to_dig_area_m: object,
    dig_to_carry_target_bucket_mass_kg: object,
    dig_to_carry_mass_plateau_enabled: object,
    dig_to_carry_mass_plateau_min_bucket_mass_kg: object,
    dig_to_carry_mass_plateau_epsilon_kg: object,
    dig_to_carry_mass_plateau_hold_steps: object,
    dig_to_carry_mass_plateau_min_steps: object,
    dig_bad_replan_enabled: object,
    dig_bad_replan_max_steps: object,
    dig_bad_replan_min_bucket_mass_kg: object,
    dig_exit_guard_enabled: object,
    dig_exit_guard_min_steps: object,
    dig_exit_guard_overshoot_m: object,
    dig_exit_guard_min_bucket_mass_kg: object,
    dump_ready_min_bucket_mass_kg: object,
    dig_failed_replan_next_skill: object,
    pre_dig_align_enabled: object,
    pre_dig_align_first_dig_only: object,
    pre_dig_align_replan_after_failed_dig: object,
) -> DigLifecycleConfig:
    return DigLifecycleConfig(
        dig_to_carry_min_bucket_mass_kg=float(dig_to_carry_min_bucket_mass_kg),
        dig_to_carry_min_distance_to_dig_area_m=float(
            dig_to_carry_min_distance_to_dig_area_m
        ),
        dig_to_carry_target_bucket_mass_kg=float(
            dig_to_carry_target_bucket_mass_kg
        ),
        dig_to_carry_mass_plateau_enabled=bool(
            dig_to_carry_mass_plateau_enabled
        ),
        dig_to_carry_mass_plateau_min_bucket_mass_kg=float(
            dig_to_carry_mass_plateau_min_bucket_mass_kg
        ),
        dig_to_carry_mass_plateau_epsilon_kg=float(
            dig_to_carry_mass_plateau_epsilon_kg
        ),
        dig_to_carry_mass_plateau_hold_steps=int(
            dig_to_carry_mass_plateau_hold_steps
        ),
        dig_to_carry_mass_plateau_min_steps=int(
            dig_to_carry_mass_plateau_min_steps
        ),
        dig_bad_replan_enabled=bool(dig_bad_replan_enabled),
        dig_bad_replan_max_steps=int(dig_bad_replan_max_steps),
        dig_bad_replan_min_bucket_mass_kg=float(dig_bad_replan_min_bucket_mass_kg),
        dig_exit_guard_enabled=bool(dig_exit_guard_enabled),
        dig_exit_guard_min_steps=int(dig_exit_guard_min_steps),
        dig_exit_guard_overshoot_m=float(dig_exit_guard_overshoot_m),
        dig_exit_guard_min_bucket_mass_kg=float(dig_exit_guard_min_bucket_mass_kg),
        dump_ready_min_bucket_mass_kg=float(dump_ready_min_bucket_mass_kg),
        dig_failed_replan_next_skill=str(dig_failed_replan_next_skill),
        pre_dig_align_enabled=bool(pre_dig_align_enabled),
        pre_dig_align_first_dig_only=bool(pre_dig_align_first_dig_only),
        pre_dig_align_replan_after_failed_dig=bool(
            pre_dig_align_replan_after_failed_dig
        ),
    )


def build_dig_lifecycle_runtime_config_from_mapping(
    values: Mapping[str, Any],
) -> DigLifecycleConfig:
    return build_dig_lifecycle_runtime_config(
        **{key: values[key] for key in DIG_LIFECYCLE_RUNTIME_CONFIG_KEYS}
    )


def build_dig_lifecycle_runtime_status_state_from_mapping(
    values: Mapping[str, Any],
) -> DigLifecycleRuntimeStatusState:
    return DigLifecycleRuntimeStatusState(
        step_count=int(values["step_count"]),
        best_mass_kg=float(values["best_mass_kg"]),
        mass_plateau_count=int(values["mass_plateau_count"]),
        dig_to_carry_reason=str(values["dig_to_carry_reason"]),
        bad_replan_count=int(values["bad_replan_count"]),
        exit_guard_replan_count=int(values["exit_guard_replan_count"]),
    )


class DigLifecycleGateService(DigLifecycleTransitionService):
    """Evaluates dig lifecycle gates without owning scheduler state."""

    @staticmethod
    def facts_from_observation_view(
        *,
        view: PlannerObservationView,
        boundary_event: Any | None,
        semantic_boundary_profile_active: bool,
        coverage_terminal_stop_requested: bool,
        dig_step_count: int,
        dig_best_mass_kg: float,
        dig_mass_plateau_count: int,
        coverage_current_payload_gain_kg: float,
        active_corridor: Any | None = None,
    ) -> DigLifecycleFacts:
        return build_dig_lifecycle_facts_from_observation_view(
            view=view,
            boundary_event=boundary_event,
            semantic_boundary_profile_active=semantic_boundary_profile_active,
            coverage_terminal_stop_requested=coverage_terminal_stop_requested,
            dig_step_count=dig_step_count,
            dig_best_mass_kg=dig_best_mass_kg,
            dig_mass_plateau_count=dig_mass_plateau_count,
            coverage_current_payload_gain_kg=coverage_current_payload_gain_kg,
            active_corridor=active_corridor,
        )

    @staticmethod
    def initial_runtime_state() -> DigLifecycleRuntimeStatusState:
        return DigLifecycleRuntimeStatusState(
            step_count=0,
            best_mass_kg=0.0,
            mass_plateau_count=0,
            dig_to_carry_reason="",
            bad_replan_count=0,
            exit_guard_replan_count=0,
        )

    @staticmethod
    def entry_runtime_state(
        facts: DigLifecycleEntryRuntimeFacts,
    ) -> DigLifecycleEntryRuntimeState:
        return DigLifecycleEntryRuntimeState(
            step_count=0,
            best_mass_kg=0.0,
            mass_plateau_count=0,
            dig_to_carry_reason="",
            coverage_payload_gain_kg=0.0,
            bad_replan_count=int(facts.bad_replan_count),
            exit_guard_replan_count=int(facts.exit_guard_replan_count),
        )

    @staticmethod
    def runtime_status_snapshot(
        *,
        config: DigLifecycleConfig,
        state: DigLifecycleRuntimeStatusState,
    ) -> DigLifecycleRuntimeStatusSnapshot:
        return DigLifecycleRuntimeStatusSnapshot(
            failed_replan_next_skill=str(config.dig_failed_replan_next_skill),
            step_count=int(state.step_count),
            best_mass_kg=float(state.best_mass_kg),
            mass_plateau_count=int(state.mass_plateau_count),
            dig_to_carry_reason=str(state.dig_to_carry_reason),
            bad_replan_count=int(state.bad_replan_count),
            exit_guard_replan_count=int(state.exit_guard_replan_count),
        )

    def update_progress(
        self,
        facts: DigLifecycleFacts,
        config: DigLifecycleConfig,
    ) -> DigProgressState:
        step_count = int(facts.dig_step_count) + 1
        mass = float(facts.mass_in_bucket_kg)
        previous_best = float(facts.dig_best_mass_kg)
        if mass > previous_best + float(config.dig_to_carry_mass_plateau_epsilon_kg):
            best_mass = mass
            plateau_count = 0
        else:
            best_mass = max(previous_best, mass)
            plateau_count = int(facts.dig_mass_plateau_count) + 1
        payload_gain = max(
            float(facts.coverage_current_payload_gain_kg),
            mass,
        )
        return DigProgressState(
            step_count=step_count,
            best_mass_kg=float(best_mass),
            mass_plateau_count=int(plateau_count),
            coverage_payload_gain_kg=float(payload_gain),
        )

    def bad_replan_ready(
        self,
        facts: DigLifecycleFacts,
        config: DigLifecycleConfig,
    ) -> bool:
        if not bool(config.dig_bad_replan_enabled):
            return False
        if bool(facts.coverage_terminal_stop_requested):
            return False
        if int(facts.dig_step_count) < int(config.dig_bad_replan_max_steps):
            return False
        return bool(
            float(facts.mass_in_bucket_kg)
            < float(config.dig_bad_replan_min_bucket_mass_kg)
        )

    def exit_guard_ready(
        self,
        facts: DigLifecycleFacts,
        config: DigLifecycleConfig,
    ) -> bool:
        if not bool(config.dig_exit_guard_enabled):
            return False
        if bool(facts.coverage_terminal_stop_requested):
            return False
        if int(facts.dig_step_count) < int(config.dig_exit_guard_min_steps):
            return False
        if float(facts.mass_in_bucket_kg) >= float(
            config.dig_exit_guard_min_bucket_mass_kg
        ):
            return False
        overshoot = self.exit_overshoot_m(facts)
        return bool(
            np.isfinite(overshoot)
            and overshoot >= float(config.dig_exit_guard_overshoot_m)
        )

    @staticmethod
    def exit_overshoot_m(facts: DigLifecycleFacts) -> float:
        if (
            facts.active_corridor_entry_xz is None
            or facts.active_corridor_exit_xz is None
            or facts.bucket_tip_xz is None
        ):
            return float("nan")
        entry = np.asarray(facts.active_corridor_entry_xz, dtype=np.float32).reshape(2)
        exit_point = np.asarray(
            facts.active_corridor_exit_xz,
            dtype=np.float32,
        ).reshape(2)
        tip = np.asarray(facts.bucket_tip_xz, dtype=np.float32).reshape(2)
        direction = exit_point - entry
        length = float(np.linalg.norm(direction))
        if length <= 1.0e-6 or not np.all(np.isfinite(tip)):
            return float("nan")
        unit = direction / length
        progress = float(np.dot(tip - entry, unit))
        return float(progress - length)

    def dig_to_carry_ready(
        self,
        facts: DigLifecycleFacts,
        config: DigLifecycleConfig,
    ) -> DigGateDecision:
        if bool(facts.boundary_dig_complete):
            return DigGateDecision(True, "dig_complete_boundary")
        if bool(facts.semantic_boundary_profile_active):
            return self.semantic_liveness_ready(facts, config)
        mass = float(facts.carry_mass_in_bucket_kg)
        dig_distance = float(facts.carry_min_distance_to_dig_area_m)
        distance_ready = bool(
            dig_distance >= float(config.dig_to_carry_min_distance_to_dig_area_m)
        )
        if mass >= float(config.dig_to_carry_target_bucket_mass_kg) and distance_ready:
            if (
                abs(
                    float(config.dig_to_carry_target_bucket_mass_kg)
                    - float(config.dig_to_carry_min_bucket_mass_kg)
                )
                <= 1.0e-6
            ):
                return DigGateDecision(True, "loaded")
            return DigGateDecision(True, "target_payload_loaded")
        if (
            bool(config.dig_to_carry_mass_plateau_enabled)
            and int(facts.dig_step_count)
            >= int(config.dig_to_carry_mass_plateau_min_steps)
            and mass >= float(config.dig_to_carry_mass_plateau_min_bucket_mass_kg)
            and int(facts.dig_mass_plateau_count)
            >= int(config.dig_to_carry_mass_plateau_hold_steps)
            and distance_ready
        ):
            return DigGateDecision(True, "mass_plateau")
        return DigGateDecision(False, "")

    def semantic_liveness_ready(
        self,
        facts: DigLifecycleFacts,
        config: DigLifecycleConfig,
    ) -> DigGateDecision:
        mass = float(facts.carry_mass_in_bucket_kg)
        dig_distance = float(facts.carry_min_distance_to_dig_area_m)
        distance_ready = bool(
            dig_distance >= float(config.dig_to_carry_min_distance_to_dig_area_m)
        )
        if not distance_ready:
            return DigGateDecision(False, "")
        if mass >= float(config.dig_to_carry_target_bucket_mass_kg):
            return DigGateDecision(True, "semantic_material_loaded")
        if (
            bool(config.dig_to_carry_mass_plateau_enabled)
            and int(facts.dig_step_count)
            >= int(config.dig_to_carry_mass_plateau_min_steps)
            and mass >= float(config.dig_to_carry_mass_plateau_min_bucket_mass_kg)
            and int(facts.dig_mass_plateau_count)
            >= int(config.dig_to_carry_mass_plateau_hold_steps)
        ):
            return DigGateDecision(True, "semantic_material_plateau")
        return DigGateDecision(False, "")

    def complete_boundary_low_payload(
        self,
        facts: DigLifecycleFacts,
        config: DigLifecycleConfig,
    ) -> bool:
        if not bool(facts.semantic_boundary_profile_active):
            return False
        if not bool(facts.boundary_dig_complete):
            return False
        min_carry_mass = max(
            float(config.dig_to_carry_min_bucket_mass_kg),
            float(config.dump_ready_min_bucket_mass_kg),
        )
        return bool(float(facts.mass_in_bucket_kg) < min_carry_mass)

    def pre_dig_align_before_dig(
        self,
        facts: FailedDigRecoveryFacts,
        config: DigLifecycleConfig,
    ) -> bool:
        if not bool(config.pre_dig_align_enabled):
            return False
        if not bool(config.pre_dig_align_first_dig_only):
            return True
        return int(facts.cycle_index) == 0

    @staticmethod
    def pre_dig_align_after_failed_dig(config: DigLifecycleConfig) -> bool:
        return bool(
            config.pre_dig_align_enabled
            and config.pre_dig_align_replan_after_failed_dig
        )

    def failed_dig_recovery(
        self,
        *,
        reason: str,
        facts: FailedDigRecoveryFacts,
        config: DigLifecycleConfig,
    ) -> FailedDigRecoveryDecision:
        reason = str(reason)
        if self.pre_dig_align_before_dig(
            facts,
            config,
        ) or self.pre_dig_align_after_failed_dig(config):
            return FailedDigRecoveryDecision(
                next_skill="pre_dig_align",
                switch_reason=f"dig_to_pre_dig_align_{reason}",
            )
        if str(config.dig_failed_replan_next_skill) == "stop":
            return FailedDigRecoveryDecision(
                next_skill="stop",
                switch_reason=f"dig_failed_stop_{reason}",
                terminal_reason=f"dig_failed_{reason}",
            )
        return FailedDigRecoveryDecision(
            next_skill="dig",
            switch_reason=f"dig_retry_{reason}",
        )
