"""Composition boundary for primitive return-handoff runtime services."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.effects.return_handoff import (
    ReturnDirectHandoffEffectPorts,
    ReturnDirectHandoffEffectService,
    ReturnHandoffReadinessConfig,
    ReturnHandoffReadinessPorts,
    ReturnHandoffReadinessService,
    ReturnStartEnvelopeGateService,
)
from testbed.planner.primitive.execution.cycle_state import PrimitiveCycleRuntimeState
from testbed.planner.primitive.execution.return_state import PrimitiveReturnRuntimeState
from testbed.planner.primitive.execution.state import PrimitiveExecutionRuntimeState
from testbed.planner.primitive.token.state import PrimitiveTokenRuntimeState


@dataclass(frozen=True)
class PrimitiveReturnHandoffRuntimePorts:
    """Explicit state, config, and service inputs for return-handoff runtime."""

    config: ReturnHandoffReadinessConfig
    action_dim: int
    execution_state: PrimitiveExecutionRuntimeState
    cycle_state: PrimitiveCycleRuntimeState
    return_state: PrimitiveReturnRuntimeState
    token_state: PrimitiveTokenRuntimeState
    coverage_state: CoverageRuntimeState
    set_skill: Callable[[str, str], None]
    ensure_return_target_plan_for_cycle: Callable[[dict[str, Any]], None]
    return_start_envelope_prior_bounds: Callable[
        [int],
        tuple[np.ndarray | None, np.ndarray | None],
    ]
    return_start_envelope_prior_mapping: Callable[[int], dict[str, object] | None]
    should_pre_dig_align_before_dig: Callable[[], bool]
    pre_dig_align_skill_name: str
    dig_skill_name: str = "dig"
    final_handoff_guard: Callable[[dict[str, Any]], Any] = (
        lambda _obs: None
    )
    request_terminal_neutral: Callable[
        [dict[str, Any], str],
        None,
    ] = lambda _obs, _reason: None


@dataclass(frozen=True)
class PrimitiveReturnHandoffRuntime:
    """Compose return-handoff readiness and direct-handoff effect services."""

    ports: PrimitiveReturnHandoffRuntimePorts

    @classmethod
    def from_ports(
        cls,
        ports: PrimitiveReturnHandoffRuntimePorts,
    ) -> PrimitiveReturnHandoffRuntime:
        return cls(ports=ports)

    def readiness_service(self) -> ReturnHandoffReadinessService:
        ports = self.ports
        return ReturnHandoffReadinessService(
            ports=ReturnHandoffReadinessPorts(
                config=ports.config,
                action_dim=int(ports.action_dim),
                execution_state=ports.execution_state,
                cycle_state=ports.cycle_state,
                return_state=ports.return_state,
                token_state=ports.token_state,
                coverage_state=ports.coverage_state,
                start_envelope_gate_service=ReturnStartEnvelopeGateService(
                    config=ports.config.start_envelope_gate
                ),
                ensure_return_target_plan_for_cycle=(
                    ports.ensure_return_target_plan_for_cycle
                ),
                return_start_envelope_prior_bounds=(
                    ports.return_start_envelope_prior_bounds
                ),
                return_start_envelope_prior_mapping=(
                    ports.return_start_envelope_prior_mapping
                ),
            )
        )

    def direct_handoff_effect_service(self) -> ReturnDirectHandoffEffectService:
        ports = self.ports
        config = ports.config
        return ReturnDirectHandoffEffectService(
            ports=ReturnDirectHandoffEffectPorts(
                execution_state=ports.execution_state,
                cycle_state=ports.cycle_state,
                set_skill=ports.set_skill,
                return_target_planner_enabled=(
                    config.return_target_planner_enabled
                ),
                return_to_dig_start_envelope_direct_handoff_enabled=(
                    config.start_envelope_direct_handoff_enabled
                ),
                ensure_return_target_plan_for_cycle=(
                    ports.ensure_return_target_plan_for_cycle
                ),
                readiness_service=self.readiness_service(),
                should_pre_dig_align_before_dig=(
                    ports.should_pre_dig_align_before_dig
                ),
                pre_dig_align_skill_name=str(ports.pre_dig_align_skill_name),
                dig_skill_name=str(ports.dig_skill_name),
                final_handoff_guard=ports.final_handoff_guard,
                request_terminal_neutral=ports.request_terminal_neutral,
            )
        )

    def apply_direct_handoff(self, obs: dict[str, Any], *, reason: str) -> None:
        self.direct_handoff_effect_service().apply(obs, reason=reason)


__all__ = [
    "PrimitiveReturnHandoffRuntime",
    "PrimitiveReturnHandoffRuntimePorts",
]
