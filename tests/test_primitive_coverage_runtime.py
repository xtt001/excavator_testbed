from __future__ import annotations

from copy import deepcopy

import numpy as np

from testbed.planner.primitive.facts.capabilities import PrimitiveObservationFacts
from testbed.planner.primitive.coverage.effects import (
    CoverageEffectFactService,
    CoverageRuntimeService,
)
from tests.test_agx_primitives_v2_2 import (
    _RecordingPolicy,
    _coverage_obs,
    _coverage_planner_policy,
)


def _coverage_effect_fact_service(policy) -> CoverageEffectFactService:
    return CoverageEffectFactService(
        state=policy._coverage_runtime_state(),
        cycle_state=policy._primitive_cycle_runtime_state(),
        observation_facts=(
            lambda obs: PrimitiveObservationFacts.from_obs(
                obs,
                action_dim=int(policy.action_dim),
            )
        ),
        remaining_depth=(
            lambda obs, corridor: policy._primitive_coverage_selection_runtime().coverage_remaining_depth_for_corridor(
                obs,
                corridor,
            )
        ),
        corridor_attempt_limit=policy._primitive_coverage_selection_runtime().coverage_corridor_attempt_limit,
    )


def test_coverage_runtime_service_matches_multi_pass_reopen_facade() -> None:
    policy = _coverage_planner_policy(
        dig_policy=_RecordingPolicy(0),
        coverage_extra={
            "use_env_removed_depth": True,
            "multi_pass_enabled": True,
            "multi_pass_max_passes": 2,
            "multi_pass_min_remaining_depth_m": 0.04,
        },
    )
    policy._primitive_coverage_selection_runtime().ensure_coverage_corridors()
    for corridor in policy._coverage_runtime_state().coverage_corridors:
        corridor.depleted = True
        corridor.attempts = 2
        corridor.low_productivity_streak = 2
        corridor.last_reason = "unit_test_depleted"
    policy._coverage_runtime_state().coverage_global_low_productivity_streak = 3
    policy._coverage_runtime_state().coverage_rejected_state_exemplar_ids.update({"cell0_a"})
    obs = _coverage_obs(mass=0.0, dig_distance=0.0, removed_cell0=0.02)

    service_corridors = deepcopy(policy._coverage_runtime_state().coverage_corridors)
    effect_runtime = policy._primitive_coverage_effect_runtime()
    service_result = CoverageRuntimeService(
        effect_runtime.coverage_runtime_config(),
    ).maybe_reopen_pass(
        service_corridors,
        _coverage_effect_fact_service(policy).reopen_facts(
            obs,
            service_corridors,
            reason="unit_test_reopen",
        ),
    )

    reopened = effect_runtime.maybe_reopen_coverage_pass(
        obs,
        reason="unit_test_reopen",
    )

    assert reopened is True
    assert service_result.reopened is True
    assert service_result.pass_index == policy._coverage_runtime_state().coverage_pass_index
    assert service_result.active_corridor_id == policy._coverage_runtime_state().coverage_active_corridor_id
    assert (
        service_result.global_low_productivity_streak
        == policy._coverage_runtime_state().coverage_global_low_productivity_streak
    )
    assert service_result.clear_rejected_state_exemplar_ids is True
    assert policy._coverage_runtime_state().coverage_rejected_state_exemplar_ids == set()
    assert service_result.reopened_corridors[-1] == (
        policy.planner_trace()["coverage_decision_trace"][-1]["reopened_corridors"][-1]
    )
    for service_corridor, planner_corridor in zip(
        service_corridors,
        policy._coverage_runtime_state().coverage_corridors,
    ):
        assert service_corridor.depleted == planner_corridor.depleted
        assert service_corridor.attempts == planner_corridor.attempts
        assert (
            service_corridor.low_productivity_streak
            == planner_corridor.low_productivity_streak
        )
        assert service_corridor.last_reason == planner_corridor.last_reason
        assert np.isclose(
            service_corridor.last_remaining_depth_m,
            planner_corridor.last_remaining_depth_m,
            equal_nan=True,
        )


def test_coverage_runtime_service_matches_terminal_stop_replace_gate() -> None:
    policy = _coverage_planner_policy(dig_policy=_RecordingPolicy(0))

    effect_runtime = policy._primitive_coverage_effect_runtime()
    first = CoverageRuntimeService(
        effect_runtime.coverage_runtime_config()
    ).request_terminal_stop(
        _coverage_effect_fact_service(policy).terminal_facts(
            "first_reason",
            replace=False,
        )
    )
    effect_runtime.request_coverage_terminal_stop("first_reason")

    ignored = CoverageRuntimeService(
        effect_runtime.coverage_runtime_config()
    ).request_terminal_stop(
        _coverage_effect_fact_service(policy).terminal_facts(
            "ignored_reason",
            replace=False,
        )
    )
    effect_runtime.request_coverage_terminal_stop("ignored_reason")

    replaced = CoverageRuntimeService(
        effect_runtime.coverage_runtime_config()
    ).request_terminal_stop(
        _coverage_effect_fact_service(policy).terminal_facts(
            "replacement_reason",
            replace=True,
        )
    )
    effect_runtime.request_coverage_terminal_stop(
        "replacement_reason",
        replace=True,
    )

    assert first.record_event is True
    assert ignored.record_event is False
    assert replaced.record_event is True
    assert policy._coverage_runtime_state().coverage_terminal_stop_requested is True
    assert policy._coverage_runtime_state().coverage_terminal_stop_reason == "replacement_reason"
    terminal_events = [
        event
        for event in policy.planner_trace()["coverage_decision_trace"]
        if event["event"] == "terminal_stop"
    ]
    assert [event["reason"] for event in terminal_events] == [
        "first_reason",
        "replacement_reason",
    ]
