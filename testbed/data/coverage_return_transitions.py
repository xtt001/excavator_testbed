"""Strict-train return transitions paired with immutable coverage tuples.

This module owns an offline data contract.  It binds each exact dig tuple to
the preceding gold return transition, where one exists, and calibrates the
11-dimensional return-start support used by the planner.  It never selects an
online target or relaxes a runtime gate.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from testbed.data.coverage_execution_library import (
    COVERAGE_EXECUTION_LIBRARY_SCHEMA,
    STRICT18_COVERAGE_EXECUTION_SAMPLE_COUNT,
)
from testbed.data.coverage_return_transition_io import (
    RETURN_START_ENVELOPE_SCHEMA,
    RETURN_START_ENVELOPE_TOKEN_DIM,
    RETURN_START_FACTS_FEATURE_ORDER,
    RETURN_START_FACTS_SCHEMA,
    execution_records,
    float_list,
    json_mapping,
    read_dig_start,
    read_return_transition,
    strict_file,
    strict_primitive_root,
    validate_source_split,
    yaml_mapping,
)
from testbed.data.handoff_envelope import (
    STRICT18_TRAIN_SOURCE_EPISODE_IDS,
    STRICT18_VALIDATION_SOURCE_EPISODE_IDS,
)
from testbed.data.schema import (
    DS_ENV_STATE,
    DS_QPOS,
    DS_QVEL,
    ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX,
)

COVERAGE_RETURN_TRANSITION_LIBRARY_SCHEMA = (
    "strict_train_coverage_return_transition_library_v1"
)
RETURN_START_REACHABILITY_PROFILE = (
    "strict_train_return_start_reachability_11d_v1"
)
STRICT18_RETURN_TRAIN_SAMPLE_COUNT = 358
STRICT18_PAIRED_POST_RETURN_TUPLE_COUNT = 353
STRICT18_POST_RETURN_INELIGIBLE_TUPLE_COUNT = 21
STRICT18_CYCLE0_ONLY_TUPLE_COUNT = 16
STRICT18_NON_GOLD_RETURN_PAIR_REQUIRED_COUNT = 5


def build_coverage_return_transition_library(
    *,
    return_primitives_dir: str | Path,
    return_split_path: str | Path,
    dig_primitives_dir: str | Path,
    dig_split_path: str | Path,
    execution_library_path: str | Path,
    output_path: str | Path,
) -> Path:
    """Build the no-overwrite strict-train tuple/return transition artifact."""

    output = Path(output_path).expanduser().resolve()
    if output.exists():
        raise FileExistsError(
            "refusing to overwrite coverage return transition library: "
            f"{output}"
        )

    return_root = strict_primitive_root(
        return_primitives_dir,
        primitive_name="return",
    )
    dig_root = strict_primitive_root(
        dig_primitives_dir,
        primitive_name="dig",
    )
    return_split = strict_file(return_split_path, label="return source split")
    dig_split = strict_file(dig_split_path, label="dig source split")
    execution_path = strict_file(
        execution_library_path,
        label="coverage execution library",
    )

    return_split_bytes = return_split.read_bytes()
    dig_split_bytes = dig_split.read_bytes()
    execution_bytes = execution_path.read_bytes()
    return_split_payload = yaml_mapping(
        return_split_bytes,
        label="return source split",
    )
    dig_split_payload = yaml_mapping(
        dig_split_bytes,
        label="dig source split",
    )
    execution_payload = json_mapping(
        execution_bytes,
        label="coverage execution library",
    )

    return_contract = validate_source_split(
        return_split_payload,
        primitive_name="return",
        dataset_dir=return_root,
        expected_train_count=STRICT18_RETURN_TRAIN_SAMPLE_COUNT,
    )
    dig_contract = validate_source_split(
        dig_split_payload,
        primitive_name="dig",
        dataset_dir=dig_root,
        expected_train_count=STRICT18_COVERAGE_EXECUTION_SAMPLE_COUNT,
    )
    execution_records_by_id = execution_records(
        execution_payload,
        expected_schema=COVERAGE_EXECUTION_LIBRARY_SCHEMA,
        expected_ids=dig_contract["train_ids"],
    )

    input_digest = hashlib.sha256()
    input_digest.update(
        f"{COVERAGE_RETURN_TRANSITION_LIBRARY_SCHEMA}\0".encode()
    )
    input_digest.update(hashlib.sha256(return_split_bytes).digest())
    input_digest.update(hashlib.sha256(dig_split_bytes).digest())
    input_digest.update(hashlib.sha256(execution_bytes).digest())

    return_rows: list[dict[str, Any]] = []
    return_by_target: dict[tuple[int, int], dict[str, Any]] = {}
    for primitive_episode_id in return_contract["train_ids"]:
        source_episode_id = return_contract["source_by_primitive"][
            primitive_episode_id
        ]
        path = return_root / f"episode_{primitive_episode_id}.hdf5"
        row = read_return_transition(
            path,
            primitive_episode_id=primitive_episode_id,
            expected_source_episode_id=source_episode_id,
        )
        key = (
            int(row["source_episode_id"]),
            int(row["target_source_cycle_id"]),
        )
        if key in return_by_target:
            raise ValueError(
                "Gold return transitions repeat a target source cycle: "
                f"{key}"
            )
        return_by_target[key] = row
        return_rows.append(row)
        input_digest.update(bytes.fromhex(row["paired_return_source_sha256"]))

    distance_contract, loo_by_return_id = _distance_contract(return_rows)
    records: list[dict[str, Any]] = []
    matched_return_ids: set[int] = set()
    for primitive_episode_id in dig_contract["train_ids"]:
        source_episode_id = dig_contract["source_by_primitive"][
            primitive_episode_id
        ]
        execution_record = execution_records_by_id[primitive_episode_id]
        dig_row = read_dig_start(
            dig_root / f"episode_{primitive_episode_id}.hdf5",
            primitive_episode_id=primitive_episode_id,
            expected_source_episode_id=source_episode_id,
            execution_record=execution_record,
        )
        pair_key = (
            int(source_episode_id),
            int(dig_row["source_cycle_id"]),
        )
        return_row = return_by_target.get(pair_key)
        if return_row is not None:
            return_id = int(return_row["paired_return_primitive_episode_id"])
            matched_return_ids.add(return_id)
            record = _paired_record(
                dig_row=dig_row,
                return_row=return_row,
                loo=loo_by_return_id[return_id],
            )
        else:
            record = _unpaired_record(dig_row)
        records.append(record)
        input_digest.update(bytes.fromhex(dig_row["dig_source_sha256"]))

    records.sort(key=lambda item: int(item["primitive_episode_id"]))
    _validate_final_counts(
        records=records,
        return_rows=return_rows,
        matched_return_ids=matched_return_ids,
    )
    _validate_reference_pair(records)

    return_source_mapping = return_contract["source_by_primitive"]
    dig_source_mapping = dig_contract["source_by_primitive"]
    artifact: dict[str, Any] = {
        "schema": COVERAGE_RETURN_TRANSITION_LIBRARY_SCHEMA,
        "status": "completed",
        "coverage_tuple_sample_count": len(records),
        "gold_return_sample_count": len(return_rows),
        "paired_post_return_tuple_count": sum(
            bool(record["eligibility"]["post_return"])
            for record in records
        ),
        "post_return_ineligible_tuple_count": sum(
            not bool(record["eligibility"]["post_return"])
            for record in records
        ),
        "cycle0_only_tuple_count": sum(
            record["eligibility"]["reason"]
            == "episode_first_no_preceding_return"
            for record in records
        ),
        "non_gold_return_pair_required_count": sum(
            record["eligibility"]["reason"]
            == "non_gold_return_pair_excluded"
            for record in records
        ),
        "source_contract": {
            "primitive_name": "return",
            "training_tier": "gold",
            "primitive_storage_mode": "copy",
            "return_start_envelope_schema": RETURN_START_ENVELOPE_SCHEMA,
            "return_start_envelope_token_dim": (
                RETURN_START_ENVELOPE_TOKEN_DIM
            ),
            "return_start_facts_schema": RETURN_START_FACTS_SCHEMA,
            "return_start_facts_dim": len(
                RETURN_START_FACTS_FEATURE_ORDER
            ),
        },
        "feature_contract": {
            "schema": RETURN_START_FACTS_SCHEMA,
            "dim": len(RETURN_START_FACTS_FEATURE_ORDER),
            "order": list(RETURN_START_FACTS_FEATURE_ORDER),
            "datasets": [
                *(
                    {"dataset": DS_QPOS, "index": index}
                    for index in range(4)
                ),
                *(
                    {"dataset": DS_QVEL, "index": index}
                    for index in range(4)
                ),
                *(
                    {
                        "dataset": DS_ENV_STATE,
                        "index": (
                            ENV_STATE_BUCKET_TIP_DIG_AREA_X_IDX + index
                        ),
                    }
                    for index in range(3)
                ),
            ],
        },
        "pairing_contract": {
            "key": [
                "source_episode_id",
                "return_next_material_cycle_id",
            ],
            "dig_key": ["source_episode_id", "source_cycle_id"],
            "primitive_episode_id_pairing_allowed": False,
            "spatial_nearest_pairing_allowed": False,
            "post_return_requires_gold_pair": True,
            "cycle0_requires_pair": False,
        },
        "distance_contract": distance_contract,
        "source_lineage": {
            "partition": "train",
            "split_policy": "source_identity_exact_allowlist_v1",
            "return_primitives_dir": str(return_root),
            "dig_primitives_dir": str(dig_root),
            "return_train_primitive_episode_ids": list(
                return_contract["train_ids"]
            ),
            "dig_train_primitive_episode_ids": list(
                dig_contract["train_ids"]
            ),
            "train_source_episode_ids": list(
                STRICT18_TRAIN_SOURCE_EPISODE_IDS
            ),
            "validation_source_episode_ids": list(
                STRICT18_VALIDATION_SOURCE_EPISODE_IDS
            ),
            "return_source_episode_id_by_primitive_episode_id": {
                str(key): int(return_source_mapping[key])
                for key in return_contract["train_ids"]
            },
            "dig_source_episode_id_by_primitive_episode_id": {
                str(key): int(dig_source_mapping[key])
                for key in dig_contract["train_ids"]
            },
            "validation_rows_read": 0,
            "non_gold_return_rows_read": 0,
            "partial_layered_salvage_input_views_allowed": False,
        },
        "source_lock": {
            "execution_library_path": str(execution_path),
            "execution_library_sha256": hashlib.sha256(
                execution_bytes
            ).hexdigest(),
            "dig_source_split_path": str(dig_split),
            "dig_source_split_sha256": hashlib.sha256(
                dig_split_bytes
            ).hexdigest(),
            "return_source_split_path": str(return_split),
            "return_source_split_sha256": hashlib.sha256(
                return_split_bytes
            ).hexdigest(),
            "input_sha256": input_digest.hexdigest(),
        },
        "records": records,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        json.dump(
            artifact,
            handle,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        handle.write("\n")
    return output


def _paired_record(
    *,
    dig_row: Mapping[str, Any],
    return_row: Mapping[str, Any],
    loo: Mapping[str, float],
) -> dict[str, Any]:
    return {
        **dict(dig_row),
        "eligibility": {
            "cycle0": True,
            "post_return": True,
            "reason": "gold_return_transition_pair",
        },
        **dict(return_row),
        "return_start_loo_nearest_rms": float(loo["rms"]),
        "return_start_loo_nearest_linf": float(loo["linf"]),
    }


def _unpaired_record(dig_row: Mapping[str, Any]) -> dict[str, Any]:
    source_cycle_id = int(dig_row["source_cycle_id"])
    if source_cycle_id == 0:
        reason = "episode_first_no_preceding_return"
    else:
        reason = "non_gold_return_pair_excluded"
    return {
        **dict(dig_row),
        "eligibility": {
            "cycle0": True,
            "post_return": False,
            "reason": reason,
        },
        "paired_return_exemplar_id": None,
        "paired_return_primitive_episode_id": None,
        "paired_return_source_sha256": None,
        "paired_return_source_cycle_id": None,
        "return_start_local_index": None,
        "return_start_source_step": None,
        "return_handoff_local_index": None,
        "return_handoff_source_step": None,
        "return_start_facts_11d": None,
        "expert_return_handoff_facts_11d": None,
        "exact_return_start_envelope_tokens_v1": None,
        "exact_return_start_envelope_valid_mask": None,
        "exact_return_start_envelope_sha256": None,
        "return_start_loo_nearest_rms": None,
        "return_start_loo_nearest_linf": None,
    }


def _distance_contract(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], dict[int, dict[str, float]]]:
    values = np.asarray(
        [row["return_start_facts_11d"] for row in rows],
        dtype=np.float64,
    )
    expected_shape = (
        STRICT18_RETURN_TRAIN_SAMPLE_COUNT,
        len(RETURN_START_FACTS_FEATURE_ORDER),
    )
    if values.shape != expected_shape or not np.isfinite(values).all():
        raise ValueError(
            "Gold return-start calibration matrix has invalid shape/values: "
            f"{values.shape}"
        )
    p01 = np.percentile(values, 1.0, axis=0)
    p99 = np.percentile(values, 99.0, axis=0)
    scale = p99 - p01
    if not np.isfinite(scale).all() or np.any(scale <= 0.0):
        raise ValueError("Return-start p01-p99 normalization scale is invalid.")

    normalized = (values - p01) / scale
    delta = normalized[:, None, :] - normalized[None, :, :]
    rms_distance = np.sqrt(np.mean(np.square(delta), axis=2))
    linf_distance = np.max(np.abs(delta), axis=2)
    np.fill_diagonal(rms_distance, np.inf)
    np.fill_diagonal(linf_distance, np.inf)
    nearest_rms = np.min(rms_distance, axis=1)
    nearest_linf = np.min(linf_distance, axis=1)
    rms_threshold = float(np.percentile(nearest_rms, 99.0))
    linf_threshold = float(np.percentile(nearest_linf, 99.0))
    if not math.isfinite(rms_threshold) or not math.isfinite(linf_threshold):
        raise ValueError("Return-start LOO thresholds are non-finite.")

    loo_by_return_id = {
        int(row["paired_return_primitive_episode_id"]): {
            "rms": float(nearest_rms[index]),
            "linf": float(nearest_linf[index]),
        }
        for index, row in enumerate(rows)
    }
    return {
        "profile": RETURN_START_REACHABILITY_PROFILE,
        "calibration_sample_count": int(values.shape[0]),
        "calibration_partition": "strict_train_gold_return_only",
        "feature_schema": RETURN_START_FACTS_SCHEMA,
        "feature_order": list(RETURN_START_FACTS_FEATURE_ORDER),
        "normalization": {
            "method": "p01_p99_range",
            "formula": "(query-reference)/(p99-p01)",
            "p01": float_list(p01),
            "p99": float_list(p99),
            "scale": float_list(scale),
            "zero_scale_policy": "error",
        },
        "runtime_reference": "selected_tuple.return_start_facts_11d",
        "metrics": {
            "rms": {
                "formula": "sqrt(mean(normalized_delta**2))",
                "nearest_neighbor_selection": (
                    "independent_leave_one_out"
                ),
                "loo_p99_threshold": rms_threshold,
            },
            "linf": {
                "formula": "max(abs(normalized_delta))",
                "nearest_neighbor_selection": (
                    "independent_leave_one_out"
                ),
                "loo_p99_threshold": linf_threshold,
            },
        },
        "acceptance": "rms_pass AND linf_pass",
        "missing_or_nonfinite": "fail_closed",
    }, loo_by_return_id


def _validate_final_counts(
    *,
    records: Sequence[Mapping[str, Any]],
    return_rows: Sequence[Mapping[str, Any]],
    matched_return_ids: set[int],
) -> None:
    paired = sum(bool(row["eligibility"]["post_return"]) for row in records)
    cycle0 = sum(
        row["eligibility"]["reason"]
        == "episode_first_no_preceding_return"
        for row in records
    )
    non_gold = sum(
        row["eligibility"]["reason"] == "non_gold_return_pair_excluded"
        for row in records
    )
    expected = (
        len(records) == STRICT18_COVERAGE_EXECUTION_SAMPLE_COUNT
        and len(return_rows) == STRICT18_RETURN_TRAIN_SAMPLE_COUNT
        and paired == STRICT18_PAIRED_POST_RETURN_TUPLE_COUNT
        and len(records) - paired
        == STRICT18_POST_RETURN_INELIGIBLE_TUPLE_COUNT
        and cycle0 == STRICT18_CYCLE0_ONLY_TUPLE_COUNT
        and non_gold == STRICT18_NON_GOLD_RETURN_PAIR_REQUIRED_COUNT
    )
    if not expected:
        raise ValueError(
            "Strict return/dig pairing counts changed: "
            f"dig={len(records)}, return={len(return_rows)}, paired={paired}, "
            f"cycle0={cycle0}, non_gold={non_gold}"
        )
    unmatched_gold_returns = len(return_rows) - len(matched_return_ids)
    if unmatched_gold_returns != STRICT18_NON_GOLD_RETURN_PAIR_REQUIRED_COUNT:
        raise ValueError(
            "Expected five gold returns targeting excluded non-gold dig rows; "
            f"got {unmatched_gold_returns}."
        )


def _validate_reference_pair(records: Sequence[Mapping[str, Any]]) -> None:
    matches = [row for row in records if row["exemplar_id"] == "episode_168"]
    if len(matches) != 1:
        raise ValueError("Strict execution library must contain episode_168.")
    row = matches[0]
    if (
        int(row["source_episode_id"]) != 24
        or int(row["source_cycle_id"]) != 1
        or int(row["paired_return_primitive_episode_id"]) != 158
    ):
        raise ValueError(
            "Reference lineage mismatch: episode_168 must pair to "
            "gold return episode_158 in source episode 24."
        )


__all__ = [
    "COVERAGE_RETURN_TRANSITION_LIBRARY_SCHEMA",
    "RETURN_START_FACTS_FEATURE_ORDER",
    "RETURN_START_FACTS_SCHEMA",
    "RETURN_START_REACHABILITY_PROFILE",
    "build_coverage_return_transition_library",
]
