from __future__ import annotations

import json
from pathlib import Path

from testbed.cli.train_terrain_effect_ensemble import main


def _record(index: int) -> dict:
    moved = bool(index % 2)
    return {
        "schema": "executed_cut_silver_sample_v1",
        "effect_input_schema": "terrain_effect_input_v1",
        "episode_id": f"episode_{index}",
        "reset_group_id": f"reset_{index}",
        "cycle_id": 0,
        "pre_terrain": {
            "surface_depth_m": [0.2] * 6,
            "removed_depth_m": [0.01 * index] * 6,
            "valid_mask": [1.0] * 6,
            "surface_valid_fraction": [1.0] * 6,
            "baseline_depth_m": [0.0] * 6,
            "grid_origin_world_m": [1.0, 0.0, 2.0],
            "long_axis_unit_world": [1.0, 0.0, 0.0],
            "short_axis_unit_world": [0.0, 0.0, 1.0],
            "cell_long_size_m": 0.5,
            "cell_short_size_m": 0.4,
            "cell_area_m2": 0.2,
            "reference_plane_local_y_m": 0.0,
        },
        "execution_context": {
            "cycle_index": index,
            "entry_qpos": [0.1, 0.2, 0.3, 0.4],
            "entry_qvel": [0.01, 0.02, 0.03, 0.04],
            "entry_bucket_tip_xyz_m": [0.0, 0.0, 0.0],
            "previous_outcome": {
                "signed_depth_delta_m": [0.0] * 6,
                "payload_gain_kg": 0.0,
                "valid": index > 0,
            },
        },
        "executed_cut": {
            "entry_x_m": 0.1,
            "entry_z_m": 0.2,
            "exit_x_m": 0.5,
            "exit_z_m": 0.2,
            "direction_x": 1.0,
            "direction_z": 0.0,
            "length_m": 0.4,
            "actual_surface_penetration_peak_m": 0.05,
            "valid": True,
        },
        "outcome": {
            "signed_depth_delta_m": [0.01 * int(moved)] * 6,
            "payload_gain_kg": 10.0 * int(moved),
        },
        "capability_labels": {"effective_move": moved},
    }


def test_cli_trains_from_deterministic_episode_grouped_fold(tmp_path: Path) -> None:
    records_path = tmp_path / "records.jsonl"
    records_path.write_text(
        "".join(json.dumps(_record(index)) + "\n" for index in range(6)),
        encoding="utf-8",
    )
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"seeds": [7], "epochs": 1, "batch_size": 2}),
        encoding="utf-8",
    )
    summary_path = tmp_path / "summary.json"

    exit_code = main(
        [
            "--records-jsonl",
            str(records_path),
            "--output-dir",
            str(tmp_path / "model"),
            "--input-contract",
            "executed_cut",
            "--fold-count",
            "6",
            "--eval-fold",
            "0",
            "--config-json",
            str(config_path),
            "--summary-json",
            str(summary_path),
        ]
    )

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert summary["schema"] == "terrain_effect_ensemble_artifact_v1"
    assert summary["episode_group_split"]["status"] == "disjoint"
    assert summary["episode_group_split"]["provenance"]["fold_count"] == 6
    assert summary["member_count"] == 1
