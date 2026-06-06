"""Goal sector sequence normalization and token assembly."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import numpy as np

from testbed.data.v2_1 import build_goal_tokens

GOAL_SECTOR_NAME_TO_ID = {"left": 0, "mid": 1, "right": 2}
GOAL_SECTOR_ID_TO_NAME = {value: key for key, value in GOAL_SECTOR_NAME_TO_ID.items()}
GOAL_SEQUENCE_CONFIG_KEYS = (
    "goal_sequence",
    "goal_scenario_id",
    "goal_depth_norm",
    "goal_dump_target_norm",
)


@dataclass(frozen=True)
class GoalSequenceConfig:
    scenario_id: str
    depth_norm: float
    dump_target_norm: float


@dataclass(frozen=True)
class GoalSequenceFacts:
    cycle_index: int


@dataclass(frozen=True)
class GoalSequencePlannerConfig:
    goal_sequence: tuple[int, ...]
    goal_scenario_id: str
    goal_depth_norm: float
    goal_dump_target_norm: float

    def planner_items(self) -> tuple[tuple[str, object], ...]:
        return tuple(self.__dict__.items())


@dataclass(frozen=True)
class GoalSequenceTokenResult:
    tokens: np.ndarray | None
    curr_sector_id: int
    next_sector_id: int


class GoalSequenceService:
    """Resolve goal sequence sectors and assemble primitive goal tokens."""

    @staticmethod
    def sector_id_for_cycle(
        *,
        sequence: tuple[int, ...],
        cycle_index: int,
    ) -> int:
        if not sequence:
            return -1
        index = max(0, min(int(cycle_index), len(sequence) - 1))
        return int(sequence[index])

    @staticmethod
    def next_sector_id(
        *,
        sequence: tuple[int, ...],
        cycle_index: int,
    ) -> int:
        if not sequence:
            return -1
        next_index = int(cycle_index) + 1
        if next_index >= len(sequence):
            return -1
        return int(sequence[next_index])

    def tokens_for_cycle(
        self,
        *,
        sequence: tuple[int, ...],
        facts: GoalSequenceFacts,
        config: GoalSequenceConfig,
    ) -> GoalSequenceTokenResult:
        if not sequence:
            return GoalSequenceTokenResult(
                tokens=None,
                curr_sector_id=-1,
                next_sector_id=-1,
            )
        curr_sector_id = self.sector_id_for_cycle(
            sequence=sequence,
            cycle_index=int(facts.cycle_index),
        )
        next_sector_id = self.next_sector_id(
            sequence=sequence,
            cycle_index=int(facts.cycle_index),
        )
        return GoalSequenceTokenResult(
            tokens=build_goal_tokens(
                str(config.scenario_id),
                curr_sector_id=curr_sector_id,
                curr_cut_depth_norm=float(config.depth_norm),
                next_sector_id=next_sector_id,
                next_cut_depth_norm=float(config.depth_norm),
                dst_target_norm=float(config.dump_target_norm),
                has_lookahead=next_sector_id >= 0,
            ),
            curr_sector_id=curr_sector_id,
            next_sector_id=next_sector_id,
        )


def normalize_goal_sequence(
    goal_sequence: list[object] | tuple[object, ...] | None,
    *,
    unknown_message_prefix: str = "Unknown primitive goal sector",
    id_message_prefix: str = "Primitive goal sector id",
) -> tuple[int, ...]:
    if not goal_sequence:
        return ()
    normalized: list[int] = []
    for item in goal_sequence:
        if isinstance(item, str):
            key = item.strip().lower()
            if key not in GOAL_SECTOR_NAME_TO_ID:
                raise ValueError(
                    f"{unknown_message_prefix} {item!r}. Expected left, mid, or right."
                )
            normalized.append(GOAL_SECTOR_NAME_TO_ID[key])
        else:
            value = int(item)
            if value < 0 or value > 2:
                raise ValueError(
                    f"{id_message_prefix} must be 0, 1, or 2, got {item!r}."
                )
            normalized.append(value)
    return tuple(normalized)


def build_goal_sequence_planner_config(
    *,
    goal_sequence: list[object] | tuple[object, ...] | None,
    goal_scenario_id: object,
    goal_depth_norm: object,
    goal_dump_target_norm: object,
) -> GoalSequencePlannerConfig:
    return GoalSequencePlannerConfig(
        goal_sequence=normalize_goal_sequence(goal_sequence),
        goal_scenario_id=str(goal_scenario_id),
        goal_depth_norm=float(goal_depth_norm),
        goal_dump_target_norm=float(goal_dump_target_norm),
    )


def build_goal_sequence_planner_config_from_mapping(
    values: Mapping[str, Any],
) -> GoalSequencePlannerConfig:
    return build_goal_sequence_planner_config(
        goal_sequence=values["goal_sequence"],
        goal_scenario_id=values["goal_scenario_id"],
        goal_depth_norm=values["goal_depth_norm"],
        goal_dump_target_norm=values["goal_dump_target_norm"],
    )


def sector_name_from_id(sector_id: int, *, default: str = "mid") -> str:
    return GOAL_SECTOR_ID_TO_NAME.get(int(sector_id), str(default))
