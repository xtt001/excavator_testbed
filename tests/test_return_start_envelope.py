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
    RETURN_START_ENVELOPE_RUNTIME_CONFIG_FIELDS,
    ReturnStartEnvelopeBuildRequest,
    ReturnStartEnvelopeConfig,
    ReturnStartEnvelopeGatePriorContext,
    ReturnStartEnvelopeState,
    build_live_return_start_envelope_token,
    build_return_start_envelope_config,
    build_return_start_envelope_config_from_mapping,
    build_return_start_envelope_for_plan,
    build_return_start_envelope_request,
    build_return_start_envelope_request_from_observation_view,
    condition_return_start_envelope_from_relocate,
    require_return_start_envelope_token_result,
    resolve_return_start_envelope_cell_id,
    return_start_envelope_gate_prior_context,
    return_start_envelope_prior_bounds,
    return_start_envelope_prior_mapping,
    return_start_envelope_prior_token,
    return_start_envelope_token_from_prior_mapping,
    return_start_envelope_token_has_gate_bounds,
    return_to_dig_start_envelope_ready,
)
from testbed.planner.return_start_envelope_config import (
    RETURN_START_ENVELOPE_RUNTIME_CONFIG_FIELDS as config_fields,
)
from testbed.planner.return_start_envelope_config import (
    ReturnStartEnvelopeConfig as ConfigReturnStartEnvelopeConfig,
)
from testbed.planner.return_start_envelope_config import (
    build_return_start_envelope_config as config_builder,
)
from testbed.planner.return_start_envelope_config import (
    build_return_start_envelope_config_from_mapping as config_mapping_builder,
)
from testbed.planner.return_start_envelope_config import (
    normalize_plane_depth_mode as config_normalize_plane_depth_mode,
)
from testbed.planner.return_start_envelope_prior import (
    ReturnStartEnvelopeGatePriorContext as PriorReturnStartEnvelopeGatePriorContext,
)
from testbed.planner.return_start_envelope_prior import (
    return_start_envelope_gate_prior_context as prior_gate_prior_context,
)
from testbed.planner.return_start_envelope_prior import (
    return_start_envelope_prior_bounds as prior_bounds,
)
from testbed.planner.return_start_envelope_prior import (
    return_start_envelope_prior_mapping as prior_mapping,
)
from testbed.planner.return_start_envelope_prior import (
    return_start_envelope_prior_token as prior_token,
)
from testbed.planner.return_start_envelope_prior import (
    return_start_envelope_token_from_prior_mapping as prior_token_from_mapping,
)
from testbed.planner.return_start_envelope_prior import (
    return_start_envelope_token_has_gate_bounds as prior_token_has_gate_bounds,
)
from testbed.planner.snapshots import build_planner_snapshot


def test_return_start_envelope_prior_symbols_remain_compatible_facades() -> None:
    assert ReturnStartEnvelopeGatePriorContext is PriorReturnStartEnvelopeGatePriorContext
    assert return_start_envelope_token_has_gate_bounds is prior_token_has_gate_bounds
    assert return_start_envelope_gate_prior_context is prior_gate_prior_context
    assert return_start_envelope_prior_mapping is prior_mapping
    assert return_start_envelope_prior_token is prior_token
    assert return_start_envelope_prior_bounds is prior_bounds
    assert return_start_envelope_token_from_prior_mapping is prior_token_from_mapping


def test_return_start_envelope_config_symbols_remain_compatible_facades() -> None:
    from testbed.planner.return_start_envelope import normalize_plane_depth_mode

    assert RETURN_START_ENVELOPE_RUNTIME_CONFIG_FIELDS is config_fields
    assert ReturnStartEnvelopeConfig is ConfigReturnStartEnvelopeConfig
    assert build_return_start_envelope_config is config_builder
    assert build_return_start_envelope_config_from_mapping is config_mapping_builder
    assert normalize_plane_depth_mode is config_normalize_plane_depth_mode


def test_build_return_start_envelope_config_projects_conditioning_and_gate_fields() -> None:
    qpos_coefficients = np.arange(32, dtype=np.float64).reshape(4, 8)
    spatial_coefficients = np.arange(16, dtype=np.float64).reshape(2, 8)

    values = {
        "use_cell_prior": 1,
        "min_source_count": 0,
        "min_source_fraction": "-0.5",
        "qpos_from_relocate_enabled": 1,
        "qpos_from_relocate_coefficients": qpos_coefficients,
        "qpos_from_relocate_min": ["0.1", "0.2", "0.3", "0.4"],
        "qpos_from_relocate_max": ["0.5", "0.6", "0.7", "0.8"],
        "qpos_from_relocate_use_prior_qpos_bounds": 1,
        "spatial_from_relocate_enabled": 1,
        "spatial_from_relocate_coefficients": spatial_coefficients,
        "spatial_from_relocate_min": ["-0.2", "-0.1"],
        "spatial_from_relocate_max": ["0.9", "1.1"],
        "spatial_from_relocate_use_prior_spatial_bounds": 1,
        "gate_enabled": 1,
        "spatial_tolerance": "0.12",
        "depth_tolerance_m": "0.07",
        "local_depth_tolerance_m": "0.006",
        "plane_depth_tolerance_m": "0.03",
        "plane_depth_mode": "target_band",
        "qpos_tolerance": "0.05",
        "require_contact": 0,
    }

    direct = build_return_start_envelope_config(**values)
    config = build_return_start_envelope_config_from_mapping(
        {**values, "ignored": object()}
    )
    assert {key for key, _ in RETURN_START_ENVELOPE_RUNTIME_CONFIG_FIELDS} == set(
        values
    )
    for key in values:
        actual = getattr(config, key)
        expected = getattr(direct, key)
        if isinstance(expected, np.ndarray):
            np.testing.assert_allclose(actual, expected)
        else:
            assert actual == expected

    assert config.use_cell_prior is True
    assert config.min_source_count == 1
    assert config.min_source_fraction == pytest.approx(0.0)
    assert config.qpos_from_relocate_enabled is True
    np.testing.assert_allclose(config.qpos_from_relocate_coefficients, qpos_coefficients)
    np.testing.assert_allclose(config.qpos_from_relocate_min, [0.1, 0.2, 0.3, 0.4])
    np.testing.assert_allclose(config.qpos_from_relocate_max, [0.5, 0.6, 0.7, 0.8])
    assert config.qpos_from_relocate_use_prior_qpos_bounds is True
    assert config.spatial_from_relocate_enabled is True
    np.testing.assert_allclose(
        config.spatial_from_relocate_coefficients,
        spatial_coefficients,
    )
    np.testing.assert_allclose(config.spatial_from_relocate_min, [-0.2, -0.1])
    np.testing.assert_allclose(config.spatial_from_relocate_max, [0.9, 1.1])
    assert config.spatial_from_relocate_use_prior_spatial_bounds is True
    assert config.gate_enabled is True
    assert config.spatial_tolerance == pytest.approx(0.12)
    assert config.depth_tolerance_m == pytest.approx(0.07)
    assert config.local_depth_tolerance_m == pytest.approx(0.006)
    assert config.plane_depth_tolerance_m == pytest.approx(0.03)
    assert config.plane_depth_mode == "target_band"
    assert config.qpos_tolerance == pytest.approx(0.05)
    assert config.require_contact is False


def test_build_return_start_envelope_request_preserves_legacy_fallbacks() -> None:
    env_state = _env_state(long_norm=0.25, short_norm=0.40)
    raw_fields = _valid_raw_fields()
    config = ReturnStartEnvelopeConfig(use_cell_prior=True)
    prior = {
        "return_start_envelope_global": {
            "token_median": np.zeros(RETURN_START_ENVELOPE_TOKEN_DIM),
        },
    }

    request = build_return_start_envelope_request(
        env_state=env_state,
        qpos=None,
        qvel=None,
        raw_fields=raw_fields,
        action_dim=4,
        dig_cut_prior=prior,
        config=config,
        cell_id=np.int64(3),
    )

    assert request.env_state is env_state
    np.testing.assert_array_equal(request.qpos, np.zeros(4))
    np.testing.assert_array_equal(request.qvel, np.zeros(4))
    assert request.raw_fields is raw_fields
    assert request.action_dim == 4
    assert request.dig_cut_prior is prior
    assert request.config is config
    assert request.cell_id == 3


def test_build_return_start_envelope_request_from_view_preserves_raw_qpos_qvel() -> None:
    obs = {
        "env_state": _env_state(long_norm=0.25, short_norm=0.40),
        "qpos": np.asarray([[0.51, 0.62, 0.22, 0.18]], dtype=np.float64),
        "qvel": np.asarray([[-0.1, 0.3, -0.2, 0.05]], dtype=np.float64),
    }
    raw_fields = _valid_raw_fields()
    config = ReturnStartEnvelopeConfig(use_cell_prior=True)
    prior = {"return_start_envelope_global": {"token_median": np.zeros(4)}}
    view = build_planner_snapshot(
        obs,
        active_skill="return",
        cycle_index=2,
        prev_action=None,
        boundary_event=None,
        action_dim=4,
    ).view

    request = build_return_start_envelope_request_from_observation_view(
        view,
        raw_fields=raw_fields,
        dig_cut_prior=prior,
        config=config,
        cell_id=np.int64(3),
    )

    np.testing.assert_allclose(request.env_state, obs["env_state"])
    assert request.qpos is obs["qpos"]
    assert request.qvel is obs["qvel"]
    assert request.raw_fields is raw_fields
    assert request.action_dim == 4
    assert request.dig_cut_prior is prior
    assert request.config is config
    assert request.cell_id == 3


def test_build_return_start_envelope_request_from_view_keeps_missing_defaults() -> None:
    view = build_planner_snapshot(
        {},
        active_skill="return",
        cycle_index=2,
        prev_action=None,
        boundary_event=None,
        action_dim=4,
    ).view

    request = build_return_start_envelope_request_from_observation_view(
        view,
        raw_fields=_valid_raw_fields(),
    )

    assert request.env_state.shape == (13,)
    assert request.env_state.dtype == np.float32
    np.testing.assert_array_equal(request.qpos, np.zeros(4))
    np.testing.assert_array_equal(request.qvel, np.zeros(4))
    assert request.qpos.dtype == np.float64
    assert request.qvel.dtype == np.float64
    assert request.action_dim == 4
    assert request.dig_cut_prior is None
    assert isinstance(request.config, ReturnStartEnvelopeConfig)
    assert request.cell_id is None


def test_require_token_result_projects_state_and_reuses_float32_token() -> None:
    token = np.arange(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)

    result = require_return_start_envelope_token_result(
        ReturnStartEnvelopeState(
            token=token,
            source="qc6_return_start_envelope_cell_3",
            use_prior_spatial_bounds=False,
            use_prior_qpos_bounds=True,
        )
    )

    assert result.token is token
    assert result.source == "qc6_return_start_envelope_cell_3"
    assert result.use_prior_spatial_bounds is False
    assert result.use_prior_qpos_bounds is True


def test_require_token_result_preserves_legacy_missing_token_error() -> None:
    with pytest.raises(
        RuntimeError,
        match="return start-envelope builder returned no token",
    ):
        require_return_start_envelope_token_result(ReturnStartEnvelopeState())


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


def test_gate_prior_context_resolves_mapping_and_bounds_only_for_valid_gate_token() -> None:
    token = _ready_token()
    lower = np.linspace(-0.25, 0.25, RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)
    upper = lower + 1.0
    prior = {
        "return_start_envelope_cells": [
            {
                "cell_id": 4,
                "source_count": 3,
                "source_fraction": 0.4,
                "token_median": token,
                "token_p05": lower,
                "token_p95": upper,
            }
        ],
        "return_start_envelope_global": {"token_median": token + 2.0},
    }
    config = ReturnStartEnvelopeConfig(
        gate_enabled=True,
        use_cell_prior=True,
        min_source_count=2,
        min_source_fraction=0.25,
    )

    assert return_start_envelope_token_has_gate_bounds(token, config)
    context = return_start_envelope_gate_prior_context(
        token=token,
        dig_cut_prior=prior,
        config=config,
        cell_id=4,
    )

    assert context.token_has_bounds
    assert context.cell_id == 4
    assert context.prior_mapping is not None
    assert context.prior_mapping["cell_id"] == 4
    np.testing.assert_allclose(context.lower, lower)
    np.testing.assert_allclose(context.upper, upper)

    invalid_token = np.zeros(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)
    disabled = return_start_envelope_gate_prior_context(
        token=token,
        dig_cut_prior=prior,
        config=ReturnStartEnvelopeConfig(gate_enabled=False),
        cell_id=4,
    )
    invalid = return_start_envelope_gate_prior_context(
        token=invalid_token,
        dig_cut_prior=prior,
        config=config,
        cell_id=4,
    )
    assert not disabled.token_has_bounds
    assert disabled.prior_mapping is None
    assert disabled.lower is None
    assert disabled.upper is None
    assert not invalid.token_has_bounds
    assert invalid.prior_mapping is None
    assert invalid.lower is None
    assert invalid.upper is None


def test_return_start_envelope_cell_id_resolution_preserves_corridor_fallback() -> None:
    assert resolve_return_start_envelope_cell_id(corridor_id=None) is None
    assert resolve_return_start_envelope_cell_id(corridor_id=-1) is None
    assert resolve_return_start_envelope_cell_id(corridor_id=3) == 3
    assert (
        resolve_return_start_envelope_cell_id(
            corridor_id=3,
            corridor_cell_id=8,
        )
        == 8
    )
    assert (
        resolve_return_start_envelope_cell_id(
            corridor_id=3,
            corridor_cell_id=-1,
        )
        == -1
    )


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
