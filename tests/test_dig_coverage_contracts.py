from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from testbed.data.operator_first_v2_2 import DIG_CUT_DEPTH_SCALE_M
from testbed.data.schema import (
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX,
    ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
    ENV_STATE_DIG_AREA_TARGET_DEPTH_START_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
)
from testbed.planner.dig_coverage import (
    CoverageService,
    CoverageServiceState,
    DigCoverageMixin,
)
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
