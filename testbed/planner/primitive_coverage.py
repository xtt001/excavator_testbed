"""Coverage candidate construction for primitive planner dig corridors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.planner.primitive_tokens import DigCutTokenPlanner


@dataclass
class CoverageCorridorState:
    corridor_id: int
    entry_x_m: float
    entry_z_m: float
    exit_x_m: float
    exit_z_m: float
    cell_id: int = -1
    source_count: int = 0
    source_fraction: float = 0.0
    entry_x_p05_m: float = float("nan")
    entry_x_p50_m: float = float("nan")
    entry_x_p95_m: float = float("nan")
    entry_z_p05_m: float = float("nan")
    entry_z_p50_m: float = float("nan")
    entry_z_p95_m: float = float("nan")
    entry_radial_p75_m: float = float("nan")
    entry_radial_p95_m: float = float("nan")
    exit_x_p05_m: float = float("nan")
    exit_x_p50_m: float = float("nan")
    exit_x_p95_m: float = float("nan")
    exit_z_p05_m: float = float("nan")
    exit_z_p50_m: float = float("nan")
    exit_z_p95_m: float = float("nan")
    exit_radial_p75_m: float = float("nan")
    exit_radial_p95_m: float = float("nan")
    cut_depth_peak_p05_m: float = float("nan")
    cut_depth_peak_p50_m: float = float("nan")
    cut_depth_peak_p95_m: float = float("nan")
    cut_depth_peak_m: float = float("nan")
    payload_gain_kg: float = float("nan")
    effective_deposit_delta_kg: float = float("nan")
    score: float = 0.0
    attempts: int = 0
    low_productivity_streak: int = 0
    depleted: bool = False
    belief_coverage: float = 0.0
    last_payload_gain_kg: float = 0.0
    last_effective_deposit_delta_kg: float = 0.0
    last_remaining_depth_m: float = float("nan")
    last_reason: str = ""
    state_exemplar_id: str = ""
    state_exemplar_distance: float = float("nan")


@dataclass(frozen=True)
class CoverageSelectionConfig:
    candidate_layout: str
    prior_fields: dict[str, Any]
    cut_depth_percentile: str
    use_env_removed_depth: bool
    max_attempts_per_corridor: int
    recent_selection_penalty: float
    unattempted_bonus: float
    attempt_penalty: float
    cell_confidence_weight: float
    rare_cell_source_fraction_threshold: float
    rare_cell_max_attempts: int
    recent_row_selection_penalty: float
    last_selected_corridor_id: int
    cycle_index: int
    completed_dump_count: int
    first_dig_strategy: str
    first_dig_preferred_corridor_id: int | None
    first_dig_preferred_bonus: float
    first_dig_proximity_weight: float
    first_dig_max_entry_distance_m: float | None
    first_dig_qpos_delta_weight: float
    first_dig_max_qpos_delta: np.ndarray | None
    pre_dig_align_controlled_dims: np.ndarray
    state_exemplars_enabled: bool
    state_exemplar_score_weight: float


@dataclass(frozen=True)
class CoverageCandidateSelectionFacts:
    remaining_depth_m: float
    first_dig_entry_distance_m: float
    first_dig_qpos_delta: np.ndarray
    state_exemplar_distance: float = float("nan")
    state_exemplar_id: str = ""


@dataclass(frozen=True)
class CoverageSelectionResult:
    selected: CoverageCorridorState
    selected_score: float
    candidate_scores: list[dict[str, Any]]
    first_dig_gate_available: int


class CoverageSelectionService:
    """Score and select a coverage corridor from explicit planner facts."""

    def __init__(self, config: CoverageSelectionConfig) -> None:
        self.config = config
        self._controlled_dims = np.asarray(
            config.pre_dig_align_controlled_dims,
            dtype=bool,
        ).reshape(-1)
        self._max_qpos_delta = (
            None
            if config.first_dig_max_qpos_delta is None
            else np.asarray(config.first_dig_max_qpos_delta, dtype=np.float32).reshape(
                self._controlled_dims.shape
            )
        )

    def select(
        self,
        corridors: list[CoverageCorridorState],
        *,
        facts_by_corridor_id: dict[int, CoverageCandidateSelectionFacts],
        recent_row_reference: CoverageCorridorState | None,
    ) -> CoverageSelectionResult:
        best: CoverageCorridorState | None = None
        best_score = -float("inf")
        candidate_scores: list[dict[str, Any]] = []
        first_dig_gate_available = self.first_dig_gate_available(
            corridors,
            facts_by_corridor_id=facts_by_corridor_id,
        )

        for corridor in corridors:
            facts = facts_by_corridor_id[int(corridor.corridor_id)]
            remaining_depth = float(facts.remaining_depth_m)
            first_dig_bonus = self.first_dig_bonus(corridor, facts)
            first_dig_distance = float(facts.first_dig_entry_distance_m)
            first_dig_entry_reachable = self.first_dig_entry_reachable(
                first_dig_distance
            )
            first_dig_qpos_delta = self.qpos_delta(facts)
            first_dig_qpos_reachable = self.first_dig_qpos_reachable(
                first_dig_qpos_delta
            )
            first_dig_qpos_penalty = self.first_dig_qpos_delta_penalty(
                first_dig_qpos_delta
            )
            first_dig_reachable = bool(
                first_dig_entry_reachable and first_dig_qpos_reachable
            )
            first_dig_gated_out = bool(
                first_dig_gate_available and not first_dig_reachable
            )
            rare_first_dig_gated_out = self.rare_first_dig_gated_out(
                corridor,
                corridors,
            )
            state_exemplar_distance = float(facts.state_exemplar_distance)
            score = (
                self.score(
                    corridor,
                    remaining_depth,
                    state_exemplar_distance=state_exemplar_distance,
                    recent_row_reference=recent_row_reference,
                )
                + first_dig_bonus
            )
            if first_dig_gated_out or rare_first_dig_gated_out:
                score = -1.0e12 + float(score)
            corridor.score = float(score)
            corridor.last_remaining_depth_m = float(remaining_depth)

            recent_row_reference_id = (
                -1
                if recent_row_reference is None
                else int(recent_row_reference.corridor_id)
            )
            recent_row_reference_cell_id = (
                -1
                if recent_row_reference is None
                else int(self.cell_id(recent_row_reference))
            )
            recent_row_reference_row_id = (
                -1
                if recent_row_reference is None
                else int(self.corridor_row_id(recent_row_reference))
            )
            row_id = int(self.corridor_row_id(corridor))
            same_recent_row = bool(
                recent_row_reference is not None
                and int(recent_row_reference.corridor_id) != int(corridor.corridor_id)
                and row_id == recent_row_reference_row_id
            )
            candidate_scores.append(
                {
                    "corridor_id": int(corridor.corridor_id),
                    "cell_id": int(self.cell_id(corridor)),
                    "row_id": int(row_id),
                    "score": float(score),
                    "attempts": int(corridor.attempts),
                    "attempt_limit": int(self.corridor_attempt_limit(corridor)),
                    "depleted": int(corridor.depleted),
                    "source_count": int(corridor.source_count),
                    "source_fraction": float(corridor.source_fraction),
                    "cell_confidence": float(self.cell_confidence(corridor)),
                    "state_exemplar_distance": float(state_exemplar_distance),
                    "state_exemplar_id": str(facts.state_exemplar_id),
                    "belief_coverage": float(corridor.belief_coverage),
                    "remaining_depth_m": float(remaining_depth),
                    "first_dig_bonus": float(first_dig_bonus),
                    "recent_row_penalty": float(
                        self.recent_row_penalty(
                            corridor,
                            recent_row_reference=recent_row_reference,
                        )
                    ),
                    "recent_row_reference_corridor_id": int(
                        recent_row_reference_id
                    ),
                    "recent_row_reference_cell_id": int(
                        recent_row_reference_cell_id
                    ),
                    "recent_row_reference_row_id": int(
                        recent_row_reference_row_id
                    ),
                    "same_recent_row": int(same_recent_row),
                    "first_dig_entry_distance_m": float(first_dig_distance),
                    "first_dig_entry_reachable": int(first_dig_entry_reachable),
                    "first_dig_qpos_delta_norm": float(first_dig_qpos_penalty),
                    "first_dig_qpos_reachable": int(first_dig_qpos_reachable),
                    "first_dig_qpos_delta": first_dig_qpos_delta.astype(float).tolist(),
                    "first_dig_max_qpos_delta": (
                        []
                        if self._max_qpos_delta is None
                        else self._max_qpos_delta.astype(float).tolist()
                    ),
                    "first_dig_reachable": int(first_dig_reachable),
                    "first_dig_gate_applied": int(first_dig_gate_available),
                    "first_dig_gated_out": int(first_dig_gated_out),
                    "rare_first_dig_gated_out": int(rare_first_dig_gated_out),
                    "first_dig_max_entry_distance_m": float(
                        np.nan
                        if self.config.first_dig_max_entry_distance_m is None
                        else self.config.first_dig_max_entry_distance_m
                    ),
                    "low_productivity_streak": int(corridor.low_productivity_streak),
                }
            )
            if first_dig_gated_out or rare_first_dig_gated_out:
                continue
            if score > best_score:
                best = corridor
                best_score = float(score)

        if best is None:
            raise ValueError("operator_prior_coverage has no selectable corridors.")
        return CoverageSelectionResult(
            selected=best,
            selected_score=float(best_score),
            candidate_scores=candidate_scores,
            first_dig_gate_available=int(first_dig_gate_available),
        )

    def score(
        self,
        corridor: CoverageCorridorState,
        remaining_depth_m: float,
        *,
        state_exemplar_distance: float = float("nan"),
        recent_row_reference: CoverageCorridorState | None,
    ) -> float:
        if corridor.depleted:
            return -1.0e9 - float(corridor.attempts)
        if corridor.attempts >= self.corridor_attempt_limit(corridor):
            return -1.0e8 - float(corridor.attempts)
        fields = dict(self.config.prior_fields)
        target_depth = (
            float(corridor.cut_depth_peak_m)
            if np.isfinite(corridor.cut_depth_peak_m)
            else self.prior_percentile(
                fields,
                "cut_depth_peak_m",
                self.config.cut_depth_percentile,
            )
        )
        if self.config.use_env_removed_depth:
            remaining_ratio = (
                1.0
                if not np.isfinite(remaining_depth_m) or target_depth <= 1.0e-6
                else float(np.clip(remaining_depth_m / target_depth, 0.0, 1.5))
            )
        else:
            remaining_ratio = float(
                np.clip(1.0 - float(corridor.belief_coverage), 0.0, 1.5)
            )
        deposit_p50 = max(
            self.prior_percentile(fields, "effective_deposit_delta_kg", "p50"),
            1.0,
        )
        productivity = (
            1.0
            if corridor.attempts <= 0
            else float(
                np.clip(
                    corridor.last_effective_deposit_delta_kg / deposit_p50,
                    0.0,
                    1.5,
                )
            )
        )
        repeat_penalty = (
            self.config.recent_selection_penalty
            if int(corridor.corridor_id)
            == int(self.config.last_selected_corridor_id)
            else 0.0
        )
        row_penalty = self.recent_row_penalty(
            corridor,
            recent_row_reference=recent_row_reference,
        )
        unattempted_bonus = (
            self.config.unattempted_bonus if corridor.attempts <= 0 else 0.0
        )
        attempt_penalty = self.config.attempt_penalty * float(corridor.attempts)
        cell_confidence = self.cell_confidence(corridor)
        state_exemplar_penalty = 0.0
        if self.config.state_exemplars_enabled and np.isfinite(
            state_exemplar_distance
        ):
            state_exemplar_penalty = (
                self.config.state_exemplar_score_weight
                * float(state_exemplar_distance)
            )
        return (
            2.0 * remaining_ratio
            + productivity
            + self.config.cell_confidence_weight * cell_confidence
            + unattempted_bonus
            - repeat_penalty
            - row_penalty
            - attempt_penalty
            - state_exemplar_penalty
            - 0.5 * float(corridor.low_productivity_streak)
        )

    def first_dig_gate_available(
        self,
        corridors: list[CoverageCorridorState],
        *,
        facts_by_corridor_id: dict[int, CoverageCandidateSelectionFacts],
    ) -> bool:
        if not self.first_dig_active():
            return False
        if (
            self.config.first_dig_max_entry_distance_m is None
            and self._max_qpos_delta is None
        ):
            return False
        for corridor in corridors:
            if corridor.depleted:
                continue
            if corridor.attempts >= self.corridor_attempt_limit(corridor):
                continue
            if self.rare_first_dig_gated_out(corridor, corridors):
                continue
            facts = facts_by_corridor_id[int(corridor.corridor_id)]
            if self.first_dig_entry_reachable(
                float(facts.first_dig_entry_distance_m)
            ) and self.first_dig_qpos_reachable(self.qpos_delta(facts)):
                return True
        return False

    def first_dig_active(self) -> bool:
        return bool(
            int(self.config.cycle_index) == 0
            and int(self.config.completed_dump_count) <= 0
            and self.config.first_dig_strategy
            not in {"", "none", "coverage_score"}
        )

    def first_dig_bonus(
        self,
        corridor: CoverageCorridorState,
        facts: CoverageCandidateSelectionFacts,
    ) -> float:
        if self.config.first_dig_strategy in {"", "none", "coverage_score"}:
            return 0.0
        if int(self.config.cycle_index) != 0 or int(
            self.config.completed_dump_count
        ) > 0:
            return 0.0
        if corridor.depleted or corridor.attempts > 0:
            return 0.0
        if self.config.first_dig_strategy in {
            "nearest_entry",
            "bootstrap_nearest_entry",
        }:
            distance = float(facts.first_dig_entry_distance_m)
            if not np.isfinite(distance):
                return 0.0
            qpos_penalty = self.first_dig_qpos_delta_penalty(
                self.qpos_delta(facts)
            )
            return (
                -float(self.config.first_dig_proximity_weight) * float(distance)
                - float(self.config.first_dig_qpos_delta_weight) * qpos_penalty
            )
        if self.config.first_dig_strategy not in {
            "preferred_corridor",
            "bootstrap_friendly",
        }:
            return 0.0
        preferred_id = self.config.first_dig_preferred_corridor_id
        if preferred_id is None:
            return 0.0
        if int(corridor.corridor_id) != int(preferred_id):
            return 0.0
        return float(self.config.first_dig_preferred_bonus)

    def first_dig_entry_reachable(self, distance: float) -> bool:
        if not self.first_dig_active():
            return True
        if self.config.first_dig_max_entry_distance_m is None:
            return True
        return bool(
            np.isfinite(distance)
            and float(distance) <= float(self.config.first_dig_max_entry_distance_m)
        )

    def first_dig_qpos_reachable(self, delta: np.ndarray) -> bool:
        if not self.first_dig_active():
            return True
        if self._max_qpos_delta is None:
            return True
        controlled = self._controlled_dims
        if not np.any(controlled):
            return True
        delta = np.asarray(delta, dtype=np.float32).reshape(controlled.shape)
        return bool(
            np.all(delta[controlled] <= self._max_qpos_delta[controlled] + 1.0e-6)
        )

    def first_dig_qpos_delta_penalty(self, delta: np.ndarray) -> float:
        if not self.first_dig_active():
            return 0.0
        controlled = self._controlled_dims
        if not np.any(controlled):
            return 0.0
        delta = np.asarray(delta, dtype=np.float32).reshape(controlled.shape)
        delta = delta[controlled]
        if self._max_qpos_delta is not None:
            scale = np.maximum(self._max_qpos_delta[controlled], 1.0e-6)
            delta = delta / scale
        return float(np.linalg.norm(delta))

    def recent_row_penalty(
        self,
        corridor: CoverageCorridorState,
        *,
        recent_row_reference: CoverageCorridorState | None,
    ) -> float:
        if self.config.recent_row_selection_penalty <= 0.0:
            return 0.0
        if recent_row_reference is None:
            return 0.0
        if int(recent_row_reference.corridor_id) == int(corridor.corridor_id):
            return 0.0
        same_row = bool(
            self.corridor_row_id(recent_row_reference)
            == self.corridor_row_id(corridor)
        )
        return float(self.config.recent_row_selection_penalty if same_row else 0.0)

    def cell_confidence(self, corridor: CoverageCorridorState) -> float:
        if self.config.candidate_layout != "cell_weighted_3x2":
            return 0.0
        fraction = float(corridor.source_fraction)
        if not np.isfinite(fraction) or fraction <= 0.0:
            return 0.0
        uniform_fraction = 1.0 / 6.0
        return float(np.clip(fraction / uniform_fraction, 0.0, 1.5))

    def corridor_is_rare(self, corridor: CoverageCorridorState) -> bool:
        if self.config.candidate_layout != "cell_weighted_3x2":
            return False
        fraction = float(corridor.source_fraction)
        return bool(
            np.isfinite(fraction)
            and fraction > 0.0
            and fraction < self.config.rare_cell_source_fraction_threshold
        )

    def corridor_attempt_limit(self, corridor: CoverageCorridorState) -> int:
        limit = int(self.config.max_attempts_per_corridor)
        if self.corridor_is_rare(corridor):
            limit = min(limit, int(self.config.rare_cell_max_attempts))
        return max(1, int(limit))

    def rare_first_dig_gated_out(
        self,
        corridor: CoverageCorridorState,
        corridors: list[CoverageCorridorState],
    ) -> bool:
        if not self.first_dig_active():
            return False
        if not self.corridor_is_rare(corridor):
            return False
        for candidate in corridors:
            if candidate is corridor:
                continue
            if self.corridor_is_rare(candidate):
                continue
            if candidate.depleted:
                continue
            if candidate.attempts >= self.corridor_attempt_limit(candidate):
                continue
            return True
        return False

    def qpos_delta(self, facts: CoverageCandidateSelectionFacts) -> np.ndarray:
        return np.asarray(facts.first_dig_qpos_delta, dtype=np.float32).reshape(
            self._controlled_dims.shape
        )

    @staticmethod
    def cell_id(corridor: CoverageCorridorState) -> int:
        if corridor.cell_id >= 0:
            return max(0, min(5, int(corridor.cell_id)))
        corridor_id = max(0, min(5, int(corridor.corridor_id)))
        z_index = corridor_id // 2
        x_index = corridor_id % 2
        return int(z_index * 2 + x_index)

    @classmethod
    def corridor_row_id(cls, corridor: CoverageCorridorState) -> int:
        return int(cls.cell_id(corridor) // 2)

    @staticmethod
    def prior_percentile(fields: dict[str, Any], field_name: str, percentile: str) -> float:
        return DigCutTokenPlanner.prior_percentile(fields, field_name, percentile)


@dataclass(frozen=True)
class CoverageCandidateBuilder:
    """Build initial coverage corridor candidates from the dig-cut prior."""

    candidate_layout: str
    entry_x_percentiles: tuple[str, ...]
    entry_z_percentiles: tuple[str, ...]
    cut_direction_percentile: str
    cut_length_percentile: str
    cut_depth_percentile: str
    payload_percentile: str

    def build(self, prior: dict[str, Any]) -> list[CoverageCorridorState]:
        fields = dict(prior.get("fields", {}))
        if self.candidate_layout == "cell_weighted_3x2":
            return self._build_cell_weighted(prior, fields)
        candidates: list[CoverageCorridorState] = []
        corridor_id = 0
        for z_index, z_percentile in enumerate(self.entry_z_percentiles):
            for x_index, x_percentile in enumerate(self.entry_x_percentiles):
                entry_x = self._prior_percentile(fields, "entry_x_m", x_percentile)
                entry_z = self._prior_percentile(fields, "entry_z_m", z_percentile)
                exit_x, exit_z = self._exit_from_entry(fields, entry_x, entry_z)
                cell_id = self.cell_id_from_percentile_indices(
                    x_index=x_index,
                    x_count=len(self.entry_x_percentiles),
                    z_index=z_index,
                    z_count=len(self.entry_z_percentiles),
                )
                candidates.append(
                    CoverageCorridorState(
                        corridor_id=corridor_id,
                        entry_x_m=float(entry_x),
                        entry_z_m=float(entry_z),
                        exit_x_m=float(exit_x),
                        exit_z_m=float(exit_z),
                        cell_id=int(cell_id),
                        cut_depth_peak_m=self._prior_percentile(
                            fields,
                            "cut_depth_peak_m",
                            self.cut_depth_percentile,
                        ),
                        payload_gain_kg=self._prior_percentile(
                            fields,
                            "payload_gain_kg",
                            self.payload_percentile,
                        ),
                        effective_deposit_delta_kg=self._prior_percentile(
                            fields,
                            "effective_deposit_delta_kg",
                            "p50",
                        ),
                    )
                )
                corridor_id += 1
        return candidates

    def _build_cell_weighted(
        self,
        prior: dict[str, Any],
        fields: dict[str, Any],
    ) -> list[CoverageCorridorState]:
        raw_cells = prior.get("coverage_cells", [])
        if not isinstance(raw_cells, list) or not raw_cells:
            raise ValueError(
                "coverage.candidate_layout='cell_weighted_3x2' requires "
                "coverage_cells in the dig cut prior."
            )
        cells = [dict(item) for item in raw_cells if isinstance(item, dict)]
        if not cells:
            raise ValueError(
                "coverage.candidate_layout='cell_weighted_3x2' found no valid "
                "coverage_cells in the dig cut prior."
            )

        candidates: list[CoverageCorridorState] = []
        for corridor_id, cell in enumerate(
            sorted(cells, key=lambda item: int(item.get("cell_id", 999999)))
        ):
            entry = dict(cell.get("entry", {}) or {})
            exit_point = dict(cell.get("exit", {}) or {})
            entry_stats = dict(cell.get("entry_stats", {}) or {})
            exit_stats = dict(cell.get("exit_stats", {}) or {})
            depth_stats = dict(cell.get("cut_depth_peak_m_stats", {}) or {})
            entry_x = self._cell_float(
                entry,
                "x_m",
                self._prior_percentile(fields, "entry_x_m", "p50"),
            )
            entry_z = self._cell_float(
                entry,
                "z_m",
                self._prior_percentile(fields, "entry_z_m", "p50"),
            )
            if "x_m" in exit_point and "z_m" in exit_point:
                exit_x = self._cell_float(
                    exit_point,
                    "x_m",
                    self._prior_percentile(fields, "exit_x_m", "p50"),
                )
                exit_z = self._cell_float(
                    exit_point,
                    "z_m",
                    self._prior_percentile(fields, "exit_z_m", "p50"),
                )
            else:
                exit_x, exit_z = self._exit_from_entry(fields, entry_x, entry_z)
            candidates.append(
                CoverageCorridorState(
                    corridor_id=int(corridor_id),
                    entry_x_m=float(entry_x),
                    entry_z_m=float(entry_z),
                    exit_x_m=float(exit_x),
                    exit_z_m=float(exit_z),
                    cell_id=int(cell.get("cell_id", corridor_id)),
                    source_count=max(0, int(cell.get("source_count", 0))),
                    source_fraction=max(0.0, float(cell.get("source_fraction", 0.0))),
                    entry_x_p05_m=self._stat_float(entry_stats, "x_m", "p05", float(entry_x)),
                    entry_x_p50_m=self._stat_float(entry_stats, "x_m", "p50", float(entry_x)),
                    entry_x_p95_m=self._stat_float(entry_stats, "x_m", "p95", float(entry_x)),
                    entry_z_p05_m=self._stat_float(entry_stats, "z_m", "p05", float(entry_z)),
                    entry_z_p50_m=self._stat_float(entry_stats, "z_m", "p50", float(entry_z)),
                    entry_z_p95_m=self._stat_float(entry_stats, "z_m", "p95", float(entry_z)),
                    entry_radial_p75_m=self._stat_float(
                        entry_stats, "radial_error_m", "p75", float("nan")
                    ),
                    entry_radial_p95_m=self._stat_float(
                        entry_stats, "radial_error_m", "p95", float("nan")
                    ),
                    exit_x_p05_m=self._stat_float(exit_stats, "x_m", "p05", float(exit_x)),
                    exit_x_p50_m=self._stat_float(exit_stats, "x_m", "p50", float(exit_x)),
                    exit_x_p95_m=self._stat_float(exit_stats, "x_m", "p95", float(exit_x)),
                    exit_z_p05_m=self._stat_float(exit_stats, "z_m", "p05", float(exit_z)),
                    exit_z_p50_m=self._stat_float(exit_stats, "z_m", "p50", float(exit_z)),
                    exit_z_p95_m=self._stat_float(exit_stats, "z_m", "p95", float(exit_z)),
                    exit_radial_p75_m=self._stat_float(
                        exit_stats, "radial_error_m", "p75", float("nan")
                    ),
                    exit_radial_p95_m=self._stat_float(
                        exit_stats, "radial_error_m", "p95", float("nan")
                    ),
                    cut_depth_peak_p05_m=self._cell_float(
                        depth_stats,
                        "p05",
                        self._prior_percentile(fields, "cut_depth_peak_m", "p10"),
                    ),
                    cut_depth_peak_p50_m=self._cell_float(
                        depth_stats,
                        "p50",
                        self._prior_percentile(fields, "cut_depth_peak_m", "p50"),
                    ),
                    cut_depth_peak_p95_m=self._cell_float(
                        depth_stats,
                        "p95",
                        self._prior_percentile(fields, "cut_depth_peak_m", "p90"),
                    ),
                    cut_depth_peak_m=self._cell_float(
                        cell,
                        "cut_depth_peak_m",
                        self._prior_percentile(
                            fields,
                            "cut_depth_peak_m",
                            self.cut_depth_percentile,
                        ),
                    ),
                    payload_gain_kg=self._cell_float(
                        cell,
                        "payload_gain_kg",
                        self._prior_percentile(
                            fields,
                            "payload_gain_kg",
                            self.payload_percentile,
                        ),
                    ),
                    effective_deposit_delta_kg=self._cell_float(
                        cell,
                        "effective_deposit_delta_kg",
                        self._prior_percentile(
                            fields,
                            "effective_deposit_delta_kg",
                            "p50",
                        ),
                    ),
                )
            )
        return candidates

    def _exit_from_entry(
        self,
        fields: dict[str, Any],
        entry_x: float,
        entry_z: float,
    ) -> tuple[float, float]:
        dir_x = self._prior_percentile(
            fields,
            "cut_direction_x",
            self.cut_direction_percentile,
        )
        dir_z = self._prior_percentile(
            fields,
            "cut_direction_z",
            self.cut_direction_percentile,
        )
        norm = float(np.hypot(dir_x, dir_z))
        if norm <= 1.0e-6:
            dir_x, dir_z = -1.0, 0.0
        else:
            dir_x, dir_z = dir_x / norm, dir_z / norm
        length = self._prior_percentile(
            fields,
            "cut_length_m",
            self.cut_length_percentile,
        )
        return (
            self._clamp_to_prior(fields, "exit_x_m", float(entry_x) + dir_x * length),
            self._clamp_to_prior(fields, "exit_z_m", float(entry_z) + dir_z * length),
        )

    @staticmethod
    def cell_id_from_percentile_indices(
        *,
        x_index: int,
        x_count: int,
        z_index: int,
        z_count: int,
    ) -> int:
        long_index = int(round(np.interp(z_index, [0, max(1, z_count - 1)], [0, 2])))
        short_index = int(round(np.interp(x_index, [0, max(1, x_count - 1)], [0, 1])))
        return int(np.clip(long_index, 0, 2) * 2 + int(np.clip(short_index, 0, 1)))

    @staticmethod
    def _cell_float(mapping: dict[str, object], name: str, default: float) -> float:
        try:
            value = float(mapping.get(name, default))
        except (TypeError, ValueError):
            value = float(default)
        return float(value if np.isfinite(value) else default)

    @classmethod
    def _stat_float(
        cls,
        mapping: dict[str, object],
        section: str,
        name: str,
        default: float,
    ) -> float:
        section_mapping = mapping.get(section, {})
        if not isinstance(section_mapping, dict):
            return float(default)
        return cls._cell_float(section_mapping, name, default)

    @staticmethod
    def _prior_percentile(fields: dict[str, Any], field_name: str, percentile: str) -> float:
        return DigCutTokenPlanner.prior_percentile(fields, field_name, percentile)

    @staticmethod
    def _clamp_to_prior(fields: dict[str, Any], field_name: str, value: float) -> float:
        return DigCutTokenPlanner(prior={}).clamp_to_prior(fields, field_name, value)


__all__ = [
    "CoverageCandidateBuilder",
    "CoverageCandidateSelectionFacts",
    "CoverageCorridorState",
    "CoverageSelectionConfig",
    "CoverageSelectionResult",
    "CoverageSelectionService",
]
