"""Action dispatch and low-level policy selection for primitive planning."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.execution.cycle_state import PrimitiveCycleRuntimeState
from testbed.planner.primitive.execution.state import PrimitiveExecutionRuntimeState


BOOTSTRAP_SKILL_NAME = "bootstrap"
DIG_SKILL_NAME = "dig"
PRE_DIG_ALIGN_SKILL_NAME = "pre_dig_align"


@dataclass(frozen=True)
class PrimitiveActionDispatchPorts:
    """Typed shell ports required for primitive action dispatch."""

    execution_state: PrimitiveExecutionRuntimeState
    cycle_state: PrimitiveCycleRuntimeState
    coverage_state: CoverageRuntimeState
    action_dim: int
    skill_policies: Mapping[str, Any]
    base_policy_order: Sequence[str]
    optional_policy_order: Sequence[str]
    first_dig_policy: Any | None
    bootstrap_policy: Any | None
    policy_observation: Callable[[dict[str, Any]], dict[str, Any]]
    scripted_bootstrap_enabled: Callable[[], bool]
    scripted_bootstrap_action: Callable[[dict[str, Any]], Any]
    pre_dig_align_action: Callable[[dict[str, Any]], Any]
    bootstrap_skill_name: str = BOOTSTRAP_SKILL_NAME
    dig_skill_name: str = DIG_SKILL_NAME
    pre_dig_align_skill_name: str = PRE_DIG_ALIGN_SKILL_NAME


@dataclass(frozen=True)
class PrimitiveActionDispatchService:
    """Select low-level policies and dispatch primitive tick actions."""

    ports: PrimitiveActionDispatchPorts

    @classmethod
    def from_ports(
        cls,
        ports: PrimitiveActionDispatchPorts,
    ) -> "PrimitiveActionDispatchService":
        return cls(ports=ports)

    def dispatch_action(self, obs: dict[str, Any]) -> Any:
        ports = self.ports
        skill_name = self._skill_name()
        if (
            skill_name == ports.bootstrap_skill_name
            and ports.scripted_bootstrap_enabled()
        ):
            return ports.scripted_bootstrap_action(obs)
        if skill_name == ports.pre_dig_align_skill_name:
            return np.asarray(
                ports.pre_dig_align_action(obs),
                dtype=np.float32,
            ).reshape(int(ports.action_dim))
        policy = self.active_policy()
        policy_obs = ports.policy_observation(obs)
        return np.asarray(policy.predict(policy_obs), dtype=np.float32).reshape(
            int(ports.action_dim)
        )

    def active_policy(self) -> Any:
        ports = self.ports
        skill_name = self._skill_name()
        if skill_name == ports.bootstrap_skill_name:
            if ports.bootstrap_policy is None:
                raise RuntimeError(
                    "bootstrap skill is active but bootstrap_policy is None."
                )
            return ports.bootstrap_policy
        if skill_name == ports.dig_skill_name and self.first_dig_policy_active():
            if ports.first_dig_policy is None:
                raise RuntimeError("first dig policy is active but missing.")
            return ports.first_dig_policy
        if skill_name in ports.skill_policies:
            return ports.skill_policies[skill_name]
        raise RuntimeError(f"Unknown primitive skill {skill_name!r}.")

    def all_policies(self) -> list[Any]:
        policies = [self.ports.skill_policies[name] for name in self.ports.base_policy_order]
        for name in self.ports.optional_policy_order:
            policy = self._optional_policy(name)
            if policy is not None:
                policies.append(policy)
        return policies

    def first_dig_policy_active(self) -> bool:
        ports = self.ports
        return bool(
            ports.first_dig_policy is not None
            and self._skill_name() == ports.dig_skill_name
            and int(ports.cycle_state.cycle_index) == 0
            and int(ports.coverage_state.coverage_completed_dump_count) <= 0
        )

    def _skill_name(self) -> str:
        return str(self.ports.execution_state.skill_name)

    def _optional_policy(self, name: str) -> Any | None:
        if name == "first_dig":
            return self.ports.first_dig_policy
        if name == "bootstrap":
            return self.ports.bootstrap_policy
        return self.ports.skill_policies.get(name)


__all__ = [
    "PrimitiveActionDispatchPorts",
    "PrimitiveActionDispatchService",
]
