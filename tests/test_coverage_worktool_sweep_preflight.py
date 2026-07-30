from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from testbed.eval.coverage_worktool_sweep_validation import (
    OUTPUT_FILENAME,
    build_coverage_worktool_sweep_preflight,
)

_RAW_FIELDS_SHA256 = (
    "c167e087f3d41f6db8fe0ad260d5f72c3440b6fab9115fdf55959feacc50991c"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_sources(tmp_path: Path) -> tuple[Path, str, Path, str]:
    execution = tmp_path / "execution.json"
    pose = tmp_path / "pose.json"
    execution.write_text('{"source":"execution"}\n', encoding="utf-8")
    pose.write_text('{"source":"pose"}\n', encoding="utf-8")
    return execution, _sha(execution), pose, _sha(pose)


def _write_sweep(
    path: Path,
    *,
    execution_sha: str,
    pose_sha: str,
) -> str:
    link_sweeps = []
    for link, sampled, wall in (
        ("boom", 0.50, "Dig_XMin_Board"),
        ("stick", 0.45, "Dig_ZMin_Board"),
        ("bucket", 0.28, "Dig_XMax_Board"),
    ):
        closest = {
            "link_name": link,
            "shape_name": f"{link}_Mesh",
            "wall_name": wall,
            "pose_index": 2,
            "qpos": [0.5, 0.4, 0.3, 0.2],
            "worktool_point_world_m": [0.0, 0.0, 0.0],
            "wall_point_world_m": [sampled, 0.0, 0.0],
        }
        wall_sweeps = [
            {
                "wall_name": name,
                "sampled_convex_cover_clearance_m": (
                    0.31
                    if link == "bucket" and name == "Dig_ZMin_Board"
                    else sampled + 0.2
                ),
                "closest": {
                    **closest,
                    "wall_name": name,
                },
            }
            for name in (
                "Dig_XMin_Board",
                "Dig_XMax_Board",
                "Dig_ZMin_Board",
                "Dig_ZMax_Board",
            )
        ]
        link_sweeps.append(
            {
                "link_name": link,
                "sampled_convex_cover_clearance_m": sampled,
                "joint_motion_radius_m": [1.0, 1.0, 1.0, 1.0],
                "closest": closest,
                "wall_sweeps": wall_sweeps,
            }
        )
    artifact = {
        "schema": "coverage_worktool_sweep_library_v1",
        "status": "completed",
        "profile": "unity_kinematic_convex_cover_worktool_sweep_v1",
        "sample_count": 1,
        "source_lock": {
            "execution_library_sha256": execution_sha,
            "pose_library_sha256": pose_sha,
            "scene_sha256": "a" * 64,
            "prefab_sha256": "b" * 64,
            "mesh_sha256": {
                "boom": "c" * 64,
                "stick": "d" * 64,
                "bucket": "e" * 64,
            },
            "normalization_sha256": "f" * 64,
            "predictor_code_sha256": "1" * 64,
        },
        "qpos_contract": {
            "order": [
                "swing_position_norm",
                "boom_position_norm",
                "stick_position_norm",
                "bucket_position_norm",
            ],
            "normalized_min": [0.0] * 4,
            "normalized_max": [1.0] * 4,
            "raw_range_rad": [1.0] * 4,
        },
        "records": [
            {
                "exemplar_id": "episode_168",
                "primitive_episode_id": 168,
                "source_episode_id": 24,
                "raw_fields_sha256": _RAW_FIELDS_SHA256,
                "pose_path_sha256": "5" * 64,
                "exemplar_start_qpos": [0.5, 0.4, 0.3, 0.2],
                "geometry_valid": True,
                "rejection_reason": "",
                "link_sweeps": link_sweeps,
            }
        ],
    }
    path.write_text(json.dumps(artifact), encoding="utf-8")
    return _sha(path)


def _write_frozen_rollouts(directory: Path) -> None:
    directory.mkdir()
    for index, qpos in enumerate(
        (
            [0.50, 0.40, 0.30, 0.20],
            [0.51, 0.40, 0.30, 0.20],
            [0.49, 0.40, 0.30, 0.20],
        )
    ):
        stem = f"rollout_{index:03d}"
        (directory / f"{stem}.jsonl").write_text(
            json.dumps(
                {
                    "step_id": 600 + index,
                    "primitive_cycle_index": 1,
                    "skill_name": "dig",
                    "coverage_corridor_id": 1_000_168,
                    "qpos": qpos,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (directory / f"{stem}_planner_trace.json").write_text(
            json.dumps(
                {
                    "coverage_decision_trace": [
                        {
                            "event": (
                                "select_actual_tuple_execution_candidate"
                            ),
                            "cycle_index": 1,
                            "exemplar_id": "episode_168",
                            "raw_fields_sha256": _RAW_FIELDS_SHA256,
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )


def test_episode168_three_start_preflight_rejects_before_act(
    tmp_path: Path,
) -> None:
    execution, execution_sha, pose, pose_sha = _write_sources(tmp_path)
    sweep = tmp_path / "sweep.json"
    sweep_sha = _write_sweep(
        sweep,
        execution_sha=execution_sha,
        pose_sha=pose_sha,
    )
    rollouts = tmp_path / "rollouts"
    _write_frozen_rollouts(rollouts)

    artifact = build_coverage_worktool_sweep_preflight(
        sweep_artifact_path=sweep,
        sweep_artifact_sha256=sweep_sha,
        execution_library_path=execution,
        execution_library_sha256=execution_sha,
        pose_library_path=pose,
        pose_library_sha256=pose_sha,
        frozen_rollout_dir=rollouts,
        output_dir=tmp_path / "preflight",
    )

    assert artifact["status"] == "passed"
    assert artifact["episode_168_rejected_count"] == 3
    assert all(
        not result["act_inference_allowed"]
        for result in artifact["evaluations"]
    )
    assert artifact["bucket_zmin_pair_witness"][
        "wall_name"
    ] == "Dig_ZMin_Board"
    assert (
        tmp_path / "preflight" / OUTPUT_FILENAME
    ).is_file()


def test_worktool_sweep_preflight_is_no_overwrite(
    tmp_path: Path,
) -> None:
    execution, execution_sha, pose, pose_sha = _write_sources(tmp_path)
    sweep = tmp_path / "sweep.json"
    sweep_sha = _write_sweep(
        sweep,
        execution_sha=execution_sha,
        pose_sha=pose_sha,
    )
    rollouts = tmp_path / "rollouts"
    _write_frozen_rollouts(rollouts)
    kwargs = {
        "sweep_artifact_path": sweep,
        "sweep_artifact_sha256": sweep_sha,
        "execution_library_path": execution,
        "execution_library_sha256": execution_sha,
        "pose_library_path": pose,
        "pose_library_sha256": pose_sha,
        "frozen_rollout_dir": rollouts,
        "output_dir": tmp_path / "preflight",
    }
    build_coverage_worktool_sweep_preflight(**kwargs)

    with pytest.raises(FileExistsError):
        build_coverage_worktool_sweep_preflight(**kwargs)
