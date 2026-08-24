"""One-step YuLong joint transition model with explicit qvel-to-qpos integration."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch

DIG_JOINT_TRANSITION_MODEL_SCHEMA = "dig_joint_transition_model_v1"
YULONG_QPOS_RAW_RANGE_RAD = torch.tensor(
    [
        6.2831854820251465,
        0.9955732524394989,
        1.8719636797904968,
        2.483125865459442,
    ],
    dtype=torch.float32,
)
CONTROL_DT_S = 0.02


@dataclass(frozen=True)
class JointTransitionPrediction:
    next_qpos: torch.Tensor
    next_qvel: torch.Tensor


@dataclass(frozen=True)
class JointTransitionRollout:
    qpos: torch.Tensor
    qvel: torch.Tensor
    horizon_indices: tuple[int, ...]


class DigJointTransitionModel(torch.nn.Module):
    """Predict next qvel; derive next qpos from the observed integration contract."""

    def __init__(
        self,
        *,
        hidden_dim: int = 256,
        input_mean: Sequence[float] | np.ndarray | None = None,
        input_scale: Sequence[float] | np.ndarray | None = None,
        delta_qvel_mean: Sequence[float] | np.ndarray | None = None,
        delta_qvel_scale: Sequence[float] | np.ndarray | None = None,
    ) -> None:
        super().__init__()
        if hidden_dim <= 0:
            raise ValueError("transition hidden_dim must be positive")
        self.hidden_dim = int(hidden_dim)
        self.network = torch.nn.Sequential(
            torch.nn.Linear(12, hidden_dim),
            torch.nn.SiLU(),
            torch.nn.Linear(hidden_dim, hidden_dim),
            torch.nn.SiLU(),
            torch.nn.Linear(hidden_dim, hidden_dim),
            torch.nn.SiLU(),
            torch.nn.Linear(hidden_dim, 4),
        )
        self.register_buffer("input_mean", _vector(input_mean, 12, 0.0))
        self.register_buffer("input_scale", _scale(input_scale, 12))
        self.register_buffer("delta_qvel_mean", _vector(delta_qvel_mean, 4, 0.0))
        self.register_buffer("delta_qvel_scale", _scale(delta_qvel_scale, 4))
        self.register_buffer("qpos_raw_range_rad", YULONG_QPOS_RAW_RANGE_RAD.clone())

    def forward(
        self,
        qpos: torch.Tensor,
        qvel: torch.Tensor,
        action: torch.Tensor,
    ) -> JointTransitionPrediction:
        for value, label in ((qpos, "qpos"), (qvel, "qvel"), (action, "action")):
            if value.ndim != 2 or value.shape[1] != 4:
                raise ValueError(f"transition {label} must have shape [B,4]")
        if not (qpos.shape == qvel.shape == action.shape):
            raise ValueError("transition state/action batch mismatch")
        features = torch.cat((qpos, qvel, action), dim=-1)
        normalized = (features - self.input_mean) / self.input_scale
        normalized_delta = self.network(normalized)
        delta_qvel = normalized_delta * self.delta_qvel_scale + self.delta_qvel_mean
        next_qvel = qvel + delta_qvel
        next_qpos = torch.clamp(
            qpos + next_qvel * CONTROL_DT_S / self.qpos_raw_range_rad,
            min=0.0,
            max=1.0,
        )
        return JointTransitionPrediction(next_qpos=next_qpos, next_qvel=next_qvel)


def load_joint_transition_checkpoint(
    path: str | Path,
    *,
    device: str | torch.device,
    frozen: bool = False,
) -> DigJointTransitionModel:
    checkpoint_path = Path(path).expanduser().resolve(strict=True)
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
    if checkpoint.get("schema") != DIG_JOINT_TRANSITION_MODEL_SCHEMA:
        raise ValueError("joint transition checkpoint schema mismatch")
    model = DigJointTransitionModel(
        hidden_dim=int(checkpoint["hidden_dim"]),
        input_mean=checkpoint["input_mean"],
        input_scale=checkpoint["input_scale"],
        delta_qvel_mean=checkpoint["delta_qvel_mean"],
        delta_qvel_scale=checkpoint["delta_qvel_scale"],
    ).to(device)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    if frozen:
        for parameter in model.parameters():
            parameter.requires_grad_(False)
    return model


def rollout_joint_transition(
    *,
    model: DigJointTransitionModel,
    initial_qpos: torch.Tensor,
    initial_qvel: torch.Tensor,
    actions: torch.Tensor,
    horizons: Sequence[int] = (1, 5, 10, 25, 50, 100),
) -> JointTransitionRollout:
    if actions.ndim != 3 or actions.shape[-1] != 4:
        raise ValueError("transition rollout actions must have shape [B,T,4]")
    if initial_qpos.shape != initial_qvel.shape or initial_qpos.shape != (
        actions.shape[0],
        4,
    ):
        raise ValueError("transition rollout initial state shape mismatch")
    horizon_indices = tuple(int(value) for value in horizons)
    if (
        not horizon_indices
        or any(value <= 0 or value > actions.shape[1] for value in horizon_indices)
        or tuple(sorted(set(horizon_indices))) != horizon_indices
    ):
        raise ValueError("transition rollout horizons are invalid")
    qpos = initial_qpos
    qvel = initial_qvel
    qpos_rows: list[torch.Tensor] = []
    qvel_rows: list[torch.Tensor] = []
    for step in range(actions.shape[1]):
        prediction = model(qpos, qvel, actions[:, step])
        qpos = prediction.next_qpos
        qvel = prediction.next_qvel
        qpos_rows.append(qpos)
        qvel_rows.append(qvel)
    return JointTransitionRollout(
        qpos=torch.stack(qpos_rows, dim=1),
        qvel=torch.stack(qvel_rows, dim=1),
        horizon_indices=horizon_indices,
    )


def _vector(
    value: Sequence[float] | np.ndarray | None,
    length: int,
    default: float,
) -> torch.Tensor:
    array = (
        np.full(length, default, dtype=np.float32)
        if value is None
        else np.asarray(value, dtype=np.float32)
    )
    if array.shape != (length,) or not np.isfinite(array).all():
        raise ValueError("transition normalization vector is invalid")
    return torch.from_numpy(array.copy())


def _scale(
    value: Sequence[float] | np.ndarray | None,
    length: int,
) -> torch.Tensor:
    result = _vector(value, length, 1.0)
    if torch.any(result <= 0.0):
        raise ValueError("transition normalization scale must be positive")
    return result


__all__ = [
    "CONTROL_DT_S",
    "DIG_JOINT_TRANSITION_MODEL_SCHEMA",
    "YULONG_QPOS_RAW_RANGE_RAD",
    "DigJointTransitionModel",
    "JointTransitionPrediction",
    "JointTransitionRollout",
    "load_joint_transition_checkpoint",
    "rollout_joint_transition",
]
