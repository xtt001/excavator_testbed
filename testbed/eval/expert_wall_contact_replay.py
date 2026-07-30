"""Exactly-once diagnostic wall-contact replay and evidence reduction.

Runs ``tb-replay`` without realignment/HDF5 output and reduces its JSONL into
split-authorized windows. Contact is classified without shortening the audit.
"""

from __future__ import annotations

import json
import math
import subprocess
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from testbed.eval import wall_contact_artifact_io as _artifact_io
from testbed.eval.wall_contact_evidence_contracts import (
    ContactEvidenceContractError,
    parse_worktool_wall_contact_detail,
    summarize_contact_details,
    validate_expert_window_fairness,
)

_load_json = _artifact_io.load_json
_required_file = _artifact_io.required_file
_sha256 = _artifact_io.sha256_file
_write_json_x = _artifact_io.write_json_x

SCHEDULE_SCHEMA = "expert_recorded_action_contact_replay_schedule_v1"
MEASUREMENT_SCHEMA = "expert_recorded_action_contact_replay_measurement_v1"
WARNING_SCHEMA = "worktool_wall_contact_detail_v1"
RUNNER_CONTRACT = "guarded_recorded_action_replay_v1"
TRAIN_SOURCE_EPISODE_IDS = (
    3, 6, 7, 8, 9, 13, 16, 19,
    23, 24, 25, 27, 28, 29, 30, 32,
)
HOLDOUT_SOURCE_EPISODE_IDS = (33, 34)
RECORDING_PRE_FIX_SOURCE_EPISODE_IDS = frozenset(
    {3, 6, 7, 8, 9, 13, 16, 19})
PRE_FIX_PROFILE = "recording_pre_fix_v1"
PRODUCTION_PROFILE = "production"
CALIBRATED_SELECTION_PROFILE = "calibrated_mixed_current_equivalent"
POST_FIX_SELECTION_PROFILE = "post_fix_raw"
SOURCE_ENV_DIM = 89
SOURCE_REMOVED_DEPTH_SLICE = slice(39, 45)
SOURCE_BUCKET_TIP_SLICE = slice(28, 31)
SOURCE_CELL_AREA_INDEX = 75

_LIVE_BUCKET_TIP_KEYS = (
    "bucket_tip_dig_area_x_m",
    "bucket_tip_dig_area_y_m",
    "bucket_tip_dig_area_z_m",
)
_LIVE_REMOVED_DEPTH_KEY = "removed_depth_m_grid_3x2"
_LIVE_BULK_DENSITY_KEY = "dig_area_source_bulk_density_kg_m3"
_LIVE_CURRENT_REMAINING_MASS_KEY = "dig_area_current_remaining_mass_kg"
_LIVE_INITIAL_REMAINING_MASS_KEY = "dig_area_initial_remaining_mass_kg"
_LIVE_REMAINING_MASS_VALID_KEY = "dig_area_remaining_mass_valid_mask"
_LIVE_WALL_MASK_KEY = "excavator_wall_contact_typed_mask"
_LIVE_WALL_FORCE_KEY = "excavator_wall_contact_step_max_force_n"
_LIVE_WALL_SESSION_KEY = "excavator_wall_contact_session_count"
_WARNING_PREFIX = f"{WARNING_SCHEMA}:"
_HIGH_FORCE_N = 100_000.0

CommandRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


class ExpertWallContactReplayError(RuntimeError):
    """Raised when the exactly-once replay evidence contract is violated."""


def validate_expert_replay_schedule(
    schedule: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Validate and normalize the frozen 18-source exactly-once schedule."""
    if not isinstance(schedule, Mapping) or schedule.get("schema") != (
        SCHEDULE_SCHEMA
    ):
        raise ExpertWallContactReplayError(
            "expert_replay_schedule_schema_invalid"
        )
    raw_attempts = schedule.get("attempts")
    if not _is_sequence(raw_attempts):
        raise ExpertWallContactReplayError(
            "expert_replay_attempt_inventory_invalid"
        )
    attempts = [
        _validate_attempt(item, index=index)
        for index, item in enumerate(raw_attempts)
    ]
    expected_ids = (
        *TRAIN_SOURCE_EPISODE_IDS,
        *HOLDOUT_SOURCE_EPISODE_IDS,
    )
    actual_ids = tuple(
        int(item["source_episode_id"])
        for item in sorted(
            attempts,
            key=lambda value: int(value["sequence_index"]),
        )
    )
    if actual_ids != expected_ids:
        raise ExpertWallContactReplayError(
            "expert_replay_source_inventory_invalid"
        )
    if len({str(item["attempt_id"]) for item in attempts}) != len(attempts):
        raise ExpertWallContactReplayError(
            "expert_replay_attempt_id_ambiguous"
        )
    if sorted(int(item["sequence_index"]) for item in attempts) != list(
        range(1, len(attempts) + 1)
    ):
        raise ExpertWallContactReplayError(
            "expert_replay_sequence_invalid"
        )
    return sorted(attempts, key=lambda item: int(item["sequence_index"]))


def build_tb_replay_command(
    *,
    attempt: Mapping[str, Any],
    diagnostic_path: str | Path,
    executable: str = "tb-replay",
    config_path: str | Path | None = None,
) -> list[str]:
    """Build the no-record, no-realign command for one complete source."""
    normalized = _validate_attempt(attempt, index=0)
    profile = str(normalized["control_compatibility_profile"])
    selection_profile = (
        CALIBRATED_SELECTION_PROFILE
        if profile == PRE_FIX_PROFILE
        else POST_FIX_SELECTION_PROFILE
    )
    command = [
        str(executable),
        "--episode",
        str(Path(normalized["source_hdf5_path"]).resolve()),
        "--selection-profile",
        selection_profile,
        "--replay-evidence-profile",
        "strict_replay_v1",
        "--control-compatibility-profile",
        profile,
        "--diagnostic-log",
        str(Path(diagnostic_path).expanduser().resolve()),
        "--diagnostic-every",
        "1",
    ]
    if config_path is not None:
        command.extend(
            [
                "--config",
                str(Path(config_path).expanduser().resolve()),
            ]
        )
    return command


def run_expert_wall_contact_replay(
    *,
    schedule_path: str | Path,
    measurement_path: str | Path,
    attempt_root: str | Path,
    config_path: str | Path | None = None,
    tb_replay_executable: str = "tb-replay",
    command_runner: CommandRunner | None = None,
) -> dict[str, Any]:
    """Execute all sources once and create one no-overwrite measurement."""
    schedule_source = _required_file(schedule_path, "schedule")
    attempts = validate_expert_replay_schedule(_load_json(schedule_source))
    destination = Path(measurement_path).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite {destination}")
    run_root = Path(attempt_root).expanduser().resolve()
    configured_outputs = [
        Path(str(item["output_path"])).expanduser().resolve()
        for item in attempts
    ]
    if len(set(configured_outputs)) != len(configured_outputs):
        raise ExpertWallContactReplayError("expert_replay_output_path_ambiguous")
    for configured_output in configured_outputs:
        if configured_output.exists():
            raise FileExistsError(f"refusing to overwrite {configured_output}")
    run_root.mkdir(parents=True, exist_ok=False)
    runner = command_runner or _run_command
    sources: list[dict[str, Any]] = []
    for attempt in attempts:
        attempt_dir = run_root / str(attempt["attempt_id"])
        attempt_dir.mkdir()
        diagnostic_path = attempt_dir / "diagnostics.jsonl"
        command = build_tb_replay_command(
            attempt=attempt,
            diagnostic_path=diagnostic_path,
            executable=tb_replay_executable,
            config_path=config_path,
        )
        _write_json_x(
            attempt_dir / "attempt_started.json",
            {
                "schema": "expert_wall_contact_replay_attempt_started_v1",
                "attempt_id": attempt["attempt_id"],
                "attempt_index": 1,
                "retry_allowed": False,
                "command": command,
                "source_hdf5_path": attempt["source_hdf5_path"],
                "source_hdf5_sha256": attempt["source_hdf5_sha256"],
            },
        )
        try:
            completed = runner(command)
        except Exception as exc:  # pragma: no cover - subprocess guard
            completed = subprocess.CompletedProcess(
                args=command, returncode=255, stdout="",
                stderr=f"{type(exc).__name__}:{exc}",
            )
        _write_text_x(attempt_dir / "stdout.txt", completed.stdout or "")
        _write_text_x(attempt_dir / "stderr.txt", completed.stderr or "")
        if completed.returncode == 0:
            try:
                source_result = postprocess_expert_replay_attempt(
                    attempt=attempt,
                    diagnostic_log_path=diagnostic_path,
                )
            except (
                ContactEvidenceContractError, ExpertWallContactReplayError,
                OSError, ValueError,
            ) as exc:
                source_result = _blocked_source_result(
                    attempt, blocker=f"expert_replay_postprocess_failed:{exc}",
                )
        else:
            source_result = _blocked_source_result(
                attempt, blocker=(
                    f"expert_replay_process_failed:{completed.returncode}"
                ),
            )
        source_result["process_returncode"] = int(completed.returncode)
        source_result["diagnostic_log_path"] = str(diagnostic_path)
        _write_json_x(attempt_dir / "attempt_result.json", source_result)
        configured_output = Path(str(attempt["output_path"])).resolve()
        if configured_output != attempt_dir / "attempt_result.json":
            configured_output.parent.mkdir(parents=True, exist_ok=True)
            _write_json_x(configured_output, source_result)
        sources.append(source_result)
    blockers = sorted({
        str(blocker)
        for source in sources
        for blocker in source.get("blockers", [])
    })
    measurement = {
        "schema": MEASUREMENT_SCHEMA,
        "status": "passed" if not blockers else "blocked",
        "blockers": blockers,
        "diagnostic_only": True,
        "non_promotable": True,
        "writes_training_hdf5": False,
        "retry_allowed": False,
        "source_count": len(sources),
        "sources": sources,
        "source_lock": {"schedule_path": str(schedule_source),
                        "schedule_sha256": _sha256(schedule_source)},
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    _write_json_x(destination, measurement)
    return measurement


def postprocess_expert_replay_attempt(
    *,
    attempt: Mapping[str, Any],
    diagnostic_log_path: str | Path,
) -> dict[str, Any]:
    """Reduce one complete ``tb-replay`` diagnostic into dig-window evidence."""
    normalized = _validate_attempt(attempt, index=0)
    source = _required_file(normalized["source_hdf5_path"], "source_hdf5")
    if _sha256(source) != normalized["source_hdf5_sha256"]:
        raise ExpertWallContactReplayError("source_artifact_drift")
    diagnostic_source = _required_file(diagnostic_log_path, "diagnostic_log")
    rows = _load_jsonl(diagnostic_source)
    start_rows = [row for row in rows if row.get("event") == "episode_start"]
    end_rows = [row for row in rows if row.get("event") == "episode_end"]
    step_rows = [row for row in rows if row.get("event") == "step"]
    if len(start_rows) != 1 or len(end_rows) != 1:
        raise ExpertWallContactReplayError("complete_replay_markers_missing")
    start = start_rows[0]
    if int(start.get("diagnostic_every", -1)) != 1:
        raise ExpertWallContactReplayError("diagnostic_every_contract_invalid")
    realign = start.get("realign_config")
    if not isinstance(realign, Mapping) or bool(realign.get("enabled", True)):
        raise ExpertWallContactReplayError("pose_realign_forbidden")
    if str(start.get("replay_control_compatibility_profile", "")) != (
        normalized["control_compatibility_profile"]
    ):
        raise ExpertWallContactReplayError("control_compatibility_profile_drift")
    with h5py.File(source, "r") as handle:
        qpos = np.asarray(handle["observations/qpos"], dtype=np.float64)
        qvel = np.asarray(handle["observations/qvel"], dtype=np.float64)
        env_state = np.asarray(handle["observations/env_state"], dtype=np.float64)
        actions = np.asarray(handle["action"])
        metadata = dict(handle["metadata"].attrs)
    if (
        qpos.ndim != 2
        or qpos.shape[1] != 4
        or qvel.shape != qpos.shape
        or env_state.ndim != 2
        or env_state.shape[0] != qpos.shape[0]
        or env_state.shape[1] != SOURCE_ENV_DIM
        or actions.shape[0] != qpos.shape[0]
    ):
        raise ExpertWallContactReplayError("source_hdf5_contract_invalid")
    expected_steps = int(actions.shape[0])
    if int(end_rows[0].get("steps", -1)) != expected_steps:
        raise ExpertWallContactReplayError(
            "complete_recorded_action_replay_missing")
    by_step: dict[int, Mapping[str, Any]] = {}
    for raw in step_rows:
        step_index = _integer(
            raw.get("record_step_index"), "record_step_index", minimum=0)
        if step_index in by_step:
            raise ExpertWallContactReplayError("diagnostic_step_ambiguous")
        by_step[step_index] = raw
    if set(by_step) != set(range(expected_steps)):
        raise ExpertWallContactReplayError("diagnostic_step_inventory_incomplete")
    expected_profile = str(normalized["control_compatibility_profile"])
    metadata_profile = _text(metadata.get(
        "replay_control_compatibility_profile", ""))
    if metadata_profile != expected_profile:
        raise ExpertWallContactReplayError("source_control_profile_drift")

    windows: list[dict[str, Any]] = []
    source_blockers: list[str] = []
    valid_train_details: list[Mapping[str, Any]] = []
    all_authorized_details: list[Mapping[str, Any]] = []
    for window in normalized["authorized_windows"]:
        reduced = _reduce_window(
            window=window,
            split=str(normalized["split"]),
            by_step=by_step,
            source_qpos=qpos,
            source_qvel=qvel,
            source_env_state=env_state,
        )
        windows.append(reduced)
        source_blockers.extend(str(x) for x in reduced.get("blockers", []))
        all_authorized_details.extend(reduced.pop("_parsed_contact_details"))
        if bool(reduced["production_inference_eligible"]):
            valid_train_details.extend(reduced.pop(
                "_production_contact_details"))
        else:
            reduced.pop("_production_contact_details")
    source_status = "blocked" if source_blockers else "passed"
    return {
        "schema": "expert_recorded_action_contact_replay_source_v1",
        "attempt_id": normalized["attempt_id"],
        "sequence_index": normalized["sequence_index"],
        "source_episode_id": normalized["source_episode_id"],
        "split": normalized["split"],
        "source_hdf5_path": normalized["source_hdf5_path"],
        "source_hdf5_sha256": normalized["source_hdf5_sha256"],
        "control_compatibility_profile": normalized[
            "control_compatibility_profile"],
        "attempt_index": 1,
        "retry_count": 0,
        "retry_allowed": False,
        "status": source_status,
        "blockers": sorted(set(source_blockers)),
        "complete_recorded_action_replay": True,
        "recorded_action_step_count": expected_steps,
        "authorized_window_count": len(windows),
        "window_status_counts": dict(sorted(
            Counter(str(item["status"]) for item in windows).items())),
        "dig_windows": windows,
        "all_authorized_window_contact_summary":
            _summarize_contact_details_detailed(all_authorized_details),
        "production_inference_contact_summary":
            _summarize_contact_details_detailed(valid_train_details),
        "holdout_used_for_region_or_budget_selection": False,
        "source_contact_semantics": {
            "recorded_env_state_dim": SOURCE_ENV_DIM,
            "generic_collision_zero_interpretation":
                "field_insufficient_not_proof_of_no_wall_contact",
            "typed_contact_source": WARNING_SCHEMA,
        },
        "diagnostic_only": True,
        "non_promotable": True,
        "writes_training_hdf5": False,
    }


def _reduce_window(
    *,
    window: Mapping[str, Any],
    split: str,
    by_step: Mapping[int, Mapping[str, Any]],
    source_qpos: np.ndarray,
    source_qvel: np.ndarray,
    source_env_state: np.ndarray,
) -> dict[str, Any]:
    start = int(window["start_step"])
    end = int(window["end_step_exclusive"])
    qpos_max = 0.0
    qvel_max = 0.0
    bucket_tip_max = 0.0
    terrain_max = 0.0
    remaining_mass_max = 0.0
    worst_mass_lineage: dict[str, Any] | None = None
    blockers: list[str] = []
    warnings_by_step: list[dict[str, Any]] = []
    parsed_details: list[Mapping[str, Any]] = []
    wall_contact_observed = False
    prior_session_count: int | None = None
    prior_contact_positive: bool | None = None
    source_initial_depth = source_env_state[0, SOURCE_REMOVED_DEPTH_SLICE]
    for step_index in range(start, end):
        row = by_step[step_index]
        try:
            replay_qpos = _vector(
                row.get("replay_qpos_before"),
                width=4,
                label="replay_qpos_before",
            )
            replay_qvel = _vector(
                row.get("replay_qvel_before"),
                width=4,
                label="replay_qvel_before",
            )
            env_before = _mapping(
                row.get("env_state_before"),
                "env_state_before",
            )
            env_after = _mapping(
                row.get("env_state_after"),
                "env_state_after",
            )
            qpos_max = max(
                qpos_max,
                _max_abs_difference(
                    replay_qpos,
                    source_qpos[step_index],
                ),
            )
            qvel_max = max(
                qvel_max,
                _max_abs_difference(
                    replay_qvel,
                    source_qvel[step_index],
                ),
            )
            live_tip = np.asarray(
                [
                    _finite(env_before.get(key), key)
                    for key in _LIVE_BUCKET_TIP_KEYS
                ],
                dtype=np.float64,
            )
            source_tip = source_env_state[
                step_index,
                SOURCE_BUCKET_TIP_SLICE,
            ]
            bucket_tip_max = max(
                bucket_tip_max,
                float(np.linalg.norm(live_tip - source_tip)),
            )
            live_depth = np.asarray(
                _vector(
                    env_before.get(_LIVE_REMOVED_DEPTH_KEY),
                    width=6,
                    label=_LIVE_REMOVED_DEPTH_KEY,
                ),
                dtype=np.float64,
            )
            source_depth = source_env_state[
                step_index,
                SOURCE_REMOVED_DEPTH_SLICE,
            ]
            terrain_max = max(
                terrain_max,
                _max_abs_difference(live_depth, source_depth),
            )
            initial_mass = _finite(
                env_before.get(_LIVE_INITIAL_REMAINING_MASS_KEY),
                _LIVE_INITIAL_REMAINING_MASS_KEY,
            )
            density = _finite(
                env_before.get(_LIVE_BULK_DENSITY_KEY),
                _LIVE_BULK_DENSITY_KEY,
            )
            observed_mass = _finite(
                env_before.get(_LIVE_CURRENT_REMAINING_MASS_KEY),
                _LIVE_CURRENT_REMAINING_MASS_KEY,
            )
            valid_mask = _finite(
                env_before.get(_LIVE_REMAINING_MASS_VALID_KEY),
                _LIVE_REMAINING_MASS_VALID_KEY,
            )
            if valid_mask < 0.5:
                raise ExpertWallContactReplayError(
                    "remaining_mass_lineage_invalid"
                )
            source_depth_delta = source_depth - source_initial_depth
            if np.any(source_depth_delta < -1.0e-6):
                raise ExpertWallContactReplayError(
                    "source_removed_depth_regressed"
                )
            source_depth_delta = np.maximum(source_depth_delta, 0.0)
            cell_area = _finite(
                source_env_state[step_index, SOURCE_CELL_AREA_INDEX],
                "source_cell_area_m2",
            )
            expected_mass = max(
                0.0,
                initial_mass
                - float(np.sum(source_depth_delta) * cell_area * density),
            )
            mass_difference = abs(observed_mass - expected_mass)
            if (
                worst_mass_lineage is None
                or mass_difference >= remaining_mass_max
            ):
                remaining_mass_max = mass_difference
                worst_mass_lineage = {
                    "live_reset_initial_remaining_mass_kg": initial_mass,
                    "source_removed_depth_grid_m": source_depth_delta.tolist(),
                    "source_cell_area_m2": cell_area,
                    "live_bulk_density_kg_m3": density,
                    "observed_remaining_mass_kg": observed_mass,
                }
            typed_mask = _finite(
                env_after.get(_LIVE_WALL_MASK_KEY), _LIVE_WALL_MASK_KEY)
            typed_force = _finite(
                env_after.get(_LIVE_WALL_FORCE_KEY), _LIVE_WALL_FORCE_KEY)
            typed_sessions = _finite(
                env_after.get(_LIVE_WALL_SESSION_KEY), _LIVE_WALL_SESSION_KEY)
            session_count = int(round(typed_sessions))
            contact_positive = typed_mask > 0.5
            invalid_scalar = (
                min(abs(typed_mask), abs(typed_mask - 1.0)) > 1.0e-6
                or typed_force < 0.0
                or session_count < 0
                or abs(typed_sessions - session_count) > 1.0e-6
            )
            invalid_transition = prior_session_count is not None and (
                session_count < prior_session_count
                or session_count > prior_session_count + 1
                or (
                    not contact_positive
                    and session_count != prior_session_count
                )
                or (
                    prior_contact_positive is True
                    and contact_positive
                    and session_count != prior_session_count
                )
            )
            if invalid_scalar or invalid_transition:
                raise ExpertWallContactReplayError(
                    "typed_contact_session_lineage_drift")
            prior_session_count = session_count
            prior_contact_positive = contact_positive
            warnings = _warning_sequence(row.get("warnings_after"))
            sidecars = [item for item in warnings if isinstance(item, str)
                        and item.startswith(_WARNING_PREFIX)]
            if contact_positive:
                wall_contact_observed = True
                warnings_by_step.append(
                    {
                        "step_id": _integer(
                            row.get("step_id_after"), "step_id_after", minimum=0,
                        ),
                        "warnings": list(warnings),
                    }
                )
                if len(sidecars) != 1:
                    raise ExpertWallContactReplayError(
                        "contact_detail_missing"
                        if not sidecars
                        else "contact_detail_ambiguous"
                    )
                detail = parse_worktool_wall_contact_detail(warnings)
                if int(detail["step_id"]) != int(row["step_id_after"]):
                    raise ExpertWallContactReplayError(
                        "contact_detail_step_lineage_drift"
                    )
                if int(detail["session_count"]) != session_count:
                    raise ExpertWallContactReplayError(
                        "contact_detail_session_lineage_drift"
                    )
                detail_force = max(
                    float(pair["max_normal_force_n"])
                    for pair in detail["pairs"]
                )
                if not math.isclose(
                    detail_force,
                    typed_force,
                    rel_tol=1.0e-5,
                    abs_tol=1.0e-3,
                ):
                    raise ExpertWallContactReplayError(
                        "contact_detail_force_lineage_drift"
                    )
                parsed_details.append(detail)
            elif sidecars:
                raise ExpertWallContactReplayError(
                    "contact_detail_without_wall_positive"
                )
            elif abs(typed_force) > 1.0e-6:
                raise ExpertWallContactReplayError(
                    "typed_contact_aggregate_ambiguous"
                )
        except (
            ContactEvidenceContractError,
            ExpertWallContactReplayError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            blockers.append(str(exc))
    metrics = {
        "qpos_max_abs_difference": qpos_max,
        "qvel_max_abs_difference": qvel_max,
        "bucket_tip_displacement_m": bucket_tip_max,
        "terrain_depth_max_abs_difference_m": terrain_max,
        "remaining_mass_abs_difference_kg": remaining_mass_max,
    }
    fairness = validate_expert_window_fairness(metrics)
    status = (
        "blocked"
        if blockers
        else ("passed" if fairness["valid"] else "invalid")
    )
    production_eligible = status == "passed" and split == "train"
    all_summary = _summarize_contact_details_detailed(parsed_details)
    production_details = parsed_details if production_eligible else []
    production_summary = _summarize_contact_details_detailed(
        production_details
    )
    return {
        "window_id": window["window_id"],
        "source_cycle_id": window["source_cycle_id"],
        "start_step": start,
        "end_step_exclusive": end,
        "status": status,
        "blockers": sorted(set(blockers)),
        "wall_contact_observed": wall_contact_observed,
        "replay_fairness": metrics,
        "replay_fairness_checks": fairness["checks"],
        "mass_lineage": worst_mass_lineage or {},
        "warnings_by_step": warnings_by_step,
        "all_diagnostic_contact_summary": all_summary,
        "production_inference_eligible": production_eligible,
        "production_inference_contact_summary": production_summary,
        "holdout_used_for_region_or_budget_selection": False,
        "_parsed_contact_details": parsed_details,
        "_production_contact_details": production_details,
    }


def _summarize_contact_details_detailed(
    details: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    summary = summarize_contact_details(details)
    accumulators: dict[tuple[str, str], dict[str, Any]] = {}
    for detail in details:
        session_id = int(detail["session_id"])
        delta_time_s = float(detail["delta_time_s"])
        for pair in detail["pairs"]:
            key = (str(pair["component"]), str(pair["wall_name"]))
            accumulator = accumulators.setdefault(
                key,
                {
                    "normal": [], "tangential": [], "total": [],
                    "normal_impulse_n_s": 0.0,
                    "sessions": set(),
                    "contact_duration_s": 0.0,
                    "maximum_session_duration_s": 0.0,
                    "maximum_tangential_displacement_m": 0.0,
                    "callback_count": 0, "contact_point_count": 0,
                    "bucket_local_contact_region_samples": [],
                },
            )
            normal = float(pair["max_normal_force_n"])
            tangential = float(pair["max_tangential_force_n"])
            total = float(pair["max_total_force_n"])
            accumulator["normal"].append(normal)
            accumulator["tangential"].append(tangential)
            accumulator["total"].append(total)
            accumulator["normal_impulse_n_s"] += normal * delta_time_s
            accumulator["sessions"].add(session_id)
            accumulator["contact_duration_s"] += delta_time_s
            accumulator["maximum_session_duration_s"] = max(
                accumulator["maximum_session_duration_s"],
                float(detail["session_duration_s"]))
            accumulator["maximum_tangential_displacement_m"] = max(
                accumulator["maximum_tangential_displacement_m"],
                float(pair["tangential_displacement_m"]))
            accumulator["callback_count"] += int(pair["callback_count"])
            accumulator["contact_point_count"] += int(pair[
                "contact_point_count"])
            local = pair["representative_contact_point_component_local_m"]
            if str(pair["component"]) == "bucket" and local:
                accumulator["bucket_local_contact_region_samples"].append(
                    list(local))
    pair_summaries: list[dict[str, Any]] = []
    for (component, wall), accumulator in sorted(accumulators.items()):
        pair_summaries.append(
            {
                "component": component,
                "wall_name": wall,
                "peak_normal_force_n": max(accumulator["normal"]),
                "rms_normal_force_n": _rms(accumulator["normal"]),
                "peak_tangential_force_n": max(accumulator["tangential"]),
                "rms_tangential_force_n": _rms(accumulator["tangential"]),
                "peak_total_force_n": max(accumulator["total"]),
                "rms_total_force_n": _rms(accumulator["total"]),
                "normal_impulse_n_s": accumulator["normal_impulse_n_s"],
                "session_count": len(accumulator["sessions"]),
                "contact_duration_s": accumulator["contact_duration_s"],
                "maximum_session_duration_s":
                    accumulator["maximum_session_duration_s"],
                "maximum_tangential_displacement_m":
                    accumulator["maximum_tangential_displacement_m"],
                "callback_count": accumulator["callback_count"],
                "contact_point_count": accumulator["contact_point_count"],
                "bucket_local_contact_region_samples":
                    accumulator["bucket_local_contact_region_samples"],
            }
        )
    summary["component_wall_summaries"] = pair_summaries
    return summary


def _validate_attempt(
    value: Any,
    *,
    index: int,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ExpertWallContactReplayError(
            f"expert_replay_attempt_invalid:{index}")
    source_id = _integer(
        value.get("source_episode_id"), "source_episode_id", minimum=0,
    )
    expected_split = (
        "train"
        if source_id in set(TRAIN_SOURCE_EPISODE_IDS)
        else (
            "validation"
            if source_id in set(HOLDOUT_SOURCE_EPISODE_IDS)
            else ""
        )
    )
    if not expected_split or str(value.get("split", "")) != expected_split:
        raise ExpertWallContactReplayError("expert_replay_split_invalid")
    expected_profile = (
        PRE_FIX_PROFILE
        if source_id in RECORDING_PRE_FIX_SOURCE_EPISODE_IDS
        else PRODUCTION_PROFILE
    )
    if str(value.get("control_compatibility_profile", "")) != expected_profile:
        raise ExpertWallContactReplayError(
            "expert_replay_control_profile_invalid")
    if (
        _integer(value.get("attempt_index"), "attempt_index", minimum=1) != 1
        or _integer(value.get("max_attempts"), "max_attempts", minimum=1)
        != 1
        or bool(value.get("retry_allowed", True))
    ):
        raise ExpertWallContactReplayError("expert_replay_retry_forbidden")
    if value.get("replay_scope") != "complete_recorded_action_source":
        raise ExpertWallContactReplayError("expert_replay_scope_invalid")
    if value.get("warning_schema") != WARNING_SCHEMA:
        raise ExpertWallContactReplayError(
            "expert_replay_warning_schema_invalid")
    source = _required_file(value.get("source_hdf5_path"), "source_hdf5")
    expected_sha = str(value.get("source_hdf5_sha256", "")).lower()
    if len(expected_sha) != 64 or _sha256(source) != expected_sha:
        raise ExpertWallContactReplayError("source_artifact_drift")
    with h5py.File(source, "r") as handle:
        step_count = int(handle["action"].shape[0])
    raw_windows = value.get("authorized_windows")
    if not _is_sequence(raw_windows) or not raw_windows:
        raise ExpertWallContactReplayError(
            "authorized_window_inventory_invalid")
    windows: list[dict[str, Any]] = []
    prior_end = -1
    for window_index, raw in enumerate(raw_windows):
        if not isinstance(raw, Mapping):
            raise ExpertWallContactReplayError("authorized_window_invalid")
        start = _integer(
            raw.get("start_step"), "start_step", minimum=0,
        )
        end = _integer(
            raw.get("end_step_exclusive"), "end_step_exclusive", minimum=1,
        )
        if start >= end or end > step_count or start < prior_end:
            raise ExpertWallContactReplayError(
                "authorized_window_bounds_invalid")
        prior_end = end
        window_id = str(raw.get("window_id", "")).strip()
        if not window_id:
            raise ExpertWallContactReplayError("authorized_window_id_invalid")
        windows.append(
            {
                "window_id": window_id,
                "source_cycle_id": _integer(
                    raw.get("source_cycle_id"), "source_cycle_id", minimum=0,
                ),
                "start_step": start,
                "end_step_exclusive": end,
                "sequence_index": window_index,
            }
        )
    if len({item["window_id"] for item in windows}) != len(windows):
        raise ExpertWallContactReplayError("authorized_window_id_ambiguous")
    attempt_id = str(value.get("attempt_id", "")).strip()
    output_path = str(value.get("output_path", "")).strip()
    if not attempt_id or not output_path:
        raise ExpertWallContactReplayError(
            "expert_replay_attempt_path_invalid")
    return {
        "attempt_id": attempt_id,
        "sequence_index": _integer(
            value.get("sequence_index"), "sequence_index", minimum=0,
        ),
        "source_episode_id": source_id,
        "split": expected_split,
        "source_hdf5_path": str(source),
        "source_hdf5_sha256": expected_sha,
        "attempt_index": 1,
        "max_attempts": 1,
        "retry_allowed": False,
        "replay_scope": "complete_recorded_action_source",
        "control_compatibility_profile": expected_profile,
        "authorized_windows": windows,
        "warning_schema": WARNING_SCHEMA,
        "output_path": output_path,
        "runner_contract": str(value.get("runner_contract", RUNNER_CONTRACT)),
    }


def _blocked_source_result(
    attempt: Mapping[str, Any],
    *,
    blocker: str,
) -> dict[str, Any]:
    return {
        "schema": "expert_recorded_action_contact_replay_source_v1",
        "attempt_id": attempt["attempt_id"],
        "sequence_index": attempt["sequence_index"],
        "source_episode_id": attempt["source_episode_id"],
        "split": attempt["split"],
        "source_hdf5_sha256": attempt["source_hdf5_sha256"],
        "control_compatibility_profile": attempt[
            "control_compatibility_profile"
        ],
        "attempt_index": 1,
        "retry_count": 0,
        "retry_allowed": False,
        "status": "blocked",
        "blockers": [blocker],
        "complete_recorded_action_replay": False,
        "dig_windows": [
            {
                "window_id": window["window_id"],
                "status": "blocked",
                "wall_contact_observed": False,
                "replay_fairness": {},
                "mass_lineage": {},
                "warnings_by_step": [],
            }
            for window in attempt["authorized_windows"]
        ],
        "diagnostic_only": True,
        "non_promotable": True,
        "writes_training_hdf5": False,
    }


def _run_command(
    command: Sequence[str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        check=False,
        capture_output=True,
        text=True,
    )


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ExpertWallContactReplayError(
                f"diagnostic_row_invalid:{line_number}"
            )
        rows.append(payload)
    return rows


def _write_text_x(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


def _integer(value: Any, label: str, *, minimum: int) -> int:
    if isinstance(value, bool):
        raise ExpertWallContactReplayError(f"{label}_invalid")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ExpertWallContactReplayError(f"{label}_invalid") from exc
    if result != value or result < minimum:
        raise ExpertWallContactReplayError(f"{label}_invalid")
    return result


def _finite(value: Any, label: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ExpertWallContactReplayError(f"{label}_invalid") from exc
    if not math.isfinite(result):
        raise ExpertWallContactReplayError(f"{label}_invalid")
    return result


def _vector(value: Any, *, width: int, label: str) -> np.ndarray:
    if not _is_sequence(value) or len(value) != width:
        raise ExpertWallContactReplayError(f"{label}_invalid")
    return np.asarray([_finite(item, label) for item in value])


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ExpertWallContactReplayError(f"{label}_invalid")
    return value


def _warning_sequence(value: Any) -> Sequence[Any]:
    if not _is_sequence(value):
        raise ExpertWallContactReplayError("warnings_after_invalid")
    return value


def _max_abs_difference(left: Any, right: Any) -> float:
    left_array = np.asarray(left, dtype=np.float64).reshape(-1)
    right_array = np.asarray(right, dtype=np.float64).reshape(-1)
    if left_array.shape != right_array.shape or left_array.size == 0:
        raise ExpertWallContactReplayError(
            "state_vector_shape_invalid"
        )
    difference = np.abs(left_array - right_array)
    if not np.all(np.isfinite(difference)):
        raise ExpertWallContactReplayError(
            "state_vector_non_finite"
        )
    return float(np.max(difference))


def _rms(values: Sequence[float]) -> float:
    return math.sqrt(
        sum(float(value) ** 2 for value in values) / len(values)
    )


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return str(value)


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    )


__all__ = [
    "ExpertWallContactReplayError",
    "MEASUREMENT_SCHEMA",
    "SCHEDULE_SCHEMA",
    "build_tb_replay_command",
    "postprocess_expert_replay_attempt",
    "run_expert_wall_contact_replay",
    "validate_expert_replay_schedule",
]
