from __future__ import annotations

import pytest

from testbed.eval.planned_cut_calibration import assess_capability_label_support
from testbed.eval.terrain_effect_acceptance import (
    build_planned_cut_calibration_acceptance,
    build_replay_effect_cv_acceptance,
)


def _replay_cv_rows() -> list[dict]:
    rows: list[dict] = []
    for fold_index in range(6):
        for candidate_index, actual in enumerate((1.0, 2.0, 3.0, 4.0)):
            rows.append(
                {
                    "fold_index": fold_index,
                    "episode_id": f"episode_{fold_index}",
                    "candidate_group_id": f"fold_{fold_index}_state_0",
                    "actual_candidate_utility": actual,
                    "effect_candidate_score": actual + 0.01,
                    "actual_removed_volume_m3": actual,
                    "actual_payload_gain_kg": actual * 10.0,
                    "effect_removed_volume_m3": actual + 0.05,
                    "effect_payload_gain_kg": actual * 10.0 + 0.5,
                    "constant_removed_volume_m3": 2.5,
                    "constant_payload_gain_kg": 25.0,
                    "geometric_removed_volume_m3": actual + 0.4,
                    "geometric_payload_gain_kg": actual * 10.0 + 4.0,
                    "actual_signed_depth_delta_m": [actual * 0.1] * 6,
                    "effect_signed_depth_delta_m": [actual * 0.1 + 0.005] * 6,
                    "geometric_signed_depth_delta_m": [actual * 0.1 + 0.006] * 6,
                }
            )
    return rows


def test_replay_acceptance_requires_formal_six_fold_baselines_and_spearman() -> None:
    result = build_replay_effect_cv_acceptance(
        _replay_cv_rows(),
        min_candidate_spearman=0.9,
    )

    assert result["schema"] == "replay_effect_cv_acceptance_v1"
    assert result["fold_count"] == 6
    assert result["fold_indices"] == [0, 1, 2, 3, 4, 5]
    assert result["status"] == "pass"
    assert result["candidate_spearman"]["median"] == pytest.approx(1.0)
    assert (
        result["mae"]["effect"]["removed_volume_m3"]
        < result["mae"]["geometric"]["removed_volume_m3"]
    )
    assert result["improvement_fraction"]["vs_constant"]["payload_gain_kg"] > 0
    assert result["constant_baseline_gate"]["minimum_improvement_fraction"] == 0.10
    assert result["cell_delta_geometric_gate"]["maximum_mae_ratio"] == 1.05

    with pytest.raises(ValueError, match="exactly folds"):
        build_replay_effect_cv_acceptance(
            _replay_cv_rows()[:-4],
            min_candidate_spearman=0.9,
        )


def test_replay_acceptance_enforces_exact_mae_and_median_rank_gates() -> None:
    below_ten_percent = _replay_cv_rows()
    for row in below_ten_percent:
        row["effect_removed_volume_m3"] = (
            row["actual_removed_volume_m3"] + 0.91
        )
    result = build_replay_effect_cv_acceptance(
        below_ten_percent,
        min_candidate_spearman=0.0,
    )
    assert result["status"] == "fail"
    assert result["constant_baseline_gate"]["status"] == "fail"

    cell_delta_worse = _replay_cv_rows()
    for row in cell_delta_worse:
        actual = row["actual_signed_depth_delta_m"]
        row["effect_signed_depth_delta_m"] = [value + 0.0106 for value in actual]
        row["geometric_signed_depth_delta_m"] = [value + 0.0100 for value in actual]
    result = build_replay_effect_cv_acceptance(
        cell_delta_worse,
        min_candidate_spearman=0.0,
    )
    assert result["status"] == "fail"
    assert result["cell_delta_geometric_gate"]["status"] == "fail"

    reversed_ranking = _replay_cv_rows()
    for row in reversed_ranking:
        row["effect_candidate_score"] = -row["actual_candidate_utility"]
    result = build_replay_effect_cv_acceptance(
        reversed_ranking,
        min_candidate_spearman=0.0,
    )
    assert result["status"] == "fail"
    assert result["candidate_spearman"]["median"] == pytest.approx(-1.0)


def _planned_rows(*, direct_is_better: bool) -> list[dict]:
    rows: list[dict] = []
    for reset_group_id in ("heldout_a", "heldout_b", "heldout_c"):
        for actual in (1.0, 2.0, 3.0):
            two_stage_volume = actual + 0.05
            two_stage_payload = actual * 10.0 + 0.5
            direct_scale = 0.5 if direct_is_better else 1.0
            rows.append(
                {
                    "reset_group_id": reset_group_id,
                    "actual_removed_volume_m3": actual,
                    "actual_payload_gain_kg": actual * 10.0,
                    "plan_as_executed_removed_volume_m3": actual + 0.5,
                    "plan_as_executed_payload_gain_kg": actual * 10.0 + 5.0,
                    "two_stage_removed_volume_m3": two_stage_volume,
                    "two_stage_payload_gain_kg": two_stage_payload,
                    "direct_planned_removed_volume_m3": actual + 0.05 * direct_scale,
                    "direct_planned_payload_gain_kg": actual * 10.0
                    + 0.5 * direct_scale,
                }
            )
    return rows


def test_planned_acceptance_uses_heldout_reset_groups_and_release_gates() -> None:
    result = build_planned_cut_calibration_acceptance(
        _planned_rows(direct_is_better=True),
        training_reset_group_ids={"train_a", "train_b", "train_c"},
    )

    assert result["schema"] == "planned_cut_calibration_acceptance_v1"
    assert result["two_stage_calibration_gate"]["status"] == "pass"
    assert result["two_stage_calibration_gate"]["minimum_improvement_fraction"] == 0.10
    assert result["direct_planned_residual_gate"]["status"] == "release_allowed"
    assert (
        result["direct_planned_residual_gate"][
            "minimum_incremental_improvement_fraction"
        ]
        == 0.05
    )

    blocked = build_planned_cut_calibration_acceptance(
        _planned_rows(direct_is_better=False),
        training_reset_group_ids={"train_a", "train_b", "train_c"},
    )
    assert blocked["direct_planned_residual_gate"]["status"] == "not_release"


def test_capability_support_requires_20_each_and_three_reset_groups_per_class() -> None:
    supported: list[dict] = []
    for value in (False, True):
        for index in range(20):
            supported.append(
                {
                    "reset_group_id": f"reset_{int(value)}_{index % 3}",
                    "capability_labels": {"effective_move": value},
                }
            )
    result = assess_capability_label_support(supported)

    assert (
        result["labels"]["effective_move"]["status"]
        == "eligible_for_learned_classifier"
    )

    insufficient = assess_capability_label_support(supported[:-1])
    assert insufficient["labels"]["effective_move"]["status"] == "rule_only_or_ood"
    assert insufficient["overall_status"] == "rule_only_or_ood"
