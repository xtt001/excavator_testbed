from __future__ import annotations

import numpy as np
import pytest

from testbed.data.schema import (
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX,
)
from testbed.planner.bootstrap import (
    BOOTSTRAP_FACT_FIELDS,
    BOOTSTRAP_RUNTIME_CONFIG_FIELDS,
    BOOTSTRAP_RUNTIME_STATUS_FIELDS,
    BootstrapConfig,
    BootstrapEndTransitionFacts,
    BootstrapEndTransitionRequest,
    BootstrapFacts,
    BootstrapRuntimeStatusState,
    BootstrapService,
    BootstrapTransitionConfig,
    build_bootstrap_config_from_mapping,
    build_bootstrap_facts,
    build_bootstrap_facts_from_mapping,
    build_bootstrap_facts_from_observation_view,
    build_bootstrap_planner_config,
    build_bootstrap_runtime_status_state_from_mapping,
)
from testbed.planner.snapshots import build_planner_snapshot


def _config(**overrides: object) -> BootstrapConfig:
    values = {
        "action_dim": 4,
        "end_mode": "scripted_qpos",
        "end_min_bucket_mass_kg": 300.0,
        "end_min_distance_to_dig_area_m": 0.25,
        "scripted_target_qpos": np.asarray([0.5, 0.6, 0.2, 0.1], dtype=np.float32),
        "scripted_kp": 2.0,
        "scripted_kd": 0.25,
        "scripted_action_clip": [0.75, 0.35, 0.35, 0.55],
        "scripted_action_signs": np.ones(4, dtype=np.float32),
        "scripted_qpos_tolerance": 0.02,
        "scripted_qvel_abs_max": 0.08,
        "scripted_hold_steps": 2,
        "scripted_max_steps": 5,
    }
    values.update(overrides)
    return BootstrapConfig(**values)


def _facts(**overrides: object) -> BootstrapFacts:
    values = {
        "qpos": np.asarray([0.5, 0.6, 0.2, 0.1], dtype=np.float32),
        "qvel": np.zeros(4, dtype=np.float32),
    }
    values.update(overrides)
    return BootstrapFacts(**values)


def test_build_bootstrap_facts_projects_inputs_to_legacy_shape() -> None:
    facts = build_bootstrap_facts(
        action_dim=4,
        qpos=np.asarray([[1.0, 2.0, 3.0, 4.0]], dtype=np.float64),
        qvel=np.asarray([[0.1, 0.2, 0.3, 0.4]], dtype=np.float64),
        mass_in_bucket_kg="12.5",
        min_distance_to_dig_area_m="0.75",
        qualified_dig_start=1,
        step_count="3",
        hold_count="2",
        bootstrap_policy_present=1,
    )

    np.testing.assert_allclose(
        facts.qpos,
        np.asarray([1.0, 2.0, 3.0, 4.0], dtype=np.float32),
    )
    np.testing.assert_allclose(
        facts.qvel,
        np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
    )
    assert facts.qpos.dtype == np.float32
    assert facts.qvel.dtype == np.float32
    assert facts.mass_in_bucket_kg == pytest.approx(12.5)
    assert facts.min_distance_to_dig_area_m == pytest.approx(0.75)
    assert facts.qualified_dig_start is True
    assert facts.step_count == 3
    assert facts.hold_count == 2
    assert facts.bootstrap_policy_present is True


def test_build_bootstrap_facts_preserves_optional_defaults() -> None:
    facts = build_bootstrap_facts(
        action_dim=4,
        qpos=None,
        qvel=None,
    )

    np.testing.assert_array_equal(facts.qpos, np.zeros(4, dtype=np.float32))
    np.testing.assert_array_equal(facts.qvel, np.zeros(4, dtype=np.float32))
    assert facts.mass_in_bucket_kg == pytest.approx(0.0)
    assert facts.min_distance_to_dig_area_m == pytest.approx(0.0)
    assert facts.qualified_dig_start is False
    assert facts.step_count == 0
    assert facts.hold_count == 0
    assert facts.bootstrap_policy_present is False


def test_build_bootstrap_facts_from_mapping_preserves_projection() -> None:
    values = {
        "action_dim": "4",
        "qpos": np.asarray([[1.0, 2.0, 3.0, 4.0]], dtype=np.float64),
        "qvel": np.asarray([[0.1, 0.2, 0.3, 0.4]], dtype=np.float64),
        "mass_in_bucket_kg": "12.5",
        "min_distance_to_dig_area_m": np.float64(0.75),
        "qualified_dig_start": 1,
        "step_count": "3",
        "hold_count": np.int64(2),
        "bootstrap_policy_present": object(),
        "ignored": object(),
    }

    facts = build_bootstrap_facts_from_mapping(values)

    assert set(BOOTSTRAP_FACT_FIELDS) == set(values) - {"ignored"}
    np.testing.assert_allclose(
        facts.qpos,
        np.asarray([1.0, 2.0, 3.0, 4.0], dtype=np.float32),
    )
    np.testing.assert_allclose(
        facts.qvel,
        np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
    )
    assert facts.qpos.dtype == np.float32
    assert facts.qvel.dtype == np.float32
    assert facts.mass_in_bucket_kg == pytest.approx(12.5)
    assert facts.min_distance_to_dig_area_m == pytest.approx(0.75)
    assert facts.qualified_dig_start is True
    assert facts.step_count == 3
    assert facts.hold_count == 2
    assert facts.bootstrap_policy_present is True


def test_build_bootstrap_facts_from_observation_view_preserves_sources() -> None:
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_MASS_IN_BUCKET_IDX] = 7.5
    env_state[ENV_STATE_MIN_DISTANCE_TO_DIG_AREA_IDX] = 0.25
    obs = {
        "env_state": env_state,
        "qpos": np.asarray([[1.0, 2.0, 3.0, 4.0]], dtype=np.float64),
        "qvel": np.asarray([[0.1, 0.2, 0.3, 0.4]], dtype=np.float64),
        "task_metrics": {"mass_in_bucket_kg": "12.5"},
    }
    boundary_event = type(
        "_BoundaryEvent",
        (),
        {"qualified_dig_start": True},
    )()
    snapshot = build_planner_snapshot(
        obs,
        active_skill="bootstrap",
        cycle_index=0,
        prev_action=None,
        boundary_event=boundary_event,
        action_dim=4,
    )

    facts = BootstrapService.facts_from_observation_view(
        view=snapshot.view,
        boundary_event=boundary_event,
        step_count="3",
        hold_count=np.int64(2),
        bootstrap_policy_present=object(),
    )
    expected = build_bootstrap_facts_from_observation_view(
        view=snapshot.view,
        boundary_event=boundary_event,
        step_count="3",
        hold_count=np.int64(2),
        bootstrap_policy_present=object(),
    )

    np.testing.assert_allclose(
        facts.qpos,
        expected.qpos,
    )
    np.testing.assert_allclose(
        facts.qvel,
        expected.qvel,
    )
    assert facts.qpos.dtype == np.float32
    assert facts.qvel.dtype == np.float32
    assert facts.mass_in_bucket_kg == pytest.approx(12.5)
    assert facts.min_distance_to_dig_area_m == pytest.approx(0.25)
    assert expected.mass_in_bucket_kg == pytest.approx(12.5)
    assert expected.min_distance_to_dig_area_m == pytest.approx(0.25)
    assert facts.qualified_dig_start is expected.qualified_dig_start
    assert facts.step_count == expected.step_count
    assert facts.hold_count == expected.hold_count
    assert facts.bootstrap_policy_present is expected.bootstrap_policy_present


def test_build_bootstrap_facts_from_observation_view_preserves_missing_defaults() -> None:
    snapshot = build_planner_snapshot(
        {},
        active_skill="bootstrap",
        cycle_index=0,
        prev_action=None,
        boundary_event=None,
        action_dim=4,
    )

    facts = BootstrapService.facts_from_observation_view(view=snapshot.view)

    np.testing.assert_array_equal(facts.qpos, np.zeros(4, dtype=np.float32))
    np.testing.assert_array_equal(facts.qvel, np.zeros(4, dtype=np.float32))
    assert facts.mass_in_bucket_kg == pytest.approx(0.0)
    assert facts.min_distance_to_dig_area_m == pytest.approx(0.0)
    assert facts.qualified_dig_start is False
    assert facts.step_count == 0
    assert facts.hold_count == 0
    assert facts.bootstrap_policy_present is False


def test_build_bootstrap_planner_config_preserves_defaults_and_shapes() -> None:
    config = build_bootstrap_planner_config(
        action_dim=4,
        bootstrap_end_mode="disabled",
        bootstrap_end_min_bucket_mass_kg=300.0,
        bootstrap_end_min_distance_to_dig_area_m=0.25,
        scripted_bootstrap_target_qpos=None,
        scripted_bootstrap_kp=2.0,
        scripted_bootstrap_kd=0.25,
        scripted_bootstrap_action_clip=0.35,
        scripted_bootstrap_action_signs=None,
        scripted_bootstrap_qpos_tolerance=0.02,
        scripted_bootstrap_qvel_abs_max=0.08,
        scripted_bootstrap_hold_steps=5,
        scripted_bootstrap_max_steps=240,
    )

    assert config.bootstrap_end_mode == "disabled"
    assert config.bootstrap_end_min_bucket_mass_kg == pytest.approx(300.0)
    assert config.bootstrap_end_min_distance_to_dig_area_m == pytest.approx(0.25)
    assert config.scripted_bootstrap_target_qpos is None
    assert config.scripted_bootstrap_kp == pytest.approx(2.0)
    assert config.scripted_bootstrap_kd == pytest.approx(0.25)
    assert config.scripted_bootstrap_action_clip == 0.35
    np.testing.assert_allclose(
        config.scripted_bootstrap_action_signs,
        np.ones(4, dtype=np.float32),
    )
    assert config.scripted_bootstrap_action_signs.dtype == np.float32
    assert config.scripted_bootstrap_qpos_tolerance == pytest.approx(0.02)
    assert config.scripted_bootstrap_qvel_abs_max == pytest.approx(0.08)
    assert config.scripted_bootstrap_hold_steps == 5
    assert config.scripted_bootstrap_max_steps == 240


def test_build_bootstrap_planner_config_preserves_overrides_and_coercion() -> None:
    config = build_bootstrap_planner_config(
        action_dim=4,
        bootstrap_end_mode="scripted_qpos",
        bootstrap_end_min_bucket_mass_kg=12,
        bootstrap_end_min_distance_to_dig_area_m=0.5,
        scripted_bootstrap_target_qpos=[0.1, 0.2, 0.3, 0.4],
        scripted_bootstrap_kp=3,
        scripted_bootstrap_kd=0.75,
        scripted_bootstrap_action_clip=[0.1, 0.2, 0.3, 0.4],
        scripted_bootstrap_action_signs=[1.0, -1.0, 1.0, -1.0],
        scripted_bootstrap_qpos_tolerance=0.03,
        scripted_bootstrap_qvel_abs_max=0.09,
        scripted_bootstrap_hold_steps=0,
        scripted_bootstrap_max_steps=0,
    )

    assert config.bootstrap_end_mode == "scripted_qpos"
    assert config.bootstrap_end_min_bucket_mass_kg == pytest.approx(12.0)
    assert config.bootstrap_end_min_distance_to_dig_area_m == pytest.approx(0.5)
    np.testing.assert_allclose(
        config.scripted_bootstrap_target_qpos,
        np.asarray([0.1, 0.2, 0.3, 0.4], dtype=np.float32),
    )
    assert config.scripted_bootstrap_target_qpos.dtype == np.float32
    assert config.scripted_bootstrap_kp == pytest.approx(3.0)
    assert config.scripted_bootstrap_kd == pytest.approx(0.75)
    assert config.scripted_bootstrap_action_clip == [0.1, 0.2, 0.3, 0.4]
    np.testing.assert_allclose(
        config.scripted_bootstrap_action_signs,
        np.asarray([1.0, -1.0, 1.0, -1.0], dtype=np.float32),
    )
    assert config.scripted_bootstrap_action_signs.dtype == np.float32
    assert config.scripted_bootstrap_qpos_tolerance == pytest.approx(0.03)
    assert config.scripted_bootstrap_qvel_abs_max == pytest.approx(0.09)
    assert config.scripted_bootstrap_hold_steps == 1
    assert config.scripted_bootstrap_max_steps == 1


def test_build_bootstrap_config_from_mapping_preserves_runtime_projection() -> None:
    target_qpos = [0.1, 0.2, 0.3, 0.4]
    action_clip = [0.1, 0.2, 0.3, 0.4]
    action_signs = [1.0, -1.0, 1.0, -1.0]
    values = {
        "end_mode": "scripted_qpos",
        "end_min_bucket_mass_kg": "12.5",
        "end_min_distance_to_dig_area_m": "0.75",
        "scripted_target_qpos": target_qpos,
        "scripted_kp": "3.0",
        "scripted_kd": "0.75",
        "scripted_action_clip": action_clip,
        "scripted_action_signs": action_signs,
        "scripted_qpos_tolerance": "0.03",
        "scripted_qvel_abs_max": "0.09",
        "scripted_hold_steps": 0,
        "scripted_max_steps": 0,
        "ignored": object(),
    }

    config = build_bootstrap_config_from_mapping(values, action_dim="4")

    assert {key for key, _ in BOOTSTRAP_RUNTIME_CONFIG_FIELDS} == (
        set(values) - {"ignored"}
    )
    assert config.action_dim == 4
    assert config.end_mode == "scripted_qpos"
    assert config.end_min_bucket_mass_kg == pytest.approx(12.5)
    assert config.end_min_distance_to_dig_area_m == pytest.approx(0.75)
    assert config.scripted_target_qpos is target_qpos
    assert config.scripted_kp == pytest.approx(3.0)
    assert config.scripted_kd == pytest.approx(0.75)
    assert config.scripted_action_clip is action_clip
    assert config.scripted_action_signs is action_signs
    assert config.scripted_qpos_tolerance == pytest.approx(0.03)
    assert config.scripted_qvel_abs_max == pytest.approx(0.09)
    assert config.scripted_hold_steps == 0
    assert config.scripted_max_steps == 0


def test_scripted_target_reached_updates_hold_count() -> None:
    service = BootstrapService()
    config = _config(scripted_hold_steps=2)

    first = service.scripted_target_reached(_facts(hold_count=0), config)
    second = service.scripted_target_reached(_facts(hold_count=first.hold_count), config)
    reset = service.scripted_target_reached(
        _facts(
            qpos=np.asarray([0.7, 0.6, 0.2, 0.1], dtype=np.float32),
            hold_count=second.hold_count,
        ),
        config,
    )

    assert not first.ready
    assert first.hold_count == 1
    assert second.ready
    assert second.hold_count == 2
    assert not reset.ready
    assert reset.hold_count == 0


def test_scripted_timeout_preserves_hold_count_and_requests_increment() -> None:
    service = BootstrapService()
    config = _config(scripted_hold_steps=3, scripted_max_steps=2)

    decision = service.should_end(
        _facts(hold_count=1, step_count=2),
        config,
    )

    assert decision.should_end
    assert decision.timeout_increment
    assert decision.hold_count == 2


def test_learned_bootstrap_gates_require_policy_presence() -> None:
    service = BootstrapService()

    assert not service.should_end(
        _facts(
            bootstrap_policy_present=False,
            qualified_dig_start=True,
        ),
        _config(end_mode="first_qualified_dig_start", scripted_target_qpos=None),
    ).should_end
    assert service.should_end(
        _facts(
            bootstrap_policy_present=True,
            qualified_dig_start=True,
        ),
        _config(end_mode="first_qualified_dig_start", scripted_target_qpos=None),
    ).should_end
    assert service.should_end(
        _facts(
            bootstrap_policy_present=True,
            mass_in_bucket_kg=300.0,
            min_distance_to_dig_area_m=0.25,
        ),
        _config(end_mode="loaded_and_clear", scripted_target_qpos=None),
    ).should_end


def test_bootstrap_end_transition_preserves_legacy_next_skill_and_reason() -> None:
    service = BootstrapService()

    carry = service.end_transition(
        BootstrapEndTransitionFacts(pre_dig_align_before_dig=True),
        _config(end_mode="disabled", scripted_target_qpos=None),
    )
    dig = service.end_transition(
        BootstrapEndTransitionFacts(pre_dig_align_before_dig=False),
        _config(
            end_mode="first_qualified_dig_start",
            scripted_target_qpos=None,
        ),
    )
    pre_dig_align = service.end_transition(
        BootstrapEndTransitionFacts(pre_dig_align_before_dig=True),
        _config(end_mode="scripted_qpos"),
    )

    assert carry.next_skill == "carry"
    assert carry.switch_reason == "bootstrap_to_carry"
    assert dig.next_skill == "dig"
    assert dig.switch_reason == "bootstrap_to_dig"
    assert pre_dig_align.next_skill == "pre_dig_align"
    assert pre_dig_align.switch_reason == "bootstrap_to_pre_dig_align"


def test_bootstrap_end_transition_accepts_explicit_skill_names() -> None:
    decision = BootstrapService.end_transition(
        BootstrapEndTransitionFacts(pre_dig_align_before_dig=True),
        _config(
            end_mode="first_qualified_dig_start",
            scripted_target_qpos=None,
        ),
        BootstrapTransitionConfig(
            dig_skill_name="dig_skill",
            carry_skill_name="carry_skill",
            pre_dig_align_skill_name="align_skill",
        ),
    )

    assert decision.next_skill == "align_skill"
    assert decision.switch_reason == "bootstrap_to_align_skill"


def test_bootstrap_end_transition_request_projects_facts_and_config() -> None:
    request = BootstrapService.end_transition_request(
        pre_dig_align_before_dig=1,
        dig_skill_name=123,
        carry_skill_name=456,
        pre_dig_align_skill_name=789,
        dig_start_end_modes=("scripted_qpos", 101),
    )

    assert isinstance(request, BootstrapEndTransitionRequest)
    assert request.facts == BootstrapEndTransitionFacts(
        pre_dig_align_before_dig=True
    )
    assert request.transition_config == BootstrapTransitionConfig(
        dig_skill_name="123",
        carry_skill_name="456",
        pre_dig_align_skill_name="789",
        dig_start_end_modes=("scripted_qpos", "101"),
    )
    decision = BootstrapService.end_transition(
        request.facts,
        _config(end_mode="scripted_qpos"),
        request.transition_config,
    )

    assert decision.next_skill == "789"
    assert decision.switch_reason == "bootstrap_to_789"


def test_runtime_status_snapshot_projects_scripted_counters() -> None:
    snapshot = BootstrapService.runtime_status_snapshot(
        BootstrapRuntimeStatusState(
            step_count=np.int64(4),
            hold_count=np.int64(2),
            timeout_count=np.int64(1),
        )
    )

    assert snapshot.step_count == 4
    assert snapshot.hold_count == 2
    assert snapshot.timeout_count == 1


def test_runtime_status_state_mapping_preserves_legacy_projection() -> None:
    values = {
        "step_count": "4",
        "hold_count": np.int64(2),
        "timeout_count": 1.0,
        "ignored": object(),
    }

    state = build_bootstrap_runtime_status_state_from_mapping(values)

    assert {key for key, _ in BOOTSTRAP_RUNTIME_STATUS_FIELDS} == (
        set(values) - {"ignored"}
    )
    assert state == BootstrapRuntimeStatusState(
        step_count=4,
        hold_count=2,
        timeout_count=1,
    )


def test_initial_runtime_state_preserves_legacy_reset_defaults() -> None:
    state = BootstrapService.initial_runtime_state()

    assert isinstance(state, BootstrapRuntimeStatusState)
    assert state.step_count == 0
    assert state.hold_count == 0
    assert state.timeout_count == 0


def test_scripted_action_matches_pd_control_and_action_signs() -> None:
    service = BootstrapService()
    config = _config(
        scripted_kp=2.0,
        scripted_kd=0.25,
        scripted_action_signs=np.asarray([1.0, -1.0, 1.0, 1.0], dtype=np.float32),
    )

    action = service.scripted_action(
        _facts(
            qpos=np.asarray([0.4, 0.7, 0.1, 0.2], dtype=np.float32),
            qvel=np.asarray([0.1, -0.1, 0.0, 0.2], dtype=np.float32),
        ),
        config,
    )

    np.testing.assert_allclose(
        action,
        np.asarray([0.175, 0.175, 0.2, -0.25], dtype=np.float32),
        atol=1e-6,
    )


def test_scripted_action_requires_target_qpos() -> None:
    service = BootstrapService()

    with pytest.raises(RuntimeError, match="scripted bootstrap"):
        service.scripted_action(
            _facts(),
            _config(scripted_target_qpos=None),
        )
