from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from testbed.eval.wall_contact_artifact_io import artifact_ref
from testbed.eval.wall_contact_session_gap_evidence import (
    build_session_gap_report,
)
from testbed.eval.wall_contact_session_gap_probe import (
    PROBE_ATTEMPT_ID,
    PROBE_SCHEMA,
    WallContactSessionGapProbeError,
    prepare_wall_contact_session_gap_probe,
    run_wall_contact_session_gap_probe,
    validate_wall_contact_session_gap_probe,
)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _source_fixture(tmp_path: Path) -> tuple[Path, Path]:
    source_run = tmp_path / "source_run"
    raw = source_run / "results" / "rollouts" / "rollout_000.jsonl"
    summary = source_run / "results" / "rollouts" / "rollout_000_summary.json"
    raw.parent.mkdir(parents=True)
    raw.write_text("{}\n", encoding="utf-8")
    _write_json(summary, {"rollout_stop_reason": "box_safety:repeat"})
    reset_state = {
        "qpos": [0.5, 0.26, 0.69, 0.35],
        "qvel": [0.0, 0.02, -0.03, -0.04],
        "bucket_tip_m": [-0.29, 0.06, -0.32],
        "terrain_depth_m": [0.0] * 6,
        "remaining_mass_kg": 7407.0,
    }
    expected_reset_path = (
        tmp_path
        / "source_lock"
        / "ab_lineage"
        / "expected_reset_state.json"
    )
    _write_json(
        expected_reset_path,
        {
            "schema": "wall_contact_expected_reset_state_v1",
            "checkpoint_semantics": "first_post_reset_control_step",
            **copy.deepcopy(reset_state),
        },
    )
    expected_reset_sha = artifact_ref(expected_reset_path)["sha256"]
    checkpoint_paths: dict[str, str] = {}
    for primitive in ("dig", "carry", "dump", "return"):
        checkpoint = tmp_path / "ckpts" / f"{primitive}.ckpt"
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_text(primitive, encoding="utf-8")
        checkpoint_paths[f"{primitive}_ckpt_path"] = str(checkpoint)

    source_config = tmp_path / "seed_2_B.yaml"
    config = {
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
            "video_dir": str(source_run / "videos"),
            "results_dir": str(source_run / "results"),
            "save_rollout_logs": True,
            "stream_rollout_logs": True,
            "rollout_log_dir": str(source_run / "results" / "rollouts"),
            "record_hdf5": False,
            "hdf5_dir": str(source_run / "disabled_hdf5"),
            "target_cycle_gate": 2,
            "target_cycle_gate_terminal_hold_steps": 0,
            "seed": 2,
            "record_hdf5_metadata": {
                "validation_schema": "wall_contact_paired_ab_attempt_v1",
                "contact_semantics_condition": "B",
                "contact_semantics_pair_id": "seed_2",
                "contact_semantics_attempt_id": "seed_2_B",
                "contact_semantics_sequence_index": 6,
                "contact_semantics_reset_seed": 2,
                "diagnostic_only": True,
                "promotion_eligible": False,
                "frozen_target_handoff_sha256": "c" * 64,
                "expected_reset_state_sha256": expected_reset_sha,
            },
        },
        "policy": {
            **checkpoint_paths,
            "dig_cut_planner": {
                "coverage": {
                    "actual_tuple_execution_library": {
                        "runtime_role": "diagnostic_legacy"
                    }
                }
            },
            "box_emptying": {
                "safety": {
                    "wall_contact_diagnostic_ab_enabled": True,
                    "wall_first_touch_mode": "record_bucket_first_session",
                },
                "bounded_dig_probe_stop": {
                    "enabled": False,
                    "diagnostic_only": True,
                },
                "functional_cycle_gate": {"enabled": False},
                "contact_semantics_one_cycle_validator": {
                    "enabled": True,
                    "diagnostic_only": True,
                    "target_exemplar_id": "episode_168",
                    "stop_on": [
                        "target_dump_complete",
                        "safety_terminal",
                    ],
                },
            },
        },
    }
    source_config.write_text(
        yaml.safe_dump(config, sort_keys=False),
        encoding="utf-8",
    )

    source_attempt = tmp_path / "seed_2_B.json"
    _write_json(
        source_attempt,
        {
            "schema": "wall_contact_paired_ab_attempt_v1",
            "status": "passed",
            "attempt_id": "seed_2_B",
            "seed": 2,
            "condition": "B",
            "retry_count": 0,
            "selected_exemplar_id": "episode_168",
            "selected_raw_fields_sha256": (
                "c167e087f3d41f6db8fe0ad260d5f72c"
                "3440b6fab9115fdf55959feacc50991c"
            ),
            "reset_checkpoint_semantics": "first_post_reset_control_step",
            "reset_state": copy.deepcopy(reset_state),
            "source_lock": {
                "rollout_jsonl": artifact_ref(raw),
                "rollout_summary": artifact_ref(summary),
            },
        },
    )
    return source_config, source_attempt


def test_prepare_is_a_fresh_one_factor_seed_2_probe(tmp_path: Path) -> None:
    source_config, source_attempt = _source_fixture(tmp_path)
    root = tmp_path / "wall_contact_session_gap_diagnostic_b2_v1"

    manifest = prepare_wall_contact_session_gap_probe(
        source_config_path=source_config,
        source_attempt_path=source_attempt,
        output_root=root,
    )

    assert manifest["schema"] == PROBE_SCHEMA
    assert manifest["status"] == "prepared"
    assert manifest["attempt_id"] == PROBE_ATTEMPT_ID
    assert manifest["seed"] == 2
    assert manifest["retry_allowed"] is False
    assert manifest["max_attempts"] == 1
    assert manifest["diagnostic_only"] is True
    assert manifest["non_promotable"] is True
    assert manifest["production_promotion_allowed"] is False
    assert manifest["downstream_gates"] == {
        "contact_budget_freeze_allowed": False,
        "continuous_predictor_allowed": False,
        "offline_e0_g1_w1_allowed": False,
        "bounded_live_allowed": False,
        "functional_1x10_allowed": False,
    }
    assert manifest["runtime_semantic_diff"] == [
        {
            "path": (
                "policy.box_emptying.safety."
                "wall_contact_session_end_clear_ticks"
            ),
            "source_effective": 1,
            "probe": 2,
        }
    ]
    assert manifest["source_lock"]["baseline_rollout_jsonl"]["sha256"]
    assert manifest["source_lock"]["expected_reset_state"]["sha256"]
    assert set(manifest["source_lock"]["checkpoints"]) == {
        "dig",
        "carry",
        "dump",
        "return",
    }
    assert (
        manifest["source_lock"]["original_environment"]["status"]
        == "not_available"
    )
    assert manifest["target_lineage"]["exemplar_id"] == "episode_168"
    assert (
        manifest["reset_lineage"]["checkpoint_semantics"]
        == "first_post_reset_control_step"
    )

    config_path = Path(manifest["config_path"])
    probe = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert probe["eval"]["seed"] == 2
    assert probe["eval"]["num_rollouts"] == 1
    assert probe["eval"]["target_cycle_gate"] == 2
    assert probe["eval"]["record_hdf5"] is False
    assert (
        probe["policy"]["box_emptying"]["safety"][
            "wall_contact_session_end_clear_ticks"
        ]
        == 2
    )
    assert (
        probe["eval"]["record_hdf5_metadata"][
            "contact_semantics_attempt_id"
        ]
        == PROBE_ATTEMPT_ID
    )
    validate_wall_contact_session_gap_probe(root / "manifest.json")

    with pytest.raises(FileExistsError):
        prepare_wall_contact_session_gap_probe(
            source_config_path=source_config,
            source_attempt_path=source_attempt,
            output_root=root,
        )


def test_validation_rejects_any_second_runtime_semantic_change(
    tmp_path: Path,
) -> None:
    source_config, source_attempt = _source_fixture(tmp_path)
    root = tmp_path / "probe"
    manifest = prepare_wall_contact_session_gap_probe(
        source_config_path=source_config,
        source_attempt_path=source_attempt,
        output_root=root,
    )
    config_path = Path(manifest["config_path"])
    probe = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    probe["policy"]["box_emptying"]["safety"]["wall_high_force_n"] = 99_999.0
    config_path.write_text(
        yaml.safe_dump(probe, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(
        WallContactSessionGapProbeError,
        match="probe_config_(artifact|lineage)_drift",
    ):
        validate_wall_contact_session_gap_probe(root / "manifest.json")


def test_run_marks_before_calling_eval_and_refuses_a_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_config, source_attempt = _source_fixture(tmp_path)
    root = tmp_path / "probe"
    manifest = prepare_wall_contact_session_gap_probe(
        source_config_path=source_config,
        source_attempt_path=source_attempt,
        output_root=root,
    )
    calls: list[list[str]] = []

    def fake_executor(command: list[str], cwd: Path, log_path: Path) -> int:
        calls.append(command)
        assert (root / "run" / "attempt_started.json").is_file()
        rollout_dir = root / "run" / "results" / "rollouts"
        rollout_dir.mkdir(parents=True)
        (rollout_dir / "rollout_000.jsonl").write_text(
            "{}\n",
            encoding="utf-8",
        )
        _write_json(
            rollout_dir / "rollout_000_summary.json",
            {"rollout_stop_reason": "box_safety:stuck"},
        )
        return 0

    extracted = {
        "schema": "wall_contact_paired_ab_attempt_v1",
        "status": "passed",
        "blockers": [],
        "attempt_id": PROBE_ATTEMPT_ID,
        "seed": 2,
        "condition": "B",
        "retry_count": 0,
        "process_returncode": 0,
        "reset_checkpoint_semantics": "first_post_reset_control_step",
        "reset_state": {
            "qpos": [0.5, 0.26, 0.69, 0.35],
            "qvel": [0.0, 0.02, -0.03, -0.04],
            "bucket_tip_m": [-0.29, 0.06, -0.32],
            "terrain_depth_m": [0.0] * 6,
            "remaining_mass_kg": 7407.0,
        },
        "selected_exemplar_id": "episode_168",
        "selected_raw_fields_sha256": (
            "c167e087f3d41f6db8fe0ad260d5f72c"
            "3440b6fab9115fdf55959feacc50991c"
        ),
        "target_cycle_index": 1,
        "entered_carry": False,
        "dump_completed": False,
        "target_dump_completed": False,
        "terminal_reason": "box_safety:stuck",
        "hard_stop_violations": ["stuck"],
        "hard_violation": True,
        "debug_lineage_valid_every_tick": True,
        "diagnostic_only": True,
        "non_promotable": True,
        "writes_training_hdf5": False,
        "source_lock": {},
    }
    monkeypatch.setattr(
        "testbed.eval.wall_contact_session_gap_probe."
        "extract_paired_ab_attempt",
        lambda **_: copy.deepcopy(extracted),
    )

    report = run_wall_contact_session_gap_probe(
        manifest_path=Path(manifest["manifest_path"]),
        executor=fake_executor,
        cwd=tmp_path,
    )

    assert len(calls) == 1
    assert calls[0][1:3] == ["-m", "testbed.cli.eval"]
    assert calls[0][-6:] == [
        "--num-rollouts",
        "1",
        "--target-cycle-gate",
        "2",
        "--output-dir",
        str(root / "run"),
    ]
    assert report["status"] == "passed"
    assert report["outcome"] == "inconclusive"
    assert report["entered_carry"] is False
    assert report["dump_completed"] is False
    assert report["terminal_reason"] == "box_safety:stuck"
    assert report["reset_fairness"]["passed"] is True
    assert (
        report["reset_fairness"]["compared_against_frozen_expected"] is True
    )
    assert (
        report["reset_fairness"]["compared_against_source_seed_2_b"] is True
    )
    assert report["physical_contact_sessions"]["count"] == 0
    assert report["logical_contact_sessions"]["count"] == 0
    assert report["retry_count"] == 0
    assert report["executed_attempt_count"] == 1
    assert report["diagnostic_only"] is True
    assert report["non_promotable"] is True
    assert report["production_promotion_allowed"] is False
    assert all(value is False for value in report["downstream_gates"].values())

    with pytest.raises(FileExistsError, match="already started"):
        run_wall_contact_session_gap_probe(
            manifest_path=Path(manifest["manifest_path"]),
            executor=fake_executor,
            cwd=tmp_path,
        )
    assert len(calls) == 1


def test_report_requires_exercised_bridge_and_complete_dump(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "manifest.json"
    attempt_path = tmp_path / "attempt.json"
    _write_json(manifest_path, {"artifact": "manifest"})
    _write_json(attempt_path, {"artifact": "attempt"})
    reset = {
        "qpos": [0.5, 0.26, 0.69, 0.35],
        "qvel": [0.0, 0.02, -0.03, -0.04],
        "bucket_tip_m": [-0.29, 0.06, -0.32],
        "terrain_depth_m": [0.0] * 6,
        "remaining_mass_kg": 7407.0,
    }
    source_ref = {"path": "locked", "sha256": "a" * 64, "size_bytes": 1}
    manifest = {
        "manifest_path": str(manifest_path),
        "reset_lineage": {"source_reset_state": copy.deepcopy(reset)},
        "baseline_outcome": {},
        "source_lock": {
            "baseline_config": source_ref,
            "baseline_attempt": source_ref,
            "baseline_rollout_jsonl": source_ref,
            "expected_reset_state": source_ref,
        },
    }
    attempt = {
        "status": "passed",
        "blockers": [],
        "reset_state": copy.deepcopy(reset),
        "selected_exemplar_id": "episode_168",
        "selected_raw_fields_sha256": (
            "c167e087f3d41f6db8fe0ad260d5f72c"
            "3440b6fab9115fdf55959feacc50991c"
        ),
        "entered_carry": True,
        "dump_completed": True,
        "contact_ended_before_carry": True,
        "hard_violation": False,
        "hard_stop_violations": [],
    }
    evidence = {
        "status": "passed",
        "single_tick_rollover_bridge_observed": True,
        "physical_contact_sessions": {"count": 2, "sessions": []},
        "logical_contact_sessions": {"count": 1, "sessions": []},
        "contact_free_gaps": [{"contact_free_tick_count": 1}],
    }

    report = build_session_gap_report(
        manifest=manifest,
        attempt=attempt,
        attempt_path=attempt_path,
        contact_evidence=evidence,
        expected_reset=reset,
        report_schema="wall_contact_session_gap_probe_report_v1",
        attempt_id=PROBE_ATTEMPT_ID,
        seed=2,
        clear_ticks_required=2,
        target_exemplar_id="episode_168",
        target_raw_fields_sha256=attempt[
            "selected_raw_fields_sha256"
        ],
        downstream_gates={
            "contact_budget_freeze_allowed": False,
        },
    )

    assert report["outcome"] == "single_clear_tick_split_supported"
    assert report["contact_ended_before_carry"] is True
    assert report["physical_contact_sessions"]["count"] == 2
    assert report["logical_contact_sessions"]["count"] == 1
