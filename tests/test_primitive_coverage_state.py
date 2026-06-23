from __future__ import annotations

import math
from typing import Any

import numpy as np

from testbed.planner.primitive_coverage import CoverageCorridorState
from testbed.planner.primitive_coverage_state import CoverageRuntimeState
from tests.test_agx_primitives_v2_2 import (
    _RecordingPolicy,
    _coverage_planner_policy,
)


def _corridor(corridor_id: int, *, depleted: bool = False) -> CoverageCorridorState:
    return CoverageCorridorState(
        corridor_id=int(corridor_id),
        entry_x_m=0.1,
        entry_z_m=0.2,
        exit_x_m=0.3,
        exit_z_m=0.4,
        depleted=bool(depleted),
    )


def test_coverage_runtime_state_defaults_match_policy_reset_contract() -> None:
    state = CoverageRuntimeState()

    assert state.coverage_corridors == []
    assert state.coverage_active_corridor_id == -1
    assert state.coverage_last_selected_corridor_id == -1
    assert state.coverage_current_payload_gain_kg == 0.0
    assert state.coverage_cycle_start_deposit_kg == 0.0
    assert state.coverage_last_payload_gain_kg == 0.0
    assert state.coverage_last_effective_deposit_delta_kg == 0.0
    assert state.coverage_global_low_productivity_streak == 0
    assert state.coverage_completed_dump_count == 0
    assert state.coverage_pass_index == 0
    assert state.coverage_terminal_stop_requested is False
    assert state.coverage_terminal_stop_reason == ""
    assert state.coverage_candidate_scores == []
    assert state.coverage_decision_trace == []
    assert state.coverage_active_state_exemplar_ids == []
    assert state.coverage_rejected_state_exemplar_ids == set()
    assert math.isnan(state.coverage_active_state_exemplar_distance)
    assert state.coverage_active_state_exemplar_profile_token is None


def test_coverage_runtime_state_keeps_mutable_containers_as_source_of_truth() -> None:
    state = CoverageRuntimeState()
    corridor = _corridor(4)

    state.coverage_corridors.append(corridor)
    state.coverage_active_corridor_id = 4
    state.coverage_decision_trace.append({"event": "select_corridor"})
    state.coverage_rejected_state_exemplar_ids.add("cell0_a")

    assert state.active_corridor() is corridor
    assert state.coverage_decision_trace == [{"event": "select_corridor"}]
    assert state.coverage_rejected_state_exemplar_ids == {"cell0_a"}


def test_coverage_runtime_state_corridor_helpers_match_legacy_policy_behavior() -> None:
    state = CoverageRuntimeState(
        coverage_corridors=[
            _corridor(1, depleted=True),
            _corridor(2, depleted=False),
        ],
        coverage_active_corridor_id=2,
    )

    assert state.corridor_by_id(1) is state.coverage_corridors[0]
    assert state.corridor_by_id(99) is None
    assert state.active_corridor() is state.coverage_corridors[1]
    assert state.depleted_count() == 1
    assert state.all_depleted() is False

    state.coverage_corridors[1].depleted = True
    assert state.depleted_count() == 2
    assert state.all_depleted() is True

    state.coverage_corridors.clear()
    assert state.all_depleted() is False


def test_coverage_runtime_state_update_helpers_preserve_runtime_values() -> None:
    state = CoverageRuntimeState()
    profile = np.asarray([1.0, 2.0], dtype=np.float32)
    scores: list[dict[str, Any]] = [{"corridor_id": 1, "score": 2.5}]

    state.set_coverage_corridors([_corridor(7)])
    state.set_selected_corridor_ids(active_corridor_id=7, last_selected_corridor_id=8)
    state.set_current_payload_gain_kg(3.0)
    state.set_cycle_start_deposit_kg(4.0)
    state.set_last_payload_gain_kg(5.0)
    state.set_last_effective_deposit_delta_kg(6.0)
    state.set_completed_dump_count(2)
    state.set_global_low_productivity_streak(3)
    state.set_coverage_pass_index(1)
    state.set_terminal_stop(requested=True, reason="dig_area_depleted")
    state.set_candidate_scores(scores)
    state.update_rejected_state_exemplar_ids(("cell0_a", ""))
    state.set_active_state_exemplar(
        exemplar_ids=["cell0_a"],
        distance=0.12,
        profile_token=profile,
    )

    assert state.coverage_corridors[0].corridor_id == 7
    assert state.coverage_active_corridor_id == 7
    assert state.coverage_last_selected_corridor_id == 8
    assert state.coverage_current_payload_gain_kg == 3.0
    assert state.coverage_cycle_start_deposit_kg == 4.0
    assert state.coverage_last_payload_gain_kg == 5.0
    assert state.coverage_last_effective_deposit_delta_kg == 6.0
    assert state.coverage_completed_dump_count == 2
    assert state.coverage_global_low_productivity_streak == 3
    assert state.coverage_pass_index == 1
    assert state.coverage_terminal_stop_requested is True
    assert state.coverage_terminal_stop_reason == "dig_area_depleted"
    assert state.coverage_candidate_scores == scores
    assert state.coverage_rejected_state_exemplar_ids == {"cell0_a", ""}
    assert state.coverage_active_state_exemplar_ids == ["cell0_a"]
    assert state.coverage_active_state_exemplar_distance == 0.12
    assert state.coverage_active_state_exemplar_profile_token is profile

    state.clear_rejected_state_exemplar_ids()
    state.clear_active_state_exemplar()
    assert state.coverage_rejected_state_exemplar_ids == set()
    assert state.coverage_active_state_exemplar_ids == []
    assert math.isnan(state.coverage_active_state_exemplar_distance)
    assert state.coverage_active_state_exemplar_profile_token is None


def test_policy_coverage_private_names_are_state_backed_compatibility_facades() -> None:
    policy = _coverage_planner_policy(dig_policy=_RecordingPolicy(0))
    state = policy._coverage_state
    corridor = _corridor(11)

    policy._coverage_corridors.append(corridor)
    policy._coverage_active_corridor_id = 11
    policy._coverage_candidate_scores = [{"corridor_id": 11, "score": 1.0}]
    policy._coverage_rejected_state_exemplar_ids.add("cell0_b")

    assert policy._coverage_state is state
    assert state.coverage_corridors == [corridor]
    assert state.coverage_active_corridor_id == 11
    assert state.coverage_candidate_scores == [{"corridor_id": 11, "score": 1.0}]
    assert state.coverage_rejected_state_exemplar_ids == {"cell0_b"}
    assert policy._coverage_active_corridor() is corridor


def test_policy_selection_and_effect_ports_share_coverage_state_owner() -> None:
    policy = _coverage_planner_policy(dig_policy=_RecordingPolicy(0))
    corridor = _corridor(12)
    policy._coverage_corridors.append(corridor)

    selection_ports = policy._coverage_selection_runtime_ports()
    effect_ports = policy._coverage_effect_runtime_ports()
    token_runtime_ports = policy._primitive_token_runtime_ports()
    dig_token_ports = policy._primitive_dig_token_planning_ports()
    return_token_ports = policy._primitive_return_token_planning_ports()

    assert selection_ports.state is policy._coverage_state
    assert not hasattr(selection_ports, "coverage_corridors")
    assert not hasattr(selection_ports, "set_coverage_corridors")
    assert not hasattr(selection_ports, "set_candidate_scores")
    assert selection_ports.state.coverage_corridors is policy._coverage_state.coverage_corridors
    assert effect_ports.state is policy._coverage_state
    assert effect_ports.cycle_state is policy._cycle_state
    assert not hasattr(effect_ports, "coverage_corridors")
    assert not hasattr(effect_ports, "set_current_payload_gain_kg")
    assert not hasattr(effect_ports, "update_rejected_state_exemplar_ids")
    assert not hasattr(effect_ports, "mass_in_bucket")
    assert not hasattr(effect_ports, "completion_facts")
    assert not hasattr(effect_ports, "rejection_facts")
    assert not hasattr(effect_ports, "reopen_facts")
    assert not hasattr(effect_ports, "terminal_facts")
    assert effect_ports.state.coverage_corridors is policy._coverage_state.coverage_corridors
    assert token_runtime_ports.coverage_state is policy._coverage_state
    assert not hasattr(token_runtime_ports, "get_coverage_active_state_exemplar_ids")
    assert not hasattr(
        token_runtime_ports,
        "get_coverage_active_state_exemplar_distance",
    )
    assert not hasattr(
        token_runtime_ports,
        "get_coverage_active_state_exemplar_profile_token",
    )
    assert not hasattr(token_runtime_ports, "clear_active_state_exemplar")
    assert dig_token_ports.coverage_state is policy._coverage_state
    assert not hasattr(dig_token_ports, "active_coverage_corridor")
    assert not hasattr(dig_token_ports, "coverage_corridor_by_id")
    assert not hasattr(dig_token_ports, "set_coverage_active_corridor_id")
    assert not hasattr(dig_token_ports, "set_coverage_cycle_start_deposit_kg")
    assert (
        dig_token_ports.coverage_state.coverage_corridors
        is policy._coverage_state.coverage_corridors
    )
    assert return_token_ports.coverage_state is policy._coverage_state
    assert not hasattr(return_token_ports, "set_coverage_active_corridor_id")
    assert not hasattr(return_token_ports, "coverage_corridor_by_id")
    assert (
        return_token_ports.coverage_state.coverage_corridors
        is policy._coverage_state.coverage_corridors
    )

    selection_ports.state.set_active_corridor_id(12)
    selection_ports.state.set_last_selected_corridor_id(13)
    selection_ports.state.set_candidate_scores([{"corridor_id": 12, "score": 3.0}])
    effect_ports.state.set_current_payload_gain_kg(9.0)
    effect_ports.state.update_rejected_state_exemplar_ids(("cell0_c",))
    token_runtime_ports.coverage_state.set_active_state_exemplar(
        exemplar_ids=["cell0_d"],
        distance=0.25,
        profile_token=None,
    )
    dig_token_ports.coverage_state.set_cycle_start_deposit_kg(21.0)
    return_token_ports.coverage_state.set_active_corridor_id(14)

    assert policy._coverage_state.coverage_active_corridor_id == 14
    assert policy._coverage_state.coverage_last_selected_corridor_id == 13
    assert policy._coverage_state.coverage_candidate_scores == [
        {"corridor_id": 12, "score": 3.0}
    ]
    assert policy._coverage_state.coverage_current_payload_gain_kg == 9.0
    assert policy._coverage_state.coverage_cycle_start_deposit_kg == 21.0
    assert policy._coverage_state.coverage_rejected_state_exemplar_ids == {"cell0_c"}
    assert policy._coverage_state.coverage_active_state_exemplar_ids == ["cell0_d"]
