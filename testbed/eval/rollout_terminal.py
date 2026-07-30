"""Resolve policy-owned rollout termination without skipping neutral ack."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def policy_terminal_stop_reason(
    policy_debug: Mapping[str, Any],
) -> str | None:
    """Defer every stop until an active safety handshake has completed."""

    safety_handshake_active = bool(
        policy_debug.get("box_safety_awaiting_neutral_ack", False)
        or policy_debug.get(
            "box_safety_hard_bottom_recovery_active",
            False,
        )
        or policy_debug.get("box_safety_clearance_active", False)
    )
    if bool(policy_debug.get("planner_terminal_stop_requested", False)):
        if safety_handshake_active:
            return None
        return str(
            policy_debug.get(
                "planner_terminal_stop_reason",
                "planner_terminal_stop",
            )
        )
    if not bool(policy_debug.get("transition_timeout", False)):
        return None
    if safety_handshake_active:
        return None
    return "transition_timeout"


__all__ = ["policy_terminal_stop_reason"]
