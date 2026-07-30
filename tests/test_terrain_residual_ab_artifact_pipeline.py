from __future__ import annotations

import json

from testbed.data.schema import (
    ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
    ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX,
    ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
)
from testbed.eval.terrain_residual_ab_artifact_pipeline import (
    build_and_write_predicted_residual_ab_artifacts,
)
from testbed.planner.primitive.token.residual_cut_intent_source import (
    RESIDUAL_CUT_INTENT_RUNTIME_SOURCE_SCHEMA,
    build_residual_cut_intent_plan_provider_from_source_path,
)

EXPECTED_FILES = [
    "eval_run_metadata.json",
    "experiment_manifest.json",
    "branch_run_plan.json",
    "predicted_b_rollout.json",
    "residual_cut_intent_runtime_source.json",
    "branch_comparison_report.json",
    "rollout_manifest.json",
]


def _env_state_with_compact_grid(
    *,
    removed_depth: list[float],
    valid_mask: list[float],
    long_count: float = 2.0,
    short_count: float = 2.0,
) -> list[float]:
    values = [0.0] * 64
    values[ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX] = long_count
    values[ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX] = short_count
    cell_count = len(removed_depth)
    values[
        ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX : ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX
        + cell_count
    ] = removed_depth
    values[
        ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX : ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX
        + cell_count
    ] = valid_mask
    return values


def _write_rollout_jsonl(path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _write_unit_rollout(path) -> None:
    _write_rollout_jsonl(
        path,
        [
            {
                "skill_name": "dig",
                "env_state": _env_state_with_compact_grid(
                    removed_depth=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                    valid_mask=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
                    long_count=3.0,
                    short_count=2.0,
                ),
            },
            {
                "skill_name": "dig",
                "env_state": _env_state_with_compact_grid(
                    removed_depth=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                    valid_mask=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
                    long_count=3.0,
                    short_count=2.0,
                ),
            },
        ],
    )


def _pipeline_kwargs(source_path="runs/eval/source/results/rollouts/rollout_000.jsonl"):
    return {
        "source_rollout_path": source_path,
        "results_root": "runs/eval/phase6f_pipeline/results",
        "target_spec": {
            "target_id": "unit_test_target",
            "grid_shape": [3, 2],
            "row_start": 0,
            "row_end": 2,
            "col_start": 0,
            "col_end": 1,
            "target_depth_m": 0.25,
            "official_semantics": "non_official_explicit_unit_test_spec",
        },
        "cycle_budget": {"max_cycles": 3},
        "candidate_generation_options": {
            "direction_options": [
                "row_forward",
                "row_reverse",
                "col_forward",
                "col_reverse",
            ],
            "depth_fraction_options": [0.5, 0.75, 1.0],
            "min_candidate_count": 20,
            "max_candidate_count": 100,
        },
        "candidate_constraint_options": {
            "max_candidate_depth_m": 0.2,
            "protected_boundary_cell_radius": 1,
            "return_origin_cell_index": 0,
        },
        "scoring_weights": {
            "candidate_depth_reward": 10.0,
            "target_footprint_cell_reward": 1.0,
            "outside_target_footprint_cell_penalty": 2.0,
            "outside_protected_boundary_cell_penalty": 4.0,
            "depth_budget_exceeded_penalty": 5.0,
            "grid_boundary_clipped_penalty": 0.5,
            "return_alignment_distance_penalty": 0.25,
        },
        "effect_geometry": {
            "cell_size_m": 0.25,
            "bucket_width_m": 0.25,
            "bucket_length_m": 0.5,
            "penetration_depth_m": None,
        },
        "payload_capacity_m3": 0.04,
        "residual_cut_intent_runtime_source_inputs": {
            "cell_centers_m": {
                str(index): {
                    "x_m": float(index // 2) * 0.25,
                    "z_m": float(index % 2) * 0.25,
                }
                for index in range(6)
            },
            "direction_vectors": {
                "row_forward": {"x": 1.0, "z": 0.0},
                "row_reverse": {"x": -1.0, "z": 0.0},
                "col_forward": {"x": 0.0, "z": 1.0},
                "col_reverse": {"x": 0.0, "z": -1.0},
            },
            "bucket_length_m": 0.5,
            "payload_kg": 12.5,
        },
        "selection_policy": "score_ranking_first",
        "protected_evidence_roots": ["runs/eval/protected/results"],
    }


def _build_pipeline(**overrides):
    kwargs = _pipeline_kwargs()
    kwargs.update(overrides)
    return build_and_write_predicted_residual_ab_artifacts(**kwargs)


def _all_keys(value):
    if isinstance(value, dict):
        for key, nested_value in value.items():
            yield key
            yield from _all_keys(nested_value)
    elif isinstance(value, list):
        for nested_value in value:
            yield from _all_keys(nested_value)


def test_pipeline_builds_chain_and_writes_predicted_ab_artifacts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source_path = tmp_path / "runs/eval/source/results/rollouts/rollout_000.jsonl"
    _write_unit_rollout(source_path)

    result = _build_pipeline()

    assert result["status"] == "present"
    assert result["schema"] == "terrain_residual_predicted_ab_artifact_pipeline_v1"
    assert result["source"] == "explicit_predicted_residual_ab_artifact_pipeline"
    assert result["offline_only"] is True
    assert result["source_rollout_path"] == (
        "runs/eval/source/results/rollouts/rollout_000.jsonl"
    )
    assert result["results_root"] == "runs/eval/phase6f_pipeline/results"
    assert result["source_record_count"] == 2
    assert result["nested_statuses"] == {
        "target_residual_report": "present",
        "experiment_manifest": "present",
        "branch_run_plan": "present",
        "predicted_b_rollout": "present",
        "residual_cut_intent_runtime_source": "present",
        "predicted_ab_comparison": "present",
        "artifact_writer": "present",
    }
    assert result["artifact_summary"] == {
        "status": "present",
        "artifact_count": 7,
        "written_files": EXPECTED_FILES,
        "results_root": "runs/eval/phase6f_pipeline/results",
    }
    assert result["branch_statuses"] == {
        "current_planner_baseline": "present",
        "heuristic_residual_pipeline": "present",
        "calibrated_residual_pipeline": "not_evaluated",
    }
    assert result["predicted_b_rollout_summary"] == {
        "status": "present",
        "step_count": 2,
        "stop_reason": "zero_target_positive_residual",
        "selected_candidate_ids": ["cut_candidate_000008", "cut_candidate_000009"],
    }
    assert result["comparison_delta_summary"] == {
        "target_positive_residual_depth_delta_m": -0.5,
        "target_positive_residual_improvement_m": 0.5,
        "target_removed_completion_ratio_delta": 1.0,
        "target_overdig_depth_increase_m": 0.0,
        "outside_target_removed_depth_increase_m": 0.25,
        "expected_delta_depth_sum_m": 0.75,
        "expected_delta_volume_m3": 0.046875,
    }
    assert result["validation_errors"] == []
    assert result["provenance_statuses"]["jsonl_read_status"] == "read"
    assert result["provenance_statuses"]["artifact_write_status"] == "written"

    root = tmp_path / "runs/eval/phase6f_pipeline/results"
    assert sorted(path.name for path in root.iterdir()) == sorted(EXPECTED_FILES)
    comparison = json.loads((root / "branch_comparison_report.json").read_text())
    assert comparison["branches"]["heuristic_residual_pipeline"][
        "evidence_type"
    ] == "predicted_counterfactual"
    runtime_source = json.loads(
        (root / "residual_cut_intent_runtime_source.json").read_text()
    )
    assert runtime_source["schema"] == RESIDUAL_CUT_INTENT_RUNTIME_SOURCE_SCHEMA
    assert runtime_source["status"] == "present"
    assert [plan["cycle_index"] for plan in runtime_source["plans"]] == [0, 1]
    assert [
        plan["cut_intent_candidate_id"] for plan in runtime_source["plans"]
    ] == ["cut_candidate_000008", "cut_candidate_000009"]
    source_provider = build_residual_cut_intent_plan_provider_from_source_path(
        root / "residual_cut_intent_runtime_source.json",
        cycle_index=lambda: 1,
    )
    assert source_provider is not None
    token, raw_fields, source, fallback_reason = source_provider({"id": "obs"})
    assert len(token) == 10
    assert raw_fields["operator_cut_payload_gain_kg"] == 12.5
    assert source == "explicit_residual_cut_intent_dig_cut_token"
    assert fallback_reason == ""

    all_keys = set(_all_keys(result))
    assert "runtime_action" not in all_keys
    assert "command_space_controls" not in all_keys
    assert "pass_fail" not in all_keys
    assert "eval_success" not in all_keys
    assert "planner_success" not in all_keys
    assert "production_readiness" not in all_keys
    assert "calibrated_fallback" not in all_keys


def test_pipeline_reports_invalid_source_rollout_without_writing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = _build_pipeline()

    assert result["status"] == "invalid_source_rollout"
    assert result["nested_statuses"]["source_rollout"] == "missing"
    assert result["artifact_summary"]["artifact_count"] == 0
    assert (tmp_path / "runs/eval/phase6f_pipeline/results").exists() is False


def test_pipeline_reports_invalid_target_and_option_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source_path = tmp_path / "runs/eval/source/results/rollouts/rollout_000.jsonl"
    _write_unit_rollout(source_path)

    invalid_target = _pipeline_kwargs()["target_spec"].copy()
    invalid_target.pop("target_depth_m")
    target_result = _build_pipeline(target_spec=invalid_target)
    assert target_result["status"] == "invalid_target_spec"
    assert target_result["artifact_summary"]["artifact_count"] == 0

    option_result = _build_pipeline(cycle_budget={"max_cycles": 0})
    assert option_result["status"] == "invalid_pipeline_options"
    assert option_result["nested_statuses"]["predicted_b_rollout"] == (
        "invalid_cycle_budget"
    )
    assert option_result["artifact_summary"]["artifact_count"] == 0


def test_pipeline_rejects_invalid_runtime_source_inputs_without_writing(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    source_path = tmp_path / "runs/eval/source/results/rollouts/rollout_000.jsonl"
    _write_unit_rollout(source_path)

    invalid_result = _build_pipeline(
        residual_cut_intent_runtime_source_inputs={
            "cell_centers_m": {},
            "direction_vectors": {
                "row_forward": {"x": 1.0, "z": 0.0},
                "row_reverse": {"x": -1.0, "z": 0.0},
                "col_forward": {"x": 0.0, "z": 1.0},
                "col_reverse": {"x": 0.0, "z": -1.0},
            },
            "bucket_length_m": 0.5,
            "payload_kg": 12.5,
        },
    )

    assert invalid_result["status"] == "invalid_runtime_source_inputs"
    assert invalid_result["nested_statuses"]["residual_cut_intent_runtime_source"] == (
        "invalid"
    )
    assert invalid_result["artifact_summary"]["artifact_count"] == 0
    assert (tmp_path / "runs/eval/phase6f_pipeline/results").exists() is False


def test_pipeline_passes_through_writer_rejections(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source_path = tmp_path / "runs/eval/source/results/rollouts/rollout_000.jsonl"
    _write_unit_rollout(source_path)

    protected_result = _build_pipeline(
        results_root="runs/eval/protected/results/phase6f_pipeline",
    )
    assert protected_result["status"] == "protected_evidence_root_overlap"
    assert protected_result["nested_statuses"]["experiment_manifest"] == (
        "protected_evidence_root_overlap"
    )
    assert protected_result["nested_statuses"]["artifact_writer"] is None
    assert (
        tmp_path / "runs/eval/protected/results/phase6f_pipeline"
    ).exists() is False

    existing_root = tmp_path / "runs/eval/existing/results"
    existing_root.mkdir(parents=True)
    existing_result = _build_pipeline(results_root="runs/eval/existing/results")
    assert existing_result["status"] == "results_root_already_exists"
    assert existing_result["nested_statuses"]["artifact_writer"] == (
        "results_root_already_exists"
    )
