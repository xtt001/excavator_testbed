"""Backend-facing primitive decision capability ports."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from testbed.planner.primitive.facts.backend import (
    BootstrapDecisionStatus,
    PrimitiveBackendFactsAccess,
    PrimitiveBackendFactsPorts,
    PrimitiveBackendFactsSource,
    PrimitiveBootstrapDecisionFacts,
    PrimitiveBootstrapDecisionReader,
    PrimitiveTransitionStatusReader,
)
from testbed.planner.primitive.facts.capabilities import (
    CarryTransitionStatus,
    DigTransitionStatus,
    DumpTransitionStatus,
    ReturnTransitionStatus,
)
from testbed.planner.primitive.decision.context import PrimitiveDecisionContext
from testbed.planner.primitive.facts.decision import (
    PrimitiveCarryTransitionFacts,
    PrimitiveDecisionFacts,
    PrimitiveDigTransitionFacts,
    PrimitiveDumpTransitionFacts,
    PrimitiveReturnTransitionFacts,
)


class PrimitiveTransitionStatusProvider(PrimitiveTransitionStatusReader, Protocol):
    """Transition status provider plus explicit legacy compatibility actions."""

    def sync_dig_transition_reason(
        self,
        status: DigTransitionStatus,
    ) -> None: ...

    def refresh_return_transition_state(
        self,
        obs: dict[str, Any],
    ) -> None: ...


@dataclass(frozen=True)
class PrimitiveDecisionCapabilitiesPorts:
    """Shell-provided decision facts for primitive backend capabilities."""

    current_skill_name: Callable[[], str]
    current_switch_reason: Callable[[], str]
    should_end_bootstrap: Callable[..., bool]
    bootstrap_end_mode: Callable[[], str]
    transition_status_provider: PrimitiveTransitionStatusProvider


@dataclass(frozen=True)
class _BootstrapDecisionReader:
    """Read-only bootstrap gate adapter over shell-provided capability ports."""

    ports: PrimitiveDecisionCapabilitiesPorts

    def should_end_bootstrap(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> bool:
        return bool(
            self.ports.should_end_bootstrap(
                obs=obs,
                boundary_event=boundary_event,
            )
        )

    def bootstrap_end_mode(self) -> str:
        return str(self.ports.bootstrap_end_mode())


PrimitiveDecisionFactsSource = PrimitiveBackendFactsSource


@dataclass(frozen=True)
class PrimitiveDecisionCompatibilityActions:
    """Explicit shell compatibility actions kept outside read-only facts access."""

    _ports: PrimitiveDecisionCapabilitiesPorts = field(repr=False, compare=False)

    def sync_dig_transition_reason(
        self,
        dig_facts: PrimitiveDigTransitionFacts,
    ) -> None:
        self._ports.transition_status_provider.sync_dig_transition_reason(
            dig_facts.status,
        )

    def refresh_return_transition_state(
        self,
        context: PrimitiveDecisionContext,
    ) -> None:
        self._ports.transition_status_provider.refresh_return_transition_state(
            context.obs
        )


@dataclass(frozen=True)
class PrimitiveDecisionCapabilities:
    """Map a decision context into legacy FSM backend facts and statuses."""

    ports: PrimitiveDecisionCapabilitiesPorts

    @classmethod
    def from_ports(
        cls,
        ports: PrimitiveDecisionCapabilitiesPorts,
    ) -> "PrimitiveDecisionCapabilities":
        return cls(ports=ports)

    def current_skill_name(self) -> str:
        return str(self.ports.current_skill_name())

    def current_switch_reason(self) -> str:
        return str(self.ports.current_switch_reason())

    def facts_source(self) -> PrimitiveBackendFactsSource:
        return PrimitiveBackendFactsSource.from_ports(
            PrimitiveBackendFactsPorts(
                current_skill_name=self.ports.current_skill_name,
                current_switch_reason=self.ports.current_switch_reason,
                transition_status_reader=self.ports.transition_status_provider,
                bootstrap_decision_reader=_BootstrapDecisionReader(self.ports),
            )
        )

    def compatibility_actions(self) -> PrimitiveDecisionCompatibilityActions:
        return PrimitiveDecisionCompatibilityActions(self.ports)

    def decision_facts(
        self,
        context: PrimitiveDecisionContext,
    ) -> PrimitiveDecisionFacts:
        return self.facts_source().decision_facts(context)

    def backend_facts(
        self,
        context: PrimitiveDecisionContext,
        *,
        facts: PrimitiveDecisionFacts | None = None,
    ) -> PrimitiveBackendFactsAccess:
        return self.facts_source().backend_facts(context, facts=facts)

    def bootstrap_status(
        self,
        context: PrimitiveDecisionContext,
        *,
        bootstrap_skill_name: str,
        facts: PrimitiveDecisionFacts | None = None,
    ) -> BootstrapDecisionStatus:
        del bootstrap_skill_name
        return self.backend_facts(context, facts=facts).bootstrap_decision().status

    def dig_transition_status(
        self,
        context: PrimitiveDecisionContext,
    ) -> DigTransitionStatus:
        return self.ports.transition_status_provider.dig_transition_status(
            context.obs,
            context.boundary_event,
        )

    def dig_transition_facts(
        self,
        context: PrimitiveDecisionContext,
        *,
        facts: PrimitiveDecisionFacts | None = None,
    ) -> PrimitiveDigTransitionFacts:
        return self.backend_facts(context, facts=facts).dig_transition()

    def sync_dig_transition_reason(
        self,
        dig_facts: PrimitiveDigTransitionFacts,
    ) -> None:
        self.compatibility_actions().sync_dig_transition_reason(dig_facts)

    def carry_transition_status(
        self,
        context: PrimitiveDecisionContext,
    ) -> CarryTransitionStatus:
        return self.ports.transition_status_provider.carry_transition_status(
            context.obs,
            context.boundary_event,
        )

    def carry_transition_facts(
        self,
        context: PrimitiveDecisionContext,
        *,
        facts: PrimitiveDecisionFacts | None = None,
    ) -> PrimitiveCarryTransitionFacts:
        return self.backend_facts(context, facts=facts).carry_transition()

    def dump_transition_status(
        self,
        context: PrimitiveDecisionContext,
    ) -> DumpTransitionStatus:
        return self.ports.transition_status_provider.dump_transition_status(
            context.obs,
            context.boundary_event,
        )

    def dump_transition_facts(
        self,
        context: PrimitiveDecisionContext,
        *,
        facts: PrimitiveDecisionFacts | None = None,
    ) -> PrimitiveDumpTransitionFacts:
        return self.backend_facts(context, facts=facts).dump_transition()

    def return_transition_status(
        self,
        context: PrimitiveDecisionContext,
    ) -> ReturnTransitionStatus:
        return self.ports.transition_status_provider.return_transition_status(
            context.obs,
            context.boundary_event,
        )

    def return_transition_facts(
        self,
        context: PrimitiveDecisionContext,
        *,
        facts: PrimitiveDecisionFacts | None = None,
    ) -> PrimitiveReturnTransitionFacts:
        return self.backend_facts(context, facts=facts).return_transition()

    def refresh_return_transition_state(
        self,
        context: PrimitiveDecisionContext,
    ) -> None:
        self.compatibility_actions().refresh_return_transition_state(context)

__all__ = [
    "BootstrapDecisionStatus",
    "PrimitiveCarryTransitionFacts",
    "PrimitiveBackendFactsAccess",
    "PrimitiveBackendFactsPorts",
    "PrimitiveBackendFactsSource",
    "PrimitiveBootstrapDecisionFacts",
    "PrimitiveBootstrapDecisionReader",
    "PrimitiveDecisionCompatibilityActions",
    "PrimitiveDecisionCapabilities",
    "PrimitiveDecisionCapabilitiesPorts",
    "PrimitiveDecisionFacts",
    "PrimitiveDecisionFactsSource",
    "PrimitiveDigTransitionFacts",
    "PrimitiveDumpTransitionFacts",
    "PrimitiveReturnTransitionFacts",
    "PrimitiveTransitionStatusReader",
    "PrimitiveTransitionStatusProvider",
]
