from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from testbed.data.terrain_cycle_cleaning import (
    APPROVED_TERRAIN_DATASET_ROOT,
    TerrainCycleCleaningConfig,
    analyze_episode_cleaning,
    resolve_approved_episode_paths,
    validate_source_root,
)


def _cycle_payload(starts: list[int], ends: list[int]) -> dict[str, np.ndarray]:
    count = len(starts)
    return {
        "cycle_id": np.arange(count, dtype=np.int32),
        "start_step": np.asarray(starts, dtype=np.int32),
        "dump_end_step": np.asarray([end - 2 for end in ends], dtype=np.int32),
        "end_step": np.asarray([end - 1 for end in ends], dtype=np.int32),
        "fill_peak_kg": np.full(count, 100.0, dtype=np.float32),
        "deposit_delta_kg": np.full(count, 50.0, dtype=np.float32),
    }


def test_source_root_is_a_hard_allowlist(tmp_path: Path) -> None:
    approved = tmp_path / "approved"
    other = tmp_path / "other"
    approved.mkdir()
    other.mkdir()

    assert validate_source_root(approved, approved_root=approved) == approved.resolve()
    with pytest.raises(ValueError, match="approved dataset root"):
        validate_source_root(other, approved_root=approved)


def test_expected_episode_inventory_must_be_exact(tmp_path: Path) -> None:
    for episode_id in range(3):
        (tmp_path / f"episode_{episode_id}.hdf5").touch()

    paths = resolve_approved_episode_paths(
        tmp_path,
        approved_root=tmp_path,
        expected_episode_count=3,
    )
    assert [path.name for path in paths] == [
        "episode_0.hdf5",
        "episode_1.hdf5",
        "episode_2.hdf5",
    ]

    (tmp_path / "episode_3.hdf5").touch()
    with pytest.raises(ValueError, match="exact episode inventory"):
        resolve_approved_episode_paths(
            tmp_path,
            approved_root=tmp_path,
            expected_episode_count=3,
        )


def test_episode_realpath_must_stay_inside_approved_root(tmp_path: Path) -> None:
    approved = tmp_path / "approved"
    outside = tmp_path / "outside.hdf5"
    approved.mkdir()
    outside.touch()
    (approved / "episode_0.hdf5").symlink_to(outside)

    with pytest.raises(ValueError, match="outside approved dataset root"):
        resolve_approved_episode_paths(
            approved,
            approved_root=approved,
            expected_episode_count=1,
        )


def test_pause_policy_uses_elapsed_timestamps_and_separates_review_from_long_pause() -> None:
    steps = 12
    actions = np.ones((steps, 4), dtype=np.float32)
    actions[1:4] = 0.0  # [1s, 4s) => 3 second active-stage review pause.
    actions[6:11] = 0.0  # [6s, 11s) => 5 second auto-mask pause.
    step_ns = np.arange(steps, dtype=np.int64) * 1_000_000_000
    cycle_id = np.asarray([0] * 6 + [1] * 6, dtype=np.int32)
    work_stage_id = np.ones(steps, dtype=np.uint8)

    result = analyze_episode_cleaning(
        episode_id=28,
        actions=actions,
        qpos=np.zeros((steps, 4), dtype=np.float32),
        qvel=np.zeros((steps, 4), dtype=np.float32),
        step_ids=np.arange(steps, dtype=np.int64),
        step_ns=step_ns,
        v2_step={"cycle_id": cycle_id, "work_stage_id": work_stage_id},
        v2_cycle=_cycle_payload([0, 6], [6, 12]),
        camera_step_valid_mask=np.ones(steps, dtype=np.uint8),
        config=TerrainCycleCleaningConfig(guard_s=0.0, timestamp_gap_s=2.0),
    )

    reasons = {window["reason"] for window in result.windows}
    assert {"pause_review_active_stage", "long_pause"} <= reasons
    windows = {window["reason"]: window for window in result.windows}
    assert windows["pause_review_active_stage"]["work_stage_ids"] == [1]
    assert windows["pause_review_active_stage"]["work_stage_scope"] == "active"
    assert windows["pause_review_active_stage"]["treatment_decision"] == (
        "cycle_review_and_default_pool_exclusion"
    )
    assert windows["long_pause"]["treatment_decision"] == (
        "local_action_loss_mask_only"
    )
    assert result.cycles[0]["review_required"] is True
    assert result.cycles[0]["replay_candidate"] is False
    assert result.cycles[0]["effect_calibration_eligible"] is False
    assert result.cycles[1]["review_required"] is False
    np.testing.assert_array_equal(result.action_loss_mask[1:4], np.ones(3, dtype=np.uint8))
    np.testing.assert_array_equal(result.action_loss_mask[6:11], np.zeros(5, dtype=np.uint8))
    np.testing.assert_array_equal(result.default_action_loss_mask[:6], np.zeros(6, dtype=np.uint8))
    assert int(result.default_action_loss_mask[11]) == 1


def test_dynamic_jump_rejects_only_the_containing_cycle() -> None:
    steps = 90
    qpos = np.zeros((steps, 4), dtype=np.float32)
    qpos[45:, 2] = 0.08
    cycle_id = np.repeat(np.arange(3, dtype=np.int32), 30)

    result = analyze_episode_cleaning(
        episode_id=30,
        actions=np.ones((steps, 4), dtype=np.float32),
        qpos=qpos,
        qvel=np.zeros((steps, 4), dtype=np.float32),
        step_ids=np.arange(steps, dtype=np.int64),
        step_ns=np.arange(steps, dtype=np.int64) * 100_000_000,
        v2_step={"cycle_id": cycle_id, "work_stage_id": np.ones(steps, dtype=np.uint8)},
        v2_cycle=_cycle_payload([0, 30, 60], [30, 60, 90]),
        camera_step_valid_mask=np.ones(steps, dtype=np.uint8),
        config=TerrainCycleCleaningConfig(),
    )

    assert result.cycles[0]["replay_candidate"] is True
    assert result.cycles[1]["replay_candidate"] is False
    assert result.cycles[2]["replay_candidate"] is True
    assert "qpos_jump" in result.cycles[1]["reason_codes"]
    np.testing.assert_array_equal(
        result.default_action_loss_mask[30:60],
        np.zeros(30, dtype=np.uint8),
    )


def test_invalid_deposit_fraction_does_not_reject_terrain_replay() -> None:
    steps = 10
    cycle = _cycle_payload([0], [10])
    cycle["deposit_delta_kg"][:] = 110.0

    result = analyze_episode_cleaning(
        episode_id=28,
        actions=np.ones((steps, 4), dtype=np.float32),
        qpos=np.zeros((steps, 4), dtype=np.float32),
        qvel=np.zeros((steps, 4), dtype=np.float32),
        step_ids=np.arange(steps, dtype=np.int64),
        step_ns=np.arange(steps, dtype=np.int64) * 20_000_000,
        v2_step={
            "cycle_id": np.zeros(steps, dtype=np.int32),
            "work_stage_id": np.ones(steps, dtype=np.uint8),
        },
        v2_cycle=cycle,
        camera_step_valid_mask=np.ones(steps, dtype=np.uint8),
    )

    assert result.cycles[0]["deposit_label_valid"] is False
    assert result.cycles[0]["replay_candidate"] is True
    assert result.cycles[0]["effect_calibration_eligible"] is True


def test_any_nonfinite_numeric_row_makes_episode_diagnostic_only() -> None:
    steps = 12
    qvel = np.zeros((steps, 4), dtype=np.float32)
    qvel[4, 1] = np.nan

    result = analyze_episode_cleaning(
        episode_id=28,
        actions=np.ones((steps, 4), dtype=np.float32),
        qpos=np.zeros((steps, 4), dtype=np.float32),
        qvel=qvel,
        step_ids=np.arange(steps, dtype=np.int64),
        step_ns=np.arange(steps, dtype=np.int64) * 20_000_000,
        v2_step={
            "cycle_id": np.zeros(steps, dtype=np.int32),
            "work_stage_id": np.ones(steps, dtype=np.uint8),
        },
        v2_cycle=_cycle_payload([0], [12]),
        camera_step_valid_mask=np.ones(steps, dtype=np.uint8),
    )

    assert result.episode_role == "diagnostic_only"
    assert result.diagnostics["nonfinite_numeric_present"] is True
    assert result.cycles[0]["diagnostic_only"] is True
    assert result.cycles[0]["replay_candidate"] is False
    np.testing.assert_array_equal(
        result.default_action_loss_mask,
        np.zeros(steps, dtype=np.uint8),
    )


def test_approved_dataset_constant_points_only_at_new_batch() -> None:
    assert APPROVED_TERRAIN_DATASET_ROOT.name.endswith("20260717")
