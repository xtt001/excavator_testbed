"""Load frozen Dig support populations for read-only OOS diagnostics.

This module owns source splits, HDF5 row classification, and the historical
v1 p01/p99 population.  It deliberately has no target-segment argument, so a
recorded outlier cannot alter fitted support evidence while it is being
diagnosed.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import yaml

from testbed.data.act_support_contract import (
    StrictSourceAwareSupportRows,
    SupportRowProvenance,
    load_strict_source_aware_support_rows,
)
from testbed.data.action_loss_mask import read_action_loss_mask
from testbed.data.recorded_act_replay import (
    StrictTrainNumericSupport,
    build_strict_train_numeric_support,
)
from testbed.data.schema import DS_STEP_ID

DIG_SUPPORT_OUTLIER_DISTRIBUTION_SCHEMA = "dig_support_outlier_distribution_v1"
DIG_FEATURE_ORDER = tuple(
    [f"qpos[{index}]" for index in range(4)]
    + [f"qvel[{index}]" for index in range(4)]
    + [f"dig_cut_tokens[{index}]" for index in range(10)]
)
DIG_QVEL1_FEATURE_INDEX = 5
_MAX_EXAMPLES = 8
_EPISODE_FILE = re.compile(r"^episode_(\d+)\.hdf5$")


class DigSupportOutlierDistributionError(ValueError):
    """Raised when frozen source evidence cannot be trusted."""


@dataclass(frozen=True)
class Qvel1RowProvenance:
    primitive: str
    partition: str
    primitive_episode_id: int
    source_episode_id: int | None
    step_index: int
    step_id: int | None
    action_loss_mask: int | None

    def as_dict(self, *, qvel1: float) -> dict[str, Any]:
        return {
            "qvel1": float(qvel1),
            "primitive": self.primitive,
            "partition": self.partition,
            "primitive_episode_id": self.primitive_episode_id,
            "source_episode_id": self.source_episode_id,
            "step_index": self.step_index,
            "step_id": self.step_id,
            "action_loss_mask": self.action_loss_mask,
        }


@dataclass(frozen=True)
class Qvel1Population:
    """An explicitly scoped qvel[1] source population."""

    name: str
    purpose: str
    values: np.ndarray
    provenance: tuple[Qvel1RowProvenance, ...]
    source_directory: str | None

    @property
    def row_count(self) -> int:
        return int(self.values.size)

    def range_summary(self, *, lower: float, upper: float) -> dict[str, Any]:
        """Describe target-range overlap without fitting or selecting anything."""

        if not np.isfinite(lower) or not np.isfinite(upper) or lower > upper:
            raise DigSupportOutlierDistributionError("target qvel[1] interval is invalid")
        matches = np.flatnonzero((self.values >= lower) & (self.values <= upper))
        return {
            "population": self.name,
            "purpose": self.purpose,
            "source_directory": self.source_directory,
            "row_count": self.row_count,
            "qvel1_min": None if not self.row_count else float(np.min(self.values)),
            "qvel1_max": None if not self.row_count else float(np.max(self.values)),
            "source_episode_ids": sorted(
                {
                    int(item.source_episode_id)
                    for item in self.provenance
                    if item.source_episode_id is not None
                }
            ),
            "target_qvel1_interval": {"lower": float(lower), "upper": float(upper)},
            "within_target_interval_row_count": int(matches.size),
            "within_target_interval_fraction": (
                0.0 if not self.row_count else float(matches.size / self.row_count)
            ),
            "examples": [
                self.provenance[int(index)].as_dict(qvel1=float(self.values[index]))
                for index in matches[:_MAX_EXAMPLES]
            ],
            "used_for_support_fit_or_selection": False,
        }


@dataclass(frozen=True)
class DigSupportOutlierDistributionReferences:
    """Strict source evidence plus audit-only non-training categories."""

    schema: str
    strict_rows: StrictSourceAwareSupportRows
    v1_support: StrictTrainNumericSupport
    strict_train_qvel1: Qvel1Population
    held_validation_qvel1: Qvel1Population
    strict_train_masked_qvel1: Qvel1Population
    excluded_dig_primitive_qvel1: Qvel1Population
    excluded_dig_primitive_missing_episode_ids: tuple[int, ...]
    other_primitive_qvel1: tuple[Qvel1Population, ...]
    training_config_path: str
    split_path: str
    dig_dataset_dir: str


@dataclass(frozen=True)
class _SplitMetadata:
    train_ids: tuple[int, ...]
    validation_ids: tuple[int, ...]
    available_ids: tuple[int, ...]
    excluded_training_tier_ids: tuple[int, ...]
    source_by_primitive_id: Mapping[int, int]


def load_dig_support_outlier_distribution_references(
    *,
    training_config_path: str | Path,
    other_primitive_dataset_dirs: Mapping[str, str | Path] | None = None,
) -> DigSupportOutlierDistributionReferences:
    """Load source-safe evidence before a target feature matrix is available."""

    config_path = Path(training_config_path).expanduser().resolve(strict=True)
    strict_rows = load_strict_source_aware_support_rows(
        training_config_path=config_path,
        skill_name="dig",
    )
    v1_support = build_strict_train_numeric_support(
        primitive_dataset_dir=strict_rows.primitive_dataset_dir,
        split_path=strict_rows.split_path,
        skill_name="dig",
    )
    validate_dig_support_outlier_distribution_references(
        strict_rows=strict_rows,
        v1_support=v1_support,
    )
    config = _read_yaml(config_path, label="Dig training config")
    task = _mapping(config, "task", label="Dig training config")
    train = _mapping(config, "train", label="Dig training config")
    dataset_dir = Path(str(task.get("dataset_dir", ""))).expanduser().resolve(
        strict=True
    )
    split_path = Path(str(train.get("split_path", ""))).expanduser().resolve(strict=True)
    if dataset_dir != Path(strict_rows.primitive_dataset_dir).resolve(strict=True):
        raise DigSupportOutlierDistributionError("Dig config dataset_dir mismatch")
    if split_path != Path(strict_rows.split_path).resolve(strict=True):
        raise DigSupportOutlierDistributionError("Dig config split_path mismatch")
    metadata = _split_metadata(
        _read_yaml(split_path, label="Dig source split"),
        dataset_dir=dataset_dir,
    )
    train_population = _strict_population(
        name="strict_train_action_loss_mask_1",
        purpose="historical_v1_fit_population",
        features=strict_rows.train_features,
        provenance=strict_rows.train_provenance,
        source_directory=dataset_dir,
    )
    validation_population = _strict_population(
        name="held_validation_action_loss_mask_1",
        purpose="read_only_normal_state_presentation",
        features=strict_rows.validation_features,
        provenance=strict_rows.validation_provenance,
        source_directory=dataset_dir,
    )
    masked_population = _masked_dig_population(
        name="strict_train_action_loss_mask_0",
        purpose="audit_only_rows_excluded_from_v1_fit",
        directory=dataset_dir,
        primitive_ids=metadata.train_ids,
        source_by_primitive_id=metadata.source_by_primitive_id,
        partition="strict_train",
    )
    excluded_population, missing_ids = _excluded_dig_population(
        directory=dataset_dir,
        metadata=metadata,
    )
    return DigSupportOutlierDistributionReferences(
        schema=DIG_SUPPORT_OUTLIER_DISTRIBUTION_SCHEMA,
        strict_rows=strict_rows,
        v1_support=v1_support,
        strict_train_qvel1=train_population,
        held_validation_qvel1=validation_population,
        strict_train_masked_qvel1=masked_population,
        excluded_dig_primitive_qvel1=excluded_population,
        excluded_dig_primitive_missing_episode_ids=missing_ids,
        other_primitive_qvel1=_other_primitive_populations(
            dig_directory=dataset_dir,
            supplied_directories=other_primitive_dataset_dirs,
        ),
        training_config_path=str(config_path),
        split_path=str(split_path),
        dig_dataset_dir=str(dataset_dir),
    )


def validate_dig_support_outlier_distribution_references(
    *,
    strict_rows: StrictSourceAwareSupportRows,
    v1_support: StrictTrainNumericSupport,
) -> None:
    """Validate that v1 is exactly the source-safe Dig feature population."""

    if (
        strict_rows.skill_name != "dig"
        or strict_rows.model_token_key != "dig_cut_tokens"
        or tuple(strict_rows.feature_order) != DIG_FEATURE_ORDER
        or v1_support.skill_name != "dig"
        or v1_support.model_token_key != "dig_cut_tokens"
        or tuple(v1_support.feature_order) != DIG_FEATURE_ORDER
    ):
        raise DigSupportOutlierDistributionError("Dig support feature contract mismatch")
    for feature, provenance, partition in (
        (strict_rows.train_features, strict_rows.train_provenance, "train"),
        (
            strict_rows.validation_features,
            strict_rows.validation_provenance,
            "validation",
        ),
    ):
        matrix = np.asarray(feature, dtype=np.float64)
        if (
            matrix.shape != (len(provenance), len(DIG_FEATURE_ORDER))
            or not np.isfinite(matrix).all()
            or any(item.partition != partition or item.action_loss_mask != 1 for item in provenance)
        ):
            raise DigSupportOutlierDistributionError(
                "strict Dig rows must be finite action_loss_mask=1 rows"
            )
    lower = np.asarray(v1_support.p01, dtype=np.float64)
    upper = np.asarray(v1_support.p99, dtype=np.float64)
    if (
        lower.shape != (len(DIG_FEATURE_ORDER),)
        or upper.shape != lower.shape
        or not np.isfinite(lower).all()
        or not np.isfinite(upper).all()
        or np.any(lower > upper)
    ):
        raise DigSupportOutlierDistributionError("v1 support bounds are invalid")


def _strict_population(
    *,
    name: str,
    purpose: str,
    features: np.ndarray,
    provenance: Sequence[SupportRowProvenance],
    source_directory: Path,
) -> Qvel1Population:
    values = np.asarray(features, dtype=np.float64)[:, DIG_QVEL1_FEATURE_INDEX]
    records = tuple(
        Qvel1RowProvenance(
            primitive="dig",
            partition=("strict_train" if item.partition == "train" else "held_validation"),
            primitive_episode_id=int(item.primitive_episode_id),
            source_episode_id=int(item.source_episode_id),
            step_index=int(item.step_index),
            step_id=int(item.step_id),
            action_loss_mask=1,
        )
        for item in provenance
    )
    return _population(
        name=name,
        purpose=purpose,
        values=(values,),
        provenance=records,
        source_directory=source_directory,
    )


def _masked_dig_population(
    *,
    name: str,
    purpose: str,
    directory: Path,
    primitive_ids: Sequence[int],
    source_by_primitive_id: Mapping[int, int],
    partition: str,
) -> Qvel1Population:
    values: list[np.ndarray] = []
    records: list[Qvel1RowProvenance] = []
    for primitive_id in primitive_ids:
        qvel1, step_ids, mask, source_id = _read_qvel1_rows(
            directory / f"episode_{primitive_id}.hdf5", require_mask=True
        )
        if source_id != source_by_primitive_id[primitive_id]:
            raise DigSupportOutlierDistributionError(
                "Dig HDF5 source_episode_id disagrees with source split"
            )
        indices = np.flatnonzero(mask == 0)
        values.append(qvel1[indices])
        records.extend(
            Qvel1RowProvenance(
                primitive="dig",
                partition=partition,
                primitive_episode_id=int(primitive_id),
                source_episode_id=source_id,
                step_index=int(index),
                step_id=int(step_ids[index]),
                action_loss_mask=0,
            )
            for index in indices
        )
    return _population(
        name=name,
        purpose=purpose,
        values=values,
        provenance=records,
        source_directory=directory,
    )


def _excluded_dig_population(
    *,
    directory: Path,
    metadata: _SplitMetadata,
) -> tuple[Qvel1Population, tuple[int, ...]]:
    selected = set(metadata.train_ids) | set(metadata.validation_ids)
    candidate_ids = (
        set(metadata.available_ids)
        | _episode_ids(directory)
        | set(metadata.excluded_training_tier_ids)
    ) - selected
    values: list[np.ndarray] = []
    records: list[Qvel1RowProvenance] = []
    missing: list[int] = []
    for primitive_id in sorted(candidate_ids):
        path = directory / f"episode_{primitive_id}.hdf5"
        if not path.is_file():
            missing.append(primitive_id)
            continue
        qvel1, step_ids, mask, source_id = _read_qvel1_rows(path, require_mask=False)
        values.append(qvel1)
        partition = (
            "excluded_training_tier"
            if primitive_id in metadata.excluded_training_tier_ids
            else "outside_strict_source_split"
        )
        records.extend(
            Qvel1RowProvenance(
                primitive="dig",
                partition=partition,
                primitive_episode_id=primitive_id,
                source_episode_id=source_id,
                step_index=int(index),
                step_id=int(step_ids[index]),
                action_loss_mask=None if mask is None else int(mask[index]),
            )
            for index in range(qvel1.size)
        )
    return (
        _population(
            name="excluded_dig_primitive_episode",
            purpose="audit_only_dig_rows_outside_strict_train_validation",
            values=values,
            provenance=records,
            source_directory=directory,
        ),
        tuple(missing),
    )


def _other_primitive_populations(
    *,
    dig_directory: Path,
    supplied_directories: Mapping[str, str | Path] | None,
) -> tuple[Qvel1Population, ...]:
    directories = (
        {name: dig_directory.parent / name for name in ("carry", "dump", "return")}
        if supplied_directories is None
        else {str(name).strip().lower(): value for name, value in supplied_directories.items()}
    )
    result: list[Qvel1Population] = []
    for primitive, raw_directory in sorted(directories.items()):
        if primitive in {"", "dig"}:
            raise DigSupportOutlierDistributionError("other primitive cannot be Dig")
        directory = Path(raw_directory).expanduser().resolve()
        values: list[np.ndarray] = []
        records: list[Qvel1RowProvenance] = []
        for primitive_id, path in _episode_paths(directory):
            qvel1, step_ids, mask, source_id = _read_qvel1_rows(path, require_mask=False)
            values.append(qvel1)
            records.extend(
                Qvel1RowProvenance(
                    primitive=primitive,
                    partition="other_primitive",
                    primitive_episode_id=primitive_id,
                    source_episode_id=source_id,
                    step_index=int(index),
                    step_id=int(step_ids[index]),
                    action_loss_mask=None if mask is None else int(mask[index]),
                )
                for index in range(qvel1.size)
            )
        result.append(
            _population(
                name=f"other_primitive:{primitive}",
                purpose="audit_only_same_qvel1_range_in_other_primitive",
                values=values,
                provenance=records,
                source_directory=directory,
            )
        )
    return tuple(result)


def _split_metadata(payload: Mapping[str, Any], *, dataset_dir: Path) -> _SplitMetadata:
    if str(payload.get("split_policy", "")) != "source_identity_exact_allowlist_v1":
        raise DigSupportOutlierDistributionError("Dig source split policy mismatch")
    if Path(str(payload.get("dataset_dir", ""))).expanduser().resolve(strict=True) != dataset_dir:
        raise DigSupportOutlierDistributionError("Dig source split dataset_dir mismatch")
    train_ids = _integer_tuple(payload.get("train_ids"), label="train_ids")
    validation_ids = _integer_tuple(payload.get("val_ids"), label="val_ids")
    if set(train_ids) & set(validation_ids):
        raise DigSupportOutlierDistributionError("Dig source split ids overlap")
    raw_mapping = payload.get("source_episode_id_by_primitive_episode_id")
    if not isinstance(raw_mapping, Mapping):
        raise DigSupportOutlierDistributionError("Dig source split lacks source mapping")
    source_map = {
        _integer(key, label="source map primitive id"): _source_id(value)
        for key, value in raw_mapping.items()
    }
    if not (set(train_ids) | set(validation_ids)) <= set(source_map):
        raise DigSupportOutlierDistributionError("Dig source split source mapping incomplete")
    available = payload.get("available_episode_ids")
    return _SplitMetadata(
        train_ids=train_ids,
        validation_ids=validation_ids,
        available_ids=(
            _integer_tuple(available, label="available_episode_ids")
            if available is not None
            else tuple(sorted(_episode_ids(dataset_dir)))
        ),
        excluded_training_tier_ids=_integer_tuple(
            payload.get("excluded_training_tier_episode_ids", ()),
            label="excluded_training_tier_episode_ids",
        ),
        source_by_primitive_id=source_map,
    )


def _read_qvel1_rows(
    path: Path,
    *,
    require_mask: bool,
) -> tuple[np.ndarray, np.ndarray, np.ndarray | None, int | None]:
    if not path.is_file():
        raise FileNotFoundError(path)
    with h5py.File(path, "r") as handle:
        if "observations/qvel" not in handle:
            raise DigSupportOutlierDistributionError(f"{path} lacks observations/qvel")
        dataset = handle["observations/qvel"]
        if len(dataset.shape) != 2 or dataset.shape[1] != 4:
            raise DigSupportOutlierDistributionError(f"{path} qvel shape must be (T, 4)")
        qvel1 = np.asarray(dataset[:, 1], dtype=np.float64).reshape(-1)
        if not np.isfinite(qvel1).all():
            raise DigSupportOutlierDistributionError(f"{path} qvel[1] is non-finite")
        count = int(qvel1.size)
        step_ids = (
            np.asarray(handle[DS_STEP_ID][:], dtype=np.int64).reshape(-1)
            if DS_STEP_ID in handle
            else np.arange(count, dtype=np.int64)
        )
        if step_ids.shape != (count,) or np.any(np.diff(step_ids) <= 0):
            raise DigSupportOutlierDistributionError(f"{path} step ids are invalid")
        mask = read_action_loss_mask(handle, expected_length=count, required=require_mask)
        source_id = _source_id(handle["metadata"].attrs["source_episode_id"])
    return qvel1, step_ids, mask, source_id


def _population(
    *,
    name: str,
    purpose: str,
    values: Sequence[np.ndarray],
    provenance: Sequence[Qvel1RowProvenance],
    source_directory: Path | str,
) -> Qvel1Population:
    merged = (
        np.concatenate([np.asarray(value, dtype=np.float64).reshape(-1) for value in values])
        if values
        else np.empty(0, dtype=np.float64)
    )
    if merged.shape != (len(provenance),) or not np.isfinite(merged).all():
        raise DigSupportOutlierDistributionError(f"{name} values/provenance invalid")
    merged.setflags(write=False)
    return Qvel1Population(
        name=name,
        purpose=purpose,
        values=merged,
        provenance=tuple(provenance),
        source_directory=str(source_directory),
    )


def _read_yaml(path: Path, *, label: str) -> Mapping[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, Mapping):
        raise DigSupportOutlierDistributionError(f"{label} must be a mapping")
    return payload


def _mapping(payload: Mapping[str, Any], key: str, *, label: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise DigSupportOutlierDistributionError(f"{label} lacks mapping {key!r}")
    return value


def _integer_tuple(value: Any, *, label: str) -> tuple[int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise DigSupportOutlierDistributionError(f"{label} must be a sequence")
    result = tuple(_integer(item, label=label) for item in value)
    if len(result) != len(set(result)):
        raise DigSupportOutlierDistributionError(f"{label} contains duplicate ids")
    return result


def _integer(value: Any, *, label: str) -> int:
    if isinstance(value, bool):
        raise DigSupportOutlierDistributionError(f"{label} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise DigSupportOutlierDistributionError(f"{label} must be an integer") from exc
    if not isinstance(value, (int, np.integer)) and str(result) != str(value).strip():
        raise DigSupportOutlierDistributionError(f"{label} must be an integer")
    return result


def _source_id(value: Any) -> int:
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    return _integer(str(value).strip().removeprefix("episode_"), label="source episode id")


def _episode_paths(directory: Path) -> tuple[tuple[int, Path], ...]:
    if not directory.is_dir():
        return ()
    result = []
    for path in directory.glob("episode_*.hdf5"):
        match = _EPISODE_FILE.fullmatch(path.name)
        if match:
            result.append((int(match.group(1)), path))
    return tuple(sorted(result))


def _episode_ids(directory: Path) -> set[int]:
    return {episode_id for episode_id, _ in _episode_paths(directory)}


__all__ = [
    "DIG_FEATURE_ORDER",
    "DIG_QVEL1_FEATURE_INDEX",
    "DIG_SUPPORT_OUTLIER_DISTRIBUTION_SCHEMA",
    "DigSupportOutlierDistributionError",
    "DigSupportOutlierDistributionReferences",
    "Qvel1Population",
    "Qvel1RowProvenance",
    "load_dig_support_outlier_distribution_references",
    "validate_dig_support_outlier_distribution_references",
]
