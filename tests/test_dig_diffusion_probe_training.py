from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from testbed.eval.dig_diffusion_probe_training import (
    MinimalDPTrainingConfig,
    load_minimal_dp_checkpoint,
    train_minimal_dp_seed,
)


def _arrays() -> dict[str, np.ndarray]:
    rng = np.random.default_rng(3)
    count = 12
    return {
        "images": rng.integers(0, 256, size=(count, 4, 32, 32), dtype=np.uint8),
        "proprio": rng.normal(size=(count, 18)).astype(np.float32),
        "actions": rng.normal(size=(count, 100, 4)).astype(np.float32),
        "source_episode_id": np.repeat([3, 6, 7], 4).astype(np.int32),
        "primitive_episode_id": np.arange(count, dtype=np.int32),
    }


def _stats() -> dict[str, np.ndarray]:
    return {
        "proprio_mean": np.zeros(18, dtype=np.float32),
        "proprio_std": np.ones(18, dtype=np.float32),
        "action_mean": np.zeros(4, dtype=np.float32),
        "action_std": np.ones(4, dtype=np.float32),
    }


def test_training_seed_writes_frozen_reloadable_checkpoint(tmp_path: Path) -> None:
    destination = tmp_path / "seed_0"
    result = train_minimal_dp_seed(
        arrays=_arrays(),
        norm_stats=_stats(),
        seed=0,
        output_dir=destination,
        config=MinimalDPTrainingConfig(
            updates=2,
            batch_size=4,
            hidden_dim=32,
            train_timesteps=10,
        ),
        device="cpu",
        lineage={"cache_sha256": "a" * 64},
    )

    assert result["seed"] == 0
    assert result["updates_completed"] == 2
    assert result["optimizer_created"] is True
    assert result["early_stopping"] is False
    assert result["source_33_34_used"] is False
    model, checkpoint = load_minimal_dp_checkpoint(
        destination / "checkpoint.pt", device="cpu"
    )
    assert checkpoint["seed"] == 0
    assert model.training is False
    assert all(parameter.requires_grad is False for parameter in model.parameters())
    with pytest.raises(FileExistsError):
        train_minimal_dp_seed(
            arrays=_arrays(),
            norm_stats=_stats(),
            seed=0,
            output_dir=destination,
            config=MinimalDPTrainingConfig(updates=1, batch_size=4, hidden_dim=32),
            device="cpu",
            lineage={},
        )
