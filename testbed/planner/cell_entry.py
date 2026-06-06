"""Scripted 3x2 Cell Entry planner and auditor for V2.2 pilots."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from typing import Any

import numpy as np

from testbed.planner import cell_entry_runtime as _cell_entry_runtime

CELL_ENTRY_TOKEN_DIM = 10
CELL_ENTRY_VERSION = "v2_2_cell_entry_3x2"

LONG_AXIS_X = 0
LONG_AXIS_Z = 2

AUDIT_REASON_OK = "ok"
AUDIT_REASON_GEOMETRY_UNAVAILABLE = "geometry_unavailable"
AUDIT_REASON_PLANNER_INVALID = "planner_invalid"
AUDIT_REASON_ENTRY_DELTA_TOO_LARGE = "entry_delta_too_large"
AUDIT_REASON_TARGET_CELL_MISS = "target_cell_miss"
AUDIT_REASON_DIG_LOW_PRODUCTIVITY = "dig_low_productivity"
AUDIT_REASON_RETURN_MISS = "return_miss"

AUDIT_REASON_TO_ID = {
    AUDIT_REASON_OK: 0,
    AUDIT_REASON_GEOMETRY_UNAVAILABLE: 1,
    AUDIT_REASON_PLANNER_INVALID: 2,
    AUDIT_REASON_ENTRY_DELTA_TOO_LARGE: 3,
    AUDIT_REASON_TARGET_CELL_MISS: 4,
    AUDIT_REASON_DIG_LOW_PRODUCTIVITY: 5,
    AUDIT_REASON_RETURN_MISS: 6,
}

RISK_GEOMETRY_UNAVAILABLE = 1 << 0
RISK_PLANNER_INVALID = 1 << 1
RISK_ENTRY_DELTA_TOO_LARGE = 1 << 2
RISK_TARGET_CELL_MISS = 1 << 3
RISK_DIG_LOW_PRODUCTIVITY = 1 << 4
RISK_RETURN_MISS = 1 << 5

CELL_ENTRY_RUNTIME_FACT_FIELDS = _cell_entry_runtime.CELL_ENTRY_RUNTIME_FACT_FIELDS
CELL_ENTRY_RUNTIME_STATE_FIELDS = _cell_entry_runtime.CELL_ENTRY_RUNTIME_STATE_FIELDS
CellEntryDebugSnapshot = _cell_entry_runtime.CellEntryDebugSnapshot
CellEntryRuntimeCompletionResult = _cell_entry_runtime.CellEntryRuntimeCompletionResult
CellEntryRuntimeConfig = _cell_entry_runtime.CellEntryRuntimeConfig
CellEntryRuntimeFacts = _cell_entry_runtime.CellEntryRuntimeFacts
CellEntryRuntimeService = _cell_entry_runtime.CellEntryRuntimeService
CellEntryRuntimeState = _cell_entry_runtime.CellEntryRuntimeState
CellEntryRuntimeTokenResult = _cell_entry_runtime.CellEntryRuntimeTokenResult
build_cell_entry_runtime_facts_from_mapping = (
    _cell_entry_runtime.build_cell_entry_runtime_facts_from_mapping
)
build_cell_entry_runtime_facts_from_observation_view = (
    _cell_entry_runtime.build_cell_entry_runtime_facts_from_observation_view
)
build_cell_entry_runtime_state_from_mapping = (
    _cell_entry_runtime.build_cell_entry_runtime_state_from_mapping
)
_runtime_outcome = _cell_entry_runtime._runtime_outcome


@dataclass(frozen=True)
class CellGridSpec:
    """3x2 DigArea grid expressed in the DigArea local horizontal frame."""

    long_count: int = 3
    short_count: int = 2
    half_long_m: float = 1.5
    half_short_m: float = 1.25
    long_axis: int = LONG_AXIS_Z
    entry_margin_m: float = 0.05
    entry_y_min_m: float = -0.20
    entry_y_max_m: float = 0.20

    @property
    def cell_count(self) -> int:
        return int(self.long_count * self.short_count)

    def validate(self) -> None:
        if self.long_count != 3 or self.short_count != 2:
            raise ValueError("Cell Entry V2.2 requires a fixed 3x2 grid.")
        if self.half_long_m <= 0.0 or self.half_short_m <= 0.0:
            raise ValueError("DigArea half extents must be positive.")
        if int(self.long_axis) not in {LONG_AXIS_X, LONG_AXIS_Z}:
            raise ValueError("long_axis must be 0 (x) or 2 (z).")

    def cell_id(self, *, long_index: int, short_index: int) -> int:
        long_index = int(long_index)
        short_index = int(short_index)
        if not (
            0 <= long_index < self.long_count and 0 <= short_index < self.short_count
        ):
            return -1
        return int(long_index * self.short_count + short_index)

    def indices_from_cell_id(self, cell_id: int) -> tuple[int, int]:
        cell_id = int(cell_id)
        if not (0 <= cell_id < self.cell_count):
            return -1, -1
        return int(cell_id // self.short_count), int(cell_id % self.short_count)

    def center_norm(self, *, long_index: int, short_index: int) -> tuple[float, float]:
        if self.cell_id(long_index=long_index, short_index=short_index) < 0:
            return float("nan"), float("nan")
        long_norm = -1.0 + (float(long_index) + 0.5) * 2.0 / float(self.long_count)
        short_norm = -1.0 + (float(short_index) + 0.5) * 2.0 / float(self.short_count)
        return float(long_norm), float(short_norm)

    def bounds_norm(
        self, *, long_index: int, short_index: int
    ) -> tuple[float, float, float, float]:
        if self.cell_id(long_index=long_index, short_index=short_index) < 0:
            return (float("nan"),) * 4
        long_min = -1.0 + float(long_index) * 2.0 / float(self.long_count)
        long_max = -1.0 + float(long_index + 1) * 2.0 / float(self.long_count)
        short_min = -1.0 + float(short_index) * 2.0 / float(self.short_count)
        short_max = -1.0 + float(short_index + 1) * 2.0 / float(self.short_count)
        return float(long_min), float(long_max), float(short_min), float(short_max)

    def local_from_long_short(
        self, *, long_value_m: float, short_value_m: float, y_m: float = 0.0
    ) -> tuple[float, float, float]:
        if int(self.long_axis) == LONG_AXIS_X:
            return float(long_value_m), float(y_m), float(short_value_m)
        return float(short_value_m), float(y_m), float(long_value_m)

    def long_short_from_local(self, *, x_m: float, z_m: float) -> tuple[float, float]:
        if int(self.long_axis) == LONG_AXIS_X:
            return float(x_m), float(z_m)
        return float(z_m), float(x_m)

    def local_center(
        self, *, long_index: int, short_index: int
    ) -> tuple[float, float, float]:
        long_norm, short_norm = self.center_norm(
            long_index=long_index,
            short_index=short_index,
        )
        return self.local_from_long_short(
            long_value_m=long_norm * self.half_long_m,
            short_value_m=short_norm * self.half_short_m,
        )

    def local_bounds(self, *, long_index: int, short_index: int) -> dict[str, float]:
        long_min, long_max, short_min, short_max = self.bounds_norm(
            long_index=long_index,
            short_index=short_index,
        )
        long_min_m = long_min * self.half_long_m - self.entry_margin_m
        long_max_m = long_max * self.half_long_m + self.entry_margin_m
        short_min_m = short_min * self.half_short_m - self.entry_margin_m
        short_max_m = short_max * self.half_short_m + self.entry_margin_m

        corners = [
            self.local_from_long_short(
                long_value_m=long_min_m, short_value_m=short_min_m
            ),
            self.local_from_long_short(
                long_value_m=long_max_m, short_value_m=short_max_m
            ),
        ]
        x_values = [corner[0] for corner in corners]
        z_values = [corner[2] for corner in corners]
        return {
            "x_min_m": float(min(x_values)),
            "x_max_m": float(max(x_values)),
            "y_min_m": float(self.entry_y_min_m),
            "y_max_m": float(self.entry_y_max_m),
            "z_min_m": float(min(z_values)),
            "z_max_m": float(max(z_values)),
        }

    def cell_from_norm(
        self, *, long_norm: float, short_norm: float
    ) -> tuple[int, int, int]:
        if not (np.isfinite(long_norm) and np.isfinite(short_norm)):
            return -1, -1, -1
        if long_norm < -1.0 or long_norm > 1.0 or short_norm < -1.0 or short_norm > 1.0:
            return -1, -1, -1
        long_index = min(
            self.long_count - 1,
            max(0, int(np.floor((float(long_norm) + 1.0) * 0.5 * self.long_count))),
        )
        short_index = min(
            self.short_count - 1,
            max(0, int(np.floor((float(short_norm) + 1.0) * 0.5 * self.short_count))),
        )
        return (
            int(long_index),
            int(short_index),
            self.cell_id(
                long_index=long_index,
                short_index=short_index,
            ),
        )


@dataclass(frozen=True)
class CellEntryPlannerConfig:
    cell_entry_enabled: bool
    cell_entry_grid: CellGridSpec
    cell_entry_low_productivity_payload_gain_kg: float

    def planner_items(self) -> tuple[tuple[str, Any], ...]:
        return tuple(self.__dict__.items())


CELL_ENTRY_CONFIG_KEYS: tuple[str, ...] = (
    "cell_entry_enabled",
    "cell_entry_grid",
    "cell_entry_low_productivity_payload_gain_kg",
)


def build_cell_entry_planner_config_from_mapping(
    values: Mapping[str, Any],
) -> CellEntryPlannerConfig:
    return build_cell_entry_planner_config(
        **{key: values[key] for key in CELL_ENTRY_CONFIG_KEYS}
    )


def build_cell_entry_planner_config(
    *,
    cell_entry_enabled: bool,
    cell_entry_grid: Mapping[str, Any] | None,
    cell_entry_low_productivity_payload_gain_kg: float,
) -> CellEntryPlannerConfig:
    grid = CellGridSpec(**dict(cell_entry_grid or {}))
    grid.validate()
    return CellEntryPlannerConfig(
        cell_entry_enabled=bool(cell_entry_enabled),
        cell_entry_grid=grid,
        cell_entry_low_productivity_payload_gain_kg=float(
            cell_entry_low_productivity_payload_gain_kg
        ),
    )


@dataclass(frozen=True)
class CellBelief:
    cell_id: int
    long_index: int
    short_index: int
    remaining_depth_m: float = 0.12
    visit_count: int = 0
    low_productivity_streak: int = 0
    collision_streak: int = 0
    blocked: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class EntryEnvelope:
    x_min_m: float
    x_max_m: float
    y_min_m: float
    y_max_m: float
    z_min_m: float
    z_max_m: float

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CellEntryGoal:
    cycle_id: int
    selected_cell_id: int
    selected_long_index: int
    selected_short_index: int
    planned_entry_x_m: float
    planned_entry_y_m: float
    planned_entry_z_m: float
    planned_bite_x_m: float
    planned_bite_y_m: float
    planned_bite_z_m: float
    entry_envelope: EntryEnvelope
    plan_source: str = "scripted_cell_entry"

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["entry_envelope"] = self.entry_envelope.to_dict()
        return payload


@dataclass(frozen=True)
class PrimitiveCycleOutcome:
    cycle_id: int
    actual_start_step: int
    actual_bite_step: int
    actual_removal_step: int
    actual_start_cell_id: int
    actual_bite_cell_id: int
    actual_removal_cell_id: int
    payload_gain_kg: float
    deposit_delta_kg: float
    collision_count_delta: int
    return_miss: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PlannerDecisionAudit:
    cycle_id: int
    planner_ok: bool
    risk_flags: int
    reason_code: int
    reason: str
    inside_entry_envelope: bool
    distance_to_entry_envelope_m: float
    entry_delta_x_m: float
    entry_delta_y_m: float
    entry_delta_z_m: float
    target_cell_match: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class CellEntryPlanner:
    """Rule planner over a fixed 3x2 DigArea grid."""

    def __init__(self, *, grid: CellGridSpec | None = None) -> None:
        self.grid = grid or CellGridSpec()
        self.grid.validate()
        self.reset()

    def reset(self) -> None:
        beliefs: list[CellBelief] = []
        for long_index in range(self.grid.long_count):
            for short_index in range(self.grid.short_count):
                cell_id = self.grid.cell_id(
                    long_index=long_index,
                    short_index=short_index,
                )
                beliefs.append(
                    CellBelief(
                        cell_id=cell_id,
                        long_index=long_index,
                        short_index=short_index,
                    )
                )
        self._beliefs = beliefs
        self._last_cell_id = -1

    def belief_map(self) -> list[dict[str, object]]:
        return [belief.to_dict() for belief in self._beliefs]

    def plan(self, *, cycle_id: int) -> CellEntryGoal:
        selected = self._select_cell()
        self._last_cell_id = int(selected.cell_id)
        entry_x, entry_y, entry_z = self.grid.local_center(
            long_index=selected.long_index,
            short_index=selected.short_index,
        )
        envelope = EntryEnvelope(
            **self.grid.local_bounds(
                long_index=selected.long_index,
                short_index=selected.short_index,
            )
        )
        return CellEntryGoal(
            cycle_id=int(cycle_id),
            selected_cell_id=int(selected.cell_id),
            selected_long_index=int(selected.long_index),
            selected_short_index=int(selected.short_index),
            planned_entry_x_m=float(entry_x),
            planned_entry_y_m=float(entry_y),
            planned_entry_z_m=float(entry_z),
            planned_bite_x_m=float(entry_x),
            planned_bite_y_m=float(entry_y),
            planned_bite_z_m=float(entry_z),
            entry_envelope=envelope,
        )

    def update(self, outcome: PrimitiveCycleOutcome) -> None:
        cell_id = int(outcome.actual_removal_cell_id)
        if not (0 <= cell_id < len(self._beliefs)):
            cell_id = int(self._last_cell_id)
        if not (0 <= cell_id < len(self._beliefs)):
            return

        belief = self._beliefs[cell_id]
        low_productivity = float(outcome.payload_gain_kg) < 100.0
        collision = int(outcome.collision_count_delta) > 0
        remaining = max(
            0.0,
            float(belief.remaining_depth_m) - (0.04 if not low_productivity else 0.0),
        )
        self._beliefs[cell_id] = replace(
            belief,
            remaining_depth_m=float(remaining),
            visit_count=int(belief.visit_count) + 1,
            low_productivity_streak=(
                int(belief.low_productivity_streak) + 1 if low_productivity else 0
            ),
            collision_streak=int(belief.collision_streak) + 1 if collision else 0,
            blocked=bool(
                belief.blocked or int(belief.collision_streak) + int(collision) >= 2
            ),
        )

    def _select_cell(self) -> CellBelief:
        scored: list[tuple[float, float, int, CellBelief]] = []
        for belief in self._beliefs:
            if belief.blocked:
                continue
            center_bonus = 1.0 if belief.long_index == 1 else 0.0
            remaining_norm = float(np.clip(belief.remaining_depth_m / 0.12, 0.0, 1.0))
            revisit_penalty = float(
                np.clip(max(belief.visit_count - 1, 0) / 3.0, 0.0, 1.0)
            )
            low_productivity_penalty = float(
                np.clip(belief.low_productivity_streak / 2.0, 0.0, 1.0)
            )
            if self._last_cell_id >= 0:
                last_long, last_short = self.grid.indices_from_cell_id(
                    self._last_cell_id
                )
                distance = abs(belief.long_index - last_long) + abs(
                    belief.short_index - last_short
                )
                continuity = 1.0 / (1.0 + float(distance))
            else:
                continuity = center_bonus
            score = (
                0.50 * remaining_norm
                + 0.20 * continuity
                + 0.15 * center_bonus
                - 0.10 * revisit_penalty
                - 0.05 * low_productivity_penalty
            )
            scored.append(
                (float(score), float(continuity), -int(belief.cell_id), belief)
            )

        if not scored:
            return self._beliefs[0]
        scored.sort(reverse=True)
        return scored[0][3]


class PlannerDecisionAuditor:
    def __init__(
        self,
        *,
        grid: CellGridSpec | None = None,
        low_productivity_payload_gain_kg: float = 100.0,
    ) -> None:
        self.grid = grid or CellGridSpec()
        self.low_productivity_payload_gain_kg = float(low_productivity_payload_gain_kg)

    def audit(
        self,
        *,
        goal: CellEntryGoal,
        outcome: PrimitiveCycleOutcome,
        current_bucket_pose: tuple[float, float, float] | None,
        geometry_available: bool,
    ) -> PlannerDecisionAudit:
        risk_flags = 0
        reasons: list[str] = []

        valid_cell = 0 <= int(goal.selected_cell_id) < self.grid.cell_count
        if not valid_cell:
            risk_flags |= RISK_PLANNER_INVALID
            reasons.append(AUDIT_REASON_PLANNER_INVALID)

        if not geometry_available:
            risk_flags |= RISK_GEOMETRY_UNAVAILABLE
            reasons.append(AUDIT_REASON_GEOMETRY_UNAVAILABLE)

        if current_bucket_pose is None:
            delta_x = delta_y = delta_z = float("nan")
            inside = False
            distance = float("nan")
        else:
            x, y, z = [float(value) for value in current_bucket_pose]
            delta_x = x - float(goal.planned_entry_x_m)
            delta_y = y - float(goal.planned_entry_y_m)
            delta_z = z - float(goal.planned_entry_z_m)
            inside = _inside_envelope(goal.entry_envelope, x=x, y=y, z=z)
            distance = distance_to_envelope(goal.entry_envelope, x=x, y=y, z=z)
            if not inside:
                risk_flags |= RISK_ENTRY_DELTA_TOO_LARGE
                reasons.append(AUDIT_REASON_ENTRY_DELTA_TOO_LARGE)

        actual_cells = [
            int(outcome.actual_start_cell_id),
            int(outcome.actual_bite_cell_id),
            int(outcome.actual_removal_cell_id),
        ]
        target_cell_match = all(
            cell_id < 0 or cell_id == int(goal.selected_cell_id)
            for cell_id in actual_cells
        )
        if any(cell_id >= 0 for cell_id in actual_cells) and not target_cell_match:
            risk_flags |= RISK_TARGET_CELL_MISS
            reasons.append(AUDIT_REASON_TARGET_CELL_MISS)

        if float(outcome.payload_gain_kg) < self.low_productivity_payload_gain_kg:
            risk_flags |= RISK_DIG_LOW_PRODUCTIVITY
            reasons.append(AUDIT_REASON_DIG_LOW_PRODUCTIVITY)

        if bool(outcome.return_miss):
            risk_flags |= RISK_RETURN_MISS
            reasons.append(AUDIT_REASON_RETURN_MISS)

        reason = reasons[0] if reasons else AUDIT_REASON_OK
        planner_ok = bool(valid_cell and risk_flags == 0)
        return PlannerDecisionAudit(
            cycle_id=int(goal.cycle_id),
            planner_ok=planner_ok,
            risk_flags=int(risk_flags),
            reason_code=int(AUDIT_REASON_TO_ID.get(reason, -1)),
            reason=str(reason),
            inside_entry_envelope=bool(inside),
            distance_to_entry_envelope_m=float(distance),
            entry_delta_x_m=float(delta_x),
            entry_delta_y_m=float(delta_y),
            entry_delta_z_m=float(delta_z),
            target_cell_match=bool(target_cell_match),
        )


def _inside_envelope(envelope: EntryEnvelope, *, x: float, y: float, z: float) -> bool:
    return bool(
        envelope.x_min_m <= x <= envelope.x_max_m
        and envelope.y_min_m <= y <= envelope.y_max_m
        and envelope.z_min_m <= z <= envelope.z_max_m
    )


def distance_to_envelope(
    envelope: EntryEnvelope, *, x: float, y: float, z: float
) -> float:
    dx = max(float(envelope.x_min_m) - x, 0.0, x - float(envelope.x_max_m))
    dy = max(float(envelope.y_min_m) - y, 0.0, y - float(envelope.y_max_m))
    dz = max(float(envelope.z_min_m) - z, 0.0, z - float(envelope.z_max_m))
    return float(np.sqrt(dx * dx + dy * dy + dz * dz))


def build_cell_entry_tokens(
    *,
    grid: CellGridSpec,
    goal: CellEntryGoal,
    audit: PlannerDecisionAudit,
) -> np.ndarray:
    long_norm, short_norm = grid.center_norm(
        long_index=int(goal.selected_long_index),
        short_index=int(goal.selected_short_index),
    )
    entry_delta_long, entry_delta_short = grid.long_short_from_local(
        x_m=float(audit.entry_delta_x_m),
        z_m=float(audit.entry_delta_z_m),
    )
    cell_norm = (
        float(goal.selected_cell_id) / float(max(grid.cell_count - 1, 1))
        if int(goal.selected_cell_id) >= 0
        else -1.0
    )
    distance_norm = (
        0.0
        if not np.isfinite(audit.distance_to_entry_envelope_m)
        else float(
            np.clip(audit.distance_to_entry_envelope_m / grid.half_long_m, 0.0, 1.0)
        )
    )
    return np.asarray(
        [
            cell_norm,
            long_norm,
            short_norm,
            long_norm,
            short_norm,
            (
                float(np.clip(entry_delta_long / grid.half_long_m, -1.0, 1.0))
                if np.isfinite(entry_delta_long)
                else 0.0
            ),
            (
                float(np.clip(entry_delta_short / grid.half_short_m, -1.0, 1.0))
                if np.isfinite(entry_delta_short)
                else 0.0
            ),
            1.0 if audit.inside_entry_envelope else 0.0,
            distance_norm,
            1.0 if audit.planner_ok else 0.0,
        ],
        dtype=np.float32,
    )


def env_cell_geometry_available(
    env_state_row: np.ndarray, *, available_index: int
) -> bool:
    arr = np.asarray(env_state_row, dtype=np.float32).reshape(-1)
    return bool(len(arr) > available_index and float(arr[available_index]) > 0.5)
