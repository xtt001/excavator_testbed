"""Coverage state-exemplar conditioning helpers."""

from __future__ import annotations

from .models import *


class CoverageStateExemplarMixin:
    def _load_coverage_state_exemplars(self) -> dict[int, list[dict[str, Any]]]:
        return load_coverage_state_exemplars(
            enabled=self.coverage_state_exemplars_enabled,
            raw_path=self.coverage_state_exemplar_path,
            prior_path=self.dig_cut_prior_path,
        )

    def _coverage_state_conditioned_plan(
        self,
        corridor: CoverageCorridorState,
        facts: CoverageObservationFacts,
        *,
        update_state: bool,
    ) -> dict[str, object] | None:
        if not self.coverage_state_exemplars_enabled:
            return None
        cell_id = self._coverage_cell_id(corridor)
        exemplars = list(self.coverage_state_exemplars_by_cell.get(cell_id, []))
        if not exemplars:
            return None
        removed_grid = self._coverage_removed_depth_grid(facts)
        if removed_grid is None:
            return None
        scored: list[tuple[float, dict[str, Any]]] = []
        for exemplar in exemplars:
            distance = self._coverage_state_exemplar_distance_for_grid(
                removed_grid,
                exemplar,
                cell_id=cell_id,
            )
            if np.isfinite(distance):
                scored.append((float(distance), exemplar))
        if not scored:
            return None
        scored.sort(key=lambda item: item[0])
        if self.coverage_state_exemplar_skip_rejected:
            filtered = [
                item
                for item in scored
                if str(item[1].get("exemplar_id", ""))
                not in self._coverage_rejected_state_exemplar_ids
            ]
            if filtered:
                scored = filtered
        selected = scored[: self.coverage_state_exemplar_k]
        raw_fields = self._weighted_state_exemplar_raw_fields(selected)
        profile_token = self._weighted_state_exemplar_profile_token(selected)
        exemplar_ids = [
            str(exemplar.get("exemplar_id", ""))
            for _, exemplar in selected
        ]
        best_distance = float(selected[0][0])
        if update_state:
            self._coverage_active_state_exemplar_ids = exemplar_ids
            self._coverage_active_state_exemplar_distance = best_distance
            self._coverage_active_state_exemplar_profile_token = (
                None
                if profile_token is None
                else profile_token.astype(np.float32).copy()
            )
            corridor.state_exemplar_id = ",".join(exemplar_ids)
            corridor.state_exemplar_distance = best_distance
        return {
            "raw_fields": raw_fields,
            "profile_token": profile_token,
            "exemplar_ids": exemplar_ids,
            "distance": best_distance,
        }

    def _coverage_state_exemplar_distance(
        self,
        corridor: CoverageCorridorState,
        facts: CoverageObservationFacts,
    ) -> float:
        state_plan = self._coverage_state_conditioned_plan(
            corridor,
            facts,
            update_state=False,
        )
        if state_plan is None:
            return float("nan")
        return float(state_plan["distance"])

    def _coverage_state_exemplar_id(
        self,
        corridor: CoverageCorridorState,
        facts: CoverageObservationFacts,
    ) -> str:
        state_plan = self._coverage_state_conditioned_plan(
            corridor,
            facts,
            update_state=False,
        )
        if state_plan is None:
            return ""
        exemplar_ids = state_plan.get("exemplar_ids", [])
        if not exemplar_ids:
            return ""
        return str(exemplar_ids[0])

    def _coverage_removed_depth_grid(
        self,
        facts: CoverageObservationFacts,
    ) -> np.ndarray | None:
        env_state = self._env_state(facts)
        start = ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX
        end = start + 6
        if len(env_state) < end:
            return None
        grid = np.asarray(env_state[start:end], dtype=np.float32).reshape(6)
        if not np.all(np.isfinite(grid)):
            return None
        return np.maximum(grid, 0.0).astype(np.float32)

    def _coverage_state_exemplar_distance_for_grid(
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
        scale = float(self.coverage_state_exemplar_removed_depth_scale_m)
        diff = (
            np.asarray(removed_grid, dtype=np.float32).reshape(6)
            - exemplar_grid[:6].astype(np.float32)
        ) / scale
        cell_index = int(max(0, min(5, cell_id)))
        diff[cell_index] *= float(self.coverage_state_exemplar_target_cell_weight)
        return float(np.sqrt(np.mean(np.square(diff.astype(np.float32)))))

    def _state_exemplar_weights(
        self,
        selected: list[tuple[float, dict[str, Any]]],
    ) -> np.ndarray:
        distances = np.asarray([distance for distance, _ in selected], dtype=np.float32)
        if distances.size == 0:
            return np.zeros(0, dtype=np.float32)
        if not np.all(np.isfinite(distances)):
            return np.full(
                distances.shape,
                1.0 / float(distances.size),
                dtype=np.float32,
            )
        shifted = distances - float(np.min(distances))
        weights = np.exp(-shifted / float(self.coverage_state_exemplar_temperature))
        weight_sum = float(np.sum(weights))
        if not np.isfinite(weight_sum) or weight_sum <= 1.0e-8:
            return np.full(
                distances.shape,
                1.0 / float(distances.size),
                dtype=np.float32,
            )
        return (weights / weight_sum).astype(np.float32)

    def _weighted_state_exemplar_raw_fields(
        self,
        selected: list[tuple[float, dict[str, Any]]],
    ) -> dict[str, float | int]:
        weights = self._state_exemplar_weights(selected)

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
        length = float(
            np.sqrt(delta_x * delta_x + delta_y * delta_y + delta_z * delta_z)
        )
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

    def _weighted_state_exemplar_profile_token(
        self,
        selected: list[tuple[float, dict[str, Any]]],
    ) -> np.ndarray | None:
        weights = self._state_exemplar_weights(selected)
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
