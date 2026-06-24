from __future__ import annotations

from copy import deepcopy
from dataclasses import fields
from math import isnan
from typing import Any

import numpy as np

from testbed.planner.primitive.coverage.selection import CoverageSelectionService
from testbed.planner.primitive.coverage.selection_runtime import (
    PrimitiveCoverageSelectionRuntime,
    PrimitiveCoverageSelectionRuntimePorts,
)
from tests.test_agx_primitives_v2_2 import (
    _RecordingPolicy,
    _coverage_obs,
    _coverage_planner_policy,
)


def _assert_score_payloads_equal(
    actual: list[dict[str, Any]],
    expected: list[dict[str, Any]],
) -> None:
    assert len(actual) == len(expected)
    for actual_item, expected_item in zip(actual, expected):
        assert actual_item.keys() == expected_item.keys()
        for key, actual_value in actual_item.items():
            expected_value = expected_item[key]
            if isinstance(actual_value, float) or isinstance(expected_value, float):
                actual_float = float(actual_value)
                expected_float = float(expected_value)
                if isnan(actual_float) and isnan(expected_float):
                    continue
                assert np.isclose(actual_float, expected_float), key
                continue
            if isinstance(actual_value, list) or isinstance(expected_value, list):
                assert np.allclose(actual_value, expected_value, equal_nan=True), key
                continue
            assert actual_value == expected_value, key


def test_coverage_selection_runtime_boundary_uses_typed_ports_without_planner_self() -> None:
    names = {field.name for field in fields(PrimitiveCoverageSelectionRuntimePorts)}
    runtime_fields = {field.name for field in fields(PrimitiveCoverageSelectionRuntime)}

    assert "planner" not in names
    assert "self" not in names
    assert "state" in names
    assert "static_config" in names
    assert "observation_facts" in names
    assert "record_decision_event" in names
    assert runtime_fields == {"ports"}


def test_coverage_selection_service_matches_planner_facade_candidate_scores() -> None:
    policy = _coverage_planner_policy(
        dig_policy=_RecordingPolicy(0),
        coverage_extra={
            "use_env_removed_depth": False,
            "recent_row_selection_penalty": 1.5,
            "first_dig_strategy": "nearest_entry",
            "first_dig_proximity_weight": 8.0,
            "first_dig_max_entry_distance_m": 0.50,
        },
    )
    policy._primitive_coverage_selection_runtime().ensure_coverage_corridors()
    policy._coverage_runtime_state().coverage_last_selected_corridor_id = 1
    obs = _coverage_obs(
        mass=0.0,
        dig_distance=0.0,
        bucket_pose=(0.4148, 0.0, -0.3382),
    )

    service_corridors = deepcopy(policy._coverage_runtime_state().coverage_corridors)
    facts_by_id = policy._primitive_coverage_selection_runtime().coverage_selection_facts(obs, service_corridors)
    recent_row_reference = next(
        corridor
        for corridor in service_corridors
        if int(corridor.corridor_id) == policy._coverage_runtime_state().coverage_last_selected_corridor_id
    )
    service_result = CoverageSelectionService(
        policy._primitive_coverage_selection_runtime().coverage_selection_config(),
    ).select(
        service_corridors,
        facts_by_corridor_id=facts_by_id,
        recent_row_reference=recent_row_reference,
    )

    selected = policy._primitive_coverage_selection_runtime().select_coverage_corridor(obs)

    assert int(service_result.selected.corridor_id) == int(selected.corridor_id)
    assert service_result.first_dig_gate_available == 1
    _assert_score_payloads_equal(
        service_result.candidate_scores,
        policy._coverage_runtime_state().coverage_candidate_scores,
    )
    for service_corridor, planner_corridor in zip(
        service_corridors,
        policy._coverage_runtime_state().coverage_corridors,
    ):
        assert np.isclose(service_corridor.score, planner_corridor.score)
        assert np.isclose(
            service_corridor.last_remaining_depth_m,
            planner_corridor.last_remaining_depth_m,
            equal_nan=True,
        )
