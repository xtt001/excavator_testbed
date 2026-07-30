from __future__ import annotations

import copy
import inspect
from pathlib import Path

import pytest

from testbed.eval.return_approach_probe import (
    ReturnApproachProbeError,
    _apply_axis_exercise_gate,
    _collect_axis_result,
    analyze_return_approach_trace,
    build_return_approach_probe_config,
    build_return_axis_train_support,
    validate_return_approach_probe_config,
)
from testbed.eval.suite import EvalSuite


def _checks(
    *,
    qpos_1: float,
    upper: float = 0.6481370115280152,
    contact: bool = False,
) -> dict[str, dict[str, float | bool]]:
    result: dict[str, dict[str, float | bool]] = {
        "long_norm": {"ok": True},
        "short_norm": {"ok": True},
        "local_depth_m": {"ok": True},
        "plane_depth_m": {"ok": True},
        "dig_contact": {"ok": contact, "value": float(contact)},
        "qpos_0": {"ok": True},
        "qpos_1": {
            "ok": 0.39158900737762453 <= qpos_1 <= upper,
            "value": qpos_1,
            "min": 0.39158900737762453,
            "max": upper,
        },
        "qpos_2": {"ok": True},
        "qpos_3": {"ok": True},
        "qvel_abs_max": {"ok": True},
    }
    return result


def _row(
    step_id: int,
    *,
    skill: str,
    dump: bool = False,
    source: str = "strict18_train_return_start_envelope_cell_0",
    qpos_1: float = 0.5,
    qvel_1: float = 0.0,
    action_1: float = -0.5,
    upper: float = 0.6481370115280152,
    contact: bool = False,
) -> dict[str, object]:
    return {
        "step_id": step_id,
        "skill_name": skill,
        "dump_end_mask": int(dump),
        "return_start_envelope_token_source": source,
        "return_to_dig_start_envelope_checks": _checks(
            qpos_1=qpos_1,
            upper=upper,
            contact=contact,
        ),
        "qpos": [0.55, qpos_1, 0.34, 0.21],
        "qvel": [0.0, qvel_1, 0.0, 0.0],
        "action": [0.1, action_1, -0.36, 0.06],
    }


def test_trace_audit_proves_commanded_qpos_overshoot_precedes_contact() -> None:
    rows: list[dict[str, object]] = []
    for index in range(1, 7):
        rows.append(_row(index * 10, skill="dump", dump=True))
    rows.extend(
        [
            _row(70, skill="return", qpos_1=0.55),
            _row(71, skill="dig", qpos_1=0.56),
            _row(100, skill="dump", dump=True),
            _row(
                101,
                skill="return",
                qpos_1=0.24,
                upper=0.6223429822921753,
            ),
            _row(102, skill="return", qpos_1=0.25),
            _row(
                110,
                skill="return",
                qpos_1=0.6354,
                qvel_1=0.208,
                action_1=-0.548,
            ),
            _row(
                111,
                skill="return",
                qpos_1=0.6479,
                qvel_1=0.207,
                action_1=-0.546,
            ),
            _row(
                112,
                skill="return",
                qpos_1=0.6521,
                qvel_1=0.206,
                action_1=-0.545,
                contact=True,
            ),
        ]
    )

    report = analyze_return_approach_trace(
        rows,
        same_cell_train_qpos1_max=0.6380621194839478,
    )

    assert report["completed_dump_count"] == 7
    assert report["final_return_start_step_id"] == 101
    assert report["axis_upper_bound"] == pytest.approx(0.6481370115280152)
    assert report["activation_threshold"] == pytest.approx(
        0.6281370115280152
    )
    assert report["servo_target_qpos"] == pytest.approx(
        0.6321370115280152
    )
    assert report["first_activation_candidate_step_id"] == 110
    assert report["first_qpos_1_violation_step_id"] == 112
    assert report["first_contact_ready_step_id"] == 112
    assert report["negative_act_command_before_qpos_violation"] is True
    assert report["servo_target_within_same_cell_train_support"] is True
    assert report["handoff_qpos_bound_changed"] is False
    assert report["causal_hypothesis"] == (
        "return_boom_command_overshoot_before_contact"
    )


def _source_config() -> dict[str, object]:
    return {
        "agx": {"host": "127.0.0.1", "port": 5057, "timeout": 10.0},
        "task": {
            "camera_names": [
                "stick_up",
                "stick_down",
                "eye_left",
                "eye_right",
            ],
            "episode_len": 24000,
        },
        "eval": {
            "num_rollouts": 1,
            "seed": 1000,
            "target_cycle_gate": 10,
            "no_overwrite": True,
            "results_dir": "/old/results",
            "video_dir": "/old/videos",
            "rollout_log_dir": "/old/rollouts",
            "record_hdf5": False,
            "hdf5_dir": "/old/disabled_hdf5",
            "record_hdf5_metadata": {"preserved": "yes"},
        },
        "policy": {
            "dig_ckpt_path": "/ckpt/dig",
            "carry_ckpt_path": "/ckpt/carry",
            "dump_ckpt_path": "/ckpt/dump",
            "return_ckpt_path": "/ckpt/return",
            "act_params": {
                "chunk_size": 100,
                "temporal_agg_weight_order": "legacy_oldest_first",
            },
            "switch": {
                "return_max_steps": 420,
                "dig_bad_replan_max_steps": 220,
            },
            "box_emptying": {
                "enabled": False,
                "safety_enabled": True,
                "safety": {
                    "wall_high_force_n": 100_000.0,
                    "wall_first_touch_mode": "record_bucket_all_contacts",
                },
            },
        },
    }


def test_probe_config_is_one_control_factor_plus_output_and_horizon_metadata(
    tmp_path: Path,
) -> None:
    source = _source_config()
    run_root = tmp_path / "run"

    candidate = build_return_approach_probe_config(
        source,
        run_root=run_root,
    )
    validate_return_approach_probe_config(
        source=source,
        candidate=candidate,
        run_root=run_root,
    )

    assert candidate["policy"]["switch"] == source["policy"]["switch"]
    assert (
        candidate["policy"]["box_emptying"]["safety"]
        == source["policy"]["box_emptying"]["safety"]
    )
    control = candidate["policy"]["box_emptying"][
        "return_approach_axis_limit"
    ]
    assert control == {
        "enabled": True,
        "diagnostic_only": True,
        "axis_index": 1,
        "min_completed_dump_count": 7,
        "required_cell_id": None,
        "lineage_warmup_ticks": 1,
        "activation_margin": 0.020,
        "target_margin": 0.016,
        "activation_velocity_min": 0.0,
        "kp": 4.0,
        "kd": 2.0,
        "action_sign": -1.0,
        "action_clip": 0.35,
    }
    assert candidate["eval"]["target_cycle_gate"] == 8
    assert candidate["eval"]["results_dir"] == str(run_root / "results")

    drifted = copy.deepcopy(candidate)
    drifted["policy"]["switch"]["return_max_steps"] = 421
    with pytest.raises(
        ReturnApproachProbeError,
        match="single_factor_config_drift",
    ):
        validate_return_approach_probe_config(
            source=source,
            candidate=drifted,
            run_root=run_root,
        )


def test_train_support_requires_every_locked_goal_cell_target_to_be_supported() -> None:
    audit = {
        "records": [
            {
                "partition": "train",
                "return_envelope_cell_id": 0,
                "qpos_1": value,
            }
            for value in (0.0, 1.0)
        ]
        + [
            {
                "partition": "train",
                "return_envelope_cell_id": 1,
                "qpos_1": value,
            }
            for value in (0.0, 0.2)
        ]
        + [
            {
                "partition": "validation",
                "return_envelope_cell_id": 1,
                "qpos_1": 1.0,
            }
        ]
    }

    support = build_return_axis_train_support(
        audit,
        axis_index=1,
        qpos_tolerance=0.04,
        activation_margin=0.020,
        target_margin=0.016,
        expected_cell_ids=(0, 1),
    )

    assert support["status"] == "blocked"
    assert support["cells"]["0"]["target_within_train_support"] is True
    assert support["cells"]["1"]["target_within_train_support"] is False
    assert support["blockers"] == [
        "return_axis_target_outside_train_support:cell_1"
    ]


def test_axis_result_and_eval_recorder_fail_closed_on_unlogged_intervention() -> None:
    rows = [
        {
            "step_id": 1,
            "skill_name": "return",
            "qpos": [0.0, 0.62, 0.0, 0.0],
            "return_approach_axis_limit_enabled": True,
            "return_approach_axis_limit_intervention_count": 0,
        }
    ]

    result = _collect_axis_result(rows)

    assert result["enabled"] is True
    assert result["intervention_count"] == 0
    assert result["exercised"] is False
    gated = _apply_axis_exercise_gate(
        {"status": "passed", "termination_category": "timeout"},
        result,
    )
    assert gated["status"] == "failed"
    assert gated["termination_category"] == "diagnostic_not_exercised"
    assert gated["blockers"] == [
        "return_approach_axis_limit_not_exercised"
    ]
    assert (
        "build_return_approach_axis_limit_log_fields"
        in inspect.getsource(EvalSuite)
    )
