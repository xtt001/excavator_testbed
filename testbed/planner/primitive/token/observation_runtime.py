"""Token observation runtime composition for primitive policy observations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.facts.observation import (
    PrimitiveObservationInjectionRuntimeState,
    PrimitivePolicyObservationAssembler,
    PrimitivePolicyObservationAssemblerPorts,
    PrimitivePolicyObservationAssemblyResult,
)
from testbed.planner.primitive.token.runtime import (
    PrimitiveTokenRuntimeCoordinator,
    PrimitiveTokenRuntimePorts,
    ReturnStartEnvelopeTokenBuilder,
    ReturnTargetPlanTuple,
)
from testbed.planner.primitive.token.state import PrimitiveTokenRuntimeState


@dataclass(frozen=True)
class PrimitiveTokenObservationRuntimePorts:
    """Typed ports for token sequencing and policy observation assembly."""

    observation_injection_state: PrimitiveObservationInjectionRuntimeState
    token_state: PrimitiveTokenRuntimeState
    coverage_state: CoverageRuntimeState

    goal_tokens: Callable[[], Any | None]
    current_skill_name: Callable[[], str]
    bootstrap_policy_available: Callable[[], bool]
    cycle_index: Callable[[], int]
    dig_cut_planner_enabled: Callable[[], bool]
    dig_cut_hold_token_until_skill_exit: Callable[[], bool]
    coverage_terminal_stop_requested: Callable[[], bool]
    return_target_planner_enabled: Callable[[], bool]
    return_target_hold_token_until_skill_exit: Callable[[], bool]

    build_dig_cut_tokens_for_obs: Callable[[dict[str, Any]], np.ndarray]
    build_dig_depth_profile_tokens_for_obs: Callable[[dict[str, Any]], np.ndarray]
    build_next_dig_cut_plan_for_return: Callable[
        [dict[str, Any]],
        ReturnTargetPlanTuple,
    ]
    build_return_start_envelope_tokens_for_obs: ReturnStartEnvelopeTokenBuilder
    plan_return_relocate_tokens: Callable[[np.ndarray], np.ndarray]

    dig_skill_name: str = "dig"
    return_skill_name: str = "return"
    bootstrap_skill_name: str = "bootstrap"


@dataclass(frozen=True)
class PrimitiveTokenObservationRuntime:
    """Compose token runtime sequencing with policy observation assembly."""

    ports: PrimitiveTokenObservationRuntimePorts

    @classmethod
    def from_ports(
        cls,
        ports: PrimitiveTokenObservationRuntimePorts,
    ) -> "PrimitiveTokenObservationRuntime":
        return cls(ports=ports)

    def policy_obs(self, obs: dict[str, Any]) -> dict[str, Any]:
        self.clear_policy_observation_injected_flags()
        result = self.policy_observation_assembler().assemble(obs)
        self.apply_policy_observation_assembly(result)
        return result.policy_obs

    def policy_observation_assembler(self) -> PrimitivePolicyObservationAssembler:
        return PrimitivePolicyObservationAssembler.from_ports(
            self.policy_observation_assembler_ports()
        )

    def policy_observation_assembler_ports(
        self,
    ) -> PrimitivePolicyObservationAssemblerPorts:
        return PrimitivePolicyObservationAssemblerPorts(
            goal_tokens=self.ports.goal_tokens,
            dig_cut_tokens=lambda obs: self.dig_cut_tokens_for_obs(obs),
            dig_depth_profile_tokens=(
                lambda obs: self.dig_depth_profile_tokens_for_obs(obs)
            ),
            return_target_tokens=lambda obs: self.return_target_tokens_for_obs(obs),
            return_relocate_tokens=(
                lambda obs: self.return_relocate_tokens_for_obs(obs)
            ),
            return_start_envelope_tokens=(
                lambda obs: self.return_start_envelope_tokens_for_obs(obs)
            ),
        )

    def clear_policy_observation_injected_flags(self) -> None:
        self.ports.observation_injection_state.clear()

    def apply_policy_observation_assembly(
        self,
        result: PrimitivePolicyObservationAssemblyResult,
    ) -> None:
        self.ports.observation_injection_state.apply_token_injection_state(
            result.token_injection_state
        )

    def return_target_tokens_for_obs(
        self,
        obs: dict[str, Any],
    ) -> np.ndarray | None:
        return self.primitive_token_runtime().return_target_tokens_for_obs(obs)

    def return_relocate_tokens_for_obs(
        self,
        obs: dict[str, Any],
    ) -> np.ndarray | None:
        return self.primitive_token_runtime().return_relocate_tokens_for_obs(obs)

    def return_start_envelope_tokens_for_obs(
        self,
        obs: dict[str, Any],
    ) -> np.ndarray | None:
        return self.primitive_token_runtime().return_start_envelope_tokens_for_obs(
            obs
        )

    def ensure_return_target_plan_for_cycle(self, obs: dict[str, Any]) -> None:
        self.primitive_token_runtime().ensure_return_target_plan_for_cycle(obs)

    def dig_cut_tokens_for_obs(self, obs: dict[str, Any]) -> np.ndarray | None:
        return self.primitive_token_runtime().dig_cut_tokens_for_obs(obs)

    def dig_depth_profile_tokens_for_obs(
        self,
        obs: dict[str, Any],
    ) -> np.ndarray | None:
        return self.primitive_token_runtime().dig_depth_profile_tokens_for_obs(obs)

    def ensure_dig_cut_plan_for_cycle(self, obs: dict[str, Any]) -> None:
        self.primitive_token_runtime().ensure_dig_cut_plan_for_cycle(obs)

    def primitive_token_runtime(self) -> PrimitiveTokenRuntimeCoordinator:
        return PrimitiveTokenRuntimeCoordinator.from_ports(
            self.primitive_token_runtime_ports()
        )

    def primitive_token_runtime_ports(self) -> PrimitiveTokenRuntimePorts:
        ports = self.ports
        return PrimitiveTokenRuntimePorts(
            state=ports.token_state,
            coverage_state=ports.coverage_state,
            current_skill_name=ports.current_skill_name,
            bootstrap_policy_available=ports.bootstrap_policy_available,
            cycle_index=ports.cycle_index,
            dig_cut_planner_enabled=ports.dig_cut_planner_enabled,
            dig_cut_hold_token_until_skill_exit=(
                ports.dig_cut_hold_token_until_skill_exit
            ),
            coverage_terminal_stop_requested=(
                ports.coverage_terminal_stop_requested
            ),
            return_target_planner_enabled=ports.return_target_planner_enabled,
            return_target_hold_token_until_skill_exit=(
                ports.return_target_hold_token_until_skill_exit
            ),
            build_dig_cut_tokens_for_obs=ports.build_dig_cut_tokens_for_obs,
            build_dig_depth_profile_tokens_for_obs=(
                ports.build_dig_depth_profile_tokens_for_obs
            ),
            build_next_dig_cut_plan_for_return=(
                ports.build_next_dig_cut_plan_for_return
            ),
            build_return_start_envelope_tokens_for_obs=(
                ports.build_return_start_envelope_tokens_for_obs
            ),
            plan_return_relocate_tokens=ports.plan_return_relocate_tokens,
            dig_skill_name=ports.dig_skill_name,
            return_skill_name=ports.return_skill_name,
            bootstrap_skill_name=ports.bootstrap_skill_name,
        )


__all__ = [
    "PrimitiveTokenObservationRuntime",
    "PrimitiveTokenObservationRuntimePorts",
]
