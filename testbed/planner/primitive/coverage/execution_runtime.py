"""Runtime selection of exact strict-train coverage execution tuples."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np

from testbed.planner.primitive.coverage.config import (
    CoverageExecutionLibraryConfig,
)
from testbed.planner.primitive.coverage.execution_candidates import (
    CoverageCorridorPrototype,
    CoverageExecutionCandidateContractError,
    CoverageExecutionCandidateService,
    CoverageOutcomeCellState,
    NoCoverageExecutionCandidateError,
    ResolvedCoverageCandidate,
)
from testbed.planner.primitive.coverage.selection import (
    CoverageCorridorState,
    CoverageSelectionService,
)
from testbed.planner.primitive.coverage.start_reachability import (
    CoverageTupleStartReachabilityContractError,
    CoverageTupleStartReachabilityService,
)
from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.coverage.wall_safety import (
    CoverageWallSafetyConfig,
    CoverageWallSafetyService,
    NoWallSafeCorridorError,
)
from testbed.planner.primitive.coverage.worktool_sweep import (
    NO_3D_WALL_SAFE_CORRIDOR_REASON,
    CoverageWorktoolSweepContractError,
    CoverageWorktoolSweepService,
)

NO_TUPLE_START_REACHABLE_REASON = "no_tuple_start_reachable"


@dataclass(frozen=True)
class CoverageExecutionRuntimeResult:
    """Compatibility corridor plus the selected immutable expert tuple."""

    candidate: ResolvedCoverageCandidate
    corridor: CoverageCorridorState
    raw_fields: dict[str, float | int]


@dataclass(frozen=True)
class CoverageExecutionLibraryRuntime:
    """Load, verify, select, and commit one exact execution-library tuple."""

    config: CoverageExecutionLibraryConfig
    wall_safety_config: CoverageWallSafetyConfig
    state: CoverageRuntimeState
    selection_service: CoverageSelectionService

    def select(
        self,
        *,
        env_state: Any,
        current_qpos: Any,
        bucket_tip_dig_area_pose: tuple[float, float, float] | None,
        remaining_depth_by_outcome_cell_id: dict[int, float],
        recent_row_reference: CoverageCorridorState | None,
        update_state: bool,
        current_qvel: Any = None,
    ) -> CoverageExecutionRuntimeResult:
        """Select K=1 without synthesizing or rewriting any tuple field."""

        if not self.config.enabled:
            raise CoverageExecutionCandidateContractError(
                "execution_library_runtime_disabled"
            )
        try:
            library = self._load_verified_library()
            worktool_sweep_service = (
                CoverageWorktoolSweepService.from_config(self.config.worktool_sweep_3d)
                if self.config.worktool_sweep_3d.enabled
                else None
            )
            tuple_start_reachability_service = (
                CoverageTupleStartReachabilityService.from_config(
                    self.config.start_reachability
                )
                if self.config.start_reachability.enabled
                else None
            )
            candidate_service = CoverageExecutionCandidateService(
                wall_safety_service=CoverageWallSafetyService(self.wall_safety_config),
                hard_bottom_margin_m=float(self.config.hard_bottom_margin_m),
                worktool_sweep_service=worktool_sweep_service,
                tuple_start_reachability_service=(tuple_start_reachability_service),
            )
            prototypes = candidate_service.parse_library(library)
            outcome_corridors = self._outcome_corridors()
            outcome_states = [
                CoverageOutcomeCellState(
                    effect_outcome_cell_id=int(corridor.cell_id),
                    attempts=int(corridor.attempts),
                    attempt_limit=int(
                        self.selection_service.corridor_attempt_limit(corridor)
                    ),
                    depleted=bool(corridor.depleted),
                )
                for corridor in outcome_corridors
            ]
            cell_scores = {
                int(corridor.cell_id): float(
                    self.selection_service.score(
                        corridor,
                        float(
                            remaining_depth_by_outcome_cell_id[int(corridor.cell_id)]
                        ),
                        state_exemplar_distance=float("nan"),
                        recent_row_reference=recent_row_reference,
                    )
                )
                for corridor in outcome_corridors
            }
            blocked = set(self.state.coverage_wall_rejected_corridor_ids)
            rejected_exemplars = set(self.state.coverage_rejected_state_exemplar_ids)
            blocked.update(
                int(prototype.corridor_id)
                for prototype in prototypes
                if prototype.exemplar_id in rejected_exemplars
            )
            candidate = candidate_service.select(
                library=library,
                env_state=env_state,
                outcome_states=outcome_states,
                cell_scores_by_outcome_cell_id=cell_scores,
                blocked_corridor_ids=blocked,
                exhausted_physical_cell_ids=(
                    self.state.coverage_depth_exhausted_physical_cell_ids
                ),
                current_qpos=current_qpos,
                live_return_start_facts=(
                    self._return_start_facts(
                        qpos=current_qpos,
                        qvel=current_qvel,
                        bucket_tip_dig_area_pose=bucket_tip_dig_area_pose,
                    )
                ),
                selection_phase=self._selection_phase(),
                prototype_score_adjustment=(
                    lambda prototype: self._prototype_score_adjustment(
                        prototype,
                        bucket_tip_dig_area_pose=bucket_tip_dig_area_pose,
                    )
                ),
            )
            result = self._resolve_result(
                candidate,
                outcome_corridors=outcome_corridors,
            )
        except NoWallSafeCorridorError:
            raise
        except NoCoverageExecutionCandidateError as exc:
            raise NoWallSafeCorridorError(
                candidate_scores=[dict(item) for item in exc.candidate_trace],
                detail="execution_library_all_candidates_rejected",
                reason=self._no_candidate_reason(exc),
            ) from exc
        except CoverageTupleStartReachabilityContractError as exc:
            raise NoWallSafeCorridorError(
                detail=f"tuple_start_reachability_contract:{exc}",
                reason=NO_TUPLE_START_REACHABLE_REASON,
            ) from exc
        except (
            CoverageExecutionCandidateContractError,
            CoverageWorktoolSweepContractError,
            FileNotFoundError,
            json.JSONDecodeError,
            OSError,
            TypeError,
            ValueError,
        ) as exc:
            raise NoWallSafeCorridorError(
                detail=f"execution_library_contract:{exc}",
                reason=(
                    NO_3D_WALL_SAFE_CORRIDOR_REASON
                    if self.config.worktool_sweep_3d.enabled
                    else "no_wall_safe_corridor"
                ),
            ) from exc

        if update_state:
            self._commit(result)
        return result

    def _load_verified_library(self) -> dict[str, Any]:
        path = Path(self.config.path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"execution_library_missing:{path}")
        payload = path.read_bytes()
        actual_sha256 = hashlib.sha256(payload).hexdigest()
        if actual_sha256 != self.config.artifact_sha256:
            raise CoverageExecutionCandidateContractError(
                "execution_library_sha256_mismatch:"
                f"expected={self.config.artifact_sha256}:"
                f"actual={actual_sha256}"
            )
        value = json.loads(payload)
        if not isinstance(value, dict):
            raise CoverageExecutionCandidateContractError(
                "execution_library_root_not_mapping"
            )
        return value

    def _selection_phase(self) -> str:
        return (
            "cycle0"
            if int(self.state.coverage_completed_dump_count) <= 0
            else "post_return"
        )

    @staticmethod
    def _return_start_facts(
        *,
        qpos: Any,
        qvel: Any,
        bucket_tip_dig_area_pose: tuple[float, float, float] | None,
    ) -> tuple[float, ...] | None:
        if bucket_tip_dig_area_pose is None:
            return None
        try:
            qpos_values = np.asarray(qpos, dtype=np.float64).reshape(-1)
            qvel_values = np.asarray(qvel, dtype=np.float64).reshape(-1)
            pose_values = np.asarray(
                bucket_tip_dig_area_pose,
                dtype=np.float64,
            ).reshape(-1)
        except (TypeError, ValueError):
            return None
        if qpos_values.size < 4 or qvel_values.size < 4 or pose_values.size != 3:
            return None
        values = np.concatenate((qpos_values[:4], qvel_values[:4], pose_values))
        if not np.all(np.isfinite(values)):
            return None
        return tuple(float(value) for value in values)

    def _no_candidate_reason(
        self,
        exc: NoCoverageExecutionCandidateError,
    ) -> str:
        trace = [dict(item) for item in exc.candidate_trace]
        if self.config.start_reachability.enabled:
            evaluated = [
                item for item in trace if "tuple_start_reachability_eligible" in item
            ]
            if evaluated and not any(
                bool(item["tuple_start_reachability_eligible"]) for item in evaluated
            ):
                return NO_TUPLE_START_REACHABLE_REASON
        if self.config.worktool_sweep_3d.enabled:
            return NO_3D_WALL_SAFE_CORRIDOR_REASON
        return "no_wall_safe_corridor"

    def _outcome_corridors(self) -> list[CoverageCorridorState]:
        by_cell: dict[int, CoverageCorridorState] = {}
        for corridor in self.state.coverage_corridors:
            cell_id = int(corridor.cell_id)
            if not 0 <= cell_id < 6:
                continue
            if cell_id in by_cell:
                raise CoverageExecutionCandidateContractError(
                    f"duplicate_outcome_corridor:{cell_id}"
                )
            by_cell[cell_id] = corridor
        if set(by_cell) != set(range(6)):
            raise CoverageExecutionCandidateContractError(
                "outcome_corridor_set_must_equal_0_through_5"
            )
        return [by_cell[cell_id] for cell_id in range(6)]

    def _prototype_score_adjustment(
        self,
        prototype: CoverageCorridorPrototype,
        *,
        bucket_tip_dig_area_pose: tuple[float, float, float] | None,
    ) -> float:
        service = self.selection_service
        if not service.first_dig_active():
            return 0.0
        strategy = str(service.config.first_dig_strategy)
        if strategy in {"nearest_entry", "bootstrap_nearest_entry"}:
            if bucket_tip_dig_area_pose is None:
                return -math.inf
            bucket_x, _, bucket_z = bucket_tip_dig_area_pose
            raw_fields = prototype.raw_fields
            distance = float(
                np.hypot(
                    float(bucket_x) - float(raw_fields["operator_entry_x_m"]),
                    float(bucket_z) - float(raw_fields["operator_entry_z_m"]),
                )
            )
            if not math.isfinite(distance):
                return -math.inf
            maximum = service.config.first_dig_max_entry_distance_m
            if maximum is not None and distance > float(maximum):
                return -math.inf
            return -float(service.config.first_dig_proximity_weight) * distance
        if strategy in {"preferred_corridor", "bootstrap_friendly"}:
            preferred = service.config.first_dig_preferred_corridor_id
            if preferred is None:
                return 0.0
            if int(prototype.effect_outcome_cell_id) == int(preferred):
                return float(service.config.first_dig_preferred_bonus)
        return 0.0

    def _resolve_result(
        self,
        candidate: ResolvedCoverageCandidate,
        *,
        outcome_corridors: list[CoverageCorridorState],
    ) -> CoverageExecutionRuntimeResult:
        outcome = next(
            corridor
            for corridor in outcome_corridors
            if int(corridor.cell_id) == int(candidate.effect_outcome_cell_id)
        )
        raw_fields = dict(candidate.raw_fields)
        corridor = replace(
            outcome,
            corridor_id=int(candidate.corridor_id),
            entry_x_m=float(raw_fields["operator_entry_x_m"]),
            entry_z_m=float(raw_fields["operator_entry_z_m"]),
            exit_x_m=float(raw_fields["operator_exit_x_m"]),
            exit_z_m=float(raw_fields["operator_exit_z_m"]),
            cell_id=int(candidate.effect_outcome_cell_id),
            cut_depth_peak_m=float(raw_fields["operator_cut_depth_peak_m"]),
            payload_gain_kg=float(raw_fields["operator_cut_payload_gain_kg"]),
            effective_deposit_delta_kg=float(
                raw_fields["operator_effective_deposit_delta_kg"]
            ),
            score=float(candidate.final_score),
            state_exemplar_id=str(candidate.exemplar_id),
            state_exemplar_distance=float(candidate.removed_depth_distance),
        )
        return CoverageExecutionRuntimeResult(
            candidate=candidate,
            corridor=corridor,
            raw_fields=raw_fields,
        )

    def _commit(self, result: CoverageExecutionRuntimeResult) -> None:
        candidate = result.candidate
        full_trace_fields = candidate.as_trace_fields()
        full_candidate_trace = list(full_trace_fields.pop("coverage_candidate_scores"))
        trace = {
            **full_trace_fields,
            "coverage_execution_library_path": str(
                Path(self.config.path).expanduser().resolve()
            ),
            "coverage_execution_library_sha256": str(self.config.artifact_sha256),
            "coverage_execution_library_mode": str(self.config.mode),
            "coverage_execution_candidate_trace_total_count": len(full_candidate_trace),
        }
        self.state.set_candidate_scores(
            compact_execution_candidate_trace(full_candidate_trace)
        )
        self.state.set_active_execution_candidate(
            corridor_id=int(candidate.corridor_id),
            effect_outcome_cell_id=int(candidate.effect_outcome_cell_id),
            return_envelope_cell_id=int(candidate.return_envelope_cell_id),
            exemplar_id=str(candidate.exemplar_id),
            raw_fields=dict(result.raw_fields),
            raw_fields_sha256=str(candidate.raw_fields_sha256),
            execution_tail_plane_depth_reserve_m=float(
                candidate.execution_tail_plane_depth_reserve_m
            ),
            trace=trace,
            start_reachability_evaluation=(candidate.start_reachability_evaluation),
            planned_handoff_worktool_sweep_evaluation=(
                candidate.worktool_sweep_evaluation
            ),
        )
        self.state.set_active_state_exemplar(
            exemplar_ids=[str(candidate.exemplar_id)],
            distance=float(candidate.removed_depth_distance),
            profile_token=None,
        )
        self.state.set_wall_safety_final_fields(
            candidate.wall_evaluation.as_trace_fields()
        )


def compact_execution_candidate_trace(
    candidate_trace: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep one representative per outcome cell for per-step debug logs."""

    if len(candidate_trace) <= 6:
        return [dict(item) for item in candidate_trace]
    status_rank = {
        "selected": 0,
        "eligible_cell_k1": 1,
        "eligible_not_selected_cross_cell": 2,
        "eligible_pre_k1": 3,
        "rejected": 4,
        "pending": 5,
    }
    by_cell: dict[int, dict[str, Any]] = {}
    for raw_item in candidate_trace:
        item = dict(raw_item)
        cell_id = int(item.get("effect_outcome_cell_id", -1))
        if not 0 <= cell_id < 6:
            continue
        current = by_cell.get(cell_id)
        key = (
            status_rank.get(str(item.get("status", "")), 99),
            int(item.get("corridor_id", -1)),
        )
        if current is None:
            by_cell[cell_id] = item
            continue
        current_key = (
            status_rank.get(str(current.get("status", "")), 99),
            int(current.get("corridor_id", -1)),
        )
        if key < current_key:
            by_cell[cell_id] = item
    compact = [by_cell[cell_id] for cell_id in sorted(by_cell)]
    for item in compact:
        item["candidate_trace_compacted"] = True
        item["candidate_trace_total_count"] = len(candidate_trace)
    return compact


__all__ = [
    "CoverageExecutionLibraryRuntime",
    "CoverageExecutionRuntimeResult",
    "compact_execution_candidate_trace",
    "NO_TUPLE_START_REACHABLE_REASON",
]
