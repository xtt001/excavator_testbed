from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import yaml

from testbed.data.dig_support_outlier_distribution import (
    DigSupportOutlierDistributionError,
    analyze_dig_support_outlier_segment,
    load_dig_support_outlier_distribution_references,
)
from testbed.data.hdf5_io import write_episode


def _write_primitive_episode(
    path: Path,
    *,
    source_episode_id: int,
    qvel1: list[float],
    token_offset: float = 0.0,
    action_loss_mask: list[int] | None = None,
) -> None:
    count = len(qvel1)
    qpos = np.asarray(
        [[0.1 * row + 0.01 * axis for axis in range(4)] for row in range(count)],
        dtype=np.float32,
    )
    qvel = np.asarray(
        [[0.2 * row + 0.01 * axis for axis in range(4)] for row in range(count)],
        dtype=np.float32,
    )
    qvel[:, 1] = np.asarray(qvel1, dtype=np.float32)
    v2_step: dict[str, np.ndarray] = {
        "dig_cut_tokens": np.asarray(
            [
                [token_offset + row + 0.01 * axis for axis in range(10)]
                for row in range(count)
            ],
            dtype=np.float32,
        )
    }
    if action_loss_mask is not None:
        v2_step["action_loss_mask"] = np.asarray(action_loss_mask, dtype=np.uint8)
    write_episode(
        path,
        qpos=qpos,
        qvel=qvel,
        actions=np.zeros((count, 4), dtype=np.float32),
        step_ids=np.arange(100, 100 + count, dtype=np.int64),
        v2={"step": v2_step},
        metadata={"source_episode_id": f"episode_{source_episode_id}"},
    )


def _write_fixture_config(tmp_path: Path) -> Path:
    root = tmp_path / "primitive_data"
    dig_dir = root / "dig"
    dig_dir.mkdir(parents=True)
    _write_primitive_episode(
        dig_dir / "episode_0.hdf5",
        source_episode_id=10,
        qvel1=[-1.0, -0.5, 0.0, 0.5],
        action_loss_mask=[1, 0, 1, 1],
    )
    _write_primitive_episode(
        dig_dir / "episode_1.hdf5",
        source_episode_id=20,
        qvel1=[-0.8, 0.2, 0.8],
        token_offset=10.0,
        action_loss_mask=[1, 1, 1],
    )
    _write_primitive_episode(
        dig_dir / "episode_2.hdf5",
        source_episode_id=30,
        qvel1=[1.25, 1.5],
        token_offset=20.0,
        action_loss_mask=[1, 1],
    )
    for primitive, qvel1 in {
        "return": [1.1, 1.3],
        "carry": [1.4],
        "dump": [1.6],
    }.items():
        directory = root / primitive
        directory.mkdir()
        _write_primitive_episode(
            directory / "episode_0.hdf5",
            source_episode_id=40,
            qvel1=qvel1,
            action_loss_mask=[1] * len(qvel1),
        )

    split_path = tmp_path / "dig_split.yaml"
    split_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "split_policy": "source_identity_exact_allowlist_v1",
                "dataset_dir": str(dig_dir.resolve()),
                "available_episode_ids": [0, 1, 2],
                "train_ids": [0],
                "val_ids": [1],
                "train_source_episode_ids": [10],
                "val_source_episode_ids": [20],
                "allowed_source_episode_ids": [10, 20],
                "excluded_training_tier_episode_ids": [2],
                "source_episode_id_by_primitive_episode_id": {
                    0: 10,
                    1: 20,
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    config_path = tmp_path / "dig_train.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "task": {"dataset_dir": str(dig_dir.resolve())},
                "policy": {"low_dim_keys": ["qpos", "qvel", "dig_cut_tokens"]},
                "train": {"split_path": str(split_path.resolve())},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return config_path


def _frozen_target(
    references: object,
) -> np.ndarray:
    train = np.asarray(references.strict_rows.train_features, dtype=np.float64)  # type: ignore[attr-defined]
    support = references.v1_support  # type: ignore[attr-defined]
    target = np.stack((train[0], train[2], train[2]), axis=0)
    target[:, 5] = np.asarray(
        [
            float(support.p99[5]) + 0.20,
            float(support.p99[5]) + 0.40,
            float(support.p99[5]) - 0.05,
        ],
        dtype=np.float64,
    )
    target.setflags(write=False)
    return target


def test_builds_strict_v1_reference_and_reports_per_frame_distribution_evidence(
    tmp_path: Path,
) -> None:
    config = _write_fixture_config(tmp_path)
    references = load_dig_support_outlier_distribution_references(
        training_config_path=config
    )
    target = _frozen_target(references)

    result = analyze_dig_support_outlier_segment(
        references=references,
        target_features=target,
    )
    payload = result.as_dict()

    assert payload["target_rollout_used_for_fit_or_selection"] is False
    assert payload["runtime_support_change"] is False
    assert payload["candidate_selection_performed"] is False
    assert payload["v1_support"]["candidate_id"] == "axis_p01_p99_v1"
    assert payload["v1_support"]["fit_partition"] == "strict_train"
    assert len(payload["frames"]) == 3
    assert payload["frames"][0]["qpos"] == pytest.approx(target[0, :4])
    assert payload["frames"][0]["qvel"] == pytest.approx(target[0, 4:8])
    assert payload["frames"][0]["token"] == pytest.approx(target[0, 8:])
    assert payload["frames"][0]["qvel1_v1_status"] == "above_p99"
    assert payload["frames"][0]["nearest_strict_train"]["qvel1_abs_delta"] >= 0.0
    assert (
        payload["frames"][0]["nearest_strict_train"]
        ["full_feature_v1_span_normalised_l2"]
        >= 0.0
    )

    topology = payload["segment_qvel1_excursion_measurement"]
    assert topology["qvel1_v1_outside_frame_indices"] == [0, 1]
    assert topology["qvel1_v1_outside_frame_count"] == 2
    assert topology["qvel1_v1_longest_contiguous_run"] == 2
    assert topology["v1_excursion_topology"] == "one_contiguous_multi_frame_run"
    assert topology["target_qvel1_max_abs_adjacent_delta"] >= 0.0

    populations = payload["qvel1_same_numeric_range_populations"]
    assert populations["strict_train_action_loss_mask_1"]["row_count"] == 3
    assert populations["held_validation_action_loss_mask_1"]["row_count"] == 3
    assert populations["strict_train_action_loss_mask_0"]["row_count"] == 1
    assert populations["excluded_dig_primitive_episode"]["row_count"] == 2
    assert populations["other_primitive:return"]["row_count"] == 2
    assert populations["other_primitive:carry"]["row_count"] == 1
    assert populations["other_primitive:dump"]["row_count"] == 1
    assert populations["strict_train_action_loss_mask_1"]["examples"]
    outside_populations = payload["qvel1_v1_outside_numeric_range_populations"]
    assert (
        outside_populations["strict_train_action_loss_mask_1"]
        ["target_qvel1_interval"]["lower"]
        > payload["v1_support"]["p99"][5]
    )
    assert outside_populations["strict_train_action_loss_mask_1"]["row_count"] == 3

    validation = payload["held_validation_distribution"]
    assert validation["partition"] == "held_validation"
    assert validation["row_count"] == 3
    assert validation["source_episode_ids"] == [20]
    assert validation["used_for_fit_or_selection"] is False


def test_requires_a_readonly_target_matrix_and_never_mutates_reference_bounds(
    tmp_path: Path,
) -> None:
    config = _write_fixture_config(tmp_path)
    references = load_dig_support_outlier_distribution_references(
        training_config_path=config
    )
    mutable = np.asarray(
        references.strict_rows.train_features[:2], dtype=np.float64
    ).copy()
    original_p01 = np.asarray(references.v1_support.p01).copy()
    original_p99 = np.asarray(references.v1_support.p99).copy()

    with pytest.raises(DigSupportOutlierDistributionError, match="read-only"):
        analyze_dig_support_outlier_segment(
            references=references,
            target_features=mutable,
        )

    target = _frozen_target(references)
    analyze_dig_support_outlier_segment(
        references=references,
        target_features=target,
    )
    np.testing.assert_array_equal(references.v1_support.p01, original_p01)
    np.testing.assert_array_equal(references.v1_support.p99, original_p99)
    assert not references.strict_rows.train_features.flags.writeable
    assert not references.strict_rows.validation_features.flags.writeable


def test_loader_keeps_masked_validation_and_excluded_sets_separate(
    tmp_path: Path,
) -> None:
    config = _write_fixture_config(tmp_path)
    references = load_dig_support_outlier_distribution_references(
        training_config_path=config
    )

    assert references.strict_train_masked_qvel1.row_count == 1
    assert references.excluded_dig_primitive_qvel1.row_count == 2
    assert references.excluded_dig_primitive_missing_episode_ids == ()
    assert {
        population.name for population in references.other_primitive_qvel1
    } == {
        "other_primitive:carry",
        "other_primitive:dump",
        "other_primitive:return",
    }
