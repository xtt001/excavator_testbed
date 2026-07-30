from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import tomllib

from testbed.cli.terrain_replay_relabel_stats import main as cli_main
from testbed.eval.terrain_replay_relabel_stats import (
    build_replay_relabel_stats,
    load_replay_diagnostic_summary,
    write_replay_relabel_outputs,
)

TARGET_ID = "t1_large_shallow_rectangular_pit_default"


def _candidate(
    *,
    episode_id: str = "episode_0",
    cycle_index: int = 0,
    payload: float = 40.0,
    deposit: float = 28.0,
    removed_end: list[float] | None = None,
    source_cycle_id: int | None = None,
) -> dict[str, object]:
    record = {
        "schema": "terrain_gold_cycle_sample_v1",
        "source": "official_gold_cycle_sample_builder",
        "episode_id": episode_id,
        "rollout_id": "repeat",
        "cycle_index": cycle_index,
        "target_id": TARGET_ID,
        "removed_depth_grid_start_m": [0.0] * 6,
        "removed_depth_grid_end_m": removed_end
        if removed_end is not None
        else [0.12, 0.0, 0.08, 0.0, 0.0, 0.0],
        "valid_mask": [1.0] * 6,
        "payload_mass_kg": payload,
        "effective_deposit_mass_kg": deposit,
    }
    if source_cycle_id is not None:
        record["source_cycle_id"] = source_cycle_id
    return record


def _repeat(
    repeat_id: str,
    record: dict[str, object],
    *,
    qpos: float = 0.001,
    exceptions: int = 0,
    realigns: int = 0,
) -> dict[str, object]:
    return {
        "repeat_id": repeat_id,
        "candidate_records": [record],
        "diagnostic_summary": {
            "qpos_max_error_max": qpos,
            "exception_count": exceptions,
            "pose_realign_count": realigns,
        },
    }


def test_replay_relabel_stats_promotes_low_variance_repeats_to_a_tier() -> None:
    repeats = [
        _repeat(f"r{i}", _candidate(payload=40.0 + delta, deposit=28.0 + 0.2 * i))
        for i, delta in enumerate([-0.8, -0.2, 0.0, 0.3, 0.7])
    ]

    result = build_replay_relabel_stats(
        repeats,
        source_episode_id="episode_0",
        target_id=TARGET_ID,
    )

    assert result["schema"] == "terrain_replay_relabel_stats_v2"
    assert result["source"] == "current_unity_replay_relabel_stats"
    assert result["status"] == "present"
    assert result["group_count"] == 1
    assert result["usable_group_count"] == 1
    record = result["records"][0]
    assert record["schema"] == "terrain_replay_relabel_cycle_sample_v2"
    assert record["source"] == "current_unity_replay_relabel"
    assert record["source_episode_id"] == "episode_0"
    assert record["target_id"] == TARGET_ID
    assert record["cycle_index"] == 0
    assert record["repeat_count"] == 5
    assert record["tier"] == "A"
    assert record["label_usage"] == "fine_relabel"
    assert record["recommended_weight"] == 1.0
    np.testing.assert_allclose(record["payload_mass_kg_mean"], 40.0)
    assert record["payload_mass_kg_std"] <= 2.0
    assert record["effective_deposit_mass_kg_std"] <= 2.0
    assert record["removed_depth_delta_grid_max_cell_std_m"] <= 0.02
    assert record["qpos_max_error_max"] == 0.001
    assert record["exception_count"] == 0
    assert record["pose_realign_count"] == 0


def test_replay_relabel_stats_marks_medium_variance_as_uncertain_b_tier() -> None:
    payloads = [36.0, 38.0, 40.0, 42.0, 44.0]
    repeats = [
        _repeat(
            f"r{i}",
            _candidate(
                payload=payload,
                deposit=25.0 + i,
                removed_end=[0.10 + i * 0.01, 0.0, 0.08, 0.0, 0.0, 0.0],
            ),
        )
        for i, payload in enumerate(payloads)
    ]

    result = build_replay_relabel_stats(
        repeats,
        source_episode_id="episode_0",
        target_id=TARGET_ID,
    )

    record = result["records"][0]
    assert record["tier"] == "B"
    assert record["label_usage"] == "uncertainty_weighted_relabel"
    assert 0.25 <= record["recommended_weight"] <= 0.75
    assert record["payload_mass_kg_std"] > 2.0
    assert record["payload_mass_kg_std"] <= 5.0
    assert record["removed_depth_delta_grid_max_cell_std_m"] <= 0.06


def test_replay_relabel_stats_keeps_postcontact_qpos_as_diagnostic_only() -> None:
    repeats = [
        _repeat(f"r{i}", _candidate(payload=40.0 + 0.1 * i), qpos=0.65)
        for i in range(5)
    ]

    result = build_replay_relabel_stats(
        repeats,
        source_episode_id="episode_0",
        target_id=TARGET_ID,
    )

    record = result["records"][0]
    assert record["tier"] == "A"
    assert record["qpos_max_error_max"] == 0.65
    assert record["qpos_gate_role"] == "diagnostic_only_post_contact"


def test_replay_relabel_stats_marks_realign_or_exception_as_c_tier() -> None:
    repeats = [
        _repeat(f"r{i}", _candidate(payload=40.0 + i), qpos=0.001)
        for i in range(4)
    ]
    repeats.append(
        _repeat(
            "r4",
            _candidate(payload=40.0),
            qpos=0.04,
            exceptions=1,
            realigns=1,
        )
    )

    result = build_replay_relabel_stats(
        repeats,
        source_episode_id="episode_0",
        target_id=TARGET_ID,
    )

    record = result["records"][0]
    assert record["tier"] == "C"
    assert record["label_usage"] == "coarse_or_diagnostic_only"
    assert record["recommended_weight"] == 0.0
    assert record["qpos_max_error_max"] == 0.04
    assert record["exception_count"] == 1
    assert record["pose_realign_count"] == 1


def test_replay_relabel_stats_writes_report_and_samples_without_overwrite(tmp_path) -> None:
    repeats = [
        _repeat(f"r{i}", _candidate(payload=40.0 + 0.1 * i))
        for i in range(5)
    ]
    report_path = tmp_path / "stats.json"
    samples_path = tmp_path / "samples.jsonl"

    first = write_replay_relabel_outputs(
        repeats,
        report_path=report_path,
        samples_path=samples_path,
        source_episode_id="episode_0",
        target_id=TARGET_ID,
    )
    second = write_replay_relabel_outputs(
        repeats,
        report_path=report_path,
        samples_path=samples_path,
        source_episode_id="episode_0",
        target_id=TARGET_ID,
    )

    assert first["status"] == "present"
    assert json.loads(report_path.read_text(encoding="utf-8"))["schema"] == (
        "terrain_replay_relabel_stats_v2"
    )
    sample_lines = samples_path.read_text(encoding="utf-8").splitlines()
    assert len(sample_lines) == 1
    assert json.loads(sample_lines[0])["schema"] == (
        "terrain_replay_relabel_cycle_sample_v2"
    )
    assert second["status"] == "output_path_already_exists"


def test_replay_relabel_stats_cli_writes_report_and_sample_jsonl(tmp_path) -> None:
    repeat_paths: list[Path] = []
    diagnostic_paths: list[Path] = []
    for index, delta in enumerate([-0.5, -0.1, 0.0, 0.1, 0.5]):
        repeat_path = tmp_path / f"repeat_{index}.jsonl"
        diagnostic_path = tmp_path / f"repeat_{index}_diagnostics.jsonl"
        repeat_path.write_text(
            json.dumps(_candidate(payload=40.0 + delta), sort_keys=True) + "\n",
            encoding="utf-8",
        )
        diagnostic_path.write_text(
            json.dumps(
                {
                    "event": "episode_end",
                    "source_episode": "episode_0.hdf5",
                    "qpos_max_diff": 0.001,
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        repeat_paths.append(repeat_path)
        diagnostic_paths.append(diagnostic_path)

    report_path = tmp_path / "relabel_stats.json"
    samples_path = tmp_path / "relabel_samples.jsonl"
    argv = [
        "--source-episode-id",
        "episode_0",
        "--target-id",
        TARGET_ID,
        "--report-json",
        str(report_path),
        "--samples-jsonl",
        str(samples_path),
    ]
    for path in repeat_paths:
        argv.extend(["--repeat-jsonl", str(path)])
    for path in diagnostic_paths:
        argv.extend(["--diagnostic-log", str(path)])

    rc = cli_main(argv)

    assert rc == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["schema"] == "terrain_replay_relabel_stats_v2"
    assert report["training_source"] == "current_unity_replay_relabel"
    assert report["gold_status"] == "not_gold"
    sample_lines = samples_path.read_text(encoding="utf-8").splitlines()
    assert len(sample_lines) == 1
    record = json.loads(sample_lines[0])
    assert record["schema"] == "terrain_replay_relabel_cycle_sample_v2"
    assert record["source_episode_id"] == "episode_0"
    assert record["target_id"] == TARGET_ID
    assert record["tier"] == "A"


def test_replay_relabel_stats_cli_entrypoint_registered() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["tb-terrain-replay-relabel-stats"] == (
        "testbed.cli.terrain_replay_relabel_stats:main"
    )


def test_replay_relabel_stats_cli_supports_python_module_entrypoint() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "testbed.cli.terrain_replay_relabel_stats",
            "--help",
        ],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )

    assert "tb-terrain-replay-relabel-stats" in completed.stdout


def test_replay_diagnostic_summary_reads_exceptions_realigns_and_qpos(tmp_path) -> None:
    path = tmp_path / "repeat.jsonl"
    rows = [
        {
            "event": "episode_start",
            "source_episode": "episode_0.hdf5",
            "diagnostic_every": 1,
        },
        {
            "event": "step",
            "record_step_index": 0,
            "step_id_before": 0,
            "step_id_after": 1,
            "qpos_max_error_before": 0.0,
            "qpos_max_error_after": 0.001,
            "env_state_before": {"bucket_dig_area_penetration_contact_mask": 0.0},
            "env_state_after": {"bucket_dig_area_penetration_contact_mask": 0.0},
        },
        {
            "event": "step",
            "record_step_index": 1,
            "step_id_before": 1,
            "step_id_after": 2,
            "qpos_max_error_before": 0.001,
            "qpos_max_error_after": 0.002,
            "env_state_before": {"bucket_dig_area_penetration_contact_mask": 0.0},
            "env_state_after": {"bucket_dig_area_penetration_contact_mask": 0.0},
        },
        {
            "event": "step",
            "record_step_index": 2,
            "step_id_before": 2,
            "step_id_after": 3,
            "qpos_max_error_before": 0.002,
            "qpos_max_error_after": 0.01,
            "env_state_before": {"bucket_dig_area_penetration_contact_mask": 0.0},
            "env_state_after": {"bucket_dig_area_penetration_contact_mask": 0.0},
        },
        {
            "event": "step",
            "record_step_index": 3,
            "step_id_before": 3,
            "step_id_after": 4,
            "qpos_max_error_before": 0.01,
            "qpos_max_error_after": 0.015,
            "env_state_before": {"bucket_dig_area_penetration_contact_mask": 0.0},
            "env_state_after": {
                "bucket_dig_area_penetration_contact_mask": 1.0,
                "removed_depth_m_grid_3x2": [0.0] * 6,
            },
        },
        {"event": "pose_realign", "qpos_max_error_after": 0.004},
        {"event": "step_exception", "qpos_max_error_before": 0.03},
        {
            "event": "episode_end",
            "steps": 4,
            "qpos_max_diff": 0.02,
            "pose_realign_count": 1,
            "final_env_state": {
                "removed_depth_m_grid_3x2": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
            },
        },
    ]
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )

    summary = load_replay_diagnostic_summary(path)

    assert summary == {
        "source_episode": "episode_0.hdf5",
        "qpos_max_error_max": 0.03,
        "qpos_pre_contact_max_error_max": 0.01,
        "first_qualified_contact_step": 3,
        "exception_count": 1,
        "pose_realign_count": 1,
        "step_sequence_complete": True,
        "logged_step_count": 4,
        "source_step_count": 4,
        "final_removed_depth_grid_m": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6],
    }


def test_replay_diagnostic_summary_detects_missing_step_sequence(tmp_path) -> None:
    path = tmp_path / "repeat_missing.jsonl"
    rows = [
        {
            "event": "episode_start",
            "source_episode": "episode_0.hdf5",
            "diagnostic_every": 1,
        },
        {"event": "step", "record_step_index": 0, "step_id_before": 0, "step_id_after": 1},
        {"event": "step", "record_step_index": 2, "step_id_before": 2, "step_id_after": 3},
        {"event": "episode_end", "steps": 3},
    ]
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )

    summary = load_replay_diagnostic_summary(path)

    assert summary["step_sequence_complete"] is False
    assert summary["logged_step_count"] == 2
    assert summary["source_step_count"] == 3


def test_corrected_replay_diagnostic_accepts_backend_id_stutter_at_realign(
    tmp_path,
) -> None:
    path = tmp_path / "repeat_corrected_realign.jsonl"
    rows = [
        {
            "event": "episode_start",
            "source_episode": "episode_4.hdf5",
            "diagnostic_every": 1,
            "realign_config": {"enabled": True},
        },
        {
            "event": "step",
            "record_step_index": 0,
            "step_id_before": 0,
            "step_id_after": 1,
        },
        {
            "event": "pose_realign",
            "record_step_index": 1,
            "step_id_before": 1,
            "step_id_after": 2,
        },
        {
            "event": "step",
            "record_step_index": 1,
            "step_id_before": 2,
            "step_id_after": 2,
        },
        {
            "event": "step",
            "record_step_index": 2,
            "step_id_before": 2,
            "step_id_after": 3,
        },
        {"event": "episode_end", "steps": 3, "pose_realign_count": 1},
    ]
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )

    summary = load_replay_diagnostic_summary(path)

    assert summary["step_sequence_complete"] is True
    assert summary["pose_realign_count"] == 1


def test_sparse_replay_diagnostics_use_terminal_snapshot_and_episode_step_count(
    tmp_path,
) -> None:
    path = tmp_path / "repeat_sparse.jsonl"
    rows = [
        {
            "event": "episode_start",
            "source_episode": "episode_0.hdf5",
            "diagnostic_every": 0,
        },
        {
            "event": "step",
            "record_step_index": 10,
            "step_id_before": 10,
            "step_id_after": 11,
            "qpos_max_error_before": 0.001,
            "qpos_max_error_after": 0.002,
            "env_state_before": {"bucket_dig_area_penetration_contact_mask": 0.0},
            "env_state_after": {"bucket_dig_area_penetration_contact_mask": 1.0},
        },
        {
            "event": "step",
            "record_step_index": 90,
            "step_id_before": 90,
            "step_id_after": 91,
        },
        {
            "event": "episode_end",
            "steps": 100,
            "qpos_max_diff": 0.4,
            "pose_realign_count": 0,
            "final_env_state": {
                "removed_depth_m_grid_3x2": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
            },
        },
    ]
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )

    summary = load_replay_diagnostic_summary(path)

    assert summary["step_sequence_complete"] is True
    assert summary["source_step_count"] == 100
    assert summary["logged_step_count"] == 2
    assert summary["qpos_max_error_max"] == 0.4
    assert summary["final_removed_depth_grid_m"] == [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]


def test_replay_relabel_stats_groups_by_source_cycle_id_after_boundary_matching() -> None:
    repeats = [
        _repeat(
            f"r{i}",
            _candidate(cycle_index=7 + i, source_cycle_id=3, payload=40.0),
        )
        for i in range(5)
    ]

    result = build_replay_relabel_stats(
        repeats,
        source_episode_id="episode_0",
        target_id=TARGET_ID,
    )

    assert result["group_count"] == 1
    assert result["records"][0]["source_cycle_id"] == 3
    assert result["records"][0]["cycle_index"] == 3
