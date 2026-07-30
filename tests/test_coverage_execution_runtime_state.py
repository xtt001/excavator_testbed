from __future__ import annotations

from types import SimpleNamespace

from testbed.planner.box_emptying.safety_effects import (
    SafetyDecisionCoverageEffectService,
)
from testbed.planner.primitive.coverage.selection import CoverageCorridorState
from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.token.return_planning import (
    PrimitiveReturnTokenPlanningPorts,
    PrimitiveReturnTokenPlanningService,
)


def _outcome_corridors() -> list[CoverageCorridorState]:
    return [
        CoverageCorridorState(
            corridor_id=cell_id,
            cell_id=cell_id,
            entry_x_m=float(cell_id),
            entry_z_m=0.0,
            exit_x_m=float(cell_id) - 0.5,
            exit_z_m=0.0,
        )
        for cell_id in range(6)
    ]


def test_actual_tuple_selection_keeps_four_ids_separate() -> None:
    state = CoverageRuntimeState()
    state.set_coverage_corridors(_outcome_corridors())

    state.set_active_execution_candidate(
        corridor_id=1_000_168,
        effect_outcome_cell_id=1,
        return_envelope_cell_id=0,
        exemplar_id="episode_168",
        raw_fields_sha256="a" * 64,
        execution_tail_plane_depth_reserve_m=0.003428,
    )

    assert state.coverage_active_corridor_id == 1_000_168
    assert state.coverage_active_effect_outcome_cell_id == 1
    assert state.coverage_active_return_envelope_cell_id == 0
    assert state.active_corridor() is state.coverage_corridors[1]
    assert state.active_execution_corridor_id() == 1_000_168


def test_wall_contact_blocks_actual_corridor_without_depleting_outcome_cell() -> None:
    state = CoverageRuntimeState()
    state.set_coverage_corridors(_outcome_corridors())
    state.set_active_execution_candidate(
        corridor_id=1_000_168,
        effect_outcome_cell_id=1,
        return_envelope_cell_id=0,
        exemplar_id="episode_168",
        raw_fields_sha256="b" * 64,
        execution_tail_plane_depth_reserve_m=0.003428,
    )

    result = SafetyDecisionCoverageEffectService(state).apply(
        SimpleNamespace(
            contact_kind="wall",
            blocked_corridor_id=1_000_168,
            depth_exhausted_cell_id=-1,
            wall_contact_session_count=1,
            neutral_acknowledged=True,
        )
    )

    assert result.applied is True
    assert state.wall_corridor_rejected(1_000_168) is True
    assert state.coverage_corridors[1].depleted is False


def test_return_envelope_uses_explicit_execution_tuple_group() -> None:
    state = CoverageRuntimeState()
    state.set_coverage_corridors(_outcome_corridors())
    state.set_active_execution_candidate(
        corridor_id=1_000_168,
        effect_outcome_cell_id=1,
        return_envelope_cell_id=0,
        exemplar_id="episode_168",
        raw_fields_sha256="c" * 64,
        execution_tail_plane_depth_reserve_m=0.003428,
    )
    service = PrimitiveReturnTokenPlanningService(
        PrimitiveReturnTokenPlanningPorts(
            token_state=SimpleNamespace(),
            coverage_state=state,
            dig_cut_planner_mode=lambda: "operator_prior_sweep_belief",
            return_target_token_planner=lambda: None,
            return_start_envelope_token_planner=lambda: None,
            observation_facts=lambda _obs: None,
            select_next_coverage_corridor=lambda _obs: None,
            coverage_raw_fields=lambda *_args, **_kwargs: {},
        )
    )

    assert service.return_start_envelope_cell_id(1_000_168) == 0
