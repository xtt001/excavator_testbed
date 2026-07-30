from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

import testbed.eval.unity_contact_rollout_probe as probe
from testbed.data.schema import ENV_STATE_ORDER_V2_4
from testbed.eval.wall_contact_artifact_io import (
    artifact_ref,
    artifact_refs_aggregate_sha256,
)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def _sources(tmp_path: Path) -> dict[str, Path]:
    baseline = tmp_path / "baseline"
    paths = {
        "config": baseline / "results/eval_resolved_config.yaml",
        "rollout": baseline / "results/rollouts/rollout_000.jsonl",
        "summary": baseline
        / "results/rollouts/rollout_000_summary.json",
        "reset": baseline / "validation_v1/validation_reset_000.json",
        "environment": tmp_path / "environment_manifest.json",
    }
    checkpoint_fields: dict[str, str] = {}
    for primitive in ("dig", "carry", "dump", "return"):
        checkpoint = tmp_path / primitive / "policy_best.ckpt"
        checkpoint.parent.mkdir(parents=True)
        checkpoint.write_bytes(primitive.encode())
        (checkpoint.parent / "dataset_stats.pkl").write_bytes(
            f"{primitive}-stats".encode()
        )
        checkpoint_fields[f"{primitive}_ckpt_path"] = str(checkpoint)
    prior = tmp_path / "prior.json"
    prior.write_text("{}\n", encoding="utf-8")
    config = {
        "agx": {"host": "127.0.0.1", "port": 5057, "timeout": 10.0},
        "task": {
            "episode_len": 24000,
            "camera_names": [
                "stick_up",
                "stick_down",
                "eye_left",
                "eye_right",
            ],
        },
        "eval": {
            "num_rollouts": 1,
            "target_cycle_gate": 10,
            "temporal_agg": True,
        },
        "policy": {
            **checkpoint_fields,
            "act_params": {"chunk_size": 100},
            "dig_cut_planner": {
                "mode": "operator_prior_sweep_belief",
                "prior_path": str(prior),
            },
            "box_emptying": {
                "safety": {
                    "wall_high_force_n": 100_000.0,
                    "stuck_action_l1_min": 0.1,
                    "stuck_window_steps": 50,
                    "stuck_qpos_max_change": 0.005,
                    "stuck_bucket_tip_max_displacement_m": 0.02,
                }
            },
            "switch": {
                "return_max_steps": 420,
                "dig_bad_replan_max_steps": 220,
            },
        },
    }
    paths["config"].parent.mkdir(parents=True)
    paths["config"].write_text(yaml.safe_dump(config), encoding="utf-8")
    paths["rollout"].parent.mkdir(parents=True)
    paths["rollout"].write_text("{}\n", encoding="utf-8")
    _write_json(
        paths["summary"],
        {
            "completed_dump_count": 7,
            "target_cycle_completed_dump_count": 7,
            "coverage_completed_dump_count": 7,
            "rollout_stop_reason": "box_safety:wall_contact_terminal",
        },
    )
    _write_json(
        paths["reset"],
        {"reset_id": "seed_1000", "completed_full_cycle_count": 7},
    )
    scene = tmp_path / "scene.unity"
    normalization = tmp_path / "normalization.json"
    contact = tmp_path / "BucketContactForceMonitor.cs"
    server = tmp_path / "AgxSimStepAckServer.cs"
    camera_capture = tmp_path / "AgxSimJpegCameraCapture.cs"
    floor_sidecar = tmp_path / "WorktoolFactoryFloorContactDetail.cs"
    for artifact in (
        scene,
        normalization,
        contact,
        server,
        camera_capture,
        floor_sidecar,
    ):
        artifact.write_text(artifact.name, encoding="utf-8")
    contact_refs = [artifact_ref(contact), artifact_ref(server)]
    _write_json(
        paths["environment"],
        {
            "source_lock": {
                "unity": {
                    "scene_path": str(scene),
                    "scene_sha256": artifact_ref(scene)["sha256"],
                    "normalization_path": str(normalization),
                    "normalization_sha256": artifact_ref(normalization)[
                        "sha256"
                    ],
                    "contact_lineage_files": contact_refs,
                    "contact_lineage_aggregate_sha256": (
                        artifact_refs_aggregate_sha256(contact_refs)
                    ),
                }
            }
        },
    )
    return paths


def _prepare(tmp_path: Path) -> dict[str, Any]:
    paths = _sources(tmp_path)
    return probe.prepare_unity_contact_rollout_probe(
        source_config_path=paths["config"],
        source_rollout_path=paths["rollout"],
        source_summary_path=paths["summary"],
        source_reset_validation_path=paths["reset"],
        environment_manifest_path=paths["environment"],
        output_root=tmp_path / "probe",
    )


def _host_evidence() -> dict[str, Any]:
    return {
        "schema": "agx_unity_get_info_v1",
        "host": "127.0.0.1",
        "port": 5057,
        "protocol_version": "agx-sim/v2",
        "runtime_build_id": (
            "editor:2022.3.62f3:test:"
            "agx_env_state_v2_4_107"
        ),
        "env_state_contract_version": "agx_env_state_v2_4_107",
        "action_order": [
            "swing_speed_cmd",
            "boom_speed_cmd",
            "stick_speed_cmd",
            "bucket_speed_cmd",
        ],
        "qpos_order": [
            "swing_position_norm",
            "boom_position_norm",
            "stick_position_norm",
            "bucket_position_norm",
        ],
        "qvel_order": [
            "swing_speed",
            "boom_speed",
            "stick_speed",
            "bucket_speed",
        ],
        "env_state_order": list(ENV_STATE_ORDER_V2_4),
        "camera_names": [
            "stick_up",
            "stick_down",
            "eye_left",
            "eye_right",
        ],
        "warnings": [
            "worktool_factory_floor_contact_detail_capability_v1:ready"
        ],
    }


def test_probe_is_exactly_once_a0_locked_and_diagnostic_only(
    tmp_path: Path,
) -> None:
    manifest = _prepare(tmp_path)
    config = yaml.safe_load(Path(manifest["config_path"]).read_text())
    safety = config["policy"]["box_emptying"]["safety"]

    assert manifest["schema"] == probe.PROBE_SCHEMA
    assert manifest["max_attempts"] == 1
    assert manifest["retry_allowed"] is False
    assert manifest["max_shovels"] == 10
    assert manifest["writes_training_hdf5"] is False
    assert (
        manifest[
            "parent_contact_lineage_drift_expected_due_to_this_diagnostic"
        ]
        is True
    )
    assert manifest["allowed_parent_contact_lineage_drift_files"] == [
        "AgxSimJpegCameraCapture.cs",
        "AgxSimStepAckServer.cs",
        "BucketContactForceMonitor.cs",
        "WorktoolFactoryFloorContactDetail.cs",
    ]
    assert manifest["source_lock"]["agx"] == {
        "host": "127.0.0.1",
        "port": 5057,
        "timeout": 10.0,
    }
    unity_names = {
        Path(item["path"]).name
        for item in manifest["source_lock"]["unity"][
            "contact_lineage_files"
        ]
    }
    assert {
        "BucketContactForceMonitor.cs",
        "AgxSimJpegCameraCapture.cs",
        "AgxSimStepAckServer.cs",
        "WorktoolFactoryFloorContactDetail.cs",
    } <= unity_names
    assert safety["wall_first_touch_mode"] == "record_bucket_all_contacts"
    assert safety["wall_contact_diagnostic_observe_only_enabled"] is True
    assert safety["unity_contact_diagnostic_observe_only_enabled"] is True
    assert safety["unity_contact_diagnostic_backend"] == "agx_unity"
    assert config["eval"]["record_hdf5"] is False
    assert manifest["downstream_gates"]["functional_1x10_allowed"] is False
    locked = {
        Path(item["path"]).name
        for item in manifest["source_lock"]["diagnostic_code"]
    }
    assert {
        "wall_contact_artifact_io.py",
        "wall_contact_config_contracts.py",
        "wall_contact_evidence_contracts.py",
        "unity_contact_observe_only_report.py",
        "unity_contact_rollout_probe.py",
        "wall_contact_rollout_integrity.py",
        "unity_contact_rollout_probe.py",
    } <= locked
    runtime_paths = {
        str(Path(item["path"]).relative_to(Path.cwd()))
        for item in manifest["source_lock"]["runtime_code"]
    }
    assert (
        "testbed/planner/box_emptying/bottom_contact_detail.py"
        in runtime_paths
    )
    assert {
        "testbed/backends/agx/backend.py",
        "testbed/backends/agx/protocol.py",
        "testbed/data/schema.py",
        "testbed/planner/box_emptying/contact_ownership.py",
        "testbed/planner/box_emptying/runtime_monitor.py",
        "testbed/planner/box_emptying/safety_effects.py",
        "testbed/planner/box_emptying/stop_conditions.py",
        "testbed/planner/primitive/execution/action_dispatch.py",
        "testbed/policies/hybrid/primitive_planner.py",
    } <= runtime_paths


def test_probe_validation_rejects_config_or_code_drift(tmp_path: Path) -> None:
    manifest = _prepare(tmp_path)
    config_path = Path(manifest["config_path"])
    config = yaml.safe_load(config_path.read_text())
    config["policy"]["box_emptying"]["safety"][
        "unity_contact_diagnostic_observe_only_enabled"
    ] = False
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    with pytest.raises(
        probe.UnityContactObserveOnlyReportError,
        match="artifact_drift:diagnostic_config|diagnostic_config_contract_drift",
    ):
        probe.validate_unity_contact_rollout_probe(
            manifest["manifest_path"]
        )


def test_probe_validation_rejects_unity_contact_code_drift(
    tmp_path: Path,
) -> None:
    manifest = _prepare(tmp_path)
    server = next(
        Path(item["path"])
        for item in manifest["source_lock"]["unity"][
            "contact_lineage_files"
        ]
        if Path(item["path"]).name == "AgxSimStepAckServer.cs"
    )
    server.write_text("drift", encoding="utf-8")

    with pytest.raises(
        probe.UnityContactObserveOnlyReportError,
        match="artifact_drift:unity_contact_environment",
    ):
        probe.validate_unity_contact_rollout_probe(
            manifest["manifest_path"]
        )


def test_probe_validation_rejects_camera_runtime_contract_drift(
    tmp_path: Path,
) -> None:
    manifest = _prepare(tmp_path)
    camera_capture = next(
        Path(item["path"])
        for item in manifest["source_lock"]["unity"][
            "contact_lineage_files"
        ]
        if Path(item["path"]).name == "AgxSimJpegCameraCapture.cs"
    )
    camera_capture.write_text("drift", encoding="utf-8")

    with pytest.raises(
        probe.UnityContactObserveOnlyReportError,
        match="artifact_drift:unity_contact_environment",
    ):
        probe.validate_unity_contact_rollout_probe(
            manifest["manifest_path"]
        )


def test_failed_attempt_is_consumed_and_cannot_retry(tmp_path: Path) -> None:
    manifest = _prepare(tmp_path)

    def failed_executor(
        command: list[str],
        cwd: Path,
        log_path: Path,
    ) -> int:
        del command, cwd, log_path
        return 9

    report = probe.run_unity_contact_rollout_probe(
        manifest_path=manifest["manifest_path"],
        executor=failed_executor,
        host_probe=lambda _agx: _host_evidence(),
        cwd=tmp_path,
    )

    assert report["status"] == "failed"
    assert report["termination_category"] == "failed"
    assert report["executed_attempt_count"] == 1
    assert report["retry_allowed"] is False
    assert report["unity_host_get_info"] == _host_evidence()
    with pytest.raises(FileExistsError, match="already consumed"):
        probe.run_unity_contact_rollout_probe(
            manifest_path=manifest["manifest_path"],
            executor=failed_executor,
            host_probe=lambda _agx: _host_evidence(),
            cwd=tmp_path,
        )


def test_invalid_unity_host_identity_does_not_consume_attempt(
    tmp_path: Path,
) -> None:
    manifest = _prepare(tmp_path)
    invalid = _host_evidence()
    invalid["protocol_version"] = "agx-sim/v1"

    with pytest.raises(
        probe.UnityContactObserveOnlyReportError,
        match="unity_host_identity_invalid:protocol_version",
    ):
        probe.run_unity_contact_rollout_probe(
            manifest_path=manifest["manifest_path"],
            executor=lambda _command, _cwd, _log: 0,
            host_probe=lambda _agx: invalid,
            cwd=tmp_path,
        )

    assert not Path(manifest["run_root"]).exists()


def test_missing_floor_sidecar_capability_does_not_consume_attempt(
    tmp_path: Path,
) -> None:
    manifest = _prepare(tmp_path)
    invalid = _host_evidence()
    invalid["warnings"] = []

    with pytest.raises(
        probe.UnityContactObserveOnlyReportError,
        match="unity_host_identity_invalid:warnings",
    ):
        probe.run_unity_contact_rollout_probe(
            manifest_path=manifest["manifest_path"],
            executor=lambda _command, _cwd, _log: 0,
            host_probe=lambda _agx: invalid,
            cwd=tmp_path,
        )

    assert not Path(manifest["run_root"]).exists()
