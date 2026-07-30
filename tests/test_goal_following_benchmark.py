from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from testbed.data.schema import ENV_STATE_ORDER_V2_3
from testbed.data.terrain_signature import build_terrain_signature_v1
from testbed.eval.goal_following_benchmark import (
    ACT_TRACKING_MARGIN_M,
    GoalFollowingCycleInput,
    build_matching_features,
    diagnostic_nearest_expert,
    evaluate_goal_following_cycle,
    run_goal_following_benchmark,
)
from testbed.planner.primitive.coverage.continuous_goal import (
    ContinuousCutGoal,
)


def _terrain(seed: float = 0.0):
    return build_terrain_signature_v1(
        {
            name: seed + float(index) / 100.0
            for index, name in enumerate(ENV_STATE_ORDER_V2_3)
        }
    )


def _goal() -> dict[str, object]:
    return ContinuousCutGoal.create(
        target_cell_id=2,
        entry_xz_m=(0.0, 0.0),
        exit_xz_m=(0.3, 0.4),
        planned_depth_m=0.08,
        payload_intent_kg=40.0,
        effect_intent={
            "kind": "remove_soil",
            "target_mass_kg": 40.0,
        },
        terrain_signature={"schema": "terrain_signature_v1"},
    ).as_dict()


def _cycle(
    *,
    cycle_id: str = "train_1",
    split: str = "train",
    offset: float = 0.01,
    worktool_offset_m: float | None = None,
    remaining_depth_m: float = 0.08,
    reference_safe: bool = True,
    effect_delta: float = 0.0,
    qpos_bound: float = 0.02,
    rollout_cycle: int | None = None,
) -> GoalFollowingCycleInput:
    progress = np.linspace(0.0, 1.0, 5)
    reference_qpos = np.stack(
        [progress, 2.0 * progress, 3.0 * progress, 4.0 * progress],
        axis=1,
    )
    actual_qpos = reference_qpos + offset
    reference_worktool = np.stack(
        [progress, progress * 0.5, progress * 0.25],
        axis=1,
    )
    displacement = offset if worktool_offset_m is None else worktool_offset_m
    actual_worktool = reference_worktool.copy()
    actual_worktool[:, 0] += displacement
    return GoalFollowingCycleInput(
        cycle_id=cycle_id,
        split=split,
        source_episode_id=1 if split != "source_heldout" else 33,
        rollout_cycle=rollout_cycle,
        is_first_dig=cycle_id.endswith("1"),
        target_region="region_a",
        remaining_depth_m=remaining_depth_m,
        continuous_goal=_goal(),
        handoff_qpos=(0.0, 0.0, 0.0, 0.0),
        handoff_qvel=(0.0, 0.0, 0.0, 0.0),
        terrain_signature=_terrain(),
        planned_entry_xz_m=(0.0, 0.0),
        actual_entry_xz_m=(0.01, 0.0),
        planned_exit_xz_m=(0.3, 0.4),
        actual_exit_xz_m=(0.31, 0.4),
        planned_terrain_relative_depth_m=0.08,
        actual_terrain_relative_depth_m=0.075,
        planned_duration_s=4.0,
        actual_duration_s=4.2,
        reference_qpos_path=reference_qpos,
        actual_qpos_path=actual_qpos,
        reference_timestamps_s=np.linspace(0.0, 4.0, 5),
        actual_timestamps_s=np.linspace(0.0, 4.2, 5),
        reference_phase=progress,
        actual_phase=progress,
        qpos_abs_error_bound=np.full((64, 4), qpos_bound),
        reference_worktool_path=reference_worktool,
        actual_worktool_path=actual_worktool,
        reference_safe=reference_safe,
        support_status="supported",
        goal_valid=True,
        planned_effect=(40.0,),
        actual_effect=(40.0 + effect_delta,),
        effect_abs_tolerance=(2.0,),
    )


def test_cycle_metrics_cover_geometry_joint_time_dtw_and_worktool() -> None:
    metrics = evaluate_goal_following_cycle(_cycle(offset=0.01))

    assert metrics.geometry["planned"]["entry_xz_m"] == pytest.approx([0.0, 0.0])
    assert metrics.geometry["actual"]["exit_xz_m"] == pytest.approx([0.31, 0.4])
    assert metrics.geometry["planned"]["direction_xz"] == pytest.approx([0.6, 0.8])
    assert metrics.geometry["planned"]["length_m"] == pytest.approx(0.5)
    assert metrics.geometry["actual"]["terrain_relative_depth_m"] == pytest.approx(
        0.075
    )
    assert metrics.geometry["actual"]["duration_s"] == pytest.approx(4.2)
    assert metrics.phase_normalized_qpos["mae"] == pytest.approx([0.01] * 4)
    assert metrics.phase_normalized_qpos["rmse"] == pytest.approx([0.01] * 4)
    assert metrics.phase_normalized_qpos["p95"] == pytest.approx([0.01] * 4)
    assert metrics.phase_normalized_qpos["max"] == pytest.approx([0.01] * 4)
    assert metrics.phase_normalized_qpos["end_error"] == pytest.approx([0.01] * 4)
    assert set(metrics.raw_time_qpos) >= {
        "mae",
        "rmse",
        "p95",
        "max",
        "end_error",
    }
    assert metrics.dtw_qpos["alignment"] == "monotonic_dtw"
    assert metrics.worktool_tracking_3d["max_m"] == pytest.approx(0.01)
    assert metrics.tracking_breach is False


def test_matching_uses_full_goal_handoff_and_terrain_and_is_diagnostic_only() -> None:
    query = build_matching_features(
        continuous_goal=_goal(),
        handoff_qpos=(0.0, 0.1, 0.2, 0.3),
        handoff_qvel=(0.4, 0.5, 0.6, 0.7),
        terrain_signature=_terrain(),
    )
    close = build_matching_features(
        continuous_goal=_goal(),
        handoff_qpos=(0.0, 0.1, 0.2, 0.31),
        handoff_qvel=(0.4, 0.5, 0.6, 0.7),
        terrain_signature=_terrain(0.001),
    )
    far = build_matching_features(
        continuous_goal=_goal(),
        handoff_qpos=(1.0, 1.0, 1.0, 1.0),
        handoff_qvel=(1.0, 1.0, 1.0, 1.0),
        terrain_signature=_terrain(1.0),
    )

    assert query.continuous_goal == _goal()
    assert len(query.handoff_qpos) == len(query.handoff_qvel) == 4
    assert len(query.terrain_signature) == 89
    match = diagnostic_nearest_expert(
        query,
        {"close": close, "far": far},
    )
    assert match.window_id == "close"
    assert match.diagnostic_only is True
    assert match.runtime_binding_allowed is False

    bad_goal = _goal()
    bad_goal["source_episode_id"] = 12
    with pytest.raises(ValueError, match="runtime binding"):
        build_matching_features(
            continuous_goal=bad_goal,
            handoff_qpos=(0.0,) * 4,
            handoff_qvel=(0.0,) * 4,
            terrain_signature=_terrain(),
        )


def test_benchmark_quantiles_are_train_only_and_strata_are_complete() -> None:
    train = [
        _cycle(
            cycle_id=f"train_{index}",
            remaining_depth_m=float(index),
        )
        for index in range(1, 6)
    ]
    heldout = _cycle(
        cycle_id="heldout_1",
        split="source_heldout",
        remaining_depth_m=1000.0,
    )
    rollout = _cycle(
        cycle_id="rollout_1",
        split="rollout_eval",
        remaining_depth_m=5000.0,
        rollout_cycle=1,
    )

    report = run_goal_following_benchmark([*train, heldout, rollout])

    assert report.remaining_depth_quantiles["fit_partition"] == "train"
    assert report.remaining_depth_quantiles["maximum_m"] == pytest.approx(5.0)
    assert report.remaining_depth_quantiles["sample_count"] == 5
    heldout_result = next(row for row in report.cycles if row.cycle_id == "heldout_1")
    assert set(heldout_result.strata) == {
        "dig_history",
        "target_region",
        "remaining_depth_quantile",
        "split",
        "rollout_cycle",
    }
    assert heldout_result.strata["split"] == "source_heldout"
    assert report.live_unlocked is False
    assert report.promotion_eligible is False


def test_benchmark_decision_is_strictly_limited_and_tracking_requires_repeats() -> None:
    unsafe = run_goal_following_benchmark(
        [
            _cycle(cycle_id="unsafe_1", reference_safe=False),
            _cycle(cycle_id="unsafe_2"),
        ]
    )
    assert unsafe.decision == "reference_or_goal_primary"

    one_breach = run_goal_following_benchmark(
        [
            _cycle(
                cycle_id="breach_1",
                worktool_offset_m=ACT_TRACKING_MARGIN_M + 0.001,
            ),
            _cycle(cycle_id="ok_2"),
        ]
    )
    assert one_breach.decision == "insufficient_evidence"

    repeated_breach = run_goal_following_benchmark(
        [
            _cycle(
                cycle_id="breach_1",
                worktool_offset_m=ACT_TRACKING_MARGIN_M + 0.001,
            ),
            _cycle(
                cycle_id="breach_2",
                worktool_offset_m=ACT_TRACKING_MARGIN_M + 0.002,
            ),
        ]
    )
    assert repeated_breach.decision == "act_tracking_primary"
    assert repeated_breach.act_retraining_allowed is True

    qpos_tube_breach = run_goal_following_benchmark(
        [
            _cycle(
                cycle_id="tube_1",
                offset=0.03,
                worktool_offset_m=0.01,
                qpos_bound=0.02,
            ),
            _cycle(
                cycle_id="tube_2",
                offset=0.03,
                worktool_offset_m=0.01,
                qpos_bound=0.02,
            ),
        ]
    )
    assert qpos_tube_breach.decision == "act_tracking_primary"

    effect = run_goal_following_benchmark(
        [
            _cycle(cycle_id="effect_1", effect_delta=4.0),
            _cycle(cycle_id="effect_2", effect_delta=5.0),
        ]
    )
    assert effect.decision == "effect_calibration_primary"
    assert effect.act_retraining_allowed is False

    no_effect_evidence = run_goal_following_benchmark(
        [
            replace(
                _cycle(cycle_id="missing_1"),
                planned_effect=(),
                actual_effect=(),
                effect_abs_tolerance=(),
            )
        ]
    )
    assert no_effect_evidence.decision == "insufficient_evidence"
    assert {
        unsafe.decision,
        one_breach.decision,
        repeated_breach.decision,
        effect.decision,
    } <= {
        "reference_or_goal_primary",
        "act_tracking_primary",
        "effect_calibration_primary",
        "insufficient_evidence",
    }


def test_goal_following_benchmark_matches_synthetic_offline_golden_v1() -> None:
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "goal_following_benchmark"
        / "golden_v1.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    report = run_goal_following_benchmark(
        [
            _cycle(
                cycle_id="golden_train_1",
                remaining_depth_m=0.04,
                effect_delta=4.0,
            ),
            _cycle(
                cycle_id="golden_train_2",
                remaining_depth_m=0.12,
                effect_delta=5.0,
            ),
        ]
    )
    canonical = json.dumps(
        report.as_dict(),
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    assert fixture["fixture_schema"] == ("goal_following_benchmark_golden_fixture_v1")
    assert fixture["evidence_kind"] == "synthetic_offline_only"
    assert fixture["real_rollout_evidence"] is False
    assert report.decision == fixture["expected_decision"]
    assert len(report.cycles) == fixture["expected_cycle_count"]
    assert hashlib.sha256(canonical).hexdigest() == fixture["report_sha256"]
