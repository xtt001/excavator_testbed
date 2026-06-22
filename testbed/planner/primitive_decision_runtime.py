"""Decision runtime and backend selection for primitive planner ticks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from testbed.planner.primitive_backend import (
    LegacyFSMBranchSet,
    LegacyFSMCompatibilityDecisionBackend,
    LegacyFSMRequestedDecisionBackend,
)
from testbed.planner.primitive_decision import (
    PrimitiveDecisionContractError,
    PrimitiveDecisionResult,
)
from testbed.planner.primitive_decision_context import PrimitiveDecisionContext
from testbed.planner.primitive_execution import PrimitiveTickPreparation


LEGACY_FSM_DECISION_BACKEND_NAME = "legacy_fsm"
SUPPORTED_DECISION_BACKENDS = (LEGACY_FSM_DECISION_BACKEND_NAME,)


@dataclass(frozen=True)
class PrimitiveDecisionRuntimeConfig:
    """Configuration for selecting the primitive decision backend."""

    backend_name: str = LEGACY_FSM_DECISION_BACKEND_NAME


@dataclass(frozen=True)
class PrimitiveDecisionRuntimePorts:
    """Typed backend factory ports for the primitive decision runtime."""

    legacy_fsm_branch_set: Callable[[], LegacyFSMBranchSet]


@dataclass(frozen=True)
class PrimitiveDecisionRuntime:
    """Select and invoke the primitive decision backend for a tick."""

    ports: PrimitiveDecisionRuntimePorts
    config: PrimitiveDecisionRuntimeConfig = PrimitiveDecisionRuntimeConfig()

    @classmethod
    def from_ports(
        cls,
        ports: PrimitiveDecisionRuntimePorts,
        *,
        config: PrimitiveDecisionRuntimeConfig | None = None,
    ) -> "PrimitiveDecisionRuntime":
        return cls(
            ports=ports,
            config=config or PrimitiveDecisionRuntimeConfig(),
        )

    def decide_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult:
        return self.decide_context(
            PrimitiveDecisionContext.from_tick(
                obs=obs,
                boundary_event=boundary_event,
                preparation=preparation,
            )
        )

    def decide_context(
        self,
        context: PrimitiveDecisionContext,
    ) -> PrimitiveDecisionResult:
        backend = self._requested_backend()
        return backend.decide_context(context)

    def decide_legacy_compatibility_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult | None:
        return self.decide_legacy_compatibility_context(
            PrimitiveDecisionContext.from_tick(
                obs=obs,
                boundary_event=boundary_event,
                preparation=preparation,
            )
        )

    def decide_legacy_compatibility_context(
        self,
        context: PrimitiveDecisionContext,
    ) -> PrimitiveDecisionResult | None:
        backend = self._compatibility_backend()
        return backend.decide_context(context)

    def legacy_fsm_branch_set(self) -> LegacyFSMBranchSet:
        self._ensure_supported_backend()
        return self.ports.legacy_fsm_branch_set()

    def legacy_fsm_requested_decision_backend(
        self,
    ) -> LegacyFSMRequestedDecisionBackend:
        return self.legacy_fsm_branch_set().requested_decision_backend()

    def legacy_fsm_compatibility_decision_backend(
        self,
    ) -> LegacyFSMCompatibilityDecisionBackend:
        return self.legacy_fsm_branch_set().compatibility_decision_backend()

    def _requested_backend(self) -> LegacyFSMRequestedDecisionBackend:
        self._ensure_supported_backend()
        return self.legacy_fsm_requested_decision_backend()

    def _compatibility_backend(self) -> LegacyFSMCompatibilityDecisionBackend:
        self._ensure_supported_backend()
        return self.legacy_fsm_compatibility_decision_backend()

    def _backend_name(self) -> str:
        return str(self.config.backend_name).strip().lower()

    def _ensure_supported_backend(self) -> None:
        backend_name = self._backend_name()
        if backend_name == LEGACY_FSM_DECISION_BACKEND_NAME:
            return
        supported = ", ".join(SUPPORTED_DECISION_BACKENDS)
        raise PrimitiveDecisionContractError(
            "unsupported primitive decision backend "
            f"{backend_name!r}; supported backends: {supported}"
        )


__all__ = [
    "LEGACY_FSM_DECISION_BACKEND_NAME",
    "PrimitiveDecisionRuntime",
    "PrimitiveDecisionRuntimeConfig",
    "PrimitiveDecisionRuntimePorts",
]
