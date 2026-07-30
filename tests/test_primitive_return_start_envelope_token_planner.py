from __future__ import annotations

import numpy as np

from testbed.data.operator_first_v2_2 import RETURN_START_ENVELOPE_TOKEN_DIM
from testbed.data.schema import (
    ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX,
    ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX,
)
from testbed.planner.primitive.token.tokens import (
    ReturnStartEnvelopeConditioningConfig,
    ReturnStartEnvelopeTokenPlanner,
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
        "operator_cut_depth_peak_m": 0.10,
        "operator_cut_payload_gain_kg": 55.0,
        "operator_cut_valid": 1,
    }


def test_return_start_envelope_token_planner_uses_cell_prior() -> None:
    token = np.arange(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)
    planner = ReturnStartEnvelopeTokenPlanner(
        prior={
            "return_start_envelope_cells": [
                {
                    "cell_id": 2,
                    "source_count": 3,
                    "source_fraction": 0.5,
                    "token_median": token.tolist(),
                },
            ],
        },
        use_cell_prior=True,
        min_source_count=1,
        min_source_fraction=0.0,
    )

    plan = planner.plan(
        raw_fields=_raw_fields(),
        env_state=np.zeros(64, dtype=np.float32),
        qpos=np.zeros(4, dtype=np.float32),
        qvel=np.zeros(4, dtype=np.float32),
        cell_id=2,
    )

    assert plan.source == "qc6_return_start_envelope_cell_2"
    assert plan.use_prior_spatial_bounds is True
    assert plan.use_prior_qpos_bounds is True
    np.testing.assert_allclose(plan.token, token)


def test_return_start_envelope_token_planner_uses_artifact_source_label() -> None:
    token = np.arange(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)
    planner = ReturnStartEnvelopeTokenPlanner(
        prior={
            "return_start_envelope_source_label": (
                "strict18_train_return_start_envelope"
            ),
            "return_start_envelope_cells": [
                {
                    "cell_id": 2,
                    "source_count": 3,
                    "source_fraction": 0.5,
                    "token_median": token.tolist(),
                },
            ],
        },
        use_cell_prior=True,
    )

    plan = planner.plan(
        raw_fields=_raw_fields(),
        env_state=np.zeros(64, dtype=np.float32),
        qpos=np.zeros(4, dtype=np.float32),
        qvel=np.zeros(4, dtype=np.float32),
        cell_id=2,
    )

    assert plan.source == "strict18_train_return_start_envelope_cell_2"


def test_return_start_envelope_token_planner_builds_live_fallback() -> None:
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX] = -0.25
    env_state[ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX] = 0.75
    planner = ReturnStartEnvelopeTokenPlanner(prior={})

    plan = planner.plan(
        raw_fields=_raw_fields(),
        env_state=env_state,
        qpos=np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
        qvel=np.asarray([0.0, -0.2, 0.1, 0.05], dtype=np.float32),
        cell_id=None,
    )

    assert plan.source == "live_current_obs_fallback"
    assert float(plan.token[0]) == -0.25
    assert float(plan.token[1]) == 0.75
    np.testing.assert_allclose(plan.token[2], 0.10)
    np.testing.assert_allclose(plan.token[7:11], [0.1, 0.2, 0.3, 0.4])
    np.testing.assert_allclose(plan.token[15], 0.2)
    assert float(plan.token[16]) == 1.0
    assert float(plan.token[17]) == 1.0


def test_return_start_envelope_token_planner_conditions_from_relocate() -> None:
    token = np.zeros(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)
    token[9] = 0.5
    qpos_coefficients = np.zeros((4, 8), dtype=np.float32)
    qpos_coefficients[:, 0] = [0.11, 0.22, 0.33, 0.44]
    spatial_coefficients = np.zeros((2, 8), dtype=np.float32)
    spatial_coefficients[:, 0] = [-0.5, 0.6]
    planner = ReturnStartEnvelopeTokenPlanner(
        prior={"return_start_envelope_global": {"token_median": token.tolist()}},
        conditioning=ReturnStartEnvelopeConditioningConfig(
            qpos_enabled=True,
            qpos_coefficients=qpos_coefficients,
            qpos_min=np.full(4, -1.0, dtype=np.float32),
            qpos_max=np.full(4, 1.0, dtype=np.float32),
            qpos_use_prior_bounds=False,
            spatial_enabled=True,
            spatial_coefficients=spatial_coefficients,
            spatial_min=np.full(2, -1.0, dtype=np.float32),
            spatial_max=np.full(2, 1.0, dtype=np.float32),
            spatial_use_prior_bounds=False,
        ),
    )

    plan = planner.plan(
        raw_fields=_raw_fields(),
        env_state=np.zeros(64, dtype=np.float32),
        qpos=np.zeros(4, dtype=np.float32),
        qvel=np.zeros(4, dtype=np.float32),
        cell_id=None,
    )

    assert (
        plan.source
        == "qc6_return_start_envelope_global+relocate_spatial_linear+relocate_qpos_linear"
    )
    assert plan.use_prior_spatial_bounds is False
    assert plan.use_prior_qpos_bounds is False
    np.testing.assert_allclose(plan.token[0:2], [-0.5, 0.6])
    np.testing.assert_allclose(plan.token[7:11], [0.11, 0.22, 0.33, 0.44])
