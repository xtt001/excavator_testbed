"""Planner dataclasses and constants for Stage-4 coarse replanning."""

from __future__ import annotations

from dataclasses import asdict, dataclass


SECTOR_NAME_TO_ID = {
    "left": 0,
    "mid": 1,
    "right": 2,
}
SECTOR_ID_TO_NAME = {value: key for key, value in SECTOR_NAME_TO_ID.items()}

DEPTH_CLASS_SHALLOW = 0
DEPTH_CLASS_MEDIUM = 1
DEPTH_CLASS_DEEP = 2

BELIEF_STATE_UNKNOWN = 0
BELIEF_STATE_CANDIDATE = 1
BELIEF_STATE_ACTIVE = 2
BELIEF_STATE_DONE = 3
BELIEF_STATE_BLOCKED = 4

PLAN_SOURCE_RULE = "rule"


@dataclass(frozen=True)
class PlannerGoal:
    cycle_id: int
    scenario_id: str
    curr_src_sector_id: int
    curr_cut_depth_class: int
    curr_cut_depth_norm: float
    dst_target_id: int
    next_src_sector_id: int
    next_cut_depth_class: int
    next_cut_depth_norm: float
    next_entry_corridor_id: int
    has_lookahead: bool
    max_cycle_steps: int
    plan_source: str = PLAN_SOURCE_RULE

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CycleSummary:
    cycle_id: int
    curr_src_sector_id: int
    next_src_sector_id: int
    fill_peak_kg: float
    deposit_delta_kg: float
    peak_bucket_depth_m: float
    collision_count_delta: int
    target_contact_max_force_n: float
    qualified_dig: bool
    cycle_success: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class SectorBelief:
    sector_id: int
    target_depth_m: float
    achieved_depth_proxy_m: float
    remaining_depth_proxy_m: float
    depth_confidence: float
    visit_count: int
    last_fill_peak_kg: float
    last_deposit_delta_kg: float
    collision_risk: float
    state: int
    low_productivity_streak: int
    collision_streak: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class TerrainBeliefMap:
    scenario_id: str
    cycle_id: int
    sectors: tuple[SectorBelief, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "cycle_id": int(self.cycle_id),
            "sectors": [sector.to_dict() for sector in self.sectors],
        }


def sector_name_from_id(sector_id: int) -> str:
    return SECTOR_ID_TO_NAME.get(int(sector_id), "mid")


def clip01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def depth_class_from_remaining_depth(remaining_depth_m: float) -> int:
    depth = max(0.0, float(remaining_depth_m))
    if depth < 0.04:
        return DEPTH_CLASS_SHALLOW
    if depth < 0.08:
        return DEPTH_CLASS_MEDIUM
    return DEPTH_CLASS_DEEP


def depth_norm_from_remaining_depth(remaining_depth_m: float) -> float:
    return clip01(float(remaining_depth_m) / 0.12)
