"""Primitive planner token providers."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from testbed.data.v2_1 import build_goal_tokens


PRIMITIVE_GOAL_SECTOR_IDS = {"left": 0, "mid": 1, "right": 2}


@dataclass(frozen=True)
class GoalTokenProvider:
    """Build goal tokens from the configured primitive goal sequence."""

    goal_sequence: tuple[int, ...]
    scenario_id: str = "s0_truck"
    depth_norm: float = 0.0
    dump_target_norm: float = 0.0

    @classmethod
    def from_inputs(
        cls,
        *,
        goal_sequence: list[str] | tuple[str, ...] | list[int] | tuple[int, ...] | None,
        scenario_id: str = "s0_truck",
        depth_norm: float = 0.0,
        dump_target_norm: float = 0.0,
    ) -> "GoalTokenProvider":
        return cls(
            goal_sequence=cls.normalize_goal_sequence(goal_sequence),
            scenario_id=str(scenario_id),
            depth_norm=float(depth_norm),
            dump_target_norm=float(dump_target_norm),
        )

    @staticmethod
    def normalize_goal_sequence(
        goal_sequence: list[str] | tuple[str, ...] | list[int] | tuple[int, ...] | None,
    ) -> tuple[int, ...]:
        if not goal_sequence:
            return ()
        normalized: list[int] = []
        for item in goal_sequence:
            if isinstance(item, str):
                key = item.strip().lower()
                if key not in PRIMITIVE_GOAL_SECTOR_IDS:
                    raise ValueError(
                        f"Unknown primitive goal sector {item!r}. Expected left, mid, or right."
                    )
                normalized.append(PRIMITIVE_GOAL_SECTOR_IDS[key])
            else:
                value = int(item)
                if value < 0 or value > 2:
                    raise ValueError(
                        f"Primitive goal sector id must be 0, 1, or 2, got {item!r}."
                    )
                normalized.append(value)
        return tuple(normalized)

    def tokens_for_cycle(self, cycle_index: int) -> np.ndarray | None:
        if not self.goal_sequence:
            return None
        curr_sector_id = self.sector_id(cycle_index)
        next_sector_id = self.next_sector_id(cycle_index)
        return build_goal_tokens(
            self.scenario_id,
            curr_sector_id=curr_sector_id,
            curr_cut_depth_norm=self.depth_norm,
            next_sector_id=next_sector_id,
            next_cut_depth_norm=self.depth_norm,
            dst_target_norm=self.dump_target_norm,
            has_lookahead=next_sector_id >= 0,
        )

    def sector_id(self, cycle_index: int) -> int:
        if not self.goal_sequence:
            return -1
        index = max(0, min(int(cycle_index), len(self.goal_sequence) - 1))
        return int(self.goal_sequence[index])

    def next_sector_id(self, cycle_index: int) -> int:
        if not self.goal_sequence:
            return -1
        next_index = int(cycle_index) + 1
        if next_index >= len(self.goal_sequence):
            return -1
        return int(self.goal_sequence[next_index])


__all__ = ["GoalTokenProvider", "PRIMITIVE_GOAL_SECTOR_IDS"]
