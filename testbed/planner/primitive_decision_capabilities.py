"""Backend-facing primitive decision capability ports."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from testbed.planner.primitive_capabilities import (
    CarryTransitionStatus,
    DigTransitionStatus,
    DumpTransitionStatus,
    ReturnTransitionStatus,
)
from testbed.planner.primitive_decision_context import PrimitiveDecisionContext
from testbed.planner.primitive_decision_facts import (
    PrimitiveDecisionFacts,
    PrimitiveDigTransitionFacts,
    PrimitiveReturnTransitionFacts,
)


class PrimitiveTransitionStatusProvider(Protocol):
    """Transition-status provider consumed by primitive decision capabilities."""

    def dig_transition_status(
        self,
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> DigTransitionStatus: ...

    def sync_dig_transition_reason(
        self,
        status: DigTransitionStatus,
    ) -> None: ...

    def carry_transition_status(
        self,
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> CarryTransitionStatus: ...

    def dump_transition_status(
        self,
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> DumpTransitionStatus: ...

    def refresh_return_transition_state(
        self,
        obs: dict[str, Any],
    ) -> None: ...

    def return_transition_status(
        self,
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> ReturnTransitionStatus: ...


@dataclass(frozen=True)
class BootstrapDecisionStatus:
    """Bootstrap facts normalized for legacy FSM branch decisions."""

    current_skill_name: str
    should_end_bootstrap: bool
    bootstrap_end_mode: str
    should_pre_dig_align_before_dig: bool
    next_skill_after_bootstrap: str


@dataclass(frozen=True)
class PrimitiveDecisionCapabilitiesPorts:
    """Shell-provided decision facts for primitive backend capabilities."""

    current_skill_name: Callable[[], str]
    current_switch_reason: Callable[[], str]
    should_end_bootstrap: Callable[..., bool]
    bootstrap_end_mode: Callable[[], str]
    should_pre_dig_align_before_dig: Callable[[], bool]
    transition_status_provider: PrimitiveTransitionStatusProvider
    maybe_handle_residual_pre_dig_align: Callable[[dict[str, Any]], bool]


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

    def decision_facts(
        self,
        context: PrimitiveDecisionContext,
    ) -> PrimitiveDecisionFacts:
        return PrimitiveDecisionFacts.from_context(
            context,
            current_skill_name=self.current_skill_name(),
            current_switch_reason=self.current_switch_reason(),
        )

    def bootstrap_status(
        self,
        context: PrimitiveDecisionContext,
        *,
        bootstrap_skill_name: str,
        pre_dig_align_skill_name: str,
        facts: PrimitiveDecisionFacts | None = None,
    ) -> BootstrapDecisionStatus:
        facts = facts or self.decision_facts(context)
        mode = str(self.ports.bootstrap_end_mode())
        pre_dig_before_dig = bool(self.ports.should_pre_dig_align_before_dig())
        next_skill = _next_skill_after_bootstrap(
            bootstrap_end_mode=mode,
            pre_dig_align_before_dig=pre_dig_before_dig,
            pre_dig_align_skill_name=pre_dig_align_skill_name,
        )
        return BootstrapDecisionStatus(
            current_skill_name=facts.current_skill_name,
            should_end_bootstrap=bool(
                self.ports.should_end_bootstrap(
                    obs=context.obs,
                    boundary_event=context.boundary_event,
                )
            ),
            bootstrap_end_mode=mode,
            should_pre_dig_align_before_dig=pre_dig_before_dig,
            next_skill_after_bootstrap=next_skill,
        )

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
        common = facts or self.decision_facts(context)
        return PrimitiveDigTransitionFacts(
            common=common,
            status=self.dig_transition_status(context),
        )

    def sync_dig_transition_reason(
        self,
        dig_facts: PrimitiveDigTransitionFacts,
    ) -> None:
        self.ports.transition_status_provider.sync_dig_transition_reason(
            dig_facts.status,
        )

    def carry_transition_status(
        self,
        context: PrimitiveDecisionContext,
    ) -> CarryTransitionStatus:
        return self.ports.transition_status_provider.carry_transition_status(
            context.obs,
            context.boundary_event,
        )

    def dump_transition_status(
        self,
        context: PrimitiveDecisionContext,
    ) -> DumpTransitionStatus:
        return self.ports.transition_status_provider.dump_transition_status(
            context.obs,
            context.boundary_event,
        )

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
        common = facts or self.decision_facts(context)
        return PrimitiveReturnTransitionFacts(
            common=common,
            status=self.return_transition_status(context),
        )

    def refresh_return_transition_state(
        self,
        context: PrimitiveDecisionContext,
    ) -> None:
        self.ports.transition_status_provider.refresh_return_transition_state(
            context.obs
        )

    def handle_residual_pre_dig_align(
        self,
        context: PrimitiveDecisionContext,
    ) -> bool:
        """Apply the parked pre-dig-align compatibility path."""

        return bool(self.ports.maybe_handle_residual_pre_dig_align(context.obs))


def _next_skill_after_bootstrap(
    *,
    bootstrap_end_mode: str,
    pre_dig_align_before_dig: bool,
    pre_dig_align_skill_name: str,
) -> str:
    if str(bootstrap_end_mode) in {
        "first_qualified_dig_start",
        "scripted_qpos",
    }:
        return str(pre_dig_align_skill_name) if pre_dig_align_before_dig else "dig"
    return "carry"


__all__ = [
    "BootstrapDecisionStatus",
    "PrimitiveDecisionCapabilities",
    "PrimitiveDecisionCapabilitiesPorts",
    "PrimitiveDecisionFacts",
    "PrimitiveDigTransitionFacts",
    "PrimitiveReturnTransitionFacts",
    "PrimitiveTransitionStatusProvider",
]
