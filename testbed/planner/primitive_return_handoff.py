"""Return handoff gate services for primitive planning."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.data.operator_first_v2_2 import RETURN_START_ENVELOPE_TOKEN_DIM
from testbed.data.schema import (
    ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX,
    ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX,
)
from testbed.planner.primitive_capabilities import PrimitiveObservationFacts
from testbed.planner.primitive_coverage_state import CoverageRuntimeState
from testbed.planner.primitive_cycle_state import PrimitiveCycleRuntimeState
from testbed.planner.primitive_execution_state import PrimitiveExecutionRuntimeState
from testbed.planner.primitive_return_state import PrimitiveReturnRuntimeState
from testbed.planner.primitive_token_state import PrimitiveTokenRuntimeState


@dataclass(frozen=True)
class ReturnDirectHandoffEffectPorts:
    """Shell mutation/read ports for applying return/direct-handoff effects."""

    execution_state: PrimitiveExecutionRuntimeState
    cycle_state: PrimitiveCycleRuntimeState
    set_skill: Callable[[str, str], None]
    return_target_planner_enabled: bool
    return_to_dig_start_envelope_direct_handoff_enabled: bool
    ensure_return_target_plan_for_cycle: Callable[[dict[str, Any]], None]
    readiness_service: ReturnHandoffReadinessService
    should_pre_dig_align_before_dig: Callable[[], bool]
    pre_dig_align_skill_name: str
    dig_skill_name: str = "dig"


@dataclass(frozen=True)
class ReturnDirectHandoffEffectResult:
    """Observable outcome from applying a return/direct-handoff effect."""

    direct_handoff_applied: bool
    next_skill: str = ""
    switch_reason: str = ""


@dataclass(frozen=True)
class ReturnDirectHandoffEffectService:
    """Apply the ordered return/direct-handoff effect-side transition sequence."""

    ports: ReturnDirectHandoffEffectPorts

    def apply(
        self,
        obs: dict[str, Any],
        *,
        reason: str,
    ) -> ReturnDirectHandoffEffectResult:
        self.ports.set_skill("return", str(reason))
        return self.try_direct_handoff(obs)

    def try_direct_handoff(
        self,
        obs: dict[str, Any],
    ) -> ReturnDirectHandoffEffectResult:
        ports = self.ports
        if str(ports.execution_state.skill_name) != "return":
            return ReturnDirectHandoffEffectResult(direct_handoff_applied=False)
        if not ports.return_target_planner_enabled:
            return ReturnDirectHandoffEffectResult(direct_handoff_applied=False)
        if not ports.return_to_dig_start_envelope_direct_handoff_enabled:
            return ReturnDirectHandoffEffectResult(direct_handoff_applied=False)

        ports.ensure_return_target_plan_for_cycle(obs)
        readiness = ports.readiness_service
        handoff_ready = bool(readiness.handoff_ready(obs))
        direct_handoff_ready = bool(
            readiness.direct_handoff_ready(obs, handoff_ready=handoff_ready)
        )
        if not direct_handoff_ready:
            return ReturnDirectHandoffEffectResult(direct_handoff_applied=False)

        ports.cycle_state.complete_return_transition()
        next_skill = (
            str(ports.pre_dig_align_skill_name)
            if ports.should_pre_dig_align_before_dig()
            else str(ports.dig_skill_name)
        )
        switch_reason = f"return_to_{next_skill}_start_envelope_ready"
        ports.set_skill(next_skill, switch_reason)
        return ReturnDirectHandoffEffectResult(
            direct_handoff_applied=True,
            next_skill=next_skill,
            switch_reason=switch_reason,
        )


@dataclass(frozen=True)
class ReturnStartEnvelopeGateConfig:
    """Static gate configuration for return-to-dig start-envelope readiness."""

    enabled: bool
    action_dim: int
    spatial_tolerance: float
    depth_tolerance_m: float
    local_depth_tolerance_m: float
    plane_depth_tolerance_m: float
    plane_depth_mode: str
    qpos_tolerance: float
    require_contact: bool


@dataclass(frozen=True)
class ReturnStartEnvelopeGateInputs:
    """Per-tick inputs for return-to-dig start-envelope readiness."""

    token: Any
    env_state: Any
    qpos: Any
    prior_bounds: Callable[[], tuple[np.ndarray | None, np.ndarray | None]]
    prior_mapping: Callable[[], dict[str, object] | None]
    use_prior_spatial_bounds: bool
    use_prior_qpos_bounds: bool


@dataclass(frozen=True)
class ReturnStartEnvelopeGateResult:
    """Computed return-to-dig start-envelope gate state."""

    ready: bool
    error: float
    checks: dict[str, Any]


@dataclass(frozen=True)
class ReturnStartEnvelopeGateService:
    """Compute return-to-dig start-envelope readiness and diagnostic checks."""

    config: ReturnStartEnvelopeGateConfig

    def evaluate(
        self,
        inputs: ReturnStartEnvelopeGateInputs,
    ) -> ReturnStartEnvelopeGateResult:
        config = self.config
        if not config.enabled:
            return ReturnStartEnvelopeGateResult(
                ready=True,
                error=float("nan"),
                checks={},
            )

        token = np.asarray(inputs.token, dtype=np.float32).reshape(-1)
        if token.shape[0] != RETURN_START_ENVELOPE_TOKEN_DIM:
            return ReturnStartEnvelopeGateResult(
                ready=True,
                error=float("nan"),
                checks={"missing_token": True},
            )
        if float(token[16]) <= 0.5 and float(token[17]) <= 0.5:
            return ReturnStartEnvelopeGateResult(
                ready=True,
                error=float("nan"),
                checks={"invalid_token": True},
            )

        lower, upper = inputs.prior_bounds()
        prior_mapping = inputs.prior_mapping()
        state = _GateState()
        env_state = np.asarray(inputs.env_state, dtype=np.float32).reshape(-1)
        local_depth_prior = (
            None
            if prior_mapping is None
            else prior_mapping.get("dig_start_local_depth_m")
        )
        local_depth_prior_used = False
        require_contact = bool(config.require_contact or float(token[6]) > 0.5)

        if float(token[17]) > 0.5:
            if len(env_state) > ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX:
                spatial_tol = config.spatial_tolerance
                low, high = _bounds_for(
                    token=token,
                    lower=lower,
                    upper=upper,
                    index=0,
                    tolerance=spatial_tol,
                    use_prior_bounds=inputs.use_prior_spatial_bounds,
                )
                state.add_check(
                    "long_norm",
                    float(env_state[ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX]),
                    low,
                    high,
                )
                low, high = _bounds_for(
                    token=token,
                    lower=lower,
                    upper=upper,
                    index=1,
                    tolerance=spatial_tol,
                    use_prior_bounds=inputs.use_prior_spatial_bounds,
                )
                state.add_check(
                    "short_norm",
                    float(env_state[ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX]),
                    low,
                    high,
                )
            else:
                state.ready = False
                state.checks["spatial_missing"] = True

            if len(env_state) > ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX:
                local_value = float(
                    env_state[ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX]
                )
                if isinstance(local_depth_prior, dict):
                    local_depth_prior_used = True
                    local_tol = config.local_depth_tolerance_m
                    p05 = float(local_depth_prior.get("p05", token[4]))
                    p50 = float(local_depth_prior.get("p50", token[2]))
                    p95 = float(local_depth_prior.get("p95", token[5]))
                    state.add_check(
                        "local_depth_m",
                        local_value,
                        p05 - local_tol,
                        p95 + local_tol,
                    )
                    state.checks["local_depth_m"].update(
                        {
                            "mode": "prior_range",
                            "target": float(p50),
                            "p05": float(p05),
                            "p50": float(p50),
                            "p95": float(p95),
                        }
                    )
                else:
                    depth_tol = config.depth_tolerance_m
                    low = float(token[4]) - depth_tol
                    high = float(token[5]) + depth_tol
                    state.add_check("local_depth_m", local_value, low, high)
                    state.checks["local_depth_m"].update({"mode": "token_range"})
            else:
                state.ready = False
                state.checks["local_depth_missing"] = True

            plane_depth_prior = (
                None
                if prior_mapping is None
                else prior_mapping.get("dig_start_plane_depth_m")
            )
            if isinstance(plane_depth_prior, dict):
                plane_tol = config.plane_depth_tolerance_m
                p05 = float(plane_depth_prior.get("p05", token[2]))
                p50 = float(plane_depth_prior.get("p50", token[2]))
                p95 = float(plane_depth_prior.get("p95", token[5]))
                mode = str(config.plane_depth_mode)
                if mode == "target_band":
                    low = p50 - plane_tol
                    high = p50 + plane_tol
                elif mode == "p50_floor":
                    plane_floor = (
                        p05 if local_depth_prior_used and require_contact else p50
                    )
                    low = plane_floor - plane_tol
                    high = p95 + plane_tol
                else:
                    low = p05 - plane_tol
                    high = p95 + plane_tol
                state.add_check(
                    "plane_depth_m",
                    float(env_state[ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX]),
                    low,
                    high,
                )
                state.checks["plane_depth_m"].update(
                    {
                        "mode": str(mode),
                        "target": float(p50),
                        "p05": float(p05),
                        "p50": float(p50),
                        "p95": float(p95),
                        "floor_source": (
                            "p05_local_contact_prior"
                            if mode == "p50_floor"
                            and local_depth_prior_used
                            and require_contact
                            else "p50"
                            if mode == "p50_floor"
                            else "range"
                        ),
                    }
                )

            if require_contact:
                if len(env_state) > ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX:
                    contact = float(env_state[ENV_STATE_BUCKET_CONTACT_DIG_AREA_MASK_IDX])
                    ok = bool(contact > 0.5)
                    state.ready = bool(state.ready and ok)
                    state.checks["dig_contact"] = {
                        "value": contact,
                        "ok": ok,
                        "required_by_config": bool(config.require_contact),
                        "required_by_token": bool(float(token[6]) > 0.5),
                    }
                else:
                    state.ready = False
                    state.checks["dig_contact_missing"] = True

        if float(token[16]) > 0.5:
            qpos = np.asarray(inputs.qpos, dtype=np.float32).reshape(-1)
            if qpos.shape[0] >= 4:
                qpos_tol = config.qpos_tolerance
                for offset in range(4):
                    index = 7 + offset
                    if (
                        inputs.use_prior_qpos_bounds
                        and lower is not None
                        and upper is not None
                    ):
                        low = float(lower[index]) - qpos_tol
                        high = float(upper[index]) + qpos_tol
                    else:
                        half_width = max(float(token[11 + offset]), qpos_tol)
                        low = float(token[index]) - half_width - qpos_tol
                        high = float(token[index]) + half_width + qpos_tol
                    state.add_check(f"qpos_{offset}", float(qpos[offset]), low, high)
            else:
                state.ready = False
                state.checks["qpos_missing"] = True

        return ReturnStartEnvelopeGateResult(
            ready=bool(state.ready),
            error=float(state.max_error),
            checks=state.checks,
        )


@dataclass(frozen=True)
class ReturnHandoffReadinessConfig:
    """Static config facts for return-to-dig handoff readiness."""

    return_target_planner_enabled: bool
    max_entry_error_m: float | None
    max_bucket_mass_kg: float
    start_envelope_direct_handoff_enabled: bool
    start_envelope_gate: ReturnStartEnvelopeGateConfig


@dataclass(frozen=True)
class ReturnHandoffReadinessPorts:
    """Focused owners and explicit algorithm ports for return handoff readiness."""

    config: ReturnHandoffReadinessConfig
    action_dim: int
    execution_state: PrimitiveExecutionRuntimeState
    cycle_state: PrimitiveCycleRuntimeState
    return_state: PrimitiveReturnRuntimeState
    token_state: PrimitiveTokenRuntimeState
    coverage_state: CoverageRuntimeState
    start_envelope_gate_service: ReturnStartEnvelopeGateService
    ensure_return_target_plan_for_cycle: Callable[[dict[str, Any]], None]
    return_start_envelope_prior_bounds: Callable[
        [int],
        tuple[np.ndarray | None, np.ndarray | None],
    ]
    return_start_envelope_prior_mapping: Callable[[int], dict[str, object] | None]


@dataclass(frozen=True)
class ReturnHandoffReadinessService:
    """Own return-to-dig handoff readiness and start-envelope cache updates."""

    ports: ReturnHandoffReadinessPorts

    def entry_target(self) -> tuple[float, float] | None:
        ports = self.ports
        raw_fields = ports.token_state.pending_dig_cut_raw_fields
        if (
            raw_fields is not None
            and int(ports.token_state.pending_dig_cut_cycle_id)
            == int(ports.cycle_state.cycle_index) + 1
        ):
            entry_x = float(raw_fields.get("operator_entry_x_m", float("nan")))
            entry_z = float(raw_fields.get("operator_entry_z_m", float("nan")))
            if np.isfinite(entry_x) and np.isfinite(entry_z):
                return entry_x, entry_z
        corridor = ports.coverage_state.active_corridor()
        if corridor is None:
            return None
        return float(corridor.entry_x_m), float(corridor.entry_z_m)

    def entry_error_for_obs(self, obs: dict[str, Any]) -> float:
        target = self.entry_target()
        pose = self._observation(obs).bucket_dig_area_pose()
        if target is None or pose is None:
            return float("nan")
        bucket_x, _, bucket_z = pose
        entry_x, entry_z = target
        if not all(np.isfinite(value) for value in (bucket_x, bucket_z, entry_x, entry_z)):
            return float("nan")
        return float(
            np.hypot(float(bucket_x) - float(entry_x), float(bucket_z) - float(entry_z))
        )

    def entry_close(self, obs: dict[str, Any]) -> bool:
        ports = self.ports
        if (
            str(ports.execution_state.skill_name) == "return"
            and ports.config.return_target_planner_enabled
        ):
            ports.ensure_return_target_plan_for_cycle(obs)
        entry_error = self.entry_error_for_obs(obs)
        max_entry_error = ports.config.max_entry_error_m
        if max_entry_error is None:
            close = True
        elif not np.isfinite(entry_error):
            close = True
        else:
            close = bool(float(entry_error) <= float(max_entry_error))
        ports.return_state.set_entry_close_result(
            error_m=float(entry_error),
            close=close,
        )
        return bool(close)

    def handoff_ready(self, obs: dict[str, Any]) -> bool:
        entry_close = self.entry_close(obs)
        envelope_ready = self.start_envelope_ready(obs)
        return bool(entry_close and envelope_ready)

    def direct_handoff_ready(
        self,
        obs: dict[str, Any],
        *,
        handoff_ready: bool | None = None,
    ) -> bool:
        config = self.ports.config
        if not config.start_envelope_direct_handoff_enabled:
            return False
        if not config.start_envelope_gate.enabled:
            return False
        ready = self.handoff_ready(obs) if handoff_ready is None else bool(handoff_ready)
        if not ready:
            return False
        return bool(
            self._observation(obs).mass_in_bucket_kg <= config.max_bucket_mass_kg
        )

    def start_envelope_ready(self, obs: dict[str, Any]) -> bool:
        result = self.ports.start_envelope_gate_service.evaluate(
            self.start_envelope_gate_inputs(obs)
        )
        self.apply_start_envelope_gate_result(result)
        return bool(result.ready)

    def start_envelope_gate_config(self) -> ReturnStartEnvelopeGateConfig:
        return self.ports.config.start_envelope_gate

    def start_envelope_gate_inputs(
        self,
        obs: dict[str, Any],
    ) -> ReturnStartEnvelopeGateInputs:
        ports = self.ports
        observation = self._observation(obs)
        corridor_id = int(ports.token_state.pending_dig_cut_corridor_id)
        return ReturnStartEnvelopeGateInputs(
            token=ports.token_state.return_start_envelope_tokens,
            env_state=observation.env_state,
            qpos=observation.qpos,
            prior_bounds=(
                lambda: ports.return_start_envelope_prior_bounds(corridor_id)
            ),
            prior_mapping=(
                lambda: ports.return_start_envelope_prior_mapping(corridor_id)
            ),
            use_prior_spatial_bounds=(
                ports.token_state.return_start_envelope_use_prior_spatial_bounds
            ),
            use_prior_qpos_bounds=(
                ports.token_state.return_start_envelope_use_prior_qpos_bounds
            ),
        )

    def apply_start_envelope_gate_result(
        self,
        result: ReturnStartEnvelopeGateResult,
    ) -> None:
        self.ports.return_state.apply_start_envelope_gate_result(
            ready=bool(result.ready),
            error=float(result.error),
            checks=dict(result.checks),
        )

    def _observation(self, obs: dict[str, Any]) -> PrimitiveObservationFacts:
        return PrimitiveObservationFacts.from_obs(
            obs,
            action_dim=self.ports.action_dim,
        )


@dataclass
class _GateState:
    ready: bool = True
    max_error: float = 0.0
    checks: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.checks is None:
            self.checks = {}

    def add_check(self, name: str, value: float, low: float, high: float) -> bool:
        finite = bool(np.isfinite(value) and np.isfinite(low) and np.isfinite(high))
        if not finite:
            ok = False
            error = float("inf")
        else:
            error = max(float(low) - float(value), float(value) - float(high), 0.0)
            ok = bool(error <= 1.0e-6)
            self.max_error = max(self.max_error, float(error))
        self.ready = bool(self.ready and ok)
        assert self.checks is not None
        self.checks[name] = {
            "value": float(value),
            "min": float(low),
            "max": float(high),
            "ok": bool(ok),
            "error": float(error),
        }
        return bool(ok)


def _bounds_for(
    *,
    token: np.ndarray,
    lower: np.ndarray | None,
    upper: np.ndarray | None,
    index: int,
    tolerance: float,
    use_prior_bounds: bool,
) -> tuple[float, float]:
    if use_prior_bounds and lower is not None and upper is not None:
        low = float(lower[index]) - float(tolerance)
        high = float(upper[index]) + float(tolerance)
    else:
        low = float(token[index]) - float(tolerance)
        high = float(token[index]) + float(tolerance)
    return low, high


__all__ = [
    "ReturnHandoffReadinessConfig",
    "ReturnHandoffReadinessPorts",
    "ReturnHandoffReadinessService",
    "ReturnDirectHandoffEffectPorts",
    "ReturnDirectHandoffEffectResult",
    "ReturnDirectHandoffEffectService",
    "ReturnStartEnvelopeGateConfig",
    "ReturnStartEnvelopeGateInputs",
    "ReturnStartEnvelopeGateResult",
    "ReturnStartEnvelopeGateService",
]
