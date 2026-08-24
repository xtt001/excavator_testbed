from __future__ import annotations

import numpy as np

from testbed.eval.dig_goal_action_data import (
    enumerate_identifiability_pairs,
    evaluate_variant_demonstration_coverage,
)
from testbed.eval.dig_goal_action_identifiability import (
    build_identifiability_contract,
)


def _token() -> np.ndarray:
    return np.asarray(
        [0.25, -0.1, 0.05, 0.0, -0.98, 0.2, 0.25, 0.5, 1.0, 1.0],
        dtype=np.float32,
    )


def _row(episode: int, token: np.ndarray, action_value: float) -> dict:
    actions = np.zeros((100, 4), dtype=np.float32)
    actions[:10, 0] = action_value
    return {
        "source_episode_id": 3,
        "primitive_episode_id": episode,
        "qpos": np.asarray([0.5, 0.4, 0.3, 0.2], dtype=np.float32),
        "qvel": np.zeros(4, dtype=np.float32),
        "controller_epoch": "epoch_a",
        "controller_profile": "profile_a",
        "calibration_schema": "calibration_a",
        "token": token.copy(),
        "actions": actions,
        "image_signature": {"episode": episode},
    }


def _camera(_left: dict, _right: dict) -> dict:
    return {
        "mean_normalised_pixel_mae": 0.01,
        "mean_pixel_correlation": 0.99,
        "mean_difference_hash_hamming_fraction": 0.01,
    }


def test_pair_inventory_separates_same_goal_noise_and_position_signal() -> None:
    contract = build_identifiability_contract()
    base = _token()
    alternate = base.copy()
    alternate[[0, 2]] += 0.05
    rows = [
        _row(1, base, 0.0),
        _row(2, base, 0.01),
        _row(3, alternate, 0.20),
    ]

    result = enumerate_identifiability_pairs(
        rows,
        action_std=np.ones(4, dtype=np.float32),
        contract=contract,
        camera_metric_fn=_camera,
    )

    assert len(result["same_goal_pairs"]) == 1
    assert len(result["different_goal_pairs"]) == 2
    assert result["different_goal_pairs"][0]["translation_bin"] == "x_plus_0p10m"
    assert result["audit"]["total_unordered_episode_pairs"] == 3
    assert result["audit"]["mechanical_state_matched"] == 3
    assert result["audit"]["camera_matched"] == 3
    assert result["audit"]["same_goal_relation"] == 1
    assert result["audit"]["position_translation_relation"] == 2


def test_variant_coverage_requires_both_target_labels_and_action_signal() -> None:
    contract = build_identifiability_contract()
    base = _token()
    alternate = base.copy()
    alternate[[0, 2]] += 0.05
    rows = [
        _row(1, base, 0.0),
        _row(2, alternate, 0.20),
    ]
    variant = {
        "variant_id": "variant",
        "source_episode_id": 3,
        "primitive_episode_id": 1,
        "base_token": base.tolist(),
        "variant_token": alternate.tolist(),
        "position_delta_m": 0.1,
    }

    result = evaluate_variant_demonstration_coverage(
        variant,
        episode_rows=rows,
        same_goal_noise_p95=0.05,
        action_std=np.ones(4, dtype=np.float32),
        contract=contract,
        camera_metric_fn=_camera,
    )

    assert result["covered"] is True
    assert result["base_demo_count"] == 1
    assert result["alternate_demo_count"] == 1
    assert result["passing_pair_count"] == 1
    assert result["base_demo_funnel"]["state_matched"] == 2
    assert result["base_demo_funnel"]["target_matched"] == 1
    assert result["alternate_demo_funnel"]["target_matched"] == 1
    rows[1]["actions"][:] = 0.0
    failed = evaluate_variant_demonstration_coverage(
        variant,
        episode_rows=rows,
        same_goal_noise_p95=0.05,
        action_std=np.ones(4, dtype=np.float32),
        contract=contract,
        camera_metric_fn=_camera,
    )
    assert failed["covered"] is False
