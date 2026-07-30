"""Atomic continuous cut goals and immutable execution-plan locking."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

import numpy as np

from testbed.planner.primitive.coverage.continuous_worktool_sweep import (
    PlannedReferenceQposSweep,
)
from testbed.planner.primitive.token.tokens import DigCutTokenPlanner

CONTINUOUS_CUT_GOAL_SCHEMA = "continuous_cut_goal_v1"
CONTINUOUS_GOAL_EXECUTION_PLAN_SCHEMA = (
    "locked_cut_goal_execution_plan_v1"
)
CONTINUOUS_GOAL_SUPPORT_DIAGNOSTIC_SCHEMA = (
    "continuous_goal_support_diagnostic_v1"
)

_EPISODE_BINDING_KEYS = frozenset(
    {
        "episode_id",
        "source_episode_id",
        "primitive_episode_id",
        "paired_return_exemplar_id",
        "exemplar_id",
    }
)


class ContinuousGoalContractError(ValueError):
    """Raised when an atomic continuous-goal contract is incomplete."""


@dataclass(frozen=True)
class ContinuousCutGoal:
    """One indivisible goal; direction and length are derived properties."""

    target_cell_id: int
    entry_xz_m: tuple[float, float]
    exit_xz_m: tuple[float, float]
    planned_depth_m: float
    payload_intent_kg: float
    effect_intent: MappingProxyType[str, Any]
    terrain_signature: MappingProxyType[str, Any]
    goal_id: str

    @classmethod
    def create(
        cls,
        *,
        target_cell_id: int,
        entry_xz_m: Sequence[float],
        exit_xz_m: Sequence[float],
        planned_depth_m: float,
        payload_intent_kg: float,
        effect_intent: Mapping[str, Any],
        terrain_signature: Mapping[str, Any],
    ) -> ContinuousCutGoal:
        entry = _finite_pair(entry_xz_m, label="entry_xz_m")
        exit_ = _finite_pair(exit_xz_m, label="exit_xz_m")
        length = float(math.hypot(exit_[0] - entry[0], exit_[1] - entry[1]))
        if length <= 1.0e-9:
            raise ContinuousGoalContractError(
                "entry_xz_m and exit_xz_m must define a non-zero cut"
            )
        depth = _finite_nonnegative(
            planned_depth_m,
            label="planned_depth_m",
        )
        payload = _finite_nonnegative(
            payload_intent_kg,
            label="payload_intent_kg",
        )
        cell_id = int(target_cell_id)
        if cell_id < 0:
            raise ContinuousGoalContractError(
                "target_cell_id must be non-negative"
            )
        effect = _immutable_mapping(
            effect_intent,
            label="effect_intent",
        )
        terrain = _immutable_mapping(
            terrain_signature,
            label="terrain_signature",
        )
        _reject_episode_bindings(effect, path="effect_intent")
        _reject_episode_bindings(terrain, path="terrain_signature")
        payload_without_id = _goal_payload(
            target_cell_id=cell_id,
            entry_xz_m=entry,
            exit_xz_m=exit_,
            planned_depth_m=depth,
            payload_intent_kg=payload,
            effect_intent=effect,
            terrain_signature=terrain,
        )
        goal_id = _canonical_sha256(payload_without_id)
        return cls(
            target_cell_id=cell_id,
            entry_xz_m=entry,
            exit_xz_m=exit_,
            planned_depth_m=depth,
            payload_intent_kg=payload,
            effect_intent=effect,
            terrain_signature=terrain,
            goal_id=goal_id,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> ContinuousCutGoal:
        payload = dict(value)
        schema = str(payload.get("schema", CONTINUOUS_CUT_GOAL_SCHEMA))
        if schema != CONTINUOUS_CUT_GOAL_SCHEMA:
            raise ContinuousGoalContractError(
                f"continuous goal schema must be {CONTINUOUS_CUT_GOAL_SCHEMA!r}"
            )
        allowed = {
            "schema",
            "target_cell_id",
            "entry_xz_m",
            "exit_xz_m",
            "direction_xz",
            "cut_length_m",
            "planned_depth_m",
            "payload_intent_kg",
            "effect_intent",
            "terrain_signature",
            "goal_id",
        }
        unexpected = sorted(set(payload) - allowed)
        if unexpected:
            raise ContinuousGoalContractError(
                f"continuous goal has unsupported fields: {unexpected}"
            )
        try:
            goal = cls.create(
                target_cell_id=payload["target_cell_id"],
                entry_xz_m=payload["entry_xz_m"],
                exit_xz_m=payload["exit_xz_m"],
                planned_depth_m=payload["planned_depth_m"],
                payload_intent_kg=payload["payload_intent_kg"],
                effect_intent=payload["effect_intent"],
                terrain_signature=payload["terrain_signature"],
            )
        except KeyError as exc:
            raise ContinuousGoalContractError(
                f"continuous goal missing field {exc.args[0]!r}"
            ) from exc
        if "direction_xz" in payload:
            observed = _finite_pair(
                payload["direction_xz"],
                label="direction_xz",
            )
            if _max_abs_difference(observed, goal.direction_xz) > 1.0e-9:
                raise ContinuousGoalContractError(
                    "direction_xz must be derived from entry_xz_m/exit_xz_m"
                )
        if "cut_length_m" in payload:
            observed_length = float(payload["cut_length_m"])
            if (
                not math.isfinite(observed_length)
                or abs(observed_length - goal.cut_length_m) > 1.0e-9
            ):
                raise ContinuousGoalContractError(
                    "cut_length_m must be derived from entry_xz_m/exit_xz_m"
                )
        supplied_goal_id = str(payload.get("goal_id", "")).strip().lower()
        if supplied_goal_id and supplied_goal_id != goal.goal_id:
            raise ContinuousGoalContractError(
                "continuous goal canonical goal_id mismatch"
            )
        return goal

    @property
    def direction_xz(self) -> tuple[float, float]:
        delta_x = self.exit_xz_m[0] - self.entry_xz_m[0]
        delta_z = self.exit_xz_m[1] - self.entry_xz_m[1]
        length = self.cut_length_m
        return (delta_x / length, delta_z / length)

    @property
    def cut_length_m(self) -> float:
        return float(
            math.hypot(
                self.exit_xz_m[0] - self.entry_xz_m[0],
                self.exit_xz_m[1] - self.entry_xz_m[1],
            )
        )

    def as_dict(self) -> dict[str, Any]:
        payload = _goal_payload(
            target_cell_id=self.target_cell_id,
            entry_xz_m=self.entry_xz_m,
            exit_xz_m=self.exit_xz_m,
            planned_depth_m=self.planned_depth_m,
            payload_intent_kg=self.payload_intent_kg,
            effect_intent=self.effect_intent,
            terrain_signature=self.terrain_signature,
        )
        payload["goal_id"] = self.goal_id
        return payload


@dataclass(frozen=True)
class ContinuousGoalSupportDiagnostic:
    """Diagnostic-only whole-goal support/OOD evidence."""

    support_status: str
    whole_goal_distance: float | None = None
    ood_reasons: tuple[str, ...] = ()
    diagnostic_only: bool = True
    episode_snap_applied: bool = False

    def __post_init__(self) -> None:
        status = str(self.support_status).strip().lower()
        if status not in {"supported", "ood", "unknown"}:
            raise ContinuousGoalContractError(
                "support_status must be supported, ood, or unknown"
            )
        object.__setattr__(self, "support_status", status)
        object.__setattr__(
            self,
            "ood_reasons",
            tuple(str(value) for value in self.ood_reasons),
        )
        if self.whole_goal_distance is not None:
            distance = float(self.whole_goal_distance)
            if not math.isfinite(distance) or distance < 0.0:
                raise ContinuousGoalContractError(
                    "whole_goal_distance must be finite and non-negative"
                )
            object.__setattr__(self, "whole_goal_distance", distance)
        if not self.diagnostic_only or self.episode_snap_applied:
            raise ContinuousGoalContractError(
                "continuous support/OOD evidence is diagnostic-only and "
                "cannot apply an episode snap"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": CONTINUOUS_GOAL_SUPPORT_DIAGNOSTIC_SCHEMA,
            "support_status": self.support_status,
            "whole_goal_distance": self.whole_goal_distance,
            "ood_reasons": list(self.ood_reasons),
            "diagnostic_only": True,
            "episode_snap_applied": False,
        }


@dataclass(frozen=True)
class LockedCutGoalExecutionPlan:
    """Atomic goal, tokens, return envelope, sweep, and diagnostics."""

    goal: ContinuousCutGoal
    raw_fields: MappingProxyType[str, float | int]
    raw_fields_sha256: str
    dig_token: np.ndarray
    return_envelope: Any
    planned_qpos_sweep: PlannedReferenceQposSweep
    support_ood: ContinuousGoalSupportDiagnostic
    schema: str = CONTINUOUS_GOAL_EXECUTION_PLAN_SCHEMA

    @property
    def goal_id(self) -> str:
        return self.goal.goal_id

    @property
    def planned_qpos_path_sha256(self) -> str:
        return self.planned_qpos_sweep.path_sha256


@dataclass(frozen=True)
class ContinuousCoverageGoalService:
    """Build raw fields/tokens once and commit one whole goal atomically."""

    def build_goal(self, value: Mapping[str, Any]) -> ContinuousCutGoal:
        return ContinuousCutGoal.from_mapping(value)

    def raw_fields(
        self,
        goal: ContinuousCutGoal,
    ) -> MappingProxyType[str, float | int]:
        direction_x, direction_z = goal.direction_xz
        entry_x, entry_z = goal.entry_xz_m
        exit_x, exit_z = goal.exit_xz_m
        return MappingProxyType(
            {
                "operator_entry_x_m": float(entry_x),
                "operator_entry_y_m": 0.0,
                "operator_entry_z_m": float(entry_z),
                "operator_exit_x_m": float(exit_x),
                "operator_exit_y_m": 0.0,
                "operator_exit_z_m": float(exit_z),
                "operator_cut_direction_x": float(direction_x),
                "operator_cut_direction_y": 0.0,
                "operator_cut_direction_z": float(direction_z),
                "operator_cut_length_m": float(goal.cut_length_m),
                "operator_cut_depth_peak_m": float(goal.planned_depth_m),
                "operator_cut_payload_gain_kg": float(
                    goal.payload_intent_kg
                ),
                "operator_effective_deposit_delta_kg": float(
                    goal.payload_intent_kg
                ),
                "operator_cut_valid": 1,
                "target_cell_id": int(goal.target_cell_id),
            }
        )

    def dig_token(self, goal: ContinuousCutGoal) -> np.ndarray:
        plan = DigCutTokenPlanner(prior={}).plan_from_raw_fields(
            dict(self.raw_fields(goal)),
            source="continuous_goal_conditioned",
        )
        if plan.token.shape != (10,) or not np.all(np.isfinite(plan.token)):
            raise ContinuousGoalContractError(
                "continuous goal did not produce a complete finite 10D token"
            )
        return plan.token.copy()

    def lock_execution_plan(
        self,
        *,
        goal: ContinuousCutGoal,
        return_envelope: Any,
        planned_qpos_sweep: PlannedReferenceQposSweep,
        support_ood: ContinuousGoalSupportDiagnostic,
    ) -> LockedCutGoalExecutionPlan:
        envelope_goal_id = str(getattr(return_envelope, "goal_id", ""))
        if envelope_goal_id != goal.goal_id:
            raise ContinuousGoalContractError(
                "return envelope goal identity drift"
            )
        if planned_qpos_sweep.goal_id != goal.goal_id:
            raise ContinuousGoalContractError(
                "planned qpos sweep goal identity drift"
            )
        token = np.asarray(self.dig_token(goal), dtype=np.float32).copy()
        token.setflags(write=False)
        fields = self.raw_fields(goal)
        raw_sha = _canonical_sha256(dict(fields))
        return LockedCutGoalExecutionPlan(
            goal=goal,
            raw_fields=fields,
            raw_fields_sha256=raw_sha,
            dig_token=token,
            return_envelope=return_envelope,
            planned_qpos_sweep=planned_qpos_sweep,
            support_ood=support_ood,
        )


def _goal_payload(
    *,
    target_cell_id: int,
    entry_xz_m: tuple[float, float],
    exit_xz_m: tuple[float, float],
    planned_depth_m: float,
    payload_intent_kg: float,
    effect_intent: Mapping[str, Any],
    terrain_signature: Mapping[str, Any],
) -> dict[str, Any]:
    delta_x = float(exit_xz_m[0] - entry_xz_m[0])
    delta_z = float(exit_xz_m[1] - entry_xz_m[1])
    length = float(math.hypot(delta_x, delta_z))
    return {
        "schema": CONTINUOUS_CUT_GOAL_SCHEMA,
        "target_cell_id": int(target_cell_id),
        "entry_xz_m": [float(value) for value in entry_xz_m],
        "exit_xz_m": [float(value) for value in exit_xz_m],
        "direction_xz": [delta_x / length, delta_z / length],
        "cut_length_m": length,
        "planned_depth_m": float(planned_depth_m),
        "payload_intent_kg": float(payload_intent_kg),
        "effect_intent": _plain_value(effect_intent),
        "terrain_signature": _plain_value(terrain_signature),
    }


def _immutable_mapping(
    value: Mapping[str, Any],
    *,
    label: str,
) -> MappingProxyType[str, Any]:
    if not isinstance(value, Mapping) or not value:
        raise ContinuousGoalContractError(
            f"{label} must be a non-empty mapping"
        )
    frozen = {
        str(key): _immutable_value(item, path=f"{label}.{key}")
        for key, item in value.items()
    }
    try:
        json.dumps(_plain_value(frozen), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ContinuousGoalContractError(
            f"{label} must contain canonical JSON values"
        ) from exc
    return MappingProxyType(frozen)


def _immutable_value(value: Any, *, path: str) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                str(key): _immutable_value(item, path=f"{path}.{key}")
                for key, item in value.items()
            }
        )
    if isinstance(value, (list, tuple)):
        return tuple(
            _immutable_value(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        )
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, (float, np.floating)):
        number = float(value)
        if not math.isfinite(number):
            raise ContinuousGoalContractError(
                f"{path} must be finite"
            )
        return 0.0 if number == 0.0 else number
    raise ContinuousGoalContractError(
        f"{path} has unsupported value type {type(value).__name__}"
    )


def _plain_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain_value(item) for item in value]
    return value


def _reject_episode_bindings(value: Any, *, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key).strip().lower()
            if key_text in _EPISODE_BINDING_KEYS or key_text.endswith(
                "_episode_id"
            ):
                raise ContinuousGoalContractError(
                    f"{path}.{key_text} is an episode runtime binding"
                )
            _reject_episode_bindings(item, path=f"{path}.{key_text}")
    elif isinstance(value, tuple):
        for index, item in enumerate(value):
            _reject_episode_bindings(item, path=f"{path}[{index}]")


def _finite_pair(value: Sequence[float], *, label: str) -> tuple[float, float]:
    try:
        array = np.asarray(value, dtype=np.float64).reshape(-1)
    except (TypeError, ValueError) as exc:
        raise ContinuousGoalContractError(
            f"{label} must contain two finite values"
        ) from exc
    if array.shape != (2,) or not np.all(np.isfinite(array)):
        raise ContinuousGoalContractError(
            f"{label} must contain two finite values"
        )
    return (float(array[0]), float(array[1]))


def _finite_nonnegative(value: Any, *, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ContinuousGoalContractError(
            f"{label} must be finite and non-negative"
        ) from exc
    if not math.isfinite(number) or number < 0.0:
        raise ContinuousGoalContractError(
            f"{label} must be finite and non-negative"
        )
    return number


def _max_abs_difference(first: Any, second: Any) -> float:
    return float(
        np.max(
            np.abs(
                np.asarray(first, dtype=np.float64)
                - np.asarray(second, dtype=np.float64)
            )
        )
    )


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        _plain_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "CONTINUOUS_CUT_GOAL_SCHEMA",
    "CONTINUOUS_GOAL_EXECUTION_PLAN_SCHEMA",
    "CONTINUOUS_GOAL_SUPPORT_DIAGNOSTIC_SCHEMA",
    "ContinuousCoverageGoalService",
    "ContinuousCutGoal",
    "ContinuousGoalContractError",
    "ContinuousGoalSupportDiagnostic",
    "LockedCutGoalExecutionPlan",
]
