from __future__ import annotations

import inspect
import json
from dataclasses import replace

import numpy as np
import pytest

from testbed.data.act_support_contract import (
    StrictSourceAwareSupportRows,
    SupportRowProvenance,
)
from testbed.data.action_loss_mask import ACTION_LOSS_MASK_SCOPE_LOSS_SAMPLING_STATS
from testbed.data.dig_local_state_support import (
    DIG_LOCAL_STATE_CANDIDATE_SPECS,
    DIG_LOCAL_STATE_SUPPORT_SCHEMA,
    DigLocalStateSupportRows,
    fit_registered_dig_local_state_support_candidates,
)
from testbed.eval.dig_local_state_support_validation import (
    FROZEN_OBVIOUS_OOD_REJECTION_MIN,
    VALIDATION_NORMAL_COVERAGE_MIN,
    DigLocalStateCandidateValidation,
    DigLocalStateSupportValidationError,
    run_dig_local_state_support_validation,
    select_dig_local_state_support_candidate,
)


def _frozen(values: list[list[float]]) -> np.ndarray:
    result = np.asarray(values, dtype=np.float64)
    result.setflags(write=False)
    return result


def _provenance(
    partition: str,
    source_ids: list[int],
) -> tuple[SupportRowProvenance, ...]:
    return tuple(
        SupportRowProvenance(
            partition=partition,  # type: ignore[arg-type]
            primitive_episode_id=100 + source_id,
            source_episode_id=source_id,
            step_index=index,
            step_id=10_000 + index,
            action_loss_mask=1,
        )
        for index, source_id in enumerate(source_ids)
    )


def _rows() -> DigLocalStateSupportRows:
    """Create four source episodes so leave-one-source k=32 is feasible."""

    train_source_ids: list[int] = []
    train_features: list[list[float]] = []
    for step in range(40):
        state = [step * 0.1 + feature * 0.01 for feature in range(18)]
        for source_id in (1, 2, 3, 4):
            train_source_ids.append(source_id)
            train_features.append(state)
    validation_source_ids = [5] * 16
    validation_features = [
        [step * 0.1 + feature * 0.01 for feature in range(18)]
        for step in range(16)
    ]
    train_feature_matrix = _frozen(train_features)
    validation_feature_matrix = _frozen(validation_features)
    train_actions = _frozen([[0.0, 0.0, 0.0, 0.0]] * len(train_features))
    validation_actions = _frozen([[0.0, 0.0, 0.0, 0.0]] * len(validation_features))
    feature_order = tuple(
        [f"qpos[{index}]" for index in range(4)]
        + [f"qvel[{index}]" for index in range(4)]
        + [f"dig_cut_tokens[{index}]" for index in range(10)]
    )
    train_provenance = _provenance("train", train_source_ids)
    validation_provenance = _provenance("validation", validation_source_ids)
    numeric_rows = StrictSourceAwareSupportRows(
        schema="strict_source_aware_act_support_rows_v1",
        skill_name="dig",
        model_token_key="dig_cut_tokens",
        feature_order=feature_order,
        train_features=train_feature_matrix,
        validation_features=validation_feature_matrix,
        train_provenance=train_provenance,
        validation_provenance=validation_provenance,
        training_config_path="/immutable/dig.yaml",
        primitive_dataset_dir="/immutable/dig",
        split_path="/immutable/dig_split.yaml",
        train_source_episode_ids=(1, 2, 3, 4),
        validation_source_episode_ids=(5,),
        total_step_count=len(train_features) + len(validation_features),
        kept_step_count=len(train_features) + len(validation_features),
        masked_step_count=0,
    )
    return DigLocalStateSupportRows(
        schema=DIG_LOCAL_STATE_SUPPORT_SCHEMA,
        feature_order=feature_order,
        train_features=train_feature_matrix,
        validation_features=validation_feature_matrix,
        train_actions=train_actions,
        validation_actions=validation_actions,
        train_provenance=train_provenance,
        validation_provenance=validation_provenance,
        training_config_path="/immutable/dig.yaml",
        primitive_dataset_dir="/immutable/dig",
        split_path="/immutable/dig_split.yaml",
        train_source_episode_ids=(1, 2, 3, 4),
        validation_source_episode_ids=(5,),
        total_step_count=len(train_features) + len(validation_features),
        kept_step_count=len(train_features) + len(validation_features),
        masked_step_count=0,
        action_loss_mask_scope=ACTION_LOSS_MASK_SCOPE_LOSS_SAMPLING_STATS,
        _numeric_rows=numeric_rows,
    )


def _evaluation(
    *,
    candidate_id: str,
    fixed_order: int,
    coverage: float,
    rejection: float,
) -> DigLocalStateCandidateValidation:
    return DigLocalStateCandidateValidation(
        candidate_id=candidate_id,
        fixed_order=fixed_order,
        validation_normal_coverage=coverage,
        validation_distance_coverage=1.0,
        validation_neighbor_count_coverage=1.0,
        validation_source_diversity_coverage=1.0,
        validation_action_coherence_coverage=1.0,
        validation_action_axis_coherence_coverage=1.0,
        frozen_obvious_ood_rejection=rejection,
        validation_frozen_predicate_verified=True,
        frozen_obvious_ood_predicate_verified=True,
        validation_normal_coverage_passed=coverage >= VALIDATION_NORMAL_COVERAGE_MIN,
        frozen_obvious_ood_rejection_passed=(
            rejection >= FROZEN_OBVIOUS_OOD_REJECTION_MIN
        ),
    )


def test_audit_uses_only_source_disjoint_train_validation_and_is_json_ready() -> None:
    result = run_dig_local_state_support_validation(rows=_rows())

    assert result["diagnostic_only"] is True
    assert result["promotion_eligible"] is False
    assert result["runtime_support_change"] is False
    assert result["target_rollout_used_for_selection"] is False
    assert result["selection_input_scope"] == "strict_train_and_held_validation_only"
    assert result["source_separation"] == {
        "fit_partition": "strict_train",
        "normal_validation_partition": "held_validation",
        "train_source_episode_ids": [1, 2, 3, 4],
        "validation_source_episode_ids": [5],
        "source_episode_id_overlap": [],
        "source_disjoint": True,
        "train_action_loss_mask": "all_rows_equal_1",
        "validation_action_loss_mask": "all_rows_equal_1",
    }
    assert result["selected_candidate_id"] == DIG_LOCAL_STATE_CANDIDATE_SPECS[0].candidate_id
    assert len(result["candidates"]) == len(DIG_LOCAL_STATE_CANDIDATE_SPECS)
    assert json.dumps(result, allow_nan=False)
    repeated = run_dig_local_state_support_validation(rows=_rows())
    assert [item["validation_assessment"]["assessment_sha256"] for item in result["candidates"]] == [
        item["validation_assessment"]["assessment_sha256"]
        for item in repeated["candidates"]
    ]


def test_validation_support_uses_all_frozen_local_predicate_parts() -> None:
    result = run_dig_local_state_support_validation(rows=_rows())

    for record in result["candidates"]:
        predicate = record["support_predicate"]
        assessment = record["validation_assessment"]
        assert record["validation_frozen_predicate_verified"] is True
        assert assessment["support_predicate_verified"] is True
        assert assessment["neighbor_count_coverage"] == 1.0
        assert assessment["source_diversity_coverage"] == 1.0
        assert assessment["action_coherence_coverage"] == 1.0
        assert assessment["action_axis_coherence_coverage"] == 1.0
        assert assessment["per_row_neighbors_serialized"] is False
        assert "rows" not in assessment
        assert "neighbors" not in assessment
        assert len(assessment["assessment_sha256"]) == 64
        assert predicate["k_neighbors_present"] in (8, 16, 32)
        assert len(predicate["neighbor_expert_action_axis_coherence_at_or_below"]) == 4


def test_audit_builds_one_max_k_cohort_per_validation_population(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import testbed.eval.dig_local_state_support_validation as evaluator

    observed_calls: list[tuple[int, int, tuple[str, ...]]] = []
    original = evaluator.build_dig_local_state_neighbor_cohort

    def _recording_builder(
        candidates: object,
        features: np.ndarray,
        **kwargs: object,
    ) -> object:
        selected = tuple(candidates.values())  # type: ignore[union-attr]
        observed_calls.append(
            (
                int(features.shape[0]),
                max(candidate.k_neighbors for candidate in selected),
                tuple(candidate.candidate_id for candidate in selected),
            )
        )
        return original(candidates, features, **kwargs)

    monkeypatch.setattr(
        evaluator,
        "build_dig_local_state_neighbor_cohort",
        _recording_builder,
    )
    result = evaluator.run_dig_local_state_support_validation(rows=_rows())

    expected_ids = tuple(spec.candidate_id for spec in DIG_LOCAL_STATE_CANDIDATE_SPECS)
    assert observed_calls == [(16, 32, expected_ids), (16, 32, expected_ids)]
    assert result["validation_neighbor_cohort"]["max_k_neighbors"] == 32
    assert result["frozen_obvious_ood_neighbor_cohort"]["max_k_neighbors"] == 32
    assert (
        result["validation_neighbor_cohort"]["reference_index_sha256"]
        == result["frozen_obvious_ood_neighbor_cohort"]["reference_index_sha256"]
    )


def test_selector_uses_ood_then_normal_coverage_then_fixed_order() -> None:
    evaluations = [
        _evaluation(
            candidate_id=spec.candidate_id,
            fixed_order=index,
            coverage=0.995,
            rejection=0.995,
        )
        for index, spec in enumerate(DIG_LOCAL_STATE_CANDIDATE_SPECS)
    ]
    evaluations[1] = _evaluation(
        candidate_id=DIG_LOCAL_STATE_CANDIDATE_SPECS[1].candidate_id,
        fixed_order=1,
        coverage=0.999,
        rejection=1.0,
    )
    assert (
        select_dig_local_state_support_candidate(evaluations).candidate_id
        == DIG_LOCAL_STATE_CANDIDATE_SPECS[1].candidate_id
    )

    ties = [
        _evaluation(
            candidate_id=spec.candidate_id,
            fixed_order=index,
            coverage=1.0,
            rejection=1.0,
        )
        for index, spec in enumerate(DIG_LOCAL_STATE_CANDIDATE_SPECS)
    ]
    assert (
        select_dig_local_state_support_candidate(ties).candidate_id
        == DIG_LOCAL_STATE_CANDIDATE_SPECS[0].candidate_id
    )


def test_selector_rejects_candidates_that_fail_the_pre_registered_gate() -> None:
    rejected = [
        _evaluation(
            candidate_id=spec.candidate_id,
            fixed_order=index,
            coverage=0.98,
            rejection=1.0,
        )
        for index, spec in enumerate(DIG_LOCAL_STATE_CANDIDATE_SPECS)
    ]
    assert select_dig_local_state_support_candidate(rejected) is None


def test_audit_rejects_candidate_not_fitted_from_strict_train(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = _rows()
    candidates = fit_registered_dig_local_state_support_candidates(rows)
    first = DIG_LOCAL_STATE_CANDIDATE_SPECS[0].candidate_id
    candidates[first] = replace(candidates[first], fit_partition="validation")
    import testbed.eval.dig_local_state_support_validation as evaluator

    monkeypatch.setattr(
        evaluator,
        "fit_registered_dig_local_state_support_candidates",
        lambda _: candidates,
    )
    with pytest.raises(DigLocalStateSupportValidationError, match="strict_train"):
        evaluator.run_dig_local_state_support_validation(rows=rows)


def test_selection_function_has_no_target_or_runtime_parameter() -> None:
    assert tuple(inspect.signature(run_dig_local_state_support_validation).parameters) == (
        "rows",
    )
