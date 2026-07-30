"""Build fixed cycle-0/1 cut-plan sources for ACT regression diagnostics."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from testbed.data.operator_first_v2_2 import DIG_CUT_TOKEN_DIM
from testbed.planner.primitive.token.residual_cut_intent_source import (
    RESIDUAL_CUT_INTENT_RUNTIME_SOURCE,
    RESIDUAL_CUT_INTENT_RUNTIME_SOURCE_SCHEMA,
)
from testbed.planner.primitive.token.tokens import DigCutTokenPlanner

ACT_REGRESSION_PLAN_MATRIX_SCHEMA = "act_regression_plan_matrix_v1"
CONDITION_ORDER = ("F0", "D1", "C1", "DC1")
LOCKED_CYCLE_INDICES = (0, 1)
DEPTH_DIAGNOSTIC_PERCENTILE = "p10"
CORRIDOR_DIAGNOSTIC_CELL_ID = 2
RUNTIME_SOURCE_FILENAME = "residual_cut_intent_runtime_source.json"
MANIFEST_FILENAME = "manifest.json"

_FIXED_PLAN_SOURCE = "act_regression_plan_matrix_fixed_cycle01"
_FIXED_PROFILE = "strict18_act_regression_plan_matrix_cycle01_v1"
_DEPTH_RAW_FIELD = "operator_cut_depth_peak_m"
_GEOMETRY_RAW_FIELDS = (
    "operator_entry_x_m",
    "operator_entry_z_m",
    "operator_exit_x_m",
    "operator_exit_z_m",
    "operator_cut_direction_x",
    "operator_cut_direction_z",
)
_REPO_ROOT = Path(__file__).resolve().parents[2]


class ActRegressionPlanMatrixError(ValueError):
    """Raised when the diagnostic matrix cannot preserve one-factor isolation."""


def build_act_regression_plan_matrix(
    *,
    a0_rollout_artifact_path: str | Path,
    output_dir: str | Path,
    planner_prior_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build no-overwrite F0/D1/C1/DC1 runtime sources and their diff audit."""

    output_path = Path(output_dir)
    if output_path.exists():
        raise FileExistsError(f"output directory already exists: {output_path}")

    rollout_path = _resolve_rollout_jsonl(a0_rollout_artifact_path)
    prior_path = _resolve_prior_path(
        rollout_path=rollout_path,
        explicit_prior_path=planner_prior_path,
    )
    prior = _read_json_mapping(prior_path, label="planner prior")
    observed = _extract_observed_cycle_plans(rollout_path)

    baseline_plans: list[dict[str, Any]] = []
    baseline_cell_ids: dict[int, int] = {}
    for cycle_index in LOCKED_CYCLE_INDICES:
        observed_plan = observed[cycle_index]
        cell_id = int(observed_plan["cell_id"])
        baseline_cell_ids[cycle_index] = cell_id
        raw_fields = _raw_fields_for_prior_cell(prior, cell_id)
        token = _token_from_raw_fields(raw_fields)
        _assert_token_matches_observation(
            cycle_index=cycle_index,
            expected_token=token,
            observed_token=observed_plan["dig_cut_tokens"],
        )
        baseline_plans.append(
            _runtime_plan_record(
                cycle_index=cycle_index,
                raw_fields=raw_fields,
                token=observed_plan["dig_cut_tokens"],
            )
        )

    f0 = _runtime_source_payload(baseline_plans)
    shallow_depth_m = _prior_percentile(
        prior,
        "cut_depth_peak_m",
        DEPTH_DIAGNOSTIC_PERCENTILE,
    )
    target_geometry = _raw_fields_for_prior_cell(
        prior,
        CORRIDOR_DIAGNOSTIC_CELL_ID,
    )
    sources = {
        "F0": f0,
        "D1": _variant_source(
            f0,
            depth_m=shallow_depth_m,
        ),
        "C1": _variant_source(
            f0,
            geometry_raw_fields=target_geometry,
        ),
        "DC1": _variant_source(
            f0,
            depth_m=shallow_depth_m,
            geometry_raw_fields=target_geometry,
        ),
    }
    guards = {
        condition: assert_allowed_condition_diff(
            baseline_source=f0,
            candidate_source=sources[condition],
            condition=condition,
        )
        for condition in CONDITION_ORDER
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.mkdir(exist_ok=False)
    condition_records: dict[str, dict[str, Any]] = {}
    for condition in CONDITION_ORDER:
        condition_dir = output_path / condition
        condition_dir.mkdir()
        source_path = condition_dir / RUNTIME_SOURCE_FILENAME
        source_text = _json_text(sources[condition])
        source_path.write_text(source_text, encoding="utf-8")
        condition_records[condition] = {
            "runtime_source_path": str(source_path.resolve()),
            "runtime_source_sha256": _sha256_bytes(source_text.encode("utf-8")),
            "allowed_diff_guard": guards[condition],
            "cycle_0_cell_id": baseline_cell_ids[0],
            "cycle_1_cell_id": (
                CORRIDOR_DIAGNOSTIC_CELL_ID
                if condition in {"C1", "DC1"}
                else baseline_cell_ids[1]
            ),
            "cycle_1_depth_m": (
                shallow_depth_m
                if condition in {"D1", "DC1"}
                else float(baseline_plans[1]["plan"]["raw_fields"][_DEPTH_RAW_FIELD])
            ),
        }

    manifest_path = output_path / MANIFEST_FILENAME
    manifest: dict[str, Any] = {
        "schema": ACT_REGRESSION_PLAN_MATRIX_SCHEMA,
        "status": "present",
        "diagnostic_only": True,
        "promotion_eligible": False,
        "locked_cycle_indices": list(LOCKED_CYCLE_INDICES),
        "condition_order": list(CONDITION_ORDER),
        "depth_diagnostic": {
            "percentile": DEPTH_DIAGNOSTIC_PERCENTILE,
            "depth_m": shallow_depth_m,
            "changed_cycle_index": 1,
        },
        "corridor_diagnostic": {
            "cell_id": CORRIDOR_DIAGNOSTIC_CELL_ID,
            "changed_cycle_index": 1,
            "held_raw_fields": [
                "operator_cut_length_m",
                "operator_cut_depth_peak_m",
                "operator_cut_payload_gain_kg",
                "operator_effective_deposit_delta_kg",
                "operator_cut_valid",
            ],
        },
        "baseline_lineage": {
            "a0_rollout_artifact_path": str(Path(a0_rollout_artifact_path).resolve()),
            "rollout_jsonl_path": str(rollout_path.resolve()),
            "rollout_jsonl_sha256": _sha256_file(rollout_path),
            "planner_prior_path": str(prior_path.resolve()),
            "planner_prior_sha256": _sha256_file(prior_path),
            "prior_id": str(prior.get("prior_id", "")),
            "cycle_cell_ids": {
                str(cycle): baseline_cell_ids[cycle] for cycle in LOCKED_CYCLE_INDICES
            },
        },
        "conditions": condition_records,
        "manifest_path": str(manifest_path.resolve()),
    }
    manifest_path.write_text(_json_text(manifest), encoding="utf-8")
    return manifest


def assert_allowed_condition_diff(
    *,
    baseline_source: Mapping[str, Any],
    candidate_source: Mapping[str, Any],
    condition: str,
) -> dict[str, Any]:
    """Require the candidate source to differ only by its named factor(s)."""

    normalized_condition = str(condition).strip().upper()
    if normalized_condition not in CONDITION_ORDER:
        raise ActRegressionPlanMatrixError(f"unknown_condition:{normalized_condition}")
    _validate_runtime_source_shape(baseline_source, label="baseline")
    _validate_runtime_source_shape(candidate_source, label="candidate")
    changed_paths = sorted(_changed_leaf_paths(baseline_source, candidate_source))
    expected_paths = sorted(_allowed_paths(normalized_condition))
    unexpected = sorted(set(changed_paths) - set(expected_paths))
    missing = sorted(set(expected_paths) - set(changed_paths))
    if unexpected or missing:
        raise ActRegressionPlanMatrixError(
            "allowed_field_diff_guard_failed:"
            f"condition={normalized_condition}:"
            f"unexpected={unexpected}:missing={missing}"
        )
    return {
        "status": "passed",
        "condition": normalized_condition,
        "changed_paths": changed_paths,
        "allowed_paths": expected_paths,
    }


def _resolve_rollout_jsonl(path_value: str | Path) -> Path:
    path = Path(path_value)
    if path.is_file():
        if not path.name.endswith(".jsonl") or path.name.endswith(".partial.jsonl"):
            raise ActRegressionPlanMatrixError(
                f"a0_rollout_artifact_must_be_complete_jsonl:{path}"
            )
        return path
    if not path.is_dir():
        raise ActRegressionPlanMatrixError(f"a0_rollout_artifact_not_found:{path}")

    preferred = (
        path / "results" / "rollouts" / "rollout_000.jsonl",
        path / "rollouts" / "rollout_000.jsonl",
        path / "rollout_000.jsonl",
    )
    for candidate in preferred:
        if candidate.is_file():
            return candidate
    candidates = sorted(
        candidate
        for candidate in path.glob("**/rollouts/rollout_*.jsonl")
        if not candidate.name.endswith(".partial.jsonl")
    )
    if len(candidates) != 1:
        raise ActRegressionPlanMatrixError(
            "a0_rollout_artifact_requires_exactly_one_complete_rollout:"
            f"found={len(candidates)}"
        )
    return candidates[0]


def _resolve_prior_path(
    *,
    rollout_path: Path,
    explicit_prior_path: str | Path | None,
) -> Path:
    if explicit_prior_path is not None:
        return _resolve_existing_path(
            explicit_prior_path,
            anchors=(Path.cwd(), _REPO_ROOT, rollout_path.parent),
            label="planner_prior",
        )

    trace_path = rollout_path.with_name(f"{rollout_path.stem}_planner_trace.json")
    if not trace_path.is_file():
        raise ActRegressionPlanMatrixError(
            f"planner_prior_path_required:planner_trace_not_found:{trace_path}"
        )
    trace = _read_json_mapping(trace_path, label="planner trace")
    value = trace.get("dig_cut_prior_path")
    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise ActRegressionPlanMatrixError(
            "planner_prior_path_required:planner_trace_missing_dig_cut_prior_path"
        )
    return _resolve_existing_path(
        value,
        anchors=(
            Path.cwd(),
            _REPO_ROOT,
            rollout_path.parent,
            rollout_path.parent.parent,
        ),
        label="planner_prior",
    )


def _resolve_existing_path(
    value: str | Path,
    *,
    anchors: Sequence[Path],
    label: str,
) -> Path:
    path = Path(value)
    candidates = [path] if path.is_absolute() else [anchor / path for anchor in anchors]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise ActRegressionPlanMatrixError(f"{label}_not_found:{path}")


def _extract_observed_cycle_plans(
    rollout_path: Path,
) -> dict[int, dict[str, Any]]:
    observed: dict[int, dict[str, Any]] = {}
    with rollout_path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ActRegressionPlanMatrixError(
                    f"rollout_json_decode_failed:line={line_number}:{exc.msg}"
                ) from exc
            if not isinstance(row, Mapping):
                raise ActRegressionPlanMatrixError(
                    f"rollout_row_must_be_object:line={line_number}"
                )
            cycle_index = _nonnegative_integer(row.get("primitive_cycle_index"))
            if (
                cycle_index not in LOCKED_CYCLE_INDICES
                or row.get("skill_name") != "dig"
                or row.get("dig_cut_token_injected") is not True
            ):
                continue
            token = _finite_float_sequence(
                row.get("dig_cut_tokens"),
                expected_length=DIG_CUT_TOKEN_DIM,
                label=f"line={line_number}:dig_cut_tokens",
            )
            cell_id = _nonnegative_integer(row.get("coverage_corridor_id"))
            if cell_id is None:
                raise ActRegressionPlanMatrixError(
                    f"line={line_number}:coverage_corridor_id_invalid"
                )
            current = {
                "cell_id": cell_id,
                "dig_cut_tokens": token,
            }
            previous = observed.get(cycle_index)
            if previous is None:
                observed[cycle_index] = current
                continue
            if previous["cell_id"] != cell_id or not _float_sequences_close(
                previous["dig_cut_tokens"],
                token,
            ):
                raise ActRegressionPlanMatrixError(
                    "a0_cycle_plan_not_stable:"
                    f"cycle_index={cycle_index}:line={line_number}"
                )

    missing = sorted(set(LOCKED_CYCLE_INDICES) - set(observed))
    if missing:
        raise ActRegressionPlanMatrixError(
            f"a0_rollout_missing_locked_cycle_plan:{missing}"
        )
    return observed


def _raw_fields_for_prior_cell(
    prior: Mapping[str, Any],
    cell_id: int,
) -> dict[str, float | int]:
    cells = prior.get("coverage_cells")
    if not _is_sequence(cells):
        raise ActRegressionPlanMatrixError("planner_prior_coverage_cells_invalid")
    matches = [
        cell
        for cell in cells
        if isinstance(cell, Mapping)
        and _nonnegative_integer(cell.get("cell_id")) == cell_id
    ]
    if len(matches) != 1:
        raise ActRegressionPlanMatrixError(
            f"planner_prior_cell_id_requires_one_match:{cell_id}:found={len(matches)}"
        )
    cell = matches[0]
    entry_x, entry_z = _x_z(cell.get("entry"), label=f"cell_{cell_id}.entry")
    exit_x, exit_z = _x_z(cell.get("exit"), label=f"cell_{cell_id}.exit")
    entry_x = _clamp_to_prior(prior, "entry_x_m", entry_x)
    entry_z = _clamp_to_prior(prior, "entry_z_m", entry_z)
    exit_x = _clamp_to_prior(prior, "exit_x_m", exit_x)
    exit_z = _clamp_to_prior(prior, "exit_z_m", exit_z)
    delta_x = exit_x - entry_x
    delta_z = exit_z - entry_z
    geometric_length = math.hypot(delta_x, delta_z)
    if geometric_length <= 1.0e-9:
        raise ActRegressionPlanMatrixError(
            f"planner_prior_cell_geometry_degenerate:{cell_id}"
        )
    direction_x = delta_x / geometric_length
    direction_z = delta_z / geometric_length
    return {
        "operator_entry_x_m": entry_x,
        "operator_entry_y_m": 0.0,
        "operator_entry_z_m": entry_z,
        "operator_exit_x_m": exit_x,
        "operator_exit_y_m": 0.0,
        "operator_exit_z_m": exit_z,
        "operator_cut_direction_x": _clamp_to_prior(
            prior,
            "cut_direction_x",
            direction_x,
        ),
        "operator_cut_direction_y": 0.0,
        "operator_cut_direction_z": _clamp_to_prior(
            prior,
            "cut_direction_z",
            direction_z,
        ),
        "operator_cut_length_m": _clamp_to_prior(
            prior,
            "cut_length_m",
            geometric_length,
        ),
        "operator_cut_depth_peak_m": _clamp_to_prior(
            prior,
            "cut_depth_peak_m",
            _finite_float(
                cell.get("cut_depth_peak_m"),
                label=f"cell_{cell_id}.cut_depth_peak_m",
            ),
        ),
        "operator_cut_payload_gain_kg": _clamp_to_prior(
            prior,
            "payload_gain_kg",
            _finite_float(
                cell.get("payload_gain_kg"),
                label=f"cell_{cell_id}.payload_gain_kg",
            ),
        ),
        "operator_effective_deposit_delta_kg": _clamp_to_prior(
            prior,
            "effective_deposit_delta_kg",
            _finite_float(
                cell.get("effective_deposit_delta_kg"),
                label=f"cell_{cell_id}.effective_deposit_delta_kg",
            ),
        ),
        "operator_cut_valid": 1,
    }


def _variant_source(
    baseline_source: Mapping[str, Any],
    *,
    depth_m: float | None = None,
    geometry_raw_fields: Mapping[str, float | int] | None = None,
) -> dict[str, Any]:
    source = copy.deepcopy(dict(baseline_source))
    plan = source["plans"][1]["plan"]
    raw_fields = plan["raw_fields"]
    if geometry_raw_fields is not None:
        for field in _GEOMETRY_RAW_FIELDS:
            raw_fields[field] = geometry_raw_fields[field]
    if depth_m is not None:
        raw_fields[_DEPTH_RAW_FIELD] = float(depth_m)
    plan["dig_cut_tokens"] = _token_from_raw_fields(raw_fields)
    return source


def _runtime_plan_record(
    *,
    cycle_index: int,
    raw_fields: Mapping[str, float | int],
    token: Sequence[float],
) -> dict[str, Any]:
    return {
        "cycle_index": cycle_index,
        "source": _FIXED_PLAN_SOURCE,
        "plan": {
            "status": "present",
            "source": _FIXED_PLAN_SOURCE,
            "raw_fields": dict(raw_fields),
            "dig_cut_tokens": [float(value) for value in token],
        },
    }


def _runtime_source_payload(
    plans: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": RESIDUAL_CUT_INTENT_RUNTIME_SOURCE_SCHEMA,
        "source": RESIDUAL_CUT_INTENT_RUNTIME_SOURCE,
        "status": "present",
        "offline_only": True,
        "diagnostic_only": True,
        "promotion_eligible": False,
        "profile": _FIXED_PROFILE,
        "plans": [copy.deepcopy(dict(plan)) for plan in plans],
        "plan_count": len(plans),
        "validation_errors": [],
    }


def _allowed_paths(condition: str) -> set[str]:
    paths: set[str] = set()
    if condition in {"D1", "DC1"}:
        paths.update(
            {
                f"plans[1].plan.raw_fields.{_DEPTH_RAW_FIELD}",
                "plans[1].plan.dig_cut_tokens[7]",
            }
        )
    if condition in {"C1", "DC1"}:
        paths.update(
            f"plans[1].plan.raw_fields.{field}" for field in _GEOMETRY_RAW_FIELDS
        )
        paths.update(f"plans[1].plan.dig_cut_tokens[{index}]" for index in range(6))
    return paths


def _validate_runtime_source_shape(
    payload: Mapping[str, Any],
    *,
    label: str,
) -> None:
    errors: list[str] = []
    if not isinstance(payload, Mapping):
        raise ActRegressionPlanMatrixError(f"{label}_runtime_source_must_be_mapping")
    if payload.get("schema") != RESIDUAL_CUT_INTENT_RUNTIME_SOURCE_SCHEMA:
        errors.append("schema")
    if payload.get("source") != RESIDUAL_CUT_INTENT_RUNTIME_SOURCE:
        errors.append("source")
    if payload.get("status") != "present":
        errors.append("status")
    plans = payload.get("plans")
    if not _is_sequence(plans) or len(plans) != 2:
        errors.append("plans")
    else:
        cycles: list[int | None] = []
        for index, record in enumerate(plans):
            if not isinstance(record, Mapping):
                errors.append(f"plans[{index}]")
                continue
            cycles.append(_nonnegative_integer(record.get("cycle_index")))
            plan = record.get("plan")
            if not isinstance(plan, Mapping):
                errors.append(f"plans[{index}].plan")
                continue
            if plan.get("status") != "present":
                errors.append(f"plans[{index}].plan.status")
            if not isinstance(plan.get("raw_fields"), Mapping):
                errors.append(f"plans[{index}].plan.raw_fields")
            try:
                _finite_float_sequence(
                    plan.get("dig_cut_tokens"),
                    expected_length=DIG_CUT_TOKEN_DIM,
                    label=f"plans[{index}].plan.dig_cut_tokens",
                )
            except ActRegressionPlanMatrixError:
                errors.append(f"plans[{index}].plan.dig_cut_tokens")
        if cycles != list(LOCKED_CYCLE_INDICES):
            errors.append(f"cycle_indices:{cycles}")
    if errors:
        raise ActRegressionPlanMatrixError(f"{label}_runtime_source_invalid:{errors}")


def _changed_leaf_paths(
    left: Any,
    right: Any,
    *,
    path: str = "",
) -> set[str]:
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        paths: set[str] = set()
        keys = set(left) | set(right)
        for key in keys:
            child_path = f"{path}.{key}" if path else str(key)
            if key not in left or key not in right:
                paths.add(child_path)
                continue
            paths.update(
                _changed_leaf_paths(
                    left[key],
                    right[key],
                    path=child_path,
                )
            )
        return paths
    if _is_sequence(left) and _is_sequence(right):
        paths = set()
        common = min(len(left), len(right))
        for index in range(common):
            child_path = f"{path}[{index}]"
            paths.update(
                _changed_leaf_paths(
                    left[index],
                    right[index],
                    path=child_path,
                )
            )
        for index in range(common, max(len(left), len(right))):
            paths.add(f"{path}[{index}]")
        return paths
    return set() if left == right else {path}


def _token_from_raw_fields(
    raw_fields: Mapping[str, float | int],
) -> list[float]:
    plan = DigCutTokenPlanner(prior={}).plan_from_raw_fields(
        dict(raw_fields),
        source=_FIXED_PLAN_SOURCE,
    )
    return [float(value) for value in plan.token.tolist()]


def _assert_token_matches_observation(
    *,
    cycle_index: int,
    expected_token: Sequence[float],
    observed_token: Sequence[float],
) -> None:
    if not _float_sequences_close(
        expected_token,
        observed_token,
        absolute_tolerance=1.0e-6,
    ):
        raise ActRegressionPlanMatrixError(
            "a0_artifact_plan_does_not_match_reconstructed_prior:"
            f"cycle_index={cycle_index}:"
            f"expected={list(expected_token)}:"
            f"observed={list(observed_token)}"
        )


def _float_sequences_close(
    left: Sequence[float],
    right: Sequence[float],
    *,
    absolute_tolerance: float = 1.0e-9,
) -> bool:
    return len(left) == len(right) and all(
        math.isclose(
            float(left_value),
            float(right_value),
            rel_tol=0.0,
            abs_tol=absolute_tolerance,
        )
        for left_value, right_value in zip(left, right, strict=True)
    )


def _clamp_to_prior(
    prior: Mapping[str, Any],
    field_name: str,
    value: float,
) -> float:
    lower = _prior_percentile(prior, field_name, "p10")
    upper = _prior_percentile(prior, field_name, "p90")
    if lower > upper:
        raise ActRegressionPlanMatrixError(
            f"planner_prior_percentile_order_invalid:{field_name}"
        )
    return max(lower, min(upper, float(value)))


def _prior_percentile(
    prior: Mapping[str, Any],
    field_name: str,
    percentile: str,
) -> float:
    fields = prior.get("fields")
    if not isinstance(fields, Mapping):
        raise ActRegressionPlanMatrixError("planner_prior_fields_invalid")
    field = fields.get(field_name)
    if not isinstance(field, Mapping):
        raise ActRegressionPlanMatrixError(f"planner_prior_field_missing:{field_name}")
    return _finite_float(
        field.get(percentile),
        label=f"fields.{field_name}.{percentile}",
    )


def _x_z(value: Any, *, label: str) -> tuple[float, float]:
    if not isinstance(value, Mapping):
        raise ActRegressionPlanMatrixError(f"{label}_must_be_mapping")
    return (
        _finite_float(value.get("x_m"), label=f"{label}.x_m"),
        _finite_float(value.get("z_m"), label=f"{label}.z_m"),
    )


def _finite_float(value: Any, *, label: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ActRegressionPlanMatrixError(f"{label}_must_be_finite") from exc
    if not math.isfinite(parsed):
        raise ActRegressionPlanMatrixError(f"{label}_must_be_finite")
    return parsed


def _finite_float_sequence(
    value: Any,
    *,
    expected_length: int,
    label: str,
) -> list[float]:
    if not _is_sequence(value) or len(value) != expected_length:
        raise ActRegressionPlanMatrixError(
            f"{label}_must_have_length_{expected_length}"
        )
    return [
        _finite_float(item, label=f"{label}[{index}]")
        for index, item in enumerate(value)
    ]


def _nonnegative_integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed < 0.0:
        return None
    integer = int(parsed)
    if not math.isclose(parsed, float(integer), rel_tol=0.0, abs_tol=1.0e-9):
        return None
    return integer


def _read_json_mapping(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ActRegressionPlanMatrixError(
            f"{label}_json_decode_failed:{path}:{exc.msg}"
        ) from exc
    if not isinstance(payload, Mapping):
        raise ActRegressionPlanMatrixError(f"{label}_must_be_json_object:{path}")
    return payload


def _is_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_text(payload: Mapping[str, Any]) -> str:
    return (
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    )


__all__ = [
    "ACT_REGRESSION_PLAN_MATRIX_SCHEMA",
    "CONDITION_ORDER",
    "ActRegressionPlanMatrixError",
    "assert_allowed_condition_diff",
    "build_act_regression_plan_matrix",
]
