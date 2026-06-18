from __future__ import annotations

from copy import deepcopy

import numpy as np

from testbed.planner.primitive_coverage_updates import CoverageUpdateService
from tests.test_agx_primitives_v2_2 import (
    _RecordingPolicy,
    _coverage_obs,
    _coverage_planner_policy,
)


def _assert_corridor_update_equal(actual, expected) -> None:
    assert actual.attempts == expected.attempts
    assert actual.low_productivity_streak == expected.low_productivity_streak
    assert actual.depleted == expected.depleted
    assert actual.last_reason == expected.last_reason
    assert np.isclose(actual.belief_coverage, expected.belief_coverage)
    assert np.isclose(actual.last_payload_gain_kg, expected.last_payload_gain_kg)
    assert np.isclose(
        actual.last_effective_deposit_delta_kg,
        expected.last_effective_deposit_delta_kg,
    )
    assert np.isclose(
        actual.last_remaining_depth_m,
        expected.last_remaining_depth_m,
        equal_nan=True,
    )


def test_coverage_completion_update_service_matches_planner_facade() -> None:
    policy = _coverage_planner_policy(
        dig_policy=_RecordingPolicy(0),
        dig_cut_mode="operator_prior_sweep_belief",
        coverage_extra={"use_env_removed_depth": False},
    )
    policy._ensure_coverage_corridors()
    corridor = policy._coverage_corridors[0]
    policy._coverage_active_corridor_id = int(corridor.corridor_id)
    policy._coverage_current_payload_gain_kg = 8.0
    policy._coverage_cycle_start_deposit_kg = 0.0
    obs = _coverage_obs(mass=0.0, dig_distance=0.0, deposited=7.0)

    service_corridor = deepcopy(corridor)
    service_result = CoverageUpdateService(
        policy._coverage_update_config(),
    ).complete_dump(
        service_corridor,
        policy._coverage_completion_facts(
            obs,
            service_corridor,
            reason="unit_test_low_productivity",
        ),
    )

    policy._complete_coverage_dump(obs, reason="unit_test_low_productivity")

    _assert_corridor_update_equal(service_corridor, corridor)
    assert service_result.completed_dump_count == policy._coverage_completed_dump_count
    assert (
        service_result.global_low_productivity_streak
        == policy._coverage_global_low_productivity_streak
    )
    assert np.isclose(
        service_result.payload_gain_kg,
        policy._coverage_last_payload_gain_kg,
    )
    assert np.isclose(
        service_result.effective_deposit_delta_kg,
        policy._coverage_last_effective_deposit_delta_kg,
    )


def test_coverage_rejection_update_service_matches_planner_facade() -> None:
    policy = _coverage_planner_policy(
        dig_policy=_RecordingPolicy(0),
        coverage_extra={
            "use_env_removed_depth": False,
            "deplete_after_low_streak": 1,
        },
    )
    policy._ensure_coverage_corridors()
    corridor = policy._coverage_corridors[0]
    policy._coverage_active_corridor_id = int(corridor.corridor_id)
    policy._coverage_active_state_exemplar_ids = ["cell0_a", ""]
    policy._coverage_current_payload_gain_kg = 3.0
    policy._dig_best_mass_kg = 6.0
    policy._coverage_cycle_start_deposit_kg = 0.0
    obs = _coverage_obs(mass=4.0, dig_distance=0.0, deposited=0.0)

    service_corridor = deepcopy(corridor)
    service_result = CoverageUpdateService(
        policy._coverage_update_config(),
    ).reject_corridor(
        service_corridor,
        policy._coverage_rejection_facts(
            obs,
            service_corridor,
            reason="unit_test_reject",
        ),
    )

    policy._reject_active_coverage_corridor(obs, reason="unit_test_reject")

    _assert_corridor_update_equal(service_corridor, corridor)
    assert service_result.counted_attempt == 1
    assert service_result.rejected_state_exemplar_ids == ("cell0_a",)
    assert policy._coverage_rejected_state_exemplar_ids == {"cell0_a"}
    assert (
        service_result.global_low_productivity_streak
        == policy._coverage_global_low_productivity_streak
    )
