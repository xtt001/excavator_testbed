"""Configuration helpers for primitive planner facades."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from testbed.contracts.primitive_tokens import DIG_CUT_TOKEN_DIM

PRIMITIVE_GOAL_SECTOR_IDS = {"left": 0, "mid": 1, "right": 2}


def normalize_plane_depth_mode(value: object) -> str:
    mode = str(value or "range").strip().lower().replace("-", "_")
    aliases = {
        "legacy": "range",
        "p05_p95": "range",
        "median_floor": "p50_floor",
        "target_floor": "p50_floor",
        "median_band": "target_band",
    }
    mode = aliases.get(mode, mode)
    if mode not in {"range", "p50_floor", "target_band"}:
        raise ValueError(
            "return_to_dig_start_envelope_plane_depth_mode must be one of "
            "'range', 'p50_floor', or 'target_band'"
        )
    return mode


def normalize_failed_dig_replan_skill(value: object) -> str:
    skill = str(value or "dig").strip().lower().replace("-", "_")
    aliases = {
        "fail": "stop",
        "fail_fast": "stop",
        "terminal": "stop",
        "terminal_stop": "stop",
        "same": "dig",
        "same_dig": "dig",
        "new_dig": "dig",
    }
    skill = aliases.get(skill, skill)
    if skill not in {"dig", "stop"}:
        raise ValueError("dig_failed_replan_next_skill must be 'dig' or 'stop'.")
    return skill


def align_vector(
    value: object,
    *,
    default: list[float] | tuple[float, ...],
    action_dim: int,
) -> np.ndarray:
    arr = np.asarray(default if value is None else value, dtype=np.float32)
    return arr.reshape(int(action_dim))


def optional_align_vector(value: object, *, action_dim: int) -> np.ndarray | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"", "none", "null"}:
            return None
        value = [part.strip() for part in text.split(",") if part.strip()]
    return np.asarray(value, dtype=np.float32).reshape(int(action_dim))


def optional_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"", "none", "null"}:
        return None
    return float(value)


def load_dig_cut_prior(path: str) -> dict[str, Any]:
    if not path:
        return {}
    prior_path = Path(path).expanduser()
    if not prior_path.is_absolute():
        prior_path = Path.cwd() / prior_path
    with prior_path.open("r", encoding="utf-8") as handle:
        prior = json.load(handle)
    if int(len(prior.get("token_order", []))) != DIG_CUT_TOKEN_DIM:
        raise ValueError(f"dig cut prior {prior_path} has invalid token_order length.")
    return dict(prior)


def validate_dig_cut_planner_config(
    *,
    dig_cut_planner_enabled: bool,
    dig_cut_planner_mode: str,
    dig_cut_prior_path: str,
    coverage_candidate_layout: str,
    dig_depth_profile_source: str,
    dig_cut_prior: dict[str, Any],
    dig_depth_profile_required: bool,
    dig_depth_profile_allow_live_fallback: bool,
) -> None:
    if not dig_cut_planner_enabled:
        return
    supported_modes = {
        "conservative_pose",
        "operator_prior",
        "operator_prior_coverage",
        "operator_prior_sweep_belief",
    }
    if dig_cut_planner_mode not in supported_modes:
        raise ValueError(
            f"Unsupported dig_cut_planner mode {dig_cut_planner_mode!r}; "
            f"expected one of {sorted(supported_modes)}."
        )
    if (
        dig_cut_planner_mode
        in {"operator_prior", "operator_prior_coverage", "operator_prior_sweep_belief"}
        and not dig_cut_prior_path
    ):
        raise ValueError(f"{dig_cut_planner_mode} dig_cut_planner requires prior_path.")
    supported_layouts = {"percentile_grid", "cell_weighted_3x2"}
    if coverage_candidate_layout not in supported_layouts:
        raise ValueError(
            "Unsupported coverage.candidate_layout "
            f"{coverage_candidate_layout!r}; expected one of "
            f"{sorted(supported_layouts)}."
        )
    supported_profile_sources = {"live_plan", "prior_profile"}
    if dig_depth_profile_source not in supported_profile_sources:
        raise ValueError(
            "Unsupported dig_depth_profile.source "
            f"{dig_depth_profile_source!r}; expected one of "
            f"{sorted(supported_profile_sources)}."
        )
    if dig_depth_profile_source == "prior_profile":
        if not dig_cut_prior_path:
            raise ValueError("dig_depth_profile.source='prior_profile' requires prior_path.")
        if "dig_depth_profile_cells" not in dig_cut_prior:
            raise ValueError(
                "dig_depth_profile.source='prior_profile' requires "
                "dig_depth_profile_cells in the dig cut prior."
            )
        if dig_depth_profile_required and dig_depth_profile_allow_live_fallback:
            raise ValueError(
                "dig_depth_profile.required=true must set "
                "allow_live_fallback=false so missing prior profiles fail fast."
            )


def normalize_goal_sequence(
    goal_sequence: list[object] | tuple[object, ...] | None,
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
