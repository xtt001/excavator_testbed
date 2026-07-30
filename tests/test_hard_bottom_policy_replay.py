from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from testbed.eval.hard_bottom_policy_replay import (
    HARD_BOTTOM_POLICY_REPLAY_SCHEMA,
    replay_independent_goal_policy_actions,
    write_policy_replay_artifact,
)


class _FakePolicy:
    def __init__(self, offset: float) -> None:
        self.offset = float(offset)
        self.temporal_step = 999
        self.reset_count = 0

    def reset(self) -> None:
        self.temporal_step = 0
        self.reset_count += 1

    def predict_with_outcome(
        self,
        obs: dict[str, np.ndarray],
    ) -> tuple[np.ndarray, None]:
        token = np.asarray(obs["dig_cut_tokens"], dtype=np.float32)
        return (
            np.asarray(
                [
                    self.offset,
                    float(token[0]),
                    float(token[1]),
                    -float(token[7]),
                ],
                dtype=np.float32,
            ),
            None,
        )

    def predict(self, obs: dict[str, np.ndarray]) -> np.ndarray:
        action, _ = self.predict_with_outcome(obs)
        action = action + np.float32(self.temporal_step * 0.01)
        self.temporal_step += 1
        return action


def _frames() -> list[dict[str, object]]:
    return [
        {
            "action_step_id": 100 + index,
            "observation_step_id": 99 + index,
            "observation_hdf5_index": index,
            "qpos": [0.0, 0.1, 0.2, 0.3],
            "qvel": [0.4, 0.5, 0.6, 0.7],
            "actual_action": [0.1, 0.2, 0.3, 0.4],
        }
        for index in range(3)
    ]


def _targets() -> dict[str, dict[str, object]]:
    return {
        target_id: {
            "dig_cut_tokens": [
                float(index),
                float(index + 1),
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                float(index + 2),
                1.0,
                1.0,
            ]
        }
        for index, target_id in enumerate(("M0", "E1", "W1"))
    }


def _nearest() -> dict[str, dict[int, list[float]]]:
    return {
        target_id: {
            step_id: [0.0, -0.1, -0.2, 0.3]
            for step_id in (100, 101, 102)
        }
        for target_id in ("M0", "E1", "W1")
    }


def test_replay_uses_three_distinct_reset_temporal_states() -> None:
    created: list[_FakePolicy] = []

    def policy_factory(target_id: str) -> _FakePolicy:
        policy = _FakePolicy(float(("M0", "E1", "W1").index(target_id)))
        created.append(policy)
        return policy

    replay = replay_independent_goal_policy_actions(
        frames=_frames(),
        targets=_targets(),
        nearest_expert_actions=_nearest(),
        policy_factory=policy_factory,
        observation_images=lambda _frame: {
            "image_stick_up": np.zeros((3, 2, 2), dtype=np.float32),
            "image_stick_down": np.zeros((3, 2, 2), dtype=np.float32),
            "image_eye_left": np.zeros((3, 2, 2), dtype=np.float32),
            "image_eye_right": np.zeros((3, 2, 2), dtype=np.float32),
        },
    )

    assert len(created) == 3
    assert len({id(policy) for policy in created}) == 3
    assert [policy.reset_count for policy in created] == [1, 1, 1]
    assert replay["independent_policy_state_contract"]["status"] == "passed"
    assert replay["targets"]["M0"]["records"][0]["aggregated_action"] == (
        replay["targets"]["M0"]["records"][0]["fresh_action"]
    )
    assert replay["targets"]["M0"]["records"][1]["aggregated_action"][0] == (
        pytest.approx(0.01)
    )
    assert replay["targets"]["E1"]["records"][0]["fresh_action"] != (
        replay["targets"]["M0"]["records"][0]["fresh_action"]
    )


def test_replay_rejects_reused_policy_instance() -> None:
    shared = _FakePolicy(0.0)

    with pytest.raises(ValueError, match="distinct policy instance"):
        replay_independent_goal_policy_actions(
            frames=_frames(),
            targets=_targets(),
            nearest_expert_actions=_nearest(),
            policy_factory=lambda _target_id: shared,
            observation_images=lambda _frame: {},
        )


def test_policy_replay_artifact_is_no_overwrite(tmp_path: Path) -> None:
    artifact = {
        "schema": HARD_BOTTOM_POLICY_REPLAY_SCHEMA,
        "status": "complete",
    }
    output_dir = tmp_path / "policy_replay"

    path = write_policy_replay_artifact(
        output_dir=output_dir,
        artifact=artifact,
    )

    assert json.loads(path.read_text(encoding="utf-8")) == artifact
    with pytest.raises(FileExistsError):
        write_policy_replay_artifact(
            output_dir=output_dir,
            artifact=artifact,
        )
