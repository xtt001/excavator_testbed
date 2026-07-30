from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from test_agx_primitives_v2_2 import (
    _coverage_obs,
    _coverage_planner_policy,
    _RecordingPolicy,
)

from testbed.data.schema import (
    ENV_STATE_DIG_AREA_CELL_LONG_SIZE_IDX,
    ENV_STATE_DIG_AREA_CELL_SHORT_SIZE_IDX,
    ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX,
    ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX,
    ENV_STATE_DIG_AREA_LONG_AXIS_IDX,
    ENV_STATE_V2_4_DIM,
)
from testbed.planner.primitive.config.adapter import (
    PrimitivePlannerAdapterConfigInputs,
    PrimitivePlannerAdapterConfigNormalizer,
)
from testbed.planner.primitive.coverage.exemplars import (
    CoverageStateExemplarPlanner,
    CoverageStateExemplarPlannerConfig,
)
from testbed.planner.primitive.coverage.facts import (
    CoveragePlanningFactConfig,
    CoveragePlanningFactService,
)
from testbed.planner.primitive.coverage.selection import CoverageCorridorState
from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.coverage.wall_safety import (
    CONSERVATIVE_2D_WORKTOOL_SWEPT_FOOTPRINT_PROFILE,
    CoverageFinalWallSafetyError,
    CoverageWallSafetyConfig,
)

ROOT = Path(__file__).parents[1]
STRICT_PRIOR = (
    ROOT
    / "testbed/configs/planner_priors/"
    "yulong_strict18_train_surface_depth_dig_cut_prior_v1.json"
)
WALL_CONFIG = {
    "enabled": True,
    "profile": CONSERVATIVE_2D_WORKTOOL_SWEPT_FOOTPRINT_PROFILE,
    "worktool_width_m": 0.70,
    "hard_clearance_m": 0.30,
    "soft_clearance_m": 0.45,
    "max_score_penalty": 1.0,
    "missing_geometry": "fail_closed",
}


def _wall_obs(
    *,
    half_scale: float = 1.0,
    step_id: int = 1,
) -> dict:
    obs = _coverage_obs(
        mass=0.0,
        dig_distance=0.0,
        bucket_pose=(0.615094, 0.0, -0.439306),
    )
    old_env = np.asarray(obs["env_state"], dtype=np.float32)
    env = np.zeros(ENV_STATE_V2_4_DIM, dtype=np.float32)
    env[: old_env.size] = old_env
    env[ENV_STATE_DIG_AREA_LONG_AXIS_IDX] = 2.0
    env[ENV_STATE_DIG_AREA_GRID_LONG_COUNT_IDX] = 3.0
    env[ENV_STATE_DIG_AREA_GRID_SHORT_COUNT_IDX] = 2.0
    env[ENV_STATE_DIG_AREA_CELL_LONG_SIZE_IDX] = 1.0 * half_scale
    env[ENV_STATE_DIG_AREA_CELL_SHORT_SIZE_IDX] = 1.25 * half_scale
    obs["env_state"] = env
    obs["step_id"] = int(step_id)
    return obs


def _wall_policy(
    *,
    dig_policy: _RecordingPolicy | None = None,
    return_policy: _RecordingPolicy | None = None,
):
    policy = _coverage_planner_policy(
        dig_policy=dig_policy or _RecordingPolicy(0),
        return_policy=return_policy,
        prior_path=STRICT_PRIOR,
        coverage_extra={
            "candidate_layout": "cell_weighted_3x2",
            "first_dig_strategy": "coverage_score",
            "wall_safety": WALL_CONFIG,
        },
        dig_cut_mode="operator_prior_sweep_belief",
        dig_cut_fallback_mode="raise",
        return_target_enabled=True,
        box_emptying={"safety_enabled": True, "safety": {}},
    )
    return policy


def test_strict_prior_filters_cells_0_1_and_keeps_cells_2_to_5_near_wall() -> None:
    policy = _wall_policy()
    selected = (
        policy._primitive_coverage_selection_runtime()
        .select_next_coverage_corridor(_wall_obs())
    )
    by_cell = {
        int(item["cell_id"]): item
        for item in policy._coverage_runtime_state().coverage_candidate_scores
    }

    assert [by_cell[cell]["wall_safety_class"] for cell in (0, 1)] == [
        "hard_reject",
        "hard_reject",
    ]
    assert all(by_cell[cell]["wall_safety_eligible"] == 0 for cell in (0, 1))
    assert all(
        by_cell[cell]["wall_safety_class"] == "near_wall"
        for cell in (2, 3, 4, 5)
    )
    assert all(by_cell[cell]["wall_safety_eligible"] == 1 for cell in (2, 3, 4, 5))
    assert int(selected.cell_id) in {2, 3, 4, 5}
    assert by_cell[2]["wall_minimum_clearance_m"] == pytest.approx(
        0.335155,
        abs=1.0e-6,
    )


def test_unsafe_high_score_and_blocked_or_final_rejected_candidates_cannot_win() -> None:
    policy = _wall_policy()
    runtime = policy._primitive_coverage_selection_runtime()
    runtime.ensure_coverage_corridors()
    corridors = policy._coverage_runtime_state().coverage_corridors
    corridors[0].source_fraction = 1000.0
    corridors[0].last_effective_deposit_delta_kg = 1.0e9
    corridors[2].depleted = True
    policy._coverage_runtime_state().reject_wall_corridor(3)

    selected = runtime.select_coverage_corridor(_wall_obs())
    by_cell = {
        int(item["cell_id"]): item
        for item in policy._coverage_runtime_state().coverage_candidate_scores
    }

    assert int(selected.cell_id) in {4, 5}
    assert by_cell[0]["selectable"] == 0
    assert by_cell[2]["rejection_reason"] == "corridor_depleted"
    assert by_cell[3]["rejection_reason"] == "wall_safety_final_raw_rejected"


class _UnsafeExemplarPlanner:
    config = CoverageStateExemplarPlannerConfig(
        enabled=True,
        path="",
        dig_cut_prior_path="",
        k=1,
        removed_depth_scale_m=0.12,
        target_cell_weight=2.0,
        temperature=0.35,
        skip_rejected=True,
    )

    def plan(self, _inputs):
        return SimpleNamespace(
            raw_fields={
                "operator_entry_x_m": 0.552648,
                "operator_entry_y_m": 0.0,
                "operator_entry_z_m": -1.029915,
                "operator_exit_x_m": 0.308558,
                "operator_exit_y_m": 0.0,
                "operator_exit_z_m": -1.014107,
                "operator_cut_direction_x": -1.0,
                "operator_cut_direction_y": 0.0,
                "operator_cut_direction_z": 0.0,
                "operator_cut_length_m": 0.525479,
                "operator_cut_depth_peak_m": 0.419068,
                "operator_cut_payload_gain_kg": 83.479198,
                "operator_effective_deposit_delta_kg": 47.556427,
                "operator_cut_valid": 1,
            },
            profile_token=None,
            exemplar_ids=("unsafe_exemplar",),
            distance=0.0,
        )


def test_final_raw_field_guard_rejects_exemplar_before_state_side_effect() -> None:
    prior = json.loads(STRICT_PRIOR.read_text(encoding="utf-8"))
    corridor = CoverageCorridorState(
        corridor_id=2,
        cell_id=2,
        entry_x_m=0.615094,
        entry_z_m=-0.439306,
        exit_x_m=0.516926,
        exit_z_m=-0.276453,
    )
    state = CoverageRuntimeState(coverage_corridors=[corridor])
    service = CoveragePlanningFactService(
        config=CoveragePlanningFactConfig(
            prior_fields=dict(prior["fields"]),
            cut_direction_percentile="p50",
            cut_length_percentile="p50",
            cut_depth_percentile="p90",
            payload_percentile="p90",
            wall_safety=CoverageWallSafetyConfig.from_mapping(WALL_CONFIG),
        ),
        coverage_state=state,
        state_exemplar_planner=_UnsafeExemplarPlanner(),
        coverage_state_exemplars_by_cell={2: [{"id": "unsafe_exemplar"}]},
        observation_facts=lambda obs: SimpleNamespace(
            env_state=np.asarray(obs["env_state"], dtype=np.float32)
        ),
        first_dig_qpos_delta=lambda _corridor, _obs: np.zeros(4, dtype=np.float32),
    )

    with pytest.raises(CoverageFinalWallSafetyError):
        service.raw_fields(corridor, obs=_wall_obs(), update_state=True)

    assert state.coverage_active_state_exemplar_ids == []
    assert state.coverage_active_state_exemplar_profile_token is None


def test_final_raw_field_guard_rejects_exhausted_physical_swept_cell() -> None:
    prior = json.loads(STRICT_PRIOR.read_text(encoding="utf-8"))
    corridor = CoverageCorridorState(
        corridor_id=4,
        cell_id=4,
        entry_x_m=0.635571,
        entry_z_m=0.549191,
        exit_x_m=0.41758,
        exit_z_m=0.717073,
        cut_depth_peak_m=0.364648,
    )
    state = CoverageRuntimeState(coverage_corridors=[corridor])
    state.mark_depth_exhausted_physical_cell(5)
    disabled_exemplars = CoverageStateExemplarPlannerConfig(
        enabled=False,
        path="",
        dig_cut_prior_path="",
        k=1,
        removed_depth_scale_m=0.12,
        target_cell_weight=2.0,
        temperature=0.35,
        skip_rejected=True,
    )
    service = CoveragePlanningFactService(
        config=CoveragePlanningFactConfig(
            prior_fields=dict(prior["fields"]),
            cut_direction_percentile="p50",
            cut_length_percentile="p50",
            cut_depth_percentile="p90",
            payload_percentile="p90",
            wall_safety=CoverageWallSafetyConfig.from_mapping(WALL_CONFIG),
        ),
        coverage_state=state,
        state_exemplar_planner=CoverageStateExemplarPlanner(
            disabled_exemplars
        ),
        coverage_state_exemplars_by_cell={},
        observation_facts=lambda obs: SimpleNamespace(
            env_state=np.asarray(obs["env_state"], dtype=np.float32)
        ),
        first_dig_qpos_delta=lambda _corridor, _obs: np.zeros(
            4,
            dtype=np.float32,
        ),
    )

    with pytest.raises(CoverageFinalWallSafetyError) as error:
        service.raw_fields(corridor, obs=_wall_obs(), update_state=True)

    assert error.value.evaluation.rejection_reason == (
        "swept_footprint_intersects_depth_exhausted_cell"
    )
    assert error.value.evaluation.depth_exhausted_swept_cell_ids == (5,)


def test_enabled_wall_safety_requires_typed_runtime_safety_and_no_fallback() -> None:
    with pytest.raises(ValueError, match="requires the safety interlock"):
        PrimitivePlannerAdapterConfigNormalizer.normalize(
            PrimitivePlannerAdapterConfigInputs(
                dig_cut_planner={
                    "enabled": True,
                    "mode": "operator_prior_sweep_belief",
                    "prior_path": str(STRICT_PRIOR),
                    "fallback_mode": "raise",
                    "coverage": {"wall_safety": WALL_CONFIG},
                },
                box_emptying={"safety_enabled": False},
            )
        )

    with pytest.raises(ValueError, match="forbids planner fallback"):
        PrimitivePlannerAdapterConfigNormalizer.normalize(
            PrimitivePlannerAdapterConfigInputs(
                dig_cut_planner={
                    "enabled": True,
                    "mode": "operator_prior_sweep_belief",
                    "prior_path": str(STRICT_PRIOR),
                    "fallback_mode": "conservative_pose",
                    "coverage": {"wall_safety": WALL_CONFIG},
                },
                box_emptying={"safety_enabled": True},
            )
        )


def test_no_safe_corridor_skips_act_then_zero_action_acknowledges_terminal() -> None:
    dig_policy = _RecordingPolicy(0)
    policy = _wall_policy(dig_policy=dig_policy)

    first = policy.predict(_wall_obs(half_scale=0.40, step_id=10))
    assert (
        policy._coverage_runtime_state().coverage_terminal_stop_requested
        is False
    )
    second = policy.predict(_wall_obs(half_scale=0.40, step_id=11))

    np.testing.assert_array_equal(first, np.zeros(4, dtype=np.float32))
    np.testing.assert_array_equal(second, np.zeros(4, dtype=np.float32))
    assert dig_policy.call_count == 0
    assert policy._coverage_runtime_state().coverage_terminal_stop_requested is True
    assert policy._coverage_runtime_state().coverage_terminal_stop_reason == (
        "box_safety:no_wall_safe_corridor"
    )
    assert policy.debug_state()["box_safety_neutral_acknowledged"] is True


def test_return_ahead_no_safe_corridor_also_skips_return_act() -> None:
    return_policy = _RecordingPolicy(3)
    policy = _wall_policy(return_policy=return_policy)
    policy._set_skill("return", "unit_test_return_ahead_no_safe")

    first = policy.predict(_wall_obs(half_scale=0.40, step_id=20))
    assert (
        policy._coverage_runtime_state().coverage_terminal_stop_requested
        is False
    )
    second = policy.predict(_wall_obs(half_scale=0.40, step_id=21))

    np.testing.assert_array_equal(first, np.zeros(4, dtype=np.float32))
    np.testing.assert_array_equal(second, np.zeros(4, dtype=np.float32))
    assert return_policy.call_count == 0
    assert policy._coverage_runtime_state().coverage_terminal_stop_requested is True


def test_exact_return_envelope_timeout_neutralizes_before_return_act() -> None:
    return_policy = _RecordingPolicy(3)
    policy = _wall_policy(return_policy=return_policy)
    policy._set_skill("return", "unit_test_exact_return_timeout")
    policy._primitive_token_runtime_state().pending_dig_exact_start_contract_required = (
        True
    )
    policy._primitive_return_runtime_state().return_step_count = int(
        policy.return_max_steps
    )

    first = policy.predict(_wall_obs(step_id=24))
    second = policy.predict(_wall_obs(step_id=25))

    np.testing.assert_array_equal(first, np.zeros(4, dtype=np.float32))
    np.testing.assert_array_equal(second, np.zeros(4, dtype=np.float32))
    assert return_policy.call_count == 0
    assert policy._coverage_runtime_state().coverage_terminal_stop_requested is True
    assert policy._coverage_runtime_state().coverage_terminal_stop_reason == (
        "box_safety:exact_return_start_envelope_timeout"
    )
    assert policy.debug_state()["box_safety_neutral_acknowledged"] is True


def test_existing_safety_event_preempts_wall_planning_until_neutral_ack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dig_policy = _RecordingPolicy(0)
    policy = _wall_policy(dig_policy=dig_policy)
    calls = {"dig": 0, "return": 0}
    token_runtime = SimpleNamespace(
        ensure_dig_cut_plan_for_cycle=(
            lambda _obs: calls.__setitem__("dig", calls["dig"] + 1)
        ),
        ensure_return_target_plan_for_cycle=(
            lambda _obs: calls.__setitem__("return", calls["return"] + 1)
        ),
    )
    monkeypatch.setattr(
        policy,
        "_primitive_token_observation_runtime",
        lambda: token_runtime,
    )
    policy._box_safety_interlock().request_neutral_event(
        step_id=30,
        reason="timeout",
        terminal=True,
    )

    action = policy.predict(_wall_obs(step_id=31))

    np.testing.assert_array_equal(action, np.zeros(4, dtype=np.float32))
    assert calls == {"dig": 0, "return": 0}
    assert dig_policy.call_count == 0
