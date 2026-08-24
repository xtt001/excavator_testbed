from __future__ import annotations

import numpy as np
import torch

from testbed.eval.dig_diffusion_probe_model import (
    DiffusionSchedule,
    LatestObservationDiffusionDispatcher,
    MinimalConditionalDiffusionPolicy,
    sample_action_chunks,
)


def test_minimal_dp_contract_is_four_camera_18d_and_100x4() -> None:
    model = MinimalConditionalDiffusionPolicy(
        camera_count=4,
        low_dim=18,
        action_horizon=100,
        action_dim=4,
        hidden_dim=64,
    )
    images = torch.zeros(2, 4, 1, 32, 32)
    low_dim = torch.zeros(2, 18)
    noisy = torch.zeros(2, 100, 4)
    timestep = torch.tensor([1, 2])

    predicted = model(noisy, timestep, low_dim, images)

    assert predicted.shape == (2, 100, 4)
    assert model.contract["camera_count"] == 4
    assert model.contract["low_dim"] == 18
    assert model.contract["action_horizon"] == 100
    assert model.contract["temporal_aggregation"] is False


def test_ddim_sampling_is_reproducible_for_fixed_initial_noise() -> None:
    torch.manual_seed(0)
    model = MinimalConditionalDiffusionPolicy(hidden_dim=32)
    model.eval()
    schedule = DiffusionSchedule.create(train_timesteps=20)
    images = torch.zeros(1, 4, 1, 32, 32)
    low_dim = torch.zeros(1, 18)
    noise = torch.randn(1, 100, 4, generator=torch.Generator().manual_seed(7))

    first = sample_action_chunks(
        model=model,
        schedule=schedule,
        images=images,
        low_dim=low_dim,
        initial_noise=noise,
        inference_steps=5,
    )
    second = sample_action_chunks(
        model=model,
        schedule=schedule,
        images=images,
        low_dim=low_dim,
        initial_noise=noise.clone(),
        inference_steps=5,
    )

    torch.testing.assert_close(first, second, rtol=0.0, atol=0.0)
    assert first.shape == (1, 100, 4)


class _CountingSampler:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, observation: dict, *, noise_seed: int) -> np.ndarray:
        self.calls += 1
        chunk = np.zeros((100, 4), dtype=np.float32)
        chunk[0] = np.asarray(
            [self.calls, observation["dig_cut_tokens"][0], noise_seed, -noise_seed],
            dtype=np.float32,
        )
        return chunk


def test_latest_observation_dispatcher_resamples_every_frame_and_uses_first_action() -> (
    None
):
    sampler = _CountingSampler()
    dispatcher = LatestObservationDiffusionDispatcher(
        chunk_sampler=sampler,
        inference_noise_seed=101,
    )
    token = np.zeros(10, dtype=np.float32)
    token[0] = 0.25

    first = dispatcher.dispatch({"frame": 0}, token)
    second = dispatcher.dispatch({"frame": 1}, token)

    assert sampler.calls == 2
    np.testing.assert_array_equal(first.dispatched_action, first.raw_action_chunk[0])
    np.testing.assert_array_equal(second.dispatched_action, second.raw_action_chunk[0])
    assert first.contributing_chunk_ages == (0,)
    assert second.contributing_chunk_ages == (0,)
    assert first.temporal_aggregation_used is False
    assert second.raw_action_chunk[0, 0] == 2.0
