"""Dump lifecycle gates for primitive planner state transitions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np


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
class DumpLifecycleFacts:
    mass_in_bucket_kg: float
    deposited_mass_kg: float
    target_geometry: Mapping[str, float]
    semantic_boundary_profile_active: bool
    coverage_cycle_start_deposit_kg: float = 0.0


@dataclass(frozen=True)
class DumpLifecycleOutcome:
    action: str
    switch_reason: str = ""
    coverage_reason: str = ""


class DumpLifecycleGateService:
    """Evaluates dump lifecycle gates without owning planner state."""

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

    @staticmethod
    def carry_outcome(
        *,
        release_safety_done: bool,
        dump_complete_event: bool,
        dump_committed_event: bool,
        release_onset_event: bool,
        legacy_dump_start_event: bool,
        dump_ready_hold_ready: bool,
    ) -> DumpLifecycleOutcome:
        if bool(release_safety_done):
            return DumpLifecycleOutcome(
                action="return",
                switch_reason="carry_to_return_release_safety",
                coverage_reason="carry_release_safety",
            )
        if bool(dump_complete_event):
            return DumpLifecycleOutcome(
                action="return",
                switch_reason="carry_to_return_dump_complete_boundary",
                coverage_reason="carry_dump_complete_boundary",
            )
        if bool(dump_ready_hold_ready):
            reason = (
                "dump_committed_boundary"
                if bool(dump_committed_event)
                else "release_onset_boundary"
                if bool(release_onset_event)
                else "dump_start_boundary"
                if bool(legacy_dump_start_event)
                else "target_ready"
            )
            return DumpLifecycleOutcome(
                action="dump",
                switch_reason=f"carry_to_dump_{reason}",
            )
        return DumpLifecycleOutcome(action="none")

    @staticmethod
    def dump_outcome(
        *,
        dump_complete_event: bool,
        legacy_dump_end_event: bool,
        dump_done_hold_ready: bool,
    ) -> DumpLifecycleOutcome:
        if bool(dump_complete_event) or bool(legacy_dump_end_event):
            coverage_reason = (
                "dump_complete_boundary"
                if bool(dump_complete_event)
                else "dump_end_boundary"
            )
            switch_reason = (
                "dump_to_return_dump_complete_boundary"
                if coverage_reason == "dump_complete_boundary"
                else "dump_to_return_dump_end"
            )
            return DumpLifecycleOutcome(
                action="return",
                switch_reason=switch_reason,
                coverage_reason=coverage_reason,
            )
        if bool(dump_done_hold_ready):
            return DumpLifecycleOutcome(
                action="return",
                switch_reason="dump_to_return_mass_low",
                coverage_reason="dump_mass_low",
            )
        return DumpLifecycleOutcome(action="none")

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
