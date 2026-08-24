from __future__ import annotations

import numpy as np
import pytest
import torch

from testbed.eval.dig_receding_horizon_projection_runtime import (
    build_sliding_projection_windows,
    paired_projection_key,
)
from testbed.eval.dig_short_horizon_projection import (
    project_frozen_joint_tip_ensemble,
)
from testbed.policies.dig_transition_predictor import JointTransitionPrediction


class _LinearDynamics(torch.nn.Module):
    def __init__(self, *, frozen: bool = True) -> None:
        super().__init__()
        self.offset = torch.nn.Parameter(torch.zeros(4))
        self.offset.requires_grad_(not frozen)
        self.eval()

    def forward(
        self,
        qpos: torch.Tensor,
        qvel: torch.Tensor,
        action: torch.Tensor,
    ) -> JointTransitionPrediction:
        next_qpos = qpos + action * 0.01 + self.offset
        return JointTransitionPrediction(next_qpos=next_qpos, next_qvel=qvel)


class _TipFK(torch.nn.Module):
    def forward(self, qpos: torch.Tensor) -> torch.Tensor:
        return qpos[..., :3]


def test_short_projection_uses_only_frozen_models_and_reports_5_10_steps() -> None:
    models = [_LinearDynamics(), _LinearDynamics()]
    actions = np.ones((2, 10, 4), dtype=np.float32)

    result = project_frozen_joint_tip_ensemble(
        models=models,
        fixed_tip_fk=_TipFK(),
        initial_qpos=np.zeros((2, 4), dtype=np.float32),
        initial_qvel=np.zeros((2, 4), dtype=np.float32),
        actions=actions,
        horizons=(5, 10),
        device="cpu",
    )

    assert result["evidence_kind"] == "short_horizon_projection_only"
    assert result["tip_xyz_m"].shape == (2, 10, 3)
    np.testing.assert_allclose(result["tip_xyz_m"][:, 4], 0.05, atol=1e-7)
    np.testing.assert_allclose(result["tip_xyz_m"][:, 9], 0.10, atol=1e-7)
    assert result["horizons"] == (5, 10)
    assert result["model_count"] == 2


def test_short_projection_rejects_trainable_dynamics() -> None:
    with pytest.raises(ValueError, match="fully frozen"):
        project_frozen_joint_tip_ensemble(
            models=[_LinearDynamics(frozen=False)],
            fixed_tip_fk=_TipFK(),
            initial_qpos=np.zeros((1, 4), dtype=np.float32),
            initial_qvel=np.zeros((1, 4), dtype=np.float32),
            actions=np.zeros((1, 10, 4), dtype=np.float32),
            horizons=(5, 10),
            device="cpu",
        )


def test_projection_identity_keeps_same_variant_token_in_distinct_episodes() -> None:
    first = paired_projection_key(
        {"source_episode_id": 3, "primitive_episode_id": 10, "variant_id": "same"}
    )
    second = paired_projection_key(
        {"source_episode_id": 3, "primitive_episode_id": 11, "variant_id": "same"}
    )

    assert first != second


def test_sliding_projection_uses_91_real_state_anchors_over_100_frames() -> None:
    qpos = np.arange(2 * 100 * 4, dtype=np.float32).reshape(2, 100, 4)
    qvel = qpos + 1.0
    actions = qpos + 2.0

    windows = build_sliding_projection_windows(
        recorded_qpos=qpos,
        recorded_qvel=qvel,
        actions=actions,
    )

    assert windows["initial_qpos"].shape == (182, 4)
    assert windows["initial_qvel"].shape == (182, 4)
    assert windows["actions"].shape == (182, 10, 4)
    assert windows["owner_index"].shape == (182,)
    assert windows["anchor_frame_index"].shape == (182,)
    assert windows["anchor_frame_index"][:91].tolist() == list(range(91))
    np.testing.assert_array_equal(windows["actions"][91], actions[1, :10])
