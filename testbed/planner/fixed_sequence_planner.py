"""Fixed coarse-sector planner for the Stage-2 hybrid prototype."""

from __future__ import annotations

from dataclasses import dataclass


SECTOR_NAME_TO_ID = {
    "left": 0,
    "mid": 1,
    "right": 2,
}
SECTOR_ID_TO_NAME = {value: key for key, value in SECTOR_NAME_TO_ID.items()}


@dataclass(frozen=True)
class PlannerGoal:
    cycle_index: int
    sector_name: str
    sector_id: int


class FixedSequencePlanner:
    """Return a fixed sector name/id sequence with last-value saturation."""

    def __init__(self, sequence: list[str] | tuple[str, ...]) -> None:
        normalized = [str(item).strip().lower() for item in sequence]
        if not normalized:
            raise ValueError("FixedSequencePlanner requires a non-empty sequence.")
        unknown = sorted({item for item in normalized if item not in SECTOR_NAME_TO_ID})
        if unknown:
            raise ValueError(
                f"Unknown sector names in fixed planner sequence: {unknown}. "
                f"Expected only {sorted(SECTOR_NAME_TO_ID)}."
            )
        self._sequence = tuple(normalized)

    @property
    def sequence(self) -> tuple[str, ...]:
        return self._sequence

    def sector_name_for_cycle(self, cycle_index: int) -> str:
        clamped = self._clamp_cycle_index(cycle_index)
        return self._sequence[clamped]

    def sector_id_for_cycle(self, cycle_index: int) -> int:
        return int(SECTOR_NAME_TO_ID[self.sector_name_for_cycle(cycle_index)])

    def goal_for_cycle(self, cycle_index: int) -> PlannerGoal:
        name = self.sector_name_for_cycle(cycle_index)
        return PlannerGoal(
            cycle_index=max(0, int(cycle_index)),
            sector_name=name,
            sector_id=int(SECTOR_NAME_TO_ID[name]),
        )

    def _clamp_cycle_index(self, cycle_index: int) -> int:
        if cycle_index <= 0:
            return 0
        return min(int(cycle_index), len(self._sequence) - 1)
