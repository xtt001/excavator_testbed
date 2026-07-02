from __future__ import annotations

import json
import tomllib
from pathlib import Path

from testbed.cli.terrain_residual_ab_artifact_pipeline import main
from testbed.data.schema import (
    ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
    ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX,
    ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
)


def _env_state_with_compact_grid(
    *,
    removed_depth: list[float],
    valid_mask: list[float],
    long_count: float = 3.0,
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


def _write_rollout_jsonl(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    records = [
        {
            "skill_name": "dig",
            "env_state": _env_state_with_compact_grid(
                removed_depth=[0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                valid_mask=[1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
            ),
        }
    ]
    path.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )


def _request_payload(source_path: Path, results_root: Path) -> dict[str, object]:
    return {
        "source_rollout_path": str(source_path),
        "results_root": str(results_root),
        "target_spec": {
            "target_id": "cli_unit_target",
            "grid_shape": [3, 2],
            "row_start": 0,
            "row_end": 2,
            "col_start": 0,
            "col_end": 1,
            "target_depth_m": 0.25,
            "official_semantics": "non_official_explicit_cli_unit_test_spec",
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
        "protected_evidence_roots": [str(source_path.parent.parent)],
    }


def test_cli_runs_pipeline_from_explicit_request_json(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    source_path = tmp_path / "source/results/rollouts/rollout_000.jsonl"
    results_root = tmp_path / "phase6f_cli/results"
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "pipeline_result.json"
    _write_rollout_jsonl(source_path)
    request_path.write_text(
        json.dumps(_request_payload(source_path, results_root), indent=2),
        encoding="utf-8",
    )

    rc = main(
        [
            "--request-json",
            str(request_path),
            "--output-json",
            str(output_path),
        ]
    )

    assert rc == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "present"
    assert payload["nested_statuses"]["predicted_ab_comparison"] == "present"
    assert payload["artifact_summary"]["artifact_count"] == 7
    assert payload["predicted_b_rollout_summary"]["selected_candidate_ids"]
    assert (results_root / "branch_comparison_report.json").is_file()
    assert (results_root / "residual_cut_intent_runtime_source.json").is_file()
    assert (results_root / "rollout_manifest.json").is_file()


def test_cli_rejects_missing_runtime_source_inputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    source_path = tmp_path / "source/results/rollouts/rollout_000.jsonl"
    results_root = tmp_path / "phase6f_cli/results"
    request_path = tmp_path / "request.json"
    output_path = tmp_path / "pipeline_result.json"
    _write_rollout_jsonl(source_path)
    request = _request_payload(source_path, results_root)
    request.pop("residual_cut_intent_runtime_source_inputs")
    request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")

    rc = main(
        [
            "--request-json",
            str(request_path),
            "--output-json",
            str(output_path),
        ]
    )

    assert rc == 2
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "invalid_request"
    assert payload["validation_errors"] == [
        "request JSON missing required fields: ['residual_cut_intent_runtime_source_inputs']"
    ]
    assert results_root.exists() is False


def test_console_script_exposes_pipeline_entrypoint() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"][
        "tb-terrain-residual-ab-artifacts"
    ] == "testbed.cli.terrain_residual_ab_artifact_pipeline:main"
