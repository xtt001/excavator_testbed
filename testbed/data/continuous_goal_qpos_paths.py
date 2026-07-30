"""Versioned continuous-goal predictor inputs and qpos path representation.

The model input is deliberately independent of replay identity.  Source ids are
training split metadata and never become predictor features.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

import numpy as np

from testbed.data.terrain_signature import (
    TERRAIN_SIGNATURE_DIM,
    TERRAIN_SIGNATURE_FIELD_NAMES,
    TERRAIN_SIGNATURE_SCHEMA_V1,
    TerrainSignatureV1,
    build_terrain_signature_v1,
)
from testbed.planner.primitive.coverage.continuous_goal import (
    ContinuousCutGoal,
    ContinuousGoalContractError,
)

CONTINUOUS_GOAL_WORKTOOL_SWEEP_INPUT_V1 = "continuous_goal_worktool_sweep_input_v1"
CONTINUOUS_GOAL_WORKTOOL_SWEEP_INPUT_V2 = "continuous_goal_worktool_sweep_input_v2"
QPOS_DIM = 4
PATH_PROGRESS_POINT_COUNT = 64
BSPLINE_CONTROL_POINT_COUNT = 12
BSPLINE_DEGREE = 3
PATH_PROGRESS = np.linspace(
    0.0,
    1.0,
    PATH_PROGRESS_POINT_COUNT,
    dtype=np.float64,
)
PATH_PROGRESS.setflags(write=False)

_FORBIDDEN_EXACT_KEYS = frozenset(
    {
        "episode_id",
        "source_id",
        "source_episode_id",
        "primitive_episode_id",
        "expert_id",
        "fixed_expert_id",
        "expert_episode_id",
        "exemplar_id",
        "paired_return_exemplar_id",
        "temporary_cell_id",
        "temp_cell_id",
        "temporary_cell_binding",
        "cell_binding",
        "nearest_trajectory_id",
        "nearest_expert_id",
    }
)


class ContinuousGoalQposPathContractError(ValueError):
    """Raised when predictor input or qpos path semantics are unsafe."""


@dataclass(frozen=True)
class LegacyContinuousGoalWorktoolSweepInputV1:
    """Read-only wrapper for frozen historical artifacts.

    It intentionally exposes no feature-vector or prediction method.
    """

    payload: MappingProxyType[str, Any]
    schema: str = CONTINUOUS_GOAL_WORKTOOL_SWEEP_INPUT_V1


@dataclass(frozen=True)
class ContinuousGoalWorktoolSweepInputV2:
    """Complete live handoff, continuous goal, and 89D terrain signature."""

    handoff_qpos: tuple[float, float, float, float]
    handoff_qvel: tuple[float, float, float, float]
    continuous_goal: MappingProxyType[str, Any]
    terrain_signature: np.ndarray
    goal_sha256: str
    input_sha256: str
    schema: str = CONTINUOUS_GOAL_WORKTOOL_SWEEP_INPUT_V2

    @classmethod
    def create(
        cls,
        *,
        handoff_qpos: Any,
        handoff_qvel: Any,
        continuous_goal: Any,
        terrain_signature: Any,
    ) -> ContinuousGoalWorktoolSweepInputV2:
        qpos = _finite_vector(
            handoff_qpos,
            size=QPOS_DIM,
            label="handoff_qpos",
        )
        qvel = _finite_vector(
            handoff_qvel,
            size=QPOS_DIM,
            label="handoff_qvel",
        )
        goal, goal_sha = _validate_continuous_goal(continuous_goal)
        terrain = _terrain_signature_array(terrain_signature)
        terrain.setflags(write=False)
        payload = {
            "schema": CONTINUOUS_GOAL_WORKTOOL_SWEEP_INPUT_V2,
            "handoff_qpos": list(qpos),
            "handoff_qvel": list(qvel),
            "continuous_goal": _plain_value(goal),
            "terrain_signature": {
                "schema": TERRAIN_SIGNATURE_SCHEMA_V1,
                "field_names": list(TERRAIN_SIGNATURE_FIELD_NAMES),
                "values": terrain.tolist(),
            },
        }
        return cls(
            handoff_qpos=qpos,
            handoff_qvel=qvel,
            continuous_goal=goal,
            terrain_signature=terrain,
            goal_sha256=goal_sha,
            input_sha256=canonical_sha256(payload),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "handoff_qpos": list(self.handoff_qpos),
            "handoff_qvel": list(self.handoff_qvel),
            "continuous_goal": _plain_value(self.continuous_goal),
            "terrain_signature": {
                "schema": TERRAIN_SIGNATURE_SCHEMA_V1,
                "field_names": list(TERRAIN_SIGNATURE_FIELD_NAMES),
                "values": self.terrain_signature.tolist(),
            },
            "goal_sha256": self.goal_sha256,
            "input_sha256": self.input_sha256,
        }


@dataclass(frozen=True)
class FittedQposBSpline:
    """Twelve clamped-cubic controls relative to the actual handoff."""

    control_points: np.ndarray
    target_relative_path: np.ndarray
    reconstructed_relative_path: np.ndarray
    path_progress: np.ndarray = field(
        default_factory=lambda: PATH_PROGRESS,
    )


def read_continuous_goal_worktool_sweep_input(
    value: Any,
    *,
    allow_legacy_v1: bool = True,
) -> ContinuousGoalWorktoolSweepInputV2 | LegacyContinuousGoalWorktoolSweepInputV1:
    """Read v1 for history, while keeping new inference on the v2 class."""

    if isinstance(value, ContinuousGoalWorktoolSweepInputV2):
        value = value.as_dict()
    if isinstance(value, LegacyContinuousGoalWorktoolSweepInputV1):
        if not allow_legacy_v1:
            raise ContinuousGoalQposPathContractError(
                "new prediction requires continuous goal sweep input v2"
            )
        return value
    mapping = _as_mapping(value, label="continuous goal sweep input")
    schema = str(mapping.get("schema", "")).strip()
    if schema == CONTINUOUS_GOAL_WORKTOOL_SWEEP_INPUT_V1:
        if not allow_legacy_v1:
            raise ContinuousGoalQposPathContractError(
                "new prediction requires continuous goal sweep input v2"
            )
        frozen = _freeze_mapping(mapping, label="legacy input")
        return LegacyContinuousGoalWorktoolSweepInputV1(payload=frozen)
    if schema != CONTINUOUS_GOAL_WORKTOOL_SWEEP_INPUT_V2:
        raise ContinuousGoalQposPathContractError(
            "continuous goal sweep input schema must be v2"
        )
    allowed_fields = {
        "schema",
        "handoff_qpos",
        "handoff_qvel",
        "continuous_goal",
        "terrain_signature",
        "goal_sha256",
        "input_sha256",
    }
    unexpected_fields = sorted(set(mapping) - allowed_fields)
    if unexpected_fields:
        raise ContinuousGoalQposPathContractError(
            f"continuous goal sweep input has unsupported fields: {unexpected_fields}"
        )
    try:
        request = ContinuousGoalWorktoolSweepInputV2.create(
            handoff_qpos=mapping["handoff_qpos"],
            handoff_qvel=mapping["handoff_qvel"],
            continuous_goal=mapping["continuous_goal"],
            terrain_signature=mapping["terrain_signature"],
        )
    except KeyError as exc:
        raise ContinuousGoalQposPathContractError(
            f"continuous goal sweep input missing {exc.args[0]!r}"
        ) from exc
    for lineage_field, expected in (
        ("goal_sha256", request.goal_sha256),
        ("input_sha256", request.input_sha256),
    ):
        supplied = mapping.get(lineage_field)
        if supplied is not None and str(supplied) != expected:
            raise ContinuousGoalQposPathContractError(
                f"continuous goal sweep input {lineage_field} lineage mismatch"
            )
    return request


def continuous_goal_numeric_features(
    goal: Mapping[str, Any],
) -> dict[str, float]:
    """Encode the complete numeric and categorical effect intent."""

    validated, _ = _validate_continuous_goal(goal)
    entry = tuple(float(value) for value in validated["entry_xz_m"])
    exit_ = tuple(float(value) for value in validated["exit_xz_m"])
    direction = tuple(float(value) for value in validated["direction_xz"])
    features = {
        "goal.target_cell_id": float(validated["target_cell_id"]),
        "goal.entry_xz_m[0]": entry[0],
        "goal.entry_xz_m[1]": entry[1],
        "goal.exit_xz_m[0]": exit_[0],
        "goal.exit_xz_m[1]": exit_[1],
        "goal.direction_xz[0]": direction[0],
        "goal.direction_xz[1]": direction[1],
        "goal.cut_length_m": float(validated["cut_length_m"]),
        "goal.planned_depth_m": float(validated["planned_depth_m"]),
        "goal.payload_intent_kg": float(validated["payload_intent_kg"]),
    }
    _append_numeric_leaves(
        features,
        validated["effect_intent"],
        path="goal.effect_intent",
    )
    return dict(sorted(features.items()))


def predictor_feature_map(
    value: ContinuousGoalWorktoolSweepInputV2,
) -> dict[str, float]:
    """Build named features so artifacts never depend on magic indexes."""

    features = {
        **{
            f"handoff_qpos[{index}]": number
            for index, number in enumerate(value.handoff_qpos)
        },
        **{
            f"handoff_qvel[{index}]": number
            for index, number in enumerate(value.handoff_qvel)
        },
        **continuous_goal_numeric_features(value.continuous_goal),
        **{
            f"terrain.{field_name}": float(value.terrain_signature[index])
            for index, field_name in enumerate(TERRAIN_SIGNATURE_FIELD_NAMES)
        },
    }
    return dict(sorted(features.items()))


def vectorize_sweep_input(
    value: ContinuousGoalWorktoolSweepInputV2,
    *,
    feature_names: Sequence[str],
) -> np.ndarray:
    """Vectorize only when the complete named schema matches the artifact."""

    features = predictor_feature_map(value)
    expected = tuple(str(name) for name in feature_names)
    missing = sorted(set(expected) - set(features))
    unexpected = sorted(set(features) - set(expected))
    missing_required = [name for name in missing if not name.startswith("categorical:")]
    categorical_groups: dict[str, list[str]] = {}
    for name in expected:
        if name.startswith("categorical:"):
            group, separator, _ = name.partition("::value::")
            if not separator:
                raise ContinuousGoalQposPathContractError(
                    "categorical predictor feature schema is invalid"
                )
            categorical_groups.setdefault(group, []).append(name)
    missing_categories = [
        group
        for group, names in categorical_groups.items()
        if sum(name in features for name in names) != 1
    ]
    if (
        unexpected
        or missing_required
        or missing_categories
        or len(expected) != len(set(expected))
    ):
        raise ContinuousGoalQposPathContractError(
            "continuous goal predictor feature schema mismatch: "
            f"missing={missing}, unexpected={unexpected}, "
            f"categorical_groups={missing_categories}"
        )
    array = np.asarray(
        [features.get(name, 0.0) for name in expected],
        dtype=np.float64,
    )
    if not np.all(np.isfinite(array)):
        raise ContinuousGoalQposPathContractError(
            "continuous goal predictor features must be finite"
        )
    return array


def resample_qpos_path_by_joint_arc_length(qpos_path: Any) -> np.ndarray:
    """Normalize an expert path by cumulative four-joint arc length."""

    path = _finite_qpos_path(qpos_path)
    segment_lengths = np.linalg.norm(np.diff(path, axis=0), axis=1)
    cumulative = np.concatenate(([0.0], np.cumsum(segment_lengths)))
    total = float(cumulative[-1])
    if total <= np.finfo(np.float64).eps:
        raise ContinuousGoalQposPathContractError(
            "expert qpos path must have non-zero four-joint arc length"
        )
    cumulative /= total
    unique_progress, unique_indices = np.unique(cumulative, return_index=True)
    unique_path = path[unique_indices]
    resampled = np.column_stack(
        [
            np.interp(PATH_PROGRESS, unique_progress, unique_path[:, joint])
            for joint in range(QPOS_DIM)
        ]
    )
    resampled[0] = path[0]
    resampled[-1] = path[-1]
    return np.asarray(resampled, dtype=np.float64)


def fit_qpos_bspline(
    qpos_path: Any,
    *,
    handoff_qpos: Any | None = None,
) -> FittedQposBSpline:
    """Fit 12 clamped-cubic controls, fixing the first control to zero."""

    resampled = resample_qpos_path_by_joint_arc_length(qpos_path)
    handoff = (
        resampled[0]
        if handoff_qpos is None
        else np.asarray(
            _finite_vector(
                handoff_qpos,
                size=QPOS_DIM,
                label="handoff_qpos",
            ),
            dtype=np.float64,
        )
    )
    start_error = float(np.max(np.abs(resampled[0] - handoff)))
    if start_error > 1.0e-6:
        raise ContinuousGoalQposPathContractError(
            "expert qpos path must start at handoff_qpos within 1e-6"
        )
    target = resampled - handoff[None, :]
    target[0] = 0.0
    basis = clamped_cubic_bspline_basis(PATH_PROGRESS)
    free_controls, *_ = np.linalg.lstsq(
        basis[:, 1:],
        target,
        rcond=None,
    )
    controls = np.vstack((np.zeros((1, QPOS_DIM)), free_controls))
    controls[0] = 0.0
    reconstructed = basis @ controls
    reconstructed[0] = 0.0
    for array in (controls, target, reconstructed):
        array.setflags(write=False)
    return FittedQposBSpline(
        control_points=controls,
        target_relative_path=target,
        reconstructed_relative_path=reconstructed,
    )


def evaluate_qpos_bspline(
    control_points: Any,
    *,
    path_progress: Any = PATH_PROGRESS,
) -> np.ndarray:
    """Evaluate a 12-control clamped cubic spline as relative qpos."""

    controls = np.asarray(control_points, dtype=np.float64)
    if controls.shape != (BSPLINE_CONTROL_POINT_COUNT, QPOS_DIM):
        raise ContinuousGoalQposPathContractError(
            "qpos B-spline controls must have shape (12, 4)"
        )
    if not np.all(np.isfinite(controls)):
        raise ContinuousGoalQposPathContractError(
            "qpos B-spline controls must be finite"
        )
    if not np.array_equal(controls[0], np.zeros(QPOS_DIM)):
        raise ContinuousGoalQposPathContractError(
            "qpos B-spline first control must be exactly zero"
        )
    progress = np.asarray(path_progress, dtype=np.float64).reshape(-1)
    if (
        progress.size < 2
        or not np.all(np.isfinite(progress))
        or np.any(np.diff(progress) < 0.0)
        or progress[0] != 0.0
        or progress[-1] != 1.0
    ):
        raise ContinuousGoalQposPathContractError(
            "path_progress must be finite, ordered, and span [0, 1]"
        )
    relative = clamped_cubic_bspline_basis(progress) @ controls
    relative[0] = 0.0
    return relative


def clamped_cubic_bspline_basis(progress: Any) -> np.ndarray:
    """Return the fixed (N, 12) clamped cubic B-spline design matrix."""

    values = np.asarray(progress, dtype=np.float64).reshape(-1)
    if (
        values.size == 0
        or not np.all(np.isfinite(values))
        or np.any(values < 0.0)
        or np.any(values > 1.0)
    ):
        raise ContinuousGoalQposPathContractError(
            "B-spline progress must be finite and inside [0, 1]"
        )
    interior_count = BSPLINE_CONTROL_POINT_COUNT - BSPLINE_DEGREE - 1
    knots = np.concatenate(
        (
            np.zeros(BSPLINE_DEGREE + 1),
            np.linspace(0.0, 1.0, interior_count + 2)[1:-1],
            np.ones(BSPLINE_DEGREE + 1),
        )
    )
    basis = np.zeros(
        (values.size, BSPLINE_CONTROL_POINT_COUNT),
        dtype=np.float64,
    )
    for index in range(BSPLINE_CONTROL_POINT_COUNT):
        basis[:, index] = (values >= knots[index]) & (values < knots[index + 1])
    basis[values == 1.0, -1] = 1.0
    for degree in range(1, BSPLINE_DEGREE + 1):
        updated = np.zeros_like(basis)
        for index in range(BSPLINE_CONTROL_POINT_COUNT):
            left_width = knots[index + degree] - knots[index]
            if left_width > 0.0:
                updated[:, index] += ((values - knots[index]) / left_width) * basis[
                    :, index
                ]
            if index + 1 < BSPLINE_CONTROL_POINT_COUNT:
                right_width = knots[index + degree + 1] - knots[index + 1]
                if right_width > 0.0:
                    updated[:, index] += (
                        (knots[index + degree + 1] - values) / right_width
                    ) * basis[:, index + 1]
        basis = updated
        basis[values == 1.0, :] = 0.0
        basis[values == 1.0, -1] = 1.0
    return basis


def qpos_path_sha256(qpos_path: Any) -> str:
    """Hash the canonical little-endian float32 row-major path."""

    path = np.asarray(qpos_path, dtype="<f4", order="C")
    if path.shape != (PATH_PROGRESS_POINT_COUNT, QPOS_DIM) or not np.all(
        np.isfinite(path)
    ):
        raise ContinuousGoalQposPathContractError(
            "qpos path lineage requires finite shape (64, 4)"
        )
    return hashlib.sha256(path.tobytes(order="C")).hexdigest()


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        _plain_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_continuous_goal(
    value: Any,
) -> tuple[MappingProxyType[str, Any], str]:
    if hasattr(value, "as_dict") and callable(value.as_dict):
        value = value.as_dict()
    goal = _as_mapping(value, label="continuous_goal")
    _reject_forbidden_bindings(goal, path="continuous_goal")
    try:
        parsed = ContinuousCutGoal.from_mapping(goal)
    except ContinuousGoalContractError as exc:
        raise ContinuousGoalQposPathContractError(
            f"continuous_goal contract invalid: {exc}"
        ) from exc
    plain_goal = parsed.as_dict()
    return (
        _freeze_mapping(plain_goal, label="continuous_goal"),
        parsed.goal_id,
    )


def _terrain_signature_array(value: Any) -> np.ndarray:
    try:
        if isinstance(value, TerrainSignatureV1):
            signature = value
        else:
            if hasattr(value, "as_dict") and callable(value.as_dict):
                value = value.as_dict()
            mapping = _as_mapping(value, label="terrain_signature")
            _reject_forbidden_bindings(
                mapping,
                path="terrain_signature",
            )
            if "values" in mapping:
                signature = TerrainSignatureV1(
                    values=tuple(mapping["values"]),
                    field_names=tuple(
                        mapping.get(
                            "field_names",
                            TERRAIN_SIGNATURE_FIELD_NAMES,
                        )
                    ),
                    schema=str(mapping.get("schema", TERRAIN_SIGNATURE_SCHEMA_V1)),
                )
            else:
                signature = build_terrain_signature_v1(mapping)
        return signature.as_array(dtype=np.float64)
    except (TypeError, ValueError) as exc:
        message = str(exc)
        if "contain" in message or "89" in message or "107" in message:
            message = "terrain signature must contain exactly 89 finite values"
        raise ContinuousGoalQposPathContractError(message) from exc


def _append_numeric_leaves(
    output: dict[str, float],
    value: Any,
    *,
    path: str,
) -> None:
    if isinstance(value, Mapping):
        for key in sorted(value, key=str):
            _append_numeric_leaves(
                output,
                value[key],
                path=f"{path}.{key}",
            )
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _append_numeric_leaves(
                output,
                item,
                path=f"{path}[{index}]",
            )
        return
    if isinstance(value, bool):
        output[path] = float(value)
        return
    if isinstance(value, (int, float, np.integer, np.floating)):
        output[path] = _finite_scalar(value, label=path)
        return
    if isinstance(value, str):
        category = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        output[f"categorical:{path}::value::{category}"] = 1.0
        return
    if value is None:
        output[f"categorical:{path}::value::null"] = 1.0
        return
    raise ContinuousGoalQposPathContractError(
        f"{path} has unsupported feature type {type(value).__name__}"
    )


def _reject_forbidden_bindings(value: Any, *, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            name = str(key).strip().lower()
            forbidden = (
                name in _FORBIDDEN_EXACT_KEYS
                or name.endswith("_episode_id")
                or "expert_id" in name
                or "exemplar" in name
                or (
                    "nearest" in name
                    and any(
                        binding in name
                        for binding in (
                            "expert",
                            "trajectory",
                            "exemplar",
                            "episode",
                        )
                    )
                )
                or ("cell" in name and ("temporary" in name or "temp_" in name))
                or ("cell" in name and "binding" in name)
            )
            if forbidden:
                raise ContinuousGoalQposPathContractError(
                    f"{path}.{name} is a forbidden model binding"
                )
            _reject_forbidden_bindings(item, path=f"{path}.{name}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_forbidden_bindings(item, path=f"{path}[{index}]")


def _finite_qpos_path(value: Any) -> np.ndarray:
    try:
        path = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ContinuousGoalQposPathContractError(
            "expert qpos path must be finite shape (N, 4)"
        ) from exc
    if (
        path.ndim != 2
        or path.shape[0] < 2
        or path.shape[1] != QPOS_DIM
        or not np.all(np.isfinite(path))
    ):
        raise ContinuousGoalQposPathContractError(
            "expert qpos path must be finite shape (N, 4), N >= 2"
        )
    return path


def _finite_vector(value: Any, *, size: int, label: str) -> tuple[float, ...]:
    try:
        array = np.asarray(value, dtype=np.float64).reshape(-1)
    except (TypeError, ValueError) as exc:
        raise ContinuousGoalQposPathContractError(
            f"{label} must contain {size} finite values"
        ) from exc
    if array.shape != (size,) or not np.all(np.isfinite(array)):
        raise ContinuousGoalQposPathContractError(
            f"{label} must contain {size} finite values"
        )
    return tuple(float(item) for item in array)


def _finite_scalar(value: Any, *, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ContinuousGoalQposPathContractError(f"{label} must be finite") from exc
    if not math.isfinite(number):
        raise ContinuousGoalQposPathContractError(f"{label} must be finite")
    return number


def _as_mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContinuousGoalQposPathContractError(f"{label} must be a mapping")
    return value


def _freeze_mapping(
    value: Mapping[str, Any],
    *,
    label: str,
) -> MappingProxyType[str, Any]:
    try:
        plain = _plain_value(value)
        json.dumps(plain, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ContinuousGoalQposPathContractError(
            f"{label} must contain canonical JSON values"
        ) from exc
    return MappingProxyType(
        {str(key): _freeze_value(item) for key, item in plain.items()}
    )


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_value(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze_value(item) for item in value)
    return value


def _plain_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain_value(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    return value


__all__ = [
    "BSPLINE_CONTROL_POINT_COUNT",
    "BSPLINE_DEGREE",
    "CONTINUOUS_GOAL_WORKTOOL_SWEEP_INPUT_V1",
    "CONTINUOUS_GOAL_WORKTOOL_SWEEP_INPUT_V2",
    "FittedQposBSpline",
    "LegacyContinuousGoalWorktoolSweepInputV1",
    "PATH_PROGRESS",
    "PATH_PROGRESS_POINT_COUNT",
    "QPOS_DIM",
    "TERRAIN_SIGNATURE_DIM",
    "ContinuousGoalQposPathContractError",
    "ContinuousGoalWorktoolSweepInputV2",
    "canonical_sha256",
    "clamped_cubic_bspline_basis",
    "continuous_goal_numeric_features",
    "evaluate_qpos_bspline",
    "fit_qpos_bspline",
    "predictor_feature_map",
    "qpos_path_sha256",
    "read_continuous_goal_worktool_sweep_input",
    "resample_qpos_path_by_joint_arc_length",
    "vectorize_sweep_input",
]
