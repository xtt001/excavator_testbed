"""Stage-4 coarse rule planner and belief-map updater."""

from __future__ import annotations

from dataclasses import replace

from testbed.planner.scenario_manifest import ScenarioManifest, resolve_scenario_manifest
from testbed.planner.types import (
    BELIEF_STATE_ACTIVE,
    BELIEF_STATE_BLOCKED,
    BELIEF_STATE_CANDIDATE,
    BELIEF_STATE_DONE,
    CycleSummary,
    PlannerGoal,
    SectorBelief,
    TerrainBeliefMap,
    depth_class_from_remaining_depth,
    depth_norm_from_remaining_depth,
)


class RuleTaskPlanner:
    """Stage-4 coarse sector/depth rule planner."""

    def __init__(self, *, manifest: ScenarioManifest) -> None:
        self._manifest = manifest
        self.reset(manifest.scenario_id)

    @property
    def manifest(self) -> ScenarioManifest:
        return self._manifest

    def reset(self, scenario_id: str) -> None:
        if str(scenario_id) != self._manifest.scenario_id:
            self._manifest = resolve_scenario_manifest(str(scenario_id))
        self._belief = self._manifest.initial_belief()
        self._trace: dict[str, object] = {
            "scenario_id": self._manifest.scenario_id,
            "manifest_id": self._manifest.manifest_id,
            "initial_belief": self._belief.to_dict(),
            "initial_goal": self._manifest.bootstrap_goal().to_dict(),
            "replans": [],
        }

    def bootstrap_first_goal(self) -> PlannerGoal:
        return self._manifest.bootstrap_goal()

    def current_belief(self) -> TerrainBeliefMap:
        return self._belief

    def planner_trace(self) -> dict[str, object]:
        return dict(self._trace)

    def replan_at_cycle_boundary(self, last_cycle: CycleSummary) -> PlannerGoal:
        belief_before = self._belief
        updated_sectors = self._update_belief(last_cycle)
        self._belief = TerrainBeliefMap(
            scenario_id=belief_before.scenario_id,
            cycle_id=int(last_cycle.cycle_id) + 1,
            sectors=tuple(updated_sectors),
        )
        anchor_sector_id = (
            int(last_cycle.next_src_sector_id)
            if int(last_cycle.next_src_sector_id) >= 0
            else int(last_cycle.curr_src_sector_id)
        )
        scored = self._score_sectors(anchor_sector_id=anchor_sector_id)
        selected_sector_id = self._select_sector(scored=scored, anchor_sector_id=anchor_sector_id)
        selected_sector = self._belief.sectors[selected_sector_id]
        next_goal = PlannerGoal(
            cycle_id=int(last_cycle.cycle_id) + 1,
            scenario_id=self._manifest.scenario_id,
            curr_src_sector_id=selected_sector_id,
            curr_cut_depth_class=depth_class_from_remaining_depth(
                selected_sector.remaining_depth_proxy_m
            ),
            curr_cut_depth_norm=depth_norm_from_remaining_depth(
                selected_sector.remaining_depth_proxy_m
            ),
            dst_target_id=int(self._manifest.dst_target_id),
            next_src_sector_id=selected_sector_id,
            next_cut_depth_class=depth_class_from_remaining_depth(
                selected_sector.remaining_depth_proxy_m
            ),
            next_cut_depth_norm=depth_norm_from_remaining_depth(
                selected_sector.remaining_depth_proxy_m
            ),
            next_entry_corridor_id=selected_sector_id,
            has_lookahead=True,
            max_cycle_steps=int(self._manifest.max_cycle_steps),
        )
        self._trace["replans"].append(
            {
                "last_cycle": last_cycle.to_dict(),
                "belief_before": belief_before.to_dict(),
                "belief_after": self._belief.to_dict(),
                "score_breakdown": scored,
                "selected_next_goal": next_goal.to_dict(),
            }
        )
        return next_goal

    def _update_belief(self, last_cycle: CycleSummary) -> list[SectorBelief]:
        updated = list(self._belief.sectors)
        sector_id = int(last_cycle.curr_src_sector_id)
        if not (0 <= sector_id < len(updated)):
            return updated
        sector = updated[sector_id]
        achieved = float(sector.achieved_depth_proxy_m)
        remaining = float(sector.remaining_depth_proxy_m)
        depth_confidence = float(sector.depth_confidence)
        low_productivity_streak = int(sector.low_productivity_streak)
        collision_risk = float(sector.collision_risk)
        collision_streak = int(sector.collision_streak)

        if bool(last_cycle.qualified_dig) and float(last_cycle.fill_peak_kg) >= 100.0:
            achieved = max(
                achieved,
                min(float(sector.target_depth_m), float(last_cycle.peak_bucket_depth_m)),
            )
            remaining = max(0.0, float(sector.target_depth_m) - achieved)
            depth_confidence = min(1.0, depth_confidence + 0.2)

        if float(last_cycle.fill_peak_kg) < 100.0 and float(last_cycle.deposit_delta_kg) < 100.0:
            low_productivity_streak += 1
        else:
            low_productivity_streak = 0

        if int(last_cycle.collision_count_delta) > 0:
            collision_risk = min(1.0, collision_risk + 0.5)
            collision_streak += 1
        else:
            collision_risk = max(0.0, collision_risk - 0.1)
            collision_streak = 0

        state = sector.state
        if remaining <= 0.01:
            state = BELIEF_STATE_DONE
        elif collision_streak >= 2:
            state = BELIEF_STATE_BLOCKED
        elif sector_id == int(last_cycle.next_src_sector_id):
            state = BELIEF_STATE_ACTIVE
        elif state not in {BELIEF_STATE_DONE, BELIEF_STATE_BLOCKED}:
            state = BELIEF_STATE_CANDIDATE

        updated[sector_id] = replace(
            sector,
            achieved_depth_proxy_m=float(achieved),
            remaining_depth_proxy_m=float(remaining),
            depth_confidence=float(depth_confidence),
            visit_count=int(sector.visit_count) + 1,
            last_fill_peak_kg=float(last_cycle.fill_peak_kg),
            last_deposit_delta_kg=float(last_cycle.deposit_delta_kg),
            collision_risk=float(collision_risk),
            state=int(state),
            low_productivity_streak=int(low_productivity_streak),
            collision_streak=int(collision_streak),
        )

        for other_index, other in enumerate(updated):
            if other_index == sector_id:
                continue
            if other.state not in {BELIEF_STATE_DONE, BELIEF_STATE_BLOCKED}:
                updated[other_index] = replace(other, state=BELIEF_STATE_CANDIDATE)
        return updated

    def _score_sectors(self, *, anchor_sector_id: int) -> list[dict[str, float | int | bool]]:
        scored: list[dict[str, float | int | bool]] = []
        for sector in self._belief.sectors:
            selectable = sector.state in {BELIEF_STATE_CANDIDATE, BELIEF_STATE_ACTIVE}
            remaining_depth_norm = max(
                0.0,
                min(1.0, float(sector.remaining_depth_proxy_m) / 0.08),
            )
            distance = abs(int(sector.sector_id) - int(anchor_sector_id))
            continuity_norm = 1.0 if distance == 0 else 0.5 if distance == 1 else 0.0
            frontier_bonus_norm = 1.0 if int(sector.visit_count) == 0 else 0.0
            revisit_penalty = max(0.0, min(1.0, max(int(sector.visit_count) - 1, 0) / 3.0))
            collision_risk_norm = max(0.0, min(1.0, float(sector.collision_risk)))
            score = (
                0.50 * remaining_depth_norm
                + 0.20 * continuity_norm
                + 0.15 * frontier_bonus_norm
                - 0.10 * revisit_penalty
                - 0.05 * collision_risk_norm
            )
            scored.append(
                {
                    "sector_id": int(sector.sector_id),
                    "selectable": bool(selectable),
                    "remaining_depth_norm": float(remaining_depth_norm),
                    "continuity_norm": float(continuity_norm),
                    "frontier_bonus_norm": float(frontier_bonus_norm),
                    "revisit_penalty": float(revisit_penalty),
                    "collision_risk_norm": float(collision_risk_norm),
                    "score": float(score),
                }
            )
        return scored

    def _select_sector(
        self,
        *,
        scored: list[dict[str, float | int | bool]],
        anchor_sector_id: int,
    ) -> int:
        selectable = [item for item in scored if bool(item["selectable"])]
        if not selectable:
            return int(anchor_sector_id)
        selectable.sort(
            key=lambda item: (
                -float(item["score"]),
                -float(item["continuity_norm"]),
                int(item["sector_id"]),
            )
        )
        return int(selectable[0]["sector_id"])
