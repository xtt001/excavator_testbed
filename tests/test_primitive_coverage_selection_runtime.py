from __future__ import annotations

from dataclasses import fields
from typing import Any

import pytest

from testbed.planner.primitive.coverage.selection import (
    CoverageCandidateSelectionFacts,
    CoverageCorridorState,
    CoverageSelectionResult,
    CoverageSelectionRuntimeCoordinator,
    CoverageSelectionRuntimePorts,
)
from testbed.planner.primitive.coverage.state import CoverageRuntimeState
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
    reopen_results: list[bool] | None = None,
) -> CoverageSelectionRuntimePorts:
    fact_values: dict[str, Any] = {
        "prior": {} if prior is None else dict(prior),
    }
    state = CoverageRuntimeState()
    state.coverage_corridors = [] if corridors is None else corridors
    reopen_values = list(reopen_results or [False])

    def facts(obs: dict[str, Any], got_corridors: list[CoverageCorridorState]) -> dict[int, CoverageCandidateSelectionFacts]:
        events.append(
            f"facts:{obs.get('tag', '')}:"
            f"{[int(corridor.corridor_id) for corridor in got_corridors]}"
        )
        return _facts_for(got_corridors)

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

    def maybe_reopen(obs: dict[str, Any], *, reason: str) -> bool:
        value = bool(reopen_values.pop(0) if reopen_values else False)
        events.append(f"reopen:{reason}:{int(value)}")
        if value:
            for corridor in state.coverage_corridors:
                corridor.depleted = False
        return value

    def terminal(reason: str) -> None:
        events.append(f"terminal:{reason}")

    ports = CoverageSelectionRuntimePorts(
        state=state,
        dig_cut_prior=lambda: dict(fact_values["prior"]),
        dig_cut_planner_mode=lambda: str(mode),
        candidate_builder=lambda: _FakeCandidateBuilder(
            events,
            [] if builder_corridors is None else builder_corridors,
        ),
        selection_service=lambda: (
            selection_service or _FakeSelectionService(events)
        ),
        selection_facts=facts,
        recent_row_reference=lambda: recent_reference,
        maybe_reopen_pass=maybe_reopen,
        request_terminal_stop=terminal,
        record_decision_event=record_event,
    )
    ports.test_state = state  # type: ignore[attr-defined]
    return ports


def test_ensure_corridors_skips_builder_when_corridors_already_exist() -> None:
    events: list[str] = []
    existing = [_corridor(3)]
    ports = _ports(events, prior={"fields": {}}, corridors=existing)

    CoverageSelectionRuntimeCoordinator.from_ports(ports).ensure_corridors()

    assert events == []
    assert ports.test_state.coverage_corridors is existing  # type: ignore[attr-defined]


def test_ensure_corridors_builds_and_writes_candidate_list() -> None:
    events: list[str] = []
    built = [_corridor(1), _corridor(2)]
    ports = _ports(events, prior={"fields": {}}, builder_corridors=built)

    CoverageSelectionRuntimeCoordinator.from_ports(ports).ensure_corridors()

    assert events == [
        "builder:build:['fields']",
    ]
    assert ports.test_state.coverage_corridors is built  # type: ignore[attr-defined]


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
        "facts:obs:[1, 2]",
        "service:select:[1, 2]:[1, 2]:-1",
        "event:select_corridor:2:12.5:2:1",
    ]
    assert ports.test_state.coverage_active_corridor_id == 2  # type: ignore[attr-defined]
    assert ports.test_state.coverage_last_selected_corridor_id == 2  # type: ignore[attr-defined]
    assert ports.test_state.coverage_candidate_scores == [  # type: ignore[attr-defined]
        {"corridor_id": 1, "score": 0.0},
        {"corridor_id": 2, "score": 1.0},
    ]


def test_select_corridor_attempts_reopen_before_select_when_all_depleted() -> None:
    events: list[str] = []
    corridors = [_corridor(1, depleted=True), _corridor(2, depleted=True)]
    ports = _ports(
        events,
        prior={"fields": {}},
        corridors=corridors,
        reopen_results=[True],
    )

    selected = CoverageSelectionRuntimeCoordinator.from_ports(ports).select_corridor(
        {"tag": "obs"}
    )

    assert selected is corridors[1]
    assert events[:2] == [
        "reopen:select_all_depleted:1",
        "facts:obs:[1, 2]",
    ]
    assert "service:select:[1, 2]:[1, 2]:-1" in events
    assert "terminal:dig_area_depleted" not in events


def test_select_corridor_records_scores_before_terminal_stop() -> None:
    events: list[str] = []
    corridors = [_corridor(1, depleted=True), _corridor(2, depleted=True)]
    ports = _ports(
        events,
        prior={"fields": {}},
        corridors=corridors,
        reopen_results=[False],
    )

    CoverageSelectionRuntimeCoordinator.from_ports(ports).select_corridor(
        {"tag": "obs"}
    )

    assert events == [
        "reopen:select_all_depleted:0",
        "facts:obs:[1, 2]",
        "service:select:[1, 2]:[1, 2]:-1",
        "event:select_corridor:2:12.5:2:1",
        "reopen:select_all_depleted:0",
        "terminal:dig_area_depleted",
    ]


def test_selection_runtime_ports_carry_state_owner_without_state_callbacks() -> None:
    ports = _ports([])
    port_fields = {field.name for field in fields(CoverageSelectionRuntimePorts)}

    assert isinstance(ports.state, CoverageRuntimeState)
    assert "coverage_corridors" not in port_fields
    assert "set_coverage_corridors" not in port_fields
    assert "set_candidate_scores" not in port_fields
    assert "set_active_corridor_id" not in port_fields
    assert "set_last_selected_corridor_id" not in port_fields
    assert "all_depleted" not in port_fields
    assert "planner" not in port_fields
    assert "self" not in port_fields


def test_coverage_selection_runtime_delegates_to_coordinator() -> None:
    obs = {"tag": "current"}
    events: list[str] = []
    selected = _corridor(4)

    class _FakeRuntime:
        def select_next_coverage_corridor(
            self,
            got_obs: dict[str, Any],
        ) -> CoverageCorridorState:
            assert got_obs is obs
            events.append("select_next")
            return selected

        def ensure_coverage_corridors(self) -> None:
            events.append("ensure")

        def select_coverage_corridor(
            self,
            got_obs: dict[str, Any],
        ) -> CoverageCorridorState:
            assert got_obs is obs
            events.append("select")
            return selected

    runtime = _FakeRuntime()

    assert runtime.select_next_coverage_corridor(obs) is selected
    runtime.ensure_coverage_corridors()
    assert runtime.select_coverage_corridor(obs) is selected
    assert events == ["select_next", "ensure", "select"]


def test_policy_no_longer_exposes_coverage_selection_private_wrappers() -> None:
    removed_names = {
        "_coverage_selection_runtime_ports",
        "_coverage_selection_runtime_coordinator",
        "_select_next_coverage_corridor",
        "_ensure_coverage_corridors",
        "_coverage_selection_config",
        "_coverage_selection_service",
        "_coverage_planning_fact_config",
        "_coverage_planning_fact_service",
        "_coverage_selection_facts",
        "_select_coverage_corridor",
        "_coverage_raw_fields",
        "_coverage_state_exemplar_planner_config",
        "_coverage_state_exemplar_planner",
        "_coverage_remaining_depth_for_corridor",
    }

    assert removed_names.isdisjoint(PrimitivePlannerACTPolicy.__dict__)


def test_policy_no_longer_exposes_coverage_scoring_exemplar_private_wrappers() -> None:
    removed_names = {
        "_set_coverage_corridors",
        "_set_coverage_candidate_scores",
        "_set_coverage_last_selected_corridor_id",
        "_build_cell_weighted_coverage_corridors",
        "_coverage_cell_float",
        "_coverage_stat_float",
        "_coverage_exit_from_entry",
        "_coverage_first_dig_active",
        "_coverage_first_dig_gate_available",
        "_coverage_first_dig_entry_reachable",
        "_coverage_score",
        "_coverage_cell_confidence",
        "_coverage_corridor_is_rare",
        "_coverage_corridor_attempt_limit",
        "_coverage_rare_first_dig_gated_out",
        "_coverage_recent_row_penalty",
        "_coverage_recent_row_reference_corridor",
        "_coverage_first_dig_bonus",
        "_coverage_entry_distance_m",
        "_coverage_first_dig_qpos_delta",
        "_coverage_first_dig_qpos_reachable",
        "_coverage_first_dig_qpos_delta_penalty",
        "_load_coverage_state_exemplars",
        "_coverage_state_conditioned_plan",
        "_coverage_state_exemplar_distance",
        "_coverage_state_exemplar_id",
        "_coverage_removed_depth_grid",
        "_coverage_state_exemplar_distance_for_grid",
        "_state_exemplar_weights",
        "_weighted_state_exemplar_raw_fields",
        "_weighted_state_exemplar_profile_token",
        "_coverage_cell_id",
        "_coverage_corridor_row_id",
        "_coverage_cell_id_from_percentile_indices",
    }

    assert removed_names.isdisjoint(PrimitivePlannerACTPolicy.__dict__)
