from __future__ import annotations

from math import isnan
from typing import Any

import numpy as np

from testbed.planner.primitive_coverage_reports import CoverageReportService
from tests.test_agx_primitives_v2_2 import (
    _RecordingPolicy,
    _coverage_obs,
    _coverage_planner_policy,
)


def _assert_nested_equal(actual: Any, expected: Any) -> None:
    if isinstance(actual, dict) and isinstance(expected, dict):
        assert actual.keys() == expected.keys()
        for key, actual_value in actual.items():
            _assert_nested_equal(actual_value, expected[key])
        return
    if isinstance(actual, list) and isinstance(expected, list):
        assert len(actual) == len(expected)
        for actual_value, expected_value in zip(actual, expected):
            _assert_nested_equal(actual_value, expected_value)
        return
    if isinstance(actual, float) or isinstance(expected, float):
        actual_float = float(actual)
        expected_float = float(expected)
        if isnan(actual_float) and isnan(expected_float):
            return
        assert np.isclose(actual_float, expected_float)
        return
    assert actual == expected


def test_coverage_report_service_matches_corridor_debug_facade() -> None:
    policy = _coverage_planner_policy(dig_policy=_RecordingPolicy(0))
    policy._ensure_coverage_corridors()
    corridor = policy._coverage_corridors[0]

    service_payload = CoverageReportService().corridor_to_debug(
        corridor,
        attempt_limit=policy._coverage_corridor_attempt_limit(corridor),
        cell_confidence=policy._coverage_cell_confidence(corridor),
    )

    _assert_nested_equal(service_payload, policy._coverage_corridor_to_debug(corridor))


def test_coverage_report_service_matches_decision_event_facade() -> None:
    policy = _coverage_planner_policy(dig_policy=_RecordingPolicy(0))
    policy._ensure_coverage_corridors()
    corridor = policy._coverage_corridors[0]
    policy._coverage_active_corridor_id = int(corridor.corridor_id)
    obs = _coverage_obs(mass=3.0, dig_distance=0.0, deposited=2.0)

    service_payload = CoverageReportService().decision_event(
        "unit_event",
        state=policy._coverage_report_state(),
        corridor=policy._coverage_corridor_to_debug(corridor),
        bucket=policy._coverage_bucket_snapshot(obs),
        extra={"reason": "unit_test"},
    )

    policy._record_coverage_decision_event(
        "unit_event",
        obs=obs,
        corridor=corridor,
        extra={"reason": "unit_test"},
    )

    _assert_nested_equal(
        service_payload,
        policy.planner_trace()["coverage_decision_trace"][-1],
    )
