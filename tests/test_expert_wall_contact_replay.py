from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import h5py
import numpy as np
import pytest

from testbed.eval.expert_wall_contact_replay import (
    ExpertWallContactReplayError,
    build_tb_replay_command,
    postprocess_expert_replay_attempt,
    run_expert_wall_contact_replay,
    validate_expert_replay_schedule,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_source(
    path: Path,
    *,
    profile: str = "recording_pre_fix_v1",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    qpos = np.asarray(
        [[0.1 + step * 0.001, 0.2, 0.3, 0.4] for step in range(5)],
        dtype=np.float32,
    )
    qvel = np.zeros((5, 4), dtype=np.float32)
    env_state = np.zeros((5, 89), dtype=np.float32)
    env_state[:, 28:31] = np.asarray([1.0, 2.0, 3.0])
    env_state[:, 75] = 1.25
    env_state[:, 39:45] = np.asarray(
        [
            [0.0] * 6,
            [0.0] * 6,
            [0.001] * 6,
            [0.002] * 6,
            [0.003] * 6,
        ],
        dtype=np.float32,
    )
    with h5py.File(path, "w") as handle:
        observations = handle.create_group("observations")
        observations.create_dataset("qpos", data=qpos)
        observations.create_dataset("qvel", data=qvel)
        observations.create_dataset("env_state", data=env_state)
        handle.create_dataset(
            "action",
            data=np.zeros((5, 4), dtype=np.float32),
        )
        metadata = handle.create_group("metadata")
        metadata.attrs["replay_control_compatibility_profile"] = profile
        metadata.attrs["seed"] = 123
        metadata.attrs["scenario_id"] = "s0_truck"
        metadata.attrs["task_name"] = "agx_excavation_teleop"
        metadata.attrs["control_hz"] = 50


def _contact_detail(
    *,
    component: str = "bucket",
    force_n: float = 1000.0,
    step_id: int = 3,
) -> dict[str, object]:
    wall = "Dig_ZMin_Board"
    return {
        "schema": "worktool_wall_contact_detail_v1",
        "step_id": step_id,
        "sim_time_s": step_id * 0.02,
        "delta_time_s": 0.02,
        "session_id": 1,
        "session_count": 1,
        "consecutive_contact_steps": 1,
        "session_duration_s": 0.02,
        "session_normal_impulse_n_s": force_n * 0.02,
        "parts": [component],
        "walls": [wall],
        "pairs": [
            {
                "component": component,
                "machine_shape_path": f"/machine/{component}",
                "wall_name": wall,
                "wall_shape_path": f"/walls/{wall}",
                "callback_count": 2,
                "contact_point_count": 2,
                "max_normal_force_n": force_n,
                "max_tangential_force_n": 20.0,
                "max_total_force_n": force_n,
                "contact_points_world_m": [
                    [1.0, 2.0, 3.0],
                    [1.1, 2.0, 3.0],
                ],
                "representative_contact_point_component_local_m": [
                    0.1,
                    0.2,
                    0.3,
                ],
                "tangential_displacement_m": 0.02,
            }
        ],
    }


def _env_snapshot(
    source_env: np.ndarray,
    *,
    current_remaining_mass_kg: float,
    wall_detail: dict[str, object] | None = None,
    wall_session_count: int = 0,
) -> dict[str, object]:
    pair_force = (
        0.0
        if wall_detail is None
        else float(wall_detail["pairs"][0]["max_normal_force_n"])  # type: ignore[index]
    )
    return {
        "shape": [107],
        "bucket_tip_dig_area_x_m": float(source_env[28]),
        "bucket_tip_dig_area_y_m": float(source_env[29]),
        "bucket_tip_dig_area_z_m": float(source_env[30]),
        "removed_depth_m_grid_3x2": source_env[39:45].tolist(),
        "dig_area_source_bulk_density_kg_m3": 1600.0,
        "dig_area_current_remaining_mass_kg": current_remaining_mass_kg,
        "dig_area_initial_remaining_mass_kg": 100.0,
        "dig_area_remaining_mass_valid_mask": 1.0,
        "excavator_wall_contact_typed_mask": (
            0.0 if wall_detail is None else 1.0
        ),
        "excavator_wall_contact_step_max_force_n": pair_force,
        "excavator_wall_contact_session_count": float(wall_session_count),
    }


def _write_diagnostics(
    path: Path,
    source: Path,
    *,
    qpos_error_step: int | None = None,
    contact_step: int | None = 2,
    omit_sidecar: bool = False,
    component: str = "bucket",
    force_n: float = 1000.0,
) -> None:
    with h5py.File(source, "r") as handle:
        qpos = np.asarray(handle["observations/qpos"])
        qvel = np.asarray(handle["observations/qvel"])
        env_state = np.asarray(handle["observations/env_state"])
        profile = str(
            handle["metadata"].attrs[
                "replay_control_compatibility_profile"
            ]
        )
    rows: list[dict[str, object]] = [
        {
            "event": "episode_start",
            "source_episode": str(source),
            "diagnostic_every": 1,
            "realign_config": {"enabled": False},
            "replay_control_compatibility_profile": profile,
        }
    ]
    initial_depth = env_state[0, 39:45]
    for step in range(len(qpos)):
        detail = (
            _contact_detail(
                component=component,
                force_n=force_n,
                step_id=step + 1,
            )
            if step == contact_step
            else None
        )
        depth_delta = env_state[step, 39:45] - initial_depth
        remaining = 100.0 - float(
            np.sum(depth_delta) * env_state[step, 75] * 1600.0
        )
        replay_qpos = qpos[step].copy()
        if qpos_error_step == step:
            replay_qpos[0] += 0.01
        warning = (
            []
            if detail is None or omit_sidecar
            else [
                "worktool_wall_contact_detail_v1:"
                + json.dumps(detail, separators=(",", ":"))
            ]
        )
        session_before = int(
            contact_step is not None and step > contact_step
        )
        session_after = int(
            contact_step is not None and step >= contact_step
        )
        rows.append(
            {
                "event": "step",
                "record_step_index": step,
                "step_id_before": step,
                "step_id_after": step + 1,
                "source_qpos": qpos[step].tolist(),
                "source_qvel": qvel[step].tolist(),
                "replay_qpos_before": replay_qpos.tolist(),
                "replay_qvel_before": qvel[step].tolist(),
                "env_state_before": _env_snapshot(
                    env_state[step],
                    current_remaining_mass_kg=remaining,
                    wall_session_count=session_before,
                ),
                "env_state_after": _env_snapshot(
                    env_state[step],
                    current_remaining_mass_kg=remaining,
                    wall_detail=detail,
                    wall_session_count=session_after,
                ),
                "warnings_after": warning,
            }
        )
    rows.append(
        {
            "event": "episode_end",
            "source_episode": str(source),
            "steps": len(qpos),
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def _attempt(source: Path) -> dict[str, object]:
    return {
        "attempt_id": "expert_source_003",
        "sequence_index": 1,
        "source_episode_id": 3,
        "split": "train",
        "source_hdf5_path": str(source),
        "source_hdf5_sha256": _sha(source),
        "attempt_index": 1,
        "max_attempts": 1,
        "retry_allowed": False,
        "replay_scope": "complete_recorded_action_source",
        "control_compatibility_profile": "recording_pre_fix_v1",
        "authorized_windows": [
            {
                "window_id": "episode_0",
                "source_cycle_id": 0,
                "start_step": 1,
                "end_step_exclusive": 4,
            }
        ],
        "warning_schema": "worktool_wall_contact_detail_v1",
        "output_path": "/unused/expert_source_003.json",
        "runner_contract": "guarded_recorded_action_replay_v1",
    }


def test_tb_replay_command_is_diagnostic_only_and_never_realigns(
    tmp_path: Path,
) -> None:
    source = tmp_path / "episode_3.hdf5"
    _write_source(source)
    command = build_tb_replay_command(
        attempt=_attempt(source),
        diagnostic_path=tmp_path / "diagnostics.jsonl",
        executable="tb-replay",
        config_path=tmp_path / "config.yaml",
    )

    assert command[:3] == ["tb-replay", "--episode", str(source.resolve())]
    assert command[command.index("--diagnostic-every") + 1] == "1"
    assert command[
        command.index("--control-compatibility-profile") + 1
    ] == "recording_pre_fix_v1"
    assert command[command.index("--selection-profile") + 1] == (
        "calibrated_mixed_current_equivalent"
    )
    assert "--record-output-dir" not in command
    assert "--realign-on-qpos-error" not in command


def test_postprocess_valid_window_aggregates_component_wall_contact(
    tmp_path: Path,
) -> None:
    source = tmp_path / "episode_3.hdf5"
    diagnostics = tmp_path / "diagnostics.jsonl"
    _write_source(source)
    _write_diagnostics(diagnostics, source)

    result = postprocess_expert_replay_attempt(
        attempt=_attempt(source),
        diagnostic_log_path=diagnostics,
    )

    assert result["status"] == "passed"
    assert result["retry_count"] == 0
    window = result["dig_windows"][0]
    assert window["status"] == "passed"
    assert window["replay_fairness"]["qpos_max_abs_difference"] == 0.0
    assert window["wall_contact_observed"] is True
    assert window["production_inference_eligible"] is True
    summary = window["production_inference_contact_summary"]
    assert summary["peak_force_n"] == 1000.0
    assert summary["categories"] == ["bucket_touch"]
    pair = summary["component_wall_summaries"][0]
    assert pair["component"] == "bucket"
    assert pair["wall_name"] == "Dig_ZMin_Board"
    assert pair["peak_total_force_n"] == 1000.0
    assert pair["rms_total_force_n"] == 1000.0
    assert pair["normal_impulse_n_s"] == 20.0
    assert pair["callback_count"] == 2
    assert pair["contact_point_count"] == 2


def test_measurement_source_matches_experiment_collector_contract(
    tmp_path: Path,
) -> None:
    from testbed.eval.wall_contact_experiment_contracts import (
        validate_expert_replay_source,
    )

    source = tmp_path / "episode_3.hdf5"
    diagnostics = tmp_path / "diagnostics.jsonl"
    _write_source(source)
    _write_diagnostics(diagnostics, source)
    attempt = _attempt(source)

    collected = validate_expert_replay_source(
        expected=attempt,
        measured=postprocess_expert_replay_attempt(
            attempt=attempt,
            diagnostic_log_path=diagnostics,
        ),
    )

    assert collected["blockers"] == []
    assert collected["production_inference_contact_summary"][
        "contact_observed"
    ] is True


def test_invalid_window_contact_is_excluded_from_production_inference(
    tmp_path: Path,
) -> None:
    source = tmp_path / "episode_3.hdf5"
    diagnostics = tmp_path / "diagnostics.jsonl"
    _write_source(source)
    _write_diagnostics(
        diagnostics,
        source,
        qpos_error_step=2,
    )

    result = postprocess_expert_replay_attempt(
        attempt=_attempt(source),
        diagnostic_log_path=diagnostics,
    )

    window = result["dig_windows"][0]
    assert window["status"] == "invalid"
    assert window["wall_contact_observed"] is True
    assert window["production_inference_eligible"] is False
    assert window["all_diagnostic_contact_summary"]["contact_observed"] is True
    assert (
        window["production_inference_contact_summary"]["contact_observed"]
        is False
    )


def test_wall_positive_tick_without_sidecar_fails_closed(
    tmp_path: Path,
) -> None:
    source = tmp_path / "episode_3.hdf5"
    diagnostics = tmp_path / "diagnostics.jsonl"
    _write_source(source)
    _write_diagnostics(
        diagnostics,
        source,
        omit_sidecar=True,
    )

    result = postprocess_expert_replay_attempt(
        attempt=_attempt(source),
        diagnostic_log_path=diagnostics,
    )

    assert result["status"] == "blocked"
    assert "contact_detail_missing" in result["blockers"]
    assert result["dig_windows"][0]["status"] == "blocked"


def test_no_contact_tick_cannot_increment_cumulative_session_count(
    tmp_path: Path,
) -> None:
    source = tmp_path / "episode_3.hdf5"
    diagnostics = tmp_path / "diagnostics.jsonl"
    _write_source(source)
    _write_diagnostics(diagnostics, source)
    rows = [
        json.loads(line)
        for line in diagnostics.read_text(encoding="utf-8").splitlines()
    ]
    row = next(
        item
        for item in rows
        if item.get("event") == "step"
        and item.get("record_step_index") == 3
    )
    row["env_state_after"][
        "excavator_wall_contact_session_count"
    ] = 2.0
    diagnostics.write_text(
        "".join(json.dumps(item) + "\n" for item in rows),
        encoding="utf-8",
    )

    result = postprocess_expert_replay_attempt(
        attempt=_attempt(source),
        diagnostic_log_path=diagnostics,
    )

    assert result["status"] == "blocked"
    assert "typed_contact_session_lineage_drift" in result["blockers"]


def test_continuous_contact_tick_cannot_start_a_new_session(
    tmp_path: Path,
) -> None:
    source = tmp_path / "episode_3.hdf5"
    diagnostics = tmp_path / "diagnostics.jsonl"
    _write_source(source)
    _write_diagnostics(diagnostics, source)
    rows = [
        json.loads(line)
        for line in diagnostics.read_text(encoding="utf-8").splitlines()
    ]
    row = next(
        item
        for item in rows
        if item.get("event") == "step"
        and item.get("record_step_index") == 3
    )
    detail = _contact_detail(step_id=4)
    detail["session_id"] = 2
    detail["session_count"] = 2
    row["env_state_after"] = _env_snapshot(
        np.zeros(89, dtype=np.float32),
        current_remaining_mass_kg=90.4,
        wall_detail=detail,
        wall_session_count=2,
    )
    row["warnings_after"] = [
        "worktool_wall_contact_detail_v1:"
        + json.dumps(detail, separators=(",", ":"))
    ]
    diagnostics.write_text(
        "".join(json.dumps(item) + "\n" for item in rows),
        encoding="utf-8",
    )

    result = postprocess_expert_replay_attempt(
        attempt=_attempt(source),
        diagnostic_log_path=diagnostics,
    )

    assert result["status"] == "blocked"
    assert "typed_contact_session_lineage_drift" in result["blockers"]


def test_forbidden_component_is_classified_without_shortening_full_replay(
    tmp_path: Path,
) -> None:
    source = tmp_path / "episode_3.hdf5"
    diagnostics = tmp_path / "diagnostics.jsonl"
    _write_source(source)
    _write_diagnostics(
        diagnostics,
        source,
        component="stick",
    )

    result = postprocess_expert_replay_attempt(
        attempt=_attempt(source),
        diagnostic_log_path=diagnostics,
    )

    assert result["status"] == "passed"
    assert result["complete_recorded_action_replay"] is True
    assert (
        result["dig_windows"][0]["all_diagnostic_contact_summary"][
            "categories"
        ]
        == ["forbidden_component"]
    )


def test_high_force_is_classified_without_shortening_full_replay(
    tmp_path: Path,
) -> None:
    source = tmp_path / "episode_3.hdf5"
    diagnostics = tmp_path / "diagnostics.jsonl"
    _write_source(source)
    _write_diagnostics(
        diagnostics,
        source,
        force_n=100_000.0,
    )

    result = postprocess_expert_replay_attempt(
        attempt=_attempt(source),
        diagnostic_log_path=diagnostics,
    )

    assert result["status"] == "passed"
    assert (
        result["dig_windows"][0]["all_diagnostic_contact_summary"][
            "categories"
        ]
        == ["bucket_touch", "high_force_collision"]
    )


def test_schedule_inventory_and_no_retry_are_frozen(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from testbed.eval import expert_wall_contact_replay as module

    source = tmp_path / "episode_3.hdf5"
    _write_source(source)
    monkeypatch.setattr(module, "TRAIN_SOURCE_EPISODE_IDS", (3,))
    monkeypatch.setattr(module, "HOLDOUT_SOURCE_EPISODE_IDS", ())
    schedule = {
        "schema": "expert_recorded_action_contact_replay_schedule_v1",
        "attempts": [_attempt(source)],
    }
    normalized = validate_expert_replay_schedule(schedule)
    assert normalized[0]["source_episode_id"] == 3

    schedule["attempts"][0]["retry_allowed"] = True
    with pytest.raises(
        ExpertWallContactReplayError,
        match="expert_replay_retry_forbidden",
    ):
        validate_expert_replay_schedule(schedule)


def test_runner_executes_each_source_once_and_continues_after_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from testbed.eval import expert_wall_contact_replay as module

    pre_source = tmp_path / "episode_3.hdf5"
    production_source = tmp_path / "episode_23.hdf5"
    _write_source(pre_source)
    _write_source(production_source, profile="production")
    monkeypatch.setattr(module, "TRAIN_SOURCE_EPISODE_IDS", (3, 23))
    monkeypatch.setattr(module, "HOLDOUT_SOURCE_EPISODE_IDS", ())
    attempts = [_attempt(pre_source), _attempt(production_source)]
    attempts[1].update(
        {
            "attempt_id": "expert_source_023",
            "sequence_index": 2,
            "source_episode_id": 23,
            "source_hdf5_path": str(production_source),
            "source_hdf5_sha256": _sha(production_source),
            "control_compatibility_profile": "production",
        }
    )
    for attempt in attempts:
        attempt["output_path"] = str(
            tmp_path / "source_outputs" / f"{attempt['attempt_id']}.json"
        )
    schedule = tmp_path / "schedule.json"
    schedule.write_text(
        json.dumps(
            {
                "schema": (
                    "expert_recorded_action_contact_replay_schedule_v1"
                ),
                "attempts": attempts,
            }
        ),
        encoding="utf-8",
    )
    calls: list[list[str]] = []

    def fake_runner(
        command: list[str],
    ) -> subprocess.CompletedProcess[str]:
        calls.append(list(command))
        source = Path(command[command.index("--episode") + 1])
        if source.name == "episode_3.hdf5":
            return subprocess.CompletedProcess(
                command,
                returncode=7,
                stdout="",
                stderr="forced failure",
            )
        diagnostic = Path(
            command[command.index("--diagnostic-log") + 1]
        )
        _write_diagnostics(diagnostic, source, contact_step=None)
        return subprocess.CompletedProcess(
            command,
            returncode=0,
            stdout="complete",
            stderr="",
        )

    result = run_expert_wall_contact_replay(
        schedule_path=schedule,
        measurement_path=tmp_path / "measurement.json",
        attempt_root=tmp_path / "attempts",
        command_runner=fake_runner,
    )

    assert len(calls) == 2
    assert [item["status"] for item in result["sources"]] == [
        "blocked",
        "passed",
    ]
    assert all(item["retry_count"] == 0 for item in result["sources"])
    assert (
        tmp_path
        / "attempts/expert_source_003/attempt_started.json"
    ).is_file()
    with pytest.raises(FileExistsError):
        run_expert_wall_contact_replay(
            schedule_path=schedule,
            measurement_path=tmp_path / "measurement_2.json",
            attempt_root=tmp_path / "attempts",
            command_runner=fake_runner,
        )
    assert len(calls) == 2
