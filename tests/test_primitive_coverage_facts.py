from __future__ import annotations

import math
from dataclasses import fields
from typing import Any

import numpy as np
import pytest

from testbed.data.schema import (
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX,
    ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
    ENV_STATE_DIG_AREA_TARGET_DEPTH_START_IDX,
)
from testbed.planner.primitive_capabilities import PrimitiveObservationFacts
from testbed.planner.primitive_coverage import CoverageCorridorState
from testbed.planner.primitive_coverage_exemplars import (
    CoverageStateExemplarPlanInputs,
    CoverageStateExemplarPlanResult,
)
from testbed.planner.primitive_coverage_facts import (
    CoveragePlanningFactConfig,
    CoveragePlanningFactService,
)
from testbed.planner.primitive_coverage_state import CoverageRuntimeState
from tests.test_agx_primitives_v2_2 import (
    _RecordingPolicy,
    _coverage_obs,
    _coverage_planner_policy,
)


def _prior_fields() -> dict[str, dict[str, float]]:
    return {
        "entry_x_m": {"p10": 0.0, "p50": 0.5, "p90": 1.0},
        "entry_z_m": {"p10": 0.0, "p50": 0.5, "p90": 1.0},
        "exit_x_m": {"p10": 0.0, "p50": 0.5, "p90": 1.0},
        "exit_z_m": {"p10": 0.0, "p50": 0.5, "p90": 1.0},
        "cut_direction_x": {"p10": -1.0, "p50": -0.5, "p90": 0.0},
        "cut_direction_z": {"p10": 0.0, "p50": 0.5, "p90": 1.0},
        "cut_length_m": {"p10": 0.3, "p50": 0.8, "p90": 1.3},
        "cut_depth_peak_m": {"p10": 0.02, "p50": 0.08, "p90": 0.12},
        "payload_gain_kg": {"p10": 10.0, "p50": 20.0, "p90": 30.0},
        "effective_deposit_delta_kg": {"p10": 5.0, "p50": 15.0, "p90": 25.0},
    }


def _config() -> CoveragePlanningFactConfig:
    return CoveragePlanningFactConfig(
        prior_fields=_prior_fields(),
        cut_direction_percentile="p50",
        cut_length_percentile="p50",
        cut_depth_percentile="p50",
        payload_percentile="p50",
    )


def _corridor(**overrides: Any) -> CoverageCorridorState:
    values = {
        "corridor_id": 4,
        "cell_id": 0,
        "entry_x_m": 2.0,
        "entry_z_m": -1.0,
        "exit_x_m": -5.0,
        "exit_z_m": 4.0,
        "cut_depth_peak_m": float("nan"),
        "payload_gain_kg": 40.0,
        "effective_deposit_delta_kg": float("nan"),
    }
    values.update(overrides)
    return CoverageCorridorState(**values)


def _env_state(
    *,
    target_depth: float = 0.08,
    removed_depth: float = 0.03,
    bucket_pose: tuple[float, float, float] = (0.0, 0.0, 0.0),
    bucket_tip: tuple[float, float, float] = (1.0, 0.0, 0.0),
) -> np.ndarray:
    env_state = np.zeros(64, dtype=np.float32)
    env_state[ENV_STATE_DIG_AREA_TARGET_DEPTH_START_IDX] = float(target_depth)
    env_state[ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX] = float(removed_depth)
    env_state[ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX] = 1.0
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX] = float(bucket_pose[0])
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX] = float(bucket_pose[1])
    env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX] = float(bucket_pose[2])
    env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX] = float(bucket_tip[0])
    env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_Y_IDX] = float(bucket_tip[1])
    env_state[ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX] = float(bucket_tip[2])
    return env_state


class _FakeStateExemplarPlanner:
    def __init__(
        self,
        result: CoverageStateExemplarPlanResult | None,
    ) -> None:
        self.result = result
        self.inputs: list[CoverageStateExemplarPlanInputs] = []

    def plan(
        self,
        inputs: CoverageStateExemplarPlanInputs,
    ) -> CoverageStateExemplarPlanResult | None:
        self.inputs.append(inputs)
        return self.result


def _service(
    *,
    state: CoverageRuntimeState | None = None,
    planner: _FakeStateExemplarPlanner | None = None,
    qpos_delta: np.ndarray | None = None,
) -> CoveragePlanningFactService:
    return CoveragePlanningFactService(
        config=_config(),
        coverage_state=state or CoverageRuntimeState(),
        state_exemplar_planner=(
            planner if planner is not None else _FakeStateExemplarPlanner(None)
        ),
        coverage_state_exemplars_by_cell={0: [{"exemplar_id": "cell0_a"}]},
        observation_facts=(
            lambda obs: PrimitiveObservationFacts.from_obs(obs, action_dim=4)
        ),
        first_dig_qpos_delta=(
            lambda corridor, obs: np.asarray(
                [0.25, 0.5] if qpos_delta is None else qpos_delta,
                dtype=np.float32,
            )
        ),
    )


def test_service_uses_typed_observation_facts_not_observation_callbacks() -> None:
    names = {field.name for field in fields(CoveragePlanningFactService)}

    assert "observation_facts" in names
    assert "env_state" not in names
    assert "bucket_tip_dig_area_pose" not in names


def test_entry_distance_uses_typed_bucket_tip_fallback_to_bucket_pose() -> None:
    service = _service()
    corridor = _corridor(entry_x_m=1.5, entry_z_m=1.0)
    obs = {
        "env_state": _env_state(
            bucket_pose=(3.0, 0.0, 4.0),
            bucket_tip=(float("nan"), float("nan"), float("nan")),
        )
    }

    assert service.entry_distance_m(corridor, obs) == pytest.approx(
        math.hypot(1.5, 3.0)
    )


def test_raw_fields_fallback_from_corridor_prior_preserves_clamp_and_percentiles() -> None:
    raw_fields = _service().raw_fields(_corridor(), obs=None)

    assert raw_fields["operator_entry_x_m"] == pytest.approx(1.0)
    assert raw_fields["operator_entry_z_m"] == pytest.approx(0.0)
    assert raw_fields["operator_exit_x_m"] == pytest.approx(0.0)
    assert raw_fields["operator_exit_z_m"] == pytest.approx(1.0)
    assert raw_fields["operator_cut_length_m"] == pytest.approx(1.3)
    assert raw_fields["operator_cut_depth_peak_m"] == pytest.approx(0.08)
    assert raw_fields["operator_cut_payload_gain_kg"] == pytest.approx(30.0)
    assert raw_fields["operator_effective_deposit_delta_kg"] == pytest.approx(15.0)
    assert raw_fields["operator_cut_valid"] == 1


def test_state_conditioned_plan_overrides_raw_fields_and_writes_active_exemplar() -> None:
    state = CoverageRuntimeState()
    profile = np.asarray([1.0, 2.0, 3.0], dtype=np.float64)
    result = CoverageStateExemplarPlanResult(
        raw_fields={"operator_entry_x_m": 0.44, "operator_cut_valid": 1},
        profile_token=profile,
        exemplar_ids=["cell0_a"],
        distance=0.125,
    )
    planner = _FakeStateExemplarPlanner(result)
    corridor = _corridor()
    service = _service(state=state, planner=planner)

    raw_fields = service.raw_fields(corridor, obs={"env_state": _env_state()}, update_state=True)
    plan = service.state_conditioned_plan(
        corridor,
        {"env_state": _env_state()},
        update_state=False,
    )

    assert raw_fields == {"operator_entry_x_m": 0.44, "operator_cut_valid": 1}
    assert plan is not None
    assert plan["profile_token"] is profile
    assert state.coverage_active_state_exemplar_ids == ["cell0_a"]
    assert state.coverage_active_state_exemplar_distance == pytest.approx(0.125)
    assert state.coverage_active_state_exemplar_profile_token is not profile
    assert state.coverage_active_state_exemplar_profile_token is not None
    assert state.coverage_active_state_exemplar_profile_token.dtype == np.float32
    assert corridor.state_exemplar_id == "cell0_a"
    assert corridor.state_exemplar_distance == pytest.approx(0.125)
    assert planner.inputs[0].rejected_exemplar_ids is state.coverage_rejected_state_exemplar_ids


def test_selection_facts_project_remaining_depth_entry_distance_qpos_and_exemplar() -> None:
    result = CoverageStateExemplarPlanResult(
        raw_fields={"operator_entry_x_m": 0.44, "operator_cut_valid": 1},
        profile_token=None,
        exemplar_ids=["cell0_a", "cell0_b"],
        distance=0.25,
    )
    corridor = _corridor(entry_x_m=1.5, entry_z_m=0.4)
    state = CoverageRuntimeState(coverage_corridors=[corridor])
    service = _service(
        state=state,
        planner=_FakeStateExemplarPlanner(result),
        qpos_delta=np.asarray([0.125, 0.25], dtype=np.float32),
    )
    obs = {"env_state": _env_state(target_depth=0.11, removed_depth=0.04)}

    facts = service.selection_facts(obs)

    fact = facts[int(corridor.corridor_id)]
    assert fact.remaining_depth_m == pytest.approx(0.07)
    assert fact.first_dig_entry_distance_m == pytest.approx(math.hypot(0.5, 0.4))
    np.testing.assert_allclose(fact.first_dig_qpos_delta, [0.125, 0.25])
    assert fact.state_exemplar_distance == pytest.approx(0.25)
    assert fact.state_exemplar_id == "cell0_a"


def test_policy_facades_delegate_to_shared_coverage_fact_service() -> None:
    policy = _coverage_planner_policy(
        dig_policy=_RecordingPolicy(0),
        coverage_extra={"use_env_removed_depth": True},
    )
    policy._ensure_coverage_corridors()
    corridor = policy._coverage_corridors[0]
    obs = _coverage_obs(
        mass=0.0,
        dig_distance=0.0,
        removed_cell0=0.02,
        bucket_tip_pose=(float(corridor.entry_x_m), 0.0, float(corridor.entry_z_m)),
    )

    service = policy._coverage_planning_fact_service()
    facade_raw_fields = policy._coverage_raw_fields(corridor, obs=obs)
    service_raw_fields = service.raw_fields(corridor, obs=obs)
    facade_facts = policy._coverage_selection_facts(obs, [corridor])
    service_facts = service.selection_facts(obs, [corridor])

    assert service.coverage_state is policy._coverage_state
    assert facade_raw_fields == service_raw_fields
    assert facade_facts.keys() == service_facts.keys()
    fact = facade_facts[int(corridor.corridor_id)]
    expected = service_facts[int(corridor.corridor_id)]
    assert fact.remaining_depth_m == pytest.approx(expected.remaining_depth_m)
    assert fact.first_dig_entry_distance_m == pytest.approx(
        expected.first_dig_entry_distance_m
    )
    np.testing.assert_allclose(
        fact.first_dig_qpos_delta,
        expected.first_dig_qpos_delta,
    )
