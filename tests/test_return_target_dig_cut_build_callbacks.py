from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from testbed.contracts.primitive_tokens import RETURN_TARGET_TOKEN_DIM
from testbed.planner.return_target_plan import (
    ReturnTargetDigCutBuildCallbacks,
    ReturnTargetDigCutBuildContext,
    ReturnTargetPlanService,
)


@pytest.mark.parametrize(
    (
        "builder_kind",
        "planner_mode",
        "expected_call",
        "expected_source",
        "expected_fallback_reason",
        "expected_corridor_id",
    ),
    [
        (
            "conservative_pose",
            "conservative_pose",
            "conservative",
            "return_target_conservative_pose",
            "",
            -1,
        ),
        (
            "operator_prior",
            "operator_prior",
            "operator_prior",
            "return_target_operator_prior_pose_clamped",
            "pose clamped",
            -1,
        ),
        (
            "operator_prior_coverage",
            "operator_prior_sweep_belief",
            "coverage",
            "return_target_operator_prior_sweep_belief",
            "",
            7,
        ),
    ],
)
def test_dig_cut_build_callbacks_select_one_builder_and_project_result(
    builder_kind: str,
    planner_mode: str,
    expected_call: str,
    expected_source: str,
    expected_fallback_reason: str,
    expected_corridor_id: int,
) -> None:
    service = ReturnTargetPlanService()
    token = np.arange(RETURN_TARGET_TOKEN_DIM, dtype=np.float64)
    raw_fields = {"operator_entry_x_m": 0.5, "operator_cut_valid": 1}
    calls: list[str] = []

    def conservative_pose_plan() -> SimpleNamespace:
        calls.append("conservative")
        return SimpleNamespace(
            token=token,
            raw_fields=raw_fields,
            source="conservative_pose",
            fallback_reason="",
        )

    def operator_prior_parts() -> tuple[np.ndarray, dict[str, float | int], str, str]:
        calls.append("operator_prior")
        return token, raw_fields, "operator_prior_pose_clamped", "pose clamped"

    def coverage_plan() -> tuple[SimpleNamespace, int]:
        calls.append("coverage")
        return (
            SimpleNamespace(
                token=token,
                raw_fields=raw_fields,
                source=planner_mode,
                fallback_reason="",
            ),
            7,
        )

    result = service.dig_cut_build_result_from_callbacks(
        ReturnTargetDigCutBuildContext(
            source_prefix="return_target",
            builder_kind=builder_kind,
            planner_mode=planner_mode,
        ),
        ReturnTargetDigCutBuildCallbacks(
            conservative_pose_plan=conservative_pose_plan,
            operator_prior_parts=operator_prior_parts,
            coverage_plan=coverage_plan,
        ),
    )

    assert calls == [expected_call]
    assert result.token is token
    assert result.raw_fields is raw_fields
    assert result.source == expected_source
    assert result.fallback_reason == expected_fallback_reason
    assert result.corridor_id == expected_corridor_id
