from __future__ import annotations

import torch

from testbed.policies.dig_transition_predictor import (
    DIG_JOINT_TRANSITION_MODEL_SCHEMA,
    YULONG_QPOS_RAW_RANGE_RAD,
    DigJointTransitionModel,
    load_joint_transition_checkpoint,
    rollout_joint_transition,
)


def test_transition_model_derives_next_qpos_from_predicted_next_qvel() -> None:
    model = DigJointTransitionModel(hidden_dim=16)
    for parameter in model.parameters():
        torch.nn.init.zeros_(parameter)
    qpos = torch.full((2, 4), 0.5)
    qvel = torch.tensor([[0.1, -0.2, 0.3, -0.4]]).repeat(2, 1)
    action = torch.zeros(2, 4)

    result = model(qpos, qvel, action)

    torch.testing.assert_close(result.next_qvel, qvel)
    expected = qpos + qvel * 0.02 / YULONG_QPOS_RAW_RANGE_RAD
    torch.testing.assert_close(result.next_qpos, expected)


def test_rollout_reports_requested_horizons_without_teacher_forcing() -> None:
    model = DigJointTransitionModel(hidden_dim=16)
    for parameter in model.parameters():
        torch.nn.init.zeros_(parameter)
    qpos = torch.zeros(1, 4)
    qvel = torch.ones(1, 4) * 0.1
    actions = torch.zeros(1, 100, 4)

    rollout = rollout_joint_transition(
        model=model,
        initial_qpos=qpos,
        initial_qvel=qvel,
        actions=actions,
        horizons=(1, 5, 10, 25, 50, 100),
    )

    assert rollout.qpos.shape == (1, 100, 4)
    assert rollout.qvel.shape == (1, 100, 4)
    assert tuple(rollout.horizon_indices) == (1, 5, 10, 25, 50, 100)
    torch.testing.assert_close(rollout.qvel[:, -1], qvel)


def test_transition_hard_projects_known_normalized_qpos_range() -> None:
    model = DigJointTransitionModel(hidden_dim=16)
    for parameter in model.parameters():
        torch.nn.init.zeros_(parameter)
    prediction = model(
        torch.full((1, 4), 0.9999),
        torch.full((1, 4), 10.0),
        torch.zeros(1, 4),
    )

    assert torch.all(prediction.next_qpos <= 1.0)
    assert torch.all(prediction.next_qpos >= 0.0)
    assert float(prediction.next_qpos.max().detach()) == 1.0


def test_checkpoint_loader_can_freeze_all_joint_parameters(tmp_path) -> None:
    model = DigJointTransitionModel(hidden_dim=16)
    checkpoint = tmp_path / "joint.pt"
    torch.save(
        {
            "schema": DIG_JOINT_TRANSITION_MODEL_SCHEMA,
            "hidden_dim": 16,
            "input_mean": model.input_mean.tolist(),
            "input_scale": model.input_scale.tolist(),
            "delta_qvel_mean": model.delta_qvel_mean.tolist(),
            "delta_qvel_scale": model.delta_qvel_scale.tolist(),
            "state_dict": model.state_dict(),
        },
        checkpoint,
    )

    loaded = load_joint_transition_checkpoint(
        checkpoint,
        device="cpu",
        frozen=True,
    )

    assert loaded.training is False
    assert all(not parameter.requires_grad for parameter in loaded.parameters())
