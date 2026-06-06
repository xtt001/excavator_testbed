"""Dump lifecycle gates for primitive planner state transitions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

from testbed.planner import dump_lifecycle_transition as _dump_transition
from testbed.planner.snapshots import (
    deposited_mass_from_obs,
    mass_in_bucket_from_obs,
    target_geometry_from_obs,
)

if TYPE_CHECKING:
    from testbed.planner.snapshots import PlannerObservationView

CarryTransitionRuntimeFacts = _dump_transition.CarryTransitionRuntimeFacts
CarryTransitionRuntimeRequest = _dump_transition.CarryTransitionRuntimeRequest
CarryTransitionRuntimeRequestFacts = (
    _dump_transition.CarryTransitionRuntimeRequestFacts
)
CarryTransitionRuntimeState = _dump_transition.CarryTransitionRuntimeState
DumpLifecycleOutcome = _dump_transition.DumpLifecycleOutcome
DumpLifecycleTransitionService = _dump_transition.DumpLifecycleTransitionService
DumpTransitionRuntimeFacts = _dump_transition.DumpTransitionRuntimeFacts
DumpTransitionRuntimeRequest = _dump_transition.DumpTransitionRuntimeRequest
DumpTransitionRuntimeRequestFacts = _dump_transition.DumpTransitionRuntimeRequestFacts
DumpTransitionRuntimeState = _dump_transition.DumpTransitionRuntimeState
build_carry_transition_runtime_request = (
    _dump_transition.build_carry_transition_runtime_request
)
build_dump_transition_runtime_request = (
    _dump_transition.build_dump_transition_runtime_request
)


@dataclass(frozen=True)
class DumpLifecycleConfig:
    dump_ready_min_bucket_mass_kg: float
    dump_ready_min_height_above_rim_m: float
    dump_ready_require_over_footprint: bool
    dump_ready_require_clearance: bool
    dump_ready_max_horizontal_distance_m: float | None
    dump_ready_position_mode: str
    dump_ready_max_dump_area_footprint_outside_distance_m: float | None
    dump_ready_min_dump_area_relative_x_m: float | None
    dump_ready_max_dump_area_relative_x_m: float | None
    dump_ready_min_dump_area_relative_z_m: float | None
    dump_ready_max_dump_area_relative_z_m: float | None
    dump_ready_near_window_enabled: bool
    dump_ready_near_window_x_tolerance_m: float
    dump_ready_near_window_z_tolerance_m: float
    dump_ready_near_window_outside_tolerance_m: float
    dump_ready_near_window_require_over_footprint: bool
    dump_done_max_bucket_mass_kg: float
    dump_done_min_deposit_delta_kg: float
    approach_ready_min_bucket_mass_kg: float = 0.0
    approach_ready_max_horizontal_distance_m: float | None = None
    approach_ready_min_height_above_rim_m: float = 0.0
    approach_ready_require_clearance: bool = True


@dataclass(frozen=True)
class DumpLifecyclePlannerConfig:
    dump_ready_min_bucket_mass_kg: float
    dump_ready_min_height_above_rim_m: float
    dump_ready_require_over_footprint: bool
    dump_ready_require_clearance: bool
    dump_ready_max_horizontal_distance_m: float | None
    dump_ready_position_mode: str
    dump_ready_max_dump_area_footprint_outside_distance_m: float | None
    dump_ready_min_dump_area_relative_x_m: float | None
    dump_ready_max_dump_area_relative_x_m: float | None
    dump_ready_min_dump_area_relative_z_m: float | None
    dump_ready_max_dump_area_relative_z_m: float | None
    dump_ready_hold_steps: int
    dump_ready_near_window_enabled: bool
    dump_ready_near_window_x_tolerance_m: float
    dump_ready_near_window_z_tolerance_m: float
    dump_ready_near_window_outside_tolerance_m: float
    dump_ready_near_window_require_over_footprint: bool
    dump_done_max_bucket_mass_kg: float
    dump_done_min_deposit_delta_kg: float
    dump_done_hold_steps: int
    dump_done_use_boundary_event: bool

    def planner_items(self) -> tuple[tuple[str, Any], ...]:
        return tuple(self.__dict__.items())


DUMP_LIFECYCLE_CONFIG_KEYS: tuple[str, ...] = (
    "dump_ready_min_bucket_mass_kg",
    "dump_ready_min_height_above_rim_m",
    "dump_ready_require_over_footprint",
    "dump_ready_require_clearance",
    "dump_ready_max_horizontal_distance_m",
    "dump_ready_position_mode",
    "dump_ready_max_dump_area_footprint_outside_distance_m",
    "dump_ready_min_dump_area_relative_x_m",
    "dump_ready_max_dump_area_relative_x_m",
    "dump_ready_min_dump_area_relative_z_m",
    "dump_ready_max_dump_area_relative_z_m",
    "dump_ready_hold_steps",
    "dump_ready_near_window_enabled",
    "dump_ready_near_window_x_tolerance_m",
    "dump_ready_near_window_z_tolerance_m",
    "dump_ready_near_window_outside_tolerance_m",
    "dump_ready_near_window_require_over_footprint",
    "dump_done_max_bucket_mass_kg",
    "dump_done_min_deposit_delta_kg",
    "dump_done_hold_steps",
    "dump_done_use_boundary_event",
)

DUMP_LIFECYCLE_RUNTIME_CONFIG_KEYS: tuple[str, ...] = (
    "dump_ready_min_bucket_mass_kg",
    "dump_ready_min_height_above_rim_m",
    "dump_ready_require_over_footprint",
    "dump_ready_require_clearance",
    "dump_ready_max_horizontal_distance_m",
    "dump_ready_position_mode",
    "dump_ready_max_dump_area_footprint_outside_distance_m",
    "dump_ready_min_dump_area_relative_x_m",
    "dump_ready_max_dump_area_relative_x_m",
    "dump_ready_min_dump_area_relative_z_m",
    "dump_ready_max_dump_area_relative_z_m",
    "dump_ready_near_window_enabled",
    "dump_ready_near_window_x_tolerance_m",
    "dump_ready_near_window_z_tolerance_m",
    "dump_ready_near_window_outside_tolerance_m",
    "dump_ready_near_window_require_over_footprint",
    "dump_done_max_bucket_mass_kg",
    "dump_done_min_deposit_delta_kg",
    "approach_ready_min_bucket_mass_kg",
    "approach_ready_max_horizontal_distance_m",
    "approach_ready_min_height_above_rim_m",
    "approach_ready_require_clearance",
)


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)


def build_dump_lifecycle_config_from_mapping(
    values: Mapping[str, Any],
) -> DumpLifecyclePlannerConfig:
    return build_dump_lifecycle_config(
        **{key: values[key] for key in DUMP_LIFECYCLE_CONFIG_KEYS}
    )


def build_dump_lifecycle_config(
    *,
    dump_ready_min_bucket_mass_kg: float,
    dump_ready_min_height_above_rim_m: float,
    dump_ready_require_over_footprint: bool,
    dump_ready_require_clearance: bool,
    dump_ready_max_horizontal_distance_m: float | None,
    dump_ready_position_mode: str,
    dump_ready_max_dump_area_footprint_outside_distance_m: float | None,
    dump_ready_min_dump_area_relative_x_m: float | None,
    dump_ready_max_dump_area_relative_x_m: float | None,
    dump_ready_min_dump_area_relative_z_m: float | None,
    dump_ready_max_dump_area_relative_z_m: float | None,
    dump_ready_hold_steps: int,
    dump_ready_near_window_enabled: bool,
    dump_ready_near_window_x_tolerance_m: float,
    dump_ready_near_window_z_tolerance_m: float,
    dump_ready_near_window_outside_tolerance_m: float,
    dump_ready_near_window_require_over_footprint: bool,
    dump_done_max_bucket_mass_kg: float,
    dump_done_min_deposit_delta_kg: float,
    dump_done_hold_steps: int,
    dump_done_use_boundary_event: bool,
) -> DumpLifecyclePlannerConfig:
    return DumpLifecyclePlannerConfig(
        dump_ready_min_bucket_mass_kg=float(dump_ready_min_bucket_mass_kg),
        dump_ready_min_height_above_rim_m=float(
            dump_ready_min_height_above_rim_m
        ),
        dump_ready_require_over_footprint=bool(
            dump_ready_require_over_footprint
        ),
        dump_ready_require_clearance=bool(dump_ready_require_clearance),
        dump_ready_max_horizontal_distance_m=_optional_float(
            dump_ready_max_horizontal_distance_m
        ),
        dump_ready_position_mode=str(dump_ready_position_mode),
        dump_ready_max_dump_area_footprint_outside_distance_m=_optional_float(
            dump_ready_max_dump_area_footprint_outside_distance_m
        ),
        dump_ready_min_dump_area_relative_x_m=_optional_float(
            dump_ready_min_dump_area_relative_x_m
        ),
        dump_ready_max_dump_area_relative_x_m=_optional_float(
            dump_ready_max_dump_area_relative_x_m
        ),
        dump_ready_min_dump_area_relative_z_m=_optional_float(
            dump_ready_min_dump_area_relative_z_m
        ),
        dump_ready_max_dump_area_relative_z_m=_optional_float(
            dump_ready_max_dump_area_relative_z_m
        ),
        dump_ready_hold_steps=max(1, int(dump_ready_hold_steps)),
        dump_ready_near_window_enabled=bool(dump_ready_near_window_enabled),
        dump_ready_near_window_x_tolerance_m=float(
            dump_ready_near_window_x_tolerance_m
        ),
        dump_ready_near_window_z_tolerance_m=float(
            dump_ready_near_window_z_tolerance_m
        ),
        dump_ready_near_window_outside_tolerance_m=float(
            dump_ready_near_window_outside_tolerance_m
        ),
        dump_ready_near_window_require_over_footprint=bool(
            dump_ready_near_window_require_over_footprint
        ),
        dump_done_max_bucket_mass_kg=float(dump_done_max_bucket_mass_kg),
        dump_done_min_deposit_delta_kg=float(dump_done_min_deposit_delta_kg),
        dump_done_hold_steps=max(1, int(dump_done_hold_steps)),
        dump_done_use_boundary_event=bool(dump_done_use_boundary_event),
    )


def build_dump_lifecycle_runtime_config(
    *,
    dump_ready_min_bucket_mass_kg: object,
    dump_ready_min_height_above_rim_m: object,
    dump_ready_require_over_footprint: object,
    dump_ready_require_clearance: object,
    dump_ready_max_horizontal_distance_m: object,
    dump_ready_position_mode: object,
    dump_ready_max_dump_area_footprint_outside_distance_m: object,
    dump_ready_min_dump_area_relative_x_m: object,
    dump_ready_max_dump_area_relative_x_m: object,
    dump_ready_min_dump_area_relative_z_m: object,
    dump_ready_max_dump_area_relative_z_m: object,
    dump_ready_near_window_enabled: object,
    dump_ready_near_window_x_tolerance_m: object,
    dump_ready_near_window_z_tolerance_m: object,
    dump_ready_near_window_outside_tolerance_m: object,
    dump_ready_near_window_require_over_footprint: object,
    dump_done_max_bucket_mass_kg: object,
    dump_done_min_deposit_delta_kg: object,
    approach_ready_min_bucket_mass_kg: object = 0.0,
    approach_ready_max_horizontal_distance_m: object = None,
    approach_ready_min_height_above_rim_m: object = 0.0,
    approach_ready_require_clearance: object = True,
) -> DumpLifecycleConfig:
    return DumpLifecycleConfig(
        dump_ready_min_bucket_mass_kg=float(dump_ready_min_bucket_mass_kg),
        dump_ready_min_height_above_rim_m=float(
            dump_ready_min_height_above_rim_m
        ),
        dump_ready_require_over_footprint=bool(
            dump_ready_require_over_footprint
        ),
        dump_ready_require_clearance=bool(dump_ready_require_clearance),
        dump_ready_max_horizontal_distance_m=_optional_float(
            dump_ready_max_horizontal_distance_m
        ),
        dump_ready_position_mode=str(dump_ready_position_mode),
        dump_ready_max_dump_area_footprint_outside_distance_m=_optional_float(
            dump_ready_max_dump_area_footprint_outside_distance_m
        ),
        dump_ready_min_dump_area_relative_x_m=_optional_float(
            dump_ready_min_dump_area_relative_x_m
        ),
        dump_ready_max_dump_area_relative_x_m=_optional_float(
            dump_ready_max_dump_area_relative_x_m
        ),
        dump_ready_min_dump_area_relative_z_m=_optional_float(
            dump_ready_min_dump_area_relative_z_m
        ),
        dump_ready_max_dump_area_relative_z_m=_optional_float(
            dump_ready_max_dump_area_relative_z_m
        ),
        dump_ready_near_window_enabled=bool(dump_ready_near_window_enabled),
        dump_ready_near_window_x_tolerance_m=float(
            dump_ready_near_window_x_tolerance_m
        ),
        dump_ready_near_window_z_tolerance_m=float(
            dump_ready_near_window_z_tolerance_m
        ),
        dump_ready_near_window_outside_tolerance_m=float(
            dump_ready_near_window_outside_tolerance_m
        ),
        dump_ready_near_window_require_over_footprint=bool(
            dump_ready_near_window_require_over_footprint
        ),
        dump_done_max_bucket_mass_kg=float(dump_done_max_bucket_mass_kg),
        dump_done_min_deposit_delta_kg=float(dump_done_min_deposit_delta_kg),
        approach_ready_min_bucket_mass_kg=float(
            approach_ready_min_bucket_mass_kg
        ),
        approach_ready_max_horizontal_distance_m=_optional_float(
            approach_ready_max_horizontal_distance_m
        ),
        approach_ready_min_height_above_rim_m=float(
            approach_ready_min_height_above_rim_m
        ),
        approach_ready_require_clearance=bool(approach_ready_require_clearance),
    )


def build_dump_lifecycle_runtime_config_from_mapping(
    values: Mapping[str, Any],
) -> DumpLifecycleConfig:
    return build_dump_lifecycle_runtime_config(
        dump_ready_min_bucket_mass_kg=values["dump_ready_min_bucket_mass_kg"],
        dump_ready_min_height_above_rim_m=values[
            "dump_ready_min_height_above_rim_m"
        ],
        dump_ready_require_over_footprint=values[
            "dump_ready_require_over_footprint"
        ],
        dump_ready_require_clearance=values["dump_ready_require_clearance"],
        dump_ready_max_horizontal_distance_m=values[
            "dump_ready_max_horizontal_distance_m"
        ],
        dump_ready_position_mode=values["dump_ready_position_mode"],
        dump_ready_max_dump_area_footprint_outside_distance_m=values[
            "dump_ready_max_dump_area_footprint_outside_distance_m"
        ],
        dump_ready_min_dump_area_relative_x_m=values[
            "dump_ready_min_dump_area_relative_x_m"
        ],
        dump_ready_max_dump_area_relative_x_m=values[
            "dump_ready_max_dump_area_relative_x_m"
        ],
        dump_ready_min_dump_area_relative_z_m=values[
            "dump_ready_min_dump_area_relative_z_m"
        ],
        dump_ready_max_dump_area_relative_z_m=values[
            "dump_ready_max_dump_area_relative_z_m"
        ],
        dump_ready_near_window_enabled=values["dump_ready_near_window_enabled"],
        dump_ready_near_window_x_tolerance_m=values[
            "dump_ready_near_window_x_tolerance_m"
        ],
        dump_ready_near_window_z_tolerance_m=values[
            "dump_ready_near_window_z_tolerance_m"
        ],
        dump_ready_near_window_outside_tolerance_m=values[
            "dump_ready_near_window_outside_tolerance_m"
        ],
        dump_ready_near_window_require_over_footprint=values[
            "dump_ready_near_window_require_over_footprint"
        ],
        dump_done_max_bucket_mass_kg=values["dump_done_max_bucket_mass_kg"],
        dump_done_min_deposit_delta_kg=values["dump_done_min_deposit_delta_kg"],
        approach_ready_min_bucket_mass_kg=values.get(
            "approach_ready_min_bucket_mass_kg",
            0.0,
        ),
        approach_ready_max_horizontal_distance_m=values.get(
            "approach_ready_max_horizontal_distance_m",
            None,
        ),
        approach_ready_min_height_above_rim_m=values.get(
            "approach_ready_min_height_above_rim_m",
            0.0,
        ),
        approach_ready_require_clearance=values.get(
            "approach_ready_require_clearance",
            True,
        ),
    )


@dataclass(frozen=True)
class DumpLifecycleFacts:
    mass_in_bucket_kg: float
    deposited_mass_kg: float
    target_geometry: Mapping[str, float]
    semantic_boundary_profile_active: bool
    coverage_cycle_start_deposit_kg: float = 0.0


DUMP_LIFECYCLE_FACT_FIELDS: tuple[str, ...] = (
    "mass_in_bucket_kg",
    "deposited_mass_kg",
    "target_geometry",
    "semantic_boundary_profile_active",
    "coverage_cycle_start_deposit_kg",
)


def build_dump_lifecycle_facts(
    *,
    mass_in_bucket_kg: float,
    deposited_mass_kg: float,
    target_geometry: Mapping[str, float],
    semantic_boundary_profile_active: bool,
    coverage_cycle_start_deposit_kg: float = 0.0,
) -> DumpLifecycleFacts:
    return DumpLifecycleFacts(
        mass_in_bucket_kg=float(mass_in_bucket_kg),
        deposited_mass_kg=float(deposited_mass_kg),
        target_geometry=target_geometry,
        semantic_boundary_profile_active=bool(semantic_boundary_profile_active),
        coverage_cycle_start_deposit_kg=float(coverage_cycle_start_deposit_kg),
    )


def build_dump_lifecycle_facts_from_mapping(
    values: Mapping[str, Any],
) -> DumpLifecycleFacts:
    return build_dump_lifecycle_facts(
        mass_in_bucket_kg=values["mass_in_bucket_kg"],
        deposited_mass_kg=values["deposited_mass_kg"],
        target_geometry=values["target_geometry"],
        semantic_boundary_profile_active=(
            values["semantic_boundary_profile_active"]
        ),
        coverage_cycle_start_deposit_kg=(
            values["coverage_cycle_start_deposit_kg"]
        ),
    )


def build_dump_lifecycle_facts_from_observation_view(
    *,
    view: PlannerObservationView,
    semantic_boundary_profile_active: bool,
    coverage_cycle_start_deposit_kg: float,
) -> DumpLifecycleFacts:
    return build_dump_lifecycle_facts(
        mass_in_bucket_kg=mass_in_bucket_from_obs(view.obs),
        deposited_mass_kg=deposited_mass_from_obs(view.obs),
        target_geometry=target_geometry_from_obs(view.obs),
        semantic_boundary_profile_active=semantic_boundary_profile_active,
        coverage_cycle_start_deposit_kg=coverage_cycle_start_deposit_kg,
    )


@dataclass(frozen=True)
class DumpLifecycleRuntimeState:
    ready_hold_count: int
    done_hold_count: int
    start_deposited_mass_kg: float


@dataclass(frozen=True)
class DumpLifecycleRuntimeStatusState:
    ready_hold_count: int
    done_hold_count: int


DUMP_LIFECYCLE_RUNTIME_STATUS_FIELDS: tuple[tuple[str, str], ...] = (
    ("ready_hold_count", "_dump_ready_hold_count"),
    ("done_hold_count", "_dump_done_hold_count"),
)


def build_dump_lifecycle_runtime_status_state_from_mapping(
    values: Mapping[str, Any],
) -> DumpLifecycleRuntimeStatusState:
    return DumpLifecycleRuntimeStatusState(
        ready_hold_count=int(values["ready_hold_count"]),
        done_hold_count=int(values["done_hold_count"]),
    )


@dataclass(frozen=True)
class DumpLifecycleRuntimeStatusSnapshot:
    ready_hold_count: int
    done_hold_count: int


class DumpLifecycleGateService(DumpLifecycleTransitionService):
    """Evaluates dump lifecycle gates without owning planner state."""

    @staticmethod
    def facts_from_observation_view(
        *,
        view: PlannerObservationView,
        semantic_boundary_profile_active: bool,
        coverage_cycle_start_deposit_kg: float,
    ) -> DumpLifecycleFacts:
        return build_dump_lifecycle_facts_from_observation_view(
            view=view,
            semantic_boundary_profile_active=semantic_boundary_profile_active,
            coverage_cycle_start_deposit_kg=coverage_cycle_start_deposit_kg,
        )

    @staticmethod
    def initial_runtime_state() -> DumpLifecycleRuntimeState:
        return DumpLifecycleRuntimeState(
            ready_hold_count=0,
            done_hold_count=0,
            start_deposited_mass_kg=0.0,
        )

    @staticmethod
    def runtime_status_snapshot(
        state: DumpLifecycleRuntimeStatusState,
    ) -> DumpLifecycleRuntimeStatusSnapshot:
        return DumpLifecycleRuntimeStatusSnapshot(
            ready_hold_count=int(state.ready_hold_count),
            done_hold_count=int(state.done_hold_count),
        )

    def dump_ready(
        self,
        facts: DumpLifecycleFacts,
        config: DumpLifecycleConfig,
    ) -> bool:
        mass = float(facts.mass_in_bucket_kg)
        if mass < float(config.dump_ready_min_bucket_mass_kg):
            return False
        geometry = dict(facts.target_geometry)
        over_footprint = geometry["bucket_over_target_footprint_mask"] > 0.5
        height_ok = (
            geometry["bucket_height_above_target_rim_m"]
            >= float(config.dump_ready_min_height_above_rim_m) - 1.0e-6
        )
        clearance_ok = geometry["dump_clearance_ok_mask"] > 0.5
        horizontal_ok = False
        if config.dump_ready_max_horizontal_distance_m is not None:
            horizontal_ok = (
                geometry["target_horizontal_distance_m"]
                <= float(config.dump_ready_max_horizontal_distance_m) + 1.0e-6
            )
        dump_area_relative_ok = self.dump_area_relative_dump_position_ok(
            geometry,
            config,
        )
        position_ok = self.dump_ready_position_ok(
            over_footprint=over_footprint,
            dump_area_relative_ok=dump_area_relative_ok,
            horizontal_ok=horizontal_ok,
            config=config,
        )
        if not position_ok:
            position_ok = self.dump_area_relative_near_window_ok(
                geometry=geometry,
                over_footprint=over_footprint,
                config=config,
            )
        return bool(
            height_ok
            and position_ok
            and (clearance_ok or not bool(config.dump_ready_require_clearance))
        )

    def dump_area_relative_dump_position_ok(
        self,
        geometry: Mapping[str, float],
        config: DumpLifecycleConfig,
    ) -> bool:
        if config.dump_ready_max_dump_area_footprint_outside_distance_m is None:
            return False
        outside_distance = float(
            geometry.get("bucket_dump_area_footprint_outside_distance_m", np.nan)
        )
        outside_ok = bool(
            np.isfinite(outside_distance)
            and outside_distance >= 0.0
            and outside_distance
            <= float(config.dump_ready_max_dump_area_footprint_outside_distance_m)
            + 1.0e-6
        )
        if not outside_ok:
            return False
        return bool(
            self.optional_range_ok(
                geometry=geometry,
                name="bucket_dump_area_relative_x_m",
                min_value=config.dump_ready_min_dump_area_relative_x_m,
                max_value=config.dump_ready_max_dump_area_relative_x_m,
            )
            and self.optional_range_ok(
                geometry=geometry,
                name="bucket_dump_area_relative_z_m",
                min_value=config.dump_ready_min_dump_area_relative_z_m,
                max_value=config.dump_ready_max_dump_area_relative_z_m,
            )
        )

    def dump_area_relative_near_window_ok(
        self,
        *,
        geometry: Mapping[str, float],
        over_footprint: bool,
        config: DumpLifecycleConfig,
    ) -> bool:
        if not bool(config.dump_ready_near_window_enabled):
            return False
        if config.dump_ready_near_window_require_over_footprint and not over_footprint:
            return False
        if config.dump_ready_max_dump_area_footprint_outside_distance_m is None:
            return False
        outside_distance = float(
            geometry.get("bucket_dump_area_footprint_outside_distance_m", np.nan)
        )
        outside_limit = (
            float(config.dump_ready_max_dump_area_footprint_outside_distance_m)
            + float(config.dump_ready_near_window_outside_tolerance_m)
        )
        outside_ok = bool(
            np.isfinite(outside_distance)
            and outside_distance >= 0.0
            and outside_distance <= outside_limit + 1.0e-6
        )
        if not outside_ok:
            return False
        return bool(
            self.optional_range_near_ok(
                geometry=geometry,
                name="bucket_dump_area_relative_x_m",
                min_value=config.dump_ready_min_dump_area_relative_x_m,
                max_value=config.dump_ready_max_dump_area_relative_x_m,
                tolerance=config.dump_ready_near_window_x_tolerance_m,
            )
            and self.optional_range_near_ok(
                geometry=geometry,
                name="bucket_dump_area_relative_z_m",
                min_value=config.dump_ready_min_dump_area_relative_z_m,
                max_value=config.dump_ready_max_dump_area_relative_z_m,
                tolerance=config.dump_ready_near_window_z_tolerance_m,
            )
        )

    @staticmethod
    def optional_range_ok(
        *,
        geometry: Mapping[str, float],
        name: str,
        min_value: float | None,
        max_value: float | None,
    ) -> bool:
        if min_value is None and max_value is None:
            return True
        value = float(geometry.get(name, np.nan))
        if not np.isfinite(value):
            return False
        if min_value is not None and value < float(min_value) - 1.0e-6:
            return False
        if max_value is not None and value > float(max_value) + 1.0e-6:
            return False
        return True

    @staticmethod
    def optional_range_near_ok(
        *,
        geometry: Mapping[str, float],
        name: str,
        min_value: float | None,
        max_value: float | None,
        tolerance: float,
    ) -> bool:
        if min_value is None and max_value is None:
            return True
        value = float(geometry.get(name, np.nan))
        if not np.isfinite(value):
            return False
        tol = max(0.0, float(tolerance))
        if min_value is not None and value < float(min_value) - tol - 1.0e-6:
            return False
        if max_value is not None and value > float(max_value) + tol + 1.0e-6:
            return False
        return True

    @staticmethod
    def dump_ready_position_ok(
        *,
        over_footprint: bool,
        dump_area_relative_ok: bool,
        horizontal_ok: bool,
        config: DumpLifecycleConfig,
    ) -> bool:
        mode = str(config.dump_ready_position_mode)
        if mode == "footprint_or_dump_area_relative":
            return bool(
                dump_area_relative_ok
                or (over_footprint and config.dump_ready_require_over_footprint)
            )
        if mode == "dump_area_relative":
            return bool(dump_area_relative_ok)
        if mode == "footprint":
            return bool(over_footprint or not config.dump_ready_require_over_footprint)
        if mode == "footprint_or_horizontal":
            return bool(
                horizontal_ok
                or (over_footprint and config.dump_ready_require_over_footprint)
            )
        raise ValueError(
            f"Unsupported dump_ready_position_mode {mode!r}. Expected one of "
            "footprint_or_dump_area_relative, dump_area_relative, footprint, "
            "footprint_or_horizontal."
        )

    def dump_done(
        self,
        facts: DumpLifecycleFacts,
        config: DumpLifecycleConfig,
        *,
        dump_start_deposited_mass_kg: float,
    ) -> bool:
        mass_low = (
            float(facts.mass_in_bucket_kg)
            <= float(config.dump_done_max_bucket_mass_kg)
        )
        deposit_delta = (
            float(facts.deposited_mass_kg) - float(dump_start_deposited_mass_kg)
        )
        return bool(
            mass_low and deposit_delta >= float(config.dump_done_min_deposit_delta_kg)
        )

    def carry_release_safety_done(
        self,
        facts: DumpLifecycleFacts,
        config: DumpLifecycleConfig,
    ) -> bool:
        if not bool(facts.semantic_boundary_profile_active):
            return False
        deposit_delta = (
            float(facts.deposited_mass_kg)
            - float(facts.coverage_cycle_start_deposit_kg)
        )
        return bool(
            float(facts.mass_in_bucket_kg) <= float(config.dump_done_max_bucket_mass_kg)
            and deposit_delta >= float(config.dump_done_min_deposit_delta_kg)
        )

    def approach_ready(
        self,
        facts: DumpLifecycleFacts,
        config: DumpLifecycleConfig,
    ) -> bool:
        if float(facts.mass_in_bucket_kg) < float(
            config.approach_ready_min_bucket_mass_kg
        ):
            return False
        geometry = dict(facts.target_geometry)
        horizontal_ok = True
        if config.approach_ready_max_horizontal_distance_m is not None:
            horizontal_ok = (
                geometry["target_horizontal_distance_m"]
                <= float(config.approach_ready_max_horizontal_distance_m) + 1.0e-6
            )
        height_ok = (
            geometry["bucket_height_above_target_rim_m"]
            >= float(config.approach_ready_min_height_above_rim_m) - 1.0e-6
        )
        clearance_ok = geometry["dump_clearance_ok_mask"] > 0.5
        return bool(
            horizontal_ok
            and height_ok
            and (clearance_ok or not bool(config.approach_ready_require_clearance))
        )
