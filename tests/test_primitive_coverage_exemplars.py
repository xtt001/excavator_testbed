from __future__ import annotations

import json
import math

import numpy as np
import pytest

from testbed.data.dig_depth_profile_v2_4 import DIG_DEPTH_PROFILE_TOKEN_DIM
from testbed.data.schema import ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX
from testbed.planner.primitive_coverage import CoverageCorridorState
from testbed.planner.primitive_coverage_exemplars import (
    CoverageStateExemplarPlanInputs,
    CoverageStateExemplarPlanner,
    CoverageStateExemplarPlannerConfig,
)
from tests.test_agx_primitives_v2_2 import (
    _RecordingPolicy,
    _coverage_obs,
    _coverage_planner_policy,
)


def _config(**overrides: object) -> CoverageStateExemplarPlannerConfig:
    values = {
        "enabled": True,
        "path": "",
        "dig_cut_prior_path": "",
        "k": 2,
        "removed_depth_scale_m": 0.1,
        "target_cell_weight": 2.0,
        "temperature": 0.5,
        "skip_rejected": True,
    }
    values.update(overrides)
    return CoverageStateExemplarPlannerConfig(**values)


def _corridor(cell_id: int = 1) -> CoverageCorridorState:
    return CoverageCorridorState(
        corridor_id=7,
        cell_id=int(cell_id),
        entry_x_m=0.1,
        entry_z_m=0.2,
        exit_x_m=0.3,
        exit_z_m=0.4,
    )


def _raw_fields(depth: float = 0.08) -> dict[str, float | int]:
    return {
        "operator_entry_x_m": 0.9,
        "operator_entry_y_m": -0.1,
        "operator_entry_z_m": -0.3,
        "operator_exit_x_m": -0.1,
        "operator_exit_y_m": -0.2,
        "operator_exit_z_m": -0.25,
        "operator_cut_direction_x": -1.0,
        "operator_cut_direction_y": 0.0,
        "operator_cut_direction_z": 0.0,
        "operator_cut_length_m": 1.0,
        "operator_cut_depth_peak_m": float(depth),
        "operator_cut_payload_gain_kg": 55.0,
        "operator_effective_deposit_delta_kg": 45.0,
        "operator_cut_valid": 1,
    }


def _env_state_with_removed_depth(values: list[float]) -> np.ndarray:
    env_state = np.zeros(ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX + 6, dtype=np.float32)
    env_state[
        ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX:
        ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX + 6
    ] = np.asarray(values, dtype=np.float32)
    return env_state


def test_disabled_planner_returns_no_exemplars_and_no_plan() -> None:
    planner = CoverageStateExemplarPlanner(_config(enabled=False))

    assert planner.load_exemplars() == {}
    assert (
        planner.plan(
            CoverageStateExemplarPlanInputs(
                corridor=_corridor(),
                env_state=_env_state_with_removed_depth([0.0] * 6),
                exemplars_by_cell={1: [{"raw_fields": _raw_fields()}]},
                rejected_exemplar_ids=set(),
            )
        )
        is None
    )


def test_load_exemplars_preserves_legacy_path_errors_and_validation(tmp_path) -> None:
    with pytest.raises(ValueError, match="enabled=true requires a path"):
        CoverageStateExemplarPlanner(_config(path="")).load_exemplars()

    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text(json.dumps({"exemplars": {"not": "a list"}}), encoding="utf-8")
    with pytest.raises(ValueError, match="must contain an exemplars list"):
        CoverageStateExemplarPlanner(_config(path=str(invalid_path))).load_exemplars()

    empty_path = tmp_path / "empty.json"
    empty_path.write_text(json.dumps({"exemplars": [{"cell_id": 99}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="has no usable rows"):
        CoverageStateExemplarPlanner(_config(path=str(empty_path))).load_exemplars()


def test_removed_depth_grid_preserves_length_finite_and_clipping_behavior() -> None:
    planner = CoverageStateExemplarPlanner(_config())

    assert planner.removed_depth_grid(np.zeros(3, dtype=np.float32)) is None

    nonfinite = _env_state_with_removed_depth([0.0, float("nan"), 0.0, 0.0, 0.0, 0.0])
    assert planner.removed_depth_grid(nonfinite) is None

    grid = planner.removed_depth_grid(
        _env_state_with_removed_depth([-0.2, 0.05, 0.1, -1.0, 0.0, 0.2])
    )
    assert grid is not None
    assert grid.dtype == np.float32
    np.testing.assert_allclose(grid, [0.0, 0.05, 0.1, 0.0, 0.0, 0.2])


def test_distance_weights_and_rejected_filtering_keep_legacy_edges() -> None:
    planner = CoverageStateExemplarPlanner(_config(k=1, temperature=0.25))
    removed_grid = np.asarray([0.0, 0.07, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
    rejected_best = {
        "exemplar_id": "",
        "start_removed_depth_grid_m": [0.0, 0.07, 0.0, 0.0, 0.0, 0.0],
        "raw_fields": _raw_fields(0.03),
    }
    selected = {
        "exemplar_id": "keep",
        "start_removed_depth_grid_m": [0.0, 0.02, 0.0, 0.0, 0.0, 0.0],
        "raw_fields": _raw_fields(0.09),
    }

    assert planner.distance_for_grid(removed_grid, rejected_best, cell_id=1) == 0.0
    np.testing.assert_allclose(
        planner.weights([(float("nan"), rejected_best), (1.0, selected)]),
        [0.5, 0.5],
    )

    result = planner.plan(
        CoverageStateExemplarPlanInputs(
            corridor=_corridor(cell_id=1),
            env_state=_env_state_with_removed_depth([0.0, 0.07, 0.0, 0.0, 0.0, 0.0]),
            exemplars_by_cell={1: [rejected_best, selected]},
            rejected_exemplar_ids={""},
        )
    )

    assert result is not None
    assert result.exemplar_ids == ["keep"]
    assert result.raw_fields["operator_cut_depth_peak_m"] == pytest.approx(0.09)


def test_weighted_raw_fields_and_profile_token_preserve_dtype_and_valid_flag() -> None:
    profile_a = np.linspace(0.1, 0.8, DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float32)
    profile_b = np.linspace(0.2, 0.9, DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float32)
    profile_a[-1] = 0.0
    profile_b[-1] = 0.0
    selected = [
        (
            0.0,
            {
                "raw_fields": _raw_fields(0.04),
                "dig_depth_profile_token": profile_a.tolist(),
            },
        ),
        (
            0.0,
            {
                "raw_fields": _raw_fields(0.08),
                "dig_depth_profile_token": profile_b.tolist(),
            },
        ),
    ]
    planner = CoverageStateExemplarPlanner(_config())

    raw_fields = planner.weighted_raw_fields(selected)
    profile_token = planner.weighted_profile_token(selected)

    assert raw_fields["operator_cut_valid"] == 1
    assert raw_fields["operator_cut_depth_peak_m"] == pytest.approx(0.06)
    assert profile_token is not None
    assert profile_token.dtype == np.float32
    assert profile_token.shape == (DIG_DEPTH_PROFILE_TOKEN_DIM,)
    assert float(profile_token[-1]) == 1.0

    profile_a[0] = 99.0
    assert float(profile_token[0]) != 99.0


def test_policy_state_conditioned_plan_facade_controls_runtime_writeback(tmp_path) -> None:
    shallow = np.linspace(0.1, 0.8, DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float32)
    deep = np.linspace(0.2, 0.9, DIG_DEPTH_PROFILE_TOKEN_DIM, dtype=np.float32)
    shallow[-1] = 1.0
    deep[-1] = 1.0
    exemplar_path = tmp_path / "state_exemplars.json"
    exemplar_path.write_text(
        json.dumps(
            {
                "exemplars": [
                    {
                        "exemplar_id": "cell1_shallow",
                        "cell_id": 1,
                        "start_removed_depth_grid_m": [0, 0, 0, 0, 0, 0],
                        "raw_fields": _raw_fields(0.04),
                        "dig_depth_profile_token": shallow.tolist(),
                    },
                    {
                        "exemplar_id": "cell1_deep",
                        "cell_id": 1,
                        "start_removed_depth_grid_m": [0, 0.06, 0, 0, 0, 0],
                        "raw_fields": _raw_fields(0.09),
                        "dig_depth_profile_token": deep.tolist(),
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    policy = _coverage_planner_policy(
        dig_policy=_RecordingPolicy(0),
        coverage_extra={
            "state_conditioned_exemplars": {
                "enabled": True,
                "path": str(exemplar_path),
                "k": 1,
                "removed_depth_scale_m": 0.12,
                "target_cell_weight": 2.0,
            },
        },
    )
    corridor = _corridor(cell_id=1)
    obs = _coverage_obs(mass=0.0, dig_distance=0.0)
    env_state = np.asarray(obs["env_state"], dtype=np.float32)
    env_state[
        ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX:
        ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX + 6
    ] = np.asarray([0.0, 0.06, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
    obs["env_state"] = env_state

    no_write = policy._coverage_state_conditioned_plan(
        corridor,
        obs,
        update_state=False,
    )
    assert no_write is not None
    assert no_write["exemplar_ids"] == ["cell1_deep"]
    assert policy._coverage_state.coverage_active_state_exemplar_ids == []
    assert corridor.state_exemplar_id == ""

    with_write = policy._coverage_state_conditioned_plan(
        corridor,
        obs,
        update_state=True,
    )

    assert with_write is not None
    assert policy._coverage_state.coverage_active_state_exemplar_ids == [
        "cell1_deep"
    ]
    assert policy._coverage_state.coverage_active_state_exemplar_distance == pytest.approx(
        0.0
    )
    assert policy._coverage_state.coverage_active_state_exemplar_profile_token is not None
    assert policy._coverage_state.coverage_active_state_exemplar_profile_token.dtype == (
        np.float32
    )
    assert corridor.state_exemplar_id == "cell1_deep"
    assert corridor.state_exemplar_distance == pytest.approx(0.0)
