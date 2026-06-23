from __future__ import annotations

from types import MethodType, SimpleNamespace

import numpy as np
import pytest

from testbed.planner.primitive_scripted_bootstrap import (
    PrimitiveScriptedBootstrapReportStatus,
    PrimitiveScriptedBootstrapRuntimeConfig,
    PrimitiveScriptedBootstrapRuntimeService,
    PrimitiveScriptedBootstrapRuntimeState,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


_DEFAULT_TARGET = object()


def _config(
    *,
    action_dim: int = 4,
    bootstrap_end_mode: str = "scripted_qpos",
    target_qpos: np.ndarray | None | object = _DEFAULT_TARGET,
    hold_steps: int = 2,
    max_steps: int = 3,
    action_clip: float | list[float] = 1.0,
    action_signs: list[float] | None = None,
) -> PrimitiveScriptedBootstrapRuntimeConfig:
    return PrimitiveScriptedBootstrapRuntimeConfig(
        action_dim=action_dim,
        bootstrap_end_mode=bootstrap_end_mode,
        target_qpos=(
            np.asarray([1.0, -1.0, 0.5, 0.0], dtype=np.float32)
            if target_qpos is _DEFAULT_TARGET
            else target_qpos
        ),
        kp=2.0,
        kd=0.25,
        action_clip=action_clip,
        action_signs=action_signs,
        qpos_tolerance=0.02,
        qvel_abs_max=0.08,
        hold_steps=hold_steps,
        max_steps=max_steps,
    )


def _install_policy_scripted_config(
    policy: PrimitivePlannerACTPolicy,
    *,
    target_qpos: np.ndarray | None = None,
    action_clip: float | list[float] = 1.0,
    action_signs: list[float] | None = None,
) -> None:
    policy.action_dim = 4
    policy.bootstrap_end_mode = "scripted_qpos"
    policy.scripted_bootstrap_target_qpos = (
        np.asarray([1.0, -1.0, 0.5, 0.0], dtype=np.float32)
        if target_qpos is None
        else target_qpos
    )
    policy.scripted_bootstrap_kp = 2.0
    policy.scripted_bootstrap_kd = 0.25
    policy.scripted_bootstrap_action_clip = action_clip
    policy.scripted_bootstrap_action_signs = action_signs
    policy.scripted_bootstrap_qpos_tolerance = 0.02
    policy.scripted_bootstrap_qvel_abs_max = 0.08
    policy.scripted_bootstrap_hold_steps = 2
    policy.scripted_bootstrap_max_steps = 3


def test_scripted_bootstrap_state_fresh_matches_legacy_reset_defaults() -> None:
    state = PrimitiveScriptedBootstrapRuntimeState.fresh()

    assert state.step_count == 0
    assert state.hold_count == 0
    assert state.timeout_count == 0


def test_policy_legacy_scripted_bootstrap_fields_use_one_state_owner() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    state = policy._primitive_scripted_bootstrap_runtime_state()

    policy._scripted_bootstrap_step_count = 3
    policy._scripted_bootstrap_hold_count = 4
    policy._scripted_bootstrap_timeout_count = 5

    assert policy._primitive_scripted_bootstrap_runtime_state() is state
    assert state.step_count == 3
    assert state.hold_count == 4
    assert state.timeout_count == 5


def test_policy_reset_application_replaces_scripted_bootstrap_state_owner() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    old_state = policy._primitive_scripted_bootstrap_runtime_state()
    old_state.step_count = 9
    reset_state = PrimitiveScriptedBootstrapRuntimeState.fresh()

    class _ResetState:
        def as_policy_field_updates(self):
            return {"_scripted_bootstrap_state": reset_state}

    policy._apply_reset_lifecycle_state(_ResetState())
    policy._scripted_bootstrap_step_count = 2

    assert policy._primitive_scripted_bootstrap_runtime_state() is reset_state
    assert policy._primitive_scripted_bootstrap_runtime_state() is not old_state
    assert reset_state.step_count == 2
    assert old_state.step_count == 9


def test_service_enabled_matches_scripted_qpos_target_rule() -> None:
    state = PrimitiveScriptedBootstrapRuntimeState.fresh()

    assert PrimitiveScriptedBootstrapRuntimeService(_config(), state).enabled() is True
    assert (
        PrimitiveScriptedBootstrapRuntimeService(
            _config(bootstrap_end_mode="first_qualified_dig_start"),
            state,
        ).enabled()
        is False
    )
    assert (
        PrimitiveScriptedBootstrapRuntimeService(
            _config(target_qpos=None),
            state,
        ).enabled()
        is False
    )


def test_target_reached_updates_hold_count_and_resets_on_gate_failure() -> None:
    state = PrimitiveScriptedBootstrapRuntimeState.fresh()
    service = PrimitiveScriptedBootstrapRuntimeService(_config(hold_steps=2), state)
    target = service.config.target_qpos.copy()
    obs = {"qpos": target.copy(), "qvel": np.zeros(4, dtype=np.float32)}

    assert service.target_reached(obs) is False
    assert state.hold_count == 1
    assert service.target_reached(obs) is True
    assert state.hold_count == 2

    failed = {"qpos": target + np.asarray([0.1, 0.0, 0.0, 0.0]), "qvel": obs["qvel"]}
    assert service.target_reached(failed) is False
    assert state.hold_count == 0


def test_should_end_bootstrap_timeout_increments_only_for_enabled_timeout() -> None:
    state = PrimitiveScriptedBootstrapRuntimeState.fresh()
    state.step_count = 3
    service = PrimitiveScriptedBootstrapRuntimeService(_config(max_steps=3), state)

    assert service.should_end_bootstrap({"qpos": np.zeros(4), "qvel": np.ones(4)}) is True
    assert state.timeout_count == 1

    disabled = PrimitiveScriptedBootstrapRuntimeService(
        _config(bootstrap_end_mode="loaded_and_clear"),
        state,
    )
    assert disabled.should_end_bootstrap({"qpos": np.zeros(4)}) is False
    assert state.timeout_count == 1


def test_action_updates_step_count_and_preserves_pd_clip_sign_dtype_shape() -> None:
    state = PrimitiveScriptedBootstrapRuntimeState.fresh()
    service = PrimitiveScriptedBootstrapRuntimeService(
        _config(
            action_dim=2,
            target_qpos=np.asarray([1.0, -1.0], dtype=np.float32),
            action_clip=[0.5, 1.0],
            action_signs=[1.0, -1.0],
        ),
        state,
    )

    action = service.action(
        {
            "qpos": np.asarray([0.5, 0.0], dtype=np.float32),
            "qvel": np.asarray([0.2, -0.4], dtype=np.float32),
        }
    )

    assert state.step_count == 1
    assert action.dtype == np.float32
    assert action.shape == (2,)
    assert action.tolist() == [0.5, 1.0]


def test_action_raises_exact_error_without_target_qpos() -> None:
    state = PrimitiveScriptedBootstrapRuntimeState.fresh()
    service = PrimitiveScriptedBootstrapRuntimeService(_config(target_qpos=None), state)

    with pytest.raises(
        RuntimeError,
        match="^scripted bootstrap is active without target qpos\\.$",
    ):
        service.action({"qpos": np.zeros(4)})


def test_policy_scripted_bootstrap_facades_delegate_to_service() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    _install_policy_scripted_config(policy, action_clip=[0.5, 1.0, 1.0, 1.0])
    state = policy._primitive_scripted_bootstrap_runtime_state()

    assert policy._scripted_bootstrap_enabled() is True
    assert policy._scripted_bootstrap_target_reached(
        {
            "qpos": policy.scripted_bootstrap_target_qpos.copy(),
            "qvel": np.zeros(4, dtype=np.float32),
        }
    ) is False
    assert state.hold_count == 1

    action = policy._scripted_bootstrap_action(
        {
            "qpos": np.asarray([0.5, 0.0, 0.5, 0.0], dtype=np.float32),
            "qvel": np.zeros(4, dtype=np.float32),
        }
    )

    assert state.step_count == 1
    assert action.dtype == np.float32
    assert action.shape == (4,)
    assert action[0] == 0.5


def test_policy_should_end_bootstrap_uses_scripted_service_timeout_path() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    _install_policy_scripted_config(policy)
    state = policy._primitive_scripted_bootstrap_runtime_state()
    state.step_count = 3

    assert policy._should_end_bootstrap(
        obs={"qpos": np.zeros(4, dtype=np.float32), "qvel": np.ones(4)},
        boundary_event=None,
    ) is True
    assert state.timeout_count == 1


def test_policy_debug_scripted_bootstrap_fields_read_state_owner() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    state = policy._primitive_scripted_bootstrap_runtime_state()
    state.step_count = 7
    state.hold_count = 2
    state.timeout_count = 1

    assert policy._debug_report_scripted_bootstrap_fields() == {
        "scripted_bootstrap_step_count": 7,
        "scripted_bootstrap_hold_count": 2,
        "scripted_bootstrap_timeout_count": 1,
    }


def test_scripted_bootstrap_runtime_state_projects_fresh_report_status() -> None:
    state = PrimitiveScriptedBootstrapRuntimeState.fresh()

    status = state.to_report_status()

    assert status == PrimitiveScriptedBootstrapReportStatus(
        step_count=0,
        hold_count=0,
        timeout_count=0,
    )
    assert status.debug_fields() == {
        "scripted_bootstrap_step_count": 0,
        "scripted_bootstrap_hold_count": 0,
        "scripted_bootstrap_timeout_count": 0,
    }


def test_scripted_bootstrap_runtime_state_projects_populated_report_status() -> None:
    state = PrimitiveScriptedBootstrapRuntimeState.fresh()
    state.step_count = 7
    state.hold_count = 2
    state.timeout_count = 1

    status = state.to_report_status()

    assert status == PrimitiveScriptedBootstrapReportStatus(
        step_count=7,
        hold_count=2,
        timeout_count=1,
    )
    assert status.debug_fields() == {
        "scripted_bootstrap_step_count": 7,
        "scripted_bootstrap_hold_count": 2,
        "scripted_bootstrap_timeout_count": 1,
    }


def test_policy_scripted_bootstrap_debug_facade_delegates_to_report_status() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    state = policy._primitive_scripted_bootstrap_runtime_state()
    state.step_count = 7
    state.hold_count = 2
    state.timeout_count = 1

    assert (
        policy._debug_report_scripted_bootstrap_fields()
        == state.to_report_status().debug_fields()
    )


def test_policy_rollout_summary_inputs_use_scripted_bootstrap_report_status() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    status = PrimitiveScriptedBootstrapReportStatus(
        step_count=7,
        hold_count=2,
        timeout_count=9,
    )
    policy._scripted_bootstrap_report_status = MethodType(
        lambda self: status,
        policy,
    )
    policy._return_report_status = MethodType(
        lambda self: SimpleNamespace(
            return_to_dig_entry_error_m=0.0,
            return_to_dig_entry_close=True,
            return_next_dig_event_seen=False,
            return_to_dig_start_envelope_gate_enabled=False,
            return_to_dig_start_envelope_direct_handoff_enabled=False,
            return_to_dig_start_envelope_ready=True,
            return_to_dig_start_envelope_plane_depth_mode="range",
            return_to_dig_start_envelope_local_depth_tolerance_m=0.0,
            return_to_dig_start_envelope_error=0.0,
        ),
        policy,
    )
    policy.dump_done_use_boundary_event = False
    policy.cell_entry_enabled = False
    policy.return_to_dig_max_entry_error_m = 0.5
    policy.dig_cut_planner_mode = "operator_prior"
    policy.dig_cut_prior_id = "default"
    policy.dig_cut_prior_path = ""
    policy.dig_failed_replan_next_skill = "dig"
    policy.coverage_multi_pass_enabled = False
    policy.coverage_use_env_removed_depth = False
    policy.coverage_candidate_layout = "corridor_grid"
    policy.coverage_first_dig_strategy = "best_score"
    policy.coverage_first_dig_preferred_corridor_id = None
    policy.coverage_first_dig_max_entry_distance_m = None
    policy.coverage_first_dig_qpos_delta_weight = 1.0
    policy.pre_dig_align_enabled = False
    policy.pre_dig_align_first_dig_only = True
    policy.pre_dig_align_replan_after_failed_dig = False
    policy.pre_dig_align_surface_guard_enabled = False

    inputs = policy._rollout_summary_inputs()

    assert inputs.scripted_bootstrap_timeout_count == 9
