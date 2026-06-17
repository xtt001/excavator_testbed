from __future__ import annotations

import ast
import importlib
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from testbed.data.operator_first_v2_2 import DIG_CUT_DEPTH_SCALE_M
from testbed.data.schema import (
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
    ENV_STATE_DIG_AREA_TARGET_DEPTH_START_IDX,
)
from testbed.planner.dig_coverage import (
    COVERAGE_OBSERVATION_FACT_FIELDS,
    COVERAGE_SERVICE_CONFIG_FIELDS,
    CoverageActiveStateExemplarState,
    CoverageCorridorState,
    CoverageObservationFacts,
    CoverageService,
    CoverageServiceConfig,
    CoverageServiceState,
    DigCoverageMixin,
    build_coverage_context_facts_from_mapping,
    build_coverage_observation_facts_from_mapping,
    build_coverage_service_config_from_mapping,
)
from testbed.planner.dig_coverage.base import CoverageServiceBase
from testbed.planner.dig_coverage.raw_fields import CoverageRawFieldsMixin
from testbed.planner.dig_coverage.scoring import CoverageScoringMixin
from testbed.planner.dig_coverage.snapshots import CoverageSnapshotMixin
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy

REPO_ROOT = Path(__file__).resolve().parents[1]
YULONG_DIG_CUT_PRIOR_PATH = (
    REPO_ROOT
    / "testbed/configs/planner_priors/yulong_operator_first_dig_cut_prior_v1.json"
)
YULONG_REMOVED_DEPTH_DIG_CUT_PRIOR_V3_PATH = (
    REPO_ROOT
    / "testbed/configs/planner_priors/yulong_removed_depth_dig_cut_prior_v3.json"
)


def test_coverage_private_methods_are_service_facades() -> None:
    policy = _coverage_policy()

    assert (
        PrimitivePlannerACTPolicy._ensure_coverage_corridors
        is DigCoverageMixin._ensure_coverage_corridors
    )
    assert (
        PrimitivePlannerACTPolicy._select_coverage_corridor
        is DigCoverageMixin._select_coverage_corridor
    )
    assert (
        PrimitivePlannerACTPolicy._coverage_raw_fields
        is DigCoverageMixin._coverage_raw_fields
    )
    assert (
        PrimitivePlannerACTPolicy._coverage_percentile_list
        is DigCoverageMixin._coverage_percentile_list
    )
    assert (
        PrimitivePlannerACTPolicy._coverage_percentile_name
        is DigCoverageMixin._coverage_percentile_name
    )
    assert (
        PrimitivePlannerACTPolicy._prior_percentile
        is DigCoverageMixin._prior_percentile
    )
    assert (
        PrimitivePlannerACTPolicy._clamp_to_prior
        is DigCoverageMixin._clamp_to_prior
    )
    assert (
        PrimitivePlannerACTPolicy._raw_fields_in_prior_range
        is DigCoverageMixin._raw_fields_in_prior_range
    )
    assert (
        PrimitivePlannerACTPolicy._complete_coverage_dump
        is DigCoverageMixin._complete_coverage_dump
    )
    assert (
        PrimitivePlannerACTPolicy._reject_active_coverage_corridor
        is DigCoverageMixin._reject_active_coverage_corridor
    )
    assert isinstance(policy.coverage_service, CoverageService)
    assert policy._coverage_service() is policy.coverage_service

    policy._ensure_coverage_corridors()

    assert policy._coverage_corridors is policy.coverage_service.state.corridors
    assert (
        policy._coverage_corridor_to_debug(policy._coverage_corridors[0])
        == policy.coverage_service.corridor_debug(policy._coverage_corridors[0])
    )
    assert (
        PrimitivePlannerACTPolicy._coverage_trace_snapshot
        is DigCoverageMixin._coverage_trace_snapshot
    )
    assert (
        PrimitivePlannerACTPolicy._coverage_rollout_summary_snapshot
        is DigCoverageMixin._coverage_rollout_summary_snapshot
    )
    assert (
        PrimitivePlannerACTPolicy._clear_coverage_active_state_exemplar
        is DigCoverageMixin._clear_coverage_active_state_exemplar
    )


def test_coverage_service_internals_use_observation_facts_boundary() -> None:
    service_paths = [
        REPO_ROOT / "testbed/planner/dig_coverage/base.py",
        REPO_ROOT / "testbed/planner/dig_coverage/candidates.py",
        REPO_ROOT / "testbed/planner/dig_coverage/progress.py",
        REPO_ROOT / "testbed/planner/dig_coverage/raw_fields.py",
        REPO_ROOT / "testbed/planner/dig_coverage/scoring.py",
        REPO_ROOT / "testbed/planner/dig_coverage/selection.py",
        REPO_ROOT / "testbed/planner/dig_coverage/state_exemplars.py",
    ]
    offenders: list[str] = []
    forbidden_type_fragments = (
        "CoverageObservationFacts | dict",
        "dict | CoverageObservationFacts",
        "facts: dict",
    )
    for path in service_paths:
        source = path.read_text()
        tree = ast.parse(source)
        rel_path = path.relative_to(REPO_ROOT)
        for fragment in forbidden_type_fragments:
            if fragment in source:
                offenders.append(f"{rel_path}:forbidden-fragment:{fragment}")
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            args = [
                *node.args.posonlyargs,
                *node.args.args,
                *node.args.kwonlyargs,
            ]
            if any(arg.arg == "obs" for arg in args):
                offenders.append(f"{rel_path}:{node.lineno}:{node.name}")

    assert offenders == []


def test_coverage_snapshot_methods_have_focused_source_of_truth() -> None:
    assert (
        CoverageService.coverage_debug_snapshot
        is CoverageSnapshotMixin.coverage_debug_snapshot
    )
    assert (
        CoverageService.coverage_trace_snapshot
        is CoverageSnapshotMixin.coverage_trace_snapshot
    )
    assert (
        CoverageService.coverage_rollout_summary_snapshot
        is CoverageSnapshotMixin.coverage_rollout_summary_snapshot
    )
    assert (
        CoverageService._coverage_corridor_to_debug
        is CoverageSnapshotMixin._coverage_corridor_to_debug
    )


def test_coverage_scoring_methods_have_focused_source_of_truth() -> None:
    assert CoverageService._coverage_score is CoverageScoringMixin._coverage_score
    assert (
        CoverageService._coverage_first_dig_gate_available
        is CoverageScoringMixin._coverage_first_dig_gate_available
    )
    assert (
        CoverageService._coverage_first_dig_bonus
        is CoverageScoringMixin._coverage_first_dig_bonus
    )
    assert (
        CoverageService._coverage_corridor_attempt_limit
        is CoverageScoringMixin._coverage_corridor_attempt_limit
    )
    assert (
        CoverageService._coverage_rare_first_dig_gated_out
        is CoverageScoringMixin._coverage_rare_first_dig_gated_out
    )
    assert (
        CoverageService._pre_dig_align_target_from_token
        is CoverageScoringMixin._pre_dig_align_target_from_token
    )


def test_coverage_state_lookup_methods_have_base_source_of_truth() -> None:
    assert (
        CoverageService._coverage_all_depleted
        is CoverageServiceBase._coverage_all_depleted
    )
    assert (
        CoverageService._coverage_active_corridor
        is CoverageServiceBase._coverage_active_corridor
    )
    assert (
        CoverageService._coverage_corridor_by_id
        is CoverageServiceBase._coverage_corridor_by_id
    )
    assert (
        CoverageService._coverage_active_corridor_score
        is CoverageServiceBase._coverage_active_corridor_score
    )
    assert (
        CoverageService._coverage_active_value
        is CoverageServiceBase._coverage_active_value
    )
    assert (
        CoverageService._coverage_active_cell_id
        is CoverageServiceBase._coverage_active_cell_id
    )
    assert (
        CoverageService._coverage_corridor_cell_id_by_id
        is CoverageServiceBase._coverage_corridor_cell_id_by_id
    )
    assert (
        CoverageService._coverage_corridor_row_id_by_id
        is CoverageServiceBase._coverage_corridor_row_id_by_id
    )
    assert (
        CoverageService._coverage_depleted_count
        is CoverageServiceBase._coverage_depleted_count
    )
    assert CoverageService._coverage_cell_id is CoverageServiceBase._coverage_cell_id
    assert (
        CoverageService._coverage_corridor_row_id
        is CoverageServiceBase._coverage_corridor_row_id
    )
    assert (
        CoverageService._coverage_cell_id_from_percentile_indices
        is CoverageServiceBase._coverage_cell_id_from_percentile_indices
    )
    assert (
        CoverageService._coverage_remaining_depth_for_corridor
        is CoverageServiceBase._coverage_remaining_depth_for_corridor
    )


def test_coverage_raw_field_prior_range_has_raw_fields_source_of_truth() -> None:
    assert (
        CoverageService.raw_fields_in_prior_range
        is CoverageRawFieldsMixin.raw_fields_in_prior_range
    )


def test_coverage_decision_trace_event_methods_have_base_source_of_truth() -> None:
    assert (
        CoverageService._record_coverage_decision_event
        is CoverageServiceBase._record_coverage_decision_event
    )
    assert CoverageService._env_state_value is CoverageServiceBase._env_state_value


def test_coverage_state_exemplar_methods_have_focused_source_of_truth() -> None:
    module = importlib.import_module("testbed.planner.dig_coverage.state_exemplars")
    state_exemplar_mixin = module.CoverageStateExemplarMixin

    assert (
        CoverageService._load_coverage_state_exemplars
        is state_exemplar_mixin._load_coverage_state_exemplars
    )
    assert (
        CoverageService._coverage_state_conditioned_plan
        is state_exemplar_mixin._coverage_state_conditioned_plan
    )
    assert (
        CoverageService._coverage_state_exemplar_distance
        is state_exemplar_mixin._coverage_state_exemplar_distance
    )
    assert (
        CoverageService._coverage_state_exemplar_id
        is state_exemplar_mixin._coverage_state_exemplar_id
    )
    assert (
        CoverageService._coverage_removed_depth_grid
        is state_exemplar_mixin._coverage_removed_depth_grid
    )
    assert (
        CoverageService._coverage_state_exemplar_distance_for_grid
        is state_exemplar_mixin._coverage_state_exemplar_distance_for_grid
    )
    assert (
        CoverageService._state_exemplar_weights
        is state_exemplar_mixin._state_exemplar_weights
    )
    assert (
        CoverageService._weighted_state_exemplar_raw_fields
        is state_exemplar_mixin._weighted_state_exemplar_raw_fields
    )
    assert (
        CoverageService._weighted_state_exemplar_profile_token
        is state_exemplar_mixin._weighted_state_exemplar_profile_token
    )


def test_coverage_service_initial_runtime_state_preserves_legacy_reset_defaults() -> None:
    state = CoverageService.initial_runtime_state()

    assert isinstance(state, CoverageServiceState)
    assert state.corridors == []
    assert state.active_corridor_id == -1
    assert state.last_selected_corridor_id == -1
    assert state.current_payload_gain_kg == 0.0
    assert state.cycle_start_deposit_kg == 0.0
    assert state.last_payload_gain_kg == 0.0
    assert state.last_effective_deposit_delta_kg == 0.0
    assert state.global_low_productivity_streak == 0
    assert state.completed_dump_count == 0
    assert state.pass_index == 0
    assert state.terminal_stop_requested is False
    assert state.terminal_stop_reason == ""
    assert state.candidate_scores == []
    assert state.decision_trace == []
    assert state.active_state_exemplar_ids == []
    assert state.rejected_state_exemplar_ids == set()
    assert np.isnan(state.active_state_exemplar_distance)
    assert state.active_state_exemplar_profile_token is None


def test_coverage_service_config_mapping_preserves_legacy_projection() -> None:
    prior = {"dig_cut": {"token": [1.0]}}
    exemplars = {2: [{"id": "cell2"}]}
    values = {
        "dig_cut_planner_mode": 123,
        "dig_cut_prior": prior,
        "dig_cut_prior_path": 456,
        "action_dim": "4",
        "candidate_layout": "cell_weighted_3x2",
        "use_env_removed_depth": 1,
        "belief_gain_scale": "0.55",
        "belief_depleted_score": "1.0",
        "low_productivity_payload_kg": "15.0",
        "low_productivity_deposit_kg": "16.0",
        "deplete_after_low_streak": "2",
        "min_remaining_depth_m": "0.05",
        "global_low_productivity_stop": "3",
        "max_attempts_per_corridor": "4",
        "multi_pass_enabled": 1,
        "multi_pass_max_passes": "5",
        "multi_pass_min_remaining_depth_m": "0.06",
        "unattempted_bonus": "2.0",
        "attempt_penalty": "0.65",
        "recent_selection_penalty": "1.25",
        "recent_row_selection_penalty": "0.5",
        "rare_cell_source_fraction_threshold": "0.05",
        "rare_cell_max_attempts": "1",
        "cell_confidence_weight": "0.75",
        "state_exemplars_enabled": 1,
        "state_exemplar_path": 789,
        "state_exemplar_k": "6",
        "state_exemplar_removed_depth_scale_m": "0.12",
        "state_exemplar_target_cell_weight": "2.0",
        "state_exemplar_score_weight": "0.75",
        "state_exemplar_temperature": "0.35",
        "state_exemplar_skip_rejected": 0,
        "state_exemplars_by_cell": exemplars,
        "first_dig_strategy": "nearest_entry",
        "first_dig_preferred_corridor_id": "7",
        "first_dig_preferred_bonus": "10000.0",
        "first_dig_proximity_weight": "100.0",
        "first_dig_max_entry_distance_m": "0.75",
        "first_dig_qpos_delta_weight": "0.5",
        "first_dig_max_qpos_delta": [0.1, 0.2, 0.3, 0.4],
        "first_dig_alignment_enabled": 1,
        "first_dig_controlled_dims": [1, 0, 1, 0],
        "entry_x_percentiles": ["p10", "p50", "p90"],
        "entry_z_percentiles": ["p05", "p50", "p95"],
        "cut_direction_percentile": "p50",
        "cut_length_percentile": "p75",
        "cut_depth_percentile": "p90",
        "payload_percentile": "p95",
    }

    config = build_coverage_service_config_from_mapping(values)

    assert isinstance(config, CoverageServiceConfig)
    assert {key for key, _ in COVERAGE_SERVICE_CONFIG_FIELDS} == set(values)
    assert config.dig_cut_planner_mode == "123"
    assert config.dig_cut_prior == prior
    assert config.dig_cut_prior is not prior
    assert config.dig_cut_prior_path == "456"
    assert config.action_dim == 4
    assert config.candidate_layout == "cell_weighted_3x2"
    assert config.use_env_removed_depth is True
    assert config.multi_pass_enabled is True
    assert config.multi_pass_max_passes == 5
    assert config.state_exemplars_enabled is True
    assert config.state_exemplar_path == "789"
    assert config.state_exemplars_by_cell == exemplars
    assert config.state_exemplars_by_cell is not exemplars
    assert config.state_exemplar_skip_rejected is False
    assert config.first_dig_preferred_corridor_id == 7
    assert config.first_dig_max_entry_distance_m == 0.75
    np.testing.assert_allclose(
        config.first_dig_max_qpos_delta,
        np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
    )
    assert config.first_dig_max_qpos_delta.dtype == np.float32
    np.testing.assert_array_equal(
        config.first_dig_controlled_dims,
        np.asarray([True, False, True, False], dtype=bool),
    )
    assert config.entry_x_percentiles == ("p10", "p50", "p90")
    assert config.entry_z_percentiles == ("p05", "p50", "p95")
    assert config.payload_percentile == "p95"

    missing_exemplars_values = dict(values)
    missing_exemplars_values.pop("state_exemplars_by_cell")
    missing_exemplars_config = build_coverage_service_config_from_mapping(
        missing_exemplars_values
    )
    assert missing_exemplars_config.state_exemplars_by_cell == {}

    optional_none_values = {
        **values,
        "first_dig_preferred_corridor_id": None,
        "first_dig_max_entry_distance_m": None,
        "first_dig_max_qpos_delta": None,
    }
    optional_none_config = build_coverage_service_config_from_mapping(
        optional_none_values
    )
    assert optional_none_config.first_dig_preferred_corridor_id is None
    assert optional_none_config.first_dig_max_entry_distance_m is None
    assert optional_none_config.first_dig_max_qpos_delta is None


def test_coverage_observation_facts_mapping_preserves_legacy_projection() -> None:
    env_state = np.asarray([1.0, 2.0, 3.0], dtype=np.float32)
    bucket_pose = (0.1, 0.2, 0.3)
    values = {
        "cycle_index": "7",
        "skill_name": 123,
        "dig_best_mass_kg": "12.5",
    }

    facts = build_coverage_observation_facts_from_mapping(
        values,
        action_dim=4,
        env_state=env_state,
        qpos=np.asarray([[0.5, 0.6], [0.7, 0.8]], dtype=np.float64),
        bucket_tip_dig_area_pose=bucket_pose,
        mass_in_bucket_kg=np.float64(4.5),
        deposited_mass_kg=np.float64(6.5),
    )

    assert isinstance(facts, CoverageObservationFacts)
    assert {key for key, _, _ in COVERAGE_OBSERVATION_FACT_FIELDS} == set(values)
    assert facts.env_state is env_state
    np.testing.assert_allclose(
        facts.qpos,
        np.asarray([0.5, 0.6, 0.7, 0.8], dtype=np.float32),
    )
    assert facts.qpos.dtype == np.float32
    assert facts.bucket_tip_dig_area_pose is bucket_pose
    assert facts.mass_in_bucket_kg == np.float64(4.5)
    assert facts.deposited_mass_kg == np.float64(6.5)
    assert facts.cycle_index == 7
    assert facts.skill_name == "123"
    assert facts.dig_best_mass_kg == 12.5

    missing_qpos_facts = build_coverage_observation_facts_from_mapping(
        values,
        action_dim=4,
        env_state=env_state,
        bucket_tip_dig_area_pose=None,
        mass_in_bucket_kg=0.0,
        deposited_mass_kg=0.0,
    )
    np.testing.assert_array_equal(
        missing_qpos_facts.qpos,
        np.zeros(4, dtype=np.float32),
    )

    with pytest.raises(ValueError):
        build_coverage_observation_facts_from_mapping(
            values,
            action_dim=4,
            env_state=env_state,
            qpos=None,
            bucket_tip_dig_area_pose=None,
            mass_in_bucket_kg=0.0,
            deposited_mass_kg=0.0,
        )


def test_policy_coverage_observation_facts_facade_matches_builder() -> None:
    policy = _coverage_policy()
    policy._cycle_index = 9
    policy._skill_name = "dump"
    policy._dig_best_mass_kg = 18.5
    obs = _coverage_obs(mass=4.5, deposited=6.5, bucket_pose=(0.8, 0.0, 0.5))
    obs["qpos"] = np.asarray([[0.5, 0.6], [0.7, 0.8]], dtype=np.float64)
    values = {
        fact_key: getattr(policy, attr_name, default)
        for fact_key, attr_name, default in COVERAGE_OBSERVATION_FACT_FIELDS
    }

    direct = build_coverage_observation_facts_from_mapping(
        values,
        action_dim=policy.action_dim,
        env_state=policy._env_state(obs),
        qpos=obs["qpos"],
        bucket_tip_dig_area_pose=policy._bucket_tip_dig_area_pose(obs),
        mass_in_bucket_kg=policy._mass_in_bucket(obs),
        deposited_mass_kg=policy._deposited_mass(obs),
    )
    facade = policy._coverage_observation_facts(obs)

    np.testing.assert_array_equal(facade.env_state, direct.env_state)
    np.testing.assert_array_equal(facade.qpos, direct.qpos)
    assert facade.qpos.dtype == np.float32
    assert facade.bucket_tip_dig_area_pose == direct.bucket_tip_dig_area_pose
    assert facade.mass_in_bucket_kg == direct.mass_in_bucket_kg
    assert facade.deposited_mass_kg == direct.deposited_mass_kg
    assert facade.cycle_index == direct.cycle_index == 9
    assert facade.skill_name == direct.skill_name == "dump"
    assert facade.dig_best_mass_kg == direct.dig_best_mass_kg == 18.5

    missing_qpos_obs = dict(obs)
    missing_qpos_obs.pop("qpos")
    missing_qpos_facade = policy._coverage_observation_facts(missing_qpos_obs)
    np.testing.assert_array_equal(
        missing_qpos_facade.qpos,
        np.zeros(policy.action_dim, dtype=np.float32),
    )


def test_coverage_context_facts_mapping_preserves_legacy_defaults() -> None:
    policy = _coverage_policy()
    policy._cycle_index = 11
    policy._skill_name = "return"
    policy._dig_best_mass_kg = 21.0
    values = {
        fact_key: getattr(policy, attr_name, default)
        for fact_key, attr_name, default in COVERAGE_OBSERVATION_FACT_FIELDS
    }

    direct = build_coverage_context_facts_from_mapping(
        values,
        action_dim=policy.action_dim,
    )
    facade = policy._coverage_context_facts()

    assert direct.env_state.dtype == np.float32
    assert direct.env_state.shape == (0,)
    np.testing.assert_array_equal(facade.env_state, direct.env_state)
    np.testing.assert_array_equal(
        facade.qpos,
        np.zeros(policy.action_dim, dtype=np.float32),
    )
    np.testing.assert_array_equal(facade.qpos, direct.qpos)
    assert facade.bucket_tip_dig_area_pose is None
    assert direct.bucket_tip_dig_area_pose is None
    assert facade.mass_in_bucket_kg == direct.mass_in_bucket_kg == 0.0
    assert facade.deposited_mass_kg == direct.deposited_mass_kg == 0.0
    assert facade.cycle_index == direct.cycle_index == 11
    assert facade.skill_name == direct.skill_name == "return"
    assert facade.dig_best_mass_kg == direct.dig_best_mass_kg == 21.0


def test_coverage_service_cleared_active_state_exemplar_preserves_legacy_defaults() -> None:
    state = CoverageService.cleared_active_state_exemplar_state()

    assert isinstance(state, CoverageActiveStateExemplarState)
    assert state.ids == ()
    assert np.isnan(state.distance)
    assert state.profile_token is None


def test_policy_clear_coverage_active_state_exemplar_applies_service_state(
    monkeypatch,
) -> None:
    policy = _coverage_policy()
    profile_token = np.arange(12, dtype=np.float64) + 30.0

    def cleared_active_state_exemplar_state() -> CoverageActiveStateExemplarState:
        return CoverageActiveStateExemplarState(
            ids=("cell7_deep",),
            distance=0.25,
            profile_token=profile_token,
        )

    monkeypatch.setattr(
        policy._coverage_service(),
        "cleared_active_state_exemplar_state",
        cleared_active_state_exemplar_state,
    )

    policy._clear_coverage_active_state_exemplar()
    profile_token[0] = 99.0

    assert policy._coverage_active_state_exemplar_ids == ["cell7_deep"]
    assert policy._coverage_active_state_exemplar_distance == 0.25
    np.testing.assert_allclose(
        policy._coverage_active_state_exemplar_profile_token,
        np.arange(12, dtype=np.float32) + 30.0,
    )
    assert policy._coverage_active_state_exemplar_profile_token.dtype == np.float32


def test_policy_reset_rebuilds_coverage_service_from_initial_runtime_state(
    monkeypatch,
) -> None:
    policy = _coverage_policy()
    corridor = CoverageCorridorState(
        corridor_id=7,
        entry_x_m=0.1,
        entry_z_m=0.2,
        exit_x_m=0.3,
        exit_z_m=0.4,
        cell_id=2,
    )
    profile_token = np.asarray([0.2, 0.4, 0.6], dtype=np.float32)

    def initial_runtime_state() -> CoverageServiceState:
        return CoverageServiceState(
            corridors=[corridor],
            active_corridor_id=7,
            last_selected_corridor_id=6,
            current_payload_gain_kg=12.5,
            cycle_start_deposit_kg=3.0,
            last_payload_gain_kg=9.5,
            last_effective_deposit_delta_kg=4.5,
            global_low_productivity_streak=2,
            completed_dump_count=3,
            pass_index=1,
            terminal_stop_requested=True,
            terminal_stop_reason="unit_terminal",
            candidate_scores=[{"corridor_id": 7, "score": 1.25}],
            decision_trace=[{"event": "unit_trace"}],
            active_state_exemplar_ids=["cell7_deep"],
            rejected_state_exemplar_ids={"cell3_shallow"},
            active_state_exemplar_distance=0.25,
            active_state_exemplar_profile_token=profile_token,
        )

    monkeypatch.setattr(
        CoverageService,
        "initial_runtime_state",
        staticmethod(initial_runtime_state),
    )

    policy.reset()

    assert policy._coverage_corridors == [corridor]
    assert policy._coverage_active_corridor_id == 7
    assert policy._coverage_last_selected_corridor_id == 6
    assert policy._coverage_current_payload_gain_kg == 12.5
    assert policy._coverage_cycle_start_deposit_kg == 3.0
    assert policy._coverage_last_payload_gain_kg == 9.5
    assert policy._coverage_last_effective_deposit_delta_kg == 4.5
    assert policy._coverage_global_low_productivity_streak == 2
    assert policy._coverage_completed_dump_count == 3
    assert policy._coverage_pass_index == 1
    assert policy._coverage_terminal_stop_requested is True
    assert policy._coverage_terminal_stop_reason == "unit_terminal"
    assert policy._coverage_candidate_scores == [{"corridor_id": 7, "score": 1.25}]
    assert policy._coverage_decision_trace == [{"event": "unit_trace"}]
    assert policy._coverage_active_state_exemplar_ids == ["cell7_deep"]
    assert policy._coverage_rejected_state_exemplar_ids == {"cell3_shallow"}
    assert policy._coverage_active_state_exemplar_distance == 0.25
    assert policy._coverage_active_state_exemplar_profile_token is profile_token


def test_coverage_trace_snapshot_matches_facade_and_preserves_trace_payload() -> None:
    policy = _coverage_policy(
        coverage_extra={
            "multi_pass_enabled": True,
            "multi_pass_max_passes": 3,
            "multi_pass_min_remaining_depth_m": 0.125,
            "first_dig_strategy": "nearest_entry",
            "first_dig_preferred_corridor_id": 2,
        },
    )
    policy._ensure_coverage_corridors()
    policy._record_coverage_decision_event(
        "unit_trace_event",
        corridor=policy._coverage_corridors[0],
        extra={"score_delta": float("nan")},
    )
    policy._request_coverage_terminal_stop("unit_terminal", replace=True)

    direct = policy.coverage_service.coverage_trace_snapshot()
    facade = policy._coverage_trace_snapshot()

    assert direct.use_env_removed_depth == facade.use_env_removed_depth
    assert direct.candidate_layout == facade.candidate_layout
    assert direct.first_dig_strategy == facade.first_dig_strategy
    assert direct.pass_index == facade.pass_index
    assert direct.multi_pass_enabled == facade.multi_pass_enabled
    assert direct.multi_pass_max_passes == facade.multi_pass_max_passes
    assert (
        direct.multi_pass_min_remaining_depth_m
        == facade.multi_pass_min_remaining_depth_m
    )
    assert direct.first_dig_preferred_corridor_id == 2
    assert facade.first_dig_preferred_corridor_id == 2
    assert _canonicalize(direct.corridors) == _canonicalize(facade.corridors)
    assert _canonicalize(direct.decision_trace) == _canonicalize(
        facade.decision_trace
    )
    assert direct.terminal_stop_requested is True
    assert facade.terminal_stop_requested is True
    assert direct.terminal_stop_reason == "unit_terminal"
    assert facade.terminal_stop_reason == "unit_terminal"


def test_coverage_rollout_summary_snapshot_matches_facade() -> None:
    policy = _coverage_policy(
        coverage_extra={
            "multi_pass_enabled": True,
            "multi_pass_max_passes": 3,
            "multi_pass_min_remaining_depth_m": 0.125,
            "first_dig_strategy": "nearest_entry",
            "first_dig_preferred_corridor_id": 2,
            "first_dig_max_entry_distance_m": 0.75,
            "first_dig_qpos_delta_weight": 0.5,
        },
    )
    policy._ensure_coverage_corridors()
    policy._coverage_active_corridor_id = int(policy._coverage_corridors[0].corridor_id)
    policy._coverage_completed_dump_count = 4
    policy._coverage_pass_index = 2
    policy._coverage_corridors[1].depleted = True
    policy._request_coverage_terminal_stop("unit_terminal", replace=True)

    direct = policy.coverage_service.coverage_rollout_summary_snapshot()
    facade = policy._coverage_rollout_summary_snapshot()

    assert direct.selected_corridor_id == facade.selected_corridor_id
    assert direct.selected_corridor_id == int(policy._coverage_corridors[0].corridor_id)
    assert direct.depleted_count == 1
    assert facade.depleted_count == 1
    assert direct.completed_dump_count == 4
    assert facade.completed_dump_count == 4
    assert direct.pass_index == 2
    assert facade.pass_index == 2
    assert direct.multi_pass_enabled is True
    assert facade.multi_pass_enabled is True
    assert direct.use_env_removed_depth == facade.use_env_removed_depth
    assert direct.candidate_layout == facade.candidate_layout
    assert direct.first_dig_strategy == "nearest_entry"
    assert facade.first_dig_strategy == "nearest_entry"
    assert direct.first_dig_preferred_corridor_id == 2
    assert facade.first_dig_preferred_corridor_id == 2
    assert direct.first_dig_max_entry_distance_m == 0.75
    assert facade.first_dig_max_entry_distance_m == 0.75
    assert direct.first_dig_qpos_delta_weight == 0.5
    assert facade.first_dig_qpos_delta_weight == 0.5
    assert direct.terminal_stop_requested is True
    assert facade.terminal_stop_requested is True
    assert direct.terminal_stop_reason == "unit_terminal"
    assert facade.terminal_stop_reason == "unit_terminal"


def test_coverage_service_direct_selection_matches_policy_facade() -> None:
    policy = _coverage_policy(
        prior_path=YULONG_REMOVED_DEPTH_DIG_CUT_PRIOR_V3_PATH,
        coverage_extra={
            "candidate_layout": "cell_weighted_3x2",
            "rare_cell_source_fraction_threshold": 0.05,
            "rare_cell_max_attempts": 1,
            "first_dig_strategy": "nearest_entry",
            "first_dig_proximity_weight": 100.0,
            "recent_row_selection_penalty": 0.5,
        },
    )
    direct_service = CoverageService(
        config=policy._coverage_service_config(),
        state=CoverageServiceState(),
        first_dig_alignment_target_fn=policy._coverage_first_dig_alignment_target,
    )
    obs = _coverage_obs(bucket_pose=(0.8023, 0.0, 0.5011))
    facts = policy._coverage_observation_facts(obs)

    direct_selected = direct_service.select_next_corridor(facts)
    facade_selected = policy._select_next_coverage_corridor(obs)

    assert direct_selected.corridor_id == facade_selected.corridor_id
    assert direct_selected.cell_id == facade_selected.cell_id
    assert _canonicalize(direct_service._coverage_candidate_scores) == _canonicalize(
        policy._coverage_candidate_scores
    )
    assert _canonicalize(direct_service.decision_trace) == _canonicalize(
        policy._coverage_decision_trace
    )


def test_coverage_service_direct_dig_cut_activation_matches_policy_facade() -> None:
    policy = _coverage_policy(
        prior_path=YULONG_REMOVED_DEPTH_DIG_CUT_PRIOR_V3_PATH,
        coverage_extra={
            "candidate_layout": "cell_weighted_3x2",
            "rare_cell_source_fraction_threshold": 0.05,
            "rare_cell_max_attempts": 1,
            "first_dig_strategy": "nearest_entry",
            "first_dig_proximity_weight": 100.0,
            "recent_row_selection_penalty": 0.5,
        },
    )
    direct_service = CoverageService(
        config=policy._coverage_service_config(),
        state=CoverageServiceState(),
        first_dig_alignment_target_fn=policy._coverage_first_dig_alignment_target,
    )
    obs = _coverage_obs(bucket_pose=(0.8023, 0.0, 0.5011), deposited=25.0)
    facts = policy._coverage_observation_facts(obs)

    direct = direct_service.activate_dig_cut_corridor(
        facts,
        reset_cycle_metrics=True,
    )
    facade = policy._activate_coverage_dig_cut(
        obs,
        reset_cycle_metrics=True,
    )

    assert direct.corridor.corridor_id == facade.corridor.corridor_id
    assert direct.corridor.cell_id == facade.corridor.cell_id
    assert _canonicalize(direct.raw_fields) == _canonicalize(facade.raw_fields)
    assert direct_service._coverage_current_payload_gain_kg == pytest.approx(0.0)
    assert policy._coverage_current_payload_gain_kg == pytest.approx(0.0)
    assert direct_service._coverage_cycle_start_deposit_kg == pytest.approx(25.0)
    assert policy._coverage_cycle_start_deposit_kg == pytest.approx(25.0)
    assert _canonicalize(direct_service._coverage_candidate_scores) == _canonicalize(
        policy._coverage_candidate_scores
    )
    assert _canonicalize(direct_service.decision_trace) == _canonicalize(
        policy._coverage_decision_trace
    )


def test_coverage_dig_cut_activation_can_preserve_cycle_metrics() -> None:
    policy = _coverage_policy(
        prior_path=YULONG_REMOVED_DEPTH_DIG_CUT_PRIOR_V3_PATH,
        coverage_extra={
            "candidate_layout": "cell_weighted_3x2",
            "first_dig_strategy": "nearest_entry",
            "first_dig_proximity_weight": 100.0,
        },
    )
    direct_service = CoverageService(
        config=policy._coverage_service_config(),
        state=CoverageServiceState(),
        first_dig_alignment_target_fn=policy._coverage_first_dig_alignment_target,
    )
    direct_service._coverage_current_payload_gain_kg = 7.5
    direct_service._coverage_cycle_start_deposit_kg = 3.25
    policy._coverage_current_payload_gain_kg = 7.5
    policy._coverage_cycle_start_deposit_kg = 3.25
    obs = _coverage_obs(bucket_pose=(0.8023, 0.0, 0.5011), deposited=25.0)
    facts = policy._coverage_observation_facts(obs)

    direct_service.activate_dig_cut_corridor(
        facts,
        reset_cycle_metrics=False,
    )
    policy._activate_coverage_dig_cut(
        obs,
        reset_cycle_metrics=False,
    )

    assert direct_service._coverage_current_payload_gain_kg == pytest.approx(7.5)
    assert direct_service._coverage_cycle_start_deposit_kg == pytest.approx(3.25)
    assert policy._coverage_current_payload_gain_kg == pytest.approx(7.5)
    assert policy._coverage_cycle_start_deposit_kg == pytest.approx(3.25)


def test_coverage_service_direct_completion_matches_facade_state_update() -> None:
    policy = _coverage_policy(
        coverage_extra={
            "use_env_removed_depth": False,
            "belief_depleted_score": 100.0,
            "max_attempts_per_corridor": 1,
        }
    )
    direct_service = CoverageService(
        config=policy._coverage_service_config(),
        state=CoverageServiceState(),
        first_dig_alignment_target_fn=policy._coverage_first_dig_alignment_target,
    )
    direct_service.ensure_corridors()
    policy._ensure_coverage_corridors()

    direct_completed = direct_service._coverage_corridors[0]
    facade_completed = policy._coverage_corridors[0]
    direct_service._coverage_active_corridor_id = int(direct_completed.corridor_id)
    policy._coverage_active_corridor_id = int(facade_completed.corridor_id)
    direct_service._coverage_current_payload_gain_kg = 50.0
    policy._coverage_current_payload_gain_kg = 50.0
    direct_service._coverage_cycle_start_deposit_kg = 0.0
    policy._coverage_cycle_start_deposit_kg = 0.0

    obs = _coverage_obs(deposited=25.0)
    direct_service.complete_dump(
        policy._coverage_observation_facts(obs),
        reason="unit_complete",
    )
    policy._complete_coverage_dump(obs, reason="unit_complete")

    assert direct_completed.attempts == facade_completed.attempts
    assert direct_completed.depleted == facade_completed.depleted
    assert direct_completed.last_reason == facade_completed.last_reason
    assert _canonicalize(direct_service.decision_trace) == _canonicalize(
        policy._coverage_decision_trace
    )


def test_percentile_coverage_corridors_raw_fields_and_debug_schema() -> None:
    policy = _coverage_policy(
        coverage_extra={
            "cut_depth_percentile": "p90",
            "payload_percentile": "p90",
        }
    )

    policy._ensure_coverage_corridors()
    corridor = policy._coverage_corridors[0]
    debug = policy._coverage_corridor_to_debug(corridor)
    raw_fields = policy._coverage_raw_fields(corridor)

    assert len(policy._coverage_corridors) == 9
    assert sorted({policy._coverage_cell_id(item) for item in policy._coverage_corridors}) == [
        0,
        1,
        2,
        3,
        4,
        5,
    ]
    assert tuple(debug) == (
        "corridor_id",
        "entry_x_m",
        "entry_z_m",
        "exit_x_m",
        "exit_z_m",
        "entry_x_p05_m",
        "entry_x_p50_m",
        "entry_x_p95_m",
        "entry_z_p05_m",
        "entry_z_p50_m",
        "entry_z_p95_m",
        "entry_radial_p75_m",
        "entry_radial_p95_m",
        "exit_x_p05_m",
        "exit_x_p50_m",
        "exit_x_p95_m",
        "exit_z_p05_m",
        "exit_z_p50_m",
        "exit_z_p95_m",
        "exit_radial_p75_m",
        "exit_radial_p95_m",
        "cut_depth_peak_p05_m",
        "cut_depth_peak_p50_m",
        "cut_depth_peak_p95_m",
        "cell_id",
        "source_count",
        "source_fraction",
        "attempt_limit",
        "cell_confidence",
        "score",
        "attempts",
        "low_productivity_streak",
        "depleted",
        "belief_coverage",
        "last_payload_gain_kg",
        "last_effective_deposit_delta_kg",
        "last_remaining_depth_m",
        "last_reason",
        "state_exemplar_id",
        "state_exemplar_distance",
    )
    assert np.isclose(float(raw_fields["operator_cut_depth_peak_m"]), 1.1767)
    assert np.isclose(float(raw_fields["operator_cut_payload_gain_kg"]), 74.2262)
    assert float(raw_fields["operator_cut_depth_peak_m"]) / DIG_CUT_DEPTH_SCALE_M > 0.0


def test_cell_weighted_coverage_selection_candidate_scores_and_attempt_limit() -> None:
    policy = _coverage_policy(
        prior_path=YULONG_REMOVED_DEPTH_DIG_CUT_PRIOR_V3_PATH,
        coverage_extra={
            "candidate_layout": "cell_weighted_3x2",
            "rare_cell_source_fraction_threshold": 0.05,
            "rare_cell_max_attempts": 1,
            "first_dig_strategy": "nearest_entry",
            "first_dig_proximity_weight": 100.0,
        },
    )
    obs = _coverage_obs(bucket_pose=(0.8023, 0.0, 0.5011))

    selected = policy._select_next_coverage_corridor(obs)
    rare = policy._coverage_corridors[4]
    candidate_by_cell = {
        int(item["cell_id"]): item for item in policy._coverage_candidate_scores
    }

    assert len(policy._coverage_corridors) == 6
    assert [policy._coverage_cell_id(item) for item in policy._coverage_corridors] == [
        0,
        1,
        2,
        3,
        4,
        5,
    ]
    assert policy._coverage_cell_id(selected) != 4
    assert rare.cell_id == 4
    assert rare.source_fraction < 0.05
    assert policy._coverage_corridor_attempt_limit(rare) == 1
    assert int(candidate_by_cell[4]["rare_first_dig_gated_out"]) == 1


def test_coverage_completion_and_rejection_update_belief_and_trace() -> None:
    complete_policy = _coverage_policy(
        coverage_extra={
            "use_env_removed_depth": False,
            "belief_depleted_score": 100.0,
            "max_attempts_per_corridor": 1,
        }
    )
    complete_policy._ensure_coverage_corridors()
    completed = complete_policy._coverage_corridors[0]
    complete_policy._coverage_active_corridor_id = int(completed.corridor_id)
    complete_policy._coverage_current_payload_gain_kg = 50.0
    complete_policy._coverage_cycle_start_deposit_kg = 0.0

    complete_policy._complete_coverage_dump(
        _coverage_obs(deposited=25.0),
        reason="unit_complete",
    )

    assert completed.attempts == 1
    assert completed.depleted is True
    assert completed.last_reason == "attempt_limit_reached"
    assert complete_policy._coverage_decision_trace[-1]["event"] == "complete_dump"

    reject_policy = _coverage_policy()
    reject_policy._ensure_coverage_corridors()
    rejected = reject_policy._coverage_corridors[0]
    reject_policy._coverage_active_corridor_id = int(rejected.corridor_id)
    reject_policy._dig_best_mass_kg = 10.0

    reject_policy._reject_active_coverage_corridor(
        _coverage_obs(deposited=0.0),
        reason="unit_reject",
    )

    assert rejected.attempts == 1
    assert rejected.low_productivity_streak == 1
    assert rejected.last_reason == "unit_reject"
    assert reject_policy._coverage_global_low_productivity_streak == 1
    assert reject_policy._coverage_decision_trace[-1]["event"] == "reject_corridor"
    assert reject_policy._coverage_decision_trace[-1]["counted_attempt"] == 1


def test_coverage_service_defers_terminal_stop_to_policy_facade() -> None:
    policy = _coverage_policy(
        coverage_extra={
            "use_env_removed_depth": False,
            "belief_depleted_score": 100.0,
            "max_attempts_per_corridor": 1,
        }
    )
    direct_service = CoverageService(
        config=policy._coverage_service_config(),
        state=CoverageServiceState(),
        first_dig_alignment_target_fn=policy._coverage_first_dig_alignment_target,
    )
    direct_service.ensure_corridors()
    policy._ensure_coverage_corridors()

    for corridor in direct_service._coverage_corridors[1:]:
        corridor.depleted = True
    for corridor in policy._coverage_corridors[1:]:
        corridor.depleted = True

    direct_corridor = direct_service._coverage_corridors[0]
    facade_corridor = policy._coverage_corridors[0]
    direct_service._coverage_active_corridor_id = int(direct_corridor.corridor_id)
    policy._coverage_active_corridor_id = int(facade_corridor.corridor_id)
    direct_service._coverage_current_payload_gain_kg = 50.0
    policy._coverage_current_payload_gain_kg = 50.0

    obs = _coverage_obs(deposited=25.0)
    result = direct_service.complete_dump(
        policy._coverage_observation_facts(obs),
        reason="unit_complete",
    )

    assert result.terminal_stop_reason == "dig_area_depleted"
    assert direct_service._coverage_terminal_stop_requested is False
    assert direct_service.decision_trace[-1]["event"] == "complete_dump"

    policy._complete_coverage_dump(obs, reason="unit_complete")

    assert policy._coverage_terminal_stop_requested is True
    assert policy._coverage_terminal_stop_reason == "dig_area_depleted"
    assert policy._coverage_decision_trace[-1]["event"] == "terminal_stop"


def test_coverage_terminal_stop_reason_preserves_first_request() -> None:
    policy = _coverage_policy(
        coverage_extra={
            "use_env_removed_depth": False,
            "belief_depleted_score": 100.0,
            "low_productivity_payload_kg": 100.0,
            "low_productivity_deposit_kg": 10.0,
            "global_low_productivity_stop": 1,
            "deplete_after_low_streak": 99,
            "max_attempts_per_corridor": 99,
        }
    )
    direct_service = CoverageService(
        config=policy._coverage_service_config(),
        state=CoverageServiceState(),
        first_dig_alignment_target_fn=policy._coverage_first_dig_alignment_target,
    )
    direct_service.ensure_corridors()
    direct_corridor = direct_service._coverage_corridors[0]
    direct_service._coverage_active_corridor_id = int(direct_corridor.corridor_id)
    direct_service._coverage_current_payload_gain_kg = 0.0

    result = direct_service.complete_dump(
        policy._coverage_observation_facts(_coverage_obs(deposited=25.0)),
        reason="unit_complete",
    )

    assert result.terminal_stop_reason == "low_productivity_consecutive"
    assert direct_service._coverage_terminal_stop_requested is False


def _coverage_policy(
    *,
    prior_path: Path = YULONG_DIG_CUT_PRIOR_PATH,
    coverage_extra: dict[str, Any] | None = None,
) -> PrimitivePlannerACTPolicy:
    return PrimitivePlannerACTPolicy(
        dig_policy=_ConstantPolicy(0.0),
        carry_policy=_ConstantPolicy(1.0),
        dump_policy=_ConstantPolicy(2.0),
        return_policy=_ConstantPolicy(3.0),
        boundary_detector=_FakeBoundaryDetector(),
        dig_to_carry_min_bucket_mass_kg=20.0,
        dig_cut_planner={
            "enabled": True,
            "mode": "operator_prior_coverage",
            "prior_path": str(prior_path),
            "fallback_mode": "conservative_pose",
            "hold_token_until_skill_exit": True,
            "coverage": dict(coverage_extra or {}),
        },
    )


def _coverage_obs(
    *,
    mass: float = 0.0,
    deposited: float = 0.0,
    removed_cell0: float = 0.0,
    bucket_pose: tuple[float, float, float] | None = None,
) -> dict[str, Any]:
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX] = float(deposited)
    for index in range(6):
        env_state[ENV_STATE_DIG_AREA_TARGET_DEPTH_START_IDX + index] = 0.08
        env_state[ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX + index] = 1.0
    env_state[ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX] = float(removed_cell0)
    if bucket_pose is not None:
        env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX] = float(bucket_pose[0])
        env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX] = float(bucket_pose[1])
        env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX] = float(bucket_pose[2])
        env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX] = float(bucket_pose[0])
        env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX] = float(bucket_pose[1])
        env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX] = float(bucket_pose[2])
    return {
        "qpos": np.asarray([0.50, 0.60, 0.10, 0.20], dtype=np.float32),
        "qvel": np.zeros(4, dtype=np.float32),
        "env_state": env_state,
        "task_metrics": {
            "mass_in_bucket_kg": float(mass),
            "deposited_mass_in_target_box_kg": float(deposited),
        },
    }


class _ConstantPolicy:
    def __init__(self, value: float) -> None:
        self.value = float(value)

    def reset(self) -> None:
        pass

    def predict(self, _obs: dict[str, Any]) -> np.ndarray:
        action = np.zeros(4, dtype=np.float32)
        action[0] = self.value
        return action


class _FakeBoundaryDetector:
    boundary_profile = "legacy"

    def reset(self) -> None:
        pass

    def update(self, _obs: dict[str, Any]) -> None:
        return None


def _canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _canonicalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_canonicalize(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_canonicalize(item) for item in value)
    if isinstance(value, float) and np.isnan(value):
        return "nan"
    return value
