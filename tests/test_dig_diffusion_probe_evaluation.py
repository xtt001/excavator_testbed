from __future__ import annotations

import io

import numpy as np
import torch

from testbed.eval.dig_diffusion_probe_evaluation import evaluate_minimal_dp_model
from testbed.eval.dig_diffusion_probe_model import MinimalConditionalDiffusionPolicy


def test_evaluation_resamples_each_frame_with_paired_condition_noise() -> None:
    torch.manual_seed(0)
    model = MinimalConditionalDiffusionPolicy(hidden_dim=32)
    arrays = {
        "images": np.zeros((1, 2, 4, 32, 32), dtype=np.uint8),
        "qpos": np.zeros((1, 2, 4), dtype=np.float32),
        "qvel": np.zeros((1, 2, 4), dtype=np.float32),
        "source_episode_id": np.asarray([3], dtype=np.int32),
        "primitive_episode_id": np.asarray([10], dtype=np.int32),
    }
    tokens = {
        "base_correct": np.zeros((1, 10), dtype=np.float32),
        "alternate_correct": np.ones((1, 10), dtype=np.float32),
        "zero": np.zeros((1, 10), dtype=np.float32),
        "shuffled": np.full((1, 10), 0.5, dtype=np.float32),
    }
    stats = {
        "proprio_mean": torch.zeros(1, 18),
        "proprio_std": torch.ones(1, 18),
        "action_mean": torch.zeros(1, 1, 4),
        "action_std": torch.ones(1, 1, 4),
    }
    trace = io.StringIO()

    result = evaluate_minimal_dp_model(
        model=model,
        schedule_betas=torch.linspace(1.0e-4, 0.02, 10),
        norm_stats=stats,
        evaluation_arrays=arrays,
        token_conditions=tokens,
        variant_records=[{"variant_id": "v0"}],
        training_seed=0,
        inference_noise_seeds=(100, 101),
        inference_steps=3,
        action_p01=np.full(4, -10.0),
        action_p99=np.full(4, 10.0),
        device="cpu",
        batch_size=2,
        trace_handle=trace,
    )

    assert result["dispatched_actions"]["base_correct"].shape == (2, 1, 2, 4)
    assert result["dispatched_actions"]["alternate_correct"].shape == (2, 1, 2, 4)
    assert result["temporal_aggregation_used"] is False
    assert result["resampled_chunk_count"] == 2 * 1 * 2 * 4
    rows = [line for line in trace.getvalue().splitlines() if line]
    assert len(rows) == 16
