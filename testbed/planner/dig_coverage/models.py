"""Coverage data models and shared imports for primitive planner."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np

from testbed.contracts.primitive_tokens import DIG_DEPTH_PROFILE_TOKEN_DIM
from testbed.data.operator_first_v2_2 import _build_dig_cut_token
from testbed.data.schema import (
    ENV_STATE_BUCKET_DEPTH_BELOW_DIG_AREA_PLANE_IDX,
    ENV_STATE_BUCKET_DEPTH_BELOW_LOCAL_SURFACE_IDX,
    ENV_STATE_BUCKET_DIG_AREA_LONG_NORM_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX,
    ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX,
    ENV_STATE_BUCKET_DIG_AREA_SHORT_NORM_IDX,
    ENV_STATE_DIG_AREA_CELL_VALID_MASK_START_IDX,
    ENV_STATE_DIG_AREA_REMOVED_DEPTH_START_IDX,
    ENV_STATE_DIG_AREA_TARGET_DEPTH_START_IDX,
)


@dataclass
class CoverageCorridorState:
    corridor_id: int
    entry_x_m: float
    entry_z_m: float
    exit_x_m: float
    exit_z_m: float
    cell_id: int = -1
    source_count: int = 0
    source_fraction: float = 0.0
    entry_x_p05_m: float = float("nan")
    entry_x_p50_m: float = float("nan")
    entry_x_p95_m: float = float("nan")
    entry_z_p05_m: float = float("nan")
    entry_z_p50_m: float = float("nan")
    entry_z_p95_m: float = float("nan")
    entry_radial_p75_m: float = float("nan")
    entry_radial_p95_m: float = float("nan")
    exit_x_p05_m: float = float("nan")
    exit_x_p50_m: float = float("nan")
    exit_x_p95_m: float = float("nan")
    exit_z_p05_m: float = float("nan")
    exit_z_p50_m: float = float("nan")
    exit_z_p95_m: float = float("nan")
    exit_radial_p75_m: float = float("nan")
    exit_radial_p95_m: float = float("nan")
    cut_depth_peak_p05_m: float = float("nan")
    cut_depth_peak_p50_m: float = float("nan")
    cut_depth_peak_p95_m: float = float("nan")
    cut_depth_peak_m: float = float("nan")
    payload_gain_kg: float = float("nan")
    effective_deposit_delta_kg: float = float("nan")
    score: float = 0.0
    attempts: int = 0
    low_productivity_streak: int = 0
    depleted: bool = False
    belief_coverage: float = 0.0
    last_payload_gain_kg: float = 0.0
    last_effective_deposit_delta_kg: float = 0.0
    last_remaining_depth_m: float = float("nan")
    last_reason: str = ""
    state_exemplar_id: str = ""
    state_exemplar_distance: float = float("nan")


@dataclass
class CoverageObservationFacts:
    """Observation facts needed by coverage planning without owning a planner."""

    env_state: np.ndarray
    qpos: np.ndarray
    bucket_tip_dig_area_pose: tuple[float, float, float] | None
    mass_in_bucket_kg: float
    deposited_mass_kg: float
    cycle_index: int
    skill_name: str
    dig_best_mass_kg: float = 0.0


@dataclass
class CoverageServiceConfig:
    """Stable configuration for coverage corridor planning."""

    dig_cut_planner_mode: str
    dig_cut_prior: dict[str, Any]
    dig_cut_prior_path: str = ""
    action_dim: int = 4
    candidate_layout: str = "percentile_grid"
    use_env_removed_depth: bool = True
    belief_gain_scale: float = 0.55
    belief_depleted_score: float = 1.0
    low_productivity_payload_kg: float = 15.0
    low_productivity_deposit_kg: float = 15.0
    deplete_after_low_streak: int = 2
    min_remaining_depth_m: float = 0.05
    global_low_productivity_stop: int = 3
    max_attempts_per_corridor: int = 3
    multi_pass_enabled: bool = False
    multi_pass_max_passes: int = 1
    multi_pass_min_remaining_depth_m: float = 0.05
    unattempted_bonus: float = 2.0
    attempt_penalty: float = 0.65
    recent_selection_penalty: float = 1.25
    recent_row_selection_penalty: float = 0.0
    rare_cell_source_fraction_threshold: float = 0.05
    rare_cell_max_attempts: int = 1
    cell_confidence_weight: float = 0.75
    state_exemplars_enabled: bool = False
    state_exemplar_path: str = ""
    state_exemplar_k: int = 5
    state_exemplar_removed_depth_scale_m: float = 0.12
    state_exemplar_target_cell_weight: float = 2.0
    state_exemplar_score_weight: float = 0.75
    state_exemplar_temperature: float = 0.35
    state_exemplar_skip_rejected: bool = True
    state_exemplars_by_cell: dict[int, list[dict[str, Any]]] | None = None
    first_dig_strategy: str = "coverage_score"
    first_dig_preferred_corridor_id: int | None = None
    first_dig_preferred_bonus: float = 10000.0
    first_dig_proximity_weight: float = 0.0
    first_dig_max_entry_distance_m: float | None = None
    first_dig_qpos_delta_weight: float = 0.0
    first_dig_max_qpos_delta: np.ndarray | None = None
    first_dig_alignment_enabled: bool = False
    first_dig_controlled_dims: np.ndarray | None = None
    entry_x_percentiles: tuple[str, ...] = ("p10", "p50", "p90")
    entry_z_percentiles: tuple[str, ...] = ("p10", "p50", "p90")
    cut_direction_percentile: str = "p50"
    cut_length_percentile: str = "p50"
    cut_depth_percentile: str = "p50"
    payload_percentile: str = "p50"


@dataclass
class CoverageServiceState:
    """Mutable state owned by coverage planning."""

    corridors: list[CoverageCorridorState] | None = None
    active_corridor_id: int = -1
    last_selected_corridor_id: int = -1
    current_payload_gain_kg: float = 0.0
    cycle_start_deposit_kg: float = 0.0
    last_payload_gain_kg: float = 0.0
    last_effective_deposit_delta_kg: float = 0.0
    global_low_productivity_streak: int = 0
    completed_dump_count: int = 0
    pass_index: int = 0
    terminal_stop_requested: bool = False
    terminal_stop_reason: str = ""
    candidate_scores: list[dict[str, float | int | str]] | None = None
    decision_trace: list[dict[str, Any]] | None = None
    active_state_exemplar_ids: list[str] | None = None
    rejected_state_exemplar_ids: set[str] | None = None
    active_state_exemplar_distance: float = float("nan")
    active_state_exemplar_profile_token: np.ndarray | None = None

    def __post_init__(self) -> None:
        self.corridors = list(self.corridors or [])
        self.candidate_scores = list(self.candidate_scores or [])
        self.decision_trace = list(self.decision_trace or [])
        self.active_state_exemplar_ids = list(self.active_state_exemplar_ids or [])
        self.rejected_state_exemplar_ids = set(self.rejected_state_exemplar_ids or set())


FirstDigAlignmentTargetFn = Callable[
    [np.ndarray, CoverageObservationFacts],
    np.ndarray,
]


def load_coverage_state_exemplars(
    *,
    enabled: bool,
    raw_path: str,
    prior_path: str,
) -> dict[int, list[dict[str, Any]]]:
    """Load state-conditioned coverage exemplars without planner ownership."""

    if not enabled:
        return {}
    raw_path = str(raw_path).strip()
    if not raw_path:
        raise ValueError(
            "coverage.state_conditioned_exemplars.enabled=true requires a path."
        )
    path = Path(raw_path).expanduser()
    if not path.is_absolute() and not path.exists():
        prior_path_obj = Path(prior_path).expanduser()
        if not prior_path_obj.is_absolute():
            prior_path_obj = Path.cwd() / prior_path_obj
        path = prior_path_obj.parent / path
    if not path.is_absolute():
        path = Path.cwd() / path
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    raw_exemplars = payload.get("exemplars", [])
    if not isinstance(raw_exemplars, list):
        raise ValueError(
            f"coverage state exemplar file {path} must contain an exemplars list."
        )
    exemplars_by_cell: dict[int, list[dict[str, Any]]] = {
        cell_id: [] for cell_id in range(6)
    }
    for item in raw_exemplars:
        if not isinstance(item, dict):
            continue
        try:
            cell_id = int(item.get("cell_id", -1))
        except (TypeError, ValueError):
            continue
        if cell_id < 0 or cell_id > 5:
            continue
        raw_fields = item.get("raw_fields", {})
        if not isinstance(raw_fields, dict):
            continue
        exemplar = dict(item)
        exemplar["raw_fields"] = dict(raw_fields)
        exemplar["exemplar_id"] = str(
            exemplar.get(
                "exemplar_id",
                f"cell_{cell_id}_{len(exemplars_by_cell[cell_id])}",
            )
        )
        exemplars_by_cell[cell_id].append(exemplar)
    if not any(exemplars_by_cell.values()):
        raise ValueError(f"coverage state exemplar file {path} has no usable rows.")
    return exemplars_by_cell
