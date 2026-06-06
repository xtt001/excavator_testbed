"""Coverage data models and shared imports for primitive planner."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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


COVERAGE_OBSERVATION_FACT_FIELDS: tuple[tuple[str, str, Any], ...] = (
    ("cycle_index", "_cycle_index", 0),
    ("skill_name", "_skill_name", ""),
    ("dig_best_mass_kg", "_dig_best_mass_kg", 0.0),
)

_QPOS_MISSING = object()


def build_coverage_observation_facts_from_mapping(
    values: Mapping[str, Any],
    *,
    action_dim: int,
    env_state: np.ndarray,
    bucket_tip_dig_area_pose: tuple[float, float, float] | None,
    mass_in_bucket_kg: float,
    deposited_mass_kg: float,
    qpos: object = _QPOS_MISSING,
) -> CoverageObservationFacts:
    if qpos is _QPOS_MISSING:
        qpos = np.zeros(int(action_dim), dtype=np.float32)
    return CoverageObservationFacts(
        env_state=env_state,
        qpos=np.asarray(qpos, dtype=np.float32).reshape(int(action_dim)),
        bucket_tip_dig_area_pose=bucket_tip_dig_area_pose,
        mass_in_bucket_kg=mass_in_bucket_kg,
        deposited_mass_kg=deposited_mass_kg,
        cycle_index=int(values["cycle_index"]),
        skill_name=str(values["skill_name"]),
        dig_best_mass_kg=float(values["dig_best_mass_kg"]),
    )


def build_coverage_context_facts_from_mapping(
    values: Mapping[str, Any],
    *,
    action_dim: int,
) -> CoverageObservationFacts:
    return build_coverage_observation_facts_from_mapping(
        values,
        action_dim=action_dim,
        env_state=np.zeros(0, dtype=np.float32),
        bucket_tip_dig_area_pose=None,
        mass_in_bucket_kg=0.0,
        deposited_mass_kg=0.0,
    )


@dataclass(frozen=True)
class CoverageActionResult:
    """Coverage state update result for planner-shell side effects."""

    terminal_stop_reason: str = ""
    terminal_stop_replace: bool = False


@dataclass(frozen=True)
class CoverageSelectionResult:
    """Selected coverage corridor plus deferred planner-shell side effects."""

    corridor: CoverageCorridorState
    action: CoverageActionResult = field(default_factory=CoverageActionResult)


@dataclass(frozen=True)
class CoverageDebugSnapshot:
    """Coverage state snapshot for debug-state payload assembly."""

    active_corridor_id: int
    last_selected_corridor_id: int
    last_selected_cell_id: int
    last_selected_row_id: int
    active_values: dict[str, float]
    active_cell_id: int
    active_corridor_score: float
    state_exemplar_enabled: bool
    active_state_exemplar_ids: tuple[Any, ...]
    active_state_exemplar_distance: float
    depleted_count: int
    pass_index: int
    multi_pass_enabled: bool
    multi_pass_max_passes: int
    multi_pass_min_remaining_depth_m: float
    last_payload_gain_kg: float
    last_effective_deposit_delta_kg: float
    global_low_productivity_streak: int
    use_env_removed_depth: bool
    candidate_layout: str
    first_dig_strategy: str
    first_dig_preferred_corridor_id: int | None
    first_dig_max_entry_distance_m: float | None
    first_dig_qpos_delta_weight: float
    first_dig_max_qpos_delta: np.ndarray | None
    terminal_stop_requested: bool
    terminal_stop_reason: str
    corridors: tuple[dict[str, float | int | str], ...]
    candidate_scores: tuple[Any, ...]


@dataclass(frozen=True)
class CoverageTraceSnapshot:
    """Coverage state snapshot for primitive planner trace assembly."""

    use_env_removed_depth: bool
    candidate_layout: str
    first_dig_strategy: str
    pass_index: int
    multi_pass_enabled: bool
    multi_pass_max_passes: int
    multi_pass_min_remaining_depth_m: float
    first_dig_preferred_corridor_id: int | None
    corridors: tuple[dict[str, float | int | str], ...]
    decision_trace: tuple[Any, ...]
    terminal_stop_requested: bool
    terminal_stop_reason: str


@dataclass(frozen=True)
class CoverageRolloutSummarySnapshot:
    """Coverage state snapshot for primitive rollout-summary assembly."""

    selected_corridor_id: int
    depleted_count: int
    completed_dump_count: int
    pass_index: int
    multi_pass_enabled: bool
    use_env_removed_depth: bool
    candidate_layout: str
    first_dig_strategy: str
    first_dig_preferred_corridor_id: int | None
    first_dig_max_entry_distance_m: float | None
    first_dig_qpos_delta_weight: float
    terminal_stop_requested: bool
    terminal_stop_reason: str


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


COVERAGE_SERVICE_CONFIG_FIELDS: tuple[tuple[str, str], ...] = (
    ("dig_cut_planner_mode", "dig_cut_planner_mode"),
    ("dig_cut_prior", "dig_cut_prior"),
    ("dig_cut_prior_path", "dig_cut_prior_path"),
    ("action_dim", "action_dim"),
    ("candidate_layout", "coverage_candidate_layout"),
    ("use_env_removed_depth", "coverage_use_env_removed_depth"),
    ("belief_gain_scale", "coverage_belief_gain_scale"),
    ("belief_depleted_score", "coverage_belief_depleted_score"),
    ("low_productivity_payload_kg", "coverage_low_productivity_payload_kg"),
    ("low_productivity_deposit_kg", "coverage_low_productivity_deposit_kg"),
    ("deplete_after_low_streak", "coverage_deplete_after_low_streak"),
    ("min_remaining_depth_m", "coverage_min_remaining_depth_m"),
    ("global_low_productivity_stop", "coverage_global_low_productivity_stop"),
    ("max_attempts_per_corridor", "coverage_max_attempts_per_corridor"),
    ("multi_pass_enabled", "coverage_multi_pass_enabled"),
    ("multi_pass_max_passes", "coverage_multi_pass_max_passes"),
    ("multi_pass_min_remaining_depth_m", "coverage_multi_pass_min_remaining_depth_m"),
    ("unattempted_bonus", "coverage_unattempted_bonus"),
    ("attempt_penalty", "coverage_attempt_penalty"),
    ("recent_selection_penalty", "coverage_recent_selection_penalty"),
    ("recent_row_selection_penalty", "coverage_recent_row_selection_penalty"),
    (
        "rare_cell_source_fraction_threshold",
        "coverage_rare_cell_source_fraction_threshold",
    ),
    ("rare_cell_max_attempts", "coverage_rare_cell_max_attempts"),
    ("cell_confidence_weight", "coverage_cell_confidence_weight"),
    ("state_exemplars_enabled", "coverage_state_exemplars_enabled"),
    ("state_exemplar_path", "coverage_state_exemplar_path"),
    ("state_exemplar_k", "coverage_state_exemplar_k"),
    (
        "state_exemplar_removed_depth_scale_m",
        "coverage_state_exemplar_removed_depth_scale_m",
    ),
    (
        "state_exemplar_target_cell_weight",
        "coverage_state_exemplar_target_cell_weight",
    ),
    ("state_exemplar_score_weight", "coverage_state_exemplar_score_weight"),
    ("state_exemplar_temperature", "coverage_state_exemplar_temperature"),
    ("state_exemplar_skip_rejected", "coverage_state_exemplar_skip_rejected"),
    ("state_exemplars_by_cell", "coverage_state_exemplars_by_cell"),
    ("first_dig_strategy", "coverage_first_dig_strategy"),
    ("first_dig_preferred_corridor_id", "coverage_first_dig_preferred_corridor_id"),
    ("first_dig_preferred_bonus", "coverage_first_dig_preferred_bonus"),
    ("first_dig_proximity_weight", "coverage_first_dig_proximity_weight"),
    ("first_dig_max_entry_distance_m", "coverage_first_dig_max_entry_distance_m"),
    ("first_dig_qpos_delta_weight", "coverage_first_dig_qpos_delta_weight"),
    ("first_dig_max_qpos_delta", "coverage_first_dig_max_qpos_delta"),
    ("first_dig_alignment_enabled", "pre_dig_align_enabled"),
    ("first_dig_controlled_dims", "pre_dig_align_controlled_dims"),
    ("entry_x_percentiles", "coverage_entry_x_percentiles"),
    ("entry_z_percentiles", "coverage_entry_z_percentiles"),
    ("cut_direction_percentile", "coverage_cut_direction_percentile"),
    ("cut_length_percentile", "coverage_cut_length_percentile"),
    ("cut_depth_percentile", "coverage_cut_depth_percentile"),
    ("payload_percentile", "coverage_payload_percentile"),
)


def build_coverage_service_config_from_mapping(
    values: Mapping[str, Any],
) -> CoverageServiceConfig:
    action_dim = int(values["action_dim"])
    first_dig_preferred_corridor_id = values["first_dig_preferred_corridor_id"]
    first_dig_max_entry_distance_m = values["first_dig_max_entry_distance_m"]
    first_dig_max_qpos_delta = values["first_dig_max_qpos_delta"]
    return CoverageServiceConfig(
        dig_cut_planner_mode=str(values["dig_cut_planner_mode"]),
        dig_cut_prior=dict(values["dig_cut_prior"]),
        dig_cut_prior_path=str(values["dig_cut_prior_path"]),
        action_dim=action_dim,
        candidate_layout=str(values["candidate_layout"]),
        use_env_removed_depth=bool(values["use_env_removed_depth"]),
        belief_gain_scale=float(values["belief_gain_scale"]),
        belief_depleted_score=float(values["belief_depleted_score"]),
        low_productivity_payload_kg=float(values["low_productivity_payload_kg"]),
        low_productivity_deposit_kg=float(values["low_productivity_deposit_kg"]),
        deplete_after_low_streak=int(values["deplete_after_low_streak"]),
        min_remaining_depth_m=float(values["min_remaining_depth_m"]),
        global_low_productivity_stop=int(values["global_low_productivity_stop"]),
        max_attempts_per_corridor=int(values["max_attempts_per_corridor"]),
        multi_pass_enabled=bool(values["multi_pass_enabled"]),
        multi_pass_max_passes=int(values["multi_pass_max_passes"]),
        multi_pass_min_remaining_depth_m=float(
            values["multi_pass_min_remaining_depth_m"]
        ),
        unattempted_bonus=float(values["unattempted_bonus"]),
        attempt_penalty=float(values["attempt_penalty"]),
        recent_selection_penalty=float(values["recent_selection_penalty"]),
        recent_row_selection_penalty=float(values["recent_row_selection_penalty"]),
        rare_cell_source_fraction_threshold=float(
            values["rare_cell_source_fraction_threshold"]
        ),
        rare_cell_max_attempts=int(values["rare_cell_max_attempts"]),
        cell_confidence_weight=float(values["cell_confidence_weight"]),
        state_exemplars_enabled=bool(values["state_exemplars_enabled"]),
        state_exemplar_path=str(values["state_exemplar_path"]),
        state_exemplar_k=int(values["state_exemplar_k"]),
        state_exemplar_removed_depth_scale_m=float(
            values["state_exemplar_removed_depth_scale_m"]
        ),
        state_exemplar_target_cell_weight=float(
            values["state_exemplar_target_cell_weight"]
        ),
        state_exemplar_score_weight=float(values["state_exemplar_score_weight"]),
        state_exemplar_temperature=float(values["state_exemplar_temperature"]),
        state_exemplar_skip_rejected=bool(values["state_exemplar_skip_rejected"]),
        state_exemplars_by_cell=dict(values.get("state_exemplars_by_cell", {}) or {}),
        first_dig_strategy=str(values["first_dig_strategy"]),
        first_dig_preferred_corridor_id=(
            None
            if first_dig_preferred_corridor_id is None
            else int(first_dig_preferred_corridor_id)
        ),
        first_dig_preferred_bonus=float(values["first_dig_preferred_bonus"]),
        first_dig_proximity_weight=float(values["first_dig_proximity_weight"]),
        first_dig_max_entry_distance_m=(
            None
            if first_dig_max_entry_distance_m is None
            else float(first_dig_max_entry_distance_m)
        ),
        first_dig_qpos_delta_weight=float(values["first_dig_qpos_delta_weight"]),
        first_dig_max_qpos_delta=(
            None
            if first_dig_max_qpos_delta is None
            else np.asarray(first_dig_max_qpos_delta, dtype=np.float32).reshape(
                action_dim
            )
        ),
        first_dig_alignment_enabled=bool(values["first_dig_alignment_enabled"]),
        first_dig_controlled_dims=np.asarray(
            values["first_dig_controlled_dims"],
            dtype=bool,
        ).reshape(action_dim),
        entry_x_percentiles=tuple(values["entry_x_percentiles"]),
        entry_z_percentiles=tuple(values["entry_z_percentiles"]),
        cut_direction_percentile=str(values["cut_direction_percentile"]),
        cut_length_percentile=str(values["cut_length_percentile"]),
        cut_depth_percentile=str(values["cut_depth_percentile"]),
        payload_percentile=str(values["payload_percentile"]),
    )


@dataclass(frozen=True)
class CoverageActiveStateExemplarState:
    """Clear-state projection for state-conditioned coverage exemplars."""

    ids: tuple[str, ...]
    distance: float
    profile_token: np.ndarray | None


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
