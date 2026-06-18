"""Primitive planner token providers."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

import numpy as np

from testbed.data.dig_depth_profile_v2_4 import (
    DIG_DEPTH_PROFILE_TOKEN_DIM,
    build_dig_depth_profile_token_from_plan,
)
from testbed.data.operator_first_v2_2 import (
    _build_dig_cut_token,
    build_live_dig_cut_tokens_from_pose,
)
from testbed.data.v2_1 import build_goal_tokens


PRIMITIVE_GOAL_SECTOR_IDS = {"left": 0, "mid": 1, "right": 2}


@dataclass(frozen=True)
class GoalTokenProvider:
    """Build goal tokens from the configured primitive goal sequence."""

    goal_sequence: tuple[int, ...]
    scenario_id: str = "s0_truck"
    depth_norm: float = 0.0
    dump_target_norm: float = 0.0

    @classmethod
    def from_inputs(
        cls,
        *,
        goal_sequence: list[str] | tuple[str, ...] | list[int] | tuple[int, ...] | None,
        scenario_id: str = "s0_truck",
        depth_norm: float = 0.0,
        dump_target_norm: float = 0.0,
    ) -> "GoalTokenProvider":
        return cls(
            goal_sequence=cls.normalize_goal_sequence(goal_sequence),
            scenario_id=str(scenario_id),
            depth_norm=float(depth_norm),
            dump_target_norm=float(dump_target_norm),
        )

    @staticmethod
    def normalize_goal_sequence(
        goal_sequence: list[str] | tuple[str, ...] | list[int] | tuple[int, ...] | None,
    ) -> tuple[int, ...]:
        if not goal_sequence:
            return ()
        normalized: list[int] = []
        for item in goal_sequence:
            if isinstance(item, str):
                key = item.strip().lower()
                if key not in PRIMITIVE_GOAL_SECTOR_IDS:
                    raise ValueError(
                        f"Unknown primitive goal sector {item!r}. Expected left, mid, or right."
                    )
                normalized.append(PRIMITIVE_GOAL_SECTOR_IDS[key])
            else:
                value = int(item)
                if value < 0 or value > 2:
                    raise ValueError(
                        f"Primitive goal sector id must be 0, 1, or 2, got {item!r}."
                    )
                normalized.append(value)
        return tuple(normalized)

    def tokens_for_cycle(self, cycle_index: int) -> np.ndarray | None:
        if not self.goal_sequence:
            return None
        curr_sector_id = self.sector_id(cycle_index)
        next_sector_id = self.next_sector_id(cycle_index)
        return build_goal_tokens(
            self.scenario_id,
            curr_sector_id=curr_sector_id,
            curr_cut_depth_norm=self.depth_norm,
            next_sector_id=next_sector_id,
            next_cut_depth_norm=self.depth_norm,
            dst_target_norm=self.dump_target_norm,
            has_lookahead=next_sector_id >= 0,
        )

    def sector_id(self, cycle_index: int) -> int:
        if not self.goal_sequence:
            return -1
        index = max(0, min(int(cycle_index), len(self.goal_sequence) - 1))
        return int(self.goal_sequence[index])

    def next_sector_id(self, cycle_index: int) -> int:
        if not self.goal_sequence:
            return -1
        next_index = int(cycle_index) + 1
        if next_index >= len(self.goal_sequence):
            return -1
        return int(self.goal_sequence[next_index])


@dataclass(frozen=True)
class DigCutTokenPlan:
    """Result of planning one dig-cut token."""

    token: np.ndarray
    raw_fields: MappingProxyType[str, float | int]
    source: str
    fallback_reason: str
    in_prior_p10_p90: bool


@dataclass(frozen=True)
class DigCutTokenPlanner:
    """Build dig-cut tokens from live pose, prior fields, or selected raw fields."""

    prior: dict[str, Any]

    def plan_conservative_pose(
        self,
        pose: tuple[float, float, float] | None,
    ) -> DigCutTokenPlan:
        raw_fields = self.raw_fields_from_live_pose(pose)
        return self._plan(
            token=build_live_dig_cut_tokens_from_pose(pose),
            raw_fields=raw_fields,
            source="conservative_pose",
            fallback_reason="",
            in_prior_p10_p90=False,
        )

    def plan_fallback_conservative_pose(
        self,
        pose: tuple[float, float, float] | None,
        *,
        fallback_reason: str,
    ) -> DigCutTokenPlan:
        raw_fields = self.raw_fields_from_live_pose(pose)
        return self._plan(
            token=build_live_dig_cut_tokens_from_pose(pose),
            raw_fields=raw_fields,
            source="fallback_conservative_pose",
            fallback_reason=fallback_reason,
            in_prior_p10_p90=False,
        )

    def plan_operator_prior(
        self,
        pose: tuple[float, float, float] | None,
    ) -> DigCutTokenPlan:
        if not self.prior:
            raise ValueError("operator_prior mode requires a dig cut prior JSON.")
        fields = dict(self.prior.get("fields", {}))
        fallback_reason = ""
        if pose is None:
            entry_x = self.prior_percentile(fields, "entry_x_m", "p50")
            entry_y = 0.0
            entry_z = self.prior_percentile(fields, "entry_z_m", "p50")
            source = "operator_prior_median_pose_fallback"
            fallback_reason = "missing_bucket_dig_area_pose"
        else:
            entry_x = self.clamp_to_prior(fields, "entry_x_m", float(pose[0]))
            entry_y = float(pose[1])
            entry_z = self.clamp_to_prior(fields, "entry_z_m", float(pose[2]))
            source = "operator_prior_pose_clamped"

        dir_x = self.prior_percentile(fields, "cut_direction_x", "p50")
        dir_z = self.prior_percentile(fields, "cut_direction_z", "p50")
        norm = float(np.hypot(dir_x, dir_z))
        if norm <= 1.0e-6:
            dir_x, dir_z = -1.0, 0.0
        else:
            dir_x, dir_z = dir_x / norm, dir_z / norm
        length = self.prior_percentile(fields, "cut_length_m", "p50")
        exit_x = self.clamp_to_prior(fields, "exit_x_m", entry_x + dir_x * length)
        exit_z = self.clamp_to_prior(fields, "exit_z_m", entry_z + dir_z * length)

        delta_x = exit_x - entry_x
        delta_z = exit_z - entry_z
        generated_length = float(np.hypot(delta_x, delta_z))
        if generated_length > 1.0e-6:
            dir_x = delta_x / generated_length
            dir_z = delta_z / generated_length
            length = generated_length

        raw_fields = {
            "operator_entry_x_m": float(entry_x),
            "operator_entry_y_m": float(entry_y),
            "operator_entry_z_m": float(entry_z),
            "operator_exit_x_m": float(exit_x),
            "operator_exit_y_m": float(entry_y),
            "operator_exit_z_m": float(exit_z),
            "operator_cut_direction_x": float(
                self.clamp_to_prior(fields, "cut_direction_x", dir_x)
            ),
            "operator_cut_direction_y": 0.0,
            "operator_cut_direction_z": float(
                self.clamp_to_prior(fields, "cut_direction_z", dir_z)
            ),
            "operator_cut_length_m": float(
                self.clamp_to_prior(fields, "cut_length_m", length)
            ),
            "operator_cut_depth_peak_m": float(
                self.prior_percentile(fields, "cut_depth_peak_m", "p50")
            ),
            "operator_cut_payload_gain_kg": float(
                self.prior_percentile(fields, "payload_gain_kg", "p50")
            ),
            "operator_effective_deposit_delta_kg": float(
                self.prior_percentile(fields, "effective_deposit_delta_kg", "p50")
            ),
            "operator_cut_valid": 1,
        }
        return self.plan_from_raw_fields(
            raw_fields,
            source=source,
            fallback_reason=fallback_reason,
        )

    def plan_pending_return_target(
        self,
        *,
        tokens: np.ndarray,
        raw_fields: dict[str, float | int] | None,
    ) -> DigCutTokenPlan:
        return self._plan(
            token=np.asarray(tokens, dtype=np.float32).reshape(-1),
            raw_fields={} if raw_fields is None else dict(raw_fields),
            source="pending_return_target",
            fallback_reason="",
            in_prior_p10_p90=(
                False if raw_fields is None else self.raw_fields_in_prior_range(raw_fields)
            ),
        )

    def plan_from_raw_fields(
        self,
        raw_fields: dict[str, float | int],
        *,
        source: str,
        fallback_reason: str = "",
    ) -> DigCutTokenPlan:
        return self._plan(
            token=_build_dig_cut_token(dict(raw_fields)),
            raw_fields=dict(raw_fields),
            source=source,
            fallback_reason=fallback_reason,
            in_prior_p10_p90=self.raw_fields_in_prior_range(raw_fields),
        )

    @staticmethod
    def raw_fields_from_live_pose(
        pose: tuple[float, float, float] | None,
    ) -> dict[str, float | int]:
        if pose is None:
            return {
                "operator_entry_x_m": 0.0,
                "operator_entry_y_m": 0.0,
                "operator_entry_z_m": 0.0,
                "operator_exit_x_m": 0.0,
                "operator_exit_y_m": 0.0,
                "operator_exit_z_m": 0.0,
                "operator_cut_direction_x": 0.0,
                "operator_cut_direction_y": 0.0,
                "operator_cut_direction_z": 0.0,
                "operator_cut_length_m": 0.0,
                "operator_cut_depth_peak_m": 0.0,
                "operator_cut_payload_gain_kg": 0.0,
                "operator_effective_deposit_delta_kg": 0.0,
                "operator_cut_valid": 0,
            }
        entry_x, entry_y, entry_z = float(pose[0]), float(pose[1]), float(pose[2])
        exit_x = entry_x - 1.2
        exit_z = entry_z
        return {
            "operator_entry_x_m": entry_x,
            "operator_entry_y_m": entry_y,
            "operator_entry_z_m": entry_z,
            "operator_exit_x_m": exit_x,
            "operator_exit_y_m": entry_y,
            "operator_exit_z_m": exit_z,
            "operator_cut_direction_x": -1.0,
            "operator_cut_direction_y": 0.0,
            "operator_cut_direction_z": 0.0,
            "operator_cut_length_m": 1.2,
            "operator_cut_depth_peak_m": 0.08,
            "operator_cut_payload_gain_kg": 55.0,
            "operator_effective_deposit_delta_kg": 55.0,
            "operator_cut_valid": 1,
        }

    @staticmethod
    def prior_percentile(
        fields: dict[str, Any],
        field_name: str,
        percentile: str,
    ) -> float:
        try:
            return float(fields[field_name][percentile])
        except KeyError as exc:
            raise KeyError(f"Missing prior field {field_name}.{percentile}") from exc

    def clamp_to_prior(
        self,
        fields: dict[str, Any],
        field_name: str,
        value: float,
    ) -> float:
        lo = self.prior_percentile(fields, field_name, "p10")
        hi = self.prior_percentile(fields, field_name, "p90")
        return float(np.clip(float(value), lo, hi))

    def raw_fields_in_prior_range(self, raw_fields: dict[str, float | int]) -> bool:
        if not self.prior:
            return False
        fields = dict(self.prior.get("fields", {}))
        mapping = {
            "operator_entry_x_m": "entry_x_m",
            "operator_entry_z_m": "entry_z_m",
            "operator_exit_x_m": "exit_x_m",
            "operator_exit_z_m": "exit_z_m",
            "operator_cut_direction_x": "cut_direction_x",
            "operator_cut_direction_z": "cut_direction_z",
            "operator_cut_length_m": "cut_length_m",
            "operator_cut_depth_peak_m": "cut_depth_peak_m",
            "operator_cut_payload_gain_kg": "payload_gain_kg",
        }
        for raw_name, prior_name in mapping.items():
            value = float(raw_fields.get(raw_name, np.nan))
            lo = self.prior_percentile(fields, prior_name, "p10")
            hi = self.prior_percentile(fields, prior_name, "p90")
            if not np.isfinite(value) or value < lo - 1.0e-6 or value > hi + 1.0e-6:
                return False
        return True

    @staticmethod
    def _plan(
        *,
        token: np.ndarray,
        raw_fields: dict[str, float | int],
        source: str,
        fallback_reason: str,
        in_prior_p10_p90: bool,
    ) -> DigCutTokenPlan:
        token_array = np.asarray(token, dtype=np.float32).reshape(-1).copy()
        token_array.setflags(write=False)
        return DigCutTokenPlan(
            token=token_array,
            raw_fields=MappingProxyType(dict(raw_fields)),
            source=str(source),
            fallback_reason=str(fallback_reason),
            in_prior_p10_p90=bool(in_prior_p10_p90),
        )


@dataclass(frozen=True)
class ReturnTargetTokenPlan:
    """Result of planning one return-target token."""

    token: np.ndarray
    raw_fields: MappingProxyType[str, float | int]
    source: str
    fallback_reason: str
    corridor_id: int


@dataclass(frozen=True)
class ReturnTargetTokenPlanner:
    """Build return-target tokens while preserving source prefix semantics."""

    dig_cut_planner: DigCutTokenPlanner
    source_prefix: str

    def plan_conservative_pose(
        self,
        pose: tuple[float, float, float] | None,
    ) -> ReturnTargetTokenPlan:
        dig_cut_plan = self.dig_cut_planner.plan_conservative_pose(pose)
        return self._from_dig_cut_plan(
            dig_cut_plan,
            source=f"{self.source_prefix}_conservative_pose",
            corridor_id=-1,
        )

    def plan_operator_prior(
        self,
        pose: tuple[float, float, float] | None,
    ) -> ReturnTargetTokenPlan:
        dig_cut_plan = self.dig_cut_planner.plan_operator_prior(pose)
        return self._from_dig_cut_plan(
            dig_cut_plan,
            source=f"{self.source_prefix}_{dig_cut_plan.source}",
            corridor_id=-1,
        )

    def plan_from_coverage_raw_fields(
        self,
        raw_fields: dict[str, float | int],
        *,
        dig_cut_planner_mode: str,
        corridor_id: int,
    ) -> ReturnTargetTokenPlan:
        dig_cut_plan = self.dig_cut_planner.plan_from_raw_fields(
            raw_fields,
            source=str(dig_cut_planner_mode),
        )
        return self._from_dig_cut_plan(
            dig_cut_plan,
            source=f"{self.source_prefix}_{dig_cut_planner_mode}",
            corridor_id=int(corridor_id),
        )

    @staticmethod
    def _from_dig_cut_plan(
        dig_cut_plan: DigCutTokenPlan,
        *,
        source: str,
        corridor_id: int,
    ) -> ReturnTargetTokenPlan:
        token = np.asarray(dig_cut_plan.token, dtype=np.float32).reshape(-1).copy()
        token.setflags(write=False)
        return ReturnTargetTokenPlan(
            token=token,
            raw_fields=MappingProxyType(dict(dig_cut_plan.raw_fields)),
            source=str(source),
            fallback_reason=str(dig_cut_plan.fallback_reason),
            corridor_id=int(corridor_id),
        )


class DigDepthProfileTokenPlanningError(ValueError):
    """Raised when a required dig-depth-profile token cannot be planned."""

    def __init__(
        self,
        message: str,
        *,
        token_source: str,
        fallback_reason: str,
    ) -> None:
        super().__init__(message)
        self.token_source = str(token_source)
        self.fallback_reason = str(fallback_reason)


@dataclass(frozen=True)
class DigDepthProfileTokenPlan:
    """Result of planning one dig-depth-profile token."""

    token: np.ndarray
    source: str
    fallback_reason: str


@dataclass(frozen=True)
class DigDepthProfileTokenPlanner:
    """Build dig-depth-profile tokens from live plans or profile priors."""

    prior: dict[str, Any]
    source: str = "live_plan"
    required: bool = False
    allow_live_fallback: bool = True
    allow_global_fallback: bool = True

    def plan(
        self,
        *,
        cell_id: int,
        raw_fields: dict[str, float | int],
        env_state: np.ndarray,
        state_exemplar_profile_token: np.ndarray | None = None,
    ) -> DigDepthProfileTokenPlan:
        if self.source == "prior_profile":
            if state_exemplar_profile_token is not None:
                return self._plan(
                    token=np.asarray(
                        state_exemplar_profile_token,
                        dtype=np.float32,
                    ),
                    source="qc6_state_conditioned_exemplar",
                    fallback_reason="",
                )
            token, source, reason = self.prior_token(int(cell_id))
            if token is not None:
                return self._plan(
                    token=token,
                    source=source,
                    fallback_reason="",
                )
            if self.required or not self.allow_live_fallback:
                raise DigDepthProfileTokenPlanningError(
                    "dig_depth_profile.source='prior_profile' requires a matching "
                    f"dig_depth_profile prior for cell {int(cell_id)}; {reason}",
                    token_source="missing_required_prior",
                    fallback_reason=reason,
                )
            return self._plan(
                token=self.live_plan_token(
                    cell_id=cell_id,
                    raw_fields=raw_fields,
                    env_state=env_state,
                ),
                source="fallback_live_plan",
                fallback_reason=reason,
            )
        if self.source != "live_plan":
            raise ValueError(
                "Unsupported dig_depth_profile.source "
                f"{self.source!r}; expected 'live_plan' or 'prior_profile'."
            )
        return self._plan(
            token=self.live_plan_token(
                cell_id=cell_id,
                raw_fields=raw_fields,
                env_state=env_state,
            ),
            source="live_plan",
            fallback_reason="",
        )

    def live_plan_token(
        self,
        *,
        cell_id: int,
        raw_fields: dict[str, float | int],
        env_state: np.ndarray,
    ) -> np.ndarray:
        return build_dig_depth_profile_token_from_plan(
            raw_fields=raw_fields,
            cell_id=int(cell_id),
            env_state=np.asarray(env_state, dtype=np.float32).reshape(-1),
            effective_deposit_delta_kg=float(
                raw_fields.get(
                    "operator_effective_deposit_delta_kg",
                    raw_fields.get("operator_cut_payload_gain_kg", 0.0),
                )
            ),
        )

    def prior_token(self, cell_id: int) -> tuple[np.ndarray | None, str, str]:
        mapping, source, reason = self.prior_mapping(cell_id)
        if mapping is None:
            return None, source, reason
        token = self.token_from_prior_mapping(mapping)
        if token is None:
            return None, source, f"{source} prior has no token_median/token field"
        if source == "cell":
            return token, f"qc6_dig_depth_profile_cell_{int(cell_id)}", ""
        return token, "qc6_dig_depth_profile_global", ""

    def prior_mapping(
        self,
        cell_id: int,
    ) -> tuple[dict[str, object] | None, str, str]:
        if not self.prior:
            return None, "missing_dig_cut_prior", "missing dig_cut_prior"
        cells = self.prior.get("dig_depth_profile_cells", [])
        if isinstance(cells, list):
            for item in cells:
                if not isinstance(item, dict):
                    continue
                cell = dict(item)
                if int(cell.get("cell_id", -999999)) == int(cell_id):
                    return cell, "cell", ""
        if self.allow_global_fallback:
            global_prior = self.prior.get("dig_depth_profile_global")
            if isinstance(global_prior, dict):
                return dict(global_prior), "global", ""
        return (
            None,
            "missing_dig_depth_profile_prior",
            f"missing dig_depth_profile_cells entry for cell {int(cell_id)}",
        )

    @staticmethod
    def token_from_prior_mapping(mapping: dict[str, object]) -> np.ndarray | None:
        for key in ("token_median", "token", "median"):
            if key not in mapping:
                continue
            token = np.asarray(mapping[key], dtype=np.float32).reshape(-1)
            if token.shape[0] != DIG_DEPTH_PROFILE_TOKEN_DIM:
                raise ValueError(
                    "dig_depth_profile prior token must have "
                    f"{DIG_DEPTH_PROFILE_TOKEN_DIM} values, got {token.shape[0]}"
                )
            if not np.all(np.isfinite(token)):
                raise ValueError("dig_depth_profile prior token contains non-finite values")
            return token.copy()
        return None

    @staticmethod
    def _plan(
        *,
        token: np.ndarray,
        source: str,
        fallback_reason: str,
    ) -> DigDepthProfileTokenPlan:
        token_array = np.asarray(token, dtype=np.float32).reshape(-1).copy()
        token_array.setflags(write=False)
        return DigDepthProfileTokenPlan(
            token=token_array,
            source=str(source),
            fallback_reason=str(fallback_reason),
        )


__all__ = [
    "DigDepthProfileTokenPlan",
    "DigDepthProfileTokenPlanner",
    "DigDepthProfileTokenPlanningError",
    "DigCutTokenPlan",
    "DigCutTokenPlanner",
    "GoalTokenProvider",
    "PRIMITIVE_GOAL_SECTOR_IDS",
    "ReturnTargetTokenPlan",
    "ReturnTargetTokenPlanner",
]
