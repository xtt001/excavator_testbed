from __future__ import annotations

from math import isnan
from typing import Any

import numpy as np

from testbed.planner.primitive_coverage_reports import (
    CoverageDebugReportInputs,
    CoverageReportConfig,
    CoverageReportService,
    CoverageSummaryReportStatus,
    CoverageTraceReportStatus,
)
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


def _coverage_debug_report_inputs(policy: Any) -> CoverageDebugReportInputs:
    active_corridor = policy._coverage_active_corridor()
    return CoverageDebugReportInputs(
        active_corridor_id=policy._coverage_active_corridor_id,
        last_selected_corridor_id=policy._coverage_last_selected_corridor_id,
        last_selected_cell_id=policy._coverage_corridor_cell_id_by_id(
            policy._coverage_last_selected_corridor_id
        ),
        last_selected_row_id=policy._coverage_corridor_row_id_by_id(
            policy._coverage_last_selected_corridor_id
        ),
        active_corridor=(
            None
            if active_corridor is None
            else policy._coverage_corridor_to_debug(active_corridor)
        ),
        active_cell_id=policy._coverage_active_cell_id(),
        active_score=policy._coverage_active_corridor_score(),
        state_exemplar_enabled=policy.coverage_state_exemplars_enabled,
        state_exemplar_ids=policy._coverage_active_state_exemplar_ids,
        state_exemplar_distance=policy._coverage_active_state_exemplar_distance,
        depleted_count=policy._coverage_depleted_count(),
        pass_index=policy._coverage_pass_index,
        multi_pass_enabled=policy.coverage_multi_pass_enabled,
        multi_pass_max_passes=policy.coverage_multi_pass_max_passes,
        multi_pass_min_remaining_depth_m=(
            policy.coverage_multi_pass_min_remaining_depth_m
        ),
        last_payload_gain_kg=policy._coverage_last_payload_gain_kg,
        last_effective_deposit_delta_kg=(
            policy._coverage_last_effective_deposit_delta_kg
        ),
        global_low_productivity_streak=(
            policy._coverage_global_low_productivity_streak
        ),
        use_env_removed_depth=policy.coverage_use_env_removed_depth,
        candidate_layout=policy.coverage_candidate_layout,
        first_dig_strategy=policy.coverage_first_dig_strategy,
        first_dig_preferred_corridor_id=(
            policy.coverage_first_dig_preferred_corridor_id
        ),
        first_dig_max_entry_distance_m=(
            policy.coverage_first_dig_max_entry_distance_m
        ),
        first_dig_qpos_delta_weight=policy.coverage_first_dig_qpos_delta_weight,
        first_dig_max_qpos_delta=policy.coverage_first_dig_max_qpos_delta,
        terminal_stop_requested=policy._coverage_terminal_stop_requested,
        terminal_stop_reason=policy._coverage_terminal_stop_reason,
        corridors=[
            policy._coverage_corridor_to_debug(corridor)
            for corridor in policy._coverage_corridors
        ],
        candidate_scores=policy._coverage_candidate_scores,
    )


def _coverage_report_config(policy: Any) -> CoverageReportConfig:
    return CoverageReportConfig(
        state_exemplar_enabled=policy.coverage_state_exemplars_enabled,
        multi_pass_enabled=policy.coverage_multi_pass_enabled,
        multi_pass_max_passes=policy.coverage_multi_pass_max_passes,
        multi_pass_min_remaining_depth_m=(
            policy.coverage_multi_pass_min_remaining_depth_m
        ),
        use_env_removed_depth=policy.coverage_use_env_removed_depth,
        candidate_layout=policy.coverage_candidate_layout,
        first_dig_strategy=policy.coverage_first_dig_strategy,
        first_dig_preferred_corridor_id=(
            policy.coverage_first_dig_preferred_corridor_id
        ),
        first_dig_max_entry_distance_m=(
            policy.coverage_first_dig_max_entry_distance_m
        ),
        first_dig_qpos_delta_weight=policy.coverage_first_dig_qpos_delta_weight,
        first_dig_max_qpos_delta=policy.coverage_first_dig_max_qpos_delta,
    )


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


def test_coverage_report_service_matches_debug_fields_with_active_corridor() -> None:
    policy = _coverage_planner_policy(dig_policy=_RecordingPolicy(0))
    policy._ensure_coverage_corridors()
    corridor = policy._coverage_corridors[0]
    policy._coverage_active_corridor_id = int(corridor.corridor_id)
    policy._coverage_last_selected_corridor_id = int(corridor.corridor_id)

    service_payload = CoverageReportService().debug_fields(
        _coverage_debug_report_inputs(policy)
    )

    _assert_nested_equal(service_payload, policy._debug_report_coverage_fields())


def test_coverage_report_service_matches_debug_fields_without_active_corridor() -> None:
    policy = _coverage_planner_policy(dig_policy=_RecordingPolicy(0))

    service_payload = CoverageReportService().debug_fields(
        _coverage_debug_report_inputs(policy)
    )

    _assert_nested_equal(service_payload, policy._debug_report_coverage_fields())
    assert service_payload["coverage_corridor_id"] == -1
    assert service_payload["coverage_selected_corridor_id"] == -1
    assert service_payload["coverage_last_selected_cell_id"] == -1
    assert service_payload["coverage_last_selected_row_id"] == -1
    assert isnan(float(service_payload["coverage_entry_x_m"]))
    assert isnan(float(service_payload["coverage_corridor_score"]))


def test_coverage_report_service_projects_debug_fields_from_runtime_state() -> None:
    policy = _coverage_planner_policy(dig_policy=_RecordingPolicy(0))
    policy._ensure_coverage_corridors()
    corridor = policy._coverage_corridors[0]
    policy._coverage_active_corridor_id = int(corridor.corridor_id)
    policy._coverage_last_selected_corridor_id = int(corridor.corridor_id)

    service_payload = CoverageReportService().debug_fields_from_state(
        policy._coverage_runtime_state(),
        config=_coverage_report_config(policy),
        selection_service=policy._coverage_selection_service(),
    )

    _assert_nested_equal(service_payload, policy._debug_report_coverage_fields())


def test_coverage_report_service_projects_empty_debug_fields_from_runtime_state() -> None:
    policy = _coverage_planner_policy(dig_policy=_RecordingPolicy(0))

    service_payload = CoverageReportService().debug_fields_from_state(
        policy._coverage_runtime_state(),
        config=_coverage_report_config(policy),
        selection_service=policy._coverage_selection_service(),
    )

    _assert_nested_equal(service_payload, policy._debug_report_coverage_fields())
    assert service_payload["coverage_corridor_id"] == -1
    assert service_payload["coverage_last_selected_cell_id"] == -1
    assert service_payload["coverage_last_selected_row_id"] == -1
    assert isnan(float(service_payload["coverage_entry_x_m"]))
    assert isnan(float(service_payload["coverage_corridor_score"]))


def test_coverage_report_service_projects_trace_status() -> None:
    corridors = [{"corridor_id": 7, "score": 1.25}]
    decision_trace = [{"event": "select_corridor"}]

    status = CoverageReportService().trace_status(
        use_env_removed_depth=False,
        candidate_layout="corridor_grid",
        first_dig_strategy="preferred_corridor",
        pass_index=3,
        multi_pass_enabled=True,
        multi_pass_max_passes=4,
        multi_pass_min_remaining_depth_m=0.05,
        first_dig_preferred_corridor_id=None,
        corridors=corridors,
        decision_trace=decision_trace,
        terminal_stop_requested=True,
        terminal_stop_reason="dig_area_depleted",
    )

    assert status == CoverageTraceReportStatus(
        use_env_removed_depth=False,
        candidate_layout="corridor_grid",
        first_dig_strategy="preferred_corridor",
        pass_index=3,
        multi_pass_enabled=True,
        multi_pass_max_passes=4,
        multi_pass_min_remaining_depth_m=0.05,
        first_dig_preferred_corridor_id=None,
        corridors=corridors,
        decision_trace=decision_trace,
        terminal_stop_requested=True,
        terminal_stop_reason="dig_area_depleted",
    )
    assert status.corridors is not corridors
    assert status.decision_trace is not decision_trace
    assert status.corridors[0] is corridors[0]
    assert status.decision_trace[0] is decision_trace[0]


def test_coverage_report_service_projects_summary_status() -> None:
    status = CoverageReportService().summary_status(
        selected_corridor_id=12,
        depleted_count=6,
        completed_dump_count=7,
        pass_index=1,
        multi_pass_enabled=True,
        use_env_removed_depth=False,
        candidate_layout="corridor_grid",
        first_dig_strategy="preferred_corridor",
        first_dig_preferred_corridor_id=None,
        first_dig_max_entry_distance_m=None,
        first_dig_qpos_delta_weight=0.75,
        terminal_stop_requested=True,
        terminal_stop_reason="dig_area_depleted",
    )

    assert status == CoverageSummaryReportStatus(
        selected_corridor_id=12,
        depleted_count=6,
        completed_dump_count=7,
        pass_index=1,
        multi_pass_enabled=True,
        use_env_removed_depth=False,
        candidate_layout="corridor_grid",
        first_dig_strategy="preferred_corridor",
        first_dig_preferred_corridor_id=None,
        first_dig_max_entry_distance_m=None,
        first_dig_qpos_delta_weight=0.75,
        terminal_stop_requested=True,
        terminal_stop_reason="dig_area_depleted",
    )


def test_coverage_report_service_projects_summary_status_from_runtime_state() -> None:
    policy = _coverage_planner_policy(dig_policy=_RecordingPolicy(0))
    policy._ensure_coverage_corridors()
    corridor = policy._coverage_corridors[0]
    policy._coverage_active_corridor_id = int(corridor.corridor_id)
    policy._coverage_completed_dump_count = 4
    policy._coverage_terminal_stop_requested = True
    policy._coverage_terminal_stop_reason = "dig_area_depleted"

    status = CoverageReportService().summary_status_from_state(
        policy._coverage_runtime_state(),
        config=_coverage_report_config(policy),
    )

    _assert_nested_equal(
        status,
        policy._rollout_summary_inputs().coverage,
    )


def test_coverage_report_service_projects_trace_status_from_runtime_state() -> None:
    policy = _coverage_planner_policy(dig_policy=_RecordingPolicy(0))
    policy._ensure_coverage_corridors()
    policy._record_coverage_decision_event(
        "unit_trace",
        corridor=policy._coverage_corridors[0],
        extra={"reason": "unit_test"},
    )

    status = CoverageReportService().trace_status_from_state(
        policy._coverage_runtime_state(),
        config=_coverage_report_config(policy),
        selection_service=policy._coverage_selection_service(),
    )

    _assert_nested_equal(status, policy._planner_trace_inputs().coverage)
    assert status.decision_trace is not policy._coverage_decision_trace
    assert status.decision_trace[0] is policy._coverage_decision_trace[0]
