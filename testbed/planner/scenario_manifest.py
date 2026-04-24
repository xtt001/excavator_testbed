"""Scenario manifest helpers for Stage-4 rule planning."""

from __future__ import annotations

from dataclasses import dataclass

from testbed.data.v2_1 import resolve_scenario_spec
from testbed.planner.types import (
    BELIEF_STATE_ACTIVE,
    BELIEF_STATE_CANDIDATE,
    DEPTH_CLASS_MEDIUM,
    PlannerGoal,
    SectorBelief,
    TerrainBeliefMap,
)


DEFAULT_TARGET_DEPTH_M = 0.08
DEFAULT_MAX_CYCLE_STEPS = 4000
DEFAULT_CURR_SECTOR_ID = 1
DEFAULT_CURR_CUT_DEPTH_CLASS = DEPTH_CLASS_MEDIUM
DEFAULT_CURR_CUT_DEPTH_NORM = 0.5


@dataclass(frozen=True)
class ScenarioManifest:
    manifest_id: str
    scenario_id: str
    dst_target_id: int
    sector_target_depth_m: tuple[float, float, float]
    max_cycle_steps: int

    def bootstrap_goal(self) -> PlannerGoal:
        return PlannerGoal(
            cycle_id=0,
            scenario_id=self.scenario_id,
            curr_src_sector_id=DEFAULT_CURR_SECTOR_ID,
            curr_cut_depth_class=DEFAULT_CURR_CUT_DEPTH_CLASS,
            curr_cut_depth_norm=DEFAULT_CURR_CUT_DEPTH_NORM,
            dst_target_id=int(self.dst_target_id),
            next_src_sector_id=DEFAULT_CURR_SECTOR_ID,
            next_cut_depth_class=DEFAULT_CURR_CUT_DEPTH_CLASS,
            next_cut_depth_norm=DEFAULT_CURR_CUT_DEPTH_NORM,
            next_entry_corridor_id=DEFAULT_CURR_SECTOR_ID,
            has_lookahead=False,
            max_cycle_steps=int(self.max_cycle_steps),
        )

    def initial_belief(self) -> TerrainBeliefMap:
        sectors = []
        for sector_id, target_depth in enumerate(self.sector_target_depth_m):
            state = BELIEF_STATE_ACTIVE if sector_id == DEFAULT_CURR_SECTOR_ID else BELIEF_STATE_CANDIDATE
            sectors.append(
                SectorBelief(
                    sector_id=sector_id,
                    target_depth_m=float(target_depth),
                    achieved_depth_proxy_m=0.0,
                    remaining_depth_proxy_m=float(target_depth),
                    depth_confidence=0.0,
                    visit_count=0,
                    last_fill_peak_kg=0.0,
                    last_deposit_delta_kg=0.0,
                    collision_risk=0.0,
                    state=state,
                    low_productivity_streak=0,
                    collision_streak=0,
                )
            )
        return TerrainBeliefMap(
            scenario_id=self.scenario_id,
            cycle_id=0,
            sectors=tuple(sectors),
        )


def resolve_scenario_manifest(manifest_id: str) -> ScenarioManifest:
    normalized = str(manifest_id).strip()
    if normalized not in {"s0_truck", "s0_baseline"}:
        raise KeyError(
            f"Unknown Stage-4 scenario manifest {manifest_id!r}. "
            "Available: ['s0_baseline', 's0_truck']."
        )
    spec = resolve_scenario_spec(normalized)
    return ScenarioManifest(
        manifest_id=normalized,
        scenario_id=spec.scenario_id,
        dst_target_id=int(spec.dst_target_id),
        sector_target_depth_m=(
            DEFAULT_TARGET_DEPTH_M,
            DEFAULT_TARGET_DEPTH_M,
            DEFAULT_TARGET_DEPTH_M,
        ),
        max_cycle_steps=DEFAULT_MAX_CYCLE_STEPS,
    )
