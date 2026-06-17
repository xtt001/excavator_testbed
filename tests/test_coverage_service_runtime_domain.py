from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

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
from testbed.planner.dig_coverage.models import (
    CoverageObservationFacts,
    CoverageServiceConfig,
    CoverageServiceState,
)
from testbed.planner.dig_coverage.service import CoverageService

REPO_ROOT = Path(__file__).resolve().parents[1]
YULONG_REMOVED_DEPTH_DIG_CUT_PRIOR_V3_PATH = (
    REPO_ROOT
    / "testbed/configs/planner_priors/yulong_removed_depth_dig_cut_prior_v3.json"
)


def test_coverage_selection_result_is_testable_without_policy_adapter() -> None:
    service = _coverage_service()
    facts = _coverage_facts(bucket_pose=(0.8023, 0.0, 0.5011))

    result = service.select_next_corridor_result(facts)

    assert result.action.terminal_stop_reason == ""
    assert result.corridor.corridor_id == service._coverage_active_corridor_id
    assert result.corridor.corridor_id == service._coverage_last_selected_corridor_id
    assert service._coverage_candidate_scores
    assert service.decision_trace[-1]["event"] == "select_corridor"
    assert (
        service.decision_trace[-1]["corridor"]["corridor_id"]
        == result.corridor.corridor_id
    )


def test_coverage_dig_cut_activation_is_testable_without_policy_adapter() -> None:
    service = _coverage_service()
    service._coverage_current_payload_gain_kg = 7.5
    service._coverage_cycle_start_deposit_kg = 3.25
    facts = _coverage_facts(
        bucket_pose=(0.8023, 0.0, 0.5011),
        deposited=25.0,
    )

    result = service.activate_dig_cut_corridor(
        facts,
        reset_cycle_metrics=True,
    )

    assert result.action.terminal_stop_reason == ""
    assert result.corridor.corridor_id == service._coverage_active_corridor_id
    assert service.raw_fields_in_prior_range(result.raw_fields)
    assert result.raw_fields["operator_cut_valid"] == 1
    assert service._coverage_current_payload_gain_kg == pytest.approx(0.0)
    assert service._coverage_cycle_start_deposit_kg == pytest.approx(25.0)
    assert service.decision_trace[-1]["event"] == "select_corridor"


def _coverage_service(
    *,
    prior_path: Path = YULONG_REMOVED_DEPTH_DIG_CUT_PRIOR_V3_PATH,
) -> CoverageService:
    with prior_path.open("r", encoding="utf-8") as handle:
        prior = json.load(handle)
    return CoverageService(
        config=CoverageServiceConfig(
            dig_cut_planner_mode="operator_prior_coverage",
            dig_cut_prior=prior,
            dig_cut_prior_path=str(prior_path),
            action_dim=4,
            candidate_layout="cell_weighted_3x2",
            rare_cell_source_fraction_threshold=0.05,
            rare_cell_max_attempts=1,
            first_dig_strategy="nearest_entry",
            first_dig_proximity_weight=100.0,
            recent_row_selection_penalty=0.5,
        ),
        state=CoverageServiceState(),
    )


def _coverage_facts(
    *,
    mass: float = 0.0,
    deposited: float = 0.0,
    removed_cell0: float = 0.0,
    bucket_pose: tuple[float, float, float] | None = None,
) -> CoverageObservationFacts:
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
    return CoverageObservationFacts(
        env_state=env_state,
        qpos=np.asarray([0.50, 0.60, 0.10, 0.20], dtype=np.float32),
        bucket_tip_dig_area_pose=bucket_pose,
        mass_in_bucket_kg=float(mass),
        deposited_mass_kg=float(deposited),
        cycle_index=0,
        skill_name="dig",
        dig_best_mass_kg=0.0,
    )
