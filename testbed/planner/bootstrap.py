"""Bootstrap compatibility gates and scripted qpos action helpers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from testbed.planner.dig_start_alignment_action import pd_servo_action
from testbed.planner.snapshots import (
    mass_in_bucket_from_obs,
    min_distance_to_dig_area_from_obs,
)

if TYPE_CHECKING:
    from testbed.planner.snapshots import PlannerObservationView


@dataclass(frozen=True)
class BootstrapConfig:
    action_dim: int
    end_mode: str
    end_min_bucket_mass_kg: float
    end_min_distance_to_dig_area_m: float
    scripted_target_qpos: np.ndarray | None = None
    scripted_kp: float = 2.0
    scripted_kd: float = 0.25
    scripted_action_clip: float | np.ndarray | list[float] | tuple[float, ...] = 0.35
    scripted_action_signs: np.ndarray | list[float] | tuple[float, ...] | None = None
    scripted_qpos_tolerance: float = 0.02
    scripted_qvel_abs_max: float = 0.08
    scripted_hold_steps: int = 5
    scripted_max_steps: int = 240


@dataclass(frozen=True)
class BootstrapPlannerConfig:
    bootstrap_end_mode: str
    bootstrap_end_min_bucket_mass_kg: float
    bootstrap_end_min_distance_to_dig_area_m: float
    scripted_bootstrap_target_qpos: np.ndarray | None
    scripted_bootstrap_kp: float
    scripted_bootstrap_kd: float
    scripted_bootstrap_action_clip: Any
    scripted_bootstrap_action_signs: np.ndarray
    scripted_bootstrap_qpos_tolerance: float
    scripted_bootstrap_qvel_abs_max: float
    scripted_bootstrap_hold_steps: int
    scripted_bootstrap_max_steps: int

    def planner_items(self) -> tuple[tuple[str, Any], ...]:
        return tuple(self.__dict__.items())


BOOTSTRAP_CONFIG_KEYS: tuple[str, ...] = (
    "bootstrap_end_mode",
    "bootstrap_end_min_bucket_mass_kg",
    "bootstrap_end_min_distance_to_dig_area_m",
    "scripted_bootstrap_target_qpos",
    "scripted_bootstrap_kp",
    "scripted_bootstrap_kd",
    "scripted_bootstrap_action_clip",
    "scripted_bootstrap_action_signs",
    "scripted_bootstrap_qpos_tolerance",
    "scripted_bootstrap_qvel_abs_max",
    "scripted_bootstrap_hold_steps",
    "scripted_bootstrap_max_steps",
)

BOOTSTRAP_RUNTIME_CONFIG_FIELDS: tuple[tuple[str, str], ...] = (
    ("end_mode", "bootstrap_end_mode"),
    ("end_min_bucket_mass_kg", "bootstrap_end_min_bucket_mass_kg"),
    ("end_min_distance_to_dig_area_m", "bootstrap_end_min_distance_to_dig_area_m"),
    ("scripted_target_qpos", "scripted_bootstrap_target_qpos"),
    ("scripted_kp", "scripted_bootstrap_kp"),
    ("scripted_kd", "scripted_bootstrap_kd"),
    ("scripted_action_clip", "scripted_bootstrap_action_clip"),
    ("scripted_action_signs", "scripted_bootstrap_action_signs"),
    ("scripted_qpos_tolerance", "scripted_bootstrap_qpos_tolerance"),
    ("scripted_qvel_abs_max", "scripted_bootstrap_qvel_abs_max"),
    ("scripted_hold_steps", "scripted_bootstrap_hold_steps"),
    ("scripted_max_steps", "scripted_bootstrap_max_steps"),
)


def build_bootstrap_config_from_mapping(
    values: Mapping[str, Any],
    *,
    action_dim: int,
) -> BootstrapConfig:
    return BootstrapConfig(
        action_dim=int(action_dim),
        end_mode=str(values["end_mode"]),
        end_min_bucket_mass_kg=float(values["end_min_bucket_mass_kg"]),
        end_min_distance_to_dig_area_m=float(
            values["end_min_distance_to_dig_area_m"]
        ),
        scripted_target_qpos=values["scripted_target_qpos"],
        scripted_kp=float(values["scripted_kp"]),
        scripted_kd=float(values["scripted_kd"]),
        scripted_action_clip=values["scripted_action_clip"],
        scripted_action_signs=values["scripted_action_signs"],
        scripted_qpos_tolerance=float(values["scripted_qpos_tolerance"]),
        scripted_qvel_abs_max=float(values["scripted_qvel_abs_max"]),
        scripted_hold_steps=int(values["scripted_hold_steps"]),
        scripted_max_steps=int(values["scripted_max_steps"]),
    )


def build_bootstrap_planner_config_from_mapping(
    values: Mapping[str, Any],
    *,
    action_dim: int,
) -> BootstrapPlannerConfig:
    return build_bootstrap_planner_config(
        action_dim=action_dim,
        **{key: values[key] for key in BOOTSTRAP_CONFIG_KEYS},
    )


def build_bootstrap_planner_config(
    *,
    action_dim: int,
    bootstrap_end_mode: str,
    bootstrap_end_min_bucket_mass_kg: float,
    bootstrap_end_min_distance_to_dig_area_m: float,
    scripted_bootstrap_target_qpos: object,
    scripted_bootstrap_kp: float,
    scripted_bootstrap_kd: float,
    scripted_bootstrap_action_clip: object,
    scripted_bootstrap_action_signs: object,
    scripted_bootstrap_qpos_tolerance: float,
    scripted_bootstrap_qvel_abs_max: float,
    scripted_bootstrap_hold_steps: int,
    scripted_bootstrap_max_steps: int,
) -> BootstrapPlannerConfig:
    dim = int(action_dim)
    return BootstrapPlannerConfig(
        bootstrap_end_mode=str(bootstrap_end_mode),
        bootstrap_end_min_bucket_mass_kg=float(bootstrap_end_min_bucket_mass_kg),
        bootstrap_end_min_distance_to_dig_area_m=float(
            bootstrap_end_min_distance_to_dig_area_m
        ),
        scripted_bootstrap_target_qpos=(
            None
            if scripted_bootstrap_target_qpos is None
            else np.asarray(
                scripted_bootstrap_target_qpos,
                dtype=np.float32,
            ).reshape(dim)
        ),
        scripted_bootstrap_kp=float(scripted_bootstrap_kp),
        scripted_bootstrap_kd=float(scripted_bootstrap_kd),
        scripted_bootstrap_action_clip=scripted_bootstrap_action_clip,
        scripted_bootstrap_action_signs=(
            np.ones(dim, dtype=np.float32)
            if scripted_bootstrap_action_signs is None
            else np.asarray(
                scripted_bootstrap_action_signs,
                dtype=np.float32,
            ).reshape(dim)
        ),
        scripted_bootstrap_qpos_tolerance=float(scripted_bootstrap_qpos_tolerance),
        scripted_bootstrap_qvel_abs_max=float(scripted_bootstrap_qvel_abs_max),
        scripted_bootstrap_hold_steps=max(1, int(scripted_bootstrap_hold_steps)),
        scripted_bootstrap_max_steps=max(1, int(scripted_bootstrap_max_steps)),
    )


@dataclass(frozen=True)
class BootstrapFacts:
    qpos: np.ndarray
    qvel: np.ndarray
    mass_in_bucket_kg: float = 0.0
    min_distance_to_dig_area_m: float = 0.0
    qualified_dig_start: bool = False
    step_count: int = 0
    hold_count: int = 0
    bootstrap_policy_present: bool = False


BOOTSTRAP_FACT_FIELDS: tuple[str, ...] = (
    "action_dim",
    "qpos",
    "qvel",
    "mass_in_bucket_kg",
    "min_distance_to_dig_area_m",
    "qualified_dig_start",
    "step_count",
    "hold_count",
    "bootstrap_policy_present",
)


def build_bootstrap_facts(
    *,
    action_dim: int,
    qpos: object | None,
    qvel: object | None,
    mass_in_bucket_kg: float = 0.0,
    min_distance_to_dig_area_m: float = 0.0,
    qualified_dig_start: bool = False,
    step_count: int = 0,
    hold_count: int = 0,
    bootstrap_policy_present: bool = False,
) -> BootstrapFacts:
    dim = int(action_dim)
    qpos_arr = (
        np.zeros(dim, dtype=np.float32)
        if qpos is None
        else np.asarray(qpos, dtype=np.float32).reshape(dim)
    )
    qvel_arr = (
        np.zeros(dim, dtype=np.float32)
        if qvel is None
        else np.asarray(qvel, dtype=np.float32).reshape(dim)
    )
    return BootstrapFacts(
        qpos=qpos_arr,
        qvel=qvel_arr,
        mass_in_bucket_kg=float(mass_in_bucket_kg),
        min_distance_to_dig_area_m=float(min_distance_to_dig_area_m),
        qualified_dig_start=bool(qualified_dig_start),
        step_count=int(step_count),
        hold_count=int(hold_count),
        bootstrap_policy_present=bool(bootstrap_policy_present),
    )


def build_bootstrap_facts_from_mapping(
    values: Mapping[str, Any],
) -> BootstrapFacts:
    return build_bootstrap_facts(
        action_dim=int(values["action_dim"]),
        qpos=values["qpos"],
        qvel=values["qvel"],
        mass_in_bucket_kg=float(values["mass_in_bucket_kg"]),
        min_distance_to_dig_area_m=float(values["min_distance_to_dig_area_m"]),
        qualified_dig_start=bool(values["qualified_dig_start"]),
        step_count=int(values["step_count"]),
        hold_count=int(values["hold_count"]),
        bootstrap_policy_present=bool(values["bootstrap_policy_present"]),
    )


def build_bootstrap_facts_from_observation_view(
    *,
    view: PlannerObservationView,
    boundary_event: Any | None = None,
    step_count: int = 0,
    hold_count: int = 0,
    bootstrap_policy_present: bool = False,
) -> BootstrapFacts:
    return build_bootstrap_facts(
        action_dim=int(view.action_dim),
        qpos=view.obs.get(
            "qpos",
            np.zeros(int(view.action_dim), dtype=np.float32),
        ),
        qvel=view.obs.get(
            "qvel",
            np.zeros(int(view.action_dim), dtype=np.float32),
        ),
        mass_in_bucket_kg=mass_in_bucket_from_obs(view.obs),
        min_distance_to_dig_area_m=min_distance_to_dig_area_from_obs(view.obs),
        qualified_dig_start=(
            boundary_event is not None
            and getattr(boundary_event, "qualified_dig_start", False)
        ),
        step_count=step_count,
        hold_count=hold_count,
        bootstrap_policy_present=bootstrap_policy_present,
    )


@dataclass(frozen=True)
class BootstrapTargetDecision:
    ready: bool
    hold_count: int


@dataclass(frozen=True)
class BootstrapEndDecision:
    should_end: bool
    hold_count: int
    timeout_increment: bool = False


@dataclass(frozen=True)
class BootstrapEndTransitionFacts:
    pre_dig_align_before_dig: bool = False


@dataclass(frozen=True)
class BootstrapTransitionConfig:
    dig_skill_name: str = "dig"
    carry_skill_name: str = "carry"
    pre_dig_align_skill_name: str = "pre_dig_align"
    dig_start_end_modes: tuple[str, ...] = (
        "first_qualified_dig_start",
        "scripted_qpos",
    )


@dataclass(frozen=True)
class BootstrapEndTransitionRequest:
    facts: BootstrapEndTransitionFacts
    transition_config: BootstrapTransitionConfig


@dataclass(frozen=True)
class BootstrapTransitionDecision:
    next_skill: str
    switch_reason: str


@dataclass(frozen=True)
class BootstrapRuntimeStatusState:
    step_count: int
    hold_count: int
    timeout_count: int


BOOTSTRAP_RUNTIME_STATUS_FIELDS: tuple[tuple[str, str], ...] = (
    ("step_count", "_scripted_bootstrap_step_count"),
    ("hold_count", "_scripted_bootstrap_hold_count"),
    ("timeout_count", "_scripted_bootstrap_timeout_count"),
)


@dataclass(frozen=True)
class BootstrapRuntimeStatusSnapshot:
    step_count: int
    hold_count: int
    timeout_count: int


def build_bootstrap_runtime_status_state_from_mapping(
    values: Mapping[str, Any],
) -> BootstrapRuntimeStatusState:
    return BootstrapRuntimeStatusState(
        step_count=int(values["step_count"]),
        hold_count=int(values["hold_count"]),
        timeout_count=int(values["timeout_count"]),
    )


class BootstrapService:
    """Evaluates legacy bootstrap compatibility gates without planner state."""

    @staticmethod
    def facts_from_observation_view(
        *,
        view: PlannerObservationView,
        boundary_event: Any | None = None,
        step_count: int = 0,
        hold_count: int = 0,
        bootstrap_policy_present: bool = False,
    ) -> BootstrapFacts:
        return build_bootstrap_facts_from_observation_view(
            view=view,
            boundary_event=boundary_event,
            step_count=step_count,
            hold_count=hold_count,
            bootstrap_policy_present=bootstrap_policy_present,
        )

    @staticmethod
    def initial_runtime_state() -> BootstrapRuntimeStatusState:
        return BootstrapRuntimeStatusState(
            step_count=0,
            hold_count=0,
            timeout_count=0,
        )

    @staticmethod
    def scripted_enabled(config: BootstrapConfig) -> bool:
        return bool(
            str(config.end_mode) == "scripted_qpos"
            and config.scripted_target_qpos is not None
        )

    @staticmethod
    def runtime_status_snapshot(
        state: BootstrapRuntimeStatusState,
    ) -> BootstrapRuntimeStatusSnapshot:
        return BootstrapRuntimeStatusSnapshot(
            step_count=int(state.step_count),
            hold_count=int(state.hold_count),
            timeout_count=int(state.timeout_count),
        )

    @staticmethod
    def end_transition_request(
        *,
        pre_dig_align_before_dig: object,
        dig_skill_name: object = "dig",
        carry_skill_name: object = "carry",
        pre_dig_align_skill_name: object = "pre_dig_align",
        dig_start_end_modes: tuple[str, ...] = (
            "first_qualified_dig_start",
            "scripted_qpos",
        ),
    ) -> BootstrapEndTransitionRequest:
        return BootstrapEndTransitionRequest(
            facts=BootstrapEndTransitionFacts(
                pre_dig_align_before_dig=bool(pre_dig_align_before_dig)
            ),
            transition_config=BootstrapTransitionConfig(
                dig_skill_name=str(dig_skill_name),
                carry_skill_name=str(carry_skill_name),
                pre_dig_align_skill_name=str(pre_dig_align_skill_name),
                dig_start_end_modes=tuple(str(mode) for mode in dig_start_end_modes),
            ),
        )

    @staticmethod
    def end_transition(
        facts: BootstrapEndTransitionFacts,
        config: BootstrapConfig,
        transition_config: BootstrapTransitionConfig | None = None,
    ) -> BootstrapTransitionDecision:
        transition_config = transition_config or BootstrapTransitionConfig()
        if str(config.end_mode) in {
            str(mode) for mode in transition_config.dig_start_end_modes
        }:
            next_skill = (
                str(transition_config.pre_dig_align_skill_name)
                if bool(facts.pre_dig_align_before_dig)
                else str(transition_config.dig_skill_name)
            )
        else:
            next_skill = str(transition_config.carry_skill_name)
        return BootstrapTransitionDecision(
            next_skill=next_skill,
            switch_reason=f"bootstrap_to_{next_skill}",
        )

    def should_end(
        self,
        facts: BootstrapFacts,
        config: BootstrapConfig,
    ) -> BootstrapEndDecision:
        if self.scripted_enabled(config):
            target = self.scripted_target_reached(facts, config)
            if target.ready:
                return BootstrapEndDecision(
                    should_end=True,
                    hold_count=target.hold_count,
                )
            timed_out = int(facts.step_count) >= int(config.scripted_max_steps)
            return BootstrapEndDecision(
                should_end=timed_out,
                hold_count=target.hold_count,
                timeout_increment=timed_out,
            )

        if not bool(facts.bootstrap_policy_present):
            return BootstrapEndDecision(
                should_end=False,
                hold_count=int(facts.hold_count),
            )

        mode = str(config.end_mode)
        if mode == "first_qualified_dig_start":
            return BootstrapEndDecision(
                should_end=bool(facts.qualified_dig_start),
                hold_count=int(facts.hold_count),
            )
        if mode == "loaded_and_clear":
            return BootstrapEndDecision(
                should_end=bool(
                    float(facts.mass_in_bucket_kg)
                    >= float(config.end_min_bucket_mass_kg)
                    and float(facts.min_distance_to_dig_area_m)
                    >= float(config.end_min_distance_to_dig_area_m)
                ),
                hold_count=int(facts.hold_count),
            )
        if mode == "disabled":
            return BootstrapEndDecision(
                should_end=False,
                hold_count=int(facts.hold_count),
            )
        raise ValueError(f"Unsupported bootstrap_end_mode {mode!r}.")

    def scripted_target_reached(
        self,
        facts: BootstrapFacts,
        config: BootstrapConfig,
    ) -> BootstrapTargetDecision:
        if config.scripted_target_qpos is None:
            return BootstrapTargetDecision(
                ready=False,
                hold_count=int(facts.hold_count),
            )
        action_dim = int(config.action_dim)
        qpos = np.asarray(facts.qpos, dtype=np.float32).reshape(action_dim)
        qvel = np.asarray(facts.qvel, dtype=np.float32).reshape(action_dim)
        target_qpos = np.asarray(
            config.scripted_target_qpos,
            dtype=np.float32,
        ).reshape(action_dim)
        qpos_close = bool(
            np.all(np.abs(qpos - target_qpos) <= float(config.scripted_qpos_tolerance))
        )
        qvel_small = bool(np.all(np.abs(qvel) <= float(config.scripted_qvel_abs_max)))
        hold_count = int(facts.hold_count) + 1 if qpos_close and qvel_small else 0
        return BootstrapTargetDecision(
            ready=bool(hold_count >= int(config.scripted_hold_steps)),
            hold_count=hold_count,
        )

    def scripted_action(
        self,
        facts: BootstrapFacts,
        config: BootstrapConfig,
    ) -> np.ndarray:
        if config.scripted_target_qpos is None:
            raise RuntimeError("scripted bootstrap is active without target qpos.")
        action_dim = int(config.action_dim)
        return pd_servo_action(
            qpos=np.asarray(facts.qpos, dtype=np.float32).reshape(action_dim),
            qvel=np.asarray(facts.qvel, dtype=np.float32).reshape(action_dim),
            target_qpos=np.asarray(
                config.scripted_target_qpos,
                dtype=np.float32,
            ).reshape(action_dim),
            kp=float(config.scripted_kp),
            kd=float(config.scripted_kd),
            action_clip=config.scripted_action_clip,
            action_signs=config.scripted_action_signs,
        )
