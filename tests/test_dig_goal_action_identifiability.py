from __future__ import annotations

import numpy as np

from testbed.eval.dig_goal_action_identifiability import (
    action_signal_metrics,
    assess_action_signal,
    build_identifiability_contract,
    camera_observation_matches,
    classify_goal_relation,
    classify_identifiability_precheck,
    hierarchical_source_episode_signal_bootstrap,
    same_non_goal_observation,
    target_token_matches,
)


def _row(*, source: int = 3, episode: int = 10) -> dict:
    return {
        "source_episode_id": source,
        "primitive_episode_id": episode,
        "qpos": np.asarray([0.5, 0.4, 0.3, 0.2], dtype=np.float32),
        "qvel": np.asarray([0.0, 0.01, -0.01, 0.0], dtype=np.float32),
        "controller_epoch": "epoch_a",
        "controller_profile": "profile_a",
        "calibration_schema": "calibration_a",
    }


def _token() -> np.ndarray:
    return np.asarray(
        [0.25, -0.1, 0.05, 0.0, -0.98, 0.2, 0.25, 0.5, 1.0, 1.0],
        dtype=np.float32,
    )


def test_non_goal_match_freezes_state_metadata_source_and_episode_contract() -> None:
    contract = build_identifiability_contract()
    left = _row()
    right = _row(episode=11)
    right["qpos"] = left["qpos"] + np.asarray([0.005, 0.0, 0.0, 0.0])
    right["qvel"] = left["qvel"] + np.asarray([0.0, 0.02, 0.0, 0.0])

    result = same_non_goal_observation(left, right, contract=contract)

    assert result["matched"] is True
    assert np.isclose(result["qpos_max_abs"], 0.005)
    assert np.isclose(result["qvel_max_abs"], 0.02)
    assert (
        same_non_goal_observation(
            left, {**right, "source_episode_id": 33}, contract=contract
        )["matched"]
        is False
    )
    assert (
        same_non_goal_observation(
            left, {**right, "controller_profile": "other"}, contract=contract
        )["matched"]
        is False
    )
    assert same_non_goal_observation(left, left, contract=contract)["matched"] is False


def test_goal_relation_recognises_frozen_axis_and_magnitude_bins() -> None:
    contract = build_identifiability_contract()
    base = _token()
    alternate = base.copy()
    alternate[[0, 2]] += 0.05

    result = classify_goal_relation(base, alternate, contract=contract)

    assert result["relation"] == "position_translation"
    assert result["translation_bin"] == "x_plus_0p10m"
    assert np.isclose(result["translation_magnitude_m"], 0.1)
    same = classify_goal_relation(base, base + 1.0e-4, contract=contract)
    assert same["relation"] == "same_goal"


def test_target_match_requires_geometry_and_non_position_fields() -> None:
    contract = build_identifiability_contract()
    target = _token()
    close = target.copy()
    close[[0, 1, 2, 3]] += 0.01

    assert target_token_matches(close, target, contract=contract)["matched"] is True
    far = close.copy()
    far[7] += 0.10
    assert target_token_matches(far, target, contract=contract)["matched"] is False


def test_camera_gate_requires_all_three_frozen_image_checks() -> None:
    contract = build_identifiability_contract()
    passing = {
        "mean_normalised_pixel_mae": 0.05,
        "mean_pixel_correlation": 0.95,
        "mean_difference_hash_hamming_fraction": 0.10,
    }

    assert camera_observation_matches(passing, contract=contract)["matched"] is True
    assert (
        camera_observation_matches(
            {**passing, "mean_pixel_correlation": 0.89}, contract=contract
        )["matched"]
        is False
    )


def test_action_signal_must_exceed_fixed_response_and_same_goal_noise() -> None:
    contract = build_identifiability_contract()
    baseline = np.zeros((100, 4), dtype=np.float32)
    alternate = baseline.copy()
    alternate[:10, 0] = 0.20
    metrics = action_signal_metrics(
        baseline,
        alternate,
        action_std=np.ones(4, dtype=np.float32),
        contract=contract,
    )

    result = assess_action_signal(metrics, same_goal_noise_p95=0.10, contract=contract)

    assert metrics["first_10_responsive_fraction"] == 1.0
    assert result["passed"] is True
    assert (
        assess_action_signal(metrics, same_goal_noise_p95=0.25, contract=contract)[
            "passed"
        ]
        is False
    )


def test_source_episode_bootstrap_confirms_signal_above_noise() -> None:
    signal = []
    noise = []
    for source in (3, 6, 7, 8):
        for episode in range(5):
            signal.append(
                {
                    "source_episode_id": source,
                    "primitive_episode_ids": [
                        source * 100 + episode,
                        source * 1000 + episode,
                    ],
                    "first_10_mean_l2": 1.0,
                }
            )
            noise.append(
                {
                    "source_episode_id": source,
                    "primitive_episode_ids": [
                        source * 200 + episode,
                        source * 2000 + episode,
                    ],
                    "first_10_mean_l2": 0.0,
                }
            )

    result = hierarchical_source_episode_signal_bootstrap(
        signal_pairs=signal,
        noise_pairs=noise,
        resamples=500,
        seed=20260823,
    )

    assert result["common_source_count"] == 4
    assert result["point_difference"] == 1.0
    assert result["ci95_low"] == 1.0
    assert result["ci95_high"] == 1.0


def _passing_summary() -> dict:
    return {
        "same_goal_noise_pair_count": 40,
        "same_goal_noise_source_count": 5,
        "different_goal_pair_count": 120,
        "different_goal_source_count": 9,
        "covered_variant_count": 104,
        "planned_variant_count": 112,
        "translation_bin_counts": {
            name: 10
            for name in build_identifiability_contract().required_translation_bins
        },
        "action_signal_pass_fraction": 0.85,
        "bootstrap_ci95_low": 0.01,
    }


def test_data_gate_blocks_training_before_any_architecture_comparison() -> None:
    summary = _passing_summary()
    summary["covered_variant_count"] = 99

    decision = classify_identifiability_precheck(
        summary=summary,
        invalid_reasons=(),
        contract=build_identifiability_contract(),
    )

    assert decision["classification"] == "data_supervision_unidentifiable"
    assert decision["act_dp_training_allowed"] is False
    assert decision["next_experiment"] == "paired_goal_action_demonstrations"


def test_data_gate_allows_training_only_after_every_gate_passes() -> None:
    decision = classify_identifiability_precheck(
        summary=_passing_summary(),
        invalid_reasons=(),
        contract=build_identifiability_contract(),
    )

    assert decision["classification"] == "goal_action_supervision_identifiable"
    assert decision["act_dp_training_allowed"] is True
    assert decision["next_experiment"] == "fair_act_vs_diffusion_policy_training"


def test_missing_lineage_is_invalid_and_never_trains() -> None:
    decision = classify_identifiability_precheck(
        summary=_passing_summary(),
        invalid_reasons=("support_lineage_missing",),
        contract=build_identifiability_contract(),
    )

    assert decision["classification"] == "invalid_precheck"
    assert decision["act_dp_training_allowed"] is False
