from __future__ import annotations

import json
from typing import Any

import numpy as np
import pytest

from testbed.data.schema import (
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX,
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_STEP_MAX_FORCE_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_TYPED_MASK_IDX,
    ENV_STATE_V2_4_DIM,
)
from testbed.eval.wall_contact_rollout_diagnostic import (
    WallContactRolloutDiagnosticError,
    build_wall_contact_rollout_report,
)


def _warning(
    *,
    step: int,
    component: str = "bucket",
    force: float = 10.0,
    nonfinite_total: bool = False,
) -> str:
    pair = {
        "component": component,
        "machine_shape_path": f"Machine/{component}/shape",
        "wall_name": "Dig_XMin_Board",
        "wall_shape_path": "DigArea/Dig_XMin_Board/shape",
        "callback_count": 1,
        "contact_point_count": 1,
        "max_normal_force_n": force,
        "max_tangential_force_n": 0.0,
        "max_total_force_n": None if nonfinite_total else force,
        "contact_points_world_m": [[1.0, 2.0, 3.0]],
        "representative_contact_point_component_local_m": [0.1, 0.2, 0.3],
        "tangential_displacement_m": 0.0,
    }
    payload = {
        "schema": "worktool_wall_contact_detail_v1",
        "step_id": step,
        "sim_time_s": step * 0.02,
        "delta_time_s": 0.02,
        "session_id": 1,
        "session_count": 1,
        "consecutive_contact_steps": 1,
        "session_duration_s": 0.02,
        "session_normal_impulse_n_s": 0.2,
        "parts": [component],
        "walls": ["Dig_XMin_Board"],
        "pairs": [pair],
    }
    return "worktool_wall_contact_detail_v1:" + json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
    )


def _row(
    step: int,
    *,
    wall_positive: bool = False,
    force: float = 0.0,
    session_count: int = 0,
    warnings: list[str] | None = None,
    qpos0: float = 0.0,
    tip_x: float = 0.0,
    action: list[float] | None = None,
    diagnostic_allowed: bool = False,
    reason: str = "",
    awaiting: bool = False,
    acknowledged: bool = False,
    terminal: bool = False,
    event_id: int = -1,
    contact_kind: str | None = None,
) -> dict[str, Any]:
    env = np.zeros(ENV_STATE_V2_4_DIM, dtype=np.float32)
    env[ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX] = tip_x
    env[ENV_STATE_EXCAVATOR_WALL_CONTACT_TYPED_MASK_IDX] = float(
        wall_positive
    )
    env[ENV_STATE_EXCAVATOR_WALL_CONTACT_STEP_MAX_FORCE_IDX] = force
    env[ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX] = session_count
    return {
        "step_id": step,
        "sim_time_ns": step * 20_000_000,
        "primitive_cycle_index": 0,
        "skill_name": "dig",
        "dump_end_mask": 0,
        "qpos": [qpos0, 0.0, 0.0, 0.0],
        "qvel": [0.0, 0.0, 0.0, 0.0],
        "action": action or [0.2, 0.0, 0.0, 0.0],
        "env_state": env.tolist(),
        "warnings": list(warnings or []),
        "box_safety_reason": reason,
        "box_safety_terminal": terminal,
        "box_safety_awaiting_neutral_ack": awaiting,
        "box_safety_neutral_acknowledged": acknowledged,
        "box_safety_replan": False,
        "box_safety_blocked_corridor_id": -1,
        "box_safety_policy_restarted": False,
        "box_safety_contact_kind": (
            contact_kind if contact_kind is not None else (
                "wall" if reason else "none"
            )
        ),
        "box_safety_event_id": event_id,
        "box_safety_wall_contact_diagnostic_allowed": diagnostic_allowed,
        "box_safety_wall_contact_diagnostic_ab_enabled": False,
        "box_safety_wall_contact_diagnostic_observe_only_enabled": True,
        "box_safety_wall_first_touch_mode": "record_bucket_all_contacts",
    }


def _unsafe_rows(kind: str, *, with_terminal_chain: bool) -> list[dict[str, Any]]:
    component = kind if kind in {"boom", "stick", "other"} else "bucket"
    force = 100_000.0 if kind == "high_force" else 10.0
    warnings = (
        []
        if kind == "invalid_lineage"
        else [
            _warning(
                step=2,
                component=component,
                force=force,
                nonfinite_total=kind == "nonfinite",
            )
        ]
    )
    rows = [
        _row(1),
        _row(
            2,
            wall_positive=True,
            force=force,
            session_count=1,
            warnings=warnings,
        ),
    ]
    if not with_terminal_chain:
        rows.append(_row(3, session_count=1))
        return rows
    expected_reason = {
        "boom": "wall_contact_forbidden_component",
        "stick": "wall_contact_forbidden_component",
        "other": "wall_contact_forbidden_component",
        "high_force": "wall_contact_high_force",
        "nonfinite": "wall_contact_high_force",
        "invalid_lineage": "wall_contact_detail_invalid",
    }[kind]
    rows.extend(
        [
            _row(
                3,
                session_count=1,
                action=[0.0] * 4,
                reason=expected_reason,
                awaiting=True,
                event_id=7,
            ),
            _row(
                4,
                session_count=1,
                action=[0.0] * 4,
                reason=expected_reason,
                acknowledged=True,
                terminal=True,
                event_id=7,
            ),
        ]
    )
    return rows


def _apply_hard_bottom_priority_chain(
    rows: list[dict[str, Any]],
    *,
    typed_bottom_positive: bool,
    replan: bool = False,
) -> None:
    contact_env = rows[1]["env_state"]
    contact_env[ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX] = float(
        typed_bottom_positive
    )
    contact_env[
        ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX
    ] = int(typed_bottom_positive)
    for row in rows[-2:]:
        row["box_safety_reason"] = "hard_bottom_contact"
        row["box_safety_contact_kind"] = "hard_bottom"
    rows[-2]["box_safety_replan"] = replan


@pytest.mark.parametrize(
    "kind",
    ["boom", "stick", "other", "high_force", "nonfinite", "invalid_lineage"],
)
def test_unsafe_contact_without_terminal_neutral_chain_is_rejected(
    kind: str,
) -> None:
    with pytest.raises(
        WallContactRolloutDiagnosticError,
        match="unsafe_contact_terminal_chain_missing",
    ):
        build_wall_contact_rollout_report(
            rows=_unsafe_rows(kind, with_terminal_chain=False),
            summary={
                "rollout_stop_reason": "episode_len_reached",
                "target_cycle_completed_dump_count": 0,
            },
        )


@pytest.mark.parametrize(
    "kind",
    ["boom", "stick", "other", "high_force", "nonfinite", "invalid_lineage"],
)
def test_unsafe_contact_with_same_event_terminal_neutral_chain_is_valid(
    kind: str,
) -> None:
    rows = _unsafe_rows(kind, with_terminal_chain=True)
    reason = str(rows[-1]["box_safety_reason"])

    report = build_wall_contact_rollout_report(
        rows=rows,
        summary={
            "rollout_stop_reason": f"box_safety:{reason}",
            "target_cycle_completed_dump_count": 0,
        },
    )

    assert report["status"] == "passed"
    assert report["outcome"] == "hard_safety_stop_before_10"
    assert report["unsafe_contact_events"][0]["reason"] == reason
    assert report["unsafe_contact_events"][0]["terminal_chain"] == {
        "event_id": 7,
        "neutral_request_step_id": 3,
        "terminal_ack_step_id": 4,
    }


def test_unsafe_contact_rejects_terminal_ack_from_a_different_event() -> None:
    rows = _unsafe_rows("boom", with_terminal_chain=True)
    rows[-1]["box_safety_event_id"] = 8

    with pytest.raises(
        WallContactRolloutDiagnosticError,
        match="unsafe_contact_terminal_chain_missing",
    ):
        build_wall_contact_rollout_report(
            rows=rows,
            summary={
                "rollout_stop_reason": (
                    "box_safety:wall_contact_forbidden_component"
                ),
                "target_cycle_completed_dump_count": 0,
            },
        )


def test_unsafe_contact_rejects_nonzero_neutral_request() -> None:
    rows = _unsafe_rows("high_force", with_terminal_chain=True)
    rows[-2]["action"] = [0.01, 0.0, 0.0, 0.0]

    with pytest.raises(
        WallContactRolloutDiagnosticError,
        match="unsafe_contact_terminal_chain_missing",
    ):
        build_wall_contact_rollout_report(
            rows=rows,
            summary={
                "rollout_stop_reason": "box_safety:wall_contact_high_force",
                "target_cycle_completed_dump_count": 0,
            },
        )


@pytest.mark.parametrize("kind", ["boom", "high_force", "invalid_lineage"])
def test_simultaneous_hard_bottom_chain_proves_unsafe_wall_tick(
    kind: str,
) -> None:
    rows = _unsafe_rows(kind, with_terminal_chain=True)
    _apply_hard_bottom_priority_chain(rows, typed_bottom_positive=True)

    report = build_wall_contact_rollout_report(
        rows=rows,
        summary={
            "rollout_stop_reason": "box_safety:hard_bottom_contact",
            "target_cycle_completed_dump_count": 0,
        },
    )

    assert report["status"] == "passed"
    assert report["unsafe_contact_events"][0]["terminal_chain"] == {
        "event_id": 7,
        "neutral_request_step_id": 3,
        "terminal_ack_step_id": 4,
    }
    assert "hard_bottom_contact" in report["hard_stop_reasons"]


@pytest.mark.parametrize(
    ("kind", "floor_reason"),
    [
        ("high_force", "factory_floor_contact_high_force"),
        ("boom", "factory_floor_contact_forbidden_component"),
    ],
)
def test_simultaneous_floor_priority_chain_proves_unsafe_wall_tick(
    kind: str,
    floor_reason: str,
) -> None:
    rows = _unsafe_rows(kind, with_terminal_chain=True)
    rows[1]["warnings"].append(
        "worktool_factory_floor_contact_detail_v1:{}"
    )
    for row in rows[-2:]:
        row["box_safety_reason"] = floor_reason
        row["box_safety_contact_kind"] = "hard_bottom"

    report = build_wall_contact_rollout_report(
        rows=rows,
        summary={
            "rollout_stop_reason": f"box_safety:{floor_reason}",
            "target_cycle_completed_dump_count": 0,
        },
    )

    assert report["status"] == "passed"
    assert report["unsafe_contact_events"][0]["terminal_chain"] == {
        "event_id": 7,
        "neutral_request_step_id": 3,
        "terminal_ack_step_id": 4,
    }


@pytest.mark.parametrize(
    ("typed_bottom_positive", "replan"),
    [(False, False), (True, True)],
)
def test_hard_bottom_chain_cannot_bypass_wall_stop_contract(
    typed_bottom_positive: bool,
    replan: bool,
) -> None:
    rows = _unsafe_rows("boom", with_terminal_chain=True)
    _apply_hard_bottom_priority_chain(
        rows,
        typed_bottom_positive=typed_bottom_positive,
        replan=replan,
    )

    with pytest.raises(
        WallContactRolloutDiagnosticError,
        match="unsafe_contact_terminal_chain_missing",
    ):
        build_wall_contact_rollout_report(
            rows=rows,
            summary={
                "rollout_stop_reason": "box_safety:hard_bottom_contact",
                "target_cycle_completed_dump_count": 0,
            },
        )


def test_single_tick_contact_motion_uses_adjacent_state_evidence() -> None:
    rows = [
        _row(1, qpos0=0.0, tip_x=0.0),
        _row(
            2,
            wall_positive=True,
            force=10.0,
            session_count=1,
            warnings=[_warning(step=2)],
            qpos0=0.006,
            tip_x=0.01,
        ),
        _row(
            3,
            session_count=1,
            qpos0=0.007,
            tip_x=0.012,
            diagnostic_allowed=True,
        ),
    ]

    report = build_wall_contact_rollout_report(
        rows=rows,
        summary={
            "rollout_stop_reason": "episode_len_reached",
            "target_cycle_completed_dump_count": 0,
        },
    )

    motion = report["shovels"][0]["motion"]
    assert report["shovels"][0]["motion_progress_observed"] is True
    assert motion["evidence_sufficient"] is True
    assert motion["contact_pose_sample_count"] == 1
    assert motion["evidence_pose_sample_count"] == 2
    assert motion["evidence_window_semantics"] == (
        "pre-contact post-step pose plus contiguous contact-positive post-step poses"
    )
    assert motion["evidence_windows"] == [
        {
            "contact_step_ids": [2],
            "sample_step_ids": [1, 2],
            "pre_contact_neighbor_included": True,
            "post_contact_neighbor_included": False,
        }
    ]


def test_post_contact_motion_is_not_counted_as_contact_progress() -> None:
    rows = [
        _row(1, qpos0=0.0, tip_x=0.0),
        _row(
            2,
            wall_positive=True,
            force=10.0,
            session_count=1,
            warnings=[_warning(step=2)],
            qpos0=0.0,
            tip_x=0.0,
        ),
        _row(
            3,
            session_count=1,
            qpos0=0.1,
            tip_x=0.1,
            diagnostic_allowed=True,
        ),
    ]

    report = build_wall_contact_rollout_report(
        rows=rows,
        summary={
            "rollout_stop_reason": "episode_len_reached",
            "target_cycle_completed_dump_count": 0,
        },
    )

    motion = report["shovels"][0]["motion"]
    assert report["shovels"][0]["motion_progress_observed"] is False
    assert motion["qpos_max_axis_range"] == 0.0
    assert motion["bucket_tip_max_displacement_m"] == 0.0
    assert motion["evidence_windows"][0]["sample_step_ids"] == [1, 2]
