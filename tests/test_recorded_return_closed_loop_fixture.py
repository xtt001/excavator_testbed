from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from testbed.data.hdf5_io import write_episode
from testbed.data.recorded_return_closed_loop_fixture import (
    FROZEN_RETURN_FIXTURE_SPECS,
    RecordedReturnFixtureSpec,
    build_recorded_return_closed_loop_fixture_set,
    load_frozen_recorded_return_closed_loop_fixture_set,
)

CAMERAS = ("stick_up", "stick_down", "eye_left", "eye_right")


def _token(value: float) -> np.ndarray:
    return np.asarray([value + index * 0.01 for index in range(18)], dtype=np.float32)


def _token_sha(token: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(token, dtype="<f4").tobytes()).hexdigest()


def _jpeg(value: int) -> np.ndarray:
    rgb = np.full((4, 6, 3), value, dtype=np.uint8)
    ok, encoded = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    assert ok
    return encoded.reshape(-1)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_fixture_inputs(
    tmp_path: Path,
) -> tuple[Path, tuple[RecordedReturnFixtureSpec, ...]]:
    source_dir = tmp_path / "source"
    stage_root = tmp_path / "stage_a_v3"
    source_dir.mkdir(parents=True)
    stage_root.mkdir(parents=True)
    hdf5_path = source_dir / "episode_0.hdf5"
    jsonl_path = source_dir / "rollout_000.jsonl"
    step_ids = np.arange(10, 21, dtype=np.int64)
    count = len(step_ids)
    qpos = np.arange(count * 4, dtype=np.float32).reshape(count, 4) / 100.0
    qvel = qpos - 0.5
    actions = qpos + 0.25
    env_state = np.arange(count * 107, dtype=np.float32).reshape(count, 107) / 10.0
    encoded = {
        camera: [_jpeg(20 + camera_index + row) for row in range(count)]
        for camera_index, camera in enumerate(CAMERAS)
    }
    write_episode(
        hdf5_path,
        qpos=qpos,
        qvel=qvel,
        actions=actions,
        env_state=env_state,
        step_ids=step_ids,
        encoded_images=encoded,
        metadata={
            "camera_names": ",".join(CAMERAS),
            "image_format": "jpeg",
            "action_order": (
                "swing_speed_cmd,boom_speed_cmd,stick_speed_cmd,bucket_speed_cmd"
            ),
            "qpos_order": (
                "swing_position_norm,boom_position_norm,stick_position_norm,"
                "bucket_position_norm"
            ),
            "qvel_order": "swing_speed,boom_speed,stick_speed,bucket_speed",
            "env_state_contract_version": "agx_env_state_v2_4_107",
            "unity_scene_id": "Assets/TestScene.unity@sha256:" + "a" * 64,
            "runtime_build_id": "editor:test:agx_env_state_v2_4_107",
            "seed": 1000,
            "soil_preset_id": "unknown",
        },
    )

    token_a = _token(-0.2)
    token_b = _token(0.2)
    token_c = _token(0.6)
    token_by_step = {11: token_a, 13: token_a, 15: token_b, 17: token_b, 19: token_c}
    source_by_step = {
        11: "cell_0",
        13: "cell_0",
        15: "cell_4",
        17: "cell_4",
        19: "cell_1",
    }
    rows: list[dict[str, object]] = []
    for index, step_id in enumerate(step_ids):
        row: dict[str, object] = {
            "step_id": int(step_id),
            "action": actions[index].tolist(),
            "qpos": qpos[index].tolist(),
            "qvel": qvel[index].tolist(),
            "env_state": env_state[index].tolist(),
            "skill_name": "bootstrap",
            "primitive_cycle_index": 0,
            "skill_switch_reason": "",
            "box_safety_policy_restarted": False,
            "box_safety_reason": "",
            "box_safety_clearance_active": False,
            "box_safety_awaiting_neutral_ack": False,
        }
        if int(step_id) in token_by_step:
            row.update(
                {
                    "skill_name": "return",
                    "return_start_envelope_tokens": token_by_step[
                        int(step_id)
                    ].tolist(),
                    "return_start_envelope_token_source": source_by_step[int(step_id)],
                }
            )
        rows.append(row)
    jsonl_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )

    segment = {
        step_id: f"return:{step_id}-{step_id}:{_token_sha(token_by_step[step_id])[:12]}"
        for step_id in token_by_step
    }
    specs = (
        RecordedReturnFixtureSpec(
            "F1",
            "offline_failed",
            segment[11],
            11,
            10,
            segment[15],
            "goal_response_invalid",
        ),
        RecordedReturnFixtureSpec(
            "N1",
            "offline_normal",
            segment[13],
            13,
            12,
            segment[15],
            "goal_response_plausible",
        ),
        RecordedReturnFixtureSpec(
            "F2",
            "offline_failed",
            segment[15],
            15,
            14,
            segment[19],
            "goal_response_invalid",
        ),
        RecordedReturnFixtureSpec(
            "N2",
            "offline_normal",
            segment[17],
            17,
            16,
            segment[19],
            "goal_response_plausible",
        ),
    )
    record_by_segment: dict[str, dict[str, object]] = {}
    for spec in specs:
        alternate_step = 15 if spec.fixture_id in {"F1", "N1"} else 19
        alternate_token = token_by_step[alternate_step]
        alternate_sha = _token_sha(alternate_token)
        record_by_segment[spec.source_segment_id] = {
            "segment": {
                "segment_id": spec.source_segment_id,
                "start_action_step_id": spec.start_action_step_id,
                "end_action_step_id": spec.start_action_step_id,
                "token_sha256": _token_sha(token_by_step[spec.start_action_step_id]),
            },
            "alternate_segment": {
                "segment_id": spec.alternate_segment_id,
                "token_sha256": alternate_sha,
            },
            "result": {
                "conditions": {
                    "recorded_token": {"classification": "baseline"},
                    f"alternate_real_token_{alternate_sha[:12]}": {
                        "classification": spec.expected_classification
                    },
                }
            },
        }
    return_path = stage_root / "return.json"
    return_path.write_text(
        json.dumps(
            {
                "schema": "act_goal_condition_sensitivity_primitive_v1",
                "primitive": "return",
                "segment_pair_records": list(record_by_segment.values()),
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    manifest_path = stage_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema": "act_goal_condition_sensitivity_manifest_v1",
                "source_lineage": {
                    "rollout_hdf5": {"path": str(hdf5_path), "sha256": _sha(hdf5_path)},
                    "rollout_jsonl": {
                        "path": str(jsonl_path),
                        "sha256": _sha(jsonl_path),
                    },
                },
                "inference_instances": {
                    "baseline_replica_a": {"camera_names": list(CAMERAS)}
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return stage_root, specs


def test_build_freezes_four_pre_action_observations_targets_and_image_lineage(
    tmp_path: Path,
) -> None:
    stage_root, specs = _write_fixture_inputs(tmp_path)

    fixture_set = build_recorded_return_closed_loop_fixture_set(
        stage_a_v3_root=stage_root,
        fixture_specs=specs,
        camera_names=CAMERAS,
    )

    assert fixture_set.camera_names == CAMERAS
    assert [fixture.fixture_id for fixture in fixture_set.fixtures] == [
        "F1",
        "N1",
        "F2",
        "N2",
    ]
    first = fixture_set.fixtures[0]
    assert first.source_segment_id == specs[0].source_segment_id
    assert first.initial_observation.action_step_id == 11
    assert first.initial_observation.observation_step_id == 10
    np.testing.assert_allclose(first.initial_observation.qpos, [0.0, 0.01, 0.02, 0.03])
    np.testing.assert_allclose(
        first.initial_observation.qvel, [-0.5, -0.49, -0.48, -0.47]
    )
    assert first.initial_observation.env_state.shape == (107,)
    assert [
        item.camera_name for item in first.initial_observation.image_lineage
    ] == list(CAMERAS)
    assert all(
        len(item.rgb_sha256) == 64 for item in first.initial_observation.image_lineage
    )
    assert all(
        len(item.encoded_jpeg_sha256) == 64
        for item in first.initial_observation.image_lineage
    )
    assert first.original_target.target_role == "original"
    assert first.alternate_target.target_role == "alternate"
    assert first.original_target.token_sha256 != first.alternate_target.token_sha256
    assert fixture_set.as_dict()["fixtures"][0]["initial_observation"][
        "qpos"
    ] == pytest.approx([0.0, 0.01, 0.02, 0.03])
    assert (
        fixture_set.source_lineage["recorded_reset_context"]["terrain_restore_evidence"]
        == "observable_metrics_only_not_restorable"
    )


def test_builder_fails_closed_on_stage_classification_or_observation_drift(
    tmp_path: Path,
) -> None:
    stage_root, specs = _write_fixture_inputs(tmp_path)
    return_path = stage_root / "return.json"
    payload = json.loads(return_path.read_text(encoding="utf-8"))
    conditions = payload["segment_pair_records"][0]["result"]["conditions"]
    alternate_key = next(key for key in conditions if key != "recorded_token")
    conditions[alternate_key]["classification"] = "goal_response_plausible"
    return_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="classification"):
        build_recorded_return_closed_loop_fixture_set(
            stage_a_v3_root=stage_root,
            fixture_specs=specs,
            camera_names=CAMERAS,
        )

    _, specs = _write_fixture_inputs(tmp_path / "second")
    with pytest.raises(ValueError, match="pre-action observation"):
        RecordedReturnFixtureSpec(
            specs[1].fixture_id,
            specs[1].evidence_role,
            specs[1].source_segment_id,
            specs[1].start_action_step_id,
            11,
            specs[1].alternate_segment_id,
            specs[1].expected_classification,
        )


def test_frozen_fixture_specs_lock_production_stage_a_ids() -> None:
    assert [item.fixture_id for item in FROZEN_RETURN_FIXTURE_SPECS] == [
        "F1",
        "N1",
        "F2",
        "N2",
    ]
    assert [item.observation_step_id for item in FROZEN_RETURN_FIXTURE_SPECS] == [
        897,
        3452,
        3958,
        4436,
    ]
    assert [item.evidence_role for item in FROZEN_RETURN_FIXTURE_SPECS] == [
        "offline_failed",
        "offline_normal",
        "offline_failed",
        "offline_normal",
    ]
    assert [item.expected_classification for item in FROZEN_RETURN_FIXTURE_SPECS] == [
        "goal_response_invalid",
        "goal_response_plausible",
        "goal_response_invalid",
        "goal_response_plausible",
    ]
    assert (
        FROZEN_RETURN_FIXTURE_SPECS[0].alternate_segment_id
        == "return:3959-4161:4afcef2eee82"
    )
    assert (
        FROZEN_RETURN_FIXTURE_SPECS[2].alternate_segment_id
        == "return:2323-2534:87aa0fb8c981"
    )


@pytest.mark.parametrize(
    ("field", "bad_value", "message"),
    (
        ("schema", "wrong", "schema"),
        ("status", "artifact_invalid", "not completed"),
        ("evidence_kind", "closed_loop", "evidence kind"),
        ("diagnostic_only", False, "not diagnostic-only"),
        ("promotion_eligible", True, "promotion-eligible"),
        ("closed_loop_claim", True, "closed-loop claim"),
    ),
)
def test_production_wrapper_rejects_invalid_stage_a_evidence_boundary(
    tmp_path: Path,
    field: str,
    bad_value: object,
    message: str,
) -> None:
    stage_root, _ = _write_fixture_inputs(tmp_path)
    manifest_path = stage_root / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload.update(
        {
            "status": "completed",
            "evidence_kind": "teacher_forced_recorded_observation",
            "diagnostic_only": True,
            "promotion_eligible": False,
            "closed_loop_claim": False,
        }
    )
    payload[field] = bad_value
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_frozen_recorded_return_closed_loop_fixture_set(stage_a_v3_root=stage_root)
