from __future__ import annotations

from copy import deepcopy

import numpy as np

from testbed.eval.terrain_replay_pilot_gate import build_source_semantic_reference
from testbed.eval.terrain_replay_single_attempt import evaluate_single_replay_attempt

TARGETS = (
    "recording_depth_0p08_full_grid_diagnostic",
    "t1_large_shallow_rectangular_pit_default",
    "t2_long_shallow_trench_default",
)


def _source_reference() -> dict[str, object]:
    env_state = np.zeros((101, 89), dtype=np.float32)
    env_state[100, 39:45] = [0.25, 0.3, 0.2, 0.4, 0.1, 0.35]
    env_state[100, 51:57] = 1.0
    return build_source_semantic_reference(
        source_episode_id="episode_1",
        control_hz=50.0,
        env_state=env_state,
        cycle_records=[
            {
                "cycle_id": 0,
                "complete_cycle": True,
                "replay_candidate": True,
                "dump_end_step": 100,
                "end_step_exclusive": 101,
            }
        ],
    )


def _candidate(target_id: str) -> dict[str, object]:
    return {
        "schema": "terrain_gold_cycle_sample_v1",
        "episode_id": "episode_1",
        "target_id": target_id,
        "cycle_index": 0,
        "cycle_start_observation_index": 0,
        "cycle_end_observation_index": 100,
        "payload_mass_kg": 24.0,
        "effective_deposit_mass_kg": 18.0,
        "removed_depth_grid_start_m": [0.0] * 6,
        "removed_depth_grid_end_m": [0.25, 0.3, 0.2, 0.4, 0.1, 0.35],
        "valid_mask": [1.0] * 6,
        "target_region_mask": [1.0] * 6,
        "surface_valid_fraction_start": [1.0] * 6,
        "surface_valid_fraction_end": [1.0] * 6,
        "grid_geometry_start": [0.0] * 13,
        "grid_geometry_end": [0.0] * 13,
        "grid_geometry_stable": True,
        "target_removed_completion_ratio_end": 0.9,
        "target_positive_residual_depth_sum_end_m": 0.1,
        "target_overdig_depth_sum_m": 0.02,
        "outside_target_removed_depth_sum_m": 0.1,
    }


def _repeat() -> dict[str, object]:
    return {
        "repeat_id": "attempt_00",
        "diagnostic_summary": {
            "qpos_max_error_max": 0.7,
            "qpos_pre_contact_max_error_max": 0.01,
            "first_qualified_contact_step": 10,
            "exception_count": 0,
            "pose_realign_count": 0,
            "step_sequence_complete": True,
            "source_step_count": 101,
            "final_removed_depth_grid_m": [0.25, 0.3, 0.2, 0.4, 0.1, 0.35],
        },
        "candidate_records": [_candidate(target) for target in TARGETS],
    }


def test_single_attempt_gate_accepts_one_semantic_pass_without_claiming_variance() -> (
    None
):
    result = evaluate_single_replay_attempt(
        _repeat(),
        source_reference=_source_reference(),
        required_source_episode_id="episode_1",
        hdf5_audit={"status": "passed", "pass": True, "errors": []},
    )

    assert result["schema"] == "terrain_replay_single_attempt_gate_v1"
    assert result["pass"] is True
    assert result["repeatability_status"] == "not_assessed_single_attempt"
    assert result["effect_label_status"] == "single_realization_silver"
    assert result["gold_status"] == "not_gold"
    assert "variance_tier_counts" not in result


def test_single_attempt_gate_rejects_semantic_or_hdf5_failure() -> None:
    repeat = deepcopy(_repeat())
    repeat["diagnostic_summary"]["final_removed_depth_grid_m"] = [0.0] * 6
    semantic_failure = evaluate_single_replay_attempt(
        repeat,
        source_reference=_source_reference(),
        required_source_episode_id="episode_1",
        hdf5_audit={"status": "passed", "pass": True, "errors": []},
    )
    assert semantic_failure["pass"] is False
    assert "semantic_attempt_failed" in semantic_failure["failed_checks"]

    hdf5_failure = evaluate_single_replay_attempt(
        _repeat(),
        source_reference=_source_reference(),
        required_source_episode_id="episode_1",
        hdf5_audit={
            "status": "failed",
            "pass": False,
            "errors": ["env_state_dim_mismatch"],
        },
    )
    assert hdf5_failure["pass"] is False
    assert "hdf5_audit_failed" in hdf5_failure["failed_checks"]
