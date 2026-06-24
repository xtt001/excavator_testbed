from __future__ import annotations

from dataclasses import fields
from types import MethodType
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from testbed.data.operator_first_v2_2 import RETURN_START_ENVELOPE_TOKEN_DIM
from testbed.data.schema import (
    ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX,
    ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX,
)
from testbed.planner.primitive.coverage.selection import CoverageCorridorState
from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.effects.return_handoff import (
    ReturnHandoffReadinessConfig,
    ReturnHandoffReadinessPorts,
    ReturnHandoffReadinessService,
    ReturnDirectHandoffEffectPorts,
    ReturnDirectHandoffEffectService,
    ReturnStartEnvelopeGateConfig,
    ReturnStartEnvelopeGateInputs,
    ReturnStartEnvelopeGateResult,
    ReturnStartEnvelopeGateService,
)
from testbed.planner.primitive.execution.cycle_state import PrimitiveCycleRuntimeState
from testbed.planner.primitive.decision.contracts import SetReturnOrDirectHandoffEffect
from testbed.planner.primitive.effects.requested import (
    PrimitiveRequestedEffectRuntime,
    PrimitiveRequestedEffectRuntimePorts,
)
from testbed.planner.primitive.execution.state import (
    PrimitiveExecutionRuntimeState,
)
from testbed.planner.primitive.execution.return_state import PrimitiveReturnRuntimeState
from testbed.planner.primitive.token.state import PrimitiveTokenRuntimeState
from testbed.policies.hybrid.primitive_planner import (
    PRE_DIG_ALIGN_SKILL_NAME,
    PrimitivePlannerACTPolicy,
)

_OLD_POLICY_RETURN_HANDOFF_READINESS_WRAPPERS = {
    "_return_to_dig_entry_close",
    "_return_to_dig_handoff_ready",
    "_return_to_dig_direct_handoff_ready",
    "_return_to_dig_start_envelope_ready",
    "_return_start_envelope_gate_service",
    "_return_start_envelope_gate_config",
    "_return_start_envelope_gate_inputs",
    "_apply_return_start_envelope_gate_result",
    "_return_to_dig_entry_error_for_obs",
    "_return_to_dig_entry_target",
    "_return_handoff_readiness_config",
    "_return_handoff_readiness_ports",
    "_return_handoff_readiness_service",
}

_OLD_POLICY_RETURN_DIRECT_HANDOFF_EFFECT_WRAPPERS = {
    "_set_return_or_direct_handoff",
    "_try_return_direct_handoff_at_current_obs",
    "_return_direct_handoff_effect_service",
    "_return_direct_handoff_effect_ports",
}


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


def _readiness_config(**overrides: Any) -> ReturnHandoffReadinessConfig:
    values: dict[str, Any] = {
        "return_target_planner_enabled": True,
        "max_entry_error_m": 0.25,
        "max_bucket_mass_kg": 2.0,
        "start_envelope_direct_handoff_enabled": True,
        "start_envelope_gate": _config(enabled=True),
    }
    values.update(overrides)
    return ReturnHandoffReadinessConfig(**values)


def _return_handoff_env(
    *,
    bucket_x: float,
    bucket_y: float = 0.0,
    bucket_z: float,
    mass_in_bucket_kg: float = 0.0,
) -> np.ndarray:
    env_state = _env_state()
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX] = float(bucket_x)
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX] = float(bucket_y)
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX] = float(bucket_z)
    env_state[0] = float(mass_in_bucket_kg)
    return env_state


def _readiness_service(
    *,
    config: ReturnHandoffReadinessConfig | None = None,
    execution_state: PrimitiveExecutionRuntimeState | None = None,
    cycle_state: PrimitiveCycleRuntimeState | None = None,
    return_state: PrimitiveReturnRuntimeState | None = None,
    token_state: PrimitiveTokenRuntimeState | None = None,
    coverage_state: CoverageRuntimeState | None = None,
    ensure_calls: list[str] | None = None,
    gate_results: list[ReturnStartEnvelopeGateResult] | None = None,
) -> ReturnHandoffReadinessService:
    execution_state = execution_state or PrimitiveExecutionRuntimeState.fresh(
        initial_skill_name="return"
    )
    cycle_state = cycle_state or PrimitiveCycleRuntimeState.fresh()
    return_state = return_state or PrimitiveReturnRuntimeState.fresh()
    token_state = token_state or PrimitiveTokenRuntimeState.fresh()
    coverage_state = coverage_state or CoverageRuntimeState()
    ensure_calls = ensure_calls if ensure_calls is not None else []
    gate_results = gate_results if gate_results is not None else [
        ReturnStartEnvelopeGateResult(ready=True, error=0.0, checks={"ok": True})
    ]

    class _FakeGateService:
        def __init__(self) -> None:
            self.inputs: list[ReturnStartEnvelopeGateInputs] = []

        def evaluate(
            self,
            inputs: ReturnStartEnvelopeGateInputs,
        ) -> ReturnStartEnvelopeGateResult:
            self.inputs.append(inputs)
            return gate_results[-1]

    gate_service = _FakeGateService()

    def ensure(obs: dict[str, Any]) -> None:
        ensure_calls.append(str(obs.get("tag", "")))

    return ReturnHandoffReadinessService(
        ports=ReturnHandoffReadinessPorts(
            config=config or _readiness_config(),
            action_dim=4,
            execution_state=execution_state,
            cycle_state=cycle_state,
            return_state=return_state,
            token_state=token_state,
            coverage_state=coverage_state,
            start_envelope_gate_service=gate_service,
            ensure_return_target_plan_for_cycle=ensure,
            return_start_envelope_prior_bounds=lambda corridor_id: (None, None),
            return_start_envelope_prior_mapping=lambda corridor_id: None,
        )
    )


def _direct_handoff_ports(
    events: list[str],
    *,
    current_skill: str = "dump",
    return_target_planner_enabled: bool = True,
    direct_handoff_enabled: bool = True,
    handoff_ready: bool = True,
    direct_handoff_ready: bool = True,
    should_pre_dig_align_before_dig: bool = False,
    next_skill: str = "dig",
) -> ReturnDirectHandoffEffectPorts:
    execution_state = PrimitiveExecutionRuntimeState.fresh(
        initial_skill_name=current_skill,
    )

    class _RecordingCycleState(PrimitiveCycleRuntimeState):
        def complete_return_transition(self) -> None:
            events.append("complete")
            super().complete_return_transition()

    cycle_state = _RecordingCycleState.fresh()

    def set_skill(skill_name: str, reason: str) -> None:
        events.append(f"set:{skill_name}:{reason}")
        execution_state.set_skill_name(skill_name)
        execution_state.set_switch_reason(reason)

    def ensure(obs: dict[str, object]) -> None:
        events.append(f"ensure:{obs['tag']}")

    class _FakeReadinessService:
        def handoff_ready(self, obs: dict[str, object]) -> bool:
            events.append(f"handoff_ready:{obs['tag']}")
            return handoff_ready

        def direct_handoff_ready(
            self,
            obs: dict[str, object],
            *,
            handoff_ready: bool | None = None,
        ) -> bool:
            events.append(f"direct_ready:{obs['tag']}:{handoff_ready}")
            return direct_handoff_ready

    return ReturnDirectHandoffEffectPorts(
        execution_state=execution_state,
        cycle_state=cycle_state,
        set_skill=set_skill,
        return_target_planner_enabled=return_target_planner_enabled,
        return_to_dig_start_envelope_direct_handoff_enabled=(
            direct_handoff_enabled
        ),
        ensure_return_target_plan_for_cycle=ensure,
        readiness_service=_FakeReadinessService(),
        should_pre_dig_align_before_dig=lambda: should_pre_dig_align_before_dig,
        pre_dig_align_skill_name=PRE_DIG_ALIGN_SKILL_NAME,
        dig_skill_name="dig",
    )


def test_return_direct_handoff_ports_use_focused_state_owners() -> None:
    port_fields = {field.name for field in fields(ReturnDirectHandoffEffectPorts)}

    assert {"execution_state", "cycle_state"} <= port_fields
    assert not {
        "current_skill_name",
        "complete_return_transition",
        "next_skill_after_return_transition",
        "return_to_dig_handoff_ready",
        "return_to_dig_direct_handoff_ready",
    } & port_fields
    assert "readiness_service" in port_fields
    assert "should_pre_dig_align_before_dig" in port_fields
    assert "pre_dig_align_skill_name" in port_fields


def test_policy_no_longer_exposes_old_return_handoff_readiness_wrappers() -> None:
    assert _OLD_POLICY_RETURN_HANDOFF_READINESS_WRAPPERS.isdisjoint(
        PrimitivePlannerACTPolicy.__dict__
    )


def test_policy_no_longer_exposes_old_return_direct_handoff_effect_wrappers() -> None:
    assert _OLD_POLICY_RETURN_DIRECT_HANDOFF_EFFECT_WRAPPERS.isdisjoint(
        PrimitivePlannerACTPolicy.__dict__
    )


def test_return_handoff_readiness_prefers_pending_next_cycle_raw_entry_target() -> None:
    token_state = PrimitiveTokenRuntimeState.fresh()
    token_state.pending_dig_cut_cycle_id = 4
    token_state.pending_dig_cut_raw_fields = {
        "operator_entry_x_m": 1.0,
        "operator_entry_z_m": 2.0,
    }
    coverage_state = CoverageRuntimeState()
    coverage_state.set_coverage_corridors(
        [
            CoverageCorridorState(
                corridor_id=9,
                entry_x_m=5.0,
                entry_z_m=6.0,
                exit_x_m=7.0,
                exit_z_m=8.0,
            )
        ]
    )
    coverage_state.set_active_corridor_id(9)
    cycle_state = PrimitiveCycleRuntimeState.fresh()
    cycle_state.cycle_index = 3
    return_state = PrimitiveReturnRuntimeState.fresh()
    service = _readiness_service(
        cycle_state=cycle_state,
        return_state=return_state,
        token_state=token_state,
        coverage_state=coverage_state,
    )

    error = service.entry_error_for_obs(
        {
            "env_state": _return_handoff_env(bucket_x=1.0, bucket_z=2.2),
            "qpos": np.zeros(4, dtype=np.float32),
        }
    )
    close = service.entry_close(
        {
            "tag": "pending",
            "env_state": _return_handoff_env(bucket_x=1.0, bucket_z=2.2),
            "qpos": np.zeros(4, dtype=np.float32),
        }
    )

    assert service.entry_target() == pytest.approx((1.0, 2.0))
    assert error == pytest.approx(0.2)
    assert close is True
    assert return_state.return_to_dig_entry_error_m == pytest.approx(0.2)
    assert return_state.return_to_dig_entry_close_state is True


def test_return_handoff_readiness_falls_back_to_active_corridor_entry_target() -> None:
    coverage_state = CoverageRuntimeState()
    coverage_state.set_coverage_corridors(
        [
            CoverageCorridorState(
                corridor_id=11,
                entry_x_m=3.0,
                entry_z_m=4.0,
                exit_x_m=5.0,
                exit_z_m=6.0,
            )
        ]
    )
    coverage_state.set_active_corridor_id(11)
    service = _readiness_service(coverage_state=coverage_state)

    assert service.entry_target() == pytest.approx((3.0, 4.0))
    assert service.entry_error_for_obs(
        {
            "env_state": _return_handoff_env(bucket_x=3.0, bucket_z=4.5),
            "qpos": np.zeros(4, dtype=np.float32),
        }
    ) == pytest.approx(0.5)


def test_return_handoff_readiness_writes_start_envelope_gate_result() -> None:
    return_state = PrimitiveReturnRuntimeState.fresh()
    result = ReturnStartEnvelopeGateResult(
        ready=False,
        error=0.75,
        checks={"long_norm": {"ok": False}},
    )
    service = _readiness_service(
        return_state=return_state,
        gate_results=[result],
    )

    ready = service.start_envelope_ready(
        {
            "env_state": _return_handoff_env(bucket_x=0.0, bucket_z=0.0),
            "qpos": np.zeros(4, dtype=np.float32),
        }
    )

    assert ready is False
    assert return_state.return_to_dig_start_envelope_ready_state is False
    assert return_state.return_to_dig_start_envelope_error == pytest.approx(0.75)
    assert return_state.return_to_dig_start_envelope_checks == {
        "long_norm": {"ok": False}
    }


def test_return_handoff_readiness_direct_handoff_requires_mass_gate() -> None:
    service = _readiness_service(
        config=_readiness_config(max_bucket_mass_kg=2.0),
    )

    assert (
        service.direct_handoff_ready(
            {
                "env_state": _return_handoff_env(bucket_x=0.0, bucket_z=0.0),
                "qpos": np.zeros(4, dtype=np.float32),
                "task_metrics": {"mass_in_bucket_kg": 1.5},
            },
            handoff_ready=True,
        )
        is True
    )
    assert (
        service.direct_handoff_ready(
            {
                "env_state": _return_handoff_env(bucket_x=0.0, bucket_z=0.0),
                "qpos": np.zeros(4, dtype=np.float32),
                "task_metrics": {"mass_in_bucket_kg": 2.5},
            },
            handoff_ready=True,
        )
        is False
    )


def test_return_direct_handoff_service_stops_after_set_return_when_direct_disabled() -> None:
    events: list[str] = []
    service = ReturnDirectHandoffEffectService(
        ports=_direct_handoff_ports(events, direct_handoff_enabled=False)
    )

    result = service.apply({"tag": "obs"}, reason="dump_to_return_mass_low")

    assert result.direct_handoff_applied is False
    assert events == ["set:return:dump_to_return_mass_low"]


def test_return_direct_handoff_service_stops_after_set_return_when_target_planner_disabled() -> None:
    events: list[str] = []
    service = ReturnDirectHandoffEffectService(
        ports=_direct_handoff_ports(events, return_target_planner_enabled=False)
    )

    result = service.apply({"tag": "obs"}, reason="dump_to_return_mass_low")

    assert result.direct_handoff_applied is False
    assert events == ["set:return:dump_to_return_mass_low"]


def test_return_direct_handoff_service_checks_readiness_without_completion_when_not_ready() -> None:
    events: list[str] = []
    service = ReturnDirectHandoffEffectService(
        ports=_direct_handoff_ports(events, direct_handoff_ready=False)
    )

    result = service.apply({"tag": "obs"}, reason="carry_to_return_release_safety")

    assert result.direct_handoff_applied is False
    assert events == [
        "set:return:carry_to_return_release_safety",
        "ensure:obs",
        "handoff_ready:obs",
        "direct_ready:obs:True",
    ]


def test_return_direct_handoff_service_applies_ready_direct_handoff_to_dig_in_order() -> None:
    events: list[str] = []
    service = ReturnDirectHandoffEffectService(
        ports=_direct_handoff_ports(events, next_skill="dig")
    )

    result = service.apply(
        {"tag": "obs"},
        reason="dump_to_return_dump_complete_boundary",
    )

    assert result.direct_handoff_applied is True
    assert result.next_skill == "dig"
    assert result.switch_reason == "return_to_dig_start_envelope_ready"
    assert events == [
        "set:return:dump_to_return_dump_complete_boundary",
        "ensure:obs",
        "handoff_ready:obs",
        "direct_ready:obs:True",
        "complete",
        "set:dig:return_to_dig_start_envelope_ready",
    ]


def test_return_direct_handoff_service_selects_pre_dig_align_when_runtime_requests_it() -> None:
    events: list[str] = []
    service = ReturnDirectHandoffEffectService(
        ports=_direct_handoff_ports(
            events,
            next_skill="dig",
            should_pre_dig_align_before_dig=True,
        )
    )

    result = service.apply(
        {"tag": "obs"},
        reason="dump_to_return_dump_complete_boundary",
    )

    assert result.direct_handoff_applied is True
    assert result.next_skill == "pre_dig_align"
    assert result.switch_reason == "return_to_pre_dig_align_start_envelope_ready"
    assert events == [
        "set:return:dump_to_return_dump_complete_boundary",
        "ensure:obs",
        "handoff_ready:obs",
        "direct_ready:obs:True",
        "complete",
        "set:pre_dig_align:return_to_pre_dig_align_start_envelope_ready",
    ]


def test_return_direct_handoff_service_try_direct_handoff_noops_outside_return() -> None:
    events: list[str] = []
    service = ReturnDirectHandoffEffectService(
        ports=_direct_handoff_ports(events, current_skill="dump")
    )

    result = service.try_direct_handoff({"tag": "obs"})

    assert result.direct_handoff_applied is False
    assert events == []


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


def test_return_handoff_readiness_service_start_envelope_writes_cached_result() -> None:
    token_state = PrimitiveTokenRuntimeState.fresh()
    token_state.return_start_envelope_tokens = _token()
    token_state.return_start_envelope_use_prior_spatial_bounds = False
    token_state.return_start_envelope_use_prior_qpos_bounds = False
    token_state.pending_dig_cut_corridor_id = 7
    return_state = PrimitiveReturnRuntimeState.fresh()

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

    service = ReturnHandoffReadinessService(
        ports=ReturnHandoffReadinessPorts(
            config=_readiness_config(),
            action_dim=4,
            execution_state=PrimitiveExecutionRuntimeState.fresh(
                initial_skill_name="return"
            ),
            cycle_state=PrimitiveCycleRuntimeState.fresh(),
            return_state=return_state,
            token_state=token_state,
            coverage_state=CoverageRuntimeState(),
            start_envelope_gate_service=_FakeService(),
            ensure_return_target_plan_for_cycle=lambda obs: None,
            return_start_envelope_prior_bounds=lambda corridor_id: (None, None),
            return_start_envelope_prior_mapping=lambda corridor_id: None,
        )
    )

    ready = service.start_envelope_ready(
        {"qpos": [1.0, 2.0, 3.0, 4.0], "env_state": _env_state()}
    )

    assert ready is False
    assert len(calls) == 1
    assert calls[0].prior_bounds() == (None, None)
    assert calls[0].prior_mapping() is None
    assert return_state.return_to_dig_start_envelope_ready_state is False
    assert return_state.return_to_dig_start_envelope_error == 0.25
    assert return_state.return_to_dig_start_envelope_checks == {
        "qpos_0": {"ok": False}
    }


def test_return_handoff_runtime_composes_readiness_from_explicit_ports() -> None:
    from testbed.planner.primitive.effects.return_handoff_runtime import (
        PrimitiveReturnHandoffRuntime,
        PrimitiveReturnHandoffRuntimePorts,
    )

    execution_state = PrimitiveExecutionRuntimeState.fresh(initial_skill_name="return")
    cycle_state = PrimitiveCycleRuntimeState.fresh()
    return_state = PrimitiveReturnRuntimeState.fresh()
    token_state = PrimitiveTokenRuntimeState.fresh()
    coverage_state = CoverageRuntimeState()
    ensure_calls: list[str] = []

    runtime = PrimitiveReturnHandoffRuntime.from_ports(
        PrimitiveReturnHandoffRuntimePorts(
            config=_readiness_config(),
            action_dim=4,
            execution_state=execution_state,
            cycle_state=cycle_state,
            return_state=return_state,
            token_state=token_state,
            coverage_state=coverage_state,
            set_skill=lambda skill, reason: None,
            ensure_return_target_plan_for_cycle=(
                lambda obs: ensure_calls.append(str(obs.get("tag", "")))
            ),
            return_start_envelope_prior_bounds=lambda corridor_id: (None, None),
            return_start_envelope_prior_mapping=lambda corridor_id: None,
            should_pre_dig_align_before_dig=lambda: False,
            pre_dig_align_skill_name=PRE_DIG_ALIGN_SKILL_NAME,
        )
    )

    service = runtime.readiness_service()
    ports = service.ports

    assert ports.execution_state is execution_state
    assert ports.cycle_state is cycle_state
    assert ports.return_state is return_state
    assert ports.token_state is token_state
    assert ports.coverage_state is coverage_state
    assert isinstance(ports.start_envelope_gate_service, ReturnStartEnvelopeGateService)


def test_return_handoff_runtime_composes_direct_handoff_effect_service() -> None:
    from testbed.planner.primitive.effects.return_handoff_runtime import (
        PrimitiveReturnHandoffRuntime,
        PrimitiveReturnHandoffRuntimePorts,
    )

    execution_state = PrimitiveExecutionRuntimeState.fresh(initial_skill_name="return")
    cycle_state = PrimitiveCycleRuntimeState.fresh()
    events: list[str] = []

    runtime = PrimitiveReturnHandoffRuntime.from_ports(
        PrimitiveReturnHandoffRuntimePorts(
            config=_readiness_config(),
            action_dim=4,
            execution_state=execution_state,
            cycle_state=cycle_state,
            return_state=PrimitiveReturnRuntimeState.fresh(),
            token_state=PrimitiveTokenRuntimeState.fresh(),
            coverage_state=CoverageRuntimeState(),
            set_skill=lambda skill, reason: events.append(f"{skill}:{reason}"),
            ensure_return_target_plan_for_cycle=lambda obs: None,
            return_start_envelope_prior_bounds=lambda corridor_id: (None, None),
            return_start_envelope_prior_mapping=lambda corridor_id: None,
            should_pre_dig_align_before_dig=lambda: True,
            pre_dig_align_skill_name=PRE_DIG_ALIGN_SKILL_NAME,
        )
    )

    ports = runtime.direct_handoff_effect_service().ports
    port_fields = {field.name for field in fields(ReturnDirectHandoffEffectPorts)}

    assert ports.execution_state is execution_state
    assert ports.cycle_state is cycle_state
    assert ports.execution_state.skill_name == "return"
    assert "current_skill_name" not in port_fields
    assert "complete_return_transition" not in port_fields
    assert "next_skill_after_return_transition" not in port_fields
    assert "return_to_dig_handoff_ready" not in port_fields
    assert "return_to_dig_direct_handoff_ready" not in port_fields
    assert ports.return_target_planner_enabled is True
    assert ports.return_to_dig_start_envelope_direct_handoff_enabled is True
    assert ports.should_pre_dig_align_before_dig() is True
    assert ports.pre_dig_align_skill_name == PRE_DIG_ALIGN_SKILL_NAME


def test_requested_effect_runtime_path_uses_return_direct_handoff_service() -> None:
    obs = {"tag": "obs"}
    calls: list[str] = []

    class _FakeReturnHandoffRuntime:
        def apply_direct_handoff(
            self,
            applied_obs: dict[str, Any],
            *,
            reason: str,
        ) -> None:
            calls.append(f"runtime:{applied_obs['tag']}:{reason}")

    class _UnusedCoverageEffectRuntime:
        def reject_active_coverage_corridor(self, got_obs, *, reason):
            raise AssertionError("return-only effect must not reject coverage")

        def complete_coverage_dig(self, got_obs):
            raise AssertionError("return-only effect must not complete dig")

        def complete_coverage_dump(self, got_obs, *, reason):
            raise AssertionError("return-only effect must not complete dump")

    class _UnusedDigRecoveryService:
        def restart_after_failed_dig(self, reason, got_obs):
            raise AssertionError("return-only effect must not restart dig")

        def restart_dig_with_new_cut(self, reason):
            raise AssertionError("return-only effect must not restart dig")

        def replan_or_restart_pre_dig_align(
            self,
            got_obs,
            *,
            replan_reason,
            restart_reason,
        ):
            raise AssertionError("return-only effect must not restart pre-dig")

    runtime = PrimitiveRequestedEffectRuntime.from_ports(
        PrimitiveRequestedEffectRuntimePorts(
            cycle_state=PrimitiveCycleRuntimeState.fresh(),
            return_state=PrimitiveReturnRuntimeState.fresh(),
            set_skill=lambda skill, reason: None,
            return_transition_next_skill_name="dig",
            coverage_effect_runtime=_UnusedCoverageEffectRuntime(),
            dig_recovery_service=_UnusedDigRecoveryService(),
            return_handoff_runtime=_FakeReturnHandoffRuntime(),
            action_dim=4,
        )
    )

    runtime.apply(
        obs,
        (SetReturnOrDirectHandoffEffect(reason="dump_to_return_mass_low"),),
    )

    assert calls == ["runtime:obs:dump_to_return_mass_low"]
