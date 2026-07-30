"""Public configuration and decision contracts for box safety."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.planner.box_emptying.bottom_contact_detail import (
    validate_unity_contact_diagnostic_scope,
)
from testbed.planner.box_emptying.contact_ownership import CONTACT_KIND_NONE
from testbed.planner.box_emptying.wall_contact_detail import (
    WALL_CONTACT_SESSION_END_CLEAR_TICKS_B2,
    WALL_FIRST_TOUCH_MODE_ALLOW_FINITE_BUCKET_CONTACTS,
    WALL_FIRST_TOUCH_MODE_RECORD_BUCKET_ALL_CONTACTS,
    WALL_FIRST_TOUCH_MODE_RECORD_BUCKET_FIRST_SESSION,
    validate_wall_contact_session_end_clear_ticks,
    validate_wall_first_touch_mode,
    validate_wall_high_force_threshold,
)


@dataclass(frozen=True)
class SafetyInterlockConfig:
    action_dim: int = 4
    low_payload_kg: float = 15.0
    wall_high_force_n: float = 100_000.0
    wall_first_touch_mode: str = "interrupt"
    wall_contact_diagnostic_ab_enabled: bool = False
    wall_contact_diagnostic_observe_only_enabled: bool = False
    unity_contact_diagnostic_observe_only_enabled: bool = False
    unity_contact_diagnostic_backend: str = ""
    wall_contact_session_end_clear_ticks: int = 1
    stuck_action_l1_min: float = 0.10
    stuck_window_steps: int = 50
    stuck_qpos_max_change: float = 0.005
    stuck_bucket_tip_max_displacement_m: float = 0.02
    hard_bottom_clearance_target_qpos: tuple[float, ...] = (
        0.513391,
        0.441393,
        0.639626,
        0.991115,
    )
    hard_bottom_clearance_kp: float = 2.0
    hard_bottom_clearance_kd: float = 0.25
    hard_bottom_clearance_action_signs: tuple[float, ...] = (
        1.0,
        -1.0,
        1.0,
        1.0,
    )
    hard_bottom_clearance_action_clip: tuple[float, ...] = (
        0.0,
        0.35,
        0.35,
        0.55,
    )
    hard_bottom_clearance_hold_steps: int = 3
    hard_bottom_clearance_margin_m: float = 0.02
    hard_bottom_clearance_max_steps: int = 150
    hard_bottom_depth_increase_abort_m: float = 0.002

    def __post_init__(self) -> None:
        if not isinstance(self.wall_contact_diagnostic_ab_enabled, bool):
            raise ValueError(
                "wall_contact_diagnostic_ab_enabled must be a boolean"
            )
        if not isinstance(
            self.wall_contact_diagnostic_observe_only_enabled,
            bool,
        ):
            raise ValueError(
                "wall_contact_diagnostic_observe_only_enabled "
                "must be a boolean"
            )
        if (
            self.wall_contact_diagnostic_ab_enabled
            and self.wall_contact_diagnostic_observe_only_enabled
        ):
            raise ValueError(
                "wall contact diagnostic markers are mutually exclusive"
            )
        mode = validate_wall_first_touch_mode(self.wall_first_touch_mode)
        if (
            mode == WALL_FIRST_TOUCH_MODE_ALLOW_FINITE_BUCKET_CONTACTS
            and (
                self.wall_contact_diagnostic_ab_enabled
                or self.wall_contact_diagnostic_observe_only_enabled
            )
        ):
            raise ValueError(
                "allow_finite_bucket_contacts is a mainline mode and "
                "cannot use diagnostic markers"
            )
        clear_ticks = validate_wall_contact_session_end_clear_ticks(
            self.wall_contact_session_end_clear_ticks
        )
        if (
            mode == WALL_FIRST_TOUCH_MODE_RECORD_BUCKET_FIRST_SESSION
            and not self.wall_contact_diagnostic_ab_enabled
        ):
            raise ValueError(
                "record_bucket_first_session requires "
                "wall_contact_diagnostic_ab_enabled=true"
            )
        if (
            mode == WALL_FIRST_TOUCH_MODE_RECORD_BUCKET_ALL_CONTACTS
            and not self.wall_contact_diagnostic_observe_only_enabled
        ):
            raise ValueError(
                "record_bucket_all_contacts requires "
                "wall_contact_diagnostic_observe_only_enabled=true"
            )
        if (
            self.wall_contact_diagnostic_observe_only_enabled
            and mode != WALL_FIRST_TOUCH_MODE_RECORD_BUCKET_ALL_CONTACTS
        ):
            raise ValueError(
                "observe-only diagnostic marker requires "
                "record_bucket_all_contacts mode"
            )
        if clear_ticks == WALL_CONTACT_SESSION_END_CLEAR_TICKS_B2 and not (
            mode == WALL_FIRST_TOUCH_MODE_RECORD_BUCKET_FIRST_SESSION
            and self.wall_contact_diagnostic_ab_enabled
        ):
            raise ValueError(
                "two-clear-tick session semantics requires diagnostic "
                "record_bucket_first_session mode"
            )
        object.__setattr__(
            self,
            "wall_high_force_n",
            validate_wall_high_force_threshold(self.wall_high_force_n),
        )
        object.__setattr__(
            self,
            "wall_first_touch_mode",
            mode,
        )
        object.__setattr__(
            self,
            "wall_contact_session_end_clear_ticks",
            clear_ticks,
        )
        object.__setattr__(
            self,
            "unity_contact_diagnostic_backend",
            validate_unity_contact_diagnostic_scope(
                enabled=(
                    self.unity_contact_diagnostic_observe_only_enabled
                ),
                backend=self.unity_contact_diagnostic_backend,
                wall_observe_only_enabled=(
                    self.wall_contact_diagnostic_observe_only_enabled
                ),
                wall_first_touch_mode=mode,
                high_force_n=self.wall_high_force_n,
            ),
        )


@dataclass(frozen=True)
class SafetyActionDecision:
    action: np.ndarray
    reason: str = ""
    terminal: bool = False
    awaiting_neutral_ack: bool = False
    neutral_acknowledged: bool = False
    replan: bool = False
    next_skill: str = ""
    blocked_corridor_id: int = -1
    depth_exhausted_cell_id: int = -1
    contact_kind: str = CONTACT_KIND_NONE
    wall_contact_session_count: int = 0
    hard_bottom_recovery_active: bool = False
    event_id: int = -1
    hard_bottom_contact: bool = False
    policy_restarted: bool = False
    hard_bottom_clearance_active: bool = False
    hard_bottom_clearance_completed: bool = False
    hard_bottom_clearance_neutral_acknowledged: bool = False
    depth_exhausted_guard: bool = False
    depth_exhausted_guard_active: bool = False
    hard_bottom_depth_budget_guard: bool = False
    wall_contact_allowed: bool = False
    wall_contact_diagnostic_allowed: bool = False
    factory_floor_contact_diagnostic_allowed: bool = False
    unity_contact_diagnostic_allowed: bool = False
    wall_contact_component: str = ""
    wall_contact_wall_name: str = ""

    def debug_fields(self) -> dict[str, Any]:
        return {
            "box_safety_reason": self.reason,
            "box_safety_terminal": bool(self.terminal),
            "box_safety_awaiting_neutral_ack": bool(
                self.awaiting_neutral_ack
            ),
            "box_safety_neutral_acknowledged": bool(
                self.neutral_acknowledged
            ),
            "box_safety_replan": bool(self.replan),
            "box_safety_next_skill": str(self.next_skill),
            "box_safety_blocked_corridor_id": int(self.blocked_corridor_id),
            "box_safety_depth_exhausted_cell_id": int(
                self.depth_exhausted_cell_id
            ),
            "box_safety_contact_kind": str(self.contact_kind),
            "box_safety_wall_contact_session_count": int(
                self.wall_contact_session_count
            ),
            "box_safety_hard_bottom_recovery_active": bool(
                self.hard_bottom_recovery_active
            ),
            "box_safety_event_id": int(self.event_id),
            "box_safety_hard_bottom_contact": bool(
                self.hard_bottom_contact
            ),
            "box_safety_policy_restarted": bool(self.policy_restarted),
            "box_safety_clearance_active": bool(
                self.hard_bottom_clearance_active
            ),
            "box_safety_clearance_completed": bool(
                self.hard_bottom_clearance_completed
            ),
            "box_safety_clearance_neutral_acknowledged": bool(
                self.hard_bottom_clearance_neutral_acknowledged
            ),
            "box_safety_depth_exhausted_guard": bool(
                self.depth_exhausted_guard
            ),
            "box_safety_depth_exhausted_guard_active": bool(
                self.depth_exhausted_guard_active
            ),
            "box_safety_hard_bottom_depth_budget_guard": bool(
                self.hard_bottom_depth_budget_guard
            ),
            "box_safety_wall_contact_allowed": bool(
                self.wall_contact_allowed
            ),
            "box_safety_wall_contact_diagnostic_allowed": bool(
                self.wall_contact_diagnostic_allowed
            ),
            "box_safety_factory_floor_contact_diagnostic_allowed": bool(
                self.factory_floor_contact_diagnostic_allowed
            ),
            "box_safety_unity_contact_diagnostic_allowed": bool(
                self.unity_contact_diagnostic_allowed
            ),
            "box_safety_wall_contact_component": str(
                self.wall_contact_component
            ),
            "box_safety_wall_contact_wall_name": str(
                self.wall_contact_wall_name
            ),
        }


__all__ = ["SafetyActionDecision", "SafetyInterlockConfig"]
