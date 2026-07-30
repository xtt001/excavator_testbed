from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
import pytest
import yaml

from testbed.eval.act_regression_live_matrix import (
    CAUSAL_LIVE_SCHEDULE,
    InitialStateSignature,
    build_act_regression_live_configs,
    collect_act_regression_live_evidence,
    evaluate_initial_state,
    extract_live_probe_attempt,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_fixture(tmp_path: Path) -> tuple[Path, Path]:
    base_config = tmp_path / "a0.yaml"
    base_config.write_text(
        yaml.safe_dump(
            {
                "task": {
                    "camera_names": [
                        "stick_up",
                        "stick_down",
                        "eye_left",
                        "eye_right",
                    ]
                },
                "eval": {
                    "num_rollouts": 1,
                    "no_overwrite": True,
                    "save_video": True,
                    "results_dir": "/old/results",
                    "video_dir": "/old/videos",
                    "rollout_log_dir": "/old/rollouts",
                    "hdf5_dir": "/old/hdf5",
                    "record_hdf5": True,
                    "save_rollout_logs": True,
                    "stream_rollout_logs": True,
                    "record_hdf5_metadata": {
                        "unity_scene_id": "scene@sha256:abc",
                        "unity_source_sha256": "def",
                    },
                },
                "policy": {
                    "dig_ckpt_path": "/ckpts/dig/policy_best.ckpt",
                    "carry_ckpt_path": "/ckpts/carry/policy_best.ckpt",
                    "dump_ckpt_path": "/ckpts/dump/policy_best.ckpt",
                    "return_ckpt_path": "/ckpts/return/policy_best.ckpt",
                    "dig_cut_planner": {
                        "enabled": True,
                        "mode": "operator_prior_sweep_belief",
                        "fallback_mode": "raise",
                    },
                    "act_params": {
                        "temporal_agg_window": 100,
                        "temporal_agg_weight_order": "legacy_oldest_first",
                        "temporal_agg_decay": 0.01,
                    },
                    "box_emptying": {
                        "safety_enabled": True,
                        "carry_start_envelope": {"enabled": True},
                        "functional_cycle_gate": {"enabled": True},
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    conditions: dict[str, dict[str, str]] = {}
    for condition_id in ("F0", "D1", "C1", "DC1"):
        source = tmp_path / condition_id / "source.json"
        source.parent.mkdir()
        source.write_text(
            json.dumps(
                {
                    "schema": "residual_cut_intent_runtime_source_v1",
                    "status": "present",
                    "plan_count": 2,
                    "plans": [],
                }
            ),
            encoding="utf-8",
        )
        conditions[condition_id] = {
            "runtime_source_path": str(source),
            "runtime_source_sha256": _sha256(source),
            "allowed_diff_guard": {"status": "passed"},
        }
    matrix = tmp_path / "matrix.json"
    matrix.write_text(
        json.dumps(
            {
                "schema": "act_regression_plan_matrix_v1",
                "status": "present",
                "diagnostic_only": True,
                "promotion_eligible": False,
                "conditions": conditions,
            }
        ),
        encoding="utf-8",
    )
    return base_config, matrix


def test_live_config_builder_emits_locked_interleaved_3x4_matrix(
    tmp_path: Path,
) -> None:
    base_config, matrix = _write_fixture(tmp_path)
    output = tmp_path / "generated"

    manifest = build_act_regression_live_configs(
        base_config_path=base_config,
        plan_matrix_path=matrix,
        output_dir=output,
    )

    assert [item["condition_id"] for item in manifest["schedule"]] == [
        condition for _, condition in CAUSAL_LIVE_SCHEDULE
    ]
    assert len(manifest["schedule"]) == 12
    for item in manifest["schedule"]:
        config = yaml.safe_load(
            Path(item["config_path"]).read_text(encoding="utf-8")
        )
        assert config["eval"]["save_video"] is False
        assert config["eval"]["no_overwrite"] is True
        assert config["policy"]["dig_cut_planner"]["mode"] == (
            "residual_cut_intent"
        )
        box = config["policy"]["box_emptying"]
        assert box["safety_enabled"] is True
        assert box["carry_start_envelope"]["enabled"] is True
        assert box["functional_cycle_gate"]["enabled"] is False
        assert box["bounded_dig_probe_stop"] == {
            "enabled": True,
            "diagnostic_only": True,
            "target_cycle_index": 1,
            "max_dig_steps": 500,
        }
        assert config["policy"]["act_params"]["temporal_agg_window"] == 100

    with pytest.raises(FileExistsError):
        build_act_regression_live_configs(
            base_config_path=base_config,
            plan_matrix_path=matrix,
            output_dir=output,
        )


def test_initial_state_contract_checks_each_locked_component() -> None:
    reference = InitialStateSignature(
        qpos=(0.5, 0.4, 0.6, 0.2),
        bucket_tip_pose_m=(0.1, 0.2, 0.3),
        terrain_surface_depth_m=(0.08,) * 6,
        remaining_mass_kg=7400.0,
    )
    valid = evaluate_initial_state(reference, reference)
    assert valid["valid"] is True

    shifted = InitialStateSignature(
        qpos=(0.5, 0.4, 0.6, 0.2),
        bucket_tip_pose_m=(0.1, 0.2, 0.3),
        terrain_surface_depth_m=(0.08, 0.08, 0.08, 0.09, 0.08, 0.08),
        remaining_mass_kg=7400.0,
    )
    invalid = evaluate_initial_state(shifted, reference)
    assert invalid["valid"] is False
    assert "terrain_surface_depth_m" in invalid["violations"]


def test_initial_signature_uses_bounded_median_to_reject_one_frame_glitch(
    tmp_path: Path,
) -> None:
    path = tmp_path / "episode_0.hdf5"
    env = np.zeros((5, 107), dtype=np.float32)
    env[:, 28:31] = [0.1, 0.2, 0.3]
    env[0, 30] = 9.0
    env[:, 33:39] = 0.08
    env[:, 97] = 7400.0
    with h5py.File(path, "w") as handle:
        handle.create_dataset(
            "observations/qpos",
            data=np.tile([0.5, 0.4, 0.6, 0.2], (5, 1)),
        )
        handle.create_dataset("observations/env_state", data=env)

    signature = InitialStateSignature.from_hdf5(path)

    assert signature.bucket_tip_pose_m == pytest.approx((0.1, 0.2, 0.3))


def test_extract_probe_attempt_preserves_failure_and_neutral_ack(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "run"
    hdf5_dir = run_dir / "results" / "hdf5_rollouts"
    rollout_dir = run_dir / "results" / "rollouts"
    hdf5_dir.mkdir(parents=True)
    rollout_dir.mkdir(parents=True)
    env = np.zeros((3, 107), dtype=np.float32)
    env[:, 28:31] = [0.1, 0.2, 0.3]
    env[:, 33:39] = 0.08
    env[:, 97] = 7400.0
    env[1, 101] = 1.0
    env[1, 102] = 25000.0
    env[1, 103] = 1.0
    with h5py.File(hdf5_dir / "episode_0.hdf5", "w") as handle:
        handle.create_dataset(
            "observations/qpos",
            data=np.tile([0.5, 0.4, 0.6, 0.2], (3, 1)),
        )
        handle.create_dataset("observations/env_state", data=env)
        handle.create_dataset("timestamps/step_id", data=[1, 2, 3])
        handle.create_dataset(
            "action",
            data=np.asarray([[0.1] * 4, [0.2] * 4, [0.0] * 4]),
        )
    rows = [
        {
            "step_id": 1,
            "primitive_cycle_index": 1,
            "skill_name": "dig",
            "carry_start_envelope_ready": False,
            "bounded_dig_probe_stop_trigger_kind": "",
        },
        {
            "step_id": 2,
            "primitive_cycle_index": 1,
            "skill_name": "dig",
            "carry_start_envelope_ready": False,
            "bounded_dig_probe_stop_trigger_kind": "wall",
        },
        {
            "step_id": 3,
            "primitive_cycle_index": 1,
            "skill_name": "dig",
            "carry_start_envelope_ready": False,
            "bounded_dig_probe_stop_trigger_kind": "wall",
            "bounded_dig_probe_stop_neutral_acknowledged": True,
            "bounded_dig_probe_stop_terminal_requested": True,
        },
    ]
    (rollout_dir / "rollout_000.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    reference = InitialStateSignature.from_hdf5(
        hdf5_dir / "episode_0.hdf5"
    )

    attempt = extract_live_probe_attempt(
        run_dir=run_dir,
        repeat_id="round01_F0_attempt01",
        condition_id="F0",
        initial_reference=reference,
    )

    assert attempt["initial_state_valid"] is True
    assert attempt["wall_contact_count"] == 1
    assert attempt["wall_typed_mask_observed"] is True
    assert attempt["wall_contact_session_count"] == 1
    assert attempt["wall_max_force_n"] == pytest.approx(25000.0)
    assert attempt["bottom_contact_count"] == 0
    assert attempt["bottom_typed_mask_observed"] is False
    assert attempt["bottom_contact_session_count"] == 0
    assert attempt["bottom_max_force_n"] == pytest.approx(0.0)
    assert attempt["envelope_ready"] is False
    assert attempt["neutral_acknowledged"] is True
    assert attempt["terminal_requested"] is True


def test_collect_live_evidence_classifies_corridor_and_is_no_overwrite(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "policy_artifacts"
    artifact_root.mkdir()
    policy_paths = {}
    for primitive in ("dig", "carry", "dump", "return"):
        primitive_dir = artifact_root / primitive
        primitive_dir.mkdir()
        checkpoint = primitive_dir / "policy_best.ckpt"
        stats = primitive_dir / "dataset_stats.pkl"
        checkpoint.write_bytes(f"{primitive}-checkpoint".encode())
        stats.write_bytes(f"{primitive}-stats".encode())
        policy_paths[primitive] = {
            "checkpoint": checkpoint,
            "stats": stats,
        }
    base_config = tmp_path / "base.yaml"
    base_config.write_text(
        yaml.safe_dump(
            {
                "task": {
                    "camera_names": [
                        "stick_up",
                        "stick_down",
                        "eye_left",
                        "eye_right",
                    ]
                },
                "eval": {
                    "record_hdf5_metadata": {
                        "unity_scene_id": "scene@sha256:scene-sha",
                        "unity_source_sha256": "source-sha",
                        "unity_git_commit": "commit",
                    }
                },
                "policy": {
                    "act_params": {
                        "temporal_agg_window": 100,
                        "temporal_agg_weight_order": (
                            "legacy_oldest_first"
                        ),
                        "temporal_agg_decay": 0.01,
                    },
                    "dig_cut_planner": {"enabled": True},
                    "box_emptying": {
                        "safety_enabled": True,
                        "carry_start_envelope": {"enabled": True},
                    },
                    **{
                        f"{primitive}_ckpt_path": str(
                            policy_paths[primitive]["checkpoint"]
                        )
                        for primitive in policy_paths
                    },
                    **{
                        f"{primitive}_ckpt_dir": str(
                            policy_paths[primitive]["checkpoint"].parent
                        )
                        for primitive in policy_paths
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    schedule = []
    condition_repeat_count = {
        condition_id: 0 for condition_id in ("F0", "D1", "C1", "DC1")
    }
    for slot_index, (round_index, condition_id) in enumerate(
        CAUSAL_LIVE_SCHEDULE,
        start=1,
    ):
        condition_repeat_count[condition_id] += 1
        repeat_index = condition_repeat_count[condition_id]
        repeat_id = (
            f"round{round_index:02d}_slot{slot_index:02d}_"
            f"{condition_id}_repeat{repeat_index:02d}"
        )
        run_dir = tmp_path / "runs" / repeat_id
        _write_probe_fixture(
            run_dir,
            wall=(
                condition_id in {"F0", "D1"}
                and repeat_index in {2, 3}
            ),
            envelope_ready=condition_id in {"C1", "DC1"},
        )
        config = tmp_path / "configs" / f"{repeat_id}.yaml"
        source = tmp_path / "sources" / f"{condition_id}.json"
        config.parent.mkdir(parents=True, exist_ok=True)
        source.parent.mkdir(parents=True, exist_ok=True)
        config.write_text("diagnostic_only: true\n", encoding="utf-8")
        if not source.exists():
            source.write_text(
                json.dumps({"condition_id": condition_id}),
                encoding="utf-8",
            )
        schedule.append(
            {
                "slot_index": slot_index,
                "round_index": round_index,
                "repeat_index": repeat_index,
                "repeat_id": repeat_id,
                "condition_id": condition_id,
                "run_dir": str(run_dir),
                "config_path": str(config),
                "config_sha256": _sha256(config),
                "runtime_source_path": str(source),
                "runtime_source_sha256": _sha256(source),
            }
        )
    plan_matrix = tmp_path / "plan_matrix.json"
    plan_matrix.write_text("{}\n", encoding="utf-8")
    manifest = tmp_path / "live_manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema": "act_regression_live_matrix_v1",
                "status": "present",
                "base_config_path": str(base_config),
                "base_config_sha256": _sha256(base_config),
                "camera_order": [
                    "stick_up",
                    "stick_down",
                    "eye_left",
                    "eye_right",
                ],
                "temporal_aggregation": {
                    "window": 100,
                    "weight_order": "legacy_oldest_first",
                    "decay": 0.01,
                },
                "safety_enabled": True,
                "carry_envelope_live_disable_allowed": False,
                "plan_matrix_path": str(plan_matrix),
                "plan_matrix_sha256": _sha256(plan_matrix),
                "schedule": schedule,
            }
        ),
        encoding="utf-8",
    )
    offline_paths = []
    for name, first_wall_step in (("a0", 40), ("a1", 60)):
        path = tmp_path / f"{name}.json"
        path.write_text(
            json.dumps(
                {
                    "schema": "act_regression_offline_diagnostic_v1",
                    "status": "present",
                    "evidence_scope": (
                        "teacher_forced_recorded_observation"
                    ),
                    "closed_loop_claim": False,
                    "summary": {
                        "count": first_wall_step,
                        "first_wall_step_id": first_wall_step,
                        "first_bottom_step_id": None,
                        "aggregated_vs_actual_mae": [0.0] * 4,
                    },
                }
            ),
            encoding="utf-8",
        )
        offline_paths.append(path)

    result = collect_act_regression_live_evidence(
        live_manifest_path=manifest,
        offline_a0_path=offline_paths[0],
        offline_a1_path=offline_paths[1],
        evidence_matrix_output_path=tmp_path / "evidence.json",
        diagnosis_output_path=tmp_path / "diagnosis.json",
        report_output_path=tmp_path / "report.md",
    )

    assert result["diagnosis"]["root_cause_classification"]["category"] == (
        "corridor_geometry_primary"
    )
    evidence = result["evidence_matrix"]
    assert len(evidence["attempts"]) == 12
    assert evidence["condition_summary"]["F0"][
        "wall_contact_repeat_count"
    ] == 2
    assert evidence["condition_summary"]["C1"][
        "envelope_ready_repeat_count"
    ] == 3
    assert evidence["experiment_contract"]["camera_order"] == [
        "stick_up",
        "stick_down",
        "eye_left",
        "eye_right",
    ]
    assert evidence["experiment_contract"]["policy_artifacts"]["dig"] == {
        "checkpoint_path": str(
            policy_paths["dig"]["checkpoint"].resolve()
        ),
        "checkpoint_sha256": _sha256(
            policy_paths["dig"]["checkpoint"]
        ),
        "stats_path": str(policy_paths["dig"]["stats"].resolve()),
        "stats_sha256": _sha256(policy_paths["dig"]["stats"]),
    }
    assert evidence["experiment_contract"]["unity_lineage"] == {
        "unity_scene_id": "scene@sha256:scene-sha",
        "unity_source_sha256": "source-sha",
        "unity_git_commit": "commit",
    }
    assert evidence["live_safety_summary"] == {
        "attempt_count": 12,
        "wall_contact_repeat_count": 4,
        "bottom_contact_repeat_count": 0,
        "stuck_repeat_count": 0,
        "timeout_repeat_count": 0,
        "terminal_contract_pass_count": 12,
        "max_wall_force_n": pytest.approx(25000.0),
        "max_bottom_force_n": pytest.approx(0.0),
    }
    assert "bounded two-cycle probes" in (
        tmp_path / "report.md"
    ).read_text(encoding="utf-8")

    with pytest.raises(FileExistsError):
        collect_act_regression_live_evidence(
            live_manifest_path=manifest,
            offline_a0_path=offline_paths[0],
            offline_a1_path=offline_paths[1],
            evidence_matrix_output_path=tmp_path / "evidence.json",
            diagnosis_output_path=tmp_path / "diagnosis-2.json",
            report_output_path=tmp_path / "report-2.md",
        )
    assert not (tmp_path / "diagnosis-2.json").exists()
    assert not (tmp_path / "report-2.md").exists()


def _write_probe_fixture(
    run_dir: Path,
    *,
    wall: bool,
    envelope_ready: bool,
) -> None:
    hdf5_dir = run_dir / "results" / "hdf5_rollouts"
    rollout_dir = run_dir / "results" / "rollouts"
    hdf5_dir.mkdir(parents=True)
    rollout_dir.mkdir(parents=True)
    env = np.zeros((3, 107), dtype=np.float32)
    env[:, 28:31] = [0.1, 0.2, 0.3]
    env[:, 33:39] = 0.08
    env[:, 97] = 7400.0
    if wall:
        env[1, 101] = 1.0
        env[1, 102] = 25000.0
        env[1, 103] = 1.0
    with h5py.File(hdf5_dir / "episode_0.hdf5", "w") as handle:
        handle.create_dataset(
            "observations/qpos",
            data=np.tile([0.5, 0.4, 0.6, 0.2], (3, 1)),
        )
        handle.create_dataset("observations/env_state", data=env)
        handle.create_dataset("timestamps/step_id", data=[1, 2, 3])
        handle.create_dataset(
            "action",
            data=np.asarray([[0.1] * 4, [0.2] * 4, [0.0] * 4]),
        )
    trigger = "wall" if wall else "carry_start_envelope_ready"
    rows = [
        {
            "step_id": 1,
            "primitive_cycle_index": 1,
            "skill_name": "dig",
            "carry_start_envelope_ready": False,
            "bounded_dig_probe_stop_trigger_kind": "",
        },
        {
            "step_id": 2,
            "primitive_cycle_index": 1,
            "skill_name": "dig",
            "carry_start_envelope_ready": envelope_ready,
            "bounded_dig_probe_stop_trigger_kind": trigger,
        },
        {
            "step_id": 3,
            "primitive_cycle_index": 1,
            "skill_name": "dig",
            "carry_start_envelope_ready": envelope_ready,
            "bounded_dig_probe_stop_trigger_kind": trigger,
            "bounded_dig_probe_stop_neutral_acknowledged": True,
            "bounded_dig_probe_stop_terminal_requested": True,
        },
    ]
    (rollout_dir / "rollout_000.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
