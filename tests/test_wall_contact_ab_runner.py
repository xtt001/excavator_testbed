from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import yaml

from testbed.eval.wall_contact_ab_runner import (
    WallContactABRunnerError,
    collect_paired_ab_attempt_set,
    extract_paired_ab_attempt,
    reextract_paired_ab_attempt_set,
    run_paired_ab_schedule,
    validate_paired_ab_schedule,
)

_RAW_SHA = (
    "c167e087f3d41f6db8fe0ad260d5f72c3440b6fab9115fdf55959feacc50991c"
)
_SEQUENCE = (
    (0, "A"),
    (0, "B"),
    (1, "B"),
    (1, "A"),
    (2, "A"),
    (2, "B"),
)


def _contact_detail(
    *,
    step_id: int = 2,
    force_n: float = 1000.0,
    component: str = "bucket",
    session_id: int = 1,
    session_count: int = 1,
    consecutive_contact_steps: int = 1,
) -> dict[str, object]:
    wall = "Dig_ZMin_Board"
    return {
        "schema": "worktool_wall_contact_detail_v1",
        "step_id": step_id,
        "sim_time_s": step_id * 0.02,
        "delta_time_s": 0.02,
        "session_id": session_id,
        "session_count": session_count,
        "consecutive_contact_steps": consecutive_contact_steps,
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
                "callback_count": 1,
                "contact_point_count": 1,
                "max_normal_force_n": force_n,
                "max_tangential_force_n": 20.0,
                "max_total_force_n": force_n,
                "contact_points_world_m": [[1.0, 2.0, 3.0]],
                "representative_contact_point_component_local_m": [
                    0.1,
                    0.2,
                    0.3,
                ],
                "tangential_displacement_m": 0.001,
            }
        ],
    }


def _row(
    *,
    t: int,
    condition: str,
    skill: str,
    action: list[float],
    contact: bool = False,
    dump_end: bool = False,
    reason: str = "",
    awaiting_ack: bool = False,
    neutral_ack: bool = False,
    diagnostic_allowed: bool = False,
    contact_force_n: float = 1000.0,
    contact_component: str = "bucket",
    wall_session_count: int = 1,
    contact_consecutive_steps: int = 1,
    hard_bottom: bool = False,
    session_end_clear_ticks: int | None = None,
) -> dict[str, object]:
    env = np.zeros(107, dtype=np.float32)
    env[28:31] = [0.1, 0.2, 0.3]
    env[39:45] = 0.0
    env[97] = 7400.0
    warnings: list[str] = []
    if contact:
        detail = _contact_detail(
            step_id=t + 1,
            force_n=contact_force_n,
            component=contact_component,
            session_id=wall_session_count,
            session_count=wall_session_count,
            consecutive_contact_steps=contact_consecutive_steps,
        )
        env[101:104] = [1.0, contact_force_n, wall_session_count]
        warnings.append(
            "worktool_wall_contact_detail_v1:"
            + json.dumps(detail, separators=(",", ":"))
        )
    if hard_bottom:
        env[104:107] = [1.0, 2000.0, 1.0]
    mode = (
        "interrupt"
        if condition == "A"
        else "record_bucket_first_session"
    )
    row: dict[str, object] = {
        "rollout_id": 0,
        "t": t,
        "step_id": t + 1,
        "sim_time_ns": (t + 1) * 20_000_000,
        "qpos": [0.5, 0.4, 0.6, 0.2],
        "qvel": [0.01, 0.01, 0.01, 0.01],
        "env_state": env.tolist(),
        "action": action,
        "warnings": warnings,
        "primitive_cycle_index": 1 if t else 0,
        "cycle_id": 1 if t else 0,
        "skill_name": skill,
        "hybrid_mode": skill,
        "dump_end_mask": int(dump_end),
        "coverage_execution_exemplar_id": (
            "episode_168" if t else ""
        ),
        "coverage_execution_raw_fields_sha256": _RAW_SHA if t else "",
        "box_safety_wall_contact_diagnostic_ab_enabled": True,
        "box_safety_wall_first_touch_mode": mode,
        "box_safety_wall_contact_diagnostic_allowed": diagnostic_allowed,
        "box_safety_reason": reason,
        "box_safety_awaiting_neutral_ack": awaiting_ack,
        "box_safety_neutral_acknowledged": neutral_ack,
        "box_safety_terminal": neutral_ack and bool(reason),
        "box_safety_hard_bottom_contact": hard_bottom,
        "transition_timeout": False,
    }
    if session_end_clear_ticks is not None:
        row["box_safety_wall_contact_session_end_clear_ticks"] = (
            session_end_clear_ticks
        )
    return row


def _attempt_rows(condition: str) -> list[dict[str, object]]:
    if condition == "A":
        return [
            _row(t=0, condition=condition, skill="return", action=[0.0] * 4),
            _row(
                t=1,
                condition=condition,
                skill="dig",
                action=[0.1] * 4,
                contact=True,
            ),
            _row(
                t=2,
                condition=condition,
                skill="dig",
                action=[0.0] * 4,
                reason="wall_contact_first_session",
                awaiting_ack=True,
            ),
            _row(
                t=3,
                condition=condition,
                skill="dig",
                action=[0.0] * 4,
                reason="wall_contact_first_session",
                neutral_ack=True,
            ),
        ]
    return [
        _row(t=0, condition=condition, skill="return", action=[0.0] * 4),
        _row(
            t=1,
            condition=condition,
            skill="dig",
            action=[0.1] * 4,
            contact=True,
            diagnostic_allowed=True,
        ),
        _row(t=2, condition=condition, skill="dig", action=[0.1] * 4),
        _row(t=3, condition=condition, skill="carry", action=[0.1] * 4),
        _row(
            t=4,
            condition=condition,
            skill="dump",
            action=[0.0] * 4,
            dump_end=True,
        ),
    ]


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def _write_schedule(tmp_path: Path) -> Path:
    root = tmp_path / "experiment" / "paired_ab"
    configs = root / "configs"
    attempts = []
    for index, (seed, condition) in enumerate(_SEQUENCE, start=1):
        attempt_id = f"seed_{seed}_{condition}"
        pair_id = f"seed_{seed}"
        run_root = root / "runs" / attempt_id
        config_path = configs / f"{attempt_id}.yaml"
        mode = (
            "interrupt"
            if condition == "A"
            else "record_bucket_first_session"
        )
        config = {
            "eval": {
                "num_rollouts": 1,
                "seed": seed,
                "target_cycle_gate": 2,
                "target_cycle_gate_terminal_hold_steps": 0,
                "no_overwrite": True,
                "record_hdf5": False,
                "results_dir": str(run_root / "results"),
                "video_dir": str(run_root / "videos"),
                "rollout_log_dir": str(
                    run_root / "results" / "rollouts"
                ),
                "hdf5_dir": str(run_root / "disabled_hdf5"),
                "record_hdf5_metadata": {
                    "validation_schema": (
                        "wall_contact_paired_ab_attempt_v1"
                    ),
                    "contact_semantics_attempt_id": attempt_id,
                    "contact_semantics_pair_id": pair_id,
                    "contact_semantics_condition": condition,
                    "contact_semantics_sequence_index": index,
                    "contact_semantics_reset_seed": seed,
                    "diagnostic_only": True,
                    "promotion_eligible": False,
                    "frozen_target_handoff_sha256": "f" * 64,
                    "expected_reset_state_sha256": "e" * 64,
                },
            },
            "policy": {
                "dig_cut_planner": {
                    "coverage": {
                        "actual_tuple_execution_library": {
                            "runtime_role": "diagnostic_legacy"
                        }
                    }
                },
                "box_emptying": {
                    "bounded_dig_probe_stop": {"enabled": False},
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
                    "safety": {
                        "wall_contact_diagnostic_ab_enabled": True,
                        "wall_first_touch_mode": mode,
                    },
                }
            },
        }
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
        command = [
            "python",
            "-m",
            "testbed.cli.eval",
            "--config",
            str(config_path),
            "--num-rollouts",
            "1",
            "--target-cycle-gate",
            "2",
            "--output-dir",
            str(run_root),
        ]
        attempts.append(
            {
                "attempt_id": attempt_id,
                "pair_id": pair_id,
                "sequence_index": index,
                "seed": seed,
                "condition": condition,
                "wall_first_touch_mode": mode,
                "config_path": str(config_path),
                "run_root": str(run_root),
                "max_attempts": 1,
                "retry_allowed": False,
                "command_argv": command,
            }
        )
    schedule = {
        "schema": "wall_contact_paired_ab_schedule_v1",
        "status": "prepared",
        "diagnostic_only": True,
        "non_promotable": True,
        "attempt_count": 6,
        "retry_allowed": False,
        "execution_order_is_mandatory": True,
        "target_contract": {
            "exemplar_id": "episode_168",
            "runtime_role": "diagnostic_legacy",
            "use_scope": "paired_ab_only",
            "production_lookup_allowed": False,
            "reset_checkpoint_semantics": "first_post_reset_control_step",
        },
        "attempts": attempts,
    }
    path = root / "schedule.json"
    path.write_text(json.dumps(schedule), encoding="utf-8")
    return path


def test_extract_a_proves_target_lineage_and_neutral_handshake(
    tmp_path: Path,
) -> None:
    rollout = tmp_path / "rollout_000.jsonl"
    summary = tmp_path / "rollout_000_summary.json"
    _write_jsonl(rollout, _attempt_rows("A"))
    summary.write_text(
        json.dumps({"rollout_stop_reason": "wall_contact_first_session"}),
        encoding="utf-8",
    )

    result = extract_paired_ab_attempt(
        expected={
            "attempt_id": "seed_0_A",
            "pair_id": "seed_0",
            "sequence_index": 1,
            "seed": 0,
            "condition": "A",
            "wall_first_touch_mode": "interrupt",
        },
        rollout_jsonl_path=rollout,
        rollout_summary_path=summary,
        process_returncode=0,
    )

    assert result["status"] == "passed"
    assert result["selected_exemplar_id"] == "episode_168"
    assert result["selected_raw_fields_sha256"] == _RAW_SHA
    assert result["reset_checkpoint_semantics"] == (
        "first_post_reset_control_step"
    )
    assert result["zero_action_after_first_contact"] is True
    assert result["neutral_acknowledged"] is True
    assert result["terminal_reason"] == "wall_contact_first_session"
    assert result["target_dump_completed"] is False


def test_extract_accepts_sibling_return_provenance_and_prefixed_terminal(
    tmp_path: Path,
) -> None:
    rows = _attempt_rows("A")
    rows[0]["coverage_execution_exemplar_id"] = "episode_168"
    rows[0]["coverage_execution_raw_fields_sha256"] = _RAW_SHA
    rollout = tmp_path / "rollout_000.jsonl"
    summary = tmp_path / "rollout_000_summary.json"
    _write_jsonl(rollout, rows)
    summary.write_text(
        json.dumps(
            {
                "rollout_stop_reason": (
                    "box_safety:wall_contact_first_session"
                )
            }
        ),
        encoding="utf-8",
    )

    result = extract_paired_ab_attempt(
        expected={
            "attempt_id": "seed_0_A",
            "pair_id": "seed_0",
            "sequence_index": 1,
            "seed": 0,
            "condition": "A",
            "wall_first_touch_mode": "interrupt",
        },
        rollout_jsonl_path=rollout,
        rollout_summary_path=summary,
        process_returncode=0,
    )

    assert result["status"] == "passed"
    assert result["blockers"] == []
    assert result["target_cycle_index"] == 1
    assert result["zero_action_after_first_contact"] is True
    assert result["neutral_acknowledged"] is True
    assert result["terminal_reason"] == (
        "box_safety:wall_contact_first_session"
    )


def test_extract_b_proves_contact_ends_before_target_carry_and_dump(
    tmp_path: Path,
) -> None:
    rollout = tmp_path / "rollout_000.jsonl"
    summary = tmp_path / "rollout_000_summary.json"
    _write_jsonl(rollout, _attempt_rows("B"))
    summary.write_text(
        json.dumps({"rollout_stop_reason": "target_cycle_gate_reached"}),
        encoding="utf-8",
    )

    result = extract_paired_ab_attempt(
        expected={
            "attempt_id": "seed_0_B",
            "pair_id": "seed_0",
            "sequence_index": 2,
            "seed": 0,
            "condition": "B",
            "wall_first_touch_mode": "record_bucket_first_session",
        },
        rollout_jsonl_path=rollout,
        rollout_summary_path=summary,
        process_returncode=0,
    )

    assert result["status"] == "passed"
    assert result["entered_carry"] is True
    assert result["dump_completed"] is True
    assert result["target_dump_completed"] is True
    assert result["contact_ended_before_carry"] is True
    assert result["diagnostic_allowed_observed"] is True
    assert result["hard_stop_violations"] == []


def _b2_session_gap_rows(
    *,
    clear_tick_count: int,
    second_consecutive_steps: int = 1,
) -> list[dict[str, object]]:
    rows = [
        _row(
            t=0,
            condition="B",
            skill="return",
            action=[0.0] * 4,
            session_end_clear_ticks=2,
        ),
        _row(
            t=1,
            condition="B",
            skill="dig",
            action=[0.1] * 4,
            contact=True,
            diagnostic_allowed=True,
            wall_session_count=1,
            session_end_clear_ticks=2,
        ),
    ]
    for offset in range(clear_tick_count):
        rows.append(
            _row(
                t=2 + offset,
                condition="B",
                skill="dig",
                action=[0.1] * 4,
                session_end_clear_ticks=2,
            )
        )
    second_contact_t = 2 + clear_tick_count
    rows.append(
        _row(
            t=second_contact_t,
            condition="B",
            skill="dig",
            action=[0.1] * 4,
            contact=True,
            diagnostic_allowed=True,
            wall_session_count=2,
            contact_consecutive_steps=second_consecutive_steps,
            session_end_clear_ticks=2,
        )
    )
    return rows


def test_b2_single_clear_tick_bridges_physical_sessions(
    tmp_path: Path,
) -> None:
    rows = _b2_session_gap_rows(clear_tick_count=1)
    rows.extend(
        [
            _row(
                t=4,
                condition="B",
                skill="carry",
                action=[0.1] * 4,
                session_end_clear_ticks=2,
            ),
            _row(
                t=5,
                condition="B",
                skill="dump",
                action=[0.0] * 4,
                dump_end=True,
                session_end_clear_ticks=2,
            ),
        ]
    )
    rollout = tmp_path / "rollout_000.jsonl"
    summary = tmp_path / "rollout_000_summary.json"
    _write_jsonl(rollout, rows)
    summary.write_text(
        json.dumps({"rollout_stop_reason": "target_cycle_gate_reached"}),
        encoding="utf-8",
    )

    result = extract_paired_ab_attempt(
        expected={
            "attempt_id": "seed_2_B2",
            "pair_id": "seed_2",
            "sequence_index": 1,
            "seed": 2,
            "condition": "B",
            "wall_first_touch_mode": "record_bucket_first_session",
            "wall_contact_session_end_clear_ticks": 2,
        },
        rollout_jsonl_path=rollout,
        rollout_summary_path=summary,
        process_returncode=0,
    )

    assert result["status"] == "passed"
    assert result["target_dump_completed"] is True
    assert "wall_contact_repeat_session" not in result[
        "hard_stop_violations"
    ]
    assert result["debug_fields"][
        "box_safety_wall_contact_session_end_clear_ticks"
    ] == 2


def test_b2_two_clear_ticks_end_logical_session(
    tmp_path: Path,
) -> None:
    rows = _b2_session_gap_rows(clear_tick_count=2)
    rows.extend(
        [
            _row(
                t=5,
                condition="B",
                skill="dig",
                action=[0.0] * 4,
                awaiting_ack=True,
                session_end_clear_ticks=2,
            ),
            _row(
                t=6,
                condition="B",
                skill="dig",
                action=[0.0] * 4,
                neutral_ack=True,
                session_end_clear_ticks=2,
            ),
        ]
    )
    rollout = tmp_path / "rollout_000.jsonl"
    summary = tmp_path / "rollout_000_summary.json"
    _write_jsonl(rollout, rows)
    summary.write_text("{}", encoding="utf-8")

    result = extract_paired_ab_attempt(
        expected={
            "attempt_id": "seed_2_B2",
            "pair_id": "seed_2",
            "sequence_index": 1,
            "seed": 2,
            "condition": "B",
            "wall_first_touch_mode": "record_bucket_first_session",
            "wall_contact_session_end_clear_ticks": 2,
        },
        rollout_jsonl_path=rollout,
        rollout_summary_path=summary,
        process_returncode=0,
    )

    assert result["status"] == "passed"
    assert "wall_contact_repeat_session" in result[
        "hard_stop_violations"
    ]


def test_b2_gap_bridge_requires_new_physical_session_step_one(
    tmp_path: Path,
) -> None:
    rows = _b2_session_gap_rows(
        clear_tick_count=1,
        second_consecutive_steps=2,
    )
    rows.extend(
        [
            _row(
                t=4,
                condition="B",
                skill="dig",
                action=[0.0] * 4,
                awaiting_ack=True,
                session_end_clear_ticks=2,
            ),
            _row(
                t=5,
                condition="B",
                skill="dig",
                action=[0.0] * 4,
                neutral_ack=True,
                session_end_clear_ticks=2,
            ),
        ]
    )
    rollout = tmp_path / "rollout_000.jsonl"
    summary = tmp_path / "rollout_000_summary.json"
    _write_jsonl(rollout, rows)
    summary.write_text("{}", encoding="utf-8")

    result = extract_paired_ab_attempt(
        expected={
            "attempt_id": "seed_2_B2",
            "pair_id": "seed_2",
            "sequence_index": 1,
            "seed": 2,
            "condition": "B",
            "wall_first_touch_mode": "record_bucket_first_session",
            "wall_contact_session_end_clear_ticks": 2,
        },
        rollout_jsonl_path=rollout,
        rollout_summary_path=summary,
        process_returncode=0,
    )

    assert result["status"] == "passed"
    assert "wall_contact_identity_drift" in result[
        "hard_stop_violations"
    ]


def test_b2_contiguous_physical_session_steps_must_increase(
    tmp_path: Path,
) -> None:
    rows = [
        _row(
            t=0,
            condition="B",
            skill="return",
            action=[0.0] * 4,
            session_end_clear_ticks=2,
        ),
        _row(
            t=1,
            condition="B",
            skill="dig",
            action=[0.1] * 4,
            contact=True,
            diagnostic_allowed=True,
            contact_consecutive_steps=1,
            session_end_clear_ticks=2,
        ),
        _row(
            t=2,
            condition="B",
            skill="dig",
            action=[0.1] * 4,
            contact=True,
            diagnostic_allowed=True,
            contact_consecutive_steps=1,
            session_end_clear_ticks=2,
        ),
        _row(
            t=3,
            condition="B",
            skill="dig",
            action=[0.0] * 4,
            awaiting_ack=True,
            session_end_clear_ticks=2,
        ),
        _row(
            t=4,
            condition="B",
            skill="dig",
            action=[0.0] * 4,
            neutral_ack=True,
            session_end_clear_ticks=2,
        ),
    ]
    rollout = tmp_path / "rollout_000.jsonl"
    summary = tmp_path / "rollout_000_summary.json"
    _write_jsonl(rollout, rows)
    summary.write_text("{}", encoding="utf-8")

    result = extract_paired_ab_attempt(
        expected={
            "attempt_id": "seed_2_B2",
            "pair_id": "seed_2",
            "sequence_index": 1,
            "seed": 2,
            "condition": "B",
            "wall_first_touch_mode": "record_bucket_first_session",
            "wall_contact_session_end_clear_ticks": 2,
        },
        rollout_jsonl_path=rollout,
        rollout_summary_path=summary,
        process_returncode=0,
    )

    assert result["status"] == "passed"
    assert "wall_contact_identity_drift" in result[
        "hard_stop_violations"
    ]


def test_b2_clear_tick_debug_lineage_drift_is_blocked(
    tmp_path: Path,
) -> None:
    rows = _attempt_rows("B")
    for row in rows:
        row["box_safety_wall_contact_session_end_clear_ticks"] = 2
    rows[-1]["box_safety_wall_contact_session_end_clear_ticks"] = 1
    rollout = tmp_path / "rollout_000.jsonl"
    summary = tmp_path / "rollout_000_summary.json"
    _write_jsonl(rollout, rows)
    summary.write_text("{}", encoding="utf-8")

    result = extract_paired_ab_attempt(
        expected={
            "attempt_id": "seed_2_B2",
            "pair_id": "seed_2",
            "sequence_index": 1,
            "seed": 2,
            "condition": "B",
            "wall_first_touch_mode": "record_bucket_first_session",
            "wall_contact_session_end_clear_ticks": 2,
        },
        rollout_jsonl_path=rollout,
        rollout_summary_path=summary,
        process_returncode=0,
    )

    assert result["status"] == "failed"
    assert "diagnostic_debug_lineage_drift" in result["blockers"]
    assert result["debug_lineage_valid_every_tick"] is False
    assert result["debug_fields"][
        "box_safety_wall_contact_session_end_clear_ticks"
    ] == 1


def test_contact_can_end_on_the_tick_immediately_before_carry(
    tmp_path: Path,
) -> None:
    rows = [
        _row(t=0, condition="B", skill="return", action=[0.0] * 4),
        _row(
            t=1,
            condition="B",
            skill="dig",
            action=[0.1] * 4,
            contact=True,
            diagnostic_allowed=True,
        ),
        _row(t=2, condition="B", skill="carry", action=[0.1] * 4),
        _row(
            t=3,
            condition="B",
            skill="dump",
            action=[0.0] * 4,
            dump_end=True,
        ),
    ]
    rollout = tmp_path / "rollout_000.jsonl"
    summary = tmp_path / "rollout_000_summary.json"
    _write_jsonl(rollout, rows)
    summary.write_text("{}", encoding="utf-8")

    result = extract_paired_ab_attempt(
        expected={
            "attempt_id": "seed_0_B",
            "pair_id": "seed_0",
            "sequence_index": 2,
            "seed": 0,
            "condition": "B",
            "wall_first_touch_mode": "record_bucket_first_session",
        },
        rollout_jsonl_path=rollout,
        rollout_summary_path=summary,
        process_returncode=0,
    )

    assert result["contact_ended_before_carry"] is True


@pytest.mark.parametrize(
    ("reason", "force_n", "session_count", "expected_violation"),
    [
        ("wall_contact_high_force", 100_000.0, 1, "wall_contact_high_force"),
        ("wall_contact_repeat_session", 1000.0, 2, "wall_contact_repeat_session"),
    ],
)
def test_contact_hard_stop_is_contact_driven_only_after_zero_and_ack(
    tmp_path: Path,
    reason: str,
    force_n: float,
    session_count: int,
    expected_violation: str,
) -> None:
    rows = [
        _row(t=0, condition="B", skill="return", action=[0.0] * 4),
        _row(
            t=1,
            condition="B",
            skill="dig",
            action=[0.1] * 4,
            contact=True,
            contact_force_n=force_n,
            wall_session_count=session_count,
        ),
        _row(
            t=2,
            condition="B",
            skill="dig",
            action=[0.0] * 4,
            reason=reason,
            awaiting_ack=True,
        ),
        _row(
            t=3,
            condition="B",
            skill="dig",
            action=[0.0] * 4,
            reason=reason,
            neutral_ack=True,
        ),
    ]
    rollout = tmp_path / "rollout_000.jsonl"
    summary = tmp_path / "rollout_000_summary.json"
    _write_jsonl(rollout, rows)
    summary.write_text("{}", encoding="utf-8")

    result = extract_paired_ab_attempt(
        expected={
            "attempt_id": "seed_0_B",
            "pair_id": "seed_0",
            "sequence_index": 2,
            "seed": 0,
            "condition": "B",
            "wall_first_touch_mode": "record_bucket_first_session",
        },
        rollout_jsonl_path=rollout,
        rollout_summary_path=summary,
        process_returncode=0,
    )

    assert result["status"] == "passed"
    assert expected_violation in result["hard_stop_violations"]
    assert result["contact_driven_hard_failure"] is True
    assert result["zero_action_after_first_contact"] is True
    assert result["neutral_acknowledged"] is True


def test_simultaneous_hard_bottom_is_hard_but_not_contact_driven(
    tmp_path: Path,
) -> None:
    rows = [
        _row(t=0, condition="B", skill="return", action=[0.0] * 4),
        _row(
            t=1,
            condition="B",
            skill="dig",
            action=[0.1] * 4,
            contact=True,
            hard_bottom=True,
        ),
        _row(
            t=2,
            condition="B",
            skill="dig",
            action=[0.0] * 4,
            reason="hard_bottom_contact",
            awaiting_ack=True,
        ),
        _row(
            t=3,
            condition="B",
            skill="dig",
            action=[0.0] * 4,
            reason="hard_bottom_contact",
            neutral_ack=True,
        ),
    ]
    rollout = tmp_path / "rollout_000.jsonl"
    summary = tmp_path / "rollout_000_summary.json"
    _write_jsonl(rollout, rows)
    summary.write_text("{}", encoding="utf-8")

    result = extract_paired_ab_attempt(
        expected={
            "attempt_id": "seed_0_B",
            "pair_id": "seed_0",
            "sequence_index": 2,
            "seed": 0,
            "condition": "B",
            "wall_first_touch_mode": "record_bucket_first_session",
        },
        rollout_jsonl_path=rollout,
        rollout_summary_path=summary,
        process_returncode=0,
    )

    assert result["status"] == "passed"
    assert "hard_bottom_contact" in result["hard_stop_violations"]
    assert result["contact_driven_hard_failure"] is False


def test_timeout_after_contact_gap_is_not_contact_driven(
    tmp_path: Path,
) -> None:
    rows = [
        _row(t=0, condition="B", skill="return", action=[0.0] * 4),
        _row(
            t=1,
            condition="B",
            skill="dig",
            action=[0.1] * 4,
            contact=True,
        ),
        _row(t=2, condition="B", skill="dig", action=[0.1] * 4),
        _row(
            t=3,
            condition="B",
            skill="dig",
            action=[0.0] * 4,
            reason="transition_timeout",
            awaiting_ack=True,
        ),
        _row(
            t=4,
            condition="B",
            skill="dig",
            action=[0.0] * 4,
            reason="transition_timeout",
            neutral_ack=True,
        ),
    ]
    rows[3]["transition_timeout"] = True
    rows[4]["transition_timeout"] = True
    rollout = tmp_path / "rollout_000.jsonl"
    summary = tmp_path / "rollout_000_summary.json"
    _write_jsonl(rollout, rows)
    summary.write_text("{}", encoding="utf-8")

    result = extract_paired_ab_attempt(
        expected={
            "attempt_id": "seed_0_B",
            "pair_id": "seed_0",
            "sequence_index": 2,
            "seed": 0,
            "condition": "B",
            "wall_first_touch_mode": "record_bucket_first_session",
        },
        rollout_jsonl_path=rollout,
        rollout_summary_path=summary,
        process_returncode=0,
    )

    assert result["status"] == "passed"
    assert "timeout" in result["hard_stop_violations"]
    assert result["contact_driven_hard_failure"] is False


def test_extract_fails_when_debug_mode_drifts_on_any_tick(
    tmp_path: Path,
) -> None:
    rows = _attempt_rows("B")
    rows[-1]["box_safety_wall_first_touch_mode"] = "interrupt"
    rollout = tmp_path / "rollout_000.jsonl"
    summary = tmp_path / "rollout_000_summary.json"
    _write_jsonl(rollout, rows)
    summary.write_text("{}", encoding="utf-8")

    result = extract_paired_ab_attempt(
        expected={
            "attempt_id": "seed_0_B",
            "pair_id": "seed_0",
            "sequence_index": 2,
            "seed": 0,
            "condition": "B",
            "wall_first_touch_mode": "record_bucket_first_session",
        },
        rollout_jsonl_path=rollout,
        rollout_summary_path=summary,
        process_returncode=0,
    )

    assert result["status"] == "failed"
    assert "diagnostic_debug_lineage_drift" in result["blockers"]
    assert result["debug_lineage_valid_every_tick"] is False
    assert result["debug_fields"]["box_safety_wall_first_touch_mode"] == (
        "interrupt"
    )


def test_schedule_preflight_rejects_old_bounded_wrapper_before_execution(
    tmp_path: Path,
) -> None:
    schedule_path = _write_schedule(tmp_path)
    schedule = json.loads(schedule_path.read_text())
    config_path = Path(schedule["attempts"][0]["config_path"])
    config = yaml.safe_load(config_path.read_text())
    config["policy"]["box_emptying"]["bounded_dig_probe_stop"][
        "enabled"
    ] = True
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    with pytest.raises(
        WallContactABRunnerError,
        match="bounded_stop_wrapper_must_be_disabled",
    ):
        validate_paired_ab_schedule(schedule_path)


def test_schedule_preflight_requires_diagnostic_legacy_exact_role(
    tmp_path: Path,
) -> None:
    schedule_path = _write_schedule(tmp_path)
    schedule = json.loads(schedule_path.read_text())
    config_path = Path(schedule["attempts"][0]["config_path"])
    config = yaml.safe_load(config_path.read_text())
    config["policy"]["dig_cut_planner"]["coverage"][
        "actual_tuple_execution_library"
    ]["runtime_role"] = "enabled"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    with pytest.raises(
        WallContactABRunnerError,
        match="exact_runtime_role_not_diagnostic_legacy",
    ):
        validate_paired_ab_schedule(schedule_path)


def test_runner_marks_before_execution_continues_after_nonzero_and_never_retries(
    tmp_path: Path,
) -> None:
    schedule_path = _write_schedule(tmp_path)
    calls: list[str] = []

    def _executor(
        command: list[str],
        cwd: Path,
        log_path: Path,
    ) -> int:
        del cwd, log_path
        run_root = Path(command[command.index("--output-dir") + 1])
        attempt_id = run_root.name
        marker = run_root / "attempt_started.json"
        assert marker.is_file()
        calls.append(attempt_id)
        condition = attempt_id.rsplit("_", 1)[1]
        rollout_dir = run_root / "results" / "rollouts"
        _write_jsonl(
            rollout_dir / "rollout_000.jsonl",
            _attempt_rows(condition),
        )
        (rollout_dir / "rollout_000_summary.json").write_text(
            json.dumps(
                {
                    "rollout_stop_reason": (
                        "wall_contact_first_session"
                        if condition == "A"
                        else "target_cycle_gate_reached"
                    )
                }
            ),
            encoding="utf-8",
        )
        return 7 if attempt_id == "seed_1_B" else 0

    output = tmp_path / "attempt_set.json"
    result = run_paired_ab_schedule(
        schedule_path=schedule_path,
        attempt_set_output_path=output,
        executor=_executor,
    )

    assert calls == [f"seed_{seed}_{condition}" for seed, condition in _SEQUENCE]
    assert len(result["attempts"]) == 6
    failed = next(
        item for item in result["attempts"] if item["attempt_id"] == "seed_1_B"
    )
    assert failed["process_returncode"] == 7
    assert failed["status"] == "failed"
    assert (Path(failed["run_root"]) / "attempt_result.json").is_file()
    with pytest.raises(FileExistsError):
        run_paired_ab_schedule(
            schedule_path=schedule_path,
            attempt_set_output_path=tmp_path / "attempt_set_second.json",
            executor=_executor,
        )
    assert len(calls) == 6


def test_collect_attempt_set_is_complete_and_no_overwrite(
    tmp_path: Path,
) -> None:
    schedule_path = _write_schedule(tmp_path)
    schedule = validate_paired_ab_schedule(schedule_path)
    for expected in schedule["attempts"]:
        run_root = Path(expected["run_root"])
        run_root.mkdir(parents=True)
        rollout_dir = run_root / "results" / "rollouts"
        _write_jsonl(
            rollout_dir / "rollout_000.jsonl",
            _attempt_rows(str(expected["condition"])),
        )
        summary = rollout_dir / "rollout_000_summary.json"
        summary.write_text("{}", encoding="utf-8")
        result = extract_paired_ab_attempt(
            expected=expected,
            rollout_jsonl_path=rollout_dir / "rollout_000.jsonl",
            rollout_summary_path=summary,
            process_returncode=0,
        )
        (run_root / "attempt_started.json").write_text(
            json.dumps(
                {
                    "schema": "wall_contact_paired_ab_attempt_started_v1",
                    "attempt_id": expected["attempt_id"],
                }
            ),
            encoding="utf-8",
        )
        (run_root / "attempt_result.json").write_text(
            json.dumps(result),
            encoding="utf-8",
        )

    output = tmp_path / "collected.json"
    attempt_set = collect_paired_ab_attempt_set(
        schedule_path=schedule_path,
        output_path=output,
    )
    assert attempt_set["schema"] == "wall_contact_paired_ab_attempt_set_v1"
    assert len(attempt_set["attempts"]) == 6
    assert attempt_set["frozen_handoff_sha256"] == "f" * 64
    with pytest.raises(FileExistsError):
        collect_paired_ab_attempt_set(
            schedule_path=schedule_path,
            output_path=output,
        )


def test_reextract_uses_existing_rollouts_without_executing_attempts(
    tmp_path: Path,
) -> None:
    schedule_path = _write_schedule(tmp_path)
    schedule = validate_paired_ab_schedule(schedule_path)
    for expected in schedule["attempts"]:
        run_root = Path(expected["run_root"])
        rollout_dir = run_root / "results" / "rollouts"
        rows = _attempt_rows(str(expected["condition"]))
        rows[0]["coverage_execution_exemplar_id"] = "episode_168"
        rows[0]["coverage_execution_raw_fields_sha256"] = _RAW_SHA
        _write_jsonl(rollout_dir / "rollout_000.jsonl", rows)
        (rollout_dir / "rollout_000_summary.json").write_text(
            json.dumps(
                {
                    "rollout_stop_reason": (
                        "box_safety:wall_contact_first_session"
                        if expected["condition"] == "A"
                        else "target_cycle_gate_reached"
                    )
                }
            ),
            encoding="utf-8",
        )
        (run_root / "attempt_started.json").write_text(
            json.dumps(
                {
                    "schema": "wall_contact_paired_ab_attempt_started_v1",
                    "attempt_id": expected["attempt_id"],
                }
            ),
            encoding="utf-8",
        )
        (run_root / "attempt_result.json").write_text(
            json.dumps(
                {
                    "schema": "wall_contact_paired_ab_attempt_v1",
                    "attempt_id": expected["attempt_id"],
                    "process_returncode": 0,
                    "retry_count": 0,
                }
            ),
            encoding="utf-8",
        )

    output_dir = tmp_path / "reanalysis"
    result = reextract_paired_ab_attempt_set(
        schedule_path=schedule_path,
        output_dir=output_dir,
    )

    assert result["status"] == "passed"
    assert result["attempt_count"] == 6
    assert result["reanalysis_only"] is True
    assert result["executed_attempt_count"] == 0
    assert all(item["status"] == "passed" for item in result["attempts"])
    assert all(item["retry_count"] == 0 for item in result["attempts"])
    assert next(
        item for item in result["attempts"] if item["attempt_id"] == "seed_0_B"
    )["dump_completed"] is True
    assert (output_dir / "attempt_set.json").is_file()
    with pytest.raises(FileExistsError):
        reextract_paired_ab_attempt_set(
            schedule_path=schedule_path,
            output_dir=output_dir,
        )
