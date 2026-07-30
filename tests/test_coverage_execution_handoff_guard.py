from __future__ import annotations

from typing import Any

import numpy as np

from testbed.planner.primitive.coverage.execution_handoff_guard import (
    CoverageExecutionHandoffGuardService,
)
from testbed.planner.primitive.coverage.start_reachability import (
    CoverageTupleStartReachabilityEvaluation,
)
from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.coverage.worktool_sweep import (
    CoverageWorktoolSweepConfig,
    CoverageWorktoolSweepEvaluation,
)


class _Sweep:
    def __init__(self, *, eligible: bool = True) -> None:
        self.eligible = eligible
        self.qpos: list[tuple[float, ...]] = []

    def evaluate(
        self,
        *,
        exemplar_id: str,
        raw_fields_sha256: str,
        live_start_qpos: Any,
    ) -> CoverageWorktoolSweepEvaluation:
        qpos = tuple(np.asarray(live_start_qpos, dtype=np.float64).reshape(-1))
        self.qpos.append(qpos)
        return CoverageWorktoolSweepEvaluation(
            profile="unity_kinematic_convex_cover_worktool_sweep_v1",
            eligible=self.eligible,
            rejection_reason=(
                "" if self.eligible else "worktool_3d_clearance_below_minimum"
            ),
            exemplar_id=exemplar_id,
            raw_fields_sha256=raw_fields_sha256,
            artifact_sha256="c" * 64,
            sampled_convex_cover_clearance_m=0.60,
            pose_interpolation_margin_m=0.01,
            act_tracking_margin_m=0.15,
            live_start_displacement_bound_m=0.02,
            effective_clearance_m=0.42 if self.eligible else 0.12,
            hard_clearance_m=0.30,
        )


def _state() -> CoverageRuntimeState:
    state = CoverageRuntimeState()
    transition = CoverageTupleStartReachabilityEvaluation(
        profile="strict_train_return_start_reachability_11d_v1",
        eligible=True,
        rejection_reason="",
        selection_phase="post_return",
        exemplar_id="episode_168",
        raw_fields_sha256="a" * 64,
        artifact_sha256="b" * 64,
        paired_return_primitive_episode_id=158,
        paired_return_exemplar_id="episode_158",
        exact_return_start_envelope_tokens=tuple([0.0] * 16 + [1.0, 1.0]),
        exact_return_start_envelope_valid_mask=(1,) * 18,
        paired_handoff_facts=(0.6,) * 11,
    )
    state.set_active_execution_candidate(
        corridor_id=1_000_168,
        effect_outcome_cell_id=1,
        return_envelope_cell_id=0,
        exemplar_id="episode_168",
        raw_fields_sha256="a" * 64,
        execution_tail_plane_depth_reserve_m=0.01,
        start_reachability_evaluation=transition,
    )
    return state


def _config() -> CoverageWorktoolSweepConfig:
    return CoverageWorktoolSweepConfig(
        enabled=True,
        artifact_path="/unused/by/fake.json",
        artifact_sha256="c" * 64,
        execution_library_sha256="d" * 64,
        pose_library_sha256="e" * 64,
    )


def test_final_handoff_guard_rechecks_actual_live_qpos() -> None:
    state = _state()
    sweep = _Sweep()
    service = CoverageExecutionHandoffGuardService(
        state=state,
        worktool_config=_config(),
        worktool_sweep_service=sweep,
    )

    result = service.evaluate([0.11, 0.22, 0.33, 0.44])

    assert result.required is True
    assert result.eligible is True
    assert sweep.qpos == [(0.11, 0.22, 0.33, 0.44)]
    assert result.trace["worktool_sweep_3d_evaluation_phase"] == (
        "final_live_handoff"
    )
    assert state.coverage_final_live_handoff_guard_result is result


def test_final_handoff_guard_fails_closed_without_bound_contract_or_clearance() -> None:
    missing = CoverageExecutionHandoffGuardService(
        state=CoverageRuntimeState(),
        worktool_config=_config(),
        worktool_sweep_service=_Sweep(),
    ).evaluate([0.1, 0.2, 0.3, 0.4], exact_contract_required=True)
    rejected = CoverageExecutionHandoffGuardService(
        state=_state(),
        worktool_config=_config(),
        worktool_sweep_service=_Sweep(eligible=False),
    ).evaluate([0.1, 0.2, 0.3, 0.4])

    assert missing.eligible is False
    assert missing.rejection_reason == "exact_tuple_handoff_contract_missing"
    assert rejected.eligible is False
    assert rejected.rejection_reason == "worktool_3d_clearance_below_minimum"


def test_final_handoff_guard_rejects_active_pending_identity_drift() -> None:
    result = CoverageExecutionHandoffGuardService(
        state=_state(),
        worktool_config=_config(),
        worktool_sweep_service=_Sweep(),
    ).evaluate(
        [0.1, 0.2, 0.3, 0.4],
        pending_exemplar_id="episode_999",
        pending_raw_fields_sha256="a" * 64,
        pending_paired_return_primitive_episode_id=158,
        pending_return_transition_artifact_sha256="b" * 64,
    )

    assert result.eligible is False
    assert result.rejection_reason == "exact_tuple_handoff_contract_missing"


def test_exact_envelope_timeout_is_specific_and_legacy_safe() -> None:
    service = CoverageExecutionHandoffGuardService(
        state=_state(),
        worktool_config=_config(),
        worktool_sweep_service=_Sweep(),
    )

    assert (
        service.exact_envelope_timeout_reason(
            skill_name="return",
            exact_contract_required=True,
            return_step_count=500,
            return_max_steps=500,
        )
        == "exact_return_start_envelope_timeout"
    )
    assert (
        service.exact_envelope_timeout_reason(
            skill_name="return",
            exact_contract_required=False,
            return_step_count=500,
            return_max_steps=500,
        )
        is None
    )
