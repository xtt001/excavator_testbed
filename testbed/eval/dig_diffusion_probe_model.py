"""Small conditional DDPM/DDIM used only by the offline Dig probe."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F


@dataclass(frozen=True)
class DiffusionSchedule:
    betas: torch.Tensor
    alphas: torch.Tensor
    alpha_bars: torch.Tensor

    @classmethod
    def create(
        cls,
        *,
        train_timesteps: int = 50,
        beta_start: float = 1.0e-4,
        beta_end: float = 2.0e-2,
    ) -> DiffusionSchedule:
        if train_timesteps < 2:
            raise ValueError("diffusion schedule requires at least two timesteps")
        betas = torch.linspace(beta_start, beta_end, train_timesteps)
        alphas = 1.0 - betas
        return cls(betas=betas, alphas=alphas, alpha_bars=torch.cumprod(alphas, 0))

    @property
    def train_timesteps(self) -> int:
        return int(self.betas.numel())

    def to(self, device: torch.device | str) -> DiffusionSchedule:
        return DiffusionSchedule(
            betas=self.betas.to(device),
            alphas=self.alphas.to(device),
            alpha_bars=self.alpha_bars.to(device),
        )

    def q_sample(
        self, clean: torch.Tensor, noise: torch.Tensor, timestep: torch.Tensor
    ) -> torch.Tensor:
        if clean.shape != noise.shape:
            raise ValueError("clean actions and diffusion noise must match")
        alpha_bar = self.alpha_bars.to(clean.device)[timestep].reshape(-1, 1, 1)
        return torch.sqrt(alpha_bar) * clean + torch.sqrt(1.0 - alpha_bar) * noise


class _CameraEncoder(torch.nn.Module):
    def __init__(self, feature_dim: int) -> None:
        super().__init__()
        self.network = torch.nn.Sequential(
            torch.nn.Conv2d(1, 8, kernel_size=3, stride=2, padding=1),
            torch.nn.SiLU(),
            torch.nn.Conv2d(8, 16, kernel_size=3, stride=2, padding=1),
            torch.nn.SiLU(),
            torch.nn.Conv2d(16, feature_dim, kernel_size=3, stride=2, padding=1),
            torch.nn.SiLU(),
            torch.nn.AdaptiveAvgPool2d(1),
        )

    def forward(self, images: torch.Tensor) -> torch.Tensor:
        return self.network(images).flatten(1)


class _ConditionedResidualBlock(torch.nn.Module):
    def __init__(self, hidden_dim: int, dilation: int) -> None:
        super().__init__()
        groups = max(
            group
            for group in range(min(8, hidden_dim), 0, -1)
            if hidden_dim % group == 0
        )
        self.norm = torch.nn.GroupNorm(groups, hidden_dim)
        self.conv = torch.nn.Conv1d(
            hidden_dim,
            hidden_dim,
            kernel_size=3,
            padding=dilation,
            dilation=dilation,
        )
        self.condition = torch.nn.Linear(hidden_dim, hidden_dim * 2)

    def forward(self, value: torch.Tensor, condition: torch.Tensor) -> torch.Tensor:
        scale, shift = self.condition(condition).chunk(2, dim=-1)
        hidden = self.norm(value)
        hidden = hidden * (1.0 + scale[:, :, None]) + shift[:, :, None]
        return value + self.conv(F.silu(hidden))


class MinimalConditionalDiffusionPolicy(torch.nn.Module):
    """A compact temporal noise predictor with a shared four-camera encoder."""

    def __init__(
        self,
        *,
        camera_count: int = 4,
        low_dim: int = 18,
        action_horizon: int = 100,
        action_dim: int = 4,
        hidden_dim: int = 128,
        camera_feature_dim: int = 32,
    ) -> None:
        super().__init__()
        if (camera_count, low_dim, action_horizon, action_dim) != (4, 18, 100, 4):
            raise ValueError(
                "minimal Dig DP contract is fixed at 4 cameras, 18D, 100x4"
            )
        self.contract = {
            "camera_count": camera_count,
            "low_dim": low_dim,
            "action_horizon": action_horizon,
            "action_dim": action_dim,
            "temporal_aggregation": False,
        }
        self.camera_encoder = _CameraEncoder(camera_feature_dim)
        self.low_dim_encoder = torch.nn.Sequential(
            torch.nn.Linear(low_dim, hidden_dim), torch.nn.SiLU()
        )
        self.image_condition = torch.nn.Sequential(
            torch.nn.Linear(camera_count * camera_feature_dim, hidden_dim),
            torch.nn.SiLU(),
        )
        self.time_condition = torch.nn.Sequential(
            torch.nn.Linear(32, hidden_dim),
            torch.nn.SiLU(),
            torch.nn.Linear(hidden_dim, hidden_dim),
        )
        self.input_projection = torch.nn.Conv1d(action_dim, hidden_dim, 3, padding=1)
        self.blocks = torch.nn.ModuleList(
            [
                _ConditionedResidualBlock(hidden_dim, dilation)
                for dilation in (1, 2, 4, 8)
            ]
        )
        groups = max(
            group
            for group in range(min(8, hidden_dim), 0, -1)
            if hidden_dim % group == 0
        )
        self.output = torch.nn.Sequential(
            torch.nn.GroupNorm(groups, hidden_dim),
            torch.nn.SiLU(),
            torch.nn.Conv1d(hidden_dim, action_dim, 3, padding=1),
        )

    def encode_images(self, images: torch.Tensor) -> torch.Tensor:
        if images.ndim != 5 or images.shape[1:] != (4, 1, 32, 32):
            raise ValueError("minimal DP images must be [B,4,1,32,32]")
        batch = images.shape[0]
        features = self.camera_encoder(images.reshape(batch * 4, 1, 32, 32))
        return features.reshape(batch, -1)

    def forward(
        self,
        noisy_actions: torch.Tensor,
        timestep: torch.Tensor,
        low_dim: torch.Tensor,
        images: torch.Tensor | None = None,
        *,
        image_features: torch.Tensor | None = None,
    ) -> torch.Tensor:
        if noisy_actions.ndim != 3 or noisy_actions.shape[1:] != (100, 4):
            raise ValueError("minimal DP noisy actions must be [B,100,4]")
        if low_dim.shape != (noisy_actions.shape[0], 18):
            raise ValueError("minimal DP low-dimensional condition must be [B,18]")
        if image_features is None:
            if images is None:
                raise ValueError(
                    "minimal DP requires images or precomputed image features"
                )
            image_features = self.encode_images(images)
        time = _sinusoidal_timestep_embedding(timestep, dimension=32)
        condition = (
            self.low_dim_encoder(low_dim)
            + self.image_condition(image_features)
            + self.time_condition(time)
        )
        hidden = self.input_projection(noisy_actions.transpose(1, 2))
        for block in self.blocks:
            hidden = block(hidden, condition)
        return self.output(hidden).transpose(1, 2)


@torch.inference_mode()
def sample_action_chunks(
    *,
    model: MinimalConditionalDiffusionPolicy,
    schedule: DiffusionSchedule,
    images: torch.Tensor | None,
    low_dim: torch.Tensor,
    initial_noise: torch.Tensor,
    inference_steps: int,
    image_features: torch.Tensor | None = None,
) -> torch.Tensor:
    if inference_steps < 2 or inference_steps > schedule.train_timesteps:
        raise ValueError("inference steps must be within the diffusion schedule")
    model.eval()
    schedule = schedule.to(initial_noise.device)
    timesteps = (
        torch.linspace(
            schedule.train_timesteps - 1,
            0,
            inference_steps,
            device=initial_noise.device,
        )
        .round()
        .long()
    )
    value = initial_noise.clone()
    for index, timestep_value in enumerate(timesteps):
        timestep = torch.full(
            (value.shape[0],),
            int(timestep_value.item()),
            dtype=torch.long,
            device=value.device,
        )
        predicted_noise = model(
            value,
            timestep,
            low_dim,
            images,
            image_features=image_features,
        )
        alpha_bar = schedule.alpha_bars[timestep_value]
        clean = (value - torch.sqrt(1.0 - alpha_bar) * predicted_noise) / torch.sqrt(
            alpha_bar
        )
        if index + 1 == len(timesteps):
            value = clean
        else:
            previous_alpha_bar = schedule.alpha_bars[timesteps[index + 1]]
            value = (
                torch.sqrt(previous_alpha_bar) * clean
                + torch.sqrt(1.0 - previous_alpha_bar) * predicted_noise
            )
    return value


@dataclass(frozen=True)
class DiffusionDispatchFrame:
    raw_action_chunk: np.ndarray
    dispatched_action: np.ndarray
    contributing_chunk_ages: tuple[int, ...] = (0,)
    temporal_aggregation_used: bool = False


class LatestObservationDiffusionDispatcher:
    def __init__(
        self,
        *,
        chunk_sampler: Callable[..., np.ndarray],
        inference_noise_seed: int,
    ) -> None:
        self.chunk_sampler = chunk_sampler
        self.inference_noise_seed = int(inference_noise_seed)

    def dispatch(
        self, observation: dict[str, Any], token: Sequence[float] | np.ndarray
    ) -> DiffusionDispatchFrame:
        bound = dict(observation)
        bound["dig_cut_tokens"] = np.asarray(token, dtype=np.float32).reshape(10)
        chunk = np.asarray(
            self.chunk_sampler(bound, noise_seed=self.inference_noise_seed),
            dtype=np.float32,
        )
        if chunk.shape != (100, 4):
            raise ValueError("DP chunk sampler must return [100,4]")
        return DiffusionDispatchFrame(
            raw_action_chunk=chunk.copy(),
            dispatched_action=chunk[0].copy(),
        )


def _sinusoidal_timestep_embedding(
    timestep: torch.Tensor, *, dimension: int
) -> torch.Tensor:
    half = dimension // 2
    frequency = torch.exp(
        -math.log(10_000.0)
        * torch.arange(half, device=timestep.device, dtype=torch.float32)
        / max(half - 1, 1)
    )
    angle = timestep.float()[:, None] * frequency[None]
    return torch.cat((torch.sin(angle), torch.cos(angle)), dim=1)


__all__ = [
    "DiffusionDispatchFrame",
    "DiffusionSchedule",
    "LatestObservationDiffusionDispatcher",
    "MinimalConditionalDiffusionPolicy",
    "sample_action_chunks",
]
