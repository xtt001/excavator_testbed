"""Decision runtime and backend selection for primitive planner ticks."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from testbed.planner.primitive.decision.backends.legacy_fsm import (
    PrimitiveCompatibilityDecisionBackend,
    PrimitiveDecisionBackend,
    PrimitiveDecisionBackendFactory,
)
from testbed.planner.primitive.decision.contracts import (
    PrimitiveDecisionContractError,
    PrimitiveDecisionResult,
)
from testbed.planner.primitive.decision.context import PrimitiveDecisionContext
from testbed.planner.primitive.execution.runtime import PrimitiveTickPreparation


LEGACY_FSM_DECISION_BACKEND_NAME = "legacy_fsm"
SUPPORTED_DECISION_BACKENDS = (LEGACY_FSM_DECISION_BACKEND_NAME,)
PRODUCTION_DECISION_BACKEND_NAMES = SUPPORTED_DECISION_BACKENDS


@dataclass(frozen=True)
class PrimitiveDecisionRuntimeConfig:
    """Configuration for selecting the primitive decision backend."""

    backend_name: str = LEGACY_FSM_DECISION_BACKEND_NAME


@dataclass(frozen=True)
class PrimitiveDecisionRuntimePorts:
    """Typed backend factory ports for the primitive decision runtime."""

    backend_factories: Mapping[str, Callable[[], PrimitiveDecisionBackendFactory]]


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

    def backend_factory_for(
        self,
        backend_name: str,
    ) -> PrimitiveDecisionBackendFactory:
        backend_name = str(backend_name).strip().lower()
        factory_builder = self._backend_factory_builders().get(backend_name)
        if factory_builder is not None:
            return factory_builder()
        supported = ", ".join(self._registered_backend_names())
        raise PrimitiveDecisionContractError(
            "unsupported primitive decision backend "
            f"{backend_name!r}; supported backends: {supported}"
        )

    def requested_backend_for(self, backend_name: str) -> PrimitiveDecisionBackend:
        return self.backend_factory_for(backend_name).requested_decision_backend()

    def compatibility_backend_for(
        self,
        backend_name: str,
    ) -> PrimitiveCompatibilityDecisionBackend:
        return self.backend_factory_for(backend_name).compatibility_decision_backend()

    def _requested_backend(self) -> PrimitiveDecisionBackend:
        return self.requested_backend_for(self._backend_name())

    def _compatibility_backend(self) -> PrimitiveCompatibilityDecisionBackend:
        return self.compatibility_backend_for(self._backend_name())

    def _backend_name(self) -> str:
        return str(self.config.backend_name).strip().lower()

    def _backend_factory(self) -> PrimitiveDecisionBackendFactory:
        return self.backend_factory_for(self._backend_name())

    def _backend_factory_builders(
        self,
    ) -> dict[str, Callable[[], PrimitiveDecisionBackendFactory]]:
        return {
            str(name).strip().lower(): builder
            for name, builder in self.ports.backend_factories.items()
        }

    def _registered_backend_names(self) -> tuple[str, ...]:
        names = tuple(self._backend_factory_builders())
        return names or SUPPORTED_DECISION_BACKENDS


__all__ = [
    "LEGACY_FSM_DECISION_BACKEND_NAME",
    "PRODUCTION_DECISION_BACKEND_NAMES",
    "PrimitiveDecisionRuntime",
    "PrimitiveDecisionRuntimeConfig",
    "PrimitiveDecisionRuntimePorts",
    "SUPPORTED_DECISION_BACKENDS",
]
