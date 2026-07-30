"""Parse and validate immutable strict-train coverage execution libraries."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

import numpy as np

from testbed.data.operator_first_v2_2 import (
    DIG_CUT_DEPTH_SCALE_M,
    DIG_CUT_LENGTH_SCALE_M,
    DIG_CUT_PAYLOAD_SCALE_KG,
    DIG_CUT_POSITION_SCALE_M,
    DIG_CUT_TOKEN_DIM,
)
from testbed.data.schema import ENV_STATE_CONTRACT_VERSION_V2_4
from testbed.planner.primitive.coverage.wall_safety import (
    CoverageWallSafetyConfig,
)

COVERAGE_EXECUTION_CANDIDATE_LIBRARY_SCHEMA = (
    "strict_train_coverage_execution_library_v1_1"
)
COVERAGE_EXECUTION_CORRIDOR_ID_BASE = 1_000_000
COVERAGE_GRID_CELL_COUNT = 6
_TUPLE_CONSISTENCY_TOLERANCE_M = 1.0e-3
_FLOAT_TOLERANCE = 2.0e-6
_RAW_FIELD_NAMES = (
    "operator_entry_x_m",
    "operator_entry_y_m",
    "operator_entry_z_m",
    "operator_exit_x_m",
    "operator_exit_y_m",
    "operator_exit_z_m",
    "operator_cut_direction_x",
    "operator_cut_direction_y",
    "operator_cut_direction_z",
    "operator_cut_length_m",
    "operator_cut_depth_peak_m",
    "operator_cut_payload_gain_kg",
    "operator_effective_deposit_delta_kg",
    "operator_cut_valid",
)


class CoverageExecutionCandidateContractError(ValueError):
    """Raised when a library or live-selection contract is malformed."""


@dataclass(frozen=True)
class CoverageCorridorPrototype:
    """One exact, immutable strict-train cut tuple."""

    corridor_id: int
    exemplar_id: str
    source_primitive_episode_id: int
    source_episode_id: int
    effect_outcome_cell_id: int
    return_envelope_cell_id: int
    raw_field_items: tuple[tuple[str, float | int], ...]
    dig_cut_tokens: tuple[float, ...]
    start_removed_depth_grid_m: tuple[float, ...]
    token_peak_local_index: int
    execution_tail_plane_depth_reserve_m: float
    loo_p99_distance: float
    source_sha256: str
    expected_centerline_physical_cell_ids: tuple[int, ...] = ()
    expected_swept_physical_cell_ids: tuple[int, ...] = ()

    @property
    def cell_id(self) -> int:
        """Read-only compatibility alias for the effect outcome label."""

        return int(self.effect_outcome_cell_id)

    @property
    def raw_fields(self) -> Mapping[str, float | int]:
        """Return an immutable view of the complete recorded raw tuple."""

        return MappingProxyType(dict(self.raw_field_items))

    @property
    def raw_fields_sha256(self) -> str:
        payload = json.dumps(
            dict(self.raw_field_items),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @property
    def token_depth_m(self) -> float:
        return float(self.dig_cut_tokens[7]) * DIG_CUT_DEPTH_SCALE_M


@dataclass(frozen=True)
class CoverageExecutionLibraryContract:
    """Validated execution-library facts consumed by online selection."""

    prototypes: tuple[CoverageCorridorPrototype, ...]
    removed_depth_scale_m: float
    target_cell_weight: float
    geometry_contract: tuple[int, int, int, float, float] | None


@dataclass(frozen=True)
class CoverageExecutionLibraryContractParser:
    """Own artifact-only parsing, lineage, and tuple consistency checks."""

    wall_safety_config: CoverageWallSafetyConfig

    def parse(
        self,
        library: Mapping[str, Any],
    ) -> CoverageExecutionLibraryContract:
        """Return a deep-frozen validated execution library."""

        if not isinstance(library, Mapping):
            raise_execution_contract_error("library_not_mapping")
        if (
            str(library.get("schema", ""))
            != COVERAGE_EXECUTION_CANDIDATE_LIBRARY_SCHEMA
        ):
            raise_execution_contract_error("library_schema")
        if str(library.get("status", "")) != "completed":
            raise_execution_contract_error("library_status")

        records_value = library.get("records")
        if records_value is None:
            records_value = library.get("corridors")
        if not _is_sequence(records_value) or not records_value:
            raise_execution_contract_error("library_records")

        for required_mapping in (
            "source_lock",
            "source_lineage",
            "tail_audit",
            "corridor_id_contract",
        ):
            if not isinstance(library.get(required_mapping), Mapping):
                raise_execution_contract_error(f"library_{required_mapping}")
        self._validate_source_lineage(library["source_lineage"])
        self._validate_corridor_id_contract(library["corridor_id_contract"])
        scale_m, target_weight = self._distance_contract(library)
        geometry_contract = self._optional_geometry_contract(library)

        prototypes = tuple(self._parse_prototype(record) for record in records_value)
        corridor_ids = [item.corridor_id for item in prototypes]
        exemplar_ids = [item.exemplar_id for item in prototypes]
        if len(set(corridor_ids)) != len(corridor_ids):
            raise_execution_contract_error("duplicate_corridor_id")
        if len(set(exemplar_ids)) != len(exemplar_ids):
            raise_execution_contract_error("duplicate_exemplar_id")
        validation_sources = {
            int(value)
            for value in library["source_lineage"].get(
                "validation_source_episode_ids",
                (),
            )
        }
        leaked = sorted(
            {
                item.source_episode_id
                for item in prototypes
                if item.source_episode_id in validation_sources
            }
        )
        if leaked:
            raise_execution_contract_error(f"validation_source_leak:{leaked}")
        p99_by_cell: dict[int, set[float]] = defaultdict(set)
        for prototype in prototypes:
            p99_by_cell[prototype.effect_outcome_cell_id].add(
                prototype.loo_p99_distance
            )
        if any(len(values) != 1 for values in p99_by_cell.values()):
            raise_execution_contract_error("outcome_cell_loo_p99_inconsistent")
        return CoverageExecutionLibraryContract(
            prototypes=prototypes,
            removed_depth_scale_m=scale_m,
            target_cell_weight=target_weight,
            geometry_contract=geometry_contract,
        )

    def _parse_prototype(self, value: Any) -> CoverageCorridorPrototype:
        if not isinstance(value, Mapping):
            raise_execution_contract_error("library_record_not_mapping")
        primitive_episode_id = _nonnegative_int(
            value.get(
                "primitive_episode_id",
                value.get("source_primitive_episode_id"),
            ),
            label="primitive_episode_id",
        )
        corridor_id = _nonnegative_int(
            value.get("corridor_id"),
            label="corridor_id",
        )
        expected_corridor_id = (
            COVERAGE_EXECUTION_CORRIDOR_ID_BASE + primitive_episode_id
        )
        if corridor_id != expected_corridor_id:
            raise_execution_contract_error(
                f"corridor_id_formula:{corridor_id}!={expected_corridor_id}"
            )
        exemplar_id = str(value.get("exemplar_id", ""))
        if exemplar_id != f"episode_{primitive_episode_id}":
            raise_execution_contract_error("exemplar_id_formula")
        source_episode_id = _nonnegative_int(
            value.get("source_episode_id"),
            label="source_episode_id",
        )
        outcome_cell_id = validate_cell_id(
            value.get("effect_outcome_cell_id"),
            label="effect_outcome_cell_id",
        )
        if (
            "cell_id" in value
            and validate_cell_id(
                value["cell_id"],
                label="legacy_cell_id",
            )
            != outcome_cell_id
        ):
            raise_execution_contract_error("legacy_cell_id_disagrees")
        return_envelope_cell_id = validate_cell_id(
            value.get("return_envelope_cell_id"),
            label="return_envelope_cell_id",
        )

        raw_value = value.get("raw_fields")
        if not isinstance(raw_value, Mapping):
            raise_execution_contract_error("raw_fields")
        if set(raw_value) != set(_RAW_FIELD_NAMES):
            raise_execution_contract_error("raw_fields_keys")
        raw_fields: dict[str, float | int] = {}
        for name in _RAW_FIELD_NAMES:
            number = finite_contract_float(
                raw_value[name],
                label=f"raw_fields.{name}",
            )
            raw_fields[name] = (
                int(round(number)) if name == "operator_cut_valid" else float(number)
            )
        if raw_fields["operator_cut_valid"] != 1:
            raise_execution_contract_error("operator_cut_valid")
        if float(raw_fields["operator_cut_length_m"]) <= 0.0:
            raise_execution_contract_error("operator_cut_length_non_positive")
        if float(raw_fields["operator_cut_depth_peak_m"]) < 0.0:
            raise_execution_contract_error("operator_cut_depth_negative")
        if float(raw_fields["operator_cut_payload_gain_kg"]) < 0.0:
            raise_execution_contract_error("operator_cut_payload_negative")
        if float(raw_fields["operator_effective_deposit_delta_kg"]) < 0.0:
            raise_execution_contract_error("operator_effect_negative")
        tuple_residual = _tuple_consistency_residual(raw_fields)
        if tuple_residual > _TUPLE_CONSISTENCY_TOLERANCE_M:
            raise_execution_contract_error(
                f"cut_direction_inconsistent:residual_m={tuple_residual}"
            )
        if "tuple_consistency_residual_m" in value:
            recorded_residual = finite_contract_float(
                value["tuple_consistency_residual_m"],
                label="tuple_consistency_residual_m",
            )
            if not math.isclose(
                recorded_residual,
                tuple_residual,
                rel_tol=0.0,
                abs_tol=2.0e-6,
            ):
                raise_execution_contract_error("tuple_consistency_residual_disagrees")

        tokens = _finite_tuple(
            value.get("dig_cut_tokens"),
            length=DIG_CUT_TOKEN_DIM,
            label="dig_cut_tokens",
        )
        expected_tokens = _tokens_from_raw_fields(raw_fields)
        if not np.allclose(
            np.asarray(tokens),
            np.asarray(expected_tokens),
            rtol=0.0,
            atol=_FLOAT_TOLERANCE,
        ):
            raise_execution_contract_error("dig_cut_tokens_disagree_with_raw_fields")
        start_removed = _finite_tuple(
            value.get("start_removed_depth_grid_m"),
            length=COVERAGE_GRID_CELL_COUNT,
            label="start_removed_depth_grid_m",
        )
        if any(number < 0.0 for number in start_removed):
            raise_execution_contract_error("start_removed_depth_grid_negative")
        token_peak_local_index = _nonnegative_int(
            value.get("token_peak_local_index"),
            label="token_peak_local_index",
        )
        tail_reserve = finite_contract_float(
            value.get("execution_tail_plane_depth_reserve_m"),
            label="execution_tail_plane_depth_reserve_m",
        )
        if tail_reserve < 0.0:
            raise_execution_contract_error(
                "execution_tail_plane_depth_reserve_negative"
            )
        loo_p99 = finite_contract_float(
            value.get("outcome_cell_loo_nearest_distance_p99"),
            label="outcome_cell_loo_nearest_distance_p99",
        )
        if loo_p99 < 0.0:
            raise_execution_contract_error("outcome_cell_loo_p99_negative")
        source_sha256 = str(value.get("source_sha256", "")).lower()
        if len(source_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in source_sha256
        ):
            raise_execution_contract_error("source_sha256")

        expected_centerline, expected_swept = self._physical_cells(value)
        return CoverageCorridorPrototype(
            corridor_id=corridor_id,
            exemplar_id=exemplar_id,
            source_primitive_episode_id=primitive_episode_id,
            source_episode_id=source_episode_id,
            effect_outcome_cell_id=outcome_cell_id,
            return_envelope_cell_id=return_envelope_cell_id,
            raw_field_items=tuple(
                (name, raw_fields[name]) for name in _RAW_FIELD_NAMES
            ),
            dig_cut_tokens=tokens,
            start_removed_depth_grid_m=start_removed,
            token_peak_local_index=token_peak_local_index,
            execution_tail_plane_depth_reserve_m=tail_reserve,
            loo_p99_distance=loo_p99,
            source_sha256=source_sha256,
            expected_centerline_physical_cell_ids=expected_centerline,
            expected_swept_physical_cell_ids=expected_swept,
        )

    def _physical_cells(
        self,
        value: Mapping[str, Any],
    ) -> tuple[tuple[int, ...], tuple[int, ...]]:
        center_key = "expected_centerline_physical_cell_ids"
        swept_key = "expected_swept_physical_cell_ids"
        if center_key not in value or swept_key not in value:
            missing = center_key if center_key not in value else swept_key
            raise_execution_contract_error(f"{missing}_missing")
        center = _physical_cell_tuple(value[center_key], label=center_key)
        swept = _physical_cell_tuple(value[swept_key], label=swept_key)
        if not center or not swept:
            raise_execution_contract_error("expected_physical_cell_fields_empty")
        if not set(center).issubset(swept):
            raise_execution_contract_error("expected_centerline_not_subset_of_swept")
        return center, swept

    def _distance_contract(
        self,
        library: Mapping[str, Any],
    ) -> tuple[float, float]:
        live_contract = library.get("live_selection_contract")
        if isinstance(live_contract, Mapping):
            if (
                str(live_contract.get("requires_env_state", ""))
                != ENV_STATE_CONTRACT_VERSION_V2_4
            ):
                raise_execution_contract_error("live_selection_env_state_contract")
            if (
                str(live_contract.get("geometry_profile", ""))
                != self.wall_safety_config.profile
            ):
                raise_execution_contract_error("live_selection_geometry_profile")
            worktool_width = finite_contract_float(
                live_contract.get("worktool_width_m"),
                label="live_selection_worktool_width_m",
            )
            if not math.isclose(
                worktool_width,
                float(self.wall_safety_config.worktool_width_m),
                rel_tol=0.0,
                abs_tol=1.0e-9,
            ):
                raise_execution_contract_error(
                    "live_selection_worktool_width_m_disagrees"
                )
            scale_m = finite_contract_float(
                live_contract.get("removed_depth_scale_m"),
                label="removed_depth_scale_m",
            )
            target_weight = finite_contract_float(
                live_contract.get("target_cell_weight"),
                label="target_cell_weight",
            )
        else:
            distance_contract = library.get("distance_contract")
            if not isinstance(distance_contract, Mapping):
                raise_execution_contract_error("library_live_selection_contract")
            scale_m = finite_contract_float(
                distance_contract.get("removed_depth_scale_m"),
                label="removed_depth_scale_m",
            )
            target_weight = finite_contract_float(
                distance_contract.get("target_cell_weight"),
                label="target_cell_weight",
            )
        if scale_m <= 0.0:
            raise_execution_contract_error("removed_depth_scale_non_positive")
        if target_weight < 0.0:
            raise_execution_contract_error("target_cell_weight_negative")
        return scale_m, target_weight

    def _optional_geometry_contract(
        self,
        library: Mapping[str, Any],
    ) -> tuple[int, int, int, float, float] | None:
        value = library.get("geometry_contract")
        if value is None:
            return None
        if not isinstance(value, Mapping):
            raise_execution_contract_error("geometry_contract")
        long_axis = validate_axis_id(value.get("long_axis"))
        long_count = validate_positive_int(
            value.get("grid_long_count"),
            label="grid_long_count",
        )
        short_count = validate_positive_int(
            value.get("grid_short_count"),
            label="grid_short_count",
        )
        if (long_count, short_count) != (3, 2):
            raise_execution_contract_error("geometry_grid_shape")
        long_size = finite_contract_float(
            value.get("cell_long_size_m"),
            label="cell_long_size_m",
        )
        short_size = finite_contract_float(
            value.get("cell_short_size_m"),
            label="cell_short_size_m",
        )
        if long_size <= 0.0 or short_size <= 0.0:
            raise_execution_contract_error("geometry_cell_size_non_positive")
        if "worktool_width_m" in value:
            width = finite_contract_float(
                value["worktool_width_m"],
                label="geometry_worktool_width_m",
            )
            if not math.isclose(
                width,
                float(self.wall_safety_config.worktool_width_m),
                rel_tol=0.0,
                abs_tol=1.0e-9,
            ):
                raise_execution_contract_error("geometry_worktool_width_m_disagrees")
        return long_axis, long_count, short_count, long_size, short_size

    @staticmethod
    def _validate_source_lineage(value: Mapping[str, Any]) -> None:
        if str(value.get("partition", "")) != "train":
            raise_execution_contract_error("source_lineage_partition")
        if int(value.get("validation_rows_read", 0)) != 0:
            raise_execution_contract_error("source_lineage_validation_rows_read")
        if bool(
            value.get(
                "partial_layered_salvage_input_views_allowed",
                False,
            )
        ):
            raise_execution_contract_error("source_lineage_partial_salvage_allowed")
        validation = value.get("validation_source_episode_ids", ())
        if not _is_sequence(validation):
            raise_execution_contract_error("validation_source_episode_ids")
        for item in validation:
            _nonnegative_int(item, label="validation_source_episode_id")

    @staticmethod
    def _validate_corridor_id_contract(value: Mapping[str, Any]) -> None:
        if (
            _nonnegative_int(
                value.get("base"),
                label="corridor_id_contract_base",
            )
            != COVERAGE_EXECUTION_CORRIDOR_ID_BASE
        ):
            raise_execution_contract_error("corridor_id_contract_base")
        if str(value.get("formula", "")) != "1000000 + primitive_episode_id":
            raise_execution_contract_error("corridor_id_contract_formula")
        legacy = value.get("legacy_outcome_cell_id_range")
        if not _is_sequence(legacy) or tuple(legacy) != (0, 5):
            raise_execution_contract_error("corridor_id_contract_legacy_range")


def _tuple_consistency_residual(
    raw_fields: Mapping[str, float | int],
) -> float:
    entry = np.asarray(
        [
            raw_fields["operator_entry_x_m"],
            raw_fields["operator_entry_y_m"],
            raw_fields["operator_entry_z_m"],
        ],
        dtype=np.float64,
    )
    exit_point = np.asarray(
        [
            raw_fields["operator_exit_x_m"],
            raw_fields["operator_exit_y_m"],
            raw_fields["operator_exit_z_m"],
        ],
        dtype=np.float64,
    )
    direction = np.asarray(
        [
            raw_fields["operator_cut_direction_x"],
            raw_fields["operator_cut_direction_y"],
            raw_fields["operator_cut_direction_z"],
        ],
        dtype=np.float64,
    )
    length_m = float(raw_fields["operator_cut_length_m"])
    return float(np.linalg.norm((exit_point - entry) - direction * length_m))


def _tokens_from_raw_fields(
    raw_fields: Mapping[str, float | int],
) -> tuple[float, ...]:
    def clipped(name: str, scale: float) -> float:
        return float(
            np.clip(
                float(raw_fields[name]) / float(scale),
                -1.0,
                1.0,
            )
        )

    return (
        clipped("operator_entry_x_m", DIG_CUT_POSITION_SCALE_M),
        clipped("operator_entry_z_m", DIG_CUT_POSITION_SCALE_M),
        clipped("operator_exit_x_m", DIG_CUT_POSITION_SCALE_M),
        clipped("operator_exit_z_m", DIG_CUT_POSITION_SCALE_M),
        float(raw_fields["operator_cut_direction_x"]),
        float(raw_fields["operator_cut_direction_z"]),
        clipped("operator_cut_length_m", DIG_CUT_LENGTH_SCALE_M),
        clipped("operator_cut_depth_peak_m", DIG_CUT_DEPTH_SCALE_M),
        clipped("operator_cut_payload_gain_kg", DIG_CUT_PAYLOAD_SCALE_KG),
        1.0,
    )


def _finite_tuple(
    value: Any,
    *,
    length: int,
    label: str,
) -> tuple[float, ...]:
    if not _is_sequence(value) or len(value) != length:
        raise_execution_contract_error(f"{label}_shape")
    return tuple(
        finite_contract_float(item, label=f"{label}[{index}]")
        for index, item in enumerate(value)
    )


def _physical_cell_tuple(value: Any, *, label: str) -> tuple[int, ...]:
    if not _is_sequence(value):
        raise_execution_contract_error(label)
    cells = tuple(validate_cell_id(item, label=label) for item in value)
    if cells != tuple(sorted(set(cells))):
        raise_execution_contract_error(f"{label}_order_or_duplicate")
    return cells


def validate_axis_id(value: Any) -> int:
    """Validate the 107D long-axis identity."""

    axis = _integer(value, label="long_axis")
    if axis not in {0, 2}:
        raise_execution_contract_error("long_axis")
    return axis


def validate_cell_id(value: Any, *, label: str) -> int:
    """Validate one physical or logical 3x2 cell identity."""

    cell_id = _integer(value, label=label)
    if cell_id < 0 or cell_id >= COVERAGE_GRID_CELL_COUNT:
        raise_execution_contract_error(f"{label}_range")
    return cell_id


def validate_positive_int(value: Any, *, label: str) -> int:
    """Validate a positive integer-valued contract field."""

    result = _integer(value, label=label)
    if result <= 0:
        raise_execution_contract_error(f"{label}_non_positive")
    return result


def _nonnegative_int(value: Any, *, label: str) -> int:
    result = _integer(value, label=label)
    if result < 0:
        raise_execution_contract_error(f"{label}_negative")
    return result


def _integer(value: Any, *, label: str) -> int:
    if isinstance(value, bool):
        raise_execution_contract_error(label)
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise_execution_contract_error(label)
    if not math.isfinite(number):
        raise_execution_contract_error(label)
    result = int(round(number))
    if not math.isclose(number, result, rel_tol=0.0, abs_tol=1.0e-6):
        raise_execution_contract_error(label)
    return result


def finite_contract_float(value: Any, *, label: str) -> float:
    """Validate a finite floating-point contract field."""

    try:
        result = float(value)
    except (TypeError, ValueError):
        raise_execution_contract_error(label)
    if not math.isfinite(result):
        raise_execution_contract_error(label)
    return result


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    )


def raise_execution_contract_error(reason: str) -> None:
    """Raise the shared execution-library contract error."""

    raise CoverageExecutionCandidateContractError(str(reason))


__all__ = [
    "COVERAGE_EXECUTION_CANDIDATE_LIBRARY_SCHEMA",
    "COVERAGE_EXECUTION_CORRIDOR_ID_BASE",
    "COVERAGE_GRID_CELL_COUNT",
    "CoverageCorridorPrototype",
    "CoverageExecutionCandidateContractError",
    "CoverageExecutionLibraryContract",
    "CoverageExecutionLibraryContractParser",
    "finite_contract_float",
    "raise_execution_contract_error",
    "validate_axis_id",
    "validate_cell_id",
    "validate_positive_int",
]
