from __future__ import annotations

from pathlib import Path

import pytest

from testbed.runtime.eval_output_paths import (
    assert_eval_output_paths_available,
)


def test_no_overwrite_accepts_fresh_eval_output_paths(tmp_path: Path) -> None:
    root = tmp_path / "functional-a0"

    assert_eval_output_paths_available(
        enabled=True,
        results_dir=root / "results",
        video_dir=root / "videos",
        rollout_log_dir=root / "results/rollouts",
        hdf5_dir=root / "results/hdf5_rollouts",
        save_video=True,
        save_rollout_logs=True,
        record_hdf5=True,
    )


def test_no_overwrite_fails_before_reusing_any_material_output(
    tmp_path: Path,
) -> None:
    existing = tmp_path / "functional-a0/results"
    existing.mkdir(parents=True)

    with pytest.raises(FileExistsError, match="eval output already exists"):
        assert_eval_output_paths_available(
            enabled=True,
            results_dir=existing,
            video_dir=tmp_path / "functional-a0/videos",
            rollout_log_dir=existing / "rollouts",
            hdf5_dir=existing / "hdf5_rollouts",
            save_video=True,
            save_rollout_logs=True,
            record_hdf5=True,
        )


def test_legacy_eval_can_explicitly_leave_no_overwrite_disabled(
    tmp_path: Path,
) -> None:
    existing = tmp_path / "legacy/results"
    existing.mkdir(parents=True)

    assert_eval_output_paths_available(
        enabled=False,
        results_dir=existing,
        video_dir=tmp_path / "legacy/videos",
        rollout_log_dir=existing / "rollouts",
        hdf5_dir=existing / "hdf5_rollouts",
        save_video=True,
        save_rollout_logs=True,
        record_hdf5=True,
    )
