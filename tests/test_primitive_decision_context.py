from __future__ import annotations

from testbed.planner.primitive_decision_context import PrimitiveDecisionContext
from testbed.planner.primitive_execution import PrimitiveTickPreparation


def test_decision_context_from_tick_preserves_identity_and_exposes_fields() -> None:
    obs = {"qpos": [1.0]}
    boundary_event = object()
    preparation = PrimitiveTickPreparation(
        boundary_event=boundary_event,
        skill_name_before_decision="dig",
        dig_progress_updated=True,
    )

    context = PrimitiveDecisionContext.from_tick(
        obs=obs,
        boundary_event=boundary_event,
        preparation=preparation,
    )

    assert context.obs is obs
    assert context.boundary_event is boundary_event
    assert context.preparation is preparation
    assert context.skill_name_before_decision == "dig"
    assert context.dig_progress_updated is True
