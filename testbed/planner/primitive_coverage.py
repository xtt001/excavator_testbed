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


__all__ = ["CoverageCandidateBuilder", "CoverageCorridorState"]
