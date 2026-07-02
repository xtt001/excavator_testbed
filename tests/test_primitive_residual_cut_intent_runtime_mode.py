from __future__ import annotations

from dataclasses import fields
from types import MappingProxyType, SimpleNamespace
from typing import Any

import numpy as np
import pytest

from testbed.data.operator_first_v2_2 import DIG_CUT_TOKEN_DIM
from testbed.planner.primitive.coverage.state import CoverageRuntimeState
from testbed.planner.primitive.token.dig_planning import (
    DIG_CUT_PLANNER_MODE_RESIDUAL_CUT_INTENT,
    PrimitiveDigTokenPlanningPorts,
    PrimitiveDigTokenPlanningService,
)
from testbed.planner.primitive.token.planning_runtime import (
    PrimitiveTokenPlanningRuntime,
    PrimitiveTokenPlanningRuntimePorts,
)
from testbed.planner.primitive.token.state import PrimitiveTokenRuntimeState
from testbed.planner.primitive.token.tokens import DigCutTokenPlan


def _token(value: float) -> np.ndarray:
    return np.full(DIG_CUT_TOKEN_DIM, value, dtype=np.float32)


def _plan(
    value: float,
    *,
    source: str,
    fallback_reason: str = "",
    raw_fields: dict[str, float | int] | None = None,
    in_prior: bool = False,
) -> DigCutTokenPlan:
    return DigCutTokenPlan(
        token=_token(value),
        raw_fields=MappingProxyType(dict(raw_fields or {"operator_entry_x_m": value})),
        source=source,
        fallback_reason=fallback_reason,
        in_prior_p10_p90=in_prior,
    )


class _ObservationFacts:
    deposited_mass_in_target_box_kg = 42.0
    env_state = np.zeros(64, dtype=np.float32)

    def bucket_dig_area_pose(self) -> tuple[float, float, float]:
        return (1.0, 2.0, 3.0)


class _DigCutPlanner:
    def __init__(
        self,
        events: list[str],
        *,
        raw_fields_error: Exception | None = None,
    ) -> None:
        self.events = events
        self.raw_fields_error = raw_fields_error
        self.last_plan: DigCutTokenPlan | None = None

    def _record(self, plan: DigCutTokenPlan) -> DigCutTokenPlan:
        self.last_plan = plan
        return plan

    def plan_from_raw_fields(
        self,
        raw_fields: dict[str, float | int],
        *,
        source: str,
        fallback_reason: str = "",
    ) -> DigCutTokenPlan:
        self.events.append(
            f"plan_raw:{source}:{raw_fields['operator_entry_x_m']}:{fallback_reason}"
        )
        if self.raw_fields_error is not None:
            raise self.raw_fields_error
        return self._record(
            _plan(
                5.0,
                source=source,
                fallback_reason=fallback_reason,
                raw_fields=raw_fields,
                in_prior=True,
            )
        )

    def plan_fallback_conservative_pose(
        self,
        pose: tuple[float, float, float] | None,
        *,
        fallback_reason: str,
    ) -> DigCutTokenPlan:
        self.events.append(f"fallback:{pose}:{fallback_reason}")
        return self._record(
            _plan(
                4.0,
                source="fallback_conservative_pose",
                fallback_reason=fallback_reason,
                in_prior=False,
            )
        )


def _ports(
    *,
    provider,
    mode: str = DIG_CUT_PLANNER_MODE_RESIDUAL_CUT_INTENT,
    fallback_mode: str = "conservative_pose",
    raw_fields_error: Exception | None = None,
) -> tuple[PrimitiveDigTokenPlanningPorts, PrimitiveTokenRuntimeState, list[str], _DigCutPlanner]:
    events: list[str] = []
    token_state = PrimitiveTokenRuntimeState.fresh()
    planner = _DigCutPlanner(events, raw_fields_error=raw_fields_error)
    ports = PrimitiveDigTokenPlanningPorts(
        token_state=token_state,
        coverage_state=CoverageRuntimeState(),
        dig_cut_planner_mode=lambda: mode,
        dig_cut_planner_fallback_mode=lambda: fallback_mode,
        cycle_index=lambda: 0,
        dig_cut_token_planner=lambda: planner,
        dig_depth_profile_token_planner=lambda: object(),
        observation_facts=lambda obs: _ObservationFacts(),
        select_next_coverage_corridor=lambda obs: SimpleNamespace(
            corridor_id=1,
            cell_id=2,
        ),
        coverage_raw_fields=lambda corridor, *, obs, update_state=False: {
            "operator_entry_x_m": 1.0,
        },
        residual_cut_intent_plan_provider=provider,
    )
    return ports, token_state, events, planner


def test_residual_cut_intent_mode_consumes_explicit_plan_and_updates_token_state() -> None:
    provided_plan = _plan(
        7.0,
        source="explicit_residual_cut_intent_runtime_plan",
        raw_fields={"operator_entry_x_m": 7.0},
        in_prior=False,
    )

    def provider(obs: dict[str, Any]) -> DigCutTokenPlan:
        assert obs["id"] == "obs"
        return provided_plan

    ports, token_state, events, planner = _ports(provider=provider)
    token = PrimitiveDigTokenPlanningService.from_ports(
        ports
    ).build_dig_cut_tokens_for_obs({"id": "obs"})

    assert events == []
    assert planner.last_plan is None
    assert token_state.dig_cut_token_source == "explicit_residual_cut_intent_runtime_plan"
    assert token_state.dig_cut_fallback_reason == ""
    assert token_state.dig_cut_token_in_prior_p10_p90 is False
    np.testing.assert_allclose(token, _token(7.0))
    token[0] = 99.0
    assert float(provided_plan.token[0]) == 7.0


def test_residual_cut_intent_mode_accepts_raw_field_tuple_via_existing_planner() -> None:
    def provider(obs: dict[str, Any]):
        return (
            _token(9.0),
            {"operator_entry_x_m": 0.42},
            "explicit_residual_cut_intent_runtime_raw_fields",
            "",
        )

    ports, token_state, events, planner = _ports(provider=provider)
    token = PrimitiveDigTokenPlanningService.from_ports(
        ports
    ).build_dig_cut_tokens_for_obs({"id": "obs"})

    assert events == [
        "plan_raw:explicit_residual_cut_intent_runtime_raw_fields:0.42:",
    ]
    assert planner.last_plan is not None
    assert token_state.dig_cut_token_source == (
        "explicit_residual_cut_intent_runtime_raw_fields"
    )
    assert token_state.dig_cut_fallback_reason == ""
    assert token_state.dig_cut_token_in_prior_p10_p90 is True
    np.testing.assert_allclose(token, _token(5.0))


def test_residual_cut_intent_mode_fallbacks_only_when_conservative_fallback_is_enabled() -> None:
    ports, token_state, events, _ = _ports(provider=lambda obs: None)
    token = PrimitiveDigTokenPlanningService.from_ports(
        ports
    ).build_dig_cut_tokens_for_obs({"id": "obs"})

    assert events == [
        "fallback:(1.0, 2.0, 3.0):residual_cut_intent provider returned no plan",
    ]
    assert token_state.dig_cut_token_source == "fallback_conservative_pose"
    assert token_state.dig_cut_fallback_reason == (
        "residual_cut_intent provider returned no plan"
    )
    np.testing.assert_allclose(token, _token(4.0))

    ports, _, _, _ = _ports(provider=lambda obs: None, fallback_mode="disabled")
    with pytest.raises(
        ValueError,
        match="residual_cut_intent provider returned no plan",
    ):
        PrimitiveDigTokenPlanningService.from_ports(
            ports
        ).build_dig_cut_tokens_for_obs({"id": "obs"})


def test_residual_cut_intent_mode_provider_errors_follow_existing_fallback_policy() -> None:
    def provider(obs: dict[str, Any]) -> DigCutTokenPlan:
        raise RuntimeError("provider failed")

    ports, token_state, events, _ = _ports(provider=provider)
    token = PrimitiveDigTokenPlanningService.from_ports(
        ports
    ).build_dig_cut_tokens_for_obs({"id": "obs"})

    assert events == [
        "fallback:(1.0, 2.0, 3.0):provider failed",
    ]
    assert token_state.dig_cut_token_source == "fallback_conservative_pose"
    assert token_state.dig_cut_fallback_reason == "provider failed"
    np.testing.assert_allclose(token, _token(4.0))

    ports, _, _, _ = _ports(provider=provider, fallback_mode="disabled")
    with pytest.raises(RuntimeError, match="provider failed"):
        PrimitiveDigTokenPlanningService.from_ports(
            ports
        ).build_dig_cut_tokens_for_obs({"id": "obs"})


def test_token_planning_runtime_passes_residual_cut_intent_provider_to_dig_ports() -> None:
    provider = lambda obs: _plan(8.0, source="runtime_provider")
    token_state = PrimitiveTokenRuntimeState.fresh()
    coverage_state = CoverageRuntimeState()
    runtime = PrimitiveTokenPlanningRuntime.from_ports(
        PrimitiveTokenPlanningRuntimePorts(
            token_state=token_state,
            coverage_state=coverage_state,
            dig_cut_planner_mode=lambda: DIG_CUT_PLANNER_MODE_RESIDUAL_CUT_INTENT,
            dig_cut_planner_fallback_mode=lambda: "conservative_pose",
            cycle_index=lambda: 0,
            dig_cut_token_planner=lambda: _DigCutPlanner([]),
            dig_depth_profile_token_planner=lambda: object(),
            return_target_token_planner=lambda: object(),
            return_start_envelope_token_planner=lambda: object(),
            observation_facts=lambda obs: _ObservationFacts(),
            select_next_coverage_corridor=lambda obs: SimpleNamespace(
                corridor_id=1,
                cell_id=2,
            ),
            coverage_raw_fields=lambda corridor, *, obs, update_state=False: {
                "operator_entry_x_m": 1.0,
            },
            residual_cut_intent_plan_provider=provider,
        )
    )

    dig_ports = runtime.dig_token_planning_ports()
    runtime_fields = {field.name for field in fields(PrimitiveTokenPlanningRuntimePorts)}
    dig_fields = {field.name for field in fields(PrimitiveDigTokenPlanningPorts)}

    assert "residual_cut_intent_plan_provider" in runtime_fields
    assert "residual_cut_intent_plan_provider" in dig_fields
    assert dig_ports.residual_cut_intent_plan_provider is provider


def test_token_planning_runtime_passes_residual_return_target_provider_to_return_ports() -> None:
    dig_provider = lambda obs: _plan(8.0, source="runtime_dig_provider")
    return_provider = lambda obs: _plan(9.0, source="runtime_return_provider")
    token_state = PrimitiveTokenRuntimeState.fresh()
    coverage_state = CoverageRuntimeState()
    runtime = PrimitiveTokenPlanningRuntime.from_ports(
        PrimitiveTokenPlanningRuntimePorts(
            token_state=token_state,
            coverage_state=coverage_state,
            dig_cut_planner_mode=lambda: DIG_CUT_PLANNER_MODE_RESIDUAL_CUT_INTENT,
            dig_cut_planner_fallback_mode=lambda: "conservative_pose",
            cycle_index=lambda: 0,
            dig_cut_token_planner=lambda: _DigCutPlanner([]),
            dig_depth_profile_token_planner=lambda: object(),
            return_target_token_planner=lambda: object(),
            return_start_envelope_token_planner=lambda: object(),
            observation_facts=lambda obs: _ObservationFacts(),
            select_next_coverage_corridor=lambda obs: SimpleNamespace(
                corridor_id=1,
                cell_id=2,
            ),
            coverage_raw_fields=lambda corridor, *, obs, update_state=False: {
                "operator_entry_x_m": 1.0,
            },
            residual_cut_intent_plan_provider=dig_provider,
            residual_cut_intent_return_target_plan_provider=return_provider,
        )
    )

    return_ports = runtime.return_token_planning_ports()
    runtime_fields = {field.name for field in fields(PrimitiveTokenPlanningRuntimePorts)}

    assert "residual_cut_intent_return_target_plan_provider" in runtime_fields
    assert return_ports.residual_cut_intent_return_target_plan_provider is return_provider
