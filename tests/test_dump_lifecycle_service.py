from __future__ import annotations

import numpy as np
import pytest

from testbed.data.schema import (
    ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
    ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_DUMP_CLEARANCE_OK_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
)
from testbed.planner import dump_lifecycle as dump_lifecycle_module
from testbed.planner import dump_lifecycle_transition as dump_transition_module
from testbed.planner.dump_lifecycle import (
    DUMP_LIFECYCLE_FACT_FIELDS,
    DUMP_LIFECYCLE_RUNTIME_STATUS_FIELDS,
    CarryTransitionRuntimeRequestFacts,
    DumpLifecycleConfig,
    DumpLifecycleFacts,
    DumpLifecycleGateService,
    DumpLifecycleRuntimeState,
    DumpLifecycleRuntimeStatusState,
    DumpTransitionRuntimeRequestFacts,
    build_dump_lifecycle_config,
    build_dump_lifecycle_facts,
    build_dump_lifecycle_facts_from_mapping,
    build_dump_lifecycle_facts_from_observation_view,
    build_dump_lifecycle_runtime_config,
    build_dump_lifecycle_runtime_config_from_mapping,
    build_dump_lifecycle_runtime_status_state_from_mapping,
)
from testbed.planner.dump_lifecycle_transition import (
    CarryTransitionRuntimeFacts,
    DumpTransitionRuntimeFacts,
    build_carry_transition_runtime_request,
    build_dump_transition_runtime_request,
)
from testbed.planner.snapshots import (
    build_planner_snapshot,
    target_geometry_from_obs,
)


def test_dump_lifecycle_reexports_transition_runtime_symbols_for_compatibility() -> None:
    assert (
        dump_lifecycle_module.CarryTransitionRuntimeFacts
        is dump_transition_module.CarryTransitionRuntimeFacts
    )
    assert (
        dump_lifecycle_module.CarryTransitionRuntimeRequestFacts
        is dump_transition_module.CarryTransitionRuntimeRequestFacts
    )
    assert (
        dump_lifecycle_module.DumpTransitionRuntimeFacts
        is dump_transition_module.DumpTransitionRuntimeFacts
    )
    assert (
        dump_lifecycle_module.DumpTransitionRuntimeRequestFacts
        is dump_transition_module.DumpTransitionRuntimeRequestFacts
    )
    assert (
        dump_lifecycle_module.build_carry_transition_runtime_request
        is dump_transition_module.build_carry_transition_runtime_request
    )
    assert (
        dump_lifecycle_module.build_dump_transition_runtime_request
        is dump_transition_module.build_dump_transition_runtime_request
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


def _event(**flags: bool) -> object:
    return type("_BoundaryEvent", (), flags)()


def test_build_dump_lifecycle_facts_projects_inputs_without_copying_geometry() -> None:
    geometry = _geometry(target_horizontal_distance_m=0.42)

    facts = build_dump_lifecycle_facts(
        mass_in_bucket_kg="12.5",
        deposited_mass_kg=3,
        target_geometry=geometry,
        semantic_boundary_profile_active=1,
        coverage_cycle_start_deposit_kg="2.25",
    )

    assert facts.mass_in_bucket_kg == pytest.approx(12.5)
    assert facts.deposited_mass_kg == pytest.approx(3.0)
    assert facts.target_geometry is geometry
    assert facts.semantic_boundary_profile_active is True
    assert facts.coverage_cycle_start_deposit_kg == pytest.approx(2.25)


def test_build_dump_lifecycle_facts_from_mapping_preserves_projection() -> None:
    geometry = _geometry(target_horizontal_distance_m=0.42)
    values = {
        "mass_in_bucket_kg": "12.5",
        "deposited_mass_kg": 3,
        "target_geometry": geometry,
        "semantic_boundary_profile_active": 1,
        "coverage_cycle_start_deposit_kg": "2.25",
        "ignored": object(),
    }

    facts = build_dump_lifecycle_facts_from_mapping(values)

    assert set(DUMP_LIFECYCLE_FACT_FIELDS) == set(values) - {"ignored"}
    assert facts == build_dump_lifecycle_facts(
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
    assert facts.target_geometry is geometry


def test_build_dump_lifecycle_facts_from_observation_view_preserves_sources() -> None:
    obs = {
        "env_state": np.zeros(0, dtype=np.float32),
        "task_metrics": {
            "mass_in_bucket_kg": "12.5",
            "deposited_mass_in_target_box_kg": 8.0,
            "target_geometry_available": 1.0,
            "target_horizontal_distance_m": 0.42,
            "bucket_height_above_target_rim_m": 0.70,
            "bucket_over_target_footprint_mask": 1.0,
            "dump_clearance_ok_mask": 1.0,
            "bucket_dump_area_relative_x_m": 0.30,
            "bucket_dump_area_relative_z_m": 1.10,
            "bucket_dump_area_footprint_outside_distance_m": 0.02,
        },
    }
    snapshot = build_planner_snapshot(
        obs,
        active_skill="carry",
        cycle_index=2,
        prev_action=None,
        boundary_event=None,
        action_dim=4,
    )

    facts = DumpLifecycleGateService.facts_from_observation_view(
        view=snapshot.view,
        semantic_boundary_profile_active=True,
        coverage_cycle_start_deposit_kg="3.25",
    )

    assert facts == build_dump_lifecycle_facts_from_observation_view(
        view=snapshot.view,
        semantic_boundary_profile_active=True,
        coverage_cycle_start_deposit_kg="3.25",
    )
    assert facts.mass_in_bucket_kg == pytest.approx(12.5)
    assert facts.deposited_mass_kg == pytest.approx(8.0)
    assert facts.target_geometry == target_geometry_from_obs(obs)
    assert facts.semantic_boundary_profile_active is True
    assert facts.coverage_cycle_start_deposit_kg == pytest.approx(3.25)


def test_dump_lifecycle_facts_from_observation_view_preserves_env_fallbacks() -> None:
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_MASS_IN_BUCKET_IDX] = 9.5
    env_state[ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX] = 4.25
    env_state[ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX] = 0.52
    env_state[ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX] = 0.61
    env_state[ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX] = 1.0
    env_state[ENV_STATE_DUMP_CLEARANCE_OK_IDX] = 1.0
    env_state[ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX] = 0.44
    env_state[ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX] = 1.25
    env_state[ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX] = 0.03
    obs = {"env_state": env_state}
    snapshot = build_planner_snapshot(
        obs,
        active_skill="carry",
        cycle_index=2,
        prev_action=None,
        boundary_event=None,
        action_dim=4,
    )

    facts = DumpLifecycleGateService.facts_from_observation_view(
        view=snapshot.view,
        semantic_boundary_profile_active=False,
        coverage_cycle_start_deposit_kg=1.5,
    )

    assert facts.mass_in_bucket_kg == pytest.approx(9.5)
    assert facts.deposited_mass_kg == pytest.approx(4.25)
    assert facts.target_geometry == target_geometry_from_obs(obs)
    assert facts.semantic_boundary_profile_active is False
    assert facts.coverage_cycle_start_deposit_kg == pytest.approx(1.5)


def test_build_dump_lifecycle_config_preserves_legacy_defaults() -> None:
    config = build_dump_lifecycle_config(
        dump_ready_min_bucket_mass_kg=150.0,
        dump_ready_min_height_above_rim_m=0.45,
        dump_ready_require_over_footprint=True,
        dump_ready_require_clearance=True,
        dump_ready_max_horizontal_distance_m=0.60,
        dump_ready_position_mode="footprint_or_dump_area_relative",
        dump_ready_max_dump_area_footprint_outside_distance_m=0.05,
        dump_ready_min_dump_area_relative_x_m=None,
        dump_ready_max_dump_area_relative_x_m=None,
        dump_ready_min_dump_area_relative_z_m=None,
        dump_ready_max_dump_area_relative_z_m=None,
        dump_ready_hold_steps=3,
        dump_ready_near_window_enabled=False,
        dump_ready_near_window_x_tolerance_m=0.05,
        dump_ready_near_window_z_tolerance_m=0.05,
        dump_ready_near_window_outside_tolerance_m=0.0,
        dump_ready_near_window_require_over_footprint=True,
        dump_done_max_bucket_mass_kg=100.0,
        dump_done_min_deposit_delta_kg=10.0,
        dump_done_hold_steps=2,
        dump_done_use_boundary_event=True,
    )

    assert config.dump_ready_min_bucket_mass_kg == pytest.approx(150.0)
    assert config.dump_ready_min_height_above_rim_m == pytest.approx(0.45)
    assert config.dump_ready_require_over_footprint is True
    assert config.dump_ready_require_clearance is True
    assert config.dump_ready_max_horizontal_distance_m == pytest.approx(0.60)
    assert config.dump_ready_position_mode == "footprint_or_dump_area_relative"
    assert (
        config.dump_ready_max_dump_area_footprint_outside_distance_m
        == pytest.approx(0.05)
    )
    assert config.dump_ready_min_dump_area_relative_x_m is None
    assert config.dump_ready_max_dump_area_relative_x_m is None
    assert config.dump_ready_min_dump_area_relative_z_m is None
    assert config.dump_ready_max_dump_area_relative_z_m is None
    assert config.dump_ready_hold_steps == 3
    assert config.dump_ready_near_window_enabled is False
    assert config.dump_ready_near_window_x_tolerance_m == pytest.approx(0.05)
    assert config.dump_ready_near_window_z_tolerance_m == pytest.approx(0.05)
    assert config.dump_ready_near_window_outside_tolerance_m == pytest.approx(0.0)
    assert config.dump_ready_near_window_require_over_footprint is True
    assert config.dump_done_max_bucket_mass_kg == pytest.approx(100.0)
    assert config.dump_done_min_deposit_delta_kg == pytest.approx(10.0)
    assert config.dump_done_hold_steps == 2
    assert config.dump_done_use_boundary_event is True


def test_build_dump_lifecycle_config_preserves_overrides_and_coercion() -> None:
    config = build_dump_lifecycle_config(
        dump_ready_min_bucket_mass_kg=12,
        dump_ready_min_height_above_rim_m=-0.1,
        dump_ready_require_over_footprint=False,
        dump_ready_require_clearance=False,
        dump_ready_max_horizontal_distance_m=None,
        dump_ready_position_mode="dump_area_relative",
        dump_ready_max_dump_area_footprint_outside_distance_m=0.3,
        dump_ready_min_dump_area_relative_x_m=-0.2,
        dump_ready_max_dump_area_relative_x_m=0.4,
        dump_ready_min_dump_area_relative_z_m="0.5",
        dump_ready_max_dump_area_relative_z_m="1.5",
        dump_ready_hold_steps=0,
        dump_ready_near_window_enabled=True,
        dump_ready_near_window_x_tolerance_m=0.03,
        dump_ready_near_window_z_tolerance_m=0.04,
        dump_ready_near_window_outside_tolerance_m=0.02,
        dump_ready_near_window_require_over_footprint=False,
        dump_done_max_bucket_mass_kg=8,
        dump_done_min_deposit_delta_kg=2.5,
        dump_done_hold_steps=0,
        dump_done_use_boundary_event=False,
    )

    assert config.dump_ready_min_bucket_mass_kg == pytest.approx(12.0)
    assert config.dump_ready_min_height_above_rim_m == pytest.approx(-0.1)
    assert config.dump_ready_require_over_footprint is False
    assert config.dump_ready_require_clearance is False
    assert config.dump_ready_max_horizontal_distance_m is None
    assert config.dump_ready_position_mode == "dump_area_relative"
    assert (
        config.dump_ready_max_dump_area_footprint_outside_distance_m
        == pytest.approx(0.3)
    )
    assert config.dump_ready_min_dump_area_relative_x_m == pytest.approx(-0.2)
    assert config.dump_ready_max_dump_area_relative_x_m == pytest.approx(0.4)
    assert config.dump_ready_min_dump_area_relative_z_m == pytest.approx(0.5)
    assert config.dump_ready_max_dump_area_relative_z_m == pytest.approx(1.5)
    assert config.dump_ready_hold_steps == 1
    assert config.dump_ready_near_window_enabled is True
    assert config.dump_ready_near_window_x_tolerance_m == pytest.approx(0.03)
    assert config.dump_ready_near_window_z_tolerance_m == pytest.approx(0.04)
    assert config.dump_ready_near_window_outside_tolerance_m == pytest.approx(0.02)
    assert config.dump_ready_near_window_require_over_footprint is False
    assert config.dump_done_max_bucket_mass_kg == pytest.approx(8.0)
    assert config.dump_done_min_deposit_delta_kg == pytest.approx(2.5)
    assert config.dump_done_hold_steps == 1
    assert config.dump_done_use_boundary_event is False


def test_build_dump_lifecycle_runtime_config_projects_gate_and_approach_fields() -> None:
    config = build_dump_lifecycle_runtime_config(
        dump_ready_min_bucket_mass_kg="12.5",
        dump_ready_min_height_above_rim_m="-0.1",
        dump_ready_require_over_footprint=0,
        dump_ready_require_clearance=1,
        dump_ready_max_horizontal_distance_m=None,
        dump_ready_position_mode="dump_area_relative",
        dump_ready_max_dump_area_footprint_outside_distance_m="0.30",
        dump_ready_min_dump_area_relative_x_m="-0.2",
        dump_ready_max_dump_area_relative_x_m="0.4",
        dump_ready_min_dump_area_relative_z_m=None,
        dump_ready_max_dump_area_relative_z_m="1.5",
        dump_ready_near_window_enabled=1,
        dump_ready_near_window_x_tolerance_m="0.03",
        dump_ready_near_window_z_tolerance_m="0.04",
        dump_ready_near_window_outside_tolerance_m="0.02",
        dump_ready_near_window_require_over_footprint=0,
        dump_done_max_bucket_mass_kg="8.0",
        dump_done_min_deposit_delta_kg="2.5",
        approach_ready_min_bucket_mass_kg="7.0",
        approach_ready_max_horizontal_distance_m="1.25",
        approach_ready_min_height_above_rim_m="-0.20",
        approach_ready_require_clearance=0,
    )

    assert config == DumpLifecycleConfig(
        dump_ready_min_bucket_mass_kg=12.5,
        dump_ready_min_height_above_rim_m=-0.1,
        dump_ready_require_over_footprint=False,
        dump_ready_require_clearance=True,
        dump_ready_max_horizontal_distance_m=None,
        dump_ready_position_mode="dump_area_relative",
        dump_ready_max_dump_area_footprint_outside_distance_m=0.30,
        dump_ready_min_dump_area_relative_x_m=-0.2,
        dump_ready_max_dump_area_relative_x_m=0.4,
        dump_ready_min_dump_area_relative_z_m=None,
        dump_ready_max_dump_area_relative_z_m=1.5,
        dump_ready_near_window_enabled=True,
        dump_ready_near_window_x_tolerance_m=0.03,
        dump_ready_near_window_z_tolerance_m=0.04,
        dump_ready_near_window_outside_tolerance_m=0.02,
        dump_ready_near_window_require_over_footprint=False,
        dump_done_max_bucket_mass_kg=8.0,
        dump_done_min_deposit_delta_kg=2.5,
        approach_ready_min_bucket_mass_kg=7.0,
        approach_ready_max_horizontal_distance_m=1.25,
        approach_ready_min_height_above_rim_m=-0.20,
        approach_ready_require_clearance=False,
    )


def test_build_dump_lifecycle_runtime_config_from_mapping_preserves_fallbacks() -> None:
    config = build_dump_lifecycle_runtime_config_from_mapping(
        {
            "dump_ready_min_bucket_mass_kg": "150.0",
            "dump_ready_min_height_above_rim_m": "0.45",
            "dump_ready_require_over_footprint": 1,
            "dump_ready_require_clearance": 0,
            "dump_ready_max_horizontal_distance_m": None,
            "dump_ready_position_mode": "footprint_or_dump_area_relative",
            "dump_ready_max_dump_area_footprint_outside_distance_m": "0.12",
            "dump_ready_min_dump_area_relative_x_m": "-0.4",
            "dump_ready_max_dump_area_relative_x_m": "0.6",
            "dump_ready_min_dump_area_relative_z_m": None,
            "dump_ready_max_dump_area_relative_z_m": "0.8",
            "dump_ready_near_window_enabled": 1,
            "dump_ready_near_window_x_tolerance_m": "0.2",
            "dump_ready_near_window_z_tolerance_m": "0.3",
            "dump_ready_near_window_outside_tolerance_m": "0.4",
            "dump_ready_near_window_require_over_footprint": 0,
            "dump_done_max_bucket_mass_kg": "20.0",
            "dump_done_min_deposit_delta_kg": "12.0",
        }
    )

    assert config == DumpLifecycleConfig(
        dump_ready_min_bucket_mass_kg=150.0,
        dump_ready_min_height_above_rim_m=0.45,
        dump_ready_require_over_footprint=True,
        dump_ready_require_clearance=False,
        dump_ready_max_horizontal_distance_m=None,
        dump_ready_position_mode="footprint_or_dump_area_relative",
        dump_ready_max_dump_area_footprint_outside_distance_m=0.12,
        dump_ready_min_dump_area_relative_x_m=-0.4,
        dump_ready_max_dump_area_relative_x_m=0.6,
        dump_ready_min_dump_area_relative_z_m=None,
        dump_ready_max_dump_area_relative_z_m=0.8,
        dump_ready_near_window_enabled=True,
        dump_ready_near_window_x_tolerance_m=0.2,
        dump_ready_near_window_z_tolerance_m=0.3,
        dump_ready_near_window_outside_tolerance_m=0.4,
        dump_ready_near_window_require_over_footprint=False,
        dump_done_max_bucket_mass_kg=20.0,
        dump_done_min_deposit_delta_kg=12.0,
        approach_ready_min_bucket_mass_kg=0.0,
        approach_ready_max_horizontal_distance_m=None,
        approach_ready_min_height_above_rim_m=0.0,
        approach_ready_require_clearance=True,
    )


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


def test_initial_runtime_state_preserves_legacy_reset_defaults() -> None:
    state = DumpLifecycleGateService.initial_runtime_state()

    assert isinstance(state, DumpLifecycleRuntimeState)
    assert state.ready_hold_count == 0
    assert state.done_hold_count == 0
    assert state.start_deposited_mass_kg == 0.0


def test_runtime_status_snapshot_projects_hold_counts() -> None:
    snapshot = DumpLifecycleGateService.runtime_status_snapshot(
        DumpLifecycleRuntimeStatusState(
            ready_hold_count=4,
            done_hold_count=2,
        )
    )

    assert snapshot.ready_hold_count == 4
    assert snapshot.done_hold_count == 2


def test_runtime_status_state_mapping_preserves_projection() -> None:
    values = {
        "ready_hold_count": "4",
        "done_hold_count": 2.0,
        "ignored": object(),
    }

    state = build_dump_lifecycle_runtime_status_state_from_mapping(values)

    assert {key for key, _ in DUMP_LIFECYCLE_RUNTIME_STATUS_FIELDS} == (
        set(values) - {"ignored"}
    )
    assert state == DumpLifecycleRuntimeStatusState(
        ready_hold_count=4,
        done_hold_count=2,
    )


def test_carry_outcome_preserves_return_and_dump_reasons() -> None:
    release = DumpLifecycleGateService.carry_outcome(
        release_safety_done=True,
        dump_complete_event=True,
        dump_committed_event=True,
        release_onset_event=True,
        legacy_dump_start_event=True,
        dump_ready_hold_ready=True,
    )
    assert release.action == "return"
    assert release.coverage_reason == "carry_release_safety"
    assert release.switch_reason == "carry_to_return_release_safety"

    dump_complete = DumpLifecycleGateService.carry_outcome(
        release_safety_done=False,
        dump_complete_event=True,
        dump_committed_event=True,
        release_onset_event=False,
        legacy_dump_start_event=False,
        dump_ready_hold_ready=True,
    )
    assert dump_complete.action == "return"
    assert dump_complete.coverage_reason == "carry_dump_complete_boundary"
    assert dump_complete.switch_reason == "carry_to_return_dump_complete_boundary"

    committed = DumpLifecycleGateService.carry_outcome(
        release_safety_done=False,
        dump_complete_event=False,
        dump_committed_event=True,
        release_onset_event=False,
        legacy_dump_start_event=False,
        dump_ready_hold_ready=True,
    )
    assert committed.action == "dump"
    assert committed.switch_reason == "carry_to_dump_dump_committed_boundary"

    release_onset = DumpLifecycleGateService.carry_outcome(
        release_safety_done=False,
        dump_complete_event=False,
        dump_committed_event=False,
        release_onset_event=True,
        legacy_dump_start_event=False,
        dump_ready_hold_ready=True,
    )
    assert release_onset.switch_reason == "carry_to_dump_release_onset_boundary"

    legacy_start = DumpLifecycleGateService.carry_outcome(
        release_safety_done=False,
        dump_complete_event=False,
        dump_committed_event=False,
        release_onset_event=False,
        legacy_dump_start_event=True,
        dump_ready_hold_ready=True,
    )
    assert legacy_start.switch_reason == "carry_to_dump_dump_start_boundary"

    target_ready = DumpLifecycleGateService.carry_outcome(
        release_safety_done=False,
        dump_complete_event=False,
        dump_committed_event=False,
        release_onset_event=False,
        legacy_dump_start_event=False,
        dump_ready_hold_ready=True,
    )
    assert target_ready.switch_reason == "carry_to_dump_target_ready"


def test_carry_transition_runtime_updates_hold_count_and_outcome() -> None:
    service = DumpLifecycleGateService()

    event_ready = service.carry_transition_runtime(
        CarryTransitionRuntimeFacts(
            release_safety_done=False,
            dump_complete_event=False,
            dump_committed_event=True,
            release_onset_event=False,
            legacy_dump_start_event=False,
            dump_ready=False,
            current_dump_ready_hold_count=0,
        ),
        dump_ready_hold_steps=2,
    )
    assert event_ready.dump_ready_hold_count == 2
    assert event_ready.outcome.action == "dump"
    assert event_ready.outcome.switch_reason == "carry_to_dump_dump_committed_boundary"

    target_ready = service.carry_transition_runtime(
        CarryTransitionRuntimeFacts(
            release_safety_done=False,
            dump_complete_event=False,
            dump_committed_event=False,
            release_onset_event=False,
            legacy_dump_start_event=False,
            dump_ready=True,
            current_dump_ready_hold_count=1,
        ),
        dump_ready_hold_steps=2,
    )
    assert target_ready.dump_ready_hold_count == 2
    assert target_ready.outcome.switch_reason == "carry_to_dump_target_ready"

    reset = service.carry_transition_runtime(
        CarryTransitionRuntimeFacts(
            release_safety_done=False,
            dump_complete_event=False,
            dump_committed_event=False,
            release_onset_event=False,
            legacy_dump_start_event=False,
            dump_ready=False,
            current_dump_ready_hold_count=1,
        ),
        dump_ready_hold_steps=2,
    )
    assert reset.dump_ready_hold_count == 0
    assert reset.outcome.action == "none"


def test_carry_transition_request_preserves_boundary_priority_and_legacy_gate() -> None:
    service = DumpLifecycleGateService()
    release = build_carry_transition_runtime_request(
        release_safety_done=True,
        boundary_event=_event(
            dump_committed_start=True,
            release_onset=True,
            dump_complete=True,
            dump_start=True,
        ),
        semantic_boundary_profile_active=False,
        current_dump_ready_hold_count=3,
    )
    assert release == service.carry_transition_runtime_request(
        CarryTransitionRuntimeRequestFacts(
            release_safety_done=True,
            boundary_event=_event(
                dump_committed_start=True,
                release_onset=True,
                dump_complete=True,
                dump_start=True,
            ),
            semantic_boundary_profile_active=False,
            current_dump_ready_hold_count=3,
        )
    )
    assert release.should_check_dump_ready is False
    assert release.facts.release_safety_done is True
    assert release.facts.dump_committed_event is False
    assert release.facts.release_onset_event is False
    assert release.facts.dump_complete_event is False
    assert release.facts.legacy_dump_start_event is False
    assert release.facts.current_dump_ready_hold_count == 3

    legacy_start = build_carry_transition_runtime_request(
        release_safety_done=False,
        boundary_event=_event(dump_start=True),
        semantic_boundary_profile_active=False,
        current_dump_ready_hold_count=1,
    )
    assert legacy_start == service.carry_transition_runtime_request(
        CarryTransitionRuntimeRequestFacts(
            release_safety_done=False,
            boundary_event=_event(dump_start=True),
            semantic_boundary_profile_active=False,
            current_dump_ready_hold_count=1,
        )
    )
    assert legacy_start.facts.legacy_dump_start_event is True
    assert legacy_start.should_check_dump_ready is False

    semantic_start = build_carry_transition_runtime_request(
        release_safety_done=False,
        boundary_event=_event(dump_start=True),
        semantic_boundary_profile_active=True,
        current_dump_ready_hold_count=1,
    )
    assert semantic_start == service.carry_transition_runtime_request(
        CarryTransitionRuntimeRequestFacts(
            release_safety_done=False,
            boundary_event=_event(dump_start=True),
            semantic_boundary_profile_active=True,
            current_dump_ready_hold_count=1,
        )
    )
    assert semantic_start.facts.legacy_dump_start_event is False
    assert semantic_start.should_check_dump_ready is False

    no_event = build_carry_transition_runtime_request(
        release_safety_done=False,
        boundary_event=None,
        semantic_boundary_profile_active=False,
        current_dump_ready_hold_count=1,
    )
    assert no_event == service.carry_transition_runtime_request(
        CarryTransitionRuntimeRequestFacts(
            release_safety_done=False,
            boundary_event=None,
            semantic_boundary_profile_active=False,
            current_dump_ready_hold_count=1,
        )
    )
    assert no_event.should_check_dump_ready is True
    facts = no_event.facts_with_dump_ready(True)
    assert facts.dump_ready is True
    assert facts.current_dump_ready_hold_count == 1


def test_dump_outcome_preserves_boundary_and_mass_low_reasons() -> None:
    complete = DumpLifecycleGateService.dump_outcome(
        dump_complete_event=True,
        legacy_dump_end_event=True,
        dump_done_hold_ready=True,
    )
    assert complete.action == "return"
    assert complete.coverage_reason == "dump_complete_boundary"
    assert complete.switch_reason == "dump_to_return_dump_complete_boundary"

    legacy_end = DumpLifecycleGateService.dump_outcome(
        dump_complete_event=False,
        legacy_dump_end_event=True,
        dump_done_hold_ready=True,
    )
    assert legacy_end.coverage_reason == "dump_end_boundary"
    assert legacy_end.switch_reason == "dump_to_return_dump_end"

    mass_low = DumpLifecycleGateService.dump_outcome(
        dump_complete_event=False,
        legacy_dump_end_event=False,
        dump_done_hold_ready=True,
    )
    assert mass_low.coverage_reason == "dump_mass_low"
    assert mass_low.switch_reason == "dump_to_return_mass_low"

    none = DumpLifecycleGateService.dump_outcome(
        dump_complete_event=False,
        legacy_dump_end_event=False,
        dump_done_hold_ready=False,
    )
    assert none.action == "none"


def test_dump_transition_runtime_updates_hold_count_and_outcome() -> None:
    service = DumpLifecycleGateService()

    boundary = service.dump_transition_runtime(
        DumpTransitionRuntimeFacts(
            dump_complete_event=True,
            legacy_dump_end_event=False,
            dump_done=False,
            current_dump_done_hold_count=1,
        ),
        dump_done_hold_steps=2,
    )
    assert boundary.dump_done_hold_count == 1
    assert boundary.outcome.switch_reason == "dump_to_return_dump_complete_boundary"

    mass_low = service.dump_transition_runtime(
        DumpTransitionRuntimeFacts(
            dump_complete_event=False,
            legacy_dump_end_event=False,
            dump_done=True,
            current_dump_done_hold_count=1,
        ),
        dump_done_hold_steps=2,
    )
    assert mass_low.dump_done_hold_count == 2
    assert mass_low.outcome.switch_reason == "dump_to_return_mass_low"

    reset = service.dump_transition_runtime(
        DumpTransitionRuntimeFacts(
            dump_complete_event=False,
            legacy_dump_end_event=False,
            dump_done=False,
            current_dump_done_hold_count=1,
        ),
        dump_done_hold_steps=2,
    )
    assert reset.dump_done_hold_count == 0
    assert reset.outcome.action == "none"


def test_dump_transition_request_preserves_boundary_event_gate() -> None:
    service = DumpLifecycleGateService()
    boundary = build_dump_transition_runtime_request(
        dump_done_use_boundary_event=True,
        boundary_event=_event(dump_complete=True, dump_end=True),
        semantic_boundary_profile_active=False,
        current_dump_done_hold_count=2,
    )
    assert boundary == service.dump_transition_runtime_request(
        DumpTransitionRuntimeRequestFacts(
            dump_done_use_boundary_event=True,
            boundary_event=_event(dump_complete=True, dump_end=True),
            semantic_boundary_profile_active=False,
            current_dump_done_hold_count=2,
        )
    )
    assert boundary.facts.dump_complete_event is True
    assert boundary.facts.legacy_dump_end_event is False
    assert boundary.should_check_dump_done is False
    assert boundary.facts.current_dump_done_hold_count == 2

    legacy_end = build_dump_transition_runtime_request(
        dump_done_use_boundary_event=True,
        boundary_event=_event(dump_end=True),
        semantic_boundary_profile_active=False,
        current_dump_done_hold_count=1,
    )
    assert legacy_end == service.dump_transition_runtime_request(
        DumpTransitionRuntimeRequestFacts(
            dump_done_use_boundary_event=True,
            boundary_event=_event(dump_end=True),
            semantic_boundary_profile_active=False,
            current_dump_done_hold_count=1,
        )
    )
    assert legacy_end.facts.dump_complete_event is False
    assert legacy_end.facts.legacy_dump_end_event is True
    assert legacy_end.should_check_dump_done is False

    semantic_end = build_dump_transition_runtime_request(
        dump_done_use_boundary_event=True,
        boundary_event=_event(dump_end=True),
        semantic_boundary_profile_active=True,
        current_dump_done_hold_count=1,
    )
    assert semantic_end == service.dump_transition_runtime_request(
        DumpTransitionRuntimeRequestFacts(
            dump_done_use_boundary_event=True,
            boundary_event=_event(dump_end=True),
            semantic_boundary_profile_active=True,
            current_dump_done_hold_count=1,
        )
    )
    assert semantic_end.facts.legacy_dump_end_event is False
    assert semantic_end.should_check_dump_done is False

    no_event = build_dump_transition_runtime_request(
        dump_done_use_boundary_event=True,
        boundary_event=None,
        semantic_boundary_profile_active=False,
        current_dump_done_hold_count=1,
    )
    assert no_event == service.dump_transition_runtime_request(
        DumpTransitionRuntimeRequestFacts(
            dump_done_use_boundary_event=True,
            boundary_event=None,
            semantic_boundary_profile_active=False,
            current_dump_done_hold_count=1,
        )
    )
    assert no_event.should_check_dump_done is True
    facts = no_event.facts_with_dump_done(True)
    assert facts.dump_done is True
    assert facts.current_dump_done_hold_count == 1

    disabled_boundary = build_dump_transition_runtime_request(
        dump_done_use_boundary_event=False,
        boundary_event=_event(dump_complete=True),
        semantic_boundary_profile_active=False,
        current_dump_done_hold_count=1,
    )
    assert disabled_boundary == service.dump_transition_runtime_request(
        DumpTransitionRuntimeRequestFacts(
            dump_done_use_boundary_event=False,
            boundary_event=_event(dump_complete=True),
            semantic_boundary_profile_active=False,
            current_dump_done_hold_count=1,
        )
    )
    assert disabled_boundary.facts.dump_complete_event is False
    assert disabled_boundary.should_check_dump_done is True


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
