from __future__ import annotations

from dataclasses import fields
from types import MappingProxyType, MethodType, SimpleNamespace
from typing import Any

import numpy as np
import pytest

from testbed.data.schema import ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX
from testbed.data.schema import ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX
from testbed.data.schema import ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX
from testbed.planner.primitive_capabilities import PrimitiveObservationFacts
from testbed.planner.primitive_return_token_planning import (
    PrimitiveReturnTokenPlanningPorts,
    PrimitiveReturnTokenPlanningService,
)
from testbed.planner.primitive_coverage_state import CoverageRuntimeState
from testbed.planner.primitive_token_state import PrimitiveTokenRuntimeState
from testbed.planner.primitive_tokens import (
    ReturnStartEnvelopeTokenPlan,
    ReturnTargetTokenPlan,
)
from testbed.policies.hybrid.primitive_planner import PrimitivePlannerACTPolicy


def _token(size: int, value: float) -> np.ndarray:
    return np.full(size, value, dtype=np.float32)


class _ReturnTargetPlanner:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.last_plan: ReturnTargetTokenPlan | None = None

    def _plan(
        self,
        event: str,
        *,
        value: float,
        source: str,
        corridor_id: int,
    ) -> ReturnTargetTokenPlan:
        self.events.append(event)
        plan = ReturnTargetTokenPlan(
            token=_token(3, value),
            raw_fields=MappingProxyType({"operator_entry_x_m": value}),
            source=source,
            fallback_reason=f"fallback_{source}",
            corridor_id=corridor_id,
        )
        self.last_plan = plan
        return plan

    def plan_conservative_pose(
        self,
        pose: tuple[float, float, float] | None,
    ) -> ReturnTargetTokenPlan:
        return self._plan(
            f"plan_conservative:{pose}",
            value=1.0,
            source="return_conservative_pose",
            corridor_id=-1,
        )

    def plan_operator_prior(
        self,
        pose: tuple[float, float, float] | None,
    ) -> ReturnTargetTokenPlan:
        return self._plan(
            f"plan_operator_prior:{pose}",
            value=2.0,
            source="return_operator_prior",
            corridor_id=-1,
        )

    def plan_from_coverage_raw_fields(
        self,
        raw_fields: dict[str, float | int],
        *,
        dig_cut_planner_mode: str,
        corridor_id: int,
    ) -> ReturnTargetTokenPlan:
        return self._plan(
            "plan_coverage:"
            f"{dig_cut_planner_mode}:{corridor_id}:{raw_fields['operator_entry_x_m']}",
            value=3.0,
            source=f"return_{dig_cut_planner_mode}",
            corridor_id=corridor_id,
        )


class _ReturnStartEnvelopePlanner:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.last_plan: ReturnStartEnvelopeTokenPlan | None = None

    def plan(
        self,
        *,
        raw_fields: dict[str, float | int],
        env_state: np.ndarray,
        qpos: np.ndarray,
        qvel: np.ndarray,
        cell_id: int | None,
    ) -> ReturnStartEnvelopeTokenPlan:
        self.events.append(
            "plan_start:"
            f"{raw_fields['operator_entry_x_m']}:{float(env_state[0])}:"
            f"{float(qpos[0])}:{float(qvel[0])}:{cell_id}"
        )
        plan = ReturnStartEnvelopeTokenPlan(
            token=_token(5, 4.0),
            source="start_planned",
            use_prior_spatial_bounds=False,
            use_prior_qpos_bounds=True,
        )
        self.last_plan = plan
        return plan

    def condition_token(
        self,
        token: np.ndarray,
        *,
        raw_fields: dict[str, float | int],
        source: str,
        use_prior_spatial_bounds: bool,
        use_prior_qpos_bounds: bool,
    ) -> ReturnStartEnvelopeTokenPlan:
        self.events.append(
            "condition_start:"
            f"{float(token[0])}:{raw_fields['operator_entry_x_m']}:{source}:"
            f"{use_prior_spatial_bounds}:{use_prior_qpos_bounds}"
        )
        plan = ReturnStartEnvelopeTokenPlan(
            token=_token(5, 5.0),
            source=f"{source}+conditioned",
            use_prior_spatial_bounds=True,
            use_prior_qpos_bounds=False,
        )
        self.last_plan = plan
        return plan

    def prior_token(self, *, cell_id: int | None) -> tuple[np.ndarray | None, str]:
        self.events.append(f"prior_token:{cell_id}")
        return _token(5, 6.0), f"cell_{cell_id}"

    def prior_mapping(self, *, cell_id: int | None) -> tuple[dict[str, object], str]:
        self.events.append(f"prior_mapping:{cell_id}")
        return {"cell_id": cell_id}, f"mapping_{cell_id}"

    def prior_bounds(
        self,
        *,
        cell_id: int | None,
    ) -> tuple[np.ndarray | None, np.ndarray | None]:
        self.events.append(f"prior_bounds:{cell_id}")
        return _token(2, 7.0), _token(2, 8.0)


def _ports(
    *,
    mode: str = "conservative_pose",
    prior_spatial: bool = True,
    prior_qpos: bool = False,
    events: list[str] | None = None,
) -> tuple[
    PrimitiveReturnTokenPlanningPorts,
    dict[str, object],
    list[str],
    _ReturnTargetPlanner,
    _ReturnStartEnvelopePlanner,
]:
    events = [] if events is None else events
    state: dict[str, object] = {
        "mode": mode,
    }
    target_planner = _ReturnTargetPlanner(events)
    start_planner = _ReturnStartEnvelopePlanner(events)
    corridor = SimpleNamespace(corridor_id=42, cell_id=9)
    token_state = PrimitiveTokenRuntimeState.fresh()
    token_state.return_start_envelope_token_source = "old"
    token_state.return_start_envelope_use_prior_spatial_bounds = bool(
        prior_spatial
    )
    token_state.return_start_envelope_use_prior_qpos_bounds = bool(prior_qpos)
    coverage_state = CoverageRuntimeState(coverage_corridors=[corridor])
    state["token_state"] = token_state
    state["coverage_state"] = coverage_state

    def observation_facts(obs: dict[str, Any]) -> PrimitiveObservationFacts:
        env_state = np.zeros(64, dtype=np.float32)
        if "env_state" in obs:
            incoming = np.asarray(obs["env_state"], dtype=np.float32).reshape(-1)
            env_state[: len(incoming)] = incoming
        if "pose_x" in obs:
            env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_X_IDX] = float(obs["pose_x"])
            env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Y_IDX] = float(obs["pose_y"])
            env_state[ENV_STATE_BUCKET_DIG_AREA_RELATIVE_Z_IDX] = float(obs["pose_z"])
        return PrimitiveObservationFacts.from_obs(
            {
                "env_state": env_state,
                "qpos": obs.get("qpos", np.zeros(4, dtype=np.float32)),
                "qvel": obs.get("qvel", np.zeros(4, dtype=np.float32)),
            },
            action_dim=4,
        )

    ports = PrimitiveReturnTokenPlanningPorts(
        token_state=token_state,
        coverage_state=coverage_state,
        dig_cut_planner_mode=lambda: str(state["mode"]),
        return_target_token_planner=lambda: target_planner,
        return_start_envelope_token_planner=lambda: start_planner,
        observation_facts=observation_facts,
        select_next_coverage_corridor=lambda obs: (
            events.append(f"select_corridor:{obs['id']}") or corridor
        ),
        coverage_raw_fields=lambda selected, *, obs, update_state: (
            events.append(
                "coverage_raw_fields:"
                f"{selected.corridor_id}:{obs['id']}:{update_state}"
            )
            or {"operator_entry_x_m": 12.5}
        ),
    )
    return ports, state, events, target_planner, start_planner


def test_conservative_and_operator_prior_routes_unpack_copy() -> None:
    ports, _, events, target_planner, _ = _ports(mode="conservative_pose")
    service = PrimitiveReturnTokenPlanningService.from_ports(ports)

    token, raw_fields, source, fallback, corridor_id = (
        service.build_next_dig_cut_plan_for_return(
            {"pose_x": 1, "pose_y": 2, "pose_z": 3}
        )
    )

    assert events == ["plan_conservative:(1.0, 2.0, 3.0)"]
    assert source == "return_conservative_pose"
    assert fallback == "fallback_return_conservative_pose"
    assert corridor_id == -1
    assert target_planner.last_plan is not None
    assert token is not target_planner.last_plan.token
    assert raw_fields == {"operator_entry_x_m": 1.0}
    token[0] = 99.0
    assert float(target_planner.last_plan.token[0]) == 1.0

    events.clear()
    ports, _, events, _, _ = _ports(mode="operator_prior", events=events)
    result = PrimitiveReturnTokenPlanningService.from_ports(
        ports
    ).build_next_dig_cut_plan_for_return({"pose_x": 4, "pose_y": 5, "pose_z": 6})

    assert events == ["plan_operator_prior:(4.0, 5.0, 6.0)"]
    assert result[2:] == ("return_operator_prior", "fallback_return_operator_prior", -1)


@pytest.mark.parametrize(
    "mode",
    ["operator_prior_coverage", "operator_prior_sweep_belief"],
)
def test_coverage_route_selects_sets_active_and_builds_raw_fields(mode: str) -> None:
    ports, state, events, _, _ = _ports(mode=mode)

    token, raw_fields, source, fallback, corridor_id = (
        PrimitiveReturnTokenPlanningService.from_ports(
            ports
        ).build_next_dig_cut_plan_for_return(
            {"id": "obs", "pose_x": 0, "pose_y": 0, "pose_z": 0}
        )
    )

    assert events == [
        "select_corridor:obs",
        "coverage_raw_fields:42:obs:True",
        f"plan_coverage:{mode}:42:12.5",
    ]
    coverage_state = state["coverage_state"]
    assert isinstance(coverage_state, CoverageRuntimeState)
    assert coverage_state.coverage_active_corridor_id == 42
    np.testing.assert_allclose(token, _token(3, 3.0))
    assert raw_fields == {"operator_entry_x_m": 3.0}
    assert source == f"return_{mode}"
    assert fallback == f"fallback_return_{mode}"
    assert corridor_id == 42


def test_unsupported_return_target_mode_keeps_old_error_shape() -> None:
    ports, _, _, _, _ = _ports(mode="not_real")

    with pytest.raises(
        ValueError,
        match="Unsupported dig_cut_planner mode 'not_real'\\.",
    ):
        PrimitiveReturnTokenPlanningService.from_ports(
            ports
        ).build_next_dig_cut_plan_for_return(
            {"pose_x": 0, "pose_y": 0, "pose_z": 0}
        )


def test_return_start_envelope_build_conditions_and_prior_helpers() -> None:
    ports, state, events, _, start_planner = _ports()
    service = PrimitiveReturnTokenPlanningService.from_ports(ports)
    obs = {
        "env_state": _token(3, 1.5),
        "qpos": _token(4, 2.5),
        "qvel": _token(4, 3.5),
    }

    token = service.build_return_start_envelope_tokens_for_obs(
        obs,
        {"operator_entry_x_m": 4.5},
        corridor_id=42,
    )

    assert events == [
        "plan_start:4.5:1.5:2.5:3.5:9",
    ]
    token_state = state["token_state"]
    assert isinstance(token_state, PrimitiveTokenRuntimeState)
    assert token_state.return_start_envelope_token_source == "start_planned"
    assert token_state.return_start_envelope_use_prior_spatial_bounds is False
    assert token_state.return_start_envelope_use_prior_qpos_bounds is True
    assert start_planner.last_plan is not None
    assert token is not start_planner.last_plan.token
    token[0] = 99.0
    assert float(start_planner.last_plan.token[0]) == 4.0

    events.clear()
    conditioned = service.condition_return_start_envelope_qpos_from_relocate(
        _token(5, 10.0),
        raw_fields={"operator_entry_x_m": 11.0},
        source="relocate",
    )

    assert events == [
        "condition_start:10.0:11.0:relocate:False:True",
    ]
    assert (
        token_state.return_start_envelope_token_source
        == "relocate+conditioned"
    )
    assert token_state.return_start_envelope_use_prior_spatial_bounds is True
    assert token_state.return_start_envelope_use_prior_qpos_bounds is False
    np.testing.assert_allclose(conditioned, _token(5, 5.0))

    events.clear()
    prior_token, prior_source = service.return_start_envelope_prior_token(
        corridor_id=42
    )
    prior_mapping, mapping_source = service.return_start_envelope_prior_mapping(
        corridor_id=99
    )
    prior_min, prior_max = service.return_start_envelope_prior_bounds(corridor_id=-1)

    assert events == [
        "prior_token:9",
        "prior_mapping:99",
        "prior_bounds:None",
    ]
    np.testing.assert_allclose(prior_token, _token(5, 6.0))
    assert prior_source == "cell_9"
    assert prior_mapping == {"cell_id": 99}
    assert mapping_source == "mapping_99"
    np.testing.assert_allclose(prior_min, _token(2, 7.0))
    np.testing.assert_allclose(prior_max, _token(2, 8.0))


def test_return_start_envelope_cell_id_preserves_current_fallbacks() -> None:
    ports, _, _, _, _ = _ports()
    service = PrimitiveReturnTokenPlanningService.from_ports(ports)

    assert service.return_start_envelope_cell_id(None) is None
    assert service.return_start_envelope_cell_id(42) == 9
    assert service.return_start_envelope_cell_id(99) == 99
    assert service.return_start_envelope_cell_id(-1) is None


def test_ports_boundary_is_typed_and_does_not_accept_planner_self() -> None:
    names = {field.name for field in fields(PrimitiveReturnTokenPlanningPorts)}
    removed_state_callbacks = {
        "set_coverage_active_corridor_id",
        "coverage_corridor_by_id",
        "get_return_start_envelope_use_prior_spatial_bounds",
        "get_return_start_envelope_use_prior_qpos_bounds",
        "set_return_start_envelope_token_source",
        "set_return_start_envelope_use_prior_spatial_bounds",
        "set_return_start_envelope_use_prior_qpos_bounds",
    }

    assert "planner" not in names
    assert "self" not in names
    assert "token_state" in names
    assert "coverage_state" in names
    assert "observation_facts" in names
    assert "return_target_token_planner" in names
    assert "return_start_envelope_token_planner" in names
    assert "bucket_dig_area_pose" not in names
    assert "env_state" not in names
    assert "qpos" not in names
    assert "qvel" not in names
    assert names.isdisjoint(removed_state_callbacks)


def test_policy_private_facades_delegate_to_return_token_planning_service() -> None:
    policy = object.__new__(PrimitivePlannerACTPolicy)
    events: list[tuple[str, object]] = []

    class FakeService:
        def build_next_dig_cut_plan_for_return(self, obs: dict[str, Any]):
            events.append(("build_next", obs))
            return "return-plan"

        def build_return_start_envelope_tokens_for_obs(
            self,
            obs: dict[str, Any],
            raw_fields: dict[str, float | int],
            *,
            corridor_id: int | None = None,
        ) -> str:
            events.append(("build_start", (obs, raw_fields, corridor_id)))
            return "start-token"

        def apply_return_start_envelope_token_plan(
            self,
            plan: ReturnStartEnvelopeTokenPlan,
        ) -> str:
            events.append(("apply_start", plan))
            return "applied"

        def condition_return_start_envelope_qpos_from_relocate(
            self,
            token: np.ndarray,
            *,
            raw_fields: dict[str, float | int],
            source: str,
        ) -> str:
            events.append(("condition", (float(token[0]), raw_fields, source)))
            return "conditioned"

        def return_start_envelope_prior_token(
            self,
            *,
            corridor_id: int | None,
        ) -> str:
            events.append(("prior_token", corridor_id))
            return "prior-token"

        def return_start_envelope_prior_mapping(
            self,
            *,
            corridor_id: int | None,
        ) -> str:
            events.append(("prior_mapping", corridor_id))
            return "prior-mapping"

        def return_start_envelope_prior_bounds(self, corridor_id: int | None) -> str:
            events.append(("prior_bounds", corridor_id))
            return "prior-bounds"

        def return_start_envelope_cell_id(self, corridor_id: int | None) -> int:
            events.append(("cell_id", corridor_id))
            return 123

    fake_service = FakeService()

    def service(self: PrimitivePlannerACTPolicy) -> FakeService:
        return fake_service

    policy._primitive_return_token_planning_service = MethodType(service, policy)
    plan = ReturnStartEnvelopeTokenPlan(
        token=_token(5, 1.0),
        source="source",
        use_prior_spatial_bounds=True,
        use_prior_qpos_bounds=False,
    )

    assert policy._build_next_dig_cut_plan_for_return({"id": "obs"}) == "return-plan"
    assert (
        policy._build_return_start_envelope_tokens_for_obs(
            {"id": "obs"},
            {"operator_entry_x_m": 1.0},
            corridor_id=7,
        )
        == "start-token"
    )
    assert policy._apply_return_start_envelope_token_plan(plan) == "applied"
    assert (
        policy._maybe_condition_return_start_envelope_qpos_from_relocate(
            _token(2, 2.0),
            raw_fields={"operator_entry_x_m": 3.0},
            source="source",
        )
        == "conditioned"
    )
    assert policy._return_start_envelope_prior_token(corridor_id=1) == "prior-token"
    assert (
        policy._return_start_envelope_prior_mapping(corridor_id=2)
        == "prior-mapping"
    )
    assert policy._return_start_envelope_prior_bounds(3) == "prior-bounds"
    assert policy._return_start_envelope_cell_id(4) == 123

    assert events == [
        ("build_next", {"id": "obs"}),
        ("build_start", ({"id": "obs"}, {"operator_entry_x_m": 1.0}, 7)),
        ("apply_start", plan),
        ("condition", (2.0, {"operator_entry_x_m": 3.0}, "source")),
        ("prior_token", 1),
        ("prior_mapping", 2),
        ("prior_bounds", 3),
        ("cell_id", 4),
    ]
