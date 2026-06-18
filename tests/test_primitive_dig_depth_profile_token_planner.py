from __future__ import annotations

import numpy as np
import pytest

from testbed.data.dig_depth_profile_v2_4 import (
    DIG_DEPTH_PROFILE_TOKEN_DIM,
    build_dig_depth_profile_token_from_plan,
)
from testbed.planner.primitive_tokens import (
    DigDepthProfileTokenPlanner,
    DigDepthProfileTokenPlanningError,
)


def _raw_fields() -> dict[str, float | int]:
    return {
        "operator_entry_x_m": 0.0,
        "operator_entry_z_m": 0.5,
        "operator_exit_x_m": -1.2,
        "operator_exit_z_m": 0.5,
        "operator_cut_direction_x": -1.0,
        "operator_cut_direction_z": 0.0,
        "operator_cut_length_m": 1.2,
        "operator_cut_depth_peak_m": 0.08,
        "operator_cut_payload_gain_kg": 55.0,
        "operator_effective_deposit_delta_kg": 45.0,
        "operator_cut_valid": 1,
    }


def test_dig_depth_profile_token_planner_builds_live_plan() -> None:
    planner = DigDepthProfileTokenPlanner(prior={}, source="live_plan")
    env_state = np.zeros(64, dtype=np.float32)

    plan = planner.plan(cell_id=2, raw_fields=_raw_fields(), env_state=env_state)

    expected = build_dig_depth_profile_token_from_plan(
        raw_fields=_raw_fields(),
        cell_id=2,
        env_state=env_state,
        effective_deposit_delta_kg=45.0,
    )
    assert plan.source == "live_plan"
    assert plan.fallback_reason == ""
    np.testing.assert_allclose(plan.token, expected)


def test_dig_depth_profile_token_planner_prefers_state_exemplar() -> None:
    exemplar = np.arange(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float32)
    planner = DigDepthProfileTokenPlanner(
        prior={},
        source="prior_profile",
        required=True,
    )

    plan = planner.plan(
        cell_id=1,
        raw_fields=_raw_fields(),
        env_state=np.zeros(64, dtype=np.float32),
        state_exemplar_profile_token=exemplar,
    )

    exemplar[0] = 99.0
    assert plan.source == "qc6_state_conditioned_exemplar"
    assert plan.fallback_reason == ""
    assert float(plan.token[0]) == 0.0


def test_dig_depth_profile_token_planner_uses_cell_then_global_prior() -> None:
    cell_token = np.ones(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float32)
    global_token = np.full(DIG_DEPTH_PROFILE_TOKEN_DIM, 2.0, dtype=np.float32)
    planner = DigDepthProfileTokenPlanner(
        prior={
            "dig_depth_profile_cells": [
                {"cell_id": 3, "token_median": cell_token.tolist()},
            ],
            "dig_depth_profile_global": {"token_median": global_token.tolist()},
        },
        source="prior_profile",
    )

    cell_plan = planner.plan(
        cell_id=3,
        raw_fields=_raw_fields(),
        env_state=np.zeros(64, dtype=np.float32),
    )
    global_plan = planner.plan(
        cell_id=4,
        raw_fields=_raw_fields(),
        env_state=np.zeros(64, dtype=np.float32),
    )

    assert cell_plan.source == "qc6_dig_depth_profile_cell_3"
    np.testing.assert_allclose(cell_plan.token, cell_token)
    assert global_plan.source == "qc6_dig_depth_profile_global"
    np.testing.assert_allclose(global_plan.token, global_token)


def test_dig_depth_profile_token_planner_missing_required_prior_reports_source() -> None:
    planner = DigDepthProfileTokenPlanner(
        prior={},
        source="prior_profile",
        required=True,
    )

    with pytest.raises(DigDepthProfileTokenPlanningError) as exc_info:
        planner.plan(
            cell_id=5,
            raw_fields=_raw_fields(),
            env_state=np.zeros(64, dtype=np.float32),
        )

    assert exc_info.value.token_source == "missing_required_prior"
    assert exc_info.value.fallback_reason == "missing dig_cut_prior"
    assert "requires a matching dig_depth_profile prior" in str(exc_info.value)
