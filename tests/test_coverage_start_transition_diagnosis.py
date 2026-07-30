from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
import pytest

from testbed.eval.coverage_start_transition_diagnosis import (
    TRANSITION_MEASUREMENT_INPUT_SCHEMA,
    TRANSITION_MEASUREMENT_OUTPUT_SCHEMA,
    build_start_transition_geometry_diagnosis,
    build_start_transition_measurement_input,
    classify_start_transition_geometry,
)


def _write_episode(path: Path, *, first_step: int, count: int) -> None:
    steps = np.arange(first_step, first_step + count, dtype=np.int64)
    qpos = np.stack(
        [
            np.linspace(0.10 + axis * 0.05, 0.20 + axis * 0.05, count)
            for axis in range(4)
        ],
        axis=1,
    ).astype(np.float32)
    with h5py.File(path, "w") as handle:
        handle.create_dataset("timestamps/step_id", data=steps)
        handle.create_dataset("observations/qpos", data=qpos)


def test_builder_extracts_exact_cycle0_and_paired_return_paths(
    tmp_path: Path,
) -> None:
    source_cycle0 = tmp_path / "episode_6.hdf5"
    source_post = tmp_path / "episode_24.hdf5"
    frozen = tmp_path / "frozen.hdf5"
    _write_episode(source_cycle0, first_step=0, count=6)
    _write_episode(source_post, first_step=10, count=16)
    _write_episode(frozen, first_step=0, count=4)

    execution = {
        "schema": "strict_train_coverage_execution_library_v1_1",
        "status": "completed",
        "sample_count": 2,
        "records": [
            {
                "exemplar_id": "episode_24",
                "source_episode_id": 6,
                "raw_fields_sha256": "a" * 64,
            },
            {
                "exemplar_id": "episode_171",
                "source_episode_id": 24,
                "raw_fields_sha256": "b" * 64,
            },
        ],
    }
    transitions = {
        "schema": "strict_train_coverage_return_transition_library_v1",
        "status": "completed",
        "records": [
            {
                "exemplar_id": "episode_24",
                "source_episode_id": 6,
                "source_cycle_id": 0,
                "dig_start_source_step": 3,
                "eligibility": {
                    "cycle0": True,
                    "post_return": False,
                    "reason": "episode_first_no_preceding_return",
                },
                "paired_return_exemplar_id": None,
            },
            {
                "exemplar_id": "episode_171",
                "source_episode_id": 24,
                "source_cycle_id": 4,
                "dig_start_source_step": 18,
                "return_start_source_step": 10,
                "return_handoff_source_step": 14,
                "paired_return_exemplar_id": "episode_161",
                "paired_return_primitive_episode_id": 161,
                "eligibility": {
                    "cycle0": True,
                    "post_return": True,
                    "reason": "gold_return_transition_pair",
                },
            },
        ],
    }
    preflight = {
        "schema": "coverage_execution_production_preflight_v2",
        "status": "failed",
        "contract": {
            "worktool_sweep_3d": {
                "hard_clearance_m": 0.24,
                "act_tracking_margin_m": 0.05,
                "pose_interpolation_bound_m": 0.01,
            }
        },
        "cases": [
            {
                "case_id": "cycle0_reset_state",
                "full_candidate_trace": [
                    {
                        "exemplar_id": "episode_24",
                        "worktool_sweep_3d_sampled_convex_cover_clearance_m": 0.63,
                        "worktool_sweep_3d_live_start_displacement_bound_m": 0.69,
                        "worktool_sweep_3d_effective_clearance_m": -0.12,
                    }
                ],
            },
            {
                "case_id": "post_return_reset_0",
                "full_candidate_trace": [
                    {
                        "exemplar_id": "episode_171",
                        "worktool_sweep_3d_sampled_convex_cover_clearance_m": 0.285,
                        "worktool_sweep_3d_live_start_displacement_bound_m": 0.075,
                        "worktool_sweep_3d_effective_clearance_m": 0.15,
                    }
                ],
            },
        ],
    }
    execution_path = tmp_path / "execution.json"
    transitions_path = tmp_path / "transitions.json"
    preflight_path = tmp_path / "preflight.json"
    execution_path.write_text(json.dumps(execution), encoding="utf-8")
    transitions_path.write_text(json.dumps(transitions), encoding="utf-8")
    preflight_path.write_text(json.dumps(preflight), encoding="utf-8")

    artifact = build_start_transition_measurement_input(
        execution_library_path=execution_path,
        return_transition_artifact_path=transitions_path,
        production_preflight_path=preflight_path,
        cycle0_source_episode_path=source_cycle0,
        post_return_source_episode_path=source_post,
        frozen_cycle0_rollout_path=frozen,
        frozen_cycle0_observation_step=2,
        post_return_dig_end_step=22,
        output_dir=tmp_path / "output",
    )

    assert artifact["schema"] == TRANSITION_MEASUREMENT_INPUT_SCHEMA
    by_id = {item["path_id"]: item for item in artifact["paths"]}
    assert list(by_id) == [
        "cycle0_source_expert_preamble",
        "cycle0_frozen_runtime_prefix",
        "post_return_gold_full",
        "post_return_handoff_tail",
        "post_return_handoff_plus_dig",
        "post_return_dig_only",
    ]
    assert len(by_id["cycle0_source_expert_preamble"]["qpos_path"]) == 4
    assert len(by_id["cycle0_frozen_runtime_prefix"]["qpos_path"]) == 3
    assert len(by_id["post_return_gold_full"]["qpos_path"]) == 9
    assert len(by_id["post_return_handoff_tail"]["qpos_path"]) == 5
    assert len(by_id["post_return_handoff_plus_dig"]["qpos_path"]) == 9
    assert len(by_id["post_return_dig_only"]["qpos_path"]) == 5
    assert by_id["post_return_handoff_tail"]["planner_bound_endpoint_match"] is True
    assert (
        by_id["cycle0_source_expert_preamble"]["planner_bound_endpoint_match"] is False
    )
    assert artifact["lineage"]["post_return"]["paired_return_exemplar_id"] == (
        "episode_161"
    )
    assert artifact["training_data_written"] is False

    with pytest.raises(FileExistsError):
        build_start_transition_measurement_input(
            execution_library_path=execution_path,
            return_transition_artifact_path=transitions_path,
            production_preflight_path=preflight_path,
            cycle0_source_episode_path=source_cycle0,
            post_return_source_episode_path=source_post,
            frozen_cycle0_rollout_path=frozen,
            frozen_cycle0_observation_step=2,
            post_return_dig_end_step=22,
            output_dir=tmp_path / "output",
        )


def test_geometry_classification_does_not_relax_contract_when_measured_path_fails() -> (
    None
):
    result = classify_start_transition_geometry(
        contract={
            "hard_clearance_m": 0.24,
            "act_tracking_margin_m": 0.05,
            "pose_interpolation_bound_m": 0.01,
        },
        input_paths={
            "cycle0_source_expert_preamble": {
                "endpoint_role": "expert_tuple_start",
            },
            "cycle0_frozen_runtime_prefix": {
                "endpoint_role": "unmatched_live_start",
            },
        },
        measured_clearance_by_path={
            "cycle0_source_expert_preamble": 0.40,
            "cycle0_frozen_runtime_prefix": 0.42,
            "post_return_gold_full": 0.31,
            "post_return_handoff_tail": 0.36,
            "post_return_handoff_plus_dig": 0.2854,
            "post_return_dig_only": 0.2854,
        },
        conservative_start_bounds={
            "cycle0": 0.6894,
            "post_return": 0.0752,
        },
    )

    assert result["post_return"]["measured_effective_clearance_m"] == (
        pytest.approx(0.2254)
    )
    assert result["post_return"]["eligible"] is False
    assert result["post_return"]["classification"] == (
        "reachable_tuple_nominal_clearance_below_calibrated_contract"
    )
    assert result["cycle0"]["classification"] == (
        "expert_preamble_is_not_current_runtime_alignment_proof"
    )
    assert result["start_bound_contract_change_allowed"] is False
    assert result["bounded_live_allowed"] is False
    assert result["thresholds_relaxed"] is False


def _measured_path(path_id: str, clearance: float) -> dict[str, object]:
    walls = (
        "Dig_XMax_Board",
        "Dig_XMin_Board",
        "Dig_ZMax_Board",
        "Dig_ZMin_Board",
    )
    values = iter(
        [
            clearance,
            clearance + 0.1,
            clearance + 0.2,
            clearance + 0.3,
            clearance + 0.4,
            clearance + 0.5,
            clearance + 0.6,
            clearance + 0.7,
            clearance + 0.8,
            clearance + 0.9,
            clearance + 1.0,
            clearance + 1.1,
        ]
    )
    return {
        "path_id": path_id,
        "sampled_convex_cover_clearance_m": clearance,
        "endpoint_maximum_convex_cover_displacement_m": 0.02,
        "closest": {"link_name": "boom", "wall_name": walls[0]},
        "link_sweeps": [
            {
                "link_name": link,
                "wall_sweeps": [
                    {
                        "wall_name": wall,
                        "sampled_convex_cover_clearance_m": next(values),
                    }
                    for wall in walls
                ],
            }
            for link in ("boom", "stick", "bucket")
        ],
    }


def test_finalizer_requires_complete_three_by_four_witnesses(
    tmp_path: Path,
) -> None:
    path_ids = (
        "cycle0_source_expert_preamble",
        "cycle0_frozen_runtime_prefix",
        "post_return_gold_full",
        "post_return_handoff_tail",
        "post_return_handoff_plus_dig",
        "post_return_dig_only",
    )
    request = {
        "schema": TRANSITION_MEASUREMENT_INPUT_SCHEMA,
        "status": "ready",
        "contract": {
            "hard_clearance_m": 0.24,
            "act_tracking_margin_m": 0.05,
            "pose_interpolation_bound_m": 0.01,
        },
        "lineage": {},
        "paths": [
            {
                "path_id": path_id,
                "endpoint_role": (
                    "unmatched_live_start"
                    if path_id == "cycle0_frozen_runtime_prefix"
                    else "expert_tuple_start"
                ),
                "planner_start_displacement_bound_m": (
                    0.6894 if path_id.startswith("cycle0") else 0.0752
                ),
                "planner_bound_endpoint_match": (path_id == "post_return_handoff_tail"),
            }
            for path_id in path_ids
        ],
    }
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps(request), encoding="utf-8")
    input_sha = hashlib.sha256(input_path.read_bytes()).hexdigest()
    clearances = {
        "cycle0_source_expert_preamble": 0.40,
        "cycle0_frozen_runtime_prefix": 0.42,
        "post_return_gold_full": 0.31,
        "post_return_handoff_tail": 0.36,
        "post_return_handoff_plus_dig": 0.2854,
        "post_return_dig_only": 0.2854,
    }
    measurement = {
        "schema": TRANSITION_MEASUREMENT_OUTPUT_SCHEMA,
        "status": "completed",
        "source_lock": {"input_sha256": input_sha},
        "paths": [_measured_path(path_id, clearances[path_id]) for path_id in path_ids],
    }
    measurement_path = tmp_path / "measurement.json"
    measurement_path.write_text(json.dumps(measurement), encoding="utf-8")

    diagnosis = build_start_transition_geometry_diagnosis(
        measurement_input_path=input_path,
        unity_measurement_path=measurement_path,
        output_dir=tmp_path / "diagnosis",
    )
    assert diagnosis["status"] == "blocked"
    assert diagnosis["post_return"]["measured_effective_clearance_m"] == (
        pytest.approx(0.2254)
    )
    assert "cycle0" not in diagnosis["endpoint_bound_comparison"]
    assert diagnosis["endpoint_bound_comparison"]["post_return"][
        "planner_bound_is_conservative"
    ]

    malformed = json.loads(json.dumps(measurement))
    malformed["paths"][0]["link_sweeps"][0]["wall_sweeps"].pop()
    malformed_path = tmp_path / "malformed.json"
    malformed_path.write_text(json.dumps(malformed), encoding="utf-8")
    with pytest.raises(ValueError, match="all four walls"):
        build_start_transition_geometry_diagnosis(
            measurement_input_path=input_path,
            unity_measurement_path=malformed_path,
            output_dir=tmp_path / "malformed-diagnosis",
        )
