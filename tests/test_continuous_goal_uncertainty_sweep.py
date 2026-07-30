from __future__ import annotations

import math
from typing import Any

from testbed.eval.continuous_goal_uncertainty_sweep import (
    REQUIRED_WITNESS_KEYS,
    SweepSampleContext,
    evaluate_continuous_goal_uncertainty_sweep,
)


def _path(value: float = 0.0) -> list[list[float]]:
    return [[value, value, value, value] for _ in range(64)]


def _bounds(value: float = 0.0) -> list[list[float]]:
    return [[value, value, value, value] for _ in range(64)]


def _clearances(value: float) -> dict[str, float]:
    return {key: value for key in REQUIRED_WITNESS_KEYS}


def test_sweep_checks_nominal_and_all_16_uncertainty_corners_per_node() -> None:
    calls: list[tuple[tuple[float, ...], SweepSampleContext]] = []
    bounds = [[0.1, 0.2, 0.3, 0.4] for _ in range(64)]

    def witness(
        qpos: tuple[float, ...],
        context: SweepSampleContext,
    ) -> dict[str, float]:
        calls.append((qpos, context))
        return _clearances(0.31)

    result = evaluate_continuous_goal_uncertainty_sweep(
        nominal_qpos_path=_path(),
        qpos_abs_error_bound=bounds,
        witness_callback=witness,
    )

    assert result.passed
    assert result.path_node_count == 64
    assert result.pose_evaluation_count == 64 * 17
    assert result.witness_evaluation_count == 64 * 17 * 12
    first_node = calls[:17]
    assert first_node[0][1].variant == "nominal"
    assert first_node[0][0] == (0.0, 0.0, 0.0, 0.0)
    assert {entry[1].corner_signs for entry in first_node[1:]} == {
        (a, b, c, d)
        for a in (-1, 1)
        for b in (-1, 1)
        for c in (-1, 1)
        for d in (-1, 1)
    }
    assert result.conservative_clearance_m == 0.25
    assert result.act_tracking_margin_m == 0.05
    assert result.predictor_uncertainty_tracking_credit_m == 0.0


def test_sweep_adaptively_interpolates_nominal_and_bound_changes() -> None:
    path = _path()
    bounds = _bounds()
    for row in path[1:]:
        row[0] = 0.11
    for row in bounds[1:]:
        row[1] = 0.11

    result = evaluate_continuous_goal_uncertainty_sweep(
        nominal_qpos_path=path,
        qpos_abs_error_bound=bounds,
        witness_callback=lambda _qpos, _context: _clearances(0.40),
        max_joint_step=0.05,
    )

    assert result.passed
    assert result.interpolated_node_count == 2
    assert result.path_node_count == 66
    assert result.pose_evaluation_count == 66 * 17


def test_sweep_applies_all_three_clearance_terms_without_margin_substitution() -> None:
    result = evaluate_continuous_goal_uncertainty_sweep(
        nominal_qpos_path=_path(),
        qpos_abs_error_bound=_bounds(0.20),
        witness_callback=lambda _qpos, _context: _clearances(0.299),
    )

    assert not result.passed
    assert result.reason == "hard_clearance_not_met"
    assert math.isclose(result.conservative_clearance_m or 0.0, 0.239)
    assert result.required_hard_clearance_m == 0.24
    assert result.predictor_uncertainty_tracking_credit_m == 0.0


def test_sweep_saves_the_worst_link_wall_witness() -> None:
    def witness(
        _qpos: tuple[float, ...],
        context: SweepSampleContext,
    ) -> dict[str, float]:
        values = _clearances(0.50)
        if (
            context.path_index == 17
            and context.variant == "uncertainty_corner"
            and context.corner_index == 6
        ):
            values["stick:z_max"] = 0.305
        return values

    result = evaluate_continuous_goal_uncertainty_sweep(
        nominal_qpos_path=_path(),
        qpos_abs_error_bound=_bounds(0.01),
        witness_callback=witness,
    )

    assert result.passed
    assert result.worst_witness is not None
    assert result.worst_witness.link == "stick"
    assert result.worst_witness.wall == "z_max"
    assert result.worst_witness.path_index == 17
    assert result.worst_witness.corner_index == 6
    assert result.worst_witness.clearance_m == 0.305


def test_sweep_fails_closed_for_nonfinite_input_or_missing_witness() -> None:
    nonfinite = _path()
    nonfinite[3][2] = float("nan")
    invalid_input = evaluate_continuous_goal_uncertainty_sweep(
        nominal_qpos_path=nonfinite,
        qpos_abs_error_bound=_bounds(),
        witness_callback=lambda _qpos, _context: _clearances(1.0),
    )
    assert not invalid_input.passed
    assert invalid_input.reason == "nominal_qpos_path_nonfinite"
    assert invalid_input.pose_evaluation_count == 0

    missing_witness = evaluate_continuous_goal_uncertainty_sweep(
        nominal_qpos_path=_path(),
        qpos_abs_error_bound=_bounds(),
        witness_callback=lambda _qpos, _context: {
            key: 1.0 for key in REQUIRED_WITNESS_KEYS[:-1]
        },
    )
    assert not missing_witness.passed
    assert missing_witness.reason == "witness_inventory_incomplete"
    assert missing_witness.worst_witness is None


def test_sweep_fails_closed_for_negative_bound_and_callback_nonfinite() -> None:
    bounds = _bounds()
    bounds[0][0] = -0.01
    negative_bound = evaluate_continuous_goal_uncertainty_sweep(
        nominal_qpos_path=_path(),
        qpos_abs_error_bound=bounds,
        witness_callback=lambda _qpos, _context: _clearances(1.0),
    )
    assert not negative_bound.passed
    assert negative_bound.reason == "qpos_abs_error_bound_negative"

    nonfinite_witness = evaluate_continuous_goal_uncertainty_sweep(
        nominal_qpos_path=_path(),
        qpos_abs_error_bound=_bounds(),
        witness_callback=lambda _qpos, _context: _clearances(float("inf")),
    )
    assert not nonfinite_witness.passed
    assert nonfinite_witness.reason == "witness_clearance_nonfinite"


def test_sweep_fails_closed_for_malformed_matrix_container() -> None:
    malformed: Any = None
    result = evaluate_continuous_goal_uncertainty_sweep(
        nominal_qpos_path=malformed,
        qpos_abs_error_bound=_bounds(),
        witness_callback=lambda _qpos, _context: _clearances(1.0),
    )

    assert not result.passed
    assert result.reason == "nominal_qpos_path_shape_invalid"
