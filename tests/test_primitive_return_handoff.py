from __future__ import annotations

from types import MethodType
from typing import Any

import numpy as np
import pytest

from testbed.data.operator_first_v2_2 import RETURN_START_ENVELOPE_TOKEN_DIM
from testbed.data.schema import (
    ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX,
    ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX,
)
from testbed.planner.primitive_return_handoff import (
    ReturnStartEnvelopeGateConfig,
    ReturnStartEnvelopeGateInputs,
    ReturnStartEnvelopeGateResult,
    ReturnStartEnvelopeGateService,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def _token() -> np.ndarray:
    token = np.zeros(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)
    token[0] = 0.10
    token[1] = -0.20
    token[2] = 0.12
    token[4] = 0.08
    token[5] = 0.18
    token[7:11] = np.asarray([0.5, 0.4, 0.3, 0.2], dtype=np.float32)
    token[11:15] = np.asarray([0.02, 0.02, 0.02, 0.02], dtype=np.float32)
    token[16] = 1.0
    token[17] = 1.0
    return token


def _env_state(size: int = 64) -> np.ndarray:
    env_state = np.zeros(size, dtype=np.float32)
    if size > ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX:
        env_state[ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX] = 0.10
    if size > ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX:
        env_state[ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX] = -0.20
    if size > ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX:
        env_state[ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX] = 0.12
    if size > ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX:
        env_state[ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX] = 0.12
    if size > ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX:
        env_state[ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX] = 1.0
    return env_state


def _config(**overrides: Any) -> ReturnStartEnvelopeGateConfig:
    values: dict[str, Any] = {
        "enabled": True,
        "action_dim": 4,
        "spatial_tolerance": 0.10,
        "depth_tolerance_m": 0.08,
        "local_depth_tolerance_m": 0.005,
        "plane_depth_tolerance_m": 0.005,
        "plane_depth_mode": "range",
        "qpos_tolerance": 0.04,
        "require_contact": False,
    }
    values.update(overrides)
    return ReturnStartEnvelopeGateConfig(**values)


def _inputs(
    *,
    token: np.ndarray | list[float] | None = None,
    env_state: np.ndarray | None = None,
    qpos: np.ndarray | None = None,
    prior_mapping: dict[str, object] | None = None,
    lower: np.ndarray | None = None,
    upper: np.ndarray | None = None,
    use_prior_spatial_bounds: bool = False,
    use_prior_qpos_bounds: bool = False,
) -> ReturnStartEnvelopeGateInputs:
    return ReturnStartEnvelopeGateInputs(
        token=_token() if token is None else token,
        env_state=_env_state() if env_state is None else env_state,
        qpos=(
            np.asarray([0.5, 0.4, 0.3, 0.2], dtype=np.float32)
            if qpos is None
            else qpos
        ),
        prior_bounds=lambda: (lower, upper),
        prior_mapping=lambda: prior_mapping,
        use_prior_spatial_bounds=use_prior_spatial_bounds,
        use_prior_qpos_bounds=use_prior_qpos_bounds,
    )


def test_start_envelope_gate_keeps_permissive_compat_cases() -> None:
    service = ReturnStartEnvelopeGateService(config=_config(enabled=False))
    disabled = service.evaluate(_inputs(token=[1.0, 2.0]))

    assert disabled.ready is True
    assert np.isnan(disabled.error)
    assert disabled.checks == {}

    service = ReturnStartEnvelopeGateService(config=_config())
    missing = service.evaluate(_inputs(token=[1.0, 2.0]))
    invalid = service.evaluate(_inputs(token=np.zeros(RETURN_START_ENVELOPE_TOKEN_DIM)))

    assert missing.ready is True
    assert np.isnan(missing.error)
    assert missing.checks == {"missing_token": True}
    assert invalid.ready is True
    assert np.isnan(invalid.error)
    assert invalid.checks == {"invalid_token": True}


def test_start_envelope_gate_records_spatial_check_failure_payload() -> None:
    env_state = _env_state()
    env_state[ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX] = 0.35

    result = ReturnStartEnvelopeGateService(config=_config()).evaluate(
        _inputs(env_state=env_state)
    )

    assert result.ready is False
    long_norm = result.checks["long_norm"]
    assert long_norm["value"] == pytest.approx(0.3499999940395355)
    assert long_norm["min"] == pytest.approx(0.0, abs=1.0e-7)
    assert long_norm["max"] == pytest.approx(0.20000000149011612)
    assert long_norm["ok"] is False
    assert long_norm["error"] == pytest.approx(0.1499999925494194)
    assert result.checks["short_norm"]["ok"] is True


def test_start_envelope_gate_records_local_depth_prior_range_payload() -> None:
    env_state = _env_state()
    env_state[ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX] = 0.03
    prior_mapping = {
        "dig_start_local_depth_m": {"p05": 0.006, "p50": 0.011, "p95": 0.021}
    }

    result = ReturnStartEnvelopeGateService(config=_config()).evaluate(
        _inputs(env_state=env_state, prior_mapping=prior_mapping)
    )

    check = result.checks["local_depth_m"]
    assert result.ready is False
    assert check["mode"] == "prior_range"
    assert check["target"] == 0.011
    assert check["p05"] == 0.006
    assert check["p50"] == 0.011
    assert check["p95"] == 0.021
    assert check["ok"] is False


def test_start_envelope_gate_records_plane_depth_p50_floor_contact_prior_payload() -> None:
    prior_mapping = {
        "dig_start_local_depth_m": {"p05": 0.006, "p50": 0.011, "p95": 0.021},
        "dig_start_plane_depth_m": {"p05": 0.09, "p50": 0.12, "p95": 0.18},
    }
    env_state = _env_state()
    env_state[ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX] = 0.011
    env_state[ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX] = 0.09
    env_state[ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX] = 1.0

    result = ReturnStartEnvelopeGateService(
        config=_config(require_contact=True, plane_depth_mode="p50_floor")
    ).evaluate(_inputs(env_state=env_state, prior_mapping=prior_mapping))

    check = result.checks["plane_depth_m"]
    assert result.ready is True
    assert check["mode"] == "p50_floor"
    assert check["target"] == 0.12
    assert check["p05"] == 0.09
    assert check["p50"] == 0.12
    assert check["p95"] == 0.18
    assert check["floor_source"] == "p05_local_contact_prior"


def test_start_envelope_gate_records_contact_required_payloads() -> None:
    missing_contact_env = _env_state(size=ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX)
    missing = ReturnStartEnvelopeGateService(
        config=_config(require_contact=True)
    ).evaluate(_inputs(env_state=missing_contact_env))

    assert missing.ready is False
    assert missing.checks["dig_contact_missing"] is True

    no_contact_env = _env_state()
    no_contact_env[ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX] = 0.0
    token = _token()
    token[6] = 1.0
    failed = ReturnStartEnvelopeGateService(
        config=_config(require_contact=True)
    ).evaluate(_inputs(token=token, env_state=no_contact_env))

    assert failed.ready is False
    assert failed.checks["dig_contact"] == {
        "value": 0.0,
        "ok": False,
        "required_by_config": True,
        "required_by_token": True,
    }


def test_start_envelope_gate_records_qpos_checks_and_missing_payload() -> None:
    qpos = np.asarray([0.60, 0.4, 0.3, 0.2], dtype=np.float32)
    result = ReturnStartEnvelopeGateService(config=_config()).evaluate(
        _inputs(qpos=qpos)
    )

    assert result.ready is False
    assert result.checks["qpos_0"]["ok"] is False
    assert result.checks["qpos_1"]["ok"] is True
    assert result.checks["qpos_2"]["ok"] is True
    assert result.checks["qpos_3"]["ok"] is True

    missing = ReturnStartEnvelopeGateService(config=_config()).evaluate(
        _inputs(qpos=np.asarray([0.5, 0.4, 0.3], dtype=np.float32))
    )

    assert missing.ready is False
    assert missing.checks["qpos_missing"] is True


def test_policy_start_envelope_wrapper_delegates_and_writes_cached_result() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    planner._return_start_envelope_tokens = _token()
    planner._return_start_envelope_use_prior_spatial_bounds = False
    planner._return_start_envelope_use_prior_qpos_bounds = False
    planner._pending_dig_cut_corridor_id = 7
    planner.action_dim = 4
    planner._env_state = MethodType(lambda self, obs: _env_state(), planner)
    planner._return_start_envelope_prior_bounds = MethodType(
        lambda self, corridor_id: (None, None),
        planner,
    )
    planner._return_start_envelope_prior_mapping = MethodType(
        lambda self, *, corridor_id: (None, "missing"),
        planner,
    )
    expected_result = ReturnStartEnvelopeGateResult(
        ready=False,
        error=0.25,
        checks={"qpos_0": {"ok": False}},
    )
    calls: list[ReturnStartEnvelopeGateInputs] = []

    class _FakeService:
        def evaluate(
            self,
            inputs: ReturnStartEnvelopeGateInputs,
        ) -> ReturnStartEnvelopeGateResult:
            calls.append(inputs)
            return expected_result

    planner._return_start_envelope_gate_service = MethodType(
        lambda self: _FakeService(),
        planner,
    )

    ready = planner._return_to_dig_start_envelope_ready({"qpos": [1.0, 2.0, 3.0, 4.0]})

    assert ready is False
    assert len(calls) == 1
    assert calls[0].prior_bounds() == (None, None)
    assert calls[0].prior_mapping() is None
    assert planner._return_to_dig_start_envelope_ready_state is False
    assert planner._return_to_dig_start_envelope_error == 0.25
    assert planner._return_to_dig_start_envelope_checks == {"qpos_0": {"ok": False}}
