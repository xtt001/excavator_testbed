from __future__ import annotations

from types import MethodType
from typing import Any

from testbed.planner.primitive_coverage import CoverageCorridorState
from testbed.planner.primitive_coverage_updates import (
    CoverageCompletionFacts,
    CoverageEffectRuntimeCoordinator,
    CoverageEffectRuntimePorts,
    CoverageRejectionFacts,
    CoverageReopenFacts,
    CoverageReopenResult,
    CoverageTerminalFacts,
    CoverageTerminalResult,
    CoverageUpdateResult,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


class _FakeUpdateService:
    def __init__(
        self,
        events: list[str],
        *,
        dump_result: CoverageUpdateResult | None = None,
        reject_result: CoverageUpdateResult | None = None,
    ) -> None:
        self.events = events
        self.dump_result = dump_result or CoverageUpdateResult(
            payload_gain_kg=6.0,
            effective_deposit_delta_kg=2.0,
            remaining_depth_m=0.03,
            final_reason="complete_reason",
            low_productivity=False,
            completed_dump_count=4,
            global_low_productivity_streak=0,
            counted_attempt=1,
        )
        self.reject_result = reject_result or CoverageUpdateResult(
            payload_gain_kg=3.0,
            effective_deposit_delta_kg=1.0,
            remaining_depth_m=0.04,
            final_reason="reject_reason",
            low_productivity=True,
            completed_dump_count=0,
            global_low_productivity_streak=2,
            counted_attempt=1,
            rejected_state_exemplar_ids=("cell0_a",),
        )

    def record_dig_payload(
        self,
        current_payload_gain_kg: float,
        bucket_mass_kg: float,
    ) -> float:
        self.events.append(
            f"update:record_dig_payload:{current_payload_gain_kg}:{bucket_mass_kg}"
        )
        return max(float(current_payload_gain_kg), float(bucket_mass_kg))

    def complete_dump(
        self,
        corridor: CoverageCorridorState,
        facts: CoverageCompletionFacts,
    ) -> CoverageUpdateResult:
        self.events.append(f"update:complete_dump:{corridor.corridor_id}:{facts.reason}")
        return self.dump_result

    def reject_corridor(
        self,
        corridor: CoverageCorridorState,
        facts: CoverageRejectionFacts,
    ) -> CoverageUpdateResult:
        self.events.append(
            f"update:reject_corridor:{corridor.corridor_id}:{facts.reason}"
        )
        return self.reject_result


class _FakeRuntimeService:
    def __init__(
        self,
        events: list[str],
        *,
        reopen_result: CoverageReopenResult | None = None,
    ) -> None:
        self.events = events
        self.reopen_result = reopen_result or CoverageReopenResult(
            reopened=False,
            reason="blocked",
            pass_index=0,
            active_corridor_id=-1,
            global_low_productivity_streak=0,
            clear_rejected_state_exemplar_ids=False,
            max_passes=2,
            min_remaining_depth_m=0.05,
            reopened_corridors=[],
        )

    def maybe_reopen_pass(
        self,
        corridors: list[CoverageCorridorState],
        facts: CoverageReopenFacts,
    ) -> CoverageReopenResult:
        self.events.append(f"runtime:maybe_reopen:{facts.reason}:{len(corridors)}")
        return self.reopen_result

    def request_terminal_stop(
        self,
        facts: CoverageTerminalFacts,
    ) -> CoverageTerminalResult:
        self.events.append(f"runtime:terminal:{facts.reason}:{facts.replace}")
        if facts.terminal_stop_requested and not facts.replace:
            return CoverageTerminalResult(
                terminal_stop_requested=True,
                terminal_stop_reason=facts.terminal_stop_reason,
                record_event=False,
            )
        return CoverageTerminalResult(
            terminal_stop_requested=True,
            terminal_stop_reason=facts.reason,
            record_event=True,
        )


def _corridor(*, depleted: bool = False) -> CoverageCorridorState:
    return CoverageCorridorState(
        corridor_id=7,
        entry_x_m=0.1,
        entry_z_m=0.2,
        exit_x_m=0.3,
        exit_z_m=0.4,
        depleted=depleted,
    )


def _ports(
    events: list[str],
    *,
    mode: str = "operator_prior_coverage",
    corridors: list[CoverageCorridorState] | None = None,
    active_corridor: CoverageCorridorState | None = None,
    update_service: _FakeUpdateService | None = None,
    runtime_service: _FakeRuntimeService | None = None,
    current_payload: float = 2.0,
    bucket_mass: float = 5.0,
    terminal_requested: bool = False,
    terminal_reason: str = "",
    global_stop: int = 3,
    low_payload_kg: float = 4.0,
    low_deposit_kg: float = 2.0,
) -> CoverageEffectRuntimePorts:
    corridor = active_corridor
    target_corridors = corridors
    if target_corridors is None:
        corridor = corridor or _corridor()
        target_corridors = [corridor]
    elif corridor is None:
        corridor = target_corridors[0] if target_corridors else None
    state: dict[str, Any] = {
        "current_payload": float(current_payload),
        "last_payload": 0.0,
        "last_deposit": 0.0,
        "completed_dump_count": 0,
        "global_streak": 0,
        "pass_index": 0,
        "active_corridor_id": -1,
        "terminal_requested": bool(terminal_requested),
        "terminal_reason": str(terminal_reason),
        "rejected_ids": set(),
    }

    def set_current_payload(value: float) -> None:
        events.append(f"write:current_payload:{value}")
        state["current_payload"] = float(value)

    def set_last_payload(value: float) -> None:
        events.append(f"write:last_payload:{value}")
        state["last_payload"] = float(value)

    def set_last_deposit(value: float) -> None:
        events.append(f"write:last_deposit:{value}")
        state["last_deposit"] = float(value)

    def set_completed_dump_count(value: int) -> None:
        events.append(f"write:completed_dump_count:{value}")
        state["completed_dump_count"] = int(value)

    def set_global_streak(value: int) -> None:
        events.append(f"write:global_streak:{value}")
        state["global_streak"] = int(value)

    def update_rejected(ids: tuple[str, ...]) -> None:
        events.append(f"write:rejected_ids:{','.join(ids)}")
        state["rejected_ids"].update(ids)

    def set_pass_index(value: int) -> None:
        events.append(f"write:pass_index:{value}")
        state["pass_index"] = int(value)

    def set_active_corridor_id(value: int) -> None:
        events.append(f"write:active_corridor_id:{value}")
        state["active_corridor_id"] = int(value)

    def clear_rejected_ids() -> None:
        events.append("write:clear_rejected_ids")
        state["rejected_ids"].clear()

    def set_terminal_requested(value: bool) -> None:
        events.append(f"write:terminal_requested:{int(value)}")
        state["terminal_requested"] = bool(value)

    def set_terminal_reason(value: str) -> None:
        events.append(f"write:terminal_reason:{value}")
        state["terminal_reason"] = str(value)

    def record_event(
        event: str,
        *,
        obs: dict[str, Any] | None = None,
        corridor: CoverageCorridorState | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        events.append(
            f"event:{event}:{-1 if corridor is None else corridor.corridor_id}:"
            f"{(extra or {}).get('reason', '')}"
        )

    ports = CoverageEffectRuntimePorts(
        coverage_mode=lambda: mode,
        coverage_update_service=lambda: update_service or _FakeUpdateService(events),
        coverage_runtime_service=lambda: runtime_service or _FakeRuntimeService(events),
        coverage_corridors=lambda: target_corridors,
        active_corridor=lambda: corridor,
        current_payload_gain_kg=lambda: float(state["current_payload"]),
        set_current_payload_gain_kg=set_current_payload,
        mass_in_bucket=lambda obs: float(bucket_mass),
        completion_facts=lambda obs, got_corridor, reason: CoverageCompletionFacts(
            payload_gain_kg=1.0,
            effective_deposit_delta_kg=1.0,
            remaining_depth_m=0.1,
            reason=reason,
            attempt_limit=3,
            completed_dump_count=0,
            global_low_productivity_streak=0,
        ),
        rejection_facts=lambda obs, got_corridor, reason: CoverageRejectionFacts(
            payload_gain_kg=1.0,
            effective_deposit_delta_kg=1.0,
            remaining_depth_m=0.1,
            reason=reason,
            attempt_limit=3,
            global_low_productivity_streak=0,
            active_state_exemplar_ids=("cell0_a",),
        ),
        reopen_facts=lambda obs, got_corridors, reason: CoverageReopenFacts(
            reason=reason,
            pass_index=0,
            terminal_stop_requested=bool(state["terminal_requested"]),
            remaining_depth_by_corridor_id={
                int(item.corridor_id): 0.1 for item in got_corridors
            },
        ),
        terminal_facts=lambda reason, replace: CoverageTerminalFacts(
            reason=reason,
            replace=replace,
            terminal_stop_requested=bool(state["terminal_requested"]),
            terminal_stop_reason=str(state["terminal_reason"]),
        ),
        set_last_payload_gain_kg=set_last_payload,
        set_last_effective_deposit_delta_kg=set_last_deposit,
        set_completed_dump_count=set_completed_dump_count,
        set_global_low_productivity_streak=set_global_streak,
        update_rejected_state_exemplar_ids=update_rejected,
        set_coverage_pass_index=set_pass_index,
        set_active_corridor_id=set_active_corridor_id,
        clear_rejected_state_exemplar_ids=clear_rejected_ids,
        set_terminal_stop_requested=set_terminal_requested,
        set_terminal_stop_reason=set_terminal_reason,
        record_decision_event=record_event,
        coverage_global_low_productivity_stop=lambda: int(global_stop),
        coverage_low_productivity_payload_kg=lambda: float(low_payload_kg),
        coverage_low_productivity_deposit_kg=lambda: float(low_deposit_kg),
    )
    ports.test_state = state  # type: ignore[attr-defined]
    return ports


def test_non_coverage_mode_skips_complete_and_reject_effects() -> None:
    events: list[str] = []
    ports = _ports(events, mode="operator_prior")
    coordinator = CoverageEffectRuntimeCoordinator.from_ports(ports)

    coordinator.complete_dig({"obs": 1})
    coordinator.complete_dump({"obs": 1}, reason="dump_done")
    coordinator.reject_active_corridor({"obs": 1}, reason="bad_dig")

    assert events == []


def test_complete_dig_records_max_payload_gain() -> None:
    events: list[str] = []
    ports = _ports(events, current_payload=2.0, bucket_mass=5.0)

    CoverageEffectRuntimeCoordinator.from_ports(ports).complete_dig({"obs": 1})

    assert events == [
        "update:record_dig_payload:2.0:5.0",
        "write:current_payload:5.0",
    ]
    assert ports.test_state["current_payload"] == 5.0  # type: ignore[attr-defined]


def test_complete_dump_writes_result_then_event_then_reopen_terminal_checks() -> None:
    events: list[str] = []
    corridor = _corridor(depleted=True)
    update_service = _FakeUpdateService(
        events,
        dump_result=CoverageUpdateResult(
            payload_gain_kg=6.0,
            effective_deposit_delta_kg=2.0,
            remaining_depth_m=0.03,
            final_reason="complete_reason",
            low_productivity=False,
            completed_dump_count=4,
            global_low_productivity_streak=0,
            counted_attempt=1,
        ),
    )
    runtime_service = _FakeRuntimeService(events)
    ports = _ports(
        events,
        corridors=[corridor],
        update_service=update_service,
        runtime_service=runtime_service,
    )

    CoverageEffectRuntimeCoordinator.from_ports(ports).complete_dump(
        {"obs": 1},
        reason="dump_done",
    )

    assert events == [
        "update:complete_dump:7:dump_done",
        "write:last_payload:6.0",
        "write:last_deposit:2.0",
        "write:completed_dump_count:4",
        "write:global_streak:0",
        "event:complete_dump:7:dump_done",
        "runtime:maybe_reopen:complete_all_depleted:1",
        "runtime:terminal:dig_area_depleted:False",
        "write:terminal_requested:1",
        "write:terminal_reason:dig_area_depleted",
        "event:terminal_stop:7:dig_area_depleted",
    ]


def test_complete_dump_global_terminal_precedes_physics_terminal_request() -> None:
    events: list[str] = []
    corridor = _corridor(depleted=False)
    other = _corridor(depleted=False)
    other.corridor_id = 9
    update_service = _FakeUpdateService(
        events,
        dump_result=CoverageUpdateResult(
            payload_gain_kg=1.0,
            effective_deposit_delta_kg=3.0,
            remaining_depth_m=0.03,
            final_reason="complete_reason",
            low_productivity=True,
            completed_dump_count=4,
            global_low_productivity_streak=3,
            counted_attempt=1,
        ),
    )
    ports = _ports(
        events,
        corridors=[corridor, other],
        update_service=update_service,
        runtime_service=_FakeRuntimeService(events),
        global_stop=3,
        low_payload_kg=4.0,
        low_deposit_kg=2.0,
    )

    CoverageEffectRuntimeCoordinator.from_ports(ports).complete_dump(
        {"obs": 1},
        reason="dump_done",
    )

    assert events[-6:] == [
        "event:complete_dump:7:dump_done",
        "runtime:terminal:low_productivity_consecutive:False",
        "write:terminal_requested:1",
        "write:terminal_reason:low_productivity_consecutive",
        "event:terminal_stop:7:low_productivity_consecutive",
        "runtime:terminal:physics_artifact_suspected:False",
    ]


def test_reject_counted_attempt_zero_records_event_and_skips_terminal_checks() -> None:
    events: list[str] = []
    reject_result = CoverageUpdateResult(
        payload_gain_kg=3.0,
        effective_deposit_delta_kg=1.0,
        remaining_depth_m=0.04,
        final_reason="align_entry_gap_timeout",
        low_productivity=False,
        completed_dump_count=0,
        global_low_productivity_streak=0,
        counted_attempt=0,
        rejected_state_exemplar_ids=("cell0_a",),
    )
    ports = _ports(
        events,
        update_service=_FakeUpdateService(events, reject_result=reject_result),
        runtime_service=_FakeRuntimeService(events),
    )

    CoverageEffectRuntimeCoordinator.from_ports(ports).reject_active_corridor(
        {"obs": 1},
        reason="align_entry_gap_timeout",
    )

    assert events == [
        "update:reject_corridor:7:align_entry_gap_timeout",
        "write:rejected_ids:cell0_a",
        "write:last_payload:3.0",
        "write:last_deposit:1.0",
        "write:global_streak:0",
        "event:reject_corridor:7:align_entry_gap_timeout",
    ]


def test_reject_counted_attempt_path_checks_reopen_or_terminal() -> None:
    events: list[str] = []
    corridor = _corridor(depleted=True)
    ports = _ports(
        events,
        corridors=[corridor],
        update_service=_FakeUpdateService(events),
        runtime_service=_FakeRuntimeService(events),
    )

    CoverageEffectRuntimeCoordinator.from_ports(ports).reject_active_corridor(
        {"obs": 1},
        reason="bad_dig",
    )

    assert events[-5:] == [
        "runtime:maybe_reopen:reject_all_depleted:1",
        "runtime:terminal:dig_area_depleted:False",
        "write:terminal_requested:1",
        "write:terminal_reason:dig_area_depleted",
        "event:terminal_stop:7:dig_area_depleted",
    ]


def test_maybe_reopen_pass_applies_result_and_records_event() -> None:
    events: list[str] = []
    corridor = _corridor(depleted=True)
    reopen_result = CoverageReopenResult(
        reopened=True,
        reason="unit_reopen",
        pass_index=2,
        active_corridor_id=-1,
        global_low_productivity_streak=0,
        clear_rejected_state_exemplar_ids=True,
        max_passes=3,
        min_remaining_depth_m=0.04,
        reopened_corridors=[{"corridor_id": 7, "remaining_depth_m": 0.12}],
    )
    ports = _ports(
        events,
        corridors=[corridor],
        runtime_service=_FakeRuntimeService(events, reopen_result=reopen_result),
    )
    ports.test_state["rejected_ids"].add("cell0_a")  # type: ignore[attr-defined]

    reopened = CoverageEffectRuntimeCoordinator.from_ports(ports).maybe_reopen_pass(
        {"obs": 1},
        reason="unit_reopen",
    )

    assert reopened is True
    assert ports.test_state["pass_index"] == 2  # type: ignore[attr-defined]
    assert ports.test_state["active_corridor_id"] == -1  # type: ignore[attr-defined]
    assert ports.test_state["global_streak"] == 0  # type: ignore[attr-defined]
    assert ports.test_state["rejected_ids"] == set()  # type: ignore[attr-defined]
    assert events == [
        "runtime:maybe_reopen:unit_reopen:1",
        "write:pass_index:2",
        "write:active_corridor_id:-1",
        "write:global_streak:0",
        "write:clear_rejected_ids",
        "event:reopen_coverage_pass:-1:unit_reopen",
    ]


def test_request_terminal_stop_skips_duplicate_without_replace() -> None:
    events: list[str] = []
    ports = _ports(
        events,
        terminal_requested=True,
        terminal_reason="first_reason",
    )

    CoverageEffectRuntimeCoordinator.from_ports(ports).request_terminal_stop(
        "ignored_reason",
    )

    assert events == ["runtime:terminal:ignored_reason:False"]
    assert ports.test_state["terminal_reason"] == "first_reason"  # type: ignore[attr-defined]


def test_request_terminal_stop_records_event_with_current_active_corridor() -> None:
    events: list[str] = []
    ports = _ports(events)

    CoverageEffectRuntimeCoordinator.from_ports(ports).request_terminal_stop(
        "dig_area_depleted",
    )

    assert events == [
        "runtime:terminal:dig_area_depleted:False",
        "write:terminal_requested:1",
        "write:terminal_reason:dig_area_depleted",
        "event:terminal_stop:7:dig_area_depleted",
    ]


def test_policy_coverage_effect_wrappers_delegate_to_coordinator() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    obs = {"tag": "current"}
    events: list[str] = []

    class _FakeCoordinator:
        def complete_dig(self, got_obs: dict[str, Any]) -> None:
            assert got_obs is obs
            events.append("complete_dig")

        def complete_dump(self, got_obs: dict[str, Any], *, reason: str) -> None:
            assert got_obs is obs
            events.append(f"complete_dump:{reason}")

        def reject_active_corridor(
            self,
            got_obs: dict[str, Any],
            *,
            reason: str,
        ) -> None:
            assert got_obs is obs
            events.append(f"reject:{reason}")

        def maybe_reopen_pass(self, got_obs: dict[str, Any], *, reason: str) -> bool:
            assert got_obs is obs
            events.append(f"reopen:{reason}")
            return True

        def request_terminal_stop(self, reason: str, *, replace: bool = False) -> None:
            events.append(f"terminal:{reason}:{replace}")

    planner._coverage_effect_runtime_coordinator = MethodType(
        lambda self: _FakeCoordinator(),
        planner,
    )

    planner._complete_coverage_dig(obs)
    planner._complete_coverage_dump(obs, reason="dump_done")
    planner._reject_active_coverage_corridor(obs, reason="bad_dig")
    reopened = planner._maybe_reopen_coverage_pass(obs, reason="all_depleted")
    planner._request_coverage_terminal_stop("terminal", replace=True)

    assert reopened is True
    assert events == [
        "complete_dig",
        "complete_dump:dump_done",
        "reject:bad_dig",
        "reopen:all_depleted",
        "terminal:terminal:True",
    ]
