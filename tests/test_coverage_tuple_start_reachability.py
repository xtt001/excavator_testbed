from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from testbed.planner.primitive.coverage.start_reachability import (
    STRICT_TRAIN_COVERAGE_RETURN_TRANSITION_LIBRARY_SCHEMA,
    STRICT_TRAIN_RETURN_START_REACHABILITY_PROFILE,
    CoverageTupleStartReachabilityConfig,
    CoverageTupleStartReachabilityContractError,
    CoverageTupleStartReachabilityService,
)

STRICT_TRAIN_SOURCE_EPISODES = [
    3,
    6,
    7,
    8,
    9,
    13,
    16,
    19,
    23,
    24,
    25,
    27,
    28,
    29,
    30,
    32,
]


def _paired_record(
    *,
    primitive_episode_id: int = 168,
    raw_fields_sha256: str = "4" * 64,
) -> dict[str, Any]:
    return {
        "exemplar_id": f"episode_{primitive_episode_id}",
        "primitive_episode_id": primitive_episode_id,
        "source_episode_id": 24,
        "source_cycle_id": 5,
        "raw_fields_sha256": raw_fields_sha256,
        "eligibility": {
            "cycle0": True,
            "post_return": True,
            "reason": "gold_return_transition_pair",
        },
        "paired_return_primitive_episode_id": 158,
        "paired_return_exemplar_id": "episode_158",
        "paired_return_source_cycle_id": 4,
        "return_start_facts_11d": [0.0] * 11,
        "exact_return_start_envelope_tokens_v1": [
            0.1,
            0.2,
            0.3,
            0.4,
            0.5,
            0.6,
            0.7,
            0.51,
            0.52,
            0.53,
            0.54,
            0.01,
            0.02,
            0.03,
            0.04,
            0.05,
            1.0,
            1.0,
        ],
        "exact_return_start_envelope_valid_mask": [1] * 18,
        "expert_return_handoff_facts_11d": [
            0.61,
            0.62,
            0.63,
            0.64,
            0.0,
            0.0,
            0.0,
            0.0,
            0.4,
            0.5,
            0.6,
        ],
        "expert_dig_start_facts_11d": [
            0.51,
            0.52,
            0.53,
            0.54,
            0.0,
            0.0,
            0.0,
            0.0,
            0.4,
            0.5,
            0.6,
        ],
        "dig_source_sha256": "5" * 64,
        "paired_return_source_sha256": "8" * 64,
    }


def _cycle0_only_record() -> dict[str, Any]:
    return {
        "exemplar_id": "episode_0",
        "primitive_episode_id": 0,
        "source_episode_id": 3,
        "source_cycle_id": 0,
        "raw_fields_sha256": "6" * 64,
        "eligibility": {
            "cycle0": True,
            "post_return": False,
            "reason": "episode_first_no_preceding_return",
        },
        "paired_return_primitive_episode_id": None,
        "paired_return_exemplar_id": None,
        "paired_return_source_cycle_id": None,
        "return_start_facts_11d": None,
        "exact_return_start_envelope_tokens_v1": None,
        "exact_return_start_envelope_valid_mask": None,
        "expert_return_handoff_facts_11d": None,
        "expert_dig_start_facts_11d": [0.0] * 11,
        "dig_source_sha256": "7" * 64,
        "paired_return_source_sha256": None,
    }


def _artifact(
    *,
    records: list[dict[str, Any]] | None = None,
    rms_threshold: float = 0.2242876880450012,
    linf_threshold: float = 0.4098004328849277,
) -> dict[str, Any]:
    records = records or [_paired_record(), _cycle0_only_record()]
    paired_count = sum(
        bool(record["eligibility"]["post_return"]) for record in records
    )
    return {
        "schema": (
            STRICT_TRAIN_COVERAGE_RETURN_TRANSITION_LIBRARY_SCHEMA
        ),
        "status": "completed",
        "coverage_tuple_sample_count": len(records),
        "gold_return_sample_count": 358,
        "paired_post_return_tuple_count": paired_count,
        "post_return_ineligible_tuple_count": len(records) - paired_count,
        "source_lock": {
            "execution_library_sha256": "a" * 64,
            "dig_source_split_sha256": "b" * 64,
            "return_source_split_sha256": "c" * 64,
            "input_sha256": "d" * 64,
        },
        "source_lineage": {
            "partition": "train",
            "train_source_episode_ids": STRICT_TRAIN_SOURCE_EPISODES,
            "validation_source_episode_ids": [33, 34],
            "validation_rows_read": 0,
            "non_gold_return_rows_read": 0,
            "partial_layered_salvage_input_views_allowed": False,
        },
        "source_contract": {
            "primitive_name": "return",
            "training_tier": "gold",
            "primitive_storage_mode": "copy",
            "return_start_envelope_schema": (
                "return_start_envelope_tokens_v1"
            ),
            "return_start_envelope_token_dim": 18,
            "return_start_facts_schema": "return_start_facts_11d_v1",
            "return_start_facts_dim": 11,
        },
        "feature_contract": {
            "schema": "return_start_facts_11d_v1",
            "dim": 11,
            "order": [
                "qpos[0]",
                "qpos[1]",
                "qpos[2]",
                "qpos[3]",
                "qvel[0]",
                "qvel[1]",
                "qvel[2]",
                "qvel[3]",
                "bucket_tip_dig_area_x_m",
                "bucket_tip_dig_area_y_m",
                "bucket_tip_dig_area_z_m",
            ],
        },
        "distance_contract": {
            "profile": STRICT_TRAIN_RETURN_START_REACHABILITY_PROFILE,
            "calibration_sample_count": 358,
            "calibration_partition": "strict_train_gold_return_only",
            "feature_schema": "return_start_facts_11d_v1",
            "feature_order": [
                "qpos[0]",
                "qpos[1]",
                "qpos[2]",
                "qpos[3]",
                "qvel[0]",
                "qvel[1]",
                "qvel[2]",
                "qvel[3]",
                "bucket_tip_dig_area_x_m",
                "bucket_tip_dig_area_y_m",
                "bucket_tip_dig_area_z_m",
            ],
            "normalization": {
                "method": "p01_p99_range",
                "formula": "(query-reference)/(p99-p01)",
                "p01": [-1.0] * 11,
                "p99": [1.0] * 11,
                "scale": [2.0] * 11,
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
        },
        "records": records,
    }


def _write_artifact(
    path: Path,
    *,
    artifact: dict[str, Any] | None = None,
) -> str:
    path.write_text(
        json.dumps(artifact or _artifact(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _service(
    path: Path,
    sha256: str,
) -> CoverageTupleStartReachabilityService:
    return CoverageTupleStartReachabilityService.from_config(
        CoverageTupleStartReachabilityConfig.from_mapping(
            {
                "enabled": True,
                "profile": STRICT_TRAIN_RETURN_START_REACHABILITY_PROFILE,
                "artifact_path": str(path),
                "artifact_sha256": sha256,
                "execution_library_sha256": "a" * 64,
                "missing_contract": "fail_closed",
            }
        )
    )


def test_exact_paired_tuple_passes_and_exposes_immutable_return_contract(
    tmp_path: Path,
) -> None:
    path = tmp_path / "return_transitions.json"
    service = _service(path, _write_artifact(path))

    result = service.evaluate(
        exemplar_id="episode_168",
        raw_fields_sha256="4" * 64,
        live_return_start_facts=np.zeros(11, dtype=np.float32),
        selection_phase="post_return",
    )

    assert result.eligible is True
    assert result.rejection_reason == ""
    assert result.cycle0_eligible is True
    assert result.post_return_eligible is True
    assert result.paired_return_primitive_episode_id == 158
    assert result.paired_return_exemplar_id == "episode_158"
    assert result.paired_return_source_cycle_id == 4
    assert result.exact_return_start_envelope_tokens[7:11] == pytest.approx(
        (0.51, 0.52, 0.53, 0.54)
    )
    assert result.exact_return_start_envelope_valid_mask == (1,) * 18
    assert result.paired_handoff_qpos == pytest.approx(
        (0.61, 0.62, 0.63, 0.64)
    )
    assert result.rms_distance == pytest.approx(0.0)
    assert result.linf_distance == pytest.approx(0.0)
    assert result.as_trace_fields()["tuple_start_paired_return_id"] == 158
    with pytest.raises(FrozenInstanceError):
        result.eligible = False  # type: ignore[misc]


@pytest.mark.parametrize(
    ("live_facts", "rms_threshold", "linf_threshold", "failed_metric"),
    (
        ([0.82] + [0.0] * 10, 0.20, 0.40, "linf"),
        ([0.50] * 11, 0.20, 0.30, "rms"),
    ),
)
def test_post_return_requires_both_rms_and_linf_thresholds(
    tmp_path: Path,
    live_facts: list[float],
    rms_threshold: float,
    linf_threshold: float,
    failed_metric: str,
) -> None:
    path = tmp_path / f"{failed_metric}.json"
    sha256 = _write_artifact(
        path,
        artifact=_artifact(
            rms_threshold=rms_threshold,
            linf_threshold=linf_threshold,
        ),
    )

    result = _service(path, sha256).evaluate(
        exemplar_id="episode_168",
        raw_fields_sha256="4" * 64,
        live_return_start_facts=live_facts,
        selection_phase="post_return",
    )

    assert result.eligible is False
    assert result.rejection_reason == "tuple_start_out_of_support"
    if failed_metric == "linf":
        assert result.rms_distance < result.rms_threshold
        assert result.linf_distance > result.linf_threshold
    else:
        assert result.rms_distance > result.rms_threshold
        assert result.linf_distance < result.linf_threshold


def test_cycle0_flag_does_not_require_a_paired_return(
    tmp_path: Path,
) -> None:
    path = tmp_path / "cycle0.json"
    service = _service(path, _write_artifact(path))

    cycle0 = service.evaluate(
        exemplar_id="episode_0",
        raw_fields_sha256="6" * 64,
        live_return_start_facts=None,
        selection_phase="cycle0",
    )
    post_return = service.evaluate(
        exemplar_id="episode_0",
        raw_fields_sha256="6" * 64,
        live_return_start_facts=[0.0] * 11,
        selection_phase="post_return",
    )

    assert cycle0.eligible is True
    assert cycle0.cycle0_eligible is True
    assert cycle0.post_return_eligible is False
    assert cycle0.paired_return_primitive_episode_id == -1
    assert post_return.eligible is False
    assert post_return.rejection_reason == "tuple_start_not_post_return_eligible"


@pytest.mark.parametrize(
    "live_facts",
    (
        [0.0] * 10,
        [0.0] * 10 + [float("nan")],
        "not-a-vector",
    ),
)
def test_missing_or_non_finite_live_facts_fail_closed(
    tmp_path: Path,
    live_facts: Any,
) -> None:
    path = tmp_path / "facts.json"
    service = _service(path, _write_artifact(path))

    result = service.evaluate(
        exemplar_id="episode_168",
        raw_fields_sha256="4" * 64,
        live_return_start_facts=live_facts,
        selection_phase="post_return",
    )

    assert result.eligible is False
    assert result.rejection_reason == "tuple_start_facts_invalid"


def test_missing_mapping_and_raw_sha_drift_fail_closed(
    tmp_path: Path,
) -> None:
    path = tmp_path / "mapping.json"
    service = _service(path, _write_artifact(path))

    missing = service.evaluate(
        exemplar_id="episode_999",
        raw_fields_sha256="4" * 64,
        live_return_start_facts=[0.0] * 11,
        selection_phase="post_return",
    )
    drift = service.evaluate(
        exemplar_id="episode_168",
        raw_fields_sha256="9" * 64,
        live_return_start_facts=[0.0] * 11,
        selection_phase="post_return",
    )

    assert missing.eligible is False
    assert missing.rejection_reason == "tuple_start_mapping_missing"
    assert drift.eligible is False
    assert drift.rejection_reason == "tuple_start_raw_fields_sha_drift"
    assert drift.exact_return_start_envelope_tokens == ()


def test_artifact_sha_schema_and_strict_lineage_are_fail_closed(
    tmp_path: Path,
) -> None:
    path = tmp_path / "bad.json"
    artifact = _artifact()
    sha256 = _write_artifact(path, artifact=artifact)

    with pytest.raises(
        CoverageTupleStartReachabilityContractError,
        match="artifact_sha256_mismatch",
    ):
        _service(path, "0" * 64)

    artifact["source_lineage"]["validation_rows_read"] = 1
    sha256 = _write_artifact(path, artifact=artifact)
    with pytest.raises(
        CoverageTupleStartReachabilityContractError,
        match="validation_rows_read",
    ):
        _service(path, sha256)

    artifact = _artifact()
    artifact["source_lineage"][
        "partial_layered_salvage_input_views_allowed"
    ] = True
    sha256 = _write_artifact(path, artifact=artifact)
    with pytest.raises(
        CoverageTupleStartReachabilityContractError,
        match="partial_layered_salvage",
    ):
        _service(path, sha256)

    artifact = _artifact()
    artifact["source_lineage"]["non_gold_return_rows_read"] = 1
    sha256 = _write_artifact(path, artifact=artifact)
    with pytest.raises(
        CoverageTupleStartReachabilityContractError,
        match="non_gold_return_rows_read",
    ):
        _service(path, sha256)


def test_artifact_rejects_distance_scale_and_pairing_inconsistency(
    tmp_path: Path,
) -> None:
    path = tmp_path / "contract.json"
    artifact = _artifact()
    artifact["distance_contract"]["normalization"]["scale"][3] = 3.0
    sha256 = _write_artifact(path, artifact=artifact)
    with pytest.raises(
        CoverageTupleStartReachabilityContractError,
        match="distance_scale",
    ):
        _service(path, sha256)

    artifact = _artifact()
    artifact["records"][0]["paired_return_exemplar_id"] = "episode_159"
    sha256 = _write_artifact(path, artifact=artifact)
    with pytest.raises(
        CoverageTupleStartReachabilityContractError,
        match="paired_return_identity",
    ):
        _service(path, sha256)
