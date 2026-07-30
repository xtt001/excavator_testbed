"""Online residual progress monitor and bounded box-emptying stops."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from testbed.data.schema import (
    ENV_STATE_DIG_AREA_CELL_AREA_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
)
from testbed.planner.box_emptying.contracts import TerrainBoxResidual
from testbed.planner.box_emptying.stop_conditions import (
    BoxEmptyingStopController,
    CycleOutcome,
)


class BoxEmptyingRuntimeContractError(RuntimeError):
    """Raised when a cycle closes without stable residual evidence."""


@dataclass(frozen=True)
class RuntimeMonitorConfig:
    stable_window_steps: int = 10
    max_depth_range_m: float = 0.002
    empty_fraction: float = 0.05
    empty_hold_observations: int = 3
    low_payload_kg: float = 15.0
    low_progress_m3: float = 0.005
    ineffective_limit: int = 3
    max_cycles: int = 120

    def __post_init__(self) -> None:
        if self.stable_window_steps <= 0:
            raise ValueError("stable_window_steps must be positive")
        if self.max_depth_range_m < 0.0:
            raise ValueError("max_depth_range_m must be non-negative")


@dataclass(frozen=True)
class RuntimeMonitorDecision:
    stop: bool = False
    reason: str = ""
    dump_before_stop: bool = False
    completed_cycle_outcome: CycleOutcome | None = None
    completed_signed_depth_delta_m: tuple[float, ...] | None = None


class BoxEmptyingRuntimeMonitor:
    """Use stable 10-step residuals for progress and exact stop semantics."""

    def __init__(self, config: RuntimeMonitorConfig | None = None) -> None:
        self.config = config or RuntimeMonitorConfig()
        self.controller = BoxEmptyingStopController(
            empty_fraction=self.config.empty_fraction,
            empty_hold_observations=self.config.empty_hold_observations,
            low_payload_kg=self.config.low_payload_kg,
            low_progress_m3=self.config.low_progress_m3,
            ineffective_limit=self.config.ineffective_limit,
            max_cycles=self.config.max_cycles,
        )
        self.reset()

    def reset(self) -> None:
        self.controller.reset()
        self._cycle_index: int | None = None
        self._window: deque[tuple[TerrainBoxResidual, float]] = deque(
            maxlen=int(self.config.stable_window_steps)
        )
        self._cycle_start_stable: tuple[TerrainBoxResidual, float] | None = None
        self._cycle_latest_stable: tuple[TerrainBoxResidual, float] | None = None
        self._cycle_peak_payload_kg = 0.0
        self._last_step_id: int | None = None
        self._last_decision = RuntimeMonitorDecision()

    def observe(
        self,
        obs: Mapping[str, Any],
        *,
        cycle_index: int,
    ) -> RuntimeMonitorDecision:
        step_id = int(obs.get("step_id", -1))
        if self._last_step_id is not None and step_id == self._last_step_id:
            return self._last_decision
        if self._last_step_id is not None and step_id < self._last_step_id:
            raise BoxEmptyingRuntimeContractError("step_id_regressed")
        env = np.asarray(obs.get("env_state"), dtype=np.float64).reshape(-1)
        residual = TerrainBoxResidual.from_env_state(env)
        if env.size <= ENV_STATE_DIG_AREA_CELL_AREA_IDX:
            raise BoxEmptyingRuntimeContractError("cell_area_missing")
        cell_area = float(env[ENV_STATE_DIG_AREA_CELL_AREA_IDX])
        if not np.isfinite(cell_area) or cell_area <= 0.0:
            raise BoxEmptyingRuntimeContractError("cell_area_invalid")
        payload = float(env[ENV_STATE_MASS_IN_BUCKET_IDX])
        if not np.isfinite(payload) or payload < 0.0:
            raise BoxEmptyingRuntimeContractError("payload_invalid")

        target_cycle = int(cycle_index)
        completed_outcome: CycleOutcome | None = None
        signed_delta: tuple[float, ...] | None = None
        cycle_stop = None
        if self._cycle_index is None:
            self._cycle_index = target_cycle
        elif target_cycle != self._cycle_index:
            if target_cycle != self._cycle_index + 1:
                raise BoxEmptyingRuntimeContractError(
                    "cycle_index_must_advance_exactly_once"
                )
            completed_outcome, signed_delta = self._finalize_cycle()
            cycle_stop = self.controller.record_cycle(completed_outcome)
            self._cycle_index = target_cycle
            self._window.clear()
            self._cycle_start_stable = None
            self._cycle_latest_stable = None
            self._cycle_peak_payload_kg = 0.0

        self._cycle_peak_payload_kg = max(self._cycle_peak_payload_kg, payload)
        self._window.append((residual, cell_area))
        stable = self._stable_window_snapshot()
        if stable is not None:
            if self._cycle_start_stable is None:
                self._cycle_start_stable = stable
            self._cycle_latest_stable = stable

        residual_stop = self.controller.observe_residual(
            residual,
            payload_kg=payload,
        )
        selected = cycle_stop if cycle_stop is not None and cycle_stop.stop else residual_stop
        decision = RuntimeMonitorDecision(
            stop=bool(selected.stop),
            reason=str(selected.reason),
            dump_before_stop=bool(selected.dump_before_stop),
            completed_cycle_outcome=completed_outcome,
            completed_signed_depth_delta_m=signed_delta,
        )
        self._last_step_id = step_id
        self._last_decision = decision
        return decision

    def latest_stable_outcome(
        self,
    ) -> tuple[tuple[float, ...], float] | None:
        """Return the current cycle's stable executed outcome, if observable."""

        if self._cycle_start_stable is None or self._cycle_latest_stable is None:
            return None
        start, start_area = self._cycle_start_stable
        end, end_area = self._cycle_latest_stable
        if abs(start_area - end_area) > 1.0e-6:
            raise BoxEmptyingRuntimeContractError("cell_area_changed_within_cycle")
        signed_depth = (
            np.asarray(start.remaining_volume_m3)
            - np.asarray(end.remaining_volume_m3)
        ) / start_area
        return (
            tuple(float(value) for value in signed_depth),
            float(self._cycle_peak_payload_kg),
        )

    def _stable_window_snapshot(
        self,
    ) -> tuple[TerrainBoxResidual, float] | None:
        if len(self._window) < int(self.config.stable_window_steps):
            return None
        areas = np.asarray([item[1] for item in self._window], dtype=np.float64)
        if np.ptp(areas) > 1.0e-6:
            return None
        volumes = np.asarray(
            [item[0].remaining_volume_m3 for item in self._window],
            dtype=np.float64,
        )
        depths = volumes / areas[:, None]
        if np.any(np.ptp(depths, axis=0) > self.config.max_depth_range_m):
            return None
        median_volume = np.median(volumes, axis=0)
        latest = self._window[-1][0]
        snapshot = TerrainBoxResidual(
            remaining_volume_m3=tuple(float(value) for value in median_volume),  # type: ignore[arg-type]
            hard_bottom_depth_m=latest.hard_bottom_depth_m,
            soil_density_kg_m3=latest.soil_density_kg_m3,
            current_remaining_mass_kg=latest.current_remaining_mass_kg,
            initial_remaining_mass_kg=latest.initial_remaining_mass_kg,
            remaining_fraction=latest.remaining_fraction,
            valid=True,
        )
        return snapshot, float(np.median(areas))

    def _finalize_cycle(
        self,
    ) -> tuple[CycleOutcome, tuple[float, ...]]:
        if self._cycle_start_stable is None or self._cycle_latest_stable is None:
            raise BoxEmptyingRuntimeContractError(
                "cycle_completed_without_stable_residual_window"
            )
        start, start_area = self._cycle_start_stable
        end, end_area = self._cycle_latest_stable
        if abs(start_area - end_area) > 1.0e-6:
            raise BoxEmptyingRuntimeContractError("cell_area_changed_within_cycle")
        signed_volume = np.asarray(start.remaining_volume_m3) - np.asarray(
            end.remaining_volume_m3
        )
        signed_depth = signed_volume / start_area
        net_removed = max(0.0, float(np.sum(signed_volume)))
        return (
            CycleOutcome(
                payload_kg=float(self._cycle_peak_payload_kg),
                stable_net_removed_volume_m3=net_removed,
            ),
            tuple(float(value) for value in signed_depth),
        )


__all__ = [
    "BoxEmptyingRuntimeContractError",
    "BoxEmptyingRuntimeMonitor",
    "RuntimeMonitorConfig",
    "RuntimeMonitorDecision",
]
