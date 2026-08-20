"""Contract tests for source-disjoint Return dispatch selection."""

from __future__ import annotations

import inspect
import json
from collections.abc import Mapping
from types import SimpleNamespace

import numpy as np
import pytest

from testbed.data.act_support_contract import SupportRowProvenance
from testbed.data.return_temporal_dispatch_reference import (
    ReturnTemporalActionReference,
)
from testbed.data.return_temporal_dispatch_sampling import (
    RETURN_TEMPORAL_DISPATCH_SAMPLE_SCHEMA,
    ReturnTemporalDispatchSourceSample,
    ReturnTemporalDispatchValidationSample,
)
from testbed.data.return_temporal_dispatch_validation import (
    RETURN_TEMPORAL_DISPATCH_VALIDATION_SCHEMA,
    ReturnTemporalDispatchFrame,
    ReturnTemporalDispatchSegment,
    ReturnTemporalDispatchStorageContract,
    ReturnTemporalDispatchValidationPopulation,
    ReturnValidationCounterfactualPair,
)
from testbed.eval.return_temporal_dispatch_validation_eval import (
    ReturnTemporalDispatchValidationEvaluationError,
    build_return_temporal_dispatch_metric_contract,
    evaluate_return_temporal_dispatch_validation,
)

_ACTION_DIM = 4
_FRAME_COUNT = 50


def _action_reference() -> ReturnTemporalActionReference:
    vector = np.ones(_ACTION_DIM, dtype=np.float32)
    return ReturnTemporalActionReference(
        fit_partition="strict_train",
        action_row_count=100,
        source_episode_ids=(10, 11),
        action_mean=np.zeros(_ACTION_DIM, dtype=np.float32),
        action_scale=vector,
        action_p01=-vector,
        action_p99=vector,
        action_min=-2.0 * vector,
        action_max=2.0 * vector,
        action_delta_row_count=99,
        action_delta_abs_p50=np.full(_ACTION_DIM, 0.1, dtype=np.float32),
        action_delta_abs_p95=np.full(_ACTION_DIM, 0.25, dtype=np.float32),
        action_delta_abs_p99=np.full(_ACTION_DIM, 0.5, dtype=np.float32),
        action_delta_abs_max=np.full(_ACTION_DIM, 0.75, dtype=np.float32),
        action_delta_l2_p50=0.1,
        action_delta_l2_p95=0.25,
        action_delta_l2_p99=0.5,
        action_delta_l2_max=0.75,
        jitter_row_count=98,
        jitter_abs_p50=np.full(_ACTION_DIM, 0.1, dtype=np.float32),
        jitter_abs_p95=np.full(_ACTION_DIM, 0.2, dtype=np.float32),
        jitter_abs_p99=np.full(_ACTION_DIM, 0.3, dtype=np.float32),
        jitter_abs_max=np.full(_ACTION_DIM, 0.4, dtype=np.float32),
        jitter_l2_p50=0.1,
        jitter_l2_p95=0.2,
        jitter_l2_p99=0.3,
        jitter_l2_max=0.4,
    )


def _frame(
    *,
    source_episode_id: int,
    primitive_episode_id: int,
    index: int,
    token: np.ndarray,
) -> ReturnTemporalDispatchFrame:
    values = np.full(4, float(index), dtype=np.float32)
    return ReturnTemporalDispatchFrame(
        provenance=SupportRowProvenance(
            partition="validation",
            primitive_episode_id=primitive_episode_id,
            source_episode_id=source_episode_id,
            step_index=index,
            step_id=10000 + index,
            action_loss_mask=1,
        ),
        hdf5_path="/not-read-by-injected-observation-reader.hdf5",
        action_index=index,
        observation_index=index,
        action_step_id=10000 + index,
        observation_step_id=10000 + index,
        qpos=values,
        qvel=values + 1.0,
        token=token.copy(),
        expert_action=np.zeros(4, dtype=np.float32),
    )


def _segment(
    *,
    source_episode_id: int,
    primitive_episode_id: int,
    token_value: float,
) -> ReturnTemporalDispatchSegment:
    token = np.full(18, token_value, dtype=np.float32)
    return ReturnTemporalDispatchSegment(
        primitive_episode_id=primitive_episode_id,
        source_episode_id=source_episode_id,
        token=token,
        token_sha256=f"token-{primitive_episode_id:04d}-{token_value:.1f}",
        frames=tuple(
            _frame(
                source_episode_id=source_episode_id,
                primitive_episode_id=primitive_episode_id,
                index=index,
                token=token,
            )
            for index in range(_FRAME_COUNT)
        ),
    )


def _population_and_sample() -> tuple[
    ReturnTemporalDispatchValidationPopulation,
    ReturnTemporalDispatchValidationSample,
]:
    segments = tuple(
        _segment(
            source_episode_id=90 if index < 8 else 91,
            primitive_episode_id=index,
            token_value=float(index % 2),
        )
        for index in range(16)
    )
    storage = ReturnTemporalDispatchStorageContract(
        qpos_dtype="float32",
        qvel_dtype="float32",
        token_dtype="float32",
        action_dtype="float32",
        step_id_dtype="int64",
        qpos_order=("q0", "q1", "q2", "q3"),
        qvel_order=("v0", "v1", "v2", "v3"),
        action_order=("a0", "a1", "a2", "a3"),
        camera_storage="raw_rgb",
        observation_action_alignment="same_row",
    )
    train_frame = ReturnTemporalDispatchFrame(
        provenance=SupportRowProvenance(
            partition="train",
            primitive_episode_id=100,
            source_episode_id=10,
            step_index=0,
            step_id=0,
            action_loss_mask=1,
        ),
        hdf5_path="/strict-train.hdf5",
        action_index=0,
        observation_index=0,
        action_step_id=0,
        observation_step_id=0,
        qpos=np.zeros(4, dtype=np.float32),
        qvel=np.zeros(4, dtype=np.float32),
        token=np.zeros(18, dtype=np.float32),
        expert_action=np.zeros(4, dtype=np.float32),
    )
    population = ReturnTemporalDispatchValidationPopulation(
        schema=RETURN_TEMPORAL_DISPATCH_VALIDATION_SCHEMA,
        feature_order=tuple(f"feature-{index}" for index in range(26)),
        model_token_key="return_start_envelope_tokens_v1",
        camera_names=("cam_a",),
        storage_contract=storage,
        training_config_path="/strict-return.yaml",
        primitive_dataset_dir="/strict-return",
        split_path="/strict-return-split.yaml",
        train_source_episode_ids=(10, 11),
        validation_source_episode_ids=(90, 91),
        train_frames=(train_frame,),
        validation_frames=tuple(
            frame for segment in segments for frame in segment.frames
        ),
        validation_segments=segments,
        action_reference=_action_reference(),
    )
    pairs = tuple(
        ReturnValidationCounterfactualPair(
            baseline_segment=segment,
            alternate_token=segments[(index + 1) % len(segments)].token.copy(),
            alternate_token_sha256=segments[(index + 1) % len(segments)].token_sha256,
            alternate_token_source_episode_id=segments[
                (index + 1) % len(segments)
            ].source_episode_id,
            alternate_token_primitive_episode_id=segments[
                (index + 1) % len(segments)
            ].primitive_episode_id,
            alternate_token_segment_id=segments[(index + 1) % len(segments)].segment_id,
        )
        for index, segment in enumerate(segments)
    )
    sample = ReturnTemporalDispatchValidationSample(
        schema=RETURN_TEMPORAL_DISPATCH_SAMPLE_SCHEMA,
        max_segments_per_validation_source=8,
        all_held_validation_segment_count=16,
        source_samples=(
            ReturnTemporalDispatchSourceSample(
                source_episode_id=90,
                available_segment_count=8,
                sampled_segment_ids=tuple(item.segment_id for item in segments[:8]),
            ),
            ReturnTemporalDispatchSourceSample(
                source_episode_id=91,
                available_segment_count=8,
                sampled_segment_ids=tuple(item.segment_id for item in segments[8:]),
            ),
        ),
        sampled_segments=segments,
        counterfactual_pairs=pairs,
    )
    return population, sample


class _Policy:
    def __init__(
        self, *, label: str, replica_bias: float = 0.0, wrong_predict: bool = False
    ) -> None:
        self.label = label
        self.replica_bias = replica_bias
        self.wrong_predict = wrong_predict
        self.reset_calls = 0
        self._chunks: list[np.ndarray] = []

    def reset(self) -> None:
        self.reset_calls += 1
        self._chunks = []

    def predict_action_chunk(
        self, observation: Mapping[str, np.ndarray]
    ) -> SimpleNamespace:
        token = np.asarray(
            observation["return_start_envelope_tokens_v1"], dtype=np.float32
        )
        query = np.arange(100, dtype=np.float32)
        effect = 0.2 * float(token[0]) * np.exp(-0.15 * query)
        chunk = np.zeros((100, _ACTION_DIM), dtype=np.float32)
        chunk[:, 0] = effect + self.replica_bias
        return SimpleNamespace(actions=chunk)

    def predict(self, observation: Mapping[str, np.ndarray]) -> np.ndarray:
        chunk = np.asarray(
            self.predict_action_chunk(observation).actions, dtype=np.float32
        )
        self._chunks.append(chunk)
        current = len(self._chunks) - 1
        start = max(0, current - 99)
        contributors = self._chunks[start : current + 1]
        query_indices = np.arange(current - start, -1, -1, dtype=np.int64)
        weights = np.exp(-0.01 * np.arange(len(contributors), dtype=np.float64))
        weights /= weights.sum()
        action = sum(
            weight * chunk_value[query_index]
            for weight, chunk_value, query_index in zip(
                weights, contributors, query_indices, strict=True
            )
        ).astype(np.float32)
        if self.wrong_predict:
            action[0] += 0.01
        return action

    @property
    def description(self) -> dict[str, object]:
        return {
            "temporal_aggregation": {
                "enabled": True,
                "num_queries": 100,
                "window": 100,
                "weight_order": "legacy_oldest_first",
                "decay": 0.01,
            },
            "action_dim": _ACTION_DIM,
            "action_mean": [0.0] * _ACTION_DIM,
            "action_std": [1.0] * _ACTION_DIM,
        }


def _reader(frame: ReturnTemporalDispatchFrame) -> dict[str, np.ndarray]:
    return {
        "qpos": frame.qpos.copy(),
        "qvel": frame.qvel.copy(),
        "image_cam_a": np.zeros((3, 2, 2), dtype=np.uint8),
    }


def test_evaluator_freezes_a_safe_source_disjoint_candidate_with_compact_metrics() -> (
    None
):
    population, sample = _population_and_sample()
    created: list[_Policy] = []

    def factory(label: str) -> _Policy:
        policy = _Policy(label=label)
        created.append(policy)
        return policy

    result = evaluate_return_temporal_dispatch_validation(
        population=population,
        sample=sample,
        policy_factory=factory,
        observation_reader=_reader,
        policy_describer=lambda policy: policy.description,
    )

    metric = build_return_temporal_dispatch_metric_contract(population)
    np.testing.assert_allclose(metric.response_threshold, np.full(4, 0.05))
    np.testing.assert_allclose(metric.jitter_mean_abs_limit, np.full(4, 0.5))
    assert result["target_stage_a_failures_used"] is False
    assert result["sample"]["sampled_segment_count"] == 16
    assert result["selection"]["selected_strategy_id"] == (
        "newest_first_max_age_20_decay_0p01"
    )
    assert result["selection"]["runtime_default_changed"] is False
    assert (
        result["strategies"]["legacy_100_oldest_first_decay_0p01"]["selection_eligible"]
        is False
    )
    assert (
        result["strategies"]["latest_current_chunk_diagnostic"]["selection_eligible"]
        is False
    )
    assert (
        result["strategies"]["newest_first_max_age_20_decay_0p01"]["aggregate"][
            "response"
        ]["passes_fixed_gate"]
        is True
    )
    assert all(policy.reset_calls == 1 for policy in created)
    payload = json.dumps(result, sort_keys=True)
    assert '"chunks"' not in payload
    assert '"actions"' not in payload


def test_evaluator_rejects_nonfixed_population_before_policy_replay() -> None:
    population, sample = _population_and_sample()
    invalid_sample = ReturnTemporalDispatchValidationSample(
        schema=sample.schema,
        max_segments_per_validation_source=sample.max_segments_per_validation_source,
        all_held_validation_segment_count=sample.all_held_validation_segment_count,
        source_samples=sample.source_samples,
        sampled_segments=sample.sampled_segments[:-1],
        counterfactual_pairs=sample.counterfactual_pairs[:-1],
    )

    with pytest.raises(
        ReturnTemporalDispatchValidationEvaluationError,
        match="exactly 16",
    ):
        evaluate_return_temporal_dispatch_validation(
            population=population,
            sample=invalid_sample,
            policy_factory=lambda _label: _Policy(label="unused"),
            observation_reader=_reader,
            policy_describer=lambda policy: policy.description,
        )

    signature = inspect.signature(evaluate_return_temporal_dispatch_validation)
    assert "target" not in " ".join(signature.parameters)
    assert "stage_a" not in " ".join(signature.parameters)


@pytest.mark.parametrize("failure", ["wrong_predict", "replica_drift"])
def test_evaluator_fails_closed_on_cache_reconstruction_or_replica_instability(
    failure: str,
) -> None:
    population, sample = _population_and_sample()

    def factory(label: str) -> _Policy:
        return _Policy(
            label=label,
            wrong_predict=failure == "wrong_predict",
            replica_bias=0.001
            if failure == "replica_drift" and "replica" in label
            else 0.0,
        )

    expected = "reconstruction" if failure == "wrong_predict" else "replica"
    with pytest.raises(ReturnTemporalDispatchValidationEvaluationError, match=expected):
        evaluate_return_temporal_dispatch_validation(
            population=population,
            sample=sample,
            policy_factory=factory,
            observation_reader=_reader,
            policy_describer=lambda policy: policy.description,
        )


def test_evaluator_rejects_a_reused_live_policy_instance() -> None:
    population, sample = _population_and_sample()
    singleton = _Policy(label="singleton")

    with pytest.raises(
        ReturnTemporalDispatchValidationEvaluationError,
        match="reused one live instance",
    ):
        evaluate_return_temporal_dispatch_validation(
            population=population,
            sample=sample,
            policy_factory=lambda _label: singleton,
            observation_reader=_reader,
            policy_describer=lambda policy: policy.description,
        )
