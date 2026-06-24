from __future__ import annotations

from math import isnan
from typing import Any

import numpy as np

from testbed.data.schema import (
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX,
)
from testbed.planner.primitive.facts.capabilities import PrimitiveObservationFacts
from testbed.planner.primitive.coverage.reports import (
    CoverageBucketSnapshot,
    CoverageDebugReportInputs,
    CoverageReportConfig,
    CoverageReportService,
    CoverageSummaryReportStatus,
    CoverageTraceReportStatus,
)
from testbed.planner.primitive.coverage.report_runtime import (
    PrimitiveCoverageReportRuntime,
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
    runtime = _coverage_report_runtime(policy)
    active_corridor = runtime.active_corridor()
    return CoverageDebugReportInputs(
        active_corridor_id=policy._coverage_runtime_state().coverage_active_corridor_id,
        last_selected_corridor_id=policy._coverage_runtime_state().coverage_last_selected_corridor_id,
        last_selected_cell_id=runtime.corridor_cell_id_by_id(
            policy._coverage_runtime_state().coverage_last_selected_corridor_id
        ),
        last_selected_row_id=runtime.corridor_row_id_by_id(
            policy._coverage_runtime_state().coverage_last_selected_corridor_id
        ),
        active_corridor=(
            None
            if active_corridor is None
            else runtime.corridor_to_debug(active_corridor)
        ),
        active_cell_id=runtime.active_cell_id(),
        active_score=runtime.active_corridor_score(),
        state_exemplar_enabled=policy.coverage_state_exemplars_enabled,
        state_exemplar_ids=policy._coverage_runtime_state().coverage_active_state_exemplar_ids,
        state_exemplar_distance=policy._coverage_runtime_state().coverage_active_state_exemplar_distance,
        depleted_count=runtime.depleted_count(),
        pass_index=policy._coverage_runtime_state().coverage_pass_index,
        multi_pass_enabled=policy.coverage_multi_pass_enabled,
        multi_pass_max_passes=policy.coverage_multi_pass_max_passes,
        multi_pass_min_remaining_depth_m=(
            policy.coverage_multi_pass_min_remaining_depth_m
        ),
        last_payload_gain_kg=policy._coverage_runtime_state().coverage_last_payload_gain_kg,
        last_effective_deposit_delta_kg=(
            policy._coverage_runtime_state().coverage_last_effective_deposit_delta_kg
        ),
        global_low_productivity_streak=(
            policy._coverage_runtime_state().coverage_global_low_productivity_streak
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
        terminal_stop_requested=policy._coverage_runtime_state().coverage_terminal_stop_requested,
        terminal_stop_reason=policy._coverage_runtime_state().coverage_terminal_stop_reason,
        corridors=[
            runtime.corridor_to_debug(corridor)
            for corridor in policy._coverage_runtime_state().coverage_corridors
        ],
        candidate_scores=policy._coverage_runtime_state().coverage_candidate_scores,
    )


def _coverage_report_config(policy: Any) -> CoverageReportConfig:
    return policy._primitive_coverage_report_runtime().report_config()


def _coverage_report_runtime(policy: Any) -> PrimitiveCoverageReportRuntime:
    return policy._primitive_coverage_report_runtime()


def test_policy_exposes_focused_coverage_report_runtime_without_old_glue() -> None:
    policy = _coverage_planner_policy(dig_policy=_RecordingPolicy(0))
    old_names = {
        f"_coverage_{name}"
        for name in (
            "report_service",
            "report_config",
            "report_state",
            "bucket_snapshot",
            "all_depleted",
            "active_corridor",
            "corridor_by_id",
            "active_corridor_score",
            "active_value",
            "active_cell_id",
            "corridor_cell_id_by_id",
            "corridor_row_id_by_id",
            "depleted_count",
            "corridor_to_debug",
            "percentile_list",
            "percentile_name",
        )
    } | {"_record_coverage_decision_event"}

    assert isinstance(
        _coverage_report_runtime(policy),
        PrimitiveCoverageReportRuntime,
    )
    assert old_names.isdisjoint(policy.__class__.__dict__)


def _env_state_with_bucket_values() -> np.ndarray:
    env_state = np.zeros(
        max(
            ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX,
            ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX,
            ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX,
            ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX,
            ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX,
            ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
            ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
        )
        + 1,
        dtype=np.float32,
    )
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX] = 1.25
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX] = -0.5
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX] = 2.5
    env_state[ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX] = 0.75
    env_state[ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX] = 0.35
    env_state[ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX] = 0.42
    env_state[ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX] = 0.18
    return env_state


def test_coverage_report_service_projects_bucket_snapshot_from_observation_facts() -> None:
    obs = {
        "env_state": _env_state_with_bucket_values(),
        "task_metrics": {
            "mass_in_bucket_kg": 3.5,
            "deposited_mass_in_target_box_kg": 2.25,
        },
    }
    facts = PrimitiveObservationFacts.from_obs(obs, action_dim=4)

    snapshot = CoverageReportService().bucket_snapshot(facts)

    _assert_nested_equal(
        snapshot.__dict__,
        CoverageBucketSnapshot(
        mass_kg=3.5,
        deposited_mass_kg=2.25,
        dig_area_x_m=1.25,
        dig_area_y_m=-0.5,
        dig_area_z_m=2.5,
        long_norm=0.75,
        short_norm=0.35,
        plane_depth_m=0.42,
        local_depth_m=0.18,
        ).__dict__,
    )


def test_coverage_report_service_bucket_snapshot_preserves_nan_and_default_fallbacks() -> None:
    facts = PrimitiveObservationFacts.from_obs({"env_state": np.zeros(3)}, action_dim=4)

    snapshot = CoverageReportService().bucket_snapshot(facts)

    assert snapshot.mass_kg == 0.0
    assert snapshot.deposited_mass_kg == 0.0
    assert isnan(snapshot.dig_area_x_m)
    assert isnan(snapshot.dig_area_y_m)
    assert isnan(snapshot.dig_area_z_m)
    assert isnan(snapshot.long_norm)
    assert isnan(snapshot.short_norm)
    assert isnan(snapshot.plane_depth_m)
    assert isnan(snapshot.local_depth_m)


def test_coverage_report_runtime_delegates_bucket_snapshot_to_report_service() -> None:
    policy = _coverage_planner_policy(dig_policy=_RecordingPolicy(0))
    obs = {
        "env_state": _env_state_with_bucket_values(),
        "task_metrics": {
            "mass_in_bucket_kg": 4.5,
            "deposited_mass_in_target_box_kg": 1.25,
        },
    }
    service_snapshot = CoverageReportService().bucket_snapshot(
        PrimitiveObservationFacts.from_obs(obs, action_dim=int(policy.action_dim))
    )

    assert _coverage_report_runtime(policy).bucket_snapshot(obs) == service_snapshot


def test_coverage_report_service_matches_runtime_corridor_debug() -> None:
    policy = _coverage_planner_policy(dig_policy=_RecordingPolicy(0))
    policy._primitive_coverage_selection_runtime().ensure_coverage_corridors()
    corridor = policy._coverage_runtime_state().coverage_corridors[0]

    service_payload = CoverageReportService().corridor_to_debug(
        corridor,
        attempt_limit=policy._primitive_coverage_selection_runtime().coverage_corridor_attempt_limit(corridor),
        cell_confidence=policy._primitive_coverage_selection_runtime().coverage_cell_confidence(corridor),
    )

    _assert_nested_equal(
        service_payload,
        _coverage_report_runtime(policy).corridor_to_debug(corridor),
    )


def test_coverage_report_runtime_records_decision_event_payload() -> None:
    policy = _coverage_planner_policy(dig_policy=_RecordingPolicy(0))
    policy._primitive_coverage_selection_runtime().ensure_coverage_corridors()
    corridor = policy._coverage_runtime_state().coverage_corridors[0]
    policy._coverage_runtime_state().coverage_active_corridor_id = int(corridor.corridor_id)
    obs = _coverage_obs(mass=3.0, dig_distance=0.0, deposited=2.0)
    runtime = _coverage_report_runtime(policy)

    service_payload = CoverageReportService().decision_event(
        "unit_event",
        state=runtime.report_state(),
        corridor=runtime.corridor_to_debug(corridor),
        bucket=runtime.bucket_snapshot(obs),
        extra={"reason": "unit_test"},
    )

    runtime.record_decision_event(
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
    policy._primitive_coverage_selection_runtime().ensure_coverage_corridors()
    corridor = policy._coverage_runtime_state().coverage_corridors[0]
    policy._coverage_runtime_state().coverage_active_corridor_id = int(corridor.corridor_id)
    policy._coverage_runtime_state().coverage_last_selected_corridor_id = int(corridor.corridor_id)

    service_payload = CoverageReportService().debug_fields(
        _coverage_debug_report_inputs(policy)
    )

    _assert_nested_equal(
        service_payload,
        policy._primitive_report_composition_runtime().report_runtime().debug_report_coverage_fields(),
    )


def test_coverage_report_service_matches_debug_fields_without_active_corridor() -> None:
    policy = _coverage_planner_policy(dig_policy=_RecordingPolicy(0))

    service_payload = CoverageReportService().debug_fields(
        _coverage_debug_report_inputs(policy)
    )

    _assert_nested_equal(
        service_payload,
        policy._primitive_report_composition_runtime().report_runtime().debug_report_coverage_fields(),
    )
    assert service_payload["coverage_corridor_id"] == -1
    assert service_payload["coverage_selected_corridor_id"] == -1
    assert service_payload["coverage_last_selected_cell_id"] == -1
    assert service_payload["coverage_last_selected_row_id"] == -1
    assert isnan(float(service_payload["coverage_entry_x_m"]))
    assert isnan(float(service_payload["coverage_corridor_score"]))


def test_coverage_report_service_projects_debug_fields_from_runtime_state() -> None:
    policy = _coverage_planner_policy(dig_policy=_RecordingPolicy(0))
    policy._primitive_coverage_selection_runtime().ensure_coverage_corridors()
    corridor = policy._coverage_runtime_state().coverage_corridors[0]
    policy._coverage_runtime_state().coverage_active_corridor_id = int(corridor.corridor_id)
    policy._coverage_runtime_state().coverage_last_selected_corridor_id = int(corridor.corridor_id)

    service_payload = CoverageReportService().debug_fields_from_state(
        policy._coverage_runtime_state(),
        config=_coverage_report_config(policy),
        selection_service=policy._primitive_coverage_selection_runtime().coverage_selection_service(),
    )

    _assert_nested_equal(
        service_payload,
        policy._primitive_report_composition_runtime().report_runtime().debug_report_coverage_fields(),
    )


def test_coverage_report_service_projects_empty_debug_fields_from_runtime_state() -> None:
    policy = _coverage_planner_policy(dig_policy=_RecordingPolicy(0))

    service_payload = CoverageReportService().debug_fields_from_state(
        policy._coverage_runtime_state(),
        config=_coverage_report_config(policy),
        selection_service=policy._primitive_coverage_selection_runtime().coverage_selection_service(),
    )

    _assert_nested_equal(
        service_payload,
        policy._primitive_report_composition_runtime().report_runtime().debug_report_coverage_fields(),
    )
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
    policy._primitive_coverage_selection_runtime().ensure_coverage_corridors()
    corridor = policy._coverage_runtime_state().coverage_corridors[0]
    policy._coverage_runtime_state().coverage_active_corridor_id = int(corridor.corridor_id)
    policy._coverage_runtime_state().coverage_completed_dump_count = 4
    policy._coverage_runtime_state().coverage_terminal_stop_requested = True
    policy._coverage_runtime_state().coverage_terminal_stop_reason = "dig_area_depleted"

    status = CoverageReportService().summary_status_from_state(
        policy._coverage_runtime_state(),
        config=_coverage_report_config(policy),
    )

    _assert_nested_equal(
        status,
        policy._primitive_report_composition_runtime().report_runtime().rollout_summary_inputs().coverage,
    )


def test_coverage_report_service_projects_trace_status_from_runtime_state() -> None:
    policy = _coverage_planner_policy(dig_policy=_RecordingPolicy(0))
    policy._primitive_coverage_selection_runtime().ensure_coverage_corridors()
    _coverage_report_runtime(policy).record_decision_event(
        "unit_trace",
        corridor=policy._coverage_runtime_state().coverage_corridors[0],
        extra={"reason": "unit_test"},
    )

    status = CoverageReportService().trace_status_from_state(
        policy._coverage_runtime_state(),
        config=_coverage_report_config(policy),
        selection_service=policy._primitive_coverage_selection_runtime().coverage_selection_service(),
    )

    _assert_nested_equal(
        status,
        policy._primitive_report_composition_runtime().report_runtime().planner_trace_inputs().coverage,
    )
    assert status.decision_trace is not policy._coverage_runtime_state().coverage_decision_trace
    assert status.decision_trace[0] is policy._coverage_runtime_state().coverage_decision_trace[0]
