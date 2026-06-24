"""State-conditioned coverage exemplar planning for primitive dig cuts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from testbed.data.dig_depth_profile_v2_4 import DIG_DEPTH_PROFILE_TOKEN_DIM
from testbed.data.schema import ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX
from testbed.planner.primitive.coverage.selection import (
    CoverageCorridorState,
    CoverageSelectionService,
)


@dataclass(frozen=True)
class CoverageStateExemplarPlannerConfig:
    enabled: bool
    path: str
    dig_cut_prior_path: str
    k: int
    removed_depth_scale_m: float
    target_cell_weight: float
    temperature: float
    skip_rejected: bool


@dataclass(frozen=True)
class CoverageStateExemplarPlanInputs:
    corridor: CoverageCorridorState
    env_state: np.ndarray
    exemplars_by_cell: dict[int, list[dict[str, Any]]]
    rejected_exemplar_ids: set[str]


@dataclass(frozen=True)
class CoverageStateExemplarPlanResult:
    raw_fields: dict[str, float | int]
    profile_token: np.ndarray | None
    exemplar_ids: list[str]
    distance: float


class CoverageStateExemplarPlanner:
    """Selects and merges state-conditioned exemplars from observation facts."""

    def __init__(self, config: CoverageStateExemplarPlannerConfig) -> None:
        self.config = config

    def load_exemplars(self) -> dict[int, list[dict[str, Any]]]:
        if not self.config.enabled:
            return {}
        raw_path = str(self.config.path).strip()
        if not raw_path:
            raise ValueError(
                "coverage.state_conditioned_exemplars.enabled=true requires a path."
            )
        path = Path(raw_path).expanduser()
        if not path.is_absolute() and not path.exists():
            prior_path = Path(str(self.config.dig_cut_prior_path)).expanduser()
            if not prior_path.is_absolute():
                prior_path = Path.cwd() / prior_path
            path = prior_path.parent / path
        if not path.is_absolute():
            path = Path.cwd() / path
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        raw_exemplars = payload.get("exemplars", [])
        if not isinstance(raw_exemplars, list):
            raise ValueError(
                f"coverage state exemplar file {path} must contain an exemplars list."
            )
        exemplars_by_cell: dict[int, list[dict[str, Any]]] = {
            cell_id: [] for cell_id in range(6)
        }
        for item in raw_exemplars:
            if not isinstance(item, dict):
                continue
            try:
                cell_id = int(item.get("cell_id", -1))
            except (TypeError, ValueError):
                continue
            if cell_id < 0 or cell_id > 5:
                continue
            raw_fields = item.get("raw_fields", {})
            if not isinstance(raw_fields, dict):
                continue
            exemplar = dict(item)
            exemplar["raw_fields"] = dict(raw_fields)
            exemplar["exemplar_id"] = str(
                exemplar.get(
                    "exemplar_id",
                    f"cell_{cell_id}_{len(exemplars_by_cell[cell_id])}",
                )
            )
            exemplars_by_cell[cell_id].append(exemplar)
        if not any(exemplars_by_cell.values()):
            raise ValueError(f"coverage state exemplar file {path} has no usable rows.")
        return exemplars_by_cell

    @staticmethod
    def removed_depth_grid(env_state: np.ndarray) -> np.ndarray | None:
        env = np.asarray(env_state, dtype=np.float32).reshape(-1)
        start = ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX
        end = start + 6
        if len(env) < end:
            return None
        grid = np.asarray(env[start:end], dtype=np.float32).reshape(6)
        if not np.all(np.isfinite(grid)):
            return None
        return np.maximum(grid, 0.0).astype(np.float32)

    def distance_for_grid(
        self,
        removed_grid: np.ndarray,
        exemplar: dict[str, Any],
        *,
        cell_id: int,
    ) -> float:
        exemplar_grid = np.asarray(
            exemplar.get("start_removed_depth_grid_m", []),
            dtype=np.float32,
        ).reshape(-1)
        if exemplar_grid.size < 6 or not np.all(np.isfinite(exemplar_grid[:6])):
            return float("nan")
        scale = max(1.0e-6, float(self.config.removed_depth_scale_m))
        diff = (
            np.asarray(removed_grid, dtype=np.float32).reshape(6)
            - exemplar_grid[:6].astype(np.float32)
        ) / scale
        cell_index = int(max(0, min(5, cell_id)))
        diff[cell_index] *= max(0.0, float(self.config.target_cell_weight))
        return float(np.sqrt(np.mean(np.square(diff.astype(np.float32)))))

    def weights(self, selected: list[tuple[float, dict[str, Any]]]) -> np.ndarray:
        distances = np.asarray([distance for distance, _ in selected], dtype=np.float32)
        if distances.size == 0:
            return np.zeros(0, dtype=np.float32)
        if not np.all(np.isfinite(distances)):
            return np.full(distances.shape, 1.0 / float(distances.size), dtype=np.float32)
        shifted = distances - float(np.min(distances))
        temperature = max(1.0e-6, float(self.config.temperature))
        weights = np.exp(-shifted / temperature)
        weight_sum = float(np.sum(weights))
        if not np.isfinite(weight_sum) or weight_sum <= 1.0e-8:
            return np.full(distances.shape, 1.0 / float(distances.size), dtype=np.float32)
        return (weights / weight_sum).astype(np.float32)

    def weighted_raw_fields(
        self,
        selected: list[tuple[float, dict[str, Any]]],
    ) -> dict[str, float | int]:
        weights = self.weights(selected)

        def weighted(name: str, default: float = 0.0) -> float:
            values: list[float] = []
            for _, exemplar in selected:
                raw_fields = dict(exemplar.get("raw_fields", {}) or {})
                try:
                    value = float(raw_fields.get(name, default))
                except (TypeError, ValueError):
                    value = float(default)
                values.append(value if np.isfinite(value) else float(default))
            return float(np.dot(weights, np.asarray(values, dtype=np.float32)))

        entry_x = weighted("operator_entry_x_m")
        entry_y = weighted("operator_entry_y_m")
        entry_z = weighted("operator_entry_z_m")
        exit_x = weighted("operator_exit_x_m")
        exit_y = weighted("operator_exit_y_m", default=entry_y)
        exit_z = weighted("operator_exit_z_m")
        delta_x = exit_x - entry_x
        delta_y = exit_y - entry_y
        delta_z = exit_z - entry_z
        length = float(np.sqrt(delta_x * delta_x + delta_y * delta_y + delta_z * delta_z))
        if length <= 1.0e-6:
            dir_x = weighted("operator_cut_direction_x", default=-1.0)
            dir_y = weighted("operator_cut_direction_y", default=0.0)
            dir_z = weighted("operator_cut_direction_z", default=0.0)
            length = weighted("operator_cut_length_m", default=1.0)
        else:
            dir_x = delta_x / length
            dir_y = delta_y / length
            dir_z = delta_z / length
        return {
            "operator_entry_x_m": float(entry_x),
            "operator_entry_y_m": float(entry_y),
            "operator_entry_z_m": float(entry_z),
            "operator_exit_x_m": float(exit_x),
            "operator_exit_y_m": float(exit_y),
            "operator_exit_z_m": float(exit_z),
            "operator_cut_direction_x": float(dir_x),
            "operator_cut_direction_y": float(dir_y),
            "operator_cut_direction_z": float(dir_z),
            "operator_cut_length_m": float(length),
            "operator_cut_depth_peak_m": weighted("operator_cut_depth_peak_m"),
            "operator_cut_payload_gain_kg": weighted("operator_cut_payload_gain_kg"),
            "operator_effective_deposit_delta_kg": weighted(
                "operator_effective_deposit_delta_kg",
                default=weighted("operator_cut_payload_gain_kg"),
            ),
            "operator_cut_valid": 1,
        }

    def weighted_profile_token(
        self,
        selected: list[tuple[float, dict[str, Any]]],
    ) -> np.ndarray | None:
        weights = self.weights(selected)
        tokens: list[np.ndarray] = []
        for _, exemplar in selected:
            if "dig_depth_profile_token" not in exemplar:
                return None
            token = np.asarray(
                exemplar.get("dig_depth_profile_token", []),
                dtype=np.float32,
            ).reshape(-1)
            if token.shape[0] != DIG_DEPTH_PROFILE_TOKEN_DIM:
                return None
            if not np.all(np.isfinite(token)):
                return None
            tokens.append(token)
        if not tokens:
            return None
        stacked = np.stack(tokens, axis=0)
        merged = np.sum(stacked * weights.reshape(-1, 1), axis=0)
        merged[-1] = 1.0
        return merged.astype(np.float32)

    def plan(
        self,
        inputs: CoverageStateExemplarPlanInputs,
    ) -> CoverageStateExemplarPlanResult | None:
        if not self.config.enabled:
            return None
        cell_id = CoverageSelectionService.cell_id(inputs.corridor)
        exemplars = list(inputs.exemplars_by_cell.get(cell_id, []))
        if not exemplars:
            return None
        removed_grid = self.removed_depth_grid(inputs.env_state)
        if removed_grid is None:
            return None
        scored: list[tuple[float, dict[str, Any]]] = []
        for exemplar in exemplars:
            distance = self.distance_for_grid(
                removed_grid,
                exemplar,
                cell_id=cell_id,
            )
            if np.isfinite(distance):
                scored.append((float(distance), exemplar))
        if not scored:
            return None
        scored.sort(key=lambda item: item[0])
        if self.config.skip_rejected:
            filtered = [
                item
                for item in scored
                if str(item[1].get("exemplar_id", ""))
                not in inputs.rejected_exemplar_ids
            ]
            if filtered:
                scored = filtered
        selected = scored[: max(1, int(self.config.k))]
        profile_token = self.weighted_profile_token(selected)
        exemplar_ids = [str(exemplar.get("exemplar_id", "")) for _, exemplar in selected]
        return CoverageStateExemplarPlanResult(
            raw_fields=self.weighted_raw_fields(selected),
            profile_token=profile_token,
            exemplar_ids=exemplar_ids,
            distance=float(selected[0][0]),
        )


__all__ = [
    "CoverageStateExemplarPlanInputs",
    "CoverageStateExemplarPlanResult",
    "CoverageStateExemplarPlanner",
    "CoverageStateExemplarPlannerConfig",
]
