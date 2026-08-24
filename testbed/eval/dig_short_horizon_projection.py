"""Frozen 5/10-step joint-dynamics plus fixed-tip diagnostic projection."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import torch

from testbed.policies.dig_transition_predictor import rollout_joint_transition

ALLOWED_HORIZONS = (5, 10)


def project_frozen_joint_tip_ensemble(
    *,
    models: Sequence[torch.nn.Module],
    fixed_tip_fk: torch.nn.Module,
    initial_qpos: np.ndarray,
    initial_qvel: np.ndarray,
    actions: np.ndarray,
    horizons: tuple[int, ...] = ALLOWED_HORIZONS,
    device: str | torch.device = "cpu",
) -> dict[str, Any]:
    """Project exactly ten actions without training, reanchoring, or long rollout."""
    if tuple(horizons) != ALLOWED_HORIZONS:
        raise ValueError("Dig diagnostic projection horizons are frozen at 5/10")
    if not models:
        raise ValueError("short projection requires a frozen dynamics ensemble")
    for model in models:
        if model.training or any(
            parameter.requires_grad for parameter in model.parameters()
        ):
            raise ValueError(
                "short projection dynamics must be fully frozen in eval mode"
            )
    positions = _matrix(initial_qpos, "initial_qpos")
    velocities = _matrix(initial_qvel, "initial_qvel")
    action_values = np.asarray(actions, dtype=np.float32)
    if (
        action_values.ndim != 3
        or action_values.shape[1:] != (10, 4)
        or not np.isfinite(action_values).all()
    ):
        raise ValueError("short projection actions must be finite [batch,10,4]")
    if (
        positions.shape != velocities.shape
        or positions.shape[0] != action_values.shape[0]
    ):
        raise ValueError("short projection state/action batch mismatch")

    target_device = torch.device(device)
    qpos = torch.as_tensor(positions, dtype=torch.float32, device=target_device)
    qvel = torch.as_tensor(velocities, dtype=torch.float32, device=target_device)
    action_tensor = torch.as_tensor(
        action_values, dtype=torch.float32, device=target_device
    )
    fixed_tip_fk = fixed_tip_fk.to(target_device)
    fixed_tip_fk.eval()
    member_tips = []
    with torch.inference_mode():
        initial_tip = fixed_tip_fk(qpos)
        for model in models:
            model = model.to(target_device)
            rollout = rollout_joint_transition(
                model=model,
                initial_qpos=qpos,
                initial_qvel=qvel,
                actions=action_tensor,
                horizons=ALLOWED_HORIZONS,
            )
            member_tips.append(fixed_tip_fk(rollout.qpos))
    stacked = torch.stack(member_tips, dim=0)
    mean_tip = stacked.mean(dim=0)
    coordinate_std = stacked.std(dim=0, unbiased=False)
    radial_std = torch.linalg.vector_norm(coordinate_std, dim=-1)
    return {
        "evidence_kind": "short_horizon_projection_only",
        "horizons": ALLOWED_HORIZONS,
        "model_count": len(models),
        "initial_tip_xyz_m": initial_tip.cpu().numpy(),
        "tip_xyz_m": mean_tip.cpu().numpy(),
        "tip_coordinate_std_m": coordinate_std.cpu().numpy(),
        "tip_radial_std_m": radial_std.cpu().numpy(),
        "endpoint_tip_xyz_m": {
            horizon: mean_tip[:, horizon - 1].cpu().numpy()
            for horizon in ALLOWED_HORIZONS
        },
    }


def _matrix(value: np.ndarray, label: str) -> np.ndarray:
    result = np.asarray(value, dtype=np.float32)
    if result.ndim != 2 or result.shape[1] != 4 or not np.isfinite(result).all():
        raise ValueError(f"{label} must be finite [batch,4]")
    return result


__all__ = ["ALLOWED_HORIZONS", "project_frozen_joint_tip_ensemble"]
