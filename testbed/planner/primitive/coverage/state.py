"""Mutable runtime state owner for primitive coverage planning."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from testbed.planner.primitive.coverage.selection import CoverageCorridorState


@dataclass(frozen=True)
class CoverageActiveExecutionContract:
    """Atomically locked tuple, paired-return, and planned-handoff evidence."""

    corridor_id: int
    effect_outcome_cell_id: int
    return_envelope_cell_id: int
    exemplar_id: str
    raw_fields_sha256: str
    start_reachability_evaluation: Any = None
    planned_handoff_worktool_sweep_evaluation: Any = None

    @property
    def exact_start_contract_required(self) -> bool:
        evaluation = self.start_reachability_evaluation
        return bool(
            evaluation is not None
            and bool(getattr(evaluation, "eligible", False))
            and str(getattr(evaluation, "selection_phase", ""))
            == "post_return"
        )


@dataclass
class CoverageRuntimeState:
    """Owns the mutable coverage state used by selection, effects, and reports."""

    coverage_corridors: list[CoverageCorridorState] = field(default_factory=list)
    coverage_active_corridor_id: int = -1
    coverage_last_selected_corridor_id: int = -1
    coverage_current_payload_gain_kg: float = 0.0
    coverage_cycle_start_deposit_kg: float = 0.0
    coverage_last_payload_gain_kg: float = 0.0
    coverage_last_effective_deposit_delta_kg: float = 0.0
    coverage_global_low_productivity_streak: int = 0
    coverage_completed_dump_count: int = 0
    coverage_pass_index: int = 0
    coverage_terminal_stop_requested: bool = False
    coverage_terminal_stop_reason: str = ""
    coverage_candidate_scores: list[dict[str, Any]] = field(default_factory=list)
    coverage_decision_trace: list[dict[str, Any]] = field(default_factory=list)
    coverage_wall_rejected_corridor_ids: set[int] = field(default_factory=set)
    coverage_wall_rejected_cell_ids: set[int] = field(default_factory=set)
    coverage_depth_exhausted_physical_cell_ids: set[int] = field(
        default_factory=set
    )
    coverage_wall_safety_final_fields: dict[str, Any] = field(
        default_factory=dict
    )
    coverage_active_effect_outcome_cell_id: int = -1
    coverage_last_selected_effect_outcome_cell_id: int = -1
    coverage_active_return_envelope_cell_id: int = -1
    coverage_active_execution_exemplar_id: str = ""
    coverage_active_execution_raw_fields: dict[str, float | int] = field(
        default_factory=dict
    )
    coverage_active_execution_raw_fields_sha256: str = ""
    coverage_active_execution_tail_plane_depth_reserve_m: float = float("nan")
    coverage_active_execution_trace: dict[str, Any] = field(
        default_factory=dict
    )
    coverage_active_execution_contract: (
        CoverageActiveExecutionContract | None
    ) = None
    coverage_active_continuous_execution_plan: Any = None
    coverage_final_live_handoff_guard_result: Any = None
    coverage_active_state_exemplar_ids: list[str] = field(default_factory=list)
    coverage_rejected_state_exemplar_ids: set[str] = field(default_factory=set)
    coverage_active_state_exemplar_distance: float = float("nan")
    coverage_active_state_exemplar_profile_token: np.ndarray | None = None
    coverage_first_plan_pose_stability_last_pose_m: tuple[
        float,
        float,
        float,
    ] | None = None
    coverage_first_plan_pose_stability_hold_count: int = 0
    coverage_first_plan_pose_stability_wait_count: int = 0
    coverage_first_plan_pose_stability_spike_count: int = 0
    coverage_first_plan_pose_stability_ready: bool = False
    coverage_first_plan_pose_stability_timed_out: bool = False

    def reset(self) -> None:
        fresh = type(self)()
        self.__dict__.update(fresh.__dict__)

    def corridor_by_id(self, corridor_id: int) -> CoverageCorridorState | None:
        for corridor in self.coverage_corridors:
            if int(corridor.corridor_id) == int(corridor_id):
                return corridor
        return None

    def active_corridor(self) -> CoverageCorridorState | None:
        if int(self.coverage_active_effect_outcome_cell_id) >= 0:
            for corridor in self.coverage_corridors:
                if (
                    int(corridor.cell_id)
                    == int(self.coverage_active_effect_outcome_cell_id)
                ):
                    return corridor
        return self.corridor_by_id(self.coverage_active_corridor_id)

    def active_execution_corridor_id(self) -> int:
        return int(self.coverage_active_corridor_id)

    def set_active_execution_candidate(
        self,
        *,
        corridor_id: int,
        effect_outcome_cell_id: int,
        return_envelope_cell_id: int,
        exemplar_id: str,
        raw_fields: dict[str, float | int] | None = None,
        raw_fields_sha256: str,
        execution_tail_plane_depth_reserve_m: float,
        trace: dict[str, Any] | None = None,
        start_reachability_evaluation: Any = None,
        planned_handoff_worktool_sweep_evaluation: Any = None,
    ) -> None:
        outcome_cell_id = int(effect_outcome_cell_id)
        return_cell_id = int(return_envelope_cell_id)
        if not 0 <= outcome_cell_id < 6:
            raise ValueError(
                f"invalid coverage effect outcome cell id: {outcome_cell_id}"
            )
        if not 0 <= return_cell_id < 6:
            raise ValueError(
                f"invalid coverage return envelope cell id: {return_cell_id}"
            )
        self.coverage_active_corridor_id = int(corridor_id)
        self.coverage_last_selected_corridor_id = int(corridor_id)
        self.coverage_active_effect_outcome_cell_id = outcome_cell_id
        self.coverage_last_selected_effect_outcome_cell_id = outcome_cell_id
        self.coverage_active_return_envelope_cell_id = return_cell_id
        self.coverage_active_execution_exemplar_id = str(exemplar_id)
        self.coverage_active_execution_raw_fields = dict(raw_fields or {})
        self.coverage_active_execution_raw_fields_sha256 = str(
            raw_fields_sha256
        )
        self.coverage_active_execution_tail_plane_depth_reserve_m = float(
            execution_tail_plane_depth_reserve_m
        )
        self.coverage_active_execution_trace = dict(trace or {})
        self.coverage_active_execution_contract = (
            CoverageActiveExecutionContract(
                corridor_id=int(corridor_id),
                effect_outcome_cell_id=outcome_cell_id,
                return_envelope_cell_id=return_cell_id,
                exemplar_id=str(exemplar_id),
                raw_fields_sha256=str(raw_fields_sha256),
                start_reachability_evaluation=(
                    start_reachability_evaluation
                ),
                planned_handoff_worktool_sweep_evaluation=(
                    planned_handoff_worktool_sweep_evaluation
                ),
            )
        )
        self.coverage_final_live_handoff_guard_result = None

    def clear_active_execution_candidate(self) -> None:
        self.coverage_active_effect_outcome_cell_id = -1
        self.coverage_active_return_envelope_cell_id = -1
        self.coverage_active_execution_exemplar_id = ""
        self.coverage_active_execution_raw_fields = {}
        self.coverage_active_execution_raw_fields_sha256 = ""
        self.coverage_active_execution_tail_plane_depth_reserve_m = float(
            "nan"
        )
        self.coverage_active_execution_trace = {}
        self.coverage_active_execution_contract = None
        self.coverage_active_continuous_execution_plan = None
        self.coverage_final_live_handoff_guard_result = None

    def set_active_continuous_execution_plan(
        self,
        *,
        corridor: CoverageCorridorState,
        locked_plan: Any,
    ) -> None:
        """Commit one complete continuous plan without exact-tuple identity."""

        goal = getattr(locked_plan, "goal", None)
        if (
            goal is None
            or int(getattr(goal, "target_cell_id", -1))
            != int(corridor.cell_id)
            or len(str(getattr(locked_plan, "goal_id", ""))) != 64
        ):
            raise ValueError(
                "continuous_goal_contract_invalid: corridor identity drift"
            )
        self.clear_active_execution_candidate()
        self.coverage_active_corridor_id = int(corridor.corridor_id)
        self.coverage_last_selected_corridor_id = int(corridor.corridor_id)
        self.coverage_active_effect_outcome_cell_id = int(corridor.cell_id)
        self.coverage_last_selected_effect_outcome_cell_id = int(
            corridor.cell_id
        )
        self.coverage_active_return_envelope_cell_id = int(corridor.cell_id)
        self.coverage_active_execution_raw_fields = dict(
            getattr(locked_plan, "raw_fields", {}) or {}
        )
        self.coverage_active_execution_raw_fields_sha256 = str(
            getattr(locked_plan, "raw_fields_sha256", "")
        )
        self.coverage_active_execution_trace = {
            "mode": "continuous_goal_conditioned",
            "goal_id": str(getattr(locked_plan, "goal_id", "")),
            "planned_qpos_path_sha256": str(
                getattr(locked_plan, "planned_qpos_path_sha256", "")
            ),
        }
        self.coverage_active_continuous_execution_plan = locked_plan

    def active_exact_return_transition(self) -> Any | None:
        """Return the locked post-return contract, never a cell-prior alias."""

        contract = self.coverage_active_execution_contract
        if contract is None or not contract.exact_start_contract_required:
            return None
        return contract.start_reachability_evaluation

    def execution_return_envelope_cell_id(
        self,
        corridor_id: int,
    ) -> int | None:
        if (
            int(corridor_id) == int(self.coverage_active_corridor_id)
            and 0 <= int(self.coverage_active_return_envelope_cell_id) < 6
        ):
            return int(self.coverage_active_return_envelope_cell_id)
        return None

    def depleted_count(self) -> int:
        return int(sum(1 for corridor in self.coverage_corridors if corridor.depleted))

    def all_depleted(self) -> bool:
        return bool(
            self.coverage_corridors
            and all(corridor.depleted for corridor in self.coverage_corridors)
        )

    def set_coverage_corridors(
        self,
        corridors: list[CoverageCorridorState],
    ) -> None:
        self.coverage_corridors = corridors

    def set_candidate_scores(self, candidate_scores: list[dict[str, Any]]) -> None:
        self.coverage_candidate_scores = list(candidate_scores)

    def reject_wall_corridor(
        self,
        corridor_id: int,
        *,
        cell_id: int | None = None,
    ) -> None:
        self.coverage_wall_rejected_corridor_ids.add(int(corridor_id))
        if cell_id is not None and int(cell_id) >= 0:
            self.coverage_wall_rejected_cell_ids.add(int(cell_id))

    def wall_corridor_rejected(self, corridor_id: int) -> bool:
        return int(corridor_id) in self.coverage_wall_rejected_corridor_ids

    def mark_depth_exhausted_physical_cell(self, cell_id: int) -> None:
        value = int(cell_id)
        if value < 0 or value >= 6:
            raise ValueError(f"invalid physical depth-exhausted cell id: {value}")
        self.coverage_depth_exhausted_physical_cell_ids.add(value)

    def set_wall_safety_final_fields(self, fields: dict[str, Any]) -> None:
        self.coverage_wall_safety_final_fields = dict(fields)

    def set_active_corridor_id(self, value: int) -> None:
        if (
            int(value) != int(self.coverage_active_corridor_id)
            and int(self.coverage_active_effect_outcome_cell_id) >= 0
        ):
            self.clear_active_execution_candidate()
        self.coverage_active_corridor_id = int(value)

    def set_last_selected_corridor_id(self, value: int) -> None:
        self.coverage_last_selected_corridor_id = int(value)

    def set_selected_corridor_ids(
        self,
        *,
        active_corridor_id: int,
        last_selected_corridor_id: int,
    ) -> None:
        self.set_active_corridor_id(active_corridor_id)
        self.set_last_selected_corridor_id(last_selected_corridor_id)

    def set_current_payload_gain_kg(self, value: float) -> None:
        self.coverage_current_payload_gain_kg = float(value)

    def set_cycle_start_deposit_kg(self, value: float) -> None:
        self.coverage_cycle_start_deposit_kg = float(value)

    def set_last_payload_gain_kg(self, value: float) -> None:
        self.coverage_last_payload_gain_kg = float(value)

    def set_last_effective_deposit_delta_kg(self, value: float) -> None:
        self.coverage_last_effective_deposit_delta_kg = float(value)

    def set_completed_dump_count(self, value: int) -> None:
        self.coverage_completed_dump_count = int(value)

    def set_global_low_productivity_streak(self, value: int) -> None:
        self.coverage_global_low_productivity_streak = int(value)

    def set_coverage_pass_index(self, value: int) -> None:
        self.coverage_pass_index = int(value)

    def set_terminal_stop(self, *, requested: bool, reason: str) -> None:
        self.coverage_terminal_stop_requested = bool(requested)
        self.coverage_terminal_stop_reason = str(reason)

    def set_terminal_stop_requested(self, value: bool) -> None:
        self.coverage_terminal_stop_requested = bool(value)

    def set_terminal_stop_reason(self, value: str) -> None:
        self.coverage_terminal_stop_reason = str(value)

    def update_rejected_state_exemplar_ids(
        self,
        exemplar_ids: tuple[str, ...],
    ) -> None:
        self.coverage_rejected_state_exemplar_ids.update(exemplar_ids)

    def clear_rejected_state_exemplar_ids(self) -> None:
        self.coverage_rejected_state_exemplar_ids.clear()

    def set_active_state_exemplar(
        self,
        *,
        exemplar_ids: list[str],
        distance: float,
        profile_token: np.ndarray | None,
    ) -> None:
        self.coverage_active_state_exemplar_ids = list(exemplar_ids)
        self.coverage_active_state_exemplar_distance = float(distance)
        self.coverage_active_state_exemplar_profile_token = profile_token

    def clear_active_state_exemplar(self) -> None:
        self.coverage_active_state_exemplar_ids = []
        self.coverage_active_state_exemplar_distance = float("nan")
        self.coverage_active_state_exemplar_profile_token = None


__all__ = [
    "CoverageActiveExecutionContract",
    "CoverageRuntimeState",
]
