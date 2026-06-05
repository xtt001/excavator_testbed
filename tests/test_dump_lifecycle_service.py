from __future__ import annotations

import pytest

from testbed.planner.dump_lifecycle import (
    DumpLifecycleConfig,
    DumpLifecycleFacts,
    DumpLifecycleGateService,
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


def _geometry(**overrides: float) -> dict[str, float]:
    values = {
        "target_horizontal_distance_m": 0.15,
        "bucket_height_above_target_rim_m": 0.50,
        "bucket_over_target_footprint_mask": 1.0,
        "dump_clearance_ok_mask": 1.0,
        "bucket_dump_area_relative_x_m": 0.60,
        "bucket_dump_area_relative_z_m": 1.20,
        "bucket_dump_area_footprint_outside_distance_m": 0.0,
    }
    values.update(overrides)
    return values


def _facts(**overrides: object) -> DumpLifecycleFacts:
    values = {
        "mass_in_bucket_kg": 320.0,
        "deposited_mass_kg": 0.0,
        "target_geometry": _geometry(),
        "semantic_boundary_profile_active": False,
        "coverage_cycle_start_deposit_kg": 0.0,
    }
    values.update(overrides)
    return DumpLifecycleFacts(**values)


def test_dump_ready_respects_position_mode_when_footprint_is_relaxed() -> None:
    service = DumpLifecycleGateService()
    config = _config(
        dump_ready_require_over_footprint=False,
        dump_ready_require_clearance=False,
        dump_ready_position_mode="dump_area_relative",
        dump_ready_max_horizontal_distance_m=None,
        dump_ready_max_dump_area_footprint_outside_distance_m=0.45,
        dump_ready_min_dump_area_relative_x_m=0.0,
        dump_ready_max_dump_area_relative_x_m=1.2,
        dump_ready_min_dump_area_relative_z_m=1.0,
        dump_ready_max_dump_area_relative_z_m=1.8,
    )
    assert not service.dump_ready(
        _facts(
            target_geometry=_geometry(
                bucket_over_target_footprint_mask=0.0,
                bucket_dump_area_relative_x_m=1.35,
                bucket_dump_area_relative_z_m=1.20,
            )
        ),
        config,
    )
    assert service.dump_ready(_facts(), config)


def test_near_window_uses_tolerance_and_required_footprint() -> None:
    service = DumpLifecycleGateService()
    config = _config(
        dump_ready_require_over_footprint=False,
        dump_ready_require_clearance=False,
        dump_ready_position_mode="dump_area_relative",
        dump_ready_max_horizontal_distance_m=None,
        dump_ready_max_dump_area_footprint_outside_distance_m=0.45,
        dump_ready_min_dump_area_relative_x_m=0.0,
        dump_ready_max_dump_area_relative_x_m=1.2,
        dump_ready_min_dump_area_relative_z_m=1.0,
        dump_ready_max_dump_area_relative_z_m=1.8,
        dump_ready_near_window_enabled=True,
        dump_ready_near_window_x_tolerance_m=0.05,
        dump_ready_near_window_z_tolerance_m=0.05,
        dump_ready_near_window_require_over_footprint=True,
    )
    near = _facts(
        target_geometry=_geometry(
            bucket_over_target_footprint_mask=1.0,
            bucket_dump_area_relative_x_m=1.202,
            bucket_dump_area_relative_z_m=0.982,
        )
    )
    no_footprint = _facts(
        target_geometry=_geometry(
            bucket_over_target_footprint_mask=0.0,
            bucket_dump_area_relative_x_m=1.202,
            bucket_dump_area_relative_z_m=0.982,
        )
    )
    assert service.dump_ready(near, config)
    assert not service.dump_ready(no_footprint, config)


def test_dump_done_and_carry_release_safety_use_same_mass_deposit_gate() -> None:
    service = DumpLifecycleGateService()
    config = _config(
        dump_done_max_bucket_mass_kg=100.0,
        dump_done_min_deposit_delta_kg=10.0,
    )
    facts = _facts(
        mass_in_bucket_kg=50.0,
        deposited_mass_kg=25.0,
        semantic_boundary_profile_active=True,
        coverage_cycle_start_deposit_kg=12.0,
    )
    assert service.dump_done(facts, config, dump_start_deposited_mass_kg=12.0)
    assert service.carry_release_safety_done(facts, config)
    assert not service.carry_release_safety_done(
        _facts(
            mass_in_bucket_kg=50.0,
            deposited_mass_kg=25.0,
            semantic_boundary_profile_active=False,
            coverage_cycle_start_deposit_kg=12.0,
        ),
        config,
    )


def test_approach_ready_checks_mass_distance_height_and_clearance() -> None:
    service = DumpLifecycleGateService()
    config = _config(
        approach_ready_min_bucket_mass_kg=150.0,
        approach_ready_max_horizontal_distance_m=1.25,
        approach_ready_min_height_above_rim_m=-0.20,
        approach_ready_require_clearance=True,
    )
    assert service.approach_ready(
        _facts(
            target_geometry=_geometry(
                target_horizontal_distance_m=1.20,
                bucket_height_above_target_rim_m=0.0,
            )
        ),
        config,
    )
    assert not service.approach_ready(
        _facts(
            target_geometry=_geometry(
                target_horizontal_distance_m=1.40,
                bucket_height_above_target_rim_m=0.0,
            )
        ),
        config,
    )


def test_invalid_dump_ready_position_mode_raises() -> None:
    service = DumpLifecycleGateService()
    with pytest.raises(ValueError, match="Unsupported dump_ready_position_mode"):
        service.dump_ready_position_ok(
            over_footprint=False,
            dump_area_relative_ok=False,
            horizontal_ok=False,
            config=_config(dump_ready_position_mode="bad_mode"),
        )
