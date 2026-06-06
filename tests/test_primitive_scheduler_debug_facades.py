from __future__ import annotations

import numpy as np
import pytest

import testbed.policies.hybrid.primitive_planner as primitive_planner_module
from testbed.planner.bootstrap import BootstrapRuntimeStatusState
from testbed.planner.cell_entry import (
    AUDIT_REASON_TO_ID,
    CELL_ENTRY_TOKEN_DIM,
    CellEntryDebugSnapshot,
    CellEntryPlanner,
    CellEntryRuntimeState,
    CellGridSpec,
    PlannerDecisionAudit,
)
from testbed.planner.dig_lifecycle import DigLifecycleRuntimeStatusState
from testbed.planner.dig_start_alignment import (
    DIG_START_ALIGNMENT_DEBUG_STATE_FIELDS,
    DigStartAlignmentRuntimeState,
    debug_state_from_mapping,
)
from testbed.planner.dump_lifecycle import (
    DUMP_LIFECYCLE_RUNTIME_STATUS_FIELDS,
    DumpLifecycleRuntimeState,
    DumpLifecycleRuntimeStatusSnapshot,
    DumpLifecycleRuntimeStatusState,
    build_dump_lifecycle_runtime_status_state_from_mapping,
)
from testbed.planner.primitive_debug import (
    PrimitiveDebugStateSnapshotConfig,
    PrimitiveDebugStateSnapshotFacts,
    PrimitivePlannerDebugState,
    build_primitive_debug_state_snapshot,
    build_primitive_debug_state_snapshot_from_runtime,
)
from testbed.planner.return_handoff import ReturnToDigHandoffStatusState
from testbed.policies.base import Policy
from testbed.policies.hybrid.primitive_planner import (
    HYBRID_MODE_TRANSITION,
    HYBRID_MODE_WORK,
    PRE_DIG_ALIGN_SKILL_NAME,
    PRIMITIVE_SKILL_IDS,
    PrimitivePlannerACT5PPolicy,
    PrimitivePlannerACTPolicy,
)


def test_debug_state_snapshot_runtime_builder_matches_legacy_builder() -> None:
    config = PrimitiveDebugStateSnapshotConfig(
        skill_ids={"dig": 0, "return": 1},
        transition_skill_names=("return",),
        transition_hybrid_mode="transition",
        work_hybrid_mode="work",
        primitive_checkpoint_paths={"dig": "dig.ckpt", "return": "return.ckpt"},
    )
    facts = PrimitiveDebugStateSnapshotFacts(
        skill_name="return",
        skill_switch_reason="dig_to_return",
        first_dig_policy_active=False,
        transition_timeout=True,
        transition_completed=False,
        completed_transition_count=3,
        transition_timeout_count=4,
        dump_ready_hold_count=5,
        dump_done_hold_count=6,
        primitive_cycle_index=7,
        approach_ready_hold_count=8,
        dump_release_ready_hold_count=9,
    )

    actual = build_primitive_debug_state_snapshot_from_runtime(
        config=config,
        facts=facts,
    )
    expected = build_primitive_debug_state_snapshot(
        skill_name=facts.skill_name,
        skill_ids=config.skill_ids,
        transition_skill_names=config.transition_skill_names,
        transition_hybrid_mode=config.transition_hybrid_mode,
        work_hybrid_mode=config.work_hybrid_mode,
        skill_switch_reason=facts.skill_switch_reason,
        primitive_checkpoint_paths=config.primitive_checkpoint_paths,
        first_dig_policy_active=facts.first_dig_policy_active,
        transition_timeout=facts.transition_timeout,
        transition_completed=facts.transition_completed,
        completed_transition_count=facts.completed_transition_count,
        transition_timeout_count=facts.transition_timeout_count,
        dump_ready_hold_count=facts.dump_ready_hold_count,
        dump_done_hold_count=facts.dump_done_hold_count,
        primitive_cycle_index=facts.primitive_cycle_index,
        approach_ready_hold_count=facts.approach_ready_hold_count,
        dump_release_ready_hold_count=facts.dump_release_ready_hold_count,
    )

    assert actual == expected


def test_make_debug_state_delegates_snapshot_config_and_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy = _make_policy()
    policy._skill_name = "return"
    policy._switch_reason = "dig_to_return"
    policy._completed_transition_count = 3
    policy._transition_timeout_count = 4
    policy._cycle_index = 5
    policy._dump_ready_hold_count = 6
    policy._dump_done_hold_count = 7
    policy.primitive_checkpoint_paths = {
        "dig": "dig.ckpt",
        "return": "return.ckpt",
    }
    captured: dict[str, object] = {}
    sentinel = PrimitivePlannerDebugState(
        skill_name="sentinel",
        skill_id=99,
        skill_switch_reason="sentinel_reason",
        primitive_checkpoint_path="sentinel.ckpt",
        hybrid_mode="work",
        transition_timeout=True,
        transition_completed=False,
        completed_transition_count=0,
        transition_timeout_count=0,
        dump_ready_hold_count=0,
        dump_done_hold_count=0,
        primitive_cycle_index=0,
    )

    def build_snapshot(
        *,
        config: PrimitiveDebugStateSnapshotConfig,
        facts: PrimitiveDebugStateSnapshotFacts,
    ) -> PrimitivePlannerDebugState:
        captured["config"] = config
        captured["facts"] = facts
        return sentinel

    monkeypatch.setattr(
        primitive_planner_module,
        "build_primitive_debug_state_snapshot_from_runtime",
        build_snapshot,
    )

    debug_state = policy._make_debug_state(
        transition_timeout=True,
        transition_completed=False,
    )

    assert debug_state is sentinel
    assert captured["config"] == PrimitiveDebugStateSnapshotConfig(
        skill_ids=PRIMITIVE_SKILL_IDS,
        transition_skill_names=("return", PRE_DIG_ALIGN_SKILL_NAME),
        transition_hybrid_mode=HYBRID_MODE_TRANSITION,
        work_hybrid_mode=HYBRID_MODE_WORK,
        primitive_checkpoint_paths=policy.primitive_checkpoint_paths,
    )
    assert captured["facts"] == PrimitiveDebugStateSnapshotFacts(
        skill_name="return",
        skill_switch_reason="dig_to_return",
        first_dig_policy_active=False,
        transition_timeout=True,
        transition_completed=False,
        completed_transition_count=3,
        transition_timeout_count=4,
        dump_ready_hold_count=6,
        dump_done_hold_count=7,
        primitive_cycle_index=5,
    )


def test_debug_state_facts_use_cell_entry_debug_snapshot() -> None:
    policy = _make_policy()
    policy._cell_entry_seen_cell_id = 99

    def fake_debug_snapshot(**kwargs: object) -> CellEntryDebugSnapshot:
        return CellEntryDebugSnapshot(
            selected_cell_id=2,
            selected_long_index=1,
            selected_short_index=0,
            planned_entry_x_m=0.1,
            planned_entry_y_m=0.2,
            planned_entry_z_m=0.3,
            planner_ok=True,
            audit_reason_code=4,
            audit_reason="target_cell_miss",
            audit_risk_flags=8,
            inside_entry_envelope=True,
            distance_to_entry_envelope_m=0.45,
            seen_cell_id=5,
        )

    policy.cell_entry_runtime_service.debug_snapshot = fake_debug_snapshot  # type: ignore[method-assign]

    facts = policy._debug_state_facts()

    assert facts.cell_entry_selected_cell_id == 2
    assert facts.cell_entry_selected_long_index == 1
    assert facts.cell_entry_selected_short_index == 0
    assert facts.cell_entry_planned_entry_x_m == 0.1
    assert facts.cell_entry_planned_entry_y_m == 0.2
    assert facts.cell_entry_planned_entry_z_m == 0.3
    assert facts.cell_entry_planner_ok is True
    assert facts.cell_entry_audit_reason_code == 4
    assert facts.cell_entry_audit_reason == "target_cell_miss"
    assert facts.cell_entry_audit_risk_flags == 8
    assert facts.cell_entry_inside_entry_envelope is True
    assert facts.cell_entry_distance_to_entry_envelope_m == 0.45
    assert facts.cell_entry_seen_cell_id == 5


def test_reset_pre_dig_align_runtime_applies_service_state() -> None:
    policy = _make_policy()
    target = np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32)
    error = np.asarray([-0.1, -0.2, -0.3, -0.4], dtype=np.float32)

    def fake_initial_runtime_state(config: object) -> DigStartAlignmentRuntimeState:
        return DigStartAlignmentRuntimeState(
            step_count=1,
            hold_count=2,
            timeout_count=3,
            completed_count=4,
            replan_count=5,
            target_qpos=target,
            error=error,
            entry_error_m=0.25,
            start_envelope_ready=True,
            entry_close_handoff_ready=True,
            entry_intent_handoff_ready=True,
            timeout_handoff_reason="pre_dig_align_to_dig_timeout_close_enough",
            surface_depth_m=0.06,
            surface_guard_triggered=True,
            surface_guard_count=6,
        )

    policy.dig_start_alignment_service.initial_runtime_state = (  # type: ignore[method-assign]
        fake_initial_runtime_state
    )

    policy.reset()
    target[0] = 99.0
    error[0] = 99.0

    assert policy._pre_dig_align_step_count == 1
    assert policy._pre_dig_align_hold_count == 2
    assert policy._pre_dig_align_timeout_count == 3
    assert policy._pre_dig_align_completed_count == 4
    assert policy._pre_dig_align_replan_count == 5
    np.testing.assert_allclose(
        policy._pre_dig_align_target_qpos,
        np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
    )
    np.testing.assert_allclose(
        policy._pre_dig_align_error,
        np.asarray([-0.1, -0.2, -0.3, -0.4], dtype=np.float32),
    )
    assert policy._pre_dig_align_entry_error_m == 0.25
    assert policy._pre_dig_align_start_envelope_ready is True
    assert policy._pre_dig_align_entry_close_handoff_ready is True
    assert policy._pre_dig_align_entry_intent_handoff_ready is True
    assert (
        policy._pre_dig_align_timeout_handoff_reason
        == "pre_dig_align_to_dig_timeout_close_enough"
    )
    assert policy._pre_dig_align_surface_depth_m == 0.06
    assert policy._pre_dig_align_surface_guard_triggered is True
    assert policy._pre_dig_align_surface_guard_count == 6


def test_apply_pre_dig_align_runtime_state_copies_service_state() -> None:
    policy = _make_policy()
    target = np.asarray([1.1, 1.2, 1.3, 1.4], dtype=np.float32)
    error = np.asarray([-1.1, -1.2, -1.3, -1.4], dtype=np.float32)
    state = DigStartAlignmentRuntimeState(
        step_count=7,
        hold_count=8,
        timeout_count=9,
        completed_count=10,
        replan_count=11,
        target_qpos=target,
        error=error,
        entry_error_m=0.35,
        start_envelope_ready=True,
        entry_close_handoff_ready=False,
        entry_intent_handoff_ready=True,
        timeout_handoff_reason="pre_dig_align_to_dig_timeout_intent_aligned",
        surface_depth_m=0.07,
        surface_guard_triggered=True,
        surface_guard_count=12,
    )

    policy._apply_pre_dig_align_runtime_state(state)
    target[0] = 99.0
    error[0] = 99.0

    assert policy._pre_dig_align_step_count == 7
    assert policy._pre_dig_align_hold_count == 8
    assert policy._pre_dig_align_timeout_count == 9
    assert policy._pre_dig_align_completed_count == 10
    assert policy._pre_dig_align_replan_count == 11
    np.testing.assert_allclose(
        policy._pre_dig_align_target_qpos,
        np.asarray([1.1, 1.2, 1.3, 1.4], dtype=np.float32),
    )
    np.testing.assert_allclose(
        policy._pre_dig_align_error,
        np.asarray([-1.1, -1.2, -1.3, -1.4], dtype=np.float32),
    )
    assert policy._pre_dig_align_entry_error_m == 0.35
    assert policy._pre_dig_align_start_envelope_ready is True
    assert policy._pre_dig_align_entry_close_handoff_ready is False
    assert policy._pre_dig_align_entry_intent_handoff_ready is True
    assert (
        policy._pre_dig_align_timeout_handoff_reason
        == "pre_dig_align_to_dig_timeout_intent_aligned"
    )
    assert policy._pre_dig_align_surface_depth_m == 0.07
    assert policy._pre_dig_align_surface_guard_triggered is True
    assert policy._pre_dig_align_surface_guard_count == 12


def test_pre_dig_align_debug_snapshot_uses_runtime_builder() -> None:
    policy = _make_policy()
    target = np.asarray([1.1, 1.2, 1.3, 1.4], dtype=np.float64)
    error = np.asarray([-1.1, -1.2, -1.3, -1.4], dtype=np.float64)
    policy._pre_dig_align_surface_depth_m = "0.07"
    policy._pre_dig_align_surface_guard_triggered = 1
    policy._pre_dig_align_surface_guard_count = np.int64(12)
    policy._pre_dig_align_step_count = "7"
    policy._pre_dig_align_hold_count = np.int64(8)
    policy._pre_dig_align_timeout_count = "9"
    policy._pre_dig_align_completed_count = np.int64(10)
    policy._pre_dig_align_replan_count = "11"
    policy._pre_dig_align_target_qpos = target
    policy._pre_dig_align_error = error
    policy._pre_dig_align_entry_error_m = "0.35"
    policy._pre_dig_align_start_envelope_ready = 1
    policy._pre_dig_align_entry_close_handoff_ready = 0
    policy._pre_dig_align_entry_intent_handoff_ready = 1
    captured: dict[str, object] = {}
    sentinel = object()

    def fake_debug_snapshot(**kwargs: object) -> object:
        captured.update(kwargs)
        return sentinel

    policy.dig_start_alignment_service.debug_snapshot = fake_debug_snapshot  # type: ignore[method-assign]

    snapshot = policy._pre_dig_align_debug_snapshot()
    expected = debug_state_from_mapping(
        {
            field_name: getattr(policy, attr_name)
            for field_name, attr_name in DIG_START_ALIGNMENT_DEBUG_STATE_FIELDS
        }
    )
    actual = captured["state"]

    assert snapshot is sentinel
    assert actual.surface_depth_m == expected.surface_depth_m
    assert actual.surface_guard_triggered is expected.surface_guard_triggered
    assert actual.surface_guard_count == expected.surface_guard_count
    assert actual.step_count == expected.step_count
    assert actual.hold_count == expected.hold_count
    assert actual.timeout_count == expected.timeout_count
    assert actual.completed_count == expected.completed_count
    assert actual.replan_count == expected.replan_count
    assert actual.target_qpos is target
    assert actual.error is error
    assert actual.entry_error_m == expected.entry_error_m
    assert actual.start_envelope_ready is expected.start_envelope_ready
    assert actual.entry_close_handoff_ready is expected.entry_close_handoff_ready
    assert actual.entry_intent_handoff_ready is expected.entry_intent_handoff_ready


def test_reset_cell_entry_runtime_applies_service_state() -> None:
    policy = _make_policy()
    tokens = np.arange(CELL_ENTRY_TOKEN_DIM, dtype=np.float64)
    trace_event = {"cycle_id": 3, "audit_reason": "ok"}
    goal = CellEntryPlanner(grid=CellGridSpec()).plan(cycle_id=3)
    audit = PlannerDecisionAudit(
        cycle_id=3,
        planner_ok=True,
        risk_flags=0,
        reason_code=AUDIT_REASON_TO_ID["ok"],
        reason="ok",
        inside_entry_envelope=True,
        distance_to_entry_envelope_m=0.0,
        entry_delta_x_m=0.0,
        entry_delta_y_m=0.0,
        entry_delta_z_m=0.0,
        target_cell_match=True,
    )

    def initial_runtime_state() -> CellEntryRuntimeState:
        return CellEntryRuntimeState(
            goal=goal,
            goal_cycle_id=3,
            audit=audit,
            tokens=tokens,
            token_injected=True,
            seen_cell_id=2,
            trace_events=(trace_event,),
        )

    policy.cell_entry_runtime_service.initial_runtime_state = (  # type: ignore[method-assign]
        initial_runtime_state
    )

    policy.reset()
    tokens[0] = 99.0
    trace_event["cycle_id"] = 99

    assert policy._cell_entry_goal is goal
    assert policy._cell_entry_goal_cycle_id == 3
    assert policy._cell_entry_audit is audit
    np.testing.assert_allclose(
        policy._cell_entry_tokens,
        np.arange(CELL_ENTRY_TOKEN_DIM, dtype=np.float32),
    )
    assert policy._cell_entry_tokens.dtype == np.float32
    assert policy._cell_entry_token_injected is True
    assert policy._cell_entry_seen_cell_id == 2
    assert policy._cell_entry_trace == [{"cycle_id": 3, "audit_reason": "ok"}]


def test_reset_return_to_dig_handoff_runtime_applies_service_state() -> None:
    policy = _make_policy()
    checks = {"qpos_0": {"ok": False, "error": 0.12}}

    def initial_runtime_state() -> ReturnToDigHandoffStatusState:
        return ReturnToDigHandoffStatusState(
            entry_error_m=0.25,
            entry_close=False,
            next_dig_event_seen=True,
            start_envelope_ready=False,
            start_envelope_error=0.12,
            start_envelope_checks=checks,
        )

    policy.return_handoff_gate.initial_runtime_state = (  # type: ignore[method-assign]
        initial_runtime_state
    )

    policy.reset()
    checks["qpos_0"]["error"] = 99.0

    assert policy._return_to_dig_entry_error_m == 0.25
    assert policy._return_to_dig_entry_close_state is False
    assert policy._return_next_dig_event_seen is True
    assert policy._return_to_dig_start_envelope_ready_state is False
    assert policy._return_to_dig_start_envelope_error == 0.12
    assert policy._return_to_dig_start_envelope_checks == {
        "qpos_0": {"ok": False, "error": 0.12}
    }


def test_reset_dig_lifecycle_runtime_applies_service_state() -> None:
    policy = _make_policy()

    def initial_runtime_state() -> DigLifecycleRuntimeStatusState:
        return DigLifecycleRuntimeStatusState(
            step_count=4,
            best_mass_kg=18.5,
            mass_plateau_count=2,
            dig_to_carry_reason="mass_plateau",
            bad_replan_count=3,
            exit_guard_replan_count=1,
        )

    policy.dig_lifecycle_gate.initial_runtime_state = (  # type: ignore[method-assign]
        initial_runtime_state
    )

    policy.reset()

    assert policy._dig_step_count == 4
    assert policy._dig_best_mass_kg == 18.5
    assert policy._dig_mass_plateau_count == 2
    assert policy._dig_to_carry_reason == "mass_plateau"
    assert policy._dig_bad_replan_count == 3
    assert policy._dig_exit_guard_replan_count == 1


def test_reset_bootstrap_runtime_applies_service_state() -> None:
    policy = _make_policy()

    def initial_runtime_state() -> BootstrapRuntimeStatusState:
        return BootstrapRuntimeStatusState(
            step_count=4,
            hold_count=2,
            timeout_count=1,
        )

    policy.bootstrap_service.initial_runtime_state = (  # type: ignore[method-assign]
        initial_runtime_state
    )

    policy.reset()

    assert policy._scripted_bootstrap_step_count == 4
    assert policy._scripted_bootstrap_hold_count == 2
    assert policy._scripted_bootstrap_timeout_count == 1


def test_reset_dump_lifecycle_runtime_applies_service_state() -> None:
    policy = _make_policy()

    def initial_runtime_state() -> DumpLifecycleRuntimeState:
        return DumpLifecycleRuntimeState(
            ready_hold_count=4,
            done_hold_count=2,
            start_deposited_mass_kg=17.5,
        )

    policy.dump_lifecycle_gate.initial_runtime_state = (  # type: ignore[method-assign]
        initial_runtime_state
    )

    policy.reset()

    assert policy._dump_ready_hold_count == 4
    assert policy._dump_done_hold_count == 2
    assert policy._dump_start_deposited_mass_kg == 17.5


def test_make_debug_state_uses_dump_lifecycle_runtime_status_snapshot() -> None:
    policy = _make_policy()
    policy._dump_ready_hold_count = 4
    policy._dump_done_hold_count = 2

    expected_state = build_dump_lifecycle_runtime_status_state_from_mapping(
        {
            field_name: getattr(policy, attr_name)
            for (
                field_name,
                attr_name,
            ) in DUMP_LIFECYCLE_RUNTIME_STATUS_FIELDS
        }
    )

    def runtime_status_snapshot(
        state: DumpLifecycleRuntimeStatusState,
    ) -> DumpLifecycleRuntimeStatusSnapshot:
        assert state == expected_state
        return DumpLifecycleRuntimeStatusSnapshot(
            ready_hold_count=13,
            done_hold_count=17,
        )

    policy.dump_lifecycle_gate.runtime_status_snapshot = (  # type: ignore[method-assign]
        runtime_status_snapshot
    )

    debug_state = policy._make_debug_state(
        transition_timeout=False,
        transition_completed=True,
    )

    assert debug_state.dump_ready_hold_count == 13
    assert debug_state.dump_done_hold_count == 17


def test_5p_make_debug_state_uses_dump_lifecycle_runtime_status_snapshot() -> None:
    policy = _make_5p_policy()
    policy._approach_ready_hold_count = 3
    policy._dump_release_ready_hold_count = 4
    policy._dump_done_hold_count = 2

    expected_state = DumpLifecycleRuntimeStatusState(
        ready_hold_count=4,
        done_hold_count=2,
    )

    def runtime_status_snapshot(
        state: DumpLifecycleRuntimeStatusState,
    ) -> DumpLifecycleRuntimeStatusSnapshot:
        assert state == expected_state
        return DumpLifecycleRuntimeStatusSnapshot(
            ready_hold_count=13,
            done_hold_count=17,
        )

    policy.dump_lifecycle_gate.runtime_status_snapshot = (  # type: ignore[method-assign]
        runtime_status_snapshot
    )

    debug_state = policy._make_debug_state(
        transition_timeout=False,
        transition_completed=True,
    )

    assert debug_state.dump_ready_hold_count == 13
    assert debug_state.dump_done_hold_count == 17
    assert debug_state.approach_ready_hold_count == 3
    assert debug_state.dump_release_ready_hold_count == 13


def _make_policy() -> PrimitivePlannerACTPolicy:
    return PrimitivePlannerACTPolicy(
        dig_policy=_ConstantPolicy(0.0),
        carry_policy=_ConstantPolicy(1.0),
        dump_policy=_ConstantPolicy(2.0),
        return_policy=_ConstantPolicy(3.0),
        boundary_detector=_FakeBoundaryDetector(),
    )


def _make_5p_policy() -> PrimitivePlannerACT5PPolicy:
    return PrimitivePlannerACT5PPolicy(
        dig_policy=_ConstantPolicy(0.0),
        carry_policy=_ConstantPolicy(1.0),
        approach_dump_policy=_ConstantPolicy(2.0),
        dump_release_policy=_ConstantPolicy(3.0),
        return_policy=_ConstantPolicy(4.0),
        boundary_detector=_FakeBoundaryDetector(),
    )


class _ConstantPolicy(Policy):
    def __init__(self, value: float) -> None:
        self.value = float(value)

    def predict(self, obs: dict) -> np.ndarray:
        action = np.zeros(4, dtype=np.float32)
        action[0] = self.value
        return action


class _FakeBoundaryDetector:
    def __init__(self) -> None:
        self.config = type(
            "_FakeBoundaryConfig",
            (),
            {"boundary_profile": "legacy"},
        )()

    def reset(self) -> None:
        pass

    def update(self, obs: dict, action: np.ndarray | None = None) -> object:
        return None
