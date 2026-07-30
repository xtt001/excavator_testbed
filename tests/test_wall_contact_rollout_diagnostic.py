from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import yaml

from testbed.data.schema import ENV_STATE_V2_4_DIM
from testbed.eval.wall_contact_artifact_io import artifact_ref
from testbed.eval.wall_contact_rollout_diagnostic import (
    WallContactRolloutDiagnosticError,
    build_wall_contact_rollout_report,
)
from testbed.eval.wall_contact_rollout_probe import (
    PROBE_ATTEMPT_ID,
    PROBE_SCHEMA,
    prepare_wall_contact_rollout_probe,
    run_wall_contact_rollout_probe,
    validate_wall_contact_rollout_probe,
)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def _pair(
    *,
    wall: str,
    normal_force_n: float,
    total_force_n: float,
    tangential_displacement_m: float,
) -> dict[str, Any]:
    return {
        "component": "bucket",
        "machine_shape_path": "Machine/bucket/shape",
        "wall_name": wall,
        "wall_shape_path": f"DigArea/{wall}/shape",
        "callback_count": 1,
        "contact_point_count": 1,
        "max_normal_force_n": normal_force_n,
        "max_tangential_force_n": max(
            0.0,
            total_force_n - normal_force_n,
        ),
        "max_total_force_n": total_force_n,
        "contact_points_world_m": [[1.0, 2.0, 3.0]],
        "representative_contact_point_component_local_m": [0.1, 0.2, 0.3],
        "tangential_displacement_m": tangential_displacement_m,
    }


def _contact_warning(
    *,
    step: int,
    session: int,
    consecutive: int,
    impulse_n_s: float,
    pair: dict[str, Any],
) -> str:
    payload = {
        "schema": "worktool_wall_contact_detail_v1",
        "step_id": step,
        "sim_time_s": step * 0.02,
        "delta_time_s": 0.02,
        "session_id": session,
        "session_count": session,
        "consecutive_contact_steps": consecutive,
        "session_duration_s": consecutive * 0.02,
        "session_normal_impulse_n_s": impulse_n_s,
        "parts": ["bucket"],
        "walls": [pair["wall_name"]],
        "pairs": [pair],
    }
    return "worktool_wall_contact_detail_v1:" + json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
    )


def _row(
    *,
    step: int,
    cycle: int,
    skill: str,
    qpos: list[float] | None = None,
    bucket_tip: list[float] | None = None,
    contact: dict[str, Any] | None = None,
    dump: bool = False,
    reason: str = "",
    awaiting: bool = False,
    acknowledged: bool = False,
    terminal: bool = False,
) -> dict[str, Any]:
    env = np.zeros(ENV_STATE_V2_4_DIM, dtype=np.float32)
    env[28:31] = np.asarray(bucket_tip or [0.0, 0.0, 0.0])
    warnings: list[str] = []
    diagnostic_allowed = False
    if contact is not None:
        env[101] = 1.0
        env[102] = float(contact["normal_force_n"])
        env[103] = float(contact["session"])
        warnings = [
            _contact_warning(
                step=step,
                session=int(contact["session"]),
                consecutive=int(contact["consecutive"]),
                impulse_n_s=float(contact["impulse_n_s"]),
                pair=contact["pair"],
            )
        ]
        diagnostic_allowed = True
    return {
        "step_id": step,
        "t": step - 1,
        "sim_time_ns": step * 20_000_000,
        "primitive_cycle_index": cycle,
        "cycle_id": cycle,
        "skill_name": skill,
        "dump_end_mask": int(dump),
        "qpos": list(qpos or [0.0, 0.0, 0.0, 0.0]),
        "qvel": [0.0, 0.0, 0.0, 0.0],
        "action": (
            [0.0, 0.0, 0.0, 0.0]
            if awaiting or acknowledged or terminal
            else [0.2, -0.2, 0.2, -0.2]
        ),
        "env_state": env.tolist(),
        "warnings": warnings,
        "box_safety_reason": reason,
        "box_safety_terminal": terminal,
        "box_safety_awaiting_neutral_ack": awaiting,
        "box_safety_neutral_acknowledged": acknowledged,
        "box_safety_replan": False,
        "box_safety_blocked_corridor_id": -1,
        "box_safety_policy_restarted": False,
        "box_safety_contact_kind": (
            "none" if not reason else "none"
        ),
        "box_safety_wall_contact_diagnostic_allowed": diagnostic_allowed,
        "box_safety_wall_contact_diagnostic_ab_enabled": False,
        "box_safety_wall_contact_diagnostic_observe_only_enabled": True,
        "box_safety_wall_first_touch_mode": (
            "record_bucket_all_contacts"
        ),
        "transition_timeout": False,
        "pre_dig_align_timeout_count": 0,
    }


def _diagnostic_rows() -> list[dict[str, Any]]:
    first_pair = _pair(
        wall="Dig_XMin_Board",
        normal_force_n=3.0,
        total_force_n=5.0,
        tangential_displacement_m=0.0,
    )
    second_pair = _pair(
        wall="Dig_XMin_Board",
        normal_force_n=4.0,
        total_force_n=7.0,
        tangential_displacement_m=0.012,
    )
    third_pair = _pair(
        wall="Dig_ZMax_Board",
        normal_force_n=8.0,
        total_force_n=11.0,
        tangential_displacement_m=0.0,
    )
    return [
        _row(step=1, cycle=0, skill="dig"),
        _row(
            step=2,
            cycle=0,
            skill="dig",
            qpos=[0.0, 0.0, 0.0, 0.0],
            bucket_tip=[0.0, 0.0, 0.0],
            contact={
                "session": 1,
                "consecutive": 1,
                "impulse_n_s": 0.06,
                "normal_force_n": 3.0,
                "pair": first_pair,
            },
        ),
        _row(
            step=3,
            cycle=0,
            skill="dig",
            qpos=[0.006, 0.0, 0.0, 0.0],
            bucket_tip=[0.01, 0.0, 0.0],
            contact={
                "session": 1,
                "consecutive": 2,
                "impulse_n_s": 0.14,
                "normal_force_n": 4.0,
                "pair": second_pair,
            },
        ),
        _row(step=4, cycle=0, skill="carry"),
        _row(step=5, cycle=0, skill="dump", dump=True),
        _row(step=6, cycle=0, skill="return"),
        _row(step=7, cycle=1, skill="dig"),
        _row(
            step=8,
            cycle=1,
            skill="dig",
            contact={
                "session": 2,
                "consecutive": 1,
                "impulse_n_s": 0.16,
                "normal_force_n": 8.0,
                "pair": third_pair,
            },
        ),
        _row(
            step=9,
            cycle=1,
            skill="dig",
            reason="stuck_50_steps",
            awaiting=True,
        ),
        _row(
            step=10,
            cycle=1,
            skill="dig",
            reason="stuck_50_steps",
            acknowledged=True,
            terminal=True,
        ),
    ]


def test_report_records_per_shovel_force_impulse_and_motion() -> None:
    report = build_wall_contact_rollout_report(
        rows=_diagnostic_rows(),
        summary={
            "rollout_stop_reason": "box_safety:stuck_50_steps",
            "target_cycle_completed_dump_count": 1,
        },
        max_shovels=10,
    )

    assert report["status"] == "passed"
    assert report["outcome"] == "hard_safety_stop_before_10"
    assert report["started_shovel_count"] == 2
    assert report["completed_dump_count"] == 1
    assert report["partial_shovel_count"] == 1
    first = report["shovels"][0]
    assert first["components"] == ["bucket"]
    assert first["walls"] == ["Dig_XMin_Board"]
    assert first["contact_tick_count"] == 2
    assert first["peak_total_force_n"] == pytest.approx(7.0)
    assert first["rms_of_step_peak_total_force_n"] == pytest.approx(
        math.sqrt((25.0 + 49.0) / 2.0)
    )
    assert first["normal_impulse_n_s"] == pytest.approx(0.14)
    assert first["contact_duration_s"] == pytest.approx(0.04)
    assert first["motion_progress_observed"] is True
    assert first["motion"]["qpos_max_axis_range"] == pytest.approx(0.006)
    assert first["motion"]["bucket_tip_max_displacement_m"] == pytest.approx(
        0.01
    )
    assert first["motion"]["max_tangential_displacement_m"] == pytest.approx(
        0.012
    )
    second = report["shovels"][1]
    assert second["dump_completed"] is False
    assert second["motion_progress_observed"] is False
    assert report["terminal_neutral"]["acknowledged"] is True


def test_report_rejects_any_side_effect_on_allowed_bucket_contact() -> None:
    rows = _diagnostic_rows()
    rows[2]["box_safety_replan"] = True

    with pytest.raises(
        WallContactRolloutDiagnosticError,
        match="observe_only_contact_side_effect",
    ):
        build_wall_contact_rollout_report(
            rows=rows,
            summary={
                "rollout_stop_reason": "box_safety:stuck_50_steps",
                "target_cycle_completed_dump_count": 1,
            },
            max_shovels=10,
        )


def test_report_accepts_live_post_step_contact_decision_alignment() -> None:
    rows = _diagnostic_rows()[:6]
    rows[1]["box_safety_wall_contact_diagnostic_allowed"] = False
    rows[2]["box_safety_wall_contact_diagnostic_allowed"] = True
    rows[3]["box_safety_wall_contact_diagnostic_allowed"] = True

    report = build_wall_contact_rollout_report(
        rows=rows,
        summary={
            "rollout_stop_reason": "episode_limit",
            "target_cycle_completed_dump_count": 1,
            # This lifecycle-derived counter can lag the direct dump pulse.
            "completed_dump_count": 0,
        },
        max_shovels=10,
    )

    assert report["status"] == "passed"
    assert report["outcome"] == "inconclusive"
    assert report["completed_dump_count"] == 1
    assert report["side_effect_free_allowed_contact_every_tick"] is True


def test_low_force_wall_contact_can_overlap_independent_timeout_chain() -> None:
    pair = _pair(
        wall="Dig_ZMin_Board",
        normal_force_n=31_000.0,
        total_force_n=31_100.0,
        tangential_displacement_m=0.02,
    )
    rows = [_row(step=1, cycle=0, skill="return")]
    for step, impulse in ((2, 620.0), (3, 1240.0), (4, 1860.0), (5, 2480.0)):
        rows.append(
            _row(
                step=step,
                cycle=0,
                skill="return",
                contact={
                    "session": 1,
                    "consecutive": step - 1,
                    "impulse_n_s": impulse,
                    "normal_force_n": 31_000.0,
                    "pair": pair,
                },
                reason="timeout" if step >= 4 else "",
                awaiting=step == 4,
                acknowledged=step == 5,
                terminal=step == 5,
            )
        )
    # Live JSONL sidecars describe the post-step observation, so the first
    # contact is adjudicated on the next row.  The final ordinary contact can
    # likewise be followed immediately by an independently owned timeout.
    for row in (rows[1], *rows[-2:]):
        row["box_safety_wall_contact_diagnostic_allowed"] = False

    report = build_wall_contact_rollout_report(
        rows=rows,
        summary={
            "rollout_stop_reason": "box_safety:timeout",
            "target_cycle_completed_dump_count": 0,
        },
        max_shovels=10,
    )

    assert report["status"] == "passed"
    assert report["completed_dump_count"] == 0
    assert report["contact_tick_count"] == 4
    assert report["side_effect_free_allowed_contact_every_tick"] is True


def test_independent_timeout_does_not_hide_prior_contact_side_effect() -> None:
    pair = _pair(
        wall="Dig_ZMin_Board",
        normal_force_n=31_000.0,
        total_force_n=31_100.0,
        tangential_displacement_m=0.02,
    )
    rows = [
        _row(step=1, cycle=0, skill="return"),
        _row(
            step=2,
            cycle=0,
            skill="return",
            contact={
                "session": 1,
                "consecutive": 1,
                "impulse_n_s": 620.0,
                "normal_force_n": 31_000.0,
                "pair": pair,
            },
        ),
        _row(step=3, cycle=0, skill="return"),
        _row(
            step=4,
            cycle=0,
            skill="return",
            contact={
                "session": 2,
                "consecutive": 1,
                "impulse_n_s": 620.0,
                "normal_force_n": 31_000.0,
                "pair": pair,
            },
        ),
    ]
    rows[1]["box_safety_wall_contact_diagnostic_allowed"] = False
    rows[2]["box_safety_wall_contact_diagnostic_allowed"] = True
    rows[3]["box_safety_replan"] = True
    rows.extend(
        [
            _row(
                step=5,
                cycle=0,
                skill="return",
                reason="timeout",
                awaiting=True,
            ),
            _row(
                step=6,
                cycle=0,
                skill="return",
                reason="timeout",
                acknowledged=True,
                terminal=True,
            ),
        ]
    )

    with pytest.raises(
        WallContactRolloutDiagnosticError,
        match="observe_only_contact_side_effect",
    ):
        build_wall_contact_rollout_report(
            rows=rows,
            summary={
                "rollout_stop_reason": "box_safety:timeout",
                "target_cycle_completed_dump_count": 0,
            },
            max_shovels=10,
        )


def test_high_force_latches_for_remaining_ticks_of_same_session() -> None:
    forces = (117_717.805, 80_685.05, 82_179.5859)
    impulses = (2_354.356, 3_968.057, 5_611.64844)
    rows = [_row(step=1, cycle=0, skill="carry")]
    for offset, (force_n, impulse_n_s) in enumerate(
        zip(forces, impulses, strict=True),
        start=2,
    ):
        rows.append(
            _row(
                step=offset,
                cycle=0,
                skill="carry",
                contact={
                    "session": 1,
                    "consecutive": offset - 1,
                    "impulse_n_s": impulse_n_s,
                    "normal_force_n": force_n,
                    "pair": _pair(
                        wall="Dig_ZMin_Board",
                        normal_force_n=force_n,
                        total_force_n=force_n,
                        tangential_displacement_m=0.0,
                    ),
                },
                reason=(
                    "wall_contact_high_force" if offset >= 3 else ""
                ),
                awaiting=offset == 3,
                acknowledged=offset == 4,
                terminal=offset == 4,
            )
        )
    for row in rows[1:]:
        row["box_safety_wall_contact_diagnostic_allowed"] = False
    for row in rows[2:]:
        row["box_safety_contact_kind"] = "wall"
        row["box_safety_event_id"] = 1

    report = build_wall_contact_rollout_report(
        rows=rows,
        summary={
            "rollout_stop_reason": "box_safety:wall_contact_high_force",
            "target_cycle_completed_dump_count": 0,
        },
        max_shovels=10,
    )

    assert report["contact_tick_count"] == 3
    assert report["hard_stop_reasons"] == ["wall_contact_high_force"]
    terminal = report["terminal_neutral"]
    assert terminal["requested"] is True
    assert terminal["acknowledged"] is True
    assert terminal["terminal_observed"] is True
    assert terminal["reason"] == "wall_contact_high_force"
    assert terminal["request_step_id"] == 3
    assert terminal["ack_step_id"] == 4


def _source_fixture(
    tmp_path: Path,
) -> tuple[Path, Path, Path, Path, Path]:
    source_root = tmp_path / "baseline7"
    source_config = source_root / "results" / "eval_resolved_config.yaml"
    source_rollout = source_root / "results" / "rollouts" / "rollout_000.jsonl"
    source_summary = (
        source_root / "results" / "rollouts" / "rollout_000_summary.json"
    )
    reset_validation = (
        source_root / "validation_v1" / "validation_reset_000.json"
    )
    checkpoint_fields: dict[str, str] = {}
    for primitive in ("dig", "carry", "dump", "return"):
        path = tmp_path / "ckpts" / primitive / "policy_best.ckpt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(primitive, encoding="utf-8")
        (path.parent / "dataset_stats.pkl").write_bytes(primitive.encode())
        checkpoint_fields[f"{primitive}_ckpt_path"] = str(path)
    prior = tmp_path / "prior.json"
    prior.write_text("{}", encoding="utf-8")
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
            "save_video": True,
            "video_dir": str(source_root / "videos"),
            "results_dir": str(source_root / "results"),
            "save_rollout_logs": True,
            "stream_rollout_logs": True,
            "rollout_log_dir": str(source_root / "results" / "rollouts"),
            "record_hdf5": True,
            "hdf5_dir": str(source_root / "results" / "hdf5"),
            "target_cycle_gate": 10,
            "target_cycle_gate_terminal_hold_steps": 1,
            "temporal_agg": True,
        },
        "policy": {
            **checkpoint_fields,
            "dig_cut_planner": {
                "mode": "operator_prior_sweep_belief",
                "prior_path": str(prior),
            },
            "box_emptying": {
                "enabled": False,
                "safety_enabled": True,
                "safety": {
                    "wall_high_force_n": 100_000.0,
                    "stuck_action_l1_min": 0.1,
                    "stuck_window_steps": 50,
                    "stuck_qpos_max_change": 0.005,
                    "stuck_bucket_tip_max_displacement_m": 0.02,
                },
            },
            "act_params": {"chunk_size": 100},
            "switch": {
                "return_max_steps": 420,
                "dig_bad_replan_max_steps": 220,
            },
        },
    }
    source_config.parent.mkdir(parents=True, exist_ok=True)
    source_config.write_text(
        yaml.safe_dump(config, sort_keys=False),
        encoding="utf-8",
    )
    baseline_reset = _row(step=1, cycle=0, skill="dig")
    _write_jsonl(source_rollout, [baseline_reset])
    _write_json(
        source_summary,
        {
            "target_cycle_completed_dump_count": 7,
            "completed_dump_count": 7,
            "coverage_completed_dump_count": 7,
            "rollout_stop_reason": "box_safety:wall_contact_terminal",
        },
    )
    _write_json(
        reset_validation,
        {
            "schema": "act_functional_10cycle_validation_v1",
            "reset_id": "seed_1000",
            "completed_full_cycle_count": 7,
        },
    )
    scene = tmp_path / "scene.unity"
    normalization = tmp_path / "norm.json"
    contact_code = tmp_path / "WorktoolWallContactDetail.cs"
    for path, text in (
        (scene, "scene"),
        (normalization, "norm"),
        (contact_code, "code"),
    ):
        path.write_text(text, encoding="utf-8")
    environment_manifest = tmp_path / "environment_manifest.json"
    _write_json(
        environment_manifest,
        {
            "schema": "wall_contact_semantics_recovery_v1",
            "source_lock": {
                "unity": {
                    "scene_path": str(scene),
                    "scene_sha256": artifact_ref(scene)["sha256"],
                    "normalization_path": str(normalization),
                    "normalization_sha256": artifact_ref(normalization)[
                        "sha256"
                    ],
                    "contact_lineage_files": [artifact_ref(contact_code)],
                    "contact_lineage_aggregate_sha256": "a" * 64,
                }
            },
        },
    )
    return (
        source_config,
        source_rollout,
        source_summary,
        reset_validation,
        environment_manifest,
    )


def test_prepare_locks_seven_dump_baseline_and_one_runtime_semantic_delta(
    tmp_path: Path,
) -> None:
    (
        source_config,
        source_rollout,
        source_summary,
        reset_validation,
        environment_manifest,
    ) = _source_fixture(tmp_path)
    root = tmp_path / "wall_contact_observe_only_multicycle_diagnostic_v1"

    manifest = prepare_wall_contact_rollout_probe(
        source_config_path=source_config,
        source_rollout_path=source_rollout,
        source_summary_path=source_summary,
        source_reset_validation_path=reset_validation,
        environment_manifest_path=environment_manifest,
        output_root=root,
    )

    assert manifest["schema"] == PROBE_SCHEMA
    assert manifest["attempt_id"] == PROBE_ATTEMPT_ID
    assert manifest["max_attempts"] == 1
    assert manifest["retry_allowed"] is False
    assert manifest["max_shovels"] == 10
    assert manifest["baseline_outcome"]["completed_dump_count"] == 7
    generated = yaml.safe_load(Path(manifest["config_path"]).read_text())
    assert generated["eval"]["target_cycle_gate"] == 10
    assert generated["eval"]["record_hdf5"] is False
    safety = generated["policy"]["box_emptying"]["safety"]
    assert safety["wall_first_touch_mode"] == "record_bucket_all_contacts"
    assert safety["wall_contact_diagnostic_observe_only_enabled"] is True
    assert safety["wall_contact_diagnostic_ab_enabled"] is False
    assert safety["wall_high_force_n"] == 100_000.0
    assert validate_wall_contact_rollout_probe(
        root / "manifest.json"
    ) == manifest
    with pytest.raises(FileExistsError):
        prepare_wall_contact_rollout_probe(
            source_config_path=source_config,
            source_rollout_path=source_rollout,
            source_summary_path=source_summary,
            source_reset_validation_path=reset_validation,
            environment_manifest_path=environment_manifest,
            output_root=root,
        )


def test_run_once_writes_marker_before_executor_and_cannot_retry(
    tmp_path: Path,
) -> None:
    (
        source_config,
        source_rollout,
        source_summary,
        reset_validation,
        environment_manifest,
    ) = _source_fixture(tmp_path)
    root = tmp_path / "probe"
    manifest = prepare_wall_contact_rollout_probe(
        source_config_path=source_config,
        source_rollout_path=source_rollout,
        source_summary_path=source_summary,
        source_reset_validation_path=reset_validation,
        environment_manifest_path=environment_manifest,
        output_root=root,
    )
    calls: list[list[str]] = []

    def executor(command: list[str], cwd: Path, log_path: Path) -> int:
        del cwd
        calls.append(command)
        assert (root / "run" / "attempt_started.json").is_file()
        log_path.write_text("executed\n", encoding="utf-8")
        results = root / "run" / "results" / "rollouts"
        _write_jsonl(results / "rollout_000.jsonl", _diagnostic_rows())
        _write_json(
            results / "rollout_000_summary.json",
            {
                "rollout_stop_reason": "box_safety:stuck_50_steps",
                "target_cycle_completed_dump_count": 1,
            },
        )
        resolved = yaml.safe_load(
            Path(manifest["config_path"]).read_text(encoding="utf-8")
        )
        resolved_eval = resolved["eval"]
        resolved_eval.update(
            {
                "results_dir": str(root / "run" / "results"),
                "video_dir": str(root / "run" / "videos"),
                "rollout_log_dir": str(results),
                "hdf5_dir": str(
                    root / "run" / "results" / "hdf5_rollouts"
                ),
            }
        )
        (root / "run" / "results" / "eval_resolved_config.yaml").write_text(
            yaml.safe_dump(resolved, sort_keys=False),
            encoding="utf-8",
        )
        return 0

    report = run_wall_contact_rollout_probe(
        manifest_path=manifest["manifest_path"],
        executor=executor,
        cwd=tmp_path,
    )

    assert len(calls) == 1
    assert report["status"] == "passed"
    assert report["executed_attempt_count"] == 1
    assert report["retry_count"] == 0
    assert report["outcome"] == "hard_safety_stop_before_10"
    with pytest.raises(FileExistsError):
        run_wall_contact_rollout_probe(
            manifest_path=manifest["manifest_path"],
            executor=executor,
            cwd=tmp_path,
        )
    assert len(calls) == 1


def test_validate_fails_closed_after_checkpoint_drift(tmp_path: Path) -> None:
    (
        source_config,
        source_rollout,
        source_summary,
        reset_validation,
        environment_manifest,
    ) = _source_fixture(tmp_path)
    root = tmp_path / "probe"
    manifest = prepare_wall_contact_rollout_probe(
        source_config_path=source_config,
        source_rollout_path=source_rollout,
        source_summary_path=source_summary,
        source_reset_validation_path=reset_validation,
        environment_manifest_path=environment_manifest,
        output_root=root,
    )
    config = yaml.safe_load(source_config.read_text())
    Path(config["policy"]["dig_ckpt_path"]).write_text(
        "drift",
        encoding="utf-8",
    )

    with pytest.raises(
        WallContactRolloutDiagnosticError,
        match="artifact_drift",
    ):
        validate_wall_contact_rollout_probe(manifest["manifest_path"])
