from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
import pytest
import yaml

from testbed.eval.wall_contact_artifact_io import (
    artifact_ref,
    artifact_refs_aggregate_sha256,
    json_sha256,
)
from testbed.eval.wall_contact_config_contracts import effective_action_scale
from testbed.eval.wall_contact_evidence_contracts import (
    ContactEvidenceContractError,
    causal_classification,
    parse_worktool_wall_contact_detail,
    validate_reset_pair,
)
from testbed.eval.wall_contact_experiment_contracts import (
    WallContactExperimentContractError,
    validate_geometry_measurement_top,
)
from testbed.eval.wall_contact_semantics_experiment import (
    assert_paired_ab_single_factor,
    build_wall_contact_source_spec,
    collect_paired_ab_evidence,
    prepare_wall_contact_semantics_experiment,
)
from testbed.eval.wall_contact_source_spec import (
    WallContactSourceSpecError,
    build_python_source_lineage,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_hdf5(path: Path, *, env_dim: int = 89) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as handle:
        observations = handle.create_group("observations")
        observations.create_dataset(
            "env_state",
            data=np.zeros((3, env_dim), dtype=np.float32),
        )
        observations.create_dataset(
            "qpos",
            data=np.asarray(
                [[0.1, 0.2, 0.3, 0.4]] * 3,
                dtype=np.float32,
            ),
        )
        observations.create_dataset(
            "qvel",
            data=np.zeros((3, 4), dtype=np.float32),
        )
        handle.create_dataset(
            "action",
            data=np.zeros((3, 4), dtype=np.float32),
        )
        step = handle.create_group("v2").create_group("step")
        step.create_dataset(
            "action_loss_mask",
            data=np.ones(3, dtype=np.uint8),
        )
        metadata = handle.create_group("metadata")
        metadata.attrs["replay_control_compatibility_profile"] = "recording_pre_fix_v1"


def _source_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, Path]:
    from testbed.eval import wall_contact_semantics_experiment as module

    monkeypatch.setattr(module, "TRAIN_SOURCE_EPISODE_IDS", (3,))
    monkeypatch.setattr(module, "HOLDOUT_SOURCE_EPISODE_IDS", (33,))
    monkeypatch.setattr(module, "EXPECTED_EXECUTION_RECORDS", 1)
    monkeypatch.setattr(module, "EXPECTED_VALIDATION_PATHS", 1)

    full = tmp_path / "full"
    dig = tmp_path / "primitives_copy" / "dig"
    source_paths: dict[str, dict[str, str]] = {}
    for source_id in (3, 33):
        source = full / f"episode_{source_id}.hdf5"
        _write_hdf5(source)
        source_paths[str(source_id)] = {
            "path": str(source),
            "sha256": _sha(source),
        }
    for primitive_id in (0, 1):
        _write_hdf5(dig / f"episode_{primitive_id}.hdf5")

    split = tmp_path / "dig_source_split.yaml"
    split.write_text(
        yaml.safe_dump(
            {
                "split_policy": "source_identity_exact_allowlist_v1",
                "dataset_dir": str(dig.resolve()),
                "train_ids": [0],
                "val_ids": [1],
                "train_source_episode_ids": [3],
                "val_source_episode_ids": [33],
                "allowed_source_episode_ids": [3, 33],
                "source_episode_id_by_primitive_episode_id": {
                    0: 3,
                    1: 33,
                },
            }
        ),
        encoding="utf-8",
    )
    execution = tmp_path / "execution.json"
    execution.write_text(
        json.dumps(
            {
                "schema": "strict_train_coverage_execution_library_v1_1",
                "status": "completed",
                "sample_count": 1,
                "records": [
                    {
                        "exemplar_id": "episode_0",
                        "primitive_episode_id": 0,
                        "source_episode_id": 3,
                        "raw_fields_sha256": "a" * 64,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    pose = tmp_path / "poses.json"
    pose.write_text(
        json.dumps(
            {
                "schema": "strict_train_coverage_pose_paths_v1",
                "status": "completed",
                "sample_count": 1,
                "qpos_contract": {
                    "order": [
                        "swing_position_norm",
                        "boom_position_norm",
                        "stick_position_norm",
                        "bucket_position_norm",
                    ],
                    "dim": 4,
                },
                "source_lock": {"execution_library": {"sha256": _sha(execution)}},
                "records": [
                    {
                        "exemplar_id": "episode_0",
                        "primitive_episode_id": 0,
                        "source_episode_id": 3,
                        "raw_fields_sha256": "a" * 64,
                        "qpos_path_sha256": hashlib.sha256(
                            json.dumps(
                                [[0.1, 0.2, 0.3, 0.4]] * 2,
                                separators=(",", ":"),
                            ).encode()
                        ).hexdigest(),
                        "qpos_path": [[0.1, 0.2, 0.3, 0.4]] * 2,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    unity_root = tmp_path / "unity"
    scene = unity_root / "Assets" / "Scenes" / "Factory.unity"
    normalization = unity_root / "Assets" / "Config" / "normalization.json"
    contact_lineage_paths = [
        unity_root / "Assets" / "Scripts" / name
        for name in (
            "WorktoolWallContactDetail.cs",
            "BucketContactForceMonitor.cs",
            "AgxSimStepAckServer.cs",
            "ExpertWorktoolContactSweep.cs",
            "CodexExpertWorktoolContactSweepUtility.cs",
        )
    ]
    for path, payload in (
        (scene, "fixture scene\n"),
        (normalization, '{"fixture": true}\n'),
        *((path, f"// fixture {path.name}\n") for path in contact_lineage_paths),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
    sweep = tmp_path / "sweep.json"
    sweep.write_text(
        json.dumps(
            {
                "schema": "coverage_worktool_sweep_library_v1",
                "status": "completed",
                "profile": "unity_kinematic_convex_cover_worktool_sweep_v1",
                "sample_count": 1,
                "source_lock": {
                    "execution_library_sha256": _sha(execution),
                    "pose_library_sha256": _sha(pose),
                    "scene_path": str(scene.relative_to(unity_root)),
                    "scene_sha256": _sha(scene),
                    "normalization_path": str(normalization.relative_to(unity_root)),
                    "normalization_sha256": _sha(normalization),
                    "predictor_code_sha256": "c" * 64,
                },
                "records": [{"exemplar_id": "episode_0"}],
            }
        ),
        encoding="utf-8",
    )
    frozen_rollout = tmp_path / "frozen_rollout.jsonl"
    frozen_trace = tmp_path / "frozen_planner_trace.json"
    frozen_rollout.write_text("{}\n", encoding="utf-8")
    frozen_trace.write_text("{}", encoding="utf-8")
    ab_lineage_lock = {
        "bounded_rollout_jsonl": artifact_ref(frozen_rollout),
        "planner_trace": artifact_ref(frozen_trace),
    }
    handoff = tmp_path / "handoff.json"
    handoff.write_text(
        json.dumps(
            {
                "schema": "episode_168_bounded_handoff_v1",
                "exemplar_id": "episode_168",
                "raw_fields_sha256": "d" * 64,
                "cycle_index": 1,
                "selection_event_cycle_index": 0,
                "corridor_id": 1_000_168,
                "handoff_row_index": 602,
                "handoff_t": 602,
                "handoff_step_id": 603,
                "first_dig_row_index": 603,
                "first_dig_t": 603,
                "first_dig_step_id": 604,
                "qpos": [0.5, 0.4, 0.6, 0.2],
                "qvel": [0.3] * 4,
                "bucket_tip_m": [0.1, 0.2, 0.3],
                "terrain_depth_m": [0.0] * 6,
                "remaining_mass_kg": 0.0,
                "source_lock": ab_lineage_lock,
            }
        ),
        encoding="utf-8",
    )
    reset = tmp_path / "expected_reset.json"
    reset.write_text(
        json.dumps(
            {
                "schema": "wall_contact_expected_reset_state_v1",
                "checkpoint_semantics": "first_post_reset_control_step",
                **_reset_state(),
                "source_lock": ab_lineage_lock,
            }
        ),
        encoding="utf-8",
    )
    source_spec = tmp_path / "source_spec.json"
    source_spec.write_text(
        json.dumps(
            {
                "schema": "wall_contact_semantics_source_lock_spec_v1",
                "full_source_episodes": source_paths,
                "split": {"path": str(split), "sha256": _sha(split)},
                "dig_primitives_dir": str(dig),
                "execution_library": {
                    "path": str(execution),
                    "sha256": _sha(execution),
                },
                "pose_library": {
                    "path": str(pose),
                    "sha256": _sha(pose),
                },
                "legacy_sweep": {
                    "path": str(sweep),
                    "sha256": _sha(sweep),
                },
                "frozen_target_handoff": {
                    "path": str(handoff),
                    "sha256": _sha(handoff),
                },
                "expected_reset_state": {
                    "path": str(reset),
                    "sha256": _sha(reset),
                },
                "unity": {
                    "repo_root": str(unity_root),
                    "scene_sha256": _sha(scene),
                    "contact_lineage_files": [
                        artifact_ref(path) for path in contact_lineage_paths
                    ],
                    "contact_lineage_aggregate_sha256": (
                        artifact_refs_aggregate_sha256(
                            [artifact_ref(path) for path in contact_lineage_paths]
                        )
                    ),
                },
                "python": build_python_source_lineage(),
            }
        ),
        encoding="utf-8",
    )
    checkpoint_paths: dict[str, str] = {}
    for primitive in ("dig", "carry", "dump", "return"):
        checkpoint = tmp_path / "checkpoints" / primitive / "policy_best.ckpt"
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_bytes(f"{primitive}-checkpoint".encode())
        checkpoint_paths[primitive] = str(checkpoint)
    base = tmp_path / "base.yaml"
    base.write_text(
        yaml.safe_dump(
            {
                "task": {
                    "camera_names": [
                        "stick_up",
                        "stick_down",
                        "eye_left",
                        "eye_right",
                    ],
                    "episode_len": 1000,
                },
                "eval": {
                    "num_rollouts": 3,
                    "results_dir": "/old",
                    "video_dir": "/old/video",
                    "rollout_log_dir": "/old/log",
                    "record_hdf5": True,
                    "hdf5_dir": "/old/hdf5",
                    "record_hdf5_metadata": {},
                },
                "policy": {
                    "action_scale": [1.0] * 4,
                    "dig_ckpt_path": checkpoint_paths["dig"],
                    "carry_ckpt_path": checkpoint_paths["carry"],
                    "dump_ckpt_path": checkpoint_paths["dump"],
                    "return_ckpt_path": checkpoint_paths["return"],
                    "act_params": {
                        "temporal_agg_window": 100,
                        "temporal_agg_weight_order": "legacy_oldest_first",
                    },
                    "dig_cut_planner": {
                        "coverage": {
                            "actual_tuple_execution_library": {
                                "enabled": True,
                                "path": str(execution),
                                "artifact_sha256": _sha(execution),
                            }
                        }
                    },
                    "box_emptying": {
                        "bounded_dig_probe_stop": {"enabled": True},
                        "functional_cycle_gate": {
                            "enabled": True,
                            "target_cycles": 10,
                        },
                        "safety": {
                            "wall_high_force_n": 100000.0,
                            "stuck_window_steps": 50,
                        },
                    },
                    "switch": {"return_max_steps": 420},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return source_spec, base, handoff


def _detail(
    *,
    component: str = "bucket",
    wall: str = "Dig_ZMin_Board",
    force_n: float = 1000.0,
    step_id: int = 1,
) -> dict[str, object]:
    return {
        "schema": "worktool_wall_contact_detail_v1",
        "step_id": step_id,
        "sim_time_s": step_id * 0.05,
        "delta_time_s": 0.05,
        "session_id": 1,
        "session_count": 1,
        "consecutive_contact_steps": step_id,
        "session_duration_s": step_id * 0.05,
        "session_normal_impulse_n_s": force_n * step_id * 0.05,
        "parts": [component],
        "walls": [wall],
        "pairs": [
            {
                "component": component,
                "machine_shape_path": f"/machine/{component}",
                "wall_name": wall,
                "wall_shape_path": f"/walls/{wall}",
                "callback_count": 1,
                "contact_point_count": 1,
                "max_normal_force_n": force_n,
                "max_tangential_force_n": 20.0,
                "max_total_force_n": force_n,
                "contact_points_world_m": [[1.0, 2.0, 3.0]],
                "representative_contact_point_component_local_m": [
                    0.1,
                    0.2,
                    0.3,
                ],
                "tangential_displacement_m": 0.02,
            }
        ],
    }


def test_contact_detail_schema_fails_closed_on_ambiguous_or_truncated() -> None:
    parsed = parse_worktool_wall_contact_detail(
        ["worktool_wall_contact_detail_v1:" + json.dumps(_detail())]
    )
    assert parsed["parts"] == ["bucket"]
    assert parsed["pairs"][0]["wall_name"] == "Dig_ZMin_Board"

    invalid = _detail()
    invalid["parts"] = ["bucket", "stick"]
    with pytest.raises(ContactEvidenceContractError, match="parts"):
        parse_worktool_wall_contact_detail([invalid])

    invalid = _detail()
    invalid["contact_points_truncated"] = True
    with pytest.raises(ContactEvidenceContractError, match="truncated"):
        parse_worktool_wall_contact_detail([invalid])


def test_source_spec_builder_hashes_all_inputs_without_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing_spec_path, _, _ = _source_fixture(tmp_path, monkeypatch)
    existing = json.loads(existing_spec_path.read_text())
    output = tmp_path / "rebuilt_source_spec.json"
    rebuilt = build_wall_contact_source_spec(
        full_source_dir=Path(existing["full_source_episodes"]["3"]["path"]).parent,
        split_path=existing["split"]["path"],
        dig_primitives_dir=existing["dig_primitives_dir"],
        execution_library_path=existing["execution_library"]["path"],
        pose_library_path=existing["pose_library"]["path"],
        legacy_sweep_path=existing["legacy_sweep"]["path"],
        unity_repo_root=existing["unity"]["repo_root"],
        contact_monitor_code_paths=[
            item["path"] for item in existing["unity"]["contact_lineage_files"]
        ],
        frozen_target_handoff_path=existing["frozen_target_handoff"]["path"],
        expected_reset_state_path=existing["expected_reset_state"]["path"],
        output_path=output,
    )

    assert rebuilt["schema"] == "wall_contact_semantics_source_lock_spec_v1"
    assert set(rebuilt["full_source_episodes"]) == {"3", "33"}
    assert rebuilt["legacy_sweep"]["sha256"] == existing["legacy_sweep"]["sha256"]
    with pytest.raises(FileExistsError):
        build_wall_contact_source_spec(
            full_source_dir=Path(existing["full_source_episodes"]["3"]["path"]).parent,
            split_path=existing["split"]["path"],
            dig_primitives_dir=existing["dig_primitives_dir"],
            execution_library_path=existing["execution_library"]["path"],
            pose_library_path=existing["pose_library"]["path"],
            legacy_sweep_path=existing["legacy_sweep"]["path"],
            unity_repo_root=existing["unity"]["repo_root"],
            contact_monitor_code_paths=[
                item["path"] for item in existing["unity"]["contact_lineage_files"]
            ],
            frozen_target_handoff_path=existing["frozen_target_handoff"]["path"],
            expected_reset_state_path=existing["expected_reset_state"]["path"],
            output_path=output,
        )
    lineage_paths = [
        item["path"] for item in existing["unity"]["contact_lineage_files"]
    ]
    with pytest.raises(
        WallContactSourceSpecError,
        match="contact_lineage_required_files_missing",
    ):
        build_wall_contact_source_spec(
            full_source_dir=Path(existing["full_source_episodes"]["3"]["path"]).parent,
            split_path=existing["split"]["path"],
            dig_primitives_dir=existing["dig_primitives_dir"],
            execution_library_path=existing["execution_library"]["path"],
            pose_library_path=existing["pose_library"]["path"],
            legacy_sweep_path=existing["legacy_sweep"]["path"],
            unity_repo_root=existing["unity"]["repo_root"],
            contact_monitor_code_paths=lineage_paths[:-1],
            frozen_target_handoff_path=existing["frozen_target_handoff"]["path"],
            expected_reset_state_path=existing["expected_reset_state"]["path"],
            output_path=tmp_path / "missing_lineage_spec.json",
        )


def test_prepare_blocks_contact_lineage_source_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_spec, base, _ = _source_fixture(tmp_path, monkeypatch)
    spec = json.loads(source_spec.read_text())
    lineage_path = Path(spec["unity"]["contact_lineage_files"][0]["path"])
    lineage_path.write_text("// drift\n", encoding="utf-8")

    result = prepare_wall_contact_semantics_experiment(
        source_spec_path=source_spec,
        base_config_path=base,
        output_root=tmp_path / "wall_contact_semantics_recovery_v1",
    )

    assert result["status"] == "blocked"
    assert result["primary_blocker"] == "source_artifact_drift"
    assert "contact_lineage_file_0_sha256_drift" in result["blockers"][0]


def test_prepare_is_no_overwrite_and_writes_blocker_on_sha_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_spec, base, _ = _source_fixture(tmp_path, monkeypatch)
    spec = json.loads(source_spec.read_text())
    spec["execution_library"]["sha256"] = "0" * 64
    source_spec.write_text(json.dumps(spec), encoding="utf-8")
    output = tmp_path / "wall_contact_semantics_recovery_v1"

    result = prepare_wall_contact_semantics_experiment(
        source_spec_path=source_spec,
        base_config_path=base,
        output_root=output,
    )

    assert result["status"] == "blocked"
    assert result["primary_blocker"] == "source_artifact_drift"
    assert (output / "experiment_manifest.json").is_file()
    with pytest.raises(FileExistsError):
        prepare_wall_contact_semantics_experiment(
            source_spec_path=source_spec,
            base_config_path=base,
            output_root=output,
        )


def test_prepare_builds_split_geometry_request_replays_and_paired_configs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_spec, base, _ = _source_fixture(tmp_path, monkeypatch)
    output = tmp_path / "wall_contact_semantics_recovery_v1"

    manifest = prepare_wall_contact_semantics_experiment(
        source_spec_path=source_spec,
        base_config_path=base,
        output_root=output,
    )

    assert manifest["schema"] == "wall_contact_semantics_recovery_v1"
    assert manifest["status"] == "blocked"
    assert manifest["primary_blocker"] == "contact_measurements_missing"
    assert manifest["production_promotion_allowed"] is False
    assert set(manifest["config_lock"]["checkpoints"]) == {
        "dig",
        "carry",
        "dump",
        "return",
    }
    assert all(
        len(item["sha256"]) == 64
        for item in manifest["config_lock"]["checkpoints"].values()
    )
    geometry = json.loads((output / "expert_geometry" / "request.json").read_text())
    assert geometry["schema"] == "expert_worktool_contact_sweep_input_v1"
    assert geometry["status"] == "ready"
    assert geometry["qpos_space"] == "normalized_act"
    assert geometry["qpos_order"] == ["swing", "boom", "stick", "bucket"]
    assert geometry["split_authorization"]["train_path_count"] == 1
    assert geometry["split_authorization"]["validation_path_count"] == 1
    assert len(geometry["contact_lineage_files"]) == 5
    assert len(geometry["contact_lineage_aggregate_sha256"]) == 64
    assert [row["split"] for row in geometry["paths"]] == [
        "train",
        "validation",
    ]
    expected_float32_sha = hashlib.sha256(
        np.asarray(
            geometry["paths"][0]["qpos_path"],
            dtype="<f4",
        ).tobytes(order="C")
    ).hexdigest()
    assert geometry["paths"][0]["qpos_path_sha256"] == expected_float32_sha
    schedule = json.loads((output / "expert_replay" / "schedule.json").read_text())
    assert len(schedule["attempts"]) == 2
    assert all(row["max_attempts"] == 1 for row in schedule["attempts"])
    assert all(row["retry_allowed"] is False for row in schedule["attempts"])
    assert {row["control_compatibility_profile"] for row in schedule["attempts"]} == {
        "recording_pre_fix_v1"
    }
    assert all(
        row["runner_contract"]["contact_safety_early_stop_allowed"] is False
        for row in schedule["attempts"]
    )

    pair_schedule = json.loads((output / "paired_ab" / "schedule.json").read_text())
    assert pair_schedule["target_contract"] == {
        "exemplar_id": "episode_168",
        "runtime_role": "diagnostic_legacy",
        "use_scope": "paired_ab_only",
        "production_lookup_allowed": False,
        "reset_checkpoint_semantics": "first_post_reset_control_step",
    }
    assert [(row["seed"], row["condition"]) for row in pair_schedule["attempts"]] == [
        (0, "A"),
        (0, "B"),
        (1, "B"),
        (1, "A"),
        (2, "A"),
        (2, "B"),
    ]
    configs = [
        yaml.safe_load(Path(row["config_path"]).read_text())
        for row in pair_schedule["attempts"]
    ]
    assert_paired_ab_single_factor(configs)
    for config, attempt in zip(configs, pair_schedule["attempts"], strict=True):
        box = config["policy"]["box_emptying"]
        assert box["bounded_dig_probe_stop"]["enabled"] is False
        assert box["contact_semantics_one_cycle_validator"] == {
            "enabled": True,
            "diagnostic_only": True,
            "target_exemplar_id": "episode_168",
            "stop_on": ["target_dump_complete", "safety_terminal"],
        }
        assert config["eval"]["record_hdf5"] is False
        assert config["policy"]["act_params"]["temporal_agg_window"] == 100
        assert (
            config["policy"]["dig_cut_planner"]["coverage"][
                "actual_tuple_execution_library"
            ]["runtime_role"]
            == "diagnostic_legacy"
        )
        expected_mode = (
            "interrupt"
            if attempt["condition"] == "A"
            else "record_bucket_first_session"
        )
        assert box["safety"]["wall_first_touch_mode"] == expected_mode


def test_missing_action_scale_locks_runtime_identity_default() -> None:
    assert effective_action_scale({}) == {
        "configured": None,
        "effective": [1.0, 1.0, 1.0, 1.0],
        "source": "runtime_identity_no_action_scale_consumer",
    }


def test_geometry_measurement_rejects_contact_lineage_aggregate_drift() -> None:
    request = {
        "split_manifest_sha256": "a" * 64,
        "qpos_order": ["swing", "boom", "stick", "bucket"],
        "scene_sha256": "b" * 64,
        "normalization_sha256": "c" * 64,
        "contact_lineage_aggregate_sha256": "d" * 64,
    }
    measurement = {
        "schema": "expert_worktool_contact_sweep_measurement_v1",
        "status": "completed",
        "request_sha256": json_sha256(request),
        "split_manifest_sha256": request["split_manifest_sha256"],
        "qpos_order": request["qpos_order"],
        "source_lock": {
            "scene_sha256": request["scene_sha256"],
            "normalization_sha256": request["normalization_sha256"],
            "contact_lineage_aggregate_sha256": "e" * 64,
            "contact_sweep_code_sha256": "f" * 64,
        },
    }
    with pytest.raises(
        WallContactExperimentContractError,
        match="geometry_contact_lineage_sha_drift",
    ):
        validate_geometry_measurement_top(
            measurement,
            request,
            schema="expert_worktool_contact_sweep_measurement_v1",
        )


def _reset_state(*, qvel: float = 0.0) -> dict[str, object]:
    return {
        "qpos": [0.5, 0.4, 0.6, 0.2],
        "qvel": [qvel] * 4,
        "bucket_tip_m": [0.1, 0.2, 0.3],
        "terrain_depth_m": [0.0] * 6,
        "remaining_mass_kg": 0.0,
    }


def test_reset_pair_validity_checks_absolute_and_cross_condition_qvel() -> None:
    expected = _reset_state()
    valid = validate_reset_pair(
        expected_reset_state=expected,
        reset_a=_reset_state(qvel=0.01),
        reset_b=_reset_state(qvel=0.02),
    )
    assert valid["valid"] is True

    invalid = validate_reset_pair(
        expected_reset_state=expected,
        reset_a=_reset_state(qvel=0.01),
        reset_b=_reset_state(qvel=0.04),
    )
    assert invalid["valid"] is False
    assert "qvel_paired_axis_delta_exceeded" in invalid["violations"]


@pytest.mark.parametrize(
    ("b_dump_count", "hard_failures", "same_region", "expected"),
    [
        (3, 0, False, "safety_too_strict"),
        (0, 2, False, "act_or_goal_geometry"),
        (1, 0, True, "low_margin_dataset_style"),
        (2, 0, False, "inconclusive"),
    ],
)
def test_causal_category_rules(
    b_dump_count: int,
    hard_failures: int,
    same_region: bool,
    expected: str,
) -> None:
    attempts = []
    for seed in range(3):
        dump = seed < b_dump_count
        hard = seed < hard_failures
        attempts.append(
            {
                "seed": seed,
                "condition": "B",
                "pair_valid": True,
                "dump_completed": dump,
                "entered_carry": dump,
                "contact_ended_before_carry": dump,
                "hard_violation": hard,
                "contact_driven_hard_failure": hard,
            }
        )
    decision = causal_classification(
        attempts=attempts,
        expert_same_region_sub_100kn=same_region,
        expert_lineage_complete=True,
    )
    assert decision == expected


def test_ab_collection_blocks_invalid_pair_and_never_unlocks_promotion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_spec, base, handoff = _source_fixture(tmp_path, monkeypatch)
    root = tmp_path / "wall_contact_semantics_recovery_v1"
    prepare_wall_contact_semantics_experiment(
        source_spec_path=source_spec,
        base_config_path=base,
        output_root=root,
    )
    schedule = json.loads((root / "paired_ab/schedule.json").read_text())
    attempts = []
    for item in schedule["attempts"]:
        reset = _reset_state(
            qvel=0.01
            if item["condition"] == "A"
            else (0.04 if item["seed"] == 1 else 0.02)
        )
        attempts.append(
            {
                "schema": "wall_contact_paired_ab_attempt_v1",
                "status": "passed",
                "attempt_id": item["attempt_id"],
                "pair_id": item["pair_id"],
                "seed": item["seed"],
                "condition": item["condition"],
                "retry_count": 0,
                "reset_checkpoint_semantics": ("first_post_reset_control_step"),
                "reset_state": reset,
                "selected_exemplar_id": "episode_168",
                "selected_raw_fields_sha256": "d" * 64,
                "entered_carry": False,
                "dump_completed": False,
                "contact_ended_before_carry": False,
                "terminal_reason": (
                    "box_safety:wall_contact_first_session"
                    if item["condition"] == "A"
                    else "wall_contact_repeat_session"
                ),
                "hard_stop_violations": (
                    [] if item["condition"] == "A" else ["wall_contact_repeat_session"]
                ),
                "hard_violation": item["condition"] == "B",
                "contact_driven_hard_failure": item["condition"] == "B",
                "zero_action_after_first_contact": True,
                "neutral_acknowledged": True,
                "debug_fields": {
                    "box_safety_wall_contact_diagnostic_ab_enabled": True,
                    "box_safety_wall_first_touch_mode": (
                        "interrupt"
                        if item["condition"] == "A"
                        else "record_bucket_first_session"
                    ),
                },
                "warnings_by_step": [
                    {
                        "step_id": 1,
                        "warnings": [
                            "worktool_wall_contact_detail_v1:" + json.dumps(_detail())
                        ],
                    }
                ],
            }
        )
    attempts_path = tmp_path / "attempts.json"
    attempts_path.write_text(
        json.dumps(
            {
                "schema": "wall_contact_paired_ab_attempt_set_v1",
                "status": "passed",
                "attempts": attempts,
                "frozen_handoff_sha256": _sha(handoff),
            }
        ),
        encoding="utf-8",
    )

    result = collect_paired_ab_evidence(
        experiment_manifest_path=root / "experiment_manifest.json",
        attempt_set_path=attempts_path,
        output_path=root / "paired_ab/collection.json",
    )

    assert result["status"] == "blocked"
    assert result["invalid_pair_ids"] == ["seed_1"]
    assert result["causal_classification"] == "inconclusive"
    assert result["production_promotion_allowed"] is False
