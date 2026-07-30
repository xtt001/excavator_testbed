"""Fail-closed exact-tuple start reachability and return-target contract."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import numpy as np

STRICT_TRAIN_COVERAGE_RETURN_TRANSITION_LIBRARY_SCHEMA = (
    "strict_train_coverage_return_transition_library_v1"
)
STRICT_TRAIN_RETURN_START_REACHABILITY_PROFILE = (
    "strict_train_return_start_reachability_11d_v1"
)
RETURN_START_FACTS_SCHEMA = "return_start_facts_11d_v1"
RETURN_START_FACT_DIM = 11
RETURN_START_ENVELOPE_TOKEN_SCHEMA = "return_start_envelope_tokens_v1"
RETURN_START_ENVELOPE_TOKEN_DIM = 18

TUPLE_START_MAPPING_MISSING = "tuple_start_mapping_missing"
TUPLE_START_RAW_FIELDS_SHA_DRIFT = "tuple_start_raw_fields_sha_drift"
TUPLE_START_NOT_POST_RETURN_ELIGIBLE = (
    "tuple_start_not_post_return_eligible"
)
TUPLE_START_NOT_CYCLE0_ELIGIBLE = "tuple_start_not_cycle0_eligible"
TUPLE_START_FACTS_INVALID = "tuple_start_facts_invalid"
TUPLE_START_OUT_OF_SUPPORT = "tuple_start_out_of_support"
TUPLE_START_PHASE_INVALID = "tuple_start_phase_invalid"

_STRICT_TRAIN_SOURCE_EPISODE_IDS = (
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
)
_VALIDATION_SOURCE_EPISODE_IDS = (33, 34)
_SELECTION_PHASES = frozenset({"cycle0", "post_return"})
_RETURN_START_FACT_ORDER = (
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
)


class CoverageTupleStartReachabilityContractError(ValueError):
    """A configured transition companion cannot be trusted."""


@dataclass(frozen=True)
class CoverageTupleStartReachabilityConfig:
    """Identity lock for the tuple/return companion artifact."""

    enabled: bool = False
    profile: str = STRICT_TRAIN_RETURN_START_REACHABILITY_PROFILE
    artifact_path: str = ""
    artifact_sha256: str = ""
    execution_library_sha256: str = ""
    missing_contract: str = "fail_closed"

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, Any] | None,
    ) -> CoverageTupleStartReachabilityConfig:
        mapping = dict(values or {})
        config = cls(
            enabled=bool(mapping.get("enabled", False)),
            profile=str(
                mapping.get(
                    "profile",
                    STRICT_TRAIN_RETURN_START_REACHABILITY_PROFILE,
                )
            ).strip(),
            artifact_path=str(mapping.get("artifact_path", "")).strip(),
            artifact_sha256=str(
                mapping.get("artifact_sha256", "")
            ).strip().lower(),
            execution_library_sha256=str(
                mapping.get("execution_library_sha256", "")
            ).strip().lower(),
            missing_contract=str(
                mapping.get("missing_contract", "fail_closed")
            ).strip(),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if self.missing_contract != "fail_closed":
            raise ValueError(
                "tuple start reachability missing_contract must be "
                "'fail_closed'"
            )
        if not self.enabled:
            return
        if self.profile != STRICT_TRAIN_RETURN_START_REACHABILITY_PROFILE:
            raise ValueError(
                "tuple start reachability profile must be "
                f"{STRICT_TRAIN_RETURN_START_REACHABILITY_PROFILE!r}"
            )
        if not self.artifact_path:
            raise ValueError(
                "tuple start reachability enabled=true requires artifact_path"
            )
        _validate_sha256(
            self.artifact_sha256,
            label="start_reachability.artifact_sha256",
        )
        _validate_sha256(
            self.execution_library_sha256,
            label="start_reachability.execution_library_sha256",
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.enabled),
            "profile": str(self.profile),
            "artifact_path": str(self.artifact_path),
            "artifact_sha256": str(self.artifact_sha256),
            "execution_library_sha256": str(
                self.execution_library_sha256
            ),
            "missing_contract": str(self.missing_contract),
        }


@dataclass(frozen=True)
class CoverageTupleStartReachabilityEvaluation:
    """Immutable exact-tuple reachability decision and return contract."""

    profile: str
    eligible: bool
    rejection_reason: str
    selection_phase: str
    exemplar_id: str
    raw_fields_sha256: str
    artifact_sha256: str
    source_episode_id: int = -1
    source_cycle_id: int = -1
    cycle0_eligible: bool = False
    post_return_eligible: bool = False
    paired_return_primitive_episode_id: int = -1
    paired_return_exemplar_id: str = ""
    paired_return_source_cycle_id: int = -1
    live_return_start_facts: tuple[float, ...] = ()
    reference_return_start_facts: tuple[float, ...] = ()
    normalized_abs_delta: tuple[float, ...] = ()
    rms_distance: float = -1.0
    linf_distance: float = -1.0
    rms_threshold: float = -1.0
    linf_threshold: float = -1.0
    exact_return_start_envelope_tokens: tuple[float, ...] = ()
    exact_return_start_envelope_valid_mask: tuple[int, ...] = ()
    paired_handoff_facts: tuple[float, ...] = ()
    expert_dig_start_facts: tuple[float, ...] = ()
    dig_source_sha256: str = ""
    paired_return_source_sha256: str = ""

    @property
    def paired_handoff_qpos(self) -> tuple[float, ...]:
        if len(self.paired_handoff_facts) != RETURN_START_FACT_DIM:
            return ()
        return tuple(self.paired_handoff_facts[:4])

    def as_trace_fields(self) -> dict[str, Any]:
        return {
            "tuple_start_reachability_profile": str(self.profile),
            "tuple_start_reachability_eligible": int(self.eligible),
            "tuple_start_reachability_rejection_reason": str(
                self.rejection_reason
            ),
            "tuple_start_reachability_selection_phase": str(
                self.selection_phase
            ),
            "tuple_start_reachability_artifact_sha256": str(
                self.artifact_sha256
            ),
            "tuple_start_exemplar_id": str(self.exemplar_id),
            "tuple_start_raw_fields_sha256": str(
                self.raw_fields_sha256
            ),
            "tuple_start_source_episode_id": int(self.source_episode_id),
            "tuple_start_source_cycle_id": int(self.source_cycle_id),
            "tuple_start_cycle0_eligible": int(self.cycle0_eligible),
            "tuple_start_post_return_eligible": int(
                self.post_return_eligible
            ),
            "tuple_start_paired_return_id": int(
                self.paired_return_primitive_episode_id
            ),
            "tuple_start_paired_return_exemplar_id": str(
                self.paired_return_exemplar_id
            ),
            "tuple_start_paired_return_source_cycle_id": int(
                self.paired_return_source_cycle_id
            ),
            "tuple_start_live_return_start_facts_11d": list(
                self.live_return_start_facts
            ),
            "tuple_start_reference_return_start_facts_11d": list(
                self.reference_return_start_facts
            ),
            "tuple_start_normalized_abs_delta_11d": list(
                self.normalized_abs_delta
            ),
            "tuple_start_rms_distance": float(self.rms_distance),
            "tuple_start_linf_distance": float(self.linf_distance),
            "tuple_start_rms_threshold": float(self.rms_threshold),
            "tuple_start_linf_threshold": float(self.linf_threshold),
            "tuple_start_exact_return_envelope_tokens_v1": list(
                self.exact_return_start_envelope_tokens
            ),
            "tuple_start_exact_return_envelope_valid_mask": list(
                self.exact_return_start_envelope_valid_mask
            ),
            "tuple_start_paired_handoff_facts_11d": list(
                self.paired_handoff_facts
            ),
            "tuple_start_paired_handoff_qpos": list(
                self.paired_handoff_qpos
            ),
            "tuple_start_expert_dig_start_facts_11d": list(
                self.expert_dig_start_facts
            ),
            "tuple_start_dig_source_sha256": str(
                self.dig_source_sha256
            ),
            "tuple_start_paired_return_source_sha256": str(
                self.paired_return_source_sha256
            ),
        }


@dataclass(frozen=True)
class _TransitionRecord:
    exemplar_id: str
    raw_fields_sha256: str
    source_episode_id: int
    source_cycle_id: int
    cycle0_eligible: bool
    post_return_eligible: bool
    ineligible_reason: str
    paired_return_primitive_episode_id: int
    paired_return_exemplar_id: str
    paired_return_source_cycle_id: int
    return_start_facts: tuple[float, ...]
    exact_return_start_envelope_tokens: tuple[float, ...]
    exact_return_start_envelope_valid_mask: tuple[int, ...]
    expert_return_handoff_facts: tuple[float, ...]
    expert_dig_start_facts: tuple[float, ...]
    dig_source_sha256: str
    paired_return_source_sha256: str


@dataclass(frozen=True)
class CoverageTupleStartReachabilityService:
    """Evaluate whether a live return start supports one exact tuple."""

    config: CoverageTupleStartReachabilityConfig
    feature_scale: tuple[float, ...]
    rms_threshold: float
    linf_threshold: float
    records: MappingProxyType[str, _TransitionRecord]

    @classmethod
    def from_config(
        cls,
        config: CoverageTupleStartReachabilityConfig,
    ) -> CoverageTupleStartReachabilityService:
        if not config.enabled:
            raise CoverageTupleStartReachabilityContractError(
                "tuple_start_reachability_runtime_disabled"
            )
        path = Path(config.artifact_path).expanduser().resolve()
        if not path.is_file():
            raise CoverageTupleStartReachabilityContractError(
                f"tuple_start_reachability_artifact_missing:{path}"
            )
        payload = path.read_bytes()
        actual_sha256 = hashlib.sha256(payload).hexdigest()
        if actual_sha256 != config.artifact_sha256:
            raise CoverageTupleStartReachabilityContractError(
                "tuple_start_reachability_artifact_sha256_mismatch:"
                f"expected={config.artifact_sha256}:actual={actual_sha256}"
            )
        try:
            artifact = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise CoverageTupleStartReachabilityContractError(
                f"tuple_start_reachability_json:{exc}"
            ) from exc
        scale, rms_threshold, linf_threshold, records = _parse_artifact(
            artifact,
            config=config,
        )
        return cls(
            config=config,
            feature_scale=scale,
            rms_threshold=rms_threshold,
            linf_threshold=linf_threshold,
            records=MappingProxyType(records),
        )

    def evaluate(
        self,
        *,
        exemplar_id: str,
        raw_fields_sha256: str,
        live_return_start_facts: Any,
        selection_phase: str = "post_return",
    ) -> CoverageTupleStartReachabilityEvaluation:
        exemplar = str(exemplar_id)
        raw_sha = str(raw_fields_sha256).strip().lower()
        phase = str(selection_phase).strip()
        record = self.records.get(exemplar)
        if record is None:
            return self._invalid(
                exemplar_id=exemplar,
                raw_fields_sha256=raw_sha,
                selection_phase=phase,
                rejection_reason=TUPLE_START_MAPPING_MISSING,
            )
        if record.raw_fields_sha256 != raw_sha:
            return self._invalid(
                exemplar_id=exemplar,
                raw_fields_sha256=raw_sha,
                selection_phase=phase,
                rejection_reason=TUPLE_START_RAW_FIELDS_SHA_DRIFT,
            )
        if phase not in _SELECTION_PHASES:
            return self._from_record(
                record=record,
                raw_fields_sha256=raw_sha,
                selection_phase=phase,
                eligible=False,
                rejection_reason=TUPLE_START_PHASE_INVALID,
            )
        if phase == "cycle0":
            return self._from_record(
                record=record,
                raw_fields_sha256=raw_sha,
                selection_phase=phase,
                eligible=bool(record.cycle0_eligible),
                rejection_reason=(
                    ""
                    if record.cycle0_eligible
                    else TUPLE_START_NOT_CYCLE0_ELIGIBLE
                ),
            )
        if not record.post_return_eligible:
            return self._from_record(
                record=record,
                raw_fields_sha256=raw_sha,
                selection_phase=phase,
                eligible=False,
                rejection_reason=TUPLE_START_NOT_POST_RETURN_ELIGIBLE,
            )
        live_facts = _validated_live_facts(live_return_start_facts)
        if live_facts is None:
            return self._from_record(
                record=record,
                raw_fields_sha256=raw_sha,
                selection_phase=phase,
                eligible=False,
                rejection_reason=TUPLE_START_FACTS_INVALID,
            )

        live = np.asarray(live_facts, dtype=np.float64)
        reference = np.asarray(
            record.return_start_facts,
            dtype=np.float64,
        )
        scale = np.asarray(self.feature_scale, dtype=np.float64)
        normalized = np.abs(live - reference) / scale
        rms = float(np.sqrt(np.mean(np.square(normalized))))
        linf = float(np.max(normalized))
        eligible = bool(
            rms <= self.rms_threshold + 1.0e-12
            and linf <= self.linf_threshold + 1.0e-12
        )
        return self._from_record(
            record=record,
            raw_fields_sha256=raw_sha,
            selection_phase=phase,
            eligible=eligible,
            rejection_reason="" if eligible else TUPLE_START_OUT_OF_SUPPORT,
            live_facts=live_facts,
            normalized_abs_delta=tuple(float(item) for item in normalized),
            rms_distance=rms,
            linf_distance=linf,
        )

    def _invalid(
        self,
        *,
        exemplar_id: str,
        raw_fields_sha256: str,
        selection_phase: str,
        rejection_reason: str,
    ) -> CoverageTupleStartReachabilityEvaluation:
        return CoverageTupleStartReachabilityEvaluation(
            profile=str(self.config.profile),
            eligible=False,
            rejection_reason=str(rejection_reason),
            selection_phase=str(selection_phase),
            exemplar_id=str(exemplar_id),
            raw_fields_sha256=str(raw_fields_sha256),
            artifact_sha256=str(self.config.artifact_sha256),
            rms_threshold=float(self.rms_threshold),
            linf_threshold=float(self.linf_threshold),
        )

    def _from_record(
        self,
        *,
        record: _TransitionRecord,
        raw_fields_sha256: str,
        selection_phase: str,
        eligible: bool,
        rejection_reason: str,
        live_facts: tuple[float, ...] = (),
        normalized_abs_delta: tuple[float, ...] = (),
        rms_distance: float = -1.0,
        linf_distance: float = -1.0,
    ) -> CoverageTupleStartReachabilityEvaluation:
        return CoverageTupleStartReachabilityEvaluation(
            profile=str(self.config.profile),
            eligible=bool(eligible),
            rejection_reason=str(rejection_reason),
            selection_phase=str(selection_phase),
            exemplar_id=str(record.exemplar_id),
            raw_fields_sha256=str(raw_fields_sha256),
            artifact_sha256=str(self.config.artifact_sha256),
            source_episode_id=int(record.source_episode_id),
            source_cycle_id=int(record.source_cycle_id),
            cycle0_eligible=bool(record.cycle0_eligible),
            post_return_eligible=bool(record.post_return_eligible),
            paired_return_primitive_episode_id=int(
                record.paired_return_primitive_episode_id
            ),
            paired_return_exemplar_id=str(
                record.paired_return_exemplar_id
            ),
            paired_return_source_cycle_id=int(
                record.paired_return_source_cycle_id
            ),
            live_return_start_facts=tuple(live_facts),
            reference_return_start_facts=tuple(
                record.return_start_facts
            ),
            normalized_abs_delta=tuple(normalized_abs_delta),
            rms_distance=float(rms_distance),
            linf_distance=float(linf_distance),
            rms_threshold=float(self.rms_threshold),
            linf_threshold=float(self.linf_threshold),
            exact_return_start_envelope_tokens=tuple(
                record.exact_return_start_envelope_tokens
            ),
            exact_return_start_envelope_valid_mask=tuple(
                record.exact_return_start_envelope_valid_mask
            ),
            paired_handoff_facts=tuple(
                record.expert_return_handoff_facts
            ),
            expert_dig_start_facts=tuple(record.expert_dig_start_facts),
            dig_source_sha256=str(record.dig_source_sha256),
            paired_return_source_sha256=str(
                record.paired_return_source_sha256
            ),
        )


def _parse_artifact(
    value: Any,
    *,
    config: CoverageTupleStartReachabilityConfig,
) -> tuple[
    tuple[float, ...],
    float,
    float,
    dict[str, _TransitionRecord],
]:
    root = _mapping(
        value,
        label="tuple_start_reachability_root",
    )
    if (
        str(root.get("schema", ""))
        != STRICT_TRAIN_COVERAGE_RETURN_TRANSITION_LIBRARY_SCHEMA
        or str(root.get("status", "")) != "completed"
    ):
        _fail("tuple_start_reachability_schema_status_profile")

    _validate_source_lock(root.get("source_lock"), config=config)
    _validate_source_lineage(root.get("source_lineage"))
    _validate_source_contract(root.get("source_contract"))
    _validate_feature_contract(root.get("feature_contract"))
    scale, rms_threshold, linf_threshold = _parse_distance_contract(
        root.get("distance_contract"),
        profile=config.profile,
    )

    records_value = root.get("records")
    if not _is_sequence(records_value):
        _fail("tuple_start_reachability_records_missing")
    records: dict[str, _TransitionRecord] = {}
    paired_count = 0
    for raw_record in records_value:
        record = _parse_record(raw_record)
        if record.exemplar_id in records:
            _fail(
                "tuple_start_reachability_duplicate:"
                f"{record.exemplar_id}"
            )
        records[record.exemplar_id] = record
        paired_count += int(record.post_return_eligible)

    if int(root.get("coverage_tuple_sample_count", -1)) != len(records):
        _fail("tuple_start_reachability_sample_count")
    if int(root.get("gold_return_sample_count", -1)) != 358:
        _fail("tuple_start_reachability_gold_return_sample_count")
    if int(root.get("paired_post_return_tuple_count", -1)) != paired_count:
        _fail("tuple_start_reachability_paired_count")
    if (
        int(root.get("post_return_ineligible_tuple_count", -1))
        != len(records) - paired_count
    ):
        _fail("tuple_start_reachability_ineligible_count")
    return scale, rms_threshold, linf_threshold, records


def _validate_source_lock(
    value: Any,
    *,
    config: CoverageTupleStartReachabilityConfig,
) -> None:
    lock = _mapping(value, label="tuple_start_reachability_source_lock")
    execution_sha = _validate_sha256(
        lock.get("execution_library_sha256"),
        label="source_lock.execution_library_sha256",
        error_type=CoverageTupleStartReachabilityContractError,
    )
    if execution_sha != config.execution_library_sha256:
        _fail("tuple_start_reachability_execution_library_sha_drift")
    for required in (
        "dig_source_split_sha256",
        "return_source_split_sha256",
        "input_sha256",
    ):
        _validate_sha256(
            lock.get(required),
            label=f"source_lock.{required}",
            error_type=CoverageTupleStartReachabilityContractError,
        )
    for key, raw_digest in lock.items():
        if str(key).endswith("_sha256"):
            _validate_sha256(
                raw_digest,
                label=f"source_lock.{key}",
                error_type=CoverageTupleStartReachabilityContractError,
            )


def _validate_source_lineage(value: Any) -> None:
    lineage = _mapping(
        value,
        label="tuple_start_reachability_source_lineage",
    )
    if str(lineage.get("partition", "")) != "train":
        _fail("tuple_start_reachability_partition")
    if (
        tuple(int(item) for item in lineage.get(
            "train_source_episode_ids",
            (),
        ))
        != _STRICT_TRAIN_SOURCE_EPISODE_IDS
    ):
        _fail("tuple_start_reachability_strict_train_allowlist")
    if (
        tuple(int(item) for item in lineage.get(
            "validation_source_episode_ids",
            (),
        ))
        != _VALIDATION_SOURCE_EPISODE_IDS
    ):
        _fail("tuple_start_reachability_validation_allowlist")
    if int(lineage.get("validation_rows_read", -1)) != 0:
        _fail("tuple_start_reachability_validation_rows_read")
    if int(lineage.get("non_gold_return_rows_read", -1)) != 0:
        _fail("tuple_start_reachability_non_gold_return_rows_read")
    if bool(
        lineage.get(
            "partial_layered_salvage_input_views_allowed",
            True,
        )
    ):
        _fail("tuple_start_reachability_partial_layered_salvage")


def _validate_source_contract(value: Any) -> None:
    contract = _mapping(
        value,
        label="tuple_start_reachability_source_contract",
    )
    expected = {
        "primitive_name": "return",
        "training_tier": "gold",
        "primitive_storage_mode": "copy",
        "return_start_envelope_schema": (
            RETURN_START_ENVELOPE_TOKEN_SCHEMA
        ),
        "return_start_envelope_token_dim": (
            RETURN_START_ENVELOPE_TOKEN_DIM
        ),
        "return_start_facts_schema": RETURN_START_FACTS_SCHEMA,
        "return_start_facts_dim": RETURN_START_FACT_DIM,
    }
    for key, expected_value in expected.items():
        if contract.get(key) != expected_value:
            _fail(f"tuple_start_reachability_source_contract:{key}")


def _validate_feature_contract(value: Any) -> None:
    contract = _mapping(
        value,
        label="tuple_start_reachability_feature_contract",
    )
    if (
        str(contract.get("schema", "")) != RETURN_START_FACTS_SCHEMA
        or int(contract.get("dim", -1)) != RETURN_START_FACT_DIM
        or tuple(contract.get("order", ())) != _RETURN_START_FACT_ORDER
    ):
        _fail("tuple_start_reachability_feature_contract")


def _parse_distance_contract(
    value: Any,
    *,
    profile: str,
) -> tuple[tuple[float, ...], float, float]:
    contract = _mapping(
        value,
        label="tuple_start_reachability_distance_contract",
    )
    if (
        str(contract.get("profile", "")) != profile
        or int(contract.get("calibration_sample_count", -1)) != 358
        or str(contract.get("calibration_partition", ""))
        != "strict_train_gold_return_only"
        or str(contract.get("feature_schema", ""))
        != RETURN_START_FACTS_SCHEMA
        or tuple(contract.get("feature_order", ()))
        != _RETURN_START_FACT_ORDER
        or str(contract.get("runtime_reference", ""))
        != "selected_tuple.return_start_facts_11d"
        or str(contract.get("acceptance", ""))
        != "rms_pass AND linf_pass"
        or str(contract.get("missing_or_nonfinite", "")) != "fail_closed"
    ):
        _fail("tuple_start_reachability_distance_profile")
    normalization = _mapping(
        contract.get("normalization"),
        label="tuple_start_reachability_normalization",
    )
    if (
        str(normalization.get("method", "")) != "p01_p99_range"
        or str(normalization.get("formula", ""))
        != "(query-reference)/(p99-p01)"
        or str(normalization.get("zero_scale_policy", "")) != "error"
    ):
        _fail("tuple_start_reachability_distance_normalization")
    p01 = _finite_tuple(
        normalization.get("p01", ()),
        expected=RETURN_START_FACT_DIM,
    )
    p99 = _finite_tuple(
        normalization.get("p99", ()),
        expected=RETURN_START_FACT_DIM,
    )
    scale = _finite_tuple(
        normalization.get("scale", ()),
        expected=RETURN_START_FACT_DIM,
    )
    expected_scale = tuple(
        float(upper - lower) for lower, upper in zip(p01, p99)
    )
    if any(item <= 0.0 for item in expected_scale) or not np.allclose(
        np.asarray(scale, dtype=np.float64),
        np.asarray(expected_scale, dtype=np.float64),
        rtol=1.0e-9,
        atol=1.0e-12,
    ):
        _fail("tuple_start_reachability_distance_scale")
    metrics = _mapping(
        contract.get("metrics"),
        label="tuple_start_reachability_distance_metrics",
    )
    if set(metrics) != {"rms", "linf"}:
        _fail("tuple_start_reachability_distance_metrics")
    rms_metric = _mapping(
        metrics.get("rms"),
        label="tuple_start_reachability_rms_metric",
    )
    linf_metric = _mapping(
        metrics.get("linf"),
        label="tuple_start_reachability_linf_metric",
    )
    if (
        str(rms_metric.get("formula", ""))
        != "sqrt(mean(normalized_delta**2))"
        or str(linf_metric.get("formula", ""))
        != "max(abs(normalized_delta))"
        or str(rms_metric.get("nearest_neighbor_selection", ""))
        != "independent_leave_one_out"
        or str(linf_metric.get("nearest_neighbor_selection", ""))
        != "independent_leave_one_out"
    ):
        _fail("tuple_start_reachability_distance_metrics")
    rms_threshold = _positive_finite(
        rms_metric.get("loo_p99_threshold"),
        label="rms_threshold",
    )
    linf_threshold = _positive_finite(
        linf_metric.get("loo_p99_threshold"),
        label="linf_threshold",
    )
    return scale, rms_threshold, linf_threshold


def _parse_record(value: Any) -> _TransitionRecord:
    record = _mapping(
        value,
        label="tuple_start_reachability_record",
    )
    primitive_episode_id = int(record.get("primitive_episode_id", -1))
    exemplar_id = str(record.get("exemplar_id", ""))
    if (
        primitive_episode_id < 0
        or exemplar_id != f"episode_{primitive_episode_id}"
    ):
        _fail("tuple_start_reachability_exemplar_identity")
    source_episode_id = int(record.get("source_episode_id", -1))
    if source_episode_id not in _STRICT_TRAIN_SOURCE_EPISODE_IDS:
        _fail("tuple_start_reachability_record_source_episode")
    source_cycle_id = int(record.get("source_cycle_id", -1))
    if source_cycle_id < 0:
        _fail("tuple_start_reachability_source_cycle_id")
    raw_fields_sha256 = _validate_sha256(
        record.get("raw_fields_sha256"),
        label="record.raw_fields_sha256",
        error_type=CoverageTupleStartReachabilityContractError,
    )
    dig_source_sha256 = _validate_sha256(
        record.get("dig_source_sha256"),
        label="record.dig_source_sha256",
        error_type=CoverageTupleStartReachabilityContractError,
    )
    expert_dig_start_facts = _finite_tuple(
        record.get("expert_dig_start_facts_11d", ()),
        expected=RETURN_START_FACT_DIM,
    )

    eligibility = _mapping(
        record.get("eligibility"),
        label="tuple_start_reachability_eligibility",
    )
    cycle0_eligible = _strict_bool(
        eligibility.get("cycle0"),
        label="eligibility.cycle0",
    )
    post_return_eligible = _strict_bool(
        eligibility.get("post_return"),
        label="eligibility.post_return",
    )
    ineligible_reason = str(eligibility.get("reason", "")).strip()
    if not cycle0_eligible:
        _fail("tuple_start_reachability_cycle0_contract")
    if (
        post_return_eligible
        and ineligible_reason != "gold_return_transition_pair"
    ) or (
        not post_return_eligible
        and ineligible_reason
        not in {
            "episode_first_no_preceding_return",
            "non_gold_return_pair_excluded",
        }
    ):
        _fail("tuple_start_reachability_eligibility_reason")

    if post_return_eligible:
        paired_id = int(
            record.get("paired_return_primitive_episode_id", -1)
        )
        paired_exemplar = str(
            record.get("paired_return_exemplar_id", "")
        )
        if paired_id < 0 or paired_exemplar != f"episode_{paired_id}":
            _fail("tuple_start_reachability_paired_return_identity")
        paired_source_cycle = int(
            record.get("paired_return_source_cycle_id", -1)
        )
        if paired_source_cycle < 0:
            _fail("tuple_start_reachability_paired_source_cycle")
        return_start_facts = _finite_tuple(
            record.get("return_start_facts_11d", ()),
            expected=RETURN_START_FACT_DIM,
        )
        exact_tokens = _finite_tuple(
            record.get("exact_return_start_envelope_tokens_v1", ()),
            expected=RETURN_START_ENVELOPE_TOKEN_DIM,
        )
        valid_mask = _binary_mask(
            record.get("exact_return_start_envelope_valid_mask"),
            expected=RETURN_START_ENVELOPE_TOKEN_DIM,
        )
        handoff_facts = _finite_tuple(
            record.get("expert_return_handoff_facts_11d", ()),
            expected=RETURN_START_FACT_DIM,
        )
        paired_source_sha256 = _validate_sha256(
            record.get("paired_return_source_sha256"),
            label="record.paired_return_source_sha256",
            error_type=CoverageTupleStartReachabilityContractError,
        )
    else:
        paired_id = -1
        paired_exemplar = ""
        paired_source_cycle = -1
        return_start_facts = ()
        exact_tokens = ()
        valid_mask = ()
        handoff_facts = ()
        paired_source_sha256 = ""
        null_fields = (
            "paired_return_primitive_episode_id",
            "paired_return_exemplar_id",
            "paired_return_source_cycle_id",
            "return_start_facts_11d",
            "exact_return_start_envelope_tokens_v1",
            "exact_return_start_envelope_valid_mask",
            "expert_return_handoff_facts_11d",
            "paired_return_source_sha256",
        )
        if any(record.get(key) is not None for key in null_fields):
            _fail("tuple_start_reachability_unpaired_fields")

    return _TransitionRecord(
        exemplar_id=exemplar_id,
        raw_fields_sha256=raw_fields_sha256,
        source_episode_id=source_episode_id,
        source_cycle_id=source_cycle_id,
        cycle0_eligible=cycle0_eligible,
        post_return_eligible=post_return_eligible,
        ineligible_reason=ineligible_reason,
        paired_return_primitive_episode_id=paired_id,
        paired_return_exemplar_id=paired_exemplar,
        paired_return_source_cycle_id=paired_source_cycle,
        return_start_facts=return_start_facts,
        exact_return_start_envelope_tokens=exact_tokens,
        exact_return_start_envelope_valid_mask=valid_mask,
        expert_return_handoff_facts=handoff_facts,
        expert_dig_start_facts=expert_dig_start_facts,
        dig_source_sha256=dig_source_sha256,
        paired_return_source_sha256=paired_source_sha256,
    )


def _validated_live_facts(value: Any) -> tuple[float, ...] | None:
    try:
        return _finite_tuple(value, expected=RETURN_START_FACT_DIM)
    except (TypeError, ValueError):
        return None


def _finite_tuple(value: Any, *, expected: int) -> tuple[float, ...]:
    if isinstance(value, (str, bytes, Mapping)):
        raise TypeError("value must be a numeric sequence")
    try:
        result = tuple(float(item) for item in value)
    except TypeError as exc:
        raise TypeError("value must be a numeric sequence") from exc
    if len(result) != expected or not all(
        math.isfinite(item) for item in result
    ):
        raise ValueError(
            f"expected {expected} finite values, got {result!r}"
        )
    return result


def _binary_mask(value: Any, *, expected: int) -> tuple[int, ...]:
    if not _is_sequence(value):
        _fail("tuple_start_reachability_valid_mask")
    result = tuple(int(item) for item in value)
    if (
        len(result) != expected
        or any(item not in (0, 1) for item in result)
        or any(float(raw) != float(parsed) for raw, parsed in zip(value, result))
    ):
        _fail("tuple_start_reachability_valid_mask")
    return result


def _strict_bool(value: Any, *, label: str) -> bool:
    if not isinstance(value, bool):
        _fail(f"tuple_start_reachability_bool:{label}")
    return bool(value)


def _positive_finite(value: Any, *, label: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        _fail(f"tuple_start_reachability_{label}")
    return result


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(f"{label}_not_mapping")
    return value


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes),
    )


def _validate_sha256(
    value: Any,
    *,
    label: str,
    error_type: type[Exception] = ValueError,
) -> str:
    digest = str(value or "").strip().lower()
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise error_type(f"{label} must be a lowercase SHA256")
    return digest


def _fail(reason: str) -> None:
    raise CoverageTupleStartReachabilityContractError(str(reason))


__all__ = [
    "RETURN_START_ENVELOPE_TOKEN_DIM", "RETURN_START_ENVELOPE_TOKEN_SCHEMA",
    "RETURN_START_FACTS_SCHEMA", "RETURN_START_FACT_DIM",
    "STRICT_TRAIN_COVERAGE_RETURN_TRANSITION_LIBRARY_SCHEMA",
    "STRICT_TRAIN_RETURN_START_REACHABILITY_PROFILE",
    "TUPLE_START_FACTS_INVALID", "TUPLE_START_MAPPING_MISSING",
    "TUPLE_START_NOT_CYCLE0_ELIGIBLE", "TUPLE_START_NOT_POST_RETURN_ELIGIBLE",
    "TUPLE_START_OUT_OF_SUPPORT", "TUPLE_START_PHASE_INVALID",
    "TUPLE_START_RAW_FIELDS_SHA_DRIFT", "CoverageTupleStartReachabilityConfig",
    "CoverageTupleStartReachabilityContractError",
    "CoverageTupleStartReachabilityEvaluation", "CoverageTupleStartReachabilityService",
]
