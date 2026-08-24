"""Fixed-budget three-seed training for the non-promotable minimal DP probe."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F

from testbed.eval.dig_diffusion_probe_data import SourceEpisodeBalancedSampler
from testbed.eval.dig_diffusion_probe_model import (
    DiffusionSchedule,
    MinimalConditionalDiffusionPolicy,
)


@dataclass(frozen=True)
class MinimalDPTrainingConfig:
    updates: int = 1000
    batch_size: int = 128
    learning_rate: float = 1.0e-4
    weight_decay: float = 1.0e-5
    ema_decay: float = 0.995
    hidden_dim: int = 64
    camera_feature_dim: int = 16
    train_timesteps: int = 50

    def __post_init__(self) -> None:
        if self.updates < 1 or self.batch_size < 1 or self.hidden_dim < 8:
            raise ValueError("minimal DP training dimensions must be positive")
        if not 0.0 < self.ema_decay < 1.0:
            raise ValueError("minimal DP EMA decay must be in (0,1)")


def train_minimal_dp_seed(
    *,
    arrays: dict[str, np.ndarray],
    norm_stats: dict[str, np.ndarray],
    seed: int,
    output_dir: str | Path,
    config: MinimalDPTrainingConfig,
    device: str | torch.device,
    lineage: dict[str, Any],
) -> dict[str, Any]:
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=False)
    values = _validate_arrays(arrays)
    stats = {
        name: value.to(device) for name, value in _validate_stats(norm_stats).items()
    }
    if np.isin(values["source_episode_id"], [33, 34]).any():
        raise ValueError("source 33/34 cannot enter minimal DP training")
    target_device = torch.device(device)
    torch.manual_seed(int(seed))
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(int(seed))
    model = MinimalConditionalDiffusionPolicy(
        hidden_dim=config.hidden_dim,
        camera_feature_dim=config.camera_feature_dim,
    ).to(target_device)
    schedule = DiffusionSchedule.create(train_timesteps=config.train_timesteps).to(
        target_device
    )
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    ema = {
        name: tensor.detach().clone()
        for name, tensor in model.state_dict().items()
        if torch.is_floating_point(tensor)
    }
    sampler = SourceEpisodeBalancedSampler(
        values["source_episode_id"], values["primitive_episode_id"]
    )
    losses = []
    generator = torch.Generator(device=target_device).manual_seed(int(seed) + 10_000)
    model.train()
    for update in range(config.updates):
        indices = sampler.sample_indices(
            batch_size=config.batch_size,
            seed=int(seed) * 10_000_000 + update,
        )
        images = (
            torch.as_tensor(
                values["images"][indices, :, None],
                dtype=torch.float32,
                device=target_device,
            )
            / 255.0
        )
        proprio = torch.as_tensor(
            values["proprio"][indices], dtype=torch.float32, device=target_device
        )
        proprio = (proprio - stats["proprio_mean"]) / stats["proprio_std"]
        actions = torch.as_tensor(
            values["actions"][indices], dtype=torch.float32, device=target_device
        )
        actions = (actions - stats["action_mean"]) / stats["action_std"]
        noise = torch.randn(
            actions.shape,
            generator=generator,
            dtype=actions.dtype,
            device=target_device,
        )
        timestep = torch.randint(
            0,
            schedule.train_timesteps,
            (actions.shape[0],),
            generator=generator,
            device=target_device,
        )
        noisy = schedule.q_sample(actions, noise, timestep)
        predicted = model(noisy, timestep, proprio, images)
        loss = F.mse_loss(predicted, noise)
        optimizer.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
        with torch.no_grad():
            state = model.state_dict()
            for name, average in ema.items():
                average.mul_(config.ema_decay).add_(
                    state[name].detach(), alpha=1.0 - config.ema_decay
                )
        losses.append(float(loss.detach().cpu()))
    state = model.state_dict()
    ema_state = {
        name: (ema[name] if name in ema else tensor.detach().clone())
        for name, tensor in state.items()
    }
    checkpoint = {
        "schema": "minimal_dig_diffusion_probe_checkpoint_v1",
        "seed": int(seed),
        "training_config": asdict(config),
        "model_config": {
            "hidden_dim": config.hidden_dim,
            "camera_feature_dim": config.camera_feature_dim,
        },
        "ema_state_dict": {name: value.cpu() for name, value in ema_state.items()},
        "norm_stats": {name: value.detach().cpu() for name, value in stats.items()},
        "schedule": {
            "train_timesteps": config.train_timesteps,
            "betas": schedule.betas.detach().cpu(),
        },
        "lineage": dict(lineage),
        "optimizer_state_saved": False,
        "promotion_eligible": False,
    }
    checkpoint_path = destination / "checkpoint.pt"
    if checkpoint_path.exists():
        raise FileExistsError(checkpoint_path)
    torch.save(checkpoint, checkpoint_path)
    history = {
        "schema": "minimal_dig_diffusion_probe_training_history_v1",
        "seed": int(seed),
        "updates_completed": config.updates,
        "loss": losses,
        "final_loss": losses[-1],
        "minimum_loss": min(losses),
        "optimizer_created": True,
        "early_stopping": False,
        "source_33_34_used": False,
        "promotion_eligible": False,
    }
    with (destination / "history.json").open("x", encoding="utf-8") as handle:
        json.dump(history, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    return {
        **history,
        "checkpoint": _file_identity(checkpoint_path),
        "parameter_count": int(
            sum(parameter.numel() for parameter in model.parameters())
        ),
    }


def load_minimal_dp_checkpoint(
    path: str | Path, *, device: str | torch.device
) -> tuple[MinimalConditionalDiffusionPolicy, dict[str, Any]]:
    checkpoint_path = Path(path).expanduser().resolve(strict=True)
    checkpoint = torch.load(checkpoint_path, map_location=device, weights_only=False)
    if checkpoint.get("schema") != "minimal_dig_diffusion_probe_checkpoint_v1":
        raise ValueError("minimal DP checkpoint schema mismatch")
    config = checkpoint["model_config"]
    model = MinimalConditionalDiffusionPolicy(
        hidden_dim=int(config["hidden_dim"]),
        camera_feature_dim=int(config["camera_feature_dim"]),
    ).to(device)
    model.load_state_dict(checkpoint["ema_state_dict"])
    model.eval()
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    return model, checkpoint


def _validate_arrays(arrays: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    values = {name: np.asarray(value) for name, value in arrays.items()}
    count = values["proprio"].shape[0]
    expected = {
        "images": (count, 4, 32, 32),
        "proprio": (count, 18),
        "actions": (count, 100, 4),
        "source_episode_id": (count,),
        "primitive_episode_id": (count,),
    }
    for name, shape in expected.items():
        if values[name].shape != shape:
            raise ValueError(f"minimal DP training cache {name} shape mismatch")
    for name in ("proprio", "actions"):
        if not np.isfinite(values[name]).all():
            raise ValueError(f"minimal DP training cache {name} is non-finite")
    return values


def _validate_stats(stats: dict[str, np.ndarray]) -> dict[str, torch.Tensor]:
    result = {
        "proprio_mean": torch.as_tensor(stats["proprio_mean"]).float().reshape(1, 18),
        "proprio_std": torch.as_tensor(stats["proprio_std"]).float().reshape(1, 18),
        "action_mean": torch.as_tensor(stats["action_mean"]).float().reshape(1, 1, 4),
        "action_std": torch.as_tensor(stats["action_std"]).float().reshape(1, 1, 4),
    }
    if any(not torch.isfinite(value).all() for value in result.values()):
        raise ValueError("minimal DP norm stats are non-finite")
    if torch.any(result["proprio_std"] <= 0.0) or torch.any(
        result["action_std"] <= 0.0
    ):
        raise ValueError("minimal DP norm scales must be positive")
    return result


def _file_identity(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return {
        "path": str(path),
        "sha256": digest.hexdigest(),
        "size_bytes": path.stat().st_size,
    }


__all__ = [
    "MinimalDPTrainingConfig",
    "load_minimal_dp_checkpoint",
    "train_minimal_dp_seed",
]
