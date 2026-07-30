"""Build auditable ACT freeze-gate records from real Unity rollout artifacts."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import h5py
import numpy as np

from testbed.data.schema import (
    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX,
    ENV_STATE_CONTRACT_VERSION_V2_4,
    ENV_STATE_DIG_AREA_CELL_AREA_IDX,
    ENV_STATE_DIG_AREA_CURRENT_REMAINING_MASS_IDX,
    ENV_STATE_DIG_AREA_INITIAL_REMAINING_MASS_IDX,
    ENV_STATE_DIG_AREA_REMAINING_MASS_VALID_MASK_IDX,
    ENV_STATE_DIG_AREA_REMAINING_SOIL_VOLUME_START_IDX,
    ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX,
    ENV_STATE_MASS_IN_BUCKET_IDX,
    ENV_STATE_V2_4_DIM,
)
from testbed.eval.act_freeze_bundle import VALIDATION_SCHEMA

PRIMITIVES = ("dig", "carry", "dump", "return")
_ROLLOUT_RE = re.compile(r"rollout_(\d{3})\.jsonl\Z")


class ActUnityValidationContractError(RuntimeError):
    """Raised when a live artifact cannot prove the locked freeze contract."""


def build_act_unity_validation_record(
    *,
    rows: Sequence[Mapping[str, Any]],
    artifact_path: str | Path,
    reset_id: str,
    stable_window_steps: int = 10,
    stable_depth_range_m: float = 0.002,
    low_payload_kg: float = 15.0,
    low_progress_m3: float = 0.005,
) -> dict[str, Any]:
    """Derive one reset record without deciding whether the 3x10 gate passes."""

    if not str(reset_id).strip():
        raise ActUnityValidationContractError("reset_id_missing")
    if stable_window_steps <= 0:
        raise ValueError("stable_window_steps must be positive")
    artifact = Path(artifact_path)
    attrs = _read_runtime_attrs(artifact)
    normalized_rows = _validate_rows(rows)
    cycles = _cycle_boundaries(normalized_rows)
    dig_index_by_cycle = _dig_index_by_cycle(normalized_rows)
    full_cycle_ids = _completed_full_cycle_ids(
        cycles,
        dig_index_by_cycle=dig_index_by_cycle,
    )
    effective_count, outcomes = _effective_cycle_outcomes(
        rows=normalized_rows,
        cycles=cycles,
        full_cycle_ids=full_cycle_ids,
        dig_index_by_cycle=dig_index_by_cycle,
        stable_window_steps=stable_window_steps,
        stable_depth_range_m=stable_depth_range_m,
        low_payload_kg=low_payload_kg,
        low_progress_m3=low_progress_m3,
    )
    valid_rows = [
        row
        for row in normalized_rows
        if _residual_valid(_row_env(row))
    ]
    if not valid_rows:
        raise ActUnityValidationContractError(
            "remaining_mass_valid_observation_missing"
        )
    initial_mass = float(
        _row_env(valid_rows[0])[ENV_STATE_DIG_AREA_INITIAL_REMAINING_MASS_IDX]
    )
    final_mass = float(
        _row_env(valid_rows[-1])[ENV_STATE_DIG_AREA_CURRENT_REMAINING_MASS_IDX]
    )
    if not math.isfinite(initial_mass) or initial_mass <= 0.0:
        raise ActUnityValidationContractError("initial_remaining_mass_invalid")
    if not math.isfinite(final_mass) or final_mass < 0.0:
        raise ActUnityValidationContractError("final_remaining_mass_invalid")

    latencies = [
        float(row["policy_inference_latency_ms"])
        for row in normalized_rows
        if str(row.get("skill_name", "")) in PRIMITIVES
        and str(row.get("primitive_checkpoint_path", "")).strip()
        and _finite_positive(row.get("policy_inference_latency_ms"))
    ]
    wall_count = max(
        int(round(_row_env(row)[ENV_STATE_EXCAVATOR_WALL_CONTACT_SESSION_COUNT_IDX]))
        for row in normalized_rows
    )
    bottom_count = max(
        int(
            round(
                _row_env(row)[
                    ENV_STATE_BUCKET_FACTORY_FLOOR_CONTACT_SESSION_COUNT_IDX
                ]
            )
        )
        for row in normalized_rows
    )
    record = {
        "schema": VALIDATION_SCHEMA,
        "reset_id": str(reset_id),
        "cycle_count": len(dig_index_by_cycle),
        "completed_full_cycle_count": len(full_cycle_ids),
        "effective_move_cycle_count": int(effective_count),
        "initial_remaining_mass_kg": initial_mass,
        "final_remaining_mass_kg": final_mass,
        "wall_contact_count": wall_count,
        "bottom_contact_count": bottom_count,
        "stuck_count": _count_safety_events(normalized_rows, "stuck"),
        "timeout_count": _timeout_count(normalized_rows),
        "four_camera_inference_latency_ms": latencies,
        "artifact_path": str(artifact.resolve()),
        "unity_build_id": attrs["runtime_build_id"],
        "scene_id": attrs["unity_scene_id"],
        "unity_source_sha256": attrs["unity_source_sha256"],
        "env_state_contract_version": attrs["env_state_contract_version"],
        "cycle_outcomes": outcomes,
        "derivation": {
            "stable_window_steps": int(stable_window_steps),
            "stable_depth_range_m": float(stable_depth_range_m),
            "low_payload_kg": float(low_payload_kg),
            "low_progress_m3": float(low_progress_m3),
            "completed_full_cycle_rule": (
                "dig_carry_dump_return_then_next_cycle_dig"
            ),
        },
    }
    return record


def build_act_unity_validation_records(
    *,
    results_dir: str | Path,
    output_dir: str | Path,
    expected_rollout_count: int = 3,
    seed_base: int = 1000,
) -> list[dict[str, Any]]:
    """Build no-overwrite per-reset JSON plus one manifest."""

    source = Path(results_dir)
    destination = Path(output_dir)
    if destination.exists():
        raise FileExistsError(f"validation output already exists: {destination}")
    if expected_rollout_count <= 0:
        raise ValueError("expected_rollout_count must be positive")
    rollout_dir = source / "rollouts"
    hdf5_dir = source / "hdf5_rollouts"
    indexed: list[tuple[int, Path]] = []
    for path in sorted(rollout_dir.glob("rollout_*.jsonl")):
        match = _ROLLOUT_RE.fullmatch(path.name)
        if match is not None:
            indexed.append((int(match.group(1)), path))
    expected_ids = list(range(expected_rollout_count))
    actual_ids = [index for index, _ in indexed]
    if actual_ids != expected_ids:
        raise ActUnityValidationContractError(
            f"rollout_inventory_mismatch:expected={expected_ids}:actual={actual_ids}"
        )

    records: list[dict[str, Any]] = []
    destination.mkdir(parents=True, exist_ok=False)
    record_paths: list[str] = []
    for rollout_id, jsonl_path in indexed:
        artifact = hdf5_dir / f"episode_{rollout_id}.hdf5"
        rows = _read_jsonl(jsonl_path)
        record = build_act_unity_validation_record(
            rows=rows,
            artifact_path=artifact,
            reset_id=f"seed_{seed_base + rollout_id}",
        )
        output_path = destination / f"validation_reset_{rollout_id:03d}.json"
        output_path.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        records.append(record)
        record_paths.append(str(output_path.resolve()))
    manifest = {
        "schema": "act_unity_closed_loop_validation_manifest_v1",
        "source_results_dir": str(source.resolve()),
        "record_count": len(records),
        "records": record_paths,
    }
    (destination / "validation_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return records


def _read_runtime_attrs(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ActUnityValidationContractError(f"artifact_missing:{path}")
    with h5py.File(path, "r") as handle:
        recorder_metadata = handle.get("metadata")
        values = {
            name: _text(
                handle.attrs.get(
                    name,
                    (
                        recorder_metadata.attrs.get(name, "")
                        if isinstance(recorder_metadata, h5py.Group)
                        else ""
                    ),
                )
            ).strip()
            for name in (
                "env_state_contract_version",
                "runtime_build_id",
                "unity_scene_id",
                "unity_source_sha256",
            )
        }
    if values["env_state_contract_version"] != ENV_STATE_CONTRACT_VERSION_V2_4:
        raise ActUnityValidationContractError(
            "env_state_contract_version_mismatch:"
            f"{values['env_state_contract_version']}"
        )
    for name in ("runtime_build_id", "unity_scene_id", "unity_source_sha256"):
        if not values[name]:
            raise ActUnityValidationContractError(f"{name}_missing")
    return values


def _validate_rows(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if not rows:
        raise ActUnityValidationContractError("rollout_rows_missing")
    normalized: list[dict[str, Any]] = []
    previous_step: int | None = None
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            raise ActUnityValidationContractError(f"row_not_mapping:{index}")
        row = dict(raw)
        step = int(row.get("step_id", row.get("t", -1)))
        if previous_step is not None and step <= previous_step:
            raise ActUnityValidationContractError("step_id_not_strictly_increasing")
        previous_step = step
        env = _row_env(row)
        if env.size != ENV_STATE_V2_4_DIM:
            raise ActUnityValidationContractError(
                f"env_state_dim_mismatch:{env.size}"
            )
        if not np.isfinite(env).all():
            raise ActUnityValidationContractError("env_state_non_finite")
        normalized.append(row)
    return normalized


def _cycle_boundaries(
    rows: Sequence[Mapping[str, Any]],
) -> dict[int, dict[str, int]]:
    by_cycle: dict[int, list[int]] = {}
    for index, row in enumerate(rows):
        cycle_id = int(row.get("primitive_cycle_index", -1))
        if cycle_id < 0:
            continue
        by_cycle.setdefault(cycle_id, []).append(index)
    cycles: dict[int, dict[str, int]] = {}
    for cycle_id, indices in sorted(by_cycle.items()):
        skill_first: dict[str, int] = {}
        for index in indices:
            skill = str(rows[index].get("skill_name", ""))
            if skill in PRIMITIVES:
                skill_first.setdefault(skill, index)
        positions = [skill_first.get(name, -1) for name in PRIMITIVES]
        if all(position >= 0 for position in positions) and positions == sorted(
            positions
        ):
            cycles[cycle_id] = {
                **skill_first,
                "first": indices[0],
                "last": indices[-1],
            }
    return cycles


def _completed_full_cycle_ids(
    cycles: Mapping[int, Mapping[str, int]],
    *,
    dig_index_by_cycle: Mapping[int, int],
) -> list[int]:
    completed: list[int] = []
    for cycle_id in sorted(cycles):
        next_dig_index = dig_index_by_cycle.get(cycle_id + 1)
        if next_dig_index is not None and int(next_dig_index) > int(
            cycles[cycle_id]["return"]
        ):
            completed.append(cycle_id)
    return completed


def _dig_index_by_cycle(
    rows: Sequence[Mapping[str, Any]],
) -> dict[int, int]:
    result: dict[int, int] = {}
    for index, row in enumerate(rows):
        if str(row.get("skill_name", "")) != "dig":
            continue
        cycle_id = int(row.get("primitive_cycle_index", -1))
        if cycle_id >= 0:
            result.setdefault(cycle_id, index)
    return result


def _effective_cycle_outcomes(
    *,
    rows: Sequence[Mapping[str, Any]],
    cycles: Mapping[int, Mapping[str, int]],
    full_cycle_ids: Sequence[int],
    dig_index_by_cycle: Mapping[int, int],
    stable_window_steps: int,
    stable_depth_range_m: float,
    low_payload_kg: float,
    low_progress_m3: float,
) -> tuple[int, list[dict[str, Any]]]:
    effective_count = 0
    outcomes: list[dict[str, Any]] = []
    for cycle_id in full_cycle_ids:
        cycle = cycles[cycle_id]
        dig_index = int(cycle["dig"])
        return_index = int(cycle["return"])
        next_dig_index = int(dig_index_by_cycle[cycle_id + 1])
        pre = _stable_snapshot(
            rows,
            start=max(0, dig_index - max(80, stable_window_steps)),
            end=dig_index,
            window=stable_window_steps,
            max_depth_range_m=stable_depth_range_m,
            prefer_last=True,
        )
        post = _stable_snapshot(
            rows,
            start=return_index,
            end=next_dig_index,
            window=stable_window_steps,
            max_depth_range_m=stable_depth_range_m,
            prefer_last=False,
        )
        payload = max(
            float(_row_env(row)[ENV_STATE_MASS_IN_BUCKET_IDX])
            for row in rows[dig_index:next_dig_index]
        )
        if pre is None or post is None:
            outcomes.append(
                {
                    "cycle_index": cycle_id,
                    "stable_evidence": False,
                    "payload_kg": payload,
                    "stable_net_removed_volume_m3": None,
                    "effective_move": False,
                }
            )
            continue
        net_removed = max(0.0, float(np.sum(pre - post)))
        effective = bool(
            payload >= low_payload_kg and net_removed >= low_progress_m3
        )
        effective_count += int(effective)
        outcomes.append(
            {
                "cycle_index": cycle_id,
                "stable_evidence": True,
                "payload_kg": payload,
                "stable_net_removed_volume_m3": net_removed,
                "effective_move": effective,
            }
        )
    return effective_count, outcomes


def _stable_snapshot(
    rows: Sequence[Mapping[str, Any]],
    *,
    start: int,
    end: int,
    window: int,
    max_depth_range_m: float,
    prefer_last: bool,
) -> np.ndarray | None:
    if end - start < window:
        return None
    starts = list(range(start, end - window + 1))
    if prefer_last:
        starts.reverse()
    for offset in starts:
        envs = [_row_env(row) for row in rows[offset : offset + window]]
        if not all(_residual_valid(env) for env in envs):
            continue
        areas = np.asarray(
            [env[ENV_STATE_DIG_AREA_CELL_AREA_IDX] for env in envs],
            dtype=np.float64,
        )
        if (
            not np.isfinite(areas).all()
            or np.any(areas <= 0.0)
            or float(np.ptp(areas)) > 1.0e-6
        ):
            continue
        volumes = np.asarray(
            [
                env[
                    ENV_STATE_DIG_AREA_REMAINING_SOIL_VOLUME_START_IDX :
                    ENV_STATE_DIG_AREA_REMAINING_SOIL_VOLUME_START_IDX + 6
                ]
                for env in envs
            ],
            dtype=np.float64,
        )
        depths = volumes / areas[:, None]
        if np.any(np.ptp(depths, axis=0) > max_depth_range_m):
            continue
        return np.median(volumes, axis=0)
    return None


def _timeout_count(rows: Sequence[Mapping[str, Any]]) -> int:
    pre_dig = max(
        int(row.get("pre_dig_align_timeout_count", 0) or 0) for row in rows
    )
    transition = 0
    previous = False
    for row in rows:
        current = bool(row.get("transition_timeout", False))
        if current and not previous:
            transition += 1
        previous = current
    return pre_dig + transition + _count_safety_events(rows, "timeout")


def _count_safety_events(
    rows: Sequence[Mapping[str, Any]],
    prefix: str,
) -> int:
    steps = {
        int(row.get("step_id", row.get("t", -1)))
        for row in rows
        if str(row.get("box_safety_reason", "")).startswith(prefix)
        and bool(row.get("box_safety_awaiting_neutral_ack", False))
    }
    return len(steps)


def _residual_valid(env: np.ndarray) -> bool:
    return bool(
        env.size == ENV_STATE_V2_4_DIM
        and env[ENV_STATE_DIG_AREA_REMAINING_MASS_VALID_MASK_IDX] >= 0.5
    )


def _row_env(row: Mapping[str, Any]) -> np.ndarray:
    return np.asarray(row.get("env_state", []), dtype=np.float64).reshape(-1)


def _finite_positive(value: Any) -> bool:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(parsed) and parsed > 0.0


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, json.JSONDecodeError) as exc:
        raise ActUnityValidationContractError(
            f"rollout_jsonl_invalid:{path}"
        ) from exc


def _text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, np.bytes_):
        return bytes(value).decode("utf-8")
    return str(value)


__all__ = [
    "ActUnityValidationContractError",
    "build_act_unity_validation_record",
    "build_act_unity_validation_records",
]
