"""Public planner-trace report assembly for the primitive planner."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from testbed.data.operator_first_v2_2 import DIG_CUT_TOKEN_CONTRACT
from testbed.planner.primitive_coverage_reports import CoverageTraceReportStatus


DIG_CUT_TOKEN_CONTRACT_TEXT = (
    "entry_x,entry_z,exit_x,exit_z,dir_x,dir_z,"
    "length,cut_depth_semantic,payload,valid"
)
RETURN_TARGET_TOKEN_CONTRACT_TEXT = (
    "next entry_x,entry_z,exit_x,exit_z,dir_x,dir_z,"
    "length,cut_depth_semantic,payload,valid"
)
RETURN_START_ENVELOPE_TOKEN_CONTRACT_VERSION = "return_start_envelope_tokens_v1"
RETURN_START_ENVELOPE_TOKEN_CONTRACT_TEXT = (
    "dig-grid long_norm,short_norm,depth_center,tip_radius,"
    "depth_min,depth_max,contact_allowed,qpos_center[4],"
    "qpos_half_width[4],qvel_abs_max,valid,no_dump_contact_required"
)


@dataclass(frozen=True)
class PrimitivePlannerTraceInputs:
    """Snapshot values required to assemble the public planner trace."""

    cell_entry_trace: Sequence[Any]
    dig_cut_planner_mode: str
    dig_cut_prior_id: str
    dig_cut_prior_path: str
    return_target_planner_enabled: bool
    coverage: CoverageTraceReportStatus


@dataclass(frozen=True)
class PrimitivePlannerTraceBuilder:
    """Build the public primitive planner trace payload."""

    def build(self, inputs: PrimitivePlannerTraceInputs) -> dict[str, object]:
        return {
            "cell_entry_trace": list(inputs.cell_entry_trace),
            "dig_cut_token_contract_version": DIG_CUT_TOKEN_CONTRACT,
            "dig_cut_token_contract": DIG_CUT_TOKEN_CONTRACT_TEXT,
            "dig_cut_planner_mode": str(inputs.dig_cut_planner_mode),
            "dig_cut_prior_id": str(inputs.dig_cut_prior_id),
            "dig_cut_prior_path": str(inputs.dig_cut_prior_path),
            "return_target_token_contract_version": DIG_CUT_TOKEN_CONTRACT,
            "return_target_token_contract": RETURN_TARGET_TOKEN_CONTRACT_TEXT,
            "return_start_envelope_token_contract_version": (
                RETURN_START_ENVELOPE_TOKEN_CONTRACT_VERSION
            ),
            "return_start_envelope_token_contract": (
                RETURN_START_ENVELOPE_TOKEN_CONTRACT_TEXT
            ),
            "return_target_planner_enabled": bool(
                inputs.return_target_planner_enabled
            ),
            "coverage_use_env_removed_depth": bool(
                inputs.coverage.use_env_removed_depth
            ),
            "coverage_candidate_layout": str(inputs.coverage.candidate_layout),
            "coverage_first_dig_strategy": str(
                inputs.coverage.first_dig_strategy
            ),
            "coverage_pass_index": int(inputs.coverage.pass_index),
            "coverage_multi_pass_enabled": bool(
                inputs.coverage.multi_pass_enabled
            ),
            "coverage_multi_pass_max_passes": int(
                inputs.coverage.multi_pass_max_passes
            ),
            "coverage_multi_pass_min_remaining_depth_m": float(
                inputs.coverage.multi_pass_min_remaining_depth_m
            ),
            "coverage_first_dig_preferred_corridor_id": int(
                -1
                if inputs.coverage.first_dig_preferred_corridor_id is None
                else inputs.coverage.first_dig_preferred_corridor_id
            ),
            "coverage_corridors": list(inputs.coverage.corridors),
            "coverage_decision_trace": list(inputs.coverage.decision_trace),
            "coverage_decision_trace_count": int(
                len(inputs.coverage.decision_trace)
            ),
            "coverage_terminal_stop_requested": bool(
                inputs.coverage.terminal_stop_requested
            ),
            "coverage_terminal_stop_reason": str(
                inputs.coverage.terminal_stop_reason
            ),
        }


__all__ = [
    "DIG_CUT_TOKEN_CONTRACT_TEXT",
    "PrimitivePlannerTraceBuilder",
    "PrimitivePlannerTraceInputs",
    "RETURN_START_ENVELOPE_TOKEN_CONTRACT_TEXT",
    "RETURN_START_ENVELOPE_TOKEN_CONTRACT_VERSION",
    "RETURN_TARGET_TOKEN_CONTRACT_TEXT",
]
