"""Read-only decision context packet for primitive planner backends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from testbed.planner.primitive_execution import PrimitiveTickPreparation


@dataclass(frozen=True)
class PrimitiveDecisionContext:
    """Shared tick input packet consumed by primitive decision backends."""

    obs: dict[str, Any]
    boundary_event: Any | None
    preparation: PrimitiveTickPreparation

    @classmethod
    def from_tick(
        cls,
        *,
        obs: dict[str, Any],
        boundary_event: Any | None,
        preparation: PrimitiveTickPreparation,
    ) -> "PrimitiveDecisionContext":
        return cls(
            obs=obs,
            boundary_event=boundary_event,
            preparation=preparation,
        )

    @property
    def skill_name_before_decision(self) -> str:
        return str(self.preparation.skill_name_before_decision)

    @property
    def dig_progress_updated(self) -> bool:
        return bool(self.preparation.dig_progress_updated)


__all__ = ["PrimitiveDecisionContext"]
