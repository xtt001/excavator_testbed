"""Per-tick backend decision input for primitive decision branches."""

from __future__ import annotations

from dataclasses import dataclass, field

from testbed.planner.primitive_backend_facts import PrimitiveBackendFactsAccess
from testbed.planner.primitive_decision_capabilities import (
    PrimitiveDecisionCompatibilityActions,
    PrimitiveDecisionFactsSource,
)
from testbed.planner.primitive_decision_context import PrimitiveDecisionContext
from testbed.planner.primitive_decision_facts import PrimitiveDecisionFacts


@dataclass(frozen=True)
class PrimitiveBackendDecisionInput:
    """Per-tick facts/actions packet passed through ordered backend branches."""

    context: PrimitiveDecisionContext
    backend_facts: PrimitiveBackendFactsAccess
    compatibility_actions: PrimitiveDecisionCompatibilityActions
    _facts_source: PrimitiveDecisionFactsSource = field(repr=False, compare=False)

    @classmethod
    def from_context(
        cls,
        context: PrimitiveDecisionContext,
        *,
        facts_source: PrimitiveDecisionFactsSource,
        compatibility_actions: PrimitiveDecisionCompatibilityActions,
    ) -> "PrimitiveBackendDecisionInput":
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


__all__ = [
    "PrimitiveBackendDecisionInput",
]
