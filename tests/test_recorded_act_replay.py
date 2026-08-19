from __future__ import annotations

import json
from pathlib import Path

import cv2
import h5py
import numpy as np
import pytest
import yaml

from testbed.data.hdf5_io import write_episode
from testbed.data.recorded_act_replay import (
    assess_strict_train_numeric_support,
    build_strict_train_numeric_support,
    deterministic_alternate_segments,
    join_recorded_act_replay_frames,
    read_recorded_act_observation,
    select_deterministic_alternate_segment,
    split_stable_recorded_act_segments,
)


def _jpeg(value: int) -> np.ndarray:
    rgb = np.full((6, 8, 3), value, dtype=np.uint8)
    ok, payload = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    assert ok
    return payload.reshape(-1)


def _token(dim: int, value: float) -> list[float]:
    return [float(value + index * 0.01) for index in range(dim)]


def _write_recorded_rollout(tmp_path: Path) -> tuple[Path, Path]:
    hdf5_path = tmp_path / "episode_0.hdf5"
    step_ids = np.arange(10, 20, dtype=np.int64)
    actions = np.arange(40, dtype=np.float32).reshape(10, 4) / 10.0
    qpos = np.arange(40, dtype=np.float32).reshape(10, 4) / 100.0
    qvel = qpos + 1.0
    write_episode(
        hdf5_path,
        qpos=qpos,
        qvel=qvel,
        actions=actions,
        step_ids=step_ids,
        encoded_images={"fpv": [_jpeg(30 + index) for index in range(10)]},
        metadata={"camera_names": "fpv", "image_format": "jpeg"},
    )
    dig_a = _token(10, 0.10)
    dig_b = _token(10, 0.40)
    return_token = _token(18, -0.20)
    rows = []
    for index, step_id in enumerate(step_ids):
        row = {
            "step_id": int(step_id),
            "action": actions[index].tolist(),
            "skill_name": "bootstrap",
            "primitive_cycle_index": 0,
            "skill_switch_reason": "",
            "box_safety_policy_restarted": False,
            "box_safety_reason": "",
            "box_safety_clearance_active": False,
            "box_safety_awaiting_neutral_ack": False,
        }
        if step_id in (11, 12):
            row.update(
                {
                    "skill_name": "dig",
                    "dig_cut_tokens": dig_a,
                    "dig_cut_token_source": "recorded_dig_a",
                }
            )
        elif step_id in (13, 14):
            row.update(
                {
                    "skill_name": "dig",
                    "dig_cut_tokens": dig_b,
                    "dig_cut_token_source": "recorded_dig_b",
                    "skill_switch_reason": "dig_replan" if step_id == 13 else "",
                }
            )
        elif step_id in (15, 16):
            row.update(
                {
                    "skill_name": "return",
                    "primitive_cycle_index": 0 if step_id == 15 else 1,
                    "return_start_envelope_tokens": return_token,
                    "return_start_envelope_token_source": "recorded_return_a",
                    "skill_switch_reason": "dump_to_return" if step_id == 15 else "",
                }
            )
        elif step_id in (17, 18):
            row.update(
                {
                    "skill_name": "carry",
                    "primitive_cycle_index": 2,
                    "skill_switch_reason": "dig_to_carry" if step_id == 17 else "",
                    # The historical row may still contain this field, but Carry
                    # must never expose it as a model observation input.
                    "dig_cut_tokens": dig_b,
                }
            )
        elif step_id == 19:
            row.update(
                {
                    "skill_name": "dump",
                    "primitive_cycle_index": 2,
                    "skill_switch_reason": "carry_to_dump",
                    "dig_cut_tokens": dig_b,
                }
            )
        rows.append(row)
    jsonl_path = tmp_path / "rollout_000.jsonl"
    jsonl_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    return hdf5_path, jsonl_path


def test_join_uses_pre_action_observation_maps_tokens_and_decodes_jpeg(
    tmp_path: Path,
) -> None:
    hdf5_path, jsonl_path = _write_recorded_rollout(tmp_path)

    frames = join_recorded_act_replay_frames(
        rollout_hdf5_path=hdf5_path,
        rollout_jsonl_path=jsonl_path,
    )

    assert [frame.action_step_id for frame in frames] == [11, 12, 13, 14, 15, 16]
    first = frames[0]
    assert first.action_hdf5_index == 1
    assert first.observation_hdf5_index == 0
    assert first.observation_step_id == 10
    assert first.model_token_key == "dig_cut_tokens"
    np.testing.assert_allclose(first.qpos, [0.0, 0.01, 0.02, 0.03])
    assert frames[-1].model_token_key == "return_start_envelope_tokens_v1"
    assert frames[-1].token.shape == (18,)

    with h5py.File(hdf5_path, "r") as handle:
        observation = read_recorded_act_observation(
            hdf5_file=handle,
            frame=first,
            camera_names=["fpv"],
        )
        return_observation = read_recorded_act_observation(
            hdf5_file=handle,
            frame=frames[-1],
            camera_names=["fpv"],
        )
    assert observation["dig_cut_tokens"].shape == (10,)
    assert return_observation["return_start_envelope_tokens_v1"].shape == (18,)
    assert observation["image_fpv"].shape == (6, 8, 3)
    assert observation["image_fpv"].dtype == np.uint8
    assert float(observation["image_fpv"].mean()) == pytest.approx(30.0, abs=3.0)

    with h5py.File(hdf5_path, "r") as handle:
        with pytest.raises(ValueError, match="camera order"):
            read_recorded_act_observation(
                hdf5_file=handle,
                frame=first,
                camera_names=["wrong_order"],
            )


def test_join_rejects_action_mismatch_and_missing_pre_observation(tmp_path: Path) -> None:
    hdf5_path, jsonl_path = _write_recorded_rollout(tmp_path)
    rows = [json.loads(line) for line in jsonl_path.read_text().splitlines()]
    rows[1]["action"][0] += 0.5
    jsonl_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="disagrees"):
        join_recorded_act_replay_frames(
            rollout_hdf5_path=hdf5_path,
            rollout_jsonl_path=jsonl_path,
        )

    rows[1]["action"] = [0.0, 0.1, 0.2, 0.3]
    rows[0]["skill_name"] = "dig"
    rows[0]["dig_cut_tokens"] = _token(10, 0.0)
    rows[0]["action"] = [0.0, 0.1, 0.2, 0.3]
    jsonl_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="pre-action observation"):
        join_recorded_act_replay_frames(
            rollout_hdf5_path=hdf5_path,
            rollout_jsonl_path=jsonl_path,
        )


def test_stable_segments_ignore_cycle_changes_but_split_on_token_or_reset(
    tmp_path: Path,
) -> None:
    hdf5_path, jsonl_path = _write_recorded_rollout(tmp_path)
    frames = join_recorded_act_replay_frames(
        rollout_hdf5_path=hdf5_path,
        rollout_jsonl_path=jsonl_path,
    )

    segments = split_stable_recorded_act_segments(frames)

    assert [(segment.skill_name, segment.frame_count) for segment in segments] == [
        ("dig", 2),
        ("dig", 2),
        ("return", 2),
    ]
    assert segments[-1].primitive_cycle_indices == (0, 1)
    assert segments[-1].primitive == "return"
    assert segments[-1].condition_input_key == "return_start_envelope_tokens_v1"
    assert segments[0].end_action_step_id == 12
    assert segments[1].start_action_step_id == 13
    assert segments[0].token_sha256 != segments[1].token_sha256


def test_alternate_selection_is_deterministic_and_excludes_baseline(tmp_path: Path) -> None:
    hdf5_path, jsonl_path = _write_recorded_rollout(tmp_path)
    segments = split_stable_recorded_act_segments(
        join_recorded_act_replay_frames(
            rollout_hdf5_path=hdf5_path,
            rollout_jsonl_path=jsonl_path,
        )
    )
    baseline = segments[0]

    candidates = deterministic_alternate_segments(
        segments=segments,
        baseline=baseline,
    )

    assert len(candidates) == 1
    assert candidates[0].skill_name == "dig"
    assert candidates[0].token_sha256 != baseline.token_sha256
    assert select_deterministic_alternate_segment(
        segments=segments,
        baseline=baseline,
    ) == candidates[0]


def test_carry_dump_replay_keeps_only_original_non_conditioned_observation(
    tmp_path: Path,
) -> None:
    hdf5_path, jsonl_path = _write_recorded_rollout(tmp_path)

    frames = join_recorded_act_replay_frames(
        rollout_hdf5_path=hdf5_path,
        rollout_jsonl_path=jsonl_path,
        skills=("carry", "dump"),
    )
    segments = split_stable_recorded_act_segments(frames)

    assert [(segment.primitive, segment.frame_count) for segment in segments] == [
        ("carry", 2),
        ("dump", 1),
    ]
    assert all(frame.token is None for frame in frames)
    assert all(frame.model_token_key is None for frame in frames)
    assert all(segment.condition_input_key is None for segment in segments)
    assert all(segment.token_sha256 is None for segment in segments)

    with h5py.File(hdf5_path, "r") as handle:
        observation = read_recorded_act_observation(
            hdf5_file=handle,
            frame=frames[0],
            camera_names=["fpv"],
        )
    assert set(observation) == {"qpos", "qvel", "image_fpv"}
    assert observation["qpos"].shape == (4,)
    assert observation["qvel"].shape == (4,)
    assert observation["image_fpv"].shape == (6, 8, 3)

    with pytest.raises(ValueError, match="condition token"):
        deterministic_alternate_segments(
            segments=segments,
            baseline=segments[0],
        )


def _write_train_episode(
    path: Path,
    *,
    source_episode_id: int,
    skill_name: str,
    offset: float,
) -> None:
    token_key = (
        "dig_cut_tokens"
        if skill_name == "dig"
        else "return_start_envelope_tokens_v1"
    )
    token_dim = 10 if skill_name == "dig" else 18
    values = np.asarray(
        [
            _token(token_dim, offset),
            _token(token_dim, offset + 0.1),
            _token(token_dim, offset + 0.2),
        ],
        dtype=np.float32,
    )
    qpos = np.asarray(
        [
            [offset, offset + 0.01, offset + 0.02, offset + 0.03],
            [offset + 0.1, offset + 0.11, offset + 0.12, offset + 0.13],
            [offset + 0.2, offset + 0.21, offset + 0.22, offset + 0.23],
        ],
        dtype=np.float32,
    )
    write_episode(
        path,
        qpos=qpos,
        qvel=qpos + 1.0,
        actions=np.zeros((3, 4), dtype=np.float32),
        v2={
            "step": {
                token_key: values,
                "action_loss_mask": np.asarray([1, 0, 1], dtype=np.uint8),
            }
        },
        metadata={"source_episode_id": f"episode_{source_episode_id}"},
    )


def _write_split(
    path: Path,
    *,
    dataset_dir: Path,
    source_map: dict[int, int],
) -> None:
    payload = {
        "schema_version": 1,
        "split_policy": "source_identity_exact_allowlist_v1",
        "dataset_dir": str(dataset_dir.resolve()),
        "train_ids": [0, 1],
        "val_ids": [2],
        "train_source_episode_ids": [3, 7],
        "val_source_episode_ids": [33],
        "allowed_source_episode_ids": [3, 7, 33],
        "source_episode_id_by_primitive_episode_id": source_map,
    }
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


@pytest.mark.parametrize(("skill_name", "token_dim"), [("dig", 10), ("return", 18)])
def test_strict_train_support_uses_masked_train_rows_and_source_split(
    tmp_path: Path,
    skill_name: str,
    token_dim: int,
) -> None:
    dataset_dir = tmp_path / skill_name
    dataset_dir.mkdir()
    _write_train_episode(
        dataset_dir / "episode_0.hdf5",
        source_episode_id=3,
        skill_name=skill_name,
        offset=0.0,
    )
    _write_train_episode(
        dataset_dir / "episode_1.hdf5",
        source_episode_id=7,
        skill_name=skill_name,
        offset=1.0,
    )
    _write_train_episode(
        dataset_dir / "episode_2.hdf5",
        source_episode_id=33,
        skill_name=skill_name,
        offset=9.0,
    )
    split_path = tmp_path / f"{skill_name}_split.yaml"
    _write_split(split_path, dataset_dir=dataset_dir, source_map={0: 3, 1: 7, 2: 33})

    support = build_strict_train_numeric_support(
        primitive_dataset_dir=dataset_dir,
        split_path=split_path,
        skill_name=skill_name,
    )

    assert support.feature_dim == 8 + token_dim
    assert support.kept_step_count == 4
    assert support.masked_step_count == 2
    assert support.train_source_episode_ids == (3, 7)
    assert support.validation_source_episode_ids == (33,)
    assert support.model_token_key == (
        "dig_cut_tokens"
        if skill_name == "dig"
        else "return_start_envelope_tokens_v1"
    )

    assessment = assess_strict_train_numeric_support(
        support,
        qpos=np.asarray([[0.1, 0.11, 0.12, 0.13], [99.0, 0.0, 0.0, 0.0]]),
        qvel=np.asarray([[1.1, 1.11, 1.12, 1.13], [1.0, 1.0, 1.0, 1.0]]),
        token=np.asarray([_token(token_dim, 0.1), _token(token_dim, 0.1)]),
    )
    assert assessment.frame_in_support.tolist() == [True, False]
    assert assessment.in_support_fraction == pytest.approx(0.5)
    assert any(issue.field == "qpos[0]" for issue in assessment.violations[1])


def test_strict_train_support_rejects_source_leakage(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dig"
    dataset_dir.mkdir()
    _write_train_episode(
        dataset_dir / "episode_0.hdf5",
        source_episode_id=33,
        skill_name="dig",
        offset=0.0,
    )
    _write_train_episode(
        dataset_dir / "episode_1.hdf5",
        source_episode_id=7,
        skill_name="dig",
        offset=1.0,
    )
    _write_train_episode(
        dataset_dir / "episode_2.hdf5",
        source_episode_id=3,
        skill_name="dig",
        offset=9.0,
    )
    split_path = tmp_path / "dig_split.yaml"
    _write_split(split_path, dataset_dir=dataset_dir, source_map={0: 3, 1: 7, 2: 33})

    with pytest.raises(ValueError, match="validation source"):
        build_strict_train_numeric_support(
            primitive_dataset_dir=dataset_dir,
            split_path=split_path,
            skill_name="dig",
        )
