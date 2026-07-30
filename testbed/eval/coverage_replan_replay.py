"""Offline replay of production coverage selection after a safety event."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import yaml

from testbed.planner.box_emptying.contact_ownership import (
    CONTACT_KIND_HARD_BOTTOM,
)
from testbed.planner.box_emptying.safety_effects import (
    SafetyDecisionCoverageEffectService,
)
from testbed.planner.box_emptying.safety_interlock import SafetyActionDecision
from testbed.planner.primitive.config.adapter import (
    PrimitivePlannerAdapterConfigInputs,
    PrimitivePlannerAdapterConfigNormalizer,
)
from testbed.planner.primitive.coverage.config import PrimitiveCoverageStaticConfig
from testbed.planner.primitive.coverage.selection_runtime import (
    PrimitiveCoverageSelectionRuntime,
    PrimitiveCoverageSelectionRuntimePorts,
)
from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.facts.capabilities import PrimitiveObservationFacts
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy

COVERAGE_REPLAN_REPLAY_SCHEMA = "coverage_replan_replay_v1"
OUTPUT_FILENAME = f"{COVERAGE_REPLAN_REPLAY_SCHEMA}.json"
COVERAGE_EXECUTION_PREFLIGHT_SCHEMA = (
    "coverage_execution_candidate_preflight_v1"
)
COVERAGE_EXECUTION_PREFLIGHT_FILENAME = (
    f"{COVERAGE_EXECUTION_PREFLIGHT_SCHEMA}.json"
)


def build_coverage_execution_preflight(
    *,
    rollout_hdf5_path: str | Path,
    rollout_jsonl_path: str | Path,
    resolved_config_path: str | Path,
    output_dir: str | Path,
    initial_dig_step_id: int,
    pre_contact_step_id: int,
    replan_step_id: int,
    depth_exhausted_physical_cell_id: int,
) -> dict[str, Any]:
    """Replay both the fresh-reset and corrected cycle-six selections."""

    hdf5_path = Path(rollout_hdf5_path).expanduser().resolve(strict=True)
    jsonl_path = Path(rollout_jsonl_path).expanduser().resolve(strict=True)
    config_path = Path(resolved_config_path).expanduser().resolve(strict=True)
    destination = Path(output_dir).expanduser().resolve()
    output_path = destination / COVERAGE_EXECUTION_PREFLIGHT_FILENAME
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite {output_path}")
    resolved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(resolved, dict):
        raise ValueError("resolved config must contain a mapping")
    static_config = _production_static_config(resolved)
    if not static_config.execution_library.enabled:
        raise ValueError(
            "coverage execution preflight requires the exact library"
        )
    initial_observation = _read_hdf5_observation(
        hdf5_path,
        int(initial_dig_step_id),
    )
    initial_row = {
        "primitive_cycle_index": 0,
        "coverage_completed_dump_count": 0,
        "coverage_corridor_id": -1,
        "coverage_candidate_scores": [
            {
                "corridor_id": cell_id,
                "attempts": 0,
                "depleted": 0,
                "belief_coverage": 0.0,
                "low_productivity_streak": 0,
                "remaining_depth_m": 0.08,
                "rejection_reason": "",
            }
            for cell_id in range(6)
        ],
    }
    initial = _run_production_selection(
        static_config=static_config,
        pre_contact_row=initial_row,
        observation=initial_observation,
        depth_exhausted_physical_cell_id=None,
    )
    corrected = _run_production_selection(
        static_config=static_config,
        pre_contact_row=_read_jsonl_step(
            jsonl_path,
            int(pre_contact_step_id),
        ),
        observation=_read_hdf5_observation(
            hdf5_path,
            int(replan_step_id),
        ),
        depth_exhausted_physical_cell_id=int(
            depth_exhausted_physical_cell_id
        ),
    )
    initial_candidate = dict(
        initial.get("selected_candidate", {}) or {}
    )
    corrected_candidate = dict(
        corrected.get("selected_candidate", {}) or {}
    )
    worktool_sweep_enabled = bool(
        static_config.execution_library.worktool_sweep_3d.enabled
    )
    if worktool_sweep_enabled:
        passed = bool(
            _selected_with_proven_3d_clearance(initial)
            and _selected_with_proven_3d_clearance(corrected)
            and initial_candidate.get("source_exemplar_id")
            != "episode_168"
            and corrected_candidate.get("source_exemplar_id")
            != "episode_168"
        )
        expected_selection_contract = {
            "episode_168_must_not_be_selected": True,
            "initial_pre_state_must_have_legal_candidate": True,
            "step_2987_must_have_legal_candidate": True,
            "selected_effective_clearance_min_m": 0.30,
        }
    else:
        passed = bool(
            initial["status"] == "selected"
            and initial_candidate.get("source_exemplar_id") == "episode_24"
            and int(initial_candidate.get("corridor_id", -1)) == 1_000_024
            and int(
                initial_candidate.get("effect_outcome_cell_id", -1)
            )
            == 3
            and list(
                initial_candidate.get(
                    "live_swept_physical_cell_ids",
                    (),
                )
            )
            == [0, 1, 2, 3]
            and corrected["status"] == "selected"
            and corrected_candidate.get("source_exemplar_id")
            == "episode_168"
            and int(corrected_candidate.get("corridor_id", -1))
            == 1_000_168
            and list(
                corrected_candidate.get(
                    "live_swept_physical_cell_ids",
                    (),
                )
            )
            == [1, 3]
        )
        expected_selection_contract = {
            "legacy_exact_tuple_replay": True,
            "initial_exemplar_id": "episode_24",
            "step_2987_exemplar_id": "episode_168",
        }
    artifact = {
        "schema": COVERAGE_EXECUTION_PREFLIGHT_SCHEMA,
        "status": "passed" if passed else "failed",
        "evidence_kind": "offline_production_service_replay",
        "teacher_forced_recorded_observation": True,
        "source_lock": {
            "rollout_hdf5": _source_record(hdf5_path),
            "rollout_jsonl": _source_record(jsonl_path),
            "resolved_config": _source_record(config_path),
        },
        "initial_dig_step_id": int(initial_dig_step_id),
        "pre_contact_step_id": int(pre_contact_step_id),
        "replan_step_id": int(replan_step_id),
        "depth_exhausted_physical_cell_id": int(
            depth_exhausted_physical_cell_id
        ),
        "worktool_sweep_3d_enabled": worktool_sweep_enabled,
        "expected_selection_contract": expected_selection_contract,
        "initial_selection": initial,
        "corrected_replan": corrected,
        "bounded_live_allowed": bool(passed),
    }
    destination.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as handle:
        json.dump(
            artifact,
            handle,
            indent=2,
            sort_keys=True,
            allow_nan=True,
        )
        handle.write("\n")
    return artifact


def _selected_with_proven_3d_clearance(
    selection: dict[str, Any],
) -> bool:
    candidate = dict(selection.get("selected_candidate", {}) or {})
    return bool(
        selection.get("status") == "selected"
        and float(
            candidate.get(
                "worktool_sweep_3d_effective_clearance_m",
                float("-inf"),
            )
        )
        >= 0.30
    )


def build_coverage_replan_replay(
    *,
    rollout_hdf5_path: str | Path,
    rollout_jsonl_path: str | Path,
    resolved_config_path: str | Path,
    output_dir: str | Path,
    pre_contact_step_id: int,
    replan_step_id: int,
    depth_exhausted_physical_cell_id: int,
) -> dict[str, Any]:
    """Re-run the production coverage builder/selector without Unity."""

    hdf5_path = Path(rollout_hdf5_path).expanduser().resolve()
    jsonl_path = Path(rollout_jsonl_path).expanduser().resolve()
    config_path = Path(resolved_config_path).expanduser().resolve()
    destination = Path(output_dir).expanduser().resolve()
    output_path = destination / OUTPUT_FILENAME
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite {output_path}")
    for path in (hdf5_path, jsonl_path, config_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    pre_contact_row = _read_jsonl_step(
        jsonl_path,
        int(pre_contact_step_id),
    )
    observation = _read_hdf5_observation(
        hdf5_path,
        int(replan_step_id),
    )
    resolved_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(resolved_config, dict):
        raise ValueError("resolved config must contain a mapping")
    static_config = _production_static_config(resolved_config)

    ownership_only = _run_production_selection(
        static_config=static_config,
        pre_contact_row=pre_contact_row,
        observation=observation,
        depth_exhausted_physical_cell_id=None,
    )
    corrected = _run_production_selection(
        static_config=static_config,
        pre_contact_row=pre_contact_row,
        observation=observation,
        depth_exhausted_physical_cell_id=int(
            depth_exhausted_physical_cell_id
        ),
    )
    mismatch = bool(
        ownership_only["status"] == "selected"
        and int(ownership_only["selected_corridor_id"]) == 4
        and corrected["status"] == "no_wall_safe_corridor"
        and any(
            int(item["corridor_id"]) == 4
            and item["rejection_reason"]
            == "swept_footprint_intersects_depth_exhausted_cell"
            for item in corrected["candidate_scores"]
        )
    )
    artifact = {
        "schema": COVERAGE_REPLAN_REPLAY_SCHEMA,
        "evidence_kind": "offline_production_service_replay",
        "teacher_forced_recorded_observation": True,
        "status": str(corrected["status"]),
        "source_lock": {
            "rollout_hdf5": _source_record(hdf5_path),
            "rollout_jsonl": _source_record(jsonl_path),
            "resolved_config": _source_record(config_path),
        },
        "pre_contact_step_id": int(pre_contact_step_id),
        "replan_step_id": int(replan_step_id),
        "selected_candidate": dict(
            corrected.get("selected_candidate", {}) or {}
        ),
        "depth_exhausted_physical_cell_id": int(
            depth_exhausted_physical_cell_id
        ),
        "production_components": [
            "PrimitivePlannerAdapterConfigNormalizer",
            "PrimitivePlannerACTPolicy._primitive_coverage_static_config",
            "CoverageCandidateBuilder",
            "CoveragePlanningFactService",
            "CoverageSelectionService",
        ],
        "contact_ownership_only_counterfactual": ownership_only,
        "corrected_production_replan": corrected,
        "root_cause_flags": {
            "bookkeeping_corridor_4_wall_depletion_removed": bool(
                ownership_only["corridor_4_pre_selection_depleted"] is False
            ),
            "data_scene_cell_semantic_mismatch": mismatch,
        },
        "live_1x10_allowed": False if mismatch else None,
        "live_gate_reason": (
            "data_scene_cell_semantic_mismatch"
            if mismatch
            else "requires_combined_diagnosis_gate"
        ),
    }
    destination.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True, allow_nan=True) + "\n",
        encoding="utf-8",
    )
    return artifact


def _production_static_config(
    resolved_config: dict[str, Any],
) -> PrimitiveCoverageStaticConfig:
    policy_config = resolved_config.get("policy")
    if not isinstance(policy_config, dict):
        raise ValueError("resolved config is missing policy mapping")
    normalized = PrimitivePlannerAdapterConfigNormalizer.normalize(
        PrimitivePlannerAdapterConfigInputs(
            action_dim=4,
            dig_cut_planner=policy_config.get("dig_cut_planner"),
            return_target_planner=policy_config.get("return_target_planner"),
            pre_dig_align=policy_config.get("pre_dig_align"),
        )
    ).as_policy_field_updates()
    shell = object.__new__(PrimitivePlannerACTPolicy)
    shell.__dict__.update(normalized)
    return shell._primitive_coverage_static_config()


def _run_production_selection(
    *,
    static_config: PrimitiveCoverageStaticConfig,
    pre_contact_row: dict[str, Any],
    observation: dict[str, Any],
    depth_exhausted_physical_cell_id: int | None,
) -> dict[str, Any]:
    state = CoverageRuntimeState()
    events: list[dict[str, Any]] = []
    cycle_index = int(pre_contact_row.get("primitive_cycle_index", 5))
    runtime = PrimitiveCoverageSelectionRuntime.from_ports(
        PrimitiveCoverageSelectionRuntimePorts(
            state=state,
            static_config=static_config,
            cycle_index=lambda: cycle_index,
            observation_facts=lambda obs: PrimitiveObservationFacts.from_obs(
                obs,
                action_dim=int(static_config.action_dim),
            ),
            maybe_reopen_pass=lambda _obs, _reason: False,
            request_terminal_stop=lambda reason: state.set_terminal_stop(
                requested=True,
                reason=str(reason),
            ),
            record_decision_event=lambda event, **kwargs: events.append(
                {
                    "event": str(event),
                    "extra": dict(kwargs.get("extra", {}) or {}),
                }
            ),
        )
    )
    runtime.ensure_coverage_corridors()
    _hydrate_pre_contact_state(state, pre_contact_row)
    corridor_4 = state.corridor_by_id(4)
    corridor_4_pre_selection_depleted = (
        None if corridor_4 is None else bool(corridor_4.depleted)
    )

    if depth_exhausted_physical_cell_id is not None:
        SafetyDecisionCoverageEffectService(coverage_state=state).apply(
            SafetyActionDecision(
                action=np.zeros(int(static_config.action_dim), dtype=np.float32),
                reason="hard_bottom_contact_neutral_acknowledged",
                neutral_acknowledged=True,
                contact_kind=CONTACT_KIND_HARD_BOTTOM,
                depth_exhausted_cell_id=int(
                    depth_exhausted_physical_cell_id
                ),
            )
        )
    try:
        if static_config.execution_library.enabled:
            selected, raw_fields = runtime.select_next_coverage_plan(
                observation,
                update_state=True,
            )
        else:
            selected = runtime.select_next_coverage_corridor(observation)
            raw_fields = {}
        status = "selected"
        selected_corridor_id = int(selected.corridor_id)
        selected_cell_id = int(selected.cell_id)
        error = ""
        selected_candidate = (
            {
                "corridor_id": int(
                    state.active_execution_corridor_id()
                ),
                "source_exemplar_id": str(
                    state.coverage_active_execution_exemplar_id
                ),
                "exemplar_id": str(
                    state.coverage_active_execution_exemplar_id
                ),
                "source_primitive_episode_id": int(
                    state.coverage_active_execution_trace.get(
                        "source_primitive_episode_id",
                        -1,
                    )
                ),
                "source_episode_id": int(
                    state.coverage_active_execution_trace.get(
                        "source_episode_id",
                        -1,
                    )
                ),
                "effect_outcome_cell_id": int(
                    state.coverage_active_effect_outcome_cell_id
                ),
                "return_envelope_cell_id": int(
                    state.coverage_active_return_envelope_cell_id
                ),
                "live_centerline_physical_cell_ids": list(
                    state.coverage_active_execution_trace.get(
                        "live_centerline_physical_cell_ids",
                        [],
                    )
                ),
                "live_swept_physical_cell_ids": list(
                    state.coverage_active_execution_trace.get(
                        "live_swept_physical_cell_ids",
                        [],
                    )
                ),
                "wall_minimum_clearance_m": float(
                    state.coverage_active_execution_trace.get(
                        "wall_minimum_clearance_m",
                        float("nan"),
                    )
                ),
                "planned_hard_bottom_clearance_before_tail_m": float(
                    state.coverage_active_execution_trace.get(
                        "planned_hard_bottom_clearance_before_tail_m",
                        float("nan"),
                    )
                ),
                "execution_tail_plane_depth_reserve_m": float(
                    state.coverage_active_execution_trace.get(
                        "execution_tail_plane_depth_reserve_m",
                        float("nan"),
                    )
                ),
                "planned_hard_bottom_budget_after_tail_m": float(
                    state.coverage_active_execution_trace.get(
                        "planned_hard_bottom_budget_after_tail_m",
                        float("nan"),
                    )
                ),
                "worktool_sweep_3d_effective_clearance_m": float(
                    state.coverage_active_execution_trace.get(
                        "worktool_sweep_3d_effective_clearance_m",
                        float("nan"),
                    )
                ),
                "worktool_sweep_3d_sampled_convex_cover_clearance_m": float(
                    state.coverage_active_execution_trace.get(
                        "worktool_sweep_3d_sampled_convex_cover_clearance_m",
                        float("nan"),
                    )
                ),
                "worktool_sweep_3d_live_start_displacement_bound_m": float(
                    state.coverage_active_execution_trace.get(
                        "worktool_sweep_3d_live_start_displacement_bound_m",
                        float("nan"),
                    )
                ),
                "worktool_sweep_3d_closest_link": str(
                    state.coverage_active_execution_trace.get(
                        "worktool_sweep_3d_closest_link",
                        "",
                    )
                ),
                "worktool_sweep_3d_closest_shape": str(
                    state.coverage_active_execution_trace.get(
                        "worktool_sweep_3d_closest_shape",
                        "",
                    )
                ),
                "worktool_sweep_3d_closest_wall": str(
                    state.coverage_active_execution_trace.get(
                        "worktool_sweep_3d_closest_wall",
                        "",
                    )
                ),
                "raw_fields": dict(raw_fields),
                "raw_fields_sha256": str(
                    state.coverage_active_execution_raw_fields_sha256
                ),
            }
            if static_config.execution_library.enabled
            else {}
        )
    except Exception as exc:
        from testbed.planner.primitive.coverage.wall_safety import (
            NoWallSafeCorridorError,
        )

        if not isinstance(exc, NoWallSafeCorridorError):
            raise
        status = "no_wall_safe_corridor"
        selected_corridor_id = -1
        selected_cell_id = -1
        error = str(exc)
        selected_candidate = {}
    full_candidate_scores: list[dict[str, Any]] = []
    for event in reversed(events):
        extra = dict(event.get("extra", {}) or {})
        raw_trace = extra.get(
            "candidate_scores",
            extra.get("coverage_candidate_scores"),
        )
        if isinstance(raw_trace, list):
            full_candidate_scores = [
                dict(item)
                for item in raw_trace
                if isinstance(item, dict)
            ]
            break
    return {
        "status": status,
        "error": error,
        "selected_corridor_id": selected_corridor_id,
        "selected_cell_id": selected_cell_id,
        "selected_candidate": selected_candidate,
        "corridor_4_pre_selection_depleted": corridor_4_pre_selection_depleted,
        "depth_exhausted_physical_cell_ids": sorted(
            state.coverage_depth_exhausted_physical_cell_ids
        ),
        "candidate_scores": list(state.coverage_candidate_scores),
        "full_candidate_scores": full_candidate_scores,
        "decision_events": events,
    }


def _hydrate_pre_contact_state(
    state: CoverageRuntimeState,
    row: dict[str, Any],
) -> None:
    raw_scores = row.get("coverage_candidate_scores")
    if not isinstance(raw_scores, list) or not raw_scores:
        raise ValueError("pre-contact row has no coverage candidate trace")
    by_id = {
        int(item["corridor_id"]): dict(item)
        for item in raw_scores
        if isinstance(item, dict) and "corridor_id" in item
    }
    for corridor in state.coverage_corridors:
        values = by_id.get(int(corridor.corridor_id))
        if values is None:
            raise ValueError(
                f"pre-contact trace missing corridor {corridor.corridor_id}"
            )
        corridor.attempts = int(values.get("attempts", 0))
        corridor.depleted = bool(values.get("depleted", 0))
        corridor.belief_coverage = float(values.get("belief_coverage", 0.0))
        corridor.low_productivity_streak = int(
            values.get("low_productivity_streak", 0)
        )
        corridor.last_effective_deposit_delta_kg = float(
            values.get("last_effective_deposit_delta_kg", 0.0)
        )
        corridor.last_remaining_depth_m = float(
            values.get("remaining_depth_m", float("nan"))
        )
        corridor.last_reason = str(values.get("rejection_reason", ""))
    active = int(row.get("coverage_corridor_id", -1))
    state.set_selected_corridor_ids(
        active_corridor_id=active,
        last_selected_corridor_id=active,
    )
    state.set_completed_dump_count(
        int(row.get("coverage_completed_dump_count", row.get("primitive_cycle_index", 0)))
    )


def _read_hdf5_observation(
    path: Path,
    step_id: int,
) -> dict[str, Any]:
    with h5py.File(path, "r") as handle:
        step_ids = np.asarray(handle["timestamps/step_id"], dtype=np.int64)
        indices = np.flatnonzero(step_ids == int(step_id))
        if indices.size != 1:
            raise ValueError(
                f"expected one HDF5 row for step_id {step_id}; "
                f"found {indices.size}"
            )
        index = int(indices[0])
        return {
            "step_id": int(step_id),
            "qpos": np.asarray(
                handle["observations/qpos"][index],
                dtype=np.float32,
            ),
            "qvel": np.asarray(
                handle["observations/qvel"][index],
                dtype=np.float32,
            ),
            "env_state": np.asarray(
                handle["observations/env_state"][index],
                dtype=np.float32,
            ),
        }


def _read_jsonl_step(path: Path, step_id: int) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if int(row.get("step_id", -1)) == int(step_id):
                matches.append(row)
    if len(matches) != 1:
        raise ValueError(
            f"expected one JSONL row for step_id {step_id}; "
            f"found {len(matches)}"
        )
    return matches[0]


def _source_record(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": str(path),
        "size_bytes": int(path.stat().st_size),
        "sha256": digest.hexdigest(),
    }


__all__ = [
    "COVERAGE_EXECUTION_PREFLIGHT_FILENAME",
    "COVERAGE_EXECUTION_PREFLIGHT_SCHEMA",
    "COVERAGE_REPLAN_REPLAY_SCHEMA",
    "OUTPUT_FILENAME",
    "build_coverage_execution_preflight",
    "build_coverage_replan_replay",
]
