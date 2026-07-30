"""Coverage-state effects of acknowledged typed box-safety decisions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from testbed.planner.box_emptying.contact_ownership import (
    CONTACT_KIND_HARD_BOTTOM,
    CONTACT_KIND_WALL,
    validate_contact_ownership,
)


@dataclass(frozen=True)
class SafetyCoverageEffect:
    """Traceable result of applying one acknowledged safety decision."""

    applied: bool = False
    contact_kind: str = "none"
    blocked_corridor_id: int = -1
    depth_exhausted_physical_cell_id: int = -1


@dataclass(frozen=True)
class SafetyDecisionCoverageEffectService:
    """Apply mutually exclusive wall/depth effects after neutral ack only."""

    coverage_state: Any
    residual_plan_service: Any | None = None

    def apply(self, decision: Any) -> SafetyCoverageEffect:
        ownership = validate_contact_ownership(
            contact_kind=str(getattr(decision, "contact_kind", "none")),
            blocked_corridor_id=int(
                getattr(decision, "blocked_corridor_id", -1)
            ),
            depth_exhausted_cell_id=int(
                getattr(decision, "depth_exhausted_cell_id", -1)
            ),
            wall_contact_session_count=int(
                getattr(decision, "wall_contact_session_count", 0)
            ),
        )
        if not bool(getattr(decision, "neutral_acknowledged", False)):
            return SafetyCoverageEffect(contact_kind=ownership.contact_kind)

        if ownership.contact_kind == CONTACT_KIND_WALL:
            corridor_id = int(ownership.blocked_corridor_id)
            if corridor_id < 0:
                return SafetyCoverageEffect(
                    contact_kind=ownership.contact_kind
                )
            if self.residual_plan_service is not None:
                self.residual_plan_service.block_corridor_numeric_id(
                    corridor_id
                )
            self.coverage_state.reject_wall_corridor(corridor_id)
            corridor = self.coverage_state.corridor_by_id(corridor_id)
            if corridor is not None:
                corridor.depleted = True
                corridor.last_reason = "wall_contact_blocked_corridor"
            return SafetyCoverageEffect(
                applied=True,
                contact_kind=ownership.contact_kind,
                blocked_corridor_id=corridor_id,
            )

        if ownership.contact_kind == CONTACT_KIND_HARD_BOTTOM:
            cell_id = int(ownership.depth_exhausted_cell_id)
            if cell_id < 0:
                return SafetyCoverageEffect(
                    contact_kind=ownership.contact_kind
                )
            if self.residual_plan_service is not None:
                self.residual_plan_service.mark_depth_exhausted(cell_id)
            self.coverage_state.mark_depth_exhausted_physical_cell(cell_id)
            return SafetyCoverageEffect(
                applied=True,
                contact_kind=ownership.contact_kind,
                depth_exhausted_physical_cell_id=cell_id,
            )

        return SafetyCoverageEffect(contact_kind=ownership.contact_kind)


__all__ = [
    "SafetyCoverageEffect",
    "SafetyDecisionCoverageEffectService",
]
