from __future__ import annotations

import numpy as np

from testbed.eval.dig_diffusion_probe_data import (
    SourceEpisodeBalancedSampler,
    build_evaluation_token_conditions,
)


def test_source_episode_sampler_is_deterministic_and_excludes_33_34() -> None:
    source_ids = np.asarray([3, 3, 6, 6, 33, 34], dtype=np.int32)
    episode_ids = np.asarray([10, 11, 20, 21, 30, 40], dtype=np.int32)
    sampler = SourceEpisodeBalancedSampler(source_ids, episode_ids)

    first = sampler.sample_indices(batch_size=16, seed=7)
    second = sampler.sample_indices(batch_size=16, seed=7)

    np.testing.assert_array_equal(first, second)
    assert set(source_ids[first]) <= {3, 6}
    assert 33 not in source_ids[first]
    assert 34 not in source_ids[first]


def test_eval_conditions_bind_base_alternate_zero_and_deterministic_shuffle() -> None:
    variants = []
    for index in range(4):
        base = np.full(10, index, dtype=np.float32)
        alternate = base.copy()
        alternate[0] += 0.1
        variants.append(
            {
                "variant_id": f"v{index}",
                "base_token": base.tolist(),
                "variant_token": alternate.tolist(),
            }
        )

    result = build_evaluation_token_conditions(variants, shuffle_seed=20260824)

    assert result["base_correct"].shape == (4, 10)
    assert result["alternate_correct"].shape == (4, 10)
    assert np.count_nonzero(result["zero"]) == 0
    assert result["shuffle_indices"].shape == (4,)
    assert np.all(result["shuffle_indices"] != np.arange(4))
    assert all(
        not np.array_equal(
            result["shuffled"][index], result["alternate_correct"][index]
        )
        for index in range(4)
    )
    np.testing.assert_array_equal(
        result["shuffled"], result["alternate_correct"][result["shuffle_indices"]]
    )
