"""Neutral-first safety interlock for hard-bottom box emptying."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, replace
from typing import Any

import numpy as np

from testbed.data.schema import (
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX,
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_STEP_MAX_FORCE_IDX,
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_DIG_AREA_HARD_BOTTOM_DEPTH_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_STEP_MAX_FORCE_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_TYPED_MASK_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_V2_4_DIM,
)
from testbed.planner.box_emptying.bottom_contact_detail import (
    FactoryFloorContactGateResult,
    FactoryFloorContactService,
)
from testbed.planner.box_emptying.contact_ownership import (
    CONTACT_KIND_HARD_BOTTOM,
    CONTACT_KIND_NONE,
    CONTACT_KIND_WALL,
    validate_contact_ownership,
)
from testbed.planner.box_emptying.safety_contracts import (
    SafetyActionDecision,
    SafetyInterlockConfig,
)
from testbed.planner.box_emptying.wall_contact_detail import (
    WALL_GATE_INTERRUPT,
    WALL_GATE_TERMINAL,
    WallContactFirstSessionService,
    WallContactGateResult,
)


@dataclass(frozen=True)
class _PendingNeutral:
    event_step_id: int
    reason: str
    terminal: bool
    replan: bool
    next_skill: str
    blocked_corridor_id: int
    depth_exhausted_cell_id: int
    contact_kind: str
    wall_contact_session_count: int
    event_id: int = -1
    phase: str = ""


@dataclass
class BoxEmptyingSafetyInterlock:
    """Override policy actions and own the hard-bottom recovery handshake."""

    config: SafetyInterlockConfig = field(default_factory=SafetyInterlockConfig)
    _pending: _PendingNeutral | None = field(default=None, init=False)
    _handled_wall_sessions: int = field(default=0, init=False)
    _handled_bottom_sessions: int = field(default=0, init=False)
    _next_event_id: int = field(default=0, init=False)
    _hard_bottom_recovery_active: bool = field(default=False, init=False)
    _hard_bottom_recovery_event_id: int = field(default=-1, init=False)
    _hard_bottom_recovery_target_skill: str = field(default="", init=False)
    _hard_bottom_recovery_cell_id: int = field(default=-1, init=False)
    _hard_bottom_recovery_kind: str = field(default="", init=False)
    _hard_bottom_recovery_start_step: int = field(default=-1, init=False)
    _hard_bottom_recovery_contact_depth_m: float = field(
        default=float("nan"),
        init=False,
    )
    _hard_bottom_clearance_hold_count: int = field(default=0, init=False)
    _policy_restarted_event_id: int = field(default=-1, init=False)
    _depth_exhausted_cell_ids: set[int] = field(
        default_factory=set,
        init=False,
    )
    _motion_window: deque[tuple[np.ndarray, np.ndarray]] = field(
        default_factory=deque,
        init=False,
    )
    _last_decision: SafetyActionDecision | None = field(
        default=None,
        init=False,
    )
    _wall_contact_service: WallContactFirstSessionService = field(
        init=False,
    )
    _bottom_contact_service: FactoryFloorContactService = field(init=False)

    def __post_init__(self) -> None:
        self._wall_contact_service = WallContactFirstSessionService(
            mode=self.config.wall_first_touch_mode,
            high_force_n=self.config.wall_high_force_n,
            session_end_clear_ticks=(
                self.config.wall_contact_session_end_clear_ticks
            ),
        )
        self._bottom_contact_service = FactoryFloorContactService(
            high_force_n=self.config.wall_high_force_n,
        )

    def reset(self) -> None:
        self._pending = None
        self._handled_wall_sessions = 0
        self._handled_bottom_sessions = 0
        self._next_event_id = 0
        self._clear_hard_bottom_recovery()
        self._policy_restarted_event_id = -1
        self._depth_exhausted_cell_ids.clear()
        self._motion_window.clear()
        self._wall_contact_service.reset()
        self._bottom_contact_service.reset()
        self._last_decision = None

    def request_neutral_event(
        self,
        *,
        step_id: int,
        reason: str,
        terminal: bool,
        next_skill: str = "",
    ) -> None:
        """Queue an externally detected stop/recovery behind one neutral ack."""

        if self._pending is not None:
            return
        self._begin_neutral(
            step_id=int(step_id),
            reason=str(reason),
            terminal=bool(terminal),
            replan=bool(next_skill) and not terminal,
            next_skill=str(next_skill),
            blocked_corridor_id=-1,
            depth_exhausted_cell_id=-1,
            contact_kind=CONTACT_KIND_NONE,
        )

    def request_terminal_neutral_action(
        self,
        obs: dict[str, Any],
        *,
        reason: str,
        active_cell_id: int = -1,
        active_corridor_id: int = -1,
        skill_name: str = "",
    ) -> SafetyActionDecision:
        """Queue a terminal event and return its same-step neutral decision."""

        self.request_neutral_event(
            step_id=int(obs.get("step_id", -1)),
            reason=str(reason),
            terminal=True,
        )
        return self.filter_action(
            obs,
            self._neutral_action(),
            active_cell_id=int(active_cell_id),
            active_corridor_id=int(active_corridor_id),
            skill_name=str(skill_name),
        )

    def pre_policy_decision(
        self,
        obs: dict[str, Any],
        *,
        active_cell_id: int = -1,
        active_corridor_id: int = -1,
        skill_name: str = "",
    ) -> SafetyActionDecision | None:
        """Return recovery actions before ACT inference so buffers do not advance."""

        env_state = self._env_state(obs)
        step_id = int(obs.get("step_id", -1))
        unity_contact_diagnostic = bool(
            self.config.unity_contact_diagnostic_observe_only_enabled
        )
        raw_bottom_sessions = float(
            env_state[
                ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX
            ]
        )
        bottom_sessions = (
            0
            if unity_contact_diagnostic
            else int(round(raw_bottom_sessions))
        )
        bottom_contact = bool(
            env_state[ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX]
            >= 0.5
        )
        if unity_contact_diagnostic:
            bottom_result = self._bottom_contact_result(obs, env_state)
            pending_before_bottom = self._pending
            if bottom_result.terminal and (
                pending_before_bottom is None
                or not pending_before_bottom.terminal
            ):
                self._next_event_id += 1
                decision = self._begin_neutral(
                    step_id=step_id,
                    reason=bottom_result.reason,
                    terminal=True,
                    replan=False,
                    next_skill="",
                    blocked_corridor_id=-1,
                    depth_exhausted_cell_id=-1,
                    contact_kind=CONTACT_KIND_HARD_BOTTOM,
                    event_id=self._next_event_id,
                    phase=bottom_result.reason,
                )
                self._last_decision = decision
                return decision
        elif (
            bottom_contact
            and bottom_sessions > self._handled_bottom_sessions
        ):
            self._handled_bottom_sessions = bottom_sessions
            self._next_event_id += 1
            payload = float(env_state[ENV_STATE_MASS_IN_BUCKET_IDX])
            observe_only_terminal = bool(
                self.config.wall_contact_diagnostic_observe_only_enabled
            )
            decision = self._begin_neutral(
                step_id=step_id,
                reason="hard_bottom_contact",
                terminal=observe_only_terminal,
                replan=not observe_only_terminal,
                next_skill=(
                    ""
                    if observe_only_terminal
                    else (
                        "carry"
                        if payload >= float(self.config.low_payload_kg)
                        else "return"
                    )
                ),
                blocked_corridor_id=-1,
                depth_exhausted_cell_id=int(active_cell_id),
                contact_kind=CONTACT_KIND_HARD_BOTTOM,
                event_id=self._next_event_id,
                phase="hard_bottom_contact",
            )
            self._last_decision = decision
            return decision
        wall_result = self._wall_contact_result(obs, env_state)
        pending = self._pending
        if pending is not None:
            hard_bottom_pending = bool(
                pending.contact_kind == CONTACT_KIND_HARD_BOTTOM
                or self._hard_bottom_recovery_active
            )
            if (
                wall_result.kind == WALL_GATE_TERMINAL
                and not pending.terminal
            ):
                if hard_bottom_pending:
                    self._clear_hard_bottom_recovery()
                decision = self._wall_neutral_decision(
                    wall_result,
                    step_id=step_id,
                    active_corridor_id=active_corridor_id,
                    env_state=env_state,
                )
            else:
                decision = self._pending_decision(step_id, env_state)
            self._last_decision = decision
            return decision
        if self._hard_bottom_recovery_active:
            if wall_result.kind == WALL_GATE_TERMINAL:
                self._clear_hard_bottom_recovery()
                decision = self._wall_neutral_decision(
                    wall_result,
                    step_id=step_id,
                    active_corridor_id=active_corridor_id,
                    env_state=env_state,
                )
            else:
                decision = self._hard_bottom_recovery_decision(
                    obs=obs, step_id=step_id, env_state=env_state
                )
            self._last_decision = decision
            return decision
        if wall_result.stops_action:
            decision = self._wall_neutral_decision(
                wall_result,
                step_id=step_id,
                active_corridor_id=active_corridor_id,
                env_state=env_state,
            )
            self._last_decision = decision
            return decision
        depth_guard_reason = (
            ""
            if unity_contact_diagnostic
            else self._depth_guard_reason(
                env_state=env_state,
                active_cell_id=active_cell_id,
                skill_name=skill_name,
            )
        )
        if depth_guard_reason:
            self._next_event_id += 1
            payload = float(env_state[ENV_STATE_MASS_IN_BUCKET_IDX])
            decision = self._begin_neutral(
                step_id=step_id,
                reason=depth_guard_reason,
                terminal=False,
                replan=True,
                next_skill=(
                    "carry"
                    if payload >= float(self.config.low_payload_kg)
                    else (str(skill_name) or "return")
                ),
                blocked_corridor_id=-1,
                depth_exhausted_cell_id=int(active_cell_id),
                contact_kind=CONTACT_KIND_HARD_BOTTOM,
                event_id=self._next_event_id,
                phase=depth_guard_reason,
            )
            self._last_decision = decision
            return decision
        return None

    def filter_action(
        self,
        obs: dict[str, Any],
        proposed_action: Any,
        *,
        active_cell_id: int,
        active_corridor_id: int,
        skill_name: str = "",
    ) -> SafetyActionDecision:
        action = np.asarray(proposed_action, dtype=np.float32).reshape(
            int(self.config.action_dim)
        )
        env_state = self._env_state(obs)
        step_id = int(obs.get("step_id", -1))
        pre_policy = self.pre_policy_decision(
            obs,
            active_cell_id=active_cell_id,
            active_corridor_id=active_corridor_id,
            skill_name=skill_name,
        )
        if pre_policy is not None:
            return pre_policy

        if self._is_stuck(obs=obs, env_state=env_state, action=action):
            return self._begin_neutral(
                step_id=step_id,
                reason="stuck_50_steps",
                terminal=True,
                replan=False,
                next_skill="",
                blocked_corridor_id=-1,
                depth_exhausted_cell_id=-1,
                contact_kind=CONTACT_KIND_NONE,
            )

        wall_result = self._wall_contact_service.last_result
        wall_detail = None if wall_result is None else wall_result.detail
        bottom_result = self._bottom_contact_service.last_result
        decision = SafetyActionDecision(
            action=action.copy(),
            wall_contact_allowed=bool(
                wall_result is not None and wall_result.allowed
            ),
            wall_contact_diagnostic_allowed=bool(
                wall_result is not None
                and wall_result.diagnostic_allowed
            ),
            factory_floor_contact_diagnostic_allowed=bool(
                self.config.unity_contact_diagnostic_observe_only_enabled
                and bottom_result is not None
                and bottom_result.diagnostic_allowed
            ),
            unity_contact_diagnostic_allowed=bool(
                self.config.unity_contact_diagnostic_observe_only_enabled
                and (
                    (
                        bottom_result is not None
                        and bottom_result.diagnostic_allowed
                    )
                    or (
                        wall_result is not None
                        and wall_result.diagnostic_allowed
                    )
                )
            ),
            wall_contact_component=(
                ""
                if wall_detail is None
                else ",".join(wall_detail.parts)
            ),
            wall_contact_wall_name=(
                ""
                if wall_detail is None
                else ",".join(wall_detail.walls)
            ),
        )
        self._last_decision = decision
        return decision

    def _bottom_contact_result(
        self,
        obs: dict[str, Any],
        env_state: np.ndarray,
    ) -> FactoryFloorContactGateResult:
        return self._bottom_contact_service.evaluate(
            typed_mask=float(
                env_state[
                    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX
                ]
            ),
            aggregate_force_n=float(
                env_state[
                    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_STEP_MAX_FORCE_IDX
                ]
            ),
            aggregate_session_count=float(
                env_state[
                    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX
                ]
            ),
            warnings=obs.get("warnings", ()),
            step_id=int(obs.get("step_id", -1)),
            sim_time_ns=(
                None
                if obs.get("sim_time_ns") is None
                else int(obs["sim_time_ns"])
            ),
        )

    def _wall_contact_result(
        self,
        obs: dict[str, Any],
        env_state: np.ndarray,
    ) -> WallContactGateResult:
        warnings = obs.get("warnings", ())
        if not isinstance(warnings, (list, tuple)):
            warnings = ()
        raw_sim_time_ns = obs.get("sim_time_ns")
        wall_typed_mask = float(
            env_state[
                ENV_STATE_EXCAVATOR_WALL_CONTACT_TYPED_MASK_IDX
            ]
        )
        if not np.isfinite(wall_typed_mask):
            return WallContactGateResult(
                kind=WALL_GATE_TERMINAL,
                reason="wall_contact_detail_invalid",
            )
        return self._wall_contact_service.evaluate(
            wall_positive=bool(wall_typed_mask >= 0.5),
            aggregate_session_count=float(
                env_state[
                    ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX
                ]
            ),
            aggregate_force_n=float(
                env_state[
                    ENV_STATE_EXCAVATOR_WALL_CONTACT_STEP_MAX_FORCE_IDX
                ]
            ),
            warnings=warnings,
            step_id=int(obs.get("step_id", -1)),
            sim_time_ns=(
                None
                if raw_sim_time_ns is None
                else int(raw_sim_time_ns)
            ),
        )

    def _wall_neutral_decision(
        self,
        result: WallContactGateResult,
        *,
        step_id: int,
        active_corridor_id: int,
        env_state: np.ndarray,
    ) -> SafetyActionDecision:
        raw_sessions = float(
            env_state[ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX]
        )
        wall_sessions = (
            result.detail.session_count
            if result.detail is not None
            else (
                int(round(raw_sessions))
                if np.isfinite(raw_sessions) and raw_sessions >= 1.0
                else 1
            )
        )
        self._handled_wall_sessions = max(
            self._handled_wall_sessions,
            wall_sessions,
        )
        terminal = bool(
            result.terminal
            or (
                self.config.wall_contact_diagnostic_ab_enabled
                and self.config.wall_first_touch_mode == "interrupt"
                and result.kind == WALL_GATE_INTERRUPT
            )
        )
        self._next_event_id += 1
        return self._begin_neutral(
            step_id=step_id,
            reason=result.reason,
            terminal=terminal,
            replan=not terminal,
            next_skill="return" if not terminal else "",
            blocked_corridor_id=int(active_corridor_id),
            depth_exhausted_cell_id=-1,
            contact_kind=CONTACT_KIND_WALL,
            wall_contact_session_count=wall_sessions,
            event_id=self._next_event_id,
        )

    def mark_policy_restarted(self, event_id: int) -> None:
        """Record that the shell completed the required current-ACT restart."""

        event = int(event_id)
        if event < 0 or event != self._hard_bottom_recovery_event_id:
            raise ValueError(
                "hard-bottom policy restart event does not match active recovery"
            )
        self._policy_restarted_event_id = event
        if self._last_decision is not None:
            self._last_decision = replace(
                self._last_decision,
                policy_restarted=True,
            )

    def debug_fields(self) -> dict[str, Any]:
        if self._last_decision is None:
            fields = SafetyActionDecision(
                action=self._neutral_action()
            ).debug_fields()
        else:
            fields = self._last_decision.debug_fields()
        fields["box_safety_depth_exhausted_cell_ids"] = sorted(
            self._depth_exhausted_cell_ids
        )
        fields["box_safety_wall_contact_diagnostic_ab_enabled"] = bool(
            self.config.wall_contact_diagnostic_ab_enabled
        )
        fields[
            "box_safety_wall_contact_diagnostic_observe_only_enabled"
        ] = bool(
            self.config.wall_contact_diagnostic_observe_only_enabled
        )
        fields[
            "box_safety_unity_contact_diagnostic_observe_only_enabled"
        ] = bool(
            self.config.unity_contact_diagnostic_observe_only_enabled
        )
        fields["box_safety_unity_contact_diagnostic_backend"] = str(
            self.config.unity_contact_diagnostic_backend
        )
        fields["box_safety_wall_first_touch_mode"] = str(
            self.config.wall_first_touch_mode
        )
        fields["box_safety_wall_contact_session_end_clear_ticks"] = int(
            self.config.wall_contact_session_end_clear_ticks
        )
        return fields

    def _pending_decision(
        self,
        step_id: int,
        env_state: np.ndarray,
    ) -> SafetyActionDecision:
        pending = self._pending
        if pending is None:  # pragma: no cover - guarded by callers
            raise RuntimeError("pending neutral state disappeared")
        hard_bottom_contact = pending.phase == "hard_bottom_contact"
        depth_exhausted_guard = (
            pending.phase == "depth_exhausted_cell_guard"
        )
        hard_bottom_depth_budget_guard = (
            pending.phase == "hard_bottom_depth_budget_guard"
        )
        clearance_completed = self._is_clearance_complete_phase(
            pending.phase
        )
        if step_id <= pending.event_step_id:
            return SafetyActionDecision(
                action=self._neutral_action(),
                reason=pending.reason,
                awaiting_neutral_ack=True,
                blocked_corridor_id=pending.blocked_corridor_id,
                depth_exhausted_cell_id=pending.depth_exhausted_cell_id,
                contact_kind=pending.contact_kind,
                wall_contact_session_count=(
                    pending.wall_contact_session_count
                ),
                hard_bottom_recovery_active=(
                    self._hard_bottom_recovery_active
                ),
                event_id=pending.event_id,
                hard_bottom_contact=hard_bottom_contact,
                policy_restarted=self._policy_restarted(pending.event_id),
                hard_bottom_clearance_completed=clearance_completed,
                depth_exhausted_guard=depth_exhausted_guard,
                depth_exhausted_guard_active=(
                    self._hard_bottom_recovery_kind
                    == "depth_exhausted_cell_guard"
                ),
                hard_bottom_depth_budget_guard=(
                    hard_bottom_depth_budget_guard
                    or self._hard_bottom_recovery_kind
                    == "hard_bottom_depth_budget_guard"
                ),
            )

        if pending.terminal:
            recovery_kind = str(self._hard_bottom_recovery_kind)
            if self._is_clearance_phase(pending.phase):
                self._clear_hard_bottom_recovery()
            return SafetyActionDecision(
                action=self._neutral_action(),
                reason=pending.reason,
                terminal=True,
                neutral_acknowledged=True,
                blocked_corridor_id=pending.blocked_corridor_id,
                depth_exhausted_cell_id=pending.depth_exhausted_cell_id,
                contact_kind=pending.contact_kind,
                wall_contact_session_count=(
                    pending.wall_contact_session_count
                ),
                event_id=pending.event_id,
                policy_restarted=self._policy_restarted(pending.event_id),
                hard_bottom_clearance_completed=clearance_completed,
                hard_bottom_clearance_neutral_acknowledged=(
                    clearance_completed
                ),
                depth_exhausted_guard_active=(
                    recovery_kind == "depth_exhausted_cell_guard"
                ),
                hard_bottom_depth_budget_guard=(
                    recovery_kind == "hard_bottom_depth_budget_guard"
                ),
            )

        self._pending = None
        if (
            hard_bottom_contact
            or depth_exhausted_guard
            or hard_bottom_depth_budget_guard
        ):
            recovery_kind = (
                "hard_bottom_contact"
                if hard_bottom_contact
                else str(pending.phase)
            )
            self._start_hard_bottom_recovery(
                pending=pending,
                step_id=step_id,
                plane_depth_m=float(
                    env_state[
                        ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX
                    ]
                ),
                recovery_kind=recovery_kind,
            )
            return SafetyActionDecision(
                action=self._neutral_action(),
                reason=(
                    "hard_bottom_contact_neutral_acknowledged"
                    if hard_bottom_contact
                    else f"{recovery_kind}_neutral_acknowledged"
                ),
                neutral_acknowledged=True,
                replan=True,
                blocked_corridor_id=pending.blocked_corridor_id,
                depth_exhausted_cell_id=pending.depth_exhausted_cell_id,
                contact_kind=pending.contact_kind,
                wall_contact_session_count=(
                    pending.wall_contact_session_count
                ),
                hard_bottom_recovery_active=True,
                event_id=pending.event_id,
                depth_exhausted_guard=depth_exhausted_guard,
                depth_exhausted_guard_active=depth_exhausted_guard,
                hard_bottom_depth_budget_guard=(
                    hard_bottom_depth_budget_guard
                ),
            )
        if clearance_completed:
            target_skill = str(self._hard_bottom_recovery_target_skill)
            event_id = int(self._hard_bottom_recovery_event_id)
            policy_restarted = self._policy_restarted(event_id)
            recovery_kind = str(self._hard_bottom_recovery_kind)
            self._clear_hard_bottom_recovery()
            return SafetyActionDecision(
                action=self._neutral_action(),
                reason=(
                    "hard_bottom_clearance_neutral_acknowledged"
                    if recovery_kind == "hard_bottom_contact"
                    else (
                        f"{recovery_kind}"
                        "_clearance_neutral_acknowledged"
                    )
                ),
                neutral_acknowledged=True,
                replan=True,
                next_skill=target_skill,
                depth_exhausted_cell_id=-1,
                contact_kind=CONTACT_KIND_HARD_BOTTOM,
                hard_bottom_recovery_active=False,
                event_id=event_id,
                policy_restarted=policy_restarted,
                hard_bottom_clearance_completed=True,
                hard_bottom_clearance_neutral_acknowledged=True,
                depth_exhausted_guard_active=(
                    recovery_kind == "depth_exhausted_cell_guard"
                ),
                hard_bottom_depth_budget_guard=(
                    recovery_kind == "hard_bottom_depth_budget_guard"
                ),
            )
        return SafetyActionDecision(
            action=self._neutral_action(),
            reason=f"{pending.reason}_neutral_acknowledged",
            neutral_acknowledged=True,
            replan=pending.replan,
            next_skill=pending.next_skill,
            blocked_corridor_id=pending.blocked_corridor_id,
            depth_exhausted_cell_id=pending.depth_exhausted_cell_id,
            contact_kind=pending.contact_kind,
            wall_contact_session_count=pending.wall_contact_session_count,
            event_id=pending.event_id,
        )

    def _begin_neutral(
        self,
        *,
        step_id: int,
        reason: str,
        terminal: bool,
        replan: bool,
        next_skill: str,
        blocked_corridor_id: int,
        depth_exhausted_cell_id: int,
        contact_kind: str,
        wall_contact_session_count: int = 0,
        event_id: int = -1,
        phase: str = "",
    ) -> SafetyActionDecision:
        ownership = validate_contact_ownership(
            contact_kind=contact_kind,
            blocked_corridor_id=blocked_corridor_id,
            depth_exhausted_cell_id=depth_exhausted_cell_id,
            wall_contact_session_count=wall_contact_session_count,
        )
        self._motion_window.clear()
        self._pending = _PendingNeutral(
            event_step_id=step_id,
            reason=reason,
            terminal=terminal,
            replan=replan,
            next_skill=next_skill,
            blocked_corridor_id=ownership.blocked_corridor_id,
            depth_exhausted_cell_id=ownership.depth_exhausted_cell_id,
            contact_kind=ownership.contact_kind,
            wall_contact_session_count=ownership.wall_contact_session_count,
            event_id=event_id,
            phase=phase,
        )
        decision = SafetyActionDecision(
            action=self._neutral_action(),
            reason=reason,
            awaiting_neutral_ack=True,
            blocked_corridor_id=ownership.blocked_corridor_id,
            depth_exhausted_cell_id=ownership.depth_exhausted_cell_id,
            contact_kind=ownership.contact_kind,
            wall_contact_session_count=ownership.wall_contact_session_count,
            hard_bottom_recovery_active=self._hard_bottom_recovery_active,
            event_id=event_id,
            hard_bottom_contact=phase == "hard_bottom_contact",
            policy_restarted=self._policy_restarted(event_id),
            hard_bottom_clearance_completed=(
                self._is_clearance_complete_phase(phase)
            ),
            depth_exhausted_guard=(
                phase == "depth_exhausted_cell_guard"
            ),
            depth_exhausted_guard_active=(
                self._hard_bottom_recovery_kind
                == "depth_exhausted_cell_guard"
            ),
            hard_bottom_depth_budget_guard=(
                phase == "hard_bottom_depth_budget_guard"
                or self._hard_bottom_recovery_kind
                == "hard_bottom_depth_budget_guard"
            ),
        )
        self._last_decision = decision
        return decision

    def _start_hard_bottom_recovery(
        self,
        *,
        pending: _PendingNeutral,
        step_id: int,
        plane_depth_m: float,
        recovery_kind: str,
    ) -> None:
        self._hard_bottom_recovery_active = True
        self._hard_bottom_recovery_event_id = int(pending.event_id)
        self._hard_bottom_recovery_target_skill = str(pending.next_skill)
        self._hard_bottom_recovery_cell_id = int(
            pending.depth_exhausted_cell_id
        )
        self._hard_bottom_recovery_kind = str(recovery_kind)
        if self._hard_bottom_recovery_cell_id >= 0:
            self._depth_exhausted_cell_ids.add(
                self._hard_bottom_recovery_cell_id
            )
        self._hard_bottom_recovery_start_step = int(step_id)
        self._hard_bottom_recovery_contact_depth_m = float(plane_depth_m)
        self._hard_bottom_clearance_hold_count = 0

    def _clear_hard_bottom_recovery(self) -> None:
        self._hard_bottom_recovery_active = False
        self._hard_bottom_recovery_event_id = -1
        self._hard_bottom_recovery_target_skill = ""
        self._hard_bottom_recovery_cell_id = -1
        self._hard_bottom_recovery_kind = ""
        self._hard_bottom_recovery_start_step = -1
        self._hard_bottom_recovery_contact_depth_m = float("nan")
        self._hard_bottom_clearance_hold_count = 0

    def _hard_bottom_recovery_decision(
        self,
        *,
        obs: dict[str, Any],
        step_id: int,
        env_state: np.ndarray,
    ) -> SafetyActionDecision:
        event_id = int(self._hard_bottom_recovery_event_id)
        recovery_kind = str(self._hard_bottom_recovery_kind)
        clearance_prefix = (
            "hard_bottom"
            if recovery_kind == "hard_bottom_contact"
            else recovery_kind
        )
        exhausted_guard = bool(
            recovery_kind == "depth_exhausted_cell_guard"
        )
        depth_budget_guard = bool(
            recovery_kind == "hard_bottom_depth_budget_guard"
        )
        elapsed = max(
            0,
            int(step_id) - int(self._hard_bottom_recovery_start_step),
        )
        if elapsed >= int(self.config.hard_bottom_clearance_max_steps):
            return self._begin_neutral(
                step_id=step_id,
                reason=f"{clearance_prefix}_clearance_timeout",
                terminal=True,
                replan=False,
                next_skill="",
                blocked_corridor_id=-1,
                depth_exhausted_cell_id=-1,
                contact_kind=CONTACT_KIND_HARD_BOTTOM,
                event_id=event_id,
                phase=f"{clearance_prefix}_clearance_abort",
            )

        plane_depth = float(
            env_state[ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX]
        )
        contact_depth = float(
            self._hard_bottom_recovery_contact_depth_m
        )
        if (
            np.isfinite(contact_depth)
            and plane_depth - contact_depth
            > float(self.config.hard_bottom_depth_increase_abort_m)
        ):
            return self._begin_neutral(
                step_id=step_id,
                reason=f"{clearance_prefix}_clearance_depth_increase",
                terminal=True,
                replan=False,
                next_skill="",
                blocked_corridor_id=-1,
                depth_exhausted_cell_id=-1,
                contact_kind=CONTACT_KIND_HARD_BOTTOM,
                event_id=event_id,
                phase=f"{clearance_prefix}_clearance_abort",
            )
        hard_bottom_depth = float(
            env_state[ENV_STATE_DIG_AREA_HARD_BOTTOM_DEPTH_IDX]
        )
        bottom_contact = bool(
            env_state[ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX]
            >= 0.5
        )
        depth_clear = bool(
            np.isfinite(hard_bottom_depth)
            and hard_bottom_depth > 0.0
            and plane_depth
            <= hard_bottom_depth
            - float(self.config.hard_bottom_clearance_margin_m)
        )
        if not bottom_contact and depth_clear:
            self._hard_bottom_clearance_hold_count += 1
        else:
            self._hard_bottom_clearance_hold_count = 0
        if self._hard_bottom_clearance_hold_count >= int(
            self.config.hard_bottom_clearance_hold_steps
        ):
            return self._begin_neutral(
                step_id=step_id,
                reason=f"{clearance_prefix}_clearance_complete",
                terminal=False,
                replan=True,
                next_skill=self._hard_bottom_recovery_target_skill,
                blocked_corridor_id=-1,
                depth_exhausted_cell_id=-1,
                contact_kind=CONTACT_KIND_HARD_BOTTOM,
                event_id=event_id,
                phase=f"{clearance_prefix}_clearance_complete",
            )

        try:
            action = self._scripted_clearance_action(obs)
        except ValueError:
            return self._begin_neutral(
                step_id=step_id,
                reason=f"{clearance_prefix}_clearance_observation_invalid",
                terminal=True,
                replan=False,
                next_skill="",
                blocked_corridor_id=-1,
                depth_exhausted_cell_id=-1,
                contact_kind=CONTACT_KIND_HARD_BOTTOM,
                event_id=event_id,
                phase=f"{clearance_prefix}_clearance_abort",
            )
        return SafetyActionDecision(
            action=action,
            reason=f"{clearance_prefix}_scripted_clearance",
            hard_bottom_recovery_active=True,
            event_id=event_id,
            policy_restarted=self._policy_restarted(event_id),
            hard_bottom_clearance_active=True,
            contact_kind=CONTACT_KIND_HARD_BOTTOM,
            depth_exhausted_guard_active=exhausted_guard,
            hard_bottom_depth_budget_guard=depth_budget_guard,
        )

    def _depth_guard_reason(
        self,
        *,
        env_state: np.ndarray,
        active_cell_id: int,
        skill_name: str,
    ) -> str:
        cell_id = int(active_cell_id)
        bottom_sessions = int(
            round(
                env_state[
                    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX
                ]
            )
        )
        if bottom_sessions > self._handled_bottom_sessions:
            return ""
        if (
            env_state[ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX]
            >= 0.5
        ):
            return ""
        hard_bottom_depth = float(
            env_state[ENV_STATE_DIG_AREA_HARD_BOTTOM_DEPTH_IDX]
        )
        plane_depth = float(
            env_state[ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX]
        )
        depth_budget_reached = bool(
            np.isfinite(hard_bottom_depth)
            and hard_bottom_depth > 0.0
            and np.isfinite(plane_depth)
            and plane_depth
            >= hard_bottom_depth
            - float(self.config.hard_bottom_clearance_margin_m)
        )
        if not depth_budget_reached:
            return ""
        if cell_id in self._depth_exhausted_cell_ids:
            return "depth_exhausted_cell_guard"
        if str(skill_name) != "dig":
            return "hard_bottom_depth_budget_guard"
        return ""

    @staticmethod
    def _is_clearance_phase(phase: str) -> bool:
        return str(phase) in {
            "hard_bottom_clearance_complete",
            "hard_bottom_clearance_abort",
            "depth_exhausted_cell_guard_clearance_complete",
            "depth_exhausted_cell_guard_clearance_abort",
            "hard_bottom_depth_budget_guard_clearance_complete",
            "hard_bottom_depth_budget_guard_clearance_abort",
        }

    @staticmethod
    def _is_clearance_complete_phase(phase: str) -> bool:
        return str(phase) in {
            "hard_bottom_clearance_complete",
            "depth_exhausted_cell_guard_clearance_complete",
            "hard_bottom_depth_budget_guard_clearance_complete",
        }

    def _scripted_clearance_action(
        self,
        obs: dict[str, Any],
    ) -> np.ndarray:
        action_dim = int(self.config.action_dim)
        qpos = np.asarray(obs.get("qpos"), dtype=np.float32).reshape(-1)
        qvel = np.asarray(obs.get("qvel"), dtype=np.float32).reshape(-1)
        target = np.asarray(
            self.config.hard_bottom_clearance_target_qpos,
            dtype=np.float32,
        ).reshape(-1)
        signs = np.asarray(
            self.config.hard_bottom_clearance_action_signs,
            dtype=np.float32,
        ).reshape(-1)
        clip = np.asarray(
            self.config.hard_bottom_clearance_action_clip,
            dtype=np.float32,
        ).reshape(-1)
        arrays = (qpos, qvel, target, signs, clip)
        if any(array.size != action_dim for array in arrays) or not all(
            np.isfinite(array).all() for array in arrays
        ):
            raise ValueError("invalid hard-bottom clearance observation/config")
        raw = signs * (
            float(self.config.hard_bottom_clearance_kp) * (target - qpos)
            - float(self.config.hard_bottom_clearance_kd) * qvel
        )
        action = np.clip(raw, -clip, clip).astype(np.float32)
        action[0] = 0.0
        return action

    def _policy_restarted(self, event_id: int) -> bool:
        return bool(
            int(event_id) >= 0
            and int(event_id) == int(self._policy_restarted_event_id)
        )

    def _is_stuck(
        self,
        *,
        obs: dict[str, Any],
        env_state: np.ndarray,
        action: np.ndarray,
    ) -> bool:
        if float(np.abs(action).sum()) + 1.0e-8 < float(
            self.config.stuck_action_l1_min
        ):
            self._motion_window.clear()
            return False
        qpos = np.asarray(obs.get("qpos"), dtype=np.float64).reshape(-1)
        if qpos.size == 0 or not np.isfinite(qpos).all():
            self._motion_window.clear()
            return False
        tip = np.asarray(
            env_state[
                ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX :
                ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX + 3
            ],
            dtype=np.float64,
        )
        self._motion_window.append((qpos.copy(), tip.copy()))
        while len(self._motion_window) > int(self.config.stuck_window_steps):
            self._motion_window.popleft()
        if len(self._motion_window) < int(self.config.stuck_window_steps):
            return False
        qpos_stack = np.stack([sample[0] for sample in self._motion_window])
        qpos_change = float(np.ptp(qpos_stack, axis=0).max(initial=0.0))
        first_tip = self._motion_window[0][1]
        tip_displacement = max(
            float(np.linalg.norm(sample[1] - first_tip))
            for sample in self._motion_window
        )
        return bool(
            qpos_change <= float(self.config.stuck_qpos_max_change)
            and tip_displacement
            <= float(self.config.stuck_bucket_tip_max_displacement_m)
        )

    def _env_state(self, obs: dict[str, Any]) -> np.ndarray:
        env_state = np.asarray(
            obs.get("env_state"),
            dtype=np.float64,
        ).reshape(-1)
        if env_state.size < ENV_STATE_V2_4_DIM:
            raise ValueError(
                f"box safety requires {ENV_STATE_V2_4_DIM}D env_state; "
                f"got {env_state.size}"
            )
        return env_state

    def _neutral_action(self) -> np.ndarray:
        return np.zeros(int(self.config.action_dim), dtype=np.float32)


__all__ = [
    "BoxEmptyingSafetyInterlock",
    "SafetyActionDecision",
    "SafetyInterlockConfig",
]
