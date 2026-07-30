"""Fail-closed 3D clearance evaluation for continuous-goal qpos tubes.

The predictor uncertainty is materialized as sixteen explicit qpos corners.
It is never converted into credit against the independent ACT tracking margin.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

PATH_NODE_COUNT = 64
QPOS_DIM = 4
INTERPOLATION_MARGIN_M = 0.01
ACT_TRACKING_MARGIN_M = 0.05
HARD_CLEARANCE_M = 0.24
DEFAULT_MAX_JOINT_STEP = 0.05

LINKS = ("boom", "stick", "bucket")
WALLS = ("x_min", "x_max", "z_min", "z_max")
REQUIRED_WITNESS_KEYS = tuple(
    f"{link}:{wall}" for link in LINKS for wall in WALLS
)
_CORNER_SIGNS = tuple(itertools.product((-1, 1), repeat=QPOS_DIM))


@dataclass(frozen=True)
class SweepSampleContext:
    """Identity of one nominal or uncertainty-corner pose evaluation."""

    path_index: int
    left_path_index: int
    right_path_index: int
    interpolation_fraction: float
    variant: str
    corner_index: int | None
    corner_signs: tuple[int, int, int, int] | None


@dataclass(frozen=True)
class WorstWitnessEvidence:
    """The smallest observed link-to-wall clearance and its pose lineage."""

    link: str
    wall: str
    clearance_m: float
    qpos: tuple[float, float, float, float]
    path_index: int
    left_path_index: int
    right_path_index: int
    interpolation_fraction: float
    variant: str
    corner_index: int | None
    corner_signs: tuple[int, int, int, int] | None


@dataclass(frozen=True)
class UncertaintySweepResult:
    """Serializable evaluation outcome for one 64-point predictor path."""

    passed: bool
    reason: str
    original_path_node_count: int
    path_node_count: int
    interpolated_node_count: int
    pose_evaluation_count: int
    witness_evaluation_count: int
    minimum_witness_clearance_m: float | None
    conservative_clearance_m: float | None
    interpolation_margin_m: float
    act_tracking_margin_m: float
    required_hard_clearance_m: float
    predictor_uncertainty_tracking_credit_m: float
    worst_witness: WorstWitnessEvidence | None


WitnessCallback = Callable[
    [tuple[float, float, float, float], SweepSampleContext],
    Mapping[str, float],
]


def evaluate_continuous_goal_uncertainty_sweep(
    *,
    nominal_qpos_path: Sequence[Sequence[float]],
    qpos_abs_error_bound: Sequence[Sequence[float]],
    witness_callback: WitnessCallback,
    max_joint_step: float = DEFAULT_MAX_JOINT_STEP,
) -> UncertaintySweepResult:
    """Evaluate nominal poses and all sixteen qpos-tube corners.

    Interpolation is adaptive.  For each segment, the subdivision count bounds
    both nominal motion and the change in the absolute-error envelope:
    ``abs(delta nominal) + abs(delta bound) <= max_joint_step``.
    """

    nominal, reason = _validated_matrix(
        nominal_qpos_path,
        label="nominal_qpos_path",
        nonnegative=False,
    )
    if reason is not None:
        return _failed(reason)
    bounds, reason = _validated_matrix(
        qpos_abs_error_bound,
        label="qpos_abs_error_bound",
        nonnegative=True,
    )
    if reason is not None:
        return _failed(reason)
    try:
        step = float(max_joint_step)
    except (TypeError, ValueError, OverflowError):
        return _failed("max_joint_step_invalid")
    if not math.isfinite(step) or step <= 0.0:
        return _failed("max_joint_step_invalid")

    assert nominal is not None
    assert bounds is not None
    interpolated = _interpolated_nodes(nominal, bounds, step)
    worst: WorstWitnessEvidence | None = None
    pose_count = 0
    witness_count = 0
    for node in interpolated:
        nominal_context = SweepSampleContext(
            path_index=node.path_index,
            left_path_index=node.left_path_index,
            right_path_index=node.right_path_index,
            interpolation_fraction=node.interpolation_fraction,
            variant="nominal",
            corner_index=None,
            corner_signs=None,
        )
        pose_count += 1
        values, reason = _call_witness(
            witness_callback,
            node.nominal,
            nominal_context,
        )
        if reason is not None:
            return _failed(
                reason,
                path_node_count=len(interpolated),
                pose_evaluation_count=pose_count,
                witness_evaluation_count=witness_count,
                worst=worst,
            )
        assert values is not None
        witness_count += len(REQUIRED_WITNESS_KEYS)
        worst = _update_worst(worst, values, node.nominal, nominal_context)

        for corner_index, signs in enumerate(_CORNER_SIGNS):
            qpos = tuple(
                node.nominal[index] + signs[index] * node.bound[index]
                for index in range(QPOS_DIM)
            )
            context = SweepSampleContext(
                path_index=node.path_index,
                left_path_index=node.left_path_index,
                right_path_index=node.right_path_index,
                interpolation_fraction=node.interpolation_fraction,
                variant="uncertainty_corner",
                corner_index=corner_index,
                corner_signs=signs,
            )
            pose_count += 1
            values, reason = _call_witness(
                witness_callback,
                qpos,
                context,
            )
            if reason is not None:
                return _failed(
                    reason,
                    path_node_count=len(interpolated),
                    pose_evaluation_count=pose_count,
                    witness_evaluation_count=witness_count,
                    worst=worst,
                )
            assert values is not None
            witness_count += len(REQUIRED_WITNESS_KEYS)
            worst = _update_worst(worst, values, qpos, context)

    assert worst is not None
    conservative = (
        worst.clearance_m
        - INTERPOLATION_MARGIN_M
        - ACT_TRACKING_MARGIN_M
    )
    passed = conservative >= HARD_CLEARANCE_M
    return UncertaintySweepResult(
        passed=passed,
        reason="passed" if passed else "hard_clearance_not_met",
        original_path_node_count=PATH_NODE_COUNT,
        path_node_count=len(interpolated),
        interpolated_node_count=len(interpolated) - PATH_NODE_COUNT,
        pose_evaluation_count=pose_count,
        witness_evaluation_count=witness_count,
        minimum_witness_clearance_m=worst.clearance_m,
        conservative_clearance_m=conservative,
        interpolation_margin_m=INTERPOLATION_MARGIN_M,
        act_tracking_margin_m=ACT_TRACKING_MARGIN_M,
        required_hard_clearance_m=HARD_CLEARANCE_M,
        predictor_uncertainty_tracking_credit_m=0.0,
        worst_witness=worst,
    )


@dataclass(frozen=True)
class _InterpolatedNode:
    nominal: tuple[float, float, float, float]
    bound: tuple[float, float, float, float]
    path_index: int
    left_path_index: int
    right_path_index: int
    interpolation_fraction: float


def _validated_matrix(
    value: Sequence[Sequence[float]],
    *,
    label: str,
    nonnegative: bool,
) -> tuple[
    tuple[tuple[float, float, float, float], ...] | None,
    str | None,
]:
    try:
        row_count = len(value)
    except (TypeError, AttributeError):
        return None, f"{label}_shape_invalid"
    if isinstance(value, (str, bytes)) or row_count != PATH_NODE_COUNT:
        return None, f"{label}_shape_invalid"
    rows: list[tuple[float, float, float, float]] = []
    for raw_row in value:
        try:
            column_count = len(raw_row)
        except (TypeError, AttributeError):
            return None, f"{label}_shape_invalid"
        if (
            isinstance(raw_row, (str, bytes))
            or column_count != QPOS_DIM
        ):
            return None, f"{label}_shape_invalid"
        try:
            row = tuple(float(item) for item in raw_row)
        except (TypeError, ValueError, OverflowError):
            return None, f"{label}_nonfinite"
        if not all(math.isfinite(item) for item in row):
            return None, f"{label}_nonfinite"
        if nonnegative and any(item < 0.0 for item in row):
            return None, f"{label}_negative"
        rows.append(row)  # type: ignore[arg-type]
    return tuple(rows), None


def _interpolated_nodes(
    nominal: tuple[tuple[float, float, float, float], ...],
    bounds: tuple[tuple[float, float, float, float], ...],
    max_joint_step: float,
) -> tuple[_InterpolatedNode, ...]:
    nodes = [
        _InterpolatedNode(
            nominal=nominal[0],
            bound=bounds[0],
            path_index=0,
            left_path_index=0,
            right_path_index=0,
            interpolation_fraction=0.0,
        )
    ]
    for left_index in range(PATH_NODE_COUNT - 1):
        right_index = left_index + 1
        envelope_step = max(
            abs(nominal[right_index][joint] - nominal[left_index][joint])
            + abs(bounds[right_index][joint] - bounds[left_index][joint])
            for joint in range(QPOS_DIM)
        )
        segment_count = max(1, math.ceil(envelope_step / max_joint_step))
        for segment_index in range(1, segment_count + 1):
            fraction = segment_index / segment_count
            is_original_node = segment_index == segment_count
            path_index = right_index if is_original_node else left_index
            nodes.append(
                _InterpolatedNode(
                    nominal=_lerp(
                        nominal[left_index],
                        nominal[right_index],
                        fraction,
                    ),
                    bound=_lerp(
                        bounds[left_index],
                        bounds[right_index],
                        fraction,
                    ),
                    path_index=path_index,
                    left_path_index=left_index,
                    right_path_index=right_index,
                    interpolation_fraction=fraction,
                )
            )
    return tuple(nodes)


def _lerp(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
    fraction: float,
) -> tuple[float, float, float, float]:
    return tuple(
        left[index] + fraction * (right[index] - left[index])
        for index in range(QPOS_DIM)
    )  # type: ignore[return-value]


def _call_witness(
    callback: WitnessCallback,
    qpos: tuple[float, float, float, float],
    context: SweepSampleContext,
) -> tuple[dict[str, float] | None, str | None]:
    try:
        raw = callback(qpos, context)
    except Exception:
        return None, "witness_callback_error"
    if not isinstance(raw, Mapping):
        return None, "witness_inventory_incomplete"
    if any(key not in raw for key in REQUIRED_WITNESS_KEYS):
        return None, "witness_inventory_incomplete"
    values: dict[str, float] = {}
    for key in REQUIRED_WITNESS_KEYS:
        try:
            value = float(raw[key])
        except (TypeError, ValueError, OverflowError):
            return None, "witness_clearance_nonfinite"
        if not math.isfinite(value):
            return None, "witness_clearance_nonfinite"
        values[key] = value
    return values, None


def _update_worst(
    previous: WorstWitnessEvidence | None,
    values: Mapping[str, float],
    qpos: tuple[float, float, float, float],
    context: SweepSampleContext,
) -> WorstWitnessEvidence:
    key = min(REQUIRED_WITNESS_KEYS, key=lambda item: values[item])
    clearance = values[key]
    if previous is not None and previous.clearance_m <= clearance:
        return previous
    link, wall = key.split(":", maxsplit=1)
    return WorstWitnessEvidence(
        link=link,
        wall=wall,
        clearance_m=clearance,
        qpos=qpos,
        path_index=context.path_index,
        left_path_index=context.left_path_index,
        right_path_index=context.right_path_index,
        interpolation_fraction=context.interpolation_fraction,
        variant=context.variant,
        corner_index=context.corner_index,
        corner_signs=context.corner_signs,
    )


def _failed(
    reason: str,
    *,
    path_node_count: int = 0,
    pose_evaluation_count: int = 0,
    witness_evaluation_count: int = 0,
    worst: WorstWitnessEvidence | None = None,
) -> UncertaintySweepResult:
    return UncertaintySweepResult(
        passed=False,
        reason=reason,
        original_path_node_count=PATH_NODE_COUNT,
        path_node_count=path_node_count,
        interpolated_node_count=max(0, path_node_count - PATH_NODE_COUNT),
        pose_evaluation_count=pose_evaluation_count,
        witness_evaluation_count=witness_evaluation_count,
        minimum_witness_clearance_m=(
            None if worst is None else worst.clearance_m
        ),
        conservative_clearance_m=None,
        interpolation_margin_m=INTERPOLATION_MARGIN_M,
        act_tracking_margin_m=ACT_TRACKING_MARGIN_M,
        required_hard_clearance_m=HARD_CLEARANCE_M,
        predictor_uncertainty_tracking_credit_m=0.0,
        worst_witness=worst,
    )
