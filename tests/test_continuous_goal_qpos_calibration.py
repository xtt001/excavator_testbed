from __future__ import annotations

import numpy as np
import pytest

from testbed.eval.continuous_goal_qpos_calibration import (
    CONFORMAL_COVERAGE_LEVEL,
    CONFORMAL_HELDOUT_SAMPLE_COUNT,
    CONFORMAL_HELDOUT_SOURCE_COUNTS,
    CONFORMAL_HELDOUT_SOURCE_IDS,
    CalibrationContractError,
    FeatureNormalization,
    build_source_grouped_folds,
    fit_conformal_qpos_calibration,
    fit_loso_ood_calibration,
)


def test_source_grouped_folds_reserve_33_34_and_never_leak_sources() -> None:
    source_ids = [0, 0, 1, 2, 3, 4, 5, 33, 33, 34]

    folds = build_source_grouped_folds(source_ids)

    assert len(folds) == 5
    assert set().union(*(set(f.validation_source_ids) for f in folds)) == {
        0,
        1,
        2,
        3,
        4,
        5,
    }
    for fold in folds:
        assert not (set(fold.train_source_ids) & set(fold.validation_source_ids))
        assert not (set(fold.train_source_ids) & set(CONFORMAL_HELDOUT_SOURCE_IDS))
        assert not (set(fold.validation_source_ids) & set(CONFORMAL_HELDOUT_SOURCE_IDS))


def test_feature_normalization_and_loso_p99_use_training_sources_only() -> None:
    features = np.asarray(
        [
            [0.0, 0.0],
            [0.1, 0.0],
            [1.0, 1.0],
            [1.1, 1.0],
            [2.0, 2.0],
            [2.1, 2.0],
        ]
    )
    source_ids = np.asarray([0, 0, 1, 1, 2, 2])
    normalization = FeatureNormalization.fit(
        features,
        feature_names=("x", "y"),
    )

    calibration = fit_loso_ood_calibration(
        features=features,
        source_ids=source_ids,
        normalization=normalization,
    )

    assert calibration.threshold_rule == "leave_one_source_out_p99"
    assert calibration.threshold > 0.0
    assert calibration.training_sample_count == 6
    assert calibration.loso_distance_samples.shape == (6,)
    assert calibration.threshold == pytest.approx(
        np.quantile(
            calibration.loso_distance_samples,
            0.99,
            method="higher",
        )
    )
    assert calibration.score(features[0], normalization=normalization) <= (
        calibration.threshold
    )
    assert (
        calibration.score(
            np.asarray([100.0, 100.0]),
            normalization=normalization,
        )
        > calibration.threshold
    )
    assert len(calibration.lineage_sha256) == 64


def test_conformal_calibration_locks_true_59_sample_split_and_is_64x4() -> None:
    residuals = np.arange(
        CONFORMAL_HELDOUT_SAMPLE_COUNT,
        dtype=np.float64,
    )[:, None, None]
    residuals = np.broadcast_to(residuals / 100.0, (59, 64, 4)).copy()
    source_ids = [33] * 29 + [34] * 30

    calibration = fit_conformal_qpos_calibration(
        absolute_residuals=residuals,
        source_ids=source_ids,
    )

    assert calibration.coverage_level == CONFORMAL_COVERAGE_LEVEL == 0.95
    assert calibration.absolute_error_bound.shape == (64, 4)
    assert calibration.absolute_error_bound == pytest.approx(0.56)
    assert calibration.source_ids == CONFORMAL_HELDOUT_SOURCE_IDS
    assert calibration.source_sample_counts == (CONFORMAL_HELDOUT_SOURCE_COUNTS)
    assert calibration.calibration_sample_count == 59
    assert len(calibration.lineage_sha256) == 64


@pytest.mark.parametrize(
    ("source_ids", "sample_count"),
    [
        ([33] * 28 + [34] * 31, 59),
        ([33] * 29 + [34] * 29, 58),
    ],
)
def test_conformal_calibration_rejects_count_drift(
    source_ids: list[int],
    sample_count: int,
) -> None:
    with pytest.raises(CalibrationContractError, match="29.*30|59"):
        fit_conformal_qpos_calibration(
            absolute_residuals=np.zeros((sample_count, 64, 4)),
            source_ids=source_ids,
        )


@pytest.mark.parametrize("invalid_fold_count", [True, 5.0])
def test_grouped_fold_count_rejects_bool_and_non_integer(
    invalid_fold_count: object,
) -> None:
    with pytest.raises(CalibrationContractError, match="five source folds"):
        build_source_grouped_folds(
            [0, 1, 2, 3, 4, 33, 34],
            fold_count=invalid_fold_count,
        )
