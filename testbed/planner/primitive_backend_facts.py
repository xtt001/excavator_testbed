"""Backend-facing read-only primitive decision facts access."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from testbed.planner.primitive_capabilities import (
    CarryTransitionStatus,
    DigTransitionStatus,
    DumpTransitionStatus,
    ReturnTransitionStatus,
)
from testbed.planner.primitive_decision_context import PrimitiveDecisionContext
from testbed.planner.primitive_decision_facts import (
    PrimitiveCarryTransitionFacts,
    PrimitiveDecisionFacts,
    PrimitiveDigTransitionFacts,
    PrimitiveDumpTransitionFacts,
    PrimitiveReturnTransitionFacts,
)


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
class PrimitiveBackendFactsAccess:
    """Lazy read-only transition facts access for primitive decision backends."""

    context: PrimitiveDecisionContext
    common: PrimitiveDecisionFacts
    _transition_status_reader: PrimitiveTransitionStatusReader = field(
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
    ) -> "PrimitiveBackendFactsAccess":
        return cls(
            context=context,
            common=common,
            _transition_status_reader=transition_status_reader,
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


__all__ = [
    "PrimitiveBackendFactsAccess",
    "PrimitiveTransitionStatusReader",
]
