"""Per-tick backend decision input for primitive decision backends."""

from __future__ import annotations

from dataclasses import dataclass, field

from testbed.planner.primitive.decision.capabilities import (
    PrimitiveDecisionCompatibilityActions,
)
from testbed.planner.primitive.decision.context import PrimitiveDecisionContext
from testbed.planner.primitive.facts.backend import (
    PrimitiveBackendFactsAccess,
    PrimitiveBackendFactsSource,
)
from testbed.planner.primitive.facts.decision import PrimitiveDecisionFacts


@dataclass(frozen=True)
class PrimitiveBackendDecisionInput:
    """Per-tick facts/actions packet passed to primitive decision backends."""

    context: PrimitiveDecisionContext
    backend_facts: PrimitiveBackendFactsAccess
    compatibility_actions: PrimitiveDecisionCompatibilityActions
    _facts_source: PrimitiveBackendFactsSource = field(repr=False, compare=False)

    @classmethod
    def from_context(
        cls,
        context: PrimitiveDecisionContext,
        *,
        facts_source: PrimitiveBackendFactsSource,
        compatibility_actions: PrimitiveDecisionCompatibilityActions,
    ) -> PrimitiveBackendDecisionInput:
        common = facts_source.decision_facts(context)
        backend_facts = facts_source.backend_facts(context, facts=common)
        return cls(
            context=context,
            backend_facts=backend_facts,
            compatibility_actions=compatibility_actions,
            _facts_source=facts_source,
        )

    @property
    def common(self) -> PrimitiveDecisionFacts:
        return self.backend_facts.common

    def rebuild_common_facts_after_compatibility_action(self) -> PrimitiveDecisionFacts:
        return self._facts_source.decision_facts(self.context)


@dataclass(frozen=True)
class PrimitiveBackendDecisionInputBuilder:
    """Build backend-neutral decision input from read-only facts and actions."""

    facts_source: PrimitiveBackendFactsSource
    compatibility_actions: PrimitiveDecisionCompatibilityActions

    @classmethod
    def from_sources(
        cls,
        *,
        facts_source: PrimitiveBackendFactsSource,
        compatibility_actions: PrimitiveDecisionCompatibilityActions,
    ) -> PrimitiveBackendDecisionInputBuilder:
        return cls(
            facts_source=facts_source,
            compatibility_actions=compatibility_actions,
        )

    def build(
        self,
        context: PrimitiveDecisionContext,
    ) -> PrimitiveBackendDecisionInput:
        return PrimitiveBackendDecisionInput.from_context(
            context,
            facts_source=self.facts_source,
            compatibility_actions=self.compatibility_actions,
        )


__all__ = [
    "PrimitiveBackendDecisionInputBuilder",
    "PrimitiveBackendDecisionInput",
]
