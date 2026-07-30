"""Online planned-cut provider backed by a released calibrated effect model."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from testbed.data.schema import (
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_DIG_AREA_BASELINE_DEPTH_START_IDX,
    ENV_STATE_DIG_AREA_CELL_AREA_IDX,
    ENV_STATE_DIG_AREA_CELL_LONG_SIZE_IDX,
    ENV_STATE_DIG_AREA_CELL_SHORT_SIZE_IDX,
    ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
    ENV_STATE_DIG_AREA_GRID_ORIGIN_WORLD_START_IDX,
    ENV_STATE_DIG_AREA_LONG_AXIS_IDX,
    ENV_STATE_DIG_AREA_LONG_AXIS_UNIT_WORLD_START_IDX,
    ENV_STATE_DIG_AREA_REFERENCE_PLANE_LOCAL_Y_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
    ENV_STATE_DIG_AREA_SHORT_AXIS_UNIT_WORLD_START_IDX,
    ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX,
    ENV_STATE_DIG_AREA_SURFACE_VALID_FRACTION_START_IDX,
    ENV_STATE_V2_4_DIM,
)
from testbed.eval.executed_cut_effect_samples import EFFECT_INPUT_SCHEMA
from testbed.planner.box_emptying.candidate_planner import (
    DIRECTIONS,
    PLANNED_EFFECT_CONTRACT_VERSION,
    BoxCutCandidate,
    BoxEmptyingCandidatePlanner,
    CandidateEffectPrediction,
    CandidatePlannerConfig,
    LockedCandidateSelection,
)
from testbed.planner.box_emptying.contracts import TerrainBoxResidual

PLANNED_BOX_SOURCE = "planned_box_emptying_residual_v1"


class PlannedRecordPredictor(Protocol):
    input_contract: str

    def predict(self, record: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass
class _BoundRecordEffectPredictor:
    record_predictor: PlannedRecordPredictor
    payload_intent_kg: float
    previous_outcome: Mapping[str, Any]
    contract_version: str = PLANNED_EFFECT_CONTRACT_VERSION
    obs: Mapping[str, Any] | None = None
    cycle_index: int = -1

    def bind(self, obs: Mapping[str, Any], *, cycle_index: int) -> None:
        self.obs = obs
        self.cycle_index = int(cycle_index)

    def predict(
        self,
        candidate: BoxCutCandidate,
        residual: TerrainBoxResidual,
    ) -> CandidateEffectPrediction:
        del residual
        if self.obs is None:
            raise RuntimeError("planned_effect_context_not_bound")
        record = _planned_effect_record(
            self.obs,
            candidate=candidate,
            cycle_index=self.cycle_index,
            payload_intent_kg=self.payload_intent_kg,
            previous_outcome=self.previous_outcome,
        )
        prediction = self.record_predictor.predict(record)
        delta_depth = np.asarray(
            prediction.get("signed_depth_delta_m"), dtype=np.float64
        ).reshape(-1)
        if delta_depth.size != 6 or not np.isfinite(delta_depth).all():
            raise ValueError("planned effect must predict six finite cell deltas")
        pre = record["pre_terrain"]
        cell_area = float(pre["cell_area_m2"])
        signed_volume = tuple(float(value * cell_area) for value in delta_depth)
        derived = prediction.get("derived_volume")
        uncertainty = prediction.get("uncertainty")
        if not isinstance(derived, Mapping) or not isinstance(
            uncertainty, Mapping
        ):
            raise ValueError("planned effect prediction lacks volume/uncertainty")
        return CandidateEffectPrediction(
            signed_cell_delta_m3=signed_volume,  # type: ignore[arg-type]
            payload_kg=_finite_float(
                prediction.get("payload_gain_kg"),
                "payload_gain_kg",
            ),
            removed_volume_m3=_finite_float(
                derived.get("removed_volume_m3"),
                "removed_volume_m3",
            ),
            uncertainty_m3=_finite_float(
                uncertainty.get("removed_volume_m3_std"),
                "removed_volume_m3_std",
            ),
        )


class BoxEmptyingResidualPlanService:
    """Select, lock, and expose one online cut through the existing token port."""

    def __init__(
        self,
        *,
        record_predictor: PlannedRecordPredictor,
        support_envelope: Mapping[str, Any],
        payload_intent_kg: float = 60.0,
        cut_length_m: float = 0.75,
        bucket_width_m: float = 0.70,
        wall_inset_m: float = 0.30,
        known_failure_candidate_ids: frozenset[str] = frozenset(),
    ) -> None:
        if str(getattr(record_predictor, "input_contract", "")) != "planned_cut":
            raise ValueError("online box planner requires a planned_cut predictor")
        self.record_predictor = record_predictor
        self.support_envelope = dict(support_envelope)
        self.payload_intent_kg = float(payload_intent_kg)
        self.cut_length_m = float(cut_length_m)
        self.bucket_width_m = float(bucket_width_m)
        self.wall_inset_m = float(wall_inset_m)
        self.known_failure_candidate_ids = set(known_failure_candidate_ids)
        self.blocked_corridor_ids: set[str] = set()
        self.depth_exhausted_cell_ids: set[int] = set()
        self._previous_outcome: dict[str, Any] = {
            "signed_depth_delta_m": [0.0] * 6,
            "payload_gain_kg": 0.0,
            "valid": False,
        }
        self._locks: dict[int, LockedCandidateSelection] = {}
        self._active_lock: LockedCandidateSelection | None = None
        self._active_target_cycle = -1

    def reset(self) -> None:
        self.blocked_corridor_ids.clear()
        self.depth_exhausted_cell_ids.clear()
        self._locks.clear()
        self._active_lock = None
        self._active_target_cycle = -1
        self._previous_outcome = {
            "signed_depth_delta_m": [0.0] * 6,
            "payload_gain_kg": 0.0,
            "valid": False,
        }

    def plan(
        self,
        obs: Mapping[str, Any],
        *,
        target_cycle_index: int,
    ) -> tuple[dict[str, float | int], str]:
        env = _env_state(obs)
        residual = TerrainBoxResidual.from_env_state(env)
        predictor = _BoundRecordEffectPredictor(
            record_predictor=self.record_predictor,
            payload_intent_kg=self.payload_intent_kg,
            previous_outcome=self._previous_outcome,
        )
        predictor.bind(obs, cycle_index=int(target_cycle_index))
        planner = BoxEmptyingCandidatePlanner(
            predictor=predictor,
            config=self._planner_config(env),
        )
        target = int(target_cycle_index)
        locked = self._locks.get(target)
        if locked is None:
            locked = planner.lock_selection(residual)
        else:
            locked = planner.validate_locked_selection(locked, residual)
        self._locks = {target: locked}
        self._active_lock = locked
        self._active_target_cycle = target
        candidate = locked.selection.candidate
        return _raw_goal_fields(
            candidate,
            payload_intent_kg=self.payload_intent_kg,
        ), PLANNED_BOX_SOURCE

    @property
    def active_cell_id(self) -> int:
        if self._active_lock is None:
            return -1
        return int(self._active_lock.selection.candidate.cell_id)

    @property
    def active_corridor_id(self) -> str:
        if self._active_lock is None:
            return ""
        return str(self._active_lock.selection.candidate.corridor_id)

    @property
    def active_corridor_numeric_id(self) -> int:
        if self._active_lock is None:
            return -1
        candidate = self._active_lock.selection.candidate
        direction_index = DIRECTIONS.index(candidate.direction)
        return int(candidate.cell_id * 4 + direction_index)

    def block_corridor_numeric_id(self, corridor_id: int) -> None:
        value = int(corridor_id)
        if value < 0 or value >= 24:
            raise ValueError(f"invalid box corridor numeric id: {value}")
        cell_id, direction_index = divmod(value, 4)
        self.blocked_corridor_ids.add(
            f"cell{cell_id}:{DIRECTIONS[direction_index]}"
        )
        self._locks.clear()

    def mark_depth_exhausted(self, cell_id: int) -> None:
        value = int(cell_id)
        if value < 0 or value >= 6:
            raise ValueError(f"invalid depth-exhausted cell id: {value}")
        self.depth_exhausted_cell_ids.add(value)
        self._locks.clear()

    def record_previous_outcome(
        self,
        *,
        signed_depth_delta_m: Any,
        payload_gain_kg: float,
    ) -> None:
        delta = np.asarray(signed_depth_delta_m, dtype=np.float64).reshape(-1)
        if delta.size != 6 or not np.isfinite(delta).all():
            raise ValueError("previous outcome requires six finite cell deltas")
        self._previous_outcome = {
            "signed_depth_delta_m": delta.astype(float).tolist(),
            "payload_gain_kg": _finite_float(
                payload_gain_kg,
                "previous_payload_gain_kg",
            ),
            "valid": True,
        }

    def debug_fields(self) -> dict[str, Any]:
        candidate = (
            None if self._active_lock is None else self._active_lock.selection.candidate
        )
        return {
            "box_planner_source": PLANNED_BOX_SOURCE,
            "box_planner_target_cycle": int(self._active_target_cycle),
            "box_planner_candidate_id": (
                "" if candidate is None else candidate.candidate_id
            ),
            "box_planner_cell_id": self.active_cell_id,
            "box_planner_corridor_id": self.active_corridor_id,
            "box_planner_blocked_corridors": sorted(self.blocked_corridor_ids),
            "box_planner_depth_exhausted_cells": sorted(
                self.depth_exhausted_cell_ids
            ),
        }

    def _planner_config(self, env: np.ndarray) -> CandidatePlannerConfig:
        cell_long = float(env[ENV_STATE_DIG_AREA_CELL_LONG_SIZE_IDX])
        cell_short = float(env[ENV_STATE_DIG_AREA_CELL_SHORT_SIZE_IDX])
        cell_area = float(env[ENV_STATE_DIG_AREA_CELL_AREA_IDX])
        long_axis = int(round(env[ENV_STATE_DIG_AREA_LONG_AXIS_IDX]))
        if cell_long <= 0.0 or cell_short <= 0.0 or cell_area <= 0.0:
            raise ValueError("live terrain grid geometry is invalid")
        return CandidatePlannerConfig(
            support_envelope=self.support_envelope,
            cell_area_m2=cell_area,
            box_long_size_m=cell_long * 3.0,
            box_short_size_m=cell_short * 2.0,
            long_axis=long_axis,
            cut_length_m=self.cut_length_m,
            bucket_width_m=self.bucket_width_m,
            wall_inset_m=self.wall_inset_m,
            blocked_corridor_ids=frozenset(self.blocked_corridor_ids),
            depth_exhausted_cell_ids=frozenset(self.depth_exhausted_cell_ids),
            known_failure_candidate_ids=frozenset(
                self.known_failure_candidate_ids
            ),
        )


def _planned_effect_record(
    obs: Mapping[str, Any],
    *,
    candidate: BoxCutCandidate,
    cycle_index: int,
    payload_intent_kg: float,
    previous_outcome: Mapping[str, Any],
) -> dict[str, Any]:
    env = _env_state(obs)
    qpos = _fixed_vector(obs.get("qpos"), "qpos", 4)
    qvel = _fixed_vector(obs.get("qvel"), "qvel", 4)
    return {
        "effect_input_schema": EFFECT_INPUT_SCHEMA,
        "input_contract": "planned_cut",
        "pre_terrain": _pre_terrain(env),
        "execution_context": {
            "cycle_index": int(cycle_index),
            "entry_qpos": qpos,
            "entry_qvel": qvel,
            "entry_bucket_tip_xyz_m": env[
                ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX :
                ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX + 3
            ].astype(float).tolist(),
            "previous_outcome": dict(previous_outcome),
        },
        "planned_cut": {
            "entry_x_m": float(candidate.entry_x_m),
            "entry_z_m": float(candidate.entry_z_m),
            "exit_x_m": float(candidate.exit_x_m),
            "exit_z_m": float(candidate.exit_z_m),
            "direction_x": float(candidate.direction_x),
            "direction_z": float(candidate.direction_z),
            "length_m": float(candidate.cut_length_m),
            "planned_penetration_m": float(candidate.planned_depth_m),
            "planned_payload_target_kg": float(payload_intent_kg),
            "valid": True,
        },
    }


def _pre_terrain(env: np.ndarray) -> dict[str, Any]:
    return {
        "surface_depth_m": _slice6(env, ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX),
        "removed_depth_m": _slice6(env, ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX),
        "valid_mask": _slice6(env, ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX),
        "surface_valid_fraction": _slice6(
            env,
            ENV_STATE_DIG_AREA_SURFACE_VALID_FRACTION_START_IDX,
        ),
        "baseline_depth_m": _slice6(env, ENV_STATE_DIG_AREA_BASELINE_DEPTH_START_IDX),
        "grid_origin_world_m": env[
            ENV_STATE_DIG_AREA_GRID_ORIGIN_WORLD_START_IDX :
            ENV_STATE_DIG_AREA_GRID_ORIGIN_WORLD_START_IDX + 3
        ].astype(float).tolist(),
        "long_axis_unit_world": env[
            ENV_STATE_DIG_AREA_LONG_AXIS_UNIT_WORLD_START_IDX :
            ENV_STATE_DIG_AREA_LONG_AXIS_UNIT_WORLD_START_IDX + 3
        ].astype(float).tolist(),
        "short_axis_unit_world": env[
            ENV_STATE_DIG_AREA_SHORT_AXIS_UNIT_WORLD_START_IDX :
            ENV_STATE_DIG_AREA_SHORT_AXIS_UNIT_WORLD_START_IDX + 3
        ].astype(float).tolist(),
        "cell_long_size_m": float(env[ENV_STATE_DIG_AREA_CELL_LONG_SIZE_IDX]),
        "cell_short_size_m": float(env[ENV_STATE_DIG_AREA_CELL_SHORT_SIZE_IDX]),
        "cell_area_m2": float(env[ENV_STATE_DIG_AREA_CELL_AREA_IDX]),
        "reference_plane_local_y_m": float(
            env[ENV_STATE_DIG_AREA_REFERENCE_PLANE_LOCAL_Y_IDX]
        ),
    }


def _raw_goal_fields(
    candidate: BoxCutCandidate,
    *,
    payload_intent_kg: float,
) -> dict[str, float | int]:
    return {
        "operator_entry_x_m": float(candidate.entry_x_m),
        "operator_entry_y_m": 0.0,
        "operator_entry_z_m": float(candidate.entry_z_m),
        "operator_exit_x_m": float(candidate.exit_x_m),
        "operator_exit_y_m": 0.0,
        "operator_exit_z_m": float(candidate.exit_z_m),
        "operator_cut_direction_x": float(candidate.direction_x),
        "operator_cut_direction_y": 0.0,
        "operator_cut_direction_z": float(candidate.direction_z),
        "operator_cut_length_m": float(candidate.cut_length_m),
        # This is explicitly the planned penetration, never actual peak depth.
        "operator_cut_depth_peak_m": float(candidate.planned_depth_m),
        "operator_cut_payload_gain_kg": float(payload_intent_kg),
        "operator_effective_deposit_delta_kg": 0.0,
        "operator_cut_valid": 1,
    }


def _env_state(obs: Mapping[str, Any]) -> np.ndarray:
    env = np.asarray(obs.get("env_state"), dtype=np.float64).reshape(-1)
    if env.size < ENV_STATE_V2_4_DIM:
        raise ValueError(
            f"online box planner requires {ENV_STATE_V2_4_DIM}D env_state; "
            f"got {env.size}"
        )
    if not np.isfinite(env[:ENV_STATE_V2_4_DIM]).all():
        raise ValueError("online box planner env_state contains non-finite values")
    return env


def _fixed_vector(value: Any, name: str, size: int) -> list[float]:
    array = np.asarray(value, dtype=np.float64).reshape(-1)
    if array.size != size or not np.isfinite(array).all():
        raise ValueError(f"{name} must contain {size} finite values")
    return array.astype(float).tolist()


def _slice6(env: np.ndarray, start: int) -> list[float]:
    return env[start : start + 6].astype(float).tolist()


def _finite_float(value: Any, name: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


__all__ = [
    "BoxEmptyingResidualPlanService",
    "PLANNED_BOX_SOURCE",
    "PlannedRecordPredictor",
]
