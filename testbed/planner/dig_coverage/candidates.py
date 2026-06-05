"""Coverage corridor candidate construction helpers."""

from __future__ import annotations

from .models import *


class CoverageCandidateBuilderMixin:
    def _select_next_coverage_corridor(self, obs: dict) -> CoverageCorridorState:
        return self._select_next_coverage_corridor_result(obs).corridor

    def _select_next_coverage_corridor_result(
        self,
        obs: dict,
    ) -> CoverageSelectionResult:
        if not self.dig_cut_prior:
            raise ValueError(
                f"{self.dig_cut_planner_mode} mode requires a dig cut prior JSON."
            )
        self._ensure_coverage_corridors()
        if not self._coverage_corridors:
            raise ValueError(
                f"{self.dig_cut_planner_mode} could not build candidate corridors."
            )
        result = self._select_coverage_corridor_result(obs)
        corridor = result.corridor
        self._coverage_active_corridor_id = int(corridor.corridor_id)
        self._coverage_last_selected_corridor_id = int(corridor.corridor_id)
        return result

    def _ensure_coverage_corridors(self) -> None:
        if self._coverage_corridors:
            return
        fields = dict(self.dig_cut_prior.get("fields", {}))
        if self.coverage_candidate_layout == "cell_weighted_3x2":
            self._coverage_corridors = self._build_cell_weighted_coverage_corridors(fields)
            return

        candidates: list[CoverageCorridorState] = []
        corridor_id = 0
        for z_index, z_percentile in enumerate(self.coverage_entry_z_percentiles):
            for x_index, x_percentile in enumerate(self.coverage_entry_x_percentiles):
                entry_x = self._prior_percentile(fields, "entry_x_m", x_percentile)
                entry_z = self._prior_percentile(fields, "entry_z_m", z_percentile)
                exit_x, exit_z = self._coverage_exit_from_entry(entry_x, entry_z)
                cell_id = self._coverage_cell_id_from_percentile_indices(
                    x_index=x_index,
                    x_count=len(self.coverage_entry_x_percentiles),
                    z_index=z_index,
                    z_count=len(self.coverage_entry_z_percentiles),
                )
                candidates.append(
                    CoverageCorridorState(
                        corridor_id=corridor_id,
                        entry_x_m=float(entry_x),
                        entry_z_m=float(entry_z),
                        exit_x_m=float(exit_x),
                        exit_z_m=float(exit_z),
                        cell_id=int(cell_id),
                    )
                )
                corridor_id += 1
        self._coverage_corridors = candidates

    def _build_cell_weighted_coverage_corridors(
        self,
        fields: dict[str, object],
    ) -> list[CoverageCorridorState]:
        raw_cells = self.dig_cut_prior.get("coverage_cells", [])
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
            entry_x = self._coverage_cell_float(
                entry,
                "x_m",
                self._prior_percentile(fields, "entry_x_m", "p50"),
            )
            entry_z = self._coverage_cell_float(
                entry,
                "z_m",
                self._prior_percentile(fields, "entry_z_m", "p50"),
            )
            if "x_m" in exit_point and "z_m" in exit_point:
                exit_x = self._coverage_cell_float(
                    exit_point,
                    "x_m",
                    self._prior_percentile(fields, "exit_x_m", "p50"),
                )
                exit_z = self._coverage_cell_float(
                    exit_point,
                    "z_m",
                    self._prior_percentile(fields, "exit_z_m", "p50"),
                )
            else:
                exit_x, exit_z = self._coverage_exit_from_entry(entry_x, entry_z)
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
                    entry_x_p05_m=self._coverage_stat_float(
                        entry_stats, "x_m", "p05", float(entry_x)
                    ),
                    entry_x_p50_m=self._coverage_stat_float(
                        entry_stats, "x_m", "p50", float(entry_x)
                    ),
                    entry_x_p95_m=self._coverage_stat_float(
                        entry_stats, "x_m", "p95", float(entry_x)
                    ),
                    entry_z_p05_m=self._coverage_stat_float(
                        entry_stats, "z_m", "p05", float(entry_z)
                    ),
                    entry_z_p50_m=self._coverage_stat_float(
                        entry_stats, "z_m", "p50", float(entry_z)
                    ),
                    entry_z_p95_m=self._coverage_stat_float(
                        entry_stats, "z_m", "p95", float(entry_z)
                    ),
                    entry_radial_p75_m=self._coverage_stat_float(
                        entry_stats, "radial_error_m", "p75", float("nan")
                    ),
                    entry_radial_p95_m=self._coverage_stat_float(
                        entry_stats, "radial_error_m", "p95", float("nan")
                    ),
                    exit_x_p05_m=self._coverage_stat_float(
                        exit_stats, "x_m", "p05", float(exit_x)
                    ),
                    exit_x_p50_m=self._coverage_stat_float(
                        exit_stats, "x_m", "p50", float(exit_x)
                    ),
                    exit_x_p95_m=self._coverage_stat_float(
                        exit_stats, "x_m", "p95", float(exit_x)
                    ),
                    exit_z_p05_m=self._coverage_stat_float(
                        exit_stats, "z_m", "p05", float(exit_z)
                    ),
                    exit_z_p50_m=self._coverage_stat_float(
                        exit_stats, "z_m", "p50", float(exit_z)
                    ),
                    exit_z_p95_m=self._coverage_stat_float(
                        exit_stats, "z_m", "p95", float(exit_z)
                    ),
                    exit_radial_p75_m=self._coverage_stat_float(
                        exit_stats, "radial_error_m", "p75", float("nan")
                    ),
                    exit_radial_p95_m=self._coverage_stat_float(
                        exit_stats, "radial_error_m", "p95", float("nan")
                    ),
                    cut_depth_peak_p05_m=self._coverage_cell_float(
                        depth_stats,
                        "p05",
                        self._prior_percentile(fields, "cut_depth_peak_m", "p10"),
                    ),
                    cut_depth_peak_p50_m=self._coverage_cell_float(
                        depth_stats,
                        "p50",
                        self._prior_percentile(fields, "cut_depth_peak_m", "p50"),
                    ),
                    cut_depth_peak_p95_m=self._coverage_cell_float(
                        depth_stats,
                        "p95",
                        self._prior_percentile(fields, "cut_depth_peak_m", "p90"),
                    ),
                    cut_depth_peak_m=self._coverage_cell_float(
                        cell,
                        "cut_depth_peak_m",
                        self._prior_percentile(
                            fields,
                            "cut_depth_peak_m",
                            self.coverage_cut_depth_percentile,
                        ),
                    ),
                    payload_gain_kg=self._coverage_cell_float(
                        cell,
                        "payload_gain_kg",
                        self._prior_percentile(
                            fields,
                            "payload_gain_kg",
                            self.coverage_payload_percentile,
                        ),
                    ),
                    effective_deposit_delta_kg=self._coverage_cell_float(
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

    @staticmethod
    def _coverage_cell_float(
        mapping: dict[str, object],
        name: str,
        default: float,
    ) -> float:
        try:
            value = float(mapping.get(name, default))
        except (TypeError, ValueError):
            value = float(default)
        return float(value if np.isfinite(value) else default)

    @classmethod
    def _coverage_stat_float(
        cls,
        mapping: dict[str, object],
        section: str,
        name: str,
        default: float,
    ) -> float:
        section_mapping = mapping.get(section, {})
        if not isinstance(section_mapping, dict):
            return float(default)
        return cls._coverage_cell_float(section_mapping, name, default)

    def _coverage_exit_from_entry(self, entry_x: float, entry_z: float) -> tuple[float, float]:
        fields = dict(self.dig_cut_prior.get("fields", {}))
        dir_x = self._prior_percentile(
            fields,
            "cut_direction_x",
            self.coverage_cut_direction_percentile,
        )
        dir_z = self._prior_percentile(
            fields,
            "cut_direction_z",
            self.coverage_cut_direction_percentile,
        )
        norm = float(np.hypot(dir_x, dir_z))
        if norm <= 1.0e-6:
            dir_x, dir_z = -1.0, 0.0
        else:
            dir_x, dir_z = dir_x / norm, dir_z / norm
        length = self._prior_percentile(
            fields,
            "cut_length_m",
            self.coverage_cut_length_percentile,
        )
        return (
            self._clamp_to_prior(fields, "exit_x_m", float(entry_x) + dir_x * length),
            self._clamp_to_prior(fields, "exit_z_m", float(entry_z) + dir_z * length),
        )
