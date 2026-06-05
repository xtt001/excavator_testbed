from __future__ import annotations

import math

import numpy as np
import pytest

from testbed.contracts.primitive_tokens import (
    RETURN_ENVELOPE_CONTACT_FLAG_IDX,
    RETURN_ENVELOPE_DEPTH_CENTER_IDX,
    RETURN_ENVELOPE_DEPTH_MAX_IDX,
    RETURN_ENVELOPE_DEPTH_MIN_IDX,
    RETURN_ENVELOPE_LONG_NORM_IDX,
    RETURN_ENVELOPE_QPOS_CENTER_SLICE,
    RETURN_ENVELOPE_QPOS_HALF_WIDTH_SLICE,
    RETURN_ENVELOPE_QPOS_VALID_IDX,
    RETURN_ENVELOPE_QVEL_ABS_MAX_IDX,
    RETURN_ENVELOPE_SHORT_NORM_IDX,
    RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX,
    RETURN_ENVELOPE_TIP_RADIUS_IDX,
    RETURN_START_ENVELOPE_TOKEN_DIM,
)
from testbed.data.schema import (
    ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX,
    ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX,
)
from testbed.planner.return_start_envelope import (
    ReturnStartEnvelopeBuildRequest,
    ReturnStartEnvelopeConfig,
    build_live_return_start_envelope_token,
    build_return_start_envelope_for_plan,
    condition_return_start_envelope_from_relocate,
    return_start_envelope_prior_bounds,
    return_start_envelope_prior_mapping,
    return_start_envelope_prior_token,
    return_start_envelope_token_from_prior_mapping,
    return_to_dig_start_envelope_ready,
)


def test_live_return_start_envelope_token_locks_current_fallback_fields() -> None:
    env_state = _env_state(long_norm=0.25, short_norm=0.40)
    qpos = np.asarray([0.51, 0.62, 0.22, 0.18], dtype=np.float32)
    qvel = np.asarray([-0.1, 0.3, -0.2, 0.05], dtype=np.float32)

    token = build_live_return_start_envelope_token(
        env_state=env_state,
        qpos=qpos,
        qvel=qvel,
        raw_fields={"operator_cut_depth_peak_m": 0.12},
        action_dim=4,
    )

    assert token.shape == (RETURN_START_ENVELOPE_TOKEN_DIM,)
    assert token[RETURN_ENVELOPE_LONG_NORM_IDX] == pytest.approx(0.25)
    assert token[RETURN_ENVELOPE_SHORT_NORM_IDX] == pytest.approx(0.40)
    assert token[RETURN_ENVELOPE_DEPTH_CENTER_IDX] == pytest.approx(0.12)
    assert token[RETURN_ENVELOPE_TIP_RADIUS_IDX] == pytest.approx(0.20)
    assert token[RETURN_ENVELOPE_DEPTH_MIN_IDX] == pytest.approx(0.04)
    assert token[RETURN_ENVELOPE_DEPTH_MAX_IDX] == pytest.approx(0.20)
    assert token[RETURN_ENVELOPE_CONTACT_FLAG_IDX] == pytest.approx(0.0)
    np.testing.assert_allclose(token[RETURN_ENVELOPE_QPOS_CENTER_SLICE], qpos)
    np.testing.assert_allclose(
        token[RETURN_ENVELOPE_QPOS_HALF_WIDTH_SLICE],
        np.asarray([0.05, 0.05, 0.05, 0.05], dtype=np.float32),
    )
    assert token[RETURN_ENVELOPE_QPOS_VALID_IDX] == pytest.approx(1.0)
    assert token[RETURN_ENVELOPE_QVEL_ABS_MAX_IDX] == pytest.approx(0.3)
    assert token[RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX] == pytest.approx(1.0)


def test_relocate_conditioning_updates_qpos_spatial_source_and_bounds() -> None:
    qpos_coefficients = np.zeros((4, 8), dtype=np.float32)
    qpos_coefficients[:, 0] = np.asarray([0.45, 0.60, 0.20, 0.10], dtype=np.float32)
    spatial_coefficients = np.zeros((2, 8), dtype=np.float32)
    spatial_coefficients[:, 0] = np.asarray([0.33, 0.44], dtype=np.float32)
    config = ReturnStartEnvelopeConfig(
        qpos_from_relocate_enabled=True,
        qpos_from_relocate_coefficients=qpos_coefficients,
        qpos_from_relocate_min=[0.0, 0.0, 0.0, 0.0],
        qpos_from_relocate_max=[1.0, 1.0, 1.0, 1.0],
        qpos_from_relocate_use_prior_qpos_bounds=False,
        spatial_from_relocate_enabled=True,
        spatial_from_relocate_coefficients=spatial_coefficients,
        spatial_from_relocate_min=[-1.0, -1.0],
        spatial_from_relocate_max=[1.0, 1.0],
        spatial_from_relocate_use_prior_spatial_bounds=False,
    )
    token = np.zeros(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)

    state = condition_return_start_envelope_from_relocate(
        token,
        raw_fields=_valid_raw_fields(),
        config=config,
        source="live_current_obs_fallback",
    )

    assert state.source == (
        "live_current_obs_fallback+relocate_spatial_linear+relocate_qpos_linear"
    )
    assert state.use_prior_spatial_bounds is False
    assert state.use_prior_qpos_bounds is False
    assert state.token is not None
    assert state.token[RETURN_ENVELOPE_LONG_NORM_IDX] == pytest.approx(0.33)
    assert state.token[RETURN_ENVELOPE_SHORT_NORM_IDX] == pytest.approx(0.44)
    np.testing.assert_allclose(
        state.token[RETURN_ENVELOPE_QPOS_CENTER_SLICE],
        np.asarray([0.45, 0.60, 0.20, 0.10], dtype=np.float32),
    )


def test_prior_mapping_prefers_supported_cell_then_global_low_support() -> None:
    token = np.linspace(0.0, 1.0, RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)
    prior = {
        "return_start_envelope_cells": [
            {
                "cell_id": 7,
                "source_count": 5,
                "source_fraction": 0.50,
                "token_median": token,
            },
            {
                "cell_id": 8,
                "source_count": 1,
                "source_fraction": 0.05,
                "token_median": token + 1.0,
            },
        ],
        "return_start_envelope_global": {"token_median": token + 2.0},
    }
    config = ReturnStartEnvelopeConfig(
        use_cell_prior=True,
        min_source_count=3,
        min_source_fraction=0.25,
    )

    mapping, source = return_start_envelope_prior_mapping(
        prior,
        config=config,
        cell_id=7,
    )
    assert source == "cell"
    prior_token, prior_source = return_start_envelope_prior_token(
        mapping,
        source=source,
        cell_id=7,
    )
    assert prior_source == "qc6_return_start_envelope_cell_7"
    np.testing.assert_allclose(prior_token, token)

    mapping, source = return_start_envelope_prior_mapping(
        prior,
        config=config,
        cell_id=8,
    )
    assert source == "global_low_support_cell"
    prior_token, prior_source = return_start_envelope_prior_token(
        mapping,
        source=source,
        cell_id=8,
    )
    assert prior_source == "qc6_return_start_envelope_global_low_support_cell_8"
    np.testing.assert_allclose(prior_token, token + 2.0)


def test_prior_token_and_bounds_fail_fast_on_wrong_shapes() -> None:
    with pytest.raises(ValueError, match="return_start_envelope prior token"):
        return_start_envelope_token_from_prior_mapping({"token": [0.0, 1.0]})

    lower, upper = return_start_envelope_prior_bounds(
        {"token_p05": [0.0, 1.0], "token_p95": [1.0, 2.0]}
    )
    assert lower is None
    assert upper is None


def test_build_return_start_envelope_for_plan_prefers_prior_and_conditions() -> None:
    prior_token = _ready_token()
    qpos_coefficients = np.zeros((4, 8), dtype=np.float32)
    qpos_coefficients[:, 0] = np.asarray([0.45, 0.60, 0.20, 0.10], dtype=np.float32)
    config = ReturnStartEnvelopeConfig(
        use_cell_prior=True,
        qpos_from_relocate_enabled=True,
        qpos_from_relocate_coefficients=qpos_coefficients,
        qpos_from_relocate_use_prior_qpos_bounds=False,
    )

    state = build_return_start_envelope_for_plan(
        ReturnStartEnvelopeBuildRequest(
            env_state=_env_state(long_norm=0.99, short_norm=0.88),
            qpos=[0.1, 0.2, 0.3, 0.4],
            qvel=[0.0, 0.0, 0.0, 0.0],
            raw_fields=_valid_raw_fields(),
            action_dim=4,
            dig_cut_prior={
                "return_start_envelope_cells": [
                    {
                        "cell_id": 3,
                        "source_count": 4,
                        "source_fraction": 0.5,
                        "token_median": prior_token,
                    }
                ],
                "return_start_envelope_global": {"token_median": prior_token + 1.0},
            },
            config=config,
            cell_id=3,
        )
    )

    assert state.source == "qc6_return_start_envelope_cell_3+relocate_qpos_linear"
    assert state.use_prior_spatial_bounds is True
    assert state.use_prior_qpos_bounds is False
    assert state.token is not None
    np.testing.assert_allclose(
        state.token[RETURN_ENVELOPE_LONG_NORM_IDX],
        prior_token[RETURN_ENVELOPE_LONG_NORM_IDX],
        atol=1.0e-6,
    )
    np.testing.assert_allclose(
        state.token[RETURN_ENVELOPE_QPOS_CENTER_SLICE],
        np.asarray([0.45, 0.60, 0.20, 0.10], dtype=np.float32),
        atol=1.0e-6,
    )


def test_build_return_start_envelope_for_plan_uses_live_fallback_without_prior() -> None:
    state = build_return_start_envelope_for_plan(
        ReturnStartEnvelopeBuildRequest(
            env_state=_env_state(long_norm=0.25, short_norm=0.40),
            qpos=[0.51, 0.62, 0.22, 0.18],
            qvel=[-0.1, 0.3, -0.2, 0.05],
            raw_fields={"operator_cut_depth_peak_m": 0.12},
            action_dim=4,
            dig_cut_prior=None,
            config=ReturnStartEnvelopeConfig(),
            cell_id=None,
        )
    )

    assert state.source == "live_current_obs_fallback"
    assert state.use_prior_spatial_bounds is True
    assert state.use_prior_qpos_bounds is True
    assert state.token is not None
    assert state.token[RETURN_ENVELOPE_LONG_NORM_IDX] == pytest.approx(0.25)
    assert state.token[RETURN_ENVELOPE_SHORT_NORM_IDX] == pytest.approx(0.40)
    assert state.token[RETURN_ENVELOPE_DEPTH_CENTER_IDX] == pytest.approx(0.12)
    np.testing.assert_allclose(
        state.token[RETURN_ENVELOPE_QPOS_CENTER_SLICE],
        np.asarray([0.51, 0.62, 0.22, 0.18], dtype=np.float32),
    )


def test_return_to_dig_start_envelope_gate_checks_ready_and_qpos_failure() -> None:
    token = _ready_token()
    prior_mapping = {
        "dig_start_local_depth_m": {"p05": 0.09, "p50": 0.11, "p95": 0.13},
        "dig_start_plane_depth_m": {"p05": 0.07, "p50": 0.10, "p95": 0.14},
    }
    config = ReturnStartEnvelopeConfig(
        gate_enabled=True,
        require_contact=True,
        plane_depth_mode="p50_floor",
    )
    env_state = _env_state(
        long_norm=0.25,
        short_norm=0.40,
        local_depth=0.11,
        plane_depth=0.08,
        contact=1.0,
    )

    state = return_to_dig_start_envelope_ready(
        token,
        config=config,
        env_state=env_state,
        qpos=[0.50, 0.60, 0.20, 0.10],
        action_dim=4,
        prior_mapping=prior_mapping,
        use_prior_spatial_bounds=False,
        use_prior_qpos_bounds=False,
    )

    assert state.ready is True
    assert state.error == pytest.approx(0.0)
    assert state.checks["local_depth_m"]["mode"] == "prior_range"
    assert state.checks["plane_depth_m"]["floor_source"] == "p05_local_contact_prior"
    assert state.checks["dig_contact"]["ok"] is True

    failed = return_to_dig_start_envelope_ready(
        token,
        config=config,
        env_state=env_state,
        qpos=[0.90, 0.60, 0.20, 0.10],
        action_dim=4,
        prior_mapping=prior_mapping,
        use_prior_spatial_bounds=False,
        use_prior_qpos_bounds=False,
    )
    assert failed.ready is False
    assert failed.checks["qpos_0"]["ok"] is False
    assert failed.error > 0.0


def test_return_to_dig_start_envelope_gate_keeps_legacy_permissive_fallbacks() -> None:
    disabled = return_to_dig_start_envelope_ready(
        [0.0],
        config=ReturnStartEnvelopeConfig(gate_enabled=False),
        env_state=[],
        qpos=None,
        action_dim=4,
    )
    assert disabled.ready is True
    assert math.isnan(disabled.error)
    assert disabled.checks == {}

    missing = return_to_dig_start_envelope_ready(
        [0.0],
        config=ReturnStartEnvelopeConfig(gate_enabled=True),
        env_state=[],
        qpos=None,
        action_dim=4,
    )
    assert missing.ready is True
    assert math.isnan(missing.error)
    assert missing.checks == {"missing_token": True}

    invalid = return_to_dig_start_envelope_ready(
        np.zeros(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32),
        config=ReturnStartEnvelopeConfig(gate_enabled=True),
        env_state=[],
        qpos=None,
        action_dim=4,
    )
    assert invalid.ready is True
    assert math.isnan(invalid.error)
    assert invalid.checks == {"invalid_token": True}


def _ready_token() -> np.ndarray:
    token = np.zeros(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)
    token[RETURN_ENVELOPE_LONG_NORM_IDX] = 0.25
    token[RETURN_ENVELOPE_SHORT_NORM_IDX] = 0.40
    token[RETURN_ENVELOPE_DEPTH_CENTER_IDX] = 0.11
    token[RETURN_ENVELOPE_DEPTH_MIN_IDX] = 0.09
    token[RETURN_ENVELOPE_DEPTH_MAX_IDX] = 0.13
    token[RETURN_ENVELOPE_CONTACT_FLAG_IDX] = 1.0
    token[RETURN_ENVELOPE_QPOS_CENTER_SLICE] = np.asarray(
        [0.50, 0.60, 0.20, 0.10],
        dtype=np.float32,
    )
    token[RETURN_ENVELOPE_QPOS_HALF_WIDTH_SLICE] = np.asarray(
        [0.05, 0.05, 0.05, 0.05],
        dtype=np.float32,
    )
    token[RETURN_ENVELOPE_QPOS_VALID_IDX] = 1.0
    token[RETURN_ENVELOPE_SPATIAL_DEPTH_VALID_IDX] = 1.0
    return token


def _env_state(
    *,
    long_norm: float = 0.0,
    short_norm: float = 0.0,
    local_depth: float = 0.0,
    plane_depth: float = 0.0,
    contact: float = 0.0,
) -> np.ndarray:
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX] = float(long_norm)
    env_state[ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX] = float(short_norm)
    env_state[ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX] = float(local_depth)
    env_state[ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX] = float(plane_depth)
    env_state[ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX] = float(contact)
    return env_state


def _valid_raw_fields() -> dict[str, float | int]:
    return {
        "operator_entry_x_m": 0.50,
        "operator_entry_z_m": 0.25,
        "operator_exit_x_m": 1.20,
        "operator_exit_z_m": 0.75,
        "operator_cut_direction_x": 1.0,
        "operator_cut_direction_z": 0.0,
        "operator_cut_length_m": 0.80,
        "operator_cut_depth_peak_m": 0.12,
        "operator_cut_payload_gain_kg": 20.0,
        "operator_cut_valid": 1,
    }
