from __future__ import annotations

from copy import deepcopy
from typing import Any

import numpy as np
import pytest

from testbed.data.schema import (
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
    ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_DUMP_CLEARANCE_OK_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
    ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
)
from testbed.planner.dig_start_alignment_outcome import PreDigAlignOutcome
from testbed.planner.dig_lifecycle import (
    DigTransitionRuntimeOutcome,
    DigTransitionRuntimeProjection,
)
from testbed.planner.primitive_action_tree import (
    PrimitiveActionTreeRunner,
    patch_primitive_action_tree_predict,
)
from testbed.planner.planner_backend_config import (
    ACTION_TREE_SHADOW_BACKEND,
    LEGACY_FSM_BACKEND,
    NOT_APPLICABLE_BACKEND,
    apply_planner_backend,
    planner_backend_from_metadata,
    planner_backend_from_policy_config,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def test_action_tree_predict_matches_legacy_golden_trace() -> None:
    legacy = _make_policy(
        boundary_events=_golden_boundary_events(),
        boundary_profile="v2_4_5_spatial_mass",
    )
    tree_policy = _make_policy(
        boundary_events=_golden_boundary_events(),
        boundary_profile="v2_4_5_spatial_mass",
    )
    runner = PrimitiveActionTreeRunner()
    observations = [
        _obs(mass=0.0, dig_distance=0.0),
        _obs(mass=1000.0, dig_distance=0.0),
        _obs(mass=0.0, dig_distance=0.0, dump_ready=False),
        _obs(mass=500.0, dig_distance=0.0, deposited=0.0),
        _obs(mass=0.0, dig_distance=0.0),
    ]

    for obs in observations:
        skill_before = tree_policy.debug_state()["skill_name"]

        legacy_action = legacy.predict(deepcopy(obs))
        tree_action = runner.predict(tree_policy, deepcopy(obs))

        np.testing.assert_allclose(tree_action, legacy_action, atol=1e-6)
        _assert_observable_surfaces_match(legacy, tree_policy)
        assert runner.last_trace is not None
        assert runner.last_trace.active_skill_before == skill_before
        assert runner.last_trace.active_skill_after == tree_policy.debug_state()[
            "skill_name"
        ]
        assert runner.last_trace.switch_reason == tree_policy.debug_state()[
            "skill_switch_reason"
        ]
        assert runner.last_trace.node_path[:2] == ("transition", skill_before)


def test_action_tree_tick_transition_matches_legacy_bootstrap() -> None:
    legacy = _make_policy(
        boundary_events=[],
        boundary_profile="legacy",
        bootstrap_policy=_ConstantPolicy(4),
        bootstrap_end_mode="first_qualified_dig_start",
    )
    tree_policy = _make_policy(
        boundary_events=[],
        boundary_profile="legacy",
        bootstrap_policy=_ConstantPolicy(4),
        bootstrap_end_mode="first_qualified_dig_start",
    )
    event = _FakeBoundaryEvent(qualified_dig_start=True)
    obs = _obs(mass=0.0, dig_distance=0.0)
    trace = _run_transition_pair(legacy, tree_policy, obs, event)

    assert trace.active_skill_before == "bootstrap"
    assert trace.active_skill_after == "dig"
    assert trace.switch_reason == "bootstrap_to_dig"
    assert "end_transition" in trace.node_path


def test_action_tree_tick_transition_matches_legacy_bootstrap_to_pre_dig_align() -> None:
    legacy = _make_policy(
        boundary_events=[],
        boundary_profile="legacy",
        bootstrap_policy=_ConstantPolicy(4),
        bootstrap_end_mode="first_qualified_dig_start",
        pre_dig_align={
            "enabled": True,
            "first_dig_only": True,
            "controlled_dims": [1, 1, 1, 1],
        },
    )
    tree_policy = _make_policy(
        boundary_events=[],
        boundary_profile="legacy",
        bootstrap_policy=_ConstantPolicy(4),
        bootstrap_end_mode="first_qualified_dig_start",
        pre_dig_align={
            "enabled": True,
            "first_dig_only": True,
            "controlled_dims": [1, 1, 1, 1],
        },
    )
    event = _FakeBoundaryEvent(qualified_dig_start=True)
    trace = _run_transition_pair(
        legacy,
        tree_policy,
        _obs(mass=0.0, dig_distance=0.0),
        event,
    )

    assert trace.active_skill_before == "bootstrap"
    assert trace.active_skill_after == "pre_dig_align"
    assert trace.switch_reason == "bootstrap_to_pre_dig_align"
    assert trace.node_path[-1] == "pre_dig_align"


def test_action_tree_tick_transition_matches_legacy_pre_dig_align_ready() -> None:
    legacy = _make_policy(
        boundary_events=[],
        boundary_profile="legacy",
        pre_dig_align={
            "enabled": True,
            "hold_steps": 1,
            "controlled_dims": [1, 1, 1, 1],
        },
    )
    tree_policy = _make_policy(
        boundary_events=[],
        boundary_profile="legacy",
        pre_dig_align={
            "enabled": True,
            "hold_steps": 1,
            "controlled_dims": [1, 1, 1, 1],
        },
    )
    obs = _obs(mass=0.0, dig_distance=0.0)
    target = legacy._pre_dig_align_target(obs)
    obs["qpos"] = target.astype(np.float32)
    obs["qvel"] = np.zeros(4, dtype=np.float32)

    trace = _run_transition_pair(legacy, tree_policy, obs, None)

    assert trace.active_skill_before == "pre_dig_align"
    assert trace.active_skill_after == "dig"
    assert trace.switch_reason.startswith("pre_dig_align_to_dig_")
    assert "pre_dig_align" in trace.node_path


def test_action_tree_tick_transition_matches_legacy_pre_dig_align_surface_guard_replan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy = _make_policy(
        boundary_events=[],
        boundary_profile="legacy",
        pre_dig_align={
            "enabled": True,
            "controlled_dims": [1, 1, 1, 1],
        },
    )
    tree_policy = _make_policy(
        boundary_events=[],
        boundary_profile="legacy",
        pre_dig_align={
            "enabled": True,
            "controlled_dims": [1, 1, 1, 1],
        },
    )
    for policy in (legacy, tree_policy):
        monkeypatch.setattr(
            policy,
            "_pre_dig_align_outcome",
            lambda _obs: PreDigAlignOutcome(
                action="surface_guard_replan",
                switch_reason="pre_dig_align_to_dig_surface_guard_replan",
                reject_reason="pre_align_surface_penetration_entry_gap",
            ),
        )

    trace = _run_transition_pair(
        legacy,
        tree_policy,
        _obs(mass=0.0, dig_distance=0.0),
        None,
    )

    assert trace.active_skill_before == "pre_dig_align"
    assert trace.active_skill_after == "dig"
    assert trace.switch_reason == "pre_dig_align_to_dig_surface_guard_replan"
    assert trace.node_path[-1] == "surface_guard_replan"


def test_action_tree_tick_transition_matches_legacy_pre_dig_align_timeout_replan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy = _make_policy(
        boundary_events=[],
        boundary_profile="legacy",
        pre_dig_align={
            "enabled": True,
            "controlled_dims": [1, 1, 1, 1],
        },
    )
    tree_policy = _make_policy(
        boundary_events=[],
        boundary_profile="legacy",
        pre_dig_align={
            "enabled": True,
            "controlled_dims": [1, 1, 1, 1],
        },
    )
    for policy in (legacy, tree_policy):
        monkeypatch.setattr(
            policy,
            "_pre_dig_align_outcome",
            lambda _obs: PreDigAlignOutcome(
                action="timeout_replan",
                switch_reason="pre_dig_align_retry_entry_gap",
                reject_reason="align_entry_gap_timeout",
            ),
        )
        monkeypatch.setattr(policy, "_try_replan_pre_dig_align_handoff", lambda _obs: False)

    trace = _run_transition_pair(
        legacy,
        tree_policy,
        _obs(mass=0.0, dig_distance=0.0),
        None,
    )

    assert trace.active_skill_before == "pre_dig_align"
    assert trace.active_skill_after == "pre_dig_align"
    assert trace.switch_reason == "pre_dig_align_retry_entry_gap"
    assert trace.node_path[-1] == "timeout_replan"


def test_action_tree_tick_transition_matches_legacy_dig_carry_dump_return_chain() -> None:
    runner = PrimitiveActionTreeRunner()
    legacy = _make_policy(boundary_events=[], boundary_profile="v2_4_5_spatial_mass")
    tree_policy = _make_policy(boundary_events=[], boundary_profile="v2_4_5_spatial_mass")
    steps = [
        (
            "dig",
            _obs(mass=1000.0, dig_distance=0.0),
            _FakeBoundaryEvent(dig_complete=True),
            "carry",
            "dig_to_carry_dig_complete_boundary",
        ),
        (
            "carry",
            _obs(mass=1000.0, dig_distance=0.0, dump_ready=False),
            _FakeBoundaryEvent(dump_committed_start=True),
            "dump",
            "carry_to_dump_dump_committed_boundary",
        ),
        (
            "dump",
            _obs(mass=500.0, dig_distance=0.0),
            _FakeBoundaryEvent(dump_complete=True),
            "return",
            "dump_to_return_dump_complete_boundary",
        ),
        (
            "return",
            _obs(mass=0.0, dig_distance=0.0),
            _FakeBoundaryEvent(next_dig_entry_ready=True),
            "dig",
            "return_to_dig_next_dig_entry_ready",
        ),
    ]

    for initial_skill, obs, event, expected_skill, expected_reason in steps:
        legacy._skill_name = initial_skill
        tree_policy._skill_name = initial_skill
        legacy._switch_reason = ""
        tree_policy._switch_reason = ""

        legacy._maybe_switch_skill(obs=deepcopy(obs), boundary_event=event)
        trace = runner.tick_transition(tree_policy, deepcopy(obs), event)

        assert tree_policy._skill_name == legacy._skill_name == expected_skill
        assert tree_policy._switch_reason == legacy._switch_reason == expected_reason
        assert trace.active_skill_before == initial_skill
        assert trace.active_skill_after == expected_skill
        assert trace.switch_reason == expected_reason
        assert trace.node_path[:2] == ("transition", initial_skill)


def test_action_tree_tick_transition_matches_legacy_dig_bad_replan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy = _make_policy(boundary_events=[], boundary_profile="legacy")
    tree_policy = _make_policy(boundary_events=[], boundary_profile="legacy")
    for policy in (legacy, tree_policy):
        policy._skill_name = "dig"
    monkeypatch.setattr(
        legacy,
        "_dig_transition_runtime",
        lambda **_kwargs: DigTransitionRuntimeProjection(
            outcome=DigTransitionRuntimeOutcome(
                action="failed_dig",
                counter="bad_replan",
                failed_dig_reason="bad_dig_low_payload",
                coverage_reject_reason="bad_dig_low_payload",
            ),
            bad_replan_count_increment=1,
        ),
    )
    monkeypatch.setattr(tree_policy, "_dig_exit_guard_ready", lambda _obs: False)
    monkeypatch.setattr(tree_policy, "_dig_bad_replan_ready", lambda _obs: True)

    trace = _run_transition_pair(
        legacy,
        tree_policy,
        _obs(mass=0.0, dig_distance=0.0),
        None,
    )

    assert trace.active_skill_before == "dig"
    assert trace.active_skill_after == "dig"
    assert trace.switch_reason == "dig_retry_bad_dig_low_payload"
    assert trace.node_path[-1] == "failed_dig"


def test_action_tree_tick_transition_matches_legacy_dig_complete_low_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy = _make_policy(boundary_events=[], boundary_profile="v2_4_5_spatial_mass")
    tree_policy = _make_policy(boundary_events=[], boundary_profile="v2_4_5_spatial_mass")
    for policy in (legacy, tree_policy):
        policy._skill_name = "dig"
    monkeypatch.setattr(
        legacy,
        "_dig_transition_runtime",
        lambda **_kwargs: DigTransitionRuntimeProjection(
            outcome=DigTransitionRuntimeOutcome(
                action="failed_dig",
                counter="bad_replan",
                failed_dig_reason="complete_low_payload",
                coverage_reject_reason="dig_complete_low_current_payload",
            ),
            bad_replan_count_increment=1,
        ),
    )
    monkeypatch.setattr(tree_policy, "_dig_exit_guard_ready", lambda _obs: False)
    monkeypatch.setattr(tree_policy, "_dig_bad_replan_ready", lambda _obs: False)
    monkeypatch.setattr(
        tree_policy,
        "_dig_complete_boundary_low_payload",
        lambda _obs, _event: True,
    )

    trace = _run_transition_pair(
        legacy,
        tree_policy,
        _obs(mass=0.0, dig_distance=0.0),
        _FakeBoundaryEvent(dig_complete=True),
    )

    assert trace.active_skill_before == "dig"
    assert trace.active_skill_after == legacy._skill_name
    assert trace.switch_reason == legacy._switch_reason
    assert trace.node_path[-1] == "failed_dig"


def test_action_tree_tick_transition_matches_legacy_carry_to_return() -> None:
    legacy = _make_policy(boundary_events=[], boundary_profile="v2_4_5_spatial_mass")
    tree_policy = _make_policy(boundary_events=[], boundary_profile="v2_4_5_spatial_mass")
    legacy._skill_name = "carry"
    tree_policy._skill_name = "carry"

    trace = _run_transition_pair(
        legacy,
        tree_policy,
        _obs(mass=1000.0, dig_distance=0.0),
        _FakeBoundaryEvent(dump_complete=True),
    )

    assert trace.active_skill_before == "carry"
    assert trace.active_skill_after == "return"
    assert trace.switch_reason == "carry_to_return_dump_complete_boundary"
    assert trace.node_path[-1] == "return"


def test_action_tree_tick_transition_matches_legacy_return_direct_handoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy = _make_policy(boundary_events=[], boundary_profile="legacy")
    tree_policy = _make_policy(boundary_events=[], boundary_profile="legacy")
    for policy in (legacy, tree_policy):
        policy._skill_name = "return"
        monkeypatch.setattr(policy, "_return_to_dig_handoff_ready", lambda _obs: True)
        monkeypatch.setattr(
            policy,
            "_return_to_dig_direct_handoff_ready",
            lambda _obs, *, handoff_ready=None: bool(handoff_ready),
        )
        monkeypatch.setattr(
            policy,
            "_return_to_dig_shallow_guard_ready",
            lambda *, obs, boundary_event: False,
        )

    trace = _run_transition_pair(
        legacy,
        tree_policy,
        _obs(mass=0.0, dig_distance=0.0),
        None,
    )

    assert trace.active_skill_before == "return"
    assert trace.active_skill_after == "dig"
    assert trace.switch_reason == "return_to_dig_start_envelope_ready"
    assert trace.node_path[-2:] == ("direct_handoff", "completion")


def test_action_tree_tick_transition_matches_legacy_return_shallow_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    legacy = _make_policy(boundary_events=[], boundary_profile="legacy")
    tree_policy = _make_policy(boundary_events=[], boundary_profile="legacy")
    for policy in (legacy, tree_policy):
        policy._skill_name = "return"
        monkeypatch.setattr(policy, "_return_to_dig_handoff_ready", lambda _obs: True)
        monkeypatch.setattr(
            policy,
            "_return_to_dig_direct_handoff_ready",
            lambda _obs, *, handoff_ready=None: False,
        )
        monkeypatch.setattr(
            policy,
            "_return_to_dig_shallow_guard_ready",
            lambda *, obs, boundary_event: True,
        )

    trace = _run_transition_pair(
        legacy,
        tree_policy,
        _obs(mass=0.0, dig_distance=0.0),
        None,
    )

    assert trace.active_skill_before == "return"
    assert trace.active_skill_after == "dig"
    assert trace.switch_reason == "return_to_dig_shallow_entry_guard"
    assert trace.node_path[-2:] == ("shallow_guard", "completion")


def test_action_tree_predict_trace_records_dispatch_resets_and_counter_deltas() -> None:
    tree_policy = _make_policy(
        boundary_events=[_FakeBoundaryEvent(dig_complete=True)],
        boundary_profile="v2_4_5_spatial_mass",
    )
    tree_policy._prev_action = np.zeros(4, dtype=np.float32)
    runner = PrimitiveActionTreeRunner()

    action = runner.predict(tree_policy, _obs(mass=1000.0, dig_distance=0.0))

    np.testing.assert_allclose(action, np.asarray([1.0, 0.0, 0.0, 0.0], dtype=np.float32))
    assert runner.last_trace is not None
    assert runner.last_trace.active_skill_before == "dig"
    assert runner.last_trace.active_skill_after == "carry"
    assert runner.last_trace.node_status == "switched"
    assert runner.last_trace.service_outcome == "carry"
    assert runner.last_trace.policy_dispatch == "carry"
    assert runner.last_trace.reset_count_delta == 1
    assert runner.last_trace.return_step_count_delta == 0
    assert runner.last_trace.transition_timeout_count_delta == 0
    assert runner.last_trace.guard_facts["dig_to_carry_ready"] is True


def test_action_tree_predict_matches_legacy_return_timeout_counter_trace() -> None:
    legacy = _make_policy(
        boundary_events=[],
        boundary_profile="legacy",
        return_max_steps=1,
    )
    tree_policy = _make_policy(
        boundary_events=[],
        boundary_profile="legacy",
        return_max_steps=1,
    )
    for policy in (legacy, tree_policy):
        policy._skill_name = "return"
        policy._prev_action = np.zeros(4, dtype=np.float32)

    legacy_action = legacy.predict(_obs(mass=0.0, dig_distance=0.0))
    runner = PrimitiveActionTreeRunner()
    tree_action = runner.predict(tree_policy, _obs(mass=0.0, dig_distance=0.0))

    np.testing.assert_allclose(tree_action, legacy_action, atol=1e-6)
    _assert_observable_surfaces_match(legacy, tree_policy)
    assert runner.last_trace is not None
    assert runner.last_trace.active_skill_before == "return"
    assert runner.last_trace.active_skill_after == "return"
    assert runner.last_trace.transition_timeout is True
    assert runner.last_trace.policy_dispatch == "return"
    assert runner.last_trace.return_step_count_delta == 1
    assert runner.last_trace.transition_timeout_count_delta == 1
    assert runner.last_trace.reset_count_delta == 0


def test_action_tree_shadow_predict_patch_is_process_scoped() -> None:
    original_predict = PrimitivePlannerACTPolicy.predict
    tree_policy = _make_policy(
        boundary_events=_golden_boundary_events(),
        boundary_profile="v2_4_5_spatial_mass",
    )

    with patch_primitive_action_tree_predict() as runner_registry:
        assert PrimitivePlannerACTPolicy.predict is not original_predict
        action = tree_policy.predict(_obs(mass=0.0, dig_distance=0.0))
        np.testing.assert_allclose(
            action,
            np.asarray([0.0, 0.0, 0.0, 0.0], dtype=np.float32),
        )
        assert tree_policy in runner_registry
        assert runner_registry[tree_policy].last_trace is not None

    assert PrimitivePlannerACTPolicy.predict is original_predict


def test_action_tree_shadow_eval_cli_patches_predict_for_eval_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from testbed.cli import eval as eval_cli
    from testbed.cli import eval_primitive_action_tree_shadow as shadow_cli

    original_predict = PrimitivePlannerACTPolicy.predict
    observed: dict[str, bool] = {}

    def fake_eval_main() -> None:
        observed["patched_during_eval"] = (
            PrimitivePlannerACTPolicy.predict is not original_predict
        )

    monkeypatch.setattr(eval_cli, "main", fake_eval_main)

    shadow_cli.main()

    assert observed == {"patched_during_eval": True}
    assert PrimitivePlannerACTPolicy.predict is original_predict


def test_planner_backend_config_defaults_to_legacy() -> None:
    policy = _make_policy(boundary_events=[], boundary_profile="legacy")

    selected = planner_backend_from_policy_config({})
    applied = apply_planner_backend(
        policy=policy,
        policy_class="PRIMITIVE_PLANNER_ACT",
        backend=selected,
    )

    assert selected == LEGACY_FSM_BACKEND
    assert applied == LEGACY_FSM_BACKEND
    assert not hasattr(policy, "_primitive_action_tree_runner")


def test_planner_backend_config_attaches_action_tree_per_instance() -> None:
    original_predict = PrimitivePlannerACTPolicy.predict
    tree_policy = _make_policy(
        boundary_events=[_FakeBoundaryEvent(dig_complete=True)],
        boundary_profile="v2_4_5_spatial_mass",
    )
    legacy_policy = _make_policy(
        boundary_events=[_FakeBoundaryEvent(dig_complete=True)],
        boundary_profile="v2_4_5_spatial_mass",
    )
    tree_policy._prev_action = np.zeros(4, dtype=np.float32)
    legacy_policy._prev_action = np.zeros(4, dtype=np.float32)

    selected = planner_backend_from_policy_config(
        {"planner_backend": "action_tree_shadow"}
    )
    applied = apply_planner_backend(
        policy=tree_policy,
        policy_class="PRIMITIVE_PLANNER_ACT",
        backend=selected,
    )

    assert applied == ACTION_TREE_SHADOW_BACKEND
    assert PrimitivePlannerACTPolicy.predict is original_predict
    assert hasattr(tree_policy, "_primitive_action_tree_runner")
    assert not hasattr(legacy_policy, "_primitive_action_tree_runner")

    tree_action = tree_policy.predict(_obs(mass=1000.0, dig_distance=0.0))
    legacy_action = legacy_policy.predict(_obs(mass=1000.0, dig_distance=0.0))

    np.testing.assert_allclose(tree_action, legacy_action, atol=1e-6)
    assert tree_policy.debug_state()["skill_name"] == "carry"
    assert legacy_policy.debug_state()["skill_name"] == "carry"


def test_planner_backend_config_rejects_action_tree_for_5p() -> None:
    policy = _make_policy(boundary_events=[], boundary_profile="legacy")

    with pytest.raises(ValueError, match="5P"):
        apply_planner_backend(
            policy=policy,
            policy_class="PRIMITIVE_PLANNER_ACT_5P",
            backend=ACTION_TREE_SHADOW_BACKEND,
        )
    with pytest.raises(ValueError, match="Unsupported planner_backend"):
        planner_backend_from_policy_config({"planner_backend": "not_applicable"})


def test_planner_backend_metadata_defaults_missing_legacy() -> None:
    assert planner_backend_from_metadata({}) == LEGACY_FSM_BACKEND
    assert (
        planner_backend_from_metadata(
            {},
            {"policy": {"planner_backend": "action_tree_shadow"}},
        )
        == LEGACY_FSM_BACKEND
    )
    assert (
        planner_backend_from_metadata({"planner_backend": "not_applicable"})
        == NOT_APPLICABLE_BACKEND
    )
    assert (
        planner_backend_from_metadata({"planner_backend": "action_tree_shadow"})
        == ACTION_TREE_SHADOW_BACKEND
    )


def _run_transition_pair(
    legacy: PrimitivePlannerACTPolicy,
    tree_policy: PrimitivePlannerACTPolicy,
    obs: dict[str, Any],
    boundary_event: Any | None,
):
    runner = PrimitiveActionTreeRunner()
    legacy._switch_reason = ""
    tree_policy._switch_reason = ""

    legacy._maybe_switch_skill(obs=deepcopy(obs), boundary_event=boundary_event)
    trace = runner.tick_transition(tree_policy, deepcopy(obs), boundary_event)

    assert tree_policy._skill_name == legacy._skill_name
    assert tree_policy._switch_reason == legacy._switch_reason
    assert tree_policy._cycle_index == legacy._cycle_index
    assert tree_policy._completed_transition_count == legacy._completed_transition_count
    return trace


def _assert_observable_surfaces_match(
    legacy: PrimitivePlannerACTPolicy,
    tree_policy: PrimitivePlannerACTPolicy,
) -> None:
    legacy_debug = legacy.debug_state()
    tree_debug = tree_policy.debug_state()
    for key in [
        "skill_name",
        "skill_switch_reason",
        "transition_timeout",
        "transition_completed",
        "completed_transition_count",
        "transition_timeout_count",
        "dump_ready_hold_count",
        "dump_done_hold_count",
        "primitive_cycle_index",
    ]:
        assert tree_debug[key] == legacy_debug[key]

    legacy_summary = legacy.rollout_summary()
    tree_summary = tree_policy.rollout_summary()
    for key in [
        "completed_transition_count",
        "transition_timeout_count",
        "primitive_cycle_index",
        "primitive_final_skill",
    ]:
        assert tree_summary[key] == legacy_summary[key]

    legacy_trace = legacy.planner_trace()
    tree_trace = tree_policy.planner_trace()
    for key in [
        "dig_cut_token_contract",
        "return_target_token_contract",
        "return_start_envelope_token_contract",
        "coverage_decision_trace_count",
    ]:
        assert tree_trace[key] == legacy_trace[key]


def _make_policy(
    *,
    boundary_events: list[_FakeBoundaryEvent],
    boundary_profile: str,
    **kwargs: Any,
) -> PrimitivePlannerACTPolicy:
    return PrimitivePlannerACTPolicy(
        dig_policy=_ConstantPolicy(0),
        carry_policy=_ConstantPolicy(1),
        dump_policy=_ConstantPolicy(2),
        return_policy=_ConstantPolicy(3),
        boundary_detector=_FakeBoundaryDetector(
            boundary_events,
            boundary_profile=boundary_profile,
        ),
        dig_to_carry_min_bucket_mass_kg=999.0,
        dump_ready_hold_steps=3,
        dump_done_hold_steps=30,
        **kwargs,
    )


def _golden_boundary_events() -> list[_FakeBoundaryEvent]:
    return [
        _FakeBoundaryEvent(dig_complete=True),
        _FakeBoundaryEvent(dump_committed_start=True),
        _FakeBoundaryEvent(dump_complete=True),
        _FakeBoundaryEvent(next_dig_entry_ready=True),
    ]


class _ConstantPolicy:
    def __init__(self, value: float) -> None:
        self.value = float(value)
        self.reset_count = 0

    def reset(self) -> None:
        self.reset_count += 1

    def predict(self, _obs: dict) -> np.ndarray:
        action = np.zeros(4, dtype=np.float32)
        action[0] = self.value
        return action


class _FakeBoundaryEvent:
    def __init__(
        self,
        *,
        qualified_dig_start: bool = False,
        dig_complete: bool = False,
        dump_committed_start: bool = False,
        dump_complete: bool = False,
        next_dig_entry_ready: bool = False,
        dump_end: bool = False,
        metrics: dict | None = None,
    ) -> None:
        self.qualified_dig_start = bool(qualified_dig_start)
        self.dig_complete = bool(dig_complete)
        self.dump_committed_start = bool(dump_committed_start)
        self.dump_complete = bool(dump_complete)
        self.next_dig_entry_ready = bool(next_dig_entry_ready)
        self.dump_end = bool(dump_end)
        self.metrics = dict(metrics or {})


class _FakeBoundaryDetector:
    def __init__(
        self,
        events: list[_FakeBoundaryEvent],
        *,
        boundary_profile: str,
    ) -> None:
        self.events = list(events)
        self.config = type(
            "_FakeBoundaryConfig",
            (),
            {"boundary_profile": str(boundary_profile)},
        )()

    def reset(self) -> None:
        pass

    def update(self, **_kwargs: Any) -> _FakeBoundaryEvent:
        if self.events:
            return self.events.pop(0)
        return _FakeBoundaryEvent()


def _obs(
    *,
    mass: float,
    dig_distance: float,
    bucket_depth: float = 0.0,
    dump_ready: bool = False,
    deposited: float = 0.0,
    bucket_pose: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> dict[str, Any]:
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_MASS_IN_BUCKET_IDX] = float(mass)
    env_state[ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX] = float(deposited)
    env_state[ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX] = float(dig_distance)
    env_state[ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX] = float(bucket_depth)
    env_state[ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX] = 0.15 if dump_ready else 2.0
    env_state[ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX] = (
        0.50 if dump_ready else -0.20
    )
    env_state[ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX] = 1.0 if dump_ready else 0.0
    env_state[ENV_STATE_DUMP_CLEARANCE_OK_IDX] = 1.0 if dump_ready else 0.0
    env_state[ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX] = 0.0
    env_state[ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX] = 0.0
    env_state[ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX] = (
        0.0 if dump_ready else 2.0
    )
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX] = float(bucket_pose[0])
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX] = float(bucket_pose[1])
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX] = float(bucket_pose[2])
    env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX] = float(bucket_pose[0])
    env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX] = float(bucket_pose[1])
    env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX] = float(bucket_pose[2])
    return {
        "qpos": np.zeros(4, dtype=np.float32),
        "qvel": np.zeros(4, dtype=np.float32),
        "env_state": env_state,
        "task_metrics": {
            "mass_in_bucket_kg": float(mass),
            "deposited_mass_in_target_box_kg": float(deposited),
            "min_distance_to_dig_area_m": float(dig_distance),
            "bucket_depth_below_dig_area_plane_m": float(bucket_depth),
            "target_geometry_available": 1.0,
            "target_horizontal_distance_m": float(
                env_state[ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX]
            ),
            "bucket_height_above_target_rim_m": float(
                env_state[ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX]
            ),
            "bucket_over_target_footprint_mask": float(
                env_state[ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX]
            ),
            "dump_clearance_ok_mask": float(
                env_state[ENV_STATE_DUMP_CLEARANCE_OK_IDX]
            ),
            "bucket_dump_area_relative_x_m": float(
                env_state[ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX]
            ),
            "bucket_dump_area_relative_z_m": float(
                env_state[ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX]
            ),
            "bucket_dump_area_footprint_outside_distance_m": float(
                env_state[ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX]
            ),
        },
    }
