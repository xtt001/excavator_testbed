from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np

from testbed.data.schema import (
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX,
)
from testbed.planner import dig_lifecycle as dig_lifecycle_module
from testbed.planner import dig_lifecycle_transition as dig_transition_module
from testbed.planner import primitive_config
from testbed.planner.dig_lifecycle import (
    DIG_LIFECYCLE_CONFIG_KEYS,
    DIG_LIFECYCLE_ENTRY_RUNTIME_FACT_FIELDS,
    DIG_LIFECYCLE_FACT_FIELDS,
    DIG_LIFECYCLE_RUNTIME_CONFIG_KEYS,
    DIG_LIFECYCLE_RUNTIME_STATUS_FIELDS,
    FAILED_DIG_STOP_FACT_FIELDS,
    DigLifecycleConfig,
    DigLifecycleEntryRuntimeFacts,
    DigLifecycleFacts,
    DigLifecycleGateService,
    DigLifecyclePlannerConfig,
    DigLifecycleRuntimeStatusState,
    DigTransitionRuntimeFacts,
    DigTransitionRuntimeOutcome,
    FailedDigRecoveryFacts,
    FailedDigStopFacts,
    build_dig_lifecycle_config,
    build_dig_lifecycle_config_from_mapping,
    build_dig_lifecycle_entry_runtime_facts_from_mapping,
    build_dig_lifecycle_facts,
    build_dig_lifecycle_facts_from_mapping,
    build_dig_lifecycle_facts_from_observation_view,
    build_dig_lifecycle_runtime_config,
    build_dig_lifecycle_runtime_config_from_mapping,
    build_dig_lifecycle_runtime_status_state_from_mapping,
    build_failed_dig_stop_facts_from_mapping,
    build_failed_dig_stop_facts_from_runtime,
    normalize_failed_dig_replan_skill,
)
from testbed.planner.snapshots import build_planner_snapshot


def test_dig_transition_symbols_remain_compatible_facades() -> None:
    assert (
        dig_lifecycle_module.DigLifecycleTransitionService
        is dig_transition_module.DigLifecycleTransitionService
    )
    assert (
        dig_lifecycle_module.DigTransitionRuntimeFacts
        is dig_transition_module.DigTransitionRuntimeFacts
    )
    assert (
        dig_lifecycle_module.DigTransitionRuntimeRequest
        is dig_transition_module.DigTransitionRuntimeRequest
    )
    assert (
        dig_lifecycle_module.DigTransitionRuntimeOutcome
        is dig_transition_module.DigTransitionRuntimeOutcome
    )
    assert (
        dig_lifecycle_module.DigTransitionRuntimeProjection
        is dig_transition_module.DigTransitionRuntimeProjection
    )
    assert (
        dig_lifecycle_module.FailedDigStopFacts
        is dig_transition_module.FailedDigStopFacts
    )
    assert (
        dig_lifecycle_module.FailedDigStopState
        is dig_transition_module.FailedDigStopState
    )
    assert (
        dig_lifecycle_module.FAILED_DIG_STOP_FACT_FIELDS
        is dig_transition_module.FAILED_DIG_STOP_FACT_FIELDS
    )
    assert (
        dig_lifecycle_module.build_failed_dig_stop_facts_from_mapping
        is dig_transition_module.build_failed_dig_stop_facts_from_mapping
    )
    assert (
        dig_lifecycle_module.build_failed_dig_stop_facts_from_runtime
        is dig_transition_module.build_failed_dig_stop_facts_from_runtime
    )
    assert issubclass(
        DigLifecycleGateService,
        dig_transition_module.DigLifecycleTransitionService,
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


def test_dig_lifecycle_config_builder_is_domain_source_of_truth() -> None:
    values = {
        "dig_to_carry_min_bucket_mass_kg": 15,
        "dig_to_carry_min_distance_to_dig_area_m": 0.25,
        "dig_to_carry_target_bucket_mass_kg": None,
        "dig_to_carry_mass_plateau_enabled": True,
        "dig_to_carry_mass_plateau_min_bucket_mass_kg": 25,
        "dig_to_carry_mass_plateau_epsilon_kg": 0.5,
        "dig_to_carry_mass_plateau_hold_steps": 0,
        "dig_to_carry_mass_plateau_min_steps": 0,
        "dig_bad_replan_enabled": True,
        "dig_bad_replan_max_steps": 0,
        "dig_bad_replan_min_bucket_mass_kg": 5,
        "dig_exit_guard_enabled": True,
        "dig_exit_guard_min_steps": 0,
        "dig_exit_guard_overshoot_m": 0.2,
        "dig_exit_guard_min_bucket_mass_kg": 7,
        "dig_failed_replan_next_skill": "terminal-stop",
        "ignored": object(),
    }

    assert primitive_config.DIG_LIFECYCLE_CONFIG_KEYS is DIG_LIFECYCLE_CONFIG_KEYS
    assert primitive_config.build_dig_lifecycle_config is build_dig_lifecycle_config
    assert (
        primitive_config.build_dig_lifecycle_config_from_mapping
        is build_dig_lifecycle_config_from_mapping
    )
    assert (
        primitive_config.normalize_failed_dig_replan_skill
        is normalize_failed_dig_replan_skill
    )
    assert build_dig_lifecycle_config_from_mapping(values) == (
        DigLifecyclePlannerConfig(
            dig_to_carry_min_bucket_mass_kg=15.0,
            dig_to_carry_min_distance_to_dig_area_m=0.25,
            dig_to_carry_target_bucket_mass_kg=15.0,
            dig_to_carry_mass_plateau_enabled=True,
            dig_to_carry_mass_plateau_min_bucket_mass_kg=25.0,
            dig_to_carry_mass_plateau_epsilon_kg=0.5,
            dig_to_carry_mass_plateau_hold_steps=1,
            dig_to_carry_mass_plateau_min_steps=1,
            dig_bad_replan_enabled=True,
            dig_bad_replan_max_steps=1,
            dig_bad_replan_min_bucket_mass_kg=5.0,
            dig_exit_guard_enabled=True,
            dig_exit_guard_min_steps=1,
            dig_exit_guard_overshoot_m=0.2,
            dig_exit_guard_min_bucket_mass_kg=7.0,
            dig_failed_replan_next_skill="stop",
        )
    )


def test_build_dig_lifecycle_runtime_config_preserves_legacy_projection() -> None:
    values = {
        "dig_to_carry_min_bucket_mass_kg": "15.0",
        "dig_to_carry_min_distance_to_dig_area_m": "0.25",
        "dig_to_carry_target_bucket_mass_kg": "30.0",
        "dig_to_carry_mass_plateau_enabled": 1,
        "dig_to_carry_mass_plateau_min_bucket_mass_kg": "25.0",
        "dig_to_carry_mass_plateau_epsilon_kg": "0.5",
        "dig_to_carry_mass_plateau_hold_steps": 0,
        "dig_to_carry_mass_plateau_min_steps": 0,
        "dig_bad_replan_enabled": 1,
        "dig_bad_replan_max_steps": 0,
        "dig_bad_replan_min_bucket_mass_kg": "5.0",
        "dig_exit_guard_enabled": 1,
        "dig_exit_guard_min_steps": 0,
        "dig_exit_guard_overshoot_m": "0.2",
        "dig_exit_guard_min_bucket_mass_kg": "7.0",
        "dump_ready_min_bucket_mass_kg": "40.0",
        "dig_failed_replan_next_skill": "STOP",
        "pre_dig_align_enabled": 1,
        "pre_dig_align_first_dig_only": 0,
        "pre_dig_align_replan_after_failed_dig": 1,
    }
    expected = DigLifecycleConfig(
        dig_to_carry_min_bucket_mass_kg=15.0,
        dig_to_carry_min_distance_to_dig_area_m=0.25,
        dig_to_carry_target_bucket_mass_kg=30.0,
        dig_to_carry_mass_plateau_enabled=True,
        dig_to_carry_mass_plateau_min_bucket_mass_kg=25.0,
        dig_to_carry_mass_plateau_epsilon_kg=0.5,
        dig_to_carry_mass_plateau_hold_steps=0,
        dig_to_carry_mass_plateau_min_steps=0,
        dig_bad_replan_enabled=True,
        dig_bad_replan_max_steps=0,
        dig_bad_replan_min_bucket_mass_kg=5.0,
        dig_exit_guard_enabled=True,
        dig_exit_guard_min_steps=0,
        dig_exit_guard_overshoot_m=0.2,
        dig_exit_guard_min_bucket_mass_kg=7.0,
        dump_ready_min_bucket_mass_kg=40.0,
        dig_failed_replan_next_skill="STOP",
        pre_dig_align_enabled=True,
        pre_dig_align_first_dig_only=False,
        pre_dig_align_replan_after_failed_dig=True,
    )
    assert build_dig_lifecycle_runtime_config(**values) == expected
    assert build_dig_lifecycle_runtime_config_from_mapping(
        {**values, "ignored": object()}
    ) == expected
    assert set(DIG_LIFECYCLE_RUNTIME_CONFIG_KEYS) == set(values)


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


def test_runtime_status_snapshot_projects_config_and_runtime_state() -> None:
    snapshot = DigLifecycleGateService.runtime_status_snapshot(
        config=_config(dig_failed_replan_next_skill="stop"),
        state=DigLifecycleRuntimeStatusState(
            step_count=8,
            best_mass_kg=21.5,
            mass_plateau_count=3,
            dig_to_carry_reason="target_payload_loaded",
            bad_replan_count=2,
            exit_guard_replan_count=1,
        ),
    )

    assert snapshot.failed_replan_next_skill == "stop"
    assert snapshot.step_count == 8
    assert snapshot.best_mass_kg == 21.5
    assert snapshot.mass_plateau_count == 3
    assert snapshot.dig_to_carry_reason == "target_payload_loaded"
    assert snapshot.bad_replan_count == 2
    assert snapshot.exit_guard_replan_count == 1


def test_runtime_status_state_mapping_preserves_legacy_projection() -> None:
    values = {
        "step_count": "8",
        "best_mass_kg": "21.5",
        "mass_plateau_count": "3",
        "dig_to_carry_reason": 123,
        "bad_replan_count": "2",
        "exit_guard_replan_count": "1",
        "ignored": object(),
    }

    state = build_dig_lifecycle_runtime_status_state_from_mapping(values)

    assert {key for key, _ in DIG_LIFECYCLE_RUNTIME_STATUS_FIELDS} == (
        set(values) - {"ignored"}
    )
    assert state == DigLifecycleRuntimeStatusState(
        step_count=8,
        best_mass_kg=21.5,
        mass_plateau_count=3,
        dig_to_carry_reason="123",
        bad_replan_count=2,
        exit_guard_replan_count=1,
    )


def test_initial_runtime_state_preserves_legacy_reset_defaults() -> None:
    state = DigLifecycleGateService.initial_runtime_state()

    assert isinstance(state, DigLifecycleRuntimeStatusState)
    assert state.step_count == 0
    assert state.best_mass_kg == 0.0
    assert state.mass_plateau_count == 0
    assert state.dig_to_carry_reason == ""
    assert state.bad_replan_count == 0
    assert state.exit_guard_replan_count == 0


def test_entry_runtime_state_resets_attempt_fields_and_preserves_replan_counts() -> None:
    state = DigLifecycleGateService.entry_runtime_state(
        DigLifecycleEntryRuntimeFacts(
            bad_replan_count="2",
            exit_guard_replan_count="3",
        )
    )

    assert state.step_count == 0
    assert state.best_mass_kg == 0.0
    assert state.mass_plateau_count == 0
    assert state.dig_to_carry_reason == ""
    assert state.coverage_payload_gain_kg == 0.0
    assert state.bad_replan_count == 2
    assert state.exit_guard_replan_count == 3


def test_entry_runtime_facts_mapping_preserves_counter_projection() -> None:
    values = {
        "bad_replan_count": "2",
        "exit_guard_replan_count": 3.0,
        "ignored": object(),
    }

    facts = build_dig_lifecycle_entry_runtime_facts_from_mapping(values)

    assert {key for key, _ in DIG_LIFECYCLE_ENTRY_RUNTIME_FACT_FIELDS} == (
        set(values) - {"ignored"}
    )
    assert facts.bad_replan_count == 2
    assert facts.exit_guard_replan_count == 3


def test_build_dig_lifecycle_facts_projects_boundary_and_geometry_inputs() -> None:
    corridor = SimpleNamespace(
        entry_x_m=0.25,
        entry_z_m=0.75,
        exit_x_m=-0.50,
        exit_z_m=0.10,
    )

    facts = build_dig_lifecycle_facts(
        mass_in_bucket_kg=12.0,
        min_distance_to_dig_area_m=0.20,
        boundary_metrics={
            "mass_in_bucket_kg": 18.0,
            "min_distance_to_dig_area_m": 0.45,
        },
        semantic_boundary_profile_active=True,
        boundary_dig_complete=True,
        coverage_terminal_stop_requested=True,
        dig_step_count=4,
        dig_best_mass_kg=13.5,
        dig_mass_plateau_count=2,
        coverage_current_payload_gain_kg=9.0,
        active_corridor=corridor,
        bucket_tip_dig_area_pose=(0.10, 0.0, 0.35),
    )

    assert facts.mass_in_bucket_kg == 12.0
    assert facts.min_distance_to_dig_area_m == 0.20
    assert facts.carry_mass_in_bucket_kg == 18.0
    assert facts.carry_min_distance_to_dig_area_m == 0.45
    assert facts.semantic_boundary_profile_active is True
    assert facts.boundary_dig_complete is True
    assert facts.coverage_terminal_stop_requested is True
    assert facts.dig_step_count == 4
    assert facts.dig_best_mass_kg == 13.5
    assert facts.dig_mass_plateau_count == 2
    assert facts.coverage_current_payload_gain_kg == 9.0
    assert facts.active_corridor_entry_xz == (0.25, 0.75)
    assert facts.active_corridor_exit_xz == (-0.50, 0.10)
    assert facts.bucket_tip_xz == (0.10, 0.35)


def test_build_dig_lifecycle_facts_from_mapping_preserves_projection() -> None:
    corridor = SimpleNamespace(
        entry_x_m=0.25,
        entry_z_m=0.75,
        exit_x_m=-0.50,
        exit_z_m=0.10,
    )
    values = {
        "mass_in_bucket_kg": "12.0",
        "min_distance_to_dig_area_m": "0.20",
        "boundary_metrics": {
            "mass_in_bucket_kg": "18.0",
            "min_distance_to_dig_area_m": "0.45",
        },
        "semantic_boundary_profile_active": 1,
        "boundary_dig_complete": object(),
        "coverage_terminal_stop_requested": np.bool_(True),
        "dig_step_count": "4",
        "dig_best_mass_kg": "13.5",
        "dig_mass_plateau_count": np.int64(2),
        "coverage_current_payload_gain_kg": "9.0",
        "active_corridor": corridor,
        "bucket_tip_dig_area_pose": (0.10, 0.0, 0.35),
        "ignored": object(),
    }

    facts = build_dig_lifecycle_facts_from_mapping(values)

    assert set(DIG_LIFECYCLE_FACT_FIELDS) == set(values) - {"ignored"}
    assert facts == build_dig_lifecycle_facts(
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


def test_build_dig_lifecycle_facts_from_observation_view_preserves_sources() -> None:
    corridor = SimpleNamespace(
        entry_x_m=0.25,
        entry_z_m=0.75,
        exit_x_m=-0.50,
        exit_z_m=0.10,
    )
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX] = 0.10
    env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX] = 0.0
    env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX] = 0.35
    obs = {
        "env_state": env_state,
        "task_metrics": {
            "mass_in_bucket_kg": 12.0,
            "min_distance_to_dig_area_m": 0.20,
        },
    }
    boundary_event = SimpleNamespace(
        dig_complete=True,
        metrics={
            "mass_in_bucket_kg": 18.0,
            "min_distance_to_dig_area_m": 0.45,
        },
    )
    view = build_planner_snapshot(
        obs,
        active_skill="dig",
        cycle_index=4,
        prev_action=None,
        boundary_event=boundary_event,
        action_dim=4,
    ).view

    expected = build_dig_lifecycle_facts(
        mass_in_bucket_kg=12.0,
        min_distance_to_dig_area_m=0.20,
        boundary_metrics=boundary_event.metrics,
        semantic_boundary_profile_active=True,
        boundary_dig_complete=True,
        coverage_terminal_stop_requested=True,
        dig_step_count=4,
        dig_best_mass_kg=13.5,
        dig_mass_plateau_count=2,
        coverage_current_payload_gain_kg=9.0,
        active_corridor=corridor,
        bucket_tip_dig_area_pose=view.bucket_tip_dig_area_pose,
    )

    facts = build_dig_lifecycle_facts_from_observation_view(
        view=view,
        boundary_event=boundary_event,
        semantic_boundary_profile_active=True,
        coverage_terminal_stop_requested=True,
        dig_step_count=4,
        dig_best_mass_kg=13.5,
        dig_mass_plateau_count=2,
        coverage_current_payload_gain_kg=9.0,
        active_corridor=corridor,
    )
    service_facts = DigLifecycleGateService.facts_from_observation_view(
        view=view,
        boundary_event=boundary_event,
        semantic_boundary_profile_active=True,
        coverage_terminal_stop_requested=True,
        dig_step_count=4,
        dig_best_mass_kg=13.5,
        dig_mass_plateau_count=2,
        coverage_current_payload_gain_kg=9.0,
        active_corridor=corridor,
    )

    assert facts == expected
    assert service_facts == expected
    np.testing.assert_allclose(facts.bucket_tip_xz, (0.10, 0.35))


def test_build_dig_lifecycle_facts_falls_back_without_boundary_or_geometry() -> None:
    facts = build_dig_lifecycle_facts(
        mass_in_bucket_kg=12.0,
        min_distance_to_dig_area_m=0.20,
        boundary_metrics=None,
        semantic_boundary_profile_active=False,
        boundary_dig_complete=False,
        coverage_terminal_stop_requested=False,
        dig_step_count=4,
        dig_best_mass_kg=13.5,
        dig_mass_plateau_count=2,
        coverage_current_payload_gain_kg=9.0,
    )

    assert facts.carry_mass_in_bucket_kg == 12.0
    assert facts.carry_min_distance_to_dig_area_m == 0.20
    assert facts.active_corridor_entry_xz is None
    assert facts.active_corridor_exit_xz is None
    assert facts.bucket_tip_xz is None


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


def test_dig_transition_runtime_preserves_priority_and_failed_reasons() -> None:
    service = DigLifecycleGateService()

    exit_guard = service.dig_transition_runtime(
        DigTransitionRuntimeFacts(
            exit_guard_ready=True,
            bad_replan_ready=True,
            complete_boundary_low_payload=True,
            dig_to_carry_ready=True,
            dig_to_carry_reason="target_payload_loaded",
        )
    )
    assert exit_guard.action == "failed_dig"
    assert exit_guard.counter == "exit_guard_replan"
    assert exit_guard.failed_dig_reason == "exit_overshoot_low_payload"
    assert exit_guard.coverage_reject_reason == "exit_overshoot_low_payload"

    bad_replan = service.dig_transition_runtime(
        DigTransitionRuntimeFacts(
            exit_guard_ready=False,
            bad_replan_ready=True,
            complete_boundary_low_payload=True,
            dig_to_carry_ready=True,
            dig_to_carry_reason="target_payload_loaded",
        )
    )
    assert bad_replan.action == "failed_dig"
    assert bad_replan.counter == "bad_replan"
    assert bad_replan.failed_dig_reason == "bad_dig_low_payload"
    assert bad_replan.coverage_reject_reason == "bad_dig_low_payload"

    complete_low = service.dig_transition_runtime(
        DigTransitionRuntimeFacts(
            exit_guard_ready=False,
            bad_replan_ready=False,
            complete_boundary_low_payload=True,
            dig_to_carry_ready=True,
            dig_to_carry_reason="target_payload_loaded",
        )
    )
    assert complete_low.action == "failed_dig"
    assert complete_low.counter == "bad_replan"
    assert complete_low.failed_dig_reason == "complete_low_payload"
    assert complete_low.coverage_reject_reason == "dig_complete_low_current_payload"


def test_dig_transition_runtime_preserves_carry_reason_and_wait() -> None:
    service = DigLifecycleGateService()

    carry = service.dig_transition_runtime(
        DigTransitionRuntimeFacts(
            exit_guard_ready=False,
            bad_replan_ready=False,
            complete_boundary_low_payload=False,
            dig_to_carry_ready=True,
            dig_to_carry_reason="target_payload_loaded",
        )
    )
    assert carry.action == "carry"
    assert carry.switch_reason == "dig_to_carry_target_payload_loaded"

    fallback_reason = service.dig_transition_runtime(
        DigTransitionRuntimeFacts(
            exit_guard_ready=False,
            bad_replan_ready=False,
            complete_boundary_low_payload=False,
            dig_to_carry_ready=True,
            dig_to_carry_reason="",
        )
    )
    assert fallback_reason.action == "carry"
    assert fallback_reason.switch_reason == "dig_to_carry_loaded"

    wait = service.dig_transition_runtime(
        DigTransitionRuntimeFacts(
            exit_guard_ready=False,
            bad_replan_ready=False,
            complete_boundary_low_payload=False,
            dig_to_carry_ready=False,
        )
    )
    assert wait.action == "none"
    assert wait.switch_reason == ""


def test_dig_transition_runtime_projection_suggests_counter_increments() -> None:
    service = DigLifecycleGateService()

    exit_guard = service.dig_transition_runtime_projection(
        DigTransitionRuntimeOutcome(
            action="failed_dig",
            counter="exit_guard_replan",
            failed_dig_reason="exit_overshoot_low_payload",
            coverage_reject_reason="exit_overshoot_low_payload",
        )
    )
    bad_replan = service.dig_transition_runtime_projection(
        DigTransitionRuntimeOutcome(
            action="failed_dig",
            counter="bad_replan",
            failed_dig_reason="bad_dig_low_payload",
            coverage_reject_reason="bad_dig_low_payload",
        )
    )
    carry = service.dig_transition_runtime_projection(
        DigTransitionRuntimeOutcome(
            action="carry",
            switch_reason="dig_to_carry_target_payload_loaded",
        )
    )
    wait = service.dig_transition_runtime_projection(
        DigTransitionRuntimeOutcome(action="none")
    )

    assert exit_guard.should_restart_after_failed_dig
    assert exit_guard.exit_guard_replan_count_increment == 1
    assert exit_guard.bad_replan_count_increment == 0
    assert bad_replan.should_restart_after_failed_dig
    assert bad_replan.exit_guard_replan_count_increment == 0
    assert bad_replan.bad_replan_count_increment == 1
    assert carry.should_handoff_to_carry
    assert carry.bad_replan_count_increment == 0
    assert carry.exit_guard_replan_count_increment == 0
    assert wait.outcome.action == "none"
    assert not wait.should_restart_after_failed_dig
    assert not wait.should_handoff_to_carry


def test_dig_transition_runtime_request_skips_later_gates_after_exit_guard() -> None:
    request = DigLifecycleGateService.dig_transition_runtime_request(
        exit_guard_ready=True,
    )

    assert not request.should_check_bad_replan
    assert not request.should_check_complete_boundary_low_payload(False)
    assert not request.should_check_dig_to_carry(
        bad_replan_ready=False,
        complete_boundary_low_payload=False,
    )
    assert request.facts_with_gate_results(
        bad_replan_ready=False,
        complete_boundary_low_payload=False,
        dig_to_carry_ready=False,
    ) == DigTransitionRuntimeFacts(
        exit_guard_ready=True,
        bad_replan_ready=False,
        complete_boundary_low_payload=False,
        dig_to_carry_ready=False,
        dig_to_carry_reason="",
    )


def test_dig_transition_runtime_request_preserves_gate_order() -> None:
    request = DigLifecycleGateService.dig_transition_runtime_request(
        exit_guard_ready=False,
    )

    assert request.should_check_bad_replan
    assert not request.should_check_complete_boundary_low_payload(True)
    assert not request.should_check_dig_to_carry(
        bad_replan_ready=True,
        complete_boundary_low_payload=False,
    )
    assert request.should_check_complete_boundary_low_payload(False)
    assert not request.should_check_dig_to_carry(
        bad_replan_ready=False,
        complete_boundary_low_payload=True,
    )
    assert request.should_check_dig_to_carry(
        bad_replan_ready=False,
        complete_boundary_low_payload=False,
    )

    assert request.facts_with_gate_results(
        bad_replan_ready=False,
        complete_boundary_low_payload=False,
        dig_to_carry_ready=True,
        dig_to_carry_reason="target_payload_loaded",
    ) == DigTransitionRuntimeFacts(
        exit_guard_ready=False,
        bad_replan_ready=False,
        complete_boundary_low_payload=False,
        dig_to_carry_ready=True,
        dig_to_carry_reason="target_payload_loaded",
    )


def test_failed_dig_recovery_defaults_to_dig_retry() -> None:
    decision = DigLifecycleGateService().failed_dig_recovery(
        reason="bad_dig_low_payload",
        facts=FailedDigRecoveryFacts(cycle_index=1),
        config=_config(),
    )

    assert decision.next_skill == "dig"
    assert decision.switch_reason == "dig_retry_bad_dig_low_payload"
    assert decision.terminal_reason == ""


def test_failed_dig_recovery_can_stop_with_terminal_reason() -> None:
    decision = DigLifecycleGateService().failed_dig_recovery(
        reason="exit_overshoot_low_payload",
        facts=FailedDigRecoveryFacts(cycle_index=1),
        config=_config(dig_failed_replan_next_skill="stop"),
    )

    assert decision.next_skill == "stop"
    assert decision.switch_reason == "dig_failed_stop_exit_overshoot_low_payload"
    assert decision.terminal_reason == "dig_failed_exit_overshoot_low_payload"


def test_failed_dig_stop_state_projects_event_payload_and_reasons() -> None:
    state = DigLifecycleGateService.failed_dig_stop_state(
        FailedDigStopFacts(
            reason="exit_overshoot_low_payload",
            coverage_current_payload_gain_kg=12.0,
            dig_best_mass_kg=18.0,
            current_bucket_mass_kg=16.0,
            dig_step_count=42,
        )
    )

    assert state.switch_reason == "dig_failed_stop_exit_overshoot_low_payload"
    assert state.terminal_reason == "dig_failed_exit_overshoot_low_payload"
    assert state.coverage_event == "failed_dig_stop"
    assert state.terminal_stop_replace is True
    assert state.coverage_event_extra == {
        "reason": "exit_overshoot_low_payload",
        "payload_gain_kg": 18.0,
        "current_bucket_mass_kg": 16.0,
        "dig_best_mass_kg": 18.0,
        "dig_step_count": 42,
    }


def test_failed_dig_stop_state_preserves_explicit_recovery_reasons() -> None:
    state = DigLifecycleGateService.failed_dig_stop_state(
        FailedDigStopFacts(
            reason="bad_dig_low_payload",
            coverage_current_payload_gain_kg=5.0,
            dig_best_mass_kg=4.0,
            current_bucket_mass_kg=9.0,
            dig_step_count=7,
            switch_reason="dig_failed_stop_custom",
            terminal_reason="dig_failed_custom",
        )
    )

    assert state.switch_reason == "dig_failed_stop_custom"
    assert state.terminal_reason == "dig_failed_custom"
    assert state.coverage_event_extra["payload_gain_kg"] == 9.0


def test_failed_dig_stop_facts_mapping_coerces_shell_fields_and_reasons() -> None:
    values = {
        "reason": "bad_dig_low_payload",
        "coverage_current_payload_gain_kg": "5.5",
        "dig_best_mass_kg": "4.25",
        "current_bucket_mass_kg": "9.75",
        "dig_step_count": "7",
        "switch_reason": "dig_failed_stop_custom",
        "terminal_reason": "dig_failed_custom",
        "ignored": object(),
    }

    facts = build_failed_dig_stop_facts_from_mapping(values)

    assert tuple(key for key, _ in FAILED_DIG_STOP_FACT_FIELDS) == (
        "coverage_current_payload_gain_kg",
        "dig_best_mass_kg",
        "dig_step_count",
    )
    assert facts == FailedDigStopFacts(
        reason="bad_dig_low_payload",
        coverage_current_payload_gain_kg=5.5,
        dig_best_mass_kg=4.25,
        current_bucket_mass_kg=9.75,
        dig_step_count=7,
        switch_reason="dig_failed_stop_custom",
        terminal_reason="dig_failed_custom",
    )


def test_failed_dig_stop_facts_runtime_builder_coerces_runtime_inputs() -> None:
    facts = build_failed_dig_stop_facts_from_runtime(
        reason="complete_low_payload",
        coverage_current_payload_gain_kg="6.5",
        dig_best_mass_kg="8.25",
        current_bucket_mass_kg=np.float64(7.5),
        dig_step_count=np.int64(11),
        switch_reason="dig_failed_stop_complete_low_payload",
        terminal_reason=None,
    )

    assert facts == FailedDigStopFacts(
        reason="complete_low_payload",
        coverage_current_payload_gain_kg=6.5,
        dig_best_mass_kg=8.25,
        current_bucket_mass_kg=7.5,
        dig_step_count=11,
        switch_reason="dig_failed_stop_complete_low_payload",
        terminal_reason=None,
    )


def test_failed_dig_recovery_prefers_first_cycle_pre_dig_align() -> None:
    service = DigLifecycleGateService()
    config = _config(
        pre_dig_align_enabled=True,
        pre_dig_align_first_dig_only=True,
    )

    assert service.pre_dig_align_before_dig(
        FailedDigRecoveryFacts(cycle_index=0),
        config,
    )
    assert not service.pre_dig_align_before_dig(
        FailedDigRecoveryFacts(cycle_index=1),
        config,
    )
    decision = service.failed_dig_recovery(
        reason="bad_dig_low_payload",
        facts=FailedDigRecoveryFacts(cycle_index=0),
        config=config,
    )

    assert decision.next_skill == "pre_dig_align"
    assert decision.switch_reason == "dig_to_pre_dig_align_bad_dig_low_payload"


def test_failed_dig_recovery_can_align_after_failed_dig() -> None:
    service = DigLifecycleGateService()
    config = _config(
        pre_dig_align_enabled=True,
        pre_dig_align_first_dig_only=True,
        pre_dig_align_replan_after_failed_dig=True,
        dig_failed_replan_next_skill="stop",
    )

    assert service.pre_dig_align_after_failed_dig(config)
    decision = service.failed_dig_recovery(
        reason="exit_overshoot_low_payload",
        facts=FailedDigRecoveryFacts(cycle_index=1),
        config=config,
    )

    assert decision.next_skill == "pre_dig_align"
    assert decision.switch_reason == "dig_to_pre_dig_align_exit_overshoot_low_payload"
    assert decision.terminal_reason == ""
