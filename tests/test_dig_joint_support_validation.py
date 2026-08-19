from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from testbed.data.act_support_contract import (
    StrictSourceAwareSupportRows,
    SupportRowProvenance,
)
from testbed.data.dig_joint_support_validation import (
    DIG_JOINT_MAHALANOBIS_CANDIDATE_IDS,
    DIG_JOINT_MAHALANOBIS_QUANTILES,
    DigJointSupportValidationError,
    build_dig_validation_v1_edge_cohort,
    build_frozen_dig_validation_obvious_ood,
    dig_joint_support_source_provenance,
    fit_dig_joint_mahalanobis_family,
    validate_dig_joint_support_validation_rows,
)
from testbed.eval.dig_joint_support_validation_audit import (
    FROZEN_OBVIOUS_OOD_REJECTION_MIN,
    VALIDATION_NORMAL_COVERAGE_MIN,
    DigJointCandidateValidation,
    run_dig_joint_support_validation_audit,
    select_dig_joint_support_candidate,
)
from testbed.eval.dig_joint_support_validation_audit_runner import (
    run_dig_joint_support_validation_audit_from_file,
)


def _frozen(values: list[list[float]]) -> np.ndarray:
    result = np.asarray(values, dtype=np.float64)
    result.setflags(write=False)
    return result


def _provenance(
    partition: str,
    source_episode_ids: list[int],
) -> tuple[SupportRowProvenance, ...]:
    return tuple(
        SupportRowProvenance(
            partition=partition,  # type: ignore[arg-type]
            primitive_episode_id=10 + index,
            source_episode_id=source_id,
            step_index=index,
            step_id=100 + index,
            action_loss_mask=1,
        )
        for index, source_id in enumerate(source_episode_ids)
    )


def _rows() -> StrictSourceAwareSupportRows:
    train = _frozen(
        [
            [-1.0, -1.0],
            [-0.8, -0.8],
            [-0.6, -0.6],
            [0.6, 0.6],
            [0.8, 0.8],
            [1.0, 1.0],
        ]
    )
    validation = _frozen(
        [[-0.7, -0.7], [-0.3, -0.3], [0.3, 0.3], [0.7, 0.7]]
    )
    return StrictSourceAwareSupportRows(
        schema="strict_source_aware_act_support_rows_v1",
        skill_name="dig",
        model_token_key="dig_cut_tokens",
        feature_order=("qpos[0]", "dig_cut_tokens[0]"),
        train_features=train,
        validation_features=validation,
        train_provenance=_provenance("train", [11, 11, 11, 12, 12, 12]),
        validation_provenance=_provenance("validation", [21, 21, 21, 21]),
        training_config_path="/immutable/dig_train.yaml",
        primitive_dataset_dir="/immutable/dig",
        split_path="/immutable/dig_split.yaml",
        train_source_episode_ids=(11, 12),
        validation_source_episode_ids=(21,),
        total_step_count=10,
        kept_step_count=10,
        masked_step_count=0,
    )


def _evaluation(
    *,
    candidate_id: str,
    fixed_order: int,
    coverage: float,
    rejection: float,
    edge_coverage: float | None = 1.0,
) -> DigJointCandidateValidation:
    return DigJointCandidateValidation(
        candidate_id=candidate_id,
        fixed_order=fixed_order,
        train_score_quantile=DIG_JOINT_MAHALANOBIS_QUANTILES[fixed_order],
        validation_normal_coverage=coverage,
        validation_v1_edge_coverage=edge_coverage,
        validation_v1_edge_nonempty=edge_coverage is not None,
        frozen_obvious_ood_rejection=rejection,
        validation_normal_coverage_passed=coverage >= VALIDATION_NORMAL_COVERAGE_MIN,
        validation_v1_edge_coverage_passed=(
            edge_coverage is not None and edge_coverage >= VALIDATION_NORMAL_COVERAGE_MIN
        ),
        frozen_obvious_ood_rejection_passed=(
            rejection >= FROZEN_OBVIOUS_OOD_REJECTION_MIN
        ),
    )


def test_joint_family_is_pre_registered_and_fitted_from_strict_train_only() -> None:
    rows = _rows()
    first = fit_dig_joint_mahalanobis_family(rows)
    changed_validation = _frozen([[999.0, -999.0]] * 4)
    second = fit_dig_joint_mahalanobis_family(
        replace(rows, validation_features=changed_validation)
    )

    assert tuple(first) == DIG_JOINT_MAHALANOBIS_CANDIDATE_IDS
    assert [candidate.train_score_quantile for candidate in first.values()] == list(
        DIG_JOINT_MAHALANOBIS_QUANTILES
    )
    assert all(candidate.fit_partition == "strict_train" for candidate in first.values())
    assert all(candidate.fit_row_count == 6 for candidate in first.values())
    assert all(candidate.regularization > 0.0 for candidate in first.values())
    assert all(not candidate.mean.flags.writeable for candidate in first.values())
    for candidate_id in DIG_JOINT_MAHALANOBIS_CANDIDATE_IDS:
        assert first[candidate_id].as_dict() == second[candidate_id].as_dict()


def test_frozen_obvious_ood_uses_held_validation_not_strict_train() -> None:
    rows = _rows()
    first = build_frozen_dig_validation_obvious_ood(rows)
    changed_train = _frozen([[999.0, -999.0]] * 6)
    second = build_frozen_dig_validation_obvious_ood(
        replace(rows, train_features=changed_train)
    )

    np.testing.assert_array_equal(first.anchor_features, rows.validation_features)
    np.testing.assert_array_equal(first.features, second.features)
    assert first.anchor_partition == "validation"
    assert first.anchor_provenance == rows.validation_provenance
    assert first.provenance_dict()["anchor_source_episode_ids"] == [21]
    assert np.all(np.abs(first.perturbation) >= 32.0)


def test_validation_v1_edge_cohort_is_held_normal_validation_only() -> None:
    rows = replace(
        _rows(),
        validation_features=_frozen(
            [[-0.7, -0.7], [-0.3, -0.3], [0.3, 0.3], [1.2, 1.2]]
        ),
    )
    cohort = build_dig_validation_v1_edge_cohort(rows)

    assert cohort.anchor_partition == "validation"
    assert cohort.v1_fit_partition == "strict_train"
    assert cohort.validation_indices.tolist() == [3]
    np.testing.assert_array_equal(cohort.features, [[1.2, 1.2]])
    assert cohort.provenance == (rows.validation_provenance[3],)
    assert "held_validation" in cohort.provenance_dict()["membership"]


def test_audit_records_source_separation_and_never_admits_target_selection() -> None:
    result = run_dig_joint_support_validation_audit(rows=_rows())

    assert result["target_rollout_used_for_selection"] is False
    assert result["selection_input_scope"] == "strict_train_and_held_validation_only"
    assert result["runtime_support_change"] is False
    assert result["source_separation"]["source_disjoint"] is True
    assert result["source_separation"]["source_episode_id_overlap"] == []
    assert result["source_separation"]["train"]["source_episode_ids"] == [11, 12]
    assert result["source_separation"]["validation"]["source_episode_ids"] == [21]
    assert len(result["candidates"]) == len(DIG_JOINT_MAHALANOBIS_CANDIDATE_IDS)
    assert all("definition" in record for record in result["candidates"])
    assert all(
        record["definition"]["fit_partition"] == "strict_train"
        for record in result["candidates"]
    )
    assert "validation_v1_edge_cohort" in result
    assert "validation_v1_edge_coverage" in result["candidates"][0]


def test_selector_requires_both_gates_then_uses_ood_coverage_and_fixed_order() -> None:
    records = [
        _evaluation(
            candidate_id=candidate_id,
            fixed_order=index,
            coverage=0.995,
            rejection=0.995,
        )
        for index, candidate_id in enumerate(DIG_JOINT_MAHALANOBIS_CANDIDATE_IDS)
    ]
    records[1] = _evaluation(
        candidate_id=DIG_JOINT_MAHALANOBIS_CANDIDATE_IDS[1],
        fixed_order=1,
        coverage=0.999,
        edge_coverage=0.999,
        rejection=1.0,
    )
    assert select_dig_joint_support_candidate(records).candidate_id == records[1].candidate_id

    tied = [
        _evaluation(
            candidate_id=candidate_id,
            fixed_order=index,
            coverage=1.0,
            rejection=1.0,
        )
        for index, candidate_id in enumerate(DIG_JOINT_MAHALANOBIS_CANDIDATE_IDS)
    ]
    assert select_dig_joint_support_candidate(tied).candidate_id == tied[0].candidate_id

    rejected = [
        _evaluation(
            candidate_id=candidate_id,
            fixed_order=index,
            coverage=0.98,
            rejection=1.0,
        )
        for index, candidate_id in enumerate(DIG_JOINT_MAHALANOBIS_CANDIDATE_IDS)
    ]
    assert select_dig_joint_support_candidate(rejected) is None

    no_edge = [
        _evaluation(
            candidate_id=candidate_id,
            fixed_order=index,
            coverage=1.0,
            edge_coverage=None,
            rejection=1.0,
        )
        for index, candidate_id in enumerate(DIG_JOINT_MAHALANOBIS_CANDIDATE_IDS)
    ]
    assert select_dig_joint_support_candidate(no_edge) is None


def test_rejects_source_overlap_and_provenance_mismatch() -> None:
    rows = _rows()
    with pytest.raises(DigJointSupportValidationError, match="overlap"):
        validate_dig_joint_support_validation_rows(
            replace(rows, validation_source_episode_ids=(11,))
        )
    with pytest.raises(DigJointSupportValidationError, match="provenance sources"):
        validate_dig_joint_support_validation_rows(
            replace(rows, validation_source_episode_ids=(22,))
        )


def test_provenance_digest_is_stable_and_does_not_contain_feature_values() -> None:
    provenance = dig_joint_support_source_provenance(_rows())
    encoded = json.dumps(provenance, sort_keys=True)
    assert "provenance_sha256" in encoded
    assert "-1.0" not in encoded


def test_file_runner_writes_no_overwrite_artifact_without_target_input(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = tmp_path / "dig.yaml"
    config.write_text("task: {}\n", encoding="utf-8")
    split = tmp_path / "split.yaml"
    split.write_text("split: immutable\n", encoding="utf-8")
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    rows = replace(
        _rows(),
        training_config_path=str(config),
        split_path=str(split),
        primitive_dataset_dir=str(dataset),
    )
    import testbed.eval.dig_joint_support_validation_audit_runner as runner

    monkeypatch.setattr(runner, "load_dig_joint_support_validation_rows", lambda **_: rows)
    monkeypatch.setattr(
        runner,
        "_clean_code_record",
        lambda: {"git_head": "a" * 40, "git_branch": "test", "worktree_clean": True},
    )
    output = tmp_path / "audit"
    result = run_dig_joint_support_validation_audit_from_file(
        dig_training_config_path=config,
        output_root=output,
    )

    assert result["output_root"] == str(output.resolve())
    assert {path.name for path in output.iterdir()} == {
        "manifest.json",
        "candidates.json",
        "validation.json",
        "audit.json",
        "report.md",
    }
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["target_rollout_used_for_selection"] is False
    assert manifest["runtime_support_change"] is False
    with pytest.raises(FileExistsError, match="already exists"):
        run_dig_joint_support_validation_audit_from_file(
            dig_training_config_path=config,
            output_root=output,
        )


def test_file_runner_requires_clean_git_before_reading_support_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import testbed.eval.dig_joint_support_validation_audit_runner as runner

    monkeypatch.setattr(
        runner,
        "_clean_code_record",
        lambda: {"git_head": "a" * 40, "git_branch": "test", "worktree_clean": False},
    )
    monkeypatch.setattr(
        runner,
        "load_dig_joint_support_validation_rows",
        lambda **_: pytest.fail("dirty tree must fail before loading rows"),
    )
    with pytest.raises(RuntimeError, match="clean Git worktree"):
        run_dig_joint_support_validation_audit_from_file(
            dig_training_config_path=tmp_path / "not-read.yaml",
            output_root=tmp_path / "audit",
        )
