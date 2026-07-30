from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pytest

from testbed.data.action_loss_mask import (
    ACTION_LOSS_MASK_SCOPE_LOSS_ONLY,
    ACTION_LOSS_MASK_SCOPE_LOSS_SAMPLING_STATS,
    select_sample_start_index,
)
from testbed.data.dataset import get_norm_stats


def _write_episode(path: Path, *, mask: np.ndarray | None) -> None:
    qpos = np.asarray([[0.0], [10.0], [2.0], [20.0]], dtype=np.float32)
    qvel = np.zeros_like(qpos)
    action = np.asarray([[1.0], [100.0], [3.0], [200.0]], dtype=np.float32)
    with h5py.File(path, "w") as handle:
        observations = handle.create_group("observations")
        observations.create_dataset("qpos", data=qpos)
        observations.create_dataset("qvel", data=qvel)
        handle.create_dataset("action", data=action)
        if mask is not None:
            step = handle.create_group("v2").create_group("step")
            step.create_dataset("action_loss_mask", data=np.asarray(mask, dtype=np.uint8))


def test_loss_sampling_stats_filters_action_and_proprio_rows(tmp_path: Path) -> None:
    _write_episode(tmp_path / "episode_0.hdf5", mask=np.asarray([1, 0, 1, 0]))

    legacy = get_norm_stats(
        tmp_path,
        1,
        action_loss_mask_scope=ACTION_LOSS_MASK_SCOPE_LOSS_ONLY,
    )
    clean = get_norm_stats(
        tmp_path,
        1,
        action_loss_mask_scope=ACTION_LOSS_MASK_SCOPE_LOSS_SAMPLING_STATS,
    )

    assert float(np.asarray(legacy["action_mean"]).reshape(-1)[0]) == pytest.approx(76.0)
    assert float(np.asarray(clean["action_mean"]).reshape(-1)[0]) == pytest.approx(2.0)
    assert float(np.asarray(clean["proprio_mean"]).reshape(-1)[0]) == pytest.approx(1.0)


def test_loss_sampling_stats_requires_mask(tmp_path: Path) -> None:
    _write_episode(tmp_path / "episode_0.hdf5", mask=None)

    with pytest.raises(ValueError, match="action_loss_mask"):
        get_norm_stats(
            tmp_path,
            1,
            action_loss_mask_scope=ACTION_LOSS_MASK_SCOPE_LOSS_SAMPLING_STATS,
        )


def test_loss_only_keeps_legacy_stats_behavior_for_nonbinary_mask(tmp_path: Path) -> None:
    _write_episode(tmp_path / "episode_0.hdf5", mask=np.asarray([2, 2, 2, 2]))

    legacy = get_norm_stats(
        tmp_path,
        1,
        action_loss_mask_scope=ACTION_LOSS_MASK_SCOPE_LOSS_ONLY,
    )

    assert float(np.asarray(legacy["action_mean"]).reshape(-1)[0]) == pytest.approx(
        76.0
    )
    with pytest.raises(ValueError, match="only 0 or 1"):
        get_norm_stats(
            tmp_path,
            1,
            action_loss_mask_scope=ACTION_LOSS_MASK_SCOPE_LOSS_SAMPLING_STATS,
        )


def test_clean_sampling_selects_only_masked_in_indices() -> None:
    observed: list[np.ndarray] = []

    def choose(values: np.ndarray) -> int:
        observed.append(np.asarray(values))
        return int(values[-1])

    selected = select_sample_start_index(
        episode_length=5,
        action_loss_mask=np.asarray([0, 1, 0, 1, 0], dtype=np.uint8),
        scope=ACTION_LOSS_MASK_SCOPE_LOSS_SAMPLING_STATS,
        choice_fn=choose,
    )

    assert selected == 3
    np.testing.assert_array_equal(observed[0], np.asarray([1, 3]))


def test_clean_sampling_rejects_all_zero_mask() -> None:
    with pytest.raises(ValueError, match="no valid sample start"):
        select_sample_start_index(
            episode_length=3,
            action_loss_mask=np.zeros(3, dtype=np.uint8),
            scope=ACTION_LOSS_MASK_SCOPE_LOSS_SAMPLING_STATS,
        )
