from __future__ import annotations

from dataclasses import fields
from types import MappingProxyType, MethodType, SimpleNamespace
from typing import Any

import numpy as np
import pytest

from testbed.data.dig_depth_profile_v2_4 import DIG_DEPTH_PROFILE_TOKEN_DIM
from testbed.data.operator_first_v2_2 import (
    DIG_CUT_DEPTH_SCALE_M,
    DIG_CUT_LENGTH_SCALE_M,
    DIG_CUT_PAYLOAD_SCALE_KG,
    DIG_CUT_POSITION_SCALE_M,
    DIG_CUT_TOKEN_DIM,
)
from testbed.data.schema import ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX
from testbed.data.schema import ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX
from testbed.data.schema import ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX
from testbed.data.schema import ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX
from testbed.data.schema import ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX
from testbed.planner.primitive_capabilities import PrimitiveObservationFacts
from testbed.planner.primitive_dig_token_planning import (
    PrimitiveDigTokenPlanningPorts,
    PrimitiveDigTokenPlanningService,
)
from testbed.planner.primitive_coverage_state import CoverageRuntimeState
from testbed.planner.primitive_token_state import PrimitiveTokenRuntimeState
from testbed.planner.primitive_tokens import (
    DigCutTokenPlan,
    DigDepthProfileTokenPlan,
    DigDepthProfileTokenPlanningError,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def _token(size: int, value: float) -> np.ndarray:
    return np.full(size, value, dtype=np.float32)


def _dig_plan(
    value: float,
    *,
    source: str,
    fallback_reason: str = "",
    raw_fields: dict[str, float | int] | None = None,
    in_prior: bool = True,
) -> DigCutTokenPlan:
    return DigCutTokenPlan(
        token=_token(DIG_CUT_TOKEN_DIM, value),
        raw_fields=MappingProxyType(
            dict(raw_fields or {"operator_entry_x_m": value})
        ),
        source=source,
        fallback_reason=fallback_reason,
        in_prior_p10_p90=in_prior,
    )


class _DigCutPlanner:
    def __init__(
        self,
        events: list[str],
        *,
        operator_prior_error: Exception | None = None,
        raw_fields_error: Exception | None = None,
    ) -> None:
        self.events = events
        self.operator_prior_error = operator_prior_error
        self.raw_fields_error = raw_fields_error
        self.last_plan: DigCutTokenPlan | None = None

    def _record(self, plan: DigCutTokenPlan) -> DigCutTokenPlan:
        self.last_plan = plan
        return plan

    def plan_pending_return_target(
        self,
        *,
        tokens: np.ndarray,
        raw_fields: dict[str, float | int] | None,
    ) -> DigCutTokenPlan:
        self.events.append(
            f"plan_pending:{float(np.asarray(tokens).reshape(-1)[0])}:{raw_fields}"
        )
        return self._record(
            _dig_plan(
                1.0,
                source="pending_return_target",
                raw_fields=raw_fields,
                in_prior=raw_fields is not None,
            )
        )

    def plan_conservative_pose(
        self,
        pose: tuple[float, float, float] | None,
    ) -> DigCutTokenPlan:
        self.events.append(f"plan_conservative:{pose}")
        return self._record(_dig_plan(2.0, source="conservative_pose", in_prior=False))

    def plan_operator_prior(
        self,
        pose: tuple[float, float, float] | None,
    ) -> DigCutTokenPlan:
        self.events.append(f"plan_operator_prior:{pose}")
        if self.operator_prior_error is not None:
            raise self.operator_prior_error
        return self._record(_dig_plan(3.0, source="operator_prior_pose_clamped"))

    def plan_fallback_conservative_pose(
        self,
        pose: tuple[float, float, float] | None,
        *,
        fallback_reason: str,
    ) -> DigCutTokenPlan:
        self.events.append(f"plan_fallback:{pose}:{fallback_reason}")
        return self._record(
            _dig_plan(
                4.0,
                source="fallback_conservative_pose",
                fallback_reason=fallback_reason,
                in_prior=False,
            )
        )

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
            _dig_plan(
                5.0,
                source=source,
                fallback_reason=fallback_reason,
                raw_fields=raw_fields,
            )
        )

    def raw_fields_from_live_pose(
        self,
        pose: tuple[float, float, float] | None,
    ) -> dict[str, float | int]:
        self.events.append(f"raw_live:{pose}")
        return {
            "operator_entry_x_m": 100.0,
            "operator_entry_z_m": 101.0,
            "operator_exit_x_m": 102.0,
            "operator_exit_z_m": 103.0,
            "operator_cut_direction_x": 104.0,
            "operator_cut_direction_z": 105.0,
            "operator_cut_length_m": 106.0,
            "operator_cut_depth_peak_m": 107.0,
            "operator_cut_payload_gain_kg": 108.0,
            "operator_cut_valid": 0,
        }


class _DepthPlanner:
    def __init__(
        self,
        events: list[str],
        *,
        plan_error: DigDepthProfileTokenPlanningError | None = None,
    ) -> None:
        self.events = events
        self.plan_error = plan_error
        self.last_plan: DigDepthProfileTokenPlan | None = None

    def plan(
        self,
        *,
        cell_id: int,
        raw_fields: dict[str, float | int],
        env_state: np.ndarray,
        state_exemplar_profile_token: np.ndarray | None = None,
    ) -> DigDepthProfileTokenPlan:
        self.events.append(
            "depth_plan:"
            f"{cell_id}:{raw_fields['operator_entry_x_m']}:"
            f"{float(env_state[0])}:"
            f"{state_exemplar_profile_token is not None}"
        )
        if self.plan_error is not None:
            raise self.plan_error
        plan = DigDepthProfileTokenPlan(
            token=_token(DIG_DEPTH_PROFILE_TOKEN_DIM, 6.0),
            source="depth_source",
            fallback_reason="",
        )
        self.last_plan = plan
        return plan

    def live_plan_token(
        self,
        *,
        cell_id: int,
        raw_fields: dict[str, float | int],
        env_state: np.ndarray,
    ) -> np.ndarray:
        self.events.append(
            f"depth_live:{cell_id}:{raw_fields['operator_entry_x_m']}:"
            f"{float(env_state[0])}"
        )
        return _token(DIG_DEPTH_PROFILE_TOKEN_DIM, 7.0)

    def prior_token(self, cell_id: int) -> tuple[np.ndarray | None, str, str]:
        self.events.append(f"depth_prior_token:{cell_id}")
        return _token(DIG_DEPTH_PROFILE_TOKEN_DIM, 8.0), f"cell_{cell_id}", ""

    def prior_mapping(
        self,
        cell_id: int,
    ) -> tuple[dict[str, object], str, str]:
        self.events.append(f"depth_prior_mapping:{cell_id}")
        return {"cell_id": cell_id}, "cell", ""


def _ports(
    *,
    mode: str = "conservative_pose",
    fallback_mode: str = "conservative_pose",
    cycle_index: int = 3,
    pending_cycle_id: int = -1,
    pending_tokens: np.ndarray | None = None,
    pending_raw_fields: dict[str, float | int] | None = None,
    pending_corridor_id: int = -1,
    active_corridor: object | None = None,
    operator_prior_error: Exception | None = None,
    raw_fields_error: Exception | None = None,
    depth_error: DigDepthProfileTokenPlanningError | None = None,
    events: list[str] | None = None,
) -> tuple[PrimitiveDigTokenPlanningPorts, dict[str, object], list[str], _DigCutPlanner, _DepthPlanner]:
    events = [] if events is None else events
    pending_profile = _token(DIG_DEPTH_PROFILE_TOKEN_DIM, 9.0)
    corridors = {
        12: SimpleNamespace(corridor_id=12, cell_id=4),
        15: SimpleNamespace(corridor_id=15, cell_id=2),
    }
    selected_corridor = SimpleNamespace(corridor_id=22, cell_id=5)
    state: dict[str, object] = {
        "mode": mode,
        "fallback_mode": fallback_mode,
        "cycle_index": cycle_index,
    }
    token_state = PrimitiveTokenRuntimeState.fresh()
    token_state.pending_dig_cut_cycle_id = int(pending_cycle_id)
    token_state.pending_dig_cut_tokens = pending_tokens
    token_state.pending_dig_cut_raw_fields = pending_raw_fields
    token_state.pending_dig_cut_corridor_id = int(pending_corridor_id)
    token_state.pending_dig_state_exemplar_ids = ["ex_a", "ex_b"]
    token_state.pending_dig_state_exemplar_distance = 1.25
    token_state.pending_dig_depth_profile_tokens = pending_profile
    token_state.dig_cut_tokens = _token(DIG_CUT_TOKEN_DIM, 0.0)
    token_state.dig_cut_token_source = "old_cut"
    token_state.dig_cut_fallback_reason = "old_cut_reason"
    token_state.dig_cut_token_in_prior_p10_p90 = False
    token_state.dig_depth_profile_token_source = "old_depth"
    token_state.dig_depth_profile_fallback_reason = "old_depth_reason"
    coverage_corridors = list(corridors.values())
    if active_corridor is not None and all(
        corridor.corridor_id != active_corridor.corridor_id
        for corridor in coverage_corridors
    ):
        coverage_corridors.append(active_corridor)
    coverage_state = CoverageRuntimeState(
        coverage_corridors=coverage_corridors,
        coverage_active_corridor_id=(
            -1 if active_corridor is None else int(active_corridor.corridor_id)
        ),
        coverage_current_payload_gain_kg=99.0,
        coverage_cycle_start_deposit_kg=-1.0,
    )
    state["token_state"] = token_state
    state["coverage_state"] = coverage_state
    cut_planner = _DigCutPlanner(
        events,
        operator_prior_error=operator_prior_error,
        raw_fields_error=raw_fields_error,
    )
    depth_planner = _DepthPlanner(events, plan_error=depth_error)

    def coverage_raw_fields(
        corridor: object,
        *,
        obs: dict[str, Any],
        update_state: bool = False,
    ) -> dict[str, float | int]:
        events.append(
            f"coverage_raw:{corridor.corridor_id}:{obs['id']}:{update_state}"
        )
        return {"operator_entry_x_m": 22.5}

    def observation_facts(obs: dict[str, Any]) -> PrimitiveObservationFacts:
        env_state = np.zeros(64, dtype=np.float32)
        if "env_state" in obs:
            incoming = np.asarray(obs["env_state"], dtype=np.float32).reshape(-1)
            env_state[: len(incoming)] = incoming
        if "pose_x" in obs:
            env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX] = float(obs["pose_x"])
            env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX] = float(obs["pose_y"])
            env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX] = float(obs["pose_z"])
        env_state[ENV_STATE_DEPOSITED_MASS_IN_TARGET_BOX_IDX] = 42.0
        return PrimitiveObservationFacts.from_obs(
            {
                "env_state": env_state,
                "task_metrics": {
                    "deposited_mass_in_target_box_kg": 42.0,
                },
            },
            action_dim=4,
        )

    ports = PrimitiveDigTokenPlanningPorts(
        token_state=token_state,
        coverage_state=coverage_state,
        dig_cut_planner_mode=lambda: str(state["mode"]),
        dig_cut_planner_fallback_mode=lambda: str(state["fallback_mode"]),
        cycle_index=lambda: int(state["cycle_index"]),
        dig_cut_token_planner=lambda: cut_planner,
        dig_depth_profile_token_planner=lambda: depth_planner,
        observation_facts=observation_facts,
        select_next_coverage_corridor=lambda obs: events.append(
            f"select_corridor:{obs['id']}"
        )
        or selected_corridor,
        coverage_raw_fields=coverage_raw_fields,
    )
    return ports, state, events, cut_planner, depth_planner


def test_pending_return_target_route_writes_coverage_state_and_copies() -> None:
    pending_tokens = _token(DIG_CUT_TOKEN_DIM, 1.5)
    pending_raw = {"operator_entry_x_m": 9.0}
    ports, state, events, cut_planner, _ = _ports(
        pending_cycle_id=3,
        pending_tokens=pending_tokens,
        pending_raw_fields=pending_raw,
        pending_corridor_id=12,
    )

    token = PrimitiveDigTokenPlanningService.from_ports(
        ports
    ).build_dig_cut_tokens_for_obs({"id": "obs", "pose_x": 1, "pose_y": 2, "pose_z": 3})

    assert events == [
        "plan_pending:1.5:{'operator_entry_x_m': 9.0}",
    ]
    token_state = state["token_state"]
    coverage_state = state["coverage_state"]
    assert isinstance(token_state, PrimitiveTokenRuntimeState)
    assert isinstance(coverage_state, CoverageRuntimeState)
    assert coverage_state.coverage_active_corridor_id == 12
    assert coverage_state.coverage_last_selected_corridor_id == 12
    assert coverage_state.coverage_current_payload_gain_kg == 0.0
    assert coverage_state.coverage_cycle_start_deposit_kg == 42.0
    assert coverage_state.coverage_active_state_exemplar_ids == ["ex_a", "ex_b"]
    assert coverage_state.coverage_active_state_exemplar_distance == 1.25
    assert (
        coverage_state.coverage_active_state_exemplar_profile_token
        is not token_state.pending_dig_depth_profile_tokens
    )
    assert token_state.dig_cut_token_source == "pending_return_target"
    assert token_state.dig_cut_fallback_reason == ""
    assert token_state.dig_cut_token_in_prior_p10_p90 is True
    assert cut_planner.last_plan is not None
    assert token is not cut_planner.last_plan.token
    token[0] = 99.0
    assert float(cut_planner.last_plan.token[0]) == 1.0


def test_conservative_and_operator_prior_routes_apply_dig_cut_plan() -> None:
    ports, state, events, _, _ = _ports(mode="conservative_pose")
    token = PrimitiveDigTokenPlanningService.from_ports(
        ports
    ).build_dig_cut_tokens_for_obs({"id": "obs", "pose_x": 1, "pose_y": 2, "pose_z": 3})

    assert events == [
        "plan_conservative:(1.0, 2.0, 3.0)",
    ]
    token_state = state["token_state"]
    assert isinstance(token_state, PrimitiveTokenRuntimeState)
    assert token_state.dig_cut_token_source == "conservative_pose"
    assert token_state.dig_cut_fallback_reason == ""
    assert token_state.dig_cut_token_in_prior_p10_p90 is False
    np.testing.assert_allclose(token, _token(DIG_CUT_TOKEN_DIM, 2.0))

    ports, state, events, _, _ = _ports(mode="operator_prior")
    token = PrimitiveDigTokenPlanningService.from_ports(
        ports
    ).build_dig_cut_tokens_for_obs({"id": "obs", "pose_x": 4, "pose_y": 5, "pose_z": 6})

    assert events == [
        "plan_operator_prior:(4.0, 5.0, 6.0)",
    ]
    token_state = state["token_state"]
    assert isinstance(token_state, PrimitiveTokenRuntimeState)
    assert token_state.dig_cut_token_source == "operator_prior_pose_clamped"
    assert token_state.dig_cut_fallback_reason == ""
    assert token_state.dig_cut_token_in_prior_p10_p90 is True
    np.testing.assert_allclose(token, _token(DIG_CUT_TOKEN_DIM, 3.0))


def test_operator_prior_fallback_and_disabled_reraise() -> None:
    ports, _, events, _, _ = _ports(
        mode="operator_prior",
        operator_prior_error=ValueError("prior failed"),
    )

    token = PrimitiveDigTokenPlanningService.from_ports(
        ports
    ).build_dig_cut_tokens_for_obs({"id": "obs", "pose_x": 1, "pose_y": 2, "pose_z": 3})

    assert events == [
        "plan_operator_prior:(1.0, 2.0, 3.0)",
        "plan_fallback:(1.0, 2.0, 3.0):prior failed",
    ]
    np.testing.assert_allclose(token, _token(DIG_CUT_TOKEN_DIM, 4.0))

    ports, _, _, _, _ = _ports(
        mode="operator_prior",
        fallback_mode="none",
        operator_prior_error=ValueError("prior failed"),
    )
    with pytest.raises(ValueError, match="prior failed"):
        PrimitiveDigTokenPlanningService.from_ports(
            ports
        ).build_dig_cut_tokens_for_obs(
            {"id": "obs", "pose_x": 1, "pose_y": 2, "pose_z": 3}
        )


@pytest.mark.parametrize(
    "mode",
    ["operator_prior_coverage", "operator_prior_sweep_belief"],
)
def test_coverage_routes_use_existing_coverage_raw_field_builder(mode: str) -> None:
    ports, state, events, _, _ = _ports(mode=mode)

    token, raw, source, fallback = PrimitiveDigTokenPlanningService.from_ports(
        ports
    ).build_operator_prior_coverage_dig_cut_tokens(
        {"id": "obs", "pose_x": 1, "pose_y": 2, "pose_z": 3}
    )

    assert events == [
        "select_corridor:obs",
        "coverage_raw:22:obs:True",
        "plan_raw:operator_prior_coverage:22.5:",
    ]
    coverage_state = state["coverage_state"]
    assert isinstance(coverage_state, CoverageRuntimeState)
    assert coverage_state.coverage_current_payload_gain_kg == 0.0
    assert coverage_state.coverage_cycle_start_deposit_kg == 42.0
    np.testing.assert_allclose(token, _token(DIG_CUT_TOKEN_DIM, 5.0))
    assert raw == {"operator_entry_x_m": 22.5}
    assert source == "operator_prior_coverage"
    assert fallback == ""

    events.clear()
    result = PrimitiveDigTokenPlanningService.from_ports(
        ports
    ).build_dig_cut_tokens_for_obs({"id": "obs", "pose_x": 1, "pose_y": 2, "pose_z": 3})
    assert events == [
        "select_corridor:obs",
        "coverage_raw:22:obs:True",
        "plan_raw:operator_prior_coverage:22.5:",
        "plan_raw:operator_prior_coverage:22.5:",
    ]
    token_state = state["token_state"]
    assert isinstance(token_state, PrimitiveTokenRuntimeState)
    assert token_state.dig_cut_token_source == "operator_prior_coverage"
    assert token_state.dig_cut_fallback_reason == ""
    assert token_state.dig_cut_token_in_prior_p10_p90 is True
    np.testing.assert_allclose(result, _token(DIG_CUT_TOKEN_DIM, 5.0))


def test_coverage_route_fallback_and_unsupported_mode_error() -> None:
    ports, _, events, _, _ = _ports(
        mode="operator_prior_coverage",
        raw_fields_error=ValueError("coverage failed"),
    )
    token = PrimitiveDigTokenPlanningService.from_ports(
        ports
    ).build_dig_cut_tokens_for_obs({"id": "obs", "pose_x": 1, "pose_y": 2, "pose_z": 3})

    assert events[-2:] == [
        "plan_raw:operator_prior_coverage:22.5:",
        "plan_fallback:(1.0, 2.0, 3.0):coverage failed",
    ]
    token_state = ports.token_state
    assert token_state.dig_cut_token_source == "fallback_conservative_pose"
    assert token_state.dig_cut_fallback_reason == "coverage failed"
    assert token_state.dig_cut_token_in_prior_p10_p90 is False
    np.testing.assert_allclose(token, _token(DIG_CUT_TOKEN_DIM, 4.0))

    ports, _, _, _, _ = _ports(mode="not_real")
    with pytest.raises(
        ValueError,
        match="Unsupported dig_cut_planner mode 'not_real'\\.",
    ):
        PrimitiveDigTokenPlanningService.from_ports(
            ports
        ).build_dig_cut_tokens_for_obs(
            {"id": "obs", "pose_x": 1, "pose_y": 2, "pose_z": 3}
        )


def test_dig_cut_apply_and_depth_profile_success_error_and_helpers() -> None:
    ports, state, events, _, depth_planner = _ports(
        active_corridor=SimpleNamespace(corridor_id=15, cell_id=2)
    )
    service = PrimitiveDigTokenPlanningService.from_ports(ports)
    obs = {
        "id": "obs",
        "pose_x": 1,
        "pose_y": 2,
        "pose_z": 3,
        "env_state": _token(32, 1.5),
    }

    token = service.build_dig_depth_profile_tokens_for_obs(obs)

    assert events == [
        "coverage_raw:15:obs:False",
        "depth_plan:2:22.5:1.5:False",
    ]
    token_state = state["token_state"]
    assert isinstance(token_state, PrimitiveTokenRuntimeState)
    assert token_state.dig_depth_profile_token_source == "depth_source"
    assert token_state.dig_depth_profile_fallback_reason == ""
    assert depth_planner.last_plan is not None
    assert token is not depth_planner.last_plan.token

    events.clear()
    live = service.build_live_dig_depth_profile_tokens_for_obs(obs, cell_id=4)
    assert events == [
        "coverage_raw:15:obs:False",
        "depth_live:4:22.5:1.5",
    ]
    np.testing.assert_allclose(live, _token(DIG_DEPTH_PROFILE_TOKEN_DIM, 7.0))

    events.clear()
    prior_token, prior_source, prior_reason = service.dig_depth_profile_prior_token(3)
    prior_mapping, mapping_source, mapping_reason = (
        service.dig_depth_profile_prior_mapping(4)
    )
    assert events == ["depth_prior_token:3", "depth_prior_mapping:4"]
    np.testing.assert_allclose(prior_token, _token(DIG_DEPTH_PROFILE_TOKEN_DIM, 8.0))
    assert prior_source == "cell_3"
    assert prior_reason == ""
    assert prior_mapping == {"cell_id": 4}
    assert mapping_source == "cell"
    assert mapping_reason == ""

    error = DigDepthProfileTokenPlanningError(
        "missing prior",
        token_source="missing_required_prior",
        fallback_reason="missing dig_cut_prior",
    )
    error_ports, error_state, error_events, _, _ = _ports(depth_error=error)
    with pytest.raises(DigDepthProfileTokenPlanningError):
        PrimitiveDigTokenPlanningService.from_ports(
            error_ports
        ).build_dig_depth_profile_tokens_for_obs(obs)
    error_token_state = error_state["token_state"]
    assert isinstance(error_token_state, PrimitiveTokenRuntimeState)
    assert (
        error_token_state.dig_depth_profile_token_source
        == "missing_required_prior"
    )
    assert (
        error_token_state.dig_depth_profile_fallback_reason
        == "missing dig_cut_prior"
    )
    assert error_events[-2:] == [
        "raw_live:(1.0, 2.0, 3.0)",
        "depth_plan:2:0.0:1.5:False",
    ]


def test_raw_fields_priority_and_token_decoding() -> None:
    pending_raw = {"operator_entry_x_m": 33.0}
    ports, state, events, _, _ = _ports(
        pending_cycle_id=3,
        pending_raw_fields=pending_raw,
    )
    service = PrimitiveDigTokenPlanningService.from_ports(ports)

    raw = service.dig_depth_profile_raw_fields({"id": "obs", "pose_x": 1, "pose_y": 2, "pose_z": 3})

    assert raw == {"operator_entry_x_m": 33.0}
    raw["operator_entry_x_m"] = 44.0
    token_state = state["token_state"]
    assert isinstance(token_state, PrimitiveTokenRuntimeState)
    assert token_state.pending_dig_cut_raw_fields == pending_raw

    ports, _, events, _, _ = _ports(
        active_corridor=SimpleNamespace(corridor_id=15, cell_id=2)
    )
    raw = PrimitiveDigTokenPlanningService.from_ports(
        ports
    ).dig_depth_profile_raw_fields({"id": "obs", "pose_x": 1, "pose_y": 2, "pose_z": 3})
    assert events == ["coverage_raw:15:obs:False"]
    assert raw == {"operator_entry_x_m": 22.5}

    dig_token = np.asarray(
        [0.5, -0.25, -0.5, 0.75, -1.0, 0.25, 0.6, 0.5, 0.75, 1.0],
        dtype=np.float32,
    )
    ports, state, events, _, _ = _ports()
    token_state = state["token_state"]
    assert isinstance(token_state, PrimitiveTokenRuntimeState)
    token_state.dig_cut_tokens = dig_token
    raw = PrimitiveDigTokenPlanningService.from_ports(
        ports
    ).dig_depth_profile_raw_fields({"id": "obs", "pose_x": 1, "pose_y": 2, "pose_z": 3})

    assert events == ["raw_live:(1.0, 2.0, 3.0)"]
    assert raw["operator_entry_x_m"] == pytest.approx(
        float(dig_token[0]) * DIG_CUT_POSITION_SCALE_M
    )
    assert raw["operator_entry_z_m"] == pytest.approx(
        float(dig_token[1]) * DIG_CUT_POSITION_SCALE_M
    )
    assert raw["operator_exit_x_m"] == pytest.approx(
        float(dig_token[2]) * DIG_CUT_POSITION_SCALE_M
    )
    assert raw["operator_exit_z_m"] == pytest.approx(
        float(dig_token[3]) * DIG_CUT_POSITION_SCALE_M
    )
    assert raw["operator_cut_length_m"] == pytest.approx(
        float(dig_token[6]) * DIG_CUT_LENGTH_SCALE_M
    )
    assert raw["operator_cut_depth_peak_m"] == pytest.approx(
        float(dig_token[7]) * DIG_CUT_DEPTH_SCALE_M
    )
    assert raw["operator_cut_payload_gain_kg"] == pytest.approx(
        float(dig_token[8]) * DIG_CUT_PAYLOAD_SCALE_KG
    )
    assert raw["operator_cut_valid"] == 1


def test_cell_id_priority() -> None:
    ports, _, _, _, _ = _ports(pending_cycle_id=3, pending_corridor_id=12)
    assert (
        PrimitiveDigTokenPlanningService.from_ports(ports).dig_depth_profile_cell_id(
            {"id": "obs", "pose_x": 1, "pose_y": 2, "pose_z": 3, "env_state": []}
        )
        == 4
    )

    active = SimpleNamespace(corridor_id=15, cell_id=2)
    ports, _, _, _, _ = _ports(active_corridor=active)
    assert (
        PrimitiveDigTokenPlanningService.from_ports(ports).dig_depth_profile_cell_id(
            {"id": "obs", "pose_x": 1, "pose_y": 2, "pose_z": 3, "env_state": []}
        )
        == 2
    )

    env_state = np.zeros(ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX + 1, dtype=np.float32)
    env_state[ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX] = 4.6
    ports, _, _, _, _ = _ports()
    assert (
        PrimitiveDigTokenPlanningService.from_ports(ports).dig_depth_profile_cell_id(
            {"id": "obs", "pose_x": 1, "pose_y": 2, "pose_z": 3, "env_state": env_state}
        )
        == 5
    )

    env_state[ENV_STATE_BUCKET_DIG_AREA_CELL_ID_IDX] = np.nan
    assert (
        PrimitiveDigTokenPlanningService.from_ports(ports).dig_depth_profile_cell_id(
            {"id": "obs", "pose_x": 1, "pose_y": 2, "pose_z": 3, "env_state": env_state}
        )
        == 0
    )


def test_ports_boundary_is_typed_and_does_not_accept_planner_self() -> None:
    names = {field.name for field in fields(PrimitiveDigTokenPlanningPorts)}
    removed_state_callbacks = {
        "get_pending_dig_cut_cycle_id",
        "get_pending_dig_cut_tokens",
        "get_pending_dig_cut_raw_fields",
        "get_pending_dig_cut_corridor_id",
        "get_pending_dig_state_exemplar_ids",
        "get_pending_dig_state_exemplar_distance",
        "get_pending_dig_depth_profile_tokens",
        "get_dig_cut_tokens",
        "set_dig_cut_token_source",
        "set_dig_cut_fallback_reason",
        "set_dig_cut_token_in_prior_p10_p90",
        "set_dig_depth_profile_token_source",
        "set_dig_depth_profile_fallback_reason",
        "active_coverage_corridor",
        "coverage_corridor_by_id",
        "set_coverage_active_corridor_id",
        "set_coverage_last_selected_corridor_id",
        "set_coverage_current_payload_gain_kg",
        "set_coverage_cycle_start_deposit_kg",
        "set_coverage_active_state_exemplar",
        "get_coverage_active_state_exemplar_profile_token",
    }

    assert "planner" not in names
    assert "self" not in names
    assert "token_state" in names
    assert "coverage_state" in names
    assert "observation_facts" in names
    assert "dig_cut_token_planner" in names
    assert "dig_depth_profile_token_planner" in names
    assert "bucket_dig_area_pose" not in names
    assert "deposited_mass" not in names
    assert "env_state" not in names
    assert names.isdisjoint(removed_state_callbacks)


def test_policy_private_facades_delegate_to_dig_token_planning_service() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    events: list[tuple[str, object]] = []

    class FakeService:
        def build_dig_cut_tokens_for_obs(self, obs: dict[str, Any]) -> str:
            events.append(("build_cut", obs))
            return "cut"

        def apply_dig_cut_token_plan(self, plan: DigCutTokenPlan) -> str:
            events.append(("apply_cut", plan))
            return "applied-cut"

        def build_dig_depth_profile_tokens_for_obs(self, obs: dict[str, Any]) -> str:
            events.append(("build_depth", obs))
            return "depth"

        def apply_dig_depth_profile_token_plan(
            self,
            plan: DigDepthProfileTokenPlan,
        ) -> str:
            events.append(("apply_depth", plan))
            return "applied-depth"

        def build_live_dig_depth_profile_tokens_for_obs(
            self,
            obs: dict[str, Any],
            *,
            cell_id: int,
        ) -> str:
            events.append(("live_depth", (obs, cell_id)))
            return "live-depth"

        def dig_depth_profile_prior_token(self, cell_id: int) -> str:
            events.append(("prior_token", cell_id))
            return "prior-token"

        def dig_depth_profile_prior_mapping(self, cell_id: int) -> str:
            events.append(("prior_mapping", cell_id))
            return "prior-mapping"

        def dig_depth_profile_raw_fields(self, obs: dict[str, Any]) -> str:
            events.append(("raw_fields", obs))
            return "raw-fields"

        def dig_depth_profile_cell_id(self, obs: dict[str, Any]) -> int:
            events.append(("cell_id", obs))
            return 5

        def build_operator_prior_coverage_dig_cut_tokens(
            self,
            obs: dict[str, Any],
        ) -> str:
            events.append(("coverage_cut", obs))
            return "coverage-cut"

    fake_service = FakeService()

    def service(self: PrimitivePlannerACTPolicy) -> FakeService:
        return fake_service

    policy._primitive_dig_token_planning_service = MethodType(service, policy)
    cut_plan = _dig_plan(1.0, source="source")
    depth_plan = DigDepthProfileTokenPlan(
        token=_token(DIG_DEPTH_PROFILE_TOKEN_DIM, 1.0),
        source="source",
        fallback_reason="",
    )

    assert policy._build_dig_cut_tokens_for_obs({"id": "obs"}) == "cut"
    assert policy._apply_dig_cut_token_plan(cut_plan) == "applied-cut"
    assert policy._build_dig_depth_profile_tokens_for_obs({"id": "obs"}) == "depth"
    assert (
        policy._apply_dig_depth_profile_token_plan(depth_plan)
        == "applied-depth"
    )
    assert (
        policy._build_live_dig_depth_profile_tokens_for_obs({"id": "obs"}, cell_id=2)
        == "live-depth"
    )
    assert policy._dig_depth_profile_prior_token(3) == "prior-token"
    assert policy._dig_depth_profile_prior_mapping(4) == "prior-mapping"
    assert policy._dig_depth_profile_raw_fields({"id": "obs"}) == "raw-fields"
    assert policy._dig_depth_profile_cell_id({"id": "obs"}) == 5
    assert (
        policy._build_operator_prior_coverage_dig_cut_tokens({"id": "obs"})
        == "coverage-cut"
    )

    assert events == [
        ("build_cut", {"id": "obs"}),
        ("apply_cut", cut_plan),
        ("build_depth", {"id": "obs"}),
        ("apply_depth", depth_plan),
        ("live_depth", ({"id": "obs"}, 2)),
        ("prior_token", 3),
        ("prior_mapping", 4),
        ("raw_fields", {"id": "obs"}),
        ("cell_id", {"id": "obs"}),
        ("coverage_cut", {"id": "obs"}),
    ]
