from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
import pytest

from testbed.data.schema import (
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_V2_4_DIM,
)
from testbed.eval.actual_tuple_bounded_validation import (
    OUTPUT_FILENAME,
    build_actual_tuple_bounded_validation,
)


def _write_library(path: Path) -> tuple[str, str]:
    raw_fields = {
        "operator_entry_x_m": 0.4,
        "operator_entry_y_m": 0.0,
        "operator_entry_z_m": -0.7,
        "operator_exit_x_m": 0.2,
        "operator_exit_y_m": -0.3,
        "operator_exit_z_m": -0.6,
        "operator_cut_direction_x": -0.5345224838248488,
        "operator_cut_direction_y": -0.8017837257372731,
        "operator_cut_direction_z": 0.2672612419124243,
        "operator_cut_length_m": 0.37416573867739417,
        "operator_cut_depth_peak_m": 0.30,
        "operator_cut_payload_gain_kg": 60.0,
        "operator_effective_deposit_delta_kg": 40.0,
        "operator_cut_valid": 1,
    }
    rendered = json.dumps(
        {
            "schema": "strict_train_coverage_execution_library_v1_1",
            "status": "completed",
            "records": [
                {
                    "exemplar_id": "episode_168",
                    "primitive_episode_id": 168,
                    "source_episode_id": 24,
                    "corridor_id": 1_000_168,
                    "effect_outcome_cell_id": 1,
                    "return_envelope_cell_id": 0,
                    "raw_fields": raw_fields,
                    "execution_tail_plane_depth_reserve_m": 0.01,
                }
            ],
        },
        sort_keys=True,
    )
    path.write_text(rendered, encoding="utf-8")
    raw_sha256 = hashlib.sha256(
        json.dumps(
            raw_fields,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    return hashlib.sha256(rendered.encode()).hexdigest(), raw_sha256


def _write_rollout(
    results: Path,
    rollout_id: int,
    *,
    final_plane_depth_m: float,
    raw_fields_sha256: str,
) -> None:
    env = np.zeros((4, ENV_STATE_V2_4_DIM), dtype=np.float32)
    env[:, ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX] = [
        0.28,
        0.299,
        0.31,
        0.32,
    ]
    env[:, ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX] = [
        0.20,
        0.21,
        0.22,
        final_plane_depth_m,
    ]
    hdf5_dir = results / "hdf5_rollouts"
    hdf5_dir.mkdir(parents=True, exist_ok=True)
    with h5py.File(hdf5_dir / f"episode_{rollout_id}.hdf5", "w") as handle:
        handle.create_dataset("observations/env_state", data=env)
        handle.create_dataset(
            "action",
            data=np.asarray(
                [[0.1, 0.0, 0.0, 0.0]] * 3
                + [[0.0, 0.0, 0.0, 0.0]],
                dtype=np.float32,
            ),
        )
        handle.create_dataset(
            "timestamps/step_id",
            data=np.arange(1, 5, dtype=np.int64),
        )
    rows = []
    for index in range(4):
        rows.append(
            {
                "rollout_id": rollout_id,
                "step_id": index + 1,
                "skill_name": "dig",
                "primitive_cycle_index": 1,
                "dig_step_count": index + 1,
                "env_state": env[index].astype(float).tolist(),
                "action": (
                    [0.0, 0.0, 0.0, 0.0]
                    if index == 3
                    else [0.1, 0.0, 0.0, 0.0]
                ),
                "coverage_execution_exemplar_id": "episode_168",
                "coverage_execution_corridor_id": 1_000_168,
                "coverage_execution_raw_fields_sha256": (
                    raw_fields_sha256
                ),
                "coverage_execution_tail_plane_depth_reserve_m": 0.01,
                "coverage_wall_minimum_clearance_m": 0.37,
                "carry_start_envelope_ready": index >= 2,
                "carry_start_envelope_hold_count": index + 1,
                "bounded_dig_probe_stop_trigger_kind": (
                    "envelope_ready" if index == 3 else ""
                ),
                "bounded_dig_probe_stop_neutral_acknowledged": (
                    index == 3
                ),
                "bounded_dig_probe_stop_terminal_requested": index == 3,
                "box_safety_contact_kind": "none",
                "box_safety_wall_contact_session_count": 0,
                "box_safety_reason": "",
                "transition_timeout": False,
            }
        )
    rollout_dir = results / "rollouts"
    rollout_dir.mkdir(parents=True, exist_ok=True)
    (rollout_dir / f"rollout_{rollout_id:03d}.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    (
        rollout_dir / f"rollout_{rollout_id:03d}_planner_trace.json"
    ).write_text(
        json.dumps(
            {
                "coverage_decision_trace": [
                    {
                        "event": "select_actual_tuple_execution_candidate",
                        "cycle_index": 1,
                        "skill_name": "dig",
                        "corridor_id": 1_000_168,
                        "exemplar_id": "episode_168",
                        "raw_fields_sha256": raw_fields_sha256,
                        "execution_tail_plane_depth_reserve_m": 0.01,
                        "wall_minimum_clearance_m": 0.37,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def test_three_reset_bounded_gate_passes_exact_tuple_and_tail_contract(
    tmp_path: Path,
) -> None:
    results = tmp_path / "results"
    library = tmp_path / "library.json"
    library_sha, raw_sha = _write_library(library)
    for rollout_id in range(3):
        _write_rollout(
            results,
            rollout_id,
            final_plane_depth_m=0.235,
            raw_fields_sha256=raw_sha,
        )
        (
            results
            / "rollouts"
            / f"rollout_{rollout_id:03d}.partial.jsonl"
        ).write_text("{}\n", encoding="utf-8")

    artifact = build_actual_tuple_bounded_validation(
        results_dir=results,
        strict_execution_library_path=library,
        strict_execution_library_sha256=library_sha,
        output_dir=tmp_path / "validation",
    )

    assert artifact["status"] == "passed"
    assert artifact["functional_1x10_allowed"] is True
    assert artifact["next_branch"] == "functional_1x10"
    assert len(artifact["rollouts"]) == 3
    assert all(item["passed"] for item in artifact["rollouts"])
    assert all(
        item["actual_execution_tail_plane_depth_m"]
        <= item["execution_tail_limit_m"]
        for item in artifact["rollouts"]
    )
    assert (tmp_path / "validation" / OUTPUT_FILENAME).is_file()


def test_tail_excess_routes_to_cut_then_extract_and_stays_closed(
    tmp_path: Path,
) -> None:
    results = tmp_path / "results"
    library = tmp_path / "library.json"
    library_sha, raw_sha = _write_library(library)
    for rollout_id in range(3):
        _write_rollout(
            results,
            rollout_id,
            final_plane_depth_m=0.26,
            raw_fields_sha256=raw_sha,
        )

    artifact = build_actual_tuple_bounded_validation(
        results_dir=results,
        strict_execution_library_path=library,
        strict_execution_library_sha256=library_sha,
        output_dir=tmp_path / "validation",
    )

    assert artifact["status"] == "failed"
    assert artifact["functional_1x10_allowed"] is False
    assert artifact["next_branch"] == "v2_4_6_cut_then_extract"


def test_missing_plan_failure_serializes_nulls_without_partial_output(
    tmp_path: Path,
) -> None:
    results = tmp_path / "results"
    library = tmp_path / "library.json"
    library_sha, raw_sha = _write_library(library)
    for rollout_id in range(3):
        _write_rollout(
            results,
            rollout_id,
            final_plane_depth_m=0.235,
            raw_fields_sha256=raw_sha,
        )
        path = results / "rollouts" / f"rollout_{rollout_id:03d}.jsonl"
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        for row in rows:
            row["coverage_execution_exemplar_id"] = ""
            row["coverage_execution_raw_fields_sha256"] = ""
            row["coverage_execution_corridor_id"] = -1
        path.write_text(
            "".join(json.dumps(row) + "\n" for row in rows),
            encoding="utf-8",
        )
        trace = (
            results
            / "rollouts"
            / f"rollout_{rollout_id:03d}_planner_trace.json"
        )
        trace.write_text(
            json.dumps({"coverage_decision_trace": []}),
            encoding="utf-8",
        )

    output_dir = tmp_path / "validation"
    artifact = build_actual_tuple_bounded_validation(
        results_dir=results,
        strict_execution_library_path=library,
        strict_execution_library_sha256=library_sha,
        output_dir=output_dir,
    )
    persisted = json.loads((output_dir / OUTPUT_FILENAME).read_text())

    assert artifact["status"] == "failed"
    assert artifact["rollouts"][0]["planned_depth_m"] is None
    assert persisted["rollouts"][0]["minimum_wall_clearance_m"] is None


def test_bounded_validation_is_no_overwrite(tmp_path: Path) -> None:
    results = tmp_path / "results"
    library = tmp_path / "library.json"
    library_sha, raw_sha = _write_library(library)
    for rollout_id in range(3):
        _write_rollout(
            results,
            rollout_id,
            final_plane_depth_m=0.235,
            raw_fields_sha256=raw_sha,
        )
    kwargs = {
        "results_dir": results,
        "strict_execution_library_path": library,
        "strict_execution_library_sha256": library_sha,
        "output_dir": tmp_path / "validation",
    }
    build_actual_tuple_bounded_validation(**kwargs)

    with pytest.raises(FileExistsError):
        build_actual_tuple_bounded_validation(**kwargs)
