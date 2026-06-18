from __future__ import annotations

from testbed.planner import dump_lifecycle
from testbed.planner.dump_lifecycle import (
    DumpLifecycleConfig,
    DumpLifecycleFacts,
    DumpLifecycleGateService,
    DumpLifecycleOutcome,
)


def test_carry_transition_runtime_skips_dump_ready_after_dump_complete_event() -> None:
    calls: list[str] = []

    class SpyService(DumpLifecycleGateService):
        def carry_release_safety_done(
            self,
            facts: DumpLifecycleFacts,
            config: DumpLifecycleConfig,
        ) -> bool:
            calls.append("release_safety")
            return False

        def dump_ready(
            self,
            facts: DumpLifecycleFacts,
            config: DumpLifecycleConfig,
        ) -> bool:
            raise AssertionError("dump_ready must not run after dump_complete")

    runtime = dump_lifecycle.carry_transition_runtime_from_facts(
        service=SpyService(),
        facts=_facts(),
        config=_config(),
        boundary_event=_event(dump_complete=True),
        semantic_boundary_profile_active=True,
        current_dump_ready_hold_count=2,
        dump_ready_hold_steps=3,
    )

    assert calls == ["release_safety"]
    assert runtime.dump_ready_hold_count == 2
    assert runtime.outcome == DumpLifecycleOutcome(
        action="return",
        switch_reason="carry_to_return_dump_complete_boundary",
        coverage_reason="carry_dump_complete_boundary",
    )


def test_dump_transition_runtime_skips_dump_done_after_dump_complete_event() -> None:
    class SpyService(DumpLifecycleGateService):
        def dump_done(
            self,
            facts: DumpLifecycleFacts,
            config: DumpLifecycleConfig,
            *,
            dump_start_deposited_mass_kg: float,
        ) -> bool:
            raise AssertionError("dump_done must not run after dump_complete")

    runtime = dump_lifecycle.dump_transition_runtime_from_facts(
        service=SpyService(),
        facts=_facts(),
        config=_config(),
        boundary_event=_event(dump_complete=True),
        semantic_boundary_profile_active=True,
        current_dump_done_hold_count=4,
        dump_done_hold_steps=3,
        dump_done_use_boundary_event=True,
        dump_start_deposited_mass_kg=10.0,
    )

    assert runtime.dump_done_hold_count == 4
    assert runtime.outcome == DumpLifecycleOutcome(
        action="return",
        switch_reason="dump_to_return_dump_complete_boundary",
        coverage_reason="dump_complete_boundary",
    )


def _config(**overrides: object) -> DumpLifecycleConfig:
    values = {
        "dump_ready_min_bucket_mass_kg": 150.0,
        "dump_ready_min_height_above_rim_m": 0.45,
        "dump_ready_require_over_footprint": True,
        "dump_ready_require_clearance": True,
        "dump_ready_max_horizontal_distance_m": 0.60,
        "dump_ready_position_mode": "footprint_or_dump_area_relative",
        "dump_ready_max_dump_area_footprint_outside_distance_m": 0.05,
        "dump_ready_min_dump_area_relative_x_m": None,
        "dump_ready_max_dump_area_relative_x_m": None,
        "dump_ready_min_dump_area_relative_z_m": None,
        "dump_ready_max_dump_area_relative_z_m": None,
        "dump_ready_near_window_enabled": False,
        "dump_ready_near_window_x_tolerance_m": 0.05,
        "dump_ready_near_window_z_tolerance_m": 0.05,
        "dump_ready_near_window_outside_tolerance_m": 0.0,
        "dump_ready_near_window_require_over_footprint": True,
        "dump_done_max_bucket_mass_kg": 100.0,
        "dump_done_min_deposit_delta_kg": 10.0,
        "approach_ready_min_bucket_mass_kg": 150.0,
        "approach_ready_max_horizontal_distance_m": 1.25,
        "approach_ready_min_height_above_rim_m": -0.20,
        "approach_ready_require_clearance": True,
    }
    values.update(overrides)
    return DumpLifecycleConfig(**values)


def _facts(**overrides: object) -> DumpLifecycleFacts:
    values = {
        "mass_in_bucket_kg": 320.0,
        "deposited_mass_kg": 25.0,
        "target_geometry": {
            "target_horizontal_distance_m": 0.15,
            "bucket_height_above_target_rim_m": 0.50,
            "bucket_over_target_footprint_mask": 1.0,
            "dump_clearance_ok_mask": 1.0,
            "bucket_dump_area_relative_x_m": 0.60,
            "bucket_dump_area_relative_z_m": 1.20,
            "bucket_dump_area_footprint_outside_distance_m": 0.0,
        },
        "semantic_boundary_profile_active": False,
        "coverage_cycle_start_deposit_kg": 0.0,
    }
    values.update(overrides)
    return DumpLifecycleFacts(**values)


def _event(**flags: bool) -> object:
    return type("_BoundaryEvent", (), flags)()
