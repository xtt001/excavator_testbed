from __future__ import annotations

import inspect

import numpy as np

from testbed.planner.primitive.coverage.config import PrimitiveCoverageStaticConfig
from testbed.planner.primitive.coverage.effect_runtime import (
    PrimitiveCoverageEffectRuntime,
    PrimitiveCoverageEffectRuntimePorts,
)
from testbed.planner.primitive.coverage.report_runtime import (
    PrimitiveCoverageReportRuntime,
    PrimitiveCoverageReportRuntimePorts,
)
from testbed.planner.primitive.coverage.selection_runtime import (
    PrimitiveCoverageSelectionRuntime,
    PrimitiveCoverageSelectionRuntimePorts,
)
from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.execution.cycle_state import PrimitiveCycleRuntimeState
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def _static_config() -> PrimitiveCoverageStaticConfig:
    return PrimitiveCoverageStaticConfig(
        dig_cut_prior={
            "fields": {
                "cut_depth_peak_m": {"p50": 0.45},
                "payload_gain_kg": {"p50": 5.0},
            }
        },
        dig_cut_prior_path="configs/prior.json",
        dig_cut_planner_mode="operator_prior_coverage",
        action_dim=4,
        candidate_layout="cell_weighted_3x2",
        entry_x_percentiles=("p05", "p50", "p95"),
        entry_z_percentiles=("p10", "p50", "p90"),
        cut_direction_percentile="p50",
        cut_length_percentile="p75",
        cut_depth_percentile="p95",
        payload_percentile="p50",
        use_env_removed_depth=True,
        max_attempts_per_corridor=3,
        recent_selection_penalty=0.25,
        unattempted_bonus=1.5,
        attempt_penalty=0.5,
        cell_confidence_weight=0.75,
        rare_cell_source_fraction_threshold=0.125,
        rare_cell_max_attempts=2,
        recent_row_selection_penalty=0.33,
        first_dig_strategy="preferred_corridor",
        first_dig_preferred_corridor_id=4,
        first_dig_preferred_bonus=2.5,
        first_dig_proximity_weight=0.8,
        first_dig_max_entry_distance_m=0.42,
        first_dig_qpos_delta_weight=1.25,
        first_dig_max_qpos_delta=np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
        pre_dig_align_controlled_dims=np.asarray([True, False, True, False]),
        state_exemplars_enabled=True,
        state_exemplar_path="state-exemplars.json",
        state_exemplar_k=5,
        state_exemplar_removed_depth_scale_m=0.6,
        state_exemplar_target_cell_weight=1.7,
        state_exemplar_temperature=0.9,
        state_exemplar_skip_rejected=True,
        state_exemplar_score_weight=0.45,
        state_exemplars_by_cell={2: [{"exemplar_id": "cell2"}]},
        multi_pass_enabled=True,
        multi_pass_max_passes=4,
        multi_pass_min_remaining_depth_m=0.09,
        low_productivity_payload_kg=12.0,
        low_productivity_deposit_kg=3.5,
        deplete_after_low_streak=2,
        min_remaining_depth_m=0.03,
        belief_depleted_score=0.85,
        belief_gain_scale=0.4,
        global_low_productivity_stop=6,
    )


def test_static_config_builds_existing_coverage_config_values() -> None:
    config = _static_config()
    state = CoverageRuntimeState()
    state.coverage_last_selected_corridor_id = 9
    state.coverage_completed_dump_count = 7

    report = config.report_config()
    selection = config.selection_config(state, cycle_index=11)
    planning = config.planning_fact_config()
    exemplar = config.state_exemplar_planner_config()
    update = config.update_config()
    runtime = config.runtime_config()

    assert report.state_exemplar_enabled is True
    assert report.multi_pass_enabled is True
    assert report.multi_pass_max_passes == 4
    assert report.multi_pass_min_remaining_depth_m == 0.09
    assert report.use_env_removed_depth is True
    assert report.candidate_layout == "cell_weighted_3x2"
    assert report.first_dig_strategy == "preferred_corridor"
    assert report.first_dig_preferred_corridor_id == 4
    assert report.first_dig_max_entry_distance_m == 0.42
    assert report.first_dig_qpos_delta_weight == 1.25
    np.testing.assert_array_equal(
        report.first_dig_max_qpos_delta,
        np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
    )

    assert selection.prior_fields == config.dig_cut_prior["fields"]
    assert selection.cut_depth_percentile == "p95"
    assert selection.max_attempts_per_corridor == 3
    assert selection.rare_cell_max_attempts == 2
    assert selection.last_selected_corridor_id == 9
    assert selection.cycle_index == 11
    assert selection.completed_dump_count == 7
    assert selection.first_dig_preferred_bonus == 2.5
    assert selection.first_dig_proximity_weight == 0.8
    np.testing.assert_array_equal(
        selection.pre_dig_align_controlled_dims,
        np.asarray([True, False, True, False]),
    )
    assert selection.state_exemplars_enabled is True
    assert selection.state_exemplar_score_weight == 0.45

    assert planning.prior_fields == config.dig_cut_prior["fields"]
    assert planning.cut_direction_percentile == "p50"
    assert planning.cut_length_percentile == "p75"
    assert planning.cut_depth_percentile == "p95"
    assert planning.payload_percentile == "p50"

    assert exemplar.enabled is True
    assert exemplar.path == "state-exemplars.json"
    assert exemplar.dig_cut_prior_path == "configs/prior.json"
    assert exemplar.k == 5
    assert exemplar.skip_rejected is True

    assert update.prior_fields == config.dig_cut_prior["fields"]
    assert update.low_productivity_payload_kg == 12.0
    assert update.low_productivity_deposit_kg == 3.5
    assert update.deplete_after_low_streak == 2
    assert update.belief_depleted_score == 0.85
    assert update.belief_gain_scale == 0.4

    assert runtime.multi_pass_enabled is True
    assert runtime.use_env_removed_depth is True
    assert runtime.multi_pass_max_passes == 4
    assert runtime.multi_pass_min_remaining_depth_m == 0.09


def test_coverage_runtimes_read_static_config_object() -> None:
    config = _static_config()
    state = CoverageRuntimeState()
    cycle_state = PrimitiveCycleRuntimeState()

    report_runtime = PrimitiveCoverageReportRuntime.from_ports(
        PrimitiveCoverageReportRuntimePorts(
            state=state,
            static_config=config,
            cycle_index=lambda: 3,
            skill_name=lambda: "dig",
            observation_facts=lambda obs: obs["facts"],
            selection_service=lambda: None,  # type: ignore[return-value]
        )
    )
    selection_runtime = PrimitiveCoverageSelectionRuntime.from_ports(
        PrimitiveCoverageSelectionRuntimePorts(
            state=state,
            static_config=config,
            cycle_index=lambda: 3,
            observation_facts=lambda obs: obs["facts"],
            maybe_reopen_pass=lambda obs, reason: False,
            request_terminal_stop=lambda reason: None,
            record_decision_event=lambda *args, **kwargs: None,
        )
    )
    effect_runtime = PrimitiveCoverageEffectRuntime.from_ports(
        PrimitiveCoverageEffectRuntimePorts(
            state=state,
            cycle_state=cycle_state,
            static_config=config,
            observation_facts=lambda obs: obs["facts"],
            remaining_depth=lambda obs, corridor: 0.0,
            corridor_attempt_limit=lambda corridor: 1,
            record_decision_event=lambda *args, **kwargs: None,
        )
    )

    report_config = report_runtime.report_config()
    expected_report_config = config.report_config()
    assert report_config.candidate_layout == expected_report_config.candidate_layout
    assert report_config.multi_pass_max_passes == expected_report_config.multi_pass_max_passes
    np.testing.assert_array_equal(
        report_config.first_dig_max_qpos_delta,
        expected_report_config.first_dig_max_qpos_delta,
    )

    selection_config = selection_runtime.coverage_selection_config()
    expected_selection_config = config.selection_config(state, cycle_index=3)
    assert selection_config.candidate_layout == expected_selection_config.candidate_layout
    assert selection_config.cycle_index == expected_selection_config.cycle_index
    assert (
        selection_config.first_dig_qpos_delta_weight
        == expected_selection_config.first_dig_qpos_delta_weight
    )
    np.testing.assert_array_equal(
        selection_config.pre_dig_align_controlled_dims,
        expected_selection_config.pre_dig_align_controlled_dims,
    )
    assert (
        selection_runtime.coverage_planning_fact_config()
        == config.planning_fact_config()
    )
    assert (
        selection_runtime.coverage_state_exemplar_planner_config()
        == config.state_exemplar_planner_config()
    )
    assert effect_runtime.coverage_update_config() == config.update_config()
    assert effect_runtime.coverage_runtime_config() == config.runtime_config()


def test_policy_keeps_static_coverage_fields_in_one_factory_weld() -> None:
    static_body = inspect.getsource(
        PrimitivePlannerACTPolicy._primitive_coverage_static_config
    )
    assert "self.coverage_candidate_layout" in static_body
    assert "self.dig_cut_prior" in static_body

    port_methods = [
        PrimitivePlannerACTPolicy._primitive_coverage_report_runtime_ports,
        PrimitivePlannerACTPolicy._primitive_coverage_selection_runtime_ports,
        PrimitivePlannerACTPolicy._primitive_coverage_effect_runtime_ports,
    ]
    forbidden_static_reads = (
        "self.coverage_candidate_layout",
        "self.coverage_entry_x_percentiles",
        "self.coverage_low_productivity_payload_kg",
        "self.coverage_multi_pass_enabled",
        "self.dig_cut_prior",
        "self.dig_cut_planner_mode",
    )
    for method in port_methods:
        body = inspect.getsource(method)
        assert "static_config=self._primitive_coverage_static_config()" in body
        for forbidden in forbidden_static_reads:
            assert forbidden not in body
