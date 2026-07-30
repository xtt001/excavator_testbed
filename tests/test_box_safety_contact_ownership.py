from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from testbed.planner.box_emptying.contact_ownership import (
    CONTACT_KIND_HARD_BOTTOM,
    CONTACT_KIND_NONE,
    CONTACT_KIND_WALL,
    SafetyContactOwnership,
)
from testbed.planner.box_emptying.safety_effects import (
    SafetyDecisionCoverageEffectService,
)
from testbed.planner.box_emptying.safety_interlock import SafetyActionDecision
from testbed.planner.primitive.coverage.selection import CoverageCorridorState
from testbed.planner.primitive.coverage.state import CoverageRuntimeState


def _decision(**overrides: object) -> SafetyActionDecision:
    values: dict[str, object] = {
        "action": np.zeros(4, dtype=np.float32),
        "neutral_acknowledged": True,
    }
    values.update(overrides)
    return SafetyActionDecision(**values)


def test_contact_ownership_rejects_mixed_wall_and_hard_bottom_fields() -> None:
    with pytest.raises(ValueError, match="wall.*depth_exhausted"):
        SafetyContactOwnership(
            contact_kind=CONTACT_KIND_WALL,
            blocked_corridor_id=4,
            depth_exhausted_cell_id=5,
            wall_contact_session_count=1,
        ).validate()

    with pytest.raises(ValueError, match="hard_bottom.*blocked_corridor"):
        SafetyContactOwnership(
            contact_kind=CONTACT_KIND_HARD_BOTTOM,
            blocked_corridor_id=4,
            depth_exhausted_cell_id=5,
        ).validate()


def test_wall_contact_requires_a_typed_nonzero_session() -> None:
    with pytest.raises(ValueError, match="typed wall session"):
        SafetyContactOwnership(
            contact_kind=CONTACT_KIND_WALL,
            blocked_corridor_id=4,
            depth_exhausted_cell_id=-1,
            wall_contact_session_count=0,
        ).validate()


def test_wall_contact_without_active_corridor_still_has_valid_ownership() -> None:
    ownership = SafetyContactOwnership(
        contact_kind=CONTACT_KIND_WALL,
        blocked_corridor_id=-1,
        depth_exhausted_cell_id=-1,
        wall_contact_session_count=1,
    ).validate()

    assert ownership.blocked_corridor_id == -1


def test_none_contact_cannot_carry_coverage_mutation_ids() -> None:
    with pytest.raises(ValueError, match="none.*coverage"):
        SafetyContactOwnership(
            contact_kind=CONTACT_KIND_NONE,
            blocked_corridor_id=4,
            depth_exhausted_cell_id=-1,
        ).validate()


def test_hard_bottom_ack_only_marks_actual_physical_cell() -> None:
    corridors = [
        CoverageCorridorState(
            corridor_id=index,
            cell_id=index,
            entry_x_m=0.0,
            entry_z_m=0.0,
            exit_x_m=0.1,
            exit_z_m=0.0,
        )
        for index in range(6)
    ]
    state = CoverageRuntimeState(coverage_corridors=corridors)
    plan_service = SimpleNamespace(
        marked=[],
        blocked=[],
        mark_depth_exhausted=lambda cell_id: plan_service.marked.append(cell_id),
        block_corridor_numeric_id=lambda corridor_id: (
            plan_service.blocked.append(corridor_id)
        ),
    )
    service = SafetyDecisionCoverageEffectService(
        coverage_state=state,
        residual_plan_service=plan_service,
    )

    before_ack = service.apply(
        _decision(
            neutral_acknowledged=False,
            contact_kind=CONTACT_KIND_HARD_BOTTOM,
            depth_exhausted_cell_id=5,
        )
    )
    assert before_ack.applied is False
    assert state.coverage_depth_exhausted_physical_cell_ids == set()

    applied = service.apply(
        _decision(
            reason="hard_bottom_contact_neutral_acknowledged",
            contact_kind=CONTACT_KIND_HARD_BOTTOM,
            depth_exhausted_cell_id=5,
        )
    )

    assert applied.applied is True
    assert applied.depth_exhausted_physical_cell_id == 5
    assert state.coverage_depth_exhausted_physical_cell_ids == {5}
    assert plan_service.marked == [5]
    assert plan_service.blocked == []
    assert corridors[4].depleted is False
    assert corridors[4].last_reason != "wall_contact_blocked_corridor"
    assert all(not corridor.depleted for corridor in corridors)


def test_wall_ack_blocks_only_its_corridor_after_typed_session() -> None:
    corridors = [
        CoverageCorridorState(
            corridor_id=index,
            cell_id=index,
            entry_x_m=0.0,
            entry_z_m=0.0,
            exit_x_m=0.1,
            exit_z_m=0.0,
        )
        for index in range(6)
    ]
    state = CoverageRuntimeState(coverage_corridors=corridors)
    service = SafetyDecisionCoverageEffectService(coverage_state=state)

    applied = service.apply(
        _decision(
            reason="wall_contact_first_session_neutral_acknowledged",
            contact_kind=CONTACT_KIND_WALL,
            blocked_corridor_id=4,
            depth_exhausted_cell_id=-1,
            wall_contact_session_count=1,
        )
    )

    assert applied.blocked_corridor_id == 4
    assert state.coverage_depth_exhausted_physical_cell_ids == set()
    assert corridors[4].depleted is True
    assert corridors[4].last_reason == "wall_contact_blocked_corridor"


def test_decision_debug_fields_publish_append_only_contact_kind() -> None:
    fields = _decision(
        contact_kind=CONTACT_KIND_HARD_BOTTOM,
        depth_exhausted_cell_id=5,
    ).debug_fields()

    assert fields["box_safety_contact_kind"] == CONTACT_KIND_HARD_BOTTOM
    assert fields["box_safety_wall_contact_session_count"] == 0
