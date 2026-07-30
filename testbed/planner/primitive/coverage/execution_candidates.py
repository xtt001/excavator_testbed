"""Select immutable strict-train execution tuples for coverage planning.

The strict execution library stores hindsight effect labels, stable exemplar
corridor identities, return-envelope labels, and real cut tuples.  These
identities are deliberately kept separate here.  Physical cells are recomputed
from the live 107D geometry before any tuple can be selected.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any

import numpy as np

from testbed.data.schema import (
    ENV_STATE_DIG_AREA_CELL_LONG_SIZE_IDX,
    ENV_STATE_DIG_AREA_CELL_SHORT_SIZE_IDX,
    ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
    ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX,
    ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX,
    ENV_STATE_DIG_AREA_HARD_BOTTOM_DEPTH_IDX,
    ENV_STATE_DIG_AREA_LONG_AXIS_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
    ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX,
    ENV_STATE_V2_4_DIM,
)
from testbed.planner.primitive.coverage.execution_library_contract import (
    COVERAGE_EXECUTION_CANDIDATE_LIBRARY_SCHEMA,
    COVERAGE_EXECUTION_CORRIDOR_ID_BASE,
    COVERAGE_GRID_CELL_COUNT,
    CoverageCorridorPrototype,
    CoverageExecutionCandidateContractError,
    CoverageExecutionLibraryContractParser,
    finite_contract_float,
    raise_execution_contract_error,
    validate_axis_id,
    validate_cell_id,
    validate_positive_int,
)
from testbed.planner.primitive.coverage.start_reachability import (
    CoverageTupleStartReachabilityEvaluation,
    CoverageTupleStartReachabilityService,
)
from testbed.planner.primitive.coverage.wall_safety import (
    CoverageWallSafetyEvaluation,
    CoverageWallSafetyService,
)
from testbed.planner.primitive.coverage.worktool_sweep import (
    CoverageWorktoolSweepEvaluation,
    CoverageWorktoolSweepService,
)

_GRID_CELL_COUNT = COVERAGE_GRID_CELL_COUNT
_axis_id = validate_axis_id
_cell_id = validate_cell_id
_finite_float = finite_contract_float
_positive_int = validate_positive_int
_fail = raise_execution_contract_error


class NoCoverageExecutionCandidateError(RuntimeError):
    """Raised after every real tuple has been rejected by a hard gate."""

    def __init__(
        self,
        *,
        rejection_reasons: Sequence[tuple[int, str]] = (),
        candidate_trace_items: tuple[
            tuple[tuple[str, Any], ...],
            ...,
        ] = (),
    ) -> None:
        self.rejection_reasons = tuple(
            (int(corridor_id), str(reason)) for corridor_id, reason in rejection_reasons
        )
        self._candidate_trace_items = tuple(candidate_trace_items)
        detail = ",".join(
            f"{corridor_id}:{reason}" for corridor_id, reason in self.rejection_reasons
        )
        message = "no_coverage_execution_candidate"
        if detail:
            message = f"{message}:{detail}"
        super().__init__(message)

    @property
    def candidate_trace(self) -> tuple[Mapping[str, Any], ...]:
        """Immutable all-tuple trace, also available on fail-closed exits."""

        return tuple(
            MappingProxyType(dict(items)) for items in self._candidate_trace_items
        )


@dataclass(frozen=True)
class CoverageOutcomeCellState:
    """Planner-owned attempt/depletion state for one effect outcome cell."""

    effect_outcome_cell_id: int
    attempts: int
    attempt_limit: int
    depleted: bool

    def __post_init__(self) -> None:
        _cell_id(
            self.effect_outcome_cell_id,
            label="effect_outcome_cell_id",
        )
        if int(self.attempts) < 0:
            _fail("outcome_attempts_negative")
        if int(self.attempt_limit) <= 0:
            _fail("outcome_attempt_limit_non_positive")

    @property
    def cell_id(self) -> int:
        """Read-only compatibility alias for the effect outcome label."""

        return int(self.effect_outcome_cell_id)


@dataclass(frozen=True)
class ResolvedCoverageCandidate:
    """One real tuple after every live eligibility gate has passed."""

    prototype: CoverageCorridorPrototype
    outcome_state: CoverageOutcomeCellState
    live_centerline_physical_cell_ids: tuple[int, ...]
    live_swept_physical_cell_ids: tuple[int, ...]
    wall_evaluation: CoverageWallSafetyEvaluation
    removed_depth_distance: float
    planned_hard_bottom_clearance_before_tail_m: float
    planned_hard_bottom_budget_after_tail_m: float
    cell_score: float
    prototype_score_adjustment: float
    final_score: float
    worktool_sweep_evaluation: CoverageWorktoolSweepEvaluation | None = None
    start_reachability_evaluation: CoverageTupleStartReachabilityEvaluation | None = (
        None
    )
    candidate_trace_items: tuple[
        tuple[tuple[str, Any], ...],
        ...,
    ] = ()

    @property
    def corridor_id(self) -> int:
        return int(self.prototype.corridor_id)

    @property
    def exemplar_id(self) -> str:
        return str(self.prototype.exemplar_id)

    @property
    def source_primitive_episode_id(self) -> int:
        return int(self.prototype.source_primitive_episode_id)

    @property
    def source_episode_id(self) -> int:
        return int(self.prototype.source_episode_id)

    @property
    def effect_outcome_cell_id(self) -> int:
        return int(self.prototype.effect_outcome_cell_id)

    @property
    def cell_id(self) -> int:
        """Read-only compatibility alias for the effect outcome label."""

        return int(self.effect_outcome_cell_id)

    @property
    def return_envelope_cell_id(self) -> int:
        return int(self.prototype.return_envelope_cell_id)

    @property
    def raw_fields(self) -> Mapping[str, float | int]:
        return self.prototype.raw_fields

    @property
    def raw_fields_sha256(self) -> str:
        return str(self.prototype.raw_fields_sha256)

    @property
    def dig_cut_tokens(self) -> tuple[float, ...]:
        return tuple(self.prototype.dig_cut_tokens)

    @property
    def execution_tail_plane_depth_reserve_m(self) -> float:
        return float(self.prototype.execution_tail_plane_depth_reserve_m)

    @property
    def loo_p99_distance(self) -> float:
        return float(self.prototype.loo_p99_distance)

    @property
    def wall_minimum_clearance_m(self) -> float:
        return float(self.wall_evaluation.minimum_clearance_m)

    @property
    def wall_score_penalty(self) -> float:
        return float(self.wall_evaluation.score_penalty)

    @property
    def candidate_trace(self) -> tuple[Mapping[str, Any], ...]:
        """Immutable score/rejection evidence for every library tuple."""

        return tuple(
            MappingProxyType(dict(items)) for items in self.candidate_trace_items
        )

    def as_trace_fields(self) -> dict[str, Any]:
        """Return explicit identities and live gate evidence for rollout logs."""

        fields = {
            "corridor_id": self.corridor_id,
            "exemplar_id": self.exemplar_id,
            "source_primitive_episode_id": self.source_primitive_episode_id,
            "source_episode_id": self.source_episode_id,
            "effect_outcome_cell_id": self.effect_outcome_cell_id,
            "return_envelope_cell_id": self.return_envelope_cell_id,
            "live_centerline_physical_cell_ids": list(
                self.live_centerline_physical_cell_ids
            ),
            "live_swept_physical_cell_ids": list(self.live_swept_physical_cell_ids),
            "raw_fields_sha256": self.raw_fields_sha256,
            "removed_depth_distance": float(self.removed_depth_distance),
            "loo_p99_distance": self.loo_p99_distance,
            "planned_hard_bottom_clearance_before_tail_m": float(
                self.planned_hard_bottom_clearance_before_tail_m
            ),
            "execution_tail_plane_depth_reserve_m": (
                self.execution_tail_plane_depth_reserve_m
            ),
            "planned_hard_bottom_budget_after_tail_m": float(
                self.planned_hard_bottom_budget_after_tail_m
            ),
            "cell_score": float(self.cell_score),
            "prototype_score_adjustment": float(self.prototype_score_adjustment),
            "final_score": float(self.final_score),
            "coverage_candidate_scores": [dict(item) for item in self.candidate_trace],
            **self.wall_evaluation.as_trace_fields(),
        }
        if self.worktool_sweep_evaluation is not None:
            fields.update(self.worktool_sweep_evaluation.as_trace_fields())
        if self.start_reachability_evaluation is not None:
            fields.update(self.start_reachability_evaluation.as_trace_fields())
        return fields


@dataclass(frozen=True)
class CoverageExecutionCandidateService:
    """Apply live geometry, support, safety, and outcome-state gates."""

    wall_safety_service: CoverageWallSafetyService
    hard_bottom_margin_m: float = 0.02
    worktool_sweep_service: CoverageWorktoolSweepService | None = None
    tuple_start_reachability_service: CoverageTupleStartReachabilityService | None = (
        None
    )

    def __post_init__(self) -> None:
        margin = float(self.hard_bottom_margin_m)
        if not math.isfinite(margin) or margin < 0.0:
            _fail("hard_bottom_margin_invalid")
        if not self.wall_safety_service.config.enabled:
            _fail("wall_safety_must_be_enabled")

    def parse_library(
        self,
        library: Mapping[str, Any],
    ) -> tuple[CoverageCorridorPrototype, ...]:
        """Parse and deep-freeze a strict execution library."""

        return self._library_parser().parse(library).prototypes

    def select(
        self,
        *,
        library: Mapping[str, Any],
        env_state: Any,
        outcome_states: Sequence[CoverageOutcomeCellState],
        cell_scores_by_outcome_cell_id: Mapping[int, float],
        blocked_corridor_ids: Collection[int] = (),
        exhausted_physical_cell_ids: Collection[int] = (),
        current_qpos: Any = None,
        live_return_start_facts: Any = None,
        selection_phase: str = "cycle0",
        prototype_score_adjustment: (
            Callable[[CoverageCorridorPrototype], float] | None
        ) = None,
    ) -> ResolvedCoverageCandidate:
        """Select K=1 within each cell, then preserve A0 cross-cell scoring."""

        parsed = self._library_parser().parse(library)
        env = self._validated_live_env_state(
            env_state,
            geometry_contract=parsed.geometry_contract,
        )
        states = self._outcome_states_by_id(outcome_states)
        scores = self._validated_cell_scores(
            cell_scores_by_outcome_cell_id,
            required_cell_ids={
                prototype.effect_outcome_cell_id for prototype in parsed.prototypes
            },
        )
        blocked = {int(value) for value in blocked_corridor_ids}
        exhausted = {
            _cell_id(value, label="exhausted_physical_cell_id")
            for value in exhausted_physical_cell_ids
        }
        removed_depth = _finite_env_grid(
            env,
            start_index=ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
            label="live_removed_depth_grid",
        )
        surface_depth = _finite_env_grid(
            env,
            start_index=ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX,
            label="live_surface_depth_grid",
        )
        valid_mask = _finite_env_grid(
            env,
            start_index=ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
            label="live_cell_valid_mask",
        )
        hard_bottom_depth = float(env[ENV_STATE_DIG_AREA_HARD_BOTTOM_DEPTH_IDX])
        if not math.isfinite(hard_bottom_depth) or hard_bottom_depth <= 0.0:
            _fail("live_hard_bottom_depth_invalid")

        trace_order = [int(prototype.corridor_id) for prototype in parsed.prototypes]
        trace_by_corridor: dict[int, dict[str, Any]] = {
            int(prototype.corridor_id): {
                "corridor_id": int(prototype.corridor_id),
                "exemplar_id": str(prototype.exemplar_id),
                "source_primitive_episode_id": int(
                    prototype.source_primitive_episode_id
                ),
                "source_episode_id": int(prototype.source_episode_id),
                "effect_outcome_cell_id": int(prototype.effect_outcome_cell_id),
                "return_envelope_cell_id": int(prototype.return_envelope_cell_id),
                "raw_fields_sha256": str(prototype.raw_fields_sha256),
                "status": "pending",
                "rejection_reason": "",
            }
            for prototype in parsed.prototypes
        }

        def reject(
            prototype: CoverageCorridorPrototype,
            reason: str,
        ) -> None:
            corridor_id = int(prototype.corridor_id)
            rejections.append((corridor_id, str(reason)))
            trace_by_corridor[corridor_id].update(
                status="rejected",
                rejection_reason=str(reason),
            )

        eligible_by_cell: dict[int, list[ResolvedCoverageCandidate]] = defaultdict(list)
        rejections: list[tuple[int, str]] = []
        for prototype in parsed.prototypes:
            corridor_id = int(prototype.corridor_id)
            state = states.get(prototype.effect_outcome_cell_id)
            if state is None:
                _fail(f"missing_outcome_state:{prototype.effect_outcome_cell_id}")
            if state.depleted:
                reject(prototype, "outcome_depleted")
                continue
            if state.attempts >= state.attempt_limit:
                reject(prototype, "outcome_attempt_limit")
                continue
            if corridor_id in blocked:
                reject(prototype, "corridor_blocked")
                continue

            wall = self.wall_safety_service.evaluate_raw_fields(
                env_state=env,
                raw_fields=prototype.raw_fields,
            )
            trace_by_corridor[corridor_id].update(
                wall_safety_class=str(wall.safety_class),
                wall_minimum_clearance_m=float(wall.minimum_clearance_m),
                wall_score_penalty=float(wall.score_penalty),
                live_centerline_physical_cell_ids=tuple(
                    int(value) for value in wall.centerline_cell_ids
                ),
                live_swept_physical_cell_ids=tuple(
                    int(value) for value in wall.swept_cell_ids
                ),
            )
            if not wall.eligible:
                reject(
                    prototype,
                    wall.rejection_reason or "wall_safety_rejected",
                )
                continue
            centerline = tuple(int(value) for value in wall.centerline_cell_ids)
            swept = tuple(int(value) for value in wall.swept_cell_ids)
            if not centerline or not swept:
                _fail(f"live_physical_cells_empty:{corridor_id}")
            if (
                prototype.expected_centerline_physical_cell_ids
                and centerline != prototype.expected_centerline_physical_cell_ids
            ):
                _fail(f"centerline_physical_cells_changed:{corridor_id}")
            if (
                prototype.expected_swept_physical_cell_ids
                and swept != prototype.expected_swept_physical_cell_ids
            ):
                _fail(f"swept_physical_cells_changed:{corridor_id}")
            start_reachability = None
            worktool_start_qpos = current_qpos
            if self.tuple_start_reachability_service is not None:
                start_reachability = self.tuple_start_reachability_service.evaluate(
                    exemplar_id=prototype.exemplar_id,
                    raw_fields_sha256=prototype.raw_fields_sha256,
                    live_return_start_facts=live_return_start_facts,
                    selection_phase=str(selection_phase),
                )
                trace_by_corridor[corridor_id].update(
                    start_reachability.as_trace_fields()
                )
                if not start_reachability.eligible:
                    reject(
                        prototype,
                        start_reachability.rejection_reason
                        or "tuple_start_out_of_support",
                    )
                    continue
                if str(selection_phase) == "post_return":
                    worktool_start_qpos = start_reachability.paired_handoff_qpos
            worktool_sweep = None
            if self.worktool_sweep_service is not None:
                worktool_sweep = self.worktool_sweep_service.evaluate(
                    exemplar_id=prototype.exemplar_id,
                    raw_fields_sha256=prototype.raw_fields_sha256,
                    live_start_qpos=worktool_start_qpos,
                )
                trace_by_corridor[corridor_id].update(worktool_sweep.as_trace_fields())
                if not worktool_sweep.eligible:
                    reject(
                        prototype,
                        worktool_sweep.rejection_reason
                        or "worktool_3d_geometry_missing",
                    )
                    continue
            if exhausted.intersection(swept):
                reject(
                    prototype,
                    "swept_footprint_intersects_depth_exhausted_cell",
                )
                continue
            if any(valid_mask[cell_id] < 0.5 for cell_id in swept):
                reject(prototype, "swept_cell_invalid")
                continue

            token_depth_m = float(prototype.token_depth_m)
            before_tail = float(
                min(
                    hard_bottom_depth - float(surface_depth[cell_id])
                    for cell_id in swept
                )
                - token_depth_m
            )
            after_tail = float(
                before_tail - prototype.execution_tail_plane_depth_reserve_m
            )
            trace_by_corridor[corridor_id].update(
                token_depth_m=token_depth_m,
                planned_hard_bottom_clearance_before_tail_m=before_tail,
                execution_tail_plane_depth_reserve_m=float(
                    prototype.execution_tail_plane_depth_reserve_m
                ),
                planned_hard_bottom_budget_after_tail_m=after_tail,
            )
            if after_tail + 1.0e-9 < float(self.hard_bottom_margin_m):
                reject(prototype, "hard_bottom_budget_below_margin")
                continue

            distance = _removed_depth_distance(
                removed_depth,
                prototype.start_removed_depth_grid_m,
                scale_m=parsed.removed_depth_scale_m,
                target_cell_id=prototype.effect_outcome_cell_id,
                target_cell_weight=parsed.target_cell_weight,
            )
            trace_by_corridor[corridor_id].update(
                removed_depth_distance=float(distance),
                loo_p99_distance=float(prototype.loo_p99_distance),
            )
            if distance > prototype.loo_p99_distance + 1.0e-12:
                reject(prototype, "removed_depth_out_of_support")
                continue
            cell_score = float(scores[prototype.effect_outcome_cell_id])
            trace_by_corridor[corridor_id].update(
                status="eligible_pre_k1",
                cell_score=cell_score,
                prototype_score_adjustment=0.0,
                final_score=float(cell_score - wall.score_penalty),
            )
            eligible_by_cell[prototype.effect_outcome_cell_id].append(
                ResolvedCoverageCandidate(
                    prototype=prototype,
                    outcome_state=state,
                    live_centerline_physical_cell_ids=centerline,
                    live_swept_physical_cell_ids=swept,
                    wall_evaluation=wall,
                    removed_depth_distance=float(distance),
                    planned_hard_bottom_clearance_before_tail_m=before_tail,
                    planned_hard_bottom_budget_after_tail_m=after_tail,
                    cell_score=cell_score,
                    prototype_score_adjustment=0.0,
                    final_score=float(cell_score - wall.score_penalty),
                    worktool_sweep_evaluation=worktool_sweep,
                    start_reachability_evaluation=start_reachability,
                )
            )

        per_cell: list[ResolvedCoverageCandidate] = []
        for cell_id in sorted(eligible_by_cell):
            cell_candidates = eligible_by_cell[cell_id]
            nearest_distance = min(
                item.removed_depth_distance for item in cell_candidates
            )
            nearest = [
                item
                for item in cell_candidates
                if math.isclose(
                    item.removed_depth_distance,
                    nearest_distance,
                    rel_tol=0.0,
                    abs_tol=1.0e-12,
                )
            ]
            adjusted_nearest: list[ResolvedCoverageCandidate] = []
            for candidate in nearest:
                adjustment = 0.0
                if prototype_score_adjustment is not None:
                    try:
                        adjustment = float(
                            prototype_score_adjustment(candidate.prototype)
                        )
                    except Exception as exc:
                        _fail(
                            "prototype_score_adjustment_failed:"
                            f"{candidate.corridor_id}:{exc}"
                        )
                    if adjustment == -math.inf:
                        reject(
                            candidate.prototype,
                            "prototype_score_adjustment_rejected",
                        )
                        continue
                    if not math.isfinite(adjustment):
                        _fail(
                            "prototype_score_adjustment_non_finite:"
                            f"{candidate.corridor_id}"
                        )
                adjusted_nearest.append(
                    replace(
                        candidate,
                        prototype_score_adjustment=adjustment,
                        final_score=float(
                            candidate.cell_score
                            - candidate.wall_score_penalty
                            + adjustment
                        ),
                    )
                )
            if not adjusted_nearest:
                continue
            winner = min(
                adjusted_nearest,
                key=lambda item: (
                    -item.prototype_score_adjustment,
                    item.corridor_id,
                ),
            )
            for candidate in eligible_by_cell[cell_id]:
                if candidate.corridor_id != winner.corridor_id:
                    existing_reason = str(
                        trace_by_corridor[candidate.corridor_id].get(
                            "rejection_reason",
                            "",
                        )
                    )
                    if existing_reason == ("prototype_score_adjustment_rejected"):
                        continue
                    reason = (
                        "not_selected_equal_distance_a0_tie_break"
                        if any(
                            item.corridor_id == candidate.corridor_id
                            for item in nearest
                        )
                        else "not_nearest_removed_depth_in_outcome_cell"
                    )
                    trace_by_corridor[candidate.corridor_id].update(
                        status="rejected",
                        rejection_reason=reason,
                    )
            trace_by_corridor[winner.corridor_id].update(
                status="eligible_cell_k1",
                prototype_score_adjustment=(winner.prototype_score_adjustment),
                final_score=float(winner.final_score),
            )
            per_cell.append(winner)

        if not per_cell:
            raise NoCoverageExecutionCandidateError(
                rejection_reasons=rejections,
                candidate_trace_items=_freeze_candidate_trace(
                    trace_order,
                    trace_by_corridor,
                ),
            )
        selected = min(
            per_cell,
            key=lambda item: (-item.final_score, item.corridor_id),
        )
        if self.worktool_sweep_service is not None:
            final_start_qpos = current_qpos
            if (
                selected.start_reachability_evaluation is not None
                and str(selection_phase) == "post_return"
            ):
                final_start_qpos = (
                    selected.start_reachability_evaluation.paired_handoff_qpos
                )
            final_worktool_sweep = self.worktool_sweep_service.evaluate(
                exemplar_id=selected.exemplar_id,
                raw_fields_sha256=selected.raw_fields_sha256,
                live_start_qpos=final_start_qpos,
            )
            if not final_worktool_sweep.eligible:
                _fail(
                    "worktool_sweep_3d_final_guard_rejected:"
                    f"{selected.corridor_id}:"
                    f"{final_worktool_sweep.rejection_reason}"
                )
            selected = replace(
                selected,
                worktool_sweep_evaluation=final_worktool_sweep,
            )
        for candidate in per_cell:
            trace_by_corridor[candidate.corridor_id].update(
                status=(
                    "selected"
                    if candidate.corridor_id == selected.corridor_id
                    else "eligible_not_selected_cross_cell"
                ),
                rejection_reason="",
            )
        return replace(
            selected,
            candidate_trace_items=_freeze_candidate_trace(
                trace_order,
                trace_by_corridor,
            ),
        )

    def _library_parser(self) -> CoverageExecutionLibraryContractParser:
        return CoverageExecutionLibraryContractParser(
            wall_safety_config=self.wall_safety_service.config,
        )

    def _validated_live_env_state(
        self,
        env_state: Any,
        *,
        geometry_contract: tuple[int, int, int, float, float] | None,
    ) -> np.ndarray:
        try:
            env = np.asarray(env_state, dtype=np.float64).reshape(-1)
        except (TypeError, ValueError) as exc:
            _fail(f"env_state_v2_4_invalid:{exc}")
        if env.size < ENV_STATE_V2_4_DIM:
            _fail(
                f"env_state_v2_4_width:expected={ENV_STATE_V2_4_DIM},actual={env.size}"
            )
        geometry = (
            _axis_id(env[ENV_STATE_DIG_AREA_LONG_AXIS_IDX]),
            _positive_int(
                env[ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX],
                label="live_grid_long_count",
            ),
            _positive_int(
                env[ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX],
                label="live_grid_short_count",
            ),
            _finite_float(
                env[ENV_STATE_DIG_AREA_CELL_LONG_SIZE_IDX],
                label="live_cell_long_size_m",
            ),
            _finite_float(
                env[ENV_STATE_DIG_AREA_CELL_SHORT_SIZE_IDX],
                label="live_cell_short_size_m",
            ),
        )
        if geometry[1:3] != (3, 2):
            _fail("live_geometry_grid_shape")
        if geometry[3] <= 0.0 or geometry[4] <= 0.0:
            _fail("live_geometry_cell_size_non_positive")
        if geometry_contract is not None:
            if geometry[:3] != geometry_contract[:3] or not (
                math.isclose(
                    geometry[3],
                    geometry_contract[3],
                    rel_tol=0.0,
                    abs_tol=1.0e-6,
                )
                and math.isclose(
                    geometry[4],
                    geometry_contract[4],
                    rel_tol=0.0,
                    abs_tol=1.0e-6,
                )
            ):
                _fail("live_geometry_disagrees_with_library")
        return env

    def _outcome_states_by_id(
        self,
        values: Sequence[CoverageOutcomeCellState],
    ) -> dict[int, CoverageOutcomeCellState]:
        result: dict[int, CoverageOutcomeCellState] = {}
        for value in values:
            if not isinstance(value, CoverageOutcomeCellState):
                _fail("outcome_state_type")
            cell_id = int(value.effect_outcome_cell_id)
            if cell_id in result:
                _fail(f"duplicate_outcome_state:{cell_id}")
            result[cell_id] = value
        return result

    def _validated_cell_scores(
        self,
        values: Mapping[int, float],
        *,
        required_cell_ids: set[int],
    ) -> dict[int, float]:
        if not isinstance(values, Mapping):
            _fail("cell_scores_not_mapping")
        result: dict[int, float] = {}
        for raw_cell_id, raw_score in values.items():
            cell_id = _cell_id(raw_cell_id, label="cell_score_cell_id")
            result[cell_id] = _finite_float(
                raw_score,
                label=f"cell_score_{cell_id}",
            )
        missing = sorted(required_cell_ids - set(result))
        if missing:
            _fail(f"missing_cell_scores:{missing}")
        return result


def _removed_depth_distance(
    live: Sequence[float],
    reference: Sequence[float],
    *,
    scale_m: float,
    target_cell_id: int,
    target_cell_weight: float,
) -> float:
    diff = (
        np.asarray(live, dtype=np.float64).reshape(_GRID_CELL_COUNT)
        - np.asarray(reference, dtype=np.float64).reshape(_GRID_CELL_COUNT)
    ) / float(scale_m)
    diff[int(target_cell_id)] *= float(target_cell_weight)
    return float(np.sqrt(np.mean(np.square(diff))))


def _finite_env_grid(
    env: np.ndarray,
    *,
    start_index: int,
    label: str,
) -> tuple[float, ...]:
    values = tuple(
        float(value) for value in env[start_index : start_index + _GRID_CELL_COUNT]
    )
    if len(values) != _GRID_CELL_COUNT or not all(
        math.isfinite(value) for value in values
    ):
        _fail(label)
    return values


def _freeze_candidate_trace(
    trace_order: Sequence[int],
    trace_by_corridor: Mapping[int, Mapping[str, Any]],
) -> tuple[tuple[tuple[str, Any], ...], ...]:
    """Deep-freeze scalar/tuple diagnostic rows in deterministic order."""

    return tuple(
        tuple(
            (
                str(key),
                tuple(value) if isinstance(value, list) else value,
            )
            for key, value in trace_by_corridor[int(corridor_id)].items()
        )
        for corridor_id in trace_order
    )


__all__ = [
    "COVERAGE_EXECUTION_CANDIDATE_LIBRARY_SCHEMA",
    "COVERAGE_EXECUTION_CORRIDOR_ID_BASE",
    "CoverageCorridorPrototype",
    "CoverageExecutionCandidateContractError",
    "CoverageExecutionCandidateService",
    "CoverageOutcomeCellState",
    "NoCoverageExecutionCandidateError",
    "ResolvedCoverageCandidate",
]
