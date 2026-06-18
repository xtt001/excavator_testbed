from __future__ import annotations

from typing import Any

from testbed.planner.primitive_backend import (
    LegacyFSMBackendAdapter,
    LegacyFSMBootstrapBranch,
    LegacyFSMBootstrapConfig,
)
from testbed.planner.primitive_decision import LEGACY_FSM_DECISION_SOURCE
from testbed.planner.primitive_execution import PrimitiveTickPreparation


def test_legacy_fsm_backend_adapter_wraps_existing_switch_callback() -> None:
    obs: dict[str, Any] = {"qpos": [1.0]}
    boundary_event = object()
    state = {"skill": "dig", "reason": ""}
    calls: list[tuple[dict[str, Any], object, str]] = []

    def maybe_switch_skill(*, obs: dict[str, Any], boundary_event: object) -> None:
        calls.append((obs, boundary_event, state["skill"]))
        state["skill"] = "carry"
        state["reason"] = "dig_to_carry_boundary_confirmed"

    backend = LegacyFSMBackendAdapter(
        maybe_switch_skill=maybe_switch_skill,
        current_skill_name=lambda: state["skill"],
        current_switch_reason=lambda: state["reason"],
    )

    result = backend.decide_tick(
        obs=obs,
        boundary_event=boundary_event,
        preparation=PrimitiveTickPreparation(
            boundary_event=boundary_event,
            skill_name_before_decision="dig",
            dig_progress_updated=True,
        ),
    )

    assert calls == [(obs, boundary_event, "dig")]
    assert result.decision_source == LEGACY_FSM_DECISION_SOURCE
    assert result.status == "skill_switch"
    assert result.skill_before == "dig"
    assert result.skill_after == "carry"
    assert result.switch_reason == "dig_to_carry_boundary_confirmed"


def test_legacy_fsm_bootstrap_branch_selects_pre_dig_align_when_enabled() -> None:
    obs: dict[str, Any] = {"qpos": [1.0]}
    boundary_event = object()
    state = {"skill": "bootstrap"}
    switches: list[tuple[str, str]] = []
    branch = LegacyFSMBootstrapBranch(
        config=LegacyFSMBootstrapConfig(
            bootstrap_skill_name="bootstrap",
            pre_dig_align_skill_name="pre_dig_align",
        ),
        current_skill_name=lambda: state["skill"],
        should_end_bootstrap=lambda *, obs, boundary_event: True,
        bootstrap_end_mode=lambda: "first_qualified_dig_start",
        should_pre_dig_align_before_dig=lambda: True,
        set_skill=lambda skill, reason: switches.append((skill, reason)),
    )

    handled = branch.maybe_handle(obs=obs, boundary_event=boundary_event)

    assert handled is True
    assert switches == [("pre_dig_align", "bootstrap_to_pre_dig_align")]


def test_legacy_fsm_bootstrap_branch_ignores_non_bootstrap_skill() -> None:
    branch = LegacyFSMBootstrapBranch(
        config=LegacyFSMBootstrapConfig(
            bootstrap_skill_name="bootstrap",
            pre_dig_align_skill_name="pre_dig_align",
        ),
        current_skill_name=lambda: "dig",
        should_end_bootstrap=lambda *, obs, boundary_event: True,
        bootstrap_end_mode=lambda: "disabled",
        should_pre_dig_align_before_dig=lambda: False,
        set_skill=lambda skill, reason: None,
    )

    assert branch.maybe_handle(obs={}, boundary_event=None) is False
