from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

import testbed.eval.wall_contact_rollout_probe as probe
from testbed.eval.wall_contact_artifact_io import artifact_ref
from testbed.eval.wall_contact_rollout_integrity import (
    runtime_command,
    validate_execution_lineage,
)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n", encoding="utf-8")


def _source_fixture(tmp_path: Path) -> tuple[dict[str, Path], dict[str, Path]]:
    source_root = tmp_path / "baseline"
    paths = {
        "config": source_root / "results/eval_resolved_config.yaml",
        "rollout": source_root / "results/rollouts/rollout_000.jsonl",
        "summary": source_root
        / "results/rollouts/rollout_000_summary.json",
        "reset": source_root / "validation/validation_reset_000.json",
        "environment": tmp_path / "environment_manifest.json",
    }
    checkpoints: dict[str, str] = {}
    stats: dict[str, Path] = {}
    for primitive in ("dig", "carry", "dump", "return"):
        checkpoint = tmp_path / "ckpts" / primitive / "policy_best.ckpt"
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_bytes(f"{primitive}-checkpoint".encode())
        stats[primitive] = checkpoint.parent / "dataset_stats.pkl"
        stats[primitive].write_bytes(f"{primitive}-stats".encode())
        checkpoints[f"{primitive}_ckpt_path"] = str(checkpoint)
    prior = tmp_path / "prior.json"
    prior.write_text("{}\n", encoding="utf-8")
    config = {
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
            **checkpoints,
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
            "act_params": {"chunk_size": 100},
            "switch": {
                "return_max_steps": 420,
                "dig_bad_replan_max_steps": 220,
            },
        },
    }
    paths["config"].parent.mkdir(parents=True, exist_ok=True)
    paths["config"].write_text(yaml.safe_dump(config), encoding="utf-8")
    paths["rollout"].parent.mkdir(parents=True, exist_ok=True)
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
    contact = tmp_path / "WorktoolWallContactDetail.cs"
    for path in (scene, normalization, contact):
        path.write_text(path.name, encoding="utf-8")
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
                    "contact_lineage_files": [artifact_ref(contact)],
                    "contact_lineage_aggregate_sha256": "a" * 64,
                }
            }
        },
    )
    return paths, stats


def _prepare(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Path]]:
    paths, stats = _source_fixture(tmp_path)
    manifest = probe.prepare_wall_contact_rollout_probe(
        source_config_path=paths["config"],
        source_rollout_path=paths["rollout"],
        source_summary_path=paths["summary"],
        source_reset_validation_path=paths["reset"],
        environment_manifest_path=paths["environment"],
        output_root=tmp_path / "probe",
    )
    return manifest, stats


def test_source_lock_covers_stats_and_act_execution_code(tmp_path: Path) -> None:
    manifest, stats = _prepare(tmp_path)

    locked_stats = manifest["source_lock"]["dataset_stats"]
    assert set(locked_stats) == {"dig", "carry", "dump", "return"}
    assert {
        primitive: Path(reference["path"])
        for primitive, reference in locked_stats.items()
    } == stats
    runtime_paths = {
        str(Path(reference["path"]).relative_to(Path.cwd()))
        for reference in manifest["source_lock"]["runtime_code"]
    }
    assert {
        "testbed/data/schema.py",
        "testbed/planner/box_emptying/bottom_contact_detail.py",
        "testbed/planner/box_emptying/contact_ownership.py",
        "testbed/policies/act/adapter.py",
        "testbed/runtime/_eval.py",
        "testbed/cli/eval.py",
        "testbed/eval/wall_contact_rollout_safety_evidence.py",
        "testbed/eval/wall_contact_rollout_integrity.py",
        "testbed/eval/wall_contact_rollout_probe.py",
        "testbed/cli/wall_contact_rollout_probe.py",
    } <= runtime_paths

    stats["dig"].write_bytes(b"drift")
    with pytest.raises(
        probe.WallContactRolloutDiagnosticError,
        match="artifact_drift:dig_dataset_stats",
    ):
        probe.validate_wall_contact_rollout_probe(manifest["manifest_path"])


def _execution_fixture(
    tmp_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    run_root = tmp_path / "run"
    run_root.mkdir()
    manifest_path = tmp_path / "manifest.json"
    configured = ["python", "-m", "testbed.cli.eval"]
    manifest = {
        "manifest_path": str(manifest_path),
        "run_root": str(run_root),
        "command_argv": configured,
    }
    _write_json(manifest_path, manifest)
    log_path = run_root / "eval_process.log"
    log_path.write_text("log\n", encoding="utf-8")
    marker_path = run_root / "attempt_started.json"
    marker = {
        "schema": probe.PROBE_START_SCHEMA,
        "attempt_id": probe.PROBE_ATTEMPT_ID,
        "seed": probe.PROBE_SEED,
        "retry_count": 0,
        "manifest": artifact_ref(manifest_path),
        "configured_argv": configured,
        "executed_argv": runtime_command(configured),
    }
    _write_json(marker_path, marker)
    execution = {
        "schema": probe.PROBE_EXECUTION_SCHEMA,
        "attempt_id": probe.PROBE_ATTEMPT_ID,
        "seed": probe.PROBE_SEED,
        "retry_count": 0,
        "attempt_started": artifact_ref(marker_path),
        "process_log": artifact_ref(log_path),
    }
    return marker, execution, manifest


@pytest.mark.parametrize(
    ("record", "field"),
    [
        ("marker_manifest", "sha256"),
        ("marker_argv", "executed_argv"),
        ("execution_marker", "sha256"),
        ("execution_log", "sha256"),
    ],
)
def test_execution_validation_rejects_artifact_or_argv_drift(
    tmp_path: Path,
    record: str,
    field: str,
) -> None:
    marker, execution, manifest = _execution_fixture(tmp_path)
    _validate_execution(marker, execution, manifest)
    if record == "marker_manifest":
        marker["manifest"][field] = "0" * 64
    elif record == "marker_argv":
        marker[field] = ["python", "-m", "wrong.cli"]
    elif record == "execution_marker":
        execution["attempt_started"][field] = "0" * 64
    else:
        execution["process_log"][field] = "0" * 64

    with pytest.raises(
        probe.WallContactRolloutDiagnosticError,
        match="attempt_execution_lineage_invalid",
    ):
        _validate_execution(marker, execution, manifest)


def _validate_execution(
    marker: dict[str, Any],
    execution: dict[str, Any],
    manifest: dict[str, Any],
) -> None:
    validate_execution_lineage(
        marker,
        execution,
        manifest,
        start_schema=probe.PROBE_START_SCHEMA,
        execution_schema=probe.PROBE_EXECUTION_SCHEMA,
        attempt_id=probe.PROBE_ATTEMPT_ID,
        seed=probe.PROBE_SEED,
    )


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        ("hdf5", "unexpected_hdf5_artifact"),
        ("jsonl", "rollout_jsonl_invalid"),
        ("summary", "JSONDecodeError"),
    ],
)
def test_collection_persists_non_overwritable_failed_report(
    tmp_path: Path,
    failure: str,
    expected: str,
) -> None:
    manifest, _ = _prepare(tmp_path)
    run_root = Path(manifest["run_root"])

    def executor(command: list[str], cwd: Path, log_path: Path) -> int:
        del command, cwd, log_path
        results = run_root / "results"
        rollouts = results / "rollouts"
        rollouts.mkdir(parents=True)
        if failure == "hdf5":
            (results / "unexpected.hdf5").write_bytes(b"forbidden")
            return 0
        (rollouts / "rollout_000.jsonl").write_text(
            "{broken\n" if failure == "jsonl" else "{}\n",
            encoding="utf-8",
        )
        (rollouts / "rollout_000_summary.json").write_text(
            "{broken\n" if failure == "summary" else "{}\n",
            encoding="utf-8",
        )
        Path(results / "eval_resolved_config.yaml").write_text(
            Path(manifest["config_path"]).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        return 0

    report = probe.run_wall_contact_rollout_probe(
        manifest_path=manifest["manifest_path"],
        executor=executor,
        cwd=tmp_path,
    )

    assert report["status"] == "failed"
    assert report["outcome"] == "attempt_failed"
    assert any(expected in blocker for blocker in report["blockers"])
    assert (run_root / "report.json").is_file()
    with pytest.raises(FileExistsError):
        probe.collect_wall_contact_rollout_probe(
            manifest_path=manifest["manifest_path"]
        )
