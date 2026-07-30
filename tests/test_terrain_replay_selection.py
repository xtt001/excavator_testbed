from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np
import pytest

from testbed.data.hdf5_io import write_episode
from testbed.eval.terrain_grid_volume import compute_grid_volume_change
from testbed.eval.terrain_replay_selection import (
    CALIBRATED_MIXED_SELECTION_PROFILE,
    ReplayEpisodeSelection,
    ReplaySelectionProfile,
    load_replay_selection,
    validate_control_compatibility_selection,
    validate_replay_evidence_profile,
)


def test_corrected_evidence_profile_locks_the_approved_realign_contract() -> None:
    kwargs = {
        "evidence_profile": "replay_corrected_partial_salvage_v1",
        "selection_manifest_present": True,
        "selection_profile": CALIBRATED_MIXED_SELECTION_PROFILE,
        "realign_on_qpos_error": True,
        "selected_episode_count": 1,
        "record_output_present": True,
        "diagnostic_log_present": True,
        "gold_cycle_samples_present": True,
        "realign_axis": "all",
        "realign_error_threshold": 0.04,
        "realign_hold_steps": 3,
        "realign_min_steps_between": 200,
        "realign_burn_in_steps": 15,
        "realign_max_count": 20,
    }

    assert validate_replay_evidence_profile(**kwargs) == []
    assert "threshold" in validate_replay_evidence_profile(
        **{**kwargs, "realign_error_threshold": 0.03}
    )[0]
    assert "three-target" in validate_replay_evidence_profile(
        **{**kwargs, "gold_cycle_samples_present": False}
    )[0]


def test_selection_groups_cycles_and_keeps_full_causal_prefix(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    episode = source_root / "episode_28.hdf5"
    episode.touch()
    manifest = tmp_path / "cycle_eligibility.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "terrain_cycle_eligibility_v1",
                "approved_source_root": str(source_root.resolve()),
                "cycles": [
                    {
                        "source_episode_id": "episode_28",
                        "source_path": str(episode.resolve()),
                        "cycle_id": 3,
                        "end_step_exclusive": 80,
                        "replay_candidate": True,
                        "controller_epoch": "post_fix_candidate",
                    },
                    {
                        "source_episode_id": "episode_28",
                        "source_path": str(episode.resolve()),
                        "cycle_id": 5,
                        "end_step_exclusive": 120,
                        "replay_candidate": True,
                        "controller_epoch": "post_fix_candidate",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    selection = load_replay_selection(
        manifest,
        approved_source_root=source_root,
    )

    assert len(selection) == 1
    assert selection[0].start_step == 0
    assert selection[0].end_step_exclusive == 120
    assert selection[0].cycle_ids == (3, 5)


def test_selection_rejects_source_outside_allowlist(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    other_root = tmp_path / "other"
    source_root.mkdir()
    other_root.mkdir()
    episode = other_root / "episode_28.hdf5"
    episode.touch()
    manifest = tmp_path / "cycles.json"
    manifest.write_text(
        json.dumps(
            {
                "cycles": [
                    {
                        "source_episode_id": "episode_28",
                        "source_path": str(episode),
                        "cycle_id": 0,
                        "end_step_exclusive": 10,
                        "replay_candidate": True,
                        "controller_epoch": "post_fix_candidate",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="outside approved source root"):
        load_replay_selection(manifest, approved_source_root=source_root)

    with pytest.raises(ValueError, match="outside approved source root"):
        load_replay_selection(
            manifest,
            approved_source_root=source_root,
            included_episode_ids=("episode_29",),
        )


def test_selection_accepts_cleaning_jsonl_manifest(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    episode = source_root / "episode_28.hdf5"
    episode.touch()
    manifest = tmp_path / "post_fix_replay_selection.jsonl"
    rows = [
        {
            "source_episode_id": "episode_28",
            "source_path": str(episode.resolve()),
            "cycle_id": cycle_id,
            "end_step_exclusive": end,
            "replay_candidate": True,
            "controller_epoch": "post_fix_candidate",
        }
        for cycle_id, end in ((1, 40), (2, 90))
    ]
    manifest.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    selection = load_replay_selection(
        manifest,
        approved_source_root=source_root,
    )

    assert len(selection) == 1
    assert selection[0].start_step == 0
    assert selection[0].end_step_exclusive == 90


def test_selection_can_include_an_explicit_episode_subset(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    episode_28 = source_root / "episode_28.hdf5"
    episode_29 = source_root / "episode_29.hdf5"
    episode_28.touch()
    episode_29.touch()
    manifest = tmp_path / "post_fix_replay_selection.jsonl"
    rows = [
        {
            "source_episode_id": episode.stem,
            "source_path": str(episode.resolve()),
            "cycle_id": 0,
            "end_step_exclusive": 10,
            "replay_candidate": True,
            "controller_epoch": "post_fix_candidate",
        }
        for episode in (episode_28, episode_29)
    ]
    manifest.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    selection = load_replay_selection(
        manifest,
        approved_source_root=source_root,
        included_episode_ids=("episode_29",),
    )

    assert [item.source_episode_id for item in selection] == ["episode_29"]


def test_calibrated_profile_accepts_pre_and_post_and_checks_action_contract(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "calibrated"
    source_root.mkdir()
    actions = np.zeros((12, 4), dtype=np.float32)
    for episode_id in (1, 23):
        write_episode(
            source_root / f"episode_{episode_id}.hdf5",
            qpos=np.zeros_like(actions),
            qvel=np.zeros_like(actions),
            actions=actions,
            metadata={
                "action_contract": "current_equivalent_v1",
                "raw_source_realpath": str(
                    tmp_path / "raw" / f"episode_{episode_id}.hdf5"
                ),
            },
        )
    manifest = tmp_path / "selection.jsonl"
    manifest.write_text(
        "".join(
            json.dumps(
                {
                    "source_episode_id": f"episode_{episode_id}",
                    "source_path": str(
                        (source_root / f"episode_{episode_id}.hdf5").resolve()
                    ),
                    "cycle_id": 0,
                    "end_step_exclusive": 10,
                    "replay_candidate": True,
                    "controller_epoch": epoch,
                }
            )
            + "\n"
            for episode_id, epoch in (
                (1, "pre_fix_candidate"),
                (23, "post_fix_candidate"),
            )
        ),
        encoding="utf-8",
    )
    profile = ReplaySelectionProfile(
        name="test_calibrated",
        approved_source_root=source_root,
        allowed_controller_epochs=("pre_fix_candidate", "post_fix_candidate"),
        expected_episode_ids=(1, 23),
        required_action_contract="current_equivalent_v1",
    )

    selection = load_replay_selection(manifest, selection_profile=profile)

    assert [item.source_episode_id for item in selection] == [
        "episode_1",
        "episode_23",
    ]

    with h5py.File(source_root / "episode_1.hdf5", "a") as handle:
        handle["metadata"].attrs["action_contract"] = "wrong_contract"
    with pytest.raises(ValueError, match="action contract"):
        load_replay_selection(manifest, selection_profile=profile)


def test_calibrated_profile_rejects_episode_outside_fixed_inventory(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "calibrated"
    source_root.mkdir()
    episode = source_root / "episode_9.hdf5"
    episode.touch()
    manifest = tmp_path / "selection.jsonl"
    manifest.write_text(
        json.dumps(
            {
                "source_episode_id": "episode_9",
                "source_path": str(episode.resolve()),
                "cycle_id": 0,
                "end_step_exclusive": 10,
                "replay_candidate": True,
                "controller_epoch": "pre_fix_candidate",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    profile = ReplaySelectionProfile(
        name="test_calibrated",
        approved_source_root=source_root,
        allowed_controller_epochs=("pre_fix_candidate", "post_fix_candidate"),
        expected_episode_ids=(1, 23),
        required_action_contract="current_equivalent_v1",
    )

    with pytest.raises(ValueError, match="outside fixed episode inventory"):
        load_replay_selection(manifest, selection_profile=profile)


def test_recording_control_compatibility_is_limited_to_calibrated_pre_sources(
    tmp_path: Path,
) -> None:
    pre = ReplayEpisodeSelection(
        source_episode_id="episode_19",
        source_path=tmp_path / "episode_19.hdf5",
        start_step=0,
        end_step_exclusive=20,
        cycle_ids=(0,),
    )
    post = ReplayEpisodeSelection(
        source_episode_id="episode_23",
        source_path=tmp_path / "episode_23.hdf5",
        start_step=0,
        end_step_exclusive=20,
        cycle_ids=(0,),
    )

    assert validate_control_compatibility_selection(
        control_profile="recording_pre_fix_v1",
        selection_profile=CALIBRATED_MIXED_SELECTION_PROFILE,
        selections=[pre],
    ) == []
    assert "pre-calibration" in validate_control_compatibility_selection(
        control_profile="recording_pre_fix_v1",
        selection_profile=CALIBRATED_MIXED_SELECTION_PROFILE,
        selections=[post],
    )[0]
    assert "calibrated_mixed_current_equivalent" in (
        validate_control_compatibility_selection(
            control_profile="recording_pre_fix_v1",
            selection_profile="post_fix_raw",
            selections=[pre],
        )[0]
    )


def test_grid_volume_keeps_removed_and_refill_separate() -> None:
    result = compute_grid_volume_change(
        start_removed_depth_m=[0.1, 0.2, 0.0],
        end_removed_depth_m=[0.3, 0.1, 0.4],
        cell_area_m2=0.5,
        valid_mask=[1.0, 1.0, 0.0],
    )

    np.testing.assert_allclose(result["signed_depth_delta_m"], [0.2, -0.1, 0.4])
    assert result["removed_volume_m3"] == pytest.approx(0.1)
    assert result["refill_volume_m3"] == pytest.approx(0.05)
    assert result["volume_label_status"] == "derived_grid_integral"
    assert result["direct_volume_status"] == "unavailable_no_sensor"


def test_grid_volume_accepts_exactly_half_valid_sampling_fraction() -> None:
    result = compute_grid_volume_change(
        start_removed_depth_m=[0.0, 0.0],
        end_removed_depth_m=[0.2, 0.2],
        cell_area_m2=1.0,
        valid_mask=[0.5, 0.49],
    )

    assert result["removed_volume_by_cell_m3"] == pytest.approx([0.2, 0.0])
    assert result["removed_volume_m3"] == pytest.approx(0.2)
