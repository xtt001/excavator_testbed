from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np
import pytest

from testbed.data.schema import (
    ENV_STATE_DIG_AREA_CELL_LONG_SIZE_IDX,
    ENV_STATE_DIG_AREA_CELL_SHORT_SIZE_IDX,
    ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
    ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX,
    ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX,
    ENV_STATE_DIG_AREA_LONG_AXIS_IDX,
    ENV_STATE_DIG_AREA_TARGET_DEPTH_START_IDX,
    ENV_STATE_V2_4_DIM,
)
from testbed.eval.coverage_replan_replay import (
    OUTPUT_FILENAME,
    build_coverage_replan_replay,
)

ROOT = Path(__file__).parents[1]
A0_CONFIG = (
    ROOT
    / "testbed/configs/"
    "eval_yulong_strict18_four_camera_4p_functional_10cycle_a0.yaml"
)


def _write_hdf5(path: Path) -> None:
    env = np.zeros((1, ENV_STATE_V2_4_DIM), dtype=np.float32)
    env[0, ENV_STATE_DIG_AREA_LONG_AXIS_IDX] = 2
    env[0, ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX] = 3
    env[0, ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX] = 2
    env[0, ENV_STATE_DIG_AREA_CELL_LONG_SIZE_IDX] = 1.0
    env[0, ENV_STATE_DIG_AREA_CELL_SHORT_SIZE_IDX] = 1.25
    env[0, ENV_STATE_DIG_AREA_TARGET_DEPTH_START_IDX : ENV_STATE_DIG_AREA_TARGET_DEPTH_START_IDX + 6] = 0.08
    env[0, ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX : ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX + 6] = 1.0
    env[0, 28:31] = (0.4, 0.0, 0.6)
    with h5py.File(path, "w") as handle:
        handle.create_dataset("timestamps/step_id", data=[2987])
        handle.create_dataset("observations/qpos", data=np.zeros((1, 4), np.float32))
        handle.create_dataset("observations/qvel", data=np.zeros((1, 4), np.float32))
        handle.create_dataset("observations/env_state", data=env)


def _write_jsonl(path: Path) -> None:
    candidate_scores = []
    for corridor_id in range(6):
        candidate_scores.append(
            {
                "corridor_id": corridor_id,
                "attempts": 2 if corridor_id == 4 else int(corridor_id in {2, 3, 5}),
                "depleted": int(corridor_id in {2, 3, 5}),
                "belief_coverage": 0.0,
                "low_productivity_streak": 0,
                "remaining_depth_m": 0.08,
                "rejection_reason": (
                    "corridor_depleted"
                    if corridor_id in {2, 3, 5}
                    else ""
                ),
            }
        )
    row = {
        "step_id": 2935,
        "primitive_cycle_index": 5,
        "coverage_completed_dump_count": 5,
        "coverage_corridor_id": 4,
        "coverage_candidate_scores": candidate_scores,
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")


def test_production_replan_separates_bookkeeping_fix_from_physical_filter(
    tmp_path: Path,
) -> None:
    hdf5_path = tmp_path / "episode_0.hdf5"
    jsonl_path = tmp_path / "rollout_000.jsonl"
    _write_hdf5(hdf5_path)
    _write_jsonl(jsonl_path)

    artifact = build_coverage_replan_replay(
        rollout_hdf5_path=hdf5_path,
        rollout_jsonl_path=jsonl_path,
        resolved_config_path=A0_CONFIG,
        output_dir=tmp_path / "diagnosis",
        pre_contact_step_id=2935,
        replan_step_id=2987,
        depth_exhausted_physical_cell_id=5,
    )

    ownership = artifact["contact_ownership_only_counterfactual"]
    corrected = artifact["corrected_production_replan"]
    assert ownership["corridor_4_pre_selection_depleted"] is False
    assert ownership["selected_corridor_id"] == 4
    assert corrected["status"] == "no_wall_safe_corridor"
    by_id = {
        int(item["corridor_id"]): item
        for item in corrected["candidate_scores"]
    }
    assert by_id[4]["rejection_reason"] == (
        "swept_footprint_intersects_depth_exhausted_cell"
    )
    assert by_id[4]["depth_exhausted_swept_cell_ids"] == [5]
    assert artifact["root_cause_flags"][
        "data_scene_cell_semantic_mismatch"
    ] is True
    assert artifact["live_1x10_allowed"] is False
    assert (tmp_path / "diagnosis" / OUTPUT_FILENAME).is_file()


def test_replan_artifact_is_no_overwrite(tmp_path: Path) -> None:
    hdf5_path = tmp_path / "episode_0.hdf5"
    jsonl_path = tmp_path / "rollout_000.jsonl"
    output_dir = tmp_path / "diagnosis"
    _write_hdf5(hdf5_path)
    _write_jsonl(jsonl_path)
    kwargs = {
        "rollout_hdf5_path": hdf5_path,
        "rollout_jsonl_path": jsonl_path,
        "resolved_config_path": A0_CONFIG,
        "output_dir": output_dir,
        "pre_contact_step_id": 2935,
        "replan_step_id": 2987,
        "depth_exhausted_physical_cell_id": 5,
    }
    build_coverage_replan_replay(**kwargs)

    with pytest.raises(FileExistsError):
        build_coverage_replan_replay(**kwargs)
