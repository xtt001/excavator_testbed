from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pytest
import yaml

from testbed.data.dig_local_state_support import (
    DIG_LOCAL_STATE_CANDIDATE_SPECS,
    assess_dig_local_state_support_candidate,
    assess_dig_local_state_support_candidate_from_cohort,
    build_dig_local_state_neighbor_cohort,
    fit_registered_dig_local_state_support_candidates,
    generate_frozen_dig_local_state_validation_ood,
    load_strict_dig_local_state_support_rows,
    summarize_dig_local_state_support_feasibility,
)
from testbed.data.hdf5_io import write_episode
from testbed.data.local_state_neighbor_queries import robust_train_scale


def _write_episode(path: Path, *, source_id: int, offset: float, masked: bool) -> None:
    count = 48
    row = np.arange(count, dtype=np.float32).reshape(-1, 1)
    axis = np.arange(4, dtype=np.float32).reshape(1, -1)
    qpos = 0.05 * row + 0.001 * offset + 0.01 * axis
    qvel = 0.04 * row + 0.002 * offset + 0.01 * axis
    token_axis = np.arange(10, dtype=np.float32).reshape(1, -1)
    token = 0.03 * row + 0.001 * offset + 0.001 * token_axis
    action = 0.02 * row + 0.002 * offset + 0.0001 * axis
    mask = np.ones(count, dtype=np.uint8)
    if masked:
        mask[[5, 29]] = 0
    write_episode(
        path,
        qpos=qpos,
        qvel=qvel,
        actions=action,
        step_ids=np.arange(1000, 1000 + count, dtype=np.int64),
        v2={"step": {"dig_cut_tokens": token, "action_loss_mask": mask}},
        metadata={"source_episode_id": f"episode_{source_id}"},
    )


def _fixture_config(tmp_path: Path, *, validation_offset: float = 9.0) -> Path:
    dataset_dir = tmp_path / "dig"
    dataset_dir.mkdir(parents=True)
    source_by_episode = {0: 10, 1: 11, 2: 12, 3: 13, 4: 90}
    for episode_id, source_id in source_by_episode.items():
        _write_episode(
            dataset_dir / f"episode_{episode_id}.hdf5",
            source_id=source_id,
            offset=(float(episode_id) if episode_id < 4 else validation_offset),
            masked=episode_id != 4,
        )
    split_path = tmp_path / "split.yaml"
    split_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "split_policy": "source_identity_exact_allowlist_v1",
                "dataset_dir": str(dataset_dir.resolve()),
                "train_ids": [0, 1, 2, 3],
                "val_ids": [4],
                "train_source_episode_ids": [10, 11, 12, 13],
                "val_source_episode_ids": [90],
                "allowed_source_episode_ids": [10, 11, 12, 13, 90],
                "source_episode_id_by_primitive_episode_id": source_by_episode,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    path = tmp_path / "dig_train.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "task": {"dataset_dir": str(dataset_dir.resolve())},
                "policy": {"low_dim_keys": ["qpos", "qvel", "dig_cut_tokens"]},
                "train": {
                    "split_path": str(split_path.resolve()),
                    "action_loss_mask_scope": "loss_sampling_stats",
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def test_loader_keeps_complete_masked_dig_state_actions_and_provenance(tmp_path: Path) -> None:
    rows = load_strict_dig_local_state_support_rows(training_config_path=_fixture_config(tmp_path))

    assert rows.train_features.shape == (184, 18)
    assert rows.validation_features.shape == (48, 18)
    assert rows.train_actions.shape == (184, 4)
    assert rows.validation_actions.shape == (48, 4)
    assert {item.source_episode_id for item in rows.train_provenance} == {10, 11, 12, 13}
    assert {item.source_episode_id for item in rows.validation_provenance} == {90}
    assert all(item.action_loss_mask == 1 for item in rows.train_provenance)
    assert not rows.train_features.flags.writeable
    assert not rows.train_actions.flags.writeable
    assert rows.as_dict()["action_rows"].endswith("mask_equals_1_only")


def test_fixed_candidate_family_fits_train_only_and_records_calibration_provenance(tmp_path: Path) -> None:
    first_rows = load_strict_dig_local_state_support_rows(training_config_path=_fixture_config(tmp_path / "a"))
    second_rows = load_strict_dig_local_state_support_rows(
        training_config_path=_fixture_config(tmp_path / "b", validation_offset=999.0)
    )
    first = fit_registered_dig_local_state_support_candidates(first_rows)
    second = fit_registered_dig_local_state_support_candidates(second_rows)

    assert tuple(first) == tuple(spec.candidate_id for spec in DIG_LOCAL_STATE_CANDIDATE_SPECS)
    assert [spec.k_neighbors for spec in DIG_LOCAL_STATE_CANDIDATE_SPECS] == [8, 16, 32]
    assert [spec.min_distinct_source_episode_ids for spec in DIG_LOCAL_STATE_CANDIDATE_SPECS] == [2, 2, 3]
    for candidate_id, candidate in first.items():
        assert candidate.fit_partition == "strict_train"
        assert candidate.distance_threshold_quantile == pytest.approx(0.99)
        assert candidate.action_coherence_threshold_quantile == pytest.approx(0.99)
        assert candidate.calibration_query_count == len(candidate.calibration_queries)
        assert candidate.calibration_queries_meeting_source_requirement > 0
        assert candidate.calibration_queries_failing_source_requirement >= 0
        assert all(item.provenance.partition == "train" for item in candidate.calibration_queries)
        assert candidate.as_dict() == second[candidate_id].as_dict()
    assert "target" not in inspect.signature(fit_registered_dig_local_state_support_candidates).parameters


def test_assessment_excludes_requested_source_and_reports_neighbor_action_diagnostics(tmp_path: Path) -> None:
    rows = load_strict_dig_local_state_support_rows(training_config_path=_fixture_config(tmp_path))
    candidate = fit_registered_dig_local_state_support_candidates(rows)[
        "dig_local_complete_state_k16_sources2_v1"
    ]
    query = np.asarray(rows.train_features[[0]], dtype=np.float64)
    assessment = assess_dig_local_state_support_candidate(
        candidate,
        query,
        query_source_episode_ids=[10],
    )
    payload = assessment.as_dict()
    row = payload["rows"][0]

    assert len(row["neighbors"]) == candidate.k_neighbors
    assert all(item["provenance"]["source_episode_id"] != 10 for item in row["neighbors"])
    assert row["distinct_source_episode_count"] >= candidate.min_distinct_source_episode_ids
    assert len(row["action_coherence_axis_scores"]) == 4
    assert len(row["action_coherence_centre"]) == 4
    assert payload["query_engine"] == "numpy_blocked_exact_normalized_l2_cpu_v1"


def test_family_cohort_reuses_one_max_k_query_without_changing_each_predicate(tmp_path: Path) -> None:
    rows = load_strict_dig_local_state_support_rows(training_config_path=_fixture_config(tmp_path))
    candidates = fit_registered_dig_local_state_support_candidates(rows)
    features = np.asarray(rows.validation_features[:3], dtype=np.float64)
    cohort = build_dig_local_state_neighbor_cohort(
        candidates,
        features,
        query_source_episode_ids=[90, 90, 90],
    )

    assert cohort.max_k_neighbors == 32
    assert cohort.candidate_ids == tuple(candidates)
    for candidate in candidates.values():
        reused = assess_dig_local_state_support_candidate_from_cohort(candidate, cohort)
        individual = assess_dig_local_state_support_candidate(
            candidate,
            features,
            query_source_episode_ids=[90, 90, 90],
        )
        assert reused.as_dict() == individual.as_dict()


def test_feasibility_and_validation_ood_are_target_free_and_scale_uses_fallback() -> None:
    scale = robust_train_scale(np.asarray([[2.0, 1.0], [2.0, 3.0], [2.0, 5.0]]))
    assert scale.methods[0] == "relative_epsilon_floor"
    assert scale.scale[0] > 0.0


def test_feasibility_and_validation_ood_are_target_free(tmp_path: Path) -> None:
    rows = load_strict_dig_local_state_support_rows(training_config_path=_fixture_config(tmp_path))
    candidates = fit_registered_dig_local_state_support_candidates(rows)
    summary = summarize_dig_local_state_support_feasibility(rows, candidates)
    ood = generate_frozen_dig_local_state_validation_ood(rows)

    assert summary["target_rollout_used_for_fit_or_summary"] is False
    assert summary["validation_partition"] == "held_out_source_disjoint"
    assert tuple(summary["candidate_feasibility"]) == tuple(candidates)
    assert ood.anchor_provenance == rows.validation_provenance
    np.testing.assert_array_equal(ood.anchor_features, rows.validation_features)
