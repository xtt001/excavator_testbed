from __future__ import annotations

import inspect
from pathlib import Path

import h5py
import numpy as np
import pytest
import yaml

from testbed.data.hdf5_io import write_episode
from testbed.data.return_temporal_dispatch_sampling import (
    RETURN_TEMPORAL_DISPATCH_MAX_SEGMENTS_PER_VALIDATION_SOURCE,
    build_source_balanced_return_temporal_dispatch_sample,
)
from testbed.data.return_temporal_dispatch_validation import (
    ReturnTemporalDispatchValidationError,
    build_return_validation_counterfactual_pairs,
    load_strict_return_temporal_dispatch_validation_population,
    read_return_temporal_dispatch_observation,
    summarize_return_temporal_dispatch_validation_feasibility,
)


def _token(value: float) -> np.ndarray:
    return np.asarray([value + 0.01 * axis for axis in range(18)], dtype=np.float32)


def _write_episode(
    path: Path,
    *,
    source_id: int,
    offset: float,
    tokens: list[float],
    mask: list[int],
    action_offset: float = 0.0,
) -> None:
    count = len(mask)
    row = np.arange(count, dtype=np.float32).reshape(-1, 1)
    axis = np.arange(4, dtype=np.float32).reshape(1, -1)
    qpos = offset + 0.1 * row + 0.01 * axis
    qvel = offset + 1.0 + 0.1 * row + 0.01 * axis
    action = action_offset + offset + 0.2 * row + 0.01 * axis
    token = np.stack([_token(value) for value in tokens], axis=0)
    image = np.zeros((count, 3, 4, 3), dtype=np.uint8)
    for index in range(count):
        image[index, ...] = int((10 * offset + index) % 255)
    write_episode(
        path,
        qpos=qpos,
        qvel=qvel,
        actions=action,
        images={"cam_a": image},
        step_ids=np.arange(1000, 1000 + count, dtype=np.int64),
        v2={
            "step": {
                "return_start_envelope_tokens_v1": token,
                "action_loss_mask": np.asarray(mask, dtype=np.uint8),
            }
        },
        metadata={
            "source_episode_id": f"episode_{source_id}",
            "qpos_order": "q0,q1,q2,q3",
            "qvel_order": "v0,v1,v2,v3",
            "action_order": "a0,a1,a2,a3",
        },
    )


def _fixture_config(
    tmp_path: Path,
    *,
    validation_action_offset: float = 0.0,
    validation_segment_count_per_source: int = 2,
) -> Path:
    dataset_dir = tmp_path / "return"
    dataset_dir.mkdir(parents=True)
    source_by_episode = {0: 10, 1: 11, 2: 90, 3: 91}
    _write_episode(
        dataset_dir / "episode_0.hdf5",
        source_id=10,
        offset=0.0,
        tokens=[0.0, 0.0, 0.0, 0.5, 0.5],
        mask=[1, 1, 0, 1, 1],
    )
    _write_episode(
        dataset_dir / "episode_1.hdf5",
        source_id=11,
        offset=2.0,
        tokens=[1.0, 1.0, 1.0, 1.5, 1.5],
        mask=[1, 1, 1, 1, 1],
    )
    if validation_segment_count_per_source == 2:
        first_validation_tokens = [2.0, 2.0, 2.0, 2.5, 2.5]
        second_validation_tokens = [3.0, 3.0, 3.0, 3.5, 3.5]
        first_validation_mask = [1, 1, 0, 1, 1]
        second_validation_mask = [1, 1, 1, 1, 1]
    else:
        first_validation_tokens = [
            2.0 + 0.1 * segment
            for segment in range(validation_segment_count_per_source)
            for _ in range(2)
        ]
        second_validation_tokens = [
            3.0 + 0.1 * segment
            for segment in range(validation_segment_count_per_source)
            for _ in range(2)
        ]
        first_validation_mask = [1] * len(first_validation_tokens)
        second_validation_mask = [1] * len(second_validation_tokens)
    _write_episode(
        dataset_dir / "episode_2.hdf5",
        source_id=90,
        offset=4.0,
        tokens=first_validation_tokens,
        mask=first_validation_mask,
        action_offset=validation_action_offset,
    )
    _write_episode(
        dataset_dir / "episode_3.hdf5",
        source_id=91,
        offset=6.0,
        tokens=second_validation_tokens,
        mask=second_validation_mask,
        action_offset=validation_action_offset,
    )
    split_path = tmp_path / "return_source_split.yaml"
    split_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "split_policy": "source_identity_exact_allowlist_v1",
                "dataset_dir": str(dataset_dir.resolve()),
                "train_ids": [0, 1],
                "val_ids": [2, 3],
                "train_source_episode_ids": [10, 11],
                "val_source_episode_ids": [90, 91],
                "allowed_source_episode_ids": [10, 11, 90, 91],
                "source_episode_id_by_primitive_episode_id": source_by_episode,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    config_path = tmp_path / "return_train.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "task": {
                    "dataset_dir": str(dataset_dir.resolve()),
                    "camera_names": ["cam_a"],
                },
                "policy": {
                    "low_dim_keys": [
                        "qpos",
                        "qvel",
                        "return_start_envelope_tokens_v1",
                    ]
                },
                "train": {
                    "split_path": str(split_path.resolve()),
                    "action_loss_mask_scope": "loss_sampling_stats",
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return config_path


def test_loads_source_disjoint_return_rows_segments_and_train_only_facts(
    tmp_path: Path,
) -> None:
    population = load_strict_return_temporal_dispatch_validation_population(
        training_config_path=_fixture_config(tmp_path)
    )

    assert population.feature_order == tuple(
        [f"qpos[{index}]" for index in range(4)]
        + [f"qvel[{index}]" for index in range(4)]
        + [f"return_start_envelope_tokens_v1[{index}]" for index in range(18)]
    )
    assert len(population.train_frames) == 9
    assert len(population.validation_frames) == 9
    assert {frame.provenance.source_episode_id for frame in population.train_frames} == {10, 11}
    assert {frame.provenance.source_episode_id for frame in population.validation_frames} == {90, 91}
    assert all(frame.provenance.action_loss_mask == 1 for frame in population.train_frames)
    assert all(frame.provenance.action_loss_mask == 1 for frame in population.validation_frames)
    assert all(frame.observation_index == frame.action_index for frame in population.validation_frames)
    assert all(frame.observation_step_id == frame.action_step_id for frame in population.validation_frames)
    assert all(frame.qpos.dtype == np.float32 for frame in population.validation_frames)
    assert all(frame.qvel.dtype == np.float32 for frame in population.validation_frames)
    assert all(frame.token.dtype == np.float32 for frame in population.validation_frames)
    assert all(frame.expert_action.dtype == np.float32 for frame in population.validation_frames)
    assert all(not frame.qpos.flags.writeable for frame in population.validation_frames)
    assert len(population.validation_segments) == 4
    assert population.camera_names == ("cam_a",)
    assert population.action_reference.fit_partition == "strict_train"
    assert population.action_reference.action_row_count == len(population.train_frames)
    assert population.action_reference.action_delta_row_count == 6
    assert population.action_reference.jitter_row_count == 3
    assert population.action_reference.action_scale.shape == (4,)
    assert np.all(population.action_reference.action_scale >= 0.01)


def test_validation_pairing_uses_only_real_held_validation_tokens_deterministically(
    tmp_path: Path,
) -> None:
    population = load_strict_return_temporal_dispatch_validation_population(
        training_config_path=_fixture_config(tmp_path)
    )

    first = build_return_validation_counterfactual_pairs(population)
    second = build_return_validation_counterfactual_pairs(population)

    assert len(first) == len(population.validation_segments)
    assert [item.as_dict() for item in first] == [item.as_dict() for item in second]
    assert all(item.baseline_segment.source_episode_id in {90, 91} for item in first)
    assert all(item.alternate_token_source_episode_id in {90, 91} for item in first)
    assert all(item.baseline_token_sha256 != item.alternate_token_sha256 for item in first)
    assert all(item.alternate_token.shape == (18,) for item in first)
    assert "target" not in inspect.signature(build_return_validation_counterfactual_pairs).parameters


def test_read_only_training_pre_dispatch_observation_matches_frame_snapshot(
    tmp_path: Path,
) -> None:
    population = load_strict_return_temporal_dispatch_validation_population(
        training_config_path=_fixture_config(tmp_path)
    )
    frame = population.validation_frames[0]

    observation = read_return_temporal_dispatch_observation(
        frame=frame,
        camera_names=population.camera_names,
    )

    np.testing.assert_array_equal(observation["qpos"], frame.qpos)
    np.testing.assert_array_equal(observation["qvel"], frame.qvel)
    np.testing.assert_array_equal(
        observation["return_start_envelope_tokens_v1"], frame.token
    )
    assert observation["image_cam_a"].dtype == np.uint8
    assert observation["image_cam_a"].shape == (3, 4, 3)


def test_train_action_reference_does_not_change_when_held_validation_actions_change(
    tmp_path: Path,
) -> None:
    first = load_strict_return_temporal_dispatch_validation_population(
        training_config_path=_fixture_config(tmp_path / "first")
    )
    second = load_strict_return_temporal_dispatch_validation_population(
        training_config_path=_fixture_config(tmp_path / "second", validation_action_offset=999.0)
    )

    assert first.action_reference.as_dict() == second.action_reference.as_dict()
    summary = summarize_return_temporal_dispatch_validation_feasibility(first)
    assert summary["target_rollout_used_for_fit_or_selection"] is False
    assert summary["fit_partition"] == "strict_train"
    assert summary["validation_partition"] == "held_out_source_disjoint"
    assert summary["counterfactual_pairing"]["uses_only_held_validation_tokens"] is True


def test_source_balanced_sample_is_fixed_held_only_and_covers_only_selected_segments(
    tmp_path: Path,
) -> None:
    population = load_strict_return_temporal_dispatch_validation_population(
        training_config_path=_fixture_config(
            tmp_path,
            validation_segment_count_per_source=10,
        )
    )

    first = build_source_balanced_return_temporal_dispatch_sample(population)
    second = build_source_balanced_return_temporal_dispatch_sample(population)
    payload = first.as_dict()

    assert len(population.validation_segments) == 20
    assert len(first.sampled_segments) == 16
    assert len(first.counterfactual_pairs) == len(first.sampled_segments)
    assert payload == second.as_dict()
    assert payload["target_rollout_used_for_selection"] is False
    assert payload["coverage_scope"] == "frozen_sampled_held_validation_segments_only"
    assert payload["counterfactual_token_pool"] == "sampled_held_validation_real_tokens_only"
    assert all(
        len(source.sampled_segment_ids)
        == RETURN_TEMPORAL_DISPATCH_MAX_SEGMENTS_PER_VALIDATION_SOURCE
        for source in first.source_samples
    )
    for source in first.source_samples:
        available = sorted(
            (
                segment
                for segment in population.validation_segments
                if segment.source_episode_id == source.source_episode_id
            ),
            key=lambda segment: (
                segment.primitive_episode_id,
                segment.frames[0].action_index,
                segment.segment_id,
            ),
        )
        positions = np.linspace(
            0,
            len(available) - 1,
            num=RETURN_TEMPORAL_DISPATCH_MAX_SEGMENTS_PER_VALIDATION_SOURCE,
            dtype=np.int64,
        )
        assert source.sampled_segment_ids == tuple(
            available[int(position)].segment_id for position in positions
        )
    assert {pair.baseline_segment.segment_id for pair in first.counterfactual_pairs} == {
        segment.segment_id for segment in first.sampled_segments
    }
    assert all(
        pair.alternate_token_source_episode_id in {90, 91}
        for pair in first.counterfactual_pairs
    )
    assert {
        pair.alternate_token_segment_id for pair in first.counterfactual_pairs
    } <= {segment.segment_id for segment in first.sampled_segments}
    assert "target" not in inspect.signature(
        build_source_balanced_return_temporal_dispatch_sample
    ).parameters


def test_rejects_non_float32_velocity_storage_before_replay_population_is_exposed(
    tmp_path: Path,
) -> None:
    config_path = _fixture_config(tmp_path)
    episode = tmp_path / "return" / "episode_2.hdf5"
    with h5py.File(episode, "r+") as handle:
        values = handle["observations/qvel"][:]
        del handle["observations/qvel"]
        handle["observations"].create_dataset("qvel", data=values.astype(np.float64))

    with pytest.raises(ReturnTemporalDispatchValidationError, match="qvel dtype"):
        load_strict_return_temporal_dispatch_validation_population(
            training_config_path=config_path
        )
