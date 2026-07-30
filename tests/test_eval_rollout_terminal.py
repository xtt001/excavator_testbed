from __future__ import annotations

from testbed.eval.rollout_terminal import policy_terminal_stop_reason


def test_safety_neutral_handshake_takes_precedence_over_legacy_timeout_break() -> None:
    assert (
        policy_terminal_stop_reason(
            {
                "transition_timeout": True,
                "box_safety_awaiting_neutral_ack": True,
                "planner_terminal_stop_requested": False,
            }
        )
        is None
    )

    assert policy_terminal_stop_reason(
        {
            "transition_timeout": True,
            "box_safety_neutral_acknowledged": True,
            "planner_terminal_stop_requested": True,
            "planner_terminal_stop_reason": "box_safety:timeout",
        }
    ) == "box_safety:timeout"


def test_legacy_timeout_without_safety_handshake_still_stops() -> None:
    assert policy_terminal_stop_reason(
        {
            "transition_timeout": True,
            "box_safety_awaiting_neutral_ack": False,
            "box_safety_neutral_acknowledged": False,
        }
    ) == "transition_timeout"


def test_coverage_terminal_waits_for_hard_bottom_clearance_neutral_ack() -> None:
    assert (
        policy_terminal_stop_reason(
            {
                "planner_terminal_stop_requested": True,
                "planner_terminal_stop_reason": "dig_area_depleted",
                "box_safety_hard_bottom_recovery_active": True,
                "box_safety_clearance_active": True,
            }
        )
        is None
    )

    assert policy_terminal_stop_reason(
        {
            "planner_terminal_stop_requested": True,
            "planner_terminal_stop_reason": "dig_area_depleted",
            "box_safety_hard_bottom_recovery_active": False,
            "box_safety_clearance_neutral_acknowledged": True,
        }
    ) == "dig_area_depleted"
