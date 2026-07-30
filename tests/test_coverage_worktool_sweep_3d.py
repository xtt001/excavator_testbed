from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from testbed.planner.primitive.coverage.worktool_sweep import (
    COVERAGE_WORKTOOL_SWEEP_LIBRARY_SCHEMA,
    UNITY_KINEMATIC_CONVEX_COVER_WORKTOOL_SWEEP_PROFILE,
    CoverageWorktoolSweepConfig,
    CoverageWorktoolSweepContractError,
    CoverageWorktoolSweepService,
)


def _write_artifact(
    path: Path,
    *,
    sampled_clearance_m: float = 0.55,
    geometry_valid: bool = True,
) -> str:
    artifact = {
        "schema": COVERAGE_WORKTOOL_SWEEP_LIBRARY_SCHEMA,
        "status": "completed",
        "profile": UNITY_KINEMATIC_CONVEX_COVER_WORKTOOL_SWEEP_PROFILE,
        "sample_count": 1,
        "source_lock": {
            "execution_library_sha256": "a" * 64,
            "pose_library_sha256": "b" * 64,
            "scene_sha256": "c" * 64,
            "prefab_sha256": "d" * 64,
            "mesh_sha256": {
                "boom": "e" * 64,
                "stick": "f" * 64,
                "bucket": "1" * 64,
            },
            "normalization_sha256": "2" * 64,
            "predictor_code_sha256": "3" * 64,
        },
        "qpos_contract": {
            "order": [
                "swing_position_norm",
                "boom_position_norm",
                "stick_position_norm",
                "bucket_position_norm",
            ],
            "normalized_min": [0.0, 0.0, 0.0, 0.0],
            "normalized_max": [1.0, 1.0, 1.0, 1.0],
            "raw_range_rad": [
                6.283185482025147,
                0.9955732524394989,
                1.8719636797904968,
                2.483125865459442,
            ],
        },
        "records": [
            {
                "exemplar_id": "episode_168",
                "primitive_episode_id": 168,
                "source_episode_id": 24,
                "raw_fields_sha256": "4" * 64,
                "pose_path_sha256": "5" * 64,
                "exemplar_start_qpos": [0.5, 0.4, 0.3, 0.2],
                "geometry_valid": geometry_valid,
                "rejection_reason": (
                    "" if geometry_valid else "unsupported_shape"
                ),
                "link_sweeps": [
                    {
                        "link_name": "boom",
                        "sampled_convex_cover_clearance_m": 0.90,
                        "joint_motion_radius_m": [4.0, 3.0, 0.0, 0.0],
                        "closest": {
                            "shape_name": "dabi.STL",
                            "wall_name": "Dig_XMax_Board",
                            "pose_index": 5,
                            "qpos": [0.5, 0.4, 0.3, 0.2],
                            "worktool_point_world_m": [0.0, 0.0, 0.0],
                            "wall_point_world_m": [0.9, 0.0, 0.0],
                        },
                    },
                    {
                        "link_name": "bucket",
                        "sampled_convex_cover_clearance_m": (
                            sampled_clearance_m
                        ),
                        "joint_motion_radius_m": [4.0, 3.0, 2.0, 1.0],
                        "closest": {
                            "shape_name": "watou.STL",
                            "wall_name": "Dig_ZMin_Board",
                            "pose_index": 33,
                            "qpos": [0.5, 0.4, 0.3, 0.2],
                            "worktool_point_world_m": [1.0, 2.0, 3.0],
                            "wall_point_world_m": [1.0, 2.0, 3.55],
                        },
                    },
                    {
                        "link_name": "stick",
                        "sampled_convex_cover_clearance_m": 0.80,
                        "joint_motion_radius_m": [4.0, 3.0, 2.0, 0.0],
                        "closest": {
                            "shape_name": "xiaobi.STL",
                            "wall_name": "Dig_XMin_Board",
                            "pose_index": 10,
                            "qpos": [0.5, 0.4, 0.3, 0.2],
                            "worktool_point_world_m": [0.0, 0.0, 0.0],
                            "wall_point_world_m": [0.8, 0.0, 0.0],
                        },
                    },
                ],
            }
        ],
    }
    for link in artifact["records"][0]["link_sweeps"]:
        closest_wall = link["closest"]["wall_name"]
        link["wall_sweeps"] = [
            {
                "wall_name": wall_name,
                "sampled_convex_cover_clearance_m": (
                    link["sampled_convex_cover_clearance_m"]
                    if wall_name == closest_wall
                    else link["sampled_convex_cover_clearance_m"] + 0.10
                ),
                "closest": {
                    **link["closest"],
                    "link_name": link["link_name"],
                    "wall_name": wall_name,
                },
            }
            for wall_name in (
                "Dig_XMin_Board",
                "Dig_XMax_Board",
                "Dig_ZMin_Board",
                "Dig_ZMax_Board",
            )
        ]
    path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _service(path: Path, sha256: str) -> CoverageWorktoolSweepService:
    return CoverageWorktoolSweepService.from_config(
        CoverageWorktoolSweepConfig.from_mapping(
            {
                "enabled": True,
                "profile": (
                    UNITY_KINEMATIC_CONVEX_COVER_WORKTOOL_SWEEP_PROFILE
                ),
                "hard_clearance_m": 0.30,
                "act_tracking_margin_m": 0.15,
                "pose_interpolation_bound_m": 0.01,
                "artifact_path": str(path),
                "artifact_sha256": sha256,
                "execution_library_sha256": "a" * 64,
                "pose_library_sha256": "b" * 64,
                "missing_contract": "fail_closed",
            }
        )
    )


def test_worktool_sweep_accepts_only_effective_clearance_at_least_030(
    tmp_path: Path,
) -> None:
    path = tmp_path / "sweep.json"
    sha256 = _write_artifact(path)
    service = _service(path, sha256)

    accepted = service.evaluate(
        exemplar_id="episode_168",
        raw_fields_sha256="4" * 64,
        live_start_qpos=[0.5, 0.4, 0.3, 0.2],
    )
    rejected = service.evaluate(
        exemplar_id="episode_168",
        raw_fields_sha256="4" * 64,
        live_start_qpos=[0.505, 0.4, 0.3, 0.2],
    )

    assert accepted.eligible is True
    assert accepted.sampled_convex_cover_clearance_m == pytest.approx(0.55)
    assert accepted.pose_interpolation_margin_m == pytest.approx(0.01)
    assert accepted.act_tracking_margin_m == pytest.approx(0.15)
    assert accepted.live_start_displacement_bound_m == pytest.approx(0.0)
    assert accepted.effective_clearance_m == pytest.approx(0.39)
    assert accepted.closest_link_name == "bucket"
    assert accepted.closest_wall_name == "Dig_ZMin_Board"

    assert rejected.eligible is False
    assert rejected.effective_clearance_m < 0.30
    assert rejected.rejection_reason == (
        "worktool_3d_clearance_below_minimum"
    )
    assert rejected.live_start_displacement_bound_m > 0.09


def test_worktool_sweep_accepts_runtime_numpy_qpos(
    tmp_path: Path,
) -> None:
    path = tmp_path / "sweep.json"
    service = _service(path, _write_artifact(path))

    result = service.evaluate(
        exemplar_id="episode_168",
        raw_fields_sha256="4" * 64,
        live_start_qpos=np.asarray(
            [0.5, 0.4, 0.3, 0.2],
            dtype=np.float32,
        ),
    )

    assert result.eligible is True


def test_worktool_sweep_fails_closed_on_geometry_or_sha_drift(
    tmp_path: Path,
) -> None:
    missing_geometry_path = tmp_path / "missing.json"
    missing_sha = _write_artifact(
        missing_geometry_path,
        geometry_valid=False,
    )
    result = _service(missing_geometry_path, missing_sha).evaluate(
        exemplar_id="episode_168",
        raw_fields_sha256="4" * 64,
        live_start_qpos=[0.5, 0.4, 0.3, 0.2],
    )
    assert result.eligible is False
    assert result.rejection_reason == "worktool_3d_geometry_missing"

    valid_path = tmp_path / "valid.json"
    valid_sha = _write_artifact(valid_path)
    service = _service(valid_path, valid_sha)
    mismatch = service.evaluate(
        exemplar_id="episode_168",
        raw_fields_sha256="9" * 64,
        live_start_qpos=[0.5, 0.4, 0.3, 0.2],
    )
    assert mismatch.eligible is False
    assert mismatch.rejection_reason == "worktool_3d_geometry_missing"

    with pytest.raises(
        CoverageWorktoolSweepContractError,
        match="artifact_sha256_mismatch",
    ):
        _service(valid_path, "0" * 64)


def test_worktool_sweep_requires_all_four_pair_witnesses(
    tmp_path: Path,
) -> None:
    path = tmp_path / "missing_pair.json"
    _write_artifact(path)
    artifact = json.loads(path.read_text(encoding="utf-8"))
    artifact["records"][0]["link_sweeps"][1]["wall_sweeps"].pop()
    path.write_text(json.dumps(artifact), encoding="utf-8")

    with pytest.raises(
        CoverageWorktoolSweepContractError,
        match="wall_sweeps",
    ):
        _service(path, hashlib.sha256(path.read_bytes()).hexdigest())


@pytest.mark.parametrize(
    "qpos",
    (
        [0.5, 0.4, 0.3],
        [0.5, 0.4, 0.3, float("nan")],
        [0.5, 0.4, 0.3, 1.01],
    ),
)
def test_worktool_sweep_rejects_missing_or_uncalibrated_live_qpos(
    tmp_path: Path,
    qpos: list[float],
) -> None:
    path = tmp_path / "sweep.json"
    service = _service(path, _write_artifact(path))

    result = service.evaluate(
        exemplar_id="episode_168",
        raw_fields_sha256="4" * 64,
        live_start_qpos=qpos,
    )

    assert result.eligible is False
    assert result.rejection_reason == "worktool_3d_geometry_missing"


def test_worktool_sweep_config_is_fail_closed_and_exact() -> None:
    disabled = CoverageWorktoolSweepConfig.from_mapping(None)
    assert disabled.enabled is False
    assert disabled.act_tracking_margin_m == pytest.approx(0.05)
    assert disabled.hard_clearance_m == pytest.approx(0.24)
    assert disabled.pose_interpolation_bound_m == pytest.approx(0.01)

    with pytest.raises(ValueError, match="requires artifact_path"):
        CoverageWorktoolSweepConfig.from_mapping({"enabled": True})
    with pytest.raises(ValueError, match="profile must be"):
        CoverageWorktoolSweepConfig.from_mapping(
            {
                "enabled": True,
                "profile": "approximate_aabb",
                "artifact_path": "/tmp/sweep.json",
                "artifact_sha256": "a" * 64,
                "execution_library_sha256": "b" * 64,
                "pose_library_sha256": "c" * 64,
            }
        )
    with pytest.raises(ValueError, match="missing_contract"):
        CoverageWorktoolSweepConfig.from_mapping(
            {
                "enabled": True,
                "artifact_path": "/tmp/sweep.json",
                "artifact_sha256": "a" * 64,
                "execution_library_sha256": "b" * 64,
                "pose_library_sha256": "c" * 64,
                "missing_contract": "fallback_2d",
            }
        )
