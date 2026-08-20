from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import yaml

from testbed.data.dig_support_outlier_alignment import (
    DigSupportOutlierAlignmentError,
    Hdf5QposQvelContract,
    audit_dig_support_outlier_alignment_from_paths,
    build_dig_support_outlier_frame_rows,
    compare_dig_qvel_feature_contracts,
    inspect_recorded_dig_segment_integrity,
)
from testbed.data.hdf5_io import write_episode
from testbed.data.recorded_act_replay import (
    RecordedActReplayFrame,
    RecordedActReplaySegment,
    StrictTrainNumericSupport,
)


def _support() -> StrictTrainNumericSupport:
    return StrictTrainNumericSupport(
        skill_name="dig",
        model_token_key="dig_cut_tokens",
        feature_order=tuple(
            [f"qpos[{index}]" for index in range(4)]
            + [f"qvel[{index}]" for index in range(4)]
            + [f"dig_cut_tokens[{index}]" for index in range(10)]
        ),
        p01=np.asarray([-1.0] * 18, dtype=np.float32),
        p99=np.asarray([1.0] * 18, dtype=np.float32),
        train_source_episode_ids=(7,),
        validation_source_episode_ids=(8,),
        total_step_count=4,
        kept_step_count=3,
        masked_step_count=1,
    )


def _frame(
    *,
    action_step_id: int,
    row_index: int,
    qvel_1: float,
    switch_reason: str = "",
    restarted: bool = False,
) -> RecordedActReplayFrame:
    return RecordedActReplayFrame(
        jsonl_row_index=row_index,
        action_step_id=action_step_id,
        observation_step_id=action_step_id - 1,
        action_hdf5_index=row_index,
        observation_hdf5_index=row_index - 1,
        skill_name="dig",
        primitive_cycle_index=2,
        skill_switch_reason=switch_reason,
        policy_restarted=restarted,
        policy_dispatched=True,
        qpos=np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
        qvel=np.asarray([0.0, qvel_1, 0.2, 0.3], dtype=np.float32),
        action=np.asarray([0.0, 0.0, 0.0, 0.0], dtype=np.float32),
        token=np.asarray([0.25] * 10, dtype=np.float32),
        model_token_key="dig_cut_tokens",
        token_source="recorded",
    )


def _segment() -> RecordedActReplaySegment:
    frames = (
        _frame(
            action_step_id=1044,
            row_index=1043,
            qvel_1=0.9,
            switch_reason="return_to_dig",
        ),
        _frame(action_step_id=1045, row_index=1044, qvel_1=1.1),
        _frame(action_step_id=1046, row_index=1045, qvel_1=0.8),
    )
    return RecordedActReplaySegment(
        skill_name="dig",
        model_token_key="dig_cut_tokens",
        token=frames[0].token,
        token_source="recorded",
        token_sha256="37a4b7afda73" + "0" * 52,
        frames=frames,
        start_action_step_id=1044,
        end_action_step_id=1046,
        primitive_cycle_indices=(2,),
    )


def test_frame_table_keeps_pre_action_observation_and_full_v1_bounds() -> None:
    rows = build_dig_support_outlier_frame_rows(segment=_segment(), support=_support())

    assert [row["action_step_id"] for row in rows] == [1044, 1045, 1046]
    assert rows[0]["observation_step_id"] == 1043
    assert rows[1]["qvel"] == pytest.approx([0.0, 1.1, 0.2, 0.3])
    assert rows[1]["token"] == pytest.approx([0.25] * 10)
    assert rows[1]["v1_bounds"]["qvel[1]"] == {
        "p01": -1.0,
        "p99": 1.0,
    }
    assert rows[1]["violations"] == [
        {
            "field": "qvel[1]",
            "kind": "above_p99",
            "value": pytest.approx(1.1),
            "p01": -1.0,
            "p99": 1.0,
        }
    ]


def test_segment_integrity_records_boundary_without_calling_it_an_internal_reset() -> (
    None
):
    result = inspect_recorded_dig_segment_integrity(_segment())

    assert result["all_actions_use_immediate_pre_action_observation"] is True
    assert result["jsonl_hdf5_action_index_identity"] is True
    assert result["action_step_ids_contiguous"] is True
    assert result["observation_step_ids_contiguous"] is True
    assert result["internal_skill_switches"] == []
    assert result["policy_restart_action_step_ids"] == []
    assert result["entry_skill_switch_reason"] == "return_to_dig"
    assert result["token_stable"] is True
    assert result["qvel_second_difference"]["qvel[1]"] == pytest.approx([-0.5])


def test_segment_integrity_rejects_a_frame_that_is_not_pre_action_aligned() -> None:
    bad = _frame(action_step_id=1045, row_index=1044, qvel_1=0.2)
    bad = RecordedActReplayFrame(**{**bad.__dict__, "observation_hdf5_index": 1044})
    segment = RecordedActReplaySegment(
        skill_name="dig",
        model_token_key="dig_cut_tokens",
        token=bad.token,
        token_source="recorded",
        token_sha256="37a4b7afda73" + "0" * 52,
        frames=(bad,),
        start_action_step_id=1045,
        end_action_step_id=1045,
        primitive_cycle_indices=(2,),
    )
    with pytest.raises(DigSupportOutlierAlignmentError, match="pre-action"):
        inspect_recorded_dig_segment_integrity(segment)


def test_qvel_contract_comparison_checks_representation_without_inferring_units() -> (
    None
):
    replay = Hdf5QposQvelContract(
        qpos_dtype="float32",
        qvel_dtype="float32",
        qpos_order=(
            "swing_position_norm",
            "boom_position_norm",
            "stick_position_norm",
            "bucket_position_norm",
        ),
        qvel_order=("swing_speed", "boom_speed", "stick_speed", "bucket_speed"),
        qvel_specific_scale_metadata=None,
    )
    result = compare_dig_qvel_feature_contracts(replay=replay, training=(replay,))

    assert result["same_qvel_dtype"] is True
    assert result["same_qvel_order"] is True
    assert result["same_raw_qvel_representation"] is True
    assert result["qvel_scale_evidence"] == "raw_hdf5_float32_identity"
    assert result["physical_unit_inference"] == "not_attempted"
    assert result["replay_qvel_index_metadata"][1] == {
        "feature": "qvel[1]",
        "metadata_field": "boom_speed",
        "physical_unit": "not_inferred",
    }

    mismatched = Hdf5QposQvelContract(
        qpos_dtype="float32",
        qvel_dtype="float64",
        qpos_order=replay.qpos_order,
        qvel_order=replay.qvel_order,
        qvel_specific_scale_metadata=None,
    )
    mismatch_result = compare_dig_qvel_feature_contracts(
        replay=replay,
        training=(mismatched,),
    )
    assert mismatch_result["same_qvel_dtype"] is False
    assert mismatch_result["same_raw_qvel_representation"] is False


def _write_rollout(tmp_path: Path) -> tuple[Path, Path]:
    hdf5_path = tmp_path / "rollout.hdf5"
    step_ids = np.arange(1043, 1047, dtype=np.int64)
    qpos = np.arange(16, dtype=np.float32).reshape(4, 4) / 10.0
    qvel = np.asarray(
        [
            [0.0, 0.5, 0.0, 0.0],
            [0.0, 1.2, 0.0, 0.0],
            [0.0, 0.5, 0.0, 0.0],
            [0.0, 0.4, 0.0, 0.0],
        ],
        dtype=np.float32,
    )
    actions = np.zeros((4, 4), dtype=np.float32)
    write_episode(
        hdf5_path,
        qpos=qpos,
        qvel=qvel,
        actions=actions,
        step_ids=step_ids,
        metadata={
            "qpos_order": "swing_position_norm,boom_position_norm,stick_position_norm,bucket_position_norm",
            "qvel_order": "swing_speed,boom_speed,stick_speed,bucket_speed",
        },
    )
    rows = []
    for index, step_id in enumerate(step_ids):
        row = {
            "step_id": int(step_id),
            "action": actions[index].tolist(),
            "skill_name": "return" if index == 0 else "dig",
            "primitive_cycle_index": 2,
            "skill_switch_reason": "return_to_dig" if index == 1 else "",
            "box_safety_policy_restarted": False,
            "box_safety_reason": "",
            "box_safety_clearance_active": False,
            "box_safety_awaiting_neutral_ack": False,
        }
        if index:
            row["dig_cut_tokens"] = [0.25] * 10
            row["dig_cut_token_source"] = "recorded"
        rows.append(row)
    jsonl_path = tmp_path / "rollout.jsonl"
    jsonl_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    return hdf5_path, jsonl_path


def _write_train_config(tmp_path: Path) -> Path:
    dataset_dir = tmp_path / "dig"
    dataset_dir.mkdir()
    train_path = dataset_dir / "episode_0.hdf5"
    validation_path = dataset_dir / "episode_1.hdf5"
    qpos = np.zeros((3, 4), dtype=np.float32)
    qvel = np.asarray(
        [[0.0, 0.0, 0.0, 0.0], [0.0, 0.5, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]],
        dtype=np.float32,
    )
    actions = np.zeros((3, 4), dtype=np.float32)
    for path, source_id, mask in (
        (train_path, "episode_7", [1, 1, 0]),
        (validation_path, "episode_8", [1, 1, 1]),
    ):
        write_episode(
            path,
            qpos=qpos,
            qvel=qvel,
            actions=actions,
            step_ids=np.arange(3, dtype=np.int64),
            metadata={
                "source_episode_id": source_id,
                "qpos_order": "swing_position_norm,boom_position_norm,stick_position_norm,bucket_position_norm",
                "qvel_order": "swing_speed,boom_speed,stick_speed,bucket_speed",
            },
            v2={
                "step": {
                    "dig_cut_tokens": np.full((3, 10), 0.25, dtype=np.float32),
                    "action_loss_mask": np.asarray(mask, dtype=np.uint8),
                }
            },
        )
    split_path = tmp_path / "split.yaml"
    split_path.write_text(
        yaml.safe_dump(
            {
                "split_policy": "source_identity_exact_allowlist_v1",
                "dataset_dir": str(dataset_dir),
                "train_ids": [0],
                "val_ids": [1],
                "train_source_episode_ids": [7],
                "val_source_episode_ids": [8],
                "allowed_source_episode_ids": [7, 8],
                "source_episode_id_by_primitive_episode_id": {0: 7, 1: 8},
            }
        ),
        encoding="utf-8",
    )
    config_path = tmp_path / "dig.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "task": {"dataset_dir": str(dataset_dir)},
                "policy": {"low_dim_keys": ["qpos", "qvel", "dig_cut_tokens"]},
                "train": {
                    "split_path": str(split_path),
                    "action_loss_mask_scope": "loss_sampling_stats",
                },
            }
        ),
        encoding="utf-8",
    )
    return config_path


def test_path_audit_uses_only_strict_train_masked_rows_and_replay_preobs(
    tmp_path: Path,
) -> None:
    rollout_hdf5, rollout_jsonl = _write_rollout(tmp_path)
    config_path = _write_train_config(tmp_path)

    result = audit_dig_support_outlier_alignment_from_paths(
        rollout_hdf5_path=rollout_hdf5,
        rollout_jsonl_path=rollout_jsonl,
        dig_training_config_path=config_path,
        target_segment_id="dig:1044-1046:184cf038ac8c",
    )

    assert result["status"] == "completed"
    assert result["target_segment_id"] == "dig:1044-1046:184cf038ac8c"
    assert result["training_action_loss_mask"]["kept_step_count"] == 2
    assert result["training_action_loss_mask"]["masked_step_count"] == 1
    assert result["training_action_loss_mask"]["only_action_loss_mask_one_used"] is True
    assert (
        result["alignment"]["all_actions_use_immediate_pre_action_observation"] is True
    )
    assert result["feature_contract"]["same_raw_qvel_representation"] is True
    assert "qvel[1]" in {
        violation["field"] for violation in result["frame_table"][1]["violations"]
    }
