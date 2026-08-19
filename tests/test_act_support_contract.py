from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import yaml

from testbed.data.act_support_contract import (
    AXIS_P0005_P9995_V2,
    AXIS_P01_P99_V1,
    JOINT_REGULARIZED_MAHALANOBIS_P99_V2,
    assess_support_candidate,
    fit_registered_support_candidates,
    generate_frozen_obvious_ood,
    load_strict_source_aware_support_rows,
)
from testbed.data.hdf5_io import write_episode


def _token(dim: int, value: float) -> np.ndarray:
    return np.asarray([value + 0.01 * index for index in range(dim)], dtype=np.float32)


def _write_episode(
    path: Path,
    *,
    source_episode_id: int,
    skill_name: str,
    offset: float,
    action_loss_mask: list[int],
) -> None:
    token_key = (
        "dig_cut_tokens"
        if skill_name == "dig"
        else "return_start_envelope_tokens_v1"
    )
    token_dim = 10 if skill_name == "dig" else 18
    count = len(action_loss_mask)
    qpos = np.asarray(
        [
            [offset + 0.1 * row + 0.01 * axis for axis in range(4)]
            for row in range(count)
        ],
        dtype=np.float32,
    )
    qvel = qpos + 1.0
    token = np.stack(
        [_token(token_dim, offset + 0.1 * row) for row in range(count)], axis=0
    )
    write_episode(
        path,
        qpos=qpos,
        qvel=qvel,
        actions=np.zeros((count, 4), dtype=np.float32),
        step_ids=np.arange(100, 100 + count, dtype=np.int64),
        v2={
            "step": {
                token_key: token,
                "action_loss_mask": np.asarray(action_loss_mask, dtype=np.uint8),
            }
        },
        metadata={"source_episode_id": f"episode_{source_episode_id}"},
    )


def _write_config_and_split(
    tmp_path: Path,
    *,
    skill_name: str,
    source_by_episode: dict[int, int],
) -> Path:
    dataset_dir = tmp_path / skill_name
    dataset_dir.mkdir()
    _write_episode(
        dataset_dir / "episode_0.hdf5",
        source_episode_id=source_by_episode[0],
        skill_name=skill_name,
        offset=0.0,
        action_loss_mask=[1, 0, 1, 1],
    )
    _write_episode(
        dataset_dir / "episode_1.hdf5",
        source_episode_id=source_by_episode[1],
        skill_name=skill_name,
        offset=2.0,
        action_loss_mask=[1, 1, 0, 1],
    )
    _write_episode(
        dataset_dir / "episode_2.hdf5",
        source_episode_id=source_by_episode[2],
        skill_name=skill_name,
        offset=4.0,
        action_loss_mask=[1, 0, 1, 1],
    )
    split_path = tmp_path / f"{skill_name}_split.yaml"
    split_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "split_policy": "source_identity_exact_allowlist_v1",
                "dataset_dir": str(dataset_dir.resolve()),
                "train_ids": [0, 1],
                "val_ids": [2],
                "train_source_episode_ids": [11, 12],
                "val_source_episode_ids": [21],
                "allowed_source_episode_ids": [11, 12, 21],
                "source_episode_id_by_primitive_episode_id": {
                    0: 11,
                    1: 12,
                    2: 21,
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    token_key = (
        "dig_cut_tokens"
        if skill_name == "dig"
        else "return_start_envelope_tokens_v1"
    )
    config_path = tmp_path / f"{skill_name}_train.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "task": {"dataset_dir": str(dataset_dir.resolve())},
                "policy": {"low_dim_keys": ["qpos", "qvel", token_key]},
                "train": {"split_path": str(split_path.resolve())},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return config_path


@pytest.mark.parametrize(("skill_name", "feature_dim"), [("dig", 18), ("return", 26)])
def test_loads_source_disjoint_train_validation_rows_from_training_config(
    tmp_path: Path,
    skill_name: str,
    feature_dim: int,
) -> None:
    config_path = _write_config_and_split(
        tmp_path,
        skill_name=skill_name,
        source_by_episode={0: 11, 1: 12, 2: 21},
    )

    rows = load_strict_source_aware_support_rows(training_config_path=config_path)

    assert rows.skill_name == skill_name
    assert rows.feature_order[:8] == tuple(
        [f"qpos[{index}]" for index in range(4)]
        + [f"qvel[{index}]" for index in range(4)]
    )
    assert rows.train_features.shape == (6, feature_dim)
    assert rows.validation_features.shape == (3, feature_dim)
    assert rows.train_source_episode_ids == (11, 12)
    assert rows.validation_source_episode_ids == (21,)
    assert {item.partition for item in rows.train_provenance} == {"train"}
    assert {item.partition for item in rows.validation_provenance} == {"validation"}
    assert {item.source_episode_id for item in rows.train_provenance} == {11, 12}
    assert {item.source_episode_id for item in rows.validation_provenance} == {21}
    assert all(item.action_loss_mask == 1 for item in rows.all_provenance)
    assert not rows.train_features.flags.writeable
    assert not rows.validation_features.flags.writeable


def test_rejects_training_config_source_leakage(tmp_path: Path) -> None:
    config_path = _write_config_and_split(
        tmp_path,
        skill_name="return",
        source_by_episode={0: 21, 1: 12, 2: 11},
    )

    with pytest.raises(ValueError, match="validation source"):
        load_strict_source_aware_support_rows(training_config_path=config_path)


def test_registered_candidates_fit_strict_train_only_and_assess_validation(
    tmp_path: Path,
) -> None:
    config_path = _write_config_and_split(
        tmp_path,
        skill_name="return",
        source_by_episode={0: 11, 1: 12, 2: 21},
    )
    rows = load_strict_source_aware_support_rows(training_config_path=config_path)

    fitted = fit_registered_support_candidates(rows)

    assert tuple(fitted) == (
        AXIS_P01_P99_V1,
        AXIS_P0005_P9995_V2,
        JOINT_REGULARIZED_MAHALANOBIS_P99_V2,
    )
    assert all(candidate.fit_partition == "strict_train" for candidate in fitted.values())
    assert all(candidate.fit_row_count == rows.train_features.shape[0] for candidate in fitted.values())
    assert fitted[AXIS_P01_P99_V1].lower_quantile == pytest.approx(0.01)
    assert fitted[AXIS_P0005_P9995_V2].upper_quantile == pytest.approx(0.9995)
    assert fitted[JOINT_REGULARIZED_MAHALANOBIS_P99_V2].regularization > 0.0
    assert fitted[JOINT_REGULARIZED_MAHALANOBIS_P99_V2].threshold_kind == "train_p99_squared_distance"

    validation_assessment = assess_support_candidate(
        fitted[AXIS_P01_P99_V1], rows.validation_features
    )
    assert validation_assessment.feature_order == rows.feature_order
    assert validation_assessment.frame_in_support.shape == (3,)
    assert validation_assessment.scores.shape == (3,)
    assert len(validation_assessment.violations) == 3

    altered_validation = rows.validation_features.copy()
    altered_validation.setflags(write=True)
    altered_validation[:] = 99999.0
    altered_validation.setflags(write=False)
    altered_rows = replace(rows, validation_features=altered_validation)
    refit = fit_registered_support_candidates(altered_rows)
    for candidate_id, candidate in fitted.items():
        assert candidate.as_dict() == refit[candidate_id].as_dict()


def test_frozen_obvious_ood_is_deterministic_validation_only_and_rejected(
    tmp_path: Path,
) -> None:
    config_path = _write_config_and_split(
        tmp_path,
        skill_name="dig",
        source_by_episode={0: 11, 1: 12, 2: 21},
    )
    rows = load_strict_source_aware_support_rows(training_config_path=config_path)

    first = generate_frozen_obvious_ood(rows)
    second = generate_frozen_obvious_ood(rows)
    altered_train = rows.train_features.copy()
    altered_train.setflags(write=True)
    altered_train[:] = -99999.0
    altered_train.setflags(write=False)
    validation_only_reference = generate_frozen_obvious_ood(
        replace(rows, train_features=altered_train)
    )
    fitted = fit_registered_support_candidates(rows)

    assert first.schema == "frozen_obvious_ood_from_validation_v1"
    assert first.anchor_partition == "validation"
    assert first.multiplier == pytest.approx(32.0)
    np.testing.assert_array_equal(first.features, second.features)
    np.testing.assert_array_equal(first.features, validation_only_reference.features)
    np.testing.assert_array_equal(first.anchor_features, rows.validation_features)
    assert first.anchor_provenance == rows.validation_provenance
    assert all(item.partition == "validation" for item in first.anchor_provenance)
    assert np.all(np.abs(first.perturbation) >= 32.0)
    assert not first.features.flags.writeable

    for candidate in fitted.values():
        assessment = assess_support_candidate(candidate, first.features)
        assert not np.any(assessment.frame_in_support)
