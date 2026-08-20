from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from testbed.eval import dig_local_state_support_validation_runner as runner


def _audit() -> dict[str, object]:
    return {
        "schema": "dig_local_complete_state_validation_v1",
        "support_contract_version": "support_contract_v2_dig_local_state_v1",
        "primitive": "dig",
        "status": "support_contract_not_selected",
        "diagnostic_only": True,
        "promotion_eligible": False,
        "runtime_support_change": False,
        "target_rollout_used_for_selection": False,
        "selection_input_scope": "strict_train_and_held_validation_only",
        "candidate_family": {"candidate_ids_in_fixed_order": ["candidate"]},
        "selection_metrics": {"validation_normal_coverage_min": 0.99},
        "source_separation": {"source_disjoint": True},
        "strict_train_feasibility": {"train_row_count": 4},
        "validation_neighbor_cohort": {"query_row_count": 2},
        "frozen_obvious_ood_neighbor_cohort": {"query_row_count": 2},
        "frozen_obvious_ood": {
            "schema": "frozen_obvious_ood_from_validation_v1",
            "feature_order": ["qvel[1]"],
            "anchor_partition": "validation",
            "multiplier": 32.0,
            "anchor_provenance": [
                {"source_episode_id": 31},
                {"source_episode_id": 32},
            ],
        },
        "candidates": [
            {
                "candidate_id": "candidate",
                "fixed_order": 0,
                "validation_normal_coverage": 0.8,
                "validation_distance_coverage": 0.9,
                "validation_neighbor_count_coverage": 1.0,
                "validation_source_diversity_coverage": 1.0,
                "validation_action_coherence_coverage": 1.0,
                "validation_action_axis_coherence_coverage": 1.0,
                "frozen_obvious_ood_rejection": 1.0,
                "validation_normal_coverage_passed": False,
                "frozen_obvious_ood_rejection_passed": True,
                "qualified": False,
                "qualification_status": "rejected_validation_coverage",
                "definition": {"fit_partition": "strict_train"},
            }
        ],
        "selected_candidate_id": None,
        "selection_status": "not_selected",
    }


def test_runner_writes_compact_no_target_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "dig.yaml"
    config.write_text("task: {}\n", encoding="utf-8")
    split = tmp_path / "split.yaml"
    split.write_text("split: immutable\n", encoding="utf-8")
    dataset = tmp_path / "dataset"
    dataset.mkdir()
    rows = SimpleNamespace(
        primitive_dataset_dir=str(dataset),
        split_path=str(split),
    )
    monkeypatch.setattr(
        runner,
        "_clean_code_record",
        lambda: {"git_head": "a" * 40, "git_branch": "test", "worktree_clean": True},
    )
    monkeypatch.setattr(
        runner, "load_strict_dig_local_state_support_rows", lambda **_: rows
    )
    monkeypatch.setattr(runner, "run_dig_local_state_support_validation", lambda **_: _audit())
    output = tmp_path / "audit"

    result = runner.run_dig_local_state_support_validation_from_file(
        dig_training_config_path=config,
        output_root=output,
    )

    assert result["status"] == "support_contract_not_selected"
    assert {path.name for path in output.iterdir()} == {
        "manifest.json",
        "candidates.json",
        "validation.json",
        "report.md",
    }
    validation = json.loads((output / "validation.json").read_text(encoding="utf-8"))
    assert validation["target_rollout_used_for_selection"] is False
    assert validation["frozen_obvious_ood"]["anchor_source_episode_ids"] == [31, 32]
    assert validation["frozen_obvious_ood"]["provenance_serialized"] is False
    with pytest.raises(FileExistsError, match="already exists"):
        runner.run_dig_local_state_support_validation_from_file(
            dig_training_config_path=config,
            output_root=output,
        )


def test_runner_requires_clean_code_before_loading_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = tmp_path / "dig.yaml"
    config.write_text("task: {}\n", encoding="utf-8")
    called = False

    def load_rows(**_: object) -> object:
        nonlocal called
        called = True
        raise AssertionError("must not read rows from a dirty worktree")

    monkeypatch.setattr(
        runner,
        "_clean_code_record",
        lambda: {"git_head": "a" * 40, "git_branch": "test", "worktree_clean": False},
    )
    monkeypatch.setattr(runner, "load_strict_dig_local_state_support_rows", load_rows)

    with pytest.raises(RuntimeError, match="clean Git worktree"):
        runner.run_dig_local_state_support_validation_from_file(
            dig_training_config_path=config,
            output_root=tmp_path / "audit",
        )
    assert called is False
