"""Read-only primitive coverage status facts."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True)
class CoverageStatus:
    """Observable coverage state used by planner transition decisions."""

    selected_corridor_id: int | None
    selected_corridor_score: float
    candidate_scores: tuple[MappingProxyType[str, Any], ...]
    terminal_stop_requested: bool
    terminal_stop_reason: str
    depleted_count: int
    active_state_exemplar_ids: tuple[str, ...]
    rejected_state_exemplar_ids: frozenset[str]
    last_payload_gain_kg: float
    last_effective_deposit_delta_kg: float
    active_corridor_depleted: bool
    rejected_active_corridor: bool

    @classmethod
    def from_inputs(
        cls,
        *,
        selected_corridor_id: int | None = None,
        selected_corridor_score: float = float("nan"),
        candidate_scores: list[dict[str, Any]] | tuple[dict[str, Any], ...] = (),
        coverage_terminal_stop_requested: bool = False,
        coverage_terminal_stop_reason: str = "",
        coverage_depleted_count: int = 0,
        active_state_exemplar_ids: list[str] | tuple[str, ...] = (),
        rejected_state_exemplar_ids: set[str] | frozenset[str] = frozenset(),
        last_payload_gain_kg: float = 0.0,
        last_effective_deposit_delta_kg: float = 0.0,
        active_corridor_depleted: bool = False,
        rejected_active_corridor: bool = False,
    ) -> "CoverageStatus":
        frozen_scores = tuple(
            MappingProxyType(dict(candidate_score))
            for candidate_score in candidate_scores
        )
        return cls(
            selected_corridor_id=(
                None if selected_corridor_id is None else int(selected_corridor_id)
            ),
            selected_corridor_score=float(selected_corridor_score),
            candidate_scores=frozen_scores,
            terminal_stop_requested=bool(coverage_terminal_stop_requested),
            terminal_stop_reason=str(coverage_terminal_stop_reason),
            depleted_count=int(coverage_depleted_count),
            active_state_exemplar_ids=tuple(str(item) for item in active_state_exemplar_ids),
            rejected_state_exemplar_ids=frozenset(
                str(item) for item in rejected_state_exemplar_ids
            ),
            last_payload_gain_kg=float(last_payload_gain_kg),
            last_effective_deposit_delta_kg=float(last_effective_deposit_delta_kg),
            active_corridor_depleted=bool(active_corridor_depleted),
            rejected_active_corridor=bool(rejected_active_corridor),
        )


__all__ = ["CoverageStatus"]
