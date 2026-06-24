"""Reset lifecycle rules for primitive planner public adapter."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.execution.cycle_state import PrimitiveCycleRuntimeState
from testbed.planner.primitive.execution.state import PrimitiveExecutionRuntimeState
from testbed.planner.primitive.execution.return_state import PrimitiveReturnRuntimeState
from testbed.planner.primitive.execution.scripted_bootstrap import (
    PrimitiveScriptedBootstrapRuntimeState,
)
from testbed.planner.primitive.execution.pre_dig_align import (
    PrimitivePreDigAlignRuntimeState,
)
from testbed.planner.primitive.facts.observation import (
    PrimitiveObservationInjectionRuntimeState,
)
from testbed.planner.primitive.token.state import PrimitiveTokenRuntimeState


@dataclass(frozen=True)
class PrimitiveResetLifecyclePorts:
    """Shell-owned reset hooks and read-only configuration snapshot."""

    all_policies: Callable[[], Sequence[Any]]
    reset_boundary_detector: Callable[[], None]
    bootstrap_end_mode: Callable[[], str]
    bootstrap_policy_available: Callable[[], bool]
    scripted_bootstrap_enabled: Callable[[], bool]
    should_pre_dig_align_before_dig: Callable[[], bool]
    action_dim: int
    bootstrap_skill_name: str = "bootstrap"
    pre_dig_align_skill_name: str = "pre_dig_align"
    dig_skill_name: str = "dig"


@dataclass
class PrimitiveResetLifecycleState:
    """Complete shell state snapshot produced by the reset lifecycle."""

    execution_state: PrimitiveExecutionRuntimeState
    skill_name: str
    prev_action: np.ndarray | None
    switch_reason: str
    cycle_state: PrimitiveCycleRuntimeState
    scripted_bootstrap_state: PrimitiveScriptedBootstrapRuntimeState
    return_state: PrimitiveReturnRuntimeState
    observation_injection_state: PrimitiveObservationInjectionRuntimeState
    token_state: PrimitiveTokenRuntimeState
    coverage_state: CoverageRuntimeState
    pre_dig_align_runtime_state: PrimitivePreDigAlignRuntimeState
    debug_transition_timeout: bool
    debug_transition_completed: bool

    def as_policy_field_updates(self) -> dict[str, Any]:
        """Map reset state to the legacy private field names owned by policy."""

        return {
            "_execution_state": self.execution_state,
            "_skill_name": self.skill_name,
            "_prev_action": self.prev_action,
            "_switch_reason": self.switch_reason,
            "_cycle_state": self.cycle_state,
            "_scripted_bootstrap_state": self.scripted_bootstrap_state,
            "_return_state": self.return_state,
            "_observation_injection_state": self.observation_injection_state,
            "_token_state": self.token_state,
            "_coverage_state": self.coverage_state,
            "_pre_dig_align_runtime_state": self.pre_dig_align_runtime_state,
        }


@dataclass(frozen=True)
class PrimitiveResetLifecycleService:
    """Own reset sequencing and legacy 4P reset-state defaults."""

    ports: PrimitiveResetLifecyclePorts

    @classmethod
    def from_ports(
        cls,
        ports: PrimitiveResetLifecyclePorts,
    ) -> "PrimitiveResetLifecycleService":
        return cls(ports=ports)

    def reset(self) -> PrimitiveResetLifecycleState:
        ports = self.ports
        for policy in ports.all_policies():
            policy.reset()
        ports.reset_boundary_detector()
        skill_name = self._initial_skill_name()
        action_dim = int(ports.action_dim)
        execution_state = PrimitiveExecutionRuntimeState.fresh(
            initial_skill_name=skill_name,
            switch_reason="reset",
        )
        cycle_state = PrimitiveCycleRuntimeState.fresh()
        token_state = PrimitiveTokenRuntimeState.fresh()
        observation_injection_state = PrimitiveObservationInjectionRuntimeState.fresh()
        return_state = PrimitiveReturnRuntimeState.fresh()
        scripted_bootstrap_state = PrimitiveScriptedBootstrapRuntimeState.fresh()
        return PrimitiveResetLifecycleState(
            execution_state=execution_state,
            skill_name=skill_name,
            prev_action=None,
            switch_reason="reset",
            cycle_state=cycle_state,
            scripted_bootstrap_state=scripted_bootstrap_state,
            return_state=return_state,
            observation_injection_state=observation_injection_state,
            token_state=token_state,
            coverage_state=CoverageRuntimeState(),
            pre_dig_align_runtime_state=(
                PrimitivePreDigAlignRuntimeState.fresh(action_dim=action_dim)
            ),
            debug_transition_timeout=False,
            debug_transition_completed=False,
        )

    def _initial_skill_name(self) -> str:
        ports = self.ports
        has_bootstrap = (
            str(ports.bootstrap_end_mode()) != "disabled"
            and (
                bool(ports.bootstrap_policy_available())
                or bool(ports.scripted_bootstrap_enabled())
            )
        )
        if has_bootstrap:
            return str(ports.bootstrap_skill_name)
        if bool(ports.should_pre_dig_align_before_dig()):
            return str(ports.pre_dig_align_skill_name)
        return str(ports.dig_skill_name)


__all__ = [
    "PrimitiveResetLifecyclePorts",
    "PrimitiveResetLifecycleService",
    "PrimitiveResetLifecycleState",
]
