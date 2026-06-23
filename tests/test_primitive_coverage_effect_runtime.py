from __future__ import annotations

from dataclasses import fields
from types import MethodType
from typing import Any

import numpy as np

from testbed.planner.primitive_capabilities import PrimitiveObservationFacts
from testbed.planner.primitive_coverage import CoverageCorridorState
from testbed.planner.primitive_coverage_state import CoverageRuntimeState
from testbed.planner.primitive_cycle_state import PrimitiveCycleRuntimeState
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
        self.last_completion_facts: CoverageCompletionFacts | None = None
        self.last_rejection_facts: CoverageRejectionFacts | None = None

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
        self.last_completion_facts = facts
        self.events.append(f"update:complete_dump:{corridor.corridor_id}:{facts.reason}")
        return self.dump_result

    def reject_corridor(
        self,
        corridor: CoverageCorridorState,
        facts: CoverageRejectionFacts,
    ) -> CoverageUpdateResult:
        self.last_rejection_facts = facts
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
        self.last_reopen_facts: CoverageReopenFacts | None = None
        self.last_terminal_facts: CoverageTerminalFacts | None = None

    def maybe_reopen_pass(
        self,
        corridors: list[CoverageCorridorState],
        facts: CoverageReopenFacts,
    ) -> CoverageReopenResult:
        self.last_reopen_facts = facts
        self.events.append(f"runtime:maybe_reopen:{facts.reason}:{len(corridors)}")
        return self.reopen_result

    def request_terminal_stop(
        self,
        facts: CoverageTerminalFacts,
    ) -> CoverageTerminalResult:
        self.last_terminal_facts = facts
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
    deposited_mass: float = 11.0,
    cycle_start_deposit: float = 4.0,
    remaining_depth: float = 0.1,
    attempt_limit: int = 3,
    dig_best_mass: float = 0.0,
    active_exemplar_ids: tuple[str, ...] = ("cell0_a",),
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
    state = CoverageRuntimeState()
    state.coverage_corridors = target_corridors
    state.coverage_active_corridor_id = -1 if corridor is None else int(corridor.corridor_id)
    state.coverage_current_payload_gain_kg = float(current_payload)
    state.coverage_cycle_start_deposit_kg = float(cycle_start_deposit)
    state.coverage_active_state_exemplar_ids = list(active_exemplar_ids)
    state.coverage_terminal_stop_requested = bool(terminal_requested)
    state.coverage_terminal_stop_reason = str(terminal_reason)
    cycle_state = PrimitiveCycleRuntimeState()
    cycle_state.dig_best_mass_kg = float(dig_best_mass)

    def observation_facts(obs: dict[str, Any]) -> PrimitiveObservationFacts:
        merged = dict(obs)
        metrics = dict(merged.get("task_metrics", {}) or {})
        metrics.setdefault("mass_in_bucket_kg", float(bucket_mass))
        metrics.setdefault("deposited_mass_in_target_box_kg", float(deposited_mass))
        merged["task_metrics"] = metrics
        merged.setdefault("env_state", np.zeros(13, dtype=np.float32))
        return PrimitiveObservationFacts.from_obs(merged, action_dim=4)

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
        state=state,
        cycle_state=cycle_state,
        coverage_mode=lambda: mode,
        coverage_update_service=lambda: update_service or _FakeUpdateService(events),
        coverage_runtime_service=lambda: runtime_service or _FakeRuntimeService(events),
        observation_facts=observation_facts,
        remaining_depth=lambda obs, got_corridor: float(remaining_depth),
        corridor_attempt_limit=lambda got_corridor: int(attempt_limit),
        record_decision_event=record_event,
        coverage_global_low_productivity_stop=lambda: int(global_stop),
        coverage_low_productivity_payload_kg=lambda: float(low_payload_kg),
        coverage_low_productivity_deposit_kg=lambda: float(low_deposit_kg),
    )
    ports.test_state = state  # type: ignore[attr-defined]
    ports.test_cycle_state = cycle_state  # type: ignore[attr-defined]
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

    assert events == ["update:record_dig_payload:2.0:5.0"]
    assert ports.test_state.coverage_current_payload_gain_kg == 5.0  # type: ignore[attr-defined]


def test_complete_dump_builds_completion_facts_from_runtime_state_and_observation() -> None:
    events: list[str] = []
    update_service = _FakeUpdateService(events)
    ports = _ports(
        events,
        update_service=update_service,
        current_payload=2.5,
        deposited_mass=12.0,
        cycle_start_deposit=4.5,
        remaining_depth=0.06,
        attempt_limit=5,
    )

    CoverageEffectRuntimeCoordinator.from_ports(ports).complete_dump(
        {"obs": 1},
        reason="dump_done",
    )

    facts = update_service.last_completion_facts
    assert facts == CoverageCompletionFacts(
        payload_gain_kg=2.5,
        effective_deposit_delta_kg=7.5,
        remaining_depth_m=0.06,
        reason="dump_done",
        attempt_limit=5,
        completed_dump_count=0,
        global_low_productivity_streak=0,
    )


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
        "event:complete_dump:7:dump_done",
        "runtime:maybe_reopen:complete_all_depleted:1",
        "runtime:terminal:dig_area_depleted:False",
        "event:terminal_stop:7:dig_area_depleted",
    ]
    assert ports.test_state.coverage_last_payload_gain_kg == 6.0  # type: ignore[attr-defined]
    assert ports.test_state.coverage_last_effective_deposit_delta_kg == 2.0  # type: ignore[attr-defined]
    assert ports.test_state.coverage_completed_dump_count == 4  # type: ignore[attr-defined]
    assert ports.test_state.coverage_global_low_productivity_streak == 0  # type: ignore[attr-defined]
    assert ports.test_state.coverage_terminal_stop_requested is True  # type: ignore[attr-defined]
    assert ports.test_state.coverage_terminal_stop_reason == "dig_area_depleted"  # type: ignore[attr-defined]


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
        "update:complete_dump:7:dump_done",
        "event:complete_dump:7:dump_done",
        "runtime:terminal:low_productivity_consecutive:False",
        "event:terminal_stop:7:low_productivity_consecutive",
        "runtime:terminal:physics_artifact_suspected:False",
    ]
    assert ports.test_state.coverage_terminal_stop_reason == "low_productivity_consecutive"  # type: ignore[attr-defined]


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
        "event:reject_corridor:7:align_entry_gap_timeout",
    ]
    assert ports.test_state.coverage_rejected_state_exemplar_ids == {"cell0_a"}  # type: ignore[attr-defined]
    assert ports.test_state.coverage_last_payload_gain_kg == 3.0  # type: ignore[attr-defined]
    assert ports.test_state.coverage_last_effective_deposit_delta_kg == 1.0  # type: ignore[attr-defined]
    assert ports.test_state.coverage_global_low_productivity_streak == 0  # type: ignore[attr-defined]


def test_reject_builds_rejection_facts_from_runtime_state_and_observation() -> None:
    events: list[str] = []
    update_service = _FakeUpdateService(events)
    ports = _ports(
        events,
        update_service=update_service,
        current_payload=2.0,
        bucket_mass=5.5,
        deposited_mass=13.0,
        cycle_start_deposit=3.0,
        remaining_depth=0.07,
        attempt_limit=4,
        dig_best_mass=6.25,
        active_exemplar_ids=("cell0_a", "cell0_b"),
    )

    CoverageEffectRuntimeCoordinator.from_ports(ports).reject_active_corridor(
        {"obs": 1},
        reason="bad_dig",
    )

    facts = update_service.last_rejection_facts
    assert facts == CoverageRejectionFacts(
        payload_gain_kg=6.25,
        effective_deposit_delta_kg=10.0,
        remaining_depth_m=0.07,
        reason="bad_dig",
        attempt_limit=4,
        global_low_productivity_streak=0,
        active_state_exemplar_ids=("cell0_a", "cell0_b"),
    )


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

    assert events[-4:] == [
        "event:reject_corridor:7:bad_dig",
        "runtime:maybe_reopen:reject_all_depleted:1",
        "runtime:terminal:dig_area_depleted:False",
        "event:terminal_stop:7:dig_area_depleted",
    ]
    assert ports.test_state.coverage_terminal_stop_reason == "dig_area_depleted"  # type: ignore[attr-defined]


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
    runtime_service = _FakeRuntimeService(events, reopen_result=reopen_result)
    ports = _ports(
        events,
        corridors=[corridor],
        runtime_service=runtime_service,
    )
    ports.test_state.coverage_rejected_state_exemplar_ids.add("cell0_a")  # type: ignore[attr-defined]

    reopened = CoverageEffectRuntimeCoordinator.from_ports(ports).maybe_reopen_pass(
        {"obs": 1},
        reason="unit_reopen",
    )

    assert reopened is True
    assert ports.test_state.coverage_pass_index == 2  # type: ignore[attr-defined]
    assert ports.test_state.coverage_active_corridor_id == -1  # type: ignore[attr-defined]
    assert ports.test_state.coverage_global_low_productivity_streak == 0  # type: ignore[attr-defined]
    assert ports.test_state.coverage_rejected_state_exemplar_ids == set()  # type: ignore[attr-defined]
    assert events == [
        "runtime:maybe_reopen:unit_reopen:1",
        "event:reopen_coverage_pass:-1:unit_reopen",
    ]
    assert runtime_service.last_reopen_facts == CoverageReopenFacts(
        reason="unit_reopen",
        pass_index=0,
        terminal_stop_requested=False,
        remaining_depth_by_corridor_id={7: 0.1},
    )


def test_request_terminal_stop_skips_duplicate_without_replace() -> None:
    events: list[str] = []
    runtime_service = _FakeRuntimeService(events)
    ports = _ports(
        events,
        runtime_service=runtime_service,
        terminal_requested=True,
        terminal_reason="first_reason",
    )

    CoverageEffectRuntimeCoordinator.from_ports(ports).request_terminal_stop(
        "ignored_reason",
    )

    assert events == ["runtime:terminal:ignored_reason:False"]
    assert ports.test_state.coverage_terminal_stop_reason == "first_reason"  # type: ignore[attr-defined]
    assert runtime_service.last_terminal_facts == CoverageTerminalFacts(
        reason="ignored_reason",
        replace=False,
        terminal_stop_requested=True,
        terminal_stop_reason="first_reason",
    )


def test_request_terminal_stop_records_event_with_current_active_corridor() -> None:
    events: list[str] = []
    ports = _ports(events)

    CoverageEffectRuntimeCoordinator.from_ports(ports).request_terminal_stop(
        "dig_area_depleted",
    )

    assert events == [
        "runtime:terminal:dig_area_depleted:False",
        "event:terminal_stop:7:dig_area_depleted",
    ]
    assert ports.test_state.coverage_terminal_stop_requested is True  # type: ignore[attr-defined]
    assert ports.test_state.coverage_terminal_stop_reason == "dig_area_depleted"  # type: ignore[attr-defined]


def test_effect_runtime_ports_carry_state_owner_without_state_callbacks() -> None:
    ports = _ports([])
    port_fields = {field.name for field in fields(CoverageEffectRuntimePorts)}

    assert isinstance(ports.state, CoverageRuntimeState)
    assert isinstance(ports.cycle_state, PrimitiveCycleRuntimeState)
    assert "coverage_corridors" not in port_fields
    assert "active_corridor" not in port_fields
    assert "current_payload_gain_kg" not in port_fields
    assert "set_current_payload_gain_kg" not in port_fields
    assert "set_last_payload_gain_kg" not in port_fields
    assert "set_last_effective_deposit_delta_kg" not in port_fields
    assert "set_completed_dump_count" not in port_fields
    assert "set_global_low_productivity_streak" not in port_fields
    assert "update_rejected_state_exemplar_ids" not in port_fields
    assert "set_coverage_pass_index" not in port_fields
    assert "set_active_corridor_id" not in port_fields
    assert "clear_rejected_state_exemplar_ids" not in port_fields
    assert "set_terminal_stop_requested" not in port_fields
    assert "set_terminal_stop_reason" not in port_fields
    assert "mass_in_bucket" not in port_fields
    assert "completion_facts" not in port_fields
    assert "rejection_facts" not in port_fields
    assert "reopen_facts" not in port_fields
    assert "terminal_facts" not in port_fields
    assert "observation_facts" in port_fields
    assert "remaining_depth" in port_fields
    assert "corridor_attempt_limit" in port_fields
    assert "planner" not in port_fields
    assert "self" not in port_fields


def test_policy_no_longer_exposes_coverage_effect_fact_facades() -> None:
    removed_names = {
        "_coverage_completion_facts",
        "_coverage_rejection_facts",
        "_coverage_reopen_facts",
        "_coverage_terminal_facts",
    }

    assert removed_names.isdisjoint(PrimitivePlannerACTPolicy.__dict__)


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
