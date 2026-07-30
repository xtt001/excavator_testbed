from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
import pytest
import yaml

from testbed.data.schema import (
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX,
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_STEP_MAX_FORCE_IDX,
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_DIG_AREA_CELL_LONG_SIZE_IDX,
    ENV_STATE_DIG_AREA_CELL_SHORT_SIZE_IDX,
    ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX,
    ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX,
    ENV_STATE_DIG_AREA_HARD_BOTTOM_DEPTH_IDX,
    ENV_STATE_DIG_AREA_LONG_AXIS_IDX,
    ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX,
    ENV_STATE_V2_4_DIM,
)
from testbed.eval.hard_bottom_execution_diagnostic import (
    DIAGNOSIS_FILENAME,
    DIAGNOSTIC_SCHEMA,
    SOURCE_MANIFEST_FILENAME,
    SOURCE_MANIFEST_SCHEMA,
    analyze_hard_bottom_execution,
    build_hard_bottom_execution_diagnostic,
    classify_hard_bottom_source,
    physical_cell_id,
    swept_cell_ids,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _env(
    *,
    long_axis: int = 2,
    tip_x: float = 0.6,
    tip_y: float = -0.2,
    tip_z: float = 0.6,
    local_penetration: float = 0.1,
    plane_depth: float = 0.15,
    bottom_mask: float = 0.0,
    bottom_force: float = 0.0,
    bottom_sessions: float = 0.0,
) -> np.ndarray:
    env = np.zeros(ENV_STATE_V2_4_DIM, dtype=np.float32)
    env[ENV_STATE_DIG_AREA_LONG_AXIS_IDX] = float(long_axis)
    env[ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX] = 3.0
    env[ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX] = 2.0
    env[ENV_STATE_DIG_AREA_CELL_LONG_SIZE_IDX] = 1.0
    env[ENV_STATE_DIG_AREA_CELL_SHORT_SIZE_IDX] = 1.25
    env[ENV_STATE_DIG_AREA_HARD_BOTTOM_DEPTH_IDX] = 0.60
    env[
        ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX:
        ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX + 6
    ] = np.asarray([0.01, 0.02, 0.03, 0.04, 0.05, 0.05], np.float32)
    env[
        ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX:
        ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX + 3
    ] = np.asarray([tip_x, tip_y, tip_z], np.float32)
    env[ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX] = local_penetration
    env[ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX] = plane_depth
    env[ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX] = bottom_mask
    env[ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_STEP_MAX_FORCE_IDX] = bottom_force
    env[ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX] = bottom_sessions
    return env


def _write_rollout(root: Path) -> tuple[Path, Path]:
    hdf5_path = root / "episode_0.hdf5"
    env_rows = np.stack(
        [
            _env(tip_x=0.62, tip_z=0.58, local_penetration=0.10, plane_depth=0.15),
            _env(tip_x=0.52, tip_z=0.68, local_penetration=0.30, plane_depth=0.35),
            _env(
                tip_x=0.37,
                tip_y=-0.59,
                tip_z=0.76,
                local_penetration=0.50,
                plane_depth=0.59,
                bottom_mask=1.0,
                bottom_force=1234.0,
                bottom_sessions=1.0,
            ),
            _env(
                tip_x=0.35,
                tip_y=-0.60,
                tip_z=0.78,
                local_penetration=0.51,
                plane_depth=0.60,
                bottom_mask=1.0,
                bottom_force=500.0,
                bottom_sessions=1.0,
            ),
            # This deliberately deeper scripted-clearance row must be excluded.
            _env(
                tip_x=0.10,
                tip_y=-0.90,
                tip_z=0.10,
                local_penetration=0.90,
                plane_depth=0.90,
                bottom_mask=0.0,
                bottom_sessions=1.0,
            ),
        ]
    )
    actions = np.asarray(
        [
            [0.0, 0.0, 0.0, 0.0],
            [0.1, -0.2, 0.3, 0.4],
            [0.2, -0.3, 0.4, 0.5],
            [0.0, 0.0, 0.0, 0.0],
            [0.0, 0.35, 0.35, 0.55],
        ],
        dtype=np.float32,
    )
    with h5py.File(hdf5_path, "w") as handle:
        handle.create_dataset(
            "timestamps/step_id",
            data=np.arange(10, 15, dtype=np.int64),
        )
        handle.create_dataset(
            "observations/env_state",
            data=env_rows,
        )
        handle.create_dataset(
            "observations/qpos",
            data=np.arange(20, dtype=np.float32).reshape(5, 4),
        )
        handle.create_dataset(
            "observations/qvel",
            data=np.arange(20, 40, dtype=np.float32).reshape(5, 4),
        )
        handle.create_dataset("action", data=actions)

    token = [0.0] * 10
    token[7] = 0.375  # 0.30m under the central 0.80m token scale.
    plan = {
        "planned_cut_cell_id": 4,
        "coverage_corridor_id": 4,
        "coverage_entry_x_m": 0.60,
        "coverage_entry_z_m": 0.60,
        "coverage_exit_x_m": 0.40,
        "coverage_exit_z_m": 0.80,
        "dig_cut_tokens": token,
    }
    rows = [
        {
            "step_id": 10,
            "primitive_cycle_index": 4,
            "skill_name": "return",
            "action": actions[0].tolist(),
            "dig_cut_tokens": [0.0] * 10,
        },
        {
            **plan,
            "step_id": 11,
            "primitive_cycle_index": 5,
            "skill_name": "dig",
            "action": actions[1].tolist(),
            "box_safety_hard_bottom_contact": False,
        },
        {
            **plan,
            "step_id": 12,
            "primitive_cycle_index": 5,
            "skill_name": "dig",
            "action": actions[2].tolist(),
            "box_safety_hard_bottom_contact": False,
        },
        {
            **plan,
            "step_id": 13,
            "primitive_cycle_index": 5,
            "skill_name": "dig",
            "action": actions[3].tolist(),
            "box_safety_hard_bottom_contact": True,
            "box_safety_reason": "hard_bottom_contact",
        },
        {
            **plan,
            "step_id": 14,
            "primitive_cycle_index": 5,
            "skill_name": "dig",
            "action": actions[4].tolist(),
            "box_safety_clearance_active": True,
            "box_safety_reason": "hard_bottom_scripted_clearance",
        },
    ]
    jsonl_path = root / "rollout_000.jsonl"
    jsonl_path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    return hdf5_path, jsonl_path


def test_diagnostic_aligns_pre_action_to_first_bottom_rising_edge(
    tmp_path: Path,
) -> None:
    hdf5_path, jsonl_path = _write_rollout(tmp_path)

    result = analyze_hard_bottom_execution(
        rollout_hdf5_path=hdf5_path,
        rollout_jsonl_path=jsonl_path,
        cycle_index=5,
        hard_bottom_margin_m=0.02,
        worktool_width_m=0.70,
    )

    assert result["evidence_scope"] == "frozen_recorded_closed_loop"
    window = result["cut_window"]
    assert window["first_action_step_id"] == 11
    assert window["first_pre_action_observation_step_id"] == 10
    assert window["contact_observation_step_id"] == 12
    assert window["safety_trigger_action_step_id"] == 13
    assert window["last_cut_action_step_id"] == 12
    assert window["trajectory_observation_step_ids"] == [10, 11, 12]
    assert window["clearance_rows_excluded"] == 1
    assert result["execution"]["actual_peak_penetration_m"] == pytest.approx(0.50)
    assert result["execution"]["contact_endpoint_xyz_m"] == pytest.approx(
        [0.37, -0.59, 0.76]
    )
    assert result["execution"]["contact_force_n"] == pytest.approx(1234.0)
    assert result["execution"]["contact_session_count"] == 1
    assert result["execution"]["contact_bucket_tip_clearance_m"] == pytest.approx(
        0.01,
        abs=1.0e-6,
    )
    assert result["execution"]["contact_local_remaining_depth_m"] == (
        pytest.approx(0.55)
    )
    assert result["execution"][
        "contact_planned_clearance_from_local_surface_m"
    ] == pytest.approx(0.25)
    assert result["classification"]["primary_cause"] == (
        "act_execution_capability_primary"
    )
    assert result["classification"]["additional_findings"] == [
        "data_scene_cell_semantic_mismatch"
    ]
    assert result["plan"]["logical_cell_id"] == 4
    assert result["plan"]["centerline_physical_cell_ids"] == [5]
    assert 5 in result["plan"]["swept_physical_cell_ids"]
    assert 4 not in result["plan"]["swept_physical_cell_ids"]
    assert result["plan"][
        "planned_centerline_minimum_hard_bottom_clearance_m"
    ] == pytest.approx(0.25)
    assert result["plan"]["local_remaining_depth_by_cell_m"]["5"] == (
        pytest.approx(0.55)
    )
    assert result["trajectory"][-1]["env_state_local_penetration_m"] == (
        pytest.approx(0.50)
    )
    assert result["trajectory"][-1]["qpos"] == [8.0, 9.0, 10.0, 11.0]


def test_physical_cell_and_swept_cell_mapping_cover_both_long_axes() -> None:
    axis_x = _env(long_axis=0)
    assert physical_cell_id(axis_x, x_m=-1.2, z_m=-0.8) == 0
    assert physical_cell_id(axis_x, x_m=0.2, z_m=0.8) == 3
    assert swept_cell_ids(
        axis_x,
        entry_x_m=-1.2,
        entry_z_m=-0.8,
        exit_x_m=1.2,
        exit_z_m=-0.8,
        worktool_width_m=0.20,
    ) == (0, 2, 4)

    axis_z = _env(long_axis=2)
    assert physical_cell_id(axis_z, x_m=-0.8, z_m=-1.2) == 0
    assert physical_cell_id(axis_z, x_m=0.8, z_m=0.2) == 3
    assert swept_cell_ids(
        axis_z,
        entry_x_m=-0.8,
        entry_z_m=-1.2,
        exit_x_m=-0.8,
        exit_z_m=1.2,
        worktool_width_m=0.20,
    ) == (0, 2, 4)


@pytest.mark.parametrize(
    ("planned_clearance", "overshoot", "tip_clearance", "primary"),
    [
        (0.019, 0.0, 0.019, "planner_depth_geometry_primary"),
        (0.20, 0.021, 0.019, "act_execution_capability_primary"),
        (0.20, 0.0, 0.020, "bucket_collision_envelope_incomplete_primary"),
    ],
)
def test_hard_bottom_source_classification_uses_locked_margin(
    planned_clearance: float,
    overshoot: float,
    tip_clearance: float,
    primary: str,
) -> None:
    result = classify_hard_bottom_source(
        planned_minimum_clearance_m=planned_clearance,
        planned_depth_m=0.30,
        actual_peak_penetration_m=0.30 + overshoot,
        contact_bucket_tip_clearance_m=tip_clearance,
        hard_bottom_margin_m=0.02,
        typed_bottom_contact=True,
        logical_cell_id=4,
        centerline_physical_cell_ids=(5,),
        swept_physical_cell_ids=(5,),
    )

    assert result["primary_cause"] == primary
    assert result["additional_findings"] == [
        "data_scene_cell_semantic_mismatch"
    ]


def _write_freeze_sources(tmp_path: Path) -> dict[str, Path]:
    results = tmp_path / "results"
    rollouts = results / "rollouts"
    hdf5_rollouts = results / "hdf5_rollouts"
    rollouts.mkdir(parents=True)
    hdf5_rollouts.mkdir()
    hdf5_source, jsonl_source = _write_rollout(tmp_path)
    hdf5_source.replace(hdf5_rollouts / "episode_0.hdf5")
    jsonl_source.replace(rollouts / "rollout_000.jsonl")
    for name, payload in (
        ("eval_run_metadata.json", {"status": "completed"}),
        ("metrics.json", {"success": True}),
        ("rollout_manifest.json", {"rollout_count": 1}),
    ):
        (results / name).write_text(json.dumps(payload), encoding="utf-8")
    (results / "results.csv").write_text("rollout_id\n0\n", encoding="utf-8")
    (rollouts / "rollout_000_planner_trace.json").write_text(
        json.dumps({"cycle_count": 6}),
        encoding="utf-8",
    )
    (rollouts / "rollout_000_summary.json").write_text(
        json.dumps({"stop_reason": "box_safety:no_wall_safe_corridor"}),
        encoding="utf-8",
    )
    video = tmp_path / "rollout_000.mp4"
    video.write_bytes(b"video")
    prior = tmp_path / "prior.json"
    prior.write_text(json.dumps({"prior_id": "strict18"}), encoding="utf-8")
    scene = tmp_path / "scene.unity"
    scene.write_text("scene", encoding="utf-8")
    policy: dict[str, object] = {
        "dig_cut_planner": {"prior_path": str(prior)},
    }
    for skill in ("dig", "carry", "dump", "return"):
        checkpoint_dir = tmp_path / "ckpts" / skill
        checkpoint_dir.mkdir(parents=True)
        checkpoint = checkpoint_dir / "policy_best.ckpt"
        stats = checkpoint_dir / "dataset_stats.pkl"
        checkpoint.write_bytes(f"{skill}-checkpoint".encode())
        stats.write_bytes(f"{skill}-stats".encode())
        policy[f"{skill}_ckpt_path"] = str(checkpoint)
        policy[f"{skill}_ckpt_dir"] = str(checkpoint_dir)
    config = {
        "policy": policy,
        "eval": {
            "record_hdf5_metadata": {
                "unity_scene_id": f"scene@sha256:{_sha256(scene)}",
            }
        },
    }
    (results / "eval_resolved_config.yaml").write_text(
        yaml.safe_dump(config),
        encoding="utf-8",
    )
    return {
        "results": results,
        "video": video,
        "prior": prior,
        "scene": scene,
    }


def test_builder_freezes_sources_by_sha_without_copying_and_is_no_overwrite(
    tmp_path: Path,
) -> None:
    sources = _write_freeze_sources(tmp_path)
    output_dir = tmp_path / "act_hard_bottom_cycle6_diagnosis_v1"
    output_dir.mkdir()
    marker = output_dir / "replan_replay.json"
    marker.write_text("other diagnosis\n", encoding="utf-8")

    artifact = build_hard_bottom_execution_diagnostic(
        results_dir=sources["results"],
        video_path=sources["video"],
        prior_path=sources["prior"],
        unity_scene_path=sources["scene"],
        output_dir=output_dir,
        cycle_index=5,
    )

    assert artifact["schema"] == DIAGNOSTIC_SCHEMA
    assert artifact["status"] == "completed"
    manifest_path = output_dir / SOURCE_MANIFEST_FILENAME
    diagnosis_path = output_dir / DIAGNOSIS_FILENAME
    assert manifest_path.is_file()
    assert diagnosis_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == SOURCE_MANIFEST_SCHEMA
    assert manifest["freeze_mode"] == "reference_only_sha256_no_copy"
    labels = {entry["label"] for entry in manifest["entries"]}
    assert {
        "results/eval_resolved_config.yaml",
        "results/eval_run_metadata.json",
        "results/hdf5_rollouts/episode_0.hdf5",
        "results/rollouts/rollout_000.jsonl",
        "results/rollouts/rollout_000_planner_trace.json",
        "results/rollouts/rollout_000_summary.json",
        "video/rollout_000.mp4",
        "prior",
        "unity_scene",
        "checkpoint/dig",
        "stats/dig",
        "checkpoint/carry",
        "stats/carry",
        "checkpoint/dump",
        "stats/dump",
        "checkpoint/return",
        "stats/return",
    } <= labels
    assert artifact["source_manifest"]["sha256"] == _sha256(manifest_path)
    assert marker.read_text(encoding="utf-8") == "other diagnosis\n"
    assert sorted(path.name for path in output_dir.iterdir()) == [
        DIAGNOSIS_FILENAME,
        marker.name,
        SOURCE_MANIFEST_FILENAME,
    ]

    with pytest.raises(FileExistsError, match="no-overwrite"):
        build_hard_bottom_execution_diagnostic(
            results_dir=sources["results"],
            video_path=sources["video"],
            prior_path=sources["prior"],
            unity_scene_path=sources["scene"],
            output_dir=output_dir,
            cycle_index=5,
        )
