from __future__ import annotations

from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from testbed.contracts.primitive_tokens import (
    DIG_CUT_TOKEN_DIM,
    DIG_DEPTH_PROFILE_TOKEN_DIM,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_TARGET_TOKEN_DIM,
)
from testbed.planner.dig_cut_plan import DigCutRuntimeState
from testbed.planner.dig_depth_profile import DigDepthProfileRuntimeState
from testbed.planner.policy_observation import PolicyObservationAssembly
from testbed.planner.return_target_plan import ReturnTargetConditioningRuntimeState
from testbed.planner.dig_coverage import CoverageServiceState
from testbed.planner.runtime import (
    PlannerBlackboard,
    PlannerBackend,
    PlannerConditioningState,
    PlannerRuntimeEffect,
    PlannerTickContext,
    PlannerTickResult,
)


def test_planner_blackboard_defaults_are_minimal_runtime_state() -> None:
    blackboard = PlannerBlackboard()

    assert blackboard.current_skill == ""
    assert blackboard.switch_reason == ""
    assert blackboard.cycle_index == 0
    assert blackboard.completed_transition_count == 0
    assert blackboard.transition_timeout_count == 0
    assert blackboard.return_step_count == 0
    assert blackboard.return_next_dig_event_seen is False
    assert blackboard.dump_ready_hold_count == 0
    assert blackboard.dump_done_hold_count == 0


def test_planner_blackboard_is_immutable_and_hashable_snapshot() -> None:
    blackboard = PlannerBlackboard(
        current_skill="dig",
        switch_reason="reset",
        cycle_index=3,
        completed_transition_count=2,
        transition_timeout_count=1,
        return_step_count=6,
        return_next_dig_event_seen=True,
        dump_ready_hold_count=4,
        dump_done_hold_count=5,
    )

    assert hash(blackboard) == hash(
        PlannerBlackboard(
            current_skill="dig",
            switch_reason="reset",
            cycle_index=3,
            completed_transition_count=2,
            transition_timeout_count=1,
            return_step_count=6,
            return_next_dig_event_seen=True,
            dump_ready_hold_count=4,
            dump_done_hold_count=5,
        )
    )
    with pytest.raises(FrozenInstanceError):
        blackboard.current_skill = "return"  # type: ignore[misc]


def test_planner_blackboard_updates_return_new_lifecycle_snapshots() -> None:
    blackboard = PlannerBlackboard(
        current_skill="return",
        switch_reason="before",
        cycle_index=4,
        completed_transition_count=2,
        transition_timeout_count=1,
    )

    skill = blackboard.with_skill("dig", "return_to_dig_ready")
    reason = blackboard.with_switch_reason("cleared")
    timeout = blackboard.with_transition_timeout_increment()
    transition = blackboard.with_return_transition_counts(
        completed_increment=3,
        cycle_increment=5,
    )

    assert blackboard == PlannerBlackboard(
        current_skill="return",
        switch_reason="before",
        cycle_index=4,
        completed_transition_count=2,
        transition_timeout_count=1,
    )
    assert skill == PlannerBlackboard(
        current_skill="dig",
        switch_reason="return_to_dig_ready",
        cycle_index=4,
        completed_transition_count=2,
        transition_timeout_count=1,
    )
    assert reason.switch_reason == "cleared"
    assert reason.current_skill == "return"
    assert timeout.transition_timeout_count == 2
    assert timeout.cycle_index == 4
    assert transition.completed_transition_count == 5
    assert transition.cycle_index == 9


def test_planner_blackboard_updates_return_new_transition_runtime_snapshots() -> None:
    blackboard = PlannerBlackboard(
        current_skill="return",
        return_step_count=4,
        return_next_dig_event_seen=False,
        dump_ready_hold_count=2,
        dump_done_hold_count=3,
    )

    return_step = blackboard.with_return_step_increment()
    return_latch = blackboard.with_return_next_dig_event_seen(True)
    ready_hold = blackboard.with_dump_ready_hold_count(7)
    done_hold = blackboard.with_dump_done_hold_count(8)

    assert blackboard == PlannerBlackboard(
        current_skill="return",
        return_step_count=4,
        return_next_dig_event_seen=False,
        dump_ready_hold_count=2,
        dump_done_hold_count=3,
    )
    assert return_step.return_step_count == 5
    assert return_step.return_next_dig_event_seen is False
    assert return_latch.return_next_dig_event_seen is True
    assert return_latch.return_step_count == 4
    assert ready_hold.dump_ready_hold_count == 7
    assert ready_hold.dump_done_hold_count == 3
    assert done_hold.dump_done_hold_count == 8
    assert done_hold.dump_ready_hold_count == 2


def test_planner_conditioning_state_defaults_are_backend_neutral_tokens() -> None:
    state = PlannerConditioningState()

    assert state.cell_entry_token_injected is False
    assert state.dig_cut.token_injected is False
    assert state.dig_cut.planned_cycle_id == -1
    assert state.dig_cut.token_source == "none"
    assert state.dig_cut.fallback_reason == ""
    assert state.dig_cut.token_in_prior_p10_p90 is False
    np.testing.assert_allclose(
        state.dig_cut.tokens,
        np.zeros(DIG_CUT_TOKEN_DIM, dtype=np.float32),
    )
    assert state.dig_depth_profile.token_injected is False
    assert state.dig_depth_profile.token_source == "none"
    np.testing.assert_allclose(
        state.dig_depth_profile.tokens,
        np.zeros(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float32),
    )
    assert state.return_target.target_token_injected is False
    assert state.return_target.target_token_source == "none"
    assert state.return_target.relocate_token_injected is False
    assert state.return_target.start_envelope_token_injected is False
    assert state.return_target.start_envelope_token_source == "none"
    assert state.return_target.pending_dig_cut_cycle_id == -1
    assert state.return_target.pending_dig_cut_tokens is None
    np.testing.assert_allclose(
        state.return_target.target_tokens,
        np.zeros(RETURN_TARGET_TOKEN_DIM, dtype=np.float32),
    )
    np.testing.assert_allclose(
        state.return_target.start_envelope_tokens,
        np.zeros(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32),
    )


def test_planner_conditioning_state_updates_are_immutable_copies() -> None:
    dig_cut_tokens = np.arange(DIG_CUT_TOKEN_DIM, dtype=np.float32)
    depth_tokens = np.arange(DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float32)
    target_tokens = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float32)
    envelope_tokens = np.arange(RETURN_START_ENVELOPE_TOKEN_DIM, dtype=np.float32)
    state = PlannerConditioningState()

    updated = (
        state.with_dig_cut_runtime_state(
            DigCutRuntimeState(
                tokens=dig_cut_tokens,
                token_injected=True,
                planned_cycle_id=3,
                token_source="dig_source",
                fallback_reason="dig_fallback",
                token_in_prior_p10_p90=True,
            )
        )
        .with_dig_depth_profile_runtime_state(
            DigDepthProfileRuntimeState(
                tokens=depth_tokens,
                token_injected=True,
                token_source="depth_source",
                fallback_reason="depth_fallback",
            )
        )
        .with_return_target_conditioning_state(
            ReturnTargetConditioningRuntimeState(
                target_tokens=target_tokens,
                target_token_injected=True,
                target_token_source="target_source",
                target_fallback_reason="target_fallback",
                relocate_tokens=target_tokens + 10.0,
                relocate_token_injected=True,
                start_envelope_tokens=envelope_tokens,
                start_envelope_token_injected=True,
                start_envelope_token_source="envelope_source",
                start_envelope_use_prior_spatial_bounds=False,
                start_envelope_use_prior_qpos_bounds=True,
                planned_cycle_id=5,
                pending_dig_cut_cycle_id=6,
                pending_dig_cut_corridor_id=7,
                pending_dig_cut_raw_fields={"operator_entry_x_m": 1.5},
                pending_dig_cut_tokens=dig_cut_tokens + 20.0,
                pending_dig_depth_profile_tokens=depth_tokens + 30.0,
                pending_dig_state_exemplar_ids=("cell7_deep",),
                pending_dig_state_exemplar_distance=0.25,
            )
        )
        .with_policy_observation_assembly(
            PolicyObservationAssembly(
                obs={},
                cell_entry_token_injected=True,
                dig_cut_token_injected=False,
                dig_depth_profile_token_injected=True,
                return_target_token_injected=False,
                return_relocate_token_injected=True,
                return_start_envelope_token_injected=False,
            )
        )
    )

    dig_cut_tokens[0] = 99.0
    depth_tokens[0] = 99.0
    target_tokens[0] = 99.0
    envelope_tokens[0] = 99.0

    assert state.cell_entry_token_injected is False
    assert updated.cell_entry_token_injected is True
    assert updated.dig_cut.token_injected is False
    assert updated.dig_cut.planned_cycle_id == 3
    assert updated.dig_cut.token_source == "dig_source"
    assert updated.dig_cut.token_in_prior_p10_p90 is True
    np.testing.assert_allclose(updated.dig_cut.tokens[0], 0.0)
    assert updated.dig_depth_profile.token_injected is True
    assert updated.dig_depth_profile.token_source == "depth_source"
    np.testing.assert_allclose(updated.dig_depth_profile.tokens[0], 0.0)
    assert updated.return_target.target_token_injected is False
    assert updated.return_target.relocate_token_injected is True
    assert updated.return_target.start_envelope_token_injected is False
    assert updated.return_target.target_token_source == "target_source"
    assert updated.return_target.pending_dig_cut_raw_fields == {
        "operator_entry_x_m": 1.5
    }
    np.testing.assert_allclose(updated.return_target.target_tokens[0], 0.0)
    np.testing.assert_allclose(updated.return_target.start_envelope_tokens[0], 0.0)
    assert updated.return_target.pending_dig_state_exemplar_ids == ("cell7_deep",)


def test_tick_context_references_coverage_state_without_copying() -> None:
    coverage_state = CoverageServiceState(active_corridor_id=7)
    blackboard = PlannerBlackboard(current_skill="dig")

    context = PlannerTickContext(
        obs={"step": 3},
        coverage_state=coverage_state,
        blackboard=blackboard,
    )

    assert context.coverage_state is coverage_state
    assert dict(context.obs) == {"step": 3}
    assert context.blackboard is blackboard
    assert context.blackboard.current_skill == "dig"
    with pytest.raises(TypeError):
        context.obs["step"] = 4  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        context.coverage_state = None  # type: ignore[misc]

    coverage_state.active_corridor_id = 9
    assert context.coverage_state.active_corridor_id == 9


def test_tick_context_rejects_untyped_blackboard_mapping() -> None:
    with pytest.raises(TypeError, match="PlannerBlackboard"):
        PlannerTickContext(blackboard={"skill_name": "dig"})  # type: ignore[arg-type]


def test_runtime_effect_payload_is_an_immutable_hashable_copy() -> None:
    payload = {"skill_name": "dig", "reset": True}

    effect = PlannerRuntimeEffect("set_skill", payload)
    payload["skill_name"] = "return"

    assert effect.effect_type == "set_skill"
    assert dict(effect.payload) == {"skill_name": "dig", "reset": True}
    with pytest.raises(TypeError):
        effect.payload["skill_name"] = "carry"  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        effect.effect_type = "reset_policy"  # type: ignore[misc]
    assert hash(effect) == hash(
        PlannerRuntimeEffect("set_skill", {"skill_name": "dig", "reset": True})
    )


def test_tick_result_preserves_effect_order_and_hashable_scalar_contract() -> None:
    first = PlannerRuntimeEffect("set_skill", {"skill_name": "dig"})
    second = PlannerRuntimeEffect("reset_policy", {"policy": "dig"})
    third = PlannerRuntimeEffect("record_trace", {"reason": "dig_complete"})

    result = PlannerTickResult(
        node_path=["transition", "dig"],
        status="success",
        reason="dig_complete",
        effects=[first, second, third],
        diagnostics={"source": "unit-test"},
    )

    assert result.node_path == ("transition", "dig")
    assert result.effects == (first, second, third)
    assert [effect.effect_type for effect in result.effects] == [
        "set_skill",
        "reset_policy",
        "record_trace",
    ]
    assert dict(result.diagnostics) == {"source": "unit-test"}
    with pytest.raises(TypeError):
        result.diagnostics["source"] = "mutated"  # type: ignore[index]
    assert hash(result) == hash(
        PlannerTickResult(
            node_path=("transition", "dig"),
            status="success",
            reason="dig_complete",
            effects=(first, second, third),
            diagnostics={"source": "unit-test"},
        )
    )


def test_planner_backend_protocol_accepts_tick_implementation() -> None:
    class EchoBackend:
        name = "echo"

        def tick(self, context: PlannerTickContext) -> PlannerTickResult:
            return PlannerTickResult(
                node_path=("echo", str(context.obs["step"])),
                status="success",
                reason=self.name,
            )

    backend = EchoBackend()

    assert isinstance(backend, PlannerBackend)
    result = backend.tick(PlannerTickContext(obs={"step": 5}))

    assert result.node_path == ("echo", "5")
    assert result.status == "success"
    assert result.reason == "echo"
