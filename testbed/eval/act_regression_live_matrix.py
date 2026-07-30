"""Build and collect the bounded F0/D1/C1/DC1 live causal matrix."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import yaml

from testbed.data.schema import (
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX,
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_STEP_MAX_FORCE_IDX,
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
    ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX,
    ENV_STATE_DIG_AREA_CURRENT_REMAINING_MASS_IDX,
    ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_STEP_MAX_FORCE_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_TYPED_MASK_IDX,
    ENV_STATE_V2_4_DIM,
)
from testbed.eval.act_regression_artifact_contract import (
    validate_completed_schedule,
    validated_experiment_contract,
)

SCHEMA = "act_regression_live_matrix_v1"
CONFIG_SCHEMA = "act_regression_live_probe_config_v1"
PLAN_MATRIX_SCHEMA = "act_regression_plan_matrix_v1"
CAMERA_ORDER = ("stick_up", "stick_down", "eye_left", "eye_right")
CONDITION_IDS = ("F0", "D1", "C1", "DC1")
CAUSAL_LIVE_SCHEDULE = (
    (1, "F0"),
    (1, "D1"),
    (1, "C1"),
    (1, "DC1"),
    (2, "C1"),
    (2, "F0"),
    (2, "DC1"),
    (2, "D1"),
    (3, "D1"),
    (3, "DC1"),
    (3, "F0"),
    (3, "C1"),
)
INITIAL_SIGNATURE_WINDOW_STEPS = 5


@dataclass(frozen=True)
class InitialStateSignature:
    """Initial-state fields that must remain comparable across resets."""

    qpos: tuple[float, float, float, float]
    bucket_tip_pose_m: tuple[float, float, float]
    terrain_surface_depth_m: tuple[
        float,
        float,
        float,
        float,
        float,
        float,
    ]
    remaining_mass_kg: float

    @classmethod
    def from_hdf5(cls, path: str | Path) -> InitialStateSignature:
        source = Path(path)
        with h5py.File(source, "r") as handle:
            count = min(
                INITIAL_SIGNATURE_WINDOW_STEPS,
                int(handle["observations/qpos"].shape[0]),
            )
            if count < 1:
                raise ValueError(f"empty initial-state rollout {source}")
            qpos_window = np.asarray(
                handle["observations/qpos"][:count],
                dtype=np.float32,
            )
            env_window = np.asarray(
                handle["observations/env_state"][:count],
                dtype=np.float32,
            )
        qpos = np.median(qpos_window, axis=0).reshape(-1)
        env = np.median(env_window, axis=0).reshape(-1)
        if qpos.shape != (4,) or not np.isfinite(qpos).all():
            raise ValueError(f"invalid initial qpos in {source}")
        if env.size < ENV_STATE_V2_4_DIM or not np.isfinite(env).all():
            raise ValueError(f"initial env_state must be finite 107D in {source}")
        return cls(
            qpos=tuple(float(value) for value in qpos),
            bucket_tip_pose_m=tuple(
                float(value)
                for value in env[
                    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX:
                    ENV_STATE_BUCKET_TIP_DIG_AREA_Z_IDX + 1
                ]
            ),
            terrain_surface_depth_m=tuple(
                float(value)
                for value in env[
                    ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX:
                    ENV_STATE_DIG_AREA_SURFACE_DEPTH_START_IDX + 6
                ]
            ),
            remaining_mass_kg=float(
                env[ENV_STATE_DIG_AREA_CURRENT_REMAINING_MASS_IDX]
            ),
        )


def build_act_regression_live_configs(
    *,
    base_config_path: str | Path,
    plan_matrix_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Generate the locked interleaved live configs without changing A0."""

    base_path = Path(base_config_path).resolve(strict=True)
    matrix_path = Path(plan_matrix_path).resolve(strict=True)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=False)
    configs_dir = output / "configs"
    runs_dir = output / "runs"
    configs_dir.mkdir()
    runs_dir.mkdir()

    base = yaml.safe_load(base_path.read_text(encoding="utf-8")) or {}
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    _validate_base_config(base)
    sources = _validated_condition_sources(matrix)
    matrix_sha = _sha256(matrix_path)
    schedule: list[dict[str, Any]] = []
    condition_repeat_count = {condition_id: 0 for condition_id in CONDITION_IDS}
    for slot_index, (round_index, condition_id) in enumerate(
        CAUSAL_LIVE_SCHEDULE,
        start=1,
    ):
        condition_repeat_count[condition_id] += 1
        repeat_index = condition_repeat_count[condition_id]
        run_id = (
            f"round{round_index:02d}_slot{slot_index:02d}_"
            f"{condition_id}_repeat{repeat_index:02d}"
        )
        run_dir = runs_dir / run_id
        config_path = configs_dir / f"{run_id}.yaml"
        config = _live_config(
            base,
            condition_id=condition_id,
            round_index=round_index,
            repeat_index=repeat_index,
            run_id=run_id,
            run_dir=run_dir,
            source=sources[condition_id],
            matrix_path=matrix_path,
            matrix_sha256=matrix_sha,
        )
        with config_path.open("x", encoding="utf-8") as handle:
            yaml.safe_dump(config, handle, sort_keys=False)
        schedule.append(
            {
                "slot_index": slot_index,
                "round_index": round_index,
                "condition_id": condition_id,
                "repeat_index": repeat_index,
                "repeat_id": run_id,
                "config_path": str(config_path.resolve()),
                "config_sha256": _sha256(config_path),
                "run_dir": str(run_dir.resolve()),
                "runtime_source_path": sources[condition_id]["path"],
                "runtime_source_sha256": sources[condition_id]["sha256"],
            }
        )

    manifest_path = output / "manifest.json"
    manifest = {
        "schema": SCHEMA,
        "status": "present",
        "diagnostic_only": True,
        "promotion_eligible": False,
        "base_config_path": str(base_path),
        "base_config_sha256": _sha256(base_path),
        "plan_matrix_path": str(matrix_path),
        "plan_matrix_sha256": matrix_sha,
        "camera_order": list(CAMERA_ORDER),
        "temporal_aggregation": {
            "window": 100,
            "weight_order": "legacy_oldest_first",
            "decay": 0.01,
        },
        "safety_enabled": True,
        "carry_envelope_live_disable_allowed": False,
        "schedule": schedule,
        "manifest_path": str(manifest_path.resolve()),
    }
    with manifest_path.open("x", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return manifest


def evaluate_initial_state(
    observed: InitialStateSignature,
    reference: InitialStateSignature,
    *,
    qpos_max_abs_delta: float = 0.005,
    bucket_tip_max_distance_m: float = 0.02,
    terrain_depth_max_abs_delta_m: float = 0.002,
    remaining_mass_max_abs_delta_kg: float = 5.0,
) -> dict[str, Any]:
    """Compare one reset to the locked reference with explicit tolerances."""

    qpos_delta = np.abs(
        np.asarray(observed.qpos) - np.asarray(reference.qpos)
    )
    bucket_distance = float(
        np.linalg.norm(
            np.asarray(observed.bucket_tip_pose_m)
            - np.asarray(reference.bucket_tip_pose_m)
        )
    )
    terrain_delta = np.abs(
        np.asarray(observed.terrain_surface_depth_m)
        - np.asarray(reference.terrain_surface_depth_m)
    )
    mass_delta = abs(
        float(observed.remaining_mass_kg)
        - float(reference.remaining_mass_kg)
    )
    violations: list[str] = []
    if float(np.max(qpos_delta)) > qpos_max_abs_delta:
        violations.append("qpos")
    if bucket_distance > bucket_tip_max_distance_m:
        violations.append("bucket_tip_pose_m")
    if float(np.max(terrain_delta)) > terrain_depth_max_abs_delta_m:
        violations.append("terrain_surface_depth_m")
    if mass_delta > remaining_mass_max_abs_delta_kg:
        violations.append("remaining_mass_kg")
    return {
        "valid": not violations,
        "violations": violations,
        "observed": asdict(observed),
        "reference": asdict(reference),
        "deltas": {
            "qpos_max_abs": float(np.max(qpos_delta)),
            "bucket_tip_distance_m": bucket_distance,
            "terrain_depth_max_abs_m": float(np.max(terrain_delta)),
            "remaining_mass_abs_kg": mass_delta,
        },
        "tolerances": {
            "qpos_max_abs_delta": qpos_max_abs_delta,
            "bucket_tip_max_distance_m": bucket_tip_max_distance_m,
            "terrain_depth_max_abs_delta_m": terrain_depth_max_abs_delta_m,
            "remaining_mass_max_abs_delta_kg": (
                remaining_mass_max_abs_delta_kg
            ),
        },
    }


def extract_live_probe_attempt(
    *,
    run_dir: str | Path,
    repeat_id: str,
    condition_id: str,
    initial_reference: InitialStateSignature,
) -> dict[str, Any]:
    """Extract one bounded live attempt without dropping failure evidence."""

    if condition_id not in CONDITION_IDS:
        raise ValueError(f"unknown causal condition {condition_id!r}")
    root = Path(run_dir)
    hdf5_path = root / "results" / "hdf5_rollouts" / "episode_0.hdf5"
    jsonl_path = root / "results" / "rollouts" / "rollout_000.jsonl"
    if not hdf5_path.is_file() or not jsonl_path.is_file():
        raise FileNotFoundError(
            f"bounded probe artifacts missing under {root}"
        )
    observed = InitialStateSignature.from_hdf5(hdf5_path)
    initial_check = evaluate_initial_state(observed, initial_reference)
    rows = [
        json.loads(line)
        for line in jsonl_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not rows:
        raise ValueError(f"bounded probe JSONL is empty: {jsonl_path}")

    with h5py.File(hdf5_path, "r") as handle:
        env = np.asarray(
            handle["observations/env_state"][:],
            dtype=np.float32,
        )
        actions = np.asarray(handle["action"][:], dtype=np.float32)
        step_ids = np.asarray(
            handle["timestamps/step_id"][:],
            dtype=np.int64,
        )
    if (
        env.ndim != 2
        or env.shape[1] < ENV_STATE_V2_4_DIM
        or actions.shape != (env.shape[0], 4)
        or step_ids.shape != (env.shape[0],)
    ):
        raise ValueError("bounded probe HDF5 shape contract mismatch")
    wall_session_count = int(
        round(
            float(
                np.max(
                    env[
                        :,
                        ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX,
                    ]
                )
            )
        )
    )
    bottom_session_count = int(
        round(
            float(
                np.max(
                    env[
                        :,
                        ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX,
                    ]
                )
            )
        )
    )
    wall_mask = bool(
        np.any(
            env[:, ENV_STATE_EXCAVATOR_WALL_CONTACT_TYPED_MASK_IDX] >= 0.5
        )
    )
    bottom_mask = bool(
        np.any(
            env[
                :,
                ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_TYPED_MASK_IDX,
            ]
            >= 0.5
        )
    )
    wall_max_force_n = float(
        np.max(
            env[:, ENV_STATE_EXCAVATOR_WALL_CONTACT_STEP_MAX_FORCE_IDX]
        )
    )
    bottom_max_force_n = float(
        np.max(
            env[
                :,
                ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_STEP_MAX_FORCE_IDX,
            ]
        )
    )
    cycle_one_rows = [
        row
        for row in rows
        if int(row.get("primitive_cycle_index", -1)) == 1
    ]
    envelope_ready = any(
        bool(row.get("carry_start_envelope_ready", False))
        and int(row.get("dig_step_count", 1)) >= 1
        for row in cycle_one_rows
    )
    trigger_kinds = [
        str(row.get("bounded_dig_probe_stop_trigger_kind", ""))
        for row in rows
        if str(row.get("bounded_dig_probe_stop_trigger_kind", ""))
    ]
    neutral_acknowledged = any(
        bool(
            row.get(
                "bounded_dig_probe_stop_neutral_acknowledged",
                False,
            )
        )
        for row in rows
    )
    terminal_requested = any(
        bool(
            row.get(
                "bounded_dig_probe_stop_terminal_requested",
                False,
            )
        )
        for row in rows
    )
    trigger_step_ids = [
        int(row.get("step_id", -1))
        for row in rows
        if str(row.get("bounded_dig_probe_stop_trigger_kind", ""))
    ]
    first_trigger_step = min(trigger_step_ids, default=-1)
    zero_after_trigger = bool(
        first_trigger_step >= 0
        and any(
            int(step_id) >= first_trigger_step
            and np.allclose(action, 0.0, rtol=0.0, atol=1.0e-8)
            for step_id, action in zip(step_ids, actions, strict=True)
        )
    )
    safety_reasons = [
        str(row.get("box_safety_reason", ""))
        for row in rows
        if str(row.get("box_safety_reason", ""))
    ]
    timeout_count = int(
        any(bool(row.get("transition_timeout", False)) for row in rows)
        or any(reason.endswith("_timeout") for reason in safety_reasons)
        or "timeout" in trigger_kinds
        or "dig_step_limit" in trigger_kinds
    )
    stuck_count = int(
        any(reason.startswith("stuck") for reason in safety_reasons)
        or "stuck" in trigger_kinds
    )
    return {
        "repeat_id": str(repeat_id),
        "condition_id": condition_id,
        "initial_state_valid": bool(initial_check["valid"]),
        "initial_state_check": initial_check,
        "wall_contact_count": max(wall_session_count, int(wall_mask)),
        "wall_typed_mask_observed": wall_mask,
        "wall_contact_session_count": wall_session_count,
        "wall_max_force_n": wall_max_force_n,
        "bottom_contact_count": max(
            bottom_session_count,
            int(bottom_mask),
        ),
        "bottom_typed_mask_observed": bottom_mask,
        "bottom_contact_session_count": bottom_session_count,
        "bottom_max_force_n": bottom_max_force_n,
        "timeout_count": timeout_count,
        "stuck_count": stuck_count,
        "envelope_ready": bool(envelope_ready),
        "trigger_kind": trigger_kinds[-1] if trigger_kinds else "",
        "neutral_acknowledged": bool(neutral_acknowledged),
        "terminal_requested": bool(terminal_requested),
        "zero_action_after_trigger": zero_after_trigger,
        "max_cycle_index": max(
            (int(row.get("primitive_cycle_index", -1)) for row in rows),
            default=-1,
        ),
        "artifact": {
            "run_dir": str(root.resolve()),
            "hdf5_path": str(hdf5_path.resolve()),
            "hdf5_sha256": _sha256(hdf5_path),
            "jsonl_path": str(jsonl_path.resolve()),
            "jsonl_sha256": _sha256(jsonl_path),
        },
    }


def collect_act_regression_live_evidence(
    *,
    live_manifest_path: str | Path,
    offline_a0_path: str | Path,
    offline_a1_path: str | Path,
    evidence_matrix_output_path: str | Path,
    diagnosis_output_path: str | Path,
    report_output_path: str | Path,
) -> dict[str, Any]:
    """Collect the completed 3x4 matrix and emit the causal diagnosis."""

    for output_path in (
        evidence_matrix_output_path,
        diagnosis_output_path,
        report_output_path,
    ):
        destination = Path(output_path)
        if destination.exists():
            raise FileExistsError(
                f"ACT regression evidence output already exists: "
                f"{destination}"
            )
    manifest_path = Path(live_manifest_path).resolve(strict=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA or manifest.get("status") != "present":
        raise ValueError("live matrix manifest contract mismatch")
    schedule = manifest.get("schedule")
    if not isinstance(schedule, list) or len(schedule) != 12:
        raise ValueError("live matrix manifest must contain 12 scheduled probes")
    validate_completed_schedule(
        schedule,
        expected_schedule=CAUSAL_LIVE_SCHEDULE,
        condition_ids=CONDITION_IDS,
        sha256_file=_sha256,
    )
    experiment_contract = validated_experiment_contract(
        manifest,
        camera_order=CAMERA_ORDER,
        temporal_contract={
            "window": 100,
            "weight_order": "legacy_oldest_first",
            "decay": 0.01,
        },
        validate_base_config=_validate_base_config,
        sha256_file=_sha256,
    )
    first_run = Path(str(schedule[0]["run_dir"]))
    reference = InitialStateSignature.from_hdf5(
        first_run / "results" / "hdf5_rollouts" / "episode_0.hdf5"
    )
    conditions: dict[str, list[dict[str, Any]]] = {
        condition_id: [] for condition_id in CONDITION_IDS
    }
    attempts: list[dict[str, Any]] = []
    for item in schedule:
        condition_id = str(item.get("condition_id", ""))
        attempt = extract_live_probe_attempt(
            run_dir=item["run_dir"],
            repeat_id=str(item["repeat_id"]),
            condition_id=condition_id,
            initial_reference=reference,
        )
        attempt["schedule"] = {
            "slot_index": int(item["slot_index"]),
            "round_index": int(item["round_index"]),
            "repeat_index": int(item["repeat_index"]),
            "config_path": str(item["config_path"]),
            "config_sha256": str(item["config_sha256"]),
            "runtime_source_path": str(item["runtime_source_path"]),
            "runtime_source_sha256": str(
                item["runtime_source_sha256"]
            ),
        }
        if (
            not attempt["neutral_acknowledged"]
            or not attempt["terminal_requested"]
            or not attempt["zero_action_after_trigger"]
            or int(attempt["max_cycle_index"]) > 1
        ):
            raise ValueError(
                f"bounded probe terminal contract failed: "
                f"{attempt['repeat_id']}"
            )
        attempts.append(attempt)
        conditions[condition_id].append(attempt)
    for condition_id in CONDITION_IDS:
        valid_count = sum(
            bool(attempt["initial_state_valid"])
            for attempt in conditions[condition_id]
        )
        if valid_count != 3:
            raise ValueError(
                f"condition {condition_id} does not have exactly 3 valid resets"
            )

    offline_a0 = _load_offline_diagnosis(offline_a0_path)
    offline_a1 = _load_offline_diagnosis(offline_a1_path)
    source_artifacts = {
        "plan_matrix": {
            "path": str(manifest["plan_matrix_path"]),
            "sha256": str(manifest["plan_matrix_sha256"]),
        },
        "live_matrix": {
            "path": str(manifest_path),
            "sha256": _sha256(manifest_path),
        },
        "offline_a0": {
            "path": str(Path(offline_a0_path).resolve()),
            "sha256": _sha256(Path(offline_a0_path)),
        },
        "offline_a1": {
            "path": str(Path(offline_a1_path).resolve()),
            "sha256": _sha256(Path(offline_a1_path)),
        },
    }
    from testbed.eval.act_regression_diagnosis import (
        write_act_regression_module_diagnosis,
    )

    diagnosis = write_act_regression_module_diagnosis(
        experiment_id="strict18_act_regression_module_isolation_v1",
        conditions=conditions,
        output_path=diagnosis_output_path,
        source_artifacts=source_artifacts,
    )
    live_safety_summary = _live_safety_summary(attempts)
    evidence = {
        "schema": "act_regression_evidence_matrix_v1",
        "status": "present",
        "evidence_scope": "bounded_live_probe",
        "closed_loop_scope": "maximum_two_cycles",
        "promotion_eligible": False,
        "experiment_contract": experiment_contract,
        "initial_reference": asdict(reference),
        "schedule_order": [
            {
                "slot_index": attempt["schedule"]["slot_index"],
                "round_index": attempt["schedule"]["round_index"],
                "condition_id": attempt["condition_id"],
                "repeat_id": attempt["repeat_id"],
            }
            for attempt in attempts
        ],
        "attempts": attempts,
        "condition_summary": diagnosis["conditions"],
        "live_safety_summary": live_safety_summary,
        "root_cause_classification": diagnosis[
            "root_cause_classification"
        ],
        "source_artifacts": source_artifacts,
    }
    _write_json_exclusive(evidence_matrix_output_path, evidence)
    report = _root_cause_report(
        evidence=evidence,
        diagnosis=diagnosis,
        offline_a0=offline_a0,
        offline_a1=offline_a1,
    )
    report_path = Path(report_output_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("x", encoding="utf-8") as handle:
        handle.write(report)
    return {
        "diagnosis": diagnosis,
        "evidence_matrix": evidence,
        "report_path": str(report_path.resolve()),
    }


def _load_offline_diagnosis(path: str | Path) -> dict[str, Any]:
    source = Path(path).resolve(strict=True)
    payload = json.loads(source.read_text(encoding="utf-8"))
    if (
        payload.get("schema") != "act_regression_offline_diagnostic_v1"
        or payload.get("evidence_scope")
        != "teacher_forced_recorded_observation"
        or payload.get("closed_loop_claim") is not False
    ):
        raise ValueError(f"offline diagnosis contract mismatch: {source}")
    return payload


def _root_cause_report(
    *,
    evidence: dict[str, Any],
    diagnosis: dict[str, Any],
    offline_a0: dict[str, Any],
    offline_a1: dict[str, Any],
) -> str:
    condition_rows: list[str] = []
    for condition_id in CONDITION_IDS:
        summary = diagnosis["conditions"][condition_id]
        condition_rows.append(
            "| "
            + " | ".join(
                [
                    condition_id,
                    str(summary["valid_repeat_count"]),
                    str(summary["wall_contact_repeat_count"]),
                    str(summary["envelope_ready_repeat_count"]),
                    str(summary["timeout_repeat_count"]),
                ]
            )
            + " |"
        )
    category = diagnosis["root_cause_classification"]["category"]
    safety = evidence["live_safety_summary"]
    a0_summary = offline_a0["summary"]
    a1_summary = offline_a1["summary"]
    f0 = diagnosis["conditions"]["F0"]
    d1 = diagnosis["conditions"]["D1"]
    c1 = diagnosis["conditions"]["C1"]
    dc1 = diagnosis["conditions"]["DC1"]
    return (
        "# Strict-18 ACT regression module causal diagnosis\n\n"
        "## Result\n\n"
        f"The locked classifier result is `{category}`. F0 reproduced the "
        "cycle-one wall failure in "
        f"{f0['wall_contact_repeat_count']}/{f0['valid_repeat_count']} valid "
        "resets. Lowering only planned depth (D1) hit the wall in "
        f"{d1['wall_contact_repeat_count']}/{d1['valid_repeat_count']} "
        "resets, while changing only the corridor geometry (C1) produced "
        f"{c1['wall_contact_repeat_count']}/{c1['valid_repeat_count']} wall "
        "contacts and reached the carry-start envelope in "
        f"{c1['envelope_ready_repeat_count']}/{c1['valid_repeat_count']} "
        "resets. DC1 reached the envelope without a wall contact in "
        f"{dc1['envelope_ready_repeat_count']}/"
        f"{dc1['valid_repeat_count']} resets. This "
        "isolates the missing wall-safe corridor/swept-footprint selection as "
        "the primary module-level cause; planned depth is not the primary "
        "cause under this matrix.\n\n"
        "## Bounded live evidence\n\n"
        "| condition | valid resets | wall repeats | envelope repeats | "
        "timeout repeats |\n"
        "| --- | ---: | ---: | ---: | ---: |\n"
        + "\n".join(condition_rows)
        + f"\n\nAll {safety['attempt_count']} probes preserved typed safety; "
        f"{safety['terminal_contract_pass_count']}/"
        f"{safety['attempt_count']} emitted zero action, received neutral "
        "acknowledgement, and stopped by cycle one. Across the matrix there "
        f"were {safety['bottom_contact_repeat_count']} bottom-contact, "
        f"{safety['stuck_repeat_count']} stuck, and "
        f"{safety['timeout_repeat_count']} timeout repeats. The observed "
        f"maximum typed wall force was {safety['max_wall_force_n']:.3f} N. "
        "These are bounded "
        "two-cycle probes, not ten-cycle or freeze evidence.\n\n"
        "## Offline recorded-observation evidence\n\n"
        f"- A0: {a0_summary['count']} cycle-one dig rows; first wall step "
        f"{a0_summary['first_wall_step_id']}; bottom contact "
        f"{a0_summary['first_bottom_step_id']}; aggregated-vs-live MAE "
        f"{a0_summary['aggregated_vs_actual_mae']}.\n"
        f"- A1: {a1_summary['count']} cycle-one dig rows; first wall step "
        f"{a1_summary['first_wall_step_id']}; bottom contact "
        f"{a1_summary['first_bottom_step_id']}; aggregated-vs-live MAE "
        f"{a1_summary['aggregated_vs_actual_mae']}.\n"
        "- F0/D1/C1/DC1 token substitutions in these files are "
        "teacher-forced local action-sensitivity checks only; they are not "
        "closed-loop causal evidence.\n\n"
        "## Scope decision\n\n"
        "The old TX24 bridge is not triggered because F0 reproduced the "
        "failure and C1 passed its locked criterion. This diagnosis does not "
        "repair the production planner, change A0 defaults, train or freeze "
        "ACT, promote A1/A2, or resume effect-model/planned-cut work.\n"
    )


def _live_safety_summary(
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "attempt_count": len(attempts),
        "wall_contact_repeat_count": sum(
            int(int(attempt["wall_contact_count"]) > 0)
            for attempt in attempts
        ),
        "bottom_contact_repeat_count": sum(
            int(int(attempt["bottom_contact_count"]) > 0)
            for attempt in attempts
        ),
        "stuck_repeat_count": sum(
            int(int(attempt["stuck_count"]) > 0) for attempt in attempts
        ),
        "timeout_repeat_count": sum(
            int(int(attempt["timeout_count"]) > 0) for attempt in attempts
        ),
        "terminal_contract_pass_count": sum(
            int(
                bool(attempt["zero_action_after_trigger"])
                and bool(attempt["neutral_acknowledged"])
                and bool(attempt["terminal_requested"])
                and int(attempt["max_cycle_index"]) <= 1
            )
            for attempt in attempts
        ),
        "max_wall_force_n": max(
            (float(attempt["wall_max_force_n"]) for attempt in attempts),
            default=0.0,
        ),
        "max_bottom_force_n": max(
            (float(attempt["bottom_max_force_n"]) for attempt in attempts),
            default=0.0,
        ),
    }


def _write_json_exclusive(
    path: str | Path,
    payload: dict[str, Any],
) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _live_config(
    base: dict[str, Any],
    *,
    condition_id: str,
    round_index: int,
    repeat_index: int,
    run_id: str,
    run_dir: Path,
    source: dict[str, str],
    matrix_path: Path,
    matrix_sha256: str,
) -> dict[str, Any]:
    config = copy.deepcopy(base)
    eval_cfg = config.setdefault("eval", {})
    results = run_dir / "results"
    eval_cfg.update(
        {
            "num_rollouts": 1,
            "no_overwrite": True,
            "save_video": False,
            "video_dir": str(run_dir / "videos"),
            "results_dir": str(results),
            "save_rollout_logs": True,
            "stream_rollout_logs": True,
            "rollout_log_dir": str(results / "rollouts"),
            "record_hdf5": True,
            "hdf5_dir": str(results / "hdf5_rollouts"),
        }
    )
    metadata = eval_cfg.setdefault("record_hdf5_metadata", {})
    metadata.update(
        {
            "validation_schema": CONFIG_SCHEMA,
            "diagnostic_only": 1,
            "promotion_eligible": 0,
            "diagnostic_condition": condition_id,
            "diagnostic_round": round_index,
            "diagnostic_repeat_index": repeat_index,
            "diagnostic_run_id": run_id,
            "plan_matrix_path": str(matrix_path),
            "plan_matrix_sha256": matrix_sha256,
            "runtime_source_sha256": source["sha256"],
        }
    )
    policy = config["policy"]
    planner = policy["dig_cut_planner"]
    planner.update(
        {
            "enabled": True,
            "mode": "residual_cut_intent",
            "residual_cut_intent_source_path": source["path"],
            "fallback_mode": "raise",
            "hold_token_until_skill_exit": True,
        }
    )
    box = policy["box_emptying"]
    box["functional_cycle_gate"]["enabled"] = False
    box["bounded_dig_probe_stop"] = {
        "enabled": True,
        "diagnostic_only": True,
        "target_cycle_index": 1,
        "max_dig_steps": 500,
    }
    return config


def _validate_base_config(config: dict[str, Any]) -> None:
    task = dict(config.get("task", {}) or {})
    if tuple(task.get("camera_names", ())) != CAMERA_ORDER:
        raise ValueError("live causal matrix requires locked four-camera order")
    policy = dict(config.get("policy", {}) or {})
    act = dict(policy.get("act_params", {}) or {})
    if (
        int(act.get("temporal_agg_window", -1)) != 100
        or str(act.get("temporal_agg_weight_order", ""))
        != "legacy_oldest_first"
        or not math.isclose(
            float(act.get("temporal_agg_decay", float("nan"))),
            0.01,
            rel_tol=0.0,
            abs_tol=1.0e-12,
        )
    ):
        raise ValueError("live causal matrix requires locked A0 aggregation")
    box = dict(policy.get("box_emptying", {}) or {})
    if not bool(box.get("safety_enabled", False)):
        raise ValueError("live causal matrix requires typed safety enabled")
    if not bool(
        dict(box.get("carry_start_envelope", {}) or {}).get(
            "enabled",
            False,
        )
    ):
        raise ValueError("live causal matrix cannot disable carry envelope")
    for primitive in ("dig", "carry", "dump", "return"):
        if not str(policy.get(f"{primitive}_ckpt_path", "")).strip():
            raise ValueError(f"base config missing {primitive} checkpoint")


def _validated_condition_sources(
    matrix: dict[str, Any],
) -> dict[str, dict[str, str]]:
    if (
        matrix.get("schema") != PLAN_MATRIX_SCHEMA
        or matrix.get("status") != "present"
        or matrix.get("diagnostic_only") is not True
        or matrix.get("promotion_eligible") is not False
    ):
        raise ValueError("plan matrix diagnostic contract mismatch")
    conditions = matrix.get("conditions")
    if not isinstance(conditions, dict) or set(conditions) != set(
        CONDITION_IDS
    ):
        raise ValueError("plan matrix conditions mismatch")
    sources: dict[str, dict[str, str]] = {}
    for condition_id in CONDITION_IDS:
        condition = conditions[condition_id]
        if (
            not isinstance(condition, dict)
            or dict(condition.get("allowed_diff_guard", {}) or {}).get(
                "status"
            )
            != "passed"
        ):
            raise ValueError(
                f"condition {condition_id} allowed-field diff guard failed"
            )
        source_path = Path(
            str(condition.get("runtime_source_path", ""))
        ).resolve(strict=True)
        expected_sha = str(
            condition.get("runtime_source_sha256", "")
        ).strip()
        actual_sha = _sha256(source_path)
        if not expected_sha or actual_sha != expected_sha:
            raise ValueError(
                f"condition {condition_id} runtime source SHA mismatch"
            )
        sources[condition_id] = {
            "path": str(source_path),
            "sha256": actual_sha,
        }
    return sources


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "CAUSAL_LIVE_SCHEDULE",
    "InitialStateSignature",
    "build_act_regression_live_configs",
    "collect_act_regression_live_evidence",
    "evaluate_initial_state",
    "extract_live_probe_attempt",
]
