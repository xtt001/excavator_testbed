from __future__ import annotations

import numpy as np

from testbed.planner.primitive_coverage import CoverageCandidateBuilder


def _prior() -> dict[str, object]:
    def field(p10: float, p50: float, p90: float) -> dict[str, float]:
        return {"p10": p10, "p50": p50, "p90": p90}

    return {
        "fields": {
            "entry_x_m": field(-1.0, 0.0, 1.0),
            "entry_z_m": field(0.0, 0.5, 1.0),
            "exit_x_m": field(-2.0, -1.0, 0.0),
            "exit_z_m": field(0.0, 0.5, 1.0),
            "cut_direction_x": field(-1.0, -1.0, 0.0),
            "cut_direction_z": field(-0.5, 0.0, 0.5),
            "cut_length_m": field(0.5, 1.0, 1.5),
            "cut_depth_peak_m": field(0.03, 0.08, 0.12),
            "payload_gain_kg": field(20.0, 55.0, 90.0),
            "effective_deposit_delta_kg": field(10.0, 45.0, 80.0),
        }
    }


def test_coverage_candidate_builder_builds_percentile_grid() -> None:
    builder = CoverageCandidateBuilder(
        candidate_layout="percentile_grid",
        entry_x_percentiles=("p10", "p90"),
        entry_z_percentiles=("p10", "p50", "p90"),
        cut_direction_percentile="p50",
        cut_length_percentile="p50",
        cut_depth_percentile="p90",
        payload_percentile="p50",
    )

    corridors = builder.build(_prior())

    assert [corridor.corridor_id for corridor in corridors] == list(range(6))
    assert [corridor.cell_id for corridor in corridors] == [0, 1, 2, 3, 4, 5]
    assert corridors[0].entry_x_m == -1.0
    assert corridors[0].entry_z_m == 0.0
    assert corridors[0].exit_x_m == -2.0
    assert corridors[0].cut_depth_peak_m == 0.12
    assert corridors[0].payload_gain_kg == 55.0


def test_coverage_candidate_builder_builds_cell_weighted_corridors() -> None:
    prior = _prior()
    prior["coverage_cells"] = [
        {
            "cell_id": 2,
            "source_count": 7,
            "source_fraction": 0.25,
            "entry": {"x_m": -0.2, "z_m": 0.8},
            "exit": {"x_m": -1.1, "z_m": 0.8},
            "entry_stats": {"x_m": {"p05": -0.3, "p50": -0.2, "p95": -0.1}},
            "cut_depth_peak_m_stats": {"p05": 0.04, "p50": 0.08, "p95": 0.12},
            "payload_gain_kg": 70.0,
            "effective_deposit_delta_kg": 60.0,
        },
        {"cell_id": 0, "entry": {"x_m": -0.8, "z_m": 0.2}},
    ]
    builder = CoverageCandidateBuilder(
        candidate_layout="cell_weighted_3x2",
        entry_x_percentiles=("p10",),
        entry_z_percentiles=("p10",),
        cut_direction_percentile="p50",
        cut_length_percentile="p50",
        cut_depth_percentile="p50",
        payload_percentile="p90",
    )

    corridors = builder.build(prior)

    assert [corridor.cell_id for corridor in corridors] == [0, 2]
    assert corridors[1].corridor_id == 1
    assert corridors[1].source_count == 7
    assert np.isclose(corridors[1].source_fraction, 0.25)
    assert corridors[1].entry_x_p05_m == -0.3
    assert corridors[1].cut_depth_peak_p95_m == 0.12
    assert corridors[1].payload_gain_kg == 70.0
    assert corridors[1].effective_deposit_delta_kg == 60.0
