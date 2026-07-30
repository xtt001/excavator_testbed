"""Evidence gates for replay effect and planned-cut calibration models."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence, Set
from typing import Any

import numpy as np

from testbed.eval.terrain_effect_ensemble import DEFAULT_GROUPED_FOLD_COUNT

PLANNED_CALIBRATION_MIN_IMPROVEMENT_FRACTION = 0.10
DIRECT_PLANNED_MIN_INCREMENTAL_IMPROVEMENT_FRACTION = 0.05
REPLAY_CONSTANT_MIN_IMPROVEMENT_FRACTION = 0.10
CELL_DELTA_MAX_GEOMETRIC_MAE_RATIO = 1.05


def build_replay_effect_cv_acceptance(
    rows: Sequence[Mapping[str, Any]],
    *,
    min_candidate_spearman: float,
) -> dict[str, Any]:
    """Summarize formal 6-fold replay CV against two explicit baselines."""

    if not -1.0 <= float(min_candidate_spearman) <= 1.0:
        raise ValueError("min_candidate_spearman must be in [-1, 1].")
    if not rows:
        raise ValueError("Replay CV rows must not be empty.")
    fold_indices = sorted({_integer(row, "fold_index") for row in rows})
    required_folds = list(range(DEFAULT_GROUPED_FOLD_COUNT))
    if fold_indices != required_folds:
        raise ValueError(f"Replay CV requires exactly folds {required_folds}.")
    episode_to_fold: dict[str, int] = {}
    for row in rows:
        episode_id = _nonempty_string(row, "episode_id")
        fold_index = _integer(row, "fold_index")
        previous = episode_to_fold.setdefault(episode_id, fold_index)
        if previous != fold_index:
            raise ValueError(f"Episode appears in multiple folds: {episode_id!r}.")
    _validate_constant_baseline(rows)

    actual_removed = _column(rows, "actual_removed_volume_m3")
    actual_payload = _column(rows, "actual_payload_gain_kg")
    model_fields = {
        "effect": (
            "effect_removed_volume_m3",
            "effect_payload_gain_kg",
        ),
        "constant": (
            "constant_removed_volume_m3",
            "constant_payload_gain_kg",
        ),
        "geometric": (
            "geometric_removed_volume_m3",
            "geometric_payload_gain_kg",
        ),
    }
    mae: dict[str, dict[str, float]] = {}
    for model_name, (removed_field, payload_field) in model_fields.items():
        mae[model_name] = {
            "removed_volume_m3": _mae(actual_removed, _column(rows, removed_field)),
            "payload_gain_kg": _mae(actual_payload, _column(rows, payload_field)),
        }
    improvements = {
        "vs_constant": {
            target: _improvement_fraction(
                mae["constant"][target], mae["effect"][target]
            )
            for target in ("removed_volume_m3", "payload_gain_kg")
        },
        "vs_geometric": {
            target: _improvement_fraction(
                mae["geometric"][target], mae["effect"][target]
            )
            for target in ("removed_volume_m3", "payload_gain_kg")
        },
    }
    cell_delta_mae = {
        "effect": _cell_delta_mae(
            rows,
            predicted_field="effect_signed_depth_delta_m",
        ),
        "geometric": _cell_delta_mae(
            rows,
            predicted_field="geometric_signed_depth_delta_m",
        ),
    }
    constant_gate_pass = all(
        value is not None
        and value >= REPLAY_CONSTANT_MIN_IMPROVEMENT_FRACTION
        for value in improvements["vs_constant"].values()
    )
    geometric_cell_mae = cell_delta_mae["geometric"]
    effect_cell_mae = cell_delta_mae["effect"]
    if geometric_cell_mae <= 1.0e-12:
        cell_delta_ratio = 1.0 if effect_cell_mae <= 1.0e-12 else None
        cell_delta_gate_pass = effect_cell_mae <= 1.0e-12
    else:
        cell_delta_ratio = effect_cell_mae / geometric_cell_mae
        cell_delta_gate_pass = (
            cell_delta_ratio <= CELL_DELTA_MAX_GEOMETRIC_MAE_RATIO
        )
    spearman = _grouped_candidate_spearman(rows)
    spearman_minimum = max(0.0, float(min_candidate_spearman))
    spearman_gate_pass = spearman["status"] == "present" and float(
        spearman["median"]
    ) > spearman_minimum
    per_fold = [
        _fold_summary(
            [row for row in rows if _integer(row, "fold_index") == fold_index],
            fold_index,
            model_fields,
        )
        for fold_index in required_folds
    ]
    return {
        "schema": "replay_effect_cv_acceptance_v1",
        "source": "heldout_episode_grouped_replay_predictions",
        "status": (
            "pass"
            if constant_gate_pass
            and cell_delta_gate_pass
            and spearman_gate_pass
            else "fail"
        ),
        "fold_count": DEFAULT_GROUPED_FOLD_COUNT,
        "fold_indices": fold_indices,
        "episode_group_leakage_status": "disjoint",
        "sample_count": len(rows),
        "baseline_contract": {
            "constant": "fold_local_constant_prediction",
            "geometric": "explicit_geometric_footprint_prediction",
        },
        "mae": mae,
        "cell_delta_mae": cell_delta_mae,
        "improvement_fraction": improvements,
        "constant_baseline_gate": {
            "status": "pass" if constant_gate_pass else "fail",
            "minimum_improvement_fraction": (
                REPLAY_CONSTANT_MIN_IMPROVEMENT_FRACTION
            ),
            "targets": ["removed_volume_m3", "payload_gain_kg"],
        },
        "cell_delta_geometric_gate": {
            "status": "pass" if cell_delta_gate_pass else "fail",
            "maximum_mae_ratio": CELL_DELTA_MAX_GEOMETRIC_MAE_RATIO,
            "effect_to_geometric_mae_ratio": cell_delta_ratio,
        },
        "mae_improvement_gate": {
            "status": (
                "pass"
                if constant_gate_pass and cell_delta_gate_pass
                else "fail"
            ),
            "rule": (
                "scalar_mae_improves_constant_by_10pct_and_cell_delta_mae_"
                "is_within_5pct_of_geometric"
            ),
        },
        "candidate_spearman": spearman,
        "candidate_spearman_gate": {
            "status": "pass" if spearman_gate_pass else "fail",
            "minimum_exclusive": spearman_minimum,
            "aggregate": "median_over_ranked_candidate_groups",
        },
        "folds": per_fold,
    }


def build_planned_cut_calibration_acceptance(
    heldout_rows: Sequence[Mapping[str, Any]],
    *,
    training_reset_group_ids: Set[str] | set[str],
) -> dict[str, Any]:
    """Gate a real two-stage calibration and a separate direct-model ablation."""

    if not heldout_rows:
        raise ValueError("Held-out planned calibration rows must not be empty.")
    heldout_groups = {_nonempty_string(row, "reset_group_id") for row in heldout_rows}
    training_groups = {str(value) for value in training_reset_group_ids}
    overlap = sorted(heldout_groups & training_groups)
    if overlap:
        raise ValueError(f"Training/held-out reset-group leakage: {overlap}.")

    actual_removed = _column(heldout_rows, "actual_removed_volume_m3")
    actual_payload = _column(heldout_rows, "actual_payload_gain_kg")
    plan_as_executed_mae = {
        "removed_volume_m3": _mae(
            actual_removed,
            _column(heldout_rows, "plan_as_executed_removed_volume_m3"),
        ),
        "payload_gain_kg": _mae(
            actual_payload,
            _column(heldout_rows, "plan_as_executed_payload_gain_kg"),
        ),
    }
    two_stage_mae = {
        "removed_volume_m3": _mae(
            actual_removed,
            _column(heldout_rows, "two_stage_removed_volume_m3"),
        ),
        "payload_gain_kg": _mae(
            actual_payload,
            _column(heldout_rows, "two_stage_payload_gain_kg"),
        ),
    }
    two_stage_improvement = {
        target: _improvement_fraction(
            plan_as_executed_mae[target],
            two_stage_mae[target],
        )
        for target in ("removed_volume_m3", "payload_gain_kg")
    }
    two_stage_pass = all(
        value is not None and value >= PLANNED_CALIBRATION_MIN_IMPROVEMENT_FRACTION
        for value in two_stage_improvement.values()
    )

    direct_fields = (
        "direct_planned_removed_volume_m3",
        "direct_planned_payload_gain_kg",
    )
    direct_available = all(
        field in row for row in heldout_rows for field in direct_fields
    )
    if direct_available:
        direct_mae: dict[str, float] | None = {
            "removed_volume_m3": _mae(
                actual_removed,
                _column(heldout_rows, direct_fields[0]),
            ),
            "payload_gain_kg": _mae(
                actual_payload,
                _column(heldout_rows, direct_fields[1]),
            ),
        }
        direct_improvement: dict[str, float | None] | None = {
            target: _improvement_fraction(two_stage_mae[target], direct_mae[target])
            for target in ("removed_volume_m3", "payload_gain_kg")
        }
        direct_release = all(
            value is not None
            and value >= DIRECT_PLANNED_MIN_INCREMENTAL_IMPROVEMENT_FRACTION
            for value in direct_improvement.values()
        )
        direct_status = "release_allowed" if direct_release else "not_release"
    else:
        direct_mae = None
        direct_improvement = None
        direct_status = "not_evaluated_not_release"

    return {
        "schema": "planned_cut_calibration_acceptance_v1",
        "source": "heldout_reset_group_predictions",
        "status": "pass" if two_stage_pass else "fail",
        "reset_group_split_status": "disjoint",
        "training_reset_group_ids": sorted(training_groups),
        "heldout_reset_group_ids": sorted(heldout_groups),
        "heldout_record_count": len(heldout_rows),
        "model_contract": {
            "two_stage": "executed_cut_effect_plus_planned_to_executed_calibration",
            "direct_planned": "separate_ablation_not_two_stage",
        },
        "mae": {
            "plan_as_executed": plan_as_executed_mae,
            "two_stage": two_stage_mae,
            "direct_planned": direct_mae,
        },
        "two_stage_calibration_gate": {
            "status": "pass" if two_stage_pass else "fail",
            "minimum_improvement_fraction": (
                PLANNED_CALIBRATION_MIN_IMPROVEMENT_FRACTION
            ),
            "improvement_fraction": two_stage_improvement,
        },
        "direct_planned_residual_gate": {
            "status": direct_status,
            "minimum_incremental_improvement_fraction": (
                DIRECT_PLANNED_MIN_INCREMENTAL_IMPROVEMENT_FRACTION
            ),
            "improvement_fraction_vs_two_stage": direct_improvement,
        },
    }


def _fold_summary(
    rows: Sequence[Mapping[str, Any]],
    fold_index: int,
    model_fields: Mapping[str, tuple[str, str]],
) -> dict[str, Any]:
    actual_removed = _column(rows, "actual_removed_volume_m3")
    actual_payload = _column(rows, "actual_payload_gain_kg")
    return {
        "fold_index": fold_index,
        "record_count": len(rows),
        "episode_ids": sorted({_nonempty_string(row, "episode_id") for row in rows}),
        "mae": {
            model_name: {
                "removed_volume_m3": _mae(actual_removed, _column(rows, fields[0])),
                "payload_gain_kg": _mae(actual_payload, _column(rows, fields[1])),
            }
            for model_name, fields in model_fields.items()
        },
        "cell_delta_mae": {
            "effect": _cell_delta_mae(
                rows,
                predicted_field="effect_signed_depth_delta_m",
            ),
            "geometric": _cell_delta_mae(
                rows,
                predicted_field="geometric_signed_depth_delta_m",
            ),
        },
    }


def _validate_constant_baseline(rows: Sequence[Mapping[str, Any]]) -> None:
    for fold_index in range(DEFAULT_GROUPED_FOLD_COUNT):
        fold_rows = [row for row in rows if _integer(row, "fold_index") == fold_index]
        for field in (
            "constant_removed_volume_m3",
            "constant_payload_gain_kg",
        ):
            values = _column(fold_rows, field)
            if np.ptp(values) > 1.0e-12:
                raise ValueError(f"{field} must be constant inside fold {fold_index}.")


def _grouped_candidate_spearman(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[int, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        group_id = _nonempty_string(row, "candidate_group_id")
        groups[(_integer(row, "fold_index"), group_id)].append(row)
    correlations: list[float] = []
    skipped_group_count = 0
    for group_rows in groups.values():
        if len(group_rows) < 2:
            skipped_group_count += 1
            continue
        actual = _column(group_rows, "actual_candidate_utility")
        predicted = _column(group_rows, "effect_candidate_score")
        actual_rank = _average_ranks(actual)
        predicted_rank = _average_ranks(predicted)
        if np.std(actual_rank) <= 1.0e-12 or np.std(predicted_rank) <= 1.0e-12:
            skipped_group_count += 1
            continue
        correlations.append(float(np.corrcoef(actual_rank, predicted_rank)[0, 1]))
    return {
        "status": "present" if correlations else "not_evaluable_no_ranked_groups",
        "mean": float(np.mean(correlations)) if correlations else None,
        "median": float(np.median(correlations)) if correlations else None,
        "evaluated_group_count": len(correlations),
        "skipped_group_count": skipped_group_count,
    }


def _cell_delta_mae(
    rows: Sequence[Mapping[str, Any]],
    *,
    predicted_field: str,
) -> float:
    actual = _fixed_cell_delta_matrix(rows, "actual_signed_depth_delta_m")
    predicted = _fixed_cell_delta_matrix(rows, predicted_field)
    return float(np.mean(np.abs(predicted - actual)))


def _fixed_cell_delta_matrix(
    rows: Sequence[Mapping[str, Any]],
    field: str,
) -> np.ndarray:
    values: list[np.ndarray] = []
    for row in rows:
        try:
            vector = np.asarray(row[field], dtype=np.float64).reshape(-1)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{field} must contain six finite values.") from exc
        if vector.size != 6 or not np.isfinite(vector).all():
            raise ValueError(f"{field} must contain six finite values.")
        values.append(vector)
    return np.stack(values)


def _average_ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=np.float64)
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and values[order[end]] == values[order[start]]:
            end += 1
        ranks[order[start:end]] = (start + end - 1) / 2.0
        start = end
    return ranks


def _column(rows: Sequence[Mapping[str, Any]], field: str) -> np.ndarray:
    return np.asarray([_finite(row, field) for row in rows], dtype=np.float64)


def _mae(actual: np.ndarray, predicted: np.ndarray) -> float:
    return float(np.mean(np.abs(predicted - actual)))


def _improvement_fraction(baseline: float, candidate: float) -> float | None:
    if baseline <= 1.0e-12:
        return None
    return float((baseline - candidate) / baseline)


def _finite(row: Mapping[str, Any], field: str) -> float:
    try:
        value = float(row[field])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be present and finite.") from exc
    if not np.isfinite(value):
        raise ValueError(f"{field} must be present and finite.")
    return value


def _integer(row: Mapping[str, Any], field: str) -> int:
    value = row.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{field} must be an integer.")
    return int(value)


def _nonempty_string(row: Mapping[str, Any], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string.")
    return value


__all__ = [
    "CELL_DELTA_MAX_GEOMETRIC_MAE_RATIO",
    "REPLAY_CONSTANT_MIN_IMPROVEMENT_FRACTION",
    "DIRECT_PLANNED_MIN_INCREMENTAL_IMPROVEMENT_FRACTION",
    "PLANNED_CALIBRATION_MIN_IMPROVEMENT_FRACTION",
    "build_planned_cut_calibration_acceptance",
    "build_replay_effect_cv_acceptance",
]
