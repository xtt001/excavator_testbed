"""Backend-facing read-only primitive decision facts access."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

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


@dataclass(frozen=True)
class BootstrapDecisionStatus:
    """Bootstrap facts normalized for primitive backend decisions."""

    current_skill_name: str
    should_end_bootstrap: bool
    bootstrap_end_mode: str
    next_skill_after_bootstrap: str


@dataclass(frozen=True)
class PrimitiveBootstrapDecisionFacts:
    """Read-only bootstrap decision view for active-bootstrap decisions."""

    common: PrimitiveDecisionFacts
    status: BootstrapDecisionStatus

    @property
    def context(self) -> PrimitiveDecisionContext:
        return self.common.context

    @property
    def obs(self) -> dict[str, Any]:
        return self.common.obs

    @property
    def boundary_event(self) -> Any | None:
        return self.common.boundary_event

    @property
    def preparation(self) -> Any:
        return self.common.preparation

    @property
    def current_skill_name(self) -> str:
        return self.common.current_skill_name

    @property
    def skill_name_before_decision(self) -> str:
        return self.common.skill_name_before_decision

    @property
    def should_end_bootstrap(self) -> bool:
        return bool(self.status.should_end_bootstrap)

    @property
    def bootstrap_end_mode(self) -> str:
        return str(self.status.bootstrap_end_mode)

    @property
    def next_skill_after_bootstrap(self) -> str:
        return str(self.status.next_skill_after_bootstrap)


class PrimitiveBootstrapDecisionReader(Protocol):
    """Read-only bootstrap decision gate reader for backend facts access."""

    def should_end_bootstrap(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> bool: ...

    def bootstrap_end_mode(self) -> str: ...


class PrimitiveTransitionStatusReader(Protocol):
    """Read-only transition status reader for backend facts access."""

    def dig_transition_status(
        self,
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> DigTransitionStatus: ...

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

    def return_transition_status(
        self,
        obs: dict[str, Any],
        boundary_event: Any | None,
    ) -> ReturnTransitionStatus: ...


@dataclass(frozen=True)
class PrimitiveBackendFactsPorts:
    """Shell-provided read-only facts for backend decision input."""

    current_skill_name: Callable[[], str]
    current_switch_reason: Callable[[], str]
    transition_status_reader: PrimitiveTransitionStatusReader
    bootstrap_decision_reader: PrimitiveBootstrapDecisionReader | None = None


@dataclass(frozen=True)
class PrimitiveBackendFactsSource:
    """Build common and backend facts without exposing planner-private state."""

    _ports: PrimitiveBackendFactsPorts = field(repr=False, compare=False)

    @classmethod
    def from_ports(
        cls,
        ports: PrimitiveBackendFactsPorts,
    ) -> "PrimitiveBackendFactsSource":
        return cls(ports)

    def decision_facts(
        self,
        context: PrimitiveDecisionContext,
    ) -> PrimitiveDecisionFacts:
        return PrimitiveDecisionFacts.from_context(
            context,
            current_skill_name=str(self._ports.current_skill_name()),
            current_switch_reason=str(self._ports.current_switch_reason()),
        )

    def backend_facts(
        self,
        context: PrimitiveDecisionContext,
        *,
        facts: PrimitiveDecisionFacts | None = None,
    ) -> "PrimitiveBackendFactsAccess":
        common = facts or self.decision_facts(context)
        return PrimitiveBackendFactsAccess.from_reader(
            context=context,
            common=common,
            transition_status_reader=self._ports.transition_status_reader,
            bootstrap_decision_reader=self._ports.bootstrap_decision_reader,
        )


@dataclass(frozen=True)
class PrimitiveBackendFactsAccess:
    """Lazy read-only transition facts access for primitive decision backends."""

    context: PrimitiveDecisionContext
    common: PrimitiveDecisionFacts
    _transition_status_reader: PrimitiveTransitionStatusReader = field(
        repr=False,
        compare=False,
    )
    _bootstrap_decision_reader: PrimitiveBootstrapDecisionReader | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    @classmethod
    def from_reader(
        cls,
        *,
        context: PrimitiveDecisionContext,
        common: PrimitiveDecisionFacts,
        transition_status_reader: PrimitiveTransitionStatusReader,
        bootstrap_decision_reader: PrimitiveBootstrapDecisionReader | None = None,
    ) -> "PrimitiveBackendFactsAccess":
        return cls(
            context=context,
            common=common,
            _transition_status_reader=transition_status_reader,
            _bootstrap_decision_reader=bootstrap_decision_reader,
        )

    def bootstrap_decision(self) -> PrimitiveBootstrapDecisionFacts:
        if self._bootstrap_decision_reader is None:
            raise RuntimeError(
                "bootstrap_decision requires a bootstrap decision reader"
            )
        mode = str(self._bootstrap_decision_reader.bootstrap_end_mode())
        next_skill = next_skill_after_bootstrap(
            bootstrap_end_mode=mode,
        )
        return PrimitiveBootstrapDecisionFacts(
            common=self.common,
            status=BootstrapDecisionStatus(
                current_skill_name=self.common.current_skill_name,
                should_end_bootstrap=bool(
                    self._bootstrap_decision_reader.should_end_bootstrap(
                        obs=self.context.obs,
                        boundary_event=self.context.boundary_event,
                    )
                ),
                bootstrap_end_mode=mode,
                next_skill_after_bootstrap=next_skill,
            ),
        )

    def dig_transition(self) -> PrimitiveDigTransitionFacts:
        return PrimitiveDigTransitionFacts(
            common=self.common,
            status=self._transition_status_reader.dig_transition_status(
                self.context.obs,
                self.context.boundary_event,
            ),
        )

    def carry_transition(self) -> PrimitiveCarryTransitionFacts:
        return PrimitiveCarryTransitionFacts(
            common=self.common,
            status=self._transition_status_reader.carry_transition_status(
                self.context.obs,
                self.context.boundary_event,
            ),
        )

    def dump_transition(self) -> PrimitiveDumpTransitionFacts:
        return PrimitiveDumpTransitionFacts(
            common=self.common,
            status=self._transition_status_reader.dump_transition_status(
                self.context.obs,
                self.context.boundary_event,
            ),
        )

    def return_transition(self) -> PrimitiveReturnTransitionFacts:
        return PrimitiveReturnTransitionFacts(
            common=self.common,
            status=self._transition_status_reader.return_transition_status(
                self.context.obs,
                self.context.boundary_event,
            ),
        )


def next_skill_after_bootstrap(
    *,
    bootstrap_end_mode: str,
) -> str:
    if str(bootstrap_end_mode) in {
        "first_qualified_dig_start",
        "scripted_qpos",
    }:
        return "dig"
    return "carry"


__all__ = [
    "BootstrapDecisionStatus",
    "PrimitiveBootstrapDecisionFacts",
    "PrimitiveBootstrapDecisionReader",
    "PrimitiveBackendFactsAccess",
    "PrimitiveBackendFactsPorts",
    "PrimitiveBackendFactsSource",
    "PrimitiveTransitionStatusReader",
    "next_skill_after_bootstrap",
]
