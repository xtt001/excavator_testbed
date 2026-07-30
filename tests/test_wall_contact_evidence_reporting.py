from __future__ import annotations

from itertools import product
from pathlib import Path

import pytest

from testbed.eval.wall_contact_artifact_io import WallContactArtifactError
from testbed.eval.wall_contact_evidence_reporting import (
    DIAGNOSTIC_NEAR_WALL_THRESHOLD_M,
    build_causal_report_sections,
    render_causal_report_markdown,
    summarize_expert_replay_records,
    summarize_geometry_paths,
    summarize_paired_ab_attempts,
)
from testbed.eval.wall_contact_experiment_contracts import validate_geometry_path
from testbed.eval.wall_contact_source_spec import (
    PYTHON_LINEAGE_REQUIRED_RELATIVE_PATHS,
    build_python_source_lineage,
    lock_python_source_lineage,
)

WALLS = (
    "Dig_XMin_Board",
    "Dig_XMax_Board",
    "Dig_ZMin_Board",
    "Dig_ZMax_Board",
)


def _geometry_pair(
    component: str,
    wall: str,
    *,
    clearance_m: float,
    contact: bool = False,
) -> dict[str, object]:
    sample = {
        "path_id": "train_1",
        "component": component,
        "wall_name": wall,
        "machine_shape_path": "/machine/bucket",
        "wall_shape_path": f"/walls/{wall}",
        "bucket_local_point_m": [0.1, 0.2, 0.3],
        "world_point_m": [1.0, 2.0, 3.0],
        "qpos": [0.0, 0.1, 0.2, 0.3],
        "sample_index": 1,
        "source_path_index": 1,
        "overlap": False,
    }
    return {
        "component": component,
        "wall_name": wall,
        "machine_shape_paths": [f"/machine/{component}"],
        "wall_shape_paths": [f"/walls/{wall}"],
        "minimum_clearance_m": clearance_m,
        "contact_or_overlap_intervals": [[1, 1]] if contact else [],
        "overlap_intervals": [],
        "bucket_local_contact_region_samples": (
            [sample] if component == "bucket" and contact else []
        ),
    }


def _detailed_summary(
    *,
    categories: list[str],
    pair: dict[str, object] | None,
) -> dict[str, object]:
    return {
        "contact_observed": pair is not None,
        "categories": categories,
        "peak_force_n": (
            float(pair["peak_total_force_n"]) if pair is not None else 0.0
        ),
        "component_wall_summaries": [] if pair is None else [pair],
    }


def _force_pair(
    component: str,
    wall: str,
    *,
    scale: float,
) -> dict[str, object]:
    return {
        "component": component,
        "wall_name": wall,
        "peak_normal_force_n": 10.0 * scale,
        "rms_normal_force_n": 8.0 * scale,
        "peak_tangential_force_n": 4.0 * scale,
        "rms_tangential_force_n": 3.0 * scale,
        "peak_total_force_n": 11.0 * scale,
        "rms_total_force_n": 9.0 * scale,
        "normal_impulse_n_s": 2.0 * scale,
        "session_count": 1,
        "contact_duration_s": 0.2 * scale,
        "maximum_session_duration_s": 0.2 * scale,
        "maximum_tangential_displacement_m": 0.01 * scale,
        "callback_count": 2,
        "contact_point_count": 3,
        "bucket_local_contact_region_samples": (
            [[0.1, 0.2, 0.3]] if component == "bucket" else []
        ),
    }


def test_geometry_validation_and_summary_preserve_all_twelve_pairs() -> None:
    expected = {
        "path_id": "train_1",
        "source_episode_id": 1,
        "split": "train",
        "source_hdf5_sha256": "a" * 64,
        "qpos_path_sha256": "b" * 64,
        "qpos_path": [[0.0] * 4, [0.1] * 4],
    }
    measured = {
        **{
            key: expected[key]
            for key in (
                "path_id",
                "source_episode_id",
                "split",
                "source_hdf5_sha256",
                "qpos_path_sha256",
            )
        },
        "adaptive_sampling": {
            "proved": True,
            "maximum_subsegment_motion_bound_m": 0.01,
        },
        "component_wall_pairs": [
            _geometry_pair(component, wall, clearance_m=0.5)
            for component, wall in product(("boom", "stick", "bucket"), WALLS)
        ],
    }

    validated = validate_geometry_path(expected=expected, measured=measured)

    assert len(validated["component_wall_pairs"]) == 12
    assert validated["contact_or_overlap_pairs"] == []

    validated["component_wall_pairs"][0]["minimum_clearance_m"] = 0.20
    bucket_index = next(
        index
        for index, pair in enumerate(validated["component_wall_pairs"])
        if pair["component"] == "bucket"
        and pair["wall_name"] == "Dig_ZMax_Board"
    )
    validated["component_wall_pairs"][bucket_index] = {
        **validated["component_wall_pairs"][bucket_index],
        "minimum_clearance_m": 0.0,
        "contact_or_overlap_intervals": [[1, 1]],
        "bucket_local_contact_region_samples": [[0.1, 0.2, 0.3]],
    }
    summary = summarize_geometry_paths([validated])

    assert summary["diagnostic_near_wall_threshold_m"] == 0.24
    assert summary["threshold_role"] == "diagnostic_only_not_production_contract"
    assert summary["path_count"] == 1
    assert len(summary["component_wall_statistics"]) == 12
    assert summary["classification_counts"] == {
        "clear": 10,
        "contact_or_overlap": 1,
        "near_wall": 1,
    }
    contact_row = next(
        row
        for row in summary["component_wall_statistics"]
        if row["classification_counts"]["contact_or_overlap"] == 1
    )
    assert contact_row["contact_or_overlap_intervals"][0]["intervals"] == [[1, 1]]
    assert contact_row["bucket_local_contact_region_samples"] == [
        [0.1, 0.2, 0.3]
    ]
    assert DIAGNOSTIC_NEAR_WALL_THRESHOLD_M == 0.24


def test_expert_summary_separates_train_inference_from_holdout_and_invalid() -> None:
    train_valid_pair = _force_pair(
        "bucket",
        "Dig_XMin_Board",
        scale=1.0,
    )
    invalid_pair = _force_pair(
        "stick",
        "Dig_XMax_Board",
        scale=10_000.0,
    )
    holdout_pair = _force_pair(
        "bucket",
        "Dig_ZMin_Board",
        scale=2.0,
    )
    empty = _detailed_summary(categories=["near_wall"], pair=None)
    records = [
        {
            "source_episode_id": 1,
            "split": "train",
            "status": "passed",
            "windows": [
                {
                    "status": "passed",
                    "valid_for_inference": True,
                    "all_diagnostic_contact_summary": _detailed_summary(
                        categories=["bucket_touch"],
                        pair=train_valid_pair,
                    ),
                    "production_inference_contact_summary": _detailed_summary(
                        categories=["bucket_touch"],
                        pair=train_valid_pair,
                    ),
                },
                {
                    "status": "invalid",
                    "valid_for_inference": False,
                    "all_diagnostic_contact_summary": _detailed_summary(
                        categories=[
                            "forbidden_component",
                            "high_force_collision",
                        ],
                        pair=invalid_pair,
                    ),
                    "production_inference_contact_summary": empty,
                },
            ],
        },
        {
            "source_episode_id": 2,
            "split": "validation",
            "status": "passed",
            "windows": [
                {
                    "status": "passed",
                    "valid_for_inference": False,
                    "all_diagnostic_contact_summary": _detailed_summary(
                        categories=["bucket_scrape_like"],
                        pair=holdout_pair,
                    ),
                    "production_inference_contact_summary": empty,
                }
            ],
        },
    ]

    summary = summarize_expert_replay_records(records)

    assert summary["train"]["source_count"] == 1
    assert summary["train"]["window_count"] == 2
    assert summary["train"]["window_status_counts"] == {
        "blocked": 0,
        "invalid": 1,
        "passed": 1,
    }
    assert summary["train"]["valid_for_inference_window_count"] == 1
    assert summary["train"]["diagnostic_window_category_counts"][
        "high_force_collision"
    ] == 1
    assert summary["train"]["inference_component_wall_statistics"] == [
        train_valid_pair
    ]
    assert all(
        row["component"] != "stick"
        for row in summary["train"]["inference_component_wall_statistics"]
    )
    assert summary["holdout"]["source_count"] == 1
    assert summary["holdout"]["used_for_region_or_budget_selection"] is False
    assert summary["holdout"]["selection_eligible"] is False
    assert summary["holdout"]["diagnostic_component_wall_statistics"] == [
        holdout_pair
    ]
    assert summary["holdout"]["diagnostic_window_category_counts"][
        "bucket_scrape_like"
    ] == 1


def test_paired_ab_summary_keeps_per_seed_fairness_and_b_outcome() -> None:
    attempts = []
    for seed in (0, 1, 2):
        fairness = {"valid": True, "violations": [], "metrics": {"seed": seed}}
        attempts.extend(
            (
                {
                    "seed": seed,
                    "pair_id": f"seed_{seed}",
                    "condition": "A",
                    "pair_valid": True,
                    "reset_fairness": fairness,
                    "entered_carry": False,
                    "dump_completed": False,
                    "contact_ended_before_carry": False,
                    "terminal_reason": "wall_contact_first_session",
                    "hard_violation": False,
                    "hard_stop_violations": [],
                    "contact_driven_hard_failure": False,
                },
                {
                    "seed": seed,
                    "pair_id": f"seed_{seed}",
                    "condition": "B",
                    "pair_valid": True,
                    "reset_fairness": fairness,
                    "entered_carry": True,
                    "dump_completed": True,
                    "contact_ended_before_carry": True,
                    "terminal_reason": "target_dump_complete",
                    "hard_violation": False,
                    "hard_stop_violations": [],
                    "contact_driven_hard_failure": False,
                },
            )
        )

    summary = summarize_paired_ab_attempts(attempts)

    assert summary["pair_count"] == 3
    assert summary["valid_pair_count"] == 3
    assert summary["b_outcome_counts"] == {
        "contact_driven_hard_failure": 0,
        "contact_ended_before_carry": 3,
        "dump_completed": 3,
        "entered_carry": 3,
        "hard_violation": 0,
    }
    assert summary["pairs"][1]["reset_fairness"]["metrics"]["seed"] == 1
    assert summary["pairs"][1]["B"]["hard_reason"] == []
    assert summary["pairs"][1]["B"]["terminal_reason"] == "target_dump_complete"


def test_causal_report_embeds_evidence_rationale_and_pauses_all_future_gates() -> None:
    geometry_summary = {
        "schema": "wall_contact_geometry_summary_v1",
        "path_count": 376,
    }
    expert_summary = {
        "schema": "wall_contact_expert_replay_summary_v1",
        "train": {"source_count": 16},
        "holdout": {
            "source_count": 2,
            "used_for_region_or_budget_selection": False,
        },
    }
    ab_summary = {
        "schema": "wall_contact_paired_ab_summary_v1",
        "pair_count": 3,
        "valid_pair_count": 3,
        "b_outcome_counts": {
            "contact_driven_hard_failure": 0,
            "contact_ended_before_carry": 3,
            "dump_completed": 3,
            "entered_carry": 3,
            "hard_violation": 0,
        },
        "pairs": [],
    }

    sections = build_causal_report_sections(
        geometry_collection={"summary": geometry_summary},
        expert_replay_collection={"summary": expert_summary},
        paired_ab_collection={
            "summary": ab_summary,
            "expert_lineage_complete": True,
            "expert_same_region_sub_100kn": False,
        },
        classification="safety_too_strict",
        blockers=[],
    )

    assert sections["geometry_summary"] is geometry_summary
    assert sections["expert_replay_summary"] is expert_summary
    assert sections["paired_ab_summary"] is ab_summary
    assert sections["classification_rationale"]["rule_satisfied"] is True
    assert sections["pause"]["required"] is True
    assert sections["pause"]["production_budget_inferred"] is False
    assert sections["future_gates"]
    assert not any(sections["future_gates"].values())

    report = {
        "status": "passed",
        "causal_classification": "safety_too_strict",
        **sections,
    }
    markdown = render_causal_report_markdown(report)
    assert "3/3" in markdown
    assert "production budget inferred: `false`" in markdown
    assert "qpos predictor" in markdown


def test_python_lineage_locks_exact_runtime_and_evidence_source_inventory(
    tmp_path: Path,
) -> None:
    for relative in PYTHON_LINEAGE_REQUIRED_RELATIVE_PATHS:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {relative}\n", encoding="utf-8")

    lineage = build_python_source_lineage(repo_root=tmp_path)
    references, aggregate = lock_python_source_lineage(
        lineage,
        expected_repo_root=tmp_path,
    )

    assert [item["relative_path"] for item in lineage["lineage_files"]] == list(
        PYTHON_LINEAGE_REQUIRED_RELATIVE_PATHS
    )
    assert len(references) == len(PYTHON_LINEAGE_REQUIRED_RELATIVE_PATHS)
    assert aggregate == lineage["lineage_aggregate_sha256"]
    required = set(PYTHON_LINEAGE_REQUIRED_RELATIVE_PATHS)
    assert {
        "testbed/planner/box_emptying/wall_contact_detail.py",
        "testbed/planner/box_emptying/safety_contracts.py",
        "testbed/planner/box_emptying/safety_interlock.py",
        "testbed/planner/primitive/config/adapter.py",
        "testbed/eval/suite.py",
        "testbed/eval/expert_wall_contact_replay.py",
        "testbed/eval/wall_contact_ab_runner.py",
        "testbed/eval/wall_contact_ab_collection.py",
        "testbed/eval/wall_contact_evidence_contracts.py",
        "testbed/eval/wall_contact_evidence_reporting.py",
        "testbed/cli/wall_contact_semantics_experiment.py",
    }.issubset(required)

    drifted = tmp_path / PYTHON_LINEAGE_REQUIRED_RELATIVE_PATHS[0]
    drifted.write_text("# drift\n", encoding="utf-8")
    with pytest.raises(WallContactArtifactError, match="sha256_drift"):
        lock_python_source_lineage(
            lineage,
            expected_repo_root=tmp_path,
        )
