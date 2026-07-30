"""Artifact-backed planner golden-window parity checks.

This module intentionally reads recorded rollout artifacts only. It does not
instantiate the planner, Unity, or low-level ACT policies.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class PlannerGoldenWindowMismatch(AssertionError):
    """Raised when a recorded planner artifact no longer matches the contract."""


@dataclass(frozen=True)
class PlannerArtifactPaths:
    rollout_jsonl: Path
    planner_trace: Path
    rollout_summary: Path
    resolved_config: Path

    def at_root(self, root: Path) -> PlannerArtifactPaths:
        return PlannerArtifactPaths(
            rollout_jsonl=_at_root(root, self.rollout_jsonl),
            planner_trace=_at_root(root, self.planner_trace),
            rollout_summary=_at_root(root, self.rollout_summary),
            resolved_config=_at_root(root, self.resolved_config),
        )


@dataclass(frozen=True)
class FullReplayAudit:
    feasible: bool
    parity_level: str
    available_inputs: tuple[str, ...]
    missing_inputs: tuple[str, ...]


@dataclass(frozen=True)
class GoldenWindowContract:
    expected_skill_switches: tuple[tuple[int, int, int, str | None, str, int, str], ...]
    expected_window_count: int
    expected_window_digest: str
    expected_trace_contracts: Mapping[str, Any]
    expected_summary_metrics: Mapping[str, Any]
    expected_config_contract: Mapping[str, Any]
    field_names: tuple[str, ...]
    float_abs_tol: float = 1e-9
    float_rel_tol: float = 1e-9


@dataclass(frozen=True)
class GoldenWindowReport:
    window_count: int
    field_count: int
    window_digest: str
    trace_contracts: Mapping[str, Any]
    summary_metrics: Mapping[str, Any]
    config_contract: Mapping[str, Any]


AGGREGATE_TX24_ARTIFACTS = PlannerArtifactPaths(
    rollout_jsonl=Path(
        "runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/"
        "rollouts/rollout_000.jsonl"
    ),
    planner_trace=Path(
        "runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/"
        "rollouts/rollout_000_planner_trace.json"
    ),
    rollout_summary=Path(
        "runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/"
        "rollouts/rollout_000_summary.json"
    ),
    resolved_config=Path(
        "runs/eval/planner_compare_20260616_x99/aggregate_tx24/results/"
        "eval_resolved_config.yaml"
    ),
)

AGGREGATE_TX24_PORTABLE_ARTIFACTS = PlannerArtifactPaths(
    rollout_jsonl=Path(
        "tests/fixtures/planner_current_code_parity/rollout_000.jsonl.gz"
    ),
    planner_trace=Path(
        "tests/fixtures/planner_current_code_parity/"
        "rollout_000_planner_trace.json"
    ),
    rollout_summary=Path(
        "tests/fixtures/planner_current_code_parity/rollout_000_summary.json"
    ),
    resolved_config=Path(
        "tests/fixtures/planner_current_code_parity/eval_resolved_config.yaml"
    ),
)


GOLDEN_WINDOW_FIELDS = (
    "rollout_id",
    "step_id",
    "t",
    "sim_time_ns",
    "skill_name",
    "skill_id",
    "skill_switch_reason",
    "goal_tokens",
    "dig_cut_token_injected",
    "dig_cut_token_source",
    "dig_cut_tokens",
    "dig_cut_planner_mode",
    "dig_cut_prior_id",
    "dig_depth_profile_token_injected",
    "dig_depth_profile_token_source",
    "dig_depth_profile_fallback_reason",
    "dig_depth_profile_tokens",
    "return_target_token_injected",
    "return_target_token_source",
    "return_target_tokens",
    "return_relocate_token_injected",
    "return_relocate_token_source",
    "return_relocate_tokens",
    "return_start_envelope_token_injected",
    "return_start_envelope_token_source",
    "return_start_envelope_tokens",
    "dig_to_carry_reason",
    "dig_step_count",
    "dig_best_mass_kg",
    "dig_mass_plateau_count",
    "dig_bad_replan_count",
    "dig_exit_guard_replan_count",
    "dump_ready_hold_count",
    "dump_done_hold_count",
    "transition_completed",
    "transition_timeout",
    "transition_source",
    "transition_policy_mode",
    "transition_fallback_count",
    "transition_fallback_reason",
    "boundary_mask",
    "dump_start_mask",
    "dump_end_mask",
    "return_to_dig_entry_close",
    "return_to_dig_entry_error_m",
    "return_to_dig_start_envelope_gate_enabled",
    "return_to_dig_start_envelope_ready",
    "return_to_dig_start_envelope_error",
    "return_to_dig_start_envelope_checks",
    "wait_next_dig_steps",
    "coverage_corridor_id",
    "coverage_corridor_score",
    "coverage_depleted_count",
    "coverage_terminal_stop_requested",
    "coverage_terminal_stop_reason",
    "coverage_global_low_productivity_streak",
    "coverage_last_payload_gain_kg",
    "coverage_last_effective_deposit_delta_kg",
    "pre_dig_align_enabled",
    "pre_dig_align_completed_count",
    "pre_dig_align_timeout_count",
    "pre_dig_align_replan_count",
    "pre_dig_align_active_for_next_dig",
    "cell_entry_token_injected",
    "cell_entry_seen_cell_id",
    "cell_entry_selected_cell_id",
    "cell_entry_audit_reason",
    "primitive_checkpoint_path",
    "primitive_cycle_index",
    "primitive_goal_curr_sector_id",
    "primitive_goal_next_sector_id",
    "task_success",
    "reward",
    "reward_phase",
    "task_metrics",
)


AGGREGATE_TX24_SKILL_SWITCHES = (
    (0, 1, 0, None, "bootstrap", -1, ""),
    (267, 268, 267, "bootstrap", "dig", 0, "bootstrap_to_dig"),
    (417, 418, 417, "dig", "carry", 1, "dig_to_carry_dig_complete_boundary"),
    (571, 572, 571, "carry", "dump", 2, "carry_to_dump_dump_committed_boundary"),
    (751, 752, 751, "dump", "return", 3, "dump_to_return_dump_complete_boundary"),
    (1004, 1005, 1004, "return", "dig", 0, "return_to_dig_start_envelope_ready"),
    (1045, 1046, 1045, "dig", "carry", 1, "dig_to_carry_semantic_material_loaded"),
    (1242, 1243, 1242, "carry", "dump", 2, "carry_to_dump_dump_committed_boundary"),
    (1401, 1402, 1401, "dump", "return", 3, "dump_to_return_dump_complete_boundary"),
    (1596, 1597, 1596, "return", "dig", 0, "return_to_dig_next_dig_entry_ready"),
    (1638, 1639, 1638, "dig", "carry", 1, "dig_to_carry_semantic_material_loaded"),
    (1865, 1866, 1865, "carry", "dump", 2, "carry_to_dump_dump_committed_boundary"),
    (2007, 2008, 2007, "dump", "return", 3, "dump_to_return_dump_complete_boundary"),
    (2221, 2222, 2221, "return", "dig", 0, "return_to_dig_next_dig_entry_ready"),
    (2261, 2262, 2261, "dig", "carry", 1, "dig_to_carry_semantic_material_loaded"),
    (2427, 2428, 2427, "carry", "dump", 2, "carry_to_dump_dump_committed_boundary"),
    (2554, 2555, 2554, "dump", "return", 3, "dump_to_return_dump_complete_boundary"),
    (2767, 2768, 2767, "return", "dig", 0, "return_to_dig_start_envelope_ready"),
    (2796, 2797, 2796, "dig", "carry", 1, "dig_to_carry_semantic_material_loaded"),
    (3026, 3027, 3026, "carry", "dump", 2, "carry_to_dump_dump_committed_boundary"),
    (3167, 3168, 3167, "dump", "return", 3, "dump_to_return_dump_complete_boundary"),
    (3365, 3366, 3365, "return", "dig", 0, "return_to_dig_next_dig_entry_ready"),
    (3408, 3409, 3408, "dig", "carry", 1, "dig_to_carry_semantic_material_loaded"),
    (3616, 3617, 3616, "carry", "dump", 2, "carry_to_dump_dump_committed_boundary"),
    (3756, 3757, 3756, "dump", "return", 3, "dump_to_return_dump_complete_boundary"),
    (3972, 3973, 3972, "return", "dig", 0, "return_to_dig_next_dig_entry_ready"),
    (4028, 4029, 4028, "dig", "carry", 1, "dig_to_carry_semantic_material_loaded"),
    (4199, 4200, 4199, "carry", "dump", 2, "carry_to_dump_dump_committed_boundary"),
    (4341, 4342, 4341, "dump", "return", 3, "dump_to_return_dump_complete_boundary"),
    (4578, 4579, 4578, "return", "dig", 0, "return_to_dig_next_dig_entry_ready"),
    (4642, 4643, 4642, "dig", "carry", 1, "dig_to_carry_semantic_material_loaded"),
    (4835, 4836, 4835, "carry", "dump", 2, "carry_to_dump_dump_committed_boundary"),
    (4974, 4975, 4974, "dump", "return", 3, "dump_to_return_dump_complete_boundary"),
    (5207, 5208, 5207, "return", "dig", 0, "return_to_dig_next_dig_entry_ready"),
    (5262, 5263, 5262, "dig", "carry", 1, "dig_to_carry_semantic_material_loaded"),
    (5452, 5453, 5452, "carry", "dump", 2, "carry_to_dump_dump_committed_boundary"),
    (5583, 5584, 5583, "dump", "return", 3, "dump_to_return_dump_complete_boundary"),
)


AGGREGATE_TX24_CONTRACT = GoldenWindowContract(
    expected_skill_switches=AGGREGATE_TX24_SKILL_SWITCHES,
    expected_window_count=112,
    expected_window_digest="71027afbf23c2f0080eda13fbd1d7b07566c17e9097c747374374caa19cbe8b5",
    expected_trace_contracts={
        "dig_cut_token_contract_version": "v2_4_removed_depth_cut_v3",
        "return_target_token_contract_version": "v2_4_removed_depth_cut_v3",
        "return_start_envelope_token_contract_version": "return_start_envelope_tokens_v1",
        "coverage_decision_trace_count": 20,
        "cell_entry_trace_count": 0,
        "coverage_terminal_stop_requested": True,
        "coverage_terminal_stop_reason": "dig_area_depleted",
    },
    expected_summary_metrics={
        "episode_len": 5584,
        "episode_return": 19296.0,
        "legacy_success": True,
        "final_hold_success": True,
        "first_task_success_step": 760,
        "completed_transition_count": 8,
        "completed_dump_count": 9,
        "coverage_terminal_stop_requested": 1,
        "coverage_terminal_stop_reason": "dig_area_depleted",
        "coverage_depleted_count": 6,
        "coverage_selected_corridor_id": 0,
        "cell_entry_enabled": 0,
        "cell_entry_trace_count": 0,
        "pre_dig_align_enabled": 0,
        "pre_dig_align_completed_count": 0,
        "transition_timeout_count": 0,
        "dig_bad_replan_count": 0,
        "dig_exit_guard_replan_count": 0,
        "rollout_stop_reason": "dig_area_depleted",
    },
    expected_config_contract={
        "policy.pre_dig_align.enabled": False,
        "policy.cell_entry": "<missing>",
        "policy.cell_entry_enabled": "<missing>",
        "policy.dig_low_dim_keys": ["qpos", "qvel", "dig_cut_tokens"],
        "policy.return_low_dim_keys": [
            "qpos",
            "qvel",
            "return_start_envelope_tokens_v1",
            "return_relocate_tokens_v1",
        ],
    },
    field_names=GOLDEN_WINDOW_FIELDS,
)


def read_jsonl_rows(path: Path) -> tuple[dict[str, Any], ...]:
    open_text = gzip.open if path.suffix == ".gz" else Path.open
    with open_text(path, "rt", encoding="utf-8") as stream:
        return tuple(json.loads(line) for line in stream if line.strip())


def skill_switches(rows: Sequence[Mapping[str, Any]]) -> tuple[
    tuple[int, int, int, str | None, str, int, str], ...
]:
    switches: list[tuple[int, int, int, str | None, str, int, str]] = []
    for index, row in enumerate(rows):
        skill_name = str(row["skill_name"])
        previous_skill = None if index == 0 else str(rows[index - 1]["skill_name"])
        if index == 0 or skill_name != previous_skill:
            switches.append(
                (
                    index,
                    int(row["step_id"]),
                    int(row["t"]),
                    previous_skill,
                    skill_name,
                    int(row["skill_id"]),
                    str(row.get("skill_switch_reason", "")),
                )
            )
    return tuple(switches)


def select_golden_window_indices(rows: Sequence[Mapping[str, Any]]) -> tuple[int, ...]:
    indices: set[int] = {0}
    for switch_index, *_ in skill_switches(rows):
        for index in (switch_index - 1, switch_index, switch_index + 1):
            if 0 <= index < len(rows):
                indices.add(index)

    terminal_index = _first_index(rows, "coverage_terminal_stop_requested", True)
    if terminal_index is not None:
        for index in (terminal_index - 1, terminal_index):
            if 0 <= index < len(rows):
                indices.add(index)

    success_index = _first_index(rows, "task_success", True)
    if success_index is not None:
        for index in (success_index - 1, success_index, success_index + 1):
            if 0 <= index < len(rows):
                indices.add(index)

    return tuple(sorted(indices))


def audit_full_replay_inputs(paths: PlannerArtifactPaths) -> FullReplayAudit:
    rows = read_jsonl_rows(paths.rollout_jsonl)
    observed_keys = set().union(*(row.keys() for row in rows[: min(len(rows), 10)]))
    image_keys = {
        key
        for key in observed_keys
        if "image" in key.lower() or "camera" in key.lower() or "rgb" in key.lower()
    }
    missing_inputs = [
        "camera image observations or image frame paths",
        "embedded checkpoint weights and normalization/runtime policy state",
        "Unity/env simulator snapshot and planner private mutable state",
    ]
    if image_keys:
        missing_inputs.remove("camera image observations or image frame paths")
    return FullReplayAudit(
        feasible=False,
        parity_level="artifact-golden-window-contract",
        available_inputs=(
            "per-step qpos/qvel/env_state/action/debug rows",
            "planner_trace contract and coverage trace summary",
            "rollout_summary aggregate metrics",
            "resolved eval config",
        ),
        missing_inputs=tuple(missing_inputs),
    )


def assert_golden_window_contract(
    paths: PlannerArtifactPaths,
    contract: GoldenWindowContract,
) -> GoldenWindowReport:
    rows = read_jsonl_rows(paths.rollout_jsonl)
    actual_switches = skill_switches(rows)
    _assert_close(contract.expected_skill_switches, actual_switches, "skill_switches", contract)

    window_indices = select_golden_window_indices(rows)
    if len(window_indices) != contract.expected_window_count:
        raise PlannerGoldenWindowMismatch(
            f"expected {contract.expected_window_count} golden windows, got {len(window_indices)}"
        )

    snapshot = build_window_snapshot(rows, window_indices, contract.field_names)
    digest = window_snapshot_digest(snapshot)
    if digest != contract.expected_window_digest:
        raise PlannerGoldenWindowMismatch(
            f"golden-window digest mismatch: expected {contract.expected_window_digest}, got {digest}"
        )

    trace_contracts = read_trace_contracts(paths.planner_trace)
    summary_metrics = read_summary_metrics(paths.rollout_summary, contract.expected_summary_metrics)
    config_contract = read_config_contract(paths.resolved_config, contract.expected_config_contract)

    _assert_close(contract.expected_trace_contracts, trace_contracts, "trace_contracts", contract)
    _assert_close(contract.expected_summary_metrics, summary_metrics, "summary_metrics", contract)
    _assert_close(contract.expected_config_contract, config_contract, "config_contract", contract)

    return GoldenWindowReport(
        window_count=len(window_indices),
        field_count=len(contract.field_names),
        window_digest=digest,
        trace_contracts=trace_contracts,
        summary_metrics=summary_metrics,
        config_contract=config_contract,
    )


def build_window_snapshot(
    rows: Sequence[Mapping[str, Any]],
    indices: Sequence[int],
    field_names: Sequence[str],
) -> tuple[dict[str, Any], ...]:
    snapshot: list[dict[str, Any]] = []
    for index in indices:
        row = rows[index]
        item: dict[str, Any] = {"index": index}
        for field_name in field_names:
            if field_name not in row:
                raise PlannerGoldenWindowMismatch(f"missing rollout field at row {index}: {field_name}")
            item[field_name] = _canonicalize(row[field_name])
        snapshot.append(item)
    return tuple(snapshot)


def window_snapshot_digest(snapshot: Sequence[Mapping[str, Any]]) -> str:
    blob = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def read_trace_contracts(path: Path) -> dict[str, Any]:
    trace = json.loads(path.read_text(encoding="utf-8"))
    return {
        "dig_cut_token_contract_version": trace.get("dig_cut_token_contract_version"),
        "return_target_token_contract_version": trace.get("return_target_token_contract_version"),
        "return_start_envelope_token_contract_version": trace.get(
            "return_start_envelope_token_contract_version"
        ),
        "coverage_decision_trace_count": int(trace.get("coverage_decision_trace_count", 0)),
        "cell_entry_trace_count": len(trace.get("cell_entry_trace") or ()),
        "coverage_terminal_stop_requested": bool(trace.get("coverage_terminal_stop_requested")),
        "coverage_terminal_stop_reason": trace.get("coverage_terminal_stop_reason", ""),
    }


def read_summary_metrics(path: Path, expected: Mapping[str, Any]) -> dict[str, Any]:
    summary = json.loads(path.read_text(encoding="utf-8"))
    return {key: summary.get(key) for key in expected}


def read_config_contract(path: Path, expected: Mapping[str, Any]) -> dict[str, Any]:
    import yaml

    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {key: _get_dotted(config, key) for key in expected}


def _assert_close(
    expected: Any,
    actual: Any,
    path: str,
    contract: GoldenWindowContract,
) -> None:
    if isinstance(expected, float) or isinstance(actual, float):
        _assert_float_close(float(expected), float(actual), path, contract)
        return
    if isinstance(expected, Mapping):
        if not isinstance(actual, Mapping):
            raise PlannerGoldenWindowMismatch(f"{path}: expected mapping, got {type(actual).__name__}")
        if set(expected) != set(actual):
            raise PlannerGoldenWindowMismatch(
                f"{path}: expected keys {sorted(expected)}, got {sorted(actual)}"
            )
        for key in expected:
            _assert_close(expected[key], actual[key], f"{path}.{key}", contract)
        return
    if isinstance(expected, Sequence) and not isinstance(expected, (str, bytes, bytearray)):
        if not isinstance(actual, Sequence) or isinstance(actual, (str, bytes, bytearray)):
            raise PlannerGoldenWindowMismatch(f"{path}: expected sequence, got {type(actual).__name__}")
        if len(expected) != len(actual):
            raise PlannerGoldenWindowMismatch(f"{path}: expected length {len(expected)}, got {len(actual)}")
        for index, (expected_item, actual_item) in enumerate(zip(expected, actual, strict=True)):
            _assert_close(expected_item, actual_item, f"{path}[{index}]", contract)
        return
    if expected != actual:
        raise PlannerGoldenWindowMismatch(f"{path}: expected {expected!r}, got {actual!r}")


def _assert_float_close(
    expected: float,
    actual: float,
    path: str,
    contract: GoldenWindowContract,
) -> None:
    if math.isnan(expected) or math.isnan(actual):
        if math.isnan(expected) and math.isnan(actual):
            return
        raise PlannerGoldenWindowMismatch(f"{path}: expected {expected!r}, got {actual!r}")
    if not math.isclose(
        expected,
        actual,
        rel_tol=contract.float_rel_tol,
        abs_tol=contract.float_abs_tol,
    ):
        raise PlannerGoldenWindowMismatch(f"{path}: expected {expected!r}, got {actual!r}")


def _canonicalize(value: Any) -> Any:
    if isinstance(value, float):
        if math.isnan(value):
            return {"__float__": "nan"}
        if math.isinf(value):
            return {"__float__": "inf" if value > 0 else "-inf"}
        return round(value, 9)
    if isinstance(value, list):
        return [_canonicalize(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_canonicalize(item) for item in value)
    if isinstance(value, dict):
        return {str(key): _canonicalize(value[key]) for key in sorted(value)}
    return value


def _first_index(rows: Sequence[Mapping[str, Any]], field_name: str, value: Any) -> int | None:
    for index, row in enumerate(rows):
        if row.get(field_name) == value:
            return index
    return None


def _at_root(root: Path, path: Path) -> Path:
    return path if path.is_absolute() else root / path


def _get_dotted(config: Mapping[str, Any], dotted_key: str) -> Any:
    value: Any = config
    for part in dotted_key.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return "<missing>"
        value = value[part]
    return value
