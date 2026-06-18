"""Decision backend protocol and legacy FSM adapter for primitive planning."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from testbed.planner.primitive_decision import PrimitiveDecisionResult
from testbed.planner.primitive_execution import PrimitiveTickPreparation


class PrimitiveDecisionBackend(Protocol):
    """Backend interface for choosing the next primitive skill for a tick."""

    def decide_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult: ...


@dataclass(frozen=True)
class LegacyFSMBackendAdapter:
    """Adapter around the existing already-mutating legacy FSM callback."""

    maybe_switch_skill: Callable[..., None]
    current_skill_name: Callable[[], str]
    current_switch_reason: Callable[[], str]

    def decide_tick(
        self,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> PrimitiveDecisionResult:
        skill_before = str(preparation.skill_name_before_decision)
        self.maybe_switch_skill(obs=obs, boundary_event=boundary_event)
        return PrimitiveDecisionResult.from_legacy_fsm_outcome(
            skill_before=skill_before,
            skill_after=str(self.current_skill_name()),
            switch_reason=str(self.current_switch_reason()),
        )


__all__ = ["LegacyFSMBackendAdapter", "PrimitiveDecisionBackend"]
