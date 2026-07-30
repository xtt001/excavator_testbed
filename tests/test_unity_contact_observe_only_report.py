from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pytest

from testbed.data.schema import ENV_STATE_V2_4_DIM
from testbed.eval.unity_contact_observe_only_report import (
    REPORT_SCHEMA,
    UnityContactObserveOnlyReportError,
    build_unity_contact_observe_only_report,
)
from testbed.planner.box_emptying.bottom_contact_detail import (
    WORKTOOL_FACTORY_FLOOR_CONTACT_DETAIL_PREFIX,
)


def _floor_warning(
    *,
    step: int,
    component: str = "bucket",
    normal_force_n: float = 10_000.0,
    tangential_force_n: float = 0.0,
    total_force_n: float | None = None,
    session: int = 1,
    consecutive_steps: int = 1,
) -> str:
    total = normal_force_n if total_force_n is None else total_force_n
    payload = {
        "schema": "worktool_factory_floor_contact_detail_v1",
        "step_id": step,
        "sim_time_s": step * 0.02,
        "delta_time_s": 0.02,
        "session_id": session,
        "session_count": session,
        "consecutive_contact_steps": consecutive_steps,
        "session_duration_s": consecutive_steps * 0.02,
        "step_max_normal_force_n": normal_force_n,
        "step_max_tangential_force_n": tangential_force_n,
        "step_max_total_force_n": total,
        "parts": [component],
        "pairs": [
            {
                "component": component,
                "machine_shape_path": f"Machine/{component}/shape",
                "floor_shape_path": "World/FactoryFloor",
                "callback_count": 1,
                "contact_point_count": 1,
                "max_normal_force_n": normal_force_n,
                "max_tangential_force_n": tangential_force_n,
                "max_total_force_n": total,
                "contact_points_world_m": [[0.0, 0.0, 0.0]],
                "representative_contact_point_component_local_m": [
                    0.0,
                    0.0,
                    0.0,
                ],
            }
        ],
    }
    return WORKTOOL_FACTORY_FLOOR_CONTACT_DETAIL_PREFIX + json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
    )


def _row(
    *,
    step: int,
    cycle: int,
    skill: str,
    dump: bool = False,
    floor_force_n: float = 0.0,
    floor_session: int = 0,
    floor_contact: bool = False,
    floor_allowed: bool = False,
    stop_reason: str = "",
    terminal: bool = False,
    awaiting: bool = False,
    acknowledged: bool = False,
    event_id: int = -1,
    contact_kind: str = "none",
    floor_component: str = "bucket",
    floor_consecutive_steps: int = 1,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    env = np.zeros(ENV_STATE_V2_4_DIM, dtype=np.float64)
    env[28:31] = [step * 0.01, 0.0, 0.0]
    env[104] = float(floor_contact)
    env[105] = floor_force_n
    env[106] = floor_session
    warning_values = list(warnings or [])
    if floor_contact:
        warning_values.append(
            _floor_warning(
                step=step,
                component=floor_component,
                normal_force_n=floor_force_n,
                session=floor_session,
                consecutive_steps=floor_consecutive_steps,
            )
        )
    return {
        "step_id": step,
        "sim_time_ns": step * 20_000_000,
        "primitive_cycle_index": cycle,
        "skill_name": skill,
        "dump_end_mask": int(dump),
        "qpos": [step * 0.01, 0.0, 0.0, 0.0],
        "qvel": [0.0, 0.0, 0.0, 0.0],
        "action": (
            [0.0, 0.0, 0.0, 0.0]
            if terminal or awaiting or acknowledged
            else [0.1, -0.1, 0.1, -0.1]
        ),
        "env_state": env.tolist(),
        "warnings": warning_values,
        "box_safety_reason": stop_reason,
        "box_safety_terminal": terminal,
        "box_safety_awaiting_neutral_ack": awaiting,
        "box_safety_neutral_acknowledged": acknowledged,
        "box_safety_replan": False,
        "box_safety_blocked_corridor_id": -1,
        "box_safety_policy_restarted": False,
        "box_safety_contact_kind": contact_kind,
        "box_safety_event_id": event_id,
        "box_safety_wall_contact_diagnostic_allowed": False,
        "box_safety_wall_contact_diagnostic_ab_enabled": False,
        "box_safety_wall_contact_diagnostic_observe_only_enabled": True,
        "box_safety_wall_first_touch_mode": "record_bucket_all_contacts",
        "box_safety_unity_contact_diagnostic_observe_only_enabled": True,
        "box_safety_unity_contact_diagnostic_backend": "agx_unity",
        "box_safety_factory_floor_contact_diagnostic_allowed": floor_allowed,
        "box_safety_unity_contact_diagnostic_allowed": floor_allowed,
        "transition_timeout": "timeout" in stop_reason,
        "pre_dig_align_timeout_count": 0,
    }


def _ten_dump_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    step = 1
    floor_session = 0
    for cycle in range(10):
        rows.append(
            _row(
                step=step,
                cycle=cycle,
                skill="dig",
                floor_session=floor_session,
            )
        )
        step += 1
        if cycle == 0:
            floor_session = 1
            rows.append(
                _row(
                    step=step,
                    cycle=cycle,
                    skill="dig",
                    floor_contact=True,
                    floor_force_n=30_000.0,
                    floor_session=1,
                    floor_allowed=True,
                )
            )
            step += 1
            rows.append(
                _row(
                    step=step,
                    cycle=cycle,
                    skill="dig",
                    floor_contact=True,
                    floor_force_n=40_000.0,
                    floor_session=1,
                    floor_allowed=True,
                    floor_consecutive_steps=2,
                )
            )
            step += 1
        rows.append(
            _row(
                step=step,
                cycle=cycle,
                skill="dump",
                dump=True,
                floor_session=floor_session,
            )
        )
        step += 1
    return rows


def test_report_records_factory_floor_force_duration_motion_and_completion() -> None:
    report = build_unity_contact_observe_only_report(
        rows=_ten_dump_rows(),
        summary={
            "target_cycle_completed_dump_count": 10,
            "rollout_stop_reason": "target_cycle_gate_reached",
        },
    )

    assert report["schema"] == REPORT_SCHEMA
    assert report["status"] == "passed"
    assert report["termination_category"] == "normal_completed_10"
    assert report["completed_dump_count"] == 10
    floor = report["shovels"][0]["factory_floor_contact"]
    assert floor["component"] == "bucket"
    assert floor["source"] == "FactoryFloor"
    assert floor["contact_tick_count"] == 2
    assert floor["session_ids"] == [1]
    assert floor["peak_normal_force_n"] == pytest.approx(40_000.0)
    assert floor["rms_of_step_peak_normal_force_n"] == pytest.approx(
        math.sqrt((30_000.0**2 + 40_000.0**2) / 2.0)
    )
    assert floor["contact_duration_s"] == pytest.approx(0.04)
    assert floor["impulse_n_s"] is None
    assert floor["impulse_status"] == (
        "unsupported_by_factory_floor_detail_v1"
    )
    assert floor["motion_progress_observed"] is True
    combined = report["shovels"][0]["combined_contact"]
    assert combined["components"] == ["bucket"]
    assert combined["sources"] == ["FactoryFloor"]
    assert combined["contact_tick_count"] == 2
    assert combined["contact_duration_s"] == pytest.approx(0.04)
    assert report["downstream_gates"] == {
        "production_contact_contract_change_allowed": False,
        "continuous_predictor_allowed": False,
        "offline_e0_g1_w1_allowed": False,
        "bounded_live_allowed": False,
        "functional_1x10_allowed": False,
    }


def test_report_includes_outside_footprint_floor_sidecar_with_zero_107d_mask() -> None:
    rows = [
        _row(step=1, cycle=0, skill="dig"),
        _row(
            step=2,
            cycle=0,
            skill="dig",
            floor_allowed=True,
            warnings=[
                _floor_warning(
                    step=2,
                    normal_force_n=35_000.0,
                )
            ],
        ),
        _row(step=3, cycle=0, skill="dump", dump=True),
    ]

    report = build_unity_contact_observe_only_report(
        rows=rows,
        summary={
            "target_cycle_completed_dump_count": 1,
            "rollout_stop_reason": "diagnostic_window_complete",
        },
    )

    floor = report["shovels"][0]["factory_floor_contact"]
    assert floor["contact_tick_count"] == 1
    assert floor["components"] == ["bucket"]
    assert floor["peak_normal_force_n"] == pytest.approx(35_000.0)
    assert floor["aggregate_107d_positive_tick_count"] == 0


def test_floor_marker_is_independent_from_wall_or_combined_marker() -> None:
    rows = [
        _row(step=1, cycle=0, skill="dig"),
        _row(
            step=2,
            cycle=0,
            skill="dig",
            warnings=[_floor_warning(step=2)],
        ),
        _row(step=3, cycle=0, skill="dump", dump=True),
    ]
    rows[1]["box_safety_wall_contact_diagnostic_allowed"] = True
    rows[1]["box_safety_unity_contact_diagnostic_allowed"] = True

    with pytest.raises(
        UnityContactObserveOnlyReportError,
        match="factory_floor_contact_allow_response_missing",
    ):
        build_unity_contact_observe_only_report(
            rows=rows,
            summary={
                "target_cycle_completed_dump_count": 1,
                "rollout_stop_reason": "diagnostic_window_complete",
            },
        )


def test_floor_marker_accepts_independent_next_row_alignment() -> None:
    rows = [
        _row(step=1, cycle=0, skill="dig"),
        _row(
            step=2,
            cycle=0,
            skill="dig",
            warnings=[_floor_warning(step=2)],
        ),
        _row(
            step=3,
            cycle=0,
            skill="dig",
            floor_allowed=True,
        ),
        _row(step=4, cycle=0, skill="dump", dump=True),
    ]

    report = build_unity_contact_observe_only_report(
        rows=rows,
        summary={
            "target_cycle_completed_dump_count": 1,
            "rollout_stop_reason": "diagnostic_window_complete",
        },
    )

    assert report["factory_floor_contact_tick_count"] == 1


def test_low_force_floor_contact_can_overlap_independent_timeout_chain() -> None:
    rows = [
        _row(step=1, cycle=0, skill="return"),
        _row(
            step=2,
            cycle=0,
            skill="return",
            floor_contact=True,
            floor_force_n=40_000.0,
            floor_session=1,
        ),
        _row(
            step=3,
            cycle=0,
            skill="return",
            floor_contact=True,
            floor_force_n=42_000.0,
            floor_session=1,
            floor_allowed=True,
            floor_consecutive_steps=2,
        ),
        _row(
            step=4,
            cycle=0,
            skill="return",
            floor_contact=True,
            floor_force_n=41_000.0,
            floor_session=1,
            floor_consecutive_steps=3,
            stop_reason="timeout",
            awaiting=True,
        ),
        _row(
            step=5,
            cycle=0,
            skill="return",
            floor_contact=True,
            floor_force_n=5_000.0,
            floor_session=1,
            floor_consecutive_steps=4,
            stop_reason="timeout",
            terminal=True,
            acknowledged=True,
        ),
    ]

    report = build_unity_contact_observe_only_report(
        rows=rows,
        summary={
            "target_cycle_completed_dump_count": 0,
            "rollout_stop_reason": "box_safety:timeout",
        },
    )

    assert report["status"] == "passed"
    assert report["termination_category"] == "timeout"
    assert report["factory_floor_contact_tick_count"] == 4


def test_high_force_outside_footprint_requires_zero_neutral_terminal_chain() -> None:
    rows = [
        _row(step=1, cycle=0, skill="dig"),
        _row(
            step=2,
            cycle=0,
            skill="dig",
            warnings=[_floor_warning(step=2, normal_force_n=120_000.0)],
            stop_reason="factory_floor_contact_high_force",
        ),
        _row(
            step=3,
            cycle=0,
            skill="dig",
            stop_reason="factory_floor_contact_high_force",
            terminal=True,
            acknowledged=True,
        ),
    ]

    with pytest.raises(
        UnityContactObserveOnlyReportError,
        match="unsafe_contact_terminal_chain_missing",
    ):
        build_unity_contact_observe_only_report(
            rows=rows,
            summary={
                "target_cycle_completed_dump_count": 0,
                "rollout_stop_reason": (
                    "box_safety:factory_floor_contact_high_force"
                ),
            },
        )


def test_forbidden_floor_component_terminal_chain_is_reported() -> None:
    rows = [
        _row(step=1, cycle=0, skill="dig"),
        _row(
            step=2,
            cycle=0,
            skill="dig",
            warnings=[
                _floor_warning(
                    step=2,
                    component="boom",
                    normal_force_n=20_000.0,
                )
            ],
            stop_reason="factory_floor_contact_forbidden_component",
            awaiting=True,
            event_id=11,
            contact_kind="hard_bottom",
        ),
        _row(
            step=3,
            cycle=0,
            skill="dig",
            stop_reason="factory_floor_contact_forbidden_component",
            terminal=True,
            acknowledged=True,
            event_id=11,
            contact_kind="hard_bottom",
        ),
    ]

    report = build_unity_contact_observe_only_report(
        rows=rows,
        summary={
            "target_cycle_completed_dump_count": 0,
            "rollout_stop_reason": (
                "box_safety:factory_floor_contact_forbidden_component"
            ),
        },
    )

    floor = report["shovels"][0]["factory_floor_contact"]
    assert floor["components"] == ["boom"]
    assert floor["unsafe_events"][0]["reason"] == (
        "factory_floor_contact_forbidden_component"
    )
    assert floor["unsafe_events"][0]["terminal_chain"] == {
        "event_id": 11,
        "neutral_request_step_id": 2,
        "terminal_ack_step_id": 3,
    }


def test_report_rejects_floor_contact_side_effect() -> None:
    rows = _ten_dump_rows()
    rows[1]["box_safety_replan"] = True

    with pytest.raises(
        UnityContactObserveOnlyReportError,
        match="floor_contact_observe_only_side_effect",
    ):
        build_unity_contact_observe_only_report(
            rows=rows,
            summary={
                "target_cycle_completed_dump_count": 10,
                "rollout_stop_reason": "target_cycle_gate_reached",
            },
        )


def test_report_rejects_legacy_hard_bottom_guard_in_unity_mode() -> None:
    rows = [_row(step=1, cycle=0, skill="dig")]
    rows[0]["box_safety_reason"] = "hard_bottom_depth_budget_guard"
    rows[0]["box_safety_hard_bottom_depth_budget_guard"] = True

    with pytest.raises(
        UnityContactObserveOnlyReportError,
        match="unity_diagnostic_hard_bottom_takeover_observed",
    ):
        build_unity_contact_observe_only_report(
            rows=rows,
            summary={
                "target_cycle_completed_dump_count": 0,
                "rollout_stop_reason": (
                    "box_safety:hard_bottom_depth_budget_guard"
                ),
            },
        )


def test_report_keeps_high_force_floor_tick_as_terminal_statistics() -> None:
    rows = [
        _row(step=1, cycle=0, skill="dig"),
        _row(
            step=2,
            cycle=0,
            skill="dig",
            floor_contact=True,
            floor_force_n=100_000.0,
            floor_session=1,
            stop_reason="factory_floor_contact_high_force",
            awaiting=True,
            event_id=7,
            contact_kind="hard_bottom",
        ),
        _row(
            step=3,
            cycle=0,
            skill="dig",
            floor_session=1,
            stop_reason="factory_floor_contact_high_force",
            terminal=True,
            acknowledged=True,
            event_id=7,
            contact_kind="hard_bottom",
        ),
    ]

    report = build_unity_contact_observe_only_report(
        rows=rows,
        summary={
            "target_cycle_completed_dump_count": 0,
            "rollout_stop_reason": (
                "box_safety:factory_floor_contact_high_force"
            ),
        },
    )

    assert report["status"] == "passed"
    assert report["termination_category"] == "high_force"
    floor = report["shovels"][0]["factory_floor_contact"]
    assert floor["peak_normal_force_n"] == 100_000.0
    assert floor["impulse_n_s"] is None


def test_high_force_alignment_does_not_reuse_previous_low_force_allow() -> None:
    rows = [
        _row(step=1, cycle=0, skill="dig"),
        _row(
            step=2,
            cycle=0,
            skill="dig",
            floor_contact=True,
            floor_force_n=10_000.0,
            floor_session=1,
            floor_allowed=True,
        ),
        _row(
            step=3,
            cycle=0,
            skill="dig",
            floor_contact=True,
            floor_force_n=100_000.0,
            floor_session=1,
            floor_consecutive_steps=2,
            stop_reason="factory_floor_contact_high_force",
            awaiting=True,
            event_id=8,
            contact_kind="hard_bottom",
        ),
        _row(
            step=4,
            cycle=0,
            skill="dig",
            floor_session=1,
            stop_reason="factory_floor_contact_high_force",
            terminal=True,
            acknowledged=True,
            event_id=8,
            contact_kind="hard_bottom",
        ),
    ]

    report = build_unity_contact_observe_only_report(
        rows=rows,
        summary={
            "target_cycle_completed_dump_count": 0,
            "rollout_stop_reason": (
                "box_safety:factory_floor_contact_high_force"
            ),
        },
    )

    assert report["termination_category"] == "high_force"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda rows: rows[1]["warnings"].append(
            "bucket_factory_floor_contact_lineage_incomplete_v1"
        ),
        lambda rows: rows[1]["warnings"].append(
            "worktool_contact_monitor_status_v1:status=unexpected"
        ),
        lambda rows: rows[1]["env_state"].__setitem__(105, float("nan")),
        lambda rows: rows[1]["env_state"].__setitem__(106, 2.0),
        lambda rows: rows[2]["env_state"].__setitem__(106, 0.0),
    ],
)
def test_report_fails_closed_on_floor_lineage_anomaly(mutate: Any) -> None:
    rows = _ten_dump_rows()
    mutate(rows)

    with pytest.raises(
        UnityContactObserveOnlyReportError,
        match="factory_floor_contact_lineage_invalid",
    ):
        build_unity_contact_observe_only_report(
            rows=rows,
            summary={
                "target_cycle_completed_dump_count": 10,
                "rollout_stop_reason": "target_cycle_gate_reached",
            },
        )


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        ("box_safety:wall_contact_high_force", "high_force"),
        ("box_safety:stuck_50_steps", "stuck"),
        ("transition_timeout", "timeout"),
        ("box_safety:wall_contact_forbidden_component", "other_hard_stop"),
    ],
)
def test_termination_category_is_causal(
    reason: str,
    expected: str,
) -> None:
    rows = [
        _row(step=1, cycle=0, skill="dig"),
        _row(
            step=2,
            cycle=0,
            skill="dig",
            stop_reason=reason.removeprefix("box_safety:"),
            terminal=True,
            acknowledged=True,
        ),
    ]
    report = build_unity_contact_observe_only_report(
        rows=rows,
        summary={
            "target_cycle_completed_dump_count": 0,
            "rollout_stop_reason": reason,
        },
    )

    assert report["termination_category"] == expected
