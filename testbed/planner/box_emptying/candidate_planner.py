"""Online 72-candidate hard-bottom box-emptying planner."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from testbed.planner.box_emptying.contracts import TerrainBoxResidual

PLANNED_EFFECT_CONTRACT_VERSION = "planned_cut_effect_v1"
DIRECTIONS = (
    "long_forward",
    "long_reverse",
    "short_forward",
    "short_reverse",
)
DEPTH_FRACTIONS = (0.5, 0.75, 1.0)


class EffectArtifactContractError(RuntimeError):
    """Raised when the planned-effect artifact is unavailable or incompatible."""


class NoValidCandidateError(RuntimeError):
    """Raised when all 72 candidates are explicitly filtered."""


@dataclass(frozen=True)
class CandidateEffectPrediction:
    signed_cell_delta_m3: tuple[float, float, float, float, float, float]
    payload_kg: float
    removed_volume_m3: float
    uncertainty_m3: float


class PlannedCutEffectPredictor(Protocol):
    contract_version: str

    def predict(
        self,
        candidate: BoxCutCandidate,
        residual: TerrainBoxResidual,
    ) -> CandidateEffectPrediction: ...


@dataclass(frozen=True)
class CandidatePlannerConfig:
    support_envelope: Mapping[str, Any]
    cell_area_m2: float = 1.25
    box_long_size_m: float = 3.0
    box_short_size_m: float = 2.5
    long_axis: int = 0
    cut_length_m: float = 0.75
    bucket_width_m: float = 0.70
    wall_inset_m: float = 0.30
    min_depth_m: float = 0.05
    max_depth_m: float = 0.60
    hard_bottom_margin_m: float = 0.02
    payload_saturation_kg: float = 60.0
    lcb_std_multiplier: float = 1.96
    blocked_cell_ids: frozenset[int] = field(default_factory=frozenset)
    blocked_corridor_ids: frozenset[str] = field(default_factory=frozenset)
    depth_exhausted_cell_ids: frozenset[int] = field(default_factory=frozenset)
    known_failure_candidate_ids: frozenset[str] = field(default_factory=frozenset)
    alignment_cost_by_cell: Mapping[int, float] = field(default_factory=dict)


@dataclass(frozen=True)
class BoxCutCandidate:
    candidate_id: str
    corridor_id: str
    cell_id: int
    row: int
    col: int
    direction: str
    depth_fraction: float
    local_remaining_depth_m: float
    planned_depth_m: float
    cut_length_m: float
    entry_x_m: float
    entry_z_m: float
    exit_x_m: float
    exit_z_m: float
    direction_x: float
    direction_z: float
    geometry_feasible: bool = True


@dataclass(frozen=True)
class ScoredEffectPrediction:
    signed_cell_delta_m3: tuple[float, float, float, float, float, float]
    payload_kg: float
    removed_volume_m3: float
    uncertainty_m3: float
    effective_volume_lcb_m3: float
    payload_bonus_kg: float


@dataclass(frozen=True)
class EvaluatedCandidate:
    candidate: BoxCutCandidate
    rejection_reason: str = ""
    prediction: ScoredEffectPrediction | None = None
    alignment_cost: float = 0.0


@dataclass(frozen=True)
class CandidateSelection:
    candidate: BoxCutCandidate
    prediction: ScoredEffectPrediction
    alignment_cost: float


@dataclass(frozen=True)
class LockedCandidateSelection:
    selection: CandidateSelection
    remaining_depth_m: tuple[float, float, float, float, float, float]
    recompute_count: int = 0


class BoxEmptyingCandidatePlanner:
    """Filter then lexicographically rank one fixed 6x4x3 candidate set."""

    def __init__(
        self,
        *,
        predictor: PlannedCutEffectPredictor | None,
        config: CandidatePlannerConfig,
    ) -> None:
        if predictor is None:
            raise EffectArtifactContractError("artifact_missing")
        if str(getattr(predictor, "contract_version", "")) != (
            PLANNED_EFFECT_CONTRACT_VERSION
        ):
            raise EffectArtifactContractError("contract_mismatch")
        if float(config.cell_area_m2) <= 0.0:
            raise ValueError("cell_area_m2 must be positive")
        self.predictor = predictor
        self.config = config

    def generate_candidates(
        self,
        residual: TerrainBoxResidual,
    ) -> list[BoxCutCandidate]:
        depths = self._remaining_depths(residual)
        candidates: list[BoxCutCandidate] = []
        for cell_id, local_depth in enumerate(depths):
            row, col = divmod(cell_id, 2)
            long_center = (row - 1) * (
                float(self.config.box_long_size_m) / 3.0
            )
            short_center = (col - 0.5) * (
                float(self.config.box_short_size_m) / 2.0
            )
            max_safe_depth = min(
                float(self.config.max_depth_m),
                max(0.0, local_depth - float(self.config.hard_bottom_margin_m)),
            )
            for direction in DIRECTIONS:
                corridor_id = f"cell{cell_id}:{direction}"
                unit_long, unit_short = {
                    "long_forward": (1.0, 0.0),
                    "long_reverse": (-1.0, 0.0),
                    "short_forward": (0.0, 1.0),
                    "short_reverse": (0.0, -1.0),
                }[direction]
                for fraction in DEPTH_FRACTIONS:
                    planned_depth = max(
                        float(self.config.min_depth_m),
                        min(local_depth * fraction, max_safe_depth),
                    )
                    cut_length = float(self.config.cut_length_m)
                    if planned_depth > cut_length + 1.0e-12:
                        raise EffectArtifactContractError(
                            "planned_depth_exceeds_cut_length"
                        )
                    horizontal_reach = math.sqrt(
                        max(0.0, cut_length**2 - planned_depth**2)
                    )
                    delta_long = unit_long * horizontal_reach
                    delta_short = unit_short * horizontal_reach
                    (
                        entry_long,
                        entry_short,
                        exit_long,
                        exit_short,
                        geometry_feasible,
                    ) = self._supported_cell_geometry(
                        row=row,
                        col=col,
                        long_center=long_center,
                        short_center=short_center,
                        delta_long=delta_long,
                        delta_short=delta_short,
                    )
                    entry_x, entry_z = self._long_short_to_xz(
                        entry_long,
                        entry_short,
                    )
                    exit_x, exit_z = self._long_short_to_xz(
                        exit_long,
                        exit_short,
                    )
                    direction_x, direction_z = self._long_short_to_xz(
                        delta_long / cut_length,
                        delta_short / cut_length,
                    )
                    candidates.append(
                        BoxCutCandidate(
                            candidate_id=(
                                f"{corridor_id}:depth{_fraction_label(fraction)}"
                            ),
                            corridor_id=corridor_id,
                            cell_id=cell_id,
                            row=row,
                            col=col,
                            direction=direction,
                            depth_fraction=fraction,
                            local_remaining_depth_m=local_depth,
                            planned_depth_m=planned_depth,
                            cut_length_m=cut_length,
                            entry_x_m=entry_x,
                            entry_z_m=entry_z,
                            exit_x_m=exit_x,
                            exit_z_m=exit_z,
                            direction_x=direction_x,
                            direction_z=direction_z,
                            geometry_feasible=geometry_feasible,
                        )
                    )
        return candidates

    def evaluate_candidates(
        self,
        residual: TerrainBoxResidual,
    ) -> list[EvaluatedCandidate]:
        evaluated: list[EvaluatedCandidate] = []
        for candidate in self.generate_candidates(residual):
            rejection = self._rejection_reason(candidate)
            if rejection:
                evaluated.append(
                    EvaluatedCandidate(
                        candidate=candidate,
                        rejection_reason=rejection,
                    )
                )
                continue
            raw_prediction = self.predictor.predict(candidate, residual)
            prediction = self._score_prediction(raw_prediction)
            evaluated.append(
                EvaluatedCandidate(
                    candidate=candidate,
                    prediction=prediction,
                    alignment_cost=float(
                        self.config.alignment_cost_by_cell.get(
                            int(candidate.cell_id),
                            0.0,
                        )
                    ),
                )
            )
        return evaluated

    def select(self, residual: TerrainBoxResidual) -> CandidateSelection:
        accepted = [
            item
            for item in self.evaluate_candidates(residual)
            if not item.rejection_reason and item.prediction is not None
        ]
        if not accepted:
            raise NoValidCandidateError("no_valid_box_emptying_candidate")
        selected = max(
            accepted,
            key=lambda item: (
                item.prediction.effective_volume_lcb_m3,
                item.prediction.payload_bonus_kg,
                -item.prediction.uncertainty_m3,
                -item.alignment_cost,
                item.candidate.candidate_id,
            ),
        )
        prediction = selected.prediction
        if prediction is None:  # pragma: no cover - filtered above
            raise RuntimeError("selected candidate lacks prediction")
        return CandidateSelection(
            candidate=selected.candidate,
            prediction=prediction,
            alignment_cost=selected.alignment_cost,
        )

    def lock_selection(
        self,
        residual: TerrainBoxResidual,
    ) -> LockedCandidateSelection:
        return LockedCandidateSelection(
            selection=self.select(residual),
            remaining_depth_m=self._remaining_depths(residual),
        )

    def validate_locked_selection(
        self,
        locked: LockedCandidateSelection,
        residual: TerrainBoxResidual,
    ) -> LockedCandidateSelection:
        current_depths = self._remaining_depths(residual)
        max_change = max(
            abs(current - previous)
            for current, previous in zip(
                current_depths,
                locked.remaining_depth_m,
                strict=True,
            )
        )
        if max_change <= 0.002:
            return locked
        if int(locked.recompute_count) >= 1:
            raise RuntimeError("locked_plan_changed_more_than_once")
        return LockedCandidateSelection(
            selection=self.select(residual),
            remaining_depth_m=current_depths,
            recompute_count=1,
        )

    def _remaining_depths(
        self,
        residual: TerrainBoxResidual,
    ) -> tuple[float, float, float, float, float, float]:
        return tuple(
            float(volume) / float(self.config.cell_area_m2)
            for volume in residual.remaining_volume_m3
        )  # type: ignore[return-value]

    def _rejection_reason(self, candidate: BoxCutCandidate) -> str:
        config = self.config
        if candidate.cell_id in config.blocked_cell_ids:
            return "blocked_cell"
        if candidate.cell_id in config.depth_exhausted_cell_ids:
            return "depth_exhausted_cell"
        if candidate.corridor_id in config.blocked_corridor_ids:
            return "blocked_corridor"
        if candidate.candidate_id in config.known_failure_candidate_ids:
            return "known_failure"
        if not candidate.geometry_feasible:
            return "unsupported_cell_geometry"
        if (
            candidate.local_remaining_depth_m
            - float(config.hard_bottom_margin_m)
            < float(config.min_depth_m)
        ):
            return "hard_bottom_budget_exhausted"
        if not self._inside_support_envelope(candidate):
            return "outside_support_envelope"
        if not self._wall_footprint_safe(candidate):
            return "wall_footprint"
        return ""

    def _inside_support_envelope(self, candidate: BoxCutCandidate) -> bool:
        envelope = self.config.support_envelope
        values = (
            ("planned_depth_m", candidate.planned_depth_m),
            ("cut_length_m", candidate.cut_length_m),
            ("entry_x_m", candidate.entry_x_m),
            ("entry_z_m", candidate.entry_z_m),
            ("exit_x_m", candidate.exit_x_m),
            ("exit_z_m", candidate.exit_z_m),
            ("direction_x", candidate.direction_x),
            ("direction_z", candidate.direction_z),
        )
        required = {"planned_depth_m", "cut_length_m"}
        for field_name, value in values:
            bounds = envelope.get(field_name)
            if bounds is None and field_name not in required:
                continue
            if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
                raise EffectArtifactContractError(
                    f"support_envelope_missing:{field_name}"
                )
            low, high = float(bounds[0]), float(bounds[1])
            if not (math.isfinite(low) and math.isfinite(high) and low <= high):
                raise EffectArtifactContractError(
                    f"support_envelope_invalid:{field_name}"
                )
            if value < low - 1.0e-12 or value > high + 1.0e-12:
                return False
        return True

    def _supported_cell_geometry(
        self,
        *,
        row: int,
        col: int,
        long_center: float,
        short_center: float,
        delta_long: float,
        delta_short: float,
    ) -> tuple[float, float, float, float, bool]:
        """Fit a supported swept segment that intersects the requested cell."""

        half_long = float(self.config.box_long_size_m) / 2.0
        half_short = float(self.config.box_short_size_m) / 2.0
        cell_long = 2.0 * half_long / 3.0
        cell_short = 2.0 * half_short / 2.0
        long_cell_bounds = (
            -half_long + row * cell_long,
            -half_long + (row + 1) * cell_long,
        )
        short_cell_bounds = (
            -half_short + col * cell_short,
            -half_short + (col + 1) * cell_short,
        )
        long_limit = half_long - float(self.config.wall_inset_m)
        short_limit = half_short - float(self.config.wall_inset_m)
        half_width = float(self.config.bucket_width_m) / 2.0

        if abs(delta_long) > 1.0e-12:
            motion = self._motion_entry_interval(
                local_axis="long",
                delta=delta_long,
                cell_bounds=long_cell_bounds,
                wall_limit=long_limit,
            )
            perpendicular = self._perpendicular_interval(
                local_axis="short",
                cell_bounds=short_cell_bounds,
                wall_limit=short_limit,
                half_width=half_width,
            )
            default_entry = (
                long_center - delta_long
                if long_center * delta_long > 0.0
                else long_center
            )
            if motion is not None and perpendicular is not None:
                entry_long = _clamp(default_entry, *motion)
                entry_short = _clamp(short_center, *perpendicular)
                return (
                    entry_long,
                    entry_short,
                    entry_long + delta_long,
                    entry_short,
                    True,
                )
        elif abs(delta_short) > 1.0e-12:
            motion = self._motion_entry_interval(
                local_axis="short",
                delta=delta_short,
                cell_bounds=short_cell_bounds,
                wall_limit=short_limit,
            )
            perpendicular = self._perpendicular_interval(
                local_axis="long",
                cell_bounds=long_cell_bounds,
                wall_limit=long_limit,
                half_width=half_width,
            )
            default_entry = (
                short_center - delta_short
                if short_center * delta_short > 0.0
                else short_center
            )
            if motion is not None and perpendicular is not None:
                entry_short = _clamp(default_entry, *motion)
                entry_long = _clamp(long_center, *perpendicular)
                return (
                    entry_long,
                    entry_short,
                    entry_long,
                    entry_short + delta_short,
                    True,
                )

        points_outward = (
            long_center * delta_long + short_center * delta_short > 0.0
        )
        if points_outward:
            entry_long = long_center - delta_long
            entry_short = short_center - delta_short
            exit_long = long_center
            exit_short = short_center
        else:
            entry_long = long_center
            entry_short = short_center
            exit_long = long_center + delta_long
            exit_short = short_center + delta_short
        return entry_long, entry_short, exit_long, exit_short, False

    def _motion_entry_interval(
        self,
        *,
        local_axis: str,
        delta: float,
        cell_bounds: tuple[float, float],
        wall_limit: float,
    ) -> tuple[float, float] | None:
        entry_support = self._coordinate_support("entry", local_axis)
        exit_support = self._coordinate_support("exit", local_axis)
        cell_low, cell_high = cell_bounds
        low = max(
            entry_support[0],
            exit_support[0] - delta,
            -wall_limit,
            -wall_limit - delta,
            cell_low - max(0.0, delta),
        )
        high = min(
            entry_support[1],
            exit_support[1] - delta,
            wall_limit,
            wall_limit - delta,
            cell_high - min(0.0, delta),
        )
        return None if low > high + 1.0e-12 else (low, high)

    def _perpendicular_interval(
        self,
        *,
        local_axis: str,
        cell_bounds: tuple[float, float],
        wall_limit: float,
        half_width: float,
    ) -> tuple[float, float] | None:
        entry_support = self._coordinate_support("entry", local_axis)
        exit_support = self._coordinate_support("exit", local_axis)
        cell_low, cell_high = cell_bounds
        low = max(
            entry_support[0],
            exit_support[0],
            -wall_limit + half_width,
            cell_low,
        )
        high = min(
            entry_support[1],
            exit_support[1],
            wall_limit - half_width,
            cell_high,
        )
        return None if low > high + 1.0e-12 else (low, high)

    def _coordinate_support(
        self,
        endpoint: str,
        local_axis: str,
    ) -> tuple[float, float]:
        long_axis = int(self.config.long_axis)
        if local_axis == "long":
            coordinate = "x" if long_axis == 0 else "z"
        elif local_axis == "short":
            coordinate = "z" if long_axis == 0 else "x"
        else:  # pragma: no cover - internal call contract
            raise ValueError(f"unknown local axis {local_axis!r}")
        bounds = self.config.support_envelope.get(
            f"{endpoint}_{coordinate}_m"
        )
        if bounds is None:
            return -math.inf, math.inf
        if not isinstance(bounds, (list, tuple)) or len(bounds) != 2:
            raise EffectArtifactContractError(
                f"support_envelope_missing:{endpoint}_{coordinate}_m"
            )
        low, high = float(bounds[0]), float(bounds[1])
        if not (math.isfinite(low) and math.isfinite(high) and low <= high):
            raise EffectArtifactContractError(
                f"support_envelope_invalid:{endpoint}_{coordinate}_m"
            )
        return low, high

    def _long_short_to_xz(
        self,
        long_value: float,
        short_value: float,
    ) -> tuple[float, float]:
        long_axis = int(self.config.long_axis)
        if long_axis == 0:
            return float(long_value), float(short_value)
        if long_axis == 2:
            return float(short_value), float(long_value)
        raise EffectArtifactContractError(
            f"unsupported_dig_area_long_axis:{long_axis}"
        )

    def _wall_footprint_safe(self, candidate: BoxCutCandidate) -> bool:
        config = self.config
        if int(config.long_axis) == 0:
            long_center, short_center = candidate.entry_x_m, candidate.entry_z_m
            end_long, end_short = candidate.exit_x_m, candidate.exit_z_m
        elif int(config.long_axis) == 2:
            long_center, short_center = candidate.entry_z_m, candidate.entry_x_m
            end_long, end_short = candidate.exit_z_m, candidate.exit_x_m
        else:
            raise EffectArtifactContractError(
                f"unsupported_dig_area_long_axis:{config.long_axis}"
            )
        half_width = float(config.bucket_width_m) / 2.0
        long_limit = float(config.box_long_size_m) / 2.0 - float(
            config.wall_inset_m
        )
        short_limit = float(config.box_short_size_m) / 2.0 - float(
            config.wall_inset_m
        )
        if candidate.direction.startswith("long"):
            return bool(
                max(abs(long_center), abs(end_long)) <= long_limit + 1.0e-12
                and abs(short_center) + half_width <= short_limit + 1.0e-12
            )
        return bool(
            max(abs(short_center), abs(end_short)) <= short_limit + 1.0e-12
            and abs(long_center) + half_width <= long_limit + 1.0e-12
        )

    def _score_prediction(
        self,
        prediction: CandidateEffectPrediction,
    ) -> ScoredEffectPrediction:
        values = (
            *prediction.signed_cell_delta_m3,
            prediction.payload_kg,
            prediction.removed_volume_m3,
            prediction.uncertainty_m3,
        )
        if len(prediction.signed_cell_delta_m3) != 6 or not all(
            math.isfinite(float(value)) for value in values
        ):
            raise EffectArtifactContractError("prediction_nonfinite_or_wrong_shape")
        if prediction.uncertainty_m3 < 0.0:
            raise EffectArtifactContractError("prediction_negative_uncertainty")
        lcb = max(
            0.0,
            float(prediction.removed_volume_m3)
            - float(self.config.lcb_std_multiplier)
            * float(prediction.uncertainty_m3),
        )
        return ScoredEffectPrediction(
            signed_cell_delta_m3=tuple(
                float(value) for value in prediction.signed_cell_delta_m3
            ),  # type: ignore[arg-type]
            payload_kg=float(prediction.payload_kg),
            removed_volume_m3=float(prediction.removed_volume_m3),
            uncertainty_m3=float(prediction.uncertainty_m3),
            effective_volume_lcb_m3=lcb,
            payload_bonus_kg=min(
                max(0.0, float(prediction.payload_kg)),
                float(self.config.payload_saturation_kg),
            ),
        )


def _fraction_label(value: float) -> str:
    if math.isclose(value, round(value)):
        return str(int(round(value)))
    return f"{value:g}"


def _clamp(value: float, low: float, high: float) -> float:
    return min(max(float(value), float(low)), float(high))


__all__ = [
    "BoxCutCandidate",
    "BoxEmptyingCandidatePlanner",
    "CandidateEffectPrediction",
    "CandidatePlannerConfig",
    "CandidateSelection",
    "EffectArtifactContractError",
    "EvaluatedCandidate",
    "LockedCandidateSelection",
    "NoValidCandidateError",
    "PLANNED_EFFECT_CONTRACT_VERSION",
    "PlannedCutEffectPredictor",
    "ScoredEffectPrediction",
]
