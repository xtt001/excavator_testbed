from __future__ import annotations

import json
from types import SimpleNamespace

import numpy as np

from testbed.eval.rollout_artifacts import (
    build_rollout_metric_summaries,
    write_rollout_log_artifacts,
)
from testbed.eval.rollout_step_records import (
    build_planner_debug_json,
    build_planner_debug_payload,
    build_policy_input,
    build_rollout_step_record,
)
from testbed.eval.suite import EvalSuite


def test_build_policy_input_adds_camera_images_and_live_goal_tokens() -> None:
    image = np.arange(12, dtype=np.uint8).reshape(2, 2, 3)
    goal_tokens = np.arange(12, dtype=np.float32)
    obs = {"qpos": np.zeros(4), "images": {"fpv": image}}

    policy_input = build_policy_input(
        obs=obs,
        camera_names=["fpv", "side"],
        goal_tokens=goal_tokens,
    )

    assert policy_input["image_fpv"].shape == (3, 2, 2)
    assert np.isclose(policy_input["image_fpv"][0, 0, 1], image[0, 1, 0] / 255.0)
    np.testing.assert_array_equal(policy_input["goal_tokens"], goal_tokens)
    assert "image_side" not in policy_input


def test_build_rollout_step_record_preserves_debug_and_boundary_fields() -> None:
    boundary_event = SimpleNamespace(
        cycle_id=2,
        mode_id=3,
        qualified_dig_start=1,
        dump_start=0,
        dump_end=1,
        pause=0,
        boundary=1,
    )
    policy_debug = {
        "dig_cut_planner_mode": "operator_prior_coverage",
        "dig_cut_token_source": "surface_depth_prior",
        "dig_cut_tokens": np.arange(10, dtype=np.float32),
        "return_start_envelope_token_injected": True,
        "return_start_envelope_token_source": "cell_prior",
        "return_start_envelope_tokens": np.arange(18, dtype=np.float32),
        "return_to_dig_start_envelope_gate_enabled": True,
        "return_to_dig_start_envelope_ready": False,
        "return_to_dig_start_envelope_error": 0.12,
        "return_to_dig_start_envelope_checks": {"qpos": False},
        "hybrid_mode": "TRANSITION",
        "transition_source": "scripted_band_servo",
        "transition_completed": True,
        "skill_name": "return",
        "skill_id": 3,
        "skill_switch_reason": "dump_complete",
    }
    post_obs = {
        "qpos": np.asarray([1.0, 2.0, 3.0, 4.0], dtype=np.float32),
        "qvel": np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
        "env_state": np.arange(64, dtype=np.float32),
        "step_id": 7,
        "sim_time_ns": 140_000_000,
    }
    policy_input = {"goal_tokens": np.arange(12, dtype=np.float32)}

    record = build_rollout_step_record(
        rollout_id=5,
        step_index=6,
        post_obs=post_obs,
        action=np.asarray([0.0, 0.1, 0.2, 0.3], dtype=np.float32),
        policy_input=policy_input,
        policy_debug=policy_debug,
        boundary_event=boundary_event,
        reward=1.5,
        reward_phase="return",
        task_success=False,
        task_step_successes=["dump_complete"],
        task_step_failures=["spill_before_target"],
        task_metrics={"mass_in_bucket_kg": 10.0},
        warnings=["near_target"],
    )

    assert record["rollout_id"] == 5
    assert record["t"] == 6
    assert record["step_id"] == 7
    assert record["cycle_id"] == 2
    assert record["dump_end_mask"] == 1
    assert record["boundary_mask"] == 1
    assert record["dig_cut_token_source"] == "surface_depth_prior"
    assert record["return_start_envelope_token_source"] == "cell_prior"
    assert record["return_to_dig_start_envelope_checks"] == {"qpos": False}
    assert record["transition_source"] == "scripted_band_servo"
    assert record["skill_switch_reason"] == "dump_complete"
    np.testing.assert_array_equal(record["dig_cut_tokens"], np.arange(10, dtype=np.float32))
    np.testing.assert_array_equal(record["goal_tokens"], np.arange(12, dtype=np.float32))


def test_planner_debug_json_matches_eval_suite_facade() -> None:
    policy_debug = {
        "dig_cut_planner_mode": "operator_prior_coverage",
        "skill_name": "dig",
        "primitive_cycle_index": 1,
        "coverage_corridor_id": 4,
        "coverage_entry_x_m": 0.25,
        "coverage_entry_z_m": np.nan,
        "dig_cut_token_source": "coverage_prior",
        "dig_cut_prior_id": "cell_4",
        "dig_cut_tokens": [0.0, 1.0, np.nan],
        "coverage_candidate_scores": [
            {"corridor_id": 4, "cell_id": 1, "score": 0.8},
            "ignore",
        ],
        "coverage_corridors": [
            {"corridor_id": 4, "cell_id": 1, "entry_x_m": 0.25},
        ],
    }
    obs = {"env_state": np.arange(64, dtype=np.float32)}

    helper_json = build_planner_debug_json(policy_debug, obs=obs)
    facade_json = EvalSuite._planner_debug_json(policy_debug, obs=obs)

    assert helper_json == facade_json
    payload = build_planner_debug_payload(policy_debug, obs=obs)
    assert payload is not None
    assert payload["mode"] == "operator_prior_coverage"
    assert payload["selected_corridor_id"] == 4
    assert payload["entry_z_m"] == 0.0
    assert payload["dig_cut_tokens"] == [0.0, 1.0, 0.0]
    assert payload["current_bucket_tip_valid"] is True
    assert len(payload["candidate_scores"]) == 1


def test_write_rollout_log_artifacts_keeps_summary_and_trace_outputs(tmp_path) -> None:
    class FakePolicy:
        def rollout_summary(self) -> dict[str, object]:
            return {"transition_source": "scripted_band_servo"}

    step_records = [
        {
            "t": 0,
            "reward": 1.0,
            "task_success": False,
            "task_step_successes": [],
            "task_step_failures": [],
            "action": np.zeros(4, dtype=np.float32),
            "hybrid_mode": "TRANSITION",
            "transition_source": "policy_debug",
            "transition_completed": True,
            "qualified_dig_start_mask": 1,
            "dump_end_mask": 1,
            "pause_mask": 1,
            "boundary_mask": 1,
        }
    ]
    metric_summaries = build_rollout_metric_summaries(
        step_records=step_records,
        policy=FakePolicy(),
        success_summary={"dump_complete_final_hold_success": True},
    )

    summary = write_rollout_log_artifacts(
        rollout_log_dir=tmp_path,
        rollout_id=0,
        success=True,
        rewards=[1.0],
        step_records=step_records,
        video_path="rollout.mp4",
        hdf5_path="rollout.hdf5",
        cell_entry_summary={"cell_entry_token_count": 1},
        success_summary={"success_mode": "strict_dump_complete", "success": True},
        continuity_summary={"pause_ratio": 1.0},
        metric_summaries=metric_summaries,
        target_gate_summary={"target_cycle_gate_success": 1},
        planner_trace={"events": [{"reason": "unit"}]},
        rollout_stop_reason="target_cycle_gate_reached",
    )

    assert (tmp_path / "rollout_000.jsonl").exists()
    assert (tmp_path / "rollout_000_summary.json").exists()
    assert (tmp_path / "rollout_000_planner_trace.json").exists()
    assert summary["jsonl_path"].endswith("rollout_000.jsonl")
    assert summary["summary_path"].endswith("rollout_000_summary.json")
    assert summary["planner_trace_path"].endswith("rollout_000_planner_trace.json")
    assert summary["transition_source"] == "scripted_band_servo"
    assert summary["rollout_stop_reason"] == "target_cycle_gate_reached"

    written_summary = json.loads((tmp_path / "rollout_000_summary.json").read_text())
    assert written_summary["success_mode"] == "strict_dump_complete"
    assert written_summary["target_cycle_gate_success"] == 1
