from __future__ import annotations

import json
from copy import deepcopy

import numpy as np

from testbed.cli.terrain_replay_pilot_gate import (
    _load_episode_candidate_records,
)
from testbed.eval.terrain_replay_pilot_gate import (
    build_source_semantic_reference,
    evaluate_replay_pilot_gate,
)

TARGETS = (
    "recording_depth_0p08_full_grid_diagnostic",
    "t1_large_shallow_rectangular_pit_default",
    "t2_long_shallow_trench_default",
)


def _record(
    target_id: str,
    *,
    cycle_index: int = 0,
    cycle_end: int = 102,
    completion: float = 0.9,
) -> dict[str, object]:
    return {
        "schema": "terrain_gold_cycle_sample_v1",
        "source_episode_id": "episode_28",
        "episode_id": "episode_28",
        "target_id": target_id,
        "cycle_index": cycle_index,
        "cycle_start_observation_index": 0,
        "cycle_end_observation_index": cycle_end,
        "payload_mass_kg": 24.0,
        "effective_deposit_mass_kg": 18.0,
        "removed_depth_grid_start_m": [0.0] * 6,
        "removed_depth_grid_end_m": [0.1, 0.0, 0.2, 0.0, 0.0, 0.0],
        "valid_mask": [1.0] * 6,
        "target_region_mask": [1.0] * 6,
        "surface_valid_fraction_start": [1.0] * 6,
        "surface_valid_fraction_end": [1.0] * 6,
        "grid_geometry_start": [0.0] * 13,
        "grid_geometry_end": [0.0] * 13,
        "grid_geometry_stable": True,
        "target_removed_completion_ratio_end": completion,
        "target_positive_residual_depth_sum_end_m": 0.1,
        "target_overdig_depth_sum_m": 0.02,
        "outside_target_removed_depth_sum_m": 0.1,
    }


def _source_reference() -> dict[str, object]:
    env_state = np.zeros((101, 89), dtype=np.float32)
    env_state[100, 39:45] = [0.25, 0.3, 0.2, 0.4, 0.1, 0.35]
    env_state[100, 51:57] = 1.0
    return build_source_semantic_reference(
        source_episode_id="episode_28",
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


def _repeats() -> list[dict[str, object]]:
    return [
        {
            "repeat_id": f"repeat_{index}",
            "diagnostic_summary": {
                "qpos_max_error_max": 0.65,
                "qpos_pre_contact_max_error_max": 0.01,
                "first_qualified_contact_step": 10,
                "exception_count": 0,
                "pose_realign_count": 0,
                "step_sequence_complete": True,
                "source_step_count": 101,
                "final_removed_depth_grid_m": [
                    0.25,
                    0.3,
                    0.2,
                    0.4,
                    0.1,
                    0.35,
                ],
            },
            "candidate_records": [_record(target_id) for target_id in TARGETS],
        }
        for index in range(5)
    ]


def test_source_semantic_reference_uses_last_complete_cycle_endpoint() -> None:
    env_state = np.zeros((120, 64), dtype=np.float32)
    env_state[100, 39:45] = [0.25, 0.3, 0.2, 0.4, 0.1, 0.35]
    env_state[100, 51:57] = 1.0
    reference = build_source_semantic_reference(
        source_episode_id="episode_28",
        control_hz=50.0,
        env_state=env_state,
        cycle_records=[
            {
                "cycle_id": 0,
                "complete_cycle": True,
                "replay_candidate": True,
                "dump_end_step": 80,
                "end_step_exclusive": 101,
            },
            {
                "cycle_id": 1,
                "complete_cycle": False,
                "replay_candidate": False,
                "dump_end_step": -1,
                "end_step_exclusive": 120,
            },
        ],
    )

    assert reference["status"] == "present"
    assert reference["complete_cycle_count"] == 1
    assert reference["source_end_step_exclusive"] == 101
    assert set(reference["target_summaries"]) == {
        "t1_large_shallow_rectangular_pit_default",
        "t2_long_shallow_trench_default",
    }


def test_pilot_gate_accepts_five_consistent_repeats() -> None:
    result = evaluate_replay_pilot_gate(
        _repeats(),
        source_reference=_source_reference(),
    )

    assert result["schema"] == "terrain_replay_pilot_gate_v2"
    assert result["status"] == "present"
    assert result["pass"] is True
    assert result["process_integrity_pass"] is True
    assert result["episode_semantic_pass"] is True
    assert result["failed_checks"] == []
    assert result["repeat_count"] == 5
    assert result["post_contact_qpos_gate"] == "diagnostic_only"
    assert result["qpos_max_error_max"] == 0.65
    assert result["qpos_pre_contact_max_error_max"] == 0.01
    assert result["semantic_pass_repeat_count"] == 5
    assert result["official_ab_fraction"] == 1.0
    assert result["cycle_completion_ratio_min"] == 0.85
    assert result["target_completion_drop_max"] == 0.05
    assert result["positive_residual_tolerance_m"] == 0.05
    assert result["shape_relative_tolerance"] == 0.15
    assert result["shape_absolute_tolerance_m"] == 0.05
    assert result["action_replay_contract"] == (
        "exact_source_action_per_fixed_unity_step"
    )
    assert result["semantic_endpoint_source"] == "diagnostic_terminal_env_state"


def test_pilot_gate_allows_boundary_jitter_and_rejects_precontact_qpos_or_validity() -> None:
    repeats = deepcopy(_repeats())
    repeats[4]["candidate_records"][0]["cycle_end_observation_index"] = 125
    repeats[3]["diagnostic_summary"]["qpos_pre_contact_max_error_max"] = 0.03
    repeats[2]["candidate_records"][1]["surface_valid_fraction_end"][0] = 0.4

    result = evaluate_replay_pilot_gate(
        repeats,
        source_reference=_source_reference(),
    )

    assert result["pass"] is False
    assert result["process_integrity_pass"] is False
    assert set(result["failed_checks"]) >= {
        "pre_contact_qpos_max_error_exceeded",
        "target_cell_valid_fraction_below_minimum",
    }
    assert "cycle_boundary_inconsistent" not in result["failed_checks"]


def test_pilot_gate_rejects_semantically_worse_final_terrain() -> None:
    repeats = deepcopy(_repeats())
    for repeat in repeats[:4]:
        repeat["diagnostic_summary"]["final_removed_depth_grid_m"] = [0.0] * 6

    result = evaluate_replay_pilot_gate(
        repeats,
        source_reference=_source_reference(),
    )

    assert result["pass"] is False
    assert result["process_integrity_pass"] is True
    assert result["episode_semantic_pass"] is False
    assert "semantic_pass_repeat_count_below_minimum" in result["failed_checks"]


def test_pilot_gate_uses_true_replay_endpoint_not_last_detected_cycle_snapshot() -> None:
    repeats = deepcopy(_repeats())
    for repeat in repeats:
        for record in repeat["candidate_records"]:
            record["target_removed_completion_ratio_end"] = 0.0
            record["target_positive_residual_depth_sum_end_m"] = 10.0

    result = evaluate_replay_pilot_gate(
        repeats,
        source_reference=_source_reference(),
    )

    assert result["pass"] is True
    assert result["semantic_pass_repeat_count"] == 5


def test_pilot_gate_rejects_missing_replay_steps() -> None:
    repeats = deepcopy(_repeats())
    repeats[0]["diagnostic_summary"]["source_step_count"] = 100

    result = evaluate_replay_pilot_gate(
        repeats,
        source_reference=_source_reference(),
    )

    assert result["pass"] is False
    assert result["process_integrity_pass"] is False
    assert "replay_step_sequence_incomplete" in result["failed_checks"]


def test_pilot_gate_effect_label_yield_does_not_reject_semantic_replay() -> None:
    repeats = deepcopy(_repeats())
    for index, repeat in enumerate(repeats):
        for record in repeat["candidate_records"]:
            record["payload_mass_kg"] = 10.0 + 20.0 * index
            record["effective_deposit_mass_kg"] = 5.0 + 15.0 * index

    result = evaluate_replay_pilot_gate(
        repeats,
        source_reference=_source_reference(),
    )

    assert result["pass"] is True
    assert result["official_ab_fraction"] == 0.0
    assert result["effect_label_yield_is_hard_gate"] is False


def test_pilot_gate_is_hard_locked_to_episode_28() -> None:
    repeats = _repeats()
    repeats[0]["candidate_records"][0]["source_episode_id"] = "episode_29"
    repeats[0]["candidate_records"][0]["episode_id"] = "episode_29"

    result = evaluate_replay_pilot_gate(
        repeats,
        source_reference=_source_reference(),
    )

    assert result["pass"] is False
    assert "pilot_source_episode_mismatch" in result["failed_checks"]


def test_cli_filters_shared_repeat_jsonl_to_requested_source_episode(tmp_path) -> None:
    path = tmp_path / "all_episodes.jsonl"
    rows = [
        {"episode_id": "episode_28", "target_id": "t1"},
        {"source_episode_id": "episode_29", "target_id": "t2"},
        {"episode_id": "episode_29", "target_id": "t1"},
    ]
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )

    assert _load_episode_candidate_records(path, "episode_29") == rows[1:]
