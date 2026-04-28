from __future__ import annotations

import unittest

import numpy as np

from testbed.eval.quality_metrics import (
    aggregate_quality_metrics,
    build_quality_summary,
)


def _record(
    *,
    t: int,
    cycle_id: int,
    qds: int = 0,
    dump_start: int = 0,
    dump_end: int = 0,
    bucket_qpos: float = 0.10,
    mass_in_bucket: float = 0.0,
    min_distance_to_target: float = 2.0,
    target_horizontal_distance: float | None = None,
    bucket_height_above_target_rim: float = 0.10,
    bucket_over_target_footprint: float = 1.0,
    dump_clearance_ok: float = 1.0,
    deposited_mass: float = 0.0,
    min_distance_to_dig_area: float = 0.0,
    bucket_depth: float = 0.0,
    failures: list[str] | None = None,
    include_target_geometry: bool = True,
) -> dict[str, object]:
    values = [
        mass_in_bucket,
        0.0,
        0.0,
        deposited_mass,
        min_distance_to_target,
        0.0,
        0.0,
        min_distance_to_dig_area,
        bucket_depth,
    ]
    if include_target_geometry:
        values.extend(
            [
                min_distance_to_target
                if target_horizontal_distance is None
                else target_horizontal_distance,
                bucket_height_above_target_rim,
                bucket_over_target_footprint,
                dump_clearance_ok,
            ]
        )
    env_state = np.asarray(values, dtype=np.float32)
    return {
        "t": int(t),
        "cycle_id": int(cycle_id),
        "qualified_dig_start_mask": int(qds),
        "dump_start_mask": int(dump_start),
        "dump_end_mask": int(dump_end),
        "qpos": np.asarray([0.5, 0.5, 0.5, bucket_qpos], dtype=np.float32),
        "env_state": env_state,
        "task_step_failures": list(failures or []),
    }


class TestQualityMetrics(unittest.TestCase):
    def test_build_quality_summary_detects_dig_dump_and_escape_issues(self) -> None:
        records = [
            _record(t=0, cycle_id=-1),
            _record(
                t=1,
                cycle_id=0,
                qds=1,
                bucket_qpos=0.25,
                mass_in_bucket=0.0,
                min_distance_to_dig_area=0.0,
                bucket_depth=0.10,
            ),
            _record(
                t=2,
                cycle_id=0,
                mass_in_bucket=500.0,
                min_distance_to_dig_area=0.40,
                bucket_depth=0.30,
                failures=["spill_before_target"],
            ),
            _record(
                t=3,
                cycle_id=0,
                mass_in_bucket=480.0,
                min_distance_to_dig_area=0.42,
                bucket_depth=0.32,
                failures=["unsafe_target_distance"],
            ),
            _record(t=4, cycle_id=0, mass_in_bucket=460.0, min_distance_to_dig_area=0.45, bucket_depth=0.34),
            _record(t=5, cycle_id=0, mass_in_bucket=430.0, min_distance_to_dig_area=0.46, bucket_depth=0.35),
            _record(t=6, cycle_id=0, mass_in_bucket=410.0, min_distance_to_dig_area=0.47, bucket_depth=0.36),
            _record(
                t=7,
                cycle_id=0,
                dump_start=1,
                mass_in_bucket=100.0,
                min_distance_to_target=1.60,
                min_distance_to_dig_area=0.48,
                bucket_depth=0.37,
            ),
            _record(
                t=8,
                cycle_id=0,
                dump_end=1,
                mass_in_bucket=300.0,
                min_distance_to_target=0.30,
                min_distance_to_dig_area=0.50,
                bucket_depth=0.20,
                failures=["hard_target_collision"],
            ),
        ]

        summary = build_quality_summary(records)

        self.assertEqual(summary["spill_before_target_count"], 1)
        self.assertGreater(float(summary["spill_before_target_rate"]), 0.0)
        self.assertEqual(summary["unsafe_target_distance_count"], 1)
        self.assertGreater(float(summary["unsafe_target_distance_rate"]), 0.0)
        self.assertEqual(summary["hard_target_collision_count"], 1)
        self.assertGreater(float(summary["hard_target_collision_rate"]), 0.0)
        self.assertEqual(summary["qualified_dig_start_count"], 1)
        self.assertEqual(summary["dump_start_count"], 1)
        self.assertEqual(summary["dump_end_count"], 1)
        self.assertEqual(summary["flat_bucket_qds_count"], 1)
        self.assertAlmostEqual(float(summary["flat_bucket_qds_rate"]), 1.0)
        self.assertEqual(summary["far_dump_start_count"], 1)
        self.assertAlmostEqual(float(summary["far_dump_start_rate"]), 1.0)
        self.assertEqual(summary["near_dump_start_count"], 0)
        self.assertAlmostEqual(float(summary["near_dump_start_rate"]), 0.0)
        self.assertEqual(summary["low_carry_efficiency_count"], 1)
        self.assertAlmostEqual(float(summary["low_carry_efficiency_rate"]), 1.0)
        self.assertEqual(summary["high_residual_bucket_mass_count"], 1)
        self.assertAlmostEqual(float(summary["high_residual_bucket_mass_rate"]), 1.0)
        self.assertEqual(summary["dig_area_escape_cycle_count"], 1)
        self.assertAlmostEqual(float(summary["dig_area_escape_cycle_rate"]), 1.0)
        self.assertEqual(summary["shallow_peak_bucket_depth_count"], 0)
        self.assertGreater(float(summary["peak_bucket_depth_mean"]), 0.30)
        self.assertGreater(float(summary["dump_start_distance_mean"]), 1.25)
        self.assertGreater(
            float(summary["dump_start_horizontal_distance_mean"]),
            1.25,
        )
        self.assertEqual(summary["dump_start_geometry_missing_count"], 0)
        self.assertAlmostEqual(float(summary["target_geometry_available_rate"]), 1.0)
        self.assertLess(float(summary["carry_efficiency_proxy_mean"]), 0.40)
        self.assertGreater(float(summary["dig_area_escape_step_ratio"]), 0.0)
        self.assertGreater(int(summary["quality_issue_count"]), 0)

    def test_build_quality_summary_does_not_fallback_to_legacy_target_distance(self) -> None:
        records = [
            _record(t=0, cycle_id=0, qds=1, include_target_geometry=False),
            _record(
                t=1,
                cycle_id=0,
                dump_start=1,
                mass_in_bucket=200.0,
                min_distance_to_target=2.0,
                include_target_geometry=False,
            ),
        ]

        summary = build_quality_summary(records)

        self.assertEqual(summary["dump_start_geometry_missing_count"], 1)
        self.assertEqual(summary["far_dump_start_count"], 0)
        self.assertEqual(summary["near_dump_start_count"], 0)
        self.assertAlmostEqual(float(summary["target_geometry_available_rate"]), 0.0)

    def test_build_quality_summary_reports_per_cycle_deposit_drop(self) -> None:
        records = [
            _record(t=0, cycle_id=0, qds=1, mass_in_bucket=500.0, deposited_mass=0.0),
            _record(
                t=1,
                cycle_id=0,
                dump_start=1,
                mass_in_bucket=500.0,
                deposited_mass=0.0,
            ),
            _record(t=2, cycle_id=0, mass_in_bucket=0.0, deposited_mass=450.0),
            _record(t=3, cycle_id=1, qds=1, mass_in_bucket=500.0, deposited_mass=450.0),
            _record(
                t=4,
                cycle_id=1,
                dump_start=1,
                mass_in_bucket=500.0,
                deposited_mass=450.0,
            ),
            _record(t=5, cycle_id=1, mass_in_bucket=100.0, deposited_mass=900.0),
            _record(t=6, cycle_id=1, mass_in_bucket=0.0, deposited_mass=650.0),
        ]

        summary = build_quality_summary(records)

        self.assertEqual(summary["cycle_deposit_metric_count"], 2)
        self.assertAlmostEqual(float(summary["cycle1_deposited_fraction"]), 0.9)
        self.assertAlmostEqual(float(summary["cycle1_post_dump_target_mass_drop_kg"]), 0.0)
        self.assertAlmostEqual(float(summary["cycle2_deposited_fraction"]), 0.4)
        self.assertAlmostEqual(float(summary["cycle2_post_dump_target_mass_drop_kg"]), 250.0)
        self.assertAlmostEqual(float(summary["cycle_deposited_fraction_min"]), 0.4)
        self.assertEqual(summary["low_cycle_deposited_fraction_count"], 1)
        self.assertEqual(summary["high_cycle_post_dump_drop_count"], 1)

    def test_aggregate_quality_metrics_averages_rollout_summaries(self) -> None:
        metrics = aggregate_quality_metrics(
            [
                {
                    "spill_before_target_count": 2,
                    "spill_before_target_rate": 0.20,
                    "dump_start_distance_mean": 1.5,
                    "near_dump_start_count": 0,
                    "near_dump_start_rate": 0.0,
                    "carry_efficiency_proxy_mean": 0.35,
                    "cycle2_deposited_fraction": 0.4,
                    "cycle2_post_dump_target_mass_drop_kg": 250.0,
                    "quality_issue_count": 5,
                },
                {
                    "spill_before_target_count": 0,
                    "spill_before_target_rate": 0.00,
                    "dump_start_distance_mean": 0.7,
                    "near_dump_start_count": 2,
                    "near_dump_start_rate": 1.0,
                    "carry_efficiency_proxy_mean": 0.85,
                    "cycle2_deposited_fraction": 0.95,
                    "cycle2_post_dump_target_mass_drop_kg": 10.0,
                    "quality_issue_count": 1,
                },
            ]
        )

        self.assertAlmostEqual(metrics["avg_spill_before_target_count"], 1.0)
        self.assertAlmostEqual(metrics["avg_spill_before_target_rate"], 0.10)
        self.assertAlmostEqual(metrics["avg_dump_start_distance_mean"], 1.1)
        self.assertAlmostEqual(metrics["avg_near_dump_start_count"], 1.0)
        self.assertAlmostEqual(metrics["avg_near_dump_start_rate"], 0.5)
        self.assertAlmostEqual(metrics["avg_carry_efficiency_proxy_mean"], 0.60)
        self.assertAlmostEqual(metrics["avg_cycle2_deposited_fraction"], 0.675)
        self.assertAlmostEqual(
            metrics["avg_cycle2_post_dump_target_mass_drop_kg"], 130.0
        )
        self.assertAlmostEqual(metrics["avg_quality_issue_count"], 3.0)


if __name__ == "__main__":
    unittest.main()
