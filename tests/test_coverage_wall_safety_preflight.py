from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np
import pytest

from testbed.data.schema import (
    ENV_STATE_DIG_AREA_CELL_LONG_SIZE_IDX,
    ENV_STATE_DIG_AREA_CELL_SHORT_SIZE_IDX,
    ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX,
    ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX,
    ENV_STATE_DIG_AREA_LONG_AXIS_IDX,
    ENV_STATE_V2_4_DIM,
)
from testbed.eval.coverage_wall_safety_preflight import (
    CoverageWallSafetyPreflightError,
    build_coverage_wall_safety_preflight,
)

ROOT = Path(__file__).parents[1]
CONFIG = (
    ROOT
    / "testbed/configs/"
    "eval_yulong_strict18_four_camera_4p_functional_10cycle_a0.yaml"
)
UNITY_SCENE = Path(
    "/home/pingfan/AGXUnityE85ExcavatorSim/Assets/"
    "AGXUnity_Excavator/AGXUnity_Excavator.unity"
)


def _write_env_hdf5(path: Path, *, cell_scale: float = 1.0) -> None:
    env_state = np.zeros((3, ENV_STATE_V2_4_DIM), dtype=np.float32)
    env_state[:, ENV_STATE_DIG_AREA_LONG_AXIS_IDX] = 2.0
    env_state[:, ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX] = 3.0
    env_state[:, ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX] = 2.0
    env_state[:, ENV_STATE_DIG_AREA_CELL_LONG_SIZE_IDX] = 1.0 * cell_scale
    env_state[:, ENV_STATE_DIG_AREA_CELL_SHORT_SIZE_IDX] = 1.25 * cell_scale
    with h5py.File(path, "w") as handle:
        handle.create_dataset("observations/env_state", data=env_state)


def test_preflight_locks_hashes_and_expected_six_corridor_classes(
    tmp_path: Path,
) -> None:
    env_hdf5 = tmp_path / "geometry.hdf5"
    output_dir = tmp_path / "coverage_wall_safety_preflight_v1"
    _write_env_hdf5(env_hdf5)

    artifact = build_coverage_wall_safety_preflight(
        config_path=CONFIG,
        env_state_hdf5_path=env_hdf5,
        unity_scene_path=UNITY_SCENE,
        output_dir=output_dir,
    )

    assert artifact["schema"] == "coverage_wall_safety_preflight_v1"
    assert artifact["status"] == "passed"
    assert artifact["config"]["sha256"]
    assert artifact["prior"]["sha256"]
    assert artifact["unity_scene"]["sha256"] == (
        "97b01deb2229b087f110defef2c117f19c4ad8e16b1ad51d154fe5cc6514b7c9"
    )
    assert artifact["geometry"]["long_axis"] == 2
    by_cell = {
        int(item["cell_id"]): item
        for item in artifact["candidate_classifications"]
    }
    assert [by_cell[cell]["wall_safety_class"] for cell in (0, 1)] == [
        "hard_reject",
        "hard_reject",
    ]
    assert all(
        by_cell[cell]["wall_safety_class"] == "near_wall"
        for cell in (2, 3, 4, 5)
    )
    assert by_cell[2]["wall_safety_eligible"] == 1
    assert (output_dir / "coverage_wall_safety_preflight_v1.json").is_file()
    persisted = json.loads(
        (output_dir / "coverage_wall_safety_preflight_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert persisted == artifact


def test_preflight_is_no_overwrite(tmp_path: Path) -> None:
    env_hdf5 = tmp_path / "geometry.hdf5"
    output_dir = tmp_path / "coverage_wall_safety_preflight_v1"
    _write_env_hdf5(env_hdf5)
    build_coverage_wall_safety_preflight(
        config_path=CONFIG,
        env_state_hdf5_path=env_hdf5,
        unity_scene_path=UNITY_SCENE,
        output_dir=output_dir,
    )

    with pytest.raises(FileExistsError):
        build_coverage_wall_safety_preflight(
            config_path=CONFIG,
            env_state_hdf5_path=env_hdf5,
            unity_scene_path=UNITY_SCENE,
            output_dir=output_dir,
        )


def test_preflight_mismatch_does_not_create_output(tmp_path: Path) -> None:
    env_hdf5 = tmp_path / "bad_geometry.hdf5"
    output_dir = tmp_path / "coverage_wall_safety_preflight_v1"
    _write_env_hdf5(env_hdf5, cell_scale=0.40)

    with pytest.raises(
        CoverageWallSafetyPreflightError,
        match="candidate_classification_mismatch",
    ):
        build_coverage_wall_safety_preflight(
            config_path=CONFIG,
            env_state_hdf5_path=env_hdf5,
            unity_scene_path=UNITY_SCENE,
            output_dir=output_dir,
        )

    assert not output_dir.exists()
