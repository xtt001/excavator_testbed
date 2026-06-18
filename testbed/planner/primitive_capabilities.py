"""Read-only primitive planner capability facts."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

import numpy as np

from testbed.data.schema import (
    ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
    ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
    ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
    ENV_STATE_DUMP_CLEARANCE_OK_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
)


@dataclass(frozen=True)
class PrimitiveObservationFacts:
    """Typed read-only facts projected from a primitive planner observation."""

    qpos: np.ndarray
    qvel: np.ndarray
    env_state: np.ndarray
    task_metrics: MappingProxyType[str, Any]
    reward_phase: Any | None
    task_step_successes: Any | None

    @classmethod
    def from_obs(
        cls,
        obs: dict[str, Any],
        *,
        action_dim: int,
    ) -> "PrimitiveObservationFacts":
        return cls(
            qpos=_readonly_array(
                obs.get("qpos", np.zeros(int(action_dim), dtype=np.float32))
            ),
            qvel=_readonly_array(
                obs.get("qvel", np.zeros(int(action_dim), dtype=np.float32))
            ),
            env_state=_readonly_array(
                obs.get("env_state", np.zeros(13, dtype=np.float32))
            ),
            task_metrics=MappingProxyType(dict(obs.get("task_metrics", {}) or {})),
            reward_phase=obs.get("reward_phase"),
            task_step_successes=obs.get("task_step_successes"),
        )

    @property
    def mass_in_bucket_kg(self) -> float:
        if "mass_in_bucket_kg" in self.task_metrics:
            return float(self.task_metrics["mass_in_bucket_kg"])
        return self.env_state_value(ENV_STATE_MASS_IN_BUCKET_IDX, default=0.0)

    @property
    def deposited_mass_in_target_box_kg(self) -> float:
        if "deposited_mass_in_target_box_kg" in self.task_metrics:
            return float(self.task_metrics["deposited_mass_in_target_box_kg"])
        return self.env_state_value(
            ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX,
            default=0.0,
        )

    def target_geometry(self) -> dict[str, float]:
        available = self.task_metrics.get("target_geometry_available")
        if available is not None and float(available) <= 0.5:
            raise RuntimeError(
                "primitive carry->dump switch requires target_geometry_available=1."
            )

        return {
            "target_horizontal_distance_m": self._metric(
                "target_horizontal_distance_m",
                ENV_STATE_TARGET_HORIZONTAL_DISTANCE_IDX,
            ),
            "bucket_height_above_target_rim_m": self._metric(
                "bucket_height_above_target_rim_m",
                ENV_STATE_BUCKET_HEIGHT_ABOVE_TARGET_RIM_IDX,
            ),
            "bucket_over_target_footprint_mask": self._metric(
                "bucket_over_target_footprint_mask",
                ENV_STATE_BUCKET_OVER_TARGET_FOOTPRINT_IDX,
            ),
            "dump_clearance_ok_mask": self._metric(
                "dump_clearance_ok_mask",
                ENV_STATE_DUMP_CLEARANCE_OK_IDX,
            ),
            "bucket_dump_area_relative_x_m": self._optional_metric(
                "bucket_dump_area_relative_x_m",
                ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_X_IDX,
            ),
            "bucket_dump_area_relative_z_m": self._optional_metric(
                "bucket_dump_area_relative_z_m",
                ENV_STATE_BUCKET_DUMP_AREA_RELATIVE_Z_IDX,
            ),
            "bucket_dump_area_footprint_outside_distance_m": self._optional_metric(
                "bucket_dump_area_footprint_outside_distance_m",
                ENV_STATE_BUCKET_DUMP_AREA_FOOTPRINT_OUTSIDE_DISTANCE_IDX,
            ),
        }

    def env_state_value(self, index: int, *, default: float = float("nan")) -> float:
        if len(self.env_state) <= int(index):
            return float(default)
        return float(self.env_state[int(index)])

    def _metric(self, name: str, index: int) -> float:
        if name in self.task_metrics:
            value = float(self.task_metrics[name])
            if np.isfinite(value):
                return value
        if len(self.env_state) <= int(index):
            raise RuntimeError(
                "primitive carry->dump switch requires Unity target geometry "
                f"field {name!r}; no legacy fallback is used."
            )
        value = float(self.env_state[int(index)])
        if not np.isfinite(value):
            raise RuntimeError(
                "primitive carry->dump switch received non-finite target geometry "
                f"field {name!r}."
            )
        return value

    def _optional_metric(self, name: str, index: int) -> float:
        if name in self.task_metrics:
            value = float(self.task_metrics[name])
            return value if np.isfinite(value) else float("nan")
        return self.env_state_value(index, default=float("nan"))


def _readonly_array(value: Any) -> np.ndarray:
    array = np.asarray(value, dtype=np.float32).reshape(-1).copy()
    array.setflags(write=False)
    return array


__all__ = ["PrimitiveObservationFacts"]
