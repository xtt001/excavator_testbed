from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np
import yaml

from testbed.data.handoff_envelope import (
    STRICT18_TRAIN_SOURCE_EPISODE_IDS,
    STRICT18_VALIDATION_SOURCE_EPISODE_IDS,
)
from testbed.eval.act_regression_offline_diagnostic import (
    build_train_expert_index,
    classify_temporal_replay_frame,
    join_rollout_action_frames,
    load_token_variant_matrix,
    nearest_expert_action,
    temporal_contributors,
    write_json_exclusive,
)
from testbed.eval.act_regression_policy_replay import summarize_records


def _write_rollout(tmp_path: Path) -> tuple[Path, Path]:
    hdf5_path = tmp_path / "episode_0.hdf5"
    with h5py.File(hdf5_path, "w") as handle:
        handle.create_dataset("timestamps/step_id", data=np.asarray([10, 11, 12]))
        handle.create_dataset(
            "observations/qpos",
            data=np.arange(12, dtype=np.float32).reshape(3, 4),
        )
        handle.create_dataset(
            "observations/qvel",
            data=np.arange(12, 24, dtype=np.float32).reshape(3, 4),
        )
        handle.create_dataset(
            "observations/env_state",
            data=np.zeros((3, 107), dtype=np.float32),
        )
        handle.create_dataset(
            "action",
            data=np.asarray(
                [[0.0, 0.0, 0.0, 0.0], [0.1, 0.2, 0.3, 0.4], [0.5] * 4],
                dtype=np.float32,
            ),
        )
    jsonl_path = tmp_path / "rollout_000.jsonl"
    rows = [
        {
            "step_id": 10,
            "primitive_cycle_index": 0,
            "skill_name": "return",
            "action": [0.0] * 4,
            "dig_cut_tokens": [0.0] * 10,
        },
        {
            "step_id": 11,
            "primitive_cycle_index": 1,
            "skill_name": "dig",
            "action": [0.1, 0.2, 0.3, 0.4],
            "dig_cut_tokens": [0.25] * 10,
            "dig_step_count": 0,
        },
        {
            "step_id": 12,
            "primitive_cycle_index": 1,
            "skill_name": "dig",
            "action": [0.5] * 4,
            "dig_cut_tokens": [0.5] * 10,
            "dig_step_count": 1,
        },
    ]
    jsonl_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    return hdf5_path, jsonl_path


def test_join_uses_previous_post_observation_for_current_action(tmp_path: Path) -> None:
    hdf5_path, jsonl_path = _write_rollout(tmp_path)

    frames = join_rollout_action_frames(
        rollout_hdf5_path=hdf5_path,
        rollout_jsonl_path=jsonl_path,
        cycle_index=1,
        skill_name="dig",
    )

    assert [frame["action_step_id"] for frame in frames] == [11, 12]
    assert [frame["observation_step_id"] for frame in frames] == [10, 11]
    assert frames[0]["observation_hdf5_index"] == 0
    assert frames[0]["qpos"] == [0.0, 1.0, 2.0, 3.0]
    assert frames[0]["dig_cut_tokens"] == [0.25] * 10
    assert np.allclose(frames[0]["actual_action"], [0.1, 0.2, 0.3, 0.4])


def test_join_fails_when_jsonl_step_is_missing_from_hdf5(tmp_path: Path) -> None:
    hdf5_path, jsonl_path = _write_rollout(tmp_path)
    with jsonl_path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {
                    "step_id": 99,
                    "primitive_cycle_index": 1,
                    "skill_name": "dig",
                    "dig_cut_tokens": [0.0] * 10,
                }
            )
            + "\n"
        )

    try:
        join_rollout_action_frames(
            rollout_hdf5_path=hdf5_path,
            rollout_jsonl_path=jsonl_path,
            cycle_index=1,
            skill_name="dig",
        )
    except ValueError as exc:
        assert "step_id 99" in str(exc)
    else:  # pragma: no cover - assertion helper
        raise AssertionError("missing HDF5 step_id should fail closed")


def _write_primitive(
    path: Path,
    *,
    source_episode_id: int,
    qpos: list[list[float]],
    action: list[list[float]],
    action_loss_mask: list[int] | None = None,
) -> None:
    with h5py.File(path, "w") as handle:
        metadata = handle.create_group("metadata")
        metadata.attrs["source_episode_id"] = f"episode_{source_episode_id}"
        handle.create_dataset("observations/qpos", data=np.asarray(qpos, np.float32))
        handle.create_dataset(
            "observations/qvel",
            data=np.zeros((len(qpos), 4), dtype=np.float32),
        )
        handle.create_dataset(
            "v2/step/dig_cut_tokens",
            data=np.zeros((len(qpos), 10), dtype=np.float32),
        )
        handle.create_dataset(
            "v2/step/action_loss_mask",
            data=np.asarray(
                action_loss_mask
                if action_loss_mask is not None
                else [1] * len(qpos),
                dtype=np.uint8,
            ),
        )
        env_state = np.zeros((len(qpos), 89), dtype=np.float32)
        env_state[:, 28:31] = np.asarray(qpos, dtype=np.float32)[:, :3]
        env_state[:, 33:39] = 0.08
        handle.create_dataset("observations/env_state", data=env_state)
        handle.create_dataset("action", data=np.asarray(action, np.float32))


def _write_strict_split(
    path: Path,
    *,
    train_ids: list[int],
    source_by_id: dict[int, int],
) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "train_ids": train_ids,
                "train_source_episode_ids": list(
                    STRICT18_TRAIN_SOURCE_EPISODE_IDS
                ),
                "val_source_episode_ids": list(
                    STRICT18_VALIDATION_SOURCE_EPISODE_IDS
                ),
                "allowed_source_episode_ids": [
                    *STRICT18_TRAIN_SOURCE_EPISODE_IDS,
                    *STRICT18_VALIDATION_SOURCE_EPISODE_IDS,
                ],
                "source_episode_id_by_primitive_episode_id": source_by_id,
            }
        ),
        encoding="utf-8",
    )


def test_train_expert_index_rejects_validation_source_leakage(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dig"
    dataset_dir.mkdir()
    _write_primitive(
        dataset_dir / "episode_0.hdf5",
        source_episode_id=3,
        qpos=[[0.0] * 4],
        action=[[0.1] * 4],
    )
    _write_primitive(
        dataset_dir / "episode_1.hdf5",
        source_episode_id=33,
        qpos=[[1.0] * 4],
        action=[[0.9] * 4],
    )
    split_path = tmp_path / "split.yaml"
    _write_strict_split(
        split_path,
        train_ids=[0, 1],
        source_by_id={0: 3, 1: 33},
    )

    try:
        build_train_expert_index(dataset_dir=dataset_dir, split_path=split_path)
    except ValueError as exc:
        assert "validation source episode 33" in str(exc)
    else:  # pragma: no cover - assertion helper
        raise AssertionError("validation source leakage should fail closed")


def test_nearest_expert_action_uses_normalized_proprio_distance(
    tmp_path: Path,
) -> None:
    dataset_dir = tmp_path / "dig"
    dataset_dir.mkdir()
    _write_primitive(
        dataset_dir / "episode_0.hdf5",
        source_episode_id=3,
        qpos=[[0.0] * 4, [2.0] * 4],
        action=[[0.1] * 4, [0.9] * 4],
    )
    split_path = tmp_path / "split.yaml"
    _write_strict_split(
        split_path,
        train_ids=[0],
        source_by_id={0: 3},
    )
    index = build_train_expert_index(
        dataset_dir=dataset_dir,
        split_path=split_path,
    )
    query = np.asarray(index["feature"][1], dtype=np.float32).copy()
    query[:4] = 1.9

    result = nearest_expert_action(
        index,
        proprio=query,
        mean=np.zeros(query.shape[0], dtype=np.float32),
        std=np.ones(query.shape[0], dtype=np.float32),
    )

    assert result["episode_id"] == 0
    assert result["step"] == 1
    assert np.allclose(result["action"], [0.9] * 4)


def test_train_expert_index_excludes_masked_actions(tmp_path: Path) -> None:
    dataset_dir = tmp_path / "dig"
    dataset_dir.mkdir()
    _write_primitive(
        dataset_dir / "episode_0.hdf5",
        source_episode_id=3,
        qpos=[[0.0] * 4, [2.0] * 4],
        action=[[0.1] * 4, [0.9] * 4],
        action_loss_mask=[1, 0],
    )
    split_path = tmp_path / "split.yaml"
    _write_strict_split(
        split_path,
        train_ids=[0],
        source_by_id={0: 3},
    )

    index = build_train_expert_index(
        dataset_dir=dataset_dir,
        split_path=split_path,
    )

    assert index["total_step_count"] == 2
    assert index["kept_step_count"] == 1
    assert index["masked_step_count"] == 1
    assert index["action"].shape == (1, 4)
    assert np.allclose(index["action"][0], [0.1] * 4)


def test_join_rejects_duplicate_json_steps_and_action_mismatch(
    tmp_path: Path,
) -> None:
    hdf5_path, jsonl_path = _write_rollout(tmp_path)
    rows = [
        json.loads(line)
        for line in jsonl_path.read_text(encoding="utf-8").splitlines()
    ]
    rows.append(dict(rows[-1]))
    jsonl_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    with np.testing.assert_raises_regex(ValueError, "JSONL step_id.*duplicates"):
        join_rollout_action_frames(
            rollout_hdf5_path=hdf5_path,
            rollout_jsonl_path=jsonl_path,
        )

    rows.pop()
    rows[-1]["action"] = [0.0] * 4
    jsonl_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    with np.testing.assert_raises_regex(ValueError, "action disagrees"):
        join_rollout_action_frames(
            rollout_hdf5_path=hdf5_path,
            rollout_jsonl_path=jsonl_path,
        )


def test_temporal_replay_frame_classification_skips_switch_and_safety() -> None:
    switch = classify_temporal_replay_frame(
        {
            "skill_switch_reason": "return_to_dig_next_dig_entry_ready",
            "box_safety_reason": "",
            "box_safety_clearance_active": False,
            "box_safety_policy_restarted": False,
            "actual_action": [0.1] * 4,
        }
    )
    assert switch == {
        "policy_called": True,
        "reason": "skill_switch_reset_before_policy_call",
        "reset_before_policy_call": True,
        "reset_before_next_policy_call": False,
    }

    safety = classify_temporal_replay_frame(
        {
            "skill_switch_reason": "",
            "box_safety_reason": "wall_contact_first_session",
            "box_safety_awaiting_neutral_ack": True,
            "box_safety_clearance_active": False,
            "box_safety_policy_restarted": False,
            "actual_action": [0.0] * 4,
        }
    )
    assert safety["policy_called"] is False
    assert safety["reason"] == "safety_pre_policy_short_circuit"


def test_token_matrix_requires_schema_f0_match_and_single_factor_diffs(
    tmp_path: Path,
) -> None:
    f0 = [float(index) for index in range(10)]
    d1 = list(f0)
    d1[7] = 0.25
    c1 = list(f0)
    c1[:6] = [-float(index + 1) for index in range(6)]
    dc1 = list(c1)
    dc1[7] = d1[7]
    artifact = tmp_path / "manifest.json"
    artifact.write_text(
        json.dumps(
            {
                "schema": "act_regression_plan_matrix_v1",
                "conditions": {
                    name: {"cycle_1_dig_cut_tokens": token}
                    for name, token in {
                        "F0": f0,
                        "D1": d1,
                        "C1": c1,
                        "DC1": dc1,
                    }.items()
                },
            }
        ),
        encoding="utf-8",
    )

    loaded = load_token_variant_matrix(
        artifact,
        recorded_tokens=[f0, f0],
    )

    assert loaded["tokens"]["DC1"] == dc1
    assert len(loaded["artifact_sha256"]) == 64

    payload = json.loads(artifact.read_text(encoding="utf-8"))
    payload["conditions"]["D1"]["cycle_1_dig_cut_tokens"][2] = 99.0
    artifact.write_text(json.dumps(payload), encoding="utf-8")
    with np.testing.assert_raises_regex(ValueError, "D1.*only token index 7"):
        load_token_variant_matrix(artifact, recorded_tokens=[f0])


def test_summary_prewall_window_excludes_contact_and_later_rows() -> None:
    records = []
    for step_id in range(1, 15):
        records.append(
            {
                "action_step_id": step_id,
                "actual_action": [float(step_id)] * 4,
                "fresh_action": [float(step_id)] * 4,
                "aggregated_action": [float(step_id)] * 4,
                "nearest_train_expert": {"action": [float(step_id)] * 4},
                "support": {"p01_p99_in_support": True},
                "typed_contact_post_action": {
                    "wall_mask": step_id >= 12,
                    "bottom_mask": False,
                },
                "pre_action_safety_reason": (
                    "wall_contact_first_session" if step_id >= 13 else ""
                ),
                "act_execution": {"policy_called": True},
                "carry_start_base_ready": False,
                "carry_start_envelope_ready": False,
            }
        )

    summary = summarize_records(records)

    assert summary["first_wall_step_id"] == 12
    assert summary["prewall_last_10"]["count"] == 10
    assert summary["prewall_last_10"]["last_action_step_id"] == 11


def test_exclusive_json_writer_allows_existing_parent_but_not_file(
    tmp_path: Path,
) -> None:
    output = tmp_path / "existing-parent" / "result.json"
    output.parent.mkdir()

    write_json_exclusive(output, {"ok": True})

    assert json.loads(output.read_text(encoding="utf-8")) == {"ok": True}
    with np.testing.assert_raises(FileExistsError):
        write_json_exclusive(output, {"ok": False})


def test_temporal_contributors_preserve_legacy_oldest_first_weights() -> None:
    result = temporal_contributors(
        local_step=3,
        window=100,
        weight_order="legacy_oldest_first",
        decay=0.01,
    )

    assert result["ages"] == [3, 2, 1, 0]
    assert result["weights"][0] > result["weights"][-1]
    assert np.isclose(sum(result["weights"]), 1.0)
