from __future__ import annotations

import math

from testbed.planner.dig_lifecycle import (
    DigLifecycleConfig,
    DigLifecycleFacts,
    DigLifecycleGateService,
)


def _config(**overrides: object) -> DigLifecycleConfig:
    values = {
        "dig_to_carry_min_bucket_mass_kg": 20.0,
        "dig_to_carry_min_distance_to_dig_area_m": 0.0,
        "dig_to_carry_target_bucket_mass_kg": 20.0,
        "dig_to_carry_mass_plateau_enabled": False,
        "dig_to_carry_mass_plateau_min_bucket_mass_kg": 25.0,
        "dig_to_carry_mass_plateau_epsilon_kg": 1.0,
        "dig_to_carry_mass_plateau_hold_steps": 3,
        "dig_to_carry_mass_plateau_min_steps": 5,
        "dig_bad_replan_enabled": False,
        "dig_bad_replan_max_steps": 5,
        "dig_bad_replan_min_bucket_mass_kg": 15.0,
        "dig_exit_guard_enabled": False,
        "dig_exit_guard_min_steps": 3,
        "dig_exit_guard_overshoot_m": 0.20,
        "dig_exit_guard_min_bucket_mass_kg": 20.0,
        "dump_ready_min_bucket_mass_kg": 15.0,
    }
    values.update(overrides)
    return DigLifecycleConfig(**values)


def _facts(**overrides: object) -> DigLifecycleFacts:
    values = {
        "mass_in_bucket_kg": 0.0,
        "min_distance_to_dig_area_m": 0.0,
        "carry_mass_in_bucket_kg": 0.0,
        "carry_min_distance_to_dig_area_m": 0.0,
        "semantic_boundary_profile_active": False,
        "boundary_dig_complete": False,
        "coverage_terminal_stop_requested": False,
        "dig_step_count": 0,
        "dig_best_mass_kg": 0.0,
        "dig_mass_plateau_count": 0,
        "coverage_current_payload_gain_kg": 0.0,
        "active_corridor_entry_xz": None,
        "active_corridor_exit_xz": None,
        "bucket_tip_xz": None,
    }
    values.update(overrides)
    return DigLifecycleFacts(**values)


def test_update_progress_tracks_best_mass_plateau_and_payload_gain() -> None:
    service = DigLifecycleGateService()
    config = _config(dig_to_carry_mass_plateau_epsilon_kg=1.0)

    plateau = service.update_progress(
        _facts(
            mass_in_bucket_kg=21.0,
            dig_step_count=7,
            dig_best_mass_kg=20.0,
            dig_mass_plateau_count=2,
            coverage_current_payload_gain_kg=18.0,
        ),
        config,
    )
    assert plateau.step_count == 8
    assert plateau.best_mass_kg == 21.0
    assert plateau.mass_plateau_count == 3
    assert plateau.coverage_payload_gain_kg == 21.0

    improved = service.update_progress(
        _facts(
            mass_in_bucket_kg=22.1,
            dig_step_count=8,
            dig_best_mass_kg=20.0,
            dig_mass_plateau_count=3,
            coverage_current_payload_gain_kg=30.0,
        ),
        config,
    )
    assert improved.step_count == 9
    assert improved.best_mass_kg == 22.1
    assert improved.mass_plateau_count == 0
    assert improved.coverage_payload_gain_kg == 30.0


def test_bad_dig_gate_requires_enabled_elapsed_and_low_current_mass() -> None:
    service = DigLifecycleGateService()
    enabled = _config(dig_bad_replan_enabled=True)

    assert not service.bad_replan_ready(
        _facts(mass_in_bucket_kg=0.0, dig_step_count=5),
        _config(dig_bad_replan_enabled=False),
    )
    assert not service.bad_replan_ready(
        _facts(mass_in_bucket_kg=0.0, dig_step_count=4),
        enabled,
    )
    assert not service.bad_replan_ready(
        _facts(mass_in_bucket_kg=20.0, dig_step_count=5),
        enabled,
    )
    assert not service.bad_replan_ready(
        _facts(
            mass_in_bucket_kg=0.0,
            dig_step_count=5,
            coverage_terminal_stop_requested=True,
        ),
        enabled,
    )
    assert service.bad_replan_ready(
        _facts(mass_in_bucket_kg=0.0, dig_step_count=5),
        enabled,
    )


def test_exit_guard_requires_overshoot_low_payload_and_active_corridor() -> None:
    service = DigLifecycleGateService()
    config = _config(dig_exit_guard_enabled=True)

    missing = _facts(mass_in_bucket_kg=5.0, dig_step_count=3)
    assert math.isnan(service.exit_overshoot_m(missing))
    assert not service.exit_guard_ready(missing, config)

    ready = _facts(
        mass_in_bucket_kg=5.0,
        dig_step_count=3,
        active_corridor_entry_xz=(0.0, 0.0),
        active_corridor_exit_xz=(-1.0, 0.0),
        bucket_tip_xz=(-1.25, 0.0),
    )
    assert service.exit_overshoot_m(ready) == 0.25
    assert service.exit_guard_ready(ready, config)
    assert not service.exit_guard_ready(
        _facts(
            mass_in_bucket_kg=25.0,
            dig_step_count=3,
            active_corridor_entry_xz=(0.0, 0.0),
            active_corridor_exit_xz=(-1.0, 0.0),
            bucket_tip_xz=(-1.25, 0.0),
        ),
        config,
    )


def test_dig_to_carry_reason_preserves_loaded_boundary_plateau_variants() -> None:
    service = DigLifecycleGateService()
    assert service.dig_to_carry_ready(
        _facts(boundary_dig_complete=True),
        _config(dig_to_carry_target_bucket_mass_kg=45.0),
    ).reason == "dig_complete_boundary"
    assert service.dig_to_carry_ready(
        _facts(carry_mass_in_bucket_kg=20.0),
        _config(dig_to_carry_target_bucket_mass_kg=20.0),
    ).reason == "loaded"
    assert service.dig_to_carry_ready(
        _facts(carry_mass_in_bucket_kg=45.0),
        _config(dig_to_carry_target_bucket_mass_kg=45.0),
    ).reason == "target_payload_loaded"
    assert service.dig_to_carry_ready(
        _facts(
            carry_mass_in_bucket_kg=25.0,
            dig_step_count=5,
            dig_mass_plateau_count=3,
        ),
        _config(
            dig_to_carry_target_bucket_mass_kg=45.0,
            dig_to_carry_mass_plateau_enabled=True,
        ),
    ).reason == "mass_plateau"
    assert service.dig_to_carry_ready(
        _facts(
            carry_mass_in_bucket_kg=45.0,
            semantic_boundary_profile_active=True,
        ),
        _config(dig_to_carry_target_bucket_mass_kg=45.0),
    ).reason == "semantic_material_loaded"
    assert service.dig_to_carry_ready(
        _facts(
            carry_mass_in_bucket_kg=25.0,
            semantic_boundary_profile_active=True,
            dig_step_count=5,
            dig_mass_plateau_count=3,
        ),
        _config(
            dig_to_carry_target_bucket_mass_kg=45.0,
            dig_to_carry_mass_plateau_enabled=True,
        ),
    ).reason == "semantic_material_plateau"


def test_dig_complete_low_payload_uses_semantic_boundary_and_min_carry_mass() -> None:
    service = DigLifecycleGateService()
    config = _config(
        dig_to_carry_min_bucket_mass_kg=15.0,
        dump_ready_min_bucket_mass_kg=20.0,
    )
    assert service.complete_boundary_low_payload(
        _facts(
            mass_in_bucket_kg=19.0,
            semantic_boundary_profile_active=True,
            boundary_dig_complete=True,
        ),
        config,
    )
    assert not service.complete_boundary_low_payload(
        _facts(
            mass_in_bucket_kg=20.0,
            semantic_boundary_profile_active=True,
            boundary_dig_complete=True,
        ),
        config,
    )
    assert not service.complete_boundary_low_payload(
        _facts(
            mass_in_bucket_kg=0.0,
            semantic_boundary_profile_active=False,
            boundary_dig_complete=True,
        ),
        config,
    )
