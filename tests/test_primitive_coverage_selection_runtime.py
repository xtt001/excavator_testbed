from __future__ import annotations

from types import MethodType
from typing import Any

import pytest

from testbed.planner.primitive_coverage import (
    CoverageCandidateSelectionFacts,
    CoverageCorridorState,
    CoverageSelectionResult,
    CoverageSelectionRuntimeCoordinator,
    CoverageSelectionRuntimePorts,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


class _FakeCandidateBuilder:
    def __init__(
        self,
        events: list[str],
        corridors: list[CoverageCorridorState],
    ) -> None:
        self.events = events
        self.corridors = corridors

    def build(self, prior: dict[str, Any]) -> list[CoverageCorridorState]:
        self.events.append(f"builder:build:{sorted(prior)}")
        return self.corridors


class _FakeSelectionService:
    def __init__(
        self,
        events: list[str],
        result: CoverageSelectionResult | None = None,
    ) -> None:
        self.events = events
        self.result = result

    def select(
        self,
        corridors: list[CoverageCorridorState],
        *,
        facts_by_corridor_id: dict[int, CoverageCandidateSelectionFacts],
        recent_row_reference: CoverageCorridorState | None,
    ) -> CoverageSelectionResult:
        self.events.append(
            "service:select:"
            f"{[int(corridor.corridor_id) for corridor in corridors]}:"
            f"{sorted(facts_by_corridor_id)}:"
            f"{-1 if recent_row_reference is None else int(recent_row_reference.corridor_id)}"
        )
        if self.result is not None:
            return self.result
        selected = corridors[-1]
        return CoverageSelectionResult(
            selected=selected,
            selected_score=12.5,
            candidate_scores=[
                {
                    "corridor_id": int(corridor.corridor_id),
                    "score": float(index),
                }
                for index, corridor in enumerate(corridors)
            ],
            first_dig_gate_available=1,
        )


def _corridor(corridor_id: int, *, depleted: bool = False) -> CoverageCorridorState:
    return CoverageCorridorState(
        corridor_id=int(corridor_id),
        entry_x_m=0.1 * float(corridor_id),
        entry_z_m=0.2,
        exit_x_m=0.3,
        exit_z_m=0.4,
        depleted=bool(depleted),
    )


def _facts_for(
    corridors: list[CoverageCorridorState],
) -> dict[int, CoverageCandidateSelectionFacts]:
    return {
        int(corridor.corridor_id): CoverageCandidateSelectionFacts(
            remaining_depth_m=0.1,
            first_dig_entry_distance_m=0.2,
            first_dig_qpos_delta=[],
        )
        for corridor in corridors
    }


def _ports(
    events: list[str],
    *,
    prior: dict[str, Any] | None = None,
    mode: str = "operator_prior_coverage",
    corridors: list[CoverageCorridorState] | None = None,
    builder_corridors: list[CoverageCorridorState] | None = None,
    selection_service: _FakeSelectionService | None = None,
    recent_reference: CoverageCorridorState | None = None,
    all_depleted_values: list[bool] | None = None,
    reopen_results: list[bool] | None = None,
) -> CoverageSelectionRuntimePorts:
    state: dict[str, Any] = {
        "prior": {} if prior is None else dict(prior),
        "corridors": [] if corridors is None else corridors,
        "candidate_scores": [],
        "active_id": -1,
        "last_selected_id": -1,
    }
    depleted_values = list(all_depleted_values or [False])
    last_depleted_value = bool(depleted_values[-1])
    reopen_values = list(reopen_results or [False])

    def coverage_corridors() -> list[CoverageCorridorState]:
        return state["corridors"]

    def set_corridors(value: list[CoverageCorridorState]) -> None:
        events.append(
            f"write:corridors:{[int(corridor.corridor_id) for corridor in value]}"
        )
        state["corridors"] = value

    def facts(obs: dict[str, Any], got_corridors: list[CoverageCorridorState]) -> dict[int, CoverageCandidateSelectionFacts]:
        events.append(
            f"facts:{obs.get('tag', '')}:"
            f"{[int(corridor.corridor_id) for corridor in got_corridors]}"
        )
        return _facts_for(got_corridors)

    def set_candidate_scores(value: list[dict[str, Any]]) -> None:
        events.append(f"write:candidate_scores:{len(value)}")
        state["candidate_scores"] = list(value)

    def record_event(
        event: str,
        *,
        obs: dict[str, Any] | None = None,
        corridor: CoverageCorridorState | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        events.append(
            f"event:{event}:{-1 if corridor is None else int(corridor.corridor_id)}:"
            f"{(extra or {}).get('selected_score', '')}:"
            f"{len((extra or {}).get('candidate_scores', []))}:"
            f"{(extra or {}).get('first_dig_gate_available', '')}"
        )

    def all_depleted() -> bool:
        value = bool(depleted_values.pop(0) if depleted_values else last_depleted_value)
        events.append(f"all_depleted:{int(value)}")
        return value

    def maybe_reopen(obs: dict[str, Any], *, reason: str) -> bool:
        value = bool(reopen_values.pop(0) if reopen_values else False)
        events.append(f"reopen:{reason}:{int(value)}")
        return value

    def terminal(reason: str) -> None:
        events.append(f"terminal:{reason}")

    def set_active(value: int) -> None:
        events.append(f"write:active:{value}")
        state["active_id"] = int(value)

    def set_last_selected(value: int) -> None:
        events.append(f"write:last_selected:{value}")
        state["last_selected_id"] = int(value)

    ports = CoverageSelectionRuntimePorts(
        dig_cut_prior=lambda: dict(state["prior"]),
        dig_cut_planner_mode=lambda: str(mode),
        coverage_corridors=coverage_corridors,
        set_coverage_corridors=set_corridors,
        candidate_builder=lambda: _FakeCandidateBuilder(
            events,
            [] if builder_corridors is None else builder_corridors,
        ),
        selection_service=lambda: (
            selection_service or _FakeSelectionService(events)
        ),
        selection_facts=facts,
        recent_row_reference=lambda: recent_reference,
        all_depleted=all_depleted,
        maybe_reopen_pass=maybe_reopen,
        request_terminal_stop=terminal,
        set_candidate_scores=set_candidate_scores,
        record_decision_event=record_event,
        set_active_corridor_id=set_active,
        set_last_selected_corridor_id=set_last_selected,
    )
    ports.test_state = state  # type: ignore[attr-defined]
    return ports


def test_ensure_corridors_skips_builder_when_corridors_already_exist() -> None:
    events: list[str] = []
    existing = [_corridor(3)]
    ports = _ports(events, prior={"fields": {}}, corridors=existing)

    CoverageSelectionRuntimeCoordinator.from_ports(ports).ensure_corridors()

    assert events == []
    assert ports.test_state["corridors"] is existing  # type: ignore[attr-defined]


def test_ensure_corridors_builds_and_writes_candidate_list() -> None:
    events: list[str] = []
    built = [_corridor(1), _corridor(2)]
    ports = _ports(events, prior={"fields": {}}, builder_corridors=built)

    CoverageSelectionRuntimeCoordinator.from_ports(ports).ensure_corridors()

    assert events == [
        "builder:build:['fields']",
        "write:corridors:[1, 2]",
    ]
    assert ports.test_state["corridors"] is built  # type: ignore[attr-defined]


def test_select_next_corridor_preserves_old_error_messages() -> None:
    coordinator = CoverageSelectionRuntimeCoordinator.from_ports(
        _ports([], prior={}, mode="operator_prior_coverage")
    )

    with pytest.raises(ValueError, match="requires a dig cut prior JSON"):
        coordinator.select_next_corridor({"tag": "obs"})

    coordinator = CoverageSelectionRuntimeCoordinator.from_ports(
        _ports([], prior={"fields": {}}, builder_corridors=[])
    )

    with pytest.raises(ValueError, match="could not build candidate corridors"):
        coordinator.select_next_corridor({"tag": "obs"})


def test_select_next_corridor_ensures_selects_then_writes_selected_ids() -> None:
    events: list[str] = []
    built = [_corridor(1), _corridor(2)]
    ports = _ports(events, prior={"fields": {}}, builder_corridors=built)

    selected = CoverageSelectionRuntimeCoordinator.from_ports(
        ports
    ).select_next_corridor({"tag": "obs"})

    assert selected is built[1]
    assert events == [
        "builder:build:['fields']",
        "write:corridors:[1, 2]",
        "all_depleted:0",
        "facts:obs:[1, 2]",
        "service:select:[1, 2]:[1, 2]:-1",
        "write:candidate_scores:2",
        "event:select_corridor:2:12.5:2:1",
        "all_depleted:0",
        "write:active:2",
        "write:last_selected:2",
    ]
    assert ports.test_state["active_id"] == 2  # type: ignore[attr-defined]
    assert ports.test_state["last_selected_id"] == 2  # type: ignore[attr-defined]


def test_select_corridor_attempts_reopen_before_select_when_all_depleted() -> None:
    events: list[str] = []
    corridors = [_corridor(1, depleted=True), _corridor(2, depleted=True)]
    ports = _ports(
        events,
        prior={"fields": {}},
        corridors=corridors,
        all_depleted_values=[True, False],
        reopen_results=[True],
    )

    selected = CoverageSelectionRuntimeCoordinator.from_ports(ports).select_corridor(
        {"tag": "obs"}
    )

    assert selected is corridors[1]
    assert events[:3] == [
        "all_depleted:1",
        "reopen:select_all_depleted:1",
        "facts:obs:[1, 2]",
    ]
    assert "service:select:[1, 2]:[1, 2]:-1" in events
    assert events[-1] == "all_depleted:0"


def test_select_corridor_records_scores_before_terminal_stop() -> None:
    events: list[str] = []
    corridors = [_corridor(1, depleted=True), _corridor(2, depleted=True)]
    ports = _ports(
        events,
        prior={"fields": {}},
        corridors=corridors,
        all_depleted_values=[False, True],
        reopen_results=[False],
    )

    CoverageSelectionRuntimeCoordinator.from_ports(ports).select_corridor(
        {"tag": "obs"}
    )

    assert events == [
        "all_depleted:0",
        "facts:obs:[1, 2]",
        "service:select:[1, 2]:[1, 2]:-1",
        "write:candidate_scores:2",
        "event:select_corridor:2:12.5:2:1",
        "all_depleted:1",
        "reopen:select_all_depleted:0",
        "terminal:dig_area_depleted",
    ]


def test_policy_coverage_selection_wrappers_delegate_to_coordinator() -> None:
    planner = object.__new__(PrimitivePlannerACTPolicy)
    obs = {"tag": "current"}
    events: list[str] = []
    selected = _corridor(4)

    class _FakeCoordinator:
        def select_next_corridor(self, got_obs: dict[str, Any]) -> CoverageCorridorState:
            assert got_obs is obs
            events.append("select_next")
            return selected

        def ensure_corridors(self) -> None:
            events.append("ensure")

        def select_corridor(self, got_obs: dict[str, Any]) -> CoverageCorridorState:
            assert got_obs is obs
            events.append("select")
            return selected

    planner._coverage_selection_runtime_coordinator = MethodType(
        lambda self: _FakeCoordinator(),
        planner,
    )

    assert planner._select_next_coverage_corridor(obs) is selected
    planner._ensure_coverage_corridors()
    assert planner._select_coverage_corridor(obs) is selected
    assert events == ["select_next", "ensure", "select"]
