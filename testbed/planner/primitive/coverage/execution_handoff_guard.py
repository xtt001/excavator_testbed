"""Final live-start safety guard for an atomically locked coverage tuple."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.coverage.worktool_sweep import (
    WORKTOOL_3D_GEOMETRY_MISSING,
    CoverageWorktoolSweepConfig,
    CoverageWorktoolSweepService,
)

EXACT_TUPLE_HANDOFF_CONTRACT_MISSING = (
    "exact_tuple_handoff_contract_missing"
)
EXACT_RETURN_START_ENVELOPE_TIMEOUT = (
    "exact_return_start_envelope_timeout"
)


@dataclass(frozen=True)
class CoverageExecutionHandoffGuardResult:
    """One final live-handoff decision made before dig ACT inference."""

    required: bool
    eligible: bool
    rejection_reason: str
    trace: dict[str, Any]


@dataclass(frozen=True)
class CoverageExecutionHandoffGuardService:
    """Re-evaluate the locked tuple's 3D sweep from the actual handoff qpos."""

    state: CoverageRuntimeState
    worktool_config: CoverageWorktoolSweepConfig
    worktool_sweep_service: Any = None

    @staticmethod
    def exact_envelope_timeout_reason(
        *,
        skill_name: str,
        exact_contract_required: bool,
        return_step_count: int,
        return_max_steps: int,
    ) -> str | None:
        """Return a specific fail-closed reason only for exact returns."""

        if (
            str(skill_name) == "return"
            and bool(exact_contract_required)
            and int(return_max_steps) > 0
            and int(return_step_count) >= int(return_max_steps)
        ):
            return EXACT_RETURN_START_ENVELOPE_TIMEOUT
        return None

    def evaluate(
        self,
        live_handoff_qpos: Any,
        *,
        exact_contract_required: bool | None = None,
        pending_exemplar_id: str | None = None,
        pending_raw_fields_sha256: str | None = None,
        pending_paired_return_primitive_episode_id: int | None = None,
        pending_return_transition_artifact_sha256: str | None = None,
    ) -> CoverageExecutionHandoffGuardResult:
        contract = self.state.coverage_active_execution_contract
        required = bool(
            contract is not None
            and contract.exact_start_contract_required
            if exact_contract_required is None
            else exact_contract_required
        )
        if not required:
            return self._store(
                CoverageExecutionHandoffGuardResult(
                    required=False,
                    eligible=True,
                    rejection_reason="",
                    trace={
                        "worktool_sweep_3d_evaluation_phase": (
                            "final_live_handoff_not_required"
                        )
                    },
                )
            )
        if (
            contract is None
            or not contract.exact_start_contract_required
            or not self.worktool_config.enabled
            or not self._pending_contract_matches(
                pending_exemplar_id=pending_exemplar_id,
                pending_raw_fields_sha256=pending_raw_fields_sha256,
                pending_paired_return_primitive_episode_id=(
                    pending_paired_return_primitive_episode_id
                ),
                pending_return_transition_artifact_sha256=(
                    pending_return_transition_artifact_sha256
                ),
            )
        ):
            return self._store(
                CoverageExecutionHandoffGuardResult(
                    required=True,
                    eligible=False,
                    rejection_reason=EXACT_TUPLE_HANDOFF_CONTRACT_MISSING,
                    trace={
                        "worktool_sweep_3d_evaluation_phase": (
                            "final_live_handoff"
                        ),
                        "worktool_sweep_3d_eligible": 0,
                        "worktool_sweep_3d_rejection_reason": (
                            EXACT_TUPLE_HANDOFF_CONTRACT_MISSING
                        ),
                    },
                )
            )
        service = self.worktool_sweep_service
        if service is None:
            try:
                service = CoverageWorktoolSweepService.from_config(
                    self.worktool_config
                )
            except Exception:
                return self._store(
                    CoverageExecutionHandoffGuardResult(
                        required=True,
                        eligible=False,
                        rejection_reason=WORKTOOL_3D_GEOMETRY_MISSING,
                        trace={
                            "worktool_sweep_3d_evaluation_phase": (
                                "final_live_handoff"
                            ),
                            "worktool_sweep_3d_eligible": 0,
                            "worktool_sweep_3d_rejection_reason": (
                                WORKTOOL_3D_GEOMETRY_MISSING
                            ),
                        },
                    )
                )
        evaluation = service.evaluate(
            exemplar_id=str(contract.exemplar_id),
            raw_fields_sha256=str(contract.raw_fields_sha256),
            live_start_qpos=live_handoff_qpos,
        )
        trace = {
            **evaluation.as_trace_fields(),
            "worktool_sweep_3d_evaluation_phase": "final_live_handoff",
        }
        return self._store(
            CoverageExecutionHandoffGuardResult(
                required=True,
                eligible=bool(evaluation.eligible),
                rejection_reason=str(evaluation.rejection_reason),
                trace=trace,
            )
        )

    def _pending_contract_matches(
        self,
        *,
        pending_exemplar_id: str | None,
        pending_raw_fields_sha256: str | None,
        pending_paired_return_primitive_episode_id: int | None,
        pending_return_transition_artifact_sha256: str | None,
    ) -> bool:
        """Require all supplied pending identities to match the active tuple."""

        contract = self.state.coverage_active_execution_contract
        if contract is None:
            return False
        transition = contract.start_reachability_evaluation
        if transition is None:
            return False
        checks = (
            (
                pending_exemplar_id,
                str(contract.exemplar_id),
            ),
            (
                pending_raw_fields_sha256,
                str(contract.raw_fields_sha256),
            ),
            (
                pending_paired_return_primitive_episode_id,
                int(
                    getattr(
                        transition,
                        "paired_return_primitive_episode_id",
                        -1,
                    )
                ),
            ),
            (
                pending_return_transition_artifact_sha256,
                str(getattr(transition, "artifact_sha256", "")),
            ),
        )
        return all(
            supplied is None or supplied == expected
            for supplied, expected in checks
        )

    def _store(
        self,
        result: CoverageExecutionHandoffGuardResult,
    ) -> CoverageExecutionHandoffGuardResult:
        self.state.coverage_final_live_handoff_guard_result = result
        if self.state.coverage_active_execution_contract is not None:
            self.state.coverage_active_execution_trace.update(result.trace)
        return result


__all__ = [
    "EXACT_RETURN_START_ENVELOPE_TIMEOUT",
    "EXACT_TUPLE_HANDOFF_CONTRACT_MISSING",
    "CoverageExecutionHandoffGuardResult",
    "CoverageExecutionHandoffGuardService",
]
